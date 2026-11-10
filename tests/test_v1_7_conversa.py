"""v1.7 — conversa por voz sem apertar nada (/conversa). Sem microfone, sem áudio, sem Godot: tudo falso."""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                          # noqa: E402
_stubs.instalar()
from brain import zenith_conversa_loop as CV      # noqa: E402


def _loop(pode=True):
    ev = {"mic": 0, "estados": [], "agendados": []}
    c = CV.ConversaContinua(abrir_microfone=lambda: ev.__setitem__("mic", ev["mic"] + 1), avisar=ev["estados"].append,
                            pode_abrir=lambda: pode() if callable(pode) else pode,
                            agendar=lambda fn, atraso: ev["agendados"].append((fn, atraso)))
    return c, ev


class MaquinaDeEstadosTests(unittest.TestCase):
    def test_ligar_abre_o_microfone_e_avisa(self):
        c, ev = _loop()
        msg = c.ligar()
        self.assertTrue(c.ligada)
        self.assertEqual((ev["mic"], ev["estados"]), (1, ["ouvindo"]))
        self.assertIn("/conversa desligar", msg)
        self.assertIn("já está ligada", c.ligar())
        self.assertEqual(ev["mic"], 1)                                     # ligar duas vezes não abre dois microfones

    def test_ciclo_completo_ouve_envia_responde_e_volta_a_ouvir(self):
        c, ev = _loop()
        c.ligar()
        self.assertEqual(c.ao_transcrever("oi, tudo bem?"), "enviar")
        self.assertEqual(ev["estados"][-1], "pensando")
        self.assertEqual(ev["agendados"], [])                              # enquanto ela pensa/fala, o microfone fica fechado
        c.ao_ficar_ocioso()                                                # terminou de responder
        self.assertEqual(len(ev["agendados"]), 1)
        self.assertGreaterEqual(ev["agendados"][0][1], 0.5)                # respiro antes de reabrir (eco da voz dela)
        ev["agendados"][0][0]()
        self.assertEqual((ev["mic"], ev["estados"][-1]), (2, "ouvindo"))

    def test_ocioso_sem_ter_enviado_nada_nao_reabre(self):
        c, ev = _loop()
        c.ligar()
        c.ao_ficar_ocioso()                                                # ex.: respondeu a algo digitado
        self.assertEqual(ev["agendados"], [])

    def test_nao_reabre_enquanto_ela_ainda_fala(self):
        falando = {"v": True}
        c, ev = _loop(pode=lambda: not falando["v"])
        c.ligar()
        c.ao_transcrever("oi")
        c.ao_ficar_ocioso()
        ev["agendados"].pop()[0]()                                         # tenta reabrir: ela ainda fala
        self.assertEqual(ev["mic"], 1)
        self.assertEqual(len(ev["agendados"]), 1)                          # reagendou
        falando["v"] = False
        ev["agendados"].pop()[0]()
        self.assertEqual(ev["mic"], 2)

    def test_silencio_repetido_desliga_sozinha(self):
        c, ev = _loop()
        c.ligar()
        self.assertEqual(c.ao_transcrever(""), "vazio")
        self.assertEqual(c.ao_transcrever("   "), "vazio")
        self.assertEqual(c.ao_transcrever(""), "desligou")
        self.assertFalse(c.ligada)
        self.assertEqual(ev["estados"][-1], "desligado")

    def test_falar_no_meio_zera_a_contagem_de_silencios(self):
        c, ev = _loop()
        c.ligar()
        c.ao_transcrever("")
        c.ao_transcrever("")
        self.assertEqual(c.ao_transcrever("ei"), "enviar")
        self.assertEqual(c.ao_transcrever(""), "vazio")                    # recomeçou a contar

    def test_desligar_para_tudo(self):
        c, ev = _loop()
        c.ligar()
        c.ao_transcrever("oi")
        self.assertIn("desligada", c.desligar("você pediu"))
        c.ao_ficar_ocioso()
        self.assertEqual(ev["agendados"], [])
        self.assertEqual(c.ao_transcrever("oi"), "ignorar")                # desligada: fluxo normal da caixa de texto
        c2, _ = _loop()
        ev["agendados"].clear()
        self.assertIn("já estava desligada", c2.desligar())

    def test_reabrir_depois_de_desligar_nao_abre_microfone(self):
        c, ev = _loop()
        c.ligar()
        c.ao_transcrever("oi")
        c.ao_ficar_ocioso()
        c.desligar()
        ev["agendados"].pop()[0]()                                         # o timer disparou depois do /parar
        self.assertEqual(ev["mic"], 1)


