"""
Zenith — ROTEADOR POR CAPACIDADE: "uma IA só, com as ferramentas de todas" (v30).

O pedido do Anderson: "virar uma singularidade" — não escolher IA na mão; ela usa a API
certa para cada coisa (conversar, ver imagem/tela, criar imagem, voz, transcrever, editar
vídeo, buscar) e troca sozinha quando a atual não sabe ou está fora do ar.

O que este módulo NÃO faz: esconder do usuário para onde o conteúdo vai. Toda troca
automática vem com um aviso no chat (ver `aviso`), e nada de áudio/vídeo/transcrição
sai do PC — essas três capacidades são LOCAIS por definição no Zenith.

Capacidades de NUVEM (dependem de chave):
  texto        — conversar (Gemini, OpenAI, Claude/OpenRouter, Groq, personalizadas, local)
  visao        — entender imagem/anexo/foto da câmera (Gemini, OpenAI, Claude/OpenRouter;
                 personalizadas/local só se o usuário marcar que o modelo delas vê imagem)
  imagem       — CRIAR imagem por IA (hoje só o modelo de imagem do Gemini)

Capacidades LOCAIS (não usam chave, não saem do computador):
  voz          — Edge-TTS/RVC (a síntese em si é na nuvem da Microsoft quando não é RVC)
  transcricao  — faster-whisper no seu PC
  video        — ffmpeg no seu PC
  busca        — buscadores públicos (+ Tavily se houver chave)

A ordem é: a IA ATIVA primeiro (se ela souber fazer), depois a preferida do usuário
(settings["rota_preferida"]), depois as outras; a IA local fica por último quando o papel
dela é "reserva" (padrão) — ela é o Megazord que entra quando a nuvem falha, não a que
rouba a vez.

Lógica pura: nenhuma rede, nenhuma SDK. Testável.
"""
from __future__ import annotations

CAPACIDADES = ("texto", "visao", "imagem", "voz", "transcricao", "video", "busca")

NOMES_CAP = {
    "texto": "conversar",
    "visao": "ver imagens/tela",
    "imagem": "criar imagem",
    "voz": "falar",
    "transcricao": "transcrever sua fala",
    "video": "editar/criar vídeo",
    "busca": "buscar na web",
}

LOCAIS = {"voz": "voz (Edge-TTS/RVC)", "transcricao": "transcrição (Whisper no seu PC)",
          "video": "vídeo (ffmpeg no seu PC)", "busca": "busca (buscadores públicos)"}

# O que cada slot sabe fazer SEM configuração extra. Conservador de propósito: prometer
# visão que o modelo não tem dá erro confuso no meio da conversa.
PADRAO = {
    "gemini": {"texto", "visao", "imagem"},
    "openai": {"texto", "visao"},
    "claude": {"texto", "visao"},
    "llama": {"texto", "visao"},
    "groq": {"texto"},
    "custom": {"texto"},
    "local": {"texto"},
}

ORDEM = ("gemini", "openai", "claude", "llama", "groq", "custom", "local")


def _get(obj, chave, padrao=None):
    if obj is None:
        return padrao
    if hasattr(obj, "get"):
        try:
            v = obj.get(chave, padrao)
            return padrao if v is None else v
        except TypeError:
            pass
    if isinstance(obj, dict):
        v = obj.get(chave, padrao)
        return padrao if v is None else v
    return padrao


def _base(prov: str) -> str:
    """'custom:abc' -> 'custom'; 'llama' -> 'llama'."""
    p = str(prov or "")
    return "custom" if p.startswith("custom:") else p


def rotulos(settings=None) -> dict:
    """provider_id -> nome bonito (personalizadas usam o nome que o usuário deu)."""
    from brain.zenith_chaves import nome_do_provedor
    out = {}
    for p in ORDEM:
        out[p] = nome_do_provedor(p, settings)
    for ep in (_get(settings, "ai_endpoints", []) or []):
        if isinstance(ep, dict) and ep.get("id"):
            pid = f"custom:{ep['id']}"
            out[pid] = str(ep.get("name") or "IA personalizada")
    return out


