extends Node3D

@export var breath_speed: float = 1.2
@export var breath_amount: float = 0.006
@export var head_look_speed: float = 0.5

var time: float = 0.0
var base_y: float = 0.0
var skeleton: Skeleton3D = null
var mesh_instance: MeshInstance3D = null
# CORREÇÃO (transparência "não funciona"): mesh_instance (acima) é só a
# PRIMEIRA malha encontrada — usada pros blend shapes de expressão (que
# realmente vivem numa malha só, a do rosto). Mas um VRM normalmente tem
# VÁRIAS malhas separadas (rosto, cabelo, roupa de cima, calça, sapato...).
# A transparência só mexia nessa primeira malha — o resto do corpo
# continuava 100% opaco, e por isso o efeito era imperceptível. Agora
# guardamos TODAS as malhas aqui, e a transparência aplica em todas.
var all_mesh_instances: Array = []

var neck_id: int = -1
var chest_id: int = -1
var head_id: int = -1
var left_arm_id: int = -1
var right_arm_id: int = -1

# CORREÇÃO (avatar "se contorce" após trocar VRM, mesmo recarregando o
# MESMO arquivo): guarda a extensão do addon VRM já registrada, pra
# registrar só uma vez (ver reload_vrm() mais abaixo).
var _vrm_gltf_extension: GLTFDocumentExtension = null

var target_head_rot: Vector3 = Vector3.ZERO
var current_head_rot: Vector3 = Vector3.ZERO
var next_head_change_time: float = 0.0

var next_blink_time: float = 3.0
var is_blinking: bool = false
var blink_timer: float = 0.0

var body_transparency: float = 1.0

# ---------- Estado de vida (novo) ----------
# Antes a única diferença entre "parada" e "falando" era abrir/fechar
# a boca. Agora o estado muda respiração, amplitude do olhar e um leve
# "tique" de pensamento — é isso que faz o avatar parecer vivo mesmo
# sem estar falando.
enum LifeState { IDLE, THINKING, SPEAKING, GREETING }

# v20 — motor de "vida" (expressões, boca, braços naturais, gestos, olhar o mouse). Fica em
# arquivo à parte (akira_vida.gd); este arquivo só o liga e continua com a base de sempre.
# Carregado com load() (e não preload) DE PROPÓSITO: se o akira_vida.gd tiver um erro, o preload
# derrubaria o akira_body.gd inteiro (avatar não abre). Com load(), só a "vida" fica desligada.
const VIDA_PATH := "res://akira_vida.gd"
var vida = null
var _vida_falhou: bool = false
var _vida_cfg_nivel: String = "suave"
var _vida_cfg_bracos: bool = true
var _vida_cfg_mouse: bool = true
var _vida_ultimo_relatorio: String = ""


var life_state: int = LifeState.IDLE
var hips_id: int = -1
var _current_expression_shape: int = -1
var _expression_blend: float = 0.0
var _expression_target: float = 0.0

# Controle de Janela
var edit_mode: bool = false
# VOLTADO PRA VERSÃO SIMPLES (v3): atravessar é tudo ou nada — com
# passthrough ligado (_click_through_enabled = true), a janela INTEIRA
# deixa o clique passar direto (não dá pra clicar nela diretamente,
# mas também não corta nada visualmente — ver set_edit_mode() mais
# abaixo pro porquê da versão anterior, com região, ter sido
# abandonada). Desligado, a janela inteira captura.
var _click_through_enabled: bool = true
var is_dragging: bool = false
var drag_offset: Vector2 = Vector2.ZERO # CORREÇÃO AQUI

# NOVO v10 — modo de ajuste fino por arraste ("janela a onde move o
# boneco" em vez de só digitar X/Y/Z/escala em número, pedido do
# Anderson). Mexe exatamente nas MESMAS _vrm_manual_offset/
# _vrm_manual_scale_mult que já existiam pro ajuste por número — arrastar
# e digitar acabam sendo dois jeitos de editar a mesma coisa, nunca dados
# duplicados. Nunca fica ligado ao mesmo tempo que edit_mode (Mover
# Zenith); quem garante isso é o par _toggle_move_avatar()/
# _toggle_adjust_drag() em ui_manager.gd.
var _adjust_drag_mode: bool = false
var _adjust_dragging: bool = false
var _adjust_drag_start_mouse: Vector2 = Vector2.ZERO
var _adjust_drag_start_offset: Vector3 = Vector3.ZERO
# v11 — valores de quando o modo foi ligado (botão direito = volta pra
# eles, "desfazer tudo") e a conversão pixel→mundo calculada no começo
# de cada arraste a partir da câmera de verdade (ver _pixels_to_world).
var _adjust_backup_offset: Vector3 = Vector3.ZERO
var _adjust_backup_scale: float = 1.0
var _adjust_px_to_world: float = 0.001

# Pose de descanso dos braços (guardada pra ser reforçada todo frame,
# já que animações/AnimationPlayer dentro do VRM podem resetar a pose)
var _left_arm_rest_target: Quaternion
var _right_arm_rest_target: Quaternion
var _arms_locked: bool = false

# SIMPLIFICADO (round "bruto primeiro, refina depois" — a pedido do
# Anderson): a versão anterior tentava ser "esperta" — media a altura
# de CADA VRM carregado (via AABB projetado) e calculava um fator de
# escala automático pra todos baterem na mesma altura da Zenith padrão,
# além de "encostar os pés" recalculando a AABB de novo depois de
# escalar. Essa esperteza foi exatamente o que ficou frágil (o "braço
# esquisito"/corpo deformado voltava mesmo com tudo em default). Agora
# a âncora guarda só ONDE na sala ela fica (posição X/Z e rotação) —
# não tenta mais adivinhar/corrigir altura ou escala sozinha. Qualquer
# VRM carrega na ESCALA NATIVA do arquivo (1.0), respeitando a
# convenção do próprio formato VRM de origem nos pés — sem cálculo
# nenhum por cima. Se um VRM específico precisar de ajuste, é pra isso
# que o ajuste fino manual (offset/escala, abaixo) existe — inclusive
# vai virar uma janela de arrastar-e-ver em vez de campo numérico.
const _VRM_ANCHOR_CFG_PATH = "user://vrm_anchor.cfg"
var _vrm_anchor_pos_xz: Vector2 = Vector2.ZERO
var _vrm_anchor_rot_y: float = 0.0
var _vrm_anchor_ready: bool = false
# Ajuste fino manual — a ÚNICA forma de escala/deslocamento agora
# (não tem mais cálculo automático por baixo). Persiste em disco.
var _vrm_manual_offset: Vector3 = Vector3.ZERO
var _vrm_manual_scale_mult: float = 1.0
var _current_vrm_path: String = ""   # pra "Aplicar ajuste" poder recarregar sem reabrir o seletor

# PAUSADO nesta rodada (não removido — só desligado por enquanto, a
# pedido do Anderson: primeiro deixar o "corpo" sólido e simples, com
# a pose 100% nativa do arquivo VRM, sem nenhuma pose forçada; braço/
# rosto reagindo por gesto entra numa rodada dedicada depois, em cima
# dessa base). _force_arms_down() e a reforço em _process() continuam
# no arquivo, só não são mais chamados — ver "PAUSADO" nos 3 lugares
# que chamavam isso antes (_ready, reload_vrm, _process).
var lock_arms_enabled: bool = false

# FEATURE (diagnosticar sem console): o .exe final roda com --noconsole,
# então print() não aparece pra ninguém em produção. Esse log próprio
# fica gravado do lado do executável (fácil de achar e mandar pra mim)
# — pensado especificamente pra depurar coisas como troca de VRM sem
# precisar recompilar em modo console.
const _DEBUG_LOG_PATH = "user://zenith_corpo_debug.log"

func _debug_log(msg: String):
	print("[Zenith/Corpo] " + msg)
	var f = FileAccess.open(_DEBUG_LOG_PATH, FileAccess.READ_WRITE if FileAccess.file_exists(_DEBUG_LOG_PATH) else FileAccess.WRITE)
	if f:
		f.seek_end()
		f.store_line(Time.get_datetime_string_from_system() + "  " + msg)
		f.close()

# NOVO: carrega a âncora salva em disco — ou, se essa é a PRIMEIRA vez
# que o programa roda (arquivo ainda não existe), calcula a partir de
# onde o avatar padrão está NESTE EXATO MOMENTO (posição, rotação,
# altura) e salva, virando o "lugar oficial" definitivo.
func _load_or_capture_anchor(avatar_padrao: Node3D):
	var cfg = ConfigFile.new()
	if cfg.load(_VRM_ANCHOR_CFG_PATH) == OK and cfg.has_section_key("anchor", "pos_x"):
		_vrm_anchor_pos_xz = Vector2(cfg.get_value("anchor", "pos_x", 0.0), cfg.get_value("anchor", "pos_z", 0.0))
		_vrm_anchor_rot_y = cfg.get_value("anchor", "rot_y", 0.0)
		_vrm_manual_offset = Vector3(cfg.get_value("adjust", "offset_x", 0.0), cfg.get_value("adjust", "offset_y", 0.0), cfg.get_value("adjust", "offset_z", 0.0))
		_vrm_manual_scale_mult = cfg.get_value("adjust", "scale_mult", 1.0)
		lock_arms_enabled = cfg.get_value("adjust", "lock_arms", false)
		# v11 — TRAVA DE SANIDADE: se um ajuste absurdo foi salvo (ex.: um
		# arraste que escapou e depois "Salvar ajuste"), ele faria a Zenith
		# nascer fora de quadro TODA vez que abre. Valores fora do razoável
		# são ignorados (volta pro padrão em memória; o arquivo só muda se
		# você salvar de novo).
		if (absf(_vrm_manual_offset.x) > 3.0 or absf(_vrm_manual_offset.y) > 3.0
				or absf(_vrm_manual_offset.z) > 3.0
				or _vrm_manual_scale_mult < 0.1 or _vrm_manual_scale_mult > 6.0):
			_debug_log("AVISO: ajuste manual salvo fora do razoável (offset=%s escala=%.3f) — ignorando e usando o padrão (0,0,0 / 1.0)." % [
				_vrm_manual_offset, _vrm_manual_scale_mult])
			_vrm_manual_offset = Vector3.ZERO
			_vrm_manual_scale_mult = 1.0
		_debug_log("Âncora carregada do disco: pos_xz=%s rot_y=%.3f | ajuste manual: offset=%s escala=%.3f" % [
			_vrm_anchor_pos_xz, _vrm_anchor_rot_y, _vrm_manual_offset, _vrm_manual_scale_mult])
	elif avatar_padrao:
		_vrm_anchor_pos_xz = Vector2(avatar_padrao.position.x, avatar_padrao.position.z)
		_vrm_anchor_rot_y = avatar_padrao.rotation.y
		_save_anchor()
		_debug_log("Primeira vez rodando — âncora capturada da Zenith padrão e salva: pos_xz=%s rot_y=%.3f" % [
			_vrm_anchor_pos_xz, _vrm_anchor_rot_y])
	_vrm_anchor_ready = true

func _save_anchor():
	var cfg = ConfigFile.new()
	cfg.load(_VRM_ANCHOR_CFG_PATH)   # preserva a outra seção se já existir
	cfg.set_value("anchor", "pos_x", _vrm_anchor_pos_xz.x)
	cfg.set_value("anchor", "pos_z", _vrm_anchor_pos_xz.y)
	cfg.set_value("anchor", "rot_y", _vrm_anchor_rot_y)
	cfg.save(_VRM_ANCHOR_CFG_PATH)

func _save_manual_adjust():
	var cfg = ConfigFile.new()
	cfg.load(_VRM_ANCHOR_CFG_PATH)
	cfg.set_value("adjust", "offset_x", _vrm_manual_offset.x)
	cfg.set_value("adjust", "offset_y", _vrm_manual_offset.y)
	cfg.set_value("adjust", "offset_z", _vrm_manual_offset.z)
	cfg.set_value("adjust", "scale_mult", _vrm_manual_scale_mult)
	cfg.set_value("adjust", "lock_arms", lock_arms_enabled)
	cfg.save(_VRM_ANCHOR_CFG_PATH)

# Chamado pela tela de Configurações. `persist=false` é usado pro "ver
# como fica" ao vivo enquanto mexe nos campos (não grava em disco
# ainda); `persist=true` é o "Salvar ajuste" de verdade. Sempre reaplica
# em cima do VRM atualmente carregado, sem precisar reabrir o seletor
# de arquivo.
func set_manual_vrm_adjust(offset: Vector3, scale_mult: float, persist: bool) -> String:
	_vrm_manual_offset = offset
	_vrm_manual_scale_mult = scale_mult if scale_mult > 0.01 else 1.0
	if persist:
		_save_manual_adjust()
	if _current_vrm_path != "":
		return reload_vrm(_current_vrm_path)
	else:
		# Sem arquivo customizado carregado — reaplica direto na Zenith padrão.
		var avatar = get_node_or_null("Akira")
		if avatar and _vrm_anchor_ready:
			avatar.position.x = _vrm_anchor_pos_xz.x + _vrm_manual_offset.x
			avatar.position.y = _vrm_manual_offset.y
			avatar.position.z = _vrm_anchor_pos_xz.y + _vrm_manual_offset.z
			avatar.scale = Vector3.ONE * _vrm_manual_scale_mult
		return ""

func reset_manual_vrm_adjust() -> String:
	return set_manual_vrm_adjust(Vector3.ZERO, 1.0, true)


