extends SceneTree
# Autoteste dos "Meus temas" e do aviso de contraste, no Godot de verdade, sem abrir a interface.
# Uso: godot --headless --path body/zenith --script <caminho absoluto deste arquivo>
# Termina com "SELFTEST_OK" (código 0) ou lista as falhas (código 1).

const Ap := preload("res://zenith_aparencia.gd")
var falhas: Array = []

func ok(cond: bool, msg: String) -> void:
	if not cond:
		falhas.append(msg)

func _init() -> void:
	var src := """extends Window
var TEMA_CFG := "user://selftest_tema.cfg"
var BG_BASE := Color("0b0d17")
var BG_PANEL := Color("11141f")
var BG_SURFACE := Color("11141f")
var BG_SURFACE_2 := Color("181c2b")
var BG_SURFACE_3 := Color("222740")
var BORDER := Color("2a3050")
var CYAN := Color("22d3ee")
var CYAN_DIM := Color("0e7c93")
var MAGENTA := Color("f472b6")
var GREEN := Color("34d399")
var RED := Color("f87171")
var TEXT_PRIMARY := Color("eef1ff")
var TEXT_SECOND := Color("aab2d5")
var TEXT_MUTED := Color("8089b3")
var BUBBLE_USER := Color("123a48")
var BUBBLE_AI := Color("181c2b")
func _mostrar_toast(_a, _b, _c): pass
func _recarregar_conversa(): pass
"""
	var gs := GDScript.new()
	gs.source_code = src
	gs.reload()
	var ui = gs.new()
	root.add_child(ui)
	var ap = Ap.new()
	root.add_child(ap)
	ap.iniciar(ui)

	# 1) salvar / listar / nome limpo
	var r: Array = ap.salvar_tema("Teste/Ação: 1")
	ok(bool(r[0]), "salvar_tema falhou: " + str(r))
	var lista: Array = ap.listar_temas()
	var achou := ""
	for t in lista:
		if str(t["nome"]).begins_with("Teste"):
			achou = t["arquivo"]
	ok(achou != "", "o tema salvo não aparece em listar_temas")
	ok(not ap.nome_limpo("a/b\\c:d").contains("/") and not ap.nome_limpo("a/b\\c:d").contains("\\"), "nome_limpo deixou barra passar")
	ok(not bool(ap.salvar_tema("   ")[0]), "aceitou tema sem nome")

	# 2) exportar -> importar (ida e volta)
	var txt: String = ap.exportar_texto(achou)
	ok(txt != "", "exportar_texto vazio")
	var ri: Array = ap.importar_texto(txt)
	ok(bool(ri[0]), "importar do próprio export falhou: " + str(ri))

	# 3) entrada maliciosa / inválida
	ok(not bool(ap.importar_texto("")[0]), "aceitou texto vazio")
	ok(not bool(ap.importar_texto("isto não é json")[0]), "aceitou lixo")
	ok(not bool(ap.importar_texto("{\"a\": 1}")[0]), "aceitou JSON que não é tema")
	ok(not bool(ap.importar_texto("x".repeat(30000))[0]), "aceitou texto gigante")
	var mal := {"zenith_tema": 1, "nome": "../../etc/passwd", "script": "OS.execute('rm')",
		"paleta": {"CYAN": "red; drop", "BG_BASE": "#0a0a0a", "INVENTADA": "#ffffff"},
		"areas": {"chat": {"tipo": "../../x", "cores": ["zzz", "#ABCDEF"], "ncores": 99, "velocidade": 999, "intensidade": -5, "opacidade": 50},
			"area_que_nao_existe": {"tipo": "fogo"}}}
	var s: Dictionary = ap.sanear_tema(mal)
	ok(not s.is_empty(), "o saneamento descartou um tema recuperável")
	ok(not s.has("script"), "o saneamento deixou passar chave estranha")
	ok(not str(s.get("nome", "")).contains("/"), "nome com barra sobreviveu")
	ok(not s["paleta"].has("CYAN") and not s["paleta"].has("INVENTADA"), "cor inválida/inventada sobreviveu")
	ok(s["paleta"].has("BG_BASE"), "cor válida foi descartada")
	ok(not s["areas"].has("area_que_nao_existe"), "área inventada sobreviveu")
	var c: Dictionary = s["areas"]["chat"]
	ok(c["tipo"] == "nenhum", "tipo de efeito inválido sobreviveu: " + str(c["tipo"]))
	ok(int(c["ncores"]) == 4 and float(c["velocidade"]) == 3.0 and float(c["intensidade"]) == 0.0 and float(c["opacidade"]) == 1.0, "números não foram limitados: " + str(c))
	ok(c["cores"].size() == 4 and c["cores"][1] == "#abcdef", "cores não foram saneadas: " + str(c["cores"]))

	# 4) aplicar muda a paleta e o efeito
	var tema := {"zenith_tema": 1, "nome": "Rosa", "paleta": {"CYAN": "#ff66aa"},
		"areas": {"barra_lateral": {"tipo": "aurora", "cores": ["#112233", "#445566", "#778899", "#aabbcc"], "ncores": 3, "velocidade": 1.0, "intensidade": 0.5, "opacidade": 0.8}}}
	ap.aplicar_tema(ap.sanear_tema(tema))
	ok((ui.CYAN as Color).to_html(false) == "ff66aa", "aplicar_tema não mudou o destaque")
	ok(ap.area("barra_lateral")["tipo"] == "aurora", "aplicar_tema não mudou o efeito da área")

	# 5) contraste
	ap.aplicar_preset("neutro")
	ok(ap.avisos_contraste().is_empty(), "o tema neutro não devia gerar aviso de contraste: " + str(ap.avisos_contraste()))
	ui.TEXT_PRIMARY = ui.BG_BASE
	ok(not ap.avisos_contraste().is_empty(), "texto igual ao fundo não gerou aviso")
	for k in ["papel", "neon", "sakura", "meia_noite", "floresta", "por_do_sol", "lavanda", "mono", "amoled"]:
		ap.aplicar_preset(k)
		ok(ap.avisos_contraste().is_empty(), "o tema pronto '" + k + "' tem texto difícil de ler: " + str(ap.avisos_contraste()))

	# 6) apagar (e recusar caminho de fora)
	ok(ap.apagar_tema(achou), "não apagou o tema salvo")
	ok(not ap.apagar_tema("/etc/passwd.json"), "apagou arquivo fora da pasta de temas!")
	for t2 in ap.listar_temas():
		ap.apagar_tema(t2["arquivo"])
	DirAccess.remove_absolute("user://selftest_tema.cfg")

	if falhas.is_empty():
		print("SELFTEST_OK")
		quit(0)
	else:
		for f in falhas:
			print("FALHA: ", f)
		quit(1)
