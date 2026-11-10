"""
Zenith — escolha de expressão e gesto a partir do texto da resposta (v20).

O `_guess_expression` antigo olhava só 3 coisas e usava "rs" como pedaço de palavra (casava
com "versão", "porque"...). Aqui: palavras inteiras, mais emoções (feliz/triste/brava/surpresa/
calma) e uma escolha de GESTO opcional (acenar, concordar, negar, dar de ombros, comemorar...).

Regras de bom senso:
  * nada é obrigatório — se o texto não sugere nada, devolve neutro/sem gesto;
  * no máximo UM gesto por resposta, e só quando o sinal é claro (evita avatar "teatral");
  * puro texto -> texto: não importa Godot, rede nem bibliotecas pesadas (testável em qualquer lugar).
"""
import re

_PALAVRA = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)

_FELIZ = {"haha", "hahaha", "kkk", "kkkk", "rs", "rsrs", "engraçado", "engracado", "legal", "ótimo", "otimo",
          "adorei", "adoro", "feliz", "parabéns", "parabens", "excelente", "incrível", "incrivel", "show",
          "maravilha", "perfeito", "boa"}
_TRISTE = {"desculpa", "desculpe", "sinto", "triste", "lamento", "infelizmente", "saudade", "pena"}
_BRAVA = {"absurdo", "inaceitável", "inaceitavel", "irritante", "raiva", "péssimo", "pessimo", "ridículo", "ridiculo"}
_SURPRESA = {"uau", "nossa", "caramba", "sério", "serio", "incrível", "incrivel", "surpresa", "inesperado", "wow"}
_CALMA = {"tranquilo", "tranquila", "calma", "calmo", "relaxa", "relaxe", "respira", "devagar", "sossego"}

_OI = {"oi", "olá", "ola", "eae", "salve", "bom dia", "boa tarde", "boa noite"}
_TCHAU = {"tchau", "até", "ate", "falou"}
_SIM = {"sim", "claro", "concordo", "exato", "exatamente", "isso", "certo", "combinado", "pode"}
_NAO = {"não", "nao", "nunca", "jamais", "discordo", "impossível", "impossivel"}
_DUVIDA = {"talvez", "depende", "hmm", "hum", "acho", "quem sabe", "difícil", "dificil"}
_PENSAR = {"deixa", "pensando", "vejamos", "analisando", "calculando"}
_COMEMORAR = {"parabéns", "parabens", "consegui", "conseguimos", "funcionou", "vitória", "vitoria", "yay", "uhul", "arrasou"}
_REVERENCIA = {"obrigada", "obrigado", "agradeço", "agradeco", "prazer", "disponha"}


def _palavras(texto: str) -> list:
    return [p.lower() for p in _PALAVRA.findall(texto or "")]


def _tem(palavras: list, texto_baixo: str, conjunto: set) -> bool:
    for item in conjunto:
        if " " in item:
            if item in texto_baixo:
                return True
        elif item in palavras:
            return True
    return False


def escolher_expressao(texto: str) -> str:
    """'happy' | 'sad' | 'angry' | 'surprised' | 'relaxed' | 'neutral'."""
    if not texto:
        return "neutral"
    p = _palavras(texto)
    baixo = texto.lower()
    # ordem importa: tristeza/raiva ganham de "!" ; alegria ganha de surpresa quando há os dois
    if _tem(p, baixo, _TRISTE):
        return "sad"
    if _tem(p, baixo, _BRAVA):
        return "angry"
    if _tem(p, baixo, _FELIZ) or "😂" in texto or "😄" in texto or "🙂" in texto:
        return "happy"
    if _tem(p, baixo, _SURPRESA):
        return "surprised"
    if _tem(p, baixo, _CALMA):
        return "relaxed"
    if "!" in texto:
        return "surprised" if texto.count("!") >= 2 else "happy"
    return "neutral"


