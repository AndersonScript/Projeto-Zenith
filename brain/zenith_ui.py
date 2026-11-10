# ============================================================
#  DEPRECADO — a UI do Zenith não usa mais Python/CustomTkinter.
#  Toda a interface (chat, conversas, configurações, aprovação)
#  agora vive dentro do Godot (body/zenith/ui_manager.gd).
#  Este arquivo fica só de referência/histórico e NÃO é chamado
#  por zenith_launcher.py nem zenith_main.py.
# ============================================================

# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_ui.py — Central de Controle.
#
#  Nesta versão:
#   - Histórico de conversa persistente (zenith_history) — carregado
#     ao abrir e enviado de verdade pro Corpo quando ele sincroniza.
#   - Papel de parede customizável no chat.
#   - Aba "Sistema": caminho do Godot e auto-abrir — nada disso exige
#     mexer no código-fonte.
#   - Auto-abre o Corpo (Godot) junto com a Central de Controle.
#   - Aviso (não bloqueio silencioso) quando texto de personalidade
#     ou caminho de arquivo passa pelo filtro de conteúdo suspeito.
# ============================================================

import os
import sys
import atexit
import subprocess
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from brain import zenith_theme as T
from brain import zenith_history as history
from brain.zenith_validator import scan_persona_text, validate_path
from brain.zenith_widgets import (
    safe_font, PulseDot, TypingIndicator, SegmentedToggle, GlowSlider, AnimatedBubble,
)
from brain.zenith_settings import ZenithSettings, BASE_DIR
from brain.zenith_core import ZenithCore, SYSTEM_NAME, CREATOR
from brain.zenith_bridge import ZenithBridge
from brain.zenith_gatekeeper import ApprovalWindow

ctk.set_appearance_mode("dark")


# ============================================================
#  PROCESSO DO CORPO (Godot) — sobe e derruba junto com a UI
# ============================================================
class GodotProcessManager:
    """Antes, o Corpo tinha que ser aberto manualmente, num Godot separado.
    Agora, se 'auto_launch_godot' estiver ligado e um caminho de
    executável estiver configurado, a Central de Controle sobe o
    processo sozinha e mata ele quando fecha."""

    def __init__(self, settings: ZenithSettings):
        self.settings = settings
        self.process = None
        atexit.register(self.stop)

    def start_if_configured(self):
        if not self.settings.get("auto_launch_godot", True):
            return
        exe = self.settings.get("godot_executable_path", "")
        if not exe or not os.path.isfile(exe):
            print("[Zenith/Corpo] Nenhum executável do Godot configurado ainda "
                  "(Configurações > Sistema) — abrindo só a Central de Controle.")
            return
        try:
            args = [exe]
            # Se o caminho apontar pro motor (godot.exe) em vez de um
            # export standalone, precisa do --path pro projeto do Corpo.
            if os.path.basename(exe).lower().startswith("godot"):
                project = self.settings.get("godot_project_path") or str(BASE_DIR / "body" / "zenith")
                args += ["--path", project]
            self.process = subprocess.Popen(args, cwd=os.path.dirname(exe) or None)
            print(f"[Zenith/Corpo] Processo do Godot iniciado (pid={self.process.pid}).")
        except Exception as e:
            print(f"[Zenith/Corpo] Não consegui abrir o Godot automaticamente: {e}")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()


