"""
Zenith — fundo do chat com QUALQUER imagem ou vídeo (v20).

Pedido do Anderson: o fundo "aceitar mp4 ou qualquer tipo de arquivo de imagem, não só
específicos". O Godot só lê nativamente PNG/JPG/WEBP/BMP/TGA e vídeo Theora (.ogv). O resto
(MP4, MOV, MKV, AVI, WEBM, GIF, TIFF, ICO...) é convertido aqui, SEM precisar do ffmpeg:

  * imagem que o Godot lê         -> usada como está;
  * imagem de outro formato       -> Pillow converte para PNG (GIF animado vira vídeo, ver abaixo);
  * .ogv                          -> usado como está;
  * vídeo / GIF animado           -> OpenCV (já usado na Visão) / Pillow extraem uma SEQUÊNCIA DE
                                     QUADROS em JPEG (até ~12 s, ≤ 15 qps, ≤ 854 px de largura)
                                     numa pasta de cache; o Corpo toca em loop lendo um quadro por vez
                                     (pouca memória, funciona em qualquer vídeo que o OpenCV abra).

Se o formato não puder ser lido, devolve uma mensagem clara — nunca levanta exceção para quem chama.
O arquivo ORIGINAL nunca é alterado nem apagado; o cache fica em temp/ (que o prepare_pendrive esvazia).
"""
import hashlib
import json
import shutil
import time
from pathlib import Path

# Godot lê direto (Image.load / VideoStreamTheora)
IMAGEM_NATIVA = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga"}
VIDEO_NATIVO = {".ogv"}
# Conhecidos — o resto é descoberto olhando o CONTEÚDO do arquivo
IMAGEM_CONVERTER = {".gif", ".tif", ".tiff", ".ico", ".jfif", ".avif", ".heic", ".heif", ".ppm", ".pgm",
                    ".pbm", ".pcx", ".dds", ".webp"}
VIDEO_CONVERTER = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".flv", ".mpg", ".mpeg",
                   ".3gp", ".ts", ".m2ts", ".mts", ".ogg", ".ogm", ".vob"}

MAX_SEGUNDOS = 12.0
FPS_SAIDA = 15.0
MAX_LARGURA_VIDEO = 854
MAX_LADO_IMAGEM = 3840
MAX_QUADROS = int(MAX_SEGUNDOS * FPS_SAIDA)        # 180
QUALIDADE_JPEG = 80
TEMPO_LIMITE = 90.0                                  # segundos de trabalho antes de desistir


class ErroFundo(Exception):
    """Mensagem já escrita para o usuário."""


def _chave(origem: Path) -> str:
    st = origem.stat()
    base = f"{origem.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:14]


def classificar(origem) -> str:
    """'imagem' | 'ogv' | 'converter_imagem' | 'video' | 'desconhecido' (só pela extensão)."""
    ext = Path(origem).suffix.lower()
    if ext in VIDEO_NATIVO:
        return "ogv"
    if ext in IMAGEM_NATIVA:
        return "imagem"
    if ext in VIDEO_CONVERTER:
        return "video"
    if ext in IMAGEM_CONVERTER:
        return "converter_imagem"
    return "desconhecido"


# ------------------------------------------------------------------ imagem
def _abrir_pillow(origem: Path):
    try:
        from PIL import Image
    except Exception as e:                                       # pragma: no cover
        raise ErroFundo(f"A biblioteca Pillow não está disponível ({e}).")
    try:
        img = Image.open(origem)
        img.load() if getattr(img, "n_frames", 1) <= 1 else None
        return img
    except Exception as e:
        raise ErroFundo(f"Não consegui abrir como imagem: {e}")


