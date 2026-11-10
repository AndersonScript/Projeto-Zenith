"""
Testes do v23 — "ela está burra": modelo certo do Gemini, raciocínio por geração, regras contra pedir permissão em
texto, memória permanente, habilidades que ela cria, observação ao vivo, fundo do avatar e correções do chat.
Rodar: python -m unittest tests.test_v23 -v

O que cobrem (sem Godot, SEM rede, sem câmera): a lógica pura e os ganchos no Cérebro.
O que NÃO provam: o Godot rodando (fundo sólido/chroma, indicador 🔴 e o balão sem picar só se confirmam no PC) nem
que a API do Gemini aceita hoje exatamente estes parâmetros (por isso existe o fallback de modelo e de raciocínio).
"""
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_commands as cmd
from brain import zenith_gemini as G
from brain import zenith_habilidades as H
from brain import zenith_modos as modos
from brain import zenith_observar as O


class FakeSettings:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **dados):
        self.dados = dict(dados)

    def get(self, chave, padrao=None):
        v = self.dados.get(chave, padrao)
        return padrao if v is None else v

    def update(self, mudancas):
        self.dados.update(mudancas)


def ler(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


# ======================================================================
class TestGemini(unittest.TestCase):
    def test_modelo_padrao_e_geracao_atual(self):
        self.assertEqual(G.MODELO_PADRAO, "gemini-3.5-flash")
        self.assertIn("gemini-2.5-flash", G.MODELOS_RESERVA)        # reserva: o antigo ainda é tentado

    def test_normalizar_tira_prefixo_models(self):
        self.assertEqual(G.normalizar("models/gemini-3.5-flash"), "gemini-3.5-flash")
        self.assertEqual(G.normalizar(" gemini-2.5-pro "), "gemini-2.5-pro")
        self.assertEqual(G.normalizar(None), "")

    def test_raciocinio_gemini3_usa_thinking_level(self):
        self.assertEqual(G.thinking_kwargs("gemini-3.5-flash", False), {"thinking_level": "LOW"})
        self.assertEqual(G.thinking_kwargs("gemini-3.5-flash", True, "oi, tudo bem?"), {"thinking_level": "MEDIUM"})
        self.assertEqual(G.thinking_kwargs("gemini-3.5-flash", True, "resolva a integral de x^2 passo a passo"),
                         {"thinking_level": "HIGH"})

    def test_gemini3_pro_nao_aceita_medium(self):
        self.assertEqual(G.thinking_kwargs("gemini-3-pro-preview", True, "oi"), {"thinking_level": "HIGH"})

    def test_raciocinio_gemini25_usa_thinking_budget(self):
        self.assertEqual(G.thinking_kwargs("gemini-2.5-flash", True), {"thinking_budget": -1})
        self.assertEqual(G.thinking_kwargs("gemini-2.5-flash", False), {"thinking_budget": 0})
        self.assertEqual(G.thinking_kwargs("gemini-2.5-pro", False), {"thinking_budget": 512})   # Pro não desliga

    def test_modelo_desconhecido_nao_manda_raciocinio(self):
        self.assertEqual(G.thinking_kwargs("outro-modelo", True), {})

    def test_dificil(self):
        self.assertTrue(G.dificil("qual a derivada de sen(x)?"))
        self.assertTrue(G.dificil("a" * 500))
        self.assertTrue(G.dificil("2 + 2 = ?"))
        self.assertFalse(G.dificil("oi, bom dia!"))

    def test_cadeia_de_modelos_sem_repetir(self):
        self.assertEqual(G.cadeia_de_modelos("gemini-3.5-flash"),      # v1.6.1: + os "lite" (cota própria, ~500/dia no plano grátis)
                         ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])
        self.assertEqual(G.cadeia_de_modelos("gemini-3.1-pro-preview")[0], "gemini-3.1-pro-preview")
        self.assertEqual(len(G.cadeia_de_modelos("gemini-3.1-pro-preview")), 5)
        self.assertEqual(G.cadeia_de_modelos("")[0], "gemini-3.5-flash")

    def test_classificar_erro(self):
        c = G.classificar_erro
        self.assertEqual(c("503 UNAVAILABLE. The model is overloaded. high demand"), "sobrecarga")
        self.assertEqual(c("429 RESOURCE_EXHAUSTED rate limit"), "sobrecarga")
        self.assertEqual(c("404 NOT_FOUND: models/gemini-9 is not found for API version v1beta"), "modelo")
        self.assertEqual(c("400 INVALID_ARGUMENT: thinking level not supported for this model"), "raciocinio")
        self.assertEqual(c("API key not valid. Please pass a valid API key."), "chave")
        self.assertEqual(c("quota exceeded for metric ... per day"), "cota")
        self.assertEqual(c("response blocked by safety"), "conteudo")
        self.assertEqual(c("algo estranho"), "outro")

    def test_escolha_e_listagem_de_modelos(self):
        ids = ["models/gemini-2.5-flash", "models/gemini-3.5-flash", "models/gemini-3.5-flash-image",
               "models/gemini-3.1-pro-preview", "models/embedding-001", "models/gemma-3-27b", "models/gemini-3.8-flash"]
        self.assertEqual(G.melhor_modelo(ids), "gemini-3.5-flash")
        self.assertNotIn("gemini-3.5-flash-image", G.sao_de_texto(ids))
        self.assertNotIn("embedding-001", " ".join(G.sao_de_texto(ids)))
        self.assertEqual(G.melhor_modelo(["models/gemini-2.5-flash", "models/gemini-3.6-flash"]), "gemini-3.6-flash")
        self.assertEqual(G.melhor_modelo([]), "")
        lista = G.formatar_lista(ids, "gemini-3.5-flash")
        self.assertIn("◀ em uso", lista)
        self.assertIn("Pro", lista)


# ======================================================================
class _FakeTypes:
    """Imita genai.types o bastante pra montar config/conteúdo sem a SDK."""
    class Part:
        def __init__(self, text=None, **kw):
            self.text = text
        @staticmethod
        def from_bytes(data, mime_type):
            return ("img", mime_type)

    class Content:
        def __init__(self, role, parts):
            self.role, self.parts = role, parts

    class ThinkingConfig:
        def __init__(self, **kw):
            self.kw = kw

    class GenerateContentConfig:
        def __init__(self, **kw):
            self.kw = kw


