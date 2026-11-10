# ============================================================
#  DEPRECADO — a UI do Zenith não usa mais Python/CustomTkinter.
#  Toda a interface (chat, conversas, configurações, aprovação)
#  agora vive dentro do Godot (body/zenith/ui_manager.gd).
#  Este arquivo fica só de referência/histórico e NÃO é chamado
#  por zenith_launcher.py nem zenith_main.py.
# ============================================================

# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_widgets.py — Componentes animados reutilizáveis.
#  CustomTkinter não tem essas coisas prontas; construídas aqui
#  uma vez só, testadas uma vez só, usadas em toda a UI.
# ============================================================

import tkinter as tk
from tkinter import font as tkfont
import customtkinter as ctk
from brain import zenith_theme as T


def safe_font(root, family, size, weight="normal"):
    """CTk quebra (ou cai pra um fallback feio) se a fonte não existir
    no sistema. Verifica antes e usa uma família segura no lugar."""
    try:
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    fam = family if family in available else ("Consolas" if "mono" in family.lower() else "Segoe UI")
    if fam not in available:
        fam = "TkDefaultFont"
    return ctk.CTkFont(family=fam, size=size, weight=weight)


class PulseDot(ctk.CTkFrame):
    """Indicador de status com animação de 'respiração' (canvas puro,
    porque widgets CTk normais não têm opacidade real)."""

    def __init__(self, master, size=10, color=T.GREEN, **kwargs):
        super().__init__(master, fg_color="transparent", width=size, height=size, **kwargs)
        self.size = size
        self.color = color
        self.canvas = tk.Canvas(self, width=size * 2, height=size * 2,
                                 bg=self._safe_bg(master), highlightthickness=0)
        self.canvas.pack()
        self._t = 0.0
        self._running = False
        self._dot = None
        self._glow = None
        self._draw_dot(1.0)

    def _safe_bg(self, master):
        try:
            return master.cget("fg_color") if isinstance(master.cget("fg_color"), str) else T.BG_SURFACE
        except Exception:
            return T.BG_SURFACE

    def set_color(self, color):
        self.color = color
        self._draw_dot(0.6 + 0.4 * abs(((self._t % 2) - 1)))

    def _draw_dot(self, pulse):
        self.canvas.delete("all")
        cx = cy = self.size
        r_core = self.size * 0.42
        r_glow = self.size * (0.55 + 0.45 * pulse)
        self.canvas.create_oval(cx - r_glow, cy - r_glow, cx + r_glow, cy + r_glow,
                                 fill=self.color, outline="", stipple="gray25")
        self.canvas.create_oval(cx - r_core, cy - r_core, cx + r_core, cy + r_core,
                                 fill=self.color, outline="")

    def start(self):
        if self._running:
            return
        self._running = True
        self._animate()

    def stop(self):
        self._running = False

    def _animate(self):
        if not self._running:
            return
        self._t += 0.08
        import math
        pulse = 0.5 + 0.5 * math.sin(self._t)
        self._draw_dot(pulse)
        self.after(40, self._animate)


