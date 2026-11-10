"""v1.6.1 (complemento) — o que faltava na v1.6.1 do outro Claude, achado comparando as duas versões.

  1. O Groq DESLIGOU o llama-3.3-70b-versatile em 16/08/2026: o padrão não pode mais ser ele.
  2. Chave do OpenRouter com "Credit limit" em US$ 0 (as capturas do Anderson): o erro tem que dizer isso,
     não "recusou a chave" nem "modelo pago".
  3. 403 "sem acesso ao modelo" não pode deixar a CHAVE de castigo por 24 h.
  4. OpenRouter com pouco saldo ("can only afford N"): repetir com o que cabe.
  5. A chave guardada no cartão "Llama" também vale para o OpenRouter (os dois são o mesmo serviço).

Tudo com cliente falso; nenhuma chamada real.
"""
import sys
import types
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                         # noqa: E402
_stubs.instalar()
from brain import zenith_chaves as CH            # noqa: E402
from brain import zenith_modelos as M            # noqa: E402

E_GROQ_DESLIGADO = ("Error code: 404 - {'error': {'message': 'The model `llama-3.3-70b-versatile` has been decommissioned and "
                    "is no longer supported.', 'code': 'model_decommissioned'}}")
E_LIMITE_403 = "Error code: 403 - {'error': {'message': 'Key limit exceeded (total limit)', 'code': 403}}"
E_LIMITE_402 = "Error code: 402 - {'error': {'message': 'Key limit exceeded', 'code': 402}}"
E_SALDO = ("Error code: 402 - {'error': {'message': 'This request requires more credits, or fewer max_tokens. You requested up "
           "to 8192 tokens, but can only afford 1234'}}")
E_SEM_ACESSO = ("Error code: 403 - {'error': {'message': 'Project `proj_x` does not have access to model `gpt-5.4-mini`', "
                "'code': 'model_not_found'}}")


class _Comp:
    def __init__(self, roteiro):
        self.roteiro, self.chamadas = list(roteiro), []

    def create(self, **kw):
        self.chamadas.append(dict(kw))
        item = self.roteiro.pop(0) if self.roteiro else "ok"
        if isinstance(item, str) and item.startswith("Error"):
            raise RuntimeError(item)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=item))])


def _cli(roteiro, modelos=()):
    comp = _Comp(roteiro)
    lista = [types.SimpleNamespace(id=i) for i in modelos]
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=comp),
                                 models=types.SimpleNamespace(list=lambda: lista)), comp


class _Cfg:
    def __init__(self, **d):
        self.d = d

    def get(self, k, p=None):
        v = self.d.get(k, p)
        return p if v is None else v


class GroqTests(unittest.TestCase):
    def test_padrao_nao_e_mais_o_modelo_desligado(self):
        self.assertEqual(M.padrao("groq"), "openai/gpt-oss-120b")

    def test_se_a_conta_ainda_enxerga_o_antigo_ele_so_entra_por_ultimo(self):
        ids = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
        self.assertEqual(M.escolher_modelo("groq", ids), "openai/gpt-oss-120b")
        self.assertEqual(M.escolher_modelo("groq", ["llama-3.3-70b-versatile"]), "llama-3.3-70b-versatile")

    def test_modelo_desligado_e_reconhecido_e_trocado(self):
        self.assertTrue(M.eh_erro_de_modelo(E_GROQ_DESLIGADO))
        self.assertEqual(M.escolher_modelo("groq", ["whisper-large-v3", "qwen/qwen3.6-27b"], "llama-3.3-70b-versatile"),
                         "qwen/qwen3.6-27b")


class LimiteDaChaveTests(unittest.TestCase):
    def test_limite_da_chave_tem_mensagem_propria_com_o_que_fazer(self):
        for e in (E_LIMITE_403, E_LIMITE_402):
            d = M.diagnosticar("claude", e, "openrouter/free")
            self.assertEqual(d["categoria"], "limite_chave", e)
            self.assertIn("Credit limit", d["mensagem"])
            self.assertNotIn("recusou a chave", d["mensagem"])


class CastigoDaChaveTests(unittest.TestCase):
    def test_sem_acesso_ao_modelo_nao_castiga_a_chave(self):
        self.assertEqual(CH.classificar_motivo(E_SEM_ACESSO), "modelo")

    def test_sem_saldo_e_cota_e_o_que_ja_existia_continua(self):
        self.assertEqual(CH.classificar_motivo(E_SALDO), "cota")
        self.assertEqual(CH.classificar_motivo("401 Unauthorized invalid api key"), "invalida")
        self.assertEqual(CH.classificar_motivo("429 RESOURCE_EXHAUSTED quota exceeded"), "cota")
        self.assertEqual(CH.classificar_motivo("503 overloaded"), "instavel")


class PoucoSaldoTests(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        self.core = object.__new__(ZenithCore)
        self.core.settings = _Cfg()
        self.core._custom_models = {}
        self.core._modelo_resolvido = {}

    def test_tokens_possiveis(self):
        self.assertEqual(M.tokens_possiveis(E_SALDO), 1234)
        self.assertIsNone(M.tokens_possiveis("outro erro"))

    def test_repete_uma_vez_com_o_que_cabe(self):
        cli, comp = _cli([E_SALDO, "resposta"])
        r = self.core._openai_criar("claude", cli, "pago/x", [{"role": "user", "content": "oi"}], max_saida=8192, timeout=5)
        self.assertEqual(r, "resposta")
        self.assertEqual(comp.chamadas[0]["max_tokens"], 8192)
        self.assertEqual(comp.chamadas[1]["max_tokens"], 1234)

    def test_nao_entra_em_laco(self):
        cli, comp = _cli([E_SALDO] * 10)
        with self.assertRaises(RuntimeError):
            self.core._openai_criar("claude", cli, "pago/x", [{"role": "user", "content": "oi"}], max_saida=8192, timeout=5)
        self.assertLessEqual(len(comp.chamadas), 3)


class ChaveDoCartaoLlamaTests(unittest.TestCase):
    def test_chave_so_no_cartao_llama_vira_cliente_do_openrouter(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        cfg = _Cfg(chaves_extras={"claude": ["sk-or-A"], "llama": ["sk-or-B"]}, active_ai="gemini")
        core.reload_api_keys(cfg)
        chaves = [e["chave"] for e in core._clientes_por_chave.get("claude", [])]
        self.assertEqual(chaves, ["sk-or-A", "sk-or-B"])
        self.assertIs(core._clientes_por_chave["llama"], core._clientes_por_chave["claude"])


if __name__ == "__main__":
    unittest.main()
