"""Zenith — QUAL MODELO usar em cada IA, e o que dizer quando uma IA falha (v1.6.1).

Por que existe (prints do Anderson, 23/10/2026: "só o Gemini funciona, as outras não"):
  * o nome do modelo de cada IA estava ESCRITO FIXO no núcleo (gpt-4o-mini, anthropic/claude-3.5-sonnet,
    meta-llama/llama-3.3-70b-instruct:free). Modelos mudam e somem: o grátis do OpenRouter acima já não existe na lista de
    grátis, o Claude 3.5 do OpenRouter é pago (e a conta dele tem US$ 0), e a OpenAI mandou o gpt-4o-mini para o
    gpt-5.4-mini. Resultado: a chave era "válida" (o teste só LISTA modelos), mas toda conversa falhava e o Zenith
    caía para o Gemini sem dizer o porquê.
  * os modelos GPT-5 da OpenAI não aceitam `max_tokens` (pedem `max_completion_tokens`) — outro erro 400 garantido.
  * o OpenRouter bloqueia os modelos grátis quando a conta não liga "free endpoints that may publish prompts"
    (erro 404 "No endpoints found matching your data policy"): a lista da conta do Anderson mostrava só 1 modelo liberado.

O que este módulo faz (lógica pura, sem rede):
  * `padrao(slot)`        — o modelo que deve funcionar numa conta GRÁTIS (o usuário pode trocar em `modelos_override`);
  * `diagnosticar(...)`   — transforma o erro cru da API numa frase em português dizendo o que aconteceu e o que fazer;
  * `escolher_modelo(...)`— dado o que a conta realmente enxerga (`models.list()`), escolhe um que funcione.
Fonte dos nomes (conferida em 23/10/2026): cheahjs/free-llm-api-resources (grátis do OpenRouter e do Groq), documentação do
OpenRouter (roteador `openrouter/free`) e a página de limites da OpenAI do próprio usuário. Mudam rápido: por isso a descoberta
automática abaixo e o `modelos_override`.
"""
from __future__ import annotations

import re

# Ordem de preferência por "slot" do Zenith. O primeiro é o padrão; os demais só entram se a conta o enxergar.
PREFERIDOS = {
    "openai": ("gpt-5.4-mini", "gpt-5-mini", "gpt-5.4-nano", "gpt-5-nano", "gpt-4o-mini"),
    # OpenRouter ("claude" e "llama" são o MESMO serviço). `openrouter/free` escolhe sozinho entre os grátis disponíveis.
    "claude": ("openrouter/free", "openai/gpt-oss-20b:free", "google/gemma-4-31b-it:free",
               "nvidia/nemotron-3-super-120b-a12b:free", "google/gemma-4-26b-a4b-it:free"),
    # O Groq DESLIGOU o llama-3.3-70b-versatile e o llama-3.1-8b-instant em 16/08/2026 (console.groq.com/docs/deprecations;
    # trocas que ele mesmo indica: gpt-oss-120b / qwen3.6-27b). Ficam por último só se a conta ainda enxergar.
    "groq": ("openai/gpt-oss-120b", "qwen/qwen3.6-27b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile",
             "llama-3.1-8b-instant"),
}
PREFERIDOS["llama"] = PREFERIDOS["claude"]

SITES = {"openai": "platform.openai.com", "claude": "openrouter.ai", "llama": "openrouter.ai", "groq": "console.groq.com",
         "gemini": "aistudio.google.com"}
NOMES = {"openai": "OpenAI", "claude": "OpenRouter", "llama": "OpenRouter", "groq": "Groq", "gemini": "Gemini"}


def grupo(slot: str) -> str:
    return "claude" if slot == "llama" else slot


def padrao(slot: str) -> str:
    """Modelo padrão do slot (vazio se o slot não é um dos fixos)."""
    lista = PREFERIDOS.get(slot) or ()
    return lista[0] if lista else ""


def _t(erro) -> str:
    return str(erro or "").lower()


# --------------------------------------------------------------------------------------------- classificação
def eh_erro_de_parametro(erro) -> bool:
    """Modelos novos da OpenAI recusam `max_tokens` (e os antigos recusam `max_completion_tokens`)."""
    t = _t(erro)
    return ("max_completion_tokens" in t or "max_tokens" in t) and ("unsupported" in t or "not supported" in t
                                                                    or "use '" in t or "instead" in t or "invalid" in t)


