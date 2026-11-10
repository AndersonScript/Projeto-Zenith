"""Carrinho por Bluetooth LE no celular (v1.14).

No PC o último recurso do carrinho é o cabo USB (serial). No celular não há cabo: o último recurso passa a ser o Bluetooth LE,
com os MESMOS identificadores do firmware (Nordic UART). Este teste confere a rota no Python e que o plugin Kotlin usa o
mesmo nome e os mesmos UUIDs do firmware — se um mudar e o outro não, o celular deixa de achar o carrinho.
Nada aqui prova que o Bluetooth funciona num aparelho real.

    python -m unittest tests.test_port_celular_carrinho_ble
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import unittest
from unittest import mock

from brain import zenith_plataforma

RAIZ = pathlib.Path(__file__).resolve().parent.parent
HABILIDADE = RAIZ / "skills" / "carrinho.py"
FIRMWARE = RAIZ / "firmware" / "carrinho_esp32s3" / "carrinho_esp32s3.ino"
KOTLIN = RAIZ / "android_plugin" / "src" / "main" / "kotlin" / "com" / "zenith" / "android" / "ZenithAndroidPlugin.kt"


def carregar():
    if not HABILIDADE.exists():
        raise unittest.SkipTest("skills/carrinho.py não está neste pacote")
    spec = importlib.util.spec_from_file_location("carrinho_skill_teste", HABILIDADE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RotaBluetooth(unittest.TestCase):
    def setUp(self):
        self.addCleanup(zenith_plataforma.definir, None)
        self.skill = carregar()

    def _celular(self, plataforma):
        p = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"}); p.start(); self.addCleanup(p.stop)
        zenith_plataforma.definir(plataforma)

    def test_fora_do_celular_nada_muda(self):
        p = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "windows"}); p.start(); self.addCleanup(p.stop)
        self.assertIsNone(self.skill._ble_do_celular(["PING"]))

    def test_no_celular_cada_linha_vai_por_bluetooth_com_quebra_de_linha(self):
        plat = mock.Mock(tem=lambda n: n == "ble")
        self._celular(plat)
        self.assertEqual(self.skill._ble_do_celular(["F", "S"]), (True, "Bluetooth"))
        self.assertEqual([c.args for c in plat.ble_enviar.call_args_list],
                         [("Zenith_Carrinho", b"F\n"), ("Zenith_Carrinho", b"S\n")])

    def test_sem_bluetooth_no_aparelho_a_frase_e_clara(self):
        self._celular(mock.Mock(tem=lambda n: False))
        ok, msg = self.skill._ble_do_celular(["S"])
        self.assertFalse(ok)
        self.assertIn("Bluetooth", msg)

    def test_falha_do_plugin_vira_frase_e_nao_derruba(self):
        plat = mock.Mock(tem=lambda n: True)
        plat.ble_enviar.side_effect = RuntimeError("Não achei o 'Zenith_Carrinho' por Bluetooth.")
        self._celular(plat)
        ok, msg = self.skill._ble_do_celular(["S"])
        self.assertFalse(ok)
        self.assertIn("Não achei", msg)

    def test_serial_no_celular_usa_bluetooth_e_nao_pyserial(self):
        plat = mock.Mock(tem=lambda n: True)
        self._celular(plat)
        self.assertEqual(self.skill._serial({}, ["S"]), (True, "Bluetooth"))


class MesmosIdentificadoresDoFirmware(unittest.TestCase):
    def setUp(self):
        if not FIRMWARE.exists() or not KOTLIN.exists():
            self.skipTest("firmware ou plugin não estão neste pacote")
        self.ino = FIRMWARE.read_text(encoding="utf-8", errors="replace")
        self.kt = KOTLIN.read_text(encoding="utf-8")

    def _define(self, nome):
        return re.search(rf'#define\s+{nome}\s+"([^"]+)"', self.ino).group(1)

    def test_nome_do_dispositivo(self):
        self.assertEqual(carregar().NOME_BLE, self._define("NOME_BT"))

    def test_uuid_do_servico_e_da_caracteristica_de_escrita(self):
        for nome_ino, nome_kt in (("UUID_SERVICO", "UUID_SERVICO_BLE"), ("UUID_RX", "UUID_RX_BLE")):
            uuid_kt = re.search(rf'{nome_kt}\s*=\s*UUID\.fromString\("([^"]+)"\)', self.kt).group(1)
            self.assertEqual(uuid_kt.lower(), self._define(nome_ino).lower(), nome_kt)


if __name__ == "__main__":
    unittest.main()
