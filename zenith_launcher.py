# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_launcher.py — Ponto de entrada ÚNICO (isto vira o Zenith.exe).
#
#  Faz, em ordem, cada passo protegido por try/except (se um passo
#  falhar, avisa no console e segue tentando os próximos — não trava
#  silenciosamente, que era o problema antes):
#   1) Garante as dependências Python (zenith_bootstrap)
#   2) Sobe o Cérebro sem janela (zenith_headless) numa thread
#   3) Abre o Corpo — o .exe exportado do Godot (usuário final NÃO
#      precisa ter o Godot instalado; só quem desenvolve o projeto).
# ============================================================

import os
import sys
import time
import threading
import subprocess
import traceback

if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# CRÍTICO: o build usa --noconsole (de propósito, pra não abrir uma
# janela de terminal preta junto com o app) — mas isso também apaga
# TODOS os print()s, sem deixar rastro nenhum de erro em lugar algum.
# Com um executável assim, é impossível debugar o que está acontecendo
# lá dentro. A partir de agora, tudo que seria print() também vai pra
# um arquivo de log ao lado do .exe — sempre que der algum problema,
# é ESSE arquivo que eu preciso ver.
LOG_PATH = os.path.join(BASE, "zenith_log.txt")


class _Vazio:
    r"""Destino que joga fora tudo que seria escrito nele.

    CORREÇÃO (linha solta no terminal do usuário): antes, quando o log não podia ser aberto
    (ou no modo ZENITH_TESTE), o redirecionamento era pulado e o print() do _log caía no
    console de verdade. A linha "[Zenith/Launcher] Corpo aberto: C:\Zenith\Zenith\body\zenith\
    export\Zenith.exe" apareceu no terminal do PyCharm do Anderson logo depois de ele rodar a
    suíte de testes (é o teste LauncherCorpoBloqueadoTests que liga o ZENITH_TESTE e chama
    _launch_godot_body()). Com a linha solta no prompt, o PowerShell tentou EXECUTÁ-LA como
    comando e cuspiu "O padrão de caractere curinga especificado não é válido: .[Zenith".
    Daqui pra frente este launcher NUNCA escreve no console: se não há log, o destino é o vazio.
    """

    def write(self, _texto) -> int:
        return 0

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


_log_file = None
if not os.environ.get("ZENITH_TESTE"):
    try:
        _log_file = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
        sys.stdout = _log_file
        sys.stderr = _log_file
    except Exception:
        # Não consegui abrir o log: o destino passa a ser o VAZIO, nunca o console.
        sys.stdout = _Vazio()
        sys.stderr = _Vazio()
# No modo de teste o sys.stdout NÃO é trocado (o unittest precisa dele). Quem garante o
# silêncio no terminal é o _log, que não escreve em lugar nenhum quando não há arquivo aberto.


def _log(msg):
    if _log_file is None:
        return          # sem arquivo de log (modo de teste, ou falha ao abrir): não escreve em lugar nenhum
    line = f"[Zenith/Launcher] {msg}"
    try:
        _log_file.write(line + "\n")
        _log_file.flush()
    except Exception:
        pass


def _avisar_na_tela(titulo: str, texto: str):
    """Caixa de mensagem nativa do Windows (sem dependência nova). O Zenith.exe roda sem
    console e a Central de Controle é do CORPO (Godot): se o Corpo não abre, não existe
    nenhuma janela pra mostrar o erro — sem isso o Zenith parece "morto" e só o log sabe.
    Roda numa thread pra não travar o resto."""
    if os.name != "nt":
        return

    def _mostrar():
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, texto, titulo, 0x10 | 0x40000)   # ícone de erro + sempre no topo
        except Exception:
            pass
    threading.Thread(target=_mostrar, daemon=True).start()


