"""
Testes do Wi-Fi do TFT: o Zenith fala com um "ESP32-S3 de mentira" por TCP, com o MESMO protocolo do firmware
(ZENITH? -> ZENITH-TFT 1 LxA ; 'ZJ'+tam+JPEG -> K / E).
Rodar: python -m unittest tests.test_wifi_tft -v
NÃO prova: que o firmware compila no seu ESP32, nem que o Wi-Fi da sua rede deixa um aparelho falar com o outro.
"""
import socket
import struct
import sys
import threading
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_commands as cmd
from brain import zenith_tft as T


class Cfg:
    def __init__(self, **d):
        self.d = dict(d)

    def get(self, k, p=None):
        v = self.d.get(k, p)
        return p if v is None else v

    def update(self, m):
        self.d.update(m)


class EspFalso:
    """Imita o firmware zenith_carrinho_esp32s3 na porta 7777."""
    def __init__(self, tamanho="128x160", erro_nos_quadros=False):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(2)
        self.porta = self.srv.getsockname()[1]
        self.tamanho = tamanho
        self.erro = erro_nos_quadros
        self.quadros = []
        self.conexoes = 0
        self._vivo = True
        self._clientes = []
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while self._vivo:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conexoes += 1
            self._clientes.append(c)
            threading.Thread(target=self._atender, args=(c,), daemon=True).start()

    def _ler(self, c, n):
        b = b""
        while len(b) < n:
            p = c.recv(n - len(b))
            if not p:
                raise ConnectionError
            b += p
        return b

    def _atender(self, c):
        try:
            while True:
                b = self._ler(c, 1)
                if b != b"Z":
                    continue
                k = self._ler(c, 1)
                if k == b"E":                                   # "ZENITH?\n"
                    resto = b""
                    while not resto.endswith(b"\n"):
                        resto += self._ler(c, 1)
                    c.sendall(f"ZENITH-TFT 1 {self.tamanho}\n".encode())
                elif k == b"J":
                    n = struct.unpack("<I", self._ler(c, 4))[0]
                    self.quadros.append(self._ler(c, n))
                    c.sendall(b"E\n" if self.erro else b"K\n")
        except Exception:
            pass

    def derrubar_clientes(self):
        for c in self._clientes:
            try:
                c.shutdown(socket.SHUT_RDWR)
                c.close()
            except Exception:
                pass
        self._clientes = []

    def fechar(self):
        self._vivo = False
        self.derrubar_clientes()
        self.srv.close()


def esperar(cond, tempo=6.0):
    fim = time.time() + tempo
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


