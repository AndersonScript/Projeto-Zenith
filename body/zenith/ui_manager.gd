extends Window
# ============================================================
#  ZENITH — Criado por Anderson
#  ui_manager.gd — Central de Controle (janela separada, estrutura
#  igual à versão antiga que já funcionava: Corpo flutuante + Chat
#  numa janela própria), com tudo que construímos depois embutido:
#  barra lateral de conversas (fixar/apagar), configurações completas
#  com teste de chave de API, seletor de arquivo nativo, indicador de
#  digitando, e aprovação de ações — tudo isso o Python
#  (zenith_headless.py) não tinha antes.
# ============================================================

# ---------- Tema ----------
# v25 — as cores agora são VARIÁVEIS (com os mesmos nomes de antes): `_tema_carregar_local()` troca os valores logo no
# começo do _ready, ANTES de a interface ser montada. A paleta vem do /tema (Python) e fica em user://zenith_tema.cfg.
# v1.7 — NOVO DESIGN (a maquete aprovada): superfícies neutras e UMA cor de destaque (laranja). "CYAN" é só o nome antigo da variável.
var BG_BASE      = Color("0e0e12")
var BG_PANEL      = Color("15151a")
var BG_SURFACE    = Color("15151a")
var BG_SURFACE_2  = Color("1a1a21")
var BG_SURFACE_3  = Color("22222a")
var BORDER        = Color("24242c")
var CYAN          = Color("f5a257")
var CYAN_DIM      = Color("a35a12")
var MAGENTA       = Color("f472b6")
var GREEN         = Color("4cc38a")
var RED           = Color("f87171")
var TEXT_PRIMARY  = Color("ececf1")
var TEXT_SECOND   = Color("a0a0ac")
var TEXT_MUTED    = Color("8a8a96")
var BUBBLE_USER   = Color("22222a")
var BUBBLE_AI     = Color("0e0e12")
const TEMA_CFG := "user://zenith_tema.cfg"
const TEMA_CHAVES := ["BG_BASE", "BG_PANEL", "BG_SURFACE", "BG_SURFACE_2", "BG_SURFACE_3", "BORDER", "CYAN", "CYAN_DIM", "MAGENTA",
	"GREEN", "RED", "TEXT_PRIMARY", "TEXT_SECOND", "TEXT_MUTED", "BUBBLE_USER", "BUBBLE_AI"]

const SIDEBAR_WIDTH = 240
const Icones := preload("res://zenith_icones.gd")        # v1.1 — ícones próprios (sem emoji)
const Aparencia := preload("res://zenith_aparencia.gd")  # v1.1 — Estúdio de Aparência (efeitos e temas ao vivo)
var aparencia: Node
const Estudio := preload("res://zenith_estudio.gd")      # v1.1 — página "Estúdio" das Configurações
const ChavesPage := preload("res://zenith_chaves_page.gd")   # v1.1 — página "Chaves" (várias chaves por IA)
var chaves_page: RefCounted
const SaudePage := preload("res://zenith_saude_page.gd")     # v1.2 — "Saúde do Zenith" (Configurações → Sobre)
var saude_page: RefCounted
var desempenho_page: RefCounted
var email_page: RefCounted                                    # v1.20 — Ponte por E-mail (Celular <-> PC)                               # v1.11 (port celular) — tela de Desempenho (ver _montar_desempenho)
var layout_celular: RefCounted = null                         # v1.12 (port celular) — layout em pé (ver _aplicar_layout_celular)
const Cartoes := preload("res://zenith_cartoes.gd")          # v1.3 — cartões de atividade no chat
var cartoes: RefCounted
var settings_tabs: TabContainer

var brain: Node
var akira_body: Node   # referência direta pro Corpo (mesmo processo, janela irmã)
var moving_avatar: bool = false
var persona_name: String = "Zenith"

# Nós principais
var sidebar: VBoxContainer
var conv_list_box: VBoxContainer
var chat_scroll: ScrollContainer
var chat_log: VBoxContainer
var input_field: TextEdit        # v28: TextEdit (era LineEdit de uma linha só): cresce, quebra linha, Enter envia / Shift+Enter quebra
var mic_btn: Button
var _mic_listening: bool = false
var custom_endpoints_list: VBoxContainer   # (legado v18 — não é mais usado; a lista agora é a caixinha ai_edit_selector)

# v19 — painel "Minhas IAs e serviços", de uma IA por vez (ver _montar_editor_de_ias)
const AI_NEW_ID := "__novo__"           # item "＋ Adicionar nova IA…" da caixinha
var ai_entries: Array = []              # entradas que o Cérebro mandou (settings["_ai_ui"]["entradas"])
var ai_shortcuts: Array = []            # atalhos do catálogo opcional (vazio na cópia de distribuição)
var ai_edit_selector: OptionButton      # a caixinha "Configurar uma IA"
var ai_edit_ids: Array = []             # id de cada item da caixinha (AI_NEW_ID por último)
var ai_current_id: String = ""          # id da IA que está no painel agora
var ai_loading: bool = false            # true enquanto os campos são preenchidos por código
var ai_dirty: bool = false              # digitou algo e ainda não salvou
var ai_drafts: Dictionary = {}          # id -> campos digitados e não salvos (não perde ao trocar de IA)
var ai_panel_box: VBoxContainer
var ai_row_name: VBoxContainer
var ai_row_url: VBoxContainer
var ai_row_key: VBoxContainer
var ai_row_model: VBoxContainer
var ai_f_name: LineEdit
var ai_f_url: LineEdit
var ai_f_key: LineEdit
var ai_f_model: LineEdit
var ai_hint_lbl: Label
var ai_status_lbl: Label
var ai_btn_test: Button
var ai_btn_save: Button
var ai_btn_active: Button
var ai_btn_remove: Button
var ai_shortcuts_row: VBoxContainer
var ai_shortcuts_box: HFlowContainer
var _migracao_avatar_avisada: bool = false   # v19: a mensagem de migração aparecia 2x (settings_data chega 2x)
var status_dot: ColorRect
var status_label: Label
var move_btn: Button
var obs_btn: Button   # v23: aparece só enquanto ela observa a câmera/tela (🔴 Parar observação)
var atividade_lbl: Label   # v26: "o que ela está fazendo agora" (🧠 Pensando · 💻 Criando o programa · 🔊 Falando...) e fases do mic
var parar_btn: Button      # v26: ⏹ Parar — aparece enquanto há algo em andamento; manda /parar pro Cérebro
var _mic_fase_id: int = 0
var _dados_atualizacao: Dictionary = {}
var _btn_atualizar: Button = null  # v26: evita que o aviso "Entendi" de uma fala antiga apague o status de uma nova
# NOVO v10 — par do "Mover Zenith": em vez de digitar Deslocamento X/Y/Z/
# Escala em número, clica aqui e arrasta a Zenith / usa a roda do mouse.
# adjust_drag_btn e adjusting_by_drag seguem o mesmo padrão de move_btn/
# moving_avatar logo acima. offx/offy/offz/scale_mult_field eram
# variáveis locais de _settings_tab_body() antes — viraram membro da
# classe só pra _process() (novo, mais abaixo) conseguir atualizá-las ao
# vivo enquanto o Anderson arrasta; continuam sendo os MESMOS campos de
# sempre, só acessíveis de fora da função que os cria agora.
var adjust_drag_btn: Button
var adjusting_by_drag: bool = false
var offx: LineEdit
var offy: LineEdit
var offz: LineEdit
var scale_mult_field: LineEdit
var quick_ai_selector: OptionButton   # FEATURE: trocar de IA sem abrir Configurações
var wallpaper_rect: TextureRect       # FEATURE: imagem de fundo do chat
var wallpaper_video: VideoStreamPlayer # FEATURE: fundo animado (.ogv)
# v20 — fundo em QUADROS (vídeo/GIF de qualquer formato, convertido pelo Cérebro em JPEGs numa pasta)
var _wp_frames: Array = []             # caminhos dos quadros, em ordem
var _wp_frame_idx: int = 0
var _wp_frame_timer: Timer
var _wp_origem_pedida: String = ""
# v20 — "Resetar tudo" (aba Permissões)
var reset_confirm_field: LineEdit
var reset_btn: Button
var reset_status_lbl: Label
var reset_quit_btn: Button
var reset_cancel_btn: Button
var wallpaper_dim_rect: ColorRect     # FEATURE: escurecer o fundo pra manter o texto legível

var settings_overlay: Control
var settings_card: PanelContainer
var approval_overlay: Control
var onboarding_overlay: Control   # FEATURE (pen drive / primeiro login zerado)
var memories_overlay: Control     # FEATURE (painel "🧠 Memórias")
var approval_card: PanelContainer
var current_settings: Dictionary = {}
var settings_fields: Dictionary = {}
var api_test_status_labels: Dictionary = {}
var active_conv_id: String = ""
var _file_dialog: FileDialog
var _file_dialog_target_field: LineEdit

# v18 — a "biblioteca externa" (VRM carregado de fora, em tempo real) foi
# REMOVIDA: deformava cabelo/roupa. Existe UMA pasta só pra avatares,
# res://addons/avatars/, e o Python cuida de levar o .vrm até lá.
# v12 — lista de avatares que o GODOT importou (res://addons/avatars/):
# o caminho que renderiza certo, ver akira_body.gd::list_project_avatars().
var _project_avatar_list_box: VBoxContainer
# v13 — tela de carregamento dos avatares ("tela de download"): aparece ao
# abrir o app enquanto o Corpo pré-carrega/verifica os avatares do projeto,
# e ao adicionar um avatar novo (espera o Godot importar, depois verifica).
var avatar_loading_overlay: Control
var avatar_loading_card: Control
var avatar_loading_title: Label
var avatar_loading_bar: ProgressBar
var avatar_loading_status: Label
var avatar_loading_report: Label
var avatar_loading_close_btn: Button
var _avatar_ui_modo: String = ""        # "" | "preload" | "aguardando_import"
var _avatar_import_path: String = ""
var _avatar_import_timer: float = 0.0
# v15 — achado do teste real do Anderson: rodando pelo editor (F5), a
# Central e a janela do avatar são OUTRO PROCESSO que o editor em si —
# focar NELAS não conta como focar o EDITOR, e é só o foco do EDITOR que
# faz ele notar o arquivo novo. Sem isso a espera ficava num ciclo sem
# fim, sem explicar por quê. Agora a mensagem muda com o tempo e sempre
# tem uma saída manual.
var _avatar_import_elapsed: float = 0.0
var avatar_loading_manual_btn: Button
var _avatar_project_dialog: FileDialog
var title_label: Label


const DESIGN_V2_FLAG := "user://zenith_design_v2.flag"

func _tema_carregar_local():
	# v1.7 — o novo design vale UMA vez por cima do tema antigo salvo (senão quem já tinha tema continuava vendo o visual de antes).
	# Depois disso a escolha é da pessoa: Configurações > Estúdio muda o tema quando quiser.
	if not FileAccess.file_exists(DESIGN_V2_FLAG):
		var novo := ConfigFile.new()
		for k in TEMA_CHAVES:
			novo.set_value("cores", k, (get(k) as Color).to_html(false))
		novo.save(TEMA_CFG)
		var fl := FileAccess.open(DESIGN_V2_FLAG, FileAccess.WRITE)
		if fl != null:
			fl.store_string("1")
			fl.close()
	var cfg := ConfigFile.new()
	if cfg.load(TEMA_CFG) != OK:
		return
	for k in TEMA_CHAVES:
		if cfg.has_section_key("cores", k):
			set(k, Color.from_string(str(cfg.get_value("cores", k)), get(k)))

# v25 — o Cérebro mandou a paleta: guarda; vale na PRÓXIMA abertura (a interface é montada uma vez, ao iniciar).
func _on_ui_tema(paleta: Dictionary):
	var cfg := ConfigFile.new()
	var mudou := false
	var antigo := ConfigFile.new()
	antigo.load(TEMA_CFG)
	for k in TEMA_CHAVES:
		if paleta.has(k):
			var v := str(paleta[k])
			cfg.set_value("cores", k, v)
			if str(antigo.get_value("cores", k, "")) != v and Color.from_string(v, get(k)) != get(k):
				mudou = true
	cfg.save(TEMA_CFG)
	if mudou:
		_add_bubble("🎨 Tema novo salvo. Feche e abra o Zenith pra ver as cores.", "ai")

func _ready():
	_tema_carregar_local()   # v25: antes de montar qualquer botão/painel
	aparencia = Aparencia.new()   # v1.1: motor de aparência (precisa existir ANTES de montar as áreas)
	aparencia.name = "Aparencia"
	add_child(aparencia)
	aparencia.iniciar(self)
	cartoes = Cartoes.new()
	cartoes.iniciar(self)
	# CORREÇÃO: esta janela é filha do nó raiz (Node3D), que é quem
	# carrega akira_body.gd — então o Corpo é o PAI desta janela (não
	# um irmão chamado "ZenithBody", que nunca existiu).
	brain = get_node_or_null("../BrainConnector")
	akira_body = get_node_or_null("..")
	_connect_brain_signals()
	_build_root()
	_montar_camada_avisos()    # v28: avisos popup + barra de progresso (por cima de tudo)
	_iconizar_arvore(self)     # v1.1: emoji dos botões -> ícones próprios
	aparencia.ajustar_texto_destaque()   # v1.1: texto sobre o botão de destaque com contraste certo em qualquer tema
	for a in OS.get_cmdline_user_args():   # gancho dos testes visuais (tools/visual): abre uma aba das Configurações
		if a.begins_with("--visual-abrir="):
			_visual_abrir.call_deferred(a.get_slice("=", 1))
		if a == "--visual-cartoes-abertos":     # teste: abre todos os cartões de atividade
			cartoes.abrir_ao_criar = true
		if a == "--visual-guarda":     # teste: simula 2 janelas de desempenho ruim (5 quadros/s)
			get_tree().create_timer(6.0).timeout.connect(func():
				aparencia._decidir(5.0)
				aparencia._decidir(5.0))
		if a.begins_with("--visual-preset="):
			aparencia.aplicar_preset.call_deferred(a.get_slice("=", 1))
	close_requested.connect(func(): get_tree().quit())
	if brain:
		brain.request_conversations()
		brain.request_settings()
	# v13 — pré-carrega/verifica os avatares do projeto assim que a UI existe
	call_deferred("_iniciar_pre_carregamento_avatares", false)
	_aplicar_layout_celular()      # v1.12 (port celular): só no Android (ou com --layout-celular); no PC nada muda


# NOVO v10 — única função _process() deste script, de propósito (o
# resto do arquivo prefere Tween/sinal, ver comentário logo abaixo).
# Existe só pra os 4 campos de "Ajuste fino" acompanharem ao vivo
# enquanto o Anderson arrasta a Zenith no modo "Ajustar arrastando" — o
# `if` de guarda faz o corpo da função não custar nada no resto do
# tempo (a imensa maioria), já que esse modo fica desligado por padrão.
func _process(delta):
	if adjusting_by_drag:
		_sync_adjust_fields()
	if _avatar_ui_modo != "":
		_tick_avatar_ui(delta)
	if not _prog_ativos.is_empty():
		_tick_progresso(delta)       # v28: barra "vai e volta" + vigia que destrava a tela se o Cérebro sumir


# v11 — os 4 campos de "Ajuste fino" eram criados com "0.0"/"1.0" fixos e
# NUNCA mostravam o que estava realmente valendo (o ajuste salvo em disco
# ou o que o arraste está fazendo agora) — então "tudo zerado" na tela não
# provava que o avatar estava sem ajuste. Agora eles espelham o valor real:
# ao abrir as Configurações e, ao vivo, enquanto o modo de arraste está ligado.
func _sync_adjust_fields():
	if not (akira_body and akira_body.has_method("get_manual_vrm_adjust")):
		return
	if not (offx and offy and offz and scale_mult_field):
		return
	var vals: Array = akira_body.get_manual_vrm_adjust()
	var offset: Vector3 = vals[0]
	var escala: float = vals[1]
	offx.text = "%.2f" % offset.x
	offy.text = "%.2f" % offset.y
	offz.text = "%.2f" % offset.z
	scale_mult_field.text = "%.2f" % escala


# Substitui o "aparece travado" por uma entrada suave (fade + leve
# encolhida->tamanho normal) — mesma ideia da barra que deslizava no
# script antigo, só que via Tween em vez de lerp em _process.
var _rx_emoji: RegEx = null


# v1.6 — tira emoji de textos que o PRÓPRIO Corpo escreve (o Cérebro já limpa os dele). Se só sobrar espaço, devolve o original.
func _sem_emoji(s: String) -> String:
	if _rx_emoji == null:
		_rx_emoji = RegEx.new()
		_rx_emoji.compile("[\\x{1F000}-\\x{1FAFF}\\x{2600}-\\x{26FF}\\x{2700}-\\x{2712}\\x{2714}\\x{2716}\\x{271D}\\x{2721}\\x{2728}\\x{2733}\\x{2734}\\x{2744}\\x{2747}\\x{274C}\\x{274E}\\x{2753}-\\x{2755}\\x{2757}\\x{2763}\\x{2764}\\x{2795}-\\x{2797}\\x{27A1}\\x{27B0}\\x{27BF}\\x{2B05}-\\x{2B07}\\x{2B1B}\\x{2B1C}\\x{2B50}\\x{2B55}\\x{231A}\\x{231B}\\x{23E9}-\\x{23F3}\\x{23F8}-\\x{23FA}\\x{FE0F}\\x{200D}\\x{20E3}]+ ?")
	if not _rx_emoji.is_valid():
		return s
	var limpo: String = _rx_emoji.sub(s, "", true)
	if limpo.strip_edges() == "":
		return s
	return limpo


# v1.6 — o avatar é OUTRA janela (sempre por cima). Painéis grandes não podem ficar por baixo dele: antes as opções de
# "Permissões" e o botão "Resetar" sumiam atrás do avatar. Encolhe o painel pela direita até a borda do avatar.
func _afastar_do_avatar(card: Control):
	if card == null or not is_instance_valid(card):
		return
	if not (card.anchor_left > 0.0 and card.anchor_right > 0.0 and card.anchor_right < 1.0):
		return
	if not card.has_meta("anchor_right_orig"):
		card.set_meta("anchor_right_orig", card.anchor_right)
	var original: float = float(card.get_meta("anchor_right_orig"))
	card.anchor_right = original
	var largura: float = float(size.x)
	if largura < 300.0:
		return
	var r_chat: Rect2 = Rect2(Vector2(position), Vector2(size))
	var r_avatar: Rect2 = Rect2(Vector2(DisplayServer.window_get_position(0)), Vector2(DisplayServer.window_get_size(0)))
	if not r_chat.intersects(r_avatar):
		return
	var borda_esq: float = r_avatar.position.x - r_chat.position.x
	if borda_esq < largura * 0.35:
		return        # avatar cobriria a maior parte da janela: não dá para fugir dele; deixa como está
	if borda_esq < largura * original:
		card.anchor_right = clampf((borda_esq - 16.0) / largura, card.anchor_left + 0.25, original)


func _show_overlay(overlay: Control, card: Control):
	_afastar_do_avatar(card)
	if layout_celular != null:
		layout_celular.preparar_cartao(card)      # v1.14 (port celular): cartão vira tela cheia / diálogo largo; no PC nada muda
	overlay.visible = true
	overlay.modulate.a = 0.0
	card.scale = Vector2(0.96, 0.96)
	card.pivot_offset = card.size / 2.0
	var tween = create_tween().set_parallel(true)
	tween.tween_property(overlay, "modulate:a", 1.0, 0.18)
	tween.tween_property(card, "scale", Vector2.ONE, 0.18).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)


func _hide_overlay(overlay: Control):
	var tween = create_tween()
	tween.tween_property(overlay, "modulate:a", 0.0, 0.12)
	tween.tween_callback(func(): overlay.visible = false)


func _connect_brain_signals():
	if not brain:
		return
	if brain.has_signal("akira_connection_changed"):
		brain.akira_connection_changed.connect(_on_connection_changed)
	if brain.has_signal("conversations_list"):
		brain.conversations_list.connect(_on_conversations_list)
	if brain.has_signal("memories_list"):
		brain.memories_list.connect(_on_memories_list)
	if brain.has_signal("projetos_dados"):          # v1.6 — painel Biblioteca
		brain.projetos_dados.connect(_on_projetos_dados)
	if brain.has_signal("conversation_loaded"):
		brain.conversation_loaded.connect(_on_conversation_loaded)
	if brain.has_signal("chaves_estado"):     # v1.1 — página Chaves
		brain.chaves_estado.connect(func(d): if chaves_page: chaves_page.ao_estado(d))
		brain.chaves_resultado.connect(func(ok, msg): if chaves_page: chaves_page.ao_resultado(ok, msg))
		brain.chaves_teste.connect(func(d): if chaves_page: chaves_page.ao_teste(d))
		brain.chaves_teste_fim.connect(func(): if chaves_page: chaves_page.ao_teste_fim())
	if brain.has_signal("cartao_atividade"):          # v1.3 — o que a Zenith está fazendo
		brain.cartao_atividade.connect(func(d): if cartoes: cartoes.atualizar(d))
	if brain.has_signal("atualizacao_disponivel"):
		brain.atualizacao_disponivel.connect(_on_atualizacao_disponivel)
	if brain.has_signal("diagnostico_resultado"):     # v1.2 — Saúde do Zenith
		brain.diagnostico_resultado.connect(func(d): if saude_page: saude_page.ao_resultado(d))
	if brain.has_signal("desempenho_estado"):          # v1.11 — Desempenho (downgrade)
		brain.desempenho_estado.connect(func(d): if desempenho_page: desempenho_page.ao_estado(d))
	if brain.has_signal("desempenho_config"):
		brain.desempenho_config.connect(func(d): _aplicar_desempenho(d))
	if brain.has_signal("akira_chat_message"):
		brain.akira_chat_message.connect(_on_incoming_chat_message)
	if brain.has_signal("akira_chat_stream_chunk"):
		brain.akira_chat_stream_chunk.connect(_on_incoming_chat_stream_chunk)
	if brain.has_signal("settings_data"):
		brain.settings_data.connect(_on_settings_data)
	if brain.has_signal("settings_saved"):
		brain.settings_saved.connect(_on_settings_saved)
	if brain.has_signal("approval_request"):
		brain.approval_request.connect(_on_approval_request)
	if brain.has_signal("api_key_test_result"):
		brain.api_key_test_result.connect(_on_api_key_test_result)
		if brain.has_signal("wallpaper_ready"):
			brain.wallpaper_ready.connect(_on_wallpaper_ready)
		if brain.has_signal("reset_scheduled"):
			brain.reset_scheduled.connect(_on_reset_scheduled)
		if brain.has_signal("chat_image"):
			brain.chat_image.connect(_on_chat_image)
		if brain.has_signal("observando"):
			brain.observando.connect(_on_observando_ui)       # v23
		if brain.has_signal("ui_tema"):
			brain.ui_tema.connect(_on_ui_tema)                # v25
	if brain.has_signal("mic_state_changed"):
		brain.mic_state_changed.connect(_on_mic_state_changed)
	if brain.has_signal("akira_notify"):
		brain.akira_notify.connect(_on_akira_notify)
	if brain.has_signal("mic_transcript_received"):
		brain.mic_transcript_received.connect(_on_mic_transcript_received)
	if brain.has_signal("conversa_estado"):
		brain.conversa_estado.connect(_on_conversa_estado)
	if brain.has_signal("atividade"):
		brain.atividade.connect(_on_atividade_ui)             # v26
	if brain.has_signal("mic_fase"):
		brain.mic_fase.connect(_on_mic_fase_ui)               # v26
	# v28
	if brain.has_signal("progresso"):
		brain.progresso.connect(_on_progresso)
	if brain.has_signal("aviso"):
		brain.aviso.connect(_on_aviso)
	if brain.has_signal("anexo_resumo"):
		brain.anexo_resumo.connect(_on_anexo_resumo)
	if brain.has_signal("comandos_lista"):
		brain.comandos_lista.connect(_on_comandos_lista)


# ================= ESTRUTURA GERAL =================
var _raiz_ui: Control = null


func _build_root():
	var root = Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_raiz_ui = root
	add_child(root)

	# CORREÇÃO (mitigação confirmada por experimento: a janela "Central de
	# Controle" atravessando dois monitores ao mesmo tempo é a causa do
	# vão preto no chat — o Godot só desenha o conteúdo na parte que está
	# no monitor "dono" da janela). Isto aqui não impede arrastar a
	# janela pro outro monitor — só garante que ela nunca fique
	# ATRAVESSADA entre os dois, empurrando ela inteira pro monitor onde
	# está o centro dela sempre que for redimensionada.
	size_changed.connect(_clamp_no_monitor)

	# O Corpo (avatar) agora é uma janela separada de novo — esta janela
	# pode ter fundo opaco à vontade, sem risco de tampar o 3D (que nem
	# está aqui).
	var bg = ColorRect.new()
	bg.color = BG_BASE
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_STOP
	root.add_child(bg)
	aparencia.registrar("moldura", root, bg)

	var hbox = HBoxContainer.new()
	hbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	hbox.add_theme_constant_override("separation", 0)
	root.add_child(hbox)

	hbox.add_child(_build_sidebar())

	var main_col = VBoxContainer.new()
	main_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	main_col.add_theme_constant_override("separation", 0)
	hbox.add_child(main_col)

	main_col.add_child(_build_topbar())
	main_col.add_child(_build_chat_area())
	main_col.add_child(_build_input_bar())

	# Overlays (por cima de tudo, começam escondidos)
	settings_overlay = _build_settings_overlay()
	settings_overlay.visible = false
	root.add_child(settings_overlay)

	approval_overlay = _build_approval_overlay()
	approval_overlay.visible = false
	root.add_child(approval_overlay)

	onboarding_overlay = _build_onboarding_overlay()
	onboarding_overlay.visible = false
	root.add_child(onboarding_overlay)

	memories_overlay = _build_memories_overlay()
	memories_overlay.visible = false
	root.add_child(memories_overlay)
	projetos_overlay = _build_projetos_overlay()      # v1.6
	projetos_overlay.visible = false
	root.add_child(projetos_overlay)
	programacao_overlay = _build_programacao_overlay()
	programacao_overlay.visible = false
	root.add_child(programacao_overlay)

	# v13 — por último, pra ficar por cima de tudo (inclusive Configurações)
	avatar_loading_overlay = _build_avatar_loading_overlay()
	avatar_loading_overlay.visible = false
	root.add_child(avatar_loading_overlay)


# CORREÇÃO (multi-monitor — causa confirmada do vão preto no chat quando
# a Central de Controle fica atravessada entre dois monitores ao mesmo
# tempo, já que o Godot só desenha o conteúdo na parte que está no
# monitor "dono" da janela). Empurra a janela inteira pro monitor onde
# está o seu centro, sem sair "no meio" de dois.
func _clamp_no_monitor() -> void:
	var s = size
	if s.x <= 0 or s.y <= 0:
		return
	var centro = position + Vector2i(s) / 2
	for i in DisplayServer.get_screen_count():
		var sp = DisplayServer.screen_get_position(i)
		var ss = DisplayServer.screen_get_size(i)
		if Rect2i(sp, ss).has_point(centro):
			_descontar_barra_de_tarefas(DisplayServer.screen_get_usable_rect(i))   # v28
			var nova = position
			nova.x = clampi(nova.x, sp.x, sp.x + ss.x - int(s.x)) if ss.x >= s.x else sp.x
			nova.y = clampi(nova.y, sp.y, sp.y + ss.y - int(s.y)) if ss.y >= s.y else sp.y
			if nova != position:
				position = nova
			return


# v28 — nos prints a barra de tarefas do Windows cobria o fundo da janela (a caixa de texto ficava escondida embaixo dela). Se a
# janela passa da ÁREA ÚTIL do monitor (a tela menos a barra de tarefas), a interface inteira encolhe por baixo na mesma medida.
func _descontar_barra_de_tarefas(util: Rect2i) -> void:
	if _raiz_ui == null or not is_instance_valid(_raiz_ui):
		return
	if mode == Window.MODE_FULLSCREEN or mode == Window.MODE_EXCLUSIVE_FULLSCREEN:
		_raiz_ui.offset_bottom = 0.0
		return
	var sobra: int = (position.y + size.y) - (util.position.y + util.size.y)
	var alvo: float = -float(maxi(sobra, 0))
	if absf(_raiz_ui.offset_bottom - alvo) > 0.5:
		_raiz_ui.offset_bottom = alvo


func _panel_style(bg_color: Color, radius: int = 0, border_color: Color = Color(0,0,0,0), border_w: int = 0) -> StyleBoxFlat:
	var sb = StyleBoxFlat.new()
	sb.bg_color = bg_color
	sb.corner_radius_top_left = radius
	sb.corner_radius_top_right = radius
	sb.corner_radius_bottom_left = radius
	sb.corner_radius_bottom_right = radius
	if border_w > 0:
		sb.border_color = border_color
		sb.border_width_left = border_w
		sb.border_width_right = border_w
		sb.border_width_top = border_w
		sb.border_width_bottom = border_w
	return sb


func _make_button(text: String, bg: Color, hover: Color, text_color: Color = Color(0, 0, 0, 0)) -> Button:
	if text_color.a == 0.0:
		text_color = TEXT_PRIMARY      # v25: TEXT_PRIMARY virou variável (tema) — não serve como valor padrão
	var b = Button.new()
	b.text = text
	b.add_theme_stylebox_override("normal", _panel_style(bg, 8))
	b.add_theme_stylebox_override("hover", _panel_style(hover, 8))
	b.add_theme_stylebox_override("pressed", _panel_style(hover, 8))
	b.add_theme_color_override("font_color", text_color)
	b.add_theme_color_override("font_hover_color", text_color)
	b.custom_minimum_size.y = 34
	return b


# ================= v1.1 — ÍCONES PRÓPRIOS (no lugar dos emojis) =================
# Põe texto num botão trocando o símbolo/emoji do começo por um ícone próprio (res://assets/icones/).
# A cor do ícone segue a cor do texto do botão — por isso acompanha o tema.
func _ic(b: Button, texto: String, cor: Color = Color(0, 0, 0, 0), tam: int = 18) -> void:
	if b == null or not is_instance_valid(b):
		return
	if cor.a == 0.0:
		cor = b.get_theme_color("font_color")
	Icones.texto_com_icone(b, texto, cor, tam)

# Passa por todos os botões já montados e troca o emoji do começo do texto pelo ícone.
func _iconizar_arvore(no: Node) -> void:
	if no is Button and not (no is OptionButton) and not (no is CheckBox) and not (no is CheckButton):
		var b: Button = no
		if b.text != "" and Icones.separar(b.text)[0] != "":
			_ic(b, b.text)
	for filho in no.get_children():
		_iconizar_arvore(filho)


