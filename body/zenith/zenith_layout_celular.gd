extends RefCounted
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  zenith_layout_celular.gd — v1.12 (port celular), FASE 1: a interface em pé, com o avatar sempre visível em cima.
#
#  No PC o Zenith tem DUAS janelas (o avatar, flutuando; e a interface, grande). No celular só existe UMA tela: o
#  avatar fica numa FAIXA no alto e a interface ocupa o resto, embaixo. Este script só liga quando é Android (ou com
#  --layout-celular no PC, para teste) — no PC normal ele não faz nada, então o Zenith do PC fica igual.
#
#  O que a fase 1 faz:  (1) coloca a janela da interface embaixo da faixa do avatar;  (2) esconde o que só existe no
#  PC (botão de mover janela);  (3) transforma a barra lateral numa GAVETA aberta pelo botão ☰ da barra de cima;
#  (4) tira "Parar"/"Parar observação"/atividade da barra de cima e os põe numa faixa própria (cabem em 390 px).
#  FASE 2 (v1.13): os cartões de PC viram TELAS CHEIAS (Configurações, Memórias, Biblioteca) ou DIÁLOGOS LARGOS (aprovação
#  de ações, primeiro uso). As Configurações ganham navegação de celular: lista de seções -> seção em tela cheia, com ‹ voltar.
#  FASE 3 (v1.14): o avatar 3D é ENQUADRADO na faixa de cima (a câmera recua e sobe; fórmula calibrada), o TECLADO VIRTUAL
#  empurra a interface para cima, e o botão/gesto VOLTAR do Android fecha gaveta -> seção -> tela, sem fechar o app.
#  Tudo isto só foi visto no Godot de PC; o teclado e o 'voltar' de verdade só existem no aparelho.
#
#  Carregado pela ui_manager com load() CONFERIDO (nunca preload): se este arquivo falhar, a interface abre como no PC.
#  Argumentos de teste (depois do "--"):  --layout-celular   --celular-tela=390x844   --visual-gaveta   --visual-atividade
#                                     --visual-memorias   --visual-aprovacao   --celular-teclado=330   --visual-voltar   --visual-modelo=63   (e o já existente --visual-abrir=Voz)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════

const FRACAO_AVATAR := 0.34        # a faixa do avatar ocupa ~1/3 da altura
const AVATAR_MIN := 160            # ...mas nunca menos que isto (px)
const GAVETA_MAX := 300            # largura máxima da gaveta (px); em tela estreita é 82% da largura
const ALVO_TOQUE := 44             # tamanho mínimo de um botão para o dedo (px)

var ui = null                      # a janela da interface (ui_manager.gd). Sem tipo de propósito: o acesso é dinâmico.
var tela := Vector2i(420, 840)
var fracao_avatar: float = 0.35    # proporção da tela dedicada ao avatar (0.22, 0.35, 0.50, 0.65)
var faixa_avatar := 0              # altura (px) da faixa do avatar, no alto
var gaveta: Control = null
var _escurecer: ColorRect = null
var modo_layout: String = "flutuante" # "flutuante" (janela móvel) | "corpo_todo" (corpo cheio 3D) | "chat" (100% chat) | "topo" (faixa)
var modo_avatar: String = "busto"    # mantido para compatibilidade
var maximizado: bool = false         # true se o avatar está maximizado
var _btn_modo_ref: Button = null
var _btn_max_ref: Button = null
var _cam_pos_base: Vector3 = Vector3.ZERO
var _menu_btn: Button = null

# Janela Flutuante Móvel (PiP) e Giro 3D
var _card_movel: PanelContainer = null
var _textura_avatar: TextureRect = null
var _bolha_avatar: Button = null
var _arraste_card: bool = false
var _pos_toque_card: Vector2 = Vector2.ZERO
var _arraste_giro: bool = false
var _pos_toque_giro: Vector2 = Vector2.ZERO
var _pos_card_flutuante: Vector2 = Vector2(-1, -1)

func ativo() -> bool:
	if OS.get_name() == "Android":
		return true
	return OS.get_cmdline_user_args().has("--layout-celular")

# Tamanho LÓGICO do canvas do Godot (coordenadas do Viewport, compatível com stretch mode canvas_items)
func _tamanho_da_tela() -> Vector2i:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--celular-tela="):
			var p = a.get_slice("=", 1).split("x")
			if p.size() == 2 and int(p[0]) > 0 and int(p[1]) > 0:
				return Vector2i(int(p[0]), int(p[1]))
	if ui != null and is_instance_valid(ui) and ui.get_tree() and ui.get_tree().root:
		var vis: Vector2 = ui.get_tree().root.get_visible_rect().size
		if vis.x > 0 and vis.y > 0:
			return Vector2i(int(round(vis.x)), int(round(vis.y)))
	if OS.get_name() == "Android":
		var wsz = DisplayServer.window_get_size(0)
		var wf = maxf(1.0, float(wsz.x))
		var hf = maxf(1.0, float(wsz.y))
		# Se o Android escalou com base no viewport de 420:
		var log_w = 420
		var log_h = int(round(420.0 * (hf / wf)))
		return Vector2i(log_w, log_h)
	return Vector2i(420, 840)

# Quanto da borda de baixo o sistema ocupa (barra de gestos). Convertido para escala lógica.
func _margem_baixo() -> int:
	var pad_min := 14
	if OS.get_name() != "Android":
		return pad_min
	var seguro: Rect2i = DisplayServer.get_display_safe_area()
	var wsz = DisplayServer.window_get_size(0)
	if seguro.size.y <= 0 or wsz.y <= 0:
		return pad_min
	var sobra_px = maxi(0, wsz.y - (seguro.position.y + seguro.size.y))
	var escala = float(tela.y) / float(wsz.y)
	return maxi(pad_min, int(round(float(sobra_px) * escala)))

# Chamado pela ui_manager NA HORA (antes do aplicar() adiado): textos e botões criados depois (listas, avisos) também são
# ajustados. Se ligasse só no aplicar(), um cartão aberto antes dele (ex.: nos testes) escaparia.
func ligar_observador() -> void:
	if ui != null and not ui.get_tree().node_added.is_connected(_ao_entrar_no):
		ui.get_tree().node_added.connect(_ao_entrar_no)

