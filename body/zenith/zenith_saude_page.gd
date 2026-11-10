extends RefCounted
# ZENITH — seção "Saúde do Zenith" (Configurações → Sobre).
# Roda o diagnóstico do Cérebro (voz, ffmpeg, áudio, bloqueio do Windows, administrador, disco, chaves, internet...)
# e mostra o que está certo/avisando/quebrado, com a causa em português. "Copiar relatório" já sai pronto para colar
# num pedido de ajuda — sem chave, sem conversa, sem nome de usuário (o Cérebro garante isso).

const Icones := preload("res://zenith_icones.gd")

var ui: Node
var brain: Node
var lista: VBoxContainer
var resumo: Label
var aviso: Label
var btn_rodar: Button
var btn_copiar: Button
var btn_pasta: Button
var _relatorio: String = ""
var _arquivo: String = ""

func montar(ui_node: Node, brain_node: Node, v: VBoxContainer) -> void:
	ui = ui_node
	brain = brain_node
	ui._section(v, "Saúde do Zenith")
	ui._hint(v, "Confere se a voz, o vídeo, o áudio, as chaves e a internet estão funcionando — e, se algo falhar, diz o motivo e " +
		"o que fazer. Pode demorar uns 10 segundos (ele testa a voz de verdade).")
	var barra := HBoxContainer.new()
	barra.add_theme_constant_override("separation", 8)
	btn_rodar = ui._make_button("Rodar diagnóstico", ui.CYAN, ui.CYAN_DIM, Color("04141a"))
	Icones.aplicar(btn_rodar, "atualizar", Color("04141a"))
	btn_rodar.pressed.connect(rodar)
	barra.add_child(btn_rodar)
	btn_copiar = ui._make_button("Copiar relatório", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	Icones.aplicar(btn_copiar, "copiar", ui.TEXT_PRIMARY)
	btn_copiar.disabled = true
	btn_copiar.pressed.connect(func():
		DisplayServer.clipboard_set(_relatorio)
		_dizer("Relatório copiado! É só colar na conversa de quem vai te ajudar.", false))
	barra.add_child(btn_copiar)
	btn_pasta = ui._make_button("Abrir pasta do relatório", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	Icones.aplicar(btn_pasta, "pasta", ui.TEXT_PRIMARY)
	btn_pasta.disabled = true
	btn_pasta.pressed.connect(func():
		if _arquivo != "":
			OS.shell_show_in_file_manager(_arquivo))
	barra.add_child(btn_pasta)
	v.add_child(barra)
	resumo = Label.new()
	resumo.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	v.add_child(resumo)
	aviso = Label.new()
	aviso.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	aviso.add_theme_font_size_override("font_size", 11)
	aviso.add_theme_color_override("font_color", ui.TEXT_SECOND)
	v.add_child(aviso)
	lista = VBoxContainer.new()
	lista.add_theme_constant_override("separation", 4)
	v.add_child(lista)

func _dizer(texto: String, erro: bool) -> void:
	if aviso and is_instance_valid(aviso):
		aviso.text = texto
		aviso.add_theme_color_override("font_color", ui.RED if erro else ui.TEXT_SECOND)

func rodar() -> void:
	if brain == null:
		_dizer("O Cérebro ainda não conectou. Espere alguns segundos e tente de novo.", true)
		return
	btn_rodar.disabled = true
	_dizer("Testando… (a voz e a internet levam uns segundos)", false)
	brain.request_diagnostico()

func ao_resultado(d: Dictionary) -> void:
	btn_rodar.disabled = false
	_relatorio = str(d.get("relatorio", ""))
	_arquivo = str(d.get("arquivo", ""))
	btn_copiar.disabled = _relatorio == ""
	btn_pasta.disabled = _arquivo == ""
	var r: Dictionary = d.get("resumo", {})
	var erros := int(r.get("erro", 0))
	var avisos := int(r.get("aviso", 0))
	resumo.text = "%d com problema  ·  %d com aviso  ·  %d certos" % [erros, avisos, int(r.get("ok", 0))]
	resumo.add_theme_color_override("font_color", ui.RED if erros > 0 else (Color("fbbf24") if avisos > 0 else ui.GREEN))
	_dizer("Pronto. Se algo estiver errado, clique em \"Copiar relatório\" e cole numa conversa para pedir ajuda." if erros + avisos > 0
		else "Tudo certo por aqui.", false)
	for f in lista.get_children():
		f.queue_free()
	var itens: Array = d.get("itens", [])
	var ordem := {"erro": 0, "aviso": 1, "ok": 2}
	itens.sort_custom(func(a, b): return int(ordem.get(str(a.get("status", "ok")), 2)) < int(ordem.get(str(b.get("status", "ok")), 2)))
	for it in itens:
		lista.add_child(_linha(it))

func _linha(it: Dictionary) -> Control:
	var st := str(it.get("status", "ok"))
	var cor: Color = {"ok": ui.GREEN, "aviso": Color("fbbf24"), "erro": ui.RED}.get(st, ui.TEXT_MUTED)
	var cartao := PanelContainer.new()
	cartao.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_SURFACE_2, 8, cor if st != "ok" else ui.BORDER, 1))
	var m := MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + lado, 8)
	cartao.add_child(m)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	m.add_child(h)
	var ic := Icones.rect({"ok": "ok", "aviso": "aviso", "erro": "fechar"}.get(st, "ok"), cor, 16)
	ic.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	h.add_child(ic)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(col)
	var nome := Label.new()
	nome.text = str(it.get("nome", ""))
	nome.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	col.add_child(nome)
	var det := str(it.get("detalhe", ""))
	if det != "":
		var l := Label.new()
		l.text = det
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.add_theme_font_size_override("font_size", 11)
		l.add_theme_color_override("font_color", ui.TEXT_SECOND)
		col.add_child(l)
	return cartao
