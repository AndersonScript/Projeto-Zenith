# -*- coding: utf-8 -*-
"""Habilidade do Zenith: andar o carrinho (ESP32-S3 -> Uno -> 4 motores).

Fala DIRETO com o carrinho pela rede dele. Nao precisa do painel
(tools/carrinho_painel.py) nem de Bluetooth para funcionar — o painel serve
so para a pagina no navegador.

Ordem de procura, da mais rapida para a ultima opcao:
  1) o IP que ja foi salvo em config/carrinho.json
  2) o IP que voce mandar agora:  "ip 192.168.68.126"
  3) o proprio carrinho avisando onde esta (UDP 7778, a cada 3 s)
  4) 192.168.4.1 (a rede propria dele, Zenith_Carrinho)
  5) de ULTIMO caso, o cabo USB (serial) — se a rede nao responder

Exemplos do que se escreve no chat:
    "Zenith, anda para frente 5 segundos"
    "vai pra tras 2 s, gira pra direita 1 s e volta pra frente 3"
    "para o carrinho"
    "faz careta de feliz no carrinho"
    "onde esta o carrinho"      (diagnostico: IP, rede, tela, Bluetooth)
    "carrinho ip 192.168.68.126" (grava o IP de uma vez por todas)

Ele so ENTREGA o pedido. Quem conta o tempo e para e o proprio carrinho.
"""

from __future__ import annotations

import json
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

try:
    from brain.zenith_settings import BASE_DIR, CONFIG_DIR
except Exception:                                    # roda solto, fora do Zenith
    BASE_DIR = Path(__file__).resolve().parent.parent
    CONFIG_DIR = BASE_DIR / "config"

ARQUIVO = Path(CONFIG_DIR) / "carrinho.json"

TIMEOUT = 2.5           # uma resposta do carrinho na rede local e instantanea
ESPERA_DESCOBERTA = 3.0  # o carrinho avisa a cada 3 s; 3 s bastam na maioria das vezes
PORTA_DESCOBERTA = 7778
AP_PADRAO = "192.168.4.1"

MAX_PASSOS = 6          # o Uno tem fila de 6
MAX_S = 10.0            # um passo nunca passa de 10 s
VEL = 140

_DIRECOES = {
    "frente": "F", "para frente": "F", "pra frente": "F", "avancar": "F",
    "avanca": "F", "anda": "F", "andar": "F",
    "tras": "B", "para tras": "B", "pra tras": "B", "re": "B",
    "reverter": "B", "voltar": "B", "recuar": "B",
    "esquerda": "L", "para esquerda": "L", "pra esquerda": "L", "gira esquerda": "L",
    "direita": "R", "para direita": "R", "pra direita": "R", "gira direita": "R",
}

_NUMEROS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}

_ROSTOS = ("normal", "feliz", "pensando", "falando")


# ------------------------------------------------------------------ utilidades
def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c)).lower().strip()


def _cfg() -> dict:
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _salvar_cfg(**novos) -> dict:
    d = _cfg()
    d.update({k: v for k, v in novos.items() if v is not None})
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return d


def _ip_valido(t: str) -> bool:
    """Aceita 192.168.0.50 e carrinho.local. Recusa endereco da internet."""
    t = (t or "").strip().lower()
    if not t or " " in t:
        return False
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", t):
        partes = [int(p) for p in t.split(".")]
        if any(p > 255 for p in partes):
            return False
        return (partes[0] == 10 or partes[0] == 127
                or (partes[0] == 192 and partes[1] == 168)
                or (partes[0] == 172 and 16 <= partes[1] <= 31)
                or (partes[0] == 169 and partes[1] == 254))
    return t.endswith(".local")


