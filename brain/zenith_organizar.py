"""
Zenith — ORGANIZAR PASTAS e LIMPAR ARQUIVOS INÚTEIS (v28).

O pedido do Anderson: "quero que organize minhas pastas e jogue fora arquivos inúteis — ela pergunta, como vou ver isso?".
O desenho é "PLANO → VOCÊ VÊ E APROVA → QUARENTENA (com desfazer)":

  1. VARRER (só leitura): olha a pasta que você indicou e monta um PLANO — nada é mexido nesta etapa.
  2. O PLANO aparece na janela de aprovação (Pilar 1): quantos arquivos, o que vai pra onde, o que seria "jogado fora",
     com exemplos e o espaço que sobra. Você aprova ou nega.
  3. Aprovado: os arquivos "inúteis" NÃO são apagados — vão pra uma pasta de QUARENTENA (`creations/quarentena/<data>/`), com
     uma lista (manifest.json) de onde cada um estava. `/quarentena desfazer` devolve tudo. Só `/quarentena esvaziar confirmar`
     apaga de verdade — e é um comando seu, digitado.

O que conta como "inútil" (conservador de propósito): arquivo VAZIO (0 bytes), lixo de sistema/Office (Thumbs.db, .DS_Store,
~$arquivo.docx), downloads incompletos antigos (.crdownload/.part/.tmp com mais de 1 dia) e CÓPIAS EXATAS (mesmo conteúdo,
conferido por hash — fica a mais antiga). Instaladores antigos (.exe/.msi com +90 dias) só entram no modo "agressivo".

Segurança: nunca roda em pasta de sistema (Windows, Program Files, AppData, /etc…), na raiz de um disco, na sua pasta de
usuário inteira, nem na pasta do próprio Zenith; não segue atalhos/links; ignora pastas de projeto (.git, node_modules, venv);
nunca sobrescreve (nome repetido ganha _2); o plano é conferido de novo na hora de aplicar.

Lógica pura (sem Godot/IA) — testável com pastas temporárias.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

LIMITE_ARQUIVOS = 20000
LIMITE_SEGUNDOS = 40
LIMITE_BYTES_HASH = 4 * 1024 ** 3
LIMITE_OPS = 5000
PROFUNDIDADE_DUPLICADOS = 4
DIAS_INCOMPLETO = 1
DIAS_INSTALADOR = 90

CATEGORIAS = {
    "Imagens": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tif", ".tiff", ".ico"},
    "Vídeos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v"},
    "Áudios": {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"},
    "Documentos": {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf", ".md", ".epub"},
    "Planilhas": {".xls", ".xlsx", ".csv", ".ods", ".tsv"},
    "Apresentações": {".ppt", ".pptx", ".odp"},
    "Compactados": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2"},
    "Programas": {".exe", ".msi", ".apk", ".dmg", ".iso"},
    "Código": {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".gd", ".ino", ".json", ".sql", ".ipynb"},
}
_NOMES_LIXO = {"thumbs.db", ".ds_store"}
_EXT_INCOMPLETO = {".crdownload", ".part", ".tmp", ".partial"}
_PASTAS_IGNORADAS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".idea", ".vscode", "$recycle.bin",
                     "system volume information", ".trash"}


class ErroOrganizar(Exception):
    """Mensagem já em português, pronta pro chat."""


# ----------------------------------------------------------------------------------------------- proteção
def _pastas_de_sistema() -> list:
    ps = []
    for var in ("WINDIR", "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData", "APPDATA", "LOCALAPPDATA"):
        v = os.environ.get(var)
        if v:
            ps.append(Path(v))
    if os.name != "nt":
        ps += [Path(p) for p in ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/proc", "/root", "/run",
                                 "/sbin", "/sys", "/usr", "/var", "/opt", "/snap", "/System", "/Library", "/Applications")]
    return ps


def _dentro_de(p: Path, base: Path) -> bool:
    try:
        p.relative_to(base)
        return True
    except ValueError:
        return False


def pasta_protegida(pasta, extra: tuple = ()) -> str | None:
    """Motivo (texto) se NÃO pode organizar essa pasta; None se pode."""
    try:
        p = Path(pasta).expanduser().resolve()
    except (OSError, RuntimeError):
        return "não consegui entender esse caminho"
    if not p.is_dir():
        return "isso não é uma pasta que existe"
    if p.parent == p:
        return "é a raiz de um disco — grande demais e perigoso"
    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        home = None
    if home and p == home:
        return "é a sua pasta de usuário inteira — escolha uma subpasta (Downloads, Documentos…)"
    if home and p == home.parent:
        return "é a pasta de todos os usuários do computador"
    for s in _pastas_de_sistema():
        try:
            sr = s.resolve()
        except (OSError, RuntimeError):
            continue
        if p == sr or _dentro_de(p, sr):
            return f"é uma pasta do sistema/programas ({s})"
    for e in extra:
        try:
            er = Path(e).resolve()
        except (OSError, RuntimeError):
            continue
        if p == er or _dentro_de(p, er) or _dentro_de(er, p):
            return "é (ou contém) a pasta do próprio Zenith"
    return None


# ----------------------------------------------------------------------------------------------- varredura
def categoria_de(nome: str) -> str:
    ext = Path(nome).suffix.lower()
    for cat, exts in CATEGORIAS.items():
        if ext in exts:
            return cat
    return "Outros"


def tamanho_legivel(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def _hash(caminho: str, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while True:
            b = f.read(bloco)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _andar(raiz: Path, profundidade_max: int, deadline: float, limite: int):
    """Gera (caminho, nivel) de arquivos reais (sem seguir links, sem pastas de projeto). Para no limite/tempo."""
    vistos = 0
    pilha = [(raiz, 0)]
    while pilha:
        pasta, nivel = pilha.pop()
        try:
            with os.scandir(pasta) as it:
                entradas = list(it)
        except OSError:
            continue
        for e in entradas:
            if time.monotonic() > deadline or vistos >= limite:
                return
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if e.name.lower() not in _PASTAS_IGNORADAS and nivel < profundidade_max:
                        pilha.append((Path(e.path), nivel + 1))
                elif e.is_file(follow_symlinks=False):
                    vistos += 1
                    yield Path(e.path), nivel
            except OSError:
                continue


def varrer(pasta, modo: str = "tudo", agressivo: bool = False, extra_protegidas: tuple = (), progresso=None,
           agora: float | None = None) -> dict:
    """SÓ LEITURA. Devolve o PLANO: {"raiz","modo","ops":[{tipo,origem,destino,motivo,tam}],"resumo":{...},"truncado":bool}.
    modo: "limpar" (inúteis + cópias) | "organizar" (arrumar por tipo) | "tudo"."""
    motivo = pasta_protegida(pasta, extra_protegidas)
    if motivo:
        raise ErroOrganizar(f"🗂️ Não vou mexer nessa pasta: {motivo}.")
    if modo not in ("limpar", "organizar", "tudo"):
        modo = "tudo"
    raiz = Path(pasta).expanduser().resolve()
    agora = agora if agora is not None else time.time()
    deadline = time.monotonic() + LIMITE_SEGUNDOS
    arquivos = []
    for caminho, nivel in _andar(raiz, PROFUNDIDADE_DUPLICADOS, deadline, LIMITE_ARQUIVOS):
        try:
            st = caminho.stat()
        except OSError:
            continue
        arquivos.append({"caminho": str(caminho), "nome": caminho.name, "tam": st.st_size, "mtime": st.st_mtime, "nivel": nivel})
        if progresso and len(arquivos) % 200 == 0:
            progresso(-1, f"Olhando a pasta… {len(arquivos)} arquivos")
    truncado = len(arquivos) >= LIMITE_ARQUIVOS or time.monotonic() > deadline
    ops, ja = [], set()

    def add(tipo, f, motivo_txt, destino=""):
        if f["caminho"] in ja or len(ops) >= LIMITE_OPS:
            return
        ja.add(f["caminho"])
        ops.append({"tipo": tipo, "origem": f["caminho"], "destino": destino, "motivo": motivo_txt, "tam": f["tam"]})

    if modo in ("limpar", "tudo"):
        for f in arquivos:
            nome, ext = f["nome"].lower(), Path(f["nome"]).suffix.lower()
            idade_d = (agora - f["mtime"]) / 86400
            if f["tam"] == 0:
                add("quarentena", f, "arquivo vazio (0 bytes)")
            elif nome in _NOMES_LIXO or nome.startswith("~$"):
                add("quarentena", f, "lixo de sistema/Office")
            elif ext in _EXT_INCOMPLETO and idade_d >= DIAS_INCOMPLETO:
                add("quarentena", f, "download incompleto/temporário antigo")
            elif agressivo and ext in (".exe", ".msi") and idade_d >= DIAS_INSTALADOR and f["nivel"] == 0:
                add("quarentena", f, f"instalador com mais de {DIAS_INSTALADOR} dias")
        # cópias exatas: mesmo tamanho -> mesmo hash; fica a mais ANTIGA (depois o caminho mais curto)
        por_tam = {}
        for f in arquivos:
            if f["tam"] > 0 and f["caminho"] not in ja:
                por_tam.setdefault(f["tam"], []).append(f)
        gasto = 0
        for tam, grupo in por_tam.items():
            if len(grupo) < 2 or gasto > LIMITE_BYTES_HASH or time.monotonic() > deadline:
                continue
            por_hash = {}
            for f in grupo:
                try:
                    por_hash.setdefault(_hash(f["caminho"]), []).append(f)
                    gasto += f["tam"]
                except OSError:
                    continue
            for fs in por_hash.values():
                if len(fs) < 2:
                    continue
                fs.sort(key=lambda x: (x["mtime"], len(x["caminho"])))
                for extra in fs[1:]:
                    add("quarentena", extra, f"cópia exata de «{fs[0]['nome']}»")
    if modo in ("organizar", "tudo"):
        for f in arquivos:
            if f["nivel"] != 0 or f["caminho"] in ja or f["nome"].startswith("."):
                continue
            cat = categoria_de(f["nome"])
            if cat == "Outros":
                continue
            add("mover", f, f"vai pra «{cat}»", str(raiz / cat / f["nome"]))
    resumo = {"arquivos_vistos": len(arquivos), "mover": sum(1 for o in ops if o["tipo"] == "mover"),
              "quarentena": sum(1 for o in ops if o["tipo"] == "quarentena"),
              "bytes_quarentena": sum(o["tam"] for o in ops if o["tipo"] == "quarentena")}
    return {"raiz": str(raiz), "modo": modo, "agressivo": agressivo, "ops": ops, "resumo": resumo, "truncado": truncado,
            "criado_em": time.strftime("%Y-%m-%d %H:%M:%S")}


# ----------------------------------------------------------------------------------------------- texto do plano
def formatar_plano(plano: dict, exemplos: int = 8) -> str:
    r = plano["resumo"]
    linhas = [f"[ORGANIZAR PASTA]\n{'─' * 40}", f"Pasta: {plano['raiz']}",
              f"Olhei {r['arquivos_vistos']} arquivo(s)" + (" (a pasta é enorme — olhei só uma parte)" if plano.get("truncado") else "") + "."]
    if not plano["ops"]:
        linhas.append("\n✓ Nada pra fazer: não achei arquivo inútil nem cópia, e a pasta já está arrumada.")
        return "\n".join(linhas)
    q = [o for o in plano["ops"] if o["tipo"] == "quarentena"]
    m = [o for o in plano["ops"] if o["tipo"] == "mover"]
    if q:
        linhas.append(f"\n🗑 {len(q)} arquivo(s) INÚTEIS → vão pra QUARENTENA (não apago nada; dá pra desfazer) — libera {tamanho_legivel(r['bytes_quarentena'])}:")
        por_motivo = {}
        for o in q:
            rotulo = "cópia exata (arquivo repetido; fica o mais antigo)" if "«" in o["motivo"] else o["motivo"]
            por_motivo.setdefault(rotulo, []).append(o)
        for mot, ops in por_motivo.items():
            linhas.append(f"  • {len(ops)} × {mot}")
            for o in ops[:max(1, exemplos // max(1, len(por_motivo)))]:
                linhas.append(f"      - {os.path.relpath(o['origem'], plano['raiz'])}")
    if m:
        por_cat = {}
        for o in m:
            por_cat.setdefault(Path(o["destino"]).parent.name, []).append(o)
        linhas.append(f"\n📂 {len(m)} arquivo(s) vão ser ARRUMADOS em subpastas por tipo:")
        for cat, ops in sorted(por_cat.items(), key=lambda x: -len(x[1])):
            linhas.append(f"  • {cat}: {len(ops)} (ex.: {', '.join(Path(o['origem']).name for o in ops[:2])})")
    linhas.append("\nNada é apagado agora. Depois de aprovar, /quarentena lista e /quarentena desfazer devolve tudo.")
    return "\n".join(linhas)


# ----------------------------------------------------------------------------------------------- aplicar / desfazer
def _unico(caminho: Path) -> Path:
    if not caminho.exists():
        return caminho
    n = 2
    while True:
        novo = caminho.with_name(f"{caminho.stem}_{n}{caminho.suffix}")
        if not novo.exists():
            return novo
        n += 1


def aplicar(plano: dict, pasta_quarentena, progresso=None, cancelado=None, extra_protegidas: tuple = ()) -> dict:
    """Executa o plano JÁ APROVADO. Confere tudo de novo, nunca sobrescreve, grava o manifest pra desfazer."""
    raiz = Path(plano["raiz"]).resolve()
    motivo = pasta_protegida(raiz, extra_protegidas)
    if motivo:
        raise ErroOrganizar(f"🗂️ Não vou mexer nessa pasta: {motivo}.")
    ops = plano.get("ops") or []
    if len(ops) > LIMITE_OPS:
        raise ErroOrganizar("🗂️ Plano grande demais.")
    carimbo = time.strftime("%Y%m%d_%H%M%S")
    base_q = Path(pasta_quarentena) / carimbo
    movidos, falhas = [], []
    for i, op in enumerate(ops, 1):
        if cancelado and cancelado():
            falhas.append("parado a pedido")
            break
        if progresso and (i % 5 == 0 or i == len(ops)):
            progresso(100.0 * i / len(ops), f"{i} de {len(ops)}")
        try:
            orig = Path(op["origem"]).resolve()
            if not _dentro_de(orig, raiz) or not orig.is_file() or orig.is_symlink():
                falhas.append(f"{orig.name}: não está mais lá")
                continue
            if op["tipo"] == "quarentena":
                dest = _unico(base_q / "arquivos" / orig.relative_to(raiz))
            elif op["tipo"] == "mover":
                dest = _unico(Path(op["destino"]).resolve())
                if not _dentro_de(dest, raiz):
                    falhas.append(f"{orig.name}: destino fora da pasta")
                    continue
            else:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(orig), str(dest))
            movidos.append({"tipo": op["tipo"], "origem": str(orig), "destino": str(dest), "motivo": op.get("motivo", "")})
        except OSError as e:
            falhas.append(f"{Path(op.get('origem', '?')).name}: {e.strerror or e}")
    if movidos:
        base_q.mkdir(parents=True, exist_ok=True)
        with open(base_q / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"raiz": str(raiz), "criado_em": plano.get("criado_em", ""), "movidos": movidos, "desfeito": False}, f,
                      ensure_ascii=False, indent=1)
    return {"carimbo": carimbo if movidos else "", "movidos": len(movidos),
            "quarentena": sum(1 for m in movidos if m["tipo"] == "quarentena"),
            "arrumados": sum(1 for m in movidos if m["tipo"] == "mover"), "falhas": falhas}


def listar_quarentenas(pasta_quarentena) -> list:
    base = Path(pasta_quarentena)
    saida = []
    if not base.is_dir():
        return saida
    for d in sorted((p for p in base.iterdir() if p.is_dir()), reverse=True):
        mf = d / "manifest.json"
        if not mf.is_file():
            continue
        try:
            dados = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        q = [m for m in dados.get("movidos", []) if m["tipo"] == "quarentena"]
        saida.append({"carimbo": d.name, "raiz": dados.get("raiz", ""), "quarentena": len(q),
                      "arrumados": len(dados.get("movidos", [])) - len(q), "desfeito": bool(dados.get("desfeito")),
                      "bytes": sum(Path(m["destino"]).stat().st_size for m in q if Path(m["destino"]).exists())})
    return saida


def formatar_quarentenas(pasta_quarentena) -> str:
    itens = listar_quarentenas(pasta_quarentena)
    if not itens:
        return "🗂️ A quarentena está vazia — nenhuma limpeza foi feita ainda."
    linhas = ["🗂️ Limpezas feitas (a mais recente primeiro):"]
    for it in itens[:10]:
        estado = "↩ desfeita" if it["desfeito"] else f"{it['quarentena']} na quarentena ({tamanho_legivel(it['bytes'])}), {it['arrumados']} arrumados"
        linhas.append(f"• {it['carimbo']} — {it['raiz']} — {estado}")
    linhas.append("Comandos: /quarentena desfazer [carimbo] · /quarentena esvaziar confirmar (APAGA DE VERDADE o que está na quarentena)")
    return "\n".join(linhas)


def desfazer(pasta_quarentena, carimbo: str = "") -> dict:
    """Devolve cada arquivo pro lugar de onde veio (se o lugar estiver livre). Sem carimbo = a limpeza mais recente."""
    itens = [i for i in listar_quarentenas(pasta_quarentena) if not i["desfeito"]]
    if carimbo:
        itens = [i for i in itens if i["carimbo"] == carimbo]
    if not itens:
        raise ErroOrganizar("🗂️ Não tem nenhuma limpeza pra desfazer" + (f" com o carimbo {carimbo}." if carimbo else "."))
    alvo = itens[0]["carimbo"]
    mf = Path(pasta_quarentena) / alvo / "manifest.json"
    dados = json.loads(mf.read_text(encoding="utf-8"))
    voltaram, falhas = 0, []
    for m in reversed(dados.get("movidos", [])):
        orig, dest = Path(m["origem"]), Path(m["destino"])
        try:
            if not dest.exists():
                falhas.append(f"{dest.name}: não está mais lá")
                continue
            if orig.exists():
                falhas.append(f"{orig.name}: já existe um arquivo no lugar original (deixei onde está)")
                continue
            orig.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(orig))
            voltaram += 1
            if m["tipo"] == "mover":                   # tira a subpasta de tipo se ficou vazia
                try:
                    dest.parent.rmdir()
                except OSError:
                    pass
        except OSError as e:
            falhas.append(f"{dest.name}: {e.strerror or e}")
    dados["desfeito"] = True
    mf.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"carimbo": alvo, "voltaram": voltaram, "falhas": falhas}


def esvaziar(pasta_quarentena) -> dict:
    """APAGA DE VERDADE tudo que está na quarentena (só chamado por comando explícito com 'confirmar')."""
    base = Path(pasta_quarentena)
    n, tam = 0, 0
    if base.is_dir():
        for d in [p for p in base.iterdir() if p.is_dir() and (p / "manifest.json").is_file()]:
            for raiz_, _, nomes in os.walk(d):
                for nome in nomes:
                    try:
                        tam += os.path.getsize(os.path.join(raiz_, nome))
                        n += 1
                    except OSError:
                        pass
            shutil.rmtree(d, ignore_errors=True)
    return {"apagados": n, "bytes": tam}


# ----------------------------------------------------------------------------------------------- etiqueta da IA
def interpretar(conteudo: str) -> dict:
    """`<organizar_pasta>C:\\Users\\x\\Downloads</organizar_pasta>` ou JSON {"pasta","modo","agressivo"}."""
    t = (conteudo or "").strip()
    if t.startswith("{"):
        try:
            d = json.loads(t)
            return {"pasta": str(d.get("pasta", "")).strip(), "modo": str(d.get("modo", "tudo")), "agressivo": bool(d.get("agressivo", False))}
        except json.JSONDecodeError:
            pass
    return {"pasta": t.strip().strip('"').strip("'"), "modo": "tudo", "agressivo": False}
