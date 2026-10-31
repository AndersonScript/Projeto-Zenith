"""
Zenith Launcher — baixa o Zenith, prepara o Python com TODAS as bibliotecas e mantém tudo atualizado.

É o programa pequeno (ZenithLauncher.exe) que o site (Vercel) entrega. Só usa a biblioteca padrão do Python,
porque ele roda ANTES de existir qualquer biblioteca instalada.

O que ele faz, em ordem (cada passo mostra o que está fazendo e pode falhar com uma dica em português):
  1. Lê o latest.json do site (HTTPS, só dos endereços permitidos) e confere o formato.
  2. Python: instala uma cópia PRÓPRIA do Python na pasta do Zenith (sem administrador, sem mexer no seu Python).
  3. Zenith: baixa o pacote, CONFERE o SHA-256, extrai com proteção contra caminho malicioso e troca a pasta `app`
     guardando a anterior (dá para voltar). Seus dados (config, modelos, avatares) ficam: nada é apagado.
  4. Bibliotecas: pip install do requirements.txt do pacote (as essenciais têm que passar; as opcionais só avisam).
  5. Atalhos e abertura do Zenith.

Regras do projeto que valem aqui:
  * Nada silencioso: a primeira instalação e cada atualização PERGUNTAM antes (a menos que você use --sim).
  * Nenhuma telemetria. A única conversa com a internet é: o latest.json, o pacote, o instalador do Python e o pip.
  * Nada é executado sem conferir o SHA-256 antes. Download vindo de endereço fora da lista permitida é recusado.
Só Windows de verdade (instalador do Python, atalhos); a lógica pura roda em qualquer sistema e é testada.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

VERSAO_LAUNCHER = "1.0.1"      # 1.0.1: download com certificado que funciona + LimparZenith (apagar por partes/desinstalar)
MANIFESTO_PADRAO = "https://SEU_PROJETO.vercel.app/latest.json"
HOSTS_PADRAO = ("SEU_PROJETO.vercel.app", "github.com", "objects.githubusercontent.com",
                "release-assets.githubusercontent.com", "www.python.org", "python.org")

LIMITE_MANIFESTO = 512 * 1024
LIMITE_PACOTE = 1_500 * 1024 * 1024
LIMITE_PYTHON = 120 * 1024 * 1024
LIMITE_LAUNCHER = 120 * 1024 * 1024
LIMITE_ARQUIVOS_ZIP = 80_000
LIMITE_DESCOMPACTADO = 6 * 1024 ** 3
TEMPO_REDE = 30

# O que a atualização NUNCA apaga (caminho relativo à pasta `app`). O usuário manda; o pacote só acrescenta o que falta.
PRESERVAR = ("config", "models", "body/zenith/addons/avatars")
# Arquivos que o PACOTE atualiza mesmo dentro de pasta preservada (não são do usuário).
GERENCIADOS = ("config/provedores_catalogo.json",)

# requirements.txt: o que não entra no ambiente de execução (só serve para gerar o .exe) e o que é opcional.
SO_PARA_BUILD = {"pyinstaller", "pywin32-ctypes"}
OPCIONAIS = {"plyer", "sympy", "imageio-ffmpeg", "pypdf", "faster-whisper", "sounddevice", "numpy",
             "opencv-python-headless", "matplotlib", "pyserial", "mss"}


class ErroInstalador(Exception):
    """Erro com mensagem pronta para o usuário (e uma dica de como resolver)."""

    def __init__(self, mensagem: str, dica: str = ""):
        super().__init__(mensagem)
        self.dica = dica


# ============================================================================ versões e endereços
def versao_tupla(texto) -> tuple:
    """'1.6.1' -> (1, 6, 1). Parte não numérica vira 0 ('1.7-beta' -> (1, 7, 0))."""
    partes = []
    for p in str(texto or "").strip().lstrip("vV").split("."):
        m = re.match(r"\d+", p)
        partes.append(int(m.group()) if m else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:4])


def host_permitido(url: str, hosts, permitir_local: bool = False) -> bool:
    try:
        u = urllib.parse.urlparse(str(url or "").strip())
    except Exception:
        return False
    if u.scheme == "http" and permitir_local and u.hostname in ("localhost", "127.0.0.1"):
        return True
    if u.scheme != "https" or not u.hostname:
        return False
    h = u.hostname.lower()
    return any(h == str(p).lower() for p in hosts)


class _RedirectSeguro(urllib.request.HTTPRedirectHandler):
    """Segue redirecionamentos (o GitHub Releases redireciona), mas só para endereços permitidos."""

    def __init__(self, hosts, permitir_local=False):
        self.hosts, self.permitir_local = tuple(hosts), permitir_local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_permitido(newurl, self.hosts, self.permitir_local):
            raise urllib.error.URLError(f"redirecionamento para endereço não permitido: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_CTX_SSL = None


def contexto_ssl():
    """Contexto de HTTPS que confia no Windows E no certifi (que vai DENTRO do .exe).

    Por que existe (caso real, 30/10/2026): o download parava em
    `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` — o Windows do usuário
    não tinha a raiz do certificado do site (Windows sem atualização de raízes). O certifi traz a
    lista de raízes junto com o programa, então o download funciona mesmo assim.
    """
    global _CTX_SSL
    if _CTX_SSL is not None:
        return _CTX_SSL
    try:
        ctx = ssl.create_default_context()          # começa com o que o Windows confia
    except Exception:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    arquivos = []
    try:
        import certifi                                # instalado no build (--collect-data certifi)
        arquivos.append(certifi.where())
    except Exception:
        pass
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    arquivos += [base / "certifi" / "cacert.pem", base / "cacert.pem"]
    for arq in arquivos:
        try:
            if arq and Path(arq).is_file():
                ctx.load_verify_locations(cafile=str(arq))
        except Exception:
            continue
    _CTX_SSL = ctx
    return ctx


def _erro_de_rede(e: Exception) -> ErroInstalador:
    """Traduz erro de download. SSL ganha uma explicação própria (não é 'sem internet')."""
    motivo = getattr(e, "reason", e)
    if isinstance(motivo, ssl.SSLError) or isinstance(e, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
        return ErroInstalador(
            f"Falha ao baixar: o Windows não reconheceu o certificado do site ({e}).",
            "Isso quase sempre é relógio/data errados no computador ou raízes de certificado antigas. "
            "Confira a data e a hora, tente de novo — e, se repetir, baixe pelo navegador no site do Zenith.")
    return ErroInstalador(f"Falha ao baixar: {e}", "Confira a internet e o espaço em disco.")


def abrir_url(url: str, hosts, permitir_local: bool = False, tempo: int = TEMPO_REDE):
    """Abre a URL com o abridor seguro. Devolve o objeto de resposta (use .read(n))."""
    if not host_permitido(url, hosts, permitir_local):
        raise ErroInstalador(f"Endereço não permitido: {url}",
                             "O Launcher só baixa dos endereços da lista (site do Zenith, GitHub e python.org).")
    abridor = urllib.request.build_opener(_RedirectSeguro(hosts, permitir_local),
                                          urllib.request.HTTPSHandler(context=contexto_ssl()))
    abridor.addheaders = [("User-Agent", f"ZenithLauncher/{VERSAO_LAUNCHER}")]
    return abridor.open(url, timeout=tempo)


# ============================================================================ manifesto (latest.json)
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _item(dados, chave, limite, hosts, permitir_local, obrigatorio=True):
    bruto = dados.get(chave)
    if not isinstance(bruto, dict):
        if obrigatorio:
            raise ErroInstalador(f"O latest.json não traz '{chave}'.", "O site está com o manifesto incompleto; avise quem publicou.")
        return None
    url = str(bruto.get("url") or "").strip()
    sha = str(bruto.get("sha256") or "").strip().lower()
    if not host_permitido(url, hosts, permitir_local):
        raise ErroInstalador(f"O latest.json aponta '{chave}' para um endereço não permitido: {url or '(vazio)'}",
                             "Por segurança o Launcher não baixa dali.")
    if not _SHA.match(sha):
        raise ErroInstalador(f"O latest.json não traz o SHA-256 de '{chave}'.", "Sem o hash eu não baixo nada.")
    try:
        tam = int(bruto.get("tamanho") or 0)
    except (TypeError, ValueError):
        tam = 0
    if tam > limite:
        raise ErroInstalador(f"'{chave}' é maior que o limite de segurança ({limite // 1024 // 1024} MB).")
    return {"url": url, "sha256": sha, "tamanho": tam, "versao": str(bruto.get("versao") or "").strip(),
            "arquivo": str(bruto.get("arquivo") or "").strip()}


def validar_manifesto(dados, hosts, permitir_local: bool = False) -> dict:
    """Confere o latest.json e devolve só o que o Launcher usa. Levanta ErroInstalador com dica."""
    if not isinstance(dados, dict) or not str(dados.get("versao") or "").strip():
        raise ErroInstalador("O latest.json não diz qual é a versão.", "Confira o endereço do manifesto.")
    return {
        "versao": str(dados["versao"]).strip(),
        "notas": str(dados.get("notas") or "").strip()[:4000],
        "pacote": _item(dados, "pacote", LIMITE_PACOTE, hosts, permitir_local),
        "python": _item(dados, "python", LIMITE_PYTHON, hosts, permitir_local),
        "launcher": _item(dados, "launcher", LIMITE_LAUNCHER, hosts, permitir_local, obrigatorio=False),
    }


def ler_manifesto(url: str, hosts, permitir_local: bool = False, abrir=None) -> dict:
    abrir = abrir or (lambda u: abrir_url(u, hosts, permitir_local))
    try:
        with abrir(url) as r:
            bruto = r.read(LIMITE_MANIFESTO + 1)
    except ErroInstalador:
        raise
    except Exception as e:
        if isinstance(getattr(e, "reason", e), ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise _erro_de_rede(e)
        raise ErroInstalador(f"Não consegui falar com o site do Zenith: {e}", "Confira a internet e tente de novo.")
    if len(bruto) > LIMITE_MANIFESTO:
        raise ErroInstalador("O latest.json veio grande demais — não vou usar.")
    try:
        dados = json.loads(bruto.decode("utf-8-sig"))
    except Exception as e:
        raise ErroInstalador(f"O servidor respondeu algo que não é o latest.json: {e}")
    return validar_manifesto(dados, hosts, permitir_local)


# ============================================================================ download conferido
def baixar(url: str, destino, sha256: str, max_bytes: int, hosts, progresso=None, abrir=None,
           cancelado=None, permitir_local: bool = False) -> Path:
    """Baixa para `destino` (via .parte), confere o SHA-256 durante a leitura e só então renomeia.
    Hash errado, tamanho acima do limite ou cancelamento => nada fica no disco."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parte = destino.with_name(destino.name + ".parte")
    abrir = abrir or (lambda u: abrir_url(u, hosts, permitir_local))
    h = hashlib.sha256()
    lido = 0
    try:
        with abrir(url) as r, open(parte, "wb") as f:
            total = 0
            try:
                total = int(getattr(r, "headers", {}).get("Content-Length") or 0)
            except Exception:
                total = 0
            while True:
                if cancelado and cancelado():
                    raise ErroInstalador("Cancelado por você.")
                bloco = r.read(256 * 1024)
                if not bloco:
                    break
                lido += len(bloco)
                if lido > max_bytes:
                    raise ErroInstalador("O arquivo passou do limite de segurança — descartei o download.")
                h.update(bloco)
                f.write(bloco)
                if progresso and total:
                    progresso(min(lido / total, 1.0))
        if lido == 0:
            raise ErroInstalador("O servidor mandou um arquivo vazio.")
        if h.hexdigest() != str(sha256).lower():
            raise ErroInstalador("O SHA-256 não confere: o arquivo pode ter sido trocado no caminho. Descartei o download.",
                                 "Tente de novo; se repetir, avise quem publicou.")
        os.replace(parte, destino)
        if progresso:
            progresso(1.0)
        return destino
    except ErroInstalador:
        raise
    except Exception as e:
        raise _erro_de_rede(e)
    finally:
        try:
            if parte.exists():
                parte.unlink()
        except OSError:
            pass


