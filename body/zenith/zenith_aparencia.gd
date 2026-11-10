extends Node
# ZENITH — Estúdio de Aparência (motor).
# O usuário escolhe, para CADA área (fundo geral, histórico, barra de cima, chat, caixa de digitar),
# uma cor, um gradiente ou um efeito animado. Também troca a paleta inteira ao vivo (sem reiniciar).
# Tudo fica em user://zenith_aparencia.cfg  (e a paleta em user://zenith_tema.cfg, que o ui_manager já lia).

const FX := preload("res://zenith_fx.gd")
const Icones := preload("res://zenith_icones.gd")
const CFG := "user://zenith_aparencia.cfg"

const AREAS := [
	["moldura", "Fundo geral da janela"],
	["barra_lateral", "Histórico (barra lateral)"],
	["barra_superior", "Barra de cima"],
	["chat", "Área do chat"],
	["entrada", "Caixa de digitar"],
]
const EFEITOS := [
	["nenhum", "Nenhum (cor do tema)"], ["cor", "Cor sólida"], ["gradiente", "Gradiente que desliza"],
	["arco_iris", "Arco-íris"], ["respiracao", "Respiração"], ["fogo", "Fogo"], ["aurora", "Aurora"],
	["plasma", "Plasma"], ["tinta", "Tinta que muda de cor"], ["borda_neon", "Borda neon que anda"],
	["particulas", "Chuva de partículas"], ["estrelas", "Estrelas cintilando"], ["varredura", "Linhas de varredura"],
]
const CHAVES_PALETA := ["BG_BASE", "BG_PANEL", "BG_SURFACE", "BG_SURFACE_2", "BG_SURFACE_3", "BORDER", "CYAN", "CYAN_DIM",
	"MAGENTA", "GREEN", "RED", "TEXT_PRIMARY", "TEXT_SECOND", "TEXT_MUTED", "BUBBLE_USER", "BUBBLE_AI"]

