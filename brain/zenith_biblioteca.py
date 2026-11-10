"""
Zenith — BIBLIOTECA DE DOCUMENTOS (v28) — o "NotebookLM local".

Você coloca apostilas, datasheets, artigos e anotações (PDF, Word, PowerPoint, Excel, texto) e a Zenith passa a responder
CITANDO a fonte e a página. É a ideia da outra IA ("Biblioteca de PDFs — é a que eu mais manteria") feita pra funcionar
OFFLINE e sem peso: a busca é por palavras (BM25, o mesmo princípio dos buscadores), feita só com a biblioteca padrão — não
precisa de embeddings, de GPU nem de rede, e a pessoa vê exatamente de qual página veio cada trecho.

  /biblioteca                    lista o que já está guardado
  /biblioteca add <arquivo|pasta> guarda (PDF, DOCX, PPTX, XLSX, TXT, MD…) — pasta: até 40 arquivos
  /biblioteca buscar <pergunta>   mostra os trechos mais parecidos, com arquivo e página
  /biblioteca remover <nome>      tira da biblioteca (o arquivo original não é tocado)

Automático: quando você pergunta algo e a biblioteca tem trechos MUITO parecidos, eles vão junto da pergunta como
CONTEÚDO EXTERNO em quarentena (ver zenith_quarentena.py) com a instrução de citar [arquivo, p. N]. Desliga com
`biblioteca_auto: false`. O índice fica em config/biblioteca/ (só no seu computador).

Lógica pura: sem rede, sem Godot — testável com arquivos de mentira.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from pathlib import Path

from brain import zenith_anexos as anexos
from brain import zenith_quarentena as quarentena

EXT_SUPORTADAS = {".pdf", ".docx", ".pptx", ".xlsx"} | anexos.EXT_TEXTO
TAM_TRECHO = 900              # caracteres por trecho
SOBREPOSICAO = 150
MAX_ARQUIVOS_PASTA = 40
MAX_BYTES_ARQUIVO = 120_000_000
MAX_TRECHOS_TOTAL = 60000
MIN_TERMOS_AUTO = 2           # pra injetar trechos sozinha: pelo menos 2 palavras da pergunta têm que aparecer no trecho…
MIN_COBERTURA_AUTO = 0.5      # …e cobrir metade ou mais das palavras úteis da pergunta (evita "oi" puxar a apostila)

_STOP = frozenset("""a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre entre e ou mas que se
 como mais menos muito muita já não nao é são foi ser ter tem há ao aos à às seu sua seus suas meu minha eu tu ele ela nós vocês
 você voce isso isto esse essa aquele aquela qual quais quando onde porque também so só the of and to in is are for on with""".split())


class ErroBiblioteca(Exception):
    """Mensagem já em português, pronta pro chat."""


def _pasta_padrao() -> Path:
    from brain.zenith_settings import CONFIG_DIR
    return Path(CONFIG_DIR) / "biblioteca"


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def tokenizar(texto: str) -> list:
    t = _sem_acento((texto or "").lower())
    return [w for w in re.findall(r"[a-z0-9]{2,}", t) if w not in _STOP]


# ----------------------------------------------------------------------------------------------- extração em trechos
def _quebrar_em_trechos(texto: str) -> list:
    texto = re.sub(r"[ \t]+", " ", texto or "").strip()
    if not texto:
        return []
    if len(texto) <= TAM_TRECHO:
        return [texto]
    trechos, i = [], 0
    while i < len(texto):
        fim = min(len(texto), i + TAM_TRECHO)
        if fim < len(texto):                               # corta em fim de frase/linha se der
            corte = max(texto.rfind(". ", i, fim), texto.rfind("\n", i, fim))
            if corte > i + TAM_TRECHO // 2:
                fim = corte + 1
        trechos.append(texto[i:fim].strip())
        if fim >= len(texto):
            break
        i = max(fim - SOBREPOSICAO, i + 1)
    return [t for t in trechos if t]


def extrair_paginas(caminho: str) -> list:
    """[(rótulo_da_página, texto)] — PDF por página; PPTX por slide; o resto vira blocos de ~3000 caracteres."""
    ext = Path(caminho).suffix.lower()
    if ext == ".pdf":
        return [(n, t) for n, t in anexos.paginas_pdf(caminho) if t.strip()]
    if ext == ".pptx":
        txt = anexos.texto_pptx(caminho)
        partes = re.split(r"--- Slide (\d+) ---\n", txt)
        return [(int(partes[i]), partes[i + 1]) for i in range(1, len(partes) - 1, 2) if partes[i + 1].strip()]
    if ext == ".docx":
        bruto = anexos.texto_docx(caminho)
    elif ext == ".xlsx":
        bruto = anexos.texto_xlsx(caminho, max_linhas=2000)
    else:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            bruto = f.read(3_000_000)
    blocos = [bruto[i:i + 3000] for i in range(0, len(bruto), 3000)]
    return [(i + 1, b) for i, b in enumerate(blocos) if b.strip()]


# ----------------------------------------------------------------------------------------------- a biblioteca
class Biblioteca:
    def __init__(self, pasta=None):
        self.pasta = Path(pasta) if pasta else _pasta_padrao()
        self.arquivo = self.pasta / "index.json"
        self._dados = None
        self._bm25 = None

    # ---- persistência
    def _carregar(self) -> dict:
        if self._dados is None:
            try:
                self._dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._dados = {"docs": {}, "trechos": []}
            self._dados.setdefault("docs", {})
            self._dados.setdefault("trechos", [])
        return self._dados

    def _salvar(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._dados, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.arquivo)
        self._bm25 = None

    def tem_documentos(self) -> bool:
        return bool(self._carregar()["docs"])

    def documentos(self) -> list:
        return sorted(self._carregar()["docs"].values(), key=lambda d: d["nome"].lower())

    # ---- adicionar / remover
    @staticmethod
    def _hash_arquivo(caminho: str) -> str:
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()[:16]

    def adicionar_arquivo(self, caminho: str, progresso=None) -> dict:
        p = Path(caminho)
        if not p.is_file():
            raise ErroBiblioteca(f"📚 Não achei o arquivo: {caminho}")
        if p.suffix.lower() not in EXT_SUPORTADAS:
            raise ErroBiblioteca(f"📚 Não sei guardar '{p.suffix or p.name}' na biblioteca (aceito PDF, Word, PowerPoint, Excel e texto/código).")
        if p.stat().st_size > MAX_BYTES_ARQUIVO:
            raise ErroBiblioteca(f"📚 '{p.name}' é grande demais pra biblioteca ({anexos.tamanho_legivel(p.stat().st_size)}).")
        dados = self._carregar()
        h = self._hash_arquivo(str(p))
        if h in dados["docs"]:
            return {**dados["docs"][h], "ja_existia": True}
        try:
            paginas = extrair_paginas(str(p))
        except RuntimeError as e:
            raise ErroBiblioteca(f"📚 {e}")
        except Exception as e:
            raise ErroBiblioteca(f"📚 Não consegui ler '{p.name}': {type(e).__name__}: {e}")
        novos = []
        for i, (pag, texto) in enumerate(paginas):
            if progresso and i % 5 == 0:
                progresso(100.0 * i / max(1, len(paginas)), f"{p.name}: página {pag}")
            for t in _quebrar_em_trechos(texto):
                novos.append({"doc": h, "pagina": pag, "texto": t})
        if not novos:
            raise ErroBiblioteca(f"📚 '{p.name}' não tem texto que eu consiga ler (talvez seja um PDF escaneado — imagem).")
        if len(dados["trechos"]) + len(novos) > MAX_TRECHOS_TOTAL:
            raise ErroBiblioteca("📚 A biblioteca está cheia — remova algum documento antes (/biblioteca remover <nome>).")
        dados["trechos"].extend(novos)
        dados["docs"][h] = {"id": h, "nome": p.name, "caminho": str(p), "paginas": len(paginas), "trechos": len(novos),
                            "adicionado": time.strftime("%Y-%m-%d %H:%M")}
        self._salvar()
        return {**dados["docs"][h], "ja_existia": False}

    def adicionar(self, caminho: str, progresso=None) -> dict:
        """Arquivo OU pasta. Devolve {"adicionados": [...], "repetidos": [...], "erros": [...]}."""
        p = Path(caminho)
        if p.is_dir():
            arquivos = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in EXT_SUPORTADAS)[:MAX_ARQUIVOS_PASTA]
            if not arquivos:
                raise ErroBiblioteca("📚 Não achei nenhum PDF/Word/PowerPoint/Excel/texto nessa pasta.")
        else:
            arquivos = [p]
        res = {"adicionados": [], "repetidos": [], "erros": []}
        for i, f in enumerate(arquivos):
            try:
                r = self.adicionar_arquivo(str(f), None if progresso is None else (lambda pct, det=None, _i=i: progresso((100.0 * _i + pct) / len(arquivos), det)))
                (res["repetidos"] if r.get("ja_existia") else res["adicionados"]).append(r)
            except ErroBiblioteca as e:
                if len(arquivos) == 1:
                    raise
                res["erros"].append(f"{f.name}: {str(e).replace('📚 ', '')}")
        return res

    def remover(self, nome_ou_id: str) -> dict:
        dados = self._carregar()
        q = (nome_ou_id or "").strip().lower()
        alvos = [d for d in dados["docs"].values() if d["id"] == q or d["nome"].lower() == q] or \
                [d for d in dados["docs"].values() if q and q in d["nome"].lower()]
        if not alvos:
            raise ErroBiblioteca(f"📚 Não achei '{nome_ou_id}' na biblioteca (veja /biblioteca).")
        if len(alvos) > 1:
            raise ErroBiblioteca("📚 Mais de um documento combina: " + ", ".join(d["nome"] for d in alvos) + ". Escreva o nome completo.")
        d = alvos[0]
        dados["trechos"] = [t for t in dados["trechos"] if t["doc"] != d["id"]]
        del dados["docs"][d["id"]]
        self._salvar()
        return d

    # ---- busca (BM25)
    def _indice(self):
        if self._bm25 is None:
            trechos = self._carregar()["trechos"]
            tfs, df, comp = [], {}, []
            for t in trechos:
                toks = tokenizar(t["texto"])
                tf = {}
                for w in toks:
                    tf[w] = tf.get(w, 0) + 1
                for w in tf:
                    df[w] = df.get(w, 0) + 1
                tfs.append(tf)
                comp.append(len(toks))
            media = (sum(comp) / len(comp)) if comp else 1.0
            self._bm25 = (tfs, df, comp, media)
        return self._bm25

    def buscar(self, pergunta: str, k: int = 5) -> list:
        dados = self._carregar()
        termos = list(dict.fromkeys(tokenizar(pergunta)))
        if not termos or not dados["trechos"]:
            return []
        tfs, df, comp, media = self._indice()
        n = len(tfs)
        k1, b = 1.4, 0.75
        pontos = []
        for i, tf in enumerate(tfs):
            s, casados = 0.0, 0
            for w in termos:
                f = tf.get(w)
                if not f:
                    continue
                casados += 1
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * comp[i] / media))
            if s > 0:
                pontos.append((s, i, casados))
        pontos.sort(reverse=True)
        saida = []
        for s, i, casados in pontos[:k]:
            t = dados["trechos"][i]
            d = dados["docs"].get(t["doc"], {})
            saida.append({"pontos": round(s, 2), "arquivo": d.get("nome", "?"), "pagina": t["pagina"], "texto": t["texto"],
                          "casados": casados, "cobertura": round(casados / len(termos), 2)})
        return saida


# ----------------------------------------------------------------------------------------------- texto pro chat e pro prompt
def formatar_lista(bib: Biblioteca) -> str:
    docs = bib.documentos()
    if not docs:
        return ("📚 A biblioteca está vazia.\nGuarde apostilas, datasheets e artigos com: /biblioteca add <arquivo ou pasta>\n"
                "Depois é só perguntar — eu respondo citando o arquivo e a página.")
    linhas = [f"📚 Biblioteca: {len(docs)} documento(s)"]
    for d in docs:
        linhas.append(f"• {d['nome']} — {d['paginas']} pág./blocos · adicionado {d['adicionado']}")
    linhas.append("Comandos: /biblioteca buscar <pergunta> · /biblioteca add <caminho> · /biblioteca remover <nome>")
    return "\n".join(linhas)


def formatar_busca(resultados: list) -> str:
    if not resultados:
        return "📚 Não achei nada parecido na biblioteca."
    linhas = ["📚 Trechos mais parecidos:"]
    for r in resultados:
        trecho = " ".join(r["texto"].split())
        linhas.append(f"• {r['arquivo']} — p. {r['pagina']}: {trecho[:260]}{'…' if len(trecho) > 260 else ''}")
    return "\n".join(linhas)


def contexto_para(bib: Biblioteca, pergunta: str, usuario: str = "o usuário", k: int = 3) -> str:
    """Trechos relevantes embrulhados como conteúdo externo (ou "" se nada for parecido o bastante)."""
    if not bib.tem_documentos() or len(tokenizar(pergunta)) < 2:
        return ""
    achados = [r for r in bib.buscar(pergunta, k)
               if r["casados"] >= MIN_TERMOS_AUTO and r["cobertura"] >= MIN_COBERTURA_AUTO]
    if not achados:
        return ""
    corpo = "\n\n".join(f"[{r['arquivo']}, p. {r['pagina']}]\n{r['texto']}" for r in achados)
    return (quarentena.envolver(corpo, "biblioteca do usuário", usuario) +
            f"\nSe usar algo desses trechos, CITE a fonte no formato [arquivo, p. N]. Se a pergunta não tiver relação com eles, ignore-os.")


_PADRAO = None


def padrao() -> "Biblioteca":
    """A biblioteca única do programa (core, comandos e Corpo enxergam o mesmo índice em memória)."""
    global _PADRAO
    if _PADRAO is None:
        _PADRAO = Biblioteca()
    return _PADRAO
