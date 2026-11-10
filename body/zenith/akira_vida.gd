extends RefCounted
# ============================================================
#  ZENITH — akira_vida.gd  (v20)
#
#  Motor de "vida" do avatar. É um módulo À PARTE: o akira_body.gd continua com a
#  base de sempre (respiração, balanço de peso, cabeça errante — vinda do v15/v16)
#  e só CHAMA este módulo no fim do _process. Nada aqui troca ou remove aquela base.
#
#  O que ele faz que a base não fazia:
#   1. EXPRESSÕES DE VERDADE. A base procurava blend shapes chamados "Joy", "Blink"...
#      mas um VRM do VRoid (os seus) tem "Fcl_ALL_Joy", "Fcl_EYE_Close"... — a busca
#      nunca achava nada, então NEM O PISCAR nem as emoções funcionavam. Aqui lemos
#      as expressões do próprio VRM (o addon cria uma animação por expressão:
#      happy, angry, sad, relaxed, surprised, aa, ih, ou, ee, oh, blink...) e
#      aplicamos os blend shapes que ELAS mandam. Se o modelo não tiver, cai num
#      plano B por nome exato dos shapes do VRoid.
#   2. BOCA enquanto fala (visemes aa/ih/ou/ee/oh) — não existia nenhum movimento
#      de boca no corpo. É "boca de mentira" (não lê o áudio): abre e fecha com ritmo
#      natural enquanto o estado é "falando".
#   3. BRAÇOS NATURAIS. O VRM nasce em T-pose (braços abertos). Em vez de girar
#      ossos por eixo local (o que dava "braço torto", porque cada modelo orienta
#      os ossos de um jeito), aqui o osso é APONTADO para uma direção calculada no
#      espaço do esqueleto (cima/lado/frente tirados da própria anatomia). Isso não
#      depende da convenção de eixos do modelo (a matemática foi conferida numa
#      simulação com 400 convenções aleatórias; ver HANDOFF.md).
#   4. GESTOS: acenar, concordar, negar, inclinar a cabeça, dar de ombros, pensar,
#      reverência, comemorar, pulinho. + gestos pequenos ao falar e, no nível
#      "expressivo", micro-gestos aleatórios parada.
#   5. OLHAR PRO MOUSE (opcional): a cabeça acompanha o cursor, devagar.
#
#  Tudo tem chave liga/desliga (Configurações > Corpo / VRM > Vida do avatar) e
#  qualquer coisa que não for encontrada (osso, malha, expressão) é simplesmente
#  ignorada — nunca derruba o corpo.
# ============================================================

const IDLE := 0
const THINKING := 1
const SPEAKING := 2
const GREETING := 3

const EXPR_NAMES := ["happy", "angry", "sad", "relaxed", "surprised", "neutral",
	"aa", "ih", "ou", "ee", "oh", "blink", "blinkleft", "blinkright"]
const EMOTIONS := ["happy", "angry", "sad", "relaxed", "surprised"]
const VISEMES := ["aa", "ih", "ou", "ee", "oh"]

# Plano B: nomes EXATOS (minúsculos) dos blend shapes do VRoid, caso o modelo não traga as
# animações de expressão.
const FALLBACK_SHAPES := {
	"happy": ["fcl_all_joy", "joy", "happy"],
	"angry": ["fcl_all_angry", "angry", "anger"],
	"sad": ["fcl_all_sorrow", "sorrow", "sad"],
	"relaxed": ["fcl_all_fun", "fun", "relaxed"],
	"surprised": ["fcl_all_surprised", "surprised"],
	"aa": ["fcl_mth_a", "a", "aa"],
	"ih": ["fcl_mth_i", "i", "ih"],
	"ou": ["fcl_mth_u", "u", "ou"],
	"ee": ["fcl_mth_e", "e", "ee"],
	"oh": ["fcl_mth_o", "o", "oh"],
	"blink": ["fcl_eye_close", "blink"],
	"blinkleft": ["fcl_eye_close_l", "blink_l", "blinkleft"],
	"blinkright": ["fcl_eye_close_r", "blink_r", "blinkright"],
}

# Nomes de osso aceitos (o addon VRM entrega os nomes "humanoides" do Godot; os crus do
# VRoid ficam como plano B).
const BONE_NAMES := {
	"hips": ["Hips", "J_Bip_C_Hips"],
	"spine": ["Spine", "J_Bip_C_Spine"],
	"chest": ["Chest", "J_Bip_C_Chest"],
	"neck": ["Neck", "J_Bip_C_Neck"],
	"head": ["Head", "J_Bip_C_Head"],
	"l_eye": ["LeftEye", "J_Adj_L_FaceEye"],
	"r_eye": ["RightEye", "J_Adj_R_FaceEye"],
	"l_shoulder": ["LeftShoulder", "J_Bip_L_Shoulder"],
	"r_shoulder": ["RightShoulder", "J_Bip_R_Shoulder"],
	"l_upper": ["LeftUpperArm", "J_Bip_L_UpperArm"],
	"r_upper": ["RightUpperArm", "J_Bip_R_UpperArm"],
	"l_lower": ["LeftLowerArm", "J_Bip_L_LowerArm"],
	"r_lower": ["RightLowerArm", "J_Bip_R_LowerArm"],
	"l_hand": ["LeftHand", "J_Bip_L_Hand"],
	"r_hand": ["RightHand", "J_Bip_R_Hand"],
}

