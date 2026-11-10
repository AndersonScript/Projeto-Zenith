#!/usr/bin/env python3
"""Mede o ditado ao vivo com um WAV SEU (T1) — `python tools/bench_ditado.py fala.wav`.

Não vai áudio nenhum para o repositório: o arquivo é passado na hora e nada é salvo.

O que ele mede, no mesmo pipeline do programa (`brain/zenith_ditado.py`):
  • latência do PRIMEIRO parcial (quanto tempo até a primeira palavra aparecer na tela);
  • latência da primeira palavra CONFIRMADA (a que já não pisca mais);
  • quantas mensagens `voice_partial` o Corpo receberia (uma por mudança real de tela).

Dois motores possíveis:
  • `--motor vosk --modelo <pasta>`: parciais rápidos (se o vosk estiver instalado);
  • `--motor whisper` (padrão): janela deslizante de 8 s com o Whisper já instalado
    (faster-whisper). Limite honesto: este é mais lento que o Vosk; o número que importa
    é a diferença entre o primeiro parcial e a palavra confirmada.
"""
import argparse
import sys
import time
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from brain import zenith_ditado as ditado  # noqa: E402


def ler_wav(caminho: str):
    with wave.open(caminho, "rb") as w:
        if w.getsampwidth() != 2:
            raise SystemExit("O WAV precisa ser 16 bits (PCM). Converta com: ffmpeg -i entrada.wav -ac 1 -ar 16000 -sample_fmt s16 saida.wav")
        taxa = w.getframerate()
        canais = w.getnchannels()
        dados = w.readframes(w.getnframes())
    if canais > 1:                      # deixa mono (média simples dos canais)
        import array
        amostras = array.array("h")
        amostras.frombytes(dados)
        mono = array.array("h", [
            int(sum(amostras[i:i + canais]) / canais)
            for i in range(0, len(amostras) - canais + 1, canais)])
        dados = mono.tobytes()
    return dados, taxa


def transcritor_whisper():
    try:
        from brain import zenith_interaction as inter
        if inter.WhisperModel is None:
            return None
    except Exception:
        return None

    from brain.zenith_settings import MODELS_DIR
    from faster_whisper import WhisperModel
    modelo = WhisperModel("small", device="cpu", compute_type="int8",
                          download_root=str(Path(MODELS_DIR) / "whisper"))

    def transcrever(pcm16: bytes) -> str:
        import array
        amostras = array.array("h")
        amostras.frombytes(pcm16[:len(pcm16) - (len(pcm16) % 2)])
        audio = [a / 32768.0 for a in amostras]
        segmentos, _ = modelo.transcribe(audio, language="pt", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segmentos).strip()

    return transcrever


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mede a latência do ditado ao vivo com um WAV seu.")
    ap.add_argument("wav", help="arquivo WAV 16 bits (de preferência 16 kHz, mono)")
    ap.add_argument("--motor", default="whisper", choices=("whisper", "vosk"))
    ap.add_argument("--modelo", default="", help="pasta do modelo Vosk (só com --motor vosk)")
    ap.add_argument("--passo", type=float, default=1.0, help="de quantos em quantos segundos re-transcreve")
    ap.add_argument("--janela", type=float, default=8.0, help="quantos segundos de áudio por passada")
    a = ap.parse_args(argv)

    if not Path(a.wav).is_file():
        print("Não achei o arquivo:", a.wav)
        return 2
    dados, taxa = ler_wav(a.wav)
    print(f"Áudio: {len(dados) / (taxa * 2):.2f} s a {taxa} Hz")

    if a.motor == "vosk":
        motor = ditado.MotorVosk.abrir(a.modelo, taxa) if a.modelo else None
        if motor is None:
            print("Vosk indisponível (pacote ou modelo). Use --motor whisper.")
            return 2
    else:
        transcrever = transcritor_whisper()
        if transcrever is None:
            print("faster-whisper não está instalado — instale (pip install faster-whisper) ou use --motor vosk.")
            return 2
        motor = ditado.MotorJanela(transcrever, taxa=taxa, janela_s=a.janela, passo_s=a.passo)

    recebidas = []
    d = ditado.Ditado(motor, enviar=recebidas.append)

    bloco = int(taxa * 0.1) * 2          # 100 ms de áudio
    inicio = time.monotonic()
    primeiro_parcial = None
    primeira_confirmada = None
    for posicao in range(0, len(dados), bloco):
        enviado_em = time.monotonic() - inicio
        d.alimentar(dados[posicao:posicao + bloco], taxa)
        if primeiro_parcial is None and recebidas:
            primeiro_parcial = enviado_em
        if primeira_confirmada is None and any(m.get("stable") for m in recebidas):
            primeira_confirmada = enviado_em
    d.fechar()

    print(f"Mensagens voice_partial: {len(recebidas)}")
    print("Primeiro parcial:      " + (f"{primeiro_parcial:.2f} s de áudio" if primeiro_parcial is not None else "não saiu"))
    print("Primeira confirmada:   " + (f"{primeira_confirmada:.2f} s de áudio" if primeira_confirmada is not None else "não saiu"))
    print("Tempo total de parede: %.2f s" % (time.monotonic() - inicio))
    if recebidas:
        print("Última tela: stable=" + repr(recebidas[-1].get("stable")) +
              " tail=" + repr(recebidas[-1].get("tail")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
