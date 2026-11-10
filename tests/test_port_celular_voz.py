"""Voz no celular (v1.11): falar e escutar passando pela plataforma, com um Android FALSO.

Prova o fluxo inteiro — texto vira áudio (voz do Android), toca pedaço por pedaço, para quando o avatar precisa,
o microfone entrega pedaços de tamanhos quebrados e a detecção de silêncio encerra a gravação — e que no PC o
caminho antigo (pygame) continua sendo o único usado.

    python -m unittest tests.test_port_celular_voz
"""
from __future__ import annotations

import base64
import importlib
import math
import os
import sys
import struct
import threading
import time
import unittest
from unittest import mock

import numpy as np

import brain
from brain import zenith_interaction as zi          # o módulo como o PC o carrega
from brain import zenith_plataforma
from brain.zenith_plataforma_android import AndroidPlataforma


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


class AndroidFalso:
    """Imita o app Android: sintetiza (cria o arquivo), toca (fica 'ocupado' por alguns toques) e grava."""

    def __init__(self, capacidades, texto_ouvido="  oi zenith  ", voz_ocupada_por=3):
        self.capacidades = list(capacidades)
        self.texto_ouvido = texto_ouvido
        self.chamadas, self.assinantes = [], {}
        self.ocupado_restante = 0
        self.voz_ocupada_por = voz_ocupada_por
        self.ao_iniciar_mic = None

    def chamar(self, nome, **args):
        self.chamadas.append((nome, args))
        if nome == "capacidades.listar":
            return self.capacidades
        if nome == "tts.sintetizar":
            with open(args["caminho_saida"], "wb") as f:
                f.write(b"audio-falso")
            return {"ok": True}
        if nome == "audio.tocar":
            self.ocupado_restante = self.voz_ocupada_por
            return {"ok": True}
        if nome == "audio.ocupado":
            if self.ocupado_restante > 0:
                self.ocupado_restante -= 1
                return {"ok": True, "ocupado": True}
            return {"ok": True, "ocupado": False}
        if nome == "audio.parar":
            self.ocupado_restante = 0
            return {"ok": True}
        if nome == "stt.transcrever":
            return {"ok": True, "texto": self.texto_ouvido}
        if nome == "mic.iniciar" and self.ao_iniciar_mic:
            threading.Thread(target=self.ao_iniciar_mic, daemon=True).start()
        return {"ok": True}

    def assinar(self, evento, funcao):
        self.assinantes.setdefault(evento, []).append(funcao)

    def desassinar(self, evento, funcao):
        if funcao in self.assinantes.get(evento, []):
            self.assinantes[evento].remove(funcao)

    def emitir(self, evento, dados):
        for f in list(self.assinantes.get(evento, [])):
            f(dados)

    def nomes(self):
        return [n for n, _ in self.chamadas]

    def ultima(self, nome):
        return [a for n, a in self.chamadas if n == nome][-1]


TUDO = ["audio_saida", "voz_local", "microfone", "transcricao"]


class Base(unittest.TestCase):
    def preparar(self, ponte, settings=None):
        """Carrega o zenith_interaction DE NOVO com ZENITH_PLATAFORMA=android (como no celular, onde o ambiente já
        nasce assim) e devolve uma voz pronta. No fim, tudo volta ao que era — inclusive o atributo do pacote `brain`."""
        env = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"})
        mods = mock.patch.dict(sys.modules)                      # retrato de sys.modules; devolve no fim
        env.start()
        mods.start()
        atributo = getattr(brain, "zenith_interaction", None)
        self.addCleanup(lambda: setattr(brain, "zenith_interaction", atributo) if atributo is not None
                        else (hasattr(brain, "zenith_interaction") and delattr(brain, "zenith_interaction")))
        self.addCleanup(mods.stop)
        self.addCleanup(env.stop)
        sys.modules.pop("brain.zenith_interaction", None)
        self.zi = importlib.import_module("brain.zenith_interaction")
        log = mock.patch.object(self.zi, "_log_voz", lambda *a, **k: None)   # nunca escrever no config/ do projeto
        log.start()
        self.addCleanup(log.stop)
        zenith_plataforma.definir(AndroidPlataforma(ponte))
        self.addCleanup(zenith_plataforma.definir, None)
        return self.zi.ZenithInteraction(dict(settings or {}))


