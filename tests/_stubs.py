"""
Auxiliar de testes: injeta módulos "de mentira" no lugar das dependências pesadas
(websockets, chromadb, openai, google-genai, edge-tts, pygame, sounddevice...) SÓ
se elas não estiverem instaladas. Assim dá pra importar brain.zenith_headless e
brain.zenith_core e exercitar a lógica deles em qualquer máquina, sem rede, sem
áudio e sem Godot. Não afeta uma máquina que já tem as bibliotecas de verdade.
"""
import importlib.util
import sys
import types
from unittest import mock

_NOMES = ["websockets", "chromadb", "chromadb.config", "openai", "google", "google.genai",
          "google.genai.types", "edge_tts", "pygame", "sounddevice", "faster_whisper",
          "cv2", "mss", "serial", "serial.tools", "serial.tools.list_ports", "plyer",
          "customtkinter", "tkinter", "onnxruntime", "tokenizers"]


def _falta(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is None
    except (ImportError, ValueError, AttributeError):
        return True


def instalar():
    for nome in _NOMES:
        if nome in sys.modules or not _falta(nome):
            continue
        mod = types.ModuleType(nome)
        mod.__path__ = []                       # deixa "import a.b" funcionar
        mod.__getattr__ = lambda attr, _n=nome: mock.MagicMock(name=f"{_n}.{attr}")
        sys.modules[nome] = mod