# ============================================================================ extração protegida
def _nome_seguro(nome: str):
    n = nome.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    partes = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in partes):
        return None
    return partes


def extrair_seguro(zip_path, destino, max_arquivos: int = LIMITE_ARQUIVOS_ZIP, max_bytes: int = LIMITE_DESCOMPACTADO) -> Path:
    """Extrai o zip em `destino`. Recusa: caminho absoluto, `..`, atalho (symlink), zip bomba e arquivo demais.
    Se o zip tem UMA pasta raiz, tira essa pasta (o conteúdo vai direto para `destino`)."""
    destino = Path(destino)
    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        if len(infos) > max_arquivos:
            raise ErroInstalador("O pacote tem arquivos demais — recusei por segurança.")
        if sum(i.file_size for i in infos) > max_bytes:
            raise ErroInstalador("O pacote descompactado passaria do limite de segurança — recusei.")
        brutas = []
        for i in infos:
            partes = _nome_seguro(i.filename)
            if partes is None:
                raise ErroInstalador(f"O pacote tem um caminho perigoso ({i.filename}) — recusei.")
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ErroInstalador(f"O pacote tem um atalho (symlink: {i.filename}) — recusei.")
            if partes:
                brutas.append((i, partes))
        raiz_unica = ""
        topos = {p[0] for _, p in brutas}
        if len(topos) == 1 and all(len(p) > 1 for _, p in brutas):
            raiz_unica = next(iter(topos))
        destino.mkdir(parents=True, exist_ok=True)
        base = destino.resolve()
        for info, partes in brutas:
            rel = partes[1:] if raiz_unica else partes
            alvo = (destino.joinpath(*rel)).resolve()
            if base != alvo and base not in alvo.parents:
                raise ErroInstalador("O pacote tentou escrever fora da pasta — recusei.")
            if info.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(alvo, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    return destino


# ============================================================================ troca da pasta app (com volta)
def _mesclar_para_o_usuario(novo: Path, antigo: Path, gerenciados_rel):
    """Antes de a pasta do usuário voltar: copia para ela o que o pacote novo trouxe e ela ainda não tem.
    Arquivos GERENCIADOS pelo pacote (ex.: catálogo de provedores) vêm do pacote novo."""
    if not novo.exists():
        return
    for arq in [p for p in novo.rglob("*") if p.is_file()]:
        rel = arq.relative_to(novo)
        alvo = antigo / rel
        gerenciado = rel.as_posix() in gerenciados_rel
        if alvo.exists() and not gerenciado:
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arq, alvo)


