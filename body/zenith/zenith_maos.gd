extends RefCounted
# ======================================================================
#  Zenith — MÃOS (v1.4): dedos que se curvam, em vez de "tábua reta".
#
#  Problema: ao levantar o braço para "pensar", o antebraço subia mas a mão ficava
#  esticada, com os dedos retos e duros (a pose de repouso do VRM é uma T-pose).
#
#  O que este arquivo faz: curva as 3 juntas de cada um dos 5 dedos (15 por mão) com uma pose
#  RELAXADA o tempo todo, abre a mão ao acenar/comemorar,
#  fecha um pouco mais ao pensar, e "conversa" com os dedos (movimento sutil) enquanto fala.
#
#  Como acerta a direção da curva sem ver o modelo: ela é CALCULADA da geometria do próprio
#  esqueleto na pose de repouso — o eixo de cada junta é (direção do dedo) x (normal da palma),
#  e a normal da palma sai de 3 pontos (pulso, base do indicador, base do mindinho). Por isso
#  funciona igual nos dois lados e em modelos com nomes de osso diferentes.
#
#  ISOLADO DE PROPÓSITO: o akira_vida.gd carrega este arquivo com load() (não preload) e só usa
#  se preparar() devolver > 0. Se algo aqui falhar, as mãos ficam como sempre foram — o resto
#  do avatar não é afetado.
#
#  NÃO TESTADO NO GODOT (escrito num computador sem Godot). A matemática foi conferida em Python
#  (tests/test_v1_4.py). Se os dedos aparecerem dobrados para o lado errado, mude SINAL_CURVA
#  para -1.0 e avise.
# ======================================================================

const SINAL_CURVA := 1.0

const DEDOS := ["thumb", "index", "middle", "ring", "little"]

# Ângulo (radianos) de cada junta [base, meio, ponta], por pose.
const POSES := {
	"relaxada": {
		"thumb": [0.10, 0.14, 0.10],
		"index": [0.22, 0.35, 0.18],
		"middle": [0.28, 0.42, 0.22],
		"ring": [0.34, 0.48, 0.25],
		"little": [0.40, 0.52, 0.28],
	},
	"aberta": {
		"thumb": [0.03, 0.04, 0.03],
		"index": [0.06, 0.08, 0.05],
		"middle": [0.07, 0.09, 0.05],
		"ring": [0.08, 0.10, 0.06],
		"little": [0.10, 0.12, 0.06],
	},
	"punho": {
		"thumb": [0.30, 0.35, 0.25],
		"index": [0.90, 1.10, 0.70],
		"middle": [0.95, 1.12, 0.72],
		"ring": [1.00, 1.14, 0.74],
		"little": [1.05, 1.15, 0.75],
	},
	"apontar": {
		"thumb": [0.15, 0.20, 0.10],
		"index": [0.02, 0.03, 0.02],
		"middle": [0.90, 1.10, 0.60],
		"ring": [1.00, 1.12, 0.62],
		"little": [1.05, 1.15, 0.64],
	},
	"pensar": {
		"thumb": [0.18, 0.22, 0.14],
		"index": [0.40, 0.55, 0.30],
		"middle": [0.50, 0.65, 0.35],
		"ring": [0.58, 0.72, 0.38],
		"little": [0.64, 0.78, 0.40],
	},
}

var _sk: Skeleton3D = null
var _juntas: Array = []
var _peso: Dictionary = {"relaxada": 1.0, "aberta": 0.0, "pensar": 0.0, "punho": 0.0, "apontar": 0.0}
var _mapa: Dictionary = {}


func _norm(s: String) -> String:
	return s.to_lower().replace("_", "").replace(".", "").replace("-", "").replace(" ", "").replace(":", "")


func _achar(candidatos: Array) -> int:
	for c in candidatos:
		var chave: String = _norm(String(c))
		if _mapa.has(chave):
			return int(_mapa[chave])
	return -1


func _nomes_da_junta(lado: String, dedo: String, junta: int) -> Array:
	# lado: "Left" | "Right". Aceita os nomes do Godot (humanoide) e os crus do VRoid.
	var rotulo: String = dedo.capitalize()
	var inicial: String = lado.substr(0, 1)
	var lista: Array = []
	if dedo == "thumb":
		var gd: Array = ["Metacarpal", "Proximal", "Distal"]
		lista.append("%s%s%s" % [lado, rotulo, gd[junta]])
		if junta == 1:
			lista.append("%s%sIntermediate" % [lado, rotulo])
	else:
		var gd2: Array = ["Proximal", "Intermediate", "Distal"]
		lista.append("%s%s%s" % [lado, rotulo, gd2[junta]])
	lista.append("J_Bip_%s_%s%d" % [inicial, rotulo, junta + 1])
	return lista


