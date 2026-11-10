"""
Zenith — PROGRESSO e AVISOS POPUP (v28).

O que o Anderson pediu (13/10/2026), vendo o "Adicionar avatar" levar minutos só com balões no chat:
"uma barrinha de download quando tiver baixando… que fale 'espere, tá carregando, não faça mais nada'… e não só mandar no
chat, manda avisos popup".

Duas mensagens pro Corpo (o Godot só DESENHA; quem decide é o Cérebro, como sempre):

  {"action": "progresso", "id", "titulo", "detalhe", "percentual", "bloqueia", "cancelavel", "timeout", "fim", "ok"}
      percentual: 0–100, ou -1 = "não sei quanto falta" (barra que vai e volta)
      bloqueia:   True  = tela escurecida com "aguarde, não faça mais nada" (importar avatar, reempacotar…)
                  False = só um painel discreto no canto (gerar imagem, editar vídeo… dá pra continuar conversando)
      cancelavel: True  = mostra o botão "Cancelar" (manda /parar pro Cérebro)
      timeout:    segundos sem NENHUMA atualização até o Corpo desistir de esperar e destravar a tela sozinho
                  (rede de segurança: se o Cérebro cair no meio, a janela NUNCA fica presa pra sempre)
      fim:        True  = fecha a barra (ok=False mostra como erro)
  {"action": "aviso", "texto", "tipo": "info"|"ok"|"erro", "segundos"}
      um aviso que aparece no canto da janela e some sozinho (toast) — complementa o chat, não o substitui.

`Progresso` é a forma de usar: abre, atualiza e SEMPRE fecha (mesmo se der erro no meio). O "batimento" (heartbeat)
reenvia o estado a cada poucos segundos enquanto o trabalho não manda novidade — assim uma etapa longa e muda (ex.: o
Godot importando um avatar por 3 minutos) não dispara o timeout do Corpo.
Lógica pura: só monta dicionários e chama `enviar(dict)`.
"""
from __future__ import annotations

import itertools
import threading
import time

_contador = itertools.count(1)

TIMEOUT_PADRAO = 60.0          # o Corpo destrava sozinho depois de tanto tempo sem ouvir o Cérebro
BATIMENTO_S = 5.0              # de quanto em quanto tempo o Cérebro reenvia "ainda estou trabalhando"


def msg_progresso(id_: str, titulo: str, detalhe: str = "", percentual: float = -1, bloqueia: bool = False,
                  fim: bool = False, ok: bool = True, cancelavel: bool = False, timeout: float = TIMEOUT_PADRAO) -> dict:
    try:
        p = float(percentual)
    except (TypeError, ValueError):
        p = -1.0
    p = -1.0 if p < 0 else min(p, 100.0)
    try:
        t = max(5.0, float(timeout))
    except (TypeError, ValueError):
        t = TIMEOUT_PADRAO
    return {"action": "progresso", "id": str(id_), "titulo": str(titulo), "detalhe": str(detalhe or ""),
            "percentual": p, "bloqueia": bool(bloqueia), "cancelavel": bool(cancelavel), "timeout": t,
            "fim": bool(fim), "ok": bool(ok)}


def msg_aviso(texto: str, tipo: str = "info", segundos: float = 5.0) -> dict:
    if tipo not in ("info", "ok", "erro"):
        tipo = "info"
    try:
        s = max(1.5, min(float(segundos), 30.0))
    except (TypeError, ValueError):
        s = 5.0
    return {"action": "aviso", "texto": str(texto), "tipo": tipo, "segundos": s}


