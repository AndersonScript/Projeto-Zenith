"""
Zenith — janela do avatar: clique que atravessa DE VERDADE (Windows).

Por que existe (relato do Anderson, v19): a janela transparente do avatar ficava por cima de
atalhos/botões e "não deixava clicar". O Corpo já ligava a flag MOUSE_PASSTHROUGH do Godot, mas
no Windows ela é implementada com HTTRANSPARENT, que só repassa o clique para janelas do MESMO
processo — para a área de trabalho, a barra de tarefas e outros programas ela não resolve. O que
resolve é o estilo estendido de janela WS_EX_TRANSPARENT (junto com WS_EX_LAYERED), que o Godot
não expõe. Este módulo aplica esse estilo na janela do avatar a partir do Cérebro (Python).

Como acha a janela: o Corpo manda o PID do próprio processo. Entre as janelas de topo desse PID,
a do avatar é a SEM barra de título (borderless); a Central de Controle tem barra de título e é
ignorada. Se não achar (ou se não for Windows), não faz nada e devolve uma mensagem — nunca levanta
exceção para quem chama.

Tudo que toca a API do Windows fica atrás de `_api()`, para os testes poderem trocar por um
falso (os testes rodam em qualquer sistema).
"""
import sys

GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_VISIBLE = 0x10000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


class _Win32:
    """Fino invólucro sobre user32 (só carregado no Windows)."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.wintypes = wintypes
        self.user32 = ctypes.windll.user32
        self._is64 = ctypes.sizeof(ctypes.c_void_p) == 8
        self.user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t if self._is64 else ctypes.c_long
        self.user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t if self._is64 else ctypes.c_long
        self.user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int,
                                                  ctypes.c_ssize_t if self._is64 else ctypes.c_long]

    def janelas_do_pid(self, pid):
        ctypes, wintypes = self.ctypes, self.wintypes
        achadas = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lp):
            dono = wintypes.DWORD(0)
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dono))
            if dono.value == pid:
                achadas.append(int(hwnd))
            return True

        self.user32.EnumWindows(proc(_cb), 0)
        return achadas

    def get_style(self, hwnd):
        return int(self.user32.GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF

    def get_exstyle(self, hwnd):
        return int(self.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF

    def set_exstyle(self, hwnd, valor):
        self.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, valor)
        # avisa o Windows que o estilo mudou (sem mexer em tamanho/posição/foco)
        self.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


_api_cache = None


def _api():
    global _api_cache
    if _api_cache is None:
        _api_cache = _Win32()
    return _api_cache


def suportado() -> bool:
    return sys.platform == "win32"


def escolher_janela_avatar(api, pid):
    """Entre as janelas do processo, a do avatar: visível e SEM barra de título.
    Devolve o HWND ou None."""
    candidatas = []
    for hwnd in api.janelas_do_pid(int(pid)):
        estilo = api.get_style(hwnd)
        if not (estilo & WS_VISIBLE):
            continue
        if estilo & WS_CAPTION:          # tem barra de título => é a Central de Controle
            continue
        candidatas.append(hwnd)
    return candidatas[0] if candidatas else None


def definir_clique_atravessa(pid, ativo: bool, api=None):
    """Liga/desliga o clique-atravessa da janela do avatar do processo `pid`.
    Devolve (ok: bool, mensagem: str). Nunca levanta exceção."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False, "PID inválido."
    if pid <= 0:
        return False, "PID inválido."
    if api is None:
        if not suportado():
            return False, "Clique-atravessa por estilo de janela só existe no Windows."
        try:
            api = _api()
        except Exception as e:
            return False, f"Não consegui carregar a API do Windows: {e}"
    try:
        hwnd = escolher_janela_avatar(api, pid)
        if hwnd is None:
            return False, "Não achei a janela do avatar (ainda abrindo?)."
        atual = api.get_exstyle(hwnd)
        if ativo:
            novo = atual | WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            # mantém WS_EX_LAYERED (o Godot usa para a transparência por pixel); só tira o TRANSPARENT
            novo = atual & ~WS_EX_TRANSPARENT
        if novo != atual:
            api.set_exstyle(hwnd, novo)
        return True, ("Clique atravessa a janela do avatar." if ativo else "Janela do avatar volta a receber cliques.")
    except Exception as e:  # pragma: no cover — defensivo
        return False, f"Falha ao mexer na janela do avatar: {e}"
