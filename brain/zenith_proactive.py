# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_proactive.py — Fala espontânea depois de inatividade.
#
#  Só avisa (via callback) quando é hora de falar — não decide O QUE
#  falar, isso fica com quem estiver escutando (zenith_headless.py),
#  que usa o próprio zenith_core.pensar() pra manter a mesma memória,
#  personalidade e filtros de segurança de uma mensagem normal.
# ============================================================

import threading
import time


class ZenithProactive:
    def __init__(self, minutos_inatividade: float = 15.0):
        self.minutos_inatividade = minutos_inatividade
        self._last_activity = time.time()
        self._callback = None
        self._running = False
        self._thread = None

    def marcar_atividade(self):
        self._last_activity = time.time()

    def set_callback(self, callback):
        self._callback = callback

    def set_intervalo(self, minutos: float):
        self.minutos_inatividade = max(1.0, minutos)

    def start(self):
        if self._running:
            return
        self._running = True
        self._last_activity = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(30)
            if not self._running:
                break
            inativo_ha_min = (time.time() - self._last_activity) / 60.0
            if inativo_ha_min >= self.minutos_inatividade and self._callback:
                try:
                    self._callback()
                except Exception as e:
                    print(f"[Zenith/Proatividade] Erro ao chamar callback: {e}")
                self._last_activity = time.time()  # não repete até passar de novo
