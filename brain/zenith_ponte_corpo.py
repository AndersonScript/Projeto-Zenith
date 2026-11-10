"""Zenith — PONTE ATÉ O ANDROID, pelo Corpo (v1.11, port celular).

O Cérebro (Python) precisa de microfone, voz, câmera... que só o Android tem. O Corpo (Godot) já está ligado ao
Cérebro por um WebSocket. Em vez de abrir um segundo canal, o Cérebro PEDE pelo mesmo WebSocket e o Corpo repassa
ao plugin Android (ver `body/zenith/ponte_android.gd`).

    Cérebro  --{"action":"ponte_chamar","id":"p7","nome":"tts.sintetizar","args":{...}}-->  Corpo  -->  plugin Android
    Cérebro  <--{"action":"ponte_resposta","id":"p7","resposta":{"ok":true}}-------------  Corpo  <--  plugin Android
    Cérebro  <--{"action":"ponte_evento","evento":"mic.quadro","dados":{"pcm16":"..."}}--  (microfone, 10x por segundo)
    Cérebro  <--{"action":"ponte_evento","evento":"capacidades","dados":{"lista":[...]}}-  (o que o aparelho TEM)

Esta classe é o objeto `ponte` que o `AndroidPlataforma` espera: `chamar`, `assinar`, `desassinar`.

Regras (cada uma existe por um motivo real do código atual)
-----------------------------------------------------------
* `chamar` BLOQUEIA até a resposta (ou o tempo esgotar), então NUNCA pode rodar na thread do WebSocket — é nela que as
  respostas chegam (`ZenithBridge._handler` chama o `on_message` ali mesmo; foi por isso que o `approval_response` foi
  para uma thread na v26). Se alguém tentar, levanta erro na hora em vez de travar o Corpo inteiro.
* `capacidades.listar` NUNCA vai à rede: é respondida do que o Corpo já anunciou. Assim `tem("microfone")` pode ser
  perguntado de dentro de um handler do WebSocket sem travar nada.
* Corpo desconectou -> toda chamada pendente falha na hora com uma frase em português, e as capacidades são esquecidas.
* Resposta que chega depois do tempo esgotado é ignorada (não confunde a chamada seguinte).
"""
from __future__ import annotations

import itertools
import threading

# Operações lentas por natureza (transcrever áudio, sintetizar voz, abrir câmera) ganham mais tempo que o padrão.
TEMPOS = {"stt.transcrever": 120.0, "tts.sintetizar": 45.0, "camera.capturar": 20.0, "tela.capturar": 60.0,   # tela: a pessoa lê a janela do Android
          "video.info": 20.0, "video.quadros": 110.0}                                                        # quadros: o plugin desiste em 90 s
TEMPO_PADRAO = 10.0


class PonteCorpo:
    def __init__(self, enviar, tempo_padrao: float = TEMPO_PADRAO):
        """`enviar(dict)` entrega uma mensagem ao Corpo (na prática: `bridge.send`)."""
        self._enviar = enviar
        self._tempo_padrao = float(tempo_padrao)
        self._lock = threading.RLock()
        self._pendentes: dict = {}
        self._assinantes: dict = {}
        self._contador = itertools.count(1)
        self._capacidades = None            # None = o Corpo ainda não anunciou
        self._conectado = False
        self._thread_receptora = None       # a thread (objeto, não o número: números de threads mortas são reaproveitados)
                                            # em que as mensagens do Corpo chegam

    # ---- estado da conexão ---------------------------------------------------------------------------
    def definir_conectado(self, conectado: bool) -> None:
        with self._lock:
            mudou = conectado != self._conectado
            self._conectado = bool(conectado)
            if not conectado:
                self._capacidades = None
                for p in self._pendentes.values():
                    p["resposta"] = {"ok": False, "erro": "O Corpo desconectou antes de responder."}
                    p["evento"].set()
                self._pendentes.clear()
        if conectado and mudou:
            try:
                self._enviar({"action": "ponte_pedir_capacidades"})       # o Corpo responde com o evento "capacidades"
            except Exception:
                pass

    @property
    def conectado(self) -> bool:
        return self._conectado

    # ---- chamadas (Cérebro -> Android) ------------------------------------------------------------------
    def chamar(self, nome: str, **args):
        if nome == "capacidades.listar":
            with self._lock:
                if self._capacidades is None:
                    raise RuntimeError("O Corpo ainda não anunciou o que este aparelho tem.")
                return list(self._capacidades)
        if threading.current_thread() is self._thread_receptora:
            raise RuntimeError(f"'{nome}' bloqueia até a resposta e não pode ser pedido de dentro da thread do "
                               f"WebSocket (travaria o Corpo). Faça o pedido numa thread à parte.")
        with self._lock:
            if not self._conectado:
                raise RuntimeError("O Corpo (app Android) não está conectado.")
            id_ = f"p{next(self._contador)}"
            pendente = {"evento": threading.Event(), "resposta": None}
            self._pendentes[id_] = pendente
        try:
            self._enviar({"action": "ponte_chamar", "id": id_, "nome": nome, "args": args})
        except Exception as e:
            with self._lock:
                self._pendentes.pop(id_, None)
            raise RuntimeError(f"Não consegui falar com o Corpo: {e}") from e
        limite = TEMPOS.get(nome, self._tempo_padrao)
        if not pendente["evento"].wait(limite):
            with self._lock:
                self._pendentes.pop(id_, None)
            raise TimeoutError(f"O app Android não respondeu a '{nome}' em {limite:.0f} s.")
        return pendente["resposta"]

    # ---- eventos (Android -> Cérebro) --------------------------------------------------------------------
    def assinar(self, evento: str, funcao) -> None:
        with self._lock:
            self._assinantes.setdefault(evento, []).append(funcao)

    def desassinar(self, evento: str, funcao) -> None:
        with self._lock:
            if funcao in self._assinantes.get(evento, []):
                self._assinantes[evento].remove(funcao)

    # ---- mensagens que chegam do Corpo ---------------------------------------------------------------------
    def tratar_mensagem(self, data: dict) -> bool:
        """Chame PRIMEIRO no roteador do Cérebro. True = a mensagem era da ponte (e já foi tratada)."""
        acao = data.get("action") if isinstance(data, dict) else None
        if acao not in ("ponte_resposta", "ponte_evento"):
            return False
        self._thread_receptora = threading.current_thread()
        if acao == "ponte_resposta":
            with self._lock:
                pendente = self._pendentes.pop(str(data.get("id", "")), None)
            if pendente is not None:                  # resposta atrasada (o tempo já esgotou): ignora
                resposta = data.get("resposta")
                pendente["resposta"] = resposta if resposta is not None else {"ok": False, "erro": "Resposta vazia do app Android."}
                pendente["evento"].set()
            return True
        evento, dados = str(data.get("evento", "")), data.get("dados") or {}
        if evento == "capacidades":
            with self._lock:
                self._capacidades = [str(c) for c in (dados.get("lista") or [])]
        with self._lock:
            funcoes = list(self._assinantes.get(evento, []))
        for f in funcoes:
            try:
                f(dados)
            except Exception:
                pass                                   # um assinante com defeito não pode derrubar o WebSocket
        return True
