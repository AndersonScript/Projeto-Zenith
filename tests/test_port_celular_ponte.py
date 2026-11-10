"""A ponte Cérebro <-> Corpo <-> Android (v1.11): pedidos e respostas pelo WebSocket que já existe.

Um "Corpo" falso (uma thread) atende os pedidos como o ponte_android.gd atenderia, e o fluxo de ponta a ponta
(AndroidPlataforma -> PonteCorpo -> Corpo -> resposta) é percorrido, inclusive o caso em que o Corpo conecta DEPOIS
do Cérebro e o de o Corpo cair no meio de um pedido.

    python -m unittest tests.test_port_celular_ponte
"""
from __future__ import annotations

import base64
import queue
import threading
import time
import unittest

from tests import _stubs
_stubs.instalar()

from brain import zenith_plataforma
from brain.zenith_plataforma_android import AndroidPlataforma
from brain.zenith_ponte_corpo import PonteCorpo


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


class CorpoFalso:
    """Faz o papel do Godot: recebe o que o Cérebro envia e responde numa thread, como chegaria pelo WebSocket."""

    def __init__(self, respostas=None):
        self.respostas = respostas or {}
        self.recebidas = []
        self.ponte = None
        self._fila = queue.Queue()
        self.mudo = False                       # True = não responde nada (para testar o tempo esgotado)
        threading.Thread(target=self._rodar, daemon=True).start()

    def enviar(self, dados):                    # é o `bridge.send` do Cérebro
        self.recebidas.append(dados)
        self._fila.put(dados)

    def _rodar(self):
        while True:
            dados = self._fila.get()
            if self.mudo:
                continue
            if dados.get("action") == "ponte_pedir_capacidades":
                self.ponte.tratar_mensagem({"action": "ponte_evento", "evento": "capacidades",
                                            "dados": {"lista": self.capacidades}})
            elif dados.get("action") == "ponte_chamar":
                resposta = self.respostas.get(dados["nome"], {"ok": True})
                if callable(resposta):
                    resposta = resposta(dados["args"])
                self.ponte.tratar_mensagem({"action": "ponte_resposta", "id": dados["id"], "resposta": resposta})

    capacidades = ["tela", "audio_saida"]


def pelo_websocket(ponte, mensagem):
    """Entrega uma mensagem como o WebSocket entregaria: numa thread à parte (nunca na que faz os pedidos)."""
    resultado = []
    t = threading.Thread(target=lambda: resultado.append(ponte.tratar_mensagem(mensagem)), daemon=True)
    t.start()
    t.join(5)
    return resultado[0] if resultado else None


def montar(respostas=None, tempo=2.0):
    corpo = CorpoFalso(respostas)
    ponte = PonteCorpo(corpo.enviar, tempo_padrao=tempo)
    corpo.ponte = ponte
    return corpo, ponte


