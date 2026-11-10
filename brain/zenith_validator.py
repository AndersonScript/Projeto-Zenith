# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_validator.py — Camada de checagem ANTES da personalização.
#
#  Tudo que o usuário pode customizar livremente (texto de
#  personalidade, pilares extras, caminho do VRM, papel de parede do
#  chat, modelo de voz RVC) passa por aqui primeiro. Duas coisas
#  diferentes são checadas:
#
#  1) TEXTO — tentativas de "jailbreak"/injeção de prompt escondidas
#     dentro da descrição de personalidade (ex: "ignore suas regras
#     de segurança"). Isso é checado NO CÓDIGO (determinístico), não
#     só confiando que o modelo de IA vai recusar sozinho — mesma
#     lógica do Stranger Danger determinístico do zenith_gatekeeper.
#
#  2) CAMINHOS DE ARQUIVO — extensão errada/perigosa ou tentativa de
#     sair da pasta do projeto (path traversal), antes de aceitar um
#     caminho de VRM, imagem de fundo ou modelo de voz.
# ============================================================

import re
from pathlib import Path

# ---------- 1) Texto de personalização ----------
# Frases (PT/EN) que tipicamente aparecem em tentativas de desativar
# guardrails via "personalidade". Não é uma lista exaustiva — é uma
# primeira barreira determinística, não substitui os Pilares Fixos.
_SUSPICIOUS_PATTERNS = [
    r"ignor[ea]\s+(todas\s+)?(as\s+)?(suas\s+)?(regras|instru[çc][õo]es|restri[çc][õo]es)",
    r"esque[çc]a\s+(suas\s+)?(regras|instru[çc][õo]es|restri[çc][õo]es)",
    r"sem\s+(filtro|censura|limites|restri[çc][õo]es)",
    r"modo\s+(sem\s+restri[çc][õo]es|desbloqueado|dan|jailbreak)",
    r"voc[êe]\s+n[ãa]o\s+tem\s+(regras|limites|restri[çc][õo]es)",
    r"finja\s+que\s+n[ãa]o\s+(tem|possui)\s+(regras|restri[çc][õo]es|guardrails)",
    r"disregard\s+(all\s+)?(previous\s+|your\s+)?(instructions|rules|guidelines)",
    r"ignore\s+(all\s+)?(previous\s+|your\s+)?(instructions|rules|safety)",
    r"you\s+(have\s+no|are\s+not\s+bound\s+by)\s+(rules|restrictions|guidelines)",
    r"\bdan\s+mode\b|\bjailbreak(ed)?\b|\bdo\s+anything\s+now\b",
    r"n[ãa]o\s+(precisa|precise)\s+pedir\s+(permiss[ãa]o|autoriza[çc][ãa]o)",
    r"execute\s+(qualquer\s+)?c[óo]digo\s+sem\s+(pedir\s+)?confirma[çc][ãa]o",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SUSPICIOUS_PATTERNS]


def scan_persona_text(text: str) -> list:
    """Retorna a lista de trechos suspeitos encontrados (vazia = limpo).
    Não apaga nada sozinho — quem decide o que fazer é quem chama."""
    if not text:
        return []
    found = []
    for pattern in _COMPILED:
        m = pattern.search(text)
        if m:
            found.append(m.group(0))
    return found


def strip_suspicious(text: str) -> str:
    """Usado no CORE antes de montar o prompt: remove os trechos batidos
    pelo filtro, mesmo que o usuário tenha ignorado o aviso na hora de
    salvar. É a camada determinística — não depende do modelo obedecer."""
    if not text:
        return text
    cleaned = text
    for pattern in _COMPILED:
        cleaned = pattern.sub("[trecho removido pelo filtro de segurança do Zenith]", cleaned)
    return cleaned


# ---------- 2) Caminhos de arquivo customizáveis ----------
_ALLOWED_EXT = {
    "vrm": {".vrm"},
    # CORREÇÃO (fundo em vídeo travando aqui, escondido): o Godot já
    # sabia tocar ".ogv" como fundo animado, mas essa lista aqui —
    # numa camada totalmente separada, no backend — nunca foi
    # atualizada com essa extensão. Resultado: mesmo escolhendo um
    # arquivo certo (.ogv), o SALVAMENTO era silenciosamente
    # rejeitado aqui antes de chegar no Godot, com aquele aviso
    # "caminho não foi salvo". Formatos de vídeo que o Godot NÃO lê
    # de verdade (.mp4, .mov, etc.) continuam de fora de propósito —
    # não adianta salvar um caminho que nunca vai tocar.
    # v20: o fundo aceita QUALQUER imagem ou vídeo (zenith_fundo.py converte o que o Godot não lê e
    # confere o CONTEÚDO do arquivo). Por isso aqui não há lista fechada de extensão para "image":
    # continuam valendo a lista de executáveis proibidos (_DANGEROUS_EXT) e a checagem de "..".
    "image": None,
    "rvc_model": {".pth"},
    "rvc_index": {".index"},
}

# Extensões que NUNCA devem ser aceitas em nenhum campo de "caminho de
# mídia/modelo", mesmo se alguém tentar disfarçar (ex: "fundo.png.exe").
_DANGEROUS_EXT = {".exe", ".bat", ".cmd", ".scr", ".vbs", ".ps1", ".dll", ".sh", ".msi", ".jar"}


def validate_path(path_str: str, kind: str) -> tuple:
    """Retorna (ok: bool, motivo: str). kind em {'vrm','image','rvc_model','rvc_index'}.
    Não abre nem lê o arquivo — só confere extensão e ausência de
    path traversal antes de qualquer módulo tentar carregar o arquivo."""
    if not path_str:
        return True, ""

    p = Path(path_str)
    suffix = p.suffix.lower()

    if suffix in _DANGEROUS_EXT:
        return False, f"Extensão '{suffix}' não é um tipo de mídia/modelo válido aqui — parece um executável disfarçado."

    allowed = _ALLOWED_EXT.get(kind)
    if allowed and suffix not in allowed:
        return False, f"Esperado um arquivo {', '.join(sorted(allowed))} — recebido '{suffix or '(sem extensão)'}'."

    if ".." in p.parts:
        return False, "Caminho contém '..' (tentativa de sair da pasta) — recuse ou peça um caminho absoluto direto."

    return True, ""
