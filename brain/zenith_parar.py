"""
Zenith — PARAR e "o que ela está fazendo agora" (v26).

Dois pedidos do Anderson (10/10/2026):
  1) "quero saber se ela tá pensando, criando ou programando, falando ou escrevendo";
  2) "se falar 'calma aí, Zenith' ela para — por voz, escrito ou no botão".

COMO O PARAR FUNCIONA (sem mágica, sem depender de a IA "decidir obedecer"):
  * Existe um contador de GERAÇÃO. Toda tarefa guarda o número da geração em que nasceu. Quando alguém pede pra
    parar, o contador sobe — e toda tarefa velha, ao terminar, vê que o número mudou e DESCARTA o próprio resultado
    (não fala, não escreve no chat, não propõe a próxima ação). Uma chamada de rede à IA não dá pra abortar no meio,
    mas o resultado dela morre ao chegar.
  * Processos que o Zenith abriu (código Python/terminal que a IA gerou) são REGISTRADOS aqui e mortos de verdade.
  * Voz, streaming e aprovações pendentes são cortados por quem chama (zenith_headless).

PALAVRA DE PARADA: só vale quando a mensagem é CURTA e é basicamente um pedido de parar ("calma aí Zenith", "para",
"pare tudo", "espera"). "Como parar um carro?" NÃO é pedido de parada. Funciona igual pra texto digitado e voz
transcrita (os dois entram pelo mesmo caminho).

Lógica pura (sem rede, sem Godot): testável em qualquer máquina.
"""
from __future__ import annotations

import re
import threading
import unicodedata

_lock = threading.Lock()
_geracao = 0
_processos: set = set()


# ------------------------------------------------------------------ geração (descartar o que ficou velho)
def geracao() -> int:
    return _geracao


def cancelado_desde(g: int) -> bool:
    """True se alguém pediu pra parar DEPOIS de a tarefa de geração `g` começar."""
    return _geracao != g


def solicitar(motivo: str = "") -> int:
    """Pede pra parar TUDO que está em andamento. Devolve a nova geração."""
    global _geracao
    with _lock:
        _geracao += 1
        nova = _geracao
    matar_processos()
    return nova


# ------------------------------------------------------------------ processos que o Zenith abriu
def registrar_processo(p):
    with _lock:
        _processos.add(p)


def liberar_processo(p):
    with _lock:
        _processos.discard(p)


def matar_processos() -> int:
    """Mata os processos registrados que ainda estão rodando. Devolve quantos matou."""
    with _lock:
        lista = list(_processos)
        _processos.clear()
    n = 0
    for p in lista:
        try:
            if p.poll() is None:
                p.kill()
                n += 1
        except Exception:
            pass
    return n


# ------------------------------------------------------------------ palavra de parada
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


_PARADA = {"para", "pare", "parar", "calma", "espera", "espere", "aguarda", "aguarde", "segura", "chega", "cancela",
           "cancele", "cancelar", "stop", "silencio", "psiu"}
_ENFEITE = {"ei", "oi", "ola", "opa", "ow", "por", "favor", "pfv", "pf", "agora", "ja", "ai", "la", "so", "um", "uma",
            "segundo", "segundinho", "momento", "minutinho", "pera", "tudo", "isso", "de", "da", "do", "ai", "ok",
            "falar", "fazer", "mexer", "nisso", "escrever", "e", "ou", "a", "o", "pode", "poderia", "tem", "que"}


def eh_pedido_de_parada(texto: str, nome_ia: str = "Zenith") -> bool:
    """True se a mensagem é, basicamente, só um pedido pra parar ("calma aí, Zenith", "para tudo", "espera")."""
    t = _norm(texto)
    if not t:
        return False
    nomes = {_norm(nome_ia), "zenith", "akira"}
    tokens = [x for x in t.split() if x not in nomes]
    if not tokens or len(tokens) > 5:
        return False
    if not any(x in _PARADA for x in tokens):
        return False
    return all(x in _PARADA or x in _ENFEITE for x in tokens)


# ------------------------------------------------------------------ rótulos de atividade (o que ela está fazendo)
# estado -> (ícone, texto padrão). O Corpo (Godot) só desenha o que o Cérebro manda.
ESTADOS = {
    "ocioso":      ("", ""),
    "pensando":    ("🧠", "Pensando"),
    "pesquisando": ("🔎", "Pesquisando na web"),
    "lendo":       ("📄", "Lendo a página"),
    "programando": ("💻", "Criando o programa"),
    "rodando":     ("⚙️", "Rodando"),
    "olhando":     ("👁", "Olhando"),
    "hardware":    ("🔌", "Falando com o hardware"),
    "aprendendo":  ("📚", "Aprendendo"),
    "desenhando":  ("🎨", "Criando a imagem"),
    "falando":     ("🔊", "Falando"),
    "aguardando":  ("✋", "Esperando sua aprovação"),
}

_POR_ACAO = {
    "python": ("rodando", "Rodando o código"),
    "terminal": ("rodando", "Rodando um comando"),
    "serial": ("hardware", "Falando com o hardware"),
    "screen": ("olhando", "Olhando a tela"),
    "camera": ("olhando", "Olhando a câmera"),
    "search": ("pesquisando", "Pesquisando na web"),
    "read_url": ("lendo", "Lendo a página"),
    "image_search": ("pesquisando", "Buscando imagens"),
    "image_gen": ("desenhando", "Criando a imagem com IA"),
    "program": ("programando", "Criando o programa"),
    "learn": ("aprendendo", "Aprendendo"),
    "skill_create": ("programando", "Criando uma habilidade"),
    "skill_run": ("rodando", "Rodando a habilidade"),
    "observe": ("olhando", "Ligando a observação"),
    "video": ("rodando", "Editando o vídeo"),                 # v28
    "document": ("rodando", "Criando o documento"),
    "organize": ("rodando", "Arrumando a pasta"),
}


def estado_da_acao(kind: str) -> tuple:
    """(estado, texto) pra uma ação aprovada de tipo `kind` ('python', 'search'...)."""
    return _POR_ACAO.get(kind, ("rodando", "Executando a ação"))


def mensagem_atividade(estado: str, texto: str = "") -> dict:
    """Mensagem pro Corpo mostrar a linha de status (e o botão Parar só enquanto há algo pra parar)."""
    if estado not in ESTADOS:
        estado = "rodando"
    icone, padrao = ESTADOS[estado]
    ocupado = estado not in ("ocioso",)
    return {"action": "atividade", "estado": estado, "icone": icone,
            "texto": texto or padrao, "pode_parar": bool(ocupado)}