# CORREÇÃO (avatar sumindo em telas por outro monitor):
# `DisplayServer.screen_get_size()` sem argumento pega a tela PRINCIPAL
# do Windows (monitor 0) — não a tela onde a "Central de Controle" está
# de fato aberta. Em setup com 2+ monitores, se a Central estiver no
# monitor secundário, o avatar era posicionado usando o tamanho do
# monitor primário, podendo cair fora da área visível daquele monitor
# (ou literalmente no monitor errado). As chamadas que posicionam esta
# janela (_ready() e update_window_properties()) agora usam esta função
# em vez de screen_get_size() puro.
func _tela_da_central() -> int:
	# Usar o CENTRO da janela da Central pra achar o monitor (em vez do
	# canto) — mais confiável perto da borda entre dois monitores de
	# tamanhos diferentes.
	for child in get_children():
		if child is Window:
			var p: Vector2i = child.position
			var s: Vector2i = child.size
			var centro: Vector2i = p + Vector2i(s.x / 2, s.y / 2)
			for i in DisplayServer.get_screen_count():
				var sp = DisplayServer.screen_get_position(i)
				var ss = DisplayServer.screen_get_size(i)
				if Rect2i(sp, ss).has_point(centro):
					_debug_log("Central detectada: pos=%s tamanho=%s → monitor %d" % [p, s, i])
					return i
			_debug_log("AVISO: Central achada (pos=%s) mas fora de todo monitor conhecido." % p)
			break
	# Fallback: tela onde ESTA janela (o Corpo) já estiver.
	return DisplayServer.window_get_current_screen()

# Roda separado do _ready() — só esta função espera a "Central de
# Controle" existir antes de posicionar o avatar.
func _posicionar_janela_avatar():
	await get_tree().process_frame
	await get_tree().process_frame
	var tela = _tela_da_central()
	var tela_pos = DisplayServer.screen_get_position(tela)
	var tela_size = DisplayServer.screen_get_size(tela)
	var alvo = tela_pos + Vector2i(tela_size.x - 435, 50)
	_debug_log("Corpo: pos=%s tam=%s | monitor %d (origem %s tam %s) | alvo=%s" % [
		DisplayServer.window_get_position(), DisplayServer.window_get_size(), tela, tela_pos, tela_size, alvo])
	# Mover a janela quando ela já está no lugar certo é desnecessário E
	# pode disparar o bug do Windows (DWM) que não repinta janelas
	# "layered" (per-pixel transparent) direito depois de reposicionar —
	# resultado: avatar invisível sem erro nenhum. Só move se estiver de
	# fato fora do lugar, e força redesenho depois.
	if Vector2(DisplayServer.window_get_position()).distance_to(Vector2(alvo)) > 4.0:
		DisplayServer.window_set_position(alvo)
		_debug_log("Janela movida pro alvo; forçando redraw (DWM).")
		_force_redraw()
	else:
		_debug_log("Janela já estava no lugar certo — não movi (evita bug de repaint do DWM).")

func _ready():
	# v28 — o contorno do cabelo/roupa aparecia serrilhado ("pontilhado") nos prints: liga o anti-aliasing do 3D (MSAA 4x + FXAA).
	# Se algum PC/driver reclamar (fundo preto, lentidão), abra o Zenith com o argumento  -- --sem-aa  e volta ao modo antigo.
	if not ("--sem-aa" in OS.get_cmdline_user_args()):
		get_viewport().msaa_3d = Viewport.MSAA_4X
		get_viewport().screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
	# Volta ao modelo de janela flutuante (igual à versão antiga que já
	# funcionava): esta janela (a do Corpo/avatar) fica sem borda,
	# transparente, sempre no topo, e o clique atravessa pra quem estiver
	# atrás — só "captura" o mouse quando o modo de mover está ligado.
	if OS.get_name() != "Android": DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true)   # v1.14: no celular há UMA tela; estas são da janela flutuante do PC
	if OS.get_name() != "Android": DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, true)
	if OS.get_name() != "Android": DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_TRANSPARENT, true)
	if OS.get_name() != "Android": DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, true)
	_atravessa_desejado = true
	_fundo_carregar_local()   # v23: se neste PC a transparência não funcionou, o modo sólido/chroma já vale desde o 1º quadro

	if OS.get_name() != "Android": DisplayServer.window_set_size(Vector2i(420, 640))
	# O posicionamento por monitor vira uma função À PARTE, chamada com
	# `call_deferred()` — só ELA espera os frames necessários pra "Central
	# de Controle" existir; o resto do _ready() roda na hora, síncrono.
	if OS.get_name() != "Android": _posicionar_janela_avatar.call_deferred()

	base_y = position.y
	var avatar_inicial = get_node_or_null("Akira")
	if avatar_inicial:
		_neutralize_vrm_node_constraints(avatar_inicial)
	_load_or_capture_anchor(avatar_inicial)
	if avatar_inicial and _vrm_anchor_ready and (_vrm_manual_offset != Vector3.ZERO or _vrm_manual_scale_mult != 1.0):
		# Reaplica um ajuste manual salvo de sessões anteriores, mesmo
		# sem trocar de VRM ainda nesta sessão.
		# TRAVA DE SANIDADE: sem ela, um valor esquisito salvo em
		# vrm_anchor.cfg (ex: testando o ajuste fino e esquecendo de
		# restaurar) faria a Zenith padrão nascer minúscula/gigante/fora
		# de quadro TODA VEZ que o programa abre — sem erro nenhum.
		var esc = _vrm_manual_scale_mult
		if esc < 0.2 or esc > 5.0:
			_debug_log(("AVISO: multiplicador de escala manual salvo (%.4f) está fora do " +
				"razoável (0.2–5.0) — ignorando e usando 1.0 pra não fazer a Zenith padrão " +
				"nascer minúscula/gigante. Confira/resete em Configurações > Corpo_VRM > " +
				"Ajuste fino.") % esc)
			esc = 1.0
		avatar_inicial.position.x = _vrm_anchor_pos_xz.x + _vrm_manual_offset.x
		avatar_inicial.position.y = _vrm_manual_offset.y
		avatar_inicial.position.z = _vrm_anchor_pos_xz.y + _vrm_manual_offset.z
		avatar_inicial.scale = Vector3.ONE * esc
	skeleton = _find_skeleton(self)
	mesh_instance = _find_mesh(self)
	all_mesh_instances = _find_all_meshes(self)
	
	if skeleton:
		neck_id = _find_bone_fuzzy(["Neck"], ["j_bip_c_neck"])
		chest_id = _find_bone_fuzzy(["Chest", "UpperChest"], ["j_bip_c_chest", "j_bip_c_upperchest"])
		head_id = _find_bone_fuzzy(["Head"], ["j_bip_c_head"])
		left_arm_id = _find_bone_fuzzy(["LeftUpperArm"], ["j_bip_l_upperarm"])
		right_arm_id = _find_bone_fuzzy(["RightUpperArm"], ["j_bip_r_upperarm"])
		hips_id = _find_bone_fuzzy(["Hips"], ["j_bip_c_hips"])
		_disable_autoplay_animation()
		# Ativa os braços relaxados por padrão para nunca travar em T-pose
		_force_arms_down()
	_vida_setup()

	# CORREÇÃO: BrainConnector é FILHO deste nó (".") e não irmão ("..").
	# Com "../BrainConnector" essa busca sempre falhava (retornava null),
	# então NENHUM sinal do Cérebro (fala/expressão/transparência/ação)
	# jamais era conectado ao corpo — por isso o avatar nunca reagia.
	var connector = get_node_or_null("BrainConnector")
	if connector:
		if connector.has_signal("akira_speaks"): connector.akira_speaks.connect(_on_akira_speaks)
		if connector.has_signal("akira_changes_expression"): connector.akira_changes_expression.connect(set_expression)
		if connector.has_signal("akira_set_transparency"): connector.akira_set_transparency.connect(set_transparency)
		if connector.has_signal("akira_receive_action"): connector.akira_receive_action.connect(receive_action)
		if connector.has_signal("avatar_fundo"): connector.avatar_fundo.connect(_on_avatar_fundo)       # v23
		if connector.has_signal("observando"): connector.observando.connect(_on_observando)             # v23
		if connector.has_signal("tft_config"): connector.tft_config.connect(_on_tft_config)              # v24
		if connector.has_signal("movimento"): connector.movimento.connect(_on_movimento)                  # v1.6

func _process(delta):
	time += delta
	if _op_cam != null and _op_main_cam != null and is_instance_valid(_op_main_cam):
		_op_cam.global_transform = _op_main_cam.global_transform

	# PAUSADO nesta rodada — reforço de pose de braço desligado junto com
	# o resto do sistema de travamento (ver nota no topo do arquivo).
	# if _arms_locked and lock_arms_enabled and skeleton:
	# 	if left_arm_id != -1:
	# 		skeleton.set_bone_pose_rotation(left_arm_id, _left_arm_rest_target)
	# 	if right_arm_id != -1:
	# 		skeleton.set_bone_pose_rotation(right_arm_id, _right_arm_rest_target)
	
	# RESPIRAÇÃO — mais rápida/rasa "pensando", mais calma parada
	var state_breath_mult = 1.6 if life_state == LifeState.THINKING else (1.15 if life_state == LifeState.SPEAKING else 1.0)
	position.y = base_y + sin(time * breath_speed * state_breath_mult) * breath_amount
	if chest_id != -1 and skeleton:
		var rest_pose = skeleton.get_bone_rest(chest_id).basis.get_rotation_quaternion()
		var breath_chest = Quaternion(Vector3(1, 0, 0), sin(time * breath_speed * state_breath_mult) * 0.01)
		skeleton.set_bone_pose_rotation(chest_id, rest_pose * breath_chest)

	# BALANÇO DE PESO — troca de perna de apoio bem lenta, quase
	# imperceptível, mas é o detalhe que impede a pose de parecer "travada
	# em pé feito estátua". Praticamente pausa durante THINKING (foco).
	if hips_id != -1 and skeleton:
		var sway_amount = 0.0 if life_state == LifeState.THINKING else 0.025
		var hips_rest = skeleton.get_bone_rest(hips_id).basis.get_rotation_quaternion()
		var sway = Quaternion(Vector3(0, 0, 1), sin(time * 0.35) * sway_amount)
		skeleton.set_bone_pose_rotation(hips_id, hips_rest * sway)

	# CABEÇA — olhar errante na maior parte do tempo; na THINKING, olha
	# mais pra cima/de lado com pausas mais longas (typico de "pensando");
	# na SPEAKING, movimentos um pouco mais frequentes/vivos.
	if time > next_head_change_time:
		match life_state:
			LifeState.THINKING:
				target_head_rot = Vector3(randf_range(-0.02, 0.12), randf_range(-0.15, 0.15), 0.0)
				next_head_change_time = time + randf_range(1.5, 3.0)
			LifeState.SPEAKING:
				target_head_rot = Vector3(randf_range(-0.06, 0.06), randf_range(-0.1, 0.1), 0.0)
				next_head_change_time = time + randf_range(1.2, 2.5)
			_:
				target_head_rot = Vector3(randf_range(-0.05, 0.05), randf_range(-0.08, 0.08), 0.0)
				next_head_change_time = time + randf_range(5.0, 12.0)

	current_head_rot = current_head_rot.lerp(target_head_rot, delta * head_look_speed)
	if neck_id != -1 and skeleton:
		var neck_rest = skeleton.get_bone_rest(neck_id).basis.get_rotation_quaternion()
		var look_quat = Quaternion.from_euler(current_head_rot)
		skeleton.set_bone_pose_rotation(neck_id, neck_rest * look_quat)

	_process_blink(delta)
	_process_expression_blend(delta)
	_update_transparency()
	_vida_update(delta)
	_mov_tick(delta)                         # v1.6: pulo, dança, câmera, janela
	_atravessa_heartbeat(delta)

# v1.17 (port celular) — AVATAR SIMPLES do downgrade: um personagem low-poly desenhado em código (zenith_avatar_simples.gd) que
# toma o lugar do VRM em celulares fracos. Fala a mesma língua do VRM (set_life_state / set_expression). Devolve "" se deu certo
# ou uma frase em português se não deu. Voltar ao VRM é só chamar com false (o VRM só foi escondido, não descarregado).
# Limite honesto: o VRM escondido continua na memória e o _process do Corpo ainda o consulta; o ganho é na hora de DESENHAR
# (sem esqueleto, sem sombreador MToon). Não comparado com o VRM de verdade (não há .vrm no pacote público).
const ANCORA_DO_AVATAR := Vector3(-0.013, -0.388, -1.285)      # onde a cena põe os pés do VRM
var _avatar_simples: Node3D = null

func usar_avatar_simples(ativo: bool) -> String:
	var vrm = get_node_or_null("Akira")
	if ativo:
		if _avatar_simples != null:
			return ""
		var caminho := "res://zenith_avatar_simples.gd"
		var script = load(caminho) if ResourceLoader.exists(caminho) else null
		if script == null:
			return "não consegui carregar o avatar simples (zenith_avatar_simples.gd)."
		var novo := Node3D.new()
		novo.set_script(script)
		novo.name = "AvatarSimples"
		add_child(novo)
		novo.global_position = vrm.global_position if vrm is Node3D else ANCORA_DO_AVATAR
		if vrm is Node3D:
			vrm.visible = false
		_avatar_simples = novo
		return ""
	if _avatar_simples != null:
		_avatar_simples.queue_free()
		_avatar_simples = null
	if vrm is Node3D:
		vrm.visible = true
	return ""

