"""Zenith — camada de PLATAFORMA: o que muda entre o PC e o celular (v1.11, port Android).

Por que isto existe
-------------------
O Cérebro nasceu no Windows. Dos 92 módulos de `brain/`, 25 importam direto uma biblioteca presa ao
PC (microfone, tela, câmera, áudio, banco de memória...). Para o MESMO código rodar dentro do celular,
sem PC e sem reescrever tudo, o módulo não pode falar com `sounddevice`, `mss` ou `pygame`: ele fala
com a PLATAFORMA, e cada sistema entrega a sua implementação.

    módulo do Cérebro ──> plataforma.obter().capturar_tela()
                              ├── PCPlataforma      (mss, opencv, plyer...)
                              └── AndroidPlataforma (pede ao app Android, pela "ponte")

Regras desta camada
-------------------
1. As assinaturas COPIAM as que já existem no código (ex.: `capturar_tela` devolve `(bytes, erro)` como o
   `ZenithVision.capture_screen`). Migrar um módulo é trocar a chamada, não repensar o módulo.
2. Capacidade que não existe NÃO quebra o programa: levanta `Indisponivel` com uma frase em português
   (ou devolve `(None, motivo)` onde o código antigo já fazia isso). Quem chama decide o que mostrar —
   é o que o "downgrade" precisa: desligar a voz ou a câmera não pode derrubar o resto.
3. Nada aqui abre microfone, câmera ou tela sozinho: quem pede é o Cérebro, depois do Gatekeeper.
4. Não há "modo PC" no celular: tudo o que a plataforma Android entrega vem do próprio aparelho.
"""
from __future__ import annotations

import os
import shutil
import sys

um_gb = 1024 ** 3


class Indisponivel(RuntimeError):
    """A plataforma atual não tem (ou ainda não ligou) a capacidade pedida."""


# nome da capacidade -> como aparece numa mensagem para a pessoa
CAPACIDADES = {
    "sistema": "medir memória, CPU, disco e bateria",
    "audio_saida": "tocar um arquivo de áudio",
    "microfone": "receber o áudio do microfone",
    "transcricao": "transformar fala em texto sem internet",
    "voz_local": "gerar a voz sem internet",
    "tela": "capturar a tela",
    "camera": "tirar uma foto com a câmera",
    "notificacao": "mostrar uma notificação",
    "abrir": "abrir um aplicativo, arquivo ou endereço",
    "ble": "falar por Bluetooth com o carrinho",
    "llm_local": "usar a IA que roda dentro do aparelho",
    "video": "ler as informações e os quadros de um vídeo",
}


def _ler_arquivo(caminho: str) -> str:
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _parse_meminfo(texto: str):
    """Lê o texto de /proc/meminfo (Linux e Android). Devolve (total_gb, livre_gb) ou (None, None)."""
    valores = {}
    for linha in (texto or "").splitlines():
        if ":" not in linha:
            continue
        chave, _, resto = linha.partition(":")
        partes = resto.split()
        if partes and partes[0].isdigit():
            valores[chave.strip()] = int(partes[0]) * 1024          # o arquivo vem em kB
    total = valores.get("MemTotal")
    if not total:
        return None, None
    livre = valores.get("MemAvailable")
    if livre is None:
        livre = valores.get("MemFree", 0) + valores.get("Buffers", 0) + valores.get("Cached", 0)
    return total / um_gb, livre / um_gb


def medir_sistema(psutil_mod=None, meminfo: str | None = None, disco: str = "") -> dict:
    """Mede o aparelho. Mesmas chaves de `zenith_desempenho.medir()` + bateria/carregando/temperatura.

    `psutil_mod` e `meminfo` (texto de /proc/meminfo) são injetáveis para teste. Sem conseguir medir,
    devolve None no campo — nunca um chute (regra de honestidade do módulo de desempenho do PC)."""
    medida = {"ram_total_gb": None, "ram_livre_gb": None, "cpu_pct": None, "nucleos": os.cpu_count() or 0,
              "disco_livre_gb": None, "bateria_pct": None, "carregando": None, "temperatura_c": None,
              "fonte": ""}
    try:
        medida["disco_livre_gb"] = round(shutil.disk_usage(disco or os.getcwd()).free / um_gb, 1)
    except OSError:
        pass
    if psutil_mod is not None:
        try:
            vm = psutil_mod.virtual_memory()
            medida.update(ram_total_gb=round(vm.total / um_gb, 1), ram_livre_gb=round(vm.available / um_gb, 1),
                          cpu_pct=float(psutil_mod.cpu_percent(interval=0.2)), fonte="psutil")
            return medida
        except Exception:
            pass
    texto = meminfo if meminfo is not None else (_ler_arquivo("/proc/meminfo") if os.name != "nt" else "")
    total, livre = _parse_meminfo(texto)
    if total is None and os.name == "nt":
        try:                                              # no Windows, reaproveita o que já existe e funciona
            from brain import zenith_desempenho
            total, livre = zenith_desempenho._memoria_windows()
        except Exception:
            total = livre = None
    if total is not None:
        medida.update(ram_total_gb=round(total, 1), ram_livre_gb=round(livre, 1) if livre is not None else None,
                      fonte="meminfo" if os.name != "nt" else "windows")
    return medida


