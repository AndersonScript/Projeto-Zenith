"""
Zenith — PRESENÇA EM VÍDEO (v1.7, tarefa T3): "ela sempre olhando", de verdade.

O `/presenca` da v1.4 tirava uma foto a cada 15 s e comparava com a anterior. Faltava o
que faz parecer vídeo:

  * **buffer circular SÓ EM MEMÓRIA** dos últimos quadros (padrão 6). Nada é gravado em
    disco em nenhum momento — não existe `open()` de escrita neste arquivo;
  * **detecção de mudança** (o `zenith_observar.diferenca`, miniatura em tons de cinza) para
    só mandar à IA quando algo mudou;
  * **janelas sensíveis** (gerenciador de senhas, banco, "login", "senha", pix…): quando o
    título da janela ativa é desses, a captura é PAUSADA e o usuário é avisado — a foto nem
    é tirada;
  * **"olha a minha tela" com a presença ligada** responde com o quadro mais novo, sem pedir
    de novo a aprovação que a sessão já deu;
  * **mini vídeo**: os 3 últimos quadros viram UMA imagem (grade 2×2 com fundo escuro), que
    qualquer IA que enxerga aceita — funciona mesmo quando o provedor só recebe uma imagem.

Este módulo é só a política; capturar, comentar e publicar continuam vindo de fora (é o que
deixa tudo testável sem câmera, sem tela e sem rede).

Mensagens para o Corpo (as mesmas do `/presenca`): `{"action": "observando", ...}` pelo
`estado` do `Observador`. O aviso de janela sensível é texto no chat.
"""
from __future__ import annotations

import io
import re
import unicodedata

MAX_QUADROS = 6
MINI_QUADROS = 3
LIMIAR_MUDANCA = 6.0

# Pilar 1: se a janela ativa parece de senha/banco/pagamento, eu NÃO olho.
_PALAVRAS_SENSIVEIS = (
    "senha", "password", "passwd", "login", "entrar", "autentica", "2fa", "token",
    "1password", "bitwarden", "keepass", "lastpass", "dashlane", "cofre", "keychain",
    "banco", "nubank", "itau", "bradesco", "santander", "caixa economica", "inter",
    "c6 bank", "picpay", "mercado pago", "pagseguro", "paypal", "pix", "cartao",
    "cartão", "fatura", "boleto", "nota fiscal", "cpf", "irpf", "imposto de renda",
    "conta azul", "gerenciador de senhas", "gerenciador de senha",
)
_SENSIVEL = re.compile("|".join(re.escape(p) for p in _PALAVRAS_SENSIVEIS), re.I)

AVISO_SENSIVEL = ("🔒 A janela em foco parece ser de senha/banco/pagamento — pausei a captura "
                  "enquanto ela estiver aberta. Nada foi olhado nem enviado.")


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(t or "")) if not unicodedata.combining(c))


def titulo_sensivel(titulo: str) -> bool:
    """True quando o título da janela ativa pede pausa (senha, banco, pagamento…)."""
    t = _sem_acento(titulo).lower()
    if not t.strip():
        return False
    return bool(_SENSIVEL.search(t))


def diferenca(a: bytes, b: bytes) -> float:
    """Diferença média (0–255) entre dois quadros. Delega para o `zenith_observar` (uma conta só)."""
    from brain import zenith_observar
    return zenith_observar.diferenca(a, b)


