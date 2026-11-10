"""Zenith — FONTES: o que ela usa como BASE para responder (v1.6.1).

Pedido do Anderson: "falta o local das coisas em que ela se baseou: a biblioteca ou a Bíblia". O painel Biblioteca
(`zenith_projetos.py`) mostrava só o que ela CRIOU. Este módulo monta a outra metade, no mesmo formato de categorias
(`id`, `titulo`, `grupos[]`, `itens[]`) para o mesmo painel desenhar:

    Fontes  -> os documentos que você guardou (PDF, Word, texto...) e que ela cita com arquivo e página
    Bíblia  -> as regras e os cartões de conhecimento que vão no prompt:
               sempre ligadas / entram quando o assunto bate / aprendidas com você / suas regras (ZENITH.md)

Só LÊ e monta dados. As três ações do painel passam por aqui e são seguras:
  * tirar um documento da biblioteca (o arquivo original NUNCA é tocado: só some do índice);
  * apagar um cartão que ELA aprendeu (`aprendido-...`; os outros são arquivos seus ou da base e não se apagam pelo painel);
  * adicionar um documento escolhido por você (usa a mesma rotina do /biblioteca add).
Nada aqui executa código, usa rede ou relaxa o Pilar 1.
"""
from __future__ import annotations

from pathlib import Path

from brain import zenith_biblia as BI
from brain import zenith_conhecimento as CO

MAX_TEXTO_CARTAO = 7000          # o painel mostra o cartão inteiro até aqui; acima disso corta e avisa
MAX_DOCUMENTOS = 200
MAX_PALAVRAS = 12


def _cortar(texto: str) -> tuple:
    texto = (texto or "").strip()
    if len(texto) <= MAX_TEXTO_CARTAO:
        return texto, False
    return texto[:MAX_TEXTO_CARTAO].rstrip() + "\n[...]", True


def _item_cartao(c, user: str, persona: str, pasta_criacoes: str, sempre: bool) -> dict:
    cheio = c.texto(user, persona, pasta_criacoes)
    texto, cortado = _cortar(cheio)
    return {"nome": c.titulo, "tipo": "biblia", "id": c.id, "origem": c.origem, "sempre": bool(sempre),
            "palavras": [p for p in c.palavras if p][:MAX_PALAVRAS], "texto": texto, "cortado": cortado,
            "tamanho": len(cheio), "apagavel": c.origem == "aprendido"}


def _item_fixo(chave: str, user: str, persona: str, pasta_criacoes: str) -> dict:
    sec = BI.SECOES[chave]
    cheio = BI._preencher(sec["texto"], user, persona, pasta_criacoes)
    texto, cortado = _cortar(cheio)
    return {"nome": sec["titulo"], "tipo": "biblia", "id": chave, "origem": "base", "sempre": True,
            "palavras": [], "texto": texto, "cortado": cortado, "tamanho": len(cheio), "apagavel": False}


def categoria_fontes(bib=None) -> dict:
    """Documentos guardados na biblioteca (os que ela cita com arquivo e página)."""
    if bib is None:
        from brain import zenith_biblioteca as B
        bib = B.padrao()
    try:
        docs = list(bib.documentos())
    except Exception:
        docs = []
    itens = []
    for d in docs[:MAX_DOCUMENTOS]:
        nome = str(d.get("nome", ""))
        itens.append({"nome": nome, "tipo": "fonte", "id": str(d.get("id", "")),
                      "paginas": int(d.get("paginas", 0) or 0), "trechos": int(d.get("trechos", 0) or 0),
                      "adicionado": str(d.get("adicionado", "")), "extensao": Path(nome).suffix.lower().lstrip(".")})
    return {"id": "fontes", "titulo": "Fontes", "grupo": "base", "total": len(docs),
            "dica": ("Documentos que você guardou: ela responde citando o arquivo e a página. Tirar daqui só remove do "
                     "índice; o arquivo original continua onde estava. Fica tudo no seu computador."),
            "pode_adicionar": True,
            "grupos": [{"titulo": f"Documentos guardados ({len(itens)})", "itens": itens}] if itens else []}


