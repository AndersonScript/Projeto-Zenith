# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_bridge.py — A Ponte (Cérebro ↔ Corpo).
#  Protocolo v2: chat_message | sync_history | update_config |
#                speak | expression | mouth | transparency | action
# ============================================================

import asyncio
import json
import logging
import threading
import queue
import websockets

# ---------- Protocolo v2 da Ponte (documento vivo) ----------
# Cérebro -> Corpo:
#   {"action": "chat_message",  "sender": "user"|"ai", "text": str}
#   {"action": "sync_history",  "history": [{"sender","text"}, ...]}
#   {"action": "speak",         "text": str}
#   {"action": "expression",    "type": str}
#   {"action": "mouth",         "speaking": bool}
#   {"action": "transparency",  "value": float}
#   {"action": "do",            "name": "wave"|...}
# Corpo -> Cérebro:
#   {"action": "chat",          "text": str}
#   {"action": "update_config", ...campos...}
#   {"action": "request_sync"}   (pede histórico completo)


class ZenithBridge:
    def __init__(self, host="localhost", port=8765):
        self.godot_client = None
        self.loop = None
        self.is_connected = False
        self.on_message = None        # callback (dict) -> None
        self.on_state_change = None   # callback (bool conectado) -> None
        self._outbox = queue.Queue()  # fila thread-safe de saída

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        threading.Thread(target=self._outbox_worker, daemon=True).start()

    # ---------- Servidor ----------
    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_server())
        except Exception as e:
            print(f"[Zenith] Ponte caiu: {e}")

    async def _start_server(self):
        # v1.9 — o log do usuário enchia de traceback de 20 linhas quando QUALQUER programa
        # abria e fechava uma conexão TCP na porta 8765 sem falar WebSocket (antivírus, um
        # scanner de portas, um `nc` de teste). Não é defeito do Zenith e não há o que
        # consertar: só o barulho assusta quem lê o log. O handshake que falha é silenciado
        # aqui; os erros do NOSSO código continuam aparecendo com traceback completo.
        logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
        logging.getLogger("websockets.asyncio.server").setLevel(logging.CRITICAL)
        try:
            # v1.8 — `max_size` padrão do websockets é 1 MiB: um quadro do TFT ou uma
            # imagem enviada pelo Corpo maior que isso faria o servidor FECHAR a conexão
            # (o Corpo só veria "desconectado"). O teto aqui é folgado de propósito.
            # Escuta em 0.0.0.0 para permitir conexão tanto do Godot do PC (localhost)
            # quanto do celular Android na mesma rede Wi-Fi.
            host = self.settings.get("websocket_host", "0.0.0.0") if hasattr(self, "settings") and isinstance(self.settings, dict) else "0.0.0.0"
            server = await websockets.serve(self._handler, host, 8765,
                                             ping_interval=20, ping_timeout=20,
                                             max_size=32 * 1024 * 1024)
        except OSError as e:
            # CORREÇÃO: antes o "Ponte ativa" era impresso ANTES de
            # confirmar que a porta abriu de verdade — se a porta 8765
            # já estivesse ocupada (uma instância antiga do Zenith ainda
            # rodando em segundo plano, por exemplo), a mensagem de
            # sucesso aparecia mesmo assim, e o motivo real do "não
            # conecta" ficava escondido lá embaixo no log, fácil de
            # não ver. Agora é impossível não perceber.
            print("=" * 60)
            print(f"[Zenith] ERRO: não consegui abrir a porta 8765 ({e}).")
            print("[Zenith] Isso quase sempre quer dizer que já tem OUTRA")
            print("[Zenith] instância do Zenith (ou um Godot antigo) rodando")
            print("[Zenith] em segundo plano. Feche TODOS os processos Zenith/")
            print("[Zenith] Godot abertos (verifique o Gerenciador de Tarefas)")
            print("[Zenith] e tente de novo.")
            print("=" * 60)
            return
        print("[Zenith] Ponte WebSocket ativa em ws://localhost:8765")
        async with server:
            await asyncio.Future()

    async def _handler(self, websocket):
        self.godot_client = websocket
        self._set_connected(True)
        try:
            async for message in websocket:
                # CORREÇÃO: antes, um erro dentro do callback (self.on_message)
                # caía no mesmo "except" do parse de JSON e virava a mensagem
                # enganosa "JSON inválido do Corpo" — foi assim que um bug real
                # (atributo não inicializado) ficou disfarçado de erro de JSON
                # por várias rodadas de teste. Agora as duas coisas são
                # tratadas separadamente, com traceback completo no erro real.
                try:
                    data = json.loads(message)
                except Exception as e:
                    print(f"[Zenith] Mensagem do Corpo não é JSON válido: {e}")
                    continue
                if self.on_message:
                    try:
                        self.on_message(data)
                    except Exception:
                        import traceback
                        print(f"[Zenith] ERRO processando mensagem do Corpo (ação: {data.get('action')}):")
                        traceback.print_exc()
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if self.godot_client is websocket:
                self.godot_client = None
                self._set_connected(False)

    def _set_connected(self, state: bool):
        self.is_connected = state
        print(f"[Zenith] Corpo {'conectado 🟢' if state else 'desconectado 🔴'}")
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception:
                # CORREÇÃO: isso engolia o erro em silêncio total — nem
                # "JSON inválido" enganoso, nada. Foi aqui que o
                # AttributeError original de verdade quebrava, e ficava
                # impossível de ver. Agora aparece com traceback completo.
                import traceback
                print("[Zenith] ERRO no callback de mudança de conexão:")
                traceback.print_exc()

    # ---------- Envio (thread-safe via fila) ----------
    def _outbox_worker(self):
        """Toda saída passa por esta fila — nenhuma thread pode
        corromper o event loop do asyncio."""
        while True:
            data = self._outbox.get()
            if self.loop and self.godot_client:
                asyncio.run_coroutine_threadsafe(self._send(json.dumps(data)), self.loop)

    async def _send(self, msg: str):
        if self.godot_client:
            try:
                await self.godot_client.send(msg)
            except Exception as e:
                print(f"[Zenith] Erro ao enviar: {e}")

    # ---------- API pública ----------
    def send(self, data: dict):
        try:                                    # v1.4 — sem emoji no chat (zenith_emoji.py); nunca pode travar o envio
            from brain import zenith_emoji
            data = zenith_emoji.limpar_mensagem(data)
        except Exception:
            pass
        self._outbox.put(data)

    def send_chat_message(self, sender: str, text: str):
        self.send({"action": "chat_message", "sender": sender, "text": text})

    def send_speak(self, text: str):
        self.send({"action": "speak", "text": text})

    def set_message_callback(self, callback):
        self.on_message = callback

    def set_state_callback(self, callback):
        self.on_state_change = callback