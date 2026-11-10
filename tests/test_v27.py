"""
Testes do v27 — correções do que o Anderson achou testando a v26 + transcrição ao vivo + imagem por IA + prévia de anexos.
Rodar: python -m unittest tests.test_v27 -v
NÃO provam: o Godot de verdade (prévia de anexo, cartões) nem o Google de verdade (geração de imagem usa um cliente de
mentira). Isso se vê abrindo o Zenith e mandando `/imagem um gato astronauta`.
"""
import glob
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import warnings
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_commands as cmd
from brain import zenith_imagem_ia as IA
from brain import zenith_matematica as M
from brain import zenith_parar as PA
from brain import zenith_stream as S
from brain import zenith_tags as T


class FakeSettings:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **d):
        self.d = dict(d)

    def get(self, chave, padrao=None):
        v = self.d.get(chave, padrao)
        return padrao if v is None else v


# ======================================================================
class TestAchadosDoTesteReal(unittest.TestCase):
    def test_nenhum_modulo_tem_escape_invalido(self):
        """O Python 3.14 do Anderson mostrou SyntaxWarning no zenith_biblia.py (barra invertida do LaTeX no texto)."""
        ruins = []
        for p in sorted(glob.glob(str(RAIZ / "brain" / "*.py")) + glob.glob(str(RAIZ / "*.py"))):
            with open(p, encoding="utf-8") as f:
                src = f.read()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                compile(src, p, "exec")
            ruins += [(os.path.basename(p), x.lineno) for x in w]
        self.assertEqual(ruins, [])

    def test_biblia_sem_caracteres_de_controle(self):
        """\\frac virava FORM FEED, \\nabla virava quebra de linha, \\vec virava VT, \\times virava TAB."""
        from brain import zenith_biblia as B
        for nome, sec in B.SECOES.items():
            ruins = [hex(ord(c)) for c in sec["texto"] if ord(c) < 32 and c != "\n"]
            self.assertEqual(ruins, [], f"seção {nome}")
        self.assertIn(r"\frac", B.SECOES["matematica"]["texto"])
        self.assertIn(r"\nabla", B.SECOES["matematica"]["texto"])
        md = (RAIZ / "BIBLIA_ZENITH.md").read_text(encoding="utf-8")
        self.assertEqual([c for c in md if ord(c) < 32 and c not in "\n\r\t"], [])

    def test_memoria_apaga_a_troca_cancelada(self):
        from brain import zenith_memory as ZM
        m = object.__new__(ZM.ZenithMemory)
        m.collection = mock.Mock()
        m._ultimo_resumo_ts = 0
        _id = m.save("Anderson", "Zenith", "explique Euler-Lagrange", "resposta longa")
        self.assertIsInstance(_id, str)
        self.assertTrue(m.apagar_id(_id))
        m.collection.delete.assert_called_once_with(ids=[_id])

    def test_core_desfaz_a_ultima_troca_quando_manda_parar(self):
        from brain.zenith_core import ZenithCore
        c = object.__new__(ZenithCore)
        c.memory = mock.Mock()
        c._ultima_troca_id = "abc"
        c.desfazer_ultima_troca()
        c.memory.apagar_id.assert_called_once_with("abc")
        self.assertIsNone(c._ultima_troca_id)
        c.desfazer_ultima_troca()                                  # 2ª vez: nada pra desfazer, não quebra
        c.memory.apagar_id.assert_called_once()

    def test_resposta_descartada_pelo_parar_some_da_memoria_tambem(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        msgs = []
        b.bridge = type("B", (), {"send": lambda s, m: msgs.append(m)})()
        b.settings = FakeSettings()
        b.core = mock.Mock()
        b.active_conv_id = "c"
        with mock.patch("brain.zenith_headless.pausa.ativo", lambda: False):
            g = PA.geracao()
            PA.solicitar("teste")
            b._deliver_result({"text": "resposta cancelada", "pending_action": None, "blocked": False}, None, g)
        b.core.desfazer_ultima_troca.assert_called_once()

    def test_primeira_mensagem_sem_ia_tenta_remontar_os_clientes(self):
        from brain.zenith_core import ZenithCore
        c = object.__new__(ZenithCore)
        c.settings = FakeSettings(gemini_key="AIza-x")
        self.assertTrue(c._ha_chaves_nas_configuracoes())
        c.settings = FakeSettings()
        self.assertFalse(c._ha_chaves_nas_configuracoes())
        src = (RAIZ / "brain" / "zenith_core.py").read_text(encoding="utf-8")
        self.assertIn("self.reload_api_keys(self.settings)", src)
        self.assertIn("remontando os clientes e tentando de novo", src)

    @mock.patch.dict("os.environ", {"ZENITH_EDICAO": "admin"})   # v1.4: na edição Pública o pedido de administrador nunca aparece
    def test_pergunta_do_admin_nao_grava_o_nao_para_sempre(self):
        from brain import zenith_admin as ADM
        self.assertIn("pergunta de novo na próxima vez", ADM.PERGUNTA)
        with tempfile.TemporaryDirectory() as d:
            ADM.marcar(d, ADM.MARCA_DISPENSADO)                    # marca antiga da v26 não cala mais a pergunta
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=False), "perguntar")
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=None), "nada")
            self.assertEqual(ADM.decidir(d, frozen=True, windows=True, admin=True), "marcar")

    def test_testes_de_godot_falso_pulam_no_windows(self):
        src = (RAIZ / "tests" / "test_vrm_import.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("@_SO_POSIX"), 4)
        self.assertIn('os.name == "nt"', src)


# ======================================================================
class TestMatematicaInline(unittest.TestCase):
    def test_colchetes_e_apostrofo_contam_como_matematica(self):
        self.assertEqual([t.latex for t in M.achar_trechos("**$S[q]$** é o funcional e $f'$ a derivada")], ["S[q]", "f'"])
        self.assertEqual(M.achar_trechos("Custa R$ 5 e R$10, ou US$ 3."), [])
        r = M.processar_resposta("* **$S[q]$** é o funcional", "/tmp/x", renderizar=lambda *a: True)
        self.assertNotIn("$", r.chat)
        self.assertIn("S[q]", r.chat)

    def test_equacao_aberta_no_meio_do_streaming(self):
        self.assertEqual(M.inicio_de_matematica_aberta("Veja $$ \\frac{a}{"), 5)
        self.assertEqual(M.inicio_de_matematica_aberta("Veja $x^"), 5)
        self.assertIsNone(M.inicio_de_matematica_aberta("Veja $x^2$ e $$a=b$$ pronto."))
        self.assertIsNone(M.inicio_de_matematica_aberta("Custa R$ 5 e R$10."))
        self.assertIsNone(M.inicio_de_matematica_aberta("Em código: ```$$a$$```"))

    def test_conversor_em_pedacos_e_igual_ao_conversor_do_texto_todo(self):
        textos = [
            "Oi! A energia é $E = mc^2$. E a integral:\n$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$\nFim, tá? Boa!",
            "Sem matemática nenhuma aqui. Custa R$ 5.",
            "Duas:\n$$a=b;\\ c=d$$ e depois $$x_1 < x_2$$ pronto. Mais uma frase.",
        ]
        for t in textos:
            inteiro = M.ConversorStream().converter(t)
            conv = M.ConversorStream()
            partes_chat, partes_fala = [], []
            # percorre o texto em pedaços de ~7 letras, estendendo o pedaço enquanto houver equação ABERTA
            pos = 0
            while pos < len(t):
                fim = pos + 7
                # (igual ao portão de verdade: espera enquanto a equação está aberta ou o pedaço termina num "$")
                while fim < len(t) and (M.inicio_de_matematica_aberta(t[pos:fim]) is not None or t[pos:fim].endswith("$")):
                    fim += 1
                c, _h, f = conv.converter(t[pos:fim])
                partes_chat.append(c)
                partes_fala.append(f)
                pos = fim
            esperado_chat = " ".join(inteiro[0].split())
            self.assertEqual(" ".join("".join(partes_chat).split()), esperado_chat, t)


class TestPortaoComMatematica(unittest.TestCase):
    def portao(self):
        saida = []
        p = S.Portao(lambda trecho, fala=None: saida.append((trecho, fala)), transformar=M.ConversorStream().converter)
        return p, saida

    def alimentar(self, p, texto, passo=5):
        for i in range(0, len(texto), passo):
            p.alimentar(texto[i:i + passo])

    def test_a_resposta_continua_fluindo_depois_da_primeira_equacao(self):
        p, saida = self.portao()
        self.alimentar(p, "Veja:\n$$\\frac{a}{b}=c$$\nDepois disso vem mais texto. E mais uma frase. E outra ainda. ")
        self.assertFalse(p.fechado)
        liberado = "".join(t for t, _ in saida)
        self.assertIn("[Equação 1 ↓]", liberado)
        self.assertIn("E mais uma frase.", liberado)             # antes (v26) o portão fechava na 1ª equação
        self.assertNotIn("$", liberado)
        self.assertNotIn("\\frac", liberado)

    def test_menor_que_dentro_de_equacao_nao_vira_etiqueta(self):
        p, saida = self.portao()
        self.alimentar(p, "Com $a < b$ e $$x_1 < x_2$$ ok. Segue a frase. Outra frase aqui. ")
        self.assertFalse(p.fechado, p.motivo)
        self.assertNotIn("$", "".join(t for t, _ in saida))

    def test_ponto_e_virgula_dentro_da_equacao_nao_corta_a_frase(self):
        p, saida = self.portao()
        self.alimentar(p, "Veja $$a=b;\\ c=d$$ pronto. Mais texto agora. Outra frase final. ")
        self.assertFalse(p.fechado)
        liberado = "".join(t for t, _ in saida)
        self.assertIn("a=b;", liberado)
        self.assertNotIn("$", liberado)

    def test_dinheiro_nao_trava_nada(self):
        p, saida = self.portao()
        self.alimentar(p, "Custa R$ 50 e sai por R$100. Beleza? Tudo certo. Mais uma. ")
        self.assertFalse(p.fechado)
        self.assertEqual("".join(t for t, _ in saida), "Custa R$ 50 e sai por R$100. Beleza? Tudo certo. Mais uma. ")

    def test_equacao_que_nunca_fecha_desiste_sem_travar_pra_sempre(self):
        p, saida = self.portao()
        self.alimentar(p, "Olha $$ " + "x " * 900)               # > 1500 letras sem fechar
        self.assertTrue(p.fechado)
        self.assertEqual(p.motivo, "matematica")

    def test_sem_conversor_o_comportamento_antigo_continua(self):
        saida = []
        p = S.Portao(saida.append)
        p.alimentar("Veja $x^2$ ok.")
        self.assertTrue(p.fechado)
        self.assertEqual(p.motivo, "matematica")

    def test_sessao_guarda_o_que_a_voz_recebeu(self):
        enviados, fala = [], []

        class F:
            def add(self, t): fala.append(t)
            def fim(self): fala.append("FIM")
        sessao = S.SessaoDeEntrega(enviados.append, criar_fala=lambda: F())
        sessao.ao_liberar("x² [Equação 1 ↓] ", "x ao quadrado ")
        self.assertEqual(sessao.liberado, "x² [Equação 1 ↓] ")
        self.assertEqual(sessao.liberado_fala, "x ao quadrado ")
        self.assertEqual(fala, ["x ao quadrado "])


class TestEntregaStreamingComMatematica(unittest.TestCase):
    def test_streaming_de_ponta_a_ponta_sem_duplicar_nem_vazar_latex(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        msgs, falas = [], []
        b.bridge = type("B", (), {"send": lambda s, m: msgs.append(m)})()
        b.settings = FakeSettings(voice_enabled=True, response_streaming=True, streaming_real=True, vida_gestos_ia=False)
        b.active_conv_id = "c1"

        class Fala:
            def add(f, t): falas.append(("add", t))
            def fim(f): falas.append(("fim",))
            def cancelar(f, silencioso=False): falas.append(("cancelar",))
        voz = type("V", (), {})()
        voz.falar_async = lambda t, **k: falas.append(("async", t))
        voz.pode_falar = lambda: True
        voz.falar_stream_iniciar = lambda **k: Fala()
        b.interaction = voz
        b._enviar_midias = lambda: None
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        b._pasta_matematica = lambda: Path(tmp.name)
        final = ("Claro! A equação de Euler–Lagrange é:\n$$\\frac{d}{dt}\\left(\\frac{\\partial L}{\\partial \\dot{q}}\\right)"
                 "=\\frac{\\partial L}{\\partial q};\\ 0.5$$\nEla diz que o sistema segue o caminho estacionário, com $S[q]$ e "
                 "$a < b$. Custa R$ 5. Depois:\n$$\\int_0^1 x^2\\,dx=\\frac13$$\nFim, tá? Boa!")
        with mock.patch("brain.zenith_headless.time.sleep", lambda s: None), \
                mock.patch("brain.zenith_headless.history.append_message", lambda *a, **k: None), \
                mock.patch("brain.zenith_headless.pausa.ativo", lambda: False):
            sessao = b._abrir_sessao_stream()
            portao = S.Portao(sessao.ao_liberar, transformar=M.ConversorStream().converter)
            for i in range(0, len(final), 5):
                portao.alimentar(final[i:i + 5])
            antes = len(sessao.liberado)
            b._deliver_result({"text": final, "pending_action": None, "blocked": False}, sessao)
        chat = "".join(m.get("delta", "") for m in msgs if m.get("action") == "chat_stream_chunk")
        self.assertFalse(portao.fechado)
        self.assertGreater(antes, len(final) * 0.6)                 # a maior parte JÁ tinha saído em streaming
        self.assertEqual(chat.count("Claro!"), 1)                    # nada duplicado
        for cru in ("$$", "\\frac", "$S", "$a"):
            self.assertNotIn(cru, chat)
        self.assertIn("[Equação 1 ↓]", chat)
        self.assertIn("[Equação 2 ↓]", chat)
        self.assertEqual([m["caption"] for m in msgs if m.get("action") == "chat_image"], ["Equação 1", "Equação 2"])
        self.assertFalse(any(f[0] == "cancelar" for f in falas))
        falado = " ".join(f[1] for f in falas if f[0] == "add")
        self.assertIn("derivada parcial", falado)
        self.assertIn("integral de 0 até 1", falado)
        self.assertNotIn("\\", falado)

    def test_imagem_que_falha_avisa_a_parte_e_o_texto_fica(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        msgs = []
        b.bridge = type("B", (), {"send": lambda s, m: msgs.append(m)})()
        b.settings = FakeSettings(voice_enabled=False, response_streaming=False, vida_gestos_ia=False)
        b.active_conv_id = "c1"
        b._enviar_midias = lambda: None
        b._pasta_matematica = lambda: Path(tempfile.gettempdir())
        original = M.processar_resposta
        sem_imagem = lambda texto, pasta, estilo=None, **k: original(texto, pasta, renderizar=lambda *a, **kw: False)
        with mock.patch.object(M, "processar_resposta", sem_imagem), \
                mock.patch("brain.zenith_headless.history.append_message", lambda *a, **k: None), \
                mock.patch("brain.zenith_headless.pausa.ativo", lambda: False), \
                mock.patch("brain.zenith_headless.time.sleep", lambda s: None):
            b._deliver_result({"text": "Veja:\n$$a^2+b^2=c^2$$\nFim.", "pending_action": None, "blocked": False})
        textos = " ".join(m.get("text", "") + m.get("delta", "") for m in msgs)
        self.assertIn("a²+b²=c²", textos)                          # o texto da equação continua no balão
        self.assertIn("Não consegui desenhar a imagem da equação 1", textos)


# ======================================================================
class FakeSeg:
    def __init__(self, t):
        self.text = t


class FakeModelo:
    def __init__(self):
        self.chamadas = []

    def transcribe(self, audio, **kw):
        time.sleep(0.03)
        self.chamadas.append((len(audio), kw.get("beam_size")))
        return iter([FakeSeg(f"fala até {len(audio) / 16000:.1f}s")]), None


class FakeStream:
    def __init__(self, samplerate, channels, dtype, blocksize, callback):
        self.cb, self.bs, self.run = callback, blocksize, False

    def __enter__(self):
        import numpy as np
        self.run = True

        def alimentar():
            for _ in range(22):
                if not self.run:
                    break
                self.cb(np.full((self.bs, 1), 0.2, dtype="float32"), self.bs, None, None)
                time.sleep(0.1)
        self.t = threading.Thread(target=alimentar)
        self.t.start()
        return self

    def __exit__(self, *a):
        self.run = False
        self.t.join()


class TestTranscricaoAoVivo(unittest.TestCase):
    def _interacao(self, **cfg):
        from brain import zenith_interaction as Z
        import numpy as np
        padrao = {"mic_mode": "manual", "mic_parcial_intervalo": 0.25, "whisper_beam": 1, "persona_name": "Zenith"}
        padrao.update(cfg)
        self.patches = [mock.patch.object(Z, "sd", types.SimpleNamespace(InputStream=FakeStream)),
                        mock.patch.object(Z, "np", np),
                        mock.patch.object(Z, "WhisperModel", lambda *a, **k: FakeModelo()),
                        # v29: _escutar_sync agora registra o volume medido em _log_voz, que grava em
                        # config/zenith_voz_debug.log — nos testes isso não deve sujar a pasta real.
                        mock.patch.object(Z, "_log_voz")]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        z = object.__new__(Z.ZenithInteraction)
        z.settings = FakeSettings(**padrao)
        z._stop_listening_flag = threading.Event()
        z._is_listening = True
        z._whisper_model = None
        z._whisper_lock_carga = threading.Lock()
        z._whisper_lock_uso = threading.Lock()
        return z

    def _rodar(self, z, com_parcial=True, segundos=1.6):
        fases, parciais, finais = [], [], []
        th = threading.Thread(target=z._escutar_sync, args=(finais.append, fases.append, parciais.append if com_parcial else None))
        th.start()
        time.sleep(segundos)
        z._stop_listening_flag.set()
        th.join(15)
        return fases, parciais, finais

    def test_mostra_o_texto_enquanto_fala_e_o_final_substitui(self):
        z = self._interacao()
        fases, parciais, finais = self._rodar(z)
        self.assertGreaterEqual(len(parciais), 1)                    # texto provisório apareceu ENQUANTO gravava
        self.assertEqual(len(finais), 1)
        self.assertTrue(finais[0].startswith("fala até"))
        self.assertIn("transcrevendo", fases)
        self.assertTrue(all(b == 1 for _, b in z._whisper_model.chamadas))   # beam 1 (rápido), não 5

    def test_desligado_nao_faz_parcial(self):
        z = self._interacao(mic_transcricao_ao_vivo=False)
        _fases, parciais, finais = self._rodar(z)
        self.assertEqual(parciais, [])
        self.assertEqual(len(finais), 1)

    def test_precarga_do_whisper_em_segundo_plano(self):
        from brain import zenith_interaction as Z
        z = self._interacao()
        self.assertTrue(z.precarregar_whisper())
        for _ in range(100):
            if z._whisper_model is not None:
                break
            time.sleep(0.02)
        self.assertIsNotNone(z._whisper_model)
        self.assertFalse(z.precarregar_whisper())                   # já carregado: não faz de novo

    def test_precarga_pode_ser_desligada(self):
        z = self._interacao(whisper_precarregar=False)
        self.assertFalse(z.precarregar_whisper())

    def test_headless_manda_o_parcial_como_mic_transcript(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        msgs = []
        b.bridge = type("B", (), {"send": lambda s, m: msgs.append(m)})()
        b._mic_parcial("olá akira")
        self.assertEqual(msgs[-1], {"action": "mic_transcript", "text": "olá akira", "parcial": True})
        b._mic_parcial("")
        self.assertEqual(len(msgs), 1)
        src = (RAIZ / "brain" / "zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn("on_parcial=self._mic_parcial", src)
        self.assertIn("self.interaction.precarregar_whisper()", src)


# ======================================================================
class UmInline:
    def __init__(self, d, m):
        self.data, self.mime_type = d, m


class UmaParte:
    def __init__(self, inline=None, text=None):
        self.inline_data, self.text = inline, text


class UmaResposta:
    def __init__(self, partes):
        self.candidates = [types.SimpleNamespace(content=types.SimpleNamespace(parts=partes))]
        self.prompt_feedback = None


class UmCliente:
    def __init__(self, resp=None, erro=None):
        self.chamadas = []
        cliente = self

        class Models:
            def generate_content(self, **kw):
                cliente.chamadas.append(kw)
                if erro:
                    raise erro
                return resp
        self.models = Models()


class Tipos:
    class GenerateContentConfig:
        def __init__(self, **kw):
            self.kw = kw

    class ImageConfig:
        def __init__(self, **kw):
            self.kw = kw


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


class TestImagemPorIA(unittest.TestCase):
    def test_gera_e_salva(self):
        with tempfile.TemporaryDirectory() as d:
            c = UmCliente(resp=UmaResposta([UmaParte(text="Aqui."), UmaParte(inline=UmInline(PNG, "image/png"))]))
            r = IA.gerar("um gato astronauta", "chave", d, cliente=c, tipos=Tipos, proporcao="16:9", agora=0)
            self.assertTrue(Path(r["caminho"]).exists())
            self.assertEqual(Path(r["caminho"]).read_bytes()[:4], b"\x89PNG")
            self.assertEqual(Path(r["caminho"]).parent.name, "imagens")
            self.assertEqual(r["modelo"], "gemini-2.5-flash-image")
            self.assertEqual(r["texto"], "Aqui.")
            self.assertEqual(c.chamadas[0]["config"].kw["image_config"].kw, {"aspect_ratio": "16:9"})

    def test_sdk_antigo_sem_image_config_cai_pra_chamada_simples(self):
        class TiposAntigos:
            class GenerateContentConfig:
                def __init__(self, **kw):
                    if "image_config" in kw:
                        raise TypeError("campo desconhecido")
                    self.kw = kw
            ImageConfig = Tipos.ImageConfig
        with tempfile.TemporaryDirectory() as d:
            c = UmCliente(resp=UmaResposta([UmaParte(inline=UmInline(PNG, "image/png"))]))
            IA.gerar("x y z", "k", d, cliente=c, tipos=TiposAntigos)
            self.assertEqual(len(c.chamadas), 1)
            self.assertEqual(c.chamadas[0]["config"].kw, {"response_modalities": ["IMAGE"]})

    def test_erros_viram_mensagens_em_portugues(self):
        casos = {"429 RESOURCE_EXHAUSTED quota": "COTA", "403 PERMISSION_DENIED billing": "PLANO PAGO",
                 "404 model not found": "modelo de imagem não foi encontrado", "400 API key not valid": "chave do Gemini",
                 "getaddrinfo failed": "Sem conexão", "finish SAFETY blocked": "segurança"}
        with tempfile.TemporaryDirectory() as d:
            for erro, trecho in casos.items():
                with self.assertRaises(IA.ErroImagem) as cm:
                    IA.gerar("algo", "k", d, cliente=UmCliente(erro=Exception(erro)), tipos=Tipos)
                self.assertIn(trecho, str(cm.exception), erro)

    def test_sem_imagem_na_resposta_e_pedido_vazio_e_sem_chave(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(IA.ErroImagem) as cm:
                IA.gerar("algo", "k", d, cliente=UmCliente(resp=UmaResposta([UmaParte(text="não posso")])), tipos=Tipos)
            self.assertIn("não devolveu imagem", str(cm.exception))
            with self.assertRaises(IA.ErroImagem):
                IA.gerar("   ", "k", d, cliente=UmCliente(), tipos=Tipos)
            with self.assertRaises(IA.ErroImagem) as cm:
                IA.gerar("algo", "", d)
            self.assertIn("chave do Gemini", str(cm.exception))

    def test_pedido_interpreta_opcoes_do_comeco(self):
        self.assertEqual(IA.interpretar_pedido("pro 16:9 um castelo"), {"qualidade": "pro", "proporcao": "16:9", "descricao": "um castelo"})
        self.assertEqual(IA.interpretar_pedido("um gato 16:9")["descricao"], "um gato 16:9")     # só o COMEÇO vale
        self.assertEqual(IA.modelo_para("pro"), "gemini-3-pro-image-preview")
        self.assertEqual(IA.modelo_para("padrao", FakeSettings(imagem_ia_modelo="outro-modelo")), "outro-modelo")

    def test_comando_imagem(self):
        self.assertIn("Use assim", cmd.tratar("/imagem")["resposta"])
        c = cmd.tratar("/imagem pro um dragão")
        self.assertEqual((c["acao"], c["args"]), ("imagem_ia", {"texto": "pro um dragão"}))
        self.assertIn("/imagem", cmd.tratar("/ajuda")["resposta"])

    def test_acao_gerar_imagem_e_registrada_em_todo_lugar(self):
        from brain import zenith_conhecimento as K
        from brain.zenith_core import ACTION_TAGS
        import re
        self.assertTrue(re.search(ACTION_TAGS["image_gen"], "<gerar_imagem>um gato</gerar_imagem>"))
        self.assertIn("gerar_imagem", T.TAGS_INTERNAS)
        self.assertIn("gerar_imagem", K._TAGS_ACAO)
        self.assertEqual(T.limpar_visivel("<gerar_imagem>um gato</gerar_imagem>Pronto"), "Pronto")
        self.assertEqual(PA.estado_da_acao("image_gen")[0], "desenhando")
        from brain.zenith_executor import ZenithExecutor
        pend = ZenithExecutor().create_pending("image_gen", "um gato astronauta")
        self.assertIn("GERAR IMAGEM POR IA", pend.preview())
        self.assertIn("pode ter custo", pend.preview().lower())

    def test_core_executa_a_acao_aprovada_e_mostra_no_chat(self):
        from brain.zenith_core import ZenithCore
        from brain.zenith_executor import ZenithExecutor
        c = object.__new__(ZenithCore)
        c.settings = FakeSettings(gemini_key="k")
        c._midias = []
        with tempfile.TemporaryDirectory() as d:
            falso = {"caminho": str(Path(d) / "ia.png"), "modelo": "gemini-2.5-flash-image", "texto": ""}
            with mock.patch("brain.zenith_core.CREATION_DIR", d), mock.patch.object(IA, "gerar", return_value=falso) as g:
                txt = c._gerar_imagem_ia("pro 9:16 um dragão")
            self.assertIn("Criei a imagem", txt)
            self.assertEqual(g.call_args.kwargs["modelo"], "gemini-3-pro-image-preview")
            self.assertEqual(g.call_args.kwargs["proporcao"], "9:16")
            self.assertEqual(c._midias[-1]["path"], falso["caminho"])
            with mock.patch("brain.zenith_core.CREATION_DIR", d), mock.patch.object(IA, "gerar", side_effect=IA.ErroImagem("🎨 cota")):
                self.assertIn("versão simples por código", c._gerar_imagem_ia("um dragão"))

    def test_comando_imagem_manda_texto_e_cartao_e_respeita_parar(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        msgs = []
        b.bridge = type("B", (), {"send": lambda s, m: msgs.append(m)})()
        b.settings = FakeSettings(gemini_key="k")
        falso = {"caminho": "/tmp/ia.png", "modelo": "gemini-2.5-flash-image", "texto": ""}
        with mock.patch.object(IA, "gerar", return_value=falso):
            b._rodar_imagem_ia({"texto": "um gato"})
        acoes = [m.get("action") for m in msgs]
        self.assertIn("chat_message", acoes)
        self.assertIn("chat_image", acoes)
        self.assertEqual([m["estado"] for m in msgs if m.get("action") == "atividade"], ["desenhando", "ocioso"])
        msgs.clear()

        def gerar_e_parar(*a, **k):
            PA.solicitar("teste")                                    # você clicou ⏹ enquanto o Google trabalhava
            return falso
        with mock.patch.object(IA, "gerar", side_effect=gerar_e_parar):
            b._atividade_atual = ("ocioso", "")
            b._rodar_imagem_ia({"texto": "um gato"})
        self.assertNotIn("chat_image", [m.get("action") for m in msgs])

    def test_biblia_ensina_quando_usar_cada_tipo_de_imagem(self):
        from brain import zenith_biblia as B
        t = B.SECOES["imagens"]["texto"]
        self.assertIn("<gerar_imagem>", t)
        self.assertIn("SEMPRE pede a aprovação", t)
        self.assertNotIn("não há gerador de imagem por IA", t)
        self.assertNotIn("que ainda não está ligado", t)


# ======================================================================
class TestComandosFalam(unittest.TestCase):
    def test_resultados_trazem_fala_em_portugues(self):
        from brain import zenith_formulas as FM
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("integral de 0 até 1", FM.executar({"tipo": "latex", "texto": r"\int_0^1 x^2\,dx"}, d)["fala"])
            f = FM.executar({"tipo": "formula", "assunto": "optica", "pagina": 1}, d)["fala"]
            self.assertIn("Óptica", f)
            self.assertIn("Lei de Snell", f)

    def test_headless_fala_o_resultado_do_comando(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        b = object.__new__(ZenithHeadlessBrain)
        msgs, falas = [], []
        b.bridge = type("B", (), {"send": lambda s, m: msgs.append(m)})()
        b.settings = FakeSettings(voice_enabled=True)
        voz = type("V", (), {})()
        voz.pode_falar = lambda: True
        voz.falar_async = lambda t, **k: falas.append(t)
        b.interaction = voz
        b._pasta_matematica = lambda: Path(tempfile.gettempdir())
        b._rodar_matematica({"tipo": "latex", "texto": r"x^2 + y^2 = z^2"})
        self.assertEqual(len(falas), 1)
        self.assertIn("x ao quadrado mais y ao quadrado igual a z ao quadrado", falas[0])
        b.settings = FakeSettings(voice_enabled=True, comandos_falam=False)
        b._rodar_matematica({"tipo": "latex", "texto": r"x^2"})
        self.assertEqual(len(falas), 1)                              # desligado: fica mudo como antes


# ======================================================================
class TestGodotV27(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = (RAIZ / "body" / "zenith" / "ui_manager.gd").read_text(encoding="utf-8")

    def test_previa_de_anexo(self):
        self.assertIn("func _mostrar_previa_do_anexo(", self.ui)
        # v1.0.1: o seletor virou VÁRIOS arquivos e passa por _adicionar_anexo (que mostra a prévia de cada um).
        self.assertIn("_adicionar_anexo(str(p))", self.ui)                            # seletor de arquivo
        self.assertIn("_mostrar_previa_do_anexo(caminho, rotulo)", self.ui)            # a prévia acontece ao adicionar
        self.assertIn('_adicionar_anexo(caminho, "imagem colada")', self.ui)           # print colado
        self.assertIn('_adicionar_anexo(caminho_t, "texto colado")', self.ui)          # texto longo colado
        self.assertIn("ImageTexture.create_from_image(img)", self.ui)
        self.assertIn("_attachment_snippet", self.ui)

    def test_texto_curto_continua_colando_normal(self):
        self.assertIn("COLADO_LIMITE_CARACTERES := 1500", self.ui)
        self.assertIn("colado.length() > COLADO_LIMITE_CARACTERES or colado.count(\"\\n\") > COLADO_LIMITE_LINHAS", self.ui)

    def test_imagem_enviada_aparece_na_conversa_como_voce(self):
        # v1.0.1: a lista de anexos é percorrida — cada imagem enviada aparece na conversa como "Você".
        self.assertIn('_on_chat_image(cam, cam.get_file(), "Você")', self.ui)
        self.assertIn("func _on_chat_image(path: String, caption: String, autor: String = \"\"):", self.ui)

    def test_versao(self):
        from brain import zenith_version
        self.assertGreaterEqual(zenith_version.numero(), (1, 0, 0))   # v1.0 em diante também vale


if __name__ == "__main__":
    unittest.main()
