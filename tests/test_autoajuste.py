"""Testes do autoajuste (brain/zenith_autoajuste.py) e do carregador de ajustes (brain/zenith_overlay.py).

Usa um MINI-PROJETO falso em pasta temporária (brain/zenith_demo.py + tests/test_demo.py). O único código "proposto"
que roda é o do próprio teste, numa cópia temporária, via `python -m unittest` de verdade.
NÃO provam: o comportamento dentro do .exe do PyInstaller, no Windows real, nem com o Zenith inteiro.
"""
import hashlib
import importlib
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from brain import zenith_autoajuste as AJ        # noqa: E402
from brain import zenith_overlay as OV           # noqa: E402

DEMO = '''"""modulo de exemplo"""


def soma(a, b):
    return a - b          # bug de propósito


def nome():
    return "demo"
'''
TESTE = '''import unittest
from brain import zenith_demo


class DemoTests(unittest.TestCase):
    def test_soma(self):
        self.assertEqual(zenith_demo.soma(2, 3), 5)

    def test_nome(self):
        self.assertEqual(zenith_demo.nome(), "demo")
'''


def proposta(arquivo="brain/zenith_demo.py", motivo="A soma estava subtraindo; troquei o sinal.", edicoes=None, **extra):
    d = {"arquivo": arquivo, "motivo": motivo,
         "edicoes": edicoes if edicoes is not None else [{"antigo": "return a - b          # bug de propósito", "novo": "return a + b"}]}
    d.update(extra)
    return json.dumps(d)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="za_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.raiz = self.tmp / "projeto"
        (self.raiz / "brain").mkdir(parents=True)
        (self.raiz / "tests").mkdir()
        (self.raiz / "tests" / "__init__.py").write_text("")
        (self.raiz / "brain" / "zenith_core.py").write_text("# marcador\n")
        (self.raiz / "brain" / "zenith_demo.py").write_text(DEMO, encoding="utf-8")
        (self.raiz / "brain" / "zenith_outro.py").write_text("X = 1\n")
        (self.raiz / "tests" / "test_demo.py").write_text(TESTE, encoding="utf-8")
        self.aj = AJ.Ajustes(self.raiz, self.tmp / "config" / "ajustes")
        self.original = (self.raiz / "brain" / "zenith_demo.py").read_bytes()

    def assertIntocado(self):
        self.assertEqual((self.raiz / "brain" / "zenith_demo.py").read_bytes(), self.original)


