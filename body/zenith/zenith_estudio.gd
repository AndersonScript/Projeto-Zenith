extends RefCounted
# ZENITH — página "Estúdio" das Configurações: o usuário escolhe tudo, ao vivo.
#   1. Tema pronto (ponto de partida)   2. Cores soltas   3. Fundo/efeito de CADA área   4. Movimento
# Só desenha controles; quem aplica é o zenith_aparencia.gd (ap). Nada aqui toca em dados do usuário.

const Icones := preload("res://zenith_icones.gd")

static func montar(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Estúdio de Aparência")
	ui._hint(v, "Aqui o visual é seu. Escolha um tema pronto como ponto de partida e mude o que quiser: cada parte da janela " +
		"(fundo, histórico, barra de cima, chat, caixa de digitar) pode ter sua própria cor ou efeito animado. " +
		"Tudo muda na hora, sem reiniciar, e fica salvo.")
	_temas(ui, ap, v)
	_meus_temas(ui, ap, v)
	_cores(ui, ap, v)
	_areas(ui, ap, v)
	_movimento(ui, ap, v)
	_chat(ui, ap, v)
	var reset: Button = ui._make_button("Voltar ao tema neutro (limpa todos os efeitos)", ui.BG_SURFACE_2, Color("5a1f1f"), ui.RED)
	reset.pressed.connect(func():
		for a in ap.AREAS:
			ap.escolher_efeito(a[0], "nenhum")
		ap.aplicar_preset("neutro")
		ap.salvar()
		_refazer(ui, ap, v))
	v.add_child(reset)

static func _refazer(ui: Node, ap: Node, v: VBoxContainer) -> void:
	for f in v.get_children():
		f.queue_free()
	montar.call_deferred(ui, ap, v)

# ---------------- 1. temas ----------------
static func _temas(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Tema pronto")
	var grade := GridContainer.new()
	grade.columns = 5
	grade.add_theme_constant_override("h_separation", 8)
	grade.add_theme_constant_override("v_separation", 8)
	for id in ap.PRESETS:
		var p: Dictionary = ap.PRESETS[id]
		var b := Button.new()
		b.text = str(p["nome"])
		b.custom_minimum_size = Vector2(120, 54)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.clip_text = true
		var cor_bg := Color.from_string(str(p["BG_SURFACE_2"]), Color.BLACK)
		var acento := Color.from_string(str(p["CYAN"]), Color.WHITE)
		var texto := Color.from_string(str(p["TEXT_PRIMARY"]), Color.WHITE)
		for estado in ["normal", "hover", "pressed"]:
			var sb: StyleBoxFlat = ui._panel_style(cor_bg if estado != "hover" else cor_bg.lightened(0.08), 10, acento, 2 if id == ap.preset_atual else 1)
			b.add_theme_stylebox_override(estado, sb)
		b.add_theme_color_override("font_color", texto)
		b.add_theme_color_override("font_hover_color", texto)
		b.pressed.connect(func():
			ap.aplicar_preset(id)
			ap.salvar())
		grade.add_child(b)
	v.add_child(grade)

# ---------------- 1b. meus temas ----------------
static func _meus_temas(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Meus temas")
	ui._hint(v, "Salve o seu visual com um nome, volte a ele quando quiser e compartilhe com amigos (copiar e colar). " +
		"Um tema guarda as cores e o efeito de cada parte — não guarda o movimento, que depende do computador.")
	var linha := HBoxContainer.new()
	linha.add_theme_constant_override("separation", 8)
	var nome := LineEdit.new()
	nome.placeholder_text = "Nome do tema"
	nome.max_length = 40
	nome.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nome.add_theme_stylebox_override("normal", ui._panel_style(ui.BG_BASE, 6))
	nome.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	nome.add_theme_color_override("font_placeholder_color", ui.TEXT_MUTED)
	linha.add_child(nome)
	var status := Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.add_theme_font_size_override("font_size", 11)
	status.add_theme_color_override("font_color", ui.TEXT_SECOND)
	var lista := VBoxContainer.new()
	lista.add_theme_constant_override("separation", 4)
	var salvar: Button = ui._make_button("Salvar tema atual", ui.CYAN, ui.CYAN_DIM, Color("04141a"))
	Icones.aplicar(salvar, "salvar", Color("04141a"))
	salvar.pressed.connect(func():
		var r: Array = ap.salvar_tema(nome.text)
		_dizer(ui, status, str(r[1]), bool(r[0]))
		if bool(r[0]):
			nome.text = ""
			_popular_temas(ui, ap, lista, status))
	linha.add_child(salvar)
	v.add_child(linha)
	var importar: Button = ui._make_button("Importar tema (cole o texto copiado)", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	Icones.aplicar(importar, "baixar", ui.TEXT_PRIMARY)
	importar.pressed.connect(func():
		var r: Array = ap.importar_texto(DisplayServer.clipboard_get())
		_dizer(ui, status, str(r[1]), bool(r[0]))
		if bool(r[0]):
			_popular_temas(ui, ap, lista, status))
	v.add_child(importar)
	v.add_child(status)
	v.add_child(lista)
	_popular_temas(ui, ap, lista, status)

static func _dizer(ui: Node, lbl: Label, texto: String, ok: bool) -> void:
	if is_instance_valid(lbl):
		lbl.text = texto
		lbl.add_theme_color_override("font_color", ui.TEXT_SECOND if ok else ui.RED)

static func _popular_temas(ui: Node, ap: Node, lista: VBoxContainer, status: Label) -> void:
	for f in lista.get_children():
		f.queue_free()
	var temas: Array = ap.listar_temas()
	if temas.is_empty():
		var vazio := Label.new()
		vazio.text = "Você ainda não salvou nenhum tema."
		vazio.add_theme_font_size_override("font_size", 11)
		vazio.add_theme_color_override("font_color", ui.TEXT_MUTED)
		lista.add_child(vazio)
		return
	for tm in temas:
		var caminho: String = tm["arquivo"]
		var l := HBoxContainer.new()
		l.add_theme_constant_override("separation", 6)
		var n := Label.new()
		n.text = str(tm["nome"])
		n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		n.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
		l.add_child(n)
		var ap_btn: Button = ui._make_button("Aplicar", ui.BG_SURFACE_3, ui.BORDER, ui.TEXT_PRIMARY)
		ap_btn.custom_minimum_size = Vector2(86, 28)
		ap_btn.pressed.connect(func():
			var r: Array = ap.carregar_tema(caminho)
			_dizer(ui, status, str(r[1]), bool(r[0])))
		l.add_child(ap_btn)
		var cp: Button = ui._make_button("Copiar", ui.BG_SURFACE_3, ui.BORDER, ui.TEXT_PRIMARY)
		Icones.aplicar(cp, "copiar", ui.TEXT_PRIMARY, 16)
		cp.custom_minimum_size = Vector2(86, 28)
		cp.tooltip_text = "Copia o tema como texto, para colar numa conversa ou mandar a um amigo"
		cp.pressed.connect(func():
			DisplayServer.clipboard_set(ap.exportar_texto(caminho))
			_dizer(ui, status, "Tema copiado! Cole numa conversa para compartilhar.", true))
		l.add_child(cp)
		var ap_del: Button = ui._make_button("", Color(0, 0, 0, 0), ui.BG_SURFACE_3, ui.TEXT_MUTED)
		Icones.so_icone(ap_del, "lixeira", ui.TEXT_MUTED, 16)
		ap_del.custom_minimum_size = Vector2(30, 28)
		ap_del.tooltip_text = "Apagar este tema salvo"
		ap_del.pressed.connect(func():
			ap.apagar_tema(caminho)
			_popular_temas(ui, ap, lista, status))
		l.add_child(ap_del)
		lista.add_child(l)

# ---------------- 2. cores soltas ----------------
static func _cores(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Cores")
	ui._hint(v, "Mude uma cor só. (Escolher um tema pronto volta todas as cores para as dele.)")
	var itens := [
		["Destaque (botões, links)", "CYAN"], ["Fundo da janela", "BG_BASE"], ["Painéis (histórico, barras)", "BG_PANEL"],
		["Cartões e caixas", "BG_SURFACE_2"], ["Texto principal", "TEXT_PRIMARY"], ["Texto secundário", "TEXT_SECOND"],
		["Balão seu", "BUBBLE_USER"], ["Balão da IA", "BUBBLE_AI"],
	]
	var grade := GridContainer.new()
	grade.columns = 2
	grade.add_theme_constant_override("h_separation", 16)
	grade.add_theme_constant_override("v_separation", 6)
	for it in itens:
		var chave: String = it[1]
		var linha := HBoxContainer.new()
		linha.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var rot := Label.new()
		rot.text = it[0]
		rot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		rot.add_theme_color_override("font_color", ui.TEXT_SECOND)
		linha.add_child(rot)
		var pk := ColorPickerButton.new()
		pk.custom_minimum_size = Vector2(64, 28)
		pk.edit_alpha = false
		pk.color = ui.get(chave)
		pk.popup_closed.connect(func():
			var nova: Dictionary = {}
			nova[chave] = pk.color
			if chave == "BG_PANEL":
				nova["BG_SURFACE"] = pk.color
			ap.aplicar_paleta(nova))
		linha.add_child(pk)
		grade.add_child(linha)
	v.add_child(grade)
	var aviso_contraste := Label.new()
	aviso_contraste.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	aviso_contraste.add_theme_font_size_override("font_size", 11)
	aviso_contraste.add_theme_color_override("font_color", Color("fbbf24"))
	v.add_child(aviso_contraste)
	var atualizar := func():
		if is_instance_valid(aviso_contraste):
			var av: Array = ap.avisos_contraste()
			aviso_contraste.text = "" if av.is_empty() else "Atenção: " + " ".join(av) + " Ajuste as cores ou escolha um tema pronto."
			aviso_contraste.visible = not av.is_empty()
	atualizar.call()
	ap.mudou.connect(atualizar)

# ---------------- 3. fundo e efeito por área ----------------
static func _areas(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Fundo e efeitos de cada parte")
	ui._hint(v, "Escolha um efeito animado, um gradiente ou uma cor sólida. \"Opacidade\" baixa deixa o efeito como um vidro por cima da cor do tema.")
	for a in ap.AREAS:
		v.add_child(_cartao_area(ui, ap, a[0], a[1]))

static func _cartao_area(ui: Node, ap: Node, id: String, nome: String) -> Control:
	var cartao := PanelContainer.new()
	cartao.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_SURFACE_2, 10, ui.BORDER, 1))
	var m := MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + lado, 10)
	cartao.add_child(m)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	m.add_child(col)
	var titulo := Label.new()
	titulo.text = nome
	titulo.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	col.add_child(titulo)

	var d: Dictionary = ap.area(id)
	var sel := OptionButton.new()
	var tipos: Array = []
	for i in ap.EFEITOS.size():
		sel.add_item(str(ap.EFEITOS[i][1]), i)
		tipos.append(ap.EFEITOS[i][0])
		if ap.EFEITOS[i][0] == d["tipo"]:
			sel.select(i)
	col.add_child(sel)

	var painel_ajustes := VBoxContainer.new()
	painel_ajustes.add_theme_constant_override("separation", 4)
	col.add_child(painel_ajustes)

	# cores (4 seletores + quantas usar)
	var linha_cores := HBoxContainer.new()
	linha_cores.add_theme_constant_override("separation", 6)
	painel_ajustes.add_child(linha_cores)
	var rot := Label.new()
	rot.text = "Cores"
	rot.custom_minimum_size.x = 90
	rot.add_theme_color_override("font_color", ui.TEXT_SECOND)
	linha_cores.add_child(rot)
	var pickers: Array = []
	for i in 4:
		var pk := ColorPickerButton.new()
		pk.custom_minimum_size = Vector2(46, 26)
		pk.edit_alpha = false
		pk.color = Color.from_string(str(d["cores"][i]), Color.WHITE)
		pk.popup_closed.connect(func():
			var cs: Array = ap.area(id)["cores"]
			cs[i] = "#" + pk.color.to_html(false)
			ap.mudar_area(id, "cores", cs)
			ap.salvar())
		linha_cores.add_child(pk)
		pickers.append(pk)
	var qtd := OptionButton.new()
	for n in [2, 3, 4]:
		qtd.add_item(str(n) + " cores", n)
	qtd.select(clampi(int(d["ncores"]), 2, 4) - 2)
	qtd.item_selected.connect(func(idx):
		ap.mudar_area(id, "ncores", qtd.get_item_id(idx))
		ap.salvar())
	linha_cores.add_child(qtd)

	var deslizantes := [["Velocidade", "velocidade", 0.0, 3.0], ["Intensidade", "intensidade", 0.0, 1.0], ["Opacidade", "opacidade", 0.1, 1.0]]
	for s in deslizantes:
		var linha := HBoxContainer.new()
		var r := Label.new()
		r.text = s[0]
		r.custom_minimum_size.x = 90
		r.add_theme_color_override("font_color", ui.TEXT_SECOND)
		linha.add_child(r)
		var sl := HSlider.new()
		sl.min_value = s[2]
		sl.max_value = s[3]
		sl.step = 0.05
		sl.value = float(d[s[1]])
		sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		sl.custom_minimum_size.y = 20
		var campo: String = s[1]
		sl.value_changed.connect(func(x): ap.mudar_area(id, campo, x))
		sl.drag_ended.connect(func(_c): ap.salvar())
		linha.add_child(sl)
		painel_ajustes.add_child(linha)

	var atualizar_visivel := func(tipo: String):
		painel_ajustes.visible = tipo != "nenhum"
	atualizar_visivel.call(str(d["tipo"]))
	sel.item_selected.connect(func(idx):
		var tipo: String = tipos[idx]
		ap.escolher_efeito(id, tipo)
		var nd: Dictionary = ap.area(id)
		for i in 4:
			pickers[i].color = Color.from_string(str(nd["cores"][i]), Color.WHITE)
		qtd.select(clampi(int(nd["ncores"]), 2, 4) - 2)
		atualizar_visivel.call(tipo)
		ap.salvar())
	return cartao

# ---------------- 5. chat ----------------
static func _chat(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Chat")
	var cartoes := CheckBox.new()
	cartoes.text = "Mostrar no chat o que a Zenith está fazendo (memória, código, pesquisa, vídeo...) — clique no aviso para ver os detalhes"
	cartoes.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cartoes.button_pressed = ap.cartoes_ativos
	cartoes.add_theme_color_override("font_color", ui.TEXT_SECOND)
	cartoes.toggled.connect(func(ligado):
		ap.cartoes_ativos = ligado
		ap.salvar())
	v.add_child(cartoes)

# ---------------- 4. movimento ----------------
static func _movimento(ui: Node, ap: Node, v: VBoxContainer) -> void:
	ui._section(v, "Movimento")
	ui._hint(v, "Os efeitos são suaves e lentos (nada pisca). Se a luz em movimento incomodar você, escolha \"Reduzido\" ou \"Desligado\". " +
		"Dica: em computador sem placa de vídeo, 30 quadros por segundo gasta menos.")
	var linha := HBoxContainer.new()
	linha.add_theme_constant_override("separation", 10)
	var ob := OptionButton.new()
	ob.add_item("Ligado", 0)
	ob.add_item("Reduzido (imagem parada)", 1)
	ob.add_item("Desligado (só cores sólidas)", 2)
	ob.select({"ligado": 0, "reduzido": 1, "desligado": 2}.get(ap.movimento, 0))
	ob.item_selected.connect(func(i): ap.mudar_movimento(["ligado", "reduzido", "desligado"][i]))
	linha.add_child(ob)
	var fps := OptionButton.new()
	for n in [15, 30, 60]:
		fps.add_item(str(n) + " quadros/s", n)
	fps.select({15: 0, 30: 1, 60: 2}.get(ap.fps_max, 1))
	fps.item_selected.connect(func(i):
		ap.fps_max = fps.get_item_id(i)
		ap.salvar())
	linha.add_child(fps)
	v.add_child(linha)
	var guarda := CheckBox.new()
	guarda.text = "Reduzir sozinho se o computador ficar lento (recomendado)"
	guarda.button_pressed = ap.guarda_ativa
	guarda.add_theme_color_override("font_color", ui.TEXT_SECOND)
	guarda.toggled.connect(func(ligada):
		ap.guarda_ativa = ligada
		ap._resetar_guarda()
		ap.salvar())
	v.add_child(guarda)
