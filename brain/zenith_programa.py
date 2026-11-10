"""
Zenith — Modo "criar programa" (v21).

O que o v20 não deixava: o `<executar_python>` roda escondido, sem janela, sem teclado e é morto aos
15 segundos — então jogo, janela, servidor ou site "não funcionavam". Aqui há um caminho próprio:

    <criar_programa nome="jogo_da_velha" tipo="janela" abrir="main.py">
    <arquivo nome="main.py"> ...código... </arquivo>
    <arquivo nome="dados/niveis.json"> ... </arquivo>
    </criar_programa>

  * UMA pasta por programa: creations/programas/<nome>/ (arquivos antigos que serão sobrescritos
    vão pra _backup/<data-hora>/ — nada se perde).
  * Vários arquivos, em qualquer linguagem de TEXTO (py, html, css, js, c, cpp, java, ino, rs, go...).
    Só Python (.py) e páginas web (.html) o Zenith sabe RODAR sozinho; o resto é gravado e a Zenith
    diz como compilar/rodar (aí cada comando passa pela aprovação normal de terminal).
  * tipo="janela"  → Python com janela própria (tkinter/pygame/etc.), sem teto de 15 s; a saída vai
                     pra _zenith_log.txt. Se fechar com erro nos primeiros segundos, o log VOLTA
                     pra IA (ela lê e conserta, dentro do limite de passos da cadeia).
    tipo="console" → Python numa janela de console de verdade (aceita input()).
    tipo="web"     → abre a página .html no navegador padrão.
  * Continua tudo sob o Pilar 1: o diálogo de aprovação mostra a pasta, os arquivos e o começo do
    código; a lista negra do Gatekeeper vale pra TODOS os arquivos; nada roda sem aprovação.
  * Botão "Parar": /parar_programa [nome] (e /programas lista).

Honesto sobre o que ficou de fora: não instala bibliotecas sozinho (a IA propõe `pip install` e você
aprova), e no .exe sem Python no PC cai no interpretador EMBUTIDO, que só tem as bibliotecas
empacotadas (a mensagem avisa).
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

LIMITE_ARQUIVOS = 20
LIMITE_BYTES_ARQUIVO = 300_000
LIMITE_BYTES_TOTAL = 800_000
TIPOS = ("janela", "console", "web")

EXT_PERMITIDAS = {
    ".py", ".pyw", ".txt", ".md", ".json", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".htm", ".css", ".js", ".mjs", ".ts", ".svg", ".xml",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".lua", ".sql",
    ".r", ".ino", ".gd", ".gdshader", ".tex", ".asm", ".v", ".vhd", ".sh",
}
_RESERVADOS_WIN = {"con", "prn", "aux", "nul", *{f"com{i}" for i in range(1, 10)},
                   *{f"lpt{i}" for i in range(1, 10)}}

_RE_PROG = re.compile(r"<criar_programa\b([^>]*)>(.*?)</criar_programa>", re.S | re.I)
_RE_ARQ = re.compile(r"<arquivo\b([^>]*)>(.*?)</arquivo>", re.S | re.I)
_RE_ATTR = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

_PROCS: dict = {}          # nome -> subprocess.Popen (programas que ficaram rodando)


# ======================================================================
#  Interpretar a tag
# ======================================================================
def limpar_codigo(texto: str) -> str:
    """Tira a cerca de markdown (```python ... ```) que muitas IAs põem DENTRO da tag — ela viraria
    erro de sintaxe. Só mexe quando a cerca embrulha o texto inteiro."""
    t = (texto or "").strip("\r\n")
    m = re.match(r"^\s*```[\w+-]*[ \t]*\r?\n(.*?)\r?\n?```\s*$", t, re.S)
    if m:
        return m.group(1)
    return t.strip("\n")


def _attrs(trecho: str) -> dict:
    return {k.lower(): (a if a is not None and a != "" else b or "") for k, a, b in _RE_ATTR.findall(trecho or "")}


def nome_seguro_pasta(nome: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", str(nome or "").strip(), flags=re.UNICODE).strip("_.")
    return s[:40]


def nome_arquivo_seguro(rel: str):
    """'dados\\x.json' -> 'dados/x.json'. None se for absoluto, tiver '..', nome reservado do Windows,
    caractere esquisito ou extensão fora da lista."""
    r = str(rel or "").strip().replace("\\", "/")
    if not r or r.startswith("/") or re.match(r"^[A-Za-z]:", r) or len(r) > 100:
        return None
    partes = r.split("/")
    for p in partes:
        if p in ("", ".", "..") or p.startswith(".") or p.endswith((" ", ".")):
            return None
        if not re.match(r"^[\w\-. ()\[\]]+$", p, flags=re.UNICODE):
            return None
        if p.split(".")[0].lower() in _RESERVADOS_WIN:
            return None
    if Path(partes[-1]).suffix.lower() not in EXT_PERMITIDAS:
        return None
    return "/".join(partes)


@dataclass
class ProgramaProposto:
    nome: str = ""
    tipo: str = ""
    abrir: str = ""
    arquivos: dict = field(default_factory=dict)       # caminho relativo -> texto
    erros: list = field(default_factory=list)


def interpretar(conteudo: str) -> ProgramaProposto:
    """Lê o texto da tag (a tag inteira). Não levanta exceção: problemas vão em `.erros`."""
    p = ProgramaProposto()
    m = _RE_PROG.search(conteudo or "")
    if not m:
        p.erros.append("não achei a tag <criar_programa>...</criar_programa> completa")
        return p
    at = _attrs(m.group(1))
    corpo = m.group(2)
    p.nome = nome_seguro_pasta(at.get("nome", ""))
    p.tipo = (at.get("tipo") or "").lower()
    p.abrir = (at.get("abrir") or "").strip()

    blocos = _RE_ARQ.findall(corpo)
    if blocos:
        for attrs_txt, texto in blocos:
            rel_bruto = _attrs(attrs_txt).get("nome", "")
            rel = nome_arquivo_seguro(rel_bruto)
            if rel is None:
                p.erros.append(f"nome de arquivo não permitido: '{rel_bruto}'")
                continue
            if rel in p.arquivos:
                p.erros.append(f"arquivo repetido: {rel}")
                continue
            p.arquivos[rel] = limpar_codigo(texto)
    else:                               # a IA pôs o código direto na tag: vira um arquivo só
        texto = limpar_codigo(corpo)
        if texto.strip():
            padrao = p.abrir or ("index.html" if p.tipo == "web" else "main.py")
            rel = nome_arquivo_seguro(padrao)
            if rel is None:
                p.erros.append(f"nome de arquivo não permitido: '{padrao}'")
            else:
                p.arquivos[rel] = texto

    if not p.tipo:                      # deduz o tipo
        so_web = p.arquivos and all(Path(a).suffix.lower() in (".html", ".htm", ".css", ".js", ".svg", ".json")
                                    for a in p.arquivos) and any(a.lower().endswith((".html", ".htm")) for a in p.arquivos)
        p.tipo = "web" if so_web else "janela"
    if not p.abrir:
        p.abrir = _escolher_principal(p)
    return p


def _escolher_principal(p: ProgramaProposto) -> str:
    nomes = list(p.arquivos)
    if p.tipo == "web":
        for pref in ("index.html", "index.htm"):
            if pref in nomes:
                return pref
        for a in nomes:
            if a.lower().endswith((".html", ".htm")):
                return a
    for pref in ("main.py", "app.py", "jogo.py", "__main__.py"):
        if pref in nomes:
            return pref
    for a in nomes:
        if a.lower().endswith((".py", ".pyw")):
            return a
    return nomes[0] if nomes else ""


def validar(p: ProgramaProposto) -> list:
    erros = list(p.erros)
    if not p.nome:
        erros.append("faltou o nome do programa (nome=\"...\")")
    if p.tipo not in TIPOS:
        erros.append(f"tipo inválido '{p.tipo}' (use: {', '.join(TIPOS)})")
    if not p.arquivos:
        erros.append("nenhum arquivo foi enviado")
    if len(p.arquivos) > LIMITE_ARQUIVOS:
        erros.append(f"arquivos demais ({len(p.arquivos)}; o limite é {LIMITE_ARQUIVOS})")
    total = 0
    for rel, txt in p.arquivos.items():
        tam = len(txt.encode("utf-8"))
        total += tam
        if tam > LIMITE_BYTES_ARQUIVO:
            erros.append(f"{rel} é grande demais ({tam // 1000} KB; o limite é {LIMITE_BYTES_ARQUIVO // 1000} KB)")
    if total > LIMITE_BYTES_TOTAL:
        erros.append(f"o conjunto passa de {LIMITE_BYTES_TOTAL // 1000} KB")
    if p.abrir and p.abrir not in p.arquivos:
        erros.append(f"o arquivo principal '{p.abrir}' não está na lista de arquivos")
    if p.arquivos and p.tipo in ("janela", "console") and not p.abrir.lower().endswith((".py", ".pyw")):
        erros.append("pra rodar com janela/console o arquivo principal precisa ser .py — "
                     "outras linguagens são gravadas, e eu digo como compilar (comando com aprovação)")
    if p.arquivos and p.tipo == "web" and not p.abrir.lower().endswith((".html", ".htm")):
        erros.append("tipo web precisa de um arquivo principal .html")
    return erros


# ======================================================================
#  Pastas, gravação, prévia
# ======================================================================
def _base() -> Path:
    from brain import zenith_settings as cfg
    return Path(cfg.CREATION_DIR) / "programas"


def pasta_do_programa(nome: str, base=None) -> Path:
    return Path(base if base is not None else _base()) / nome


def preview_text(conteudo: str, base=None) -> str:
    """Texto do diálogo de aprovação (mostrado ANTES de qualquer coisa ser gravada ou rodada)."""
    p = interpretar(conteudo)
    erros = validar(p)
    pasta = pasta_do_programa(p.nome or "?", base)
    linhas = [f"[PROGRAMA] {p.nome or '(sem nome)'} — tipo: {p.tipo}",
              f"Pasta: {pasta}",
              f"Arquivo principal: {p.abrir or '?'}", "─" * 40]
    for rel, txt in list(p.arquivos.items())[:12]:
        linhas.append(f"• {rel}  ({len(txt.encode('utf-8'))} bytes, {len(txt.splitlines())} linhas)")
    if len(p.arquivos) > 12:
        linhas.append(f"• ... (+{len(p.arquivos) - 12} arquivos)")
    if erros:
        linhas.append("⚠ Problemas: " + "; ".join(erros))
    principal = p.arquivos.get(p.abrir, "")
    if principal:
        corpo = principal.splitlines()
        linhas += ["─" * 40, f"Começo de {p.abrir}:"] + corpo[:15]
        if len(corpo) > 15:
            linhas.append(f"... (+{len(corpo) - 15} linhas)")
    return "\n".join(linhas)


def gravar(p: ProgramaProposto, base=None) -> tuple:
    """Grava os arquivos. Devolve (pasta, [arquivos com backup]). Arquivo que já existia e mudou vai
    pra _backup/<data-hora>/ antes de ser sobrescrito."""
    pasta = pasta_do_programa(p.nome, base)
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    com_backup = []
    for rel, texto in p.arquivos.items():
        destino = pasta / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            try:
                if destino.read_text(encoding="utf-8", errors="replace") != texto:
                    bk = pasta / "_backup" / carimbo / rel
                    bk.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destino, bk)
                    com_backup.append(rel)
            except OSError:
                pass
        destino.write_text(texto, encoding="utf-8")
    return pasta, com_backup


# ======================================================================
#  Qual Python usar
# ======================================================================
def _python_funciona(cmd: list) -> bool:
    try:
        r = subprocess.run(cmd + ["-c", "import sys; print(sys.version_info[0])"], capture_output=True,
                           text=True, timeout=8)
        return r.returncode == 0 and r.stdout.strip() == "3"
    except Exception:
        return False


def achar_python(configurado: str = "") -> tuple:
    """(prefixo_do_comando, descrição, embutido). Ordem: caminho configurado → o próprio Python (se não
    é .exe) → tools/python → `python`/`py` do PC (sem o falso 'python' da Microsoft Store) → o
    interpretador EMBUTIDO do .exe (limitado). (None, motivo, False) se não achou nada."""
    if configurado and Path(configurado).exists() and _python_funciona([configurado]):
        return [configurado], f"Python configurado ({configurado})", False
    frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        return [sys.executable], "Python do Zenith", False
    try:
        from brain import zenith_settings as cfg
        portatil = Path(cfg.BASE_DIR) / "tools" / "python" / "python.exe"
        if portatil.exists() and _python_funciona([str(portatil)]):
            return [str(portatil)], "Python portátil (tools/python)", False
    except Exception:
        pass
    for nome in ("python", "python3"):
        achado = shutil.which(nome)
        if achado and "windowsapps" not in achado.lower() and _python_funciona([achado]):
            return [achado], f"Python do PC ({achado})", False
    if shutil.which("py") and _python_funciona(["py", "-3"]):
        return ["py", "-3"], "Python do PC (py -3)", False
    return [sys.executable, "--zenith-run-script"], "interpretador EMBUTIDO do Zenith.exe", True


# ======================================================================
#  Executar
# ======================================================================
def _ler_cauda(arquivo: Path, linhas: int = 40, chars: int = 3000) -> str:
    try:
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    ult = "\n".join(texto.strip().splitlines()[-linhas:])
    return ult[-chars:]


# v1.7 (T4) — o programa que ABRE mostrando erro: a janela aparece, o log diz "ERRO! Ajuste o ângulo",
# o processo continua vivo e, no v1.6, isso era reportado como sucesso. Aqui a saída é LIDA.
_PADROES_ERRO = re.compile(
    r"(traceback \(most recent call last\)|\b\w*(?:error|exception)\b|\berro\b|\bfalhou\b|\bfalha ao\b|"
    r"nao foi possivel|não foi possível|\buncaught\b|is not defined|\bundefined\b|syntaxerror|"
    r"indentationerror|\bNaN\b|\bcrash\w*)", re.I)


def parece_erro(saida: str) -> str:
    """Trecho que mostra erro na saída ("" se não há). Pega o caso real do vídeo do usuário:
    o simulador de física abriu com "ERRO! Ajuste o ângulo e a velocidade" e o processo NÃO caiu."""
    texto = str(saida or "")
    for linha in texto.splitlines():
        if _PADROES_ERRO.search(linha):
            limpa = " ".join(linha.split())
            if len(limpa) > 160:
                limpa = limpa[:160] + "…"
            return limpa
    return ""


def dica_de_erro(log: str, embutido: bool = False) -> str:
    dicas = []
    m = re.search(r"No module named '([\w.]+)'", log or "")
    if m:
        lib = m.group(1).split(".")[0]
        if lib == "_tkinter":
            dicas.append("Falta o Tk (tkinter) nesse Python. Use outra biblioteca de janela ou instale um Python completo.")
        else:
            dicas.append(f"Falta a biblioteca '{lib}'. Posso propor `pip install {lib}` (com a sua aprovação).")
            if embutido:
                dicas.append("Estou usando o interpretador EMBUTIDO do Zenith.exe, que só tem as bibliotecas empacotadas. "
                             "Com um Python instalado no PC (ou 'programas_python_exe' nas configurações) o pip funciona.")
    if re.search(r"EOFError|EOF when reading a line", log or ""):
        dicas.append("O programa pediu teclado (input()) — refaça com tipo=\"console\" ou troque o input() por uma janela.")
    if re.search(r"SyntaxError|IndentationError", log or ""):
        dicas.append("Erro de sintaxe/indentação: corrija o trecho apontado e rode de novo.")
    return " ".join(dicas)


def _esperar(proc, segundos: float):
    fim = time.time() + max(0.5, float(segundos))
    while time.time() < fim:
        if proc.poll() is not None:
            return
        time.sleep(0.2)


def executar(p: ProgramaProposto, base=None, python_configurado: str = "", espera_s: float = 6,
             abrir_navegador=None) -> str:
    """Grava e roda. Devolve o texto do resultado (já em linguagem humana)."""
    erros = validar(p)
    if erros:
        return "❌ Não criei o programa: " + "; ".join(erros)
    pasta, backups = gravar(p, base)
    nota_bk = (f"\n(Versões anteriores de {', '.join(backups)} ficaram em {pasta / '_backup'}.)" if backups else "")
    lista = ", ".join(p.arquivos)
    principal = pasta / p.abrir

    if p.tipo == "web":
        try:
            (abrir_navegador or webbrowser.open)(principal.resolve().as_uri())
        except Exception as e:
            return f"✅ Gravei {len(p.arquivos)} arquivo(s) em {pasta}, mas não consegui abrir o navegador ({e}). Abra {principal} na mão.{nota_bk}"
        return (f"🌐 Site '{p.nome}' gravado em {pasta} e aberto no navegador.\nArquivos: {lista}{nota_bk}")

    cmd_py, desc_py, embutido = achar_python(python_configurado)
    if cmd_py is None:
        return f"❌ Não achei um Python pra rodar o programa ({desc_py}). Gravei os arquivos em {pasta}."
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if not embutido:
        for k in ("PYTHONHOME", "PYTHONPATH", "_MEIPASS2"):
            env.pop(k, None)
    log = pasta / "_zenith_log.txt"
    nt = os.name == "nt"
    flags_nt = lambda *nomes: sum(getattr(subprocess, n, 0) for n in nomes)   # noqa: E731

    pararnome = p.nome
    parar(pararnome)                   # se a versão anterior ainda estiver rodando, fecha antes

    try:
        if p.tipo == "console":
            lanc = pasta / "_zenith_rodar.py"
            lanc.write_text(
                "import runpy, sys, traceback\n"
                f"try:\n    runpy.run_path({p.abrir!r}, run_name='__main__')\n"
                "except SystemExit:\n    pass\n"
                "except BaseException:\n    traceback.print_exc()\n"
                "input('\\n[Zenith] O programa terminou. Aperte Enter para fechar...')\n", encoding="utf-8")
            cmd = cmd_py + [str(lanc)]
            proc = subprocess.Popen(cmd, cwd=str(pasta), env=env,
                                    creationflags=flags_nt("CREATE_NEW_CONSOLE") if nt else 0,
                                    **({} if nt else {"start_new_session": True}))
            _PROCS[pararnome] = proc
            return (f"🖥️ Programa '{p.nome}' aberto numa janela de console (pasta {pasta}).\n"
                    f"Arquivos: {lista}\nPython: {desc_py}.{nota_bk}\nPara fechar: /parar_programa {p.nome}")

        cmd = cmd_py + [str(principal)]
        with open(log, "wb") as fh:
            proc = subprocess.Popen(cmd, cwd=str(pasta), env=env, stdin=subprocess.DEVNULL,
                                    stdout=fh, stderr=subprocess.STDOUT,
                                    creationflags=flags_nt("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP") if nt else 0,
                                    **({} if nt else {"start_new_session": True}))
    except Exception as e:
        return f"❌ Não consegui iniciar o programa: {e}\n(Os arquivos estão em {pasta}.)"

    t0 = time.time()
    _esperar(proc, espera_s)
    rc = proc.poll()
    saida = _ler_cauda(log)
    suspeita = parece_erro(saida)
    if rc is None and suspeita:
        # v1.7 (T4): continua vivo, mas a primeira tela mostra erro -> não é sucesso.
        _matar(proc)
        dica = dica_de_erro(saida, embutido)
        return (f"❌ O programa '{p.nome}' abriu mostrando um erro: {suspeita}\n"
                f"Log ({log}):\n{saida}" + (f"\n💡 {dica}" if dica else "") + nota_bk)
    if rc is None:
        _PROCS[pararnome] = proc
        extra = f"\nSaída até agora:\n{saida}" if saida else ""
        return (f"✅ O programa '{p.nome}' está rodando (PID {proc.pid}) — pasta {pasta}.\n"
                f"Arquivos: {lista}\nPython: {desc_py}.{nota_bk}\n"
                f"Se não apareceu janela ou deu erro depois, o log fica em {log}. Para fechar: /parar_programa {p.nome}{extra}")
    dur = time.time() - t0
    if rc != 0:
        dica = dica_de_erro(saida, embutido)
        return (f"❌ O programa '{p.nome}' fechou com erro (código {rc}) depois de {dur:.1f}s.\n"
                f"Log ({log}):\n{saida or '(vazio)'}" + (f"\n💡 {dica}" if dica else "") + nota_bk)
    return (f"✅ O programa '{p.nome}' rodou e terminou sem erro ({dur:.1f}s). Pasta: {pasta}\n"
            f"Saída:\n{saida or '(sem saída de texto)'}{nota_bk}")


# ======================================================================
#  v1.7 (T4) — programa que já sai testado: cria, roda, LÊ a saída e tenta corrigir até 2x
# ======================================================================
def executar_com_correcao(p: "ProgramaProposto", corrigir, base=None, tentativas: int = 2,
                          executar_fn=None, avisar=None) -> str:
    """Roda o programa e, se ele abrir com erro, pede UMA correção à IA (até `tentativas`).

    `corrigir(programa, saida, n)` devolve um ProgramaProposto novo (ou None se não souber).
    Cada correção é mostrada ao usuário (`avisar`) — nada roda escondido, e a aprovação do
    usuário para criar o programa continua valendo para as correções do MESMO programa.
    """
    executar_fn = executar_fn or (lambda prog: executar(prog, base=base))
    avisar = avisar or (lambda _t: None)
    atual, resultado = p, ""
    for n in range(0, max(0, int(tentativas)) + 1):
        resultado = executar_fn(atual)
        texto = str(resultado)
        corpo_saida = texto.split("Saída:", 1)[1] if "Saída:" in texto else ""
        if "❌" not in texto and not (corpo_saida and parece_erro(corpo_saida)):
            if n:
                return (f"✅ Correção {n} funcionou.\n{resultado}\n"
                        f"(Corrigi o programa {n} vez(es) depois de ler a saída.)")
            return resultado
        if n >= max(0, int(tentativas)):
            break
        try:
            novo = corrigir(atual, resultado, n + 1)
        except Exception as e:
            novo = None
            resultado += f"\n(Erro ao montar a correção: {type(e).__name__}: {e})"
        if not novo or not getattr(novo, "arquivos", None):
            return (f"{resultado}\n❌ Não consegui corrigir sozinha desta vez. "
                    "O que ficou errado está acima; se quiser, peça outra correção com mais detalhe.")
        avisar(f"🔧 Correção {n + 1} de {tentativas}: {getattr(novo, 'nome', '')} — vou rodar de novo.")
        atual = novo
    return (f"{resultado}\n❌ Tentei corrigir {tentativas} vez(es) e o erro continuou. "
            "Não vou insistir sozinha; me diga o que ajustar.")


# ======================================================================
#  Parar / listar
# ======================================================================
def _matar(proc) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=8)
        except Exception:
            pass
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except Exception:
        pass


def parar(nome: str = "") -> list:
    """Fecha o programa `nome` (ou todos, se vazio). Devolve os nomes que fechou."""
    alvo = nome_seguro_pasta(nome) if nome else ""
    fechados = []
    for n in list(_PROCS):
        if alvo and n != alvo:
            continue
        proc = _PROCS.pop(n)
        if proc.poll() is None:
            _matar(proc)
            fechados.append(n)
    return fechados


def listar(base=None) -> str:
    pasta = Path(base if base is not None else _base())
    if not pasta.exists():
        return "📁 Nenhum programa criado ainda. Peça: “cria um programa que...”."
    itens = sorted([d for d in pasta.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
    if not itens:
        return "📁 Nenhum programa criado ainda."
    linhas = ["📁 Programas criados (mais recentes primeiro):"]
    for d in itens[:20]:
        proc = _PROCS.get(d.name)
        estado = "▶ rodando" if (proc and proc.poll() is None) else "parado"
        n = sum(1 for f in d.rglob("*") if f.is_file() and "_backup" not in f.parts and not f.name.startswith("_zenith"))
        linhas.append(f"• {d.name} — {n} arquivo(s) — {estado}  ({d})")
    linhas.append("Fechar um que está rodando: /parar_programa <nome>")
    return "\n".join(linhas)
