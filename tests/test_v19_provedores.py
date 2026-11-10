"""
Testes do v19 — painel "IAs & Chaves" de uma IA por vez + modo pendrive sem URLs.

Cobre (tudo Python; nada aqui prova o painel em si, que é Godot e só se vê na máquina do Anderson):
  * catálogo opcional (ausente / inválido / saneado) e a lista unificada de IAs;
  * edição pura (salvar / adicionar / remover) no mesmo formato de settings.json de sempre;
  * o zenith_core sem URL de marca escrita no código (endereço vem do catálogo);
  * os handlers novos do Cérebro (save_ai_entry / remove_ai_entry);
  * o prepare_pendrive.py (limpeza dos dados do v18 + varredura de chave/caminho/endereço);
  * checagens estáticas do ui_manager.gd (balanço, contrato com o Python, sem URL de marca).

Rodam sem Godot, sem rede, sem as bibliotecas pesadas. NUNCA escrevem em config/ do projeto.
Rodar: python -m unittest tests.test_v19_provedores -v
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_provedores as P
import prepare_pendrive as prep

CATALOGO_EXEMPLO = {
    "provedores": [
        {"id": "gemini", "nome": "Gem", "modelo": "m1", "onde_pegar": "exemplo.test/chave", "dica": "d1"},
        {"id": "claude", "nome": "Roteador", "url": "https://roteador.example/api/v1", "dica": "d2"},
        {"id": "groq", "nome": "Rapida", "url": "https://rapida.example/v1"},
        {"id": "openai", "nome": "Oai"},
    ],
    "servicos": [{"id": "tavily", "nome": "Busca", "dica": "s1"}],
    "atalhos": [{"label": "Local", "nome": "Local", "url": "http://localhost:11434/v1", "modelo": "x"}],
}


class FakeCfg:
    """Imita ZenithSettings no que o Cérebro usa: .settings (dict), .get, .update."""
    def __init__(self, **dados):
        self.settings = dict(dados)

    def get(self, k, padrao=None):
        v = self.settings.get(k, padrao)
        return padrao if v in (None, "") else v

    def update(self, mud):
        self.settings.update(mud)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cat_path = self.tmp / "cat.json"
        self.cat_path.write_text(json.dumps(CATALOGO_EXEMPLO), encoding="utf-8")
        # Qualquer leitura "padrão" do catálogo cai neste arquivo temporário — nunca em config/.
        self._p = mock.patch.object(P, "CATALOGO_ARQUIVO", self.cat_path)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self._tmp.cleanup()

    def sem_catalogo(self):
        self.cat_path.unlink()


# ======================================================================
class CatalogoTests(Base):
    def test_ausente_vira_vazio(self):
        self.sem_catalogo()
        cat = P.carregar_catalogo()
        self.assertEqual(cat, P.catalogo_vazio())
        self.assertEqual(P.url_do_slot("claude"), "")

    def test_json_quebrado_vira_vazio(self):
        self.cat_path.write_text("{ isso nao e json", encoding="utf-8")
        self.assertEqual(P.carregar_catalogo(), P.catalogo_vazio())

    def test_raiz_de_tipo_errado_vira_vazio(self):
        self.cat_path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(P.carregar_catalogo(), P.catalogo_vazio())

    def test_carrega_e_resolve_url(self):
        self.assertEqual(P.url_do_slot("claude"), "https://roteador.example/api/v1")
        self.assertEqual(P.url_do_slot("llama"), "https://roteador.example/api/v1")   # apelido do OpenRouter
        self.assertEqual(P.url_do_slot("groq"), "https://rapida.example/v1")
        self.assertEqual(P.url_do_slot("gemini"), "")                                 # SDK, sem URL

    def test_saneamento(self):
        sujo = {"provedores": [
            {"id": "inventado", "nome": "X", "url": "https://x.test"},        # id desconhecido
            {"id": "groq", "nome": "G", "url": "ftp://x.test"},               # esquema inválido
            {"id": "groq", "nome": "G2", "url": "https://dup.test"},          # duplicado
            "lixo", 5, None,
        ], "servicos": [{"id": "outro"}, {"id": "tavily", "nome": "T"}],
            "atalhos": [{"label": "ruim", "url": "javascript:alert(1)"},
                        {"label": "ok", "nome": "n", "url": "https://ok.test"}, "x"]}
        self.cat_path.write_text(json.dumps(sujo), encoding="utf-8")
        cat = P.carregar_catalogo()
        self.assertEqual([p["id"] for p in cat["provedores"]], ["groq"])
        self.assertEqual(cat["provedores"][0]["url"], "")          # URL inválida some
        self.assertEqual([s["id"] for s in cat["servicos"]], ["tavily"])
        self.assertEqual([a["label"] for a in cat["atalhos"]], ["ok"])

    def test_catalogo_do_projeto_e_valido(self):
        """O catálogo que acompanha o projeto (dev) tem os 4 slots, o serviço e atalhos."""
        cat = P.carregar_catalogo(RAIZ / "config" / "provedores_catalogo.json")
        self.assertEqual({p["id"] for p in cat["provedores"]}, {"gemini", "openai", "claude", "groq"})
        self.assertEqual([s["id"] for s in cat["servicos"]], ["tavily"])
        self.assertTrue(cat["atalhos"])
        self.assertTrue(P.url_do_slot("claude", cat).startswith("https://"))
        self.assertTrue(P.url_do_slot("groq", cat).startswith("https://"))


# ======================================================================
class EntradasTests(Base):
    def test_ordem_rotulos_e_estados(self):
        s = {"active_ai": "claude", "gemini_key": "g", "openrouter_key": "o", "tavily_api_key": "",
             "ai_endpoints": [{"id": "e1", "name": "Minha", "api_url": "http://localhost:1/v1",
                               "api_key": "", "model_name": "mod"}]}
        es = P.montar_entradas(s)
        self.assertEqual([e["id"] for e in es], ["gemini", "claude", "groq", "openai", "custom:e1", "tavily"])
        por_id = {e["id"]: e for e in es}
        self.assertEqual(por_id["gemini"]["rotulo"], "✓ Gem")
        self.assertEqual(por_id["openai"]["rotulo"], "⚠ Oai")
        self.assertEqual(por_id["claude"]["rotulo"], "★ ✓ Roteador")
        self.assertTrue(por_id["claude"]["ativa"])
        self.assertEqual(por_id["custom:e1"]["rotulo"], "✓ Minha")          # chave vazia é ok p/ IA local
        self.assertEqual(por_id["tavily"]["rotulo"], "⚠ Busca  (serviço)")
        self.assertFalse(por_id["tavily"]["eh_llm"])
        self.assertEqual(P.ids_de_ia(es), ["gemini", "claude", "groq", "openai", "custom:e1"])

    def test_campos_editaveis_por_origem(self):
        s = {"custom_api_url": "http://x/v1", "ai_endpoints": [
            {"id": "e1", "name": "N", "api_url": "http://l/v1", "api_key": "k", "model_name": "m"}]}
        por_id = {e["id"]: e for e in P.montar_entradas(s)}
        gem, antiga, minha = por_id["gemini"], por_id["custom"], por_id["custom:e1"]
        self.assertFalse(gem["url_editavel"] or gem["modelo_editavel"] or gem["nome_editavel"] or gem["removivel"])
        self.assertTrue(antiga["url_editavel"] and antiga["modelo_editavel"] and antiga["removivel"])
        self.assertTrue(minha["url_editavel"] and minha["modelo_editavel"] and minha["nome_editavel"])
        self.assertEqual(minha["teste_como"], "new_custom")
        self.assertEqual(gem["teste_como"], "gemini")
        self.assertEqual(por_id["tavily"]["teste_como"], "")

    def test_api_antiga_so_aparece_se_tem_url(self):
        self.assertNotIn("custom", [e["id"] for e in P.montar_entradas({})])
        self.assertIn("custom", [e["id"] for e in P.montar_entradas({"custom_api_url": "http://x/v1"})])

    def test_slot_sem_url_no_catalogo_nao_fica_pronto(self):
        self.cat_path.write_text(json.dumps({"provedores": [{"id": "claude", "nome": "R"}]}), encoding="utf-8")
        e = P.montar_entradas({"openrouter_key": "abc"})[0]
        self.assertFalse(e["configurada"])
        self.assertIn("catálogo", e["aviso"])

    def test_sem_catalogo_so_minhas_ias(self):
        self.sem_catalogo()
        s = {"gemini_key": "sobrou", "ai_endpoints": [
            {"id": "e1", "name": "Minha", "api_url": "https://a.test/v1", "api_key": "k", "model_name": "m"}]}
        es = P.montar_entradas(s)
        self.assertEqual([e["id"] for e in es], ["custom:e1"])
        ui = P.dados_para_ui(s)
        self.assertTrue(ui["catalogo_vazio"])
        self.assertEqual(ui["atalhos"], [])
        # nada de marca no que o Corpo recebe
        texto = json.dumps(ui, ensure_ascii=False).lower()
        for host in prep.HOSTS_DE_PROVEDOR:
            self.assertNotIn(host, texto)

    def test_ia_com_url_sem_modelo_nao_esta_pronta(self):
        s = {"ai_endpoints": [{"id": "e1", "name": "N", "api_url": "https://a.test", "model_name": ""}]}
        e = next(x for x in P.montar_entradas(s) if x["id"] == "custom:e1")
        self.assertFalse(e["configurada"])

    def test_entrada_malformada_e_ignorada(self):
        s = {"ai_endpoints": ["lixo", {"name": "sem id"}, None, {"id": "ok", "name": "Ok",
                                                                   "api_url": "https://a.test", "model_name": "m"}]}
        ids = [e["id"] for e in P.montar_entradas(s)]
        self.assertIn("custom:ok", ids)
        self.assertEqual(len([i for i in ids if i.startswith("custom:")]), 1)


# ======================================================================
class EdicaoTests(Base):
    def test_salvar_slot_e_servico_escrevem_no_campo_certo(self):
        self.assertEqual(P.salvar_entrada({}, "gemini", {"chave": "  K1  "}), {"gemini_key": "K1"})
        self.assertEqual(P.salvar_entrada({}, "claude", {"chave": "K2"}), {"openrouter_key": "K2"})
        self.assertEqual(P.salvar_entrada({}, "groq", {"chave": "K3"}), {"groq_key": "K3"})
        self.assertEqual(P.salvar_entrada({}, "openai", {"chave": "K4"}), {"openai_key": "K4"})
        self.assertEqual(P.salvar_entrada({}, "tavily", {"chave": "K5"}), {"tavily_api_key": "K5"})

    def test_slot_fora_do_catalogo_e_recusado(self):
        self.sem_catalogo()
        with self.assertRaises(P.ErroProvedor):
            P.salvar_entrada({}, "gemini", {"chave": "x"})

    def test_id_desconhecido_nunca_vira_campo_arbitrario(self):
        for ruim in ("persona_name", "unlock_password", "../x", "", "custom_api_key"):
            with self.assertRaises(P.ErroProvedor):
                P.salvar_entrada({}, ruim, {"chave": "x", "url": "https://a.test", "nome": "n", "modelo": "m"})

    def test_api_antiga(self):
        mud = P.salvar_entrada({"custom_api_url": "http://a/v1"}, "custom",
                               {"url": "http://b/v1", "chave": "k", "modelo": "m"})
        self.assertEqual(mud, {"custom_api_url": "http://b/v1", "custom_api_key": "k", "custom_api_model": "m"})
        with self.assertRaises(P.ErroProvedor):
            P.salvar_entrada({}, "custom", {"url": ""})

    def test_atualizar_minha_ia_preserva_id_e_as_outras(self):
        s = {"ai_endpoints": [
            {"id": "a", "name": "A", "api_url": "http://a/v1", "api_key": "", "model_name": "ma"},
            {"id": "b", "name": "B", "api_url": "http://b/v1", "api_key": "", "model_name": "mb"}]}
        mud = P.salvar_entrada(s, "custom:b", {"nome": "B2", "url": "https://novo.test/v1", "chave": "k", "modelo": "m2"})
        eps = mud["ai_endpoints"]
        self.assertEqual([e["id"] for e in eps], ["a", "b"])
        self.assertEqual(eps[0]["name"], "A")
        self.assertEqual(eps[1], {"id": "b", "name": "B2", "api_url": "https://novo.test/v1",
                                  "api_key": "k", "model_name": "m2"})
        self.assertEqual(s["ai_endpoints"][1]["name"], "B")                  # não mexeu no original

    def test_validacoes_da_minha_ia(self):
        s = {"ai_endpoints": [{"id": "a", "name": "A", "api_url": "http://a/v1", "model_name": "m"}]}
        for campos in ({"nome": "", "url": "http://x/v1", "modelo": "m"},
                       {"nome": "N", "url": "", "modelo": "m"},
                       {"nome": "N", "url": "http://x/v1", "modelo": ""},
                       {"nome": "N", "url": "ftp://x/v1", "modelo": "m"}):
            with self.assertRaises(P.ErroProvedor, msg=str(campos)):
                P.salvar_entrada(s, "custom:a", campos)
        with self.assertRaises(P.ErroProvedor):
            P.salvar_entrada(s, "custom:naoexiste", {"nome": "N", "url": "http://x/v1", "modelo": "m"})

    def test_nova_ia_gera_id_e_valida(self):
        novo_id, mud = P.nova_endpoint({"ai_endpoints": [{"id": "a"}]},
                                       {"nome": " N ", "url": "http://localhost:1234/v1", "chave": "", "modelo": "m"})
        self.assertTrue(novo_id.startswith("custom:"))
        eps = mud["ai_endpoints"]
        self.assertEqual(len(eps), 2)
        self.assertEqual(eps[1]["name"], "N")
        self.assertEqual("custom:" + eps[1]["id"], novo_id)
        with self.assertRaises(P.ErroProvedor):
            P.nova_endpoint({}, {"nome": "N", "url": "", "modelo": "m"})
        with self.assertRaises(P.ErroProvedor):
            P.nova_endpoint({}, {"nome": "N", "url": "https://a.test", "modelo": ""})

    def test_remover_minha_ia_e_trocar_ativa(self):
        s = {"active_ai": "custom:a", "gemini_key": "g", "ai_endpoints": [
            {"id": "a", "name": "A", "api_url": "http://a/v1", "model_name": "m"}]}
        mud = P.remover_entrada(s, "custom:a")
        self.assertEqual(mud["ai_endpoints"], [])
        self.assertEqual(mud["active_ai"], "gemini")                         # a próxima pronta

    def test_remover_ativa_sem_outra_pronta_volta_ao_padrao(self):
        s = {"active_ai": "custom:a", "ai_endpoints": [
            {"id": "a", "name": "A", "api_url": "http://a/v1", "model_name": "m"}]}
        self.assertEqual(P.remover_entrada(s, "custom:a")["active_ai"], P.ATIVA_PADRAO)

    def test_remover_slot_so_limpa_a_chave(self):
        self.assertEqual(P.remover_entrada({"active_ai": "x", "groq_key": "k"}, "groq"), {"groq_key": ""})
        self.assertEqual(P.remover_entrada({}, "tavily"), {"tavily_api_key": ""})
        self.assertEqual(P.remover_entrada({}, "custom"),
                         {"custom_api_url": "", "custom_api_key": "", "custom_api_model": ""})
        with self.assertRaises(P.ErroProvedor):
            P.remover_entrada({}, "qualquer_coisa")

    def test_remover_slot_ativo_escolhe_outra(self):
        s = {"active_ai": "gemini", "gemini_key": "g", "groq_key": "k"}
        mud = P.remover_entrada(s, "gemini")
        self.assertEqual(mud["gemini_key"], "")
        self.assertEqual(mud["active_ai"], "groq")


# ======================================================================
class CoreSemUrlDeMarcaTests(Base):
    def setUp(self):
        super().setUp()
        from brain import zenith_core as core
        self.core_mod = core
        self.chamadas = []
        self._oa = mock.patch.object(core, "OpenAI", lambda **kw: self.chamadas.append(kw) or object())
        self._oa.start()
        c = object.__new__(core.ZenithCore)
        c.chat = None
        c.client = None
        self.c = c

    def tearDown(self):
        self._oa.stop()
        super().tearDown()

    def test_usa_o_endereco_do_catalogo(self):
        cfg = FakeCfg(openrouter_key="k1", groq_key="k2", active_ai="claude")
        self.c.reload_api_keys(cfg)
        urls = sorted(kw["base_url"] for kw in self.chamadas)
        self.assertEqual(urls, ["https://rapida.example/v1", "https://roteador.example/api/v1"])
        self.assertTrue(self.c.has_provider("claude") and self.c.has_provider("llama") and self.c.has_provider("groq"))

    def test_sem_catalogo_nao_cria_cliente_e_nao_quebra(self):
        self.sem_catalogo()
        cfg = FakeCfg(openrouter_key="k1", groq_key="k2")
        self.c.reload_api_keys(cfg)
        self.assertEqual(self.chamadas, [])
        self.assertFalse(self.c.has_provider("claude"))
        self.assertFalse(self.c.has_provider("groq"))

    def test_minhas_ias_continuam_funcionando_sem_catalogo(self):
        self.sem_catalogo()
        cfg = FakeCfg(ai_endpoints=[{"id": "x1", "name": "Mine", "api_url": "https://a.test/v1",
                                     "api_key": "k", "model_name": "m"}])
        self.c.reload_api_keys(cfg)
        self.assertTrue(self.c.has_provider("custom:x1"))
        self.assertEqual(self.chamadas[0]["base_url"], "https://a.test/v1")

    def test_teste_de_chave_sem_catalogo_explica(self):
        self.sem_catalogo()
        ok, msg = self.c.test_api_key("groq", "chave")
        self.assertFalse(ok)
        self.assertIn("catálogo", msg)
        ok, msg = self.c.test_api_key("claude", "chave")
        self.assertFalse(ok)

    def test_codigo_do_core_nao_tem_endereco_de_provedor(self):
        src = (RAIZ / "brain" / "zenith_core.py").read_text(encoding="utf-8")
        for host in prep.HOSTS_DE_PROVEDOR:
            self.assertNotIn(host, src, host)


# ======================================================================
class HandlersTests(Base):
    def setUp(self):
        super().setUp()
        from brain import zenith_headless as h
        b = object.__new__(h.ZenithHeadlessBrain)
        b.settings = FakeCfg(active_ai="gemini")
        b.core = mock.Mock()
        b.enviados = []
        b.bridge = mock.Mock()
        b.bridge.send = b.enviados.append
        b._ai_selecionar = ""
        self.b = b

    def resposta(self):
        return [m for m in self.b.enviados if m.get("provider") == "ai_panel"][-1]

    def settings_data(self):
        return [m for m in self.b.enviados if m.get("action") == "settings_data"][-1]["settings"]

    def test_settings_data_leva_a_lista_de_ias(self):
        d = self.b._settings_for_ui()
        self.assertIn("_ai_ui", d)
        self.assertEqual([e["id"] for e in d["_ai_ui"]["entradas"]][:2], ["gemini", "claude"])   # ordem do catálogo
        self.assertEqual(d["_ai_ui"]["selecionar"], "")

    def test_salvar_chave_de_slot(self):
        self.b._handle_save_ai_entry({"id": "groq", "chave": " abc "})
        self.assertEqual(self.b.settings.settings["groq_key"], "abc")
        self.b.core.reload_api_keys.assert_called_once()
        self.assertTrue(self.resposta()["valid"])

    def test_erro_de_validacao_vai_pro_painel_e_nao_grava(self):
        self.b._handle_save_ai_entry({"id": "__novo__", "nome": "N", "url": "", "modelo": "m"})
        r = self.resposta()
        self.assertFalse(r["valid"])
        self.assertNotIn("ai_endpoints", self.b.settings.settings)
        self.b.core.reload_api_keys.assert_not_called()

    def test_primeira_ia_nova_vira_a_ativa_e_e_selecionada_uma_vez(self):
        self.sem_catalogo()                                   # cópia de pendrive: ninguém pronto
        self.b._handle_save_ai_entry({"id": "__novo__", "nome": "Minha", "url": "https://a.test/v1",
                                      "chave": "k", "modelo": "m"})
        eps = self.b.settings.settings["ai_endpoints"]
        self.assertEqual(len(eps), 1)
        novo = "custom:" + eps[0]["id"]
        self.assertEqual(self.b.settings.settings["active_ai"], novo)
        self.assertEqual(self.settings_data()["_ai_ui"]["selecionar"], novo)
        self.assertIn("ativa", self.resposta()["message"].lower())
        self.assertEqual(self.b._settings_for_ui()["_ai_ui"]["selecionar"], "")      # só uma vez

    def test_segunda_ia_nao_rouba_a_ativa(self):
        self.sem_catalogo()
        for nome in ("Um", "Dois"):
            self.b._handle_save_ai_entry({"id": "__novo__", "nome": nome, "url": "https://a.test/v1", "modelo": "m"})
        eps = self.b.settings.settings["ai_endpoints"]
        self.assertEqual(self.b.settings.settings["active_ai"], "custom:" + eps[0]["id"])

    def test_editar_minha_ia(self):
        self.sem_catalogo()
        self.b._handle_save_ai_entry({"id": "__novo__", "nome": "Um", "url": "https://a.test/v1", "modelo": "m"})
        eid = "custom:" + self.b.settings.settings["ai_endpoints"][0]["id"]
        self.b._handle_save_ai_entry({"id": eid, "nome": "Um2", "url": "https://b.test/v1", "chave": "k", "modelo": "m2"})
        ep = self.b.settings.settings["ai_endpoints"][0]
        self.assertEqual((ep["name"], ep["api_url"], ep["api_key"], ep["model_name"]),
                         ("Um2", "https://b.test/v1", "k", "m2"))

    def test_remover(self):
        self.b._handle_save_ai_entry({"id": "gemini", "chave": "g"})
        self.b._handle_remove_ai_entry({"id": "gemini"})
        self.assertEqual(self.b.settings.settings["gemini_key"], "")
        self.assertTrue(self.resposta()["valid"])
        self.b._handle_remove_ai_entry({"id": "id_que_nao_existe"})
        self.assertFalse(self.resposta()["valid"])

    def test_roteador_conhece_as_acoes_novas(self):
        src = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('"save_ai_entry": self._handle_save_ai_entry', src)
        self.assertIn('"remove_ai_entry": self._handle_remove_ai_entry', src)

    def test_chave_nunca_vai_para_o_texto_do_chat(self):
        self.b._handle_save_ai_entry({"id": "gemini", "chave": "SEGREDO-123"})
        for m in self.b.enviados:
            if m.get("action") == "chat_message":
                self.assertNotIn("SEGREDO-123", m.get("text", ""))
        self.assertNotIn("SEGREDO-123", self.resposta()["message"])


# ======================================================================
class PendrivePrepTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name) / "Zenith"
        (self.d / "config").mkdir(parents=True)
        (self.d / "body/zenith/addons/avatars").mkdir(parents=True)
        (self.d / "body/zenith/.godot/imported").mkdir(parents=True)
        (self.d / "memory_db").mkdir()
        (self.d / "memory_db/x.bin").write_bytes(b"x")
        for nome in ("zenith_notas.jsonl", "zenith_acoes_log.jsonl", "zenith_lembretes.json",
                     "provedores_catalogo.json", "conversations.json"):
            (self.d / "config" / nome).write_text("{}", encoding="utf-8")
        (self.d / "config/settings.json").write_text(json.dumps({
            "persona_name": "Outra", "user_name": "Anderson", "gemini_key": "AIza" + "x" * 35,
            "openrouter_key": "sk-or-" + "y" * 30, "vrm_model_path": "D:/Código em Python/Cypher.vrm",
            "ai_endpoints": [{"id": "1", "name": "N", "api_url": "https://openrouter.ai/api/v1"}],
            "active_ai": "custom:1", "onboarding_done": True, "aviso_inicial_visto": True,
            "modo_atual": "estudo", "tavily_api_key": "tvly-" + "z" * 20,
        }), encoding="utf-8")
        av = self.d / "body/zenith/addons/avatars"
        for nome in ("Zenith.vrm", "Cypher.vrm", "Meu_Teste.vrm"):
            (av / nome).write_bytes(b"v")
            (av / (nome + ".import")).write_text("x", encoding="utf-8")
        (self.d / "body/zenith/.godot/imported/Meu_Teste.vrm-abc.scn").write_bytes(b"c")
        (self.d / "body/zenith/.godot/imported/Zenith.vrm-def.scn").write_bytes(b"c")
        (self.d / "body/zenith/Zenith_novo.pck").write_bytes(b"p")
        (self.d / "body/zenith/Zenith.pck.bak").write_bytes(b"p")
        (self.d / "zenith_log.txt").write_text(r"erro em C:\Users\joao\Desktop\x", encoding="utf-8")
        (self.d / "LEIAME.md").write_text("pegue a chave em https://console.groq.com/keys", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def tipos(self, achados):
        return {t for _, t, _ in achados}

    def test_varredura_acha_tudo_que_vazaria(self):
        achados = prep.varrer_distribuicao(str(self.d))
        tipos = self.tipos(achados)
        self.assertIn("chave de API (AIza…)", tipos)
        self.assertIn("chave de API (sk-…)", tipos)
        self.assertIn("chave de API (tvly-…)", tipos)
        self.assertIn("campo de segredo preenchido", tipos)
        self.assertIn("caminho pessoal", tipos)
        self.assertIn("endereço de provedor", tipos)
        arquivos = {a for a, _, _ in achados}
        self.assertIn("zenith_log.txt", arquivos)
        self.assertIn("LEIAME.md", arquivos)

    def test_varredura_mascara_chaves(self):
        for _, tipo, trecho in prep.varrer_distribuicao(str(self.d)):
            if tipo.startswith("chave"):
                self.assertNotIn("x" * 10, trecho)
                self.assertNotIn("y" * 10, trecho)
                self.assertIn("mascarado", trecho)

    def test_apos_a_limpeza_a_varredura_fica_limpa(self):
        d = str(self.d)
        for arq in prep._FILES_TO_REMOVE:
            p = self.d / arq
            if p.is_file():
                p.unlink()
        prep.remover_sobras_pck(d)
        prep.remover_avatares(d, prep.avatares_extras(d))
        prep.reset_settings_json(d)
        (self.d / "LEIAME.md").unlink()
        achados = prep.varrer_distribuicao(d)
        self.assertEqual(achados, [], achados)

    def test_dados_do_v18_estao_na_lista_de_remocao(self):
        lista = [Path(p).name for p in prep._FILES_TO_REMOVE]
        for nome in ("zenith_notas.jsonl", "zenith_acoes_log.jsonl", "zenith_lembretes.json",
                     "provedores_catalogo.json", "conversations.json", "zenith_log.txt"):
            self.assertIn(nome, lista)

    def test_nomes_dos_arquivos_batem_com_os_modulos(self):
        """Se um módulo mudar o nome do arquivo que grava, a limpeza do pendrive precisa acompanhar."""
        from brain import zenith_notes, zenith_actionlog, zenith_lembretes
        self.assertEqual(Path(zenith_notes._caminho_padrao()).name, "zenith_notas.jsonl")
        self.assertEqual(Path(zenith_actionlog._caminho_padrao()).name, "zenith_acoes_log.jsonl")
        self.assertEqual(Path(zenith_lembretes._caminho_padrao()).name, "zenith_lembretes.json")
        self.assertEqual(P.CATALOGO_ARQUIVO.name, "provedores_catalogo.json")

    def test_sobras_do_pck_somem(self):
        removidos = prep.remover_sobras_pck(str(self.d))
        self.assertEqual(len(removidos), 2)
        self.assertFalse((self.d / "body/zenith/Zenith_novo.pck").exists())
        self.assertFalse((self.d / "body/zenith/Zenith.pck.bak").exists())

    def test_so_o_avatar_adicionado_e_removido(self):
        """1.0 Oficial: TUDO que não é o mascote oficial sai — inclusive os VRMs de terceiros.

        Antes (v19) o Cypher contava como "de fábrica" e ficava na distribuição; agora só o
        Zenith.vrm viaja, então ele entra na lista de extras junto com o avatar que você adicionou.
        """
        d = str(self.d)
        extras = prep.avatares_extras(d)
        self.assertEqual(sorted(extras), ["Cypher.vrm", "Meu_Teste.vrm"])
        prep.remover_avatares(d, extras)
        av = self.d / "body/zenith/addons/avatars"
        self.assertFalse((av / "Meu_Teste.vrm").exists() or (av / "Meu_Teste.vrm.import").exists())
        self.assertFalse((self.d / "body/zenith/.godot/imported/Meu_Teste.vrm-abc.scn").exists())
        self.assertFalse((av / "Cypher.vrm").exists() or (av / "Cypher.vrm.import").exists())
        self.assertTrue((av / "Zenith.vrm").exists() and (av / "Zenith.vrm.import").exists())
        self.assertTrue((self.d / "body/zenith/.godot/imported/Zenith.vrm-def.scn").exists())

    def test_sem_avatares_tira_todos(self):
        d = str(self.d)
        self.assertEqual(prep.avatares_extras(d, sem_avatares=True), ["Cypher.vrm", "Meu_Teste.vrm", "Zenith.vrm"])

    def test_reset_do_settings(self):
        prep.reset_settings_json(str(self.d))
        s = json.loads((self.d / "config/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(s["gemini_key"], "")
        self.assertEqual(s["ai_endpoints"], [])
        self.assertEqual(s["vrm_model_path"], "")
        self.assertEqual(s["tavily_api_key"], "")
        self.assertFalse(s["onboarding_done"])
        self.assertFalse(s["aviso_inicial_visto"])
        self.assertEqual(s["modo_atual"], "normal")
        self.assertEqual(s["user_name"], "")
        self.assertEqual(s["persona_name"], "Zenith")

    def test_so_varrer_nao_apaga_nada(self):
        with mock.patch("builtins.input", side_effect=AssertionError("não devia pedir confirmação")):
            prep.main([str(self.d), "--so-varrer"])
        self.assertTrue((self.d / "config/zenith_notas.jsonl").exists())
        self.assertTrue((self.d / "memory_db/x.bin").exists())

    def test_main_cancelado_nao_apaga(self):
        with mock.patch("builtins.input", return_value="nao"):
            prep.main([str(self.d)])
        self.assertTrue((self.d / "config/zenith_notas.jsonl").exists())

    def test_main_completo(self):
        with mock.patch("builtins.input", return_value="sim"):
            prep.main([str(self.d)])
        for nome in ("zenith_notas.jsonl", "zenith_acoes_log.jsonl", "zenith_lembretes.json",
                     "provedores_catalogo.json", "conversations.json"):
            self.assertFalse((self.d / "config" / nome).exists(), nome)
        self.assertFalse((self.d / "body/zenith/addons/avatars/Meu_Teste.vrm").exists())
        self.assertTrue((self.d / "body/zenith/addons/avatars/Zenith.vrm").exists())
        self.assertTrue((self.d / "config/settings.json").exists())

    def test_varredura_ignora_pastas_de_terceiros(self):
        (self.d / "_internal").mkdir()
        (self.d / "_internal/lib.py").write_text("url = 'https://api.openai.com/v1'", encoding="utf-8")
        (self.d / "body/zenith/addons/vrm").mkdir(parents=True)
        (self.d / "body/zenith/addons/vrm/README.md").write_text("see openrouter.ai", encoding="utf-8")
        arquivos = {a for a, _, _ in prep.varrer_distribuicao(str(self.d))}
        self.assertNotIn(str(Path("_internal/lib.py")), arquivos)
        self.assertNotIn(str(Path("body/zenith/addons/vrm/README.md")), arquivos)


# ======================================================================
class GodotEstaticoTests(unittest.TestCase):
    """Não substitui rodar no Godot. Pega o erro bobo (parêntese, espaço no lugar de tab) e a
    quebra de contrato entre o que o Python manda e o que o .gd lê."""

    @classmethod
    def setUpClass(cls):
        cls.gd = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")

    @staticmethod
    def _sem_strings(linha: str) -> str:
        out, i, q = [], 0, None
        while i < len(linha):
            c = linha[i]
            if q:
                if c == "\\":
                    i += 2
                    continue
                if c == q:
                    q = None
                i += 1
                continue
            if c in "\"'":
                q = c
                i += 1
                continue
            if c == "#":
                break
            out.append(c)
            i += 1
        return "".join(out)

    def test_delimitadores_balanceados_e_sem_indentacao_por_espaco(self):
        par = {")": "(", "]": "[", "}": "{"}
        pilha = []
        for n, linha in enumerate(self.gd.split("\n"), 1):
            self.assertFalse(linha.startswith(" "), f"linha {n} começa com espaço")
            for c in self._sem_strings(linha):
                if c in "([{":
                    pilha.append((c, n))
                elif c in ")]}":
                    self.assertTrue(pilha and pilha[-1][0] == par[c], f"fecha {c} sem abrir (linha {n})")
                    pilha.pop()
        self.assertEqual(pilha, [], f"abriu e não fechou: {pilha[:3]}")

    def test_nenhuma_funcao_repetida(self):
        nomes = re.findall(r"^func (\w+)", self.gd, re.M)
        repetidas = {n for n in nomes if nomes.count(n) > 1}
        self.assertEqual(repetidas, set())

    def test_funcoes_chamadas_do_painel_existem(self):
        definidas = set(re.findall(r"^func (\w+)", self.gd, re.M))
        for nome in ("_refresh_ai_panel", "_ai_show_entry", "_ai_flush_all", "_ai_fill_active_selector",
                     "_ai_stash_current", "_ai_make_row", "_ai_find", "_ai_read_fields", "_ai_send_save",
                     "_on_ai_save_pressed", "_on_ai_remove_pressed", "_on_ai_use_pressed",
                     "_on_ai_test_pressed", "_on_ai_edit_selected", "_on_ai_field_edited",
                     "_ai_rebuild_shortcuts", "_ai_apply_empty_state"):
            self.assertIn(nome, definidas, nome)
            self.assertGreaterEqual(len(re.findall(rf"\b{nome}\b", self.gd)), 2, f"{nome} nunca é usada")
        self.assertNotIn("_refresh_custom_endpoints_list(", self.gd)

    def test_variaveis_de_membro_do_painel_declaradas(self):
        sem_strings = re.sub(r'"[^"\n]*"', '""', self.gd)
        usadas = set(re.findall(r"\b(ai_[a-z_]+)\b", sem_strings))
        declaradas = set(re.findall(r"^var (ai_[a-z_]+)", self.gd, re.M))
        funcoes = set(re.findall(r"^func (\w+)", self.gd, re.M))
        locais = set(re.findall(r"\bvar (ai_[a-z_]+)", self.gd)) - declaradas
        faltando = {u for u in usadas if u not in declaradas and u not in funcoes and u not in locais
                    and not u.startswith("ai_ui") and u != "ai_entradas"}
        self.assertEqual(faltando, set())

    def test_chaves_lidas_do_dicionario_da_entrada_existem_no_python(self):
        i = self.gd.index("func _ai_find")
        j = self.gd.index("func _on_ai_field_edited")
        lidas = set(re.findall(r'\be\.get\("(\w+)"', self.gd[i:j]))
        lidas |= set(re.findall(r'\be\.get\("(\w+)"', self.gd[self.gd.index("func _refresh_ai_panel"):i + 1]))
        lidas |= set(re.findall(r'\be\.get\("(\w+)"', self.gd[self.gd.index("func _ai_fill_active_selector"):]
                                [:900]))
        self.assertTrue(lidas)
        cat = P.carregar_catalogo(RAIZ / "config" / "provedores_catalogo.json")
        exemplo = P.montar_entradas({"custom_api_url": "http://x/v1", "ai_endpoints": [
            {"id": "a", "name": "A", "api_url": "http://a/v1", "model_name": "m"}]}, cat)
        chaves_python = set().union(*[set(e) for e in exemplo])
        self.assertEqual(lidas - chaves_python, set(), "o .gd lê campo que o Python não manda")

    def test_chaves_do_ui_lidas_existem(self):
        for chave in ("entradas", "atalhos", "selecionar"):
            self.assertIn(f'"{chave}"', self.gd)
        ui = P.dados_para_ui({})
        self.assertTrue({"entradas", "atalhos", "selecionar"} - set(ui) <= {"selecionar"})  # selecionar vem do Cérebro

    def test_salvar_geral_leva_os_rascunhos_e_nao_grava_id_vazio(self):
        i = self.gd.index("func _save_settings()")
        corpo = self.gd[i:i + 600]
        self.assertIn("_ai_flush_all()", corpo)
        self.assertIn('String(ai_opts[field.selected]) != ""', self.gd)

    def test_godot_sem_endereco_nem_nome_de_provedor(self):
        for arq in ("ui_manager.gd", "akira_body.gd", "brain_connector.gd"):
            txt = (RAIZ / "body/zenith" / arq).read_text(encoding="utf-8").lower()
            for host in prep.HOSTS_DE_PROVEDOR:
                self.assertFalse(host in txt, f"{arq}: tem o endereço {host}")
            for marca in ("openrouter", "groq", "aistudio", "tavily", "ollama", "lm studio", "together"):
                self.assertFalse(marca in txt, f"{arq}: cita a marca {marca}")

    def test_titulo_da_aba_corpo_vrm(self):
        """A posição do título tem que acompanhar a ordem das abas (v1.1 tirou a aba "IAs & Chaves")."""
        bloco = self.gd[self.gd.index("settings_tabs = tabs"):self.gd.index("tabs.set_tab_title")]
        ordem = re.findall(r"tabs\.add_child\((_settings_tab_\w+)\(\)\)", bloco)
        self.assertIn("_settings_tab_body", ordem)
        i = ordem.index("_settings_tab_body")
        self.assertIn(f'tabs.set_tab_title({i}, "Corpo / VRM")', self.gd)

    def test_aviso_de_migracao_nao_repete(self):
        self.assertIn("_migracao_avatar_avisada", self.gd)
        self.assertGreaterEqual(self.gd.count("if not _migracao_avatar_avisada:"), 2)


if __name__ == "__main__":
    unittest.main()