# ------------------------------------------------------------------ rede
def _http(ip: str, caminho: str, cfg: dict, timeout: float = TIMEOUT):
    """(ok, corpo). Devolve o texto ou o JSON que o carrinho mandou."""
    chave = (cfg.get("chave") or "").strip()
    if chave:
        caminho += ("&" if "?" in caminho else "?") + "k=" + quote(chave)
    url = f"http://{ip}{caminho}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            corpo = r.read().decode("utf-8", "replace")
            try:
                return True, json.loads(corpo)
            except ValueError:
                return True, corpo.strip()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "o carrinho recusou a chave (confira 'chave' em config/carrinho.json)"
        return False, f"o carrinho respondeu {e.code}"
    except urllib.error.URLError as e:
        motivo = getattr(e, "reason", e)
        return False, f"sem resposta ({motivo})"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _descobrir(tempo: float = ESPERA_DESCOBERTA):
    """Escuta o aviso do carrinho (UDP 7778) e devolve o IP dele, ou ''."""
    fim = time.time() + tempo
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PORTA_DESCOBERTA))
        s.settimeout(0.5)
        while time.time() < fim:
            try:
                dados, origem = s.recvfrom(256)
            except socket.timeout:
                continue
            texto = dados.decode("utf-8", "replace").strip()
            if not texto.startswith("ZENITH-CARRINHO"):
                continue
            partes = texto.split()
            ip = partes[2] if len(partes) > 2 else origem[0]
            if _ip_valido(ip) and ip != AP_PADRAO:
                return ip
            return origem[0] if _ip_valido(origem[0]) else ""
        return ""
    except OSError:
        return ""
    finally:
        s.close()


def _achar(forcado: str = "") -> tuple:
    """(ip, como_achei) — '' em ip quando nada respondeu."""
    cfg = _cfg()

    candidatos = []
    if forcado:
        candidatos.append((forcado, "o IP que voce mandou"))
    if cfg.get("ip") and cfg.get("ip") != forcado:
        candidatos.append((cfg["ip"], "o IP salvo"))
    candidatos.append((AP_PADRAO, "a rede propria do carrinho"))

    for ip, como in candidatos:
        ok, _ = _http(ip, "/status", cfg)
        if ok:
            if cfg.get("ip") != ip:
                _salvar_cfg(ip=ip)
            return ip, como

    ip = _descobrir()
    if ip:
        ok, _ = _http(ip, "/status", cfg)
        if ok:
            _salvar_cfg(ip=ip)
            return ip, "ele avisou onde esta na rede (UDP)"

    return "", ""


NOME_BLE = "Zenith_Carrinho"      # igual ao NOME_BT do firmware (carrinho_esp32s3.ino)


def _ble_do_celular(linhas: list):
    """v1.14 (port celular): no celular NÃO há cabo USB para o Zenith; o último recurso é o Bluetooth LE (Nordic UART).
    Devolve (ok, mensagem) mandando as linhas pelo plugin Android, ou None fora do celular (aí vale o cabo)."""
    try:
        from brain import zenith_plataforma
        if zenith_plataforma.detectar() != "android":
            return None
        plat = zenith_plataforma.obter()
    except Exception:
        return None
    if not plat.tem("ble"):
        return False, "este celular não liberou o Bluetooth LE para o Zenith"
    try:
        for linha in linhas:
            plat.ble_enviar(NOME_BLE, (linha + "\n").encode("utf-8"))
        return True, "Bluetooth"
    except Exception as e:
        return False, f"Bluetooth: {e}"


def _serial(cfg: dict, linhas: list) -> tuple:
    """ULTIMO caso: manda pelo cabo USB (ou, no celular, por Bluetooth). (ok, mensagem)."""
    ble = _ble_do_celular(linhas)
    if ble is not None:
        return ble
    try:
        import serial                     # pyserial (ja vem com o Zenith)
        import serial.tools.list_ports
    except Exception:
        return False, "pyserial nao esta instalado"

    porta = (cfg.get("porta_serial") or "").strip()
    if not porta:
        achadas = [p.device for p in serial.tools.list_ports.comports()
                   if "USB" in (p.description or "").upper() or "CP210" in (p.description or "").upper()
                   or "CH340" in (p.description or "").upper()]
        porta = achadas[0] if achadas else ""
    if not porta:
        return False, "nenhuma porta USB do carrinho encontrada"

    try:
        with serial.Serial(porta, 115200, timeout=1, write_timeout=1) as s:
            time.sleep(0.3)
            for linha in linhas:
                s.write((linha + "\n").encode("utf-8"))
                s.flush()
            _salvar_cfg(porta_serial=porta)
        return True, porta
    except Exception as e:
        return False, f"{type(e).__name__} na {porta}: {e}"


