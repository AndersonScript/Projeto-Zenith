extends Node3D
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  zenith_avatar_simples.gd — v1.17 (port celular): o "AVATAR SIMPLES" do downgrade.
#
#  Um personagem low-poly DESENHADO EM CÓDIGO (esferas, cápsulas, caixas): sem arquivo .vrm, sem esqueleto, sem sombreador
#  MToon. Serve a celulares que não aguentam o VRM e a quem ainda não importou nenhum avatar. A regra do projeto continua:
#  "o avatar fica sempre visível; o piso do downgrade é o avatar padrão, nunca sem avatar".
#
#  Fala a MESMA língua que o Corpo usa com o VRM: set_life_state("idle"/"thinking"/"speaking"/"greeting", e os nomes em
#  português) e set_expression("happy"/"feliz"/"joy", "angry"/"brava"/"anger", "sad"/"triste"/"sorrow", "surprised"/
#  "surpresa", "neutral"/"neutro"). A origem (0,0,0) é o PÉ do personagem, olhando para +Z (para a câmera do Corpo).
#
#  Carregado pela akira_body.gd com load() CONFERIDO. Não foi comparado com o VRM de verdade (aqui não há .vrm).
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════

const BASE_SOBRANCELHA := 0.152       # altura da sobrancelha parada, no pivô da cabeça
const ESTADOS_FALANDO := ["speaking", "falando"]
const ESTADOS_PENSANDO := ["thinking", "pensando"]
const ESTADOS_CUMPRIMENTO := ["greeting"]
const EXPRESSOES := {
	# nome -> [olho_y, sobrancelha_y, sobrancelha_giro, boca_largura, boca_altura]
	"neutral": [1.0, 0.0, 0.0, 1.0, 1.0], "happy": [0.45, 0.004, 0.0, 1.6, 1.8], "sad": [0.8, 0.004, -0.45, 0.7, 0.8],
	"angry": [0.75, -0.004, 0.5, 0.85, 0.9], "surprised": [1.5, 0.012, 0.0, 0.6, 5.0],
}
const SINONIMOS := {
	"neutro": "neutral", "feliz": "happy", "joy": "happy", "brava": "angry", "anger": "angry", "triste": "sad",
	"sorrow": "sad", "surpresa": "surprised",
}

var _t := 0.0
var _estado := "idle"
var _expressao := "neutral"
var _cum_resto := 0.0
var _piscar_em := 3.0
var _piscando := 0.0
# valores suavizados (perseguem o alvo da expressão)
var _olho_y := 1.0
var _sobr_y := 0.0
var _sobr_giro := 0.0
var _boca_l := 1.0
var _boca_a := 1.0

var _tronco: MeshInstance3D
var _cabeca: Node3D
var _olhos: Array = []
var _brilhos: Array = []
var _sobrancelhas: Array = []
var _boca: MeshInstance3D

func _ready() -> void:
	_montar()