# ================= BARRA LATERAL (conversas) =================
func _build_sidebar() -> PanelContainer:
	var panel = PanelContainer.new()
	panel.custom_minimum_size.x = SIDEBAR_WIDTH
	panel.add_theme_stylebox_override("panel", _panel_style(BG_PANEL))
	aparencia.registrar("barra_lateral", panel)

	sidebar = VBoxContainer.new()
	sidebar.add_theme_constant_override("separation", 4)
	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 10)
	margin.add_theme_constant_override("margin_right", 10)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_bottom", 26)
	margin.add_child(sidebar)
	panel.add_child(margin)

	var marca = HBoxContainer.new()                 # v1.7: logo + nome no alto da barra lateral
	marca.add_theme_constant_override("separation", 10)
	if ResourceLoader.exists("res://icon.png"):
		var logo := TextureRect.new()
		logo.texture = load("res://icon.png")
		logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		logo.custom_minimum_size = Vector2(26, 26)
		marca.add_child(logo)
	var nome_marca = Label.new()
	nome_marca.text = "ZENITH"
	nome_marca.add_theme_color_override("font_color", TEXT_PRIMARY)
	nome_marca.add_theme_font_size_override("font_size", 15)
	marca.add_child(nome_marca)
	var marca_margem = MarginContainer.new()
	marca_margem.add_theme_constant_override("margin_left", 6)
	marca_margem.add_theme_constant_override("margin_bottom", 12)
	marca_margem.add_child(marca)
	sidebar.add_child(marca_margem)

	var new_btn = _make_button("Nova conversa", CYAN, CYAN_DIM, Color("04141a"))
	Icones.aplicar(new_btn, "mais", Color("04141a"))
	new_btn.pressed.connect(func(): if brain: brain.request_new_conversation())
	sidebar.add_child(new_btn)

	# FEATURE ("mostra as coisas que ela lembra"): a memória semântica já
	# existia por trás dos panos (recall automático a cada resposta) —
	# esse botão só deixa ela VISÍVEL, com uma lista do que já foi
	# guardado, pra você conseguir de fato testar "você lembra disso?".
	var memories_btn = _make_button("🧠  Memórias", Color(0, 0, 0, 0), BG_SURFACE_2)
	memories_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	memories_btn.pressed.connect(func():
		if brain: brain.request_memories()
		_show_overlay(memories_overlay, memories_card))
	sidebar.add_child(memories_btn)

	# v1.6 — Biblioteca Zenith: tudo o que ela criou, por assunto
	var projetos_btn = _make_button("📚  Biblioteca", Color(0, 0, 0, 0), BG_SURFACE_2)
	projetos_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	projetos_btn.pressed.connect(func():
		if brain: brain.request_projetos()
		_show_overlay(projetos_overlay, projetos_card))
	sidebar.add_child(projetos_btn)

	# v1.22 — Área de Programação (Código e Mentoria)
	var prog_btn = _make_button("💻  Programação", Color(0, 0, 0, 0), BG_SURFACE_2)
	prog_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	prog_btn.pressed.connect(func():
		_show_overlay(programacao_overlay, programacao_card))
	sidebar.add_child(prog_btn)

	var rotulo_conv = Label.new()                   # v1.7: no lugar da linha separadora
	rotulo_conv.text = "CONVERSAS"
	rotulo_conv.add_theme_color_override("font_color", TEXT_MUTED)
	rotulo_conv.add_theme_font_size_override("font_size", 11)
	var rotulo_margem = MarginContainer.new()
	rotulo_margem.add_theme_constant_override("margin_left", 6)
	rotulo_margem.add_theme_constant_override("margin_top", 14)
	rotulo_margem.add_theme_constant_override("margin_bottom", 4)
	rotulo_margem.add_child(rotulo_conv)
	sidebar.add_child(rotulo_margem)

	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sidebar.add_child(scroll)

	conv_list_box = VBoxContainer.new()
	conv_list_box.add_theme_constant_override("separation", 2)
	conv_list_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(conv_list_box)

	var gear_btn = _make_button("⚙  Configurações", Color(0, 0, 0, 0), BG_SURFACE_2)
	gear_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	gear_btn.pressed.connect(func():
		_sync_adjust_fields()
		_refresh_project_avatar_list()
		_show_overlay(settings_overlay, settings_card))
	sidebar.add_child(gear_btn)

	return panel


func _on_conversations_list(items: Array):
	for c in conv_list_box.get_children():
		c.queue_free()
	for item in items:
		conv_list_box.add_child(_build_conversation_row(item))
		if item.get("id", "") == active_conv_id:          # v1.7: renomear a conversa aberta atualiza o título lá em cima
			_atualizar_titulo(String(item.get("title", "")))


func _build_conversation_row(item: Dictionary) -> Control:
	var row = PanelContainer.new()
	var is_active = (item.get("id", "") == active_conv_id)
	row.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2 if is_active else Color(0,0,0,0), 6))

	var hbox = HBoxContainer.new()
	row.add_child(hbox)

	var title_btn = Button.new()
	var prefix = "★ " if item.get("pinned", false) else ""
	title_btn.text = prefix + String(item.get("title", "Conversa"))
	title_btn.clip_text = true
	title_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	title_btn.flat = true
	title_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_btn.add_theme_color_override("font_color", CYAN if item.get("pinned", false) else TEXT_PRIMARY)
	title_btn.pressed.connect(func(): if brain: brain.request_load_conversation(item.get("id", "")))
	hbox.add_child(title_btn)

	# FEATURE (renomear conversa): clique no lápis troca o botão-título
	# por um campo de texto editável ali mesmo na lista, sem abrir
	# nenhuma outra tela.
	var rename_field = LineEdit.new()
	rename_field.text = String(item.get("title", "Conversa"))
	rename_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rename_field.visible = false
	hbox.add_child(rename_field)

	var _confirm_rename = func():
		var novo = rename_field.text.strip_edges()
		rename_field.visible = false
		title_btn.visible = true
		if novo != "" and novo != String(item.get("title", "")) and brain:
			brain.request_rename_conversation(item.get("id", ""), novo)
	rename_field.text_submitted.connect(func(_t): _confirm_rename.call())
	rename_field.focus_exited.connect(func(): _confirm_rename.call())

	var rename_btn = Button.new()
	_ic(rename_btn, "✎", TEXT_MUTED, 16)
	rename_btn.flat = true
	rename_btn.custom_minimum_size.x = 26
	rename_btn.tooltip_text = "Renomear conversa"
	rename_btn.add_theme_color_override("font_color", TEXT_MUTED)
	rename_btn.add_theme_color_override("font_hover_color", CYAN)
	rename_btn.pressed.connect(func():
		title_btn.visible = false
		rename_field.visible = true
		rename_field.grab_focus()
		rename_field.select_all())
	hbox.add_child(rename_btn)

	var pin_btn = Button.new()
	Icones.aplicar(pin_btn, "fixar", TEXT_MUTED if not item.get("pinned", false) else CYAN, 16)
	pin_btn.flat = true
	pin_btn.custom_minimum_size.x = 26
	pin_btn.add_theme_color_override("font_color", TEXT_MUTED if not item.get("pinned", false) else CYAN)
	pin_btn.pressed.connect(func(): if brain: brain.request_pin_conversation(item.get("id", ""), not item.get("pinned", false)))
	hbox.add_child(pin_btn)

	var del_btn = Button.new()
	_ic(del_btn, "✕", TEXT_MUTED, 16)
	del_btn.flat = true
	del_btn.custom_minimum_size.x = 26
	del_btn.add_theme_color_override("font_color", TEXT_MUTED)
	del_btn.add_theme_color_override("font_hover_color", RED)
	del_btn.pressed.connect(func(): if brain: brain.request_delete_conversation(item.get("id", "")))
	hbox.add_child(del_btn)

	# v1.7 — os três ícones só aparecem ao passar o mouse, na conversa aberta ou (o alfinete) se estiver fixada.
	# visible=false (e não transparente) para um ícone escondido nunca ser clicado sem ninguém ver.
	var acoes: Array = [rename_btn, pin_btn, del_btn]
	var fixada: bool = bool(item.get("pinned", false))
	var mostrar_acoes = func(sim: bool):
		for a in acoes:
			if is_instance_valid(a):
				a.visible = sim or is_active or (a == pin_btn and fixada)
	mostrar_acoes.call(false)
	row.mouse_entered.connect(func(): mostrar_acoes.call(true))
	row.mouse_exited.connect(func(): mostrar_acoes.call(row.get_global_rect().has_point(row.get_global_mouse_position())))

	return row


func _rolar_chat_para_baixo() -> void:
	await get_tree().process_frame
	chat_scroll.scroll_vertical = int(chat_scroll.get_v_scroll_bar().max_value)


func _atualizar_titulo(titulo: String) -> void:       # v1.7: a barra de cima mostra o título da conversa aberta
	if title_label and is_instance_valid(title_label):
		title_label.text = titulo if titulo.strip_edges() != "" else persona_name


func _on_conversation_loaded(id: String, title: String, messages: Array):
	active_conv_id = id
	_atualizar_titulo(title)
	if cartoes:
		cartoes.limpar()
	for c in chat_log.get_children():
		c.queue_free()
	for m in messages:
		_add_bubble(String(m.get("text", "")), String(m.get("sender", "ai")), String(m.get("ts", "")))
	var eh_celular: bool = OS.get_name() == "Android" or OS.get_cmdline_user_args().has("--layout-celular")
	if brain and not eh_celular:
		brain.request_conversations()  # atualiza destaque de "ativa" na lista


# ================= TOPO =================
func _build_topbar() -> PanelContainer:
	var panel = PanelContainer.new()
	panel.custom_minimum_size.y = 52
	panel.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE))
	aparencia.registrar("barra_superior", panel)

	var hbox = HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 8)
	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 16)
	margin.add_theme_constant_override("margin_right", 16)
	margin.add_child(hbox)
	panel.add_child(margin)

	var title = Label.new()
	title.text = persona_name       # v1.7: vira o título da conversa aberta (_atualizar_titulo)
	title.clip_text = true
	title.custom_minimum_size.x = 160
	title.add_theme_color_override("font_color", TEXT_PRIMARY)
	title.add_theme_font_size_override("font_size", 17)
	hbox.add_child(title)
	title_label = title

	var spacer = Control.new()
	spacer.custom_minimum_size.x = 8
	hbox.add_child(spacer)

	status_dot = ColorRect.new()
	status_dot.color = RED
	status_dot.custom_minimum_size = Vector2(9, 9)
	status_dot.mouse_filter = Control.MOUSE_FILTER_PASS
	status_dot.tooltip_text = "Desconectado do Cérebro"
	status_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	hbox.add_child(status_dot)

	status_label = Label.new()
	status_label.text = "desconectado"
	status_label.add_theme_color_override("font_color", TEXT_SECOND)
	status_label.add_theme_font_size_override("font_size", 11)
	status_label.visible = false      # v1.7: só o ponto colorido; o texto fica no tooltip do ponto
	hbox.add_child(status_label)

	var spacer2 = Control.new()
	spacer2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_child(spacer2)

	# FEATURE (trocar de IA direto do chat): antes só dava pra trocar de
	# provedor abrindo Configurações > IAs & Chaves. Esse seletor aqui
	# mostra as MESMAS opções (as IAs prontas + qualquer IA
	# personalizada cadastrada) e reflete/edita o mesmo "active_ai" —
	# os dois lugares ficam sempre sincronizados.
	quick_ai_selector = OptionButton.new()
	quick_ai_selector.custom_minimum_size.x = 150
	for est in ["normal", "hover", "pressed", "focus"]:     # v1.1: antes ficava com o cinza padrão do Godot em qualquer tema
		quick_ai_selector.add_theme_stylebox_override(est, _panel_style(BG_SURFACE_3 if est == "hover" else BG_SURFACE_2, 18, BORDER, 1))
	for cn in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		quick_ai_selector.add_theme_color_override(cn, TEXT_PRIMARY)
	quick_ai_selector.tooltip_text = "Trocar de IA"
	quick_ai_selector.item_selected.connect(func(_idx):
		var opts = quick_ai_selector.get_meta("options", [])
		if quick_ai_selector.selected >= 0 and quick_ai_selector.selected < opts.size() and brain \
				and String(opts[quick_ai_selector.selected]) != "":
			brain.save_settings({"active_ai": opts[quick_ai_selector.selected]}))
	hbox.add_child(quick_ai_selector)

	# Botão "Mover Zenith" — volta a fazer sentido agora que o Corpo é
	# uma janela flutuante separada de novo. Chama akira_body direto
	# (mesmo processo Godot, sem precisar da Ponte/WebSocket pra isso).
	move_btn = _make_button("◈", Color(0, 0, 0, 0), BG_SURFACE_2)      # v1.7: só o ícone; o nome vai no tooltip
	move_btn.custom_minimum_size.x = 38
	move_btn.tooltip_text = "Mover o avatar (arraste a janela dela)"
	move_btn.pressed.connect(_toggle_move_avatar)
	_btn_atualizar = _make_button("🚀 Atualizar", CYAN, BG_SURFACE_2, TEXT_PRIMARY)
	_btn_atualizar.custom_minimum_size = Vector2(110, 32)
	_btn_atualizar.visible = false
	_btn_atualizar.pressed.connect(_on_clique_atualizar)
	hbox.add_child(_btn_atualizar)
	hbox.add_child(move_btn)

	# v23 — indicador + botão PARAR da observação ao vivo (Pilar 1: sempre visível e sempre dá pra parar)
	obs_btn = _make_button("🔴  Parar observação", Color(0.42, 0.07, 0.07), Color(0.6, 0.1, 0.1))
	obs_btn.custom_minimum_size.x = 190
	obs_btn.visible = false
	obs_btn.pressed.connect(func():
		if brain and brain.has_method("send_to_brain"):
			brain.send_to_brain({"action": "chat", "text": "/parar_observacao"}))
	hbox.add_child(obs_btn)

	# v26 — linha de status "o que ela está fazendo" + botão ⏹ PARAR (sempre à mão enquanto há algo em andamento).
	# O texto vem pronto do Cérebro (mensagem "atividade"): o Corpo só desenha, não decide nada.
	atividade_lbl = Label.new()
	atividade_lbl.visible = false
	atividade_lbl.clip_text = true
	atividade_lbl.custom_minimum_size.x = 200
	atividade_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	hbox.add_child(atividade_lbl)
	parar_btn = _make_button("⏹  Parar", Color(0.42, 0.07, 0.07), Color(0.6, 0.1, 0.1))
	parar_btn.custom_minimum_size.x = 100
	parar_btn.tooltip_text = "Para tudo que ela estiver fazendo (ou diga: calma aí, Zenith)"
	parar_btn.visible = false
	parar_btn.pressed.connect(func():
		if brain and brain.has_method("send_to_brain"):
			brain.send_to_brain({"action": "chat", "text": "/parar"}))
	hbox.add_child(parar_btn)

	return panel


# v1.1 — fundo do bloco de código: um pouco mais escuro que o fundo do tema (no tema claro, um pouco mais cinza)
func _hex_codigo() -> String:
	var c: Color = BG_BASE.darkened(0.3) if BG_BASE.get_luminance() < 0.5 else BG_BASE.darkened(0.07)
	return c.to_html(false)


# v1.1 — depois de trocar o tema, redesenha a conversa aberta (balões antigos guardam as cores de quando nasceram)
func _recarregar_conversa() -> void:
	if brain and active_conv_id != "":
		brain.request_load_conversation(active_conv_id)


func _visual_abrir(aba: String) -> void:
	if aba.begins_with("Biblioteca"):      # teste visual (v1.6.1): abre o painel Biblioteca, opcionalmente numa aba ("Biblioteca:biblia")
		if aba.contains(":"):
			projetos_aba = aba.get_slice(":", 1)
		_show_overlay(projetos_overlay, projetos_card)
		await get_tree().create_timer(6.0).timeout      # espera o Cérebro (de mentira) conectar antes de pedir os dados
		if brain:
			brain.request_projetos()
		if OS.get_cmdline_user_args().has("--visual-ler"):      # teste: abre o primeiro cartão da Bíblia (botão "Ler")
			await get_tree().create_timer(2.0).timeout
			var ler = _achar_botao(projetos_list_box, "Ler")
			if ler != null:
				ler.pressed.emit()
		return
	_show_overlay(settings_overlay, settings_card)
	for i in settings_tabs.get_tab_count():
		if settings_tabs.get_tab_title(i) == aba:
			settings_tabs.current_tab = i
	for a in OS.get_cmdline_user_args():     # teste visual: rola a aba até a posição pedida
		if a.begins_with("--visual-rolar="):
			await get_tree().create_timer(1.0).timeout
			(settings_tabs.get_current_tab_control() as ScrollContainer).scroll_vertical = int(a.get_slice("=", 1))
	if aba == "Sobre" and OS.get_cmdline_user_args().has("--visual-rodar"):     # teste visual: roda o diagnóstico sozinho
		get_tree().create_timer(6.0).timeout.connect(func(): saude_page.rodar())


func _achar_botao(raiz: Node, texto: String) -> Button:     # só para os testes visuais
	for c in raiz.get_children():
		if c is Button and (c as Button).text == texto:
			return c
		var dentro = _achar_botao(c, texto)
		if dentro != null:
			return dentro
	return null


func _toggle_move_avatar():
	moving_avatar = not moving_avatar
	# NOVO v10 — os dois modos de arraste (mover janela / ajustar
	# posição-escala) nunca ficam ligados junto, senão o mesmo arraste
	# vira ambíguo (move a janela OU ajusta o avatar?). Desliga o outro
	# sozinho; o guard dentro de _toggle_adjust_drag() evita ida-e-volta
	# infinita entre as duas funções.
	if moving_avatar and adjusting_by_drag:
		_toggle_adjust_drag()
	if akira_body and akira_body.has_method("set_edit_mode"):
		akira_body.set_edit_mode(moving_avatar)
	if moving_avatar:
		_ic(move_btn, "■")
		move_btn.tooltip_text = "Fixar o avatar onde está"
		move_btn.add_theme_stylebox_override("normal", _panel_style(RED, 8))
	else:
		_ic(move_btn, "◈")
		move_btn.tooltip_text = "Mover o avatar (arraste a janela dela)"
		move_btn.add_theme_stylebox_override("normal", _panel_style(Color(0, 0, 0, 0), 8))


# NOVO v10 — par de _toggle_move_avatar(), mesmo padrão. Liga/desliga o
# modo "arrastar pra ajustar" (ver akira_body.gd::set_adjust_drag_mode).
func _toggle_adjust_drag():
	adjusting_by_drag = not adjusting_by_drag
	if adjusting_by_drag and moving_avatar:
		_toggle_move_avatar()
	if akira_body and akira_body.has_method("set_adjust_drag_mode"):
		akira_body.set_adjust_drag_mode(adjusting_by_drag)
	if adjusting_by_drag:
		_ic(adjust_drag_btn, "■  Parar de ajustar")
		adjust_drag_btn.add_theme_stylebox_override("normal", _panel_style(RED, 8))
	else:
		_ic(adjust_drag_btn, "🖱  Ajustar arrastando")
		adjust_drag_btn.add_theme_stylebox_override("normal", _panel_style(BG_SURFACE_2, 8))


func _on_connection_changed(connected: bool):
	if connected and chaves_page and chaves_page.pendente:     # v1.1: a página Chaves pediu antes de o Cérebro conectar
		chaves_page.pedir()
	status_dot.color = GREEN if connected else RED
	status_label.text = "conectado" if connected else "desconectado"
	status_dot.tooltip_text = "Conectado ao Cérebro" if connected else "Desconectado do Cérebro"
	if connected and brain:
		brain.request_conversations()
		brain.request_settings()


# ================= CHAT =================
func _build_chat_area() -> Control:
	var wrapper = PanelContainer.new()
	wrapper.size_flags_vertical = Control.SIZE_EXPAND_FILL
	wrapper.add_theme_stylebox_override("panel", _panel_style(BG_BASE))

	# FEATURE (imagem/animação de fundo do chat — corrigindo um recurso
	# que ficou "morto" na migração pra Godot): a config chat_wallpaper_path
	# já existia e salvava certinho, mas nada aqui desenhava ela de
	# verdade — essa era a causa de "eu troco mas não muda nada".
	# Ficam os dois nós prontos, escondidos até ter um caminho salvo;
	# _apply_wallpaper() decide qual mostrar.
	wallpaper_rect = TextureRect.new()
	wallpaper_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	wallpaper_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	wallpaper_rect.visible = false
	wrapper.add_child(wallpaper_rect)

	wallpaper_video = VideoStreamPlayer.new()
	wallpaper_video.set_anchors_preset(Control.PRESET_FULL_RECT)
	wallpaper_video.expand = true
	wallpaper_video.autoplay = false
	wallpaper_video.visible = false
	wrapper.add_child(wallpaper_video)

	wallpaper_dim_rect = ColorRect.new()
	wallpaper_dim_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	wallpaper_dim_rect.color = Color(0, 0, 0, 0)
	wallpaper_dim_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	wrapper.add_child(wallpaper_dim_rect)
	aparencia.registrar("chat", wrapper, wallpaper_dim_rect)

	chat_scroll = ScrollContainer.new()
	chat_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	chat_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chat_scroll.resized.connect(_agendar_reajuste)     # v28: balões acompanham a largura da janela
	wrapper.add_child(chat_scroll)

	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 20)
	margin.add_theme_constant_override("margin_right", 20)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_bottom", 12)
	chat_scroll.add_child(margin)
	_margem_chat = margin
	chat_scroll.resized.connect(_ajustar_margens_leitura)      # v1.7: coluna de leitura centralizada
	call_deferred("_ajustar_margens_leitura")

	chat_log = VBoxContainer.new()
	chat_log.add_theme_constant_override("separation", 10)
	chat_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	margin.add_child(chat_log)

	return wrapper


var typing_row: Control
var typing_label: Label
var typing_timer: Timer
var typing_dots: int = 0


func _show_typing():
	if typing_row and is_instance_valid(typing_row):
		return
	var row = HBoxContainer.new()
	var bubble_panel = PanelContainer.new()
	bubble_panel.add_theme_stylebox_override("panel", _panel_style(BUBBLE_AI, 12, Color("33335a"), 1))
	typing_label = Label.new()
	typing_label.text = "digitando"
	typing_label.add_theme_color_override("font_color", TEXT_SECOND)
	var inner_margin = MarginContainer.new()
	inner_margin.add_theme_constant_override("margin_left", 14)
	inner_margin.add_theme_constant_override("margin_right", 14)
	inner_margin.add_theme_constant_override("margin_top", 8)
	inner_margin.add_theme_constant_override("margin_bottom", 8)
	inner_margin.add_child(typing_label)
	bubble_panel.add_child(inner_margin)
	row.add_child(bubble_panel)
	var spacer = Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	chat_log.add_child(row)
	typing_row = row

	typing_timer = Timer.new()
	typing_timer.wait_time = 0.45
	typing_timer.timeout.connect(func():
		typing_dots = (typing_dots + 1) % 4
		if typing_label and is_instance_valid(typing_label):
			typing_label.text = "digitando" + ".".repeat(typing_dots))
	add_child(typing_timer)
	typing_timer.start()

	await get_tree().process_frame
	chat_scroll.scroll_vertical = int(chat_scroll.get_v_scroll_bar().max_value)


func _hide_typing():
	if typing_timer and is_instance_valid(typing_timer):
		typing_timer.stop()
		typing_timer.queue_free()
		typing_timer = null
	if typing_row and is_instance_valid(typing_row):
		typing_row.queue_free()
		typing_row = null


# v1.0 (A2) — reconhece chave de API e troca o valor por •••• + os 4 últimos caracteres.
# Mesmos padrões do brain/zenith_segredos.py (aqui é a camada que protege a TELA).
const _PADROES_SEGREDO := [
	r"AIza[0-9A-Za-z_\-]{30,}",
	r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}",
	r"\bgsk_[A-Za-z0-9_\-]{20,}",
	r"\btvly-[A-Za-z0-9_\-]{10,}",
	r"\bhf_[A-Za-z0-9]{20,}",
	r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}"
]


func _mascarar_segredo(texto: String) -> String:
	if texto.is_empty():
		return texto
	var saida = texto
	for padrao in _PADROES_SEGREDO:
		var re = RegEx.new()
		if re.compile(padrao) != OK:
			continue
		var busca = 0
		while true:
			var achado = re.search(saida, busca)
			if achado == null:
				break
			var valor = achado.get_string()
			var fim4 = ""
			if valor.length() > 4:
				fim4 = valor.right(4)
			saida = saida.substr(0, achado.get_start()) + "••••" + fim4 + saida.substr(achado.get_end())
			busca = achado.get_start() + 4 + fim4.length()
	return saida


func _add_bubble(text: String, sender: String, timestamp: String = ""):
	# v1.0 (A2) — chave de API nunca aparece inteira num balão, nem no seu nem no da Zenith.
	# O Cérebro já mascara o que guarda; isto é a segunda camada, para o que aparece na TELA.
	text = _mascarar_segredo(text)
	var is_user = (sender == "user")
	if not is_user:
		text = _sem_emoji(text)          # v1.6: visual próprio, sem emoji (o que a pessoa digita não é mexido)
	var row = HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	var bubble_panel = PanelContainer.new()
	bubble_panel.add_theme_stylebox_override("panel", _panel_style(
		BUBBLE_USER if is_user else Color(0, 0, 0, 0), 16 if is_user else 12))      # v1.7: sem contorno; a Zenith sem caixa

	# FEATURE (design mais legível): nome de quem falou + horário, bem
	# discretos, acima do texto — mesma ideia de qualquer app de
	# mensagens, ajuda a não depender só da cor/lado do balão pra saber
	# quem disse o quê (principalmente rolando o histórico de uma
	# conversa antiga). Quando vem de uma conversa já salva, usa o
	# horário REAL daquela mensagem (timestamp), não "agora".
	var hora_str = timestamp.replace("T", " ").split(".")[0].substr(11, 5) if timestamp != "" \
		else Time.get_time_string_from_system().substr(0, 5)
	var sender_label = Label.new()
	sender_label.text = ("Você" if is_user else persona_name) + "  ·  " + hora_str

	sender_label.add_theme_color_override("font_color", TEXT_MUTED if is_user else CYAN)
	sender_label.add_theme_font_size_override("font_size", 10 if is_user else 11)

	# v28 — resposta da IA = RichTextLabel (markdown: **negrito**, listas, `código`, ``` blocos ```); sua mensagem continua texto puro.
	# A largura acompanha o texto e a janela (antes era um 420 px fixo, e metade da tela ficava vazia).
	var label: Control
	if is_user:
		var lbl_user = Label.new()
		lbl_user.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lbl_user.add_theme_color_override("font_color", TEXT_PRIMARY)
		label = lbl_user
	else:
		label = _novo_rich()

	# FEATURE (copiar texto): cada balão ganha um botãozinho discreto de
	# copiar — some das configurações do usuário até aqui não dava pra
	# reaproveitar uma resposta fora do chat sem digitar tudo de novo.
	var copy_btn = _make_button("📋", Color(0, 0, 0, 0), BG_SURFACE_3, TEXT_MUTED)
	copy_btn.custom_minimum_size = Vector2(26, 22)
	_ic(copy_btn, "📋")
	copy_btn.tooltip_text = "Copiar texto"
	copy_btn.pressed.connect(func():
		# CORREÇÃO: usar label.text (o texto ATUAL na tela) em vez do
		# parâmetro "text" capturado na criação do balão — pra uma
		# resposta em streaming, o balão nasce com texto vazio e só o
		# Label é atualizado aos poucos (ver _on_incoming_chat_stream_chunk);
		# copiar o "text" original sempre pegava vazio/incompleto nesses casos.
		DisplayServer.clipboard_set(_texto_do_balao(label))      # v28: o texto ORIGINAL (não o BBCode, nem só o pedaço antes da equação)
		_ic(copy_btn, "✓")
		copy_btn.tooltip_text = "Copiado!"
		var t = get_tree().create_timer(1.2)
		t.timeout.connect(func():
			if is_instance_valid(copy_btn):
				_ic(copy_btn, "📋")
				copy_btn.tooltip_text = "Copiar texto"))

	var content_col = VBoxContainer.new()
	content_col.add_theme_constant_override("separation", 2)
	content_col.add_child(sender_label)
	content_col.add_child(label)
	label.set_meta("col", content_col)
	label.set_meta("primeiro", true)
	_definir_texto_balao(label, text)
	var copy_row = HBoxContainer.new()
	copy_row.alignment = BoxContainer.ALIGNMENT_END
	copy_row.add_child(copy_btn)
	content_col.add_child(copy_row)
	copy_row.modulate.a = 0.0         # v1.7: o botão de copiar só aparece ao passar o mouse no balão
	bubble_panel.mouse_entered.connect(func(): copy_row.modulate.a = 1.0)
	bubble_panel.mouse_exited.connect(func():
		if is_instance_valid(bubble_panel) and not bubble_panel.get_global_rect().has_point(bubble_panel.get_global_mouse_position()):
			copy_row.modulate.a = 0.0)

	var inner_margin = MarginContainer.new()
	inner_margin.add_theme_constant_override("margin_left", 12)
	inner_margin.add_theme_constant_override("margin_right", 12)
	inner_margin.add_theme_constant_override("margin_top", 8)
	inner_margin.add_theme_constant_override("margin_bottom", 4)
	inner_margin.add_child(content_col)
	bubble_panel.add_child(inner_margin)

	if is_user:
		var spacer = Control.new()
		spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(spacer)
		row.add_child(bubble_panel)
	else:
		row.add_child(bubble_panel)
		var spacer = Control.new()
		spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(spacer)

	row.set_meta("col", content_col)          # v28: pra achar o balão (equação no meio do texto, reajuste de largura)
	row.set_meta("ia", not is_user)
	chat_log.add_child(row)
	await get_tree().process_frame
	chat_scroll.scroll_vertical = int(chat_scroll.get_v_scroll_bar().max_value)
	return label   # FEATURE (streaming): quem chama pode guardar essa referência
	               # e ir atualizando .text aos poucos, em vez de criar um balão novo


# v21 — IMAGEM NO CHAT. Antes a IA criava a imagem e só dizia o caminho do arquivo; agora ela
# aparece num balão (com botão "Abrir" para ver em tamanho real no visualizador do sistema).
func _on_chat_image(path: String, caption: String, autor: String = ""):
	if path == "" or not FileAccess.file_exists(path):
		return
	var img = Image.new()
	if img.load(path) != OK:
		_add_bubble("🖼️ Criei a imagem, mas não consegui mostrá-la aqui: " + path, "ai")
		return
	_hide_typing()
	var tex = ImageTexture.create_from_image(img)
	# v28 — "Equação N": em vez de um cartão separado DEPOIS do texto, a imagem entra no lugar do marcador "[Equação N ↓]", no meio da resposta
	var eq_n: int = _numero_da_equacao(caption)
	if eq_n > 0:
		var colocou: bool = await _inserir_equacao_inline(eq_n, tex, img, path)
		if colocou:
			return
	var row = HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var panel = PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _panel_style(BUBBLE_AI, 12, Color("33335a"), 1))
	var col = VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	var cap = Label.new()
	cap.text = (autor if autor != "" else persona_name) + "  ·  🖼️ " + (caption if caption != "" else path.get_file())
	cap.add_theme_font_size_override("font_size", 10)
	cap.add_theme_color_override("font_color", TEXT_MUTED)
	col.add_child(cap)
	var rect = TextureRect.new()
	rect.texture = tex
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	var w = 420.0
	var h = clampf(w * float(img.get_height()) / maxf(float(img.get_width()), 1.0), 80.0, 420.0)
	rect.custom_minimum_size = Vector2(w, h)
	col.add_child(rect)
	var btn_row = HBoxContainer.new()
	btn_row.alignment = BoxContainer.ALIGNMENT_END
	var open_btn = _make_button("Abrir", BG_SURFACE_3, CYAN_DIM)
	open_btn.custom_minimum_size = Vector2(80, 26)
	open_btn.pressed.connect(func(): OS.shell_open(path))
	btn_row.add_child(open_btn)
	col.add_child(btn_row)
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 10)
	margin.add_child(col)
	panel.add_child(margin)
	row.add_child(panel)
	var spacer = Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	chat_log.add_child(row)
	await get_tree().process_frame
	chat_scroll.scroll_vertical = int(chat_scroll.get_v_scroll_bar().max_value)


