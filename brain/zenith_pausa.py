"""
Zenith — Modo silêncio total (/pausar e /retomar). Pilar 1: o usuário sempre
pode parar tudo, com um comando, sem depender da IA concordar.

Este módulo só guarda o ESTADO (ligado/desligado, desde quando, por quê). Quem
age conforme ele é o Cérebro (zenith_headless.py): enquanto estiver ativo,
ele não manda nada pra IA, não fala sozinho, não liga microfone, não abre
pedido de aprovação novo e cancelou os pendentes na hora de pausar. Comandos
"/" continuam funcionando (senão não teria como retomar).

O estado NÃO é gravado em disco de propósito: reabrir o Zenith começa sempre
"liberado" — um modo que sobrevive a reiniciar e prende o usuário do lado de
fora é pior que o problema que ele resolve.
"""
import datetime
import threading

_lock = threading.Lock()
_estado = {"ativo": False, "desde": None, "motivo": ""}


def ativo() -> bool:
    with _lock:
        return bool(_estado["ativo"])


def pausar(motivo: str = "") -> bool:
    """True se ligou agora; False se já estava ligado."""
    with _lock:
        if _estado["ativo"]:
            return False
        _estado.update(ativo=True, desde=datetime.datetime.now(), motivo=str(motivo or ""))
        return True


def retomar() -> bool:
    """True se desligou agora; False se já estava liberado."""
    with _lock:
        if not _estado["ativo"]:
            return False
        _estado.update(ativo=False, desde=None, motivo="")
        return True


def desde_texto() -> str:
    with _lock:
        d = _estado["desde"]
    return d.strftime("%H:%M") if d else ""


def mensagem_bloqueio() -> str:
    quando = desde_texto()
    parte = f" desde {quando}" if quando else ""
    return (f"⏸️ Modo silêncio total ativo{parte}: não estou mandando nada pra IA, não estou "
            f"falando, nem ouvindo, nem propondo ações. Digite /retomar pra liberar.")


def _resetar():
    """Só pros testes."""
    with _lock:
        _estado.update(ativo=False, desde=None, motivo="")