func aplicar(janela) -> void:
	ui = janela
	if ui == null or not is_instance_valid(ui):
		return
	tela = _tamanho_da_tela()
	faixa_avatar = maxi(AVATAR_MIN, int(tela.y * fracao_avatar))
	_posicionar_janela()
	_esconder_o_que_e_de_pc()
	_montar_gaveta()
	_montar_card_flutuante.call_deferred()
	_configurar_toque_3d.call_deferred()
	_enquadrar_avatar.call_deferred()
	_iniciar_teclado()
	_ligar_voltar()
	if ui and ui.get_tree() and ui.get_tree().root:
		if not ui.get_tree().root.size_changed.is_connected(_ao_tamanho_mudou):
			ui.get_tree().root.size_changed.connect(_ao_tamanho_mudou)
	if OS.get_cmdline_user_args().has("--visual-voltar"):        # teste: simula o botão voltar duas vezes (seção -> lista -> fecha)
		ui.get_tree().create_timer(2.0).timeout.connect(func():
			voltar()
			print("VOLTAR 1: lista visível=", _lista_cfg != null and _lista_cfg.visible, " configurações visíveis=", ui.settings_overlay.visible))
		ui.get_tree().create_timer(3.0).timeout.connect(func():
			voltar()
			ui.get_tree().create_timer(1.0).timeout.connect(func():           # o fechar tem animação: confere depois dela
				print("VOLTAR 2: configurações visíveis=", ui.settings_overlay.visible)))
	if OS.get_cmdline_user_args().has("--visual-atividade"):     # teste: mostra os botões que aparecem durante o uso
		ui.atividade_lbl.text = "Pesquisando na web..."
		ui.atividade_lbl.visible = true
		ui.parar_btn.visible = true
		ui.obs_btn.visible = true
	if OS.get_cmdline_user_args().has("--visual-gaveta"):
		abrir_gaveta.call_deferred()
	if OS.get_cmdline_user_args().has("--visual-memorias"):
		ui._show_overlay.call_deferred(ui.memories_overlay, ui.memories_card)
	if OS.get_cmdline_user_args().has("--visual-aprovacao"):     # teste: uma aprovação de mentira, como o Cérebro mandaria
		ui._on_approval_request.call_deferred("teste-1", "run_code", "Rodar o programa jogo_da_velha.py", "print('olá')")

func _ao_tamanho_mudou() -> void:
	tela = _tamanho_da_tela()
	faixa_avatar = maxi(AVATAR_MIN, int(tela.y * fracao_avatar))
	_posicionar_janela()
	_enquadrar_avatar()

func alternar_modo_layout() -> void:
	match modo_layout:
		"flutuante":
			modo_layout = "corpo_todo"
		"corpo_todo":
			modo_layout = "chat"
		"chat":
			modo_layout = "topo"
		"topo":
			modo_layout = "flutuante"
		_:
			modo_layout = "flutuante"
	_atualizar_botoes_modo()
	_posicionar_janela()
	_enquadrar_avatar()

func alternar_modo_avatar() -> void:
	alternar_modo_layout()

func maximizar_avatar() -> void:
	if modo_layout == "corpo_todo":
		modo_layout = "flutuante"
	else:
		modo_layout = "corpo_todo"
	_atualizar_botoes_modo()
	_posicionar_janela()
	_enquadrar_avatar()

func _atualizar_botoes_modo() -> void:
	if _btn_modo_ref != null and is_instance_valid(_btn_modo_ref):
		match modo_layout:
			"flutuante":
				_btn_modo_ref.text = "📱 Flutuante"
				_btn_modo_ref.tooltip_text = "Modo: Janela Flutuante Móvel (mova com o dedo). Toque para alternar."
			"corpo_todo":
				_btn_modo_ref.text = "🧍 Corpo Cheio"
				_btn_modo_ref.tooltip_text = "Modo: Corpo Cheio 3D (dos pés à cabeça). Toque para alternar."
			"chat":
				_btn_modo_ref.text = "💬 Só Chat"
				_btn_modo_ref.tooltip_text = "Modo: 100% Chat (estilo Claude / ChatGPT). Toque para alternar."
			"topo":
				_btn_modo_ref.text = "🔲 No Topo"
				_btn_modo_ref.tooltip_text = "Modo: Fixado no Topo. Toque para alternar."

func _posicionar_janela() -> void:
	if ui == null or not is_instance_valid(ui):
		return
	if ui.has_method("_clamp_no_monitor") and ui.size_changed.is_connected(ui._clamp_no_monitor):
		ui.size_changed.disconnect(ui._clamp_no_monitor)
	ui.borderless = true
	ui.unresizable = true
	ui.min_size = Vector2i(180, 180)
	var teclado: int = maxi(0, _teclado_px)
	
	match modo_layout:
		"flutuante":
			# Modo Janela Flutuante Móvel: Chat em tela cheia (como Claude / ChatGPT)
			# O avatar flutua transparente por cima do chat e pode ser movido para qualquer lugar!
			ui.position = Vector2i(0, 0)
			ui.size = Vector2i(tela.x, tela.y - _margem_baixo() - teclado)
			if _card_movel != null and is_instance_valid(_card_movel):
				_card_movel.visible = true
			if _bolha_avatar != null and is_instance_valid(_bolha_avatar):
				_bolha_avatar.visible = false
		"corpo_todo":
			# Modo Corpo Cheio: Avatar 3D em tamanho gigante da cabeça aos pés!
			var alt_chat = mini(250, int(tela.y * 0.38))
			var base = tela.y - _margem_baixo() - teclado
			ui.position = Vector2i(0, maxi(0, base - alt_chat))
			ui.size = Vector2i(tela.x, alt_chat)
			if _card_movel != null and is_instance_valid(_card_movel):
				_card_movel.visible = false
			if _bolha_avatar != null and is_instance_valid(_bolha_avatar):
				_bolha_avatar.visible = false
		"chat":
			# Modo 100% Chat: Tela cheia limpa, avatar recolhido em bolha discreta
			ui.position = Vector2i(0, 0)
			ui.size = Vector2i(tela.x, tela.y - _margem_baixo() - teclado)
			if _card_movel != null and is_instance_valid(_card_movel):
				_card_movel.visible = false
			if _bolha_avatar != null and is_instance_valid(_bolha_avatar):
				_bolha_avatar.visible = true
		"topo":
			# Modo Dividido no Topo: 34% avatar, 66% chat
			var alt_topo = int(tela.y * 0.34) if teclado == 0 else mini(int(tela.y * 0.34), FAIXA_COM_TECLADO)
			var base_t = tela.y - _margem_baixo() - teclado
			ui.size = Vector2i(tela.x, maxi(180, base_t - alt_topo))
			ui.position = Vector2i(0, maxi(0, base_t - ui.size.y))
			if _card_movel != null and is_instance_valid(_card_movel):
				_card_movel.visible = false
			if _bolha_avatar != null and is_instance_valid(_bolha_avatar):
				_bolha_avatar.visible = false

