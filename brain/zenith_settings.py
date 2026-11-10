# ============================================================
#  ZENITH — Sistema de IA Companheira Corporificada
#  Criado por Anderson Ricardo de Souza Filho
#
#  zenith_settings.py — Fonte ÚNICA de configuração do sistema.
#  Este é o ÚNICO lugar onde a configuração é lida e salva.
#  (Substitui: akira_settings.py, akira_config.py,
#   akira_user_settings.json e user://akira_settings.cfg)
# ============================================================

import json
import os
import sys
import threading
from pathlib import Path

# ---------- Estrutura de pastas do projeto ----------
# CORREÇÃO (bug do executável): __file__ funciona certo rodando via
# "python zenith_launcher.py" (aponta pra pasta real do projeto), mas
# no .exe compilado com --onedir o PyInstaller extrai os módulos Python
# pra dentro de dist/Zenith/_internal/ — __file__ passava a apontar pra
# lá, e BASE_DIR virava "dist/Zenith/_internal" em vez de "dist/Zenith"
# (onde está o Zenith.exe de verdade). Resultado: config/, temp/,
# memory_db/ e creations/ ficavam escondidos dentro de _internal — daí
# o backend "desconectando", módulos "sumindo", papel de parede e
# conversas não carregando. Agora, quando frozen, BASE_DIR é sempre a
# pasta onde está o .exe de verdade.
def _resolve_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = _resolve_base_dir()   # Zenith/ (ou dist/Zenith/ no .exe)
CONFIG_DIR  = BASE_DIR / "config"                      # config única (fica sempre
                                                        # aqui — precisa existir
                                                        # ANTES de sabermos se o
                                                        # usuário escolheu outra
                                                        # pasta de dados, já que
                                                        # é essa config que diz
                                                        # qual pasta ele escolheu)

SETTINGS_FILE = CONFIG_DIR / "settings.json"

# FEATURE (pasta de dados única, escolhida pelo usuário): TEMP_DIR,
# CREATION_DIR e MEMORY_DIR são lidos por outros arquivos como
# constantes fixas (`from brain.zenith_settings import MEMORY_DIR`),
# calculadas uma única vez aqui na importação do módulo — ANTES da
# classe ZenithSettings existir de verdade. Por isso, pra permitir uma
# pasta customizada, a única forma é ler esse UM campo direto do JSON
# cru agora, sem esperar o ZenithSettings normal (que só termina de
# montar depois). Se o usuário nunca configurou nada em Configurações >
# Corpo, cai no padrão de sempre (pastas dentro de BASE_DIR).
# v1.4 — o INSTALADOR pergunta "onde ficam suas criações e dados?" e grava a resposta em config/instalacao.json.
# Vale só quando o usuário ainda não escolheu outra pasta em Configurações (o settings.json manda).
INSTALACAO_FILE = CONFIG_DIR / "instalacao.json"