def _salvar_png(img, destino: Path) -> None:
    from PIL import Image
    quadro = img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img
    maior = max(quadro.size)
    if maior > MAX_LADO_IMAGEM:
        k = MAX_LADO_IMAGEM / float(maior)
        quadro = quadro.resize((max(1, int(quadro.width * k)), max(1, int(quadro.height * k))), Image.LANCZOS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    quadro.save(destino, "PNG")


def _quadros_de_animacao_pillow(img, pasta: Path) -> dict:
    """GIF/WEBP/APNG animado -> sequência de JPEG."""
    from PIL import Image, ImageSequence
    pasta.mkdir(parents=True, exist_ok=True)
    total = getattr(img, "n_frames", 1)
    passo = max(1, int(round(total / float(MAX_QUADROS))))
    duracoes = []
    n = 0
    for i, frame in enumerate(ImageSequence.Iterator(img)):
        duracoes.append(max(20, int(frame.info.get("duration", 80) or 80)))
        if i % passo:
            continue
        rgb = frame.convert("RGB")
        if rgb.width > MAX_LARGURA_VIDEO:
            k = MAX_LARGURA_VIDEO / float(rgb.width)
            rgb = rgb.resize((MAX_LARGURA_VIDEO, max(1, int(rgb.height * k))), Image.LANCZOS)
        n += 1
        rgb.save(pasta / f"f{n:04d}.jpg", "JPEG", quality=QUALIDADE_JPEG)
        if n >= MAX_QUADROS:
            break
    if n == 0:
        raise ErroFundo("O GIF/animação não tem quadros legíveis.")
    media_ms = sum(duracoes) / float(len(duracoes))
    fps = max(1.0, min(30.0, 1000.0 / media_ms / passo))
    return {"fps": round(fps, 2), "n": n}


# ------------------------------------------------------------------ vídeo
def _quadros_de_video_cv2(origem: Path, pasta: Path) -> dict:
    try:
        import cv2
    except Exception as e:                                       # pragma: no cover
        raise ErroFundo(f"A biblioteca OpenCV não está disponível ({e}).")
    cap = cv2.VideoCapture(str(origem))
    if not cap or not cap.isOpened():
        raise ErroFundo("Não consegui abrir esse vídeo (formato/codec que o OpenCV deste computador não lê). "
                        "Tente salvar o vídeo como MP4 (H.264) ou WEBM.")
    try:
        fps_orig = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if not (1.0 <= fps_orig <= 240.0):
            fps_orig = 24.0
        passo = max(1, int(round(fps_orig / FPS_SAIDA)))
        fps_saida = fps_orig / passo
        limite_quadros_lidos = int(MAX_SEGUNDOS * fps_orig)
        pasta.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        n = 0
        lidos = 0
        while lidos < limite_quadros_lidos and n < MAX_QUADROS:
            ok, quadro = cap.read()
            if not ok:
                break
            if lidos % passo == 0:
                h, w = quadro.shape[:2]
                if w > MAX_LARGURA_VIDEO:
                    k = MAX_LARGURA_VIDEO / float(w)
                    quadro = cv2.resize(quadro, (MAX_LARGURA_VIDEO, max(1, int(h * k))), interpolation=cv2.INTER_AREA)
                n += 1
                cv2.imwrite(str(pasta / f"f{n:04d}.jpg"), quadro, [int(cv2.IMWRITE_JPEG_QUALITY), QUALIDADE_JPEG])
            lidos += 1
            if time.time() - t0 > TEMPO_LIMITE:
                break
    finally:
        cap.release()
    if n == 0:
        raise ErroFundo("O vídeo abriu, mas não consegui ler nenhum quadro dele.")
    return {"fps": round(max(1.0, min(30.0, fps_saida)), 2), "n": n}


def _no_celular() -> bool:
    try:
        from brain import zenith_plataforma
        return zenith_plataforma.detectar() == "android"
    except Exception:
        return False


def _plataforma_com_video():
    """(v1.19) A plataforma do celular, se ela souber ler vídeo. No PC devolve None (lá é o OpenCV)."""
    try:
        from brain import zenith_plataforma
        if zenith_plataforma.detectar() != "android":
            return None
        plat = zenith_plataforma.obter()
        return plat if plat.tem("video") else None
    except Exception:
        return None


def _quadros_de_video_android(plat, origem: Path, pasta: Path) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        r = plat.video_quadros(str(origem), str(pasta), inicio_s=0.0, fps=FPS_SAIDA, max_quadros=MAX_QUADROS,
                               max_largura=MAX_LARGURA_VIDEO, qualidade=QUALIDADE_JPEG, tempo_limite_s=TEMPO_LIMITE)
    except Exception as e:
        raise ErroFundo(f"O Android não conseguiu ler esse vídeo ({e}). Tente salvar como MP4 (H.264) ou WEBM.")
    n = int((r or {}).get("n") or 0)
    if n <= 0 or not (pasta / "f0001.jpg").is_file():
        raise ErroFundo("O vídeo abriu, mas não consegui ler nenhum quadro dele.")
    fps = float((r or {}).get("fps") or FPS_SAIDA)
    return {"fps": round(max(1.0, min(30.0, fps)), 2), "n": n}


def _quadros_de_video(origem: Path, pasta: Path) -> dict:
    """PC: OpenCV. Celular: o próprio Android (o OpenCV quase nunca existe lá). Sem nenhum dos dois, uma frase honesta."""
    try:
        return _quadros_de_video_cv2(origem, pasta)
    except ErroFundo:
        plat = _plataforma_com_video()
        if plat is not None:
            return _quadros_de_video_android(plat, origem, pasta)
        if _no_celular():
            raise ErroFundo("Este celular ainda não consegue preparar vídeo como fundo (o app não liberou a leitura de vídeo). "
                            "Use uma imagem, ou um GIF/WEBP animado.")
        raise


# ------------------------------------------------------------------ API
def preparar(origem, cache_dir) -> dict:
    """Prepara `origem` como fundo. Devolve:
       {"ok": True,  "tipo": "imagem"|"ogv"|"quadros", "path": ..., "dir": ..., "fps": ..., "n": ..., "msg": ...}
       {"ok": False, "msg": "..."}
    Nunca levanta exceção."""
    try:
        return _preparar(origem, cache_dir)
    except ErroFundo as e:
        return {"ok": False, "msg": str(e)}
    except Exception as e:  # pragma: no cover — defensivo
        return {"ok": False, "msg": f"Erro inesperado preparando o fundo: {e}"}


def _preparar(origem, cache_dir) -> dict:
    if not origem:
        return {"ok": True, "tipo": "nenhum", "msg": ""}
    p = Path(origem)
    if not p.is_file():
        raise ErroFundo(f"Não encontrei o arquivo: {p}")
    tipo = classificar(p)
    if tipo == "imagem":
        return {"ok": True, "tipo": "imagem", "path": str(p), "msg": ""}
    if tipo == "ogv":
        return {"ok": True, "tipo": "ogv", "path": str(p), "msg": ""}

    raiz = Path(cache_dir) / "fundo" / _chave(p)
    meta_arq = raiz / "meta.json"
    if meta_arq.is_file():                                       # já preparado antes
        try:
            meta = json.loads(meta_arq.read_text(encoding="utf-8"))
            if meta.get("tipo") == "imagem" and Path(meta["path"]).is_file():
                return {"ok": True, **meta, "msg": "(do cache)"}
            if meta.get("tipo") == "quadros" and (Path(meta["dir"]) / "f0001.jpg").is_file():
                return {"ok": True, **meta, "msg": "(do cache)"}
        except (OSError, ValueError, KeyError):
            pass
        shutil.rmtree(raiz, ignore_errors=True)

    # limpa preparos antigos de OUTROS arquivos (mantém os 3 mais recentes)
    _limpar_cache_antigo(Path(cache_dir) / "fundo", manter=raiz.name, quantos=3)
    raiz.mkdir(parents=True, exist_ok=True)

    meta = None
    erro_imagem = None
    if tipo in ("converter_imagem", "desconhecido"):
        img = None
        try:
            img = _abrir_pillow(p)
            if getattr(img, "n_frames", 1) > 1:
                info = _quadros_de_animacao_pillow(img, raiz / "q")
                meta = {"tipo": "quadros", "dir": str(raiz / "q"), **info}
            else:
                destino = raiz / "fundo.png"
                _salvar_png(img, destino)
                meta = {"tipo": "imagem", "path": str(destino)}
        except ErroFundo as e:
            erro_imagem = e
        finally:
            if img is not None:
                try:
                    img.close()              # GIF/WEBP animado deixa o arquivo aberto até aqui
                except Exception:
                    pass
    if meta is None and tipo in ("video", "desconhecido", "converter_imagem"):
        try:
            info = _quadros_de_video(p, raiz / "q")
            meta = {"tipo": "quadros", "dir": str(raiz / "q"), **info}
        except ErroFundo as e:
            if tipo == "video" or erro_imagem is None:
                shutil.rmtree(raiz, ignore_errors=True)
                raise
    if meta is None:
        shutil.rmtree(raiz, ignore_errors=True)
        if tipo == "desconhecido":
            raise ErroFundo("Esse arquivo não parece ser uma imagem nem um vídeo que eu consiga ler.")
        raise erro_imagem or ErroFundo("Não consegui preparar esse arquivo como fundo.")
    meta_arq.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, **meta, "msg": ""}


def _limpar_cache_antigo(pasta_fundo: Path, manter: str, quantos: int = 3) -> None:
    try:
        if not pasta_fundo.is_dir():
            return
        pastas = [d for d in pasta_fundo.iterdir() if d.is_dir() and d.name != manter]
        pastas.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        for d in pastas[quantos:]:
            shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass
