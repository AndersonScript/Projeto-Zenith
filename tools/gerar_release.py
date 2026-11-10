"""Gera uma versão do Zenith para o Launcher: o .zip do app, o SHA-256 e o site/latest.json.

Uso (no seu PC, depois de rodar `python tools/preparar_publico.py` e exportar o Corpo no Godot):
    python tools/gerar_release.py --versao 1.6.1 --pacote dist_publico/Zenith_Publico_v1.6.1 \\
        --base-url https://github.com/SEU_USUARIO/zenith/releases/download/v1.6.1 \\
        [--launcher-exe dist_launcher/ZenithLauncher.exe] [--notas "o que mudou"]

Faz: confere que a pasta é publicável (sem chave, config pessoal nem avatar), confere que o número da versão bate com
brain/zenith_version.py, cria release/Zenith_app_<versao>.zip (sempre o mesmo zip para o mesmo conteúdo), calcula o SHA-256,
descobre o SHA-256 do instalador do Python (baixa uma vez, do python.org) e escreve site/latest.json e site/versions.json.
Você sobe o .zip (e o .exe) na Release do GitHub e dá push no site: o Launcher de todo mundo passa a oferecer a atualização.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYTHON_PADRAO = "3.12.10"
EXCLUIR_DIRS = {"__pycache__", ".git", ".github", ".idea", ".vscode", "dist", "dist_publico", "dist_launcher", "dist_instalador",
                "release", "_zenith_testes_tmp", ".godot"}
PROIBIDOS = ("config/settings.json", "config/chaves.txt", "config/ZENITH.md", ".env")

# v1.9 — "isto pode ir para o público?" é UMA regra só, em preparar_publico (chaves falsas de teste,
# termos pessoais, nome antigo, avatar). Antes o gerar_release tinha a sua própria cópia, mais burra:
# ela recusava publicar por causa da chave FALSA dos testes ("AIzaSyD-abcdefghij...").
try:
    from tools import preparar_publico as _PP
except ImportError:                                    # rodando como script (python tools/gerar_release.py)
    import preparar_publico as _PP
DATA_FIXA = (2026, 1, 1, 0, 0, 0)


class ErroRelease(Exception):
    pass


def _arquivos(pasta: Path):
    for p in sorted(pasta.rglob("*")):
        rel = p.relative_to(pasta)
        if any(parte in EXCLUIR_DIRS for parte in rel.parts) or p.suffix == ".pyc":
            continue
        if p.is_file():
            yield p, rel


def conferir_pasta(pasta: Path, versao: str, exigir_corpo: bool = True) -> list:
    """Levanta ErroRelease se a pasta não pode ser publicada. Devolve avisos (não bloqueiam)."""
    avisos = []
    if not (pasta / "zenith_launcher.py").exists() or not (pasta / "requirements.txt").exists():
        raise ErroRelease("A pasta não parece o Zenith (faltam zenith_launcher.py e requirements.txt).")
    for p, rel in _arquivos(pasta):
        r = rel.as_posix()
        if r in PROIBIDOS or r.lower().endswith(".vrm"):
            raise ErroRelease(f"Não pode ir para o público: {r} (dado pessoal ou avatar sem licença confirmada).")
    # Chave de verdade = recusa. Chave de mentira só é aceita onde ela mora de propósito: nos testes
    # (e nos arquivos que DEFINEM os padrões). A regra de "o que parece chave" é a do preparar_publico,
    # para não existirem duas listas divergentes.
    for p, rel in _arquivos(pasta):
        if p.suffix.lower() not in _PP.TEXTO or rel.name in _PP.SO_DEFINEM_PADROES:
            continue
        e_teste = bool(rel.parts) and rel.parts[0] == "tests"
        try:
            texto = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for nome, rx in _PP.PADROES_CHAVE:
            for m in rx.finditer(texto):
                if e_teste and _PP._parece_falsa(m.group(0)):
                    continue
                raise ErroRelease(f"Achei algo que parece uma {nome} em {rel.as_posix()}. Tire antes de publicar.")
    try:
        txt = (pasta / "brain" / "zenith_version.py").read_text(encoding="utf-8")
        m = re.search(r'^VERSAO\s*=\s*"v?([\d.]+)"', txt, re.M)
        if not m or m.group(1) != versao.lstrip("v"):
            raise ErroRelease(f"--versao {versao} não bate com brain/zenith_version.py ({m.group(1) if m else 'não achei'}). "
                              "Suba o número lá (e em tests/test_v1.py) antes de gerar.")
    except FileNotFoundError:
        raise ErroRelease("Falta brain/zenith_version.py na pasta.")
    export = pasta / "body" / "zenith" / "export"
    if not (export.exists() and list(export.glob("*.exe"))):
        msg = "Não há o Corpo exportado (body/zenith/export/*.exe). Sem ele o Zenith abre sem avatar."
        if exigir_corpo:
            raise ErroRelease(msg + " Exporte no Godot ou use --sem-corpo para um teste.")
        avisos.append(msg)
    return avisos


def montar_zip(pasta: Path, destino: Path, raiz_no_zip: str = "Zenith") -> dict:
    """Zip determinístico (ordem e datas fixas): o mesmo conteúdo gera sempre o mesmo SHA-256."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p, rel in _arquivos(pasta):
            info = zipfile.ZipInfo(f"{raiz_no_zip}/{rel.as_posix()}", DATA_FIXA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 << 16)
            z.writestr(info, p.read_bytes())
    dados = destino.read_bytes()
    return {"sha256": hashlib.sha256(dados).hexdigest(), "tamanho": len(dados)}