def categoria_biblia(user: str = "", persona: str = "Zenith", pasta_criacoes: str = "", pasta_biblia=None, extra=None) -> dict:
    """A Bíblia: regras de ouro, cartões por assunto, o que ela aprendeu e as regras do usuário."""
    try:
        cartoes = CO.carregar_cartoes(pasta_biblia)
    except Exception:
        cartoes = CO.cartoes_base()
    sempre, por_assunto, aprendidos = [], [], []
    for c in sorted(cartoes, key=lambda x: (-x.prioridade, x.id)):
        if c.origem == "aprendido":
            aprendidos.append(_item_cartao(c, user, persona, pasta_criacoes, False))
        elif c.sempre == "sim":
            sempre.append(_item_cartao(c, user, persona, pasta_criacoes, True))
        else:
            por_assunto.append(_item_cartao(c, user, persona, pasta_criacoes, False))
    fixos = [_item_fixo(k, user, persona, pasta_criacoes) for k in ("essencial", "corpo")]
    if extra is None:
        extra = BI.carregar_extra()
    regras = []
    texto_extra, cortado = _cortar(extra or "")
    regras.append({"nome": "Suas regras (config/ZENITH.md)", "tipo": "biblia", "id": "extra", "origem": "arquivo",
                   "sempre": bool(texto_extra), "palavras": [], "cortado": cortado, "tamanho": len(extra or ""), "apagavel": False,
                   "texto": texto_extra or ("Ainda vazio. Escreva suas regras em config/ZENITH.md (até "
                                            f"{BI.LIMITE_EXTRA} caracteres) e elas entram no prompt de toda conversa, "
                                            "sempre abaixo dos pilares de segurança.")})
    grupos = [
        {"titulo": f"Sempre no prompt ({len(fixos) + len(sempre)})", "itens": fixos + sempre},
        {"titulo": f"Entram quando o assunto bate, no máximo {BI.MAX_SECOES_POR_MENSAGEM} por mensagem ({len(por_assunto)})", "itens": por_assunto},
    ]
    if aprendidos:
        grupos.append({"titulo": f"Aprendidas com você ({len(aprendidos)})", "itens": aprendidos})
    grupos.append({"titulo": "Suas regras", "itens": regras})
    total = len(fixos) + len(sempre) + len(por_assunto) + len(aprendidos) + (1 if texto_extra else 0)
    return {"id": "biblia", "titulo": "Bíblia", "grupo": "base", "total": total,
            "dica": ("É o que ela sabe sobre si mesma e sobre como trabalhar bem, seja qual for a IA por trás. Aqui é só leitura: "
                     "as regras vêm do programa; para acrescentar as suas, use config/ZENITH.md. Os pilares de segurança vêm antes de tudo."),
            "grupos": [g for g in grupos if g["itens"]]}


def categorias(bib=None, user: str = "", persona: str = "Zenith", pasta_criacoes: str = "", pasta_biblia=None, extra=None) -> list:
    """As duas categorias do grupo 'base' (o que ela usa como base). Nunca levanta erro."""
    saida = []
    for fabrica in (lambda: categoria_fontes(bib), lambda: categoria_biblia(user, persona, pasta_criacoes, pasta_biblia, extra)):
        try:
            saida.append(fabrica())
        except Exception as e:                                   # um defeito aqui não pode derrubar o painel inteiro
            print(f"[Zenith/Fontes] {type(e).__name__}: {e}")
    return saida


# ---------------------------------------------------------------------------------------------------- ações do painel
def tirar_fonte(doc_id: str, bib=None) -> tuple:
    """Tira um documento da biblioteca (só do índice). Devolve (ok, mensagem em português)."""
    from brain import zenith_biblioteca as B
    bib = bib or B.padrao()
    try:
        d = bib.remover(str(doc_id or "").strip())
    except B.ErroBiblioteca as e:
        return False, str(e).replace("📚 ", "")
    return True, f"Tirei \"{d['nome']}\" da biblioteca. O arquivo original continua onde estava."


def apagar_aprendido(cid: str, pasta=None) -> tuple:
    """Apaga um cartão que ELA aprendeu. Só `aprendido-...`: o resto não se apaga pelo painel."""
    msg = CO.apagar_aprendizado(cid, pasta)
    return (not msg.lstrip().startswith("❌")), msg
