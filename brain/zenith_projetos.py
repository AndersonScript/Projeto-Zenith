"""Zenith — BIBLIOTECA / PROJETOS (v1.6): tudo o que ela criou, separado por assunto, visível no painel "Biblioteca".

Pedido do Anderson: "projetos Zenith, separando em tópicos: imagens, vídeos, programas, separando em linguagens ou projetos
completos, aparente no chat".

O que este módulo faz: LÊ a pasta de criações (creations/) e monta um índice:
    Programas    -> agrupados por LINGUAGEM principal (Python, JavaScript, Web, C++...), cada um mostra quantos arquivos tem
    Projetos completos -> (v1.6.1) os programas com 2 ou mais arquivos (jogo, site, app), à parte dos scripts de um arquivo só
    Sites        -> páginas feitas pela Zenith (creations/web)
    Imagens      -> as imagens criadas/baixadas, da mais nova para a mais antiga
    Vídeos       -> idem
    Documentos   -> Word, PDF, planilhas, apresentações, textos

Ele só LÊ. Não apaga, não move, não roda nada. As duas ações do painel são seguras e passam por aqui:
  * "Abrir pasta"  -> mostra o item no Explorador de Arquivos (não executa nada);
  * "Ver no chat"  -> manda a imagem para o chat.
Os dois só aceitam caminhos DENTRO da pasta de criações (ver `dentro_das_criacoes`): o painel não consegue abrir outra coisa.
Para RODAR um programa criado, a pessoa pede no chat e a aprovação de sempre vale (Pilar 1).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

CATEGORIAS = (
    ("programas", "Programas"),
    ("sites", "Sites e páginas"),
    ("imagens", "Imagens"),
    ("videos", "Vídeos"),
    ("documentos", "Documentos"),
)
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
EXT_DOC = {".docx", ".pdf", ".xlsx", ".pptx", ".md", ".txt", ".csv", ".odt"}
LINGUAGEM = {
    ".py": "Python", ".pyw": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript",
    ".html": "Web", ".htm": "Web", ".css": "Web", ".c": "C", ".h": "C/C++", ".cpp": "C++", ".cc": "C++", ".hpp": "C/C++",
    ".java": "Java", ".kt": "Kotlin", ".rs": "Rust", ".go": "Go", ".cs": "C#", ".ino": "Arduino", ".lua": "Lua",
    ".sh": "Shell", ".bat": "Batch", ".ps1": "PowerShell", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift", ".sql": "SQL",
    ".gd": "GDScript", ".m": "MATLAB/Octave", ".r": "R", ".jl": "Julia",
    # v1.7 (T5) — as linguagens que agora também sabe compilar/rodar
    ".cjs": "JavaScript", ".mjs": "JavaScript", ".jsx": "JavaScript", ".tsx": "TypeScript",
    ".dart": "Dart", ".zig": "Zig", ".nim": "Nim", ".pl": "Perl", ".asm": "Assembly",
    ".v": "Verilog", ".vhd": "VHDL",
}
IGNORAR_PASTAS = {"_backup", "__pycache__", ".git", "node_modules", ".venv", "venv", "quarentena", "exports"}
IGNORAR_ARQUIVOS = {"_zenith_log.txt", "thumbs.db", ".ds_store"}
MAX_POR_GRUPO, MAX_TOTAL, MAX_RESUMO = 60, 400, 6
MIN_ARQUIVOS_PROJETO = 2      # v1.6.1: a partir de quantos arquivos um programa conta como "projeto completo"


def raiz_padrao() -> Path:
    from brain.zenith_settings import CREATION_DIR
    return Path(CREATION_DIR)


def dentro_das_criacoes(caminho, raiz=None) -> bool:
    """True só se `caminho` está DENTRO da pasta de criações (impede o painel de abrir qualquer outra coisa)."""
    try:
        base = Path(raiz or raiz_padrao()).resolve()
        alvo = Path(str(caminho)).resolve()
        return alvo == base or base in alvo.parents
    except (OSError, ValueError, RuntimeError):
        return False


def _arquivos(pasta: Path):
    """Arquivos de uma pasta de projeto (recursivo), sem backups/caches/log."""
    out = []
    for raiz, dirs, files in os.walk(pasta):
        dirs[:] = [d for d in dirs if d not in IGNORAR_PASTAS and not d.startswith(".")]
        for f in files:
            if f.lower() in IGNORAR_ARQUIVOS:
                continue
            out.append(Path(raiz) / f)
        if len(out) > 2000:
            break
    return out


def _info(p: Path) -> dict:
    try:
        st = p.stat()
        return {"tamanho": int(st.st_size), "modificado": float(st.st_mtime)}
    except OSError:
        return {"tamanho": 0, "modificado": 0.0}


def _projeto(pasta: Path) -> dict:
    arqs = _arquivos(pasta)
    contagem = {}
    for a in arqs:
        lang = LINGUAGEM.get(a.suffix.lower())
        if lang:
            contagem[lang] = contagem.get(lang, 0) + 1
    # "Web" (html+css+js) é uma linguagem só para o painel: se há html, ele manda
    if "Web" in contagem and "JavaScript" in contagem and contagem["Web"] >= 1:
        contagem["Web"] += contagem.pop("JavaScript")
    ordem = sorted(contagem, key=lambda k: (-contagem[k], k))
    mtime = max([_info(a)["modificado"] for a in arqs] or [_info(pasta)["modificado"]])
    return {"nome": pasta.name, "tipo": "projeto", "caminho": str(pasta), "arquivos": len(arqs),
            "linguagens": ordem, "principal": ordem[0] if ordem else "Sem código",
            "tamanho": sum(_info(a)["tamanho"] for a in arqs), "modificado": mtime,
            "resumo": [a.name for a in sorted(arqs, key=lambda x: x.name.lower())[:MAX_RESUMO]]}


def _achar_midia(raiz: Path, extensoes: set, pular=("programas", "web", "quarentena", "exports", "_backup")) -> list:
    itens = []
    if not raiz.is_dir():
        return itens
    for r, dirs, files in os.walk(raiz):
        rel = Path(r).relative_to(raiz).parts
        dirs[:] = [d for d in dirs if d not in IGNORAR_PASTAS and not d.startswith(".")]
        if rel and rel[0] in pular:
            dirs[:] = []
            continue
        for f in files:
            p = Path(r) / f
            if p.suffix.lower() in extensoes and f.lower() not in IGNORAR_ARQUIVOS:
                info = _info(p)
                itens.append({"nome": f, "tipo": "arquivo", "caminho": str(p), "pasta": str(Path(r)), **info,
                              "extensao": p.suffix.lower().lstrip(".")})
    return sorted(itens, key=lambda i: -i["modificado"])


def indexar(raiz=None) -> dict:
    """Monta o índice completo. Nunca levanta erro por causa de pasta ausente ou arquivo ilegível."""
    raiz = Path(raiz or raiz_padrao())
    cats = []

    # Programas: uma pasta por programa, agrupados por linguagem
    progs = []
    pasta_prog = raiz / "programas"
    if pasta_prog.is_dir():
        for d in sorted(pasta_prog.iterdir()):
            if d.is_dir() and d.name not in IGNORAR_PASTAS and not d.name.startswith("."):
                try:
                    progs.append(_projeto(d))
                except OSError:
                    continue
    grupos = {}
    for p in sorted(progs, key=lambda x: -x["modificado"]):
        grupos.setdefault(p["principal"], []).append(p)
    cats.append({"id": "programas", "titulo": "Programas", "total": len(progs),
                 "grupos": [{"titulo": f"{lang} ({len(v)})", "itens": v[:MAX_POR_GRUPO]}
                            for lang, v in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0]))]})

    # Projetos completos (v1.6.1): os programas de vários arquivos, agrupados por linguagem — é o mesmo conjunto de pastas,
    # visto de outro jeito; por isso NÃO entra na soma de `total` (senão cada projeto contaria duas vezes).
    completos = {}
    for p in sorted(progs, key=lambda x: -x["modificado"]):
        if p["arquivos"] >= MIN_ARQUIVOS_PROJETO:
            completos.setdefault(p["principal"], []).append(p)
    n_completos = sum(len(v) for v in completos.values())
    cats.append({"id": "projetos", "titulo": "Projetos completos", "total": n_completos, "repetida": True,
                 "grupos": [{"titulo": f"{lang} ({len(v)})", "itens": v[:MAX_POR_GRUPO]}
                            for lang, v in sorted(completos.items(), key=lambda kv: (-len(kv[1]), kv[0]))]})

    # Sites: creations/web (páginas soltas ou pastas)
    sites = []
    pasta_web = raiz / "web"
    if pasta_web.is_dir():
        for d in sorted(pasta_web.iterdir()):
            try:
                if d.is_dir() and d.name not in IGNORAR_PASTAS:
                    sites.append(_projeto(d))
                elif d.suffix.lower() in (".html", ".htm"):
                    sites.append({"nome": d.name, "tipo": "arquivo", "caminho": str(d), "pasta": str(pasta_web), **_info(d), "extensao": "html"})
            except OSError:
                continue
    sites.sort(key=lambda x: -x["modificado"])
    cats.append({"id": "sites", "titulo": "Sites e páginas", "total": len(sites),
                 "grupos": [{"titulo": f"Todos ({len(sites)})", "itens": sites[:MAX_POR_GRUPO]}] if sites else []})

    # Imagens / vídeos / documentos
    for cid, titulo, exts in (("imagens", "Imagens", EXT_IMAGEM), ("videos", "Vídeos", EXT_VIDEO), ("documentos", "Documentos", EXT_DOC)):
        itens = _achar_midia(raiz, exts)
        por_mes = {}
        for i in itens:
            chave = time.strftime("%m/%Y", time.localtime(i["modificado"])) if i["modificado"] else "sem data"
            por_mes.setdefault(chave, []).append(i)
        cats.append({"id": cid, "titulo": titulo, "total": len(itens),
                     "grupos": [{"titulo": f"{mes} ({len(v)})", "itens": v[:MAX_POR_GRUPO]} for mes, v in por_mes.items()][:12]})

    total = sum(c["total"] for c in cats if not c.get("repetida"))
    for c in cats:
        c["grupo"] = "criacoes"        # v1.6.1: o painel separa "o que ela criou" de "o que ela usa como base"
    # teto de tamanho da mensagem
    restante = MAX_TOTAL
    for c in cats:
        for g in c["grupos"]:
            g["itens"] = g["itens"][:max(0, restante)]
            restante -= len(g["itens"])
        c["grupos"] = [g for g in c["grupos"] if g["itens"]]
    return {"pasta": str(raiz), "total": total, "categorias": cats}


def _tamanho(n: int) -> str:
    for un in ("B", "KB", "MB", "GB"):
        if n < 1024 or un == "GB":
            return f"{n:.0f} {un}" if un == "B" else f"{n:.1f} {un}"
        n /= 1024.0
    return f"{n} B"


def formatar_texto(indice: dict, maximo_por_grupo: int = 6) -> str:
    """Versão em texto, para o comando /projetos no chat."""
    if not indice.get("total"):
        return ("Ainda não há nada na Biblioteca. Peça para eu criar um programa, uma imagem, um vídeo ou um site, "
                f"e eles aparecem aqui.\nPasta: {indice.get('pasta', '')}")
    linhas = [f"Biblioteca Zenith — {indice['total']} item(ns)  ({indice['pasta']})"]
    for c in indice["categorias"]:
        if not c["total"] or c.get("repetida") or c.get("grupo") == "base":
            continue
        linhas.append(f"\n{c['titulo']} ({c['total']})")
        for g in c["grupos"]:
            linhas.append(f"  {g['titulo']}")
            for it in g["itens"][:maximo_por_grupo]:
                extra = (f"{it['arquivos']} arquivo(s)" if it.get("tipo") == "projeto" else _tamanho(it.get("tamanho", 0)))
                linhas.append(f"    - {it['nome']}  ({extra})")
            if len(g["itens"]) > maximo_por_grupo:
                linhas.append(f"    ... e mais {len(g['itens']) - maximo_por_grupo}")
    linhas.append("\nAbra o painel Biblioteca na barra lateral para abrir a pasta de cada item.")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------------------------------------------------
# ações do painel (as duas únicas): abrir a pasta no Explorador e mostrar a imagem no chat
# ---------------------------------------------------------------------------------------------------------------------
def abrir_no_explorador(caminho, raiz=None, abridor=None) -> tuple:
    """Mostra o item no Explorador de Arquivos. NÃO executa o arquivo. Devolve (ok, mensagem)."""
    if not dentro_das_criacoes(caminho, raiz):
        return False, "Esse caminho não está dentro da pasta de criações do Zenith."
    alvo = Path(str(caminho))
    if not alvo.exists():
        return False, "Esse item não existe mais (foi movido ou apagado)."
    try:
        if abridor is not None:
            abridor(str(alvo))
        elif sys.platform.startswith("win"):
            if alvo.is_dir():
                os.startfile(str(alvo))                                           # abre a pasta
            else:
                subprocess.Popen(["explorer", "/select,", str(alvo)])             # mostra o arquivo (não o executa)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(alvo)] if alvo.is_file() else ["open", str(alvo)])
        else:
            subprocess.Popen(["xdg-open", str(alvo if alvo.is_dir() else alvo.parent)])
        return True, f"Abri {alvo.name} no Explorador."
    except OSError as e:
        return False, f"Não consegui abrir: {e}"


def caminho_de_imagem(caminho, raiz=None):
    """Para 'Ver no chat': devolve o caminho se for uma imagem de dentro das criações; senão None."""
    if not dentro_das_criacoes(caminho, raiz):
        return None
    p = Path(str(caminho))
    return str(p) if p.is_file() and p.suffix.lower() in EXT_IMAGEM else None