func set_life_state(state_name: String):
	if _avatar_simples != null:
		_avatar_simples.set_life_state(state_name)
	match state_name.to_lower():
		"thinking", "pensando": life_state = LifeState.THINKING
		"speaking", "falando": life_state = LifeState.SPEAKING
		"greeting": life_state = LifeState.GREETING
		_: life_state = LifeState.IDLE

func _process_blink(delta):
	if _vida_cuida_do_rosto(): return
	if not mesh_instance: return
	var blink_id = mesh_instance.find_blend_shape_by_name("Blink")
	if blink_id == -1: blink_id = mesh_instance.find_blend_shape_by_name("blink")
	if blink_id == -1: return
	
	if not is_blinking and time > next_blink_time:
		is_blinking = true
		blink_timer = 0.15
		mesh_instance.set_blend_shape_value(blink_id, 1.0)
	elif is_blinking:
		blink_timer -= delta
		if blink_timer <= 0.0:
			is_blinking = false
			next_blink_time = time + randf_range(2.0, 6.0)
			mesh_instance.set_blend_shape_value(blink_id, 0.0)

func _on_akira_speaks(text): pass

func set_expression(expression_name: String):
	if _avatar_simples != null:
		_avatar_simples.set_expression(expression_name)
	if vida != null and _vida_cuida_do_rosto():
		vida.set_emotion(expression_name)
		return
	if not mesh_instance: return

	var shape_index = -1
	match expression_name.to_lower():
		"happy", "feliz", "joy":
			shape_index = mesh_instance.find_blend_shape_by_name("Joy")
			if shape_index == -1: shape_index = mesh_instance.find_blend_shape_by_name("Happy")
		"angry", "brava", "anger":
			shape_index = mesh_instance.find_blend_shape_by_name("Angry")
			if shape_index == -1: shape_index = mesh_instance.find_blend_shape_by_name("Anger")
		"sad", "triste", "sorrow":
			shape_index = mesh_instance.find_blend_shape_by_name("Sorrow")
			if shape_index == -1: shape_index = mesh_instance.find_blend_shape_by_name("Sad")
		"surprised", "surpresa":
			shape_index = mesh_instance.find_blend_shape_by_name("Surprised")
		"neutral", "neutro":
			shape_index = mesh_instance.find_blend_shape_by_name("Neutral")

	if shape_index == _current_expression_shape:
		return

	# Solta a expressão anterior suavemente (ela quem cuida de zerar a si
	# mesma dentro de _process_expression_blend) e começa a subir a nova.
	if _current_expression_shape != -1:
		var fading = _current_expression_shape
		var start_val = mesh_instance.get_blend_shape_value(fading)
		_fade_out_shape(fading, start_val)

	_current_expression_shape = shape_index
	_expression_blend = 0.0
	_expression_target = 1.0 if shape_index != -1 else 0.0

func _fade_out_shape(shape_index: int, start_val: float):
	if shape_index == -1: return
	var t = create_tween()
	t.tween_method(func(v): if mesh_instance: mesh_instance.set_blend_shape_value(shape_index, v), start_val, 0.0, 0.35)

func _process_expression_blend(delta):
	if _vida_cuida_do_rosto(): return
	if _current_expression_shape == -1 or not mesh_instance: return
	_expression_blend = move_toward(_expression_blend, _expression_target, delta * 2.5)
	mesh_instance.set_blend_shape_value(_current_expression_shape, _expression_blend)

func set_transparency(value: float):
	body_transparency = value

# NOVO (diagnóstico braço torto): liga/desliga o travamento em tempo
# real, sem precisar trocar de VRM pra ver o efeito. Sempre salva — ao
# contrário do ajuste fino (offset/escala), aqui não faz muito sentido
# ter um "só testar" separado, é só ligado ou desligado mesmo.
func set_lock_arms(enabled: bool):
	# PAUSADO nesta rodada: só guarda a preferência em disco (pra já
	# estar configurado quando o sistema de travamento voltar, na rodada
	# de reações de braço/rosto) — não força pose nenhuma agora. Garante
	# que os braços fiquem na pose nativa do arquivo, sempre, enquanto
	# isso não volta.
	lock_arms_enabled = enabled
	_save_manual_adjust()
	_arms_locked = false
	if skeleton:
		if left_arm_id != -1:
			skeleton.set_bone_pose_rotation(left_arm_id, skeleton.get_bone_rest(left_arm_id).basis.get_rotation_quaternion())
		if right_arm_id != -1:
			skeleton.set_bone_pose_rotation(right_arm_id, skeleton.get_bone_rest(right_arm_id).basis.get_rotation_quaternion())

# v21 — TRANSPARÊNCIA SEM "FANTASMA". A versão do v20 deixava cada PEÇA do avatar translúcida
# (troca do shader MToon por uma variante com alpha) — e aí enxerga-se uma peça através da outra:
# roupa, corpo e cabelo aparecem uns por dentro dos outros (o "fantasma" que o Anderson viu).
# Agora é OPACIDADE EM GRUPO, como "opacidade da camada" num editor de imagem: o avatar inteiro é
# desenhado normalmente (opaco, sem nenhum material alterado) numa SubViewport com fundo
# transparente, e é essa IMAGEM PRONTA que é exibida com opacidade < 100%. Só liga quando a
# opacidade sai de 100% (a 100% nada muda: o caminho original continua intacto).
#  * a SubViewport usa o MESMO mundo 3D (luzes, ambiente, avatar) com uma câmera cópia da principal;
#  * a câmera principal fica sem enxergar nada (cull_mask = 0) enquanto isso, mas continua sendo a
#    "câmera da cena" (o ajuste por arraste e os limites de Z dependem dela);
#  * qualquer falha cai no comportamento de 100% (nunca deixa o avatar invisível).
var _op_ativo: bool = false
var _op_sub: SubViewport = null
var _op_cam: Camera3D = null
var _op_layer: CanvasLayer = null
var _op_rect: TextureRect = null
var _op_main_cam: Camera3D = null
var _op_main_cull: int = 1048575

func _update_transparency():
	var alpha = clampf(body_transparency, 0.05, 1.0)
	var quer = alpha < 0.995
	if quer and not _op_ativo:
		_opacidade_ligar()
	elif (not quer) and _op_ativo:
		_opacidade_desligar()
	if _op_ativo:
		_opacidade_atualizar(alpha)

func obter_textura_avatar() -> Texture2D:
	if _op_sub == null or not is_instance_valid(_op_sub):
		var main_cam = get_viewport().get_camera_3d() if get_viewport() else null
		_op_sub = SubViewport.new()
		_op_sub.name = "AvatarSubViewport"
		_op_sub.transparent_bg = true
		_op_sub.disable_3d = false
		_op_sub.gui_disable_input = true
		_op_sub.handle_input_locally = false
		_op_sub.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		_op_sub.size = Vector2i(320, 480)
		add_child(_op_sub)
		_op_cam = Camera3D.new()
		_op_cam.name = "AvatarSubCam"
		_op_sub.add_child(_op_cam)
		if main_cam != null:
			_op_main_cam = main_cam
			_op_cam.projection = main_cam.projection
			_op_cam.fov = main_cam.fov
			_op_cam.near = main_cam.near
			_op_cam.far = main_cam.far
			_op_cam.global_transform = main_cam.global_transform
	return _op_sub.get_texture()

func _opacidade_ligar():
	var main_cam = get_viewport().get_camera_3d()
	if main_cam == null:
		return
	var vp_size = Vector2i(get_viewport().get_visible_rect().size)
	if vp_size.x < 2 or vp_size.y < 2:
		return
	_op_main_cam = main_cam
	_op_main_cull = main_cam.cull_mask
	if _op_sub == null or not is_instance_valid(_op_sub):
		_op_sub = SubViewport.new()
		_op_sub.transparent_bg = true
		_op_sub.disable_3d = false
		_op_sub.gui_disable_input = true
		_op_sub.handle_input_locally = false
		_op_sub.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		_op_sub.msaa_3d = get_viewport().msaa_3d
		add_child(_op_sub)
		_op_cam = Camera3D.new()
		_op_sub.add_child(_op_cam)
		_op_layer = CanvasLayer.new()
		_op_layer.layer = 50
		add_child(_op_layer)
		_op_rect = TextureRect.new()
		_op_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_op_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_op_rect.stretch_mode = TextureRect.STRETCH_SCALE
		_op_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
		_op_layer.add_child(_op_rect)
	_op_sub.size = vp_size
	_op_sub.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_op_rect.texture = _op_sub.get_texture()
	if _op_rect.texture == null:
		_opacidade_desligar()
		return
	_op_cam.current = true
	_opacidade_copiar_camera()
	main_cam.cull_mask = 0           # a principal deixa de desenhar o avatar (a cópia desenha)
	_op_layer.visible = true
	_op_ativo = true

func _opacidade_copiar_camera():
	if _op_main_cam == null or not is_instance_valid(_op_main_cam) or _op_cam == null:
		return
	_op_cam.projection = _op_main_cam.projection
	_op_cam.fov = _op_main_cam.fov
	_op_cam.size = _op_main_cam.size
	_op_cam.near = _op_main_cam.near
	_op_cam.far = _op_main_cam.far
	_op_cam.keep_aspect = _op_main_cam.keep_aspect
	_op_cam.h_offset = _op_main_cam.h_offset
	_op_cam.v_offset = _op_main_cam.v_offset
	_op_cam.environment = _op_main_cam.environment
	_op_cam.attributes = _op_main_cam.attributes
	_op_cam.cull_mask = 1048575
	_op_cam.global_transform = _op_main_cam.global_transform

func _opacidade_atualizar(alpha: float):
	if _op_sub == null or _op_rect == null or not is_instance_valid(_op_sub):
		return
	var vp_size = Vector2i(get_viewport().get_visible_rect().size)
	if vp_size.x >= 2 and vp_size.y >= 2 and vp_size != _op_sub.size:
		_op_sub.size = vp_size
	_opacidade_copiar_camera()
	_op_rect.modulate = Color(1, 1, 1, alpha)

func _opacidade_desligar():
	if _op_main_cam != null and is_instance_valid(_op_main_cam):
		_op_main_cam.cull_mask = _op_main_cull          # a câmera principal volta a desenhar o avatar
	if _op_layer != null and is_instance_valid(_op_layer):
		_op_layer.visible = false
	if _op_sub != null and is_instance_valid(_op_sub):
		_op_sub.render_target_update_mode = SubViewport.UPDATE_DISABLED
	_op_ativo = false

func receive_action(action_name: String):
	var an = action_name.to_lower().strip_edges()
	# v20: "gesture:acenar", "emotion:happy" e os nomes de gesto soltos vão pro motor de vida
	if an.begins_with("gesture:"):
		if an == "gesture:pulinho" and _mov != null and _mov.existe("pulo"):
			_mov.tocar("pulo", 1.0)         # v1.6: o "pulinho" antigo era uma vibração de 1 cm; agora é um pulo de verdade
			return
		vida_play_gesture(an.substr(8))
		return
	if an.begins_with("emotion:"):
		if vida != null:
			vida.set_emotion(an.substr(8))
		return
	match an:
		"wave", "oi", "aceno":
			if not vida_play_gesture("acenar"):
				dar_oi()
		_:
			if an.begins_with("state:"):
				set_life_state(action_name.substr(6))
			elif vida != null and vida.gesture_names().has(an):
				vida.play_gesture(an)

func _force_arms_down():
	if not skeleton: return
	if left_arm_id != -1:
		var rest_pose = skeleton.get_bone_rest(left_arm_id).basis.get_rotation_quaternion()
		_left_arm_rest_target = rest_pose * Quaternion(Vector3(0, 0, 1), deg_to_rad(68)) * Quaternion(Vector3(1, 0, 0), deg_to_rad(12))
		skeleton.set_bone_pose_rotation(left_arm_id, _left_arm_rest_target)
	if right_arm_id != -1:
		var rest_pose = skeleton.get_bone_rest(right_arm_id).basis.get_rotation_quaternion()
		_right_arm_rest_target = rest_pose * Quaternion(Vector3(0, 0, 1), deg_to_rad(-68)) * Quaternion(Vector3(1, 0, 0), deg_to_rad(12))
		skeleton.set_bone_pose_rotation(right_arm_id, _right_arm_rest_target)
	_arms_locked = (left_arm_id != -1 or right_arm_id != -1)

# Procura um osso tentando primeiro os nomes "humanoides" que o addon VRM
# do Godot usa quando retargeta (ex: "LeftUpperArm"), e se não achar, cai
# pra uma busca livre por substring nos nomes crus do glTF (ex: contém
# "upperarm" e "l"/"left"). Funciona com qualquer rig VRM, não só o da Zenith.
func _find_bone_fuzzy(exact_names: Array, contains_any: Array) -> int:
	if not skeleton: return -1
	for n in exact_names:
		var id = skeleton.find_bone(n)
		if id != -1: return id
	for i in skeleton.get_bone_count():
		var bone_name = skeleton.get_bone_name(i).to_lower()
		for token in contains_any:
			if bone_name.find(String(token).to_lower()) != -1:
				return i
	return -1

# Se o VRM importado trouxer um AnimationPlayer com autoplay (comum em
# exports do VRoid/glTF), ele reescreve a pose dos ossos todo frame e é
# a causa mais provável do avatar voltar sozinho pro T-pose. Paramos
# qualquer animação de repouso tocando por baixo.
func _disable_autoplay_animation():
	var players = _find_all_animation_players(self)
	for p in players:
		if p.is_playing():
			print("[Zenith/Corpo] Parando AnimationPlayer '" + p.name + "' que estava sobrescrevendo a pose.")
			p.stop()
		p.autoplay = ""

