"""v1.7 — honestidade e visibilidade: cartão de pesquisa em modo "sempre", texto inventado depois de uma ação, bolha vazia."""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                         # noqa: E402
_stubs.instalar()
from brain.zenith_core import ZenithCore         # noqa: E402

cortar = ZenithCore._cortar_depois_da_acao


class CortarDepoisDaAcaoTests(unittest.TestCase):
    def test_texto_inventado_depois_de_rodar_codigo_some(self):
        r = ("Vou olhar os arquivos.<executar_python>print(1)</executar_python>\n\nCódigo executado.\n\n"
             "Analisando, o Claude atualizou o Gemini para a versão 2.0.")
        out = cortar(r)
        self.assertIn("Vou olhar os arquivos.", out)
        self.assertIn("<executar_python>print(1)</executar_python>", out)
        self.assertNotIn("Analisando", out)
        self.assertNotIn("Claude atualizou", out)

    def test_vale_para_pesquisa_ler_url_e_ver_tela(self):
        for tag in ("buscar_web", "ler_url", "ver_tela", "ver_camera", "executar_terminal", "buscar_imagem"):
            out = cortar(f"Já volto.<{tag}>x</{tag}> E o resultado foi ótimo, encontrei tudo!")
            self.assertNotIn("encontrei tudo", out, tag)
            self.assertIn("Já volto.", out, tag)

    def test_mantem_as_outras_etiquetas_que_vem_depois(self):
        out = cortar("Ok.<buscar_web>q</buscar_web> texto inventado <corpo>pensar</corpo> mais invenção <lembrar>fato</lembrar>")
        self.assertIn("<corpo>pensar</corpo>", out)
        self.assertIn("<lembrar>fato</lembrar>", out)
        self.assertNotIn("invenção", out)
        self.assertNotIn("inventado", out)

    def test_resposta_sem_acao_nao_muda(self):
        for r in ("Só conversa.", "Oi <corpo>acenar</corpo> tudo bem?", "Salvei. <lembrar>x</lembrar> Feito!"):
            self.assertEqual(cortar(r), r)

    def test_acao_que_nao_depende_de_resultado_nao_corta(self):
        r = '<aprender id="x" titulo="t" palavras="a">corpo</aprender> Aprendi, obrigada!'
        self.assertEqual(cortar(r), r)

    def test_so_a_primeira_acao_com_resultado_vale(self):
        out = cortar("A.<executar_python>1</executar_python> B <buscar_web>q</buscar_web> C")
        self.assertIn("<buscar_web>q</buscar_web>", out)               # a etiqueta fica (é da mesma resposta)...
        self.assertNotIn(" B ", out)                                    # ...mas o texto solto entre elas não
        self.assertNotIn(" C", out)


class CartaoDePesquisaTests(unittest.TestCase):
    def _core(self):
        c = object.__new__(ZenithCore)
        c.cartoes = []
        c.atividade_fn = c.cartoes.append
        return c

    def test_busca_em_modo_sempre_mostra_cartao_rodando_e_pronto(self):
        c = self._core()
        r = c._com_cartao("search", "preços de GPU", lambda: "resposta pronta")
        self.assertEqual(r, "resposta pronta")
        self.assertEqual([x["estado"] for x in c.cartoes], ["rodando", "ok"])
        self.assertEqual(c.cartoes[0]["tipo"], "busca")
        self.assertEqual(c.cartoes[0]["titulo"], "Pesquisando na web")
        self.assertEqual(c.cartoes[0]["id"], c.cartoes[1]["id"])        # o MESMO cartão muda de estado

    def test_busca_que_falha_vira_cartao_de_erro_e_o_erro_continua(self):
        c = self._core()
        with self.assertRaises(RuntimeError):
            c._com_cartao("search", "x", lambda: (_ for _ in ()).throw(RuntimeError("sem rede")))
        self.assertEqual(c.cartoes[-1]["estado"], "erro")
        self.assertIn("sem rede", c.cartoes[-1]["detalhe"])

    def test_resultado_de_falha_vira_cartao_de_erro(self):
        c = self._core()
        c._com_cartao("search", "x", lambda: "❌ Não consegui buscar")
        self.assertEqual(c.cartoes[-1]["estado"], "erro")

    def test_tipo_sem_cartao_so_executa(self):
        c = self._core()
        self.assertEqual(c._com_cartao("nao_existe", "x", lambda: "ok"), "ok")
        self.assertEqual(c.cartoes, [])

    def test_aprovar_acao_continua_mostrando_o_cartao(self):
        c = self._core()
        c._approve_action_impl = lambda a: "feito"
        acao = types.SimpleNamespace(kind="python", content="print(1)")
        self.assertEqual(c.approve_action(acao), "feito")
        self.assertEqual([x["estado"] for x in c.cartoes], ["rodando", "ok"])

    def test_os_tres_caminhos_do_modo_sempre_usam_o_cartao(self):
        txt = (RAIZ / "brain/zenith_core.py").read_text(encoding="utf-8")
        for kind in ("search", "image_search", "read_url"):
            self.assertIn(f'self._com_cartao("{kind}", pending.content', txt)


class BolhaVaziaTests(unittest.TestCase):
    def test_corpo_ignora_mensagem_vazia_da_ia_e_tira_a_bolha_do_streaming(self):
        u = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")
        self.assertIn('if _sem_emoji(text).strip_edges() == "":', u)
        self.assertIn('if texto_final.strip_edges() == "" and _stream_label != null', u)


if __name__ == "__main__":
    unittest.main()


class CatalogoDeIAsTests(unittest.TestCase):
    def test_atalhos_sao_https_ou_locais_e_cabem_no_limite(self):
        import json
        d = json.loads((RAIZ / "config/provedores_catalogo.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(d["atalhos"]), 12)
        for a in d["atalhos"]:
            self.assertTrue(a["url"].startswith("https://") or a["url"].startswith("http://localhost"), a)
        nomes = {a["nome"] for a in d["atalhos"]}
        self.assertTrue({"Cerebras", "Mistral", "NVIDIA NIM", "OpenRouter"} <= nomes)

    def test_nenhum_atalho_aponta_para_modelo_que_saiu_da_lista(self):
        import json
        d = json.loads((RAIZ / "config/provedores_catalogo.json").read_text(encoding="utf-8"))
        modelos = {a["nome"]: a["modelo"] for a in d["atalhos"]}
        self.assertEqual(modelos["OpenRouter"], "openrouter/free")
        self.assertNotIn("llama-3.3-70b-instruct:free", json.dumps(d))