# Pontos de partida (não são "o estilo do Zenith": o padrão é o neutro e o resto é do usuário).
const PRESETS := {
	"neutro": {"nome": "Neutro (padrão)", "BG_BASE": "0b0d17", "BG_PANEL": "11141f", "BG_SURFACE": "11141f", "BG_SURFACE_2": "181c2b",
		"BG_SURFACE_3": "222740", "BORDER": "2a3050", "CYAN": "22d3ee", "CYAN_DIM": "0e7c93", "MAGENTA": "f472b6", "GREEN": "34d399",
		"RED": "f87171", "TEXT_PRIMARY": "eef1ff", "TEXT_SECOND": "aab2d5", "TEXT_MUTED": "8089b3", "BUBBLE_USER": "123a48", "BUBBLE_AI": "181c2b"},
	"papel": {"nome": "Papel (claro)", "BG_BASE": "f6f7fb", "BG_PANEL": "eceef6", "BG_SURFACE": "eceef6", "BG_SURFACE_2": "ffffff",
		"BG_SURFACE_3": "e3e6f2", "BORDER": "cbd0e4", "CYAN": "0b6fd6", "CYAN_DIM": "0a57aa", "MAGENTA": "c2185b", "GREEN": "0f8a5f",
		"RED": "c62828", "TEXT_PRIMARY": "1a1d2e", "TEXT_SECOND": "4a5072", "TEXT_MUTED": "636a91", "BUBBLE_USER": "d6e8fb", "BUBBLE_AI": "ffffff"},
	"neon": {"nome": "Neon", "BG_BASE": "07040f", "BG_PANEL": "0d0820", "BG_SURFACE": "0d0820", "BG_SURFACE_2": "150c33",
		"BG_SURFACE_3": "20124d", "BORDER": "3a1f7a", "CYAN": "00f0ff", "CYAN_DIM": "0891a8", "MAGENTA": "ff2bd6", "GREEN": "39ff9c",
		"RED": "ff5470", "TEXT_PRIMARY": "f4eeff", "TEXT_SECOND": "bba8f0", "TEXT_MUTED": "8f7dc8", "BUBBLE_USER": "0a3a52", "BUBBLE_AI": "150c33"},
	"sakura": {"nome": "Sakura", "BG_BASE": "1a1118", "BG_PANEL": "22161f", "BG_SURFACE": "22161f", "BG_SURFACE_2": "2d1d29",
		"BG_SURFACE_3": "3a2636", "BORDER": "4a2f40", "CYAN": "ff8fb8", "CYAN_DIM": "b8587f", "MAGENTA": "ffb3d1", "GREEN": "7ee0b0",
		"RED": "ff6b81", "TEXT_PRIMARY": "fff1f6", "TEXT_SECOND": "e0b7c8", "TEXT_MUTED": "b88ca0", "BUBBLE_USER": "4a2338", "BUBBLE_AI": "2d1d29"},
	"meia_noite": {"nome": "Meia-noite", "BG_BASE": "060814", "BG_PANEL": "0a0e22", "BG_SURFACE": "0a0e22", "BG_SURFACE_2": "101634",
		"BG_SURFACE_3": "19224a", "BORDER": "263063", "CYAN": "6c8cff", "CYAN_DIM": "3f56b8", "MAGENTA": "c084fc", "GREEN": "34d399",
		"RED": "f87171", "TEXT_PRIMARY": "e8edff", "TEXT_SECOND": "a9b5e8", "TEXT_MUTED": "7c89c4", "BUBBLE_USER": "172457", "BUBBLE_AI": "101634"},
	"floresta": {"nome": "Floresta", "BG_BASE": "0b140f", "BG_PANEL": "101c14", "BG_SURFACE": "101c14", "BG_SURFACE_2": "16271b",
		"BG_SURFACE_3": "1f3626", "BORDER": "2b4a35", "CYAN": "4ade80", "CYAN_DIM": "23995a", "MAGENTA": "f9a8d4", "GREEN": "86efac",
		"RED": "f87171", "TEXT_PRIMARY": "eaf7ee", "TEXT_SECOND": "a9c9b3", "TEXT_MUTED": "7fa48b", "BUBBLE_USER": "14422a", "BUBBLE_AI": "16271b"},
	"por_do_sol": {"nome": "Pôr do sol", "BG_BASE": "170e12", "BG_PANEL": "1f1317", "BG_SURFACE": "1f1317", "BG_SURFACE_2": "2b1a1f",
		"BG_SURFACE_3": "3a2229", "BORDER": "553039", "CYAN": "fb923c", "CYAN_DIM": "b4600f", "MAGENTA": "f472b6", "GREEN": "a3e635",
		"RED": "f87171", "TEXT_PRIMARY": "fff3ea", "TEXT_SECOND": "e6bfa6", "TEXT_MUTED": "b58d78", "BUBBLE_USER": "4a2a12", "BUBBLE_AI": "2b1a1f"},
	"lavanda": {"nome": "Lavanda", "BG_BASE": "120e1d", "BG_PANEL": "181328", "BG_SURFACE": "181328", "BG_SURFACE_2": "21193a",
		"BG_SURFACE_3": "2d2350", "BORDER": "3f3270", "CYAN": "b197fc", "CYAN_DIM": "7351d9", "MAGENTA": "f0abfc", "GREEN": "6ee7b7",
		"RED": "fb7185", "TEXT_PRIMARY": "f2eeff", "TEXT_SECOND": "c3b6ee", "TEXT_MUTED": "9486c9", "BUBBLE_USER": "33266b", "BUBBLE_AI": "21193a"},
	"mono": {"nome": "Mono", "BG_BASE": "0e0e0e", "BG_PANEL": "151515", "BG_SURFACE": "151515", "BG_SURFACE_2": "1e1e1e",
		"BG_SURFACE_3": "2a2a2a", "BORDER": "383838", "CYAN": "e5e5e5", "CYAN_DIM": "9a9a9a", "MAGENTA": "cfcfcf", "GREEN": "bdbdbd",
		"RED": "d9d9d9", "TEXT_PRIMARY": "f5f5f5", "TEXT_SECOND": "bdbdbd", "TEXT_MUTED": "8c8c8c", "BUBBLE_USER": "2f2f2f", "BUBBLE_AI": "1e1e1e"},
	"amoled": {"nome": "Amoled", "BG_BASE": "000000", "BG_PANEL": "050505", "BG_SURFACE": "050505", "BG_SURFACE_2": "0e0e12",
		"BG_SURFACE_3": "18181f", "BORDER": "24242e", "CYAN": "22d3ee", "CYAN_DIM": "0e7c93", "MAGENTA": "f472b6", "GREEN": "34d399",
		"RED": "f87171", "TEXT_PRIMARY": "f2f4ff", "TEXT_SECOND": "a8afd0", "TEXT_MUTED": "7c84ad", "BUBBLE_USER": "0f3340", "BUBBLE_AI": "0e0e12"},
}
# O texto que fica EM CIMA do botão de destaque era fixo (04141a); agora acompanha o destaque (claro ↔ escuro).
const TEXTO_SOBRE_DESTAQUE_ANTIGO := Color("04141a")

