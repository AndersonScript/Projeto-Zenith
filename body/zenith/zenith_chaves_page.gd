extends RefCounted
# ZENITH — página "Chaves" das Configurações (contrato A8 do Cérebro).
# Várias chaves por IA, estado de cada uma (livre / em castigo / inválida), testar, remover e "onde pegar de graça".
# SEGURANÇA: a chave só sai da caixinha direto para o Cérebro e a caixinha é limpa na hora; a tela só recebe
# a versão mascarada (••••1234). Nada aqui grava chave em arquivo do Corpo nem escreve no chat.

const Icones := preload("res://zenith_icones.gd")
const PROVEDORES_ADD := [["gemini", "Gemini (Google)"], ["groq", "Groq"], ["openai", "OpenAI"],
	["claude", "Claude (via OpenRouter)"], ["llama", "Llama (via OpenRouter)"]]

var ui: Node
var brain: Node
var raiz: VBoxContainer
var lista: VBoxContainer
var status: Label
var _estado: Dictionary = {}
var _testes: Dictionary = {}        # "provedor:idx" -> {"ok", "msg"}
var _aviso_projeto: Dictionary = {} # provedor -> texto do aviso de cota por projeto
var pendente: bool = false          # pediu o estado e ainda não chegou (repete quando o Cérebro conectar)

const CHAVES_LOCAL_PATH := "user://chaves_local.json"

func _salvar_chave_local(id: String, chave: String) -> void:
	var dados := _carregar_chaves_locais()
	if not dados.has(id):
		dados[id] = []
	if not chave in dados[id]:
		dados[id].append(chave)
	var f = FileAccess.open(CHAVES_LOCAL_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(dados))

func _carregar_chaves_locais() -> Dictionary:
	if not FileAccess.file_exists(CHAVES_LOCAL_PATH):
		return {}
	var f = FileAccess.open(CHAVES_LOCAL_PATH, FileAccess.READ)
	if not f:
		return {}
	var parsed = JSON.parse_string(f.get_as_text())
	return parsed if parsed is Dictionary else {}

