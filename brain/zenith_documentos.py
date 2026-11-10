"""
Zenith — CRIAR WORD e EXCEL (v28).

O pedido do Anderson: ela "ter acesso a Word, Excel entre outros". LER já vem com `zenith_anexos` (docx/xlsx/pptx/pdf).
Aqui ela ganha o CRIAR: um documento Word (.docx) ou uma planilha Excel (.xlsx) NOVOS, sempre em `creations/documentos/`
com nome novo — nunca mexe num arquivo seu que já existe. Feito só com a biblioteca padrão (zipfile + XML): não precisa
instalar python-docx nem openpyxl, então funciona igual dentro do .exe.

Word  — texto em Markdown simples:  # título · ## subtítulo · ### · "- item" · "1. item" · **negrito** · *itálico* ·
        tabela "| a | b |" (linha 2 "|---|---|") · linha em branco separa parágrafos.
Excel — JSON {"abas": {"Notas": [["Nome", "Nota"], ["Ana", 9.5]]}} ou CSV/tabela Markdown. Texto que começa com "="
        vira fórmula (ex.: "=SUM(B2:B10)").

Etiqueta da IA:  <criar_documento tipo="docx|xlsx" nome="Relatório">conteúdo</criar_documento>  (sempre pede aprovação)
Lógica pura — testável sem Word/Excel (o teste lê de volta com os leitores de zenith_anexos).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MAX_BLOCOS = 4000
MAX_LINHAS_XLSX = 20000
MAX_ABAS = 12


class ErroDocumento(Exception):
    """Mensagem já em português, pronta pro chat."""


def _nome_seguro(nome: str, padrao: str) -> str:
    n = re.sub(r"[^\w\- ]+", "", Path(str(nome or "")).stem, flags=re.U).strip().replace(" ", "_")[:60]
    return n or padrao


def _caminho_novo(pasta: str, nome: str, ext: str) -> str:
    os.makedirs(pasta, exist_ok=True)
    base = os.path.join(pasta, f"{nome}.{ext}")
    n, c = 2, base
    while os.path.exists(c):
        c = os.path.join(pasta, f"{nome}_{n}.{ext}")
        n += 1
    return c


# ============================================================================================ WORD
_CT_DOCX = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '</Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
         '</Relationships>')
_DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '</Relationships>')


def _estilo(id_, nome, tam, negrito=True, cor="1F2A44", antes=240, depois=80):
    b = "<w:b/>" if negrito else ""
    return (f'<w:style w:type="paragraph" w:styleId="{id_}"><w:name w:val="{nome}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>'
            f'<w:pPr><w:spacing w:before="{antes}" w:after="{depois}"/></w:pPr>'
            f'<w:rPr>{b}<w:color w:val="{cor}"/><w:sz w:val="{tam}"/></w:rPr></w:style>')


_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
           '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
           + _estilo("Title", "Title", 48, True, "0B3C5D", 0, 200)
           + _estilo("Heading1", "heading 1", 34, True, "0B3C5D", 360, 120)
           + _estilo("Heading2", "heading 2", 28, True, "1F5F8B", 280, 100)
           + _estilo("Heading3", "heading 3", 24, True, "2E7D9A", 200, 80)
           + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
             '<w:top w:val="single" w:sz="4" w:space="0" w:color="999999"/><w:left w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
             '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="999999"/><w:right w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
             '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="999999"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
             '</w:tblBorders></w:tblPr></w:style>'
           '</w:styles>')

_RE_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|\*[^*\n]+\*)")


def _runs(texto: str) -> str:
    """Texto com **negrito** e *itálico* -> <w:r>…</w:r> (o resto é escapado)."""
    saida = []
    for pedaco in _RE_INLINE.split(texto):
        if not pedaco:
            continue
        if pedaco.startswith("**") and pedaco.endswith("**") and len(pedaco) > 4:
            rpr, t = "<w:rPr><w:b/></w:rPr>", pedaco[2:-2]
        elif pedaco.startswith("*") and pedaco.endswith("*") and len(pedaco) > 2:
            rpr, t = "<w:rPr><w:i/></w:rPr>", pedaco[1:-1]
        else:
            rpr, t = "", pedaco
        saida.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>')
    return "".join(saida)


def _par(texto: str, estilo: str = "", recuo: int = 0) -> str:
    ppr = ""
    if estilo or recuo:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{estilo}"/>' if estilo else "") + \
              (f'<w:ind w:left="{recuo}" w:hanging="260"/>' if recuo else "") + "</w:pPr>"
    return f"<w:p>{ppr}{_runs(texto)}</w:p>"


def _tabela(linhas: list) -> str:
    n = max(len(l) for l in linhas)
    xml = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/></w:tblPr>']
    for i, l in enumerate(linhas):
        xml.append("<w:tr>")
        for c in range(n):
            txt = l[c] if c < len(l) else ""
            if i == 0:
                txt = f"**{txt}**" if txt and not txt.startswith("**") else txt
            xml.append(f"<w:tc><w:tcPr><w:tcW w:w=\"0\" w:type=\"auto\"/></w:tcPr><w:p>{_runs(txt)}</w:p></w:tc>")
        xml.append("</w:tr>")
    xml.append("</w:tbl><w:p/>")
    return "".join(xml)


def _celulas_md(linha: str) -> list:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def _eh_separador_tabela(linha: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", linha))


def markdown_para_blocos_xml(texto: str) -> list:
    linhas = (texto or "").replace("\r\n", "\n").split("\n")
    blocos, i, paragrafo = [], 0, []

    def fechar():
        if paragrafo:
            blocos.append(_par(" ".join(paragrafo)))
            paragrafo.clear()

    while i < len(linhas):
        l = linhas[i].rstrip()
        if not l.strip():
            fechar()
        elif re.match(r"^#{1,3}\s+", l):
            fechar()
            nivel = len(re.match(r"^(#+)", l).group(1))
            blocos.append(_par(re.sub(r"^#{1,3}\s+", "", l), f"Heading{nivel}"))
        elif re.match(r"^\s*[-*•]\s+", l):
            fechar()
            blocos.append(_par("• " + re.sub(r"^\s*[-*•]\s+", "", l), "", 360))
        elif re.match(r"^\s*\d+[.)]\s+", l):
            fechar()
            m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", l)
            blocos.append(_par(f"{m.group(1)}. {m.group(2)}", "", 360))
        elif l.lstrip().startswith("|") and i + 1 < len(linhas) and _eh_separador_tabela(linhas[i + 1]):
            fechar()
            tabela = [_celulas_md(l)]
            i += 2
            while i < len(linhas) and linhas[i].lstrip().startswith("|"):
                tabela.append(_celulas_md(linhas[i]))
                i += 1
            blocos.append(_tabela(tabela))
            continue
        else:
            paragrafo.append(l.strip())
        i += 1
        if len(blocos) > MAX_BLOCOS:
            raise ErroDocumento("📄 Documento grande demais pra um pedido só.")
    fechar()
    return blocos


def criar_docx(caminho: str, texto: str, titulo: str = "") -> str:
    blocos = markdown_para_blocos_xml(texto)
    if titulo:
        blocos.insert(0, _par(titulo, "Title"))
    if not blocos:
        raise ErroDocumento("📄 O documento está vazio — escreva o conteúdo.")
    corpo = "".join(blocos)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + corpo + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
           '</w:body></w:document>')
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT_DOCX)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
    return caminho


# ============================================================================================ EXCEL
_CT_XLSX_BASE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                 '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>')
_STYLES_XLSX = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                '</styleSheet>')


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _numero(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        t = v.strip().replace(" ", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", t):
            return t
        if re.fullmatch(r"-?\d+,\d+", t):               # 3,14 (pt-BR) -> 3.14
            return t.replace(",", ".")
    return None


def _celula(ref: str, v, cabecalho: bool) -> str:
    estilo = ' s="1"' if cabecalho else ""
    if v is None or v == "":
        return ""
    if isinstance(v, str) and v.startswith("=") and len(v) > 1:
        return f'<c r="{ref}"{estilo}><f>{escape(v[1:])}</f></c>'
    n = _numero(v)
    if n is not None and not cabecalho:
        return f'<c r="{ref}"{estilo}><v>{n}</v></c>'
    return f'<c r="{ref}"{estilo} t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def _xml_aba(linhas: list) -> str:
    larguras = {}
    for r in linhas[:200]:
        for c, v in enumerate(r):
            larguras[c] = max(larguras.get(c, 8), min(60, len(str(v)) + 2))
    cols = "".join(f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>' for c, w in sorted(larguras.items()))
    xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if cols:
        xml.append(f"<cols>{cols}</cols>")
    xml.append("<sheetData>")
    for i, r in enumerate(linhas, 1):
        cel = "".join(_celula(f"{_col(c)}{i}", v, i == 1) for c, v in enumerate(r))
        xml.append(f'<row r="{i}">{cel}</row>')
    xml.append("</sheetData></worksheet>")
    return "".join(xml)


def interpretar_planilha(conteudo: str) -> dict:
    """JSON {"abas": {...}} | {"Aba": [[...]]} | lista de listas | tabela Markdown | CSV -> {"nome_aba": [[...], ...]}."""
    t = (conteudo or "").strip()
    t = re.sub(r"^```(?:json|csv)?\s*|\s*```$", "", t, flags=re.I).strip()
    if not t:
        raise ErroDocumento("📊 A planilha está vazia.")
    if t[0] in "{[":
        try:
            d = json.loads(t)
        except json.JSONDecodeError as e:
            raise ErroDocumento(f"📊 Não entendi o JSON da planilha ({e.msg}).")
        if isinstance(d, list):
            d = {"Planilha1": d}
        if isinstance(d, dict) and isinstance(d.get("abas"), dict):
            d = d["abas"]
        if not isinstance(d, dict):
            raise ErroDocumento("📊 O JSON da planilha precisa ser {\"abas\": {\"Nome\": [[...], ...]}}.")
        abas = {}
        for nome, linhas in list(d.items())[:MAX_ABAS]:
            if not isinstance(linhas, list):
                raise ErroDocumento(f"📊 A aba '{nome}' precisa ser uma lista de linhas.")
            abas[str(nome)] = [list(l) if isinstance(l, (list, tuple)) else [l] for l in linhas[:MAX_LINHAS_XLSX]]
        return abas
    linhas_txt = t.splitlines()
    if sum(1 for l in linhas_txt if l.lstrip().startswith("|")) >= 2:
        tabela = [_celulas_md(l) for l in linhas_txt if l.lstrip().startswith("|") and not _eh_separador_tabela(l)]
        return {"Planilha1": tabela[:MAX_LINHAS_XLSX]}
    amostra = t[:2000]
    delim = ";" if amostra.count(";") > amostra.count(",") else ("\t" if amostra.count("\t") > amostra.count(",") else ",")
    return {"Planilha1": [r for r in csv.reader(io.StringIO(t), delimiter=delim)][:MAX_LINHAS_XLSX]}


def criar_xlsx(caminho: str, abas: dict) -> str:
    if not abas:
        raise ErroDocumento("📊 A planilha está vazia.")
    nomes = []
    for n in list(abas)[:MAX_ABAS]:
        limpo = re.sub(r"[\\/*?:\[\]]", "", str(n))[:31] or f"Planilha{len(nomes) + 1}"
        while limpo in nomes:
            limpo = (limpo[:28] + f"_{len(nomes) + 1}")[:31]
        nomes.append(limpo)
    dados = [abas[n] for n in list(abas)[:MAX_ABAS]]
    ct = _CT_XLSX_BASE + "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, len(nomes) + 1)) + "</Types>"
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(nomes, 1)) + "</sheets></workbook>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                      for i in range(1, len(nomes) + 1))
            + f'<Relationship Id="rId{len(nomes) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/styles.xml", _STYLES_XLSX)
        for i, linhas in enumerate(dados, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _xml_aba(linhas))
    return caminho


# ============================================================================================ etiqueta / despacho
_RE_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def interpretar(conteudo: str) -> dict:
    """`<criar_documento tipo="docx" nome="X">texto</criar_documento>` (a etiqueta inteira) -> {tipo, nome, texto}."""
    m = re.match(r"\s*<criar_documento\b([^>]*)>(.*?)</criar_documento>\s*$", conteudo or "", re.S | re.I)
    attrs, texto = ({}, conteudo or "") if not m else (dict(_RE_ATTR.findall(m.group(1))), m.group(2))
    tipo = (attrs.get("tipo") or "").lower().lstrip(".")
    if tipo not in ("docx", "xlsx", "word", "excel"):
        if re.match(r"^\s*[\[{]", texto or "") or len([l for l in (texto or "").splitlines() if l.lstrip().startswith("|")]) >= 2:
            tipo = "xlsx"
        else:
            tipo = "docx"
    tipo = {"word": "docx", "excel": "xlsx"}.get(tipo, tipo)
    return {"tipo": tipo, "nome": attrs.get("nome", ""), "titulo": attrs.get("titulo", ""), "texto": texto.strip("\n")}


def preview_text(conteudo: str) -> str:
    d = interpretar(conteudo)
    corpo = d["texto"].strip()
    linhas = corpo.splitlines()
    amostra = "\n".join(linhas[:12]) + (f"\n… (+{len(linhas) - 12} linhas)" if len(linhas) > 12 else "")
    nome = d["nome"] or ("documento" if d["tipo"] == "docx" else "planilha")
    return (f"[CRIAR {'WORD' if d['tipo'] == 'docx' else 'EXCEL'}]\n{'─' * 40}\nArquivo novo: {nome}.{d['tipo']} "
            f"(em creations/documentos/ — nenhum arquivo seu é alterado)\n\n{amostra[:900]}")


def criar(conteudo: str, pasta: str) -> dict:
    """Cria o arquivo (sempre novo) e devolve {"caminho", "tipo"}."""
    d = interpretar(conteudo)
    nome = _nome_seguro(d["nome"] or d["titulo"], "documento" if d["tipo"] == "docx" else "planilha")
    caminho = _caminho_novo(pasta, f"{nome}_{time.strftime('%Y%m%d_%H%M')}", d["tipo"])
    if d["tipo"] == "docx":
        criar_docx(caminho, d["texto"], d["titulo"])
    else:
        criar_xlsx(caminho, interpretar_planilha(d["texto"]))
    return {"caminho": caminho, "tipo": d["tipo"]}
