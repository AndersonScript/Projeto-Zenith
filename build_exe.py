# ============================================================
#  ZENITH — Criado por Anderson
#  build_exe.py — Mesma coisa que build_exe.bat, mas em Python.
#
#  Por quê isso existe: o Windows (Controle de Aplicativo Inteligente/
#  SmartScreen) trata arquivos .bat baixados da internet com MUITA
#  desconfiança — ele bloqueia antes mesmo de você decidir rodar.
#  Um script .py rodado via "python build_exe.py" não dispara esse
#  mesmo bloqueio, porque quem está "executando" é o python.exe (que
#  já é confiável no seu PC), não um script batch direto.
#
#  Rode com: python build_exe.py
# ============================================================

import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=HERE)


def _prepare_export_folder() -> str:
    """Descobre onde o Godot exportou o Corpo, não importa a pasta
    exata, e garante que body/zenith/export/ tenha uma cópia limpa —
    isso existe porque exportar direto em body/zenith/ (a pasta do
    próprio projeto, em vez de body/zenith/export/) é um erro fácil de
    cometer no diálogo de export do Godot, e trava o build inteiro se
    a gente exigir o caminho exato."""
    export_dir = os.path.join(HERE, "body", "zenith", "export")
    project_dir = os.path.join(HERE, "body", "zenith")

    if os.path.isfile(os.path.join(export_dir, "Zenith.exe")):
        return export_dir

    exe_no_lugar_errado = os.path.join(project_dir, "Zenith.exe")
    if os.path.isfile(exe_no_lugar_errado):
        print("[Aviso] Achei Zenith.exe exportado direto em body/zenith/ "
              "(não em body/zenith/export/) — copiando pro lugar certo automaticamente.")
        os.makedirs(export_dir, exist_ok=True)
        for name in ("Zenith.exe", "Zenith.pck", "Zenith.console.exe"):
            src = os.path.join(project_dir, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(export_dir, name))
        for name in os.listdir(project_dir):
            if name.lower().endswith(".dll"):
                shutil.copy2(os.path.join(project_dir, name), os.path.join(export_dir, name))
        return export_dir

    return export_dir  # nenhum dos dois — quem chama decide o aviso


# Pastas dentro de dist/Zenith que são DADO DO USUÁRIO, não saída de build.
# Elas NÃO podem morrer num rebuild: contêm as chaves de API (config/settings.json), o histórico
# das conversas, a memória de longo prazo (memory_db/), o modelo do Whisper já baixado
# (models/, ~464 MB), as criações e o que a Zenith aprendeu (skills/).
_PASTAS_DO_USUARIO = ("config", "memory_db", "models", "creations", "temp", "skills")

# Onde o dado do usuário fica guardado DURANTE o build (fora do dist/, que é apagado).
_RESGATE = os.path.join(HERE, "_dados_do_usuario_resgatados")


def _preservar_dados_do_usuario():
    """Tira o dado do usuário de dentro do dist/ ANTES de apagá-lo.

    BUG REAL CORRIGIDO — e é a causa do "Nenhuma IA configurada" que reaparecia depois de cada
    build (registrado no GUIA_v27_PASSO_A_PASSO.md, seção 9, onde ficou sem explicação):
    o _clean_old_build() apagava a pasta dist/ INTEIRA, e o _copy_config_beside_exe() devolvia
    só o config/ DO PROJETO — que tem o catálogo de provedores, mas NÃO tem o settings.json
    (esse só existe dentro do dist/, criado em tempo de execução). Resultado: cada build novo
    apagava as chaves de API, as conversas, a memória de longo prazo, o modelo do Whisper já
    baixado e as criações. O Zenith abria como instalação nova — sem IA nenhuma configurada.

    A causa não estava no programa, estava no BUILD. É por isso que o Anderson via o problema
    voltar a cada versão nova sem ninguém conseguir explicar.
    """
    dist = os.path.join(HERE, "dist", "Zenith")
    if not os.path.isdir(dist):
        return
    if os.path.isdir(_RESGATE):
        # BUG REAL (achado em 17/10, e ele custou caro): se a pasta de resgate JÁ existe quando este
        # build começa, é porque o build ANTERIOR morreu no meio (Ctrl+C, fechar a janela, energia,
        # ou um segundo build rodando ao mesmo tempo). Aí o que está aqui é o dado do usuário MAIS
        # NOVO que existe — e não pode ser apagado. Antes esta linha era shutil.rmtree(_RESGATE): o
        # build seguinte APAGAVA as chaves de API, as conversas e os 464 MB de modelos do Anderson.
        print("[Limpeza] Achei dados guardados por um build interrompido — devolvendo ao dist/ antes de continuar...")
        if not _restaurar_dados_do_usuario():
            print("[ERRO] Build CANCELADO: os dados do build anterior ainda não voltaram para o dist/.")
            print(f"       Eles estão a salvo em {_RESGATE}. Rode o build de novo quando resolver.")
            sys.exit(1)
    resgatadas = []
    for nome in _PASTAS_DO_USUARIO:
        origem = os.path.join(dist, nome)
        if not os.path.isdir(origem):
            continue
        os.makedirs(_RESGATE, exist_ok=True)
        try:
            shutil.move(origem, os.path.join(_RESGATE, nome))
            resgatadas.append(nome)
        except Exception as e:
            print(f"[Aviso] Não consegui guardar '{nome}' antes do build ({e}).")
    if resgatadas:
        print(f"[Limpeza] Dados do usuário guardados a salvo: {', '.join(resgatadas)}")
        print("[Limpeza] Suas chaves de API, conversas e memória voltam no fim do build.")


def _inventario(pasta: str) -> list:
    """Lista (caminho relativo, tamanho) de cada arquivo de uma pasta, ANTES de mexer nela.
    Serve para conferir, depois da devolução, se TUDO chegou ao destino."""
    itens = []
    for raiz, _dirs, arquivos in os.walk(pasta):
        for nome in arquivos:
            caminho = os.path.join(raiz, nome)
            try:
                itens.append((os.path.relpath(caminho, pasta), os.path.getsize(caminho)))
            except OSError:
                itens.append((os.path.relpath(caminho, pasta), -1))
    return itens


def _conferir_devolucao(inventario: list, destino: str) -> list:
    """Devolve os arquivos do inventário que NÃO chegaram ao destino (ou chegaram truncados)."""
    faltando = []
    for rel, tamanho in inventario:
        alvo = os.path.join(destino, rel)
        try:
            if not os.path.isfile(alvo) or (tamanho >= 0 and os.path.getsize(alvo) != tamanho):
                faltando.append(rel)
        except OSError:
            faltando.append(rel)
    return faltando


