"""
Testes do v21 — o que o Anderson pediu depois de testar o v20:
  * buscar na web / imagens SEM chave de API (parsers com HTML de exemplo; NENHUM teste usa a rede);
  * download de imagem com segurança (SSRF, tipo, tamanho);
  * criar imagens de verdade (zenith_img) — e MOSTRAR no chat;
  * a "Bíblia" que equaliza o conhecimento de qualquer IA;
  * a IA controlando o corpo (<corpo>) e sabendo que tem corpo;
  * contratos Python <-> Godot.
Rodar: python -m unittest tests.test_v21 -v
"""
import io
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

from brain import zenith_busca as B
from brain import zenith_biblia as BI
from brain import zenith_gestos as G
from brain import zenith_img as IMG


def _real(modulo):
    try:
        return getattr(__import__(modulo), "__file__", None) is not None
    except Exception:
        return False


# ------------------------------------------------------------------ HTML de exemplo
DDG_HTML = """
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpt.wikipedia.org%2Fwiki%2FRe%3AZero&amp;rut=abc">Re:Zero &mdash; Wikipédia</a></h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpt.wikipedia.org%2Fwiki%2FRe%3AZero">Re:Zero é uma <b>série</b> de light novels &amp; anime.</a>
</div>
<div class="result result--ad"><a class="result__a" href="//duckduckgo.com/y.js?ad_provider=bing&amp;u=x">Anúncio</a>
  <a class="result__snippet">propaganda</a></div>
<div class="result"><a class="result__a" href="https://example.org/pagina">Outro resultado</a>
  <a class="result__snippet" href="x">Trecho do outro.</a></div>
"""

BING_HTML = """
<ol id="b_results">
 <li class="b_algo" data-id=""><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=1&amp;u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9hcnRpZ28&amp;ntb=1">Artigo <strong>legal</strong></a></h2>
   <div class="b_caption"><p>Um trecho do artigo &amp; mais.</p></div></li>
 <li class="b_algo"><h2><a href="https://exemplo.net/x">Segundo</a></h2><p>Outro trecho.</p></li>
 <li class="b_ad"><h2><a href="https://anuncio.com">Ad</a></h2></li>
</ol>
"""

# formato REAL do Bing: aspas duplas e &quot; dentro do atributo m (+ um com aspas simples, por garantia)
BING_IMG_HTML = (
    '<a class="iusc" style="height:200px" m="{&quot;cid&quot;:&quot;x&quot;,&quot;purl&quot;:&quot;https://example.org/p&quot;,'
    '&quot;murl&quot;:&quot;https://img.example.org/a.jpg&quot;,&quot;turl&quot;:&quot;https://tse1.mm.bing.net/th?id=1&quot;,'
    '&quot;t&quot;:&quot;Rem &amp;amp; Ram&quot;}" mad="{}" href="/x">x</a>'
    '<a class="iusc" m="{&quot;murl&quot;:&quot;ftp://nao.vale/b.jpg&quot;,&quot;t&quot;:&quot;ruim&quot;}">y</a>'
    "<a class=\"iusc\" m='{\"murl\":\"https://img.example.org/c.png\",\"t\":\"Terceira\"}'>z</a>"
)


