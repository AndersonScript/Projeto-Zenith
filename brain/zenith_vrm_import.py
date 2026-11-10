"""
Zenith — importação automática de avatar (brain/zenith_vrm_import.py) — v18.

REGRA DE OURO (decisão do Anderson, depois de muito teste): existe UMA
pasta só pra avatares — res://addons/avatars/ dentro do projeto Godot. Todo
.vrm, venha de onde vier, é COPIADO pra lá e importado pelo próprio Godot
(o único caminho que renderiza cabelo/roupa certo — o carregamento em tempo
real, "de fora", deforma e foi abandonado). O Python faz o vai-e-vem inteiro:

    1. copia o .vrm pra <projeto>/addons/avatars/        (sem duplicar)
    2. godot --headless --path <projeto> --import          (importa)
    3. godot --headless --path <projeto> --export-pack ... (reempacota o .pck)
    4. confere que o avatar de fato entrou no .pck novo
    5. para o Corpo, troca o Zenith.pck, sobe o Corpo de novo

Os dois comandos do Godot são oficiais e documentados
(https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).

NADA de configurar 4 caminhos: localizar_ambiente() descobre sozinho o editor
do Godot, a pasta do projeto, o preset de exportação e o .pck em uso. O único
campo que pode sobrar pro usuário é "onde está o editor do Godot", e só se o
Zenith não achar sozinho.

NUNCA TESTADO COM UM GODOT DE VERDADE (não existe um neste ambiente de
desenvolvimento): os testes usam um "Godot falso" que imita os argumentos de
linha de comando. Por isso cada etapa grava no "log" devolvido — dá pra
debugar sem adivinhar — e o Zenith.pck antigo sempre fica guardado (.bak).
"""
import hashlib
import mmap
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

TIMEOUT_VERSAO = 30
TIMEOUT_IMPORT = 900   # s — a 1ª importação, sem cache (.godot/), reimporta tudo e pode levar minutos
TIMEOUT_EXPORT = 900   # s
TAMANHO_MINIMO_PCK = 1_000_000   # 1 MB — bem menos que isso = exportação vazia/incompleta
PRESET_PADRAO = "Windows Desktop"
TENTATIVAS_ARQUIVO = 10          # antivírus costuma segurar arquivo recém-escrito por alguns segundos
ESPERA_ARQUIVO = 1.0

_em_andamento = threading.Lock()   # uma importação de cada vez


