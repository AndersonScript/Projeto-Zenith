"""
Testes do v26 — filtro de tags, "verificar antes de afirmar", PARAR + status de atividade, matemática/LaTeX,
fórmulas e a 1ª abertura do .exe como administrador.
Rodar: python -m unittest tests.test_v26 -v
NÃO provam: o Godot de verdade (linha de status, botão ⏹, cores do microfone) — só os contratos entre as pontas
e a sintaxe. Isso se vê abrindo o Zenith.
"""
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

from brain import zenith_admin as ADM
from brain import zenith_commands as cmd
from brain import zenith_formulas as FM
from brain import zenith_matematica as M
from brain import zenith_parar as PA
from brain import zenith_stream as S
from brain import zenith_tags as T
from brain import zenith_verificar as V


class FakeSettings:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **d):
        self.d = dict(d)

    def get(self, chave, padrao=None):
        v = self.d.get(chave, padrao)
        return padrao if v is None else v


# ======================================================================
class TestTags(unittest.TestCase):
    def test_nome_errado_vira_o_certo(self):
        self.assertEqual(T.corrigir_tags("<lembral>gosta de física</lembral>"), "<lembrar>gosta de física</lembrar>")
        self.assertEqual(T.corrigir_tags("<executar_pyton>print(1)</executar_pyton>"),
                         "<executar_python>print(1)</executar_python>")

    def test_nome_certo_nao_muda(self):
        s = "<lembrar>x</lembrar> e <corpo>emocao:happy</corpo>"
        self.assertEqual(T.corrigir_tags(s), s)

    def test_html_e_codigo_ficam_como_estao(self):
        s = "veja <b>negrito</b> e <br> e a<b>c"
        self.assertEqual(T.corrigir_tags(s), s)
        self.assertEqual(T.limpar_visivel(s), s)
        cod = "Assim: ```html\n<lembral>x</lembral><div>ok</div>\n``` e `<lembral>` inline"
        self.assertEqual(T.corrigir_tags(cod), cod)
        self.assertEqual(T.limpar_visivel(cod), cod)

    def test_o_caso_do_print_do_anderson(self):
        txt = ("<lembral> O usuário é o Anderson, criador do sistema Zenith. </lembral>\n\n"
               "A primeira busca acabou trazendo uns resultados de rádio...")
        vis = T.limpar_visivel(T.corrigir_tags(txt))
        self.assertNotIn("lembral", vis)
        self.assertNotIn("criador do sistema", vis)               # o conteúdo era só pra memória
        self.assertTrue(vis.startswith("A primeira busca"))

    def test_marca_solta_some_e_desconhecida_mantem_o_texto(self):
        self.assertEqual(T.limpar_visivel("texto <lembrar> aberto sem fechar"), "texto  aberto sem fechar")
        self.assertEqual(T.limpar_visivel("<pensando>raciocínio</pensando> resposta"), "raciocínio resposta")
        self.assertEqual(T.limpar_visivel("Se x<y>z então ok"), "Se x<y>z então ok")     # matemática, não etiqueta

    def test_core_remove_tags_pega_nome_errado(self):
        from brain.zenith_core import ZenithCore
        saida = ZenithCore._remove_tags("Oi <lembral>fato</lembral> tudo bem?")
        self.assertNotIn("lembral", saida)
        self.assertNotIn("fato", saida)                           # o conteúdo era só pra memória
        self.assertTrue(saida.startswith("Oi") and saida.endswith("tudo bem?"))

    def test_core_salva_fato_mesmo_com_etiqueta_escrita_errado(self):
        from brain.zenith_core import ZenithCore
        c = object.__new__(ZenithCore)
        c.memory = mock.Mock()
        c._guardar_fatos("Claro! <lembral>O usuário é o Anderson</lembral> Anotado.")
        c.memory.save_fact.assert_called_once_with("O usuário é o Anderson")


