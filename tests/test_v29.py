"""
Testes do v29 — MICROFONE: por que o Anderson apertou o microfone 4 vezes e recebeu
"não consegui entender nada" 4 vezes, sem nenhuma pista do motivo (16/10 20:24).

O que estes testes cobrem:
  • o Zenith MEDE o que gravou (pico de volume) e diz, em português, o que houve;
  • quando o filtro de silêncio do Whisper descarta TUDO, ele tenta de novo sem o filtro;
  • dá pra escolher o microfone ("mic_device") por nome ou número;
  • o diagnóstico da voz mostra o motivo REAL de o áudio não ter iniciado.

Rodar: python -m unittest tests.test_v29 -v
NÃO provam: o microfone de verdade (nenhum teste aqui abre hardware) nem o .exe compilado.
Isso é verificado rodando `Zenith.exe --zenith-run-script` com o diagnóstico — ver
DIAGNOSTICO_MICROFONE no fim deste arquivo.
"""
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_interaction as Z


class FakeSettings:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **d):
        self.d = dict(d)

    def get(self, chave, padrao=None):
        v = self.d.get(chave, padrao)
        return padrao if v is None else v


class FakeSeg:
    def __init__(self, t):
        self.text = t


class FakeModelo:
    """Devolve texto; registra com que filtro de silêncio (vad_filter) foi chamado."""

    def __init__(self, texto="fala reconhecida", vazia_com_vad=False):
        self.texto = texto
        self.vazia_com_vad = vazia_com_vad
        self.vad_usado = []

    def transcribe(self, audio, **kw):
        self.vad_usado.append(bool(kw.get("vad_filter", True)))
        if self.vazia_com_vad and kw.get("vad_filter"):
            return iter([]), None
        return iter([FakeSeg(self.texto)]), None


class FakeStream:
    """microfone de mentira: alimenta blocos com um volume fixo, num tamanho fixo de array."""

    def __init__(self, samplerate, channels, dtype, blocksize, callback, device=None):
        self.cb, self.bs, self.device, self.run = callback, blocksize, device, False

    def __enter__(self):
        import numpy as np
        self.run = True

        def alimentar():
            for _ in range(30):
                if not self.run:
                    break
                self.cb(np.full((self.bs, 1), FakeStream.VALOR, dtype="float32"), self.bs, None, None)
                time.sleep(0.02)
        self.t = threading.Thread(target=alimentar)
        self.t.start()
        return self

    def __exit__(self, *a):
        self.run = False
        self.t.join()


def _interacao(**cfg):
    import numpy as np
    padrao = {"mic_mode": "manual", "mic_parcial_intervalo": 0.25, "whisper_beam": 1,
              "persona_name": "Zenith", "mic_transcricao_ao_vivo": False}
    padrao.update(cfg)
    patches = [mock.patch.object(Z, "sd", types.SimpleNamespace(InputStream=FakeStream,
                                                                query_devices=lambda *a: [])),
               mock.patch.object(Z, "np", np),
               mock.patch.object(Z, "WhisperModel", lambda *a, **k: FakeModelo()),
               mock.patch.object(Z, "_log_voz")]
    for p in patches:
        p.start()
    z = object.__new__(Z.ZenithInteraction)
    z.settings = FakeSettings(**padrao)
    z._stop_listening_flag = threading.Event()
    z._is_listening = True
    z._whisper_model = None
    z._whisper_lock_carga = threading.Lock()
    z._whisper_lock_uso = threading.Lock()
    z.ultimo_motivo_mic = ""
    z.ultimo_nivel_mic = 0.0
    z.ultimo_dispositivo_mic = ""
    return z


def _escutar(z, segundos=0.8):
    finais, fases = [], []
    th = threading.Thread(target=z._escutar_sync, args=(finais.append, fases.append, None))
    th.start()
    time.sleep(segundos)
    z._stop_listening_flag.set()
    th.join(15)
    return finais, fases


