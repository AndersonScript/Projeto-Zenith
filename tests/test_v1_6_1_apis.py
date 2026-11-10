"""v1.6.1 — "só o Gemini funciona": modelo certo por IA, erro explicado em português e lista de IAs sem o ⚠ falso.

Nada aqui usa rede: os clientes das IAs são falsos e imitam as mensagens de erro REAIS que apareceram nos prints do Anderson
(23/10/2026). O teste ponta a ponta contra o SDK de verdade da OpenAI foi feito à parte, com um servidor local.
"""
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                         # noqa: E402
_stubs.instalar()
from brain import zenith_modelos as M            # noqa: E402
from brain import zenith_provedores as P         # noqa: E402
from brain import zenith_gemini as G             # noqa: E402

E_MODELO_OPENAI = ("Error code: 404 - {'error': {'message': 'The model `gpt-4o-mini` does not exist or you do not have access "
                   "to it.', 'code': 'model_not_found'}}")
E_COTA_OPENAI = ("Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing "
                 "details.', 'code': 'insufficient_quota'}}")
E_PARAM = "Error code: 400 - Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."
E_POLITICA = ("Error code: 404 - {'error': {'message': 'No endpoints found matching your data policy (Free model publication). "
              "Configure: https://openrouter.ai/settings/privacy'}}")
E_SUMIU = "Error code: 404 - No endpoints found for meta-llama/llama-3.3-70b-instruct:free."
E_CREDITO_OR = "Error code: 402 - Insufficient credits. Add more using https://openrouter.ai/credits"
E_LIMITE = "Error code: 429 - Rate limit reached for model llama-3.3-70b-versatile: tokens per minute (TPM)"
E_CHAVE = "Error code: 401 - Invalid API Key"


class ModelosTests(unittest.TestCase):
    def test_padroes_sao_modelos_que_funcionam_em_conta_gratis(self):
        self.assertEqual(M.padrao("openai"), "gpt-5.4-mini")
        self.assertEqual(M.padrao("claude"), "openrouter/free")           # roteador grátis do OpenRouter
        self.assertEqual(M.padrao("llama"), "openrouter/free")
        self.assertEqual(M.padrao("groq"), "openai/gpt-oss-120b")   # llama-3.3 foi desligado em 16/08/2026
        for velho in ("anthropic/claude-3.5-sonnet", "meta-llama/llama-3.3-70b-instruct:free"):
            self.assertNotIn(velho, M.PREFERIDOS["claude"])

    def test_classificacao_dos_erros_reais(self):
        casos = [(E_MODELO_OPENAI, "modelo"), (E_COTA_OPENAI, "credito"), (E_PARAM, "parametro"), (E_POLITICA, "politica"),
                 (E_SUMIU, "modelo"), (E_CREDITO_OR, "credito"), (E_LIMITE, "limite"), (E_CHAVE, "chave"),
                 ("Connection error.", "rede"), ("algo estranho", "outro")]
        for erro, esperado in casos:
            self.assertEqual(M.classificar(erro), esperado, erro)

    def test_politica_de_dados_nao_e_erro_de_modelo(self):
        self.assertFalse(M.eh_erro_de_modelo(E_POLITICA))                # trocar de modelo não resolve: é configuração da conta
        self.assertTrue(M.eh_erro_de_modelo(E_SUMIU))

    def test_mensagens_dizem_o_que_fazer_e_sem_emoji(self):
        d = M.diagnosticar("claude", E_POLITICA)
        self.assertIn("openrouter.ai/settings/privacy", d["mensagem"])
        self.assertIn("Billing", M.diagnosticar("openai", E_COTA_OPENAI)["mensagem"])
        self.assertIn("console.groq.com", M.diagnosticar("groq", E_CHAVE)["mensagem"])
        self.assertIn(":free", M.diagnosticar("claude", E_CREDITO_OR)["mensagem"])
        for slot, erro in (("openai", E_MODELO_OPENAI), ("groq", E_LIMITE), ("claude", E_SUMIU)):
            msg = M.diagnosticar(slot, erro, "x")["mensagem"]
            self.assertTrue(msg.isascii() or all(ord(c) < 0x2190 or c in "áàâãéêíóôõúçÁÉÍÓÚÇ" for c in msg), msg)

    def test_escolher_modelo_entre_os_que_a_conta_enxerga(self):
        self.assertEqual(M.escolher_modelo("openai", ["gpt-5.5", "gpt-5.4-mini"], "gpt-4o-mini"), "gpt-5.4-mini")
        self.assertEqual(M.escolher_modelo("openai", ["gpt-5.5", "gpt-5.5-pro", "gpt-5-nano"], "gpt-4o-mini"), "gpt-5-nano")
        self.assertEqual(M.escolher_modelo("openai", ["gpt-5.5-pro"], "x"), "")                 # nada barato/seguro: não inventa
        self.assertEqual(M.escolher_modelo("claude", ["anthropic/x", "foo/bar:free", "google/gemma-4-26b-a4b-it:free"], "ruim"),
                         "google/gemma-4-26b-a4b-it:free")
        self.assertEqual(M.escolher_modelo("groq", ["llama-3.1-8b-instant", "openai/gpt-oss-120b"], "llama-3.3-70b-versatile"),
                         "openai/gpt-oss-120b")
        self.assertNotEqual(M.escolher_modelo("groq", ["llama-3.3-70b-versatile"], "llama-3.3-70b-versatile"), "llama-3.3-70b-versatile")