def _texto_corpo_bloqueado(detalhe: str) -> str:
    extra = ""
    try:
        from brain import zenith_diag
        codigo, _ = zenith_diag.estado_controle_inteligente()
        if codigo == "ligado":
            extra = ("\n\nNeste PC o CONTROLE INTELIGENTE DE APLICATIVOS está ligado — ele bloqueia programas "
                     "sem assinatura digital e é o principal suspeito.")
    except Exception:
        pass
    return ("O Windows (ou o antivírus) não deixou o Corpo do Zenith abrir — é ele que mostra o avatar e a "
            "Central de Controle." + extra +
            "\n\nO que fazer: leia NOTES_ANTIVIRUS.md (seção \"Controle Inteligente de Aplicativos\"). "
            "O Zenith continua rodando em segundo plano, sem janela; feche-o pelo Gerenciador de Tarefas "
            "(Zenith.exe) e abra de novo depois de resolver."
            f"\n\nDetalhe técnico: {detalhe}\nLog: {LOG_PATH}")


def _primeira_execucao_admin():
    """v26 — o .exe só funciona se a PRIMEIRA abertura for como administrador. Em vez de o usuário ter que lembrar,
    o Zenith pergunta (uma vez) e reabre elevado se ele disser que sim. Só vale pro .exe no Windows."""
    try:
        from brain import zenith_admin as adm
        from brain.zenith_settings import CONFIG_DIR
        acao = adm.decidir(CONFIG_DIR)
        if acao == "marcar":
            adm.marcar(CONFIG_DIR, adm.MARCA_OK)
            _log("Primeira abertura como administrador: ok (marcado em config/.admin_ok).")
        elif acao == "perguntar":
            _log("Primeira abertura SEM administrador: perguntando se reabre como administrador.")
            r = adm.perguntar_reabrir()
            if r == "sim":
                if adm.reabrir_como_admin():
                    _log("Reabrindo como administrador — esta cópia fecha agora.")
                    sys.exit(0)
                _log("O Windows não liberou a elevação (ou foi cancelada). Seguindo sem administrador.")
            elif r == "nao":
                _log("Você escolheu seguir sem administrador agora. Posso não funcionar direito; pergunto de novo na próxima abertura.")
            try:                                   # marca antiga da v26 ("Não" pra sempre): some, pra voltar a perguntar
                os.remove(os.path.join(str(CONFIG_DIR), adm.MARCA_DISPENSADO))
            except OSError:
                pass
    except SystemExit:
        raise
    except Exception:
        _log("Não consegui checar a primeira abertura como administrador — seguindo:")
        traceback.print_exc()


def _preparar_ajustes():
    """v1.6.2 — liga os AJUSTES DE CÓDIGO que o usuário aprovou (config/ajustes/overlay) ANTES de qualquer outro módulo do
    Zenith ser importado. Se o Zenith não abriu nas 2 últimas vezes com ajustes ativos, eles vão para a quarentena e o
    Zenith abre limpo (modo seguro). Nunca derruba o app: qualquer erro aqui só vira linha no log."""
    pasta = os.path.join(BASE, "config", "ajustes")
    try:
        from brain import zenith_overlay as ov
        estado = ov.iniciar_boot(pasta)
        if estado["modo_seguro"]:
            _log("MODO SEGURO: " + estado["motivo"] + " Os ajustes foram para config/ajustes/quarentena/ e o Zenith abre sem eles.")
        info = ov.instalar(pasta)
        if info["ativos"]:
            _log("Ajustes de código ativos: " + ", ".join(info["ativos"]))
        for nome, motivo in info["ignorados"]:
            _log(f"Ajuste ignorado ({nome}): {motivo}")
        if info["ja_importados"]:
            _log("Aviso: estes módulos já tinham sido carregados e só usam o ajuste na próxima abertura: " + ", ".join(info["ja_importados"]))
        return pasta
    except Exception:
        _log("Não consegui ligar os ajustes de código — seguindo sem eles:")
        traceback.print_exc()
        return None