func _on_incoming_chat_message(sender: String, text: String):
	if sender == "ai":
		_timeout_token += 1   # resposta chegou — cancela o aviso de "sem resposta" pendente
		_hide_typing()
		if _sem_emoji(text).strip_edges() == "":
			return          # v1.7: nunca uma bolha vazia (aparecia depois de pesquisas e ações)
	_add_bubble(text, sender)
	if brain and sender == "ai":
		brain.emit_signal("akira_speaks", text)  # aciona fala/boca no corpo, se existir TTS


# FEATURE (resposta em streaming): em vez de um "chat_message" só, no fim
# de tudo, agora pode chegar uma sequência de pedacinhos de texto. O
# primeiro pedaço cria o balão (vazio) e guarda a referência do Label;
# cada pedaço seguinte só concatena e atualiza o texto do MESMO balão —
# visualmente parece a IA "digitando ao vivo". "done" fecha esse balão
# (dispara a fala/TTS com o texto completo, do mesmo jeito que já
# acontecia em _on_incoming_chat_message) e libera a referência pro
# próximo streaming começar do zero.
var _stream_label: Control = null    # v28: pode ser RichTextLabel (markdown)
var _stream_full_text: String = ""

# v23 — CORREÇÃO ("a resposta sai picada, cada frase num balão" em PC mais lento): criar o balão é assíncrono
# (`await _add_bubble`). Se o próximo pedaço chegava ANTES do balão ficar pronto, ele via `_stream_label == null`
# e criava OUTRO balão — um por frase. Agora, enquanto o balão está sendo criado, os pedaços só se ACUMULAM
# num buffer, e quem criou o balão escreve tudo de uma vez.
var _stream_criando: bool = false
var _stream_buffer: String = ""
var _stream_done_pendente: bool = false

func _on_incoming_chat_stream_chunk(delta: String, done: bool):
	_timeout_token += 1
	_hide_typing()
	if _stream_criando:
		_stream_buffer += delta
		_stream_done_pendente = _stream_done_pendente or done
		return
	if _stream_label == null or not is_instance_valid(_stream_label):
		_stream_criando = true
		_stream_buffer = delta
		_stream_done_pendente = done
		_stream_label = await _add_bubble("", "ai")
		_stream_criando = false
		_stream_full_text = _stream_buffer
		done = _stream_done_pendente
		_stream_buffer = ""
		_stream_done_pendente = false
	else:
		_stream_full_text += delta
	if is_instance_valid(_stream_label):
		_definir_texto_balao(_stream_label, _stream_full_text)      # v28: markdown + largura
		await get_tree().process_frame
		chat_scroll.scroll_vertical = int(chat_scroll.get_v_scroll_bar().max_value)
	if done:
		var texto_final = _stream_full_text
		if texto_final.strip_edges() == "" and _stream_label != null and is_instance_valid(_stream_label):
			var linha: Node = _stream_label          # v1.7: o streaming terminou sem texto: tira a bolha vazia
			while linha != null and linha.get_parent() != chat_log:
				linha = linha.get_parent()
			if linha != null:
				linha.queue_free()
		_stream_label = null
		_stream_full_text = ""
		if brain and texto_final != "":
			brain.emit_signal("akira_speaks", texto_final)


# FEATURE (anexar arquivo/imagem): guarda o caminho escolhido até a
# próxima mensagem ser enviada. Só um por vez, de propósito — mantém
# simples (o mesmo padrão de "attachment" que apps de chat básicos usam).
var _pending_attachment_path: String = ""
# v1.0.1 — VÁRIOS anexos por mensagem (foto colada, foto do disco, texto, zip...). O caminho "principal"
# acima continua existindo (é o primeiro da lista) para não quebrar quem já mexia nessa variável.
var _pending_attachment_paths: Array = []
const MAX_ANEXOS := 8
var _attachment_chip: PanelContainer = null
var _attachment_chip_label: Label = null
var _attachment_strip: HBoxContainer = null # v1.0.2: faixa de cartões (um por anexo), como o Claude faz
var _attachment_thumb: TextureRect = null   # (legado v27 — a miniatura agora é montada em _cartao_de_anexo)
var _attachment_snippet: Label = null       # v27: primeiras linhas do texto/código anexado (dentro do cartão)
var _attachment_dialog: FileDialog = null

const COLADO_LIMITE_CARACTERES := 1500   # v27: texto colado maior que isso vira cartão de anexo
const COLADO_LIMITE_LINHAS := 25
const _EXT_IMAGEM := ["png", "jpg", "jpeg", "webp", "gif", "bmp"]
const _EXT_VIDEO := ["mp4", "webm", "mkv", "mov", "avi", "ogv"]
const _EXT_TEXTO := ["txt", "md", "py", "pyw", "json", "csv", "log", "html", "css", "js", "ts", "c", "cpp", "h", "java",
	"ino", "xml", "yaml", "yml", "sql", "gd", "bat", "ps1", "cs", "go", "rs", "php", "sh", "ini", "cfg", "toml"]


func _tamanho_legivel(bytes: int) -> String:
	if bytes < 1024:
		return str(bytes) + " B"
	if bytes < 1024 * 1024:
		return String.num(bytes / 1024.0, 1) + " KB"
	return String.num(bytes / 1048576.0, 1) + " MB"


# v1.0.2 — PRÉVIA dos anexos (pedido do Anderson: "melhor se fosse do jeito que o Claude faz").
# Antes era UM chip com o texto "2 anexos: nome1, nome2": você não via as imagens e o ✕ apagava tudo.
# Agora é uma FAIXA: um cartão por anexo — miniatura se for imagem, ícone + primeira linha se for texto —
# e cada cartão tem o seu próprio ✕. O nome da função ficou igual porque o resto do arquivo usa ela.
func _mostrar_previa_do_anexo(_caminho: String, _rotulo: String = "") -> void:
	if _attachment_chip == null or _attachment_strip == null:
		return
	_limpar_faixa_de_anexos()
	_attachment_snippet = null
	for p in _pending_attachment_paths:
		_attachment_strip.add_child(_cartao_de_anexo(str(p)))
	if _pending_attachment_paths.is_empty():
		_attachment_chip.visible = false
		return
	_attachment_chip.visible = true
	if _attachment_chip_label:
		var quantos: int = _pending_attachment_paths.size()
		_attachment_chip_label.text = ("1 anexo" if quantos == 1 else str(quantos) + " anexos") + "  ·  clique para ver, ✕ para tirar"


func _limpar_faixa_de_anexos() -> void:
	if _attachment_strip == null:
		return
	for c in _attachment_strip.get_children():
		_attachment_strip.remove_child(c)
		c.queue_free()


func _remover_anexo(caminho: String) -> void:
	_pending_attachment_paths.erase(caminho)
	_pending_attachment_path = str(_pending_attachment_paths[_pending_attachment_paths.size() - 1]) if not _pending_attachment_paths.is_empty() else ""
	_mostrar_previa_do_anexo("", "")


# Um cartão: miniatura/ícone em cima, nome + ✕ embaixo. Clicar no cartão abre a mini janela de prévia.
func _cartao_de_anexo(caminho: String) -> Control:
	var cartao := PanelContainer.new()
	cartao.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_3, 8, BORDER, 1))
	cartao.tooltip_text = caminho.get_file() + "\n" + caminho
	cartao.mouse_filter = Control.MOUSE_FILTER_STOP
	cartao.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
			_pedir_previa(caminho))
	var margem := MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		margem.add_theme_constant_override("margin_" + lado, 6)
	cartao.add_child(margem)
	var coluna := VBoxContainer.new()
	coluna.add_theme_constant_override("separation", 4)
	margem.add_child(coluna)
	var ext: String = caminho.get_extension().to_lower()
	var bytes: int = 0
	if FileAccess.file_exists(caminho):
		var f = FileAccess.open(caminho, FileAccess.READ)
		if f:
			bytes = f.get_length()
			f.close()
	var topo: Control = null
	if ext in _EXT_IMAGEM:
		var img := Image.new()
		if img.load(caminho) == OK:
			var larg: int = img.get_width()
			var alt: int = img.get_height()
			var esc: float = minf(88.0 / maxf(float(larg), 1.0), 64.0 / maxf(float(alt), 1.0))
			if esc < 1.0:
				img.resize(maxi(int(larg * esc), 1), maxi(int(alt * esc), 1), Image.INTERPOLATE_LANCZOS)
			var miniatura := TextureRect.new()
			miniatura.texture = ImageTexture.create_from_image(img)
			miniatura.custom_minimum_size = Vector2(88, 64)
			miniatura.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			miniatura.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			miniatura.mouse_filter = Control.MOUSE_FILTER_IGNORE
			topo = miniatura
	if topo == null:
		var icone = Icones.rect("anexo", TEXT_MUTED, 40)
		icone.custom_minimum_size = Vector2(88, 64)
		topo = icone
	coluna.add_child(topo)
	if ext in _EXT_TEXTO:
		var trecho := Label.new()
		trecho.add_theme_color_override("font_color", Color("9aa3c7"))
		trecho.add_theme_font_size_override("font_size", 9)
		trecho.clip_text = true
		trecho.custom_minimum_size = Vector2(88, 12)
		var f2 = FileAccess.open(caminho, FileAccess.READ)
		if f2:
			var bruto: String = f2.get_buffer(400).get_string_from_utf8()
			f2.close()
			var linhas: PackedStringArray = bruto.split("\n")
			trecho.text = linhas[0].substr(0, 40) if linhas.size() > 0 else ""
		coluna.add_child(trecho)
		_attachment_snippet = trecho
	var rodape := HBoxContainer.new()
	rodape.add_theme_constant_override("separation", 4)
	coluna.add_child(rodape)
	var nome := Label.new()
	nome.text = caminho.get_file()
	nome.clip_text = true
	nome.add_theme_font_size_override("font_size", 10)
	nome.add_theme_color_override("font_color", TEXT_SECOND)
	nome.custom_minimum_size = Vector2(72, 0)
	nome.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nome.tooltip_text = caminho.get_file() + "  ·  " + _tamanho_legivel(bytes)
	rodape.add_child(nome)
	var tirar := _make_button("✕", Color(0, 0, 0, 0), BG_SURFACE_2, TEXT_MUTED)
	tirar.custom_minimum_size = Vector2(20, 20)
	tirar.add_theme_font_size_override("font_size", 11)
	tirar.tooltip_text = "Tirar este anexo"
	tirar.pressed.connect(func(): _remover_anexo(caminho))
	rodape.add_child(tirar)
	return cartao


# v22 — colar print: Ctrl+V com uma IMAGEM na área de transferência vira o anexo da próxima mensagem. Se a
# área de transferência também tiver texto, o campo cola o texto normalmente (Excel, por exemplo, copia os dois).
func _on_input_gui_input(event):
	# v28 — Enter ENVIA; Shift+Enter QUEBRA a linha; setas/Tab/Esc mexem no autocompletar de comandos "/"
	if event is InputEventKey and event.pressed:
		if _autocompletar_ativo():
			if event.keycode == KEY_DOWN:
				_autocompletar_mover(1)
				input_field.accept_event()
				return
			if event.keycode == KEY_UP:
				_autocompletar_mover(-1)
				input_field.accept_event()
				return
			if event.keycode == KEY_ESCAPE:
				_ac_panel.visible = false
				input_field.accept_event()
				return
			if event.keycode == KEY_TAB:
				_autocompletar_escolher(_autocompletar_selecionado())
				input_field.accept_event()
				return
		if (event.keycode == KEY_ENTER or event.keycode == KEY_KP_ENTER) and not event.echo:
			if event.shift_pressed:
				return      # Shift+Enter: o TextEdit insere a quebra de linha sozinho
			if _autocompletar_ativo():
				var i: int = _autocompletar_selecionado()
				if i >= 0 and input_field.text.strip_edges() != str(_ac_filtrados[i].get("cmd", "")):
					_autocompletar_escolher(i)       # "/ima" + Enter completa pra "/imagem " (o Enter seguinte envia)
					input_field.accept_event()
					return
			input_field.accept_event()
			_send()
			return
	if not (event is InputEventKey):
		return
	if not event.pressed or event.echo or event.keycode != KEY_V:
		return
	if not (event.ctrl_pressed or event.meta_pressed):
		return
	# CORREÇÃO (v1.0.1) — ORDEM: aqui, QUALQUER texto na área de transferência fazia a função sair ali mesmo e
	# a imagem nunca era olhada. A Ferramenta de Captura do Windows copia o print JUNTO com o texto dele, então
	# colar um print não anexava nada. Agora: texto LONGO (código, log) ganha da imagem; fora isso, a imagem ganha.
	var colado: String = DisplayServer.clipboard_get() if DisplayServer.clipboard_has() else ""
	if colado.length() > COLADO_LIMITE_CARACTERES or colado.count("\n") > COLADO_LIMITE_LINHAS:
			var pasta_t = OS.get_user_data_dir().path_join("colados")
			DirAccess.make_dir_recursive_absolute(pasta_t)
			var carimbo_t = Time.get_datetime_string_from_system().replace(":", "").replace("-", "").replace("T", "_")
			var caminho_t = pasta_t.path_join("texto_" + carimbo_t + ".txt")
			var arq = FileAccess.open(caminho_t, FileAccess.WRITE)
			if arq:
				arq.store_string(colado)
				arq.close()
				_adicionar_anexo(caminho_t, "texto colado")
				input_field.accept_event()
			return
	if not DisplayServer.clipboard_has_image():
		return
	var img = DisplayServer.clipboard_get_image()
	if img == null or img.is_empty():
		return
	if img.get_width() > 2000:      # prints de tela cheia: reduz pra não pesar na IA
		img.resize(2000, int(float(img.get_height()) * 2000.0 / float(img.get_width())), Image.INTERPOLATE_LANCZOS)
	var pasta = OS.get_user_data_dir().path_join("colados")
	DirAccess.make_dir_recursive_absolute(pasta)
	var carimbo = Time.get_datetime_string_from_system().replace(":", "").replace("-", "").replace("T", "_")
	var caminho = pasta.path_join("print_" + carimbo + ".png")
	if img.save_png(caminho) != OK:
		_add_bubble("⚠ Não consegui guardar a imagem colada.", "ai")
		return
	_adicionar_anexo(caminho, "imagem colada")        # v27: com miniatura · v1.0.1: soma, não substitui
	input_field.accept_event()


# v1.0.1 — colar/escolher VÁRIOS: cada anexo ENTRA na lista em vez de substituir o anterior.
# Era esse o defeito que o Anderson descreveu ("não consigo colocar mais de um arquivo no mesmo prompt").
func _adicionar_anexo(caminho: String, rotulo: String = "") -> void:
	if caminho.is_empty():
		return
	if not _pending_attachment_paths.has(caminho):
		_pending_attachment_paths.append(caminho)
	while _pending_attachment_paths.size() > MAX_ANEXOS:
		_pending_attachment_paths.pop_front()
		_add_bubble("⚠ Máximo de " + str(MAX_ANEXOS) + " anexos por mensagem — o mais antigo saiu.", "ai")
	_pending_attachment_path = caminho
	_mostrar_previa_do_anexo(caminho, rotulo)      # v1.0.2: redesenha a faixa inteira (um cartão por anexo)


func _abrir_seletor_de_anexo():
	# O FileDialog em si só é criado na hora do primeiro clique — de
	# propósito — GDScript não tem try/except, então se alguma coisa der
	# errado montando o seletor de arquivo, isso NÃO pode derrubar a
	# barra de digitar inteira (foi exatamente isso que quebrou numa
	# rodada anterior: um erro montando a tela cortava a função no meio
	# e a barra — campo de texto, mic, botão de enviar — sumia).
	if _attachment_dialog == null:
		_attachment_dialog = FileDialog.new()
		_attachment_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_attachment_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILES      # v1.0.1: escolher vários de uma vez
		# v22: janela de verdade do Windows (igual à de escolher o avatar .vrm). A do Godot abria numa pasta
		# estranha e vazia por causa do filtro.
		_attachment_dialog.use_native_dialog = true
		_attachment_dialog.title = "Anexar arquivo ou imagem"
		_attachment_dialog.add_filter("*.*", "Todos os arquivos")
		_attachment_dialog.add_filter("*.png,*.jpg,*.jpeg,*.webp,*.gif,*.bmp", "Imagens")
		_attachment_dialog.add_filter("*.txt,*.md,*.py,*.pyw,*.json,*.csv,*.log,*.html,*.css,*.js,*.c,*.cpp,*.h,*.java,*.ino,*.xml,*.yaml,*.yml,*.sql,*.gd", "Texto e código")
		_attachment_dialog.size = Vector2i(700, 500)
		var _pics = OS.get_system_dir(OS.SYSTEM_DIR_PICTURES)
		if not _pics.is_empty():
			_attachment_dialog.current_dir = _pics   # onde ficam os prints
		_attachment_dialog.files_selected.connect(func(paths):
			for p in paths:
				_adicionar_anexo(str(p)))                        # v1.0.1: vários arquivos de uma vez
		add_child(_attachment_dialog)
	_attachment_dialog.popup_centered()


# ================= ENTRADA =================
func _build_input_bar() -> PanelContainer:
	var panel = PanelContainer.new()
	panel.custom_minimum_size.y = 64
	panel.add_theme_stylebox_override("panel", _panel_style(BG_BASE))      # v1.7: a caixa fica no fundo da conversa; a pílula é que aparece
	aparencia.registrar("entrada", panel)

	var outer_col = VBoxContainer.new()
	outer_col.add_theme_constant_override("separation", 4)

	# v1.0.2 — FAIXA de anexos no estilo do Claude: um cartão por arquivo, cada um com o seu ✕.
	# Antes era um chip só ("2 anexos: nome1, nome2") e o ✕ apagava TODOS de uma vez.
	_attachment_chip = PanelContainer.new()
	_attachment_chip.visible = false
	_attachment_chip.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 10, BORDER, 1))
	var chip_margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		chip_margin.add_theme_constant_override("margin_" + side, 8)
	_attachment_chip.add_child(chip_margin)
	var chip_coluna = VBoxContainer.new()
	chip_coluna.add_theme_constant_override("separation", 6)
	chip_margin.add_child(chip_coluna)
	var chip_topo = HBoxContainer.new()
	chip_topo.add_theme_constant_override("separation", 8)
	chip_coluna.add_child(chip_topo)
	var chip_label = Label.new()
	chip_label.name = "ChipLabel"
	chip_label.add_theme_color_override("font_color", TEXT_MUTED)
	chip_label.add_theme_font_size_override("font_size", 11)
	chip_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chip_topo.add_child(chip_label)
	_attachment_chip_label = chip_label
	var chip_limpar = _make_button("Limpar tudo", Color(0, 0, 0, 0), BG_SURFACE_3, TEXT_MUTED)
	chip_limpar.custom_minimum_size = Vector2(0, 20)
	chip_limpar.add_theme_font_size_override("font_size", 11)
	chip_limpar.tooltip_text = "Tirar todos os anexos"
	chip_limpar.pressed.connect(func():
		_pending_attachment_path = ""
		_pending_attachment_paths.clear()
		_attachment_snippet = null
		if _attachment_chip:
			_attachment_chip.visible = false
		_limpar_faixa_de_anexos())
	chip_topo.add_child(chip_limpar)
	var chip_rolagem = ScrollContainer.new()
	chip_rolagem.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	chip_rolagem.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	chip_rolagem.custom_minimum_size = Vector2(0, 104)
	chip_coluna.add_child(chip_rolagem)
	_attachment_strip = HBoxContainer.new()
	_attachment_strip.add_theme_constant_override("separation", 8)
	chip_rolagem.add_child(_attachment_strip)
	outer_col.add_child(_attachment_chip)

	# v28 — autocompletar de comandos: digitou "/" e algumas letras, aparece a lista (setas escolhem; Tab/Enter completam)
	_ac_panel = PanelContainer.new()
	_ac_panel.visible = false
	_ac_panel.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 8, CYAN_DIM, 1))
	_ac_lista = ItemList.new()
	_ac_lista.focus_mode = Control.FOCUS_NONE
	_ac_lista.same_column_width = true
	_ac_lista.add_theme_color_override("font_color", TEXT_PRIMARY)
	_ac_lista.add_theme_color_override("font_selected_color", Color("04141a"))
	_ac_lista.add_theme_stylebox_override("panel", _panel_style(Color(0, 0, 0, 0)))
	_ac_lista.item_clicked.connect(func(i, _pos, _btn): _autocompletar_escolher(i))
	_ac_panel.add_child(_ac_lista)
	outer_col.add_child(_ac_panel)

	var hbox = HBoxContainer.new()
	hbox.add_theme_constant_override("separation", 8)
	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 16)
	margin.add_theme_constant_override("margin_right", 16)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_bottom", 12)
	var pilula = PanelContainer.new()                     # v1.7: caixa única arredondada
	_pilula_entrada = pilula
	pilula.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 26, BORDER, 1))
	var pilula_m = MarginContainer.new()
	pilula_m.add_theme_constant_override("margin_left", 10)
	pilula_m.add_theme_constant_override("margin_right", 8)
	pilula_m.add_theme_constant_override("margin_top", 5)
	pilula_m.add_theme_constant_override("margin_bottom", 5)
	pilula_m.add_child(hbox)
	pilula.add_child(pilula_m)
	margin.add_child(pilula)
	_margem_entrada = margin
	outer_col.add_child(margin)
	panel.add_child(outer_col)
	call_deferred("_ajustar_margens_leitura")

	# v28 — TextEdit no lugar do LineEdit: várias linhas, cresce sozinho até ~8 linhas e acompanha a largura da janela.
	# Enter ENVIA · Shift+Enter QUEBRA A LINHA (tratado em _on_input_gui_input).
	input_field = TextEdit.new()
	input_field.placeholder_text = "Escreva ou fale"       # v1.7 (Enter envia · Shift+Enter quebra a linha: no tooltip)
	input_field.tooltip_text = "Enter envia · Shift+Enter quebra a linha"
	input_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input_field.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	input_field.custom_minimum_size.y = 42
	var estilo_normal: StyleBoxFlat = _panel_style(Color(0, 0, 0, 0), 8)       # v1.7: sem borda própria (a pílula já tem)
	var estilo_foco: StyleBoxFlat = _panel_style(Color(0, 0, 0, 0), 8)
	for est in [estilo_normal, estilo_foco]:
		est.content_margin_left = 10
		est.content_margin_right = 10
		est.content_margin_top = 8
		est.content_margin_bottom = 8
	input_field.add_theme_stylebox_override("normal", estilo_normal)
	input_field.add_theme_stylebox_override("focus", estilo_foco)
	input_field.add_theme_color_override("font_color", TEXT_PRIMARY)
	input_field.add_theme_color_override("caret_color", CYAN)
	input_field.add_theme_color_override("font_placeholder_color", TEXT_MUTED)
	input_field.text_changed.connect(_on_entrada_mudou)
	input_field.resized.connect(func(): call_deferred("_ajustar_altura_entrada"))
	input_field.gui_input.connect(_on_input_gui_input)   # v22: Ctrl+V com imagem · v28: Enter/Shift+Enter e autocompletar
	hbox.add_child(input_field)

	# FEATURE (anexar arquivo/imagem): botão de clipe.
	var attach_btn = _make_button("📎", Color(0, 0, 0, 0), BG_SURFACE_3, TEXT_MUTED)
	attach_btn.custom_minimum_size = Vector2(40, 40)
	attach_btn.tooltip_text = "Anexar arquivo ou imagem"
	attach_btn.pressed.connect(_abrir_seletor_de_anexo)
	hbox.add_child(attach_btn)

	# FEATURE (microfone no chat): botão liga/desliga a gravação. Fica
	# ao lado da caixa de texto, sempre visível — é um toggle: aperta
	# pra começar a ouvir, aperta de novo (ou fala e para) pra encerrar
	# e transcrever, preenchendo a caixa de texto pra você revisar antes
	# de mandar.
	mic_btn = _make_button("🎙", Color(0, 0, 0, 0), BG_SURFACE_3, TEXT_MUTED)
	mic_btn.custom_minimum_size = Vector2(40, 40)
	mic_btn.tooltip_text = "Falar por voz"
	mic_btn.pressed.connect(_toggle_mic)
	hbox.add_child(mic_btn)

	var send_btn = _make_button("Enviar", CYAN, CYAN_DIM, Color("04141a"))
	Icones.aplicar(send_btn, "enviar", Color("04141a"))
	send_btn.text = ""                                   # v1.7: botão redondo só com a seta
	send_btn.custom_minimum_size = Vector2(40, 40)
	send_btn.tooltip_text = "Enviar (Enter)"
	for est in ["normal", "hover", "pressed"]:
		send_btn.add_theme_stylebox_override(est, _panel_style(CYAN_DIM if est != "normal" else CYAN, 20))
	send_btn.pressed.connect(_send)
	hbox.add_child(send_btn)
	hbox.move_child(attach_btn, 0)                       # v1.7: o clipe passa para o começo da pílula
	for filho in hbox.get_children():       # v28: a caixa cresce; os botões ficam alinhados embaixo (não esticam junto)
		if filho != input_field and filho is Control:
			filho.size_flags_vertical = Control.SIZE_SHRINK_END

	return panel


func _toggle_mic():
	if not brain:
		return
	if _mic_listening:
		brain.request_mic_stop()
	else:
		brain.request_mic_start()


func _on_mic_state_changed(listening: bool):
	_mic_listening = listening
	if not mic_btn or not is_instance_valid(mic_btn):
		return
	if listening:
		mic_btn.add_theme_color_override("font_color", Color("ff4d4d"))
		_ic(mic_btn, "🎙")
		mic_btn.tooltip_text = "Ouvindo... clique pra parar"
	else:
		mic_btn.add_theme_color_override("font_color", TEXT_MUTED)
		_ic(mic_btn, "🎙")
		mic_btn.tooltip_text = "Falar por voz"


func _on_mic_transcript_received(text: String, enviar: bool = false):
	if text.is_empty():
		return
	# Preenche a caixa de texto com o que foi entendido — o usuário
	# revisa/edita e aperta Enviar, em vez de mandar sem ver.
	if input_field and is_instance_valid(input_field):
		input_field.text = text
		input_field.grab_focus()
		_cursor_no_fim_da_entrada()
		call_deferred("_ajustar_altura_entrada")
		if enviar:
			_send()          # v1.7: conversa por voz ligada (/conversa ligar): envia sozinha, como se tivesse digitado


# v1.7 — aviso visível de que o microfone está em modo conversa: a pílula da caixa de texto ganha contorno laranja
func _on_conversa_estado(estado: String) -> void:
	if _pilula_entrada == null or not is_instance_valid(_pilula_entrada):
		return
	var ativa: bool = estado == "ouvindo" or estado == "pensando"
	_pilula_entrada.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 26, CYAN if ativa else BORDER, 2 if ativa else 1))
	if mic_btn and is_instance_valid(mic_btn):
		mic_btn.tooltip_text = ("Conversa por voz ligada (" + estado + "). /conversa desligar para sair") if ativa else "Falar (ou /conversa ligar)"


func _send():
	var text = input_field.text.strip_edges()
	var anexos: Array = _pending_attachment_paths.duplicate()
	if anexos.is_empty() and not _pending_attachment_path.is_empty():
		anexos.append(_pending_attachment_path)      # segurança: caminho definido fora da lista
	var anexo: String = str(anexos[0]) if anexos.size() > 0 else ""
	if text.is_empty() and anexos.is_empty():
		return
	input_field.text = ""
	if _ac_panel != null:
		_ac_panel.visible = false       # v28
	call_deferred("_ajustar_altura_entrada")
	var texto_balao = text
	if anexos.size() == 1:
		texto_balao = ("📎 " + anexo.get_file() + ("\n" + text if not text.is_empty() else ""))
	elif anexos.size() > 1:
		var nomes: PackedStringArray = []
		for p in anexos:
			nomes.append(str(p).get_file())
		texto_balao = ("📎 " + str(anexos.size()) + " anexos: " + ", ".join(nomes)
			+ ("\n" + text if not text.is_empty() else ""))
	_add_bubble(texto_balao if not texto_balao.is_empty() else "📎 (anexo)", "user")
	for p in anexos:
		var cam: String = str(p)
		if cam.is_empty():
			continue
		if cam.get_extension().to_lower() in _EXT_IMAGEM:
			_on_chat_image(cam, cam.get_file(), "Você")         # v27: a imagem que você mandou aparece na conversa
		else:
			_add_anexo_botao(cam)         # v28: clicar abre a mini janela com a prévia (texto, lista do zip, quadro do vídeo…)
	_pending_attachment_path = ""
	_pending_attachment_paths.clear()
	_attachment_snippet = null
	if _attachment_chip:
		_attachment_chip.visible = false
	_limpar_faixa_de_anexos()          # v1.0.2: zera os cartões da faixa
	if not brain or not brain.has_method("send_chat"):
		_add_bubble("⚠ Erro interno: conector da Zenith não encontrado.", "ai")
		return
	# No PC (sem modo celular) continua exigindo o Cérebro conectado, como sempre foi.
	var celular: bool = OS.get_name() == "Android" or OS.get_cmdline_user_args().has("--layout-celular")
	if not celular and brain.websocket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		_add_bubble("⚠ Não estou conectado ao Cérebro agora — a mensagem não foi enviada. " +
			"Confira se só existe UM Zenith/Godot aberto (feche instâncias antigas) e tente de novo.", "ai")
		return
	brain.send_chat(text, anexo, anexos)      # v1.0.1: manda a lista inteira
	_show_typing()
	_start_response_timeout()


var _timeout_timer: SceneTreeTimer
var _timeout_token: int = 0

# AJUSTE (sem prazo curto pra pensar): 20s era rápido demais — cortava
# o aviso bem no meio de respostas mais longas/complexas ou de IAs
# locais mais lentas, mesmo com tudo funcionando normal. Isso NÃO é
# mais um "deu erro" — é só um lembrete discreto de que ainda tá
# processando, e só aparece depois de um tempo bem mais generoso.
const RESPONSE_SOFT_WARNING_SECONDS := 90.0

func _start_response_timeout():
	_timeout_token += 1
	var my_token = _timeout_token
	_timeout_timer = get_tree().create_timer(RESPONSE_SOFT_WARNING_SECONDS)
	_timeout_timer.timeout.connect(func():
		if my_token == _timeout_token and typing_row and is_instance_valid(typing_row):
			# Continua "pensando" — NÃO esconde o "digitando..." nem
			# cancela nada, só avisa uma vez que tá demorando mais que
			# o normal (útil pra pedidos complexos ou IA local lenta).
			if brain and brain.has_method("is_connected_to_brain") and brain.is_connected_to_brain():
				_add_bubble("⏳ Ainda pensando — pode levar mais um pouco em respostas complexas ou com IAs locais. Se realmente travou, veja o console do Python.", "ai")
			else:
				_add_bubble("⏳ Ainda processando sua resposta... Verifique sua conexão com a internet.", "ai"))