# ------------------------------------------------------------------ validação
class ValidacaoTests(Base):
    def recusa(self, bruto, trecho=""):
        r = self.aj.propor(bruto)
        self.assertFalse(r["ok"], r)
        self.assertIn(trecho, r["mensagem"])
        self.assertEqual(self.aj.listar(), [])
        self.assertIntocado()
        return r

    def test_proposta_boa_e_guardada_sem_mudar_nada(self):
        r = self.aj.propor(proposta())
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["id"], 1)
        self.assertIn("Nada foi alterado", r["mensagem"])
        self.assertIn("/ajuste testar 1", r["mensagem"])
        p = self.aj.carregar(1)
        self.assertEqual(p["estado"], "pendente")
        self.assertIn("-    return a - b", self.aj.ver(1))
        self.assertIn("+    return a + b", self.aj.ver(1))
        self.assertIntocado()
        self.assertFalse((self.tmp / "config" / "ajustes" / "overlay").exists())

    def test_ids_crescem(self):
        self.assertEqual(self.aj.propor(proposta())["id"], 1)
        self.assertEqual(self.aj.propor(proposta(edicoes=[{"antigo": 'return "demo"', "novo": 'return "demo2"'}]))["id"], 2)

    def test_aceita_json_dentro_de_cerca_de_codigo(self):
        r = self.aj.propor("```json\n" + proposta() + "\n```")
        self.assertTrue(r["ok"], r)

    def test_modulos_protegidos_nao_podem_ser_propostos(self):
        for nome in ("zenith_core", "zenith_gatekeeper", "zenith_executor", "zenith_settings", "zenith_atualizar",
                     "zenith_overlay", "zenith_autoajuste", "zenith_commands", "zenith_headless"):
            self.aj.propor(proposta(arquivo=f"brain/{nome}.py"))      # nem chega a checar o conteúdo
            self.assertEqual(self.aj.listar(), [], nome)
        self.recusa(proposta(arquivo="brain/zenith_core.py"), "protegido")

    def test_nome_de_arquivo_invalido_ou_fora_da_pasta(self):
        for ruim in ("../config/settings.json", "brain/../x.py", "tools/gerar_release.py", "brain/sub/zenith_a.py",
                     "C:/x/zenith_a.py", "", "zenith_Demo.py;rm"):
            self.recusa(proposta(arquivo=ruim))

    def test_json_invalido_e_motivo_curto(self):
        self.recusa("isto nao e json", "JSON")
        self.recusa(proposta(motivo="x"), "motivo")

    def test_antigo_precisa_existir_e_ser_unico(self):
        self.recusa(proposta(edicoes=[{"antigo": "return a * b", "novo": "return a"}]), "não existe")
        self.recusa(proposta(edicoes=[{"antigo": "return", "novo": "pass"}]), "aparece")
        self.recusa(proposta(edicoes=[{"antigo": "   ", "novo": "x"}]), "vazio")
        self.recusa(proposta(edicoes=[{"antigo": "return a - b          # bug de propósito", "novo": "return a - b          # bug de propósito"}]), "iguais")
        self.recusa(proposta(edicoes=[]), "edicoes")

    def test_arquivo_que_nao_compila(self):
        self.recusa(proposta(edicoes=[{"antigo": "return a - b          # bug de propósito", "novo": "return a +"}]), "compila")

    def test_nao_deixa_acrescentar_o_que_so_atualizacao_oficial_traz(self):
        casos = {
            "import subprocess\n    return a + b": "subprocess",
            "return a + b + eval('1')": "eval",
            "import urllib.request\n    return a + b": "rede",
            "import os\n    os.remove('x')\n    return a + b": "apagar",
            "return a + b  # https://evil.example/x": "endereço",
            "import ctypes\n    return a + b": "ctypes",
            "import pickle\n    return a + b": "serialização",
            "import sys\n    sys.modules['x'] = 1\n    return a + b": "sys.modules",
            "from brain import zenith_gatekeeper\n    return a + b": "segurança",
            "__import__('os')\n    return a + b": "importação dinâmica",
        }
        for novo, palavra in casos.items():
            r = self.aj.propor(proposta(edicoes=[{"antigo": "return a - b          # bug de propósito", "novo": novo}]))
            self.assertFalse(r["ok"], novo)
            self.assertIn(palavra, r["mensagem"], novo)
        self.assertEqual(self.aj.listar(), [])

    def test_quem_ja_tinha_pode_manter_a_mesma_quantidade(self):
        (self.raiz / "brain" / "zenith_outro.py").write_text("import subprocess\n\n\ndef a():\n    return subprocess.run(['x'])\n\n\ndef b():\n    return 1\n")
        r = self.aj.propor(proposta(arquivo="brain/zenith_outro.py", edicoes=[{"antigo": "return 1", "novo": "return 2"}]))
        self.assertTrue(r["ok"], r)

    def test_avisos_de_atencao(self):
        novo = "open('x.txt', 'w').write('1')\n    return a + b"
        r = self.aj.propor(proposta(edicoes=[{"antigo": "return a - b          # bug de propósito", "novo": novo}]))
        self.assertTrue(r["ok"], r)
        self.assertIn("escreve em arquivo", " ".join(self.aj.carregar(r["id"])["avisos"]))
        r2 = self.aj.propor(proposta(edicoes=[{"antigo": 'return "demo"', "novo": "import numpy\n    return 'demo'"}]))
        self.assertIn("numpy", " ".join(self.aj.carregar(r2["id"])["avisos"]))

    def test_preserva_crlf(self):
        (self.raiz / "brain" / "zenith_demo.py").write_bytes(DEMO.replace("\n", "\r\n").encode())
        r = self.aj.propor(proposta())
        self.assertTrue(r["ok"], r)
        novo = (self.aj._proposta_dir(r["id"]) / "novo.py").read_bytes()
        self.assertIn(b"return a + b\r\n", novo)
        self.assertEqual(novo.count(b"\n"), novo.count(b"\r\n"))

    def test_modulo_novo_so_com_conteudo(self):
        r = self.aj.propor(json.dumps({"arquivo": "brain/zenith_novo.py", "motivo": "Preciso de um módulo auxiliar novo.", "conteudo": "def f():\n    return 1\n"}))
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.aj.carregar(r["id"])["criar"])
        r2 = self.aj.propor(json.dumps({"arquivo": "brain/zenith_demo.py", "motivo": "Reescrever o arquivo todo.", "conteudo": "x = 1\n"}))
        self.assertFalse(r2["ok"])
        self.assertIn("edicoes", r2["mensagem"])
        r3 = self.aj.propor(proposta(arquivo="brain/zenith_inexistente.py"))
        self.assertFalse(r3["ok"])

    def test_limite_de_pendentes(self):
        for i in range(AJ.LIMITE_PENDENTES):
            self.assertTrue(self.aj.propor(proposta(motivo=f"Motivo número {i} do ajuste de teste.", edicoes=[{"antigo": 'return "demo"', "novo": f'return "d{i}"'}]))["ok"])
        r = self.aj.propor(proposta())
        self.assertFalse(r["ok"])
        self.assertIn("demais", r["mensagem"])

    def test_sem_codigo_fonte_no_executavel_fechado(self):
        (self.raiz / "brain" / "zenith_core.py").unlink()
        r = self.aj.propor(proposta())
        self.assertFalse(r["ok"])
        self.assertIn("executável fechado", r["mensagem"])
        self.assertEqual(self.aj.ler_trecho("brain/zenith_demo.py")[0], "")

    def test_extrair_propostas_da_resposta(self):
        txt = "Achei o bug.\n<propor_ajuste>{\"a\":1}</propor_ajuste> e mais <PROPOR_AJUSTE>\n{\"b\":2}\n</PROPOR_AJUSTE>"
        self.assertEqual(AJ.extrair_propostas(txt), ['{"a":1}', '{"b":2}'])
        self.assertEqual(AJ.extrair_propostas("nada"), [])


