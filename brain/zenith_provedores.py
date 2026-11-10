"""
Zenith — provedores de IA: catálogo OPCIONAL + visão unificada das "entradas de IA".

Por que isto existe (pedido do Anderson, v18 → v19):
  1. O painel "IAs & Chaves" mostrava TODOS os provedores de uma vez (um cartão por
     provedor, mais o formulário de IA personalizada). Agora é uma caixinha: escolhe-se
     UMA IA e só ela aparece. Este módulo monta a lista que a caixinha mostra.
  2. No modo pendrive/distribuição não pode sobrar nome de provedor, endereço (URL) nem
     dica de onde pegar chave no programa — a pessoa que receber cola o endereço e a chave
     que o provedor dela fornece. Por isso o que é "de marca" (nomes, URLs, dicas, atalhos)
     saiu do código e mora num arquivo opcional: config/provedores_catalogo.json.
     Sem o arquivo => catálogo vazio => só existe "Minhas IAs" (endereço + chave + modelo).

O que NÃO muda: o formato de gravação. As chaves continuam em gemini_key / openai_key /
openrouter_key / groq_key / tavily_api_key / custom_api_*, e as IAs personalizadas em
ai_endpoints. Este módulo só lê esses campos e devolve mudanças no mesmo formato — o
zenith_core continua lendo exatamente o que lia. (Migrar tudo para um formato único fica
para depois de este caminho ser visto rodando.)

Nada aqui importa Godot, rede ou bibliotecas pesadas.
"""
import json
import uuid
from pathlib import Path

try:
    from brain.zenith_settings import CONFIG_DIR
except Exception:                       # pragma: no cover — import isolado em teste
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

CATALOGO_ARQUIVO = Path(CONFIG_DIR) / "provedores_catalogo.json"

# Ids de "slots" que o zenith_core sabe atender, e o campo do settings.json onde cada chave
# mora. NÃO vem do catálogo de propósito: o catálogo só enfeita (nome, URL, dica) — ele
# nunca decide em qual campo do settings se escreve.
CAMPOS_SLOT = {
    "gemini": "gemini_key",
    "openai": "openai_key",
    "claude": "openrouter_key",     # "claude" = OpenRouter (também atende "llama")
    "groq": "groq_key",
}
CAMPO_SERVICO = {"tavily": "tavily_api_key"}

# Slots que precisam de URL vinda do catálogo (os outros usam o SDK com endereço padrão).
SLOTS_COM_URL = ("claude", "groq")

ATIVA_PADRAO = "gemini"
NOVO = "__novo__"                       # id reservado: "＋ Adicionar nova IA…"
_MAX_TXT = 300


class ErroProvedor(ValueError):
    """Mensagem já escrita pra mostrar ao usuário."""


# ------------------------------------------------------------------ catálogo
def catalogo_vazio() -> dict:
    return {"provedores": [], "servicos": [], "atalhos": []}


def _txt(v, limite: int = _MAX_TXT) -> str:
    return v.strip()[:limite] if isinstance(v, str) else ""


def _url_ok(u: str) -> bool:
    u = u.strip().lower()
    return u.startswith("https://") or u.startswith("http://localhost") or u.startswith("http://127.0.0.1")


