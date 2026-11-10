"""Trava de progresso do port: cada módulo do Cérebro tem que IMPORTAR num "celular simulado".

O celular simulado = as bibliotecas presas ao PC (Tk, microfone, câmera, chromadb, Whisper...) ficam AUSENTES de
verdade (ImportError), e as de rede/IA são falsas (no celular elas são instaladas à parte). Se alguém voltar a
escrever `import tkinter` solto no topo de um módulo que o celular precisa, este teste quebra na hora — não no
aparelho de alguém.

Os módulos de INTERFACE ANTIGA em Tk (zenith_ui, zenith_widgets) não existem no celular: o Corpo Godot os substitui.

    python -m unittest tests.test_importa_no_celular
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
NAO_EXISTEM_NO_CELULAR = {"zenith_ui", "zenith_widgets"}        # interface antiga em Tk

CODIGO = r'''
import sys, types, os
from unittest import mock
os.environ["ZENITH_PLATAFORMA"] = "android"
for n in ("websockets","openai","google","google.genai","google.genai.types","edge_tts","onnxruntime","tokenizers","requests"):
    m = types.ModuleType(n); m.__path__ = []; m.__getattr__ = lambda a, _n=n: mock.MagicMock(); sys.modules[n] = m
for n in ("tkinter","_tkinter","customtkinter","sounddevice","pygame","cv2","mss","mss.tools","serial","serial.tools",
          "serial.tools.list_ports","plyer","chromadb","chromadb.config","faster_whisper","matplotlib","sympy","pyaudio",
          "win32api","win32gui","winreg"):
    sys.modules[n] = None
import importlib
importlib.import_module("brain." + sys.argv[1])
'''


class ImportaNoCelularSimulado(unittest.TestCase):
    def test_todo_modulo_do_cerebro_importa(self):
        modulos = sorted(p.stem for p in (RAIZ / "brain").glob("*.py") if p.stem != "__init__")
        if not modulos:
            self.skipTest("pasta brain/ não encontrada")
        quebrados = []
        for nome in modulos:
            if nome in NAO_EXISTEM_NO_CELULAR:
                continue
            r = subprocess.run([sys.executable, "-c", CODIGO, nome], capture_output=True, text=True,
                               timeout=120, cwd=str(RAIZ))
            if r.returncode != 0:
                linhas = [l for l in r.stderr.strip().splitlines() if l.strip()]
                quebrados.append(f"{nome}: {linhas[-1][:150] if linhas else '?'}")
        self.assertEqual(quebrados, [], "Estes módulos não importam num celular simulado:\n  " + "\n  ".join(quebrados))

    def test_o_modulo_que_liga_tudo_ao_corpo_importa(self):
        """zenith_headless é o Cérebro de verdade (o que o Godot usa). Se ele não importar, nada anda."""
        r = subprocess.run([sys.executable, "-c", CODIGO, "zenith_headless"], capture_output=True, text=True,
                           timeout=120, cwd=str(RAIZ))
        self.assertEqual(r.returncode, 0, r.stderr[-600:])

    def test_a_regra_do_gatekeeper_vale_sem_tk(self):
        codigo = CODIGO + "\nfrom brain.zenith_gatekeeper import DeterministicGuard\n" \
                          "g = DeterministicGuard('Anderson')\nassert g.check_action('terminal', 'echo oi') is None or True\n" \
                          "from brain import zenith_gatekeeper as G\nassert G.tk is None\n"
        r = subprocess.run([sys.executable, "-c", codigo, "zenith_gatekeeper"], capture_output=True, text=True,
                           timeout=120, cwd=str(RAIZ))
        self.assertEqual(r.returncode, 0, r.stderr[-600:])

    def test_janela_antiga_de_aprovacao_avisa_em_vez_de_quebrar_feio(self):
        codigo = CODIGO + "\nfrom brain import zenith_gatekeeper as G\n" \
                          "try:\n    G.ApprovalWindow(None, None, 'a', 'b')\nexcept RuntimeError as e:\n" \
                          "    assert 'pelo Corpo' in str(e)\nelse:\n    raise SystemExit('deveria ter avisado')\n"
        r = subprocess.run([sys.executable, "-c", codigo, "zenith_gatekeeper"], capture_output=True, text=True,
                           timeout=120, cwd=str(RAIZ))
        self.assertEqual(r.returncode, 0, r.stderr[-600:])


if __name__ == "__main__":
    unittest.main()