class _Comp:
    """chat.completions de mentira: cada regra decide o erro por (modelo, parâmetro de tokens)."""
    def __init__(self, regra):
        self.regra, self.chamadas = regra, []

    def create(self, **kw):
        self.chamadas.append(kw)
        erro = self.regra(kw)
        if erro:
            raise RuntimeError(erro)
        msg = types.SimpleNamespace(content="ok")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


def _cli(regra, modelos=()):
    comp = _Comp(regra)
    lista = [types.SimpleNamespace(id=i) for i in modelos]
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=comp),
                                 models=types.SimpleNamespace(list=lambda: lista)), comp


class _Cfg:
    def __init__(self, **d):
        self.d = d

    def get(self, k, p=None):
        v = self.d.get(k, p)
        return p if v is None else v


class CoreModelosTests(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        self.core = object.__new__(ZenithCore)
        self.core.settings = _Cfg()
        self.core._custom_models = {}
        self.core._modelo_resolvido = {}

    def criar(self, slot, cli, modelo=None):
        return self.core._openai_criar(slot, cli, modelo or self.core._modelo_do_slot(slot), [{"role": "user", "content": "oi"}],
                                       max_saida=64, timeout=5)

    def test_modelo_do_slot_usa_os_padroes_novos(self):
        self.assertEqual(self.core._modelo_do_slot("openai"), "gpt-5.4-mini")
        self.assertEqual(self.core._modelo_do_slot("claude"), "openrouter/free")
        self.assertEqual(self.core._modelo_do_slot("groq"), "openai/gpt-oss-120b")

    def test_override_do_usuario_ganha_de_tudo(self):
        self.core.settings = _Cfg(modelos_override={"openai": "gpt-5.5"})
        self.core._modelo_resolvido = {"openai": "gpt-5-mini"}
        self.assertEqual(self.core._modelo_do_slot("openai"), "gpt-5.5")

    def test_openai_oficial_usa_max_completion_tokens(self):
        cli, comp = _cli(lambda kw: None)
        self.assertEqual(self.criar("openai", cli), "ok")
        self.assertIn("max_completion_tokens", comp.chamadas[0])
        self.assertNotIn("max_tokens", comp.chamadas[0])

    def test_outras_ias_continuam_com_max_tokens(self):
        cli, comp = _cli(lambda kw: None)
        self.criar("groq", cli)
        self.assertIn("max_tokens", comp.chamadas[0])

    def test_troca_o_parametro_uma_vez_quando_o_servidor_recusa(self):
        cli, comp = _cli(lambda kw: E_PARAM if "max_tokens" in kw else None)
        self.assertEqual(self.criar("groq", cli), "ok")
        self.assertEqual(len(comp.chamadas), 2)
        self.assertIn("max_completion_tokens", comp.chamadas[1])

    def test_modelo_que_sumiu_e_trocado_por_um_que_a_conta_enxerga_e_lembrado(self):
        cli, comp = _cli(lambda kw: E_MODELO_OPENAI if kw["model"] == "gpt-5.4-mini" else None, modelos=["gpt-5.5", "gpt-5-mini"])
        self.assertEqual(self.criar("openai", cli), "ok")
        self.assertEqual([c["model"] for c in comp.chamadas], ["gpt-5.4-mini", "gpt-5-mini"])
        self.assertEqual(self.core._modelo_do_slot("openai"), "gpt-5-mini")        # a próxima mensagem já vai direto

    def test_claude_e_llama_dividem_a_descoberta(self):
        cli, _ = _cli(lambda kw: E_SUMIU if kw["model"] == "openrouter/free" else None, modelos=["openai/gpt-oss-20b:free"])
        self.criar("claude", cli)
        self.assertEqual(self.core._modelo_do_slot("llama"), "openai/gpt-oss-20b:free")

    def test_nao_inventa_modelo_quando_a_conta_nao_tem_nenhum_que_sirva(self):
        cli, comp = _cli(lambda kw: E_MODELO_OPENAI, modelos=["gpt-5.5-pro"])
        with self.assertRaises(RuntimeError):
            self.criar("openai", cli)
        self.assertEqual(len(comp.chamadas), 1)

    def test_override_do_usuario_nao_e_trocado_as_escondidas(self):
        self.core.settings = _Cfg(modelos_override={"openai": "meu-modelo"})
        cli, comp = _cli(lambda kw: E_MODELO_OPENAI, modelos=["gpt-5-mini"])
        with self.assertRaises(RuntimeError):
            self.criar("openai", cli)
        self.assertEqual(len(comp.chamadas), 1)                                   # respeita o que a pessoa escolheu

    def test_politica_do_openrouter_nao_gasta_tentativas_e_sobe_o_erro(self):
        cli, comp = _cli(lambda kw: E_POLITICA, modelos=["openrouter/free"])
        with self.assertRaises(RuntimeError) as ctx:
            self.criar("claude", cli)
        self.assertEqual(len(comp.chamadas), 1)
        self.assertEqual(M.classificar(ctx.exception), "politica")

    def test_nunca_tenta_mais_de_duas_vezes_por_motivo(self):
        cli, comp = _cli(lambda kw: E_PARAM, modelos=[])
        with self.assertRaises(RuntimeError):
            self.criar("groq", cli)
        self.assertEqual(len(comp.chamadas), 2)

    def test_testar_chat_explica_em_portugues_o_que_a_chave_valida_nao_mostrava(self):
        cli, _ = _cli(lambda kw: E_COTA_OPENAI)
        with mock.patch("brain.zenith_core.OpenAI", return_value=cli):
            ok, msg = self.core.testar_chat("openai", "sk-teste")
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("Chave válida, mas o chat falhou"))
        self.assertIn("Billing", msg)

    def test_testar_chat_ok_diz_o_modelo_usado(self):
        cli, _ = _cli(lambda kw: None)
        with mock.patch("brain.zenith_core.OpenAI", return_value=cli):
            ok, msg = self.core.testar_chat("openai", "sk-teste")
        self.assertTrue(ok)
        self.assertIn("gpt-5.4-mini", msg)

    def test_testar_chat_chave_errada_diz_chave_e_nao_chat(self):
        cli, _ = _cli(lambda kw: E_CHAVE)
        with mock.patch("brain.zenith_core.OpenAI", return_value=cli), \
                mock.patch.object(P, "url_do_slot", return_value="https://exemplo.invalido/v1"):
            ok, msg = self.core.testar_chat("groq", "gsk-x")
        self.assertFalse(ok)
        self.assertNotIn("o chat falhou", msg)
        self.assertIn("recusou a chave", msg)