func _find_all_animation_players(node) -> Array:
	var found = []
	for child in node.get_children():
		if child is AnimationPlayer:
			found.append(child)
		found.append_array(_find_all_animation_players(child))
	return found

func dar_oi():
	if not skeleton or right_arm_id == -1: return
	var rest_arm = skeleton.get_bone_rest(right_arm_id).basis.get_rotation_quaternion()
	var arm_up = rest_arm * Quaternion(Vector3(0, 0, 1), deg_to_rad(-90)) * Quaternion(Vector3(1, 0, 0), deg_to_rad(-90))
	var arm_mid = rest_arm * Quaternion(Vector3(0, 0, 1), deg_to_rad(-90)) * Quaternion(Vector3(1, 0, 0), deg_to_rad(-70))
	
	# Solta o "lock" do braço direito enquanto o aceno toca, senão o
	# reforço por frame do _process luta contra o tween e trava o braço.
	_arms_locked = false
	var tween = create_tween()
	tween.set_parallel(false)
	tween.tween_method(_set_arm_rot.bind(right_arm_id), rest_arm, arm_up, 0.4)
	tween.tween_method(_set_arm_rot.bind(right_arm_id), arm_up, arm_mid, 0.15)
	tween.tween_method(_set_arm_rot.bind(right_arm_id), arm_mid, arm_up, 0.15)
	tween.tween_method(_set_arm_rot.bind(right_arm_id), arm_up, arm_mid, 0.15)
	tween.tween_method(_set_arm_rot.bind(right_arm_id), arm_mid, rest_arm, 0.4)
	tween.tween_callback(func(): _arms_locked = true)

func _set_arm_rot(rot: Quaternion, bone_id: int):
	if skeleton: skeleton.set_bone_pose_rotation(bone_id, rot)

# ==========================================
# CONTROLE DA JANELA VRM E MODO EDIÇÃO
# ==========================================
func set_edit_mode(state):
	edit_mode = state
	# VOLTADO PRA VERSÃO SIMPLES (v3), a pedido do Anderson: a versão
	# anterior tentava calcular uma região exata (só o corpo dela
	# capturando clique, o resto atravessando) — e essa mesma conta é a
	# suspeita nº1 do "avatar esquisito/cortado", porque a documentação
	# oficial do Godot confirma que no Windows a parte da janela FORA da
	# região definida por window_set_mouse_passthrough() simplesmente
	# NÃO É DESENHADA. Essa versão volta pro jeito tudo-ou-nada que já
	# funcionava antes: em modo mover, a janela INTEIRA captura clique
	# (pra dar pra arrastar); fora do modo mover, a janela INTEIRA
	# atravessa (pra não atrapalhar clicar em nada atrás, executável
	# incluso) — sem região nenhuma, sem risco de recorte visual. O
	# preço: não dá mais pra clicar NELA diretamente enquanto atravessa
	# — pra interagir/mover, usa o botão "Mover Zenith" na Central, que
	# já é o fluxo principal hoje.
	# Respeita também a opção "Mouse atravessa a janela" das
	# Configurações (_click_through_enabled) — se o Anderson desligou
	# isso de propósito, sair do modo mover não deve religar o
	# atravessar por conta própria.
	_update_passthrough()

# NOVO v10 — antes essa conta ("a janela captura clique quando não deve
# atravessar") só existia dentro de set_edit_mode(). Virou função à parte
# pra dar pra somar edit_mode (Mover Zenith) e _adjust_drag_mode (Ajustar
# arrastando) sem repetir a linha em dois lugares.
func _update_passthrough():
	var captura_janela = edit_mode or _adjust_drag_mode
	var atravessa = (not captura_janela) and _click_through_enabled
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, atravessa)
	_notificar_clique_atravessa(atravessa)

# v20 — A flag MOUSE_PASSTHROUGH do Godot no Windows só deixa o clique passar para janelas do
# MESMO programa (usa HTTRANSPARENT); para a área de trabalho, a barra de tarefas e outros
# programas ela não resolve. Quem resolve de verdade é o estilo de janela WS_EX_TRANSPARENT do
# Windows — o Godot não expõe isso, então o Cérebro (Python) aplica na janela deste processo.
# Aqui só pedimos: "janela do processo N: clique atravessa = sim/não".
# Mensagem enviada com o Cérebro offline é descartada, então há um "batimento": a cada 3 s o
# estado DESEJADO é reenviado (o lado Python é idempotente — se já está certo, não faz nada).
# Isso cobre o começo (a janela ainda abrindo / WebSocket ainda conectando) e qualquer vez que o
# Windows ou o Godot refaçam o estilo da janela.
var _atravessa_desejado: bool = true
var _atravessa_timer: float = 0.0
func _notificar_clique_atravessa(ativo: bool, forcar: bool = false):
	_atravessa_desejado = ativo
	var connector = get_node_or_null("BrainConnector")
	if connector and connector.has_method("send_to_brain") and connector.get("websocket") != null:
		if connector.websocket.get_ready_state() == WebSocketPeer.STATE_OPEN:
			connector.send_to_brain({"action": "set_click_through", "pid": OS.get_process_id(), "active": ativo})

func _atravessa_heartbeat(delta: float):
	_atravessa_timer += delta
	if _atravessa_timer >= 3.0:
		_atravessa_timer = 0.0
		_notificar_clique_atravessa(_atravessa_desejado, true)

# NOVO v10 — liga/desliga o modo "arrastar pra ajustar". Mesmo esquema
# tudo-ou-nada de captura de clique do set_edit_mode() (ver comentário
# grande logo acima): enquanto ativo, a janela do avatar captura o
# clique inteira; ao desligar, volta a atravessar (se _click_through_
# enabled estiver ligado).
func set_adjust_drag_mode(state: bool):
	if state and not _adjust_drag_mode:
		_adjust_backup_offset = _vrm_manual_offset
		_adjust_backup_scale = _vrm_manual_scale_mult
	_adjust_drag_mode = state
	_adjust_dragging = false
	_update_passthrough()

# NOVO v10 — pro painel de Configurações (ui_manager.gd) ler os valores
# atuais enquanto o Anderson arrasta, e refletir isso nos 4 campos de
# número ao vivo. Os campos continuam sendo a fonte "oficial" na hora de
# "Salvar ajuste" — isso aqui só sincroniza o que já está valendo.
func get_manual_vrm_adjust() -> Array:
	return [_vrm_manual_offset, _vrm_manual_scale_mult]

func update_window_properties(pos_index, size_str, click_through):
	if OS.get_name() == "Android":
		return      # v1.14: não há janela do avatar para mover/redimensionar; a faixa de cima é decidida pelo layout de celular
	_click_through_enabled = click_through
	if not edit_mode and not _adjust_drag_mode:
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, click_through)
	_notificar_clique_atravessa((not edit_mode) and (not _adjust_drag_mode) and click_through, true)

	var new_size = Vector2i(420, 640)
	if "x" in size_str.to_lower():
		var parts = size_str.to_lower().split("x")
		if parts.size() == 2:
			var w = int(parts[0].strip_edges())
			var h = int(parts[1].strip_edges())
			if w > 100 and h > 100:
				new_size = Vector2i(w, h)
	DisplayServer.window_set_size(new_size)

	var tela = _tela_da_central()
	var tela_pos = DisplayServer.screen_get_position(tela)
	var screen_size = DisplayServer.screen_get_size(tela)
	var margin = 15
	var target_pos = tela_pos + Vector2i(screen_size.x - new_size.x - margin, margin)

	match pos_index:
		0: target_pos = tela_pos + Vector2i(screen_size.x - new_size.x - margin, margin)
		1: target_pos = tela_pos + Vector2i(screen_size.x - new_size.x - margin, screen_size.y - new_size.y - margin)
		2: target_pos = tela_pos + Vector2i(margin, margin)
		3: target_pos = tela_pos + Vector2i(margin, screen_size.y - new_size.y - margin)

	DisplayServer.window_set_position(target_pos)
	_force_redraw()

# CORREÇÃO (avatar some ao mover/redimensionar a janela): bug conhecido
# do Windows com janelas "layered" (per-pixel transparent) — o
# compositor (DWM) às vezes não repinta o buffer da janela depois de
# window_set_position()/window_set_size(), mesmo com per_pixel_
# transparency habilitado no project.godot (que já está certo). O
# conteúdo fica "congelado" invisível até algo force um redraw de
# verdade. Aqui forçamos isso mudando o tamanho em 1px e voltando —
# obriga o Windows a recompor a janela.
func _force_redraw():
	await get_tree().process_frame
	var s = DisplayServer.window_get_size()
	DisplayServer.window_set_size(s + Vector2i(1, 0))
	await get_tree().process_frame
	DisplayServer.window_set_size(s)

func _input(event):
	if edit_mode:
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				is_dragging = true
				drag_offset = event.position
			else:
				if is_dragging:
					# CORREÇÃO: mesmo bug do update_window_properties — só
					# força o redraw ao SOLTAR o mouse (não a cada frame do
					# arraste, que seria desperdício de performance).
					_force_redraw()
				is_dragging = false
		if event is InputEventMouseMotion and is_dragging:
			var current_pos = DisplayServer.window_get_position()
			var movement = event.position - drag_offset
			DisplayServer.window_set_position(current_pos + Vector2i(movement.x, movement.y))
	elif _adjust_drag_mode:
		_handle_adjust_drag_input(event)

# v11 — CORREÇÃO DE UM ERRO MEU DO v10: o fator fixo de 0.01 "mundo por
# pixel" estava ~10x grande demais pra câmera desta cena (câmera a ~0.93 m
# do avatar, campo de visão de ~0.68 m de altura numa janela de 640 px →
# ~0.001 m por pixel). Um arrastozinho jogava a Zenith longe, e Shift+roda
# podia empurrá-la pra dentro da câmera (o plano "near" corta o modelo e
# só aparece o miolo gigante). Agora a conversão é calculada da câmera de
# verdade no começo de cada arraste (o avatar acompanha o mouse 1:1), e
# tudo passa por limites de segurança em _reposition_live().
const _ADJUST_PIXELS_TO_WORLD_FALLBACK := 0.001
const _ADJUST_WHEEL_SCALE_FACTOR := 1.04   # cada "clique" da roda = +4% / -4% de escala
const _ADJUST_WHEEL_Z_STEP := 0.02         # metros por "clique" (Shift + roda)

# Quantos metros do mundo cabem em 1 pixel da janela, na profundidade em
# que a Zenith está agora. Usa FOV/altura da janela da câmera ativa.
func _pixels_to_world() -> float:
	var avatar = get_node_or_null("Akira")
	var cam = get_viewport().get_camera_3d()
	if avatar == null or cam == null:
		return _ADJUST_PIXELS_TO_WORLD_FALLBACK
	var vp = get_viewport().get_visible_rect().size
	if vp.x <= 0.0 or vp.y <= 0.0:
		return _ADJUST_PIXELS_TO_WORLD_FALLBACK
	var frente = -cam.global_transform.basis.z
	var profundidade = (avatar.global_position - cam.global_position).dot(frente)
	if profundidade < 0.1:
		return _ADJUST_PIXELS_TO_WORLD_FALLBACK
	var extensao = 2.0 * profundidade * tan(deg_to_rad(cam.fov) * 0.5)
	if cam.keep_aspect == Camera3D.KEEP_WIDTH:
		return extensao / vp.x
	return extensao / vp.y

# Limite de Z (frente/trás): não deixa o avatar chegar perto demais da
# câmera — o plano "near" corta o modelo e aparece só o "miolo" gigante
# (foi o que aconteceu no print do v10). Deixa uma folga de 0.45 m além
# do plano near.
func _max_offset_z() -> float:
	var cam = get_viewport().get_camera_3d()
	if cam == null:
		return 0.1
	return cam.global_position.z - (cam.near + 0.45) - _vrm_anchor_pos_xz.y

# v11 — botão esquerdo arrastando = Deslocamento X/Y (1:1 com o mouse);
# roda = Escala; Shift + roda = Deslocamento Z; BOTÃO DIREITO = desfaz
# tudo desde que o modo foi ligado (botão de pânico).
func _handle_adjust_drag_input(event):
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			_adjust_dragging = true
			_adjust_drag_start_mouse = event.position
			_adjust_drag_start_offset = _vrm_manual_offset
			_adjust_px_to_world = _pixels_to_world()
		else:
			_adjust_dragging = false
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		_adjust_dragging = false
		_reposition_live(_adjust_backup_offset, _adjust_backup_scale)
	elif event is InputEventMouseMotion and _adjust_dragging:
		var delta = event.position - _adjust_drag_start_mouse
		var novo_offset = _adjust_drag_start_offset
		novo_offset.x += delta.x * _adjust_px_to_world
		novo_offset.y -= delta.y * _adjust_px_to_world   # tela Y cresce pra baixo, mundo Y cresce pra cima
		_reposition_live(novo_offset, _vrm_manual_scale_mult)
	elif event is InputEventMouseButton and event.pressed and (
			event.button_index == MOUSE_BUTTON_WHEEL_UP or event.button_index == MOUSE_BUTTON_WHEEL_DOWN):
		var subindo = event.button_index == MOUSE_BUTTON_WHEEL_UP
		if Input.is_key_pressed(KEY_SHIFT):
			var novo_z = _vrm_manual_offset.z + (_ADJUST_WHEEL_Z_STEP if subindo else -_ADJUST_WHEEL_Z_STEP)
			_reposition_live(Vector3(_vrm_manual_offset.x, _vrm_manual_offset.y, novo_z), _vrm_manual_scale_mult)
		else:
			var fator = _ADJUST_WHEEL_SCALE_FACTOR if subindo else 1.0 / _ADJUST_WHEEL_SCALE_FACTOR
			_reposition_live(_vrm_manual_offset, _vrm_manual_scale_mult * fator)

