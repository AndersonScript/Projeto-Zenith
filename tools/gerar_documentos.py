"""Gera os documentos do projeto em Word (.docx) a partir dos textos em Markdown.

Por que existe: o documento conceitual e o histórico são escritos em Markdown (fácil de revisar e de
versionar no Git), mas precisam chegar às pessoas em Word, com capa, sumário, tabelas e tipografia
decente. Este script faz a ponte sem depender de Word instalado.

Uso:
    py -3 tools/gerar_documentos.py

Saída:
    docs/<Nome>.docx                       (cópia para o repositório)
    site/docs/<Nome>.docx + <Nome>.md      (o que o site entrega no download)

O Markdown aceito é o subconjunto usado nos documentos do projeto: títulos (#, ##, ###),
parágrafos, listas (- e 1.), tabelas (| a | b |), citações (>), blocos de código (```), **negrito**,
_cursiva_ e `código` na linha.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
SITE_DOCS = RAIZ / "site" / "docs"
# Os textos-fonte ficam em docs/interno: eles citam a instituição e o autor, e a edição pública do
# projeto não leva dado pessoal do dono (regra conferida por tests/test_v1_4). O que vai para o site
# é só o Word pronto, em site/docs.
FONTES = RAIZ / "docs" / "interno" / "documentos"
CAPA = RAIZ / "docs" / "interno" / "capa.json"

ACENTO = RGBColor(0xC2, 0x6A, 0x1E)
CINZA = RGBColor(0x5C, 0x5C, 0x66)
TEXTO = RGBColor(0x14, 0x14, 0x18)

# ------------------------------------------------------------------ os dois documentos a gerar
DOCUMENTOS = [
    {
        "origem": FONTES / "DOCUMENTO_DO_PROJETO.md",
        "arquivo": "Projeto_Zenith_Documento_Conceitual_2.0",
        "titulo": "PROJETO ZENITH",
        "subtitulo": "Especificação Conceitual de um Assistente Pessoal com Avatar, Multimodal e Local",
        "versao": "Versão 2.0 — 01/11/2026",
        "nota": "Documento de concepção, atualizado com o que já existe no programa. "
                "Onde algo não foi testado, está dito com essas palavras.",
    },
    {
        "origem": FONTES / "HISTORICO_DE_MUDANCAS.md",
        "arquivo": "Historico_de_Mudancas_Zenith",
        "titulo": "ZENITH — HISTÓRICO DE MUDANÇAS",
        "subtitulo": "Do primeiro protótipo até 01/11/2026",
        "versao": "Versão 1.0 — 01/11/2026",
        "nota": "Registro de cada rodada: o que entrou, o que foi provado e o que ficou pendente.",
    },
]

def _ler_capa() -> dict:
    """Dados pessoais da capa ficam em docs/interno/capa.json (fora da edição pública)."""
    padrao = {"instituicao": "", "curso": "", "autor": "Anderson", "autor_linhas": [],
              "cidade": "São Paulo", "ano": "2026"}
    try:
        dados = json.loads(CAPA.read_text(encoding="utf-8-sig"))
        if isinstance(dados, dict):
            padrao.update({k: v for k, v in dados.items() if k in padrao})
    except Exception:
        pass
    return padrao


CAPA_DADOS = _ler_capa()
AUTOR = CAPA_DADOS["autor"]
AUTOR_LINHAS = list(CAPA_DADOS["autor_linhas"])


# ------------------------------------------------------------------ utilidades de formatação
def _fonte(padrao: str = "Segoe UI") -> None:
    """Ajusta a fonte do estilo Normal (python-docx não aceita nome de fonte só pelo atributo)."""
    for nome in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3", "List Bullet",
                 "List Number", "Quote", "Caption"):
        try:
            estilo = Document().styles[nome]
        except KeyError:
            continue
        estilo.font.name = padrao
        rpr = estilo.element.get_or_add_rPr()
        fontes = rpr.find(qn("w:rFonts"))
        if fontes is None:
            fontes = OxmlElement("w:rFonts")
            rpr.append(fontes)
        for atributo in ("w:ascii", "w:hAnsi", "w:cs"):
            fontes.set(qn(atributo), padrao)


def _margens(doc: Document) -> None:
    for secao in doc.sections:
        secao.page_width, secao.page_height = Cm(21), Cm(29.7)
        secao.top_margin = Cm(2.4)
        secao.bottom_margin = Cm(2.2)
        secao.left_margin = Cm(2.6)
        secao.right_margin = Cm(2.4)


def _linha_horizontal(paragrafo) -> None:
    ppr = paragrafo._p.get_or_add_pPr()
    borda = OxmlElement("w:pBdr")
    baixo = OxmlElement("w:bottom")
    baixo.set(qn("w:val"), "single")
    baixo.set(qn("w:sz"), "6")
    baixo.set(qn("w:space"), "6")
    baixo.set(qn("w:color"), "C26A1E")
    borda.append(baixo)
    ppr.append(borda)


def _sombra(celula, cor: str = "F4F0E9") -> None:
    tcpr = celula._tc.get_or_add_tcPr()
    sombra = OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:color"), "auto")
    sombra.set(qn("w:fill"), cor)
    tcpr.append(sombra)


def _rodape(doc: Document, titulo: str) -> None:
    for secao in doc.sections:
        paragrafo = secao.footer.paragraphs[0]
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragrafo.text = ""
        corrida = paragrafo.add_run(f"{titulo}  ·  Projeto Zenith  ·  página ")
        corrida.font.size = Pt(8)
        corrida.font.color.rgb = CINZA
        campo = OxmlElement("w:fldSimple")
        campo.set(qn("w:instr"), "PAGE")
        paragrafo._p.append(campo)


# ------------------------------------------------------------------ conversão do Markdown
NEGRITO = re.compile(r"\*\*(.+?)\*\*")
CURSIVA = re.compile(r"(?<!\*)_([^_]+)_(?!\*)")
CODIGO = re.compile(r"`([^`]+)`")


def _escrever_com_marcacao(paragrafo, texto: str) -> None:
    """Escreve o texto respeitando **negrito**, _cursiva_ e `código` na mesma linha."""
    pedacos = []
    resto = texto
    padrao = re.compile(r"(\*\*.+?\*\*|(?<!\*)_[^_]+_(?!\*)|`[^`]+`)")
    for parte in padrao.split(resto):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**"):
            pedacos.append(("bold", parte[2:-2]))
        elif parte.startswith("`") and parte.endswith("`"):
            pedacos.append(("code", parte[1:-1]))
        elif parte.startswith("_") and parte.endswith("_") and len(parte) > 2:
            pedacos.append(("italic", parte[1:-1]))
        else:
            pedacos.append(("normal", parte))
    for tipo, valor in pedacos:
        corrida = paragrafo.add_run(valor)
        if tipo == "bold":
            corrida.bold = True
        elif tipo == "italic":
            corrida.italic = True
        elif tipo == "code":
            corrida.font.name = "Consolas"
            corrida.font.size = Pt(9.5)
            corrida.font.color.rgb = RGBColor(0x8A, 0x45, 0x10)


def _tabela(doc: Document, linhas: list[list[str]]) -> None:
    colunas = max(len(linha) for linha in linhas)
    tabela = doc.add_table(rows=0, cols=colunas)
    tabela.style = "Table Grid"
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    for pos, linha in enumerate(linhas):
        celulas = tabela.add_row().cells
        for i in range(colunas):
            texto = linha[i] if i < len(linha) else ""
            paragrafo = celulas[i].paragraphs[0]
            paragrafo.paragraph_format.space_after = Pt(2)
            paragrafo.paragraph_format.space_before = Pt(2)
            _escrever_com_marcacao(paragrafo, texto)
            for corrida in paragrafo.runs:
                corrida.font.size = Pt(9)
                if pos == 0:
                    corrida.bold = True
                    corrida.font.color.rgb = TEXTO
                    _sombra(celulas[i])
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def _capa(doc: Document, cfg: dict) -> None:
    vazio = doc.add_paragraph()
    vazio.paragraph_format.space_after = Pt(60)

    if CAPA_DADOS["instituicao"]:
        instituicao = doc.add_paragraph()
        instituicao.alignment = WD_ALIGN_PARAGRAPH.CENTER
        corrida = instituicao.add_run(CAPA_DADOS["instituicao"])
        corrida.bold = True
        corrida.font.size = Pt(11)
        corrida.font.color.rgb = CINZA

    if CAPA_DADOS["curso"]:
        curso = doc.add_paragraph()
        curso.alignment = WD_ALIGN_PARAGRAPH.CENTER
        curso.add_run(CAPA_DADOS["curso"]).font.size = Pt(10)
        curso.runs[0].font.color.rgb = CINZA

    doc.add_paragraph().paragraph_format.space_after = Pt(50)

    titulo = doc.add_paragraph()
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    corrida = titulo.add_run(cfg["titulo"])
    corrida.bold = True
    corrida.font.size = Pt(30)
    corrida.font.color.rgb = TEXTO

    subtitulo = doc.add_paragraph()
    subtitulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitulo.paragraph_format.space_before = Pt(6)
    corrida = subtitulo.add_run(cfg["subtitulo"])
    corrida.italic = True
    corrida.font.size = Pt(13)
    corrida.font.color.rgb = ACENTO

    regua = doc.add_paragraph()
    regua.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _linha_horizontal(regua)
    regua.paragraph_format.space_before = Pt(18)

    doc.add_paragraph().paragraph_format.space_after = Pt(46)

    for texto, tamanho, negrito in [("Idealizador e Desenvolvedor", 9, False),
                                    (AUTOR, 14, True)] + [(linha, 9, False) for linha in AUTOR_LINHAS]:
        paragrafo = doc.add_paragraph()
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        corrida = paragrafo.add_run(texto)
        corrida.bold = negrito
        corrida.font.size = Pt(tamanho)
        corrida.font.color.rgb = TEXTO if negrito else CINZA
        paragrafo.paragraph_format.space_after = Pt(2)

    doc.add_paragraph().paragraph_format.space_after = Pt(60)

    for texto in (CAPA_DADOS["cidade"], CAPA_DADOS["ano"], cfg["versao"]):
        paragrafo = doc.add_paragraph()
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        corrida = paragrafo.add_run(texto)
        corrida.font.size = Pt(10)
        corrida.font.color.rgb = CINZA

    aviso = doc.add_paragraph()
    aviso.alignment = WD_ALIGN_PARAGRAPH.CENTER
    aviso.paragraph_format.space_before = Pt(28)
    corrida = aviso.add_run(cfg["nota"])
    corrida.italic = True
    corrida.font.size = Pt(9)
    corrida.font.color.rgb = CINZA

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _corpo(doc: Document, linhas: list[str]) -> None:
    i = 0
    total = len(linhas)
    primeiro_h1_visto = False
    while i < total:
        linha = linhas[i].rstrip()
        sem_espaco = linha.strip()

        if not sem_espaco:
            i += 1
            continue

        # blocos de código
        if sem_espaco.startswith("```"):
            if not primeiro_h1_visto:
                primeiro_h1_visto = True
                i += 1
                continue
            i += 1
            codigo = []
            while i < total and not linhas[i].strip().startswith("```"):
                codigo.append(linhas[i].rstrip("\n"))
                i += 1
            paragrafo = doc.add_paragraph()
            paragrafo.paragraph_format.left_indent = Cm(0.4)
            paragrafo.paragraph_format.space_before = Pt(4)
            paragrafo.paragraph_format.space_after = Pt(8)
            corrida = paragrafo.add_run("\n".join(codigo))
            corrida.font.name = "Consolas"
            corrida.font.size = Pt(8.5)
            corrida.font.color.rgb = RGBColor(0x33, 0x33, 0x3A)
            i += 1
            continue

        # tabelas
        if sem_espaco.startswith("|") and i + 1 < total and re.match(r"^\|[\s:|-]+\|?\s*$", linhas[i + 1].strip()):
            linhas_tabela = []
            while i < total and linhas[i].strip().startswith("|"):
                bruta = linhas[i].strip().strip("|")
                if not re.match(r"^[\s:|-]+$", bruta):
                    linhas_tabela.append([c.strip() for c in bruta.split("|")])
                i += 1
            if linhas_tabela:
                _tabela(doc, linhas_tabela)
            continue

        # títulos
        if sem_espaco.startswith("#"):
            nivel = len(sem_espaco) - len(sem_espaco.lstrip("#"))
            texto = sem_espaco[nivel:].strip()
            if nivel == 1 and not primeiro_h1_visto:
                primeiro_h1_visto = True          # o título já está na capa
                i += 1
                continue
            if nivel == 1 and texto.startswith("Projeto Zenith"):
                i += 1
                continue
            if texto.startswith("Especificação Conceitual") or texto.startswith("Do primeiro protótipo"):
                i += 1
                continue
            titulo = doc.add_heading("", level=min(max(nivel - 1, 1), 3))
            titulo.paragraph_format.space_before = Pt(14 if nivel <= 2 else 10)
            titulo.paragraph_format.space_after = Pt(6)
            corrida = titulo.add_run(texto)
            corrida.font.color.rgb = TEXTO if nivel > 2 else ACENTO
            corrida.font.size = Pt({2: 15, 3: 12.5}.get(nivel, 11))
            i += 1
            continue

        # separadores
        if sem_espaco in ("---", "***", "___"):
            paragrafo = doc.add_paragraph()
            _linha_horizontal(paragrafo)
            paragrafo.paragraph_format.space_before = Pt(2)
            paragrafo.paragraph_format.space_after = Pt(8)
            i += 1
            continue

        # citação
        if sem_espaco.startswith(">"):
            texto = sem_espaco.lstrip("> ").strip()
            paragrafo = doc.add_paragraph()
            paragrafo.paragraph_format.left_indent = Cm(0.5)
            paragrafo.paragraph_format.space_before = Pt(4)
            paragrafo.paragraph_format.space_after = Pt(8)
            _escrever_com_marcacao(paragrafo, texto)
            for corrida in paragrafo.runs:
                corrida.italic = True
                corrida.font.color.rgb = CINZA
            i += 1
            continue

        # listas
        if re.match(r"^[-*]\s+", sem_espaco):
            texto = re.sub(r"^[-*]\s+", "", sem_espaco)
            paragrafo = doc.add_paragraph(style="List Bullet")
            paragrafo.paragraph_format.space_after = Pt(2)
            _escrever_com_marcacao(paragrafo, texto)
            i += 1
            continue

        if re.match(r"^\d+\.\s+", sem_espaco):
            texto = re.sub(r"^\d+\.\s+", "", sem_espaco)
            paragrafo = doc.add_paragraph(style="List Number")
            paragrafo.paragraph_format.space_after = Pt(2)
            _escrever_com_marcacao(paragrafo, texto)
            i += 1
            continue

        # parágrafo comum (junta linhas seguidas do mesmo bloco)
        bloco = [sem_espaco]
        i += 1
        while i < total:
            seguinte = linhas[i].strip()
            if (not seguinte or seguinte.startswith(("|", "#", ">", "```", "---"))
                    or re.match(r"^[-*]\s+", seguinte) or re.match(r"^\d+\.\s+", seguinte)):
                break
            bloco.append(seguinte)
            i += 1
        paragrafo = doc.add_paragraph()
        paragrafo.paragraph_format.space_after = Pt(7)
        paragrafo.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _escrever_com_marcacao(paragrafo, " ".join(bloco))


def gerar(cfg: dict) -> Path:
    origem: Path = cfg["origem"]
    if not origem.exists():
        raise FileNotFoundError(f"não achei {origem}")

    doc = Document()
    _fonte()
    _margens(doc)
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.styles["Normal"].paragraph_format.line_spacing = 1.18

    _capa(doc, cfg)
    _corpo(doc, origem.read_text(encoding="utf-8").splitlines())
    _rodape(doc, cfg["titulo"].replace(" — HISTÓRICO DE MUDANÇAS", ""))

    DOCS.mkdir(parents=True, exist_ok=True)
    SITE_DOCS.mkdir(parents=True, exist_ok=True)

    destino = DOCS / f"{cfg['arquivo']}.docx"
    doc.save(destino)
    shutil.copy2(destino, SITE_DOCS / destino.name)
    return destino


def main() -> int:
    print("Gerando os documentos do Zenith...\n")
    for cfg in DOCUMENTOS:
        destino = gerar(cfg)
        tamanho = destino.stat().st_size / 1024
        print(f"  OK  {destino.relative_to(RAIZ)}  ({tamanho:.0f} KB)")
        print(f"      site/docs/{destino.name}")
    print("\nPronto. Suba a pasta site/ (com site/docs/) para o site publicar os arquivos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