def trocar_app(raiz, novo, preservar=PRESERVAR, gerenciados=GERENCIADOS) -> dict:
    """Coloca `novo` como `raiz/app`, guarda a pasta antiga em `raiz/app.anterior` e leva as pastas do usuário.
    Só renomeia (mesmo volume): se algo falhar no meio, desfaz e a versão antiga continua inteira."""
    raiz, novo = Path(raiz), Path(novo)
    app, anterior = raiz / "app", raiz / "app.anterior"
    movidas = []
    if anterior.exists():
        shutil.rmtree(anterior, ignore_errors=True)
    tinha_app = app.exists()
    try:
        if tinha_app:
            try:
                os.replace(app, anterior)
            except OSError as e:
                raise ErroInstalador(f"Não consegui trocar a pasta do Zenith ({e}).", "Feche o Zenith (e o avatar) e tente de novo.")
            for rel in preservar:
                velho = anterior / rel
                if not velho.exists():
                    continue
                alvo = novo / rel
                _mesclar_para_o_usuario(alvo, velho, {g[len(rel) + 1:] for g in gerenciados if g.startswith(rel.rstrip("/") + "/")})
                if alvo.exists():
                    shutil.rmtree(alvo, ignore_errors=True)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                os.replace(velho, alvo)
                movidas.append(rel)
        os.replace(novo, app)
    except BaseException:
        # desfaz: devolve o que foi levado e recoloca a pasta antiga
        for rel in movidas:
            try:
                os.replace(novo / rel, anterior / rel)
            except OSError:
                pass
        if tinha_app and anterior.exists() and not app.exists():
            try:
                os.replace(anterior, app)
            except OSError:
                pass
        raise
    return {"app": str(app), "anterior": str(anterior) if tinha_app else "", "movidas": movidas}


def reverter(raiz, preservar=PRESERVAR) -> bool:
    """Volta para a versão anterior (se existir) levando de volta as pastas do usuário."""
    raiz = Path(raiz)
    app, anterior, descartada = raiz / "app", raiz / "app.anterior", raiz / "app.descartada"
    if not anterior.exists():
        return False
    if descartada.exists():
        shutil.rmtree(descartada, ignore_errors=True)
    if app.exists():
        os.replace(app, descartada)
        for rel in preservar:
            origem = descartada / rel
            if origem.exists():
                alvo = anterior / rel
                if alvo.exists():
                    shutil.rmtree(alvo, ignore_errors=True)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                os.replace(origem, alvo)
    os.replace(anterior, app)
    shutil.rmtree(descartada, ignore_errors=True)
    return True


# ============================================================================ requirements.txt
def ler_requisitos(texto: str) -> tuple:
    """-> (obrigatorios, opcionais): linhas de requisito já sem comentários. Ignora o que é só de build."""
    obrig, opc = [], []
    for linha in str(texto or "").splitlines():
        s = linha.split("#", 1)[0].strip()
        if not s or s.startswith("-"):
            continue
        nome = re.split(r"[<>=!~;\[ ]", s, 1)[0].strip().lower().replace("_", "-")
        if not nome or nome in SO_PARA_BUILD:
            continue
        (opc if nome in OPCIONAIS else obrig).append(s)
    return obrig, opc


# ============================================================================ pastas e estado
def raiz_padrao() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "Zenith"


def python_exe(raiz, janela: bool = False) -> Path:
    pasta = Path(raiz) / "runtime" / "python"
    if os.name == "nt":
        return pasta / ("pythonw.exe" if janela else "python.exe")
    return pasta / "bin" / "python3"


