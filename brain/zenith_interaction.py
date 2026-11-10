# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_interaction.py — Voz (portado de akira_interaction.py,
#  que existia em TODAS as versões antigas mas nunca tinha sido
#  trazido pro Zenith — por isso a Zenith parou de falar).
#
#  Diferenças em relação ao original:
#  - falar_async() não trava a thread que chama (o original bloqueava
#    até o áudio acabar; aqui roda em background e avisa via callback).
#  - on_start/on_end permitem sincronizar o estado "falando" do avatar
#    com a DURAÇÃO REAL do áudio, em vez do timer fixo de 1.5s que
#    o zenith_headless.py usava até agora.
# ============================================================

import asyncio
import itertools
import os
import queue
import re
import threading
import time

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import pygame
except ImportError:
    pygame = None

try:
    import requests
except ImportError:
    requests = None

try:
    from rvc_python.infer import RVCInference
except ImportError:
    RVCInference = None

from brain import zenith_rvc as rvc_externo        # v20: RVC num Python 3.10 à parte
from brain import zenith_plataforma                # v1.11: no celular, áudio/voz/microfone passam pela plataforma

# FEATURE (diagnosticar RVC "sem diferença perceptível" sem console):
# antes, todo aviso de RVC (lib faltando, engine falhou, etc.) só ia pra
# print() — invisível no .exe final (--noconsole). Sem NENHUM jeito de
# saber, de fora, se a conversão de voz rodou de verdade ou se caiu
# silenciosamente pro áudio base a cada fala. Agora cada evento também
# grava aqui, do mesmo jeito que zenith_corpo_debug.log faz do lado do
# Godot — dá pra abrir esse arquivo depois de uma conversa e ver, fala
# por fala, se o RVC de fato processou o áudio, ou por que não.
def _log_voz(msg: str):
    print("[Zenith/Voz] " + msg)
    try:
        from brain.zenith_settings import CONFIG_DIR
        import datetime
        log_path = CONFIG_DIR / "zenith_voz_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}  {msg}\n")
    except Exception:
        pass   # log é só conveniência — nunca deve travar a fala por causa disso

# --- Microfone (STT) ---------------------------------------------------
# sounddevice grava o áudio cru do microfone; faster-whisper transcreve
# localmente (sem mandar áudio pra nuvem nenhuma — mesmo espírito de
# privacidade do resto do projeto). As duas são opcionais: se não
# estiverem instaladas, comecar_a_escutar() avisa e devolve False, do
# mesmo jeito que o resto do arquivo já faz com edge_tts/pygame.
#
# CORREÇÃO (diagnóstico): antes isso só pegava ImportError — mas quando
# o binário nativo (PortAudio, no caso do sounddevice) não é encontrado
# em tempo de execução, o erro real costuma ser OSError/RuntimeError,
# não ImportError. Com "except ImportError" apertado demais, isso caía
# no "except" errado silenciosamente OU nem era pego, dependendo do
# caso — e a mensagem de erro real do porquê a lib não carregou se
# perdia. Agora pega qualquer Exception E guarda o motivo de verdade
# pra aparecer no zenith_log.txt.
_sd_import_error = None
_fw_import_error = None
try:
    import sounddevice as sd
    import numpy as np
except Exception as _e:
    sd = None
    np = None
    _sd_import_error = _e

if np is None and zenith_plataforma.detectar() == "android":
    # v1.11 — no celular não existe sounddevice, mas o numpy existe e é o que a escuta (blocos de áudio) precisa.
    # No PC nada muda: ali `np` continua sendo None quando o sounddevice não carrega, como sempre foi.
    try:
        import numpy as np
    except Exception:
        np = None

try:
    from faster_whisper import WhisperModel
except Exception as _e:
    WhisperModel = None
    _fw_import_error = _e

from brain.zenith_settings import MODELS_DIR, TEMP_DIR

_SAMPLE_RATE = 16000  # taxa que o Whisper espera


# FEATURE (modulação de voz por expressão): a MESMA emoção que já vai pro
# rosto do avatar (ver _guess_expression em zenith_headless.py) mexe um
# pouco no tom e na velocidade do Edge-TTS. Valores pequenos de propósito
# (nada de voz de desenho animado) — em (velocidade %, tom Hz). A
# intensidade (setting voice_expression_intensity, 0.0–2.0) só multiplica.
# Só vale pro Edge-TTS: ElevenLabs e RVC seguem como sempre.
_MODULACAO_EXPRESSAO = {
    "happy":     (8, 6),
    "surprised": (6, 10),
    "sad":       (-10, -8),
    "thinking":  (-6, -2),
    "angry":     (4, -2),
    "relaxed":   (-4, -2),
    "neutral":   (0, 0),
}


def parametros_de_voz(expressao: str, intensidade: float = 1.0):
    """Devolve (rate, pitch) no formato exato que o edge-tts exige
    ('+8%' e '+6Hz'). Expressão desconhecida = neutra. Puro (sem rede,
    sem áudio) — por isso é fácil de testar."""
    base_rate, base_pitch = _MODULACAO_EXPRESSAO.get(str(expressao or "neutral").lower(), (0, 0))
    try:
        k = max(0.0, min(2.0, float(intensidade)))
    except (TypeError, ValueError):
        k = 1.0
    rate = int(round(base_rate * k))
    pitch = int(round(base_pitch * k))
    return f"{rate:+d}%", f"{pitch:+d}Hz"


