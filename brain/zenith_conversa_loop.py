"""Zenith — CONVERSA POR VOZ sem apertar nada (v1.7).

Pedido do Anderson: "o processo de transcrever e de conversa não está nada fluido... a Shogers do Miyauti e a Rem falam de boa,
ela escuta e responde tranquilamente; o meu parece um chat comum, com dificuldades".
O que tornava travado: (1) era preciso apertar o microfone a cada frase; (2) o texto entendido ia para a caixa e esperava você apertar Enviar.

Este módulo é a máquina de estados que faz o ciclo sozinho (meio-duplex: ela nunca escuta enquanto fala, então não há eco):

    /conversa ligar -> escuta -> você para de falar -> transcreve -> ENVIA SOZINHA -> ela pensa e responde (voz) -> volta a escutar

Segurança (Pilar 1): só liga porque VOCÊ digitou /conversa ligar; o microfone passa pela mesma aprovação de sempre
(1ª vez da sessão), há aviso visível (`conversa_estado`), `/conversa desligar` e `/parar` encerram na hora, e depois de
MAX_VAZIOS tentativas sem ouvir nada ela se desliga sozinha (nunca fica escutando para sempre).
Só lógica pura: o microfone, o envio e o relógio entram por injeção (testável sem áudio).
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

MAX_VAZIOS = 3          # tentativas seguidas sem ouvir nada antes de desligar sozinha
ATRASO_S = 0.7          # respiro antes de reabrir o microfone (deixa o eco da voz dela morrer)

AJUDA = ("Conversa por voz ligada: pode falar, eu envio sozinha quando você parar e volto a escutar depois de responder. "
         "Para sair: /conversa desligar (ou /parar).")


def _agendar_thread(fn: Callable[[], None], atraso: float) -> None:
    t = threading.Timer(atraso, fn)
    t.daemon = True
    t.start()


class ConversaContinua:
    def __init__(self, abrir_microfone: Callable[[], None], avisar: Callable[[str], None],
                 pode_abrir: Optional[Callable[[], bool]] = None, agendar: Optional[Callable] = None,
                 atraso_s: float = ATRASO_S):
        self._abrir = abrir_microfone
        self._avisar = avisar
        self._pode_abrir = pode_abrir or (lambda: True)
        self._agendar = agendar or _agendar_thread
        self._atraso = atraso_s
        self.ligada = False
        self._vazios = 0
        self._esperando_resposta = False

    # ---- comandos do usuário
    def ligar(self) -> str:
        if self.ligada:
            return "A conversa por voz já está ligada. Para sair: /conversa desligar."
        self.ligada = True
        self._vazios = 0
        self._esperando_resposta = False
        self._avisar("ouvindo")
        self._abrir()
        return AJUDA

    def desligar(self, motivo: str = "") -> str:
        if not self.ligada:
            return "A conversa por voz já estava desligada."
        self.ligada = False
        self._esperando_resposta = False
        self._avisar("desligado")
        return "Conversa por voz desligada" + (f" ({motivo})." if motivo else ".")

    def status(self) -> str:
        return "Conversa por voz: LIGADA." if self.ligada else "Conversa por voz: desligada. Para ligar: /conversa ligar."

    # ---- eventos do ciclo
    def ao_transcrever(self, texto: str) -> str:
        """Devolve 'ignorar' (modo desligado: fluxo normal da caixa de texto), 'enviar' (manda sozinha),
        'vazio' (não entendeu; tenta de novo) ou 'desligou' (desistiu depois de várias tentativas)."""
        if not self.ligada:
            return "ignorar"
        if (texto or "").strip():
            self._vazios = 0
            self._esperando_resposta = True
            self._avisar("pensando")
            return "enviar"
        self._vazios += 1
        if self._vazios >= MAX_VAZIOS:
            self.desligar("não ouvi ninguém")
            return "desligou"
        self._agendar(self._reabrir, self._atraso)
        return "vazio"

    def ao_ficar_ocioso(self) -> None:
        """Ela terminou de falar (ou de responder por texto): hora de voltar a escutar."""
        if self.ligada and self._esperando_resposta:
            self._esperando_resposta = False
            self._agendar(self._reabrir, self._atraso)

    def _reabrir(self) -> None:
        if not self.ligada:
            return
        if not self._pode_abrir():                 # ainda falando/pensando: tenta de novo daqui a pouco
            self._agendar(self._reabrir, self._atraso)
            return
        self._avisar("ouvindo")
        self._abrir()
