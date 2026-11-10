"""v1.2 — diagnóstico que pega o que realmente deu problema (voz muda, ffmpeg, .pyd barrado, áudio, administrador, disco)
e a ação `diagnostico_rodar` que alimenta a seção "Saúde do Zenith" das Configurações."""
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.test_v14 import _importar_headless_com_stubs
from brain import zenith_diag as diag


class FakeSettings(dict):
    pass


class TestFfmpeg(unittest.TestCase):
    def test_nao_achou_explica_o_pip(self):
        with mock.patch("brain.zenith_video.achar_ffmpeg", return_value=None):
            r = diag._checar_ffmpeg("x")
        self.assertEqual(r["status"], diag.AVISO)
        self.assertIn("imageio-ffmpeg", r["detalhe"])
        self.assertIn("/video", r["detalhe"])          # o aviso antigo dizia "só faz falta pra fundo" — enganava

    def test_achou_e_roda(self):
        ok = mock.Mock(returncode=0, stdout="ffmpeg version 7.0 Copyright\nmais", stderr="")
        with mock.patch("brain.zenith_video.achar_ffmpeg", return_value="/usr/bin/ffmpeg"), \
                mock.patch("subprocess.run", return_value=ok):
            r = diag._checar_ffmpeg("x")
        self.assertEqual(r["status"], diag.OK)
        self.assertIn("ffmpeg version 7.0", r["detalhe"])

    def test_achou_mas_nao_executa(self):
        with mock.patch("brain.zenith_video.achar_ffmpeg", return_value="/x/ffmpeg"), \
                mock.patch("subprocess.run", side_effect=PermissionError("[WinError 4551] bloqueado pelo Application Control")):
            r = diag._checar_ffmpeg("x")
        self.assertEqual(r["status"], diag.ERRO)
        self.assertIn("bloqueio", r["detalhe"].lower())


