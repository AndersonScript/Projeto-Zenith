# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_content_safety.py — Camada de proteção determinística.
#
#  Por quê isso existe separado do modelo de IA: pedir pro modelo
#  "seguir uma regra de personalidade" é uma defesa fraca — modelos
#  podem ser convencidos, confundidos ou simplesmente errar. Isso aqui
#  roda NO CÓDIGO, antes de mandar pro modelo E depois de receber a
#  resposta dele. Mesma filosofia do DeterministicGuard (Stranger
#  Danger) que já existe em zenith_gatekeeper.py.
#
#  REGRA DURA (sem exceção, sem "avisar e deixar passar"): qualquer
#  conteúdo sexual/exploração envolvendo indicação de menor de idade é
#  bloqueado direto, incidente é registrado, e o sistema entra em
#  bloqueio (igual ao Stranger Danger) — não é "pedir confirmação",
#  é recusar e travar.
# ============================================================

import json
import re
from datetime import datetime

from brain.zenith_settings import CONFIG_DIR

INCIDENT_LOG = CONFIG_DIR / "security_incidents.json"

# ---------- Indicadores de idade / menor ----------
_MINOR_TERMS = [
    r"\bcrian[çc]a\b", r"\binfantil\b", r"\bmenor(es)?\s+de\s+idade\b",
    r"\b(?:[5-9]|1[0-7])\s*anos\b",  # "9 anos" .. "17 anos"
    r"\bkid\b", r"\bchild(ren)?\b", r"\bminor\b", r"\bunderage\b",
    r"\bloli\b", r"\bshota\b", r"\bpre[- ]?teen\b", r"\bstudent\b.*\bschool\b.*\byoung\b",
]

# ---------- Indicadores de conteúdo sexual/exploração ----------
_SEXUAL_TERMS = [
    r"\bsexual\b", r"\bsexo\b", r"\bnude?z?\b", r"\bnu[a]?\b", r"\bpelad[ao]\b",
    r"\bpornograf", r"\berotic", r"\bmasturba", r"\bestupr", r"\babus[eo]\s+sexual\b",
    r"\bsex\b", r"\bnaked\b", r"\bnsfw\b", r"\bfetiche\b", r"\bfetish\b",
]

_MINOR_RE = re.compile("|".join(_MINOR_TERMS), re.IGNORECASE)
_SEXUAL_RE = re.compile("|".join(_SEXUAL_TERMS), re.IGNORECASE)

# Outras categorias graves — bloqueiam, mas sem o mesmo "trava tudo"
# automático que a combinação sexual+menor dispara.
_SEVERE_OTHER = [
    r"\bcomo\s+fazer\s+uma\s+bomba\b", r"\bhow\s+to\s+make\s+a\s+bomb\b",
    r"\barma\s+qu[íi]mica\b", r"\bchemical\s+weapon\b",
]
_SEVERE_OTHER_RE = re.compile("|".join(_SEVERE_OTHER), re.IGNORECASE)


def check(text: str) -> dict:
    """Retorna {"severe": bool, "category": str, "reason": str} para o
    texto (mensagem do usuário OU resposta da IA — os dois são checados).
    Roda em cima da mesma janela de texto, sem depender de contexto de
    conversas anteriores (então não some se a pessoa quebrar em partes
    numa única mensagem)."""
    if not text:
        return {"severe": False}

    minor_hit = _MINOR_RE.search(text)
    sexual_hit = _SEXUAL_RE.search(text)

    if minor_hit and sexual_hit:
        return {"severe": True, "category": "sexual_minor",
                "reason": "Conteúdo sexual combinado com indicação de menor de idade."}

    if _SEVERE_OTHER_RE.search(text):
        return {"severe": True, "category": "weapon_instructions",
                "reason": "Pedido de instruções pra criação de arma/explosivo."}

    return {"severe": False}


def log_incident(category: str, reason: str, snippet: str, source: str):
    """Guarda só o suficiente pra auditoria (categoria, motivo, um
    trecho CURTO, não o texto inteiro) — o objetivo é você conseguir
    checar se o app tá sendo mal-usado, não guardar uma cópia integral
    de conteúdo grave em disco sem necessidade."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    incidents = []
    if INCIDENT_LOG.exists():
        try:
            incidents = json.loads(INCIDENT_LOG.read_text(encoding="utf-8"))
        except Exception:
            incidents = []
    incidents.append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "category": category,
        "reason": reason,
        "source": source,  # "user_message" | "ai_response"
        "snippet": (snippet or "")[:80],
    })
    incidents = incidents[-300:]
    INCIDENT_LOG.write_text(json.dumps(incidents, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- VRM: checagem fraca por nome de arquivo ----------
# IMPORTANTE ser honesto sobre o limite disto: não existe como um
# programa "olhar" o modelo 3D e saber se ele representa uma criança —
# isso exigiria análise visual/IA de verdade, que não temos aqui. Isso
# aqui pega só o caso óbvio (nome de arquivo problemático) — é uma
# camada a mais, não uma garantia.
_VRM_FILENAME_BLOCK = re.compile(
    r"\b(loli|shota|child|kid|infantil|crianca|criança)\b", re.IGNORECASE)


def vrm_filename_suspicious(path: str) -> bool:
    return bool(path) and bool(_VRM_FILENAME_BLOCK.search(path))
