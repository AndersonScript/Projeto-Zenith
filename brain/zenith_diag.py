"""
Zenith — "Testar tudo" (/diagnostico) e "Relatório de diagnóstico" (/relatorio).

/diagnostico confere, na hora, o que costuma dar problema: pasta de dados,
chaves de IA (só SE existem — o valor nunca aparece), bibliotecas, ffmpeg,
microfone, câmera (só a biblioteca — nunca abre a câmera), voz, rede, a Ponte
com o Corpo e a importação automática de avatar. Mostra ✓ / ⚠ / ✗ com a causa.

/relatorio monta um texto pra colar num pedido de ajuda. Ele NUNCA inclui:
chaves/senhas (mascaradas), conteúdo de conversas, memórias, notas, nome do
usuário nem descrição da persona. Caminhos de usuário do Windows/Linux têm o
nome da pessoa trocado por <usuario>.

Nada aqui levanta exceção pra quem chamou: cada checagem é isolada — se uma
falhar por bug, vira um ⚠ "não consegui checar", e as outras seguem.
"""
import datetime
import importlib.metadata
import importlib.util
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from brain import zenith_actionlog as _actionlog
from brain import zenith_version

OK, AVISO, ERRO = "ok", "aviso", "erro"
_ICONE = {OK: "✓", AVISO: "⚠", ERRO: "✗"}

# (nome do import, nome no pip, pra que serve, essencial?)
_BIBLIOTECAS = [
    ("websockets", "websockets", "conversa com o Corpo", True),
    ("chromadb", "chromadb", "memória de longo prazo", True),
    ("onnxruntime", "onnxruntime", "embeddings da memória", False),
    ("openai", "openai", "OpenAI / Groq / endpoints compatíveis", False),
    ("google.genai", "google-genai", "Gemini", False),
    ("edge_tts", "edge-tts", "voz gratuita", False),
    ("pygame", "pygame-ce", "tocar o áudio da voz", False),
    ("sounddevice", "sounddevice", "microfone", False),
    ("faster_whisper", "faster-whisper", "transcrever o microfone", False),
    ("cv2", "opencv-python-headless", "câmera", False),
    ("mss", "mss", "captura de tela", False),
    ("PIL", "Pillow", "papel de parede", False),
    ("serial", "pyserial", "Arduino/ESP32", False),
    ("plyer", "plyer", "notificação nativa do Windows", False),
    ("requests", "requests", "ElevenLabs", False),
]


def _tem_modulo(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _versao_pip(nome_pip: str) -> str:
    for n in (nome_pip, nome_pip.replace("-", "_")):
        try:
            return importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "?"


def _item(nome, status, detalhe=""):
    return {"nome": nome, "status": status, "detalhe": detalhe}


def _pastas_de_dados() -> dict:
    from brain.zenith_settings import CONFIG_DIR, CREATION_DIR, MEMORY_DIR, TEMP_DIR
    return {"config": Path(CONFIG_DIR), "temporários": Path(TEMP_DIR),
            "criações": Path(CREATION_DIR), "memória": Path(MEMORY_DIR)}


def _checar_pasta(nome: str, pasta: Path):
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / ".zenith_teste_escrita"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
        return _item(f"Pasta de {nome}", OK, str(pasta))
    except OSError as e:
        return _item(f"Pasta de {nome}", ERRO, f"não consigo gravar em {pasta} ({e})")


def _checar_chaves(settings):
    chaves = {"Gemini": "gemini_key", "OpenAI": "openai_key", "OpenRouter": "openrouter_key",
              "Groq": "groq_key", "Tavily (busca na web)": "tavily_api_key",
              "ElevenLabs (voz)": "elevenlabs_key"}
    tem = [n for n, k in chaves.items() if str(settings.get(k, "") or "").strip()]
    extras = settings.get("ai_endpoints", []) or []
    n_extras = len([e for e in extras if isinstance(e, dict) and e.get("api_url")])
    ia = [n for n in tem if n in ("Gemini", "OpenAI", "OpenRouter", "Groq")]
    if not ia and not n_extras and not str(settings.get("custom_api_url", "") or "").strip():
        return _item("Chaves de IA", ERRO, "nenhuma IA configurada — em Configurações > IAs & Chaves")
    partes = ", ".join(tem) if tem else "só endpoints personalizados"
    if n_extras:
        partes += f" + {n_extras} endpoint(s) personalizado(s)"
    return _item("Chaves de IA", OK, f"configuradas: {partes} (valores nunca são mostrados)")


def _checar_microfone():
    if not _tem_modulo("sounddevice"):
        return _item("Microfone", AVISO, "biblioteca 'sounddevice' não instalada")
    try:
        import sounddevice as sd
        entradas = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        if not entradas:
            return _item("Microfone", AVISO, "nenhum dispositivo de entrada encontrado")
        return _item("Microfone", OK, f"{len(entradas)} dispositivo(s) de entrada")
    except Exception as e:
        return _item("Microfone", AVISO, f"não consegui listar dispositivos ({e})")


# Controle Inteligente de Aplicativos (Smart App Control, Windows 11): bloqueia programa SEM
# assinatura digital que ele não reconheça pela reputação na nuvem — exatamente o caso do
# Zenith.exe e do Corpo (Godot) gerados localmente. Estado em
# HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy, valor VerifiedAndReputablePolicyState
# (0 = desligado, 1 = ligado/bloqueando, 2 = modo de avaliação — só observa).
_SAC_CHAVE = r"SYSTEM\CurrentControlSet\Control\CI\Policy"
_SAC_VALOR = "VerifiedAndReputablePolicyState"


def _ler_valor_sac():
    """int | None (None = não deu pra ler / não existe). Só faz sentido no Windows."""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SAC_CHAVE) as chave:
            valor, _tipo = winreg.QueryValueEx(chave, _SAC_VALOR)
        return int(valor)
    except (OSError, ValueError, ImportError):
        return None


