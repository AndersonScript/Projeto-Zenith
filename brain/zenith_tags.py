"""
Zenith — filtro de TAGS (v26): nenhuma etiqueta interna aparece no chat, mesmo escrita errado.

O problema que isso resolve (print do Anderson, 10/10/2026): a IA escreveu `<lembral>` em vez de `<lembrar>`.
O Zenith só conhecia a grafia exata, então (1) o fato NÃO foi salvo na memória e (2) a etiqueta apareceu CRUA
no chat. Já tinha acontecido antes com `<corpo>emocao:sad</corpo>`. Modelos pequenos erram nome de etiqueta o
tempo todo — o programa tem que aguentar isso.

Duas funções, duas camadas de defesa:

  corrigir_tags(texto)   -> troca nome de etiqueta ERRADO pelo certo mais parecido (`<lembral>` -> `<lembrar>`).
                            Roda ANTES de extrair memória/ações, então a memória é salva de verdade.
  limpar_visivel(texto)  -> última barreira antes do chat: some com qualquer etiqueta interna que sobrou
                            (com o conteúdo) e tira só as MARCAS de etiquetas desconhecidas (mantém o texto).

Regras de segurança do filtro (pra não estragar conteúdo legítimo):
  * Blocos de código (``` ... ```) e `código inline` NUNCA são tocados — HTML/XML dentro de código fica como está.
  * Etiquetas HTML conhecidas (<b>, <div>, <br>...) nunca são tocadas nem "corrigidas".
  * Nomes com menos de 4 letras e coisas como `a<b>c` (matemática) não contam como etiqueta.
  * Só corrige se for MUITO parecido com uma etiqueta interna (distância de edição ≤ 1 em nomes curtos, ≤ 2 nos longos).

Lógica pura (sem rede, sem Godot): testável em qualquer máquina.
"""
from __future__ import annotations

import re
import unicodedata

# Etiquetas internas que o Zenith entende (ver ACTION_TAGS e companhia em zenith_core / gestos / pendencias).
TAGS_INTERNAS = (
    "executar_python", "executar_terminal", "conectar_serial", "ver_tela", "ver_camera",
    "buscar_web", "ler_url", "buscar_imagem", "gerar_imagem", "criar_programa", "aprender",
    "criar_habilidade", "usar_habilidade", "observar",
    "lembrar", "corpo", "comando", "pendencia", "concluir", "projeto", "action",
    "editar_video", "organizar_pasta", "criar_documento",            # v28
    "criar_movimento",                                               # v1.6
    "propor_ajuste",                                                 # v1.6.2 — conserto do próprio código (só vira proposta)
)

# Nomes de HTML/XML comuns: nunca mexer.
_HTML = frozenset("""
a abbr address article aside audio b base bdi bdo blockquote body br button canvas caption cite code col colgroup
data datalist dd del details dfn dialog div dl dt em embed fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6
head header hr html i iframe img input ins kbd label legend li link main map mark menu meta meter nav noscript object
ol optgroup option output p param picture pre progress q rp rt ruby s samp script section select slot small source
span strong style sub summary sup svg table tbody td template textarea tfoot th thead time title tr track u ul var
video wbr center font
""".split())

_RE_TAG = re.compile(r"<(/?)([A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]*)((?:\s+[\w:-]+\s*=\s*(?:\"[^\"<>]*\"|'[^'<>]*'))*)\s*(/?)>")
_RE_CODIGO = re.compile(r"(```.*?(?:```|\Z)|`[^`\n]+`)", re.S)


def _norm(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def distancia(a: str, b: str) -> int:
    """Distância de edição (Levenshtein) — pequena e suficiente: os nomes têm no máximo ~20 letras."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def parecida_com(nome: str):
    """Nome de etiqueta interna mais parecido com `nome` (ou None). Se `nome` JÁ é interno, devolve ele mesmo."""
    n = _norm(nome)
    if n in TAGS_INTERNAS:
        return n
    if n in _HTML or len(n) < 4:
        return None
    melhor, melhor_d = None, 99
    for t in TAGS_INTERNAS:
        d = distancia(n, t)
        if d < melhor_d:
            melhor, melhor_d = t, d
    limite = 1 if len(n) <= 6 else 2
    return melhor if melhor_d <= limite else None


def _fora_do_codigo(texto: str, funcao):
    """Aplica `funcao(trecho)` só nos pedaços FORA de código (``` e `inline`)."""
    saida, pos = [], 0
    for m in _RE_CODIGO.finditer(texto):
        saida.append(funcao(texto[pos:m.start()]))
        saida.append(m.group(0))
        pos = m.end()
    saida.append(funcao(texto[pos:]))
    return "".join(saida)


def _troca(m):
    """Troca o nome de UMA etiqueta (abertura ou fechamento) pelo nome interno certo, se for muito parecido."""
    barra, nome, attrs, auto = m.group(1), m.group(2), m.group(3), m.group(4)
    certo = parecida_com(nome)
    if certo is None or nome == certo:
        return m.group(0)
    return f"<{barra}{certo}{attrs}{auto}>"


def corrigir_tags(texto: str) -> str:
    """`<lembral>x</lembral>` -> `<lembrar>x</lembrar>` (só quando MUITO parecido com uma etiqueta interna)."""
    if not texto or "<" not in texto:
        return texto or ""
    return _fora_do_codigo(texto, lambda t: _RE_TAG.sub(_troca, t))


def nomes_desconhecidos(texto: str) -> list:
    """Nomes de etiqueta que não são HTML nem internas (pra log/diagnóstico). Ignora código."""
    achados = []

    def _ve(trecho):
        for m in _RE_TAG.finditer(trecho):
            n = _norm(m.group(2))
            if len(n) >= 4 and n not in _HTML and n not in TAGS_INTERNAS and n not in achados:
                achados.append(n)
        return trecho

    _fora_do_codigo(texto or "", _ve)
    return achados


def limpar_visivel(texto: str) -> str:
    """Última barreira: nada de etiqueta interna no chat.
       - Etiqueta interna (ou quase) em par: some com a etiqueta E o conteúdo (era só pra memória/corpo/ação).
       - Etiqueta interna solta (sem par): some só a marca.
       - Etiqueta desconhecida (nome >= 4 letras, não é HTML): tira só as marcas, o texto de dentro fica."""
    if not texto or "<" not in texto:
        return (texto or "").strip()

    def _limpa(trecho):
        trecho = _RE_TAG.sub(_troca, trecho)          # `<lembral>…</lembral>` vira `<lembrar>…</lembrar>` antes de sumir
        # 1) pares internos: <x ...>conteúdo</x>
        for nome in TAGS_INTERNAS:
            trecho = re.sub(rf"<{nome}\b[^<>]*>.*?</{nome}\s*>", "", trecho, flags=re.S | re.I)
        # 2) marcas internas soltas
        for nome in TAGS_INTERNAS:
            trecho = re.sub(rf"</?{nome}\b[^<>]*>", "", trecho, flags=re.I)

        # 3) desconhecidas: tira só as marcas
        def _desconhecida(m):
            n = _norm(m.group(2))
            if len(n) >= 4 and n not in _HTML and n not in TAGS_INTERNAS:
                return ""
            return m.group(0)
        trecho = _RE_TAG.sub(_desconhecida, trecho)
        return trecho

    texto = _fora_do_codigo(texto, _limpa)
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()



def limpar_pra_comparar(texto: str) -> str:
    """Atalho para os testes."""
    return limpar_visivel(corrigir_tags(texto))
