"""Zenith — plataforma PC (v1.11): o lado "Windows" da mesma interface.

Esta é a parte DELIBERADAMENTE pequena. Os módulos do PC (`zenith_interaction`, `zenith_vision`...) continuam
funcionando como sempre, sem mexer. Cada módulo passa a chamar a plataforma só quando for migrado, um por vez,
e o PC nunca fica sem funcionar no meio do caminho.

Aqui já estão: medir o sistema, capturar tela e câmera (mesma lógica do `ZenithVision`), notificar e abrir.
Áudio, microfone, Whisper e voz continuam nos módulos atuais até a migração deles — por isso `tem("microfone")`
é falso aqui, e isso é esperado, não um defeito.

As bibliotecas são importadas na hora, e podem ser injetadas (`mss_mod`, `cv2_mod`, `plyer_mod`) para testar
sem nada instalado.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import webbrowser

from brain.zenith_plataforma import Plataforma, medir_sistema

_FALTA = object()


def _importar(nome: str):
    try:
        return __import__(nome)
    except Exception:
        return None


class PCPlataforma(Plataforma):
    nome = "pc"

    def __init__(self, mss_mod=_FALTA, cv2_mod=_FALTA, plyer_mod=_FALTA):
        self._mss = _importar("mss") if mss_mod is _FALTA else mss_mod
        self._cv2 = _importar("cv2") if cv2_mod is _FALTA else cv2_mod
        self._plyer = _importar("plyer") if plyer_mod is _FALTA else plyer_mod
        caps = {"sistema", "abrir"}
        if self._mss is not None:
            caps.add("tela")
        if self._cv2 is not None:
            caps.add("camera")
        if self._plyer is not None:
            caps.add("notificacao")
        self.capacidades = frozenset(caps)

    def medir(self) -> dict:
        return medir_sistema(psutil_mod=_importar("psutil"))

    # ---- visão (mesma lógica de zenith_vision, para a migração ser só trocar a chamada) ----------------
    def capturar_tela(self, max_w: int = 0, jpeg: bool = False):
        if "tela" not in self.capacidades:
            return None, "Biblioteca 'mss' não instalada. Rode: pip install mss"
        try:
            mss = self._mss
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(monitor)
                if not max_w and not jpeg:
                    return mss.tools.to_png(shot.rgb, shot.size), None
                from PIL import Image
                im = Image.frombytes("RGB", shot.size, shot.rgb)
                if max_w and im.width > max_w:
                    im = im.resize((max_w, max(1, int(im.height * max_w / im.width))))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82) if jpeg else im.save(buf, "PNG")
                return buf.getvalue(), None
        except Exception as e:
            return None, f"Erro ao capturar a tela: {e}"

    def capturar_camera(self, warmup: int = 5, max_w: int = 0):
        if "camera" not in self.capacidades:
            return None, "Biblioteca 'opencv-python' não instalada. Rode: pip install opencv-python-headless"
        cv2, cam = self._cv2, None
        try:
            cam = cv2.VideoCapture(0)
            if not cam.isOpened():
                return None, "Nenhuma câmera encontrada (índice 0)."
            frame, ok = None, False
            for _ in range(max(1, int(warmup))):
                ok, frame = cam.read()
            if not ok:
                return None, "Não consegui capturar um frame da câmera."
            if max_w and frame.shape[1] > max_w:
                frame = cv2.resize(frame, (max_w, int(frame.shape[0] * max_w / frame.shape[1])))
            sucesso, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not sucesso:
                return None, "Erro ao codificar a imagem da câmera."
            return buf.tobytes(), None
        except Exception as e:
            return None, f"Erro ao acessar a câmera: {e}"
        finally:
            if cam is not None:
                cam.release()

    # ---- sistema do usuário -----------------------------------------------------------------------------
    def notificar(self, titulo: str, texto: str) -> bool:
        self._exigir("notificacao")
        try:
            self._plyer.notification.notify(title=titulo, message=texto, timeout=5)
            return True
        except Exception:
            return False

    def abrir(self, alvo: str) -> bool:
        try:
            if alvo.lower().startswith(("http://", "https://")):
                return bool(webbrowser.open(alvo))
            if hasattr(os, "startfile"):
                os.startfile(alvo)                      # type: ignore[attr-defined]   # só existe no Windows
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", alvo])
            return True
        except Exception:
            return False
