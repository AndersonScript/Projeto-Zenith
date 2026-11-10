"""
Zenith — VÁRIAS CHAVES DA MESMA IA, com troca automática (v30).

O que o Anderson pediu, com estas palavras: "infinitas APIs da mesma IA" — não quer
parar a conversa porque a chave do Gemini estourou a cota do dia, nem ficar trocando
de IA na mão. Este módulo guarda N chaves por provedor, usa sempre a próxima livre e
põe a chave problemática de QUARENTENA por um tempo, em vez de tentar de novo a cada
mensagem.

Regras que este arquivo respeita:
  * Não inventa nada no settings.json: as chaves moram onde sempre moraram
    (gemini_key, openai_key, openrouter_key, groq_key, custom_api_*). As EXTRAS ficam
    em settings["chaves_extras"] = {"gemini": ["...", "..."], ...} ou num arquivo
    opcional config/chaves.txt, uma por linha ("gemini = AIza..."). A chave
    principal continua valendo e é a primeira da fila.
  * Nada de chave em log/estado: o arquivo de quarentena guarda só um HASH curto e
    os últimos 4 caracteres. O relatório também mostra só os últimos 4.
  * Estado é passageiro (config/chaves_estado.json): se apagar, nada quebra — só
    esquece que uma chave estava de castigo.

Como a troca funciona:
  * cota/limite (429, RESOURCE_EXHAUSTED, "quota exceeded") -> 15 min de castigo
    (1 h se já falhou 3+ vezes; cota diária não volta em 15 min, mas tentar de novo
    uma vez por hora é barato).
  * chave inválida/sem permissão (401/403, "API key not valid") -> 24 h.
  * instabilidade/sobrecarga/timeout -> 20 s (pode ser passageiro).
  * erro de modelo/conteúdo NÃO castiga a chave: o problema não é ela.

Sem rede e sem SDK aqui: lógica pura, testável.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

try:
    from brain.zenith_settings import CONFIG_DIR
except Exception:                                  # pragma: no cover — import isolado em teste
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

ARQUIVO_PADRAO = Path(CONFIG_DIR) / "chaves.txt"
ESTADO_PADRAO = Path(CONFIG_DIR) / "chaves_estado.json"

MAX_CHAVES = 20                 # por provedor (é "infinitas" na prática, sem virar lixo)
MAX_TAMANHO_CHAVE = 400

TEMPO_ESPERA = {                # segundos de quarentena
    "cota": 15 * 60,
    "invalida": 24 * 60 * 60,
    "instavel": 20,
    "outro": 5,
}

# Nome só para MOSTRAR (nada de URL nem dica de onde comprar chave aqui — a regra do
# modo pendrive continua valendo; quem compra/onde compra está no catálogo opcional).
NOMES = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "claude": "OpenRouter/Claude",
    "llama": "OpenRouter/Llama",
    "groq": "Groq",
    "custom": "API personalizada",
    "local": "IA local (no seu PC)",
}

# Onde a chave PRINCIPAL de cada slot mora no settings.json.
_CAMPO = {
    "gemini": "gemini_key",
    "openai": "openai_key",
    "claude": "openrouter_key",
    "llama": "openrouter_key",
    "groq": "groq_key",
    "custom": "custom_api_key",
}


def _get(obj, chave, padrao=None):
    """Aceita ZenithSettings OU dict (os testes usam dict)."""
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


def normalizar_provedor(nome: str) -> str:
    """'Gemini ' / 'openrouter' / 'custom:abc' -> id canônico usado no resto do código."""
    p = str(nome or "").strip().lower()
    p = {"openrouter": "claude", "anthropic": "claude", "gpt": "openai"}.get(p, p)
    if p.startswith("custom:") or p == "custom":
        return p
    return p if p in _CAMPO or p == "local" else ""


def mascarar(chave: str) -> str:
    """'AIzaSy...9f2e' -> '••••9f2e' (nunca mostra a chave inteira)."""
    s = str(chave or "")
    if not s:
        return "(vazia)"
    if len(s) <= 4:
        return "••••"
    return "••••" + s[-4:]


def _hash(chave: str) -> str:
    """Impressão digital curta da chave (não dá pra voltar pra chave a partir dela)."""
    return hashlib.sha256(str(chave).encode("utf-8")).hexdigest()[:12]


def _limpar(valor) -> str:
    s = str(valor or "").strip().strip('"').strip("'").strip()
    if not s or s.lower().startswith("#"):
        return ""
    if len(s) > MAX_TAMANHO_CHAVE:
        return ""
    return s


# ------------------------------------------------------------------ arquivo opcional
def ler_arquivo(caminho=None) -> dict:
    """config/chaves.txt -> {"gemini": [...], ...}. Linhas: 'gemini = AIza...' (ou só a chave,
    que vai para o provedor padrão 'gemini'). '#' no começo é comentário. Duplicada é ignorada."""
    caminho = Path(caminho) if caminho else ARQUIVO_PADRAO
    saida = {}
    try:
        texto = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return saida
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if "=" in linha:
            prov, _, valor = linha.partition("=")
        elif ":" in linha and not linha.startswith("AIza") and linha.count(":") == 1:
            prov, _, valor = linha.partition(":")
        else:
            prov, valor = "gemini", linha
        prov = normalizar_provedor(prov)
        chave = _limpar(valor)
        if not prov or not chave:
            continue
        lista = saida.setdefault(prov, [])
        if chave not in lista and len(lista) < MAX_CHAVES:
            lista.append(chave)
    return saida


def classificar_motivo(erro) -> str:
    """Erro técnico -> 'cota' | 'invalida' | 'instavel' | 'modelo' | 'outro'.

    'modelo' existe para NÃO castigar a chave quando o problema é o nome do modelo ou
    o conteúdo bloqueado (aí o certo é tentar outro modelo, não outra chave)."""
    t = str(erro or "").lower()
    # v1.6.1 (complemento) — modelo desligado/sem acesso NÃO é culpa da chave (a OpenAI devolve 403 nesse caso e isso
    # punia a chave por 24 h). Vem antes de "chave inválida". Sem saldo/limite de gasto = cota (tentar já não adianta).
    if any(s in t for s in ("decommissioned", "model_not_found", "does not have access to model",
                            "no endpoints found", "has been deprecated")):
        return "modelo"
    if any(s in t for s in ("insufficient credits", "requires more credits", "can only afford",
                            "payment required", "error code: 402", "key limit exceeded", "credit limit")):
        return "cota"
    if any(s in t for s in ("quota exceeded", "insufficient_quota", "exceeded your current quota",
                            "resource_exhausted", "resource exhausted", "rate limit", "rate_limit",
                            "too many requests", "free_tier", "free tier", "per day", "daily limit",
                            "cota", "limite de uso")):      # mensagens já traduzidas em português
        return "cota"
    if any(s in t for s in ("api key not valid", "api_key_invalid", "invalid api key", "invalid_api_key",
                            "incorrect api key", "unauthorized", "permission_denied", "permission denied",
                            "401", "403", "authentication")):
        return "invalida"
    if any(s in t for s in ("429", "503", "502", "504", "unavailable", "overloaded", "high demand",
                            "timeout", "timed out", "connection", "temporarily")):
        return "instavel"
    if any(s in t for s in ("model", "not found", "404", "safety", "blocked", "content")):
        return "modelo"
    return "outro"


class Rotador:
    """Fila de chaves por provedor. Thread-safe o suficiente (lock curto) e persistente
    só no que importa: quem está de castigo e por quanto tempo."""

    def __init__(self, settings=None, arquivo=None, estado=None, relogio=None):
        self.settings = settings
        self.arquivo = Path(arquivo) if arquivo else ARQUIVO_PADRAO
        self.estado_path = Path(estado) if estado else ESTADO_PADRAO
        self._relogio = relogio or time.time
        self._ptr = {}
        self._memoria = {}          # provedor -> {hash: {"falhas","ate","motivo"}}
        try:
            import threading
            self._lock = threading.Lock()
        except Exception:           # pragma: no cover
            self._lock = None
        self._carregar()

    # ---------------- estado persistido
    def _carregar(self):
        try:
            dados = json.loads(self.estado_path.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                agora = self._relogio()
                for prov, itens in dados.items():
                    if not isinstance(itens, dict):
                        continue
                    for h, info in itens.items():
                        if isinstance(info, dict) and float(info.get("ate", 0) or 0) > agora:
                            self._memoria.setdefault(prov, {})[h] = {
                                "falhas": int(info.get("falhas", 1) or 1),
                                "ate": float(info.get("ate", 0) or 0),
                                "motivo": str(info.get("motivo", "") or ""),
                            }
        except (OSError, ValueError, TypeError):
            self._memoria = {}

    def _salvar(self):
        dados = {p: dict(itens) for p, itens in self._memoria.items() if itens}
        try:
            self.estado_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.estado_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(dados, indent=1, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.estado_path)
        except OSError:
            pass                    # estado é conveniência: não pode derrubar a conversa

    # ---------------- quais são as chaves
    def chaves(self, provedor: str) -> list:
        prov = normalizar_provedor(provedor)
        if not prov or prov == "local":
            return []
        lista = []
        principal = _limpar(_get(self.settings, _CAMPO.get(prov, ""), ""))
        if prov.startswith("custom:") and not principal:
            alvo = prov.split(":", 1)[1]
            for ep in (_get(self.settings, "ai_endpoints", []) or []):
                if isinstance(ep, dict) and str(ep.get("id", "")) == alvo:
                    principal = _limpar(ep.get("api_key"))
                    break
        if principal:
            lista.append(principal)
        extras = _get(self.settings, "chaves_extras", {}) or {}
        if isinstance(extras, dict):
            for k in extras.get(prov, []) or []:
                chave = _limpar(k)
                if chave and chave not in lista and len(lista) < MAX_CHAVES:
                    lista.append(chave)
        for chave in ler_arquivo(self.arquivo).get(prov, []):
            if chave not in lista and len(lista) < MAX_CHAVES:
                lista.append(chave)
        return lista

    def recarregar(self, settings=None):
        if settings is not None:
            self.settings = settings
        self._carregar()

    def _info(self, provedor: str, chave: str) -> dict:
        return self._memoria.get(provedor, {}).get(_hash(chave), {})

    def disponivel(self, provedor: str, chave: str) -> bool:
        info = self._info(provedor, chave)
        return not info or float(info.get("ate", 0) or 0) <= self._relogio()

    def _livres(self, provedor: str) -> list:
        return [(i, c) for i, c in enumerate(self.chaves(provedor)) if self.disponivel(provedor, c)]

    def tem_alguma(self, provedor: str) -> bool:
        return bool(self.chaves(provedor))

    def alguma_livre(self, provedor: str) -> bool:
        return bool(self._livres(provedor))

    def proxima(self, provedor: str):
        """(chave, índice) da próxima livre, em rodízio. (None, -1) se todas estão de castigo."""
        prov = normalizar_provedor(provedor)
        livres = self._livres(prov)
        if not livres:
            return None, -1
        with (self._lock or _Nulo()):
            i = self._ptr.get(prov, 0) % len(livres)
            self._ptr[prov] = i + 1
            return livres[i][1], livres[i][0]

    def chave_para(self, provedor: str) -> str:
        """Só a chave (usada por quem não tem cliente próprio, ex.: gerar imagem)."""
        return self.proxima(provedor)[0] or ""

    # ---------------- castigo / perdão
    def marcar_ok(self, provedor: str, chave: str):
        prov = normalizar_provedor(provedor)
        with (self._lock or _Nulo()):
            itens = self._memoria.get(prov, {})
            h = _hash(chave)
            if h in itens:
                itens.pop(h, None)
                if not itens:
                    self._memoria.pop(prov, None)
                self._salvar()

    def marcar_erro(self, provedor: str, chave: str, erro) -> str:
        """Classifica o erro e põe a chave de castigo (se for culpa dela). Devolve o motivo."""
        prov = normalizar_provedor(provedor)
        motivo = classificar_motivo(erro)
        if motivo == "modelo" or not prov or not chave:
            return motivo
        agora = self._relogio()
        h = _hash(chave)
        with (self._lock or _Nulo()):
            itens = self._memoria.setdefault(prov, {})
            info = itens.get(h) or {"falhas": 0, "ate": 0, "motivo": ""}
            info["falhas"] = int(info.get("falhas", 0) or 0) + 1
            espera = TEMPO_ESPERA.get(motivo, TEMPO_ESPERA["outro"])
            if motivo == "cota" and info["falhas"] >= 3:
                espera = 60 * 60
            info["ate"] = agora + espera
            info["motivo"] = motivo
            itens[h] = info
            self._salvar()
        return motivo

    def esquecer_castigos(self):
        with (self._lock or _Nulo()):
            self._memoria = {}
            self._salvar()

    # ---------------- relatório (para o chat)
    def resumo(self) -> list:
        linhas = []
        provs = set(_CAMPO) | set((_get(self.settings, "chaves_extras", {}) or {}).keys() if isinstance(
            _get(self.settings, "chaves_extras", {}), dict) else set())
        for ep in (_get(self.settings, "ai_endpoints", []) or []):
            if isinstance(ep, dict) and ep.get("id"):
                provs.add(f"custom:{ep['id']}")
        for prov in sorted(provs):
            chaves = self.chaves(prov)
            if not chaves:
                continue
            agora = self._relogio()
            livres, presas = 0, []
            for c in chaves:
                info = self._info(prov, c)
                if info and float(info.get("ate", 0) or 0) > agora:
                    presas.append({"chave": mascarar(c), "faltam_s": int(float(info["ate"]) - agora),
                                   "motivo": info.get("motivo", ""), "falhas": info.get("falhas", 1)})
                else:
                    livres += 1
            linhas.append({"provedor": prov, "nome": nome_do_provedor(prov, self.settings),
                           "total": len(chaves), "livres": livres, "presas": presas,
                           "chaves": [mascarar(c) for c in chaves]})
        return linhas

    def texto_relatorio(self) -> str:
        linhas = self.resumo()
        if not linhas:
            return ("🔑 Nenhuma chave cadastrada ainda.\n"
                    "Para somar chaves da MESMA IA (troca automática quando uma estoura a cota):\n"
                    "• /chave add gemini A_SUA_CHAVE_AQUI  (repita com as outras)\n"
                    "ou junte todas em config/chaves.txt, uma por linha: gemini = AIza...")
        out = ["🔑 Chaves por IA — a Zenith troca sozinha quando uma estoura:"]
        for item in linhas:
            presas = item["presas"]
            extra = ""
            if presas:
                p = presas[0]
                falta = _tempo_curto(p["faltam_s"])
                extra = f" · {len(presas)} em espera (a 1ª volta em {falta}: {p['motivo']})"
            out.append(f"• {item['nome']}: {item['total']} chave(s), {item['livres']} livre(s){extra}")
            out.append("   " + ", ".join(item["chaves"]))
        return "\n".join(out)


class _Nulo:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _tempo_curto(segundos: int) -> str:
    s = max(0, int(segundos))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}min"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def nome_do_provedor(prov: str, settings=None) -> str:
    prov = str(prov or "")
    if prov.startswith("custom:"):
        alvo = prov.split(":", 1)[1]
        for ep in (_get(settings, "ai_endpoints", []) or []):
            if isinstance(ep, dict) and str(ep.get("id", "")) == alvo:
                return str(ep.get("name") or "IA personalizada")
        return "IA personalizada"
    return NOMES.get(prov, prov.capitalize())


def adicionar_chave(settings, provedor: str, chave: str) -> dict:
    """Soma uma chave EXTRA no settings (só quando o usuário pediu, via /chave add).
    Devolve {"ok", "mensagem", "total"}. Nunca imprime a chave."""
    prov = normalizar_provedor(provedor)
    valor = _limpar(chave)
    if not prov:
        return {"ok": False, "mensagem": "Não conheço esse provedor. Use: gemini, openai, claude, groq ou custom:<id>."}
    if prov == "local":
        return {"ok": False, "mensagem": "IA local não usa chave."}
    if not valor:
        return {"ok": False, "mensagem": "Chave vazia."}
    atual = _get(settings, "chaves_extras", {}) or {}
    if not isinstance(atual, dict):
        atual = {}
    lista = [x for x in (atual.get(prov) or []) if _limpar(x)]
    principal = _limpar(_get(settings, _CAMPO.get(prov, ""), ""))
    if valor == principal or valor in lista:
        return {"ok": False, "mensagem": "Essa chave já está cadastrada.", "total": len(lista) + (1 if principal else 0)}
    if len(lista) >= MAX_CHAVES:
        return {"ok": False, "mensagem": f"Já são {MAX_CHAVES} chaves nesse provedor — apague alguma antes."}
    lista.append(valor)
    novo = dict(atual)
    novo[prov] = lista
    settings.update({"chaves_extras": novo})
    total = len(lista) + (1 if principal else 0)
    return {"ok": True, "total": total,
            "mensagem": f"✅ Chave {mascarar(valor)} somada ao {nome_do_provedor(prov, settings)}. "
                        f"Agora são {total} — quando uma estourar a cota, a próxima entra sozinha."}


# ============================================================================ v1.0 — contrato da TELA
def link_para_pegar_chave(provedor: str, settings=None) -> dict:
    """Onde pegar a chave, para a página de Configurações mostrar o botão "como conseguir".

    Lido do catálogo opcional (`config/provedores_catalogo.json`). Sem o catálogo (modo pendrive)
    devolve vazio — a página continua funcionando, só sem o link. Nada de chave aqui: só texto.
    """
    prov = normalizar_provedor(provedor)
    base = prov.split(":", 1)[0]
    try:
        import json
        from brain.zenith_settings import CONFIG_DIR
        dados = json.loads((Path(CONFIG_DIR) / "provedores_catalogo.json").read_text(encoding="utf-8"))
        for item in dados.get("provedores", []) + dados.get("servicos", []):
            if str(item.get("id", "")).lower() == base:
                return {"onde": str(item.get("onde_pegar", "")),
                        "dica": str(item.get("dica", "")),
                        "gratis": bool(item.get("gratis", base in ("gemini", "groq", "claude")))}
    except Exception:
        pass
    return {}


def estado_para_tela(settings, rotador=None) -> dict:
    """Estado completo para a página **Chaves** do Godot (contrato combinado na v1.0/A8).

    Tudo com a chave MASCARADA (`••••1234`) — a tela nunca recebe uma chave inteira; quem
    adiciona uma nova manda o valor e recebe só a confirmação. Devolve:

        {"provedores": [{"id", "nome", "chaves": [{"idx", "mascara", "principal", "estado", "segundos", "motivo"}]}],
         "rota": {...}, "ia_local": {"ligada", "modelo", "papel"}, "como_obter": {id: {...}}}
    """
    rot = rotador or Rotador(settings)
    agora = rot._relogio()
    provs = set(_CAMPO)
    extras = _get(settings, "chaves_extras", {}) or {}
    if isinstance(extras, dict):
        provs |= set(extras.keys())
    for ep in (_get(settings, "ai_endpoints", []) or []):
        if isinstance(ep, dict) and ep.get("id"):
            provs.add(f"custom:{ep['id']}")

    provedores, como_obter = [], {}
    for prov in sorted(provs):
        if prov == "local":
            continue
        chaves = rot.chaves(prov)
        if not chaves and prov != "gemini":      # a tela sempre mostra o Gemini (é o do plano grátis)
            continue
        itens = []
        for i, c in enumerate(chaves):
            info = rot._info(prov, c)
            presa = bool(info) and float(info.get("ate", 0) or 0) > agora
            motivo = str(info.get("motivo", "")) if presa else ""
            itens.append({"idx": i, "mascara": mascarar(c), "principal": i == 0,
                          "estado": ("invalida" if presa and motivo == "invalida" else ("castigo" if presa else "livre")),
                          "segundos": int(max(0, float(info.get("ate", 0) or 0) - agora)) if presa else 0,
                          "motivo": motivo})
        provedores.append({"id": prov, "nome": nome_do_provedor(prov, settings), "chaves": itens})
        info = link_para_pegar_chave(prov, settings)
        if info:
            como_obter[prov] = info

    try:
        from brain import zenith_rota as rota_mod
        mapa = rota_mod.mapa(_provedores_com_chave(rot), settings)
    except Exception:
        mapa = {}
    try:
        from brain import zenith_ia_local as local_mod
        local = local_mod.detectar(settings, timeout=0.6)
        from brain import zenith_rota as _rota
        ia_local = {"ligada": bool(_get(settings, "ia_local_ligada", False)),
                    "modelo": local_mod.modelo_escolhido(settings, local) if local else "",
                    "papel": _rota.papel_local(settings),
                    "servidor": (local or {}).get("tipo", "")}
    except Exception:
        ia_local = {"ligada": bool(_get(settings, "ia_local_ligada", False)),
                    "modelo": str(_get(settings, "ia_local_modelo", "")), "papel": "reserva", "servidor": ""}

    return {"provedores": provedores, "rota": mapa, "ia_local": ia_local, "como_obter": como_obter,
            "versao_contrato": 1}


def _provedores_com_chave(rot) -> list:
    """Ids dos provedores que TÊM pelo menos uma chave (é o que o mapa /rota mostra)."""
    return sorted(prov for prov in _CAMPO if rot.tem_alguma(prov))


def remover_chave(settings, provedor: str, indice: int) -> dict:
    """Remove a chave EXTRA de número `indice` (1 = primeira extra; 0 é a principal do settings,
    que se apaga na tela de Configurações)."""
    prov = normalizar_provedor(provedor)
    atual = _get(settings, "chaves_extras", {}) or {}
    lista = [_limpar(x) for x in (atual.get(prov) or []) if _limpar(x)]
    if not prov or not lista:
        return {"ok": False, "mensagem": "Não há chave extra nesse provedor."}
    if indice < 1 or indice > len(lista):
        return {"ok": False, "mensagem": f"Escolha de 1 a {len(lista)} (a chave principal não se apaga por aqui)."}
    removida = lista.pop(indice - 1)
    novo = dict(atual)
    if lista:
        novo[prov] = lista
    else:
        novo.pop(prov, None)
    settings.update({"chaves_extras": novo})
    return {"ok": True, "mensagem": f"🗑 Chave {mascarar(removida)} removida."}