func _estilizar_botao_topo(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.14, 0.16, 0.22, 0.85)
	sb.border_color = Color(0.28, 0.32, 0.42, 0.70)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(8)
	sb.content_margin_left = 6
	sb.content_margin_right = 6
	sb.content_margin_top = 4
	sb.content_margin_bottom = 4
	var sb_hover := sb.duplicate()
	sb_hover.bg_color = Color(0.20, 0.24, 0.32, 0.95)
	sb_hover.border_color = Color(0.40, 0.45, 0.60, 0.90)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_stylebox_override("hover", sb_hover)
	btn.add_theme_stylebox_override("pressed", sb_hover)
	btn.add_theme_stylebox_override("focus", sb)
	btn.add_theme_color_override("font_color", Color(0.92, 0.93, 0.96))

func _esconder_o_que_e_de_pc() -> void:
	if ui.get("move_btn") != null:
		ui.move_btn.visible = false          # "mover a janela do avatar": só faz sentido com duas janelas
	if ui.get("_btn_atualizar") != null:
		ui._btn_atualizar.visible = false
	if ui.get("quick_ai_selector") != null:
		ui.quick_ai_selector.visible = false # economiza 150px de largura que estourariam a tela do celular
	var titulo = ui.get("title_label")
	if titulo != null:
		titulo.custom_minimum_size.x = 0
		titulo.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		titulo.clip_text = true
		titulo.add_theme_font_size_override("font_size", 16)
		
		# Botão seletor de modo do avatar (Flutuante Móvel / Corpo Cheio / Só Chat / No Topo)
		var btn_modo := Button.new()
		btn_modo.text = "📱 Flutuante"
		btn_modo.tooltip_text = "Alternar modo: Flutuante Móvel -> Corpo Cheio -> Só Chat -> No Topo"
		btn_modo.focus_mode = Control.FOCUS_NONE
		btn_modo.custom_minimum_size = Vector2(96, 34)
		btn_modo.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		btn_modo.add_theme_font_size_override("font_size", 12)
		_estilizar_botao_topo(btn_modo)
		btn_modo.pressed.connect(alternar_modo_layout)
		_btn_modo_ref = btn_modo
		titulo.get_parent().add_child(btn_modo)
		
		for c in titulo.get_parent().get_children():
			if c.get_class() == "Control" and c != titulo and c != _menu_btn and c != btn_modo and c != ui.get("status_dot"):
				c.visible = false
	_montar_faixa_de_atividade()

# "Parar", "Parar observação" e a linha "o que ela está fazendo" aparecem durante o uso e somam ~500 px: não cabem
# na barra de cima de 390 px. O "Parar" é trava de segurança (Pilar 1: sempre à mão), então ganha uma FAIXA PRÓPRIA logo
# abaixo da barra. Quem liga/desliga esses botões continua sendo a ui_manager (eles só mudam de lugar); com todos
# escondidos a faixa tem altura zero.
func _montar_faixa_de_atividade() -> void:
	var titulo = ui.get("title_label")
	if titulo == null:
		return
	var barra: Node = titulo.get_parent().get_parent().get_parent()
	var coluna: Node = barra.get_parent()
	var faixa := HBoxContainer.new()
	faixa.add_theme_constant_override("separation", 8)
	coluna.add_child(faixa)
	coluna.move_child(faixa, barra.get_index() + 1)
	
	var ativ = ui.get("atividade_lbl")
	if ativ != null:
		ativ.reparent(faixa, false)
		ativ.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		ativ.add_theme_font_size_override("font_size", 12)
		ativ.add_theme_color_override("font_color", Color(0.75, 0.80, 0.90))
	
	var parar = ui.get("parar_btn")
	if parar != null:
		parar.reparent(faixa, false)
		parar.text = "⏹ Parar"
		parar.custom_minimum_size = Vector2(74, 26)
		parar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		parar.add_theme_font_size_override("font_size", 11)
		_estilizar_botao_topo(parar)
	
	var obs = ui.get("obs_btn")
	if obs != null:
		obs.reparent(faixa, false)
		obs.custom_minimum_size = Vector2(74, 26)
		obs.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		obs.add_theme_font_size_override("font_size", 11)
		_estilizar_botao_topo(obs)

# Uma linha horizontal com margem de 4 px à esquerda (+8 de separação). Os espaçadores têm altura ZERO: com os botões
# escondidos a linha inteira some, sem deixar um vão.
func _linha_com_margem() -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	var esq := Control.new()
	esq.custom_minimum_size = Vector2(4, 0)
	h.add_child(esq)
	return h

# ---------- gaveta (a barra lateral) ----------
func _montar_gaveta() -> void:
	var raiz: Control = ui.get("_raiz_ui")
	var barra = ui.get("sidebar")
	if raiz == null or barra == null:
		push_warning("[Zenith/Celular] Barra lateral não encontrada; a gaveta não foi montada.")
		return
	var painel: Control = barra.get_parent().get_parent()       # PanelContainer > MarginContainer > VBox (sidebar)
	var linha_principal: Node = painel.get_parent()              # o HBox que hoje divide a tela entre barra lateral e chat
	painel.reparent(raiz, false)                                 # sai do HBox: deixa de dividir a tela com o chat
	var largura: int = mini(GAVETA_MAX, int(tela.x * 0.82))
	painel.custom_minimum_size.x = largura
	painel.set_anchors_and_offsets_preset(Control.PRESET_LEFT_WIDE, Control.PRESET_MODE_MINSIZE)
	painel.visible = false
	gaveta = painel

	_escurecer = ColorRect.new()
	_escurecer.color = Color(0, 0, 0, 0.55)
	_escurecer.set_anchors_preset(Control.PRESET_FULL_RECT)
	_escurecer.mouse_filter = Control.MOUSE_FILTER_STOP
	_escurecer.visible = false
	_escurecer.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed:
			fechar_gaveta())
	raiz.add_child(_escurecer)
	# Camadas: logo DEPOIS do HBox principal (por cima do chat) e ANTES das telas cheias (Configurações etc.).
	# Não dá para usar números fixos: o sistema de aparência põe camadas de efeito no meio dos filhos da raiz
	# (foi o erro da 1ª versão: a gaveta ficava desenhada por baixo do chat — achado no teste com o Godot).
	var acima: int = linha_principal.get_index() + 1
	raiz.move_child(_escurecer, acima)
	raiz.move_child(painel, acima + 1)

	_montar_botao_menu()
	# qualquer botão tocado dentro da gaveta (nova conversa, uma conversa, Memórias, Configurações...) fecha a gaveta
	_ligar_fechamento(painel)
	ui.get_tree().node_added.connect(func(no): if gaveta != null and gaveta.is_ancestor_of(no): _ligar_fechamento(no))