def eh_erro_de_politica(erro) -> bool:
    t = _t(erro)
    return "data policy" in t or "free model publication" in t or "may publish prompts" in t


def eh_limite_da_chave(erro) -> bool:
    """A chave tem um limite de gasto próprio que acabou (no OpenRouter: campo "Credit limit"; em US$ 0 ela nunca funciona)."""
    t = _t(erro)
    return any(s in t for s in ("key limit exceeded", "credit limit", "limit_remaining", "spending limit"))


def tokens_possiveis(erro):
    """'...but can only afford 1234' (OpenRouter com pouco saldo) -> 1234; senão None."""
    m = re.search(r"can only afford (\d+)", _t(erro))
    return int(m.group(1)) if m else None


def eh_erro_de_modelo(erro) -> bool:
    """O NOME do modelo não existe mais / a conta não tem acesso (trocar de chave não resolve; trocar de modelo sim)."""
    t = _t(erro)
    if eh_erro_de_politica(erro):
        return False                         # é configuração da conta, não o nome do modelo
    sinais = ("model_not_found", "model not found", "no endpoints found for", "does not exist", "decommission",
              "has been deprecated", "is deprecated", "no longer available", "unknown model", "invalid model",
              "do not have access to the model", "does not have access to model", "not available to your",
              "is not a valid model", "model_decommissioned")
    if any(s in t for s in sinais):
        return True
    return "404" in t and "model" in t


def eh_pedido_grande(erro) -> bool:
    """O pedido (personalidade + histórico + pergunta) é maior que o limite por minuto do plano grátis.

    v1.10 — log do Anderson, 28/10/2026: `413 - Request too large for model openai/gpt-oss-120b ... on tokens
    per minute (TPM): Limit 8000`. Não é saldo, não é chave e não é cota do dia: é o TAMANHO do pedido. Antes
    isso caía em "credito" e o chat dizia "Groq recusou por falta de saldo ou de cota" — mentira que mandava
    o usuário procurar crédito onde o problema era contexto. Mandar a conversa sem o histórico resolve."""
    t = _t(erro)
    # Só o que é TAMANHO. "tokens per minute" sozinho é limite de uso (429) e continua sendo "limite", que é
    # outro conselho (esperar), não cortar contexto.
    return any(s in t for s in ("request too large", "reduce the length of the messages", "reduce your message size",
                                "context_length_exceeded", "context length", "too many tokens", "413"))


def classificar(erro) -> str:
    """parametro | politica | limite_chave | modelo | contexto | credito | chave | limite | rede | outro"""
    t = _t(erro)
    if eh_erro_de_parametro(erro):
        return "parametro"
    if eh_pedido_grande(erro):
        return "contexto"
    if eh_erro_de_politica(erro):
        return "politica"
    if eh_limite_da_chave(erro):
        return "limite_chave"
    if eh_erro_de_modelo(erro):
        return "modelo"
    if any(s in t for s in ("insufficient_quota", "exceeded your current quota", "payment required", "add credits",
                            "insufficient credits", "requires more credits", "billing", "402")):
        return "credito"
    if any(s in t for s in ("401", "invalid api key", "incorrect api key", "invalid_api_key", "authentication",
                            "unauthorized", "permission_denied", "403")):
        return "chave"
    if any(s in t for s in ("429", "rate limit", "rate_limit", "too many requests", "free-models-per-day",
                            "resource_exhausted", "tokens per minute", "requests per day", "quota")):
        return "limite"
    if any(s in t for s in ("connection", "timeout", "timed out", "name resolution", "unreachable", "ssl", "503", "502",
                            "overloaded", "unavailable")):
        return "rede"
    return "outro"