var ui: Node = null
var movimento: String = "ligado"       # ligado | reduzido | desligado
var fps_max: int = 30
var preset_atual: String = "neutro"
var _areas: Dictionary = {}            # id -> dict de configuração
var _fx: Dictionary = {}               # id -> nó FX
var _t: float = 0.0
var _acc: float = 0.0
var _congelado_t: float = 7.0          # quadro usado quando o movimento está "reduzido"
signal mudou
signal desempenho_reduzido(motivo)

# ---- guarda de desempenho: se o computador sofrer com os efeitos, o Zenith reduz sozinho (e avisa) ----
var guarda_ativa: bool = true
var cartoes_ativos: bool = true     # v1.3 — cartões "o que a Zenith está fazendo" no meio do chat
var _graca: float = 4.0          # segundos de tolerância depois de qualquer mudança (abrir janela, trocar efeito...)
var _g_tempo: float = 0.0
var _g_quadros: int = 0
var _g_ruins: int = 0

func iniciar(ui_node: Node) -> void:
	ui = ui_node
	_carregar()

# ---------------- configuração ----------------
# Ao escolher um efeito, já vem com cores que ficam bonitas (o usuário muda depois): [cores, quantas]
const SUGESTAO := {
	"gradiente": [["#22d3ee", "#a78bfa", "#f472b6", "#fbbf24"], 3],
	"arco_iris": [["#22d3ee", "#a78bfa", "#f472b6", "#fbbf24"], 2],
	"respiracao": [["#0e7c93", "#22d3ee", "#a78bfa", "#f472b6"], 2],
	"fogo": [["#6b1200", "#ff5a00", "#ffd23f", "#fff4c2"], 4],
	"aurora": [["#22d3ee", "#34d399", "#a78bfa", "#f472b6"], 3],
	"plasma": [["#7c4dff", "#00d9ff", "#ff4fa3", "#ffd23f"], 4],
	"tinta": [["#ff4fa3", "#7c4dff", "#00d9ff", "#ffd23f"], 3],
	"borda_neon": [["#00f0ff", "#ff2bd6", "#7c4dff", "#39ff9c"], 3],
	"particulas": [["#22d3ee", "#a78bfa", "#f472b6", "#ffffff"], 3],
	"estrelas": [["#ffffff", "#bcd4ff", "#ffe9a8", "#ffffff"], 3],
	"varredura": [["#22d3ee", "#a78bfa", "#22d3ee", "#a78bfa"], 2],
}

func area_padrao() -> Dictionary:
	return {"tipo": "nenhum", "cores": ["#22d3ee", "#f472b6", "#34d399", "#a78bfa"], "ncores": 2, "velocidade": 1.0, "intensidade": 0.6, "opacidade": 1.0}

func escolher_efeito(id: String, tipo: String) -> void:
	_resetar_guarda()
	var d := area(id)
	d["tipo"] = tipo
	if SUGESTAO.has(tipo):
		d["cores"] = (SUGESTAO[tipo][0] as Array).duplicate()
		d["ncores"] = SUGESTAO[tipo][1]
	if tipo == "cor":
		d["opacidade"] = 1.0
	_aplicar_area(id)

func area(id: String) -> Dictionary:
	if not _areas.has(id):
		_areas[id] = area_padrao()
	return _areas[id]

