"""
Zenith — FÓRMULAS e CÁLCULO (v26): o "caderno" de física/cálculo do Anderson dentro do chat.

Comandos (todos resolvidos aqui, SEM gastar IA — a conta é do computador, não de um modelo que pode errar):

  /latex <equação>            desenha a equação em imagem (ex.: /latex \\frac{d}{dt}\\frac{\\partial L}{\\partial \\dot q}=0)
                              modos: /latex claro ...  (preto no branco, pra imprimir / slide)
                                     /latex transparente ...  (PNG sem fundo, pra editar vídeo)
  /formula                    lista os assuntos · /formula mecanica|optica|derivadas|integrais|vetorial|ondas|maxwell
                              /formula <assunto> 2   (página 2) · /formula buscar <palavra>
  /derivar <f(x)> [em x]      derivada exata (sympy) + conferência
  /integrar <f(x)> [de a ate b]   integral exata (indefinida ou definida) + conferência derivando de volta
  /limite <f(x)> quando x->a  limite exato

Por que /derivar e /integrar existem: uma IA de linguagem "adivinha" a próxima palavra — na conta, ela às vezes erra
com muita confiança. Aqui quem faz a álgebra é o sympy, e o programa CONFERE o resultado (deriva a integral de volta;
compara numericamente). O `sympy` é opcional: sem ele, os comandos avisam como instalar e o resto segue funcionando.

Lógica pura (menos o desenho, que usa zenith_matematica.renderizar_png e o sympy opcional).
"""
from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

from brain import zenith_matematica as M

