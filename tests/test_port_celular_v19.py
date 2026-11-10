"""v1.19 (port celular): vídeo, anexos, fundo, desempenho, IA local e diagnóstico no CELULAR — com plataforma FALSA.

Nada aqui prova que o Android faz o que o Cérebro pede: isso só um aparelho real prova. O que estes testes travam é o lado
Python: que no celular o Cérebro PEDE ao Android (em vez de usar OpenCV, psutil, pygame...), que sem a capacidade ele diz uma frase
clara e que no PC nada muda.

    python -m unittest tests.test_port_celular_v19
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from brain import (zenith_anexos, zenith_desempenho, zenith_diag, zenith_fundo, zenith_ia_local,
                   zenith_plataforma)
from brain.zenith_plataforma import Indisponivel, Plataforma
from brain.zenith_plataforma_android import AndroidPlataforma


class PlatFalsa(Plataforma):
    """Um 'Android' de mentira: devolve o que o teste mandar e anota o que foi pedido."""
    nome = "falsa"

    def __init__(self, caps=(), medida=None, endereco=None, quadros=3, falha_video=None):
        self.capacidades = frozenset({"sistema", *caps})
        self._medida = medida or {}
        self._endereco = endereco
        self._quadros = quadros
        self._falha_video = falha_video
        self.pedidos = []

    def medir(self):
        return dict(self._medida)

    def video_info(self, caminho):
        self.pedidos.append(("info", caminho))
        return {"duracao_s": 10.0, "largura": 1280, "altura": 720, "fps": 30.0}

    def video_quadros(self, caminho, pasta, inicio_s=0.0, fps=15.0, max_quadros=180, max_largura=854, qualidade=80,
                      tempo_limite_s=90.0):
        self.pedidos.append(("quadros", caminho, inicio_s, max_quadros))
        if self._falha_video:
            raise Indisponivel(self._falha_video)
        for i in range(1, self._quadros + 1):
            Path(pasta, f"f{i:04d}.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
        return {"n": self._quadros, "fps": 15.0}

    def endereco_llm_local(self):
        return self._endereco


def _como(teste, sistema, plat=None):
    p = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": sistema})
    p.start()
    teste.addCleanup(p.stop)
    teste.addCleanup(zenith_plataforma.definir, None)
    zenith_plataforma.definir(plat)


# ============================================================================== a ponte "vídeo"
class PonteDeVideo(unittest.TestCase):
    def test_o_pc_nao_anuncia_video_e_a_base_recusa_com_frase(self):
        from brain.zenith_plataforma_pc import PCPlataforma
        self.assertNotIn("video", PCPlataforma.capacidades)          # no PC quem lê vídeo é o OpenCV
        base = Plataforma()
        with self.assertRaises(Indisponivel):
            base.video_info("a.mp4")
        with self.assertRaises(Indisponivel):
            base.video_quadros("a.mp4", "/tmp")

    def test_android_manda_os_pedidos_certos_pela_ponte(self):
        ponte = mock.Mock()
        ponte.chamar.side_effect = lambda nome, **a: (
            ["video"] if nome == "capacidades.listar" else
            {"ok": True, "duracao_s": 5.5, "largura": 640, "altura": 360, "fps": 24} if nome == "video.info" else
            {"ok": True, "n": 7, "fps": 12.0})
        p = AndroidPlataforma(ponte)
        self.assertTrue(p.tem("video"))
        self.assertEqual(p.video_info("/sdcard/v.mp4"), {"duracao_s": 5.5, "largura": 640, "altura": 360, "fps": 24.0})
        r = p.video_quadros("/sdcard/v.mp4", "/tmp/q", inicio_s=1.0, fps=15, max_quadros=10, max_largura=480,
                            qualidade=70, tempo_limite_s=20)
        self.assertEqual(r, {"n": 7, "fps": 12.0})
        nome, args = ponte.chamar.call_args.args[0], ponte.chamar.call_args.kwargs
        self.assertEqual(nome, "video.quadros")
        for chave in ("caminho", "pasta", "inicio_s", "fps", "max_quadros", "max_largura", "qualidade", "tempo_limite_s"):
            self.assertIn(chave, args)

    def test_sem_a_capacidade_vira_indisponivel_com_frase(self):
        p = AndroidPlataforma(mock.Mock(chamar=mock.Mock(return_value=[])))
        with self.assertRaises(Indisponivel) as e:
            p.video_info("v.mp4")
        self.assertIn("vídeo", str(e.exception))


# ============================================================================== anexos
class AnexosNoCelular(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d, ignore_errors=True))
        self.video = os.path.join(self.d, "festa.mp4")
        Path(self.video).write_bytes(b"\x00\x00\x00\x18ftypmp42 fake")

    def test_sem_opencv_o_celular_pede_ao_android(self):
        plat = PlatFalsa(caps=["video"])
        _como(self, "android", plat)
        with mock.patch.object(zenith_anexos, "_info_de_video_cv2", return_value={}), \
             mock.patch.object(zenith_anexos, "_miniatura_cv2", return_value=None):
            txt, img, mime, erro = zenith_anexos.ler_anexo_geral(self.video, self.d)
        self.assertIsNone(erro)
        self.assertIn("Vídeo anexado", txt)
        self.assertIn("0:10 de duração", txt)
        self.assertIn("1280×720", txt)
        self.assertEqual(mime, "image/jpeg")
        self.assertTrue(img.startswith(b"\xff\xd8"))
        self.assertEqual([p[0] for p in plat.pedidos], ["info", "quadros"])
        self.assertEqual(plat.pedidos[1][2], 1.0)                  # o quadro vem de ~1 s, como no PC
        self.assertEqual(plat.pedidos[1][3], 1)                    # e é UM quadro só
        self.assertEqual([n for n in os.listdir(self.d) if n.startswith("_thumb_tmp")], [])    # não deixa lixo

    def test_celular_sem_video_so_descreve_o_arquivo(self):
        _como(self, "android", PlatFalsa(caps=[]))
        with mock.patch.object(zenith_anexos, "_info_de_video_cv2", return_value={}), \
             mock.patch.object(zenith_anexos, "_miniatura_cv2", return_value=None):
            txt, img, mime, erro = zenith_anexos.ler_anexo_geral(self.video, self.d)
        self.assertIsNone(erro)
        self.assertIn("Vídeo anexado", txt)
        self.assertIsNone(img)

    def test_falha_do_android_nao_derruba_o_anexo(self):
        _como(self, "android", PlatFalsa(caps=["video"], falha_video="O Android não conseguiu ler o vídeo."))
        with mock.patch.object(zenith_anexos, "_info_de_video_cv2", return_value={}), \
             mock.patch.object(zenith_anexos, "_miniatura_cv2", return_value=None):
            txt, img, mime, erro = zenith_anexos.ler_anexo_geral(self.video, self.d)
        self.assertIsNone(erro)
        self.assertIsNone(img)

    def test_no_pc_a_plataforma_nunca_e_consultada(self):
        plat = PlatFalsa(caps=["video"])
        _como(self, "windows", plat)
        with mock.patch.object(zenith_anexos, "_info_de_video_cv2", return_value={}), \
             mock.patch.object(zenith_anexos, "_miniatura_cv2", return_value=None):
            zenith_anexos.ler_anexo_geral(self.video, self.d)
        self.assertEqual(plat.pedidos, [])


# ============================================================================== fundo
class FundoNoCelular(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d, ignore_errors=True))
        self.video = os.path.join(self.d, "fundo.mp4")
        Path(self.video).write_bytes(b"fake")
        self.cache = os.path.join(self.d, "cache")
        p = mock.patch.object(zenith_fundo, "_quadros_de_video_cv2", side_effect=zenith_fundo.ErroFundo("sem OpenCV"))
        p.start()
        self.addCleanup(p.stop)

    def test_video_vira_quadros_pelo_android(self):
        plat = PlatFalsa(caps=["video"], quadros=4)
        _como(self, "android", plat)
        r = zenith_fundo.preparar(self.video, self.cache)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["tipo"], r["n"], r["fps"]), ("quadros", 4, 15.0))
        self.assertTrue((Path(r["dir"]) / "f0001.jpg").is_file())
        pedido = plat.pedidos[0]
        self.assertEqual((pedido[0], pedido[2], pedido[3]), ("quadros", 0.0, zenith_fundo.MAX_QUADROS))

    def test_erro_do_android_vira_frase(self):
        _como(self, "android", PlatFalsa(caps=["video"], falha_video="codec não suportado"))
        r = zenith_fundo.preparar(self.video, self.cache)
        self.assertFalse(r["ok"])
        self.assertIn("codec não suportado", r["msg"])
        self.assertEqual(list(Path(self.cache, "fundo").glob("*/q/f0001.jpg")), [])      # não deixa preparo pela metade

    def test_celular_sem_video_diz_o_que_fazer(self):
        _como(self, "android", PlatFalsa(caps=[]))
        r = zenith_fundo.preparar(self.video, self.cache)
        self.assertFalse(r["ok"])
        self.assertIn("Este celular", r["msg"])
        self.assertIn("imagem", r["msg"])

    def test_no_pc_a_mensagem_do_opencv_continua(self):
        plat = PlatFalsa(caps=["video"])
        _como(self, "windows", plat)
        r = zenith_fundo.preparar(self.video, self.cache)
        self.assertFalse(r["ok"])
        self.assertEqual(r["msg"], "sem OpenCV")
        self.assertEqual(plat.pedidos, [])


# ============================================================================== desempenho
MEDIDA_ANDROID = {"ram_total_gb": 6.0, "ram_livre_gb": 2.5, "bateria_pct": 41.0, "carregando": False,
                  "temperatura_c": 38.5, "nucleos": 8, "disco_livre_gb": 20.0, "cpu_pct": None, "fonte": "android"}


class DesempenhoNoCelular(unittest.TestCase):
    def test_medir_traz_bateria_e_temperatura_do_android(self):
        _como(self, "android", PlatFalsa(medida=MEDIDA_ANDROID))
        m = zenith_desempenho.medir()
        self.assertEqual((m["bateria_pct"], m["carregando"], m["temperatura_c"], m["fonte"]), (41.0, False, 38.5, "android"))
        self.assertEqual((m["ram_total_gb"], m["ram_livre_gb"]), (6.0, 2.5))

    def test_formatar_mostra_bateria_e_temperatura_e_fala_aparelho(self):
        _como(self, "android", PlatFalsa(medida=MEDIDA_ANDROID))
        txt = zenith_desempenho.formatar(zenith_desempenho.medir())
        self.assertTrue(txt.startswith("📱 Este aparelho:"))
        self.assertIn("Bateria: 41%", txt)
        self.assertIn("38.5 °C", txt)
        self.assertNotIn("psutil", txt)

    def test_carregando_aparece(self):
        _como(self, "android", PlatFalsa(medida={**MEDIDA_ANDROID, "carregando": True}))
        self.assertIn("(carregando)", zenith_desempenho.formatar(zenith_desempenho.medir()))

    def test_sem_conseguir_medir_nao_chuta_e_nao_manda_instalar_psutil(self):
        _como(self, "android", PlatFalsa(medida={}))
        with mock.patch.object(zenith_desempenho, "_memoria_windows", return_value=(None, None)), \
             mock.patch("os.sysconf", side_effect=ValueError, create=True):
            m = zenith_desempenho.medir()
        m["fonte"] = "android"                                      # como a plataforma Android marcaria
        rec = zenith_desempenho.recomendar(m)
        self.assertFalse(rec["ok"])
        self.assertNotIn("psutil", rec["motivo"])
        self.assertIn("aparelho", rec["motivo"])

    def test_recomendar_fala_aparelho_quando_nada_cabe(self):
        rec = zenith_desempenho.recomendar({"ram_livre_gb": 0.5, "ram_total_gb": 2.0, "fonte": "android", "bateria_pct": 50})
        self.assertFalse(rec["ok"])
        self.assertIn("o aparelho", rec["motivo"])

    def test_no_pc_nada_mudou(self):
        plat = PlatFalsa(medida=MEDIDA_ANDROID)
        _como(self, "windows", plat)
        psutil = mock.Mock()
        psutil.virtual_memory.return_value = mock.Mock(total=16 * 1024 ** 3, available=8 * 1024 ** 3)
        psutil.cpu_percent.return_value = 12.0
        psutil.cpu_count.return_value = 6
        m = zenith_desempenho.medir(psutil_mod=psutil)
        self.assertNotIn("bateria_pct", m)
        txt = zenith_desempenho.formatar(m)
        self.assertTrue(txt.startswith("🖥 Este PC:"))
        self.assertNotIn("Bateria", txt)
        self.assertTrue(zenith_desempenho.recomendar({"ram_livre_gb": None, "ram_total_gb": None})["motivo"]
                        .startswith("Não consegui medir a memória deste PC"))


# ============================================================================== IA local
class IaLocalNoCelular(unittest.TestCase):
    @staticmethod
    def _http(urls_que_respondem):
        def http(url, timeout=2.0, **_):
            if url in urls_que_respondem:
                return {"data": [{"id": "qwen2.5-0.5b"}]}
            raise OSError("sem resposta")
        return http

    def test_acha_o_servidor_do_proprio_app_e_normaliza_o_v1(self):
        _como(self, "android", PlatFalsa(caps=["llm_local"], endereco="http://127.0.0.1:8080/"))
        det = zenith_ia_local.detectar(None, http=self._http({"http://127.0.0.1:8080/v1/models"}))
        self.assertTrue(det["rodando"])
        self.assertEqual((det["tipo"], det["url"], det["modelos"]), ("celular", "http://127.0.0.1:8080/v1", ["qwen2.5-0.5b"]))
        self.assertEqual(zenith_ia_local.url_para_cliente(None, det), "http://127.0.0.1:8080/v1")

    def test_a_url_que_a_pessoa_escolheu_continua_na_frente(self):
        _como(self, "android", PlatFalsa(caps=["llm_local"], endereco="http://127.0.0.1:8080"))
        settings = {"ia_local_url": "http://192.168.0.9:1234/v1"}
        det = zenith_ia_local.detectar(settings, http=self._http({"http://192.168.0.9:1234/v1/models", "http://127.0.0.1:8080/v1/models"}))
        self.assertEqual(det["tipo"], "custom")

    def test_sem_a_capacidade_cai_nos_candidatos_de_sempre(self):
        _como(self, "android", PlatFalsa(caps=[], endereco="http://127.0.0.1:8080"))
        det = zenith_ia_local.detectar(None, http=self._http({"http://127.0.0.1:11434/api/tags"}))
        self.assertEqual(det["tipo"], "ollama")

    def test_endereco_vazio_ou_falha_nao_quebra(self):
        _como(self, "android", PlatFalsa(caps=["llm_local"], endereco=None))
        self.assertEqual(zenith_ia_local._endereco_do_aparelho(), "")
        det = zenith_ia_local.detectar(None, http=self._http(set()))
        self.assertFalse(det["rodando"])

    def test_no_pc_o_endereco_do_aparelho_nunca_e_consultado(self):
        plat = mock.Mock(**{"tem.return_value": True, "endereco_llm_local.return_value": "http://x"})
        _como(self, "windows", plat)
        self.assertEqual(zenith_ia_local._endereco_do_aparelho(), "")
        plat.endereco_llm_local.assert_not_called()

    def test_mensagens_do_celular_nao_mandam_instalar_ollama_no_pc(self):
        _como(self, "android", PlatFalsa(caps=[]))
        self.assertIn("neste aparelho", zenith_ia_local.msg_sem_servidor())
        self.assertNotIn("Ollama", zenith_ia_local.msg_sem_servidor())
        with mock.patch("shutil.which", return_value=None):
            self.assertIn("neste aparelho", zenith_ia_local.iniciar_servidor()["mensagem"])
        self.assertIn("seu aparelho", zenith_ia_local.status_texto(None, {"rodando": False}))

    def test_no_pc_as_mensagens_continuam_as_de_sempre(self):
        _como(self, "windows")
        self.assertIs(zenith_ia_local.msg_sem_servidor(), zenith_ia_local.MSG_SEM_SERVIDOR)
        self.assertIn("seu PC", zenith_ia_local.status_texto(None, {"rodando": False}))


# ============================================================================== diagnóstico
class DiagnosticoNoCelular(unittest.TestCase):
    CAPS = ["microfone", "audio_saida", "camera", "video"]

    def _rodar(self, plat, sistema="android"):
        _como(self, sistema, plat)
        return zenith_diag.testar_tudo({"voice_enabled": False}, base_dir=None, rede=False, pastas={})

    def test_celular_pergunta_ao_aparelho_em_vez_de_acusar_biblioteca_do_pc(self):
        r = self._rodar(PlatFalsa(caps=self.CAPS, medida=MEDIDA_ANDROID))
        nomes = [i["nome"] for i in r]
        self.assertIn("Aparelho", nomes)
        for do_pc in ("Biblioteca pygame-ce", "Biblioteca sounddevice", "Biblioteca mss", "Biblioteca plyer",
                      "Módulos nativos", "Administrador", "ffmpeg"):
            self.assertNotIn(do_pc, nomes)
        por_nome = {i["nome"]: i for i in r}
        self.assertEqual(por_nome["Microfone"]["status"], zenith_diag.OK)
        self.assertEqual(por_nome["Leitura de vídeo"]["status"], zenith_diag.OK)
        self.assertEqual(por_nome["Captura de tela"]["status"], zenith_diag.AVISO)

    def test_aviso_de_bateria_baixa_e_calor(self):
        baixa = self._rodar(PlatFalsa(medida={**MEDIDA_ANDROID, "bateria_pct": 9.0}))
        self.assertEqual({i["nome"]: i for i in baixa}["Aparelho"]["status"], zenith_diag.AVISO)
        quente = self._rodar(PlatFalsa(medida={**MEDIDA_ANDROID, "temperatura_c": 45.0}))
        self.assertEqual({i["nome"]: i for i in quente}["Aparelho"]["status"], zenith_diag.AVISO)
        ok = self._rodar(PlatFalsa(medida=MEDIDA_ANDROID))
        self.assertEqual({i["nome"]: i for i in ok}["Aparelho"]["status"], zenith_diag.OK)

    def test_no_pc_a_lista_de_sempre(self):
        r = self._rodar(PlatFalsa(caps=self.CAPS), sistema="windows")
        nomes = [i["nome"] for i in r]
        self.assertIn("Biblioteca pygame-ce", nomes)
        self.assertIn("Biblioteca mss", nomes)
        self.assertIn("Módulos nativos", nomes)
        self.assertIn("Administrador", nomes)
        self.assertNotIn("Aparelho", nomes)
        self.assertNotIn("Leitura de vídeo", nomes)


# ============================================================================== o plugin Kotlin (só o TEXTO: nada foi compilado)
RAIZ = Path(__file__).resolve().parent.parent
KT_DIR = RAIZ / "android_plugin" / "src" / "main" / "kotlin" / "com" / "zenith" / "android"
KOTLIN = KT_DIR / "ZenithAndroidPlugin.kt"
SERVICO = KT_DIR / "ZenithCapturaService.kt"
MANIFESTO = RAIZ / "android_plugin" / "src" / "main" / "AndroidManifest.xml"


def _ler(p):
    if not p.exists():
        raise unittest.SkipTest(f"{p.name} não está neste pacote")
    return p.read_text(encoding="utf-8")


class PluginVideoCameraTela(unittest.TestCase):
    """Isto NÃO prova que o Kotlin compila nem que o Android obedece. Só pega esquecimento e nome trocado."""

    def test_chaves_e_parenteses_fecham(self):
        for arq in (KOTLIN, SERVICO):
            s = _ler(arq)
            for a, b in ("{}", "()", "[]"):
                self.assertEqual(s.count(a), s.count(b), f"{arq.name}: '{a}' e '{b}' em número diferente")

    def test_anuncia_video_tela_e_so_anuncia_camera_se_o_aparelho_tem(self):
        kt = _ler(KOTLIN)
        capacidades = kt[kt.index("fun capacidades()"):kt.index("// ---------- ponto de entrada")]
        self.assertIn('"video"', capacidades)
        self.assertIn('"tela"', capacidades)
        self.assertIn("FEATURE_CAMERA_ANY", capacidades)
        self.assertNotIn('"llm_local"', capacidades)                # essa continua sem servidor nativo

    def test_as_quatro_chamadas_novas_estao_no_despacho(self):
        kt = _ler(KOTLIN)
        for chamada in ("video.info", "video.quadros", "camera.capturar", "tela.capturar"):
            self.assertIn(f'"{chamada}" ->', kt)

    def test_manifesto_declara_camera_servico_e_o_tipo_certo(self):
        mf = _ler(MANIFESTO)
        for perm in ("CAMERA", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_MEDIA_PROJECTION"):
            self.assertIn(f"android.permission.{perm}", mf)
        self.assertIn('android:name="com.zenith.android.ZenithCapturaService"', mf)
        self.assertIn('android:foregroundServiceType="mediaProjection"', mf)
        self.assertIn('android:exported="false"', mf)
        self.assertIn("class ZenithCapturaService", _ler(SERVICO))   # o nome do manifesto existe de fato

    def test_ordem_que_o_android_14_exige_na_captura_de_tela(self):
        kt, sv = _ler(KOTLIN), _ler(SERVICO)
        # 1) permissão do usuário -> 2) serviço em primeiro plano -> 3) projeção -> 4) callback ANTES da tela virtual
        self.assertLess(kt.index("createScreenCaptureIntent"), kt.index("startForegroundService"))
        self.assertLess(kt.index("startForegroundService"), kt.index("getMediaProjection"))
        self.assertLess(kt.index("registerCallback"), kt.index("createVirtualDisplay"))
        self.assertIn("FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION", sv)
        self.assertIn("override fun onMainActivityResult", kt)
        self.assertIn("override fun onMainDestroy", kt)

    def test_a_projecao_nao_se_mantem_para_sempre(self):
        kt = _ler(KOTLIN)
        self.assertIn("120_000", kt)                                 # fecha sozinha depois de 2 min sem pedido
        self.assertIn("onStop()", kt)                                # e quando a pessoa toca no ícone do sistema

    def test_a_camera_nao_fica_presa_nem_espera_para_sempre(self):
        kt = _ler(KOTLIN)
        self.assertIn("cameraOcupada", kt)
        self.assertIn("12_000", kt)                                  # desiste em 12 s
        self.assertIn("quitSafely", kt)                              # solta a linha de execução da câmera

    def test_sem_a_sintaxe_de_catch_que_o_kotlin_da_epoca_pode_recusar(self):
        for arq in (KOTLIN, SERVICO):
            self.assertNotIn("catch (_:", _ler(arq), "use um nome (ex.: `ignorado`): `_` no catch exige Kotlin novo")

    def test_o_tempo_que_o_cerebro_espera_cobre_o_que_o_plugin_demora(self):
        from brain import zenith_ponte_corpo as ponte
        self.assertGreater(ponte.TEMPOS["video.quadros"], 90.0)      # o plugin desiste em 90 s (tempo_limite_s)
        self.assertGreaterEqual(ponte.TEMPOS["tela.capturar"], 45.0)  # a pessoa lê a janela de permissão do Android
        self.assertGreater(ponte.TEMPOS["camera.capturar"], 12.0)    # o plugin da câmera desiste em 12 s


# ============================================================================== bibliotecas
class MapaDeBibliotecas(unittest.TestCase):
    DOC = RAIZ / "docs" / "BIBLIOTECAS_ANDROID.md"

    def test_toda_biblioteca_de_fora_esta_no_documento(self):
        from tests import mapa_bibliotecas as mapa
        doc = _ler(self.DOC)
        faltando = [lib for lib in sorted(mapa.usos(RAIZ)) if f"`{lib}`" not in doc]
        self.assertEqual(faltando, [], "biblioteca nova no código: acrescente em docs/BIBLIOTECAS_ANDROID.md")

    def test_as_exigidas_na_partida_sao_as_do_documento(self):
        from tests import mapa_bibliotecas as mapa
        doc = _ler(self.DOC)
        secao1 = doc.split("## 1.")[1].split("## 2.")[0]
        for lib in mapa.exigidas_na_partida(RAIZ):
            self.assertIn(f"`{lib}`", secao1, f"'{lib}' passou a ser exigida na partida: ponha na seção 1 do documento")
        for lib in ("serial", "cv2", "mss", "sounddevice", "pygame", "customtkinter", "chromadb"):
            self.assertNotIn(lib, mapa.exigidas_na_partida(RAIZ), f"'{lib}' não pode ser exigida na partida do celular")


if __name__ == "__main__":
    unittest.main()
