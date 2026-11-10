"""
Zenith — HABILIDADES: a Zenith se estende sozinha, sem mexer no próprio código (v23).

Pedido do Anderson: "quero que seja maleável, que ela até se auto-modifique". Mexer no núcleo do Zenith
enquanto ele roda é a forma mais fácil de quebrar tudo (e de abrir brecha de segurança). O caminho seguro:

  * Uma HABILIDADE é um pequeno programa Python guardado em `skills/<nome>.py` com uma função
    `rodar(args: str) -> str`. Exemplos: controlar o pistão pelo ESP32, ler um sensor, montar o placar de um
    quiz, converter uma planilha, consultar uma API.
  * Ela CRIA a habilidade com `<criar_habilidade nome="x" descricao="o que faz"> código </criar_habilidade>`.
    Nada é gravado antes de VOCÊ ver o código inteiro (e o que ele toca: arquivos, rede, serial...) e aprovar.
  * Ela USA com `<usar_habilidade nome="x">argumentos</usar_habilidade>` — aprovação de novo, a cada uso,
    a não ser que VOCÊ marque aquela habilidade como confiável (`/habilidade confiar x`; vale só pra ela,
    dá pra desfazer com `/habilidade desconfiar x`, e a lista negra do Gatekeeper continua valendo).
  * A lista das habilidades (nome + o que faz) vai no prompt dela, então ela sabe o que já sabe fazer.

Pilar 1: criar e usar passam pela aprovação; o código é conferido na lista negra do Gatekeeper ao criar E ao
rodar (o arquivo pode ter sido editado no meio tempo). Este módulo só lê/escreve texto; quem roda é o
executor (processo à parte, com limite de tempo).
"""
from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path

from brain.zenith_settings import BASE_DIR

SKILLS_DIR = BASE_DIR / "skills"
NOME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MAX_CODIGO = 24000
MAX_HABILIDADES = 40
MAX_DESC = 200

_RE_CRIAR = re.compile(r"<criar_habilidade\b([^>]*)>(.*?)</criar_habilidade>", re.S | re.I)
_RE_USAR = re.compile(r"<usar_habilidade\b([^>]*)>(.*?)</usar_habilidade>", re.S | re.I)
_RE_ATTR = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')

# o que mostrar de aviso na aprovação (nome do import/chamada -> rótulo humano)
_SENSIVEL = {
    "requests": "acessa a internet", "urllib": "acessa a internet", "socket": "acessa a rede", "http": "acessa a internet",
    "serial": "fala com portas seriais/Arduino/ESP32", "bluetooth": "usa Bluetooth",
    "subprocess": "roda outros programas", "os.system": "roda comandos do sistema", "os.popen": "roda comandos do sistema",
    "shutil": "copia/move/apaga arquivos", "os.remove": "apaga arquivos", "os.unlink": "apaga arquivos",
    "os.rmdir": "apaga pastas", "pathlib": "mexe em arquivos", "open": "lê/escreve arquivos",
    "ctypes": "usa chamadas de baixo nível do Windows", "winreg": "mexe no registro do Windows",
    "pyautogui": "controla mouse/teclado", "keyboard": "controla/lê o teclado", "pynput": "controla/lê mouse e teclado",
    "smtplib": "envia e-mail", "ftplib": "usa FTP", "eval": "executa texto como código", "exec": "executa texto como código",
    "__import__": "importa módulos dinamicamente", "pickle": "carrega objetos serializados (risco)",
}


class ErroHabilidade(ValueError):
    pass


# ---------------------------------------------------------------- interpretação das etiquetas
def _atributos(texto: str) -> dict:
    return {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3)) for m in _RE_ATTR.finditer(texto or "")}


def _limpar_codigo(c: str) -> str:
    c = (c or "").strip("\n")
    m = re.match(r"^\s*```[a-zA-Z]*\n(.*?)\n?```\s*$", c, re.S)       # tira ``` de dentro da etiqueta
    return (m.group(1) if m else c).strip("\n")


