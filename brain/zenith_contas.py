"""
Zenith — CONFERIR CONTAS (v28).

A ideia ("Verificador de contas: é barato e aproveita o ponto forte do Gemini em cálculo"): a IA escreve a conta, o
COMPUTADOR confere. Sempre que a resposta traz uma operação com resultado — "12 × 3 = 36", "(5+7)/4 = 3" — este módulo refaz
a conta com aritmética exata. Se o resultado escrito não bate, a Zenith avisa logo abaixo da resposta. Se tudo bate, fica
em silêncio (nada de ruído).

Segurança: NÃO usa `eval`. A expressão é lida por um interpretador próprio, só com números, + - * / ^ ** % e parênteses
(via `ast` com lista branca), com limite de tamanho e de potência — impossível rodar código por aqui.
Aceita o jeito brasileiro de escrever: vírgula decimal (3,14), × · ÷, ^ e % (resto), "1.000,50", unidades coladas
são ignoradas só se estiverem DEPOIS do resultado (ex.: "= 36 V").

  /conta <expressão>   — faz a conta exata na hora (sem gastar IA)

Lógica pura — testável sem rede.
"""
from __future__ import annotations

import ast
import operator
import re
from fractions import Fraction

MAX_EXPR = 120
MAX_EXPOENTE = 64
MAX_NUM = 10 ** 30

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod}


class ErroConta(Exception):
    pass


def _normalizar(expr: str) -> str:
    e = (expr or "").strip()
    e = e.replace("×", "*").replace("·", "*").replace("÷", "/").replace("−", "-").replace("–", "-").replace("^", "**").replace("x", "*") \
        if re.fullmatch(r"[\d\s.,+\-*/^×·÷−–x()%]+", e) else e
    # número brasileiro: 1.000,50 -> 1000.50 ; 3,14 -> 3.14 ; (só mexe se tiver vírgula decimal)
    e = re.sub(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+),(\d+)", lambda m: m.group(1).replace(".", "") + "." + m.group(2), e)
    e = re.sub(r"(\d),(\d)", r"\1.\2", e)
    e = re.sub(r"(?<![\d.])(\d{1,3}(?:\.\d{3}){1,})(?![\d.])", lambda m: m.group(1).replace(".", ""), e)
    return e


def _avaliar_no(no):
    if isinstance(no, ast.Expression):
        return _avaliar_no(no.body)
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)) and not isinstance(no.value, bool):
        if abs(no.value) > MAX_NUM:
            raise ErroConta("número grande demais")
        return Fraction(str(no.value))
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.UAdd, ast.USub)):
        v = _avaliar_no(no.operand)
        return v if isinstance(no.op, ast.UAdd) else -v
    if isinstance(no, ast.BinOp) and type(no.op) in _OPS:
        a, b = _avaliar_no(no.left), _avaliar_no(no.right)
        if isinstance(no.op, ast.Pow):
            if b.denominator != 1 or abs(b) > MAX_EXPOENTE:
                raise ErroConta("potência não suportada")
            if a == 0 and b < 0:
                raise ErroConta("divisão por zero")
            r = a ** int(b)
        elif isinstance(no.op, ast.Div):
            if b == 0:
                raise ErroConta("divisão por zero")
            r = a / b
        elif isinstance(no.op, ast.Mod):
            if b == 0:
                raise ErroConta("divisão por zero")
            r = a % b
        else:
            r = _OPS[type(no.op)](a, b)
        if abs(r) > MAX_NUM:
            raise ErroConta("resultado grande demais")
        return r
    raise ErroConta("expressão não suportada")


def avaliar(expr: str) -> Fraction:
    e = _normalizar(expr)
    if not e or len(e) > MAX_EXPR:
        raise ErroConta("expressão vazia ou grande demais")
    if not re.fullmatch(r"[\d\s.+\-*/()%]+", e):
        raise ErroConta("só números e + - × ÷ ^ ( ) são aceitos")
    try:
        arvore = ast.parse(e, mode="eval")
    except SyntaxError:
        raise ErroConta("expressão mal formada")
    return _avaliar_no(arvore)