# NOVO v10 — CUIDADO (motivo de existir em vez de só chamar
# set_manual_vrm_adjust(), a função que os campos de número já usavam):
# set_manual_vrm_adjust() recarrega o arquivo VRM inteiro do disco
# (reload_vrm()) sempre que tem um VRM customizado carregado — ótimo pra
# UM clique em "Aplicar (ver ao vivo)", mas reabrir/reprocessar o
# arquivo INTEIRO a cada pixel de um arraste ia travar a janela (dezenas
# de eventos de mouse por segundo, cada um relendo o arquivo do zero).
# Esta função só move/reescala o nó que já está carregado — sem tocar
# em disco — e funciona igual pro avatar padrão e pra um VRM
# customizado, porque depois de qualquer troca (reload_vrm()) o nó
# ativo sempre se chama "Akira" na árvore (ver o final de reload_vrm()).
func _reposition_live(offset: Vector3, scale_mult: float):
	# v11 — limites de segurança: nada de jogar a Zenith pra fora do mundo
	# nem pra dentro da câmera.
	offset.x = clamp(offset.x, -2.0, 2.0)
	offset.y = clamp(offset.y, -2.0, 2.0)
	offset.z = clamp(offset.z, -3.0, _max_offset_z())
	scale_mult = clamp(scale_mult, 0.2, 5.0)
	_vrm_manual_offset = offset
	_vrm_manual_scale_mult = scale_mult
	var avatar = get_node_or_null("Akira")
	if not avatar or not _vrm_anchor_ready:
		return
	avatar.position.x = _vrm_anchor_pos_xz.x + offset.x
	avatar.position.y = offset.y
	avatar.position.z = _vrm_anchor_pos_xz.y + offset.z
	avatar.scale = Vector3.ONE * scale_mult

# ==========================================
# UTILITÁRIOS
# ==========================================
func _find_skeleton(node) -> Skeleton3D:
	for child in node.get_children():
		if child is Skeleton3D:
			return child
		var found = _find_skeleton(child)
		if found:
			return found
	return null

func _find_mesh(node) -> MeshInstance3D:
	for child in node.get_children():
		if child is MeshInstance3D:
			return child
		var found = _find_mesh(child)
		if found:
			return found
	return null

# CORREÇÃO (transparência): pra transparência afetar o corpo INTEIRO
# (rosto, cabelo, roupa, sapato...) em vez de só a primeira malha
# encontrada, precisa da lista completa — ver _update_transparency().
func _find_all_meshes(node) -> Array:
	var result: Array = []
	for child in node.get_children():
		if child is MeshInstance3D:
			result.append(child)
		result.append_array(_find_all_meshes(child))
	return result

# NOVO (Rodada 16, portado): procura recursivamente por qualquer
# BoneNodeConstraintApplier (addons/vrm/node_constraint/) dentro do avatar
# recém-carregado e esvazia as constraints dele. Não referencio a classe
# diretamente (evita depender do addon estar carregado numa ordem
# específica) — identifico pelo caminho do script, que é estável.
func _neutralize_vrm_node_constraints(node: Node):
	var achou = false
	for child in node.get_children():
		var script = child.get_script()
		if script and String(script.resource_path).ends_with("bone_node_constraint_applier.gd"):
			child.set("constraints", [])
			child.set_process(false)
			achou = true
		_neutralize_vrm_node_constraints(child)
	if achou:
		_debug_log("Constraint(s) VRMC_node_constraint encontrada(s) e esvaziada(s) — " +
			"evita que o motor reescreva a pose dos braços por baixo do nosso travamento.")

# ==========================================
# TROCA DE VRM EM TEMPO REAL
# ==========================================
# Usa GLTFDocument, que funciona em jogo rodando (não só no editor).
# HONESTIDADE: o addon VRM faz processamento extra na hora de importar
# (mapeamento de ossos humanoides, blend shapes, física de mola no
# cabelo) que este caminho simples não reproduz 100%. Pra maioria dos
# modelos VRM 1.0/0.x deve funcionar (esqueleto, malha, expressões
# básicas), mas cabelo com física de mola pode não se mover igual ao
# avatar original importado no editor.
# v18 — decisão do Anderson, depois de testar de todo jeito: VRM carregado "de
# fora" (GLTFDocument em tempo real) deforma cabelo/roupa tanto no editor quanto
# no .exe, e a causa raiz nunca foi achada (nem o bake do v16 resolveu). O que
# funciona é SEMPRE o avatar dentro de res://addons/avatars/, importado pelo
# próprio Godot — e o Python leva o .vrm até lá sozinho. Por isso o caminho de
# tempo real abaixo fica DESLIGADO. Só vire pra true pra experimentar/depurar.
const PERMITIR_VRM_EXTERNO := false

func reload_vrm(path: String) -> String:
	# AJUSTE (mensagem de erro específica): antes só retornava
	# true/false, e o Corpo (Godot) mostrava sempre a MESMA mensagem
	# genérica pra qualquer tipo de falha — arquivo não encontrado,
	# formato não suportado, VRM corrompido, tudo virava "confira se o
	# caminho está certo", o que não ajuda a diagnosticar. Agora
	# devolve "" (sucesso) ou uma frase específica do que deu errado —
	# aparece direto no chat, mesmo no .exe compilado sem console.
	_debug_log("reload_vrm() chamado com: " + path)
	# v12 — caminho "res://..." = avatar que o próprio GODOT já importou
	# (addons/avatars/*.vrm + o .vrm.import que o editor gera). Esse é o
	# caminho que renderiza certo; o carregamento em tempo real abaixo
	# (GLTFDocument) deforma cabelo/roupa em alguns modelos, como o Cypher.
	if path.begins_with("res://"):
		return _load_project_avatar(path)
	if not PERMITIR_VRM_EXTERNO:
		return ("esse avatar está fora do projeto (" + path.get_file() + ") e carregar assim deforma " +
			"cabelo/roupa. Em Configurações > Corpo / VRM, use \"Adicionar avatar...\" — eu importo " +
			"pra pasta do projeto pra você.")
	if not FileAccess.file_exists(path):
		_debug_log("arquivo não encontrado.")
		return "não encontrei esse arquivo no caminho informado."

	var doc = GLTFDocument.new()
	# CORREÇÃO (causa raiz do "se contorce" — inclusive recarregando a
	# MESMA Zenith): registra a extensão do addon VRM (a mesma que o EDITOR
	# usa pra importar um .vrm de verdade), que normaliza a orientação/eixo
	# dos ossos do padrão VRM pro padrão do Godot. Sem essa normalização, o
	# esqueleto carrega com uma pose de repouso (`get_bone_rest()`)
	# DIFERENTE da que o sistema de respiração/olhar/braço (em _process(),
	# mais abaixo) foi ajustado pra usar — daí cada frame ele aplica
	# rotação em cima da base errada, torcendo o corpo aos poucos. Só
	# precisa registrar uma vez.
	if _vrm_gltf_extension == null:
		var ext_script = load("res://addons/vrm/vrm_extension.gd")
		if ext_script:
			_vrm_gltf_extension = ext_script.new()
			GLTFDocument.register_gltf_document_extension(_vrm_gltf_extension)
			_debug_log("Extensão do addon VRM registrada no GLTFDocument.")
		else:
			_debug_log("AVISO: não consegui carregar addons/vrm/vrm_extension.gd — a " +
				"troca de VRM vai continuar sem a normalização de ossos do addon " +
				"(pode voltar a torcer o corpo).")
	var state = GLTFState.new()
	# CORREÇÃO (achado pelo Anderson comparando import pelo EDITOR vs
	# carregar em tempo real — "quando mudo direto no Godot dá certo"):
	# o addon tem um importador oficial (addons/vrm/import_vrm.gd, o que
	# o EDITOR usa quando gera o arquivo .vrm.import) que faz DUAS coisas
	# a mais do que este carregamento em tempo de execução vinha fazendo:
	# primeiro, passa flags = IMPORT_SCENE|IMPORT_ANIMATION|IMPORT_USE_NAMED_SKIN_BINDS
	#    (1|2|16 = 19) pro append_from_file() — sem isso, os binds de skin
	#    (que ligam cada vértice da malha ao osso certo) ficam por índice
	#    numérico em vez de por NOME, o que é frágil e é exatamente onde o
	#    erro batia ("Trying to assign value of type 'AnimationPlayer' to a
	#    variable of type 'ImporterMeshInstance3D'", achado pelo Anderson no
	#    depurador — indica os índices de nó saindo dessincronizados de
	#    malha pra animação). Uso o número direto (19), não a constante
	#    EditorSceneFormatImporter.IMPORT_USE_NAMED_SKIN_BINDS, porque essa
	#    classe é só do EDITOR — não existe no .exe exportado, ia dar erro
	#    tentando usar isso no jogo rodando de verdade.
	# segundo, define handle_binary_image ANTES de carregar — o import_vrm.gd
	#    comenta que o modo padrão (BASISU) "crashes on some files"; usa
	#    UNCOMPRESSED de propósito por segurança. Aplicando a mesma coisa
	#    aqui.
	state.handle_binary_image = GLTFState.HANDLE_BINARY_EMBED_AS_UNCOMPRESSED
	var flags_import := 1 | 2 | 16   # IMPORT_SCENE | IMPORT_ANIMATION | IMPORT_USE_NAMED_SKIN_BINDS
	var err = doc.append_from_file(path, state, flags_import)
	_debug_log("append_from_file() retornou código " + str(err))
	if err != OK:
		# Erros mais comuns do Godot ao ler um arquivo glTF/GLB (VRM é
		# um GLB por baixo): ERR_FILE_UNRECOGNIZED (arquivo não é um
		# glTF/GLB válido), ERR_FILE_CORRUPT (binário quebrado/truncado),
		# ERR_PARSE_ERROR (JSON interno malformado, comum em VRM 1.0
		# exportado por ferramentas mais novas que usam extensões que o
		# parser não reconhece direito ainda).
		var motivo = "código %d" % err
		if err == ERR_FILE_UNRECOGNIZED:
			motivo = "o arquivo não parece ser um VRM/glTF válido (ou está muito corrompido)"
		elif err == ERR_FILE_CORRUPT or err == ERR_PARSE_ERROR:
			motivo = ("o arquivo parece corrompido ou usa uma versão/recurso do formato VRM " +
				"que essa versão do Godot ainda não lê direito — costuma acontecer com VRM " +
				"1.0 exportado por ferramentas bem recentes; se puder, tente re-exportar " +
				"como VRM 0.x, que tem suporte mais maduro")
		return "falha ao ler o arquivo (" + motivo + ")."

	var new_avatar = doc.generate_scene(state)
	_debug_log("generate_scene() retornou: " + ("um nó válido" if new_avatar else "null"))
	if not new_avatar:
		return "o arquivo carregou, mas não consegui montar um modelo 3D válido a partir dele."

	# v16 — HIPÓTESE FORTE pro cabelo/roupa esticado ao carregar "de fora"
	# (não testada rodando — ver comentário grande em _bake_importer_meshes).
	# generate_scene() devolve as malhas como ImporterMeshInstance3D, o
	# formato de PRÉ-importação do Godot — o EDITOR sempre converte isso
	# pro formato final antes de salvar o .scn, e esse passo nunca
	# acontecia aqui. Essa é a única diferença real que sobrou depois de
	# já ter igualado flags, handle_binary_image e as extensões VRM
	# (essas o vrm_runtime_bootstrap.gd já registra desde antes do v9).
	_bake_importer_meshes(new_avatar)

	return _install_avatar(new_avatar, path)


# v16 — converte ImporterMeshInstance3D (o formato "de pré-importação",
# que é o que generate_scene() sempre devolve) em MeshInstance3D de
# verdade (o formato final que o EDITOR grava no .scn depois de
# importar). A documentação oficial do ImporterMesh é explícita sobre
# essa distinção: "Ao contrário do seu equivalente em tempo de execução,
# ImporterMesh contém os dados da malha ANTES de passos de importação —
# como geração de LOD e malha de sombra — acontecerem" (tradução livre).
# ImporterMesh.get_mesh() é a função pública (funciona fora do editor)
# que faz exatamente essa conversão — é o mesmo bake que o importador
# faz, só que chamado por nós em vez de pelo Godot. Só troca o tipo do
# nó; os dados (vértices, peso de osso, blend shape) são os mesmos.
# Não deveria piorar nada mesmo se a hipótese estiver errada — é só
# reempacotar o mesmo dado num formato diferente.
func _bake_importer_meshes(node: Node) -> void:
	for child in node.get_children():
		if child is ImporterMeshInstance3D:
			var origem: ImporterMeshInstance3D = child
			var novo := MeshInstance3D.new()
			novo.name = origem.name
			novo.transform = origem.transform
			novo.visible = origem.visible
			novo.cast_shadow = origem.cast_shadow
			novo.layer_mask = origem.layer_mask
			novo.skeleton_path = origem.skeleton_path
			if origem.skin:
				novo.skin = origem.skin
			if origem.mesh:
				novo.mesh = origem.mesh.get_mesh()
			var indice := origem.get_index()
			for neto in origem.get_children():
				origem.remove_child(neto)
				novo.add_child(neto)
			node.remove_child(origem)
			node.add_child(novo)
			node.move_child(novo, indice)
			origem.queue_free()
			_bake_importer_meshes(novo)   # caso tenha filho (raro numa malha), continua descendo
		else:
			_bake_importer_meshes(child)