# ---- configuração (vem das Configurações) ----
var nivel: String = "suave"          # "desligado" | "suave" | "expressivo"
var bracos_naturais: bool = true
var olhar_mouse: bool = true

# ---- ligações ----
var body: Node3D = null
var skeleton: Skeleton3D = null
var _root: Node = null
var _meshes: Array = []
var _bones: Dictionary = {}

# ---- referencial do corpo (espaço do esqueleto) ----
var _up := Vector3.UP
var _lat := Vector3.RIGHT           # da ESQUERDA do personagem para a DIREITA dele
var _fwd := Vector3.BACK            # para onde o personagem olha
var _frame_ok := false
var _pitch_sign := 1.0              # sinal que faz a cabeça "baixar" ao girar em torno de _lat
var _yaw_right_sign := 1.0          # sinal que gira para a DIREITA do personagem
var _rest_dir: Dictionary = {}      # "r_upper" -> direção em T-pose
var _rest_rot: Dictionary = {}      # "spine"/"head" -> rotação local de repouso (pra não acumular quadro a quadro)
var _arms_touched := false
var _shoulders_touched := false
# v1.4 — mãos/dedos: módulo ISOLADO (load, não preload; se falhar, as mãos ficam como sempre foram)
const MAOS_PATH := "res://zenith_maos.gd"
var _maos = null
# v1.6 — quadro do movimento em curso (braços, cabeça, rosto, mão): vem do akira_body.gd (zenith_movimentos.gd)
var _mov: Dictionary = {}

# ---- expressões ----
var _binds: Dictionary = {}         # nome -> Array de [MeshInstance3D, índice, peso]
var _expr_w: Dictionary = {}        # peso atual de cada expressão (0..1)
var _driven: Dictionary = {}        # chave "id:idx" -> [mesh, idx] já mexidos (pra zerar depois)
var _emotion: String = "neutral"
var _emotion_until: float = 0.0
var _emotion_strength: float = 0.55         # v21: era 0.75 — "feliz" fechava os olhos demais
var _t: float = 0.0

# ---- piscar ----
var _next_blink: float = 2.5
var _blink_phase: float = -1.0       # <0 = parado; senão progresso 0..1

# ---- boca ----
var _mouth_target: String = "aa"
var _mouth_amp: float = 0.0
var _mouth_next: float = 0.0
var _mouth_cur: Dictionary = {}

# ---- gestos ----
var _gesture: String = ""
var _g_t0: float = 0.0
var _g_dur: float = 0.0
var _g_hold: bool = false            # fica até o estado de vida mudar (ex.: "pensar")
var _g_scale: float = 1.0
var _next_micro: float = 8.0
var _look_yaw: float = 0.0
var _look_pitch: float = 0.0
var _life: int = IDLE
var _bounce: float = 0.0


# ======================================================================
#  Ligação com o avatar
# ======================================================================
func setup(p_body: Node3D, p_skeleton: Skeleton3D, p_root: Node, p_meshes: Array) -> String:
	body = p_body
	skeleton = p_skeleton
	_root = p_root
	_meshes = p_meshes
	_bones = {}
	_rest_dir = {}
	_rest_rot = {}
	_shoulders_touched = false
	_binds = {}
	_expr_w = {}
	_driven = {}
	_mouth_cur = {}
	_arms_touched = false
	_frame_ok = false
	_gesture = ""
	_emotion = "neutral"
	if skeleton != null:
		for key in BONE_NAMES.keys():
			_bones[key] = _find_bone(BONE_NAMES[key])
		_frame_ok = _compute_frame()
		if _frame_ok:
			_capture_rest_dirs()
			_preparar_maos()
			for k in ["spine", "head"]:
				if _has(k):
					_rest_rot[k] = skeleton.get_bone_rest(int(_bones[k])).basis.get_rotation_quaternion()
	_build_expressions()
	return describe()


func _preparar_maos():
	_maos = null
	if skeleton == null or not _frame_ok:
		return
	var script = load(MAOS_PATH)
	if script == null or not script.can_instantiate():
		return
	var m = script.new()
	if m != null and m.has_method("preparar") and int(m.preparar(skeleton, _up, _lat)) > 0:
		_maos = m


func _norm(s: String) -> String:
	return s.to_lower().replace("_", "").replace(".", "").replace("-", "").replace(" ", "").replace(":", "")