# ------------------------------------------------------------------ texto
def _segundos(trecho: str) -> float:
    """Acha o tempo em segundos no trecho: '5', '5s', '5 segundos', 'meio segundo', 'dois'."""
    t = _sem_acento(trecho)
    if "meio segundo" in t:
        return 0.5
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(s\b|seg|segundo|segundos)?", t)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return 1.0
    for palavra, valor in _NUMEROS.items():
        if re.search(rf"\b{palavra}\b", t):
            return float(valor)
    return 1.0


def _direcao(trecho: str):
    t = _sem_acento(trecho)
    for chave in sorted(_DIRECOES, key=len, reverse=True):   # "para frente" ganha de "frente"
        if chave in t:
            return _DIRECOES[chave]
    return None


def _ajudar() -> str:
    return (
        "Nao entendi o pedido para o carrinho.\n"
        "Use, por exemplo: 'frente 5', 'tras 2', 'esquerda 1', 'parar', "
        "'rosto feliz', 'onde esta o carrinho' ou 'frente 3 ; direita 1 ; frente 2'."
    )


def _nao_achei(dica: str = "") -> str:
    cfg = _cfg()
    linhas = [
        "Nao achei o carrinho na rede." + (f" ({dica})" if dica else ""),
        "O que conferir, nesta ordem:",
        "  1. o carrinho esta ligado e a telinha mostra um IP?",
        "  2. o PC esta no MESMO Wi-Fi que ele?",
        f"  3. o IP salvo aqui e {cfg.get('ip') or 'nenhum'} — se mudou, diga: "
        "\"carrinho ip 192.168.x.x\".",
        "  4. Windows: permita o Zenith na rede particular (o firewall bloqueia isso).",
    ]
    if (cfg.get("porta_serial") or ""):
        linhas.append(f"  5. ultimo recurso: cabo USB em {cfg['porta_serial']} (diga \"carrinho cabo\").")
    else:
        linhas.append("  5. ultimo recurso: cabo USB no PC (diga \"carrinho cabo\").")
    return "\n".join(linhas)


# ------------------------------------------------------------------ acoes
def _entregar(pedidos: list, cfg: dict) -> str:
    """pedidos: lista de linhas do protocolo ('F 5000 140', 'S', 'ROSTO feliz')."""
    ip, como = _achar()
    if ip:
        entregues = []
        for linha in pedidos:
            partes = linha.split()
            if partes[0] == "ROSTO":                     # texto puro, sem numeração
                caminho = f"/cmd?c={quote(linha)}"
            else:
                caminho = f"/cmd?c={quote(partes[0])}"
                if len(partes) > 1:
                    caminho += f"&t={quote(partes[1])}"
                if len(partes) > 2:
                    caminho += f"&v={quote(partes[2])}"
            ok, corpo = _http(ip, caminho, cfg)
            if not ok:
                return (f"o carrinho parou de responder no meio da fila ({corpo}). "
                        f"Ele executa o que ja recebeu e para sozinho.")
            entregues.append(linha)
        return f"Wi-Fi {ip} ({como})."

    ok, info = _serial(cfg, pedidos)
    if ok:
        return (f"cabo USB {info} (a rede nao respondeu). Se a placa reiniciar ao abrir a porta, "
                "e o reset do USB — nao e defeito.")
    return _nao_achei(info)