def _ler_data_root(arquivo) -> Path | None:
    try:
        with open(arquivo, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        root = str(raw.get("data_root_path", "") or "").strip()
        return Path(os.path.expandvars(root)) if root else None
    except Exception:
        return None


def _read_data_root_override() -> Path | None:
    return _ler_data_root(SETTINGS_FILE) or _ler_data_root(INSTALACAO_FILE)

_data_root = _read_data_root_override()
TEMP_DIR     = (_data_root / "temp")      if _data_root else BASE_DIR / "temp"
CREATION_DIR = (_data_root / "creations") if _data_root else BASE_DIR / "creations"
MEMORY_DIR   = (_data_root / "memory_db") if _data_root else BASE_DIR / "memory_db"
# FEATURE (portabilidade — pen drive / computador sem internet): antes,
# o faster-whisper baixava o modelo de transcrição pro cache global do
# Windows (fora da pasta do Zenith) na primeira vez que o microfone
# fosse usado — então copiar dist/Zenith pra um pen drive e levar pra
# outro PC NÃO levava o modelo junto, e o app tentava baixar de novo
# (falhando se não tivesse internet lá). Agora o modelo fica DENTRO da
# própria pasta do Zenith — baixa uma vez (com internet), e a partir
# daí faz parte do que você copia pro pen drive, funcionando 100%
# offline no computador de destino.
MODELS_DIR   = (_data_root / "models")    if _data_root else BASE_DIR / "models"

# Arquivos antigos do projeto Zenith — usados só na migração única
_LEGACY_FILES = [
    BASE_DIR / "akira_user_settings.json",
    BASE_DIR / "system_settings.json",
    BASE_DIR / "brain" / "system_settings.json",
    BASE_DIR / "brain" / "akira_user_settings.json",
]

# ---------- Configuração padrão ----------
# Regra de identidade (IMUTÁVEL no código, não fica na config):
#   Zenith  = nome do SISTEMA  (de Anderson)
#   persona = nome da IA DAQUELE USUÁRIO (padrão: "Zenith")
#   user    = nome do usuário humano (antes era "Anderson" fixo)
DEFAULT_SETTINGS = {
    "_version": 1,

    # --- Identidade (cada usuário personaliza a SUA IA) ---
    "persona_name": "Zenith",            # nome da IA deste usuário
    "user_name": "",                    # nome do humano (vazio = "Usuário")
    "persona_description": "",          # texto livre: como a IA deve ser
    "user_pillars": "",                 # pilares extras do usuário
    # FEATURE (distribuição/pen drive — primeiro login zerado): fica
    # False numa instalação nova (sem settings.json ainda, ou copiada
    # zerada de propósito pra pen drive). O Corpo (Godot) mostra a tela
    # de boas-vindas/criação da IA enquanto isso for False, e só marca
    # True depois que a pessoa escolhe (ou confirma) o nome da IA — daí
    # em diante entra direto no chat normal, nesse mesmo computador.
    "onboarding_done": False,

    # --- APIs de raciocínio ---
    # NUNCA deixe uma chave real fixa aqui — esse arquivo pode ir pro Git.
    "gemini_key": "",
    "openai_key": "",
    "openrouter_key": "",
    "groq_key": "",
    # v30 — "infinitas APIs da mesma IA": chaves EXTRAS por provedor, usadas em rodízio quando
    # a principal estoura a cota. A principal continua no campo de sempre (acima). Formato:
    # {"gemini": ["...", "..."], "openai": ["..."], "custom:<id>": ["..."]}. Também aceita
    # config/chaves.txt (uma por linha: gemini = AIza...). Ver brain/zenith_chaves.py.
    "chaves_extras": {},
    # v30 — "singularidade": preferência de rota por capacidade (texto | visao | imagem).
    # Ex.: {"visao": "openai"} = para ver imagem use a OpenAI mesmo que a ativa seja outra.
    "rota_preferida": {},
    # v30 — o que cada IA sabe fazer, para as personalizadas/locais que têm modelo multimodal.
    # Ex.: {"custom:abc123": ["texto", "visao"]}. Ver brain/zenith_rota.py.
    "ia_capacidades": {},
    # v30 — IA local OPCIONAL (Ollama/LM Studio no próprio PC): entra como reserva, sem chave.
    "ia_local_ativa": False,
    "ia_local_url": "",                  # "" = procura o Ollama (11434) e o LM Studio (1234) sozinho
    "ia_local_modelo": "",               # "" = o primeiro já baixado, senão qwen2.5:1.5b
    "ia_local_papel": "reserva",          # reserva (padrão) | principal
    "ia_local_baixar_sozinho": False,     # True = baixa o modelo sem perguntar (só se VOCÊ ligar isso)
    "tavily_api_key": "",                # OPCIONAL: a busca na web/imagens funciona SEM chave (v21); com chave, a Tavily é tentada primeiro
    "response_streaming": True,          # resposta em pedaços (efeito "digitando") após passar pela segurança
    "multi_step_actions": True,          # deixa uma ação aprovada encadear a próxima sozinha (ainda com aprovação a cada passo)
    # FEATURE (modo econômico vs pensante): só tem efeito com o Gemini
    # (2.5 Flash), único provedor cujo SDK aqui expõe controle de
    # "thinking budget" (tokens extras de raciocínio antes de responder,
    # cobrados à parte). "economico" desliga esse raciocínio extra
    # (thinking_budget=0) — mais rápido e mais barato, ideal pro dia a
    # dia. "pensante" liga o modo dinâmico (thinking_budget=-1): o
    # PRÓPRIO Gemini decide, pergunta por pergunta, se vale a pena gastar
    # tokens pensando antes de responder — não é a Zenith "sempre
    # pensando mais", é ela raciocinando fundo só quando a pergunta
    # realmente precisar. Outros provedores (OpenAI/Groq/local) ignoram
    # essa configuração — cada um já decide isso à própria maneira.
    "thinking_mode": "pensante",         # "economico" | "pensante" — v22: o padrão agora é PENSANTE (raciocínio ligado; o econômico deixava o Gemini bem mais "burro")
    # v22 — inteligência, contexto e programas
    "contexto_modo": "max",              # quanto da conversa vai junto a cada pergunta: max | equilibrado | economico | desligado
    # v23 — o padrão era gemini-2.5-flash (duas gerações atrás). Agora gemini-3.5-flash (estável). Se um modelo
    # sumir ou a cota dele acabar, o Zenith tenta o próximo da lista sozinho. Veja /modelos e /modelo gemini <id>.
    "gemini_modelo": "gemini-3.5-flash",
    "gemini_modelo_v23": False,          # marca interna: a troca única do 2.5-flash antigo pelo modelo novo já foi feita?
    "velocidade": "rapido",              # v24: rapido | equilibrado | profundo (quanto ela "pensa" antes de falar) — /velocidade
    "streaming_real": True,              # v24: texto e voz saem frase a frase ENQUANTO o modelo gera (False = espera tudo, como antes)
    # v24 — display TFT no ESP32-S3 (USB): detectado sozinho (porta Espressif); veja /tft e firmware/
    # v25 — pendências/projeto (ela não esquece o que você pediu) e tema de cores da interface
    "projeto_ativo": "",                 # nome do arquivo em config/projetos/ (ex.: "etec") — o roteiro vai em toda mensagem
    "ui_tema_preset": "ciano",           # ciano azul roxo rosa vermelho laranja amarelo verde turquesa cinza amoled claro
    "ui_tema_destaque": "",              # "#rrggbb" — sobrescreve só a cor de destaque
    "ui_tema_fundo": "",                 # "#rrggbb" — sobrescreve a cor base (o resto é derivado)
    "tft_enquadre": "rosto",             # rosto | busto | corpo — quanto da Zenith aparece no display
    "tft_ativo": True,
    "tft_porta": "",                     # "" = automático (VID 0x303A); ou "COM7" pra placa com ponte USB-serial
    "tft_baud": 115200,                  # os dois firmwares fazem Serial.begin(115200); o app ainda tenta 921600 sozinho
    "tft_fps": 10,
    "tft_qualidade": 70,                 # JPEG %, 30–95
    "tft_zoom": 1.0,                     # >1 aproxima do rosto
    "tft_cor": "#0b1020",                # fundo atrás da Zenith no display
    "saida_max_tokens": 32768,           # teto de resposta do Gemini (inclui o raciocínio); era 8192 e cortava código longo
    # v23 — fundo da janela do avatar: "auto" | "transparente" | "solido" | "chroma" (verde, pra OBS).
    # Em alguns PCs/drivers a transparência não funciona e o fundo vira um quadrado PRETO; /fundo_avatar solido resolve.
    "avatar_fundo_modo": "auto",
    "avatar_fundo_cor": "#0b1020",
    # v23 — habilidades que ela mesma cria (pasta skills/) e observação ao vivo (câmera/tela)
    "habilidades_ativas": True,
    "atitude_validador": True,           # v23: refaz 1x a resposta que pede licença em texto / dá desculpa pronta em vez de agir
    "comandos_auto": True,               # v23: ela pode acionar comandos de leitura/estilo (/contexto, /modo...) sozinha
    "habilidades_confiaveis": [],        # nomes que o usuário marcou pra rodar sem perguntar de novo (/habilidade confiar x)
    "observar_intervalo_s": 20,          # a cada quantos segundos ela olha (mín. 8)
    "observar_max_minutos": 15,          # pára sozinha depois disso (precisa pedir de novo)
    "movimentos_ativos": True,            # v1.6 — pulo, dança, câmera, caretas (brain/zenith_movimentos.py)
    "movimentos_janela": True,            # v1.6 — deixa a janela do avatar andar/pular pela tela
    "movimentos_camera": True,            # v1.6 — deixa ela aproximar/afastar a câmera
    "persona_migrada_v16": False,         # v1.6 — marca que o nome antigo "Akira" já foi trocado por "Zenith" (uma vez só)  # legado-ok
    "sem_emoji": True,                   # v1.4 — tira emoji do chat (visual próprio, sem figurinha de terceiros)
    "captura_sem_zenith": True,          # v1.4 — esconde as janelas do Zenith por um instante ao tirar print da tela
    "atualizar_url": "https://projeto-zenith-five.vercel.app/versions.json",  # v1.5 — endereço do versions.json
    "microfone_sempre": False,           # v1.5 — modo conversa (microfone aberto); desligado por padrão
    "modelos_override": {},              # ex.: {"openai": "nome-do-modelo"} — troca o modelo de um slot sem mexer no código
    "biblia_validador": True,            # confere o formato das etiquetas e pede UMA correção automática
    "programas_python_exe": "",           # caminho de um python.exe pra rodar programas criados ('' = automático)
    "programas_espera_s": 6,             # segundos que ela espera o programa antes de dizer "está rodando"
    "custom_api_url": "",
    "custom_api_key": "",
    "custom_api_model": "",
    "active_ai": "gemini",              # gemini|openai|claude|llama|groq|custom|custom:<id>
    # FEATURE (Gerenciador Dinâmico de Endpoints de IA): em vez de só o
    # ÚNICO slot "custom" de cima, isso aqui é uma LISTA — o usuário pode
    # adicionar quantas IAs compatíveis com a API da OpenAI quiser
    # (LLMs locais tipo LM Studio/Ollama, ou qualquer serviço na nuvem
    # que fale esse protocolo), cada uma com nome/endpoint/chave/modelo
    # próprios. Cada uma vira um provider selecionável chamado
    # "custom:<id>" em active_ai.
    "ai_endpoints": [],   # cada item: {"id","name","api_url","api_key","model_name"}

    # --- Voz ---
    "elevenlabs_key": "",
    "elevenlabs_voice_id": "",
    "rvc_model_path": "",
    "rvc_index_path": "",
    "rvc_python_exe": "",               # v20: python.exe (3.10) do venv do RVC — vazio = procura tools/rvc/venv
    "tts_volume": 0.8,
    "voice_enabled": True,          # interruptor "Desativar voz" das Configurações
    "voice_expression_modulation": True,   # v14: tom/velocidade do Edge-TTS variam com a emoção (liga/desliga: /voz_emocao)
    "voice_expression_intensity": 1.8,     # v14: 0.0–2.0, multiplica a variação acima
    "aviso_inicial_visto": False,   # v18: o aviso de primeiro uso (zenith_boas_vindas.py) aparece uma vez
    "modo_atual": "normal",         # v18: /modo estudo|lab|codigo|normal (só ajusta o estilo; ver zenith_modos.py)
    "notify_on_chain_end": True,    # v14: avisa (barra de tarefas + notificação do Windows) quando uma ação em cadeia termina e a Central não está em foco
    # v18 — importação automática de avatar (brain/zenith_vrm_import.py). O
    # Zenith descobre TUDO sozinho (editor do Godot, projeto, preset, .pck em
    # uso). Estas chaves são só "overrides" opcionais — vazio = autodetectar.
    # Na tela, só aparece "Editor do Godot" (vrm_auto_import_godot_bin).
    "vrm_auto_import_godot_bin": "",       # executável do EDITOR do Godot (só se não achar sozinho)
    "vrm_auto_import_project_dir": "",     # avançado: pasta do projeto Godot (padrão: body/zenith)
    "vrm_auto_import_preset": "",          # avançado: nome do preset (padrão: o 1º "Windows Desktop")
    "vrm_auto_import_pck_destino": "",     # sem uso desde o v18 (o .pck é deduzido do Corpo); mantido por compatibilidade
    "proactive_enabled": True,      # fala espontânea depois de inatividade
    "proactive_minutes": 15,        # quantos minutos sem mensagem até puxar assunto
    # FEATURE (modo mãos-livres / walkie-talkie): "manual" é o antigo
    # comportamento (aperta pra começar, aperta de novo pra parar).
    # "auto" liga a detecção de silêncio: aperta uma vez e ela já fica
    # "sempre ouvindo" até você parar de falar, sem precisar apertar de
    # novo. mic_max_seconds também deixa configurável o teto de
    # segurança (antes era 60s fixo no código).
    "mic_mode": "manual",           # manual | auto
    "mic_silence_ms": 900,          # silêncio (ms) pra considerar que parou de falar, no modo auto
    "mic_max_seconds": 60,          # trava de segurança, mesmo no modo auto
    # v29 — QUAL MICROFONE usar e o mínimo de som pra considerar que você falou.
    # Vazio = o microfone padrão do Windows (era o único comportamento até agora).
    # Se o Zenith responder "não entendi nada", a própria resposta mostra o volume
    # medido; se ele estiver baixinho, troque o microfone aqui pelo NOME exato que
    # aparece em Configurações de som > Entrada do Windows (ex.: "Microfone (Brio 105)")
    # ou pelo número da lista (o comando de diagnóstico da voz lista os disponíveis).
    "mic_device": "",               # nome ou número do microfone ("" = padrão do Windows)
    # 0.06 não é chute: medido no PC do Anderson, o chiado da sala com o microfone aberto
    # deu pico de 0.013 numa medição e 0.032 em outra (ventilador, vizinhança) — e fala normal
    # fica entre 0.1 e 0.6. Com 0.03 o plano B chegaria a rodar em cima de ruído; com 0.06, não.
    "mic_nivel_minimo": 0.06,       # pico (0..1) mínimo pra considerar que houve fala, não chiado
    "mic_sem_vad_fallback": True,   # se o filtro de silêncio do Whisper descartar tudo, tenta sem ele
    # v27 — TRANSCRIÇÃO DO MICROFONE. Estas cinco chaves já eram LIDAS por
    # zenith_interaction.py (com valor padrão no .get()), só que não estavam aqui: por isso
    # não apareciam no settings.json, não davam pra ajustar em lugar nenhum, e ficavam
    # invisíveis — foi assim que o Anderson ficou sem entender por que a transcrição ao vivo
    # não ia acompanhando a fala. Agora aparecem no arquivo e dá pra mexer sem editar código.
    "whisper_modelo": "small",         # tiny | base | small | medium — menor = mais rápido e menos preciso
    "whisper_beam": 1,                 # 1 = mais rápido (greedy); 5 = mais preciso e bem mais lento
    "mic_transcricao_ao_vivo": True,   # ir escrevendo na caixa de texto enquanto você fala
    "mic_parcial_intervalo": 1.0,      # segundos entre uma transcrição parcial e a próxima
    "whisper_precarregar": True,       # carrega o modelo ao abrir o Zenith (a 1ª fala não espera)

    # --- Corpo / Avatar ---
    "vrm_model_path": "",
    "body_transparency": 1.0,
    "vrm_window_position": 0,   # 0=sup.direito 1=inf.direito 2=sup.esquerdo 3=inf.esquerdo
    "vrm_window_size": "420x640",
    "vrm_click_through": True,
    # v20 — vida do avatar (expressões, boca, braços naturais, gestos, olhar o mouse)
    "vida_nivel": "suave",              # desligado | suave | expressivo
    "vida_bracos_naturais": True,       # desce os braços da T-pose (apontando por direção, sem depender dos eixos do modelo)
    "vida_olhar_mouse": True,           # a cabeça acompanha o cursor, devagar
    "vida_gestos_ia": True,             # gestos automáticos conforme o que ela diz (oi, sim, não, parabéns...)

    # --- Aparência do chat ---
    "chat_wallpaper_path": "",          # imagem/vídeo de fundo do chat (vazio = sem papel de parede)
    "chat_wallpaper_dim": 0.35,          # 0 = nada escurecido, 1 = totalmente preto (legibilidade do texto)

    # --- Integração com o Godot (Corpo) ---
    "godot_executable_path": "",        # .exe exportado do Corpo, OU o godot.exe do motor
    "godot_project_path": "",           # só usado se godot_executable_path apontar pro motor (godot.exe --path X)
    "auto_launch_godot": True,          # abrir o Corpo automaticamente junto com a Central de Controle

    # --- Visão (gravação de tela, não print) ---
    "screen_record_seconds": 8,         # duração da gravação p/ análise
    "camera_mode": "photo",             # photo | video (futuro)

    # --- Comandos e código (tempo máximo) ---
    "tempo_comando_s": 60,             # v1.11 — antes era 15 s fixos, e download/
                                        # raspagem (yt-dlp, pip, build) nunca cabiam.
                                        # Vale de 15 a 1800 (30 min).

    # --- Permissões (Gatekeeper) ---
    "permissions": {
        "screen":     "ask",            # ask | always | never
        "microphone": "ask",
        "camera":     "ask",
        "run_code":   "ask",            # NOVO: código/terminal sempre pede
        "terminal":   "ask",
        "serial":     "ask",            # NOVO: Arduino/ESP32
        "web_search": "ask",            # busca na web e de imagens (sem chave de API) — ask | always | never
    },

    # --- Pastas (relativas à raiz do Zenith) ---
    "output_folder": "",                # vazio = usa creations/ padrão
    "data_root_path": "",                # FEATURE: pasta única pra memória de
                                          # longo prazo, temporários e criações —
                                          # vazio = usa as pastas padrão dentro
                                          # da instalação do Zenith. Precisa
                                          # REINICIAR o Zenith depois de mudar
                                          # (os módulos leem isso na largada).

    # --- Segurança ---
    "unlock_password": "",              # p/ desbloquear Stranger Danger (Fase 2)
}


class ZenithSettings:
    """Gerenciador da configuração única. Thread-safe, com merge de defaults
    e migração automática dos arquivos antigos (uma única vez)."""

    _lock = threading.Lock()

    def __init__(self):
        self._ensure_folders()
        self.settings = self._load_with_migration()

    # ---------- Pastas ----------
    def _ensure_folders(self):
        for d in (CONFIG_DIR, TEMP_DIR, CREATION_DIR, MEMORY_DIR, MODELS_DIR):
            d.mkdir(parents=True, exist_ok=True)

    # ---------- Leitura ----------
    def _load_with_migration(self) -> dict:
        merged = self._deep_copy_defaults()

        # 1) Migração única: importa chaves NÃO VAZIAS dos arquivos antigos
        if not SETTINGS_FILE.exists():
            for legacy in _LEGACY_FILES:
                if legacy.exists():
                    try:
                        with open(legacy, "r", encoding="utf-8") as f:
                            old = json.load(f)
                        for k, v in old.items():
                            # só importa valores úteis (não vazios)
                            if k in merged and v not in ("", None, {}):
                                merged[k] = v
                        print(f"[Zenith] Config antiga importada de: {legacy.name}")
                    except Exception as e:
                        print(f"[Zenith] Ignorando config antiga ({legacy.name}): {e}")

        # 2) Lê a config oficial (se existir) por cima
        if SETTINGS_FILE.exists():
            # CORREÇÃO (tela de boas-vindas aparecendo pra quem já usava o
            # Zenith): "onboarding_done" é uma config NOVA. Sem isso, todo
            # mundo que já tinha um settings.json de antes (sem essa chave)
            # caía no valor padrão (False) e via a tela de primeiro login
            # de novo, como se fosse instalação nova. Regra certa: só é
            # "primeira vez" de verdade quando settings.json NUNCA existiu
            # (pen drive/instalação nova), ou quando alguém zera ele de
            # propósito (prepare_pendrive.py grava "onboarding_done": false
            # explicitamente). Se o arquivo já existia e só não tinha essa
            # chave ainda, assume que a pessoa já passou por isso.
            merged["onboarding_done"] = True
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = self._deep_merge(merged, data)
            except Exception as e:
                print(f"[Zenith] ERRO ao ler settings.json ({e}). Usando padrões.")

        # v1.6 — o nome antigo da IA vira "Zenith" UMA vez. Depois disso o nome é escolha de quem usa
        # (Configurações > Identidade): se a pessoa colocar o nome antigo de novo, fica.
        if not merged.get("persona_migrada_v16", False):
            if str(merged.get("persona_name", "")).strip() == "Akira":     # legado-ok
                merged["persona_name"] = "Zenith"
            merged["persona_migrada_v16"] = True

        self._save_dict(merged)  # persiste sempre (cria arquivo / normaliza)
        return merged

    @staticmethod
    def _deep_copy_defaults() -> dict:
        return json.loads(json.dumps(DEFAULT_SETTINGS))

    @staticmethod
    def _deep_merge(base: dict, incoming: dict) -> dict:
        """Merge profundo: defaults nunca desaparecem, e sub-dicts (permissions)
        são mesclados chave a chave, não substituídos inteiros."""
        for k, v in incoming.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                ZenithSettings._deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    # ---------- Escrita ----------
    def save(self, new_settings: dict):
        with self._lock:
            merged = self._deep_merge(self._deep_copy_defaults(), new_settings)
            self._save_dict(merged)
            self.settings = merged

    def update(self, changes: dict):
        """Atualiza só as chaves recebidas (sem apagar o resto).
        É o que a Ponte usa quando o Godot manda update_config."""
        with self._lock:
            self.settings = self._deep_merge(self.settings, changes)
            self._save_dict(self.settings)

    @staticmethod
    def _save_dict(d: dict):
        tmp = SETTINGS_FILE.with_suffix(".tmp")   # escrita atômica
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=4, ensure_ascii=False)
        os.replace(tmp, SETTINGS_FILE)

    # ---------- Acesso ----------
    def get(self, key, fallback=None):
        val = self.settings.get(key)
        if val in ("", None):
            if fallback is not None:
                return fallback
            return DEFAULT_SETTINGS.get(key)
        return val

    # ---------- Helpers de identidade ----------
    @property
    def persona_name(self) -> str:
        return self.get("persona_name", "Zenith")

    @property
    def user_name(self) -> str:
        return self.get("user_name") or "Usuário"

    # ---------- Caminhos resolvidos ----------
    @property
    def temp_path(self) -> Path:
        return TEMP_DIR

    @property
    def creations_path(self) -> Path:
        custom = self.get("output_folder")
        p = Path(custom) if custom else CREATION_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p