class _GemModels:
    """models do Gemini de mentira: cada regra decide o que acontece por nome de modelo."""

    def __init__(self, regra, modelos=()):
        self.regra, self.modelos, self.chamadas = regra, list(modelos), []

    def generate_content(self, model, contents, config=None):
        self.chamadas.append(model)
        erro = self.regra(model)
        if erro:
            raise RuntimeError(erro)
        return types.SimpleNamespace(text="ok")

    def list(self):
        return [types.SimpleNamespace(name=f"models/{m}") for m in self.modelos]


def _cli_gemini(regra, modelos=()):
    models = _GemModels(regra, modelos)
    return types.SimpleNamespace(models=models), models


E_GEMINI_SOBRECARGA = "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}"
E_GEMINI_VELHO = ("404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer "
                  "available to new users.'}}")


class TesteDeChatDoGeminiTests(unittest.TestCase):
    """v1.10 — "só o Gemini funciona" era meia verdade: o botão de testar dizia "chave válida" para o Gemini
    mesmo com todos os modelos em 503/404, porque o Gemini era o ÚNICO provedor que nunca passava pelo teste
    de chat (só listava modelos). Estes testes fixam o comportamento novo, com as mensagens reais do Google."""

    def setUp(self):
        from brain.zenith_core import ZenithCore
        self.core = object.__new__(ZenithCore)
        self.core.settings = _Cfg()
        self.core._modelo_resolvido = {}

    def test_sobrecarga_em_todo_modelo_nao_vira_chave_valida(self):
        cli, comp = _cli_gemini(lambda m: E_GEMINI_SOBRECARGA)
        with mock.patch("brain.zenith_core.genai.Client", return_value=cli):
            ok, msg = self.core.testar_chat("gemini", "chave")
        self.assertFalse(ok)
        self.assertNotIn("Chave do Gemini válida", msg)
        self.assertTrue(msg.startswith("Chave parece válida, mas o chat falhou"))
        self.assertIn("sobrecarregados", msg)
        self.assertGreaterEqual(len(comp.chamadas), 2)          # tentou a cadeia, não desistiu no primeiro

    def test_um_modelo_da_cadeia_respondendo_ja_e_sucesso(self):
        cli, comp = _cli_gemini(lambda m: E_GEMINI_SOBRECARGA if m == G.MODELO_PADRAO else None)
        with mock.patch("brain.zenith_core.genai.Client", return_value=cli):
            ok, msg = self.core.testar_chat("gemini", "chave")
        self.assertTrue(ok)
        self.assertEqual(comp.chamadas[0], G.MODELO_PADRAO)
        self.assertIn(comp.chamadas[-1], msg)                   # diz QUAL modelo respondeu

    def test_nome_aposentado_cai_no_melhor_modelo_que_a_conta_ve(self):
        cli, comp = _cli_gemini(lambda m: E_GEMINI_VELHO if m != "gemini-3.8-flash" else None,
                                modelos=["gemini-3.8-flash", "gemini-3.5-flash"])
        with mock.patch("brain.zenith_core.genai.Client", return_value=cli):
            ok, msg = self.core.testar_chat("gemini", "chave")
        self.assertTrue(ok)
        self.assertIn("gemini-3.8-flash", msg)