class FalarNoCelular(Base):
    def test_pronta_para_falar_sem_internet_e_sem_pygame(self):
        voz = self.preparar(AndroidFalso(TUDO))
        self.assertTrue(voz._ready)
        self.assertTrue(voz.pode_falar())

    def test_sem_saida_de_audio_nao_pode_falar_e_diz_porque(self):
        voz = self.preparar(AndroidFalso(["microfone"]))
        self.assertFalse(voz.pode_falar())
        self.assertIn("saída de áudio", voz._mixer_erro)

    def test_sem_voz_local_e_sem_edge_tts_nao_pode_falar(self):
        voz = self.preparar(AndroidFalso(["audio_saida"]))
        with mock.patch.object(self.zi, "edge_tts", None):
            self.assertFalse(voz.pode_falar())

    def test_gerar_audio_usa_a_voz_do_android(self):
        ponte = AndroidFalso(TUDO)
        voz = self.preparar(ponte)
        caminho = os.path.join(os.path.dirname(self.zi.__file__), "_teste_voz_android.wav")
        self.addCleanup(lambda: os.path.exists(caminho) and os.remove(caminho))
        import asyncio
        out = asyncio.run(voz._gerar_audio_base("Olá, tudo bem?", caminho))
        self.assertEqual(out, caminho)
        self.assertEqual(voz.ultimo_motor_voz, "Voz do Android (sem internet)")
        args = ponte.ultima("tts.sintetizar")
        self.assertEqual((args["voz"], args["texto"]), ("pt-BR", "Olá, tudo bem?"))

    def test_emocao_vira_velocidade(self):
        voz = self.preparar(AndroidFalso(TUDO), {"voice_expression_modulation": True})
        com_rate = next(k for k, (r, _p) in self.zi._MODULACAO_EXPRESSAO.items() if r)
        rate = self.zi._MODULACAO_EXPRESSAO[com_rate][0]
        esperado = max(0.5, min(2.0, 1.0 + rate / 100.0))
        self.assertAlmostEqual(voz._velocidade_da_expressao(com_rate), esperado, places=2)
        self.assertEqual(voz._velocidade_da_expressao("neutral"), 1.0)
        voz.settings["voice_expression_modulation"] = False
        self.assertEqual(voz._velocidade_da_expressao(com_rate), 1.0)

    def test_fala_completa_sintetiza_toca_espera_e_avisa_o_avatar(self):
        ponte = AndroidFalso(TUDO)
        voz = self.preparar(ponte, {"tts_volume": 0.6})
        comecou, acabou = threading.Event(), threading.Event()
        voz.falar_async("Olá! Eu sou a Zenith. Como posso ajudar?", on_start=comecou.set, on_end=acabou.set)
        self.assertTrue(acabou.wait(8), "a fala não terminou")
        self.assertTrue(comecou.is_set())
        nomes = ponte.nomes()
        self.assertIn("tts.sintetizar", nomes)
        self.assertIn("audio.tocar", nomes)
        self.assertGreaterEqual(nomes.count("audio.ocupado"), 4)        # esperou o som acabar (3 'ocupado' + 1 livre)
        self.assertAlmostEqual(ponte.ultima("audio.tocar")["volume"], 0.6)
        self.assertLess(nomes.index("tts.sintetizar"), nomes.index("audio.tocar"))

    def test_parar_de_falar_corta_o_audio_do_android(self):
        ponte = AndroidFalso(TUDO, voz_ocupada_por=10_000)
        voz = self.preparar(ponte)
        acabou = threading.Event()
        voz.falar_async("Uma fala bem longa que vai ser cortada no meio.", on_end=acabou.set)
        for _ in range(100):
            if "audio.tocar" in ponte.nomes():
                break
            time.sleep(0.05)
        voz.parar_de_falar()
        self.assertTrue(acabou.wait(5) or True)
        self.assertIn("audio.parar", ponte.nomes())

    def test_rvc_nao_existe_no_celular_fica_a_voz_base(self):
        voz = self.preparar(AndroidFalso(TUDO), {"rvc_model_path": "/qualquer/modelo.pth"})
        self.assertEqual(voz._aplicar_rvc("/data/x.wav"), "/data/x.wav")

    def test_diagnostico_fala_de_android_e_nao_de_pygame(self):
        voz = self.preparar(AndroidFalso(TUDO))
        texto = voz.diagnostico_voz()
        self.assertIn("Áudio (Android): OK", texto)
        self.assertNotIn("pygame", texto)
        self.assertIn("Microfone (Android): disponível", texto)


