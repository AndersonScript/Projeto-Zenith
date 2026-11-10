# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_vision.py — Captura de tela e câmera.
#
#  Fica só na captura (bytes de imagem) — quem decide o que fazer com
#  a imagem (comentar via IA multimodal) é o zenith_core.py. A
#  aprovação do usuário (Pilar 1) acontece ANTES desse módulo ser
#  chamado, em zenith_core.approve_action().
#
#  Degrada com elegância: se 'mss' ou 'cv2' não estiverem instalados,
#  retorna None com uma mensagem clara em vez de derrubar o programa.
# ============================================================

from brain import zenith_plataforma

try:
    import mss
    import mss.tools
except ImportError:
    mss = None

try:
    import cv2
except ImportError:
    cv2 = None


class ZenithVision:
    def capture_screen(self, max_w: int = 0, jpeg: bool = False, ocultar_area=0.0):
        """Retorna (bytes, None) ou (None, motivo_do_erro). PNG por padrão. `max_w` reduz a largura (menos tokens
        pra IA) e `jpeg=True` troca o formato — a observação ao vivo usa os dois.
        v1.4: as janelas do Zenith são escondidas por um instante (ver zenith_captura.py); `ocultar_area=None` desliga."""
        if zenith_plataforma.detectar() == "android":      # v1.11 — celular: quem captura é o Android (pela ponte)
            return zenith_plataforma.obter().capturar_tela(max_w, jpeg)
        try:
            from brain import zenith_captura
            return zenith_captura.capturar_sem_zenith(lambda: self._capture_screen_raw(max_w, jpeg), ocultar_area)
        except Exception:
            return self._capture_screen_raw(max_w, jpeg)

    def _capture_screen_raw(self, max_w: int = 0, jpeg: bool = False):
        if mss is None:
            return None, "Biblioteca 'mss' não instalada. Rode: pip install mss"
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(monitor)
                if not max_w and not jpeg:
                    return mss.tools.to_png(shot.rgb, shot.size), None
                from PIL import Image
                import io
                im = Image.frombytes("RGB", shot.size, shot.rgb)
                if max_w and im.width > max_w:
                    im = im.resize((max_w, max(1, int(im.height * max_w / im.width))))
                buf = io.BytesIO()
                if jpeg:
                    im.save(buf, "JPEG", quality=82)
                else:
                    im.save(buf, "PNG")
                return buf.getvalue(), None
        except Exception as e:
            return None, f"Erro ao capturar a tela: {e}"

    def capture_camera(self, warmup: int = 5, max_w: int = 0):
        """Retorna (bytes_jpeg, None) ou (None, motivo_do_erro). v23: descarta os primeiros `warmup` quadros — logo
        depois de abrir, a câmera costuma entregar imagem ESCURA (exposição ainda ajustando) — e pode reduzir a
        largura (`max_w`) pra economizar tokens."""
        if zenith_plataforma.detectar() == "android":      # v1.11 — celular: a câmera é a do Android (pela ponte)
            return zenith_plataforma.obter().capturar_camera(warmup, max_w)
        if cv2 is None:
            return None, "Biblioteca 'opencv-python' não instalada. Rode: pip install opencv-python-headless"
        cam = None
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
                h = int(frame.shape[0] * max_w / frame.shape[1])
                frame = cv2.resize(frame, (max_w, h))
            success, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not success:
                return None, "Erro ao codificar a imagem da câmera."
            return buf.tobytes(), None
        except Exception as e:
            return None, f"Erro ao acessar a câmera: {e}"
        finally:
            if cam is not None:
                cam.release()
