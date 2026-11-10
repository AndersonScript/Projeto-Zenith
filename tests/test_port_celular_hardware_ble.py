"""Hardware (serial) no celular: porta BLE e mensagens honestas (v1.17).

No PC, `ZenithHardware` fala por cabo (pyserial). No celular não há cabo: a porta especial "BLE" manda a linha por Bluetooth LE,
pelo plugin Android (`ble.enviar`) — SÓ IDA, o plugin não lê de volta. A TFT não usa Bluetooth: imagem só passa por cabo ou Wi-Fi,
então no celular o caminho é o Wi-Fi e a mensagem diz isso (em vez de mandar instalar o pyserial).
Tudo aqui usa plataforma FALSA. Nada prova que o Bluetooth funciona num aparelho real.

    python -m unittest tests.test_port_celular_hardware_ble
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import unittest
from unittest import mock

from brain import zenith_commands, zenith_hardware, zenith_plataforma, zenith_tft

RAIZ = pathlib.Path(__file__).resolve().parent.parent
HABILIDADE = RAIZ / "skills" / "carrinho.py"


def _como(teste, sistema, plataforma=None):
    p = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": sistema})
    p.start()
    teste.addCleanup(p.stop)
    teste.addCleanup(zenith_plataforma.definir, None)
    zenith_plataforma.definir(plataforma)


class NomeDaPortaBle(unittest.TestCase):
    def test_nomes(self):
        f = zenith_hardware.nome_ble_da_porta
        self.assertEqual(f("BLE"), "Zenith_Carrinho")
        self.assertEqual(f(" ble "), "Zenith_Carrinho")
        self.assertEqual(f("BLE:Outro_Nome"), "Outro_Nome")
        self.assertIsNone(f("BLE:"))
        self.assertIsNone(f("COM3"))
        self.assertIsNone(f("/dev/ttyUSB0"))
        self.assertIsNone(f(""))

    def test_nome_padrao_e_o_mesmo_da_habilidade_do_carrinho(self):
        if not HABILIDADE.exists():
            self.skipTest("skills/carrinho.py não está neste pacote")
        spec = importlib.util.spec_from_file_location("carrinho_skill_teste2", HABILIDADE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(zenith_hardware.NOME_BLE_PADRAO, mod.NOME_BLE)


class NoCelularComBluetooth(unittest.TestCase):
    def setUp(self):
        self.plat = mock.Mock(tem=lambda n: n == "ble")
        _como(self, "android", self.plat)
        self.hw = zenith_hardware.ZenithHardware()

    def test_conectar_ble_nao_abre_cabo_e_avisa_que_so_envia(self):
        ok, msg = self.hw.connect("BLE", 9600)
        self.assertTrue(ok)
        self.assertIn("Zenith_Carrinho", msg)
        self.assertIn("só envia", msg)
        self.assertTrue(self.hw.is_connected())
        self.assertEqual(self.hw.port, "BLE")
        self.plat.ble_enviar.assert_not_called()          # a conexão só abre no primeiro comando

    def test_enviar_vai_por_bluetooth_com_quebra_de_linha(self):
        self.hw.connect("BLE")
        ok, resp = self.hw.send("F 3000 140")
        self.assertTrue(ok)
        self.assertIn("não recebe resposta", resp)
        self.plat.ble_enviar.assert_called_once_with("Zenith_Carrinho", b"F 3000 140\n")

    def test_nome_de_outro_dispositivo(self):
        self.hw.connect("BLE:Meu_Robo")
        self.hw.send("S")
        self.plat.ble_enviar.assert_called_once_with("Meu_Robo", b"S\n")

    def test_falha_do_plugin_vira_frase_e_nao_derruba(self):
        self.plat.ble_enviar.side_effect = RuntimeError("Não achei o 'Zenith_Carrinho' por Bluetooth.")
        self.hw.connect("BLE")
        ok, resp = self.hw.send("S")
        self.assertFalse(ok)
        self.assertIn("Não achei", resp)
        self.assertTrue(resp.startswith("Erro ao enviar por Bluetooth"))

    def test_desconectar_limpa(self):
        self.hw.connect("BLE")
        self.hw.disconnect()
        self.assertFalse(self.hw.is_connected())
        self.assertIsNone(self.hw.port)
        ok, resp = self.hw.send("S")
        self.assertFalse(ok)

    def test_disponivel_e_lista_a_porta_ble_mesmo_sem_pyserial(self):
        with mock.patch.object(zenith_hardware, "serial", None):
            self.assertTrue(self.hw.is_available())
            self.assertEqual(self.hw.list_ports(), ["BLE"])

    def test_trocar_de_ble_para_cabo_volta_para_o_cabo(self):
        falso = mock.MagicMock()
        falso.Serial.return_value = mock.Mock(is_open=True)
        with mock.patch.object(zenith_hardware, "serial", falso):
            self.hw.connect("BLE")
            ok, _ = self.hw.connect("COM3", 115200)
            self.assertTrue(ok)
            self.assertIsNone(self.hw.ble_nome)
            self.hw.send("PING")
        self.plat.ble_enviar.assert_not_called()          # o PING foi pelo cabo, não por Bluetooth


class NoCelularSemBluetooth(unittest.TestCase):
    def setUp(self):
        _como(self, "android", mock.Mock(tem=lambda n: False))
        self.hw = zenith_hardware.ZenithHardware()

    def test_ble_recusado_com_frase_clara(self):
        ok, msg = self.hw.connect("BLE")
        self.assertFalse(ok)
        self.assertIn("Bluetooth", msg)
        self.assertFalse(self.hw.is_connected())

    def test_cabo_no_celular_sem_pyserial_explica_o_que_usar(self):
        with mock.patch.object(zenith_hardware, "serial", None):
            ok, msg = self.hw.connect("COM3")
            self.assertFalse(ok)
            self.assertNotIn("pip install", msg)
            self.assertIn("BLE", msg)
            self.assertFalse(self.hw.is_available())


class NoPcNadaMuda(unittest.TestCase):
    def setUp(self):
        _como(self, "windows")
        self.hw = zenith_hardware.ZenithHardware()

    def test_porta_ble_no_pc_e_recusada(self):
        ok, msg = self.hw.connect("BLE")
        self.assertFalse(ok)
        self.assertIn("só existe no celular", msg)
        self.assertFalse(self.hw.is_connected())

    def test_sem_pyserial_no_pc_continua_mandando_instalar(self):
        with mock.patch.object(zenith_hardware, "serial", None):
            ok, msg = self.hw.connect("COM3")
            self.assertFalse(ok)
            self.assertIn("pip install pyserial", msg)
            self.assertFalse(self.hw.is_available())
            self.assertEqual(self.hw.list_ports(), [])

    def test_serial_de_sempre(self):
        falso = mock.MagicMock()
        conexao = mock.Mock(is_open=True)
        conexao.readline.return_value = b"OK\n"
        falso.Serial.return_value = conexao
        with mock.patch.object(zenith_hardware, "serial", falso):
            ok, _ = self.hw.connect("COM3", 9600)
            self.assertTrue(ok)
            ok, resp = self.hw.send("LIGAR_LED")
        self.assertTrue(ok)
        self.assertEqual(resp, "OK")
        conexao.write.assert_called_once_with(b"LIGAR_LED\n")


class MensagemDaTft(unittest.TestCase):
    def test_no_celular_manda_usar_wifi(self):
        _como(self, "android", mock.Mock(tem=lambda n: False))
        msg = zenith_tft.aviso_sem_pyserial()
        self.assertIn("Wi-Fi", msg)
        self.assertIn("/tft porta wifi:auto", msg)
        self.assertIn("Bluetooth não serve", msg)
        self.assertNotIn("pip install", msg)

    def test_no_pc_continua_igual(self):
        _como(self, "windows")
        self.assertEqual(zenith_tft.aviso_sem_pyserial(), "pyserial não instalado — rode: pip install pyserial")

    def test_status_no_celular_sem_pyserial_e_sem_wifi(self):
        _como(self, "android", mock.Mock(tem=lambda n: False))
        link = zenith_tft.TftLink(settings=mock.Mock(), enviar_ao_corpo=lambda *_: None)
        link._cfg = lambda chave, padrao="": padrao       # nenhuma porta configurada
        with mock.patch.object(zenith_tft, "serial", None):
            self.assertIn("Wi-Fi", link.status())
            self.assertNotIn("pip install", link.status())


class ComandoTftPortas(unittest.TestCase):
    """`/tft portas` listava portas COM e, sem pyserial, mandava instalar — no celular a resposta certa é o Wi-Fi."""

    def _sem_pyserial(self):
        p = mock.patch.dict(sys.modules, {"serial": None, "serial.tools": None})
        p.start()
        self.addCleanup(p.stop)

    def test_no_celular_manda_usar_wifi_e_nao_instalar_pyserial(self):
        _como(self, "android", mock.Mock(tem=lambda n: False))
        self._sem_pyserial()
        r = zenith_commands.tratar("/tft portas", {"settings": mock.Mock()})
        self.assertIn("/tft porta wifi:auto", r["resposta"])
        self.assertNotIn("pip install", r["resposta"])

    def test_no_pc_sem_pyserial_continua_igual(self):
        _como(self, "windows")
        self._sem_pyserial()
        r = zenith_commands.tratar("/tft portas", {"settings": mock.Mock()})
        self.assertIn("pip install pyserial", r["resposta"])


if __name__ == "__main__":
    unittest.main()