# ============================================================================ o banco de fórmulas
# (nome, latex, nota curta). Escritas pra o mathtext do matplotlib (sem ambientes não suportados).
BANCO = {
    "mecanica": ("Mecânica clássica", [
        ("2ª lei de Newton", r"\vec{F} = \frac{d\vec{p}}{dt} = m\vec{a}", "força resultante = taxa de variação do momento"),
        ("Cinemática (MRUV)", r"v = v_0 + a t \qquad x = x_0 + v_0 t + \frac{1}{2} a t^2", "aceleração constante"),
        ("Torricelli", r"v^2 = v_0^2 + 2a\,\Delta x", "sem o tempo"),
        ("Trabalho e energia cinética", r"W = \int \vec{F}\cdot d\vec{r} = \Delta K = \frac{1}{2} m v^2 - \frac{1}{2} m v_0^2", "teorema trabalho–energia"),
        ("Energia mecânica", r"E = \frac{1}{2} m v^2 + U(\vec{r}) \quad (\text{conservada se só há forças conservativas})", ""),
        ("Momento angular e torque", r"\vec{L} = \vec{r}\times\vec{p} \qquad \vec{\tau} = \vec{r}\times\vec{F} = \frac{d\vec{L}}{dt}", ""),
        ("Momento de inércia", r"I = \int r^2\,dm \qquad I = I_{cm} + M d^2", "definição e eixos paralelos"),
        ("Lagrangiana", r"L = T - V", "energia cinética menos potencial"),
        ("Euler–Lagrange", r"\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{q}_i}\right) - \frac{\partial L}{\partial q_i} = 0", "uma equação por coordenada generalizada"),
        ("Momento conjugado e Hamiltoniana", r"p_i = \frac{\partial L}{\partial \dot{q}_i} \qquad H = \sum_i p_i \dot{q}_i - L", ""),
        ("Equações de Hamilton", r"\dot{q}_i = \frac{\partial H}{\partial p_i} \qquad \dot{p}_i = -\frac{\partial H}{\partial q_i}", ""),
        ("Oscilador harmônico", r"\ddot{x} + \omega^2 x = 0 \qquad \omega = \sqrt{\frac{k}{m}} \qquad x(t) = A\cos(\omega t + \varphi)", ""),
        ("Pêndulo simples", r"\ddot{\theta} + \frac{g}{\ell}\sin\theta = 0 \qquad T \approx 2\pi\sqrt{\frac{\ell}{g}}", "T vale para pequenos ângulos"),
        ("Gravitação", r"F = G\,\frac{m_1 m_2}{r^2} \qquad U = -G\,\frac{m_1 m_2}{r}", ""),
        ("3ª lei de Kepler", r"T^2 = \frac{4\pi^2}{G M}\,a^3", ""),
        ("Centro de massa", r"\vec{R}_{cm} = \frac{1}{M}\int \vec{r}\,dm", ""),
    ]),
    "optica": ("Óptica", [
        ("Lei de Snell", r"n_1 \sin\theta_1 = n_2 \sin\theta_2", "refração"),
        ("Ângulo crítico", r"\sin\theta_c = \frac{n_2}{n_1} \quad (n_1 > n_2)", "reflexão total interna"),
        ("Lei da reflexão", r"\theta_i = \theta_r", ""),
        ("Lente delgada (Gauss)", r"\frac{1}{f} = \frac{1}{d_o} + \frac{1}{d_i} \qquad m = -\frac{d_i}{d_o}", "foco, objeto, imagem e aumento"),
        ("Equação do fabricante de lentes", r"\frac{1}{f} = (n-1)\left(\frac{1}{R_1} - \frac{1}{R_2}\right)", ""),
        ("Espelho esférico", r"\frac{1}{f} = \frac{2}{R}", ""),
        ("Young (fendas duplas)", r"d\sin\theta = m\lambda \qquad \Delta y = \frac{\lambda L}{d}", "máximos de interferência"),
        ("Rede de difração", r"d\sin\theta = m\lambda", ""),
        ("Fenda simples (mínimos)", r"a\sin\theta = m\lambda \quad (m = \pm 1, \pm 2, \dots)", ""),
        ("Critério de Rayleigh", r"\theta_{min} \approx 1{,}22\,\frac{\lambda}{D}", "resolução de uma abertura circular"),
        ("Lei de Malus", r"I = I_0 \cos^2\theta", "polarizadores"),
        ("Ângulo de Brewster", r"\tan\theta_B = \frac{n_2}{n_1}", ""),
        ("Onda", r"c = \lambda f \qquad k = \frac{2\pi}{\lambda} \qquad \omega = 2\pi f \qquad n = \frac{c}{v}", ""),
        ("Princípio de Fermat", r"\delta \int_A^B n\,ds = 0", "a luz segue o caminho de tempo estacionário"),
    ]),
    "derivadas": ("Derivadas", [
        ("Definição", r"f'(x) = \lim_{h \to 0}\frac{f(x+h) - f(x)}{h}", ""),
        ("Regra da soma e do produto", r"(f+g)' = f' + g' \qquad (fg)' = f'g + fg'", ""),
        ("Regra do quociente", r"\left(\frac{f}{g}\right)' = \frac{f'g - fg'}{g^2}", ""),
        ("Regra da cadeia", r"\frac{d}{dx} f(g(x)) = f'(g(x))\,g'(x)", ""),
        ("Potência", r"\frac{d}{dx}x^n = n\,x^{n-1}", ""),
        ("Exponencial e logaritmo", r"\frac{d}{dx}e^x = e^x \qquad \frac{d}{dx}a^x = a^x\ln a \qquad \frac{d}{dx}\ln x = \frac{1}{x}", ""),
        ("Trigonométricas", r"(\sin x)' = \cos x \qquad (\cos x)' = -\sin x \qquad (\tan x)' = \sec^2 x", ""),
        ("Trigonométricas inversas", r"(\arcsin x)' = \frac{1}{\sqrt{1-x^2}} \qquad (\arctan x)' = \frac{1}{1+x^2}", ""),
        ("Regra de L'Hôpital", r"\lim_{x\to a}\frac{f(x)}{g(x)} = \lim_{x\to a}\frac{f'(x)}{g'(x)} \quad (\frac{0}{0}\ \text{ou}\ \frac{\infty}{\infty})", ""),
        ("Série de Taylor", r"f(x) = \sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^n", ""),
        ("Maclaurin úteis", r"e^x = \sum_{n=0}^{\infty}\frac{x^n}{n!} \qquad \sin x = \sum_{n=0}^{\infty}\frac{(-1)^n x^{2n+1}}{(2n+1)!}", ""),
        ("Derivada parcial e gradiente", r"\nabla f = \left(\frac{\partial f}{\partial x}, \frac{\partial f}{\partial y}, \frac{\partial f}{\partial z}\right)", ""),
    ]),
    "integrais": ("Integrais", [
        ("Teorema fundamental do cálculo", r"\int_a^b f(x)\,dx = F(b) - F(a) \quad \text{com } F' = f", ""),
        ("Potência", r"\int x^n\,dx = \frac{x^{n+1}}{n+1} + C \quad (n \neq -1) \qquad \int \frac{1}{x}\,dx = \ln|x| + C", ""),
        ("Exponencial", r"\int e^x\,dx = e^x + C \qquad \int a^x\,dx = \frac{a^x}{\ln a} + C", ""),
        ("Trigonométricas", r"\int \sin x\,dx = -\cos x + C \qquad \int \cos x\,dx = \sin x + C \qquad \int \sec^2 x\,dx = \tan x + C", ""),
        ("Por partes", r"\int u\,dv = uv - \int v\,du", ""),
        ("Substituição", r"\int f(g(x))\,g'(x)\,dx = \int f(u)\,du \quad (u = g(x))", ""),
        ("Gaussiana", r"\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}", ""),
        ("Integral dupla (Fubini)", r"\iint_R f\,dA = \int_a^b\int_c^d f(x,y)\,dy\,dx", ""),
        ("Coordenadas polares", r"\iint f\,dA = \iint f(r\cos\theta, r\sin\theta)\,r\,dr\,d\theta", ""),
        ("Valor médio", r"\bar{f} = \frac{1}{b-a}\int_a^b f(x)\,dx", ""),
    ]),
    "vetorial": ("Cálculo vetorial", [
        ("Gradiente, divergente, rotacional", r"\nabla f \qquad \nabla\cdot\vec{F} \qquad \nabla\times\vec{F}", ""),
        ("Teorema da divergência (Gauss)", r"\oint_S \vec{F}\cdot d\vec{A} = \int_V \nabla\cdot\vec{F}\,dV", ""),
        ("Teorema de Stokes", r"\oint_C \vec{F}\cdot d\vec{\ell} = \int_S (\nabla\times\vec{F})\cdot d\vec{A}", ""),
        ("Teorema de Green", r"\oint_C (P\,dx + Q\,dy) = \iint_R\left(\frac{\partial Q}{\partial x} - \frac{\partial P}{\partial y}\right)dA", ""),
        ("Identidades", r"\nabla\times(\nabla f) = 0 \qquad \nabla\cdot(\nabla\times\vec{F}) = 0", ""),
        ("Laplaciano", r"\nabla^2 f = \frac{\partial^2 f}{\partial x^2} + \frac{\partial^2 f}{\partial y^2} + \frac{\partial^2 f}{\partial z^2}", ""),
    ]),
    "ondas": ("Ondas e oscilações", [
        ("Equação de onda", r"\frac{\partial^2 y}{\partial x^2} = \frac{1}{v^2}\frac{\partial^2 y}{\partial t^2}", ""),
        ("Onda harmônica", r"y(x,t) = A\sin(kx - \omega t + \varphi)", ""),
        ("Velocidade de fase", r"v = \frac{\omega}{k} = \lambda f", ""),
        ("Intensidade", r"I = \frac{P}{A} \propto A^2", ""),
        ("Batimento", r"f_b = |f_1 - f_2|", ""),
        ("Efeito Doppler", r"f' = f\,\frac{v \pm v_o}{v \mp v_s}", ""),
        ("Oscilador amortecido", r"m\ddot{x} + b\dot{x} + kx = 0", ""),
    ]),
    "maxwell": ("Equações de Maxwell", [
        ("Lei de Gauss", r"\nabla\cdot\vec{E} = \frac{\rho}{\varepsilon_0}", ""),
        ("Gauss do magnetismo", r"\nabla\cdot\vec{B} = 0", ""),
        ("Lei de Faraday", r"\nabla\times\vec{E} = -\frac{\partial\vec{B}}{\partial t}", ""),
        ("Lei de Ampère–Maxwell", r"\nabla\times\vec{B} = \mu_0\vec{J} + \mu_0\varepsilon_0\frac{\partial\vec{E}}{\partial t}", ""),
        ("Força de Lorentz", r"\vec{F} = q(\vec{E} + \vec{v}\times\vec{B})", ""),
    ]),
}
ALIAS = {"mecanica": "mecanica", "mecânica": "mecanica", "classica": "mecanica", "optica": "optica", "óptica": "optica",
         "derivada": "derivadas", "derivadas": "derivadas", "integral": "integrais", "integrais": "integrais",
         "vetorial": "vetorial", "vetores": "vetorial", "ondas": "ondas", "onda": "ondas", "maxwell": "maxwell",
         "eletromagnetismo": "maxwell", "oscilacoes": "ondas"}