def ler_estado(raiz) -> dict:
    try:
        return json.loads((Path(raiz) / "estado.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def gravar_estado(raiz, estado: dict):
    raiz = Path(raiz)
    raiz.mkdir(parents=True, exist_ok=True)
    tmp = raiz / "estado.json.tmp"
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, raiz / "estado.json")


def gravar_instalacao_json(app: Path, dados: Path):
    """O app já sabe ler config/instalacao.json: data_root_path = onde ficam criações, memória e temporários.
    Não sobrescreve uma escolha que o usuário já fez."""
    arq = Path(app) / "config" / "instalacao.json"
    arq.parent.mkdir(parents=True, exist_ok=True)
    try:
        atual = json.loads(arq.read_text(encoding="utf-8-sig"))
        if not isinstance(atual, dict):
            atual = {}
    except Exception:
        atual = {}
    if not str(atual.get("data_root_path") or "").strip():
        atual["data_root_path"] = str(dados)
        arq.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================================ programas externos
def executar_comando(cmd, linha=None, tempo: int = 3600, cwd=None) -> tuple:
    """Roda um programa e devolve (codigo, cauda_da_saida). `linha` recebe cada linha (para mostrar progresso)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                         cwd=cwd, creationflags=flags)
    cauda = []
    inicio = time.time()
    try:
        for ln in p.stdout:
            ln = ln.rstrip()
            cauda.append(ln)
            del cauda[:-40]
            if linha:
                linha(ln)
            if time.time() - inicio > tempo:
                p.kill()
                raise ErroInstalador("Demorou demais e eu parei.")
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            p.kill()
    return p.returncode, "\n".join(cauda)


def comando_instalar_python(instalador, destino) -> list:
    """Instalação silenciosa, só para este usuário (sem administrador), com Tk e pip, sem mexer em PATH/atalhos."""
    return [str(instalador), "/quiet", "InstallAllUsers=0", f"TargetDir={destino}", "Include_launcher=0",
            "InstallLauncherAllUsers=0", "Include_test=0", "Include_doc=0", "Include_tcltk=1", "Include_pip=1",
            "PrependPath=0", "Shortcuts=0", "AssociateFiles=0", "CompileAll=0"]


def instalar_python(raiz, instalador, executar=executar_comando):
    destino = Path(raiz) / "runtime" / "python"
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    codigo, saida = executar(comando_instalar_python(instalador, destino), None, 1200)
    exe = python_exe(raiz)
    if codigo != 0 or not exe.exists():
        raise ErroInstalador(f"A instalação do Python não terminou (código {codigo}).",
                             "Veja se há espaço em disco e se o antivírus não bloqueou. Detalhe: " + saida[-300:])
    codigo, saida = executar([str(exe), "-c", "import tkinter, ssl, sqlite3, venv; print('ok')"], None, 120)
    if codigo != 0:
        raise ErroInstalador("O Python foi instalado, mas faltam peças (Tk/SSL). Instalação incompleta.", saida[-300:])
    return exe


def pip_instalar(raiz, obrigatorios, opcionais, executar=executar_comando, linha=None) -> list:
    """Instala as bibliotecas. As essenciais precisam passar (senão levanta erro); as opcionais só somam avisos.
    Devolve a lista de opcionais que não instalaram."""
    py = python_exe(raiz)
    base = [str(py), "-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary"]
    if obrigatorios:
        tmp = Path(raiz) / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        req = tmp / "essenciais.txt"
        req.write_text("\n".join(obrigatorios) + "\n", encoding="utf-8")
        codigo, saida = executar(base + ["-r", str(req)], linha, 3600)
        if codigo != 0:
            raise ErroInstalador("Não consegui instalar as bibliotecas essenciais do Zenith.",
                                 "Confira a internet e tente de novo. Detalhe: " + saida[-400:])
    falhas = []
    for req_opc in opcionais:
        codigo, _saida = executar(base + [req_opc], linha, 1800)
        if codigo != 0:
            falhas.append(re.split(r"[<>=!~;\[ ]", req_opc, 1)[0])
    return falhas


def _ps_texto(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def script_atalhos(launcher_exe, nome="Zenith") -> str:
    """Cria atalho na Área de Trabalho e no Menu Iniciar (PowerShell; sem biblioteca extra)."""
    alvo = _ps_texto(launcher_exe)
    return ("$w = New-Object -ComObject WScript.Shell; "
            f"foreach ($pasta in @([Environment]::GetFolderPath('Desktop'), "
            "(Join-Path ([Environment]::GetFolderPath('Programs')) ''))) { "
            f"$l = $w.CreateShortcut((Join-Path $pasta ({_ps_texto(nome + '.lnk')}))); "
            f"$l.TargetPath = {alvo}; $l.WorkingDirectory = (Split-Path {alvo}); "
            f"$l.IconLocation = {alvo}; $l.Save() }}")


def criar_atalhos(launcher_exe, executar=executar_comando):
    if os.name != "nt" or not launcher_exe:
        return False
    codigo, _ = executar(["powershell", "-NoProfile", "-NonInteractive", "-Command", script_atalhos(launcher_exe)], None, 60)
    return codigo == 0


def script_encerrar_pasta(pasta) -> str:
    """Encerra programas que estão rodando de dentro da pasta (o avatar/Corpo do Zenith), para a troca de arquivos."""
    p = _ps_texto(str(pasta).rstrip("\\/") + "\\*")
    return f"Get-Process | Where-Object {{ $_.Path -like {p} }} | Stop-Process -Force -ErrorAction SilentlyContinue"


def esperar_processo(pid: int, limite: float = 120.0) -> bool:
    """Espera o processo `pid` terminar. True = terminou (ou não existe)."""
    if not pid:
        return True
    fim = time.time() + limite
    while time.time() < fim:
        try:
            if os.name == "nt":
                import ctypes
                k = ctypes.windll.kernel32
                h = k.OpenProcess(0x00100000, False, int(pid))      # SYNCHRONIZE
                if not h:
                    return True
                r = k.WaitForSingleObject(h, 500)
                k.CloseHandle(h)
                if r == 0:
                    return True
            else:
                os.kill(int(pid), 0)
                time.sleep(0.5)
        except OSError:
            return True
    return False


def iniciar_app(raiz, launcher_exe="", popen=subprocess.Popen, manifesto_url=""):
    """Abre o Zenith com o Python próprio (sem janela de terminal)."""
    app = Path(raiz) / "app"
    script = app / "zenith_launcher.py"
    if not script.exists():
        raise ErroInstalador("A pasta do Zenith não tem o zenith_launcher.py.", "Rode o Launcher de novo para reinstalar.")
    env = dict(os.environ)
    env["ZENITH_LAUNCHER"] = str(launcher_exe or "")
    env["ZENITH_RAIZ"] = str(raiz)
    if manifesto_url:
        env["ZENITH_ATUALIZAR_URL"] = str(manifesto_url)     # o /atualizar de dentro do Zenith consulta o mesmo latest.json
    env.pop("PYTHONPATH", None)
    return popen([str(python_exe(raiz, janela=True)), str(script)], cwd=str(app), env=env, close_fds=True)


# ============================================================================ trocar o próprio launcher
def trocar_executavel(atual, novo) -> bool:
    """Windows não deixa apagar o .exe em uso, mas deixa RENOMEAR: o atual vira .antigo e o novo ocupa o lugar."""
    atual, novo = Path(atual), Path(novo)
    antigo = atual.with_name(atual.name + ".antigo")
    try:
        if antigo.exists():
            antigo.unlink()
        os.replace(atual, antigo)
        os.replace(novo, atual)
        return True
    except OSError:
        if antigo.exists() and not atual.exists():
            os.replace(antigo, atual)
        return False


def limpar_antigo(atual):
    try:
        Path(str(atual) + ".antigo").unlink()
    except OSError:
        pass


# ============================================================================ apagar por partes / desinstalar
# Pedido do Anderson (30/10/2026): além do "resetar tudo", poder apagar SÓ uma coisa —
# só o histórico, só as chaves, só as fotos/vídeos, só os programas que ela criou.
PEDACOS = {
    "historico": "Conversas e histórico (conversas, notas, lembretes, log de ações)",
    "memoria": "Memória de longo prazo (o que ela aprendeu e guardou sobre você)",
    "chaves": "Chaves de API (Gemini, Groq, OpenAI, OpenRouter...)",
    "fotos": "Fotos e vídeos que ela gerou",
    "programas": "Programas/habilidades que ela criou",
    "temporarios": "Temporários e rascunhos",
    "pessoal": "Arquivos que você escreveu (ZENITH.md, bíblia extra)",
}
# Chaves de API zeradas no settings.json (mesma lista que brain/zenith_reset.py usa)
CAMPOS_DE_CHAVE = (
    "gemini_key", "openai_key", "openrouter_key", "groq_key", "tavily_api_key",
    "custom_api_url", "custom_api_key", "custom_api_model", "elevenlabs_key", "elevenlabs_voice_id",
)


def caminhos_do_app(raiz) -> dict:
    """Onde ficam as coisas do Zenith instalado: app, config, e a pasta de dados escolhida."""
    raiz = Path(raiz)
    app = raiz / "app"
    config = app / "config"
    dados = raiz / "dados"
    for arq in (config / "settings.json", config / "instalacao.json"):
        try:
            bruto = json.loads(arq.read_text(encoding="utf-8-sig"))
            escolhido = str(bruto.get("data_root_path") or "").strip()
            if escolhido:
                dados = Path(os.path.expandvars(escolhido))
                break
        except Exception:
            continue
    return {"raiz": raiz, "app": app, "config": config, "dados": dados,
            "temp": dados / "temp", "creations": dados / "creations",
            "memory": dados / "memory_db", "skills": app / "skills"}


def _tamanho(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _apagar(alvo, relatorio: dict):
    alvo = Path(alvo)
    if not alvo.exists():
        return False
    tamanho = _tamanho(alvo)
    try:
        if alvo.is_dir():
            shutil.rmtree(alvo)
        else:
            alvo.unlink()
    except OSError as e:
        relatorio["falhas"].append(f"{alvo.name}: {e}")
        return False
    relatorio["bytes"] += tamanho
    relatorio["itens"] += 1
    return True


def _esvaziar_pasta(pasta, relatorio: dict):
    pasta = Path(pasta)
    if not pasta.is_dir():
        return
    for item in list(pasta.iterdir()):
        _apagar(item, relatorio)


def _zerar_chaves(config: Path, relatorio: dict):
    arq = Path(config) / "settings.json"
    try:
        dados = json.loads(arq.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    if not isinstance(dados, dict):
        return
    for campo in CAMPOS_DE_CHAVE:
        if campo in dados:
            dados[campo] = ""
    dados["ai_endpoints"] = []
    try:
        tmp = arq.with_name("settings.json.tmp")
        tmp.write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, arq)
        relatorio["itens"] += 1
    except OSError as e:
        relatorio["falhas"].append(f"settings.json: {e}")


def categorias_validas() -> list:
    return sorted(PEDACOS)


def ler_categorias(texto) -> list:
    """'historico, chaves' -> ['chaves','historico']. '*' = tudo menos o programa; nome errado é recusado."""
    bruto = str(texto or "").replace(";", ",").replace(" ", ",")
    itens = [p for p in (x.strip().lower() for x in bruto.split(",")) if p]
    if "*" in itens or "tudo" in itens:
        return categorias_validas()
    for nome in itens:
        if nome not in PEDACOS:
            raise ErroInstalador(f"Não conheço a opção '{nome}'.",
                                 "Use: " + ", ".join(categorias_validas()) + ".")
    return sorted(set(itens))


def limpar_pedacos(raiz, categorias, log=print) -> dict:
    """Apaga SÓ as categorias pedidas. Devolve {itens, bytes, falhas, categorias}. Nunca levanta por erro de disco."""
    categorias = list(dict.fromkeys(categorias))
    if "tudo" in categorias or "*" in categorias:      # atalho: tudo, menos o programa em si
        categorias = categorias_validas()
    caminhos = caminhos_do_app(raiz)
    rel = {"itens": 0, "bytes": 0, "falhas": [], "categorias": categorias}
    for cat in categorias:
        if cat == "historico":
            for nome in ("conversations.json", "zenith_notas.jsonl", "zenith_acoes_log.jsonl",
                         "zenith_acoes_log.1.jsonl", "zenith_lembretes.json", "zenith_voz_debug.log"):
                _apagar(caminhos["config"] / nome, rel)
            _apagar(caminhos["app"] / "zenith_log.txt", rel)
        elif cat == "memoria":
            _esvaziar_pasta(caminhos["memory"], rel)
            _esvaziar_pasta(caminhos["app"] / "memory_db", rel)
        elif cat == "pessoal":
            for nome in ("ZENITH.md", "biblia_extra.md"):
                _apagar(caminhos["config"] / nome, rel)
        elif cat == "chaves":
            _zerar_chaves(caminhos["config"], rel)
        elif cat == "fotos":
            _esvaziar_pasta(caminhos["creations"], rel)
            _esvaziar_pasta(caminhos["app"] / "creations", rel)
        elif cat == "programas":
            _esvaziar_pasta(caminhos["skills"], rel)
            _esvaziar_pasta(caminhos["dados"] / "skills", rel)
        elif cat == "temporarios":
            _esvaziar_pasta(caminhos["temp"], rel)
            _apagar(caminhos["app"] / "_zenith_voice_temp.mp3", rel)
            _apagar(caminhos["raiz"] / "tmp", rel)
    log(f"[Zenith] Limpeza ({', '.join(categorias)}): {rel['itens']} item(ns), "
        f"{rel['bytes'] / 1024 / 1024:.1f} MB liberados" + (f"; {len(rel['falhas'])} não deu: {rel['falhas'][:3]}" if rel["falhas"] else "."))
    return rel


def fechar_zenith(raiz, executar=executar_comando):
    """Encerra o Zenith/Corpo que estiver rodando de dentro da pasta (senão o Windows não deixa apagar)."""
    if os.name != "nt":
        return False
    try:
        codigo, _ = executar(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              script_encerrar_pasta(raiz)], None, 60)
        return codigo == 0
    except Exception:
        return False


def _pode_apagar(p: Path) -> bool:
    """Trava de segurança: nunca apagar raiz de disco, pasta do usuário ou a pasta do projeto."""
    try:
        p = p.resolve()
    except Exception:
        return False
    if not p.exists():
        return False
    if len(p.parts) <= 2:                      # C:\, C:\Users, /home, /usr...
        return False
    proibidas = {Path.home().resolve(), Path(os.environ.get("USERPROFILE", "~")).resolve()}
    return p not in proibidas and p.name.lower() not in ("windows", "users", "desktop", "documents", "downloads")


def desinstalar_tudo(raiz, ui, executar=executar_comando) -> int:
    """Apaga QUALQUER resquício do Zenith: programa, Python dele, dados, atalhos, Corpo (Godot)."""
    raiz = Path(raiz)
    caminhos = caminhos_do_app(raiz)
    rel = {"itens": 0, "bytes": 0, "falhas": []}
    ui.status("Fechando o Zenith...")
    fechar_zenith(raiz, executar)
    time.sleep(1.0)
    alvos = [raiz]
    dados = caminhos["dados"]
    try:
        if dados.exists() and raiz not in dados.resolve().parents and "zenith" in str(dados).lower():
            alvos.append(dados)                 # pasta de dados escolhida FORA da instalação
    except Exception:
        pass
    godot = Path(os.environ.get("APPDATA", "")) / "Godot" / "app_userdata"
    for nome in ("Zenith", "zenith"):
        if (godot / nome).exists():
            alvos.append(godot / nome)          # config interna do Corpo (Godot)
    for alvo in alvos:
        if _pode_apagar(Path(alvo)):
            ui.status(f"Apagando {alvo}...")
            _apagar(alvo, rel)
    for lnk in _atalhos():
        _apagar(lnk, rel)
    total_mb = rel["bytes"] / 1024 / 1024
    if rel["falhas"]:
        ui.erro("Apaguei quase tudo, mas alguns itens ficaram presos:\n\n" + "\n".join(rel["falhas"][:8]) +
                "\n\nFeche o Zenith e rode este programa de novo.")
        return 2
    ui.status(f"Pronto: {total_mb:.0f} MB liberados. O Zenith e todo o histórico dele saíram deste computador.\n\n"
              f"Você ainda pode apagar à mão o arquivo do instalador que baixou (ZenithLauncher.exe), se quiser.")
    return 0


def _atalhos() -> list:
    """Atalhos que o Launcher cria: Área de Trabalho e Menu Iniciar."""
    saida = []
    if os.name != "nt":
        return saida
    try:
        ps = ("$d=[Environment]::GetFolderPath('Desktop'); $p=[Environment]::GetFolderPath('Programs'); "
              "Write-Output (Join-Path $d 'Zenith.lnk'); Write-Output (Join-Path $p 'Zenith.lnk')")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
        saida = [Path(x.strip()) for x in r.stdout.splitlines() if x.strip().lower().endswith(".lnk")]
    except Exception:
        pass
    return saida


def executar_limpeza(args, ui) -> int:
    """Caminho sem janela: --desinstalar ou --limpar a,b,c (com --sim para não perguntar)."""
    raiz = Path(getattr(args, "pasta", "") or raiz_padrao())
    if getattr(args, "desinstalar", False):
        if not ui.perguntar("Desinstalar o Zenith",
                            f"Isto apaga TUDO que o Zenith criou neste computador em {raiz}:\n"
                            "programa, conversas, memória, chaves de API, fotos e vídeos gerados, "
                            "programas que ele criou e os atalhos.\n\nNão tem como desfazer. Continuar?"):
            ui.status("Nada foi apagado.")
            return 0
        return desinstalar_tudo(raiz, ui)
    try:
        cats = ler_categorias(getattr(args, "limpar", "") or "*")
    except ErroInstalador as e:
        ui.erro(f"{e}\n{e.dica}".strip())
        return 3
    resumo = "; ".join(PEDACOS[c] for c in cats)
    if not ui.perguntar("Apagar do Zenith", f"Vou fechar o Zenith e apagar:\n\n{resumo}\n\nContinuar?"):
        ui.status("Nada foi apagado.")
        return 0
    fechar_zenith(raiz)
    rel = limpar_pedacos(raiz, cats, log=ui.status)
    ui.status(f"Feito: {rel['itens']} item(ns), {rel['bytes'] / 1024 / 1024:.1f} MB liberados.")
    return 0 if not rel["falhas"] else 2


# ============================================================================ o fluxo
class Console:
    """Interface mínima (sem janela): imprime e responde 'sim' só com --sim."""

    def __init__(self, sim=False):
        self.sim = sim

    def status(self, texto):
        print(texto, flush=True)

    def progresso(self, fracao):
        pass

    def perguntar(self, titulo, texto) -> bool:
        print(f"{titulo}\n{texto}")
        return bool(self.sim)

    def erro(self, texto):
        print("ERRO: " + texto, file=sys.stderr, flush=True)


def _passo_baixar(ui, rotulo, item, limite, hosts, destino, permitir_local, abrir):
    ui.status(rotulo)
    return baixar(item["url"], destino, item["sha256"], limite, hosts, progresso=ui.progresso,
                  abrir=abrir, permitir_local=permitir_local)


def instalar_ou_atualizar(raiz, man, ui, hosts, launcher_exe="", permitir_local=False, abrir=None,
                          executar=executar_comando, instalacao_nova=True) -> dict:
    """Baixa tudo, confere, troca a pasta, instala as bibliotecas e grava o estado. Não abre o Zenith."""
    raiz = Path(raiz)
    tmp = raiz / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    estado = ler_estado(raiz)
    py_precisa = (not python_exe(raiz).exists()) or estado.get("python") != man["python"]["versao"]
    if py_precisa:
        arq = _passo_baixar(ui, "Baixando o Python do Zenith...", man["python"], LIMITE_PYTHON, hosts,
                            tmp / "python_instalador.exe", permitir_local, abrir)
        ui.status("Instalando o Python (só para o Zenith, sem administrador)...")
        instalar_python(raiz, arq, executar)
        estado["python"] = man["python"]["versao"]
        estado.pop("requisitos_sha", None)               # Python novo: bibliotecas de novo
        gravar_estado(raiz, estado)
    zip_pacote = _passo_baixar(ui, f"Baixando o Zenith {man['versao']}...", man["pacote"], LIMITE_PACOTE, hosts,
                               tmp / f"zenith_{man['versao']}.zip", permitir_local, abrir)
    ui.status("Conferido. Preparando os arquivos...")
    staging = tmp / "app_novo"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    extrair_seguro(zip_pacote, staging)
    if not (staging / "zenith_launcher.py").exists():
        shutil.rmtree(staging, ignore_errors=True)
        raise ErroInstalador("O pacote baixado não é o Zenith (falta o zenith_launcher.py).", "Avise quem publicou.")
    if os.name == "nt" and (raiz / "app").exists():
        executar(["powershell", "-NoProfile", "-NonInteractive", "-Command", script_encerrar_pasta(raiz / "app")], None, 60)
    ui.status("Trocando a versão (a anterior fica guardada)...")
    trocar_app(raiz, staging)
    gravar_instalacao_json(raiz / "app", raiz / "dados")
    # bibliotecas: só mexe se o requirements.txt mudou (ou se é novo)
    req_arq = raiz / "app" / "requirements.txt"
    texto = req_arq.read_text(encoding="utf-8", errors="replace") if req_arq.exists() else ""
    sha_req = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    falhas = []
    if estado.get("requisitos_sha") != sha_req:
        obrig, opc = ler_requisitos(texto)
        ui.status("Instalando as bibliotecas do Python (a primeira vez demora; pode levar vários minutos)...")
        falhas = pip_instalar(raiz, obrig, opc, executar, linha=lambda ln: ui.status(ln[:90]) if ln.startswith(("Collecting", "Installing")) else None)
        estado["requisitos_sha"] = sha_req
    estado.update({"versao": man["versao"], "instalado_em": time.strftime("%Y-%m-%d %H:%M")})
    gravar_estado(raiz, estado)
    shutil.rmtree(tmp, ignore_errors=True)
    if instalacao_nova and launcher_exe:
        ui.status("Criando atalhos...")
        criar_atalhos(launcher_exe, executar)
    return {"versao": man["versao"], "opcionais_que_falharam": falhas}


def executar_launcher(args, ui, abrir=None, executar=executar_comando, popen=subprocess.Popen) -> int:
    """O 'main' sem interface: devolve o código de saída (0 = ok)."""
    cfg = carregar_config(args.manifesto)
    hosts, permitir_local = cfg["hosts"], cfg["permitir_local"]
    raiz = Path(args.pasta) if args.pasta else raiz_padrao()
    launcher_exe = sys.executable if getattr(sys, "frozen", False) else ""
    if launcher_exe:
        limpar_antigo(launcher_exe)
    if args.esperar_pid:
        ui.status("Esperando o Zenith fechar...")
        esperar_processo(args.esperar_pid)
    if args.reverter:
        ok = reverter(raiz)
        ui.status("Voltei para a versão anterior." if ok else "Não há versão anterior guardada.")
        return 0 if ok else 1
    estado = ler_estado(raiz)
    instalada = estado.get("versao", "")
    try:
        man = ler_manifesto(cfg["manifesto"], hosts, permitir_local, abrir)
    except ErroInstalador as e:
        man = None
        if not instalada:
            ui.erro(f"{e}\n{e.dica}".strip())
            return 2
        ui.status("Sem internet agora: abrindo a versão que você já tem.")
    try:
        if man and not instalada:
            tam = (man["pacote"]["tamanho"] + man["python"]["tamanho"]) / 1e6
            texto = (f"Vou instalar o Zenith {man['versao']} em:\n{raiz}\n\n"
                     "Isso baixa o Python próprio do Zenith e as bibliotecas (alguns GB, pode demorar). "
                     "Não precisa de administrador e não mexe no seu Python.\n"
                     + (f"Download inicial: cerca de {tam:.0f} MB.\n" if tam else "") + "\nContinuar?")
            if not ui.perguntar("Instalar o Zenith", texto):
                ui.status("Instalação cancelada. Nada foi baixado.")
                return 1
            instalar_ou_atualizar(raiz, man, ui, hosts, launcher_exe, permitir_local, abrir, executar, True)
        elif man and versao_tupla(man["versao"]) > versao_tupla(instalada):
            if args.atualizar or args.sim or ui.perguntar(
                    "Atualização do Zenith",
                    f"Versão nova: {man['versao']} (você tem {instalada}).\n\n{man['notas'] or ''}\n\n"
                    "Seus dados e configurações ficam como estão; a versão antiga fica guardada. Atualizar agora?"):
                instalar_ou_atualizar(raiz, man, ui, hosts, launcher_exe, permitir_local, abrir, executar, False)
        elif args.atualizar:
            ui.status(f"Você já está na versão mais nova ({instalada}).")
        if man and man.get("launcher") and launcher_exe and versao_tupla(man["launcher"]["versao"]) > versao_tupla(VERSAO_LAUNCHER):
            ui.status("Há uma versão nova do próprio Launcher; ela entra na próxima vez.")
    except ErroInstalador as e:
        ui.erro(f"{e}\n{e.dica}".strip())
        return 3
    if args.sem_abrir:
        return 0
    try:
        iniciar_app(raiz, launcher_exe, popen, cfg["manifesto"])
    except ErroInstalador as e:
        ui.erro(f"{e}\n{e.dica}".strip())
        return 4
    ui.status("Zenith aberto.")
    return 0


def carregar_config(manifesto_arg: str = "") -> dict:
    """launcher.json (ao lado do .exe ou dentro dele) + variável ZENITH_MANIFESTO + --manifesto."""
    cfg = {"manifesto": MANIFESTO_PADRAO, "hosts": list(HOSTS_PADRAO), "permitir_local": False}
    candidatos = []
    if getattr(sys, "frozen", False):
        candidatos += [Path(sys.executable).with_name("launcher.json"), Path(getattr(sys, "_MEIPASS", ".")) / "launcher.json"]
    candidatos.append(Path(__file__).with_name("launcher.json"))
    for c in candidatos:
        try:
            dados = json.loads(c.read_text(encoding="utf-8-sig"))
            if isinstance(dados, dict):
                cfg["manifesto"] = str(dados.get("manifesto") or cfg["manifesto"])
                if isinstance(dados.get("hosts"), list) and dados["hosts"]:
                    cfg["hosts"] = [str(h) for h in dados["hosts"]]
                cfg["permitir_local"] = bool(dados.get("permitir_local", False))
                break
        except Exception:
            continue
    if os.environ.get("ZENITH_MANIFESTO"):
        cfg["manifesto"] = os.environ["ZENITH_MANIFESTO"]
    if manifesto_arg:
        cfg["manifesto"] = manifesto_arg
    return cfg


# ============================================================================ janela (tkinter) — não testada em Linux
class JanelaTk:
    def __init__(self):
        import tkinter as tk
        from tkinter import messagebox, ttk
        self.tk, self.mb = tk, messagebox
        self.root = tk.Tk()
        self.root.title("Zenith")
        self.root.geometry("520x210")
        self.root.resizable(False, False)
        self.rotulo = tk.Label(self.root, text="Iniciando...", wraplength=480, justify="left", anchor="w")
        self.rotulo.pack(fill="x", padx=20, pady=(24, 8))
        self.barra = ttk.Progressbar(self.root, length=480, maximum=100)
        self.barra.pack(padx=20, pady=8)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

    def status(self, texto):
        self.root.after(0, lambda: self.rotulo.config(text=texto))

    def progresso(self, fracao):
        self.root.after(0, lambda: self.barra.config(value=fracao * 100))

    def perguntar(self, titulo, texto) -> bool:
        resp = {}
        evento = __import__("threading").Event()

        def _p():
            resp["v"] = self.mb.askyesno(titulo, texto)
            evento.set()
        self.root.after(0, _p)
        evento.wait()
        return bool(resp.get("v"))

    def erro(self, texto):
        self.root.after(0, lambda: self.mb.showerror("Zenith", texto))

    def rodar(self, trabalho) -> int:
        import threading
        codigo = {"v": 0}

        def _t():
            try:
                codigo["v"] = trabalho(self)
            except Exception as e:                      # nunca deixa a janela presa
                self.erro(f"Erro inesperado: {e}")
                codigo["v"] = 9
            self.root.after(800, self.root.destroy)
        threading.Thread(target=_t, daemon=True).start()
        self.root.mainloop()
        return codigo["v"]


class JanelaLimpeza:
    """Janela do LimparZenith.exe: uma caixinha por tipo de coisa, e a opção de desinstalar tudo.
    Existe para o pedido "apagar por partes" — só o histórico, só as chaves, só as fotos...
    """

    def __init__(self, raiz):
        import tkinter as tk
        from tkinter import messagebox
        self.tk, self.mb = tk, messagebox
        self.raiz = Path(raiz)
        self.root = tk.Tk()
        self.root.title("Zenith — Limpar e desinstalar")
        self.root.geometry("580x600")
        self.root.resizable(False, False)
        tk.Label(self.root, text="O que você quer apagar?",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(self.root, text=f"Instalação: {self.raiz}", fg="#555",
                 wraplength=540, justify="left").pack(anchor="w", padx=18)
        self.vars = {}
        for chave, texto in PEDACOS.items():
            v = tk.BooleanVar(value=False)
            self.vars[chave] = v
            tk.Checkbutton(self.root, text=texto, variable=v, anchor="w", justify="left",
                           wraplength=520).pack(fill="x", padx=18, pady=1)
        tk.Frame(self.root, height=1, bg="#cccccc").pack(fill="x", padx=18, pady=10)
        self.var_tudo = tk.BooleanVar(value=False)
        tk.Checkbutton(self.root, text="DESINSTALAR O ZENITH INTEIRO\n(programa, Python dele, tudo acima e os atalhos)",
                       variable=self.var_tudo, fg="#b00020", anchor="w", justify="left",
                       wraplength=520).pack(fill="x", padx=18)
        self.rotulo = tk.Label(self.root, text="Nada será apagado sem você confirmar.", fg="#555",
                               wraplength=540, justify="left")
        self.rotulo.pack(fill="x", padx=18, pady=10)
        barra = tk.Frame(self.root)
        barra.pack(fill="x", padx=18, pady=(0, 14))
        tk.Button(barra, text="Apagar o que está marcado", command=self.apagar,
                  bg="#f5a623", fg="#111").pack(side="left")
        tk.Button(barra, text="Fechar", command=self.root.destroy).pack(side="right")
        for v in list(self.vars.values()) + [self.var_tudo]:
            v.trace_add("write", lambda *_: self._atualizar())

    def _atualizar(self):
        if self.var_tudo.get():
            self.rotulo.config(text="Vai apagar o programa inteiro e todos os dados. Não tem como desfazer.")
            return
        marcados = [c for c, v in self.vars.items() if v.get()]
        self.rotulo.config(text=("Marcado: " + ", ".join(marcados) + ".") if marcados
                           else "Nada será apagado sem você confirmar.")

    def status(self, texto):
        self.root.after(0, lambda: self.rotulo.config(text=texto))

    def erro(self, texto):
        self.root.after(0, lambda: self.mb.showerror("Zenith", texto))

    def apagar(self):
        if self.var_tudo.get():
            if not self.mb.askyesno(
                    "Desinstalar o Zenith",
                    "Isto apaga TUDO que o Zenith criou neste computador:\n\n"
                    "• o programa e o Python dele\n• conversas e memória\n• chaves de API\n"
                    "• fotos e vídeos gerados\n• programas que ele criou\n• os atalhos\n\n"
                    "Não tem como desfazer. Continuar?"):
                return
            self._rodar(lambda ui: desinstalar_tudo(self.raiz, ui))
            return
        cats = [c for c, v in self.vars.items() if v.get()]
        if not cats:
            self.mb.showinfo("Zenith", "Marque pelo menos uma coisa para apagar.")
            return
        resumo = "\n".join("• " + PEDACOS[c] for c in cats)
        if not self.mb.askyesno("Apagar do Zenith",
                                f"O Zenith vai ser fechado e eu vou apagar:\n\n{resumo}\n\nContinuar?"):
            return
        self._rodar(lambda ui: self._limpar(cats, ui))

    def _limpar(self, cats, ui):
        ui.status("Fechando o Zenith...")
        fechar_zenith(self.raiz)
        time.sleep(1.0)
        rel = limpar_pedacos(self.raiz, cats, log=ui.status)
        texto = (f"Apaguei {rel['itens']} item(ns) — {rel['bytes'] / 1024 / 1024:.1f} MB liberados.")
        if rel["falhas"]:
            ui.status(texto + f" Mas {len(rel['falhas'])} não deu para apagar: " + "; ".join(rel["falhas"][:3]))
            return 2
        ui.status(texto + " Pode abrir o Zenith de novo.")
        return 0

    def _rodar(self, trabalho):
        import threading

        def _t():
            try:
                codigo = trabalho(self)
            except Exception as e:                       # nunca deixa a janela presa
                self.erro(f"Erro inesperado: {e}")
                codigo = 9

            def _fim():
                texto = self.rotulo.cget("text")
                if codigo == 0:
                    self.mb.showinfo("Zenith", texto or "Pronto.")
                self.root.destroy()
            self.root.after(0, _fim)
        threading.Thread(target=_t, daemon=True).start()


def analisar_argumentos(argv=None):
    p = argparse.ArgumentParser(description="Zenith Launcher")
    p.add_argument("--pasta", default="", help="onde instalar (padrão: %%LOCALAPPDATA%%\\Zenith)")
    p.add_argument("--manifesto", default="", help="endereço do latest.json (para testes)")
    p.add_argument("--atualizar", action="store_true", help="só atualizar (e abrir)")
    p.add_argument("--reverter", action="store_true", help="voltar para a versão anterior")
    p.add_argument("--sem-abrir", action="store_true", help="não abrir o Zenith no fim")
    p.add_argument("--silencioso", action="store_true", help="sem janela")
    p.add_argument("--sim", action="store_true", help="responde sim às perguntas (instalação sem supervisão)")
    p.add_argument("--esperar-pid", type=int, default=0, help="espera esse processo fechar antes de trocar arquivos")
    p.add_argument("--desinstalar", action="store_true", help="apaga o Zenith inteiro (programa + dados + atalhos)")
    p.add_argument("--limpar", nargs="?", const="*", default=None,
                   help="apaga só o que for listado: " + ",".join(categorias_validas()) + " (vazio = abre a janela)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = analisar_argumentos(argv)
    if args.desinstalar or args.limpar is not None:
        raiz = Path(args.pasta) if args.pasta else raiz_padrao()
        if args.silencioso or os.name != "nt":
            return executar_limpeza(args, Console(args.sim))
        try:
            janela = JanelaLimpeza(raiz)
        except Exception:
            return executar_limpeza(args, Console(args.sim))
        if args.limpar not in (None, "*"):              # lista na linha de comando: não é para abrir janela
            janela.root.destroy()
            return executar_limpeza(args, Console(args.sim))
        janela.root.mainloop()
        return 0
    if args.silencioso or os.name != "nt":
        return executar_launcher(args, Console(args.sim))
    try:
        janela = JanelaTk()
    except Exception:
        return executar_launcher(args, Console(args.sim))
    return janela.rodar(lambda ui: executar_launcher(args, ui))


if __name__ == "__main__":
    sys.exit(main())