class PonteCorpoTests(unittest.TestCase):
    def test_chamar_envia_o_pedido_e_devolve_a_resposta(self):
        corpo, ponte = montar({"audio.tocar": {"ok": True, "tocando": True}})
        ponte.definir_conectado(True)
        r = ponte.chamar("audio.tocar", caminho="/x.wav", volume=0.5)
        self.assertEqual(r, {"ok": True, "tocando": True})
        pedido = [d for d in corpo.recebidas if d.get("action") == "ponte_chamar"][0]
        self.assertEqual((pedido["nome"], pedido["args"]), ("audio.tocar", {"caminho": "/x.wav", "volume": 0.5}))
        self.assertIsInstance(pedido["id"], str)            # id texto: o Godot lê números JSON como float

    def test_sem_corpo_conectado_falha_com_frase_clara(self):
        _, ponte = montar()
        with self.assertRaises(RuntimeError) as ctx:
            ponte.chamar("audio.parar")
        self.assertIn("não está conectado", str(ctx.exception))

    def test_tempo_esgotado_vira_erro_claro_e_resposta_atrasada_e_ignorada(self):
        corpo, ponte = montar(tempo=0.2)
        ponte.definir_conectado(True)
        corpo.mudo = True
        with self.assertRaises(TimeoutError) as ctx:
            ponte.chamar("notificacao.mostrar", titulo="a", texto="b")
        self.assertIn("não respondeu", str(ctx.exception))
        atrasado = [d for d in corpo.recebidas if d.get("action") == "ponte_chamar"][0]["id"]
        self.assertTrue(pelo_websocket(ponte, {"action": "ponte_resposta", "id": atrasado, "resposta": {"ok": True}}))
        corpo.mudo = False
        self.assertEqual(ponte.chamar("audio.parar"), {"ok": True})            # a chamada seguinte não se confunde

    def test_capacidades_so_do_que_o_corpo_anunciou_e_sem_ida_a_rede(self):
        corpo, ponte = montar()
        with self.assertRaises(RuntimeError):
            ponte.chamar("capacidades.listar")                 # ainda ninguém anunciou
        ponte.definir_conectado(True)                          # pede ao Corpo; ele responde com o evento
        for _ in range(100):
            try:
                self.assertEqual(ponte.chamar("capacidades.listar"), ["tela", "audio_saida"])
                break
            except RuntimeError:
                time.sleep(0.02)
        else:
            self.fail("o Corpo não anunciou as capacidades")
        self.assertEqual([d["nome"] for d in corpo.recebidas if d.get("action") == "ponte_chamar"], [])   # nenhuma ida à rede

    def test_corpo_que_cai_falha_o_pedido_pendente_na_hora_e_esquece_as_capacidades(self):
        corpo, ponte = montar(tempo=5.0)
        ponte.definir_conectado(True)
        corpo.mudo = True
        resultado = []
        t = threading.Thread(target=lambda: resultado.append(ponte.chamar("tela.capturar")), daemon=True)
        t.start()
        time.sleep(0.15)
        ponte.definir_conectado(False)
        t.join(2)
        self.assertEqual(resultado[0]["ok"], False)
        self.assertIn("desconectou", resultado[0]["erro"])
        with self.assertRaises(RuntimeError):
            ponte.chamar("capacidades.listar")

    def test_so_pega_mensagens_da_ponte(self):
        _, ponte = montar()
        self.assertFalse(ponte.tratar_mensagem({"action": "chat", "text": "oi"}))
        self.assertFalse(ponte.tratar_mensagem({"sem": "action"}))
        self.assertTrue(ponte.tratar_mensagem({"action": "ponte_evento", "evento": "x", "dados": {}}))

    def test_eventos_chegam_aos_assinantes_e_um_assinante_ruim_nao_derruba_os_outros(self):
        _, ponte = montar()
        recebidos = []

        def ruim(_):
            raise RuntimeError("boom")

        ponte.assinar("mic.quadro", ruim)
        ponte.assinar("mic.quadro", recebidos.append)
        ponte.tratar_mensagem({"action": "ponte_evento", "evento": "mic.quadro", "dados": {"pcm16": "AAA="}})
        self.assertEqual(recebidos, [{"pcm16": "AAA="}])
        ponte.desassinar("mic.quadro", recebidos.append)

    def test_pedido_bloqueante_dentro_da_thread_do_websocket_e_barrado(self):
        """É o erro que travaria o Corpo inteiro: pedir e esperar resposta na mesma thread que recebe as respostas."""
        _, ponte = montar()
        ponte.definir_conectado(True)
        erros = []

        def dentro_do_handler(_):
            try:
                ponte.chamar("audio.parar")
            except RuntimeError as e:
                erros.append(str(e))

        ponte.assinar("qualquer", dentro_do_handler)
        ponte.tratar_mensagem({"action": "ponte_evento", "evento": "qualquer", "dados": {}})
        self.assertTrue(erros and "thread do WebSocket" in erros[0])

    def test_pedir_capacidades_ao_conectar_so_quando_muda(self):
        corpo, ponte = montar()
        ponte.definir_conectado(True)
        ponte.definir_conectado(True)
        pedidos = [d for d in corpo.recebidas if d.get("action") == "ponte_pedir_capacidades"]
        self.assertEqual(len(pedidos), 1)

    def test_enviar_que_falha_vira_erro_claro_e_nao_deixa_pedido_pendurado(self):
        def quebrado(_):
            raise OSError("socket fechado")

        ponte = PonteCorpo(quebrado)
        ponte.definir_conectado(True)
        with self.assertRaises(RuntimeError) as ctx:
            ponte.chamar("audio.parar")
        self.assertIn("socket fechado", str(ctx.exception))
        self.assertEqual(ponte._pendentes, {})


class PontaAPontaTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(zenith_plataforma.definir, None)

    def test_corpo_conecta_depois_do_cerebro_e_a_tela_passa_a_funcionar(self):
        corpo, ponte = montar({"tela.capturar": {"ok": True, "imagem": b64(b"PNGDADOS")}})
        plat = AndroidPlataforma(ponte)                       # o Cérebro nasce ANTES de o Corpo conectar
        self.assertFalse(plat.tem("tela"))
        img, erro = plat.capturar_tela()
        self.assertIsNone(img)
        self.assertIn("não dá para", erro)                    # sem travar nem estourar
        ponte.definir_conectado(True)                         # o Corpo conecta e anuncia o que o aparelho tem
        for _ in range(100):
            if plat.tem("tela"):
                break
            time.sleep(0.02)
        self.assertTrue(plat.tem("tela"))
        self.assertEqual(plat.capturar_tela(), (b"PNGDADOS", None))

    def test_capacidades_mudam_quando_o_corpo_anuncia_de_novo(self):
        corpo, ponte = montar()
        plat = AndroidPlataforma(ponte)
        ponte.definir_conectado(True)
        for _ in range(100):
            if plat.tem("audio_saida"):
                break
            time.sleep(0.02)
        self.assertTrue(plat.tem("audio_saida"))
        pelo_websocket(ponte, {"action": "ponte_evento", "evento": "capacidades",
                               "dados": {"lista": ["microfone"]}})        # a pessoa deu a permissão do microfone
        self.assertTrue(plat.tem("microfone"))
        self.assertFalse(plat.tem("audio_saida"))

    def test_tem_pode_ser_perguntado_de_dentro_da_thread_do_websocket(self):
        _, ponte = montar()
        plat = AndroidPlataforma(ponte)
        ponte.tratar_mensagem({"action": "ponte_evento", "evento": "capacidades", "dados": {"lista": ["tela"]}})
        resultado = []
        ponte.assinar("x", lambda _: resultado.append(plat.tem("tela")))
        ponte.tratar_mensagem({"action": "ponte_evento", "evento": "x", "dados": {}})      # roda na thread receptora
        self.assertEqual(resultado, [True])

    def test_microfone_de_ponta_a_ponta_pelo_corpo(self):
        corpo, ponte = montar({"mic.iniciar": {"ok": True}, "mic.parar": {"ok": True}})
        corpo.capacidades = ["microfone"]                     # o que ESTE Corpo anuncia (e só isso: sem corrida)
        plat = AndroidPlataforma(ponte)
        ponte.definir_conectado(True)
        for _ in range(250):
            if plat.tem("microfone"):
                break
            time.sleep(0.02)
        self.assertTrue(plat.tem("microfone"))
        pedacos = []
        plat.iniciar_microfone(pedacos.append, taxa=16000)
        pelo_websocket(ponte, {"action": "ponte_evento", "evento": "mic.quadro", "dados": {"pcm16": b64(b"\x01\x02\x03\x04")}})
        plat.parar_microfone()
        self.assertEqual(pedacos, [b"\x01\x02\x03\x04"])
        nomes = [d["nome"] for d in corpo.recebidas if d.get("action") == "ponte_chamar"]
        self.assertEqual(nomes, ["mic.iniciar", "mic.parar"])


class RoteadorDoCerebroTests(unittest.TestCase):
    def test_headless_entrega_a_ponte_primeiro_e_nao_trata_como_comando(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        hl = ZenithHeadlessBrain.__new__(ZenithHeadlessBrain)
        _, hl._ponte_corpo = montar()
        recebidos = []
        hl._ponte_corpo.assinar("mic.quadro", recebidos.append)
        hl._on_message({"action": "ponte_evento", "evento": "mic.quadro", "dados": {"pcm16": "AA=="}})
        self.assertEqual(recebidos, [{"pcm16": "AA=="}])

    def test_headless_sem_ponte_continua_roteando_normal(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        hl = ZenithHeadlessBrain.__new__(ZenithHeadlessBrain)
        chamadas = []
        hl._handle_chat = chamadas.append
        hl._on_message({"action": "chat", "text": "oi"})
        self.assertEqual(chamadas, [{"action": "chat", "text": "oi"}])

    def test_on_state_avisa_a_ponte(self):
        from brain.zenith_headless import ZenithHeadlessBrain
        hl = ZenithHeadlessBrain.__new__(ZenithHeadlessBrain)
        _, hl._ponte_corpo = montar()
        hl._on_state(False)                                     # False só desliga: não manda nada ao Corpo
        self.assertFalse(hl._ponte_corpo.conectado)


if __name__ == "__main__":
    unittest.main()