# ------------------------------------------------------------------
# utilidades pequenas
# ------------------------------------------------------------------
def _flags_sem_janela() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _rodar(cmd: list, timeout: int, log: list):
    log.append("$ " + " ".join(str(c) for c in cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout,
                           creationflags=_flags_sem_janela())
        log.append(f"(código de saída {r.returncode})")
        if (r.stdout or "").strip():
            log.append(r.stdout[-4000:])
        if (r.stderr or "").strip():
            log.append("[stderr] " + r.stderr[-4000:])
        return r
    except subprocess.TimeoutExpired:
        log.append(f"CANCELADO: passou de {timeout}s sem terminar.")
        return None
    except Exception as e:
        log.append(f"ERRO ao rodar: {e}")
        return None


def _com_repeticao(fazer, log: list, descricao: str):
    """Roda fazer(); se der PermissionError/OSError (arquivo segurado por
    antivírus ou ainda em uso), espera e tenta de novo. Levanta o último erro."""
    ultimo = None
    for tentativa in range(1, TENTATIVAS_ARQUIVO + 1):
        try:
            return fazer()
        except OSError as e:
            ultimo = e
            if tentativa == 1:
                log.append(f"{descricao}: arquivo em uso ({e}) — tentando de novo...")
            time.sleep(ESPERA_ARQUIVO)
    raise ultimo


def _dica_bloqueio() -> str:
    """Se o Controle Inteligente de Aplicativos do Windows está ligado, ele é o suspeito
    nº 1 de o Godot (sem assinatura digital) não abrir — diz isso em vez de só "falhou"."""
    try:
        from brain import zenith_diag
        codigo, _ = zenith_diag.estado_controle_inteligente()
    except Exception:
        return ""
    if codigo == "ligado":
        return (" O Controle Inteligente de Aplicativos do Windows está LIGADO e bloqueia programas sem "
                "assinatura digital (como o Godot) — veja NOTES_ANTIVIRUS.md.")
    return ""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _nome_seguro(nome: str) -> str:
    """Só letras/números/espaço/._- — o resto vira '_'. Mantém a extensão .vrm."""
    stem = Path(nome).stem
    limpo = "".join(c if (c.isalnum() or c in " ._-") else "_" for c in stem).strip(" .")
    if not any(c.isalnum() for c in limpo):
        limpo = "avatar"
    return limpo + ".vrm"


def _nome_sem_colisao(pasta: Path, nome_base: str) -> str:
    nome, n = nome_base, 2
    while (pasta / nome).exists():
        nome = f"{Path(nome_base).stem}_{n}.vrm"
        n += 1
    return nome


def _versao(texto: str):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", texto or "")
    return tuple(int(x) for x in m.groups() if x is not None) if m else None


# ------------------------------------------------------------------
# descoberta automática do ambiente
# ------------------------------------------------------------------
def _parece_godot(p: Path) -> bool:
    n = p.name.lower()
    if not n.startswith("godot") or "template" in n or "export" in n:
        return False
    if os.name == "nt":
        return p.suffix.lower() == ".exe" and p.is_file()
    return p.is_file() and os.access(p, os.X_OK)


def _achar_godot_em(pasta: Path) -> list:
    """Procura godot*.exe em `pasta` e até 2 níveis abaixo (sem varrer o disco todo)."""
    achados = []
    try:
        if not pasta.is_dir():
            return achados
        for padrao in ("*", "*/*", "*/*/*"):
            for p in pasta.glob(padrao):
                try:
                    if _parece_godot(p):
                        achados.append(p)
                except OSError:
                    continue
    except OSError:
        pass
    return achados


def _achar_godot_nas_raizes() -> list:
    """Windows: pastas "Godot*" direto na raiz dos discos (ex.: C:\\Godot_v4.7.1\\Godot_v4.7.1_win64.exe).
    Só olha as pastas cujo nome começa com "godot" — NÃO varre o disco inteiro."""
    achados = []
    if os.name != "nt":
        return achados
    for letra in "CDEFG":
        raiz = Path(f"{letra}:/")
        try:
            if not raiz.is_dir():
                continue
            for pasta in raiz.glob("[Gg]odot*"):
                if pasta.is_dir():
                    achados += _achar_godot_em(pasta)
                elif _parece_godot(pasta):
                    achados.append(pasta)
        except OSError:
            continue
    return achados


def _pastas_para_procurar_godot(base_dir: Path) -> list:
    home = Path.home()
    pastas = [base_dir / "tools" / "godot", base_dir / "tools", base_dir.parent,
              home / "Downloads", home / "Desktop", home / "Documents"]
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        pastas += [Path("C:/Godot"), Path("C:/Program Files/Godot"),
                   Path("C:/Program Files (x86)/Godot"),
                   Path("C:/Program Files (x86)/Steam/steamapps/common/Godot Engine"),
                   Path("C:/Program Files/Steam/steamapps/common/Godot Engine"),
                   local / "Programs" / "Godot",
                   local / "Microsoft" / "WinGet" / "Packages",
                   home / "scoop" / "apps" / "godot" / "current"]
    return pastas


def localizar_godot(base_dir, override: str = "", versao_minima=None, log: list = None):
    """Devolve o Path do executável do EDITOR do Godot, ou None.
    Ordem: campo opcional das Configurações > variáveis de ambiente > pasta
    tools/godot do Zenith > PATH > pastas comuns (Downloads, Desktop, C:\\Godot...).
    Entre vários achados, vale o de versão mais nova (e a variante *_console)."""
    log = log if log is not None else []
    base_dir = Path(base_dir)

    override = (override or "").strip().strip('"')
    if override:
        p = Path(override)
        if p.is_file() and p.name.lower().startswith("godot") and "template" not in p.name.lower():
            return p
        log.append(f"o caminho do editor do Godot nas Configurações não serve ({override}): precisa existir "
                   f"e o arquivo ter nome Godot*.exe. Procurando sozinho...")

    for var in ("ZENITH_GODOT", "GODOT_BIN", "GODOT"):
        v = os.environ.get(var, "").strip().strip('"')
        if v and Path(v).is_file():
            return Path(v)

    candidatos = []
    for nome in ("godot", "godot4", "Godot", "godot-editor"):
        w = shutil.which(nome)
        if w:
            candidatos.append(Path(w))
    for pasta in _pastas_para_procurar_godot(base_dir):
        candidatos += _achar_godot_em(pasta)
    candidatos += _achar_godot_nas_raizes()
    if not candidatos:
        return None

    def chave(p: Path):
        v = _versao(p.name) or (0,)
        bom = 1 if (versao_minima is None or v >= versao_minima[: len(v)] or v == (0,)) else 0
        return (bom, v, 1 if "console" in p.name.lower() else 0)

    vistos, unicos = set(), []
    for p in candidatos:
        k = str(p.resolve()).lower()
        if k not in vistos:
            vistos.add(k)
            unicos.append(p)
    unicos.sort(key=chave, reverse=True)
    log.append("editores do Godot encontrados: " + "; ".join(str(p) for p in unicos[:5]))
    return unicos[0]


def versao_do_projeto(project_dir: Path):
    """(4, 7) a partir de config/features=PackedStringArray("4.7", ...) do project.godot."""
    try:
        txt = (Path(project_dir) / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'config/features\s*=\s*PackedStringArray\(\s*"(\d+\.\d+)"', txt)
    return _versao(m.group(1)) if m else None


def versao_do_godot(godot_bin: Path, log: list):
    r = _rodar([str(godot_bin), "--version"], TIMEOUT_VERSAO, log)
    if r is None or r.returncode != 0:
        return None
    saida = (r.stdout or "") + " " + (r.stderr or "")
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?\.(stable|dev|beta|rc|alpha)", saida)
    return tuple(int(x) for x in m.groups()[:3] if x is not None) if m else None


def _ler_presets(project_dir: Path) -> list:
    """[{"nome","plataforma","embute_pck","encripta_diretorio"}] de export_presets.cfg."""
    try:
        txt = (Path(project_dir) / "export_presets.cfg").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    presets = []
    for corpo in re.split(r"(?m)^\[preset\.\d+\]\s*$", txt)[1:]:
        # `corpo` vai até o próximo [preset.N] e inclui o [preset.N.options] dele
        # (é lá que mora binary_format/embed_pck).
        nome = re.search(r'(?m)^name="([^"]*)"', corpo)
        plat = re.search(r'(?m)^platform="([^"]*)"', corpo)
        emb = re.search(r"(?m)^binary_format/embed_pck\s*=\s*(true|false)", corpo)
        enc = re.search(r"(?m)^encrypt_directory\s*=\s*(true|false)", corpo)
        if nome:
            presets.append({"nome": nome.group(1), "plataforma": plat.group(1) if plat else "",
                            "embute_pck": bool(emb and emb.group(1) == "true"),
                            "encripta_diretorio": bool(enc and enc.group(1) == "true")})
    return presets


def localizar_ambiente(base_dir, settings_get=None) -> dict:
    """Descobre TUDO sozinho. `settings_get(chave, padrao)` é opcional (overrides
    avançados). Devolve {"godot_bin","project_dir","pck_destino","export_preset",
    "faltando": [str], "log": str}. Nunca levanta exceção."""
    log: list = []
    get = settings_get or (lambda k, d="": d)
    base_dir = Path(base_dir)
    faltando = []

    # --- Corpo (Zenith.exe/.pck em uso) ---
    exe_cfg = str(get("godot_executable_path", "") or "").strip()
    corpo_candidatos = ([Path(exe_cfg)] if exe_cfg else []) + [
        base_dir / "body" / "zenith" / "export" / "Zenith.exe",
        base_dir / "body" / "zenith" / "Zenith.exe"]
    corpo_exe = next((c for c in corpo_candidatos if c.is_file()), None)
    pck = ""
    if corpo_exe:
        pck = str(corpo_exe.with_suffix(".pck"))
    else:
        log.append("não achei o Zenith.exe do Corpo (procurei em body/zenith/export/).")
        faltando.append("o Corpo exportado do Godot (body/zenith/export/Zenith.exe)")

    # --- Projeto Godot completo ---
    proj_override = str(get("vrm_auto_import_project_dir", "") or "").strip().strip('"')
    proj_candidatos = ([Path(proj_override)] if proj_override else []) + [base_dir / "body" / "zenith"]
    if corpo_exe:
        proj_candidatos += [corpo_exe.parent.parent, corpo_exe.parent]
    project_dir = next((p for p in proj_candidatos if (p / "project.godot").is_file()), None)
    if project_dir is None:
        faltando.append("a pasta do projeto Godot completo (body/zenith, com o project.godot dentro)")

    # --- Preset ---
    preset = str(get("vrm_auto_import_preset", "") or "").strip()
    presets = _ler_presets(project_dir) if project_dir else []
    if not preset:
        win = [p["nome"] for p in presets if p["plataforma"] == "Windows Desktop"]
        preset = win[0] if win else (presets[0]["nome"] if presets else PRESET_PADRAO)

    # --- Editor do Godot ---
    godot = None
    if project_dir is not None:
        godot = localizar_godot(base_dir, str(get("vrm_auto_import_godot_bin", "") or ""),
                                versao_do_projeto(project_dir), log)
    if godot is None:
        faltando.append("o editor do Godot (o programa que você usa pra abrir o projeto)")

    return {"godot_bin": str(godot) if godot else "", "project_dir": str(project_dir) if project_dir else "",
            "pck_destino": pck, "export_preset": preset, "faltando": faltando, "log": "\n".join(log)}


def explicar_faltando(faltando: list, base_dir) -> str:
    """Frase pro usuário dizendo o que fazer, sem jargão."""
    if not faltando:
        return ""
    itens = "; ".join(faltando)
    dica = ""
    if any("editor do Godot" in f for f in faltando):
        dica = (f" Coloque o Godot (o .exe do editor, versão 4.x) em \"{Path(base_dir) / 'tools' / 'godot'}\" — "
                f"o Zenith acha sozinho — ou, se ele já está em outro lugar, cole o caminho em "
                f"Configurações > Corpo / VRM > \"Editor do Godot\".")
    return f"Pra importar o avatar sozinho me falta: {itens}.{dica}"


# ------------------------------------------------------------------
# verificações
# ------------------------------------------------------------------
def _destino_importado(import_file: Path, project_dir: Path):
    """Lê `path="res://.godot/imported/X.vrm-hash.scn"` do .import e devolve o Path real no disco."""
    try:
        txt = import_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'(?m)^path\s*=\s*"res://([^"]+)"', txt)
    return (Path(project_dir) / m.group(1)) if m else None