func _find_bone(candidates: Array) -> int:
	for c in candidates:
		var i = skeleton.find_bone(String(c))
		if i != -1:
			return i
	var wanted: Array = []
	for c in candidates:
		wanted.append(_norm(String(c)))
	for i in range(skeleton.get_bone_count()):
		if _norm(skeleton.get_bone_name(i)) in wanted:
			return i
	return -1


func _has(key: String) -> bool:
	return int(_bones.get(key, -1)) != -1


func _compute_frame() -> bool:
	if not (_has("l_upper") and _has("r_upper") and _has("hips") and _has("head")):
		return false
	var pl: Vector3 = skeleton.get_bone_global_rest(int(_bones["l_upper"])).origin
	var pr: Vector3 = skeleton.get_bone_global_rest(int(_bones["r_upper"])).origin
	var ph: Vector3 = skeleton.get_bone_global_rest(int(_bones["head"])).origin
	var pp: Vector3 = skeleton.get_bone_global_rest(int(_bones["hips"])).origin
	var up = ph - pp
	if up.length() < 0.001:
		return false
	_up = up.normalized()
	var lat = pr - pl
	lat = lat - _up * lat.dot(_up)
	if lat.length() < 0.001:
		return false
	_lat = lat.normalized()
	# frente = cima x lateral (ver a conta na simulação do HANDOFF: vale pra qualquer orientação)
	_fwd = _up.cross(_lat).normalized()
	# conferência com os olhos, se existirem: o olho fica À FRENTE da origem da cabeça
	if _has("l_eye"):
		var pe: Vector3 = skeleton.get_bone_global_rest(int(_bones["l_eye"])).origin
		if (pe - ph).dot(_fwd) < -0.002:
			_fwd = -_fwd
	_pitch_sign = 1.0 if (Quaternion(_lat, 0.1) * _up).dot(_fwd) > 0.0 else -1.0
	_yaw_right_sign = 1.0 if (Quaternion(_up, 0.1) * _fwd).dot(_lat) > 0.0 else -1.0
	return true


func _capture_rest_dirs():
	for pre in ["l_", "r_"]:
		var chain = [[pre + "shoulder", pre + "upper"], [pre + "upper", pre + "lower"], [pre + "lower", pre + "hand"]]
		for pair in chain:
			if _has(pair[0]) and _has(pair[1]):
				var a: Vector3 = skeleton.get_bone_global_rest(int(_bones[pair[0]])).origin
				var b: Vector3 = skeleton.get_bone_global_rest(int(_bones[pair[1]])).origin
				if (b - a).length() > 0.0001:
					_rest_dir[pair[0]] = (b - a).normalized()


func describe() -> String:
	var achados: Array = []
	var faltando: Array = []
	for key in BONE_NAMES.keys():
		if _has(key):
			achados.append(key)
		else:
			faltando.append(key)
	var linhas: Array = []
	linhas.append("Vida (nível %s | braços naturais: %s | olhar o mouse: %s)" % [nivel, str(bracos_naturais), str(olhar_mouse)])
	linhas.append("Ossos: %d/%d achados%s" % [achados.size(), BONE_NAMES.size(),
		("" if faltando.is_empty() else " — faltam: " + ", ".join(PackedStringArray(faltando)))])
	linhas.append("Referencial do corpo: %s" % ("ok" if _frame_ok else "NÃO calculado (faltam ossos básicos) — braços e gestos ficam desligados"))
	var com_expr: Array = []
	for n in EXPR_NAMES:
		if _binds.has(n):
			com_expr.append(n)
	linhas.append("Expressões com blend shape: %d/%d (%s)" % [com_expr.size(), EXPR_NAMES.size() - 1, ", ".join(PackedStringArray(com_expr))])
	return "\n".join(PackedStringArray(linhas))


# ======================================================================
#  Expressões (lidas do próprio VRM)
# ======================================================================
func _find_animation_players(node: Node) -> Array:
	var found: Array = []
	for child in node.get_children():
		if child is AnimationPlayer:
			found.append(child)
		found.append_array(_find_animation_players(child))
	return found


