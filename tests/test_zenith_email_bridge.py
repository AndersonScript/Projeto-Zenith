import email
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from brain import zenith_email_bridge as bridge


class TestZenithEmailBridge(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_config = bridge.ARQUIVO_CONFIG
        bridge.ARQUIVO_CONFIG = Path(self.tmp_dir.name) / "email_ponte.json"

    def tearDown(self):
        bridge.ARQUIVO_CONFIG = self.orig_config
        self.tmp_dir.cleanup()

    def test_config_carregar_e_salvar(self):
        cfg = bridge.carregar_config()
        self.assertFalse(cfg["ativo"])
        self.assertEqual(cfg["email"], "")

        sucesso = bridge.salvar_config({"ativo": True, "email": "teste@gmail.com", "senha_app": "1234abcd"})
        self.assertTrue(sucesso)

        cfg_novo = bridge.carregar_config()
        self.assertTrue(cfg_novo["ativo"])
        self.assertEqual(cfg_novo["email"], "teste@gmail.com")
        self.assertEqual(cfg_novo["senha_app"], "1234abcd")

    def test_limpar_remetente(self):
        self.assertEqual(bridge._limpar_remetente("Anderson <anderson@gmail.com>"), "anderson@gmail.com")
        self.assertEqual(bridge._limpar_remetente("anderson@gmail.com"), "anderson@gmail.com")
        self.assertEqual(bridge._limpar_remetente("  ANDERSON@GMAIL.COM  "), "anderson@gmail.com")

    def test_decodificar_cabecalho(self):
        self.assertEqual(bridge._decodificar_cabecalho("Zenith"), "Zenith")
        self.assertEqual(bridge._decodificar_cabecalho("[Zenith-Comando] status"), "[Zenith-Comando] status")

    def test_executar_comando_status(self):
        res = bridge._executar_comando_status()
        self.assertIn("Status do Computador", res)
        self.assertIn("Zenith", res)

    def test_validar_caminho_seguro_e_prevencao_traversal(self):
        # Cria um arquivo dentro de uma pasta temporária fora das permitidas
        arquivo_fora = Path(self.tmp_dir.name) / "secreto.txt"
        arquivo_fora.write_text("segredo", encoding="utf-8")

        # Não deve permitir arquivos fora das pastas do usuário
        valido = bridge._validar_caminho_seguro(str(arquivo_fora))
        self.assertIsNone(valido)

        # Não deve permitir arquivos inexistentes
        self.assertIsNone(bridge._validar_caminho_seguro("C:/inexistente_12345_teste.xyz"))

    def test_processar_pedido_status(self):
        b = bridge.ZenithEmailBridge()
        texto, anexo = b._processar_pedido("[Zenith-Comando] status", "status")
        self.assertIn("Status do Computador", texto)
        self.assertIsNone(anexo)

    def test_processar_pedido_buscar(self):
        b = bridge.ZenithEmailBridge()
        texto, anexo = b._processar_pedido("[Zenith-Comando] buscar: arquivo_que_nao_existe_xyz_999", "")
        self.assertIn("Não encontrei", texto)
        self.assertIsNone(anexo)

    @patch("brain.zenith_email_bridge._capturar_tela_pc")
    def test_processar_pedido_print(self, mock_print):
        mock_file = Path(self.tmp_dir.name) / "fake_print.png"
        mock_file.write_bytes(b"fake image bytes")
        mock_print.return_value = mock_file

        b = bridge.ZenithEmailBridge()
        texto, anexo = b._processar_pedido("[Zenith-Comando] print", "")
        self.assertIn("captura de tela", texto)
        self.assertEqual(anexo, mock_file)

    def test_rejeicao_de_remetente_nao_autorizado(self):
        """Garante que se alguém de fora mandar um e-mail para o usuário, o PC não executa."""
        b = bridge.ZenithEmailBridge()
        cfg = {
            "email": "dono@gmail.com",
            "senha_app": "senha",
            "servidor_imap": "imap.gmail.com",
            "porta_imap": 993,
        }

        # Mock IMAP
        mock_mail = MagicMock()
        mock_mail.search.return_value = ("OK", [b"1"])

        # Monta email falso de um invasor
        msg = email.message.EmailMessage()
        msg["From"] = "hacker@malicioso.com"
        msg["To"] = "dono@gmail.com"
        msg["Subject"] = "[Zenith-Comando] bloquear"
        msg.set_content("bloquear")

        mock_mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch("imaplib.IMAP4_SSL", return_value=mock_mail):
            with patch.object(b, "enviar_resposta_email") as mock_envia:
                respostas = b.verificar_novos_emails(cfg)
                self.assertEqual(respostas, [])
                mock_envia.assert_not_called()
                # Verifica que foi marcado como visto para não repetir
                mock_mail.store.assert_called_with(b"1", "+FLAGS", "(\\Seen)")


if __name__ == "__main__":
    unittest.main()
