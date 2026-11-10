"""
Zenith — voz RVC rodando num Python 3.10 À PARTE (v20).

Problema (diagnóstico das capturas do Anderson): o modelo .pth estava configurado, mas a
biblioteca `rvc-python` "NÃO instalada" — o Zenith usava a voz base. E ela não instala no
Python do projeto: o `rvc-python` recomenda Python 3.10 (o fairseq dele não acompanha as versões
novas), enquanto o Zenith roda em Python bem mais novo.

Solução: o Zenith mantém um **processo auxiliar** rodando o Python 3.10 do RVC (um venv só dele)
e conversa com ele por linhas de JSON (stdin/stdout). O modelo fica carregado entre as falas, então
só a 1ª fala demora. Se o Python do RVC não existir/falhar, nada quebra: cai na voz base, como antes.

  Zenith (Python novo)  <-- JSON por linha -->  rvc_worker (Python 3.10 + rvc-python + torch)

Este módulo não importa torch nem rvc_python — só fala com o processo. Os testes usam um
`rvc_python` FALSO colocado no PYTHONPATH do processo auxiliar (ver tests/test_v20_*.py).
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

# O worker é embutido aqui (string) para funcionar também no .exe, onde não há pasta tools/.
# Roda no Python 3.10 do RVC; NÃO importa nada do Zenith.
WORKER_SOURCE = r'''
import json, os, sys, traceback

_proto = sys.stdout            # canal do protocolo (uma linha de JSON por resposta)
sys.stdout = sys.stderr        # tudo que as bibliotecas imprimirem vai para o erro, não para o protocolo


def _resp(obj):
    _proto.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _proto.flush()


engine = None
modelo_atual = None
try:
    from rvc_python.infer import RVCInference
except Exception as e:
    _resp({"ok": False, "evento": "inicio", "erro": "import rvc_python falhou: " + repr(e)})
    sys.exit(2)

_resp({"ok": True, "evento": "pronto"})

for linha in sys.stdin:
    linha = linha.strip()
    if not linha:
        continue
    try:
        req = json.loads(linha)
        cmd = req.get("cmd")
        if cmd == "sair":
            _resp({"ok": True, "evento": "saindo"})
            break
        if cmd == "converter":
            device = req.get("device") or "cpu:0"
            if engine is None:
                engine = RVCInference(device=device)
            chave = (req["modelo"], req.get("indice") or "", req.get("versao") or "")
            if chave != modelo_atual:
                try:
                    engine.load_model(req["modelo"], index_path=req.get("indice") or "")
                except TypeError:
                    engine.load_model(req["modelo"])
                modelo_atual = chave
            try:
                if req.get("pitch"):
                    engine.set_params(f0up_key=int(req["pitch"]))
            except Exception:
                pass
            engine.infer_file(req["entrada"], req["saida"])
            ok = os.path.isfile(req["saida"]) and os.path.getsize(req["saida"]) > 0
            _resp({"ok": ok, "evento": "convertido", "saida": req["saida"],
                   "erro": "" if ok else "a inferência rodou mas não gerou arquivo"})
        else:
            _resp({"ok": False, "erro": "comando desconhecido: " + str(cmd)})
    except Exception as e:
        _resp({"ok": False, "erro": repr(e), "trace": traceback.format_exc()[-1500:]})
'''

TEMPO_INICIO = 180.0         # carregar torch + rvc_python na 1ª vez pode demorar
TEMPO_CONVERSAO = 240.0      # primeira frase carrega Hubert/RMVPE + modelo; CPU é lento

_NOMES_PYTHON_OK = ("python.exe", "python3.exe", "python", "python3", "pythonw.exe")


def python_valido(caminho) -> bool:
    """Só aceita um arquivo que se chame python(.exe) e exista — este caminho é EXECUTADO, então não
    pode ser qualquer programa."""
    try:
        p = Path(str(caminho))
        return p.is_file() and p.name.lower() in _NOMES_PYTHON_OK
    except (OSError, ValueError):
        return False


def candidatos_python(base_dir, configurado: str = "") -> list:
    """Onde procurar o Python 3.10 do RVC (em ordem): o caminho configurado e o venv padrão que o
    instalar_rvc.bat cria dentro da pasta do Zenith."""
    base = Path(base_dir)
    achados = []
    if configurado:
        achados.append(Path(configurado))
    achados += [
        base / "tools" / "rvc" / "venv" / "Scripts" / "python.exe",
        base / "tools" / "rvc" / "venv" / "bin" / "python",
        base / "rvc_env" / "Scripts" / "python.exe",
    ]
    return achados


def achar_python_rvc(base_dir, configurado: str = ""):
    for c in candidatos_python(base_dir, configurado):
        if python_valido(c):
            return str(c)
    return None


def mp3_para_wav(origem: str, destino: str) -> bool:
    """Decodifica o áudio (mp3 do Edge-TTS) para WAV 16-bit usando PyAV (já vem junto com o
    faster-whisper), sem precisar de ffmpeg instalado. O RVC lê arquivo com o ffmpeg — com WAV ele
    não precisa. Devolve False se não deu (quem chama então manda o arquivo original)."""
    try:
        import av
        import wave
        import numpy as np
    except Exception:
        return False
    try:
        entrada = av.open(origem)
        fluxo = entrada.streams.audio[0]
        taxa = 44100
        res = av.AudioResampler(format="s16", layout="mono", rate=taxa)
        pedacos = []
        for quadro in entrada.decode(fluxo):
            for r in (res.resample(quadro) or []):
                pedacos.append(r.to_ndarray().reshape(-1))
        for r in (res.resample(None) or []):
            pedacos.append(r.to_ndarray().reshape(-1))
        entrada.close()
        if not pedacos:
            return False
        dados = np.concatenate(pedacos).astype("<i2")
        with wave.open(destino, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(taxa)
            w.writeframes(dados.tobytes())
        return os.path.isfile(destino) and os.path.getsize(destino) > 44
    except Exception:
        return False


class RVCExterno:
    """Gerencia o processo auxiliar. Uma conversão por vez (trava interna)."""

    def __init__(self, python_exe: str, pasta_trabalho, log=print, pythonpath_extra: str = ""):
        self.python_exe = python_exe
        self.pasta = Path(pasta_trabalho)
        self.log = log
        self.pythonpath_extra = pythonpath_extra
        self._proc = None
        self._lock = threading.Lock()
        self.ultimo_erro = ""

    # -- ciclo de vida
    def _arquivo_worker(self) -> Path:
        self.pasta.mkdir(parents=True, exist_ok=True)
        alvo = self.pasta / "rvc_worker.py"
        if not alvo.is_file() or alvo.read_text(encoding="utf-8") != WORKER_SOURCE:
            alvo.write_text(WORKER_SOURCE, encoding="utf-8")
        return alvo

    def vivo(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def parar(self):
        p = self._proc
        self._proc = None
        if p is None:
            return
        try:
            if p.poll() is None:
                try:
                    p.stdin.write(json.dumps({"cmd": "sair"}) + "\n")
                    p.stdin.flush()
                    p.wait(timeout=3)
                except Exception:
                    pass
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
        finally:
            for pipe in (p.stdin, p.stdout):
                try:
                    if pipe:
                        pipe.close()
                except Exception:
                    pass

    def _iniciar(self) -> bool:
        worker = self._arquivo_worker()
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        if self.pythonpath_extra:
            env["PYTHONPATH"] = self.pythonpath_extra + os.pathsep + env.get("PYTHONPATH", "")
        flags = 0
        if sys.platform == "win32":
            flags = 0x08000000        # CREATE_NO_WINDOW
        try:
            self._proc = subprocess.Popen(
                [self.python_exe, "-u", str(worker)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", env=env, creationflags=flags)
        except OSError as e:
            self.ultimo_erro = f"não consegui iniciar o Python do RVC: {e}"
            self._proc = None
            return False
        resp = self._ler_resposta(TEMPO_INICIO)
        if not resp or not resp.get("ok"):
            self.ultimo_erro = (resp or {}).get("erro") or "o Python do RVC não respondeu ao iniciar"
            self.parar()
            return False
        return True

    def _ler_resposta(self, limite: float):
        """Lê UMA linha de JSON do processo, com tempo limite (numa thread, porque readline bloqueia)."""
        p = self._proc
        if p is None:
            return None
        saida = {}

        def _ler():
            try:
                saida["linha"] = p.stdout.readline()
            except Exception as e:
                saida["erro"] = str(e)

        t = threading.Thread(target=_ler, daemon=True)
        t.start()
        t.join(limite)
        if t.is_alive():
            return None
        linha = (saida.get("linha") or "").strip()
        if not linha:
            return None
        try:
            return json.loads(linha)
        except ValueError:
            return None

    # -- conversão
    def converter(self, entrada: str, saida: str, modelo: str, indice: str = "", device: str = "cpu:0",
                  pitch: int = 0) -> tuple:
        """(ok, mensagem). Nunca levanta exceção."""
        with self._lock:
            try:
                if not self.vivo() and not self._iniciar():
                    return False, self.ultimo_erro
                req = {"cmd": "converter", "entrada": entrada, "saida": saida, "modelo": modelo,
                       "indice": indice or "", "device": device, "pitch": pitch}
                self._proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
                resp = self._ler_resposta(TEMPO_CONVERSAO)
                if resp is None:
                    self.parar()                       # travou ou morreu: recomeça na próxima fala
                    self.ultimo_erro = "o Python do RVC não respondeu a tempo (ou fechou)"
                    return False, self.ultimo_erro
                if not resp.get("ok"):
                    self.ultimo_erro = resp.get("erro") or "conversão falhou"
                    return False, self.ultimo_erro
                self.ultimo_erro = ""
                return True, "ok"
            except Exception as e:
                self.parar()
                self.ultimo_erro = f"erro falando com o Python do RVC: {e}"
                return False, self.ultimo_erro