def rotulo(prov: str, settings=None) -> str:
    return rotulos(settings).get(prov) or prov


def capacidades(prov: str, settings=None) -> set:
    """O que ESTE provedor sabe fazer, já com os ajustes do usuário.

    settings["ia_capacidades"] = {"custom:abc": ["texto", "visao"], "openai": ["texto"]}
    serve para (a) marcar visão numa IA personalizada/local que tem modelo multimodal e
    (b) tirar uma capacidade que o usuário não quer usar naquela IA.
    """
    p = str(prov or "")
    caps = set(PADRAO.get(_base(p), {"texto"}))
    ajustes = _get(settings, "ia_capacidades", {}) or {}
    if isinstance(ajustes, dict):
        for chave in (p, _base(p)):
            valor = ajustes.get(chave)
            if isinstance(valor, (list, tuple, set)):
                caps = {str(c).strip().lower() for c in valor if str(c).strip()}
                break
    return {c for c in caps if c in CAPACIDADES}


def pode(prov: str, capacidade: str, settings=None) -> bool:
    return capacidade in capacidades(prov, settings)


def papel_local(settings=None) -> str:
    """'reserva' (padrão: entra quando a nuvem falha) | 'principal' (primeiro da fila)."""
    p = str(_get(settings, "ia_local_papel", "reserva") or "reserva").strip().lower()
    return p if p in ("reserva", "principal") else "reserva"


def escolher(capacidade: str, disponiveis, preferido: str = "", settings=None) -> list:
    """Ordem de quem pode atender `capacidade`. Nunca inclui quem não tem a capacidade.

    Regras de ordem:
      1. `preferido` (a IA ativa) — o usuário manda; se ela não souber, cai fora naturalmente.
      2. settings["rota_preferida"][capacidade], se configurado.
      3. a ordem estável do projeto (Gemini, OpenAI, Claude, ...).
      4. IA local por último quando o papel dela é "reserva" (padrão).
    """
    cap = str(capacidade or "").strip().lower()
    vivos = [p for p in (disponiveis or []) if p]
    capazes = [p for p in vivos if pode(p, cap, settings)]
    prefs = _get(settings, "rota_preferida", {}) or {}
    pref_cap = str(prefs.get(cap) or "") if isinstance(prefs, dict) else ""

    def chave(p):
        try:
            base = ORDEM.index(_base(p))
        except ValueError:
            base = len(ORDEM) - 1
        if p == preferido:
            return (-10, 0, base)
        if pref_cap and p == pref_cap:
            return (-9, 0, base)
        if _base(p) == "local" and papel_local(settings) == "reserva":
            return (5, 0, base)
        return (0, 0, base)

    return sorted(capazes, key=chave)


def melhor_para(capacidade: str, disponiveis, preferido: str = "", settings=None) -> str:
    ordem = escolher(capacidade, disponiveis, preferido, settings)
    return ordem[0] if ordem else ""


def precisa_trocar(capacidade: str, atual: str, disponiveis, settings=None) -> str:
    """Devolve o provedor que deve atender (pode ser o mesmo). '' = ninguém sabe fazer."""
    if pode(atual, capacidade, settings):
        return atual
    return melhor_para(capacidade, disponiveis, atual, settings)


def aviso(capacidade: str, de: str, para: str, settings=None) -> str:
    """Frase honesta para o chat quando a rota muda sozinha (nunca silenciosa)."""
    if not para or para == de:
        return ""
    nome_de = rotulo(de, settings) if de else "a IA anterior"
    nome_para = rotulo(para, settings)
    if capacidade == "visao":
        return f"👁 *Para ver a imagem eu usei {nome_para} — {nome_de} não faz visão.*\n\n"
    if capacidade == "texto":
        return f"⚠️ *{nome_de} não respondeu agora — continuei com {nome_para}.*\n\n"
    return f"🔀 *Para {NOMES_CAP.get(capacidade, capacidade)} usei {nome_para}.*\n\n"


