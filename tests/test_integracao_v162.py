"""v1.6.2 — as LIGAÇÕES do autoajuste e do Launcher com o resto do Zenith (comandos, core, headless, launcher do app, Bíblia).

Prova principalmente a parte de SEGURANÇA da ligação: a IA só consegue LER o código sozinha (/codigo); propor vira só
proposta; testar/aplicar/desfazer só existem como comando digitado pelo usuário.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs                         # noqa: E402
_stubs.instalar()
from brain import zenith_atualizar as AT          # noqa: E402
from brain import zenith_autoajuste as AJ         # noqa: E402
from brain import zenith_biblia as BI             # noqa: E402
from brain import zenith_commands as CMD          # noqa: E402
from brain import zenith_overlay as OV            # noqa: E402
from brain import zenith_tags as TAGS             # noqa: E402

DEMO = '"""demo"""\n\n\ndef soma(a, b):\n    return a - b\n'
TESTE = 'import unittest\nfrom brain import zenith_demo\n\n\nclass T(unittest.TestCase):\n    def test_soma(self):\n        self.assertEqual(zenith_demo.soma(2, 3), 5)\n'


def proposta():
    return json.dumps({"arquivo": "brain/zenith_demo.py", "motivo": "A soma estava subtraindo; troquei o sinal.",
                       "edicoes": [{"antigo": "return a - b", "novo": "return a + b"}]})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zi_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        raiz = self.tmp / "projeto"
        (raiz / "brain").mkdir(parents=True)
        (raiz / "tests").mkdir()
        (raiz / "tests" / "__init__.py").write_text("")
        (raiz / "brain" / "zenith_core.py").write_text("#\n")
        (raiz / "brain" / "zenith_demo.py").write_text(DEMO)
        (raiz / "tests" / "test_demo.py").write_text(TESTE)
        self.aj = AJ.Ajustes(raiz, self.tmp / "config" / "ajustes")
        p = mock.patch.object(AJ, "instancia", lambda: self.aj)
        p.start()
        self.addCleanup(p.stop)


# ------------------------------------------------------------------ comandos
class ComandosTests(Base):
    def cmd(self, texto):
        return CMD.tratar(texto, {})

    def test_listar_e_ajuda(self):
        self.assertIn("Nenhum ajuste", self.cmd("/ajustes")["resposta"])
        self.assertIn("/ajustes", CMD._AJUDA)
        self.assertIn("/codigo", CMD._AJUDA)

    def test_fluxo_completo_pelos_comandos(self):
        self.aj.propor(proposta())
        self.assertIn("#1 [pendente]", self.cmd("/ajustes")["resposta"])
        ver = self.cmd("/ajuste ver 1")["resposta"]
        self.assertIn("+    return a + b", ver)
        t = self.cmd("/ajuste testar 1")
        self.assertEqual(t["acao"], "ajuste_testar")
        self.assertEqual(t["args"], {"id": 1})
        self.assertIn("Ainda não testei", self.cmd("/ajuste aplicar 1")["resposta"])
        self.assertTrue(self.aj.testar(1)["ok"])
        self.assertIn("aplicado", self.cmd("/ajuste aplicar 1")["resposta"])
        self.assertIn("desfeito", self.cmd("/ajuste desfazer")["resposta"])

    def test_aplicar_sem_teste_so_com_a_palavra_explicita(self):
        self.aj.propor(proposta())
        self.assertIn("aplicado", self.cmd("/ajuste aplicar 1 sem-teste")["resposta"])

    def test_recusar_e_erros_de_uso(self):
        self.aj.propor(proposta())
        self.assertIn("recusado", self.cmd("/ajuste recusar 1")["resposta"])
        self.assertIn("Diga o número", self.cmd("/ajuste ver")["resposta"])
        self.assertIn("Não existe", self.cmd("/ajuste ver 99")["resposta"])
        self.assertIn("Não existe", self.cmd("/ajuste testar 99")["resposta"])
        self.assertIn("Não conheço", self.cmd("/ajuste explodir 1")["resposta"])

    def test_codigo_mostra_o_trecho_e_guarda_no_contexto(self):
        r = self.cmd("/codigo brain/zenith_demo.py 4-5")["resposta"]
        self.assertIn("```python", r)
        self.assertIn("return a - b", r)
        self.assertIn("return a - b", self.aj.bloco_contexto())
        self.assertIn("Use:", self.cmd("/codigo")["resposta"])
        self.assertIn("100-160", self.cmd("/codigo zenith_demo abc")["resposta"])
        self.assertIn("Só leio", self.cmd("/codigo config/settings.json")["resposta"])
        self.assertIn("return a - b", self.cmd("/ajuste codigo zenith_demo")["resposta"])


# ------------------------------------------------------------------ o que a IA consegue fazer sozinha
class SegurancaDaLigacaoTests(Base):
    def setUp(self):
        super().setUp()
        from brain.zenith_core import ZenithCore, COMANDOS_AUTO
        self.COMANDOS_AUTO = COMANDOS_AUTO
        core = object.__new__(ZenithCore)
        core.settings = types.SimpleNamespace(get=lambda k, p=None: p)
        self.core = core

    def test_so_codigo_esta_na_lista_dos_comandos_automaticos(self):
        self.assertIn("codigo", self.COMANDOS_AUTO)
        for perigoso in ("ajuste", "ajustes", "aplicar", "testar", "desfazer", "chave", "chaves", "atualizar", "modelo"):
            self.assertNotIn(perigoso, self.COMANDOS_AUTO)

    def test_ia_nao_consegue_testar_nem_aplicar_pelo_comando_automatico(self):
        self.aj.propor(proposta())
        for ordem in ("ajuste aplicar 1 sem-teste", "ajuste testar 1", "ajuste desfazer", "ajustes", "/ajuste aplicar 1"):
            saidas = self.core._rodar_comandos_auto(f"vou resolver <comando>{ordem}</comando>")
            self.assertEqual(saidas, [], ordem)
        self.assertEqual(self.aj.carregar(1)["estado"], "pendente")
        self.assertFalse((self.tmp / "config" / "ajustes" / "overlay").exists())

    def test_ia_consegue_ler_o_proprio_codigo(self):
        saidas = self.core._rodar_comandos_auto("<comando>codigo brain/zenith_demo.py 1-6</comando>")
        self.assertEqual(len(saidas), 1)
        self.assertIn("return a - b", saidas[0]["saida"])
        self.assertIn("return a - b", self.aj.bloco_contexto())

    def test_proposta_some_do_chat_e_vira_proposta(self):
        txt = "Achei o erro na soma. <propor_ajuste>" + proposta() + "</propor_ajuste> Aguardo você."
        limpo = TAGS.limpar_visivel(txt)
        self.assertNotIn("propor_ajuste", limpo)
        self.assertNotIn("edicoes", limpo)
        self.assertIn("Achei o erro", limpo)
        self.assertEqual(len(AJ.extrair_propostas(txt)), 1)
        from brain.zenith_core import ZenithCore
        self.assertNotIn("edicoes", ZenithCore._remove_tags(txt))

    def test_trechos_vao_para_o_prompt(self):
        self.aj.ler_trecho("zenith_demo")
        self.assertIn("def soma", self.core._bloco_codigo())


# ------------------------------------------------------------------ headless
class HeadlessTests(Base):
    def setUp(self):
        super().setUp()
        from brain.zenith_headless import ZenithHeadlessBrain
        self.h = object.__new__(ZenithHeadlessBrain)
        self.enviadas = []
        self.h.bridge = types.SimpleNamespace(send=lambda m: self.enviadas.append(m))

    def textos(self):
        return [m["text"] for m in self.enviadas if m.get("action") == "chat_message"]

    def test_proposta_da_ia_vira_aviso_no_chat_sem_mudar_nada(self):
        self.h._receber_propostas_ajuste([proposta()])
        self.assertEqual(len(self.textos()), 1)
        self.assertIn("Propus o ajuste #1", self.textos()[0])
        self.assertIn("Nada foi alterado", self.textos()[0])
        self.assertEqual(self.aj.carregar(1)["estado"], "pendente")

    def test_proposta_recusada_avisa_o_motivo(self):
        ruim = json.dumps({"arquivo": "brain/zenith_core.py", "motivo": "Quero mexer no núcleo do Zenith.", "edicoes": [{"antigo": "#", "novo": "# x"}]})
        self.h._receber_propostas_ajuste([ruim, "lixo"])
        t = self.textos()
        self.assertEqual(len(t), 2)
        self.assertIn("protegido", t[0])
        self.assertIn("JSON", t[1])
        self.assertEqual(self.aj.listar(), [])

    def test_nao_aceita_mais_de_3_por_vez(self):
        self.h._receber_propostas_ajuste(["x"] * 7)
        self.assertEqual(len(self.textos()), 3)

    def test_testar_responde_no_chat(self):
        self.aj.propor(proposta())
        self.h._rodar_ajuste_testar(1)
        self.assertIn("Testei o ajuste #1", self.textos()[0])
        self.h._rodar_ajuste_testar(42)
        self.assertIn("Não existe", self.textos()[1])

    def test_o_comando_ajuste_testar_chega_na_thread_certa(self):
        chamado = []
        self.h._rodar_ajuste_testar = lambda i: chamado.append(i)
        with mock.patch.object(threading.Thread, "start", lambda t: t.run()):
            self.h._executar_comando({"resposta": "Vou testar.", "acao": "ajuste_testar", "args": {"id": 3}})
            self.h._executar_comando({"resposta": "", "acao": "ajuste_testar", "args": {"id": "lixo"}})
        self.assertEqual(chamado, [3, 0])
        self.assertEqual(self.textos(), ["Vou testar."])


class AtualizarViaLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zl2_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.exe = self.tmp / "ZenithLauncher.exe"
        self.exe.write_bytes(b"MZ")

    def test_abre_com_atualizar_e_espera_o_pid(self):
        chamadas = []
        ok, msg = AT.abrir_launcher(str(self.exe), 4321, aprovado=True, popen=lambda cmd, **k: chamadas.append(cmd))
        self.assertTrue(ok)
        self.assertEqual(chamadas[0], [str(self.exe), "--atualizar", "--esperar-pid", "4321"])
        self.assertIn("Feche o Zenith", msg)

    def test_sem_pedido_do_usuario_nao_abre(self):
        chamadas = []
        ok, _ = AT.abrir_launcher(str(self.exe), 1, aprovado=False, popen=lambda *a, **k: chamadas.append(a))
        self.assertFalse(ok)
        self.assertEqual(chamadas, [])

    def test_so_exe_que_existe_e_caminho_absoluto(self):
        for ruim in ("", "ZenithLauncher.exe", str(self.tmp / "nao_existe.exe"), str(self.tmp)):
            ok, _ = AT.abrir_launcher(ruim, 1, aprovado=True, popen=lambda *a, **k: None)
            self.assertFalse(ok, ruim)
        txt = self.tmp / "x.txt"
        txt.write_text("a")
        self.assertFalse(AT.abrir_launcher(str(txt), 1, aprovado=True, popen=lambda *a, **k: None)[0])

    def test_headless_entrega_a_vez_ao_launcher_so_quando_o_usuario_pede(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        h = object.__new__(ZenithHeadlessBrain)
        enviadas = []
        h.bridge = types.SimpleNamespace(send=lambda m: enviadas.append(m["text"]))
        h.settings = types.SimpleNamespace(get=lambda k, p=None: p)
        info = {"versao": "9.9", "notas": "x", "url": "https://github.com/u/z/a.zip", "sha256": "a" * 64, "tamanho": 5}
        abertos = []
        env = {"ZENITH_LAUNCHER": str(self.exe), "ZENITH_ATUALIZAR_URL": "https://site.vercel.app/latest.json"}
        with mock.patch.dict(os.environ, env), mock.patch.object(AT, "consultar", lambda url, **k: (info, "")), \
                mock.patch.object(AT, "abrir_launcher", lambda *a, **k: abertos.append(a) or (True, "Abri o Launcher.")):
            h._rodar_atualizar("consultar")
            self.assertEqual(abertos, [])
            self.assertIn("/atualizar instalar", enviadas[-1])
            h._rodar_atualizar("instalar")
            self.assertEqual(len(abertos), 1)
            self.assertEqual(abertos[0][0], str(self.exe))
            self.assertEqual(enviadas[-1], "Abri o Launcher.")


# ------------------------------------------------------------------ launcher do app (modo seguro + overlay)
class LauncherDoAppTests(unittest.TestCase):
    def setUp(self):
        os.environ["ZENITH_TESTE"] = "1"
        import zenith_launcher as ZL
        self.ZL = ZL
        self.tmp = Path(tempfile.mkdtemp(prefix="zb_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.logs = []
        for alvo, valor in (("BASE", str(self.tmp)), ("_log", lambda m, *a, **k: self.logs.append(str(m)))):
            p = mock.patch.object(ZL, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(OV.desinstalar)
        self.pasta = self.tmp / "config" / "ajustes"

    def aprovar(self, nome="zenith_overlay_teste.py"):
        d = OV.pasta_overlay(self.pasta)
        d.mkdir(parents=True)
        (d / nome).write_text("X = 1\n")
        m = OV.ler_manifesto(self.pasta)
        m["arquivos"][nome] = {"sha256": OV.sha256_arquivo(d / nome), "id": 1}
        OV.gravar_manifesto(self.pasta, m)

    def test_sem_ajustes_nao_muda_nada(self):
        self.assertEqual(self.ZL._preparar_ajustes(), str(self.pasta))
        self.assertEqual([f for f in sys.meta_path if isinstance(f, OV.BuscadorOverlay)], [])

    def test_liga_os_ajustes_aprovados_e_registra_no_log(self):
        self.aprovar()
        self.ZL._preparar_ajustes()
        self.assertTrue(any("Ajustes de código ativos: zenith_overlay_teste.py" in m for m in self.logs))
        self.assertEqual(len([f for f in sys.meta_path if isinstance(f, OV.BuscadorOverlay)]), 1)

    def test_modo_seguro_depois_de_dois_inicios_que_nao_abriram(self):
        self.aprovar()
        for _ in range(3):
            self.ZL._preparar_ajustes()
        self.assertTrue(any("MODO SEGURO" in m for m in self.logs))
        self.assertEqual(OV.ler_manifesto(self.pasta)["arquivos"], {})
        self.assertEqual([f for f in sys.meta_path if isinstance(f, OV.BuscadorOverlay)], [])

    def test_confirmar_boot_zera_a_contagem_sem_travar(self):
        self.aprovar()
        self.ZL._preparar_ajustes()
        with mock.patch("atexit.register") as reg:
            self.ZL._confirmar_boot(str(self.pasta), segundos=0)
            reg.assert_called_once()
        import time
        for _ in range(50):
            if json.loads((self.pasta / "boot.json").read_text()).get("tentativas") == 0:
                break
            time.sleep(0.05)
        self.assertEqual(json.loads((self.pasta / "boot.json").read_text())["tentativas"], 0)

    def test_erro_ao_ligar_nao_derruba_o_app(self):
        with mock.patch.object(OV, "iniciar_boot", side_effect=RuntimeError("boom")), mock.patch("traceback.print_exc"):
            self.assertIsNone(self.ZL._preparar_ajustes())
        self.assertTrue(any("seguindo sem eles" in m for m in self.logs))


# ------------------------------------------------------------------ Bíblia
class BibliaTests(unittest.TestCase):
    def test_cartao_aparece_quando_o_assunto_bate_e_ensina_a_regra_de_honestidade(self):
        self.assertIn("meu_codigo", BI.secoes_para("você pode se consertar? corrija você mesma esse erro"))
        sec = BI.SECOES["meu_codigo"]["texto"]
        for trecho in ("<propor_ajuste>", "<comando>codigo", "/ajuste testar N", "/ajuste aplicar N", "HONESTIDADE", "próximo início"):
            self.assertIn(trecho, sec)
        self.assertIn("meu_codigo", BI.ORDEM_DOC)

    def test_o_cartao_nao_afrouxa_os_pilares(self):
        sec = BI.SECOES["meu_codigo"]["texto"].lower()
        self.assertIn("quem decide", sec)
        self.assertNotIn("sem aprova", sec)


if __name__ == "__main__":
    unittest.main()