func montar(ui_node: Node, brain_node: Node, v: VBoxContainer) -> void:
	ui = ui_node
	brain = brain_node
	raiz = v
	ui._section(v, "Chaves de IA")
	ui._hint(v, "Cole aqui a chave de cada serviço. Você pode ter várias por serviço: se uma atingir o limite, o Zenith passa para a próxima sozinho. " +
		"A chave fica guardada só neste computador e nunca aparece inteira na tela. Nunca cole chave no chat.")
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.add_theme_font_size_override("font_size", 11)
	status.add_theme_color_override("font_color", ui.TEXT_SECOND)
	v.add_child(status)

	# --- adicionar chave nova ---
	var add := PanelContainer.new()
	add.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_SURFACE_2, 10, ui.BORDER, 1))
	var m := MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + lado, 10)
	add.add_child(m)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	m.add_child(col)
	var t := Label.new()
	t.text = "Adicionar uma chave"
	t.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	col.add_child(t)
	var linha := HBoxContainer.new()
	linha.add_theme_constant_override("separation", 8)
	col.add_child(linha)
	var prov := OptionButton.new()
	for p in PROVEDORES_ADD:
		prov.add_item(p[1])
	linha.add_child(prov)
	var campo := LineEdit.new()
	campo.secret = true
	campo.placeholder_text = "Cole a chave aqui"
	campo.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	campo.add_theme_stylebox_override("normal", ui._panel_style(ui.BG_BASE, 6))
	campo.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	campo.add_theme_color_override("font_placeholder_color", ui.TEXT_MUTED)
	linha.add_child(campo)
	var btn: Button = ui._make_button("Adicionar", ui.CYAN, ui.CYAN_DIM, Color("04141a"))
	btn.custom_minimum_size.x = 110
	Icones.aplicar(btn, "mais", Color("04141a"))
	btn.pressed.connect(func():
		var chave := campo.text.strip_edges()
		if chave.is_empty():
			_dizer("Cole a chave na caixinha primeiro.", false)
			return
		var id: String = PROVEDORES_ADD[prov.selected][0]
		campo.text = ""                          # some da tela na hora
		if brain:
			brain.chave_add(id, chave)
		if brain and brain.has_method("is_connected_to_brain") and brain.is_connected_to_brain():
			_dizer("Enviando chave ao Cérebro…", true)
		else:
			_dizer("✓ Chave salva (criptografada) no aparelho!", true))
	linha.add_child(btn)
	v.add_child(add)

	var barra := HBoxContainer.new()
	barra.add_theme_constant_override("separation", 8)
	var testar: Button = ui._make_button("Testar todas as chaves", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	Icones.aplicar(testar, "ok", ui.TEXT_PRIMARY)
	testar.pressed.connect(func():
		_testes.clear()
		_dizer("Testando cada chave… (pode levar alguns segundos)", true)
		if brain:
			brain.chaves_testar())
	barra.add_child(testar)
	var atualizar: Button = ui._make_button("Atualizar", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	Icones.aplicar(atualizar, "atualizar", ui.TEXT_PRIMARY)
	atualizar.pressed.connect(func():
		if brain:
			brain.request_chaves())
	barra.add_child(atualizar)
	v.add_child(barra)

	lista = VBoxContainer.new()
	lista.add_theme_constant_override("separation", 8)
	v.add_child(lista)
	# v1.1 — o editor de "Minhas IAs e serviços" mora nesta mesma página. Antes era uma aba própria
	# ("IAs & Chaves") que mostrava as MESMAS chaves dos cartões acima; agora cada chave tem um dono.
	ui._montar_editor_de_ias(v)
	_desenhar()

func pedir() -> void:
	pendente = true
	if brain:
		brain.request_chaves()

func _dizer(texto: String, ok: bool) -> void:
	if status and is_instance_valid(status):
		status.text = texto
		status.add_theme_color_override("font_color", ui.TEXT_SECOND if ok else ui.RED)

# ---------------- respostas do Cérebro ----------------
func ao_estado(d: Dictionary) -> void:
	pendente = false
	_estado = d
	_desenhar()

func ao_resultado(ok: bool, msg: String) -> void:
	_dizer(msg, ok)

func ao_teste(d: Dictionary) -> void:
	var idx := int(d.get("idx", -1))
	var prov := str(d.get("provedor", ""))
	if idx < 0:
		_aviso_projeto[prov] = str(d.get("msg", ""))
	else:
		_testes["%s:%d" % [prov, idx]] = {"ok": bool(d.get("ok", false)), "msg": str(d.get("msg", ""))}
	_desenhar()

func ao_teste_fim() -> void:
	_dizer("Teste terminado.", true)

# ---------------- desenho ----------------
func _desenhar() -> void:
	if lista == null or not is_instance_valid(lista):
		return
	for f in lista.get_children():
		f.queue_free()
	# v1.1 — só o catálogo vira cartão aqui: é a lista que aceita várias chaves por serviço.
	# As entradas de "Minhas IAs e serviços" (chave própria) ficam no editor abaixo — assim a
	# mesma chave não aparece em dois lugares da mesma tela.
	var do_catalogo := {}
	for p in PROVEDORES_ADD:
		do_catalogo[String(p[0])] = true
	var visiveis: Array = []
	for p in _estado.get("provedores", []):
		if do_catalogo.has(str(p.get("id", ""))):
			visiveis.append(p)
	if visiveis.is_empty():
		var vazio := Label.new()
		vazio.text = "Nenhuma chave por aqui ainda. Adicione a primeira acima — o Gemini tem plano grátis (veja \"Onde pegar\")."
		vazio.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		vazio.add_theme_color_override("font_color", ui.TEXT_MUTED)
		lista.add_child(vazio)
	var como: Dictionary = _estado.get("como_obter", {})
	for p in visiveis:
		lista.add_child(_cartao(p, como.get(str(p.get("id", "")), {})))
	var loc: Dictionary = _estado.get("ia_local", {})
	if not loc.is_empty():
		lista.add_child(_cartao_local(loc))

func _cartao(p: Dictionary, info: Dictionary) -> Control:
	var id := str(p.get("id", ""))
	var cartao := PanelContainer.new()
	cartao.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_SURFACE_2, 10, ui.BORDER, 1))
	var m := MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + lado, 10)
	cartao.add_child(m)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 5)
	m.add_child(col)
	var cab := HBoxContainer.new()
	var nome := Label.new()
	nome.text = str(p.get("nome", id))
	nome.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	nome.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cab.add_child(nome)
	if not info.is_empty() and bool(info.get("gratis", false)):
		var g := Label.new()
		g.text = "tem plano grátis"
		g.add_theme_font_size_override("font_size", 11)
		g.add_theme_color_override("font_color", ui.GREEN)
		cab.add_child(g)
	col.add_child(cab)

	var chaves: Array = p.get("chaves", [])
	if chaves.is_empty():
		var l := Label.new()
		l.text = "Sem chave cadastrada."
		l.add_theme_color_override("font_color", ui.TEXT_MUTED)
		col.add_child(l)
	for c in chaves:
		col.add_child(_linha_chave(id, c))

	if _aviso_projeto.has(id):
		var av := Label.new()
		av.text = str(_aviso_projeto[id])
		av.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		av.add_theme_font_size_override("font_size", 11)
		av.add_theme_color_override("font_color", Color("fbbf24"))
		col.add_child(av)

	if not info.is_empty():
		var onde := str(info.get("onde", ""))
		var dica := str(info.get("dica", ""))
		var l2 := Label.new()
		l2.text = ("Onde pegar: " + onde if onde != "" else "") + ("\n" + dica if dica != "" else "")
		l2.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l2.add_theme_font_size_override("font_size", 11)
		l2.add_theme_color_override("font_color", ui.TEXT_MUTED)
		col.add_child(l2)
		if onde != "":
			var abrir: Button = ui._make_button("Abrir o site", ui.BG_SURFACE_3, ui.BORDER, ui.TEXT_PRIMARY)
			Icones.aplicar(abrir, "link", ui.TEXT_PRIMARY, 16)
			abrir.custom_minimum_size.y = 28
			abrir.pressed.connect(func():
				OS.shell_open(onde if onde.begins_with("http") else "https://" + onde))
			col.add_child(abrir)
	return cartao