class ZenithInteraction:
    def __init__(self, settings):
        self.settings = settings
        self.voice = "pt-BR-FranciscaNeural"
        self.current_volume = settings.get("tts_volume", 0.8)
        self._ready = False
        # v29 — DIAGNOSTICABILIDADE: o motivo real de o áudio não iniciar
        # era só um print() — e o .exe é --noconsole, então sumia. O
        # Anderson viu "Áudio (pygame): NÃO iniciou — sem áudio" no
        # diagnóstico e NÃO TINHA COMO saber por quê. Agora o erro fica
        # guardado e aparece no diagnóstico do próprio Zenith.
        self._mixer_erro = ""
        # v29 — o mesmo vale pro microfone: guarda o motivo (e o volume
        # medido) da última vez que ela tentou ouvir, pra mensagem que o
        # usuário recebe dizer o QUE fazer em vez de "não entendi nada".
        self.ultimo_motivo_mic = ""
        self.ultimo_nivel_mic = 0.0
        self.ultimo_dispositivo_mic = ""

        if self._no_celular():       # v1.11 — celular: o áudio de saída é o do Android (pela ponte)
            self._ready = self._plataforma().tem("audio_saida")
            if not self._ready:
                self._mixer_erro = "o app Android ainda não ofereceu saída de áudio"
                _log_voz(self._mixer_erro)
        elif pygame:
            try:
                pygame.mixer.init()
                pygame.mixer.music.set_volume(self.current_volume)
                self._ready = True
            except Exception as e:
                self._mixer_erro = f"{type(e).__name__}: {e}"
                _log_voz(f"Não consegui iniciar o mixer de áudio: {self._mixer_erro}")
        else:
            self._mixer_erro = "'pygame' não instalado"
            _log_voz("'pygame' não instalado — voz desativada. Rode: pip install pygame")

        if edge_tts is None:
            print("[Zenith/Voz] 'edge-tts' não instalado — voz desativada. "
                  "Rode: pip install edge-tts")

        # --- Estado do microfone ---
        self._whisper_lock_carga = threading.Lock()   # v27: um carregamento só (pré-carga × 1º uso)
        self._whisper_lock_uso = threading.Lock()     # v27: uma transcrição por vez (parcial × final)
        self._whisper_model = None     # carregado sob demanda (lazy) —
                                        # é pesado, não precisa se o
                                        # usuário nunca usar o mic.
        self._is_listening = False
        self._stop_listening_flag = threading.Event()
        self._listen_thread = None

        # FEATURE (RVC de verdade): motor carregado sob demanda — é
        # PESADO (carrega Hubert/RMVPE + o modelo .pth em memória), então
        # só carrega na primeira fala depois de configurado, e só
        # recarrega se o caminho do modelo mudar nas Configurações.
        self._rvc_engine = None
        self._rvc_model_loaded = None
        self._rvc_ext = None                 # v20: RVCExterno (processo auxiliar), criado sob demanda
        self._rvc_ext_python = None
        self.ultimo_status_rvc = "ainda não falou nada nesta sessão"
        self.ultimo_motor_voz = "ainda não falou nada nesta sessão"

        if not self._no_celular() and (sd is None or np is None):
            print(f"[Zenith/Voz] 'sounddevice'/numpy não disponíveis — microfone "
                  f"desativado. Motivo real: {_sd_import_error!r}. Se já instalou e "
                  f"continua assim, pode ser o binário nativo do PortAudio faltando "
                  f"no .exe compilado — confira o build_exe.py.")
        if not self._no_celular() and WhisperModel is None:
            print(f"[Zenith/Voz] 'faster-whisper' não disponível — microfone "
                  f"desativado. Motivo real: {_fw_import_error!r}.")

    # ---- v1.11 (port celular): áudio de saída e voz passam pela plataforma quando o Zenith roda no celular ----------
    # No PC cada um destes métodos faz EXATAMENTE o que o código fazia antes (pygame); só o celular desvia.
    def _no_celular(self) -> bool:
        return zenith_plataforma.detectar() == "android"

    def _plataforma(self):
        return zenith_plataforma.obter()

    def _tem_voz_do_celular(self) -> bool:
        try:
            return self._no_celular() and self._plataforma().tem("voz_local")
        except Exception:
            return False

    def motivo_de_nao_escutar(self) -> str:
        """v1.14 (port celular) — POR QUE não dá para escutar neste aparelho, numa frase para o chat.

        Devolve "" quando não é o celular (no PC vale a mensagem de sempre, sobre sounddevice/faster-whisper) ou quando
        nada impede. Sem isto o celular receberia o aviso do PC, que manda "instalar sounddevice" — sem sentido num Android."""
        if not self._no_celular():
            return ""
        if np is None:
            return "Falta a biblioteca numpy neste aparelho, então não consigo ouvir."
        plat = self._plataforma()
        if not plat.tem("microfone"):
            return ("O app não tem acesso ao microfone. Permita o microfone nas permissões do Android "
                    "(Configurações do aparelho > Apps > Zenith > Permissões) e toque no microfone de novo.")
        if not plat.tem("transcricao"):
            return ("Ainda não tenho o modelo de fala em português neste aparelho, então não consigo entender o que "
                    "você diz. Baixe em Configurações > Voz > Entender a fala (sem internet) > Baixar modelo.")
        return ""

    def _velocidade_da_expressao(self, expressao: str) -> float:
        """'+8%' (formato do edge-tts) vira 1.08. Sem modulação ligada, ou formato estranho: 1.0."""
        if not self.settings.get("voice_expression_modulation", True) or expressao == "neutral":
            return 1.0
        try:
            rate, _pitch = parametros_de_voz(expressao, self.settings.get("voice_expression_intensity", 1.0))
            return max(0.5, min(2.0, 1.0 + int(rate.rstrip("%")) / 100.0))
        except Exception:
            return 1.0

    def _tocar_arquivo(self, caminho: str) -> None:
        _audio_tocar(self, caminho)

    def _audio_ocupado(self) -> bool:
        return _audio_ocupado()

    def _parar_audio(self) -> None:
        if self._no_celular():
            try:
                self._plataforma().parar_audio()
            except Exception:
                pass
            return
        if pygame and self._ready:
            pygame.mixer.music.stop()

    def _descarregar_audio(self) -> None:
        _audio_descarregar()

    def set_volume(self, volume: float):
        self.current_volume = volume
        if pygame and self._ready:
            pygame.mixer.music.set_volume(volume)

    def _limpar_para_voz(self, texto: str) -> str:
        texto = re.sub(r'\*\*(.*?)\*\*', r'\1', texto)
        texto = re.sub(r'\*(.*?)\*', r'\1', texto)
        texto = re.sub(r'[^\w\s.,!?;:áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇ\n-]', '', texto)
        return texto.strip()

    async def _gerar_audio_base(self, texto: str, temp_path: str = "_zenith_voice_temp.mp3",
                                expressao: str = "neutral") -> str:
        if self._no_celular() and self._ready and temp_path == "_zenith_voice_temp.mp3":
            self._parar_audio()          # v1.11 — celular: corta o que estiver tocando (mesma ideia do bloco abaixo)
            await asyncio.sleep(0.05)
        elif pygame and self._ready and temp_path == "_zenith_voice_temp.mp3":
            # Só para/descarrega o player quando é a "primeira fala" de uma
            # resposta nova (nome de arquivo padrão) — nos pedaços
            # seguintes (fala em partes, ver _falar_sync) isso pararia a
            # própria fala que acabou de começar a tocar.
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            await asyncio.sleep(0.05)

        eleven_key = self.settings.get("elevenlabs_key")
        eleven_voice = self.settings.get("elevenlabs_voice_id")
        if eleven_key and eleven_voice and requests:
            try:
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_voice}"
                headers = {"xi-api-key": eleven_key, "Content-Type": "application/json"}
                data = {"text": texto, "model_id": "eleven_multilingual_v2",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}
                response = requests.post(url, json=data, headers=headers, timeout=20)
                if response.status_code == 200:
                    with open(temp_path, "wb") as f:
                        f.write(response.content)
                    self.ultimo_motor_voz = "ElevenLabs"
                    return temp_path
                print(f"[Zenith/Voz] ElevenLabs respondeu {response.status_code}, caindo pro Edge-TTS.")
            except Exception as e:
                print(f"[Zenith/Voz] Erro na ElevenLabs, caindo pro Edge-TTS: {e}")

        if self._tem_voz_do_celular():          # v1.11 — celular: a voz do próprio Android (funciona sem internet)
            try:
                if self._plataforma().sintetizar(texto, temp_path, voz="pt-BR",
                                                 velocidade=self._velocidade_da_expressao(expressao), tom=1.0):
                    self.ultimo_motor_voz = "Voz do Android (sem internet)"
                    return temp_path
                print("[Zenith/Voz] A voz do Android não gerou o áudio; tentando o Edge-TTS.")
            except Exception as e:
                print(f"[Zenith/Voz] Erro na voz do Android, tentando o Edge-TTS: {e}")

        if edge_tts is None:
            raise RuntimeError("Nenhum motor de voz disponível (nem ElevenLabs, nem edge-tts).")

        # v14 — variação de tom/velocidade conforme a emoção (só Edge-TTS).
        # Se algo no formato der errado, cai pra voz normal na hora — a
        # fala nunca deixa de sair por causa desse enfeite.
        communicate = None
        if self.settings.get("voice_expression_modulation", True) and expressao != "neutral":
            try:
                rate, pitch = parametros_de_voz(expressao, self.settings.get("voice_expression_intensity", 1.0))
                communicate = edge_tts.Communicate(texto, self.voice, rate=rate, pitch=pitch)
            except Exception as e:
                _log_voz(f"modulação por emoção ignorada ({expressao}): {e}")
                communicate = None
        if communicate is None:
            communicate = edge_tts.Communicate(texto, self.voice)
        await communicate.save(temp_path)
        self.ultimo_motor_voz = f"Edge-TTS ({self.voice})"
        return temp_path

    def sintetizar_para_arquivo(self, texto: str, caminho: str) -> bool:
        """v28 — gera a voz num ARQUIVO (pra narrar vídeo). Não toca nada e não mexe no player de fala.
        Devolve True se o arquivo ficou pronto; qualquer falha (sem internet, sem motor) devolve False e o vídeo sai mudo."""
        try:
            limpo = self._limpar_para_voz(texto or "")
            if not limpo:
                return False
            asyncio.run(self._gerar_audio_base(limpo, temp_path=str(caminho)))
            return os.path.exists(caminho) and os.path.getsize(caminho) > 0
        except Exception as e:
            print(f"[Zenith/Voz] não consegui gerar a voz do vídeo: {e}")
            return False

    def _aplicar_rvc(self, input_path: str) -> str:
        if self._no_celular():       # v1.11 — o RVC não existe no celular: fica a voz base
            return input_path
        # FEATURE (RVC de verdade): antes isso só detectava o modelo e
        # devolvia o áudio sem mexer — nunca convertia de fato. Agora usa
        # a lib `rvc-python` (pip install rvc-python) pra rodar a
        # inferência real. É pesada de propósito (carrega um encoder de
        # conteúdo de voz (Hubert) + extrator de tom (RMVPE) + o seu
        # modelo .pth em memória) — a primeira fala depois de configurar
        # ou trocar de modelo demora bem mais que o normal; as próximas
        # reusam o motor já carregado.
        rvc_model = self.settings.get("rvc_model_path")
        if not rvc_model or not os.path.exists(rvc_model):
            _log_voz("RVC: nenhum modelo configurado (ou caminho não existe) — falando com a voz base, sem tentar conversão.")
            self.ultimo_status_rvc = "desligado (nenhum modelo .pth configurado ou o caminho não existe)"
            return input_path  # sem modelo configurado — segue com a voz base, normal

        if RVCInference is None:
            # v20: não instala no Python do Zenith (o fairseq do RVC só acompanha o Python 3.10) —
            # então tenta o Python 3.10 à parte (processo auxiliar), se existir.
            return self._aplicar_rvc_externo(input_path, rvc_model)

        try:
            if self._rvc_engine is None:
                self._rvc_engine = RVCInference(device="cpu:0")
            if self._rvc_model_loaded != rvc_model:
                index_path = self.settings.get("rvc_index_path", "") or ""
                self._rvc_engine.load_model(rvc_model, index_path=index_path)
                self._rvc_model_loaded = rvc_model
                _log_voz(f"RVC: modelo carregado ({rvc_model} | index={index_path or '(nenhum)'})")

            saida = input_path.rsplit(".", 1)[0] + "_rvc.wav"
            self._rvc_engine.infer_file(input_path, saida)
            ok = os.path.exists(saida) and os.path.getsize(saida) > 0
            _log_voz(f"RVC: infer_file() concluído — arquivo de saída {'existe' if ok else 'NÃO existe/vazio'} "
                      f"({saida}). Se o áudio soar igual ao original, o mais provável é que o modelo/.pth "
                      f"carregado tenha um timbre muito parecido com a voz base do Edge-TTS, não que o RVC "
                      f"não tenha rodado — este log confirma que a inferência foi chamada com sucesso.")
            self.ultimo_status_rvc = ("RODOU — conversão concluída (se soar igual, o timbre do .pth é parecido com a voz base)"
                                      if ok else "rodou, mas NÃO gerou arquivo de saída (usando a voz base)")
            return saida if ok else input_path
        except Exception as e:
            _log_voz(f"RVC: modelo configurado, mas a conversão FALHOU nesta fala (caindo pra voz base, "
                      f"sem travar a conversa). Detalhe do erro: {e}")
            self.ultimo_status_rvc = f"FALHOU nesta fala (usando a voz base): {e}"
            return input_path

    def _python_rvc(self):
        """Caminho do Python 3.10 do RVC (configurado ou o venv padrão em tools/rvc/venv) ou None."""
        try:
            from brain.zenith_settings import BASE_DIR
            base = BASE_DIR
        except Exception:
            base = os.getcwd()
        return rvc_externo.achar_python_rvc(base, str(self.settings.get("rvc_python_exe", "") or ""))

    def _aplicar_rvc_externo(self, input_path: str, rvc_model: str) -> str:
        py = self._python_rvc()
        if not py:
            _log_voz("RVC: modelo configurado (" + rvc_model + "), mas não há 'rvc-python' neste Python nem um "
                     "Python 3.10 do RVC configurado — usando a voz base. Veja instalar_rvc.bat / Configurações > Voz.")
            self.ultimo_status_rvc = ("modelo configurado, mas falta o Python 3.10 do RVC (rode instalar_rvc.bat "
                                      "ou aponte o python.exe em Configurações > Voz) — usando a voz base")
            return input_path
        try:
            if self._rvc_ext is None or self._rvc_ext_python != py:
                if self._rvc_ext is not None:
                    self._rvc_ext.parar()
                from brain.zenith_settings import TEMP_DIR
                self._rvc_ext = rvc_externo.RVCExterno(py, os.path.join(str(TEMP_DIR), "rvc"), log=_log_voz)
                self._rvc_ext_python = py
            # O RVC lê o áudio com o ffmpeg; entregando WAV ele não precisa dele.
            entrada = input_path
            if input_path.lower().endswith(".mp3"):
                wav = input_path.rsplit(".", 1)[0] + "_in.wav"
                if rvc_externo.mp3_para_wav(input_path, wav):
                    entrada = wav
            saida = input_path.rsplit(".", 1)[0] + "_rvc.wav"
            index_path = self.settings.get("rvc_index_path", "") or ""
            if index_path and not os.path.exists(index_path):
                index_path = ""
            ok, msg = self._rvc_ext.converter(entrada, saida, rvc_model, index_path)
            if ok and os.path.exists(saida) and os.path.getsize(saida) > 0:
                self.ultimo_status_rvc = "RODOU (Python 3.10 à parte) — conversão concluída"
                _log_voz(f"RVC externo: ok ({saida})")
                return saida
            self.ultimo_status_rvc = f"Python do RVC respondeu com erro (usando a voz base): {msg}"
            _log_voz(f"RVC externo falhou: {msg}")
            return input_path
        except Exception as e:
            self.ultimo_status_rvc = f"FALHOU nesta fala (usando a voz base): {e}"
            _log_voz(f"RVC externo: erro inesperado: {e}")
            return input_path

    def pode_falar(self) -> bool:
        """v24 — a voz está pronta (modelos carregados e Edge-TTS disponível)?"""
        if self._no_celular() and not self._ready:      # v1.11 — o Corpo (Android) pode ter conectado depois do boot
            self._ready = self._plataforma().tem("audio_saida")
            if self._ready:
                self._mixer_erro = ""
        return bool(self._ready and (edge_tts is not None or self._tem_voz_do_celular()))

    def falar_async(self, texto: str, on_start=None, on_end=None, expressao: str = "neutral"):
        """Não bloqueia quem chama. on_start()/on_end() são chamados em
        background — quem estiver ouvindo pode sincronizar o avatar
        (boca/estado) com a duração REAL do áudio, não um timer chutado."""
        if not self.pode_falar():                 # (v1.11: o mesmo teste de antes, agora também conta a voz do celular)
            if on_end:
                on_end()
            return
        fala = self.falar_stream_iniciar(on_start=on_start, on_end=on_end, expressao=expressao)
        fala.add(texto)
        fala.fim()

    def falar_stream_iniciar(self, on_start=None, on_end=None, expressao: str = "neutral"):
        """v24 — fala EM PEDAÇOS enquanto o texto ainda está sendo escrito: devolve um objeto com .add(texto),
        .fim() e .cancelar(). A primeira frase começa a tocar assim que o áudio dela fica pronto; as seguintes
        são geradas em paralelo e tocadas na ordem. Uma fala nova corta a anterior (sem avisar o fim dela)."""
        anterior = getattr(self, "_fala_atual", None)
        if anterior is not None:
            anterior.cancelar(silencioso=True)
        self.parar_de_falar(_so_audio=True)
        fala = FalaStream(self, on_start=on_start, on_end=on_end, expressao=expressao)
        self._fala_atual = fala
        return fala

    def diagnostico_voz(self) -> str:
        """Resumo em português do estado da voz, pro botão/comando
        'testar voz' — responde 'o RVC rodou de verdade?' sem abrir log."""
        linhas = []
        if self._no_celular():
            linhas.append("• Áudio (Android): " + ("OK" if self._ready else "NÃO disponível — sem áudio"))
            linhas.append("• Voz do Android (sem internet): " + ("disponível" if self._tem_voz_do_celular() else "NÃO disponível"))
        elif self._ready:
            linhas.append("• Áudio (pygame): OK")
        else:
            erro = getattr(self, "_mixer_erro", "")       # getattr: há lugares (testes) que criam o objeto sem __init__
            linhas.append("• Áudio (pygame): NÃO iniciou — sem áudio"
                          + (f" ({erro})" if erro else ""))
        linhas.append("• Edge-TTS: " + ("instalado" if edge_tts is not None else "NÃO instalado"))
        eleven = bool(self.settings.get("elevenlabs_key") and self.settings.get("elevenlabs_voice_id"))
        linhas.append("• ElevenLabs: " + ("configurada (tenta primeiro)" if eleven else "não configurada"))
        linhas.append("• Motor da última fala: " + self.ultimo_motor_voz)
        rvc_model = self.settings.get("rvc_model_path")
        if RVCInference is not None:
            linhas.append("• Biblioteca rvc-python: instalada neste Python")
        else:
            py = self._python_rvc()
            linhas.append("• Biblioteca rvc-python: NÃO instalada neste Python (normal — ela exige Python 3.10)")
            linhas.append("• Python 3.10 do RVC: " + (f"encontrado ({py})" if py else
                          "NÃO encontrado — rode instalar_rvc.bat ou aponte o python.exe em Configurações > Voz"))
        linhas.append("• RVC (última fala): " + self.ultimo_status_rvc)
        if rvc_model:
            linhas.append("• Modelo .pth: " + str(rvc_model))
        mod = self.settings.get("voice_expression_modulation", True)
        linhas.append("• Variação por emoção (Edge-TTS): " + ("ligada" if mod else "desligada"))
        linhas.append("")
        linhas += self.diagnostico_microfone()
        return "\n".join(linhas)

    def diagnostico_microfone(self) -> list:
        """v29 — o pedaço do diagnóstico que responde "o microfone funciona?": qual aparelho está
        sendo usado, quais existem neste PC, e quanta voz entrou na última vez (o número que o
        usuário via como "não entendi nada" sem explicação nenhuma).
        """
        if self._no_celular():       # v1.11 — celular: quem diz o que existe é o app Android
            plat = self._plataforma()
            return ["• Microfone (Android): " + ("disponível" if plat.tem("microfone") else "NÃO disponível (sem permissão ou sem microfone)"),
                    "• Transcrição no aparelho: " + ("disponível" if plat.tem("transcricao") else "NÃO disponível")]
        if sd is None or np is None:
            return ["• Microfone: INDISPONÍVEL — sounddevice não carregou"
                    + (f" ({_sd_import_error!r})" if _sd_import_error else "")]

        linhas = []
        try:
            escolhido = ""
            try:
                escolhido = str(self.settings.get("mic_device", "") or "")
            except Exception:
                pass
            nome_mic = self._nome_dispositivo_mic()
            if escolhido:
                sufixo = f" (escolhido em Configurações: {escolhido!r})"
            else:
                # _nome_dispositivo_mic() já devolve "padrão do Windows" — não repetir na mesma linha
                sufixo = "" if nome_mic == "padrão do Windows" else " (padrão do Windows)"
            linhas.append("• Microfone em uso: " + nome_mic + sufixo)
            entradas = [f"[{i}] {d['name']}" for i, d in enumerate(sd.query_devices())
                        if int(d.get("max_input_channels", 0)) > 0]
            linhas.append("• Microfones deste PC: " + ("; ".join(entradas[:6]) if entradas else "nenhum"))
            nivel = float(getattr(self, "ultimo_nivel_mic", 0.0) or 0.0)
            explicacao = {"silencio": "quase silêncio (microfone mudo, tampado ou o dispositivo errado)",
                          "nada_chegou": "o dispositivo abriu e não mandou som nenhum",
                          "curto": "menos de meio segundo gravado",
                          "erro_mic": "erro ao abrir o microfone",
                          "nao_transcreveu": "ouvi som, mas não virou texto"}
            motivo = explicacao.get(getattr(self, "ultimo_motivo_mic", "") or "",
                                    "nada foi ouvido nesta sessão ainda")
            linhas.append(f"• Última escuta: pico de volume {nivel:.1%} — {motivo}")
            if nivel and nivel < float(self.settings.get("mic_nivel_minimo", 0.06) or 0.0):
                linhas.append("  (baixo demais: troque o microfone em settings.json > 'mic_device')")
        except Exception as e:
            linhas.append(f"• Microfone: erro ao consultar ({e})")
        return linhas

    @staticmethod
    def _dividir_em_frases(texto: str) -> list:
        """Quebra o texto em frases pra fala em pedaços (ver _falar_sync
        acima). Frases muito curtas (ex: 'Ok.') são coladas na próxima
        pra não gerar áudios minúsculos demais que soariam picotados."""
        brutas = re.split(r'(?<=[.!?;])\s+', texto.strip())
        brutas = [f for f in brutas if f.strip()]
        if not brutas:
            return [texto]
        frases = []
        atual = ""
        for f in brutas:
            atual = f"{atual} {f}".strip() if atual else f
            if len(atual) >= 24:
                frases.append(atual)
                atual = ""
        if atual:
            if frases:
                frases[-1] = f"{frases[-1]} {atual}".strip()
            else:
                frases.append(atual)
        frases = frases or [texto]
        # v24: o 1º áudio demora mais quanto mais longo for o texto dele — se a 1ª frase é longa, corta na 1ª vírgula
        # (ou travessão/dois-pontos) depois de ~25 caracteres, pra a Zenith começar a falar mais cedo.
        primeira = frases[0]
        if len(primeira) > 90:
            m = re.search(r"[,:;—–]\s", primeira[25:80])
            if m:
                corte = 25 + m.end()
                frases[0:1] = [primeira[:corte].strip(), primeira[corte:].strip()]
        return frases

    # ---------------- Microfone (antes era um stub que não fazia nada) ----------------

    def _get_whisper_model(self):
        """Carrega o modelo Whisper só na primeira vez que alguém usa o
        microfone (lazy) — carregar de cara no __init__ deixaria o
        Cérebro mais lento pra abrir toda vez, mesmo pra quem nunca vai
        usar voz de entrada."""
        with self._whisper_lock_carga:                        # v27: pré-carga e 1º uso não carregam o modelo duas vezes
            return self._carregar_whisper()

    def _carregar_whisper(self):
        if self._whisper_model is None:
            print("[Zenith/Voz] Carregando modelo de transcrição (primeira vez pode "
                  "demorar alguns segundos)...")
            # AJUSTE (transcrição errando palavras, tipo trocar o nome
            # da IA por outra coisa e confundir a frase toda): "base"
            # era rápido mas erra mais em nomes próprios/PT-BR. "small"
            # é sensivelmente mais preciso, ainda roda numa CPU comum
            # (só um pouco mais lento). Quem preferir a velocidade de
            # antes pode editar aqui pra "base" de novo.
            self._whisper_model = WhisperModel(
                str(self.settings.get("whisper_modelo", "small") or "small"), device="cpu", compute_type="int8",
                download_root=str(MODELS_DIR / "whisper"))
        return self._whisper_model

    # ---- v27: transcrição RÁPIDA e AO VIVO -----------------------------------------------------------------------------
    # O Anderson: "o processo de transcrever é lento... tem que ser igual a Shogers: vai escrevendo enquanto a pessoa fala
    # e depois arruma, igual o Word". O tempo ia todo em 3 coisas, e as 3 mudaram:
    #   1) carregar o modelo do Whisper NA 1ª VEZ que o microfone é usado -> agora carrega em segundo plano ao abrir o Zenith
    #      (precarregar_whisper) e, se ainda não terminou, carrega ENQUANTO você fala (a transcrição parcial já pede o modelo);
    #   2) a busca "beam_size=5" do Whisper (5 hipóteses por trecho) -> agora 1 (greedy, 2–4x mais rápido; configurável em
    #      `whisper_beam`);
    #   3) só começar a transcrever DEPOIS de você parar -> agora transcreve a cada ~1 s o que já foi dito e mostra na caixa
    #      (mic_transcript parcial); quando você para, só falta o último pedacinho, e o texto final substitui o provisório.
    def precarregar_whisper(self):
        """Carrega o Whisper em segundo plano (não trava nada). Desliga com `whisper_precarregar: false`."""
        if self._no_celular():       # v1.11 — no celular não há modelo para pré-carregar (a transcrição é do Android)
            return False
        if WhisperModel is None or sd is None or np is None:
            return False
        if not self.settings.get("whisper_precarregar", True) or self._whisper_model is not None:
            return False

        def _carregar():
            try:
                self._get_whisper_model()
                print("[Zenith/Voz] Modelo de transcrição pronto (pré-carregado).")
            except Exception as e:
                print(f"[Zenith/Voz] Não consegui pré-carregar o modelo de transcrição: {e}")
        threading.Thread(target=_carregar, daemon=True, name="zenith-whisper-precarga").start()
        return True

    def _transcrever_audio(self, audio, beam: int = None, vad: bool = True) -> str:
        """Transcreve um trecho de áudio (float32, 16 kHz). Uma transcrição por vez (o modelo é compartilhado).

        v29 — `vad=False` só é usado no plano B (ver `_escutar_sync`): o filtro VAD do Whisper é ótimo pra
        tirar silêncio, mas quando ele decide que TUDO é silêncio o resultado é string vazia — e o usuário
        recebia "não entendi nada" com o áudio dele perfeitamente audível. Desligar o VAD numa fala real
        recupera o texto; em ruído puro ele inventa frase, por isso o plano B só roda quando o áudio tem
        energia de fala de verdade (medida antes).
        """
        if self._no_celular():       # v1.11 — celular: a transcrição é feita pelo Android (pela ponte)
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            with self._whisper_lock_uso:
                return str(self._plataforma().transcrever(pcm, _SAMPLE_RATE, "pt") or "").strip()
        model = self._get_whisper_model()
        beam = int(beam or self.settings.get("whisper_beam", 1) or 1)
        nome_ia = self.settings.get("persona_name", "Zenith")
        with self._whisper_lock_uso:
            segments, _info = model.transcribe(
                audio, language="pt", vad_filter=bool(vad), beam_size=beam,
                condition_on_previous_text=False,
                initial_prompt=f"Conversa em português com a assistente {nome_ia}.")
            texto = " ".join(seg.text.strip() for seg in segments).strip()
        if not texto and vad and self.settings.get("mic_sem_vad_fallback", True):
            # O plano B só vale quando houve ENERGIA DE FALA no áudio. Em ruído puro o Whisper sem
            # filtro inventa frase (medido: 6 s de chiado viraram "Deixe-me ver o que é isso.") —
            # inventar fala seria pior que não entender nada.
            minimo = float(self.settings.get("mic_nivel_minimo", 0.06) or 0.0)
            nivel = float(np.max(np.abs(audio))) if len(audio) else 0.0
            if nivel >= minimo:
                _log_voz(f"O filtro de silêncio do Whisper descartou tudo (pico {nivel:.4f}) — "
                         f"tentando de novo sem ele (plano B).")
                return self._transcrever_audio(audio, beam=beam, vad=False)
        return texto

    def _dispositivo_mic(self):
        """v29 — qual microfone usar. Vazio (padrão) = o que o Windows escolheu; pode ser o nome
        ('Microfone (Brio 105)') ou o número da lista. Existe porque o padrão do Windows nem sempre é o
        microfone em que a pessoa fala — era uma das causas de 'não entendi nada' sem explicação."""
        if self._no_celular():       # v1.11 — o microfone do celular é o do aparelho
            return None
        escolhido = str(self.settings.get("mic_device", "") or "").strip()
        if not escolhido:
            return None
        if escolhido.isdigit():
            return int(escolhido)
        try:
            for i, d in enumerate(sd.query_devices()):
                if escolhido.lower() in str(d["name"]).lower() and int(d["max_input_channels"]) > 0:
                    return i
        except Exception as e:
            _log_voz(f"Não consegui resolver o microfone configurado ({escolhido!r}): {e}")
        _log_voz(f"Microfone configurado ({escolhido!r}) não existe neste PC — usando o padrão do Windows.")
        return None

    def _nome_dispositivo_mic(self) -> str:
        if self._no_celular():
            return "microfone do aparelho"
        try:
            dev = self._dispositivo_mic()
            if dev is None:
                return "padrão do Windows"
            return str(sd.query_devices(dev)["name"])
        except Exception:
            return "?"

    def explicacao_falha_mic(self) -> str:
        """v29 — em vez de só "não consegui entender nada", diz o motivo provável COM o número medido.
        É a diferença entre o usuário achar que o Zenith está quebrado e ele saber o que ajustar."""
        nivel = self.ultimo_nivel_mic
        aparelho = self.ultimo_dispositivo_mic or self._nome_dispositivo_mic()
        motivo = self.ultimo_motivo_mic
        if motivo == "silencio":
            return (f"O áudio chegou praticamente mudo (volume máximo {nivel:.1%}) pelo '{aparelho}'. "
                    "Confira se esse é o microfone em que você fala, se ele não está mudo/tampado e se o "
                    "volume dele está alto no Windows (Configurações de som > Entrada).")
        if motivo == "nada_chegou":
            return (f"O microfone '{aparelho}' abriu, mas não mandou nenhum som. "
                    "Costuma ser microfone desligado/desconectado, ou o dispositivo errado selecionado.")
        if motivo == "curto":
            return "A gravação durou menos de meio segundo. Aperte o microfone, fale e aperte de novo pra parar."
        if motivo == "erro_mic":
            return f"Não consegui abrir o microfone '{aparelho}' (veja zenith_log.txt)."
        if motivo == "nao_transcreveu":
            return (f"Ouvi som (pico {nivel:.1%}) mas não consegui virar texto — fale mais perto do microfone "
                    "e mais devagar, sem música/ventilador perto.")
        return ""

    def comecar_a_escutar(self, callback_quando_ouvir, on_fase=None, on_parcial=None) -> bool:
        """Começa a gravar o microfone. Quando o usuário chamar
        parar_de_escutar() (ou o silêncio for detectado), transcreve o
        áudio e chama callback_quando_ouvir(texto) — texto == "" se não
        entendeu nada. Roda tudo numa thread separada: nunca trava quem
        chamou, nem a Ponte, nem a UI do Godot."""
        if self._no_celular():       # v1.11 — celular: precisa de microfone E transcrição oferecidos pelo app Android
            plat = self._plataforma()
            if np is None or not (plat.tem("microfone") and plat.tem("transcricao")):
                print("[Zenith/Voz] Não dá pra escutar: o app Android não ofereceu microfone/transcrição (ou falta o numpy).")
                return False
        else:
            if sd is None or np is None:
                print("[Zenith/Voz] Não dá pra escutar: 'sounddevice' não está instalado.")
                return False
            if WhisperModel is None:
                print("[Zenith/Voz] Não dá pra escutar: 'faster-whisper' não está instalado.")
                return False
        if self._is_listening:
            print("[Zenith/Voz] Já estou escutando — ignorando novo pedido.")
            return False

        self._is_listening = True
        self._stop_listening_flag.clear()
        self._listen_thread = threading.Thread(
            target=self._escutar_sync, args=(callback_quando_ouvir, on_fase, on_parcial), daemon=True
        )
        self._listen_thread.start()
        return True

    def parar_de_falar(self, _so_audio: bool = False):
        """v18 (/pausar): corta o áudio que está tocando agora. Nunca levanta exceção.
        v24: também cancela a fala em pedaços que ainda estava sendo gerada."""
        try:
            if not _so_audio:
                fala = getattr(self, "_fala_atual", None)
                if fala is not None:
                    fala.cancelar()
            self._parar_audio()
        except Exception:
            pass

    def parar_de_escutar(self):
        """Sinaliza pra thread de gravação parar AGORA e transcrever o
        que já foi capturado até aqui — é o que o botão de microfone do
        chat chama ao ser apertado de novo pra encerrar a gravação."""
        self._stop_listening_flag.set()

    def _abrir_microfone(self, kwargs_mic: dict):
        """v1.11 — no PC é o `sd.InputStream` de sempre; no celular, o microfone do Android com a MESMA forma."""
        if self._no_celular():
            return _MicAndroid(self._plataforma(), kwargs_mic["callback"], kwargs_mic["samplerate"], kwargs_mic["blocksize"])
        return sd.InputStream(**kwargs_mic)

    def _escutar_sync(self, callback_quando_ouvir, on_fase=None, on_parcial=None):
        # v26 — FASES DO MICROFONE ("ouvindo" → "captando" → "transcrevendo"): o Corpo mostra cada uma com texto, ícone
        # e cor diferentes. Antes era sempre o mesmo ícone e dava pra ficar sem saber se ela te ouviu ou se travou
        # (a 1ª transcrição ainda carrega o modelo do Whisper, que demora alguns segundos).
        def _fase(nome):
            if on_fase:
                try:
                    on_fase(nome)
                except Exception:
                    pass
        frames = []
        self.ultimo_motivo_mic = ""
        self.ultimo_nivel_mic = 0.0
        self.ultimo_dispositivo_mic = self._nome_dispositivo_mic()
        MAX_SEGUNDOS = self.settings.get("mic_max_seconds", 60)  # trava de segurança:
                            # nunca escuta pra sempre mesmo se o botão de
                            # parar falhar, ou (modo auto) o silêncio não
                            # for detectado por algum motivo

        # FEATURE (modo mãos-livres / walkie-talkie): no modo "auto" não
        # precisa apertar o botão de novo pra parar — a própria gravação
        # detecta quando você parou de falar (silêncio sustentado) e
        # encerra sozinha, encurtando o tempo até a resposta em vez de
        # esperar um clique manual. Detecção simples por energia do
        # sinal (RMS), sem depender de nenhuma lib nova.
        mic_mode = self.settings.get("mic_mode", "manual")
        silence_ms = self.settings.get("mic_silence_ms", 900)
        _BLOCK_MS = 100
        _SILENCE_RMS_THRESHOLD = 0.012
        _blocks_of_silence_needed = max(1, int(silence_ms / _BLOCK_MS))
        _state = {"silent_blocks": 0, "heard_voice": False, "avisou_voz": False}

        def _on_audio_block(indata, num_frames, time_info, status):
            frames.append(indata.copy())
            rms = float(np.sqrt(np.mean(np.square(indata)))) if len(indata) else 0.0
            if rms >= _SILENCE_RMS_THRESHOLD and not _state["avisou_voz"]:
                _state["avisou_voz"] = True                 # v26: a 1ª vez que ela REALMENTE ouve voz (nos dois modos)
                _fase("captando")
            if mic_mode != "auto":
                return
            if rms >= _SILENCE_RMS_THRESHOLD:
                _state["heard_voice"] = True
                _state["silent_blocks"] = 0
            elif _state["heard_voice"]:
                _state["silent_blocks"] += 1
                if _state["silent_blocks"] >= _blocks_of_silence_needed:
                    self._stop_listening_flag.set()

        parcial = {"fim": threading.Event(), "texto": "", "amostras": 0}

        def _loop_parcial():
            """v27 — enquanto você fala: a cada ~1 s transcreve o que já foi dito e manda pra caixa de texto."""
            try:
                self._get_whisper_model()                    # se ainda não carregou, carrega AGORA (em paralelo com a fala)
            except Exception as e:
                print(f"[Zenith/Voz] transcrição ao vivo indisponível: {e}")
                return
            intervalo = float(self.settings.get("mic_parcial_intervalo", 1.0))
            while not parcial["fim"].wait(intervalo):
                snap = list(frames)
                n = sum(len(f) for f in snap)
                if n < _SAMPLE_RATE * 1.0 or n - parcial["amostras"] < _SAMPLE_RATE * 0.6:
                    continue
                try:
                    a = np.concatenate(snap, axis=0).flatten()
                    a = a[-int(_SAMPLE_RATE * 20):]            # só os últimos 20 s (o final pega tudo)
                    texto = self._transcrever_audio(a, beam=1)
                except Exception as e:
                    print(f"[Zenith/Voz] erro na transcrição ao vivo: {e}")
                    continue
                if parcial["fim"].is_set():
                    break
                parcial["amostras"] = n
                parcial["texto"] = texto
                if texto:
                    try:
                        on_parcial(texto)
                    except Exception:
                        pass

        if on_parcial is not None and self.settings.get("mic_transcricao_ao_vivo", True):
            threading.Thread(target=_loop_parcial, daemon=True, name="zenith-mic-parcial").start()
        # v29: "mic_device" escolhido pelo usuário. Só passa a chave `device` quando há um escolhido —
        # sem ele o sounddevice usa o padrão do Windows (e é assim que sempre funcionou).
        kwargs_mic = {"samplerate": _SAMPLE_RATE, "channels": 1, "dtype": "float32",
                      "blocksize": int(_SAMPLE_RATE * _BLOCK_MS / 1000),
                      "callback": _on_audio_block}
        dispositivo = self._dispositivo_mic()
        if dispositivo is not None:
            kwargs_mic["device"] = dispositivo
        try:
            with self._abrir_microfone(kwargs_mic):
                _fase("ouvindo")                             # v26: o microfone abriu, pode falar
                self._stop_listening_flag.wait(timeout=MAX_SEGUNDOS)
        except Exception as e:
            _log_voz(f"Erro acessando o microfone: {e}")
            self.ultimo_motivo_mic = "erro_mic"
            self._is_listening = False
            callback_quando_ouvir("")
            return

        self._is_listening = False
        parcial["fim"].set()                                  # v27: acabou de gravar: a transcrição ao vivo para

        if not frames:
            self.ultimo_motivo_mic = "nada_chegou"           # v29: o dispositivo abriu e não mandou nada
            callback_quando_ouvir("")
            return

        audio = np.concatenate(frames, axis=0).flatten()
        # v29 — quanto som realmente entrou: pico (0..1) do que foi gravado.
        self.ultimo_nivel_mic = round(float(np.max(np.abs(audio))) if len(audio) else 0.0, 4)
        _log_voz(f"Microfone '{self.ultimo_dispositivo_mic}': {len(audio) / _SAMPLE_RATE:.2f}s gravados, "
                 f"pico {self.ultimo_nivel_mic:.4f}.")
        # menos de ~0.3s de áudio: provavelmente só ruído/clique acidental
        if len(audio) < _SAMPLE_RATE * 0.3:
            self.ultimo_motivo_mic = "curto"
            callback_quando_ouvir("")
            return


        _fase("transcrevendo")                               # v26
        # v27 — atalho: se a transcrição ao vivo JÁ cobriu quase todo o áudio (sobraram < 0,35 s), o texto dela é o final
        # (instantâneo). Senão, uma passada rápida (beam 1) com o modelo que já está carregado.
        if (parcial["texto"] and len(audio) <= _SAMPLE_RATE * 20
                and len(audio) - parcial["amostras"] < _SAMPLE_RATE * 0.35):
            callback_quando_ouvir(parcial["texto"])
            return
        try:
            # AJUSTE (mesmo motivo de antes): condition_on_previous_text=False evita que um erro de reconhecimento
            # "contamine" o resto da frase; o initial_prompt avisa o nome da IA de antemão (ver _transcrever_audio).
            texto = self._transcrever_audio(audio)
        except Exception as e:
            _log_voz(f"Erro transcrevendo áudio: {e}")
            texto = ""

        if not texto:
            # v29 — NÃO entender tem duas causas MUITO diferentes, e o usuário precisa saber qual foi:
            # quase silêncio (microfone mudo/errado) ou som que o Whisper não virou texto (ruído, fala
            # longe). O nível medido decide qual das duas mensagens aparece. Importante: medir NÃO
            # impede a transcrição — o áudio é sempre transcrito; a medição só explica a falha.
            minimo = float(self.settings.get("mic_nivel_minimo", 0.06) or 0.0)
            self.ultimo_motivo_mic = "silencio" if self.ultimo_nivel_mic < minimo else "nao_transcreveu"
        callback_quando_ouvir(texto)



