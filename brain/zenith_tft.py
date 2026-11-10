"""
Zenith — TFT: a Zenith num mini-display ligado por USB a um ESP32-S3 (v24).

Pedido do Anderson: "quando eu conecto o ESP32-S3 na porta USB, a VRM da Zenith aparece na tela TFT".
(Nenhuma das versões anteriores — v21, v21 Claude, v22, v23 — tinha qualquer código de TFT: isto é novo.)

Como funciona (3 pedaços):
  1. CORPO (Godot): quando este módulo avisa (`tft_config`), o Godot renderiza o ROSTO da Zenith num SubViewport
     pequeno (câmera enquadrada na cabeça, fundo sólido), uns 10 quadros por segundo, e manda cada quadro em JPEG
     pro Cérebro (`tft_frame`). Boca, olhos e expressões aparecem sozinhos: é o MESMO avatar.
  2. CÉREBRO (este arquivo): procura a placa (porta USB da Espressif, VID 0x303A, ou a porta que você escolher com
     `/tft porta COM7`), faz um "aperto de mão" (`ZENITH?` → `ZENITH-TFT 1 240x240`) e repassa os quadros.
     Placa desconectada = para tudo e o Godot pára de renderizar (zero gasto).
  3. FIRMWARE (firmware/zenith_tft_esp32s3): decodifica o JPEG (TJpg_Decoder) e desenha na TFT.

Protocolo (USB serial, ida): handshake `ZENITH?\\n`; quadro `b"ZJ" + tamanho(4 bytes, little-endian) + JPEG`.
Volta: `ZENITH-TFT 1 LxA\\n` (handshake), `K\\n` (quadro desenhado), `E\\n` (erro ao decodificar). Quadro velho é descartado:
sempre vai o MAIS RECENTE (conversa fluida > fidelidade).

Segurança: só abre portas com VID da Espressif (ou a porta que o usuário escolheu) e só manda o handshake em texto.
Não executa nada no computador; o que vai pra placa é só imagem. DTR/RTS ficam desligados ao abrir a porta
(senão a placa reinicia a cada conexão).
"""
from __future__ import annotations

import base64
import io
import re
import socket
import struct
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except Exception:                       # pyserial não instalado: o módulo avisa em vez de quebrar
    serial = None
    list_ports = None

VID_ESPRESSIF = 0x303A

# CORREÇÃO (v1.0.1) — "a placa está na COM5 e ele lê a COM7":
# o `auto` só aceitava o VID nativo da Espressif (0x303A). Muitas placas ESP32-S3 (como a do Anderson)
# chegam pelo chip conversor USB-serial CH343/CH340 (VID 1A86), CP210x (10C4) ou FTDI (0403) — com essas,
# o `auto` não achava NADA e o programa ficava olhando portas erradas (a COM7 era um "Serial Padrão por
# link Bluetooth", fantasma de celular pareado). Agora aceita os quatro VID e ignora porta de Bluetooth.
VIDS_PLACA = {0x303A, 0x1A86, 0x10C4, 0x0403}
VID_ESPRESSIF = 0x303A          # mantido pelo nome antigo (outros arquivos/testes usam)
HANDSHAKE = b"ZENITH?\n"
PREFIXO_RESPOSTA = "ZENITH-TFT"
MAX_JPEG = 90_000                       # o firmware reserva um buffer desse tamanho
INTERVALO_BUSCA_S = 3.0

_RE_RESPOSTA = re.compile(r"^ZENITH-TFT\s+(\d+)\s+(\d+)x(\d+)", re.I)


ENQUADRES = ("rosto", "busto", "corpo")


def enquadre_valido(v) -> str:
    """rosto = cabeça e ombros · busto = peito pra cima (braços/gestos aparecem) · corpo = o avatar inteiro."""
    v = str(v or "rosto").lower()
    return v if v in ENQUADRES else "rosto"


