"""
Testes do v20 — corrigem o que as capturas do Anderson mostraram + base de "vida" do avatar.

O que cobrem (tudo sem Godot, sem rede, sem Windows):
  * zenith_janela  — clique-atravessa por estilo de janela (API do Windows FALSA);
  * zenith_gestos  — expressão/gesto a partir do texto;
  * zenith_fundo   — qualquer imagem/vídeo como fundo (Pillow e OpenCV de verdade, quando instalados);
  * zenith_reset   — "Resetar tudo" agendado (numa pasta temporária);
  * zenith_rvc     — processo auxiliar do RVC com um `rvc_python` FALSO, processo real;
  * handlers do Cérebro e contratos Python <-> Godot (nomes de gesto, shaders, métodos chamados);
  * a matemática de "apontar osso" (simulação com 400 convenções de eixo aleatórias).

O que NÃO provam: o Godot de verdade (braços, rosto, transparência, painel). Isso só se vê rodando.
Rodar: python -m unittest tests.test_v20 -v
"""
import importlib.util
import json
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_janela as J
from brain import zenith_gestos as G
from brain import zenith_fundo as F
from brain import zenith_reset as R
from brain import zenith_rvc as V


def _real(modulo: str) -> bool:
    """True só se o módulo é o de verdade (os testes trocam alguns por MagicMock)."""
    try:
        m = __import__(modulo)
        return getattr(m, "__file__", None) is not None
    except Exception:
        return False


# ======================================================================
class ApiFalsa:
    def __init__(self, janelas):
        self.janelas = janelas          # {hwnd: (pid, estilo, exestilo)}
        self.set_calls = []

    def janelas_do_pid(self, pid):
        return [h for h, (p, _s, _e) in self.janelas.items() if p == pid]

    def get_style(self, hwnd):
        return self.janelas[hwnd][1]

    def get_exstyle(self, hwnd):
        return self.janelas[hwnd][2]

    def set_exstyle(self, hwnd, valor):
        p, s, _ = self.janelas[hwnd]
        self.janelas[hwnd] = (p, s, valor)
        self.set_calls.append((hwnd, valor))


class JanelaTests(unittest.TestCase):
    def setUp(self):
        vis = J.WS_VISIBLE
        self.api = ApiFalsa({
            101: (500, vis | J.WS_CAPTION, 0),              # Central de Controle (tem barra de título)
            102: (500, vis, J.WS_EX_LAYERED),               # avatar (sem barra)
            103: (999, vis, 0),                             # outro programa
            104: (500, 0, 0),                               # invisível
        })

    def test_acha_a_janela_sem_barra_de_titulo(self):
        self.assertEqual(J.escolher_janela_avatar(self.api, 500), 102)
        self.assertIsNone(J.escolher_janela_avatar(self.api, 12345))

    def test_liga_e_desliga(self):
        ok, _ = J.definir_clique_atravessa(500, True, api=self.api)
        self.assertTrue(ok)
        ex = self.api.get_exstyle(102)
        self.assertTrue(ex & J.WS_EX_TRANSPARENT and ex & J.WS_EX_LAYERED)
        ok, _ = J.definir_clique_atravessa(500, False, api=self.api)
        ex = self.api.get_exstyle(102)
        self.assertTrue(ok and not (ex & J.WS_EX_TRANSPARENT))
        self.assertTrue(ex & J.WS_EX_LAYERED, "o LAYERED é do Godot (transparência por pixel): não pode sair")

    def test_nunca_mexe_na_central_nem_em_outro_programa(self):
        J.definir_clique_atravessa(500, True, api=self.api)
        self.assertEqual(self.api.get_exstyle(101), 0)
        self.assertEqual(self.api.get_exstyle(103), 0)
        self.assertEqual(self.api.get_exstyle(104), 0)

    def test_idempotente_nao_reaplica(self):
        J.definir_clique_atravessa(500, True, api=self.api)
        J.definir_clique_atravessa(500, True, api=self.api)
        self.assertEqual(len(self.api.set_calls), 1)

    def test_pid_ruim_e_janela_ausente_nao_levantam(self):
        for pid in (None, "abc", 0, -3):
            ok, msg = J.definir_clique_atravessa(pid, True, api=self.api)
            self.assertFalse(ok)
            self.assertTrue(msg)
        ok, msg = J.definir_clique_atravessa(777, True, api=self.api)
        self.assertFalse(ok)
        self.assertIn("janela", msg)

    @unittest.skipIf(sys.platform == "win32", "só vale fora do Windows")
    def test_fora_do_windows_diz_que_nao_se_aplica(self):
        ok, msg = J.definir_clique_atravessa(1234, True)
        self.assertFalse(ok)
        self.assertIn("Windows", msg)


