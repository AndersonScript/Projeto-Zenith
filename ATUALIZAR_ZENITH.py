"""Atualiza o Zenith com um .zip novo, sem perder suas conversas, chaves e criações.
Arraste o .zip em cima deste arquivo, ou:  python ATUALIZAR_ZENITH.py caminho\\Zenith_v1_X_Y.zip   (--so-conferir só mostra o que mudaria)"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_path(str(Path(__file__).resolve().parent / "tools" / "atualizar_de_zip.py"), run_name="__main__")
