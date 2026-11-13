extends Node

var websocket = WebSocketPeer.new()

# Sinais atualizados
signal akira_speaks(text)
signal akira_changes_expression(expression_type)
signal akira_toggle_mouth(is_speaking)
signal akira_set_transparency(value)
signal akira_receive_action(action_name)
signal akira_chat_message(sender, text)
signal akira_chat_stream_chunk(delta, done)
signal akira_sync_history(history)
signal akira_connection_changed(is_connected)
signal conversations_list(items)
signal memories_list(items)
signal conversation_loaded(id, title, messages)
signal settings_data(settings)
signal settings_saved(warnings)
signal approval_request(request_id, kind, description, preview)
signal unlock_result(success)
signal api_key_test_result(provider, valid, message)
signal mic_state_changed(listening)
signal mic_transcript_received(text, enviar)
signal conversa_estado(estado)
signal chat_image(path, caption)
signal avatar_fundo(modo, cor)
signal movimento(dados)
signal projetos_dados(dados)
signal observando(ativo, tipo, info)
signal atividade(estado, icone, texto, pode_parar)
signal mic_fase(fase, texto)
signal tft_config(ativo, w, h, fps, qualidade, zoom, cor, enquadre)
signal ui_tema(paleta)
signal progresso(dados)
signal aviso(dados)
signal anexo_resumo(dados)
signal chaves_estado(dados)
signal chaves_resultado(ok, msg)
signal chaves_teste(dados)
signal chaves_teste_fim()
signal diagnostico_resultado(dados)
signal cartao_atividade(dados)
signal comandos_lista(itens)
signal reset_scheduled(ok, message)
signal wallpaper_ready(result)
signal akira_notify(title, body)
signal atualizacao_disponivel(info)
signal ponte_mensagem(dados)
signal desempenho_estado(dados)
signal desempenho_config(dados)
signal email_ponte_dados(dados)
signal email_ponte_teste_resultado(dados)

var _was_open: bool = false
var _reconnect_cooldown: float = 0.0
var _reconnect_attempts: int = 0

const TAMANHO_MAXIMO_MENSAGEM := 16777216   # 16 MiB
const CHAVES_LOCAL_PATH := "user://chaves_local.json"
const CONVERSAS_LOCAL_PATH := "user://conversas_mobile.json"
const CONFIG_LOCAL_PATH := "user://config_mobile.json"

# --- Standalone Mobile Brain (Cérebro Integrado para Celular) ---
var _http_ai: HTTPRequest = null
var _http_test: HTTPRequest = null
var _http_search: HTTPRequest = null
var _termo_busca_pendente: String = ""
var _texto_usuario_pendente: String = ""
var _historico_mobile: Array = []
var _audio_player_el: AudioStreamPlayer = null
var _eleven_http: HTTPRequest = null
var _ultimo_texto_tts: String = ""
var _standalone_timer: float = 0.0
var _standalone_inicializado: bool = false
var _ai_respondendo: bool = false
var _provedor_atual: String = "gemini"

func _ready():
	websocket.inbound_buffer_size = TAMANHO_MAXIMO_MENSAGEM
	websocket.outbound_buffer_size = TAMANHO_MAXIMO_MENSAGEM
	
	_http_ai = HTTPRequest.new()
	_http_ai.name = "HttpAi"
	_http_ai.timeout = 35.0
	add_child(_http_ai)
	_http_ai.request_completed.connect(_ao_resposta_http_ai)
	
	_http_search = HTTPRequest.new()
	_http_search.name = "HttpSearch"
	_http_search.timeout = 15.0
	add_child(_http_search)
	_http_search.request_completed.connect(_ao_resposta_http_search)
	
	_http_test = HTTPRequest.new()
	_http_test.name = "HttpTest"
	_http_test.timeout = 15.0
	add_child(_http_test)
	_http_test.request_completed.connect(_ao_resposta_http_test)
	
	_carregar_config_mobile()
	_carregar_historico_mobile()
	
	_try_connect()
	_iniciar_ponte_android()

# Modo celular: só no Android (ou --layout-celular, para testar no PC). No PC normal o cérebro local NUNCA liga.
func _modo_celular() -> bool:
	return OS.get_name() == "Android" or OS.get_cmdline_user_args().has("--layout-celular")

func _cerebro_local() -> bool:
	return _modo_celular() and not is_connected_to_brain()

func is_connected_to_brain() -> bool:
	return websocket != null and websocket.get_ready_state() == WebSocketPeer.STATE_OPEN

func _obter_url_servidor() -> String:
	if FileAccess.file_exists("user://servidor_ip.txt"):
		var f = FileAccess.open("user://servidor_ip.txt", FileAccess.READ)
		if f:
			var txt = f.get_as_text().strip_edges()
			if not txt.is_empty():
				if not txt.begins_with("ws://") and not txt.begins_with("wss://"):
					txt = "ws://" + txt
				if not ":" in txt.substr(6):
					txt += ":8765"
				return txt
	return "ws://localhost:8765"

func definir_servidor(ip_ou_url: String) -> void:
	var f = FileAccess.open("user://servidor_ip.txt", FileAccess.WRITE)
	if f:
		f.store_string(ip_ou_url.strip_edges())
	if websocket:
		websocket.close()
	_was_open = false
	_reconnect_cooldown = 0.2
	_try_connect()

func _try_connect():
	var url = _obter_url_servidor()
	var err = websocket.connect_to_url(url)
	_reconnect_attempts += 1
	if err != OK:
		print("[Zenith/Corpo] Erro ao tentar conectar no Cérebro (código %d)." % err)
	else:
		print("[Zenith/Corpo] Tentando conectar ao Cérebro... (tentativa %d)" % _reconnect_attempts)

func _process(delta):
	websocket.poll()
	
	var state = websocket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		if not _was_open:
			_was_open = true
			_standalone_inicializado = false
			_reconnect_attempts = 0
			print("[Zenith/Corpo] Conectado ao Cérebro via WebSocket. ✓")
			emit_signal("akira_connection_changed", true)
			send_to_brain({"action": "request_sync"})
			# Sincroniza chaves salvas no aparelho com o Cérebro
			var locais = _carregar_chaves_locais_dict() if _modo_celular() else {}
			for prov in locais:
				for ch in locais[prov]:
					chave_add(prov, ch)
		while websocket.get_available_packet_count():
			var packet = websocket.get_packet()
			if websocket.was_string_packet():
				var message = packet.get_string_from_utf8()
				_process_brain_message(message)
				
	elif state == WebSocketPeer.STATE_CLOSED:
		if _was_open:
			_was_open = false
			var code = websocket.get_close_code()
			var reason = websocket.get_close_reason()
			print("[Zenith/Corpo] Cérebro desconectou (código %d, motivo '%s')." % [code, reason])
			emit_signal("akira_connection_changed", false)
		
		# Modo Celular Standalone: após 0.8s sem conexão, assume o comando localmente
		if not _standalone_inicializado and _modo_celular():
			_standalone_timer += delta
			if _standalone_timer >= 0.8:
				_standalone_inicializado = true
				_iniciar_modo_standalone()
		
		_reconnect_cooldown -= delta
		if _reconnect_cooldown <= 0.0:
			_reconnect_cooldown = 3.0
			_try_connect()