# ================= APROVAÇÃO DE AÇÕES (Pilar 1) =================
func _build_approval_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 14, CYAN, 1))
	card.anchor_left = 0.32
	card.anchor_right = 0.68
	card.anchor_top = 0.3
	card.anchor_bottom = 0.7
	overlay.add_child(card)
	approval_card = card

	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 10)
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 20)
	margin.add_child(vbox)
	card.add_child(margin)

	var title = Label.new()
	title.text = "⚠  Confirmação necessária"
	title.add_theme_color_override("font_color", Color("ffb84d"))
	title.add_theme_font_size_override("font_size", 16)
	vbox.add_child(title)

	var desc_label = Label.new()
	desc_label.name = "DescLabel"
	desc_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc_label.add_theme_color_override("font_color", TEXT_PRIMARY)
	vbox.add_child(desc_label)

	var preview_label = Label.new()
	preview_label.name = "PreviewLabel"
	preview_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	preview_label.add_theme_color_override("font_color", TEXT_SECOND)
	preview_label.add_theme_font_size_override("font_size", 11)
	vbox.add_child(preview_label)

	var btn_row = HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 10)
	vbox.add_child(btn_row)

	var deny_btn = _make_button("Negar", BG_SURFACE_2, RED)
	deny_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_row.add_child(deny_btn)

	var approve_btn = _make_button("Aprovar", GREEN, Color("00c090"), Color("042014"))
	approve_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_row.add_child(approve_btn)

	overlay.set_meta("desc_label", desc_label)
	overlay.set_meta("preview_label", preview_label)
	overlay.set_meta("deny_btn", deny_btn)
	overlay.set_meta("approve_btn", approve_btn)

	return overlay


func _on_approval_request(request_id: String, kind: String, description: String, preview: String):
	var desc_label: Label = approval_overlay.get_meta("desc_label")
	var preview_label: Label = approval_overlay.get_meta("preview_label")
	var deny_btn: Button = approval_overlay.get_meta("deny_btn")
	var approve_btn: Button = approval_overlay.get_meta("approve_btn")

	desc_label.text = "[" + kind.to_upper() + "] " + description
	preview_label.text = preview

	for s in [deny_btn.pressed, approve_btn.pressed]:
		for c in s.get_connections():
			s.disconnect(c["callable"])

	deny_btn.pressed.connect(func():
		_hide_overlay(approval_overlay)
		if brain: brain.send_approval_response(request_id, false))
	approve_btn.pressed.connect(func():
		_hide_overlay(approval_overlay)
		if brain: brain.send_approval_response(request_id, true))

	_show_overlay(approval_overlay, approval_card)


# ================= PRIMEIRO LOGIN (pen drive / instalação zerada) =================
# FEATURE: numa cópia nova do Zenith (sem config/settings.json, ou com
# ele deliberadamente zerado antes de ir pro pen drive — ver
# prepare_pendrive.py na raiz do projeto), "onboarding_done" começa
# False. Essa tela aparece UMA vez, antes do chat normal, e deixa a
# pessoa manter a Zenith padrão ou criar a IA dela do zero — nome,
# como ela deve te chamar, e (opcional) como ela deve ser. Depois
# disso fica salvo só NAQUELE computador; não afeta outras cópias.
var onboarding_card: Control
var _onboarding_shown_once := false

func _build_onboarding_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.75)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 16, CYAN, 1))
	# v20: antes a largura/altura eram ancoradas em % da janela e o conteúdo (dentro de um
	# ScrollContainer) encolhia pro tamanho mínimo — ficava um fiapo de ~250 px no meio de um
	# cartão enorme, e mudava de jeito conforme o tamanho da janela. Agora o cartão tem tamanho
	# calculado (com mínimo e máximo) e é recentralizado quando a janela muda; o conteúdo ocupa
	# a largura toda.
	overlay.add_child(card)
	onboarding_card = card
	overlay.resized.connect(func(): _layout_onboarding_card(overlay, card))

	var scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	card.add_child(scroll)
	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 10)
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 24)
	margin.add_child(vbox)
	margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	margin.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(margin)

	var title = Label.new()
	title.text = "✦"
	title.add_theme_color_override("font_color", CYAN)
	title.add_theme_font_size_override("font_size", 40)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.add_child(title)

	var title2 = Label.new()
	title2.text = "Bem-vindo(a) ao Zenith"
	title2.add_theme_color_override("font_color", TEXT_PRIMARY)
	title2.add_theme_font_size_override("font_size", 22)
	title2.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title2.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vbox.add_child(title2)

	var subtitle = Label.new()
	subtitle.text = ("Essa é a primeira vez rodando neste computador. Pode manter a Zenith " +
		"como está, ou criar a SUA própria IA agora — nome, como ela deve te chamar e " +
		"(se quiser) a personalidade dela. Dá pra mudar tudo de novo depois em " +
		"Configurações > Identidade.")
	subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	subtitle.add_theme_color_override("font_color", TEXT_SECOND)
	subtitle.add_theme_font_size_override("font_size", 12)
	vbox.add_child(subtitle)

	var sep = HSeparator.new()
	vbox.add_child(sep)

	var form_card = _card_start(vbox, "Personalize (ou deixe como está)", "◆")

	_section(form_card, "Nome da sua IA")
	var name_field = LineEdit.new()
	name_field.placeholder_text = "Zenith"
	name_field.add_theme_stylebox_override("normal", _panel_style(BG_SURFACE_2, 8))
	name_field.add_theme_color_override("font_color", TEXT_PRIMARY)
	form_card.add_child(name_field)

	_section(form_card, "Seu nome (como ela deve te chamar)")
	var user_field = LineEdit.new()
	user_field.placeholder_text = "Usuário"
	user_field.add_theme_stylebox_override("normal", _panel_style(BG_SURFACE_2, 8))
	user_field.add_theme_color_override("font_color", TEXT_PRIMARY)
	form_card.add_child(user_field)

	_section(form_card, "Como ela deve ser (opcional)")
	var desc_field = TextEdit.new()
	desc_field.custom_minimum_size.y = 90
	desc_field.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	desc_field.placeholder_text = "Ex: bem-humorada, direta, curiosa por ciência... (deixe em branco pra usar o padrão)"
	form_card.add_child(desc_field)

	var btn_row = HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 10)
	vbox.add_child(btn_row)

	var quick_btn = _make_button("Usar Zenith (padrão)", BG_SURFACE_2, BG_SURFACE_3)
	quick_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_row.add_child(quick_btn)

	var start_btn = _make_button("Começar", CYAN, CYAN_DIM, Color("04141a"))
	start_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btn_row.add_child(start_btn)

	quick_btn.pressed.connect(func():
		if brain:
			brain.save_settings({"persona_name": "Zenith", "onboarding_done": true})
		_hide_overlay(onboarding_overlay))

	start_btn.pressed.connect(func():
		var nm = name_field.text.strip_edges()
		if brain:
			brain.save_settings({
				"persona_name": nm if not nm.is_empty() else "Zenith",
				"user_name": user_field.text.strip_edges(),
				"persona_description": desc_field.text.strip_edges(),
				"onboarding_done": true,
			})
		_hide_overlay(onboarding_overlay))

	_layout_onboarding_card(overlay, card)
	overlay.set_meta("name_field", name_field)
	overlay.set_meta("user_field", user_field)
	overlay.set_meta("desc_field", desc_field)
	return overlay


# v20 — tamanho e posição do cartão de boas-vindas: ~62% x 80% da janela, com mínimo (cabe
# o formulário) e máximo (não vira um lençol em tela grande); em janela pequena, encosta
# nas bordas em vez de estourar.
func _layout_onboarding_card(overlay: Control, card: Control):
	if overlay == null or card == null or not is_instance_valid(overlay) or not is_instance_valid(card):
		return
	var s: Vector2 = overlay.size
	if s.x < 10.0 or s.y < 10.0:
		return
	var w = clampf(s.x * 0.62, 520.0, 800.0)
	var h = clampf(s.y * 0.80, 440.0, 780.0)
	w = minf(w, maxf(s.x - 24.0, 320.0))
	h = minf(h, maxf(s.y - 24.0, 320.0))
	card.size = Vector2(w, h)
	card.position = ((s - card.size) / 2.0).floor()
	card.pivot_offset = card.size / 2.0


func _maybe_show_onboarding(settings: Dictionary):
	if _onboarding_shown_once:
		return
	if settings.get("onboarding_done", false):
		return
	_onboarding_shown_once = true
	# Pré-preenche com o que já existir (útil se alguém reabrir essa
	# tela manualmente no futuro, ou se a config trouxer algo parcial).
	var name_field: LineEdit = onboarding_overlay.get_meta("name_field")
	var user_field: LineEdit = onboarding_overlay.get_meta("user_field")
	if name_field:
		name_field.text = String(settings.get("persona_name", ""))
	if user_field:
		user_field.text = String(settings.get("user_name", ""))
	_layout_onboarding_card(onboarding_overlay, onboarding_card)
	_show_overlay(onboarding_overlay, onboarding_card)


# ================= MEMÓRIAS ("o que ela lembra") =================
var memories_card: Control
var memories_list_box: VBoxContainer

func _build_memories_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.65)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	dim.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed:
			_hide_overlay(memories_overlay))
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 16, CYAN, 1))
	card.anchor_left = 0.22
	card.anchor_right = 0.78
	card.anchor_top = 0.1
	card.anchor_bottom = 0.9
	overlay.add_child(card)
	memories_card = card

	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 10)
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 20)
	margin.add_child(vbox)
	card.add_child(margin)

	var header = HBoxContainer.new()
	vbox.add_child(header)
	var title = Label.new()
	title.text = "🧠 O que " + persona_name + " lembra"
	title.add_theme_color_override("font_color", CYAN)
	title.add_theme_font_size_override("font_size", 18)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_btn = _make_button("Fechar", BG_SURFACE_2, BG_SURFACE_3)
	close_btn.pressed.connect(func(): _hide_overlay(memories_overlay))
	header.add_child(close_btn)

	_hint(vbox, "Trechos de conversas antigas que ficaram guardados na memória de longo " +
		"prazo — ela usa isso sozinha pra puxar contexto quando faz sentido, sem você " +
		"precisar pedir. Clique em \"Perguntar sobre isso\" pra testar na prática.")

	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vbox.add_child(scroll)
	memories_list_box = VBoxContainer.new()
	memories_list_box.add_theme_constant_override("separation", 8)
	memories_list_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(memories_list_box)

	return overlay


func _on_memories_list(items: Array):
	for c in memories_list_box.get_children():
		c.queue_free()

	if items.is_empty():
		var empty_lbl = Label.new()
		empty_lbl.text = ("Ainda não tem nada guardado — ela vai lembrar coisas conforme " +
			"vocês forem conversando.")
		empty_lbl.add_theme_color_override("font_color", TEXT_MUTED)
		empty_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		memories_list_box.add_child(empty_lbl)
		return

	for item in items:
		var texto = String(item.get("text", ""))
		var quando = String(item.get("timestamp", ""))
		var tipo = String(item.get("mem_type", "chat_raw"))

		var row = PanelContainer.new()
		row.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 8))
		memories_list_box.add_child(row)

		var inner = VBoxContainer.new()
		inner.add_theme_constant_override("separation", 4)
		var pad = MarginContainer.new()
		for side in ["left", "right", "top", "bottom"]:
			pad.add_theme_constant_override("margin_" + side, 10)
		pad.add_child(inner)
		row.add_child(pad)

		# FEATURE (memória mais organizada): selo mostrando se é um fato
		# permanente, um resumo de conversas antigas, ou conversa crua
		# recente — só cosmético, não muda nada por baixo dos panos.
		var topo_row = HBoxContainer.new()
		topo_row.add_theme_constant_override("separation", 6)
		var selo = Label.new()
		match tipo:
			"fact":
				selo.text = "⭐ Fato lembrado"
				selo.add_theme_color_override("font_color", CYAN)
			"chat_summary":
				selo.text = "📎 Resumo de conversas antigas"
				selo.add_theme_color_override("font_color", TEXT_MUTED)
			_:
				selo.text = "💬 Conversa"
				selo.add_theme_color_override("font_color", TEXT_MUTED)
		selo.add_theme_font_size_override("font_size", 10)
		topo_row.add_child(selo)
		inner.add_child(topo_row)

		if quando != "":
			var quando_lbl = Label.new()
			quando_lbl.text = quando.replace("T", " ").split(".")[0]
			quando_lbl.add_theme_color_override("font_color", TEXT_MUTED)
			quando_lbl.add_theme_font_size_override("font_size", 10)
			inner.add_child(quando_lbl)

		var texto_lbl = Label.new()
		texto_lbl.text = texto
		texto_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		texto_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
		texto_lbl.add_theme_font_size_override("font_size", 12)
		inner.add_child(texto_lbl)

		var ask_btn = _make_button("Perguntar sobre isso", BG_SURFACE_3, CYAN_DIM, TEXT_PRIMARY)
		ask_btn.custom_minimum_size.y = 26
		# Pega só um pedacinho da lembrança pra não jogar o texto
		# inteiro de volta pra ela — é só um gatilho pro recall entrar
		# em ação, igual perguntaria numa conversa normal.
		var trecho = texto.substr(0, 60)
		ask_btn.pressed.connect(func():
			_hide_overlay(memories_overlay)
			if input_field:
				input_field.text = "Você lembra dessa conversa? \"" + trecho + "...\""
				input_field.grab_focus())
		inner.add_child(ask_btn)


# ================= CONFIGURAÇÕES =================
func _build_settings_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.7)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 14, BORDER, 1))
	# Auto-ajustável: ancorado em porcentagem da janela, não pixel fixo —
	# redimensiona sozinho se a janela for redimensionada.
	card.anchor_left = 0.08
	card.anchor_right = 0.92
	card.anchor_top = 0.05
	card.anchor_bottom = 0.95
	overlay.add_child(card)
	settings_card = card

	var outer_vbox = VBoxContainer.new()
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	margin.add_child(outer_vbox)
	card.add_child(margin)

	var header = HBoxContainer.new()
	var htitle = Label.new()
	htitle.text = "Configurações"
	htitle.add_theme_color_override("font_color", CYAN)
	htitle.add_theme_font_size_override("font_size", 18)
	htitle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(htitle)
	var close_btn = Button.new()
	close_btn.text = "✕"
	close_btn.flat = true
	close_btn.add_theme_color_override("font_color", TEXT_MUTED)
	close_btn.pressed.connect(func(): _hide_overlay(settings_overlay))
	header.add_child(close_btn)
	outer_vbox.add_child(header)

	var tabs = TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	outer_vbox.add_child(tabs)
	settings_tabs = tabs

	tabs.add_child(_settings_tab_identity())
	tabs.add_child(_settings_tab_voice())
	tabs.add_child(_settings_tab_body())
	tabs.add_child(_settings_tab_appearance())
	tabs.add_child(_settings_tab_estudio())          # v1.1 — temas, cores e efeitos animados por área
	tabs.add_child(_settings_tab_chaves())           # v1.1 — ÚNICA tela de chaves e de "Minhas IAs"
	tabs.add_child(_settings_tab_email())            # v1.20 — Ponte por E-mail (Celular <-> PC)
	tabs.tab_changed.connect(func(i):
		var t_nome = settings_tabs.get_tab_title(i)
		if t_nome == "Chaves & IAs" and chaves_page:
			chaves_page.pedir()
		elif t_nome == "Ponte E-mail" and email_page:
			email_page.pedir_dados())
	tabs.add_child(_settings_tab_permissions())
	tabs.add_child(_settings_tab_about())          # v1.0 — quem criou o Zenith
	# O nome de um nó não aceita "/" (virava "Corpo _ VRM"); o título da aba é definido à parte.
	tabs.set_tab_title(2, "Corpo / VRM")

	var save_btn = _make_button("Salvar e Aplicar", CYAN, CYAN_DIM, Color("04141a"))
	save_btn.custom_minimum_size.y = 40
	save_btn.pressed.connect(_save_settings)
	outer_vbox.add_child(save_btn)

	return overlay


func _labeled_field(parent: VBoxContainer, label_text: String, key: String, secret: bool = false) -> LineEdit:
	var field = _unregistered_field(parent, label_text, secret)
	settings_fields[key] = field
	return field


# Igual _labeled_field, mas SEM registrar em settings_fields — pra
# campos avulsos que não fazem parte do "Salvar" geral das
# Configurações (ex.: o formulário de "+ Adicionar Nova IA", que manda
# os dados por uma ação própria em vez do fluxo normal de save). Usar
# _labeled_field com key="" pra isso seria um bug: todo campo com
# key="" cairia no MESMO slot do dicionário e vazaria um valor
# imprevisível pro save geral.
func _unregistered_field(parent: VBoxContainer, label_text: String, secret: bool = false) -> LineEdit:
	var lbl = Label.new()
	lbl.text = label_text
	lbl.add_theme_color_override("font_color", TEXT_SECOND)
	lbl.add_theme_font_size_override("font_size", 11)
	parent.add_child(lbl)

	var field = LineEdit.new()
	field.secret = secret
	field.add_theme_stylebox_override("normal", _panel_style(BG_SURFACE_2, 6))
	field.add_theme_color_override("font_color", TEXT_PRIMARY)
	parent.add_child(field)
	return field


# Campo + botão "Procurar..." que abre o Explorer de verdade (FileDialog
# nativo do sistema), igual em qualquer aplicativo profissional — em vez
# de o usuário ter que colar o caminho completo na mão.
func _labeled_field_with_browse(parent: VBoxContainer, label_text: String, key: String, filters: PackedStringArray) -> LineEdit:
	var field = _labeled_field(parent, label_text, key)

	var row = HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)

	var spacer = Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)

	var browse_btn = _make_button("Procurar...", BG_SURFACE_2, BG_SURFACE_3)
	browse_btn.custom_minimum_size = Vector2(110, 28)
	browse_btn.pressed.connect(func(): _open_file_dialog(field, filters))
	row.add_child(browse_btn)

	return field


func _get_file_dialog() -> FileDialog:
	if _file_dialog and is_instance_valid(_file_dialog):
		return _file_dialog
	_file_dialog = FileDialog.new()
	_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	_file_dialog.use_native_dialog = true   # Explorer de verdade do Windows, não a UI do Godot
	_file_dialog.size = Vector2i(760, 520)
	get_tree().root.add_child.call_deferred(_file_dialog)
	_file_dialog.file_selected.connect(func(path):
		# CORREÇÃO (painel RVC "perde a referência" ao trocar o modelo):
		# só existe UM FileDialog, reaproveitado por todos os campos
		# "Procurar..." (VRM, modelo RVC, índice RVC, papel de parede).
		# Sem checar is_instance_valid, se o campo alvo guardado em
		# _file_dialog_target_field tivesse sido liberado da memória
		# entre o clique em "Procurar..." e a escolha do arquivo, esta
		# linha quebrava o callback com um nó já liberado — e a aba
		# travava/sumia.
		if _file_dialog_target_field and is_instance_valid(_file_dialog_target_field):
			_file_dialog_target_field.text = path
		else:
			push_warning("[Zenith] Campo de destino não existe mais — seleção de arquivo ignorada.")
		_file_dialog_target_field = null)
	return _file_dialog


func _open_file_dialog(target_field: LineEdit, filters: PackedStringArray, mode: FileDialog.FileMode = FileDialog.FILE_MODE_OPEN_FILE):
	_file_dialog_target_field = target_field
	var dlg = _get_file_dialog()
	dlg.file_mode = mode
	dlg.clear_filters()
	for f in filters:
		dlg.add_filter(f)
	dlg.popup_centered()


# v14 — fim de uma ação em cadeia: se a Central NÃO está em foco, pisca o
# ícone na barra de tarefas (aviso que não depende de nenhuma biblioteca)
# e devolve "toast" pro Cérebro mostrar a notificação nativa do Windows
# (se a lib opcional `plyer` estiver instalada; senão fica só o piscar).
func _on_akira_notify(title, body):
	if has_focus():
		return
	request_attention()
	if brain and brain.has_method("send_to_brain"):
		brain.send_to_brain({"action": "toast", "title": str(title), "body": str(body)})


# ==========================================
# v13 — TELA DE CARREGAMENTO DOS AVATARES
# ==========================================
func _build_avatar_loading_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.72)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 16, CYAN, 1))
	card.anchor_left = 0.24
	card.anchor_right = 0.76
	card.anchor_top = 0.3
	card.anchor_bottom = 0.7
	overlay.add_child(card)
	avatar_loading_card = card

	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 22)
	card.add_child(margin)

	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 12)
	margin.add_child(vbox)

	avatar_loading_title = Label.new()
	avatar_loading_title.text = "Carregando avatares..."
	avatar_loading_title.add_theme_font_size_override("font_size", 18)
	avatar_loading_title.add_theme_color_override("font_color", CYAN)
	vbox.add_child(avatar_loading_title)

	avatar_loading_bar = ProgressBar.new()
	avatar_loading_bar.min_value = 0.0
	avatar_loading_bar.max_value = 100.0
	avatar_loading_bar.show_percentage = false
	avatar_loading_bar.custom_minimum_size = Vector2(0, 14)
	avatar_loading_bar.add_theme_stylebox_override("background", _panel_style(BG_SURFACE_3, 7))
	avatar_loading_bar.add_theme_stylebox_override("fill", _panel_style(CYAN, 7))
	vbox.add_child(avatar_loading_bar)

	avatar_loading_status = Label.new()
	avatar_loading_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	avatar_loading_status.add_theme_color_override("font_color", TEXT_PRIMARY)
	vbox.add_child(avatar_loading_status)

	avatar_loading_report = Label.new()
	avatar_loading_report.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	avatar_loading_report.add_theme_font_size_override("font_size", 12)
	avatar_loading_report.add_theme_color_override("font_color", TEXT_MUTED)
	vbox.add_child(avatar_loading_report)

	var botoes = HBoxContainer.new()
	botoes.add_theme_constant_override("separation", 8)
	avatar_loading_manual_btn = _make_button("✓  Já importei — verificar agora", CYAN, CYAN_DIM, Color("04141a"))
	avatar_loading_manual_btn.visible = false
	avatar_loading_manual_btn.pressed.connect(_forcar_verificacao_manual)
	botoes.add_child(avatar_loading_manual_btn)
	avatar_loading_close_btn = _make_button("Fechar", BG_SURFACE_2, BG_SURFACE_3, TEXT_PRIMARY)
	avatar_loading_close_btn.pressed.connect(_fechar_tela_avatares)
	botoes.add_child(avatar_loading_close_btn)
	vbox.add_child(botoes)
	return overlay

func _abrir_tela_avatares(titulo: String, status: String, texto_botao: String, mostrar_manual: bool = false):
	avatar_loading_title.text = titulo
	avatar_loading_status.text = status
	avatar_loading_report.text = ""
	avatar_loading_bar.value = 0.0
	avatar_loading_close_btn.text = texto_botao
	avatar_loading_manual_btn.visible = mostrar_manual
	if not avatar_loading_overlay.visible or avatar_loading_overlay.modulate.a < 0.5:
		_show_overlay(avatar_loading_overlay, avatar_loading_card)

# Sempre dá pra fechar/cancelar — a tela nunca prende o app.
func _fechar_tela_avatares():
	_avatar_ui_modo = ""
	_hide_overlay(avatar_loading_overlay)
	_refresh_project_avatar_list()

func _iniciar_pre_carregamento_avatares(forcar: bool):
	if not akira_body or not akira_body.has_method("start_avatar_preload"):
		return
	var total: int = akira_body.start_avatar_preload(forcar)
	if total <= 0:
		_refresh_project_avatar_list()
		return
	_avatar_ui_modo = "preload"
	_abrir_tela_avatares("Carregando avatares...", "Preparando...", "Pular", false)

# v15 — mensagem muda com o tempo de espera. Nos primeiros segundos é só
# o aviso normal; depois de um tempo, vira dica específica (clicar na
# janela do EDITOR em si, não na Central nem no avatar); ainda mais
# depois, sugere reimportar manualmente pelo painel Arquivos do editor
# (clique direito > Reimportar), caso o foco sozinho não seja suficiente.
func _texto_aguardando_import(segundos: float) -> String:
	if segundos < 8.0:
		return ("Volte pra janela do EDITOR do Godot (a que tem \"- Godot Engine\" no título) — " +
			"ele importa o arquivo sozinho quando ela ganha foco. Clicar aqui na Central ou no " +
			"avatar não conta, tem que ser a janela do EDITOR mesmo.")
	elif segundos < 25.0:
		return ("Ainda esperando? Clique bem na BARRA DE TÍTULO da janela do Editor do Godot " +
			"(não nesta janela) pra garantir que ela ficou em foco de verdade — é isso que faz " +
			"ele notar o arquivo novo. Se já clicou e nada mudou, dá pra clicar em \"Já importei\" " +
			"abaixo e ver o que a verificação encontra.")
	else:
		return ("Ainda não importou? No painel \"Arquivos\" do editor, clique com o botão direito " +
			"na pasta addons/avatars e escolha \"Reimportar\" (ou \"Rastrear novos arquivos\"), " +
			"depois clique em \"Já importei\" abaixo. Rodando pelo .exe exportado, isso não se " +
			"aplica — lá é preciso adicionar pelo editor e reexportar o .pck.")

# v15 — saída manual: não espera mais o editor "avisar" sozinho, só
# manda verificar como está AGORA. Se ainda não importou, a verificação
# mesmo mostra isso com clareza (⚠), em vez de um ciclo sem fim e sem
# explicação.
func _forcar_verificacao_manual():
	_avatar_ui_modo = "preload"
	akira_body.start_avatar_preload(false)
	avatar_loading_title.text = "Verificando..."
	avatar_loading_status.text = "Preparando..."
	avatar_loading_manual_btn.visible = false

func _tick_avatar_ui(delta: float):
	if not (akira_body and akira_body.has_method("poll_avatar_preload")):
		_avatar_ui_modo = ""
		return
	if _avatar_ui_modo == "aguardando_import":
		# barra "vai e volta" (não dá pra saber o andamento da importação do editor)
		avatar_loading_bar.value = fmod(float(Time.get_ticks_msec()) / 12.0, 100.0)
		_avatar_import_elapsed += delta
		avatar_loading_status.text = _texto_aguardando_import(_avatar_import_elapsed)
		_avatar_import_timer += delta
		if _avatar_import_timer >= 0.5:
			_avatar_import_timer = 0.0
			if akira_body.is_avatar_import_ready(_avatar_import_path):
				akira_body.start_avatar_preload(false)
				_avatar_ui_modo = "preload"
				avatar_loading_title.text = "Verificando o avatar novo..."
				avatar_loading_close_btn.text = "Pular"
				avatar_loading_manual_btn.visible = false
		return
	var st: Dictionary = akira_body.poll_avatar_preload()
	avatar_loading_bar.value = float(st["fracao"]) * 100.0
	if st["ativo"]:
		avatar_loading_status.text = "%s   (%d/%d)" % [st["atual"], mini(int(st["feitos"]) + 1, int(st["total"])), int(st["total"])]
		return
	# terminou
	_avatar_ui_modo = ""
	avatar_loading_bar.value = 100.0
	var linhas: Array = []
	var falhou := false
	for a in akira_body.list_project_avatars():
		var stt: Dictionary = akira_body.get_avatar_status(String(a["path"]))
		if stt.is_empty():
			continue
		if stt["ok"]:
			linhas.append("✓ %s — %s" % [a["nome"], stt["info"]])
		else:
			falhou = true
			linhas.append("⚠ %s — %s" % [a["nome"], stt["info"]])
	avatar_loading_report.text = "\n".join(linhas)
	_refresh_project_avatar_list()
	if falhou:
		avatar_loading_title.text = "Terminou, mas tem avatar com problema"
		avatar_loading_status.text = "Veja abaixo. Se acabou de adicionar, espere o Godot terminar de importar e clique em \"Verificar de novo\"."
		avatar_loading_close_btn.text = "Fechar"
	else:
		avatar_loading_title.text = "Tudo carregado ✓"
		avatar_loading_status.text = "Todos os avatares passaram na verificação."
		avatar_loading_close_btn.text = "Fechar"
		get_tree().create_timer(1.6).timeout.connect(_fechar_se_tudo_ok)

# Fecha sozinha a tela de carregamento 1,6 s depois de "Tudo carregado ✓" —
# só se nada mudou nesse meio tempo (ex.: você começou a adicionar outro).
func _fechar_se_tudo_ok():
	if _avatar_ui_modo == "" and avatar_loading_overlay.visible and avatar_loading_title.text == "Tudo carregado ✓":
		_hide_overlay(avatar_loading_overlay)

func _abrir_seletor_avatar_projeto():
	if _avatar_project_dialog == null:
		_avatar_project_dialog = FileDialog.new()
		_avatar_project_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_avatar_project_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		_avatar_project_dialog.use_native_dialog = true
		_avatar_project_dialog.add_filter("*.vrm", "Modelo VRM")
		_avatar_project_dialog.size = Vector2i(760, 520)
		_avatar_project_dialog.file_selected.connect(_adicionar_avatar_ao_projeto)
		add_child(_avatar_project_dialog)
	_avatar_project_dialog.popup_centered()

func _adicionar_avatar_ao_projeto(origem: String):
	# Dentro do editor (F5), o próprio Godot importa sozinho (fluxo de sempre,
	# desde o v13). FORA do editor (rodando o .exe), essa API não existe pro jogo
	# em si — v18: o CÉREBRO (Python) faz tudo via linha de comando do Godot
	# (--headless --import / --export-pack), sem nada pra configurar.
	if OS.has_feature("editor"):
		if not akira_body or not akira_body.has_method("add_avatar_to_project"):
			_add_bubble("⚠ Corpo/avatar não está conectado agora.", "ai")
			return
		var r: Dictionary = akira_body.add_avatar_to_project(origem)
		if not r["ok"]:
			_add_bubble("⚠ " + String(r["msg"]), "ai")
			return
		_avatar_import_path = String(r["path"])
		_avatar_import_elapsed = 0.0
		if akira_body.is_avatar_import_ready(_avatar_import_path):
			akira_body.start_avatar_preload(false)
			_avatar_ui_modo = "preload"
			_abrir_tela_avatares("Verificando o avatar novo...", "Preparando...", "Pular", false)
		else:
			_avatar_ui_modo = "aguardando_import"
			_abrir_tela_avatares("Copiado! Aguardando o Godot importar...",
				_texto_aguardando_import(0.0), "Cancelar", true)
	else:
		if not (brain and brain.has_method("send_to_brain")):
			_add_bubble("⚠ Cérebro não está conectado agora.", "ai")
			return
		# v18 — sem nada pra configurar: o Cérebro acha o Godot sozinho, copia o .vrm
		# pra res://addons/avatars, importa, reempacota e reinicia o Corpo. Ele mesmo
		# avisa no chat cada etapa (e o que faltar, se faltar).
		brain.send_to_brain({"action": "import_vrm_python", "path": origem})

# v18 — acha, entre os avatares do projeto, o que tem o mesmo nome do arquivo
# salvo ("D:/x/Cypher.vrm" -> res://addons/avatars/Cypher.vrm). "" = não tem.
func _resolver_avatar_salvo(caminho: String) -> String:
	if not (akira_body and akira_body.has_method("list_project_avatars")):
		return ""
	var base: String = caminho.replace("\\", "/").get_file().get_basename().to_lower()
	for a in akira_body.list_project_avatars():
		if String(a["nome"]).to_lower() == base:
			return String(a["path"])
	return ""

func _reverificar_avatares():
	_iniciar_pre_carregamento_avatares(true)

