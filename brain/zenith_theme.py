# ============================================================
#  DEPRECADO — a UI do Zenith não usa mais Python/CustomTkinter.
#  Toda a interface (chat, conversas, configurações, aprovação)
#  agora vive dentro do Godot (body/zenith/ui_manager.gd).
#  Este arquivo fica só de referência/histórico e NÃO é chamado
#  por zenith_launcher.py nem zenith_main.py.
# ============================================================

# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_theme.py — Sistema de design único (cores, fontes,
#  espaçamento, curvas de animação). Toda tela do Zenith importa
#  daqui — é assim que a UI para de parecer "colcha de retalhos".
# ============================================================

# ---------- Paleta ----------
# Um cyberpunk mais "premium" que neon puro: fundo quase-preto azulado,
# ciano como cor de assinatura, magenta só como destaque raro (não em
# tudo), e uma escala de cinzas-azulados pros níveis de superfície.
BG_BASE       = "#0a0a12"   # fundo mais escuro (janela)
BG_SURFACE    = "#12121e"   # painéis, cards
BG_SURFACE_2  = "#1a1a2c"   # elementos dentro de painéis (inputs, bolhas IA)
BG_SURFACE_3  = "#22223a"   # hover / elementos elevados

BORDER        = "#2a2a44"
BORDER_FOCUS  = "#00d9ff"

CYAN          = "#00d9ff"   # cor de assinatura do sistema
CYAN_DIM      = "#0a8ba8"
MAGENTA       = "#ff4fa3"   # destaque raro (persona/usuário)
GREEN         = "#00e6a8"   # sucesso / conectado / aprovar
AMBER         = "#ffb84d"   # atenção
RED           = "#ff5470"   # erro / negar / bloqueado

TEXT_PRIMARY  = "#eef0fa"
TEXT_SECOND   = "#8d8fae"
TEXT_MUTED    = "#5a5c78"
TEXT_ON_ACCENT = "#04141a"

# Bolhas de chat
BUBBLE_USER   = "#0f3a44"
BUBBLE_USER_BORDER = CYAN_DIM
BUBBLE_AI     = "#1a1a2c"
BUBBLE_AI_BORDER = "#33335a"

# ---------- Tipografia ----------
FONT_FAMILY      = "Segoe UI"
FONT_FAMILY_MONO = "Cascadia Mono"   # fallback tratado em zenith_widgets.safe_font

F_H1   = (FONT_FAMILY, 20, "bold")
F_H2   = (FONT_FAMILY, 15, "bold")
F_BODY = (FONT_FAMILY, 13)
F_SMALL = (FONT_FAMILY, 11)
F_MONO = (FONT_FAMILY_MONO, 12)
F_LABEL = (FONT_FAMILY, 12, "bold")

# ---------- Espaçamento (múltiplos de 4, como qualquer design system sério) ----------
S1, S2, S3, S4, S5, S6 = 4, 8, 12, 16, 24, 32
RADIUS_SM, RADIUS_MD, RADIUS_LG = 6, 10, 16

# ---------- Movimento ----------
# Durações em ms e "passos" de easing pré-calculados (ease-out cúbico),
# usados pelos widgets animados em zenith_widgets.py.
DUR_FAST   = 120
DUR_MED    = 220
DUR_SLOW   = 380
FPS_STEP   = 16   # ~60fps


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - pow(1 - t, 3)


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Interpola linearmente entre duas cores hex '#rrggbb'."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"
