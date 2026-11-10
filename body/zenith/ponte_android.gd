extends Node
# ============================================================
#  ZENITH — Criado por Anderson
#  ponte_android.gd — v1.11 (port celular): o Corpo atende os pedidos do Cérebro ao Android.
#
#  O Cérebro (Python, dentro do celular) precisa de microfone, voz, câmera... que só o Android tem. Ele pede pelo MESMO
#  WebSocket de sempre (ver brain/zenith_ponte_corpo.py); o brain_connector.gd entrega a mensagem aqui, e este script
#  só REPASSA ao plugin Android ("ZenithAndroid", ver android_plugin/) e devolve a resposta. Ele não sabe o que cada
#  chamada faz: toda a lógica de cada capacidade mora no plugin. Por isso é pequeno e igual para qualquer capacidade nova.
#
#    Cérebro -> {"action":"ponte_chamar","id":"p7","nome":"tts.sintetizar","args":{...}} -> plugin.chamar(id, nome, json)
#    plugin  -> sinal resposta(id, json)  -> {"action":"ponte_resposta","id":"p7","resposta":{...}} -> Cérebro
#    plugin  -> sinal evento(nome, json)  -> {"action":"ponte_evento","evento":"mic.quadro","dados":{...}} -> Cérebro
#
#  ESTE ARQUIVO NÃO FOI EXECUTADO NO GODOT (não há Godot nem Android onde ele foi escrito). Os testes só conferem o
#  texto. Ao exportar o APK, qualquer erro de sintaxe aparece no editor — corrija e me conte.
# ============================================================

const NOME_PLUGIN := "ZenithAndroid"

# Chamada -> permissão do Android que precisa estar concedida antes. Sem ela o pedido é respondido com uma frase clara
# (e a janela de permissão do Android é aberta), em vez de o plugin falhar sem explicar.
const PERMISSOES := {
	"mic.iniciar": "RECORD_AUDIO",
	"camera.capturar": "CAMERA",
	"notificacao.mostrar": "POST_NOTIFICATIONS",
	"ble.enviar": "BLUETOOTH_SCAN|BLUETOOTH_CONNECT",      # mais de uma permissão: separadas por |
}

var _conector: Node = null
var _plugin: Object = null

func configurar(conector: Node) -> void:
	_conector = conector
	conector.connect("ponte_mensagem", _ao_receber)
	conector.connect("akira_connection_changed", _ao_mudar_conexao)
	get_tree().on_request_permissions_result.connect(_ao_permissao)
	if Engine.has_singleton(NOME_PLUGIN):
		_plugin = Engine.get_singleton(NOME_PLUGIN)
		_plugin.connect("resposta", _ao_resposta)
		_plugin.connect("evento", _ao_evento)
	else:
		push_warning("[Zenith/Ponte] Plugin Android '%s' não encontrado: microfone, voz e câmera do aparelho ficam indisponíveis." % NOME_PLUGIN)

# ---------- Cérebro -> Android ----------
func _ao_receber(dados: Dictionary) -> void:
	match str(dados.get("action", "")):
		"ponte_pedir_capacidades":
			_anunciar_capacidades()
		"ponte_chamar":
			_atender(str(dados.get("id", "")), str(dados.get("nome", "")), dados.get("args", {}))

# v1.14: o Corpo (tela de Voz) também fala com o plugin, sem passar pelo Cérebro. Os pedidos levam o prefixo "ui:" no id;
# a resposta deles NÃO vai ao Cérebro (ele não os fez).
signal resposta_local(id, dado)
signal modelo_evento(nome, dados)       # progresso / pronto / erro do baixador do modelo de fala

func chamar_local(nome: String, args: Dictionary = {}) -> void:
	if _plugin == null:
		resposta_local.emit("ui:" + nome, {"ok": false, "erro": "Este aparelho não tem o plugin Android do Zenith."})
		return
	_plugin.chamar("ui:" + nome, nome, JSON.stringify(args))

func _atender(id: String, nome: String, args) -> void:
	if _plugin == null:
		_responder(id, {"ok": false, "erro": "Este aparelho não tem o plugin Android do Zenith (%s)." % NOME_PLUGIN})
		return
	var permissao: String = _primeira_permissao_faltando(PERMISSOES.get(nome, ""))
	if permissao != "":
		OS.request_permission(permissao)
		_responder(id, {"ok": false, "erro": "Preciso da permissão '%s'. Conceda na janela do Android e peça de novo." % permissao})
		return
	_plugin.chamar(id, nome, JSON.stringify(args))

# Das permissões de um pedido ("A|B"), devolve a primeira que ainda falta ("" se estão todas concedidas). O Android pede uma
# por vez: com duas faltando, a pessoa concede, pede de novo e aparece a segunda.
func _primeira_permissao_faltando(permissoes: String) -> String:
	for p in permissoes.split("|"):
		if p != "" and not _permissao_concedida(p):
			return p
	return ""

func _permissao_concedida(permissao: String) -> bool:
	return ("android.permission." + permissao) in OS.get_granted_permissions()

# ---------- Android -> Cérebro ----------
func _ao_resposta(id: String, json_texto: String) -> void:
	var dado = _ler_json(json_texto)
	if dado == null:
		dado = {"ok": false, "erro": "O plugin Android devolveu uma resposta ilegível."}
	if id.begins_with("ui:"):
		resposta_local.emit(id, dado)
		return
	_responder(id, dado)

func _ao_evento(nome: String, json_texto: String) -> void:
	var dado = _ler_json(json_texto)
	if dado == null:
		dado = {}
	if nome.begins_with("modelo."):
		modelo_evento.emit(nome, dado)
		if nome == "modelo.pronto":
			_anunciar_capacidades()          # agora o aparelho TEM a transcrição: o Cérebro precisa saber
		return
	_enviar({"action": "ponte_evento", "evento": nome, "dados": dado})

func _responder(id: String, resposta) -> void:
	_enviar({"action": "ponte_resposta", "id": id, "resposta": resposta})

# ---------- capacidades (o que ESTE aparelho tem) ----------
func _ao_mudar_conexao(conectado: bool) -> void:
	if conectado:
		_anunciar_capacidades()

func _ao_permissao(_permissao: String, _concedida: bool) -> void:
	_anunciar_capacidades()           # a lista pode ter mudado (o plugin decide o que anuncia)

func _anunciar_capacidades() -> void:
	var lista: Array = []
	if _plugin != null:
		var dado = _ler_json(str(_plugin.capacidades()))
		if dado is Array:
			lista = dado
	_enviar({"action": "ponte_evento", "evento": "capacidades", "dados": {"lista": lista}})

# ---------- utilidades ----------
func _enviar(dados: Dictionary) -> void:
	if _conector != null and _conector.has_method("send_to_brain"):
		_conector.send_to_brain(dados)

func _ler_json(texto: String):
	var j := JSON.new()
	if j.parse(texto) == OK:
		return j.data
	return null