# ------------------------------------------------------------------ ler o próprio código
class LeituraTests(Base):
    def test_trecho_com_cabecalho_e_limites(self):
        texto, erro = self.aj.ler_trecho("brain/zenith_demo.py", 4, 5)
        self.assertEqual(erro, "")
        self.assertTrue(texto.startswith("brain/zenith_demo.py, linhas 4-5 de"))
        self.assertIn("return a - b", texto)
        (self.raiz / "brain" / "zenith_longo.py").write_text("\n".join(f"x{i} = {i}" for i in range(600)))
        t, _ = self.aj.ler_trecho("zenith_longo")
        self.assertEqual(len(t.splitlines()), AJ.LINHAS_TRECHO + 1)

    def test_so_modulos_do_cerebro(self):
        for ruim in ("config/settings.json", "../x.py", "brain/../config/chaves.txt", "tests/test_demo.py"):
            self.assertNotEqual(self.aj.ler_trecho(ruim)[1], "", ruim)

    def test_contexto_entra_no_prompt_e_expira(self):
        self.assertEqual(self.aj.bloco_contexto(), "")
        self.aj.ler_trecho("zenith_demo")
        bloco = self.aj.bloco_contexto()
        self.assertIn("SEU PRÓPRIO CÓDIGO", bloco)
        self.assertIn("def soma", bloco)
        self.aj._trechos = [(time.time() - AJ.VALIDADE_TRECHO_S - 5,) + t[1:] for t in self.aj._trechos]
        self.assertEqual(self.aj.bloco_contexto(), "")

    def test_so_guarda_os_ultimos_trechos(self):
        for _ in range(AJ.MAX_TRECHOS + 3):
            self.aj.ler_trecho("zenith_demo")
        self.assertEqual(len(self.aj._trechos), AJ.MAX_TRECHOS)