def _limpar_catalogo(bruto) -> dict:
    """Aceita só o que conhecemos, com texto curto. Entrada inválida é descartada em silêncio."""
    cat = catalogo_vazio()
    if not isinstance(bruto, dict):
        return cat
    for item in bruto.get("provedores", []) if isinstance(bruto.get("provedores"), list) else []:
        if not isinstance(item, dict):
            continue
        pid = _txt(item.get("id"), 20)
        if pid not in CAMPOS_SLOT or any(p["id"] == pid for p in cat["provedores"]):
            continue
        url = _txt(item.get("url"), 200)
        cat["provedores"].append({
            "id": pid,
            "nome": _txt(item.get("nome"), 60) or pid,
            "url": url if _url_ok(url) else "",
            "modelo": _txt(item.get("modelo"), 80),
            "onde_pegar": _txt(item.get("onde_pegar"), 120),
            "dica": _txt(item.get("dica"), 400),
        })
    for item in bruto.get("servicos", []) if isinstance(bruto.get("servicos"), list) else []:
        if not isinstance(item, dict):
            continue
        sid = _txt(item.get("id"), 20)
        if sid not in CAMPO_SERVICO or any(s["id"] == sid for s in cat["servicos"]):
            continue
        cat["servicos"].append({
            "id": sid,
            "nome": _txt(item.get("nome"), 60) or sid,
            "onde_pegar": _txt(item.get("onde_pegar"), 120),
            "dica": _txt(item.get("dica"), 600),
        })
    for item in bruto.get("atalhos", []) if isinstance(bruto.get("atalhos"), list) else []:
        if not isinstance(item, dict):
            continue
        url = _txt(item.get("url"), 200)
        if not _url_ok(url):
            continue
        cat["atalhos"].append({
            "label": _txt(item.get("label"), 40) or _txt(item.get("nome"), 40),
            "nome": _txt(item.get("nome"), 60),
            "url": url,
            "modelo": _txt(item.get("modelo"), 80),
        })
        if len(cat["atalhos"]) >= 12:
            break
    return cat


def carregar_catalogo(caminho=None) -> dict:
    """Lê o catálogo opcional. Arquivo ausente/ilegível/inválido => catálogo vazio."""
    p = Path(caminho) if caminho is not None else CATALOGO_ARQUIVO
    try:
        with open(p, "r", encoding="utf-8") as f:
            return _limpar_catalogo(json.load(f))
    except (OSError, ValueError):
        return catalogo_vazio()


def url_do_slot(slot: str, catalogo=None) -> str:
    """Endereço (URL) de um slot que usa a API compatível com OpenAI (OpenRouter/Groq).
    Vazio = o catálogo não tem => o zenith_core não cria o cliente e avisa."""
    cat = catalogo if catalogo is not None else carregar_catalogo()
    if slot == "llama":
        slot = "claude"
    for p in cat["provedores"]:
        if p["id"] == slot:
            return p["url"]
    return ""


# ------------------------------------------------------------------ visão unificada
def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _tem_chave_extra(settings: dict, pid: str) -> bool:
    """v1.6.1 — chaves cadastradas pela tela "Chaves & IAs" ficam em `chaves_extras` (a principal só existe se veio do
    jeito antigo). Antes, só a principal contava: Groq/OpenAI/OpenRouter com chave válida apareciam com ⚠ ("falta chave")."""
    extras = settings.get("chaves_extras") if isinstance(settings, dict) or hasattr(settings, "get") else None
    if not isinstance(extras, dict):
        return False
    nomes = (pid, "llama") if pid == "claude" else (pid,)
    for n in nomes:
        lista = extras.get(n)
        if isinstance(lista, (list, tuple)) and any(isinstance(x, str) and x.strip() for x in lista):
            return True
    return False


def _rotulo(nome: str, configurada: bool, ativa: bool) -> str:
    return ("★ " if ativa else "") + ("✓ " if configurada else "⚠ ") + nome


