"""
Zenith — criação de imagens de alto nível (v21).

Por que existe: no teste do Anderson a Zenith escreveu um script de meme que só DEFINIA a
função `criar_meme(...)` (nunca chamou) e ainda exigia uma imagem-base que não existia — então
"o programa não funcionou". Modelos menores erram esse tipo de coisa o tempo todo. Aqui estão
funções prontas, de UMA linha, que sempre produzem uma imagem de verdade (sem precisar de arquivo
nenhum de entrada), salvam em `creations/` e imprimem o caminho.

Como a IA usa (dentro de <executar_python>):

    from brain.zenith_img import meme, cartaz, gradiente, colagem, citacao
    meme("QUANDO O CÓDIGO RODA", "DE PRIMEIRA")             # fundo gerado, texto grande com contorno
    cartaz("Feira de Ciências", "Colégio Exemplo • sexta 19h", tema="neon")
    citacao("A imaginação é mais importante que o conhecimento.", "Einstein", tema="oceano")

Cada função devolve o caminho do arquivo e imprime `IMAGEM_CRIADA: <caminho>`.
Só usa Pillow (já é dependência do projeto). Nunca levanta erro por falta de fonte/pasta.
"""
import os
import random
import re
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEMAS = {
    "neon":     ("#0b1020", "#7b2ff7", "#00e5ff"),
    "oceano":   ("#03253d", "#0a7ea4", "#bff0ff"),
    "por_do_sol": ("#2b1055", "#ff6a3d", "#ffd36e"),
    "floresta": ("#08301c", "#2e9e5b", "#d6ffc9"),
    "rosa":     ("#3a0b2e", "#d63384", "#ffd1e8"),
    "mono":     ("#101010", "#4a4a4a", "#f2f2f2"),
    "papel":    ("#f4ecd8", "#e2d4b0", "#3b2f1d"),
}
_FONTES_NEGRITO = ["impact.ttf", "Impact.ttf", "arialbd.ttf", "segoeuib.ttf", "calibrib.ttf",
                   "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf"]
_FONTES_NORMAL = ["segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
                  "FreeSans.ttf"]


def pasta_criacoes() -> Path:
    """Pasta onde as criações da IA ficam (a mesma de Configurações). Se não der pra descobrir,
    usa a pasta atual — nunca falha."""
    try:
        from brain.zenith_settings import CREATION_DIR
        p = Path(CREATION_DIR)
    except Exception:
        p = Path(os.environ.get("ZENITH_PASTA_CRIACOES") or Path.cwd())
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = Path.cwd()
    return p


def fonte(tamanho: int, negrito: bool = True):
    for nome in (_FONTES_NEGRITO if negrito else _FONTES_NORMAL):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    try:                                          # Pillow >= 10.1: fonte padrão escalável
        return ImageFont.load_default(size=tamanho)
    except TypeError:
        return ImageFont.load_default()


def _cor(c):
    if isinstance(c, str):
        c = c.lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c)[:3]


def _tema(tema):
    return TEMAS.get(str(tema).lower().replace(" ", "_"), TEMAS["neon"])


def gradiente(largura: int = 1080, altura: int = 1080, cores=("#0b1020", "#7b2ff7"), direcao: str = "vertical"):
    """Imagem com degradê. direcao: 'vertical', 'horizontal' ou 'diagonal'."""
    largura, altura = max(2, int(largura)), max(2, int(altura))
    a, b = _cor(cores[0]), _cor(cores[-1])
    try:                                              # rápido (numpy já é dependência do projeto)
        import numpy as np
        xs = np.linspace(0.0, 1.0, largura)[None, :]
        ys = np.linspace(0.0, 1.0, altura)[:, None]
        if direcao == "horizontal":
            t = np.broadcast_to(xs, (altura, largura))
        elif direcao == "diagonal":
            t = (xs + ys) / 2.0
        else:
            t = np.broadcast_to(ys, (altura, largura))
        canais = [(a[i] + (b[i] - a[i]) * t) for i in range(3)]
        return Image.fromarray(np.stack(canais, axis=-1).astype("uint8"), "RGB")
    except ImportError:                               # plano B sem numpy
        img = Image.new("RGB", (largura, altura))
        px = img.load()
        for y in range(altura):
            for x in range(largura):
                if direcao == "horizontal":
                    t = x / (largura - 1)
                elif direcao == "diagonal":
                    t = (x / (largura - 1) + y / (altura - 1)) / 2
                else:
                    t = y / (altura - 1)
                px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
        return img