class TestChamadaGemini(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        from brain.zenith_executor import ZenithExecutor
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(active_ai="gemini", modo_atual="normal", gemini_modelo="gemini-3.5-flash",
                                     thinking_mode="pensante", contexto_modo="desligado")
        core.ia_ativa = "gemini"
        core.executor = ZenithExecutor()
        core.conv_id = "c1"
        core._clients = {}
        core._custom_models = {}
        core._hist_depth = 0
        core._msg_atual = "qual a derivada de x^2?"
        core._modelo_em_uso = ""
        self.fake_genai = mock.MagicMock()
        self.fake_genai.types = _FakeTypes
        self.chamadas = []
        self.respostas = {}          # modelo -> lista de resultados (texto ou Exception)

        def gerar(model, contents, config):
            self.chamadas.append((model, config.kw.get("thinking_config")))
            r = self.respostas[model].pop(0)
            if isinstance(r, Exception):
                raise r
            return type("R", (), {"text": r})()

        client = mock.MagicMock()
        client.models.generate_content.side_effect = gerar
        core.client = client
        core._build_system_prompt = lambda: "SISTEMA"
        self.core = core
        p = mock.patch("brain.zenith_core.genai", self.fake_genai)
        p.start()
        self.addCleanup(p.stop)
        s = mock.patch("brain.zenith_core.time.sleep", lambda *_: None)
        s.start()
        self.addCleanup(s.stop)

    def test_usa_o_modelo_escolhido_e_o_raciocinio_da_geracao(self):
        self.respostas = {"gemini-3.5-flash": ["oi!"]}
        self.assertEqual(self.core._gemini_chamar("pergunta"), "oi!")
        modelo, tc = self.chamadas[0]
        self.assertEqual(modelo, "gemini-3.5-flash")
        self.assertEqual(tc.kw, {"thinking_level": "MEDIUM"})      # mensagem difícil (derivada) no modo "rapido" (padrão v24)
        self.assertEqual(self.core._modelo_em_uso, "gemini-3.5-flash")

    def test_modelo_inexistente_cai_pro_proximo(self):
        self.core.settings.update({"gemini_modelo": "gemini-9-ultra"})
        self.respostas = {"gemini-9-ultra": [RuntimeError("404 NOT_FOUND models/gemini-9-ultra is not found")],
                          "gemini-3.5-flash": ["ok pelo reserva"]}
        self.assertEqual(self.core._gemini_chamar("x"), "ok pelo reserva")
        self.assertEqual([c[0] for c in self.chamadas], ["gemini-9-ultra", "gemini-3.5-flash"])

    def test_503_tenta_de_novo_e_depois_troca_de_modelo(self):
        erro = RuntimeError("503 UNAVAILABLE. high demand")
        self.respostas = {"gemini-3.5-flash": [erro, erro], "gemini-2.5-flash": ["respondeu o reserva"]}
        self.assertEqual(self.core._gemini_chamar("x"), "respondeu o reserva")
        self.assertEqual([c[0] for c in self.chamadas], ["gemini-3.5-flash", "gemini-3.5-flash", "gemini-2.5-flash"])

    def test_raciocinio_recusado_refaz_sem_ele(self):
        self.respostas = {"gemini-3.5-flash": [RuntimeError("400 INVALID_ARGUMENT thinking level not supported"), "ok"]}
        self.assertEqual(self.core._gemini_chamar("x"), "ok")
        self.assertIsNotNone(self.chamadas[0][1])
        self.assertIsNone(self.chamadas[1][1])                       # 2ª tentativa sem ThinkingConfig

    def test_erro_de_chave_nao_fica_tentando_modelos(self):
        self.respostas = {"gemini-3.5-flash": [RuntimeError("API key not valid. Please pass a valid API key.")]}
        with self.assertRaises(RuntimeError):
            self.core._gemini_chamar("x")
        self.assertEqual(len(self.chamadas), 1)

    def test_resposta_vazia_vira_erro_claro(self):
        self.respostas = {"gemini-3.5-flash": ["   "]}
        with self.assertRaises(RuntimeError) as cm:
            self.core._gemini_chamar("x")
        self.assertIn("vazia", str(cm.exception))

    def test_saida_maxima_vem_das_configuracoes(self):
        self.core.settings.update({"saida_max_tokens": 50000})
        cfg = self.core._gemini_config("gemini-3.5-flash", "oi")
        self.assertEqual(cfg.kw["max_output_tokens"], 50000)
        self.assertEqual(cfg.kw["system_instruction"], "SISTEMA")

    def test_modo_economico_baixa_o_raciocinio(self):
        self.core.settings.update({"thinking_mode": "economico"})
        self.assertEqual(self.core._gemini_config("gemini-3.5-flash", "calcule a integral").kw["thinking_config"].kw,
                         {"thinking_level": "LOW"})

    def test_historico_da_conversa_vira_contents(self):
        conversa = {"id": "c1", "messages": [{"sender": "user", "text": "meu nome é Anderson"},
                                              {"sender": "ai", "text": "Prazer!"},
                                              {"sender": "user", "text": "qual é o meu nome?"}]}
        self.core.settings.update({"contexto_modo": "max"})
        self.core._hist_depth = 1
        with mock.patch("brain.zenith_history.get_conversation", return_value=conversa):
            contents = self.core._gemini_contents("qual é o meu nome?")
        self.assertEqual([c.role for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[-1].parts[0].text, "qual é o meu nome?")

    def test_migracao_unica_do_modelo_antigo(self):
        self.core.settings = FakeSettings(gemini_modelo="gemini-2.5-flash")
        self.core._migrar_modelo_gemini()
        self.assertEqual(self.core.settings.get("gemini_modelo"), "gemini-3.5-flash")
        self.assertTrue(self.core.settings.get("gemini_modelo_v23"))
        self.core.settings.update({"gemini_modelo": "gemini-2.5-flash"})      # escolha do usuário DEPOIS da migração
        self.core._migrar_modelo_gemini()
        self.assertEqual(self.core.settings.get("gemini_modelo"), "gemini-2.5-flash")

    def test_migracao_respeita_modelo_escolhido_pelo_usuario(self):
        self.core.settings = FakeSettings(gemini_modelo="gemini-3.1-pro-preview")
        self.core._migrar_modelo_gemini()
        self.assertEqual(self.core.settings.get("gemini_modelo"), "gemini-3.1-pro-preview")

    def test_listar_modelos_usa_a_chave_do_usuario(self):
        self.core.client.models.list.return_value = [type("M", (), {"name": "models/gemini-3.5-flash"})(),
                                                      type("M", (), {"name": "models/gemini-2.5-flash"})()]
        self.assertEqual(self.core.listar_modelos_gemini(), ["models/gemini-3.5-flash", "models/gemini-2.5-flash"])


# ======================================================================
class TestVelocidade(unittest.TestCase):
    def test_niveis_por_velocidade_no_gemini3(self):
        k = G.thinking_kwargs
        m = "gemini-3.5-flash"
        self.assertEqual(k(m, True, "oi, tudo bem?", "rapido"), {"thinking_level": "LOW"})
        self.assertEqual(k(m, True, "resolva a integral de x^2", "rapido"), {"thinking_level": "MEDIUM"})
        self.assertEqual(k(m, True, "oi", "equilibrado"), {"thinking_level": "MEDIUM"})
        self.assertEqual(k(m, True, "resolva a integral de x^2", "equilibrado"), {"thinking_level": "HIGH"})
        self.assertEqual(k(m, True, "oi", "profundo"), {"thinking_level": "HIGH"})
        self.assertEqual(k(m, False, "resolva a integral", "profundo"), {"thinking_level": "LOW"})     # econômico manda
        self.assertEqual(k(m, True, "oi", "xyz"), {"thinking_level": "MEDIUM"})                         # valor inválido = equilibrado

    def test_gemini25_por_velocidade(self):
        k = G.thinking_kwargs
        self.assertEqual(k("gemini-2.5-flash", True, "oi", "rapido"), {"thinking_budget": 0})
        self.assertEqual(k("gemini-2.5-flash", True, "calcule a integral", "rapido"), {"thinking_budget": 2048})
        self.assertEqual(k("gemini-2.5-flash", True, "oi", "profundo"), {"thinking_budget": -1})
        self.assertEqual(k("gemini-2.5-pro", True, "oi", "rapido"), {"thinking_budget": 512})

    def test_padroes(self):
        from brain.zenith_settings import DEFAULT_SETTINGS as d
        self.assertEqual(d["velocidade"], "rapido")
        self.assertTrue(d["streaming_real"])

    def test_comando_velocidade(self):
        cfg = FakeSettings()
        self.assertIn("rapido", cmd.tratar("/velocidade", {"settings": cfg})["resposta"])
        cmd.tratar("/velocidade profundo", {"settings": cfg})
        self.assertEqual(cfg.get("velocidade"), "profundo")
        cmd.tratar("/velocidade equilibrado", {"settings": cfg})
        self.assertEqual(cfg.get("velocidade"), "equilibrado")
        self.assertIn("Use", cmd.tratar("/velocidade turbo", {"settings": cfg})["resposta"])
        self.assertEqual(cfg.get("velocidade"), "equilibrado")


class TestStreaming(unittest.TestCase):
    def portao(self, **kw):
        from brain import zenith_stream as S
        saida = []
        return S.Portao(saida.append, **kw), saida

    def test_libera_frase_a_frase(self):
        p, saida = self.portao()
        for d in ["Oi, tu", "do bem? Que ", "bom te ver", ". Vamos"]:
            p.alimentar(d)
        self.assertEqual(saida, ["Oi, tudo bem? ", "Que bom te ver. "])        # "Vamos" ainda não terminou
        self.assertEqual(p.liberado, "Oi, tudo bem? Que bom te ver. ")

    def test_etiqueta_fecha_o_portao_e_nao_vaza(self):
        p, saida = self.portao()
        p.alimentar("Vou olhar! <ver_camera>mesa</ver_camera> depois falo.")
        self.assertEqual(saida, ["Vou olhar! "])
        self.assertTrue(p.fechado)
        self.assertEqual(p.motivo, "etiqueta")
        p.alimentar(" Mais uma frase. E outra. ")
        self.assertEqual(saida, ["Vou olhar! "])                                  # fechado: nada mais sai

    def test_etiqueta_no_meio_da_frase(self):
        p, saida = self.portao()
        p.alimentar("Beleza, vou fazer <executar_python>print(1)</executar_python>")
        self.assertEqual(saida, ["Beleza, vou fazer "])

    def test_bloco_de_codigo_fecha_o_portao(self):
        p, saida = self.portao()
        p.alimentar("Aqui está o código. ```python\nprint(1)\n``` Pronto. ")
        self.assertEqual(saida, ["Aqui está o código. "])
        self.assertEqual(p.motivo, "codigo")

    def test_frase_insegura_nao_sai_e_fecha(self):
        p, saida = self.portao(seguro=lambda txt: "grave" not in txt)
        p.alimentar("Tudo bem por aqui. Isso é grave. Outra. ")
        self.assertEqual(saida, ["Tudo bem por aqui. "])
        self.assertEqual(p.motivo, "seguranca")

    def test_atitude_ruim_fecha_o_portao_no_meio(self):
        from brain import zenith_conhecimento as K
        p, saida = self.portao(atitude=lambda txt: K.problemas_de_atitude(txt, "desenhe você"))
        p.alimentar("Que ideia legal! Como uma IA, eu não tenho uma forma física. Mas tento. ")
        self.assertEqual(saida, ["Que ideia legal! "])
        self.assertEqual(p.motivo, "atitude")

    def test_terminar_nao_libera_o_resto(self):
        p, saida = self.portao()
        p.alimentar("Primeira frase. Segunda sem ponto final")
        p.terminar()
        self.assertEqual(saida, ["Primeira frase. "])           # o resto vai pelo caminho completo (reconciliar)

    def test_reconciliar(self):
        from brain import zenith_stream as S
        self.assertEqual(S.reconciliar("Oi. Tudo bem? ", "Oi. Tudo bem? Que bom."), (True, "Que bom."))
        self.assertEqual(S.reconciliar("Oi. Tudo bem? ", "Oi.  Tudo bem?"), (True, ""))
        self.assertEqual(S.reconciliar("", "Qualquer coisa."), (True, "Qualquer coisa."))
        ok, resto = S.reconciliar("Oi. Tudo bem? ", "Resposta que o validador reescreveu.")
        self.assertFalse(ok)
        self.assertEqual(resto, "Resposta que o validador reescreveu.")

    def test_reconciliar_preserva_quebras_do_resto(self):
        from brain import zenith_stream as S
        ok, resto = S.reconciliar("Veja: ", "Veja: \n\n1. item um\n2. item dois")
        self.assertTrue(ok)
        self.assertEqual(resto, "1. item um\n2. item dois")

    def test_sessao_de_entrega(self):
        from brain import zenith_stream as S
        msgs, fala_log = [], []

        class Fala:
            def add(self, t): fala_log.append(("add", t))
            def fim(self): fala_log.append(("fim",))
            def cancelar(self): fala_log.append(("cancelar",))

        s = S.SessaoDeEntrega(msgs.append, criar_fala=lambda: Fala())
        s.ao_liberar("Oi! ")
        s.ao_liberar("Tudo bem? ")
        s.entregar_resto("Fim.")
        self.assertEqual([m["delta"] for m in msgs], ["Oi! ", "Tudo bem? ", "Fim.", ""])
        self.assertTrue(msgs[-1]["done"])
        self.assertEqual(fala_log, [("add", "Oi! "), ("add", "Tudo bem? "), ("add", "Fim."), ("fim",)])

    def test_sessao_cancelada_corta_a_voz_e_fecha_o_balao(self):
        from brain import zenith_stream as S
        msgs, fala_log = [], []

        class Fala:
            def add(self, t): fala_log.append("add")
            def fim(self): fala_log.append("fim")
            def cancelar(self): fala_log.append("cancelar")

        s = S.SessaoDeEntrega(msgs.append, criar_fala=lambda: Fala())
        s.ao_liberar("Resposta ruim. ")
        s.cancelar()
        s.ao_liberar("não deve sair. ")                                        # depois de cancelada, ignora
        self.assertEqual(fala_log, ["add", "cancelar"])
        self.assertTrue(msgs[-1]["done"])
        self.assertEqual(len(msgs), 2)

    def test_pausa_total_bloqueia_a_sessao(self):
        from brain import zenith_stream as S
        msgs = []
        s = S.SessaoDeEntrega(msgs.append, pausado=lambda: True)
        s.ao_liberar("Oi! ")
        self.assertEqual(msgs, [])


class _PedacoStream:
    def __init__(self, text):
        self.text = text


class TestStreamingNoCore(unittest.TestCase):
    """O Gemini em streaming: texto sai frase a frase pelo portão e o texto INTEIRO volta pro caminho normal."""
    def setUp(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(active_ai="gemini", gemini_modelo="gemini-3.5-flash", thinking_mode="pensante",
                                     contexto_modo="desligado", streaming_real=True, atitude_validador=True, velocidade="rapido")
        core.ia_ativa = "gemini"
        core._hist_depth = 0
        core._msg_atual = "oi"
        core._modelo_em_uso = ""
        core._build_system_prompt = lambda: "SISTEMA"
        self.core = core
        self.fake_genai = mock.MagicMock()
        self.fake_genai.types = _FakeTypes
        for alvo, valor in (("brain.zenith_core.genai", self.fake_genai), ("brain.zenith_core.time.sleep", lambda *_: None)):
            p = mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

    def _cliente(self, pedacos=None, erro_no_meio=False):
        cli = mock.MagicMock()
        def stream(model, contents, config):
            for i, pd in enumerate(pedacos or []):
                if erro_no_meio and i == 2:
                    raise RuntimeError("503 UNAVAILABLE high demand")
                yield _PedacoStream(pd)
        cli.models.generate_content_stream.side_effect = stream
        cli.models.generate_content.return_value = type("R", (), {"text": "Resposta inteira sem streaming."})()
        self.core.client = cli
        return cli

    def test_texto_sai_frase_a_frase_e_o_total_volta(self):
        cli = self._cliente(["Oi, tudo ", "bem? Que bom ", "te ver. Como ", "posso ajudar?"])
        saida = []
        self.core._set_portao(self.core._criar_portao(saida.append, "oi"))
        total = self.core._gemini_chamar("oi")
        self.assertEqual(saida, ["Oi, tudo bem? ", "Que bom te ver. "])        # a última frase fica pro caminho completo
        self.assertEqual(total, "Oi, tudo bem? Que bom te ver. Como posso ajudar?")
        cli.models.generate_content.assert_not_called()

    def test_sem_destino_usa_o_caminho_antigo(self):
        cli = self._cliente(["x"])
        self.core._set_portao(self.core._criar_portao(None, "oi"))
        self.assertEqual(self.core._gemini_chamar("oi"), "Resposta inteira sem streaming.")
        cli.models.generate_content_stream.assert_not_called()

    def test_desligado_nas_configuracoes(self):
        self.core.settings.update({"streaming_real": False})
        self.assertIsNone(self.core._criar_portao(lambda t: None, "oi"))

    def test_so_o_gemini_transmite(self):
        self.core.ia_ativa = "openai"
        self.assertIsNone(self.core._criar_portao(lambda t: None, "oi"))

    def test_erro_no_meio_nao_duplica_o_que_ja_saiu(self):
        cli = self._cliente(["Primeira frase. ", "Segunda frase. ", "Terceira"], erro_no_meio=True)
        saida = []
        self.core._set_portao(self.core._criar_portao(saida.append, "oi"))
        texto = self.core._gemini_chamar("oi")                                   # 1ª tentativa quebra no meio; as seguintes NÃO transmitem
        self.assertEqual(saida, ["Primeira frase. ", "Segunda frase. "])
        self.assertEqual(texto, "Resposta inteira sem streaming.")
        self.assertEqual(self.core._portao().motivo, "erro")

    def test_portao_e_por_thread(self):
        saida = []
        self.core._set_portao(self.core._criar_portao(saida.append, "oi"))
        visto = {}
        t = threading.Thread(target=lambda: visto.update(p=self.core._portao()))
        t.start()
        t.join()
        self.assertIsNone(visto["p"])                                              # a observação ao vivo (outra thread) não herda

    def test_pensar_entrega_no_callback_e_o_resultado_completo(self):
        """Fim a fim com o Cérebro de verdade (sem rede): on_text recebe as frases; result['text'] vem inteiro."""
        from brain.zenith_core import ZenithCore
        from brain.zenith_executor import ZenithExecutor
        from brain.zenith_gatekeeper import DeterministicGuard
        core = self.core
        core.executor = ZenithExecutor()
        core.guard = DeterministicGuard("Anderson")
        core.is_locked = False
        core.is_processing = False
        core._midias = []
        core.memory = type("M", (), {"recall": lambda s, q: "", "save": lambda s, *a: None, "save_fact": lambda s, f: None,
                                     "contagem_chat_raw": lambda s: 0, "fatos_fixos": lambda s: ""})()
        core.conv_id = "c1"
        core.settings.persona_name, core.settings.user_name = "Zenith", "Anderson"
        core.settings.update({"biblia_validador": False})
        core._clients = {}
        self._cliente(["Oi, Anderson! ", "Tudo bem por aí? ", "Estou aqui."])
        recebido = []
        out = core.pensar("e aí, como você está hoje?", on_text=recebido.append)
        self.assertEqual(recebido, ["Oi, Anderson! ", "Tudo bem por aí? "])
        self.assertEqual(out["text"], "Oi, Anderson! Tudo bem por aí? Estou aqui.")


class TestEntregaNoCerebro(unittest.TestCase):
    """A entrega do resultado no Cérebro: streaming reconciliado, voz antes do texto, sem pausas artificiais."""
    def setUp(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        from brain import zenith_stream as S
        self.S = S
        b = object.__new__(ZenithHeadlessBrain)
        self.msgs = []
        b.bridge = type("B", (), {"send": lambda s, m: self.msgs.append(m)})()
        b.settings = FakeSettings(voice_enabled=True, response_streaming=True, streaming_real=True, vida_gestos_ia=False)
        b.active_conv_id = "c1"
        self.ordem = []
        voz = type("V", (), {})()
        voz.falar_async = lambda texto, **k: self.ordem.append(("voz", texto))
        voz.pode_falar = lambda: True
        self.fala_log = []

        class Fala:
            def __init__(f, log): f.log = log
            def add(f, t): f.log.append(("add", t))
            def fim(f): f.log.append(("fim",))
            def cancelar(f, silencioso=False): f.log.append(("cancelar",))
        voz.falar_stream_iniciar = lambda **k: Fala(self.fala_log)
        b.interaction = voz
        b._enviar_midias = lambda: None
        self.b = b
        self.dormiu = []
        for alvo, valor in (("brain.zenith_headless.time.sleep", lambda s: self.dormiu.append(s)),
                            ("brain.zenith_headless.history.append_message", lambda *a, **k: self.ordem.append(("hist", a[2]))),
                            ("brain.zenith_headless.pausa.ativo", lambda: False)):
            p = mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

    def _texto_do_chat(self):
        return "".join(m.get("delta", "") for m in self.msgs if m.get("action") == "chat_stream_chunk")

    def test_sem_streaming_a_voz_comeca_antes_do_texto_e_nao_ha_pausa_longa(self):
        resultado = {"text": "Primeira frase bem longa aqui para testar. Segunda frase bem longa aqui para testar. Terceira frase aqui.",
                     "pending_action": None, "blocked": False}
        self.b._deliver_result(resultado)
        self.assertEqual(self.ordem[0][0], "hist")
        self.assertEqual(self.ordem[1][0], "voz")                         # voz disparada ANTES dos pedaços de texto
        primeiro_texto = next(i for i, m in enumerate(self.msgs) if m.get("action") == "chat_stream_chunk")
        self.assertEqual(self._texto_do_chat().strip(), resultado["text"])
        self.assertTrue(all(s <= 0.08 for s in self.dormiu), self.dormiu)  # antes: até 0,6 s por frase
        self.assertLess(sum(self.dormiu), 0.5)

    def test_streaming_que_bate_entrega_so_o_resto(self):
        sessao = self.b._abrir_sessao_stream()
        sessao.ao_liberar("Oi, Anderson! ")
        sessao.ao_liberar("Tudo bem por aí? ")
        self.b._deliver_result({"text": "Oi, Anderson! Tudo bem por aí? Estou aqui pra ajudar.", "pending_action": None,
                                "blocked": False}, sessao)
        self.assertEqual(self._texto_do_chat(), "Oi, Anderson! Tudo bem por aí? Estou aqui pra ajudar.")
        self.assertEqual(self.fala_log, [("add", "Oi, Anderson! "), ("add", "Tudo bem por aí? "),
                                         ("add", "Estou aqui pra ajudar."), ("fim",)])
        self.assertFalse([o for o in self.ordem if o[0] == "voz"])         # não falou duas vezes
        self.assertEqual(len([m for m in self.msgs if m.get("done")]), 1)  # um só fechamento de balão
        self.assertEqual([o for o in self.ordem if o[0] == "hist"][0][1], "Oi, Anderson! Tudo bem por aí? Estou aqui pra ajudar.")

    def test_streaming_que_nao_bate_cancela_e_entrega_o_texto_final(self):
        sessao = self.b._abrir_sessao_stream()
        sessao.ao_liberar("Resposta que o validador vai reescrever. ")
        self.b._deliver_result({"text": "Texto corrigido e completo.", "pending_action": None, "blocked": False}, sessao)
        self.assertIn(("cancelar",), self.fala_log)
        self.assertIn(("voz", "Texto corrigido e completo."), self.ordem)  # fala o final inteiro, pelo caminho normal
        self.assertTrue(self._texto_do_chat().endswith("Texto corrigido e completo."))

    def test_resposta_bloqueada_pela_seguranca_cancela_o_que_ja_saiu(self):
        sessao = self.b._abrir_sessao_stream()
        sessao.ao_liberar("Começo normal. ")
        self.b._deliver_result({"text": "🔒 Conteúdo bloqueado.", "pending_action": None, "blocked": True}, sessao)
        self.assertIn(("cancelar",), self.fala_log)

    def test_sessao_sem_nenhuma_frase_liberada_usa_o_caminho_normal(self):
        sessao = self.b._abrir_sessao_stream()
        self.b._deliver_result({"text": "Vou olhar. Ok.", "pending_action": None, "blocked": False}, sessao)
        self.assertIn(("voz", "Vou olhar. Ok."), self.ordem)

    def test_pausa_total_cancela_a_sessao(self):
        sessao = self.b._abrir_sessao_stream()
        sessao.ao_liberar("Começou a falar. ")
        with mock.patch("brain.zenith_headless.pausa.ativo", lambda: True):
            self.b._deliver_result({"text": "Começou a falar. E continuou.", "pending_action": None, "blocked": False}, sessao)
        self.assertIn(("cancelar",), self.fala_log)

    def test_streaming_desligado_nao_cria_sessao(self):
        self.b.settings.update({"streaming_real": False})
        self.assertIsNone(self.b._abrir_sessao_stream())
        self.b.settings.update({"streaming_real": True, "response_streaming": False})
        self.assertIsNone(self.b._abrir_sessao_stream())

    def test_sem_voz_a_sessao_so_manda_texto(self):
        self.b.settings.update({"voice_enabled": False})
        sessao = self.b._abrir_sessao_stream()
        sessao.ao_liberar("Só texto aqui. ")
        self.assertEqual(self.fala_log, [])
        self.assertEqual(self._texto_do_chat(), "Só texto aqui. ")


class TestFalaEmPedacos(unittest.TestCase):
    def setUp(self):
        from brain import zenith_interaction as I
        self.I = I
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tocados = []

        class Musica:
            def __init__(m):
                m.arquivo, m.polls = None, 0
            def load(m, arq): m.arquivo = arq
            def set_volume(m, v): pass
            def play(m):
                m.polls = 3
                self.tocados.append(Path(m.arquivo).read_text())
            def get_busy(m):
                m.polls -= 1
                return m.polls > 0
            def unload(m): pass
            def stop(m): m.polls = 0

        self.musica = Musica()
        fake_pygame = mock.MagicMock()
        fake_pygame.mixer.music = self.musica
        for alvo, valor in (("brain.zenith_interaction.pygame", fake_pygame),
                            ("brain.zenith_interaction.TEMP_DIR", Path(self.tmp.name))):
            p = mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

        class Voz:
            current_volume = 0.8
            def _limpar_para_voz(s, t): return t.strip()
            _dividir_em_frases = staticmethod(I.ZenithInteraction._dividir_em_frases)
            async def _gerar_audio_base(s, texto, caminho, expressao="neutral"):
                Path(caminho).write_text(texto)
                return caminho
            def _aplicar_rvc(s, caminho): return caminho
        self.voz = Voz()

    def _esperar(self, cond, timeout=5):
        fim = time.time() + timeout
        while time.time() < fim and not cond():
            time.sleep(0.01)
        return cond()

    def test_toca_todas_as_frases_na_ordem(self):
        eventos = []
        f = self.I.FalaStream(self.voz, on_start=lambda: eventos.append("start"), on_end=lambda: eventos.append("end"))
        frases = ["Primeira frase bem comprida aqui.", "Segunda frase bem comprida aqui.",
                  "Terceira frase bem comprida aqui.", "Quarta frase bem comprida aqui."]
        for frase in frases:
            f.add(frase)
        f.fim()
        self.assertTrue(self._esperar(lambda: "end" in eventos))
        self.assertEqual(self.tocados, frases)          # NENHUMA frase do meio é pulada (o queue() do pygame pulava)
        self.assertEqual(eventos, ["start", "end"])

    def test_primeira_frase_curta_sai_logo(self):
        f = self.I.FalaStream(self.voz)
        f.add("Claro!")
        self.assertTrue(self._esperar(lambda: self.tocados == ["Claro!"]))      # não espera juntar 24 caracteres
        f.cancelar()

    def test_cancelar_corta_e_ainda_avisa_o_fim(self):
        eventos = []
        f = self.I.FalaStream(self.voz, on_end=lambda: eventos.append("end"))
        f.add("Uma frase razoavelmente longa pra tocar. ")
        f.cancelar()
        self.assertTrue(self._esperar(lambda: "end" in eventos))

    def test_cancelar_silencioso_nao_avisa_o_fim(self):
        eventos = []
        f = self.I.FalaStream(self.voz, on_end=lambda: eventos.append("end"))
        f.cancelar(silencioso=True)
        time.sleep(0.3)
        self.assertEqual(eventos, [])

    def test_primeira_frase_longa_e_quebrada_na_virgula(self):
        longa = "Olha só, eu pensei bastante sobre isso e acho que a melhor saída, de verdade, é testar primeiro com calma antes de ligar tudo."
        partes = self.I.ZenithInteraction._dividir_em_frases(longa)
        self.assertGreaterEqual(len(partes), 2)
        self.assertTrue(len(partes[0]) < 90)
        self.assertEqual(" ".join(partes), longa)

    def test_nova_fala_corta_a_anterior(self):
        from brain.zenith_interaction import ZenithInteraction
        z = object.__new__(ZenithInteraction)
        z._ready = True
        z.current_volume = 0.8
        z._limpar_para_voz = self.voz._limpar_para_voz
        z._dividir_em_frases = self.voz._dividir_em_frases
        z._gerar_audio_base = self.voz._gerar_audio_base
        z._aplicar_rvc = self.voz._aplicar_rvc
        a = z.falar_stream_iniciar()
        b = z.falar_stream_iniciar()
        self.assertTrue(a._cancelado.is_set())
        self.assertFalse(b._cancelado.is_set())
        z.parar_de_falar()
        self.assertTrue(b._cancelado.is_set())


class TestHabilidades(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(H, "SKILLS_DIR", Path(self.tmp.name) / "skills")
        p.start()
        self.addCleanup(p.stop)

    TAG = ('<criar_habilidade nome="Piston-Teste" descricao="estende e recolhe o pistão">\n'
           '```python\ndef rodar(args: str = "") -> str:\n    return "movendo: " + (args or "nada")\n```\n</criar_habilidade>')

    def test_parse_criar_ok_e_normaliza_o_nome(self):
        h = H.parse_criar(self.TAG)
        self.assertEqual(h["nome"], "piston_teste")
        self.assertIn("def rodar", h["codigo"])
        self.assertNotIn("```", h["codigo"])

    def test_parse_criar_recusa_problemas(self):
        casos = {
            "sem def rodar": '<criar_habilidade nome="x1" descricao="d">print(1)</criar_habilidade>',
            "sintaxe": '<criar_habilidade nome="x1" descricao="d">def rodar(:\n</criar_habilidade>',
            "sem descricao": '<criar_habilidade nome="x1">def rodar(a=""): return "1"</criar_habilidade>',
            "nome ruim": '<criar_habilidade nome="1abc" descricao="d">def rodar(a=""): return "1"</criar_habilidade>',
            "vazio": '<criar_habilidade nome="x1" descricao="d">  </criar_habilidade>',
        }
        for rotulo, tag in casos.items():
            with self.assertRaises(H.ErroHabilidade, msg=rotulo):
                H.parse_criar(tag)

    def test_salvar_listar_ler_apagar(self):
        msg = H.salvar(self.TAG)
        self.assertIn("criada", msg)
        self.assertTrue(H.existe("piston_teste"))
        itens = H.listar()
        self.assertEqual(itens[0]["nome"], "piston_teste")
        self.assertIn("pistão", itens[0]["descricao"])
        self.assertIn("def rodar", H.ler_codigo("piston_teste"))
        self.assertIn("atualizada", H.salvar(self.TAG))
        self.assertTrue(H.apagar("piston_teste"))
        self.assertFalse(H.existe("piston_teste"))

    def test_analise_mostra_o_que_o_codigo_toca(self):
        achados = H.analisar_codigo("import serial, requests\nimport os\nos.system('dir')\nopen('a','w')")
        texto = " ".join(achados)
        for trecho in ("seriais", "internet", "comandos do sistema", "arquivos"):
            self.assertIn(trecho, texto)
        self.assertEqual(H.analisar_codigo("def rodar(a=''):\n    return str(2+2)"), [])

    def test_preview_avisa_se_substitui_e_mostra_o_codigo(self):
        H.salvar(self.TAG)
        pv = H.preview_criar(self.TAG)
        self.assertIn("SUBSTITUI", pv)
        self.assertIn("def rodar", pv)
        self.assertIn("Nada sensível", pv)

    def test_wrapper_roda_a_habilidade_de_verdade(self):
        import subprocess
        H.salvar(self.TAG)
        wrapper = H.montar_wrapper("piston_teste", "estender 5cm")
        r = subprocess.run([sys.executable, "-c", wrapper], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("movendo: estender 5cm", r.stdout)

    def test_wrapper_mostra_o_erro_da_habilidade(self):
        import subprocess
        H.salvar('<criar_habilidade nome="quebra" descricao="falha">def rodar(a=""):\n    return 1/0</criar_habilidade>')
        r = subprocess.run([sys.executable, "-c", H.montar_wrapper("quebra", "")], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ZeroDivisionError", r.stderr)

    def test_args_com_aspas_nao_quebram_o_wrapper(self):
        import subprocess
        H.salvar(self.TAG)
        r = subprocess.run([sys.executable, "-c", H.montar_wrapper("piston_teste", "he said \"oi\" e 'tchau'\n; import os")],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("he said", r.stdout)

    def test_prompt_lista_as_habilidades(self):
        self.assertIn("ainda não criou nenhuma", H.bloco_prompt(FakeSettings()))
        H.salvar(self.TAG)
        bloco = H.bloco_prompt(FakeSettings())
        self.assertIn("piston_teste", bloco)
        self.assertIn("<criar_habilidade", bloco)
        self.assertEqual(H.bloco_prompt(FakeSettings(habilidades_ativas=False)), "")

    def test_confianca_e_por_habilidade(self):
        cfg = FakeSettings(habilidades_confiaveis=["a_boa"])
        self.assertTrue(H.eh_confiavel(cfg, "a_boa"))
        self.assertFalse(H.eh_confiavel(cfg, "outra"))

    def test_limite_de_habilidades(self):
        with mock.patch.object(H, "MAX_HABILIDADES", 1):
            H.salvar(self.TAG)
            msg = H.salvar('<criar_habilidade nome="segunda" descricao="d">def rodar(a=""): return "1"</criar_habilidade>')
        self.assertIn("máximo", msg)

    def test_comandos(self):
        cfg = FakeSettings()
        H.salvar(self.TAG)
        r = cmd.tratar("/habilidades", {"settings": cfg})
        self.assertIn("piston_teste", r["resposta"])
        r = cmd.tratar("/habilidade confiar piston_teste", {"settings": cfg})
        self.assertEqual(cfg.get("habilidades_confiaveis"), ["piston_teste"])
        cmd.tratar("/habilidade desconfiar piston_teste", {"settings": cfg})
        self.assertEqual(cfg.get("habilidades_confiaveis"), [])
        self.assertIn("def rodar", cmd.tratar("/habilidade ver piston_teste", {"settings": cfg})["resposta"])
        cmd.tratar("/habilidade confiar piston_teste", {"settings": cfg})
        cmd.tratar("/habilidade apagar piston_teste", {"settings": cfg})
        self.assertFalse(H.existe("piston_teste"))
        self.assertEqual(cfg.get("habilidades_confiaveis"), [])         # apagar também tira a confiança
        self.assertIn("Não existe", cmd.tratar("/habilidade ver nada", {"settings": cfg})["resposta"])


class TestHabilidadesNoCerebro(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        from brain.zenith_executor import ZenithExecutor
        from brain.zenith_gatekeeper import DeterministicGuard
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(H, "SKILLS_DIR", Path(self.tmp.name) / "skills")
        p.start()
        self.addCleanup(p.stop)
        p2 = mock.patch("brain.zenith_executor.TEMP_DIR", Path(self.tmp.name) / "temp")     # não toca a pasta temp/ do projeto
        p2.start()
        self.addCleanup(p2.stop)
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(active_ai="openai", habilidades_confiaveis=[], modo_atual="normal")
        core.executor = ZenithExecutor()
        core.guard = DeterministicGuard("Anderson")
        core._midias = []
        self.core = core

    def test_etiquetas_novas_existem_e_viram_acao_pendente(self):
        from brain import zenith_core
        for k in ("skill_create", "skill_run", "observe"):
            self.assertIn(k, zenith_core.ACTION_TAGS)
        pend = self.core._extract_pending_action(TestHabilidades.TAG)
        self.assertEqual(pend.kind, "skill_create")

    def test_criar_grava_so_na_aprovacao_e_bloqueia_codigo_perigoso(self):
        ok = self.core.approve_action(self.core.executor.create_pending("skill_create", TestHabilidades.TAG, "d"))
        self.assertIn("criada", ok)
        perigosa = ('<criar_habilidade nome="ruim" descricao="apaga tudo">import shutil\n'
                    'def rodar(a=""):\n    shutil.rmtree("C:\\\\Windows")\n    return "x"</criar_habilidade>')
        veto = self.core.approve_action(self.core.executor.create_pending("skill_create", perigosa, "d"))
        self.assertFalse(H.existe("ruim"))
        self.assertTrue(veto)

    def test_usar_executa_e_relê_o_arquivo_contra_a_lista_negra(self):
        H.salvar(TestHabilidades.TAG)
        tag = '<usar_habilidade nome="piston_teste">estender</usar_habilidade>'
        saida = self.core.approve_action(self.core.executor.create_pending("skill_run", tag, "d"))
        self.assertIn("movendo: estender", saida)
        # alguém editou o arquivo depois da aprovação de criação: a lista negra pega na hora de rodar
        arq = H.SKILLS_DIR / "piston_teste.py"
        arq.write_text(arq.read_text(encoding="utf-8") + "\nimport shutil\nshutil.rmtree('C:\\\\Windows')\n", encoding="utf-8")
        saida2 = self.core.approve_action(self.core.executor.create_pending("skill_run", tag, "d"))
        self.assertNotIn("movendo", saida2)

    def test_usar_habilidade_inexistente_explica(self):
        tag = '<usar_habilidade nome="fantasma">x</usar_habilidade>'
        self.assertIn("❌", self.core.approve_action(self.core.executor.create_pending("skill_run", tag, "d")))

    def test_preview_das_acoes_novas(self):
        pv = self.core.executor.create_pending("skill_create", TestHabilidades.TAG, "d").preview()
        self.assertIn("CRIAR HABILIDADE", pv)
        obs = self.core.executor.create_pending("observe", O.montar_tag("camera", 20, 10, "montar circuito"), "d").preview()
        self.assertIn("OBSERVAR AO VIVO", obs)
        self.assertIn("Privacidade", obs)


# ======================================================================
class TestComandosAutomaticos(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(modo_atual="normal", comandos_auto=True, contexto_modo="max")
        self.core = core

    def test_modo_por_etiqueta_muda_o_modo(self):
        saidas = self.core._rodar_comandos_auto("Vamos estudar! <comando>modo tutor</comando>")
        self.assertEqual([s["nome"] for s in saidas], ["modo"])
        self.assertEqual(self.core.settings.get("modo_atual"), "tutor")

    def test_so_a_lista_permitida_roda(self):
        for perigoso in ("parar_programa", "observar camera", "esquecer 3", "diario", "lembrar 10:00 x", "habilidade apagar x"):
            self.assertEqual(self.core._rodar_comandos_auto(f"<comando>{perigoso}</comando>"), [], perigoso)
        self.assertEqual(self.core._rodar_comandos_auto("<comando>biblia apagar x</comando>"), [])

    def test_desligado_nas_configuracoes(self):
        self.core.settings.update({"comandos_auto": False})
        self.assertEqual(self.core._rodar_comandos_auto("<comando>modo tutor</comando>"), [])
        self.assertEqual(self.core.settings.get("modo_atual"), "normal")

    def test_limite_de_dois_por_resposta(self):
        r = self.core._rodar_comandos_auto("<comando>modo tutor</comando><comando>modo estudo</comando><comando>modo lab</comando>")
        self.assertEqual(len(r), 2)

    def test_etiqueta_some_do_texto_exibido(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        self.assertEqual(core._remove_tags("Beleza <comando>contexto</comando> segue!"), "Beleza  segue!")


# ======================================================================
class TestObservar(unittest.TestCase):
    def test_parse_e_limites(self):
        o = O.parse('<observar tipo="tela" intervalo="2" minutos="500">jogando</observar>')
        self.assertEqual(o["tipo"], "screen")
        self.assertEqual(o["intervalo"], O.INTERVALO_MIN)        # mínimo 8 s
        self.assertEqual(o["minutos"], O.MINUTOS_MAX)            # máximo 60 min
        self.assertEqual(o["motivo"], "jogando")
        self.assertEqual(O.parse('<observar>x</observar>')["tipo"], "camera")
        with self.assertRaises(ValueError):
            O.parse('<observar tipo="geladeira">x</observar>')

    def test_montar_tag_vai_e_volta(self):
        o = O.parse(O.montar_tag("camera", 15, 10, "ver o circuito"))
        self.assertEqual((o["tipo"], o["intervalo"], o["minutos"], o["motivo"]), ("camera", 15, 10, "ver o circuito"))

    def test_preview_tem_aviso_de_privacidade_e_como_parar(self):
        pv = O.preview_text(O.montar_tag("camera", 20, 15, "x"))
        for t in ("Privacidade", "/parar_observacao", "/pausar", "Nada fica salvo"):
            self.assertIn(t.split()[0], pv)

    def _png(self, cor):
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (64, 64), cor).save(b, "PNG")
        return b.getvalue()

    def test_diferenca_de_imagens(self):
        a, b = self._png((10, 10, 10)), self._png((240, 240, 240))
        self.assertLess(O.diferenca(a, a), 1)
        self.assertGreater(O.diferenca(a, b), 100)
        self.assertEqual(O.diferenca(None, a), 255.0)
        self.assertEqual(O.diferenca(b"lixo", a), 255.0)

    def _observador(self, imagens, respostas, minutos=1, erro_captura=None):
        pub, estados = [], []
        seq = iter(imagens)
        resp = iter(respostas)
        chamadas = {"comentar": 0}

        def capturar(tipo):
            if erro_captura:
                return None, erro_captura
            try:
                return next(seq), None
            except StopIteration:
                return imagens[-1], None

        def comentar(tipo, img, motivo, anterior):
            chamadas["comentar"] += 1
            return next(resp, "[SEM_NOVIDADE]")

        relogio = {"t": 0.0}

        def dormir(s):
            relogio["t"] += s

        obs = O.Observador(capturar, comentar, pub.append, lambda *a: estados.append(a),
                           relogio=lambda: relogio["t"], dormir=dormir)
        return obs, pub, estados, chamadas

    def test_laco_publica_so_o_que_importa_e_economiza_chamadas(self):
        claro, escuro = self._png((250, 250, 250)), self._png((5, 5, 5))
        obs, pub, estados, chamadas = self._observador([claro, claro, claro, escuro, escuro],
                                                       ["O fio vermelho está no pino errado.", "[SEM_NOVIDADE]"])
        obs.iniciar("camera", 20, 1, "montar o circuito")
        obs._thread.join(timeout=10)
        self.assertEqual(pub, ["O fio vermelho está no pino errado."])
        self.assertLess(chamadas["comentar"], obs.fotos)                    # fotos iguais NÃO chamam a IA
        self.assertEqual(estados[0][0], True)
        self.assertEqual(estados[-1][0], False)
        self.assertFalse(obs.ativo)

    def test_para_sozinho_depois_do_tempo(self):
        obs, pub, estados, _ = self._observador([self._png((9, 9, 9))], [], minutos=1)
        obs.iniciar("screen", 20, 1)
        obs._thread.join(timeout=10)
        self.assertIn("passaram", obs.motivo_parada)

    def test_falhas_seguidas_de_captura_param_com_motivo(self):
        obs, pub, estados, _ = self._observador([], [], erro_captura="Nenhuma câmera encontrada")
        obs.iniciar("camera", 10, 5)
        obs._thread.join(timeout=10)
        self.assertIn("Nenhuma câmera", obs.motivo_parada)
        self.assertEqual(pub, [])

    def test_parar_a_qualquer_momento(self):
        parar_evt = threading.Event()
        obs = O.Observador(lambda t: (b"x", None), lambda *a: "[SEM_NOVIDADE]", lambda t: None,
                           dormir=lambda s: parar_evt.wait(0.05))
        obs.iniciar("camera", 20, 30)
        self.assertTrue(obs.ativo)
        self.assertTrue(obs.parar("teste"))
        obs._thread.join(timeout=5)
        self.assertFalse(obs.ativo)
        self.assertEqual(obs.motivo_parada, "teste")
        self.assertFalse(obs.parar())                                       # já parado

    def test_prompt_de_observacao_leva_conversa_recente_e_a_regra_do_silencio(self):
        pr = O.prompt_de_observacao("a câmera", "Anderson", "montar o circuito", "o fio está solto",
                                    "Ele: vou ligar o ESP32\nVocê: ok, começa pelo GND")
        for t in ("montar o circuito", "o fio está solto", "começa pelo GND", O.SEM_NOVIDADE, "NÃO repita"):
            self.assertIn(t, pr)

    def test_observacao_nao_manda_o_historico_inteiro_a_cada_foto(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings()
        core.conv_id = "c1"
        core._hist_depth = 0
        vistos = {}
        core._call_provider = lambda prompt, img=None, mime=None: (vistos.update(depth=core._hist_depth, prompt=prompt) or "[SEM_NOVIDADE]")
        conversa = {"messages": [{"sender": "user", "text": "vou montar o circuito"}, {"sender": "ai", "text": "bora"}]}
        with mock.patch("brain.zenith_history.get_conversation", return_value=conversa):
            self.assertEqual(core.observar_comentar("camera", b"x", "circuito", ""), "[SEM_NOVIDADE]")
        self.assertEqual(vistos["depth"], 0)                       # sem _com_historico
        self.assertIn("vou montar o circuito", vistos["prompt"])

    def test_comandos_de_observacao(self):
        cfg = FakeSettings(observar_intervalo_s=20, observar_max_minutos=15)
        r = cmd.tratar("/observar tela 30 5 jogando wow", {"settings": cfg})
        self.assertEqual(r["acao"], "observar")
        self.assertEqual(r["args"], {"tipo": "screen", "intervalo": 30, "minutos": 5, "motivo": "jogando wow"})
        r = cmd.tratar("/observar", {"settings": cfg})
        self.assertEqual((r["args"]["tipo"], r["args"]["intervalo"], r["args"]["minutos"]), ("camera", 20, 15))
        self.assertEqual(cmd.tratar("/parar_observacao", {"settings": cfg})["acao"], "parar_observacao")

    def test_pausa_total_bloqueia_observar(self):
        from brain import zenith_pausa as pausa
        pausa.pausar("teste")
        try:
            r = cmd.tratar("/observar camera", {"settings": FakeSettings()})
            self.assertNotEqual(r.get("acao"), "observar")
        finally:
            pausa.retomar()


# ======================================================================
class _Col:
    """Coleção Chroma de mentira: guarda (id, doc, meta) e responde query/get por tipo."""
    def __init__(self, itens):
        self.itens = itens                      # [(doc, meta, distancia)]

    def count(self):
        return len(self.itens)

    def get(self, where=None, include=None):
        sel = [i for i in self.itens if not where or i[1].get("type") == where.get("type")]
        return {"documents": [i[0] for i in sel], "metadatas": [i[1] for i in sel]}

    def query(self, query_texts, n_results, where=None, include=None):
        sel = sorted([i for i in self.itens if not where or i[1].get("type") == where.get("type")], key=lambda i: i[2])[:n_results]
        return {"documents": [[i[0] for i in sel]], "distances": [[i[2] for i in sel]], "metadatas": [[i[1] for i in sel]]}

    def add(self, **kw):
        self.itens.append((kw["documents"][0], kw["metadatas"][0], 0.0))


class TestMemoria(unittest.TestCase):
    def memoria(self, itens, **cfg):
        from brain.zenith_memory import ZenithMemory
        m = object.__new__(ZenithMemory)
        m.settings = FakeSettings(**cfg)
        m.collection = _Col(itens)
        return m

    def test_recall_filtra_o_que_esta_longe_e_prioriza_fatos(self):
        m = self.memoria([
            ("Fulano estuda Automação Industrial no curso técnico", {"type": "fact"}, 0.9),
            ("papo sobre pizza ontem", {"type": "chat_raw"}, 1.9),                    # longe demais: some
            ("resumo: ele montou um circuito com ESP32", {"type": "chat_summary"}, 1.0),
            ("Anderson: e o pistão? Zenith: ligamos na ponte H", {"type": "chat_raw"}, 1.1),
        ])
        r = m.recall("qual o meu curso?")
        self.assertIn("Automação Industrial", r)
        self.assertIn("ESP32", r)
        self.assertNotIn("pizza", r)
        self.assertEqual(r.splitlines()[0], "Fulano estuda Automação Industrial no curso técnico")   # fato primeiro

    def test_recall_faz_uma_unica_consulta(self):
        """v24: um cálculo de embedding só (na v23 eram três consultas, e isso pesava em PC lento)."""
        m = self.memoria([("fato", {"type": "fact"}, 0.5), ("papo", {"type": "chat_raw"}, 0.6)])
        m.collection.query = mock.MagicMock(wraps=m.collection.query)
        m.recall("qualquer coisa")
        self.assertEqual(m.collection.query.call_count, 1)

    def test_fato_ganha_bonus_sobre_conversa_crua_um_pouco_mais_perto(self):
        m = self.memoria([("conversa antiga", {"type": "chat_raw"}, 1.0), ("fato importante", {"type": "fact"}, 1.1)])
        self.assertEqual(m.recall("x").splitlines()[0], "fato importante")

    def test_recall_respeita_o_limite_configurado(self):
        itens = [(f"fato {i}", {"type": "fact"}, 0.5 + i / 100) for i in range(10)]
        self.assertEqual(len(self.memoria(itens, memoria_recall_n=3).recall("x").splitlines()), 3)

    def test_recall_sem_memoria_devolve_vazio(self):
        self.assertEqual(self.memoria([]).recall("x"), "")

    def test_fatos_fixos_mais_recentes_primeiro_e_com_limite(self):
        m = self.memoria([("fato velho", {"type": "fact", "timestamp": "2026-01-01"}, 0),
                          ("fato novo", {"type": "fact", "timestamp": "2026-10-01"}, 0),
                          ("conversa", {"type": "chat_raw", "timestamp": "2026-10-02"}, 0)])
        self.assertEqual(m.fatos_fixos().splitlines(), ["- fato novo", "- fato velho"])
        self.assertEqual(m.fatos_fixos(max_chars=15).splitlines(), ["- fato novo"])
        self.assertEqual(self.memoria([("x", {"type": "fact"}, 0)], memoria_fatos_fixos_chars=0).fatos_fixos(), "")

    def test_save_fact_nao_duplica(self):
        m = self.memoria([("Anderson gosta de café", {"type": "fact"}, 0)])
        m.save_fact("  anderson   GOSTA de café ")
        self.assertEqual(m.collection.count(), 1)
        m.save_fact("Anderson mora em São Paulo")
        self.assertEqual(m.collection.count(), 2)

    def test_fatos_entram_no_prompt_do_sistema(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(modo_atual="normal")
        core.memory = type("M", (), {"fatos_fixos": lambda self: "- estuda Automação Industrial"})()
        self.assertIn("ESTUDA AUTOMAÇÃO", core._bloco_fatos("Anderson").upper())
        core2 = object.__new__(ZenithCore)
        core2.memory = type("M", (), {"fatos_fixos": lambda self: ""})()
        self.assertEqual(core2._bloco_fatos("Anderson"), "")


# ======================================================================
class TestPromptEModos(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(modo_atual="normal", habilidades_ativas=True)
        core.memory = type("M", (), {"fatos_fixos": lambda self: ""})()
        self.prompt = core._build_system_prompt()

    def test_regras_contra_pedir_permissao_em_texto(self):
        for t in ("A APROVAÇÃO É DO ZENITH", "NUNCA escreva", "ESCOLHA A FERRAMENTA CERTA", "autorretrato",
                  "<criar_habilidade", "<usar_habilidade"):
            self.assertIn(t, self.prompt)
        self.assertNotIn("ou pergunte em uma frase se ele prefere", self.prompt)    # a regra velha que induzia o "você aprova?"

    def test_modos_novos(self):
        for nome in ("quiz", "debate", "jogo", "eletronica"):
            self.assertEqual(modos.normalizar(nome), nome)
            self.assertIn("MODO", modos.prompt_extra(nome))
        self.assertEqual(modos.normalizar("eletrônica"), "eletronica")
        self.assertEqual(modos.normalizar("bancada"), "lab")          # o alias antigo continua valendo
        self.assertEqual(modos.normalizar("Kahoot"), "quiz")
        self.assertIn("SEGURANÇA PRIMEIRO", modos.prompt_extra("eletronica"))

    def test_modo_nunca_relaxa_pilares(self):
        for nome in ("quiz", "debate", "jogo", "eletronica"):
            self.assertIn("jamais relaxa os pilares", modos.prompt_extra(nome))

    def test_validador_conhece_as_etiquetas_novas(self):
        from brain import zenith_conhecimento as K
        for t in ("criar_habilidade", "usar_habilidade", "observar", "comando"):
            self.assertIn(t, K._TAGS_TODAS)

    def test_biblia_gerada_esta_em_dia(self):
        from brain import zenith_biblia as BI
        self.assertEqual(ler("BIBLIA_ZENITH.md").replace("\r\n", "\n").strip(), BI.gerar_markdown().replace("\r\n", "\n").strip())


class TestAtitude(unittest.TestCase):
    """O erro REAL do print do Anderson: pediu aprovação em texto, citou uma etiqueta vazia e disse que não tem corpo."""
    RESPOSTA_DO_PRINT = (
        "Ah, que interessante! Você quer que eu me desenhe e depois use a câmera. Desenhar-me... hmm, como uma IA, eu não tenho "
        "uma forma física, mas posso tentar. Para que eu possa dar uma olhada na sua câmera, eu preciso da sua aprovação "
        "explícita. Assim que você aprovar, eu vou inserir a tag `` na minha resposta.")
    PEDIDO = "Cria um desenho de você mesmo e depois dá uma olhada na minha câmera"

    def test_pega_o_erro_do_print(self):
        from brain import zenith_conhecimento as K
        probs = K.problemas_de_atitude(self.RESPOSTA_DO_PRINT, self.PEDIDO)
        self.assertEqual(len(probs), 2)
        self.assertIn("TEXTO", probs[0])
        self.assertIn("desculpa", probs[1])

    def test_nao_dispara_quando_ela_usou_a_ferramenta(self):
        from brain import zenith_conhecimento as K
        self.assertEqual(K.problemas_de_atitude("Vou olhar! <ver_camera>mesa</ver_camera> preciso da sua aprovação", "olha"), [])

    def test_nao_dispara_quando_a_pergunta_e_sobre_as_regras(self):
        from brain import zenith_conhecimento as K
        self.assertEqual(K.problemas_de_atitude(self.RESPOSTA_DO_PRINT, "como funciona a aprovação das ações?"), [])

    def test_conversa_normal_nao_dispara(self):
        from brain import zenith_conhecimento as K
        for texto in ("Bom dia! Como foi a prova de física?", "A derivada de x² é 2x.", "Posso te ajudar com isso, vamos lá!"):
            self.assertEqual(K.problemas_de_atitude(texto, "oi"), [], texto)

    def test_cerebro_pede_segunda_tentativa_e_usa_a_corrigida(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(biblia_validador=True, atitude_validador=True)
        core.ia_ativa = "gemini"
        core._hist_depth = 0
        pedidos = []

        def chamar(prompt, *a, **k):
            pedidos.append(prompt)
            return "Vou desenhar! <executar_python>from brain.zenith_img import autorretrato\nautorretrato()</executar_python>"
        core._call_provider = chamar
        core._com_historico = lambda: __import__("contextlib").nullcontext()
        out = core._validar_e_corrigir(self.RESPOSTA_DO_PRINT, self.PEDIDO)
        self.assertIn("<executar_python>", out)
        self.assertEqual(len(pedidos), 1)
        self.assertIn("atitude", pedidos[0])
        self.assertIn("autorretrato", pedidos[0])

    def test_pode_desligar(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(biblia_validador=True, atitude_validador=False)
        core.ia_ativa = "gemini"
        core._call_provider = lambda *a, **k: self.fail("não deveria chamar a IA")
        self.assertEqual(core._validar_e_corrigir(self.RESPOSTA_DO_PRINT, self.PEDIDO), self.RESPOSTA_DO_PRINT)


class TestComandosNovos(unittest.TestCase):
    def test_modelo(self):
        cfg = FakeSettings(gemini_modelo="gemini-3.5-flash")
        self.assertIn("gemini-3.5-flash", cmd.tratar("/modelo", {"settings": cfg})["resposta"])
        cmd.tratar("/modelo gemini gemini-3.1-pro-preview", {"settings": cfg})
        self.assertEqual(cfg.get("gemini_modelo"), "gemini-3.1-pro-preview")
        cmd.tratar("/modelo gemini-3.6-flash", {"settings": cfg})
        self.assertEqual(cfg.get("gemini_modelo"), "gemini-3.6-flash")
        cmd.tratar("/modelo auto", {"settings": cfg})
        self.assertEqual(cfg.get("gemini_modelo"), "gemini-3.5-flash")
        self.assertIn("inválido", cmd.tratar("/modelo gemini rm -rf", {"settings": cfg})["resposta"])
        self.assertEqual(cfg.get("gemini_modelo"), "gemini-3.5-flash")
        self.assertEqual(cmd.tratar("/modelos", {"settings": cfg})["acao"], "listar_modelos")

    def test_fundo_avatar(self):
        cfg = FakeSettings()
        r = cmd.tratar("/fundo_avatar solido #101830", {"settings": cfg})
        self.assertEqual(r["acao"], "fundo_avatar")
        self.assertEqual((cfg.get("avatar_fundo_modo"), cfg.get("avatar_fundo_cor")), ("solido", "#101830"))
        cmd.tratar("/fundo_avatar chroma", {"settings": cfg})
        self.assertEqual(cfg.get("avatar_fundo_modo"), "chroma")
        cmd.tratar("/fundo_avatar preto", {"settings": cfg})
        self.assertEqual(cfg.get("avatar_fundo_modo"), "solido")
        self.assertIn("Use:", cmd.tratar("/fundo_avatar xyz", {"settings": cfg})["resposta"])
        self.assertNotEqual(cfg.get("avatar_fundo_modo"), "xyz")
        cmd.tratar("/fundo_avatar solido #zzz", {"settings": cfg})
        self.assertEqual(cfg.get("avatar_fundo_cor"), "#101830")           # cor inválida é ignorada

    def test_ajuda_lista_os_comandos_novos(self):
        ajuda = cmd.tratar("/ajuda", {})["resposta"]
        for c in ("/modelos", "/habilidades", "/observar", "/parar_observacao", "/fundo_avatar", "/velocidade", "quiz|debate|jogo|eletronica"):
            self.assertIn(c, ajuda)


class TestConfiguracoesEImagem(unittest.TestCase):
    def test_padroes_novos(self):
        from brain.zenith_settings import DEFAULT_SETTINGS as d
        self.assertEqual(d["gemini_modelo"], "gemini-3.5-flash")
        self.assertGreaterEqual(d["saida_max_tokens"], 16384)
        self.assertEqual(d["avatar_fundo_modo"], "auto")
        self.assertEqual(d["habilidades_confiaveis"], [])
        self.assertGreaterEqual(d["observar_intervalo_s"], O.INTERVALO_MIN)
        self.assertEqual(d["thinking_mode"], "pensante")

    def test_autorretrato_gera_png_quadrado(self):
        from brain import zenith_img
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "a.png"
            with mock.patch.object(zenith_img, "salvar", lambda im, nome, *a, **k: (im.save(destino), str(destino))[1]):
                caminho = zenith_img.autorretrato("Zenith", tamanho=500)
            from PIL import Image
            with Image.open(caminho) as im:
                self.assertEqual(im.size, (500, 500))

    def test_gatekeeper_aplica_lista_negra_nas_habilidades(self):
        from brain.zenith_gatekeeper import DeterministicGuard
        g = DeterministicGuard("Anderson")
        self.assertTrue(g.check_action("skill_create", "import shutil\nshutil.rmtree('C:\\\\')"))
        self.assertFalse(g.check_action("skill_create", "def rodar(a=''):\n    return '1'"))


class TestContratosComOGodot(unittest.TestCase):
    """O Godot não roda aqui; estes testes só garantem que as pontas combinam (nome de ação, sinal, função)."""
    def test_conector_tem_os_sinais_e_acoes_novas(self):
        t = ler("body/zenith/brain_connector.gd")
        for s in ("signal avatar_fundo(modo, cor)", "signal observando(ativo, tipo, info)", '"avatar_fundo":', '"observando":'):
            self.assertIn(s, t)

    def test_corpo_aplica_o_fundo_nos_tres_modos(self):
        t = ler("body/zenith/akira_body.gd")
        for s in ("_fundo_carregar_local()", "func _fundo_aplicar()", "is_window_transparency_available",
                  "WINDOW_FLAG_TRANSPARENT, transp", "transparent_bg = transp", "Color(0.0, 1.0, 0.0, 1.0)",
                  'connector.avatar_fundo.connect(_on_avatar_fundo)', 'connector.observando.connect(_on_observando)',
                  "OBSERVANDO"):
            self.assertIn(s, t)
        # o modo salvo é lido ANTES de qualquer quadro (logo depois das flags da janela no _ready)
        self.assertLess(t.index("WINDOW_FLAG_MOUSE_PASSTHROUGH, true)"), t.index("_fundo_carregar_local()   #"))

    def test_chat_nao_cria_um_balao_por_frase(self):
        t = ler("body/zenith/ui_manager.gd")
        for s in ("var _stream_criando", "_stream_buffer", "_stream_done_pendente"):
            self.assertIn(s, t)
        self.assertIn("if _stream_criando:", t)

    def test_botao_parar_observacao_existe_e_manda_o_comando(self):
        t = ler("body/zenith/ui_manager.gd")
        self.assertIn("Parar observação", t)
        self.assertIn('"/parar_observacao"', t)
        self.assertIn("brain.observando.connect(_on_observando_ui)", t)

    def test_cerebro_manda_as_acoes_que_o_godot_espera(self):
        t = ler("brain/zenith_headless.py")
        for s in ('"action": "avatar_fundo"', '"action": "observando"'):
            self.assertIn(s, t)

    def test_aviso_de_primeira_vez_em_outro_computador(self):
        t = ler("brain/zenith_headless.py")
        self.assertIn("/fundo_avatar solido", t)
        self.assertIn("platform.node()", t)


if __name__ == "__main__":
    unittest.main()