def estado_controle_inteligente():
    """(codigo, texto). codigo: "nao_windows" | "desconhecido" | "desligado" | "ligado" | "avaliacao"."""
    if os.name != "nt":
        return "nao_windows", "não se aplica (não é Windows)"
    valor = _ler_valor_sac()
    if valor == 1:
        return "ligado", "LIGADO — bloqueia programas sem assinatura digital"
    if valor == 2:
        return "avaliacao", "em modo de avaliação (a Microsoft diz que nesse modo só observa; pode passar a bloquear)"
    if valor == 0:
        return "desligado", "desligado"
    if valor is None:
        return "desconhecido", "não consegui ler o estado (pode não existir neste Windows)"
    return "desconhecido", f"valor inesperado ({valor})"


def _checar_controle_inteligente():
    codigo, texto = estado_controle_inteligente()
    nome = "Controle Inteligente de Aplicativos"
    if codigo == "ligado":
        return _item(nome, AVISO, texto + ". O Zenith.exe e o Godot do Corpo não têm assinatura digital: se o "
                     "Corpo (avatar/Central) não abrir, é ele — veja NOTES_ANTIVIRUS.md")
    if codigo == "avaliacao":
        return _item(nome, AVISO, texto)
    if codigo == "nao_windows":
        return _item(nome, OK, texto)
    return _item(nome, OK, texto)


def _checar_rede(timeout=2.0):
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=timeout):
            pass
        return _item("Internet", OK, "conexão de saída funciona (nenhum dado seu foi enviado)")
    except OSError as e:
        return _item("Internet", AVISO, f"sem conexão de saída ({e}) — IAs na nuvem e busca não funcionam")


def _checar_ponte(porta=8765):
    try:
        with socket.socket() as s:
            s.settimeout(1.0)
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return _item("Ponte com o Corpo", OK, f"porta {porta} aberta (só localhost)")
        return _item("Ponte com o Corpo", AVISO, f"porta {porta} fechada — o Cérebro não está ouvindo")
    except OSError as e:
        return _item("Ponte com o Corpo", AVISO, f"não consegui checar ({e})")


# ---------------- v1.2 — checagens do que REALMENTE deu problema nos testes do dia a dia ----------------
# (voz que "sumiu", /video sem ffmpeg mesmo depois do pip, .pyd barrado pelo Windows, .exe sem administrador)
_PISTAS_BLOQUEIO = ("bloque", "blocked", "4551", "application control", "controle inteligente",
                    "dll load failed", "access is denied", "acesso negado", "smart app")
_NATIVOS = [("_pybase64", "base64 rápido (vai dentro do .exe)"), ("numpy", "cálculos"), ("PIL._imaging", "imagens")]


def _parece_bloqueio(msg: str) -> bool:
    baixo = (msg or "").lower()
    return any(p in baixo for p in _PISTAS_BLOQUEIO)