class LigacaoNoCerebroTests(unittest.TestCase):
    def _h(self):
        from brain import zenith_headless as H
        h = object.__new__(H.ZenithHeadlessBrain)
        h.bridge = mock.MagicMock()
        h.settings = mock.MagicMock()
        h.settings.get = lambda k, d=None: {"permissions": {"microphone": "ask"}}.get(k, d)
        h._conversa_voz = None
        h._atividade_atual = ("ocioso", "")
        h._mic_aprovado_nesta_sessao = False
        h._proxima_fala_vira_nota = False
        h._handle_mic_start = mock.MagicMock()
        h._parar_tudo = mock.MagicMock()
        return h

    def _enviados(self, h):
        return [c.args[0] for c in h.bridge.send.call_args_list]

    def test_comando_conversa_liga_e_abre_o_microfone_pela_aprovacao_de_sempre(self):
        h = self._h()
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        h._handle_mic_start.assert_called_once()                           # a 1ª vez da sessão ainda pede aprovação lá dentro
        self.assertTrue(h._conversa_voz.ligada)
        estados = [m.get("estado") for m in self._enviados(h) if m.get("action") == "conversa_estado"]
        self.assertEqual(estados, ["ouvindo"])

    def test_microfone_bloqueado_nas_permissoes_nao_liga(self):
        h = self._h()
        h.settings.get = lambda k, d=None: {"permissions": {"microphone": "never"}}.get(k, d)
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        self.assertFalse(h._conversa_voz.ligada)
        h._handle_mic_start.assert_not_called()
        self.assertTrue(any("bloqueado" in str(m.get("text", "")) for m in self._enviados(h)))

    def test_silencio_total_nao_liga(self):
        h = self._h()
        with mock.patch("brain.zenith_headless.pausa.ativo", return_value=True):
            h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        self.assertFalse(h._conversa_voz.ligada)

    def test_parar_desliga_a_conversa(self):
        h = self._h()
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        h._executar_comando({"acao": "parar"})
        self.assertFalse(h._conversa_voz.ligada)
        h._parar_tudo.assert_called_once()

    def test_desligar_e_status(self):
        h = self._h()
        h._executar_comando({"acao": "conversa", "args": {"modo": "status"}})
        self.assertIn("desligada", self._enviados(h)[-1]["text"])
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        h._executar_comando({"acao": "conversa", "args": {"modo": "desligar"}})
        self.assertFalse(h._conversa_voz.ligada)

    def test_texto_ouvido_vai_com_enviar_so_quando_a_conversa_esta_ligada(self):
        h = self._h()
        capturado = {}
        h._mic_fase = lambda *_: None
        h._mic_parcial = lambda *_: None
        h.interaction = types.SimpleNamespace(
            comecar_a_escutar=lambda cb, **k: capturado.update(cb=cb) or True, explicacao_falha_mic=lambda: "")
        h._start_listening()
        capturado["cb"]("oi zenith")                                       # conversa desligada: fluxo antigo (cai na caixa, sem enviar)
        msg = [m for m in self._enviados(h) if m.get("action") == "mic_transcript"][-1]
        self.assertNotIn("enviar", msg)
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        h.bridge.reset_mock()
        h._start_listening()
        capturado["cb"]("e agora?")
        msg = [m for m in self._enviados(h) if m.get("action") == "mic_transcript"][-1]
        self.assertEqual((msg["text"], msg.get("enviar")), ("e agora?", True))

    def test_nao_ouvi_nada_nao_enche_o_chat_mas_desliga_depois_de_tentar(self):
        h = self._h()
        capturado = {}
        h._mic_fase = lambda *_: None
        h._mic_parcial = lambda *_: None
        h.interaction = types.SimpleNamespace(
            comecar_a_escutar=lambda cb, **k: capturado.update(cb=cb) or True, explicacao_falha_mic=lambda: "mic mudo")
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        h._conversa_voz._agendar = lambda fn, atraso: None                  # sem relógio real
        for _ in range(3):
            h._start_listening()
            capturado["cb"]("")
        textos = [str(m.get("text", "")) for m in self._enviados(h) if m.get("action") == "chat_message"]
        self.assertFalse(any("mic mudo" in t for t in textos))              # não repete o diagnóstico a cada tentativa
        self.assertTrue(any("desliguei a conversa por voz" in t for t in textos))
        self.assertFalse(h._conversa_voz.ligada)

    def test_ficar_ocioso_avisa_a_conversa(self):
        h = self._h()
        h._atividade = lambda *a, **k: None
        h._executar_comando({"acao": "conversa", "args": {"modo": "ligar"}})
        h._conversa_voz.ao_transcrever("oi")
        h._conversa_voz._agendar = mock.MagicMock()
        h._estado("idle")
        h._conversa_voz._agendar.assert_called_once()

    def test_comando_digitado_vira_acao(self):
        from brain import zenith_commands as CMD
        r = CMD.tratar("/conversa ligar", {"settings": mock.MagicMock(), "core": None})
        self.assertEqual((r["acao"], r["args"]["modo"]), ("conversa", "ligar"))
        # v1.9 — sem argumento é STATUS: abrir o microfone exige a palavra "ligar".
        # É a única forma que continua verdadeira depois de juntar as duas linhas (o /conversa e o
        # microfone sempre pedem confirmação; um comando solto não deve começar a gravar por conta própria).
        self.assertEqual(CMD.tratar("/conversa", {"settings": mock.MagicMock(), "core": None})["args"]["modo"], "status")
        self.assertEqual(CMD.tratar("/conversa desligar", {"settings": mock.MagicMock(), "core": None})["args"]["modo"], "desligar")
        self.assertIn("Uso:", CMD.tratar("/conversa banana", {"settings": mock.MagicMock(), "core": None})["resposta"])

    def test_corpo_envia_sozinho_so_com_o_sinal(self):
        u = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")
        self.assertIn("func _on_mic_transcript_received(text: String, enviar: bool = false):", u)
        self.assertIn("if enviar:", u)
        c = (RAIZ / "body/zenith/brain_connector.gd").read_text(encoding="utf-8")
        self.assertIn('data.get("enviar", false)', c)
        self.assertIn('"conversa_estado"', c)


if __name__ == "__main__":
    unittest.main()
