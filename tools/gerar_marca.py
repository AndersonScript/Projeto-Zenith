#!/usr/bin/env python3
"""Zenith — gera a MARCA (logo, tela de abertura e imagens do instalador) por código.

    python tools/gerar_marca.py

A MARCA é o ícone do próprio Zenith (o "Z" com órbita), guardado em assets/zenith_icone_original.png. Este script só
monta a tela de abertura, as imagens do instalador e o logo horizontal AO REDOR dele — nada de ícone de terceiros ou emoji.
Para trocar a marca, substitua assets/zenith_icone_original.png (256x256, fundo transparente) e rode de novo.

Saídas:
  assets/zenith_logo.png                 a marca sozinha (256x256)
  assets/zenith_logo_horizontal.png      marca + palavra, fundo escuro (1200x360) — README e site
  body/zenith/assets/zenith_splash.png   tela de abertura do Corpo (substitui a do Godot) — 420x640
  assets/instalador_lateral.bmp          painel grande do instalador (164x314)
  assets/instalador_pequena.bmp          imagem pequena do instalador (55x55)
  site/logo.png                          versão leve para a página de downloads (256x256)

A fonte usada nas letras é a DejaVu Sans Bold (licença livre Bitstream Vera/DejaVu, permite redistribuir o desenho
resultante). Se ela não existir no seu PC, o script usa a fonte padrão do Pillow — o desenho muda um pouco.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
FUNDO = (12, 13, 15)            # fundo do ícone do Zenith
PAINEL = (24, 30, 31)
TEXTO = (248, 233, 214)         # creme do "Z"
TEXTO_2 = (160, 176, 172)
CIANO = (95, 160, 140)          # verde da órbita (usado só no brilho)
VIOLETA = (95, 160, 140)
FONTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _fonte(tam: int):
    for f in FONTES:
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _estrela(tam: int, cor_a=CIANO, cor_b=VIOLETA) -> Image.Image:
    """A marca = o ícone do dono, redimensionado. (Nome histórico da função.) Usa só até ~256 px: acima disso ficaria borrada."""
    arte = RAIZ / "assets" / "zenith_icone_original.png"
    img = Image.open(arte).convert("RGBA")
    s = tam * 4
    img = img.resize((s, s), Image.LANCZOS)
    # a arte original tem cantos escuros opacos: recorta num quadrado arredondado para não aparecer uma "caixa" no fundo
    mascara = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([s * 0.058, s * 0.058, s * 0.942, s * 0.942], radius=s * 0.205, fill=255)
    img.putalpha(mascara)
    return img.resize((tam, tam), Image.LANCZOS)


def _brilho(tam: int, cor=CIANO, forca=90) -> Image.Image:
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = tam / 2
    for i in range(40, 0, -1):
        rr = tam * 0.5 * i / 40
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=cor + (int(forca * (1 - i / 40) ** 2),))
    return img.filter(ImageFilter.GaussianBlur(tam * 0.02))


def _palavra(draw, xy, texto, fonte, cor, espaco=0, ancora="la"):
    """Escreve letra por letra com espaçamento extra (o Pillow não tem 'letter-spacing')."""
    x, y = xy
    larguras = [draw.textlength(ch, font=fonte) for ch in texto]
    total = sum(larguras) + espaco * (len(texto) - 1)
    if ancora == "ma":
        x -= total / 2
    for ch, w in zip(texto, larguras):
        draw.text((x, y), ch, font=fonte, fill=cor)
        x += w + espaco
    return total


def logo_horizontal() -> Image.Image:
    img = Image.new("RGB", (1200, 360), FUNDO)
    img.paste(_brilho(420, forca=70).convert("RGB"), (-40, -30), _brilho(420, forca=70))
    marca = _estrela(256)
    img.paste(marca, (60, 52), marca)
    d = ImageDraw.Draw(img)
    _palavra(d, (350, 85), "ZENITH", _fonte(150), TEXTO, espaco=14)
    d.text((356, 262), "assistente pessoal com avatar", font=_fonte(34), fill=TEXTO_2)
    return img


def splash() -> Image.Image:
    w, h = 420, 640
    img = Image.new("RGB", (w, h), FUNDO)
    for y in range(h):                                   # degradê vertical bem suave
        k = y / h
        cor = tuple(int(FUNDO[i] + (PAINEL[i] - FUNDO[i]) * k) for i in range(3))
        ImageDraw.Draw(img).line([(0, y), (w, y)], fill=cor)
    glow = _brilho(520, forca=80)
    img.paste(glow.convert("RGB"), (w // 2 - 260, 230 - 260), glow)
    marca = _estrela(236)
    img.paste(marca, (w // 2 - 118, 250 - 118), marca)
    d = ImageDraw.Draw(img)
    f2 = _fonte(24)
    t = "Seja bem-vindo"
    d.text(((w - d.textlength(t, font=f2)) / 2, 400), t, font=f2, fill=TEXTO)
    f3 = _fonte(13)
    t = "iniciando..."
    d.text(((w - d.textlength(t, font=f3)) / 2, h - 52), t, font=f3, fill=TEXTO_2)
    return img


def instalador_lateral() -> Image.Image:
    w, h = 164, 314
    img = Image.new("RGB", (w, h), FUNDO)
    for y in range(h):
        k = y / h
        cor = tuple(int(FUNDO[i] + (PAINEL[i] - FUNDO[i]) * k) for i in range(3))
        ImageDraw.Draw(img).line([(0, y), (w, y)], fill=cor)
    glow = _brilho(200, forca=70)
    img.paste(glow.convert("RGB"), (w // 2 - 100, 95 - 100), glow)
    marca = _estrela(128)
    img.paste(marca, (w // 2 - 64, 100 - 64), marca)
    d = ImageDraw.Draw(img)
    f = _fonte(13)
    t = "seja bem-vindo"
    d.text(((w - d.textlength(t, font=f)) / 2, 190), t, font=f, fill=TEXTO)
    return img


def instalador_pequena() -> Image.Image:
    img = Image.new("RGB", (55, 55), FUNDO)
    marca = _estrela(47)
    img.paste(marca, (4, 4), marca)
    return img


def main() -> int:
    destinos = {
        RAIZ / "assets" / "zenith_logo.png": _estrela(256),
        RAIZ / "assets" / "zenith_logo_horizontal.png": logo_horizontal(),
        RAIZ / "body" / "zenith" / "assets" / "zenith_splash.png": splash(),
        RAIZ / "assets" / "instalador_lateral.bmp": instalador_lateral(),
        RAIZ / "assets" / "instalador_pequena.bmp": instalador_pequena(),
        RAIZ / "site" / "logo.png": _estrela(256),
    }
    for caminho, img in destinos.items():
        caminho.parent.mkdir(parents=True, exist_ok=True)
        img.save(caminho)
        print("gerado:", caminho.relative_to(RAIZ), img.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
