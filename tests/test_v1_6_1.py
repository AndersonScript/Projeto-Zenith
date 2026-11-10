"""v1.6.1 — Biblioteca Zenith: "o que ela usa como base" (documentos + Bíblia) e a aba "Projetos completos"."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                          # noqa: E402
_stubs.instalar()
from brain import zenith_fontes as F              # noqa: E402
from brain import zenith_projetos as PJ           # noqa: E402
from brain import zenith_biblioteca as B          # noqa: E402
from brain import zenith_biblia as BI             # noqa: E402
from brain import zenith_conhecimento as CO       # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="zenith_v161_"))
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)


class _BibFalsa:
    def __init__(self, docs):
        self._docs = docs

    def documentos(self):
        return self._docs


class FontesTests(_Tmp):
    def test_documentos_viram_itens_com_pagina_e_trechos(self):
        bib = _BibFalsa([{"id": "a1", "nome": "Apostila.pdf", "paginas": 10, "trechos": 40, "adicionado": "2026-10-20 10:00"}])
        c = F.categoria_fontes(bib)
        self.assertEqual((c["id"], c["grupo"], c["total"]), ("fontes", "base", 1))
        it = c["grupos"][0]["itens"][0]
        self.assertEqual((it["tipo"], it["id"], it["paginas"], it["trechos"], it["extensao"]), ("fonte", "a1", 10, 40, "pdf"))
        self.assertTrue(c["pode_adicionar"])

    def test_sem_documentos_a_categoria_existe_e_vem_vazia(self):
        c = F.categoria_fontes(_BibFalsa([]))
        self.assertEqual((c["total"], c["grupos"]), (0, []))

    def test_tirar_fonte_remove_do_indice_e_nao_toca_o_arquivo(self):
        original = self.d / "notas.txt"
        original.write_text("lei de Newton: força é massa vezes aceleração. " * 30, encoding="utf-8")
        bib = B.Biblioteca(self.d / "bib")
        bib.adicionar(str(original))
        doc_id = bib.documentos()[0]["id"]
        ok, msg = F.tirar_fonte(doc_id, bib)
        self.assertTrue(ok)
        self.assertIn("notas.txt", msg)
        self.assertIn("continua onde estava", msg)
        self.assertEqual(bib.documentos(), [])
        self.assertTrue(original.exists())                          # o original nunca é tocado

    def test_tirar_fonte_que_nao_existe_devolve_erro_claro(self):
        ok, msg = F.tirar_fonte("nao-existe", B.Biblioteca(self.d / "bib"))
        self.assertFalse(ok)
        self.assertNotIn("📚", msg)


class BibliaTests(_Tmp):
    def _cat(self, pasta=None, extra=""):
        return F.categoria_biblia("Anderson", "Zenith", "/criacoes", pasta or self.d / "biblia_vazia", extra)

    def _itens(self, cat):
        return {i["id"]: i for g in cat["grupos"] for i in g["itens"]}

    def test_grupos_sempre_assunto_e_regras(self):
        cat = self._cat()
        titulos = [g["titulo"].split(" (")[0] for g in cat["grupos"]]
        self.assertEqual(titulos[0], "Sempre no prompt")
        self.assertTrue(titulos[1].startswith("Entram quando o assunto bate"))
        self.assertEqual(titulos[-1], "Suas regras")
        itens = self._itens(cat)
        self.assertTrue(itens["essencial"]["sempre"] and itens["corpo"]["sempre"])
        self.assertFalse(itens["programacao"]["sempre"])
        self.assertIn("programacao", itens)

    def test_texto_vem_preenchido_com_o_nome_da_pessoa(self):
        itens = self._itens(self._cat())
        self.assertIn("Anderson", itens["essencial"]["texto"])
        self.assertNotIn("{user}", itens["essencial"]["texto"])

    def test_nenhuma_secao_da_biblia_some(self):
        itens = self._itens(self._cat())
        for chave in BI.SECOES:
            self.assertIn(chave, itens)

    def test_regras_do_usuario_aparecem_e_vazio_explica_onde_escrever(self):
        self.assertIn("ZENITH.md", self._itens(self._cat())["extra"]["texto"])
        com = self._itens(self._cat(extra="Sempre me chame de chefe."))["extra"]
        self.assertEqual(com["texto"], "Sempre me chame de chefe.")
        self.assertTrue(com["sempre"])

    def test_texto_muito_grande_e_cortado_e_avisa(self):
        cheio = "palavra " * 3000
        item = self._itens(self._cat(extra=cheio))["extra"]
        self.assertTrue(item["cortado"])
        self.assertLessEqual(len(item["texto"]), F.MAX_TEXTO_CARTAO + 10)
        self.assertEqual(item["tamanho"], len(cheio))

    def test_cartao_aprendido_aparece_e_so_ele_e_apagavel(self):
        pasta = self.d / "biblia"
        pasta.mkdir()
        (pasta / "aprendido-erro-pyd.md").write_text(
            "---\nid: aprendido-erro-pyd\ntitulo: Erro no .pyd\npalavras: pyd, acesso negado\n---\nFeche o Zenith e tente de novo.\n", encoding="utf-8")
        (pasta / "meu-cartao.md").write_text("---\nid: meu-cartao\ntitulo: Meu cartão\npalavras: gato\n---\nTexto meu.\n", encoding="utf-8")
        cat = self._cat(pasta)
        itens = self._itens(cat)
        self.assertTrue(itens["aprendido-erro-pyd"]["apagavel"])
        self.assertEqual(itens["aprendido-erro-pyd"]["origem"], "aprendido")
        self.assertFalse(itens["meu-cartao"]["apagavel"])
        self.assertFalse(itens["essencial"]["apagavel"])
        self.assertTrue(any(g["titulo"].startswith("Aprendidas com você") for g in cat["grupos"]))

    def test_apagar_aprendido_so_apaga_aprendido(self):
        pasta = self.d / "biblia"
        pasta.mkdir()
        (pasta / "aprendido-teste-abc.md").write_text("---\nid: aprendido-teste-abc\ntitulo: T\npalavras: x\n---\ncorpo\n", encoding="utf-8")
        (pasta / "meu-cartao.md").write_text("---\nid: meu-cartao\ntitulo: M\npalavras: x\n---\ncorpo\n", encoding="utf-8")
        ok, _ = F.apagar_aprendido("aprendido-teste-abc", pasta)
        self.assertTrue(ok)
        self.assertFalse((pasta / "aprendido-teste-abc.md").exists())
        ok, msg = F.apagar_aprendido("meu-cartao", pasta)
        self.assertFalse(ok)
        self.assertTrue((pasta / "meu-cartao.md").exists())            # arquivo seu: o painel não apaga
        ok, _ = F.apagar_aprendido("../config/settings", pasta)        # nome com caminho: recusado
        self.assertFalse(ok)

    def test_categorias_nunca_levanta_erro(self):
        with mock.patch.object(F, "categoria_biblia", side_effect=RuntimeError("quebrou")):
            cats = F.categorias(bib=_BibFalsa([]))
        self.assertEqual([c["id"] for c in cats], ["fontes"])           # a outra metade continua aparecendo


class ProjetosCompletosTests(_Tmp):
    def _criacoes(self):
        r = self.d / "creations"
        for rel in ("programas/jogo_da_velha/main.py", "programas/jogo_da_velha/util.py", "programas/simulador/index.html",
                    "programas/simulador/app.js", "programas/blink/blink.ino", "web/pagina.html", "imagens/gato.png"):
            p = r / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        return r

    def test_projetos_completos_sao_so_os_de_varios_arquivos(self):
        cats = {c["id"]: c for c in PJ.indexar(self._criacoes())["categorias"]}
        nomes = {i["nome"] for g in cats["projetos"]["grupos"] for i in g["itens"]}
        self.assertEqual(nomes, {"jogo_da_velha", "simulador"})         # blink.ino tem 1 arquivo: é só um programa
        self.assertEqual(cats["programas"]["total"], 3)

    def test_o_total_nao_conta_o_mesmo_projeto_duas_vezes(self):
        ind = PJ.indexar(self._criacoes())
        self.assertEqual(ind["total"], 3 + 1 + 1)                      # programas + sites + imagens

    def test_toda_categoria_de_criacao_tem_o_grupo(self):
        for c in PJ.indexar(self._criacoes())["categorias"]:
            self.assertEqual(c["grupo"], "criacoes")

    def test_texto_do_chat_nao_repete_nem_lista_a_base(self):
        ind = PJ.indexar(self._criacoes())
        ind["categorias"] += [{"id": "biblia", "titulo": "Bíblia", "grupo": "base", "total": 14, "grupos": []}]
        txt = PJ.formatar_texto(ind)
        self.assertEqual(txt.count("jogo_da_velha"), 1)
        self.assertNotIn("Bíblia", txt)
        self.assertNotIn("Projetos completos", txt)


class HeadlessTests(_Tmp):
    def _headless(self):
        from brain import zenith_headless as H
        h = object.__new__(H.ZenithHeadlessBrain)
        h.settings = mock.MagicMock()
        h.settings.get = lambda k, d=None: {"user_name": "Anderson", "persona_name": "Zenith"}.get(k, d)
        h.bridge = mock.MagicMock()
        return h

    def test_painel_recebe_o_que_ela_criou_e_o_que_ela_usa_como_base(self):
        h = self._headless()
        r = self.d / "creations"
        (r / "programas" / "a").mkdir(parents=True)
        (r / "programas" / "a" / "a.py").write_text("print(1)")
        with mock.patch.object(PJ, "raiz_padrao", return_value=r), \
                mock.patch.object(B, "padrao", return_value=B.Biblioteca(self.d / "bib")), \
                mock.patch.object(CO, "pasta_biblia", return_value=self.d / "biblia"), \
                mock.patch.object(BI, "carregar_extra", return_value=""):
            h._handle_list_projetos()
        msg = h.bridge.send.call_args[0][0]
        self.assertEqual(msg["action"], "projetos_dados")
        grupos = {c["id"]: c["grupo"] for c in msg["categorias"]}
        self.assertEqual(grupos["programas"], "criacoes")
        self.assertEqual((grupos["fontes"], grupos["biblia"]), ("base", "base"))

    def test_tirar_documento_avisa_e_reenvia_o_painel(self):
        h = self._headless()
        with mock.patch.object(F, "tirar_fonte", return_value=(True, "Tirei \"x.pdf\" da biblioteca.")) as t, \
                mock.patch.object(h, "_handle_list_projetos") as reenviar:
            h._handle_fonte_remover({"id": "abc"})
        t.assert_called_once_with("abc")
        reenviar.assert_called_once()
        self.assertEqual(h.bridge.send.call_args[0][0]["text"], "Tirei \"x.pdf\" da biblioteca.")

    def test_adicionar_documento_usa_a_mesma_rotina_do_comando(self):
        h = self._headless()
        chamadas = []
        h._rodar_biblioteca_add = lambda a: chamadas.append(("add", a["caminho"]))
        h._handle_list_projetos = lambda d=None: chamadas.append(("painel",))
        with mock.patch("threading.Thread") as Th:
            Th.side_effect = lambda target, daemon=None, **kw: mock.MagicMock(start=lambda: target())
            h._handle_fonte_add({"caminho": "C:/docs/apostila.pdf"})
        self.assertEqual(chamadas, [("add", "C:/docs/apostila.pdf"), ("painel",)])
        h._handle_fonte_add({"caminho": ""})                            # vazio não faz nada
        self.assertEqual(len(chamadas), 2)

    def test_acoes_registradas_no_despachante(self):
        txt = (RAIZ / "brain/zenith_headless.py").read_text(encoding="utf-8")
        for a in ('"fonte_add": self._handle_fonte_add', '"fonte_remover": self._handle_fonte_remover',
                  '"fonte_apagar_aprendido": self._handle_fonte_apagar_aprendido'):
            self.assertIn(a, txt)


class GodotEstruturaTests(unittest.TestCase):
    def test_conector_tem_as_tres_acoes_novas(self):
        c = (RAIZ / "body/zenith/brain_connector.gd").read_text(encoding="utf-8")
        for f in ("func request_fonte_add(", "func request_fonte_remover(", "func request_fonte_apagar_aprendido("):
            self.assertIn(f, c)
        for a in ('"action": "fonte_add"', '"action": "fonte_remover"', '"action": "fonte_apagar_aprendido"'):
            self.assertIn(a, c)

    def test_painel_desenha_as_duas_partes_e_os_dois_tipos_de_linha(self):
        u = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")
        for trecho in ("PROJETOS_GRUPOS", '"O que ela criou"', '"O que ela usa como base"', "func _linha_fonte(", "func _linha_biblia(",
                       "func _botao_confirmar(", "func _abrir_dialogo_fonte(", "brain.request_fonte_remover(id)",
                       "brain.request_fonte_apagar_aprendido(id)", 'tipo_item == "biblia"', 'tipo_item == "fonte"'):
            self.assertIn(trecho, u)

    def test_remover_pede_confirmacao_em_dois_toques(self):
        u = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")
        self.assertIn('_botao_confirmar("Tirar da biblioteca", "Confirmar?"', u)
        self.assertIn('_botao_confirmar("Apagar", "Confirmar?"', u)

    def test_nomes_de_acao_do_corpo_batem_com_os_do_cerebro(self):
        c = (RAIZ / "body/zenith/brain_connector.gd").read_text(encoding="utf-8")
        h = (RAIZ / "brain/zenith_headless.py").read_text(encoding="utf-8")
        for a in ("fonte_add", "fonte_remover", "fonte_apagar_aprendido"):
            self.assertIn(f'"{a}"', c)
            self.assertIn(f'"{a}":', h)


if __name__ == "__main__":
    unittest.main()