# ======================================================================
class GestosTests(unittest.TestCase):
    def test_exemplos(self):
        casos = [
            ("Olá! Que bom te ver de novo.", "happy", "acenar"),
            ("Sim, claro, pode fazer assim.", "neutral", "concordar"),
            ("Não, isso não funciona assim.", "neutral", "negar"),
            ("Talvez dependa do caso.", "neutral", "ombros"),
            ("Parabéns! Funcionou!", "happy", "comemorar"),
            ("Desculpa, não consegui.", "sad", "negar"),
            ("Como você está?", "neutral", "inclinar"),
            ("Obrigada pela ajuda", "neutral", "reverencia"),
        ]
        for texto, expr, gesto in casos:
            with self.subTest(texto=texto):
                self.assertEqual(G.escolher_expressao(texto), expr)
                self.assertEqual(G.escolher_gesto(texto), gesto)

    def test_palavra_inteira_nao_pedaco(self):
        # o antigo casava "rs" dentro de "versão"/"porque"
        self.assertEqual(G.escolher_expressao("A versão nova saiu"), "neutral")
        self.assertIsNone(G.escolher_gesto("A versão nova saiu"))

    def test_derrota_nao_e_festa(self):
        self.assertNotEqual(G.escolher_gesto("Não funcionou, infelizmente."), "comemorar")

    def test_vazio_e_none(self):
        self.assertEqual(G.escolher_expressao(""), "neutral")
        self.assertIsNone(G.escolher_gesto(""))
        self.assertIsNone(G.escolher_gesto(None))

    def test_so_olha_o_comeco(self):
        longo = "Hoje o tempo está estável e vamos falar de física. " * 6 + "Sim, claro."
        self.assertIsNone(G.escolher_gesto(longo))

    def test_gestos_existem_no_godot(self):
        """Todo gesto que o Python pode mandar tem que existir no akira_vida.gd."""
        gd = (RAIZ / "body/zenith/akira_vida.gd").read_text(encoding="utf-8")
        bloco = re.search(r"const GESTURE_DURATIONS := \{(.*?)\}", gd, re.S).group(1)
        no_godot = set(re.findall(r'"(\w+)"\s*:', bloco))
        fonte = (RAIZ / "brain/zenith_gestos.py").read_text(encoding="utf-8")
        retornos = set(re.findall(r'return "(\w+)"', fonte)) - {"happy", "sad", "angry", "surprised", "relaxed", "neutral"}
        self.assertTrue(retornos)
        self.assertEqual(retornos - no_godot, set())


# ======================================================================
@unittest.skipUnless(_real("PIL"), "Pillow não instalado")
class FundoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _imagem(self, nome, **kw):
        from PIL import Image
        p = self.d / nome
        Image.new("RGB", (64, 48), (200, 30, 30)).save(p, **kw)
        return p

    def test_classificacao(self):
        self.assertEqual(F.classificar("a.PNG"), "imagem")
        self.assertEqual(F.classificar("a.ogv"), "ogv")
        self.assertEqual(F.classificar("a.mp4"), "video")
        self.assertEqual(F.classificar("a.tiff"), "converter_imagem")
        self.assertEqual(F.classificar("a.xyz"), "desconhecido")

    def test_imagem_nativa_passa_direto(self):
        p = self._imagem("a.png")
        r = F.preparar(p, self.d / "c")
        self.assertTrue(r["ok"])
        self.assertEqual((r["tipo"], r["path"]), ("imagem", str(p)))

    def test_tiff_vira_png(self):
        p = self._imagem("a.tiff")
        r = F.preparar(p, self.d / "c")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["tipo"], "imagem")
        self.assertTrue(r["path"].endswith(".png") and Path(r["path"]).is_file())

    def test_ico_vira_png(self):
        from PIL import Image
        p = self.d / "i.ico"
        Image.new("RGB", (32, 32), (10, 200, 10)).save(p)
        r = F.preparar(p, self.d / "c")
        self.assertTrue(r["ok"] and r["tipo"] == "imagem", r)

    def test_gif_animado_vira_quadros(self):
        from PIL import Image
        quadros = [Image.new("RGB", (40, 30), (i * 40, 255 - i * 40, 90)) for i in range(6)]
        p = self.d / "a.gif"
        quadros[0].save(p, save_all=True, append_images=quadros[1:], duration=100, loop=0)
        r = F.preparar(p, self.d / "c")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["tipo"], "quadros")
        self.assertEqual(r["n"], 6)
        self.assertAlmostEqual(r["fps"], 10.0, delta=0.5)
        self.assertEqual(len(list(Path(r["dir"]).glob("f*.jpg"))), 6)

    def test_gif_de_um_quadro_vira_imagem(self):
        from PIL import Image
        p = self.d / "u.gif"
        Image.new("P", (20, 20), 3).save(p)
        r = F.preparar(p, self.d / "c")
        self.assertTrue(r["ok"] and r["tipo"] == "imagem", r)

    @unittest.skipUnless(_real("cv2") and _real("numpy"), "OpenCV/numpy não instalados")
    def test_video_vira_quadros_e_usa_cache(self):
        import cv2
        import numpy as np
        p = self.d / "v.mp4"
        w = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 30, (320, 180))
        if not w.isOpened():
            self.skipTest("este OpenCV não escreve mp4v")
        for i in range(90):
            w.write(np.full((180, 320, 3), (i * 2) % 255, np.uint8))
        w.release()
        r = F.preparar(p, self.d / "c")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["tipo"], "quadros")
        self.assertAlmostEqual(r["fps"], 15.0, delta=0.5)
        self.assertEqual(r["n"], 45)
        r2 = F.preparar(p, self.d / "c")
        self.assertIn("cache", r2["msg"])
        self.assertEqual(r2["dir"], r["dir"])

    def test_video_longo_e_limitado(self):
        self.assertEqual(F.MAX_QUADROS, int(F.MAX_SEGUNDOS * F.FPS_SAIDA))
        self.assertLessEqual(F.MAX_LARGURA_VIDEO, 1280)

    def test_arquivo_ruim_e_ausente(self):
        lixo = self.d / "x.xyz"
        lixo.write_text("isto não é mídia")
        r = F.preparar(lixo, self.d / "c")
        self.assertFalse(r["ok"])
        self.assertTrue(r["msg"])
        r = F.preparar(self.d / "naoexiste.mp4", self.d / "c")
        self.assertFalse(r["ok"])
        self.assertTrue(F.preparar("", self.d / "c")["ok"])        # vazio = "sem fundo"

    def test_original_nunca_e_alterado(self):
        p = self._imagem("o.tiff")
        antes = p.read_bytes()
        F.preparar(p, self.d / "c")
        self.assertEqual(p.read_bytes(), antes)

    def test_validador_aceita_qualquer_midia_e_continua_barrando_executavel(self):
        from brain.zenith_validator import validate_path
        for nome in ("a.mp4", "a.mkv", "a.tiff", "a.heic", "a.png", "a.ogv"):
            self.assertTrue(validate_path("C:/x/" + nome, "image")[0], nome)
        for nome in ("a.exe", "a.bat", "a.png.exe", "a.ps1"):
            self.assertFalse(validate_path("C:/x/" + nome, "image")[0], nome)
        self.assertFalse(validate_path("C:/x/../y.png", "image")[0])
        self.assertFalse(validate_path("C:/x/a.png", "vrm")[0])            # os outros tipos seguem restritos
        self.assertFalse(validate_path("C:/x/a.pth", "rvc_index")[0])


