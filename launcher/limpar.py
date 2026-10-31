"""Entrada do LimparZenith.exe — a janela de "apagar por partes" e "desinstalar tudo".

Uso (do código, sem compilar):
    python launcher\\limpar.py                 -> abre a janela com as caixinhas
    python launcher\\limpar.py --desinstalar    -> desinstala tudo (pergunta antes)
    python launcher\\limpar.py --limpar historico,chaves --sim   -> sem janela
"""
from __future__ import annotations

import sys

import zenith_instalador as ZI

if __name__ == "__main__":
    argumentos = sys.argv[1:]
    if not any(a.startswith("--desinstalar") or a.startswith("--limpar") for a in argumentos):
        argumentos = ["--limpar"] + argumentos        # sem argumento = janela com as caixinhas
    sys.exit(ZI.main(argumentos))
