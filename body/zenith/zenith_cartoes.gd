extends RefCounted
# ZENITH — cartões de atividade no meio do chat: "Adicionando à memória…", "Executando código…", "Pesquisando na web…".
# Um cartão por tarefa (o Cérebro reaproveita o `id` quando o estado muda). Clicando, abre e mostra O QUE foi feito:
# o código, o fato salvo, o que foi pesquisado, o resultado. O texto já chega mascarado (sem chaves) do Cérebro.
# Desligável em Estúdio → Chat. Com "movimento reduzido/desligado" o ícone de carregando não gira.

const Icones := preload("res://zenith_icones.gd")
const ICONE_DO_TIPO := {"memoria": "memoria", "busca": "globo", "codigo": "codigo", "terminal": "terminal", "imagem": "imagem",
	"video": "video", "documento": "caderno", "pasta": "pasta", "biblioteca": "biblioteca", "olho": "olho",
	"programa": "comando", "info": "info"}
const MAX_CARTOES := 60

var ui: Node
var _cartoes: Dictionary = {}     # id -> widgets
var _ordem: Array = []
var _mono: SystemFont
var abrir_ao_criar: bool = false      # (testes visuais) cartões já nascem abertos

func iniciar(ui_node: Node) -> void:
	ui = ui_node
	_mono = SystemFont.new()
	_mono.font_names = PackedStringArray(["Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New", "monospace"])

func abrir_todos() -> void:      # (usado nos testes visuais)
	for id in _cartoes:
		var c: Dictionary = _cartoes[id]
		if c["tem_detalhe"] and is_instance_valid(c["raiz"]):
			c["corpo"].visible = true
			c["seta"].text = "▾"

func limpar() -> void:      # a conversa foi recarregada: os cartões antigos saíram da tela junto com os balões
	_cartoes.clear()
	_ordem.clear()

func atualizar(d: Dictionary) -> void:
	if ui == null or not ui.aparencia.cartoes_ativos or ui.chat_log == null:
		return
	var id := str(d.get("id", ""))
	if id == "":
		return
	var c: Dictionary = _cartoes.get(id, {})
	if c.is_empty() or not is_instance_valid(c["raiz"]):
		c = _criar()
		_cartoes[id] = c
		_ordem.append(id)
		ui.chat_log.add_child(c["raiz"])
		_podar()
	_preencher(c, d)
	if abrir_ao_criar and c["tem_detalhe"]:
		c["corpo"].visible = true
		c["seta"].text = "▾"
	ui.call_deferred("_rolar_chat_para_baixo")

func _podar() -> void:
	while _ordem.size() > MAX_CARTOES:
		var velho: String = _ordem.pop_front()
		_cartoes.erase(velho)