def _confirmar_boot(pasta, segundos=25):
    """O Zenith ficou de pé: zera a contagem do modo seguro (passados {segundos}s, ou ao fechar normalmente)."""
    if not pasta:
        return
    try:
        import atexit
        from brain import zenith_overlay as ov
        atexit.register(ov.boot_ok, pasta)

        def _depois():
            time.sleep(segundos)
            try:
                ov.boot_ok(pasta)
            except Exception:
                pass
        threading.Thread(target=_depois, daemon=True).start()
    except Exception:
        pass


def main():
    from datetime import datetime
    _log(f"=== Zenith iniciando em {datetime.now().isoformat(timespec='seconds')} ===")
    _log(f"Log completo desta sessão fica em: {LOG_PATH}")
    pasta_ajustes = _preparar_ajustes()
    _primeira_execucao_admin()
    try:
        from brain.zenith_bootstrap import ensure_dependencies
        ensure_dependencies()
    except Exception:
        _log("Falha na checagem de dependências — seguindo mesmo assim:")
        traceback.print_exc()

    try:
        from brain.zenith_headless import ZenithHeadlessBrain
        brain = ZenithHeadlessBrain()
        _log("Cérebro rodando (WebSocket em ws://localhost:8765).")
        # Dá um respiro real pro servidor WebSocket (que sobe numa thread
        # em background) terminar de abrir a porta ANTES do Corpo tentar
        # conectar — não elimina a necessidade do Corpo ter retry (ele já
        # tem, com intervalo de verdade agora), mas evita a corrida mais
        # óbvia logo na largada.
        time.sleep(0.8)
        _confirmar_boot(pasta_ajustes)            # v1.6.2: o Cérebro subiu — o modo seguro não precisa agir
    except Exception:
        _log("O Cérebro não conseguiu subir. O Corpo ainda vai abrir, mas "
             "sem IA respondendo até isso ser corrigido. Detalhe do erro:")
        traceback.print_exc()
        brain = None

    # v18 — o launcher SUPERVISIONA o Corpo (brain/zenith_body_control.py): se o
    # Cérebro pedir pra trocar o Zenith.pck (importação de avatar novo), o
    # Corpo é parado, o arquivo trocado e o Corpo sobe de novo sozinho. Se o
    # usuário fechar o Corpo, tudo fecha, como sempre foi.
    try:
        from brain import zenith_body_control
        zenith_body_control.supervisionar(_launch_godot_body, log=_log)
    except KeyboardInterrupt:
        pass
    except Exception:
        _log("Falha no supervisor do Corpo — seguindo sem reinício automático:")
        traceback.print_exc()
        proc, _ = _launch_godot_body()
        try:
            if proc:
                proc.wait()
            else:
                threading.Event().wait()
        except KeyboardInterrupt:
            pass


def _launch_godot_via_projeto(motivo: str):
    """PLANO B (v18). O Windows (Controle Inteligente de Aplicativos) bloqueia programa SEM
    assinatura digital que ele não conhece — e o Zenith.exe que o Godot exporta é recém-gerado e
    não tem assinatura. O editor oficial do Godot, ao contrário, o Windows já conhece. Então,
    se o Corpo exportado não abriu, abre-se o MESMO Corpo pelo projeto: `Godot --path <projeto>`
    (equivale ao F5 do editor, sem a janela do editor). Exige o editor do Godot e o cache
    `.godot/imported` do projeto (criado ao abrir o projeto no editor ou ao importar um avatar).
    Devolve (processo, caminho) ou (None, "")."""
    try:
        from brain.zenith_settings import ZenithSettings, BASE_DIR
        from brain import zenith_vrm_import as vi
        env = vi.localizar_ambiente(BASE_DIR, ZenithSettings().get)
        godot, projeto = env.get("godot_bin"), env.get("project_dir")
        if not (godot and projeto):
            _log("Plano B (abrir o Corpo pelo editor do Godot) indisponível: não achei o editor do Godot "
                 "e/ou a pasta do projeto. Coloque o Godot_v4.x_win64.exe em tools/godot/.")
            return None, ""
        if not os.path.isdir(os.path.join(projeto, ".godot", "imported")):
            _log("Plano B indisponível: o projeto não tem .godot/imported (abra o projeto no editor do Godot "
                 "uma vez, ou use 'Adicionar avatar' que importa tudo).")
            return None, ""
        _log(f"Plano B ({motivo}): abrindo o Corpo pelo projeto com o editor do Godot: {godot}")
        proc = subprocess.Popen([godot, "--path", projeto], cwd=projeto)
        try:
            codigo = proc.wait(timeout=4)
            _log(f"Plano B também falhou: o Godot fechou logo (código {codigo}).")
            return None, ""
        except subprocess.TimeoutExpired:
            _log("Plano B funcionou: Corpo aberto pelo editor do Godot (sem depender do Zenith.exe sem assinatura).")
            return proc, godot
    except Exception as e:
        _log(f"Plano B falhou: {type(e).__name__}: {e}")
        return None, ""