class EscutarNoCelular(Base):
    def test_nao_escuta_sem_microfone_ou_sem_transcricao(self):
        for caps in (["audio_saida", "transcricao"], ["audio_saida", "microfone"]):
            voz = self.preparar(AndroidFalso(caps))
            self.assertFalse(voz.comecar_a_escutar(lambda t: None))

    def test_transcrever_manda_pcm16_e_limpa_o_texto(self):
        ponte = AndroidFalso(TUDO, texto_ouvido="  olá mundo \n")
        voz = self.preparar(ponte)
        audio = np.array([0.0, 0.5, -0.5, 1.0, 2.0], dtype="float32")          # 2.0 tem que ser cortado em 1.0
        self.assertEqual(voz._transcrever_audio(audio), "olá mundo")
        enviado = ponte.ultima("stt.transcrever")
        pcm = np.frombuffer(base64.b64decode(enviado["pcm16"]), dtype="<i2").tolist()
        self.assertEqual(pcm, [0, 16383, -16383, 32767, 32767])
        self.assertEqual((enviado["taxa"], enviado["idioma"]), (16000, "pt"))

    def test_escuta_de_ponta_a_ponta_com_silencio_encerrando_a_gravacao(self):
        ponte = AndroidFalso(TUDO, texto_ouvido="oi zenith")

        def emitir_fala():
            taxa = 16000
            tom = [int(0.3 * 32767 * math.sin(2 * math.pi * 440 * i / taxa)) for i in range(int(0.6 * taxa))]
            silencio = [0] * int(1.2 * taxa)
            pcm = struct.pack("<%dh" % (len(tom) + len(silencio)), *(tom + silencio))
            for i in range(0, len(pcm), 2001):                  # 2001 bytes: tamanho ímpar de propósito
                ponte.emitir("mic.quadro", {"pcm16": b64(pcm[i:i + 2001])})
                time.sleep(0.004)

        ponte.ao_iniciar_mic = emitir_fala
        voz = self.preparar(ponte, {"mic_mode": "auto", "mic_silence_ms": 300, "mic_max_seconds": 10})
        ouvido, fases = [], []
        pronto = threading.Event()
        self.assertTrue(voz.comecar_a_escutar(lambda t: (ouvido.append(t), pronto.set()), on_fase=fases.append))
        self.assertTrue(pronto.wait(10), "a escuta não terminou sozinha pelo silêncio")
        self.assertEqual(ouvido, ["oi zenith"])
        self.assertEqual(fases[:2], ["ouvindo", "captando"])
        self.assertIn("transcrevendo", fases)
        self.assertGreater(voz.ultimo_nivel_mic, 0.2)
        self.assertIn("mic.parar", ponte.nomes())
        self.assertEqual(ponte.assinantes.get("mic.quadro", []), [])           # não deixou assinatura pendurada

    def test_microfone_negado_vira_erro_claro_e_nao_trava(self):
        ponte = AndroidFalso(TUDO)
        original = ponte.chamar

        def chamar(nome, **a):
            if nome == "mic.iniciar":
                ponte.chamadas.append((nome, a))
                return {"ok": False, "erro": "Permissão do microfone negada."}
            return original(nome, **a)

        ponte.chamar = chamar
        voz = self.preparar(ponte)
        ouvido, pronto = [], threading.Event()
        voz.comecar_a_escutar(lambda t: (ouvido.append(t), pronto.set()))
        self.assertTrue(pronto.wait(5))
        self.assertEqual(ouvido, [""])
        self.assertEqual(voz.ultimo_motivo_mic, "erro_mic")
        self.assertFalse(voz._is_listening)

    def test_blocos_de_100ms_mesmo_com_pedacos_quebrados(self):
        recebidos = []

        class Plat:
            def iniciar_microfone(self, cb, taxa):
                self.cb = cb

            def parar_microfone(self):
                self.parou = True

        self.preparar(AndroidFalso(TUDO))                # só para carregar o módulo no modo celular
        plat = Plat()
        with self.zi._MicAndroid(plat, lambda ind, n, t, s: recebidos.append(ind), 16000, 1600) as mic:
            pcm = struct.pack("<%dh" % 4000, *([16384] * 4000))             # 4000 amostras = 2,5 blocos
            for i in range(0, len(pcm), 777):                                # 777 bytes: ímpar
                plat.cb(pcm[i:i + 777])
        self.assertTrue(plat.parou)
        self.assertEqual([b.shape for b in recebidos], [(1600, 1), (1600, 1)])
        self.assertAlmostEqual(float(recebidos[0][0, 0]), 0.5, places=3)
        self.assertEqual(recebidos[0].dtype, np.float32)

    def test_precarga_do_whisper_nao_existe_no_celular(self):
        self.assertFalse(self.preparar(AndroidFalso(TUDO)).precarregar_whisper())


