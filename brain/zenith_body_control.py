"""
Zenith — controle do processo do Corpo (brain/zenith_body_control.py).

Por que isso existe (v18): pra importar um avatar novo, o Cérebro (Python)
reempacota o Zenith.pck. Só que o Corpo (o Zenith.exe exportado do Godot)
está rodando e segurando esse arquivo. Antes, o usuário tinha que fechar e
abrir o Zenith na mão. Agora o launcher SUPERVISIONA o Corpo: o Cérebro pede
"pare o Corpo, deixa eu trocar o arquivo, e suba ele de novo", e o launcher
faz isso sozinho.

Duas metades, no mesmo processo (o Cérebro roda numa thread do launcher):

  * supervisionar(lancar)  — roda no launcher (thread principal). Sobe o
    Corpo, espera ele sair e, se a saída foi um reinício PEDIDO, espera a
    troca de arquivos terminar e sobe de novo. Se foi o usuário que fechou
    o Corpo, sai (o Zenith fecha, como sempre foi).
  * trocar_e_reiniciar(fazer_troca) — roda no Cérebro. Para o Corpo, executa
    `fazer_troca()` (copiar o .pck) e libera o launcher pra relançar.

Se ninguém estiver supervisionando (ex.: Cérebro rodando sozinho e o Godot
aberto à mão pelo editor), trocar_e_reiniciar() só executa a troca e avisa
que NÃO reiniciou nada (quem chamou decide o que dizer ao usuário).
"""
import subprocess
import threading

_lock = threading.RLock()
_swap_lock = threading.Lock()         # uma troca de cada vez
_proc = None                          # subprocess.Popen do Corpo atual
_exe = ""                             # caminho do Zenith.exe do Corpo atual
_supervisionando = False              # há um launcher ativo cuidando do Corpo?
_reinicio_pedido = threading.Event()  # o Cérebro pediu "pare, troque, suba de novo"
_troca_concluida = threading.Event()  # a troca de arquivos terminou (com ou sem sucesso)

TIMEOUT_PARAR = 15       # s: terminate() -> kill() se o Corpo não sair
TIMEOUT_TROCA = 600      # s: o launcher não espera a troca pra sempre


def supervisionando() -> bool:
    return _supervisionando


def corpo_exe() -> str:
    """Caminho do Zenith.exe do Corpo em execução (ou o último lançado)."""
    return _exe


def corpo_vivo() -> bool:
    with _lock:
        return _proc is not None and _proc.poll() is None


def _resetar():
    """Só pros testes: volta ao estado inicial."""
    global _proc, _exe, _supervisionando
    with _lock:
        _proc = None
        _exe = ""
        _supervisionando = False
    _reinicio_pedido.clear()
    _troca_concluida.clear()


def supervisionar(lancar, log=print) -> None:
    """Loop do launcher. `lancar()` devolve (Popen | None, caminho_exe).
    Bloqueia até o Corpo ser fechado de verdade pelo usuário (ou, sem
    Corpo, fica de pé só com o Cérebro — igual o launcher sempre fez)."""
    global _proc, _exe, _supervisionando
    _supervisionando = True
    try:
        while True:
            proc, exe = lancar()
            with _lock:
                _proc, _exe = proc, (exe or "")
            if proc is None:
                threading.Event().wait()      # só o Cérebro vivo
                return
            proc.wait()
            if not _reinicio_pedido.is_set():
                return                        # o usuário fechou o Corpo: fecha tudo
            log("Corpo parado pra troca de arquivos; esperando ela terminar...")
            if not _troca_concluida.wait(TIMEOUT_TROCA):
                log("A troca de arquivos passou do tempo — subindo o Corpo mesmo assim.")
            _reinicio_pedido.clear()
            _troca_concluida.clear()
            log("Subindo o Corpo de novo.")
    finally:
        with _lock:
            _supervisionando = False
            if _proc is not None and _proc.poll() is None:
                try:
                    _proc.terminate()
                except Exception:
                    pass


def _parar_corpo() -> bool:
    """Para o Corpo atual. True se ele não está mais rodando."""
    with _lock:
        p = _proc
    if p is None or p.poll() is not None:
        return True
    try:
        p.terminate()
        p.wait(TIMEOUT_PARAR)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
            p.wait(TIMEOUT_PARAR)
        except Exception:
            pass
    except Exception:
        pass
    return p.poll() is not None


def trocar_e_reiniciar(fazer_troca) -> dict:
    """Para o Corpo, roda `fazer_troca()` e deixa o launcher subir ele de novo.

    Devolve {"reiniciou": bool, "resultado": <retorno de fazer_troca>,
             "erro": str}. Nunca levanta exceção: se `fazer_troca` falhar, o
    Corpo é relançado mesmo assim (com os arquivos antigos) e o erro vem em
    "erro"."""
    if not _supervisionando:
        try:
            return {"reiniciou": False, "resultado": fazer_troca(), "erro": ""}
        except Exception as e:
            return {"reiniciou": False, "resultado": None, "erro": str(e)}

    if not _swap_lock.acquire(blocking=False):
        return {"reiniciou": False, "resultado": None,
                "erro": "já existe uma troca de arquivos em andamento"}
    try:
        _troca_concluida.clear()
        _reinicio_pedido.set()            # ANTES de parar, pro launcher saber que foi de propósito
        resultado, erro, parou = None, "", False
        try:
            if not _parar_corpo():
                erro = "não consegui parar o Corpo pra trocar o arquivo"
            else:
                resultado = fazer_troca()
        except Exception as e:
            erro = str(e)
        finally:
            parou = not corpo_vivo()      # medido ANTES de liberar o launcher (que sobe um Corpo novo)
            if not parou:
                _reinicio_pedido.clear()  # o Corpo não parou: não é um reinício de verdade
            _troca_concluida.set()        # sempre libera o launcher, senão o Zenith ficaria sem Corpo
        return {"reiniciou": parou, "resultado": resultado, "erro": erro}
    finally:
        _swap_lock.release()
