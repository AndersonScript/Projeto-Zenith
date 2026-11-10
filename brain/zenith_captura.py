"""Zenith — CAPTURA DE TELA SEM A JANELA DO PRÓPRIO ZENITH POR CIMA (v1.4).

Problema (print do Anderson): "Como você aprovou a captura de tela, a própria janela do Zenith ficou por cima na hora do
print." A IA via o chat dela mesma em vez do que o usuário queria mostrar.

Solução: no instante da captura, as janelas do Zenith são ESCONDIDAS por uma fração de segundo e logo DEVOLVIDAS
(sempre — mesmo se a captura falhar, o `finally` as mostra de novo). Vale para a foto única (`<ver_tela>`) e, com um
limiar, para a observação ao vivo (para a janela pequena do avatar não piscar a cada 20 s).

  ocultar_area = 0.0   esconde TODAS as janelas do Zenith (foto única)
  ocultar_area = 0.25  esconde só as que cobrem >= 25% da tela (a Central de Controle), e deixa o avatar quieto
  ocultar_area = None  não esconde nada

Só mexe em janelas do PRÓPRIO Zenith (reconhecidas pelo nome do programa), nunca em outras. Só existe no Windows; em outro
sistema a função devolve a captura normal. As funções de Windows ficam isoladas (e injetáveis) para poder testar sem Windows.
NÃO foi testado em um Windows de verdade: se o avatar sumir e não voltar, desligue `captura_sem_zenith` em Configurações.
"""
from __future__ import annotations

import os
import time

ATIVO = True                 # settings["captura_sem_zenith"]
ESPERA_S = 0.18              # tempo para o Windows redesenhar a tela sem a janela
NOMES_DO_PROGRAMA = ("zenith.exe",)          # o .exe do Cérebro e o do Corpo (Godot exportado) se chamam assim
SW_HIDE, SW_SHOWNOACTIVATE = 0, 8


# ---------------------------------------------------------------------------------------------------------------------
# camada Windows (isolada; ctypes só é importado se for Windows)
# ---------------------------------------------------------------------------------------------------------------------
def _enumerar_janelas_zenith() -> list:
    """[{'hwnd': int, 'rect': (esq, topo, dir, base), 'titulo': str}] das janelas visíveis do Zenith. Vazio fora do Windows."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    achadas = []
    nome_da_imagem = ctypes.create_unicode_buffer(520)

    def _imagem_do_processo(pid: int) -> str:
        h = k.OpenProcess(0x1000, False, pid)             # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            tam = wintypes.DWORD(len(nome_da_imagem))
            if k.QueryFullProcessImageNameW(h, 0, nome_da_imagem, ctypes.byref(tam)):
                return os.path.basename(nome_da_imagem.value).lower()
            return ""
        finally:
            k.CloseHandle(h)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        try:
            if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
                return True
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid():
                return True                               # o Cérebro (Python) não tem janela de interface
            if _imagem_do_processo(pid.value) not in NOMES_DO_PROGRAMA:
                return True
            r = wintypes.RECT()
            u.GetWindowRect(hwnd, ctypes.byref(r))
            if (r.right - r.left) < 40 or (r.bottom - r.top) < 40:
                return True
            n = u.GetWindowTextLengthW(hwnd)
            t = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, t, n + 1)
            achadas.append({"hwnd": int(hwnd), "rect": (r.left, r.top, r.right, r.bottom), "titulo": t.value})
        except Exception:
            pass
        return True

    u.EnumWindows(_cb, 0)
    return achadas


def titulo_ativo() -> str:
    """Título da janela em foco (v1.7: a presença pausa em janela de senha/banco). "" fora do Windows.
    Só LÊ o título — não captura nada, não mexe em nenhuma janela."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        if not h:
            return ""
        n = u.GetWindowTextLengthW(h)
        if n <= 0:
            return ""
        t = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, t, n + 1)
        return t.value.strip()
    except Exception:
        return ""


def _tamanho_da_tela() -> tuple:
    if os.name != "nt":
        return (1920, 1080)
    import ctypes
    u = ctypes.windll.user32
    return (u.GetSystemMetrics(0), u.GetSystemMetrics(1))


def _esconder(j: dict) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    ctypes.windll.user32.ShowWindow(j["hwnd"], SW_HIDE)
    return True


def _mostrar(j: dict) -> None:
    if os.name != "nt":
        return
    import ctypes
    ctypes.windll.user32.ShowWindow(j["hwnd"], SW_SHOWNOACTIVATE)


# ---------------------------------------------------------------------------------------------------------------------
# lógica (testável)
# ---------------------------------------------------------------------------------------------------------------------
def _fracao_da_tela(rect, tela) -> float:
    esq, topo, dir_, base = rect
    area = max(0, dir_ - esq) * max(0, base - topo)
    return area / float(max(1, tela[0] * tela[1]))


def escolher(janelas: list, ocultar_area, tela=(1920, 1080)) -> list:
    """Quais janelas esconder. `ocultar_area` None = nenhuma; 0.0 = todas; 0.25 = só as grandes."""
    if ocultar_area is None:
        return []
    return [j for j in janelas if _fracao_da_tela(j["rect"], tela) >= float(ocultar_area)]


def capturar_sem_zenith(capturar, ocultar_area=0.0, enumerar=None, esconder=None, mostrar=None, tela=None,
                        espera=None, dormir=time.sleep):
    """Chama `capturar()` com as janelas do Zenith escondidas e as DEVOLVE sempre. Qualquer falha na parte de janelas
    é engolida: a captura acontece do mesmo jeito (pior caso: sai com a janela do Zenith, como antes da v1.4)."""
    escondidas = []
    try:
        if ATIVO and ocultar_area is not None:
            janelas = (enumerar or _enumerar_janelas_zenith)()
            for j in escolher(janelas, ocultar_area, tela or _tamanho_da_tela()):
                try:
                    if (esconder or _esconder)(j):
                        escondidas.append(j)
                except Exception:
                    pass
            if escondidas:
                dormir(ESPERA_S if espera is None else espera)
    except Exception:
        pass
    try:
        return capturar()
    finally:
        for j in reversed(escondidas):
            try:
                (mostrar or _mostrar)(j)
            except Exception:
                pass