func _montar_botao_menu() -> void:
	var titulo = ui.get("title_label")
	if titulo == null:
		return
	var linha: Node = titulo.get_parent()                        # o HBox da barra de cima
	_menu_btn = Button.new()
	_menu_btn.flat = true
	_menu_btn.icon = _icone_menu(Color(0.93, 0.93, 0.95))
	_menu_btn.custom_minimum_size = Vector2(ALVO_TOQUE, ALVO_TOQUE)
	_menu_btn.focus_mode = Control.FOCUS_NONE
	_menu_btn.tooltip_text = "Conversas"
	_menu_btn.pressed.connect(abrir_gaveta)
	linha.add_child(_menu_btn)
	linha.move_child(_menu_btn, 0)

# Três tracinhos desenhados em código (não depende de fonte nem de arquivo de imagem).
func _icone_menu(cor: Color) -> Texture2D:
	var img := Image.create(24, 24, false, Image.FORMAT_RGBA8)
	for y in [6, 11, 16]:
		for dy in 2:
			for x in range(4, 20):
				img.set_pixel(x, y + dy, cor)
	return ImageTexture.create_from_image(img)

func _ligar_fechamento(no: Node) -> void:
	if no is Button and not no.pressed.is_connected(_fechar_depois):
		no.pressed.connect(_fechar_depois)
	for filho in no.get_children():
		_ligar_fechamento(filho)

func _fechar_depois() -> void:
	fechar_gaveta.call_deferred()      # deixa o botão fazer o que faz primeiro; só depois a gaveta some

func abrir_gaveta() -> void:
	if gaveta == null:
		return
	_escurecer.visible = true
	gaveta.visible = true

func fechar_gaveta() -> void:
	if gaveta == null:
		return
	gaveta.visible = false
	_escurecer.visible = false

# ═══════════════════════ FASE 2: cartões viram telas ═══════════════════════
# Chamado pela ui_manager ANTES de mostrar qualquer cartão (_show_overlay). Cartões que o PC desenha como janelinha em
# porcentagem da tela viram: tela cheia (Configurações, Memórias, Biblioteca) ou diálogo largo (aprovação, primeiro uso).
# O avatar continua visível: a interface é uma janela só da parte de baixo, a faixa de cima não é tocada.
func preparar_cartao(card: Control) -> void:
	if ui == null or card == null or not is_instance_valid(card):
		return
	if card == ui.get("settings_card"):
		_montar_navegacao_configuracoes()
	var cheia: bool = card == ui.get("settings_card") or card == ui.get("memories_card") or card == ui.get("projetos_card")
	var dialogo: bool = card == ui.get("approval_card") or card == ui.get("onboarding_card")
	if not cheia and not dialogo:
		return                                   # ex.: o cartão de "carregando avatar" tem tamanho próprio: não mexe
	_quebrar_textos(card)
	if cheia:
		card.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		var caixa = card.get_theme_stylebox("panel")
		if caixa is StyleBoxFlat:                # sem cantos arredondados nem borda: é uma tela, não uma janelinha
			var nova: StyleBoxFlat = caixa.duplicate()
			nova.set_corner_radius_all(0)
			nova.set_border_width_all(0)
			card.add_theme_stylebox_override("panel", nova)
	else:
		_alvos_de_toque(card)                    # "Aprovar"/"Negar" são trava de segurança: têm de ser fáceis de acertar com o dedo
		card.anchor_left = 0.04
		card.anchor_right = 0.96
		card.anchor_top = 0.10
		card.anchor_bottom = 0.90
		card.offset_left = 0
		card.offset_right = 0
		card.offset_top = 0
		card.offset_bottom = 0

func _alvos_de_toque(no: Node) -> void:
	if no is Button:
		no.custom_minimum_size.y = maxf(no.custom_minimum_size.y, 48.0)
	for filho in no.get_children():
		_alvos_de_toque(filho)

# ---------- Configurações: lista de seções -> seção em tela cheia ----------
const LEGENDAS := {
	"Identidade": "Nome, personalidade e chat",
	"Voz": "Falar e escutar",
	"Corpo / VRM": "Avatar, ajuste e vida",
	"Aparência": "Fundo do chat",
	"Estúdio": "Temas, cores e efeitos",
	"Chaves & IAs": "IAs que respondem e suas chaves",
	"Permissões": "O que ela pode fazer",
	"Sobre": "Versão, diagnóstico e créditos",
}
var _nav_pronta := false
var _navegando := false
var _abas: TabContainer = null
var _lista_cfg: Control = null
var _voltar_cfg: Button = null
var _titulo_cfg: Label = null
var _salvar_cfg: Control = null
var _aba_ao_fechar := 0

func _montar_navegacao_configuracoes() -> void:
	if _nav_pronta:
		return
	_abas = ui.get("settings_tabs")
	if _abas == null:
		return
	_nav_pronta = true
	var coluna: Node = _abas.get_parent()                       # VBox: cabeçalho, abas, botão "Salvar e Aplicar"
	var cabecalho: Node = coluna.get_child(0)                   # HBox: título + ✕
	_titulo_cfg = cabecalho.get_child(0)
	_salvar_cfg = coluna.get_child(coluna.get_child_count() - 1)
	_voltar_cfg = Button.new()
	_voltar_cfg.flat = true
	_voltar_cfg.icon = _icone_seta(true, Color(0.93, 0.93, 0.95))
	_voltar_cfg.custom_minimum_size = Vector2(ALVO_TOQUE, ALVO_TOQUE)
	_voltar_cfg.focus_mode = Control.FOCUS_NONE
	_voltar_cfg.tooltip_text = "Voltar às seções"
	_voltar_cfg.pressed.connect(_voltar_para_lista)
	cabecalho.add_child(_voltar_cfg)
	cabecalho.move_child(_voltar_cfg, 0)

	_abas.tabs_visible = false                                  # a barra de abas de PC não cabe: entra a lista
	var rolagem := ScrollContainer.new()
	rolagem.size_flags_vertical = Control.SIZE_EXPAND_FILL
	rolagem.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var itens := VBoxContainer.new()
	itens.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	itens.add_theme_constant_override("separation", 8)
	rolagem.add_child(itens)
	coluna.add_child(rolagem)
	coluna.move_child(rolagem, _abas.get_index() + 1)
	_lista_cfg = rolagem
	for i in _abas.get_tab_count():
		itens.add_child(_linha_de_secao(i, _abas.get_tab_title(i)))

	_abas.tab_changed.connect(func(i):                          # quem abre numa seção direto (ex.: atalho para Chaves)
		if not _navegando and ui.settings_overlay.visible:
			_abrir_secao(i))
	ui.settings_overlay.visibility_changed.connect(func():
		if ui.settings_overlay.visible:
			if _abas.current_tab != _aba_ao_fechar:
				_abrir_secao(_abas.current_tab)
			else:
				_voltar_para_lista()
		else:
			_aba_ao_fechar = _abas.current_tab)
	_voltar_para_lista()
	_montar_linha_modelo_de_voz()