func _carregar() -> void:
	var c := ConfigFile.new()
	if c.load(CFG) != OK:
		for a in AREAS:
			_areas[a[0]] = area_padrao()
		return
	movimento = str(c.get_value("geral", "movimento", "ligado"))
	fps_max = clampi(int(c.get_value("geral", "fps_max", 30)), 10, 60)
	guarda_ativa = bool(c.get_value("geral", "guarda", true))
	cartoes_ativos = bool(c.get_value("geral", "cartoes", true))
	preset_atual = str(c.get_value("geral", "preset", "neutro"))
	for a in AREAS:
		var d := area_padrao()
		var sec := "area_" + str(a[0])
		if c.has_section(sec):
			d["tipo"] = str(c.get_value(sec, "tipo", "nenhum"))
			d["cores"] = Array(c.get_value(sec, "cores", d["cores"]))
			while d["cores"].size() < 4:
				d["cores"].append("#ffffff")
			d["ncores"] = clampi(int(c.get_value(sec, "ncores", 2)), 2, 4)
			d["velocidade"] = float(c.get_value(sec, "velocidade", 1.0))
			d["intensidade"] = float(c.get_value(sec, "intensidade", 0.6))
			d["opacidade"] = float(c.get_value(sec, "opacidade", 1.0))
		_areas[a[0]] = d

func salvar() -> void:
	var c := ConfigFile.new()
	c.set_value("geral", "movimento", movimento)
	c.set_value("geral", "fps_max", fps_max)
	c.set_value("geral", "guarda", guarda_ativa)
	c.set_value("geral", "cartoes", cartoes_ativos)
	c.set_value("geral", "preset", preset_atual)
	for a in AREAS:
		var d: Dictionary = area(a[0])
		var sec := "area_" + str(a[0])
		for k in ["tipo", "cores", "ncores", "velocidade", "intensidade", "opacidade"]:
			c.set_value(sec, k, d[k])
	c.save(CFG)

# ---------------- camadas de efeito ----------------
# Cria a camada da área e a coloca como PRIMEIRO filho (atrás do conteúdo). `depois_de` põe logo depois de um irmão.
func registrar(id: String, pai: Node, depois_de: Node = null) -> void:
	var fx = FX.new()
	fx.area_id = id
	fx.name = "FX_" + id
	pai.add_child(fx)
	pai.move_child(fx, 0 if depois_de == null else depois_de.get_index() + 1)
	_fx[id] = fx
	_aplicar_area(id)

func _aplicar_area(id: String) -> void:
	if not _fx.has(id):
		return
	var d: Dictionary = area(id).duplicate(true)
	if movimento == "desligado" and d["tipo"] != "cor":
		d["tipo"] = "nenhum"
	_fx[id].aplicar(d)
	if movimento == "reduzido":
		_fx[id].tempo(_congelado_t)

func aplicar_tudo() -> void:
	_resetar_guarda()
	for a in AREAS:
		_aplicar_area(a[0])
	emit_signal("mudou")

func mudar_area(id: String, campo: String, valor) -> void:
	_resetar_guarda()
	area(id)[campo] = valor
	_aplicar_area(id)

func mudar_movimento(m: String) -> void:
	movimento = m
	aplicar_tudo()
	salvar()

func _resetar_guarda() -> void:
	_graca = 4.0
	_g_tempo = 0.0
	_g_quadros = 0
	_g_ruins = 0

# Chamada a cada quadro enquanto há efeito animado e a janela está em uso. Mede a taxa REAL de quadros.
func _vigiar(delta: float) -> void:
	if _graca > 0.0:
		_graca -= delta
		return
	_g_tempo += delta
	_g_quadros += 1
	if _g_tempo < 6.0:
		return
	var fps := float(_g_quadros) / _g_tempo
	_g_tempo = 0.0
	_g_quadros = 0
	_decidir(fps)

# Duas janelas seguidas (≈12 s) abaixo de 60% da meta = pesado de verdade (um soluço isolado não conta).
func _decidir(fps: float) -> void:
	if fps >= float(fps_max) * 0.6:
		_g_ruins = 0
		return
	_g_ruins += 1
	if _g_ruins >= 2:
		_g_ruins = 0
		_degradar(fps)