def _restaurar_dados_do_usuario() -> bool:
    """Devolve ao dist/ novo tudo que o _preservar_dados_do_usuario() guardou.
    O que veio do resgate SEMPRE ganha do que o build acabou de copiar — é o dado do usuário.

    v1.0 — BUG GRAVE CORRIGIDO (achado pelo Claude e reproduzido): antes, quando a devolução de
    uma pasta falhava (arquivo em uso, antivírus, disco cheio), o código avisava "os dados
    continuam em _resgate" e NA LINHA SEGUINTE apagava a pasta de resgate sem condição. Ou seja:
    o aviso era mentira e o dado do usuário (chaves, conversas, modelos de 464 MB) morria — a
    mesma classe de perda que já custou caro neste projeto.

    Agora só apaga o resgate quando TODOS os arquivos chegaram ao destino E foram CONFERIDOS
    (existência + tamanho). Se qualquer coisa falhar, o resgate fica intacto, o caminho dele é
    mostrado em português e a função devolve False — quem chama ABORTA o build em vez de seguir.

    Devolve True quando não havia nada a devolver ou quando tudo foi devolvido e conferido."""
    dist = os.path.join(HERE, "dist", "Zenith")
    if not os.path.isdir(_RESGATE):
        return True
    os.makedirs(dist, exist_ok=True)      # v29: também é chamada antes do build (build anterior interrompido)

    # O inventário é tirado ANTES de mover (depois do move o arquivo não está mais na origem).
    planos = {nome: _inventario(os.path.join(_RESGATE, nome)) for nome in os.listdir(_RESGATE)}

    devolvidas, falharam = [], []
    for nome, inventario in planos.items():
        origem = os.path.join(_RESGATE, nome)
        destino = os.path.join(dist, nome)
        try:
            if nome == "config" or os.path.isdir(destino):
                shutil.copytree(origem, destino, dirs_exist_ok=True)   # mescla por cima
            else:
                shutil.move(origem, destino)                            # muda de lugar (rápido)
        except Exception as e:
            falharam.append(nome)
            print(f"[Aviso] Não consegui devolver '{nome}' ({e}).")
        faltando = _conferir_devolucao(inventario, destino)
        if faltando:
            falharam.append(nome)
            print(f"[Aviso] '{nome}': {len(faltando)} arquivo(s) não chegaram ao destino "
                  f"(ex.: {faltando[0]}).")
        elif nome not in falharam:
            devolvidas.append(nome)

    if falharam:
        print("")
        print("=" * 60)
        print("[ERRO] Não consegui devolver TODOS os seus dados para o dist/.")
        print(f"        Pastas com problema: {', '.join(sorted(set(falharam)))}")
        print("        Seus dados NÃO foram apagados — eles estão guardados inteiros em:")
        print(f"        {_RESGATE}")
        print("        Nada foi perdido. Feche o Zenith (e o antivírus, se estiver segurando")
        print("        algum arquivo) e rode o build de novo: ele devolve o que faltou.")
        print("=" * 60)
        return False

    shutil.rmtree(_RESGATE, ignore_errors=True)
    if devolvidas:
        print(f"[Zenith] Dados do usuário devolvidos e conferidos: {', '.join(devolvidas)}")
    return True


def _clean_old_build():
    """Apaga build/, dist/ e o .spec de builds anteriores ANTES de
    começar. O PyInstaller guarda cache nessas pastas e às vezes não
    percebe que algo mudou (ex: a pasta body/zenith/export que antes
    não existia) — apagar tudo garante uma build 100% do zero toda vez,
    sem sobra de versão antiga misturada.

    ANTES de apagar, o dado do usuário é resgatado (ver _preservar_dados_do_usuario):
    dist/ deixa de ser descartável."""
    _preservar_dados_do_usuario()
    for name in ("build", "dist"):
        path = os.path.join(HERE, name)
        if os.path.isdir(path):
            print(f"[Limpeza] Apagando {path}...")
            shutil.rmtree(path, ignore_errors=True)
    spec = os.path.join(HERE, "Zenith.spec")
    if os.path.isfile(spec):
        print(f"[Limpeza] Apagando {spec}...")
        os.remove(spec)


def _pip_env() -> dict:
    """Mesma proteção do zenith_bootstrap.py: desliga a saída colorida
    do pip, que quebra sozinha em ambientes onde o Windows bloqueia a
    DLL de _ctypes — sem isso, o pip enche o console de tracebacks
    "Logging error" e esconde se a instalação real deu certo ou não."""
    env = os.environ.copy()
    env["PIP_NO_COLOR"] = "1"
    env["NO_COLOR"] = "1"
    env["PIP_PROGRESS_BAR"] = "off"
    return env


def _ensure_build_tooling():
    """pywin32-ctypes é exigido pelo PyInstaller pra embutir o ícone
    num .exe no Windows — não é dependência do Zenith em si, é
    ferramenta de build. Sem ela, o PyInstaller falha com
    'Could not import pywintypes or win32api'. Instala sozinho se
    faltar, em vez de só apontar o comando e travar."""
    try:
        import win32ctypes.pywin32.pywintypes  # noqa: F401
        return
    except Exception:
        pass
    print("[Aviso] Faltando pywin32-ctypes (o PyInstaller precisa disso pra "
          "embutir o ícone). Instalando automaticamente...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "pywin32-ctypes"],
                        check=True, env=_pip_env())
    except Exception as e:
        print(f"[Aviso] Não consegui instalar sozinho ({e}). "
              f"Rode manualmente: pip install pywin32-ctypes")
        return
    # Confirma de verdade em vez de assumir que deu certo — se ainda
    # não importar depois do pip install, foi o mesmo bloqueio de DLL
    # que já vem afetando outras coisas no seu ambiente, não um bug
    # deste script.
    try:
        import win32ctypes.pywin32.pywintypes  # noqa: F401
    except Exception:
        print("[Aviso] pywin32-ctypes foi instalado mas ainda não importa. "
              "Isso é o mesmo bloqueio de DLL (_ctypes) que já apareceu antes "
              "no seu ambiente — não é algo que este script resolve sozinho. "
              "O build vai tentar seguir mesmo assim.")


def _copy_config_beside_exe():
    """CORREÇÃO (bug do executável): garante que config/ exista AO LADO
    do Zenith.exe (dist/Zenith/config/), não escondido dentro de
    _internal/. Só copia se ainda não existir lá — não sobrescreve uma
    config que o usuário final já tenha personalizado num build anterior."""
    dist_config = os.path.join(HERE, "dist", "Zenith", "config")
    src_config = os.path.join(HERE, "config")
    if os.path.isdir(dist_config):
        return
    if os.path.isdir(src_config):
        shutil.copytree(src_config, dist_config)
        print(f"[Zenith] config/ copiada pra {dist_config}")