func _linha_de_secao(indice: int, titulo: String) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(0, 64)
	b.focus_mode = Control.FOCUS_NONE
	b.pressed.connect(func(): _abrir_secao(indice))
	var margem := MarginContainer.new()
	margem.set_anchors_preset(Control.PRESET_FULL_RECT)
	margem.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for lado in ["left", "right", "top", "bottom"]:
		margem.add_theme_constant_override("margin_" + lado, 12 if lado in ["left", "right"] else 6)
	var linha := HBoxContainer.new()
	linha.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var textos := VBoxContainer.new()
	textos.alignment = BoxContainer.ALIGNMENT_CENTER
	textos.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	textos.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var t := Label.new()
	t.text = titulo
	t.add_theme_font_size_override("font_size", 16)
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var c := Label.new()
	c.text = LEGENDAS.get(titulo, "")
	c.add_theme_font_size_override("font_size", 12)
	c.modulate = Color(1, 1, 1, 0.65)                          # esmaecido: acompanha qualquer tema do Estúdio
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	textos.add_child(t)
	textos.add_child(c)
	var seta := TextureRect.new()
	seta.texture = _icone_seta(false, Color(0.93, 0.93, 0.95, 0.7))
	seta.stretch_mode = TextureRect.STRETCH_KEEP_CENTERED
	seta.mouse_filter = Control.MOUSE_FILTER_IGNORE
	linha.add_child(textos)
	linha.add_child(seta)
	margem.add_child(linha)
	b.add_child(margem)
	return b

func _abrir_secao(i: int) -> void:
	_navegando = true
	_abas.current_tab = i
	_abas.visible = true
	_lista_cfg.visible = false
	_titulo_cfg.text = _abas.get_tab_title(i)
	_voltar_cfg.visible = true
	_salvar_cfg.visible = true
	_navegando = false

func _voltar_para_lista() -> void:
	_abas.visible = false
	_lista_cfg.visible = true
	_titulo_cfg.text = "Configurações"
	_voltar_cfg.visible = false
	_salvar_cfg.visible = false                                 # "Salvar e Aplicar" só faz sentido dentro de uma seção

# Seta (‹ ou ›) desenhada em código: não depende de fonte nem de arquivo de imagem.
func _icone_seta(para_esquerda: bool, cor: Color) -> Texture2D:
	var img := Image.create(24, 24, false, Image.FORMAT_RGBA8)
	for t in 8:
		for grossura in 2:
			var x_topo: int = (15 - t) if para_esquerda else (8 + t)
			var x_base: int = (8 + t) if para_esquerda else (15 - t)
			img.set_pixel(x_topo + grossura, 5 + t, cor)
			img.set_pixel(x_base + grossura, 12 + t, cor)
	return ImageTexture.create_from_image(img)

# ---------- o que não cabe em 390 px: textos, botões, linhas e grades ----------
# No PC a janela é larga e cada coisa fica numa linha só. Em 390 px isso estoura a tela. Regras gerais (valem para as 8
# seções das Configurações, Memórias, Biblioteca, aprovação...), sem mexer na ui_manager:
# - Texto (Label): quebra linha, exceto o texto solto numa linha com botões (viraria uma coluna estreita).
# - Botão ou caixa de marcar de linha inteira (numa coluna): o texto desce para a linha de baixo.
# - Botão que já ocupa a folga de uma linha: corta com "…" se faltar espaço. Os outros não são tocados (cortar o texto
#   deles os faria sumir).
# - Grade (GridContainer) com mais de 2 colunas: passa a 2 (ex.: os 10 temas do Estúdio, 5 por linha, viram 2 por linha).
# - Linha (HBoxContainer) cujos componentes não cabem juntos: eles passam a quebrar para a linha de baixo. A linha
#   ORIGINAL continua no lugar (só ganha um filho, o "fluxo"), então qualquer código que a esconda/mostre segue valendo.
const CARTOES := ["settings_card", "memories_card", "projetos_card", "approval_card", "onboarding_card"]
const MARGEM_DO_CARTAO := 56      # margens internas do cartão + barra de rolagem (px)

func _largura_util() -> float:
	return float(ui.size.x - MARGEM_DO_CARTAO)

func _ajustar_um(no: Control) -> void:
	var ocupa_folga: bool = (no.size_flags_horizontal & Control.SIZE_EXPAND) != 0
	if no is Label:
		var em_linha_de_botoes: bool = no.get_parent() is HBoxContainer and not ocupa_folga
		if no.autowrap_mode == TextServer.AUTOWRAP_OFF and not em_linha_de_botoes:
			no.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			no.custom_minimum_size.x = 0
	elif no is Button and not (no is OptionButton):
		if no.autowrap_mode == TextServer.AUTOWRAP_OFF and no.get_parent() is VBoxContainer:
			no.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART      # botão/caixa de marcar de linha inteira: o texto desce
		elif ocupa_folga and not no.clip_text:
			no.clip_text = true
			no.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	elif no is GridContainer:
		if no.columns > 2:
			no.columns = 2
	elif no.get_class() == "HBoxContainer":
		_avaliar_linha.call_deferred(no)       # adiado: os filhos ainda estão sendo adicionados agora

# A largura mínima que a linha EXIGE de verdade. Um Label que quebra linha informa a largura do texto inteiro numa
# linha só (get_combined_minimum_size), mas na prática encolhe: conta como 80 px. Sem isso, "texto + seletor" parecia
# não caber e era convertido à toa (o texto ficava espremido numa coluna de letras).
func _largura_minima_real(linha: HBoxContainer, filhos: Array) -> float:
	var total: float = float(linha.get_theme_constant("separation")) * (filhos.size() - 1)
	for f in filhos:
		if f is Label and f.autowrap_mode != TextServer.AUTOWRAP_OFF:
			total += 80.0
		else:
			total += f.get_combined_minimum_size().x
	return total

