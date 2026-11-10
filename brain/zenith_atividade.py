"""v1.3 — cartões de atividade no meio do chat ("Adicionando à memória…", "Executando código…", "Pesquisando na web…").

Cada cartão tem um `id`. O Cérebro manda o mesmo id de novo quando o estado muda (rodando -> ok/erro), e o Corpo atualiza o cartão
em vez de criar outro. Clicando no cartão a pessoa vê O QUE foi feito (o código, o fato salvo, a pergunta pesquisada, o resultado).

SEGURANÇA: tudo que vai para a tela passa por `zenith_segredos.mascarar` (uma chave que apareça num código ou numa pesquisa não vaza)
e é cortado em MAX_DETALHE caracteres. Isto é só um AVISO visual: se algo aqui der errado, a ação em si nunca é afetada.
"""
import itertools
import time

from brain import zenith_segredos

MAX_DETALHE = 12000
ESTADOS = ("rodando", "ok", "erro")
TIPOS = ("memoria", "busca", "codigo", "terminal", "imagem", "video", "documento", "pasta", "biblioteca", "olho", "programa", "info")
_contador = itertools.count(1)

# tipo de ação aprovada -> (tipo do cartão, título enquanto roda, título quando termina bem)
ACOES = {
    "python": ("codigo", "Executando código Python", "Código executado"),
    "terminal": ("terminal", "Executando comando no terminal", "Comando executado"),
    "serial": ("programa", "Falando com a placa (Arduino/ESP32)", "Comando enviado à placa"),
    "screen": ("olho", "Olhando a tela", "Tela analisada"),
    "camera": ("olho", "Olhando pela câmera", "Câmera analisada"),
    "search": ("busca", "Pesquisando na web", "Pesquisa feita"),
    "read_url": ("busca", "Lendo uma página da web", "Página lida"),
    "image_search": ("imagem", "Procurando imagens", "Imagens encontradas"),
    "image_gen": ("imagem", "Gerando imagem", "Imagem gerada"),
    "video": ("video", "Editando vídeo", "Vídeo pronto"),
    "document": ("documento", "Criando documento", "Documento criado"),
    "organize": ("pasta", "Organizando pasta", "Pasta organizada"),
    "program": ("programa", "Abrindo programa", "Programa aberto"),
    "learn": ("memoria", "Aprendendo algo novo", "Aprendizado salvo"),
    "skill_create": ("codigo", "Criando uma habilidade", "Habilidade criada"),
    "skill_run": ("codigo", "Usando uma habilidade", "Habilidade usada"),
}
_PREFIXOS_DE_FALHA = ("❌", "⛔", "🚫", "🔒")


def novo_id() -> str:
    return f"a{int(time.time() * 1000)}_{next(_contador)}"


def _cortar(texto: str, limite: int = MAX_DETALHE) -> str:
    texto = str(texto or "")
    if len(texto) <= limite:
        return texto
    return texto[:limite] + f"\n… (cortado: o texto completo tem {len(texto)} caracteres)"


def montar(tipo: str, titulo: str, estado: str = "rodando", detalhe: str = "", id: str = None) -> dict:
    """Monta a mensagem para o Corpo. Nunca levanta erro por causa do conteúdo."""
    return {
        "action": "cartao_atividade",
        "id": id or novo_id(),
        "tipo": tipo if tipo in TIPOS else "info",
        "titulo": zenith_segredos.mascarar(str(titulo or ""))[:120],
        "estado": estado if estado in ESTADOS else "ok",
        "detalhe": _cortar(zenith_segredos.mascarar(str(detalhe or ""))),
        "ts": time.time(),
    }


def descrever_acao(kind: str):
    return ACOES.get(kind)


# v1.6 — "Não achei o vídeo neste caminho" aparecia com o cartão "Vídeo pronto" e um visto verde. Agora o começo do texto
# também conta (sem depender de emoji).
_COMECOS_DE_FALHA = ("não achei", "nao achei", "não encontrei", "nao encontrei", "não consegui", "nao consegui",
                     "não foi possível", "nao foi possivel", "não existe", "nao existe", "não deu", "nao deu",
                     "erro", "deu erro", "falha", "falhou", "faltou", "arquivo não encontrado", "arquivo nao encontrado")


def parece_falha(resultado) -> bool:
    texto = str(resultado or "").lstrip()
    if texto.startswith(_PREFIXOS_DE_FALHA):
        return True
    return texto.lower().startswith(_COMECOS_DE_FALHA)