func _degradar(fps: float) -> void:
	var msg := ""
	if fps_max > 15:
		fps_max = 15
		msg = "Os efeitos estavam pesados para este computador (cerca de %d quadros por segundo). Reduzi para 15 quadros por segundo. " % int(fps) + \
			"Para mudar: Configurações → Estúdio → Movimento."
	elif movimento == "ligado":
		movimento = "reduzido"
		aplicar_tudo()
		msg = "Mesmo assim os efeitos pesaram. Deixei o movimento reduzido (imagem parada). Para religar: Configurações → Estúdio → Movimento."
	else:
		return
	_resetar_guarda()
	salvar()
	emit_signal("desempenho_reduzido", msg)
	if ui != null and ui.has_method("_mostrar_toast"):
		ui._mostrar_toast(msg, "aviso", 10.0)

func _process(delta: float) -> void:
	if movimento != "ligado" or ui == null:
		return
	var alguma := false
	for id in _fx:
		if _fx[id].animado():
			alguma = true
			break
	if not alguma:
		return
	# Janela minimizada/escondida: não gasta nada. Sem foco: ritmo bem menor.
	if not ui.visible or ui.mode == Window.MODE_MINIMIZED:
		_resetar_guarda()
		return
	if guarda_ativa and ui.has_focus():
		_vigiar(delta)
	else:
		_resetar_guarda()
	var alvo := fps_max if ui.has_focus() else 10
	_acc += delta
	if _acc < 1.0 / float(alvo):
		return
	_t += _acc
	_acc = 0.0
	for id in _fx:
		if _fx[id].animado():
			_fx[id].tempo(_t)

# ---------------- paleta (tema ao vivo) ----------------
func paleta_atual() -> Dictionary:
	var p := {}
	for k in CHAVES_PALETA:
		p[k] = ui.get(k)
	return p

func aplicar_preset(nome: String) -> void:
	if not PRESETS.has(nome):
		return
	var novo := {}
	for k in CHAVES_PALETA:
		novo[k] = Color.from_string(str(PRESETS[nome][k]), ui.get(k))
	preset_atual = nome
	aplicar_paleta(novo)

# Troca TODAS as cores da interface sem reiniciar: atualiza as variáveis do ui_manager (para o que for criado
# depois) e percorre o que já existe trocando cada cor antiga pela nova.
func aplicar_paleta(nova: Dictionary) -> void:
	var antiga := paleta_atual()
	var mapa: Array = []     # pares [antiga, nova]
	for k in CHAVES_PALETA:
		if nova.has(k):
			mapa.append([antiga[k] as Color, nova[k] as Color])
	var destaque_novo: Color = nova.get("CYAN", ui.get("CYAN"))
	mapa.append([TEXTO_SOBRE_DESTAQUE_ANTIGO, texto_sobre(destaque_novo)])
	for k in CHAVES_PALETA:
		if nova.has(k):
			ui.set(k, nova[k])
	_recolorir_arvore(ui, mapa, {})
	_salvar_paleta(nova)
	salvar()
	if ui.has_method("_recarregar_conversa"):
		ui.call_deferred("_recarregar_conversa")
	emit_signal("mudou")

# Luminância relativa (WCAG) e a cor de texto (escuro ou branco) com MAIS contraste sobre um fundo de destaque.
func _lum(c: Color) -> float:
	var l := c.srgb_to_linear()
	return 0.2126 * l.r + 0.7152 * l.g + 0.0722 * l.b

func texto_sobre(destaque: Color) -> Color:
	var L := _lum(destaque)
	var contra_escuro := (L + 0.05) / (_lum(TEXTO_SOBRE_DESTAQUE_ANTIGO) + 0.05)
	var contra_branco := 1.05 / (L + 0.05)
	return TEXTO_SOBRE_DESTAQUE_ANTIGO if contra_escuro >= contra_branco else Color("ffffff")