func _avaliar_linha(linha: HBoxContainer) -> void:
	if not is_instance_valid(linha) or linha.has_meta("celular_fluxo"):
		return
	var filhos: Array = []
	for f in linha.get_children():
		if f is Control and f.visible:
			filhos.append(f)
	if filhos.size() < 2 or _largura_minima_real(linha, filhos) <= _largura_util():
		return
	var fluxo := HFlowContainer.new()
	fluxo.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	fluxo.add_theme_constant_override("h_separation", linha.get_theme_constant("separation"))
	fluxo.add_theme_constant_override("v_separation", 6)
	for f in linha.get_children():
		linha.remove_child(f)
		fluxo.add_child(f)
		if f is Control:
			f.size_flags_horizontal = Control.SIZE_FILL      # no fluxo cada um fica do seu tamanho; a folga não se reparte
			if f is Range or f is LineEdit or f is TextEdit:
				# controles SEM largura própria (barra de volume, campo de texto) sumiriam; ganham uma largura de uso.
				# (achado no print: o Volume virava só uma bolinha e o "Cole a chave" ficava com 8 letras de largura)
				f.custom_minimum_size.x = maxf(f.custom_minimum_size.x, 180.0)
	linha.set_meta("celular_fluxo", true)
	linha.add_child(fluxo)

func _quebrar_textos(no: Node) -> void:
	if no is Control:
		_ajustar_um(no)
	for filho in no.get_children():
		_quebrar_textos(filho)

func _ao_entrar_no(no: Node) -> void:
	if not (no is Label or no is Button or no is GridContainer or no is HBoxContainer):
		return
	for nome in CARTOES:
		var c = ui.get(nome)
		if c != null and is_instance_valid(c) and c.is_ancestor_of(no):
			_ajustar_um(no)
			return

# ═══════════════════════ FASE 3: avatar na faixa, teclado e "voltar" ═══════════════════════
# ---------- enquadrar o avatar na faixa de cima ----------
# A câmera do Corpo olha o busto do avatar e preenche a TELA INTEIRA (no PC a janela do avatar é pequena). No celular a
# interface cobre a parte de baixo; sobra a faixa de cima. A câmera RECUA (o avatar fica `faixa/altura` vezes menor, com
# a mesma perspectiva — mexer no FOV distorceria) e DESCE no próprio plano (o conteúdo sobe até o meio da faixa).
# Conferido numa cena de calibração com a mesma câmera: uma régua de 527 px virou 179 px (34%), com o centro em 141 px
# (meio da faixa de 286 px = 143). NÃO foi conferido com o avatar de verdade (aqui não há arquivo .vrm): se o
# enquadramento sair torto no aparelho, "Corpo / VRM > Ajustar arrastando" (já existe) corrige à mão.
var _camera_enquadrada := false

# Quanto mover a câmera (em coordenadas do mundo) para o avatar caber na faixa. `distancia_foco`: distância da câmera ao
# avatar medida ao longo do eixo de visão.
func deslocamento_da_camera(cam: Camera3D, distancia_foco: float, altura_tela: float, faixa: float) -> Vector3:
	var f: float = altura_tela / faixa                               # quantas vezes o avatar tem de ficar menor
	var recuo: Vector3 = cam.global_transform.basis.z * distancia_foco * (f - 1.0)
	var d2: float = distancia_foco * f                               # distância nova ao avatar
	var subir_px: float = (altura_tela - faixa) / 2.0                # do centro da tela ao centro da faixa
	var delta: float = subir_px / altura_tela * 2.0 * d2 * tan(deg_to_rad(cam.fov / 2.0))
	return recuo - cam.global_transform.basis.y * delta              # a câmera desce no plano: o conteúdo sobe

func _enquadrar_avatar() -> void:
	if ui == null:
		return
	var corpo = ui.get_parent()
	if corpo == null:
		return
	var cam = corpo.get_node_or_null("Camera3D")
	if not (cam is Camera3D):
		return
	if _cam_pos_base == Vector3.ZERO:
		_cam_pos_base = cam.global_position
	
	if modo_layout == "corpo_todo":
		# Modo Corpo Cheio: recua e abaixa para enquadrar dos pés à cabeça com amplitude!
		cam.global_position = Vector3(_cam_pos_base.x, 0.58, _cam_pos_base.z + 1.65)
		return
	
	if modo_layout == "flutuante":
		# Janela Móvel: foca perfeitamente no rosto e busto com detalhes nítidos
		cam.global_position = Vector3(_cam_pos_base.x, 1.05, _cam_pos_base.z + 0.35)
		return
	
	# Modo Busto / Faixa no Topo
	cam.global_position = _cam_pos_base
	var avatar = corpo.get_node_or_null("Akira")
	var ponto: Vector3 = cam.global_position - cam.global_transform.basis.z * 0.9
	if avatar is Node3D:
		ponto = avatar.global_position
		ponto.y = cam.global_position.y
	var d: float = clampf((ponto - cam.global_position).dot(-cam.global_transform.basis.z), 0.3, 6.0)
	
	if tela.x > tela.y:
		var delta_x: float = d * tan(deg_to_rad(cam.fov / 2.0)) * 0.65
		cam.global_position = _cam_pos_base + cam.global_transform.basis.x * delta_x
	else:
		var frac := 0.32 if modo_avatar == "busto" else 0.50
		cam.global_position = _cam_pos_base + deslocamento_da_camera(cam, d, float(tela.y), float(tela.y * frac))

# ---------- teclado virtual ----------
# Com o teclado aberto, a interface sobe para ficar acima dele (cobrindo parte da faixa do avatar, só enquanto se digita).
const FAIXA_COM_TECLADO := 120
var _teclado_px := -1

func _altura_do_teclado() -> int:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--celular-teclado="):                       # teste: simula o teclado no PC
			return int(a.get_slice("=", 1))
	if OS.get_name() == "Android":
		var h_raw = DisplayServer.virtual_keyboard_get_height()
		var wsz = DisplayServer.window_get_size(0)
		if wsz.y > 0 and h_raw > 0:
			var escala = float(tela.y) / float(wsz.y)
			return int(round(float(h_raw) * escala))
		return h_raw
	return 0

func _iniciar_teclado() -> void:
	var simulado := false
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--celular-teclado="):
			simulado = true
	if OS.get_name() != "Android" and not simulado:
		return
	_ciclo_teclado()

func _ciclo_teclado() -> void:
	if ui == null or not is_instance_valid(ui):
		return
	var h: int = _altura_do_teclado()
	if h != _teclado_px:
		_teclado_px = h
		_posicionar_janela()
	ui.get_tree().create_timer(0.15).timeout.connect(_ciclo_teclado)