# ------------------------------------------------------------------ testar de verdade
class TestarTests(Base):
    def test_ajuste_bom_passa_e_corrige_um_teste(self):
        r = self.aj.propor(proposta())
        t = self.aj.testar(r["id"])
        self.assertTrue(t["ok"], t)
        res = t["resultado"]
        self.assertTrue(res["rodou"])
        self.assertEqual(res["novas"], [])
        self.assertEqual(len(res["corrigidas"]), 1)
        self.assertIn("test_soma", res["corrigidas"][0])
        self.assertEqual(self.aj.carregar(r["id"])["estado"], "testado_ok")
        self.assertIntocado()

    def test_ajuste_que_quebra_outro_teste_e_reprovado(self):
        r = self.aj.propor(proposta(edicoes=[{"antigo": 'return "demo"', "novo": 'return "outro"'}]))
        t = self.aj.testar(r["id"])
        self.assertFalse(t["ok"])
        self.assertEqual(len(t["resultado"]["novas"]), 1)
        self.assertIn("test_nome", t["resultado"]["novas"][0])
        self.assertEqual(self.aj.carregar(r["id"])["estado"], "testado_falhou")
        ap = self.aj.aplicar(r["id"])
        self.assertFalse(ap["ok"])
        self.assertIn("falha nova", ap["mensagem"])
        self.assertFalse((self.tmp / "config" / "ajustes" / "overlay" / "zenith_demo.py").exists())

    def test_falha_que_ja_existia_nao_conta_contra_o_ajuste(self):
        r = self.aj.propor(proposta(edicoes=[{"antigo": 'return "demo"', "novo": 'return "demo"  # igual'}]))
        t = self.aj.testar(r["id"])
        self.assertTrue(t["ok"], t)                                   # test_soma já falhava antes e continua
        self.assertEqual(t["resultado"]["novas"], [])
        self.assertEqual(t["resultado"]["falhavam_antes"], 1)

    def test_sem_teste_que_cite_o_modulo_confere_so_a_importacao(self):
        r = self.aj.propor(proposta(arquivo="brain/zenith_outro.py", edicoes=[{"antigo": "X = 1", "novo": "X = 2"}]))
        t = self.aj.testar(r["id"])
        self.assertTrue(t["ok"], t)
        self.assertIn("Nenhum teste", t["mensagem"])
        self.assertFalse(t["resultado"]["rodou"])

    def test_nao_toca_na_pasta_do_projeto(self):
        r = self.aj.propor(proposta())
        antes = sorted(str(p.relative_to(self.raiz)) for p in self.raiz.rglob("*") if "__pycache__" not in str(p))
        self.aj.testar(r["id"])
        depois = sorted(str(p.relative_to(self.raiz)) for p in self.raiz.rglob("*") if "__pycache__" not in str(p))
        self.assertEqual(antes, depois)
        self.assertIntocado()

    def test_saida_do_unittest_e_analisada(self):
        s = "ERROR: test_a (tests.t.C.test_a)\nFAIL: test_b (tests.t.C.test_b)\n\nRan 7 tests in 0.1s\n\nFAILED (failures=1, errors=1)\n"
        a = AJ.Ajustes.analisar_saida(s)
        self.assertEqual(a["ran"], 7)
        self.assertEqual(len(a["falhas"]), 2)
        self.assertFalse(AJ.Ajustes.analisar_saida("Traceback...")["terminou"])


