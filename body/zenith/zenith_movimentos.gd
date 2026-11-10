extends RefCounted
# ======================================================================
#  Zenith — MOVIMENTOS (v1.6): toca "clipes" de dados — pulo, dança, caretas, câmera, janela, mortais e acrobacias.
#
#  Um clipe é um dicionário vindo do Cérebro (brain/zenith_movimentos.py) ou criado localmente:
#    {"nome", "duracao", "repetir", "suave", "mao", "faixas": [{"alvo": "corpo_y", "chaves": [[t, valor], ...]}, ...]}
#  Aqui NÃO existe código vindo da IA: só números no tempo. Este arquivo apenas calcula o valor de cada
#  faixa a cada quadro (a mesma conta de zenith_movimentos.py -> avaliar(), testada em Python) e entrega
#  um dicionário para o akira_body.gd aplicar no avatar, na câmera e na janela.
#
#  Isolado de propósito: o akira_body.gd carrega este arquivo com load() e só usa se existir e funcionar.
#  Se algo falhar aqui, o avatar continua como sempre foi.
# ======================================================================

const PERSISTENTES := ["camera_zoom", "camera_x", "camera_y", "janela_x", "janela_y"]
const FILA_MAX := 4
const MOV_LOCAL_PATH := "user://movimentos_local.json"

# [mínimo, máximo] — limites amplos para permitir mortais, saltos altos, estrelas e acrobacias livres.
const LIMITES := {
	"corpo_x": [-3.0, 3.0], "corpo_y": [-1.5, 4.5], "corpo_z": [-3.0, 3.0],
	"corpo_giro": [-1080.0, 1080.0], "corpo_roll": [-720.0, 720.0], "corpo_pitch": [-720.0, 720.0],
	"cabeca_pitch": [-70.0, 70.0], "cabeca_yaw": [-100.0, 100.0], "cabeca_roll": [-70.0, 70.0],
	"camera_zoom": [0.2, 4.0], "camera_x": [-2.0, 2.0], "camera_y": [-2.0, 2.0],
	"janela_x": [-2500.0, 2500.0], "janela_y": [-1500.0, 1500.0],
	"janela_dx": [-500.0, 500.0], "janela_dy": [-500.0, 500.0],
}

var _clips: Dictionary = {}
var _fila: Array = []
var _atual: Dictionary = {}
var _t: float = 0.0
var _ini_persist: Dictionary = {}
var _persist: Dictionary = {"camera_zoom": 1.0, "camera_x": 0.0, "camera_y": 0.0, "janela_x": 0.0, "janela_y": 0.0}

func _init():
	_carregar_padroes()
	_carregar_locais()