# ---- v1.11 (port celular): tocar/esperar/descarregar o áudio. No PC é EXATAMENTE o pygame de sempre. -------------------
def _audio_tocar(voz, caminho: str) -> None:
    if zenith_plataforma.detectar() == "android":
        zenith_plataforma.obter().tocar_audio(caminho, voz.current_volume)
        return
    pygame.mixer.music.load(caminho)
    pygame.mixer.music.set_volume(voz.current_volume)
    pygame.mixer.music.play()


def _audio_ocupado() -> bool:
    if zenith_plataforma.detectar() == "android":
        try:
            return bool(zenith_plataforma.obter().audio_ocupado())
        except Exception:
            return False
    return bool(pygame.mixer.music.get_busy())


def _audio_descarregar() -> None:
    if zenith_plataforma.detectar() == "android":
        return
    try:
        pygame.mixer.music.unload()
    except Exception:
        pass


class _MicAndroid:
    """v1.11 — faz o microfone do Android (pela plataforma) parecer um `sd.InputStream`: entrega blocos float32 de
    exatamente `bloco` amostras (100 ms) ao MESMO callback, então a detecção de silêncio e a transcrição ao vivo ficam
    iguais às do PC, mesmo que o app mande os pedaços em tamanhos quebrados."""

    def __init__(self, plat, callback, taxa: int, bloco: int):
        self._plat, self._callback = plat, callback
        self._taxa, self._bloco = int(taxa), max(1, int(bloco))
        self._pendente = bytearray()
        self._lock = threading.Lock()

    def _receber(self, pcm16: bytes) -> None:
        with self._lock:
            self._pendente += pcm16
            passo = self._bloco * 2                        # 16 bits = 2 bytes por amostra
            while len(self._pendente) >= passo:
                pedaco = bytes(self._pendente[:passo])
                del self._pendente[:passo]
                indata = (np.frombuffer(pedaco, dtype="<i2").astype("float32") / 32768.0).reshape(-1, 1)
                self._callback(indata, len(indata), None, None)

    def __enter__(self):
        self._plat.iniciar_microfone(self._receber, self._taxa)
        return self

    def __exit__(self, *_):
        try:
            self._plat.parar_microfone()
        except Exception:
            pass
        return False