# v12 — a parte de "colocar o avatar novo na cena" (âncora, escala/
# deslocamento manual, remover o antigo, achar esqueleto/ossos) saiu de
# dentro do reload_vrm() pra ser compartilhada: tanto o carregamento em
# tempo real (GLTFDocument) quanto o avatar já importado pelo Godot
# (_load_project_avatar) terminam aqui, do mesmo jeito de sempre.
# `new_avatar` fica sem tipo de propósito (igual era antes, quando vinha
# direto de generate_scene()).
func _install_avatar(new_avatar, path: String) -> String:
	# CORREÇÃO ("tela fica vazia e o modelo some"): a versão anterior
	# removia o avatar ANTIGO antes de garantir que o NOVO estava
	# pronto pra entrar na cena — se algo desse errado bem nessa hora
	# (arquivo grande/complexo, algo no encaixe automático de escala),
	# a janela ficava sem avatar NENHUM. Agora o antigo só é removido
	# depois que o novo já está confirmado, montado e medido — nunca
	# mais fica em branco: se algo falhar lá na frente, o avatar
	# ANTERIOR ainda está lá.
	var old_avatar = get_node_or_null("Akira")
	# CORREÇÃO ("ponto fixo"): antes, cada troca copiava posição/altura
	# de quem estivesse carregado NAQUELE momento — trocar de VRM várias
	# vezes seguidas podia ir acumulando deriva. Agora usa SEMPRE a
	# mesma âncora fixa (calculada uma vez, na primeira execução do
	# programa, e salva em disco), então qualquer VRM cai exatamente no
	# mesmo lugar "oficial", não importa quantas trocas já rolaram —
	# inclusive a posição X/Z que a câmera espera (sem isso, o modelo
	# novo nasce no (0,0,0) local, que pode cair fora do enquadramento
	# da câmera e o avatar simplesmente some, mesmo a troca "dando
	# certo" tecnicamente).
	if not _vrm_anchor_ready:
		_load_or_capture_anchor(old_avatar)
	var old_pos_xz := _vrm_anchor_pos_xz
	var old_rotation_y := _vrm_anchor_rot_y
	_debug_log("usando âncora fixa — pos XZ: %s | rotY: %.3f | ajuste manual: offset=%s escala=%.3f" % [
		old_pos_xz, old_rotation_y, _vrm_manual_offset, _vrm_manual_scale_mult])

	# SIMPLIFICADO (round "bruto primeiro" — ver comentário no topo do
	# arquivo, na declaração das variáveis de âncora): SEM mais cálculo
	# de AABB/altura pra decidir escala, e SEM "encostar os pés"
	# recalculando caixa depois de escalar. Cada VRM entra na escala
	# NATIVA do arquivo (1.0) vezes só o multiplicador manual — e a
	# origem do arquivo é usada como está (o formato VRM já garante,
	# por especificação, que a origem fica no chão entre os pés; exports
	# que não seguem isso precisam do ajuste fino manual mesmo, e é pra
	# isso que ele existe).
	new_avatar.name = "AkiraNovo_temp"
	add_child(new_avatar)
	new_avatar.position.x = old_pos_xz.x + _vrm_manual_offset.x
	new_avatar.position.y = _vrm_manual_offset.y
	new_avatar.position.z = old_pos_xz.y + _vrm_manual_offset.z
	new_avatar.rotation.y = old_rotation_y
	var fator = _vrm_manual_scale_mult if _vrm_manual_scale_mult > 0.01 else 1.0
	new_avatar.scale = Vector3.ONE * fator
	_debug_log("escala aplicada (só o multiplicador manual — sem encaixe automático): %.4f" % fator)

	# Só AGORA remove o antigo — o novo já está confirmado na árvore.
	if old_avatar:
		remove_child(old_avatar)
		old_avatar.queue_free()
	new_avatar.name = "Akira"
	_current_vrm_path = path

	# MITIGAÇÃO (braços travados em "T-pose"): registrar a extensão do
	# addon VRM corrige a deformação geral do corpo, mas ela também pode
	# criar um nó "secondary" — física de mola pra cabelo/roupa
	# (VRMC_springBone) — que roda sozinho a cada frame e pode brigar com
	# o travamento dos braços (_force_arms_down). Como essa física extra
	# não é usada em mais nada no Zenith, é mais seguro remover esse nó.
	var secondary_node = new_avatar.get_node_or_null("secondary")
	if secondary_node:
		secondary_node.queue_free()
		_debug_log("Nó 'secondary' (física de mola do addon VRM) removido por segurança.")

	# MITIGAÇÃO (braços ainda travando em T-pose): VRMs que usam o recurso
	# VRMC_node_constraint (comum em exports VRM 1.0 mais novos) trazem um
	# BoneNodeConstraintApplier que registra um SkeletonModifier3D interno
	# no esqueleto — esse modifier roda DEPOIS do _process() de qualquer
	# script (inclusive o nosso, que reforça o braço todo frame), sempre
	# por último. Mesmo travando o braço a cada frame, se o VRM tiver uma
	# constraint mirando o ombro/braço, ela reescreve por cima logo depois,
	# sem gerar nenhum erro. Como o Zenith não usa esse recurso pra nada,
	# é seguro esvaziar as constraints desse nó.
	_neutralize_vrm_node_constraints(new_avatar)

	# Precisa re-detectar esqueleto/malha/ossos — é um modelo novo.
	skeleton = _find_skeleton(new_avatar)
	mesh_instance = _find_mesh(new_avatar)
	all_mesh_instances = _find_all_meshes(new_avatar)
	_debug_log("skeleton encontrado: " + str(skeleton != null) + " | mesh encontrada: " + str(mesh_instance != null))
	if skeleton:
		neck_id = _find_bone_fuzzy(["Neck"], ["j_bip_c_neck"])
		chest_id = _find_bone_fuzzy(["Chest", "UpperChest"], ["j_bip_c_chest", "j_bip_c_upperchest"])
		head_id = _find_bone_fuzzy(["Head"], ["j_bip_c_head"])
		left_arm_id = _find_bone_fuzzy(["LeftUpperArm"], ["j_bip_l_upperarm"])
		right_arm_id = _find_bone_fuzzy(["RightUpperArm"], ["j_bip_r_upperarm"])
		hips_id = _find_bone_fuzzy(["Hips"], ["j_bip_c_hips"])
		# LOG (pra nunca mais precisar adivinhar isso de novo): mostra
		# exatamente se cada osso-chave foi encontrado neste arquivo.
		_debug_log("ossos resolvidos — braço esq: %s | braço dir: %s | pescoço: %s | peito: %s | cabeça: %s | quadril: %s" % [
			str(left_arm_id), str(right_arm_id), str(neck_id), str(chest_id), str(head_id), str(hips_id)])
		_disable_autoplay_animation()
		_force_arms_down()
		_vida_setup()
	else:
		# O modelo aparece (é isso que importa pro "funcionou"), só que
		# sem esqueleto humanoide reconhecido a respiração/olhar/gestos
		# não têm o que animar — avisa no console pra não parecer bug
		# escondido.
		_debug_log("Aviso: não encontrei um esqueleto humanoide reconhecível nesse VRM. " +
			"O modelo aparece, mas respiração/olhar/gestos automáticos não vão se mexer.")

	print("[Zenith/Corpo] VRM trocado: " + path + " (escala %.2fx, sem encaixe automático)" % fator)
	if not skeleton:
		return ("carregou e apareceu, mas não achei um esqueleto humanoide reconhecível " +
			"nesse arquivo — respiração/olhar/gestos automáticos não vão se mexer, só o " +
			"visual estático.")
	return ""

# ==========================================
# VIDA DO AVATAR (v20) — ligação com akira_vida.gd
# ==========================================
func _vida_setup():
	if vida == null and not _vida_falhou:
		var script = load(VIDA_PATH)
		if script == null or not script.can_instantiate():
			_vida_falhou = true
			push_warning("[Zenith] akira_vida.gd não carregou — o avatar segue só com a base (respiração/cabeça).")
			return
		vida = script.new()
	if vida == null:
		return
	vida.nivel = _vida_cfg_nivel
	vida.bracos_naturais = _vida_cfg_bracos
	vida.olhar_mouse = _vida_cfg_mouse
	var raiz: Node = self
	var avatar_atual = get_node_or_null("Akira")     # todo avatar, ao entrar, é renomeado "Akira"
	if avatar_atual != null:
		raiz = avatar_atual
	_vida_ultimo_relatorio = vida.setup(self, skeleton, raiz, all_mesh_instances)
	_debug_log("vida: " + _vida_ultimo_relatorio.replace("\n", " | "))

func _vida_cuida_do_rosto() -> bool:
	return vida != null and vida.nivel != "desligado" and vida.has_expressions()

func _vida_state_int() -> int:
	match life_state:
		LifeState.THINKING: return 1
		LifeState.SPEAKING: return 2
		LifeState.GREETING: return 3
		_: return 0

func _vida_update(delta: float):
	if vida == null:
		return
	vida.update(delta, _vida_state_int())

# Chamado pelas Configurações (e a cada settings_data): nível, braços naturais, olhar o mouse.
func vida_apply_config(nivel: String, bracos: bool, mouse: bool):
	var n = nivel.to_lower().strip_edges()
	if not (n in ["desligado", "suave", "expressivo"]):
		n = "suave"
	_vida_cfg_nivel = n
	_vida_cfg_bracos = bracos
	_vida_cfg_mouse = mouse
	if vida != null:
		var mudou_nivel = (vida.nivel != n)
		vida.nivel = n
		vida.bracos_naturais = bracos
		vida.olhar_mouse = mouse
		if mudou_nivel and n == "desligado":
			vida.reset_pose_to_rest()

func vida_play_gesture(nome: String) -> bool:
	if vida == null:
		return false
	return vida.play_gesture(nome)

func vida_gesture_names() -> Array:
	if vida == null:
		return []
	return vida.gesture_names()

func vida_report() -> String:
	if vida == null:
		return "Motor de vida não iniciado."
	return vida.describe()

# Deslocamento vertical (pulinho) somado à posição do corpo.
func vida_bounce_offset() -> float:
	if vida == null:
		return 0.0
	return vida.get_bounce_offset()

# ==========================================
# AVATARES DO PROJETO (importados pelo Godot) — v12
# ==========================================
# Pedido/achado do Anderson: "se eu coloco o VRM direto no Godot dá
# certo". O .vrm que fica em res://addons/avatars/ passa pelo IMPORTADOR
# do editor (gera o .vrm.import + uma cena pronta em .godot/imported/),
# que é exatamente como a Zenith padrão já funciona. Aqui a gente só
# INSTANCIA essa cena pronta — nada de reler/reconstruir o arquivo em
# tempo real. Preço: o VRM tem que estar dentro do projeto e o Godot
# precisa ter importado (abrir o projeto no editor faz isso sozinho) e
# reexportado o .pck pra ir junto no executável.
const PROJECT_AVATAR_DIR := "res://addons/avatars"

# Lista os avatares que o Godot importou: [{"nome": "Cypher", "path":
# "res://addons/avatars/Cypher.vrm"}, ...]. Num jogo exportado o .vrm
# original não vai junto (só a versão importada), então a listagem
# enxerga "X.vrm.import"/"X.vrm.remap" também e tira o sufixo — e a
# checagem de existência é ResourceLoader.exists(), não FileAccess.
func list_project_avatars() -> Array:
	var resultado: Array = []
	var vistos := {}
	var dir = DirAccess.open(PROJECT_AVATAR_DIR)
	if dir == null:
		return resultado
	for f in dir.get_files():
		var nome: String = f
		if nome.ends_with(".import"):
			nome = nome.trim_suffix(".import")
		elif nome.ends_with(".remap"):
			nome = nome.trim_suffix(".remap")
		if nome.get_extension().to_lower() != "vrm" or vistos.has(nome):
			continue
		var caminho = PROJECT_AVATAR_DIR + "/" + nome
		if ResourceLoader.exists(caminho):
			vistos[nome] = true
			resultado.append({"nome": nome.get_basename(), "path": caminho})
	resultado.sort_custom(func(a, b): return String(a["nome"]).naturalnocasecmp_to(String(b["nome"])) < 0)
	return resultado

func _load_project_avatar(path: String) -> String:
	if not ResourceLoader.exists(path):
		_debug_log("avatar do projeto NÃO encontrado: " + path)
		return ("não encontrei esse avatar dentro do projeto (" + path + "). Ele precisa estar em " +
			"res://addons/avatars/ e ter sido importado pelo Godot (abra o projeto no editor " +
			"uma vez e reexporte).")
	# v13 — se o pré-carregamento já verificou e guardou essa cena, usa
	# ela (troca instantânea); senão carrega na hora, como no v12.
	var recurso = _avatar_cache.get(path, null)
	if recurso == null:
		recurso = load(path)
	if not (recurso is PackedScene):
		_debug_log("avatar do projeto não é PackedScene: " + path)
		return "o Godot não importou esse arquivo como uma cena 3D (confira o .vrm.import ao lado dele)."
	var instancia = (recurso as PackedScene).instantiate()
	if instancia == null:
		return "o avatar foi importado, mas não consegui criar uma instância dele."
	_debug_log("avatar do projeto instanciado (importado pelo editor): " + path)
	return _install_avatar(instancia, path)