# ------------------------------------------------------------------ aplicar / desfazer
class AplicarTests(Base):
    def aplicar_testado(self, bruto):
        r = self.aj.propor(bruto)
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.aj.testar(r["id"])["ok"])
        return r["id"], self.aj.aplicar(r["id"])

    def test_exige_teste_ou_sem_teste_explicito(self):
        r = self.aj.propor(proposta())
        ap = self.aj.aplicar(r["id"])
        self.assertFalse(ap["ok"])
        self.assertIn("sem-teste", ap["mensagem"])
        self.assertTrue(self.aj.aplicar(r["id"], sem_teste=True)["ok"])

    def test_aplicar_grava_so_na_pasta_de_ajustes(self):
        id_, ap = self.aplicar_testado(proposta())
        self.assertTrue(ap["ok"], ap)
        self.assertIn("PRÓXIMO início", ap["mensagem"])
        self.assertIntocado()                                              # o arquivo instalado nunca é trocado
        ov = self.tmp / "config" / "ajustes" / "overlay" / "zenith_demo.py"
        self.assertIn("return a + b", ov.read_text())
        m = OV.ler_manifesto(self.tmp / "config" / "ajustes")
        self.assertEqual(m["arquivos"]["zenith_demo.py"]["sha256"], hashlib.sha256(ov.read_bytes()).hexdigest())
        self.assertEqual(self.aj.carregar(id_)["estado"], "aplicado")
        self.assertFalse(self.aj.aplicar(id_)["ok"])                      # não aplica duas vezes

    def test_arquivo_mudou_depois_da_proposta(self):
        r = self.aj.propor(proposta())
        self.aj.testar(r["id"])
        (self.raiz / "brain" / "zenith_demo.py").write_text(DEMO + "\n# mudou\n", encoding="utf-8")
        ap = self.aj.aplicar(r["id"])
        self.assertFalse(ap["ok"])
        self.assertIn("mudou", ap["mensagem"])

    def test_proposta_adulterada_no_disco_e_recusada(self):
        r = self.aj.propor(proposta())
        self.aj.testar(r["id"])
        (self.aj._proposta_dir(r["id"]) / "novo.py").write_text("import os\nos.system('x')\n")
        ap = self.aj.aplicar(r["id"])
        self.assertFalse(ap["ok"])
        self.assertIn("alterado", ap["mensagem"])

    def test_recusar(self):
        r = self.aj.propor(proposta())
        self.assertTrue(self.aj.recusar(r["id"])["ok"])
        self.assertEqual(self.aj.carregar(r["id"])["estado"], "recusado")
        self.assertFalse(self.aj.aplicar(r["id"], sem_teste=True)["ok"])

    def test_desfazer_um_ajuste(self):
        id_, _ = self.aplicar_testado(proposta())
        d = self.aj.desfazer(id_)
        self.assertTrue(d["ok"], d)
        self.assertFalse((self.tmp / "config" / "ajustes" / "overlay" / "zenith_demo.py").exists())
        self.assertEqual(OV.ler_manifesto(self.tmp / "config" / "ajustes")["arquivos"], {})
        self.assertEqual(self.aj.carregar(id_)["estado"], "desfeito")
        self.assertFalse(self.aj.desfazer()["ok"])

    def test_pilha_de_ajustes_no_mesmo_arquivo(self):
        id1, _ = self.aplicar_testado(proposta())
        id2, ap2 = self.aplicar_testado(proposta(motivo="Outro conserto no mesmo arquivo, a descrição.", edicoes=[{"antigo": '"""modulo de exemplo"""', "novo": '"""modulo de exemplo ajustado"""'}]))
        self.assertTrue(ap2["ok"], ap2)
        self.assertIn("exemplo ajustado", (self.tmp / "config/ajustes/overlay/zenith_demo.py").read_text())
        d1 = self.aj.desfazer(id1)
        self.assertFalse(d1["ok"])
        self.assertIn(f"#{id2}", d1["mensagem"])
        self.assertTrue(self.aj.desfazer()["ok"])                           # sem número: desfaz o mais novo (#2)
        destino = self.tmp / "config/ajustes/overlay/zenith_demo.py"
        conteudo = destino.read_text()
        self.assertIn("return a + b", conteudo)
        self.assertNotIn("exemplo ajustado", conteudo)
        m = OV.ler_manifesto(self.tmp / "config" / "ajustes")
        # o manifesto aponta o hash dos BYTES do arquivo (no Windows o texto sai com CRLF)
        self.assertEqual(m["arquivos"]["zenith_demo.py"]["sha256"], hashlib.sha256(destino.read_bytes()).hexdigest())
        self.assertTrue(self.aj.desfazer(id1)["ok"])
        self.assertFalse((self.tmp / "config/ajustes/overlay/zenith_demo.py").exists())

    def test_resumo_lista(self):
        self.assertIn("Nenhum ajuste", self.aj.resumo())
        self.aj.propor(proposta())
        r = self.aj.resumo()
        self.assertIn("#1 [pendente]", r)
        self.assertIn("aplicar N", r)