# Devolve quantas juntas de dedo foram encontradas e preparadas (0 = não use este módulo).
func preparar(sk: Skeleton3D, up: Vector3, lat: Vector3) -> int:
	_sk = sk
	_juntas = []
	_mapa = {}
	if sk == null:
		return 0
	for i in range(sk.get_bone_count()):
		_mapa[_norm(sk.get_bone_name(i))] = i
	var contador: int = 0
	for lado in ["Left", "Right"]:
		var sinal: float = -1.0
		if lado == "Right":
			sinal = 1.0
		var mao: int = _achar(["%sHand" % lado, "J_Bip_%s_Hand" % lado.substr(0, 1)])
		# ids[dedo] = [id_base, id_meio, id_ponta]
		var ids: Dictionary = {}
		for dedo in DEDOS:
			var trio: Array = []
			for j in range(3):
				trio.append(_achar(_nomes_da_junta(lado, String(dedo), j)))
			ids[dedo] = trio
		# normal da palma (aponta para o lado da palma)
		var normal: Vector3 = -up
		var base_ind: int = int(ids["index"][0])
		var base_min: int = int(ids["little"][0])
		if mao != -1 and base_ind != -1 and base_min != -1:
			var po: Vector3 = sk.get_bone_global_rest(mao).origin
			var a: Vector3 = sk.get_bone_global_rest(base_ind).origin - po
			var b: Vector3 = sk.get_bone_global_rest(base_min).origin - po
			var n: Vector3 = a.cross(b)
			if n.length() > 0.00001:
				n = n.normalized()
				var ref: Vector3 = (-up * 0.7 + (-lat * sinal) * 0.7).normalized()
				if n.dot(ref) >= 0.0:
					normal = n
				else:
					normal = -n
		var di: int = 0
		for dedo2 in DEDOS:
			var trio2: Array = ids[dedo2]
			for j2 in range(3):
				var id: int = int(trio2[j2])
				if id == -1:
					continue
				var d: Vector3 = Vector3.ZERO
				var prox: int = -1
				if j2 < 2:
					prox = int(trio2[j2 + 1])
				if prox != -1:
					d = sk.get_bone_global_rest(prox).origin - sk.get_bone_global_rest(id).origin
				elif j2 > 0 and int(trio2[j2 - 1]) != -1:
					d = sk.get_bone_global_rest(id).origin - sk.get_bone_global_rest(int(trio2[j2 - 1])).origin
				if d.length() < 0.00001:
					continue
				d = d.normalized()
				var eixo_g: Vector3 = d.cross(normal)
				if eixo_g.length() < 0.2:
					continue
				eixo_g = eixo_g.normalized()
				var gb: Basis = sk.get_bone_global_rest(id).basis.orthonormalized()
				var eixo_l: Vector3 = (gb.inverse() * eixo_g).normalized()
				_juntas.append({
					"id": id,
					"rest": sk.get_bone_rest(id).basis.get_rotation_quaternion(),
					"eixo": eixo_l,
					"dedo": String(dedo2),
					"junta": j2,
					"fase": float(j2) * 0.7 + float(di) * 1.3 + (0.0 if lado == "Left" else 2.1),
				})
				contador += 1
			di += 1
	return contador


# Chamado todo quadro pelo akira_vida.gd. `gesto` = nome do gesto atual ("" se nenhum).
func atualizar(delta: float, gesto: String, falando: bool, t: float) -> void:
	if _sk == null or _juntas.is_empty():
		return
	var alvo: String = "relaxada"
	if POSES.has(gesto):
		alvo = gesto                    # v1.6: um movimento pode escolher a pose da mão pelo nome
	elif gesto == "acenar" or gesto == "comemorar" or gesto == "ombros":
		alvo = "aberta"
	var k: float = 1.0 - exp(-delta * 6.0)
	for nome in _peso.keys():
		var w: float = float(_peso[nome])
		var objetivo: float = 0.0
		if String(nome) == alvo:
			objetivo = 1.0
		_peso[nome] = w + (objetivo - w) * k
	for j in _juntas:
		var dedo: String = j["dedo"]
		var idx: int = j["junta"]
		var ang: float = 0.0
		for nome2 in _peso.keys():
			var tabela: Array = POSES[nome2][dedo]
			ang += float(_peso[nome2]) * float(tabela[idx])
		var fase: float = j["fase"]
		ang = ang * (1.0 + 0.07 * sin(t * 0.9 + fase))
		if falando:
			ang += 0.05 * sin(t * 3.2 + fase * 1.7)
		ang = clampf(ang, 0.0, 1.45) * SINAL_CURVA
		var rest: Quaternion = j["rest"]
		var eixo: Vector3 = j["eixo"]
		_sk.set_bone_pose_rotation(int(j["id"]), rest * Quaternion(eixo, ang))


# Volta os dedos para a pose de repouso do modelo.
func soltar() -> void:
	if _sk == null:
		return
	for j in _juntas:
		var rest: Quaternion = j["rest"]
		_sk.set_bone_pose_rotation(int(j["id"]), rest)