def formatar(v: Fraction, casas: int = 6) -> str:
    if v.denominator == 1:
        return str(v.numerator)
    f = float(v)
    s = f"{f:.{casas}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _numero_escrito(txt: str):
    """'36', '3,14', '1.000,5' -> (Fraction, casas_decimais_escritas) ou None."""
    t = txt.strip().replace(" ", "")
    if not re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:[.,]\d+)?", t):
        return None
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", t):                    # 1.000 = mil
        t = t.replace(".", "")
    elif "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    casas = len(t.split(".")[1]) if "." in t else 0
    try:
        return Fraction(t), casas
    except ValueError:
        return None


# Uma conta escrita: <expressão com operador> = <resultado>. A expressão não atravessa palavras.
_RE_CONTA = re.compile(r"(?<![\w:/.,])(?P<expr>(?:\(?-?\d[\d.,]*\)?\s*(?:[+\-*/×·÷^x%]|\*\*)\s*){1,8}\(?-?\d[\d.,]*\)?(?:\s*(?:[+\-*/×·÷^%]|\*\*)\s*\(?-?\d[\d.,]*\)?)*)"
                       r"\s*(?:=|≈)\s*(?P<res>-?\d[\d.,]*)(?![\d.,]*\d*\s*[\*/×÷^+\-]\s*\d)")


def verificar_texto(texto: str, max_contas: int = 12) -> list:
    """Lista de problemas: [{"conta", "escrito", "correto"}]. Vazia = tudo bateu (ou nada a conferir)."""
    problemas, vistos = [], set()
    # não confere dentro de blocos de código nem de equações LaTeX
    limpo = re.sub(r"```.*?```|`[^`\n]+`|\$\$.*?\$\$|\$[^$\n]+\$", " ", texto or "", flags=re.S)
    for m in _RE_CONTA.finditer(limpo):
        expr, res = m.group("expr").strip(), m.group("res").rstrip(".,")
        chave = (expr, res)
        if chave in vistos:
            continue
        vistos.add(chave)
        if len(vistos) > max_contas:
            break
        try:
            correto = avaliar(expr)
        except ErroConta:
            continue
        esc = _numero_escrito(res)
        if esc is None:
            continue
        valor, casas = esc
        tol = Fraction(1, 2 * 10 ** casas) if casas else Fraction(1, 2)      # arredondamento no nº de casas escrito
        if casas == 0 and correto.denominator != 1:
            tol = Fraction(1, 2)
        if abs(correto - valor) > tol:
            problemas.append({"conta": " ".join(expr.split()), "escrito": res.strip(), "correto": formatar(correto)})
    return problemas


def aviso_para(problemas: list) -> str:
    if not problemas:
        return ""
    linhas = ["🧮 Conferi as contas da resposta e achei " + ("uma que não bate:" if len(problemas) == 1 else f"{len(problemas)} que não batem:")]
    for p in problemas[:5]:
        linhas.append(f"• {p['conta']} = {p['correto']} (a resposta diz {p['escrito']})")
    linhas.append("Vale conferir antes de usar — a conta aqui foi refeita pelo computador, não pela IA.")
    return "\n".join(linhas)


def comando(arg: str) -> str:
    a = (arg or "").strip()
    if not a:
        return "🧮 Use: /conta <expressão> — ex.: /conta (12,5 + 7) * 3 / 4   (aceito + - × ÷ ^ % e parênteses)"
    try:
        v = avaliar(a.split("=")[0])
    except ErroConta as e:
        return f"🧮 Não consegui fazer essa conta: {e}."
    extra = f"  (= {v.numerator}/{v.denominator} exato)" if v.denominator != 1 and v.denominator <= 10000 else ""
    return f"🧮 {a.split('=')[0].strip()} = {formatar(v, 8)}{extra}"
