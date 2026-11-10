# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_main.py — Atalho de desenvolvimento.
#
#  Pra rodar o Zenith de verdade, use zenith_launcher.py (é ele que
#  vira o Zenith.exe). Este arquivo continua existindo só pra rodar
#  o Cérebro isolado, sem o Corpo, direto no terminal — útil pra
#  debugar respostas da IA sem precisar abrir o Godot toda hora.
# ============================================================

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.zenith_headless import run as run_headless


def main():
    print("[Zenith] Modo desenvolvimento: só o Cérebro, sem abrir o Corpo.")
    print("[Zenith] Para o sistema completo (Cérebro + Corpo em uma janela), "
          "rode zenith_launcher.py na raiz do projeto.")
    run_headless()


if __name__ == "__main__":
    main()
