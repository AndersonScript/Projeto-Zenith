"""
Zenith — TEMA de cores da interface (v25). Pedido do Anderson: "personalização de cores que só fica no azul claro e azul escuro".

Este módulo só calcula a PALETA (nome da cor -> #hex); o Godot guarda em user://zenith_tema.cfg e aplica na próxima
abertura (a interface é montada uma vez, ao iniciar). Comandos: /tema (lista), /tema roxo, /tema cor #ff8800 (só o destaque),
/tema fundo #101820 (cor base; o resto é derivado), /tema padrao.
"""
from __future__ import annotations

import colorsys
import re

CHAVES = ("BG_BASE", "BG_PANEL", "BG_SURFACE", "BG_SURFACE_2", "BG_SURFACE_3", "BORDER", "CYAN", "CYAN_DIM", "MAGENTA",
          "GREEN", "RED", "TEXT_PRIMARY", "TEXT_SECOND", "TEXT_MUTED", "BUBBLE_USER", "BUBBLE_AI")
_RE_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")

# Escuros: (fundo base, destaque). Os demais tons saem da base e do destaque.
_ESCUROS = {
    "ciano": ("#0d0d1a", "#00d9ff"), "azul": ("#0b1020", "#448aff"), "roxo": ("#120d1f", "#b388ff"),
    "rosa": ("#1a0d16", "#ff4fa3"), "vermelho": ("#1a0d0f", "#ff5470"), "laranja": ("#1a120a", "#ff9100"),
    "amarelo": ("#18160a", "#ffd54f"), "verde": ("#0b1a14", "#00e676"), "turquesa": ("#0a1a1a", "#1de9b6"),
    "cinza": ("#121212", "#b0bec5"), "amoled": ("#000000", "#00d9ff"),
}
PRESETS = tuple(_ESCUROS) + ("claro",)
PADRAO = "ciano"


def _rgb(h: str):
    m = _RE_HEX.match(h or "")
    if not m:
        raise ValueError(f"cor inválida: {h!r} (use #rrggbb)")
    v = m.group(1)
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def eh_hex(h: str) -> bool:
    return bool(_RE_HEX.match(h or ""))


def normalizar_hex(h: str) -> str:
    return _hex(_rgb(h))


def paleta(preset: str = PADRAO, destaque: str = "", fundo: str = "") -> dict:
    """Paleta completa {CHAVE: '#rrggbb'}. `destaque`/`fundo` (opcionais) sobrescrevem o preset."""
    preset = (preset or PADRAO).lower()
    if preset not in PRESETS:
        preset = PADRAO
    claro = preset == "claro"
    base_h, dest_h = (("#eef1f8", "#0b6fd6") if claro else _ESCUROS[preset])
    base = _rgb(fundo) if eh_hex(fundo) else _rgb(base_h)
    dest = _rgb(destaque) if eh_hex(destaque) else _rgb(dest_h)
    branco, preto = (1, 1, 1), (0, 0, 0)
    if claro:
        p = {"BG_BASE": base, "BG_PANEL": _mix(base, branco, 0.55), "BG_SURFACE": _mix(base, branco, 0.55),
             "BG_SURFACE_2": _mix(base, branco, 0.25), "BG_SURFACE_3": _mix(base, preto, 0.05),
             "BORDER": _mix(base, preto, 0.16), "TEXT_PRIMARY": (0.08, 0.09, 0.16), "TEXT_SECOND": (0.27, 0.29, 0.40),
             "TEXT_MUTED": (0.45, 0.47, 0.58), "BUBBLE_USER": _mix(dest, branco, 0.78), "BUBBLE_AI": _mix(base, branco, 0.6)}
    else:
        p = {"BG_BASE": base, "BG_PANEL": _mix(base, branco, 0.04), "BG_SURFACE": _mix(base, branco, 0.04),
             "BG_SURFACE_2": _mix(base, branco, 0.09), "BG_SURFACE_3": _mix(base, branco, 0.15),
             "BORDER": _mix(base, branco, 0.22), "TEXT_PRIMARY": (0.93, 0.94, 0.98), "TEXT_SECOND": (0.55, 0.56, 0.68),
             "TEXT_MUTED": (0.35, 0.36, 0.47), "BUBBLE_USER": _mix(base, dest, 0.22), "BUBBLE_AI": _mix(base, branco, 0.09)}
    h, s, v = colorsys.rgb_to_hsv(*dest)
    p["CYAN"] = dest
    p["CYAN_DIM"] = colorsys.hsv_to_rgb(h, s, max(0.0, v * 0.6))
    p["MAGENTA"] = _rgb("#ff4fa3")
    p["GREEN"] = _rgb("#00e6a8" if not claro else "#00a878")
    p["RED"] = _rgb("#ff5470" if not claro else "#d62848")
    return {k: _hex(p[k]) for k in CHAVES}


def paleta_dos_settings(settings) -> dict:
    g = (lambda k, d="": settings.get(k, d)) if settings is not None else (lambda k, d="": d)
    try:
        return paleta(g("ui_tema_preset", PADRAO), g("ui_tema_destaque", ""), g("ui_tema_fundo", ""))
    except ValueError:
        return paleta(PADRAO)


def lista_texto() -> str:
    return ("🎨 Temas: " + " · ".join(PRESETS) + "\nUso: /tema roxo · /tema cor #ff8800 (muda só o destaque) · /tema fundo #101820 "
            "(cor base; o resto é derivado) · /tema padrao. Aplica na PRÓXIMA abertura do Zenith (a interface é montada ao iniciar). "
            "\"claro\" é experimental.")