E_GROQ_413 = ("Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` in organization "
              "`org_teste` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 12045, please "
              "reduce your message size and try again.'}}")


class PedidoGrandeTests(unittest.TestCase):
    """v1.10 — log real do Anderson (28/10/2026): o Groq recusava a conversa inteira com 413 ("Request too large ...
    tokens per minute: Limit 8000") e o chat culpava "falta de saldo ou de cota". O erro é TAMANHO do pedido."""

    def test_413_do_limite_por_minuto_nao_e_falta_de_saldo(self):
        self.assertEqual(M.classificar(E_GROQ_413), "contexto")
        msg = M.diagnosticar("groq", E_GROQ_413)["mensagem"]
        self.assertIn("limite de tokens por minuto", msg)
        self.assertNotIn("saldo", msg)

    def test_manda_de_novo_sem_o_historico_antes_de_desistir(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = _Cfg()
        core._modelo_resolvido = {"groq": "openai/gpt-oss-120b"}
        core._custom_models = {}
        core._build_system_prompt = lambda: "SISTEMA"
        core._historico_para_provedor = lambda p: [{"role": "user", "content": "pergunta antiga enorme"}]
        vistos = []

        def criar(ia, cli, model, mensagens, max_saida=8192, timeout=180):
            vistos.append(mensagens)
            if len(vistos) == 1:
                raise RuntimeError(E_GROQ_413)
            return "ok"

        core._openai_criar = criar
        self.assertEqual(core._openai_chamar("groq", object(), "oi"), "ok")
        self.assertEqual(len(vistos), 2)
        self.assertEqual(len(vistos[0]), 3)                          # sistema + histórico + pergunta
        self.assertEqual([m["role"] for m in vistos[1]], ["system", "user"])   # sem o histórico


class FallbackExplicaTests(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        c = object.__new__(ZenithCore)
        c.settings = _Cfg(active_ai="groq")
        c.ia_ativa = "groq"
        c._custom_models = {}
        c._modelo_resolvido = {}
        c.client = None
        c._clients = {}
        c._clientes_por_chave = {"groq": [{"chave": "", "cliente": object()}], "gemini": [{"chave": "", "cliente": object()}]}
        self.core = c

    def test_quando_cai_para_o_gemini_o_chat_diz_por_que(self):
        def raw(prov, prompt, image_bytes=None, image_mime=None):
            if prov == "groq":
                raise RuntimeError(E_LIMITE)
            return "resposta do gemini"
        self.core._call_provider_raw = raw
        txt = self.core._call_provider("oi")
        self.assertIn("resposta do gemini", txt)
        self.assertIn("Motivo", txt)
        self.assertIn("limite de uso", txt)

    def test_erro_final_traz_o_motivo_de_cada_ia(self):
        def raw(prov, *a, **k):
            raise RuntimeError(E_CHAVE if prov == "groq" else E_COTA_OPENAI)
        self.core._call_provider_raw = raw
        with self.assertRaises(RuntimeError) as ctx:
            self.core._call_provider("oi")
        self.assertIn("recusou a chave", str(ctx.exception))


class ListaDeIAsTests(unittest.TestCase):
    CAT = {"provedores": [
        {"id": "gemini", "nome": "Gemini", "url": "", "modelo": "", "onde_pegar": "", "dica": ""},
        {"id": "openai", "nome": "OpenAI", "url": "", "modelo": "", "onde_pegar": "", "dica": ""},
        {"id": "claude", "nome": "OpenRouter", "url": "https://openrouter.ai/api/v1", "modelo": "", "onde_pegar": "", "dica": ""},
        {"id": "groq", "nome": "Groq", "url": "https://api.groq.com/openai/v1", "modelo": "", "onde_pegar": "", "dica": ""}],
        "servicos": [], "atalhos": []}

    def _cfg(self, **d):
        return d

    def test_chave_cadastrada_pela_tela_de_chaves_conta_como_configurada(self):
        # o caso dos prints: Groq/OpenAI/OpenRouter com chave, mas só em "chaves_extras" (a principal ficou vazia)
        e = {x["id"]: x for x in P.montar_entradas(self._cfg(gemini_key="AIza", chaves_extras={
            "groq": ["gsk_1"], "openai": ["sk-1"], "claude": ["sk-or-1"]}), self.CAT)}
        for pid in ("gemini", "groq", "openai", "claude"):
            self.assertTrue(e[pid]["configurada"], pid)
            self.assertTrue(e[pid]["rotulo"].startswith("✓ ") or "✓ " in e[pid]["rotulo"], e[pid]["rotulo"])

    def test_sem_chave_nenhuma_continua_com_aviso(self):
        e = {x["id"]: x for x in P.montar_entradas(self._cfg(), self.CAT)}
        self.assertFalse(e["groq"]["configurada"])
        self.assertIn("⚠", e["groq"]["rotulo"])

    def test_llama_extra_vale_para_o_openrouter(self):
        e = {x["id"]: x for x in P.montar_entradas(self._cfg(chaves_extras={"llama": ["k"]}), self.CAT)}
        self.assertTrue(e["claude"]["configurada"])

    def test_extras_vazias_ou_lixo_nao_contam(self):
        for extras in ({"groq": []}, {"groq": [""]}, {"groq": [None]}, {"groq": "texto"}, "nada", None):
            e = {x["id"]: x for x in P.montar_entradas(self._cfg(chaves_extras=extras), self.CAT)}
            self.assertFalse(e["groq"]["configurada"], extras)

    def test_provedor_que_precisa_de_url_sem_url_no_catalogo_continua_nao_configurado(self):
        cat = {"provedores": [dict(self.CAT["provedores"][3], url="")], "servicos": [], "atalhos": []}
        e = P.montar_entradas(self._cfg(chaves_extras={"groq": ["k"]}), cat)
        self.assertFalse(e[0]["configurada"])


class GeminiReservaTests(unittest.TestCase):
    def test_cadeia_termina_nos_modelos_lite_de_cota_propria(self):
        c = G.cadeia_de_modelos("gemini-3.5-flash")
        self.assertEqual(c[:2], ["gemini-3.5-flash", "gemini-2.5-flash"])
        self.assertEqual(c[-2:], ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])

    def test_erro_de_modelo_do_lite_nao_apaga_o_erro_de_cota_dos_flash(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core._msg_atual = "oi"
        core._modelo_em_uso = ""
        core.settings = _Cfg(gemini_modelo="gemini-3.5-flash")
        core._gemini_contents = lambda *a, **k: []
        core._gemini_config = lambda *a, **k: None
        core._portao = lambda: None

        def gerar(model, contents, config):
            if "lite" in model:
                raise RuntimeError("404 models/%s is not found" % model)
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded per day")
        cli = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=gerar))
        with mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                core._gemini_chamar("oi", cliente=cli)
        self.assertIn("quota", str(ctx.exception).lower())                       # o motivo real, não "modelo não existe"