def sha256_de_url(url: str) -> tuple:
    h, n = hashlib.sha256(), 0
    with urllib.request.urlopen(url, timeout=60) as r:           # noqa: S310 (https do python.org; você roda isto)
        while True:
            b = r.read(1024 * 1024)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def montar_manifesto(versao, notas, base_url, zip_info, nome_zip, python_versao, python_url, python_sha, python_tam,
                     launcher=None) -> dict:
    m = {
        "versao": versao.lstrip("v"),
        "data": time.strftime("%Y-%m-%d"),
        "notas": notas,
        "pacote": {"arquivo": nome_zip, "url": f"{base_url.rstrip('/')}/{nome_zip}",
                   "sha256": zip_info["sha256"], "tamanho": zip_info["tamanho"]},
        "python": {"versao": python_versao, "url": python_url, "sha256": python_sha, "tamanho": python_tam},
        # compatibilidade com o /atualizar de dentro do Zenith (lê estas chaves no topo)
        "url": f"{base_url.rstrip('/')}/{nome_zip}", "sha256": zip_info["sha256"], "tamanho": zip_info["tamanho"],
    }
    if launcher:
        m["launcher"] = launcher
    return m


def atualizar_versions_json(arq: Path, manifesto: dict, notas_lista: list, repo_url: str = ""):
    try:
        antigo = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        antigo = {}
    versoes = [v for v in antigo.get("versoes", []) if v.get("versao") != manifesto["versao"]]
    item = {"versao": manifesto["versao"], "data": manifesto["data"], "estado": "estável", "notas": notas_lista,
            "pacote": {"tamanho": manifesto["pacote"]["tamanho"], "sha256": manifesto["pacote"]["sha256"]}}
    if manifesto.get("launcher"):
        item["launcher"] = {"url": manifesto["launcher"]["url"], "sha256": manifesto["launcher"]["sha256"],
                            "tamanho": manifesto["launcher"]["tamanho"]}
    versoes.insert(0, item)
    novo = {"atualizado": manifesto["data"], "repositorio": repo_url or antigo.get("repositorio", ""), "versoes": versoes}
    arq.write_text(json.dumps(novo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--versao", required=True)
    p.add_argument("--pacote", required=True, help="pasta pronta (saída do preparar_publico + Corpo exportado)")
    p.add_argument("--base-url", required=True, help="onde o .zip vai ficar (ex.: .../releases/download/v1.6.1)")
    p.add_argument("--notas", default="", help="texto curto do que mudou (uma linha por ponto, separado por ';')")
    p.add_argument("--python-versao", default=PYTHON_PADRAO)
    p.add_argument("--python-url", default="")
    p.add_argument("--python-sha256", default="", help="se já souber; senão baixo do python.org para calcular")
    p.add_argument("--launcher-exe", default="", help="ZenithLauncher.exe já gerado (entra no manifesto)")
    p.add_argument("--launcher-versao", default="1.0.0")
    p.add_argument("--sem-corpo", action="store_true", help="aceita pacote sem o Corpo exportado (só para teste)")
    p.add_argument("--site", default=str(RAIZ / "site"))
    p.add_argument("--saida", default=str(RAIZ / "release"))
    p.add_argument("--repo-url", default="")
    a = p.parse_args(argv)
    pasta = Path(a.pacote)
    try:
        avisos = conferir_pasta(pasta, a.versao, exigir_corpo=not a.sem_corpo)
    except ErroRelease as e:
        print("RECUSADO:", e)
        return 1
    for av in avisos:
        print("AVISO:", av)
    nome_zip = f"Zenith_app_{a.versao.lstrip('v')}.zip"
    info = montar_zip(pasta, Path(a.saida) / nome_zip)
    print(f"{nome_zip}: {info['tamanho'] / 1e6:.1f} MB  SHA-256 {info['sha256']}")
    py_url = a.python_url or f"https://www.python.org/ftp/python/{a.python_versao}/python-{a.python_versao}-amd64.exe"
    if a.python_sha256:
        py_sha, py_tam = a.python_sha256.lower(), 0
    else:
        print("Baixando o instalador do Python só para calcular o SHA-256 (uma vez)...")
        py_sha, py_tam = sha256_de_url(py_url)
    launcher = None
    if a.launcher_exe:
        exe = Path(a.launcher_exe)
        dados = exe.read_bytes()
        launcher = {"versao": a.launcher_versao, "arquivo": exe.name,
                    "url": f"{a.base_url.rstrip('/')}/{exe.name}", "sha256": hashlib.sha256(dados).hexdigest(), "tamanho": len(dados)}
    notas_lista = [n.strip() for n in a.notas.split(";") if n.strip()]
    man = montar_manifesto(a.versao, "\n".join(notas_lista), a.base_url, info, nome_zip, a.python_versao, py_url, py_sha, py_tam, launcher)
    site = Path(a.site)
    site.mkdir(parents=True, exist_ok=True)
    (site / "latest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    atualizar_versions_json(site / "versions.json", man, notas_lista, a.repo_url)
    print(f"\nEscrevi {site / 'latest.json'} e {site / 'versions.json'}.\nAgora: 1) suba {Path(a.saida) / nome_zip}"
          f"{' e o ZenithLauncher.exe' if launcher else ''} na Release do GitHub (tag da --base-url);\n"
          "2) faça commit/push da pasta site (o Vercel publica sozinho).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