func _build_expressions():
	_binds = {}
	if _root != null:
		for ap in _find_animation_players(_root):
			var base: Node = ap.get_node_or_null(ap.root_node)
			if base == null:
				base = ap.get_parent()
			for lib_name in ap.get_animation_library_list():
				var lib: AnimationLibrary = ap.get_animation_library(lib_name)
				for an in lib.get_animation_list():
					var key = String(an).to_lower()
					if not (key in EXPR_NAMES):
						continue
					var anim: Animation = lib.get_animation(an)
					var binds: Array = []
					for ti in range(anim.get_track_count()):
						if anim.track_get_type(ti) != Animation.TYPE_BLEND_SHAPE:
							continue
						if anim.track_get_key_count(ti) == 0:
							continue
						var path: NodePath = anim.track_get_path(ti)
						var node = base.get_node_or_null(NodePath(String(path.get_concatenated_names())))
						if not (node is MeshInstance3D):
							continue
						var shape = String(path.get_concatenated_subnames())
						var idx = (node as MeshInstance3D).find_blend_shape_by_name(shape)
						if idx == -1:
							continue
						var w = float(anim.track_get_key_value(ti, 0))
						if w > 0.0001:
							binds.append([node, idx, minf(w, 1.0)])
					if not binds.is_empty():
						_binds[key] = binds
	# Plano B por nome exato, só para o que o modelo não trouxe
	for key in FALLBACK_SHAPES.keys():
		if _binds.has(key):
			continue
		var found: Array = []
		for mi in _meshes:
			if not is_instance_valid(mi) or not (mi is MeshInstance3D):
				continue
			var m: MeshInstance3D = mi
			if m.mesh == null:
				continue
			for i in range(m.mesh.get_blend_shape_count()):
				var nm = String(m.mesh.get_blend_shape_name(i)).to_lower()
				if nm in FALLBACK_SHAPES[key]:
					found.append([m, i, 1.0])
		if not found.is_empty():
			_binds[key] = found
	for n in EXPR_NAMES:
		_expr_w[n] = 0.0
	for v in VISEMES:
		_mouth_cur[v] = 0.0


func has_expressions() -> bool:
	return not _binds.is_empty()


# "happy", "feliz", "joy"... -> nome VRM; "" = neutro
func _expr_from_word(word: String) -> String:
	match word.to_lower().strip_edges():
		"happy", "feliz", "joy", "alegre", "contente", "fun":
			return "happy"
		"angry", "brava", "bravo", "anger", "raiva":
			return "angry"
		"sad", "triste", "sorrow", "tristeza":
			return "sad"
		"surprised", "surpresa", "surpreso", "surprise":
			return "surprised"
		"relaxed", "calma", "calmo", "relaxada", "relaxado", "tranquila":
			return "relaxed"
		_:
			return ""


func set_emotion(word: String, hold_seconds: float = 6.0):
	var e = _expr_from_word(word)
	_emotion = e if e != "" else "neutral"
	_emotion_until = _t + hold_seconds
	if _emotion == "happy":
		bounce(0.5)
	elif _emotion == "surprised":
		bounce(0.8)


func bounce(strength: float = 1.0):
	_bounce = maxf(_bounce, clampf(strength, 0.0, 1.5))


# ======================================================================
#  Estado de vida e gestos
# ======================================================================
func set_life(state: int):
	var before = _life
	_life = state
	if before == THINKING and state != THINKING and _gesture == "pensar" and _g_hold:
		_g_hold = false
		_g_dur = (_t - _g_t0) + 0.5
	if state == THINKING and nivel != "desligado" and _gesture == "":
		play_gesture("pensar")
	if state == GREETING:
		play_gesture("acenar")


const GESTURE_DURATIONS := {
	"acenar": 2.1, "concordar": 1.3, "negar": 1.4, "inclinar": 2.2, "ombros": 1.6,
	"pensar": 4.0, "reverencia": 2.0, "comemorar": 2.2, "pulinho": 0.7,
}


func gesture_names() -> Array:
	return GESTURE_DURATIONS.keys()


func _gesture_alias(n: String) -> String:
	match n.to_lower().strip_edges():
		"wave", "oi", "aceno", "acenar", "tchau":
			return "acenar"
		"nod", "sim", "concordar", "yes":
			return "concordar"
		"shake", "nao", "não", "negar", "no":
			return "negar"
		"tilt", "curiosa", "inclinar", "curioso":
			return "inclinar"
		"shrug", "ombros", "dar_de_ombros", "sei_la":
			return "ombros"
		"think", "pensar", "pensando":
			return "pensar"
		"bow", "reverencia", "reverência", "cumprimentar":
			return "reverencia"
		"cheer", "comemorar", "vitoria", "vitória", "yay":
			return "comemorar"
		"hop", "pulinho", "pular", "bounce":
			return "pulinho"
		_:
			return ""


# Devolve true se o gesto existe. `escala` 1.0 = normal.
func play_gesture(name: String, escala: float = 1.0) -> bool:
	var g = _gesture_alias(name)
	if g == "":
		return false
	if nivel == "desligado" and g != "pulinho":
		return false
	if not _frame_ok and g != "pulinho":
		return false
	_gesture = g
	_g_t0 = _t
	_g_dur = float(GESTURE_DURATIONS[g])
	_g_hold = (g == "pensar" and _life == THINKING)
	_g_scale = escala * (1.35 if nivel == "expressivo" else 1.0)
	if g == "pulinho" or g == "comemorar":
		bounce(1.0)
	return true


func _envelope(t: float, dur: float, rise: float = 0.28, fall: float = 0.35) -> float:
	if t < 0.0 or t > dur:
		return 0.0
	var a = smoothstep(0.0, rise, t)
	var b = 1.0 - smoothstep(maxf(dur - fall, rise), dur, t)
	return a * b


