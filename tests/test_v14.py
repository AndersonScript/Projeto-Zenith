"""
Testes automáticos do Cérebro (v14). Rodam SEM Godot, SEM internet, SEM
áudio e SEM chave de API — tudo que toca o mundo de fora é simulado.

    python -m unittest tests.test_v14 -v        (na pasta raiz do projeto)

Rode depois de qualquer mudança no Python: se algo quebrou, aparece aqui
antes de você abrir o programa.
"""
import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brain import zenith_actionlog as alog
from brain import zenith_notes as notes
from brain import zenith_commands as cmds
from brain import zenith_notify as notify


class ActionLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name) / "log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_registra_e_le(self):
        self.assertTrue(alog.registrar("python", "Fazer um gráfico", "aprovada", "ok", "c1", caminho=self.p))
        self.assertTrue(alog.registrar("terminal", "Apagar tudo", "negada", caminho=self.p))
        ev = alog.recentes(10, self.p)
        self.assertEqual([e["decisao"] for e in ev], ["aprovada", "negada"])
        self.assertIn("ts", ev[0])

    def test_mascara_segredos(self):
        alog.registrar("python", "usa a chave sk-abcdefghijklmnopqrstuvwx", "aprovada",
                       'api_key = "AIzaSyA1234567890abcdefghijklmnop"; password: hunter2', caminho=self.p)
        bruto = self.p.read_text(encoding="utf-8")
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", bruto)
        self.assertNotIn("AIzaSyA1234567890abcdefghijklmnop", bruto)
        self.assertNotIn("hunter2", bruto)

    def test_trunca_texto_longo(self):
        alog.registrar("python", "x" * 5000, "aprovada", "y" * 5000, caminho=self.p)
        e = alog.recentes(1, self.p)[0]
        self.assertLessEqual(len(e["descricao"]), 200)
        self.assertLessEqual(len(e["detalhe"]), 400)

    def test_linha_corrompida_nao_derruba(self):
        alog.registrar("python", "a", "aprovada", caminho=self.p)
        with open(self.p, "a", encoding="utf-8") as f:
            f.write("{isso nao e json\n\n")
        alog.registrar("python", "b", "aprovada", caminho=self.p)
        self.assertEqual(len(alog.recentes(10, self.p)), 2)

    def test_nunca_levanta(self):
        # caminho impossível (um arquivo no lugar de pasta)
        arq = Path(self.tmp.name) / "arquivo"
        arq.write_text("x")
        self.assertFalse(alog.registrar("python", "a", "aprovada", caminho=arq / "sub" / "log.jsonl"))

    def test_rotacao(self):
        with mock.patch.object(alog, "_MAX_BYTES", 300):
            for i in range(20):
                alog.registrar("python", f"acao {i}", "aprovada", caminho=self.p)
        self.assertTrue(self.p.with_name("log.1.jsonl").exists())
        self.assertLess(self.p.stat().st_size, 2000)

    def test_formatar_vazio_e_cheio(self):
        self.assertIn("Ainda não há", alog.formatar_recentes(5, self.p))
        alog.registrar("python", "Fazer gráfico", "aprovada", caminho=self.p)
        alog.registrar("python", "Coisa perigosa", "vetada", "bloqueado", caminho=self.p)
        txt = alog.formatar_recentes(5, self.p)
        self.assertIn("Fazer gráfico", txt)
        self.assertIn("⛔", txt)

    def test_exportar_markdown(self):
        alog.registrar("python", "Fazer gráfico", "aprovada", caminho=self.p)
        dest = Path(self.tmp.name) / "out" / "log.md"
        self.assertEqual(alog.exportar_markdown(dest, self.p), 1)
        self.assertIn("Fazer gráfico", dest.read_text(encoding="utf-8"))


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name) / "notas.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_adicionar_listar_exportar(self):
        self.assertTrue(notes.adicionar("temperatura 23.4 C", caminho=self.p))
        self.assertTrue(notes.adicionar("amostra 2 turva", origem="voz", caminho=self.p))
        self.assertFalse(notes.adicionar("   ", caminho=self.p))
        self.assertEqual(len(notes.listar(10, self.p)), 2)
        self.assertIn("🎙️", notes.formatar(10, self.p))
        dest = Path(self.tmp.name) / "n.md"
        self.assertEqual(notes.exportar_markdown(dest, self.p), 2)
        self.assertIn("amostra 2 turva", dest.read_text(encoding="utf-8"))

    def test_vazio(self):
        self.assertIn("Nenhuma nota", notes.formatar(5, self.p))


