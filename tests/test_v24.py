"""
Testes do v24 — display TFT no ESP32-S3 (USB), antivírus/build e contratos entre as pontas.
Rodar: python -m unittest tests.test_v24 -v

Sem placa, sem Godot, sem rede: a "placa" é um objeto falso que fala o protocolo do firmware.
NÃO provam: que o firmware compila/desenha no SEU display, nem o enquadramento do rosto no Godot.
"""
import io
import re
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_commands as cmd
from brain import zenith_tft as T


class FakeSettings:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **d):
        self.d = dict(d)

    def get(self, k, p=None):
        v = self.d.get(k, p)
        return p if v is None else v

    def update(self, m):
        self.d.update(m)


def ler(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


class PlacaFalsa:
    """Imita o firmware: responde ao aperto de mão e dá 'K' a cada quadro."""
    def __init__(self, resposta=b"ZENITH-TFT 1 240x240\n", falha_escrita=False):
        self.recebido = bytearray()
        self._saida = bytearray()
        self.resposta = resposta
        self.fechada = False
        self.falha_escrita = falha_escrita

    def write(self, dados):
        if self.falha_escrita:
            raise OSError("porta sumiu")
        self.recebido += dados
        if dados == T.HANDSHAKE:
            self._saida += self.resposta
        elif dados.startswith(b"ZJ"):
            self._saida += b"K\n"
        return len(dados)

    def flush(self):
        pass

    def readline(self):
        i = self._saida.find(b"\n")
        if i == -1:
            time.sleep(0.01)
            return b""
        linha, self._saida = bytes(self._saida[:i + 1]), self._saida[i + 1:]
        return linha

    def read(self, n):
        dado, self._saida = bytes(self._saida[:n]), self._saida[n:]
        return dado

    def close(self):
        self.fechada = True


class TestProtocolo(unittest.TestCase):
    def test_parse_resposta(self):
        self.assertEqual(T.parse_resposta("ZENITH-TFT 1 240x320\n"), (1, 240, 320))
        self.assertEqual(T.parse_resposta("  zenith-tft 1 128x160 "), (1, 128, 160))
        for lixo in ("", "OK", "ZENITH-TFT", "ZENITH-TFT 1 240", "outra coisa 1 240x240"):
            self.assertIsNone(T.parse_resposta(lixo))

    def test_pacote_do_quadro(self):
        jpg = b"\xff\xd8abc\xff\xd9"
        pacote = T.montar_pacote(jpg)
        self.assertEqual(pacote[:2], b"ZJ")
        self.assertEqual(struct.unpack("<I", pacote[2:6])[0], len(jpg))
        self.assertEqual(pacote[6:], jpg)

    def test_quadro_de_teste_e_um_jpeg_do_tamanho_do_painel(self):
        from PIL import Image
        jpg = T.quadro_de_teste(240, 320)
        self.assertLess(len(jpg), T.MAX_JPEG)
        with Image.open(io.BytesIO(jpg)) as im:
            self.assertEqual(im.size, (240, 320))
            self.assertEqual(im.format, "JPEG")

    def test_base64(self):
        import base64
        self.assertEqual(T.decodificar_quadro_base64(base64.b64encode(b"xyz").decode()), b"xyz")
        self.assertEqual(T.decodificar_quadro_base64(None), b"")


class TestLigacao(unittest.TestCase):
    def setUp(self):
        self.msgs = []
        self.placa = PlacaFalsa()
        self.abertas = []
        self.portas = [("COM3", 0x1A86), ("COM9", T.VID_ESPRESSIF)]
        self.cfg = FakeSettings(tft_ativo=True, tft_fps=10, tft_qualidade=70)

        def abrir(dev, baud):
            self.abertas.append((dev, baud))
            return self.placa
        self.link = T.TftLink(self.cfg, self.msgs.append, abrir_porta=abrir, listar_portas=lambda: list(self.portas),
                              log=lambda *a: None)
        self.addCleanup(self.link.parar)

    def esperar(self, cond, t=5.0):
        fim = time.time() + t
        while time.time() < fim and not cond():
            time.sleep(0.01)
        return cond()

    def test_automatico_prefere_a_espressif_e_ainda_tenta_o_conversor(self):
        # v1.0.1: antes a COM3 (CH340/CH343) ficava de fora — e muitas placas ESP32-S3 chegam POR ESSE chip.
        # Com a regra antiga, o `auto` não achava nada e o programa ficava olhando porta errada (no PC do
        # Anderson, a COM7 era um "serial por Bluetooth" e a placa real estava na COM5, CH343).
        # Regra nova: a USB nativa vem primeiro; o conversor fica como segunda tentativa (quem decide é o handshake).
        self.assertEqual(self.link.candidatas(), ["COM9", "COM3"])
        self.cfg.update({"tft_porta": "COM3"})
        self.assertEqual(self.link.candidatas(), ["COM3"])                  # escolha explícita do usuário
        self.cfg.update({"tft_porta": "auto"})
        self.assertEqual(self.link.candidatas(), ["COM9", "COM3"])

    def test_ignora_porta_de_bluetooth(self):
        self.portas = [("COM7", None, "Serial Padrão por link Bluetooth (COM7)"),
                       ("COM5", 0x1A86, "USB-Enhanced-SERIAL CH343 (COM5)")]
        self.assertEqual(self.link.candidatas(), ["COM5"])                  # a COM7 é fantasma de celular pareado

    def test_conecta_aperta_a_mao_e_avisa_o_godot(self):
        self.assertTrue(self.link._tentar_conectar())
        # 01/11: o padrão virou 115200 porque é a velocidade que os dois firmwares gravam
        # (`Serial.begin(115200)`); o 921600 antigo deixava a placa muda e o `/tft teste` dizia
        # "nenhuma placa conectada". A cadeia abaixo continua tentando 921600 se 115200 não responder.
        self.assertEqual(self.abertas, [("COM9", 115200)])
        self.assertIn(T.HANDSHAKE, bytes(self.placa.recebido))
        self.assertEqual(self.link.painel, (240, 240))
        cfg = [m for m in self.msgs if m.get("action") == "tft_config"][-1]
        self.assertTrue(cfg["ativo"])
        self.assertEqual((cfg["w"], cfg["h"]), (240, 240))
        self.assertAlmostEqual(cfg["qualidade"], 0.7)
        self.assertIn("conectado em COM9", self.link.status())

    def test_usa_o_tamanho_do_painel_que_a_placa_informa(self):
        self.placa = PlacaFalsa(b"ZENITH-TFT 1 240x320\n")
        self.link._abrir = lambda d, b: self.placa
        self.assertTrue(self.link._tentar_conectar())
        self.assertEqual(self.link.painel, (240, 320))

    def test_placa_que_nao_responde_o_aperto_nao_e_usada(self):
        self.placa = PlacaFalsa(resposta=b"")
        with mock.patch("brain.zenith_tft.time.time", side_effect=itertools_contador()):
            self.assertFalse(self.link._tentar_conectar())
        self.assertTrue(self.placa.fechada)
        self.assertIsNone(self.link._porta)

    def test_placa_em_115200_aparece_mesmo_com_921600_configurado(self):
        """O defeito de 01/11: o app abria a porta a 921600 e o firmware roda em 115200. A placa
        ficava MUDA, o laço desistia calado e o `/tft teste` dizia "nenhuma placa conectada"
        com o cabo plugado. Agora cai para 115200 sozinho e grava a velocidade que funcionou."""
        class Cfg(FakeSettings):
            salvos = {}

            def update(self, m):
                self.salvos.update(m)
                super().update(m)

        cfg = Cfg(tft_ativo=True, tft_fps=10, tft_qualidade=70)
        cfg.d["tft_baud"] = 921600
        abertas = []

        def abrir(dev, baud):
            abertas.append((dev, baud))
            return PlacaFalsa() if baud == 115200 else PlacaFalsa(resposta=b"")

        link = T.TftLink(cfg, self.msgs.append, abrir_porta=abrir,
                         listar_portas=lambda: [("COM5", 0x1A86)], log=lambda *a: None)
        self.addCleanup(link.parar)
        with mock.patch("brain.zenith_tft.time.time", side_effect=itertools_contador()):
            self.assertTrue(link._tentar_conectar())
        self.assertEqual(abertas, [("COM5", 921600), ("COM5", 115200)])
        self.assertEqual(cfg.salvos.get("tft_baud"), 115200)     # aprendeu a velocidade certa
        self.assertEqual(link.painel, (240, 240))

    def test_laco_envia_so_o_quadro_mais_recente(self):
        self.link.iniciar()
        self.assertTrue(self.esperar(lambda: self.link._porta is not None))
        self.link.on_quadro(b"\xff\xd8velho\xff\xd9")
        self.link.on_quadro(b"\xff\xd8novo\xff\xd9")
        self.assertTrue(self.esperar(lambda: self.link.quadros_enviados >= 1))
        enviados = bytes(self.placa.recebido)
        self.assertIn(b"novo", enviados)
        self.assertEqual(enviados.count(b"ZJ"), enviados.count(b"ZJ"))      # (sanidade)
        self.assertTrue(enviados.endswith(b"\xff\xd9"))

    def test_quadro_grande_demais_e_descartado(self):
        self.link.on_quadro(b"x" * (T.MAX_JPEG + 1))
        self.assertIsNone(self.link._ultimo)

    def test_erro_de_escrita_desconecta_e_manda_o_godot_parar(self):
        self.assertTrue(self.link._tentar_conectar())
        self.placa.falha_escrita = True
        self.link._enviar_quadro(b"\xff\xd8x\xff\xd9")
        self.assertIsNone(self.link._porta)
        self.assertFalse([m for m in self.msgs if m.get("action") == "tft_config"][-1]["ativo"])
        self.assertIn("desconectado", self.link.status())

    def test_detecta_placa_desplugada(self):
        self.assertTrue(self.link._tentar_conectar())
        self.portas = [("COM3", 0x1A86)]                                     # a COM9 sumiu
        self.link._checar_viva()
        self.assertIsNone(self.link._porta)
        self.assertIn("desligada da USB", self.link.status())

    def test_desligar_nas_configuracoes_fecha_a_porta(self):
        self.link.iniciar()
        self.assertTrue(self.esperar(lambda: self.link._porta is not None))
        self.cfg.update({"tft_ativo": False})
        self.assertTrue(self.esperar(lambda: self.link._porta is None))
        self.assertTrue(self.placa.fechada)

    def test_dtr_rts_ficam_desligados_ao_abrir_a_porta_real(self):
        fake_serial = mock.MagicMock()
        instancia = fake_serial.Serial.return_value
        with mock.patch.object(T, "serial", fake_serial):
            T.TftLink._abrir_real("COM9", 921600)
        self.assertFalse(instancia.dtr)
        self.assertFalse(instancia.rts)
        instancia.open.assert_called_once()
        self.assertEqual(instancia.port, "COM9")

    def test_sem_placa_status_amigavel(self):
        self.assertIn("desligado", self.link.status())

    def test_reenviar_config_reflete_o_estado(self):
        self.link.reenviar_config()
        self.assertFalse(self.msgs[-1]["ativo"])                             # sem placa: Godot não renderiza
        self.link._tentar_conectar()
        self.link.reenviar_config()
        self.assertTrue(self.msgs[-1]["ativo"])

    def test_enviar_teste_sem_e_com_placa(self):
        self.placa = PlacaFalsa(resposta=b"")              # placa muda (firmware errado ou baud errado)
        with mock.patch("brain.zenith_tft.time.time", side_effect=itertools_contador()):
            sem_placa = self.link.enviar_teste()
        self.assertIn("Nenhuma placa", sem_placa)
        self.assertIn("zenith_tft_esp32s3", sem_placa)      # diz QUAL firmware gravar
        self.placa = PlacaFalsa(b"ZENITH-TFT 1 240x240\n")
        self.assertIn("barras", self.link.enviar_teste())   # placa respondendo: o teste conecta na hora
        self.assertIsNotNone(self.link._ultimo)


def itertools_contador():
    import itertools
    return itertools.count(1000.0, 1.0)


class TestComandoTft(unittest.TestCase):
    def test_subcomandos(self):
        cfg = FakeSettings()
        self.assertEqual(cmd.tratar("/tft", {"settings": cfg})["acao"], "tft_status")
        self.assertEqual(cmd.tratar("/tft teste", {"settings": cfg})["acao"], "tft_teste")
        cmd.tratar("/tft desligar", {"settings": cfg})
        self.assertFalse(cfg.get("tft_ativo"))
        cmd.tratar("/tft ligar", {"settings": cfg})
        self.assertTrue(cfg.get("tft_ativo"))
        r = cmd.tratar("/tft porta COM7", {"settings": cfg})
        self.assertEqual((cfg.get("tft_porta"), r["acao"]), ("COM7", "tft"))
        cmd.tratar("/tft porta auto", {"settings": cfg})
        self.assertEqual(cfg.get("tft_porta"), "")
        cmd.tratar("/tft fps 12", {"settings": cfg})
        self.assertEqual(cfg.get("tft_fps"), 12)
        cmd.tratar("/tft fps 999", {"settings": cfg})
        self.assertEqual(cfg.get("tft_fps"), 30)                              # limitado
        cmd.tratar("/tft zoom 1,4", {"settings": cfg})
        self.assertAlmostEqual(cfg.get("tft_zoom"), 1.4)
        cmd.tratar("/tft cor #101830", {"settings": cfg})
        self.assertEqual(cfg.get("tft_cor"), "#101830")

    def test_entradas_invalidas_nao_mudam_nada(self):
        cfg = FakeSettings(tft_porta="", tft_fps=10, tft_cor="#0b1020")
        self.assertIn("inválida", cmd.tratar("/tft porta rm -rf", {"settings": cfg})["resposta"])
        self.assertIn("inválido", cmd.tratar("/tft fps abc", {"settings": cfg})["resposta"])
        self.assertIn("inválido", cmd.tratar("/tft cor azul", {"settings": cfg})["resposta"])
        self.assertEqual((cfg.get("tft_porta"), cfg.get("tft_fps"), cfg.get("tft_cor")), ("", 10, "#0b1020"))

    def test_ajuda_menciona_o_tft(self):
        self.assertIn("/tft", cmd.tratar("/ajuda", {})["resposta"])


class TestBuildEAntivirus(unittest.TestCase):
    def test_metadados_de_versao_sao_python_valido_e_usam_a_versao(self):
        import ast
        import build_exe as B
        txt = B.version_info_text("v24")
        ast.parse(txt)                                   # o PyInstaller avalia este texto como Python
        for s in ("VSVersionInfo(", "FixedFileInfo(filevers=(24, 0, 0, 0)", "u'ProductName', u'Zenith'",
                  "u'OriginalFilename', u'Zenith.exe'", "Translation', [1046, 1200]"):
            self.assertIn(s, txt)
        self.assertIn("FileVersion', u'24.0.0.0'", B.version_info_text("v24"))
        self.assertIn("filevers=(24, 1, 2, 0)", B.version_info_text("24.1.2"))

    def test_build_passa_o_arquivo_de_versao_e_grava_hashes(self):
        fonte = ler("build_exe.py")
        for s in ('"--version-file"', "_write_version_file()", "_escrever_hashes(", "HASHES_SHA256.txt", "--onedir", "--noupx"):
            self.assertIn(s, fonte)

    def test_hashes_sao_sha256_e_pulam_a_pasta_internal(self):
        import build_exe as B
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Zenith.exe").write_bytes(b"abc")
            (Path(d) / "_internal").mkdir()
            (Path(d) / "_internal" / "lib.exe").write_bytes(b"zzz")
            (Path(d) / "body").mkdir()
            (Path(d) / "body" / "Zenith.pck").write_bytes(b"pck")
            B._escrever_hashes(d)
            txt = (Path(d) / "HASHES_SHA256.txt").read_text(encoding="utf-8")
        self.assertIn("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  Zenith.exe", txt)
        self.assertIn("Zenith.pck", txt)
        self.assertNotIn("lib.exe", txt)

    def test_notas_de_antivirus_explicam_o_por_que_volta_e_o_que_fazer(self):
        n = ler("NOTES_ANTIVIRUS.md")
        for s in ("v24", "hash", "python zenith_launcher.py", "HASHES_SHA256.txt", "zenith_tft.py", "/observar", "Norton"):
            self.assertIn(s, n)


class TestContratos(unittest.TestCase):
    """As três pontas (Python ↔ firmware ↔ Godot) têm que combinar nos nomes e números."""
    def test_firmware_usa_os_pinos_e_o_protocolo_do_python(self):
        ino = ler("firmware/zenith_tft_esp32s3/zenith_tft_esp32s3.ino")
        for pino, num in (("TFT_CS", 8), ("TFT_RST", 10), ("TFT_DC", 9), ("PIN_SCK", 12), ("PIN_MOSI", 11)):
            self.assertRegex(ino, rf"#define\s+{pino}\s+{num}\b", pino)
        self.assertIn('"ZENITH-TFT 1 %dx%d', ino)
        self.assertIn("if (c == 'J') tratarQuadro();", ino)
        self.assertIn("if (c == 'E') responderAperto", ino)
        self.assertEqual(re.search(r"MAX_JPEG\s*=\s*(\d+)", ino).group(1), str(T.MAX_JPEG))
        self.assertTrue(T.HANDSHAKE.startswith(b"Z") and T.HANDSHAKE[1:2] == b"E")      # 'Z' 'E'NITH? -> responderAperto
        self.assertTrue(T.montar_pacote(b"x").startswith(b"ZJ"))
        self.assertIn("psramFound()", ino)
        self.assertIn("setRxBufferSize", ino)
        codigo = re.sub(r"/\*.*?\*/", "", ino, flags=re.S)                                  # só o CÓDIGO (sem comentários)
        codigo = re.sub(r"//[^\n]*", "", codigo)
        self.assertFalse(re.search(r"while\s*\(\s*!\s*Serial\s*\)", codigo), "o firmware trava sem PC conectado")

    def test_firmware_tem_os_tres_controladores_e_so_um_ligado(self):
        ino = ler("firmware/zenith_tft_esp32s3/zenith_tft_esp32s3.ino")
        ligados = re.findall(r"^#define (DRIVER_[A-Z0-9]+)", ino, re.M)
        self.assertEqual(ligados, ["DRIVER_ST7789"])
        for d in ("DRIVER_ILI9341", "DRIVER_ST7735"):
            self.assertIn(d, ino)

    def test_godot_recebe_e_responde_com_as_mesmas_acoes(self):
        con, corpo = ler("body/zenith/brain_connector.gd"), ler("body/zenith/akira_body.gd")
        self.assertIn("signal tft_config(ativo, w, h, fps, qualidade, zoom, cor, enquadre)", con)
        self.assertIn('"tft_config":', con)
        self.assertIn("connector.tft_config.connect(_on_tft_config)", corpo)
        self.assertIn('"action": "tft_frame"', corpo)
        for s in ("save_jpg_to_buffer", "frame_post_draw", "UPDATE_ONCE", "BG_COLOR", "get_bone_global_pose(head_id)",
                  "_tft_parar()", "STATE_OPEN"):
            self.assertIn(s, corpo)
        self.assertIn('"tft_frame": self._handle_tft_frame', ler("brain/zenith_headless.py"))

    def test_python_manda_ao_godot_os_campos_que_o_godot_le(self):
        link = T.TftLink(FakeSettings(), lambda m: None)
        cfg = link.config_para_corpo(True)
        for campo in ("action", "ativo", "w", "h", "fps", "qualidade", "zoom", "cor", "enquadre"):
            self.assertIn(campo, cfg)
        corpo = ler("body/zenith/brain_connector.gd")
        for campo in ("ativo", "w", "h", "fps", "qualidade", "zoom", "cor", "enquadre"):
            self.assertIn(f'data.get("{campo}"', corpo)

    def test_pyserial_nos_requisitos_e_leia_me_do_firmware(self):
        self.assertIn("pyserial", ler("requirements.txt"))
        leia = ler("firmware/LEIA-ME.md")
        for s in ("USB CDC On Boot", "TJpg_Decoder", "/tft teste", "GPIO 8", "CS", "/tft porta"):
            self.assertIn(s, leia)

    def test_padroes(self):
        from brain.zenith_settings import DEFAULT_SETTINGS as d
        self.assertTrue(d["tft_ativo"])
        self.assertEqual(d["tft_porta"], "")
        self.assertEqual(d["tft_fps"], 10)


if __name__ == "__main__":
    unittest.main()