func _criar() -> Dictionary:
	var c := {}
	var raiz := PanelContainer.new()
	raiz.size_flags_horizontal = Control.SIZE_FILL
	var fundo: Color = ui.BG_SURFACE_2
	raiz.add_theme_stylebox_override("panel", ui._panel_style(Color(fundo.r, fundo.g, fundo.b, 0.85), 10, ui.BORDER, 1))
	var m := MarginContainer.new()
	m.add_theme_constant_override("margin_left", 10)
	m.add_theme_constant_override("margin_right", 10)
	m.add_theme_constant_override("margin_top", 4)
	m.add_theme_constant_override("margin_bottom", 4)
	raiz.add_child(m)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	m.add_child(col)
	# --- cabeçalho (clicável) ---
	var linha := HBoxContainer.new()
	linha.add_theme_constant_override("separation", 6)
	col.add_child(linha)
	var cab := Button.new()
	cab.flat = true
	cab.alignment = HORIZONTAL_ALIGNMENT_LEFT
	cab.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cab.clip_text = true
	cab.focus_mode = Control.FOCUS_NONE
	cab.add_theme_font_size_override("font_size", 13)
	for est in ["normal", "pressed", "focus"]:
		cab.add_theme_stylebox_override(est, StyleBoxEmpty.new())
	var hov := StyleBoxFlat.new()
	hov.bg_color = Color(ui.BG_SURFACE_3.r, ui.BG_SURFACE_3.g, ui.BG_SURFACE_3.b, 0.5)
	hov.set_corner_radius_all(6)
	cab.add_theme_stylebox_override("hover", hov)
	linha.add_child(cab)
	var estado_ic := TextureRect.new()
	estado_ic.custom_minimum_size = Vector2(16, 16)
	estado_ic.pivot_offset = Vector2(8, 8)
	estado_ic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	estado_ic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	estado_ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	estado_ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	linha.add_child(estado_ic)
	var seta := Label.new()
	seta.text = "▸"
	seta.add_theme_font_size_override("font_size", 12)
	seta.add_theme_color_override("font_color", ui.TEXT_MUTED)
	linha.add_child(seta)
	# --- corpo (abre ao clicar) ---
	var corpo := VBoxContainer.new()
	corpo.visible = false
	corpo.add_theme_constant_override("separation", 4)
	col.add_child(corpo)
	var caixa := PanelContainer.new()
	caixa.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_BASE, 8, ui.BORDER, 1))
	corpo.add_child(caixa)
	var rolo := ScrollContainer.new()
	rolo.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	rolo.custom_minimum_size = Vector2(0, 60)
	caixa.add_child(rolo)
	var mm := MarginContainer.new()
	mm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for lado in ["left", "right", "top", "bottom"]:
		mm.add_theme_constant_override("margin_" + lado, 8)
	rolo.add_child(mm)
	var texto := Label.new()
	texto.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	texto.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	texto.add_theme_font_override("font", _mono)
	texto.add_theme_font_size_override("font_size", 12)
	texto.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	mm.add_child(texto)
	var barra := HBoxContainer.new()
	corpo.add_child(barra)
	var copiar: Button = ui._make_button("Copiar", ui.BG_SURFACE_3, ui.BORDER, ui.TEXT_PRIMARY)
	copiar.custom_minimum_size = Vector2(90, 26)
	Icones.aplicar(copiar, "copiar", ui.TEXT_PRIMARY, 14)
	barra.add_child(copiar)
	c = {"raiz": raiz, "cab": cab, "estado_ic": estado_ic, "seta": seta, "corpo": corpo, "rolo": rolo, "texto": texto,
		"tween": null, "tem_detalhe": false}
	cab.pressed.connect(func():
		if c["tem_detalhe"]:
			c["corpo"].visible = not c["corpo"].visible
			c["seta"].text = "▾" if c["corpo"].visible else "▸"
			ui.call_deferred("_rolar_chat_para_baixo"))
	copiar.pressed.connect(func(): DisplayServer.clipboard_set(c["texto"].text))
	return c

func _preencher(c: Dictionary, d: Dictionary) -> void:
	var estado := str(d.get("estado", "ok"))
	var cor: Color = ui.CYAN if estado == "rodando" else (ui.RED if estado == "erro" else ui.TEXT_SECOND)
	var cab: Button = c["cab"]
	cab.text = str(d.get("titulo", "")) + ("…" if estado == "rodando" else "")
	cab.add_theme_color_override("font_color", ui.RED if estado == "erro" else ui.TEXT_SECOND)
	cab.add_theme_color_override("font_hover_color", ui.TEXT_PRIMARY)
	Icones.aplicar(cab, ICONE_DO_TIPO.get(str(d.get("tipo", "info")), "info"), cab.get_theme_color("font_color"), 16)
	# ícone de estado: gira enquanto roda
	var ic: TextureRect = c["estado_ic"]
	if c["tween"] != null:
		(c["tween"] as Tween).kill()
		c["tween"] = null
	ic.rotation = 0.0
	match estado:
		"rodando":
			ic.texture = Icones.tex("atualizar")
			ic.self_modulate = ui.CYAN
			if ui.aparencia.movimento == "ligado":
				var tw := ic.create_tween().set_loops()
				tw.tween_property(ic, "rotation", TAU, 1.1).from(0.0)
				c["tween"] = tw
		"erro":
			ic.texture = Icones.tex("aviso")
			ic.self_modulate = ui.RED
		_:
			ic.texture = Icones.tex("ok")
			ic.self_modulate = ui.GREEN
	var det := str(d.get("detalhe", ""))
	c["tem_detalhe"] = det != ""
	c["seta"].visible = det != ""
	c["texto"].text = det
	var linhas := det.count("\n") + 1 + int(det.length() / 90)
	(c["rolo"] as ScrollContainer).custom_minimum_size.y = clampi(linhas * 17 + 20, 56, 280)
	cab.tooltip_text = "Clique para ver o que foi feito" if det != "" else ""