func _material(cor: Color, rugosidade := 0.85, emissao := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = cor
	m.roughness = rugosidade
	if emissao > 0.0:
		m.emission_enabled = true
		m.emission = cor
		m.emission_energy_multiplier = emissao
	return m

func _peca(pai: Node3D, malha: Mesh, cor: Color, pos: Vector3, rot := Vector3.ZERO, escala := Vector3.ONE, emissao := 0.0) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = malha
	mi.material_override = _material(cor, 0.85, emissao)
	mi.position = pos
	mi.rotation = rot
	mi.scale = escala
	pai.add_child(mi)
	return mi

func _esfera(r: float, h := -1.0) -> SphereMesh:
	var s := SphereMesh.new()
	s.radius = r
	s.height = (r * 2.0) if h < 0.0 else h
	s.radial_segments = 20
	s.rings = 10
	return s

func _capsula(r: float, h: float) -> CapsuleMesh:
	var c := CapsuleMesh.new()
	c.radius = r
	c.height = h
	c.radial_segments = 16
	c.rings = 4
	return c

func _caixa(x: float, y: float, z: float) -> BoxMesh:
	var b := BoxMesh.new()
	b.size = Vector3(x, y, z)
	return b

func _montar() -> void:
	var jaqueta := Color(0.16, 0.17, 0.2)
	var laranja := Color(0.96, 0.64, 0.34)         # o laranja do Zenith
	var pele := Color(0.93, 0.78, 0.68)
	var cabelo := Color(0.1, 0.09, 0.11)
	# corpo
	_tronco = _peca(self, _capsula(0.17, 0.62), jaqueta, Vector3(0, 1.0, 0))
	_peca(self, _capsula(0.06, 0.46), jaqueta, Vector3(0, 1.27, 0), Vector3(0, 0, PI / 2.0))           # ombros
	for lado in [-1.0, 1.0]:
		_peca(self, _capsula(0.055, 0.5), jaqueta, Vector3(lado * 0.245, 1.02, 0), Vector3(0, 0, lado * 0.08))   # braços
	_peca(self, _caixa(0.02, 0.42, 0.01), laranja, Vector3(0, 1.02, 0.168), Vector3.ZERO, Vector3.ONE, 0.25)   # listra
	_peca(self, _esfera(0.052, 0.12), pele, Vector3(0, 1.38, 0))                                              # pescoço
	# cabeça (um pivô: inclina e gira como um todo)
	_cabeca = Node3D.new()
	_cabeca.position = Vector3(0, 1.40, 0)
	add_child(_cabeca)
	_peca(_cabeca, _esfera(0.12, 0.27), pele, Vector3(0, 0.12, 0))
	_peca(_cabeca, _esfera(0.132, 0.25), cabelo, Vector3(0, 0.165, -0.032))                                   # cabelo (um boné para trás/cima)
	_peca(_cabeca, _caixa(0.19, 0.04, 0.05), cabelo, Vector3(0, 0.212, 0.07), Vector3(0.25, 0, 0))            # franja
	for lado in [-1.0, 1.0]:
		var olho := _peca(_cabeca, _esfera(0.018), Color(0.06, 0.07, 0.15), Vector3(lado * 0.045, 0.125, 0.103))
		_olhos.append(olho)
		_brilhos.append(_peca(_cabeca, _esfera(0.006), Color(1, 1, 1), Vector3(lado * 0.040, 0.132, 0.119), Vector3.ZERO, Vector3.ONE, 0.6))
		_sobrancelhas.append(_peca(_cabeca, _caixa(0.056, 0.012, 0.01), Color(0.2, 0.14, 0.12), Vector3(lado * 0.045, BASE_SOBRANCELHA, 0.124)))
	_boca = _peca(_cabeca, _caixa(0.045, 0.008, 0.008), Color(0.55, 0.18, 0.24), Vector3(0, 0.075, 0.108))

func set_life_state(nome: String) -> void:
	var n := nome.to_lower()
	if ESTADOS_FALANDO.has(n):
		_estado = "speaking"
	elif ESTADOS_PENSANDO.has(n):
		_estado = "thinking"
	elif ESTADOS_CUMPRIMENTO.has(n):
		_estado = "greeting"
		_cum_resto = 1.2
	else:
		_estado = "idle"

func set_expression(nome: String) -> void:
	var n := nome.to_lower()
	n = SINONIMOS.get(n, n)
	_expressao = n if EXPRESSOES.has(n) else "neutral"

func _process(delta: float) -> void:
	if _cabeca == null:
		return
	_t += delta
	# --- expressão: cada valor persegue o alvo, sem pular ---
	var alvo: Array = EXPRESSOES[_expressao]
	var k: float = minf(1.0, delta * 8.0)
	_olho_y = lerpf(_olho_y, alvo[0], k)
	_sobr_y = lerpf(_sobr_y, alvo[1], k)
	_sobr_giro = lerpf(_sobr_giro, alvo[2], k)
	_boca_l = lerpf(_boca_l, alvo[3], k)
	_boca_a = lerpf(_boca_a, alvo[4], k)
	# --- piscar ---
	_piscar_em -= delta
	if _piscar_em <= 0.0 and _piscando <= 0.0:
		_piscando = 0.12
		_piscar_em = randf_range(2.0, 6.0)
	var fecha := 1.0
	if _piscando > 0.0:
		_piscando -= delta
		fecha = 0.1
	for olho in _olhos:
		olho.scale.y = _olho_y * fecha
	for b in _brilhos:
		b.visible = fecha > 0.5
	for i in _sobrancelhas.size():
		var lado: float = -1.0 if i == 0 else 1.0
		_sobrancelhas[i].position.y = BASE_SOBRANCELHA + _sobr_y
		_sobrancelhas[i].rotation.z = _sobr_giro * lado        # giro > 0: pontas de DENTRO para baixo (brava); < 0: para cima (triste)
	# --- estado: respiração, cabeça e boca ---
	var resp: float = 0.01 if _estado != "thinking" else 0.006
	var vel: float = 1.5 if _estado != "thinking" else 2.6
	_tronco.scale.y = 1.0 + resp * sin(_t * vel)
	var inclina: float = 0.02 * sin(_t * 0.7)
	var gira: float = 0.0
	var abre: float = 0.0
	match _estado:
		"thinking":
			gira = 0.22
			inclina = 0.09
		"speaking":
			abre = clampf(0.5 + 0.5 * sin(_t * 11.0) * (0.6 + 0.4 * sin(_t * 3.1)), 0.0, 1.0)
			inclina += 0.015 * sin(_t * 5.0)
		"greeting":
			_cum_resto -= delta
			_cabeca.rotation.x = 0.12 * sin(_t * 7.0)
			if _cum_resto <= 0.0:
				_estado = "idle"
	if _estado != "greeting":
		_cabeca.rotation.x = lerpf(_cabeca.rotation.x, 0.0, k)
	_cabeca.rotation.z = lerpf(_cabeca.rotation.z, inclina, k)
	_cabeca.rotation.y = lerpf(_cabeca.rotation.y, gira, k)
	_boca.scale = Vector3(_boca_l, _boca_a + 5.0 * abre, 1.0)