def _checar_ffmpeg(base_dir=None):
    """Acha o ffmpeg do MESMO jeito que o /video acha (PATH, tools/ffmpeg, imageio-ffmpeg) e confere se ele RODA."""
    try:
        from brain import zenith_video
        exe = zenith_video.achar_ffmpeg(str(base_dir or ""))
    except Exception as e:
        return _item("ffmpeg", AVISO, f"não consegui procurar ({e})")
    if not exe:
        return _item("ffmpeg", AVISO, "não encontrado — o /video e a conversão de fundo precisam dele. "
                                      "No terminal do Zenith: pip install imageio-ffmpeg (e abra o Zenith de novo)")
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=8)
        saida = (r.stdout or r.stderr or "").strip().splitlines()
        primeira = saida[0][:70] if saida else "sem resposta"
        if r.returncode == 0:
            return _item("ffmpeg", OK, primeira)
        return _item("ffmpeg", ERRO, f"achei, mas não executou (código {r.returncode}) — {anonimizar(exe)}")
    except Exception as e:
        dica = " — parece bloqueio do Windows/antivírus" if _parece_bloqueio(str(e)) else ""
        return _item("ffmpeg", ERRO, f"achei em {anonimizar(exe)}, mas não consegui rodar ({str(e)[:80]}){dica}")


def _checar_nativos():
    """Módulos compilados (.pyd) são os que o Windows barra com mais frequência. Só acusa se o módulo EXISTE e não carrega."""
    problemas = []
    for modulo, uso in _NATIVOS:
        try:
            if importlib.util.find_spec(modulo) is None:
                continue
        except Exception:
            continue
        try:
            importlib.import_module(modulo)
        except Exception as e:
            msg = str(e)
            dica = " — parece BLOQUEIO do Windows (Controle Inteligente/antivírus): veja NOTES_ANTIVIRUS.md" if _parece_bloqueio(msg) else ""
            problemas.append(_item(f"Módulo nativo {modulo}", ERRO, f"não carregou ({anonimizar(msg)[:90]}) — {uso}{dica}"))
    return problemas or _item("Módulos nativos", OK, "carregam normalmente")


def _checar_admin():
    if os.name != "nt":
        return _item("Administrador", OK, "não se aplica fora do Windows")
    try:
        import ctypes
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        return _item("Administrador", AVISO, f"não consegui descobrir ({e})")
    if admin:
        return _item("Administrador", OK, "sim")
    if getattr(sys, "frozen", False):
        return _item("Administrador", AVISO, "não — na PRIMEIRA vez, o Zenith.exe precisa ser aberto como administrador "
                                             "(botão direito → Executar como administrador)")
    return _item("Administrador", OK, "não (modo desenvolvimento; tudo bem)")


def _checar_disco(pastas=None):
    alvo = None
    for _, p in (pastas if pastas is not None else _pastas_de_dados()).items():
        alvo = Path(p)
        break
    if alvo is None:
        return _item("Espaço em disco", AVISO, "não sei qual pasta checar")
    while not alvo.exists() and alvo.parent != alvo:
        alvo = alvo.parent
    try:
        livre = shutil.disk_usage(str(alvo)).free
    except Exception as e:
        return _item("Espaço em disco", AVISO, f"não consegui checar ({e})")
    gb = livre / (1024 ** 3)
    if gb < 0.2:
        return _item("Espaço em disco", ERRO, f"só {gb:.1f} GB livres — vídeos, importações e a memória podem falhar")
    if gb < 1.0:
        return _item("Espaço em disco", AVISO, f"{gb:.1f} GB livres — pouco para vídeos e avatares")
    return _item("Espaço em disco", OK, f"{gb:.0f} GB livres")


def _checar_saida_audio():
    """A voz toca por pygame.mixer: se ele não abre a saída de áudio, ela 'fala' mas você não ouve nada."""
    if not _tem_modulo("pygame"):
        return _item("Saída de áudio", AVISO, "biblioteca pygame não instalada — sem ela a voz não toca")
    try:
        import pygame
        ja_aberto = pygame.mixer.get_init()
        if not ja_aberto:
            pygame.mixer.init()
        info = pygame.mixer.get_init()
        if not ja_aberto:
            pygame.mixer.quit()
        return _item("Saída de áudio", OK, f"responde ({info[0]} Hz)" if info else "responde")
    except Exception as e:
        return _item("Saída de áudio", ERRO, f"o pygame não conseguiu abrir a saída de áudio ({str(e)[:80]}) — "
                                             "veja se há caixa de som/fone ativo e se o Windows não bloqueou o áudio")