# ======================================================================
class TestVerificar(unittest.TestCase):
    BASE = r"C:\Zenith\Zenith\dist\Zenith\creations"

    def _existe(self, *caminhos):
        return lambda p: p in caminhos

    def _recentes(self, *caminhos):
        return lambda pasta, j, agora: [(c, agora - 30) for c in caminhos]

    def test_caminho_inventado_gera_aviso_com_o_arquivo_real(self):
        falso = self.BASE + r"\minha_imagem.png"
        real = self.BASE + r"\autorretrato.png"
        texto = f"A imagem foi gerada e salva no sistema:\n`{falso}`\nProntinho!"
        out, prob = V.conferir(texto, self.BASE, existe=self._existe(real), recentes=self._recentes(real))
        self.assertEqual(len(prob), 1)
        self.assertIn("NÃO existe", out)
        self.assertIn(real, out)

    def test_arquivo_que_existe_nao_gera_aviso(self):
        real = self.BASE + r"\autorretrato.png"
        out, prob = V.conferir(f"Pronto, está em {real}", self.BASE, existe=self._existe(real))
        self.assertEqual(prob, [])
        self.assertEqual(out, f"Pronto, está em {real}")

    def test_futuro_e_caminho_de_exemplo_nao_alarmam(self):
        falso = self.BASE + r"\x.png"
        self.assertEqual(V.conferir(f"Vou salvar em {falso} quando você aprovar.", self.BASE, existe=lambda p: False)[1], [])
        self.assertEqual(V.conferir(r"Pronto! Salvei em C:\Users\voce\Documents\x.png", self.BASE, existe=lambda p: False)[1], [])
        self.assertEqual(V.conferir(f"O arquivo está em {falso}", self.BASE, existe=lambda p: False)[1][0]["caminho"], falso)

    def test_nada_recente_avisa_que_provavelmente_nao_foi_criado(self):
        out, prob = V.conferir(f"Salvei em {self.BASE}\\a.png", self.BASE, existe=lambda p: False,
                               recentes=lambda *a: [])
        self.assertIn("provavelmente não foi criado", out)

    def test_o_core_chama_o_verificador(self):
        src = (RAIZ / "brain" / "zenith_core.py").read_text(encoding="utf-8")
        self.assertIn("verificar.conferir(texto, str(CREATION_DIR))", src)
        self.assertIn("ACTION_TAGS.values()", src)             # não confere quando há ação ainda não executada


# ======================================================================
class TestParar(unittest.TestCase):
    def test_palavras_de_parada(self):
        for t in ["calma aí, Zenith", "Calma ai akira!", "para", "pare tudo", "Zenith, para por favor", "espera",
                  "espera aí um segundo", "stop", "chega", "para de falar", "cancela isso", "ei akira calma"]:
            self.assertTrue(PA.eh_pedido_de_parada(t), t)

    def test_frases_normais_nao_param(self):
        for t in ["como parar um carro?", "para que serve a derivada?", "espera, o que é um quaternion?", "oi", "",
                  "o trem para na estação", "para mim fazer o cálculo",
                  "calma, preciso te explicar uma coisa com calma sobre o projeto"]:
            self.assertFalse(PA.eh_pedido_de_parada(t), t)

    def test_geracao_descarta_tarefa_velha(self):
        g = PA.geracao()
        self.assertFalse(PA.cancelado_desde(g))
        PA.solicitar("teste")
        self.assertTrue(PA.cancelado_desde(g))
        self.assertFalse(PA.cancelado_desde(PA.geracao()))

    def test_mata_processo_registrado(self):
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        PA.registrar_processo(p)
        PA.solicitar("teste")
        p.wait(timeout=10)
        self.assertNotEqual(p.returncode, 0)

    def test_executor_para_o_script_no_meio(self):
        from brain import zenith_executor as E
        ex = E.ZenithExecutor()
        a = ex.create_pending("python", "import time\nprint('x', flush=True)\ntime.sleep(12)\nprint('fim')")
        threading.Timer(0.8, lambda: PA.solicitar("teste")).start()
        t0 = time.time()
        r = ex.run_python(a, True)
        self.assertIn("Parei o código", r)
        self.assertLess(time.time() - t0, 8)

    def test_executor_normal_continua_igual(self):
        from brain import zenith_executor as E
        ex = E.ZenithExecutor()
        self.assertEqual(ex.run_python(ex.create_pending("python", "print('oi')"), True).strip(), "oi")
        self.assertIn("terminou com erro", ex.run_python(ex.create_pending("python", "raise SystemExit(3)"), True))

    def test_mensagem_de_atividade(self):
        m = PA.mensagem_atividade("programando")
        self.assertEqual((m["action"], m["estado"], m["pode_parar"]), ("atividade", "programando", True))
        self.assertFalse(PA.mensagem_atividade("ocioso")["pode_parar"])
        self.assertEqual(PA.estado_da_acao("search")[0], "pesquisando")
        self.assertEqual(PA.estado_da_acao("python")[0], "rodando")
        self.assertEqual(PA.estado_da_acao("tipo_novo")[0], "rodando")

    def test_comando_parar(self):
        self.assertEqual(cmd.tratar("/parar")["acao"], "parar")
        self.assertEqual(cmd.tratar("/stop")["acao"], "parar")
        self.assertNotEqual(cmd.tratar("/parar_observacao")["acao"], "parar")     # os outros "parar_…" continuam os mesmos


class FakeFala:
    def __init__(self):
        self.cancelada = False

    def cancelar(self, silencioso=False):
        self.cancelada = True