# ============================================================
#  BARRA SUPERIOR
# ============================================================
class TopBar(ctk.CTkFrame):
    def __init__(self, master, persona_name, on_settings, on_toggle_move):
        super().__init__(master, fg_color=T.BG_SURFACE, height=56, corner_radius=0)
        self.grid_propagate(False)

        title = ctk.CTkLabel(self, text=f"◆ {persona_name}", anchor="w",
                              text_color=T.TEXT_PRIMARY, font=safe_font(self, T.FONT_FAMILY, 16, "bold"))
        title.pack(side="left", padx=(T.S4, T.S2), pady=T.S2)

        self.status_dot = PulseDot(self, size=8, color=T.RED)
        self.status_dot.pack(side="left", padx=(0, T.S1))
        self.status_label = ctk.CTkLabel(self, text="Corpo desconectado", text_color=T.TEXT_SECOND,
                                          font=safe_font(self, T.FONT_FAMILY, 11))
        self.status_label.pack(side="left")

        gear = ctk.CTkButton(self, text="⚙  Configurações", width=140, height=32,
                              fg_color=T.BG_SURFACE_2, hover_color=T.BG_SURFACE_3,
                              text_color=T.TEXT_PRIMARY, corner_radius=T.RADIUS_MD,
                              font=safe_font(self, T.FONT_FAMILY, 12), command=on_settings)
        gear.pack(side="right", padx=T.S4, pady=T.S2)

        self.move_btn = ctk.CTkButton(self, text="◈  Mover Zenith", width=140, height=32,
                                       fg_color=T.BG_SURFACE_2, hover_color=T.BG_SURFACE_3,
                                       text_color=T.TEXT_PRIMARY, corner_radius=T.RADIUS_MD,
                                       font=safe_font(self, T.FONT_FAMILY, 12), command=on_toggle_move)
        self.move_btn.pack(side="right", padx=(0, T.S2), pady=T.S2)

    def set_connected(self, connected: bool):
        self.status_dot.set_color(T.GREEN if connected else T.RED)
        self.status_label.configure(text="Corpo conectado" if connected else "Corpo desconectado")

    def set_moving(self, moving: bool):
        if moving:
            self.move_btn.configure(text="■  Fixar Zenith", fg_color=T.RED, hover_color="#c94059")
        else:
            self.move_btn.configure(text="◈  Mover Zenith", fg_color=T.BG_SURFACE_2, hover_color=T.BG_SURFACE_3)


# ============================================================
#  ÁREA DE CHAT COM PAPEL DE PAREDE OPCIONAL
# ============================================================
class ChatArea(ctk.CTkScrollableFrame):
    """CTkScrollableFrame não tem suporte nativo a imagem de fundo —
    desenhamos a imagem direto no canvas interno dele (_parent_canvas)
    e mandamos pro fundo (tag_lower), antes de qualquer bolha."""

    def __init__(self, master):
        super().__init__(master, fg_color=T.BG_BASE)
        self.grid_columnconfigure(0, weight=1)
        self._bg_photo = None
        self._bg_image_id = None
        self._parent_canvas.bind("<Configure>", lambda e: self._reposition_bg())

    def set_wallpaper(self, path: str):
        self._parent_canvas.delete("bg")
        self._bg_photo = None
        if not path or not os.path.isfile(path):
            return
        try:
            from PIL import Image, ImageTk, ImageEnhance
            img = Image.open(path).convert("RGB")
            # Escurece um pouco a imagem pra bolha de texto continuar legível
            # por cima — sem isso, papel de parede claro deixa o chat ilegível.
            img = ImageEnhance.Brightness(img).enhance(0.45)
            self._pil_source = img
            self._redraw_bg()
        except Exception as e:
            print(f"[Zenith/UI] Não consegui carregar o papel de parede: {e}")

    def _redraw_bg(self):
        if not hasattr(self, "_pil_source") or self._pil_source is None:
            return
        from PIL import ImageTk
        cw = max(self._parent_canvas.winfo_width(), 400)
        ch = max(self._parent_canvas.winfo_height(), 400)
        src = self._pil_source
        scale = max(cw / src.width, ch / src.height)
        resized = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1))
        left = (resized.width - cw) // 2
        top = (resized.height - ch) // 2
        cropped = resized.crop((left, top, left + cw, top + ch))
        self._bg_photo = ImageTk.PhotoImage(cropped)
        self._parent_canvas.delete("bg")
        self._bg_image_id = self._parent_canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg")
        self._parent_canvas.tag_lower("bg")

    def _reposition_bg(self):
        if hasattr(self, "_pil_source") and self._pil_source is not None:
            self._redraw_bg()