# ======================================================================
#  Atualização por quadro (chamada pelo akira_body.gd no fim do _process)
# ======================================================================
func update(delta: float, life_state: int):
	_t += delta
	if life_state != _life:
		set_life(life_state)
	if nivel == "desligado":
		_zero_driven_shapes()
		_bounce = maxf(0.0, _bounce - delta * 3.0)
		return
	_update_face(delta)
	if skeleton == null or not _frame_ok:
		_bounce = maxf(0.0, _bounce - delta * 3.0)
		return
	_update_gesture_timer()
	_update_arms(delta)
	if _maos != null:
		var pose_mao: String = _gesture
		if _mov.has("mao"):
			pose_mao = String(_mov["mao"])
		_maos.atualizar(delta, pose_mao, _life == SPEAKING, _t)
	_update_posture(delta)
	_update_head_extras(delta)


func mov_set(d: Dictionary):
	_mov = d


func get_bounce_offset() -> float:
	return _bounce * 0.012 * sin(_t * 18.0) * clampf(_bounce, 0.0, 1.0)


func _update_gesture_timer():
	if _gesture != "":
		if _g_hold and _life == THINKING:
			_g_dur = (_t - _g_t0) + 1.0
		elif (_t - _g_t0) > _g_dur:
			_gesture = ""
			_g_hold = false
	# micro-gestos aleatórios (só no nível "expressivo", parada)
	if _gesture == "" and nivel == "expressivo" and _life == IDLE and _t > _next_micro:
		var pool = ["inclinar", "concordar", "ombros"]
		play_gesture(pool[randi() % pool.size()], 0.6)
		_next_micro = _t + randf_range(7.0, 16.0)
	elif _next_micro < _t:
		_next_micro = _t + randf_range(7.0, 16.0)


# ---------------------------------------------------------------- rosto
func _update_face(delta: float):
	# 1) emoção alvo: segura por um tempo e depois relaxa pro neutro
	var emo_target = _emotion
	if _t > _emotion_until and _life != SPEAKING:
		emo_target = "neutral"
	var kf = 1.0 - exp(-delta * 7.0)
	# v21: falando, a emoção diminui (senão olhos fechados + boca aberta ao mesmo tempo ficam estranhos)
	var forca_emo = _emotion_strength * (0.7 if _life == SPEAKING else 1.0)
	for e in EMOTIONS:
		var alvo = forca_emo if e == emo_target else 0.0
		_expr_w[e] = lerpf(float(_expr_w[e]), alvo, kf)

	# 2) piscar (mais raro quando a emoção já fecha os olhos)
	var blink_w = 0.0
	if _blink_phase < 0.0:
		if _t >= _next_blink:
			_blink_phase = 0.0
	else:
		_blink_phase += delta / 0.17
		if _blink_phase >= 1.0:
			_blink_phase = -1.0
			_next_blink = _t + randf_range(2.2, 6.0)
			if randf() < 0.18:
				_next_blink = _t + 0.25      # piscada dupla
		else:
			blink_w = sin(_blink_phase * PI)
	var emo_close = 0.0
	if emo_target == "happy":
		emo_close = float(_expr_w["happy"]) * 0.6
	blink_w *= (1.0 - emo_close)

	# 3) boca ao falar (visemes), com respiros
	var speaking = (_life == SPEAKING)
	if speaking:
		if _t >= _mouth_next:
			if randf() < 0.16:
				_mouth_amp = 0.0                              # pausa curta, como entre palavras
				_mouth_next = _t + randf_range(0.10, 0.22)
			else:
				_mouth_target = VISEMES[randi() % VISEMES.size()]
				_mouth_amp = randf_range(0.18, 0.55)      # v21: era 0.30–0.85 (boca escancarada)
				_mouth_next = _t + randf_range(0.07, 0.17)
	else:
		_mouth_amp = 0.0
	var km = 1.0 - exp(-delta * 22.0)
	for v in VISEMES:
		var alvo_v = _mouth_amp if (speaking and v == _mouth_target) else 0.0
		_mouth_cur[v] = lerpf(float(_mouth_cur[v]), alvo_v, km)

	# 4) soma tudo por blend shape e aplica
	var acc: Dictionary = {}
	for e in EMOTIONS:
		_accumulate(acc, e, float(_expr_w[e]))
	_accumulate(acc, "blink", blink_w)
	for v in VISEMES:
		_accumulate(acc, v, float(_mouth_cur[v]))
	# v1.6 — rosto de um MOVIMENTO (careta, espanto...): pesos 0..1 por expressão, com o envelope do clipe
	if _mov.has("rosto"):
		var rosto_mov: Dictionary = _mov["rosto"]
		var peso_mov: float = float(_mov.get("peso", 1.0))
		for rk in rosto_mov.keys():
			_accumulate(acc, String(rk), float(rosto_mov[rk]) * peso_mov)
	for k in acc.keys():
		var par: Array = acc[k]
		var mi: MeshInstance3D = par[0]
		if is_instance_valid(mi):
			mi.set_blend_shape_value(int(par[1]), clampf(float(par[2]), 0.0, 1.0))
		_driven[k] = [par[0], par[1]]
	# o que foi mexido antes e agora não está mais ativo volta a zero
	for k in _driven.keys():
		if not acc.has(k):
			var d: Array = _driven[k]
			if is_instance_valid(d[0]):
				(d[0] as MeshInstance3D).set_blend_shape_value(int(d[1]), 0.0)
			_driven.erase(k)