# ====================================================================== medição de volume
class MedicaoDeVolumeTests(unittest.TestCase):
    def test_silencio_e_medido_e_explicado(self):
        """O caso do Anderson: ele apertou o mic e o áudio chegou mudo. Antes: 'não entendi nada' e nada mais.

        O modelo de mentira não devolve texto (é o que o Whisper de verdade faz em silêncio — medido no
        PC dele: 6 s de sala quieta = string vazia). O que a v29 acrescenta é DIZER o motivo.
        """
        FakeStream.VALOR = 0.002                       # só o chiado da placa (medido no PC dele: 0.0021)
        z = _interacao()
        z.settings.d["mic_sem_vad_fallback"] = False   # sem plano B, pra isolar a explicação do silêncio
        z._get_whisper_model = lambda: FakeModelo(texto="", vazia_com_vad=True)
        finais, _fases = _escutar(z)

        self.assertEqual(finais, [""])                  # não inventou texto nenhum
        self.assertEqual(z.ultimo_motivo_mic, "silencio")
        self.assertLess(z.ultimo_nivel_mic, 0.03)       # o volume ficou registrado, não perdido

        explicacao = z.explicacao_falha_mic()
        self.assertIn("0.2%", explicacao)               # o número medido, na mensagem do usuário
        self.assertIn("mudo", explicacao)               # e o que fazer sobre isso
        self.assertNotEqual(explicacao, "")             # nunca mais uma mensagem sem motivo

    def test_fala_de_verdade_nao_e_tratada_como_silencio(self):
        FakeStream.VALOR = 0.2
        z = _interacao()
        finais, fases = _escutar(z)

        self.assertEqual(z.ultimo_motivo_mic, "")       # não sobrou motivo de falha
        self.assertGreater(z.ultimo_nivel_mic, 0.03)
        self.assertTrue(finais[0].startswith("fala"))   # o texto do modelo chegou ao chat
        self.assertIn("transcrevendo", fases)

    def test_som_que_nao_vira_texto_tem_explicacao_propria(self):
        """Ruído/chiado alto não é silêncio nem fala: a mensagem é outra, com o pico medido."""
        FakeStream.VALOR = 0.2
        z = _interacao()
        z._get_whisper_model = lambda: FakeModelo(texto="", vazia_com_vad=True)
        z.settings.d["mic_sem_vad_fallback"] = False    # sem o plano B, pra isolar o caso
        finais, _fases = _escutar(z)

        self.assertEqual(finais, [""])
        self.assertEqual(z.ultimo_motivo_mic, "nao_transcreveu")
        explicacao = z.explicacao_falha_mic()
        self.assertIn("20.0%", explicacao)
        self.assertIn("texto", explicacao)


# ====================================================================== plano B do Whisper
class FiltroDeSilencioTests(unittest.TestCase):
    def _z(self, volume=0.2, **cfg):
        import numpy as np
        z = _interacao()
        z.settings.d.update(cfg)
        z._whisper_model = FakeModelo(texto="bom dia Zenith", vazia_com_vad=True)
        return z, np.full(16000, volume, dtype="float32")

    def test_vad_que_descarta_tudo_tenta_de_novo_sem_ele(self):
        z, audio = self._z()
        texto = z._transcrever_audio(audio)

        self.assertEqual(texto, "bom dia Zenith")                 # o áudio dele não virou silêncio nenhum
        self.assertEqual(z._whisper_model.vad_usado, [True, False])   # 1ª com filtro, 2ª sem

    def test_plano_b_pode_ser_desligado(self):
        z, audio = self._z(mic_sem_vad_fallback=False)
        texto = z._transcrever_audio(audio)

        self.assertEqual(texto, "")
        self.assertEqual(z._whisper_model.vad_usado, [True])     # não insistiu

    def test_ruido_sem_energia_de_fala_nao_ganha_plano_b(self):
        """Medido de verdade: 6 s de chiado sem filtro virou "Deixe-me ver o que é isso." — inventar
        fala é pior do que não entender nada, então o plano B exige energia de fala no áudio."""
        z, audio = self._z(volume=0.002)                # chiado, abaixo do mínimo (0.03)
        texto = z._transcrever_audio(audio)

        self.assertEqual(texto, "")
        self.assertEqual(z._whisper_model.vad_usado, [True])     # nem tentou inventar