def _explicar_falha_fala(e) -> str:
    msg, nome, baixo = str(e), type(e).__name__, str(e).lower()
    if "403" in msg:
        return "o serviço de voz recusou (erro 403) — costuma ser edge-tts desatualizado: pip install -U edge-tts"
    if "ssl" in baixo or "certificate" in baixo:
        return "problema de certificado/SSL — confira a data/hora do Windows e se algum antivírus/proxy intercepta a conexão"
    if isinstance(e, (TimeoutError,)) or nome in ("TimeoutError", "CancelledError") or "timeout" in baixo or "timed out" in baixo:
        return "demorou demais — internet lenta ou o serviço está bloqueado"
    if "getaddrinfo" in baixo or "name resolution" in baixo or "cannot connect" in baixo or "connect" in baixo:
        return "sem acesso à internet para o serviço de voz"
    if nome == "NoAudioReceived" or "no audio" in baixo:
        return "o serviço respondeu mas sem áudio — costuma ser edge-tts antigo ou voz inexistente (pip install -U edge-tts)"
    return f"{nome}: {anonimizar(msg)[:90]}"


def _checar_fala(timeout: float = 12.0):
    """Gera de verdade uma fala de 2 palavras com o Edge-TTS (precisa de internet). É o teste que diz POR QUE a voz some."""
    if not _tem_modulo("edge_tts"):
        return None
    import asyncio
    import concurrent.futures

    async def gerar():
        import edge_tts
        com = edge_tts.Communicate("Teste de voz.", "pt-BR-FranciscaNeural")
        with tempfile.TemporaryDirectory() as d:
            alvo = os.path.join(d, "teste.mp3")
            await asyncio.wait_for(com.save(alvo), timeout)
            return os.path.getsize(alvo)

    try:
        # numa thread própria: quem chama pode estar dentro de um laço asyncio (asyncio.run não aceita isso)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            tam = ex.submit(asyncio.run, gerar()).result(timeout + 5)
    except Exception as e:
        return _item("Teste de fala", ERRO, _explicar_falha_fala(e))
    if tam <= 0:
        return _item("Teste de fala", ERRO, "o serviço respondeu com áudio vazio — pip install -U edge-tts")
    return _item("Teste de fala", OK, f"o Edge-TTS gerou áudio ({tam // 1024} KB)")


# ------------------------------------------------------------------ celular (v1.19)
# No celular o microfone, a voz, a câmera, a tela e o resto vêm do ANDROID (pela ponte), não de bibliotecas do PC.
# Por isso o diagnóstico de lá pergunta ao app o que o aparelho tem, em vez de acusar "pygame não instalado".
_SO_NO_PC = {"pygame", "sounddevice", "faster_whisper", "mss", "plyer", "serial", "cv2"}

# (capacidade da plataforma, nome na tela, o que significa faltar)
_CAPACIDADES_DO_CELULAR = [
    ("microfone", "Microfone", "o app não anunciou o microfone (falta a permissão?)"),
    ("audio_saida", "Saída de áudio", "o app não anunciou a saída de áudio"),
    ("voz_local", "Voz do aparelho", "sem a voz do Android; a voz da internet (Edge-TTS) ainda pode funcionar"),
    ("transcricao", "Entender a fala sem internet", "o modelo de fala em português ainda não foi baixado (tela Voz)"),
    ("camera", "Câmera", "o app não anunciou a câmera (falta a permissão?)"),
    ("tela", "Captura de tela", "o app não anunciou a captura de tela"),
    ("notificacao", "Notificações", "o app não anunciou notificações (falta a permissão?)"),
    ("ble", "Bluetooth do carrinho", "o aparelho não tem Bluetooth LE ou falta a permissão"),
    ("video", "Leitura de vídeo", "sem isso o vídeo não vira fundo nem miniatura de anexo"),
    ("llm_local", "IA local", "a IA que roda dentro do aparelho não está instalada (opcional)"),
]


def _plataforma_android():
    try:
        from brain import zenith_plataforma
        return zenith_plataforma.obter() if zenith_plataforma.detectar() == "android" else None
    except Exception:
        return None


