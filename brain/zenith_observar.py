"""
Zenith — OBSERVAÇÃO AO VIVO: ela acompanha a câmera ou a tela enquanto você trabalha (v23).

Inspiração (vídeo do Miyauti com a Shogun): ele monta um circuito de eletrônica, a IA olha a mesa pela câmera e
vai guiando — "esse fio está no pino errado". Até a v22, `<ver_camera>` e `<ver_tela>` tiravam UMA foto.

Como funciona (Pilar 1 em primeiro lugar):
  * COMEÇA só com a sua aprovação (janela mostrando tipo, intervalo, duração e um aviso de privacidade).
  * Enquanto ativo: indicador VISÍVEL no chat ("🔴 Observando…") e botão/comando de PARAR a qualquer momento
    (`/parar_observacao`, `/pausar` ou o botão no topo do chat).
  * A cada N segundos (mín. 8) tira uma foto. Se a imagem é praticamente igual à anterior, NÃO chama a IA
    (economiza cota e dinheiro). Se mudou, pergunta ao modelo; ele só fala se houver algo relevante
    (responde `[SEM_NOVIDADE]` quando não há).
  * Para sozinha depois de `minutos` (padrão 15; máx. 60) — pra continuar é preciso pedir de novo — e depois de
    3 falhas seguidas.
  * Privacidade: as fotos vão pro provedor de IA que você escolheu (nuvem, a menos que seja modelo local) —
    o texto da aprovação diz isso. Nada é gravado em disco.

A parte pesada (tirar foto, perguntar à IA, publicar no chat) entra por funções injetadas — por isso a classe é
testável sem câmera, sem rede e sem Godot.
"""
from __future__ import annotations

import io
import re
import threading
import time

INTERVALO_MIN = 8
INTERVALO_PADRAO = 20
MINUTOS_PADRAO = 15
MINUTOS_MAX = 480            # 8 h: "ela sempre olhando a webcam" (v25). Quem decide é você, na janela de aprovação
LIMIAR_MUDANCA = 6.0          # diferença média (0–255) entre duas fotos pra considerar "mudou"
SEM_NOVIDADE = "[SEM_NOVIDADE]"
MAX_FALHAS = 3

_RE_TAG = re.compile(r"<observar\b([^>]*)>(.*?)</observar>", re.S | re.I)
_RE_ATTR = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
_TIPOS = {"camera": "camera", "câmera": "camera", "cam": "camera", "webcam": "camera",
          "tela": "screen", "screen": "screen", "monitor": "screen"}
_ROTULO = {"camera": "a câmera", "screen": "a tela"}


def _int(v, padrao, minimo, maximo):
    try:
        return max(minimo, min(maximo, int(float(str(v).replace(",", ".")))))
    except (TypeError, ValueError):
        return padrao


def parse(conteudo: str, intervalo_padrao: int = INTERVALO_PADRAO, minutos_padrao: int = MINUTOS_PADRAO) -> dict:
    """{'tipo','intervalo','minutos','motivo'} a partir da etiqueta <observar tipo=".." intervalo=".." minutos="..">motivo</observar>."""
    m = _RE_TAG.search(conteudo or "")
    if not m:
        raise ValueError("etiqueta <observar tipo=\"camera\" intervalo=\"20\" minutos=\"10\">motivo</observar> incompleta")
    at = {k.lower(): (a if a is not None else b) for k, a, b in _RE_ATTR.findall(m.group(1))}
    tipo = _TIPOS.get((at.get("tipo") or "camera").strip().lower())
    if not tipo:
        raise ValueError("tipo deve ser camera ou tela")
    return {"tipo": tipo,
            "intervalo": _int(at.get("intervalo"), intervalo_padrao, INTERVALO_MIN, 600),
            "minutos": _int(at.get("minutos"), minutos_padrao, 1, MINUTOS_MAX),
            "motivo": " ".join(m.group(2).split())[:300]}


def montar_tag(tipo: str, intervalo: int, minutos: int, motivo: str = "") -> str:
    return f'<observar tipo="{tipo}" intervalo="{int(intervalo)}" minutos="{int(minutos)}">{motivo}</observar>'