func _zero_driven_shapes():
	if _driven.is_empty():
		return
	for k in _driven.keys():
		var d: Array = _driven[k]
		if is_instance_valid(d[0]):
			(d[0] as MeshInstance3D).set_blend_shape_value(int(d[1]), 0.0)
	_driven.clear()


# Ao desligar a vida: tudo que ela mexeu volta ao repouso do arquivo (a base de respiração/
# cabeça do akira_body.gd segue funcionando por conta própria).
func reset_pose_to_rest():
	_zero_driven_shapes()
	_gesture = ""
	if skeleton == null:
		return
	for key in ["l_shoulder", "r_shoulder", "l_upper", "r_upper", "l_lower", "r_lower", "l_hand", "r_hand", "spine"]:
		if _has(key):
			var b = int(_bones[key])
			skeleton.set_bone_pose_rotation(b, skeleton.get_bone_rest(b).basis.get_rotation_quaternion())
	_arms_touched = false
	_shoulders_touched = false
	if _maos != null:
		_maos.soltar()


func _accumulate(acc: Dictionary, expr: String, weight: float):
	if weight < 0.002 or not _binds.has(expr):
		return
	for b in _binds[expr]:
		var mi = b[0]
		if not is_instance_valid(mi):
			continue
		var key = str(mi.get_instance_id()) + ":" + str(b[1])
		var add = weight * float(b[2])
		if acc.has(key):
			acc[key][2] = float(acc[key][2]) + add
		else:
			acc[key] = [mi, b[1], add]


# ---------------------------------------------------------------- ossos
func _dir(lat_amt: float, up_amt: float, fwd_amt: float, side: float) -> Vector3:
	# side: +1 = braço DIREITO do personagem, -1 = esquerdo
	return (_lat * (lat_amt * side) + _up * up_amt + _fwd * fwd_amt).normalized()


func _gparent_quat(bone: int) -> Quaternion:
	var parent = skeleton.get_bone_parent(bone)
	if parent == -1:
		return Quaternion.IDENTITY
	return skeleton.get_bone_global_pose(parent).basis.orthonormalized().get_rotation_quaternion()


# Gira o osso por uma rotação GLOBAL (espaço do esqueleto) por cima da pose atual.
func _rotate_global(bone: int, rot: Quaternion):
	if bone == -1:
		return
	var pq = _gparent_quat(bone)
	var local = skeleton.get_bone_pose_rotation(bone)
	skeleton.set_bone_pose_rotation(bone, (pq.inverse() * rot * pq * local).normalized())


# Faz o osso `bone` apontar (na direção do filho `child`) para `target` (espaço do esqueleto).
# `w` = fração do caminho andada neste quadro (suavização). Só gira "de lado" (swing) — não
# mexe na torção do osso nem no comprimento.
func _aim(bone: int, child: int, target: Vector3, w: float):
	if bone == -1 or child == -1:
		return
	var gb = skeleton.get_bone_global_pose(bone)
	var gc = skeleton.get_bone_global_pose(child)
	var cur = gc.origin - gb.origin
	if cur.length() < 0.0001 or target.length() < 0.0001:
		return
	cur = cur.normalized()
	var tgt = target.normalized()
	var swing: Quaternion
	if cur.dot(tgt) < -0.9999:
		swing = Quaternion(_fwd, PI)
	else:
		swing = Quaternion(cur, tgt)
	if w < 1.0:
		swing = Quaternion.IDENTITY.slerp(swing, w)
	_rotate_global(bone, swing)


