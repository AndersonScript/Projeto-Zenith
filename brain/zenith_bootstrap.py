# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_bootstrap.py — Checagem/instalação automática de
#  dependências na primeira execução.
#
#  Só faz sentido quando o Zenith está rodando A PARTIR DO CÓDIGO-FONTE
#  (python zenith_launcher.py). Se já foi empacotado num .exe pelo
#  PyInstaller, o Python e todas as bibliotecas JÁ estão dentro do
#  executável — não tem o que baixar. Detectamos isso e pulamos.
#
#  Tudo aqui é best-effort e envolto em try/except: se alguma etapa
#  falhar (sem internet, sem permissão, etc.), o programa AVISA no
#  console e continua tentando abrir mesmo assim, em vez de travar
#  sem explicação nenhuma — foi bug real antes ("crashava sem log").
# ============================================================

import importlib
import os
import subprocess
import sys

# nome do pacote pip -> nome usado no "import"
_REQUIRED = {
    "customtkinter": "customtkinter",
    "websockets": "websockets",
    "openai": "openai",
    "google-genai": "google.genai",
    "chromadb": "chromadb",
    "Pillow": "PIL",
    "edge-tts": "edge_tts",
    # CORREÇÃO: "pygame" (o pacote original na PyPI) ainda não tem uma
    # versão pronta (wheel) pro Python 3.14 — pip tenta compilar do
    # zero e quebra, porque o sistema de build dele é velho demais pro
    # Python 3.14 (usa uma parte do "distutils" que foi removida).
    # "pygame-ce" é o fork da comunidade, tem wheel pro 3.14, e
    # continua funcionando com "import pygame" normalmente — sem
    # mudar nadá no resto do código.
    "pygame-ce": "pygame",
    "requests": "requests",
    "pyserial": "serial",
    "mss": "mss",
    "opencv-python-headless": "cv2",
    # CORREÇÃO (revisão de código): estes seis pacotes estão no
    # requirements.txt e são de verdade usados (sounddevice/numpy/
    # faster-whisper são importados sob demanda dentro de
    # zenith_interaction.py, só na hora de gravar/transcrever — por
    # isso não apareciam num "import" no topo de nenhum arquivo, e
    # tinham ficado de fora daqui por engano). Sem eles nesta lista, uma
    # instalação rodando DIRETO DO CÓDIGO-FONTE (não o .exe empacotado,
    # que já traz tudo) passava pela checagem de dependências sem
    # problema nenhum, e só ia quebrar (import faltando) na hora de
    # usar o microfone, gerar um gráfico, ou guardar/buscar uma memória
    # — silenciosamente tarde demais pra esse aviso ajudar.
    "sounddevice": "sounddevice",
    "numpy": "numpy",
    "faster-whisper": "faster_whisper",
    "matplotlib": "matplotlib",
    "onnxruntime": "onnxruntime",
    "tokenizers": "tokenizers",
}


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _missing_packages() -> list:
    missing = []
    for pip_name, import_name in _REQUIRED.items():
        try:
            importlib.import_module(import_name)
        except Exception:
            missing.append(pip_name)
    return missing


def _pip_env() -> dict:
    """Desliga a saída colorida ("rich") do pip. Em ambientes onde o
    Windows bloqueia a DLL de _ctypes (Controle de Aplicativo — o
    mesmo problema que já afetou pygame/libcrypto/pywin32-ctypes por
    aqui), o próprio pip quebra tentando DESENHAR a barra de progresso
    colorida, e isso enchia o console de tracebacks "--- Logging
    error ---" que escondiam o erro de instalação de verdade lá
    embaixo. Sem cor, o pip usa um caminho que não depende disso."""
    env = os.environ.copy()
    env["PIP_NO_COLOR"] = "1"
    env["NO_COLOR"] = "1"
    env["PIP_PROGRESS_BAR"] = "off"
    return env


def ensure_dependencies():
    if _is_frozen():
        print("[Zenith/Bootstrap] Rodando como executável empacotado — "
              "dependências já estão embutidas, pulando checagem.")
        return True

    try:
        missing = _missing_packages()
    except Exception as e:
        print(f"[Zenith/Bootstrap] Não consegui checar dependências ({e}). "
              f"Tentando abrir mesmo assim.")
        return True

    if not missing:
        print("[Zenith/Bootstrap] Todas as dependências já estão instaladas.")
        return True

    print(f"[Zenith/Bootstrap] Faltando: {', '.join(missing)}. Instalando automaticamente...")
    env = _pip_env()
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", *missing],
            check=True, env=env,
        )
        print("[Zenith/Bootstrap] Instalação concluída.")
        return True
    except subprocess.CalledProcessError:
        # Alguns Pythons (instalados fora do sistema, ex. venv) não aceitam
        # --break-system-packages — tenta de novo sem a flag antes de desistir.
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=True, env=env)
            print("[Zenith/Bootstrap] Instalação concluída (sem --break-system-packages).")
            return True
        except Exception as e2:
            print(f"[Zenith/Bootstrap] Não consegui instalar sozinho ({e2}).")
            print(f"[Zenith/Bootstrap] Rode manualmente: pip install {' '.join(missing)}")
            return False
    except Exception as e:
        print(f"[Zenith/Bootstrap] Erro inesperado instalando dependências: {e}")
        return False