def escolher_gesto(texto: str):
    """Nome do gesto (em português, como o akira_vida.gd conhece) ou None.
    Só olha o COMEÇO da resposta (primeira frase / ~120 caracteres): é onde o gesto cabe."""
    if not texto:
        return None
    inicio = texto.strip()[:120]
    p = _palavras(inicio)
    baixo = inicio.lower()
    primeiras = p[:6]
    nega = _tem(p[:5], " ".join(p[:5]), _NAO) or _tem(p, baixo, _TRISTE)
    if _tem(primeiras, baixo, _COMEMORAR) and not nega:      # "não consegui" / "desculpa, não funcionou" não é festa
        return "comemorar"
    if _tem(primeiras, " ".join(primeiras), _OI):
        return "acenar"
    if _tem(primeiras, " ".join(primeiras), _TCHAU) and len(p) <= 8:
        return "acenar"
    if _tem(primeiras[:3], " ".join(primeiras[:3]), _NAO):
        return "negar"
    if _tem(primeiras[:3], " ".join(primeiras[:3]), _SIM):
        return "concordar"
    if _tem(primeiras[:4], " ".join(primeiras[:4]), _DUVIDA):
        return "ombros"
    if _tem(primeiras[:4], " ".join(primeiras[:4]), _REVERENCIA):
        return "reverencia"
    if _tem(primeiras, " ".join(primeiras), _PENSAR):
        return "pensar"
    if inicio.rstrip().endswith("?"):
        return "inclinar"
    return None


# ------------------------------------------------------------------ <corpo> escrito PELA IA (v21)
GESTOS_VALIDOS = ("acenar", "concordar", "negar", "inclinar", "ombros", "pensar", "reverencia", "comemorar", "pulinho")
EMOCOES_VALIDAS = ("happy", "sad", "angry", "surprised", "relaxed", "neutral")
_ALIAS_EMOCAO = {"feliz": "happy", "alegre": "happy", "triste": "sad", "brava": "angry", "bravo": "angry",
                 "surpresa": "surprised", "surpreso": "surprised", "calma": "relaxed", "calmo": "relaxed",
                 "neutra": "neutral", "neutro": "neutral"}
_ALIAS_GESTO = {"oi": "acenar", "tchau": "acenar", "sim": "concordar", "nao": "negar", "não": "negar",
                "duvida": "ombros", "dúvida": "ombros", "curiosa": "inclinar", "curioso": "inclinar",
                "pensando": "pensar", "cumprimentar": "reverencia", "reverência": "reverencia",
                "festa": "comemorar", "pular": "pulinho"}
TAG_CORPO = r"<corpo>(.*?)</corpo>"


# v1.6 — nomes de movimento (brain/zenith_movimentos.py) que a IA pode pedir. Quem preenche é o próprio módulo de movimentos.
MOVIMENTOS_CONHECIDOS: set = set()


def extrair_comandos_corpo(texto: str, maximo: int = 3) -> tuple:
    """Tira as tags <corpo>gesto:acenar</corpo> / <corpo>emocao:happy</corpo> escritas pela IA.
    Devolve (texto_sem_as_tags, [(\"gesto\"|\"emocao\", nome), ...]). Nome desconhecido é ignorado
    (a IA pode inventar) — nunca levanta erro e nunca passa algo que o corpo não conheça."""
    cmds = []
    if not texto:
        return texto or "", cmds
    for bruto in re.findall(TAG_CORPO, texto, flags=re.DOTALL | re.IGNORECASE):
        for parte in re.split(r"[;,\n]", bruto):
            if ":" not in parte:
                continue
            tipo, nome = [x.strip().lower() for x in parte.split(":", 1)]
            nome = nome.replace(" ", "_")
            if tipo in ("movimento", "movement", "mov"):
                if nome in MOVIMENTOS_CONHECIDOS:
                    cmds.append(("movimento", nome))
            elif tipo in ("gesto", "gesture", "acao", "ação"):
                nome = _ALIAS_GESTO.get(nome, nome)
                if nome in GESTOS_VALIDOS:
                    cmds.append(("gesto", nome))
                elif nome in MOVIMENTOS_CONHECIDOS:          # a IA escreveu gesto:pulo — o pulo é um movimento
                    cmds.append(("movimento", nome))
            elif tipo in ("emocao", "emoção", "expressao", "expressão", "emotion"):
                nome = _ALIAS_EMOCAO.get(nome, nome)
                if nome in EMOCOES_VALIDAS:
                    cmds.append(("emocao", nome))
    limpo = re.sub(TAG_CORPO, "", texto, flags=re.DOTALL | re.IGNORECASE).strip()
    return limpo, cmds[:maximo]
