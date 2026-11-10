"""
Zenith — STREAMING de verdade: a resposta sai frase a frase ENQUANTO o modelo ainda gera (v24).

Por que existe: até a v23, o Zenith esperava o modelo terminar TUDO, conferia a resposta inteira e só então
"digitava ao vivo" (com pausas artificiais de até 0,6 s por frase) e só DEPOIS começava a falar. Numa resposta
de 6 frases isso eram uns 8–10 s até a primeira palavra falada. Conversa fluida (como a Shogun) pede o oposto:
a primeira frase sai assim que ela existe.

Como NÃO perder as proteções (nada aparece/é falado sem passar por elas):
  * cada frase só é liberada depois de passar pela checagem de CONTEÚDO GRAVE (a mesma do Zenith inteiro);
  * cada frase é conferida contra o validador de ATITUDE (pedir licença em texto, desculpa pronta...): se a
    conversa começa a descambar, o portão FECHA e o resto segue o caminho antigo (resposta completa, conferida,
    corrigida e entregue de uma vez);
  * a PRIMEIRA etiqueta de ação (`<`) ou bloco de código (```) fecha o portão: tudo dali em diante é tratado pelo
    caminho normal (aprovação, executor, etc.). Etiqueta nenhuma é lida em voz alta;
  * o texto FINAL continua passando por tudo (segurança, validador de formato, extração de ações, memória). Se o
    final não bater com o que já foi liberado, a sessão cancela a voz e entrega o texto correto (ver `reconciliar`).

Este módulo é lógica pura (sem Godot, sem rede, sem áudio): as pontas entram por funções injetadas.
"""
from __future__ import annotations

import re

_FIM_DE_FRASE = re.compile(r"(?<=[.!?;…])\s+")
# v26: começo de matemática: $$ · \[ · \( · \comando · $x (cifrão colado numa letra/símbolo; "R$ 5" e "$5" não contam)
_LIMITE_MATEMATICA_ABERTA = 1500
_MATEMATICA_CHEGANDO = re.compile(r"\$\$|\\[\[\(A-Za-z]|\$(?=[^\s\d$])")


