"""
Zenith — ANEXOS DE QUALQUER TIPO (v28).

O pedido do Anderson (13/10/2026): "ela vai aceitar ARQUIVO INTEIRO, e compactado, e programação colada… e se clicar nele
abre uma mini janela". Até a v27 a Zenith só entendia imagem e texto simples; qualquer outra coisa virava erro. Agora:

  .zip / .tar / .tgz    -> lista o que tem dentro e LÊ os arquivos de texto/código pequenos (sem extrair nada pro disco)
  .docx / .xlsx / .pptx -> extrai o texto (Word, Excel, PowerPoint) — só com a biblioteca padrão (zipfile + xml)
  .pdf                  -> extrai o texto se `pypdf` estiver instalado (senão avisa como instalar)
  vídeo                 -> um quadro do vídeo vira IMAGEM (a IA enxerga) + duração/tamanho/resolução
  qualquer outra coisa  -> NÃO dá mais erro: a IA recebe nome, tipo e tamanho e sabe que o arquivo existe

Tudo aqui é SOMENTE LEITURA e tem limites (tamanho, quantidade de arquivos, taxa de descompressão) — um zip malicioso ("zip
bomb") não derruba o Zenith. v28 (revisão): arquivos compactados são FECHADOS (no Windows um .zip aberto fica travado), as
leituras de dentro do pacote têm teto de verdade (o tamanho escrito no cabeçalho do zip pode ser mentira), e todo texto que
vem de documento/pacote entra na IA como CONTEÚDO EXTERNO em quarentena (ver zenith_quarentena.py).

`resumo_para_visualizador` alimenta a MINI JANELA do Corpo (clicar no anexo): texto, listagem ou miniatura.
Lógica pura (+ OpenCV opcional pro vídeo): testável sem Godot.
"""
from __future__ import annotations

import os
import re
import shutil
import tarfile
import zipfile
from pathlib import Path

from brain import zenith_quarentena as quarentena

LIMITE_TEXTO = 20000                    # igual ao anexo de texto de sempre: não estoura o contexto da IA
LIMITE_ARQUIVO_DENTRO_DO_ZIP = 60_000   # só lê arquivos de texto pequenos de dentro do zip
LIMITE_ENTRADAS = 80                    # quantos nomes listar
LIMITE_DESCOMPRIMIDO = 200_000_000      # zip bomb: passou disso, não lê nada de dentro
LIMITE_MEMBROS_TAR = 3000               # .tar/.tgz: no máximo tantos itens são percorridos
LIMITE_TAR_COMPRIMIDO = 150_000_000     # .tar.gz maior que isso não é percorrido (descompactar só pra listar)
LIMITE_MEMBRO_OFFICE = 5_000_000        # um XML de dentro de docx/xlsx/pptx maior que isso é recusado

EXT_TEXTO = {
    ".txt", ".md", ".py", ".pyw", ".json", ".csv", ".log", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".c", ".cpp",
    ".h", ".hpp", ".java", ".ino", ".xml", ".yaml", ".yml", ".sql", ".gd", ".cs", ".go", ".rs", ".php", ".rb", ".kt",
    ".sh", ".bash", ".ps1", ".bat", ".r", ".lua", ".swift", ".dart", ".ini", ".cfg", ".toml", ".tsv", ".tex", ".srt",
}
EXT_VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".ogv", ".wmv", ".flv", ".m4v"}
EXT_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
EXT_OFFICE = {".docx", ".xlsx", ".pptx"}
EXT_ZIP = {".zip", ".tar", ".tgz", ".gz", ".tbz2", ".bz2"}
EXT_FECHADOS = {".rar", ".7z"}


