"""
Zenith — EDITAR e CRIAR VÍDEO (v28).

O pedido do Anderson (13/10/2026): "quero que edite vídeo também e faça vídeo — a Shogers faz isso também". Aqui a Zenith ganha
as ferramentas de vídeo do dia a dia, em cima do ffmpeg (o programa de vídeo que quase tudo no mundo usa por baixo).

POR QUE "OPERAÇÕES TIPADAS" e não "a IA escreve o comando do ffmpeg":
um comando livre de terminal pode apagar/gravar o que quiser. Aqui a IA (ou você) só ESCOLHE uma operação da lista e passa
parâmetros simples; quem monta a linha do ffmpeg é ESTE código. Nunca sobrescreve o arquivo original: o resultado vai pra
`creations/videos/` com nome novo. (v28 — revisão: o campo `saida` do pedido agora só vale como NOME; a pasta é SEMPRE a
`creations/videos/` e o nome nunca repete um arquivo que já existe. Antes um `saida` com caminho completo + `ffmpeg -y`
deixava a IA sobrescrever qualquer arquivo do PC.)

Operações: cortar · juntar · velocidade · extrair_audio · remover_audio · redimensionar · girar · gif · converter ·
           mesclar_audio · frame · slides (imagens -> vídeo) · narrar (roteiro -> vídeo com slides + voz + legenda .srt)

`narrar` é o "faz vídeo": cada parágrafo do roteiro vira um slide (texto; equações $$…$$ viram imagem) com a voz da Zenith
lendo por cima — no estilo de vídeo de aula. Sem internet/voz, os slides saem mudos com tempo calculado.
(Vídeo "gerado por IA" — tipo Veo/Sora — é outro serviço, pago; isto aqui é MONTAGEM.)

ffmpeg: procura no PATH, em `tools/ffmpeg/`, ou usa o `imageio-ffmpeg` (pip install imageio-ffmpeg — o jeito mais fácil).
Lógica de montagem pura + `_rodar` (único ponto que abre o ffmpeg).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path

from brain import zenith_parar as parar

FORMATOS = ("mp4", "webm", "mkv", "mov", "avi")
FORMATOS_AUDIO = ("mp3", "wav", "aac", "m4a", "ogg")
MAX_PASSOS = 8
MAX_JUNTAR = 12
MAX_CENAS = 40
MAX_GIF_S = 30


class ErroVideo(Exception):
    """Mensagem já em português, pronta pro chat."""


# ----------------------------------------------------------------------------------------------- achar ferramentas
def achar_ffmpeg(base_dir: str = "") -> str | None:
    cand = os.environ.get("ZENITH_FFMPEG")
    if cand and os.path.isfile(cand):
        return cand
    no_path = shutil.which("ffmpeg")
    if no_path:
        return no_path
    for sub in ("tools/ffmpeg/ffmpeg.exe", "tools/ffmpeg/bin/ffmpeg.exe", "tools/ffmpeg/ffmpeg", "tools/ffmpeg/bin/ffmpeg"):
        p = os.path.join(base_dir, sub) if base_dir else sub
        if os.path.isfile(p):
            return p
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return None


MSG_SEM_FFMPEG = ("🎬 Não achei o ffmpeg (o programa que edita vídeo). O jeito mais fácil: no terminal do Zenith rode "
                  "`pip install imageio-ffmpeg` e abra o Zenith de novo. (Ou coloque o ffmpeg.exe em tools\\ffmpeg\\.)")


def tempo_para_segundos(valor) -> float:
    """'83' | '1:23' | '00:01:23.5' | 83 -> segundos."""
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().replace(",", ".")
    if not s:
        raise ErroVideo("🎬 Faltou um tempo (ex.: 10, 1:30 ou 00:01:30).")
    partes = s.split(":")
    try:
        total = 0.0
        for p in partes:
            total = total * 60 + float(p)
        return total
    except ValueError:
        raise ErroVideo(f"🎬 Não entendi o tempo '{valor}'. Use segundos (90) ou minutos:segundos (1:30).")


def _carimbo() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _limpar_nome(nome: str) -> str:
    stem = re.sub(r"_\d{8}_\d{4,6}(_\d+)?", "", Path(str(nome)).stem)       # tira carimbos de passos anteriores
    return re.sub(r"[^\w\-]+", "_", stem)[:40].strip("_") or "video"


def _unico(caminho: str) -> str:
    base, ext = os.path.splitext(caminho)
    n, novo = 2, caminho
    while os.path.exists(novo):
        novo = f"{base}_{n}{ext}"
        n += 1
    return novo


def saida_padrao(entrada: str, sufixo: str, ext: str, pasta: str) -> str:
    os.makedirs(pasta, exist_ok=True)
    return _unico(os.path.join(pasta, f"{_limpar_nome(entrada)}_{sufixo}_{_carimbo()}.{ext}"))


def saida_segura(pedido_saida, ref: str, sufixo: str, ext: str, pasta: str, exts_ok: tuple = ()) -> str:
    """Caminho de saída SEMPRE dentro de `pasta` e SEMPRE novo. Se o pedido trouxe um `saida`, só o NOME (sem pasta) vale."""
    if pedido_saida:
        os.makedirs(pasta, exist_ok=True)
        ext_pedida = Path(str(pedido_saida)).suffix.lstrip(".").lower()
        if ext_pedida and (ext_pedida in exts_ok):
            ext = ext_pedida
        return _unico(os.path.join(pasta, f"{_limpar_nome(pedido_saida)}.{ext}"))
    return saida_padrao(ref, sufixo, ext, pasta)


# ----------------------------------------------------------------------------------------------- rodar o ffmpeg
def _flags_janela() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _sondar(ffmpeg: str, caminho: str) -> str:
    """Saída de texto do `ffmpeg -i arquivo` (é onde ele escreve duração e streams)."""
    p = subprocess.run([ffmpeg, "-hide_banner", "-i", caminho], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=_flags_janela())
    return (p.stderr or "") + (p.stdout or "")


def duracao_de(ffmpeg: str, caminho: str) -> float:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", _sondar(ffmpeg, caminho))
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def tem_audio(ffmpeg: str, caminho: str) -> bool:
    return bool(re.search(r"Stream #\d+:\d+.*Audio:", _sondar(ffmpeg, caminho)))


def _apagar(caminho: str):
    if caminho and os.path.exists(caminho):
        try:
            os.remove(caminho)
        except OSError:
            pass


def _rodar(argv: list, duracao_total: float = 0.0, progresso=None, saida: str = "", cwd: str = None):
    """Roda o ffmpeg com barra de progresso e com o PARAR funcionando (o processo é morto de verdade).

    `cwd` existe para o caso da legenda (v1.0): o filtro `subtitles=` só aceita um caminho relativo
    seguro quando o ffmpeg roda de dentro de uma pasta temporária — ver legendar()."""
    g = parar.geracao()
    cmd = [argv[0], "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"] + argv[1:]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", creationflags=_flags_janela(), cwd=cwd)
    parar.registrar_processo(p)
    cauda = []
    try:
        for linha in p.stdout:
            linha = linha.strip()
            m = re.match(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)", linha)
            if m:
                if progresso and duracao_total > 0:
                    t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                    progresso(min(99.0, 100.0 * t / duracao_total))
            elif linha and "=" not in linha.split(" ")[0]:
                cauda.append(linha)
                cauda = cauda[-8:]
        p.wait()
    finally:
        parar.liberar_processo(p)
        if p.poll() is None:                    # saiu do loop por erro: não deixa o ffmpeg órfão rodando
            try:
                p.kill()
                p.wait(timeout=5)
            except Exception:
                pass
        try:
            p.stdout.close()                    # fecha o cano (senão: ResourceWarning e, no Windows, arquivo preso)
        except Exception:
            pass
    if parar.cancelado_desde(g):
        _apagar(saida)
        raise ErroVideo("🎬 Parei o vídeo a pedido seu.")
    if p.returncode != 0:
        _apagar(saida)
        raise ErroVideo("🎬 O ffmpeg não conseguiu fazer isso: " + (" ".join(cauda)[-300:] or f"código {p.returncode}"))
    if saida and (not os.path.exists(saida) or os.path.getsize(saida) == 0):
        raise ErroVideo("🎬 O ffmpeg terminou, mas o arquivo de saída não foi criado.")
    if progresso:
        progresso(100.0)


def _codec_video_audio(ext: str) -> list:
    if ext == "webm":
        return ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"]
    if ext == "avi":
        return ["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac"] + \
           (["-movflags", "+faststart"] if ext in ("mp4", "mov") else [])


def _ext_de(caminho: str) -> str:
    return Path(caminho).suffix.lstrip(".").lower() or "mp4"


def _exigir_arquivo(caminho: str, rotulo: str = "o arquivo"):
    """Erro em português que MOSTRA o caminho entendido e ensina o jeito certo (v1.0).

    Antes, quando o caminho chegava vazio (aspas duplicadas na hora de colar), a pessoa via só
    "Não achei o vídeo: (vazio)" — sem saber o que o programa tinha entendido nem como corrigir."""
    if caminho and os.path.isfile(caminho):
        return
    if not caminho:
        raise ErroVideo(
            f"🎬 Não recebi o caminho de {rotulo} — ele chegou vazio.\n"
            "No Explorer: segure Shift, clique com o botão direito no arquivo > \"Copiar como caminho\".\n"
            "Cole DEPOIS da operação. O Windows já coloca aspas — não precisa pôr outras.\n"
            "Exemplo: /video vertical \"C:\\Users\\voce\\Videos\\aula.mp4\" 9:16 corte")
    raise ErroVideo(
        f"🎬 Não achei {rotulo} neste caminho:\n{caminho}\n"
        "Confira se o arquivo existe mesmo (e se o nome está completo).\n"
        "Se o caminho tem espaço e veio sem aspas, ele pode ter sido cortado no meio — "
        "copie de novo com \"Copiar como caminho\" e cole inteiro.")


def _atempo(fator: float) -> str:
    cadeia, f = [], fator
    while f > 2.0:
        cadeia.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        cadeia.append("atempo=0.5")
        f /= 0.5
    cadeia.append(f"atempo={f:.4f}")
    return ",".join(cadeia)


# ----------------------------------------------------------------------------------------------- as operações
def cortar(ff, entrada, inicio, fim, saida, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    ini = tempo_para_segundos(inicio)
    total = duracao_de(ff, entrada)
    fim_s = tempo_para_segundos(fim) if fim not in (None, "", "fim") else total
    if fim_s <= ini:
        raise ErroVideo("🎬 O fim do corte precisa ser DEPOIS do início.")
    argv = [ff, "-y", "-ss", f"{ini}", "-i", entrada, "-t", f"{fim_s - ini}"] + _codec_video_audio(_ext_de(saida)) + [saida]
    _rodar(argv, fim_s - ini, progresso, saida)


def juntar(ff, entradas, saida, progresso=None):
    if len(entradas) < 2:
        raise ErroVideo("🎬 Pra juntar preciso de pelo menos 2 vídeos.")
    if len(entradas) > MAX_JUNTAR:
        raise ErroVideo(f"🎬 Juntar vídeos demais de uma vez (máximo {MAX_JUNTAR}).")
    for e in entradas:
        _exigir_arquivo(e, "um dos vídeos")
    argv, filtros, concat_in = [ff, "-y"], [], []
    total = 0.0
    for i, e in enumerate(entradas):
        d = duracao_de(ff, e) or 1.0
        total += d
        argv += ["-i", e]
        filtros.append(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                       f"setsar=1,fps=30,format=yuv420p[v{i}]")
        if tem_audio(ff, e):
            filtros.append(f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        else:                                                   # vídeo mudo no meio da junção: silêncio do mesmo tamanho
            filtros.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{d:.3f},asetpts=PTS-STARTPTS[a{i}]")
        concat_in.append(f"[v{i}][a{i}]")
    filtros.append("".join(concat_in) + f"concat=n={len(entradas)}:v=1:a=1[v][a]")
    argv += ["-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]"] + _codec_video_audio(_ext_de(saida)) + [saida]
    _rodar(argv, total, progresso, saida)


def velocidade(ff, entrada, fator, saida, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    try:
        f = float(str(fator).replace(",", ".").replace("x", ""))
    except ValueError:
        raise ErroVideo(f"🎬 Não entendi a velocidade '{fator}' (ex.: 2 = o dobro, 0.5 = metade).")
    if not 0.25 <= f <= 8:
        raise ErroVideo("🎬 A velocidade precisa ficar entre 0.25x e 8x.")
    audio = tem_audio(ff, entrada)
    filtro = f"[0:v]setpts=PTS/{f}[v]" + (f";[0:a]{_atempo(f)}[a]" if audio else "")
    argv = [ff, "-y", "-i", entrada, "-filter_complex", filtro, "-map", "[v]"] + (["-map", "[a]"] if audio else []) + \
           _codec_video_audio(_ext_de(saida)) + [saida]
    _rodar(argv, duracao_de(ff, entrada) / f, progresso, saida)


def extrair_audio(ff, entrada, saida, progresso=None):
    _exigir_arquivo(entrada, "o arquivo")
    if not tem_audio(ff, entrada):
        raise ErroVideo("🎬 Esse vídeo não tem áudio pra extrair.")
    ext = Path(saida).suffix.lstrip(".").lower()
    codec = {"mp3": ["-c:a", "libmp3lame", "-q:a", "2"], "wav": ["-c:a", "pcm_s16le"], "aac": ["-c:a", "aac"],
             "m4a": ["-c:a", "aac"], "ogg": ["-c:a", "libvorbis"]}.get(ext, ["-c:a", "libmp3lame", "-q:a", "2"])
    _rodar([ff, "-y", "-i", entrada, "-vn"] + codec + [saida], duracao_de(ff, entrada), progresso, saida)


def remover_audio(ff, entrada, saida, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    _rodar([ff, "-y", "-i", entrada, "-an", "-c:v", "copy", saida], duracao_de(ff, entrada), progresso, saida)


def redimensionar(ff, entrada, largura, saida, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    try:
        w = int(largura)
        assert 64 <= w <= 7680
    except Exception:
        raise ErroVideo("🎬 A largura precisa ser um número entre 64 e 7680 (ex.: 1280).")
    _rodar([ff, "-y", "-i", entrada, "-vf", f"scale={w}:-2"] + _codec_video_audio(_ext_de(saida)) + [saida],
           duracao_de(ff, entrada), progresso, saida)


def girar(ff, entrada, graus, saida, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    try:
        g = int(float(graus)) % 360
    except (TypeError, ValueError):
        g = -1
    vf = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}.get(g)
    if not vf:
        raise ErroVideo("🎬 Só giro 90, 180 ou 270 graus.")
    _rodar([ff, "-y", "-i", entrada, "-vf", vf] + _codec_video_audio(_ext_de(saida)) + [saida],
           duracao_de(ff, entrada), progresso, saida)


# ------------------------------------------------------------------ v30: efeitos, 9:16 e transições
# Estilos = cadeias de filtros do ffmpeg. São "de gosto", então o nome em português é o que
# o usuário fala ("deixa em preto e branco", "com cara de filme antigo").
ESTILOS = {
    "pb": ("preto e branco", "hue=s=0,eq=contrast=1.12"),
    "sepia": ("sépia", "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"),
    "vintage": ("vintage", "curves=vintage,eq=saturation=0.85:contrast=1.05,vignette=PI/5"),
    "antigo": ("filme antigo", "curves=vintage,noise=alls=10:allf=t,gblur=sigma=0.4"),
    "cinema": ("cinema", "eq=contrast=1.15:saturation=0.85:gamma=0.95,colorbalance=bs=0.10:rs=-0.04,vignette=PI/6"),
    "neon": ("neon/vivo", "eq=contrast=1.25:saturation=1.6,unsharp=5:5:1.0"),
    "sonho": ("sonho/suave", "gblur=sigma=2.2,eq=brightness=0.04:saturation=1.25"),
    "vinheta": ("vinheta", "vignette=PI/5"),
    "nitido": ("mais nítido", "unsharp=5:5:1.2:5:5:0.0"),
    "espelho": ("espelhado", "hflip"),
    "desfoque": ("desfocado", "gblur=sigma={sigma}"),
}
_ESTILO_ALIAS = {
    "preto_branco": "pb", "preto e branco": "pb", "pb": "pb", "mono": "pb",
    "sepia": "sepia", "sépia": "sepia", "vintage": "vintage", "retro": "vintage",
    "antigo": "antigo", "filme": "antigo", "filme antigo": "antigo", "8mm": "antigo",
    "cinema": "cinema", "filme de cinema": "cinema", "neon": "neon", "vivo": "neon",
    "sonho": "sonho", "suave": "sonho", "blur": "desfoque", "desfoque": "desfoque",
    "desfocado": "desfoque", "vinheta": "vinheta", "nitido": "nitido", "nítido": "nitido",
    "sharp": "nitido", "espelho": "espelho", "espelhado": "espelho",
}

PROPORCOES = {"9:16": (1080, 1920), "shorts": (1080, 1920), "reels": (1080, 1920), "tiktok": (1080, 1920),
              "1:1": (1080, 1080), "quadrado": (1080, 1080),
              "4:5": (1080, 1350), "feed": (1080, 1350),
              "16:9": (1920, 1080), "youtube": (1920, 1080),
              "3:4": (1080, 1440)}

TRANSICOES = {
    "fade": "fade", "suave": "fade", "dissolver": "dissolve", "dissolve": "dissolve",
    "preto": "fadeblack", "fadeblack": "fadeblack", "branco": "fadewhite",
    "esquerda": "slideleft", "slideleft": "slideleft", "direita": "slideright",
    "cima": "slideup", "baixo": "slidedown", "wipe": "wipeleft", "wipeleft": "wipeleft",
    "redondo": "circleopen", "circleopen": "circleopen", "pixel": "pixelize", "pixelize": "pixelize",
    "zoom": "zoomin", "radial": "radial", "hlslice": "hlslice",
}


def normalizar_estilo(estilo) -> str:
    e = str(estilo or "").strip().lower()
    e = _ESTILO_ALIAS.get(e, e)
    if e not in ESTILOS:
        raise ErroVideo(f"🎬 Não conheço o efeito '{estilo}'. Os que eu faço: "
                        f"{', '.join(sorted({v[0] for v in ESTILOS.values()}))}.")
    return e


def filtro_do_estilo(estilo, forca=1.0) -> str:
    nome = normalizar_estilo(estilo)
    vf = ESTILOS[nome][1]
    if "{sigma}" in vf:
        try:
            f = max(0.0, min(float(forca), 3.0))
        except (TypeError, ValueError):
            f = 1.0
        vf = vf.format(sigma=f"{2.0 + 8.0 * f:.2f}")
    return vf


def efeito(ff, entrada, estilo, saida, forca=1.0, progresso=None):
    """Aplica um efeito de cor/estilo no vídeo inteiro (o áudio não muda)."""
    _exigir_arquivo(entrada, "o vídeo")
    vf = filtro_do_estilo(estilo, forca)
    _rodar([ff, "-y", "-i", entrada, "-vf", vf] + _codec_video_audio(_ext_de(saida)) + [saida],
           duracao_de(ff, entrada), progresso, saida)


def enquadrar(ff, entrada, saida, proporcao="9:16", modo="corte", progresso=None):
    """Deixa o vídeo no formato de Shorts/Reels/feed.

    modo='corte' (padrão): preenche a tela cortando as sobras (sem barras).
    modo='fundo': mantém o vídeo inteiro e põe um fundo desfocado atrás (barras bonitas)."""
    _exigir_arquivo(entrada, "o vídeo")
    chave = str(proporcao or "9:16").strip().lower().replace(" ", "")
    if chave not in PROPORCOES:
        raise ErroVideo(f"🎬 Formato '{proporcao}' não suportado. Use: {', '.join(PROPORCOES)}.")
    w, h = PROPORCOES[chave]
    modo = str(modo or "corte").strip().lower()
    dur = duracao_de(ff, entrada)
    if modo in ("fundo", "blur", "desfocado", "barras"):
        filtro = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=40:2[bg];"
                  f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]")
        argv = [ff, "-y", "-i", entrada, "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?"] + \
               _codec_video_audio(_ext_de(saida)) + [saida]
    elif modo in ("corte", "cortar", "preencher", "cover"):
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
        argv = [ff, "-y", "-i", entrada, "-vf", vf] + _codec_video_audio(_ext_de(saida)) + [saida]
    else:
        raise ErroVideo("🎬 Modo inválido para o formato: use 'corte' (preenche) ou 'fundo' (barras desfocadas).")
    _rodar(argv, dur, progresso, saida)


def normalizar_transicao(tipo) -> str:
    t = str(tipo or "fade").strip().lower()
    t = TRANSICOES.get(t, t)
    if t not in set(TRANSICOES.values()):
        raise ErroVideo(f"🎬 Não conheço a transição '{tipo}'. Use: fade, dissolve, fadeblack, fadewhite, "
                        f"slideleft, slideright, slideup, slidedown, wipeleft, circleopen, pixelize, zoomin, radial.")
    return t


def _normalizar_tamanho(rotulo: str) -> str:
    """Deixa os dois lados no mesmo tamanho/fps (obrigatório pro xfade não distorcer)."""
    return (f"[{rotulo}]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{rotulo}]")


def transicao(ff, entradas, saida, tipo="fade", segundos=0.7, progresso=None):
    """Junta 2+ vídeos com uma transição entre eles (xfade). Se algum não tiver áudio, o resultado
    fica sem áudio — o Zenith avisa em vez de fingir."""
    if len(entradas) < 2:
        raise ErroVideo("🎬 Pra fazer transição preciso de pelo menos 2 vídeos.")
    if len(entradas) > MAX_JUNTAR:
        raise ErroVideo(f"🎬 Vídeos demais de uma vez (máximo {MAX_JUNTAR}).")
    for e in entradas:
        _exigir_arquivo(e, "um dos vídeos")
    trans = normalizar_transicao(tipo)
    try:
        pedido_t = float(segundos)
    except (TypeError, ValueError):
        pedido_t = 0.7
    atual = entradas[0]
    temporarios, n = [], len(entradas)
    for i, prox in enumerate(entradas[1:], 1):
        d1, d2 = duracao_de(ff, atual), duracao_de(ff, prox)
        t = max(0.1, min(pedido_t, (d1 or 1.0) / 2.0, (d2 or 1.0) / 2.0))
        off = max(0.0, (d1 or 0.0) - t)
        ultimo = (i == n - 1)
        ext_final = _ext_de(saida)
        destino = saida if (ultimo and ext_final == "mp4") else _unico(os.path.join(
            os.path.dirname(saida) or ".", f".zenith_transicao_{i}.mp4"))
        filtro = (_normalizar_tamanho("0") + ";" + _normalizar_tamanho("1") + ";" +
                  f"[v0][v1]xfade=transition={trans}:duration={t:.3f}:offset={off:.3f},format=yuv420p[v]")
        usa_audio = tem_audio(ff, atual) and tem_audio(ff, prox)
        argv = [ff, "-y", "-i", atual, "-i", prox, "-filter_complex", filtro, "-map", "[v]"]
        if usa_audio:
            filtro += f";[0:a][1:a]acrossfade=d={t:.3f}:c1=tri:c2=tri[a]"
            argv = [ff, "-y", "-i", atual, "-i", prox, "-filter_complex", filtro,
                    "-map", "[v]", "-map", "[a]"]
            argv += _codec_video_audio("mp4")
        else:
            argv += ["-an"] + [x for x in _codec_video_audio("mp4") if x != "aac" and x != "-c:a"]
        argv += [destino]
        _rodar(argv, (d1 or 1.0) + (d2 or 1.0),
               (lambda pct, _i=i: progresso((100.0 * (_i - 1) + pct) / (n - 1))) if progresso else None,
               destino)
        if atual not in entradas:
            temporarios.append(atual)
        atual = destino
    for t in temporarios:
        _apagar(t)
    if atual != saida:
        converter(ff, atual, _ext_de(saida), saida, progresso)
        _apagar(atual)


def _caminho_de_filtro(caminho: str) -> str:
    """Caminho pro filtro subtitles: barras normais e ':' do drive escapado (C\\:/...).

    ATENÇÃO (v1.0): isto NÃO resolve apóstrofo nem vírgula dentro do nome. O ffmpeg usa aspas
    simples como delimitador e não entende `\\'` ali — o filtro quebrava com um arquivo chamado
    `o'brien.srt` ("Unable to open …obrien.srt"). Por isso `legendar()` agora NÃO usa mais esta
    função para o caminho: ele copia a legenda para uma pasta temporária e passa só o nome
    `legenda.srt`. Esta função fica só como referência/teste."""
    p = os.path.abspath(caminho).replace("\\", "/")
    return p.replace(":", "\\:").replace("'", "\\'")


NOME_LEGENDA_SEGURA = "legenda.srt"


def _legenda_em_pasta_segura(srt: str) -> str:
    """Copia o .srt para uma pasta temporária com um nome SEM nenhum caractere perigoso e devolve a pasta.

    POR QUE (bug provado com ffmpeg de verdade, v1.0): o filtro `subtitles=` recebe o caminho dentro
    de aspas simples e não tem escape válido para `'` — com `o'brien.srt` o ffmpeg tentava abrir
    "obrien.srt" e o vídeo não saía. Nome com `,` `[` `]` `;` também quebra a sintaxe do filtro, e um
    nome malicioso poderia injetar opções. Com o ffmpeg rodando de dentro da pasta temporária, o
    filtro só vê `legenda.srt`: nada do nome original chega à linha de filtro."""
    pasta = tempfile.mkdtemp(prefix="zenith_legenda_")
    try:
        shutil.copyfile(srt, os.path.join(pasta, NOME_LEGENDA_SEGURA))
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    return pasta


def legendar(ff, entrada, srt, saida, progresso=None):
    """QUEIMA a legenda .srt no vídeo (não é faixa opcional: aparece sempre, igual Shorts prontos).

    O caminho da legenda NUNCA vai para o filtro: o arquivo é copiado como `legenda.srt` para uma
    pasta temporária e o ffmpeg roda de dentro dela (ver _legenda_em_pasta_segura)."""
    _exigir_arquivo(entrada, "o vídeo")
    _exigir_arquivo(srt, "a legenda .srt")
    entrada, saida = os.path.abspath(entrada), os.path.abspath(saida)
    estilo = "FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,MarginV=36"
    pasta = _legenda_em_pasta_segura(srt)
    try:
        vf = f"subtitles='{NOME_LEGENDA_SEGURA}':force_style='{estilo}'"
        _rodar([ff, "-y", "-i", entrada, "-vf", vf] + _codec_video_audio(_ext_de(saida)) + [saida],
               duracao_de(ff, entrada), progresso, saida, cwd=pasta)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def gif(ff, entrada, inicio, fim, saida, largura=480, fps=12, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    ini = tempo_para_segundos(inicio or 0)
    total = duracao_de(ff, entrada)
    fim_s = tempo_para_segundos(fim) if fim not in (None, "") else min(total, ini + 5)
    if fim_s <= ini:
        raise ErroVideo("🎬 O fim do GIF precisa ser DEPOIS do início.")
    dur = min(fim_s - ini, MAX_GIF_S)
    largura = max(64, min(int(largura), 800))
    fps = max(1, min(int(fps), 20))
    vf = f"fps={fps},scale={largura}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    _rodar([ff, "-y", "-ss", f"{ini}", "-t", f"{dur}", "-i", entrada, "-filter_complex", vf, "-an", "-loop", "0", saida],
           dur, progresso, saida)


def converter(ff, entrada, formato, saida, progresso=None):
    _exigir_arquivo(entrada, "o arquivo")
    formato = formato.lower().lstrip(".")
    if formato in FORMATOS_AUDIO:
        return extrair_audio(ff, entrada, saida, progresso)
    if formato not in FORMATOS:
        raise ErroVideo(f"🎬 Formato '{formato}' não suportado. Use: {', '.join(FORMATOS)} (ou mp3/wav pra áudio).")
    _rodar([ff, "-y", "-i", entrada] + _codec_video_audio(formato) + [saida], duracao_de(ff, entrada), progresso, saida)


def mesclar_audio(ff, video, audio, saida, volume=1.0, progresso=None):
    _exigir_arquivo(video, "o vídeo")
    _exigir_arquivo(audio, "o áudio")
    try:
        vol = float(volume)
    except (TypeError, ValueError):
        vol = 1.0
    argv = [ff, "-y", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest"]
    if vol != 1.0:
        argv += ["-filter:a", f"volume={max(0.0, min(vol, 4.0))}"]
    _rodar(argv + [saida], duracao_de(ff, video), progresso, saida)


def frame(ff, entrada, tempo, saida, progresso=None):
    _exigir_arquivo(entrada, "o vídeo")
    _rodar([ff, "-y", "-ss", f"{tempo_para_segundos(tempo)}", "-i", entrada, "-frames:v", "1", saida], 0, progresso, saida)


def slides(ff, imagens, saida, segundos=3.0, audio=None, progresso=None):
    """Imagens -> vídeo (cada imagem fica `segundos` na tela). `audio` opcional (música/narração)."""
    if not imagens:
        raise ErroVideo("🎬 Faltaram as imagens.")
    if len(imagens) > 100:
        raise ErroVideo("🎬 Imagens demais (máximo 100).")
    for i in imagens:
        _exigir_arquivo(i, "uma das imagens")
    seg = max(0.5, min(float(segundos), 60.0))
    argv, filtros = [ff, "-y"], []
    for i, img in enumerate(imagens):
        argv += ["-loop", "1", "-t", f"{seg}", "-i", img]
        filtros.append(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                       f"setsar=1,fps=30,format=yuv420p[v{i}]")
    filtros.append("".join(f"[v{i}]" for i in range(len(imagens))) + f"concat=n={len(imagens)}:v=1:a=0[v]")
    argv += (["-i", audio] if audio else []) + ["-filter_complex", ";".join(filtros), "-map", "[v]"]
    if audio:
        _exigir_arquivo(audio, "o áudio")
        argv += ["-map", f"{len(imagens)}:a:0", "-c:a", "aac", "-shortest"]
    argv += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", saida]
    _rodar(argv, seg * len(imagens), progresso, saida)


# ----------------------------------------------------------------------------------------------- o "faz vídeo": roteiro -> vídeo
LARGURA, ALTURA = 1280, 720

TEMAS = {
    "escuro": {"topo": "#0e1230", "base": "#1d1456", "texto": "#eef1ff", "destaque": "#7fd6ff", "suave": "#8a93c8", "barra": "#00d9ff"},
    "claro":  {"topo": "#f8faff", "base": "#dfe8ff", "texto": "#12172f", "destaque": "#2457d6", "suave": "#5d6a99", "barra": "#2457d6"},
    "neon":   {"topo": "#03101a", "base": "#05363c", "texto": "#e9fffb", "destaque": "#00e6c3", "suave": "#6fb7b0", "barra": "#00e6c3"},
}


def dividir_roteiro(roteiro: str) -> list:
    """Cenas = parágrafos separados por linha em branco (ou por `---`). Equações $$…$$ ficam inteiras na cena."""
    texto = (roteiro or "").replace("\r\n", "\n").strip()
    if not texto:
        return []
    partes = re.split(r"\n\s*\n|\n-{3,}\n", texto)
    return [p.strip() for p in partes if p.strip()]


_FONTES = {}


def _fonte(tamanho: int):
    from PIL import ImageFont
    if tamanho in _FONTES:
        return _FONTES[tamanho]
    candidatos = []
    try:
        from matplotlib import font_manager
        candidatos.append(font_manager.findfont("DejaVu Sans", fallback_to_default=False))
    except Exception:
        pass
    candidatos += ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"]
    f = None
    for c in candidatos:
        try:
            if c and os.path.isfile(c):
                f = ImageFont.truetype(c, tamanho)
                break
        except Exception:
            continue
    if f is None:
        try:
            f = ImageFont.load_default(tamanho)          # Pillow ≥ 10.1: fonte escalável
        except Exception:
            f = ImageFont.load_default()
    _FONTES[tamanho] = f
    return f


def _quebrar(d, texto: str, fonte, largura: int) -> list:
    """Quebra o texto em linhas que cabem em `largura` pixels (mede de verdade, não conta letras)."""
    linhas = []
    for paragrafo in str(texto).split("\n"):
        palavras, atual = paragrafo.split(), ""
        if not palavras:
            linhas.append("")
            continue
        for w in palavras:
            teste = (atual + " " + w).strip()
            if d.textlength(teste, font=fonte) <= largura or not atual:
                atual = teste
            else:
                linhas.append(atual)
                atual = w
        linhas.append(atual)
    return linhas


def _fundo(tema: dict):
    """Fundo com degradê vertical + faixa de destaque à esquerda (um visual limpo, sem depender de imagens)."""
    from PIL import Image, ImageDraw
    tela = Image.new("RGB", (LARGURA, ALTURA), tema["topo"])
    d = ImageDraw.Draw(tela)
    a = tuple(int(tema["topo"][i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(tema["base"][i:i + 2], 16) for i in (1, 3, 5))
    for y in range(ALTURA):
        t = y / (ALTURA - 1)
        d.line([(0, y), (LARGURA, y)], fill=tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    d.rectangle([0, 0, 12, ALTURA], fill=tema["barra"])
    return tela


def desenhar_slide(cena: str, caminho_png: str, titulo: str = "", numero: int = 0, total: int = 0, renderizar_eq=None,
                   tema: str = "escuro") -> bool:
    """Um slide 1280×720: fundo em degradê, título em destaque, texto que se ajusta ao espaço, equações centralizadas."""
    from PIL import Image, ImageDraw
    from brain import zenith_matematica as M
    cores = TEMAS.get(tema, TEMAS["escuro"])
    tela = _fundo(cores)
    d = ImageDraw.Draw(tela)
    margem_x, largura_util = 80, LARGURA - 160
    y0 = 56
    if titulo:
        f_t = _fonte(54)
        for linha in _quebrar(d, titulo, f_t, largura_util)[:2]:
            d.text((margem_x, y0), linha, font=f_t, fill=cores["destaque"])
            y0 += 66
        d.rectangle([margem_x, y0 + 4, margem_x + 120, y0 + 8], fill=cores["barra"])
        y0 += 34

    trechos = M.achar_trechos(cena)
    pos, blocos = 0, []                                  # [("texto", str) | ("eq", latex)]
    for t in trechos:
        if cena[pos:t.ini].strip():
            blocos.append(("texto", cena[pos:t.ini].strip()))
        blocos.append(("eq", t.latex) if t.display else ("texto", M.latex_para_unicode(t.latex)))
        pos = t.fim
    if cena[pos:].strip():
        blocos.append(("texto", cena[pos:].strip()))
    # junta texto seguido de texto (equação em linha vira palavra do parágrafo)
    juntos = []
    for tipo, c in blocos:
        if tipo == "texto" and juntos and juntos[-1][0] == "texto":
            juntos[-1] = ("texto", juntos[-1][1] + " " + c)
        else:
            juntos.append((tipo, c))

    espaco = ALTURA - y0 - 70
    tamanho = 44
    while tamanho > 24:                                  # maior fonte em que tudo cabe
        f = _fonte(tamanho)
        altura = 0
        for tipo, c in juntos:
            altura += (len(_quebrar(d, re.sub(r"[ \t]+", " ", c), f, largura_util)) * int(tamanho * 1.35) + 14
                       if tipo == "texto" else 110)
        if altura <= espaco:
            break
        tamanho -= 2
    fonte = _fonte(tamanho)
    render = renderizar_eq or M.renderizar_png
    y = y0
    for tipo, conteudo in juntos:
        if y > ALTURA - 80:
            break
        if tipo == "texto":
            for linha in _quebrar(d, re.sub(r"[ \t]+", " ", conteudo), fonte, largura_util):
                if y > ALTURA - 80:
                    break
                d.text((margem_x, y), linha, font=fonte, fill=cores["texto"])
                y += int(tamanho * 1.35)
            y += 14
        else:
            fd, tmp = tempfile.mkstemp(prefix="_zen_eq_", suffix=".png")
            os.close(fd)
            try:
                if render(conteudo, tmp, M.EstiloImagem(fundo=None, texto=cores["texto"], tamanho=30, dpi=150, margem=6)) \
                        and os.path.getsize(tmp) > 0:
                    with Image.open(tmp) as im:
                        im = im.convert("RGBA")
                        limite_h = max(60, ALTURA - 80 - y)
                        esc = min(1.0, largura_util / im.width, limite_h / im.height)
                        if esc < 1.0:
                            im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))))
                        tela.paste(im, ((LARGURA - im.width) // 2, y), im)
                        y += im.height + 20
                else:
                    d.text((margem_x, y), M.latex_para_unicode(conteudo), font=fonte, fill=cores["texto"])
                    y += int(tamanho * 1.35)
            finally:
                _apagar(tmp)
    if total:
        d.text((LARGURA - 130, ALTURA - 52), f"{numero} / {total}", font=_fonte(22), fill=cores["suave"])
    os.makedirs(os.path.dirname(caminho_png) or ".", exist_ok=True)
    tela.save(caminho_png)
    return True


def _texto_falado(cena: str) -> str:
    from brain import zenith_matematica as M
    return M.ConversorStream().converter(cena)[2].replace("\n", " ").strip()


def _texto_legenda(cena: str) -> str:
    from brain import zenith_matematica as M
    return re.sub(r"\s+", " ", M.ConversorStream().converter(cena)[1]).strip()


def _srt_tempo(s: float) -> str:
    total_ms = int(round(max(0.0, s) * 1000))
    h, resto = divmod(total_ms, 3600_000)
    m, resto = divmod(resto, 60_000)
    seg, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"


def _cues(texto: str, t0: float, t1: float, max_linha: int = 42) -> list:
    """Divide a fala em legendas de até 2 linhas, repartindo o tempo pelo tamanho de cada pedaço."""
    linhas = textwrap.wrap(texto, width=max_linha) or [""]
    grupos = ["\n".join(linhas[i:i + 2]) for i in range(0, len(linhas), 2)]
    pesos = [max(1, len(g)) for g in grupos]
    soma, ini, saida = float(sum(pesos)), t0, []
    for g, p in zip(grupos, pesos):
        fim = ini + (t1 - t0) * p / soma
        saida.append((ini, fim, g))
        ini = fim
    return saida


def narrar(ff, roteiro, saida, titulo="", tts_fn=None, pasta_trabalho="", progresso=None, segundos_minimos=3.0, tema="escuro"):
    """Roteiro -> vídeo: slide + voz por cena, tudo juntado. Devolve {"video","legenda","cenas","duracao","com_voz"}."""
    cenas = dividir_roteiro(roteiro)
    if not cenas:
        raise ErroVideo("🎬 O roteiro está vazio. Escreva as cenas separadas por uma linha em branco.")
    if len(cenas) > MAX_CENAS:
        raise ErroVideo(f"🎬 Roteiro grande demais (máximo {MAX_CENAS} cenas por vídeo).")
    trabalho = pasta_trabalho or tempfile.mkdtemp(prefix="zenith_video_")
    os.makedirs(trabalho, exist_ok=True)
    segmentos, legenda, t_acum, com_voz = [], [], 0.0, 0
    try:
        for i, cena in enumerate(cenas, 1):
            if progresso:
                progresso(100.0 * (i - 1) / (len(cenas) + 1), f"Cena {i} de {len(cenas)}")
            png = os.path.join(trabalho, f"cena_{i:02d}.png")
            desenhar_slide(cena, png, titulo if i == 1 else "", i, len(cenas), tema=tema)
            falado = _texto_falado(cena)
            mp3 = os.path.join(trabalho, f"voz_{i:02d}.mp3")
            tem_voz = bool(tts_fn and falado and tts_fn(falado, mp3) and os.path.exists(mp3) and os.path.getsize(mp3) > 0)
            seg = os.path.join(trabalho, f"seg_{i:02d}.mp4")
            if tem_voz:
                com_voz += 1
                dur = max(segundos_minimos, duracao_de(ff, mp3) + 0.6)
                argv = [ff, "-y", "-loop", "1", "-i", png, "-i", mp3, "-t", f"{dur}", "-c:v", "libx264", "-tune", "stillimage",
                        "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-af", "apad", seg]
            else:                                              # sem voz: slide mudo, tempo pelo tamanho do texto (~14 letras/s)
                dur = max(segundos_minimos, len(falado) / 14.0)
                argv = [ff, "-y", "-loop", "1", "-i", png, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur}",
                        "-c:v", "libx264", "-tune", "stillimage", "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", seg]
            _rodar(argv, dur, None, seg)
            segmentos.append(seg)
            legenda.extend(_cues(_texto_legenda(cena), t_acum, t_acum + dur))
            t_acum += dur
        lista = os.path.join(trabalho, "lista.txt")
        with open(lista, "w", encoding="utf-8") as f:
            for s in segmentos:
                f.write("file '" + s.replace("\\", "/").replace("'", "'\\''") + "'\n")

        def _prog_final(p):
            if progresso:
                progresso(100.0 * len(cenas) / (len(cenas) + 1) + p / (len(cenas) + 1), "Juntando as cenas")
        _rodar([ff, "-y", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", saida], t_acum, _prog_final, saida)
        srt = os.path.splitext(saida)[0] + ".srt"
        with open(srt, "w", encoding="utf-8") as f:
            for n, (a, b, txt) in enumerate(legenda, 1):
                f.write(f"{n}\n{_srt_tempo(a)} --> {_srt_tempo(b)}\n{txt}\n\n")
        return {"video": saida, "legenda": srt, "cenas": len(cenas), "duracao": t_acum, "com_voz": com_voz}
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- pedido (JSON da IA/comando)
OPERACOES = ("cortar", "juntar", "velocidade", "extrair_audio", "remover_audio", "redimensionar", "girar", "gif", "converter",
             "mesclar_audio", "frame", "slides", "narrar",
             "efeito", "enquadrar", "transicao", "legendar")     # v30: efeitos, Shorts 9:16, transições e legenda queimada
_ALIAS = {"acelerar": "velocidade", "audio": "extrair_audio", "mudo": "remover_audio", "musica": "mesclar_audio", "criar": "narrar",
          "filtro": "efeito", "cor": "efeito", "estilo": "efeito",
          "vertical": "enquadrar", "shorts": "enquadrar", "reels": "enquadrar", "tiktok": "enquadrar",
          "formato": "enquadrar", "transicao": "transicao", "transição": "transicao", "legenda": "legendar",
          "subtitle": "legendar", "legendas": "legendar"}


def interpretar(conteudo) -> dict:
    """Conteúdo da etiqueta <editar_video> (JSON, às vezes dentro de ```), ou já um dict."""
    if isinstance(conteudo, dict):
        return conteudo
    t = (conteudo or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        d = json.loads(t)
    except json.JSONDecodeError as e:
        raise ErroVideo(f"🎬 Não entendi o pedido de vídeo (o JSON está com erro: {e.msg}).")
    if not isinstance(d, dict):
        raise ErroVideo("🎬 O pedido de vídeo precisa ser um objeto JSON, ex.: {\"op\": \"cortar\", \"entrada\": \"...\", \"inicio\": 10, \"fim\": 30}.")
    return d


def _passos(pedido: dict) -> list:
    passos = pedido.get("passos") if isinstance(pedido.get("passos"), list) else [pedido]
    if not passos:
        raise ErroVideo("🎬 Pedido de vídeo vazio.")
    if len(passos) > MAX_PASSOS:
        raise ErroVideo(f"🎬 Passos demais num pedido só (máximo {MAX_PASSOS}).")
    for p in passos:
        if not isinstance(p, dict):
            raise ErroVideo("🎬 Cada passo precisa ser um objeto JSON.")
        op = _ALIAS.get(str(p.get("op", "")).lower(), str(p.get("op", "")).lower())
        if op not in OPERACOES:
            raise ErroVideo(f"🎬 Não conheço a operação '{p.get('op', '')}'. As que eu faço: {', '.join(OPERACOES)}.")
    return passos


def preview_text(conteudo, pasta_saida: str = "") -> str:
    """Resumo em português pro cartão de aprovação (Pilar 1): o que vai ser feito, com quais arquivos e onde sai."""
    try:
        passos = _passos(interpretar(conteudo))
    except ErroVideo as e:
        return f"[EDITAR VÍDEO]\n{'─' * 40}\n{e}"
    linhas = [f"[EDITAR / CRIAR VÍDEO]\n{'─' * 40}"]
    for i, p in enumerate(passos, 1):
        op = _ALIAS.get(str(p.get("op", "")).lower(), str(p.get("op", "")).lower())
        det = []
        for k in ("entrada", "inicio", "fim", "fator", "largura", "graus", "formato", "tempo", "audio", "segundos", "titulo",
                  "estilo", "forca", "proporcao", "modo", "tipo", "srt"):
            if p.get(k) not in (None, ""):
                det.append(f"{k}={p[k]}")
        if p.get("entradas"):
            det.append("entradas=" + ", ".join(os.path.basename(str(x)) for x in p["entradas"][:6]))
        if p.get("imagens"):
            det.append(f"{len(p['imagens'])} imagem(ns)")
        if op == "narrar":
            n = len(dividir_roteiro(p.get("roteiro", "")))
            det.append(f"{n} cena(s) com voz")
        linhas.append(f"{i}. {op}" + (" — " + "; ".join(det) if det else ""))
    linhas.append(f"\nO original NUNCA é alterado. O resultado vai pra: {pasta_saida or 'creations/videos/'} (nome novo).")
    return "\n".join(linhas)


# ----------------------------------------------------------------------------------------------- despachante (comando e IA)
def executar_pedido(pedido: dict, pasta_saida: str, progresso=None, ffmpeg: str = None, resolver=None, tts_fn=None,
                    base_dir: str = "") -> dict:
    """Executa UMA operação (ou uma lista `passos`, onde a saída de um passo vira a entrada do próximo).
    `progresso(pct, detalhe=None)` é chamado durante o trabalho. Devolve {"arquivos": [...], "saida": str, "texto": str}.
    Toda saída vai pra `pasta_saida`, com nome novo — o campo `saida` do pedido só sugere o NOME."""
    ff = ffmpeg or achar_ffmpeg(base_dir)
    if not ff:
        raise ErroVideo(MSG_SEM_FFMPEG)
    resolver = resolver or (lambda x: x)
    passos = _passos(pedido)
    os.makedirs(pasta_saida, exist_ok=True)
    anterior, resultados = None, []

    def _abs(caminho):
        c = resolver(str(caminho)) if caminho else ""
        return os.path.abspath(c) if c else ""

    for k, p in enumerate(passos):
        op = _ALIAS.get(str(p.get("op", "")).lower(), str(p.get("op", "")).lower())

        def prog(pct, detalhe=None, _k=k):
            if progresso:
                progresso((100.0 * _k + pct) / len(passos), detalhe)

        def ent(chave="entrada"):
            v = p.get(chave)
            if v in (None, "", "$anterior") and anterior:
                return anterior
            return _abs(v)

        def sai(ref, sufixo, ext, exts_ok=FORMATOS):
            return saida_segura(p.get("saida"), ref, sufixo, ext, pasta_saida, exts_ok)

        if op == "cortar":
            entrada = ent()
            e = _ext_de(entrada)
            s = sai(entrada, "corte", e if e in FORMATOS else "mp4")
            cortar(ff, entrada, p.get("inicio", 0), p.get("fim"), s, prog)
        elif op == "juntar":
            entradas = [_abs(x) for x in p.get("entradas", [])]
            s = sai(entradas[0] if entradas else "juntado", "juntado", "mp4")
            juntar(ff, entradas, s, prog)
        elif op == "velocidade":
            entrada = ent()
            e = _ext_de(entrada)
            s = sai(entrada, f"{str(p.get('fator', 2))}x", e if e in FORMATOS else "mp4")
            velocidade(ff, entrada, p.get("fator", 2), s, prog)
        elif op == "extrair_audio":
            entrada = ent()
            fmt = str(p.get("formato", "mp3")).lstrip(".").lower()
            fmt = fmt if fmt in FORMATOS_AUDIO else "mp3"
            s = sai(entrada, "audio", fmt, FORMATOS_AUDIO)
            extrair_audio(ff, entrada, s, prog)
        elif op == "remover_audio":
            entrada = ent()
            e = _ext_de(entrada)
            s = sai(entrada, "mudo", e if e in FORMATOS else "mp4")
            remover_audio(ff, entrada, s, prog)
        elif op == "redimensionar":
            entrada = ent()
            e = _ext_de(entrada)
            s = sai(entrada, f"{p.get('largura', 1280)}px", e if e in FORMATOS else "mp4")
            redimensionar(ff, entrada, p.get("largura", 1280), s, prog)
        elif op == "girar":
            entrada = ent()
            e = _ext_de(entrada)
            s = sai(entrada, f"giro{p.get('graus', 90)}", e if e in FORMATOS else "mp4")
            girar(ff, entrada, p.get("graus", 90), s, prog)
        elif op == "gif":
            entrada = ent()
            s = sai(entrada, "gif", "gif", ("gif",))
            gif(ff, entrada, p.get("inicio", 0), p.get("fim"), s, int(p.get("largura", 480)), int(p.get("fps", 12)), prog)
        elif op == "converter":
            entrada = ent()
            fmt = str(p.get("formato", "mp4")).lstrip(".").lower()
            if fmt not in FORMATOS and fmt not in FORMATOS_AUDIO:
                raise ErroVideo(f"🎬 Formato '{fmt}' não suportado. Use: {', '.join(FORMATOS)} (ou mp3/wav pra áudio).")
            s = sai(entrada, "conv", fmt, (fmt,))
            converter(ff, entrada, fmt, s, prog)
        elif op == "mesclar_audio":
            entrada = ent()
            s = sai(entrada, "musica", "mp4")
            mesclar_audio(ff, entrada, _abs(p.get("audio", "")), s, p.get("volume", 1.0), prog)
        elif op == "frame":
            entrada = ent()
            s = sai(entrada, "frame", "png", ("png", "jpg", "jpeg"))
            frame(ff, entrada, p.get("tempo", 0), s, prog)
        elif op == "slides":
            imgs = [_abs(x) for x in p.get("imagens", [])]
            s = sai(imgs[0] if imgs else "slides", "slides", "mp4")
            slides(ff, imgs, s, p.get("segundos", 3), _abs(p["audio"]) if p.get("audio") else None, prog)
        elif op == "efeito":
            entrada = ent()
            e = _ext_de(entrada)
            estilo = normalizar_estilo(p.get("estilo") or p.get("efeito") or p.get("nome") or "")
            s = sai(entrada, f"efeito_{estilo}", e if e in FORMATOS else "mp4")
            efeito(ff, entrada, estilo, s, p.get("forca", 1.0), prog)
        elif op == "enquadrar":
            entrada = ent()
            prop = str(p.get("proporcao") or p.get("formato") or "9:16")
            s = sai(entrada, "vertical" if prop.strip().lower() in ("9:16", "shorts", "reels", "tiktok") else "enquadrado", "mp4")
            enquadrar(ff, entrada, s, prop, p.get("modo", "corte"), prog)
        elif op == "transicao":
            entradas = [_abs(x) for x in p.get("entradas", [])]
            s = sai(entradas[0] if entradas else "transicao", "transicao", "mp4")
            transicao(ff, entradas, s, p.get("tipo", "fade"), p.get("segundos", 0.7), prog)
        elif op == "legendar":
            entrada = ent()
            e = _ext_de(entrada)
            s = sai(entrada, "legendado", e if e in FORMATOS else "mp4")
            legendar(ff, entrada, _abs(p.get("srt") or p.get("legenda") or ""), s, prog)
        else:                                                  # narrar
            s = sai(p.get("titulo") or "video_aula", "narrado", "mp4")
            r = narrar(ff, p.get("roteiro", ""), s, p.get("titulo", ""), tts_fn, "", lambda pct, det=None: prog(pct, det),
                       tema=str(p.get("tema", "escuro")))
            resultados.append(r["legenda"])
            s = r["video"]
            if tts_fn is not None and r["com_voz"] == 0:
                resultados.append("(sem voz: não consegui gerar a fala — os slides saíram mudos, com tempo calculado)")
        anterior = s
        resultados.append(s)
    arquivos = [r for r in resultados if os.path.isfile(r)]
    notas = [r for r in resultados if not os.path.isfile(r)]
    return {"arquivos": arquivos, "saida": anterior, "texto": " ".join(notas)}