class BufferQuadros:
    """Últimos quadros — em memória, com teto. Nunca escreve em disco."""

    def __init__(self, maximo: int = MAX_QUADROS):
        self.maximo = max(1, int(maximo))
        self._itens = []                     # [(bytes, titulo, marca)] — tela/camera
        self.descartados = 0

    def __len__(self) -> int:
        return len(self._itens)

    def adicionar(self, img: bytes, titulo: str = "", marca: str = "") -> bool:
        if not img:
            return False
        self._itens.append((bytes(img), str(titulo or "")[:120], str(marca or "")))
        while len(self._itens) > self.maximo:
            self._itens.pop(0)
            self.descartados += 1
        return True

    def _filtrados(self, marca: str = "") -> list:
        if not marca:
            return list(self._itens)
        return [i for i in self._itens if i[2] == marca]

    def ultimo(self, marca: str = ""):
        itens = self._filtrados(marca)
        return itens[-1][0] if itens else None

    def ultimos(self, n: int = MINI_QUADROS, marca: str = "") -> list:
        n = max(1, int(n))
        return [i[0] for i in self._filtrados(marca)[-n:]]

    def limpar(self) -> None:
        self._itens.clear()

    def mini_video(self, n: int = MINI_QUADROS, colunas: int = 2, marca: str = ""):
        """Os últimos `n` quadros viram UMA imagem (grade). Devolve bytes PNG, ou o último quadro se não
        der para compor (sem PIL, quadro quebrado). A IA recebe uma imagem só — funciona em todo provedor."""
        quadros = self.ultimos(n, marca)
        if not quadros:
            return None
        if len(quadros) == 1:
            return quadros[0]
        try:
            from PIL import Image
            abertos = [Image.open(io.BytesIO(q)).convert("RGB") for q in quadros]
        except Exception:
            return quadros[-1]
        largura = 320
        alturas = [max(1, int(im.height * largura / max(1, im.width))) for im in abertos]
        colunas = max(1, min(int(colunas), len(abertos)))
        linhas = (len(abertos) + colunas - 1) // colunas
        alt_linha = [max(alturas[i:i + colunas]) for i in range(0, len(abertos), colunas)]
        fundo = Image.new("RGB", (largura * colunas, sum(alt_linha)), (12, 16, 32))
        y = 0
        for li, alt in enumerate(alt_linha):
            for ci in range(colunas):
                k = li * colunas + ci
                if k >= len(abertos):
                    break
                fundo.paste(abertos[k].resize((largura, alturas[k])), (ci * largura, y))
            y += alt
        saida = io.BytesIO()
        fundo.save(saida, format="PNG")
        return saida.getvalue()


class Presenca:
    """Envolve a captura: buffer, mudança, janelas sensíveis e resposta rápida.

    `capturar(tipo)` -> (bytes|None, erro|None)      a captura de verdade (tela/câmera)
    `titulo_atual()` -> str                          o título da janela em foco (opcional)
    `avisar(texto)`                                  mostra o aviso no chat (uma vez por pausa)
    """

    def __init__(self, capturar, titulo_atual=None, avisar=None, buffer=None,
                 limiar: float = LIMIAR_MUDANCA, mini: int = MINI_QUADROS):
        self._capturar = capturar
        self._titulo_atual = titulo_atual
        self._avisar = avisar or (lambda _t: None)
        self.buffer = buffer or BufferQuadros()
        self.limiar = float(limiar)
        self.mini = int(mini)
        self.pausada = False
        self.pausas = 0
        self.fotos = 0
        self._ultimo_enviado = None
        self._avisou = False

    # ------------------------------------------------------------------ captura
    def capturar(self, tipo: str = "screen"):
        """Mesma assinatura do `Observador`. Em janela sensível devolve (None, motivo) sem tirar foto."""
        try:
            titulo = str(self._titulo_atual()) if self._titulo_atual else ""
        except Exception:
            titulo = ""
        if titulo_sensivel(titulo):
            self.pausada = True
            self.pausas += 1
            if not self._avisou:
                self._avisou = True
                self._avisar(AVISO_SENSIVEL)
            return None, "janela sensível (captura pausada)"
        self.pausada = False
        self._avisou = False
        img, erro = self._capturar(tipo)
        if img:
            self.fotos += 1
            self.buffer.adicionar(img, titulo or ("camera" if tipo == "camera" else "tela"), marca=tipo)
        return img, erro

    def mudou(self, img: bytes) -> bool:
        """Compara com o último quadro ENVIADO à IA (não com o último capturado)."""
        if not img:
            return False
        if self._ultimo_enviado is None or diferenca(self._ultimo_enviado, img) >= self.limiar:
            self._ultimo_enviado = img
            return True
        return False

    # ------------------------------------------------------------------ resposta rápida
    def quadros_para_pedido(self, tipo: str = "") -> list:
        """Para "olha a minha tela" com a presença já aprovada: o quadro mais novo (ou o mini vídeo)."""
        marca = "screen" if tipo in ("screen", "tela") else "camera" if tipo in ("camera", "câmera") else ""
        if not self.buffer.ultimo(marca):
            return []
        if len(self.buffer.ultimos(self.mini, marca)) >= 2:
            composto = self.buffer.mini_video(self.mini, marca=marca)
            return [composto] if composto else [self.buffer.ultimo(marca)]
        ultimo = self.buffer.ultimo(marca)
        return [ultimo] if ultimo else []

    def resumo(self) -> str:
        if not self.fotos:
            return "Presença: nenhum quadro em memória ainda."
        return (f"Presença: {self.fotos} quadro(s) vistos, {len(self.buffer)} em memória "
                f"(nada em disco)" + (f", {self.pausas} pausa(s) por janela sensível" if self.pausas else "") + ".")