def _copy_godot_export_beside_exe(export_dir: str):
    """CORREÇÃO (bug do executável: 'Não encontrei o executável do
    Corpo'): copia o Godot já exportado pra dist/Zenith/body/zenith/
    export/, do lado de fora do _internal — mesmo raciocínio de
    _copy_config_beside_exe(), pro zenith_launcher.py conseguir achar
    o Corpo em runtime."""
    dist_export = os.path.join(HERE, "dist", "Zenith", "body", "zenith", "export")
    if os.path.isdir(dist_export):
        return
    if os.path.isdir(export_dir) and os.listdir(export_dir):
        shutil.copytree(export_dir, dist_export)
        print(f"[Zenith] Corpo (Godot) copiado pra {dist_export}")


def _copy_godot_project_beside_exe():
    """v18 — a importação automática de avatar (brain/zenith_vrm_import.py) precisa
    do PROJETO Godot completo ao lado do .exe, não só do Corpo exportado: é ele que
    o Godot em linha de comando importa e reempacota. Copia body/zenith inteiro pra
    dist/Zenith/body/zenith/ — MESMA posição relativa de quando se roda pelo código,
    então o Zenith acha tudo sem configuração (projeto em body/zenith, .pck em
    body/zenith/export). Importante: os avatares que já existem (Zenith, Cypher...)
    TÊM que ir junto, senão sumiriam do .pck novo na primeira importação.
    Fica de fora: export/ (copiada à parte, logo abaixo) e cache só do editor."""
    src = os.path.join(HERE, "body", "zenith")
    dst = os.path.join(HERE, "dist", "Zenith", "body", "zenith")
    if not os.path.isfile(os.path.join(src, "project.godot")):
        print("[Aviso] body/zenith/project.godot não existe — o .exe vai sair SEM o projeto "
              "Godot, então 'Adicionar avatar' não vai conseguir importar sozinho.")
        return
    if os.path.isfile(os.path.join(dst, "project.godot")):
        return

    def _ignorar(pasta, nomes):
        pasta_n = os.path.normpath(pasta)
        fora = set()
        if pasta_n == os.path.normpath(src):
            fora |= {"export", ".git"}                       # só no topo: outras 'export' ficam
        if pasta_n == os.path.normpath(os.path.join(src, ".godot")):
            fora |= {"editor", "shader_cache"}              # cache do EDITOR, não serve no dist
        # No topo do projeto, o editor exporta Zenith.exe/.pck (export_path="./Zenith.exe"):
        # não precisam ir de novo pro dist (o Corpo já vai em body/zenith/export/).
        return [n for n in nomes if n in fora or n.endswith(".tmp") or n == "__pycache__"
                or (pasta_n == os.path.normpath(src) and n.lower().endswith((".exe", ".pck", ".bak")))]

    shutil.copytree(src, dst, ignore=_ignorar)
    tem_cache = os.path.isdir(os.path.join(dst, ".godot", "imported"))
    print(f"[Zenith] Projeto Godot copiado pra {dst}")
    if not tem_cache:
        print("[Aviso] body/zenith/.godot/imported não existe (abra o projeto no editor uma vez). "
              "Sem esse cache, a PRIMEIRA importação de avatar no .exe reimporta tudo e demora "
              "vários minutos.")


def _copy_godot_editor_beside_exe():
    """v18 — opcional: se existir tools/godot/ ao lado do build_exe.py (com o
    Godot_v4.x_win64.exe do EDITOR dentro), vai junto pro dist e o Zenith acha sozinho
    — 'Adicionar avatar' funciona pra quem só tem o .exe. O Godot é MIT, pode ser
    redistribuído (mantenha a licença junto). Sem a pasta, o Zenith procura o Godot
    instalado na máquina (Downloads, Desktop, PATH...) ou pede o caminho 1 vez."""
    src = os.path.join(HERE, "tools", "godot")
    dst = os.path.join(HERE, "dist", "Zenith", "tools", "godot")
    if not os.path.isdir(src) or not os.listdir(src):
        print("[Zenith] (tools/godot/ não existe — o .exe vai depender de um Godot instalado na máquina "
              "pra 'Adicionar avatar'. Pra levar junto, coloque o Godot_v4.x_win64.exe em tools/godot/ "
              "e rode o build de novo.)")
        return
    if not os.path.isdir(dst):
        shutil.copytree(src, dst)
        print(f"[Zenith] Editor do Godot copiado pra {dst}")


def _copy_rvc_installer_beside_exe():
    """v20 — leva o instalar_rvc.bat pra dist/Zenith: rodado LÁ, ele cria o Python 3.10 do RVC em
    dist/Zenith/tools/rvc/venv, que é onde o Zenith.exe procura sozinho."""
    src = os.path.join(HERE, "instalar_rvc.bat")
    dst_dir = os.path.join(HERE, "dist", "Zenith")
    if os.path.isfile(src) and os.path.isdir(dst_dir):
        shutil.copy2(src, os.path.join(dst_dir, "instalar_rvc.bat"))
        print("[Zenith] instalar_rvc.bat copiado pra dist/Zenith (voz RVC opcional).")


def _semear_habilidades():
    """v1.11 — leva as habilidades da pasta skills/ do projeto para dist/Zenith/skills.

    `skills/` é pasta do usuário, e um dist novo nasce sem ela: a habilidade existia no
    projeto e "não existia" dentro do programa (a Zenith respondia "não tenho essa
    habilidade"). Copia SÓ o que falta — habilidade que já está no dist nunca é sobrescrita
    (pode ter sido editada ou criada pela própria Zenith)."""
    origem = os.path.join(HERE, "skills")
    destino = os.path.join(HERE, "dist", "Zenith", "skills")
    if not os.path.isdir(origem) or not os.path.isdir(os.path.join(HERE, "dist", "Zenith")):
        return
    os.makedirs(destino, exist_ok=True)
    copiados = []
    for nome in sorted(os.listdir(origem)):
        if not nome.endswith(".py"):
            continue
        alvo = os.path.join(destino, nome)
        if os.path.exists(alvo):
            continue
        try:
            shutil.copy2(os.path.join(origem, nome), alvo)
            copiados.append(nome[:-3])
        except OSError:
            pass
    if copiados:
        print(f"[Zenith] Habilidades de fábrica copiadas para dist: {', '.join(copiados)}.")


