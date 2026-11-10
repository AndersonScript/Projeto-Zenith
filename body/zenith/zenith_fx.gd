extends ColorRect
# ZENITH — camada de fundo de UMA área da interface (histórico, chat, barra de cima...).
# Fica atrás do conteúdo, nunca recebe clique. Quem manda nela é o zenith_aparencia.gd.

const SHADER := preload("res://zenith_fx.gdshader")
const IDS := {"gradiente": 1, "arco_iris": 2, "respiracao": 3, "fogo": 4, "aurora": 5,
	"plasma": 6, "tinta": 7, "borda_neon": 8, "particulas": 9, "estrelas": 10, "varredura": 11}

var area_id: String = ""
var tipo: String = "nenhum"
var velocidade: float = 1.0
var _mat: ShaderMaterial

func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)
	color = Color(0, 0, 0, 0)
	_mat = ShaderMaterial.new()
	_mat.shader = SHADER
	resized.connect(func(): _mat.set_shader_parameter("tamanho", size))

func aplicar(cfg: Dictionary) -> void:
	tipo = str(cfg.get("tipo", "nenhum"))
	velocidade = clampf(float(cfg.get("velocidade", 1.0)), 0.0, 3.0)
	var cores: Array = cfg.get("cores", ["#00d9ff", "#ff4fa3", "#34d399", "#a78bfa"])
	if cores.is_empty():
		cores = ["#00d9ff", "#ff4fa3"]
	var op := clampf(float(cfg.get("opacidade", 1.0)), 0.0, 1.0)
	if tipo == "nenhum":
		visible = false
		material = null
		return
	visible = true
	if tipo == "cor":
		material = null
		color = Color.from_string(str(cores[0]), Color("14141f"))
		color.a = op
		return
	if not IDS.has(tipo):
		visible = false
		return
	color = Color.WHITE
	material = _mat
	_mat.set_shader_parameter("efeito", IDS[tipo])
	for i in 4:
		var c := Color.from_string(str(cores[i % cores.size()]), Color.WHITE) if cores.size() > 0 else Color.WHITE
		_mat.set_shader_parameter("c" + str(i + 1), c)
	_mat.set_shader_parameter("ncores", clampi(int(cfg.get("ncores", cores.size())), 2, 4))
	_mat.set_shader_parameter("intensidade", clampf(float(cfg.get("intensidade", 0.6)), 0.0, 1.0))
	_mat.set_shader_parameter("opacidade", op)
	_mat.set_shader_parameter("tamanho", size)

func animado() -> bool:
	return visible and material != null

func tempo(t: float) -> void:
	if _mat:
		_mat.set_shader_parameter("t", t * velocidade)
