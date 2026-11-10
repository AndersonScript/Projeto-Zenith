"""
Zenith — Log de ações aprovadas (Pilar 1: consentimento explícito).

Cada ação sensível que a Zenith propõe (rodar Python, terminal, serial...)
passa por aprovação humana. Este módulo guarda um histórico simples e
LEGÍVEL disso: o que foi proposto, se você aprovou / negou / a segurança
vetou, e como terminou. Serve de "recibo" — reforça a confiança no Pilar 1
e, no dia em que o Zenith virar software de uso diário, é a base de
qualquer auditoria ("o que esse agente fez no meu computador?").

Formato: uma linha JSON por evento (JSONL) em config/zenith_acoes_log.jsonl.
- Nunca guarda o conteúdo completo de um script — só um trecho curto, com
  chaves/senhas óbvias mascaradas.
- Gira sozinho: passou de ~2 MB, o arquivo vira .1.jsonl (o antigo é
  descartado) e recomeça.
- NUNCA levanta exceção pra quem chamou: log é conveniência, não pode
  travar a conversa nem impedir uma ação já aprovada.
"""
import datetime
import json
import re
import threading
from pathlib import Path

_MAX_BYTES = 2_000_000
_MAX_TRECHO = 400
_lock = threading.Lock()

# Padrões óbvios de segredo. Não é à prova de tudo (nada é) — é uma rede
# de segurança pra um script que tenha uma chave colada dentro não vazar
# pro arquivo de log.
_SEGREDOS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "[chave oculta]"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[chave oculta]"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "[chave oculta]"),
    (re.compile(r"(?i)\b(api[_\- ]?key|token|secret|senha|password|passwd)\b(\s*[=:]\s*)(\S+)"),
     r"\1\2[oculto]"),
]


def _caminho_padrao() -> Path:
    from brain.zenith_settings import CONFIG_DIR
    return Path(CONFIG_DIR) / "zenith_acoes_log.jsonl"


def mascarar_segredos(texto: str) -> str:
    for padrao, subst in _SEGREDOS:
        texto = padrao.sub(subst, texto)
    return texto


def _trecho(texto: str, limite: int = _MAX_TRECHO) -> str:
    texto = mascarar_segredos(str(texto or "").strip())
    texto = re.sub(r"\s+", " ", texto)
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


def registrar(tipo: str, descricao: str, decisao: str, detalhe: str = "",
              conversa: str = "", caminho=None) -> bool:
    """decisao: 'aprovada' | 'negada' | 'vetada' | 'microfone'.
    Devolve True se gravou, False se algo falhou (nunca levanta)."""
    try:
        p = Path(caminho) if caminho else _caminho_padrao()
        evento = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "tipo": str(tipo or "?"),
            "descricao": _trecho(descricao, 200),
            "decisao": decisao,
            "detalhe": _trecho(detalhe),
            "conversa": str(conversa or ""),
        }
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() and p.stat().st_size > _MAX_BYTES:
                antigo = p.with_name(p.stem + ".1" + p.suffix)
                if antigo.exists():
                    antigo.unlink()
                p.rename(antigo)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"[Zenith/Log de ações] não consegui gravar: {e}")
        return False


def recentes(n: int = 10, caminho=None) -> list:
    """Últimos n eventos (do mais antigo pro mais novo). Linhas
    corrompidas são ignoradas em vez de derrubar a leitura."""
    try:
        p = Path(caminho) if caminho else _caminho_padrao()
        if not p.exists():
            return []
        eventos = []
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    eventos.append(json.loads(linha))
                except ValueError:
                    continue
        return eventos[-max(1, int(n)):]
    except Exception:
        return []


_ICONE = {"aprovada": "✅", "negada": "🚫", "vetada": "⛔", "microfone": "🎙️"}


def formatar_recentes(n: int = 10, caminho=None) -> str:
    eventos = recentes(n, caminho)
    if not eventos:
        return "📋 Ainda não há ações registradas — nada rodou com a sua aprovação até agora."
    linhas = [f"📋 Últimas {len(eventos)} ações (mais recente por último):"]
    for e in eventos:
        quando = str(e.get("ts", ""))[:19].replace("T", " ")
        icone = _ICONE.get(e.get("decisao"), "•")
        linha = f"{icone} {quando} · {e.get('tipo', '?')} · {e.get('decisao', '?')} — {e.get('descricao', '')}"
        if e.get("detalhe"):
            linha += f"\n     ↳ {e['detalhe']}"
        linhas.append(linha)
    return "\n".join(linhas)


def exportar_markdown(destino, caminho=None) -> int:
    """Grava o log inteiro (até 5000 eventos) como Markdown. Devolve quantos."""
    eventos = recentes(5000, caminho)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    linhas = ["# Zenith — histórico de ações aprovadas", ""]
    dia = None
    for e in eventos:
        ts = str(e.get("ts", ""))
        d, _, h = ts.partition("T")
        if d != dia:
            dia = d
            linhas += ["", f"## {d}", ""]
        icone = _ICONE.get(e.get("decisao"), "•")
        linhas.append(f"- {icone} **{h[:8]}** · `{e.get('tipo', '?')}` · {e.get('decisao', '?')} — {e.get('descricao', '')}")
        if e.get("detalhe"):
            linhas.append(f"    - {e['detalhe']}")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return len(eventos)
