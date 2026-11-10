# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_hardware.py — Fala com Arduino/ESP32 por serial.
#
#  Igual às outras ações sensíveis: quem chama isso já passou pela
#  aprovação do Gatekeeper (Pilar 1) em zenith_core.approve_action().
#  Este módulo só executa quando já foi aprovado.
#
#  v1.17 (port celular) — no celular NÃO existe cabo USB para o Zenith. A porta especial "BLE"
#  (ou "BLE:NomeDoDispositivo") manda a linha por Bluetooth LE, pelo plugin Android. É só IDA:
#  o plugin escreve no dispositivo e não lê de volta, então nunca há resposta do aparelho.
#  No PC nada muda: continua a porta serial de sempre.
# ============================================================

import threading

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

NOME_BLE_PADRAO = "Zenith_Carrinho"     # igual ao NOME_BT do firmware e a skills/carrinho.py (um teste confere)


def _plataforma_android():
    """A plataforma do celular, ou None fora dele (ou se o jeito de achá-la falhar)."""
    try:
        from brain import zenith_plataforma
        if zenith_plataforma.detectar() != "android":
            return None
        return zenith_plataforma.obter()
    except Exception:
        return None


def _ble_liberado() -> bool:
    plat = _plataforma_android()
    return bool(plat is not None and plat.tem("ble"))


def nome_ble_da_porta(porta: str):
    """'BLE' -> 'Zenith_Carrinho' · 'BLE:Outro_Nome' -> 'Outro_Nome' · qualquer outra coisa (COM3, /dev/ttyUSB0) -> None."""
    t = (porta or "").strip()
    if t.lower() == "ble":
        return NOME_BLE_PADRAO
    if t.lower().startswith("ble:") and t[4:].strip():
        return t[4:].strip()
    return None


class ZenithHardware:
    def __init__(self):
        self.connection = None
        self.port = None
        self.ble_nome = None            # preenchido quando a "porta" é Bluetooth (só no celular)
        self.lock = threading.Lock()

    def is_available(self) -> bool:
        return serial is not None or _ble_liberado()

    def list_ports(self) -> list:
        portas = [p.device for p in serial.tools.list_ports.comports()] if serial is not None else []
        if _ble_liberado():
            portas.append("BLE")
        return portas

    def connect(self, port: str, baud: int = 9600) -> tuple:
        nome_ble = nome_ble_da_porta(port)
        if nome_ble is not None:
            if _plataforma_android() is None:
                return False, ("Bluetooth (porta BLE) só existe no celular. No PC use a porta serial, "
                               "por exemplo COM3.")
            if not _ble_liberado():
                return False, "Este celular não liberou o Bluetooth LE para o Zenith."
            with self.lock:
                self._fechar_serial()
                self.port = port
                self.ble_nome = nome_ble
            return True, (f"Pronto para falar com '{nome_ble}' por Bluetooth. A conexão abre no primeiro comando; "
                          "o celular só envia, não recebe resposta.")
        if serial is None:
            if _plataforma_android() is not None:
                return False, ("No celular não há cabo USB para o Zenith. Para o carrinho, use a porta BLE "
                               "(Bluetooth); para a TFT, o Wi-Fi.")
            return False, "Biblioteca 'pyserial' não instalada. Rode: pip install pyserial"
        with self.lock:
            self.ble_nome = None
            try:
                if self.connection and self.connection.is_open:
                    self.connection.close()
                self.connection = serial.Serial(port, baud, timeout=2)
                self.port = port
                return True, f"Conectado em {port} @ {baud} baud."
            except Exception as e:
                self.connection = None
                return False, f"Erro ao conectar em {port}: {e}"

    def _fechar_serial(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
        self.connection = None

    def disconnect(self):
        with self.lock:
            self._fechar_serial()
            self.port = None
            self.ble_nome = None

    def is_connected(self) -> bool:
        return bool(self.ble_nome) or bool(self.connection and self.connection.is_open)

    def send(self, data: str) -> tuple:
        """Manda uma linha de texto e espera até 1.5s por resposta.
        Não trava pra sempre se o Arduino não responder nada."""
        with self.lock:
            if not self.is_connected():
                return False, "Nenhuma porta serial conectada — conecte primeiro."
            if self.ble_nome:
                plat = _plataforma_android()
                if plat is None:
                    return False, "Erro ao enviar por Bluetooth: o Bluetooth só existe no celular."
                try:
                    plat.ble_enviar(self.ble_nome, (data.strip() + "\n").encode("utf-8"))
                    return True, "(comando enviado por Bluetooth; o celular só envia, não recebe resposta)"
                except Exception as e:
                    return False, f"Erro ao enviar por Bluetooth: {e}"
            try:
                self.connection.write((data.strip() + "\n").encode("utf-8"))
                self.connection.timeout = 1.5
                resposta = self.connection.readline().decode("utf-8", errors="replace").strip()
                return True, resposta or "(comando enviado, sem resposta do dispositivo)"
            except Exception as e:
                return False, f"Erro ao enviar pela serial: {e}"
