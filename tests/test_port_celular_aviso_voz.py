"""Aviso certo no chat quando o celular não consegue escutar (v1.14).

Antes, qualquer falha da escuta mandava a mensagem do PC ("instale sounddevice/faster-whisper"), sem sentido no Android.
Agora o celular diz o motivo real: sem permissão do microfone, ou sem o modelo de fala em português.

    python -m unittest tests.test_port_celular_aviso_voz
"""
from __future__ import annotations

import os
import pathlib
import unittest
from unittest import mock

from brain import zenith_interaction, zenith_plataforma

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def interacao():
    return zenith_interaction.ZenithInteraction.__new__(zenith_interaction.ZenithInteraction)   # só os métodos de decisão


def plataforma_com(*capacidades):
    return mock.Mock(tem=lambda nome: nome in capacidades)


class MotivoDeNaoEscutar(unittest.TestCase):
    def setUp(self):
        self.addCleanup(zenith_plataforma.definir, None)

    def _celular(self, *capacidades):
        p = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"}); p.start(); self.addCleanup(p.stop)
        zenith_plataforma.definir(plataforma_com(*capacidades))

    def test_no_pc_nao_ha_frase_do_celular(self):
        p = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "windows"}); p.start(); self.addCleanup(p.stop)
        self.assertEqual(interacao().motivo_de_nao_escutar(), "")

    def test_sem_microfone_manda_permitir_nas_permissoes_do_android(self):
        self._celular("transcricao")
        with mock.patch.object(zenith_interaction, "np", object()):
            self.assertIn("permissões do Android", interacao().motivo_de_nao_escutar())

    def test_sem_modelo_de_fala_manda_baixar_na_tela_de_voz(self):
        self._celular("microfone")
        with mock.patch.object(zenith_interaction, "np", object()):
            frase = interacao().motivo_de_nao_escutar()
        self.assertIn("modelo de fala em português", frase)
        self.assertIn("Baixar modelo", frase)

    def test_com_tudo_nao_ha_motivo(self):
        self._celular("microfone", "transcricao")
        with mock.patch.object(zenith_interaction, "np", object()):
            self.assertEqual(interacao().motivo_de_nao_escutar(), "")

    def test_o_headless_usa_a_frase_do_celular_e_mantem_a_do_pc(self):
        fonte = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn("self.interaction.motivo_de_nao_escutar()", fonte)
        self.assertIn("sounddevice", fonte)          # a mensagem do PC continua lá, para o PC


if __name__ == "__main__":
    unittest.main()
