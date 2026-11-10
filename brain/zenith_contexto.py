"""
Zenith — Contexto da conversa: a Zenith passa a LEMBRAR do que acabou de ser dito, com qualquer IA (v22).

O problema ("ela perde o contexto, fica burra do nada, dá uma de perdida"):
  * Só o Gemini guardava a conversa (numa sessão em memória, perdida ao reiniciar, ao trocar de conversa
    ou ao cair pra outra IA).
  * OpenAI, OpenRouter, Groq, modelos locais... recebiam, a cada mensagem, SÓ o prompt do sistema e a
    pergunta atual — cada mensagem era uma conversa nova. As "memórias relevantes" ajudavam pouco.

O que isto faz: monta, a partir da conversa SALVA (config/conversations.json), o histórico que vai junto
de cada pergunta — dentro de um orçamento de tokens que depende do modo (max / equilibrado / economico)
e do tamanho de janela do perfil da IA em uso. O que não couber vira um RESUMO EXTRATIVO curto (sem gastar
chamada de IA) das mensagens mais antigas; o que couber entra INTEIRO e na ordem.

Limites honestos: tokens são estimados (~4 caracteres por token); a janela de cada modelo está nos perfis
(config/biblia/perfis_modelos.json) e é aproximada; o resumo extrativo guarda o "fio" da conversa, não os
detalhes (por isso o modo "max" deixa caber a conversa quase toda).

Só texto: nada aqui executa coisa alguma nem mexe nos pilares.
"""
from __future__ import annotations

import re

# fração da janela da IA que o HISTÓRICO pode ocupar, e teto absoluto (em tokens)
MODOS = {
    "max":         {"fracao": 0.45, "teto": 150_000, "msg_user": 12_000, "msg_ai": 10_000},
    "equilibrado": {"fracao": 0.20, "teto": 40_000,  "msg_user": 6_000,  "msg_ai": 4_000},
    "economico":   {"fracao": 0.08, "teto": 8_000,   "msg_user": 2_500,  "msg_ai": 1_500},
}
MODO_PADRAO = "max"
APELIDOS = {"maximo": "max", "máximo": "max", "máx": "max", "alto": "max", "normal": "equilibrado",
            "medio": "equilibrado", "médio": "equilibrado", "baixo": "economico", "econômico": "economico",
            "eco": "economico", "barato": "economico"}

# respostas "de sistema" que a interface guarda como se fossem da Zenith (não são conversa de verdade)
_PREFIXOS_AVISO = ("❌", "ℹ️", "🔒", "📋", "🧭", "💾", "📖", "📏", "🔧", "⏹️", "📁", "🎛️", "▶️", "⏸",
                   "📝", "🔊", "🎙️", "🔎 Não achei", "👋 Antes de começar", "🔓", "🗑️", "✅ Modo", "🆕")


def normalizar_modo(valor) -> str:
    v = str(valor or "").strip().lower()
    v = APELIDOS.get(v, v)
    return v if v in MODOS else MODO_PADRAO