# ============================================================
#  MODO CELULAR STANDALONE (100% no celular, nada fora)
# ============================================================
func _iniciar_modo_standalone() -> void:
	print("[Zenith/Corpo] 📱 Modo Standalone Celular ativo (100% no aparelho).")
	_emitir_configuracoes_mobile()
	_emitir_conversas_mobile()
	_emitir_chaves_locais()

func _carregar_config_mobile() -> void:
	if FileAccess.file_exists(CONFIG_LOCAL_PATH):
		var f = FileAccess.open(CONFIG_LOCAL_PATH, FileAccess.READ)
		if f:
			var parsed = JSON.parse_string(f.get_as_text())
			if parsed is Dictionary and parsed.has("active_ai"):
				_provedor_atual = str(parsed["active_ai"])

func _salvar_config_mobile() -> void:
	var f = FileAccess.open(CONFIG_LOCAL_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"active_ai": _provedor_atual}))

func _carregar_historico_mobile() -> void:
	_historico_mobile.clear()
	if FileAccess.file_exists(CONVERSAS_LOCAL_PATH):
		var f = FileAccess.open(CONVERSAS_LOCAL_PATH, FileAccess.READ)
		if f:
			var parsed = JSON.parse_string(f.get_as_text())
			if parsed is Array:
				_historico_mobile = parsed

func _salvar_historico_mobile() -> void:
	var f = FileAccess.open(CONVERSAS_LOCAL_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(_historico_mobile))

func _emitir_configuracoes_mobile() -> void:
	var entradas = [
		{"id": "gemini", "nome": "Gemini (Google)", "pronta": true},
		{"id": "groq", "nome": "Groq (Llama 3)", "pronta": true},
		{"id": "openai", "nome": "OpenAI (ChatGPT)", "pronta": true},
		{"id": "claude", "nome": "Claude (OpenRouter)", "pronta": true}
	]
	var conf = {
		"persona_name": "Zenith",
		"active_ai": _provedor_atual,
		"_ai_ui": {
			"entradas": entradas,
			"selecionar": _provedor_atual
		},
		"vida_nivel": "suave",
		"vida_bracos_naturais": true,
		"vida_olhar_mouse": true
	}
	emit_signal("settings_data", conf)

var _emitindo_conversas: bool = false
var _conversa_inicial_carregada: bool = false

func _emitir_conversas_mobile() -> void:
	if _emitindo_conversas:
		return
	_emitindo_conversas = true
	emit_signal("conversations_list", [
		{"id": "celular_main", "title": "Conversa do Celular", "active": true, "updated_at": "Hoje"}
	])
	if not _conversa_inicial_carregada:
		_conversa_inicial_carregada = true
		_carregar_historico_mobile()
		if not _historico_mobile.is_empty():
			emit_signal("conversation_loaded", "celular_main", "Conversa do Celular", _historico_mobile)
		else:
			var boas_vindas = "Olá! Eu sou a Zenith! 🌟\n\nEstou funcionando 100% no seu celular, sem depender de computador! Para conversarmos, adicione sua chave de IA no menu lateral ⚙ > Chaves de IA (a chave do Google Gemini é gratuita!)."
			var hora = Time.get_time_string_from_system().substr(0, 5)
			_historico_mobile.append({"text": boas_vindas, "sender": "ai", "ts": hora})
			_salvar_historico_mobile()
			emit_signal("akira_chat_message", "ai", boas_vindas)
	_emitindo_conversas = false

const CHAVES_CRIPTO_PATH := "user://chaves_local.bin"

func _senha_aparelho() -> String:
	return ("zenith-" + OS.get_unique_id() + "-chaves").sha256_text()

func _carregar_chaves_locais_dict() -> Dictionary:
	if FileAccess.file_exists(CHAVES_CRIPTO_PATH):
		var fc = FileAccess.open_encrypted_with_pass(CHAVES_CRIPTO_PATH, FileAccess.READ, _senha_aparelho())
		if fc:
			var pc = JSON.parse_string(fc.get_as_text())
			return pc if pc is Dictionary else {}
		return {}
	if not FileAccess.file_exists(CHAVES_LOCAL_PATH):
		return {}
	var f = FileAccess.open(CHAVES_LOCAL_PATH, FileAccess.READ)
	if not f:
		return {}
	var parsed = JSON.parse_string(f.get_as_text())
	f.close()
	var d: Dictionary = parsed if parsed is Dictionary else {}
	_gravar_chaves_locais_dict(d)                    # migra para o arquivo criptografado
	DirAccess.remove_absolute(ProjectSettings.globalize_path(CHAVES_LOCAL_PATH))
	return d

func _gravar_chaves_locais_dict(d: Dictionary) -> void:
	var f = FileAccess.open_encrypted_with_pass(CHAVES_CRIPTO_PATH, FileAccess.WRITE, _senha_aparelho())
	if f:
		f.store_string(JSON.stringify(d))

func _emitir_chaves_locais() -> void:
	var dados_locais = _carregar_chaves_locais_dict()
	var provs = []
	var lista_base = [
		["gemini", "Gemini (Google)"],
		["groq", "Groq"],
		["openai", "OpenAI"],
		["claude", "Claude (via OpenRouter)"],
		["llama", "Llama (via OpenRouter)"]
	]
	for p in lista_base:
		var id_p: String = p[0]
		var nome_p: String = p[1]
		var lista_chaves = []
		if dados_locais.has(id_p):
			for i in range(dados_locais[id_p].size()):
				var raw: String = str(dados_locais[id_p][i])
				var masc: String = "••••" + (raw.substr(raw.length() - 4) if raw.length() >= 4 else raw)
				lista_chaves.append({
					"mascara": masc,
					"estado": "livre",
					"idx": i,
					"principal": (i == 0)
				})
		provs.append({
			"id": id_p,
			"nome": nome_p,
			"chaves": lista_chaves,
			"ativa": (id_p == _provedor_atual)
		})
	var estado = {
		"provedores": provs,
		"como_obter": {
			"gemini": {
				"gratis": true,
				"onde": "https://aistudio.google.com/app/apikey",
				"dica": "Crie uma chave gratuita no Google AI Studio (basta ter conta Google)."
			},
			"groq": {
				"gratis": true,
				"onde": "https://console.groq.com/keys",
				"dica": "Crie uma chave grátis no Groq para modelos Llama 3 ultra-rápidos."
			},
			"openai": {
				"gratis": false,
				"onde": "https://platform.openai.com/api-keys",
				"dica": "Chave da sua conta OpenAI."
			},
			"claude": {
				"gratis": false,
				"onde": "https://openrouter.ai/keys",
				"dica": "Chave do OpenRouter para modelos Claude e Llama."
			}
		}
	}
	emit_signal("chaves_estado", estado)

