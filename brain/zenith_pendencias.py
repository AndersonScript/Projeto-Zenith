"""
Zenith — PENDÊNCIAS e PROJETO ATIVO: ela não esquece o que você pediu, nem o roteiro (v25).

Problema real (relato do Anderson, vídeo de divulgação da escola): "ela ficou pedindo pra eu deixar pra depois uma imagem que
pedi a 10 conversas antes, e eu queria que ela seguisse o roteiro". Cada conversa começa "do zero" e nada guardava
"isto foi pedido e ainda NÃO foi entregue". Agora:

  * PENDÊNCIAS (config/pendencias.json): o que você pediu e ainda falta entregar. Ela anota com <pendencia>texto</pendencia>,
    dá baixa com <concluir>número</concluir>; as ABERTAS vão no prompt de TODA mensagem, em TODA conversa.
    Você vê/edita com /pendencias, /pendencia add|feito|apagar.
  * PROJETO ATIVO (config/projetos/<nome>.md): o roteiro/briefing de um trabalho (ex.: "etec"). O ativo vai no prompt de toda
    mensagem — ela SEGUE o roteiro. /projeto etec · /projeto novo etec · /projeto texto <roteiro> · /projeto ver · /projeto desligar.
    Ela pode acrescentar ao projeto ativo com <projeto>texto</projeto> (só se houver projeto ativo; passa pelo filtro de texto suspeito).

Tudo é texto local; nada executa. Arquivos ficam em config/ (que nunca vai em pacote de distribuição).
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

from brain.zenith_settings import CONFIG_DIR

ARQUIVO = CONFIG_DIR / "pendencias.json"
PASTA_PROJETOS = CONFIG_DIR / "projetos"
MAX_ABERTAS = 40
MAX_TEXTO = 300
MAX_PROJETO_CHARS = 12000          # tamanho do arquivo do projeto
MAX_PROJETO_PROMPT = 6000          # quanto dele vai por mensagem
_RE_PEND = re.compile(r"<pendencia>(.*?)</pendencia>", re.S | re.I)
_RE_CONC = re.compile(r"<concluir>(.*?)</concluir>", re.S | re.I)
_RE_PROJ = re.compile(r"<projeto>(.*?)</projeto>", re.S | re.I)
TAGS = (_RE_PEND, _RE_CONC, _RE_PROJ)


def _norma(t: str) -> str:
    return " ".join((t or "").lower().split())


def _ler() -> dict:
    try:
        d = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        d.setdefault("abertas", [])
        d.setdefault("feitas", [])
        d.setdefault("proximo_id", 1)
        return d
    except Exception:
        return {"abertas": [], "feitas": [], "proximo_id": 1}


def _gravar(d: dict):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- pendências
def listar() -> list:
    return list(_ler()["abertas"])


def adicionar(texto: str, origem: str = "conversa"):
    """Devolve a pendência criada, a já existente (duplicada) ou None (vazia / lista cheia)."""
    texto = " ".join((texto or "").split())[:MAX_TEXTO]
    if not texto:
        return None
    d = _ler()
    for p in d["abertas"]:
        if _norma(p["texto"]) == _norma(texto):
            return p
    if len(d["abertas"]) >= MAX_ABERTAS:
        return None
    p = {"id": d["proximo_id"], "texto": texto, "criada": time.strftime("%Y-%m-%d"), "origem": origem}
    d["proximo_id"] += 1
    d["abertas"].append(p)
    _gravar(d)
    return p


def concluir(ref) -> bool:
    """`ref` = número da pendência ou um pedaço do texto."""
    d = _ler()
    alvo = None
    ref = str(ref).strip()
    if ref.isdigit():
        alvo = next((p for p in d["abertas"] if p["id"] == int(ref)), None)
    elif ref:
        alvo = next((p for p in d["abertas"] if _norma(ref) in _norma(p["texto"])), None)
    if alvo is None:
        return False
    d["abertas"].remove(alvo)
    alvo["concluida"] = time.strftime("%Y-%m-%d")
    d["feitas"] = (d["feitas"] + [alvo])[-60:]
    _gravar(d)
    return True


def apagar(ref) -> bool:
    d = _ler()
    ref = str(ref).strip()
    alvo = next((p for p in d["abertas"] if str(p["id"]) == ref), None)
    if alvo is None:
        return False
    d["abertas"].remove(alvo)
    _gravar(d)
    return True


def resumo_lista() -> str:
    ab = listar()
    if not ab:
        return "📌 Nenhuma pendência aberta. (Ela anota sozinha o que você pede e ainda não foi entregue; ou: /pendencia add <texto>)"
    return ("📌 Pendências abertas (ela vê esta lista em TODA conversa):\n" +
            "\n".join(f"{p['id']}. {p['texto']}  ({p['criada']})" for p in ab) +
            "\nDar baixa: /pendencia feito <número> · Apagar: /pendencia apagar <número> · Nova: /pendencia add <texto>")


# ---------------------------------------------------------------- projeto ativo
def nome_valido(nome: str) -> str:
    n = unicodedata.normalize("NFKD", (nome or "").strip().lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9_-]+", "-", n).strip("-")
    return n[:40] if len(n) >= 2 else ""


def _arq(nome: str) -> Path:
    return PASTA_PROJETOS / f"{nome}.md"


def projetos() -> list:
    return sorted(p.stem for p in PASTA_PROJETOS.glob("*.md")) if PASTA_PROJETOS.is_dir() else []


def existe(nome: str) -> bool:
    n = nome_valido(nome)
    return bool(n) and _arq(n).is_file()


def criar(nome: str, texto: str = "") -> str:
    n = nome_valido(nome)
    if not n:
        raise ValueError("nome inválido (use letras/números, 2 a 40 caracteres)")
    PASTA_PROJETOS.mkdir(parents=True, exist_ok=True)
    if not _arq(n).exists():
        _arq(n).write_text((texto or "").strip()[:MAX_PROJETO_CHARS] + "\n", encoding="utf-8")
    elif texto:
        acrescentar(n, texto)
    return n


def ler_projeto(nome: str) -> str:
    n = nome_valido(nome)
    try:
        return _arq(n).read_text(encoding="utf-8") if n else ""
    except OSError:
        return ""


def acrescentar(nome: str, texto: str) -> bool:
    """Junta ao FIM do projeto (nunca sobrescreve). Recusa texto com cara de instrução maliciosa."""
    from brain.zenith_validator import scan_persona_text
    n = nome_valido(nome)
    texto = (texto or "").strip()
    if not n or not _arq(n).is_file() or not texto or scan_persona_text(texto):
        return False
    atual = _arq(n).read_text(encoding="utf-8")
    if len(atual) + len(texto) > MAX_PROJETO_CHARS:
        return False
    _arq(n).write_text(atual.rstrip() + "\n\n" + texto + "\n", encoding="utf-8")
    return True


def apagar_projeto(nome: str) -> bool:
    n = nome_valido(nome)
    if n and _arq(n).is_file():
        _arq(n).unlink()
        return True
    return False


# ---------------------------------------------------------------- prompt
def bloco_prompt(user: str, projeto_ativo: str = "") -> str:
    partes = []
    ab = listar()
    if ab:
        partes.append(
            f"\n\nPENDÊNCIAS ABERTAS (coisas que {user} te pediu e AINDA NÃO foram entregues — vale em TODA conversa). "
            "Não adie nem peça pra deixar pra depois: se ele não pediu outra coisa, FAÇA agora a mais antiga que der e "
            "dê baixa com <concluir>número</concluir>. Pedido grande: entregue a 1ª parte e anote o resto com "
            "<pendencia>texto</pendencia>.\n" + "\n".join(f"{p['id']}. {p['texto']}" for p in ab))
    if projeto_ativo and existe(projeto_ativo):
        corpo = ler_projeto(projeto_ativo).strip()[:MAX_PROJETO_PROMPT]
        if corpo:
            partes.append(
                f"\n\nPROJETO ATIVO: \"{nome_valido(projeto_ativo)}\" — este é o roteiro/briefing que {user} definiu. "
                "SIGA-O à risca (ordem, tom, tempos, nomes); se algo nele estiver ambíguo, escolha o mais provável e diga a "
                "suposição. Para anotar uma decisão nova no projeto: <projeto>texto curto</projeto>.\n---\n" + corpo + "\n---")
    return "".join(partes)


def processar_tags(resposta: str, projeto_ativo: str = "") -> dict:
    """Aplica <pendencia>, <concluir> e <projeto> de uma resposta. Devolve contagens (pra log/teste)."""
    r = {"adicionadas": 0, "concluidas": 0, "projeto": 0}
    for t in _RE_PEND.findall(resposta or ""):
        if adicionar(t) is not None:
            r["adicionadas"] += 1
    for t in _RE_CONC.findall(resposta or ""):
        if concluir(t.strip()):
            r["concluidas"] += 1
    if projeto_ativo and existe(projeto_ativo):
        for t in _RE_PROJ.findall(resposta or ""):
            if acrescentar(projeto_ativo, t):
                r["projeto"] += 1
    return r


def remover_tags(texto: str) -> str:
    for rx in TAGS:
        texto = rx.sub("", texto or "")
    return texto