def estimar_tokens(texto: str) -> int:
    return max(0, (len(texto or "") + 3) // 4)


def orcamento_tokens(perfil: dict, modo: str) -> int:
    """Tokens que o histórico pode ocupar nesta IA e neste modo."""
    m = MODOS[normalizar_modo(modo)]
    janela = int((perfil or {}).get("contexto_tokens", 32_000) or 32_000)
    return max(500, min(int(janela * m["fracao"]), m["teto"]))


def _cortar_no_meio(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    metade = max(100, limite // 2 - 20)
    return texto[:metade].rstrip() + "\n[... trecho longo cortado ...]\n" + texto[-metade:].lstrip()


def limpar(msgs: list, mensagem_atual: str = "", modo: str = MODO_PADRAO) -> list:
    """[(papel, texto)] da conversa salva, sem avisos de sistema, com cada mensagem limitada, e SEM a
    mensagem atual (a interface grava a pergunta antes de chamar a IA, então ela aparece no fim da lista)."""
    m = MODOS[normalizar_modo(modo)]
    saida = []
    for it in msgs or []:
        texto = str((it or {}).get("text", "")).strip()
        if not texto:
            continue
        papel = "user" if (it or {}).get("sender") == "user" else "assistant"
        if papel == "assistant" and texto.startswith(_PREFIXOS_AVISO):
            continue
        limite = (m["msg_user"] if papel == "user" else m["msg_ai"]) * 4
        saida.append((papel, _cortar_no_meio(texto, limite)))
    # tira a pergunta atual (última do usuário) para não duplicar
    atual = (mensagem_atual or "").strip()
    if saida and saida[-1][0] == "user":
        ultimo = saida[-1][1]
        if not atual or atual in ultimo or ultimo in atual:
            saida.pop()
    return saida


def resumo_extrativo(descartadas: list, max_chars: int = 2500) -> str:
    """Fio da conversa antiga em poucas linhas, sem chamar IA: começo de cada pergunta e de cada resposta."""
    linhas = []
    for papel, texto in descartadas:
        t = re.sub(r"\s+", " ", texto).strip()
        if not t:
            continue
        linhas.append(("Usuário: " if papel == "user" else "Você: ") + (t[:160] + ("…" if len(t) > 160 else "")))
    if not linhas:
        return ""
    # se estourar, mantém o começo e o fim (o assunto inicial e o mais recente)
    texto = "\n".join(linhas)
    if len(texto) > max_chars:
        mei = max_chars // 2
        texto = texto[:mei].rstrip() + "\n[...]\n" + texto[-mei:].lstrip()
    return texto


def montar(msgs: list, perfil: dict, modo: str = MODO_PADRAO, mensagem_atual: str = "", reservado_tokens: int = 0) -> dict:
    """Escolhe o que vai junto da pergunta. Devolve:
       {"turnos": [(papel, texto)...], "resumo": str, "descartadas": n, "tokens": n, "orcamento": n}"""
    limpas = limpar(msgs, mensagem_atual, modo)
    orcamento = max(0, orcamento_tokens(perfil, modo) - int(reservado_tokens))
    usados, escolhidos = 0, []
    for papel, texto in reversed(limpas):              # do mais novo para o mais antigo
        t = estimar_tokens(texto) + 4
        if usados + t > orcamento and escolhidos:
            break
        if usados + t > orcamento and not escolhidos:  # nem a última cabe: corta ela
            texto = _cortar_no_meio(texto, max(400, orcamento * 4))
            t = estimar_tokens(texto) + 4
        escolhidos.append((papel, texto))
        usados += t
    escolhidos.reverse()
    n_desc = len(limpas) - len(escolhidos)
    resumo = resumo_extrativo(limpas[:n_desc]) if n_desc > 0 else ""
    usados += estimar_tokens(resumo)
    return {"turnos": escolhidos, "resumo": resumo, "descartadas": n_desc, "tokens": usados, "orcamento": orcamento}


# ------------------------------------------------------------------ formatos por provedor
NOTA_RESUMO = ("[Resumo automático do começo desta conversa — o que veio depois está logo abaixo, completo. "
               "Use só como pano de fundo.]\n")


def para_openai(ctx: dict) -> list:
    """Mensagens (sem o 'system' e sem a pergunta atual) no formato dos provedores compatíveis com OpenAI."""
    saida = []
    if ctx.get("resumo"):
        saida.append({"role": "user", "content": NOTA_RESUMO + ctx["resumo"]})
        saida.append({"role": "assistant", "content": "Entendido, sigo daqui."})
    for papel, texto in ctx.get("turnos", []):
        saida.append({"role": papel, "content": texto})
    return _alternar(saida)


def para_gemini(ctx: dict) -> list:
    """[(papel, texto)] com papéis 'user'/'model' ALTERNADOS, começando por 'user' e terminando em 'model'
    (o Gemini recusa duas falas seguidas do mesmo papel e a próxima pergunta é do usuário)."""
    base = para_openai(ctx)
    pares = [("user" if m["role"] == "user" else "model", m["content"]) for m in base]
    while pares and pares[-1][0] == "user":            # pergunta sem resposta: descarta
        pares.pop()
    while pares and pares[0][0] != "user":
        pares.pop(0)
    return pares


def _alternar(msgs: list) -> list:
    """Junta falas seguidas do mesmo papel numa só (vários provedores exigem alternância)."""
    saida = []
    for m in msgs:
        if saida and saida[-1]["role"] == m["role"]:
            saida[-1] = {"role": m["role"], "content": saida[-1]["content"] + "\n\n" + m["content"]}
        else:
            saida.append(dict(m))
    return saida