def preview_text(conteudo: str) -> str:
    try:
        o = parse(conteudo)
    except ValueError as e:
        return f"[OBSERVAR] ⚠ {e}"
    n = max(1, (o["minutos"] * 60) // o["intervalo"])
    return (f"[OBSERVAR AO VIVO] {_ROTULO[o['tipo']].capitalize()}, uma foto a cada {o['intervalo']} s, por até {o['minutos']} min "
            f"(no máximo ~{n} fotos).\nMotivo: {o['motivo'] or '(não informado)'}\n{'─' * 40}\n"
            "• Eu só olho enquanto o indicador 🔴 estiver ligado; você para quando quiser (/parar_observacao, /pausar ou o botão no topo).\n"
            "• Fotos parecidas com a anterior nem são enviadas; só chamo a IA quando algo muda.\n"
            "• Privacidade: as fotos vão para a IA que você escolheu (nuvem, se não for modelo local). Nada fica salvo no disco.\n"
            "• Aprovar liga a observação; negar não faz nada.")


# ---------------------------------------------------------------- detecção de mudança
def diferenca(a_bytes: bytes, b_bytes: bytes) -> float:
    """Diferença média (0–255) entre duas fotos, em miniatura 24×24 em tons de cinza. 255 = totalmente diferentes.
    Sem a primeira foto (ou se algo falhar), devolve 255 (= trate como mudou)."""
    if not a_bytes or not b_bytes:
        return 255.0
    try:
        from PIL import Image
        def mini(b):
            return list(Image.open(io.BytesIO(b)).convert("L").resize((24, 24)).getdata())
        ma, mb = mini(a_bytes), mini(b_bytes)
        return sum(abs(x - y) for x, y in zip(ma, mb)) / len(ma)
    except Exception:
        return 255.0


def prompt_de_observacao(rotulo: str, usuario: str, motivo: str, anterior: str, conversa: str = "") -> str:
    ant = f"\nO que você comentou por último: \"{anterior[:300]}\"" if anterior else ""
    conv = f"\nConversa recente (pra você saber o que estão fazendo):\n{conversa}" if conversa else ""
    return (f"[Observação ao vivo de {rotulo} — {usuario} autorizou e pode parar quando quiser]\n"
            f"Motivo do acompanhamento: {motivo or 'ajudar no que ele estiver fazendo'}.{ant}{conv}\n"
            "Olhe a imagem e fale SÓ se houver algo relevante: algo mudou de verdade, ele precisa de ajuda, há um erro "
            "ou risco (ex.: fio no pino errado, ligação sem resistor, tensão errada, código com erro na tela) ou ele "
            "terminou uma etapa. Seja específica e curta (1–2 frases, na sua personalidade) e NÃO repita o que já disse. "
            f"Se não há nada novo/importante, responda exatamente: {SEM_NOVIDADE}\n"
            "Descreva só o que você realmente vê; se não der pra ter certeza, diga o que ajustar (luz, foco, ângulo).")


# ---------------------------------------------------------------- o observador
class Observador:
    """Laço em thread: foto -> (mudou?) -> comentar -> publicar. Todas as pontas são injetadas.

    capturar(tipo)            -> (bytes|None, erro|None)
    comentar(tipo, img, motivo, anterior) -> texto  (pode levantar exceção)
    publicar(texto)           -> mostra no chat (e fala)
    estado(ativo, tipo, info) -> avisa a interface (indicador 🔴 / botão parar)
    """

    def __init__(self, capturar, comentar, publicar, estado=None, relogio=time.time, dormir=None):
        self._capturar, self._comentar, self._publicar = capturar, comentar, publicar
        self._estado = estado or (lambda *a, **k: None)
        self._relogio = relogio
        self._parar = threading.Event()
        self._dormir = dormir or (lambda s: self._parar.wait(s))
        self._thread = None
        self.tipo = ""
        self.config = {}
        self.fotos = 0
        self.comentarios = 0
        self.motivo_parada = ""

    @property
    def ativo(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._parar.is_set())

    def iniciar(self, tipo: str, intervalo: int, minutos: int, motivo: str = "", usuario: str = "você") -> str:
        if self.ativo:
            self.parar("substituída por um novo pedido")
            if self._thread:
                self._thread.join(timeout=2)
        self.tipo = tipo
        self.config = {"tipo": tipo, "intervalo": max(INTERVALO_MIN, int(intervalo)),
                       "minutos": max(1, min(MINUTOS_MAX, int(minutos))), "motivo": motivo, "usuario": usuario}
        self.fotos = self.comentarios = 0
        self.motivo_parada = ""
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, daemon=True, name="zenith-observador")
        self._thread.start()
        c = self.config
        return (f"🔴 Observando {_ROTULO[tipo]} — uma foto a cada {c['intervalo']} s, por até {c['minutos']} min. "
                f"Pra parar: /parar_observacao (ou o botão no topo / /pausar).")

    def parar(self, motivo: str = "pedido do usuário") -> bool:
        estava = self.ativo
        self.motivo_parada = self.motivo_parada or motivo
        self._parar.set()
        return estava

    def _laco(self):
        c = self.config
        fim = self._relogio() + c["minutos"] * 60
        anterior_img, ultimo_texto, falhas = None, "", 0
        self._estado(True, c["tipo"], f"{c['minutos']} min")
        try:
            while not self._parar.is_set() and self._relogio() < fim:
                img, erro = self._capturar(c["tipo"])
                if erro or not img:
                    falhas += 1
                    if falhas >= MAX_FALHAS:
                        self.motivo_parada = f"não consegui capturar {_ROTULO[c['tipo']]}: {erro or 'imagem vazia'}"
                        break
                else:
                    self.fotos += 1
                    if anterior_img is None or diferenca(anterior_img, img) >= LIMIAR_MUDANCA:
                        try:
                            texto = (self._comentar(c["tipo"], img, c["motivo"], ultimo_texto) or "").strip()
                            falhas = 0
                            anterior_img = img
                            if texto and SEM_NOVIDADE.lower() not in texto.lower():
                                ultimo_texto = texto
                                self.comentarios += 1
                                self._publicar(texto)
                        except Exception as e:
                            falhas += 1
                            if falhas >= MAX_FALHAS:
                                self.motivo_parada = f"a IA não respondeu {MAX_FALHAS}x seguidas ({str(e)[:100]})"
                                break
                self._dormir(c["intervalo"])
        finally:
            if not self.motivo_parada:
                self.motivo_parada = f"passaram os {c['minutos']} min"
            self._parar.set()
            self._estado(False, c["tipo"], self.motivo_parada)

    def resumo(self) -> str:
        if self.ativo:
            return (f"🔴 Observando {_ROTULO.get(self.tipo, '')}: {self.fotos} foto(s), {self.comentarios} comentário(s) até agora. "
                    f"Parar: /parar_observacao")
        return "👁 Não estou observando nada agora. Pra começar: /observar camera (ou tela)."