# ---------- botão/gesto "voltar" do Android ----------
func _ligar_voltar() -> void:
	if OS.get_name() == "Android":
		if not ui.go_back_requested.is_connected(voltar):
			ui.go_back_requested.connect(voltar)
		var raiz: Window = ui.get_tree().root
		if not raiz.go_back_requested.is_connected(voltar):
			raiz.go_back_requested.connect(voltar)

# Voltar fecha UMA coisa por vez: gaveta -> (seção -> lista) -> tela. A aprovação de ação NÃO fecha com "voltar":
# negar ou aprovar tem de ser uma escolha explícita. Sem nada aberto, não faz nada (o app não fecha).
func voltar() -> void:
	if gaveta != null and gaveta.visible:
		fechar_gaveta()
		return
	var aprovacao = ui.get("approval_overlay")
	if aprovacao != null and aprovacao.visible:
		return
	if _nav_pronta and ui.settings_overlay.visible:
		if _abas.visible:
			_voltar_para_lista()
		else:
			_fechar_tela(ui.settings_overlay)
		return
	for nome in ["memories_overlay", "projetos_overlay"]:
		var ov = ui.get(nome)
		if ov != null and ov.visible:
			_fechar_tela(ov)
			return

func _fechar_tela(overlay: Control) -> void:
	if ui.has_method("_hide_overlay"):
		ui._hide_overlay(overlay)                 # a mesma saída do botão ✕/Fechar (com a animação de sempre)
	else:
		overlay.visible = false

# ═══════════════════════ Voz: baixar o modelo de fala em português ═══════════════════════
# Sem o modelo o Zenith FALA no celular mas NÃO ENTENDE o que a pessoa diz. O download (~50 MB) é feito pelo plugin Android
# (quem escreve na pasta do app); aqui só há o botão, a barra e a frase de estado. No PC o botão avisa que é coisa do celular.
var _modelo_estado: Label = null
var _modelo_barra: ProgressBar = null
var _modelo_botao: Button = null
var _ponte: Node = null

func _montar_linha_modelo_de_voz() -> void:
	var pagina: Node = null
	for i in _abas.get_tab_count():
		if _abas.get_tab_title(i) == "Voz":
			pagina = _abas.get_child(i)
	if pagina == null:
		return
	var conteudo = pagina.find_child("content", true, false)
	if not (conteudo is VBoxContainer):
		push_warning("[Zenith/Celular] Página de Voz sem a coluna 'content'; a linha do modelo de fala não foi criada.")
		return
	var titulo := Label.new()
	titulo.text = "Entender a fala (sem internet)"
	titulo.add_theme_color_override("font_color", Color(0.96, 0.64, 0.34))
	titulo.add_theme_font_size_override("font_size", 13)
	_modelo_estado = Label.new()
	_modelo_estado.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_modelo_estado.add_theme_font_size_override("font_size", 12)
	_modelo_barra = ProgressBar.new()
	_modelo_barra.custom_minimum_size = Vector2(0, 14)
	_modelo_barra.visible = false
	_modelo_botao = Button.new()
	_modelo_botao.custom_minimum_size = Vector2(0, 48)
	_modelo_botao.focus_mode = Control.FOCUS_NONE
	_modelo_botao.text = "Baixar modelo de português (~50 MB)"
	_modelo_botao.pressed.connect(_pedir_download_do_modelo)
	for c in [titulo, _modelo_estado, _modelo_barra, _modelo_botao]:
		conteudo.add_child(c)
	_ponte = ui.get_tree().root.find_child("PonteAndroid", true, false)
	if _ponte != null:
		_ponte.modelo_evento.connect(_ao_evento_do_modelo)
		_ponte.resposta_local.connect(_ao_resposta_local)
		_ponte.chamar_local("modelo.estado")
		_mostrar_modelo("Verificando se o modelo já está neste aparelho...", false, false)
	else:
		_mostrar_modelo("O modelo de fala só se instala no celular. Sem ele, o Zenith fala mas não entende o que você diz.", false, false)
		_modelo_botao.disabled = true
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--visual-modelo="):                    # teste: mostra a barra a N%
			_ao_evento_do_modelo("modelo.progresso", {"fase": "baixando", "pct": int(a.get_slice("=", 1))})
			ui.get_tree().create_timer(1.5).timeout.connect(func(): pagina.scroll_vertical = 100000)

func _mostrar_modelo(texto: String, barra: bool, botao: bool) -> void:
	_modelo_estado.text = texto
	_modelo_barra.visible = barra
	_modelo_botao.visible = botao

func _pedir_download_do_modelo() -> void:
	if _ponte == null:
		return
	_mostrar_modelo("Começando o download...", true, false)
	_modelo_barra.value = 0
	_ponte.chamar_local("modelo.baixar")

func _ao_resposta_local(id: String, dado) -> void:
	if id == "ui:modelo.estado" and dado is Dictionary:
		if dado.get("instalado", false):
			_mostrar_modelo("Instalado. O Zenith entende o que você diz, sem internet.", false, false)
		elif dado.get("baixando", false):
			_mostrar_modelo("Baixando...", true, false)
		else:
			_mostrar_modelo("Ainda não instalado. Sem o modelo o Zenith fala, mas não entende o que você diz.", false, true)
	elif id == "ui:modelo.baixar" and dado is Dictionary and not dado.get("ok", false):
		_mostrar_modelo(str(dado.get("erro", "Não consegui começar o download.")), false, true)

func _ao_evento_do_modelo(nome: String, dados: Dictionary) -> void:
	match nome:
		"modelo.progresso":
			var pct: int = int(dados.get("pct", -1))
			var instalando: bool = str(dados.get("fase", "")) == "instalando"
			_modelo_barra.visible = true
			_modelo_botao.visible = false
			_modelo_barra.value = 100 if (instalando or pct < 0) else pct
			_modelo_estado.text = "Instalando..." if instalando else ("Baixando... %d%%" % pct if pct >= 0 else "Baixando...")
		"modelo.pronto":
			_mostrar_modelo("Instalado. O Zenith entende o que você diz, sem internet.", false, false)
		"modelo.erro":
			_mostrar_modelo(str(dados.get("erro", "Não consegui baixar o modelo.")), false, true)