class TestTransporteWifi(unittest.TestCase):
    def setUp(self):
        self.esp = EspFalso()
        self.msgs = []
        self.cfg = Cfg(tft_ativo=True, tft_fps=10, tft_qualidade=70, tft_porta=f"wifi:127.0.0.1:{self.esp.porta}")
        self.link = T.TftLink(self.cfg, self.msgs.append, log=lambda *a: None)
        T.INTERVALO_BUSCA_S = 0.2

    def tearDown(self):
        self.link.parar()
        self.esp.fechar()

    def test_conecta_le_o_tamanho_da_tela_e_avisa_o_godot(self):
        self.link.iniciar()
        self.assertTrue(esperar(lambda: self.link._porta is not None), self.link.status())
        self.assertEqual(self.link.painel, (128, 160))
        self.assertIn("conectado", self.link.status())
        cfgs = [m for m in self.msgs if m.get("action") == "tft_config" and m.get("ativo")]
        self.assertTrue(cfgs)
        self.assertEqual((cfgs[-1]["w"], cfgs[-1]["h"]), (128, 160))     # o Godot vai renderizar 128x160

    def test_quadro_chega_inteiro_e_o_K_e_lido(self):
        self.link.iniciar()
        self.assertTrue(esperar(lambda: self.link._porta is not None))
        jpg = T.quadro_de_teste(128, 160)
        self.link.on_quadro(jpg)
        self.assertTrue(esperar(lambda: len(self.esp.quadros) == 1))
        self.assertEqual(self.esp.quadros[0], jpg)                       # byte a byte
        self.assertTrue(esperar(lambda: self.link.quadros_enviados == 1))
        self.assertEqual(self.link.erros, 0)

    def test_varios_quadros_seguidos_e_sempre_o_mais_recente(self):
        self.link.iniciar()
        self.assertTrue(esperar(lambda: self.link._porta is not None))
        qs = [T.quadro_de_teste(128, 160, texto=f"q{i}") for i in range(12)]
        for q in qs:
            self.link.on_quadro(q)
            time.sleep(0.03)
        self.assertTrue(esperar(lambda: len(self.esp.quadros) >= 6))
        self.assertEqual(self.esp.quadros[-1], qs[-1])
        for recebido in self.esp.quadros:
            self.assertIn(recebido, qs)                                   # nenhum quadro corrompido

    def test_erro_de_decodificacao_E_e_contado(self):
        self.esp.erro = True
        self.link.iniciar()
        self.assertTrue(esperar(lambda: self.link._porta is not None))
        self.link.on_quadro(T.quadro_de_teste(128, 160))
        self.assertTrue(esperar(lambda: self.link.erros == 1))

    def test_placa_some_desconecta_e_reconecta_sozinho(self):
        self.link.iniciar()
        self.assertTrue(esperar(lambda: self.link._porta is not None))
        self.assertEqual(self.esp.conexoes, 1)
        self.esp.derrubar_clientes()                                      # Wi-Fi caiu / placa reiniciou
        for _ in range(60):                                               # a queda aparece no próximo quadro enviado
            self.link.on_quadro(T.quadro_de_teste(128, 160))
            if self.esp.conexoes >= 2:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(self.esp.conexoes, 2, "deveria ter percebido a queda e reconectado sozinho")
        desligou = [m for m in self.msgs if m.get("action") == "tft_config" and not m.get("ativo")]
        self.assertTrue(desligou)                                         # o Godot foi avisado (parou de renderizar)
        self.assertTrue(esperar(lambda: self.link._porta is not None))    # e está conectado de novo
        n = len(self.esp.quadros)
        self.link.on_quadro(T.quadro_de_teste(128, 160, texto="depois"))
        self.assertTrue(esperar(lambda: len(self.esp.quadros) > n), "depois de reconectar, os quadros voltam a chegar")

    def test_nao_derruba_a_conexao_por_ficar_parado_sem_quadros(self):
        self.link.iniciar()
        self.assertTrue(esperar(lambda: self.link._porta is not None))
        time.sleep(2.5)                                                   # _checar_viva roda; não pode achar que a "porta sumiu"
        self.assertIsNotNone(self.link._porta)

    def test_status_nao_pede_pyserial_no_modo_wifi(self):
        antigo = T.serial
        T.serial = None
        try:
            self.assertNotIn("pyserial", self.link.status())
        finally:
            T.serial = antigo


class TestSegurancaEComando(unittest.TestCase):
    def test_so_aceita_rede_local(self):
        ok = ["192.168.0.50", "10.0.0.7", "172.16.5.5", "127.0.0.1", "169.254.1.1", "carrinho.local", "carrinho", "Carrinho.LOCAL"]
        ruim = ["8.8.8.8", "1.1.1.1", "example.com", "meusite.com.br", "", "93.184.216.34"]
        for h in ok:
            self.assertTrue(T.host_da_rede_local(h), h)
        for h in ruim:
            self.assertFalse(T.host_da_rede_local(h), h)

    def test_host_publico_e_recusado_sem_abrir_conexao(self):
        with self.assertRaises(RuntimeError):
            T.abrir_wifi("wifi:8.8.8.8")

    def test_separar_wifi(self):
        self.assertEqual(T.separar_wifi("wifi:carrinho.local"), ("carrinho.local", 7777))
        self.assertEqual(T.separar_wifi("WIFI:192.168.0.50:9000"), ("192.168.0.50", 9000))
        self.assertEqual(T.separar_wifi("tcp://carrinho.local:7777/"), ("carrinho.local", 7777))

    def test_comando_tft_porta_aceita_wifi_e_ainda_recusa_lixo(self):
        cfg = Cfg(tft_porta="")
        r = cmd.tratar("/tft porta wifi:carrinho.local", {"settings": cfg})
        self.assertEqual((cfg.get("tft_porta"), r["acao"]), ("wifi:carrinho.local", "tft"))
        cmd.tratar("/tft porta wifi:192.168.0.50:7777", {"settings": cfg})
        self.assertEqual(cfg.get("tft_porta"), "wifi:192.168.0.50:7777")
        cmd.tratar("/tft porta COM7", {"settings": cfg})                  # USB continua igual
        self.assertEqual(cfg.get("tft_porta"), "COM7")
        cmd.tratar("/tft porta auto", {"settings": cfg})
        self.assertEqual(cfg.get("tft_porta"), "")
        for lixo in ["wifi:", "wifi:x;rm", "wifi:host:9", "http://x.com", "rm -rf"]:
            antes = cfg.get("tft_porta")
            self.assertIn("inválida", cmd.tratar(f"/tft porta {lixo}", {"settings": cfg})["resposta"], lixo)
            self.assertEqual(cfg.get("tft_porta"), antes)