# ==========================================
# PRÉ-CARREGAMENTO E VERIFICAÇÃO DOS AVATARES (v13)
# ==========================================
# Pedido do Anderson: "sempre rever que está carregado bonitinho" e "uma
# tela de download". Ao abrir o Zenith (e sempre que entra avatar novo)
# cada avatar de res://addons/avatars/ é carregado em segundo plano
# (ResourceLoader threaded → dá pra mostrar progresso de verdade), passa
# por uma checagem de saúde (tem esqueleto? tem malha? quantos ossos?) e
# fica guardado em cache — trocar de avatar depois é instantâneo e a lista
# mostra ✓/⚠ de cada um. Quem desenha a tela de progresso é o
# ui_manager.gd, perguntando aqui por poll_avatar_preload().
var _avatar_cache: Dictionary = {}     # path -> PackedScene já verificada
var _avatar_status: Dictionary = {}    # path -> {"ok": bool, "info": String}
var _preload_fila: Array = []
var _preload_atual: String = ""
var _preload_total: int = 0
var _preload_feitos: int = 0
var _preload_replace: bool = false

# Monta a fila. forcar=true joga fora o resultado anterior e reverifica tudo
# (botão "Verificar de novo"). Devolve quantos avatares vão ser checados.
func start_avatar_preload(forcar: bool = false) -> int:
	_preload_fila.clear()
	_preload_atual = ""
	_preload_replace = forcar
	for a in list_project_avatars():
		var p: String = String(a["path"])
		if forcar:
			_avatar_cache.erase(p)
			_avatar_status.erase(p)
		if not _avatar_status.has(p):
			_preload_fila.append(p)
	_preload_total = _preload_fila.size()
	_preload_feitos = 0
	return _preload_total

# Chamado todo frame pela UI enquanto a tela de carregamento está aberta.
# Trabalha em UM avatar por vez. Devolve o andamento.
func poll_avatar_preload() -> Dictionary:
	var frac_atual := 0.0
	if _preload_atual == "" and not _preload_fila.is_empty():
		_preload_atual = String(_preload_fila.pop_front())
		var modo = ResourceLoader.CACHE_MODE_REPLACE if _preload_replace else ResourceLoader.CACHE_MODE_REUSE
		var err = ResourceLoader.load_threaded_request(_preload_atual, "", false, modo)
		if err != OK:
			_marcar_avatar(_preload_atual, false, "não consegui iniciar o carregamento (erro %d)" % err)
			_preload_atual = ""
			_preload_feitos += 1
	elif _preload_atual != "":
		var progresso: Array = []
		var st = ResourceLoader.load_threaded_get_status(_preload_atual, progresso)
		if progresso.size() > 0:
			frac_atual = float(progresso[0])
		if st == ResourceLoader.THREAD_LOAD_LOADED:
			_verificar_avatar(_preload_atual, ResourceLoader.load_threaded_get(_preload_atual))
			_preload_atual = ""
			_preload_feitos += 1
			frac_atual = 0.0
		elif st == ResourceLoader.THREAD_LOAD_FAILED or st == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
			_marcar_avatar(_preload_atual, false, "o Godot não conseguiu carregar (importação incompleta ou falhou)")
			_preload_atual = ""
			_preload_feitos += 1
			frac_atual = 0.0
	var ativo: bool = _preload_atual != "" or not _preload_fila.is_empty()
	var fracao := 1.0
	if _preload_total > 0:
		fracao = clamp((float(_preload_feitos) + frac_atual) / float(_preload_total), 0.0, 1.0)
	var nome_atual := ""
	if _preload_atual != "":
		nome_atual = _preload_atual.get_file().get_basename()
	elif not _preload_fila.is_empty():
		nome_atual = String(_preload_fila[0]).get_file().get_basename()
	return {"ativo": ativo, "feitos": _preload_feitos, "total": _preload_total,
		"atual": nome_atual, "fracao": fracao}

func _marcar_avatar(path: String, ok: bool, info: String):
	_avatar_status[path] = {"ok": ok, "info": info}
	_debug_log("avatar %s → %s (%s)" % [path, "OK" if ok else "FALHOU", info])

# Checagem de saúde: instancia a cena fora da árvore (não aparece na
# tela), confere esqueleto e malha, conta ossos e descarta.
func _verificar_avatar(path: String, recurso):
	if not (recurso is PackedScene):
		_marcar_avatar(path, false, "não foi importado como cena 3D")
		return
	var inst = (recurso as PackedScene).instantiate()
	if inst == null:
		_marcar_avatar(path, false, "não consegui instanciar")
		return
	var esqueletos = inst.find_children("*", "Skeleton3D", true, false)
	var malhas = inst.find_children("*", "MeshInstance3D", true, false)
	var ossos := 0
	if not esqueletos.is_empty():
		ossos = (esqueletos[0] as Skeleton3D).get_bone_count()
	var n_malhas: int = malhas.size()
	inst.free()
	if esqueletos.is_empty() or n_malhas == 0:
		_marcar_avatar(path, false, "sem esqueleto ou sem malha (importação estranha)")
		return
	_avatar_cache[path] = recurso
	_marcar_avatar(path, true, "%d ossos · %d malhas" % [ossos, n_malhas])

func get_avatar_status(path: String) -> Dictionary:
	return _avatar_status.get(path, {})

# ==========================================
# ADICIONAR AVATAR NOVO AO PROJETO (v13)
# ==========================================
# Só dá pra copiar pra dentro de res://addons/avatars/ rodando pelo EDITOR
# do Godot (F5) — num .exe exportado o res:// é somente leitura e o Godot
# não sabe importar arquivo novo. Depois da cópia, o EDITOR importa sozinho
# quando a janela dele ganha foco; a UI espera aparecer o resultado da
# importação (is_avatar_import_ready) e aí pré-carrega/verifica.
func add_avatar_to_project(origem: String) -> Dictionary:
	if not OS.has_feature("editor"):
		return {"ok": false, "msg": "este caminho (copiar direto pra res://) só existe rodando pelo editor do " +
			"Godot (F5). No .exe, o Cérebro (Python) faz a importação — use \"Adicionar avatar...\" nas Configurações."}
	if origem.get_extension().to_lower() != "vrm":
		return {"ok": false, "msg": "isso não é um arquivo .vrm."}
	var pasta: String = ProjectSettings.globalize_path(PROJECT_AVATAR_DIR)
	if not DirAccess.dir_exists_absolute(pasta):
		return {"ok": false, "msg": "não achei a pasta " + PROJECT_AVATAR_DIR + " do projeto."}
	var nome: String = origem.get_file()
	var destino: String = pasta.path_join(nome)
	if origem.replace("\\", "/").to_lower() == destino.replace("\\", "/").to_lower():
		return {"ok": true, "msg": "", "path": PROJECT_AVATAR_DIR + "/" + nome}   # já está lá
	var n := 2
	while FileAccess.file_exists(destino):
		nome = origem.get_file().get_basename() + "_" + str(n) + ".vrm"
		destino = pasta.path_join(nome)
		n += 1
	var err = DirAccess.copy_absolute(origem, destino)
	if err != OK:
		return {"ok": false, "msg": "não consegui copiar o arquivo pra pasta do projeto (erro %d)." % err}
	_debug_log("avatar copiado pro projeto: " + destino)
	return {"ok": true, "msg": "", "path": PROJECT_AVATAR_DIR + "/" + nome}

# A importação do editor terminou de verdade? Não basta existir o
# ".vrm.import" (ele nasce antes da cena pronta): confere se o arquivo
# importado que ele aponta já está no disco.
func is_avatar_import_ready(path: String) -> bool:
	var cfg := ConfigFile.new()
	if cfg.load(path + ".import") != OK:
		return false
	var destino: String = String(cfg.get_value("remap", "path", ""))
	return destino != "" and FileAccess.file_exists(destino)

# FIM (_compute_visual_aabb foi removida nesta rodada — não sobrou
# nenhuma chamada pra ela: era usada só pelo encaixe automático de
# escala e pela região de clique, os dois removidos/simplificados
# nesta rodada. Se precisar de novo no futuro, está no histórico do
# Zenith_v6/v5 — akira_body.gd, função _compute_visual_aabb).


# ====================================================================================================
# v23 — FUNDO DA JANELA DO AVATAR  (transparente · sólido · chroma · auto)
#
# Em alguns computadores (certos drivers de vídeo, notebooks mais antigos, Windows sem composição) a janela
# "transparente" não é transparente: aparece um quadrado PRETO atrás da Zenith. A transparência é um pedido que
# a janela faz ao Windows — o programa não tem como forçar. Então:
#   • "transparente": como sempre (o padrão onde funciona);
#   • "solido":       a janela NÃO é transparente; o fundo é uma cor (padrão azul-marinho do tema) — funciona
#                     em QUALQUER máquina;
#   • "chroma":       fundo VERDE puro, pra recortar no OBS (Filtro > Chroma Key) em lives;
#   • "auto":         transparente, a menos que o Godot diga que este sistema não suporta.
# A escolha fica em user://zenith_avatar_fundo.cfg (vale já no primeiro quadro da próxima abertura) e o Cérebro
# também a guarda em settings (/fundo_avatar).
# ====================================================================================================
const FUNDO_CFG := "user://zenith_avatar_fundo.cfg"
var fundo_modo: String = "auto"
var fundo_cor: Color = Color(0.043, 0.063, 0.125, 1.0)
var fundo_transparente_efetivo: bool = true

func _fundo_carregar_local():
	var cfg := ConfigFile.new()
	if cfg.load(FUNDO_CFG) == OK:
		fundo_modo = str(cfg.get_value("fundo", "modo", "auto"))
		fundo_cor = Color.from_string(str(cfg.get_value("fundo", "cor", "#0b1020")), fundo_cor)
	_fundo_aplicar()

func _fundo_salvar_local():
	var cfg := ConfigFile.new()
	cfg.set_value("fundo", "modo", fundo_modo)
	cfg.set_value("fundo", "cor", "#" + fundo_cor.to_html(false))
	cfg.save(FUNDO_CFG)

func _on_avatar_fundo(modo: String, cor: String):
	if not (modo in ["auto", "transparente", "solido", "chroma"]):
		modo = "auto"
	var mudou = (modo != fundo_modo) or (Color.from_string(cor, fundo_cor) != fundo_cor)
	fundo_modo = modo
	fundo_cor = Color.from_string(cor, fundo_cor)
	if mudou:
		_fundo_salvar_local()
		_fundo_aplicar()

func _fundo_sistema_suporta_transparencia() -> bool:
	if DisplayServer.has_method("is_window_transparency_available"):
		return DisplayServer.is_window_transparency_available()
	return true

func _fundo_aplicar():
	var transp := true
	match fundo_modo:
		"solido", "chroma":
			transp = false
		"transparente":
			transp = true
		_:
			transp = _fundo_sistema_suporta_transparencia()
	fundo_transparente_efetivo = transp
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_TRANSPARENT, transp)
	get_viewport().transparent_bg = transp
	var cor_fundo: Color = Color(0.0, 1.0, 0.0, 1.0) if fundo_modo == "chroma" else fundo_cor
	RenderingServer.set_default_clear_color(Color(0, 0, 0, 0) if transp else cor_fundo)
	var we = get_node_or_null("WorldEnvironment")
	if we and we.environment:
		var env: Environment = we.environment.duplicate() as Environment
		if transp:
			env.background_mode = Environment.BG_CANVAS
		else:
			env.background_mode = Environment.BG_COLOR
			env.background_color = cor_fundo
		we.environment = env


# v23 — indicador de observação ao vivo na janela do avatar (a janela é "clique-atravessa": é só visual; o botão
# de PARAR fica na Central de Controle, e /parar_observacao e /pausar também valem).
var _obs_layer: CanvasLayer = null

func _on_observando(ativo: bool, tipo: String, _info: String):
	if _obs_layer and is_instance_valid(_obs_layer):
		_obs_layer.queue_free()
		_obs_layer = null
	if not ativo:
		return
	_obs_layer = CanvasLayer.new()
	_obs_layer.layer = 100
	var lbl := Label.new()
	lbl.text = "● OBSERVANDO " + ("A TELA" if tipo == "screen" else "A CÂMERA")
	lbl.add_theme_color_override("font_color", Color(1.0, 0.2, 0.2))
	lbl.add_theme_color_override("font_outline_color", Color(0, 0, 0, 1))
	lbl.add_theme_constant_override("outline_size", 6)
	lbl.add_theme_font_size_override("font_size", 16)
	lbl.position = Vector2(10, 8)
	_obs_layer.add_child(lbl)
	add_child(_obs_layer)


# ====================================================================================================
# v24 — DISPLAY TFT: o rosto da Zenith num mini-display (ESP32-S3 por USB)
#
# O Cérebro (Python) avisa por `tft_config` quando uma placa está plugada. Aí este código renderiza o ROSTO num
# SubViewport pequeno (câmera enquadrada na cabeça, fundo sólido), ~10 quadros/s, e manda cada quadro em JPEG
# (base64) de volta ao Cérebro (`tft_frame`), que repassa pela USB. Placa desplugada = `ativo=false` = tudo pára
# (nenhum custo de GPU). É o MESMO avatar da tela: boca, piscar e expressões aparecem sozinhos.
#
# Enquadramento: segue o osso da cabeça (head_id) e olha de frente (mesma direção da câmera principal).
# Se o rosto ficar pequeno/grande, ajuste `/tft zoom 1.3`. Se o avatar não tiver osso "Head", usa o centro do corpo.
# ====================================================================================================
var _tft_vp: SubViewport = null
var _tft_cam: Camera3D = null
var _tft_timer: Timer = null
var _tft_ativo: bool = false
var _tft_ocupado: bool = false
var _tft_w: int = 240
var _tft_h: int = 240
var _tft_qualidade: float = 0.7
var _tft_zoom: float = 1.0
var _tft_enquadre: String = "rosto"   # v25: rosto (cabeça e ombros) · busto (peito pra cima) · corpo (inteira)
var _tft_cor: Color = Color(0.043, 0.063, 0.125, 1.0)
const _TFT_ALTURA_ENQUADRE_M := 0.42      # altura (em metros do avatar) que o quadro mostra: rosto + ombros
const _TFT_FOV := 28.0