def version_info_text(versao: str = "v24") -> str:
    """Conteúdo do arquivo de metadados de versão que o PyInstaller grava DENTRO do Zenith.exe (aba "Detalhes" do
    Windows: nome do produto, descrição, versão). Um .exe sem nenhum metadado é um dos sinais que os motores de
    "aprendizado de máquina" dos antivírus pesam contra arquivos desconhecidos; metadados honestos não resolvem o
    alerta sozinhos, mas tiram esse ponto da conta. (É texto Python no formato `VSVersionInfo` do PyInstaller.)"""
    nums = [int(n) for n in re.findall(r"\d+", versao)][:4]
    nums = (nums + [0, 0, 0, 0])[:4]
    tup = tuple(nums)
    ver = ".".join(str(n) for n in nums)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable(u'041604B0', [
        StringStruct(u'CompanyName', u'Zenith'),
        StringStruct(u'FileDescription', u'Zenith'),
        StringStruct(u'FileVersion', u'{ver}'),
        StringStruct(u'InternalName', u'Zenith'),
        StringStruct(u'LegalCopyright', u'Zenith'),
        StringStruct(u'OriginalFilename', u'Zenith.exe'),
        StringStruct(u'ProductName', u'Zenith'),
        StringStruct(u'ProductVersion', u'{ver}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1046, 1200])])
  ]
)
"""


def _write_version_file() -> str:
    try:
        from brain.zenith_version import VERSAO
    except Exception:
        VERSAO = "v24"
    pasta = os.path.join(HERE, "build")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, "zenith_version_info.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(version_info_text(VERSAO))
    return caminho


def sha256_de(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _escrever_leia_me_primeira_vez(pasta_dist: str, publico: bool = False):
    """v26 — deixa um LEIA-ME ao lado do .exe: a 1ª abertura precisa ser como administrador (o Anderson descobriu que,
    sem isso, o .exe não funciona). Assim quem receber a pasta sabe, mesmo sem falar com ele."""
    try:
        if publico:   # v1.4 — edição Pública: quem instala pelo instalador não precisa ser administrador
            texto = (
                "ZENITH — LEIA ANTES DE ABRIR\r\n"
                "============================\r\n\r\n"
                "1) Abra o Zenith pelo atalho do menu Iniciar (ou da area de trabalho). Nao precisa ser administrador.\r\n\r\n"
                "2) Se o Windows ou o antivirus barrar o programa: leia NOTES_ANTIVIRUS.md. O instalador ainda nao tem\r\n"
                "   assinatura digital; confira o SHA-256 na pagina de download antes de abrir.\r\n"
            )
            os.makedirs(pasta_dist, exist_ok=True)
            with open(os.path.join(pasta_dist, "LEIA-ME_PRIMEIRA_VEZ.txt"), "w", encoding="utf-8", newline="") as f:
                f.write(texto)
            return
        texto = (
            "ZENITH — LEIA ANTES DE ABRIR\r\n"
            "============================\r\n\r\n"
            "1) Na PRIMEIRA vez, abra o Zenith.exe COMO ADMINISTRADOR:\r\n"
            "   clique com o botao direito em Zenith.exe > \"Executar como administrador\".\r\n"
            "   (Se voce abrir normalmente, o Zenith pergunta e reabre sozinho como administrador se voce aceitar.)\r\n\r\n"
            "2) Depois dessa primeira vez, pode abrir normalmente, com duplo clique.\r\n\r\n"
            "3) Se o Windows ou o antivirus barrar: leia NOTES_ANTIVIRUS.md.\r\n"
        )
        os.makedirs(pasta_dist, exist_ok=True)
        with open(os.path.join(pasta_dist, "LEIA-ME_PRIMEIRA_VEZ.txt"), "w", encoding="utf-8", newline="") as f:
            f.write(texto)
    except OSError as e:
        print(f"[Aviso] Nao consegui escrever o LEIA-ME_PRIMEIRA_VEZ.txt ({e}).")


def _escrever_versao_build(pasta_dist: str):
    """Grava dist/Zenith/VERSAO_BUILD.txt — lido pelo brain/zenith_version.py.

    v1.0 (A12): o `/versao` passa a mostrar TAMBÉM a data/hora do build. Sem isso, depois de
    recompilar duas vezes no mesmo dia, não dava pra saber qual .exe estava aberto.
    """
    import datetime as _dt
    try:
        from brain.zenith_version import VERSAO
    except Exception:
        VERSAO = "v1.0"
    agora = _dt.datetime.now()
    try:
        os.makedirs(pasta_dist, exist_ok=True)
        with open(os.path.join(pasta_dist, "VERSAO_BUILD.txt"), "w", encoding="utf-8") as f:
            f.write(f"{agora.strftime('%d/%m/%Y %H:%M')} — {VERSAO} — Python {sys.version.split()[0]}\n")
    except OSError as e:
        print(f"[Aviso] Não consegui gravar a data do build ({e}).")


def _avisar_python_incompativel():
    """A12.5 — o Anderson já compilou com Python novo demais e o PyInstaller falhou de um jeito confuso."""
    if sys.version_info >= (3, 14):
        print("")
        print("=" * 60)
        print(f"[ATENÇÃO] Você está compilando com Python {sys.version.split()[0]}.")
        print("           O build do Zenith é feito e testado com Python 3.12 ou 3.13.")
        print("           Em versões mais novas o PyInstaller pode falhar no meio — se falhar,")
        print("           instale o Python 3.13 e rode: py -3.13 build_exe.py")
        print("=" * 60)


def _escrever_hashes(pasta_dist: str):
    """Grava dist/Zenith/HASHES_SHA256.txt com o hash de cada .exe/.pck. Serve pra: (1) conferir no VirusTotal se um
    arquivo igual já é conhecido; (2) preencher o formulário de falso positivo do antivírus; (3) provar que a cópia que
    chegou a outro PC é a mesma que você gerou. Cada build novo = hash novo = o antivírus nunca viu: é por isso que o
    alerta volta a cada build."""
    linhas = []
    for raiz, _dirs, arquivos in os.walk(pasta_dist):
        if os.sep + "_internal" in raiz:
            continue                                     # são centenas de DLLs/bibliotecas conhecidas
        for nome in sorted(arquivos):
            if nome.lower().endswith((".exe", ".pck")):
                p = os.path.join(raiz, nome)
                linhas.append(f"{sha256_de(p)}  {os.path.relpath(p, pasta_dist)}")
    if linhas:
        with open(os.path.join(pasta_dist, "HASHES_SHA256.txt"), "w", encoding="utf-8") as f:
            f.write("SHA-256 dos programas deste build (cada build novo muda estes números):\n" + "\n".join(linhas) + "\n")
        print(f"[Zenith] Hashes gravados em dist/Zenith/HASHES_SHA256.txt ({len(linhas)} arquivo(s)).")


def _warn_if_admin():
    """AJUSTE (aviso novo do PyInstaller): "Running PyInstaller as admin
    is not necessary nor sensible... PyInstaller 7.0 will block this."
    Não trava o build (ainda funciona hoje), só avisa ALTO agora
    enquanto dá tempo de mudar o hábito — se você tiver rodando isso
    num terminal "Executar como administrador", o build vai simplesmente
    parar de funcionar quando o PyInstaller for atualizado pra 7.0.
    """
    try:
        is_admin = os.name == "nt" and __import__("ctypes").windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if is_admin:
        print("=" * 60)
        print(" [Aviso] Você está rodando isso num terminal de ADMINISTRADOR.")
        print(" O PyInstaller já avisa que isso não é necessário nem")
        print(" recomendado, e a versão 7.0 dele vai BLOQUEAR builds assim.")
        print(" Feche esse terminal e abra um normal (sem 'Executar como")
        print(" administrador') pra rodar build_exe.py.")
        print("=" * 60)


# Módulos que o .exe PRECISA ter para o Zenith funcionar de verdade (nome importável, para que serve).
_MODULOS_OBRIGATORIOS = (
    ("edge_tts", "a voz da Zenith"),
    ("pygame", "tocar o áudio da voz"),
    ("faster_whisper", "transcrever o microfone"),
    ("sounddevice", "acessar o microfone"),
    ("websockets", "a Ponte com o Corpo (Godot)"),
    ("chromadb", "memória de longo prazo"),
    ("onnxruntime", "memória de longo prazo (vetores)"),
    ("tokenizers", "memória de longo prazo (vetores)"),
    ("google.genai", "IA do Google (Gemini)"),
    ("openai", "IAs compatíveis com OpenAI (Groq, OpenRouter, IA local)"),
    ("PIL", "imagem, papel de parede e autorretrato"),
    ("cv2", "câmera e quadro de vídeo"),
)

# Módulos bons de ter: sem eles o Zenith roda, só a função específica some.
_MODULOS_OPCIONAIS = (
    ("imageio_ffmpeg", "edição de vídeo (/video)"),
    ("pypdf", "ler PDF"),
    ("sympy", "conta exata (/derivar, /integrar, /limite)"),
    ("plyer", "notificação nativa do Windows"),
    ("mss", "captura de tela"),
    ("serial", "Arduino / ESP32"),
)

_SCRIPT_DE_CONFERENCIA = '''# arquivo temporário, gerado e apagado pelo build_exe.py
import importlib
import importlib.metadata as md

DESTINO = {destino!r}
ITENS = {itens!r}

linhas = []
for nome, para_que, obrigatorio in ITENS:
    try:
        importlib.import_module(nome)
        try:
            versao = md.version(nome)
        except Exception:
            versao = "-"
        linhas.append("OK|" + nome + "|" + versao)
    except Exception:
        linhas.append(("FALTA" if obrigatorio else "OPCIONAL") + "|" + nome + "|" + para_que)

with open(DESTINO, "w", encoding="utf-8") as f:
    f.write("\\n".join(linhas) + "\\n")
'''


def explicar_falha_pip(saida: str, admin: bool = False, py: tuple = None) -> list:
    """v1.2 — lê o que o pip disse e devolve linhas de ajuda em português (o motivo provável e o que fazer).

    Nasceu do erro real do Anderson: `[WinError 5] Acesso negado: ...\\.venv\\Lib\\site-packages\\PIL\\_avif.cp314-win_amd64.pyd`
    num ambiente .venv novo, com Python 3.14, num terminal de administrador. Isso quase nunca é erro do Zenith: é o Windows
    (antivírus/Defender escaneando ou barrando o arquivo recém-baixado) ou um programa ainda usando o .venv.
    """
    py = py or sys.version_info[:2]
    baixo = (saida or "").lower()
    linhas = []
    if "winerror 5" in baixo or "acesso negado" in baixo or "access is denied" in baixo or "permissionerror" in baixo:
        linhas += [
            "MOTIVO PROVÁVEL: o Windows negou acesso a um arquivo (.pyd/.dll) na hora de instalar. Quase sempre é o antivírus/Defender",
            "segurando ou barrando o arquivo recém-baixado, ou algum programa ainda usando este ambiente (.venv).",
            "O QUE FAZER, nesta ordem (para no primeiro que resolver):",
            "  1) Feche o Zenith, o Godot e qualquer Python aberto (Gerenciador de Tarefas > procure python.exe / Zenith.exe).",
            "  2) Abra um terminal NORMAL (sem 'Executar como administrador') e rode o build de novo — o pip continua de onde parou",
            "     e, muitas vezes, na segunda vez o antivírus já terminou de escanear e passa.",
            "  3) Se repetir: Segurança do Windows > Proteção contra vírus > Gerenciar configurações > Exclusões > adicione a pasta",
            "     do Zenith (ex.: C:\\Zenith). Depois rode o build de novo.",
            "  4) Se ainda repetir: apague a pasta .venv e crie de novo com Python 3.13:  py -3.13 -m venv .venv",
            "     e depois  .venv\\Scripts\\python.exe build_exe.py",
        ]
        if admin:
            linhas.append("  (Você está num terminal de administrador: isso também atrapalha o PyInstaller — use um terminal normal.)")
    if "no matching distribution" in baixo or "could not find a version" in baixo or "metadata-generation-failed" in baixo:
        linhas += ["MOTIVO PROVÁVEL: alguma biblioteca ainda não tem versão pronta para o seu Python.",
                   "O QUE FAZER: instale o Python 3.13 (ou 3.12) e rode:  py -3.13 build_exe.py"]
    if "microsoft visual c++" in baixo or "vcvarsall" in baixo or "build tools" in baixo:
        linhas += ["MOTIVO PROVÁVEL: uma biblioteca tentou ser compilada e falta o 'Microsoft C++ Build Tools'.",
                   "O QUE FAZER: normalmente basta usar o Python 3.13 (as bibliotecas já vêm prontas). Só instale o Build Tools se for inevitável."]
    if "connectionerror" in baixo or "timed out" in baixo or "name or service not known" in baixo or "getaddrinfo" in baixo \
            or "max retries exceeded" in baixo:
        linhas += ["MOTIVO PROVÁVEL: sem internet (ou internet bloqueada) para baixar as bibliotecas.",
                   "O QUE FAZER: confira a conexão e rode o build de novo."]
    if not linhas and py >= (3, 14):
        linhas += ["DICA: você está no Python %d.%d; o Zenith é feito e testado com 3.12/3.13. Se o erro persistir, tente:  py -3.13 build_exe.py" % py[:2]]
    return linhas


def _rodar_pip_mostrando(req: str):
    """Roda o pip mostrando a saída ao vivo (como antes) E guardando o final dela para explicar a falha. -> (código, texto)."""
    import collections
    proc = subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", req, "--disable-pip-version-check", "--no-input"],
                            cwd=HERE, env=_pip_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace")
    ultimas = collections.deque(maxlen=80)
    for linha in proc.stdout:
        print(linha, end="")
        ultimas.append(linha)
    proc.wait()
    return proc.returncode, "".join(ultimas)


def _garantir_dependencias():
    """Instala o requirements.txt ANTES de empacotar, e ABORTA se não conseguir.

    PEDIDO DO ANDERSON, ao pé da letra: "pede na hora de construir a build do executavel
    abaixar e salvar todas as bibliotecas de uma vez".

    Antes, este script só AVISAVA quando faltava imageio-ffmpeg, pypdf ou sympy e seguia em
    frente — saía um .exe capenga (sem edição de vídeo, sem PDF, sem /derivar) e a pessoa só
    descobria quando a função falhava no meio do uso. E o zenith_bootstrap.py PULA a checagem
    inteira quando o programa está empacotado (_is_frozen()), então o .exe não tinha como se
    defender sozinho. Agora: instala tudo de uma vez e, se o pip falhar, NÃO gera .exe nenhum.
    """
    req = os.path.join(HERE, "requirements.txt")
    if not os.path.isfile(req):
        print("[Zenith/build] aviso: requirements.txt não encontrado — pulando a checagem de dependências.")
        return
    print("[Zenith/build] Garantindo as dependências (pode demorar na 1ª vez)...")
    try:
        codigo, saida = _rodar_pip_mostrando(req)
        if codigo != 0:
            try:
                admin = os.name == "nt" and bool(__import__("ctypes").windll.shell32.IsUserAnAdmin())
            except Exception:
                admin = False
            print("\n" + "=" * 60)
            print(f"[ERRO] O pip falhou (código {codigo}) ao instalar o requirements.txt.")
            print("[ERRO] BUILD ABORTADO DE PROPÓSITO.")
            print("[ERRO] É melhor não ter .exe nenhum do que um .exe sem voz, sem vídeo ou sem PDF:")
            print("[ERRO] esse furo não aparece na hora de construir, só na hora de usar.")
            ajuda = explicar_falha_pip(saida, admin=admin)
            if ajuda:
                print("-" * 60)
                for linha in ajuda:
                    print(linha)
                print("-" * 60)
            print("[ERRO] Resolva o erro do pip acima e rode o build de novo.")
            print("=" * 60)
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n[ERRO] Falha inesperada ao instalar as dependências: {e}")
        sys.exit(1)
    print("[Zenith/build] Dependências OK.")


def _verificar_exe_empacotado() -> bool:
    """Abre o .exe RECÉM-GERADO e pergunta a ele quais bibliotecas ele tem de verdade.

    Por que não basta olhar o tamanho da pasta dist/: o PyInstaller empacota os módulos Python
    puros dentro do PRÓPRIO Zenith.exe (o edge-tts, por exemplo, aparece 11 vezes dentro do
    binário e NÃO tem nenhuma pasta _internal/edge_tts). Então o único teste honesto é EXECUTAR
    o arquivo que o usuário vai abrir.

    Usa o modo script que o launcher já tem (`Zenith.exe --zenith-run-script arquivo.py`), que
    não abre janela e não pede administrador — só roda o arquivo e sai. A resposta é gravada num
    arquivo de texto próprio, para não depender do log da sessão do usuário.
    """
    pasta = os.path.join(HERE, "dist", "Zenith")
    exe = os.path.join(pasta, "Zenith.exe")
    if not os.path.isfile(exe):
        print("[Zenith/build] aviso: não achei o .exe gerado — não deu para conferir o que entrou nele.")
        return True

    script = os.path.join(pasta, "_conferir_build.py")
    resultado = os.path.join(pasta, "_conferir_build.txt")
    itens = ([(n, p, True) for n, p in _MODULOS_OBRIGATORIOS]
             + [(n, p, False) for n, p in _MODULOS_OPCIONAIS])
    try:
        with open(script, "w", encoding="utf-8") as f:
            f.write(_SCRIPT_DE_CONFERENCIA.format(destino=resultado, itens=itens))
        if os.path.exists(resultado):
            os.remove(resultado)
        subprocess.run([exe, "--zenith-run-script", script], cwd=pasta, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[Zenith/build] aviso: não consegui executar o .exe para conferir ({e}).")
        return True

    faltando, opcionais_fora, linhas_lidas = [], [], 0
    try:
        with open(resultado, "r", encoding="utf-8") as f:
            for linha in f.read().splitlines():
                partes = linha.split("|")
                if len(partes) < 3:
                    continue
                linhas_lidas += 1
                estado, nome, extra = partes[0], partes[1], partes[2]
                if estado == "OK":
                    print(f"[Zenith/build]   ok  {nome} {extra}")
                elif estado == "FALTA":
                    faltando.append(f"{nome} ({extra})")
                else:
                    opcionais_fora.append(f"{nome} ({extra})")
    except Exception as e:
        print(f"[Zenith/build] aviso: o .exe não deixou resposta legível ({e}).")
        return True
    finally:
        for p in (script, resultado):
            try:
                os.remove(p)
            except OSError:
                pass

    if linhas_lidas == 0:
        print("[Zenith/build] aviso: o .exe não respondeu à conferência — não deu para verificar.")
        return True
    if opcionais_fora:
        print("[Zenith/build] Sem estas (opcionais, o resto funciona): " + "; ".join(opcionais_fora))
    if faltando:
        print("\n" + "=" * 60)
        print("[ERRO] O .exe foi gerado MAS está sem bibliotecas OBRIGATÓRIAS:")
        for item in faltando:
            print(f"[ERRO]   - {item}")
        print("[ERRO] Abra o Zenith assim e essas funções vão falhar. NÃO distribua este build.")
        print("=" * 60)
        return False
    print("[Zenith/build] Verificação do .exe: todas as bibliotecas obrigatórias estão dentro dele. OK")
    return True


# ---------------------------------------------------------------------------------------------------------------
# v1.4 — EDIÇÕES (Pública × Admin). A edição é gravada em edition.json e vai junto no pacote; ver brain/zenith_edicao.py
#   python build_exe.py --edicao publico     (a que vai pro GitHub/instalador: sem nada do dono)
#   python build_exe.py --edicao admin       (a do dono)
# Na Pública, avatares .vrm só entram se o dono CONFIRMAR que pode redistribuir: --confirmo-avatares-livres
# ---------------------------------------------------------------------------------------------------------------
def _edicao_pedida(argv=None) -> str:
    argv = list(sys.argv[1:] if argv is None else argv)
    for i, a in enumerate(argv):
        if a.startswith("--edicao="):
            return a.split("=", 1)[1].strip().lower()
        if a == "--edicao" and i + 1 < len(argv):
            return argv[i + 1].strip().lower()
    return ""


def _aplicar_edicao_do_build(argv=None, pasta=None) -> str:
    """Grava edition.json se o usuário pediu --edicao; devolve a edição que vale ('publico' | 'admin')."""
    from brain import zenith_edicao
    pasta = pasta or HERE
    pedida = _edicao_pedida(argv)
    if pedida:
        if pedida not in ("publico", "público", "admin"):
            print(f"[ERRO] --edicao {pedida!r} não existe. Use: --edicao publico  ou  --edicao admin")
            sys.exit(1)
        zenith_edicao.gravar(pasta, pedida)
        print(f"[Zenith/build] Edição gravada: {zenith_edicao.edicao(pasta)}")
    return zenith_edicao.edicao(pasta)


def _avatares_do_projeto(pasta=None) -> list:
    pasta = pasta or HERE
    av = os.path.join(pasta, "body", "zenith", "addons", "avatars")
    try:
        return sorted(f for f in os.listdir(av) if f.lower().endswith(".vrm"))
    except OSError:
        return []


def _conferir_avatares_publicos(argv=None, pasta=None) -> bool:
    """Edição Pública: um .vrm dentro do projeto vai DENTRO do instalador. Só segue se o dono confirmar que tem o direito."""
    avatares = _avatares_do_projeto(pasta)
    if not avatares:
        print("[Zenith/build] Edição Pública: nenhum avatar .vrm na pasta — o Corpo precisa de UM avatar seu (ver body/zenith/addons/avatars/LEIA-ME.md).")
        return True
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--confirmo-avatares-livres" in argv:
        print(f"[Zenith/build] Você confirmou que pode redistribuir: {', '.join(avatares)}")
        return True
    print("=" * 60)
    print("[PARADO] Edição Pública: estes avatares iriam DENTRO do instalador que qualquer pessoa vai baixar:")
    for a in avatares:
        print(f"         - {a}")
    print("         Só distribua modelo que VOCÊ criou ou cuja licença permite redistribuir (assets/LICENCAS.md).")
    print("         Se for só o seu: rode de novo com  --confirmo-avatares-livres")
    print("=" * 60)
    return False


def _copiar_edition_json():
    """Leva o edition.json (se existir) para dist/Zenith, ao lado do .exe — é de lá que o programa lê a edição."""
    origem = os.path.join(HERE, "edition.json")
    if os.path.isfile(origem):
        destino = os.path.join(HERE, "dist", "Zenith")
        os.makedirs(destino, exist_ok=True)
        shutil.copy2(origem, os.path.join(destino, "edition.json"))


def main():
    edicao_do_build = _aplicar_edicao_do_build()          # v1.4
    if edicao_do_build == "publico" and not _conferir_avatares_publicos():
        sys.exit(1)
    _warn_if_admin()
    _avisar_python_incompativel()        # v1.0 (A12.5): Python 3.14+ pode quebrar o PyInstaller
    _garantir_dependencias()
    _clean_old_build()
    _ensure_build_tooling()
    icon = os.path.join(HERE, "assets", "zenith_icon.ico")
    export_dir = _prepare_export_folder()

    # v15 — CORREÇÃO: antes esta flag ia pro comando sempre, mesmo sem o
    # plyer instalado, e o PyInstaller imprimia uma linha "ERROR: Hidden
    # import ... not found" (inofensiva — o build termina igual — mas
    # ruidosa e parecia um problema de verdade no log). notificação nativa
    # continua opcional: sem plyer, o Zenith roda igual, só sem o toast do
    # Windows (o piscar da barra de tarefas continua funcionando).
    tem_plyer = importlib.util.find_spec("plyer") is not None
    if not tem_plyer:
        print("[Zenith] Aviso: biblioteca 'plyer' não encontrada — o .exe vai sair sem notificação "
              "nativa do Windows (só o piscar da barra de tarefas). Pra incluir: pip install plyer "
              "e rode o build de novo.")

    # v26 — sympy é OPCIONAL (só pra /derivar, /integrar, /limite: conta exata e conferida). Se estiver instalado, entra
    # no .exe; se não, o resto do Zenith (inclusive /latex e /formula) funciona igual.
    tem_sympy = importlib.util.find_spec("sympy") is not None
    if not tem_sympy:
        print("[Zenith] Aviso: biblioteca 'sympy' não encontrada — o .exe vai sair SEM /derivar, /integrar e /limite "
              "(o /latex e o /formula funcionam). Pra incluir: pip install sympy e rode o build de novo.")

    cmd = [
        sys.executable, "-m", "PyInstaller", "zenith_launcher.py",
        "--name", "Zenith",
        "--onedir",
        "--noupx",
        "--noconsole",
        "--noconfirm",  # CORREÇÃO: sem isso, um dist/ já existente de um build
                         # anterior trava com "output directory is not empty"
                         # em vez de simplesmente sobrescrever.
        # CORREÇÃO (bug do executável): NÃO usar --add-data pra config/
        # aqui — isso embute o config/ inicial dentro de dist/Zenith/
        # _internal/, o mesmo lugar escondido que causava o bug do
        # BASE_DIR. O config/ é copiado pra fora, ao lado do .exe, no
        # final desta função (_copy_config_beside_exe).
        "--hidden-import=customtkinter",
        "--collect-all", "customtkinter",
        # FEATURE (microfone): faster-whisper (via ctranslate2) e
        # sounddevice (via PortAudio) têm binários nativos que o
        # PyInstaller não pega sozinho por análise estática — sem isso
        # o microfone funcionaria rodando via "python zenith_launcher.py"
        # mas quebraria de novo só no .exe compilado.
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-all", "sounddevice",
        "--collect-binaries", "sounddevice",
        # CORREÇÃO (mic falhando só no .exe, mesmo com sounddevice
        # "instalado"): o PortAudio (a lib nativa que o sounddevice usa
        # de verdade pra falar com o driver de áudio) não vive dentro do
        # módulo sounddevice.py — ele mora num pacote escondido chamado
        # _sounddevice_data, instalado junto no pip install sounddevice
        # no Windows. --collect-all sounddevice sozinho não pega isso
        # porque sounddevice é um ARQUIVO .py solto, não um pacote — é
        # um gotcha bem conhecido do PyInstaller com essa lib.
        "--collect-all", "_sounddevice_data",
        # O Zenith não usa matplotlib/Jupyter em nada — está sendo
        # puxado de carona por alguma dependência transitiva do seu
        # ambiente (uv/PyCharm). Excluir reduz o tamanho do pacote e a
        # quantidade de DLLs desconhecidas que o Controle de Aplicativo
        # Inteligente do Windows pode bloquear.
        # CORREÇÃO: matplotlib estava sendo excluído por engano — não
        # era "carona de dependência transitiva", é o que a Zenith
        # precisa pra gerar gráficos de verdade quando pedido (via
        # execução de código Python aprovada, ver zenith_executor.py).
        # Excluir isso fazia qualquer script gerado com
        # "import matplotlib" falhar com ModuleNotFoundError no .exe
        # compilado, mesmo funcionando certinho em modo desenvolvimento.
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        # CORREÇÃO (crash "No module named 'chromadb.telemetry.product.
        # posthog'"): o chromadb resolve essa classe por uma string de
        # config, importada via importlib.import_module — a análise
        # estática do PyInstaller não enxerga isso sozinha. Já
        # desativei a telemetria em zenith_memory.py (o que evita essa
        # importação por completo), mas isso aqui é a segunda camada de
        # defesa: se qualquer outra parte do chromadb tentar uma
        # importação dinâmica parecida, o módulo já está empacotado.
        "--collect-all", "chromadb",
        "--hidden-import=chromadb.telemetry.product.posthog",
        # CORREÇÃO ("onnxruntime python package is not installed" ao
        # salvar/buscar na memória): mesma classe de bug do sounddevice/
        # faster-whisper — onnxruntime tem binários nativos carregados
        # sob demanda que o PyInstaller não pega só de olhar os imports.
        "--collect-all", "onnxruntime",
        "--collect-all", "tokenizers",
    ]
    if tem_sympy:
        cmd += ["--collect-all", "sympy", "--collect-all", "mpmath"]
    # v26 — o desenho das equações (/latex) usa o mathtext do matplotlib e as fontes Computer Modern dele.
    cmd += ["--hidden-import=matplotlib.backends.backend_agg", "--collect-data", "matplotlib"]
    # v28 — editar/criar vídeo (/video): o imageio-ffmpeg traz o ffmpeg.exe junto; sem isso o .exe não acha o ffmpeg.
    # E o pypdf lê PDF (anexo + biblioteca de documentos). Os dois são opcionais: sem eles o resto funciona.
    if importlib.util.find_spec("imageio_ffmpeg") is not None:
        cmd += ["--collect-all", "imageio_ffmpeg"]
    else:
        print("[Zenith/build] aviso: imageio-ffmpeg não instalado — o .exe NÃO terá edição de vídeo (pip install imageio-ffmpeg).")
    if importlib.util.find_spec("pypdf") is not None:
        cmd += ["--collect-all", "pypdf"]
    else:
        print("[Zenith/build] aviso: pypdf não instalado — o .exe não lerá PDF (pip install pypdf).")
    if tem_plyer:
        # v14/v15 — notificação nativa do Windows (opcional). O plyer
        # escolhe o backend por import dinâmico, que o PyInstaller não
        # enxerga sozinho por análise estática.
        cmd += ["--hidden-import=plyer.platforms.win.notification", "--collect-all", "plyer"]

    # CORREÇÃO (bug do executável, parte 2 — "Não encontrei o
    # executável do Corpo"): --add-data pra body/zenith/export
    # embutia o jogo Godot inteiro dentro de dist/Zenith/_internal/,
    # igual acontecia com config/ — mas zenith_launcher.py procura o
    # Corpo em BASE_DIR (a pasta do .exe, já corrigido), não dentro de
    # _internal. Por isso "Não encontrei o executável do Corpo" mesmo
    # com o Godot exportado direitinho: ele estava lá, só que escondido
    # no lugar errado. Agora o Corpo é copiado pra fora, ao lado do
    # Zenith.exe, depois do build (_copy_godot_export_beside_exe) — o
    # --add-data não é mais usado pra isso.
    if not (os.path.isdir(export_dir) and os.listdir(export_dir)):
        print(f"[Aviso] '{export_dir}' não existe ou está vazia — build vai sair "
              f"SEM o Corpo (Godot) embutido.")
        print("[Aviso] Exporte o projeto Godot (Project > Export > Windows Desktop) "
              "— pode salvar em body/zenith/export/Zenith.exe OU direto em "
              "body/zenith/Zenith.exe, os dois funcionam agora — depois rode este "
              "script de novo pra incluir o Corpo no pacote final.")

    icon_works = False
    if os.path.isfile(icon):
        try:
            import win32ctypes.pywin32.pywintypes  # noqa: F401
            icon_works = True
        except Exception:
            pass

    try:
        cmd += ["--version-file", _write_version_file()]     # v24: metadados de versão no .exe (aba "Detalhes")
    except Exception as e:
        print(f"[Aviso] Não consegui gerar os metadados de versão ({e}); o build segue sem eles.")

    if icon_works:
        cmd += ["--icon", icon]
    elif os.path.isfile(icon):
        print("[Aviso] Ícone encontrado, mas a ferramenta que embute ícone no .exe "
              "não está funcionando neste ambiente (bloqueio de DLL) — build vai "
              "sair SEM ícone customizado, em vez de travar por causa disso.")
    else:
        print(f"[Aviso] Ícone não encontrado em {icon} — build vai sair sem ícone customizado.")

    try:
        run(cmd)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERRO] PyInstaller falhou (código {e.returncode}). "
              f"Copia a saída acima e me manda.")
        sys.exit(1)
    except FileNotFoundError:
        print("\n[ERRO] PyInstaller não está instalado. Rode: pip install pyinstaller")
        sys.exit(1)

    _copy_config_beside_exe()
    _copiar_edition_json()                # v1.4
    _copy_godot_project_beside_exe()     # v18: ANTES do export/, que fica dentro da mesma pasta
    _copy_godot_export_beside_exe(export_dir)
    _copy_godot_editor_beside_exe()
    _copy_rvc_installer_beside_exe()
    _semear_habilidades()
    # v29/v1.0: devolve chaves, conversas, memória e modelos — e, se não conseguir devolver TUDO,
    # PARA aqui (sem apagar o resgate). Antes o build seguia em frente e apagava os dados.
    if not _restaurar_dados_do_usuario():
        print("\n[ERRO] O build terminou, mas seus dados NÃO voltaram para dist/. NÃO abra o Zenith ainda.")
        print(f"       Eles estão inteiros em {_RESGATE}. Feche o Zenith/antivírus e rode o build de novo.")
        sys.exit(1)
    _escrever_versao_build(os.path.join(HERE, "dist", "Zenith"))   # v1.0: data do build no /versao
    _escrever_hashes(os.path.join(HERE, "dist", "Zenith"))      # v24

    _escrever_leia_me_primeira_vez(os.path.join(HERE, "dist", "Zenith"), publico=(edicao_do_build == "publico"))   # v26/v1.4

    # v29 — confere de verdade o que entrou no .exe (executando ele), em vez de só olhar o tamanho
    if not _verificar_exe_empacotado():
        sys.exit(1)

    print("\n" + "=" * 60)
    print(" Pronto! dist/Zenith/Zenith.exe  (distribua a pasta dist/Zenith inteira)")
    if edicao_do_build == "publico":
        print(" Edicao PUBLICA. Proximo passo: gerar o instalador (instalador/construir_instalador.bat).")
    else:
        print(" PRIMEIRA ABERTURA: precisa ser COMO ADMINISTRADOR (botao direito > Executar como administrador).")
        print(" O proprio Zenith pergunta isso na 1a vez e reabre sozinho se voce disser que sim.")
    print(" Leia NOTES_ANTIVIRUS.md antes de distribuir pra terceiros.")
    print(" Se o seu antivirus (Norton, Defender...) barrar o dist/, veja la a secao do Norton:")
    print(" excluir a pasta do projeto nas DUAS listas de exclusao e enviar o Zenith.exe como falso positivo.")
    print("=" * 60)


if __name__ == "__main__":
    main()
