"""Zenith — versão em um lugar só (mostrada em /versao, no diagnóstico e no relatório).

v1.0 — a versão oficial. O Anderson decidiu que a numeração reinicia aqui ("1.0 mesmo"),
então o formato agora é `vMAJOR.MINOR` (antes era `v30`, `v31`...). Por isso existe
`numero()`: qualquer comparação ("esta versão é pelo menos 1.0?") usa a tupla, não o texto.

Também entra a DATA DO BUILD (pedido A12): `/versao` mostra quando o .exe foi compilado, o que
acaba com a dúvida "será que eu estou rodando a versão nova?". Quem grava o arquivo é o
build_exe.py; se o arquivo não existir (rodando do código-fonte), a data vem do próprio código.
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

VERSAO = "v1.0"
ROTULO = "1.0 Oficial"          # como aparece para quem não é programador (site, Release, /versao)
NOME = "Zenith"
DESCRICAO = "Cérebro Python + Corpo Godot"
def edicao() -> str:
    """'publico' ou 'admin' (ver brain/zenith_edicao.py)."""
    try:
        from brain import zenith_edicao
        return zenith_edicao.edicao()
    except Exception:
        return "admin"


EDICAO = "admin"          # só o valor de partida; quem decide de verdade é edicao()
ARQUIVO_BUILD = "VERSAO_BUILD.txt"


def numero(versao: str = "") -> tuple:
    """'v1.0' -> (1, 0, 0). Aceita 'v30' (-> (30, 0, 0)) para não quebrar código antigo."""
    nums = [int(n) for n in re.findall(r"\d+", versao or VERSAO)][:3]
    return tuple((nums + [0, 0, 0])[:3])


def _candidatos_build() -> list:
    """Onde procurar o arquivo com a data do build (do mais confiável para o menos)."""
    saida = []
    try:
        from brain.zenith_settings import BASE_DIR           # pasta do .exe / do projeto
        saida.append(Path(BASE_DIR) / ARQUIVO_BUILD)
    except Exception:
        pass
    try:
        if getattr(sys, "frozen", False):
            saida.append(Path(sys.executable).resolve().parent / ARQUIVO_BUILD)
    except Exception:
        pass
    saida.append(Path(__file__).resolve().parent.parent / ARQUIVO_BUILD)
    return saida


def data_build() -> str:
    """Data/hora em que este .exe foi compilado ('17/10/2026 06:31'), ou "" se não souber."""
    for caminho in _candidatos_build():
        try:
            if caminho.is_file():
                texto = caminho.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                if texto:
                    # O arquivo é "18/10/2026 14:05 — v1.0 — Python 3.13.1": o que interessa é a data.
                    achado = re.search(r"\d{2}/\d{2}/\d{4}[ T]\d{2}:\d{2}", texto[0])
                    return achado.group(0) if achado else texto[0].strip()[:40]
        except OSError:
            continue
    try:                                        # sem arquivo: a data do próprio código
        return datetime.datetime.fromtimestamp(Path(__file__).stat().st_mtime).strftime("%d/%m/%Y %H:%M")
    except OSError:
        return ""


def texto() -> str:
    base = f"{NOME} {VERSAO} Oficial — {DESCRICAO}"
    data = data_build()
    return f"{base} · build de {data}" if data else base
