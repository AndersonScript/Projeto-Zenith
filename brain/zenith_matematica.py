"""
Zenith — MATEMÁTICA E LaTeX NO CHAT (v26).

O que o Anderson pediu (10/10/2026): "a parte da letra de matemática avançada funcionar, a escrita do editor LaTeX
funcionar ainda mais — eu mexo com mecânica clássica, física, óptica, derivada e integral".

COMO FUNCIONA (a decisão de projeto, em uma frase): o chat do Godot só mostra TEXTO, então a equação chega de DUAS
formas ao mesmo tempo — e nenhuma depende de o Godot entender LaTeX:

  1) texto legível (unicode) dentro da própria frase:   `\\frac{\\partial L}{\\partial \\dot q}`  ->  (∂L)/(∂q̇)
  2) IMAGEM bonita da equação (estilo livro, fonte Computer Modern) como cartão de imagem logo abaixo — o mesmo
     cartão que o chat já usa pras imagens que ela cria ("Abrir" amplia).
  + a VOZ lê a equação em português ("integral de zero a infinito de e elevado a menos x ao quadrado dx"),
    em vez de soletrar barras e chaves.

Usa o matplotlib (mathtext), que JÁ é dependência do Zenith — nada novo pra instalar. O mathtext cobre quase tudo
de física/cálculo (frações, integrais, somatórios, vetores, derivadas parciais, ∇, ∮, raízes, gregas, \\vec, \\hat,
\\dot, \\ddot...). O que ele NÃO cobre (matrizes, `cases`, \\begin{align}) é tratado: `align`/`gather` viram uma
linha por equação; `cases`/matrizes viram linhas simples; se mesmo assim falhar, a imagem sai com o texto unicode.

Lógica pura + um renderizador isolado em renderizar_png() (único ponto que usa matplotlib/PIL).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================================ tabelas
GREGAS = {  # nome -> (unicode, fala)
    "alpha": ("α", "alfa"), "beta": ("β", "beta"), "gamma": ("γ", "gama"), "delta": ("δ", "delta"),
    "epsilon": ("ϵ", "épsilon"), "varepsilon": ("ε", "épsilon"), "zeta": ("ζ", "zeta"), "eta": ("η", "eta"),
    "theta": ("θ", "teta"), "vartheta": ("ϑ", "teta"), "iota": ("ι", "iota"), "kappa": ("κ", "capa"),
    "lambda": ("λ", "lambda"), "mu": ("μ", "mi"), "nu": ("ν", "ni"), "xi": ("ξ", "csi"), "pi": ("π", "pi"),
    "varpi": ("ϖ", "pi"), "rho": ("ρ", "rô"), "varrho": ("ϱ", "rô"), "sigma": ("σ", "sigma"), "varsigma": ("ς", "sigma"),
    "tau": ("τ", "tau"), "upsilon": ("υ", "ípsilon"), "phi": ("ϕ", "fi"), "varphi": ("φ", "fi"), "chi": ("χ", "qui"),
    "psi": ("ψ", "psi"), "omega": ("ω", "ômega"),
    "Gamma": ("Γ", "gama maiúsculo"), "Delta": ("Δ", "delta maiúsculo"), "Theta": ("Θ", "teta maiúsculo"),
    "Lambda": ("Λ", "lambda maiúsculo"), "Xi": ("Ξ", "csi maiúsculo"), "Pi": ("Π", "pi maiúsculo"),
    "Sigma": ("Σ", "sigma maiúsculo"), "Upsilon": ("Υ", "ípsilon maiúsculo"), "Phi": ("Φ", "fi maiúsculo"),
    "Psi": ("Ψ", "psi maiúsculo"), "Omega": ("Ω", "ômega maiúsculo"),
}

SIMBOLOS = {  # comando -> (unicode, fala)
    "cdot": (" · ", " vezes "), "times": (" × ", " vezes "), "div": ("÷", " dividido por "), "pm": ("±", " mais ou menos "),
    "mp": ("∓", " menos ou mais "), "leq": ("≤", " menor ou igual a "), "le": ("≤", " menor ou igual a "),
    "geq": ("≥", " maior ou igual a "), "ge": ("≥", " maior ou igual a "), "neq": ("≠", " diferente de "),
    "ne": ("≠", " diferente de "), "approx": ("≈", " aproximadamente "), "sim": ("∼", " semelhante a "),
    "equiv": ("≡", " equivalente a "), "propto": ("∝", " proporcional a "), "infty": ("∞", " infinito "),
    "partial": ("∂", " derivada parcial "), "nabla": ("∇", " nabla "), "int": ("∫", " integral de "),
    "iint": ("∬", " integral dupla de "), "iiint": ("∭", " integral tripla de "),
    "oint": ("∮", " integral de linha fechada de "), "sum": ("∑", " somatório de "), "prod": ("∏", " produtório de "),
    "to": ("→", " tende a "), "rightarrow": ("→", " tende a "), "leftarrow": ("←", " seta pra esquerda "),
    "Rightarrow": ("⇒", " implica "), "Leftrightarrow": ("⇔", " se e somente se "), "implies": ("⇒", " implica "),
    "mapsto": ("↦", " leva em "), "in": ("∈", " pertence a "), "notin": ("∉", " não pertence a "),
    "subset": ("⊂", " está contido em "), "cup": ("∪", " união "), "cap": ("∩", " interseção "),
    "forall": ("∀", " para todo "), "exists": ("∃", " existe "), "hbar": ("ħ", " h cortado "), "ell": ("ℓ", " l "),
    "degree": ("°", " graus "), "circ": ("∘", " composta com "), "ldots": ("…", " e assim por diante "),
    "cdots": ("⋯", " e assim por diante "), "dots": ("…", " e assim por diante "), "perp": ("⊥", " perpendicular a "),
    "parallel": ("∥", " paralelo a "), "angle": ("∠", " ângulo "), "langle": ("⟨", " abre "), "rangle": ("⟩", " fecha "),
    "Re": ("ℜ", " parte real de "), "Im": ("ℑ", " parte imaginária de "), "star": ("⋆", " estrela "),
    "dagger": ("†", " adjunto "), "prime": ("′", " linha "), "emptyset": ("∅", " conjunto vazio "),
    "aleph": ("ℵ", " álefe "), "wp": ("℘", " pê "), "colon": (":", " "),
}
FUNCOES = {"sin": "seno", "cos": "cosseno", "tan": "tangente", "cot": "cotangente", "sec": "secante",
           "csc": "cossecante", "arcsin": "arco seno", "arccos": "arco cosseno", "arctan": "arco tangente",
           "sinh": "seno hiperbólico", "cosh": "cosseno hiperbólico", "tanh": "tangente hiperbólica",
           "ln": "log natural", "log": "log", "exp": "exponencial", "lim": "limite", "max": "máximo",
           "min": "mínimo", "det": "determinante", "ker": "núcleo", "dim": "dimensão", "sup": "supremo",
           "inf": "ínfimo", "mod": "módulo", "gcd": "mdc", "deg": "grau", "arg": "argumento"}
ACENTOS = {"vec": ("\u20d7", "vetor {}"), "hat": ("\u0302", "{} chapéu"), "dot": ("\u0307", "{} ponto"),
           "ddot": ("\u0308", "{} dois pontos"), "bar": ("\u0304", "{} barra"), "overline": ("\u0304", "{} barra"),
           "tilde": ("\u0303", "{} til"), "widehat": ("\u0302", "{} chapéu"), "check": ("\u030c", "{} circunflexo"),
           "overrightarrow": ("\u20d7", "vetor {}"), "underline": ("\u0332", "{}")}
ESTILOS_TEXTO = {"mathbf", "mathrm", "mathit", "text", "textrm", "textbf", "textit", "mbox", "operatorname",
                 "boldsymbol", "bm", "mathcal", "mathbb", "mathsf", "mathtt", "mathfrak", "displaystyle",
                 "textstyle", "scriptstyle", "limits", "nolimits"}

_SUP = dict(zip("0123456789+-=()niabcdefghjklmoprstuvwxyz", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"))
_SUB = dict(zip("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))
_SUBFALA = {"2": " ao quadrado ", "3": " ao cubo "}


# ============================================================================ leitura de argumentos {…}
def _arg(s: str, i: int):
    """Lê UM argumento a partir de s[i]: um grupo {...} ou um único token. Devolve (conteudo, novo_i)."""
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    if i >= n:
        return "", i
    if s[i] == "{":
        nivel, j = 0, i
        while j < n:
            if s[j] == "{" and (j == 0 or s[j - 1] != "\\"):
                nivel += 1
            elif s[j] == "}" and (j == 0 or s[j - 1] != "\\"):
                nivel -= 1
                if nivel == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], n                     # chave sem fechar: pega o resto
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        return m.group(0), i + m.end()
    return s[i], i + 1


def _arg_opcional(s: str, i: int):
    """[n] logo depois de \\sqrt, se houver."""
    j = i
    while j < len(s) and s[j] == " ":
        j += 1
    if j < len(s) and s[j] == "[":
        fim = s.find("]", j)
        if fim != -1:
            return s[j + 1:fim], fim + 1
    return None, i


def _limites(s: str, i: int):
    """Lê `_{baixo}` e `^{cima}` (em qualquer ordem) logo depois de \\int / \\sum / \\lim. Devolve (baixo, cima, novo_i)."""
    baixo = cima = None
    for _ in range(2):
        m = re.match(r"\s*([_^])", s[i:])
        if not m:
            break
        valor, i = _arg(s, i + m.end())
        if m.group(1) == "_":
            baixo = valor
        else:
            cima = valor
    return baixo, cima, i


# ============================================================================ conversor (unicode e fala)
class _Estilo:
    """Duas 'línguas' de saída pro mesmo analisador: texto unicode e fala em português."""

    def __init__(self, fala: bool):
        self.fala = fala

    def sup(self, x: str) -> str:
        if self.fala:
            x = x.strip()
            if len(x) > 2 and x.startswith("(") and x.endswith(")"):        # f^{(n)}: derivada de ordem n
                return f" derivada de ordem {x[1:-1]} "
            return _SUBFALA.get(x, f" elevado a {x} ")
        if x and all(c in _SUP for c in x):
            return "".join(_SUP[c] for c in x)
        return f"^{x}" if len(x) == 1 else f"^({x})"

    def sub(self, x: str) -> str:
        if self.fala:
            return f" índice {x.strip()} "
        if x and all(c in _SUB for c in x):
            return "".join(_SUB[c] for c in x)
        return f"_{x}" if len(x) == 1 else f"_({x})"

    def frac(self, a: str, b: str) -> str:
        if self.fala:
            return f" {a.strip()} sobre {b.strip()} "
        simples = lambda t: re.fullmatch(r"[\w.,′°]+|\([^()]*\)", t.strip()) is not None
        A = a.strip() if simples(a) else f"({a.strip()})"
        B = b.strip() if simples(b) else f"({b.strip()})"
        return f"{A}/{B}"

    def raiz(self, x: str, n: str | None) -> str:
        if self.fala:
            if n is None or n.strip() == "2":
                return f" raiz quadrada de {x.strip()} "
            return f" raiz {n.strip()} de {x.strip()} "
        pre = "" if n is None or n.strip() == "2" else "".join(_SUP.get(c, c) for c in n.strip())
        return f"{pre}√({x.strip()})" if len(x.strip()) > 1 else f"{pre}√{x.strip()}"

    def acento(self, cmd: str, x: str) -> str:
        comb, falado = ACENTOS[cmd]
        if self.fala:
            return " " + falado.format(x.strip()) + " "
        x = x.strip()
        return (x[:-1] + x[-1] + comb) if x else ""

    def simbolo(self, cmd: str) -> str:
        if cmd in GREGAS:
            return " " + GREGAS[cmd][1] + " " if self.fala else GREGAS[cmd][0]
        u, f = SIMBOLOS[cmd]
        return f if self.fala else u

    def funcao(self, nome: str) -> str:
        return (" " + FUNCOES[nome] + " ") if self.fala else nome

    def char(self, c: str) -> str:
        if not self.fala:
            return c
        return {"=": " igual a ", "+": " mais ", "-": " menos ", "<": " menor que ", ">": " maior que ",
                "/": " dividido por ", "*": " vezes ", "!": " fatorial ", "|": " módulo ", "%": " por cento ",
                "^": " elevado a ", "_": " ", "&": " ", "~": " "}.get(c, c)


def _conv(s: str, st: _Estilo) -> str:
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            if not m:
                i += 1
                continue
            cmd = m.group(1)
            i += m.end()
            if cmd in ("frac", "dfrac", "tfrac", "cfrac"):
                a, i = _arg(s, i)
                b, i = _arg(s, i)
                out.append(st.frac(_conv(a, st), _conv(b, st)))
            elif cmd == "binom":
                a, i = _arg(s, i)
                b, i = _arg(s, i)
                out.append((f" {_conv(a, st)} escolhe {_conv(b, st)} " if st.fala else f"C({_conv(a, st)},{_conv(b, st)})"))
            elif cmd == "sqrt":
                opt, i = _arg_opcional(s, i)
                a, i = _arg(s, i)
                out.append(st.raiz(_conv(a, st), _conv(opt, st) if opt is not None else None))
            elif cmd in ACENTOS:
                a, i = _arg(s, i)
                out.append(st.acento(cmd, _conv(a, st)))
            elif cmd in ESTILOS_TEXTO:
                if cmd in ("displaystyle", "textstyle", "scriptstyle", "limits", "nolimits"):
                    continue
                a, i = _arg(s, i)
                out.append(_conv(a, st))
            elif cmd in ("left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr"):
                if i < n and s[i] == ".":
                    i += 1                                # \left. / \right. : delimitador invisível
            elif st.fala and cmd in ("int", "oint", "iint", "iiint", "sum", "prod") and re.match(r"\s*[_^]", s[i:]):
                baixo, cima, i = _limites(s, i)
                nome = {"int": "integral", "oint": "integral de linha fechada", "iint": "integral dupla",
                        "iiint": "integral tripla", "sum": "somatório", "prod": "produtório"}[cmd]
                partes = [f" {nome} "]
                if baixo is not None and cima is not None:
                    partes.append(f"de {_conv(baixo, st)} até {_conv(cima, st)} de ")
                elif baixo is not None:
                    partes.append(f"com {_conv(baixo, st)}, de ")
                elif cima is not None:
                    partes.append(f"até {_conv(cima, st)} de ")
                out.append("".join(partes))
            elif st.fala and cmd == "lim" and re.match(r"\s*_", s[i:]):
                baixo, _cima, i = _limites(s, i)
                out.append(f" limite quando {_conv(baixo, st)} de ")
            elif cmd in GREGAS or cmd in SIMBOLOS:
                out.append(st.simbolo(cmd))
            elif cmd in FUNCOES:
                nome = st.funcao(cmd)
                prox = s[i] if i < n else ""
                antes = out[-1][-1:] if out and out[-1] else ""
                pre = " " if (not st.fala) and antes.isalnum() else ""
                out.append(pre + nome + (" " if (not st.fala) and (prox.isalnum() or prox == "\\") else ""))
            elif cmd in (",", ";", ":", "!", " ", "quad", "qquad", "enspace", "thinspace", "negthinspace", "hspace"):
                if cmd == "hspace":
                    _, i = _arg(s, i)
                out.append("" if cmd in ("!", "negthinspace") else (" " if cmd in (",", ";", ":", " ", "thinspace", "enspace") else "  "))
            elif cmd == "\\":
                out.append("\n")
            elif cmd in ("{", "}"):
                out.append(cmd)
            elif cmd in ("begin", "end"):
                _, i = _arg(s, i)                          # nome do ambiente: some
            elif cmd in ("label", "tag", "nonumber", "notag"):
                if cmd in ("label", "tag"):
                    _, i = _arg(s, i)
            elif cmd == "%":
                out.append("%")
            else:
                out.append(cmd)                           # comando desconhecido: ao menos o nome aparece
        elif c in "^_":
            a, i = _arg(s, i + 1)
            a = _conv(a, st)
            out.append(st.sup(a) if c == "^" else st.sub(a))
        elif c in "{}":
            i += 1
        elif c == "'":
            out.append(" linha " if st.fala else "′")
            i += 1
        elif c in "&~":
            out.append(" ")
            i += 1
        else:
            out.append(st.char(c))
            i += 1
    return "".join(out)


def latex_para_unicode(latex: str) -> str:
    """LaTeX -> texto legível: `\\int_0^\\infty e^{-x^2}\\,dx = \\frac{\\sqrt{\\pi}}{2}` -> `∫₀^∞ e⁻ˣ² dx = √π/2`."""
    s = _conv((latex or "").strip(), _Estilo(fala=False))
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\(\s+", "(", s)                 # "sin(x )" -> "sin(x)"
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\(- ", "(-", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return s.strip()


def latex_para_fala(latex: str) -> str:
    """LaTeX -> como se LÊ em voz alta, em português."""
    s = _conv((latex or "").strip(), _Estilo(fala=True))
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s.strip()


# ============================================================================ achar a matemática dentro do texto
@dataclass
class Trecho:
    ini: int
    fim: int
    latex: str
    display: bool


_RE_CODIGO = re.compile(r"(```.*?(?:```|\Z)|`[^`\n]+`)", re.S)
_AMBIENTES = r"equation\*?|align\*?|aligned|gather\*?|multline\*?|eqnarray\*?|split"
_RE_MATEMATICA = re.compile(
    r"(?P<dd>\$\$(?P<dd_c>.+?)\$\$)"
    r"|(?P<env>\\begin\{(?P<env_n>" + _AMBIENTES + r")\}(?P<env_c>.+?)\\end\{(?P=env_n)\})"
    r"|(?P<cb>\\\[(?P<cb_c>.+?)\\\])"
    r"|(?P<pa>\\\((?P<pa_c>.+?)\\\))"
    r"|(?P<di>(?<![\\$\w])\$(?!\s)(?P<di_c>[^$\n]+?)(?<!\s)\$(?![\w$]))",
    re.S)


def _parece_matematica(c: str) -> bool:
    c = c.strip()
    if not c:
        return False
    if re.fullmatch(r"[\d\s.,]+", c):               # "$5" / "$10,50$": dinheiro, não matemática
        return False
    # v27: colchetes e apóstrofo contam ($S[q]$, $f'$); e um "token" curto sem espaço ($x$, $q̇$, $A$) também
    return bool(re.search(r"[\\^_{}=+\-*/<>()|\[\]']", c) or re.fullmatch(r"[^\s\d$]{1,4}", c))


def achar_trechos(texto: str) -> list:
    """Trechos de matemática ($$…$$, \\[…\\], \\begin{equation}…, \\(…\\), $…$) FORA de blocos de código."""
    proibidos = [(m.start(), m.end()) for m in _RE_CODIGO.finditer(texto or "")]

    def dentro_de_codigo(a, b):
        return any(a < pe and b > ps for ps, pe in proibidos)

    achados = []
    for m in _RE_MATEMATICA.finditer(texto or ""):
        if dentro_de_codigo(m.start(), m.end()):
            continue
        if m.group("dd") is not None:
            achados.append(Trecho(m.start(), m.end(), m.group("dd_c").strip(), True))
        elif m.group("env") is not None:
            achados.append(Trecho(m.start(), m.end(), m.group("env_c").strip(), True))
        elif m.group("cb") is not None:
            achados.append(Trecho(m.start(), m.end(), m.group("cb_c").strip(), True))
        elif m.group("pa") is not None:
            achados.append(Trecho(m.start(), m.end(), m.group("pa_c").strip(), False))
        elif m.group("di") is not None:
            c = m.group("di_c")
            if _parece_matematica(c):
                achados.append(Trecho(m.start(), m.end(), c.strip(), False))
    return achados


# LaTeX "solto" (sem $): só comandos inequívocos e só quando NÃO parece caminho de arquivo do Windows
_CMDS_SOLTOS = r"frac|dfrac|vec|hat|dot|ddot|sqrt|int|oint|sum|prod|partial|nabla|cdot|times|infty|hbar|" + "|".join(sorted(GREGAS, key=len, reverse=True))
_RE_SOLTO = re.compile(r"(?<![A-Za-z0-9:\\_])(\\(?:" + _CMDS_SOLTOS + r")\b(?:\s*\{[^{}]*\}|\s*_\{[^{}]*\}|\s*\^\{[^{}]*\})*)")


def _solto_para_unicode(trecho: str, estilo_fala: bool = False) -> str:
    return _RE_SOLTO.sub(lambda m: (latex_para_fala if estilo_fala else latex_para_unicode)(m.group(1)), trecho)


def _fora_do_codigo(texto: str, fn):
    saida, pos = [], 0
    for m in _RE_CODIGO.finditer(texto):
        saida.append(fn(texto[pos:m.start()]))
        saida.append(m.group(0))
        pos = m.end()
    saida.append(fn(texto[pos:]))
    return "".join(saida)


# ============================================================================ saneamento pro mathtext do matplotlib
def sanear_para_mathtext(latex: str) -> str:
    """O mathtext do matplotlib é um SUBCONJUNTO do LaTeX. Traduz o que dá pra traduzir."""
    s = latex
    s = re.sub(r"\\(displaystyle|textstyle|scriptstyle|limits|nolimits|nonumber|notag)\b", "", s)
    s = re.sub(r"\\(label|tag)\{[^{}]*\}", "", s)
    s = re.sub(r"\\(left|right)\.", "", s)
    s = re.sub(r"\\(bigl|bigr|Bigl|Bigr|biggl|biggr|big|Big|bigg|Bigg)\b", "", s)
    s = re.sub(r"\\(dfrac|tfrac|cfrac)\b", r"\\frac", s)
    s = re.sub(r"\\(boldsymbol|bm)\b", r"\\mathbf", s)
    s = re.sub(r"\\(mathsf|mathtt|mathfrak)\b", r"\\mathrm", s)
    s = s.replace("\\mathbb{R}", "\\mathbb{R}")

    def _texto(m):
        interno = m.group(2).replace(" ", r"\ ")
        return r"\mathrm{" + interno + "}"
    s = re.sub(r"\\(text|textrm|textbf|textit|mbox)\{([^{}]*)\}", _texto, s)
    s = re.sub(r"\\operatorname\{([^{}]*)\}", lambda m: r"\mathrm{" + m.group(1).replace(" ", r"\ ") + r"}\,", s)
    s = re.sub(r"\\oint(?![A-Za-z])\s*", r"\\oint\\!\\,\\,\\,", s)       # o círculo do \oint colava no que vinha depois
    s = re.sub(r"\\(qquad)", r"\\quad\\quad", s)
    s = s.replace(r"\,", r"\,").replace(r"\;", r"\;").replace(r"\:", r"\;")
    s = re.sub(r"\\overrightarrow\b", r"\\vec", s)
    s = re.sub(r"\\widehat\b", r"\\hat", s)
    s = re.sub(r"\\iiint", r"\\int\\!\\!\\!\\int\\!\\!\\!\\int", s)
    s = re.sub(r"\\iint", r"\\int\\!\\!\\!\\int", s)
    s = re.sub(r"\\(le|ge|ne)\b", lambda m: "\\" + {"le": "leq", "ge": "geq", "ne": "neq"}[m.group(1)], s)
    s = re.sub(r"\\implies\b", r"\\Rightarrow", s)
    s = re.sub(r"\\mapsto\b", r"\\rightarrow", s)
    s = s.replace("&", " ")
    return s.strip()


def dividir_em_linhas(latex: str) -> list:
    """`a = b \\\\ c = d` (align/gather/cases/matrizes) -> ["a = b", "c = d"]. Ambientes sem suporte viram linhas."""
    s = re.sub(r"\\begin\{(?:cases|[pbvBV]?matrix|array|aligned|align\*?|gather\*?|split|equation\*?)\}(?:\{[^{}]*\})?", "", latex)
    s = re.sub(r"\\end\{(?:cases|[pbvBV]?matrix|array|aligned|align\*?|gather\*?|split|equation\*?)\}", "", s)
    partes = [p.strip() for p in re.split(r"\\\\(?:\[[^\]]*\])?", s)]
    return [sanear_para_mathtext(p) for p in partes if p.strip()]


# ============================================================================ renderização (único ponto que usa matplotlib/PIL)
@dataclass
class EstiloImagem:
    fundo: str | None = "#10142b"        # None = transparente
    texto: str = "#eef1ff"
    tamanho: float = 22.0
    dpi: int = 200
    margem: int = 28


ESTILO_ESCURO = EstiloImagem()
ESTILO_CLARO = EstiloImagem(fundo="#ffffff", texto="#111111")
ESTILO_TRANSPARENTE = EstiloImagem(fundo=None, texto="#111111")


def _hex_rgba(h: str, alpha: int = 255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _linha_png(linha: str, estilo: EstiloImagem):
    """Uma linha de LaTeX -> imagem PIL RGBA (fundo transparente, cortada rente). Levanta exceção se o mathtext não entende."""
    import io
    from matplotlib import rcParams
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from PIL import Image
    rcParams["mathtext.fontset"] = "cm"
    fig = Figure(figsize=(1, 1), dpi=estilo.dpi)
    FigureCanvasAgg(fig)
    fig.text(0.02, 0.5, f"${linha}$", fontsize=estilo.tamanho, color=estilo.texto, va="center", ha="left")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=estilo.dpi, transparent=True, bbox_inches="tight", pad_inches=0.04)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _linha_texto_png(texto: str, estilo: EstiloImagem):
    """Plano B: o texto unicode, sem mathtext (acontece se o mathtext não entendeu a equação)."""
    import io
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from PIL import Image
    fig = Figure(figsize=(1, 1), dpi=estilo.dpi)
    FigureCanvasAgg(fig)
    fig.text(0.02, 0.5, texto, fontsize=estilo.tamanho * 0.9, color=estilo.texto, va="center", ha="left",
             family="DejaVu Sans")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=estilo.dpi, transparent=True, bbox_inches="tight", pad_inches=0.04)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def renderizar_png(latex: str, caminho, estilo: EstiloImagem = ESTILO_ESCURO) -> bool:
    """Renderiza uma equação (pode ter várias linhas) em PNG. True se salvou. Nunca levanta exceção."""
    try:
        from PIL import Image
        linhas = dividir_em_linhas(latex) or [sanear_para_mathtext(latex)]
        imagens = []
        for ln in linhas:
            try:
                imagens.append(_linha_png(ln, estilo))
            except Exception:
                imagens.append(_linha_texto_png(latex_para_unicode(ln), estilo))
        m = estilo.margem
        espaco = int(estilo.dpi * 0.12)
        largura = max(i.width for i in imagens) + 2 * m
        altura = sum(i.height for i in imagens) + espaco * (len(imagens) - 1) + 2 * m
        fundo = _hex_rgba(estilo.fundo) if estilo.fundo else (0, 0, 0, 0)
        tela = Image.new("RGBA", (largura, altura), fundo)
        y = m
        for im in imagens:
            tela.alpha_composite(im, (m, y))
            y += im.height + espaco
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        tela.save(str(caminho), "PNG")
        return True
    except Exception as e:
        print(f"[Zenith/Matemática] não consegui desenhar a equação: {type(e).__name__}: {e}")
        return False


def limpar_antigos(pasta, manter: int = 60):
    """Mantém só as `manter` imagens de equação mais novas (a pasta não cresce pra sempre)."""
    try:
        arquivos = sorted((p for p in Path(pasta).glob("eq_*.png")), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in arquivos[manter:]:
            try:
                p.unlink()
            except OSError:
                pass
    except Exception:
        pass


# ============================================================================ a resposta inteira
@dataclass
class Resultado:
    chat: str = ""                                    # o que aparece no balão (com "[Equação 1 ↓]" onde há imagem)
    historico: str = ""                               # o que fica no histórico da conversa (unicode no lugar da equação)
    fala: str = ""                                    # o que a voz lê
    imagens: list = field(default_factory=list)       # [(caminho_png, legenda)]
    equacoes: int = 0
    falhas: list = field(default_factory=list)        # números das equações cuja imagem NÃO saiu (o texto continua lá)


MAX_IMAGENS = 6
_ABERTURA = re.compile(r"\$\$|\\\[|\\\(|\\begin\{(?:" + _AMBIENTES + r")\}|(?<![\\$\w])\$(?=[^\s\d$])")


def inicio_de_matematica_aberta(texto: str):
    """Posição onde começa uma equação que ainda NÃO fechou (ex.: "... $$ \\frac{a}{" no meio do streaming), ou None.
    O portão de streaming espera ela fechar antes de liberar a frase."""
    ocupados = [(t.ini, t.fim) for t in achar_trechos(texto)] + [(m.start(), m.end()) for m in _RE_CODIGO.finditer(texto)]
    for m in _ABERTURA.finditer(texto or ""):
        if any(a <= m.start() < b for a, b in ocupados):
            continue
        return m.start()
    return None


class ConversorStream:
    """Converte texto com equações em (chat, histórico, fala), PEDAÇO POR PEDAÇO.

    v27 — o MESMO conversor serve o streaming (frase a frase, enquanto a IA ainda escreve) e a resposta final
    (processar_resposta). Por isso o texto que já saiu em streaming é exatamente o começo do texto final e nada se
    duplica. A numeração das equações ("[Equação 1 ↓]") continua de pedaço em pedaço, e o texto NÃO depende de a
    imagem ter sido desenhada com sucesso (senão o streaming e o final divergiriam)."""

    def __init__(self):
        self.n_eq = 0
        self.equacoes = []                            # [(n, latex)] — as que têm cartão de imagem

    def converter(self, texto: str):
        texto = texto or ""
        if "$" not in texto and "\\" not in texto:
            return texto, texto, texto
        chat, hist, fala = [], [], []
        pos = 0

        def _pre(trecho):
            chat.append(_fora_do_codigo(trecho, _solto_para_unicode))
            hist.append(_fora_do_codigo(trecho, _solto_para_unicode))
            fala.append(_fora_do_codigo(trecho, lambda y: _solto_para_unicode(y, True)))

        for t in achar_trechos(texto):
            _pre(texto[pos:t.ini])
            uni = latex_para_unicode(t.latex)
            falado = latex_para_fala(t.latex)
            if t.display:
                self.n_eq += 1
                if self.n_eq <= MAX_IMAGENS:
                    self.equacoes.append((self.n_eq, t.latex))
                    chat.append(f"\n[Equação {self.n_eq} ↓]  {uni}\n" if len(uni) <= 60 else f"\n[Equação {self.n_eq} ↓]\n")
                else:
                    chat.append(f"\n    {uni}\n")
                hist.append(f"\n    {uni}\n")
                fala.append(f" {falado}. ")
            else:
                chat.append(uni)
                hist.append(uni)
                fala.append(f" {falado} ")
            pos = t.fim
        _pre(texto[pos:])
        return "".join(chat), "".join(hist), re.sub(r"[ \t]{2,}", " ", "".join(fala))


def processar_resposta(texto: str, pasta, estilo: EstiloImagem = ESTILO_ESCURO, renderizar=renderizar_png,
                       agora=None) -> Resultado:
    """Transforma a resposta da IA: equações viram texto legível + imagem, e a fala ganha a leitura em português.
    Sem matemática no texto: devolve o texto igual (custo zero)."""
    texto = texto or ""
    if "$" not in texto and "\\" not in texto:
        return Resultado(chat=texto, historico=texto, fala=texto)
    conv = ConversorStream()
    chat, hist, fala = conv.converter(texto)
    imagens, falhas = [], []
    carimbo = time.strftime("%Y%m%d_%H%M%S", time.localtime(agora or time.time()))
    for n, latex in conv.equacoes:
        p = Path(pasta) / f"eq_{carimbo}_{n}.png"
        if renderizar(latex, p, estilo):
            imagens.append((str(p), f"Equação {n}"))
        else:
            falhas.append(n)
    if imagens:
        limpar_antigos(pasta)
    return Resultado(chat=chat, historico=hist, fala=fala, imagens=imagens, equacoes=conv.n_eq, falhas=falhas)