def _importacao_ok(vrm: Path, project_dir: Path):
    """(ok, motivo). Só existir o .import não basta: ele nasce ANTES da cena pronta."""
    imp = Path(str(vrm) + ".import")
    if not imp.is_file():
        return False, "o Godot não gerou o arquivo .import"
    dest = _destino_importado(imp, project_dir)
    if dest is None:
        return False, "o .import não aponta pra nenhuma cena importada (importação pulada?)"
    if not dest.is_file() or dest.stat().st_size < 1000:
        return False, f"a cena importada não existe ou está vazia ({dest.name})"
    return True, ""


def _pck_contem(pck: Path, caminho_rel: str) -> bool:
    """O diretório do .pck guarda os caminhos como texto — procura o da cena importada."""
    alvo = caminho_rel.replace("\\", "/").encode("utf-8")
    try:
        with open(pck, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            return mm.find(alvo) != -1
    except (OSError, ValueError):
        return False


def _limpar_avatar(vrm: Path, project_dir: Path, log: list):
    """Desfaz uma cópia que não deu certo: o .vrm, o .import e a cena em .godot/imported."""
    try:
        imp = Path(str(vrm) + ".import")
        dest = _destino_importado(imp, project_dir) if imp.is_file() else None
        for p in (vrm, imp, dest):
            if p is not None and Path(p).exists():
                Path(p).unlink()
        for sobra in (Path(project_dir) / ".godot" / "imported").glob(f"{vrm.name}-*"):
            sobra.unlink()
        log.append(f"limpeza: {vrm.name} removido do projeto.")
    except OSError as e:
        log.append(f"limpeza incompleta: {e}")


# ------------------------------------------------------------------
# pipeline principal
# ------------------------------------------------------------------
def importar_vrm(vrm_origem: str, config: dict, progresso=None, trocar=None,
                 antes_de_trocar=None) -> dict:
    """config: {"godot_bin","project_dir","export_preset","pck_destino"}.
    progresso(msg): chamado a cada etapa. trocar(fazer_troca) -> {"reiniciou",
    "resultado","erro"}: quem para o Corpo, roda fazer_troca() e sobe ele de novo
    (zenith_body_control.trocar_e_reiniciar); sem isso a troca roda direto e o
    usuário é avisado pra reabrir na mão. antes_de_trocar(info): chamado com o
    avatar pronto, logo antes de parar o Corpo (pra gravar configuração/histórico).
    Devolve {"ok","mensagem","log","nome","avatar_path","reiniciou"}. Nunca levanta exceção."""
    log: list = []
    if not _em_andamento.acquire(blocking=False):
        return {"ok": False, "mensagem": "já tem uma importação de avatar em andamento — espere terminar.",
                "log": "", "nome": "", "avatar_path": "", "reiniciou": False}
    try:
        return _importar_interno(vrm_origem, config or {}, log, progresso or (lambda m: None),
                                 trocar, antes_de_trocar)
    except Exception as e:
        log.append(f"ERRO inesperado: {e}")
        return {"ok": False, "mensagem": f"erro inesperado durante a importação: {e}",
                "log": "\n".join(log), "nome": "", "avatar_path": "", "reiniciou": False}
    finally:
        _em_andamento.release()


def _importar_interno(vrm_origem, config, log, progresso, trocar, antes_de_trocar) -> dict:
    godot_bin = str(config.get("godot_bin") or "").strip()
    project_dir = str(config.get("project_dir") or "").strip()
    export_preset = str(config.get("export_preset") or "").strip() or PRESET_PADRAO
    pck_destino = str(config.get("pck_destino") or "").strip()

    def falha(msg, nome="", avatar_path="", reiniciou=False):
        return {"ok": False, "mensagem": msg, "log": "\n".join(log), "nome": nome,
                "avatar_path": avatar_path, "reiniciou": reiniciou}

    if not (godot_bin and project_dir and pck_destino):
        return falha("a importação automática não achou o que precisa (editor do Godot, projeto "
                     "e Zenith.pck). Veja o log.")

    origem = Path(str(vrm_origem or "").strip().strip('"'))
    if not origem.is_file():
        return falha(f"não achei o arquivo: {origem}")
    if origem.suffix.lower() != ".vrm":
        return falha("isso não é um arquivo .vrm.")

    # Mesma regra do salvamento de configurações (zenith_content_safety): recusa definitiva.
    try:
        from brain.zenith_content_safety import vrm_filename_suspicious
        if vrm_filename_suspicious(str(origem)):
            return falha("nome de arquivo recusado — indica conteúdo envolvendo menor de idade. "
                         "Isso não é negociável.")
    except ImportError:
        pass

    godot_p = Path(godot_bin)
    if not godot_p.is_file():
        return falha(f"não achei o executável do editor do Godot em: {godot_bin}")
    project_p = Path(project_dir)
    if not (project_p / "project.godot").is_file():
        return falha(f"não achei project.godot dentro de: {project_dir}")
    pck_p = Path(pck_destino)
    if not pck_p.parent.is_dir():
        return falha(f"a pasta do Zenith.pck não existe: {pck_p.parent}")

    avatars_dir = project_p / "addons" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    preset = next((p for p in _ler_presets(project_p) if p["nome"] == export_preset), None)
    if preset and preset["embute_pck"]:
        return falha(f"o preset \"{export_preset}\" embute o .pck dentro do .exe — não dá pra trocar só o "
                     f"pacote. Desligue \"Embed PCK\" em Projeto > Exportar e exporte de novo.")

    # versão do editor x versão do projeto
    v_proj, v_godot = versao_do_projeto(project_p), versao_do_godot(godot_p, log)
    if v_godot is None:
        return falha(f"o executável \"{godot_p.name}\" não respondeu a --version — não parece ser o "
                     f"editor do Godot (use o Godot_v4.x_win64.exe, não o Zenith.exe). Veja o log.")
    if v_proj and v_godot[:2] < v_proj[:2]:
        return falha(f"o editor do Godot é o {'.'.join(map(str, v_godot))}, mais antigo que o do projeto "
                     f"({'.'.join(map(str, v_proj))}). Use o mesmo Godot (ou mais novo) que você usa pra editar.")

    # 1) copia pro projeto — sem duplicar
    progresso("Copiando o avatar pra pasta do projeto...")
    nome_base = _nome_seguro(origem.name)
    copiado_agora = True
    alvo = avatars_dir / nome_base
    if alvo.exists():
        if alvo.stat().st_size == origem.stat().st_size and _sha256(alvo) == _sha256(origem):
            copiado_agora = False
            log.append(f"{nome_base} já está no projeto (mesmo conteúdo) — só reimporto/reempacoto.")
        else:
            nome_base = _nome_sem_colisao(avatars_dir, nome_base)
            alvo = avatars_dir / nome_base
    if copiado_agora:
        try:
            _com_repeticao(lambda: shutil.copy2(origem, alvo), log, "copiar o .vrm")
            log.append(f"copiado: {origem} -> {alvo}")
        except OSError as e:
            return falha(f"não consegui copiar o arquivo pro projeto: {e}")

    avatar_path = f"res://addons/avatars/{nome_base}"
    nome_exibicao = Path(nome_base).stem

    def desfazer():
        if copiado_agora:
            _limpar_avatar(alvo, project_p, log)

    # 2) importa (headless) — até 2 tentativas: na 1ª vez sem .godot/ os plugins do
    #    projeto às vezes só ficam prontos depois de uma primeira passada.
    ok_imp, motivo = False, ""
    for tentativa in (1, 2):
        progresso("Importando no Godot (a primeira vez pode levar alguns minutos)..." if tentativa == 1
                  else "Importando de novo (o Godot pede uma segunda passada na 1ª vez)...")
        r = _rodar([str(godot_p), "--headless", "--path", str(project_p), "--import"], TIMEOUT_IMPORT, log)
        if r is None:
            desfazer()
            return falha("a importação não terminou (passou do tempo ou o Godot não abriu — veja o log)."
                         + _dica_bloqueio(), nome_exibicao, avatar_path)
        ok_imp, motivo = _importacao_ok(alvo, project_p)
        if ok_imp:
            break
        log.append(f"importação (tentativa {tentativa}) incompleta: {motivo}")
    if not ok_imp:
        desfazer()
        return falha(f"o Godot rodou, mas não importou o avatar ({motivo}). O arquivo pode estar "
                     f"corrompido ou não ser um VRM válido. Veja o log.", nome_exibicao, avatar_path)
    cena_rel = str(_destino_importado(Path(str(alvo) + ".import"), project_p).relative_to(project_p))
    log.append(f"importado: {cena_rel}")

    # 3) exporta só o .pck, direto na pasta do destino (mesmo volume -> troca atômica depois)
    progresso("Empacotando o avatar pro Zenith...")
    pck_novo = pck_p.with_name("Zenith_novo.pck")
    for sobra in (pck_novo,):
        try:
            sobra.unlink(missing_ok=True)
        except OSError:
            pass
    r = _rodar([str(godot_p), "--headless", "--path", str(project_p), "--export-pack",
                export_preset, str(pck_novo)], TIMEOUT_EXPORT, log)
    if r is None:
        return falha("a exportação do pacote não terminou (veja o log). O avatar ficou no projeto, mas o "
                     "Zenith.pck em uso não foi trocado." + _dica_bloqueio(), nome_exibicao, avatar_path)
    tamanho = pck_novo.stat().st_size if pck_novo.is_file() else 0
    if tamanho < TAMANHO_MINIMO_PCK:
        pck_novo.unlink(missing_ok=True)
        return falha(f"o pacote gerado está incompleto ({tamanho} bytes). Confira se o preset "
                     f"\"{export_preset}\" existe em Projeto > Exportar (e se os modelos de exportação do "
                     f"Godot estão instalados). Veja o log.", nome_exibicao, avatar_path)
    if not (preset and preset["encripta_diretorio"]) and not _pck_contem(pck_novo, cena_rel):
        pck_novo.unlink(missing_ok=True)
        return falha("o pacote novo foi gerado mas o avatar NÃO entrou nele — não troquei o Zenith.pck "
                     "pra não perder nada. Veja o log.", nome_exibicao, avatar_path)
    log.append(f"pacote novo: {pck_novo} ({tamanho} bytes) — avatar confirmado dentro dele.")

    # 4) grava o que precisa ficar salvo e troca o .pck (com o Corpo parado)
    if antes_de_trocar:
        try:
            antes_de_trocar({"nome": nome_exibicao, "avatar_path": avatar_path})
        except Exception as e:
            log.append(f"aviso: antes_de_trocar falhou ({e}) — seguindo.")

    def fazer_troca():
        backup = pck_p.with_name(pck_p.name + ".bak")
        if pck_p.exists():
            _com_repeticao(lambda: shutil.copy2(pck_p, backup), log, "guardar o .pck antigo")
            log.append(f"backup do .pck antigo: {backup}")
        _com_repeticao(lambda: os.replace(pck_novo, pck_p), log, "trocar o Zenith.pck")
        log.append(f"substituído: {pck_p}")
        return True

    progresso("Reiniciando o Corpo pra carregar o avatar novo...")
    def _troca_direta(f):
        try:
            return {"reiniciou": False, "resultado": f(), "erro": ""}
        except Exception as e:
            return {"reiniciou": False, "resultado": None, "erro": str(e)}
    t = (trocar or _troca_direta)(fazer_troca)
    if t.get("erro") or not t.get("resultado"):
        pck_novo.unlink(missing_ok=True)
        return falha(f"o pacote novo está pronto, mas não consegui trocar o Zenith.pck em uso: "
                     f"{t.get('erro') or 'erro desconhecido'}. Se um antivírus estiver segurando o arquivo, "
                     f"adicione a pasta do Zenith às exclusões dele e tente de novo.",
                     nome_exibicao, avatar_path, reiniciou=bool(t.get("reiniciou")))

    reiniciou = bool(t.get("reiniciou"))
    msg = (f"Avatar \"{nome_exibicao}\" importado. O Corpo reiniciou sozinho com ele." if reiniciou else
           f"Avatar \"{nome_exibicao}\" importado e empacotado. FECHE E ABRA O ZENITH pra usar — "
           f"o Corpo só lê o pacote novo quando inicia.")
    return {"ok": True, "mensagem": msg, "log": "\n".join(log), "nome": nome_exibicao,
            "avatar_path": avatar_path, "reiniciou": reiniciou}
