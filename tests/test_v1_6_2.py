"""v1.6.2 — junção das duas v1.6.1 (a do Godot/Biblioteca + a das IAs) e o interruptor do teste real de chaves."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                         # noqa: E402
_stubs.instalar()
from brain import zenith_modelos as M            # noqa: E402


class JuncaoTests(unittest.TestCase):
    def test_o_teste_real_das_chaves_pode_ser_desligado(self):
        h = (RAIZ / "brain/zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('self.settings.get("teste_real_chaves", True) is not False', h)

    def test_groq_nao_comeca_por_modelo_desligado(self):
        self.assertEqual(M.padrao("groq"), "openai/gpt-oss-120b")
        self.assertNotEqual(M.PREFERIDOS["groq"][0], "llama-3.3-70b-versatile")

    def test_modelo_desligado_do_groq_so_entra_se_a_conta_ainda_enxergar(self):
        self.assertEqual(M.escolher_modelo("groq", ["llama-3.3-70b-versatile"], ""), "llama-3.3-70b-versatile")
        self.assertEqual(M.escolher_modelo("groq", ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"], ""), "openai/gpt-oss-120b")

    def test_painel_da_biblioteca_continua_ligado(self):
        u = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")
        for trecho in ("PROJETOS_GRUPOS", "func _linha_fonte(", "func _linha_biblia("):
            self.assertIn(trecho, u)
        for ac in ("fonte_add", "fonte_remover", "fonte_apagar_aprendido"):
            self.assertIn(f'"{ac}"', (RAIZ / "body/zenith/brain_connector.gd").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