def montar_entradas(settings: dict, catalogo=None) -> list:
    """Lista de 'entradas' para a caixinha do painel (e para os seletores de IA ativa).

    Cada entrada: id, nome, rotulo, origem ('catalogo'|'antiga'|'minha'|'servico'),
    eh_llm, configurada, ativa, chave, url, modelo, url_editavel, modelo_editavel,
    nome_editavel, removivel, teste_como ('' = sem teste), dica, onde_pegar.
    Ordem: IAs do catálogo → API antiga (se existir) → Minhas IAs → serviços.
    """
    cat = catalogo if catalogo is not None else carregar_catalogo()
    ativa_id = _s(settings.get("active_ai")) or ATIVA_PADRAO
    saida = []

    for p in cat["provedores"]:
        chave = _s(settings.get(CAMPOS_SLOT[p["id"]]))
        precisa_url = p["id"] in SLOTS_COM_URL
        configurada = (bool(chave) or _tem_chave_extra(settings, p["id"])) and (bool(p["url"]) if precisa_url else True)
        saida.append({
            "id": p["id"], "nome": p["nome"], "origem": "catalogo", "eh_llm": True,
            "configurada": configurada, "ativa": ativa_id == p["id"],
            "chave": chave, "url": p["url"], "modelo": p["modelo"],
            "url_editavel": False, "modelo_editavel": False, "nome_editavel": False,
            "removivel": False, "teste_como": p["id"],
            "dica": p["dica"], "onde_pegar": p["onde_pegar"],
            "aviso": ("" if (p["url"] or not precisa_url)
                      else "o catálogo não traz o endereço deste provedor"),
        })

    if _s(settings.get("custom_api_url")):
        saida.append({
            "id": "custom", "nome": "API customizada (antiga)", "origem": "antiga",
            "eh_llm": True, "configurada": True, "ativa": ativa_id == "custom",
            "chave": _s(settings.get("custom_api_key")),
            "url": _s(settings.get("custom_api_url")),
            "modelo": _s(settings.get("custom_api_model")),
            "url_editavel": True, "modelo_editavel": True, "nome_editavel": False,
            "removivel": True, "teste_como": "custom", "dica": "", "onde_pegar": "", "aviso": "",
        })

    for ep in settings.get("ai_endpoints", []) or []:
        if not isinstance(ep, dict) or not ep.get("id"):
            continue
        url, modelo = _s(ep.get("api_url")), _s(ep.get("model_name"))
        pid = f"custom:{ep['id']}"
        saida.append({
            "id": pid, "nome": _s(ep.get("name")) or "IA personalizada", "origem": "minha",
            "eh_llm": True, "configurada": bool(url and modelo), "ativa": ativa_id == pid,
            "chave": _s(ep.get("api_key")), "url": url, "modelo": modelo,
            "url_editavel": True, "modelo_editavel": True, "nome_editavel": True,
            "removivel": True, "teste_como": "new_custom", "dica": "", "onde_pegar": "",
            "aviso": "",
        })

    for s in cat["servicos"]:
        chave = _s(settings.get(CAMPO_SERVICO[s["id"]]))
        saida.append({
            "id": s["id"], "nome": s["nome"], "origem": "servico", "eh_llm": False,
            "configurada": bool(chave), "ativa": False, "chave": chave, "url": "", "modelo": "",
            "url_editavel": False, "modelo_editavel": False, "nome_editavel": False,
            "removivel": False, "teste_como": "", "dica": s["dica"],
            "onde_pegar": s["onde_pegar"], "aviso": "",
        })

    for e in saida:
        e["rotulo"] = _rotulo(e["nome"], e["configurada"], e["ativa"]) + ("" if e["eh_llm"] else "  (serviço)")
    return saida


def ids_de_ia(entradas: list) -> list:
    """Ids que podem ser 'IA ativa' (só modelos de linguagem)."""
    return [e["id"] for e in entradas if e.get("eh_llm")]


def dados_para_ui(settings: dict, catalogo=None) -> dict:
    """O que o Corpo (Godot) recebe junto das configurações. Nunca contém URL de marca
    quando o catálogo está vazio."""
    cat = catalogo if catalogo is not None else carregar_catalogo()
    return {"entradas": montar_entradas(settings, cat), "atalhos": cat["atalhos"],
            "catalogo_vazio": not (cat["provedores"] or cat["servicos"] or cat["atalhos"])}


# ------------------------------------------------------------------ edição (mudanças puras)
def _campos(c) -> tuple:
    c = c if isinstance(c, dict) else {}
    return (_txt(c.get("nome"), 60), _txt(c.get("url"), 300), _txt(c.get("chave"), 500),
            _txt(c.get("modelo"), 120))