func _refresh_project_avatar_list():
	if not _project_avatar_list_box:
		return
	for c in _project_avatar_list_box.get_children():
		c.queue_free()
	var avatares: Array = []
	if akira_body and akira_body.has_method("list_project_avatars"):
		avatares = akira_body.list_project_avatars()
	if avatares.is_empty():
		var vazio = Label.new()
		vazio.text = "(nenhum avatar importado encontrado em res://addons/avatars/)"
		vazio.add_theme_color_override("font_color", TEXT_MUTED)
		vazio.add_theme_font_size_override("font_size", 11)
		_project_avatar_list_box.add_child(vazio)
		return
	var em_uso = str(akira_body.get("_current_vrm_path")) if akira_body else ""
	for a in avatares:
		var row = HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		var lbl = Label.new()
		lbl.text = String(a["nome"]) + ("   ● em uso" if em_uso == String(a["path"]) else "")
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lbl.add_theme_color_override("font_color", GREEN if em_uso == String(a["path"]) else TEXT_PRIMARY)
		row.add_child(lbl)
		# v13 — resultado da verificação (✓ carregou bonitinho / ⚠ problema)
		var stt: Dictionary = akira_body.get_avatar_status(String(a["path"])) if akira_body and akira_body.has_method("get_avatar_status") else {}
		var st_lbl = Label.new()
		st_lbl.add_theme_font_size_override("font_size", 11)
		if stt.is_empty():
			st_lbl.text = "não verificado"
			st_lbl.add_theme_color_override("font_color", TEXT_MUTED)
		elif stt["ok"]:
			st_lbl.text = "✓ " + String(stt["info"])
			st_lbl.add_theme_color_override("font_color", GREEN)
		else:
			st_lbl.text = "⚠ " + String(stt["info"])
			st_lbl.add_theme_color_override("font_color", RED)
			st_lbl.tooltip_text = String(stt["info"])
		row.add_child(st_lbl)
		var usar_btn = _make_button("Usar", CYAN, CYAN_DIM, Color("04141a"))
		usar_btn.custom_minimum_size = Vector2(64, 26)
		if not stt.is_empty() and not stt["ok"]:
			usar_btn.disabled = true
		usar_btn.pressed.connect(_usar_avatar_do_projeto.bind(String(a["path"]), String(a["nome"])))
		row.add_child(usar_btn)
		_project_avatar_list_box.add_child(row)

func _usar_avatar_do_projeto(caminho: String, nome: String):
	if settings_fields.has("vrm_model_path"):
		settings_fields["vrm_model_path"].text = caminho
	if not akira_body or not akira_body.has_method("reload_vrm"):
		_add_bubble("⚠ Corpo/avatar não está conectado agora.", "ai")
		return
	var erro = akira_body.reload_vrm(caminho)
	_add_bubble(("⚠ VRM: " + erro) if erro != "" else ("✓ Usando \"" + nome + "\" (importado pelo Godot). Clique em \"Salvar e Aplicar\" pra isso valer na próxima vez que abrir o Zenith."), "ai")
	_refresh_project_avatar_list()

# FEATURE (pasta de dados única): igual _labeled_field_with_browse, mas
# pra ESCOLHER UMA PASTA em vez de um arquivo — reaproveita o mesmo
# FileDialog compartilhado, só muda o modo pra FILE_MODE_OPEN_DIR nesta
# chamada específica.
func _labeled_folder_with_browse(parent: VBoxContainer, label_text: String, key: String) -> LineEdit:
	var field = _labeled_field(parent, label_text, key)

	var row = HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)

	var spacer = Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)

	var browse_btn = _make_button("Escolher pasta...", BG_SURFACE_2, BG_SURFACE_3)
	browse_btn.custom_minimum_size = Vector2(130, 28)
	browse_btn.pressed.connect(func(): _open_file_dialog(field, PackedStringArray(), FileDialog.FILE_MODE_OPEN_DIR))
	row.add_child(browse_btn)

	return field


# v1.11 (port celular) — Desempenho (downgrade). Os dois scripts são carregados com load() e CONFERIDOS (nunca com preload),
# para que um erro de compilação neles não impeça a ui_manager de carregar: a tela só deixa de aparecer.
func _script_opcional(caminho: String):
	if not ResourceLoader.exists(caminho):
		return null
	var script = load(caminho)
	if script == null or not script.can_instantiate():
		push_warning("[Zenith] %s não pôde ser carregado; ignorando." % caminho)
		return null
	return script


# v1.12 (port celular) — layout em pé: avatar numa faixa no alto, interface embaixo. Só liga no Android (ou com
# --layout-celular). Se o arquivo falhar ao compilar, a interface abre exatamente como no PC.
func _aplicar_layout_celular() -> void:
	var script = _script_opcional("res://zenith_layout_celular.gd")
	if script == null:
		return
	var candidato = script.new()
	if not candidato.ativo():
		return
	layout_celular = candidato
	layout_celular.ui = self                  # já conhece a janela: um cartão pode abrir antes do aplicar() adiado
	layout_celular.ligar_observador()
	layout_celular.aplicar.call_deferred(self)

func _montar_desempenho(v: VBoxContainer) -> void:
	var script = _script_opcional("res://zenith_desempenho_page.gd")
	if script == null:
		return
	desempenho_page = script.new()
	desempenho_page.montar(self, brain, v)

func _aplicar_desempenho(dados) -> void:
	var script = _script_opcional("res://zenith_desempenho_aplicar.gd")
	if script != null:
		script.new().aplicar(dados, get_tree())

func _section(parent: VBoxContainer, text: String):
	var lbl = Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", CYAN)
	lbl.add_theme_font_size_override("font_size", 12)
	parent.add_child(lbl)


func _hint(parent: VBoxContainer, text: String):
	var lbl = Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", TEXT_MUTED)
	lbl.add_theme_font_size_override("font_size", 10)
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(lbl)


# ==========================================
# v1.0 — ABA "SOBRE": QUEM CRIOU O ZENITH
# ==========================================
# O Anderson pediu que o menu de Configurações diga quem criou. O nome e o papel ficam aqui
# (não mudam); a APRESENTAÇÃO (o texto pessoal) é dele, escrita em config/creditos.txt e
# mostrada no chat pelo /sobre — assim ele pode mudar o texto sem recompilar nada.
func _settings_tab_about() -> ScrollContainer:
	var tab = _new_tab("Sobre")
	var v = tab.get_meta("content")

	var nome = Label.new()
	nome.text = "Zenith — criado por Anderson Ricardo de Souza Filho"
	nome.add_theme_color_override("font_color", CYAN)
	nome.add_theme_font_size_override("font_size", 14)
	nome.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(nome)

	var papel = Label.new()
	papel.text = "Criador e desenvolvedor"
	papel.add_theme_color_override("font_color", TEXT_SECOND)
	papel.add_theme_font_size_override("font_size", 11)
	papel.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(papel)

	_section(v, "Apresentação")
	_hint(v, "O texto de apresentação é escrito pelo próprio Anderson e fica em config/creditos.txt. " +
		"Ele aparece no chat pelo comando /sobre — e pode ser editado quando quiser, sem recompilar o programa.")

	var abrir = _make_button("Ver a apresentação no chat  (/sobre)", BG_SURFACE_2, BG_SURFACE_3)
	abrir.custom_minimum_size.y = 32
	abrir.pressed.connect(func():
		if brain and brain.has_method("send_chat"):
			brain.send_chat("/sobre", ""))
	v.add_child(abrir)

	_section(v, "Versão")
	_hint(v, "Digite /versao no chat para ver a versão e a data em que este programa foi compilado.")

	saude_page = SaudePage.new()      # v1.2 — diagnóstico visível, com a causa e o que fazer
	saude_page.montar(self, brain, v)

	_montar_desempenho(v)             # v1.11 — Desempenho (downgrade); se o arquivo falhar, a tela só não aparece

	_section(v, "Créditos")
	_hint(v, "Feito no Brasil, em português, para uso pessoal. Sem telemetria: nada do que você escreve aqui " +
		"é enviado para o criador. As bibliotecas de terceiros e suas licenças estão em assets/LICENCAS.md.")
	return tab


func _new_tab(title: String) -> ScrollContainer:
	var scroll = ScrollContainer.new()
	scroll.name = title
	var vbox = VBoxContainer.new()
	vbox.name = "content"
	vbox.add_theme_constant_override("separation", 6)
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 12)
	margin.add_child(vbox)
	margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL     # v1.1: antes usava só metade da largura
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.add_child(margin)
	scroll.set_meta("content", vbox)
	return scroll


func _settings_tab_identity() -> ScrollContainer:
	var tab = _new_tab("Identidade")
	var v = tab.get_meta("content")
	_labeled_field(v, "Nome da IA (persona)", "persona_name")
	_labeled_field(v, "Seu nome", "user_name")
	_section(v, "Personalidade")
	var persona_box = TextEdit.new()
	persona_box.custom_minimum_size.y = 90
	persona_box.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	settings_fields["persona_description"] = persona_box
	v.add_child(persona_box)
	_section(v, "Pilares extras (os 4 fixos do sistema não mudam)")
	var pillars_box = TextEdit.new()
	pillars_box.custom_minimum_size.y = 90
	settings_fields["user_pillars"] = pillars_box
	v.add_child(pillars_box)

	_section(v, "Chat")
	var stream_row = HBoxContainer.new()
	var stream_lbl = Label.new()
	stream_lbl.text = "Resposta em streaming (aparece aos poucos)"
	stream_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	stream_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	stream_row.add_child(stream_lbl)
	var stream_toggle = SegmentedToggleLite(["desligado", "ligado"])
	settings_fields["response_streaming"] = stream_toggle
	stream_row.add_child(stream_toggle)
	v.add_child(stream_row)
	_hint(v, "A resposta só é liberada DEPOIS de passar pelas checagens de segurança " +
		"normais (isso não muda) — o streaming só afeta como ela aparece na tela " +
		"depois: em pedacinhos indo direto, tipo \"digitando\", em vez de tudo de uma " +
		"vez. Desligue se notar travadinha em PC mais fraco.")

	var chain_row = HBoxContainer.new()
	var chain_lbl = Label.new()
	chain_lbl.text = "Ações em várias etapas (encadear sozinha)"
	chain_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chain_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	chain_row.add_child(chain_lbl)
	var chain_toggle = SegmentedToggleLite(["desligado", "ligado"])
	settings_fields["multi_step_actions"] = chain_toggle
	chain_row.add_child(chain_toggle)
	v.add_child(chain_row)
	_hint(v, "Quando uma ação aprovada termina, deixa a Zenith decidir sozinha se a " +
		"tarefa já acabou ou se falta mais um passo (até 4 seguidos, pra nunca virar " +
		"loop) — cada passo novo AINDA pede sua aprovação normalmente, do jeito que " +
		"já era (Pilar 1 continua valendo em cada etapa). Desligado, ela sempre para " +
		"depois de uma ação só, como era antes.")

	var think_row = HBoxContainer.new()
	var think_lbl = Label.new()
	think_lbl.text = "Modo econômico / pensante"
	think_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	think_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	think_row.add_child(think_lbl)
	var think_toggle = SegmentedToggleLite(["econômico", "pensante"])
	settings_fields["thinking_mode"] = think_toggle
	think_row.add_child(think_toggle)
	v.add_child(think_row)
	_hint(v, "Só afeta o Gemini (2.5 Flash) — os outros provedores já decidem isso à " +
		"própria maneira. \"Econômico\" desliga o raciocínio estendido: mais rápido e " +
		"mais barato, ótimo pro dia a dia. \"Pensante\" liga o modo dinâmico — o próprio " +
		"Gemini decide, pergunta por pergunta, se vale a pena gastar mais tokens " +
		"pensando antes de responder (não é ela sempre demorar mais, é raciocinar " +
		"fundo só quando a pergunta realmente precisar).")
	return tab


func _card_start(parent: VBoxContainer, title: String, icon: String = "") -> VBoxContainer:
	"""FEATURE (design mais intuitivo): agrupa um bloco de campos numa
	'caixinha' com borda e título próprio, em vez de tudo escorrido
	numa lista só — é o que faz o olho conseguir separar um assunto do
	outro numa olhada rápida."""
	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 10, BORDER, 1))
	parent.add_child(card)
	var inner = VBoxContainer.new()
	inner.add_theme_constant_override("separation", 4)
	var pad = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		pad.add_theme_constant_override("margin_" + side, 12)
	pad.add_child(inner)
	card.add_child(pad)

	var title_lbl = Label.new()
	title_lbl.text = (icon + "  " if icon != "" else "") + title
	title_lbl.add_theme_color_override("font_color", CYAN)
	title_lbl.add_theme_font_size_override("font_size", 13)
	inner.add_child(title_lbl)
	return inner


# v1.1 — este é o editor de "Minhas IAs e serviços" e mora DENTRO da página única de Chaves
# (zenith_chaves_page.gd). A aba antiga de IAs foi removida: as chaves dos provedores do catálogo
# (os do topo daquela página) aparecem SÓ nos cartões dela. Aqui ficam o seletor da IA ativa e o
# que NÃO é do catálogo: "Minhas IAs" (endereço/modelo/chave próprios) e serviços (busca, voz).
# Assim cada chave tem um dono só na tela.
func _montar_editor_de_ias(v: VBoxContainer) -> void:
	# v19 — UMA IA POR VEZ. A caixinha lista só as entradas que não são do catálogo; escolhendo
	# uma, só o painel dela aparece. Nomes, endereços e dicas vêm do Cérebro em settings["_ai_ui"].
	_section(v, "IA que responde nas conversas")
	_hint(v, "É a IA que a Zenith usa pra responder. As chaves dos provedores do catálogo ficam " +
		"nos cartões acima — aqui é só a escolha de quem responde.")
	var active_ai = OptionButton.new()
	active_ai.set_meta("options", [""])
	active_ai.add_item("(carregando...)")
	settings_fields["active_ai"] = active_ai
	v.add_child(active_ai)

	_section(v, "Minhas IAs e serviços")
	_hint(v, "Para uma IA que não está no catálogo (endereço e modelo próprios) ou para a chave de " +
		"um serviço (busca na web, voz). As chaves dos provedores do catálogo ficam nos cartões " +
		"acima. ✓ pronta · ⚠ falta chave ou endereço · ★ é a que responde agora.")
	var pick_row = HBoxContainer.new()
	pick_row.add_theme_constant_override("separation", 8)
	v.add_child(pick_row)
	ai_edit_selector = OptionButton.new()
	ai_edit_selector.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ai_edit_selector.item_selected.connect(_on_ai_edit_selected)
	pick_row.add_child(ai_edit_selector)
	ai_btn_remove = _make_button("Remover", BG_SURFACE_3, Color("5a1f1f"), RED)
	ai_btn_remove.custom_minimum_size = Vector2(110, 28)
	ai_btn_remove.pressed.connect(_on_ai_remove_pressed)
	pick_row.add_child(ai_btn_remove)

	var panel = PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 10, BORDER, 1))
	v.add_child(panel)
	var pad = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		pad.add_theme_constant_override("margin_" + side, 12)
	panel.add_child(pad)
	ai_panel_box = VBoxContainer.new()
	ai_panel_box.add_theme_constant_override("separation", 6)
	pad.add_child(ai_panel_box)

	ai_hint_lbl = Label.new()
	ai_hint_lbl.add_theme_font_size_override("font_size", 11)
	ai_hint_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	ai_hint_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	ai_panel_box.add_child(ai_hint_lbl)

	var r = _ai_make_row(ai_panel_box, "Nome (só pra você identificar)", false)
	ai_row_name = r[0]
	ai_f_name = r[1]
	r = _ai_make_row(ai_panel_box, "Endereço da API (URL)", false)
	ai_row_url = r[0]
	ai_f_url = r[1]
	r = _ai_make_row(ai_panel_box, "Chave da API", true)
	ai_row_key = r[0]
	ai_f_key = r[1]
	r = _ai_make_row(ai_panel_box, "Nome do modelo", false)
	ai_row_model = r[0]
	ai_f_model = r[1]
	ai_f_name.text_changed.connect(_on_ai_field_edited)
	ai_f_url.text_changed.connect(_on_ai_field_edited)
	ai_f_key.text_changed.connect(_on_ai_field_edited)
	ai_f_model.text_changed.connect(_on_ai_field_edited)

	# Atalhos do catálogo (vazio na cópia de distribuição => a linha nem aparece).
	ai_shortcuts_row = VBoxContainer.new()
	ai_shortcuts_row.add_theme_constant_override("separation", 4)
	ai_panel_box.add_child(ai_shortcuts_row)
	var sc_lbl = Label.new()
	sc_lbl.text = "Atalhos:"
	sc_lbl.add_theme_font_size_override("font_size", 11)
	sc_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	ai_shortcuts_row.add_child(sc_lbl)
	ai_shortcuts_box = HFlowContainer.new()
	ai_shortcuts_box.add_theme_constant_override("h_separation", 6)
	ai_shortcuts_box.add_theme_constant_override("v_separation", 6)
	ai_shortcuts_row.add_child(ai_shortcuts_box)

	var key_row = HBoxContainer.new()
	key_row.add_theme_constant_override("separation", 8)
	ai_panel_box.add_child(key_row)
	var show_btn = _make_button("👁 Mostrar chave", BG_SURFACE_3, CYAN_DIM)
	show_btn.custom_minimum_size = Vector2(150, 30)
	show_btn.pressed.connect(func():
		ai_f_key.secret = not ai_f_key.secret
		_ic(show_btn, "🙈 Ocultar chave" if not ai_f_key.secret else "👁 Mostrar chave"))
	key_row.add_child(show_btn)
	ai_btn_test = _make_button("Testar", BG_SURFACE_3, CYAN_DIM)
	ai_btn_test.custom_minimum_size = Vector2(90, 30)
	ai_btn_test.pressed.connect(_on_ai_test_pressed)
	key_row.add_child(ai_btn_test)

	var act_row = HBoxContainer.new()
	act_row.add_theme_constant_override("separation", 8)
	ai_panel_box.add_child(act_row)
	ai_btn_save = _make_button("Salvar esta IA", CYAN, CYAN_DIM, Color("04141a"))
	ai_btn_save.custom_minimum_size = Vector2(190, 32)
	ai_btn_save.pressed.connect(_on_ai_save_pressed)
	act_row.add_child(ai_btn_save)
	ai_btn_active = _make_button("★ Usar nas conversas", BG_SURFACE_3, CYAN_DIM)
	ai_btn_active.custom_minimum_size = Vector2(190, 32)
	ai_btn_active.pressed.connect(_on_ai_use_pressed)
	act_row.add_child(ai_btn_active)

	ai_status_lbl = Label.new()
	ai_status_lbl.add_theme_font_size_override("font_size", 11)
	ai_status_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	ai_status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	ai_panel_box.add_child(ai_status_lbl)
	# O Cérebro responde "Salvar/Remover/Testar" neste mesmo rótulo (provider "ai_panel").
	api_test_status_labels["ai_panel"] = ai_status_lbl

	_ai_apply_empty_state()


# Cria "rótulo + campo" dentro de um VBox próprio, pra poder esconder a linha inteira.
# Devolve [VBoxContainer, LineEdit]. Não registra em settings_fields (o salvamento das IAs
# é próprio: ação save_ai_entry).
func _ai_make_row(parent: VBoxContainer, label_text: String, secret: bool) -> Array:
	var box = VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	parent.add_child(box)
	var field = _unregistered_field(box, label_text, secret)
	# v20: o cartão é BG_SURFACE_2 e o campo também era => campo invisível. Agora o campo é
	# mais escuro que o cartão e tem borda (e borda ciano quando está com foco).
	field.add_theme_stylebox_override("normal", _panel_style(BG_BASE, 6, BORDER, 1))
	field.add_theme_stylebox_override("focus", _panel_style(BG_BASE, 6, CYAN_DIM, 1))
	field.custom_minimum_size.y = 32
	return [box, field]


# Estado inicial (antes do primeiro settings_data chegar): painel vazio e escondido.
func _ai_apply_empty_state():
	ai_edit_selector.clear()
	ai_edit_selector.add_item("＋ Adicionar nova IA…")
	ai_edit_ids = [AI_NEW_ID]
	ai_edit_selector.select(0)
	_ai_show_entry(AI_NEW_ID, true)


func _ai_find(entry_id: String) -> Dictionary:
	for e in ai_entries:
		if String(e.get("id", "")) == entry_id:
			return e
	return {}


func _ai_read_fields() -> Dictionary:
	return {
		"nome": ai_f_name.text.strip_edges(),
		"url": ai_f_url.text.strip_edges(),
		"chave": ai_f_key.text.strip_edges(),
		"modelo": ai_f_model.text.strip_edges(),
	}


# Redesenha a caixinha a partir do que o Cérebro mandou (chamado a cada settings_data).
func _refresh_ai_panel(entradas: Array, select_id: String):
	if ai_edit_selector == null or not is_instance_valid(ai_edit_selector):
		return
	ai_entries = entradas
	var keep_id = ai_current_id
	if select_id != "":
		keep_id = select_id
	ai_loading = true
	ai_edit_selector.clear()
	ai_edit_ids = []
	for e in entradas:
		ai_edit_selector.add_item(String(e.get("rotulo", e.get("nome", ""))))
		ai_edit_ids.append(String(e.get("id", "")))
	ai_edit_selector.add_item("＋ Adicionar nova IA…")
	ai_edit_ids.append(AI_NEW_ID)
	var idx = ai_edit_ids.find(keep_id)
	if idx == -1:
		idx = 0
	ai_edit_selector.select(idx)
	ai_loading = false
	var shown_id = String(ai_edit_ids[idx])
	# Se a pessoa está digitando nesta mesma IA, não atropela o que ela escreveu.
	var reload = not (ai_dirty and shown_id == ai_current_id)
	_ai_show_entry(shown_id, reload)


# Mostra o painel de UMA entrada (ou o formulário de "nova IA").
func _ai_show_entry(entry_id: String, reload_fields: bool):
	var changed = (entry_id != ai_current_id)
	ai_current_id = entry_id
	var is_new = (entry_id == AI_NEW_ID)
	var e: Dictionary = {}
	if not is_new:
		e = _ai_find(entry_id)
	if changed:
		ai_status_lbl.text = ""
	ai_loading = true
	if reload_fields:
		if is_new:
			ai_f_name.text = ""
			ai_f_url.text = ""
			ai_f_key.text = ""
			ai_f_model.text = ""
		else:
			ai_f_name.text = String(e.get("nome", ""))
			ai_f_url.text = String(e.get("url", ""))
			ai_f_key.text = String(e.get("chave", ""))
			ai_f_model.text = String(e.get("modelo", ""))
		if ai_drafts.has(entry_id):
			var d: Dictionary = ai_drafts[entry_id]
			ai_f_name.text = String(d.get("nome", ""))
			ai_f_url.text = String(d.get("url", ""))
			ai_f_key.text = String(d.get("chave", ""))
			ai_f_model.text = String(d.get("modelo", ""))
	ai_loading = false
	if reload_fields:
		ai_dirty = ai_drafts.has(entry_id)

	var is_llm = true
	if not is_new:
		is_llm = bool(e.get("eh_llm", true))
	ai_row_name.visible = is_new or bool(e.get("nome_editavel", false))
	ai_row_url.visible = is_new or bool(e.get("url_editavel", false))
	ai_row_model.visible = is_new or bool(e.get("modelo_editavel", false))
	ai_row_key.visible = true
	ai_f_key.placeholder_text = "opcional se a IA roda no seu PC" if is_new else ""
	ai_btn_save.text = "Adicionar esta IA" if is_new else "Salvar esta IA"
	ai_btn_test.visible = is_new or String(e.get("teste_como", "")) != ""
	ai_btn_active.visible = (not is_new) and is_llm and (not bool(e.get("ativa", false)))
	ai_btn_remove.visible = not is_new
	if not is_new:
		var origem = String(e.get("origem", ""))
		ai_btn_remove.text = "Remover" if (origem == "minha" or origem == "antiga") else "Limpar chave"

	var texto = ""
	if is_new:
		texto = "Cole aqui o endereço (URL) e a chave que o seu provedor fornece, e o nome do modelo. " + \
			"Serve qualquer serviço compatível com a API da OpenAI; uma IA que roda no seu computador " + \
			"não precisa de chave."
	else:
		texto = String(e.get("dica", ""))
		var onde = String(e.get("onde_pegar", ""))
		if onde != "":
			texto += ("\n" if texto != "" else "") + "Pegue a chave em: " + onde
		var aviso = String(e.get("aviso", ""))
		if aviso != "":
			texto += ("\n" if texto != "" else "") + "⚠ " + aviso
	ai_hint_lbl.text = texto
	ai_hint_lbl.visible = texto != ""
	_ai_rebuild_shortcuts()


func _ai_rebuild_shortcuts():
	for c in ai_shortcuts_box.get_children():
		c.queue_free()
	for s in ai_shortcuts:
		var sd: Dictionary = s
		var b = _make_button(String(sd.get("label", sd.get("nome", "?"))), BG_SURFACE_3, CYAN_DIM)
		b.custom_minimum_size = Vector2(0, 28)
		b.pressed.connect(func():
			if ai_f_name.text.strip_edges().is_empty():
				ai_f_name.text = String(sd.get("nome", ""))
			ai_f_url.text = String(sd.get("url", ""))
			if String(sd.get("modelo", "")) != "":
				ai_f_model.text = String(sd.get("modelo", ""))
			ai_dirty = true)
		ai_shortcuts_box.add_child(b)
	ai_shortcuts_row.visible = (ai_current_id == AI_NEW_ID) and not ai_shortcuts.is_empty()


func _on_ai_field_edited(_t: String):
	if not ai_loading:
		ai_dirty = true


# Guarda o que foi digitado e ainda não salvo da IA que está na tela (rascunho), pra não
# perder uma chave colada só porque a pessoa trocou de IA na caixinha.
func _ai_stash_current():
	if ai_dirty and ai_current_id != "":
		ai_drafts[ai_current_id] = _ai_read_fields()
	ai_dirty = false


func _on_ai_edit_selected(idx: int):
	if ai_loading:
		return
	if idx < 0 or idx >= ai_edit_ids.size():
		return
	_ai_stash_current()
	_ai_show_entry(String(ai_edit_ids[idx]), true)


func _ai_send_save(entry_id: String, f: Dictionary):
	if brain == null or not brain.has_method("send_to_brain"):
		return
	brain.send_to_brain({"action": "save_ai_entry", "id": entry_id, "nome": f.get("nome", ""),
		"url": f.get("url", ""), "chave": f.get("chave", ""), "modelo": f.get("modelo", "")})


func _on_ai_save_pressed():
	ai_status_lbl.text = "salvando..."
	ai_status_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	_ai_send_save(ai_current_id, _ai_read_fields())
	ai_drafts.erase(ai_current_id)
	ai_dirty = false


func _on_ai_remove_pressed():
	if ai_current_id == AI_NEW_ID or ai_current_id == "":
		return
	if brain and brain.has_method("send_to_brain"):
		brain.send_to_brain({"action": "remove_ai_entry", "id": ai_current_id})
	ai_drafts.erase(ai_current_id)
	ai_dirty = false
	ai_current_id = ""


func _on_ai_use_pressed():
	if ai_current_id == AI_NEW_ID or ai_current_id == "":
		return
	# Se tem algo digitado e não salvo, salva junto (senão "usar" uma IA sem chave).
	if ai_dirty:
		_ai_send_save(ai_current_id, _ai_read_fields())
		ai_drafts.erase(ai_current_id)
		ai_dirty = false
	if brain:
		brain.save_settings({"active_ai": ai_current_id})
	ai_status_lbl.text = "★ Agora é esta IA que responde."
	ai_status_lbl.add_theme_color_override("font_color", GREEN)


func _on_ai_test_pressed():
	var kind = "new_custom"
	if ai_current_id != AI_NEW_ID:
		kind = String(_ai_find(ai_current_id).get("teste_como", ""))
	if kind == "":
		return
	ai_status_lbl.text = "testando..."
	ai_status_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	api_test_status_labels[kind] = ai_status_lbl
	if brain:
		brain.test_api_key(kind, ai_f_key.text.strip_edges(), ai_f_url.text.strip_edges())


# Chamado por "Salvar e Aplicar": tudo que ficou digitado e não foi salvo em cada IA vai junto
# (o salvamento geral não conhece estes campos). Rascunho incompleto de "nova IA" é ignorado.
func _ai_flush_all():
	_ai_stash_current()
	for id in ai_drafts.keys():
		var f: Dictionary = ai_drafts[id]
		if String(id) == AI_NEW_ID:
			if String(f.get("nome", "")) == "" or String(f.get("url", "")) == "" or String(f.get("modelo", "")) == "":
				continue
		_ai_send_save(String(id), f)
	ai_drafts.clear()


# Preenche um seletor de "IA ativa" (o das Configurações e o do topo do chat) só com as entradas
# que são modelo de linguagem. Se não há nenhuma, mostra um aviso e NÃO grava nada ao salvar.
func _ai_fill_active_selector(opt: OptionButton, entradas: Array, active_id: String):
	if opt == null or not is_instance_valid(opt):
		return
	var ids: Array = []
	opt.clear()
	for e in entradas:
		if not bool(e.get("eh_llm", false)):
			continue
		ids.append(String(e.get("id", "")))
		opt.add_item(String(e.get("nome", "")) + ("  ✓" if bool(e.get("configurada", false)) else "  ⚠"))
	if ids.is_empty():
		opt.add_item("(nenhuma IA — cadastre abaixo)")
		ids.append("")
	opt.set_meta("options", ids)
	_select_option(opt, active_id, ids)


# Campo de chave + botão "Testar" + statuszinho colorido — confirma se
# a chave é de verdade ANTES de você salvar e descobrir só na hora de
# conversar que ela tava errada.
func _labeled_field_with_test(parent: VBoxContainer, label_text: String, key: String, provider: String):
	var field = _labeled_field(parent, label_text, key, true)

	var row = HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)

	var test_btn = _make_button("Testar chave", BG_SURFACE_2, BG_SURFACE_3)
	test_btn.custom_minimum_size = Vector2(110, 28)
	row.add_child(test_btn)

	# Botão pra ver a chave em texto puro — pra conferir se colou certo
	# sem precisar apagar e digitar de novo às cegas.
	var show_btn = _make_button("👁 Mostrar", BG_SURFACE_2, BG_SURFACE_3)
	show_btn.custom_minimum_size = Vector2(100, 28)
	show_btn.pressed.connect(func():
		field.secret = not field.secret
		_ic(show_btn, "🙈 Ocultar" if not field.secret else "👁 Mostrar"))
	row.add_child(show_btn)

	var status = Label.new()
	status.text = ""
	status.add_theme_font_size_override("font_size", 11)
	status.add_theme_color_override("font_color", TEXT_MUTED)
	row.add_child(status)

	api_test_status_labels[provider] = status

	test_btn.pressed.connect(func():
		status.text = "testando..."
		status.add_theme_color_override("font_color", TEXT_MUTED)
		var custom_url = settings_fields.get("custom_api_url").text if provider == "custom" and settings_fields.has("custom_api_url") else ""
		if brain:
			brain.test_api_key(provider, field.text, custom_url))


