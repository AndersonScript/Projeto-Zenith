#!/usr/bin/env python3
"""
Zenith — liga o display TFT do ESP32-S3 por WI-FI (além da USB).

Uso (na pasta do Zenith, onde existe a pasta  brain/ ):
    python aplicar_wifi_tft.py                 # aplica
    python aplicar_wifi_tft.py "C:\\Zenith\\Zenith"   # ou diz onde está o Zenith
    python aplicar_wifi_tft.py --desfazer      # volta os arquivos originais (usa os .bak_wifi)

O que faz (só 2 arquivos, com cópia de segurança .bak_wifi):
  brain/zenith_tft.py       aceita a "porta"  wifi:auto  (acha o carrinho sozinho), wifi:carrinho.local ou wifi:IP  e fala com a placa por TCP
                            usando o MESMO protocolo da USB (nada muda no Godot nem no firmware além do Wi-Fi)
  brain/zenith_commands.py  o comando  /tft porta wifi:carrinho.local  passa a ser aceito

Depois:   /tft porta wifi:carrinho.local   (ou o IP que aparece na telinha)   e   /tft teste
Voltar para USB:  /tft porta auto

Segurança: só aceita placas da REDE LOCAL (IP privado, nome .local ou nome simples). Nunca manda o rosto para a internet.
É idempotente: rodar duas vezes não duplica nada.
"""
import shutil
import sys
from pathlib import Path

MARCA = "# [wifi-tft]"

# ---------------------------------------------------------------- zenith_tft.py
TFT_IMPORT_VELHO = "import re\nimport struct\n"
TFT_IMPORT_NOVO = "import re\nimport socket\nimport struct\n"

TFT_BLOCO = '''

# ---------------------------------------------------------------- Wi-Fi (TCP) [wifi-tft]
PORTA_WIFI_PADRAO = 7777                 # a mesma do firmware do carrinho
PORTA_DESCOBERTA = 7778                  # o carrinho avisa 'estou aqui' por UDP nesta porta


def eh_wifi(dispositivo) -> bool:
    """'wifi:carrinho.local' / 'wifi:192.168.0.50:7777' / 'tcp://...' -> True"""
    return str(dispositivo or "").strip().lower().startswith(("wifi:", "tcp://"))


def separar_wifi(dispositivo):
    """'wifi:carrinho.local' -> ('carrinho.local', 7777)."""
    d = re.sub(r"^(wifi:|tcp://)\\s*", "", str(dispositivo).strip(), flags=re.I).strip().rstrip("/")
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
        while b"\\n" not in self._buf:
            if not self._puxar():
                r, self._buf = self._buf, b""
                return r
        i = self._buf.index(b"\\n") + 1
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
'''

TFT_CLASSE_ANCORA = "\n\nclass TftLink:"

TFT_ABRIR_VELHO = '''    def _abrir_real(dispositivo: str, baud: int):
        if serial is None:'''
TFT_ABRIR_NOVO = '''    def _abrir_real(dispositivo: str, baud: int):
        if eh_wifi(dispositivo):                                     # [wifi-tft]
            return abrir_wifi(dispositivo)
        if serial is None:'''

TFT_VIVA_VELHO = '''        try:
            if self._dispositivo not in [d for d, _ in self._listar()]:'''
TFT_VIVA_NOVO = '''        if eh_wifi(self._dispositivo):                               # [wifi-tft] a queda aparece na próxima escrita
            return
        try:
            if self._dispositivo not in [d for d, _ in self._listar()]:'''

TFT_LACO_VELHO = '''        if serial is None and self._abrir == self._abrir_real:
            self._status = "pyserial não instalado — rode: pip install pyserial"
            return'''
TFT_LACO_NOVO = '''        if serial is None and self._abrir == self._abrir_real and not eh_wifi(self._cfg("tft_porta", "")):  # [wifi-tft]
            self._status = "pyserial não instalado — rode: pip install pyserial"
            return'''

TFT_STATUS_VELHO = '''        if serial is None and self._abrir == self._abrir_real:
            return "🖥 TFT: pyserial não instalado — rode: pip install pyserial"'''
TFT_STATUS_NOVO = '''        if serial is None and self._abrir == self._abrir_real and not eh_wifi(self._cfg("tft_porta", "")):  # [wifi-tft]
            return "🖥 TFT: pyserial não instalado — rode: pip install pyserial"'''

TFT_PROCURANDO_VELHO = 'self._status = "procurando a placa (ESP32-S3 por USB)…"'
TFT_PROCURANDO_NOVO = ('self._status = ("procurando a placa no Wi-Fi…" if eh_wifi(self._cfg("tft_porta", "")) '
                       'else "procurando a placa (ESP32-S3 por USB)…")  # [wifi-tft]')