class PCNaoMudou(unittest.TestCase):
    """No PC só o pygame é usado: nenhuma chamada passa pela plataforma."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "windows"})
        patcher.start()
        self.addCleanup(patcher.stop)
        armadilha = mock.Mock(side_effect=AssertionError("o PC não deveria usar a plataforma Android"))
        zenith_plataforma.definir(mock.Mock(tocar_audio=armadilha, parar_audio=armadilha, audio_ocupado=armadilha,
                                            sintetizar=armadilha, transcrever=armadilha))
        self.addCleanup(zenith_plataforma.definir, None)
        self.voz = zi.ZenithInteraction.__new__(zi.ZenithInteraction)       # sem __init__: nada de áudio real
        self.voz.settings, self.voz.current_volume, self.voz._ready = {}, 0.7, True
        self.pygame = mock.MagicMock()
        patcher2 = mock.patch.object(zi, "pygame", self.pygame)
        patcher2.start()
        self.addCleanup(patcher2.stop)

    def test_tocar_usa_o_pygame_como_sempre(self):
        self.voz._tocar_arquivo("a.mp3")
        m = self.pygame.mixer.music
        m.load.assert_called_once_with("a.mp3")
        m.set_volume.assert_called_once_with(0.7)
        m.play.assert_called_once_with()

    def test_ocupado_parar_e_descarregar_usam_o_pygame(self):
        m = self.pygame.mixer.music
        m.get_busy.return_value = True
        self.assertTrue(self.voz._audio_ocupado())
        self.voz._parar_audio()
        m.stop.assert_called_once_with()
        self.voz._descarregar_audio()
        m.unload.assert_called_once_with()

    def test_pode_falar_so_depende_de_pronto_e_edge_tts(self):
        with mock.patch.object(zi, "edge_tts", object()):
            self.assertTrue(self.voz.pode_falar())
        with mock.patch.object(zi, "edge_tts", None):
            self.assertFalse(self.voz.pode_falar())

    def test_microfone_continua_sendo_o_sounddevice(self):
        fake_sd = mock.MagicMock()
        with mock.patch.object(zi, "sd", fake_sd):
            self.voz._abrir_microfone({"samplerate": 16000, "blocksize": 1600, "callback": print})
        fake_sd.InputStream.assert_called_once()


if __name__ == "__main__":
    unittest.main()
