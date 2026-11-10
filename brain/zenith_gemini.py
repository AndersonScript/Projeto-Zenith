"""
Zenith — Gemini: qual modelo usar e como ligar o raciocínio (v23).

Por que existe (achado no teste do Anderson: "cadê o poder do Gemini, que é bom em cálculo e programação?"):
  * até a v22 o código tinha `gemini-2.5-flash` escrito no meio do núcleo — em 2026 o Gemini já está na geração 3.x
    (gemini-3.5-flash é estável; 3.6/3.7/3.8 saem como versões curtas; 3.1-pro-preview é o "Pro"). Rodar um
    modelo duas gerações atrás é a causa mais provável de "ela está burra" quando o resto está certo.
  * o raciocínio estendido mudou: nos modelos 3.x o controle é `thinking_level` (low/medium/high); nos 2.5 é
    `thinking_budget` (número de tokens). Mandar o parâmetro errado dá erro 400 — por isso esta tabela.
  * o teto de saída era 8192 tokens (cortava código longo no meio); os modelos atuais aceitam 65 mil.

Tudo aqui é lógica pura (texto -> texto/dict): não importa a SDK nem faz rede, então é testável em qualquer lugar.
A fonte dos nomes é a documentação oficial do Gemini API (ai.google.dev/gemini-api/docs/models e /thinking),
conferida em 07/10/2026. Os nomes mudam rápido: o `/modelos` lista o que a SUA chave realmente enxerga e o
`/modelo gemini <id>` troca na hora, sem mexer em código.
"""
from __future__ import annotations

import re

MODELO_PADRAO = "gemini-3.5-flash"          # estável (doc: disponível até pelo menos 05/2027)
# v1.6.1: no plano grátis a cota é POR MODELO e os Flash têm só ~20 pedidos/dia; os "lite" têm ~500. Eles entram por último:
# quando os Flash esgotam, a conversa continua em vez de cair em outra IA. (Ids conferidos pela lista de grátis; se o seu
# /modelos mostrar outro nome, troque com /modelo gemini <id> — um id que não existe só é pulado.)
MODELOS_RESERVA = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
SAIDA_MAX_PADRAO = 32768                    # tokens de saída (inclui o "pensamento"); o modelo aceita até 65 536

# modelos 3.x que NÃO aceitam o nível "medium" (doc: gemini-3-pro-preview só tem low/high)
_SEM_MEDIUM = ("gemini-3-pro",)

_PALAVRAS_DIFICEIS = (
    "calcul", "equac", "integral", "derivad", "limite", "matriz", "prove", "demonstr", "fisica", "física",
    "algoritm", "codigo", "código", "programa", "script", "bug", "erro", "debug", "otimiz", "arquitetura",
    "circuito", "esp32", "arduino", "serial", "resist", "tensao", "tensão", "corrente", "lei de", "formula",
    "fórmula", "passo a passo", "explique", "explica", "por que", "porque", "compare", "analise", "análise",
    "projeto", "planeje", "plano", "estrateg", "resolva", "quiz", "prova", "exercicio", "exercício",
)


def normalizar(modelo: str) -> str:
    """'models/gemini-3.5-flash' -> 'gemini-3.5-flash' (a API devolve com o prefixo)."""
    m = str(modelo or "").strip()
    return m[7:] if m.lower().startswith("models/") else m


def eh_gemini3(modelo: str) -> bool:
    return normalizar(modelo).lower().startswith("gemini-3")


def eh_gemini25(modelo: str) -> bool:
    return normalizar(modelo).lower().startswith("gemini-2.5")


def eh_pro(modelo: str) -> bool:
    return "-pro" in normalizar(modelo).lower()


def dificil(mensagem: str) -> bool:
    """Heurística barata: a mensagem pede raciocínio de verdade? (conta, código, passo a passo, texto longo...)."""
    t = (mensagem or "").lower()
    if len(t) > 400:
        return True
    if re.search(r"\d+\s*[-+*/^=]\s*\d+|[a-z]\s*=\s*[-\d(]", t):
        return True
    return any(p in t for p in _PALAVRAS_DIFICEIS)


VELOCIDADES = ("rapido", "equilibrado", "profundo")


def thinking_kwargs(modelo: str, pensante: bool, mensagem: str = "", velocidade: str = "equilibrado") -> dict:
    """Argumentos do ThinkingConfig certos para a geração do modelo ({} = não mandar nada).

    pensante=False ('modo econômico') -> raciocínio mínimo sempre.
    pensante=True depende da `velocidade` (v24 — quanto MAIS raciocínio, MAIS demora pra falar):
      * "rapido"      : conversa casual = LOW (resposta em ~1–2 s); pergunta difícil (conta, código...) = MEDIUM
      * "equilibrado" : casual = MEDIUM; difícil = HIGH
      * "profundo"    : sempre HIGH (estudo/lição de casa: capricho acima de rapidez)"""
    m = normalizar(modelo).lower()
    if velocidade not in VELOCIDADES:
        velocidade = "equilibrado"
    dif = dificil(mensagem)
    if eh_gemini3(m):
        if not pensante:
            return {"thinking_level": "LOW"}
        if velocidade == "rapido":
            nivel = "MEDIUM" if dif else "LOW"
        elif velocidade == "profundo":
            nivel = "HIGH"
        else:
            nivel = "HIGH" if dif else "MEDIUM"
        if nivel == "MEDIUM" and any(m.startswith(p) for p in _SEM_MEDIUM):
            nivel = "HIGH"
        return {"thinking_level": nivel}
    if eh_gemini25(m):
        if eh_pro(m):                            # o 2.5 Pro não deixa desligar o raciocínio
            if not pensante or (velocidade == "rapido" and not dif):
                return {"thinking_budget": 512}
            return {"thinking_budget": -1}
        if not pensante or (velocidade == "rapido" and not dif):
            return {"thinking_budget": 0}
        if velocidade == "rapido":
            return {"thinking_budget": 2048}    # difícil, mas sem deixar o raciocínio correr solto
        return {"thinking_budget": -1}
    return {}                                    # modelo desconhecido: deixa o padrão da API


