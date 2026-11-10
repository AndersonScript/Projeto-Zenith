#!/usr/bin/env python3
"""Zenith — monta a PASTA DA EDIÇÃO PÚBLICA (a que vai para o GitHub) e confere se ela está limpa.

    python tools/preparar_publico.py                 # cria dist_publico/Zenith_Publico_v1.4/
    python tools/preparar_publico.py --zip           # e também o .zip dela
    python tools/preparar_publico.py --so-conferir   # não copia nada: varre a pasta atual COMO se fosse a Pública

O que ela FAZ
  1. copia o projeto SEM o que é pessoal ou pesado: chaves, conversas, memória, modelos baixados, criações,
     builds, cache, histórico de conversas com IAs (docs/historico) e os avatares .vrm (licença não confirmada);
  2. grava `edition.json` = "publico" (a edição não é um botão: o que é do dono nem vai na pasta);
  3. VARRE o resultado e FALHA (código de saída 1) se achar: padrão de chave de API, caminho pessoal do Windows,
     termos pessoais do dono, arquivo proibido (settings.json, .vrm...), ou o nome antigo da IA em texto visível;
  4. escreve SHA256SUMS.txt, LICENSES/ e um rascunho das notas da versão.

Ela NÃO publica nada e NÃO apaga nada da pasta original. Só lê o projeto e escreve em `dist_publico/`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# ---------- o que NÃO vai para a edição Pública ----------
EXCLUIR_PASTAS = {  # nomes de pasta em qualquer nível
    ".git", "__pycache__", ".venv", "venv", "env", "dist", "build", "temp", "creations", "memory_db", "models",
    "libs", "staging", "_resgate", ".godot", ".idea", ".vscode", "dist_publico", "node_modules", ".pytest_cache",
    # v1.9 — saídas de build: nunca são públicas e carregam HTML com o caminho de quem compilou
    # (o PyInstaller gera `xref-*.html` com `C:\Users\<nome>`), o que fazia a varredura acusar
    # "termo pessoal" logo depois de gerar o Launcher.
    "dist_launcher", "dist_instalador", "release",
    # v1.8 — o build guarda os dados do usuário antes de sobrescrever a pasta (build_exe.py,
    # `_RESGATE`). Não é o `_resgate` de antes: é `_dados_do_usuario_resgatados`, com settings e
    # conversas DO DONO. Sem esta linha ele ia dentro da edição Pública e a varredura acusava
    # o nome antigo do modelo de exemplo — o "--so-conferir" nunca dava OK depois de um build.
    "_dados_do_usuario_resgatados",
}
EXCLUIR_CAMINHOS = (  # prefixos relativos (com /)
    "docs/historico", "docs/interno", "body/zenith/export",
)
EXCLUIR_ARQUIVOS = {  # nome exato
    "settings.json", "conversations.json", "chaves.txt", "zenith_log.txt", "HASHES_SHA256.txt", "VERSAO_BUILD.txt",
    ".admin_ok", ".admin_dispensado", ".segredos_mascarados", "build.lock", ".DS_Store", "Thumbs.db", "creditos.txt",
}
EXCLUIR_SUFIXOS = (".pyc", ".pyo", ".log", ".vrm", ".vrm.import", ".exe", ".pck", ".zip", ".whl", ".gguf", ".bin")

# ---------- o que a VARREDURA procura ----------
PADROES_CHAVE = [
    ("chave Google/Gemini", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("chave sk-", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("chave Groq", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("chave Tavily", re.compile(r"\btvly-[A-Za-z0-9]{10,}")),
    ("chave Hugging Face", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("Bearer", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{24,}")),
]
_FALSAS = ("abcdefghij", "ABCDEFGHIJ", "0123456789", "DONTLEAK", "xxxxxxxx", "XXXXXXXX", "EXEMPLO", "exemplo")
CAMINHO_PESSOAL = re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}(?!<|usuario|usuário|voce|você|fulano|maria|joao|nome|SEU|Seu|Public|Default|%|\{|[xyz]\\|\w\b)\w+")
TERMOS_PESSOAIS = re.compile(r"Itaquera|Itaquaera|Caderno Aberto|\bander\b", re.I)
NOME_ANTIGO = re.compile(r"Akira")
# Nomes INTERNOS do Godot que ainda usam o nome antigo (o usuário não vê; renomear só pelo editor do Godot)
INTERNO_GD = re.compile(r'get_node_or_null\("Akira"\)|\.name = "Akira|"AkiraNovo_temp"|Akira\.vrm|Akira_Body|renomeado "Akira"|se chama "Akira"|nó "Akira"')
ARQUIVOS_INTERNOS_ANTIGOS = ("Akira_Body.tscn", "Akira.vrm.import", "project.godot", "RENOMEAR_INTERNOS_GODOT.md")
SO_DEFINEM_PADROES = {"preparar_publico.py", "test_v1_4.py", "SHA256SUMS.txt"}   # arquivos que CONTÊM os padrões (não se auto-varrem)
TEXTO = {".py", ".gd", ".md", ".txt", ".json", ".cfg", ".yml", ".yaml", ".html", ".bat", ".ino", ".tscn", ".godot",
         ".iss", ".gdshader", ".toml", ".svg", ".import"}


def _excluir(rel: Path) -> bool:
    partes = rel.parts
    if any(p in EXCLUIR_PASTAS for p in partes[:-1]):
        return True
    if rel.name in EXCLUIR_ARQUIVOS:
        return True
    posix = rel.as_posix()
    if any(posix == c or posix.startswith(c + "/") for c in EXCLUIR_CAMINHOS):
        return True
    return posix.lower().endswith(EXCLUIR_SUFIXOS)


def _parece_falsa(achado: str) -> bool:
    return any(f in achado for f in _FALSAS)


def varrer(pasta: Path, respeitar_exclusoes: bool = False) -> dict:
    """Confere uma pasta. Devolve {'erros': [...], 'avisos': [...], 'arquivos': N}. Não altera nada.

    `respeitar_exclusoes=True` confere **o que iria para a edição Pública** (aplica a mesma lista de
    `_excluir`): é o modo do `--so-conferir` na pasta de ORIGEM. Sem isso, a varredura acusa justamente
    o que a cópia já deixa de fora — `docs/historico`, `docs/interno`, os `.vrm` e o `body/zenith/export` —
    e o guia mandava esperar "OK" num comando que nunca poderia dar OK.
    """
    erros, avisos = [], []
    n = 0
    internos = 0
    for p in sorted(pasta.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(pasta)
        if any(part in (".git", "__pycache__") for part in rel.parts):
            continue
        if respeitar_exclusoes and _excluir(rel):
            continue
        n += 1
        if rel.name in EXCLUIR_ARQUIVOS and rel.name not in ("VERSAO_BUILD.txt",):
            erros.append(f"{rel.as_posix()}: arquivo proibido na edição Pública ({rel.name})")
            continue
        if rel.as_posix().lower().endswith((".vrm", ".gguf")):
            erros.append(f"{rel.as_posix()}: avatar/modelo sem licença de redistribuição confirmada")
            continue
        if p.suffix.lower() not in TEXTO or rel.name in SO_DEFINEM_PADROES:
            continue
        try:
            texto = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        e_teste = rel.parts and rel.parts[0] == "tests"
        for numero, linha in enumerate(texto.split("\n"), 1):
            for nome, rx in PADROES_CHAVE:
                for m in rx.finditer(linha):
                    if not _parece_falsa(m.group(0)):
                        erros.append(f"{rel.as_posix()}:{numero}: parece uma {nome} de verdade")
            if CAMINHO_PESSOAL.search(linha):
                erros.append(f"{rel.as_posix()}:{numero}: caminho pessoal do Windows")
            if TERMOS_PESSOAIS.search(linha) and not (p.suffix == ".md" and rel.name in ("LICENSE", "README.md")):
                erros.append(f"{rel.as_posix()}:{numero}: termo pessoal do dono ({TERMOS_PESSOAIS.search(linha).group(0)})")
            if NOME_ANTIGO.search(linha) and "legado-ok" not in linha:      # a migração do nome salvo precisa citar o nome antigo
                if rel.name in ARQUIVOS_INTERNOS_ANTIGOS or (p.suffix == ".gd" and INTERNO_GD.search(linha)) \
                        or p.suffix == ".import":
                    internos += 1
                elif e_teste and INTERNO_GD.search(linha):
                    internos += 1
                else:
                    erros.append(f"{rel.as_posix()}:{numero}: nome antigo da IA em texto visível")
    if internos:
        avisos.append(f"{internos} referência(s) INTERNA(s) ao nome antigo (arquivo/nó do Godot) — invisíveis ao usuário; "
                      "renomear pelo editor do Godot (ver docs/RENOMEAR_INTERNOS_GODOT.md)")
    return {"erros": erros, "avisos": avisos, "arquivos": n}


def copiar(origem: Path, destino: Path) -> int:
    if destino.exists():
        shutil.rmtree(destino)
    n = 0
    for p in sorted(origem.rglob("*")):
        rel = p.relative_to(origem)
        if rel == Path(".") or _excluir(rel if p.is_file() else rel / "_"):
            continue
        alvo = destino / rel
        if p.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, alvo)
            n += 1
    return n


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def escrever_sums(pasta: Path) -> Path:
    linhas = []
    for p in sorted(pasta.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            linhas.append(f"{_sha256(p)}  {p.relative_to(pasta).as_posix()}")
    alvo = pasta / "SHA256SUMS.txt"
    alvo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return alvo


def montar(origem: Path = RAIZ, saida: Path | None = None, zipar: bool = False) -> dict:
    from brain import zenith_edicao, zenith_version
    versao = zenith_version.VERSAO
    saida = Path(saida) if saida else origem / "dist_publico" / f"Zenith_Publico_{versao}"
    n = copiar(origem, saida)
    zenith_edicao.gravar(saida, zenith_edicao.PUBLICO)
    # avatares: pasta fica, arquivos não; LEIA-ME explica
    av = saida / "body" / "zenith" / "addons" / "avatars"
    av.mkdir(parents=True, exist_ok=True)
    (av / "LEIA-ME.md").write_text(
        "# Avatares\n\nA edição Pública NÃO traz avatar: a licença de cada modelo .vrm precisa ser conferida antes "
        "de redistribuir.\nColoque aqui o SEU modelo `.vrm` (use um que você criou ou que permita redistribuição) e abra o "
        "projeto no Godot uma vez para ele ser importado.\n", encoding="utf-8")
    lic = saida / "LICENSES"
    lic.mkdir(exist_ok=True)
    if (origem / "assets" / "LICENCAS.md").is_file():
        shutil.copy2(origem / "assets" / "LICENCAS.md", lic / "TERCEIROS.md")
    for extra in (origem / "body" / "zenith" / "addons" / "vrm" / "LICENSE",):
        if extra.is_file():
            shutil.copy2(extra, lic / "addon_vrm_LICENSE.txt")
    (saida / "NOTAS_DA_VERSAO.md").write_text(
        f"# Zenith {versao} — edição Pública\n\n(rascunho — edite antes de publicar)\n\n"
        "- Assistente pessoal com avatar: conversa, programa, cria imagens e vídeos, tudo com a SUA aprovação.\n"
        "- Nada sai do seu computador sem você saber. Nenhuma telemetria.\n"
        "- Suas chaves de IA ficam só no seu computador.\n\n"
        "Confira o SHA-256 do instalador antes de abrir (SHA256SUMS.txt).\n", encoding="utf-8")
    resultado = varrer(saida)
    resultado.update({"pasta": str(saida), "copiados": n, "zip": ""})
    if not resultado["erros"]:
        escrever_sums(saida)
        if zipar:
            alvo = saida.parent / (saida.name + ".zip")
            with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(saida.rglob("*")):
                    if p.is_file():
                        z.write(p, Path(saida.name) / p.relative_to(saida))
            resultado["zip"] = str(alvo)
    return resultado


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Monta e confere a pasta da edição Pública do Zenith.")
    ap.add_argument("--origem", default=str(RAIZ))
    ap.add_argument("--saida", default="")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--so-conferir", action="store_true", help="só varre a pasta --origem, sem copiar")
    a = ap.parse_args(argv)
    if a.so_conferir:
        r = varrer(Path(a.origem), respeitar_exclusoes=True)
    else:
        r = montar(Path(a.origem), Path(a.saida) if a.saida else None, a.zip)
    for aviso in r["avisos"]:
        print("AVISO:", aviso)
    for erro in r["erros"][:60]:
        print("ERRO :", erro)
    if len(r["erros"]) > 60:
        print(f"... e mais {len(r['erros']) - 60} erro(s)")
    if r["erros"]:
        print(f"\nFALHOU: {len(r['erros'])} problema(s). Nada foi publicado. Corrija e rode de novo.")
        return 1
    print(f"\nOK: {r['arquivos']} arquivos conferidos." + (f" Pasta: {r['pasta']}" if "pasta" in r else ""))
    if r.get("zip"):
        print("Zip:", r["zip"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