# Na abertura, o tema salvo muda o destaque mas os botões nascem com texto escuro fixo: acerta o texto sobre o destaque.
func ajustar_texto_destaque() -> void:
	var novo := texto_sobre(ui.get("CYAN"))
	if novo == TEXTO_SOBRE_DESTAQUE_ANTIGO:
		return
	_recolorir_arvore(ui, [[TEXTO_SOBRE_DESTAQUE_ANTIGO, novo]], {})

func _trocar(c: Color, mapa: Array) -> Color:
	for par in mapa:
		var a: Color = par[0]
		if absf(a.r - c.r) < 0.004 and absf(a.g - c.g) < 0.004 and absf(a.b - c.b) < 0.004:
			return Color(par[1].r, par[1].g, par[1].b, c.a)
	return c

const _NOMES_ESTILO := ["normal", "hover", "pressed", "focus", "disabled", "panel", "read_only", "fill", "background",
	"hover_pressed", "tab_selected", "tab_unselected", "tab_hovered"]
const _NOMES_COR := ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color", "font_disabled_color",
	"font_selected_color", "font_placeholder_color", "caret_color", "default_color", "font_hover_pressed_color",
	"font_uneditable_color", "font_selected_color", "selection_color"]

func _recolorir_arvore(no: Node, mapa: Array, vistos: Dictionary) -> void:
	if no is ColorRect and not (no is FX):
		no.color = _trocar(no.color, mapa)
	if no is Control and not (no is FX):
		var c: Control = no
		for n in _NOMES_ESTILO:
			if c.has_theme_stylebox_override(n):
				var sb := c.get_theme_stylebox(n)
				if sb is StyleBoxFlat and not vistos.has(sb.get_instance_id()):
					vistos[sb.get_instance_id()] = true
					sb.bg_color = _trocar(sb.bg_color, mapa)
					sb.border_color = _trocar(sb.border_color, mapa)
		for n in _NOMES_COR:
			if c.has_theme_color_override(n):
				c.add_theme_color_override(n, _trocar(c.get_theme_color(n), mapa))
		if c.self_modulate != Color.WHITE and c is TextureRect:
			c.self_modulate = _trocar(c.self_modulate, mapa)
		if c is Button and c.has_meta("ic_nome"):     # ícone acompanha a cor do texto do botão
			Icones.aplicar(c, str(c.get_meta("ic_nome")), c.get_theme_color("font_color"), int(c.get_meta("ic_tam", 18)))
	for filho in no.get_children():
		_recolorir_arvore(filho, mapa, vistos)

func _salvar_paleta(p: Dictionary) -> void:
	var cfg := ConfigFile.new()
	cfg.load(ui.get("TEMA_CFG"))
	for k in CHAVES_PALETA:
		if p.has(k):
			cfg.set_value("cores", k, "#" + (p[k] as Color).to_html(false))
	cfg.save(ui.get("TEMA_CFG"))

# ---------------- Meus temas (salvar, aplicar, compartilhar) ----------------
# Um tema = a paleta + o efeito de cada área. NÃO leva movimento/FPS (isso depende do computador de cada um).
# Arquivos em user://temas/<nome>.json. Tema que vem de fora (importar) é SANEADO: só cores #rrggbb, só efeitos
# conhecidos, números limitados — um arquivo malicioso não consegue fazer nada além de pintar a tela.
const TEMAS_DIR := "user://temas/"
const TEMA_MAX_BYTES := 20000

func nome_limpo(nome: String) -> String:
	var s := nome.strip_edges()
	var saida := ""
	for ch in s:
		saida += ch if (ch.unicode_at(0) >= 32 and ch not in ["/", "\\", ":", "*", "?", "\"", "<", ">", "|"]) else " "
	return saida.strip_edges().left(40)

func _arquivo_do_tema(nome: String) -> String:
	var slug := ""
	for ch in nome_limpo(nome).to_lower():
		var c := ch.unicode_at(0)
		slug += ch if ((c >= 97 and c <= 122) or (c >= 48 and c <= 57)) else "_"
	return TEMAS_DIR + slug + ".json"

func tema_atual(nome: String) -> Dictionary:
	var pal := {}
	for k in CHAVES_PALETA:
		pal[k] = "#" + (ui.get(k) as Color).to_html(false)
	var areas := {}
	for a in AREAS:
		areas[a[0]] = area(a[0]).duplicate(true)
	return {"zenith_tema": 1, "nome": nome_limpo(nome), "paleta": pal, "areas": areas}