func _arm_targets(side: float, pre: String) -> Array:
	var gt = _gesture_t()
	var t_up: Vector3
	var t_lo: Vector3
	if bracos_naturais:
		# respiração/ruído bem leves nos braços
		var br = sin(_t * 1.3) * 0.012
		var sway = sin(_t * 0.43 + side) * 0.018
		t_up = _dir(0.17 + sway, -0.98, 0.05 + br, side)
		t_lo = _dir(0.06 + sway * 0.5, -0.93, 0.32 + br, side)
		if _life == SPEAKING and nivel != "desligado":
			# gesticulação leve do braço direito ao falar
			if side > 0.0:
				var k = 0.5 + 0.5 * sin(_t * 2.1)
				t_lo = _dir(0.04 - 0.1 * k, -0.62 + 0.45 * k, 0.55, side)
	else:
		t_up = _rest_dir.get(pre + "upper", _dir(1.0, 0.0, 0.0, side))
		t_lo = _rest_dir.get(pre + "lower", _dir(1.0, 0.0, 0.0, side))
	# gestos sobrepõem (mistura pelo envelope)
	var ov = _gesture_arm(side, gt)
	if ov.size() == 3:
		var wgt: float = float(ov[0])
		t_up = t_up.lerp(ov[1], wgt).normalized()
		t_lo = t_lo.lerp(ov[2], wgt).normalized()
	# v1.6 — braço de um MOVIMENTO (dados): mistura pelo peso do clipe e pelo envelope
	var chave_braco: String = "braco_esq"
	if side > 0.0:
		chave_braco = "braco_dir"
	if _mov.has(chave_braco):
		var mv: Array = _mov[chave_braco]
		if mv.size() >= 7:
			var wm: float = clampf(float(mv[6]) * float(_mov.get("peso", 1.0)), 0.0, 1.0)
			if wm > 0.001:
				var m_up: Vector3 = _dir(float(mv[0]), float(mv[1]), float(mv[2]), side)
				var m_lo: Vector3 = _dir(float(mv[3]), float(mv[4]), float(mv[5]), side)
				t_up = t_up.lerp(m_up, wm).normalized()
				t_lo = t_lo.lerp(m_lo, wm).normalized()
	return [t_up, t_lo]


func _gesture_t() -> float:
	if _gesture == "":
		return -1.0
	return _t - _g_t0


func _gesture_arm(side: float, gt: float) -> Array:
	if _gesture == "" or gt < 0.0:
		return []
	var e = _envelope(gt, _g_dur) * minf(_g_scale, 1.3)
	e = clampf(e, 0.0, 1.0)
	match _gesture:
		"acenar":
			if side > 0.0:
				var osc = sin(gt * 11.0) * 0.55
				return [e, _dir(0.72, 0.62, 0.20, side), _dir(0.25 + osc, 0.92, 0.15, side)]
		"comemorar":
			return [e, _dir(0.55, 0.85, 0.10, side), _dir(0.20 + sin(gt * 9.0) * 0.15, 1.0, 0.10, side)]
		"ombros":
			return [e, _dir(0.48, -0.82, 0.12, side), _dir(0.80, -0.15, 0.45, side)]
		"pensar":
			if side > 0.0:
				return [e, _dir(0.05, -0.55, 0.55, side), _dir(-0.30, 0.78, 0.55, side)]
		"reverencia":
			return [e * 0.7, _dir(0.10, -0.98, 0.25, side), _dir(0.0, -0.80, 0.55, side)]
	return []


func _update_arms(delta: float):
	if not (bracos_naturais or _gesture != "" or _arms_touched or _mov.has("braco_dir") or _mov.has("braco_esq")):
		return
	var k = 1.0 - exp(-delta * 7.0)
	# ombros primeiro (os braços são filhos deles): levantam em "ombros", senão ficam no repouso
	var lift = 0.0
	if _gesture == "ombros":
		lift = _envelope(_gesture_t(), _g_dur)
	if lift > 0.001 or _shoulders_touched:
		for pre0 in ["r_", "l_"]:
			var key_sh = pre0 + "shoulder"
			if _has(key_sh) and _has(pre0 + "upper") and _rest_dir.has(key_sh):
				var alvo_sh: Vector3 = (_rest_dir[key_sh] + _up * (0.35 * lift)).normalized()
				_aim(int(_bones[key_sh]), int(_bones[pre0 + "upper"]), alvo_sh, 1.0 - exp(-delta * 10.0))
				_shoulders_touched = true
	for pre in ["r_", "l_"]:
		var side = 1.0 if pre == "r_" else -1.0
		if not (_has(pre + "upper") and _has(pre + "lower")):
			continue
		var tg = _arm_targets(side, pre)
		var kk = k
		if _gesture == "acenar" or _gesture == "comemorar" or _mov.has("braco_dir") or _mov.has("braco_esq"):
			kk = 1.0 - exp(-delta * 14.0)          # gesto/movimento: mais rápido que a pose parada
		_aim(int(_bones[pre + "upper"]), int(_bones[pre + "lower"]), tg[0], kk)
		if _has(pre + "hand"):
			_aim(int(_bones[pre + "lower"]), int(_bones[pre + "hand"]), tg[1], kk)
		_arms_touched = true