# v1.0.1 — TELA PRETA. Relato do Anderson (01/11/2026): no notebook o Corpo abria e a janela ficava
# TODA PRETA — sem erro, sem mensagem, o Zenith parecia morto. No Godot 4.7 a combinação janela
# transparente + MSAA 4x + HDR com o renderizador gl_compatibility falha em driver antigo e desenha
# preto. O Corpo entende `--sem-aa` (sem anti-aliasing) e `--video-seguro` (desliga os efeitos).
# As flags vão DEPOIS de `--` porque é só assim que o Godot entrega em OS.get_cmdline_user_args().
VIDEO_ARGUMENTOS = {
    "normal": [],
    "sem-aa": ["--sem-aa"],
    "seguro": ["--sem-aa", "--video-seguro"],
}


def _modo_video() -> str:
    """'auto' (padrão) | 'normal' | 'sem-aa' | 'seguro'. Vem do ZENITH_VIDEO ou de
    config/settings.json -> body_video_modo. Valor desconhecido volta para 'auto'."""
    modo = ""
    try:
        from brain.zenith_settings import ZenithSettings
        modo = str(ZenithSettings().get("body_video_modo", "") or "").strip().lower()
    except Exception:
        modo = ""
    modo = (os.environ.get("ZENITH_VIDEO") or modo or "auto").strip().lower()
    return modo if (modo in VIDEO_ARGUMENTOS or modo == "auto") else "auto"


def _comando_corpo(path: str, modo: str) -> list:
    """Comando de abertura do Corpo no modo de vídeo pedido (sem modo extra, é só o caminho)."""
    args = VIDEO_ARGUMENTOS.get(modo, [])
    return [path] + (["--"] + args if args else [])


