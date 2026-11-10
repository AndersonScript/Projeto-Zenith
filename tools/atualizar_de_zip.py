"""Zenith — ATUALIZAR a partir de um .zip novo, sem Freebuff e sem perder seus dados (v1.7).

Uso:  python ATUALIZAR_ZENITH.py caminho\\Zenith_v1_6_2.zip      (ou arraste o .zip em cima do ATUALIZAR_ZENITH.py)

O que faz: abre o zip numa pasta temporária (com proteção contra caminhos perigosos), compara com a sua pasta, faz um BACKUP em
`backups/` dos arquivos que vai trocar, copia só o que mudou e conta o que fez. Se algum arquivo estiver em uso (Zenith aberto),
desfaz tudo e pede para fechar.
NUNCA mexe em: memória (memory_db), criações, temporários, modelos, .venv, backups, exportações, .godot, logs.
Em `config/` (suas chaves e preferências) e `edition.json`: só cria o que não existe — nunca sobrescreve.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PRESERVAR = ("memory_db", "creations", "temp", "models", ".venv", "backups", "dist", "build", "dist_publico", "dist_instalador",
             ".git", "body/zenith/.godot", "body/zenith/export", "__pycache__")
SO_SE_NAO_EXISTE = ("config", "edition.json", "zenith_log.txt")
SEMPRE_ATUALIZA = ("config/provedores_catalogo.json",)      # catálogo de IAs: vem do programa (nomes, endereços, atalhos), não do usuário
MAX_ARQUIVOS = 20000
MAX_BYTES = 3 * 1024 ** 3


def _partes(rel: str) -> tuple:
    return tuple(p for p in rel.replace("\\", "/").split("/") if p)


def _comeca_com(rel: str, prefixo: str) -> bool:
    a, b = _partes(rel), _partes(prefixo)
    return a[:len(b)] == b


def eh_preservado(rel: str) -> bool:
    return any(_comeca_com(rel, p) for p in PRESERVAR) or "__pycache__" in _partes(rel) or rel.endswith(".pyc")


def eh_so_se_nao_existe(rel: str) -> bool:
    if any(_comeca_com(rel, p) for p in SEMPRE_ATUALIZA):
        return False
    return any(_comeca_com(rel, p) for p in SO_SE_NAO_EXISTE)


def extrair_seguro(zip_path: Path, destino: Path) -> int:
    """Abre o zip recusando caminho que escapa da pasta (zip slip), atalhos e tamanho absurdo. Devolve quantos arquivos."""
    destino = destino.resolve()
    total = 0
    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        if len(infos) > MAX_ARQUIVOS or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError("O zip é grande demais para ser uma atualização do Zenith.")
        for i in infos:
            nome = i.filename.replace("\\", "/")
            alvo = (destino / nome).resolve()
            if nome.startswith("/") or ".." in _partes(nome) or not str(alvo).startswith(str(destino)):
                raise ValueError(f"Caminho perigoso dentro do zip: {i.filename!r}. Não vou abrir este arquivo.")
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Atalho (symlink) dentro do zip: {i.filename!r}. Não vou abrir este arquivo.")
            if i.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as f, open(alvo, "wb") as out:
                shutil.copyfileobj(f, out)
            total += 1
    return total


def achar_raiz(base: Path):
    """A pasta do Zenith dentro do que foi extraído (tem brain/, body/ e zenith_launcher.py), até 3 níveis."""
    base = Path(base)
    for nivel in range(4):
        for cand in [base] if nivel == 0 else [p for p in base.glob("/".join(["*"] * nivel)) if p.is_dir()]:
            if (cand / "brain").is_dir() and (cand / "body").is_dir() and (cand / "zenith_launcher.py").exists():
                return cand
    return None


def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def versao_de(raiz: Path) -> str:
    try:
        m = re.search(r'VERSAO\s*=\s*"([^"]+)"', (Path(raiz) / "brain" / "zenith_version.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def montar_plano(origem: Path, destino: Path) -> dict:
    """{'novos': [...], 'trocar': [...], 'iguais': n, 'protegidos': [...]}  (caminhos relativos com /)."""
    origem, destino = Path(origem), Path(destino)
    plano = {"novos": [], "trocar": [], "iguais": 0, "protegidos": []}
    for p in sorted(origem.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(origem).as_posix()
        if eh_preservado(rel):
            continue
        alvo = destino / rel
        if alvo.exists():
            if eh_so_se_nao_existe(rel):
                plano["protegidos"].append(rel)
            elif _hash(p) == _hash(alvo):
                plano["iguais"] += 1
            else:
                plano["trocar"].append(rel)
        else:
            plano["novos"].append(rel)
    return plano


def fazer_backup(plano: dict, destino: Path, pasta_backup: Path) -> Path:
    pasta_backup.mkdir(parents=True, exist_ok=True)
    arq = pasta_backup / time.strftime("antes_%Y%m%d_%H%M%S.zip")
    with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in plano["trocar"]:
            z.write(Path(destino) / rel, rel)
    return arq


def restaurar(backup: Path, destino: Path) -> int:
    n = 0
    with zipfile.ZipFile(backup) as z:
        for i in z.infolist():
            (Path(destino) / i.filename).write_bytes(z.read(i))
            n += 1
    return n


def aplicar(plano: dict, origem: Path, destino: Path, pasta_backup: Path) -> dict:
    """Copia. Se algo falhar no meio (arquivo em uso), desfaz o que já trocou e levanta PermissionError/OSError."""
    origem, destino = Path(origem), Path(destino)
    backup = fazer_backup(plano, destino, pasta_backup) if plano["trocar"] else None
    feitos_novos, feitos_trocados = [], []
    try:
        for rel in plano["trocar"] + plano["novos"]:
            alvo = destino / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            eh_novo = not alvo.exists()
            shutil.copy2(origem / rel, alvo)
            (feitos_novos if eh_novo else feitos_trocados).append(rel)
    except OSError:
        for rel in feitos_novos:
            try:
                (destino / rel).unlink()
            except OSError:
                pass
        if backup is not None:
            restaurar(backup, destino)
        raise
    return {"novos": len(feitos_novos), "trocados": len(feitos_trocados), "backup": str(backup) if backup else ""}


def main(argv=None, imprimir=print) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    so_conferir = "--so-conferir" in argv
    caminhos = [a for a in argv if not a.startswith("--")]
    if not caminhos:
        imprimir("Uso: python ATUALIZAR_ZENITH.py caminho\\Zenith_v1_X_Y.zip   (ou arraste o .zip em cima do ATUALIZAR_ZENITH.py)")
        return 2
    zip_path = Path(caminhos[0].strip('"'))
    if not zip_path.exists():
        imprimir(f"Não achei o arquivo: {zip_path}")
        return 2
    with tempfile.TemporaryDirectory(prefix="zenith_atualizar_") as tmp:
        try:
            extrair_seguro(zip_path, Path(tmp))
        except (ValueError, zipfile.BadZipFile) as e:
            imprimir(f"Não posso usar este zip: {e}")
            return 2
        raiz = achar_raiz(Path(tmp))
        if raiz is None:
            imprimir("Este zip não parece ser do Zenith (não achei brain/, body/ e zenith_launcher.py).")
            return 2
        plano = montar_plano(raiz, RAIZ)
        imprimir(f"Versão atual: {versao_de(RAIZ)}  ->  nova: {versao_de(raiz)}")
        imprimir(f"{len(plano['trocar'])} arquivos mudam, {len(plano['novos'])} são novos, {plano['iguais']} já estão iguais. "
                 f"Seus dados ficam intactos ({len(plano['protegidos'])} arquivos de configuração protegidos).")
        if so_conferir:
            imprimir("(só conferi: nada foi alterado)")
            return 0
        try:
            r = aplicar(plano, raiz, RAIZ, RAIZ / "backups")
        except OSError as e:
            imprimir(f"\nUm arquivo está em uso ({e}). Feche o Zenith e o Godot e rode de novo. Nada foi alterado (desfiz o que já tinha trocado).")
            return 1
    imprimir(f"\nAtualizado: {r['trocados']} trocados, {r['novos']} novos." + (f"\nBackup do que foi trocado: {r['backup']}" if r["backup"] else ""))
    imprimir("Agora abra o Zenith com:  python INICIAR_ZENITH.py")
    return 0


if __name__ == "__main__":
    codigo = main()
    if codigo != 0 and sys.stdin is not None and sys.stdin.isatty():
        input("\nPressione Enter para fechar...")
    sys.exit(codigo)