class Plataforma:
    """Contrato. Cada subclasse declara em `capacidades` o que realmente entrega."""

    nome = "base"
    capacidades: frozenset = frozenset({"sistema"})

    # ---- consulta -----------------------------------------------------------------------------
    def tem(self, capacidade: str) -> bool:
        return capacidade in self.capacidades

    def _exigir(self, capacidade: str) -> None:
        if capacidade not in CAPACIDADES:
            raise ValueError(f"capacidade desconhecida: {capacidade!r}")
        if capacidade not in self.capacidades:
            raise Indisponivel(f"Nesta plataforma ({self.nome}) não dá para: {CAPACIDADES[capacidade]}.")

    def _nao_implementado(self, capacidade: str):
        raise NotImplementedError(f"{self.nome}: '{capacidade}' foi declarada mas não foi implementada.")

    # ---- sistema ------------------------------------------------------------------------------
    def medir(self) -> dict:
        return medir_sistema()

    # ---- áudio --------------------------------------------------------------------------------
    def tocar_audio(self, caminho: str, volume: float = 1.0) -> None:
        self._exigir("audio_saida")
        self._nao_implementado("audio_saida")

    def parar_audio(self) -> None:
        self._exigir("audio_saida")
        self._nao_implementado("audio_saida")

    def audio_ocupado(self) -> bool:
        """True enquanto o áudio iniciado por `tocar_audio` ainda está tocando."""
        self._exigir("audio_saida")
        self._nao_implementado("audio_saida")

    def iniciar_microfone(self, ao_receber, taxa: int = 16000) -> None:
        """`ao_receber(pcm16: bytes)` é chamada a cada pedaço de áudio (16 bits, mono)."""
        self._exigir("microfone")
        self._nao_implementado("microfone")

    def parar_microfone(self) -> None:
        self._exigir("microfone")
        self._nao_implementado("microfone")

    def transcrever(self, pcm16: bytes, taxa: int = 16000, idioma: str = "pt") -> str:
        self._exigir("transcricao")
        self._nao_implementado("transcricao")

    def sintetizar(self, texto: str, caminho_saida: str, voz: str = "", velocidade: float = 1.0,
                   tom: float = 1.0) -> bool:
        self._exigir("voz_local")
        self._nao_implementado("voz_local")

    # ---- visão (mesmas assinaturas de ZenithVision) ----------------------------------------------
    def capturar_tela(self, max_w: int = 0, jpeg: bool = False):
        """Devolve (bytes, None) ou (None, motivo)."""
        try:
            self._exigir("tela")
        except Indisponivel as e:
            return None, str(e)
        self._nao_implementado("tela")

    def capturar_camera(self, warmup: int = 5, max_w: int = 0):
        """Devolve (bytes_jpeg, None) ou (None, motivo)."""
        try:
            self._exigir("camera")
        except Indisponivel as e:
            return None, str(e)
        self._nao_implementado("camera")

    # ---- vídeo (v1.19) -----------------------------------------------------------------------------
    # No PC quem lê vídeo é o OpenCV (direto nos módulos). No celular o OpenCV quase nunca existe: quem lê é o Android.
    def video_info(self, caminho: str) -> dict:
        """{'duracao_s', 'largura', 'altura', 'fps'} (fps 0 quando o aparelho não sabe). Levanta Indisponivel se não há."""
        self._exigir("video")
        self._nao_implementado("video")

    def video_quadros(self, caminho: str, pasta: str, inicio_s: float = 0.0, fps: float = 15.0,
                      max_quadros: int = 180, max_largura: int = 854, qualidade: int = 80,
                      tempo_limite_s: float = 90.0) -> dict:
        """Grava f0001.jpg, f0002.jpg... em `pasta`. Devolve {'n': quantos gravou, 'fps': a taxa real}."""
        self._exigir("video")
        self._nao_implementado("video")

    # ---- sistema do usuário -----------------------------------------------------------------------
    def notificar(self, titulo: str, texto: str) -> bool:
        self._exigir("notificacao")
        self._nao_implementado("notificacao")

    def abrir(self, alvo: str) -> bool:
        self._exigir("abrir")
        self._nao_implementado("abrir")

    # ---- carrinho ------------------------------------------------------------------------------------
    def ble_enviar(self, dispositivo: str, dados: bytes) -> bool:
        self._exigir("ble")
        self._nao_implementado("ble")

    # ---- IA local ------------------------------------------------------------------------------------
    def endereco_llm_local(self):
        """URL (compatível com OpenAI) do modelo que roda no aparelho, ou None se não há."""
        self._exigir("llm_local")
        self._nao_implementado("llm_local")


# ---- escolha da plataforma -------------------------------------------------------------------------
_ponte = None
_cache = None


def detectar() -> str:
    """'android', 'windows' ou 'linux'. `ZENITH_PLATAFORMA` força o valor (útil em teste)."""
    forcado = os.environ.get("ZENITH_PLATAFORMA", "").strip().lower()
    if forcado in ("android", "windows", "linux"):
        return forcado
    if (sys.platform == "android" or hasattr(sys, "getandroidapilevel")
            or ("ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ)):   # inclui o Termux
        return "android"
    return "windows" if os.name == "nt" else "linux"


def registrar_ponte(ponte) -> None:
    """O app Android chama isto ao iniciar o Cérebro, entregando o objeto que fala com o aparelho."""
    global _ponte, _cache
    _ponte = ponte
    _cache = None


def definir(plataforma) -> None:
    """Troca a plataforma ativa (usado nos testes)."""
    global _cache
    _cache = plataforma


def obter() -> Plataforma:
    global _cache
    if _cache is None:
        if detectar() == "android":
            from brain.zenith_plataforma_android import AndroidPlataforma
            _cache = AndroidPlataforma(_ponte)
        else:
            from brain.zenith_plataforma_pc import PCPlataforma
            _cache = PCPlataforma()
    return _cache
