"""
Zenith — Exportar conversa em Markdown (/exportar_conversa).

Segue o mesmo padrão de /exportar_notas e /exportar_log: arquivo em
creations/exports/. Chaves e senhas óbvias são mascaradas (a conversa pode ser
compartilhada). PDF ainda não — Markdown abre em qualquer editor e dá pra
converter.
"""
import re
from pathlib import Path

from brain import zenith_actionlog as _actionlog


def _slug(titulo: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", str(titulo or "conversa"), flags=re.UNICODE).strip("_")
    return (s or "conversa")[:40]


def nome_sugerido(conv: dict, carimbo: str) -> str:
    return f"zenith_conversa_{_slug(conv.get('title'))}_{carimbo}.md"


def conversa_para_markdown(conv: dict, persona: str = "Zenith", usuario: str = "Você") -> str:
    titulo = str(conv.get("title") or "Conversa")
    linhas = [f"# {titulo}", ""]
    ultimo_dia = None
    for m in conv.get("messages", []) or []:
        texto = _actionlog.mascarar_segredos(str(m.get("text", "")).strip())
        if not texto:
            continue
        ts = str(m.get("ts", ""))
        dia, _, hora = ts.partition("T")
        if dia and dia != ultimo_dia:
            ultimo_dia = dia
            linhas += [f"## {dia}", ""]
        quem = usuario if m.get("sender") == "user" else persona
        marca = f"**{quem}**" + (f" · {hora[:5]}" if hora else "")
        linhas += [marca, "", *(("> " + l) if l.strip() else ">" for l in texto.splitlines()), ""]
    return "\n".join(linhas).rstrip() + "\n"


def exportar_conversa(conv: dict, destino, persona: str = "Zenith", usuario: str = "Você") -> int:
    """Grava o Markdown em `destino`. Devolve quantas mensagens foram exportadas."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conversa_para_markdown(conv, persona, usuario), encoding="utf-8")
    return sum(1 for m in conv.get("messages", []) or [] if str(m.get("text", "")).strip())