def cadeia_de_modelos(escolhido: str) -> list:
    """Modelo escolhido primeiro; depois as reservas (sem repetir)."""
    saida = []
    for m in (normalizar(escolhido) or MODELO_PADRAO, *MODELOS_RESERVA):
        if m and m not in saida:
            saida.append(m)
    return saida


# ---------------------------------------------------------------- classificação de erros
def classificar_erro(erro) -> str:
    """'modelo' (nome inválido/sem acesso) | 'raciocinio' (parâmetro de thinking recusado) |
    'sobrecarga' (503/429/timeout: vale esperar ou trocar) | 'cota' (limite diário zerado) |
    'chave' (chave inválida) | 'conteudo' (bloqueado pela segurança do Google) | 'outro'."""
    t = str(erro or "").lower()
    if any(s in t for s in ("api key not valid", "api_key_invalid", "permission_denied", "401", "403")) \
            and "model" not in t:
        return "chave"
    if "thinking" in t and any(s in t for s in ("invalid", "unsupported", "not supported", "400", "level", "budget")):
        return "raciocinio"                       # antes de 'modelo': "...not supported for this model" também casaria lá
    if any(s in t for s in ("is not found", "not_found", "404", "not supported for", "unknown model",
                            "models/", "model not found", "no longer available", "deprecated")):
        return "modelo"
    if any(s in t for s in ("per day", "daily", "quota exceeded", "free_tier", "billing")):
        return "cota"
    if any(s in t for s in ("503", "unavailable", "overloaded", "high demand", "429", "resource_exhausted",
                            "rate limit", "timeout", "timed out", "deadline", "500", "internal")):
        return "sobrecarga"
    if any(s in t for s in ("blocked", "safety", "prohibited")):
        return "conteudo"
    return "outro"


# ---------------------------------------------------------------- escolha / listagem de modelos
_RE_FLASH = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash$")


def _versao(modelo: str) -> tuple:
    m = re.match(r"^gemini-(\d+)(?:\.(\d+))?", modelo)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def sao_de_texto(ids: list) -> list:
    """Filtra a lista da API: só modelos de conversa (tira imagem, voz, live, embedding, robótica...)."""
    ruins = ("image", "tts", "live", "embedding", "robotics", "imagen", "veo", "lyria", "audio", "omni",
             "aqa", "learnlm", "gemma", "computer-use", "customtools")
    saida = []
    for i in ids or []:
        m = normalizar(i)
        if m.lower().startswith("gemini") and not any(r in m.lower() for r in ruins):
            saida.append(m)
    return sorted(set(saida))


def melhor_modelo(ids: list) -> str:
    """Escolhe o melhor modelo ESTÁVEL de conversa que a chave enxerga. Preferência: gemini-3.5-flash (longa
    vida); senão o flash estável de maior versão; senão qualquer 'flash'; senão '' (use o padrão)."""
    lista = sao_de_texto(ids)
    if MODELO_PADRAO in lista:
        return MODELO_PADRAO
    estaveis = [m for m in lista if _RE_FLASH.match(m)]
    if estaveis:
        return max(estaveis, key=_versao)
    flashes = [m for m in lista if "flash" in m and "lite" not in m]
    return max(flashes, key=_versao) if flashes else ""


def candidatos_de_conversa(ids: list, ja_tentados=()) -> list:
    """Modelos de conversa que a conta enxerga e que ainda NÃO foram tentados, do mais novo para o mais velho.

    v1.10 — é o socorro quando os nomes da cadeia morreram: `melhor_modelo` pode devolver justamente um nome
    que acabou de falhar (o padrão), e aí a conversa morria mesmo com a conta tendo um modelo novo bom.
    """
    vistos = set(ja_tentados or ())
    sobrou = [m for m in sao_de_texto(ids) if m not in vistos]
    return sorted(sobrou, key=_versao, reverse=True)[:4]


def formatar_lista(ids: list, atual: str) -> str:
    lista = sao_de_texto(ids)
    if not lista:
        return "Nenhum modelo Gemini de conversa apareceu para a sua chave."
    atual = normalizar(atual)
    linhas = []
    for m in sorted(lista, key=lambda x: (_versao(x), x), reverse=True):
        marca = " ◀ em uso" if m == atual else ""
        tipo = "Pro (mais forte, mais lento)" if eh_pro(m) else ("Flash-Lite (mais rápido, mais simples)" if "lite" in m else "Flash (equilíbrio)")
        prev = " · preview" if ("preview" in m or "exp" in m) else ""
        linhas.append(f"• {m} — {tipo}{prev}{marca}")
    return "\n".join(linhas)