class Portao:
    """Recebe pedaços de texto do modelo e libera FRASES COMPLETAS e seguras."""

    def __init__(self, ao_liberar, seguro=None, atitude=None, transformar=None):
        # v27: `transformar(trecho) -> (chat, histórico, fala)` (ver zenith_matematica.ConversorStream.converter). Com ele, a
        # matemática NÃO fecha mais o portão: a equação é convertida na hora e o streaming segue (antes, a 1ª equação
        # travava o resto da resposta até o fim — parecia lentidão).
        self._transformar = transformar
        self.liberado_fala = ""                                # o mesmo que `liberado`, escrito pra ser LIDO
        self._ao_liberar = ao_liberar
        self._seguro = seguro or (lambda texto: True)          # texto -> False se for conteúdo grave
        self._atitude = atitude or (lambda texto: [])          # texto acumulado -> lista de problemas
        self._buf = ""
        self.liberado = ""                                     # tudo o que já foi entregue (texto cru, na ordem)
        self.fechado = False
        self.motivo = ""

    # ------------------------------------------------------------------ entrada
    def alimentar(self, delta: str):
        if self.fechado or not delta:
            return
        self._buf += delta
        self._processar(fim=False)

    def terminar(self):
        """O modelo acabou. NÃO libera o resto aqui: o final passa pelo caminho completo (reconciliar)."""
        if not self.fechado:
            self._processar(fim=True)

    def fechar(self, motivo: str):
        if not self.fechado:
            self.fechado = True
            self.motivo = motivo

    # ------------------------------------------------------------------ interno
    def _processar(self, fim: bool):
        while not self.fechado:
            corte = self._achar_corte()
            if corte is None:
                return
            trecho, resto, motivo_fechar = corte
            if trecho.strip():
                if not self._liberar(trecho):
                    return
            self._buf = resto
            if motivo_fechar:
                self.fechar(motivo_fechar)
                return

    def _achar_corte(self):
        """(trecho_a_liberar, resto, motivo_pra_fechar|'') ou None se ainda não há uma frase completa."""
        b = self._buf
        marcas = [(b.find("<"), "etiqueta"), (b.find("```"), "codigo")]
        marcas = [(i, m) for i, m in marcas if i != -1]
        aberta = None
        if self._transformar is not None:
            # v27 — o "<" de uma equação ($a < b$) e o "```" não são etiqueta/código QUANDO estão dentro de matemática
            from brain import zenith_matematica as _mat
            spans0 = [(t.ini, t.fim) for t in _mat.achar_trechos(b)]
            aberta0 = _mat.inicio_de_matematica_aberta(b)

            def _fora(i):
                return not any(a <= i < f for a, f in spans0) and (aberta0 is None or i < aberta0)
            marcas = []
            for padrao, motivo in (("<", "etiqueta"), ("```", "codigo")):
                for mm in re.finditer(re.escape(padrao), b):
                    if _fora(mm.start()):
                        marcas.append((mm.start(), motivo))
                        break
        if self._transformar is None:
            # v26 (sem conversor): matemática chegando ($$…$$, $x^2$, \\[…\\], \\frac…) fecha o portão como nas etiquetas
            m_mat = _MATEMATICA_CHEGANDO.search(b)
            if m_mat:
                marcas.append((m_mat.start(), "matematica"))
            elif b.endswith("$"):                          # "$" no fim do pedaço: ainda não dá pra saber (R$ 5 ou $x$?)
                return None
        else:
            # v27 (com conversor): espera a equação FECHAR e converte; só desiste se ela não fechar em ~1500 letras
            from brain import zenith_matematica as _mat
            aberta = _mat.inicio_de_matematica_aberta(b)
            if aberta is not None and len(b) - aberta > _LIMITE_MATEMATICA_ABERTA:
                marcas.append((aberta, "matematica"))
            elif aberta is None and b.endswith("$"):
                return None
        if marcas:                                          # tem etiqueta/código chegando: solta o que vem antes e fecha
            i, motivo = min(marcas)
            return b[:i], b[i:], motivo
        if self._transformar is None:
            m = _FIM_DE_FRASE.search(b)
            if m:
                return b[:m.start()] + b[m.start():m.end()], b[m.end():], ""
            return None
        from brain import zenith_matematica as _mat
        spans = [(t.ini, t.fim) for t in _mat.achar_trechos(b)]
        limite = aberta if aberta is not None else len(b) + 1
        for m in _FIM_DE_FRASE.finditer(b):
            if m.start() >= limite:
                break
            if any(a < m.start() < f for a, f in spans):    # ponto/vírgula DENTRO de uma equação não termina a frase
                continue
            return b[:m.end()], b[m.end():], ""
        return None

    def _liberar(self, trecho: str) -> bool:
        if not self._seguro(trecho):
            self.fechar("seguranca")
            return False
        chat, fala = trecho, trecho
        if self._transformar is not None:
            try:
                chat, _hist, fala = self._transformar(trecho)
            except Exception as e:
                print(f"[Zenith/Stream] conversor de matemática falhou ({e}) — fechando o portão")
                self.fechar("matematica")
                return False
        problemas = self._atitude((self.liberado + " " + chat).strip())
        if problemas:
            self.fechar("atitude")
            return False
        self.liberado += chat
        self.liberado_fala += fala
        if fala == chat:
            self._ao_liberar(chat)
        else:
            self._ao_liberar(chat, fala)
        return True