func _settings_tab_voice() -> ScrollContainer:
	var tab = _new_tab("Voz")
	var v = tab.get_meta("content")

	_section(v, "Ativar/Desativar")
	var voice_row = HBoxContainer.new()
	var voice_lbl = Label.new()
	voice_lbl.text = "Voz (fala em áudio)"
	voice_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	voice_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	voice_row.add_child(voice_lbl)
	var voice_toggle = SegmentedToggleLite(["desligada", "ligada"])
	settings_fields["voice_enabled"] = voice_toggle
	voice_row.add_child(voice_toggle)
	v.add_child(voice_row)
	_hint(v, "Desliga TTS/RVC — a Zenith responde só em texto. Bom pra economizar CPU/GPU numa reunião.")

	# v14 — "Testar voz": toca uma frase fixa e mostra o diagnóstico (Edge-TTS,
	# ElevenLabs, RVC rodou ou não) no chat, sem precisar mandar mensagem.
	var test_voice_btn = _make_button("🔊  Testar voz agora", BG_SURFACE_2, BG_SURFACE_3, TEXT_PRIMARY)
	test_voice_btn.pressed.connect(func():
		if brain and brain.has_method("send_to_brain"):
			brain.send_to_brain({"action": "test_voice"})
		else:
			_add_bubble("⚠ Cérebro não está conectado agora.", "ai"))
	v.add_child(test_voice_btn)
	_hint(v, "Toca uma frase fixa e escreve no chat um diagnóstico da voz (também dá pra usar /testar_voz). " +
		"Use depois de trocar de modelo RVC pra saber na hora se a conversão realmente rodou.")

	_section(v, "Microfone")
	_hint(v, "\"Sempre ouvindo\" (mãos-livres): aperte o 🎙 uma vez e fale — ela detecta " +
		"sozinha quando você parou de falar e já manda pra transcrição, sem precisar " +
		"apertar de novo. Deixa a conversa por voz mais rápida, tipo walkie-talkie.")
	var mic_row = HBoxContainer.new()
	var mic_lbl = Label.new()
	mic_lbl.text = "Modo do microfone"
	mic_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mic_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	mic_row.add_child(mic_lbl)
	var mic_toggle = SegmentedToggleLite(["manual (aperta 2x)", "sempre ouvindo"])
	settings_fields["mic_mode"] = mic_toggle
	mic_row.add_child(mic_toggle)
	v.add_child(mic_row)
	_labeled_field(v, "Silêncio (ms) até considerar que parou de falar", "mic_silence_ms")
	_labeled_field(v, "Tempo máximo de gravação (s) — trava de segurança", "mic_max_seconds")

	_section(v, "ElevenLabs")
	_labeled_field(v, "API Key", "elevenlabs_key", true)
	_labeled_field(v, "Voice ID", "elevenlabs_voice_id")
	_section(v, "RVC")
	_labeled_field_with_browse(v, "Modelo (.pth)", "rvc_model_path", PackedStringArray(["*.pth ; Modelo RVC"]))
	_labeled_field_with_browse(v, "Índice (.index)", "rvc_index_path", PackedStringArray(["*.index ; Índice RVC"]))
	_labeled_field_with_browse(v, "Python 3.10 do RVC (opcional)", "rvc_python_exe", PackedStringArray(["python.exe ; Python do ambiente do RVC"]))
	_hint(v, "O RVC não instala no Python do Zenith (exige Python 3.10). Rode o instalar_rvc.bat " +
		"(fica ao lado do Zenith.exe): ele cria um ambiente só do RVC em tools/rvc/venv e o Zenith " +
		"acha sozinho — este campo só serve se você instalou em outro lugar. Depois, /testar_voz mostra " +
		"se funcionou. Sem isso o modelo .pth é ignorado e a voz base é usada.")
	_section(v, "Emoção na voz")
	_hint(v, "O quanto a velocidade e o tom da voz variam com a emoção da resposta (alegre, triste, " +
		"surpresa...). Só vale para a voz Edge-TTS; ElevenLabs e RVC não são afetados.")
	var emo_row = HBoxContainer.new()
	var emo_lbl = Label.new()
	emo_lbl.text = "Intensidade"
	emo_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	emo_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	emo_row.add_child(emo_lbl)
	var emo_opt = SegmentedToggleLite(["sutil", "normal", "marcada", "exagerada"])
	settings_fields["voice_expression_intensity"] = emo_opt
	emo_row.add_child(emo_opt)
	v.add_child(emo_row)
	_section(v, "Volume")
	var vol = HSlider.new()
	vol.min_value = 0.0; vol.max_value = 1.0; vol.step = 0.01
	settings_fields["tts_volume"] = vol
	v.add_child(vol)

	_section(v, "Fala espontânea (proatividade)")
	var proactive_row = HBoxContainer.new()
	var proactive_lbl = Label.new()
	proactive_lbl.text = "Puxar assunto sozinha depois de um tempo parado"
	proactive_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	proactive_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	proactive_row.add_child(proactive_lbl)
	var proactive_toggle = SegmentedToggleLite(["desligada", "ligada"])
	settings_fields["proactive_enabled"] = proactive_toggle
	proactive_row.add_child(proactive_toggle)
	v.add_child(proactive_row)
	_labeled_field(v, "Minutos de inatividade até puxar assunto", "proactive_minutes")
	return tab


func _settings_tab_body() -> ScrollContainer:
	var tab = _new_tab("Corpo / VRM")
	var v = tab.get_meta("content")
	# v18 — UMA pasta só: todo avatar vive em res://addons/avatars/ e é importado
	# pelo próprio Godot (o único caminho que renderiza cabelo/roupa certo). O
	# campo abaixo só MOSTRA qual está em uso — trocar é pela lista.
	var campo_vrm = _labeled_field(v, "Avatar em uso", "vrm_model_path")
	campo_vrm.editable = false

	_section(v, "Avatares do projeto")
	_hint(v, "Todo avatar fica em res://addons/avatars/ e é importado pelo próprio Godot — é o que " +
		"renderiza cabelo e roupa certos. Clique em \"Usar\" pra trocar.")
	_project_avatar_list_box = VBoxContainer.new()
	_project_avatar_list_box.add_theme_constant_override("separation", 6)
	v.add_child(_project_avatar_list_box)
	_refresh_project_avatar_list()

	var linha_av = HBoxContainer.new()
	linha_av.add_theme_constant_override("separation", 8)
	var add_av_btn = _make_button("➕  Adicionar avatar...", BG_SURFACE_2, BG_SURFACE_3, TEXT_PRIMARY)
	add_av_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_av_btn.pressed.connect(_abrir_seletor_avatar_projeto)
	linha_av.add_child(add_av_btn)
	var ver_av_btn = _make_button("🔄  Verificar de novo", BG_SURFACE_2, BORDER, TEXT_PRIMARY)
	ver_av_btn.pressed.connect(_reverificar_avatares)
	linha_av.add_child(ver_av_btn)
	v.add_child(linha_av)
	_hint(v, "\"Adicionar\" faz tudo sozinho: copia o .vrm pra pasta do projeto, importa no Godot, " +
		"reempacota e reinicia o Zenith já com o avatar novo. Leva de 1 a alguns minutos (na primeira " +
		"vez é mais demorado). Se algo faltar, a Zenith explica no chat — ou digite /avatar_diag.")

	_section(v, "Editor do Godot (só se o Zenith não achar sozinho)")
	_hint(v, "Pra importar, o Zenith usa o editor do Godot em segundo plano, sem abrir janela. Ele procura " +
		"sozinho (pasta tools/godot do Zenith, Downloads, Desktop...). Deixe em branco a menos que a " +
		"Zenith diga que não achou — aí aponte o Godot_v4.x_win64.exe.")
	_labeled_field_with_browse(v, "Editor do Godot (Godot_v4.x_win64.exe)", "vrm_auto_import_godot_bin",
		PackedStringArray(["*.exe ; Godot"]))

	# FEATURE ("recarregar" sem reabrir o seletor): útil quando você
	# SUBSTITUI o arquivo no mesmo caminho de sempre (mesmo nome) — o
	# Godot só troca de VRM quando o TEXTO do caminho muda, então
	# sobrescrever o arquivo sozinho não disparava nada antes. Esse
	# botão força a troca na hora, não importa se o caminho mudou.
	var reload_btn = _make_button("🔄  Recarregar avatar agora", BG_SURFACE_2, BORDER, TEXT_PRIMARY)
	reload_btn.pressed.connect(func():
		var path = String(settings_fields["vrm_model_path"].text).strip_edges() if settings_fields.has("vrm_model_path") else ""
		if path == "":
			_add_bubble("⚠ Nenhum avatar em uso ainda — escolha um na lista.", "ai")
			return
		if not akira_body or not akira_body.has_method("reload_vrm"):
			_add_bubble("⚠ Corpo/avatar não está conectado agora.", "ai")
			return
		var erro = akira_body.reload_vrm(path)
		_add_bubble(("⚠ VRM: " + erro) if erro != "" else "✓ VRM recarregado.", "ai"))
	v.add_child(reload_btn)

	# FEATURE (ajuste fino manual): o encaixe automático (que escala o
	# NOVO (diagnóstico do braço torto/deformado em alguns VRMs): o
	# travamento assume que todo VRM usa a mesma convenção de eixo nos
	# ossos do braço que a Zenith padrão — em VRMs de outros programas
	# isso pode não bater, e a MESMA conta que deixa o braço da Zenith
	# caído "normal" pode deixar o de outro modelo torto. Desligado (o
	# padrão agora), o avatar fica na pose nativa do arquivo — geralmente
	# T-pose ou A-pose, do jeito que o próprio VRM define — sem nada
	# forçando os braços. Ligado, volta a travar os braços pra baixo.
	_section(v, "Postura dos braços")
	var lock_row = HBoxContainer.new()
	var lock_lbl = Label.new()
	lock_lbl.text = "Travar braços pra baixo (desligado = pose nativa do arquivo)"
	lock_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lock_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	lock_row.add_child(lock_lbl)
	var lock_toggle = SegmentedToggleLite(["desligado", "ligado"])
	lock_toggle.selected = 1 if (akira_body and "lock_arms_enabled" in akira_body and akira_body.lock_arms_enabled) else 0
	lock_toggle.item_selected.connect(func(idx):
		if akira_body and akira_body.has_method("set_lock_arms"):
			akira_body.set_lock_arms(idx == 1))
	lock_row.add_child(lock_toggle)
	v.add_child(lock_row)
	_hint(v, "Se um VRM específico aparecer com os braços tortos/dobrados de um jeito " +
		"estranho (não um T-pose limpo), deixe DESLIGADO pra esse modelo — é sinal de que " +
		"o cálculo do travamento não bate com a convenção de ossos dele.")

	# VRM novo pra bater com a altura "âncora" salva) não acerta 100%
	# pra todo arquivo — modelos com proporções bem diferentes podem
	# sobrar grande/pequeno/deslocado. Esses campos ficam POR CIMA do
	# cálculo automático (nunca no lugar dele) e dá pra ver o resultado
	# na hora, já que a janela do avatar continua visível ao lado desta
	# tela de Configurações.
	_section(v, "Ajuste fino (se o avatar aparecer grande/pequeno/deslocado)")
	_hint(v, "Desloca e reescala por cima do encaixe automático. \"Aplicar (ver ao vivo)\" só " +
		"testa — \"Salvar ajuste\" grava pra valer, inclusive pra próxima vez que abrir o Zenith.")

	# NOVO v10 — alternativa aos 4 campos de número logo abaixo: ativa e
	# arrasta a própria Zenith pra ajustar ao vivo, os campos se atualizam
	# sozinhos (ver _process() e _toggle_adjust_drag()).
	adjust_drag_btn = _make_button("🖱  Ajustar arrastando", BG_SURFACE_2, BG_SURFACE_3)
	adjust_drag_btn.pressed.connect(_toggle_adjust_drag)
	v.add_child(adjust_drag_btn)
	_hint(v, "Em vez de digitar os 4 campos abaixo, clique aqui e arraste a Zenith com o botão " +
		"esquerdo (ela acompanha o mouse; ajusta X/Y) — roda do mouse = Escala, Shift + roda = " +
		"Deslocamento Z, BOTÃO DIREITO = desfaz tudo desde que ligou o modo. Os campos abaixo " +
		"acompanham ao vivo; clique em \"Salvar ajuste\" só quando estiver bom. Só um modo de " +
		"arraste por vez — ativar isso desliga \"Mover Zenith\" sozinho.")

	offx = _unregistered_field(v, "Deslocamento X (esquerda/direita)")
	offx.text = "0.0"
	offy = _unregistered_field(v, "Deslocamento Y (altura)")
	offy.text = "0.0"
	offz = _unregistered_field(v, "Deslocamento Z (frente/trás)")
	offz.text = "0.0"
	scale_mult_field = _unregistered_field(v, "Multiplicador de escala (1.0 = tamanho normal)")
	scale_mult_field.text = "1.0"

	var adjust_row = HBoxContainer.new()
	adjust_row.add_theme_constant_override("separation", 8)
	v.add_child(adjust_row)

	var _parse_adjust = func() -> Array:
		var ox = float(offx.text) if offx.text.strip_edges().is_valid_float() else 0.0
		var oy = float(offy.text) if offy.text.strip_edges().is_valid_float() else 0.0
		var oz = float(offz.text) if offz.text.strip_edges().is_valid_float() else 0.0
		var sm = float(scale_mult_field.text) if scale_mult_field.text.strip_edges().is_valid_float() else 1.0
		return [Vector3(ox, oy, oz), sm]

	var apply_live_btn = _make_button("👁  Aplicar (ver ao vivo)", BG_SURFACE_2, BORDER, TEXT_PRIMARY)
	apply_live_btn.pressed.connect(func():
		if not akira_body or not akira_body.has_method("set_manual_vrm_adjust"):
			_add_bubble("⚠ Corpo/avatar não está conectado agora.", "ai")
			return
		var vals = _parse_adjust.call()
		var erro = akira_body.set_manual_vrm_adjust(vals[0], vals[1], false)
		_add_bubble(("⚠ VRM: " + erro) if erro != "" else "👁 Ajuste aplicado (ainda não salvo).", "ai"))
	adjust_row.add_child(apply_live_btn)

	var save_adjust_btn = _make_button("💾  Salvar ajuste", BG_SURFACE_2, BORDER, TEXT_PRIMARY)
	save_adjust_btn.pressed.connect(func():
		if not akira_body or not akira_body.has_method("set_manual_vrm_adjust"):
			_add_bubble("⚠ Corpo/avatar não está conectado agora.", "ai")
			return
		var vals = _parse_adjust.call()
		var erro = akira_body.set_manual_vrm_adjust(vals[0], vals[1], true)
		_add_bubble(("⚠ VRM: " + erro) if erro != "" else "✓ Ajuste salvo — vale pra esse VRM e pra próxima vez que abrir o Zenith.", "ai"))
	adjust_row.add_child(save_adjust_btn)

	var reset_adjust_btn = _make_button("↺  Restaurar padrão", BG_SURFACE_2, BORDER, TEXT_MUTED)
	reset_adjust_btn.pressed.connect(func():
		offx.text = "0.0"; offy.text = "0.0"; offz.text = "0.0"; scale_mult_field.text = "1.0"
		if akira_body and akira_body.has_method("reset_manual_vrm_adjust"):
			akira_body.reset_manual_vrm_adjust()
		_add_bubble("↺ Ajuste manual zerado.", "ai"))
	adjust_row.add_child(reset_adjust_btn)

	_section(v, "Transparência do corpo")
	var trans = HSlider.new()
	trans.min_value = 0.1; trans.max_value = 1.0; trans.step = 0.01
	settings_fields["body_transparency"] = trans
	v.add_child(trans)
	_hint(v, "Funciona em VRM (shader MToon): ao sair de 100% o corpo troca para a variante " +
		"transparente do próprio shader. Aplica ao clicar em \"Salvar e Aplicar\".")

	# ---- v20: VIDA DO AVATAR ----
	_section(v, "Vida do avatar")
	_hint(v, "Expressões do rosto (piscar, emoções), boca ao falar, braços relaxados (em vez da " +
		"T-pose), gestos (acenar, concordar, negar, dar de ombros...) e olhar para o mouse. " +
		"\"Suave\" é discreto; \"expressivo\" faz mais gestos sozinha. Se algum modelo ficar " +
		"estranho, desligue \"Braços naturais\" ou o nível.")
	var vida_rows = [
		["Nível", "vida_nivel", ["desligado", "suave", "expressivo"]],
		["Braços naturais (desce da T-pose)", "vida_bracos_naturais", ["não", "sim"]],
		["Olhar para o mouse", "vida_olhar_mouse", ["não", "sim"]],
		["Gestos automáticos conforme a resposta", "vida_gestos_ia", ["não", "sim"]],
	]
	for vr in vida_rows:
		var vrow = HBoxContainer.new()
		var vlbl = Label.new()
		vlbl.text = String(vr[0])
		vlbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		vlbl.add_theme_color_override("font_color", TEXT_PRIMARY)
		vrow.add_child(vlbl)
		var vtog = SegmentedToggleLite(vr[2])
		settings_fields[String(vr[1])] = vtog
		vrow.add_child(vtog)
		v.add_child(vrow)
	var gest_row = HBoxContainer.new()
	gest_row.add_theme_constant_override("separation", 8)
	v.add_child(gest_row)
	var gest_pick = OptionButton.new()
	gest_pick.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for gname in ["acenar", "concordar", "negar", "inclinar", "ombros", "pensar", "reverencia", "comemorar", "pulinho"]:
		gest_pick.add_item(gname)
	gest_row.add_child(gest_pick)
	var gest_btn = _make_button("▶ Testar gesto", BG_SURFACE_3, CYAN_DIM)
	gest_btn.custom_minimum_size = Vector2(150, 32)
	gest_btn.pressed.connect(func():
		if akira_body and akira_body.has_method("vida_play_gesture"):
			var gn = gest_pick.get_item_text(gest_pick.selected)
			if not akira_body.vida_play_gesture(gn):
				_add_bubble("⚠ Gesto \"" + gn + "\" não tocou (vida desligada, ou o modelo não tem os ossos necessários — veja o relatório).", "ai"))
	gest_row.add_child(gest_btn)
	var rep_btn = _make_button("📋 Relatório da vida (ossos e expressões)", BG_SURFACE_3, CYAN_DIM)
	rep_btn.pressed.connect(func():
		if akira_body and akira_body.has_method("vida_report"):
			_add_bubble("🧍 " + String(akira_body.vida_report()), "ai"))
	v.add_child(rep_btn)

	# Reposto a aba "Janela VRM" que existia no script antigo (posição
	# no canto + tamanho em pixels) — tinha caído quando reorganizei as
	# abas depois de voltar pro modelo de janela flutuante.
	_section(v, "Posição da janela do avatar")
	var pos_opt = OptionButton.new()
	for label in ["Canto superior direito", "Canto inferior direito", "Canto superior esquerdo", "Canto inferior esquerdo"]:
		pos_opt.add_item(label)
	settings_fields["vrm_window_position"] = pos_opt
	v.add_child(pos_opt)

	_section(v, "Tamanho da janela (largura x altura, em pixels)")
	_hint(v, "Exemplos: 200x200, 400x500, 420x640 (padrão).")
	_labeled_field(v, "Tamanho", "vrm_window_size")

	var click_row = HBoxContainer.new()
	var click_lbl = Label.new()
	click_lbl.text = "Mouse atravessa a janela (fora do modo Mover)"
	click_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	click_lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	click_row.add_child(click_lbl)
	var click_toggle = SegmentedToggleLite(["não", "sim"])
	settings_fields["vrm_click_through"] = click_toggle
	click_row.add_child(click_toggle)
	v.add_child(click_row)

	_labeled_field(v, "Pasta de criações da IA (vazio = padrão)", "output_folder")
	_section(v, "Pasta única de dados (memória, temporários e criações)")
	_hint(v, "Deixa tudo (memória de longo prazo, áudios temporários, criações) numa " +
		"pasta só, escolhida por você — em vez de espalhado dentro da instalação " +
		"do Zenith. Vazio = usa as pastas padrão. Precisa REINICIAR o Zenith depois de mudar.")
	_labeled_folder_with_browse(v, "Pasta de dados", "data_root_path")
	return tab


# Mini-controle de duas opções (sim/não) reaproveitando o visual dos
# OptionButton já usados no resto da tela de Permissões.
func SegmentedToggleLite(options: Array) -> OptionButton:
	var opt = OptionButton.new()
	for o in options:
		opt.add_item(o)
	opt.set_meta("options", options)
	return opt


func _settings_tab_appearance() -> ScrollContainer:
	var tab = _new_tab("Aparência")
	var v = tab.get_meta("content")
	_section(v, "Papel de parede do chat")
	_hint(v, "Qualquer imagem (PNG, JPG, WEBP, BMP, GIF, TIFF, ICO...) ou vídeo (MP4, MOV, MKV, " +
		"AVI, WEBM, OGV...). O que o Godot não lê direto eu converto sozinha, sem precisar de " +
		"ffmpeg — vídeo e GIF viram um loop de até ~12 s (a 1ª vez leva alguns segundos). " +
		"Se o seu vídeo não abrir, tente MP4 (H.264) ou WEBM.")
	var wp_field = _labeled_field_with_browse(v, "Arquivo", "chat_wallpaper_path",
		PackedStringArray(["*.png,*.jpg,*.jpeg,*.webp,*.bmp,*.tga,*.gif,*.tif,*.tiff,*.ico,*.avif,*.heic,*.mp4,*.m4v,*.mov,*.mkv,*.avi,*.webm,*.wmv,*.flv,*.mpg,*.mpeg,*.ogv ; Imagens e vídeos",
			"* ; Qualquer arquivo"]))
	var clear_wp_btn = _make_button("Remover fundo", BG_SURFACE_2, Color("5a1f1f"), RED)
	clear_wp_btn.pressed.connect(func(): wp_field.text = "")
	v.add_child(clear_wp_btn)

	_labeled_field(v, "Escurecer o fundo (0 = nada, 1 = totalmente preto)", "chat_wallpaper_dim")
	_hint(v, "Ajuda a manter o texto do chat legível em cima de fundos claros ou " +
		"muito cheios de detalhe.")
	return tab


func _settings_tab_email() -> ScrollContainer:
	var tab = _new_tab("Ponte E-mail")
	var script = _script_opcional("res://zenith_email_page.gd")
	if script:
		email_page = script.new()
		email_page.montar(self, brain, tab.get_meta("content"))
	return tab


func _settings_tab_chaves() -> ScrollContainer:
	# v1.1 — a página é DONA da tela de chaves: cartões do catálogo (várias chaves, testar, remover)
	# e, logo abaixo, o editor de "Minhas IAs e serviços". Não existe mais uma aba separada de IAs.
	var tab = _new_tab("Chaves & IAs")
	chaves_page = ChavesPage.new()
	chaves_page.montar(self, brain, tab.get_meta("content"))
	return tab


func _settings_tab_estudio() -> ScrollContainer:
	var tab = _new_tab("Estúdio")
	Estudio.montar(self, aparencia, tab.get_meta("content"))
	return tab


func _settings_tab_permissions() -> ScrollContainer:
	var tab = _new_tab("Permissões")
	var v = tab.get_meta("content")
	var hint = Label.new()
	hint.text = "\"Rodar código\" e \"Terminal\" recomendado sempre em \"ask\"."
	hint.add_theme_color_override("font_color", TEXT_MUTED)
	hint.add_theme_font_size_override("font_size", 10)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(hint)

	var labels = {"screen": "Ver a tela", "microphone": "Usar microfone", "camera": "Usar câmera",
		"run_code": "Rodar código Python", "terminal": "Rodar terminal", "serial": "Conectar hardware",
		"web_search": "Buscar/ler na web"}
	# Câmera e microfone nunca oferecem "always" (sempre permitir sem
	# perguntar) — risco alto demais num app de companhia com avatar/voz.
	# Mesmo que alguém tente forçar isso editando o JSON na mão, o
	# zenith_headless.py rejeita de qualquer forma (defesa em duas camadas).
	var sensitive_keys = ["camera", "microphone"]
	for key in labels.keys():
		var row = HBoxContainer.new()
		var lbl = Label.new()
		lbl.text = labels[key]
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
		row.add_child(lbl)
		var opt = OptionButton.new()
		var opts = ["never", "ask"] if key in sensitive_keys else ["never", "ask", "always"]
		for o in opts:
			opt.add_item(o)
		opt.set_meta("options", opts)
		settings_fields["permission:" + key] = opt
		row.add_child(opt)
		v.add_child(row)

	# ---- v20: ZONA DE PERIGO — resetar tudo ----
	_section(v, "Zona de perigo — resetar tudo")
	_hint(v, "Apaga os SEUS dados: memória de longo prazo, conversas, notas, log de ações, " +
		"lembretes, chaves de API, IAs cadastradas e persona. O Zenith volta ao estado de " +
		"\"primeira abertura\". NÃO apaga o programa, os avatares nem os modelos de voz. " +
		"Por segurança o apagamento acontece na PRÓXIMA abertura (o Windows não deixa apagar " +
		"arquivo em uso): você confirma aqui, fecha e abre de novo.")
	reset_confirm_field = LineEdit.new()
	reset_confirm_field.placeholder_text = "Digite RESETAR para liberar o botão"
	reset_confirm_field.add_theme_stylebox_override("normal", _panel_style(BG_SURFACE_2, 6, BORDER, 1))
	reset_confirm_field.custom_minimum_size.y = 32
	v.add_child(reset_confirm_field)
	reset_btn = _make_button("Resetar tudo (apagar meus dados)", BG_SURFACE_3, Color("5a1f1f"), RED)
	reset_btn.custom_minimum_size = Vector2(0, 34)
	reset_btn.disabled = true
	reset_confirm_field.text_changed.connect(func(txt: String):
		reset_btn.disabled = (txt.strip_edges().to_upper() != "RESETAR"))
	reset_btn.pressed.connect(func():
		if brain and brain.has_method("send_to_brain"):
			reset_status_lbl.text = "agendando..."
			brain.send_to_brain({"action": "schedule_reset", "confirm": reset_confirm_field.text}))
	v.add_child(reset_btn)
	reset_status_lbl = Label.new()
	reset_status_lbl.add_theme_font_size_override("font_size", 11)
	reset_status_lbl.add_theme_color_override("font_color", TEXT_MUTED)
	reset_status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(reset_status_lbl)
	reset_quit_btn = _make_button("Fechar o Zenith agora", BG_SURFACE_3, CYAN_DIM)
	reset_quit_btn.visible = false
	reset_quit_btn.pressed.connect(func(): get_tree().quit())
	v.add_child(reset_quit_btn)
	reset_cancel_btn = _make_button("Cancelar o reset agendado", BG_SURFACE_3, CYAN_DIM)
	reset_cancel_btn.visible = false
	reset_cancel_btn.pressed.connect(func():
		if brain and brain.has_method("send_to_brain"):
			brain.send_to_brain({"action": "cancel_reset"}))
	v.add_child(reset_cancel_btn)
	return tab


func _on_reset_scheduled(ok: bool, message: String):
	if reset_status_lbl == null or not is_instance_valid(reset_status_lbl):
		return
	reset_status_lbl.text = message
	reset_status_lbl.add_theme_color_override("font_color", GREEN if ok else RED)
	reset_quit_btn.visible = ok
	reset_cancel_btn.visible = ok
	if ok:
		reset_confirm_field.text = ""
		reset_btn.disabled = true


var _wallpaper_path_aplicado := "<<nunca-aplicado>>"   # sentinela: nunca bate com "" nem com um caminho real

func _wp_parar_quadros():
	if _wp_frame_timer != null and is_instance_valid(_wp_frame_timer):
		_wp_frame_timer.stop()
	_wp_frames = []
	_wp_frame_idx = 0

func _wp_mostrar_imagem(path: String) -> bool:
	var img = Image.new()
	if img.load(path) != OK:
		return false
	wallpaper_rect.texture = ImageTexture.create_from_image(img)
	wallpaper_rect.visible = true
	return true

func _wp_tocar_ogv(path: String):
	var stream = VideoStreamTheora.new()
	stream.file = path
	wallpaper_video.stream = stream
	wallpaper_video.visible = true
	wallpaper_video.loop = true
	wallpaper_video.play()

func _wp_tocar_quadros(pasta: String, fps: float):
	var d = DirAccess.open(pasta)
	if d == null:
		return false
	var nomes: Array = []
	for f in d.get_files():
		if f.to_lower().ends_with(".jpg") or f.to_lower().ends_with(".png"):
			nomes.append(f)
	nomes.sort()
	if nomes.is_empty():
		return false
	_wp_frames = []
	for n in nomes:
		_wp_frames.append(pasta.path_join(String(n)))
	_wp_frame_idx = 0
	if _wp_frame_timer == null or not is_instance_valid(_wp_frame_timer):
		_wp_frame_timer = Timer.new()
		_wp_frame_timer.one_shot = false
		_wp_frame_timer.timeout.connect(_wp_proximo_quadro)
		add_child(_wp_frame_timer)
	_wp_frame_timer.wait_time = 1.0 / clampf(fps, 1.0, 30.0)
	_wp_proximo_quadro()
	_wp_frame_timer.start()
	return true

# Um quadro por vez lido do disco (não guarda o vídeo inteiro na memória).
func _wp_proximo_quadro():
	if _wp_frames.is_empty():
		return
	var caminho = String(_wp_frames[_wp_frame_idx])
	_wp_frame_idx = (_wp_frame_idx + 1) % _wp_frames.size()
	var img = Image.new()
	if img.load(caminho) == OK:
		wallpaper_rect.texture = ImageTexture.create_from_image(img)
		wallpaper_rect.visible = true

func _apply_wallpaper(path: String):
	if path == _wallpaper_path_aplicado:
		return   # evita recarregar a imagem/vídeo do disco a cada "settings_data" recebido
	_wallpaper_path_aplicado = path

	wallpaper_rect.visible = false
	wallpaper_video.visible = false
	wallpaper_video.stop()
	_wp_parar_quadros()
	_wp_origem_pedida = ""

	if path == "" or not FileAccess.file_exists(path):
		return

	# v20 — QUALQUER imagem ou vídeo: o que o Godot lê direto (PNG/JPG/WEBP/BMP/TGA e .ogv) é
	# usado na hora; o resto (MP4, MOV, MKV, AVI, WEBM, GIF, TIFF, ICO...) é pedido ao Cérebro,
	# que converte (sem ffmpeg) e responde com "wallpaper_ready".
	var ext = path.get_extension().to_lower()
	if ext == "ogv":
		_wp_tocar_ogv(path)
	elif ext in ["png", "jpg", "jpeg", "webp", "bmp", "tga"]:
		if not _wp_mostrar_imagem(path):
			_add_bubble("⚠ Não consegui abrir essa imagem de fundo — confira se o arquivo não " +
				"está corrompido.", "ai")
	else:
		if brain and brain.has_method("send_to_brain"):
			_wp_origem_pedida = path
			brain.send_to_brain({"action": "prepare_wallpaper", "path": path})
		else:
			_add_bubble("⚠ Sem conexão com o Cérebro para preparar esse formato de fundo.", "ai")

func _on_wallpaper_ready(res: Dictionary):
	var origem = String(res.get("origem", ""))
	if origem != _wp_origem_pedida or origem == "":
		return   # resposta de um pedido antigo (a pessoa já trocou de fundo)
	if not bool(res.get("ok", false)):
		_add_bubble("⚠ Fundo: " + String(res.get("msg", "não consegui preparar esse arquivo.")), "ai")
		return
	match String(res.get("tipo", "")):
		"imagem":
			if not _wp_mostrar_imagem(String(res.get("path", ""))):
				_add_bubble("⚠ Preparei a imagem de fundo, mas o Godot não conseguiu abri-la.", "ai")
		"ogv":
			_wp_tocar_ogv(String(res.get("path", "")))
		"quadros":
			if not _wp_tocar_quadros(String(res.get("dir", "")), float(res.get("fps", 12.0))):
				_add_bubble("⚠ Preparei o vídeo de fundo, mas não achei os quadros na pasta.", "ai")


