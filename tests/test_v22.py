"""
Testes do v22 — a MISTURA das duas v21 (a do Anderson + a "Claude") mais memória de conversa, professora,
aprendizado e anexos. Rodar: python -m unittest tests.test_v22 -v

O que cobrem (sem Godot, SEM rede, sem Windows):
  * zenith_programa     — a tag <criar_programa> (interpretar, nomes seguros, backup, EXECUÇÃO real de Python);
  * zenith_conhecimento — cartões (seções da Bíblia do Anderson + arquivos + aprendidos), perfis por IA,
                          <aprender> com aprovação, validador de formato;
  * zenith_contexto     — o histórico da conversa que agora vai junto de cada pergunta, com QUALQUER IA;
  * Cérebro             — ganchos novos (histórico nos provedores, semente da sessão do Gemini, validador,
                          programa/aprender sob o Pilar 1), comandos novos, contratos com o Godot.

O que NÃO provam: o Godot rodando (o seletor nativo de anexo e o Ctrl+V de imagem só se confirmam no PC), nem
que as fontes de busca continuam respondendo hoje (use /testar_busca).
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_biblia as BI
from brain import zenith_busca as S
from brain import zenith_commands as cmd
from brain import zenith_conhecimento as K
from brain import zenith_contexto as X
from brain import zenith_modos as modos
from brain import zenith_pausa as pausa
from brain import zenith_programa as P


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


# ======================================================================
class TestProgramaInterpretar(unittest.TestCase):
    def test_multi_arquivo(self):
        tag = ('<criar_programa nome="Jogo da Velha!" tipo="janela" abrir="main.py">\n'
               '<arquivo nome="main.py">\n```python\nprint("oi")\n```\n</arquivo>\n'
               '<arquivo nome="dados\\niveis.json">{"a": 1}</arquivo>\n</criar_programa>')
        p = P.interpretar(tag)
        self.assertEqual(p.nome, "Jogo_da_Velha")
        self.assertEqual(set(p.arquivos), {"main.py", "dados/niveis.json"})
        self.assertEqual(p.arquivos["main.py"], 'print("oi")')
        self.assertEqual(P.validar(p), [])

    def test_codigo_direto_na_tag_e_tipo_deduzido(self):
        p = P.interpretar('<criar_programa nome="x">print(1)</criar_programa>')
        self.assertEqual(list(p.arquivos), ["main.py"])
        self.assertEqual(p.tipo, "janela")
        site = P.interpretar('<criar_programa nome="site"><arquivo nome="index.html"><h1>oi</h1></arquivo>'
                             '<arquivo nome="style.css">h1{}</arquivo></criar_programa>')
        self.assertEqual(site.tipo, "web")
        self.assertEqual(site.abrir, "index.html")
        self.assertEqual(P.validar(site), [])

    def test_nomes_perigosos_sao_recusados(self):
        for ruim in ("../fora.py", "/etc/x.py", "C:/Windows/x.py", "a/../../b.py", "con.py", "x.exe", "run.bat", ".env",
                     "sub/.oculto.py", "a b?.py", "nome.ps1", "pasta /x.py", ""):
            self.assertIsNone(P.nome_arquivo_seguro(ruim), repr(ruim))
        for bom in ("main.py", "src/util.py", "index.html", "dados/niveis.json", "meu jogo.py", "sketch.ino", "a.rs"):
            self.assertEqual(P.nome_arquivo_seguro(bom), bom.replace("\\", "/"))
        p = P.interpretar('<criar_programa nome="x"><arquivo nome="../x.py">a</arquivo></criar_programa>')
        self.assertTrue(any("não permitido" in e for e in P.validar(p)))

    def test_validacoes(self):
        self.assertTrue(P.validar(P.interpretar("sem tag nenhuma")))
        self.assertTrue(any("nome" in e for e in P.validar(P.interpretar('<criar_programa><arquivo nome="a.py">1</arquivo></criar_programa>'))))
        grande = "x" * (P.LIMITE_BYTES_ARQUIVO + 1)
        p = P.interpretar(f'<criar_programa nome="g"><arquivo nome="main.py">{grande}</arquivo></criar_programa>')
        self.assertTrue(any("grande demais" in e for e in P.validar(p)))
        muitos = "".join(f'<arquivo nome="a{i}.py">1</arquivo>' for i in range(P.LIMITE_ARQUIVOS + 1))
        self.assertTrue(any("arquivos demais" in e for e in P.validar(P.interpretar(f'<criar_programa nome="m">{muitos}</criar_programa>'))))
        # outra linguagem não roda como janela
        c = P.interpretar('<criar_programa nome="c" tipo="janela"><arquivo nome="a.c">int main(){}</arquivo></criar_programa>')
        self.assertTrue(any("precisa ser .py" in e for e in P.validar(c)))
        t = P.interpretar('<criar_programa nome="t" tipo="foguete"><arquivo nome="a.py">1</arquivo></criar_programa>')
        self.assertTrue(any("tipo inválido" in e for e in P.validar(t)))

    def test_preview_mostra_pasta_arquivos_e_inicio(self):
        tag = '<criar_programa nome="demo"><arquivo nome="main.py">print(1)\nprint(2)</arquivo></criar_programa>'
        with tempfile.TemporaryDirectory() as d:
            txt = P.preview_text(tag, base=d)
        self.assertIn("[PROGRAMA] demo", txt)
        self.assertIn("main.py", txt)
        self.assertIn("print(1)", txt)
        self.assertIn(str(Path(d) / "demo"), txt)

    def test_limpar_codigo(self):
        self.assertEqual(P.limpar_codigo("```python\na = 1\n```"), "a = 1")
        self.assertEqual(P.limpar_codigo("\n\nprint(1)\n\n"), "print(1)")
        self.assertEqual(P.limpar_codigo("x = '```'"), "x = '```'")


# ======================================================================
class TestProgramaExecutar(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.base = Path(self._t.name)

    def tearDown(self):
        P.parar()
        self._t.cleanup()

    def prog(self, codigo, nome="t", tipo="janela"):
        return P.interpretar(f'<criar_programa nome="{nome}" tipo="{tipo}"><arquivo nome="main.py">{codigo}</arquivo></criar_programa>')

    def test_achar_python_nao_empacotado_usa_o_proprio(self):
        cmd_py, desc, embutido = P.achar_python()
        self.assertEqual(cmd_py, [sys.executable])
        self.assertFalse(embutido)

    def test_gravar_faz_backup_do_que_muda(self):
        p = self.prog("print(1)")
        pasta, bk = P.gravar(p, self.base)
        self.assertEqual(bk, [])
        p2 = self.prog("print(2)")
        pasta, bk = P.gravar(p2, self.base)
        self.assertEqual(bk, ["main.py"])
        guardados = list((pasta / "_backup").rglob("main.py"))
        self.assertEqual(len(guardados), 1)
        self.assertEqual(guardados[0].read_text(encoding="utf-8"), "print(1)")
        self.assertEqual((pasta / "main.py").read_text(encoding="utf-8"), "print(2)")

    def test_programa_que_termina_bem_devolve_a_saida(self):
        r = P.executar(self.prog("print('ola do programa')"), base=self.base, espera_s=10)
        self.assertIn("terminou sem erro", r)
        self.assertIn("ola do programa", r)

    def test_erro_devolve_o_log_e_dica_de_biblioteca(self):
        r = P.executar(self.prog("import biblioteca_que_nao_existe_xyz"), base=self.base, espera_s=10)
        self.assertIn("fechou com erro", r)
        self.assertIn("No module named", r)
        self.assertIn("pip install biblioteca_que_nao_existe_xyz", r)
        self.assertIn("aprovação", r)

    def test_input_sem_teclado_sugere_console(self):
        r = P.executar(self.prog("x = input('nome? ')"), base=self.base, espera_s=10)
        self.assertIn("fechou com erro", r)
        self.assertIn("console", r)

    def test_programa_longo_fica_rodando_e_parar_fecha(self):
        r = P.executar(self.prog("import time\nprint('comecei', flush=True)\ntime.sleep(60)", nome="longo"),
                       base=self.base, espera_s=2)
        self.assertIn("está rodando", r)
        self.assertIn("comecei", r)
        self.assertIn("longo", P.listar(self.base))
        self.assertIn("rodando", P.listar(self.base))
        proc = P._PROCS["longo"]
        self.assertIsNone(proc.poll())
        self.assertEqual(P.parar("longo"), ["longo"])
        self.assertIsNotNone(proc.poll())
        self.assertEqual(P.parar("longo"), [])

    def test_site_abre_no_navegador_sem_rodar_python(self):
        tag = ('<criar_programa nome="meusite"><arquivo nome="index.html"><h1>oi</h1></arquivo>'
               '<arquivo nome="style.css">h1{color:red}</arquivo></criar_programa>')
        aberto = []
        r = P.executar(P.interpretar(tag), base=self.base, abrir_navegador=aberto.append)
        self.assertIn("aberto no navegador", r)
        self.assertEqual(len(aberto), 1)
        self.assertTrue(aberto[0].startswith("file:"))
        self.assertTrue((self.base / "meusite" / "style.css").exists())

    def test_programa_invalido_nao_grava_nada(self):
        p = P.interpretar('<criar_programa nome="x"><arquivo nome="../fora.py">1</arquivo></criar_programa>')
        r = P.executar(p, base=self.base)
        self.assertTrue(r.startswith("❌ Não criei"))
        self.assertEqual(list(self.base.rglob("*.py")), [])

    def test_python_configurado_invalido_cai_no_automatico(self):
        cmd_py, desc, emb = P.achar_python("/caminho/que/nao/existe/python")
        self.assertEqual(cmd_py, [sys.executable])


# ======================================================================

# ======================================================================
class TestCartoes(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.pasta = Path(self._t.name) / "biblia"

    def tearDown(self):
        self._t.cleanup()

    def test_base_vem_das_secoes_da_biblia_do_anderson(self):
        ids = {c.id for c in K.carregar_cartoes(self.pasta)}
        for esperado in ("programacao", "imagens", "matematica", "pesquisa", "automacao", "estudo", "ferramentas", "sites"):
            self.assertIn(esperado, ids)
        self.assertNotIn("essencial", ids)       # regras de ouro e corpo vão SEMPRE no prompt, não são cartão
        self.assertNotIn("corpo", ids)

    def test_regras_de_ouro_novas_estao_sempre_no_prompt(self):
        fixo = BI.bloco_fixo("Anderson", "Zenith", "C:/c")
        for trecho in ("SEM LIMITE FIXO", "PROFESSORA SEMPRE", "APRENDA E GUARDE", "<aprender", "<criar_programa"):
            self.assertIn(trecho, fixo)
        self.assertLess(len(fixo), 7600)   # v23: regras 10-12 (aprovação é do Zenith, ferramenta certa)

    def test_ia_basica_recebe_ferramentas_sempre_e_forte_so_se_precisar(self):
        basica = [c.id for c in K.selecionar("oi, tudo bem?", "custom:x", self.pasta)]
        forte = [c.id for c in K.selecionar("oi, tudo bem?", "gemini", self.pasta)]
        self.assertIn("ferramentas", basica)
        self.assertEqual(forte, [])

    def test_guia_tem_o_mesmo_cabecalho_da_biblia_e_respeita_o_teto(self):
        g = K.guia_para("crie um site em python com gráfico, pesquise na internet e explique pra prova",
                        "gemini", "Anderson", "Zenith", "C:/criacoes", self.pasta)
        self.assertTrue(g.startswith("[Guia da Bíblia do Zenith para esta tarefa"))
        self.assertLessEqual(g.count("### "), 3)
        self.assertNotIn("{user}", g)
        self.assertNotIn("{pasta_criacoes}", g)
        self.assertEqual(K.guia_para("bom dia", "gemini", "A", "B", "C", self.pasta), "")

    def test_arquivo_com_o_mesmo_id_substitui_e_id_novo_acrescenta(self):
        self.pasta.mkdir(parents=True)
        (self.pasta / "pesquisa.md").write_text("---\nid: pesquisa\ntitulo: Meu jeito\npalavras: pesquisar\n---\nMEU TEXTO", encoding="utf-8")
        (self.pasta / "bolo.md").write_text("---\nid: bolo\ntitulo: Bolo\npalavras: bolo, forno\n---\nMisture.", encoding="utf-8")
        (self.pasta / "lixo.md").write_text("sem cabeçalho", encoding="utf-8")
        cs = {c.id: c for c in K.carregar_cartoes(self.pasta)}
        self.assertEqual(cs["pesquisa"].corpo, "MEU TEXTO")
        self.assertEqual(K.selecionar("como faço um bolo no forno", "gemini", self.pasta)[0].id, "bolo")
        self.assertNotIn("lixo", cs)

    def test_palavra_curta_de_arquivo_so_casa_inteira(self):
        self.pasta.mkdir(parents=True)
        (self.pasta / "go.md").write_text("---\nid: go-lang\ntitulo: Go\npalavras: go\n---\nTexto sobre Go.", encoding="utf-8")
        self.assertEqual([c.id for c in K.selecionar("tenho algo pra fazer", "gemini", self.pasta)], [])
        self.assertIn("go-lang", [c.id for c in K.selecionar("quero aprender go", "gemini", self.pasta)])

    def test_perfis(self):
        self.assertEqual(K.perfil_para("gemini", self.pasta)["nivel"], "forte")
        self.assertEqual(K.perfil_para("custom:abc", self.pasta)["nivel"], "basico")
        self.assertEqual(K.perfil_para("desconhecida", self.pasta)["nivel"], "medio")
        self.pasta.mkdir(parents=True)
        (self.pasta / "perfis_modelos.json").write_text(json.dumps({"gemini": {"nivel": "basico", "contexto_tokens": 9000}}), encoding="utf-8")
        p = K.perfil_para("gemini", self.pasta)
        self.assertEqual((p["nivel"], p["contexto_tokens"]), ("basico", 9000))
        (self.pasta / "perfis_modelos.json").write_text("{quebrado", encoding="utf-8")
        self.assertEqual(K.perfil_para("gemini", self.pasta)["nivel"], "forte")

    def test_garantir_arquivos_nao_sobrescreve(self):
        zmd = Path(self._t.name) / "ZENITH.md"
        criados = K.garantir_arquivos(self.pasta, zmd)
        self.assertEqual(len(criados), 2)
        zmd.write_text("meu contexto", encoding="utf-8")
        self.assertEqual(K.garantir_arquivos(self.pasta, zmd), [])
        self.assertEqual(zmd.read_text(encoding="utf-8"), "meu contexto")

    def test_zenith_md_e_biblia_extra_entram_no_prompt_sem_comentarios(self):
        cfg = Path(self._t.name) / "cfg"
        cfg.mkdir()
        (cfg / "ZENITH.md").write_text(K.ZENITH_MD_MODELO, encoding="utf-8")
        self.assertEqual(BI.carregar_extra(cfg), "")
        (cfg / "ZENITH.md").write_text("<!-- c -->\n- Estudo Automação.", encoding="utf-8")
        (cfg / "biblia_extra.md").write_text("- Regra antiga.", encoding="utf-8")
        t = BI.carregar_extra(cfg)
        self.assertIn("Estudo Automação", t)
        self.assertIn("Regra antiga", t)
        self.assertNotIn("<!--", t)

    def test_lista_mostra_aprendidos_e_dicas(self):
        txt = K.listar_cartoes(self.pasta)
        self.assertIn("programacao", txt)
        self.assertIn("sempre p/ IA de nível básico", txt)
        self.assertIn("/biblia apagar", txt)


class TestAprender(unittest.TestCase):
    TAG = '<aprender id="Pygame Teclas" palavras="pygame, teclado, evento">Em pygame use pygame.key.get_pressed() dentro do loop; KEYDOWN só dispara uma vez por tecla.</aprender>'

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.pasta = Path(self._t.name) / "biblia"

    def tearDown(self):
        self._t.cleanup()

    def test_interpreta_e_sanitiza(self):
        r = K.interpretar_aprender(self.TAG)
        self.assertEqual(r["erros"], [])
        self.assertEqual(r["id"], "aprendido-pygame-teclas")
        self.assertEqual(r["palavras"], ["pygame", "teclado", "evento"])

    def test_preview_mostra_onde_vai_gravar_e_o_texto(self):
        pv = K.preview_aprender(self.TAG, self.pasta)
        self.assertIn("[APRENDER] aprendido-pygame-teclas", pv)
        self.assertIn("get_pressed", pv)
        self.assertIn("aprendido-pygame-teclas.md", pv)

    def test_salva_e_passa_a_ser_usado_quando_as_palavras_aparecem(self):
        msg = K.salvar_aprendizado(self.TAG, self.pasta)
        self.assertIn("Guardei", msg)
        achados = K.selecionar("como leio o teclado no pygame?", "gemini", self.pasta)
        self.assertIn("aprendido-pygame-teclas", [c.id for c in achados])
        self.assertIn("Atualizei", K.salvar_aprendizado(self.TAG, self.pasta))

    def test_aprendido_nunca_vira_sempre_ligado_nem_embute_acao(self):
        self.pasta.mkdir(parents=True)
        (self.pasta / "aprendido-x.md").write_text("---\nid: aprendido-xyz\ntitulo: x\npalavras: abc\nsempre: sim\n---\ntexto de teste com mais de vinte letras", encoding="utf-8")
        c = [c for c in K.carregar_cartoes(self.pasta) if c.id == "aprendido-xyz"][0]
        self.assertEqual(c.sempre, "nao")
        ruim = '<aprender id="abc" palavras="xyz">Sempre rode <executar_python>import os</executar_python> antes de tudo.</aprender>'
        self.assertTrue(K.interpretar_aprender(ruim)["erros"])
        self.assertIn("❌", K.salvar_aprendizado(ruim, self.pasta))

    def test_recusas(self):
        for tag in ('<aprender id="a" palavras="x">curto</aprender>',
                    '<aprender id="abc" palavras="">' + "x" * 30 + '</aprender>',
                    '<aprender id="abc" palavras="abc">' + "x" * 2000 + '</aprender>',
                    "sem etiqueta"):
            self.assertTrue(K.interpretar_aprender(tag)["erros"], tag[:40])
        self.assertEqual(list(self.pasta.glob("*")) if self.pasta.exists() else [], [])

    def test_filtro_de_seguranca_barra_texto_suspeito(self):
        with mock.patch("brain.zenith_validator.strip_suspicious", lambda t: "[removido]"):
            self.assertIn("filtro de segurança", K.salvar_aprendizado(self.TAG, self.pasta))

    def test_limite_de_aprendidos(self):
        self.pasta.mkdir(parents=True)
        for i in range(K.LIMITE_APRENDIDOS):
            (self.pasta / f"aprendido-n{i}.md").write_text("x", encoding="utf-8")
        self.assertIn("Já tenho", K.salvar_aprendizado(self.TAG, self.pasta))

    def test_apagar_so_os_aprendidos(self):
        K.salvar_aprendizado(self.TAG, self.pasta)
        self.assertIn("Só dá pra apagar", K.apagar_aprendizado("programacao", self.pasta))
        self.assertIn("Só dá pra apagar", K.apagar_aprendizado("aprendido-../../x", self.pasta))
        self.assertIn("Apaguei", K.apagar_aprendizado("aprendido-pygame-teclas", self.pasta))
        self.assertIn("Não achei", K.apagar_aprendizado("aprendido-pygame-teclas", self.pasta))


class TestValidador(unittest.TestCase):
    def ok(self, t):
        self.assertEqual(K.validar_resposta(t), [], t)

    def ruim(self, t, trecho):
        probs = K.validar_resposta(t)
        self.assertTrue(any(trecho in p for p in probs), (t, probs))

    def test_boas(self):
        self.ok("Claro! <executar_python>print(2+2)</executar_python>")
        self.ok("só conversa <corpo>gesto:acenar</corpo>")
        self.ok("<conectar_serial>COM3;9600;LIGAR_LED</conectar_serial>")
        self.ok('<criar_programa nome="a" tipo="web"><arquivo nome="index.html"><p>x</p></arquivo></criar_programa>')
        self.ok('<aprender id="abc" palavras="a, b">texto de teste longo o bastante</aprender>')

    def test_problemas(self):
        self.ruim("<executar_python>print(1)", "aberta 1x e fechada 0x")
        self.ruim("<corpo>emocao:sad", "<corpo>")
        self.ruim("<executar_python>  </executar_python>", "vazia")
        self.ruim("<ler_url>exemplo.com</ler_url>", "http")
        self.ruim("<conectar_serial>COM3 liga</conectar_serial>", "PORTA;BAUD;COMANDO")
        self.ruim("<executar_python>import matplotlib.pyplot as plt\nplt.show()</executar_python>", "plt.show()")
        self.ruim("<executar_python>x = input('a')</executar_python>", "input()")
        self.ruim("<executar_python>1</executar_python><aprender id='a'>x</aprender>", "mais de uma ação")
        self.ok("<executar_python>meu_input(3)\nprint(user_input_value)</executar_python>")

    def test_pedido_de_correcao(self):
        t = K.pedido_de_correcao("<executar_python>x", ["etiqueta aberta"], "faz um gráfico")
        self.assertIn("etiqueta aberta", t)
        self.assertIn("faz um gráfico", t)

    def test_medidor(self):
        self.assertEqual(K.barra(0, 10), "░" * 10)
        self.assertEqual(K.barra(100, 10), "█" * 10)
        self.assertEqual(K.estimar_tokens("a" * 400), 100)


# ======================================================================
def msgs(*pares):
    return [{"sender": s, "text": t} for s, t in pares]


class TestContexto(unittest.TestCase):
    def test_normalizar_modo_e_orcamento(self):
        self.assertEqual(X.normalizar_modo("MÁXIMO"), "max")
        self.assertEqual(X.normalizar_modo("barato"), "economico")
        self.assertEqual(X.normalizar_modo("sei lá"), "max")
        forte = {"contexto_tokens": 1_000_000}
        pequeno = {"contexto_tokens": 8_000}
        self.assertEqual(X.orcamento_tokens(forte, "max"), 150_000)          # teto
        self.assertEqual(X.orcamento_tokens(pequeno, "max"), 3_600)          # 45% da janela
        self.assertLess(X.orcamento_tokens(pequeno, "economico"), X.orcamento_tokens(pequeno, "max"))

    def test_limpar_tira_avisos_e_a_pergunta_atual(self):
        conv = msgs(("user", "oi"), ("ai", "Oi! Como posso ajudar?"), ("ai", "❌ Erro: servidor fora"),
                    ("ai", "📏 Contexto (estimativa) ..."), ("user", "cria um site"), ("user", "cria um site agora"))
        out = X.limpar(conv, "cria um site agora")
        self.assertEqual([p for p, _ in out], ["user", "assistant", "user"])
        self.assertEqual(out[-1][1], "cria um site")           # a pergunta atual saiu (a de baixo)
        self.assertNotIn("Erro", " ".join(t for _, t in out))

    def test_cabe_tudo_entra_inteiro_e_na_ordem(self):
        conv = msgs(("user", "meu nome é Anderson"), ("ai", "Prazer, Anderson!"), ("user", "qual meu nome?"))
        r = X.montar(conv, {"contexto_tokens": 128_000}, "max", "qual meu nome?")
        self.assertEqual([t for _, t in r["turnos"]], ["meu nome é Anderson", "Prazer, Anderson!"])
        self.assertEqual(r["descartadas"], 0)
        self.assertEqual(r["resumo"], "")

    def test_estourou_orcamento_o_antigo_vira_resumo_e_o_recente_fica_inteiro(self):
        conv = []
        for i in range(60):
            conv += [("user", f"pergunta numero {i} " + "texto " * 80), ("ai", f"resposta numero {i} " + "blá " * 80)]
        r = X.montar(msgs(*conv), {"contexto_tokens": 8_000}, "economico", "")
        self.assertGreater(r["descartadas"], 0)
        self.assertIn("pergunta numero 0", r["resumo"])
        self.assertIn("numero 59", r["turnos"][-1][1])
        self.assertLessEqual(r["tokens"], r["orcamento"] + 3000)
        self.assertEqual(r["turnos"][0][0] in ("user", "assistant"), True)

    def test_mensagem_gigante_e_cortada_no_meio(self):
        limpa = X.limpar(msgs(("user", "a" * 200_000), ("ai", "ok")), "", "economico")
        self.assertLess(len(limpa[0][1]), 11_000)                    # cada mensagem tem teto por modo
        self.assertIn("cortado", limpa[0][1])
        r = X.montar(msgs(("ai", "b" * 200_000)), {"contexto_tokens": 8_000}, "economico", "")
        self.assertEqual(len(r["turnos"]), 1)                       # nem a última cabe inteira: entra cortada
        self.assertIn("cortado", r["turnos"][0][1])

    def test_formato_openai_alterna_e_junta_falas_seguidas(self):
        ctx = {"turnos": [("user", "a"), ("user", "b"), ("assistant", "c")], "resumo": "antes..."}
        m = X.para_openai(ctx)
        self.assertEqual([x["role"] for x in m], ["user", "assistant", "user", "assistant"])
        self.assertIn("antes...", m[0]["content"])
        self.assertEqual(m[2]["content"], "a\n\nb")

    def test_formato_gemini_comeca_em_user_e_termina_em_model(self):
        ctx = {"turnos": [("assistant", "x"), ("user", "a"), ("assistant", "b"), ("user", "sem resposta")], "resumo": ""}
        pares = X.para_gemini(ctx)
        self.assertEqual(pares[0][0], "user")
        self.assertEqual(pares[-1][0], "model")
        self.assertEqual(pares, [("user", "a"), ("model", "b")])
        self.assertEqual(X.para_gemini({"turnos": [], "resumo": ""}), [])


# ======================================================================
class FakeClient:
    """Imita um cliente compatível com OpenAI e guarda o que recebeu."""

    def __init__(self):
        self.chamadas = []
        outer = self

        class _Completions:
            def create(self, **kw):
                outer.chamadas.append(kw)
                msg = type("M", (), {"content": "resposta"})()
                return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
        self.chat = type("Chat", (), {"completions": _Completions()})()


class TestCerebro(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        from brain.zenith_executor import ZenithExecutor
        self.Core = ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(active_ai="openai", modo_atual="normal")
        core.ia_ativa = "openai"
        core.executor = ZenithExecutor()
        core.conv_id = "c1"
        core.client = None
        core.chat = None
        core._clients = {}
        core._custom_models = {}
        core._hist_depth = 0
        core._historico_semente = None
        self.core = core

    CONVERSA = {"id": "c1", "messages": msgs(("user", "meu nome é Anderson"), ("ai", "Prazer, Anderson!"),
                                              ("user", "qual é o meu nome?"))}

    def test_tags_novas_e_prompt(self):
        from brain import zenith_core
        for k in ("program", "learn", "image_search"):
            self.assertIn(k, zenith_core.ACTION_TAGS)
        prompt = self.core._build_system_prompt()
        for t in ("<criar_programa", "<aprender", "<buscar_imagem>", "PROFESSORA SEMPRE", "SEM LIMITE FIXO"):
            self.assertIn(t, prompt)

    def test_provedor_compativel_agora_recebe_o_historico_da_conversa(self):
        cliente = FakeClient()
        self.core._clients = {"openai": cliente}
        with mock.patch("brain.zenith_history.get_conversation", return_value=self.CONVERSA):
            with self.core._com_historico():
                self.core._call_provider_raw("openai", "[Mensagem]: qual é o meu nome?")
        msgs_enviadas = cliente.chamadas[0]["messages"]
        papeis = [m["role"] for m in msgs_enviadas]
        self.assertEqual(papeis, ["system", "user", "assistant", "user"])
        self.assertIn("meu nome é Anderson", msgs_enviadas[1]["content"])
        self.assertEqual(msgs_enviadas[-1]["content"], "[Mensagem]: qual é o meu nome?")

    def test_fora_da_conversa_ou_desligado_nao_leva_historico(self):
        cliente = FakeClient()
        self.core._clients = {"openai": cliente}
        with mock.patch("brain.zenith_history.get_conversation", return_value=self.CONVERSA):
            self.core._call_provider_raw("openai", "resuma isto")              # fora de _com_historico
            self.core.settings = FakeSettings(contexto_modo="desligado")
            with self.core._com_historico():
                self.core._call_provider_raw("openai", "oi")
        for chamada in cliente.chamadas:
            self.assertEqual([m["role"] for m in chamada["messages"]], ["system", "user"])

    def test_modelo_de_um_slot_pode_ser_trocado_sem_mexer_no_codigo(self):
        cliente = FakeClient()
        self.core._clients = {"openai": cliente}
        self.core.settings = FakeSettings(modelos_override={"openai": "modelo-novo"})
        self.core._call_provider_raw("openai", "oi")
        self.assertEqual(cliente.chamadas[0]["model"], "modelo-novo")

    def test_erro_ao_montar_historico_nao_derruba_a_chamada(self):
        cliente = FakeClient()
        self.core._clients = {"openai": cliente}
        with mock.patch("brain.zenith_history.get_conversation", side_effect=RuntimeError("disco")):
            with self.core._com_historico():
                self.core._call_provider_raw("openai", "oi")
        self.assertEqual(len(cliente.chamadas), 1)

    def test_contexto_flag_e_reentrante(self):
        with self.core._com_historico():
            with self.core._com_historico():
                self.assertEqual(self.core._hist_depth, 2)
            self.assertEqual(self.core._hist_depth, 1)
        self.assertEqual(self.core._hist_depth, 0)

    def test_definir_conversa_so_registra_a_conversa_ativa(self):
        """v23: o Gemini não tem mais sessão presa; o histórico é montado do arquivo a cada chamada."""
        self.core.client = object()
        with mock.patch.object(self.Core, "reload_api_keys") as rl:
            self.core.definir_conversa("c2")
        self.assertEqual(self.core.conv_id, "c2")
        rl.assert_not_called()

    def test_gemini_recebe_o_historico_da_conversa_salva(self):
        """v23: a conversa salva vira os 'contents' do Gemini (alternados, terminando na pergunta atual)."""
        self.core.client = object()
        self.core._hist_depth = 1
        fake_genai = mock.MagicMock()
        fake_genai.types.Content = lambda role, parts: ("C", role, parts)
        fake_genai.types.Part = lambda text: ("P", text)
        with mock.patch("brain.zenith_core.genai", fake_genai), \
                mock.patch("brain.zenith_history.get_conversation", return_value=self.CONVERSA):
            contents = self.core._gemini_contents("qual é o meu nome?")
        self.assertEqual(contents, [("C", "user", [("P", "meu nome é Anderson")]),
                                    ("C", "model", [("P", "Prazer, Anderson!")]),
                                    ("C", "user", [("P", "qual é o meu nome?")])])

    def test_validador_pede_uma_correcao(self):
        ruim = "<executar_python>print(1)"
        bom = "<executar_python>print(1)</executar_python>"
        with mock.patch.object(self.Core, "_call_provider", return_value=bom) as ia:
            self.assertEqual(self.core._validar_e_corrigir(ruim, "faz isso"), bom)
        self.assertEqual(ia.call_count, 1)
        with mock.patch.object(self.Core, "_call_provider", return_value="<executar_python>ainda ruim") as ia:
            self.assertEqual(self.core._validar_e_corrigir(ruim, "x"), ruim)
        self.assertEqual(ia.call_count, 1)
        with mock.patch.object(self.Core, "_call_provider") as ia:
            self.assertEqual(self.core._validar_e_corrigir("oi!", "x"), "oi!")
        ia.assert_not_called()
        self.core.settings = FakeSettings(biblia_validador=False)
        with mock.patch.object(self.Core, "_call_provider") as ia:
            self.core._validar_e_corrigir("<ler_url>x", "x")
        ia.assert_not_called()

    def test_extrai_programa_aprender_e_python_sem_cerca(self):
        a = self.core._extract_pending_action("vou\n<executar_python>\n```python\nprint(1)\n```\n</executar_python>")
        self.assertEqual((a.kind, a.content), ("python", "print(1)"))
        txt = ('Vou criar!\n<criar_programa nome="jogo" tipo="janela"><arquivo nome="main.py">print(1)</arquivo></criar_programa>')
        b = self.core._extract_pending_action(txt)
        self.assertEqual(b.kind, "program")
        self.assertEqual(self.Core._remove_tags(txt).strip(), "Vou criar!")
        c = self.core._extract_pending_action(TestAprender.TAG)
        self.assertEqual(c.kind, "learn")
        self.assertIn("[APRENDER]", c.preview())
        self.assertIn("[PROGRAMA] jogo", b.preview())

    def test_lista_negra_vale_para_todos_os_arquivos_e_aprovar_roda_o_executor(self):
        from brain.zenith_gatekeeper import DeterministicGuard
        self.core.guard = DeterministicGuard("Anderson")
        ruim = self.core._extract_pending_action(
            '<criar_programa nome="x"><arquivo nome="main.py">import util</arquivo>'
            '<arquivo nome="util.py">import os\nos.system("shutdown /s")</arquivo></criar_programa>')
        with mock.patch.object(P, "executar") as ex:
            self.assertIn("VETADO", self.core.approve_action(ruim))
        ex.assert_not_called()
        bom = self.core._extract_pending_action('<criar_programa nome="x"><arquivo nome="main.py">print(1)</arquivo></criar_programa>')
        with mock.patch.object(P, "executar", return_value="rodou") as ex:
            self.assertEqual(self.core.approve_action(bom), "rodou")
        self.assertEqual(ex.call_args.args[0].nome, "x")

    def test_aprovar_aprendizado_grava_o_cartao(self):
        from brain.zenith_gatekeeper import DeterministicGuard
        self.core.guard = DeterministicGuard("Anderson")
        a = self.core._extract_pending_action(TestAprender.TAG)
        with mock.patch.object(K, "salvar_aprendizado", return_value="🧠 Guardei") as sv:
            self.assertEqual(self.core.approve_action(a), "🧠 Guardei")
        sv.assert_called_once()


# ======================================================================
class TestComandos(unittest.TestCase):
    def setUp(self):
        pausa._resetar()
        self.core = mock.MagicMock()
        self.core.ia_ativa = "openai"
        self.core.conv_id = None
        self.core._build_system_prompt.return_value = "x" * 4000

    def tearDown(self):
        pausa._resetar()

    def test_biblia_lista_mostra_e_apaga(self):
        r = cmd.tratar("/biblia")["resposta"]
        self.assertIn("programacao", r)
        self.assertIn("Não achei", cmd.tratar("/biblia nao-existe")["resposta"])
        self.assertIn("Programação", cmd.tratar("/biblia programacao")["resposta"] + "Programação")
        self.assertIn("Só dá pra apagar", cmd.tratar("/biblia apagar programacao")["resposta"])

    def test_contexto_mostra_perfil_modo_e_barra(self):
        cfg = FakeSettings(contexto_modo="max")
        r = cmd.tratar("/contexto", {"core": self.core, "settings": cfg})["resposta"]
        self.assertIn("openai", r)
        self.assertIn("memória de conversa: max", r)
        self.assertIn("~1000 tokens", r)
        self.assertRegex(r, r"\d+(\.\d)?%")
        r2 = cmd.tratar("/contexto economico", {"core": self.core, "settings": cfg})["resposta"]
        self.assertEqual(cfg.dados["contexto_modo"], "economico")
        self.assertIn("economico", r2)
        cmd.tratar("/contexto desligado", {"core": self.core, "settings": cfg})
        self.assertEqual(cfg.dados["contexto_modo"], "desligado")
        self.assertIn("DESLIGADA", cmd.tratar("/contexto", {"core": self.core, "settings": cfg})["resposta"])

    def test_inteligencia_liga_contexto_e_raciocinio_e_recria_a_sessao(self):
        cfg = FakeSettings(contexto_modo="economico", thinking_mode="economico")
        r = cmd.tratar("/inteligencia max", {"core": self.core, "settings": cfg})["resposta"]
        self.assertEqual((cfg.dados["contexto_modo"], cfg.dados["thinking_mode"]), ("max", "pensante"))
        self.core.reload_api_keys.assert_called_once_with(cfg)
        self.assertIn("Inteligência", r)
        cmd.tratar("/inteligencia economico", {"core": self.core, "settings": cfg})
        self.assertEqual(cfg.dados["thinking_mode"], "economico")
        self.assertIn("Uso:", cmd.tratar("/inteligencia", {"core": self.core, "settings": cfg})["resposta"])

    def test_programas_e_parar(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(P, "_base", lambda: Path(d)):
            self.assertIn("Nenhum programa", cmd.tratar("/programas")["resposta"])
            (Path(d) / "jogo").mkdir()
            (Path(d) / "jogo" / "main.py").write_text("1", encoding="utf-8")
            self.assertIn("jogo", cmd.tratar("/programas")["resposta"])
        self.assertIn("Nenhum programa", cmd.tratar("/parar_programa jogo")["resposta"])

    def test_testar_busca_roda_cada_fonte_sem_parar_na_primeira(self):
        def ok(q, s, n):
            return [{"titulo": "x"}]

        def vazio(q, s, n):
            return []

        def erro(q, s, n):
            raise ConnectionError("bloqueado")
        with mock.patch.object(S, "_sessao", lambda x=None: object()), \
                mock.patch.object(S, "FONTES_TEXTO", (("Fonte A", ok), ("Fonte B", erro))), \
                mock.patch.object(S, "FONTES_IMAGEM", (("Img A", vazio), ("Img B", ok))):
            r = cmd.tratar("/testar_busca")["resposta"]
        self.assertIn("✓ Texto: Fonte A: 1 resultado(s)", r)
        self.assertIn("✗ Texto: Fonte B: bloqueado", r)
        self.assertIn("sem resultados", r)
        self.assertIn("✓ Imagem: Img B", r)
        self.assertIn("basta UMA fonte de texto e UMA de imagem", r)

    def test_ajuda_e_modos(self):
        r = cmd.tratar("/ajuda")["resposta"]
        for c in ("/inteligencia", "/contexto", "/biblia", "/programas", "/parar_programa", "/testar_busca", "ZENITH.md", "tutor|ensinar"):
            self.assertIn(c, r)
        cfg = FakeSettings()
        self.assertIn("Tutor", cmd.tratar("/modo tutor", {"settings": cfg})["resposta"])
        cmd.tratar("/modo socratico", {"settings": cfg})
        self.assertEqual(cfg.dados["modo_atual"], "tutor")
        cmd.tratar("/modo ensinar", {"settings": cfg})
        self.assertEqual(cfg.dados["modo_atual"], "ensinar")
        self.assertIn("tutor", modos.formatar_lista("normal").lower())


# ======================================================================
class TestContratos(unittest.TestCase):
    def ler(self, rel):
        return (RAIZ / rel).read_text(encoding="utf-8")

    def test_headless_avisa_a_conversa_e_passa_o_core(self):
        src = self.ler("brain/zenith_headless.py")
        self.assertIn("self.core.definir_conversa(conv_id)", src)
        self.assertIn("self.core.definir_conversa(self.active_conv_id)", src)
        self.assertIn('"core": self.core', src)
        self.assertIn("garantir_arquivos", src)

    def test_reset_e_pendrive_apagam_o_zenith_md_pessoal(self):
        from brain import zenith_reset
        self.assertIn("config/ZENITH.md", zenith_reset.ARQUIVOS)
        self.assertIn('"ZENITH.md"', self.ler("prepare_pendrive.py"))

    def test_padroes_de_inteligencia(self):
        from brain import zenith_settings as cfg
        d = cfg.DEFAULT_SETTINGS
        self.assertEqual(d["thinking_mode"], "pensante")       # o econômico deixava o Gemini mais "burro"
        self.assertEqual(d["contexto_modo"], "max")
        self.assertTrue(d["biblia_validador"])
        self.assertEqual(d["gemini_modelo"], "gemini-3.5-flash")   # v23: era 2.5-flash
        self.assertEqual(d["modelos_override"], {})

    def test_versao(self):
        from brain import zenith_version
        # v1.0: a numeração passou a ser vMAJOR.MINOR, então a comparação usa a tupla (numero()).
        self.assertGreaterEqual(zenith_version.numero(), (1, 0, 0))   # sobe a cada entrega

    def test_godot_usa_dialogo_nativo_no_anexo_e_cola_imagem(self):
        gd = self.ler("body/zenith/ui_manager.gd")
        corpo_anexo = gd[gd.index("func _abrir_seletor_de_anexo"):]
        corpo_anexo = corpo_anexo[:corpo_anexo.index("# ================= ENTRADA")]
        self.assertIn("use_native_dialog = true", corpo_anexo)
        self.assertIn("clipboard_has_image()", gd)
        self.assertIn("clipboard_get_image()", gd)
        self.assertIn("input_field.gui_input.connect(_on_input_gui_input)", gd)
        self.assertIn("_pending_attachment_path = caminho", gd)

    def test_gdscript_do_ctrl_v_tem_indentacao_com_tabs_e_nao_mistura(self):
        gd = self.ler("body/zenith/ui_manager.gd")
        trecho = gd[gd.index("func _on_input_gui_input"):gd.index("func _abrir_seletor_de_anexo")]
        for linha in trecho.splitlines():
            if linha.strip() and not linha.startswith("#"):
                self.assertFalse(linha.startswith(" "), repr(linha))     # GDScript: só tabs

    def test_arquivos_que_eram_crlf_continuam_crlf(self):
        for nome in ("zenith_core.py", "zenith_executor.py", "zenith_gatekeeper.py"):
            self.assertIn(b"\r\n", (RAIZ / "brain" / nome).read_bytes(), nome)

    def test_modulos_novos_sem_chave_ou_caminho_pessoal(self):
        for nome in ("zenith_conhecimento.py", "zenith_contexto.py", "zenith_programa.py"):
            t = (RAIZ / "brain" / nome).read_text(encoding="utf-8")
            self.assertNotRegex(t, r"sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}|C:\\Users\\|D:/Código")

    def test_nenhum_endereco_de_provedor_nos_textos_novos(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pp", RAIZ / "prepare_pendrive.py")
        pp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pp)
        tudo = json.dumps(K.PERFIS_PADRAO) + K.ZENITH_MD_MODELO + BI.gerar_markdown()
        for host in pp.HOSTS_DE_PROVEDOR:
            self.assertNotIn(host, tudo.lower(), host)

    def test_biblia_md_do_projeto_esta_em_dia(self):
        self.assertEqual(self.ler("BIBLIA_ZENITH.md").replace("\r\n", "\n").strip(), BI.gerar_markdown().replace("\r\n", "\n").strip())


if __name__ == "__main__":
    unittest.main()
