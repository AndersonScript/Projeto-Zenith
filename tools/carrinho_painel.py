#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Painel do carrinho do Zenith — sem cabo, pelo navegador.

    python tools/carrinho_painel.py            Bluetooth (sem cabo) — modo normal
    python tools/carrinho_painel.py --usb      pelo cabo (para testar)
    python tools/carrinho_painel.py --listar   mostra as portas COM
    python tools/carrinho_painel.py --procurar procura o carrinho no Bluetooth
    python tools/carrinho_painel.py --simular  testa o painel SEM o carrinho
    python tools/carrinho_painel.py --rede     aceita também o celular na mesma rede

Como as peças conversam:

    navegador -> este painel -> (Bluetooth BLE) -> ESP32-S3 -> (TX) -> Uno -> motores

O painel é o **dono único do rádio**: o Bluetooth do Windows aceita uma conexão só,
então nada mais no computador deve falar com o carrinho ao mesmo tempo. A habilidade
da Zenith (`skills/carrinho.py`) fala com este painel por HTTP, em 127.0.0.1.

Se o carrinho desligar, o painel fica tentando reconectar sozinho — ligue a bateria
depois de abrir o painel, sem pressa.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PORTA_WEB = 8777
BAUD = 115200
VEL_PADRAO = 140
DUR_MAX_MS = 10000
VEL_MAX = 150

NOME_BT = "Zenith_Carrinho"   # o firmware anuncia assim (o painel aceita hífen, sublinhado e o serviço)
UUID_SERVICO = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UUID_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # PC escreve
UUID_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # carrinho responde

_PISTAS_USB = ("usb jtag", "usb serial", "esp32", "espressif", "silicon labs", "wch", "usb-serial")


def _sem_separador(nome: str) -> str:
    """'Zenith-Carrinho', 'Zenith_Carrinho' e 'zenith carrinho' viram a mesma coisa."""
    return re.sub(r"[^a-z0-9]", "", (nome or "").lower())


_ACEITOS = {_sem_separador(NOME_BT), _sem_separador("Zenith-Carrinho"), _sem_separador("Zenith Carrinho")}


# ====================================================================== limites
def montar_comando(c: str, ms: int, vel: int) -> str:
    """Mesma conferência do ESP32 e do Uno (o carrinho nunca recebe fora dos limites)."""
    c = (c or "").upper()[:1]
    if c not in ("F", "B", "L", "R"):
        raise ValueError("comando inválido: use F, B, L ou R")
    ms = max(50, min(DUR_MAX_MS, int(ms)))
    vel = max(60, min(VEL_MAX, int(vel)))
    return f"{c} {ms} {vel}"


# ====================================================================== ligações
class Ligacao:
    """O que o servidor web precisa: enviar uma linha, saber o estado, fechar."""

    nome = "?"
    detalhe = ""

    def enviar(self, linha: str) -> str:
        raise NotImplementedError

    def status(self) -> dict:
        raise NotImplementedError

    def fechar(self) -> None:
        pass


class LigacaoSimulada(Ligacao):
    nome = "simulação"

    def __init__(self):
        self.ultimo = ""
        self.quando = 0.0

    def enviar(self, linha: str) -> str:
        self.ultimo, self.quando = linha, time.time()
        print(f"[simulado] -> {linha}", flush=True)
        return linha

    def status(self) -> dict:
        return {"ok": True, "transporte": self.nome, "porta": "(sem placa)",
                "conectado": True, "ultimo_envio": self.ultimo,
                "ha_segundos": round(time.time() - self.quando, 2) if self.quando else None}


