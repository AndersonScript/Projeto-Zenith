"""Zenith — plataforma ANDROID (v1.11): o Cérebro pede, o app Android faz.

O Cérebro (Python) roda DENTRO do celular. Microfone, câmera, tela, voz, Bluetooth e IA local são do
Android, então o Python não os alcança sozinho: ele pede ao app (o "host": Godot/Kotlin) por uma PONTE.

Contrato da ponte (qualquer objeto com estes dois métodos serve):

    ponte.chamar(nome: str, **args) -> dict | list | None
    ponte.assinar(evento: str, funcao) / ponte.desassinar(evento: str, funcao)      # só para o microfone

Regras do contrato — pensadas para atravessar o WebSocket que o Corpo e o Cérebro já usam:
  * tudo é JSON; bytes viajam em base64 (`pcm16`, `imagem`, `dados`);
  * erro de verdade = `{"ok": False, "erro": "frase em português"}`; a ponte nunca devolve exceção da
    plataforma nativa, só a frase;
  * `capacidades.listar` devolve a lista do que o aparelho REALMENTE tem. Celular sem câmera, sem
    Bluetooth ou com a IA local desligada no "downgrade" simplesmente não anuncia — e a capacidade
    some daqui, sem erro e sem quebrar o resto.

Regras de tempo que o Cérebro assume:
  * `audio.tocar` só volta DEPOIS de o som ter começado; `audio.ocupado` fica verdadeiro até ele terminar
    (é assim que o Cérebro sabe a hora de tocar o pedaço seguinte da fala e de avisar o avatar que acabou);
  * `mic.quadro` entrega PCM de 16 bits, mono, na taxa pedida, em pedaços de qualquer tamanho (o Cérebro
    reagrupa em blocos de 100 ms).

Chamadas usadas (nome -> argumentos -> resposta):
    capacidades.listar                                  -> ["audio_saida", "tela", ...]
    sistema.medir                                       -> {ram_total_gb, ram_livre_gb, bateria_pct, carregando, temperatura_c}
    audio.tocar    caminho, volume                      -> {ok}
    audio.parar                                         -> {ok}
    audio.ocupado                                       -> {ok, ocupado}
    mic.iniciar    taxa            (+ evento mic.quadro {pcm16})  -> {ok}
    mic.parar                                           -> {ok}
    stt.transcrever pcm16, taxa, idioma                 -> {ok, texto}
    tts.sintetizar texto, caminho_saida, voz, velocidade, tom -> {ok}
    tela.capturar  max_w, jpeg                          -> {ok, imagem}
    camera.capturar warmup, max_w                       -> {ok, imagem}
    video.info     caminho                              -> {ok, duracao_s, largura, altura, fps}
    video.quadros  caminho, pasta, inicio_s, fps, max_quadros, max_largura, qualidade, tempo_limite_s -> {ok, n, fps}
    notificacao.mostrar titulo, texto                   -> {ok}
    app.abrir      alvo                                 -> {ok}
    ble.enviar     dispositivo, dados                   -> {ok}
    llm.endereco                                        -> {ok, url}
"""
from __future__ import annotations

import base64
import time

from brain.zenith_plataforma import CAPACIDADES, Indisponivel, Plataforma, medir_sistema