def parse_resposta(linha: str):
    """'ZENITH-TFT 1 240x240' -> (versao, largura, altura) ou None."""
    m = _RE_RESPOSTA.match((linha or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def montar_pacote(jpg: bytes) -> bytes:
    return b"ZJ" + struct.pack("<I", len(jpg)) + jpg


def quadro_de_teste(largura: int, altura: int, texto: str = "Zenith TFT OK") -> bytes:
    """JPEG de teste (barras de cor + texto) pra conferir fiação/driver SEM precisar do Godot."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (largura, altura), (11, 16, 32))
    d = ImageDraw.Draw(im)
    cores = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255)]
    faixa = max(1, altura // 3)
    larg = max(1, largura // len(cores))
    for i, c in enumerate(cores):
        d.rectangle((i * larg, 0, (i + 1) * larg, faixa), fill=c)
    d.rectangle((0, faixa + 4, largura, faixa + 6), fill=(255, 255, 255))
    d.text((8, faixa + 14), texto, fill=(255, 255, 255))
    d.text((8, faixa + 34), f"{largura}x{altura}", fill=(160, 200, 255))
    d.text((8, altura - 24), "vermelho / verde / azul no topo", fill=(200, 200, 200))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------- Wi-Fi (TCP) [wifi-tft]
PORTA_WIFI_PADRAO = 7777                 # a mesma do firmware do carrinho
PORTA_DESCOBERTA = 7778                  # o carrinho avisa 'estou aqui' por UDP nesta porta


def eh_wifi(dispositivo) -> bool:
    """'wifi:carrinho.local' / 'wifi:192.168.0.50:7777' / 'tcp://...' -> True"""
    return str(dispositivo or "").strip().lower().startswith(("wifi:", "tcp://"))


def aviso_sem_pyserial() -> str:
    """v1.17 (port celular): sem pyserial. No celular isso é normal (não há cabo USB para a TFT); o caminho é o Wi-Fi."""
    try:
        from brain import zenith_plataforma
        if zenith_plataforma.detectar() == "android":
            return ("no celular não há cabo USB para a TFT — use o Wi-Fi do carrinho: digite /tft porta wifi:auto "
                    "(ou /tft porta wifi:IP). Bluetooth não serve: não leva imagem.")
    except Exception:
        pass
    return "pyserial não instalado — rode: pip install pyserial"


def separar_wifi(dispositivo):
    """'wifi:carrinho.local' -> ('carrinho.local', 7777)."""
    d = re.sub(r"^(wifi:|tcp://)\s*", "", str(dispositivo).strip(), flags=re.I).strip().rstrip("/")
    host, _, porta = d.partition(":")
    return host, (int(porta) if porta.isdigit() else PORTA_WIFI_PADRAO)


def host_da_rede_local(host: str) -> bool:
    """Só rede local: IP privado/loopback, nome '.local' ou nome simples (sem ponto). Nunca a internet."""
    import ipaddress
    host = (host or "").strip().lower()
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        pass
    return host.endswith(".local") or "." not in host


class SocketComoSerial:
    """Faz um socket TCP se comportar como a porta serial que o TftLink espera:
    write / flush / read(n) / readline / close, com tempo-limite (devolve parcial ou vazio, como o pyserial)."""

    def __init__(self, sock, tempo_leitura=0.3, tempo_escrita=2.0):
        self._s = sock
        self._buf = b""
        self._t_ler = tempo_leitura
        self._t_escrever = tempo_escrita
        self._s.settimeout(tempo_leitura)

    def write(self, dados: bytes):
        self._s.settimeout(self._t_escrever)          # escrever quadro grande pode demorar mais que ler 'K'
        try:
            self._s.sendall(dados)
        finally:
            self._s.settimeout(self._t_ler)
        return len(dados)

    def flush(self):
        pass

    def _puxar(self) -> bool:
        """Lê mais um pedaço do socket. False = estourou o tempo. Levanta ConnectionError se a placa fechou."""
        try:
            pedaco = self._s.recv(4096)
        except socket.timeout:
            return False
        if not pedaco:
            raise ConnectionError("a placa fechou a conexão")
        self._buf += pedaco
        return True

    def read(self, n: int = 1) -> bytes:
        while len(self._buf) < n:
            if not self._puxar():
                break
        r, self._buf = self._buf[:n], self._buf[n:]
        return r

    def readline(self) -> bytes:
        while b"\n" not in self._buf:
            if not self._puxar():
                r, self._buf = self._buf, b""
                return r
        i = self._buf.index(b"\n") + 1
        r, self._buf = self._buf[:i], self._buf[i:]
        return r

    def close(self):
        try:
            self._s.close()
        except Exception:
            pass


def _conectar_tcp(host, porta, tempo=3.0):
    s = socket.create_connection((host, porta), timeout=tempo)
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    return SocketComoSerial(s)


def descobrir_carrinho(tempo=3.0):
    """Escuta o aviso UDP do carrinho ('ZENITH-CARRINHO 1.5 192.168.43.7 7777 carrinho') e devolve (ip, porta) ou None.
    Só vale aviso com IP da rede local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PORTA_DESCOBERTA))
        s.settimeout(0.4)
        fim = time.time() + tempo
        while time.time() < fim:
            try:
                dados, _ = s.recvfrom(256)
            except socket.timeout:
                continue
            p = dados.decode("utf-8", "replace").split()
            if len(p) >= 4 and p[0] == "ZENITH-CARRINHO" and p[3].isdigit() and host_da_rede_local(p[2]):
                return p[2], int(p[3])
    finally:
        s.close()
    return None


