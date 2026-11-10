"""Zenith — SEM EMOJI no chat (v1.4).

Pedido do Anderson: interface com visual PRÓPRIO, sem emoji nem figurinha de terceiros. Os botões já usam ícones próprios
(assets/ icones); faltava o TEXTO: tanto as mensagens do programa quanto a resposta da IA vinham com emoji.

Duas camadas (as duas ligadas por padrão, desliga com `sem_emoji: false` em Configurações):
  1. o prompt pede à IA para não usar emoji;
  2. este filtro tira o que passar, na hora de MOSTRAR no chat (o que está salvo na conversa não é alterado).

Cuidados: não mexe em símbolos de ciência/typografia (→ ≤ ∑ © ™ ° ✓ e setas); se a mensagem inteira fosse só emoji, devolve
a original (balão vazio é pior); ajusta o espaço que sobra ("fim 🙂." -> "fim.").
Limite conhecido: no texto em streaming cada pedaço é filtrado separado, então um emoji DENTRO de um bloco de código mostrado
no chat também some da tela (o código criado em arquivo não é afetado).
"""
from __future__ import annotations

import re

ATIVO = True       # quem liga/desliga é o Cérebro, a partir de settings["sem_emoji"]

# faixas de emoji de verdade (figuras, rostos, bandeiras, objetos, setas coloridas, selos). Ficam de fora: matemática,
# letras, setas simples (U+2190–21FF), pontuação, ✓ ✔ ✗ ✘ e símbolos técnicos.
_EMOJI = (
    "\U0001F000-\U0001FAFF"      # emoticons, símbolos, transporte, suplementos (inclui 🌐 👁 🔴 👋 🚀 🧠)
    "\u2600-\u26FF"              # sol, aviso, raio, relógio, estrela...
    "\u2700-\u2712\u2714\u2716\u271D\u2721\u2728\u2733\u2734\u2744\u2747\u274C\u274E\u2753-\u2755\u2757\u2763\u2764\u2795-\u2797\u27A1\u27B0\u27BF"
    "\u2B05-\u2B07\u2B1B\u2B1C\u2B50\u2B55"
    "\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA"
    "\u2934\u2935\u3030\u303D\u3297\u3299"
    "\u00A9\uFE0F\u200D\u20E3"   # variação de emoji, junta-emoji, caixa numerada
)
# © vem junto só quando colado a FE0F (emoji); sozinho é símbolo normal: tratamos abaixo
_RX = re.compile(r"([ \t]?)((?:[" + _EMOJI.replace("\u00A9", "") + r"])+)([ \t]?)")
_KEYCAP = re.compile(r"([0-9#*])\uFE0F?\u20E3")
_FINAL = ".,;:!?)]}"


def _troca(m: "re.Match") -> str:
    esquerda, direita = m.group(1), m.group(3)
    resto = m.string[m.end():m.end() + 1]
    if esquerda and (resto == "" or resto == "\n" or resto in _FINAL):
        return ""                                  # "fim 🙂." / "fim 🙂"  -> "fim." / "fim"
    if esquerda and direita:
        return " "                                 # "a 🚀 b" -> "a b"
    if not esquerda:
        return ""                                  # "🌐 Título" -> "Título"   |   "ok🙂ok" -> "okok"
    return esquerda                                # "a 🚀b" -> "a b"


def remover(texto: str) -> str:
    """Tira os emoji de `texto`. Se não sobrar nada além de espaço, devolve o texto original."""
    if not texto or not isinstance(texto, str):
        return texto
    limpo = _RX.sub(_troca, _KEYCAP.sub(r"\1.", texto))
    return limpo if limpo.strip() else texto


_CAMPOS = {
    "chat_message": ("text",),
    "chat_stream_chunk": ("delta",),
    "notify": ("title", "body"),
    "chat_image": ("caption",),
    "approval_request": ("description",),
}


def limpar_mensagem(data: dict) -> dict:
    """Devolve a mensagem do Cérebro para o Corpo com os emoji dos textos removidos (cópia; não altera o original)."""
    if not ATIVO or not isinstance(data, dict):
        return data
    acao = data.get("action")
    if acao == "conversation_loaded" and isinstance(data.get("messages"), list):
        novo = dict(data)
        novo["messages"] = [dict(m, text=remover(m.get("text"))) if isinstance(m, dict) and "text" in m else m
                            for m in data["messages"]]
        return novo
    campos = _CAMPOS.get(acao)
    if not campos:
        return data
    novo = None
    for c in campos:
        v = data.get(c)
        if isinstance(v, str) and v:
            r = remover(v) if acao != "chat_stream_chunk" else _RX.sub(_troca, _KEYCAP.sub(r"\1.", v))    # pedaço de stream pode ser só um emoji
            if r != v:
                novo = novo or dict(data)
                novo[c] = r
    return novo if novo is not None else data