# ---------------------------------------------------------------- zenith_commands.py
CMD_REGEX_VELHO = r'''re.match(r"^(COM\d{1,3}|/dev/tty[A-Za-z0-9._-]+)$", valor, re.I)'''
CMD_REGEX_NOVO = r'''re.match(r"^(COM\d{1,3}|/dev/tty[A-Za-z0-9._-]+|(wifi:|tcp://)[A-Za-z0-9._-]+(:\d{2,5})?)$", valor, re.I)'''
CMD_ERRO_VELHO = "❌ Porta inválida. Exemplos: COM7 · /dev/ttyACM0 · auto"
CMD_ERRO_NOVO = "❌ Porta inválida. Exemplos: COM7 · /dev/ttyACM0 · wifi:auto · wifi:carrinho.local · wifi:192.168.0.50 · auto"
CMD_USO_VELHO = "🖥 Uso: /tft porta COM7 (ou /tft porta auto). Auto = placa com USB nativa do ESP32-S3."
CMD_USO_NOVO = ("🖥 Uso: /tft porta COM7 · /tft porta wifi:auto (acha o carrinho) · /tft porta wifi:IP · /tft porta auto. "
                "Auto = placa com USB nativa do ESP32-S3.")


def _ler(caminho: Path):
    bruto = caminho.read_bytes()
    crlf = b"\r\n" in bruto
    return bruto.decode("utf-8").replace("\r\n", "\n"), crlf


def _gravar(caminho: Path, texto: str, crlf: bool):
    if crlf:
        texto = texto.replace("\n", "\r\n")
    caminho.write_bytes(texto.encode("utf-8"))


def _trocar(texto: str, velho: str, novo: str, nome: str) -> str:
    if velho not in texto:
        raise SystemExit(f"❌ Não achei o trecho '{nome}'. Esta versão do Zenith é diferente da que eu li (v1.9). "
                         "Nada foi alterado. Me mande o arquivo e eu adapto.")
    return texto.replace(velho, novo, 1)


def aplicar(raiz: Path) -> list:
    tft, cmd = raiz / "brain" / "zenith_tft.py", raiz / "brain" / "zenith_commands.py"
    for f in (tft, cmd):
        if not f.exists():
            raise SystemExit(f"❌ Não achei {f}. Rode este script dentro da pasta do Zenith (a que tem a pasta 'brain').")
    feito = []

    t, crlf_t = _ler(tft)
    if "def abrir_wifi" in t and "def descobrir_carrinho" not in t:      # versão antiga do patch: volta ao original e aplica de novo
        bak = Path(str(tft) + ".bak_wifi")
        if not bak.exists():
            raise SystemExit("❌ zenith_tft.py tem uma versão antiga do patch e não achei a cópia .bak_wifi para refazer.")
        shutil.copy2(bak, tft)
        t, crlf_t = _ler(tft)
    if "def descobrir_carrinho" in t:
        feito.append("zenith_tft.py já tinha o Wi-Fi com descoberta automática (nada a fazer)")
    else:
        t = _trocar(t, TFT_IMPORT_VELHO, TFT_IMPORT_NOVO, "imports")
        t = _trocar(t, TFT_CLASSE_ANCORA, TFT_BLOCO + "\nclass TftLink:", "class TftLink")
        t = _trocar(t, TFT_ABRIR_VELHO, TFT_ABRIR_NOVO, "_abrir_real")
        t = _trocar(t, TFT_VIVA_VELHO, TFT_VIVA_NOVO, "_checar_viva")
        t = _trocar(t, TFT_LACO_VELHO, TFT_LACO_NOVO, "_laco")
        t = _trocar(t, TFT_STATUS_VELHO, TFT_STATUS_NOVO, "status")
        t = _trocar(t, TFT_PROCURANDO_VELHO, TFT_PROCURANDO_NOVO, "mensagem de busca")
        shutil.copy2(tft, str(tft) + ".bak_wifi")
        _gravar(tft, t, crlf_t)
        feito.append("zenith_tft.py: Wi-Fi adicionado")

    c, crlf_c = _ler(cmd)
    if "wifi:|tcp://" in c:
        feito.append("zenith_commands.py já aceitava wifi: (nada a fazer)")
    else:
        c = _trocar(c, CMD_REGEX_VELHO, CMD_REGEX_NOVO, "regex de /tft porta")
        c = _trocar(c, CMD_ERRO_VELHO, CMD_ERRO_NOVO, "mensagem de porta inválida")
        c = _trocar(c, CMD_USO_VELHO, CMD_USO_NOVO, "mensagem de uso")
        shutil.copy2(cmd, str(cmd) + ".bak_wifi")
        _gravar(cmd, c, crlf_c)
        feito.append("zenith_commands.py: /tft porta wifi:... aceito")
    return feito


def desfazer(raiz: Path) -> list:
    feito = []
    for nome in ("zenith_tft.py", "zenith_commands.py"):
        arq = raiz / "brain" / nome
        bak = Path(str(arq) + ".bak_wifi")
        if bak.exists():
            shutil.copy2(bak, arq)
            feito.append(f"{nome} restaurado")
    return feito or ["não havia cópias .bak_wifi para restaurar"]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raiz = Path(args[0]) if args else Path.cwd()
    if "--desfazer" in sys.argv:
        for linha in desfazer(raiz):
            print("↩", linha)
    else:
        for linha in aplicar(raiz):
            print("✓", linha)
        print("\nPronto. No Zenith:  /tft porta wifi:auto   e depois   /tft teste")