class TestSocketComoSerial(unittest.TestCase):
    def test_readline_e_read_com_tempo_limite(self):
        a, b = socket.socketpair()
        s = T.SocketComoSerial(a, tempo_leitura=0.1)
        b.sendall(b"ZENITH-TFT 1 128x160\nK\n")
        self.assertEqual(s.readline(), b"ZENITH-TFT 1 128x160\n")
        self.assertEqual(s.read(2), b"K\n")
        self.assertEqual(s.read(2), b"")                                   # nada chegou: vazio, não trava
        self.assertEqual(s.readline(), b"")
        b.sendall(b"par")
        self.assertEqual(s.readline(), b"par")                             # parcial no tempo-limite (como o pyserial)
        b.close()
        with self.assertRaises(ConnectionError):
            s.read(1)
        s.close()


class TestDescobertaAutomatica(unittest.TestCase):
    """wifi:auto — o Zenith acha o carrinho pelo aviso UDP, sem digitar IP."""

    def setUp(self):
        self.udp_porta = _porta_udp_livre()
        T.PORTA_DESCOBERTA = self.udp_porta
        self._parar = False

    def tearDown(self):
        self._parar = True
        T.PORTA_DESCOBERTA = 7778

    def _gritar(self, textos, intervalo=0.15):
        def laco():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            while not self._parar:
                for t in textos:
                    s.sendto(t.encode(), ("127.0.0.1", self.udp_porta))
                time.sleep(intervalo)
            s.close()
        threading.Thread(target=laco, daemon=True).start()

    def test_acha_o_carrinho_e_conecta_pelo_link(self):
        esp = EspFalso()
        try:
            self._gritar([f"ZENITH-CARRINHO 1.5 127.0.0.1 {esp.porta} carrinho"])
            msgs = []
            cfg = Cfg(tft_ativo=True, tft_fps=10, tft_qualidade=70, tft_porta="wifi:auto")
            link = T.TftLink(cfg, msgs.append, log=lambda *a: None)
            T.INTERVALO_BUSCA_S = 0.2
            link.iniciar()
            try:
                self.assertTrue(esperar(lambda: link._porta is not None, 10), link.status())
                self.assertEqual(link.painel, (128, 160))
                jpg = T.quadro_de_teste(128, 160)
                link.on_quadro(jpg)
                self.assertTrue(esperar(lambda: len(esp.quadros) == 1))
                self.assertEqual(esp.quadros[0], jpg)
            finally:
                link.parar()
        finally:
            esp.fechar()

    def test_ignora_aviso_falso_ou_de_fora_da_rede_local(self):
        self._gritar(["ZENITH-CARRINHO 1.5 8.8.8.8 7777 x",          # IP público: recusado
                      "OUTRA-COISA 1.5 127.0.0.1 7777 x",            # não é do carrinho
                      "ZENITH-CARRINHO 1.5 127.0.0.1 abc x",         # porta inválida
                      "lixo"])
        self.assertIsNone(T.descobrir_carrinho(tempo=1.2))

    def test_devolve_ip_e_porta_do_aviso_bom(self):
        self._gritar(["ZENITH-CARRINHO 1.5 192.168.43.7 7777 carrinho"])
        self.assertEqual(T.descobrir_carrinho(tempo=3.0), ("192.168.43.7", 7777))

    def test_sem_aviso_tenta_o_nome_e_a_rede_propria_e_depois_desiste(self):
        tentados = []

        def falso(endereco, timeout=None):
            tentados.append(endereco[0])
            raise OSError("sem rota")
        original = T.socket.create_connection
        T.socket.create_connection = falso
        try:
            T.PORTA_DESCOBERTA = self.udp_porta
            with self.assertRaises(RuntimeError) as c:
                T.abrir_wifi("wifi:auto")
            self.assertIn("não achei o carrinho", str(c.exception))
            self.assertEqual(tentados, ["carrinho.local", "192.168.4.1"])
        finally:
            T.socket.create_connection = original

    def test_comando_aceita_wifi_auto(self):
        cfg = Cfg(tft_porta="")
        cmd.tratar("/tft porta wifi:auto", {"settings": cfg})
        self.assertEqual(cfg.get("tft_porta"), "wifi:auto")


def _porta_udp_livre():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


if __name__ == "__main__":
    unittest.main()