class LigacaoUSB(Ligacao):
    nome = "cabo USB"

    def __init__(self, porta: str | None = None):
        try:
            import serial
        except ImportError:
            raise SystemExit("Falta o pyserial. Rode: pip install pyserial")
        self._trava = threading.Lock()
        self.porta = porta or self._achar_porta()
        try:
            self._serial = serial.Serial(self.porta, BAUD, timeout=0.2, write_timeout=2)
        except Exception as e:
            raise SystemExit(
                f"Não consegui abrir a porta {self.porta}: {e}\n"
                "  - O Monitor Serial do Arduino IDE está aberto? Feche.\n"
                "  - O cabo está bom? Veja --listar."
            )
        time.sleep(0.3)
        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass
        self.ultimo = ""
        self.quando = 0.0

    @staticmethod
    def portas() -> list:
        try:
            from serial.tools import list_ports
        except ImportError:
            return []
        return list(list_ports.comports())

    @classmethod
    def _achar_porta(cls) -> str:
        achadas = cls.portas()
        if not achadas:
            raise SystemExit(
                "Nenhuma porta serial encontrada.\n"
                "  Sem cabo é normal: rode sem --usb para usar o Bluetooth.\n"
                "  Quer conferir o cabo? python tools/carrinho_painel.py --listar"
            )
        for p in achadas:
            texto = f"{p.description} {p.manufacturer or ''} {p.product or ''}".lower()
            if any(pista in texto for pista in _PISTAS_USB):
                return p.device
        if len(achadas) == 1:
            return achadas[0].device
        lista = "\n".join(f"  {p.device}  {p.description}" for p in achadas)
        raise SystemExit("Não soube qual porta é o carrinho. Escolha com --porta:\n" + lista)

    def enviar(self, linha: str) -> str:
        with self._trava:
            self.ultimo, self.quando = linha, time.time()
            try:
                self._serial.write((linha + "\n").encode("ascii", "ignore"))
                self._serial.flush()
            except Exception as e:
                raise RuntimeError(f"falha na porta {self.porta}: {e}")
        return linha

    def status(self) -> dict:
        return {"ok": True, "transporte": self.nome, "porta": self.porta,
                "conectado": True, "ultimo_envio": self.ultimo,
                "ha_segundos": round(time.time() - self.quando, 2) if self.quando else None}

    def fechar(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass


class LigacaoBLE(Ligacao):
    """Bluetooth do carrinho. Um laço asyncio próprio, em segundo plano.

    O Windows aceita UMA conexão BLE por aparelho, então este objeto é o único que
    conversa com o carrinho. Se a bateria acabar ou ele sair de alcance, a thread
    `_vigiar` tenta de novo a cada 5 s — não precisa reiniciar o painel.
    """

    nome = "Bluetooth"

    def __init__(self, nome_bt: str = NOME_BT, espera_busca: float = 8.0):
        try:
            import bleak
        except ImportError:
            raise SystemExit(
                "Bluetooth precisa da biblioteca bleak (não é aplicativo, é uma biblioteca):\n"
                "    pip install bleak"
            )
        self._bleak = bleak
        self.alvo_nome = nome_bt
        self.espera_busca = espera_busca
        self.detalhe = nome_bt
        self._cliente = None
        self._conectado = False
        self._estado = "procurando"
        self._erro = ""
        self._trava = threading.Lock()
        self.ultimo = ""
        self.quando = 0.0
        self._parar = False
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        threading.Thread(target=self._vigiar, daemon=True).start()

    # -- utilidades
    def _rodar(self, coro, espera: float = 25.0):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(espera)

    def _recebi(self, _char, dados: bytearray) -> None:
        texto = bytes(dados).decode("utf-8", "ignore").strip()
        if texto:
            print(f"[BLE] <- {texto}", flush=True)

    def _caiu(self, _cliente) -> None:
        self._conectado = False
        self._estado = "caiu"
        print("[BLE] desconectou — tentando de novo", flush=True)

    # -- conexão
    async def _procurar(self):
        achados = await self._bleak.BleakScanner.discover(timeout=self.espera_busca, return_adv=True)
        if isinstance(achados, dict):
            pares = list(achados.values())                 # [(aparelho, anúncio), ...]
        else:
            pares = [(d, None) for d in achados]
        por_servico = None
        for d, anuncio in pares:
            nome = (getattr(d, "name", None) or "").strip()
            if not nome and anuncio is not None:
                nome = (getattr(anuncio, "local_name", None) or "").strip()
            # 1) nome igual (ignorando hífen/sublinhado/maiúsculas)
            if _sem_separador(nome) in _ACEITOS:
                return d
            # 2) nome estranho, mas anuncia o serviço Nordic UART: é o carrinho também
            uuids = [str(u).lower() for u in (getattr(anuncio, "service_uuids", None) or [])]
            if por_servico is None and UUID_SERVICO in uuids:
                por_servico = d
        return por_servico

    async def _conectar(self) -> None:
        self._estado = "procurando"
        alvo = await self._procurar()
        if alvo is None:
            raise RuntimeError(
                f"não achei '{self.alvo_nome}' — carrinho ligado? Bluetooth do PC ligado?"
            )
        cliente = self._bleak.BleakClient(alvo, disconnected_callback=self._caiu)
        await cliente.connect()
        try:
            await cliente.start_notify(UUID_TX, self._recebi)
        except Exception:
            pass                                   # resposta é enfeite; o comando é o que importa
        self._cliente = cliente
        self._conectado = True
        self._estado = "conectado"
        self._erro = ""
        print(f"[BLE] conectado em {getattr(alvo, 'address', alvo)}", flush=True)

    def _vigiar(self) -> None:
        while not self._parar:
            if not self._conectado:
                try:
                    self._rodar(self._conectar())
                except Exception as e:
                    self._erro = str(e)
                    self._estado = "sem conexão"
            time.sleep(5)

    # -- uso
    def enviar(self, linha: str) -> str:
        if not self._conectado or self._cliente is None:
            raise RuntimeError(self._erro or "Bluetooth sem conexão com o carrinho")
        with self._trava:
            try:
                self._rodar(self._cliente.write_gatt_char(
                    UUID_RX, linha.encode("ascii", "ignore"), response=True), espera=10)
            except Exception as e:
                self._conectado = False
                raise RuntimeError(f"não consegui enviar pelo Bluetooth: {e}")
            self.ultimo, self.quando = linha, time.time()
        return linha

    def status(self) -> dict:
        return {"ok": True, "transporte": self.nome, "porta": self.alvo_nome,
                "conectado": self._conectado, "estado": self._estado,
                "erro": self._erro, "ultimo_envio": self.ultimo,
                "ha_segundos": round(time.time() - self.quando, 2) if self.quando else None}

    def fechar(self) -> None:
        self._parar = True
        try:
            if self._cliente is not None:
                asyncio.run_coroutine_threadsafe(self._cliente.disconnect(), self._loop).result(5)
        except Exception:
            pass


# ====================================================================== página
PAGINA = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Carrinho do Zenith</title>
<style>
:root{--fundo:#12151c;--cartao:#1b202b;--texto:#e9edf5;--fraco:#93a0b5;--destaque:#f3a35c;--vermelho:#d94a4a}
*{box-sizing:border-box}
body{margin:0;padding:18px;background:var(--fundo);color:var(--texto);
     font-family:system-ui,Segoe UI,Roboto,sans-serif;text-align:center}
h1{font-size:1.15rem;margin:0 0 4px;font-weight:600}
.estado{font-size:.85rem;color:var(--fraco);margin-bottom:16px}
.estado b{color:var(--destaque)}
.pad{display:grid;gap:10px;justify-items:center;margin:0 auto 14px;max-width:420px}
.linha{display:flex;gap:10px}
button{font:inherit;font-size:1rem;cursor:pointer;border:0;border-radius:14px;
       background:var(--cartao);color:var(--texto);padding:16px 22px;min-width:96px;
       transition:transform .05s}
button:active{transform:scale(.96)}
button.parar{background:var(--vermelho);color:#fff;width:100%;max-width:420px;
             font-size:1.2rem;font-weight:700;letter-spacing:.04em;padding:18px;margin:6px 0 18px}
.tempo{margin-bottom:12px;color:var(--fraco);font-size:.9rem}
input{font:inherit;font-size:1rem;width:74px;padding:8px;border-radius:10px;border:0;
      background:var(--cartao);color:var(--texto);text-align:center}
.rosto{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;align-items:center;
       color:var(--fraco);font-size:.85rem;margin-bottom:10px}
.rosto button{padding:10px 14px;min-width:auto;font-size:.85rem}
.dica{color:var(--fraco);font-size:.8rem;margin:0 0 14px}
#log{min-height:46px;background:var(--cartao);border-radius:12px;padding:12px;
     font-size:.85rem;color:var(--destaque);max-width:420px;margin:0 auto;white-space:pre-wrap}
</style></head><body>
<h1>Carrinho do Zenith</h1>
<div class="estado" id="estado">procurando o carrinho...</div>

<div class="tempo">segundos: <input id="t" type="number" value="1" min="0.1" max="10" step="0.1"></div>

<div class="pad">
  <button onclick="m('F')">▲ frente</button>
  <div class="linha">
    <button onclick="m('L')">◀ esquerda</button>
    <button onclick="m('R')">direita ▶</button>
  </div>
  <button onclick="m('B')">▼ trás</button>
</div>

<button class="parar" onclick="p()">PARAR</button>

<div class="rosto">
  <span>rosto:</span>
  <button onclick="r('normal')">normal</button>
  <button onclick="r('feliz')">feliz</button>
  <button onclick="r('pensando')">pensando</button>
  <button onclick="r('falando')">falando</button>
</div>

<p class="dica">As setas do teclado também andam · espaço para parar</p>
<div id="log">pronto.</div>

<script>
const log = t => document.getElementById('log').textContent = t;
async function pedir(url){
  try{ const r = await fetch(url); const j = await r.json();
       log(j.ok ? (j.enviado ? 'entregue ao carrinho: ' + j.enviado : 'ok') : ('erro: ' + (j.erro||'?')));
       return j; }
  catch(e){ log('sem resposta do painel: ' + e); }
}
function m(c){
  const s = parseFloat(document.getElementById('t').value) || 1;
  pedir('/cmd?c=' + c + '&t=' + Math.round(s*1000));
}
function p(){ pedir('/parar'); }
function r(e){ pedir('/rosto?e=' + e); }

async function status(){
  try{
    const r = await fetch('/status'); const j = await r.json();
    const ok = j.conectado ? '' : ' (sem conexão)';
    document.getElementById('estado').innerHTML =
      j.transporte + ' <b>' + j.porta + '</b>' + ok +
      (j.ultimo_envio ? ' · último: <b>' + j.ultimo_envio + '</b>' : '') +
      (j.erro && !j.conectado ? '<br>' + j.erro : '');
  }catch(e){ document.getElementById('estado').textContent = 'painel fora do ar'; }
}
status(); setInterval(status, 2000);

document.addEventListener('keydown', ev => {
  const mapa = {ArrowUp:'F', ArrowDown:'B', ArrowLeft:'L', ArrowRight:'R'};
  if (mapa[ev.key]) { ev.preventDefault(); m(mapa[ev.key]); }
  else if (ev.key === ' ') { ev.preventDefault(); p(); }
});
</script></body></html>
"""


# ====================================================================== servidor
class Servidor(BaseHTTPRequestHandler):
    ligacao: Ligacao = None          # preenchido em main()

    def log_message(self, *args):
        pass

    def _responder(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados: dict, codigo: int = 200) -> None:
        self._responder(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")

    def do_GET(self) -> None:                                   # noqa: N802
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                self._responder(200, PAGINA.encode("utf-8"), "text/html; charset=utf-8")
                return

            if url.path == "/status":
                self._json(self.ligacao.status())
                return

            if url.path == "/cmd":
                c = (q.get("c") or [""])[0]
                t = int(float((q.get("t") or ["1000"])[0]))
                v = int(float((q.get("v") or [str(VEL_PADRAO)])[0]))
                linha = montar_comando(c, t, v)
                self.ligacao.enviar(linha)
                self._json({"ok": True, "enviado": linha})
                return

            if url.path == "/parar":
                self.ligacao.enviar("S")
                self._json({"ok": True, "enviado": "S"})
                return

            if url.path == "/rosto":
                e = (q.get("e") or ["normal"])[0].lower()
                if e not in ("normal", "feliz", "pensando", "falando"):
                    self._json({"ok": False, "erro": "rosto inválido"}, 400)
                    return
                self.ligacao.enviar("ROSTO " + e)
                self._json({"ok": True, "enviado": "ROSTO " + e})
                return

            self._json({"ok": False, "erro": "endereço desconhecido"}, 404)
        except ValueError as e:
            self._json({"ok": False, "erro": str(e)}, 400)
        except RuntimeError as e:
            self._json({"ok": False, "erro": str(e)}, 503)
        except Exception as e:                                   # nunca derruba o painel
            self._json({"ok": False, "erro": f"{type(e).__name__}: {e}"}, 500)


# ====================================================================== utilidades
def _ip_da_rede() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def procurar_bluetooth(nome: str = NOME_BT, segundos: float = 8.0) -> int:
    try:
        from bleak import BleakScanner
    except ImportError:
        print("Falta o bleak: pip install bleak")
        return 1

    async def _varrer():
        achados = await BleakScanner.discover(timeout=segundos, return_adv=True)
        if isinstance(achados, dict):
            achados = [par[0] for par in achados.values()]
        return achados

    print(f"procurando aparelhos por {segundos:.0f} s...")
    try:
        lista = asyncio.run(_varrer())
    except Exception as e:
        print(f"o Bluetooth do Windows não respondeu: {e}")
        print("  - o PC tem adaptador Bluetooth? (Gerenciador de Dispositivos)")
        print("  - em desktop comum é preciso um dongle USB Bluetooth 4.0 ou melhor")
        return 1
    if not lista:
        print("nenhum aparelho Bluetooth encontrado (o PC tem Bluetooth ligado?)")
        return 1
    achou = False
    for d in lista:
        nome_d = getattr(d, "name", None) or "(sem nome)"
        marca = "  <-- é o carrinho" if nome_d == nome else ""
        if nome_d == nome:
            achou = True
        print(f"  {nome_d}  {getattr(d, 'address', '')}{marca}")
    if not achou:
        print(f"\nnão apareceu nenhum '{nome}'."
              "\n  - o carrinho está ligado (power bank / bateria)?"
              "\n  - ele acabou de reiniciar? espere 5 s e procure de novo"
              "\n  - alguma outra coisa no PC já está conectada nele? (fecha o painel antigo)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Painel do carrinho do Zenith")
    p.add_argument("--usb", action="store_true", help="usar o cabo USB em vez do Bluetooth")
    p.add_argument("--porta", help="porta serial (ex.: COM7) quando usar --usb")
    p.add_argument("--ble-nome", default=NOME_BT, help="nome do carrinho no Bluetooth")
    p.add_argument("--listar", action="store_true", help="lista as portas seriais e sai")
    p.add_argument("--procurar", action="store_true", help="procura o carrinho no Bluetooth e sai")
    p.add_argument("--simular", action="store_true", help="testa o painel sem carrinho")
    p.add_argument("--rede", action="store_true", help="aceita também o celular na mesma rede")
    p.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    p.add_argument("--porta-web", type=int, default=PORTA_WEB)
    a = p.parse_args(argv)

    if a.listar:
        achadas = LigacaoUSB.portas()
        if not achadas:
            print("Nenhuma porta serial encontrada (sem cabo é normal — o modo normal é Bluetooth).")
            return 1
        for x in achadas:
            print(f"{x.device}  {x.description}")
        return 0

    if a.procurar:
        return procurar_bluetooth(a.ble_nome)

    if a.simular:
        ligacao: Ligacao = LigacaoSimulada()
    elif a.usb:
        ligacao = LigacaoUSB(a.porta)
    else:
        ligacao = LigacaoBLE(a.ble_nome)

    Servidor.ligacao = ligacao

    endereco = "0.0.0.0" if a.rede else "127.0.0.1"
    try:
        servidor = ThreadingHTTPServer((endereco, a.porta_web), Servidor)
    except OSError as e:
        print(f"não consegui usar a porta {a.porta_web}: {e}\n"
              "  já existe um painel aberto? feche o outro ou use --porta-web 8778")
        return 1

    url = f"http://127.0.0.1:{a.porta_web}/"
    print(f"carrinho por {ligacao.nome}" + (f" ({ligacao.detalhe})" if ligacao.detalhe else ""))
    print(f"painel em {url}")
    if a.rede:
        print(f"no celular (mesma rede): http://{_ip_da_rede()}:{a.porta_web}/")
    print("Ctrl+C para fechar")

    if not a.sem_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nfechando...")
    finally:
        servidor.server_close()
        ligacao.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