def _checar_aparelho(plat):
    """Memória, bateria e temperatura do aparelho. Aviso quando é hora de ir mais devagar (mesmos limites do downgrade)."""
    m = plat.medir()
    partes, aviso = [], False
    if m.get("ram_total_gb") is not None:
        livre = m.get("ram_livre_gb")
        partes.append(f"{livre:.1f} GB livres de {m['ram_total_gb']:.1f} GB" if livre is not None else f"{m['ram_total_gb']:.1f} GB")
    else:
        partes.append("não consegui medir a memória")
        aviso = True
    try:
        from brain import zenith_downgrade as dg
        limite_bat, limite_temp = dg.BATERIA_ALERTA_PCT, dg.TEMPERATURA_ALERTA_C
    except Exception:
        limite_bat, limite_temp = 20, 42.0
    bat = m.get("bateria_pct")
    if bat is not None:
        partes.append(f"bateria {bat:.0f}%" + (" (carregando)" if m.get("carregando") else ""))
        aviso = aviso or (bat <= limite_bat and not m.get("carregando"))
    temp = m.get("temperatura_c")
    if temp is not None:
        partes.append(f"bateria a {temp:.1f} °C")
        aviso = aviso or temp >= limite_temp
    return _item("Aparelho", AVISO if aviso else OK, " · ".join(partes))


def _checar_capacidades_do_celular(plat):
    itens = []
    for cap, nome, falta in _CAPACIDADES_DO_CELULAR:
        itens.append(_item(nome, OK, "o app entrega") if plat.tem(cap) else _item(nome, AVISO, falta))
    return itens


def testar_tudo(settings, base_dir=None, rede: bool = True, porta: int = 8765, pastas=None) -> list:
    """Devolve [{"nome","status","detalhe"}]. `pastas`/`rede`/`porta` existem pra teste."""
    resultados = []
    celular = _plataforma_android()

    def isolado(fn, nome_se_falhar):
        try:
            r = fn()
            resultados.extend(r if isinstance(r, list) else [r])
        except Exception as e:
            resultados.append(_item(nome_se_falhar, AVISO, f"não consegui checar ({e})"))

    isolado(_checar_controle_inteligente, "Controle Inteligente de Aplicativos")
    isolado(lambda: _item("Versão", OK, f"{zenith_version.texto()} · Python {platform.python_version()}"
                                         f"{' (empacotado)' if getattr(sys, 'frozen', False) else ''}"), "Versão")
    isolado(lambda: [_checar_pasta(n, p) for n, p in (pastas if pastas is not None else _pastas_de_dados()).items()],
            "Pastas de dados")
    isolado(lambda: _checar_chaves(settings), "Chaves de IA")

    def libs():
        out = []
        for modulo, pip, uso, essencial in _BIBLIOTECAS:
            if celular is not None and modulo.split(".")[0] in _SO_NO_PC:
                continue                                  # no celular isso vem do Android, não de biblioteca
            if _tem_modulo(modulo):
                out.append(_item(f"Biblioteca {pip}", OK, f"{_versao_pip(pip)} — {uso}"))
            else:
                out.append(_item(f"Biblioteca {pip}", ERRO if essencial else AVISO,
                                 f"não instalada — {uso}" + ("" if essencial else " (opcional)")))
        return out
    isolado(libs, "Bibliotecas")

    if celular is not None:
        isolado(lambda: _checar_aparelho(celular), "Aparelho")
        isolado(lambda: _checar_capacidades_do_celular(celular), "Capacidades do aparelho")
    else:
        isolado(lambda: _checar_ffmpeg(base_dir), "ffmpeg")
        isolado(_checar_microfone, "Microfone")
        isolado(lambda: _item("Câmera", OK, "biblioteca presente (a câmera nunca é aberta num teste)")
                if _tem_modulo("cv2") else _item("Câmera", AVISO, "biblioteca 'opencv' não instalada"), "Câmera")

    def voz():
        if not settings.get("voice_enabled", True):
            return _item("Voz", AVISO, "desligada nas Configurações")
        motor = "ElevenLabs" if str(settings.get("elevenlabs_key", "") or "").strip() else "Edge-TTS"
        if motor == "Edge-TTS" and not _tem_modulo("edge_tts"):
            return _item("Voz", ERRO, "Edge-TTS não instalado (pip install edge-tts)")
        rvc = str(settings.get("rvc_model_path", "") or "").strip()
        extra = ""
        if rvc:
            extra = " · RVC: modelo existe" if Path(rvc).is_file() else " · RVC: modelo NÃO encontrado (cai pra voz base)"
        return _item("Voz", OK, f"motor {motor}{extra}")
    isolado(voz, "Voz")
    if settings.get("voice_enabled", True):
        if celular is None:
            isolado(_checar_saida_audio, "Saída de áudio")
        if rede and not str(settings.get("elevenlabs_key", "") or "").strip():
            def _fala():
                r = _checar_fala()
                return r if r is not None else []
            isolado(_fala, "Teste de fala")
    if celular is None:
        isolado(_checar_nativos, "Módulos nativos")
        isolado(_checar_admin, "Administrador")
    isolado(lambda: _checar_disco(pastas), "Espaço em disco")

    if rede:
        isolado(_checar_rede, "Internet")
    isolado(lambda: _checar_ponte(porta), "Ponte com o Corpo")

    def avatar():
        from brain import zenith_vrm_import as vi
        env = vi.localizar_ambiente(base_dir or Path.cwd(), settings.get)
        if env["faltando"]:
            return _item("Importação de avatar", AVISO, "falta: " + "; ".join(env["faltando"]))
        return _item("Importação de avatar", OK, f"Godot: {env['godot_bin']}")
    if base_dir is not None and celular is None:       # importar avatar pelo Godot é coisa do PC
        isolado(avatar, "Importação de avatar")

    def estado():
        from brain import zenith_modos, zenith_pausa
        modo = zenith_modos.normalizar(settings.get("modo_atual", "")) or zenith_modos.MODO_PADRAO
        return _item("Estado", AVISO if zenith_pausa.ativo() else OK,
                     f"modo de conversa: {modo}" + (" · SILÊNCIO TOTAL ativo (/retomar)" if zenith_pausa.ativo() else ""))
    isolado(estado, "Estado")
    return resultados