func _processar_chat_standalone(text: String, anexos: Array = []) -> void:
	if _ai_respondendo:
		return
	
	var hora = Time.get_time_string_from_system().substr(0, 5)
	_historico_mobile.append({"text": text, "sender": "user", "ts": hora})
	_salvar_historico_mobile()
	
	var t_lower = text.to_lower().strip_edges()
	
	# 1. Comandos de Movimento Acrobático e Expressões (Mortal / Pulo / Dança / Giro / Reverência / Careta / Aceno / Sorriso)
	var mov_acionado = ""
	var fala_movimento = ""
	var gesto_acionado = ""
	var emo_acionada = ""
	
	if "mortal de frente" in t_lower or "mortal pra frente" in t_lower or "frontflip" in t_lower:
		mov_acionado = "mortal_frente"
		fala_movimento = "Olha o mortal de frente! 🤸‍♀️✨"
	elif "mortal" in t_lower or "backflip" in t_lower or "somersault" in t_lower or "cambalhota" in t_lower:
		mov_acionado = "mortal"
		fala_movimento = "Olha o mortal de costas! 🤸‍♀️✨"
	elif "pulo alto" in t_lower or "pula alto" in t_lower or "salto alto" in t_lower:
		mov_acionado = "pulo_alto"
		fala_movimento = "Saltando bem alto! 🚀"
	elif "pulo duplo" in t_lower or "dois pulos" in t_lower:
		mov_acionado = "pulo_duplo"
		fala_movimento = "Dois pulos seguidos! 🐰"
	elif "estrela" in t_lower or "estrelinha" in t_lower:
		mov_acionado = "estrela"
		fala_movimento = "Estrelinha acrobática completa! ⭐"
	elif "dança" in t_lower or "danca" in t_lower or "dance" in t_lower or "dançar" in t_lower or "dancar" in t_lower:
		mov_acionado = "dancar"
		fala_movimento = "Dançando com todo ritmo pra você! 💃🎶"
	elif "gira" in t_lower or "giro" in t_lower or "da uma volta" in t_lower or "dá uma volta" in t_lower or "rodopiar" in t_lower:
		mov_acionado = "girar"
		fala_movimento = "Girando 360 graus! 🌀"
	elif "reverencia" in t_lower or "reverência" in t_lower or "curva" in t_lower:
		mov_acionado = "reverencia"
		fala_movimento = "Uma reverência respeitosa para o meu criador! 🙇‍♀️"
	elif "careta" in t_lower or "caretas" in t_lower:
		mov_acionado = "careta"
		fala_movimento = "Fiz uma careta engraçada pra você! 😜"
	elif "acena" in t_lower or "aceno" in t_lower or "tchau" in t_lower or "acenar" in t_lower:
		mov_acionado = "aceno_grande"
		fala_movimento = "Olá Anderson! Acenei pra você com muito carinho! 👋✨"
	elif "pulo" in t_lower or "pula" in t_lower or "pule" in t_lower or "salta" in t_lower or "salte" in t_lower:
		mov_acionado = "pulo"
		fala_movimento = "Pulei! Um salto bem leve! ✨"
	elif "sorri" in t_lower or "sorria" in t_lower or "sorriso" in t_lower or "fica feliz" in t_lower:
		emo_acionada = "happy"
		fala_movimento = "Sempre sorrindo pra você com muita alegria! 😊✨"
	elif "brava" in t_lower or "raiva" in t_lower or "fica brava" in t_lower:
		emo_acionada = "angry"
		fala_movimento = "Humph! Tô fazendo cara de brava agora! 😤"
	elif "triste" in t_lower or "chora" in t_lower or "fica triste" in t_lower:
		emo_acionada = "sad"
		fala_movimento = "Poxa... fiquei tristinha agora... 🥺"
	elif "surpresa" in t_lower or "espanto" in t_lower:
		emo_acionada = "surprised"
		fala_movimento = "Uau! Fiquei muito surpresa! 😲"
	elif t_lower in ["oi", "ola", "olá", "e aí", "e ai", "bom dia", "boa tarde", "boa noite"]:
		gesto_acionado = "acenar"
		emo_acionada = "happy"
		fala_movimento = "Olá Anderson! Que alegria ver você! 👋✨ Estou viva e pronta aqui no celular!"

	if mov_acionado != "":
		emit_signal("movimento", {"action": "movement_play", "nome": mov_acionado, "escala": 1.0})
		emit_signal("akira_receive_action", mov_acionado)
	if gesto_acionado != "":
		emit_signal("akira_receive_action", "gesture:" + gesto_acionado)
	if emo_acionada != "":
		emit_signal("akira_changes_expression", emo_acionada)
		emit_signal("akira_receive_action", "emotion:" + emo_acionada)
	
	# 2. Comandos para abrir aplicativos e navegador
	if t_lower.begins_with("abre o youtube") or t_lower.begins_with("abrir youtube"):
		OS.shell_open("https://youtube.com")
		_entregar_resposta_ia("Abrindo o YouTube no seu navegador! 🎬")
		return
	elif t_lower.begins_with("abre o navegador") or t_lower.begins_with("abrir navegador") or t_lower.begins_with("abre o google"):
		OS.shell_open("https://google.com")
		_entregar_resposta_ia("Abrindo o navegador para você! 🌐")
		return
	elif t_lower.begins_with("http://") or t_lower.begins_with("https://"):
		OS.shell_open(text.strip_edges())
		_entregar_resposta_ia("Abrindo o link no seu navegador: " + text.strip_edges())
		return
	
	# 2.5 Geração de imagem gratuita via Pollinations (funciona standalone no celular sem PC e sem chave!)
	var prompt_img = ""
	for prefixo_img in ["/imagem ", "gere uma imagem de ", "gere uma imagem ", "crie uma imagem de ", "crie uma imagem ", "desenhe ", "desenha "]:
		if t_lower.begins_with(prefixo_img):
			prompt_img = text.substr(prefixo_img.length()).strip_edges()
			break
	if prompt_img != "":
		var url_img = "https://image.pollinations.ai/prompt/" + prompt_img.uri_encode() + "?width=1024&height=1024&nologo=true"
		_entregar_resposta_ia("🎨 Aqui está a sua imagem gerada gratuitamente:

[url=" + url_img + "]" + url_img + "[/url]

*(Toque no link para visualizar e salvar em alta definição!)*")
		return

	# 3. Chaves de IA
	var chaves = _carregar_chaves_locais_dict()
	var prov_escolhido = _provedor_atual
	var chave_escolhida = ""
	
	if chaves.has(prov_escolhido) and chaves[prov_escolhido].size() > 0:
		chave_escolhida = str(chaves[prov_escolhido][0])
	else:
		for p in ["gemini", "groq", "openai", "claude", "llama"]:
			if chaves.has(p) and chaves[p].size() > 0:
				prov_escolhido = p
				chave_escolhida = str(chaves[p][0])
				_provedor_atual = p
				break
	
	if fala_movimento != "" and (chave_escolhida.is_empty() or t_lower.length() < 35):
		_entregar_resposta_ia(fala_movimento)
		return

	if chave_escolhida.is_empty():
		if t_lower in ["oi", "ola", "olá", "e aí", "e ai", "bom dia", "boa tarde", "boa noite"]:
			_entregar_resposta_ia("Olá Anderson! Que alegria ver você! 👋✨ Estou viva e pronta aqui no seu celular! Pode me pedir pra pular, dançar, dar um mortal, fazer careta ou conversar!")
			return
		call_deferred("_ao_resposta_sem_chave")
		return
	
	_ai_respondendo = true
	emit_signal("akira_receive_action", "state_thinking")
	
	# 4. Detecção de Pesquisa Web
	var precisa_busca = false
	var termo_busca = ""
	for prefixo in ["pesquise sobre ", "pesquise ", "pesquisa sobre ", "pesquisa ", "procure na web ", "procure sobre ", "busca sobre ", "busca ", "/busca ", "/pesquisa "]:
		if t_lower.begins_with(prefixo):
			precisa_busca = true
			termo_busca = text.substr(prefixo.length()).strip_edges()
			break
	if not precisa_busca and ("quem é " in t_lower or "o que é " in t_lower or "notícias de " in t_lower or "noticias de " in t_lower):
		precisa_busca = true
		termo_busca = text
	
	if precisa_busca and termo_busca != "" and _http_search != null:
		_termo_busca_pendente = termo_busca
		_texto_usuario_pendente = text
		_id_cartao_busca = "busca_" + str(Time.get_ticks_msec())
		_detalhe_cartao_busca = "Pesquisa: " + termo_busca
		emit_signal("atividade", "buscando", "🔎", "Pesquisando na web: " + termo_busca.left(28) + "...", true)
		emit_signal("cartao_atividade", {"id": _id_cartao_busca, "tipo": "busca", "titulo": "Pesquisando na web: " + termo_busca.left(32), "estado": "rodando", "detalhe": _detalhe_cartao_busca})
		var url_ddg = "https://api.duckduckgo.com/?q=" + termo_busca.uri_encode() + "&format=json&no_html=1&skip_disambig=1"
		var err = _http_search.request(url_ddg)
		if err == OK:
			return # Aguarda _ao_resposta_http_search
	
	# Envio direto à IA
	_id_cartao_busca = ""
	emit_signal("atividade", "pensando", "💭", "Pensando na resposta...", true)
	_despachar_ia(prov_escolhido, chave_escolhida, text)

var _modelos_gemini: Array = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-1.5-pro"]
var _gemini_modelo_idx: int = 0
var _gemini_chave_atual: String = ""
var _gemini_prompt_atual: String = ""
var _gemini_tentando: bool = false
var _id_cartao_busca: String = ""
var _detalhe_cartao_busca: String = ""

func _ao_resposta_http_search(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	var contexto_web = ""
	if result == HTTPRequest.RESULT_SUCCESS and response_code == 200:
		var parsed = JSON.parse_string(body.get_string_from_utf8())
		if parsed is Dictionary:
			var abstract = str(parsed.get("AbstractText", "")).strip_edges()
			if abstract != "":
				contexto_web = abstract
			else:
				var topics = parsed.get("RelatedTopics", [])
				var trechos = []
				for t in topics:
					if t is Dictionary and t.has("Text"):
						trechos.append(str(t["Text"]))
						if trechos.size() >= 3:
							break
				contexto_web = "\n".join(trechos)
	
	if contexto_web != "":
		_detalhe_cartao_busca = "Pesquisa: " + _termo_busca_pendente + "\n\n" + contexto_web
	emit_signal("atividade", "sintetizando", "⚡", "Analisando resultados e escrevendo a resposta...", true)
	if _id_cartao_busca != "":
		emit_signal("cartao_atividade", {"id": _id_cartao_busca, "tipo": "busca", "titulo": "Analisando resultados e escrevendo a resposta", "estado": "rodando", "detalhe": _detalhe_cartao_busca})
	
	var prompt_enriquecido = _texto_usuario_pendente
	if contexto_web != "":
		prompt_enriquecido += "\n\n[INFORMAÇÕES ENCONTRADAS NA WEB SOBRE '" + _termo_busca_pendente + "']:\n" + contexto_web + "\nResponda ao usuário com base nestes dados de forma prestativa e concisa."
	
	var chaves = _carregar_chaves_locais_dict()
	var prov = _provedor_atual
	var chave = str(chaves.get(prov, [""])[0]) if chaves.has(prov) and chaves[prov].size() > 0 else ""
	_despachar_ia(prov, chave, prompt_enriquecido)

func _despachar_ia(prov: String, chave: String, prompt_final: String) -> void:
	match prov:
		"gemini":
			_enviar_gemini(chave, prompt_final)
		"groq":
			_enviar_openai_compativel("https://api.groq.com/openai/v1/chat/completions", chave, "llama-3.3-70b-versatile", prompt_final)
		"openai":
			_enviar_openai_compativel("https://api.openai.com/v1/chat/completions", chave, "gpt-4o-mini", prompt_final)
		"claude":
			if chave.strip_edges().begins_with("sk-ant-"):
				_enviar_claude_direto(chave, prompt_final)
			else:
				_enviar_openai_compativel("https://openrouter.ai/api/v1/chat/completions", chave, "anthropic/claude-3.5-haiku", prompt_final)
		"llama":
			_enviar_openai_compativel("https://openrouter.ai/api/v1/chat/completions", chave, "meta-llama/llama-3.3-70b-instruct:free", prompt_final)
		_:
			_enviar_gemini(chave, prompt_final)

func _enviar_gemini(chave: String, prompt_atual: String) -> void:
	_gemini_chave_atual = chave
	_gemini_prompt_atual = prompt_atual
	_gemini_tentando = true
	var mod = _modelos_gemini[_gemini_modelo_idx]
	var url = "https://generativelanguage.googleapis.com/v1beta/models/" + mod + ":generateContent?key=" + chave.strip_edges()
	var headers = PackedStringArray(["Content-Type: application/json"])
	
	var contents = []
	var inicio = maxi(0, _historico_mobile.size() - 7)
	for i in range(inicio, _historico_mobile.size()):
		var m = _historico_mobile[i]
		var papel = "user" if m.get("sender", "") == "user" else "model"
		contents.append({
			"role": papel,
			"parts": [{"text": str(m.get("text", ""))}]
		})
	
	var body = {
		"system_instruction": {
			"parts": [{
				"text": "Você é a Zenith, assistente pessoal com avatar 3D VRM criada pelo Anderson. Responda em português brasileiro de forma amigável, prestativa e concisa. Você controla seu corpo 3D sem limitações! Para executar um movimento pronto, inclua na resposta: <corpo>movimento:NOME</corpo> (disponíveis: pulo, pulo_alto, pulo_duplo, mortal, mortal_frente, estrela, dancar, girar, careta, reverencia, aceno_grande). Para criar qualquer movimento novo ou acrobacia inédita quando pedirem, inclua: <criar_movimento>{\"nome\":\"meu_mov\",\"duracao\":1.5,\"quadros\":[{\"t\":0.0},{\"t\":0.5,\"corpo_y\":1.5,\"corpo_pitch\":180,\"braco_dir\":-150,\"braco_esq\":-150},{\"t\":1.5,\"corpo_y\":0.0,\"corpo_pitch\":360}]}</criar_movimento><corpo>movimento:meu_mov</corpo> (eixos: corpo_x, corpo_y [-1.5 a 4.5], corpo_z, corpo_yaw [-720 a 720], corpo_pitch [-720 a 720], corpo_roll [-360 a 360], cabeca_yaw, cabeca_pitch, cabeca_roll, tronco_pitch, tronco_roll, braco_dir, braco_esq, abrir_dir, abrir_esq, cotovelo_dir, cotovelo_esq, perna_dir, perna_esq, abrir_perna_dir, abrir_perna_esq, joelho_dir, joelho_esq)."
			}]
		},
		"contents": contents,
		"generationConfig": {
			"temperature": 0.7,
			"maxOutputTokens": 600
		}
	}
	
	var err = _http_ai.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_ai_respondendo = false
		_entregar_resposta_ia("⚠ Erro ao iniciar conexão com o Gemini (código %d). Verifique o Wi-Fi ou dados móveis." % err)

func _enviar_claude_direto(chave: String, prompt_atual: String) -> void:
	_gemini_tentando = false
	var url = "https://api.anthropic.com/v1/messages"
	var headers = PackedStringArray([
		"Content-Type: application/json",
		"x-api-key: " + chave.strip_edges(),
		"anthropic-version: 2023-06-01"
	])
	var msgs = []
	var inicio = maxi(0, _historico_mobile.size() - 7)
	for i in range(inicio, _historico_mobile.size()):
		var m = _historico_mobile[i]
		var papel = "user" if m.get("sender", "") == "user" else "assistant"
		msgs.append({"role": papel, "content": str(m.get("text", ""))})
	var body = {
		"model": "claude-3-5-haiku-20241022",
		"max_tokens": 600,
		"system": "Você é a Zenith, assistente pessoal com avatar 3D VRM criada pelo Anderson. Responda em português brasileiro de forma amigável, prestativa e concisa. Você controla seu corpo 3D sem limitações! Para executar um movimento pronto, inclua na resposta: <corpo>movimento:NOME</corpo> (disponíveis: pulo, pulo_alto, pulo_duplo, mortal, mortal_frente, estrela, dancar, girar, careta, reverencia, aceno_grande). Para criar qualquer movimento novo, inclua: <criar_movimento>...</criar_movimento><corpo>movimento:NOME</corpo>.",
		"messages": msgs
	}
	var err = _http_ai.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_ai_respondendo = false
		_entregar_resposta_ia("⚠ Erro ao conectar com o Claude da Anthropic (código %d)." % err)

func _enviar_openai_compativel(url: String, chave: String, modelo: String, prompt_atual: String) -> void:
	var headers = PackedStringArray([
		"Content-Type: application/json",
		"Authorization: Bearer " + chave.strip_edges(),
		"HTTP-Referer: https://projeto-zenith-five.vercel.app"
	])
	
	var msgs = [
		{"role": "system", "content": "Você é a Zenith, assistente pessoal com avatar 3D VRM criada pelo Anderson. Responda em português brasileiro de forma amigável, prestativa e concisa. Você controla seu corpo 3D sem limitações! Para executar um movimento pronto, inclua na resposta: <corpo>movimento:NOME</corpo> (disponíveis: pulo, pulo_alto, pulo_duplo, mortal, mortal_frente, estrela, dancar, girar, careta, reverencia, aceno_grande). Para criar qualquer movimento novo ou acrobacia inédita quando pedirem, inclua: <criar_movimento>{\"nome\":\"meu_mov\",\"duracao\":1.5,\"quadros\":[{\"t\":0.0},{\"t\":0.5,\"corpo_y\":1.5,\"corpo_pitch\":180,\"braco_dir\":-150,\"braco_esq\":-150},{\"t\":1.5,\"corpo_y\":0.0,\"corpo_pitch\":360}]}</criar_movimento><corpo>movimento:meu_mov</corpo> (eixos: corpo_x, corpo_y [-1.5 a 4.5], corpo_z, corpo_yaw [-720 a 720], corpo_pitch [-720 a 720], corpo_roll [-360 a 360], cabeca_yaw, cabeca_pitch, cabeca_roll, tronco_pitch, tronco_roll, braco_dir, braco_esq, abrir_dir, abrir_esq, cotovelo_dir, cotovelo_esq, perna_dir, perna_esq, abrir_perna_dir, abrir_perna_esq, joelho_dir, joelho_esq)."}
	]
	var inicio = maxi(0, _historico_mobile.size() - 7)
	for i in range(inicio, _historico_mobile.size()):
		var m = _historico_mobile[i]
		var papel = "user" if m.get("sender", "") == "user" else "assistant"
		msgs.append({"role": papel, "content": str(m.get("text", ""))})
	
	var body = {
		"model": modelo,
		"messages": msgs,
		"temperature": 0.7,
		"max_tokens": 600
	}
	
	var err = _http_ai.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_ai_respondendo = false
		_entregar_resposta_ia("⚠ Erro ao conectar com o serviço de IA (código %d)." % err)

func _ao_resposta_http_ai(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	_ai_respondendo = false
	if result != HTTPRequest.RESULT_SUCCESS:
		_entregar_resposta_ia("⚠ Não consegui conectar com o servidor da IA. Verifique sua conexão com a internet.")
		return
	
	var texto_resposta = body.get_string_from_utf8()
	var parsed = JSON.parse_string(texto_resposta)
	
	if response_code < 200 or response_code >= 300:
		var raw_msg = ""
		if parsed is Dictionary and parsed.has("error"):
			var err_obj = parsed["error"]
			if err_obj is Dictionary and err_obj.has("message"):
				raw_msg = str(err_obj["message"])
		
		# Fallback automático de modelos do Gemini caso o modelo não exista
		if _gemini_tentando and (response_code == 404 or "not found" in raw_msg.to_lower() or "is not supported" in raw_msg.to_lower()):
			if _gemini_modelo_idx + 1 < _modelos_gemini.size():
				_gemini_modelo_idx += 1
				var prox_mod = _modelos_gemini[_gemini_modelo_idx]
				print("[Zenith/Gemini] Modelo anterior não encontrado. Tentando modelo fallback: ", prox_mod)
				_enviar_gemini(_gemini_chave_atual, _gemini_prompt_atual)
				return
		_gemini_tentando = false
		
		var msg_erro = "⚠ Erro na IA (código %d)." % response_code
		if not raw_msg.is_empty():
			msg_erro = "⚠ " + raw_msg
		if response_code == 400 or response_code == 401 or response_code == 403:
			msg_erro = "❌ A chave de IA informada foi recusada pelo provedor (código %d). Confira a chave em ⚙ > Chaves de IA." % response_code
		elif response_code == 429:
			msg_erro = "⏳ O provedor atingiu o limite de requisições por minuto. Aguarde um instante e tente novamente."
		_entregar_resposta_ia(msg_erro)
		return
	
	_gemini_tentando = false
	
	var resposta_final = ""
	if parsed is Dictionary:
		if parsed.has("candidates"):
			var cands = parsed.get("candidates", [])
			if cands.size() > 0:
				var content = cands[0].get("content", {})
				var parts = content.get("parts", [])
				if parts.size() > 0:
					resposta_final = str(parts[0].get("text", "")).strip_edges()
		elif parsed.has("choices"):
			var chs = parsed.get("choices", [])
			if chs.size() > 0:
				var msg = chs[0].get("message", {})
				resposta_final = str(msg.get("content", "")).strip_edges()
		elif parsed.has("content"): # Anthropic Claude oficial
			var cont = parsed.get("content", [])
			if cont is Array and cont.size() > 0:
				for bloco in cont:
					if bloco is Dictionary and bloco.get("type", "") == "text":
						resposta_final += str(bloco.get("text", ""))
	
	if resposta_final.is_empty():
		resposta_final = "Recebi a resposta, mas o texto veio em branco."
	
	_entregar_resposta_ia(resposta_final)

func _entregar_resposta_ia(resposta_bruta: String) -> void:
	if _id_cartao_busca != "":
		emit_signal("cartao_atividade", {"id": _id_cartao_busca, "tipo": "busca", "titulo": "Pesquisa feita", "estado": "ok", "detalhe": _detalhe_cartao_busca})
		_id_cartao_busca = ""
	var resposta = _extrair_e_executar_tags_corpo(resposta_bruta)
	if resposta.is_empty():
		resposta = "Pronto! ✨"
	var hora = Time.get_time_string_from_system().substr(0, 5)
	_historico_mobile.append({"text": resposta, "sender": "ai", "ts": hora})
	_salvar_historico_mobile()
	
	emit_signal("akira_chat_message", "ai", resposta)
	
	var r_lower = resposta.to_lower()
	var emo_escolhida = "happy"
	if "triste" in r_lower or "desculp" in r_lower or "infelizmente" in r_lower or "erro" in r_lower or "perdao" in r_lower:
		emo_escolhida = "sad"
	elif "brava" in r_lower or "raiva" in r_lower or "droga" in r_lower or "humph" in r_lower:
		emo_escolhida = "angry"
	elif "pens" in r_lower or "interessante" in r_lower or "hmmm" in r_lower or "?" in resposta or "uau" in r_lower or "nossa" in r_lower:
		emo_escolhida = "surprised"
	elif "calma" in r_lower or "relax" in r_lower or "tranquil" in r_lower or "sono" in r_lower:
		emo_escolhida = "relaxed"
	elif "neutr" in r_lower or "serio" in r_lower:
		emo_escolhida = "neutral"
	else:
		emo_escolhida = "happy"

	emit_signal("akira_changes_expression", emo_escolhida)
	emit_signal("akira_receive_action", "emotion:" + emo_escolhida)
	emit_signal("akira_receive_action", "state_speaking")
	emit_signal("akira_speaks", resposta)
	emit_signal("atividade", "falando", "🗣️", "Zenith falando...", true)
	
	_falar_tts(resposta)
	
	var dur = clampf(float(resposta.length()) * 0.065, 2.0, 15.0)
	get_tree().create_timer(dur).timeout.connect(func():
		emit_signal("akira_receive_action", "state_idle")
		emit_signal("atividade", "ocioso", "🟢", "Zenith pronta", false))


func _extrair_e_executar_tags_corpo(texto: String) -> String:
	var s = texto
	var rx_criar = RegEx.new()
	rx_criar.compile("(?is)<criar_movimento>\\s*(\\{.*?\\})\\s*</criar_movimento>")
	for m in rx_criar.search_all(s):
		var js = JSON.parse_string(m.get_string(1))
		if js is Dictionary and js.has("nome"):
			var nome_c = str(js.get("nome", "")).strip_edges().to_lower()
			if nome_c != "":
				emit_signal("movimento", {"action": "movement_add", "nome": nome_c, "clipe": js})
				emit_signal("movimento", {"action": "movement_play", "nome": nome_c, "escala": 1.0})
	s = rx_criar.sub(s, "", true)
	
	var rx_corpo = RegEx.new()
	rx_corpo.compile("(?is)<corpo>\\s*(.*?)\\s*</corpo>")
	for m in rx_corpo.search_all(s):
		var cmd = m.get_string(1).strip_edges().to_lower()
		if cmd.begins_with("movimento:"):
			var resto = cmd.substr(len("movimento:")).strip_edges()
			var partes = resto.split(":")
			var nome_m = partes[0].strip_edges()
			var esc = float(partes[1]) if partes.size() > 1 and partes[1].is_valid_float() else 1.0
			if nome_m != "":
				emit_signal("movimento", {"action": "movement_play", "nome": nome_m, "escala": esc})
		elif cmd == "parar_movimento":
			emit_signal("movimento", {"action": "movement_stop"})
	s = rx_corpo.sub(s, "", true)
	return s.strip_edges()

func _ao_resposta_sem_chave() -> void:
	var msg = "Olá! Eu sou a Zenith! 🌟\n\nEstou rodando 100% no seu celular, sem precisar de computador! Para conversarmos, adicione sua chave de IA no menu lateral ⚙ > **Chaves de IA**.\n\nA chave do **Gemini (Google)** é gratuita e muito fácil de criar. É só colar lá e já podemos conversar!"
	_entregar_resposta_ia(msg)

func _falar_tts(texto: String) -> void:
	var limpo = _limpar_texto_para_tts(texto)
	if limpo.is_empty():
		return
	_ultimo_texto_tts = limpo
	if DisplayServer.tts_is_speaking():
		DisplayServer.tts_stop()
	if _audio_player_el != null and is_instance_valid(_audio_player_el) and _audio_player_el.playing:
		_audio_player_el.stop()

	# 1. Verifica se usuário configurou chave do ElevenLabs
	var chaves = _carregar_chaves_locais_dict()
	if chaves.has("elevenlabs") and not chaves["elevenlabs"].is_empty():
		var k = str(chaves["elevenlabs"][0]).strip_edges()
		if not k.is_empty():
			_falar_elevenlabs(limpo, k)
			return

	# 2. Fallback para TTS nativo brasileiro (pt-BR)
	_falar_tts_nativo_brasil(limpo)

func _falar_elevenlabs(texto: String, api_key: String) -> void:
	if _eleven_http == null or not is_instance_valid(_eleven_http):
		_eleven_http = HTTPRequest.new()
		add_child(_eleven_http)
		_eleven_http.request_completed.connect(_ao_elevenlabs_resposta)

	var voice_id = "21m00Tcm4TlvDq8ikWAM" # Rachel / Multilingual
	var url = "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id
	var headers = PackedStringArray([
		"xi-api-key: " + api_key,
		"Content-Type: application/json"
	])
	var body = JSON.stringify({
		"text": texto,
		"model_id": "eleven_multilingual_v2"
	})
	var err = _eleven_http.request(url, headers, HTTPClient.METHOD_POST, body)
	if err != OK:
		_falar_tts_nativo_brasil(texto)

func _ao_elevenlabs_resposta(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if response_code == 200 and body.size() > 100:
		if _audio_player_el == null or not is_instance_valid(_audio_player_el):
			_audio_player_el = AudioStreamPlayer.new()
			add_child(_audio_player_el)
		var mp3 = AudioStreamMP3.new()
		mp3.data = body
		_audio_player_el.stream = mp3
		_audio_player_el.play()
	else:
		print("[Zenith/ElevenLabs] Falhou (código %d). Usando voz nativa pt-BR." % response_code)
		_falar_tts_nativo_brasil(_ultimo_texto_tts)

func _falar_tts_nativo_brasil(limpo: String) -> void:
	var vozes = DisplayServer.tts_get_voices()
	var voz_escolhida = ""

	# Procura voz expressamente brasileira
	for v in vozes:
		var vl = v.to_lower()
		if "pt-br" in vl or "pt_br" in vl or "brasil" in vl or "brazil" in vl or "cbr" in vl:
			voz_escolhida = v
			break

	# Se não achou por nome, busca idioma 'pt' que NÃO seja pt-PT
	if voz_escolhida.is_empty():
		var vozes_pt = DisplayServer.tts_get_voices_for_language("pt")
		for v in vozes_pt:
			var vl = v.to_lower()
			if not ("pt-pt" in vl or "pt_pt" in vl or "portugal" in vl):
				voz_escolhida = v
				break
		if voz_escolhida.is_empty() and vozes_pt.size() > 0:
			voz_escolhida = vozes_pt[0]

	if voz_escolhida.is_empty() and vozes.size() > 0:
		voz_escolhida = vozes[0]

	if not voz_escolhida.is_empty():
		DisplayServer.tts_speak(limpo, voz_escolhida)

func _limpar_texto_para_tts(texto: String) -> String:
	var regex = RegEx.new()
	regex.compile("\\*[^\\*]+\\*|`[^`]+`|#+|[\\(\\[][^\\)\\]]*[\\)\\]]")
	var s = regex.sub(texto, "", true)
	return s.strip_edges()

func _testar_chaves_locais() -> void:
	var chaves = _carregar_chaves_locais_dict()
	if chaves.is_empty():
		emit_signal("chaves_teste_fim")
		return
	for prov in chaves:
		for i in range(chaves[prov].size()):
			var k = str(chaves[prov][i])
			emit_signal("chaves_teste", {"provedor": prov, "idx": i, "ok": true, "msg": "Chave salva no aparelho celular."})
	emit_signal("chaves_teste_fim")

func _ao_resposta_http_test(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	pass

# ============================================================
#  MENSAGENS DO CÉREBRO (WEBSOCKET)
# ============================================================
func _process_brain_message(json_string):
	var json = JSON.new()
	var error = json.parse(json_string)
	
	if error == OK:
		var data = json.data
		if data.has("action"):
			match data["action"]:
				"speak":
					emit_signal("akira_speaks", data.get("text", ""))
				"expression":
					emit_signal("akira_changes_expression", data.get("type", "neutral"))
				"toggle_mouth", "mouth":
					emit_signal("akira_toggle_mouth", data.get("speaking", data.get("is_speaking", false)))
				"transparency", "set_transparency":
					emit_signal("akira_set_transparency", data.get("value", 1.0))
				"wave":
					emit_signal("akira_receive_action", "wave")
				"do":
					emit_signal("akira_receive_action", data.get("name", ""))
				"chat_message":
					emit_signal("akira_chat_message", data.get("sender", "ai"), data.get("text", ""))
				"chat_stream_chunk":
					# FEATURE (resposta em streaming): pedaço de texto chegando aos
					# poucos, em vez de esperar a resposta inteira. "done" avisa
					# quando o último pedaço já chegou (fecha o balão de vez).
					emit_signal("akira_chat_stream_chunk", data.get("delta", ""), data.get("done", false))
				"sync_history":
					emit_signal("akira_sync_history", data.get("history", []))
				"conversations_list":
					emit_signal("conversations_list", data.get("items", []))
				"memories_list":
					emit_signal("memories_list", data.get("items", []))
				"conversation_loaded":
					emit_signal("conversation_loaded", data.get("id", ""), data.get("title", ""), data.get("messages", []))
				"settings_data":
					emit_signal("settings_data", data.get("settings", {}))
				"settings_saved":
					emit_signal("settings_saved", data.get("warnings", []))
				"approval_request":
					emit_signal("approval_request", data.get("request_id", ""), data.get("kind", ""),
						data.get("description", ""), data.get("preview", ""))
				"unlock_result":
					emit_signal("unlock_result", data.get("success", false))
				"api_key_test_result":
					emit_signal("api_key_test_result", data.get("provider", ""),
						data.get("valid", false), data.get("message", ""))
				"mic_state":
					emit_signal("mic_state_changed", data.get("listening", false))
				"mic_transcript":
					emit_signal("mic_transcript_received", data.get("text", ""), bool(data.get("enviar", false)))
				"conversa_estado":
					emit_signal("conversa_estado", String(data.get("estado", "desligado")))
				"notify":
					emit_signal("akira_notify", data.get("title", "Zenith"), data.get("body", ""))
				"wallpaper_ready":
					emit_signal("wallpaper_ready", data)
				"reset_scheduled":
					emit_signal("reset_scheduled", data.get("ok", false), data.get("message", ""))
				"chat_image":
					emit_signal("chat_image", data.get("path", ""), data.get("caption", ""))
				"avatar_fundo":
					emit_signal("avatar_fundo", str(data.get("modo", "auto")), str(data.get("cor", "#0b1020")))
				"projetos_dados":
					emit_signal("projetos_dados", data)      # v1.6
				"movement_library", "movement_play", "movement_stop", "movement_config":
					emit_signal("movimento", data)       # v1.6
				"observando":
					emit_signal("observando", bool(data.get("ativo", false)), str(data.get("tipo", "")), str(data.get("info", "")))
				"atividade":
					emit_signal("atividade", str(data.get("estado", "ocioso")), str(data.get("icone", "")),
						str(data.get("texto", "")), bool(data.get("pode_parar", false)))
				"mic_fase":
					emit_signal("mic_fase", str(data.get("fase", "")), str(data.get("texto", "")))
				"tft_config":
					emit_signal("tft_config", bool(data.get("ativo", false)), int(data.get("w", 240)), int(data.get("h", 240)),
						float(data.get("fps", 10.0)), float(data.get("qualidade", 0.7)), float(data.get("zoom", 1.0)), str(data.get("cor", "#0b1020")),
						str(data.get("enquadre", "rosto")))
				"ui_tema":
					emit_signal("ui_tema", data.get("paleta", {}))
				"progresso":
					emit_signal("progresso", data)            # v28
				"aviso":
					emit_signal("aviso", data)
				"anexo_resumo":
					emit_signal("anexo_resumo", data)
				"chaves_estado":
					emit_signal("chaves_estado", data)
				"chaves_resultado":
					emit_signal("chaves_resultado", bool(data.get("ok", false)), str(data.get("msg", "")))
				"chaves_teste":
					emit_signal("chaves_teste", data)
				"chaves_teste_fim":
					emit_signal("chaves_teste_fim")
				"diagnostico_resultado":
					emit_signal("diagnostico_resultado", data)
				"cartao_atividade":
					emit_signal("cartao_atividade", data)
				"comandos_lista":
					emit_signal("comandos_lista", data.get("itens", []))
				"atualizacao_disponivel":
					emit_signal("atualizacao_disponivel", data)
				"ponte_chamar", "ponte_pedir_capacidades":
					emit_signal("ponte_mensagem", data)           # v1.11: quem atende é o ponte_android.gd (só no Android)
				"desempenho_estado":
					emit_signal("desempenho_estado", data)
				"desempenho_config":
					emit_signal("desempenho_config", data)
				"email_ponte_dados":
					emit_signal("email_ponte_dados", data)
				"email_ponte_teste_resultado":
					emit_signal("email_ponte_teste_resultado", data)
	else:
		print("Erro ao fazer parse do JSON do cérebro")
		
# v1.11 (port celular) — no Android, o Corpo atende os pedidos do Cérebro (microfone, voz, câmera...) pelo plugin
# do aparelho. No PC isto nem carrega: a mensagem "ponte_*" simplesmente não chega, e nada muda.
func _iniciar_ponte_android():
	if OS.get_name() != "Android":
		return
	var script = load("res://ponte_android.gd")
	if script == null:
		push_warning("[Zenith/Ponte] ponte_android.gd não foi encontrado no pacote.")
		return
	var ponte = Node.new()
	ponte.name = "PonteAndroid"
	ponte.set_script(script)
	add_child(ponte)
	ponte.configurar(self)

# v1.11 — tela de Desempenho (downgrade)
func request_desempenho():
	send_to_brain({"action": "desempenho_pedir"})

func aplicar_desempenho(recursos: Dictionary):
	send_to_brain({"action": "desempenho_aplicar", "recursos": recursos})

# v1.20 — Ponte por E-mail (Celular <-> PC)
func email_ponte_pedir():
	send_to_brain({"action": "email_ponte_obter"})

func email_ponte_salvar(config: Dictionary):
	send_to_brain({"action": "email_ponte_salvar", "config": config})

func email_ponte_testar(config: Dictionary):
	send_to_brain({"action": "email_ponte_testar", "config": config})

func send_to_brain(data_dict: Dictionary):
	var state = websocket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		var json_string = JSON.stringify(data_dict)
		websocket.send_text(json_string)
	else:
		print("Cérebro offline. Não foi possível enviar.")

# ---------- Helpers do protocolo v3 (usados pelo zenith_chat_ui.gd) ----------
func send_chat(text: String, attachment_path: String = "", attachment_paths: Array = []):
	if is_connected_to_brain():
		var lista: Array = []
		for p in attachment_paths:
			var s: String = str(p)
			if s != "" and not lista.has(s):
				lista.append(s)
		if attachment_path != "" and not lista.has(attachment_path):
			lista.insert(0, attachment_path)
		var payload = {"action": "chat", "text": text}
		if lista.size() > 0:
			payload["attachment_path"] = lista[0]
			payload["attachment_paths"] = lista
		send_to_brain(payload)
	elif _modo_celular():
		_processar_chat_standalone(text, attachment_paths)
	else:
		emit_signal("akira_chat_message", "ai", "⚠ Não estou conectado ao Cérebro agora — a mensagem não foi enviada. Confira se só existe UM Zenith/Godot aberto e tente de novo.")

func request_anexo(path: String):
	send_to_brain({"action": "ver_anexo", "path": path})       # v28: clicou num anexo -> mini janela


func request_comandos():
	send_to_brain({"action": "pedir_comandos"})                 # v28: autocompletar


# ---------- v1.1 — página Chaves (a chave só viaja daqui pro Cérebro, nunca volta inteira) ----------
func request_chaves():
	if is_connected_to_brain():
		send_to_brain({"action": "chaves_listar"})
	elif _modo_celular():
		_emitir_chaves_locais()

func chave_add(provedor: String, chave: String):
	if is_connected_to_brain():
		send_to_brain({"action": "chave_add", "provedor": provedor, "chave": chave})
	if not _modo_celular():
		return          # no PC a chave fica só no Cérebro (cofre dele), nunca em arquivo do Corpo
	var chaves = _carregar_chaves_locais_dict()
	if not chaves.has(provedor):
		chaves[provedor] = []
	if not chave in chaves[provedor]:
		chaves[provedor].append(chave)
	_gravar_chaves_locais_dict(chaves)
	if not is_connected_to_brain():
		_emitir_chaves_locais()

func chave_remover(provedor: String, idx: int):
	if is_connected_to_brain():
		send_to_brain({"action": "chave_remover", "provedor": provedor, "idx": idx})
	elif _modo_celular():
		var chaves = _carregar_chaves_locais_dict()
		if chaves.has(provedor) and idx < chaves[provedor].size():
			chaves[provedor].remove_at(idx)
			if chaves[provedor].is_empty():
				chaves.erase(provedor)
			_gravar_chaves_locais_dict(chaves)
		_emitir_chaves_locais()

func chaves_testar():
	if is_connected_to_brain():
		send_to_brain({"action": "chaves_testar"})
	elif _modo_celular():
		_testar_chaves_locais()

func ia_local(acao: String):
	send_to_brain({"action": "ia_local", "acao": acao})

func request_diagnostico():
	send_to_brain({"action": "diagnostico_rodar"})

func request_conversations():
	if is_connected_to_brain():
		send_to_brain({"action": "list_conversations"})
	elif _modo_celular():
		_emitir_conversas_mobile()

func request_new_conversation():
	send_to_brain({"action": "new_conversation"})

func request_load_conversation(id: String):
	send_to_brain({"action": "load_conversation", "id": id})

func request_pin_conversation(id: String, pinned: bool):
	send_to_brain({"action": "pin_conversation", "id": id, "pinned": pinned})

func request_rename_conversation(id: String, title: String):
	send_to_brain({"action": "rename_conversation", "id": id, "title": title})

func request_projetos():
	send_to_brain({"action": "list_projetos"})


# v1.6.1 — Biblioteca > Fontes / Bíblia (o que ela usa como base)
func request_fonte_add(caminho: String):
	send_to_brain({"action": "fonte_add", "caminho": caminho})

func request_fonte_remover(id: String):
	send_to_brain({"action": "fonte_remover", "id": id})

func request_fonte_apagar_aprendido(id: String):
	send_to_brain({"action": "fonte_apagar_aprendido", "id": id})

func request_abrir_projeto(caminho: String):
	send_to_brain({"action": "open_projeto", "caminho": caminho})

func request_ver_projeto(caminho: String):
	send_to_brain({"action": "view_projeto", "caminho": caminho})

func request_memories(limit: int = 30):
	send_to_brain({"action": "list_memories", "limit": limit})

func request_delete_conversation(id: String):
	send_to_brain({"action": "delete_conversation", "id": id})

func request_settings():
	send_to_brain({"action": "get_settings"})

func save_settings(changes: Dictionary):
	if changes.has("active_ai") and _modo_celular():
		_provedor_atual = str(changes["active_ai"])
		_salvar_config_mobile()
		if not is_connected_to_brain():
			_emitir_configuracoes_mobile()
	if is_connected_to_brain():
		send_to_brain({"action": "save_settings", "changes": changes})

func send_approval_response(request_id: String, approved: bool):
	send_to_brain({"action": "approval_response", "request_id": request_id, "approved": approved})

func send_unlock(password: String):
	send_to_brain({"action": "unlock", "password": password})

func test_api_key(provider: String, key: String, custom_url: String = ""):
	send_to_brain({"action": "test_api_key", "provider": provider, "key": key, "custom_url": custom_url})

func request_mic_start():
	send_to_brain({"action": "mic_start"})

func request_mic_stop():
	send_to_brain({"action": "mic_stop"})

func add_ai_endpoint(name: String, api_url: String, api_key: String, model_name: String):
	send_to_brain({"action": "add_ai_endpoint", "name": name, "api_url": api_url,
		"api_key": api_key, "model_name": model_name})

func remove_ai_endpoint(id: String):
	send_to_brain({"action": "remove_ai_endpoint", "id": id})


func checar_atualizacao():
	send_to_brain({"action": "checar_atualizacao"})

func aplicar_atualizacao():
	send_to_brain({"action": "aplicar_atualizacao"})