# ======================================================================
class ParsersTests(unittest.TestCase):
    def test_ddg_desembrulha_link_ignora_anuncio_e_pega_trecho(self):
        r = B.parse_ddg_html(DDG_HTML)
        self.assertEqual([x["url"] for x in r], ["https://pt.wikipedia.org/wiki/Re:Zero", "https://example.org/pagina"])
        self.assertEqual(r[0]["titulo"], "Re:Zero — Wikipédia")
        self.assertEqual(r[0]["trecho"], "Re:Zero é uma série de light novels & anime.")
        self.assertEqual(r[1]["trecho"], "Trecho do outro.")

    def test_bing_texto_desembrulha_base64_e_ignora_anuncio(self):
        r = B.parse_bing_html(BING_HTML)
        self.assertEqual(r[0]["url"], "https://example.com/artigo")
        self.assertEqual(r[0]["titulo"], "Artigo legal")
        self.assertEqual(r[0]["trecho"], "Um trecho do artigo & mais.")
        self.assertEqual(len(r), 2)

    def test_bing_imagens(self):
        r = B.parse_bing_imagens(BING_IMG_HTML)
        self.assertEqual([x["url"] for x in r], ["https://img.example.org/a.jpg", "https://img.example.org/c.png"])
        self.assertEqual(r[0]["titulo"], "Rem & Ram")
        self.assertEqual(r[0]["miniatura"], "https://tse1.mm.bing.net/th?id=1")

    def test_wikipedia_commons_openverse(self):
        w = B.parse_wikipedia({"query": {"search": [{"title": "Física quântica", "snippet": "a <span>b</span>"}]}})
        self.assertEqual(w[0]["url"], "https://pt.wikipedia.org/wiki/F%C3%ADsica_qu%C3%A2ntica")
        self.assertEqual(w[0]["trecho"], "a b")
        c = B.parse_commons({"query": {"pages": {"2": {"index": 2, "title": "File:B.png", "imageinfo": [{"url": "https://u/b.png"}]},
                                                  "1": {"index": 1, "title": "File:A.jpg", "imageinfo": [{
                                                      "url": "https://u/a.jpg", "thumburl": "https://u/t.jpg",
                                                      "descriptionurl": "https://c/A",
                                                      "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}})
        self.assertEqual([x["titulo"] for x in c], ["A.jpg", "B.png"])
        self.assertEqual(c[0]["licenca"], "CC BY-SA 4.0")
        o = B.parse_openverse({"results": [{"url": "https://o/1.jpg", "title": "T", "license": "by", "license_version": "2.0"},
                                           {"url": "javascript:x"}]})
        self.assertEqual(len(o), 1)
        self.assertIn("CC BY", o[0]["licenca"])

    def test_lixo_nao_quebra(self):
        for f in (B.parse_ddg_html, B.parse_bing_html, B.parse_bing_imagens):
            self.assertEqual(f(""), [])
            self.assertEqual(f(None), [])
            self.assertEqual(f("<<<<>>> <a"), [])

    def test_deteccao_de_bloqueio(self):
        self.assertTrue(B.parece_bloqueio("<div class='anomaly-modal'>"))
        self.assertTrue(B.parece_bloqueio("Please complete the CAPTCHA"))
        self.assertFalse(B.parece_bloqueio(DDG_HTML))


class FalsaResposta:
    def __init__(self, texto="", json_=None, status=200, headers=None, conteudo=b"", url=""):
        self.text, self._j, self.status_code, self.headers = texto, json_, status, headers or {}
        self._c, self.url = conteudo, url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._j

    def iter_content(self, n):
        for i in range(0, len(self._c), n):
            yield self._c[i:i + n]


class FalsaSessao:
    def __init__(self, respostas):
        self.respostas, self.chamadas = respostas, []

    def _r(self, url):
        self.chamadas.append(url)
        for chave, r in self.respostas.items():
            if chave in url:
                if isinstance(r, Exception):
                    raise r
                return r
        raise RuntimeError("sem resposta de teste para " + url)

    def get(self, url, **kw):
        return self._r(url)

    def post(self, url, **kw):
        return self._r(url)


class BuscaTests(unittest.TestCase):
    def test_usa_a_primeira_fonte_que_responde(self):
        s = FalsaSessao({"html.duckduckgo.com": FalsaResposta(DDG_HTML)})
        r = B.buscar_texto("re zero", sessao=s)
        self.assertTrue(r["ok"])
        self.assertEqual(r["fonte"], "DuckDuckGo")
        self.assertEqual(len(s.chamadas), 1)

    def test_cai_para_a_proxima_quando_a_primeira_falha(self):
        s = FalsaSessao({"html.duckduckgo.com": RuntimeError("timeout"),
                         "bing.com/search": FalsaResposta(BING_HTML)})
        r = B.buscar_texto("algo", sessao=s)
        self.assertTrue(r["ok"] and r["fonte"] == "Bing")
        self.assertIn("DuckDuckGo", r["erros"][0])

    def test_wikipedia_e_a_rede_de_seguranca(self):
        s = FalsaSessao({"html.duckduckgo.com": RuntimeError("x"), "bing.com/search": RuntimeError("y"),
                         "wikipedia.org": FalsaResposta(json_={"query": {"search": [{"title": "Tema", "snippet": "s"}]}})})
        r = B.buscar_texto("tema", sessao=s)
        self.assertTrue(r["ok"] and r["fonte"] == "Wikipédia")

    def test_tudo_falhando_da_mensagem_clara_e_nao_levanta(self):
        s = FalsaSessao({"duckduckgo": RuntimeError("a"), "bing": RuntimeError("b"), "wikipedia": RuntimeError("c")})
        r = B.buscar_texto("x", sessao=s)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["erros"]), 3)
        txt = B.formatar_texto("x", r)
        self.assertIn("tente de novo", txt)
        self.assertNotIn("chave", txt.lower().replace("sem chave", ""))

    def test_bloqueio_vira_erro_e_tenta_a_proxima(self):
        s = FalsaSessao({"html.duckduckgo.com": FalsaResposta("<div class='anomaly-modal'></div>"),
                         "bing.com/search": FalsaResposta(BING_HTML)})
        r = B.buscar_texto("x", sessao=s)
        self.assertEqual(r["fonte"], "Bing")
        self.assertIn("verificação", " ".join(r["erros"]))

    def test_consulta_vazia(self):
        self.assertFalse(B.buscar_texto("   ")["ok"])
        self.assertFalse(B.buscar_imagens("")["ok"])

    def test_imagens_com_rede_de_seguranca_livre(self):
        s = FalsaSessao({"bing.com/images": FalsaResposta("<html></html>"),
                         "commons.wikimedia.org": FalsaResposta(json_={"query": {"pages": {"1": {"index": 1, "title": "File:A.jpg",
                                                                  "imageinfo": [{"url": "https://u/a.jpg"}]}}}})})
        r = B.buscar_imagens("gato", sessao=s)
        self.assertTrue(r["ok"] and r["fonte"] == "Wikimedia Commons")

    def test_formatacao_para_a_ia_menciona_direitos_e_arquivos(self):
        res = {"ok": True, "fonte": "Wikimedia Commons", "resultados": [
            {"titulo": "A", "url": "https://u/a.jpg", "licenca": "CC BY 4.0", "pagina": "https://c/A"}]}
        t = B.formatar_imagens("gato", res, ["/c/gato_1.jpg"])
        self.assertIn("CC BY 4.0", t)
        self.assertIn("/c/gato_1.jpg", t)
        self.assertIn("Direitos", t)
        self.assertIn("sem chave", t)


# ======================================================================
@unittest.skipUnless(_real("PIL"), "Pillow não instalado")
class DownloadSeguroTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (20, 20), (200, 10, 10)).save(buf, "PNG")
        self.png = buf.getvalue()
        self.publico = lambda host, *a: [(2, 1, 6, "", ("93.184.216.34", 0))]

    def tearDown(self):
        self._tmp.cleanup()

    def test_bloqueia_endereco_local_e_privado(self):
        for url in ("http://localhost/a.png", "http://127.0.0.1/a.png", "http://10.0.0.5/a.png",
                    "http://192.168.1.1/a.png", "http://169.254.169.254/latest/meta-data", "http://[::1]/a.png",
                    "file:///C:/Windows/win.ini", "ftp://x/a.png", "javascript:alert(1)"):
            ok, motivo = B.url_publica(url)
            self.assertFalse(ok, url)
            self.assertTrue(motivo)

    def test_dominio_que_resolve_para_ip_privado_tambem_e_bloqueado(self):
        interno = lambda host, *a: [(2, 1, 6, "", ("10.1.2.3", 0))]
        self.assertFalse(B.url_publica("https://parece-normal.com/a.png", interno)[0])
        self.assertTrue(B.url_publica("https://parece-normal.com/a.png", self.publico)[0])

    def test_baixa_imagem_valida(self):
        s = FalsaSessao({"img.test": FalsaResposta(headers={"Content-Type": "image/png"}, conteudo=self.png,
                                                    url="https://img.test/a.png")})
        r = B.baixar_imagem("https://img.test/a.png", self.d, nome="Rem & Ram", sessao=s, resolver=self.publico)
        self.assertTrue(r["ok"], r)
        self.assertTrue(Path(r["path"]).is_file())
        self.assertTrue(r["path"].endswith(".png"))
        self.assertNotIn("&", Path(r["path"]).name)

    def test_nao_aceita_o_que_nao_e_imagem(self):
        s = FalsaSessao({"img.test": FalsaResposta(headers={"Content-Type": "text/html"}, conteudo=b"<html>",
                                                    url="https://img.test/a")})
        self.assertFalse(B.baixar_imagem("https://img.test/a", self.d, sessao=s, resolver=self.publico)["ok"])
        s2 = FalsaSessao({"img.test": FalsaResposta(headers={"Content-Type": "image/png"},
                                                     conteudo=b"MZ\x90\x00 isto e um exe", url="https://img.test/a.png")})
        r = B.baixar_imagem("https://img.test/a.png", self.d, sessao=s2, resolver=self.publico)
        self.assertFalse(r["ok"])
        self.assertEqual(list(self.d.iterdir()), [], "nada é gravado quando o conteúdo não é imagem")

    def test_limite_de_tamanho(self):
        grande = b"x" * (B.TETO_BYTES_IMAGEM + 10)
        s = FalsaSessao({"img.test": FalsaResposta(headers={"Content-Type": "image/jpeg"}, conteudo=grande,
                                                    url="https://img.test/a.jpg")})
        r = B.baixar_imagem("https://img.test/a.jpg", self.d, sessao=s, resolver=self.publico)
        self.assertFalse(r["ok"])
        self.assertIn("grande", r["msg"])

    def test_redirecionamento_para_endereco_interno_e_barrado(self):
        s = FalsaSessao({"img.test": FalsaResposta(headers={"Content-Type": "image/png"}, conteudo=self.png,
                                                    url="http://127.0.0.1/segredo.png")})
        r = B.baixar_imagem("https://img.test/a.png", self.d, sessao=s, resolver=self.publico)
        self.assertFalse(r["ok"])

    def test_nao_sobrescreve_arquivo_existente(self):
        s = FalsaSessao({"img.test": FalsaResposta(headers={"Content-Type": "image/png"}, conteudo=self.png,
                                                    url="https://img.test/a.png")})
        a = B.baixar_imagem("https://img.test/a.png", self.d, nome="x", sessao=s, resolver=self.publico)
        b = B.baixar_imagem("https://img.test/a.png", self.d, nome="x", sessao=s, resolver=self.publico)
        self.assertNotEqual(a["path"], b["path"])


# ======================================================================
@unittest.skipUnless(_real("PIL"), "Pillow não instalado")
class ImagensTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self._p = mock.patch.object(IMG, "pasta_criacoes", lambda: self.d)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self._tmp.cleanup()

    def _abre(self, caminho):
        from PIL import Image
        with Image.open(caminho) as im:
            im.load()
            return im.size

    def test_meme_sem_nenhuma_imagem_de_entrada(self):
        """O bug do teste dele: o script exigia uma imagem-base que não existia."""
        with mock.patch("builtins.print") as pr:
            caminho = IMG.meme("QUANDO O CÓDIGO RODA", "DE PRIMEIRA")
        self.assertTrue(Path(caminho).is_file())
        self.assertEqual(self._abre(caminho), (900, 900))
        self.assertTrue(any("IMAGEM_CRIADA:" in str(c) for c in pr.call_args_list))

    def test_meme_com_fundo_inexistente_nao_quebra(self):
        caminho = IMG.meme("a", "b", fundo=str(self.d / "nao_existe.jpg"))
        self.assertTrue(Path(caminho).is_file())

    def test_meme_com_fundo_do_usuario(self):
        from PIL import Image
        base = self.d / "base.png"
        Image.new("RGB", (400, 200), (10, 90, 10)).save(base)
        caminho = IMG.meme("topo", "base", fundo=str(base), largura=600)
        self.assertEqual(self._abre(caminho), (600, 300))

    def test_cartaz_citacao_gradiente_colagem(self):
        c1 = IMG.cartaz("Feira de Ciências", "Colégio Exemplo", tema="neon")
        self.assertEqual(self._abre(c1), (1080, 1350))
        c2 = IMG.citacao("A imaginação é mais importante que o conhecimento.", "Einstein", tema="oceano")
        self.assertEqual(self._abre(c2), (1080, 1080))
        g = IMG.gradiente(64, 32, ("#000", "#fff"), "horizontal")
        self.assertEqual(g.size, (64, 32))
        self.assertEqual(g.getpixel((0, 0))[0], 0)
        self.assertGreater(g.getpixel((63, 0))[0], 250)
        c3 = IMG.colagem([c1, c2, str(self.d / "ruim.png")], colunas=2, tamanho_celula=200)
        self.assertEqual(self._abre(c3), (400, 200), "a imagem inválida é pulada: sobram 2 em 1 linha")

    def test_texto_enorme_e_tema_invalido_nao_quebram(self):
        caminho = IMG.cartaz("PALAVRA" * 40, "x " * 300, tema="inexistente")
        self.assertTrue(Path(caminho).is_file())

    def test_nao_sobrescreve_e_nome_seguro(self):
        a = IMG.meme("a", "b", saida="meu meme/../x")
        b = IMG.meme("a", "b", saida="meu meme/../x")
        self.assertNotEqual(a, b)
        self.assertEqual(Path(a).parent, self.d)

    def test_colagem_sem_imagens_validas_levanta_erro_claro(self):
        with self.assertRaises(ValueError):
            IMG.colagem([str(self.d / "x.png")])

    def test_cabe_no_limite_de_15_segundos(self):
        import time
        t = time.time()
        IMG.cartaz("Título", "Sub")
        self.assertLess(time.time() - t, 8)


# ======================================================================
class BibliaTests(unittest.TestCase):
    def test_bloco_fixo_tem_o_essencial_e_o_corpo_e_cabe(self):
        b = BI.bloco_fixo("Anderson", "Zenith", "C:/criacoes")
        self.assertIn("VOCÊ TEM UM CORPO", b)
        self.assertIn("<corpo>gesto:acenar</corpo>", b)
        self.assertIn("ENTREGUE, NÃO SÓ PERGUNTE", b)
        self.assertIn("Anderson", b)
        self.assertNotIn("{user}", b)
        self.assertNotIn("{persona}", b)
        self.assertLess(len(b), 7600, "o bloco que vai SEMPRE no prompt precisa ser enxuto (v23: ~1,8 mil tokens, 0,2% da janela do Gemini)")

    def test_assunto_certo_puxa_a_secao_certa(self):
        casos = {
            "faz um meme de gato pra mim": "imagens",
            "crie um programa em python que organize minhas notas": "programacao",
            "resolva essa integral de x^2 e calcule a derivada": "matematica",
            "pesquise o preço atual do arduino uno": "pesquisa",
            "explique pra mim o conceito de entropia pra prova": "estudo",
            "como configuro a porta serial do clp": "automacao",
        }
        for msg, esperado in casos.items():
            with self.subTest(msg=msg):
                self.assertIn(esperado, BI.secoes_para(msg))

    def test_conversa_comum_nao_gasta_token(self):
        for msg in ("oi tudo bem?", "bom dia akira", "obrigado!", ""):
            self.assertEqual(BI.guia_para(msg), "", msg)

    def test_no_maximo_duas_secoes(self):
        msg = "crie um programa python com gráfico de física, pesquise na internet e explique pra prova"
        self.assertLessEqual(len(BI.secoes_para(msg)), 2)
        self.assertLessEqual(len(BI.guia_para(msg)), 3200)

    def test_acentos_nao_atrapalham(self):
        self.assertIn("matematica", BI.secoes_para("calcule a derivada"))
        self.assertIn("imagens", BI.secoes_para("DESENHE uma ilustração"))

    def test_regras_de_programacao_ensinam_o_que_deu_errado_no_teste(self):
        t = BI.SECOES["programacao"]["texto"]
        self.assertIn("CHAME o que você definiu", t)
        self.assertIn("arquivo que talvez não exista", t)
        self.assertIn("input()", t)

    def test_imagens_apontam_para_a_biblioteca_pronta(self):
        t = BI.SECOES["imagens"]["texto"]
        for nome in ("meme(", "cartaz(", "citacao(", "from brain.zenith_img import"):
            self.assertIn(nome, t)
        for f in ("meme", "cartaz", "citacao", "gradiente", "colagem"):
            self.assertTrue(hasattr(IMG, f), f)

    def test_extra_do_usuario_entra_limitado(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "biblia_extra.md").write_text("Sempre me chame de chefe. " * 400, encoding="utf-8")
            extra = BI.carregar_extra(t)
            self.assertEqual(len(extra), BI.LIMITE_EXTRA)
            self.assertIn("Sempre me chame", BI.bloco_fixo("A", "K", "x", extra))
            self.assertEqual(BI.carregar_extra(Path(t) / "outra"), "")

    def test_nenhuma_marca_ou_endereco_de_provedor(self):
        import prepare_pendrive as prep
        tudo = BI.gerar_markdown().lower()
        for host in prep.HOSTS_DE_PROVEDOR:
            self.assertNotIn(host, tudo)
        for marca in ("openrouter", "groq", "gemini", "tavily", "openai"):
            self.assertNotIn(marca, tudo)

    def test_nao_afrouxa_os_pilares(self):
        tudo = BI.gerar_markdown().lower()
        self.assertIn("pilares", tudo)
        self.assertIn("anti-romântico", tudo)
        self.assertNotIn("ignore as regras", tudo)

    def test_documento_do_projeto_esta_em_dia(self):
        """O BIBLIA_ZENITH.md é GERADO do módulo; se alguém editar um e esquecer do outro, falha."""
        md = (RAIZ / "BIBLIA_ZENITH.md").read_text(encoding="utf-8")
        self.assertEqual(md, BI.gerar_markdown(),
                         "BIBLIA_ZENITH.md desatualizado — veja a instrução no topo do arquivo para regenerar")

    def test_ferramentas_citadas_existem_no_prompt_do_core(self):
        src = (RAIZ / "brain" / "zenith_core.py").read_text(encoding="utf-8")
        for tag in ("<buscar_web>", "<ler_url>", "<buscar_imagem>", "<executar_python>"):
            self.assertIn(tag, src)
        self.assertIn("biblia.bloco_fixo", src)
        self.assertIn("conhecimento.guia_para", src)   # v22: o core usa o guia unificado (mesmas seções + cartões + perfis)


# ======================================================================
class CorpoDaIATests(unittest.TestCase):
    def test_extrai_gestos_e_emocoes(self):
        txt, cmds = G.extrair_comandos_corpo("Oi! <corpo>gesto:acenar</corpo> Tudo bem? <corpo>emocao:happy</corpo>")
        self.assertEqual(cmds, [("gesto", "acenar"), ("emocao", "happy")])
        self.assertNotIn("<corpo>", txt)
        self.assertIn("Oi!", txt)

    def test_varios_na_mesma_tag_e_apelidos(self):
        _t, cmds = G.extrair_comandos_corpo("<corpo>gesto: oi; emocao: feliz</corpo>")
        self.assertEqual(cmds, [("gesto", "acenar"), ("emocao", "happy")])

    def test_nome_inventado_e_ignorado_mas_a_tag_some(self):
        txt, cmds = G.extrair_comandos_corpo("ok <corpo>gesto:beijo</corpo><corpo>gesto:piscadinha</corpo> fim")
        self.assertEqual(cmds, [])
        self.assertNotIn("corpo", txt)

    def test_limite_e_lixo(self):
        _t, cmds = G.extrair_comandos_corpo("<corpo>" + ";".join(["gesto:negar"] * 20) + "</corpo>")
        self.assertEqual(len(cmds), 3)
        self.assertEqual(G.extrair_comandos_corpo("")[1], [])
        self.assertEqual(G.extrair_comandos_corpo(None)[1], [])
        self.assertEqual(G.extrair_comandos_corpo("<corpo>sem dois pontos</corpo>")[1], [])

    def test_gestos_validos_batem_com_o_godot(self):
        gd = (RAIZ / "body/zenith/akira_vida.gd").read_text(encoding="utf-8")
        bloco = re.search(r"const GESTURE_DURATIONS := \{(.*?)\}", gd, re.S).group(1)
        self.assertEqual(set(re.findall(r'"(\w+)"\s*:', bloco)), set(G.GESTOS_VALIDOS))

    def test_gestos_proibidos_pelo_projeto_nao_existem(self):
        for ruim in ("beijo", "coracao", "piscadinha", "abraco", "ok"):
            self.assertNotIn(ruim, G.GESTOS_VALIDOS)


# ======================================================================
class CoreIntegracaoTests(unittest.TestCase):
    def setUp(self):
        from brain import zenith_core as zc
        self.zc = zc
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self._p = mock.patch.object(zc, "CREATION_DIR", self.d)
        self._p.start()
        c = object.__new__(zc.ZenithCore)
        c.executor = mock.Mock()
        c.settings = mock.Mock()
        c.settings.user_name = "Anderson"
        c.settings.persona_name = "Zenith"
        c.settings.get = lambda k, d=None: {"permissions": {"web_search": "ask"}}.get(k, d)
        self.c = c

    def tearDown(self):
        self._p.stop()
        self._tmp.cleanup()

    def test_tag_de_imagem_e_corpo_sao_reconhecidas_e_somem_do_texto(self):
        self.assertIn("image_search", self.zc.ACTION_TAGS)
        limpo = self.c._remove_tags("Vou buscar. <buscar_imagem>gato</buscar_imagem> <corpo>gesto:acenar</corpo> Pronto")
        self.assertNotIn("<", limpo)
        self.assertIn("Vou buscar.", limpo)

    def test_imagem_criada_pelo_script_vai_pra_fila_do_chat(self):
        antes = self.c._fotografar_imagens()
        nova = self.d / "meme.png"
        nova.write_bytes(b"x")
        self.c._registrar_midias_novas(antes, f"IMAGEM_CRIADA: {nova}")
        m = self.c.pegar_midias()
        self.assertEqual([x["path"] for x in m], [str(nova)])
        self.assertEqual(self.c.pegar_midias(), [], "a fila esvazia depois de entregue")

    def test_so_aparecem_as_imagens_NOVAS(self):
        velha = self.d / "velha.png"
        velha.write_bytes(b"x")
        antes = self.c._fotografar_imagens()
        self.c._registrar_midias_novas(antes, "nada")
        self.assertEqual(self.c.pegar_midias(), [])

    def test_script_que_so_define_funcao_nao_e_sucesso(self):
        """O bug do vídeo: `def criar_meme(...)` sem chamar -> "✅ Código executado" enganava a IA."""
        antes = self.c._fotografar_imagens()
        r = self.c._avisar_se_nada_aconteceu(antes, "✅ Código executado (sem saída de texto).")
        self.assertIn("CHAMAR a função", r)
        self.assertIn("não diga que deu certo", r)

    def test_sem_texto_mas_criou_arquivo_esta_ok(self):
        antes = self.c._fotografar_imagens()
        (self.d / "resultado.csv").write_text("a,b")
        msg = "✅ Código executado (sem saída de texto)."
        self.assertEqual(self.c._avisar_se_nada_aconteceu(antes, msg), msg)

    def test_saida_com_texto_nao_ganha_aviso(self):
        antes = self.c._fotografar_imagens()
        self.assertEqual(self.c._avisar_se_nada_aconteceu(antes, "42"), "42")

    def test_fila_tem_limite(self):
        antes = self.c._fotografar_imagens()
        for i in range(9):
            (self.d / f"i{i}.png").write_bytes(b"x")
        self.c._registrar_midias_novas(antes, "")
        self.assertLessEqual(len(self.c.pegar_midias()), self.c.MAX_MIDIAS)

    def test_busca_de_imagem_baixa_e_enfileira(self):
        arq = self.d / "web" / "gato_1.jpg"
        arq.parent.mkdir()
        arq.write_bytes(b"x")
        self.c.executor.run_image_search.return_value = ("Imagens encontradas ...", [str(arq)])
        self.c._call_provider = lambda prompt: "Achei uma foto de gato."
        r = self.c._image_search_and_answer("gato", "mostre um gato")
        self.assertEqual(r, "Achei uma foto de gato.")
        self.assertEqual([m["path"] for m in self.c.pegar_midias()], [str(arq)])

    def test_busca_de_imagem_que_falha_devolve_o_erro_sem_inventar(self):
        self.c.executor.run_image_search.return_value = ("❌ Não consegui buscar imagens ...", [])
        r = self.c._image_search_and_answer("gato", "mostre um gato")
        self.assertTrue(r.startswith("❌"))
        self.assertEqual(self.c.pegar_midias(), [])

    def test_sem_a_chave_da_tavily_a_busca_funciona(self):
        from brain import zenith_executor as ze
        ex = object.__new__(ze.ZenithExecutor)
        fake = {"ok": True, "fonte": "DuckDuckGo", "resultados": [{"titulo": "T", "url": "https://x.org", "trecho": "tt"}], "erros": []}
        with mock.patch.object(ze.zenith_busca, "buscar_texto", return_value=fake) as bt, \
                mock.patch.object(ze.requests, "post", side_effect=AssertionError("não devia chamar a Tavily sem chave")):
            txt = ex.run_websearch("física quântica", "")
        bt.assert_called_once()
        self.assertIn("https://x.org", txt)
        self.assertIn("sem chave", txt)

    def test_com_chave_tenta_a_tavily_e_cai_no_sem_chave_se_falhar(self):
        from brain import zenith_executor as ze
        ex = object.__new__(ze.ZenithExecutor)
        fake = {"ok": True, "fonte": "Bing", "resultados": [{"titulo": "T", "url": "https://y.org", "trecho": ""}], "erros": []}
        with mock.patch.object(ze.requests, "post", side_effect=RuntimeError("fora do ar")), \
                mock.patch.object(ze.zenith_busca, "buscar_texto", return_value=fake):
            txt = ex.run_websearch("x", "chave-qualquer")
        self.assertIn("https://y.org", txt)

    def test_script_da_ia_consegue_importar_a_biblioteca_de_imagens(self):
        """O run_python precisa por a pasta do projeto no PYTHONPATH (fora do .exe)."""
        src = (RAIZ / "brain" / "zenith_executor.py").read_text(encoding="utf-8")
        self.assertIn('env["PYTHONPATH"]', src)
        self.assertIn("from brain import zenith_img", src)


class HeadlessIntegracaoTests(unittest.TestCase):
    def setUp(self):
        from brain import zenith_headless as h
        self.h = h
        b = object.__new__(h.ZenithHeadlessBrain)
        b.enviados = []
        b.bridge = mock.Mock()
        b.bridge.send = b.enviados.append
        b.core = mock.Mock()
        b.core.pegar_midias.return_value = [{"path": "C:/c/meme.png", "caption": "meme.png"}]
        self.b = b

    def test_manda_cada_imagem_para_o_corpo(self):
        self.b._enviar_midias()
        self.assertEqual(self.b.enviados, [{"action": "chat_image", "path": "C:/c/meme.png", "caption": "meme.png"}])

    def test_erro_ao_enviar_imagem_nao_derruba_nada(self):
        self.b.core.pegar_midias.side_effect = RuntimeError("boom")
        self.b._enviar_midias()

    def test_busca_de_imagem_nao_encadeia_como_acao_de_codigo(self):
        # v22: + "learn"; v23: + "observe"; v27: + "image_gen".
        # CORREÇÃO (este teste falhava por motivo errado): ele procurava a linha INTEIRA, terminando em
        # `"observe")`. Quando a v28 acrescentou mais tipos à lista, a linha passou a continuar na linha de
        # baixo e o texto deixou de bater — mas o CÓDIGO estava certo, a lista só tinha crescido (e a
        # proteção, ficado mais forte). O teste acusava um problema de segurança que não existia.
        # Agora ele lê a lista inteira (de `pending.kind not in (` até o fecha-parênteses) e confere TIPO POR
        # TIPO. Ficou imune a quebra de linha e é mais rigoroso do que antes: se alguém tirar QUALQUER um
        # desses tipos da lista, o teste diz exatamente qual sumiu.
        src = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        inicio = src.index("pending.kind not in (")
        lista = src[inicio:src.index(")", inicio)]
        for tipo in ("search", "read_url", "image_search", "image_gen", "learn", "observe"):
            self.assertIn(f'"{tipo}"', lista,
                          f'{tipo} saiu da lista que NÃO encadeia como ação de código (Pilar 1)')

    def test_corpo_pedido_pela_ia_vence_o_palpite_automatico(self):
        src = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('result.get("body_cmds")', src)
        self.assertIn("if gesto_ia:", src)
        self.assertIn("self._enviar_midias()", src)


# ======================================================================
class GodotV21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = RAIZ / "body" / "zenith"
        cls.body = (d / "akira_body.gd").read_text(encoding="utf-8")
        cls.ui = (d / "ui_manager.gd").read_text(encoding="utf-8")
        cls.con = (d / "brain_connector.gd").read_text(encoding="utf-8")
        cls.vida = (d / "akira_vida.gd").read_text(encoding="utf-8")

    def test_sinal_e_balao_de_imagem(self):
        self.assertIn("signal chat_image", self.con)
        self.assertIn('emit_signal("chat_image"', self.con)
        self.assertIn("brain.chat_image.connect(_on_chat_image)", self.ui)
        self.assertIn("func _on_chat_image(", self.ui)
        self.assertIn("OS.shell_open(path)", self.ui)

    def test_acao_enviada_pelo_python_e_a_que_o_godot_escuta(self):
        py = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('"action": "chat_image"', py)
        self.assertIn('"chat_image":', self.con)

    def test_opacidade_em_grupo_tem_saida_segura(self):
        self.assertIn("if main_cam == null:\n\t\treturn", self.body)
        self.assertIn("if _op_rect.texture == null:\n\t\t_opacidade_desligar()", self.body)
        self.assertIn("main_cam.cull_mask = 0", self.body)
        codigo = [l for l in self.body.split("\n") if not l.strip().startswith("#")]
        self.assertEqual(sum(1 for l in codigo if "cull_mask = 0" in l), 1, "só a câmera principal fica sem enxergar")

    def test_vida_ficou_mais_suave(self):
        self.assertIn("var _emotion_strength: float = 0.55", self.vida)
        self.assertIn("randf_range(0.18, 0.55)", self.vida)
        self.assertIn("alvo_pitch = ny * 0.12", self.vida)

    def test_sintaxe_basica_dos_arquivos_mexidos(self):
        par = {")": "(", "]": "[", "}": "{"}
        for nome, txt in (("akira_body.gd", self.body), ("ui_manager.gd", self.ui),
                          ("brain_connector.gd", self.con), ("akira_vida.gd", self.vida)):
            pilha = []
            for n, linha in enumerate(txt.split("\n"), 1):
                self.assertFalse(linha.startswith(" "), f"{nome}:{n}")
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
                    elif c == "#":
                        break
                    else:
                        out.append(c)
                    i += 1
                for c in out:
                    if c in "([{":
                        pilha.append((c, n))
                    elif c in ")]}":
                        self.assertTrue(pilha and pilha[-1][0] == par[c], f"{nome}:{n}")
                        pilha.pop()
            self.assertEqual(pilha, [], nome)

    def test_sem_funcoes_repetidas(self):
        for nome, txt in (("akira_body.gd", self.body), ("ui_manager.gd", self.ui)):
            fs = re.findall(r"^func (\w+)", txt, re.M)
            self.assertEqual({f for f in fs if fs.count(f) > 1}, set(), nome)


class PendriveV21Tests(unittest.TestCase):
    def test_biblia_extra_e_dados_novos_saem_do_pendrive_e_do_reset(self):
        import prepare_pendrive as prep
        from brain import zenith_reset as R
        self.assertIn("biblia_extra.md", [Path(p).name for p in prep._FILES_TO_REMOVE])
        self.assertIn("config/biblia_extra.md", R.ARQUIVOS)

    def test_pasta_web_das_imagens_baixadas_e_limpa(self):
        from brain import zenith_reset as R
        self.assertIn("creations", R.PASTAS)          # creations/web/ fica dentro
        import prepare_pendrive as prep
        self.assertIn("creations", prep._FOLDERS_TO_EMPTY)


if __name__ == "__main__":
    unittest.main()