def formatar(resultados: list) -> str:
    n = {OK: 0, AVISO: 0, ERRO: 0}
    linhas = []
    for r in resultados:
        n[r["status"]] = n.get(r["status"], 0) + 1
        det = f" — {r['detalhe']}" if r.get("detalhe") else ""
        linhas.append(f"{_ICONE.get(r['status'], '?')} {r['nome']}{det}")
    cab = f"🩺 Diagnóstico: {n[OK]} ok · {n[AVISO]} aviso(s) · {n[ERRO]} erro(s)"
    return cab + "\n" + "\n".join(linhas)


# ------------------------------------------------------------------
# relatório (pra pedir ajuda) — sem chaves, sem conversas
# ------------------------------------------------------------------
_RE_USUARIO_WIN = re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s\"']+")
_RE_USUARIO_NIX = re.compile(r"(/(?:home|Users)/)[^/\s\"']+")


def anonimizar(texto: str) -> str:
    texto = _actionlog.mascarar_segredos(texto)
    texto = _RE_USUARIO_WIN.sub(r"\1<usuario>", texto)
    return _RE_USUARIO_NIX.sub(r"\1<usuario>", texto)


def _ultimas_linhas_do_log(base_dir, n=40) -> str:
    if base_dir is None:
        return "(sem pasta base)"
    p = Path(base_dir) / "zenith_log.txt"
    try:
        linhas = p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        return anonimizar("\n".join(linhas)) if linhas else "(log vazio)"
    except OSError:
        return "(zenith_log.txt não existe — só é criado rodando o .exe)"


def relatorio(settings, base_dir=None, rede: bool = False, agora=None, pastas=None, resultados=None) -> str:
    agora = agora or datetime.datetime.now()
    linhas = [
        "Zenith — relatório de diagnóstico",
        "(sem chaves de API, sem conversas, sem memórias, sem notas, sem nome de usuário)",
        f"Gerado em: {agora:%Y-%m-%d %H:%M}",
        "",
        f"Versão: {zenith_version.texto()}",
        f"Sistema: {platform.platform()}",
        f"Python: {platform.python_version()}{' (empacotado com PyInstaller)' if getattr(sys, 'frozen', False) else ''}",
        "",
        "Configuração (resumo):",
        f"- IA ativa: {settings.get('active_ai', '?')}",
        f"- Voz ligada: {bool(settings.get('voice_enabled', True))}",
        f"- Fala proativa: {bool(settings.get('proactive_enabled', True))}",
        f"- Modo de conversa: {settings.get('modo_atual', 'normal') or 'normal'}",
        f"- Ações em várias etapas: {bool(settings.get('multi_step_actions', True))}",
        "",
        "Checagens:",
        anonimizar(formatar(resultados if resultados is not None else testar_tudo(settings, base_dir=base_dir, rede=rede, pastas=pastas))),
        "",
        "Últimas linhas do zenith_log.txt:",
        _ultimas_linhas_do_log(base_dir),
    ]
    return "\n".join(linhas)