def _launch_godot_body():
    """Devolve (processo, caminho_do_exe) — (None, "") se não achou.
    Procura o Corpo já exportado (não precisa do Godot Engine
    instalado) em alguns lugares plausíveis, nessa ordem:
      1) Caminho salvo em config/settings.json (godot_executable_path)
      2) body/zenith/export/Zenith.exe (lugar recomendado)
      3) body/zenith/Zenith.exe (erro comum: exportar direto na pasta
         do projeto em vez de export/ — aceito também)
    Se não achar em lugar nenhum, avisa como abrir manualmente em vez
    de travar sem dizer nada."""
    candidates = []
    try:
        from brain.zenith_settings import ZenithSettings, BASE_DIR
        settings = ZenithSettings()
        configured = settings.get("godot_executable_path", "")
        if configured:
            candidates.append(configured)
        candidates.append(str(BASE_DIR / "body" / "zenith" / "export" / "Zenith.exe"))
        candidates.append(str(BASE_DIR / "body" / "zenith" / "Zenith.exe"))
    except Exception:
        candidates.append(os.path.join(BASE, "body", "zenith", "export", "Zenith.exe"))
        candidates.append(os.path.join(BASE, "body", "zenith", "Zenith.exe"))

    falhou_ao_abrir = ""
    modo_pedido = _modo_video()
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                # v1.0.1 (TELA PRETA): tenta abrir normalmente e, se o Corpo morrer logo, tenta de novo
                # sem os efeitos de vídeo. Quem já sabe o que funciona na própria placa fixa o modo em
                # config/settings.json ("body_video_modo": "seguro") ou abre com ZENITH_VIDEO=seguro.
                tentativas = [modo_pedido] if modo_pedido != "auto" else ["normal", "sem-aa", "seguro"]
                proc, codigo = None, None
                for pos, modo in enumerate(tentativas):
                    proc = subprocess.Popen(_comando_corpo(path, modo), cwd=os.path.dirname(path))
                    _log(f"Corpo aberto (vídeo: {modo}): {path}")
                    # v18: se o Windows barrar o Corpo DEPOIS de iniciar, ele some em segundos. Sem isso o
                    # Zenith fechava (ou ficava invisível) sem dizer nada.
                    try:
                        codigo = proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        _log(f"Corpo rodando (vídeo: {modo}).")
                        return proc, path
                    _log(f"O Corpo FECHOU logo depois de abrir (código de saída {codigo}, vídeo: {modo}).")
                    if codigo != 0 and pos + 1 < len(tentativas):
                        _log("Vou tentar de novo sem os efeitos de vídeo (tela preta / placa antiga).")
                        continue
                    plano_b = _launch_godot_via_projeto(f"o Corpo exportado fechou com código {codigo}")
                    if plano_b[0] is not None:
                        return plano_b
                    _avisar_na_tela("Zenith — o Corpo fechou ao abrir",
                                    _texto_corpo_bloqueado(f"o Corpo encerrou em menos de 4 s (código {codigo})"))
                    break
                return proc, path
            except Exception as e:
                winerr = getattr(e, "winerror", None)
                falhou_ao_abrir = f"{type(e).__name__}: {e}" + (f" (WinError {winerr})" if winerr else "")
                _log(f"Achei '{path}' mas não consegui abrir: {falhou_ao_abrir}")
                _log("Isso costuma ser o Windows barrando um programa sem assinatura digital "
                     "(Controle Inteligente de Aplicativos / antivírus). Veja NOTES_ANTIVIRUS.md.")
                traceback.print_exc()

    if falhou_ao_abrir:
        plano_b = _launch_godot_via_projeto(f"o Corpo exportado não abriu: {falhou_ao_abrir}")
        if plano_b[0] is not None:
            return plano_b
        _avisar_na_tela("Zenith — o Windows bloqueou o Corpo", _texto_corpo_bloqueado(falhou_ao_abrir))
        return None, ""

    _log("Não encontrei o executável do Corpo (Zenith.exe exportado do Godot).")
    _log("Exporte o projeto em body/zenith (Project > Export > Windows Desktop),")
    _log("salve em body/zenith/export/Zenith.exe, ou aponte o caminho em")
    _log("config/settings.json -> 'godot_executable_path'.")
    return None, ""


# CORREÇÃO (execução de código Python quebrada no .exe compilado):
# zenith_executor.py's run_python() chama
# subprocess.run([sys.executable, script_path]) pra rodar o código que
# a IA gerou — isso funciona perfeitamente rodando via "python
# zenith_launcher.py" porque sys.executable É um python.exe de
# verdade. Só que no .exe compilado com PyInstaller, sys.executable é
# o PRÓPRIO Zenith.exe — não existe um python.exe solto pra chamar. Ou
# seja: no .exe compilado, essa chamada não rodava o script gerado —
# abria uma SEGUNDA INSTÂNCIA INTEIRA DO ZENITH, silenciosamente, toda
# vez que a Zenith tentasse "executar código".
#
# A correção é o Zenith.exe saber rodar em "modo script" quando
# chamado com essa flag especial: em vez de abrir o app inteiro, só
# executa o arquivo Python pedido e sai — continua sendo um processo
# separado de verdade (mesmo isolamento de antes), só que agora É
# capaz de rodar o script em vez de reabrir o app. Funciona idêntico
# rodando via "python zenith_launcher.py" ou já compilado.
_RUN_SCRIPT_FLAG = "--zenith-run-script"

