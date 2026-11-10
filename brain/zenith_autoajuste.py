"""Zenith — a IA propõe consertos no PRÓPRIO código; quem decide é o usuário (v1.6.2).

Fluxo (nada acontece sem um comando seu, em cada passo):
  1. A IA escreve <propor_ajuste>{json}</propor_ajuste>. O Cérebro só VALIDA e GUARDA (não roda nada, não muda nada).
  2. /ajuste ver N       -> você lê o que muda (diff), os avisos e o motivo.
  3. /ajuste testar N    -> numa CÓPIA temporária, roda os testes que cobrem esse módulo, antes e depois. (Aqui é a única
                            hora em que o código proposto roda, e só porque você pediu.)
  4. /ajuste aplicar N   -> grava a cópia aprovada em config/ajustes/overlay/. Vale a partir do PRÓXIMO início (o programa
                            em uso nunca é trocado). /ajuste desfazer volta ao que era; se o Zenith não abrir, o modo seguro
                            tira os ajustes sozinho (brain/zenith_overlay.py).

O que um ajuste NUNCA pode:
  * mexer em módulo protegido (aprovação, executor, segredos, configurações, atualização, pilares, este mecanismo);
  * ACRESCENTAR rede, subprocesso, eval/exec, apagar/renomear arquivo, endereço de internet novo, serialização perigosa
    ou referência ao mecanismo de segurança. (Ajuste que faz isso precisa virar atualização oficial.)
  * valer se o arquivo mudou desde que foi proposto (hash conferido) ou se os testes mostram falha NOVA.
Isso vale para o código-fonte aberto (instalação do Launcher). No .exe fechado não há .py para ler nem trocar.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from brain import zenith_overlay as ov

TAG = re.compile(r"<propor_ajuste>(.*?)</propor_ajuste>", re.S | re.I)
NOME_RE = re.compile(r"^(?:brain/)?(zenith_[a-z0-9_]+)(?:\.py)?$")
LIMITE_EDICOES = 12
LIMITE_BYTES = 300_000
LIMITE_PENDENTES = 20
LIMITE_MOTIVO = 400
LINHAS_TRECHO = 250
MAX_TRECHOS = 3
VALIDADE_TRECHO_S = 20 * 60
TEMPO_TESTES = 240

# Se a contagem destes padrões AUMENTAR no arquivo novo, o ajuste é recusado.
BLOQUEADOS = {
    "chamar programas (subprocess)": r"\bsubprocess\b",
    "chamar programas (os.system/popen/exec)": r"\bos\s*\.\s*(system|popen|exec\w*|spawn\w*|startfile)\b",
    "eval/exec/compile": r"(?<![\w.])(eval|exec|compile)\s*\(",
    "importação dinâmica": r"__import__|\bimportlib\b",
    "ctypes": r"\bctypes\b",
    "rede (socket, urllib, http, requests, websockets...)": r"\b(socket|urllib|http\.client|requests|websockets|ftplib|smtplib|aiohttp|httpx)\b",
    "serialização perigosa (pickle/marshal/shelve)": r"\b(pickle|marshal|shelve)\b",
    "apagar, mover ou renomear arquivos": r"\bshutil\s*\.\s*(rmtree|move)\b|\bos\s*\.\s*(remove|unlink|rmdir|removedirs|rename|replace)\b|\.unlink\s*\(|\.rmdir\s*\(",
    "endereço de internet novo": r"https?://",
    "mexer no mecanismo de segurança": r"zenith_(gatekeeper|executor|validator|autoajuste|overlay|quarentena|content_safety)\b",
    "mexer em sys.modules / meta_path": r"sys\s*\.\s*(modules|meta_path|path_hooks)",
}
# Só avisa (aparece em destaque no /ajuste ver):
ATENCAO = {
    "escreve em arquivo": r"\bopen\s*\([^)]*['\"][wax]\+?b?['\"]|\.write_(text|bytes)\s*\(",
    "lê variável de ambiente": r"\bos\s*\.\s*environ\b|\bgetenv\s*\(",
}


class ErroAjuste(Exception):
    pass


def _contar(padrao: str, texto: str) -> int:
    return len(re.findall(padrao, texto))


def _imports(codigo: str) -> set:
    try:
        arvore = ast.parse(codigo)
    except SyntaxError:
        return set()
    achados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
            achados.add(no.module.split(".")[0])
    return achados


def _stdlib() -> set:
    return set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def normalizar_arquivo(valor) -> str:
    """'brain/zenith_x.py' | 'zenith_x' -> 'zenith_x.py' (ou '' se não for um módulo do Cérebro)."""
    m = NOME_RE.match(str(valor or "").strip().replace("\\", "/"))
    return (m.group(1) + ".py") if m else ""


def extrair_propostas(texto: str) -> list:
    return [b.strip() for b in TAG.findall(texto or "")]


def _limpar_json(bruto: str) -> str:
    s = bruto.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    return s.strip()


# ============================================================================ o gerenciador
class Ajustes:
    def __init__(self, raiz_codigo, pasta_ajustes):
        self.raiz = Path(raiz_codigo)
        self.pasta = Path(pasta_ajustes)
        self.propostas = self.pasta / "propostas"
        self._trechos = []                      # [(quando, arquivo, ini, fim, texto)] só em memória

    # ---------------------------------------------------------------- leitura do código
    def fonte_disponivel(self) -> bool:
        return (self.raiz / "brain" / "zenith_core.py").is_file()

    def _arquivo_efetivo(self, nome: str):
        m = ov.ler_manifesto(self.pasta)
        if nome in m["arquivos"]:
            a = ov.pasta_overlay(self.pasta) / nome
            if a.is_file():
                return a
        a = self.raiz / "brain" / nome
        return a if a.is_file() else None

    def fonte_atual(self, nome: str):
        a = self._arquivo_efetivo(nome)
        return a.read_bytes().decode("utf-8") if a else None

    def ler_trecho(self, arquivo, ini=None, fim=None) -> tuple:
        """-> (texto_com_cabecalho, erro). Só módulos do Cérebro; no máximo 250 linhas por vez."""
        nome = normalizar_arquivo(arquivo)
        if not nome:
            return "", "Só leio módulos do Cérebro (ex.: brain/zenith_movimentos.py)."
        if not self.fonte_disponivel():
            return "", "Esta instalação é o executável fechado: não há código-fonte para ler. O autoajuste vale na instalação do Launcher."
        src = self.fonte_atual(nome)
        if src is None:
            return "", f"Não achei {nome}."
        linhas = src.replace("\r\n", "\n").split("\n")
        total = len(linhas)
        ini = max(1, int(ini or 1))
        fim = min(total, int(fim or (ini + LINHAS_TRECHO - 1)))
        if fim < ini:
            return "", "Intervalo de linhas inválido."
        if fim - ini + 1 > LINHAS_TRECHO:
            fim = ini + LINHAS_TRECHO - 1
        corpo = "\n".join(linhas[ini - 1:fim])
        cab = f"brain/{nome}, linhas {ini}-{fim} de {total}"
        self._trechos.append((time.time(), nome, ini, fim, corpo))
        del self._trechos[:-MAX_TRECHOS]
        return f"{cab}\n{corpo}", ""

    def bloco_contexto(self) -> str:
        """Trechos que você (ou ela) pediu para ver: entram no prompt por 20 minutos, para ela conseguir propor o conserto."""
        agora = time.time()
        vivos = [t for t in self._trechos if agora - t[0] <= VALIDADE_TRECHO_S]
        self._trechos = vivos
        if not vivos:
            return ""
        partes = ["\n\nTRECHOS DO SEU PRÓPRIO CÓDIGO (somente leitura; para propor conserto use <propor_ajuste>, ver Bíblia):"]
        for _, nome, ini, fim, corpo in vivos:
            partes.append(f"--- brain/{nome}, linhas {ini}-{fim} ---\n{corpo}")
        return "\n".join(partes)

    # ---------------------------------------------------------------- validação
    def _montar(self, dados: dict) -> dict:
        """Aplica a proposta ao texto atual e roda TODAS as verificações estáticas. Levanta ErroAjuste com a razão."""
        if not isinstance(dados, dict):
            raise ErroAjuste("A proposta precisa ser um objeto JSON.")
        nome = normalizar_arquivo(dados.get("arquivo"))
        if not nome:
            raise ErroAjuste("'arquivo' precisa ser um módulo do Cérebro, como brain/zenith_movimentos.py.")
        if nome in ov.PROTEGIDOS:
            raise ErroAjuste(f"{nome} é protegido (aprovação, segredos, configurações, atualização ou o próprio mecanismo). "
                             "Isso só muda por atualização oficial do Zenith.")
        motivo = str(dados.get("motivo") or "").strip()
        if len(motivo) < 10:
            raise ErroAjuste("Explique em 'motivo' o que está errado e como o conserto resolve (pelo menos uma frase).")
        motivo = motivo[:LIMITE_MOTIVO]
        if not self.fonte_disponivel():
            raise ErroAjuste("Esta instalação é o executável fechado: não há código-fonte para ajustar.")
        atual_bytes = self._arquivo_efetivo(nome)
        atual = atual_bytes.read_bytes().decode("utf-8") if atual_bytes else None
        if "conteudo" in dados and "edicoes" not in dados:
            if atual is not None:
                raise ErroAjuste(f"{nome} já existe: use 'edicoes' (antigo/novo) em vez de mandar o arquivo inteiro.")
            novo = str(dados["conteudo"])
            eol, base = "\n", ""
            edicoes = []
        else:
            if atual is None:
                raise ErroAjuste(f"{nome} não existe. Para criar um módulo novo mande 'conteudo' com o arquivo inteiro.")
            edicoes = dados.get("edicoes")
            if not isinstance(edicoes, list) or not edicoes:
                raise ErroAjuste("Falta a lista 'edicoes': [{\"antigo\": \"trecho exato\", \"novo\": \"trecho novo\"}].")
            if len(edicoes) > LIMITE_EDICOES:
                raise ErroAjuste(f"No máximo {LIMITE_EDICOES} edições por proposta.")
            eol = "\r\n" if "\r\n" in atual else "\n"
            base = atual.replace("\r\n", "\n")
            novo = base
            for i, e in enumerate(edicoes, 1):
                if not isinstance(e, dict) or not isinstance(e.get("antigo"), str) or not isinstance(e.get("novo"), str):
                    raise ErroAjuste(f"Edição {i}: precisa de 'antigo' e 'novo' (texto).")
                ant, nov = e["antigo"].replace("\r\n", "\n"), e["novo"].replace("\r\n", "\n")
                if not ant.strip():
                    raise ErroAjuste(f"Edição {i}: 'antigo' está vazio.")
                if ant == nov:
                    raise ErroAjuste(f"Edição {i}: 'antigo' e 'novo' são iguais.")
                n = novo.count(ant)
                if n == 0:
                    raise ErroAjuste(f"Edição {i}: o trecho 'antigo' não existe no arquivo (copie exatamente, sem números de linha).")
                if n > 1:
                    raise ErroAjuste(f"Edição {i}: o trecho 'antigo' aparece {n} vezes; inclua mais linhas em volta para ser único.")
                novo = novo.replace(ant, nov, 1)
            if novo == base:
                raise ErroAjuste("A proposta não muda nada.")
        if len(novo.encode("utf-8")) > LIMITE_BYTES:
            raise ErroAjuste("O arquivo novo passaria de 300 KB.")
        try:
            ast.parse(novo)
            compile(novo, nome, "exec")
        except SyntaxError as e:
            raise ErroAjuste(f"O arquivo novo não compila: {e.msg} (linha {e.lineno}).")
        bloqueios, avisos = [], []
        velho = base
        for rotulo, pad in BLOQUEADOS.items():
            antes, depois = _contar(pad, velho), _contar(pad, novo)
            if depois > antes:
                bloqueios.append(f"{rotulo}: de {antes} para {depois}")
        if bloqueios:
            raise ErroAjuste("O ajuste acrescentaria algo que só uma atualização oficial pode trazer — " + "; ".join(bloqueios) + ".")
        for rotulo, pad in ATENCAO.items():
            antes, depois = _contar(pad, velho), _contar(pad, novo)
            if depois > antes:
                avisos.append(f"{rotulo}: de {antes} para {depois}")
        novos_imports = sorted((_imports(novo) - _imports(velho)) - _stdlib() - {"brain"})
        if novos_imports:
            avisos.append("importa biblioteca nova: " + ", ".join(novos_imports))
        diff = "".join(difflib.unified_diff(velho.splitlines(True), novo.replace("\r\n", "\n").splitlines(True),
                                            f"brain/{nome} (atual)", f"brain/{nome} (proposto)", n=3))
        texto_final = novo.replace("\n", eol) if eol == "\r\n" else novo
        return {"arquivo": nome, "motivo": motivo, "novo_texto": texto_final, "diff": diff, "avisos": avisos,
                "base_sha256": hashlib.sha256(atual.encode("utf-8")).hexdigest() if atual is not None else "",
                "novo_sha256": hashlib.sha256(texto_final.encode("utf-8")).hexdigest(),
                "criar": atual is None}

    # ---------------------------------------------------------------- guardar / listar
    def _proposta_dir(self, id_: int) -> Path:
        return self.propostas / str(int(id_))

    def _proximo_id(self) -> int:
        arq = self.pasta / "contador.json"
        n = int((ov._json(arq, {}) or {}).get("proximo", 1))
        ov._gravar_json(arq, {"proximo": n + 1})
        return n

    def carregar(self, id_):
        try:
            return json.loads((self._proposta_dir(int(id_)) / "proposta.json").read_text(encoding="utf-8"))
        except Exception:
            return None

    def _salvar(self, p: dict):
        ov._gravar_json(self._proposta_dir(p["id"]) / "proposta.json", p)

    def listar(self) -> list:
        saida = []
        if self.propostas.exists():
            for d in self.propostas.iterdir():
                if d.name.isdigit():
                    p = self.carregar(int(d.name))
                    if p:
                        saida.append(p)
        return sorted(saida, key=lambda p: p["id"])

    def propor(self, bruto: str) -> dict:
        """Valida e guarda. NÃO roda nada. -> {'ok', 'id', 'mensagem'}."""
        try:
            dados = json.loads(_limpar_json(bruto))
        except Exception as e:
            return {"ok": False, "id": 0, "mensagem": f"Não entendi a proposta de ajuste (JSON inválido: {e})."}
        pendentes = [p for p in self.listar() if p["estado"] in ("pendente", "testado_ok", "testado_falhou")]
        if len(pendentes) >= LIMITE_PENDENTES:
            return {"ok": False, "id": 0, "mensagem": "Há ajustes demais esperando você (20). Recuse ou aplique alguns com /ajustes."}
        try:
            plano = self._montar(dados)
        except ErroAjuste as e:
            return {"ok": False, "id": 0, "mensagem": f"O ajuste que propus foi recusado antes de chegar a você: {e}"}
        id_ = self._proximo_id()
        d = self._proposta_dir(id_)
        d.mkdir(parents=True, exist_ok=True)
        (d / "novo.py").write_bytes(plano["novo_texto"].encode("utf-8"))
        (d / "diff.patch").write_text(plano["diff"], encoding="utf-8")
        p = {"id": id_, "quando": time.strftime("%Y-%m-%d %H:%M"), "arquivo": plano["arquivo"], "motivo": plano["motivo"],
             "estado": "pendente", "avisos": plano["avisos"], "base_sha256": plano["base_sha256"],
             "novo_sha256": plano["novo_sha256"], "criar": plano["criar"], "teste": None}
        self._salvar(p)
        extra = (" Atenção: " + "; ".join(plano["avisos"]) + ".") if plano["avisos"] else ""
        return {"ok": True, "id": id_, "mensagem":
                f"Propus o ajuste #{id_} em brain/{plano['arquivo']}: {plano['motivo']} Nada foi alterado. "
                f"Veja com /ajuste ver {id_}, teste com /ajuste testar {id_} e, se concordar, /ajuste aplicar {id_}.{extra}"}

    # ---------------------------------------------------------------- ver
    def ver(self, id_) -> str:
        p = self.carregar(id_)
        if not p:
            return f"Não existe o ajuste #{id_}."
        diff = (self._proposta_dir(p["id"]) / "diff.patch").read_text(encoding="utf-8") if (self._proposta_dir(p["id"]) / "diff.patch").exists() else ""
        linhas = diff.splitlines()
        if len(linhas) > 160:
            diff = "\n".join(linhas[:160]) + f"\n... (+{len(linhas) - 160} linhas)"
        t = p.get("teste")
        if t is None:
            teste = "Testes: ainda não rodei (use /ajuste testar)."
        elif not t.get("rodou"):
            teste = f"Testes: não rodei ({t.get('motivo', '')})."
        else:
            teste = (f"Testes: {t['ran']} rodados; falhas novas: {len(t['novas'])}; corrigidas: {len(t['corrigidas'])}"
                     + (f" ({', '.join(t['novas'][:5])})" if t["novas"] else "") + ".")
        av = ("\nAtenção: " + "; ".join(p["avisos"])) if p["avisos"] else ""
        return (f"Ajuste #{p['id']} ({p['estado']}) em brain/{p['arquivo']} — {p['quando']}\nMotivo: {p['motivo']}{av}\n{teste}\n\n"
                f"```diff\n{diff}\n```")

    # ---------------------------------------------------------------- testar (só quando você pede)
    def _py_console(self) -> str:
        exe = sys.executable or ""
        if exe.lower().endswith("pythonw.exe"):
            c = exe[:-len("pythonw.exe")] + "python.exe"
            if os.path.exists(c):
                return c
        return exe

    def _tests_do_modulo(self, raiz_stage: Path, nome: str) -> list:
        stem = nome[:-3]
        achados = []
        pasta = raiz_stage / "tests"
        if pasta.exists():
            for t in sorted(pasta.glob("test_*.py")):
                try:
                    if stem in t.read_text(encoding="utf-8", errors="ignore"):
                        achados.append("tests." + t.stem)
                except OSError:
                    pass
        return achados

    @staticmethod
    def analisar_saida(saida: str) -> dict:
        ran = re.search(r"Ran (\d+) tests?", saida)
        falhas = set(re.findall(r"^(?:FAIL|ERROR): (.+)$", saida, re.M))
        return {"ran": int(ran.group(1)) if ran else 0, "falhas": falhas, "terminou": bool(ran)}

    def _executar_testes(self, py, modulos, cwd, executar=None) -> dict:
        env = dict(os.environ, ZENITH_TESTE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        cmd = [py, "-m", "unittest"] + list(modulos)
        try:
            if executar:
                saida = executar(cmd, str(cwd), env, TEMPO_TESTES)
            else:
                r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, errors="replace",
                                   timeout=TEMPO_TESTES, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                saida = (r.stdout or "") + "\n" + (r.stderr or "")
        except subprocess.TimeoutExpired:
            return {"ran": 0, "falhas": set(), "terminou": False, "motivo": "estourou o tempo"}
        return self.analisar_saida(saida)

    def testar(self, id_, executar=None) -> dict:
        """Roda os testes que citam o módulo, na cópia SEM e COM o ajuste. Guarda o resultado na proposta."""
        p = self.carregar(id_)
        if not p:
            return {"ok": False, "mensagem": f"Não existe o ajuste #{id_}."}
        if p["estado"] in ("aplicado", "recusado", "desfeito"):
            return {"ok": False, "mensagem": f"O ajuste #{p['id']} está '{p['estado']}'."}
        if not self.fonte_disponivel():
            return {"ok": False, "mensagem": "Não há código-fonte nesta instalação."}
        novo = (self._proposta_dir(p["id"]) / "novo.py").read_bytes()
        stage = Path(tempfile.mkdtemp(prefix="zenith_ajuste_"))
        try:
            ign = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "_zenith_testes_tmp")
            for d in ("brain", "tests", "tools", "launcher", "site"):
                if (self.raiz / d).is_dir():
                    shutil.copytree(self.raiz / d, stage / d, ignore=ign)
            for f in ("requirements.txt", "zenith_launcher.py"):
                if (self.raiz / f).is_file():
                    shutil.copy2(self.raiz / f, stage / f)
            cat = self.raiz / "config" / "provedores_catalogo.json"
            if cat.is_file():
                (stage / "config").mkdir(exist_ok=True)
                shutil.copy2(cat, stage / "config" / cat.name)
            m = ov.ler_manifesto(self.pasta)                       # ajustes já aplicados também valem na cópia
            for nome in m["arquivos"]:
                a = ov.pasta_overlay(self.pasta) / nome
                if a.is_file():
                    shutil.copy2(a, stage / "brain" / nome)
            modulos = self._tests_do_modulo(stage, p["arquivo"])
            py = self._py_console()
            if not modulos:
                modulos_fumaca = None
                resultado = {"rodou": False, "motivo": "nenhum teste do projeto cita este módulo", "ran": 0, "novas": [], "corrigidas": []}
                # ao menos conferir que importa
                (stage / "brain" / p["arquivo"]).write_bytes(novo)
                cmd = [py, "-c", f"import brain.{p['arquivo'][:-3]}"]
                try:
                    if executar:
                        executar(cmd, str(stage), dict(os.environ, ZENITH_TESTE="1"), 60)
                        resultado["importa"] = True
                    else:
                        r = subprocess.run(cmd, cwd=str(stage), env=dict(os.environ, ZENITH_TESTE="1", PYTHONDONTWRITEBYTECODE="1"),
                                           capture_output=True, text=True, timeout=60,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        resultado["importa"] = r.returncode == 0
                except Exception:
                    resultado["importa"] = False
                p["estado"] = "testado_ok" if resultado["importa"] else "testado_falhou"
                p["teste"] = resultado
                self._salvar(p)
                texto = ("Nenhum teste do projeto cobre esse módulo, então só conferi que ele ainda importa: "
                         + ("importa." if resultado["importa"] else "NÃO importa — não aplique."))
                return {"ok": resultado["importa"], "mensagem": texto, "resultado": resultado}
            antes = self._executar_testes(py, modulos, stage, executar)
            (stage / "brain" / p["arquivo"]).write_bytes(novo)
            depois = self._executar_testes(py, modulos, stage, executar)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        if not antes["terminou"] or not depois["terminou"]:
            res = {"rodou": False, "motivo": "os testes não terminaram (tempo ou erro ao iniciar)", "ran": 0, "novas": [], "corrigidas": []}
            p["teste"], p["estado"] = res, "testado_falhou"
            self._salvar(p)
            return {"ok": False, "mensagem": "Os testes não terminaram; por segurança não conto como aprovado.", "resultado": res}
        novas = sorted(depois["falhas"] - antes["falhas"])
        corrigidas = sorted(antes["falhas"] - depois["falhas"])
        res = {"rodou": True, "ran": depois["ran"], "modulos": modulos, "novas": novas, "corrigidas": corrigidas,
               "falhavam_antes": len(antes["falhas"])}
        ok = not novas
        p["teste"], p["estado"] = res, ("testado_ok" if ok else "testado_falhou")
        self._salvar(p)
        msg = (f"Testei o ajuste #{p['id']} ({depois['ran']} testes em {len(modulos)} arquivo(s)): "
               f"{len(novas)} falha(s) nova(s), {len(corrigidas)} corrigida(s). "
               + ("Pode aplicar com /ajuste aplicar " + str(p["id"]) + "." if ok else "NÃO aplique: " + ", ".join(novas[:3])))
        return {"ok": ok, "mensagem": msg, "resultado": res}

    # ---------------------------------------------------------------- aplicar / recusar / desfazer
    def aplicar(self, id_, sem_teste: bool = False) -> dict:
        p = self.carregar(id_)
        if not p:
            return {"ok": False, "mensagem": f"Não existe o ajuste #{id_}."}
        if p["estado"] == "testado_falhou":
            return {"ok": False, "mensagem": "Os testes desse ajuste mostraram falha nova; não aplico."}
        if p["estado"] not in ("pendente", "testado_ok"):
            return {"ok": False, "mensagem": f"O ajuste #{p['id']} está '{p['estado']}'."}
        if p["estado"] == "pendente" and not sem_teste:
            return {"ok": False, "mensagem": f"Ainda não testei o #{p['id']}. Rode /ajuste testar {p['id']} "
                                             f"(ou, por sua conta e risco, /ajuste aplicar {p['id']} sem-teste)."}
        nome = p["arquivo"]
        atual = self.fonte_atual(nome)
        atual_sha = hashlib.sha256(atual.encode("utf-8")).hexdigest() if atual is not None else ""
        if atual_sha != p["base_sha256"]:
            return {"ok": False, "mensagem": "O arquivo mudou depois que essa proposta foi feita (outro ajuste ou atualização). "
                                             "Recuse este e peça uma proposta nova."}
        novo = (self._proposta_dir(p["id"]) / "novo.py").read_bytes()
        if hashlib.sha256(novo).hexdigest() != p["novo_sha256"]:
            return {"ok": False, "mensagem": "O arquivo guardado da proposta foi alterado; recuso por segurança."}
        destino = ov.pasta_overlay(self.pasta) / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(destino.name + ".tmp")
        tmp.write_bytes(novo)
        os.replace(tmp, destino)
        m = ov.ler_manifesto(self.pasta)
        m["arquivos"][nome] = {"sha256": p["novo_sha256"], "id": p["id"], "quando": time.strftime("%Y-%m-%d %H:%M")}
        m["pilhas"].setdefault(nome, []).append(p["id"])
        m["historico"].append({"quando": time.strftime("%Y-%m-%d %H:%M"), "evento": "aplicado", "id": p["id"], "arquivo": nome})
        ov.gravar_manifesto(self.pasta, m)
        p["estado"] = "aplicado"
        self._salvar(p)
        return {"ok": True, "mensagem": f"Ajuste #{p['id']} aplicado em brain/{nome}. Vale a partir do PRÓXIMO início do Zenith "
                                        f"(feche e abra). Para voltar atrás: /ajuste desfazer {p['id']}."}

    def recusar(self, id_) -> dict:
        p = self.carregar(id_)
        if not p:
            return {"ok": False, "mensagem": f"Não existe o ajuste #{id_}."}
        if p["estado"] in ("aplicado",):
            return {"ok": False, "mensagem": "Esse já foi aplicado; use /ajuste desfazer."}
        p["estado"] = "recusado"
        self._salvar(p)
        return {"ok": True, "mensagem": f"Ajuste #{p['id']} recusado. Nada mudou."}

    def desfazer(self, id_=None) -> dict:
        m = ov.ler_manifesto(self.pasta)
        if id_ in (None, ""):
            aplicados = [h for h in m["historico"] if h.get("evento") == "aplicado" and m["pilhas"].get(h["arquivo"], [None])[-1] == h["id"]]
            if not aplicados:
                return {"ok": False, "mensagem": "Não há ajuste aplicado para desfazer."}
            id_ = aplicados[-1]["id"]
        p = self.carregar(id_)
        if not p or p["estado"] != "aplicado":
            return {"ok": False, "mensagem": f"O ajuste #{id_} não está aplicado."}
        nome = p["arquivo"]
        pilha = m["pilhas"].get(nome, [])
        if not pilha or pilha[-1] != p["id"]:
            topo = pilha[-1] if pilha else "?"
            return {"ok": False, "mensagem": f"Há um ajuste mais novo (#{topo}) em cima deste em {nome}. Desfaça o #{topo} primeiro."}
        pilha.pop()
        destino = ov.pasta_overlay(self.pasta) / nome
        if pilha:
            anterior = self.carregar(pilha[-1])
            novo = (self._proposta_dir(anterior["id"]) / "novo.py").read_bytes()
            destino.write_bytes(novo)
            m["arquivos"][nome] = {"sha256": hashlib.sha256(novo).hexdigest(), "id": anterior["id"], "quando": time.strftime("%Y-%m-%d %H:%M")}
        else:
            m["pilhas"].pop(nome, None)
            m["arquivos"].pop(nome, None)
            try:
                destino.unlink()
            except OSError:
                pass
        m["historico"].append({"quando": time.strftime("%Y-%m-%d %H:%M"), "evento": "desfeito", "id": p["id"], "arquivo": nome})
        ov.gravar_manifesto(self.pasta, m)
        p["estado"] = "desfeito"
        self._salvar(p)
        return {"ok": True, "mensagem": f"Ajuste #{p['id']} desfeito. Vale a partir do próximo início do Zenith."}

    def resumo(self) -> str:
        itens = self.listar()
        if not itens:
            return "Nenhum ajuste de código proposto ainda. Quando algo do meu código falhar, eu proponho; você decide."
        linhas = ["Ajustes de código (você aprova cada um; nada vale sem /ajuste aplicar):"]
        for p in itens[-15:]:
            linhas.append(f"- #{p['id']} [{p['estado']}] brain/{p['arquivo']} — {p['motivo'][:90]}")
        linhas.append("Comandos: /ajuste ver N, testar N, aplicar N, recusar N, desfazer [N], codigo <arquivo> [inicio-fim]")
        return "\n".join(linhas)


# ============================================================================ uso no dia a dia
def padrao() -> Ajustes:
    """O gerenciador de verdade: código ao lado de `brain/`, ajustes em config/ajustes/."""
    from brain.zenith_settings import BASE_DIR, CONFIG_DIR
    return Ajustes(BASE_DIR, Path(CONFIG_DIR) / "ajustes")


_CACHE = {}


def instancia() -> Ajustes:
    if "a" not in _CACHE:
        _CACHE["a"] = padrao()
    return _CACHE["a"]