def parse_criar(conteudo: str) -> dict:
    """{'nome','descricao','codigo'} da etiqueta <criar_habilidade ...>...</criar_habilidade>. Levanta ErroHabilidade."""
    m = _RE_CRIAR.search(conteudo or "")
    if not m:
        raise ErroHabilidade("etiqueta <criar_habilidade nome=\"...\" descricao=\"...\"> ... </criar_habilidade> incompleta")
    at = _atributos(m.group(1))
    nome = (at.get("nome") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not NOME_RE.match(nome):
        raise ErroHabilidade(f"nome '{nome}' inválido — use letras minúsculas, números e _ (2 a 32 caracteres, começando por letra)")
    desc = " ".join((at.get("descricao") or at.get("desc") or "").split())[:MAX_DESC]
    if not desc:
        raise ErroHabilidade("falta descricao=\"...\" (uma frase dizendo o que a habilidade faz)")
    codigo = _limpar_codigo(m.group(2))
    if not codigo.strip():
        raise ErroHabilidade("o código da habilidade veio vazio")
    if len(codigo) > MAX_CODIGO:
        raise ErroHabilidade(f"código grande demais ({len(codigo)} caracteres; máximo {MAX_CODIGO}) — divida em habilidades menores")
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as e:
        raise ErroHabilidade(f"erro de sintaxe no código (linha {e.lineno}): {e.msg}")
    tem_rodar = any(isinstance(n, ast.FunctionDef) and n.name == "rodar" for n in arvore.body)
    if not tem_rodar:
        raise ErroHabilidade("o código precisa definir `def rodar(args: str = \"\") -> str:` (é o que o Zenith chama)")
    return {"nome": nome, "descricao": desc, "codigo": codigo}


def parse_usar(conteudo: str) -> tuple:
    """(nome, args) da etiqueta <usar_habilidade nome="x">args</usar_habilidade>."""
    m = _RE_USAR.search(conteudo or "")
    if not m:
        raise ErroHabilidade("etiqueta <usar_habilidade nome=\"...\">argumentos</usar_habilidade> incompleta")
    nome = (_atributos(m.group(1)).get("nome") or "").strip().lower()
    if not NOME_RE.match(nome):
        raise ErroHabilidade(f"nome '{nome}' inválido")
    return nome, m.group(2).strip()


# ---------------------------------------------------------------- análise do que o código toca
def analisar_codigo(codigo: str) -> list:
    """Lista legível do que o código FAZ de sensível (pra mostrar na janela de aprovação). Não é um sandbox:
    é transparência — quem decide é a pessoa."""
    achados = []
    try:
        arvore = ast.parse(codigo)
    except SyntaxError:
        return ["código com erro de sintaxe"]
    for n in ast.walk(arvore):
        nomes = []
        if isinstance(n, ast.Import):
            nomes = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            nomes = [n.module]
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                nomes = [f.id]
            elif isinstance(f, ast.Attribute):
                partes = []
                while isinstance(f, ast.Attribute):
                    partes.append(f.attr)
                    f = f.value
                if isinstance(f, ast.Name):
                    partes.append(f.id)
                nomes = [".".join(reversed(partes))]
        for nome in nomes:
            for chave, rotulo in _SENSIVEL.items():
                if nome == chave or nome.startswith(chave + ".") or nome.split(".")[0] == chave:
                    if rotulo not in achados:
                        achados.append(rotulo)
    return achados


# ---------------------------------------------------------------- arquivos
def _arquivo(nome: str) -> Path:
    return SKILLS_DIR / f"{nome}.py"


def existe(nome: str) -> bool:
    return bool(NOME_RE.match(nome or "")) and _arquivo(nome).is_file()


def _cabecalho(nome: str, desc: str) -> str:
    d = desc.replace('"""', "'''")
    return f'"""{d}\n\n[Habilidade "{nome}" criada pela Zenith em {time.strftime("%Y-%m-%d %H:%M")}]\n"""\n'


def descricao_de(nome: str) -> str:
    try:
        arvore = ast.parse(_arquivo(nome).read_text(encoding="utf-8"))
        doc = ast.get_docstring(arvore) or ""
        return " ".join(doc.split("\n\n")[0].split())[:MAX_DESC]
    except Exception:
        return ""


def ler_codigo(nome: str) -> str:
    if not existe(nome):
        raise ErroHabilidade(f"não existe a habilidade '{nome}' (veja /habilidades)")
    return _arquivo(nome).read_text(encoding="utf-8")


def listar() -> list:
    if not SKILLS_DIR.is_dir():
        return []
    itens = []
    for f in sorted(SKILLS_DIR.glob("*.py")):
        nome = f.stem
        if NOME_RE.match(nome):
            itens.append({"nome": nome, "descricao": descricao_de(nome),
                          "linhas": len(f.read_text(encoding="utf-8", errors="replace").splitlines())})
    return itens


def salvar(conteudo: str) -> str:
    """Grava a habilidade (chamado SÓ depois da aprovação). Devolve mensagem pra mostrar."""
    h = parse_criar(conteudo)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    nova = not existe(h["nome"])
    if nova and len(listar()) >= MAX_HABILIDADES:
        return f"❌ Já existem {MAX_HABILIDADES} habilidades (o máximo). Apague alguma com /habilidade apagar <nome>."
    _arquivo(h["nome"]).write_text(_cabecalho(h["nome"], h["descricao"]) + "\n" + h["codigo"] + "\n", encoding="utf-8")
    return (f"🧩 Habilidade '{h['nome']}' {'criada' if nova else 'atualizada'} em skills/{h['nome']}.py. "
            f"Agora eu sei: {h['descricao']}")


def apagar(nome: str) -> bool:
    if not existe(nome):
        return False
    _arquivo(nome).unlink()
    return True


# ---------------------------------------------------------------- previews (o que a pessoa vê ao aprovar)
def preview_criar(conteudo: str) -> str:
    try:
        h = parse_criar(conteudo)
    except ErroHabilidade as e:
        return f"[CRIAR HABILIDADE] ⚠ etiqueta com problema: {e}"
    linhas = h["codigo"].splitlines()
    sens = analisar_codigo(h["codigo"])
    corpo = "\n".join(linhas[:40]) + (f"\n... (+{len(linhas) - 40} linhas — o arquivo completo vai pra skills/{h['nome']}.py)" if len(linhas) > 40 else "")
    aviso = ("⚠ Esta habilidade: " + "; ".join(sens) + ".") if sens else "Nada sensível detectado (só cálculo/texto)."
    sub = "  ⚠ JÁ EXISTE uma habilidade com esse nome — esta aprovação SUBSTITUI o código dela." if existe(h["nome"]) else ""
    return (f"[CRIAR HABILIDADE] {h['nome']} — {h['descricao']}{sub}\n{aviso}\n"
            f"Ela só será gravada se você aprovar; para USÁ-LA haverá outra aprovação.\n{'─' * 40}\n{corpo}")


def preview_usar(conteudo: str) -> str:
    try:
        nome, args = parse_usar(conteudo)
        codigo = ler_codigo(nome)
    except ErroHabilidade as e:
        return f"[USAR HABILIDADE] ⚠ {e}"
    sens = analisar_codigo(codigo)
    linhas = codigo.splitlines()
    corpo = "\n".join(linhas[:30]) + (f"\n... (+{len(linhas) - 30} linhas)" if len(linhas) > 30 else "")
    aviso = ("⚠ Ela: " + "; ".join(sens) + ".") if sens else "Nada sensível detectado."
    return (f"[USAR HABILIDADE] {nome} — {descricao_de(nome)}\nArgumentos: {args or '(nenhum)'}\n{aviso}\n{'─' * 40}\n{corpo}")


# ---------------------------------------------------------------- execução (quem roda é o executor, em processo à parte)
def montar_wrapper(nome: str, args: str) -> str:
    """Script que carrega skills/<nome>.py e chama rodar(args). Roda via ZenithExecutor.run_python."""
    caminho = str(_arquivo(nome))
    return (
        "import importlib.util, sys, traceback\n"
        f"_caminho = {caminho!r}\n"
        f"_args = {args!r}\n"
        "spec = importlib.util.spec_from_file_location('habilidade_' + " + repr(nome) + ", _caminho)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "try:\n"
        "    spec.loader.exec_module(mod)\n"
        "    res = mod.rodar(_args)\n"
        "    print(res if res is not None else '(a habilidade terminou sem devolver texto)')\n"
        "except SystemExit:\n"
        "    raise\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )


# ---------------------------------------------------------------- confiança e prompt
def confiaveis(settings) -> list:
    try:
        v = settings.get("habilidades_confiaveis", []) or []
        return [str(x) for x in v]
    except Exception:
        return []


def eh_confiavel(settings, nome: str) -> bool:
    return nome in confiaveis(settings)


def bloco_prompt(settings=None) -> str:
    """Trecho do prompt do sistema: o que ela já sabe fazer (e como criar mais). Vazio se desligado."""
    try:
        if settings is not None and not settings.get("habilidades_ativas", True):
            return ""
    except Exception:
        pass
    itens = listar()
    cab = ("\n\nHABILIDADES (você se estende sozinha, sem mexer no seu código):\n"
           "- Criar: <criar_habilidade nome=\"nome_curto\" descricao=\"o que faz, numa frase\"> código Python com "
           "`def rodar(args: str = \"\") -> str:` que devolve um texto </criar_habilidade> — o usuário vê o código inteiro "
           "e aprova antes de gravar. Use quando faltar uma ferramenta (controlar o ESP32/pistão, ler um sensor, "
           "montar um placar, chamar uma API...) e a tarefa for se repetir.\n"
           "- Usar: <usar_habilidade nome=\"nome_curto\">argumentos</usar_habilidade> (também pede aprovação, salvo se "
           "o usuário marcou a habilidade como confiável).\n")
    if not itens:
        return cab + "Você ainda não criou nenhuma habilidade."
    linhas = [f"  • {i['nome']} — {i['descricao'] or '(sem descrição)'}" for i in itens[:MAX_HABILIDADES]]
    return cab + "Habilidades que você JÁ tem:\n" + "\n".join(linhas)


def resumo_lista(settings=None) -> str:
    itens = listar()
    if not itens:
        return ("🧩 Nenhuma habilidade ainda. Peça algo que ela ainda não faz (\"controla o pistão pelo ESP32\") e ela "
                "pode CRIAR uma — você vê o código e aprova antes.")
    conf = set(confiaveis(settings)) if settings is not None else set()
    linhas = [f"• {i['nome']} ({i['linhas']} linhas){' ✔ confiável' if i['nome'] in conf else ''} — {i['descricao'] or '(sem descrição)'}"
              for i in itens]
    return ("🧩 Habilidades da Zenith (pasta skills/):\n" + "\n".join(linhas) +
            "\nVer o código: /habilidade ver <nome> · Apagar: /habilidade apagar <nome> · "
            "Rodar sem perguntar: /habilidade confiar <nome> (desfaz com desconfiar)")
