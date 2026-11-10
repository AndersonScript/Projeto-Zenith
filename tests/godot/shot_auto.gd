extends Node
# TESTE (cópia temporária, nunca vai para o pacote): tira print da janela do Corpo e da janela da interface.
var t := 0.0
var feito := false
var _args_aplicados := false

# Argumentos que mexem no CORPO antes do print (teste do avatar simples), depois do "--":
#   --aplicar-avatar=padrao|vrm   --corpo-estado=speaking   --corpo-expressao=happy
func _aplicar_args() -> void:
	_args_aplicados = true
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--aplicar-avatar="):
			var ap = load("res://zenith_desempenho_aplicar.gd").new()
			ap.aplicar({"recursos": {"avatar": a.get_slice("=", 1)}}, get_tree())
		elif a.begins_with("--corpo-estado="):
			get_tree().current_scene.set_life_state(a.get_slice("=", 1))
		elif a.begins_with("--corpo-expressao="):
			get_tree().current_scene.set_expression(a.get_slice("=", 1))
func _achar_janelas(n: Node, acc: Array):
	for c in n.get_children():
		if c is Window: acc.append(c)
		_achar_janelas(c, acc)
func _process(d):
	t += d
	if not _args_aplicados and t > 2.0:
		_aplicar_args()
	var espera := 7.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--espera="): espera = float(a.get_slice("=", 1))
	if feito or t < espera: return
	feito = true
	var prefixo := "teste"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--nome="): prefixo = a.get_slice("=", 1)
	var raiz := get_tree().root
	raiz.get_texture().get_image().save_png("/home/claude/shots/%s_corpo.png" % prefixo)
	var js := []
	_achar_janelas(raiz, js)
	var i := 0
	for j in js:
		var img = j.get_texture().get_image()
		img.save_png("/home/claude/shots/%s_janela%d.png" % [prefixo, i])
		print("JANELA ", i, " ", j.name, " pos=", j.position, " tam=", j.size, " embutida=", j.is_embedded())
		i += 1
	print("RAIZ tam=", raiz.size)
	get_tree().quit()