class FalaStream:
    """Fala em pedaços (v24). `add(texto)` recebe frases (ou o texto todo); o PRODUTOR gera o áudio de cada pedaço
    (Edge-TTS/ElevenLabs + RVC se houver) e o TOCADOR toca na ordem. Isso também conserta um problema da versão
    anterior: o `pygame.mixer.music.queue()` guarda UM áudio só — se a geração fosse mais rápida que a fala, as
    frases do meio eram substituídas e puladas."""

    PRIMEIRO_MIN = 6        # a 1ª frase pode ser curta ("Claro!"): sai mais rápido
    MIN = 24                # as demais: junta frases miúdas pra não picotar o áudio
    _contador = itertools.count(1)

    def __init__(self, voz, on_start=None, on_end=None, expressao: str = "neutral"):
        self._voz = voz
        self._on_start, self._on_end = on_start, on_end
        self._expressao = expressao
        self._id = next(FalaStream._contador)
        self._buf = ""
        self._enviados = 0
        self._textos = queue.Queue()
        self._audios = queue.Queue()
        self._cancelado = threading.Event()
        self._silencioso = False
        self._encerrou = False
        self._lock = threading.Lock()
        threading.Thread(target=self._produzir, daemon=True, name=f"zenith-voz-prod-{self._id}").start()
        threading.Thread(target=self._tocar, daemon=True, name=f"zenith-voz-toca-{self._id}").start()

    # ---------------------------------------------------------------- entrada
    def add(self, texto: str):
        with self._lock:
            if self._cancelado.is_set() or self._encerrou:
                return
            limpo = self._voz._limpar_para_voz(texto or "")
            if not limpo:
                return
            self._buf = f"{self._buf} {limpo}".strip()
            if len(self._buf) >= (self.PRIMEIRO_MIN if self._enviados == 0 else self.MIN):
                self._empurrar()

    def _empurrar(self):
        for pedaco in self._voz._dividir_em_frases(self._buf):
            if pedaco.strip():
                self._textos.put(pedaco)
                self._enviados += 1
        self._buf = ""

    def fim(self):
        with self._lock:
            if self._encerrou:
                return
            if self._buf.strip():
                self._empurrar()
            self._encerrou = True
            self._textos.put(None)

    def cancelar(self, silencioso: bool = False):
        """Corta a fala. `silencioso=True` = foi substituída por outra fala (não dispara on_end, pra o avatar não
        piscar pra 'parado' no meio da fala nova)."""
        self._silencioso = self._silencioso or silencioso
        self._cancelado.set()
        self._encerrou = True
        self._textos.put(None)

    # ---------------------------------------------------------------- threads
    def _produzir(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        n = 0
        try:
            while True:
                frase = self._textos.get()
                if frase is None or self._cancelado.is_set():
                    break
                caminho = os.path.join(str(TEMP_DIR), f"_zenith_voz_{self._id}_{n}.mp3")
                n += 1
                try:
                    os.makedirs(str(TEMP_DIR), exist_ok=True)
                    audio = loop.run_until_complete(self._voz._gerar_audio_base(frase, caminho, expressao=self._expressao))
                    audio = self._voz._aplicar_rvc(audio)
                except Exception as e:
                    print(f"[Zenith/Voz] Não consegui gerar o áudio de um pedaço: {e}")
                    continue
                if self._cancelado.is_set():
                    break
                self._audios.put(audio)
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._audios.put(None)

    def _tocar(self):
        comecou = False
        try:
            while True:
                audio = self._audios.get()
                if audio is None or self._cancelado.is_set():
                    break
                try:
                    _audio_tocar(self._voz, audio)
                except Exception as e:
                    print(f"[Zenith/Voz] Erro ao tocar um pedaço: {e}")
                    continue
                if not comecou:
                    comecou = True
                    if self._on_start:
                        self._on_start()
                while _audio_ocupado() and not self._cancelado.is_set():
                    time.sleep(0.03)
                _audio_descarregar()
                self._apagar(audio)
        except Exception as e:
            print(f"[Zenith/Voz] Erro ao falar: {e}")
        finally:
            while True:                                   # apaga o que sobrou na fila
                try:
                    resto = self._audios.get_nowait()
                except queue.Empty:
                    break
                if resto:
                    self._apagar(resto)
            if self._on_end and not self._silencioso:
                self._on_end()

    @staticmethod
    def _apagar(caminho: str):
        try:
            os.remove(caminho)
        except OSError:
            pass