def _fluxo_do_processo(fd_std: int):
    """Devolve um fluxo de texto ligado ao canal que o processo PAI abriu (PIPE), ou None.

    Em app Windows SEM console (o nosso .exe), o descritor do CRT (`1`/`2`) não existe: `os.fdopen(1)` falha
    ou devolve um fluxo que engole tudo. O que existe é o HANDLE herdado do processo pai, e é por ele que a
    saída tem que sair. Tentativa 1: Windows + handle. Tentativa 2: descritor normal (Linux ou python.exe)."""
    if os.name == "nt":
        try:
            import ctypes
            import msvcrt
            handle = ctypes.windll.kernel32.GetStdHandle(-10 - fd_std)   # 1 -> -11 (stdout), 2 -> -12 (stderr)
            if handle and handle != -1:
                fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
                return os.fdopen(fd, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
        except Exception:
            pass
    try:
        return os.fdopen(fd_std, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
    except Exception:
        return None


def _garantir_saida_padrao(forcar: bool = False) -> None:
    """CORREÇÃO ("Código executado (sem saída de texto)" mentindo): no .exe compilado em MODO JANELA
    (console=False) o PyInstaller deixa sys.stdout e sys.stderr como None, e aí TODO print() do script
    é descartado sem erro nenhum — o código rodava certo e o Zenith jurava que não tinha saído nada.
    Aqui os canais do processo são religados no PIPE que o Zenith abriu (ver `_fluxo_do_processo`).

    CORREÇÃO 2 (o print() continuava sumindo): este arquivo, no topo, troca sys.stdout/sys.stderr pelo
    zenith_log.txt. Ou seja, no .exe eles NUNCA são None — o conserto acima nem era acionado e todo
    print() do script ia para o LOG, enquanto o Zenith lia um PIPE vazio e respondia "sem saída".
    Por isso `forcar=True` no modo script: ali a saída TEM que ir para o processo pai (o pipe),
    não para o log."""
    for nome, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, nome, None) is not None and not forcar:
            continue
        fluxo = _fluxo_do_processo(fd)
        if fluxo is not None:
            setattr(sys, nome, fluxo)
        # sem canal nenhum: segue sem saída em vez de derrubar o script


def _try_run_as_script_runner() -> bool:
    """Se chamado como `Zenith.exe --zenith-run-script caminho.py`,
    roda esse arquivo e sai — não abre o app. Devolve True se foi esse
    o caso (quem chamou já deve sair do processo em seguida)."""
    if _RUN_SCRIPT_FLAG not in sys.argv:
        return False
    try:
        idx = sys.argv.index(_RUN_SCRIPT_FLAG)
        script_path = sys.argv[idx + 1]
    except IndexError:
        print("[Zenith] --zenith-run-script precisa do caminho do arquivo depois da flag.")
        sys.exit(1)

    _garantir_saida_padrao(forcar=True)
    import runpy
    try:
        runpy.run_path(script_path, run_name="__main__")
        _despejar_saida()
        sys.exit(0)
    except SystemExit as e:
        _despejar_saida()
        raise
    except BaseException as e:
        traceback.print_exc()
        print(f"[Zenith] Erro executando '{script_path}': {e}", file=sys.stderr)
        _despejar_saida()
        sys.exit(1)


def _despejar_saida() -> None:
    """Sem isso, o último print pode ficar no buffer quando o processo termina (a saída chega vazia)."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            if fluxo is not None:
                fluxo.flush()
        except Exception:
            pass


if __name__ == "__main__":
    if _try_run_as_script_runner():
        pass   # _try_run_as_script_runner já chamou sys.exit() — nunca chega aqui de verdade
    else:
        main()