def fatiar_preservando(texto: str) -> list:
    """Divide o texto em frases para o "digitar ao vivo" SEM perder NADA do texto (v1.0).

    BUG REAL CORRIGIDO (A6): o entregador fazia `re.split(r'(?<=[.!?;])\\s+', texto)` e depois
    colava `pedaco + " "`. Isso TROCAVA toda quebra de linha que vinha depois de um ponto final por
    um espaço: `escalares.\\n---\\n\\n### 1.` virava `escalares. ---`, listas colavam e o `###`
    aparecia como parágrafo em negrito. Aqui as quebras de linha fazem parte dos pedaços e
    `"".join(fatiar_preservando(t)) == t` sempre (é o que o teste verifica).
    """
    if not texto:
        return []
    partes, inicio = [], 0
    for m in re.finditer(r"[.!?;…]+(?=\s)|\n{2,}", texto):
        if m.end() <= inicio:
            continue
        partes.append(texto[inicio:m.end()])
        inicio = m.end()
    if inicio < len(texto):
        partes.append(texto[inicio:])
    return partes


def _norm(s: str) -> str:
    return " ".join((s or "").split())


def reconciliar(liberado: str, final: str) -> tuple:
    """Compara o que já foi entregue em streaming com o texto FINAL (depois de segurança/validador/etiquetas).
    Devolve (ok, resto): ok=True e o `resto` ainda NÃO entregue; ok=False se o final não começa pelo liberado
    (ex.: o validador reescreveu a resposta) — aí a sessão deve cancelar e entregar o final inteiro."""
    lib, fin = _norm(liberado), _norm(final)
    if not lib:
        return True, final.strip()
    if fin == lib:
        return True, ""
    if fin.startswith(lib + " ") or fin.startswith(lib):
        # acha o ponto de corte no texto ORIGINAL do final (preserva quebras de linha do resto)
        palavras = len(lib.split())
        partes = final.split()
        if len(partes) < palavras:
            return False, final.strip()
        idx, vistas = 0, 0
        for m in re.finditer(r"\S+", final):
            vistas += 1
            if vistas == palavras:
                idx = m.end()
                break
        return True, final[idx:].strip()
    return False, final.strip()


class SessaoDeEntrega:
    """Liga o portão ao Corpo (balão do chat em streaming) e à voz. Tudo injetado: `enviar(dict)` manda mensagem
    ao Godot; `falar` é um objeto com .add(texto) / .fim() / .cancelar() ou None (voz desligada)."""

    def __init__(self, enviar, criar_fala=None, pausado=lambda: False):
        self._enviar = enviar
        self._criar_fala = criar_fala
        self._pausado = pausado
        self._fala = None
        self.liberado = ""
        self.liberado_fala = ""                      # v27: o que a voz já recebeu (equações em português falado)
        self.iniciada = False
        self.cancelada = False

    def ao_liberar(self, trecho: str, fala: str = None):
        if self.cancelada or self._pausado():
            return
        self.iniciada = True
        falado = trecho if fala is None else fala
        self.liberado += trecho
        self.liberado_fala += falado
        self._enviar({"action": "chat_stream_chunk", "delta": trecho, "done": False})   # o trecho já leva o espaço final
        if self._criar_fala is not None:
            if self._fala is None:
                self._fala = self._criar_fala()
            if self._fala is not None:
                self._fala.add(falado)

    def entregar_resto(self, resto: str, resto_fala: str = None):
        """Final bateu com o liberado: manda só o que faltava e fecha o balão e a fala.
        v26: `resto_fala` = o mesmo resto, mas escrito pra ser LIDO (equações em português: "x ao quadrado")."""
        if resto:
            self._enviar({"action": "chat_stream_chunk", "delta": resto, "done": False})
        falado = resto if resto_fala is None else resto_fala
        if falado and self._fala is not None:
            self._fala.add(falado)
        self._enviar({"action": "chat_stream_chunk", "delta": "", "done": True})
        if self._fala is not None:
            self._fala.fim()

    def cancelar(self):
        """Final NÃO bateu (ex.: validador reescreveu): corta a voz e fecha o balão parcial."""
        self.cancelada = True
        if self._fala is not None:
            self._fala.cancelar()
        if self.iniciada:
            self._enviar({"action": "chat_stream_chunk", "delta": "", "done": True})