def abrir_wifi(dispositivo: str):
    host, porta = separar_wifi(dispositivo)
    if host.lower() == "auto":                       # wifi:auto -> acha o carrinho sozinho
        achou = descobrir_carrinho()
        if achou:
            return _conectar_tcp(achou[0], achou[1])
        for h in ("carrinho.local", "192.168.4.1"):   # plano B: o nome do carrinho e a rede própria dele
            try:
                return _conectar_tcp(h, porta, 1.2)
            except OSError:
                continue
        raise RuntimeError("não achei o carrinho (ele está ligado e no mesmo Wi-Fi que este PC?)")
    if not host_da_rede_local(host):
        raise RuntimeError("só aceito placas da rede local (IP 192.168.x.x / 10.x.x.x, ou nome .local)")
    return _conectar_tcp(host, porta)

class TftLink:
    """Mantém a conexão com a placa e envia o quadro mais recente. Pontas injetáveis (testes sem hardware):
    abrir_porta(dispositivo, baud) -> objeto com write/flush/read/readline/close; listar_portas() -> [(dispositivo, vid)]."""

    def __init__(self, settings, enviar_ao_corpo, abrir_porta=None, listar_portas=None, log=print):
        self.settings = settings
        self._enviar_ao_corpo = enviar_ao_corpo
        self._abrir = abrir_porta or self._abrir_real
        self._listar = listar_portas or self._listar_real
        self._log = log
        self._porta = None
        self._dispositivo = ""
        self.painel = (240, 240)
        self._ultimo = None
        self._evt = threading.Event()
        self._fim = threading.Event()
        self._thread = None
        self._status = "desligado"
        self.quadros_enviados = 0
        self.erros = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ pontas reais
    @staticmethod
    def _abrir_real(dispositivo: str, baud: int):
        if eh_wifi(dispositivo):                                     # [wifi-tft]
            return abrir_wifi(dispositivo)
        if serial is None:
            raise RuntimeError("pyserial não instalado (pip install pyserial)")
        s = serial.Serial()
        s.port, s.baudrate = dispositivo, baud
        s.timeout, s.write_timeout = 0.3, 2.0
        s.dtr = False                    # DTR/RTS ligados reiniciam o ESP32-S3 a cada abertura da porta
        s.rts = False
        s.open()
        return s

    @staticmethod
    def _listar_real():
        if list_ports is None:
            return []
        return [(p.device, p.vid, (p.description or "")) for p in list_ports.comports()]

    # ------------------------------------------------------------------ configuração
    def _cfg(self, chave, padrao):
        try:
            v = self.settings.get(chave, padrao)
            return padrao if v is None else v
        except Exception:
            return padrao

    def _ativo(self) -> bool:
        return bool(self._cfg("tft_ativo", True))

    def config_para_corpo(self, ativo: bool) -> dict:
        q = max(30, min(95, int(self._cfg("tft_qualidade", 70)))) / 100.0
        return {"action": "tft_config", "ativo": bool(ativo), "w": int(self.painel[0]), "h": int(self.painel[1]),
                "fps": float(max(1, min(30, float(self._cfg("tft_fps", 10))))), "qualidade": q,
                "zoom": float(self._cfg("tft_zoom", 1.0)), "cor": str(self._cfg("tft_cor", "#0b1020")),
                "enquadre": enquadre_valido(self._cfg("tft_enquadre", "rosto"))}

    def reenviar_config(self):
        """O Godot (re)conectou ou o usuário mudou algo: repete o estado atual."""
        self._enviar_ao_corpo(self.config_para_corpo(self._porta is not None))

    # ------------------------------------------------------------------ ciclo de vida
    def iniciar(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._fim.clear()
        self._thread = threading.Thread(target=self._laco, daemon=True, name="zenith-tft")
        self._thread.start()

    def parar(self):
        self._fim.set()
        self._evt.set()
        self._desconectar("encerrado")
        if self._thread:
            self._thread.join(timeout=2)

    def on_quadro(self, jpg: bytes):
        """Chamado quando o Godot manda um quadro: guarda só o mais recente."""
        if not jpg or len(jpg) > MAX_JPEG:
            return
        with self._lock:
            self._ultimo = jpg
        self._evt.set()

    # ------------------------------------------------------------------ conexão
    def candidatas(self) -> list:
        escolhida = str(self._cfg("tft_porta", "") or "").strip()
        if escolhida and escolhida.lower() != "auto":
            return [escolhida]
        try:
            achadas = list(self._listar())
        except Exception as e:
            self._log(f"[Zenith/TFT] não consegui listar as portas: {e}")
            return []
        nativas, conversores, seriais = [], [], []
        for item in achadas:
            dev, vid = item[0], item[1]
            desc = str(item[2]) if len(item) > 2 else ""
            if "bluetooth" in desc.lower():
                continue                     # COM fantasma de aparelho pareado: nunca é a placa
            if vid == VID_ESPRESSIF:
                nativas.append(dev)          # USB nativa do ESP32-S3: sempre a primeira tentativa
            elif vid in VIDS_PLACA:
                conversores.append(dev)      # CH340/CH343, CP210x, FTDI: só vale se responder o handshake
            elif vid is None and ("usb" in desc.lower() or "serial" in desc.lower()):
                seriais.append(dev)
        return nativas + conversores + seriais

    def _aperto_de_mao(self, porta) -> tuple:
        for _ in range(3):                                   # a placa pode ainda estar ligando
            try:
                porta.write(HANDSHAKE)
                porta.flush()
                fim = time.time() + 1.2
                while time.time() < fim:
                    linha = porta.readline().decode("utf-8", "replace")
                    r = parse_resposta(linha)
                    if r:
                        return r
            except Exception:
                return None
        return None

    def _tentar_conectar(self) -> bool:
        for dev in self.candidatas():
            porta = None
            try:
                porta = self._abrir(dev, int(self._cfg("tft_baud", 921600)))
                r = self._aperto_de_mao(porta)
                if not r:
                    porta.close()
                    continue
                _versao, larg, alt = r
                with self._lock:
                    self._porta, self._dispositivo = porta, dev
                    self.painel = (larg, alt)
                self._status = f"conectado em {dev} ({larg}x{alt})"
                self._log(f"[Zenith/TFT] {self._status}")
                self.reenviar_config()
                return True
            except Exception as e:
                self._status = f"não consegui abrir {dev}: {str(e)[:80]}"
                try:
                    if porta:
                        porta.close()
                except Exception:
                    pass
        return False

    def _desconectar(self, motivo: str):
        with self._lock:
            porta, self._porta = self._porta, None
        if porta is not None:
            try:
                porta.close()
            except Exception:
                pass
            self._status = f"desconectado ({motivo})"
            self._log(f"[Zenith/TFT] {self._status}")
            try:
                self._enviar_ao_corpo(self.config_para_corpo(False))     # o Godot pára de renderizar
            except Exception:
                pass

    # ------------------------------------------------------------------ laço
    def _laco(self):
        if serial is None and self._abrir == self._abrir_real and not eh_wifi(self._cfg("tft_porta", "")):  # [wifi-tft]
            self._status = aviso_sem_pyserial()
            return
        while not self._fim.is_set():
            if not self._ativo():
                self._desconectar("desligado em Configurações")
                self._status = "desligado"
                self._fim.wait(1.0)
                continue
            if self._porta is None:
                if not self._tentar_conectar():
                    if not self._status.startswith("não consegui"):
                        self._status = ("procurando a placa no Wi-Fi…" if eh_wifi(self._cfg("tft_porta", "")) else "procurando a placa (ESP32-S3 por USB)…")  # [wifi-tft]
                    self._fim.wait(INTERVALO_BUSCA_S)
                    continue
            if not self._evt.wait(1.0):
                self._checar_viva()
                continue
            self._evt.clear()
            with self._lock:
                jpg, self._ultimo = self._ultimo, None
            if jpg:
                self._enviar_quadro(jpg)

    def _checar_viva(self):
        """Sem quadros há 1 s: confirma que a porta ainda existe (placa desplugada)."""
        if self._porta is None:
            return
        if eh_wifi(self._dispositivo):                               # [wifi-tft] a queda aparece na próxima escrita
            return
        try:
            if self._dispositivo not in [i[0] for i in self._listar()]:
                self._desconectar("a placa foi desligada da USB")
        except Exception:
            pass

    def _enviar_quadro(self, jpg: bytes):
        try:
            self._porta.write(montar_pacote(jpg))
            self._porta.flush()
            resp = self._porta.read(2)                      # 'K\n' = desenhou; 'E\n' = erro; vazio = placa ocupada
            if resp[:1] == b"E":
                self.erros += 1
            self.quadros_enviados += 1
        except Exception as e:
            self._desconectar(f"erro de escrita: {str(e)[:60]}")

    # ------------------------------------------------------------------ comandos
    def enviar_teste(self) -> str:
        if self._porta is None:
            return "🖥 Nenhuma placa conectada agora. Veja /tft."
        try:
            jpg = quadro_de_teste(*self.painel)
        except Exception as e:
            return f"🖥 Não consegui montar o quadro de teste: {e}"
        self.on_quadro(jpg)
        return (f"🖥 Quadro de teste enviado ({self.painel[0]}x{self.painel[1]}). Deve aparecer barras coloridas: de cima pra baixo "
                "vermelho, verde, azul… Se as cores vierem trocadas, ajuste TJPG_TROCAR_BYTES no firmware; se vier torto/deslocado, "
                "confira TFT_LARGURA/TFT_ALTURA e a rotação.")

    def status(self) -> str:
        if serial is None and self._abrir == self._abrir_real and not eh_wifi(self._cfg("tft_porta", "")):  # [wifi-tft]
            return "🖥 TFT: " + aviso_sem_pyserial()
        base = f"🖥 TFT: {self._status}"
        if self._porta is not None:
            base += f" · {self.quadros_enviados} quadro(s) enviado(s)"
            if self.erros:
                base += f", {self.erros} com erro de decodificação"
        return base


def decodificar_quadro_base64(texto: str) -> bytes:
    try:
        return base64.b64decode(texto or "", validate=False)
    except Exception:
        return b""
