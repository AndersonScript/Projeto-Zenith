"""Abre o Zenith (instala o que faltar). Clique duas vezes aqui, ou:  python INICIAR_ZENITH.py
Opções: --so-conferir (só mostra o que faria) · --sem-abrir · --refazer (recria o ambiente) · --gerar-exe [--edicao=publico]
Funciona com qualquer Python 3.8+: ele mesmo procura o 3.13/3.12 e usa só ele (veja tools/instalar_zenith.py)."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_path(str(Path(__file__).resolve().parent / "tools" / "instalar_zenith.py"), run_name="__main__")
