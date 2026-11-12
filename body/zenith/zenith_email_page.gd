extends RefCounted
# ============================================================
#  ZENITH — página "Ponte por E-mail" (Celular ↔ Computador) — v1.20
#
#  Permite ao usuário conectar o celular com o computador pelo
#  seu próprio e-mail pessoal (Gmail, Outlook, etc.).
#  100% privado, sem servidores externos e sem banco de dados.
# ============================================================

const Icones := preload("res://zenith_icones.gd")

var ui: Node
var brain: Node
var raiz: VBoxContainer

var chk_ativo: CheckBox
var edt_email: LineEdit
var edt_senha: LineEdit
var opt_provedor: OptionButton
var edt_imap: LineEdit
var edt_smtp: LineEdit
var lbl_status: Label
var btn_testar: Button
var btn_salvar: Button

const LOCAL_EMAIL_CFG := "user://email_ponte.json"

func montar(ui_node: Node, brain_node: Node, v: VBoxContainer) -> void:
	ui = ui_node
	brain = brain_node
	raiz = v

	ui._section(v, "Ponte por E-mail (Celular ↔ PC)")
	ui._hint(v, "Conecte seu celular ao computador pelo seu próprio e-mail pessoal. Funciona de qualquer lugar (em casa no Wi-Fi ou na rua pelo 4G), sem nenhum servidor intermediário e 100% anônimo.")

	var painel = PanelContainer.new()
	painel.add_theme_stylebox_override("panel", ui._panel_style(ui.BG_SURFACE_2, 10, ui.BORDER, 1))
	v.add_child(painel)

	var pad = MarginContainer.new()
	for s in ["left", "right", "top", "bottom"]:
		pad.add_theme_constant_override("margin_" + s, 14)
	painel.add_child(pad)

	var box = VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	pad.add_child(box)

	# 1. Ativar / Desativar
	chk_ativo = CheckBox.new()
	chk_ativo.text = "Ativar monitoramento e comandos por e-mail"
	chk_ativo.button_pressed = false
	box.add_child(chk_ativo)

	# 2. Provedor
	var lbl_prov = Label.new()
	lbl_prov.text = "Provedor:"
	lbl_prov.add_theme_font_size_override("font_size", 12)
	lbl_prov.add_theme_color_override("font_color", ui.TEXT_SECOND)
	box.add_child(lbl_prov)

	opt_provedor = OptionButton.new()
	opt_provedor.add_item("Gmail (Google) — Recomendado", 0)
	opt_provedor.add_item("Outlook / Hotmail (Microsoft)", 1)
	opt_provedor.add_item("Personalizado (IMAP / SMTP)", 2)
	opt_provedor.item_selected.connect(_ao_trocar_provedor)
	box.add_child(opt_provedor)

	# 3. E-mail
	var lbl_em = Label.new()
	lbl_em.text = "Seu E-mail:"
	lbl_em.add_theme_font_size_override("font_size", 12)
	lbl_em.add_theme_color_override("font_color", ui.TEXT_SECOND)
	box.add_child(lbl_em)

	edt_email = LineEdit.new()
	edt_email.placeholder_text = "seu.email@gmail.com"
	box.add_child(edt_email)

	# 4. Senha de Aplicativo
	var lbl_pw = Label.new()
	lbl_pw.text = "Senha de Aplicativo (16 letras do Gmail / Outlook):"
	lbl_pw.add_theme_font_size_override("font_size", 12)
	lbl_pw.add_theme_color_override("font_color", ui.TEXT_SECOND)
	box.add_child(lbl_pw)

	edt_senha = LineEdit.new()
	edt_senha.placeholder_text = "Cole a senha de app de 16 letras aqui"
	edt_senha.secret = true
	box.add_child(edt_senha)

	# 5. Dica rápida
	var dica = Label.new()
	dica.text = "💡 Dica Gmail: Acesse myaccount.google.com > Segurança > 'Senhas de app', crie uma com o nome 'Zenith' e cole as 16 letras aqui.\n" + \
		"📱 Comandos no celular: você pode enviar um e-mail para si mesmo com assunto [Zenith] status, [Zenith] print, ou [Zenith] buscar <arquivo> e o PC responde!"
	dica.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	dica.add_theme_font_size_override("font_size", 11)
	dica.add_theme_color_override("font_color", ui.TEXT_MUTED)
	box.add_child(dica)

	# 6. Status Label
	lbl_status = Label.new()
	lbl_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl_status.add_theme_font_size_override("font_size", 12)
	lbl_status.add_theme_color_override("font_color", ui.CYAN)
	lbl_status.text = "⚪ Carregando status da ponte..."
	box.add_child(lbl_status)

	# 7. Botões
	var linha_btn = HBoxContainer.new()
	linha_btn.add_theme_constant_override("separation", 10)
	box.add_child(linha_btn)

	btn_testar = ui._make_button("Testar Conexão", ui.BG_SURFACE_3, ui.BG_SURFACE_2, ui.CYAN)
	btn_testar.custom_minimum_size = Vector2(130, 36)
	btn_testar.pressed.connect(_testar)
	linha_btn.add_child(btn_testar)

	btn_salvar = ui._make_button("Salvar e Ativar", ui.CYAN, ui.CYAN_DIM, Color("04141a"))
	btn_salvar.custom_minimum_size = Vector2(140, 36)
	btn_salvar.pressed.connect(_salvar)
	linha_btn.add_child(btn_salvar)

	# Conecta sinais do Cérebro
	if brain.has_signal("email_ponte_dados"):
		brain.email_ponte_dados.connect(_ao_receber_dados)
	if brain.has_signal("email_ponte_teste_resultado"):
		brain.email_ponte_teste_resultado.connect(_ao_resultado_teste)

	pedir_dados()

