"""v1.3 — cartões de atividade no chat (o que a Zenith está fazendo, clicável)."""
import types
import unittest
from unittest import mock

from tests.test_v14 import _importar_headless_com_stubs
from brain import zenith_atividade as AT


def _core():
    _importar_headless_com_stubs()
    from brain import zenith_core
    c = zenith_core.ZenithCore.__new__(zenith_core.ZenithCore)       # sem rodar o __init__ pesado
    c.cartoes = []
    c.atividade_fn = lambda d: c.cartoes.append(d)
    c.guard = types.SimpleNamespace(check_action=lambda kind, content: None)
    c.memory = types.SimpleNamespace(save_fact=lambda f: None)
    return c


def _acao(kind, content="x", desc=""):
    return types.SimpleNamespace(kind=kind, content=content, description=desc)


class TestMontar(unittest.TestCase):
    def test_formato_e_valores_invalidos_viram_padrao(self):
        d = AT.montar("tipo_inventado", "Título", "estado_inventado", "texto")
        self.assertEqual(d["action"], "cartao_atividade")
        self.assertEqual(d["tipo"], "info")
        self.assertEqual(d["estado"], "ok")
        self.assertTrue(d["id"].startswith("a"))

    def test_mesmo_id_e_ids_novos_sao_unicos(self):
        self.assertEqual(AT.montar("codigo", "a", id="fixo")["id"], "fixo")
        self.assertNotEqual(AT.novo_id(), AT.novo_id())

    def test_chave_no_codigo_ou_no_titulo_nao_vaza(self):
        chave = "AIzaSyD" + "x" * 33
        d = AT.montar("codigo", f"usando {chave}", "ok", f"KEY = '{chave}'\nprint(KEY)")
        self.assertNotIn(chave, d["titulo"])
        self.assertNotIn(chave, d["detalhe"])

    def test_detalhe_enorme_e_cortado_com_aviso(self):
        d = AT.montar("codigo", "t", "ok", "a" * 50000)
        self.assertLess(len(d["detalhe"]), AT.MAX_DETALHE + 200)
        self.assertIn("cortado", d["detalhe"])

    def test_todo_tipo_de_acao_tem_cartao(self):
        for kind in ("python", "terminal", "search", "read_url", "image_gen", "video", "document", "organize", "program"):
            tipo, andando, pronto = AT.descrever_acao(kind)
            self.assertIn(tipo, AT.TIPOS)
            self.assertTrue(andando and pronto)
        self.assertIsNone(AT.descrever_acao("observe"))

    def test_parece_falha(self):
        self.assertTrue(AT.parece_falha("❌ não deu"))
        self.assertTrue(AT.parece_falha("  ⛔ bloqueado"))
        self.assertFalse(AT.parece_falha("Pronto, gerei a imagem"))


class TestAcaoAprovadaViraCartao(unittest.TestCase):
    def test_rodando_depois_ok_com_o_mesmo_id_e_o_resultado(self):
        c = _core()
        c._approve_action_impl = lambda a: "Saída: 42"
        r = c.approve_action(_acao("python", "print(6*7)"))
        self.assertEqual(r, "Saída: 42")                      # o retorno da ação NÃO muda
        self.assertEqual([x["estado"] for x in c.cartoes], ["rodando", "ok"])
        self.assertEqual(c.cartoes[0]["id"], c.cartoes[1]["id"])
        self.assertIn("print(6*7)", c.cartoes[0]["detalhe"])
        self.assertIn("Saída: 42", c.cartoes[1]["detalhe"])
        self.assertEqual(c.cartoes[1]["titulo"], "Código executado")

    def test_resultado_de_falha_vira_cartao_de_erro(self):
        c = _core()
        c._approve_action_impl = lambda a: "❌ o comando foi vetado"
        r = c.approve_action(_acao("terminal", "rm -rf /"))
        self.assertEqual(r, "❌ o comando foi vetado")
        self.assertEqual(c.cartoes[-1]["estado"], "erro")

    def test_excecao_vira_cartao_de_erro_e_continua_subindo(self):
        c = _core()

        def explode(a):
            raise RuntimeError("quebrou")
        c._approve_action_impl = explode
        with self.assertRaises(RuntimeError):
            c.approve_action(_acao("video", "{}"))
        self.assertEqual(c.cartoes[-1]["estado"], "erro")
        self.assertIn("quebrou", c.cartoes[-1]["detalhe"])

    def test_se_o_aviso_quebrar_a_acao_continua_funcionando(self):
        c = _core()

        def aviso_ruim(d):
            raise OSError("ponte caiu")
        c.atividade_fn = aviso_ruim
        c._approve_action_impl = lambda a: "ok mesmo assim"
        self.assertEqual(c.approve_action(_acao("search", "algo")), "ok mesmo assim")

    def test_acao_sem_cartao_passa_direto(self):
        c = _core()
        c._approve_action_impl = lambda a: "👁 Observação aprovada."
        self.assertEqual(c.approve_action(_acao("observe")), "👁 Observação aprovada.")
        self.assertEqual(c.cartoes, [])

    def test_sem_ponte_conectada_nao_faz_nada_e_nao_quebra(self):
        c = _core()
        c.atividade_fn = None
        c._approve_action_impl = lambda a: "ok"
        self.assertEqual(c.approve_action(_acao("python", "1")), "ok")


class TestMemoriaViraCartao(unittest.TestCase):
    def test_fato_salvo(self):
        c = _core()
        salvos = []
        c.memory = types.SimpleNamespace(save_fact=lambda f: salvos.append(f))
        c._guardar_fatos("Claro! <lembrar>Anderson estuda Automação Industrial</lembrar> Vamos lá.")
        self.assertEqual(salvos, ["Anderson estuda Automação Industrial"])
        self.assertEqual([x["estado"] for x in c.cartoes], ["rodando", "ok"])
        self.assertEqual(c.cartoes[0]["tipo"], "memoria")
        self.assertEqual(c.cartoes[0]["id"], c.cartoes[1]["id"])
        self.assertIn("Automação Industrial", c.cartoes[1]["detalhe"])
        self.assertEqual(c.cartoes[1]["titulo"], "Memória adicionada")

    def test_falha_ao_salvar_mostra_erro_sem_derrubar(self):
        c = _core()

        def falha(f):
            raise RuntimeError("banco travado")
        c.memory = types.SimpleNamespace(save_fact=falha)
        c._guardar_fatos("<lembrar>um fato</lembrar>")
        self.assertEqual(c.cartoes[-1]["estado"], "erro")

    def test_resposta_sem_lembrar_nao_gera_cartao(self):
        c = _core()
        c._guardar_fatos("só conversa, sem fato novo")
        self.assertEqual(c.cartoes, [])


class TestPonteDoCerebro(unittest.TestCase):
    def test_headless_liga_o_core_ao_bridge(self):
        import inspect
        H = _importar_headless_com_stubs()
        self.assertIn("self.core.atividade_fn", inspect.getsource(H.ZenithHeadlessBrain.__init__))


if __name__ == "__main__":
    unittest.main()