# ═══════════════════════ JANELA FLUTUANTE MÓVEL & GIRO 3D ═══════════════════════
func _montar_card_flutuante() -> void:
	var raiz: Control = ui.get("_raiz_ui")
	if raiz == null:
		return
	
	var card := PanelContainer.new()
	card.name = "CardVRMFlutuante"
	var larg := mini(170, int(tela.x * 0.42))
	var alt := mini(235, int(tela.y * 0.32))
	card.custom_minimum_size = Vector2(larg, alt)
	card.size = Vector2(larg, alt)
	if _pos_card_flutuante == Vector2(-1, -1):
		_pos_card_flutuante = Vector2(tela.x - larg - 12, 54)
	card.position = _pos_card_flutuante
	
	# Estilo translúcido elegante com cantos arredondados e borda ciano
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.11, 0.16, 0.82)
	sb.border_color = Color(0.25, 0.45, 0.70, 0.65)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(14)
	sb.shadow_color = Color(0, 0, 0, 0.45)
	sb.shadow_size = 8
	card.add_theme_stylebox_override("panel", sb)
	
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 2)
	card.add_child(vb)
	
	# Barra de arraste do card (header)
	var topo_card := HBoxContainer.new()
	topo_card.custom_minimum_size.y = 24
	topo_card.mouse_filter = Control.MOUSE_FILTER_PASS
	topo_card.gui_input.connect(_ao_gui_input_card)
	vb.add_child(topo_card)
	
	var alca := Label.new()
	alca.text = " ⋮⋮ Zenith 3D"
	alca.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	alca.add_theme_font_size_override("font_size", 10)
	alca.add_theme_color_override("font_color", Color(0.70, 0.80, 0.95))
	alca.mouse_filter = Control.MOUSE_FILTER_PASS
	topo_card.add_child(alca)
	
	# Botão resetar rotação para frente
	var btn_reset := Button.new()
	btn_reset.text = "↺"
	btn_reset.tooltip_text = "Centralizar avatar de frente"
	btn_reset.focus_mode = Control.FOCUS_NONE
	btn_reset.custom_minimum_size = Vector2(22, 20)
	btn_reset.add_theme_font_size_override("font_size", 10)
	_estilizar_botao_topo(btn_reset)
	btn_reset.pressed.connect(_resetar_giro_avatar)
	topo_card.add_child(btn_reset)
	
	# Botão minimizar
	var btn_min := Button.new()
	btn_min.text = "—"
	btn_min.tooltip_text = "Minimizar avatar"
	btn_min.focus_mode = Control.FOCUS_NONE
	btn_min.custom_minimum_size = Vector2(22, 20)
	btn_min.add_theme_font_size_override("font_size", 10)
	_estilizar_botao_topo(btn_min)
	btn_min.pressed.connect(func():
		card.visible = false
		if _bolha_avatar != null:
			_bolha_avatar.visible = true)
	topo_card.add_child(btn_min)
	
	# Textura do avatar com fundo transparente
	var tex_rect := TextureRect.new()
	tex_rect.name = "TexturaAvatar"
	tex_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tex_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	tex_rect.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tex_rect.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tex_rect.mouse_filter = Control.MOUSE_FILTER_STOP
	tex_rect.tooltip_text = "Arraste na horizontal para virar o avatar em 3D. Toque duplo centraliza."
	tex_rect.gui_input.connect(_ao_gui_input_giro)
	
	var corpo = ui.get_parent()
	if corpo != null and corpo.has_method("obter_textura_avatar"):
		tex_rect.texture = corpo.obter_textura_avatar()
	vb.add_child(tex_rect)
	_textura_avatar = tex_rect
	
	raiz.add_child(card)
	_card_movel = card
	
	# Bolha flutuante para reabrir quando minimizado
	var bolha := Button.new()
	bolha.text = "👤"
	bolha.tooltip_text = "Abrir avatar flutuante"
	bolha.focus_mode = Control.FOCUS_NONE
	bolha.custom_minimum_size = Vector2(38, 38)
	bolha.size = Vector2(38, 38)
	bolha.position = Vector2(tela.x - 50, 54)
	bolha.visible = false
	_estilizar_botao_topo(bolha)
	bolha.pressed.connect(func():
		bolha.visible = false
		card.visible = true)
	raiz.add_child(bolha)
	_bolha_avatar = bolha

func _ao_gui_input_card(ev: InputEvent) -> void:
	if ev is InputEventMouseButton:
		if ev.button_index == MOUSE_BUTTON_LEFT:
			_arraste_card = ev.pressed
			_pos_toque_card = ev.global_position
	elif ev is InputEventScreenTouch:
		_arraste_card = ev.pressed
		_pos_toque_card = ev.position
	elif (ev is InputEventMouseMotion or ev is InputEventScreenDrag) and _arraste_card:
		if _card_movel != null:
			var nova_pos = _card_movel.position + ev.relative
			nova_pos.x = clampf(nova_pos.x, 0.0, float(tela.x - _card_movel.size.x))
			nova_pos.y = clampf(nova_pos.y, 44.0, float(tela.y - _card_movel.size.y - 48))
			_card_movel.position = nova_pos
			_pos_card_flutuante = nova_pos

func _ao_gui_input_giro(ev: InputEvent) -> void:
	if ev is InputEventMouseButton:
		if ev.button_index == MOUSE_BUTTON_LEFT:
			_arraste_giro = ev.pressed
			_pos_toque_giro = ev.position
			if ev.double_click:
				_resetar_giro_avatar()
	elif ev is InputEventScreenTouch:
		_arraste_giro = ev.pressed
		_pos_toque_giro = ev.position
		if ev.double_tap:
			_resetar_giro_avatar()
	elif (ev is InputEventMouseMotion or ev is InputEventScreenDrag) and _arraste_giro:
		var dx = ev.relative.x
		_girar_avatar(dx * 0.015)

func _configurar_toque_3d() -> void:
	var corpo = ui.get_parent()
	if corpo == null:
		return
	var area = corpo.get_node_or_null("AreaToque3D")
	if area == null:
		area = Control.new()
		area.name = "AreaToque3D"
		area.set_anchors_preset(Control.PRESET_FULL_RECT)
		area.mouse_filter = Control.MOUSE_FILTER_PASS
		area.gui_input.connect(_ao_gui_input_giro)
		corpo.add_child(area)

func _girar_avatar(delta: float) -> void:
	if ui == null or not is_instance_valid(ui):
		return
	var corpo = ui.get_parent()
	if corpo == null:
		return
	var avatar = corpo.get_node_or_null("Akira")
	if avatar != null:
		avatar.rotation.y += delta

func _resetar_giro_avatar() -> void:
	if ui == null or not is_instance_valid(ui):
		return
	var corpo = ui.get_parent()
	if corpo == null:
		return
	var avatar = corpo.get_node_or_null("Akira")
	if avatar != null:
		avatar.rotation.y = 0.0