def fundo_decorado(largura: int, altura: int, tema: str = "neon", semente=None):
    """Degradê + círculos suaves, pra não ficar um fundo chato. Determinístico por semente."""
    c0, c1, _ = _tema(tema)
    base = gradiente(largura, altura, (c0, c1), "diagonal").convert("RGBA")
    rnd = random.Random(semente if semente is not None else 7)
    camada = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for _ in range(7):
        r = rnd.randint(min(largura, altura) // 8, min(largura, altura) // 3)
        x, y = rnd.randint(-r // 2, largura), rnd.randint(-r // 2, altura)
        cor = _cor(_tema(tema)[2]) + (rnd.randint(18, 46),)
        d.ellipse((x - r, y - r, x + r, y + r), fill=cor)
    camada = camada.filter(ImageFilter.GaussianBlur(max(2, min(largura, altura) // 60)))
    return Image.alpha_composite(base, camada).convert("RGB")


def _medir(draw, texto, fnt, contorno=0):
    x0, y0, x1, y1 = draw.textbbox((0, 0), texto, font=fnt, stroke_width=contorno)
    return x1 - x0, y1 - y0


def quebrar_texto(draw, texto: str, fnt, largura_max: int, contorno: int = 0) -> list:
    linhas = []
    for paragrafo in str(texto).split("\n"):
        atual = ""
        for palavra in paragrafo.split():
            teste = (atual + " " + palavra).strip()
            if _medir(draw, teste, fnt, contorno)[0] <= largura_max or not atual:
                atual = teste
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
    return [l for l in linhas if l != ""] or [""]


def _ajustar(draw, texto, largura_max, altura_max, tamanho_max, negrito=True, contorno_fator=0.07):
    """Maior tamanho de fonte em que o texto quebrado cabe na caixa."""
    tam = int(tamanho_max)
    while tam >= 12:
        fnt = fonte(tam, negrito)
        cont = max(0, int(tam * contorno_fator))
        linhas = quebrar_texto(draw, texto, fnt, largura_max, cont)
        alt_linha = _medir(draw, "Ág", fnt, cont)[1]
        total = int(alt_linha * 1.12 * len(linhas))
        larg = max(_medir(draw, l, fnt, cont)[0] for l in linhas)
        if total <= altura_max and larg <= largura_max:
            return fnt, linhas, cont, alt_linha
        tam -= max(2, tam // 14)
    fnt = fonte(12, negrito)
    return fnt, quebrar_texto(draw, texto, fnt, largura_max), 1, _medir(draw, "Ág", fnt)[1]


def texto_centralizado(img, texto, caixa, tamanho_max=120, cor="#ffffff", contorno_cor="#000000",
                       negrito=True, contorno_fator=0.07, alinhar_vertical="meio"):
    """Escreve `texto` centralizado dentro de `caixa=(x0,y0,x1,y1)`, ajustando o tamanho pra caber."""
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = caixa
    fnt, linhas, cont, alt = _ajustar(draw, texto, x1 - x0, y1 - y0, tamanho_max, negrito, contorno_fator)
    passo = int(alt * 1.12)
    total = passo * len(linhas)
    if alinhar_vertical == "topo":
        y = y0
    elif alinhar_vertical == "base":
        y = y1 - total
    else:
        y = y0 + (y1 - y0 - total) // 2
    for linha in linhas:
        w, _h = _medir(draw, linha, fnt, cont)
        draw.text((x0 + (x1 - x0 - w) // 2, y), linha, font=fnt, fill=_cor(cor), stroke_width=cont,
                  stroke_fill=_cor(contorno_cor))
        y += passo
    return img


def salvar(img, nome: str = "", pasta=None, formato: str = "PNG") -> str:
    """Salva em creations/ (nome único) e imprime `IMAGEM_CRIADA: <caminho>`."""
    pasta = Path(pasta) if pasta else pasta_criacoes()
    pasta.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w\-]+", "_", nome or time.strftime("imagem_%Y%m%d_%H%M%S"), flags=re.UNICODE).strip("_") or "imagem"
    ext = ".png" if formato.upper() == "PNG" else ".jpg"
    destino = pasta / (base if base.lower().endswith(ext) else base + ext)
    k = 1
    while destino.exists():
        k += 1
        destino = pasta / f"{destino.stem.rsplit('_', 1)[0] if k > 2 else destino.stem}_{k}{ext}"
    img.convert("RGB").save(destino, formato.upper())
    print(f"IMAGEM_CRIADA: {destino}")
    return str(destino)


def _abrir_fundo(fundo, largura):
    if fundo and os.path.isfile(str(fundo)):
        try:
            im = Image.open(fundo).convert("RGB")
            k = largura / im.width
            return im.resize((largura, max(1, int(im.height * k))))
        except Exception:
            return None
    return None


def meme(texto_topo: str = "", texto_base: str = "", fundo=None, saida: str = "", largura: int = 900,
         tema: str = "neon") -> str:
    """Meme clássico: texto branco GRANDE com contorno preto em cima e embaixo.
    `fundo` é opcional (caminho de uma imagem); sem ele, gera um fundo decorado. Sempre cria a imagem."""
    largura = int(max(300, min(largura, 2000)))
    im = _abrir_fundo(fundo, largura)
    if im is None:
        im = fundo_decorado(largura, largura if not fundo else int(largura * 0.8), tema, semente=len(texto_topo) + len(texto_base))
        d = ImageDraw.Draw(im)
        cx, cy, r = largura // 2, im.height // 2, largura // 6
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_cor(_tema(tema)[2]), width=max(4, largura // 120))
        d.ellipse((cx - r // 3, cy - r // 3, cx - r // 3 + r // 6, cy - r // 3 + r // 6), fill=_cor(_tema(tema)[2]))
        d.ellipse((cx + r // 3, cy - r // 3, cx + r // 3 + r // 6, cy - r // 3 + r // 6), fill=_cor(_tema(tema)[2]))
        d.arc((cx - r // 2, cy - r // 4, cx + r // 2, cy + r // 2), 20, 160, fill=_cor(_tema(tema)[2]), width=max(4, largura // 120))
    h = im.height
    margem = int(largura * 0.04)
    faixa = int(h * 0.30)
    if texto_topo:
        texto_centralizado(im, texto_topo.upper(), (margem, margem, largura - margem, margem + faixa),
                           tamanho_max=int(largura * 0.14), alinhar_vertical="topo")
    if texto_base:
        texto_centralizado(im, texto_base.upper(), (margem, h - margem - faixa, largura - margem, h - margem),
                           tamanho_max=int(largura * 0.14), alinhar_vertical="base")
    return salvar(im, saida or "meme")


def cartaz(titulo: str, subtitulo: str = "", tema: str = "neon", saida: str = "", largura: int = 1080,
           altura: int = 1350) -> str:
    """Cartaz/pôster vertical com título grande e subtítulo."""
    largura, altura = int(max(300, min(largura, 3000))), int(max(300, min(altura, 3000)))
    im = fundo_decorado(largura, altura, tema, semente=len(titulo))
    c_destaque = _tema(tema)[2]
    d = ImageDraw.Draw(im)
    m = int(largura * 0.08)
    d.rectangle((m, m, largura - m, altura - m), outline=_cor(c_destaque), width=max(3, largura // 220))
    texto_centralizado(im, titulo, (m * 2, int(altura * 0.22), largura - m * 2, int(altura * 0.62)),
                       tamanho_max=int(largura * 0.16), cor=c_destaque, contorno_cor=_tema(tema)[0],
                       contorno_fator=0.04)
    if subtitulo:
        d.line((largura * 0.3, altura * 0.66, largura * 0.7, altura * 0.66), fill=_cor(c_destaque), width=max(3, largura // 260))
        texto_centralizado(im, subtitulo, (m * 2, int(altura * 0.69), largura - m * 2, int(altura * 0.84)),
                           tamanho_max=int(largura * 0.06), cor="#ffffff", contorno_cor=_tema(tema)[0],
                           negrito=False, contorno_fator=0.03)
    return salvar(im, saida or "cartaz")


def citacao(texto: str, autor: str = "", tema: str = "oceano", saida: str = "", tamanho: int = 1080) -> str:
    """Imagem quadrada com uma frase e o autor."""
    tamanho = int(max(300, min(tamanho, 3000)))
    im = fundo_decorado(tamanho, tamanho, tema, semente=len(texto))
    m = int(tamanho * 0.1)
    texto_centralizado(im, "“" + texto.strip() + "”", (m, m, tamanho - m, int(tamanho * 0.74)),
                       tamanho_max=int(tamanho * 0.1), cor="#ffffff", contorno_cor=_tema(tema)[0],
                       contorno_fator=0.02)
    if autor:
        texto_centralizado(im, "— " + autor, (m, int(tamanho * 0.78), tamanho - m, int(tamanho * 0.9)),
                           tamanho_max=int(tamanho * 0.055), cor=_tema(tema)[2], contorno_cor=_tema(tema)[0],
                           negrito=False, contorno_fator=0.02)
    return salvar(im, saida or "citacao")


def colagem(imagens, colunas: int = 2, tamanho_celula: int = 480, saida: str = "") -> str:
    """Junta várias imagens (lista de caminhos) numa grade."""
    abertas = []
    for p in imagens:
        try:
            abertas.append(Image.open(p).convert("RGB"))
        except Exception:
            continue
    if not abertas:
        raise ValueError("nenhuma das imagens pôde ser aberta")
    colunas = max(1, min(int(colunas), len(abertas)))
    linhas = (len(abertas) + colunas - 1) // colunas
    cel = int(tamanho_celula)
    tela = Image.new("RGB", (colunas * cel, linhas * cel), (16, 16, 24))
    for i, im in enumerate(abertas):
        im.thumbnail((cel - 8, cel - 8))
        x = (i % colunas) * cel + (cel - im.width) // 2
        y = (i // colunas) * cel + (cel - im.height) // 2
        tela.paste(im, (x, y))
    return salvar(tela, saida or "colagem")


# v26 — cores da aparência da Zenith. ANTES: o padrão era "cabelo escuro, olhos vermelhos" (outro avatar) — por isso o
# autorretrato nunca parecia com a Zenith real (cabelo azul-turquesa). Agora: o que a IA passar > config/aparencia.json
# (comando /aparencia) > este padrão (as cores do avatar atual).
APARENCIA_PADRAO = {"cabelo": "#7ad0e8", "olhos": "#3ccfb4", "roupa": "#8ed3d8", "detalhe": "#6a4332"}


def _arquivo_aparencia() -> Path:
    try:
        from brain.zenith_settings import CONFIG_DIR
        return Path(CONFIG_DIR) / "aparencia.json"
    except Exception:
        return Path(os.environ.get("ZENITH_PASTA_CRIACOES") or Path.cwd()) / "aparencia.json"


def ler_aparencia() -> dict:
    """Cores salvas com /aparencia (cabelo, olhos, roupa, detalhe) sobre o padrão."""
    import json
    cores = dict(APARENCIA_PADRAO)
    try:
        dados = json.loads(_arquivo_aparencia().read_text(encoding="utf-8"))
        for k in cores:
            v = str(dados.get(k, "")).strip()
            if re.fullmatch(r"#?[0-9a-fA-F]{6}", v):
                cores[k] = "#" + v.lstrip("#")
    except Exception:
        pass
    return cores


def salvar_aparencia(novas: dict) -> dict:
    """Guarda as cores (só chaves válidas, só #rrggbb) e devolve o conjunto final."""
    import json
    atuais = ler_aparencia()
    for k, v in (novas or {}).items():
        if k in atuais and re.fullmatch(r"#?[0-9a-fA-F]{6}", str(v).strip()):
            atuais[k] = "#" + str(v).strip().lstrip("#")
    arq = _arquivo_aparencia()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(atuais, ensure_ascii=False, indent=2), encoding="utf-8")
    return atuais


def apagar_aparencia() -> None:
    try:
        _arquivo_aparencia().unlink()
    except OSError:
        pass


def autorretrato(nome: str = "Zenith", cabelo: str = None, olhos: str = None, roupa: str = None,
                 detalhe: str = None, tema: str = "oceano", saida: str = "", tamanho: int = 1024) -> str:
    """v23 — um retrato estilizado (estilo anime, desenhado com formas, sem imagem de entrada) pra quando pedem
    "desenhe você mesma". É um DESENHO SIMPLES por código (Pillow) — não é uma captura do avatar 3D nem uma IA de
    imagem; não diga que é "a sua VRM". Cores: o que você passar > /aparencia > padrão (cabelo azul-turquesa,
    olhos verde-água, moletom azul-claro). Salva em creations e imprime IMAGEM_CRIADA."""
    cores = ler_aparencia()
    cabelo, olhos, roupa, detalhe = cabelo or cores["cabelo"], olhos or cores["olhos"], roupa or cores["roupa"], detalhe or cores["detalhe"]
    tamanho = int(max(400, min(tamanho, 2400)))
    S = 2                                             # desenha em 2x e reduz: bordas suaves
    W = tamanho * S
    im = fundo_decorado(W, W, tema, semente=len(nome)).convert("RGBA")
    d = ImageDraw.Draw(im)
    pele, c_olho = "#f3dccf", _cor(olhos)

    def el(cx, cy, rx, ry, cor, **k):
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=cor, **k)

    cx = W // 2
    # ombros e jaqueta
    d.pieslice((cx - W * 0.46, W * 0.72, cx + W * 0.46, W * 1.35), 180, 360, fill=roupa)
    d.polygon([(cx - W * 0.09, W * 0.78), (cx, W * 0.97), (cx + W * 0.09, W * 0.78)], fill=detalhe)
    d.rectangle((cx - W * 0.012, W * 0.82, cx + W * 0.012, W), fill=roupa)
    # pescoço
    d.rectangle((cx - W * 0.055, W * 0.62, cx + W * 0.055, W * 0.78), fill=pele)
    # cabelo (atrás), rosto, franja
    el(cx, W * 0.42, W * 0.215, W * 0.255, cabelo)
    el(cx, W * 0.47, W * 0.175, W * 0.215, pele)
    franja = [(cx - W * 0.19, W * 0.41), (cx - W * 0.12, W * 0.43), (cx - W * 0.06, W * 0.37), (cx, W * 0.44),
              (cx + W * 0.06, W * 0.37), (cx + W * 0.12, W * 0.43), (cx + W * 0.19, W * 0.41),
              (cx + W * 0.2, W * 0.28), (cx, W * 0.2), (cx - W * 0.2, W * 0.28)]
    d.polygon(franja, fill=cabelo)
    # olhos
    for lado in (-1, 1):
        ex, ey = cx + lado * W * 0.075, W * 0.50
        el(ex, ey, W * 0.038, W * 0.045, "#ffffff")
        el(ex, ey, W * 0.026, W * 0.036, c_olho)
        el(ex, ey, W * 0.012, W * 0.02, "#12101a")
        el(ex - W * 0.008, ey - W * 0.012, W * 0.007, W * 0.007, "#ffffff")
        d.line((ex - W * 0.045, ey - W * 0.052, ex + W * 0.045, ey - W * 0.052), fill=cabelo, width=int(W * 0.007))
    # nariz e boca discretas
    d.line((cx, W * 0.545, cx - W * 0.006, W * 0.56), fill="#d9b8a8", width=int(W * 0.004))
    d.arc((cx - W * 0.03, W * 0.565, cx + W * 0.03, W * 0.6), 20, 160, fill="#b0605c", width=int(W * 0.005))
    out = im.convert("RGB").resize((tamanho, tamanho), Image.LANCZOS)
    if nome:
        texto_centralizado(out, nome, (int(tamanho * 0.1), int(tamanho * 0.9), int(tamanho * 0.9), int(tamanho * 0.98)),
                           tamanho_max=int(tamanho * 0.06), cor="#ffffff", contorno_cor="#000000", contorno_fator=0.04)
    return salvar(out, saida or "autorretrato")