def salvar_entrada(settings: dict, entrada_id: str, campos: dict, catalogo=None) -> dict:
    """Devolve as mudanças (no formato de sempre do settings.json) para gravar UMA entrada.
    Levanta ErroProvedor com mensagem pronta se faltar algo. Não grava nada."""
    cat = catalogo if catalogo is not None else carregar_catalogo()
    nome, url, chave, modelo = _campos(campos)
    eid = _s(entrada_id)

    if eid in CAMPOS_SLOT:
        if not any(p["id"] == eid for p in cat["provedores"]):
            raise ErroProvedor("Esta IA não existe neste catálogo.")
        return {CAMPOS_SLOT[eid]: chave}
    if eid in CAMPO_SERVICO:
        if not any(s["id"] == eid for s in cat["servicos"]):
            raise ErroProvedor("Este serviço não existe neste catálogo.")
        return {CAMPO_SERVICO[eid]: chave}
    if eid == "custom":
        if not url:
            raise ErroProvedor("Informe o endereço (URL) da API.")
        return {"custom_api_url": url, "custom_api_key": chave, "custom_api_model": modelo}

    if eid.startswith("custom:"):
        ep_id = eid.split(":", 1)[1]
        if not nome or not url or not modelo:
            raise ErroProvedor("Preciso de Nome, Endereço (URL) e Modelo pra salvar esta IA.")
        if not _url_ok(url) and not url.lower().startswith("http://"):
            raise ErroProvedor("O endereço precisa começar com https:// (ou http:// para uma IA local).")
        eps = [dict(e) for e in (settings.get("ai_endpoints", []) or []) if isinstance(e, dict)]
        for e in eps:
            if e.get("id") == ep_id:
                e.update({"name": nome, "api_url": url, "api_key": chave, "model_name": modelo})
                return {"ai_endpoints": eps}
        raise ErroProvedor("Não achei essa IA na lista (talvez já tenha sido removida).")
    raise ErroProvedor("IA desconhecida.")


def nova_endpoint(settings: dict, campos: dict) -> tuple:
    """Cria uma IA personalizada. Devolve (id_completo, mudancas)."""
    nome, url, chave, modelo = _campos(campos)
    if not nome or not url or not modelo:
        raise ErroProvedor("Pra adicionar uma IA preciso pelo menos do Nome, do Endereço (URL) e do Modelo.")
    if not (_url_ok(url) or url.lower().startswith("http://")):
        raise ErroProvedor("O endereço precisa começar com https:// (ou http:// para uma IA local).")
    novo_id = uuid.uuid4().hex[:10]
    eps = [dict(e) for e in (settings.get("ai_endpoints", []) or []) if isinstance(e, dict)]
    eps.append({"id": novo_id, "name": nome, "api_url": url, "api_key": chave, "model_name": modelo})
    return f"custom:{novo_id}", {"ai_endpoints": eps}


def proxima_ativa(settings: dict, excluir_id: str, catalogo=None) -> str:
    """Quando a IA ativa some, qual passa a ser a ativa: a primeira configurada, senão o padrão."""
    for e in montar_entradas(settings, catalogo):
        if e["eh_llm"] and e["configurada"] and e["id"] != excluir_id:
            return e["id"]
    return ATIVA_PADRAO


def remover_entrada(settings: dict, entrada_id: str, catalogo=None) -> dict:
    """Mudanças para 'remover' uma entrada: IA personalizada some; slot do catálogo e serviço
    só têm a chave apagada; a API antiga é zerada. Se era a ativa, escolhe outra."""
    eid = _s(entrada_id)
    mud = {}
    if eid in CAMPOS_SLOT:
        mud[CAMPOS_SLOT[eid]] = ""
    elif eid in CAMPO_SERVICO:
        mud[CAMPO_SERVICO[eid]] = ""
    elif eid == "custom":
        mud.update({"custom_api_url": "", "custom_api_key": "", "custom_api_model": ""})
    elif eid.startswith("custom:"):
        ep_id = eid.split(":", 1)[1]
        mud["ai_endpoints"] = [e for e in (settings.get("ai_endpoints", []) or [])
                               if isinstance(e, dict) and e.get("id") != ep_id]
    else:
        raise ErroProvedor("IA desconhecida.")
    if _s(settings.get("active_ai")) == eid:
        futuro = dict(settings)
        futuro.update(mud)
        mud["active_ai"] = proxima_ativa(futuro, eid, catalogo)
    return mud