def diagnosticar(slot: str, erro, modelo: str = "") -> dict:
    """{categoria, mensagem}. A mensagem é para o usuário: o que aconteceu e o que fazer, sem jargão e sem emoji."""
    g = grupo(slot)
    nome = NOMES.get(g, g or "A IA")
    cat = classificar(erro)
    m = f" (modelo {modelo})" if modelo else ""
    if cat == "parametro":
        msg = f"{nome}{m} recusou um parâmetro do pedido; o Zenith tenta o formato novo sozinho."
    elif cat == "politica":
        msg = ("o OpenRouter bloqueou os modelos grátis desta conta (política de dados). Abra openrouter.ai/settings/privacy "
               "e ligue \"Enable free endpoints that may publish prompts\"; depois teste de novo")
    elif cat == "limite_chave":
        msg = (f"{nome}: a chave tem um limite de gasto próprio que já acabou (se estiver em US$ 0, ela nunca funciona). "
               "No site, abra a chave (Settings > Keys) e apague o valor de \"Credit limit\", deixando o campo em branco")
    elif cat == "modelo":
        msg = (f"o modelo{m} não existe mais ou a sua conta não tem acesso a ele em {nome}. O Zenith procura outro sozinho; "
               "se não achar, troque com /modelo <ia> <nome-do-modelo>")
    elif cat == "contexto":
        msg = (f"o pedido ficou maior que o limite de tokens por minuto do plano grátis do {nome} (na personalidade + "
               "histórico da conversa). O Zenith repete a mesma pergunta sem o histórico; se ainda não couber, abra uma "
               "conversa nova com /nova ou use outra IA")
    elif cat == "credito":
        if g == "openai":
            msg = ("a OpenAI recusou por falta de saldo ou por limite do plano grátis (que libera só poucos pedidos por dia, "
                   "em alguns modelos). Para uso normal, coloque crédito em platform.openai.com > Billing")
        elif g == "claude":
            msg = ("o OpenRouter pediu crédito: o modelo escolhido é pago e a conta está sem saldo. Os modelos grátis "
                   "(terminam em :free) funcionam sem saldo, com limite de 50 pedidos por dia")
        else:
            msg = f"{nome} recusou por falta de saldo ou de cota"
    elif cat == "chave":
        msg = f"{nome} recusou a chave (inválida, apagada ou sem permissão). Gere outra em {SITES.get(g, 'o site do serviço')}"
    elif cat == "limite":
        msg = (f"{nome} bateu o limite de uso do plano grátis (por minuto ou por dia). Espere um pouco, use outra chave "
               "ou outra IA; o Zenith volta sozinho quando liberar")
    elif cat == "rede":
        msg = f"não consegui falar com {nome} agora (internet ou servidor fora do ar). Tente de novo em instantes"
    else:
        cru = re.sub(r"\s+", " ", str(erro or "").strip())
        msg = f"{nome} respondeu com um erro: {cru[:140]}"
    return {"categoria": cat, "mensagem": msg}


# --------------------------------------------------------------------------------------------- escolha do modelo
_RE_GPT5 = re.compile(r"^gpt-(\d+)(?:\.(\d+))?-(mini|nano)$")


def _versao_gpt(i: str) -> tuple:
    m = _RE_GPT5.match(i)
    return (int(m.group(1)), int(m.group(2) or 0), 1 if m.group(3) == "mini" else 0) if m else (0, 0, 0)


def escolher_modelo(slot: str, ids, ruim: str = "") -> str:
    """Entre os modelos que a CONTA enxerga (`ids`), o melhor para este slot, diferente de `ruim`. '' se nada serve."""
    g = grupo(slot)
    ids = [str(i) for i in (ids or []) if str(i).strip()]
    existentes = set(ids)
    for m in PREFERIDOS.get(g, ()):
        if m != ruim and (m in existentes or m == "openrouter/free" and g == "claude" and not ids):
            return m
    if g == "claude":
        gratis = sorted(i for i in ids if i.endswith(":free") and i != ruim)
        for gosto in ("gpt-oss", "gemma", "nemotron", "llama", "qwen"):
            for i in gratis:
                if gosto in i:
                    return i
        return gratis[0] if gratis else ""
    if g == "openai":
        gpt5 = sorted((i for i in ids if _RE_GPT5.match(i) and i != ruim), key=_versao_gpt, reverse=True)
        return gpt5[0] if gpt5 else ""
    if g == "groq":
        for gosto in ("gpt-oss-120b", "qwen3.6", "gpt-oss-20b", "llama-3.3-70b", "llama-3.1-8b"):
            for i in ids:
                if gosto in i and i != ruim:
                    return i
    return ""
