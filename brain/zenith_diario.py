"""
Zenith — Diário (/diario): a Zenith resume a conversa atual e guarda como memória
📎 (resumo), pra ter continuidade entre sessões (Pilar 5 — contexto evolutivo).

Usa a IA ativa (a conversa recente é enviada ao provedor, como em qualquer
mensagem). Chaves/senhas óbvias são mascaradas antes. Nunca levanta exceção:
devolve {"ok", "mensagem", "texto"}.
"""
import datetime

from brain import zenith_actionlog as _actionlog

MAX_CARACTERES = 12000
MAX_POR_MENSAGEM = 700
MIN_MENSAGENS_DO_USUARIO = 2


def montar_transcricao(mensagens: list, persona: str, usuario: str) -> str:
    """Pega o FIM da conversa (o mais recente importa mais) até MAX_CARACTERES."""
    linhas, total = [], 0
    for m in reversed(mensagens or []):
        texto = " ".join(str(m.get("text", "")).split())
        if not texto:
            continue
        quem = usuario if m.get("sender") == "user" else persona
        linha = f"{quem}: {_actionlog.mascarar_segredos(texto)[:MAX_POR_MENSAGEM]}"
        if total + len(linha) > MAX_CARACTERES:
            break
        linhas.append(linha)
        total += len(linha) + 1
    return "\n".join(reversed(linhas))


def montar_prompt(transcricao: str, persona: str, usuario: str) -> str:
    return (f"Escreva o DIÁRIO desta conversa, em português, em até 8 linhas, na primeira pessoa "
            f"de {persona} (quem acompanhou {usuario}). Inclua: o que foi feito ou decidido; o que "
            f"ficou pendente; preferências ou fatos novos sobre {usuario} que valem lembrar; e o "
            f"clima da conversa. Sem saudação, sem enrolação, sem inventar o que não aconteceu. "
            f"Responda SÓ com o texto do diário.\n\n[Conversa]:\n{transcricao}")


def gerar(core, memory, mensagens: list, persona: str, usuario: str, agora=None) -> dict:
    agora = agora or datetime.datetime.now()
    try:
        do_usuario = [m for m in (mensagens or []) if m.get("sender") == "user" and str(m.get("text", "")).strip()]
        if len(do_usuario) < MIN_MENSAGENS_DO_USUARIO:
            return {"ok": False, "texto": "",
                    "mensagem": "A conversa está curta demais pra um diário — converse mais um pouco."}
        transcricao = montar_transcricao(mensagens, persona, usuario)
        texto = (core._call_provider(montar_prompt(transcricao, persona, usuario)) or "").strip()
        if not texto:
            return {"ok": False, "texto": "", "mensagem": "A IA não devolveu texto — tente de novo."}
        entrada = f"📔 Diário de {agora:%d/%m/%Y %H:%M} — {texto}"
        if not memory.save_summary(entrada):
            return {"ok": False, "texto": texto, "mensagem": "Escrevi o diário mas não consegui guardar na memória."}
        return {"ok": True, "texto": texto,
                "mensagem": f"📔 Diário guardado na memória (📎 resumo):\n\n{texto}"}
    except Exception as e:
        return {"ok": False, "texto": "", "mensagem": f"Não consegui gerar o diário agora: {e}"}