class AndroidPlataforma(Plataforma):
    nome = "android"

    def __init__(self, ponte=None):
        self.ponte = ponte
        self._assinaturas = {}
        self._caps = frozenset({"sistema"})      # medir() sempre funciona: lê /proc, mesmo sem ponte
        self._descoberto = ponte is None         # sem ponte não há o que perguntar
        self._ultima_busca = 0.0
        if ponte is not None:
            try:                                  # o Corpo ANUNCIA o que o aparelho tem (ao conectar e ao mudar uma permissão)
                ponte.assinar("capacidades", self._ao_anunciar)
            except Exception:
                pass
            self._descobrir()

    # ---- descoberta -----------------------------------------------------------------------------
    # O Corpo pode conectar DEPOIS de o Cérebro nascer (o Cérebro sobe primeiro). Por isso a lista não é lida uma
    # vez só: enquanto o Corpo não respondeu, cada consulta tenta de novo (no máximo 1 vez por segundo), e quando o
    # Corpo anuncia (ou muda) as capacidades, a lista é atualizada na hora.
    @property
    def capacidades(self) -> frozenset:
        if not self._descoberto:
            self._descobrir()
        return self._caps

    def _guardar(self, lista) -> None:
        if isinstance(lista, dict):
            lista = lista.get("capacidades", lista.get("lista", []))
        self._caps = frozenset({"sistema"} | {c for c in (lista or []) if c in CAPACIDADES})
        self._descoberto = True

    def _ao_anunciar(self, dados) -> None:
        self._guardar(dados)

    def _descobrir(self) -> None:
        agora = time.monotonic()
        if self._ultima_busca and agora - self._ultima_busca < 1.0:
            return
        self._ultima_busca = agora
        try:
            lista = self.ponte.chamar("capacidades.listar")
        except Exception:
            return                                # o Corpo ainda não anunciou: tenta de novo daqui a pouco
        self._guardar(lista)

    def _chamar(self, nome: str, **args):
        if self.ponte is None:
            raise Indisponivel("O Cérebro ainda não está ligado ao app Android (ponte ausente).")
        try:
            r = self.ponte.chamar(nome, **args)
        except Indisponivel:
            raise
        except Exception as e:
            raise Indisponivel(f"Falha ao pedir '{nome}' ao Android: {e}") from e
        if isinstance(r, dict) and r.get("ok") is False:
            raise Indisponivel(str(r.get("erro") or f"O Android não conseguiu fazer '{nome}'."))
        return r

    # ---- sistema --------------------------------------------------------------------------------
    def medir(self) -> dict:
        medida = medir_sistema()
        if self.ponte is not None:
            try:
                extra = self._chamar("sistema.medir")
            except Indisponivel:
                extra = None
            if isinstance(extra, dict):
                for chave in ("ram_total_gb", "ram_livre_gb", "bateria_pct", "carregando", "temperatura_c"):
                    if extra.get(chave) is not None:
                        medida[chave] = extra[chave]
                medida["fonte"] = "android"
        return medida

    # ---- áudio ----------------------------------------------------------------------------------
    def tocar_audio(self, caminho: str, volume: float = 1.0) -> None:
        self._exigir("audio_saida")
        self._chamar("audio.tocar", caminho=str(caminho), volume=float(volume))

    def parar_audio(self) -> None:
        self._exigir("audio_saida")
        self._chamar("audio.parar")

    def audio_ocupado(self) -> bool:
        self._exigir("audio_saida")
        r = self._chamar("audio.ocupado")
        return bool(r.get("ocupado")) if isinstance(r, dict) else bool(r)

    def iniciar_microfone(self, ao_receber, taxa: int = 16000) -> None:
        self._exigir("microfone")

        def _quadro(evento):
            try:
                ao_receber(base64.b64decode(evento.get("pcm16", ""), validate=True))
            except Exception:
                pass                              # um quadro ruim não pode derrubar a escuta

        self.parar_microfone_silencioso()
        self.ponte.assinar("mic.quadro", _quadro)
        self._assinaturas["mic.quadro"] = _quadro
        try:
            self._chamar("mic.iniciar", taxa=int(taxa))
        except Indisponivel:
            self.parar_microfone_silencioso()
            raise

    def parar_microfone_silencioso(self) -> None:
        funcao = self._assinaturas.pop("mic.quadro", None)
        if funcao is not None and self.ponte is not None:
            try:
                self.ponte.desassinar("mic.quadro", funcao)
            except Exception:
                pass

    def parar_microfone(self) -> None:
        self._exigir("microfone")
        self.parar_microfone_silencioso()
        self._chamar("mic.parar")

    def transcrever(self, pcm16: bytes, taxa: int = 16000, idioma: str = "pt") -> str:
        self._exigir("transcricao")
        r = self._chamar("stt.transcrever", pcm16=base64.b64encode(pcm16).decode("ascii"),
                         taxa=int(taxa), idioma=idioma)
        return str((r or {}).get("texto", "")) if isinstance(r, dict) else ""

    def sintetizar(self, texto: str, caminho_saida: str, voz: str = "", velocidade: float = 1.0,
                   tom: float = 1.0) -> bool:
        self._exigir("voz_local")
        r = self._chamar("tts.sintetizar", texto=texto, caminho_saida=str(caminho_saida), voz=voz,
                         velocidade=float(velocidade), tom=float(tom))
        return bool(r.get("ok", True)) if isinstance(r, dict) else bool(r)

    # ---- visão ----------------------------------------------------------------------------------
    def _imagem(self, capacidade: str, chamada: str, **args):
        try:
            self._exigir(capacidade)
            r = self._chamar(chamada, **args)
        except Indisponivel as e:
            return None, str(e)
        b64 = (r or {}).get("imagem") if isinstance(r, dict) else None
        if not b64:
            return None, "O Android não devolveu imagem."
        try:
            dados = base64.b64decode(b64, validate=True)
        except Exception:
            dados = b""
        if not dados:
            return None, "A imagem que veio do Android estava corrompida."
        return dados, None

    def capturar_tela(self, max_w: int = 0, jpeg: bool = False):
        return self._imagem("tela", "tela.capturar", max_w=int(max_w), jpeg=bool(jpeg))

    def capturar_camera(self, warmup: int = 5, max_w: int = 0):
        return self._imagem("camera", "camera.capturar", warmup=int(warmup), max_w=int(max_w))

    # ---- vídeo (v1.19) ------------------------------------------------------------------------------
    def video_info(self, caminho: str) -> dict:
        self._exigir("video")
        r = self._chamar("video.info", caminho=str(caminho))
        r = r if isinstance(r, dict) else {}
        return {"duracao_s": float(r.get("duracao_s") or 0.0), "largura": int(r.get("largura") or 0),
                "altura": int(r.get("altura") or 0), "fps": float(r.get("fps") or 0.0)}

    def video_quadros(self, caminho: str, pasta: str, inicio_s: float = 0.0, fps: float = 15.0,
                      max_quadros: int = 180, max_largura: int = 854, qualidade: int = 80,
                      tempo_limite_s: float = 90.0) -> dict:
        self._exigir("video")
        r = self._chamar("video.quadros", caminho=str(caminho), pasta=str(pasta), inicio_s=float(inicio_s),
                         fps=float(fps), max_quadros=int(max_quadros), max_largura=int(max_largura),
                         qualidade=int(qualidade), tempo_limite_s=float(tempo_limite_s))
        r = r if isinstance(r, dict) else {}
        return {"n": int(r.get("n") or 0), "fps": float(r.get("fps") or fps)}

    # ---- sistema do usuário ------------------------------------------------------------------------
    def notificar(self, titulo: str, texto: str) -> bool:
        self._exigir("notificacao")
        self._chamar("notificacao.mostrar", titulo=titulo, texto=texto)
        return True

    def abrir(self, alvo: str) -> bool:
        self._exigir("abrir")
        self._chamar("app.abrir", alvo=alvo)
        return True

    # ---- carrinho ----------------------------------------------------------------------------------------
    def ble_enviar(self, dispositivo: str, dados: bytes) -> bool:
        self._exigir("ble")
        self._chamar("ble.enviar", dispositivo=dispositivo, dados=base64.b64encode(dados).decode("ascii"))
        return True

    # ---- IA local ----------------------------------------------------------------------------------------
    def endereco_llm_local(self):
        self._exigir("llm_local")
        r = self._chamar("llm.endereco")
        url = (r or {}).get("url") if isinstance(r, dict) else None
        return str(url) if url else None