func _hex_ok(v) -> bool:
	if typeof(v) != TYPE_STRING:
		return false
	var s := String(v).trim_prefix("#")
	if s.length() != 6:
		return false
	for ch in s.to_lower():
		if not "0123456789abcdef".contains(ch):
			return false
	return true

# Devolve {} se não for um tema Zenith válido; senão uma cópia só com o que é seguro.
func sanear_tema(d) -> Dictionary:
	if typeof(d) != TYPE_DICTIONARY or int(d.get("zenith_tema", 0)) != 1:
		return {}
	var nome := nome_limpo(str(d.get("nome", "")))
	if nome == "":
		return {}
	var pal := {}
	var p: Dictionary = d.get("paleta", {}) if typeof(d.get("paleta", {})) == TYPE_DICTIONARY else {}
	for k in CHAVES_PALETA:
		if p.has(k) and _hex_ok(p[k]):
			pal[k] = "#" + String(p[k]).trim_prefix("#").to_lower()
	var tipos_validos := ["nenhum", "cor"]
	for e in EFEITOS:
		tipos_validos.append(e[0])
	var areas := {}
	var a_in: Dictionary = d.get("areas", {}) if typeof(d.get("areas", {})) == TYPE_DICTIONARY else {}
	for a in AREAS:
		var id: String = a[0]
		if not a_in.has(id) or typeof(a_in[id]) != TYPE_DICTIONARY:
			continue
		var src: Dictionary = a_in[id]
		var tipo := str(src.get("tipo", "nenhum"))
		if tipo not in tipos_validos:
			tipo = "nenhum"
		var cores: Array = []
		var cs = src.get("cores", [])
		for i in 4:     # cada posição é mantida; cor inválida vira branco (não desloca as outras)
			if typeof(cs) == TYPE_ARRAY and i < cs.size() and _hex_ok(cs[i]):
				cores.append("#" + String(cs[i]).trim_prefix("#").to_lower())
			else:
				cores.append("#ffffff")
		areas[id] = {"tipo": tipo, "cores": cores, "ncores": clampi(int(src.get("ncores", 2)), 2, 4),
			"velocidade": clampf(float(src.get("velocidade", 1.0)), 0.0, 3.0),
			"intensidade": clampf(float(src.get("intensidade", 0.6)), 0.0, 1.0),
			"opacidade": clampf(float(src.get("opacidade", 1.0)), 0.1, 1.0)}
	if pal.is_empty() and areas.is_empty():
		return {}
	return {"zenith_tema": 1, "nome": nome, "paleta": pal, "areas": areas}

# [ok, mensagem]
func salvar_tema(nome: String) -> Array:
	var limpo := nome_limpo(nome)
	if limpo == "":
		return [false, "Dê um nome ao tema."]
	DirAccess.make_dir_recursive_absolute(TEMAS_DIR)
	var f := FileAccess.open(_arquivo_do_tema(limpo), FileAccess.WRITE)
	if f == null:
		return [false, "Não consegui salvar o tema (pasta sem permissão?)."]
	f.store_string(JSON.stringify(tema_atual(limpo), "\t"))
	f.close()
	return [true, "Tema \"%s\" salvo." % limpo]

func listar_temas() -> Array:
	var out: Array = []
	var d := DirAccess.open(TEMAS_DIR)
	if d == null:
		return out
	for arq in d.get_files():
		if not arq.ends_with(".json"):
			continue
		var r := _ler_tema(TEMAS_DIR + arq)
		if not r.is_empty():
			out.append({"nome": r["nome"], "arquivo": TEMAS_DIR + arq})
	out.sort_custom(func(a, b): return str(a["nome"]).to_lower() < str(b["nome"]).to_lower())
	return out

# JSON.parse_string imprime ERROR no log quando o texto não é JSON; assim é silencioso (devolve null).
func _json(texto: String):
	var j := JSON.new()
	if j.parse(texto) != OK:
		return null
	return j.data