class ComandoModeloTests(unittest.TestCase):
    def _cmd(self, texto, settings):
        from brain import zenith_commands as CMD
        fn = next(getattr(CMD, n) for n in ("tratar", "processar", "executar") if hasattr(CMD, n))
        return fn(texto, {"settings": settings, "core": None})

    def test_modelo_de_outras_ias(self):
        cfg = _Cfg()
        cfg.update = lambda m: cfg.d.update(m)
        r = self._cmd("/modelo groq llama-3.1-8b-instant", cfg)
        self.assertEqual(cfg.d["modelos_override"]["groq"], "llama-3.1-8b-instant")
        r = self._cmd("/modelo openrouter openai/gpt-oss-20b:free", cfg)
        self.assertEqual(cfg.d["modelos_override"]["claude"], "openai/gpt-oss-20b:free")
        self.assertEqual(cfg.d["modelos_override"]["llama"], "openai/gpt-oss-20b:free")
        self._cmd("/modelo openrouter auto", cfg)
        self.assertNotIn("claude", cfg.d["modelos_override"])
        self.assertNotIn("llama", cfg.d["modelos_override"])
        r = self._cmd("/modelo openai ../../etc/passwd; rm", cfg)
        self.assertNotIn("openai", cfg.d["modelos_override"])                   # nome estranho é recusado


if __name__ == "__main__":
    unittest.main()