def tamanho_legivel(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1048576:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def tipo_do_arquivo(caminho: str) -> str:
    """'imagem' | 'video' | 'audio' | 'texto' | 'compactado' | 'documento' | 'pdf' | 'outro'."""
    ext = Path(caminho).suffix.lower()
    if ext in EXT_IMAGEM:
        return "imagem"
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_AUDIO:
        return "audio"
    if ext in EXT_TEXTO:
        return "texto"
    if ext in EXT_ZIP or ext in EXT_FECHADOS:
        return "compactado"
    if ext in EXT_OFFICE:
        return "documento"
    if ext == ".pdf":
        return "pdf"
    return "outro"


# ----------------------------------------------------------------------------------------------- texto de documentos
def _limpar_xml(trecho: str) -> str:
    trecho = re.sub(r"<[^>]+>", "", trecho)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        trecho = trecho.replace(a, b)
    return trecho


def _ler_zip_membro(z: zipfile.ZipFile, nome: str, limite: int = LIMITE_MEMBRO_OFFICE) -> bytes:
    """Lê UM item do zip com teto REAL: o tamanho do cabeçalho pode mentir (zip bomb), então só lemos `limite`+1 bytes."""
    info = z.getinfo(nome)
    if info.file_size > limite:
        raise ValueError(f"'{nome}' é grande demais ({tamanho_legivel(info.file_size)})")
    with z.open(info) as f:
        dados = f.read(limite + 1)
    if len(dados) > limite:
        raise ValueError(f"'{nome}' descompacta pra mais do que o permitido (arquivo suspeito)")
    return dados


def texto_docx(caminho: str) -> str:
    with zipfile.ZipFile(caminho) as z:
        xml = _ler_zip_membro(z, "word/document.xml").decode("utf-8", errors="replace")
    xml = xml.replace("</w:p></w:tc>", "</w:tc>")            # parágrafo que fecha a célula: sem quebra de linha extra
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"</w:tc>", " | ", xml)
    xml = re.sub(r"</w:tr>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    texto = _limpar_xml(xml)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def texto_pptx(caminho: str) -> str:
    partes = []
    with zipfile.ZipFile(caminho) as z:
        slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                        key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        for i, nome in enumerate(slides[:200], 1):
            xml = _ler_zip_membro(z, nome).decode("utf-8", errors="replace")
            xml = re.sub(r"</a:p>", "\n", xml)
            txt = re.sub(r"\n{2,}", "\n", _limpar_xml(xml)).strip()
            partes.append(f"--- Slide {i} ---\n{txt}")
    return "\n".join(partes).strip()


def texto_xlsx(caminho: str, max_linhas: int = 200) -> str:
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(caminho) as z:
        compartilhadas = []
        nomes_z = set(z.namelist())
        if "xl/sharedStrings.xml" in nomes_z:
            raiz = ET.fromstring(_ler_zip_membro(z, "xl/sharedStrings.xml"))
            for si in raiz.findall("m:si", ns):
                compartilhadas.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        nomes_abas = {}
        if "xl/workbook.xml" in nomes_z:
            wb = ET.fromstring(_ler_zip_membro(z, "xl/workbook.xml"))
            for i, s in enumerate(wb.iter("{%s}sheet" % ns["m"]), 1):
                nomes_abas[i] = s.get("name", f"Planilha{i}")
        abas = sorted((n for n in nomes_z if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                      key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        saida = []
        for idx, nome in enumerate(abas[:6], 1):
            raiz = ET.fromstring(_ler_zip_membro(z, nome))
            saida.append(f"--- Aba: {nomes_abas.get(idx, idx)} ---")
            linhas = 0
            for row in raiz.iter("{%s}row" % ns["m"]):
                if linhas >= max_linhas:
                    saida.append("[... mais linhas cortadas ...]")
                    break
                celulas = []
                for c in row.findall("m:c", ns):
                    v = c.find("m:v", ns)
                    if c.get("t") == "inlineStr":
                        celulas.append("".join(t.text or "" for t in c.iter("{%s}t" % ns["m"])))
                    elif v is None or v.text is None:
                        celulas.append("")
                    elif c.get("t") == "s":
                        try:
                            celulas.append(compartilhadas[int(v.text)])
                        except (ValueError, IndexError):
                            celulas.append(v.text)
                    else:
                        celulas.append(v.text)
                if any(celulas):
                    saida.append(" | ".join(celulas))
                    linhas += 1
    return "\n".join(saida).strip()


def _leitor_pdf(caminho: str):
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
    except ImportError:
        raise RuntimeError("Pra ler PDF falta a biblioteca `pypdf` (pip install pypdf). O resto dos anexos funciona normal.")
    leitor = PdfReader(caminho)
    if getattr(leitor, "is_encrypted", False):
        try:
            ok = leitor.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            raise RuntimeError("Esse PDF tem senha — não consigo abrir.")
    return leitor


def paginas_pdf(caminho: str, max_paginas: int = 400) -> list:
    """[(número_da_página, texto)] — usado pela biblioteca (citar a página) e por texto_pdf."""
    leitor = _leitor_pdf(caminho)
    saida = []
    for i, pagina in enumerate(leitor.pages[:max_paginas], 1):
        try:
            saida.append((i, (pagina.extract_text() or "").strip()))
        except Exception:
            saida.append((i, ""))
    return saida


def texto_pdf(caminho: str, max_paginas: int = 40) -> str:
    leitor = _leitor_pdf(caminho)
    partes = []
    for i, pagina in enumerate(leitor.pages[:max_paginas], 1):
        try:
            txt = (pagina.extract_text() or "").strip()
        except Exception:
            txt = ""
        partes.append(f"--- Página {i} ---\n{txt}")
    if len(leitor.pages) > max_paginas:
        partes.append(f"[... {len(leitor.pages) - max_paginas} páginas cortadas ...]")
    return "\n".join(partes).strip()


# ----------------------------------------------------------------------------------------------- compactados
def _eh_texto_pequeno(nome: str, tamanho: int) -> bool:
    return Path(nome).suffix.lower() in EXT_TEXTO and 0 < tamanho <= LIMITE_ARQUIVO_DENTRO_DO_ZIP


def _entradas_zip(z: zipfile.ZipFile) -> list:
    return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]


def _ler_pedaco_zip(z: zipfile.ZipFile, nome: str) -> str:
    with z.open(nome) as f:                       # teto de verdade (não confia no cabeçalho)
        return f.read(LIMITE_ARQUIVO_DENTRO_DO_ZIP).decode("utf-8", errors="replace")


def _entradas_tar(t: tarfile.TarFile) -> list:
    entradas, total = [], 0
    for i, m in enumerate(t):
        if i >= LIMITE_MEMBROS_TAR or total > LIMITE_DESCOMPRIMIDO:
            break
        if m.isfile():
            entradas.append((m.name, m.size))
            total += m.size
    return entradas


def listar_compactado(caminho: str, ler_conteudo: bool = True, teto: int = LIMITE_TEXTO) -> str:
    """Resumo de um .zip/.tar: nomes + conteúdo dos arquivos de texto pequenos. NADA é extraído pro disco.
    (Só o CONTEÚDO lido — o que veio de dentro do pacote — deve ser tratado como externo por quem chama.)"""
    nome_base = os.path.basename(caminho)
    if zipfile.is_zipfile(caminho):
        with zipfile.ZipFile(caminho) as z:
            infos = z.infolist()
            if any(i.flag_bits & 0x1 for i in infos):
                return f"[Pacote compactado '{nome_base}': tem arquivos com SENHA — não consigo abrir.]"
            entradas = _entradas_zip(z)
            return _formatar_pacote(nome_base, entradas, ler_conteudo, teto, lambda n: _ler_pedaco_zip(z, n))
    try:
        if os.path.getsize(caminho) > LIMITE_TAR_COMPRIMIDO:
            return f"[Pacote compactado '{nome_base}': grande demais pra listar aqui ({tamanho_legivel(os.path.getsize(caminho))}).]"
        eh_tar = tarfile.is_tarfile(caminho)
    except (OSError, tarfile.TarError):
        eh_tar = False
    if eh_tar:
        with tarfile.open(caminho) as t:
            entradas = _entradas_tar(t)
            nomes_ok = {n for n, tam in entradas if _eh_texto_pequeno(n, tam)}
        if ler_conteudo and nomes_ok:                  # 2ª passada, só pra ler os pequenos de texto
            conteudos = {}
            with tarfile.open(caminho) as t:
                for i, m in enumerate(t):
                    if i >= LIMITE_MEMBROS_TAR:
                        break
                    if m.isfile() and m.name in nomes_ok and len(conteudos) < 40:
                        f = t.extractfile(m)
                        if f is not None:
                            with f:
                                conteudos[m.name] = f.read(LIMITE_ARQUIVO_DENTRO_DO_ZIP).decode("utf-8", errors="replace")
            return _formatar_pacote(nome_base, entradas, ler_conteudo, teto, lambda n: conteudos.get(n, ""))
        return _formatar_pacote(nome_base, entradas, False, teto, lambda n: "")
    return f"[Arquivo compactado '{nome_base}': formato que não consigo abrir aqui.]"


def _formatar_pacote(nome_base, entradas, ler_conteudo, teto, leitor) -> str:
    total = sum(s for _, s in entradas)
    linhas = [f"[Pacote compactado '{nome_base}': {len(entradas)} arquivos, {tamanho_legivel(total)} descomprimido]"]
    for nome, tam in entradas[:LIMITE_ENTRADAS]:
        linhas.append(f"  • {nome}  ({tamanho_legivel(tam)})")
    if len(entradas) > LIMITE_ENTRADAS:
        linhas.append(f"  [... mais {len(entradas) - LIMITE_ENTRADAS} arquivos ...]")
    if ler_conteudo and total <= LIMITE_DESCOMPRIMIDO:
        usado = sum(len(l) for l in linhas)
        for nome, tam in entradas:
            if usado >= teto:
                linhas.append("[... conteúdo cortado ...]")
                break
            if not _eh_texto_pequeno(nome, tam):
                continue
            try:
                bruto = leitor(nome)
            except Exception:
                continue
            bloco = f"\n=== {nome} ===\n{bruto}"
            bloco = bloco[: max(0, teto - usado)]
            linhas.append(bloco)
            usado += len(bloco)
    elif total > LIMITE_DESCOMPRIMIDO:
        linhas.append("[conteúdo NÃO lido: o pacote descomprimido é gigante (proteção contra zip bomb)]")
    return "\n".join(linhas)


# ----------------------------------------------------------------------------------------------- vídeo
def _plataforma_com_video():
    """(v1.19) A plataforma do celular, se (e só se) ela souber ler vídeo. No PC devolve None: lá quem lê é o OpenCV."""
    try:
        from brain import zenith_plataforma
        if zenith_plataforma.detectar() != "android":
            return None
        plat = zenith_plataforma.obter()
        return plat if plat.tem("video") else None
    except Exception:
        return None


def _info_de_video_cv2(caminho: str) -> dict:
    try:
        import cv2
        cap = cv2.VideoCapture(caminho)
        try:
            if not cap.isOpened():
                return {}
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            return {"duracao_s": (frames / fps) if fps > 0 else 0.0,
                    "largura": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "altura": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "fps": round(fps, 2)}
        finally:
            cap.release()
    except Exception:
        return {}


def info_de_video(caminho: str) -> dict:
    """{'duracao_s', 'largura', 'altura', 'fps'} via OpenCV; no celular, sem OpenCV, pelo próprio Android (vazio se nenhum dos dois)."""
    info = _info_de_video_cv2(caminho)
    if info:
        return info
    plat = _plataforma_com_video()
    if plat is None:
        return {}
    try:
        r = plat.video_info(caminho) or {}
        return {"duracao_s": float(r.get("duracao_s") or 0.0), "largura": int(r.get("largura") or 0),
                "altura": int(r.get("altura") or 0), "fps": round(float(r.get("fps") or 0.0), 2)}
    except Exception:
        return {}


def _miniatura_cv2(caminho: str, pasta_saida: str, largura_max: int, info: dict):
    try:
        import cv2
        cap = cv2.VideoCapture(caminho)
        try:
            if not cap.isOpened():
                return None
            fps = info.get("fps") or 25
            dur = info.get("duracao_s") or 0
            alvo = min(1.0, dur / 2) if dur else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(alvo * fps))
            ok, quadro = cap.read()
            if not ok or quadro is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, quadro = cap.read()
            if not ok or quadro is None:
                return None
            h, w = quadro.shape[:2]
            if w > largura_max:
                quadro = cv2.resize(quadro, (largura_max, max(1, int(h * largura_max / w))))
            os.makedirs(pasta_saida, exist_ok=True)
            saida = os.path.join(pasta_saida, "_thumb_" + re.sub(r"\W+", "_", Path(caminho).stem)[:40] + ".png")
            if not cv2.imwrite(saida, quadro):
                return None
            return saida
        finally:
            cap.release()
    except Exception:
        return None


def _miniatura_android(plat, caminho: str, pasta_saida: str, largura_max: int, info: dict):
    """(v1.19) Um quadro de ~1 s pelo Android. Sai em JPEG (o plugin grava JPEG); o PC continua em PNG."""
    base = re.sub(r"\W+", "_", Path(caminho).stem)
    tmp = os.path.join(pasta_saida, "_thumb_tmp_" + base[:30])
    try:
        os.makedirs(tmp, exist_ok=True)
        dur = info.get("duracao_s") or 0
        alvo = min(1.0, dur / 2) if dur else 0.0
        r = plat.video_quadros(caminho, tmp, inicio_s=alvo, fps=1.0, max_quadros=1, max_largura=largura_max,
                               qualidade=85, tempo_limite_s=20.0)
        origem = os.path.join(tmp, "f0001.jpg")
        if not (r or {}).get("n") or not os.path.isfile(origem):
            return None
        saida = os.path.join(pasta_saida, "_thumb_" + base[:40] + ".jpg")
        os.replace(origem, saida)
        return saida
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def miniatura_de_video(caminho: str, pasta_saida: str, largura_max: int = 480) -> tuple:
    """(caminho_da_imagem | None, info). Pega um quadro de ~1 s (ou do meio, se o vídeo for curto)."""
    info = info_de_video(caminho)
    saida = _miniatura_cv2(caminho, pasta_saida, largura_max, info)
    if saida:
        return saida, info
    plat = _plataforma_com_video()
    if plat is not None:
        saida = _miniatura_android(plat, caminho, pasta_saida, largura_max, info)
        if saida:
            return saida, info
    return None, info


def descricao_de_video(caminho: str, info: dict) -> str:
    partes = [f"[Vídeo anexado: {os.path.basename(caminho)} — {tamanho_legivel(os.path.getsize(caminho))}"]
    if info.get("duracao_s"):
        s = int(info["duracao_s"])
        partes.append(f", {s // 60}:{s % 60:02d} de duração")
    if info.get("largura"):
        partes.append(f", {info['largura']}×{info['altura']}")
    partes.append("]")
    return "".join(partes)


# ----------------------------------------------------------------------------------------------- a leitura principal
def _externo(texto: str, nome: str, usuario: str) -> str:
    """Todo texto que veio de DENTRO de um documento/pacote entra na IA em quarentena (dado, nunca instrução)."""
    return quarentena.envolver(texto, nome, usuario or "o usuário")


def ler_anexo_geral(caminho: str, pasta_temp: str = "", teto: int = LIMITE_TEXTO, usuario: str = ""):
    """Retorna (texto_extra, image_bytes, image_mime, erro) pra tudo que NÃO é imagem/texto simples (esses já têm
    caminho próprio em zenith_headless._ler_anexo). Nunca devolve erro por 'tipo desconhecido'."""
    nome = os.path.basename(caminho)
    ext = Path(caminho).suffix.lower()
    try:
        tam = os.path.getsize(caminho)
    except OSError as e:
        return None, None, None, f"⚠️ Não consegui abrir '{nome}': {e}"
    try:
        if ext in EXT_ZIP:
            return _externo(listar_compactado(caminho, True, teto), nome, usuario), None, None, None
        if ext in EXT_FECHADOS:
            return (f"[Arquivo compactado '{nome}' ({tamanho_legivel(tam)}): .rar/.7z — não abro esse formato aqui. "
                    f"Converta pra .zip e anexe de novo se quiser que eu leia o conteúdo.]"), None, None, None
        if ext in EXT_OFFICE:
            leitor = {".docx": texto_docx, ".xlsx": texto_xlsx, ".pptx": texto_pptx}[ext]
            txt = leitor(caminho)
            if len(txt) > teto:
                txt = txt[:teto] + "\n[...conteúdo cortado, documento muito grande...]"
            return _externo(f"[Conteúdo do documento '{nome}']:\n{txt or '(sem texto)'}", nome, usuario), None, None, None
        if ext == ".pdf":
            try:
                txt = texto_pdf(caminho)
            except RuntimeError as e:
                return f"[PDF anexado: {nome} ({tamanho_legivel(tam)}) — {e}]", None, None, None
            if len(txt) > teto:
                txt = txt[:teto] + "\n[...conteúdo cortado...]"
            corpo = f"[Conteúdo do PDF '{nome}']:\n{txt or '(PDF sem texto — talvez seja imagem escaneada)'}"
            return _externo(corpo, nome, usuario), None, None, None
        if ext in EXT_VIDEO:
            pasta = pasta_temp or os.path.dirname(caminho)
            thumb, info = miniatura_de_video(caminho, pasta)
            desc = descricao_de_video(caminho, info)
            if thumb:
                with open(thumb, "rb") as f:
                    mime = "image/jpeg" if thumb.lower().endswith(".jpg") else "image/png"      # celular: JPEG
                    return desc + " (a imagem é um quadro do vídeo)", f.read(), mime, None
            return desc, None, None, None
        if ext in EXT_AUDIO:
            return f"[Áudio anexado: {nome} ({tamanho_legivel(tam)}) — não ouço o áudio ainda, mas sei que o arquivo existe.]", None, None, None
        return (f"[Arquivo anexado: {nome} ({tamanho_legivel(tam)}), tipo '{ext or 'sem extensão'}' — não sei ler o conteúdo "
                f"desse formato, mas sei que ele existe e posso mexer nele (mover, compactar, apagar…) se você pedir.]"), None, None, None
    except zipfile.BadZipFile:
        return None, None, None, f"⚠️ '{nome}' parece corrompido (não abre como pacote/documento)."
    except Exception as e:
        return None, None, None, f"⚠️ Não consegui ler '{nome}': {type(e).__name__}: {e}"


def resumo_para_visualizador(caminho: str, pasta_temp: str = "", teto: int = 60000) -> dict:
    """Alimenta a MINI JANELA do Corpo: {'tipo','nome','tamanho','texto','miniatura'}."""
    nome = os.path.basename(caminho)
    r = {"tipo": tipo_do_arquivo(caminho), "nome": nome, "caminho": caminho, "tamanho": "", "texto": "", "miniatura": ""}
    try:
        r["tamanho"] = tamanho_legivel(os.path.getsize(caminho))
    except OSError as e:
        r["texto"] = f"Não consegui abrir: {e}"
        return r
    ext = Path(caminho).suffix.lower()
    try:
        if r["tipo"] == "texto":
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                r["texto"] = f.read(teto + 1)[:teto]
        elif r["tipo"] == "imagem":
            r["miniatura"] = caminho
            r["texto"] = f"Imagem: {nome} ({r['tamanho']})"
        elif r["tipo"] == "compactado" and ext not in EXT_FECHADOS:
            r["texto"] = listar_compactado(caminho, ler_conteudo=False)
        elif r["tipo"] == "documento":
            r["texto"] = {".docx": texto_docx, ".xlsx": texto_xlsx, ".pptx": texto_pptx}[ext](caminho)[:teto]
        elif r["tipo"] == "pdf":
            try:
                r["texto"] = texto_pdf(caminho)[:teto]
            except RuntimeError as e:
                r["texto"] = str(e)
        elif r["tipo"] == "video":
            thumb, info = miniatura_de_video(caminho, pasta_temp or os.path.dirname(caminho))
            r["miniatura"] = thumb or ""
            r["texto"] = descricao_de_video(caminho, info)
        elif r["tipo"] == "audio":
            r["texto"] = f"Áudio: {nome} ({r['tamanho']})"
        elif r["tipo"] == "outro" or (r["tipo"] == "compactado"):
            r["texto"] = f"{nome}\nTipo: {ext or 'sem extensão'}\nTamanho: {r['tamanho']}\n\n(Sem prévia pra esse formato — use \"Abrir no programa\".)"
    except Exception as e:
        r["texto"] = f"Não consegui montar a prévia: {type(e).__name__}: {e}"
    return r