class TypingIndicator(ctk.CTkFrame):
    """Três pontinhos subindo/descendo em sequência — usado enquanto
    a IA está pensando, no lugar de travar a tela sem feedback nenhum."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=T.BUBBLE_AI, corner_radius=T.RADIUS_MD, **kwargs)
        self.canvas = tk.Canvas(self, width=52, height=24, bg=T.BUBBLE_AI, highlightthickness=0)
        self.canvas.pack(padx=T.S2, pady=T.S2)
        self._t = 0
        self._running = False

    def start(self):
        self._running = True
        self._tick()

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        import math
        self.canvas.delete("all")
        for i in range(3):
            phase = self._t * 0.15 - i * 0.6
            y = 12 + math.sin(phase) * 5
            self.canvas.create_oval(10 + i * 16 - 4, y - 4, 10 + i * 16 + 4, y + 4,
                                     fill=T.CYAN, outline="")
        self._t += 1
        self.after(40, self._tick)


class SegmentedToggle(ctk.CTkFrame):
    """Substitui os OptionButton de 'ask/always/never' por um controle
    segmentado com um indicador que desliza suavemente até a opção
    escolhida — visualmente muito mais claro que um dropdown escondido."""

    def __init__(self, master, options, value=None, on_change=None, width=240, **kwargs):
        super().__init__(master, fg_color=T.BG_SURFACE_2, corner_radius=T.RADIUS_MD, **kwargs)
        self.options = options
        self.on_change = on_change
        self.width = width
        self.seg_w = width / len(options)
        self.value = value if value in options else options[0]
        self._target_x = self.options.index(self.value) * self.seg_w

        self.canvas = tk.Canvas(self, width=width, height=32, bg=T.BG_SURFACE_2, highlightthickness=0)
        self.canvas.pack(padx=2, pady=2)
        self.canvas.bind("<Button-1>", self._on_click)
        self._anim_x = self._target_x
        self._redraw()

    def _on_click(self, event):
        idx = min(len(self.options) - 1, max(0, int(event.x // self.seg_w)))
        self.set_value(self.options[idx], animate=True, fire_event=True)

    def set_value(self, value, animate=True, fire_event=False):
        if value not in self.options:
            return
        self.value = value
        self._target_x = self.options.index(value) * self.seg_w
        if animate:
            self._animate_to_target()
        else:
            self._anim_x = self._target_x
            self._redraw()
        if fire_event and self.on_change:
            self.on_change(value)

    def _animate_to_target(self):
        diff = self._target_x - self._anim_x
        if abs(diff) < 0.5:
            self._anim_x = self._target_x
            self._redraw()
            return
        self._anim_x += diff * 0.35
        self._redraw()
        self.after(T.FPS_STEP, self._animate_to_target)

    def _redraw(self):
        self.canvas.delete("all")
        h = 32
        self.canvas.create_rectangle(self._anim_x, 0, self._anim_x + self.seg_w, h,
                                      fill=T.CYAN, outline="")
        for i, opt in enumerate(self.options):
            cx = i * self.seg_w + self.seg_w / 2
            active = (opt == self.value)
            self.canvas.create_text(cx, h / 2, text=opt,
                                     fill=T.TEXT_ON_ACCENT if active else T.TEXT_SECOND,
                                     font=("Segoe UI", 11, "bold" if active else "normal"))


class GlowSlider(ctk.CTkFrame):
    """Slider desenhado à mão: preenchimento em degradê simulado e um
    'halo' no manípulo ao arrastar. Os HSlider padrão da versão antiga
    ficavam com o manípulo sempre travado no máximo — esse é conectado
    de verdade ao evento de arraste, sem depender de binding externo."""

    def __init__(self, master, from_=0.0, to=1.0, value=1.0, on_change=None,
                 width=260, height=28, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.from_, self.to = from_, to
        self.value = value
        self.on_change = on_change
        self.width, self.height = width, height
        self.canvas = tk.Canvas(self, width=width, height=height, bg=T.BG_SURFACE, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self._dragging = False
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_dragging", False))
        self._redraw()

    def _drag(self, event):
        self._dragging = True
        ratio = max(0.0, min(1.0, event.x / self.width))
        self.value = self.from_ + ratio * (self.to - self.from_)
        self._redraw()
        if self.on_change:
            self.on_change(self.value)

    def set(self, value):
        self.value = max(self.from_, min(self.to, value))
        self._redraw()

    def get(self):
        return self.value

    def _redraw(self):
        self.canvas.delete("all")
        ratio = (self.value - self.from_) / (self.to - self.from_ or 1)
        track_y = self.height / 2
        self.canvas.create_line(4, track_y, self.width - 4, track_y,
                                 fill=T.BG_SURFACE_3, width=4, capstyle="round")
        fill_x = 4 + ratio * (self.width - 8)
        self.canvas.create_line(4, track_y, fill_x, track_y,
                                 fill=T.CYAN, width=4, capstyle="round")
        r = 9 if self._dragging else 7
        if self._dragging:
            self.canvas.create_oval(fill_x - r - 4, track_y - r - 4, fill_x + r + 4, track_y + r + 4,
                                     fill=T.CYAN, outline="", stipple="gray25")
        self.canvas.create_oval(fill_x - r, track_y - r, fill_x + r, track_y + r,
                                 fill=T.TEXT_PRIMARY, outline=T.CYAN, width=2)


class AnimatedBubble(ctk.CTkFrame):
    """Bolha de chat que 'nasce' com um leve slide + crescimento em vez
    de simplesmente aparecer travada na tela — é essa pequena diferença
    que separa um app de protótipo de um app com acabamento."""

    def __init__(self, master, text, sender, **kwargs):
        is_user = (sender == "user")
        bg = T.BUBBLE_USER if is_user else T.BUBBLE_AI
        border = T.BUBBLE_USER_BORDER if is_user else T.BUBBLE_AI_BORDER
        super().__init__(master, fg_color=bg, corner_radius=T.RADIUS_MD,
                          border_width=1, border_color=border, **kwargs)
        self.label = ctk.CTkLabel(self, text=text, justify="left", anchor="w",
                                   text_color=T.TEXT_PRIMARY, wraplength=460,
                                   font=safe_font(self, T.FONT_FAMILY, 13))
        self.label.pack(padx=T.S3, pady=T.S2, fill="both")
        self._step = 0
        self.configure(fg_color=bg)

    def animate_in(self):
        # Efeito simples de "assentar": começa levemente translúcido via
        # cor mais próxima do fundo e migra pra cor final da bolha.
        target = self.cget("fg_color")
        start = T.BG_SURFACE
        steps = 8
        def run(i=0):
            if i > steps:
                self.configure(fg_color=target)
                return
            t = T.ease_out_cubic(i / steps) if hasattr(T, "ease_out_cubic") else i / steps
            self.configure(fg_color=T.lerp_color(start, target, t))
            self.after(14, lambda: run(i + 1))
        run()