func _on_settings_data(settings: Dictionary):
	_maybe_show_onboarding(settings)
	_apply_wallpaper(String(settings.get("chat_wallpaper_path", "")))
	if wallpaper_dim_rect:
		var dim_val = float(settings.get("chat_wallpaper_dim", 0.35))
		var tem_fundo := String(settings.get("chat_wallpaper_path", "")) != ""     # v1.1: sem papel de parede não escurece (no tema claro ficava cinza)
		wallpaper_dim_rect.color = Color(0, 0, 0, clampf(dim_val, 0.0, 1.0) if tem_fundo else 0.0)
	current_settings = settings
	# v20: a configuração de "vida" salva vale já na abertura (não só depois de Salvar)
	if akira_body and akira_body.has_method("vida_apply_config"):
		akira_body.vida_apply_config(String(settings.get("vida_nivel", "suave")),
			bool(settings.get("vida_bracos_naturais", true)), bool(settings.get("vida_olhar_mouse", true)))
	# CORREÇÃO ("não ter nenhum fixo de verdade", pedido do Anderson):
	# a Zenith embutida na cena era um caso especial que só saía de cena quando
	# você MUDAVA de VRM manualmente; no boot, sempre aparecia ela
	# primeiro, mesmo se você já tivesse escolhido outro VRM antes.
	# Agora, assim que a primeira sincronização de configurações chega
	# do Python, se já existe um vrm_model_path salvo, ele carrega
	# IMEDIATAMENTE pelo mesmo reload_vrm() que a troca manual usa — a
	# Zenith embutida deixa de ser um "padrão fixo" e vira só o que
	# aparece por meio segundo antes da primeira sincronização.
	var vrm_ao_conectar = String(settings.get("vrm_model_path", "")).strip_edges()
	# v18 — avatar salvo de uma versão antiga pode apontar pra FORA do projeto
	# (biblioteca externa / caminho do disco), que deforma cabelo/roupa e não é
	# mais suportado. Se existe um avatar do projeto com o mesmo nome, usa ele e
	# regrava a configuração; se não, avisa e fica no avatar padrão.
	if vrm_ao_conectar != "" and not vrm_ao_conectar.begins_with("res://"):
		var migrado = _resolver_avatar_salvo(vrm_ao_conectar)
		if migrado != "":
			settings["vrm_model_path"] = migrado
			if brain:
				brain.save_settings({"vrm_model_path": migrado})
			if not _migracao_avatar_avisada:
				_add_bubble("ℹ Seu avatar salvo estava fora do projeto — troquei pro equivalente em " +
					migrado + " (renderiza certo).", "ai")
		else:
			if not _migracao_avatar_avisada:
				_add_bubble("⚠ O avatar salvo (" + vrm_ao_conectar.get_file() + ") está fora do projeto e não é " +
					"mais carregado assim. Em Configurações > Corpo / VRM, clique em \"Adicionar avatar...\" e " +
					"escolha esse arquivo — eu importo pra você.", "ai")
		_migracao_avatar_avisada = true
		vrm_ao_conectar = migrado
	if vrm_ao_conectar != "" and akira_body and akira_body.has_method("reload_vrm") \
			and akira_body.get("_current_vrm_path") != vrm_ao_conectar:
		var erro_boot = akira_body.reload_vrm(vrm_ao_conectar)
		if erro_boot != "":
			push_warning("[Zenith/UI] Não consegui carregar o VRM salvo (" + vrm_ao_conectar + ") ao conectar: " + erro_boot)
	persona_name = String(settings.get("persona_name", "Zenith"))
	# CORREÇÃO: o título e o campo de mensagem ficavam presos no nome
	# padrão pra sempre, mesmo depois de renomear a persona e salvar —
	# eram criados uma vez só, no início, e nunca mais atualizados.
	if input_field and is_instance_valid(input_field):
		input_field.placeholder_text = "Escreva ou fale"       # v1.7: o título da barra de cima agora é o da conversa (_atualizar_titulo)

	# v19 — lista unificada de IAs vinda do Cérebro (catálogo opcional + Minhas IAs + serviços).
	# Alimenta a caixinha "Configurar uma IA", o seletor "IA que responde" e o seletor do topo.
	var ai_ui: Dictionary = settings.get("_ai_ui", {})
	var ai_entradas: Array = ai_ui.get("entradas", [])
	ai_shortcuts = ai_ui.get("atalhos", [])
	_refresh_ai_panel(ai_entradas, String(ai_ui.get("selecionar", "")))
	_ai_fill_active_selector(quick_ai_selector, ai_entradas, String(settings.get("active_ai", "")))

	for key in settings_fields.keys():
		var field = settings_fields[key]
		if key.begins_with("permission:"):
			var perm_key = key.replace("permission:", "")
			var val = settings.get("permissions", {}).get(perm_key, "ask")
			_select_option(field, val, field.get_meta("options", ["never", "ask", "always"]))
		elif key == "active_ai":
			_ai_fill_active_selector(field, ai_entradas, String(settings.get("active_ai", "")))
		elif key == "vrm_window_position":
			field.selected = clampi(int(settings.get("vrm_window_position", 0)), 0, 3)
		elif key == "vrm_click_through":
			field.selected = 1 if settings.get("vrm_click_through", true) else 0
		elif key == "voice_expression_intensity":
			var kv = float(settings.get("voice_expression_intensity", 1.8))
			field.selected = 0 if kv < 0.8 else (1 if kv < 1.4 else (2 if kv < 1.95 else 3))
		elif key == "vida_nivel":
			field.selected = maxi(0, ["desligado", "suave", "expressivo"].find(String(settings.get("vida_nivel", "suave"))))
		elif key == "vida_bracos_naturais" or key == "vida_olhar_mouse" or key == "vida_gestos_ia":
			field.selected = 1 if settings.get(key, true) else 0
		elif key == "voice_enabled":
			field.selected = 1 if settings.get("voice_enabled", true) else 0
		elif key == "mic_mode":
			field.selected = 1 if String(settings.get("mic_mode", "manual")) == "auto" else 0
		elif key == "mic_silence_ms":
			field.text = str(settings.get("mic_silence_ms", 900))
		elif key == "mic_max_seconds":
			field.text = str(settings.get("mic_max_seconds", 60))
		elif key == "proactive_enabled":
			field.selected = 1 if settings.get("proactive_enabled", true) else 0
		elif key == "response_streaming":
			field.selected = 1 if settings.get("response_streaming", true) else 0
		elif key == "multi_step_actions":
			field.selected = 1 if settings.get("multi_step_actions", true) else 0
		elif key == "thinking_mode":
			field.selected = 1 if settings.get("thinking_mode", "economico") == "pensante" else 0
		elif key == "proactive_minutes":
			field.text = str(settings.get("proactive_minutes", 15))
		elif key == "chat_wallpaper_dim":
			field.text = str(settings.get("chat_wallpaper_dim", 0.35))
		elif field is HSlider:
			field.value = float(settings.get(key, field.value))
		elif field is TextEdit:
			field.text = String(settings.get(key, ""))
		elif field is LineEdit:
			field.text = String(settings.get(key, ""))


func _select_option(opt: OptionButton, value: String, options: Array):
	var idx = options.find(value)
	opt.selected = idx if idx != -1 else 0


func _save_settings():
	_ai_flush_all()   # v19: chaves/endereços digitados no painel de IAs e ainda não salvos vão junto
	var changes = {}
	var permissions = {}
	for key in settings_fields.keys():
		var field = settings_fields[key]
		if key.begins_with("permission:"):
			var perm_key = key.replace("permission:", "")
			var opts = field.get_meta("options", ["never", "ask", "always"])
			permissions[perm_key] = opts[field.selected]
		elif key == "active_ai":
			# CORREÇÃO: antes era uma lista fixa de 4 ids — quebrava (índice fora
			# do range) assim que uma IA personalizada era selecionada.
			# Agora lê a MESMA lista dinâmica que populou o dropdown (salva
			# junto como metadado); id vazio (nenhuma IA cadastrada) não grava.
			var ai_opts = field.get_meta("options", [])
			if field.selected >= 0 and field.selected < ai_opts.size() and String(ai_opts[field.selected]) != "":
				changes["active_ai"] = ai_opts[field.selected]
		elif key == "vrm_window_position":
			changes["vrm_window_position"] = field.selected
		elif key == "vrm_click_through":
			changes["vrm_click_through"] = (field.selected == 1)
		elif key == "voice_expression_intensity":
			changes["voice_expression_intensity"] = [0.6, 1.0, 1.8, 2.0][clampi(field.selected, 0, 3)]
		elif key == "vida_nivel":
			changes["vida_nivel"] = ["desligado", "suave", "expressivo"][clampi(field.selected, 0, 2)]
		elif key == "vida_bracos_naturais" or key == "vida_olhar_mouse" or key == "vida_gestos_ia":
			changes[key] = (field.selected == 1)
		elif key == "voice_enabled":
			changes["voice_enabled"] = (field.selected == 1)
		elif key == "mic_mode":
			changes["mic_mode"] = "auto" if field.selected == 1 else "manual"
		elif key == "mic_silence_ms":
			changes["mic_silence_ms"] = float(field.text) if field.text.is_valid_float() else 900.0
		elif key == "mic_max_seconds":
			changes["mic_max_seconds"] = float(field.text) if field.text.is_valid_float() else 60.0
		elif key == "proactive_enabled":
			changes["proactive_enabled"] = (field.selected == 1)
		elif key == "response_streaming":
			changes["response_streaming"] = (field.selected == 1)
		elif key == "multi_step_actions":
			changes["multi_step_actions"] = (field.selected == 1)
		elif key == "thinking_mode":
			changes["thinking_mode"] = "pensante" if field.selected == 1 else "economico"
		elif key == "proactive_minutes":
			changes["proactive_minutes"] = float(field.text) if field.text.is_valid_float() else 15.0
		elif key == "chat_wallpaper_dim":
			changes["chat_wallpaper_dim"] = clampf(float(field.text) if field.text.is_valid_float() else 0.35, 0.0, 1.0)
		elif field is HSlider:
			changes[key] = field.value
		elif field is TextEdit:
			changes[key] = field.text
		elif field is LineEdit:
			changes[key] = field.text
	changes["permissions"] = permissions

	# Aplica no Corpo diretamente (mesmo processo, sem precisar da Ponte)
	# — mesma ideia do botão "Mover Zenith". Só troca o VRM se o caminho
	# realmente mudou, pra não recarregar o modelo toda vez que salvar
	# qualquer outra coisa na tela.
	if akira_body:
		if akira_body.has_method("update_window_properties"):
			var pos_idx = changes.get("vrm_window_position", 0)
			var size_str = changes.get("vrm_window_size", "420x640")
			var click_through = changes.get("vrm_click_through", true)
			akira_body.update_window_properties(pos_idx, size_str, click_through)
		if akira_body.has_method("vida_apply_config"):
			akira_body.vida_apply_config(String(changes.get("vida_nivel", "suave")),
				bool(changes.get("vida_bracos_naturais", true)), bool(changes.get("vida_olhar_mouse", true)))
		var new_vrm_path = changes.get("vrm_model_path", "")
		var old_vrm_path = current_settings.get("vrm_model_path", "")
		if new_vrm_path != "" and new_vrm_path != old_vrm_path and akira_body.has_method("reload_vrm"):
			var erro = akira_body.reload_vrm(new_vrm_path)
			if erro != "":
				_add_bubble("⚠ VRM: " + erro, "ai")
			else:
				_add_bubble("✓ VRM trocado com sucesso.", "ai")

	if brain:
		brain.save_settings(changes)
	_hide_overlay(settings_overlay)


func _on_settings_saved(warnings: Array):
	if warnings.size() > 0:
		_add_bubble("⚠ Configurações salvas com avisos:\n- " + "\n- ".join(warnings), "ai")
	if brain:
		brain.request_settings()


func _on_api_key_test_result(provider: String, valid: bool, message: String):
	var status: Label = api_test_status_labels.get(provider)
	if not status:
		return
	status.text = ("✓ " if valid else "✗ ") + message
	status.add_theme_color_override("font_color", GREEN if valid else RED)


# v26 — linha de status + botão ⏹ Parar: o Cérebro manda "atividade" a cada mudança (pensando, rodando, falando...)
func _on_atividade_ui(estado: String, icone: String, texto: String, pode_parar: bool):
	if atividade_lbl == null or not is_instance_valid(atividade_lbl):
		return
	var ocupado: bool = estado != "ocioso" and texto != ""
	_mic_fase_id += 1
	atividade_lbl.visible = ocupado
	atividade_lbl.text = (icone + "  " + texto) if icone != "" else texto
	if parar_btn != null and is_instance_valid(parar_btn):
		parar_btn.visible = pode_parar and estado != "ocioso"


# v26 — fases do microfone: cada uma com ícone, texto e cor próprios (antes era sempre o mesmo ícone)
func _on_mic_fase_ui(fase: String, texto: String):
	var icones := {"ouvindo": "🎙", "captando": "🔴", "transcrevendo": "✍", "enviado": "✅", "nada": "🤷"}
	var cores := {"ouvindo": Color("ff4d4d"), "captando": Color("4dff88"), "transcrevendo": Color("ffc14d")}
	if mic_btn != null and is_instance_valid(mic_btn) and cores.has(fase):
		mic_btn.add_theme_color_override("font_color", cores[fase])
		_ic(mic_btn, {"ouvindo": "🎙", "captando": "🎙", "transcrevendo": "✦"}[fase])
		mic_btn.tooltip_text = texto
	if atividade_lbl == null or not is_instance_valid(atividade_lbl):
		return
	atividade_lbl.visible = true
	atividade_lbl.text = String(icones.get(fase, "🎙")) + "  " + texto
	_mic_fase_id += 1
	if fase == "enviado" or fase == "nada":
		var meu_id: int = _mic_fase_id
		get_tree().create_timer(2.5).timeout.connect(func():
			if meu_id == _mic_fase_id and atividade_lbl != null and is_instance_valid(atividade_lbl):
				atividade_lbl.visible = false)


# v23 — liga/desliga o botão "🔴 Parar observação" conforme o Cérebro avisa
func _on_observando_ui(ativo: bool, tipo: String, _info: String):
	if obs_btn == null or not is_instance_valid(obs_btn):
		return
	obs_btn.visible = ativo
	if ativo:
		_ic(obs_btn, "🔴  Parar observação (" + ("tela" if tipo == "screen" else "câmera") + ")")


# =====================================================================================================================
#  v28 — MARKDOWN NO CHAT · EQUAÇÃO NO MEIO DO TEXTO · LARGURA QUE ACOMPANHA A JANELA · CAIXA DE TEXTO QUE CRESCE
#  (Enter envia, Shift+Enter quebra a linha) · AUTOCOMPLETAR de "/" · BARRA DE PROGRESSO · AVISOS POPUP · MINI JANELA de anexo
#  Tudo aqui só DESENHA: quem decide o que mostrar é o Cérebro (Python), como sempre.
# =====================================================================================================================

# ---------------------------------------------------------------- markdown -> BBCode (o Label comum mostrava ** e * crus)
var _re_titulo: RegEx = null
var _re_lista: RegEx = null
var _re_codigo: RegEx = null
var _re_negrito: RegEx = null
var _re_italico: RegEx = null
var _re_regua: RegEx = null
var _re_equacao: RegEx = null


func _md_regex_init() -> void:
	if _re_titulo != null:
		return
	_re_titulo = RegEx.create_from_string("^(#{1,3})\\s+(.*)$")
	_re_lista = RegEx.create_from_string("^(\\s*)[-*•]\\s+(.*)$")
	_re_codigo = RegEx.create_from_string("`([^`\\n]+)`")
	_re_negrito = RegEx.create_from_string("\\*\\*([^*\\n]+)\\*\\*")
	_re_italico = RegEx.create_from_string("(?<![*\\w])\\*([^*\\n]+)\\*(?![*\\w])")
	_re_regua = RegEx.create_from_string("^\\s*([-*_])\\1{2,}\\s*$")
	_re_equacao = RegEx.create_from_string("Equa[^\\d\\s]*\\s+(\\d+)")


func _esc_bb(s: String) -> String:
	return s.replace("[", "[lb]")


func _md_inline(s: String) -> String:
	s = _re_codigo.sub(s, "[bgcolor=#" + _hex_codigo() + "][code]$1[/code][/bgcolor]", true)
	s = _re_negrito.sub(s, "[b]$1[/b]", true)
	s = _re_italico.sub(s, "[i]$1[/i]", true)
	return s


func _md_linha(t: String) -> String:
	var s: String = _esc_bb(t)
	if _re_regua.search(s) != null:
		return "[color=#5a5c78]──────────────────────[/color]"
	var m: RegExMatch = _re_titulo.search(s)
	if m != null:
		var nivel: int = m.get_string(1).length()
		var tam: int = 22 if nivel == 1 else (19 if nivel == 2 else 17)
		return "[b][font_size=%d]%s[/font_size][/b]" % [tam, _md_inline(m.get_string(2))]
	m = _re_lista.search(s)
	if m != null:
		var recuo: int = m.get_string(1).length() >> 1
		return "    ".repeat(recuo) + "  •  " + _md_inline(m.get_string(2))
	return _md_inline(s)


func _md_a_bbcode(texto: String) -> String:
	_md_regex_init()
	var saida: PackedStringArray = PackedStringArray()
	var em_codigo: bool = false
	var bloco: PackedStringArray = PackedStringArray()
	for linha in texto.split("\n"):
		if linha.strip_edges().begins_with("```"):
			if em_codigo:
				saida.append("[bgcolor=#" + _hex_codigo() + "][code]" + "\n".join(bloco) + "[/code][/bgcolor]")
				bloco = PackedStringArray()
				em_codigo = false
			else:
				em_codigo = true
			continue
		if em_codigo:
			bloco.append(_esc_bb(linha))
			continue
		saida.append(_md_linha(linha))
	if em_codigo:   # bloco de código ainda aberto (a resposta está chegando): mostra o que já veio
		saida.append("[bgcolor=#" + _hex_codigo() + "][code]" + "\n".join(bloco) + "[/code][/bgcolor]")
	return "\n".join(saida)


func _novo_rich() -> RichTextLabel:
	var rl: RichTextLabel = RichTextLabel.new()
	rl.bbcode_enabled = true
	rl.fit_content = true
	rl.scroll_active = false
	rl.selection_enabled = true
	rl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	rl.mouse_filter = Control.MOUSE_FILTER_PASS
	rl.add_theme_color_override("default_color", TEXT_PRIMARY)
	return rl


# ---------------------------------------------------------------- texto do balão + largura que acompanha a janela
func _texto_do_balao(label: Control) -> String:
	var col = label.get_meta("col", null)
	if col != null and is_instance_valid(col) and col.has_meta("raw_full"):
		return str(col.get_meta("raw_full"))
	return str(label.get_meta("raw", ""))


func _definir_texto_balao(label: Control, raw: String, completo: bool = true) -> void:
	label.set_meta("raw", raw)
	if completo and label.get_meta("primeiro", false):
		var col = label.get_meta("col", null)
		if col != null and is_instance_valid(col):
			col.set_meta("raw_full", raw)
	if label is RichTextLabel:
		label.text = _md_a_bbcode(raw)
	else:
		label.text = raw
	_ajustar_largura_balao(label, raw)


const LARGURA_LEITURA := 760.0          # v1.7: largura da coluna de conversa (a maquete usa ~720)
var _margem_chat: MarginContainer
var _margem_entrada: MarginContainer
var _pilula_entrada: PanelContainer


func _ajustar_margens_leitura() -> void:
	var largura: float = chat_scroll.size.x if (chat_scroll != null and is_instance_valid(chat_scroll)) else size.x
	var lado: int = int(maxf(20.0, (largura - LARGURA_LEITURA) / 2.0))
	for m in [_margem_chat, _margem_entrada]:
		if m != null and is_instance_valid(m):
			m.add_theme_constant_override("margin_left", lado)
			m.add_theme_constant_override("margin_right", lado)


func _largura_max_balao() -> float:
	var w: float = 700.0
	if chat_scroll != null and is_instance_valid(chat_scroll):
		w = minf(chat_scroll.size.x - 110.0, LARGURA_LEITURA - 40.0)       # margens do chat + margem interna do balão + folga
	return clampf(w, 240.0, 1000.0)


func _ajustar_largura_balao(label: Control, raw: String) -> void:
	var fonte: Font = label.get_theme_default_font()
	var tam: int = label.get_theme_default_font_size()
	if fonte == null:
		label.custom_minimum_size.x = _largura_max_balao()
		return
	var maior: float = 0.0
	for linha in raw.split("\n"):
		maior = maxf(maior, fonte.get_string_size(linha, HORIZONTAL_ALIGNMENT_LEFT, -1, tam).x)
	label.custom_minimum_size.x = clampf(maior + 14.0, 140.0, _largura_max_balao())


var _reajuste_pendente: bool = false


func _agendar_reajuste() -> void:
	if _reajuste_pendente:
		return
	_reajuste_pendente = true
	await get_tree().create_timer(0.12).timeout
	_reajuste_pendente = false
	_reajustar_baloes()


func _reajustar_baloes() -> void:
	if chat_log == null or not is_instance_valid(chat_log):
		return
	for row in chat_log.get_children():
		if not row.has_meta("col"):
			continue
		var col = row.get_meta("col")
		if col == null or not is_instance_valid(col):
			continue
		for filho in col.get_children():
			if filho is Control and filho.has_meta("raw"):
				_ajustar_largura_balao(filho, str(filho.get_meta("raw")))


# ---------------------------------------------------------------- equação NO MEIO do texto (não mais no fim do balão)
func _numero_da_equacao(caption: String) -> int:
	_md_regex_init()
	var m: RegExMatch = _re_equacao.search(caption)
	if m == null:
		return 0
	return int(m.get_string(1))


func _inserir_equacao_inline(n: int, tex: ImageTexture, img: Image, path: String) -> bool:
	# a imagem pode chegar um instante antes de o balão da resposta terminar de nascer: só espera se ainda há streaming
	var tentativas: int = 8 if (_stream_criando or _stream_label != null) else 1
	for _i in range(tentativas):
		if _tentar_inserir_equacao(n, tex, img, path):
			return true
		if tentativas > 1:
			await get_tree().create_timer(0.18).timeout
	return false


func _tentar_inserir_equacao(n: int, tex: ImageTexture, img: Image, path: String) -> bool:
	var marcador: String = "[Equação %d ↓]" % n
	var visitados: int = 0
	for k in range(chat_log.get_child_count() - 1, -1, -1):
		var row = chat_log.get_child(k)
		if not row.has_meta("col") or not row.get_meta("ia", false):
			continue
		visitados += 1
		if visitados > 2:
			break
		var col = row.get_meta("col")
		if col == null or not is_instance_valid(col):
			continue
		for filho in col.get_children():
			if filho is Control and filho.has_meta("raw") and str(filho.get_meta("raw")).find(marcador) >= 0:
				_dividir_no_marcador(col, filho, marcador, tex, img, path)
				return true
	return false


func _dividir_no_marcador(col: Control, label: Control, marcador: String, tex: ImageTexture, img: Image, path: String) -> void:
	var raw: String = str(label.get_meta("raw"))
	var idx: int = raw.find(marcador)
	var antes: String = raw.substr(0, idx).strip_edges(false, true)
	var fim_linha: int = raw.find("\n", idx)
	var depois: String = "" if fim_linha == -1 else raw.substr(fim_linha + 1).strip_edges(true, false)
	_definir_texto_balao(label, antes, false)
	label.visible = antes != ""
	var w: float = clampf(float(img.get_width()), 120.0, minf(520.0, _largura_max_balao() - 20.0))
	var h: float = clampf(w * float(img.get_height()) / maxf(float(img.get_width()), 1.0), 24.0, 300.0)
	var rect: TextureRect = TextureRect.new()
	rect.texture = tex
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	rect.custom_minimum_size = Vector2(w, h)
	rect.mouse_filter = Control.MOUSE_FILTER_STOP
	rect.tooltip_text = "Clique pra abrir a equação em tamanho real"
	rect.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
			OS.shell_open(path))
	col.add_child(rect)
	col.move_child(rect, label.get_index() + 1)
	var resto: RichTextLabel = _novo_rich()
	resto.set_meta("col", col)
	col.add_child(resto)
	col.move_child(resto, rect.get_index() + 1)
	_definir_texto_balao(resto, depois, false)
	resto.visible = depois != ""
	await get_tree().process_frame
	chat_scroll.scroll_vertical = int(chat_scroll.get_v_scroll_bar().max_value)


# ---------------------------------------------------------------- caixa de texto que cresce (Enter envia · Shift+Enter quebra)
func _ajustar_altura_entrada() -> void:
	if input_field == null or not is_instance_valid(input_field):
		return
	var linhas: int = maxi(1, input_field.get_total_visible_line_count())
	var alt: float = float(mini(linhas, 8)) * float(input_field.get_line_height()) + 20.0
	input_field.custom_minimum_size.y = maxf(alt, 42.0)


func _on_entrada_mudou() -> void:
	call_deferred("_ajustar_altura_entrada")
	_atualizar_autocompletar()


func _cursor_no_fim_da_entrada() -> void:
	var ultima: int = input_field.get_line_count() - 1
	input_field.set_caret_line(ultima)
	input_field.set_caret_column(input_field.get_line(ultima).length())


# ---------------------------------------------------------------- autocompletar de comandos ("/" + letras)
var _ac_panel: PanelContainer = null
var _ac_lista: ItemList = null
var _ac_itens: Array = []
var _ac_filtrados: Array = []


func _on_comandos_lista(itens: Array) -> void:
	_ac_itens = itens


func _autocompletar_ativo() -> bool:
	return _ac_panel != null and is_instance_valid(_ac_panel) and _ac_panel.visible and _ac_filtrados.size() > 0


func _atualizar_autocompletar() -> void:
	if _ac_panel == null or not is_instance_valid(_ac_panel):
		return
	var t: String = input_field.text
	if not t.begins_with("/") or t.contains(" ") or t.contains("\n") or _ac_itens.is_empty():
		_ac_panel.visible = false
		_ac_filtrados = []
		return
	var prefixo: String = t.substr(1).to_lower()
	_ac_filtrados = []
	for it in _ac_itens:
		var cmd: String = str(it.get("cmd", ""))
		if cmd.substr(1).to_lower().begins_with(prefixo):
			_ac_filtrados.append(it)
		if _ac_filtrados.size() >= 8:
			break
	if _ac_filtrados.is_empty():
		_ac_panel.visible = false
		return
	_ac_lista.clear()
	for it in _ac_filtrados:
		var desc: String = str(it.get("desc", ""))
		if desc.length() > 64:
			desc = desc.substr(0, 61) + "…"
		var uso: String = str(it.get("uso", ""))
		var idx: int = _ac_lista.add_item(str(it.get("cmd", "")) + ("  " + uso if uso != "" else "") + ("   —   " + desc if desc != "" else ""))
		_ac_lista.set_item_tooltip(idx, (uso + "\n" if uso != "" else "") + str(it.get("desc", "")))
	_ac_lista.select(0)
	_ac_lista.custom_minimum_size.y = float(mini(_ac_filtrados.size(), 6)) * 26.0 + 8.0
	_ac_panel.visible = true


func _autocompletar_escolher(i: int) -> void:
	if i < 0 or i >= _ac_filtrados.size():
		return
	input_field.text = str(_ac_filtrados[i].get("cmd", "")) + " "
	_cursor_no_fim_da_entrada()
	_ac_panel.visible = false
	_ac_filtrados = []
	input_field.grab_focus()
	call_deferred("_ajustar_altura_entrada")


func _autocompletar_mover(delta: int) -> void:
	if _ac_filtrados.is_empty():
		return
	var sel: PackedInt32Array = _ac_lista.get_selected_items()
	var atual: int = sel[0] if sel.size() > 0 else 0
	var novo: int = posmod(atual + delta, _ac_filtrados.size())
	_ac_lista.select(novo)
	_ac_lista.ensure_current_is_visible()


func _autocompletar_selecionado() -> int:
	var sel: PackedInt32Array = _ac_lista.get_selected_items()
	return sel[0] if sel.size() > 0 else -1


# ---------------------------------------------------------------- prévia de anexo (mini janela)
func _pedir_previa(caminho: String) -> void:
	if caminho == "":
		return
	if brain and brain.has_method("request_anexo"):
		brain.request_anexo(caminho)


func _add_anexo_botao(caminho: String) -> void:
	var row: HBoxContainer = HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var spacer: Control = Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	var btn: Button = _make_button("🔍  Abrir prévia de " + caminho.get_file(), BG_SURFACE_3, CYAN_DIM, TEXT_SECOND)
	btn.custom_minimum_size = Vector2(0, 28)
	btn.tooltip_text = "Clique pra ver o que tem dentro do arquivo"
	btn.pressed.connect(func(): _pedir_previa(caminho))
	row.add_child(btn)
	chat_log.add_child(row)


func _on_anexo_resumo(d: Dictionary) -> void:
	var janela: Window = Window.new()
	janela.title = str(d.get("nome", "Anexo")) + "  —  prévia"
	janela.size = Vector2i(760, 580)
	janela.min_size = Vector2i(420, 300)
	janela.transient = true
	janela.exclusive = false
	janela.visible = false       # só aparece no popup_centered(), sem piscar no canto
	janela.close_requested.connect(func(): janela.queue_free())

	var fundo: ColorRect = ColorRect.new()
	fundo.color = BG_BASE
	fundo.set_anchors_preset(Control.PRESET_FULL_RECT)
	janela.add_child(fundo)

	var margem: MarginContainer = MarginContainer.new()
	margem.set_anchors_preset(Control.PRESET_FULL_RECT)
	for lado in ["left", "right", "top", "bottom"]:
		margem.add_theme_constant_override("margin_" + lado, 14)
	janela.add_child(margem)

	var col: VBoxContainer = VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	margem.add_child(col)

	var cab: Label = Label.new()
	cab.text = "📄 " + str(d.get("nome", "")) + "   ·   " + str(d.get("tipo", "")) + "   ·   " + str(d.get("tamanho", ""))
	cab.add_theme_color_override("font_color", TEXT_PRIMARY)
	col.add_child(cab)

	var miniatura: String = str(d.get("miniatura", ""))
	if miniatura != "" and FileAccess.file_exists(miniatura):
		var im: Image = Image.new()
		if im.load(miniatura) == OK:
			var tr: TextureRect = TextureRect.new()
			tr.texture = ImageTexture.create_from_image(im)
			tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			tr.custom_minimum_size = Vector2(0, 260)
			tr.size_flags_vertical = Control.SIZE_EXPAND_FILL if str(d.get("texto", "")) == "" else Control.SIZE_FILL
			col.add_child(tr)

	var corpo: TextEdit = TextEdit.new()
	corpo.editable = false
	corpo.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	corpo.text = str(d.get("texto", ""))
	corpo.size_flags_vertical = Control.SIZE_EXPAND_FILL
	corpo.add_theme_stylebox_override("normal", _panel_style(BG_SURFACE_2, 8))
	corpo.add_theme_stylebox_override("read_only", _panel_style(BG_SURFACE_2, 8))
	corpo.add_theme_color_override("font_color", TEXT_PRIMARY)
	corpo.add_theme_color_override("font_readonly_color", TEXT_PRIMARY)
	col.add_child(corpo)

	var botoes: HBoxContainer = HBoxContainer.new()
	botoes.add_theme_constant_override("separation", 8)
	var caminho: String = str(d.get("caminho", ""))
	var b_abrir: Button = _make_button("Abrir no programa", BG_SURFACE_3, CYAN_DIM)
	b_abrir.pressed.connect(func(): OS.shell_open(caminho))
	botoes.add_child(b_abrir)
	var b_pasta: Button = _make_button("Mostrar na pasta", BG_SURFACE_3, CYAN_DIM)
	b_pasta.pressed.connect(func(): OS.shell_show_in_file_manager(caminho))
	botoes.add_child(b_pasta)
	var b_copiar: Button = _make_button("Copiar texto", BG_SURFACE_3, CYAN_DIM)
	b_copiar.pressed.connect(func(): DisplayServer.clipboard_set(corpo.text))
	botoes.add_child(b_copiar)
	var folga: Control = Control.new()
	folga.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	botoes.add_child(folga)
	var b_fechar: Button = _make_button("Fechar", CYAN, CYAN_DIM, Color("04141a"))
	b_fechar.pressed.connect(func(): janela.queue_free())
	botoes.add_child(b_fechar)
	col.add_child(botoes)

	add_child(janela)
	janela.popup_centered()