class TestNativos(unittest.TestCase):
    def test_modulo_bloqueado_vira_erro_com_dica(self):
        real = importlib.import_module

        def falso(nome, *a, **k):
            if nome == "_pybase64":
                raise ImportError("DLL load failed while importing _pybase64: Application Control blocked this file")
            return real(nome, *a, **k)
        spec = mock.Mock()
        with mock.patch("importlib.util.find_spec", return_value=spec), mock.patch("importlib.import_module", side_effect=falso):
            r = diag._checar_nativos()
        self.assertIsInstance(r, list)
        self.assertTrue(any(i["status"] == diag.ERRO and "BLOQUEIO" in i["detalhe"] and "_pybase64" in i["nome"] for i in r))

    def test_modulo_que_nao_existe_nao_assusta(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            r = diag._checar_nativos()
        self.assertEqual(r["status"], diag.OK)


class TestAdminEDisco(unittest.TestCase):
    def test_admin_fora_do_windows_nao_se_aplica(self):
        with mock.patch("os.name", "posix"):
            self.assertEqual(diag._checar_admin()["status"], diag.OK)

    def test_disco_pouco_espaco(self):
        with tempfile.TemporaryDirectory() as d:
            uso = types.SimpleNamespace(free=int(0.5 * 1024 ** 3))
            with mock.patch("shutil.disk_usage", return_value=uso):
                self.assertEqual(diag._checar_disco({"dados": Path(d)})["status"], diag.AVISO)
            uso = types.SimpleNamespace(free=int(0.05 * 1024 ** 3))
            with mock.patch("shutil.disk_usage", return_value=uso):
                self.assertEqual(diag._checar_disco({"dados": Path(d)})["status"], diag.ERRO)
            uso = types.SimpleNamespace(free=int(50 * 1024 ** 3))
            with mock.patch("shutil.disk_usage", return_value=uso):
                self.assertEqual(diag._checar_disco({"dados": Path(d)})["status"], diag.OK)


class TestAudioEFala(unittest.TestCase):
    def test_saida_de_audio_que_nao_abre(self):
        fake = types.ModuleType("pygame")
        fake.mixer = mock.Mock()
        fake.mixer.get_init.return_value = None
        fake.mixer.init.side_effect = RuntimeError("No available audio device")
        with mock.patch.dict(sys.modules, {"pygame": fake}), mock.patch.object(diag, "_tem_modulo", return_value=True):
            r = diag._checar_saida_audio()
        self.assertEqual(r["status"], diag.ERRO)
        self.assertIn("caixa de som", r["detalhe"])

    def test_saida_de_audio_ok_e_nao_derruba_o_mixer_ja_aberto(self):
        fake = types.ModuleType("pygame")
        fake.mixer = mock.Mock()
        fake.mixer.get_init.return_value = (44100, -16, 2)       # a voz do Zenith já abriu
        with mock.patch.dict(sys.modules, {"pygame": fake}), mock.patch.object(diag, "_tem_modulo", return_value=True):
            r = diag._checar_saida_audio()
        self.assertEqual(r["status"], diag.OK)
        fake.mixer.quit.assert_not_called()                      # não pode fechar o áudio que a Zenith está usando

    def test_explicacoes_da_falha_de_fala(self):
        self.assertIn("pip install -U edge-tts", diag._explicar_falha_fala(Exception("403, message='Invalid response status'")))
        self.assertIn("certificado", diag._explicar_falha_fala(Exception("SSL: CERTIFICATE_VERIFY_FAILED")))
        self.assertIn("internet", diag._explicar_falha_fala(Exception("Cannot connect to host speech.platform...")))
        self.assertIn("demorou", diag._explicar_falha_fala(TimeoutError()))
        NoAudioReceived = type("NoAudioReceived", (Exception,), {})
        self.assertIn("sem áudio", diag._explicar_falha_fala(NoAudioReceived("No audio was received")))

    def _edge_falso(self, salva):
        fake = types.ModuleType("edge_tts")

        class Communicate:
            def __init__(self, *a, **k):
                pass

            async def save(self, caminho):
                salva(caminho)
        fake.Communicate = Communicate
        return fake

    def test_fala_ok(self):
        def salva(caminho):
            Path(caminho).write_bytes(b"x" * 4096)
        with mock.patch.dict(sys.modules, {"edge_tts": self._edge_falso(salva)}), mock.patch.object(diag, "_tem_modulo", return_value=True):
            r = diag._checar_fala(timeout=3)
        self.assertEqual(r["status"], diag.OK)

    def test_fala_recusada_diz_o_que_fazer(self):
        def salva(caminho):
            raise Exception("403, message='Invalid response status'")
        with mock.patch.dict(sys.modules, {"edge_tts": self._edge_falso(salva)}), mock.patch.object(diag, "_tem_modulo", return_value=True):
            r = diag._checar_fala(timeout=3)
        self.assertEqual(r["status"], diag.ERRO)
        self.assertIn("edge-tts", r["detalhe"])

    def test_fala_funciona_mesmo_dentro_de_um_laco_asyncio(self):
        """O /diagnostico antigo pode ser chamado de dentro do laço da ponte; asyncio.run puro quebraria aí."""
        import asyncio

        def salva(caminho):
            Path(caminho).write_bytes(b"x" * 10)

        async def dentro():
            return diag._checar_fala(timeout=3)
        with mock.patch.dict(sys.modules, {"edge_tts": self._edge_falso(salva)}), mock.patch.object(diag, "_tem_modulo", return_value=True):
            r = asyncio.run(dentro())
        self.assertEqual(r["status"], diag.OK)


class TestTestarTudo(unittest.TestCase):
    def test_tem_as_checagens_novas_e_nao_vaza_chave(self):
        cfg = FakeSettings(voice_enabled=True, gemini_key="AIzaSyDONTLEAKTHISKEY0123456789abcdef")
        with tempfile.TemporaryDirectory() as d:
            res = diag.testar_tudo(cfg, rede=False, pastas={"dados": Path(d)})
        nomes = " | ".join(i["nome"] for i in res)
        for esperado in ("ffmpeg", "Módulos nativos", "Administrador", "Espaço em disco"):
            self.assertIn(esperado, nomes)
        self.assertNotIn("DONTLEAK", diag.formatar(res))

    def test_relatorio_reaproveita_resultados_sem_rodar_de_novo(self):
        itens = [{"nome": "Teste X", "status": "ok", "detalhe": "tudo certo"}]
        with mock.patch.object(diag, "testar_tudo", side_effect=AssertionError("não era pra rodar de novo")):
            txt = diag.relatorio(FakeSettings(), resultados=itens)
        self.assertIn("Teste X", txt)


class TestAcaoDiagnosticoRodar(unittest.TestCase):
    def test_manda_o_resultado_pra_tela(self):
        H = _importar_headless_com_stubs()
        enviados = []
        falso = types.SimpleNamespace(settings=FakeSettings(),
                                      bridge=types.SimpleNamespace(send=lambda m: enviados.append(m)))
        itens = [{"nome": "A", "status": "ok", "detalhe": ""}, {"nome": "B", "status": "aviso", "detalhe": "x"},
                 {"nome": "C", "status": "erro", "detalhe": "y"}]
        with tempfile.TemporaryDirectory() as d, mock.patch("brain.zenith_diag.testar_tudo", return_value=itens), \
                mock.patch("brain.zenith_settings.CREATION_DIR", Path(d)):
            H.ZenithHeadlessBrain._diagnostico_para_tela(falso)
            msg = enviados[-1]
            self.assertEqual(msg["action"], "diagnostico_resultado")
            self.assertEqual(msg["resumo"], {"ok": 1, "aviso": 1, "erro": 1})
            self.assertIn("relatório de diagnóstico", msg["relatorio"])
            self.assertTrue(Path(msg["arquivo"]).is_file())

    def test_se_o_diagnostico_quebrar_a_tela_ainda_recebe_resposta(self):
        H = _importar_headless_com_stubs()
        enviados = []
        falso = types.SimpleNamespace(settings=FakeSettings(), bridge=types.SimpleNamespace(send=lambda m: enviados.append(m)))
        with mock.patch("brain.zenith_diag.testar_tudo", side_effect=RuntimeError("boom")):
            H.ZenithHeadlessBrain._diagnostico_para_tela(falso)
        self.assertEqual(enviados[-1]["resumo"]["erro"], 1)
        self.assertIn("boom", enviados[-1]["itens"][0]["detalhe"])


class TestBuildExplicaFalhaDoPip(unittest.TestCase):
    """O erro real do Anderson: [WinError 5] Acesso negado num .pyd, .venv novo, Python 3.14, terminal de administrador."""
    ERRO_REAL = (r"ERROR: Could not install packages due to an OSError: [WinError 5] Acesso negado: "
                 r"'C:\Zenith\Teste\Zenith_v1.1\.venv\Lib\site-packages\PIL\_avif.cp314-win_amd64.pyd'" "\nCheck the permissions.")

    def setUp(self):
        import build_exe
        self.b = build_exe

    def test_acesso_negado_explica_antivirus_e_o_que_fazer(self):
        texto = "\n".join(self.b.explicar_falha_pip(self.ERRO_REAL, admin=True, py=(3, 14)))
        for esperado in ("antivírus", "terminal NORMAL", "Exclusões", "py -3.13 -m venv .venv", "administrador"):
            self.assertIn(esperado, texto)

    def test_fora_de_admin_nao_manda_sair_do_admin(self):
        texto = "\n".join(self.b.explicar_falha_pip(self.ERRO_REAL, admin=False, py=(3, 13)))
        self.assertNotIn("Você está num terminal de administrador", texto)

    def test_outros_motivos(self):
        f = self.b.explicar_falha_pip
        self.assertIn("Python 3.13", "\n".join(f("ERROR: No matching distribution found for pygame-ce", py=(3, 14))))
        self.assertIn("Build Tools", "\n".join(f("error: Microsoft Visual C++ 14.0 or greater is required", py=(3, 13))))
        self.assertIn("internet", "\n".join(f("Max retries exceeded with url: /simple/openai/", py=(3, 13))))

    def test_erro_desconhecido_no_python_14_sugere_3_13_e_no_12_fica_quieto(self):
        self.assertIn("3.13", "\n".join(self.b.explicar_falha_pip("algo estranho", py=(3, 14))))
        self.assertEqual(self.b.explicar_falha_pip("algo estranho", py=(3, 12)), [])

    def test_build_aborta_e_mostra_a_ajuda(self):
        import contextlib
        import io
        buf = io.StringIO()
        with mock.patch.object(self.b, "_rodar_pip_mostrando", return_value=(1, self.ERRO_REAL)), \
                mock.patch("os.path.isfile", return_value=True), contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                self.b._garantir_dependencias()
        self.assertEqual(cm.exception.code, 1)
        saida = buf.getvalue()
        self.assertIn("BUILD ABORTADO", saida)
        self.assertIn("MOTIVO PROVÁVEL", saida)

    def test_pip_ok_segue_em_frente(self):
        import contextlib
        import io
        buf = io.StringIO()
        with mock.patch.object(self.b, "_rodar_pip_mostrando", return_value=(0, "ok")), \
                mock.patch("os.path.isfile", return_value=True), contextlib.redirect_stdout(buf):
            self.b._garantir_dependencias()
        self.assertIn("Dependências OK", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
