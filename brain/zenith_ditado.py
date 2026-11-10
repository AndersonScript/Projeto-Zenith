"""Zenith — ditado ao vivo, do jeito do Word (v1.5, tarefa T1).

O problema que isto resolve: hoje (`zenith_interaction.py`) o texto parcial sai a cada ~1 s
RE-TRANSCREVENDO TUDO com o Whisper "small" no CPU. O texto pisca, recua e demora.

Aqui a política de exibição é separada do motor de reconhecimento:

    MotorFluxo (motor)  ->  EstadoDitado (o que já é certo x o que ainda pode mudar)  ->  comandos pt-BR

1. **Motor** — qualquer coisa que receba áudio e produza texto parcial/final:
   `alimentar(pcm16, taxa)` e `eventos()` -> `("parcial", texto)` / `("final", texto)`.
   - `MotorVosk`: parciais em ~200-300 ms (opcional; só se o pacote `vosk` e o modelo existirem).
   - `MotorJanela`: reserva SEM dependência nova — re-transcreve só a janela recente (padrão 8 s)
     a cada `passo_s`, usando uma função `transcrever` injetada (o Whisper que já existe).
2. **LocalAgreement-2** — uma palavra só vira "estável" quando DUAS passadas seguidas concordam
   nela. O trecho estável nunca recua; a cauda pode mudar à vontade e é mostrada mais clara.
3. **Comandos pt-BR** — "vírgula", "ponto", "ponto de interrogação", "nova linha", "apagar isso"
   e maiúscula depois de ponto. Tudo em função PURA (`aplicar_comandos`).

A tela recebe sempre o mesmo contrato: `{"action": "voice_partial", "stable": "...", "tail": "..."}`.
O texto final (depois da passada de correção) sai como `{"action": "voice_final", "text": "..."}`.

Nada aqui abre microfone, rede ou arquivo: quem grava é o `zenith_interaction.py`; este módulo
só decide o que mostrar. Por isso roda inteirinho em teste, com motor falso.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

ACAO_PARCIAL = "voice_partial"
ACAO_FINAL = "voice_final"

NL = chr(10)            # quebra de linha (escrita assim para o arquivo não depender de escape)
TAB = chr(9)
LETRAS = "A-Za-zÀ-ÖØ-öø-ÿ"


# ======================================================================
# Comandos de pontuação em português (função pura, testada)
# ======================================================================
# A ordem importa: as expressões longas vêm antes das curtas ("ponto de interrogação" antes de "ponto").
_COMANDOS = (
    ("ponto de interroga[çc][ãa]o", "?"),
    ("ponto de exclama[çc][ãa]o", "!"),
    ("ponto e v[íi]rgula", ";"),
    ("dois pontos", ":"),
    ("retic[êe]ncias", "…"),
    ("ponto final", "."),
    ("ponto", "."),
    ("v[íi]rgula", ","),
    ("nova linha|quebra de linha", NL),
)
_RX_COMANDOS = re.compile(
    "(?<![" + LETRAS + "])(" + "|".join("(?:%s)" % p for p, _ in _COMANDOS) + ")(?![" + LETRAS + "])",
    re.I)
_MAPA = [(re.compile("^(?:%s)$" % p, re.I), s) for p, s in _COMANDOS]
_FIM_DE_FRASE = re.compile("[.!?…" + NL + "]")
_APAGAR = re.compile("(?<![" + LETRAS + "])apagar (?:isso|isto|essa frase)(?![" + LETRAS + "])", re.I)
_ESPACOS = re.compile("[" + TAB + " ]+")
_ANTES_DE_PONTUACAO = re.compile("[" + TAB + " ]+([,.;:!?…])")
_DEPOIS_DE_PONTUACAO = re.compile("([,.;:!?…])(?=([^ " + NL + "]))")
_ESPACO_ANTES_DA_LINHA = re.compile(" +" + NL)
def _espaco_depois(m) -> str:
    """Põe um espaço depois da pontuação — menos em decimal (4,98 / 3.14)."""
    sinal, proximo = m.group(1), m.group(2)
    if sinal in ",." and proximo.isdigit():
        return sinal
    return sinal + " "


_MUITAS_LINHAS = re.compile(NL + "{3,}")
_ESPACO_NO_INICIO_DA_LINHA = re.compile(NL + "[" + TAB + " ]+")


def _simbolo(achado: str) -> str:
    for rx, simbolo in _MAPA:
        if rx.match(achado):
            return simbolo
    return achado


def apagar_ultima_frase(texto: str) -> str:
    """'apagar isso' — tira a última frase (a que termina no último . ! ? … ou quebra de linha)."""
    t = (texto or "").rstrip()
    if not t:
        return ""
    cortes = list(_FIM_DE_FRASE.finditer(t))
    if not cortes:
        return ""
    fim = cortes[-1].end()
    if fim >= len(t):                       # a última frase termina no fim: apaga ela inteira
        inicio = cortes[-2].end() if len(cortes) > 1 else 0
        return t[:inicio].rstrip()
    return t[:fim].rstrip()                 # a última frase ainda não tinha ponto: apaga ela


def aplicar_comandos(texto: str) -> str:
    """Troca as palavras-comando por pontuação e arruma espaços. Puro: mesma entrada, mesma saída."""
    if not texto:
        return ""
    # 1) pontuação PRIMEIRO: "apagar isso" tira a frase já pontuada (senão a palavra "ponto"
    #    ainda não virou "." e não haveria onde cortar).
    saida = _RX_COMANDOS.sub(lambda m: _simbolo(m.group(1)), texto)
    # 2) "apagar isso" quantas vezes aparecer: tira o marcador e a última frase.
    for _ in range(20):
        novo = _APAGAR.sub(" ", saida, count=1)
        if novo == saida:
            break
        saida = apagar_ultima_frase(novo)
    saida = _ESPACOS.sub(" ", saida)
    saida = _ANTES_DE_PONTUACAO.sub(lambda m: m.group(1), saida)
    saida = _DEPOIS_DE_PONTUACAO.sub(_espaco_depois, saida)
    saida = _ESPACO_ANTES_DA_LINHA.sub(NL, saida)
    saida = _MUITAS_LINHAS.sub(NL + NL, saida)
    saida = _ESPACO_NO_INICIO_DA_LINHA.sub(NL, saida)
    return saida.strip()


def capitalizar(texto: str) -> str:
    """Maiúscula no começo e depois de . ! ? … ou quebra de linha (como o Word faz)."""
    if not texto:
        return ""
    saida = []
    maiuscula = True
    for c in texto:
        if maiuscula and c.isalpha():
            saida.append(c.upper())
            maiuscula = False
            continue
        saida.append(c)
        if c in ".!?…" or c == NL:
            maiuscula = True
    return "".join(saida)


def formatar(texto: str) -> str:
    """Comandos + capitalização. É o que o chat recebe no fim da fala."""
    return capitalizar(aplicar_comandos(texto))


# ======================================================================
# LocalAgreement-2
# ======================================================================
def _palavras(texto: str) -> list:
    return [p for p in formatar(texto or "").split() if p]


def _prefixo_comum(a: list, b: list) -> int:
    n = 0
    for x, y in zip(a, b):
        if x.casefold() != y.casefold():
            break
        n += 1
    return n


def local_agreement(anterior: Iterable, atual: Iterable) -> int:
    """Quantas palavras do começo as DUAS passadas concordam (o critério LocalAgreement-2).

    `anterior` é a passada anterior e `atual` a de agora. Devolve o tamanho do prefixo igual —
    é o que pode ser mostrado como "certo" sem risco de piscar.
    """
    return _prefixo_comum(list(anterior), list(atual))


class EstadoDitado:
    """Dono único do que já é certo (`estavel`) e do que ainda pode mudar (`cauda`).

    Regra de ouro: **o estável nunca recua**. Se a nova passada discorda de uma palavra que já
    estava estável, ela continua estável (o reconhecedor pode ter errado antes; voltar atrás faria
    o texto piscar, que é justamente o defeito do método antigo). A cauda, sim, muda sempre.
    """

    def __init__(self, estavel: str = ""):
        self._estavel = _palavras(estavel)
        self._ultima = list(self._estavel)

    @property
    def estavel(self) -> str:
        return " ".join(self._estavel)

    def atualizar(self, texto: str) -> dict:
        """Recebe a transcrição da passada atual e devolve `{"stable", "tail"}`."""
        atual = _palavras(texto)
        confirmadas = min(local_agreement(self._ultima, atual), len(atual))
        # Só cresce: nunca volta atrás do que já foi confirmado.
        if confirmadas > len(self._estavel):
            self._estavel = atual[:confirmadas]
        self._ultima = atual
        cauda = atual[len(self._estavel):] if len(atual) > len(self._estavel) else []
        return {"stable": self.estavel, "tail": " ".join(cauda)}

    def finalizar(self, texto: str = "") -> str:
        """Fecha a fala: a passada de correção manda. Sem texto novo, vale o que estava na tela."""
        if texto:
            self._estavel = _palavras(texto)
        return self.estavel


# ======================================================================
# Motores
# ======================================================================
class MotorFluxo:
    """Interface mínima de um motor de reconhecimento em fluxo."""

    nome = "motor"

    def alimentar(self, pcm16, taxa: int = 16000) -> None:
        raise NotImplementedError

    def eventos(self) -> list:
        return []

    def fechar(self) -> None:
        return None


class MotorVosk(MotorFluxo):
    """Parciais rápidos com Vosk (opcional: sem o pacote/modelo, `abrir()` devolve None)."""

    nome = "vosk"

    def __init__(self, modelo, taxa: int = 16000):
        self._modelo = modelo
        self._taxa = taxa
        self._rec = modelo.KaldiRecognizer(taxa)
        self._fila = []

    @staticmethod
    def disponivel() -> bool:
        try:
            import vosk  # noqa: F401
        except Exception:
            return False
        return True

    @classmethod
    def abrir(cls, caminho_modelo: str, taxa: int = 16000):
        """Carrega o modelo; devolve None (sem travar nada) se o Vosk não estiver instalado."""
        try:
            import vosk
            vosk.SetLogLevel(-1)
            return cls(vosk.Model(str(caminho_modelo)), taxa)
        except Exception:
            return None

    def alimentar(self, pcm16, taxa: int = 16000) -> None:
        if not pcm16:
            return
        if self._rec.AcceptWaveform(bytes(pcm16)):
            self._fila.append(("final", self._texto(self._rec.Result())))
        else:
            parcial = self._texto(self._rec.PartialResult())
            if parcial:
                self._fila.append(("parcial", parcial))

    @staticmethod
    def _texto(bruto: str) -> str:
        import json
        try:
            dados = json.loads(bruto)
        except Exception:
            return ""
        return str(dados.get("partial") or dados.get("text") or "").strip()

    def eventos(self) -> list:
        fila, self._fila = self._fila, []
        return fila


class MotorJanela(MotorFluxo):
    """Reserva SEM dependência nova: re-transcreve só a janela recente, a cada `passo_s`.

    `transcrever` recebe um `bytes` PCM 16 bits mono e devolve o texto — nos testes é um falso;
    no programa é o Whisper que já está carregado. A janela (8 s) limita o custo: não cresce com
    a duração da fala.
    """

    nome = "janela"

    def __init__(self, transcrever: Callable, taxa: int = 16000, janela_s: float = 8.0,
                 passo_s: float = 1.0, bytes_por_amostra: int = 2):
        self._transcrever = transcrever
        self._taxa = int(taxa)
        self._janela = max(1, int(janela_s * self._taxa)) * bytes_por_amostra
        self._passo = max(1, int(passo_s * self._taxa)) * bytes_por_amostra
        self._buf = b""
        self._desde = 0
        self._fila = []

    def alimentar(self, pcm16, taxa: int = 16000) -> None:
        if not pcm16:
            return
        self._buf = (self._buf + bytes(pcm16))[-self._janela:]
        self._desde += len(pcm16)
        if self._desde < self._passo:
            return
        self._desde = 0
        try:
            texto = str(self._transcrever(self._buf) or "").strip()
        except Exception:
            texto = ""
        if texto:
            self._fila.append(("parcial", texto))

    def eventos(self) -> list:
        fila, self._fila = self._fila, []
        return fila


# ======================================================================
# Ligação com o Corpo
# ======================================================================
class Ditado:
    """Junta motor + estado + comandos e produz as mensagens que o Corpo desenha.

    `enviar` é a função que manda o JSON pela ponte (injetada: nos testes, uma lista).
    """

    def __init__(self, motor: MotorFluxo, enviar: Callable = None, correcao: Callable = None):
        self.motor = motor
        self.enviar = enviar or (lambda msg: None)
        self.correcao = correcao
        self.estado = EstadoDitado()
        self._ultimo = ("", "")

    # ---- áudio entrando -------------------------------------------------
    def alimentar(self, pcm16, taxa: int = 16000) -> list:
        """Manda áudio ao motor e devolve as mensagens geradas (para quem não usa `enviar`)."""
        self.motor.alimentar(pcm16, taxa)
        return self.drenar()

    def drenar(self) -> list:
        mensagens = []
        for tipo, texto in self.motor.eventos():
            if tipo == "final":
                mensagens.append(self._final(texto))
                continue
            parcial = self.estado.atualizar(texto)
            if (parcial["stable"], parcial["tail"]) != self._ultimo:
                self._ultimo = (parcial["stable"], parcial["tail"])
                mensagens.append({"action": ACAO_PARCIAL, **parcial})
        for msg in mensagens:
            self.enviar(msg)
        return mensagens

    def _final(self, texto: str) -> dict:
        final = texto
        if self.correcao is not None:
            try:
                final = str(self.correcao(texto) or texto)
            except Exception:
                final = texto
        final = self.estado.finalizar(final)
        self._ultimo = ("", "")
        self.estado = EstadoDitado()
        return {"action": ACAO_FINAL, "text": final}

    def fechar(self) -> dict:
        """Termina a fala: fecha o motor e devolve o texto final (o da tela, se o motor não mandou)."""
        self.motor.fechar()
        for tipo, texto in self.motor.eventos():
            if tipo == "final" and texto:
                return self._final(texto)
        return self._final(self.estado.estavel)


def escolher_motor(transcrever: Callable = None, modelo_vosk: str = "", taxa: int = 16000) -> MotorFluxo:
    """Vosk se existir (rápido); senão a janela deslizante (sem dependência nova)."""
    if modelo_vosk:
        motor = MotorVosk.abrir(modelo_vosk, taxa)
        if motor is not None:
            return motor
    return MotorJanela(transcrever or (lambda _audio: ""), taxa=taxa)