# ------------------------------------------------------------------ o carregador (overlay)
class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zo_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pasta = self.tmp / "ajustes"
        self.pkg = self.tmp / "src" / "pkgovl"
        self.pkg.mkdir(parents=True)
        (self.pkg / "zenith_a.py").write_text("VALOR = 'original'\n")
        (self.pkg / "zenith_core.py").write_text("VALOR = 'original'\n")
        sys.path.insert(0, str(self.tmp / "src"))
        self.addCleanup(lambda: sys.path.remove(str(self.tmp / "src")))
        self.addCleanup(OV.desinstalar)
        self.addCleanup(self._limpar_modulos)

    def _limpar_modulos(self):
        for n in [n for n in sys.modules if n == "pkgovl" or n.startswith("pkgovl.")]:
            del sys.modules[n]
        importlib.invalidate_caches()

    def aprovar(self, nome, conteudo, sha=None):
        d = OV.pasta_overlay(self.pasta)
        d.mkdir(parents=True, exist_ok=True)
        (d / nome).write_text(conteudo)
        m = OV.ler_manifesto(self.pasta)
        m["arquivos"][nome] = {"sha256": sha or OV.sha256_arquivo(d / nome), "id": 1}
        OV.gravar_manifesto(self.pasta, m)

    def test_carrega_a_copia_aprovada_no_lugar_do_original(self):
        self.aprovar("zenith_a.py", "VALOR = 'ajustado'\n")
        r = OV.instalar(self.pasta, "pkgovl")
        self.assertEqual(r["ativos"], ["zenith_a.py"])
        self.assertEqual(importlib.import_module("pkgovl.zenith_a").VALOR, "ajustado")

    def test_sem_ajuste_usa_o_original(self):
        OV.instalar(self.pasta, "pkgovl")
        self.assertEqual(importlib.import_module("pkgovl.zenith_a").VALOR, "original")

    def test_copia_alterada_depois_da_aprovacao_e_ignorada(self):
        self.aprovar("zenith_a.py", "VALOR = 'ajustado'\n")
        (OV.pasta_overlay(self.pasta) / "zenith_a.py").write_text("VALOR = 'adulterado'\n")
        r = OV.instalar(self.pasta, "pkgovl")
        self.assertEqual(r["ativos"], [])
        self.assertIn("hash", r["ignorados"][0][1])
        self.assertEqual(importlib.import_module("pkgovl.zenith_a").VALOR, "original")

    def test_modulo_protegido_nunca_e_substituido_mesmo_no_manifesto(self):
        self.aprovar("zenith_core.py", "VALOR = 'invasor'\n")
        r = OV.instalar(self.pasta, "pkgovl")
        self.assertEqual(r["ativos"], [])
        self.assertEqual(r["ignorados"][0], ("zenith_core.py", "módulo protegido"))
        self.assertEqual(importlib.import_module("pkgovl.zenith_core").VALOR, "original")

    def test_nome_estranho_e_arquivo_sumido(self):
        m = OV.ler_manifesto(self.pasta)
        m["arquivos"] = {"../x.py": {"sha256": "0" * 64}, "zenith_b.py": {"sha256": "0" * 64}, "outro.py": {"sha256": "0" * 64}}
        OV.gravar_manifesto(self.pasta, m)
        r = OV.instalar(self.pasta, "pkgovl")
        self.assertEqual(r["ativos"], [])
        self.assertEqual(len(r["ignorados"]), 3)

    def test_avisa_modulo_que_ja_estava_importado(self):
        importlib.import_module("pkgovl.zenith_a")
        self.aprovar("zenith_a.py", "VALOR = 'ajustado'\n")
        self.assertEqual(OV.instalar(self.pasta, "pkgovl")["ja_importados"], ["pkgovl.zenith_a"])

    def test_instalar_duas_vezes_nao_empilha_buscadores(self):
        self.aprovar("zenith_a.py", "VALOR = 'x'\n")
        OV.instalar(self.pasta, "pkgovl")
        OV.instalar(self.pasta, "pkgovl")
        self.assertEqual(len([f for f in sys.meta_path if isinstance(f, OV.BuscadorOverlay)]), 1)
        OV.desinstalar()
        self.assertEqual(len([f for f in sys.meta_path if isinstance(f, OV.BuscadorOverlay)]), 0)

    def test_modo_seguro_depois_de_dois_inicios_que_nao_abriram(self):
        self.aprovar("zenith_a.py", "VALOR = 'ajustado'\n")
        self.assertFalse(OV.iniciar_boot(self.pasta)["modo_seguro"])        # 1ª tentativa
        self.assertFalse(OV.iniciar_boot(self.pasta)["modo_seguro"])        # 2ª (a 1ª nunca confirmou)
        r = OV.iniciar_boot(self.pasta)                                     # 3ª: as duas anteriores falharam
        self.assertTrue(r["modo_seguro"])
        self.assertIn("2 inícios", r["motivo"])
        self.assertEqual(OV.ler_manifesto(self.pasta)["arquivos"], {})
        quarentenas = list((self.pasta / "quarentena").iterdir())
        self.assertEqual(len(quarentenas), 1)
        self.assertTrue((quarentenas[0] / "overlay" / "zenith_a.py").exists())
        self.assertTrue((quarentenas[0] / "motivo.txt").exists())
        self.assertEqual(OV.instalar(self.pasta, "pkgovl")["ativos"], [])

    def test_boot_ok_zera_a_contagem(self):
        self.aprovar("zenith_a.py", "VALOR = 'ajustado'\n")
        for _ in range(5):
            self.assertFalse(OV.iniciar_boot(self.pasta)["modo_seguro"])
            OV.boot_ok(self.pasta)
        self.assertEqual(len(OV.ler_manifesto(self.pasta)["arquivos"]), 1)

    def test_sem_ajustes_nunca_entra_em_modo_seguro(self):
        for _ in range(6):
            self.assertFalse(OV.iniciar_boot(self.pasta)["modo_seguro"])


# ------------------------------------------------------------------ ponta a ponta: proposta -> teste -> aplicar -> próximo início
class PontaAPontaTests(Base):
    def test_o_ajuste_aprovado_vira_o_codigo_que_roda_no_proximo_inicio(self):
        r = self.aj.propor(proposta())
        self.assertTrue(self.aj.testar(r["id"])["ok"])
        self.assertTrue(self.aj.aplicar(r["id"])["ok"])
        pasta = self.tmp / "config" / "ajustes"
        for n in [n for n in sys.modules if n == "brain.zenith_demo"]:
            del sys.modules[n]
        self.addCleanup(OV.desinstalar)
        self.addCleanup(lambda: sys.modules.pop("brain.zenith_demo", None))
        try:
            info = OV.instalar(pasta)
            self.assertEqual(info["ativos"], ["zenith_demo.py"])
            demo = importlib.import_module("brain.zenith_demo")
            self.assertEqual(demo.soma(2, 3), 5)                              # o bug de verdade foi consertado
        finally:
            OV.desinstalar()
        self.assertEqual((self.raiz / "brain" / "zenith_demo.py").read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