def rodar(args: str = "") -> str:
    texto = _sem_acento(args)
    cfg = _cfg()

    if not texto:
        return _ajudar()

    # ---- apontar o IP na mao: "ip 192.168.68.126" / "carrinho ip ..." ----
    m = re.search(r"\bip\s+([a-z0-9\.\-]+)", texto)
    if m:
        ip = m.group(1).strip(".")
        if not _ip_valido(ip):
            return ("Esse endereco nao serve: so aceito endereco de rede local "
                    "(ex.: 192.168.68.126). Endereco da internet eu nao uso.")
        ok, corpo = _http(ip, "/status", cfg)
        if not ok:
            _salvar_cfg(ip=ip)
            return (f"guardei o IP {ip}, mas ele nao respondeu agora ({corpo}).\n"
                    "Ligue o carrinho e confira se o PC esta no mesmo Wi-Fi; depois peca "
                    "\"onde esta o carrinho\".")
        _salvar_cfg(ip=ip)
        return f"guardei o IP {ip}. Ele respondeu: {_resumo(corpo)}"

    # ---- diagnostico ----
    if any(p in texto for p in ("onde", "status", "diagnostic", "checkup", "check-up")):
        ip, como = _achar()
        if not ip:
            return _nao_achei("nem Wi-Fi, nem descoberta automatica")
        ok, corpo = _http(ip, "/status", cfg)
        if not ok:
            return f"achei em {ip} ({como}), mas ele nao respondeu: {corpo}"
        return (f"carrinho em {ip} ({como}).\n{_resumo(corpo)}\n"
                f"quadro/rosto: porta 7777 · comandos: http://{ip}/cmd")

    # ---- cabo, na mao ----
    if any(p in texto for p in ("cabo", "serial", "usb")):
        if "frente" in texto or "tras" in texto:
            pass
        else:
            ok, info = _serial(cfg, ["PING"])
            return (f"cabo USB: {info}" if ok else f"pelo cabo tambem nao deu: {info}")

    # ---- parar ----
    if any(p in texto for p in ("parar", "pare", "para o carrinho", "stop", "emergencia")):
        ip, como = _achar()
        if ip:
            ok, corpo = _http(ip, "/parar", cfg)
            if ok:
                return "carrinho parado (fila apagada)."
            return f"nao consegui parar por Wi-Fi ({corpo}). {_nao_achei()}"
        ok, info = _serial(cfg, ["S"])
        if ok:
            return f"parei pelo cabo USB ({info})."
        return "NAO consegui falar com o carrinho para parar.\n" + _nao_achei(info)

    # ---- rosto ----
    m = re.search(r"rosto\s+(\w+)", texto)
    if m:
        estado = m.group(1) if m.group(1) in _ROSTOS else "normal"
        r = _entregar([f"ROSTO {estado}"], cfg)
        return f"careta trocada no carrinho: {estado}. ({r})"

    # ---- passos: "frente 5 ; direita 1 ; frente 2" ----
    partes = [p for p in re.split(r"[;,]|\be\s+depois\b|\bdepois\b|\be\b", texto) if p.strip()]
    passos, avisos = [], []
    for parte in partes:
        d = _direcao(parte)
        if not d:
            continue
        s = min(MAX_S, max(0.1, _segundos(parte)))
        passos.append((d, s))

    if not passos:
        return _ajudar()

    if len(passos) > MAX_PASSOS:
        passos = passos[:MAX_PASSOS]
        avisos.append(f"(cortei em {MAX_PASSOS} passos: e o limite do carrinho)")

    nomes = {"F": "frente", "B": "tras", "L": "esquerda", "R": "direita"}
    pedidos = [f"{d} {int(round(s * 1000))} {VEL}" for d, s in passos]
    resposta = _entregar(pedidos, cfg)

    feitos = ", ".join(f"{nomes[d]} {s:g} s" for d, s in passos)
    if resposta.startswith(("Wi-Fi", "cabo USB")):
        linhas = [f"entreguei ao carrinho: {feitos} — {resposta}",
                  "Ele conta o tempo e para sozinho — nao fica andando se a conexao cair."]
    else:
        linhas = [resposta]
    return "\n".join(linhas + avisos)


def _resumo(corpo) -> str:
    """Transforma o /status do carrinho em uma frase legivel."""
    if not isinstance(corpo, dict):
        return str(corpo)[:200]
    pedacos = [f"versao {corpo.get('versao', '?')}"]
    if corpo.get("wifi"):
        pedacos.append(f"Wi-Fi {corpo['wifi']} ({corpo.get('ip') or 'sem IP'})")
    elif corpo.get("ap"):
        pedacos.append("na rede propria dele (192.168.4.1)")
    pedacos.append("tela " + ("ok" if corpo.get("tela") else "sem tela"))
    pedacos.append("Zenith " + ("conectado" if corpo.get("zenith") else "nao conectado"))
    if corpo.get("ble"):
        pedacos.append("Bluetooth " + ("conectado" if corpo["ble"] else "livre"))
    if corpo.get("chave"):
        pedacos.append("exige chave")
    return " · ".join(pedacos)