func _on_tft_config(ativo: bool, w: int, h: int, fps: float, qualidade: float, zoom: float, cor: String, enquadre: String = "rosto"):
	_tft_enquadre = enquadre if enquadre in ["rosto", "busto", "corpo"] else "rosto"
	_tft_w = clampi(w, 64, 480)
	_tft_h = clampi(h, 64, 480)
	_tft_qualidade = clampf(qualidade, 0.3, 0.95)
	_tft_zoom = clampf(zoom, 0.3, 3.0)
	_tft_cor = Color.from_string(cor, _tft_cor)
	if not ativo:
		_tft_parar()
		return
	_tft_iniciar(clampf(fps, 1.0, 30.0))

func _tft_iniciar(fps: float):
	if _tft_vp == null or not is_instance_valid(_tft_vp):
		_tft_vp = SubViewport.new()
		_tft_vp.transparent_bg = false
		_tft_vp.disable_3d = false
		_tft_vp.gui_disable_input = true
		_tft_vp.handle_input_locally = false
		_tft_vp.msaa_3d = Viewport.MSAA_2X
		_tft_vp.render_target_update_mode = SubViewport.UPDATE_DISABLED
		add_child(_tft_vp)
		_tft_cam = Camera3D.new()
		_tft_cam.fov = _TFT_FOV
		_tft_cam.near = 0.05
		_tft_cam.far = 20.0
		_tft_vp.add_child(_tft_cam)
		_tft_cam.current = true
	_tft_vp.size = Vector2i(_tft_w, _tft_h)
	# Ambiente = o da cena (mesma luz/ambiente do avatar), só que com FUNDO SÓLIDO
	var env: Environment = null
	var we = get_node_or_null("WorldEnvironment")
	if we and we.environment:
		env = we.environment.duplicate() as Environment
	else:
		env = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = _tft_cor
	_tft_cam.environment = env
	if _tft_timer == null or not is_instance_valid(_tft_timer):
		_tft_timer = Timer.new()
		_tft_timer.one_shot = false
		_tft_timer.timeout.connect(_tft_tick)
		add_child(_tft_timer)
	_tft_timer.wait_time = 1.0 / fps
	_tft_timer.start()
	_tft_ativo = true

func _tft_parar():
	_tft_ativo = false
	if _tft_timer and is_instance_valid(_tft_timer):
		_tft_timer.stop()
	if _tft_vp and is_instance_valid(_tft_vp):
		_tft_vp.render_target_update_mode = SubViewport.UPDATE_DISABLED

func _tft_posicionar_camera():
	var main_cam = get_viewport().get_camera_3d()
	var alvo := Vector3.ZERO
	var escala := 1.0
	var altura_m := _TFT_ALTURA_ENQUADRE_M          # rosto
	if skeleton != null and head_id >= 0:
		escala = maxf(0.1, skeleton.global_transform.basis.get_scale().y)
		var cabeca: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(head_id).origin
		match _tft_enquadre:
			"corpo":
				altura_m = 1.95
				if hips_id >= 0:
					var quadril: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(hips_id).origin
					alvo = (cabeca + quadril) * 0.5 - Vector3.UP * 0.12 * escala
				else:
					alvo = cabeca - Vector3.UP * 0.7 * escala
			"busto":
				altura_m = 0.9
				alvo = cabeca - Vector3.UP * 0.12 * escala
			_:
				alvo = cabeca + Vector3.UP * 0.07 * escala    # o osso da cabeça fica na base do crânio: sobe até o meio do rosto
	else:
		var av = get_node_or_null("Akira")
		if av is Node3D:
			alvo = (av as Node3D).global_position + Vector3.UP * (1.45 if _tft_enquadre == "rosto" else 1.0)
			altura_m = 0.42 if _tft_enquadre == "rosto" else (0.9 if _tft_enquadre == "busto" else 1.95)
	var de_frente := Vector3.BACK                  # sem câmera principal: assume o avatar olhando pra +Z
	if main_cam != null:
		de_frente = main_cam.global_transform.basis.z.normalized()    # da cena em direção à câmera
		de_frente.y = 0.0                                              # sempre na altura do rosto, sem olhar de cima/baixo
		if de_frente.length() < 0.01:
			de_frente = Vector3.BACK
		de_frente = de_frente.normalized()
	var altura := altura_m * escala / _tft_zoom
	var dist := (altura * 0.5) / tan(deg_to_rad(_TFT_FOV * 0.5))
	_tft_cam.look_at_from_position(alvo + de_frente * dist, alvo - Vector3.UP * 0.02 * escala, Vector3.UP)

func _tft_tick():
	if not _tft_ativo or _tft_ocupado or _tft_vp == null or not is_instance_valid(_tft_vp):
		return
	var connector = get_node_or_null("BrainConnector")
	if connector == null:
		return
	var ws = connector.get("websocket")
	if ws == null or ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		_tft_parar()                                    # Cérebro offline: pára (o Cérebro manda de novo ao reconectar)
		return
	_tft_ocupado = true
	_tft_posicionar_camera()
	_tft_vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	if _tft_ativo and _tft_vp and is_instance_valid(_tft_vp):
		var img: Image = _tft_vp.get_texture().get_image()
		if img != null and not img.is_empty():
			img.convert(Image.FORMAT_RGB8)
			var bytes: PackedByteArray = img.save_jpg_to_buffer(_tft_qualidade)
			connector.send_to_brain({"action": "tft_frame", "w": img.get_width(), "h": img.get_height(),
				"jpg": Marshalls.raw_to_base64(bytes)})
	_tft_ocupado = false


# ======================================================================
#  v1.6 — MOVIMENTOS: pulo (de verdade), dança, caretas, câmera, passeio da janela.
#  Os dados vêm do Cérebro (brain/zenith_movimentos.py); o intérprete é o zenith_movimentos.gd (carregado com load()).
#  Corpo/câmera/janela são aplicados aqui; braços, cabeça, rosto e mãos, no akira_vida.gd (vida.mov_set).
#  NÃO TESTADO NO GODOT. Desligar tudo: Configurações > movimentos_ativos (ou apague zenith_movimentos.gd).
# ======================================================================
const MOV_PATH := "res://zenith_movimentos.gd"
var _mov = null
var _mov_janela_ok: bool = true
var _mov_camera_ok: bool = true
var _mov_ativo_antes: bool = false
var _mov_cam_fov0: float = -1.0
var _mov_cam_pos0: Vector3 = Vector3.ZERO
var _mov_win_home: Vector2 = Vector2.ZERO
var _mov_win_moveu: bool = false


func _on_movimento(dados):
	if typeof(dados) != TYPE_DICTIONARY:
		return
	if _mov == null:
		var script = load(MOV_PATH)
		if script == null or not script.can_instantiate():
			return
		_mov = script.new()
		if _mov == null:
			return
	var acao: String = str(dados.get("action", ""))
	if acao == "movement_library":
		_mov.definir_todos(dados.get("clips", {}))
	elif acao == "movement_add":
		_mov.adicionar(str(dados.get("nome", "")), dados.get("clipe", {}))
	elif acao == "movement_play":
		_mov.tocar(str(dados.get("nome", "")), float(dados.get("escala", 1.0)))
	elif acao == "movement_stop":
		_mov.parar()
	elif acao == "movement_config":
		_mov_janela_ok = bool(dados.get("janela", true))
		_mov_camera_ok = bool(dados.get("camera", true))


func _mov_tick(delta: float):
	if _mov == null:
		return
	if (not _mov_ativo_antes) and _mov.ativo():
		# começando um clipe: descobre o "canto de casa" da janela (posição de agora menos o deslocamento guardado)
		_mov_win_home = Vector2(DisplayServer.window_get_position()) - Vector2(_mov.persistente("janela_x"), _mov.persistente("janela_y"))
		var cam0: Camera3D = get_viewport().get_camera_3d()
		if cam0 != null:
			_mov_cam_fov0 = cam0.fov
			_mov_cam_pos0 = cam0.position
	var f: Dictionary = _mov.atualizar(delta)
	var ativo: bool = bool(f.get("ativo", false))
	if (not ativo) and (not _mov_ativo_antes):
		return
	var terminou: bool = (not ativo) and _mov_ativo_antes
	_mov_ativo_antes = ativo
	if vida != null:
		if ativo:
			vida.mov_set(f)
		else:
			vida.mov_set({})
	if edit_mode or is_dragging:
		return
	_mov_aplicar_avatar(f)
	if _mov_camera_ok:
		_mov_aplicar_camera(f, terminou)
	if _mov_janela_ok:
		_mov_aplicar_janela(f, terminou)


func _mov_aplicar_avatar(f: Dictionary):
	var av = get_node_or_null("Akira")
	if av == null or not _vrm_anchor_ready:
		return
	var dx: float = float(f.get("corpo_x", 0.0))
	var dy: float = float(f.get("corpo_y", 0.0))
	var dz: float = float(f.get("corpo_z", 0.0))
	var rx: float = deg_to_rad(float(f.get("corpo_pitch", 0.0)))
	var ry: float = _vrm_anchor_rot_y + deg_to_rad(float(f.get("corpo_giro", 0.0)))
	var rz: float = deg_to_rad(float(f.get("corpo_roll", 0.0)))
	# Compensação de pivô no centro de massa (cintura ~0.82m) para mortais e estrelas girarem no ar sem afundar no chão
	var comp := Vector3.ZERO
	if absf(rx) > 0.001 or absf(rz) > 0.001:
		var hc: float = 0.82 * maxf(0.2, av.scale.y)
		var pc := Vector3(0.0, hc, 0.0)
		var b_rot := Basis.from_euler(Vector3(rx, ry, rz))
		var b_ref := Basis.from_euler(Vector3(0.0, ry, 0.0))
		comp = (b_ref * pc) - (b_rot * pc)
	# mesma conta de reaplicar_ajuste_manual_vrm(): âncora + ajuste do usuário + o deslocamento do movimento + compensação de pivô
	av.position = Vector3(
		_vrm_anchor_pos_xz.x + _vrm_manual_offset.x + dx + comp.x,
		_vrm_manual_offset.y + dy + comp.y,
		_vrm_anchor_pos_xz.y + _vrm_manual_offset.z + dz + comp.z
	)
	av.rotation = Vector3(rx, ry, rz)


func _mov_aplicar_camera(f: Dictionary, terminou: bool = false):
	var cam: Camera3D = get_viewport().get_camera_3d()
	if cam == null:
		return
	if _mov_cam_fov0 < 0.0:
		_mov_cam_fov0 = cam.fov
		_mov_cam_pos0 = cam.position
	if terminou:
		cam.fov = _mov_cam_fov0
		cam.position = _mov_cam_pos0
		return
	var zoom: float = clampf(float(f.get("camera_zoom", 1.0)), 0.4, 2.5)
	var dy: float = float(f.get("corpo_y", 0.0))
	var pitch_abs: float = absf(float(f.get("corpo_pitch", 0.0)))
	var roll_abs: float = absf(float(f.get("corpo_roll", 0.0)))
	var acro: float = clampf(maxf(maxf(absf(dy) - 0.25, 0.0) / 0.8, maxf(pitch_abs, roll_abs) / 90.0), 0.0, 1.0)
	var dz_acro: float = acro * 0.95
	var dy_acro: float = dy * 0.55 * acro - acro * 0.22
	cam.fov = clampf(rad_to_deg(2.0 * atan(tan(deg_to_rad(_mov_cam_fov0) * 0.5) / zoom)), 8.0, 100.0)
	cam.position = _mov_cam_pos0 + Vector3(float(f.get("camera_x", 0.0)), float(f.get("camera_y", 0.0)) + dy_acro, dz_acro)


func _mov_aplicar_janela(f: Dictionary, terminou: bool):
	if OS.get_name() == "Android":
		return      # v1.14: o movimento que anda com a janela pela tela só existe no PC
	var alvo: Vector2 = _mov_win_home + Vector2(
		float(f.get("janela_x", 0.0)) + float(f.get("janela_dx", 0.0)),
		float(f.get("janela_y", 0.0)) + float(f.get("janela_dy", 0.0)))
	# nunca sai da tela
	var tela: int = DisplayServer.window_get_current_screen()
	var area: Rect2i = DisplayServer.screen_get_usable_rect(tela)
	var tam: Vector2i = DisplayServer.window_get_size()
	alvo.x = clampf(alvo.x, float(area.position.x), float(area.end.x - tam.x))
	alvo.y = clampf(alvo.y, float(area.position.y), float(area.end.y - tam.y))
	var atual: Vector2 = Vector2(DisplayServer.window_get_position())
	if atual.distance_to(alvo) >= 1.0:
		DisplayServer.window_set_position(Vector2i(int(round(alvo.x)), int(round(alvo.y))))
		_mov_win_moveu = true
	if terminou and _mov_win_moveu:
		_mov_win_moveu = false
		# guarda o deslocamento que de fato foi alcançado (a tela pode ter limitado) e repinta (bug do DWM)
		_mov.definir_persistente("janela_x", alvo.x - _mov_win_home.x)
		_mov.definir_persistente("janela_y", alvo.y - _mov_win_home.y)
		_force_redraw()
