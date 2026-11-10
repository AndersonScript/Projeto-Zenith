"""Testes dos módulos JÁ migrados para a plataforma (visão e notificação), modo celular e modo PC.

No modo celular a ponte é falsa; no modo PC, o que importa é provar que NADA mudou.

    python -m unittest tests.test_port_celular_migracao
"""
from __future__ import annotations

import base64
import os
import unittest
from unittest import mock

from brain import zenith_notify, zenith_plataforma, zenith_vision
from brain.zenith_plataforma_android import AndroidPlataforma


class PontaFalsa:
    def __init__(self, respostas=None, capacidades=()):
        self.respostas, self.capacidades, self.chamadas = respostas or {}, list(capacidades), []

    def chamar(self, nome, **args):
        self.chamadas.append((nome, args))
        return self.capacidades if nome == "capacidades.listar" else self.respostas.get(nome, {"ok": True})

    def assinar(self, *a):
        pass

    def desassinar(self, *a):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(zenith_plataforma.definir, None)

    def ligar(self, ponte):
        zenith_plataforma.definir(AndroidPlataforma(ponte))
        return ponte


class VisaoNoCelular(Base):
    def test_tela_vem_do_android_e_ignora_janelas_do_zenith(self):
        p = self.ligar(PontaFalsa({"tela.capturar": {"ok": True, "imagem": base64.b64encode(b"JPEG!").decode()}}, ["tela"]))
        self.assertEqual(zenith_vision.ZenithVision().capture_screen(max_w=1280, jpeg=True, ocultar_area=0.25),
                         (b"JPEG!", None))
        self.assertEqual(p.chamadas[-1], ("tela.capturar", {"max_w": 1280, "jpeg": True}))

    def test_camera_vem_do_android(self):
        p = self.ligar(PontaFalsa({"camera.capturar": {"ok": True, "imagem": base64.b64encode(b"FOTO").decode()}},
                                  ["camera"]))
        self.assertEqual(zenith_vision.ZenithVision().capture_camera(warmup=3, max_w=640), (b"FOTO", None))
        self.assertEqual(p.chamadas[-1], ("camera.capturar", {"warmup": 3, "max_w": 640}))

    def test_sem_camera_no_aparelho_a_frase_e_clara_e_nada_quebra(self):
        self.ligar(PontaFalsa(capacidades=["tela"]))
        img, erro = zenith_vision.ZenithVision().capture_camera()
        self.assertIsNone(img)
        self.assertIn("tirar uma foto", erro)

    def test_permissao_negada_vira_a_frase_do_android(self):
        self.ligar(PontaFalsa({"tela.capturar": {"ok": False, "erro": "Permissão de captura de tela negada."}}, ["tela"]))
        self.assertEqual(zenith_vision.ZenithVision().capture_screen(),
                         (None, "Permissão de captura de tela negada."))


class NotificacaoNoCelular(Base):
    def test_notifica_pelo_android_e_corta_textos_longos(self):
        p = self.ligar(PontaFalsa(capacidades=["notificacao"]))
        self.assertTrue(zenith_notify.notificar("T" * 100, "m" * 500))
        nome, args = p.chamadas[-1]
        self.assertEqual(nome, "notificacao.mostrar")
        self.assertEqual((len(args["titulo"]), len(args["texto"])), (64, 240))

    def test_sem_capacidade_devolve_false_sem_levantar(self):
        self.ligar(PontaFalsa(capacidades=[]))
        self.assertFalse(zenith_notify.notificar("oi", "tchau"))


class PCNaoMudou(unittest.TestCase):
    """No PC o caminho antigo continua sendo o usado — nenhuma chamada passa pela plataforma."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "windows"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.armadilha = mock.Mock(side_effect=AssertionError("o PC não deveria passar pela plataforma Android"))
        zenith_plataforma.definir(mock.Mock(capturar_tela=self.armadilha, capturar_camera=self.armadilha,
                                            notificar=self.armadilha))
        self.addCleanup(zenith_plataforma.definir, None)

    def test_camera_sem_opencv_dá_a_mesma_mensagem_de_sempre(self):
        with mock.patch.object(zenith_vision, "cv2", None):
            self.assertEqual(zenith_vision.ZenithVision().capture_camera(),
                             (None, "Biblioteca 'opencv-python' não instalada. Rode: pip install opencv-python-headless"))

    def test_tela_sem_mss_dá_a_mesma_mensagem_de_sempre(self):
        with mock.patch.object(zenith_vision, "mss", None):
            img, erro = zenith_vision.ZenithVision().capture_screen()
        self.assertIsNone(img)
        self.assertIn("mss", erro)

    def test_notificar_sem_plyer_continua_devolvendo_false(self):
        with mock.patch.dict("sys.modules", {"plyer": None}):
            self.assertFalse(zenith_notify.notificar("a", "b"))


if __name__ == "__main__":
    unittest.main()