func _ler_tema(caminho: String) -> Dictionary:
	if not FileAccess.file_exists(caminho):
		return {}
	var f := FileAccess.open(caminho, FileAccess.READ)
	if f == null or f.get_length() > TEMA_MAX_BYTES:
		return {}
	return sanear_tema(_json(f.get_as_text()))

func aplicar_tema(t: Dictionary) -> void:
	for id in t.get("areas", {}):
		_areas[id] = (t["areas"][id] as Dictionary).duplicate(true)
	preset_atual = "personalizado"
	var nova := {}
	for k in t.get("paleta", {}):
		nova[k] = Color.from_string(str(t["paleta"][k]), ui.get(k))
	if nova.is_empty():
		aplicar_tudo()
		salvar()
	else:
		aplicar_paleta(nova)        # já salva e recolore
		aplicar_tudo()
		salvar()

func carregar_tema(caminho: String) -> Array:
	var t := _ler_tema(caminho)
	if t.is_empty():
		return [false, "Esse arquivo de tema não está válido."]
	aplicar_tema(t)
	return [true, "Tema \"%s\" aplicado." % t["nome"]]

func apagar_tema(caminho: String) -> bool:
	if not caminho.begins_with(TEMAS_DIR) or not caminho.ends_with(".json"):
		return false
	return DirAccess.remove_absolute(caminho) == OK

func exportar_texto(caminho: String) -> String:
	var t := _ler_tema(caminho)
	return "" if t.is_empty() else JSON.stringify(t, "\t")

# Importa um tema colado (texto). Salva em Meus temas, mas NÃO aplica — a pessoa vê antes de decidir.
func importar_texto(texto: String) -> Array:
	if texto.strip_edges() == "":
		return [false, "A área de transferência está vazia. Copie o tema (o texto que começa com {) e tente de novo."]
	if texto.length() > TEMA_MAX_BYTES:
		return [false, "Esse texto é grande demais para ser um tema."]
	var t := sanear_tema(_json(texto))
	if t.is_empty():
		return [false, "Isso não parece um tema do Zenith."]
	DirAccess.make_dir_recursive_absolute(TEMAS_DIR)
	var f := FileAccess.open(_arquivo_do_tema(str(t["nome"])), FileAccess.WRITE)
	if f == null:
		return [false, "Não consegui salvar o tema importado."]
	f.store_string(JSON.stringify(t, "\t"))
	f.close()
	return [true, "Tema \"%s\" importado. Clique em Aplicar para ver como fica." % t["nome"]]

# ---------------- contraste (cores personalizadas que deixam o texto ilegível) ----------------
func contraste(a: Color, b: Color) -> float:
	var la := _lum(a)
	var lb := _lum(b)
	return (maxf(la, lb) + 0.05) / (minf(la, lb) + 0.05)

func avisos_contraste() -> Array:
	var out: Array = []
	var pares := [
		["texto principal", "TEXT_PRIMARY", "o fundo da janela", "BG_BASE", 4.5], ["texto principal", "TEXT_PRIMARY", "os painéis", "BG_PANEL", 4.5],
		["texto principal", "TEXT_PRIMARY", "os cartões", "BG_SURFACE_2", 4.5], ["texto principal", "TEXT_PRIMARY", "o balão seu", "BUBBLE_USER", 4.5],
		["texto principal", "TEXT_PRIMARY", "o balão da IA", "BUBBLE_AI", 4.5], ["texto secundário", "TEXT_SECOND", "os painéis", "BG_PANEL", 3.0],
		["texto secundário", "TEXT_SECOND", "o fundo da janela", "BG_BASE", 3.0],
	]
	for p in pares:
		var r := contraste(ui.get(p[1]), ui.get(p[3]))
		if r < float(p[4]):
			out.append("O %s fica difícil de ler sobre %s (contraste %.1f; o ideal é %.1f ou mais)." % [p[0], p[2], r, p[4]])
	var destaque: Color = ui.get("CYAN")
	var r2 := contraste(texto_sobre(destaque), destaque)
	if r2 < 3.0:
		out.append("O texto dos botões de destaque fica difícil de ler (contraste %.1f)." % r2)
	return out