# ============================================================
#  JANELA PRINCIPAL — CHAT
# ============================================================
class ZenithApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{SYSTEM_NAME} — Central de Controle")
        self.geometry("880x680")
        self.minsize(560, 480)
        self.configure(fg_color=T.BG_BASE)

        self.settings = ZenithSettings()
        self.core = ZenithCore(self.settings)
        self.bridge = ZenithBridge()
        self.bridge.set_state_callback(self._on_bridge_state)
        self.bridge.set_message_callback(self._on_bridge_message)
        self.godot = GodotProcessManager(self.settings)

        self._moving_avatar = False
        self._settings_window = None
        self._build_ui()
        self._load_history_into_ui()
        self.after(300, self.godot.start_if_configured)

    # ---------------- layout ----------------
    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.topbar = TopBar(self, self.settings.persona_name,
                              on_settings=self._open_settings,
                              on_toggle_move=self._toggle_move_avatar)
        self.topbar.grid(row=0, column=0, sticky="ew")

        self.chat_scroll = ChatArea(self)
        self.chat_scroll.grid(row=1, column=0, sticky="nsew", padx=T.S4, pady=T.S3)
        wallpaper = self.settings.get("chat_wallpaper_path", "")
        if wallpaper:
            self.after(100, lambda: self.chat_scroll.set_wallpaper(wallpaper))
        self._row = 0
        self._typing_widget = None

        bottom = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0, height=64)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_propagate(False)
        bottom.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(bottom, placeholder_text=f"Fale com {self.settings.persona_name}...",
                                   fg_color=T.BG_SURFACE_2, border_color=T.BORDER,
                                   text_color=T.TEXT_PRIMARY, height=40, corner_radius=T.RADIUS_MD,
                                   font=safe_font(self, T.FONT_FAMILY, 13))
        self.entry.grid(row=0, column=0, sticky="ew", padx=(T.S4, T.S2), pady=T.S3)
        self.entry.bind("<Return>", lambda e: self._on_send())

        send_btn = ctk.CTkButton(bottom, text="Enviar", width=96, height=40,
                                  fg_color=T.CYAN, hover_color=T.CYAN_DIM, text_color=T.TEXT_ON_ACCENT,
                                  corner_radius=T.RADIUS_MD, font=safe_font(self, T.FONT_FAMILY, 13, "bold"),
                                  command=self._on_send)
        send_btn.grid(row=0, column=1, padx=(0, T.S4), pady=T.S3)

    # ---------------- histórico ----------------
    def _load_history_into_ui(self):
        for entry in history.load()[-60:]:  # não pesa a UI carregando 500 bolhas de cara
            self._add_bubble(entry.get("text", ""), entry.get("sender", "ai"), animate=False)

    # ---------------- bolhas ----------------
    def _add_bubble(self, text, sender, animate=True):
        bubble = AnimatedBubble(self.chat_scroll, text, sender)
        anchor = "e" if sender == "user" else "w"
        bubble.grid(row=self._row, column=0, sticky=anchor, padx=T.S1, pady=T.S1)
        self._row += 1
        if animate:
            bubble.animate_in()
        self.after(30, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))
        return bubble

    def _show_typing(self):
        self._typing_widget = TypingIndicator(self.chat_scroll)
        self._typing_widget.grid(row=self._row, column=0, sticky="w", padx=T.S1, pady=T.S1)
        self._typing_widget.start()
        self._row += 1
        self.after(30, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    def _hide_typing(self):
        if self._typing_widget:
            self._typing_widget.stop()
            self._typing_widget.destroy()
            self._typing_widget = None

    # ---------------- envio / IA ----------------
    def _on_send(self):
        msg = self.entry.get().strip()
        if not msg:
            return
        self.entry.delete(0, "end")
        self._add_bubble(msg, "user")
        history.append("user", msg)
        self.bridge.send_chat_message("user", msg)
        self.bridge.send({"action": "do", "name": "state:thinking"})
        self._show_typing()
        threading.Thread(target=self._think, args=(msg,), daemon=True).start()

    def _think(self, msg):
        result = self.core.pensar(msg)
        self.after(0, lambda: self._handle_result(result))

    def _handle_result(self, result):
        self._hide_typing()
        text = result.get("text", "")
        pending = result.get("pending_action")
        veto = result.get("veto_reason")

        if result.get("blocked"):
            self._add_bubble(text, "ai")
            history.append("ai", text)
            return

        if text:
            self._add_bubble(text, "ai")
            history.append("ai", text)
            self.bridge.send_chat_message("ai", text)
            self.bridge.send({"action": "expression", "type": self._guess_expression(text)})
            self.bridge.send({"action": "do", "name": "state:speaking"})
            self.after(1500, lambda: self.bridge.send({"action": "do", "name": "state:idle"}))

        if pending and veto:
            self._add_bubble(f"⛔ {veto}", "ai")
            return

        if pending:
            self._ask_approval(pending)

    def _ask_approval(self, pending):
        win = ApprovalWindow(self, pending, self.settings.user_name, self.settings.persona_name)
        approved = win.ask()
        resultado = self.core.approve_action(pending) if approved else "⛔ Ação negada pelo usuário."
        self._add_bubble(resultado, "ai")
        history.append("ai", resultado)

    @staticmethod
    def _guess_expression(text: str) -> str:
        low = text.lower()
        if any(w in low for w in ("haha", "kkk", "rs", "engraçado")):
            return "happy"
        if any(w in low for w in ("desculpa", "sinto muito", "triste")):
            return "sad"
        if "!" in text:
            return "surprised"
        return "neutral"

    # ---------------- ponte / corpo ----------------
    def _on_bridge_state(self, connected: bool):
        self.after(0, lambda: self.topbar.set_connected(connected))

    def _on_bridge_message(self, data: dict):
        action = data.get("action")
        if action == "chat":
            text = data.get("text", "")
            if text:
                self.after(0, lambda: self._add_bubble(text, "user"))
                history.append("user", text)
                self.after(0, self._show_typing)
                threading.Thread(target=self._think, args=(text,), daemon=True).start()
        elif action == "update_config":
            self.settings.update({k: v for k, v in data.items() if k != "action"})
            self.core.reload_api_keys(self.settings)
        elif action == "request_sync":
            # O Corpo reconectou (ou abriu agora) e quer o histórico de
            # verdade — antes isso não existia, o chat do Godot sempre
            # nascia vazio mesmo com conversas antigas salvas.
            payload = [{"sender": e.get("sender", "ai"), "text": e.get("text", "")}
                       for e in history.load()[-100:]]
            self.bridge.send({"action": "sync_history", "history": payload})

    def _toggle_move_avatar(self):
        self._moving_avatar = not self._moving_avatar
        self.topbar.set_moving(self._moving_avatar)
        self.bridge.send({"action": "do", "name": "set_edit_mode", "value": self._moving_avatar})

    # ---------------- configurações ----------------
    def _open_settings(self):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return
        self._settings_window = SettingsWindow(self, self.settings, self._on_settings_saved)

    def _on_settings_saved(self, changes: dict):
        self.settings.update(changes)
        self.core.reload_api_keys(self.settings)
        self.bridge.send({"action": "update_config", **changes})
        if "chat_wallpaper_path" in changes:
            self.chat_scroll.set_wallpaper(changes["chat_wallpaper_path"])
        if changes.get("godot_executable_path") and not self.godot.process:
            self.godot.settings = self.settings
            self.godot.start_if_configured()


# ============================================================
#  JANELA DE CONFIGURAÇÕES
# ============================================================
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, settings: ZenithSettings, on_save):
        super().__init__(master)
        self._fields = {}
        self.settings = settings
        self.on_save = on_save
        self.title("Zenith — Configurações")
        self.geometry("640x700")
        self.configure(fg_color=T.BG_BASE)
        self.transient(master)
        self.grab_set()

        self.tabs = ctk.CTkTabview(self, fg_color=T.BG_SURFACE,
                                    segmented_button_selected_color=T.CYAN,
                                    segmented_button_selected_hover_color=T.CYAN_DIM,
                                    text_color=T.TEXT_PRIMARY)
        self.tabs.pack(fill="both", expand=True, padx=T.S4, pady=(T.S4, 0))

        self._build_identity_tab(self.tabs.add("Identidade"))
        self._build_apis_tab(self.tabs.add("IAs & Chaves"))
        self._build_voice_tab(self.tabs.add("Voz"))
        self._build_body_tab(self.tabs.add("Corpo / VRM"))
        self._build_appearance_tab(self.tabs.add("Aparência"))
        self._build_system_tab(self.tabs.add("Sistema"))
        self._build_permissions_tab(self.tabs.add("Permissões"))

        save = ctk.CTkButton(self, text="Salvar e Aplicar", height=42, fg_color=T.CYAN,
                              hover_color=T.CYAN_DIM, text_color=T.TEXT_ON_ACCENT,
                              font=safe_font(self, T.FONT_FAMILY, 13, "bold"), command=self._save)
        save.pack(fill="x", padx=T.S4, pady=T.S4)

    # ---- helpers ----
    def _labeled_entry(self, parent, label, key, secret=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=T.S1)
        ctk.CTkLabel(row, text=label, text_color=T.TEXT_SECOND, anchor="w",
                     font=safe_font(self, T.FONT_FAMILY, 11)).pack(fill="x")
        entry = ctk.CTkEntry(row, fg_color=T.BG_SURFACE_2, border_color=T.BORDER,
                              text_color=T.TEXT_PRIMARY, show="•" if secret else "",
                              font=safe_font(self, T.FONT_FAMILY, 12))
        entry.insert(0, self.settings.get(key, "") or "")
        entry.pack(fill="x", pady=(2, 0))
        self._fields[key] = entry
        return entry

    def _path_entry_with_browse(self, parent, label, key, filetypes, dialog_kind="open"):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=T.S1)
        ctk.CTkLabel(row, text=label, text_color=T.TEXT_SECOND, anchor="w",
                     font=safe_font(self, T.FONT_FAMILY, 11)).pack(fill="x")
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", pady=(2, 0))
        inner.grid_columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(inner, fg_color=T.BG_SURFACE_2, border_color=T.BORDER,
                              text_color=T.TEXT_PRIMARY, font=safe_font(self, T.FONT_FAMILY, 12))
        entry.insert(0, self.settings.get(key, "") or "")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, T.S1))

        def browse():
            path = filedialog.askopenfilename(filetypes=filetypes) if dialog_kind == "open" \
                else filedialog.askdirectory()
            if path:
                entry.delete(0, "end")
                entry.insert(0, path)

        ctk.CTkButton(inner, text="Procurar...", width=90, fg_color=T.BG_SURFACE_3,
                      hover_color=T.CYAN_DIM, text_color=T.TEXT_PRIMARY,
                      font=safe_font(self, T.FONT_FAMILY, 11), command=browse).grid(row=0, column=1)
        self._fields[key] = entry
        return entry

    def _section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, text_color=T.CYAN, anchor="w",
                     font=safe_font(self, T.FONT_FAMILY, 12, "bold")).pack(fill="x", pady=(T.S3, T.S1))

    def _hint(self, parent, text):
        ctk.CTkLabel(parent, text=text, text_color=T.TEXT_MUTED, anchor="w", wraplength=540, justify="left",
                     font=safe_font(self, T.FONT_FAMILY, 10)).pack(fill="x", pady=(0, T.S1))

    # ---- abas ----
    def _build_identity_tab(self, tab):
        self._labeled_entry(tab, "Nome da IA (persona)", "persona_name")
        self._labeled_entry(tab, "Seu nome", "user_name")
        ctk.CTkLabel(tab, text="Personalidade (texto livre)", text_color=T.TEXT_SECOND, anchor="w",
                     font=safe_font(self, T.FONT_FAMILY, 11)).pack(fill="x", pady=(T.S3, T.S1))
        self.persona_box = ctk.CTkTextbox(tab, fg_color=T.BG_SURFACE_2, text_color=T.TEXT_PRIMARY, height=100)
        self.persona_box.insert("1.0", self.settings.get("persona_description", "") or "")
        self.persona_box.pack(fill="x")
        ctk.CTkLabel(tab, text="Pilares extras seus (os 4 fixos do sistema não mudam)",
                     text_color=T.TEXT_SECOND, anchor="w",
                     font=safe_font(self, T.FONT_FAMILY, 11)).pack(fill="x", pady=(T.S3, T.S1))
        self.pillars_box = ctk.CTkTextbox(tab, fg_color=T.BG_SURFACE_2, text_color=T.TEXT_PRIMARY, height=100)
        self.pillars_box.insert("1.0", self.settings.get("user_pillars", "") or "")
        self.pillars_box.pack(fill="x")

    def _build_apis_tab(self, tab):
        self._section_label(tab, "Provedor ativo")
        self.active_ai_toggle = SegmentedToggle(
            tab, ["gemini", "openai", "claude", "groq"],
            value=self.settings.get("active_ai", "gemini"), width=380)
        self.active_ai_toggle.pack(pady=(0, T.S3))
        self._section_label(tab, "Chaves de API")
        self._labeled_entry(tab, "Gemini API Key", "gemini_key", secret=True)
        self._labeled_entry(tab, "OpenAI API Key", "openai_key", secret=True)
        self._labeled_entry(tab, "OpenRouter Key (Claude / Llama)", "openrouter_key", secret=True)
        self._labeled_entry(tab, "Groq API Key", "groq_key", secret=True)
        self._section_label(tab, "API customizada (opcional)")
        self._labeled_entry(tab, "URL", "custom_api_url")
        self._labeled_entry(tab, "Chave", "custom_api_key", secret=True)
        self._labeled_entry(tab, "Modelo", "custom_api_model")

    def _build_voice_tab(self, tab):
        self._section_label(tab, "ElevenLabs")
        self._labeled_entry(tab, "API Key", "elevenlabs_key", secret=True)
        self._labeled_entry(tab, "Voice ID", "elevenlabs_voice_id")
        self._section_label(tab, "RVC (timbre de voz customizado)")
        self._path_entry_with_browse(tab, "Modelo (.pth)", "rvc_model_path",
                                      [("Modelo RVC", "*.pth")])
        self._path_entry_with_browse(tab, "Índice (.index)", "rvc_index_path",
                                      [("Índice RVC", "*.index")])
        self._section_label(tab, "Volume da voz")
        self.volume_slider = GlowSlider(tab, 0.0, 1.0, self.settings.get("tts_volume", 0.8), width=380)
        self.volume_slider.pack(pady=T.S1)

    def _build_body_tab(self, tab):
        self._section_label(tab, "Modelo VRM")
        self._path_entry_with_browse(tab, "Arquivo .vrm", "vrm_model_path", [("Modelo VRM", "*.vrm")])
        self._section_label(tab, "Transparência do corpo")
        self.transparency_slider = GlowSlider(tab, 0.1, 1.0, self.settings.get("body_transparency", 1.0), width=380)
        self.transparency_slider.pack(pady=T.S1)
        self._section_label(tab, "Pasta de criações da IA")
        self._path_entry_with_browse(tab, "Pasta de saída (vazio = padrão)", "output_folder", [], dialog_kind="dir")

    def _build_appearance_tab(self, tab):
        self._section_label(tab, "Papel de parede do chat")
        self._hint(tab, "Uma imagem de fundo pro chat. Ela é escurecida automaticamente pra o texto continuar legível.")
        self._path_entry_with_browse(tab, "Imagem de fundo", "chat_wallpaper_path",
                                      [("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp")])
        ctk.CTkButton(tab, text="Remover papel de parede", fg_color=T.BG_SURFACE_2, hover_color=T.RED,
                      text_color=T.TEXT_PRIMARY, font=safe_font(self, T.FONT_FAMILY, 11),
                      command=lambda: (self._fields["chat_wallpaper_path"].delete(0, "end"))
                      ).pack(anchor="w", pady=(T.S2, 0))

    def _build_system_tab(self, tab):
        self._section_label(tab, "Corpo (Godot)")
        self._hint(tab, "Aponte pro executável exportado do Corpo (ex: Zenith.exe), ou pro godot.exe "
                        "do motor — nesse caso, informe também a pasta do projeto abaixo.")
        self._path_entry_with_browse(tab, "Executável do Godot", "godot_executable_path",
                                      [("Executável", "*.exe"), ("Todos", "*.*")])
        self._path_entry_with_browse(tab, "Pasta do projeto (só se usar godot.exe do motor)",
                                      "godot_project_path", [], dialog_kind="dir")
        self.auto_launch_toggle = SegmentedToggle(tab, ["desligado", "ligado"], width=200,
                                                    value="ligado" if self.settings.get("auto_launch_godot", True) else "desligado")
        ctk.CTkLabel(tab, text="Abrir o Corpo automaticamente junto com a Central de Controle",
                     text_color=T.TEXT_PRIMARY, anchor="w",
                     font=safe_font(self, T.FONT_FAMILY, 12)).pack(fill="x", pady=(T.S3, T.S1))
        self.auto_launch_toggle.pack(anchor="w")

    def _build_permissions_tab(self, tab):
        self._section_label(tab, "O que a IA pode fazer sem perguntar")
        self._hint(tab, "\"Rodar código\" e \"Terminal\" recomendado sempre em \"ask\" — "
                        "é a base do Consentimento Soberano (Pilar 1).")
        self.perm_toggles = {}
        perms = self.settings.get("permissions", {})
        labels = {"screen": "Ver a tela", "microphone": "Usar microfone", "camera": "Usar câmera",
                  "run_code": "Rodar código Python", "terminal": "Rodar comandos de terminal",
                  "serial": "Conectar hardware (Arduino/ESP32)"}
        for key, label in labels.items():
            row = ctk.CTkFrame(tab, fg_color="transparent")
            row.pack(fill="x", pady=T.S2)
            ctk.CTkLabel(row, text=label, text_color=T.TEXT_PRIMARY, anchor="w",
                         font=safe_font(self, T.FONT_FAMILY, 12)).pack(side="left")
            toggle = SegmentedToggle(row, ["never", "ask", "always"],
                                      value=perms.get(key, "ask"), width=180)
            toggle.pack(side="right")
            self.perm_toggles[key] = toggle

    # ---- validação antes de salvar ----
    def _run_pre_save_checks(self, changes: dict) -> bool:
        """Confere texto de personalidade e caminhos de arquivo ANTES de
        aplicar. Não bloqueia sozinho — avisa e deixa o usuário decidir,
        mas o zenith_core filtra de novo de qualquer forma (determinístico)."""
        warnings = []
        for key, label in (("persona_description", "Personalidade"), ("user_pillars", "Pilares extras")):
            hits = scan_persona_text(changes.get(key, ""))
            if hits:
                warnings.append(f"• {label}: parece uma tentativa de remover as proteções de segurança "
                                 f"(trecho: \"{hits[0]}\"). Isso será filtrado automaticamente mesmo se você continuar.")

        path_checks = [("vrm_model_path", "vrm"), ("chat_wallpaper_path", "image"),
                       ("rvc_model_path", "rvc_model"), ("rvc_index_path", "rvc_index")]
        for key, kind in path_checks:
            ok, motivo = validate_path(changes.get(key, ""), kind)
            if not ok:
                warnings.append(f"• {key}: {motivo}")

        if warnings:
            return messagebox.askyesno(
                "Zenith — Conteúdo suspeito detectado",
                "Antes de salvar, encontrei isto:\n\n" + "\n\n".join(warnings) +
                "\n\nQuer salvar mesmo assim?"
            )
        return True

    # ---- salvar ----
    def _save(self):
        changes = {k: entry.get() for k, entry in self._fields.items()}
        changes["persona_description"] = self.persona_box.get("1.0", "end").strip()
        changes["user_pillars"] = self.pillars_box.get("1.0", "end").strip()
        changes["active_ai"] = self.active_ai_toggle.value
        changes["tts_volume"] = round(self.volume_slider.get(), 2)
        changes["body_transparency"] = round(self.transparency_slider.get(), 2)
        changes["auto_launch_godot"] = (self.auto_launch_toggle.value == "ligado")
        changes["permissions"] = {k: t.value for k, t in self.perm_toggles.items()}

        if not self._run_pre_save_checks(changes):
            return

        self.on_save(changes)
        self.destroy()


def run():
    app = ZenithApp()
    app.mainloop()


if __name__ == "__main__":
    run()
