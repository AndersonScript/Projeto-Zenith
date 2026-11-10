extends RefCounted
# ============================================================
#  ZENITH — seção "Desempenho" (Configurações → Sobre) — v1.11, port celular.
#
#  A tela do downgrade: mostra o que o aparelho aguenta e deixa a pessoa DESLIGAR ou REDUZIR o que não aguenta (avatar
#  3D, voz, câmera/tela, memória, IA no aparelho). Nada muda sozinho: ela escolhe, aperta "Aplicar", e o Cérebro grava
#  (e guarda o que estava antes, para voltar exatamente igual ao religar). Mesmo molde da página "Saúde" (zenith_saude_page.gd).
#
#  ESTE ARQUIVO NÃO FOI EXECUTADO NO GODOT. Se falhar ao compilar, a ui_manager.gd o ignora (carrega com load(), não
#  com preload()) e a tela simplesmente não aparece — o resto do Zenith segue normal.
# ============================================================

const Icones := preload("res://zenith_icones.gd")

# Ordem em que as linhas aparecem (as chaves vêm do Cérebro: zenith_downgrade.RECURSOS)
const ORDEM := ["avatar", "qualidade_grafica", "fps", "voz_saida", "voz_entrada", "visao", "memoria", "ia_local"]
const NOMES := {
	"vrm": "Avatar 3D (VRM)", "padrao": "Avatar simples",
	"alta": "Alta", "media": "Média", "baixa": "Baixa",
	"local": "Ligada", "ligada": "Ligada", "desligada": "Desligada",
	"whisper": "Whisper (melhor)", "sistema": "Do aparelho",
	"vetorial": "Por sentido", "leve": "Por palavras",
}

var ui: Node
var brain: Node
var texto: Label
var aviso: Label
var grade: GridContainer
var btn_aplicar: Button
var btn_medir: Button
var btn_sugestao: Button
var _seletores: Dictionary = {}
var _sugestao: Dictionary = {}

func montar(ui_node: Node, brain_node: Node, v: VBoxContainer) -> void:
	ui = ui_node
	brain = brain_node
	ui._section(v, "Desempenho")
	ui._hint(v, "Se o aparelho estiver pesado, desligue ou reduza o que ele não aguenta. Nada muda sozinho: você escolhe e " +
		"aperta Aplicar — e, ao religar, tudo volta exatamente como estava.")
	texto = Label.new()
	texto.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	texto.add_theme_font_size_override("font_size", 11)
	texto.add_theme_color_override("font_color", ui.TEXT_SECOND)
	v.add_child(texto)
	grade = GridContainer.new()
	grade.columns = 2
	grade.add_theme_constant_override("h_separation", 12)
	grade.add_theme_constant_override("v_separation", 6)
	v.add_child(grade)
	btn_sugestao = ui._make_button("", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	btn_sugestao.visible = false
	btn_sugestao.pressed.connect(_usar_sugestao)
	v.add_child(btn_sugestao)
	var barra := HBoxContainer.new()
	barra.add_theme_constant_override("separation", 8)
	btn_aplicar = ui._make_button("Aplicar", ui.CYAN, ui.CYAN_DIM, Color("04141a"))
	btn_aplicar.pressed.connect(_aplicar)
	barra.add_child(btn_aplicar)
	btn_medir = ui._make_button("Medir de novo", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	Icones.aplicar(btn_medir, "atualizar", ui.TEXT_PRIMARY)
	btn_medir.pressed.connect(_pedir)
	barra.add_child(btn_medir)
	v.add_child(barra)
	aviso = Label.new()
	aviso.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	aviso.add_theme_font_size_override("font_size", 11)
	aviso.add_theme_color_override("font_color", ui.TEXT_SECOND)
	v.add_child(aviso)
	_pedir()

func _pedir() -> void:
	if brain and brain.has_method("request_desempenho"):
		brain.request_desempenho()

# Resposta do Cérebro (ver zenith_headless._estado_desempenho)
func ao_estado(d: Dictionary) -> void:
	if grade == null or not is_instance_valid(grade):
		return
	_dizer(str(d.get("mensagem", "")), not bool(d.get("ok", true)))
	texto.text = str(d.get("texto", ""))
	for c in grade.get_children():
		c.queue_free()
	_seletores.clear()
	var opcoes: Dictionary = d.get("opcoes", {})
	var rotulos: Dictionary = d.get("rotulos", {})
	var atuais: Dictionary = d.get("recursos", {})
	for chave in ORDEM:
		if not opcoes.has(chave):
			continue
		var nome := Label.new()
		nome.text = str(rotulos.get(chave, chave))
		nome.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
		var seletor := OptionButton.new()
		var lista: Array = opcoes[chave]
		var indice := 0
		for i in lista.size():
			seletor.add_item(_nome(lista[i]))
			seletor.set_item_metadata(i, lista[i])
			if _igual(lista[i], atuais.get(chave)):
				indice = i
		seletor.select(indice)
		if chave == "avatar":
			seletor.tooltip_text = "Avatar simples: um personagem leve, desenhado em código, para celulares que não aguentam o VRM."
		grade.add_child(nome)
		grade.add_child(seletor)
		_seletores[chave] = seletor
	_sugestao = d.get("sugestao", {})
	btn_sugestao.visible = not _sugestao.is_empty()
	if btn_sugestao.visible:
		btn_sugestao.text = "Sugestão para aliviar: %s — %s → %s" % [
			str(_sugestao.get("rotulo", "")), _nome(_sugestao.get("de", "")), _nome(_sugestao.get("para", ""))]

# A sugestão só MOVE a escolha na tela; quem aplica é a pessoa, no botão Aplicar.
func _usar_sugestao() -> void:
	var seletor = _seletores.get(str(_sugestao.get("recurso", "")))
	if seletor == null:
		return
	for i in seletor.item_count:
		if _igual(seletor.get_item_metadata(i), _sugestao.get("para")):
			seletor.select(i)
	_dizer("Sugestão escolhida. Aperte Aplicar para valer.", false)

func _aplicar() -> void:
	var recursos := {}
	for chave in _seletores:
		var seletor: OptionButton = _seletores[chave]
		recursos[chave] = seletor.get_item_metadata(seletor.selected)
	if brain and brain.has_method("aplicar_desempenho"):
		_dizer("Aplicando...", false)
		brain.aplicar_desempenho(recursos)

func _nome(valor) -> String:
	if typeof(valor) == TYPE_INT or typeof(valor) == TYPE_FLOAT:
		return "%d quadros por segundo" % int(valor)
	return str(NOMES.get(str(valor), str(valor)))

func _igual(a, b) -> bool:
	var numero_a: bool = typeof(a) == TYPE_INT or typeof(a) == TYPE_FLOAT
	var numero_b: bool = typeof(b) == TYPE_INT or typeof(b) == TYPE_FLOAT
	if numero_a and numero_b:
		return float(a) == float(b)
	return str(a) == str(b)

func _dizer(mensagem: String, erro: bool) -> void:
	if aviso and is_instance_valid(aviso):
		aviso.text = mensagem
		aviso.add_theme_color_override("font_color", Color("ff8a8a") if erro else ui.TEXT_SECOND)