class FakeSettings:
    def __init__(self, **kw):
        self.d = dict(kw)

    def get(self, k, default=None):
        return self.d.get(k, default)

    def update(self, ch):
        self.d.update(ch)


class CommandTests(unittest.TestCase):
    def test_nao_comando_passa(self):
        self.assertIsNone(cmds.tratar("oi tudo bem?"))
        self.assertIsNone(cmds.tratar("/home/usuario/arquivo.txt"))
        # v1.0 (A5): UMA palavra começando com "/" que não existe NUNCA vai para a IA — antes a IA
        # inventava um "visualizador 3D" para /vi e coisas do tipo. Agora volta uma sugestão.
        r = cmds.tratar("/comandoquenaoexiste")
        self.assertIsNotNone(r)
        self.assertIn("Não existe", r["resposta"])
        self.assertIsNone(cmds.tratar("/algo com argumentos"))   # frase com espaço continua conversa
        self.assertIsNone(cmds.tratar(""))

    def test_ajuda_e_versao(self):
        self.assertIn("/log", cmds.tratar("/ajuda")["resposta"])
        self.assertIn("v14", cmds.tratar("/versao", {"versao": "Zenith v14"})["resposta"])

    def test_nota_e_acoes(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "n.jsonl"
            with mock.patch.object(notes, "_caminho_padrao", return_value=p):
                self.assertIn("Anotado", cmds.tratar("/nota medi 5 ml")["resposta"])
                self.assertIn("Use assim", cmds.tratar("/nota")["resposta"])
                self.assertIn("medi 5 ml", cmds.tratar("/notas")["resposta"])
        self.assertEqual(cmds.tratar("/nota_voz")["acao"], "nota_voz")
        self.assertEqual(cmds.tratar("/testar_voz")["acao"], "test_voice")

    def test_log_via_comando(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "l.jsonl"
            with mock.patch.object(alog, "_caminho_padrao", return_value=p):
                alog.registrar("python", "Fazer gráfico", "aprovada")
                self.assertIn("Fazer gráfico", cmds.tratar("/log 3")["resposta"])

    def test_voz_emocao_alterna(self):
        cfg = FakeSettings(voice_expression_modulation=True)
        self.assertIn("DESLIGADA", cmds.tratar("/voz_emocao", {"settings": cfg})["resposta"])
        self.assertFalse(cfg.get("voice_expression_modulation"))
        self.assertIn("LIGADA", cmds.tratar("/voz_emocao", {"settings": cfg})["resposta"])

    def test_exportar_vai_pra_pasta(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(cmds, "_pasta_exportacao", return_value=Path(t)), \
                 mock.patch.object(alog, "_caminho_padrao", return_value=Path(t) / "l.jsonl"), \
                 mock.patch.object(notes, "_caminho_padrao", return_value=Path(t) / "n.jsonl"):
                alog.registrar("python", "x", "aprovada")
                notes.adicionar("y")
                self.assertIn("exportados", cmds.tratar("/exportar_log")["resposta"])
                self.assertIn("exportadas", cmds.tratar("/exportar_notas")["resposta"])
                self.assertEqual(len(list(Path(t).glob("*.md"))), 2)


class NotifyTests(unittest.TestCase):
    def test_sem_plyer_devolve_false(self):
        with mock.patch.dict(sys.modules, {"plyer": None}):
            self.assertFalse(notify.notificar("t", "m"))

    def test_com_plyer_chama(self):
        fake = types.ModuleType("plyer")
        fake.notification = mock.Mock()
        with mock.patch.dict(sys.modules, {"plyer": fake}):
            self.assertTrue(notify.notificar("Zenith terminou", "gráfico pronto"))
        kwargs = fake.notification.notify.call_args.kwargs
        self.assertEqual(kwargs["title"], "Zenith terminou")
        self.assertEqual(kwargs["app_name"], "Zenith")

    def test_plyer_quebrado_nao_levanta(self):
        fake = types.ModuleType("plyer")
        fake.notification = mock.Mock()
        fake.notification.notify.side_effect = RuntimeError("sem backend")
        with mock.patch.dict(sys.modules, {"plyer": fake}):
            self.assertFalse(notify.notificar("t", "m"))


def _importar_interaction():
    # Simula as libs pesadas ausentes — o módulo precisa importar mesmo assim.
    from brain import zenith_interaction as zi
    return zi


class VoiceModulationTests(unittest.TestCase):
    def setUp(self):
        self.zi = _importar_interaction()

    def test_parametros_formato_edge_tts(self):
        import re
        for expr in ("happy", "sad", "surprised", "thinking", "angry", "neutral", "desconhecida", None, ""):
            for k in (0.0, 0.5, 1.0, 2.0, 99, -3, "abc", None):
                rate, pitch = self.zi.parametros_de_voz(expr, k)
                self.assertRegex(rate, r"^[+-]\d+%$")
                self.assertRegex(pitch, r"^[+-]\d+Hz$")

    def test_valores(self):
        self.assertEqual(self.zi.parametros_de_voz("happy", 1.0), ("+8%", "+6Hz"))
        self.assertEqual(self.zi.parametros_de_voz("sad", 1.0), ("-10%", "-8Hz"))
        self.assertEqual(self.zi.parametros_de_voz("neutral", 1.0), ("+0%", "+0Hz"))
        self.assertEqual(self.zi.parametros_de_voz("happy", 0.0), ("+0%", "+0Hz"))
        self.assertEqual(self.zi.parametros_de_voz("happy", 2.0), ("+16%", "+12Hz"))
        self.assertEqual(self.zi.parametros_de_voz("qualquer", 1.0), ("+0%", "+0Hz"))

    def _rodar(self, settings, expressao, communicate_cls):
        fake_edge = types.SimpleNamespace(Communicate=communicate_cls)
        obj = self.zi.ZenithInteraction.__new__(self.zi.ZenithInteraction)
        obj.settings = settings
        obj.voice = "pt-BR-FranciscaNeural"
        obj._ready = False
        obj.ultimo_motor_voz = "-"
        obj.ultimo_status_rvc = "-"
        with mock.patch.object(self.zi, "edge_tts", fake_edge), mock.patch.object(self.zi, "requests", None), \
                mock.patch.object(self.zi, "_log_voz"):   # não escrever no config/ de verdade
            asyncio.run(obj._gerar_audio_base("oi", "x.mp3", expressao=expressao))
        return obj

    def test_edge_recebe_rate_e_pitch(self):
        chamadas = []

        class Fake:
            def __init__(self, texto, voz, **kw):
                chamadas.append(kw)

            async def save(self, p):
                pass

        obj = self._rodar(FakeSettings(voice_expression_modulation=True), "happy", Fake)
        self.assertEqual(chamadas, [{"rate": "+8%", "pitch": "+6Hz"}])
        self.assertIn("Edge-TTS", obj.ultimo_motor_voz)

    def test_desligado_ou_neutro_nao_modula(self):
        chamadas = []

        class Fake:
            def __init__(self, texto, voz, **kw):
                chamadas.append(kw)

            async def save(self, p):
                pass

        self._rodar(FakeSettings(voice_expression_modulation=False), "happy", Fake)
        self._rodar(FakeSettings(voice_expression_modulation=True), "neutral", Fake)
        self.assertEqual(chamadas, [{}, {}])

    def test_fallback_se_formato_recusado(self):
        chamadas = []

        class Fake:
            def __init__(self, texto, voz, **kw):
                if kw:
                    raise ValueError("formato invalido")
                chamadas.append("plain")

            async def save(self, p):
                pass

        self._rodar(FakeSettings(voice_expression_modulation=True), "sad", Fake)
        self.assertEqual(chamadas, ["plain"])   # caiu pra voz normal em vez de quebrar

    def test_diagnostico(self):
        obj = self.zi.ZenithInteraction.__new__(self.zi.ZenithInteraction)
        obj.settings = FakeSettings(rvc_model_path="C:/m.pth")
        obj._ready = True
        obj.ultimo_motor_voz = "Edge-TTS (x)"
        obj.ultimo_status_rvc = "desligado"
        txt = obj.diagnostico_voz()
        for trecho in ("Edge-TTS", "RVC", "C:/m.pth", "Variação por emoção"):
            self.assertIn(trecho, txt)


def _importar_headless_com_stubs():
    """Importa brain.zenith_headless mesmo sem as libs de nuvem/GUI
    instaladas (google-genai, openai, websockets, chromadb...), trocando
    só as que faltarem por dublês vazios. Numa instalação completa do
    Zenith nada disso é necessário — usa as libs de verdade."""
    ultimo = None
    for _ in range(25):
        try:
            from brain import zenith_headless as zh
            return zh
        except ImportError as e:
            ultimo = e
            nome = getattr(e, "name", None)
            if not nome or nome.startswith("brain"):
                break
            sys.modules[nome] = mock.MagicMock()
            for pai in [".".join(nome.split(".")[:i]) for i in range(1, nome.count(".") + 1)]:
                sys.modules.setdefault(pai, mock.MagicMock())
    raise ImportError(f"não consegui importar zenith_headless nem com dublês: {ultimo}")


class HeadlessIntegrationTests(unittest.TestCase):
    """Monta o Cérebro SEM rede/áudio/Godot (tudo simulado) e exercita os
    caminhos novos: comando, aprovação → log → aviso de fim de cadeia."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.logp = Path(self.tmp.name) / "log.jsonl"
        zh = _importar_headless_com_stubs()
        self.zh = zh
        b = zh.ZenithHeadlessBrain.__new__(zh.ZenithHeadlessBrain)
        b.settings = FakeSettings(notify_on_chain_end=True, multi_step_actions=True, voice_enabled=False)
        b.active_conv_id = "c1"
        b._pending_approvals = {}
        b._pending_mic_approvals = set()
        b._mic_aprovado_nesta_sessao = False
        b._proxima_fala_vira_nota = False
        b.sent = []
        b.bridge = types.SimpleNamespace(send=lambda d: b.sent.append(d))
        b.proactive = types.SimpleNamespace(marcar_atividade=lambda: None)
        b.interaction = mock.Mock()
        b.core = mock.Mock()
        self.b = b

    def tearDown(self):
        self.tmp.cleanup()

    def test_comando_nao_vai_pra_ia(self):
        with mock.patch.object(self.zh.history, "append_message") as ap:
            self.b._handle_chat({"text": "/ajuda"})
        self.b.core.pensar.assert_not_called()
        ap.assert_not_called()
        self.assertIn("Comandos", self.b.sent[-1]["text"])

    def test_nota_voz_liga_flag(self):
        self.b._handle_chat({"text": "/nota_voz"})
        self.assertTrue(self.b._proxima_fala_vira_nota)

    def test_aprovacao_grava_log_e_avisa_fim_de_cadeia(self):
        pend = types.SimpleNamespace(kind="python", description="Fazer gráfico", chain_original="pedido", chain_step=0)
        self.b._pending_approvals["r1"] = pend
        self.b.core.approve_action.return_value = "Gráfico salvo em X\nlinha 2"
        self.b.core.continuar_cadeia.return_value = {"text": "Pronto, o gráfico está feito.", "pending_action": None}
        with mock.patch.object(alog, "_caminho_padrao", return_value=self.logp), \
             mock.patch.object(self.zh.history, "append_message"):
            self.b._handle_approval_response({"request_id": "r1", "approved": True})
        ev = alog.recentes(5, self.logp)
        self.assertEqual(ev[-1]["decisao"], "aprovada")
        self.assertEqual(ev[-1]["detalhe"], "Gráfico salvo em X")
        avisos = [m for m in self.b.sent if m.get("action") == "notify"]
        self.assertEqual(len(avisos), 1)
        self.assertIn("gráfico", avisos[0]["body"])

    def test_cadeia_com_proxima_acao_nao_avisa(self):
        pend = types.SimpleNamespace(kind="python", description="Passo 1", chain_original="p", chain_step=0)
        prox = types.SimpleNamespace(kind="python", description="Passo 2", content="print(1)",
                                     chain_original="p", chain_step=1, preview=lambda: "prev")
        self.b._pending_approvals["r1"] = pend
        self.b.core.approve_action.return_value = "ok"
        self.b.core.continuar_cadeia.return_value = {"text": "", "pending_action": prox}
        with mock.patch.object(alog, "_caminho_padrao", return_value=self.logp), \
             mock.patch.object(self.zh.history, "append_message"):
            self.b._handle_approval_response({"request_id": "r1", "approved": True})
        self.assertFalse([m for m in self.b.sent if m.get("action") == "notify"])

    def test_negada_e_microfone_no_log(self):
        pend = types.SimpleNamespace(kind="terminal", description="rm -rf", chain_original="", chain_step=0)
        self.b._pending_approvals["r2"] = pend
        self.b._pending_mic_approvals.add("r3")
        with mock.patch.object(alog, "_caminho_padrao", return_value=self.logp), \
             mock.patch.object(self.zh.history, "append_message"), \
             mock.patch.object(self.b, "_start_listening"):
            self.b._handle_approval_response({"request_id": "r2", "approved": False})
            self.b._handle_approval_response({"request_id": "r3", "approved": True})
        dec = [(e["tipo"], e["decisao"]) for e in alog.recentes(5, self.logp)]
        self.assertEqual(dec, [("terminal", "negada"), ("microfone", "aprovada")])

    def test_notificacao_desligada(self):
        self.b.settings.update({"notify_on_chain_end": False})
        self.b._avisar_fim_de_cadeia(types.SimpleNamespace(description="x"), "texto")
        self.assertFalse(self.b.sent)

    def test_testar_voz_com_voz_desligada(self):
        self.b._handle_test_voice({})
        self.assertIn("desligada", self.b.sent[-1]["text"])
        self.b.interaction.falar_async.assert_not_called()

    def test_testar_voz_fala_e_diagnostica(self):
        self.b.settings.update({"voice_enabled": True})
        self.b.interaction.diagnostico_voz.return_value = "• Áudio: OK"

        def falso_falar(texto, on_start=None, on_end=None, expressao="neutral"):
            on_start(); on_end()
        self.b.interaction.falar_async.side_effect = falso_falar
        self.b._handle_test_voice({})
        self.assertIn("Diagnóstico da voz", self.b.sent[-1]["text"])
        self.assertEqual(self.b.interaction.falar_async.call_args.kwargs["expressao"], "happy")

    def test_toast_chama_notificacao(self):
        with mock.patch.object(self.zh.notify, "notificar") as n:
            self.b._handle_toast({"title": "Zenith terminou", "body": "ok"})
        n.assert_called_once_with("Zenith terminou", "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