# ---------------------------------------------------------------- AVISOS POPUP (toast) e BARRA DE PROGRESSO
var _camada_avisos: Control = null
var _toast_box: VBoxContainer = null
var _prog_lista_box: VBoxContainer = null
var _prog_overlay: ColorRect = null
var _prog_titulo: Label = null
var _prog_detalhe: Label = null
var _prog_barra: ProgressBar = null
var _prog_btn_cancelar: Button = null
var _prog_btn_fechar: Button = null
var _prog_ativos: Dictionary = {}       # id -> {titulo, detalhe, pct, bloqueia, cancelavel, timeout, ultimo, inicio, oculto}
var _prog_widgets: Dictionary = {}      # id -> {painel, titulo, detalhe, barra}
var _prog_checagem: float = 0.0


func _montar_camada_avisos() -> void:
	_camada_avisos = Control.new()
	_camada_avisos.set_anchors_preset(Control.PRESET_FULL_RECT)
	_camada_avisos.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_camada_avisos)

	# avisos popup: canto superior direito, somem sozinhos
	_toast_box = VBoxContainer.new()
	_toast_box.anchor_left = 1.0
	_toast_box.anchor_right = 1.0
	_toast_box.offset_left = -360.0
	_toast_box.offset_right = -16.0
	_toast_box.offset_top = 52.0
	_toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_box.add_theme_constant_override("separation", 8)
	_camada_avisos.add_child(_toast_box)

	# tarefas em andamento que NÃO travam nada (gerar imagem, editar vídeo…): canto inferior direito, acima da barra de digitar
	_prog_lista_box = VBoxContainer.new()
	_prog_lista_box.anchor_left = 1.0
	_prog_lista_box.anchor_right = 1.0
	_prog_lista_box.anchor_top = 1.0
	_prog_lista_box.anchor_bottom = 1.0
	_prog_lista_box.offset_left = -360.0
	_prog_lista_box.offset_right = -16.0
	_prog_lista_box.offset_top = -110.0
	_prog_lista_box.offset_bottom = -110.0
	_prog_lista_box.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_prog_lista_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_prog_lista_box.add_theme_constant_override("separation", 8)
	_camada_avisos.add_child(_prog_lista_box)

	# "espere, tá carregando, não faça mais nada": tela escurecida (só pro que é realmente exclusivo, ex.: importar avatar)
	_prog_overlay = ColorRect.new()
	_prog_overlay.color = Color(0.02, 0.03, 0.08, 0.78)
	_prog_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	_prog_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	_prog_overlay.visible = false
	_camada_avisos.add_child(_prog_overlay)
	var centro: CenterContainer = CenterContainer.new()
	centro.set_anchors_preset(Control.PRESET_FULL_RECT)
	centro.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_prog_overlay.add_child(centro)
	var card: PanelContainer = PanelContainer.new()
	card.custom_minimum_size = Vector2(460, 0)
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 14, CYAN_DIM, 1))
	centro.add_child(card)
	var m: MarginContainer = MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + lado, 22)
	card.add_child(m)
	var c: VBoxContainer = VBoxContainer.new()
	c.add_theme_constant_override("separation", 10)
	m.add_child(c)
	_prog_titulo = Label.new()
	_prog_titulo.add_theme_font_size_override("font_size", 18)
	_prog_titulo.add_theme_color_override("font_color", TEXT_PRIMARY)
	c.add_child(_prog_titulo)
	var aviso: Label = Label.new()
	aviso.text = "Espere — estou trabalhando nisso. Não feche o Zenith e não faça mais nada até terminar."
	aviso.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	aviso.add_theme_color_override("font_color", TEXT_SECOND)
	c.add_child(aviso)
	_prog_barra = ProgressBar.new()
	_prog_barra.min_value = 0.0
	_prog_barra.max_value = 100.0
	_prog_barra.custom_minimum_size = Vector2(0, 22)
	c.add_child(_prog_barra)
	_prog_detalhe = Label.new()
	_prog_detalhe.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_prog_detalhe.add_theme_color_override("font_color", TEXT_MUTED)
	_prog_detalhe.add_theme_font_size_override("font_size", 12)
	c.add_child(_prog_detalhe)
	var linha: HBoxContainer = HBoxContainer.new()
	linha.alignment = BoxContainer.ALIGNMENT_END
	linha.add_theme_constant_override("separation", 8)
	c.add_child(linha)
	_prog_btn_fechar = _make_button("Fechar (continua em segundo plano)", BG_SURFACE_3, CYAN_DIM, TEXT_SECOND)
	_prog_btn_fechar.visible = false
	_prog_btn_fechar.pressed.connect(_prog_ocultar_bloqueio)
	linha.add_child(_prog_btn_fechar)
	_prog_btn_cancelar = _make_button("Cancelar", RED, MAGENTA, Color("1a0509"))
	_prog_btn_cancelar.visible = false
	_prog_btn_cancelar.pressed.connect(_prog_cancelar)
	linha.add_child(_prog_btn_cancelar)


func _mostrar_toast(texto: String, tipo: String = "info", segundos: float = 5.0) -> void:
	if _toast_box == null or not is_instance_valid(_toast_box):
		return
	var cor: Color = CYAN_DIM
	var icone: String = "info"     # v1.1: ícones próprios (antes eram emojis)
	if tipo == "ok":
		cor = GREEN
		icone = "ok"
	elif tipo == "aviso":
		cor = Color("fbbf24")
		icone = "aviso"
	elif tipo == "erro":
		cor = RED
		icone = "aviso"
	var painel: PanelContainer = PanelContainer.new()
	painel.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 10, cor, 1))
	painel.mouse_filter = Control.MOUSE_FILTER_STOP
	var m: MarginContainer = MarginContainer.new()
	m.add_theme_constant_override("margin_left", 12)
	m.add_theme_constant_override("margin_right", 12)
	m.add_theme_constant_override("margin_top", 8)
	m.add_theme_constant_override("margin_bottom", 8)
	painel.add_child(m)
	var linha_toast := HBoxContainer.new()
	linha_toast.add_theme_constant_override("separation", 8)
	var ic_toast := Icones.rect(icone, cor if tipo != "info" else CYAN, 18)
	ic_toast.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	linha_toast.add_child(ic_toast)
	var lbl: Label = Label.new()
	lbl.text = texto
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.custom_minimum_size.x = 300
	lbl.add_theme_color_override("font_color", TEXT_PRIMARY)
	linha_toast.add_child(lbl)
	m.add_child(linha_toast)
	painel.modulate.a = 0.0
	_toast_box.add_child(painel)
	painel.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed:
			painel.queue_free())
	var tw: Tween = create_tween()
	tw.tween_property(painel, "modulate:a", 1.0, 0.18)
	tw.tween_interval(segundos)
	tw.tween_property(painel, "modulate:a", 0.0, 0.4)
	tw.tween_callback(func():
		if is_instance_valid(painel):
			painel.queue_free())
	if _toast_box.get_child_count() > 4:
		_toast_box.get_child(0).queue_free()


func _on_aviso(d: Dictionary) -> void:
	_mostrar_toast(str(d.get("texto", "")), str(d.get("tipo", "info")), float(d.get("segundos", 5.0)))


func _on_progresso(d: Dictionary) -> void:
	var id: String = str(d.get("id", ""))
	if id == "":
		return
	if bool(d.get("fim", false)):
		_prog_remover(id)
		return
	if not _prog_ativos.has(id):
		_prog_ativos[id] = {"inicio": Time.get_ticks_msec(), "oculto": false}
	var a: Dictionary = _prog_ativos[id]
	a["titulo"] = str(d.get("titulo", ""))
	a["detalhe"] = str(d.get("detalhe", ""))
	a["pct"] = float(d.get("percentual", -1.0))
	a["bloqueia"] = bool(d.get("bloqueia", false))
	a["cancelavel"] = bool(d.get("cancelavel", false))
	a["timeout"] = maxf(float(d.get("timeout", 60.0)), 5.0)
	a["ultimo"] = Time.get_ticks_msec()
	_prog_redesenhar()


func _prog_remover(id: String) -> void:
	_prog_ativos.erase(id)
	if _prog_widgets.has(id):
		var w: Dictionary = _prog_widgets[id]
		if is_instance_valid(w["painel"]):
			w["painel"].queue_free()
		_prog_widgets.erase(id)
	_prog_redesenhar()


func _prog_id_bloqueante() -> String:
	var escolhido: String = ""
	for id in _prog_ativos.keys():
		var a: Dictionary = _prog_ativos[id]
		if a["bloqueia"] and not a["oculto"]:
			escolhido = str(id)
	return escolhido


func _prog_redesenhar() -> void:
	if _prog_overlay == null or not is_instance_valid(_prog_overlay):
		return
	# 1) a tela escurecida (só o que é bloqueante e ainda não foi "fechado" pelo usuário)
	var bid: String = _prog_id_bloqueante()
	if bid != "":
		var b: Dictionary = _prog_ativos[bid]
		_prog_titulo.text = str(b["titulo"])
		_prog_detalhe.text = str(b["detalhe"])
		if float(b["pct"]) >= 0.0:
			_prog_barra.value = float(b["pct"])
		_prog_barra.show_percentage = float(b["pct"]) >= 0.0
		_prog_btn_cancelar.visible = bool(b["cancelavel"])
		_prog_btn_fechar.visible = (Time.get_ticks_msec() - int(b["inicio"])) > 20000
		if not _prog_overlay.visible:
			_prog_overlay.visible = true
	else:
		_prog_overlay.visible = false
	# 2) os painéis discretos (tudo que NÃO está bloqueando a tela)
	for id in _prog_ativos.keys():
		var a: Dictionary = _prog_ativos[id]
		var discreto: bool = (not a["bloqueia"]) or a["oculto"]
		if not discreto:
			if _prog_widgets.has(id):
				var velho: Dictionary = _prog_widgets[id]
				if is_instance_valid(velho["painel"]):
					velho["painel"].queue_free()
				_prog_widgets.erase(id)
			continue
		if not _prog_widgets.has(id):
			_prog_widgets[id] = _criar_painel_progresso(str(id))
		var w: Dictionary = _prog_widgets[id]
		w["titulo"].text = str(a["titulo"])
		w["detalhe"].text = str(a["detalhe"])
		if float(a["pct"]) >= 0.0:
			w["barra"].value = float(a["pct"])


func _criar_painel_progresso(id: String) -> Dictionary:
	var painel: PanelContainer = PanelContainer.new()
	painel.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 10, CYAN_DIM, 1))
	var m: MarginContainer = MarginContainer.new()
	m.add_theme_constant_override("margin_left", 12)
	m.add_theme_constant_override("margin_right", 12)
	m.add_theme_constant_override("margin_top", 8)
	m.add_theme_constant_override("margin_bottom", 8)
	painel.add_child(m)
	var c: VBoxContainer = VBoxContainer.new()
	c.add_theme_constant_override("separation", 4)
	m.add_child(c)
	var topo: HBoxContainer = HBoxContainer.new()
	c.add_child(topo)
	var titulo: Label = Label.new()
	titulo.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	titulo.add_theme_color_override("font_color", TEXT_PRIMARY)
	topo.add_child(titulo)
	var cancelar: Button = _make_button("✕", Color(0, 0, 0, 0), BG_SURFACE_3, TEXT_MUTED)
	cancelar.custom_minimum_size = Vector2(26, 22)
	cancelar.tooltip_text = "Cancelar"
	cancelar.pressed.connect(_prog_cancelar)
	cancelar.visible = bool(_prog_ativos.get(id, {}).get("cancelavel", false))
	topo.add_child(cancelar)
	var barra: ProgressBar = ProgressBar.new()
	barra.min_value = 0.0
	barra.max_value = 100.0
	barra.show_percentage = false
	barra.custom_minimum_size = Vector2(0, 8)
	c.add_child(barra)
	var detalhe: Label = Label.new()
	detalhe.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detalhe.add_theme_font_size_override("font_size", 11)
	detalhe.add_theme_color_override("font_color", TEXT_MUTED)
	c.add_child(detalhe)
	_prog_lista_box.add_child(painel)
	return {"painel": painel, "titulo": titulo, "detalhe": detalhe, "barra": barra}


func _prog_cancelar() -> void:
	if brain:
		brain.send_to_brain({"action": "chat", "text": "/parar"})


func _prog_ocultar_bloqueio() -> void:
	for id in _prog_ativos.keys():
		if _prog_ativos[id]["bloqueia"]:
			_prog_ativos[id]["oculto"] = true
	_prog_redesenhar()


# chamada pelo _process (única função _process do arquivo): barra "vai e volta" quando não se sabe quanto falta + vigia de segurança
func _tick_progresso(delta: float) -> void:
	var t: float = float(Time.get_ticks_msec()) / 1000.0
	var onda: float = fposmod(t * 70.0, 200.0)
	onda = onda if onda <= 100.0 else 200.0 - onda
	for id in _prog_ativos.keys():
		var a: Dictionary = _prog_ativos[id]
		if float(a["pct"]) < 0.0:
			if a["bloqueia"] and not a["oculto"]:
				if _prog_barra != null and is_instance_valid(_prog_barra):
					_prog_barra.value = onda
			elif _prog_widgets.has(id):
				_prog_widgets[id]["barra"].value = onda
	_prog_checagem += delta
	if _prog_checagem < 1.0:
		return
	_prog_checagem = 0.0
	var agora: int = Time.get_ticks_msec()
	var mudou: bool = false
	for id in _prog_ativos.keys():
		var a2: Dictionary = _prog_ativos[id]
		if (agora - int(a2["ultimo"])) > int(float(a2["timeout"]) * 1000.0):
			# o Cérebro parou de dar notícias: NUNCA deixa a tela presa pra sempre
			if a2["bloqueia"]:
				_mostrar_toast("Perdi contato com o que estava trabalhando (" + str(a2["titulo"]) + ") — liberei a tela. Veja o chat/zenith_log.txt.", "erro", 8.0)
			_prog_remover(str(id))
			mudou = true
	if _prog_overlay != null and is_instance_valid(_prog_overlay) and _prog_overlay.visible and not mudou:
		var bid: String = _prog_id_bloqueante()
		if bid != "":
			_prog_btn_fechar.visible = (agora - int(_prog_ativos[bid]["inicio"])) > 20000


# ======================================================================
#  v1.6 — BIBLIOTECA / PROJETOS ZENITH: o que ela criou, separado por assunto
#  (programas por linguagem, sites, imagens, vídeos, documentos). Só LISTA; as duas ações são abrir a pasta
#  no Explorador e ver a imagem no chat. Rodar um programa continua sendo pedido no chat (com aprovação).
# ======================================================================
var projetos_overlay: Control
var programacao_page: RefCounted
var programacao_overlay: Control
var programacao_card: PanelContainer
var projetos_card: Control
var projetos_abas_box: VBoxContainer          # v1.6.1: duas fileiras de abas (o que ela criou / o que ela usa como base)
var projetos_fonte_dialog: FileDialog           # v1.6.1: seletor de documento para a biblioteca
var projetos_list_box: VBoxContainer
var projetos_dados_cache: Dictionary = {}
var projetos_aba: String = "programas"


func _build_projetos_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.65)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	dim.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed:
			_hide_overlay(projetos_overlay))
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 16, CYAN, 1))
	card.anchor_left = 0.12
	card.anchor_right = 0.78
	card.anchor_top = 0.08
	card.anchor_bottom = 0.92
	overlay.add_child(card)
	projetos_card = card

	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 10)
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 20)
	margin.add_child(vbox)
	card.add_child(margin)

	var header = HBoxContainer.new()
	vbox.add_child(header)
	var title = Label.new()
	title.text = "Biblioteca Zenith"
	title.add_theme_color_override("font_color", CYAN)
	title.add_theme_font_size_override("font_size", 18)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_btn = _make_button("Fechar", BG_SURFACE_2, BG_SURFACE_3)
	close_btn.pressed.connect(func(): _hide_overlay(projetos_overlay))
	header.add_child(close_btn)

	_hint(vbox, "O que ela criou e o que ela usa como base. Para rodar um programa, peça no chat (e você aprova, como sempre).")

	projetos_abas_box = VBoxContainer.new()
	projetos_abas_box.add_theme_constant_override("separation", 4)
	vbox.add_child(projetos_abas_box)

	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vbox.add_child(scroll)
	projetos_list_box = VBoxContainer.new()
	projetos_list_box.add_theme_constant_override("separation", 8)
	projetos_list_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(projetos_list_box)
	return overlay


func _on_projetos_dados(d):
	if typeof(d) != TYPE_DICTIONARY:
		return
	projetos_dados_cache = d
	_render_projetos()


func _fmt_bytes(n: int) -> String:
	if n < 1024:
		return str(n) + " B"
	if n < 1024 * 1024:
		return "%.1f KB" % (float(n) / 1024.0)
	if n < 1024 * 1024 * 1024:
		return "%.1f MB" % (float(n) / 1048576.0)
	return "%.1f GB" % (float(n) / 1073741824.0)


const PROJETOS_GRUPOS := [["criacoes", "O que ela criou"], ["base", "O que ela usa como base"]]


func _render_projetos():
	if projetos_list_box == null or projetos_abas_box == null:
		return
	for c in projetos_abas_box.get_children():
		c.queue_free()
	for c in projetos_list_box.get_children():
		c.queue_free()
	var cats: Array = projetos_dados_cache.get("categorias", [])
	if cats.is_empty():
		var vazio = Label.new()
		vazio.text = "Ainda não há nada aqui. Peça para criar um programa, uma imagem, um vídeo ou um site, e eles aparecem nesta Biblioteca."
		vazio.add_theme_color_override("font_color", TEXT_MUTED)
		vazio.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		projetos_list_box.add_child(vazio)
		return
	var existe: bool = false
	for cat in cats:
		if String(cat.get("id", "")) == projetos_aba:
			existe = true
	if not existe:
		projetos_aba = String(cats[0].get("id", "programas"))
	for g in PROJETOS_GRUPOS:
		var daqui: Array = []
		for cat in cats:
			if String(cat.get("grupo", "criacoes")) == String(g[0]):
				daqui.append(cat)
		if daqui.is_empty():
			continue
		var rotulo = Label.new()
		rotulo.text = String(g[1])
		rotulo.add_theme_color_override("font_color", TEXT_MUTED)
		rotulo.add_theme_font_size_override("font_size", 11)
		projetos_abas_box.add_child(rotulo)
		var fileira = HFlowContainer.new()
		fileira.add_theme_constant_override("h_separation", 6)
		fileira.add_theme_constant_override("v_separation", 6)
		projetos_abas_box.add_child(fileira)
		for cat in daqui:
			var cid: String = String(cat.get("id", ""))
			var ativa: bool = (cid == projetos_aba)
			var aba = _make_button(String(cat.get("titulo", cid)) + "  " + str(int(cat.get("total", 0))),
				Color(0, 0, 0, 0), BG_SURFACE_2, Color("1a1208") if ativa else TEXT_PRIMARY)
			for est in ["normal", "hover", "pressed"]:        # v1.7: abas em formato de pílula (a ativa em laranja), como na maquete
				aba.add_theme_stylebox_override(est, _panel_style(CYAN if ativa else (BG_SURFACE_2 if est != "normal" else Color(0, 0, 0, 0)),
					16, CYAN if ativa else BORDER, 1))
			aba.custom_minimum_size.y = 32
			aba.pressed.connect(func():
				projetos_aba = cid
				_render_projetos())
			fileira.add_child(aba)
	for cat in cats:
		if String(cat.get("id", "")) != projetos_aba:
			continue
		var dica: String = String(cat.get("dica", ""))
		if dica != "":
			var d = Label.new()
			d.text = dica
			d.add_theme_color_override("font_color", TEXT_MUTED)
			d.add_theme_font_size_override("font_size", 11)
			d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			projetos_list_box.add_child(d)
		if bool(cat.get("pode_adicionar", false)):
			var add = _make_button("Adicionar documento", CYAN_DIM, BG_SURFACE_3)
			add.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
			add.pressed.connect(_abrir_dialogo_fonte)
			projetos_list_box.add_child(add)
		var grupos: Array = cat.get("grupos", [])
		if grupos.is_empty():
			var nada = Label.new()
			nada.text = "Nenhum documento guardado ainda. Use Adicionar documento (PDF, Word, PowerPoint, Excel ou texto) e ela passa a responder citando o arquivo e a página." \
				if projetos_aba == "fontes" else "Nada nesta categoria ainda."
			nada.add_theme_color_override("font_color", TEXT_MUTED)
			nada.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			projetos_list_box.add_child(nada)
		for g in grupos:
			var gt = Label.new()
			gt.text = String(g.get("titulo", ""))
			gt.add_theme_color_override("font_color", CYAN)
			gt.add_theme_font_size_override("font_size", 14)
			projetos_list_box.add_child(gt)
			for item in g.get("itens", []):
				projetos_list_box.add_child(_linha_projeto(item))


# v1.6.1 — seletor de documento (Biblioteca > Fontes). O arquivo escolhido vai para o Cérebro, que o lê e guarda no índice local.
func _abrir_dialogo_fonte() -> void:
	if projetos_fonte_dialog == null or not is_instance_valid(projetos_fonte_dialog):
		projetos_fonte_dialog = FileDialog.new()
		projetos_fonte_dialog.access = FileDialog.ACCESS_FILESYSTEM
		projetos_fonte_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		projetos_fonte_dialog.use_native_dialog = true
		projetos_fonte_dialog.title = "Escolha um documento para a biblioteca"
		projetos_fonte_dialog.size = Vector2i(760, 520)
		projetos_fonte_dialog.add_filter("*.pdf, *.docx, *.pptx, *.xlsx, *.txt, *.md, *.csv", "Documentos")
		get_tree().root.add_child.call_deferred(projetos_fonte_dialog)
		projetos_fonte_dialog.file_selected.connect(func(caminho):
			if brain:
				brain.request_fonte_add(String(caminho)))
	projetos_fonte_dialog.popup_centered.call_deferred()


# Botão de dois toques ("Tirar" -> "Confirmar?") para ações que removem algo do índice; volta ao normal em 3 s.
func _botao_confirmar(rotulo: String, rotulo_confirma: String, acao: Callable) -> Button:
	var b = _make_button(rotulo, BG_SURFACE, BG_SURFACE_3)
	b.set_meta("armado", false)
	b.pressed.connect(func():
		if bool(b.get_meta("armado")):
			acao.call()
			return
		b.set_meta("armado", true)
		b.text = rotulo_confirma
		await get_tree().create_timer(3.0).timeout
		if is_instance_valid(b):
			b.set_meta("armado", false)
			b.text = rotulo)
	return b


func _linha_fonte(item: Dictionary) -> Control:
	var row = PanelContainer.new()
	row.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 8))
	var pad = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		pad.add_theme_constant_override("margin_" + side, 10)
	row.add_child(pad)
	var hb = HBoxContainer.new()
	hb.add_theme_constant_override("separation", 8)
	pad.add_child(hb)
	var col = VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 2)
	hb.add_child(col)
	var nome = Label.new()
	nome.text = String(item.get("nome", ""))
	nome.clip_text = true
	col.add_child(nome)
	var sub = Label.new()
	var partes: Array = [str(int(item.get("paginas", 0))) + " pág./blocos", str(int(item.get("trechos", 0))) + " trechos"]
	var quando: String = String(item.get("adicionado", ""))
	if quando != "":
		partes.append("guardado em " + quando)
	sub.text = "  ·  ".join(PackedStringArray(partes))
	sub.add_theme_color_override("font_color", TEXT_MUTED)
	sub.add_theme_font_size_override("font_size", 11)
	col.add_child(sub)
	var id: String = String(item.get("id", ""))
	hb.add_child(_botao_confirmar("Tirar da biblioteca", "Confirmar?", func():
		if brain:
			brain.request_fonte_remover(id)))
	return row


func _linha_biblia(item: Dictionary) -> Control:
	var row = PanelContainer.new()
	row.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 8))
	var pad = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		pad.add_theme_constant_override("margin_" + side, 10)
	row.add_child(pad)
	var vb = VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	pad.add_child(vb)
	var hb = HBoxContainer.new()
	hb.add_theme_constant_override("separation", 8)
	vb.add_child(hb)
	var col = VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 2)
	hb.add_child(col)
	var nome = Label.new()
	nome.text = String(item.get("nome", ""))
	nome.clip_text = true
	col.add_child(nome)
	var sub = Label.new()
	var partes: Array = []
	if bool(item.get("sempre", false)):
		partes.append("vai em toda conversa")
	else:
		var palavras: Array = item.get("palavras", [])
		if not palavras.is_empty():
			partes.append("entra quando falar de: " + ", ".join(PackedStringArray(palavras.slice(0, 6))))
	var origem: String = String(item.get("origem", "base"))
	partes.append({"base": "do programa", "arquivo": "arquivo seu", "aprendido": "aprendido com você"}.get(origem, origem))
	partes.append(_fmt_bytes(int(item.get("tamanho", 0))))
	sub.text = "  ·  ".join(PackedStringArray(partes))
	sub.add_theme_color_override("font_color", TEXT_MUTED)
	sub.add_theme_font_size_override("font_size", 11)
	sub.clip_text = true
	col.add_child(sub)
	var corpo = Label.new()
	corpo.text = String(item.get("texto", ""))
	corpo.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	corpo.add_theme_color_override("font_color", TEXT_SECOND)
	corpo.add_theme_font_size_override("font_size", 12)
	corpo.visible = false
	vb.add_child(corpo)
	var ler = _make_button("Ler", BG_SURFACE, BG_SURFACE_3)
	ler.pressed.connect(func():
		corpo.visible = not corpo.visible
		ler.text = "Fechar" if corpo.visible else "Ler")
	hb.add_child(ler)
	if bool(item.get("apagavel", false)):
		var id: String = String(item.get("id", ""))
		hb.add_child(_botao_confirmar("Apagar", "Confirmar?", func():
			if brain:
				brain.request_fonte_apagar_aprendido(id)))
	return row


func _linha_projeto(item: Dictionary) -> Control:
	var tipo_item: String = String(item.get("tipo", ""))
	if tipo_item == "fonte":            # v1.6.1 — documento guardado na biblioteca
		return _linha_fonte(item)
	if tipo_item == "biblia":           # v1.6.1 — cartão da Bíblia
		return _linha_biblia(item)
	var row = PanelContainer.new()
	row.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE_2, 8))
	var pad = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		pad.add_theme_constant_override("margin_" + side, 10)
	row.add_child(pad)
	var hb = HBoxContainer.new()
	hb.add_theme_constant_override("separation", 8)
	pad.add_child(hb)

	var col = VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 2)
	hb.add_child(col)
	var nome = Label.new()
	nome.text = String(item.get("nome", ""))
	nome.clip_text = true
	col.add_child(nome)
	var sub = Label.new()
	var partes: Array = []
	if String(item.get("tipo", "")) == "projeto":
		partes.append(str(int(item.get("arquivos", 0))) + " arquivo(s)")
		var langs: Array = item.get("linguagens", [])
		if not langs.is_empty():
			partes.append(", ".join(PackedStringArray(langs)))
	partes.append(_fmt_bytes(int(item.get("tamanho", 0))))
	var quando: float = float(item.get("modificado", 0.0))
	if quando > 0.0:
		partes.append(Time.get_datetime_string_from_unix_time(int(quando)).replace("T", " ").substr(0, 16))
	sub.text = "  ·  ".join(PackedStringArray(partes))
	sub.add_theme_color_override("font_color", TEXT_MUTED)
	sub.add_theme_font_size_override("font_size", 11)
	col.add_child(sub)

	var caminho: String = String(item.get("caminho", ""))
	var ext: String = String(item.get("extensao", "")).to_lower()
	if ext in ["png", "jpg", "jpeg", "gif", "webp", "bmp"]:
		var ver = _make_button("Ver no chat", BG_SURFACE, BG_SURFACE_3)
		ver.pressed.connect(func():
			if brain:
				brain.request_ver_projeto(caminho)
			_hide_overlay(projetos_overlay))
		hb.add_child(ver)
	var abrir = _make_button("Abrir pasta", BG_SURFACE, BG_SURFACE_3)
	abrir.pressed.connect(func():
		if brain:
			brain.request_abrir_projeto(caminho))
	hb.add_child(abrir)
	return row


func _on_atualizacao_disponivel(info: Dictionary):
	_dados_atualizacao = info
	if _btn_atualizar:
		var v = str(info.get("versao", ""))
		_btn_atualizar.text = "🚀 Atualizar v" + v
		_btn_atualizar.tooltip_text = "Nova versão disponível: v" + v + "\n" + str(info.get("notas", "")) + "\nClique para atualizar automaticamente agora."
		_btn_atualizar.visible = true

func _on_clique_atualizar():
	if _btn_atualizar:
		_btn_atualizar.disabled = true
		_btn_atualizar.text = "⏳ Atualizando..."
	if brain:
		_add_bubble("🚀 Iniciando atualização automática... O Zenith vai baixar a nova versão e aplicar preservando todas as suas conversas e chaves.", "ai")
		if brain.has_method("aplicar_atualizacao"):
			brain.aplicar_atualizacao()
		else:
			brain.send_chat("/atualizar instalar")


# ================= v1.22 — ÁREA DE PROGRAMAÇÃO & MENTORIA =================
func _build_programacao_overlay() -> Control:
	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.65)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	dim.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.pressed:
			_hide_overlay(programacao_overlay))
	overlay.add_child(dim)

	var card = PanelContainer.new()
	card.add_theme_stylebox_override("panel", _panel_style(BG_SURFACE, 16, CYAN, 1))
	card.anchor_left = 0.08
	card.anchor_right = 0.92
	card.anchor_top = 0.05
	card.anchor_bottom = 0.95
	overlay.add_child(card)
	programacao_card = card

	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 8)
	var margin = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	margin.add_child(vbox)
	card.add_child(margin)

	var header = HBoxContainer.new()
	vbox.add_child(header)
	var title = Label.new()
	title.text = "💻  Área de Programação & Mentoria"
	title.add_theme_color_override("font_color", CYAN)
	title.add_theme_font_size_override("font_size", 18)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_btn = _make_button("Fechar", BG_SURFACE_2, BG_SURFACE_3)
	close_btn.pressed.connect(func(): _hide_overlay(programacao_overlay))
	header.add_child(close_btn)

	var script = _script_opcional("res://zenith_programacao_page.gd")
	if script:
		programacao_page = script.new()
		programacao_page.montar(self, brain, vbox)

	return overlay
