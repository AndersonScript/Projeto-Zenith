"""
Zenith — "VERIFICAR ANTES DE AFIRMAR" (v26).

O problema (prints do Anderson, 10/10/2026): a Zenith escreveu no chat o caminho `...\\creations\\minha_imagem.png`, mas o
arquivo que o sistema realmente salvou se chamava `autorretrato.png`. Ela "disse" um caminho de cabeça — a IA não
enxerga o disco, só escreve texto que PARECE certo. Se a pessoa for abrir esse caminho, não acha nada.

A regra nova: quando a resposta cita um arquivo dentro da pasta de criações como JÁ FEITO, o Zenith confere no disco.
Se o arquivo não existe, acrescenta um aviso com o que realmente foi salvo há pouco. A IA continua livre pra escrever;
o PROGRAMA é quem garante a verdade sobre o que existe no computador.

Só confere quando faz sentido (pra não gerar alarme falso):
  * só caminhos dentro da pasta de criações (caminho de exemplo tipo C:\\Users\\voce\\... é ignorado);
  * só quando o texto fala em algo concluído ("criei", "salvei", "gerei", "pronto"...) — "vou salvar em ..." não conta;
  * quem chama (zenith_core) não confere quando a mesma resposta traz uma ação ainda NÃO executada.

Lógica pura: o sistema de arquivos entra por funções injetadas, então dá pra testar sem disco de verdade.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

_RE_CAMINHO = re.compile(
    r"""(?<![A-Za-z0-9])([A-Za-z]:[\\/][^\s"'<>|*?`\r\n]*?\.[A-Za-z0-9]{1,6})(?=$|[\s"'`<>|,;:!?)\]}]|\.(?:\s|$))""")
_RE_CONCLUIDO = re.compile(
    r"\b(criei|criado|criada|criou|salvei|salvo|salva|salvou|gerei|gerado|gerada|gerou|pronto|prontinho|pronta|"
    r"terminei|finalizei|conclu[ií]|foi\s+(?:criad|salv|ger)\w+|est[aá]\s+(?:em|salv|dispon)\w*|ficou\s+(?:em|salv)\w*|"
    r"fica\s+em|encontra-se|encontra\s+em|aqui\s+est[aá])\b", re.I)
_RE_FUTURO = re.compile(r"\b(vou|vamos|posso|poderia|irei|farei|criarei|salvarei)\b", re.I)


def _norm(caminho: str) -> str:
    return os.path.normcase(str(caminho)).replace("\\", "/").rstrip("/").lower()


def caminhos_citados(texto: str) -> list:
    """Caminhos de arquivo no estilo C:\\pasta\\arquivo.ext citados no texto (sem repetir)."""
    vistos, saida = set(), []
    for m in _RE_CAMINHO.finditer(texto or ""):
        c = m.group(1).rstrip(".")
        if c not in vistos:
            vistos.add(c)
            saida.append(c)
    return saida


def _arquivos_recentes(pasta, janela_s: float, agora: float, profundidade: int = 4, limite: int = 200) -> list:
    """(caminho, mtime) de arquivos modificados nos últimos `janela_s` segundos, do mais novo pro mais velho."""
    achados = []
    base = str(pasta)
    try:
        for raiz, dirs, arquivos in os.walk(base):
            nivel = raiz.rstrip("\\/").count(os.sep) - base.rstrip("\\/").count(os.sep)
            if nivel >= profundidade:
                dirs[:] = []
            for nome in arquivos:
                p = os.path.join(raiz, nome)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                if agora - mt <= janela_s:
                    achados.append((p, mt))
                if len(achados) >= limite:
                    break
    except OSError:
        return []
    achados.sort(key=lambda x: -x[1])
    return achados


def conferir(texto: str, pasta_base, janela_s: float = 1800, agora: float | None = None,
             existe=os.path.exists, recentes=None) -> tuple:
    """Devolve (texto_possivelmente_com_aviso, problemas).
    `problemas` = lista de {"caminho": ..., "reais": [caminhos que existem e são recentes]}.
    `existe(caminho)->bool` e `recentes(pasta, janela_s, agora)->[(caminho, mtime)]` podem ser injetados (testes)."""
    if not texto or not pasta_base:
        return texto, []
    if not _RE_CONCLUIDO.search(texto):
        return texto, []
    agora = time.time() if agora is None else agora
    base_n = _norm(pasta_base)
    problemas = []
    for c in caminhos_citados(texto):
        cn = _norm(c)
        if not (cn == base_n or cn.startswith(base_n + "/")):
            continue                                   # fora da pasta de criações: não é da nossa conta
        if existe(c):
            continue
        # frase "vou salvar em X" (futuro) perto do caminho não é afirmação de que já existe
        idx = texto.find(c)
        janela_texto = texto[max(0, idx - 80):idx]
        if _RE_FUTURO.search(janela_texto) and not _RE_CONCLUIDO.search(janela_texto):
            continue
        ext = os.path.splitext(c)[1].lower()
        lista = (recentes or _arquivos_recentes)(pasta_base, janela_s, agora)
        mesmos = [p for p, _ in lista if os.path.splitext(p)[1].lower() == ext]
        reais = (mesmos or [p for p, _ in lista])[:3]
        problemas.append({"caminho": c, "reais": reais})
    if not problemas:
        return texto, []

    linhas = []
    for p in problemas:
        if p["reais"]:
            onde = "\n".join(f"   • `{r}`" for r in p["reais"])
            linhas.append(f"⚠️ Conferi no computador: o arquivo `{p['caminho']}` NÃO existe. "
                          f"O que o sistema realmente salvou agora há pouco:\n{onde}")
        else:
            linhas.append(f"⚠️ Conferi no computador: o arquivo `{p['caminho']}` NÃO existe, e não achei nenhum "
                          f"arquivo novo na pasta de criações — então ele provavelmente não foi criado de verdade.")
    return texto.rstrip() + "\n\n" + "\n\n".join(linhas), problemas
