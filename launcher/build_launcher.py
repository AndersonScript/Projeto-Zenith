"""Gera o ZenithLauncher.exe (PyInstaller) já apontando para o SEU site.

Uso (Windows, na pasta do projeto):
    python launcher\\build_launcher.py --site https://seu-projeto.vercel.app --repo SEU_USUARIO/zenith

Saída: dist_launcher\\ZenithLauncher.exe (+ launcher.json e o SHA-256 para o latest.json).
O launcher.json fica DENTRO do .exe (e uma cópia ao lado, para você poder trocar sem recompilar).
Honesto: o PyInstaller só roda no Windows e eu não consegui testar este script; o que ele monta (launcher.json) é testado.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
HOSTS_FIXOS = ["github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
               "www.python.org", "python.org"]


def montar_config(site: str, hosts_extras=()) -> dict:
    u = urlparse(site.strip().rstrip("/"))
    if u.scheme != "https" or not u.hostname:
        raise SystemExit("O --site precisa ser um endereço https (ex.: https://zenith.vercel.app).")
    hosts = [u.hostname.lower()] + HOSTS_FIXOS + [h.strip().lower() for h in hosts_extras if h.strip()]
    vistos, ordem = set(), []
    for h in hosts:
        if h not in vistos:
            vistos.add(h)
            ordem.append(h)
    return {"manifesto": f"{u.scheme}://{u.netloc}/latest.json", "hosts": ordem, "permitir_local": False}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--site", required=True, help="endereço do seu site no Vercel")
    p.add_argument("--host-extra", action="append", default=[], help="outro endereço permitido para downloads")
    p.add_argument("--saida", default=str(RAIZ / "dist_launcher"))
    a = p.parse_args(argv)
    cfg = montar_config(a.site, a.host_extra)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    cfg_arq = saida / "launcher.json"
    cfg_arq.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    icone = RAIZ / "assets" / "zenith_icon.ico"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
           "--name", "ZenithLauncher", "--distpath", str(saida), "--workpath", str(saida / "_build"),
           "--specpath", str(saida / "_build"),
           # certifi vai DENTRO do .exe: sem ele, Windows com raízes de certificado antigas
           # quebra o download com CERTIFICATE_VERIFY_FAILED (caso real de 30/10/2026).
           "--collect-data", "certifi",
           "--add-data", f"{cfg_arq}{os.pathsep}.", str(RAIZ / "launcher" / "zenith_instalador.py")]
    if icone.exists():
        cmd[cmd.index("--name"):cmd.index("--name")] = ["--icon", str(icone)]
    print("Rodando:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(RAIZ))
    exe = saida / "ZenithLauncher.exe"
    if r.returncode != 0 or not exe.exists():
        print("O PyInstaller não terminou. Instale com: pip install pyinstaller")
        return 1
    h = hashlib.sha256(exe.read_bytes()).hexdigest()
    print(f"\nPronto: {exe}\nTamanho: {exe.stat().st_size}\nSHA-256: {h}\n"
          f"Suba o .exe na Release do GitHub (nome exato: ZenithLauncher.exe) e rode tools/gerar_release.py --launcher-exe.")

    # ---- LimparZenith.exe: janela para apagar por partes ou desinstalar tudo ----
    cmd_limpar = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
                  "--name", "LimparZenith", "--distpath", str(saida), "--workpath", str(saida / "_build2"),
                  "--specpath", str(saida / "_build2"), "--paths", str(RAIZ / "launcher"),
                  str(RAIZ / "launcher" / "limpar.py")]
    if icone.exists():
        cmd_limpar[cmd_limpar.index("--name"):cmd_limpar.index("--name")] = ["--icon", str(icone)]
    print("Rodando:", " ".join(cmd_limpar))
    r2 = subprocess.run(cmd_limpar, cwd=str(RAIZ))
    exe_limpar = saida / "LimparZenith.exe"
    if r2.returncode == 0 and exe_limpar.exists():
        h2 = hashlib.sha256(exe_limpar.read_bytes()).hexdigest()
        print(f"\nPronto: {exe_limpar}\nTamanho: {exe_limpar.stat().st_size}\nSHA-256: {h2}\n"
              f"Suba os dois .exe na Release (ZenithLauncher.exe e LimparZenith.exe).")
    else:
        print("\nO LimparZenith.exe não saiu (o Launcher principal saiu). Veja o erro do PyInstaller acima.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
