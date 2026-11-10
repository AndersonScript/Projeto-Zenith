"""
Zenith — PRIMEIRA ABERTURA DO .EXE COMO ADMINISTRADOR (v26).

O que o Anderson avisou (11/10/2026): depois do build do executável, se o .exe NÃO for aberto como administrador
na PRIMEIRA vez, ele não funciona; abrindo como administrador uma vez, depois funciona normal.

Antes isso era um segredo na cabeça dele. Agora o programa cuida:
  * no .exe (e só no Windows), se ainda não houve nenhuma abertura como administrador nesta pasta, o Zenith PERGUNTA:
    "Reabrir como administrador agora?"  Sim → pede a permissão do Windows (UAC) e reabre.
    Não → segue (pode não funcionar direito) e PERGUNTA DE NOVO na próxima abertura. (v26 gravava o "não" pra sempre e
    nunca mais perguntava — o Anderson clicou "Não" no 1º teste e ficou com um .exe que não funcionava e sem aviso.)
  * se já está como administrador, anota (config/.admin_ok) e nunca mais pergunta.
  * a cópia limpa de pendrive (prepare_pendrive.py) apaga a marca — cada cópia nova pergunta de novo.

Rodando do código-fonte (python zenith_launcher.py) NADA disso acontece: só vale pro .exe compilado.
A decisão (decidir) é lógica pura e testável; as chamadas do Windows ficam isoladas nas outras funções.
"""
from __future__ import annotations

import os
import subprocess
import sys

MARCA_OK = ".admin_ok"
MARCA_DISPENSADO = ".admin_dispensado"      # v26 (legado): não é mais gravada nem respeitada; só é apagada
_AUTO = object()                             # "olhe o ambiente real" (None quer dizer "não consegui descobrir")

TITULO = "Zenith — primeira abertura"
PERGUNTA = (
    "Esta é a primeira vez que o Zenith abre nesta pasta.\n\n"
    "A PRIMEIRA abertura precisa ser como ADMINISTRADOR, senão o Zenith pode não funcionar. "
    "Depois dessa vez você abre normalmente, com duplo clique.\n\n"
    "Clique SIM: o Windows vai pedir a sua permissão e o Zenith abre de novo sozinho.\n"
    "Clique NÃO: o Zenith abre assim mesmo (pode dar problema) e pergunta de novo na próxima vez."
)


def e_admin():
    """True/False no Windows; None se não der pra saber."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return None


def decidir(config_dir, frozen=_AUTO, windows=_AUTO, admin=_AUTO) -> str:
    """'nada' | 'marcar' | 'perguntar'. Parâmetros existem pra teste; sem eles, olha o ambiente real.
    (v27: `admin=None` agora significa "não consegui descobrir" — antes virava "olhe o ambiente", e o teste mudava de
    resultado no PC do Anderson, que roda como administrador.)"""
    frozen = getattr(sys, "frozen", False) if frozen is _AUTO else frozen
    windows = (os.name == "nt") if windows is _AUTO else windows
    if not (frozen and windows):
        return "nada"
    try:                                  # v1.4 — edição PÚBLICA nunca pede "reabrir como administrador":
        from brain import zenith_edicao   # quem baixa usa o instalador (que cuida do que for preciso)
        if zenith_edicao.e_publico():
            return "nada"
    except Exception:
        pass
    if os.path.exists(os.path.join(str(config_dir), MARCA_OK)):
        return "nada"
    admin = e_admin() if admin is _AUTO else admin
    if admin is None:
        return "nada"                  # não consegui descobrir: não incomoda
    return "marcar" if admin else "perguntar"


def marcar(config_dir, nome: str = MARCA_OK):
    try:
        os.makedirs(str(config_dir), exist_ok=True)
        with open(os.path.join(str(config_dir), nome), "w", encoding="utf-8") as f:
            f.write("Zenith: primeira abertura resolvida. Apague este arquivo pra o Zenith perguntar de novo.\n")
    except OSError:
        pass


def perguntar_reabrir():
    """Caixa Sim/Não nativa. 'sim' | 'nao' | None (não deu pra mostrar)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        # MB_YESNO (4) | MB_ICONQUESTION (0x20) | MB_TOPMOST (0x40000)
        r = ctypes.windll.user32.MessageBoxW(0, PERGUNTA, TITULO, 0x4 | 0x20 | 0x40000)
        return "sim" if r == 6 else "nao"
    except Exception:
        return None


def reabrir_como_admin() -> bool:
    """Pede elevação (UAC) e abre o MESMO .exe de novo. True se o Windows aceitou o pedido."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        params = subprocess.list2cmdline(sys.argv[1:])
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return int(r) > 32
    except Exception:
        return False