func _update_posture(delta: float):
	# respiração/balanço do tronco, mais "vivo" que só o osso do peito da base
	var sp = int(_bones.get("spine", -1))
	if sp != -1:
		var roll = sin(_t * 0.53) * 0.010 + sin(_t * 1.3) * 0.004
		var pitch = sin(_t * 0.37 + 1.0) * 0.008
		var extra_pitch = 0.0
		if _rest_rot.has("spine"):
			skeleton.set_bone_pose_rotation(sp, _rest_rot["spine"])     # absoluto: sem acumular
		if _gesture == "reverencia":
			extra_pitch = 0.42 * _envelope(_gesture_t(), _g_dur, 0.5, 0.6)
		_rotate_global(sp, Quaternion(_fwd, roll) * Quaternion(_lat, (pitch + extra_pitch) * _pitch_sign))


func _update_head_extras(delta: float):
	var neck = int(_bones.get("neck", -1))
	var head = int(_bones.get("head", -1))
	if head == -1:
		return
	var gt = _gesture_t()
	var e = 0.0
	if _gesture != "":
		e = clampf(_envelope(gt, _g_dur) * minf(_g_scale, 1.3), 0.0, 1.0)
	var yaw = 0.0      # + = para a direita do personagem
	var pitch = 0.0    # + = baixar a cabeça
	var roll = 0.0

	match _gesture:
		"concordar":
			pitch = 0.20 * sin(gt * TAU * 1.7) * e
		"negar":
			yaw = 0.30 * sin(gt * TAU * 2.0) * e
		"inclinar":
			roll = 0.20 * e
			pitch = -0.04 * e
		"pensar":
			roll = 0.14 * e
			pitch = -0.08 * e
			yaw = -0.12 * e
		"ombros":
			roll = 0.12 * sin(gt * TAU * 0.6) * e
		"reverencia":
			pitch = 0.20 * e
		"acenar":
			roll = 0.08 * e
		"comemorar":
			pitch = -0.10 * e

	# v1.6 — cabeça de um MOVIMENTO (graus nos dados): soma ao gesto, com o envelope do clipe
	if _mov.has("cabeca_pitch") or _mov.has("cabeca_yaw") or _mov.has("cabeca_roll"):
		var wh: float = float(_mov.get("peso", 1.0))
		pitch += deg_to_rad(float(_mov.get("cabeca_pitch", 0.0))) * wh
		yaw += deg_to_rad(float(_mov.get("cabeca_yaw", 0.0))) * wh
		roll += deg_to_rad(float(_mov.get("cabeca_roll", 0.0))) * wh

	# ao falar: cabeça acompanha o ritmo, bem de leve
	if _life == SPEAKING:
		pitch += 0.025 * sin(_t * 2.6) + 0.015 * sin(_t * 4.3 + 1.2)
		yaw += 0.02 * sin(_t * 1.7)

	# olhar o mouse (cabeça + pescoço), suavizado
	var alvo_yaw = 0.0
	var alvo_pitch = 0.0
	if olhar_mouse:
		var m = DisplayServer.mouse_get_position()
		var wp = DisplayServer.window_get_position()
		var ws = DisplayServer.window_get_size()
		var c = Vector2(wp.x + ws.x * 0.5, wp.y + ws.y * 0.3)
		var nx = clampf((float(m.x) - c.x) / 900.0, -1.0, 1.0)
		var ny = clampf((float(m.y) - c.y) / 600.0, -1.0, 1.0)
		# v21: zona morta no meio (cursor perto = não fica "tremendo" atrás do mouse) e amplitude menor
		# (a cabeça virava/baixava demais quando o mouse estava longe, em outro monitor, por exemplo)
		if absf(nx) < 0.10:
			nx = 0.0
		if absf(ny) < 0.10:
			ny = 0.0
		var amp = 0.36 if nivel == "expressivo" else 0.26
		# mouse à direita da tela = lado ESQUERDO do personagem (ele está de frente pra nós)
		alvo_yaw = -nx * amp
		alvo_pitch = ny * 0.12
	var kl = 1.0 - exp(-delta * 3.0)
	_look_yaw = lerpf(_look_yaw, alvo_yaw, kl)
	_look_pitch = lerpf(_look_pitch, alvo_pitch, kl)

	# composição em rotações globais: yaw em torno de _up, pitch em torno de _lat, roll em torno de _fwd
	var yaw_total = yaw + _look_yaw
	var pitch_total = pitch + _look_pitch
	# `yaw_total` positivo = direita do personagem; converte pelo sinal medido no referencial
	var q_yaw = Quaternion(_up, yaw_total * _yaw_right_sign)
	var q_pitch = Quaternion(_lat, pitch_total * _pitch_sign)
	var q_roll = Quaternion(_fwd, roll)
	var rot = q_yaw * q_pitch * q_roll
	if _rest_rot.has("head"):
		skeleton.set_bone_pose_rotation(head, _rest_rot["head"])           # absoluto: sem acumular
	if neck != -1:
		_rotate_global(neck, Quaternion.IDENTITY.slerp(rot, 0.4))
		_rotate_global(head, Quaternion.IDENTITY.slerp(rot, 0.6))
	else:
		_rotate_global(head, rot)

	_bounce = maxf(0.0, _bounce - delta * 2.2)