func _carregar_padroes():
	_clips["mortal"] = {
		"nome": "mortal", "duracao": 1.3, "repetir": 1, "suave": true,
		"faixas": [
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.15, -0.18], [0.65, 1.35], [1.1, 0.05], [1.2, -0.05], [1.3, 0.0]]},
			{"alvo": "corpo_pitch", "chaves": [[0.0, 0.0], [0.15, 15.0], [0.38, -90.0], [0.65, -180.0], [0.92, -270.0], [1.15, -360.0], [1.3, -360.0]]},
			{"alvo": "braco_dir", "chaves": [[0.0, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0], [0.35, 0.45, 0.85, 0.25, 0.30, 0.90, 0.20, 0.95], [1.0, 0.45, 0.85, 0.25, 0.30, 0.90, 0.20, 0.8], [1.3, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0]]},
			{"alvo": "braco_esq", "chaves": [[0.0, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0], [0.35, 0.45, 0.85, 0.25, 0.30, 0.90, 0.20, 0.95], [1.0, 0.45, 0.85, 0.25, 0.30, 0.90, 0.20, 0.8], [1.3, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.85], [1.0, 0.85], [1.3, 0.0]]}
		]
	}
	_clips["mortal_frente"] = {
		"nome": "mortal_frente", "duracao": 1.3, "repetir": 1, "suave": true,
		"faixas": [
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.15, -0.18], [0.65, 1.35], [1.1, 0.05], [1.2, -0.05], [1.3, 0.0]]},
			{"alvo": "corpo_pitch", "chaves": [[0.0, 0.0], [0.15, -15.0], [0.38, 90.0], [0.65, 180.0], [0.92, 270.0], [1.15, 360.0], [1.3, 360.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.85], [1.0, 0.85], [1.3, 0.0]]}
		]
	}
	_clips["pulo_alto"] = {
		"nome": "pulo_alto", "duracao": 1.4, "repetir": 1, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.18, -0.22], [0.65, 1.6], [1.15, 0.05], [1.25, -0.05], [1.4, 0.0]]},
			{"alvo": "braco_dir", "chaves": [[0.0, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0], [0.55, 0.55, 0.80, 0.15, 0.35, 0.90, 0.15, 0.95], [1.4, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0]]},
			{"alvo": "braco_esq", "chaves": [[0.0, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0], [0.55, 0.55, 0.80, 0.15, 0.35, 0.90, 0.15, 0.95], [1.4, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.9], [1.1, 0.9], [1.4, 0.0]]}
		]
	}
	_clips["estrela"] = {
		"nome": "estrela", "duracao": 1.4, "repetir": 1, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "corpo_x", "chaves": [[0.0, 0.0], [0.35, -0.45], [0.7, 0.0], [1.05, 0.45], [1.4, 0.0]]},
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.25, 0.4], [0.7, 0.95], [1.15, 0.25], [1.4, 0.0]]},
			{"alvo": "corpo_roll", "chaves": [[0.0, 0.0], [0.7, 180.0], [1.4, 360.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.75], [1.1, 0.75], [1.4, 0.0]]}
		]
	}
	_clips["pulo"] = {
		"nome": "pulo", "duracao": 1.15, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.14, -0.05], [0.46, 0.45], [0.80, 0.0], [0.92, -0.02], [1.15, 0.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.7], [0.9, 0.7], [1.15, 0.0]]}
		]
	}
	_clips["pulo_duplo"] = {
		"nome": "pulo_duplo", "duracao": 0.95, "repetir": 2, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.12, -0.04], [0.42, 0.38], [0.78, 0.0], [0.95, 0.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.3], [0.42, 0.85], [0.95, 0.3]]}
		]
	}
	_clips["dancar"] = {
		"nome": "dancar", "duracao": 2.4, "repetir": 2, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "corpo_x", "chaves": [[0.0, 0.0], [0.6, 0.09], [1.2, 0.0], [1.8, -0.09], [2.4, 0.0]]},
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.3, 0.07], [0.6, 0.0], [0.9, 0.07], [1.2, 0.0], [1.5, 0.07], [1.8, 0.0], [2.1, 0.07], [2.4, 0.0]]},
			{"alvo": "corpo_giro", "chaves": [[0.0, 0.0], [0.6, 16.0], [1.2, 0.0], [1.8, -16.0], [2.4, 0.0]]},
			{"alvo": "corpo_roll", "chaves": [[0.0, 0.0], [0.6, 4.0], [1.2, 0.0], [1.8, -4.0], [2.4, 0.0]]},
			{"alvo": "cabeca_roll", "chaves": [[0.0, 0.0], [0.6, -10.0], [1.2, 0.0], [1.8, 10.0], [2.4, 0.0]]},
			{"alvo": "braco_dir", "chaves": [[0.0, 0.35, -0.75, 0.20, 0.25, -0.30, 0.70, 0.85], [0.6, 0.65, 0.45, 0.25, 0.35, 0.80, 0.35, 0.95], [1.2, 0.35, -0.55, 0.30, 0.20, 0.20, 0.80, 0.85], [1.8, 0.55, 0.25, 0.35, 0.25, 0.70, 0.45, 0.90], [2.4, 0.35, -0.75, 0.20, 0.25, -0.30, 0.70, 0.85]]},
			{"alvo": "braco_esq", "chaves": [[0.0, 0.55, 0.25, 0.35, 0.25, 0.70, 0.45, 0.90], [0.6, 0.35, -0.55, 0.30, 0.20, 0.20, 0.80, 0.85], [1.2, 0.65, 0.45, 0.25, 0.35, 0.80, 0.35, 0.95], [1.8, 0.35, -0.75, 0.20, 0.25, -0.30, 0.70, 0.85], [2.4, 0.55, 0.25, 0.35, 0.25, 0.70, 0.45, 0.90]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.65], [1.2, 0.85], [2.4, 0.65]]}
		]
	}
	_clips["girar"] = {
		"nome": "girar", "duracao": 1.3, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "corpo_giro", "chaves": [[0.0, 0.0], [1.3, 360.0]]},
			{"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.3, 0.05], [1.0, 0.05], [1.3, 0.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.4, 0.6], [1.0, 0.6], [1.3, 0.0]]}
		]
	}
	_clips["careta"] = {
		"nome": "careta", "duracao": 1.6, "suave": true,
		"faixas": [
			{"alvo": "cabeca_roll", "chaves": [[0.0, 0.0], [0.35, 16.0], [0.85, -14.0], [1.3, 8.0], [1.6, 0.0]]},
			{"alvo": "cabeca_pitch", "chaves": [[0.0, 0.0], [0.4, -10.0], [0.9, 8.0], [1.6, 0.0]]},
			{"alvo": "rosto:surprised", "chaves": [[0.0, 0.0], [0.3, 0.85], [0.8, 0.2], [1.6, 0.0]]},
			{"alvo": "rosto:ee", "chaves": [[0.0, 0.0], [0.4, 0.8], [1.1, 0.7], [1.6, 0.0]]},
			{"alvo": "rosto:blink", "chaves": [[0.0, 0.0], [0.5, 0.65], [0.9, 0.0], [1.6, 0.0]]}
		]
	}
	_clips["reverencia"] = {
		"nome": "reverencia", "duracao": 1.8, "suave": true,
		"faixas": [
			{"alvo": "corpo_pitch", "chaves": [[0.0, 0.0], [0.6, 28.0], [1.1, 28.0], [1.8, 0.0]]},
			{"alvo": "cabeca_pitch", "chaves": [[0.0, 0.0], [0.6, 18.0], [1.1, 18.0], [1.8, 0.0]]},
			{"alvo": "rosto:relaxed", "chaves": [[0.0, 0.0], [0.5, 0.8], [1.3, 0.8], [1.8, 0.0]]}
		]
	}
	_clips["aceno_grande"] = {
		"nome": "aceno_grande", "duracao": 1.8, "suave": true, "mao": "aberta",
		"faixas": [
			{"alvo": "braco_dir", "chaves": [[0.0, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0], [0.35, 0.65, 0.55, 0.20, 0.45, 0.85, 0.20, 0.95], [0.65, 0.45, 0.65, 0.20, 0.15, 0.92, 0.20, 0.95], [0.95, 0.65, 0.55, 0.20, 0.45, 0.85, 0.20, 0.95], [1.25, 0.45, 0.65, 0.20, 0.15, 0.92, 0.20, 0.95], [1.8, 0.12, -0.95, 0.05, 0.05, -0.95, 0.10, 0.0]]},
			{"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.8], [1.4, 0.8], [1.8, 0.0]]}
		]
	}

func _carregar_locais() -> void:
	if not FileAccess.file_exists(MOV_LOCAL_PATH):
		return
	var f = FileAccess.open(MOV_LOCAL_PATH, FileAccess.READ)
	if not f:
		return
	var parsed = JSON.parse_string(f.get_as_text())
	f.close()
	if parsed is Dictionary:
		for k in parsed:
			if parsed[k] is Dictionary:
				_clips[str(k)] = parsed[k]

func _salvar_locais(nome: String, clipe: Dictionary) -> void:
	var locais: Dictionary = {}
	if FileAccess.file_exists(MOV_LOCAL_PATH):
		var fr = FileAccess.open(MOV_LOCAL_PATH, FileAccess.READ)
		if fr:
			var p = JSON.parse_string(fr.get_as_text())
			fr.close()
			if p is Dictionary:
				locais = p
	locais[nome] = clipe
	var fw = FileAccess.open(MOV_LOCAL_PATH, FileAccess.WRITE)
	if fw:
		fw.store_string(JSON.stringify(locais))
		fw.close()

func definir_todos(clips) -> void:
	if typeof(clips) != TYPE_DICTIONARY:
		return
	_carregar_padroes()
	_carregar_locais()
	for k in clips:
		if clips[k] is Dictionary:
			_clips[str(k)] = (clips[k] as Dictionary).duplicate(true)

func adicionar(nome: String, clipe: Dictionary) -> bool:
	var n := nome.strip_edges().to_lower()
	if n == "" or clipe.is_empty():
		return false
	_clips[n] = clipe.duplicate(true)
	_salvar_locais(n, _clips[n])
	return true

func existe(nome: String) -> bool:
	return _clips.has(nome)


func tocar(nome: String, _escala: float = 1.0) -> bool:
	if not _clips.has(nome):
		return false
	if _atual.is_empty():
		_iniciar(nome)
		return true
	if _fila.size() < FILA_MAX:
		_fila.append(nome)
		return true
	return false


func parar() -> void:
	_fila.clear()
	_atual = {}
	_t = 0.0


func ativo() -> bool:
	return not _atual.is_empty()


func definir_persistente(alvo: String, valor: float) -> void:
	if _persist.has(alvo):
		_persist[alvo] = valor


func persistente(alvo: String) -> float:
	return float(_persist.get(alvo, 0.0))


func _iniciar(nome: String) -> void:
	_atual = _clips[nome]
	_t = 0.0
	_ini_persist = _persist.duplicate()


func _envelope(t: float, total: float) -> float:
	var a: float = clampf(t / 0.18, 0.0, 1.0)
	var b: float = clampf((total - t) / 0.25, 0.0, 1.0)
	a = a * a * (3.0 - 2.0 * a)
	b = b * b * (3.0 - 2.0 * b)
	return minf(a, b)


func _valor_chave(c: Array, alvo: String):
	if c.size() == 2:
		if typeof(c[1]) == TYPE_NIL:
			if _ini_persist.has(alvo):
				return float(_ini_persist[alvo])
			if alvo == "camera_zoom":
				return 1.0
			return 0.0
		return float(c[1])
	var saida: Array = []
	for i in range(1, c.size()):
		saida.append(float(c[i]))
	return saida


func _interpolar(chaves: Array, t: float, suave: bool, alvo: String):
	var primeira: Array = chaves[0]
	if t <= float(primeira[0]):
		return _valor_chave(primeira, alvo)
	for i in range(chaves.size() - 1):
		var a: Array = chaves[i]
		var b: Array = chaves[i + 1]
		if t <= float(b[0]):
			var span: float = float(b[0]) - float(a[0])
			var u: float = 1.0
			if span > 0.000001:
				u = (t - float(a[0])) / span
			if suave:
				u = u * u * (3.0 - 2.0 * u)
			var va = _valor_chave(a, alvo)
			var vb = _valor_chave(b, alvo)
			if va is Array:
				var r: Array = []
				for k in range((va as Array).size()):
					r.append(float(va[k]) + (float(vb[k]) - float(va[k])) * u)
				return r
			return float(va) + (float(vb) - float(va)) * u
	return _valor_chave(chaves[chaves.size() - 1], alvo)


# Chamado todo quadro pelo akira_body.gd. Devolve o dicionário do quadro:
#   "ativo": bool, "peso": 0..1 (envelope p/ braços, cabeça e rosto), "corpo_*", "cabeca_*", "camera_*", "janela_*",
#   "braco_dir"/"braco_esq": [ux,uy,uz,lx,ly,lz,peso], "rosto": {nome: 0..1}, "mao": "aberta"...
func atualizar(delta: float) -> Dictionary:
	var f: Dictionary = {"ativo": false, "peso": 0.0}
	if _atual.is_empty():
		for p in PERSISTENTES:
			f[p] = float(_persist[p])
		return f
	_t += delta
	var dur: float = maxf(0.05, float(_atual.get("duracao", 1.0)))
	var repetir: int = maxi(1, int(_atual.get("repetir", 1)))
	var total: float = dur * float(repetir)
	var fim: bool = _t >= total
	var t_local: float = dur
	if not fim:
		t_local = fposmod(_t, dur)
	var suave: bool = bool(_atual.get("suave", true))
	f["ativo"] = true
	f["peso"] = _envelope(minf(_t, total), total)
	var rosto: Dictionary = {}
	var faixas: Array = _atual.get("faixas", [])
	for faixa in faixas:
		var alvo: String = String(faixa.get("alvo", ""))
		var chaves: Array = faixa.get("chaves", [])
		if chaves.size() < 2:
			continue
		var v = _interpolar(chaves, t_local, suave, alvo)
		if alvo.begins_with("rosto:"):
			rosto[alvo.substr(6)] = clampf(float(v), 0.0, 1.0)
		elif alvo == "braco_dir" or alvo == "braco_esq":
			f[alvo] = v
		elif LIMITES.has(alvo):
			var lim: Array = LIMITES[alvo]
			f[alvo] = clampf(float(v), float(lim[0]), float(lim[1]))
	f["rosto"] = rosto
	var m = _atual.get("mao", null)
	if m != null and String(m) != "":
		f["mao"] = String(m)
	for p in PERSISTENTES:
		if f.has(p):
			_persist[p] = float(f[p])
		else:
			f[p] = float(_persist[p])
	if fim:
		_atual = {}
		_t = 0.0
		if not _fila.is_empty():
			_iniciar(String(_fila.pop_front()))
	return f