def mapa(disponiveis, settings=None) -> dict:
    """{capacidade: [provedores na ordem] } + locais marcadas como sempre disponíveis."""
    vivos = list(disponiveis or [])
    out = {}
    for cap in CAPACIDADES:
        if cap in LOCAIS:
            out[cap] = []                                # roda no PC: não escolhe provedor
        else:
            out[cap] = escolher(cap, vivos, _get(settings, "active_ai", "") or "", settings)
    return out


def texto_mapa(disponiveis, settings=None) -> str:
    """Relatório em português pro comando /rota."""
    vivos = list(disponiveis or [])
    nomes = rotulos(settings)
    linhas = ["🧠 Uma IA só, com as ferramentas de todas (v30):"]
    ativa = str(_get(settings, "active_ai", "") or "")
    if vivos:
        linhas.append(f"• IA ativa: {nomes.get(ativa, ativa or '—')}")
    else:
        linhas.append("• IA ativa: NENHUMA (sem chave configurada)")

    for cap in ("texto", "visao", "imagem"):
        ordem = escolher(cap, vivos, ativa, settings)
        if ordem:
            seta = " → ".join(_curto(nomes.get(p, p)) for p in ordem)
            linhas.append(f"• {NOMES_CAP[cap].capitalize()}: {seta}")
        elif cap == "imagem":
            linhas.append("• Criar imagem: nenhuma IA com modelo de imagem configurada (hoje é o Gemini)")
        else:
            linhas.append(f"• {NOMES_CAP[cap].capitalize()}: ninguém disponível")

    linhas.append("• No seu PC (não usam chave, não saem daqui): " +
                  ", ".join(LOCAIS[c] for c in ("transcricao", "video", "busca", "voz")))
    local_ativa = str(_get(settings, "ia_local_ativa", False)).lower() in ("true", "1", "sim")
    if "local" in vivos:
        linhas.append(f"• IA local: ligada como {papel_local(settings)} (modelo {_get(settings, 'ia_local_modelo', '') or '—'})")
    elif local_ativa:
        linhas.append("• IA local: marcada como ligada, mas o servidor local não respondeu — veja /local")
    else:
        linhas.append("• IA local: desligada — /local para ligar (roda no seu PC, sem chave, mais lenta)")
    linhas.append("\nA troca automática avisa no chat. Para forçar uma preferência: /rota visao <nome-do-provedor> "
                  "(ou /rota limpar).")
    return "\n".join(linhas)


def _curto(nome: str) -> str:
    n = str(nome or "")
    return n.replace("OpenRouter/", "").replace(" (no seu PC)", "").replace("API personalizada", "personalizada")


def definir_preferencia(settings, capacidade: str, provedor: str = "") -> dict:
    """Grava (ou limpa) a preferência de rota. Só em resposta a um comando do usuário."""
    prefs = dict(_get(settings, "rota_preferida", {}) or {})
    cap = str(capacidade or "").strip().lower()
    if cap in ("limpar", "padrao", "auto"):
        settings.update({"rota_preferida": {}})
        return {"ok": True, "mensagem": "🔀 Preferências de rota limpas — vale a ordem automática (IA ativa primeiro)."}
    if cap not in CAPACIDADES or cap in LOCAIS:
        return {"ok": False, "mensagem": f"Capacidade inválida. Use: {', '.join(c for c in CAPACIDADES if c not in LOCAIS)}."}
    p = str(provedor or "").strip()
    if not p:
        prefs.pop(cap, None)
        settings.update({"rota_preferida": prefs})
        return {"ok": True, "mensagem": f"🔀 {NOMES_CAP[cap].capitalize()}: preferência removida."}
    prefs[cap] = p
    settings.update({"rota_preferida": prefs})
    return {"ok": True, "mensagem": f"🔀 {NOMES_CAP[cap].capitalize()} passa a preferir {rotulo(p, settings)}."}