class Progresso:
    """with Progresso(enviar, "Importando avatar", bloqueia=True) as p:  p.etapa("Copiando…", 10) ..."""

    INTERVALO_MIN = 0.15          # no máximo ~6 atualizações por segundo (o ffmpeg manda dezenas)

    def __init__(self, enviar, titulo: str, bloqueia: bool = False, detalhe: str = "", avisar_no_fim: bool = True,
                 cancelavel: bool = False, timeout: float = TIMEOUT_PADRAO, batimento: bool = True):
        self._enviar = enviar
        self.titulo = titulo
        self.bloqueia = bloqueia
        self.cancelavel = cancelavel
        self.timeout = timeout
        self.id = f"p{next(_contador)}"
        self._detalhe = detalhe
        self._pct = -1.0
        self._aberto = False
        self._fechado = False
        self._ultimo = 0.0
        self._avisar = avisar_no_fim
        self._lock = threading.Lock()
        self._batimento = batimento
        self._parar_bat = threading.Event()
        self._thread_bat = None

    # -------------------------------------------------------------------------------------------- envio
    def _msg(self, **extra) -> dict:
        return msg_progresso(self.id, self.titulo, self._detalhe, self._pct, self.bloqueia,
                             cancelavel=self.cancelavel, timeout=self.timeout, **extra)

    def _mandar(self, d: dict):
        try:
            self._enviar(d)
        except Exception as e:
            print(f"[Zenith/Progresso] {e}")

    def _bater(self):
        """Thread do batimento: reenvia o estado atual enquanto a barra estiver aberta."""
        while not self._parar_bat.wait(BATIMENTO_S):
            with self._lock:
                if self._fechado:
                    return
                self._mandar(self._msg())

    # -------------------------------------------------------------------------------------------- uso
    def comecar(self, detalhe: str = None, pct: float = None):
        with self._lock:
            if self._aberto:
                return self
            self._aberto = True
            if detalhe is not None:
                self._detalhe = detalhe
            if pct is not None:
                self._pct = pct
            self._mandar(self._msg())
            self._ultimo = time.monotonic()
            if self._batimento:
                self._thread_bat = threading.Thread(target=self._bater, daemon=True)
                self._thread_bat.start()
        return self

    def etapa(self, detalhe: str = None, pct: float = None, forcar: bool = False):
        with self._lock:
            if self._fechado:
                return
            if detalhe is not None:
                self._detalhe = detalhe
            if pct is not None:
                self._pct = pct
            agora = time.monotonic()
            if not self._aberto:
                self._aberto = True
                forcar = True
                if self._batimento and self._thread_bat is None:
                    self._thread_bat = threading.Thread(target=self._bater, daemon=True)
                    self._thread_bat.start()
            if not forcar and agora - self._ultimo < self.INTERVALO_MIN and (self._pct is None or self._pct < 100):
                return
            self._ultimo = agora
            self._mandar(self._msg())

    def callback(self):
        """Função `(pct, detalhe=None)` pra passar pra quem reporta progresso (ffmpeg, importadores…)."""
        def _cb(pct, detalhe=None):
            self.etapa(detalhe, pct)
        return _cb

    def fim(self, ok: bool = True, detalhe: str = "", aviso: str = None):
        with self._lock:
            if self._fechado:
                return
            self._fechado = True
            self._parar_bat.set()
            if detalhe:
                self._detalhe = detalhe
            if ok:
                self._pct = 100
            self._mandar(self._msg(fim=True, ok=ok))
            if aviso is None and self._avisar:
                aviso = (f"{self.titulo}: pronto." if ok else f"{self.titulo}: deu erro.")
            if aviso:
                self._mandar(msg_aviso(aviso, "ok" if ok else "erro"))

    def __enter__(self):
        return self.comecar()

    def __exit__(self, tipo, valor, tb):
        if not self._fechado:
            self.fim(ok=tipo is None, detalhe=("" if tipo is None else f"{tipo.__name__}: {valor}"[:200]))
        return False


class Nulo:
    """Mesma interface do Progresso, sem fazer nada (quando ninguém está ouvindo — testes, linha de comando)."""
    id = "nulo"
    titulo = ""

    def comecar(self, *a, **k):
        return self

    def etapa(self, *a, **k):
        pass

    def callback(self):
        return lambda pct, detalhe=None: None

    def fim(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, tb):
        return False