func pedir_dados() -> void:
	if brain.has_method("email_ponte_pedir"):
		brain.email_ponte_pedir()
	else:
		_carregar_local()

func _ao_trocar_provedor(idx: int) -> void:
	match idx:
		0: # Gmail
			pass
		1: # Outlook
			pass
		2: # Personalizado
			pass

func _testar() -> void:
	lbl_status.text = "⏳ Testando conexão com os servidores de e-mail..."
	lbl_status.add_theme_color_override("font_color", ui.CYAN)
	var cfg = _obter_formulario()
	if brain.has_method("email_ponte_testar"):
		brain.email_ponte_testar(cfg)
	else:
		lbl_status.text = "ℹ️ Cérebro não conectado ao PC. Salve no celular."

func _salvar() -> void:
	var cfg = _obter_formulario()
	_salvar_local(cfg)
	if brain.has_method("email_ponte_salvar"):
		brain.email_ponte_salvar(cfg)
	lbl_status.text = "✅ Configurações salvas!"
	lbl_status.add_theme_color_override("font_color", ui.GREEN)

func _obter_formulario() -> Dictionary:
	var imap_srv = "imap.gmail.com"
	var smtp_srv = "smtp.gmail.com"
	if opt_provedor.selected == 1:
		imap_srv = "outlook.office365.com"
		smtp_srv = "smtp.office365.com"
	
	return {
		"ativo": chk_ativo.button_pressed,
		"email": edt_email.text.strip_edges(),
		"senha_app": edt_senha.text.strip_edges().replace(" ", ""),
		"servidor_imap": imap_srv,
		"porta_imap": 993,
		"servidor_smtp": smtp_srv,
		"porta_smtp": 465,
	}

func _ao_receber_dados(dados: Dictionary) -> void:
	var cfg = dados.get("config", {})
	chk_ativo.button_pressed = bool(cfg.get("ativo", false))
	if not edt_email.has_focus():
		edt_email.text = str(cfg.get("email", ""))
	if cfg.has("senha_mascarada") and not str(cfg.get("senha_mascarada")).is_empty():
		edt_senha.placeholder_text = "Salva: " + str(cfg.get("senha_mascarada"))
	
	var rodando = bool(cfg.get("rodando", false))
	if rodando:
		lbl_status.text = "🟢 Ponte por E-mail Ativa e Monitorando no Computador!"
		lbl_status.add_theme_color_override("font_color", ui.GREEN)
	elif chk_ativo.button_pressed:
		lbl_status.text = "🟡 Ativada, aguardando início do monitoramento..."
		lbl_status.add_theme_color_override("font_color", ui.YELLOW)
	else:
		lbl_status.text = "⚪ Ponte desativada."
		lbl_status.add_theme_color_override("font_color", ui.TEXT_MUTED)

func _ao_resultado_teste(dados: Dictionary) -> void:
	var ok = bool(dados.get("ok", false))
	var msg = str(dados.get("mensagem", ""))
	if ok:
		lbl_status.text = "✅ Sucesso! Conexão com IMAP e SMTP confirmada."
		lbl_status.add_theme_color_override("font_color", ui.GREEN)
	else:
		lbl_status.text = "❌ Erro no teste: " + msg
		lbl_status.add_theme_color_override("font_color", ui.RED)

func _salvar_local(cfg: Dictionary) -> void:
	var f = FileAccess.open(LOCAL_EMAIL_CFG, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(cfg))

func _carregar_local() -> void:
	if not FileAccess.file_exists(LOCAL_EMAIL_CFG):
		return
	var f = FileAccess.open(LOCAL_EMAIL_CFG, FileAccess.READ)
	if f:
		var parsed = JSON.parse_string(f.get_as_text())
		if parsed is Dictionary:
			_ao_receber_dados({"config": parsed})