# ====================================================================== escolha do microfone
class EscolhaDoMicrofoneTests(unittest.TestCase):
    APARELHOS = [{"name": "Mapeador de som da Microsoft - Input", "max_input_channels": 2},
                 {"name": "Microfone (Brio 105)", "max_input_channels": 1},
                 {"name": "Speakers (Realtek HD Audio output)", "max_input_channels": 0}]

    def _z(self, mic_device):
        z = _interacao(mic_device=mic_device)
        Z.sd.query_devices = lambda dev=None: (self.APARELHOS if dev is None else self.APARELHOS[dev])
        return z

    def test_vazio_usa_o_padrao_do_windows(self):
        z = self._z("")
        self.assertIsNone(z._dispositivo_mic())
        self.assertEqual(z._nome_dispositivo_mic(), "padrão do Windows")

    def test_por_nome_e_por_numero(self):
        self.assertEqual(self._z("Brio")._dispositivo_mic(), 1)          # o problema do Anderson: falar no Brio
        self.assertEqual(self._z("3")._dispositivo_mic(), 3)
        self.assertIsNone(self._z("microfone que não existe")._dispositivo_mic())

    def test_o_escolhido_chega_no_stream_de_audio(self):
        FakeStream.VALOR = 0.2
        z = self._z("Brio")
        _escutar(z)
        self.assertEqual(z.ultimo_dispositivo_mic, "Microfone (Brio 105)")


# ====================================================================== diagnóstico da voz
class DiagnosticoDaVozTests(unittest.TestCase):
    def test_motivo_real_do_audio_nao_iniciar(self):
        """No PC dele o diagnóstico dizia só 'Áudio (pygame): NÃO iniciou — sem áudio'. Agora diz por quê."""
        z = object.__new__(Z.ZenithInteraction)
        z.settings = FakeSettings()
        z._ready = False
        z._mixer_erro = "PortAudioError: no default output device"
        z.ultimo_motor_voz = "-"
        z.ultimo_status_rvc = "-"
        z.ultimo_motivo_mic = ""
        z.ultimo_nivel_mic = 0.0

        with mock.patch.object(Z, "sd", None), mock.patch.object(Z, "np", None):
            texto = z.diagnostico_voz()

        self.assertIn("no default output device", texto)

    def test_microfone_indisponivel_e_dito_com_motivo(self):
        z = object.__new__(Z.ZenithInteraction)
        z.settings = FakeSettings()
        z._ready = True
        z._mixer_erro = ""
        z.ultimo_motor_voz = "-"
        z.ultimo_status_rvc = "-"
        z.ultimo_motivo_mic = "silencio"
        z.ultimo_nivel_mic = 0.0021

        with mock.patch.object(Z, "sd", None), mock.patch.object(Z, "np", None):
            texto = z.diagnostico_voz()

        self.assertIn("Microfone: INDISPONÍVEL", texto)


# ====================================================================== a mensagem no chat
class MensagemNoChatTests(unittest.TestCase):
    """O que o Anderson VÊ. Antes: 'não consegui entender nada — tenta de novo?' 4 vezes."""

    def test_aviso_do_microfone_leva_o_motivo_medido(self):
        from brain import zenith_headless as ZH

        enviados = []
        b = object.__new__(ZH.ZenithHeadlessBrain)
        b.bridge = types.SimpleNamespace(send=lambda msg: enviados.append(msg))
        b.interaction = types.SimpleNamespace(
            comecar_a_escutar=lambda cb, on_fase=None, on_parcial=None: (cb(""), True)[1],
            explicacao_falha_mic=lambda: "O áudio chegou praticamente mudo (volume máximo 0.2%) pelo "
                                         "'Microfone (Brio 105)'.")
        b._mic_fase = lambda *a, **k: None
        b._mic_parcial = lambda *a, **k: None
        b._proxima_fala_vira_nota = False

        b._start_listening()

        avisos = [m.get("text", "") for m in enviados if m.get("action") == "chat_message"]
        self.assertEqual(len(avisos), 1)
        self.assertIn("Não consegui entender nada", avisos[0])          # o aviso antigo continua lá
        self.assertIn("0.2%", avisos[0])                                # mas agora com o motivo
        self.assertIn("Brio", avisos[0])

    def test_sem_motivo_conhecido_o_aviso_antigo_continua(self):
        from brain import zenith_headless as ZH

        enviados = []
        b = object.__new__(ZH.ZenithHeadlessBrain)
        b.bridge = types.SimpleNamespace(send=lambda msg: enviados.append(msg))
        b.interaction = types.SimpleNamespace(
            comecar_a_escutar=lambda cb, on_fase=None, on_parcial=None: (cb(""), True)[1],
            explicacao_falha_mic=lambda: "")
        b._mic_fase = lambda *a, **k: None
        b._mic_parcial = lambda *a, **k: None
        b._proxima_fala_vira_nota = False

        b._start_listening()

        avisos = [m.get("text", "") for m in enviados if m.get("action") == "chat_message"]
        self.assertEqual(avisos, ["🎙️ Não consegui entender nada. Tenta de novo?"])


