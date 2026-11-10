"""Zenith — INSTALAR E ABRIR sem Freebuff e sem .bat (v1.7).

Por que existe (pedido do Anderson, 24/10/2026: "não quero depender do Freebuff... deve ser a versão do Python"):
  * o Python padrão do PC dele pode ser o 3.14, que quebra pacotes (chromadb, onnxruntime, PyInstaller...). Este script ACHA o Python
    3.13 (ou 3.12) que já esteja instalado, mesmo que não seja o padrão, e usa só ele;
  * cria um ambiente isolado (.venv) dentro da pasta do Zenith: nada é instalado no Python do sistema;
  * instala os requisitos UMA vez (e de novo só se o requirements.txt mudar) e abre o Zenith;
  * se não houver Python bom, diz o comando exato para instalar (e pergunta se pode instalar pelo winget).
  * NADA de .bat: o Windows bloqueia .bat baixado da internet. Funciona com `python INICIAR_ZENITH.py` ou clique duplo no .py.

Só biblioteca padrão (roda em qualquer Python 3.8+). Não coleta nada, não manda nada para fora; o único acesso à rede é o `pip` baixando
os pacotes do requirements.txt (e o winget, se você aceitar).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENV = RAIZ / ".venv"
REQUISITOS = RAIZ / "requirements.txt"
LOG = RAIZ / "temp" / "instalacao.log"
MARCA = VENV / "zenith_requisitos.sha256"

OTIMOS = ((3, 13), (3, 12))              # os que o build e os pacotes aceitam bem
ACEITOS = ((3, 11), (3, 10))             # funcionam, mas com aviso


def classificar_versao(v) -> str:
    v = tuple(v)[:2]
    if v in OTIMOS:
        return "otimo"
    if v in ACEITOS:
        return "aceito"
    return "ruim"


# ------------------------------------------------------------------------------------------------ achar os Pythons
_RE_PY_LAUNCHER = re.compile(r"-(?:V:)?(\d+)\.(\d+)\S*\s+\*?\s*(.+?python\w*\.exe)\s*$", re.IGNORECASE)


def _versao_de(caminho: str, rodar=subprocess.run):
    try:
        r = rodar([caminho, "-c", "import sys;print(sys.version_info[0],sys.version_info[1])"],
                  capture_output=True, text=True, timeout=20)
        a, b = r.stdout.split()[:2]
        return int(a), int(b)
    except Exception:
        return None


def listar_pythons(rodar=subprocess.run, plataforma: str = sys.platform, which=shutil.which) -> list:
    """[(versao(maior, menor), caminho)] de todos os Pythons que o PC tem, sem repetir."""
    achados, vistos = [], set()

    def somar(v, caminho):
        chave = os.path.normcase(str(caminho))
        if v and chave not in vistos:
            vistos.add(chave)
            achados.append((tuple(v), str(caminho)))

    if plataforma.startswith("win"):
        try:
            r = rodar(["py", "-0p"], capture_output=True, text=True, timeout=20)
            for linha in (r.stdout or "").splitlines():
                m = _RE_PY_LAUNCHER.search(linha.strip())
                if m:
                    somar((int(m.group(1)), int(m.group(2))), m.group(3).strip())
        except Exception:
            pass
    for nome in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
        c = which(nome)
        if c:
            somar(_versao_de(c, rodar), c)
    somar(sys.version_info[:2], sys.executable)
    return achados


def escolher(pythons: list):
    """(versao, caminho, nivel) do melhor Python, ou None. 3.13 > 3.12 > 3.11 > 3.10; 3.14+ e antigos ficam de fora."""
    for ordem in (OTIMOS, ACEITOS):
        for alvo in ordem:
            for v, c in pythons:
                if tuple(v)[:2] == alvo:
                    return v, c, classificar_versao(v)
    return None


# ------------------------------------------------------------------------------------------------ ambiente isolado
def python_do_venv(venv: Path = VENV) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def hash_requisitos(req: Path = REQUISITOS) -> str:
    try:
        return hashlib.sha256(req.read_bytes()).hexdigest()
    except OSError:
        return ""


def venv_serve(alvo, venv: Path = VENV, rodar=subprocess.run) -> bool:
    """O .venv existe E foi feito com a mesma versão (se foi feito com o 3.14 por engano, refaz)."""
    py = python_do_venv(venv)
    if not py.exists():
        return False
    return _versao_de(str(py), rodar) == tuple(alvo)[:2]


def requisitos_em_dia(venv: Path = VENV, req: Path = REQUISITOS, marca: Path = MARCA) -> bool:
    try:
        return marca.read_text(encoding="utf-8").strip() == hash_requisitos(req) != ""
    except OSError:
        return False


def diagnosticar_pip(texto: str) -> str:
    """Traduz o erro do pip em português, com o que fazer."""
    t = (texto or "").lower()
    if "winerror 5" in t or "acesso negado" in t or "access is denied" in t:
        return ("O Windows negou acesso a um arquivo. Feche o Zenith e o Godot, tente de novo; se continuar, adicione a pasta do Zenith "
                "nas Exclusões do Segurança do Windows (antivírus).")
    if "no matching distribution" in t or "could not find a version" in t:
        return ("Um pacote não existe para esta versão do Python. Use o Python 3.13 ou 3.12 (este script já tenta escolher sozinho; "
                "se só há o 3.14 instalado, instale o 3.13).")
    if "microsoft visual c++" in t or "vcvarsall" in t or "building wheel" in t and "error" in t:
        return ("Um pacote tentou compilar e não conseguiu. Quase sempre é Python novo demais; use o 3.13 ou 3.12. "
                "Se persistir, instale as 'Ferramentas de Build do Visual Studio'.")
    if "ssl" in t or "connection" in t or "timed out" in t or "network" in t or "proxy" in t:
        return "Falha de internet ao baixar os pacotes. Confira a conexão (ou proxy/antivírus) e rode de novo: ele continua de onde parou."
    if "no space left" in t or "espaço" in t and "disco" in t:
        return "Acabou o espaço em disco. Libere uns 3 GB e rode de novo."
    return "O pip falhou. Mande o arquivo temp/instalacao.log para eu ver a causa."


def ultimas_linhas(texto: str, n: int = 12) -> str:
    return "\n".join((texto or "").strip().splitlines()[-n:])


# ------------------------------------------------------------------------------------------------ passos com efeito
def criar_venv(py: str, venv: Path = VENV, rodar=subprocess.run) -> bool:
    if venv.exists():
        shutil.rmtree(venv, ignore_errors=True)
    r = rodar([py, "-m", "venv", str(venv)], capture_output=True, text=True)
    return r.returncode == 0 and python_do_venv(venv).exists()


def instalar_requisitos(venv_py: str, req: Path = REQUISITOS, log: Path = LOG, rodar=subprocess.run) -> tuple:
    """(ok, texto). Grava tudo em temp/instalacao.log."""
    log.parent.mkdir(parents=True, exist_ok=True)
    r = rodar([venv_py, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req)],
              capture_output=True, text=True)
    texto = (r.stdout or "") + "\n" + (r.stderr or "")
    try:
        log.write_text(texto, encoding="utf-8")
    except OSError:
        pass
    return r.returncode == 0, texto


def abrir_zenith(venv_py: str) -> None:
    py = Path(venv_py)
    janela = py.with_name("pythonw.exe")                  # no Windows: sem janela preta de terminal
    exe = str(janela if (os.name == "nt" and janela.exists()) else py)
    subprocess.Popen([exe, str(RAIZ / "zenith_launcher.py")], cwd=str(RAIZ))


def oferecer_instalar_python(entrada=input, rodar=subprocess.run, which=shutil.which, imprimir=print) -> bool:
    """Sem Python bom: mostra o comando e, se houver winget e a pessoa disser 's', instala o 3.13 só para o usuário."""
    cmd = "winget install -e --id Python.Python.3.13 --scope user"
    imprimir("\nNão achei o Python 3.13 nem o 3.12 neste computador. O Zenith precisa de um deles (o 3.14 ainda quebra alguns pacotes).")
    imprimir(f"Comando para instalar (não precisa de administrador):\n    {cmd}")
    imprimir("Ou baixe em https://www.python.org/downloads/ (marque 'Add python.exe to PATH').")
    if which("winget") is None:
        return False
    resp = entrada("\nQuer que eu instale o Python 3.13 agora pelo winget? (s/n) ").strip().lower()
    if resp not in ("s", "sim", "y", "yes"):
        return False
    return rodar(cmd.split()).returncode == 0


# ------------------------------------------------------------------------------------------------ programa principal
def planejar(pythons: list, venv: Path = VENV, req: Path = REQUISITOS) -> dict:
    esc = escolher(pythons)
    plano = {"python": esc, "refazer_venv": False, "instalar": False}
    if esc is None:
        return plano
    plano["refazer_venv"] = not venv_serve(esc[0], venv)
    plano["instalar"] = plano["refazer_venv"] or not requisitos_em_dia(venv, req)
    return plano


def main(argv=None, imprimir=print) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    so_conferir, sem_abrir, gerar_exe, refazer = ("--so-conferir" in argv, "--sem-abrir" in argv, "--gerar-exe" in argv, "--refazer" in argv)
    pythons = listar_pythons()
    plano = planejar(pythons)
    if plano["python"] is None:
        if so_conferir:
            imprimir("SEM PYTHON BOM: precisa do 3.13 ou 3.12. Pythons achados: " + (", ".join(f"{a}.{b}" for (a, b), _ in pythons) or "nenhum"))
            return 2
        if not oferecer_instalar_python(imprimir=imprimir):
            return 2
        imprimir("\nPython instalado. Feche esta janela e rode de novo (o Windows precisa reconhecê-lo).")
        return 0
    (maior, menor), caminho, nivel = plano["python"]
    imprimir(f"Python escolhido: {maior}.{menor} ({caminho})" + ("  [aviso: o ideal é o 3.13 ou 3.12]" if nivel == "aceito" else ""))
    if refazer:
        plano["refazer_venv"] = plano["instalar"] = True
    if so_conferir:
        imprimir(f"Ambiente isolado: {'será (re)criado' if plano['refazer_venv'] else 'já existe'}; "
                 f"requisitos: {'serão instalados' if plano['instalar'] else 'em dia'}.")
        return 0
    if plano["refazer_venv"]:
        imprimir("Criando o ambiente isolado (.venv)...")
        if not criar_venv(caminho):
            imprimir("Não consegui criar o ambiente isolado. Tente de novo; se persistir, apague a pasta .venv.")
            return 1
    py = str(python_do_venv())
    if plano["instalar"]:
        imprimir("Instalando os requisitos. Na primeira vez demora alguns minutos (baixa cerca de 1 GB)...")
        ok, texto = instalar_requisitos(py)
        if not ok:
            imprimir("\nA instalação falhou.\n" + diagnosticar_pip(texto) + "\n\nÚltimas linhas:\n" + ultimas_linhas(texto))
            return 1
        try:
            MARCA.write_text(hash_requisitos(), encoding="utf-8")
        except OSError:
            pass
        imprimir("Requisitos instalados.")
    if gerar_exe:
        imprimir("Gerando o Zenith.exe (build_exe.py)...")
        args = [py, str(RAIZ / "build_exe.py")] + [a for a in argv if a.startswith("--edicao") or a == "--confirmo-avatares-livres"]
        return subprocess.run(args, cwd=str(RAIZ)).returncode
    if sem_abrir:
        imprimir("Pronto (não abri o Zenith, como pedido).")
        return 0
    imprimir("Abrindo o Zenith...")
    abrir_zenith(py)
    return 0


if __name__ == "__main__":
    codigo = main()
    if codigo != 0 and sys.stdin is not None and sys.stdin.isatty():
        input("\nPressione Enter para fechar...")
    sys.exit(codigo)