# ======================================================================
class ResetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.b = Path(self._tmp.name)
        (self.b / "config").mkdir()
        (self.b / "memory_db").mkdir()
        (self.b / "memory_db" / "x.bin").write_bytes(b"1")
        (self.b / "temp").mkdir()
        (self.b / "temp" / "fundo").mkdir()
        (self.b / "creations").mkdir()
        (self.b / "creations" / "a.txt").write_text("a")
        for nome in ("conversations.json", "zenith_notas.jsonl", "zenith_acoes_log.jsonl", "zenith_lembretes.json"):
            (self.b / "config" / nome).write_text("{}")
        (self.b / "config" / "settings.json").write_text(json.dumps({
            "gemini_key": "SEGREDO", "user_name": "Anderson", "persona_name": "Outra", "onboarding_done": True,
            "ai_endpoints": [{"id": "1"}], "rvc_python_exe": "C:/py/python.exe", "tts_volume": 0.3,
            "vrm_model_path": "res://addons/avatars/Cypher.vrm"}))
        (self.b / "body").mkdir()
        (self.b / "body" / "Cypher.vrm").write_bytes(b"v")

    def tearDown(self):
        self._tmp.cleanup()

    def test_confirmacao_errada_nao_agenda(self):
        for ruim in ("", "sim", "reset", None, "RESETAR TUDO"):
            ok, _ = R.agendar(self.b, ruim)
            self.assertFalse(ok, ruim)
        self.assertFalse(R.pendente(self.b))

    def test_confirmacao_certa_agenda_mas_nao_apaga_nada_ainda(self):
        ok, msg = R.agendar(self.b, "resetar")
        self.assertTrue(ok and R.pendente(self.b), msg)
        self.assertTrue((self.b / "memory_db" / "x.bin").exists())
        self.assertTrue((self.b / "config" / "conversations.json").exists())

    def test_cancelar(self):
        R.agendar(self.b, "RESETAR")
        self.assertTrue(R.cancelar(self.b))
        self.assertFalse(R.pendente(self.b))

    def test_sem_marcador_nao_faz_nada(self):
        r = R.aplicar_se_pendente(self.b, log=lambda *_: None)
        self.assertFalse(r["aplicado"])
        self.assertTrue((self.b / "memory_db" / "x.bin").exists())

    def test_aplica_e_limpa_so_o_pessoal(self):
        R.agendar(self.b, "RESETAR")
        r = R.aplicar_se_pendente(self.b, log=lambda *_: None)
        self.assertTrue(r["aplicado"])
        self.assertEqual(r["falhas"], [])
        self.assertFalse(R.pendente(self.b), "o marcador precisa sumir (senão reseta a cada abertura)")
        self.assertEqual(list((self.b / "memory_db").iterdir()), [])
        self.assertEqual(list((self.b / "creations").iterdir()), [])
        self.assertEqual(list((self.b / "temp").iterdir()), [])
        for nome in ("conversations.json", "zenith_notas.jsonl", "zenith_acoes_log.jsonl", "zenith_lembretes.json"):
            self.assertFalse((self.b / "config" / nome).exists(), nome)
        s = json.loads((self.b / "config" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(s["gemini_key"], "")
        self.assertEqual(s["ai_endpoints"], [])
        self.assertEqual(s["rvc_python_exe"], "")
        self.assertEqual((s["user_name"], s["persona_name"]), ("", "Zenith"))
        self.assertFalse(s["onboarding_done"])
        self.assertEqual(s["tts_volume"], 0.3, "preferência que não é pessoal fica")
        self.assertTrue((self.b / "body" / "Cypher.vrm").exists(), "avatares/programa NÃO são apagados")

    def test_segunda_abertura_nao_reseta_de_novo(self):
        R.agendar(self.b, "RESETAR")
        R.aplicar_se_pendente(self.b, log=lambda *_: None)
        (self.b / "memory_db" / "novo.bin").write_bytes(b"2")
        r = R.aplicar_se_pendente(self.b, log=lambda *_: None)
        self.assertFalse(r["aplicado"])
        self.assertTrue((self.b / "memory_db" / "novo.bin").exists())

    def test_settings_ilegivel_nao_trava(self):
        (self.b / "config" / "settings.json").write_text("{ quebrado")
        R.agendar(self.b, "RESETAR")
        r = R.aplicar_se_pendente(self.b, log=lambda *_: None)
        self.assertTrue(r["aplicado"])

    def test_lista_de_campos_bate_com_a_do_pendrive(self):
        import prepare_pendrive as prep
        self.assertEqual(set(R.CAMPOS_PESSOAIS) - set(prep._CAMPOS_PESSOAIS), set())


# ======================================================================
class RVCExternoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        fake = self.d / "fake" / "rvc_python"
        fake.mkdir(parents=True)
        (fake / "__init__.py").write_text("")
        (fake / "infer.py").write_text(
            "import shutil\n"
            "class RVCInference:\n"
            "    def __init__(self, device='cpu:0'):\n"
            "        print('lixo no stdout NAO pode quebrar o protocolo')\n"
            "    def load_model(self, m, index_path=''): pass\n"
            "    def set_params(self, **k): pass\n"
            "    def infer_file(self, a, b):\n"
            "        if 'falha' in a: raise RuntimeError('falha simulada')\n"
            "        shutil.copyfile(a, b)\n", encoding="utf-8")
        self.entrada = self.d / "a.wav"
        self.entrada.write_bytes(b"RIFF" + b"x" * 100)
        self.entrada_ruim = self.d / "falha.wav"
        self.entrada_ruim.write_bytes(b"RIFF" + b"x" * 100)
        self.r = V.RVCExterno(sys.executable, self.d / "w", pythonpath_extra=str(self.d / "fake"))

    def tearDown(self):
        self.r.parar()
        self._tmp.cleanup()

    def test_converte_e_reaproveita_o_processo(self):
        ok, msg = self.r.converter(str(self.entrada), str(self.d / "s1.wav"), "/m/model.pth")
        self.assertTrue(ok, msg)
        self.assertTrue((self.d / "s1.wav").is_file())
        pid1 = self.r._proc.pid
        ok, _ = self.r.converter(str(self.entrada), str(self.d / "s2.wav"), "/m/model.pth")
        self.assertTrue(ok)
        self.assertEqual(self.r._proc.pid, pid1, "o modelo fica carregado: não recria o processo")

    def test_falha_numa_fala_nao_derruba_o_processo(self):
        ok, msg = self.r.converter(str(self.entrada_ruim), str(self.d / "s3.wav"), "/m/model.pth")
        self.assertFalse(ok)
        self.assertIn("falha simulada", msg)
        self.assertTrue(self.r.vivo())
        ok, _ = self.r.converter(str(self.entrada), str(self.d / "s4.wav"), "/m/model.pth")
        self.assertTrue(ok)

    def test_sem_a_lib_o_erro_e_claro(self):
        r = V.RVCExterno(sys.executable, self.d / "w2")
        ok, msg = r.converter(str(self.entrada), str(self.d / "s5.wav"), "/m/model.pth")
        self.assertFalse(ok)
        self.assertIn("rvc_python", msg)
        r.parar()

    def test_python_inexistente(self):
        r = V.RVCExterno(str(self.d / "nao_existe" / "python.exe"), self.d / "w3")
        ok, msg = r.converter(str(self.entrada), str(self.d / "s6.wav"), "/m/model.pth")
        self.assertFalse(ok)
        self.assertTrue(msg)

    def test_python_valido_so_aceita_python(self):
        self.assertTrue(V.python_valido(sys.executable) or Path(sys.executable).name.lower() not in V._NOMES_PYTHON_OK)
        falso = self.d / "notepad.exe"
        falso.write_text("x")
        self.assertFalse(V.python_valido(falso))
        self.assertFalse(V.python_valido(self.d / "python.exe"))          # não existe
        self.assertFalse(V.python_valido(""))
        self.assertFalse(V.python_valido(None))

    def test_busca_do_python_do_rvc(self):
        py = self.d / "tools" / "rvc" / "venv" / "Scripts" / "python.exe"
        py.parent.mkdir(parents=True)
        py.write_text("x")
        self.assertEqual(V.achar_python_rvc(self.d), str(py))
        self.assertIsNone(V.achar_python_rvc(self.d / "outra"))
        outro = self.d / "meu" / "python.exe"
        outro.parent.mkdir()
        outro.write_text("x")
        self.assertEqual(V.achar_python_rvc(self.d / "outra", str(outro)), str(outro))

    def test_mp3_para_wav_sem_av_devolve_false(self):
        with mock.patch.dict(sys.modules, {"av": None}):
            self.assertFalse(V.mp3_para_wav(str(self.entrada), str(self.d / "z.wav")))

    def test_o_worker_embutido_compila(self):
        compile(V.WORKER_SOURCE, "rvc_worker.py", "exec")


class InteracaoRVCTests(unittest.TestCase):
    """_aplicar_rvc quando a lib NÃO está no Python do Zenith (caso do Anderson)."""

    def setUp(self):
        from brain import zenith_interaction as zi
        self.zi = zi
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.modelo = self.d / "m.pth"
        self.modelo.write_bytes(b"pth")
        self.audio = self.d / "fala.mp3"
        self.audio.write_bytes(b"mp3")

        class Cfg:
            def __init__(s, **kw):
                s.d = kw

            def get(s, k, p=None):
                v = s.d.get(k, p)
                return p if v in (None, "") else v

        self.Cfg = Cfg
        obj = object.__new__(zi.ZenithInteraction)
        obj.settings = Cfg(rvc_model_path=str(self.modelo))
        obj._rvc_engine = None
        obj._rvc_model_loaded = None
        obj._rvc_ext = None
        obj._rvc_ext_python = None
        obj.ultimo_status_rvc = ""
        self.obj = obj
        self._p = mock.patch.object(zi, "RVCInference", None)
        self._p.start()
        # _log_voz grava em config/zenith_voz_debug.log: o teste NUNCA pode escrever no config/ do projeto
        self._plog = mock.patch.object(zi, "_log_voz", lambda *a, **k: None)
        self._plog.start()

    def tearDown(self):
        self._plog.stop()
        self._p.stop()
        self._tmp.cleanup()

    def test_sem_python_3_10_cai_na_voz_base_e_explica(self):
        with mock.patch.object(self.obj, "_python_rvc", return_value=None):
            r = self.obj._aplicar_rvc(str(self.audio))
        self.assertEqual(r, str(self.audio))
        self.assertIn("3.10", self.obj.ultimo_status_rvc)
        self.assertIn("instalar_rvc", self.obj.ultimo_status_rvc)

    def test_com_python_externo_usa_o_wav_convertido(self):
        class Falso:
            def __init__(s, *a, **k):
                s.chamadas = []

            def converter(s, entrada, saida, modelo, indice="", **kw):
                s.chamadas.append((entrada, saida, modelo))
                Path(saida).write_bytes(b"RIFFok")
                return True, "ok"

            def parar(s):
                pass

        with mock.patch.object(self.obj, "_python_rvc", return_value="/x/python.exe"), \
                mock.patch.object(self.zi.rvc_externo, "RVCExterno", Falso), \
                mock.patch.object(self.zi.rvc_externo, "mp3_para_wav", return_value=True) as conv:
            r = self.obj._aplicar_rvc(str(self.audio))
        self.assertTrue(r.endswith("_rvc.wav") and Path(r).is_file())
        self.assertIn("Python 3.10", self.obj.ultimo_status_rvc)
        conv.assert_called_once()
        entrada = self.obj._rvc_ext.chamadas[0][0]
        self.assertTrue(entrada.endswith("_in.wav"), "manda o WAV (o RVC lê mp3 pelo ffmpeg)")

    def test_erro_do_rvc_nao_derruba_a_fala(self):
        class Quebra:
            def __init__(s, *a, **k):
                pass

            def converter(s, *a, **k):
                return False, "deu ruim"

            def parar(s):
                pass

        with mock.patch.object(self.obj, "_python_rvc", return_value="/x/python.exe"), \
                mock.patch.object(self.zi.rvc_externo, "RVCExterno", Quebra), \
                mock.patch.object(self.zi.rvc_externo, "mp3_para_wav", return_value=False):
            r = self.obj._aplicar_rvc(str(self.audio))
        self.assertEqual(r, str(self.audio))
        self.assertIn("deu ruim", self.obj.ultimo_status_rvc)

    def test_intensidade_padrao_e_mais_audivel(self):
        from brain.zenith_settings import DEFAULT_SETTINGS
        self.assertGreater(DEFAULT_SETTINGS["voice_expression_intensity"], 1.0)
        rate, pitch = self.zi.parametros_de_voz("happy", DEFAULT_SETTINGS["voice_expression_intensity"])
        self.assertGreater(int(rate.rstrip("%")), 8)
        self.assertEqual(self.zi.parametros_de_voz("relaxed", 1.0), ("-4%", "-2Hz"))


# ======================================================================
class FakeCfg:
    def __init__(self, **d):
        self.settings = dict(d)

    def get(self, k, p=None):
        v = self.settings.get(k, p)
        return p if v in (None, "") else v

    def update(self, m):
        self.settings.update(m)


class HandlersTests(unittest.TestCase):
    def setUp(self):
        from brain import zenith_headless as h
        self.h = h
        b = object.__new__(h.ZenithHeadlessBrain)
        b.settings = FakeCfg()
        b.core = mock.Mock()
        b.enviados = []
        b.bridge = mock.Mock()
        b.bridge.send = b.enviados.append
        self.b = b

    def test_roteador_conhece_as_acoes_novas(self):
        src = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        for acao, handler in (("set_click_through", "_handle_set_click_through"),
                              ("prepare_wallpaper", "_handle_prepare_wallpaper"),
                              ("schedule_reset", "_handle_schedule_reset"),
                              ("cancel_reset", "_handle_cancel_reset")):
            self.assertIn(f'"{acao}": self.{handler}', src)
            self.assertTrue(hasattr(self.h.ZenithHeadlessBrain, handler))

    def test_click_through_chama_a_janela_e_loga_so_na_mudanca(self):
        with mock.patch.object(self.h.janela_avatar, "definir_clique_atravessa", return_value=(True, "ok")) as f, \
                mock.patch("builtins.print") as pr:
            self.b._handle_set_click_through({"pid": 42, "active": True})
            self.b._handle_set_click_through({"pid": 42, "active": True})
            self.b._handle_set_click_through({"pid": 42, "active": False})
        self.assertEqual(f.call_count, 3)
        self.assertEqual(pr.call_count, 2, "o batimento de 3 s não pode encher o log")
        f.assert_any_call(42, False)

    def test_prepare_wallpaper_responde_com_wallpaper_ready(self):
        pronto = threading.Event()
        self.b.bridge.send = lambda m: (self.b.enviados.append(m), pronto.set())
        with mock.patch.object(self.h.fundo_chat, "preparar",
                               return_value={"ok": True, "tipo": "quadros", "dir": "/c/q", "fps": 15.0, "n": 3, "msg": ""}):
            self.b._handle_prepare_wallpaper({"path": "C:/v.mp4"})
            self.assertTrue(pronto.wait(5))
        m = self.b.enviados[-1]
        self.assertEqual((m["action"], m["tipo"], m["origem"]), ("wallpaper_ready", "quadros", "C:/v.mp4"))

    def test_prepare_wallpaper_nunca_deixa_a_excecao_escapar(self):
        pronto = threading.Event()
        self.b.bridge.send = lambda m: (self.b.enviados.append(m), pronto.set())
        with mock.patch.object(self.h.fundo_chat, "preparar", side_effect=RuntimeError("boom")):
            self.b._handle_prepare_wallpaper({"path": "C:/v.mp4"})
            self.assertTrue(pronto.wait(5))
        self.assertFalse(self.b.enviados[-1]["ok"])

    def test_reset_agendado_so_com_a_palavra(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch("brain.zenith_settings.BASE_DIR", Path(t)):
                self.b._handle_schedule_reset({"confirm": "nao"})
                self.assertFalse(self.b.enviados[-1]["ok"])
                self.assertFalse(R.pendente(t))
                self.b._handle_schedule_reset({"confirm": "RESETAR"})
                self.assertTrue(self.b.enviados[-1]["ok"] and R.pendente(t))
                self.b._handle_cancel_reset({})
                self.assertFalse(R.pendente(t))

    def test_salvar_rejeita_python_do_rvc_que_nao_e_python(self):
        self.b.settings = FakeCfg(rvc_python_exe="")
        self.b.interaction = mock.Mock()
        self.b.proactive = mock.Mock()
        with tempfile.TemporaryDirectory() as t:
            falso = Path(t) / "calc.exe"
            falso.write_text("x")
            try:
                self.b._handle_save_settings({"changes": {"rvc_python_exe": str(falso)}})
            except Exception:
                pass
        self.assertEqual(self.b.settings.settings.get("rvc_python_exe", ""), "")


# ======================================================================
class ConfigIntactoTests(unittest.TestCase):
    def test_config_so_tem_os_arquivos_do_projeto(self):
        """Rastro de teste em config/ (como um log) iria parar no zip e na cópia de distribuição."""
        permitidos = {"settings.json", "conversations.json", "provedores_catalogo.json"}
        extras = {p.name for p in (RAIZ / "config").iterdir()} - permitidos
        self.assertEqual(extras, set(), f"sobras em config/: {extras}")


class GodotContratosTests(unittest.TestCase):
    """Checagens estáticas: não substituem rodar no Godot, mas pegam o erro bobo e a quebra de
    contrato entre os arquivos .gd e o Python."""

    @classmethod
    def setUpClass(cls):
        d = RAIZ / "body" / "zenith"
        cls.vida = (d / "akira_vida.gd").read_text(encoding="utf-8")
        cls.body = (d / "akira_body.gd").read_text(encoding="utf-8")
        cls.ui = (d / "ui_manager.gd").read_text(encoding="utf-8")
        cls.con = (d / "brain_connector.gd").read_text(encoding="utf-8")

    def _balanceado(self, texto, nome):
        par = {")": "(", "]": "[", "}": "{"}
        pilha = []
        for n, linha in enumerate(texto.split("\n"), 1):
            self.assertFalse(linha.startswith(" "), f"{nome}:{n} começa com espaço")
            out, i, q = [], 0, None
            while i < len(linha):
                c = linha[i]
                if q:
                    if c == "\\":
                        i += 2
                        continue
                    if c == q:
                        q = None
                    i += 1
                    continue
                if c in "\"'":
                    q = c
                elif c == "#":
                    break
                else:
                    out.append(c)
                i += 1
            for c in out:
                if c in "([{":
                    pilha.append((c, n))
                elif c in ")]}":
                    self.assertTrue(pilha and pilha[-1][0] == par[c], f"{nome}:{n} fecha {c} sem abrir")
                    pilha.pop()
        self.assertEqual(pilha, [], f"{nome}: delimitador aberto {pilha[:2]}")

    def test_sintaxe_basica(self):
        for nome, txt in (("akira_vida.gd", self.vida), ("akira_body.gd", self.body),
                          ("ui_manager.gd", self.ui), ("brain_connector.gd", self.con)):
            self._balanceado(txt, nome)

    def test_sem_funcoes_repetidas(self):
        for nome, txt in (("akira_vida.gd", self.vida), ("akira_body.gd", self.body), ("ui_manager.gd", self.ui)):
            fs = re.findall(r"^func (\w+)", txt, re.M)
            self.assertEqual({f for f in fs if fs.count(f) > 1}, set(), nome)

    def test_akira_body_so_chama_metodos_que_a_vida_tem(self):
        definidas = set(re.findall(r"^func (\w+)", self.vida, re.M))
        membros = set(re.findall(r"^var (\w+)", self.vida, re.M))
        usadas = set(re.findall(r"\bvida\.(\w+)", self.body))
        self.assertTrue(usadas)
        self.assertEqual(usadas - definidas - membros, set())

    def test_ui_so_chama_metodos_que_o_corpo_tem(self):
        definidas = set(re.findall(r"^func (\w+)", self.body, re.M))
        usadas = set(re.findall(r"akira_body\.(?:has_method\(\"(\w+)\"\)|(\w+)\()", self.ui))
        nomes = {a or b for a, b in usadas} - {"has_method", "get"}
        for obrigatorio in ("vida_apply_config", "vida_play_gesture", "vida_report", "update_window_properties"):
            self.assertIn(obrigatorio, definidas)
        self.assertEqual({n for n in nomes if n.startswith(("vida_", "update_"))} - definidas, set())

    def test_vida_e_carregada_sem_preload(self):
        """Erro no akira_vida.gd não pode derrubar o corpo inteiro."""
        self.assertNotIn("preload(\"res://akira_vida.gd\")", self.body)
        self.assertIn("can_instantiate()", self.body)
        self.assertTrue((RAIZ / "body/zenith/akira_vida.gd").is_file())

    def test_sinais_novos_existem_no_conector_e_sao_emitidos(self):
        for sinal in ("wallpaper_ready", "reset_scheduled"):
            self.assertIn(f"signal {sinal}", self.con)
            self.assertIn(f'emit_signal("{sinal}"', self.con)
            self.assertIn(f"brain.{sinal}.connect", self.ui)

    def test_acoes_enviadas_ao_cerebro_tem_handler(self):
        py = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        enviadas = set(re.findall(r'"action":\s*"(\w+)"', self.ui + self.body))
        enviadas = {a for a in enviadas if a in {"prepare_wallpaper", "schedule_reset", "cancel_reset", "set_click_through"}}
        self.assertEqual(enviadas, {"prepare_wallpaper", "schedule_reset", "cancel_reset", "set_click_through"})
        for a in enviadas:
            self.assertIn(f'"{a}":', py)

    def test_transparencia_e_opacidade_em_grupo(self):
        """v21: o v20 trocava o shader de cada peça (virava "fantasma"). Agora é uma SubViewport."""
        self.assertIn("SubViewport.new()", self.body)
        self.assertIn("transparent_bg = true", self.body)
        self.assertNotIn("mtoon_trans", self.body)
        self.assertNotIn("set_surface_override_material", self.body)

    def test_gestos_do_godot_tem_corpo_no_codigo(self):
        bloco = re.search(r"const GESTURE_DURATIONS := \{(.*?)\}", self.vida, re.S).group(1)
        nomes = set(re.findall(r'"(\w+)"\s*:', bloco))
        self.assertGreaterEqual(len(nomes), 9)
        for n in nomes:
            self.assertIn(f'"{n}"', self.vida.split("func _gesture_alias")[1], f"alias de {n}")
        botoes = re.search(r'for gname in \[(.*?)\]', self.ui).group(1)
        self.assertEqual(set(re.findall(r'"(\w+)"', botoes)), nomes, "o botão 'Testar gesto' lista os mesmos gestos")

    def test_niveis_de_vida_consistentes(self):
        self.assertIn('["desligado", "suave", "expressivo"]', self.ui)
        from brain.zenith_settings import DEFAULT_SETTINGS
        self.assertIn(DEFAULT_SETTINGS["vida_nivel"], ("desligado", "suave", "expressivo"))
        for k in ("vida_bracos_naturais", "vida_olhar_mouse", "vida_gestos_ia", "rvc_python_exe"):
            self.assertIn(k, DEFAULT_SETTINGS)
            self.assertIn(f'"{k}"', self.ui)

    def test_cores_usadas_existem(self):
        # v25: as cores do tema são `var` (carregadas de user://zenith_tema.cfg antes de montar a interface); antes eram `const`
        consts = set(re.findall(r"^(?:const|var) (\w+)", self.ui, re.M))
        usadas = set(re.findall(r"\b(BG_[A-Z_0-9]+|CYAN\w*|MAGENTA|GREEN|RED|TEXT_[A-Z]+|BORDER|BUBBLE_\w+)\b", self.ui))
        self.assertEqual(usadas - consts, set())

    def test_campos_do_painel_de_ia_ficam_visiveis(self):
        """Regressão da captura: campo e botão com a MESMA cor do cartão ficavam invisíveis."""
        i = self.ui.index("func _ai_make_row")
        corpo = self.ui[i:i + 900]
        self.assertIn('add_theme_stylebox_override("normal", _panel_style(BG_BASE', corpo)
        self.assertNotIn("BG_SURFACE_2, BG_SURFACE_3)", self.ui[self.ui.index("func _montar_editor_de_ias"):self.ui.index("func _ai_make_row")])
        # v1.1: o editor deixou de ser aba própria (não tem mais largura mínima 640) e passou a ser
        # montado dentro da página única de Chaves — é ela quem garante o espaço.
        pagina = (RAIZ / "body/zenith/zenith_chaves_page.gd").read_text(encoding="utf-8")
        self.assertIn("ui._montar_editor_de_ias(v)", pagina)

    def test_boas_vindas_nao_encolhe(self):
        i = self.ui.index("func _build_onboarding")
        corpo = self.ui[i:i + 4500]
        self.assertIn("margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL", corpo)
        self.assertIn("_layout_onboarding_card", corpo)
        self.assertNotIn("card.anchor_left = 0.26", corpo)

    def test_a_100_por_cento_nada_muda(self):
        i = self.body.index("func _update_transparency()")
        corpo = self.body[i:i + 600]
        self.assertIn("alpha < 0.995", corpo)
        j = self.body.index("func _opacidade_desligar()")
        self.assertIn("cull_mask = _op_main_cull", self.body[j:j + 400], "a câmera principal volta a desenhar")

    def test_sem_marca_de_provedor_nos_arquivos_novos(self):
        import prepare_pendrive as prep
        for nome, txt in (("akira_vida.gd", self.vida), ("akira_body.gd", self.body), ("ui_manager.gd", self.ui)):
            baixo = txt.lower()
            for host in prep.HOSTS_DE_PROVEDOR:
                self.assertFalse(host in baixo, f"{nome}: {host}")
            for marca in ("openrouter", "groq", "aistudio", "tavily", "ollama", "lm studio"):
                self.assertFalse(marca in baixo, f"{nome}: {marca}")


# ======================================================================
@unittest.skipUnless(_real("numpy"), "numpy não instalado")
class MatematicaDosBracosTests(unittest.TestCase):
    """O braço aponta para a direção pedida com QUALQUER convenção de eixos do osso."""

    def test_400_convencoes_aleatorias(self):
        import numpy as np
        sys.path.insert(0, str(RAIZ / "tests"))
        import vida_math_sim as M
        rng = np.random.default_rng(7)
        pior = 0.0
        for trial in range(400):
            lado = rng.choice([-1.0, 1.0])
            sk = M.Skel(rng, lado)
            up = np.array([0, 1.0, 0])
            lat = np.array([lado, 0, 0.0])
            fwd = np.cross(up, lat)
            t_up = lat * 0.17 + up * -0.98 + fwd * 0.05
            t_lo = lat * 0.06 + up * -0.93 + fwd * 0.32
            M.aim(sk, 1, 2, t_up)
            M.aim(sk, 2, 3, t_lo)
            p1, _ = sk.gpose(1)
            p2, _ = sk.gpose(2)
            p3, _ = sk.gpose(3)
            d1 = (p2 - p1) / np.linalg.norm(p2 - p1)
            d2 = (p3 - p2) / np.linalg.norm(p3 - p2)
            pior = max(pior, np.linalg.norm(d1 - t_up / np.linalg.norm(t_up)),
                       np.linalg.norm(d2 - t_lo / np.linalg.norm(t_lo)))
        self.assertLess(pior, 1e-9)

    def test_suavizacao_converge_sem_passar_do_alvo(self):
        import numpy as np
        import vida_math_sim as M
        sk = M.Skel(np.random.default_rng(3), 1.0)
        alvo = np.array([0.2, -1.0, 0.1])
        alvo /= np.linalg.norm(alvo)
        erros = []
        for _ in range(60):
            M.aim(sk, 1, 2, alvo, 0.15)
            p1, _ = sk.gpose(1)
            p2, _ = sk.gpose(2)
            erros.append(np.linalg.norm((p2 - p1) / np.linalg.norm(p2 - p1) - alvo))
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(erros, erros[1:])), "erro nunca volta a crescer")
        self.assertLess(erros[-1], 1e-3)


if __name__ == "__main__":
    unittest.main()