# ====================================================================== build interrompido
class BuildNaoApagaDadosDoUsuarioTests(unittest.TestCase):
    """Um build interrompido (Ctrl+C, duas compilações ao mesmo tempo) deixava os dados do usuário
    guardados na pasta de resgate. O build SEGUINTE apagava essa pasta — ou seja: fechar a janela
    no momento errado custava a chave de API, as conversas e os 464 MB de modelos do Anderson.
    Isso aconteceu de verdade em 17/10 e está consertado aqui."""

    def setUp(self):
        import shutil
        import tempfile
        import build_exe as B

        self.B, self.shutil = B, shutil
        self.raiz = Path(tempfile.mkdtemp(prefix="zenith_build_"))
        self.addCleanup(shutil.rmtree, str(self.raiz), True)
        for attr, valor in (("HERE", str(self.raiz)),
                            ("_RESGATE", str(self.raiz / "_dados_do_usuario_resgatados"))):
            original = getattr(B, attr)
            setattr(B, attr, valor)
            self.addCleanup(setattr, B, attr, original)

    def _dist(self):
        p = self.raiz / "dist" / "Zenith"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _resgate(self):
        return self.raiz / "_dados_do_usuario_resgatados"

    def _config_com_chave(self, pasta, chave="minha-chave-secreta"):
        (pasta / "config").mkdir(parents=True, exist_ok=True)
        (pasta / "config" / "settings.json").write_text('{"gemini_key": "%s"}' % chave, encoding="utf-8")

    def test_build_interrompido_nao_custa_os_dados(self):
        # 1) build anterior morreu DEPOIS de guardar e ANTES de devolver
        self._config_com_chave(self._resgate())
        self.assertFalse((self.raiz / "dist" / "Zenith").exists())    # nem o dist/ sobrou

        # 2) build novo começa (é isto que apagava tudo)
        self.B._clean_old_build()

        # 3) os dados continuam existindo, guardados — e voltam no fim
        self.B._restaurar_dados_do_usuario()
        texto = (self._dist() / "config" / "settings.json").read_text(encoding="utf-8")
        self.assertIn("minha-chave-secreta", texto)
        self.assertFalse(self._resgate().exists())                    # resgate consumido, não descartado

    def test_build_normal_guarda_e_devolve_como_sempre(self):
        self._config_com_chave(self._dist(), "chave-do-dist")
        (self._dist() / "models" / "whisper").mkdir(parents=True)
        (self._dist() / "models" / "whisper" / "modelo.bin").write_bytes(b"pesado")

        self.B._clean_old_build()                                     # guarda e apaga o dist/
        self.assertTrue((self._resgate() / "config" / "settings.json").exists())

        self._dist().mkdir(parents=True, exist_ok=True)               # o build recriou o dist/ do zero
        (self._dist() / "Zenith.exe").write_bytes(b"exe")
        self.B._restaurar_dados_do_usuario()

        self.assertIn("chave-do-dist", (self._dist() / "config" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((self._dist() / "models" / "whisper" / "modelo.bin").read_bytes(), b"pesado")


DIAGNOSTICO_MICROFONE = """
Como verificar o microfone e a voz DENTRO do .exe compilado (foi assim que a v29
foi conferida, sem depender de ouvir nada):

    cd dist/Zenith
    ./Zenith.exe --zenith-run-script C:\\Zenith\\Zenith\\temp\\_diag_mic.py
    type C:\\Zenith\\Zenith\\temp\\_diag_mic_resultado.txt

Isso lista os microfones que o .exe enxerga, grava alguns segundos de verdade,
mostra o pico de volume medido e transcreve (com e sem o filtro de silêncio).
O mesmo vale para o áudio de saída com o _diag_audio.py.
"""


if __name__ == "__main__":
    unittest.main(verbosity=2)
