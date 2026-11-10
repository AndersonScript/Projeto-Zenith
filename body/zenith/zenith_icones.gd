extends RefCounted
# ZENITH — ícones próprios (51 SVGs originais em res://assets/icones/, traço branco 24x24).
# Pintamos pela cor do texto do botão (modulate), então o mesmo ícone serve para qualquer tema.
#   Icones.aplicar(botao, "microfone", cor)      Icones.tex("microfone")      Icones.separar("🧠  Memórias")

const PASTA := "res://assets/icones/"
static var _cache: Dictionary = {}

# Símbolo no começo do texto -> ícone próprio. (Os emojis saem; o ícone entra.)
const POR_SIMBOLO := {
	"🧠": "memoria", "⚙": "ajustes", "◈": "mover", "🔴": "olho", "🖱": "mover", "📋": "copiar", "✓": "ok",
	"📎": "anexo", "🎙": "microfone", "✕": "fechar", "⚠": "aviso", "👁": "olho", "🙈": "olho", "🔊": "alto_falante",
	"➕": "mais", "🔄": "atualizar", "💾": "salvar", "↺": "desfazer", "▶": "tocar", "⏹": "parar", "★": "estrela",
	"☆": "estrela", "🔍": "buscar", "✎": "editar", "✦": "faisca", "📄": "caderno", "◆": "faisca", "⭐": "estrela",
	"💬": "conversa", "🖼": "imagem", "⏺": "microfone", "◉": "microfone", "…": "",
	"📁": "pasta", "📚": "biblioteca", "🎞": "video", "💻": "codigo",         # v1.6: Biblioteca/Projetos
}

static func existe(nome: String) -> bool:
	return ResourceLoader.exists(PASTA + nome + ".svg")

static func tex(nome: String) -> Texture2D:
	if _cache.has(nome):
		return _cache[nome]
	var caminho := PASTA + nome + ".svg"
	var t: Texture2D = null
	if ResourceLoader.exists(caminho):
		t = load(caminho) as Texture2D
	_cache[nome] = t
	return t

# "🧠  Memórias" -> ["memoria", "Memórias"]  ·  sem símbolo conhecido -> ["", texto]
static func separar(texto: String) -> Array:
	if texto.is_empty():
		return ["", texto]
	var primeiro := texto.substr(0, 1)
	if POR_SIMBOLO.has(primeiro):
		var resto := texto.substr(1).strip_edges().trim_prefix("\ufe0f").strip_edges()
		var nome: String = POR_SIMBOLO[primeiro]
		if primeiro == "■" or texto.begins_with("■"):
			nome = "fixar" if resto.contains("Fixar") else "parar"
		return [nome, resto]
	if texto.begins_with("■"):
		var r := texto.substr(1).strip_edges()
		return ["fixar" if r.contains("Fixar") else "parar", r]
	return ["", texto]

static func aplicar(btn: Button, nome: String, cor: Color, tam: int = 18) -> void:
	var t := tex(nome)
	if t == null:
		return
	btn.icon = t
	btn.expand_icon = false
	btn.icon_alignment = HORIZONTAL_ALIGNMENT_LEFT
	btn.add_theme_constant_override("icon_max_width", tam)
	btn.add_theme_constant_override("h_separation", 8)
	if btn.text != "":
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	btn.add_theme_color_override("icon_normal_color", cor)
	btn.add_theme_color_override("icon_hover_color", cor.lightened(0.25))
	btn.add_theme_color_override("icon_pressed_color", cor.lightened(0.4))
	btn.add_theme_color_override("icon_focus_color", cor)
	btn.add_theme_color_override("icon_disabled_color", cor.darkened(0.5))
	btn.set_meta("ic_nome", nome)
	btn.set_meta("ic_tam", tam)

# Põe texto num botão trocando o símbolo/emoji do começo por um ícone próprio. Só ícone = centralizado.
static func texto_com_icone(btn: Button, texto: String, cor: Color, tam: int = 18) -> void:
	var r := separar(texto)
	btn.text = r[1]
	if r[0] != "" and existe(r[0]):
		aplicar(btn, r[0], cor, tam)
		if String(r[1]).is_empty():
			btn.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
			btn.alignment = HORIZONTAL_ALIGNMENT_CENTER
	elif btn.has_meta("ic_nome"):     # antes tinha ícone e agora o texto não tem símbolo: tira o ícone
		btn.icon = null
		btn.remove_meta("ic_nome")

# Só o ícone, centralizado (botões quadradinhos: lixeira, fechar...).
static func so_icone(btn: Button, nome: String, cor: Color, tam: int = 18) -> void:
	btn.text = ""
	aplicar(btn, nome, cor, tam)
	btn.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
	btn.alignment = HORIZONTAL_ALIGNMENT_CENTER

static func rect(nome: String, cor: Color, tam: int = 18) -> TextureRect:
	var r := TextureRect.new()
	r.texture = tex(nome)
	r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	r.custom_minimum_size = Vector2(tam, tam)
	r.self_modulate = cor
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return r