POR_PAGINA = 6


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()


def listar_assuntos() -> str:
    linhas = ["📐 Fórmulas — escolha um assunto (ex.: /formula mecanica):"]
    for chave, (titulo, itens) in BANCO.items():
        linhas.append(f"• /formula {chave} — {titulo} ({len(itens)} fórmulas)")
    linhas.append("• /formula buscar <palavra> — procura em todas (ex.: /formula buscar lagrange)")
    linhas.append("• /latex <equação> — desenha qualquer equação LaTeX · /derivar · /integrar · /limite — conta exata")
    return "\n".join(linhas)


def pagina_do_assunto(chave: str, pagina: int = 1) -> tuple:
    """(titulo, itens_da_pagina, total_paginas)."""
    titulo, itens = BANCO[chave]
    total = max(1, (len(itens) + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(max(1, pagina), total)
    ini = (pagina - 1) * POR_PAGINA
    return titulo, itens[ini:ini + POR_PAGINA], total


def buscar(termo: str) -> list:
    t = _sem_acento(termo)
    achados = []
    for chave, (titulo, itens) in BANCO.items():
        for nome, latex, nota in itens:
            if t in _sem_acento(nome) or t in _sem_acento(nota) or t in _sem_acento(titulo):
                achados.append((titulo, nome, latex, nota))
    return achados


# ============================================================================ a folha (imagem com várias fórmulas)
def _fonte_rotulo(tamanho: int):
    from PIL import ImageFont
    try:
        import matplotlib
        from matplotlib import font_manager
        return ImageFont.truetype(font_manager.findfont("DejaVu Sans"), tamanho)
    except Exception:
        return ImageFont.load_default()


def renderizar_folha(titulo: str, itens: list, caminho, estilo: M.EstiloImagem = M.ESTILO_ESCURO) -> bool:
    """Uma imagem com várias fórmulas, cada uma com o nome acima. itens = [(nome, latex, nota)]."""
    try:
        import io
        from PIL import Image, ImageDraw
        fonte = _fonte_rotulo(int(estilo.dpi * 0.11))
        fonte_t = _fonte_rotulo(int(estilo.dpi * 0.16))
        cor_rotulo = (150, 160, 200, 255) if estilo.fundo and estilo.fundo != "#ffffff" else (90, 90, 90, 255)
        cor_titulo = M._hex_rgba(estilo.texto)
        blocos = []
        for nome, latex, _nota in itens:
            png = io.BytesIO()
            tmp = Path(caminho).with_suffix(".tmp.png")
            est = M.EstiloImagem(fundo=None, texto=estilo.texto, tamanho=estilo.tamanho * 0.85, dpi=estilo.dpi, margem=4)
            if not M.renderizar_png(latex, tmp, est):
                continue
            im = Image.open(tmp).convert("RGBA")
            blocos.append((nome, im))
            try:
                tmp.unlink()
            except OSError:
                pass
        if not blocos:
            return False
        m = estilo.margem
        lar = max(max(im.width for _, im in blocos), 700) + 2 * m
        alt = m + int(estilo.dpi * 0.30) + sum(int(estilo.dpi * 0.20) + im.height + int(estilo.dpi * 0.10) for _, im in blocos) + m
        fundo = M._hex_rgba(estilo.fundo) if estilo.fundo else (0, 0, 0, 0)
        tela = Image.new("RGBA", (lar, alt), fundo)
        d = ImageDraw.Draw(tela)
        y = m
        d.text((m, y), titulo, font=fonte_t, fill=cor_titulo)
        y += int(estilo.dpi * 0.30)
        for nome, im in blocos:
            d.text((m, y), nome, font=fonte, fill=cor_rotulo)
            y += int(estilo.dpi * 0.20)
            tela.alpha_composite(im, (m + 12, y))
            y += im.height + int(estilo.dpi * 0.10)
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        tela.save(str(caminho), "PNG")
        return True
    except Exception as e:
        print(f"[Zenith/Fórmulas] não consegui montar a folha: {type(e).__name__}: {e}")
        return False


# ============================================================================ cálculo exato (sympy opcional)
_PERMITIDO = re.compile(r"^[A-Za-z0-9_+\-*/^().,\s=<>|!]+$")
_PROIBIDO = re.compile(r"(__|\.[A-Za-z_]|\blambda\b|\bimport\b|\bexec\b|\beval\b|\bopen\b|\bos\b|\bsys\b|\bgetattr\b|\bglobals\b)")


class ErroCalculo(Exception):
    pass


def _sympy():
    try:
        import sympy
        return sympy
    except Exception:
        raise ErroCalculo("O cálculo exato usa a biblioteca sympy, que ainda não está instalada neste Zenith. "
                          "Rodando do código-fonte: `pip install sympy`. No .exe, é preciso recompilar com ela "
                          "(veja docs/historico/GUIA_v26_PASSO_A_PASSO.md).")


def _parse(expr: str, simbolos=None):
    sp = _sympy()
    from sympy.parsing.sympy_parser import (parse_expr, standard_transformations, implicit_multiplication_application,
                                            convert_xor)
    expr = (expr or "").strip().replace("−", "-").replace("×", "*").replace("÷", "/").replace("·", "*")
    expr = expr.replace("π", "pi").replace("∞", "oo").replace("²", "**2").replace("³", "**3")
    expr = re.sub(r"\bln\b", "log", expr)
    expr = re.sub(r"\bsen\b", "sin", expr)
    expr = re.sub(r"\btg\b", "tan", expr)
    if not expr:
        raise ErroCalculo("Faltou a expressão.")
    if not _PERMITIDO.match(expr) or _PROIBIDO.search(expr):
        raise ErroCalculo("Só aceito expressões matemáticas simples (números, letras, + - * / ^ ( ), sin, cos, exp, log...).")
    if len(expr) > 300:
        raise ErroCalculo("Expressão grande demais.")
    trans = standard_transformations + (implicit_multiplication_application, convert_xor)
    try:
        return parse_expr(expr, transformations=trans, local_dict=dict(simbolos or {}), evaluate=True)
    except Exception as e:
        raise ErroCalculo(f"Não consegui entender a expressão ({type(e).__name__}). Use ** ou ^ para potência e escreva "
                          f"as funções assim: sin(x), cos(x), exp(x), log(x), sqrt(x).")


def _variavel(sp, expr, pedida: str | None):
    if pedida:
        return sp.Symbol(pedida)
    livres = sorted(expr.free_symbols, key=lambda s: s.name)
    return sp.Symbol("x") if (not livres or sp.Symbol("x") in livres) else livres[0]


def _num(sp, valor, casas=6):
    try:
        v = sp.N(valor, 12)
        if v.is_real:
            return f"{float(v):.{casas}g}"
    except Exception:
        pass
    return ""


def derivar(expr: str, var: str | None = None) -> dict:
    sp = _sympy()
    f = _parse(expr)
    x = _variavel(sp, f, var)
    d = sp.simplify(sp.diff(f, x))
    # conferência numérica: (f(x+h) - f(x-h)) / 2h no ponto 1.3
    ok = None
    try:
        h, p = 1e-6, 1.3
        subs = {s: 1.1 for s in f.free_symbols}
        subs[x] = p
        aprox = (float(f.subs({**subs, x: p + h})) - float(f.subs({**subs, x: p - h}))) / (2 * h)
        exato = float(d.subs(subs))
        ok = abs(aprox - exato) <= 1e-4 * max(1.0, abs(exato))
    except Exception:
        ok = None
    return {"entrada": f, "var": x, "resultado": d, "latex": rf"\frac{{d}}{{d{sp.latex(x)}}}\left[{sp.latex(f)}\right] = {sp.latex(d)}",
            "conferido": ok, "como": "derivada simbólica; conferida numericamente por diferença central"}


def integrar(expr: str, var: str | None = None, a: str | None = None, b: str | None = None) -> dict:
    sp = _sympy()
    f = _parse(expr)
    x = _variavel(sp, f, var)
    if a is not None and b is not None:
        A, B = _parse(a), _parse(b)
        r = sp.simplify(sp.integrate(f, (x, A, B)))
        if r.has(sp.Integral):
            raise ErroCalculo("Não achei uma forma fechada pra essa integral definida — dá pra resolver numericamente.")
        lat = rf"\int_{{{sp.latex(A)}}}^{{{sp.latex(B)}}} {sp.latex(f)}\,d{sp.latex(x)} = {sp.latex(r)}"
        conf = None
        try:
            from sympy import Integral
            num = float(Integral(f, (x, A, B)).evalf(15))
            conf = abs(num - float(sp.N(r))) <= 1e-6 * max(1.0, abs(num))
        except Exception:
            pass
        return {"entrada": f, "var": x, "resultado": r, "latex": lat, "conferido": conf, "definida": True,
                "aproximado": _num(sp, r), "como": "integral definida exata; conferida pela integração numérica"}
    F = sp.integrate(f, x)
    if F.has(sp.Integral):
        raise ErroCalculo("Não achei uma primitiva em forma fechada pra essa função.")
    conf = sp.simplify(sp.diff(F, x) - f) == 0
    lat = rf"\int {sp.latex(f)}\,d{sp.latex(x)} = {sp.latex(sp.simplify(F))} + C"
    return {"entrada": f, "var": x, "resultado": F, "latex": lat, "conferido": conf, "definida": False,
            "como": "primitiva exata; conferida derivando de volta (F' − f = 0)"}


def limite(expr: str, ponto: str, var: str | None = None, lado: str = "") -> dict:
    sp = _sympy()
    f = _parse(expr)
    x = _variavel(sp, f, var)
    p = _parse(ponto)
    r = sp.limit(f, x, p, dir={"+": "+", "-": "-"}.get(lado, "+-"))
    lat = rf"\lim_{{{sp.latex(x)} \to {sp.latex(p)}}} {sp.latex(f)} = {sp.latex(r)}"
    return {"entrada": f, "var": x, "resultado": r, "latex": lat, "conferido": None, "como": "limite simbólico"}


def _texto_resultado(nome: str, r: dict) -> str:
    sp = _sympy()
    uni = M.latex_para_unicode(r["latex"])
    sel = ""
    if r.get("conferido") is True:
        sel = "✔ conferi: bate."
    elif r.get("conferido") is False:
        sel = "⚠️ a conferência NÃO bateu — desconfie desse resultado e me avise."
    extra = f"\n≈ {r['aproximado']}" if r.get("aproximado") else ""
    return f"🧮 {nome}\n{uni}{extra}\n{sel} ({r['como']})".strip()


# ============================================================================ interpretador dos comandos
def _modo_estilo(texto: str):
    m = re.match(r"^(claro|transparente|escuro)\s+(.*)$", texto.strip(), re.S | re.I)
    if not m:
        return M.ESTILO_ESCURO, texto.strip()
    modo = m.group(1).lower()
    return ({"claro": M.ESTILO_CLARO, "transparente": M.ESTILO_TRANSPARENTE}.get(modo, M.ESTILO_ESCURO)), m.group(2).strip()


def _caminho(pasta, prefixo: str) -> Path:
    return Path(pasta) / f"eq_{time.strftime('%Y%m%d_%H%M%S')}_{prefixo}.png"


def analisar_comando(nome: str, arg: str):
    """Chamado por zenith_commands. Devolve None (não é nosso) ou {"resposta": txt, "acao": "matematica", "args": {...}}."""
    nome = nome.lower()
    if nome == "latex":
        if not arg.strip():
            return {"resposta": "📐 Use assim: /latex \\frac{d}{dt}\\frac{\\partial L}{\\partial \\dot q} = \\frac{\\partial L}{\\partial q}\n"
                                "Modos: /latex claro … (preto no branco) · /latex transparente … (PNG sem fundo)", "acao": None}
        return {"resposta": "", "acao": "matematica", "args": {"tipo": "latex", "texto": arg}}
    if nome in ("formula", "fórmula", "formulas", "fórmulas"):
        a = arg.strip()
        if not a:
            return {"resposta": listar_assuntos(), "acao": None}
        m = re.match(r"^(?:buscar|procurar)\s+(.+)$", a, re.I)
        if m:
            return {"resposta": "", "acao": "matematica", "args": {"tipo": "formula_busca", "texto": m.group(1)}}
        partes = a.split()
        chave = ALIAS.get(_sem_acento(partes[0]))
        if not chave:
            return {"resposta": f"Não conheço o assunto '{partes[0]}'.\n\n" + listar_assuntos(), "acao": None}
        pag = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 1
        return {"resposta": "", "acao": "matematica", "args": {"tipo": "formula", "assunto": chave, "pagina": pag}}
    if nome in ("derivar", "derivada"):
        if not arg.strip():
            return {"resposta": "🧮 Use assim: /derivar x**2*sin(x)   ou   /derivar exp(-t^2) em t", "acao": None}
        m = re.match(r"^(.*?)\s+em\s+([A-Za-z]\w*)\s*$", arg.strip(), re.I)
        return {"resposta": "", "acao": "matematica",
                "args": {"tipo": "derivar", "expr": (m.group(1) if m else arg).strip(), "var": m.group(2) if m else None}}
    if nome in ("integrar", "integral"):
        if not arg.strip():
            return {"resposta": "🧮 Use assim: /integrar x**2   ·   /integrar sin(x) de 0 ate pi   ·   /integrar exp(-x^2) de -oo ate oo", "acao": None}
        m = re.match(r"^(.*?)\s+de\s+(\S+)\s+(?:ate|até|a)\s+(\S+)\s*$", arg.strip(), re.I)
        if m:
            return {"resposta": "", "acao": "matematica",
                    "args": {"tipo": "integrar", "expr": m.group(1).strip(), "a": m.group(2), "b": m.group(3)}}
        m2 = re.match(r"^(.*?)\s+em\s+([A-Za-z]\w*)\s*$", arg.strip(), re.I)
        return {"resposta": "", "acao": "matematica",
                "args": {"tipo": "integrar", "expr": (m2.group(1) if m2 else arg).strip(), "var": m2.group(2) if m2 else None}}
    if nome in ("limite", "lim"):
        m = re.match(r"^(.*?)\s+(?:quando\s+)?([A-Za-z]\w*)\s*(?:->|→|tende a)\s*(\S+?)([+-]?)\s*$", arg.strip(), re.I)
        if not m:
            return {"resposta": "🧮 Use assim: /limite sin(x)/x quando x->0   ·   /limite (1+1/n)^n quando n->oo", "acao": None}
        return {"resposta": "", "acao": "matematica",
                "args": {"tipo": "limite", "expr": m.group(1).strip(), "var": m.group(2), "ponto": m.group(3),
                         "lado": m.group(4)}}
    return None


def executar(args: dict, pasta) -> dict:
    """Roda o pedido (pode demorar ~1–2 s: desenho e/ou sympy). Devolve {"texto": str, "imagens": [(caminho, legenda)]}.
    Nunca levanta exceção."""
    try:
        tipo = args.get("tipo")
        pasta = Path(pasta)
        if tipo == "latex":
            estilo, latex = _modo_estilo(args.get("texto", ""))
            latex = re.sub(r"^\s*\$\$?|\$\$?\s*$", "", latex).strip()
            p = _caminho(pasta, "latex")
            ok = M.renderizar_png(latex, p, estilo)
            uni = M.latex_para_unicode(latex)
            fala = M.latex_para_fala(latex)
            if ok:
                return {"texto": f"📐 {uni}\n\nLaTeX (pra copiar):\n{latex}", "imagens": [(str(p), "Equação")], "fala": fala}
            return {"texto": f"📐 {uni}\n\n(não consegui desenhar a imagem; o LaTeX está acima e o texto legível aqui.)",
                    "imagens": [], "fala": fala}
        if tipo == "formula":
            titulo, itens, total = pagina_do_assunto(args["assunto"], int(args.get("pagina", 1)))
            pag = min(max(1, int(args.get("pagina", 1))), total)
            p = _caminho(pasta, f"{args['assunto']}_{pag}")
            ok = renderizar_folha(f"{titulo} — página {pag}/{total}", itens, p)
            linhas = [f"• {nome}" + (f" — {nota}" if nota else "") for nome, _l, nota in itens]
            rodape = f"\n\n(página {pag} de {total}" + (f" — veja a próxima com /formula {args['assunto']} {pag + 1})" if pag < total else ")")
            txt = f"📐 {titulo} — página {pag}/{total}\n" + "\n".join(linhas) + rodape
            return {"texto": txt, "imagens": [(str(p), f"{titulo} {pag}/{total}")] if ok else [],
                    "fala": f"{titulo}, página {pag} de {total}. São {len(itens)} fórmulas: " + ", ".join(n for n, _l, _no in itens) + "."}
        if tipo == "formula_busca":
            achados = buscar(args.get("texto", ""))
            if not achados:
                return {"texto": f"Não achei fórmula com '{args.get('texto', '')}'. Veja os assuntos com /formula.", "imagens": []}
            achados = achados[:POR_PAGINA]
            p = _caminho(pasta, "busca")
            ok = renderizar_folha(f"Busca: {args.get('texto', '')}", [(f"{t} · {n}", l, no) for t, n, l, no in achados], p)
            linhas = [f"• {t} · {n}" for t, n, _l, _no in achados]
            return {"texto": "📐 Achei:\n" + "\n".join(linhas), "imagens": [(str(p), "Busca de fórmulas")] if ok else [],
                    "fala": f"Achei {len(achados)} fórmula" + ("s" if len(achados) != 1 else "") + ": " + ", ".join(n for _t, n, _l, _no in achados) + "."}
        if tipo in ("derivar", "integrar", "limite"):
            if tipo == "derivar":
                r = derivar(args["expr"], args.get("var"))
                nome = "Derivada"
            elif tipo == "integrar":
                r = integrar(args["expr"], args.get("var"), args.get("a"), args.get("b"))
                nome = "Integral definida" if r.get("definida") else "Integral indefinida"
            else:
                r = limite(args["expr"], args["ponto"], args.get("var"), args.get("lado", ""))
                nome = "Limite"
            p = _caminho(pasta, tipo)
            ok = M.renderizar_png(r["latex"], p)
            sel = " Conferi: bate." if r.get("conferido") is True else (" Atenção: a conferência não bateu." if r.get("conferido") is False else "")
            return {"texto": _texto_resultado(nome, r) + f"\n\nLaTeX: {r['latex']}", "imagens": [(str(p), nome)] if ok else [],
                    "fala": f"{nome}. " + M.latex_para_fala(r["latex"]) + "." + sel}
        return {"texto": "❌ Pedido de matemática desconhecido.", "imagens": []}
    except ErroCalculo as e:
        return {"texto": f"🧮 {e}", "imagens": []}
    except Exception as e:
        return {"texto": f"❌ Deu erro na conta: {type(e).__name__}: {e}", "imagens": []}