func _linha_chave(prov: String, c: Dictionary) -> Control:
	var linha := HBoxContainer.new()
	linha.add_theme_constant_override("separation", 8)
	var estado := str(c.get("estado", "livre"))
	var cor: Color = {"livre": ui.GREEN, "castigo": Color("fbbf24"), "invalida": ui.RED}.get(estado, ui.TEXT_MUTED)
	var ponto := ColorRect.new()
	ponto.color = cor
	ponto.custom_minimum_size = Vector2(8, 8)
	ponto.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	linha.add_child(ponto)
	var mascara := Label.new()
	mascara.text = str(c.get("mascara", "••••")) + ("  (principal)" if bool(c.get("principal", false)) else "")
	mascara.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	linha.add_child(mascara)
	var txt := Label.new()
	var s := int(c.get("segundos", 0))
	match estado:
		"livre": txt.text = "livre"
		"castigo": txt.text = "no limite — volta em ~%d s" % s
		"invalida": txt.text = "chave inválida"
		_: txt.text = estado
	txt.add_theme_font_size_override("font_size", 11)
	txt.add_theme_color_override("font_color", cor)
	txt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	linha.add_child(txt)
	var res: Dictionary = _testes.get("%s:%d" % [prov, int(c.get("idx", 0))], {})
	if not res.is_empty():
		var r := Label.new()
		r.text = ("✓ " if bool(res["ok"]) else "✗ ") + str(res["msg"]).left(60)
		r.add_theme_font_size_override("font_size", 11)
		r.add_theme_color_override("font_color", ui.GREEN if bool(res["ok"]) else ui.RED)
		linha.add_child(r)
	var rem: Button = ui._make_button("", Color(0, 0, 0, 0), ui.BG_SURFACE_3, ui.TEXT_MUTED)
	Icones.so_icone(rem, "lixeira", ui.TEXT_MUTED, 16)
	rem.custom_minimum_size = Vector2(30, 26)
	rem.tooltip_text = "Remover esta chave"
	var idx := int(c.get("idx", 0))
	rem.pressed.connect(func():
		if brain:
			brain.chave_remover(prov, idx))
	linha.add_child(rem)
	return linha

func _cartao_local(loc: Dictionary) -> Control:
	var cartao := PanelContainer.new()
	cartao.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_SURFACE_2, 10, ui.BORDER, 1))
	var m := MarginContainer.new()
	for lado in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + lado, 10)
	cartao.add_child(m)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 5)
	m.add_child(col)
	var n := Label.new()
	n.text = "IA local (roda no seu computador, sem internet)"
	n.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	col.add_child(n)
	var l := Label.new()
	var ligada := bool(loc.get("ligada", false))
	l.text = ("Ligada" if ligada else "Desligada") + (" · modelo: " + str(loc.get("modelo", "")) if str(loc.get("modelo", "")) != "" else "") + \
		(" · servidor: " + str(loc.get("servidor", "")) if str(loc.get("servidor", "")) != "" else " · nenhum servidor local encontrado")
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 11)
	l.add_theme_color_override("font_color", ui.TEXT_SECOND)
	col.add_child(l)
	var b: Button = ui._make_button("Desligar" if ligada else "Ligar", ui.BG_SURFACE_3, ui.BORDER, ui.TEXT_PRIMARY)
	b.custom_minimum_size.y = 28
	b.pressed.connect(func():
		if brain:
			brain.ia_local("desligar" if ligada else "ligar"))
	col.add_child(b)
	return cartao