class TestCerebroParar(unittest.TestCase):
    def setUp(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        self.msgs = []
        b.bridge = type("B", (), {"send": lambda s, m: self.msgs.append(m)})()
        b.settings = FakeSettings(voice_enabled=False, response_streaming=False, vida_gestos_ia=False)
        b.active_conv_id = "c1"
        b._pending_approvals = {}
        b._pending_mic_approvals = set()
        b._proxima_fala_vira_nota = False
        b.interaction = mock.Mock()
        b.observador = None
        b._parar_observacao = mock.Mock()
        b._enviar_midias = lambda: None
        b.proactive = mock.Mock()
        self.b = b
        for alvo, valor in (("brain.zenith_headless.history.append_message", lambda *a, **k: None),
                            ("brain.zenith_headless.pausa.ativo", lambda: False),
                            ("brain.zenith_headless.actionlog.registrar", lambda *a, **k: None)):
            p = mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

    def _acoes(self):
        return [m.get("action") for m in self.msgs]

    def test_parar_tudo_corta_tudo_e_avisa(self):
        sessao = mock.Mock()
        self.b._sessao_atual = sessao
        pend = mock.Mock(kind="python", description="rodar")
        self.b._pending_approvals["r1"] = pend
        self.b._atividade_atual = ("pensando", "")
        g = PA.geracao()
        self.b._parar_tudo("teste")
        self.assertTrue(PA.cancelado_desde(g))
        sessao.cancelar.assert_called_once()
        self.b.interaction.parar_de_falar.assert_called_once()
        self.b.interaction.parar_de_escutar.assert_called_once()
        self.assertEqual(self.b._pending_approvals, {})
        self.assertIn("r1", self.b._pedidos_cancelados)
        self.assertIn("mic_state", self._acoes())
        texto = [m for m in self.msgs if m.get("action") == "chat_message"][-1]["text"]
        self.assertIn("Parei", texto)

    def test_sem_nada_em_andamento_diz_isso(self):
        self.b._atividade_atual = ("ocioso", "")
        self.b._parar_tudo("teste")
        texto = [m for m in self.msgs if m.get("action") == "chat_message"][-1]["text"]
        self.assertIn("não tinha nada em andamento", texto)

    def test_palavra_de_parada_nao_vai_pra_ia(self):
        self.b.core = mock.Mock()
        self.b._parar_tudo = mock.Mock()
        self.b._handle_chat({"text": "calma aí, Zenith"})
        self.b._parar_tudo.assert_called_once()
        self.b.core.pensar.assert_not_called()

    def test_resultado_de_tarefa_velha_e_descartado(self):
        g = PA.geracao()
        PA.solicitar("teste")
        self.b._deliver_result({"text": "Resposta que chegou tarde.", "pending_action": None, "blocked": False}, None, g)
        self.assertNotIn("chat_stream_chunk", self._acoes())
        self.assertNotIn("chat_message", self._acoes())

    def test_aprovacao_cancelada_avisa_em_vez_de_ficar_muda(self):
        self.b._pedidos_cancelados = {"r9"}
        self.b._handle_approval_response({"request_id": "r9", "approved": True})
        self.assertIn("cancelado quando você mandou parar", self.msgs[-1]["text"])

    def test_atividade_so_manda_quando_muda(self):
        self.b._atividade_atual = ("ocioso", "")
        self.b._atividade("pensando")
        self.b._atividade("pensando")
        self.b._atividade("ocioso")
        estados = [m["estado"] for m in self.msgs if m.get("action") == "atividade"]
        self.assertEqual(estados, ["pensando", "ocioso"])

    def test_estado_espelha_no_corpo_e_na_linha_de_status(self):
        self.b._atividade_atual = ("ocioso", "")
        self.b._estado("thinking")
        self.b._estado("speaking")
        self.assertEqual([m for m in self.msgs if m.get("action") == "do"],
                         [{"action": "do", "name": "state:thinking"}, {"action": "do", "name": "state:speaking"}])
        self.assertEqual([m["estado"] for m in self.msgs if m.get("action") == "atividade"], ["pensando", "falando"])

    def test_fases_do_mic(self):
        self.b._mic_fase("transcrevendo")
        self.assertEqual(self.msgs[-1], {"action": "mic_fase", "fase": "transcrevendo", "texto": "Transcrevendo…"})

    def test_aprovacao_roda_em_thread_pra_nao_travar_o_laco_do_websocket(self):
        src = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('if action == "approval_response":', src)
        self.assertIn("threading.Thread(target=handler, args=(data,), daemon=True).start()", src)


# ======================================================================
class TestMatematicaTexto(unittest.TestCase):
    def test_unicode_fisica(self):
        self.assertEqual(M.latex_para_unicode(r"x(t) = A\cos(\omega t + \phi)"), "x(t) = A cos(ω t + ϕ)")
        self.assertEqual(M.latex_para_unicode(r"\int_0^1 x^2\,dx"), "∫₀¹ x² dx")
        self.assertEqual(M.latex_para_unicode(r"T = 2\pi\sqrt{\frac{L}{g}}"), "T = 2π√(L/g)")
        self.assertEqual(M.latex_para_unicode(r"L = \frac{1}{2} m \dot{x}^2 - V(x)"), "L = 1/2 m x\u0307² - V(x)")        # ẋ = x + ponto combinante
        self.assertIn("E⃗", M.latex_para_unicode(r"\vec{E}"))
        self.assertIn("∂", M.latex_para_unicode(r"\frac{\partial L}{\partial q}"))

    def test_fala_em_portugues(self):
        self.assertEqual(M.latex_para_fala(r"\int_0^1 x^2 dx"), "integral de 0 até 1 de x ao quadrado dx")
        self.assertEqual(M.latex_para_fala(r"x^2 + y^3 = z"), "x ao quadrado mais y ao cubo igual a z")
        self.assertIn("raiz quadrada de", M.latex_para_fala(r"\sqrt{\pi}"))
        self.assertIn("derivada parcial", M.latex_para_fala(r"\frac{\partial L}{\partial q}"))
        self.assertIn("integral de menos infinito até infinito de", M.latex_para_fala(r"\int_{-\infty}^{\infty} e^{-x^2}dx"))
        self.assertIn("limite quando h tende a 0", M.latex_para_fala(r"\lim_{h \to 0} f(h)"))
        self.assertNotIn("\\", M.latex_para_fala(r"\nabla\times\vec{E}=-\frac{\partial\vec{B}}{\partial t}"))

    def test_acha_trechos_e_ignora_dinheiro_e_codigo(self):
        t = M.achar_trechos("Custa $5 e depois $10, mas $x^2$ é matemática e $$a=b$$ também.")
        self.assertEqual([(x.latex, x.display) for x in t], [("x^2", False), ("a=b", True)])
        self.assertEqual(M.achar_trechos("Custa R$ 50 e R$ 100."), [])
        self.assertEqual(M.achar_trechos("```python\nx = '$$a$$'\n``` e `$x^2$`"), [])
        d = M.achar_trechos(r"veja \[ \int f \] e \( x \) e \begin{equation} a=b \end{equation}")
        self.assertEqual([x.display for x in d], [True, False, True])

    def test_sem_matematica_o_texto_passa_igual(self):
        r = M.processar_resposta("Oi! Tudo bem? Custa R$ 50.", tempfile.gettempdir())
        self.assertEqual((r.chat, r.historico, r.fala, r.imagens), ("Oi! Tudo bem? Custa R$ 50.",) * 3 + ([],))

    def test_resposta_com_equacao_vira_marcador_imagem_e_fala(self):
        gerados = []

        def falso_renderizador(latex, caminho, estilo):
            gerados.append((latex, str(caminho)))
            return True
        r = M.processar_resposta("A energia é $E = mc^2$ e a integral:\n$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$\nFim.",
                                 "/tmp/x", renderizar=falso_renderizador, agora=0)
        self.assertEqual(len(r.imagens), 1)
        self.assertIn("[Equação 1 ↓]", r.chat)
        self.assertIn("E = mc²", r.chat)                          # inline vira texto legível
        self.assertNotIn("$", r.chat)
        self.assertNotIn("[Equação", r.historico)                 # histórico guarda texto, sem marcador de imagem
        self.assertIn("∫₀¹ x² dx = 1/3", r.historico)
        self.assertIn("integral de 0 até 1", r.fala)
        self.assertNotIn("\\", r.fala)

    def test_se_a_imagem_falha_a_equacao_aparece_em_texto(self):
        r = M.processar_resposta("$$a^2 + b^2 = c^2$$", "/tmp/x", renderizar=lambda *a: False)
        self.assertEqual(r.imagens, [])
        self.assertEqual(r.falhas, [1])                    # v27: o aviso vai à parte; o TEXTO do balão não depende da imagem
        self.assertIn("a² + b² = c²", r.chat)

    def test_limite_de_imagens_por_resposta(self):
        txt = "\n".join(f"$$x_{i}=y_{i}$$" for i in range(10))
        r = M.processar_resposta(txt, "/tmp/x", renderizar=lambda *a: True, agora=0)
        self.assertEqual(len(r.imagens), M.MAX_IMAGENS)

    def test_latex_solto_vira_unicode_mas_caminho_do_windows_nao(self):
        r = M.processar_resposta(r"Use \frac{a}{b} aqui, e o arquivo C:\Users\joao\Zenith\int\x.png fica.", "/tmp/x")
        self.assertIn("a/b", r.chat)
        self.assertIn(r"C:\Users\joao\Zenith\int\x.png", r.chat)

    def test_saneamento_para_o_mathtext(self):
        s = M.sanear_para_mathtext(r"\dfrac{a}{b} \text{em m/s} \operatorname{rot}\vec F \oint \vec E")
        self.assertIn(r"\frac{a}{b}", s)
        self.assertIn(r"\mathrm{em\ m/s}", s)
        self.assertIn(r"\mathrm{rot}\,", s)
        self.assertIn(r"\oint\!", s)
        self.assertEqual(M.dividir_em_linhas(r"\begin{aligned} a &= b \\ c &= d \end{aligned}"), ["a  = b", "c  = d"])


class TestMatematicaImagem(unittest.TestCase):
    def test_desenha_png_de_verdade(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "eq_teste.png"
            self.assertTrue(M.renderizar_png(r"\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{q}}\right)=\frac{\partial L}{\partial q}", p))
            self.assertGreater(p.stat().st_size, 2000)
            from PIL import Image
            with Image.open(p) as im:                          # fechar o arquivo: no Windows ele trava a pasta temporária
                self.assertGreater(im.width, 100)
                self.assertGreater(im.height, 40)

    def test_estilos_claro_e_transparente(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            claro, transp = Path(d) / "c.png", Path(d) / "t.png"
            self.assertTrue(M.renderizar_png(r"x^2", claro, M.ESTILO_CLARO))
            self.assertTrue(M.renderizar_png(r"x^2", transp, M.ESTILO_TRANSPARENTE))
            with Image.open(claro) as a, Image.open(transp) as b:
                self.assertEqual(a.convert("RGBA").getpixel((2, 2))[:3], (255, 255, 255))
                self.assertEqual(b.convert("RGBA").getpixel((2, 2))[3], 0)

    def test_equacao_invalida_nao_derruba(self):
        with tempfile.TemporaryDirectory() as d:
            M.renderizar_png(r"\frac{a}{", Path(d) / "x.png")        # não pode levantar exceção

    def test_limpa_imagens_antigas(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(8):
                (Path(d) / f"eq_{i}.png").write_bytes(b"x")
            M.limpar_antigos(d, manter=3)
            self.assertEqual(len(list(Path(d).glob("eq_*.png"))), 3)


# ======================================================================
class TestFormulas(unittest.TestCase):
    def test_todo_o_banco_o_mathtext_entende(self):
        ruins = []
        for chave, (titulo, itens) in FM.BANCO.items():
            for nome, latex, _nota in itens:
                for ln in (M.dividir_em_linhas(latex) or [M.sanear_para_mathtext(latex)]):
                    try:
                        M._linha_png(ln, M.ESTILO_ESCURO)
                    except Exception as e:
                        ruins.append((chave, nome, str(e)[:80]))
        self.assertEqual(ruins, [])

    def test_banco_cobre_o_que_o_anderson_pediu(self):
        for k in ("mecanica", "optica", "derivadas", "integrais"):
            self.assertIn(k, FM.BANCO)
            self.assertGreaterEqual(len(FM.BANCO[k][1]), 8)
        nomes = " ".join(n for _, itens in FM.BANCO.values() for n, _l, _no in itens).lower()
        for termo in ("euler", "lagrangiana", "snell", "lente", "rayleigh", "regra da cadeia", "por partes"):
            self.assertIn(termo, nomes)

    def test_comandos_e_ajuda(self):
        self.assertIn("mecanica", cmd.tratar("/formula")["resposta"])
        self.assertEqual(cmd.tratar("/formula mecânica 2")["args"], {"tipo": "formula", "assunto": "mecanica", "pagina": 2})
        self.assertEqual(cmd.tratar("/formula buscar lagrange")["args"]["tipo"], "formula_busca")
        self.assertIn("Não conheço", cmd.tratar("/formula xyz")["resposta"])
        self.assertEqual(cmd.tratar(r"/latex \frac{a}{b}")["args"], {"tipo": "latex", "texto": r"\frac{a}{b}"})
        self.assertEqual(cmd.tratar("/integrar sin(x) de 0 ate pi")["args"],
                         {"tipo": "integrar", "expr": "sin(x)", "a": "0", "b": "pi"})
        self.assertEqual(cmd.tratar("/derivar exp(-t^2) em t")["args"], {"tipo": "derivar", "expr": "exp(-t^2)", "var": "t"})
        self.assertEqual(cmd.tratar("/limite sin(x)/x quando x->0")["args"]["ponto"], "0")
        ajuda = cmd.tratar("/ajuda")["resposta"]
        for c in ("/parar", "/latex", "/formula", "/derivar", "/integrar", "/limite", "/aparencia"):
            self.assertIn(c, ajuda)

    def test_latex_gera_imagem_e_texto(self):
        with tempfile.TemporaryDirectory() as d:
            r = FM.executar({"tipo": "latex", "texto": r"claro \int_0^1 x^2\,dx = \frac13"}, d)
            self.assertEqual(len(r["imagens"]), 1)
            self.assertTrue(Path(r["imagens"][0][0]).exists())
            self.assertIn("∫₀¹ x² dx = 1/3", r["texto"])
            self.assertIn(r"\int_0^1", r["texto"])                 # o LaTeX volta pra copiar

    def test_folha_de_formulas(self):
        with tempfile.TemporaryDirectory() as d:
            r = FM.executar({"tipo": "formula", "assunto": "optica", "pagina": 1}, d)
            self.assertEqual(len(r["imagens"]), 1)
            self.assertIn("Lei de Snell", r["texto"])
            self.assertIn("página 1 de", r["texto"])
            b = FM.executar({"tipo": "formula_busca", "texto": "lagrange"}, d)
            self.assertIn("Euler", b["texto"])

    def test_paginas(self):
        _t, itens, total = FM.pagina_do_assunto("mecanica", 1)
        self.assertEqual(len(itens), FM.POR_PAGINA)
        self.assertGreaterEqual(total, 2)
        self.assertEqual(FM.pagina_do_assunto("mecanica", 99)[2], total)


try:
    import sympy  # noqa: F401
    _TEM_SYMPY = True
except Exception:
    _TEM_SYMPY = False


@unittest.skipUnless(_TEM_SYMPY, "sympy não instalado (é opcional)")
class TestCalculoExato(unittest.TestCase):
    def test_derivada(self):
        r = FM.derivar("x**2*sin(x)")
        self.assertTrue(r["conferido"])
        import sympy as sp
        x = sp.Symbol("x")
        self.assertEqual(sp.simplify(r["resultado"] - (2 * x * sp.sin(x) + x**2 * sp.cos(x))), 0)

    def test_integral_indefinida_e_definida(self):
        r = FM.integrar("x**2")
        self.assertTrue(r["conferido"])
        self.assertIn("x^{3}", r["latex"])
        d = FM.integrar("sin(x)", None, "0", "pi")
        self.assertEqual(int(d["resultado"]), 2)
        g = FM.integrar("exp(-x^2)", None, "-oo", "oo")
        self.assertTrue(g["conferido"])
        self.assertIn("sqrt", str(g["resultado"]).lower())

    def test_limite(self):
        self.assertEqual(int(FM.limite("sin(x)/x", "0")["resultado"]), 1)

    def test_entrada_maliciosa_e_barrada(self):
        for ruim in ("__import__('os').system('ls')", "x.__class__", "open(1)", "lambda: 1", "x; import os"):
            with self.assertRaises(FM.ErroCalculo):
                FM.derivar(ruim)

    def test_comando_completo_com_imagem(self):
        with tempfile.TemporaryDirectory() as d:
            r = FM.executar({"tipo": "integrar", "expr": "x*exp(x)"}, d)
            self.assertIn("✔ conferi", r["texto"])
            self.assertEqual(len(r["imagens"]), 1)


class TestSemSympy(unittest.TestCase):
    def test_sem_sympy_o_aviso_e_amigavel(self):
        with mock.patch.dict(sys.modules, {"sympy": None}):
            r = FM.executar({"tipo": "derivar", "expr": "x**2"}, tempfile.gettempdir())
        self.assertIn("sympy", r["texto"])
        self.assertEqual(r["imagens"], [])


# ======================================================================
class TestStreamComMatematica(unittest.TestCase):
    def portao(self):
        saida = []
        return S.Portao(saida.append), saida

    def test_equacao_fecha_o_portao_como_etiqueta(self):
        for trecho in ("A energia é $E = mc^2$. Pronto.", "Veja $$a=b$$ ok.", r"Veja \[ a=b \] ok.", r"A fração \frac{a}{b} é."):
            p, saida = self.portao()
            p.alimentar(trecho)
            self.assertTrue(p.fechado, trecho)
            self.assertEqual(p.motivo, "matematica", trecho)
            self.assertNotIn("$", "".join(saida))
            self.assertNotIn("\\", "".join(saida))

    def test_dinheiro_nao_fecha_o_portao(self):
        p, saida = self.portao()
        p.alimentar("Custa R$ 50 e sai por R$100. Beleza? Tudo certo. ")
        self.assertFalse(p.fechado)
        self.assertEqual("".join(saida), "Custa R$ 50 e sai por R$100. Beleza? Tudo certo. ")

    def test_cifrao_no_fim_do_pedaco_espera_o_proximo(self):
        p, saida = self.portao()
        p.alimentar("Custa R$")
        self.assertFalse(p.fechado)
        p.alimentar(" 50. Beleza? ")
        self.assertFalse(p.fechado)

    def test_entregar_resto_com_fala_diferente(self):
        enviados, fala = [], []

        class F:
            def add(self, t): fala.append(t)
            def fim(self): fala.append("FIM")
        sessao = S.SessaoDeEntrega(enviados.append, criar_fala=lambda: F())
        sessao.ao_liberar("Veja. ")
        fala.clear()
        sessao.entregar_resto("x² [Equação 1 ↓]", "x ao quadrado")
        self.assertEqual(fala, ["x ao quadrado", "FIM"])                       # a voz lê o texto falado...
        self.assertEqual(enviados[-2]["delta"], "x² [Equação 1 ↓]")            # ...e o balão mostra o texto escrito

    def test_entregar_resto_sem_fala_separada_continua_igual(self):
        enviados, fala = [], []

        class F:
            def add(self, t): fala.append(t)
            def fim(self): fala.append("FIM")
        sessao = S.SessaoDeEntrega(enviados.append, criar_fala=lambda: F())
        sessao.ao_liberar("Oi. ")
        fala.clear()
        sessao.entregar_resto("Tchau.")
        self.assertEqual(fala, ["Tchau.", "FIM"])


class TestEntregaComMatematica(unittest.TestCase):
    def setUp(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        self.msgs, self.historico, self.falas = [], [], []
        b.bridge = type("B", (), {"send": lambda s, m: self.msgs.append(m)})()
        b.settings = FakeSettings(voice_enabled=True, response_streaming=False, vida_gestos_ia=False)
        b.active_conv_id = "c1"
        voz = type("V", (), {})()
        voz.falar_async = lambda texto, **k: self.falas.append(texto)
        b.interaction = voz
        b._enviar_midias = lambda: None
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        b._pasta_matematica = lambda: Path(self.tmp.name)
        self.b = b
        for alvo, valor in (("brain.zenith_headless.time.sleep", lambda s: None),
                            ("brain.zenith_headless.history.append_message", lambda *a, **k: self.historico.append(a[2])),
                            ("brain.zenith_headless.pausa.ativo", lambda: False)):
            p = mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

    def test_equacao_vira_imagem_no_chat_texto_legivel_e_fala_em_portugues(self):
        self.b._deliver_result({"text": "A integral vale:\n$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$\nSimples, né?",
                                "pending_action": None, "blocked": False})
        imgs = [m for m in self.msgs if m.get("action") == "chat_image"]
        self.assertEqual(len(imgs), 1)
        self.assertTrue(Path(imgs[0]["path"]).exists())
        self.assertEqual(imgs[0]["caption"], "Equação 1")
        texto = "".join(m.get("delta", "") for m in self.msgs if m.get("action") == "chat_stream_chunk") \
            or "".join(m.get("text", "") for m in self.msgs if m.get("action") == "chat_message")
        self.assertNotIn("$$", texto)
        self.assertNotIn("\\int", texto)
        self.assertIn("[Equação 1 ↓]", texto)
        self.assertEqual(len(self.falas), 1)
        self.assertIn("integral de 0 até 1 de x ao quadrado dx", self.falas[0])
        self.assertNotIn("\\", self.falas[0])
        self.assertNotIn("\\int", self.historico[0])
        self.assertIn("∫₀¹", self.historico[0])

    def test_desligar_latex_entrega_o_texto_cru(self):
        self.b.settings = FakeSettings(voice_enabled=False, response_streaming=False, vida_gestos_ia=False, latex_ativo=False)
        self.b._deliver_result({"text": "Veja $x^2$ aqui.", "pending_action": None, "blocked": False})
        self.assertFalse([m for m in self.msgs if m.get("action") == "chat_image"])
        texto = "".join(m.get("text", "") for m in self.msgs if m.get("action") == "chat_message") \
            or "".join(m.get("delta", "") for m in self.msgs if m.get("action") == "chat_stream_chunk")
        self.assertIn("$x^2$", texto)

    def test_comando_de_matematica_manda_texto_e_imagem(self):
        self.b._atividade_atual = ("ocioso", "")
        self.b._rodar_matematica({"tipo": "latex", "texto": r"\frac{a}{b}"})
        acoes = [m.get("action") for m in self.msgs]
        self.assertIn("chat_message", acoes)
        self.assertIn("chat_image", acoes)
        self.assertEqual([m["estado"] for m in self.msgs if m.get("action") == "atividade"][-1], "ocioso")


# ======================================================================
class TestAdmin(unittest.TestCase):
    @mock.patch.dict("os.environ", {"ZENITH_EDICAO": "admin"})   # v1.4: na edição Pública o pedido de administrador nunca aparece
    def test_decisao(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ADM.decidir(d, frozen=False, windows=True, admin=False), "nada")      # código-fonte: não incomoda
            self.assertEqual(ADM.decidir(d, frozen=True, windows=False, admin=False), "nada")
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=False), "perguntar")
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=True), "marcar")
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=None), "nada")
            ADM.marcar(d, ADM.MARCA_OK)
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=False), "nada")      # já resolvido
        with tempfile.TemporaryDirectory() as d:
            # v27: a marca "dispensado" da v26 NÃO vale mais — o "Não" não cala a pergunta pra sempre
            ADM.marcar(d, ADM.MARCA_DISPENSADO)
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=False), "perguntar")

    def test_launcher_chama_antes_de_subir_o_cerebro(self):
        src = (RAIZ / "zenith_launcher.py").read_text(encoding="utf-8")
        self.assertLess(src.index("_primeira_execucao_admin()\n"), src.index("ensure_dependencies"))
        self.assertIn("adm.reabrir_como_admin()", src)
        self.assertNotIn("adm.marcar(CONFIG_DIR, adm.MARCA_DISPENSADO)", src)                  # "Não" não grava mais nada

    def test_pendrive_limpa_as_marcas(self):
        src = (RAIZ / "prepare_pendrive.py").read_text(encoding="utf-8")
        self.assertIn('".admin_ok"', src)
        self.assertIn('".admin_dispensado"', src)

    def test_build_avisa_e_escreve_leia_me(self):
        src = (RAIZ / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn("LEIA-ME_PRIMEIRA_VEZ.txt", src)
        self.assertIn("COMO ADMINISTRADOR", src)


# ======================================================================
class TestAparenciaEAutorretrato(unittest.TestCase):
    def test_padrao_e_a_cor_da_akira_atual(self):
        from brain import zenith_img as I
        self.assertEqual(I.APARENCIA_PADRAO["cabelo"], "#7ad0e8")
        self.assertEqual(I.APARENCIA_PADRAO["olhos"], "#3ccfb4")

    def test_aparencia_salva_e_le(self):
        from brain import zenith_img as I
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(I, "_arquivo_aparencia", lambda: Path(d) / "aparencia.json"):
                self.assertEqual(I.ler_aparencia(), I.APARENCIA_PADRAO)
                I.salvar_aparencia({"cabelo": "ff00aa", "olhos": "invalido", "coisa": "#000000"})
                self.assertEqual(I.ler_aparencia()["cabelo"], "#ff00aa")
                self.assertEqual(I.ler_aparencia()["olhos"], I.APARENCIA_PADRAO["olhos"])
                I.apagar_aparencia()
                self.assertEqual(I.ler_aparencia(), I.APARENCIA_PADRAO)

    def test_comando_aparencia(self):
        from brain import zenith_img as I
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(I, "_arquivo_aparencia", lambda: Path(d) / "aparencia.json"):
                self.assertIn("#7ad0e8", cmd.tratar("/aparencia")["resposta"])
                self.assertIn("#112233", cmd.tratar("/aparencia cabelo #112233")["resposta"])
                self.assertIn("padrão", cmd.tratar("/aparencia padrao")["resposta"])

    def test_biblia_ensina_latex_e_honestidade_do_autorretrato(self):
        from brain import zenith_biblia as B
        guia = B.SECOES["matematica"]["texto"]
        self.assertIn("$$", guia)
        self.assertIn("/derivar", guia)
        self.assertIn("não a captura do seu corpo 3D", B.SECOES["imagens"]["texto"])


# ======================================================================
class TestGodotV26(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = RAIZ / "body" / "zenith"
        cls.ui = (d / "ui_manager.gd").read_text(encoding="utf-8")
        cls.con = (d / "brain_connector.gd").read_text(encoding="utf-8")

    def test_sinais_e_mensagens_batem_com_o_python(self):
        py = (RAIZ / "brain" / "zenith_parar.py").read_text(encoding="utf-8") \
            + (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('"action": "atividade"', py)
        self.assertIn('"action": "mic_fase"', py)
        self.assertIn("signal atividade(estado, icone, texto, pode_parar)", self.con)
        self.assertIn("signal mic_fase(fase, texto)", self.con)
        self.assertIn('"atividade":', self.con)
        self.assertIn('"mic_fase":', self.con)
        self.assertIn("brain.atividade.connect(_on_atividade_ui)", self.ui)
        self.assertIn("brain.mic_fase.connect(_on_mic_fase_ui)", self.ui)

    def test_botao_parar_manda_o_comando_certo(self):
        self.assertIn('parar_btn = _make_button("⏹  Parar"', self.ui)
        self.assertIn('brain.send_to_brain({"action": "chat", "text": "/parar"})', self.ui)
        self.assertIn("func _on_atividade_ui(", self.ui)
        self.assertIn("func _on_mic_fase_ui(", self.ui)

    def test_estados_de_fase_do_mic_sao_os_que_o_python_manda(self):
        interacao = (RAIZ / "brain" / "zenith_interaction.py").read_text(encoding="utf-8")
        for fase in ("ouvindo", "captando", "transcrevendo"):
            self.assertIn(f'_fase("{fase}")', interacao)
            self.assertIn(f'"{fase}"', self.ui)
        head = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        for fase in ("enviado", "nada"):
            self.assertIn(f'"{fase}"', head)
            self.assertIn(f'"{fase}"', self.ui)

    def test_versao(self):
        from brain import zenith_version
        # v1.0: a numeração reiniciou (vMAJOR.MINOR), então a comparação é pela tupla.
        self.assertGreaterEqual(zenith_version.numero(), (1, 0, 0))   # sobe a cada entrega


if __name__ == "__main__":
    unittest.main()
