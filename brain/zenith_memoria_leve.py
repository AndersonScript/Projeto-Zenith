"""Zenith — MEMÓRIA LEVE (v1.11): a coleção do chromadb, trocada por SQLite puro (para o celular).

Por que existe
--------------
`zenith_memory.py` é o ÚNICO módulo que importa o `chromadb` — e o chromadb (com onnxruntime e o modelo de
embeddings) é pesado e não é garantido no Android. Em vez de reescrever a memória, esta classe imita só o
pedaço da coleção do chromadb que o Zenith realmente usa:

    colecao.add(ids=, documents=, metadatas=)       colecao.count()
    colecao.delete(ids=)                            colecao.get(where=, include=)
    colecao.query(query_texts=, n_results=, include=)

Então, no celular, a troca em `zenith_memory.py` é UMA linha:
    self.collection = zenith_memoria_leve.abrir(MEMORY_DIR)      # em vez de chromadb.PersistentClient(...)
e `save`, `recall`, `fatos_fixos`, `forget`... continuam iguais.

O que muda de verdade (sem enfeite)
-----------------------------------
* A busca é por PALAVRAS (BM25 em Python puro, sem acento, com radical grosseiro), não por SENTIDO. "carro" não
  acha "automóvel". É o nível "memória leve" do downgrade; o nível "vetorial" (embeddings pequenos no aparelho)
  é um próximo passo e pluga aqui sem mudar quem chama.
* `distances` é uma pseudo-distância na MESMA escala do chromadb para o `memoria_dist_max` (padrão 1.25) do
  `recall` continuar valendo: 0 = todas as palavras da pergunta aparecem; 2 = nenhuma. Passa o corte quem
  cobre cerca de 40% das palavras (ponderadas pela raridade) ou mais.
* Cabe em milhares de itens (a busca percorre a tabela). Se passar de ~20 mil, o próximo passo é um índice.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import unicodedata
from collections import Counter

_PARADA = frozenset("""a o as os de do da dos das em no na nos nas um uma uns umas e ou que por para com se ao aos
mais mas como eu tu ele ela voce vc me te lhe meu minha seu sua isso isto esse essa este esta foi ser ter tem ja
nao sim""".split())

K1, B = 1.5, 0.75


def _tokens(texto: str) -> list:
    s = unicodedata.normalize("NFD", (texto or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    saida = []
    for t in re.findall(r"[a-z0-9]+", s):
        if (len(t) < 2 and not t.isdigit()) or t in _PARADA:
            continue
        saida.append(t[:6] if len(t) > 6 else t)               # radical grosseiro: programar/programação
    return saida


def _casa(meta: dict, where) -> bool:
    """Filtro estilo chromadb: {"type": "fact"}, {"type": {"$in": [...]}}, {"$and": [...]}, {"$or": [...]}."""
    if not where:
        return True
    for chave, cond in where.items():
        if chave == "$and":
            if not all(_casa(meta, w) for w in cond):
                return False
        elif chave == "$or":
            if not any(_casa(meta, w) for w in cond):
                return False
        else:
            valor = meta.get(chave)
            if isinstance(cond, dict):
                for op, esperado in cond.items():
                    if op == "$eq" and valor != esperado:
                        return False
                    if op == "$ne" and valor == esperado:
                        return False
                    if op == "$in" and valor not in esperado:
                        return False
                    if op == "$nin" and valor in esperado:
                        return False
            elif valor != cond:
                return False
    return True


class ColecaoLeve:
    def __init__(self, caminho: str = ":memory:"):
        if caminho != ":memory:":
            pasta = os.path.dirname(os.path.abspath(caminho))
            os.makedirs(pasta, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(caminho, check_same_thread=False)
        self._con.execute("""CREATE TABLE IF NOT EXISTS docs (
            ordem INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE NOT NULL, doc TEXT NOT NULL, meta TEXT NOT NULL, toks TEXT NOT NULL)""")
        self._con.commit()

    # ---- escrita ----------------------------------------------------------------------------------
    def add(self, ids, documents, metadatas=None):
        ids, documents = list(ids), list(documents)
        metadatas = list(metadatas) if metadatas is not None else [{} for _ in ids]
        if not (len(ids) == len(documents) == len(metadatas)):
            raise ValueError("ids, documents e metadatas precisam ter o mesmo tamanho.")
        with self._lock:
            for id_, doc, meta in zip(ids, documents, metadatas):
                # id repetido é ignorado (o chromadb também não duplica)
                self._con.execute("INSERT OR IGNORE INTO docs (id, doc, meta, toks) VALUES (?,?,?,?)",
                                  (str(id_), str(doc), json.dumps(meta or {}, ensure_ascii=False),
                                   " ".join(_tokens(str(doc)))))
            self._con.commit()

    def delete(self, ids=None, where=None):
        with self._lock:
            if ids is not None:
                self._con.executemany("DELETE FROM docs WHERE id=?", [(str(i),) for i in ids])
            if where:
                alvo = [i for i, m in self._con.execute("SELECT id, meta FROM docs")
                        if _casa(json.loads(m), where)]
                self._con.executemany("DELETE FROM docs WHERE id=?", [(i,) for i in alvo])
            self._con.commit()

    # ---- leitura ----------------------------------------------------------------------------------
    def count(self) -> int:
        with self._lock:
            return self._con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]

    def get(self, ids=None, where=None, include=None, limit=None):
        include = include if include is not None else ["documents", "metadatas"]
        quer = set(map(str, ids)) if ids is not None else None
        with self._lock:
            linhas = self._con.execute("SELECT id, doc, meta FROM docs ORDER BY ordem").fetchall()
        achados = [(i, d, json.loads(m)) for i, d, m in linhas
                   if (quer is None or i in quer) and _casa(json.loads(m), where)]
        if limit:
            achados = achados[: int(limit)]
        saida = {"ids": [a[0] for a in achados]}
        if "documents" in include:
            saida["documents"] = [a[1] for a in achados]
        if "metadatas" in include:
            saida["metadatas"] = [a[2] for a in achados]
        return saida

    def query(self, query_texts, n_results: int = 10, include=None, where=None):
        include = include if include is not None else ["documents", "metadatas", "distances"]
        with self._lock:
            linhas = self._con.execute("SELECT ordem, id, doc, meta, toks FROM docs").fetchall()
        base = []
        for ordem, id_, doc, meta, toks in linhas:
            m = json.loads(meta)
            if _casa(m, where):
                base.append((ordem, id_, doc, m, Counter(toks.split())))
        saida = {"ids": [], "documents": [], "metadatas": [], "distances": []}
        n = len(base)
        df = Counter()
        for *_, tf in base:
            df.update(tf.keys())
        comprimento_medio = (sum(sum(tf.values()) for *_, tf in base) / n) if n else 0.0
        for texto in ([query_texts] if isinstance(query_texts, str) else list(query_texts)):
            termos = set(_tokens(texto))
            ranque = []
            if n and termos:
                idf = {t: math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) for t in termos}
                soma_idf = sum(idf.values()) or 1.0
                for ordem, id_, doc, m, tf in base:
                    dl = sum(tf.values()) or 1
                    score = cobertos = 0.0
                    for t in termos:
                        f = tf.get(t, 0)
                        if f:
                            score += idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / (comprimento_medio or 1)))
                            cobertos += idf[t]
                    if score > 0:
                        ranque.append((score, ordem, id_, doc, m, round(2 * (1 - cobertos / soma_idf), 4)))
                ranque.sort(key=lambda r: (-r[0], -r[1]))          # empate: o mais novo primeiro
            ranque = ranque[: max(0, int(n_results))]
            saida["ids"].append([r[2] for r in ranque])
            saida["documents"].append([r[3] for r in ranque])
            saida["metadatas"].append([r[4] for r in ranque])
            saida["distances"].append([r[5] for r in ranque])
        return {k: v for k, v in saida.items() if k == "ids" or k in include}

    # ---- utilidades --------------------------------------------------------------------------------
    def importar_de(self, colecao_origem) -> int:
        """Copia tudo de outra coleção (ex.: a do chromadb do PC) — uma vez só, para levar a memória."""
        r = colecao_origem.get(include=["documents", "metadatas"])
        antes = self.count()
        self.add(r.get("ids") or [], r.get("documents") or [], r.get("metadatas") or None)
        return self.count() - antes

    def fechar(self):
        with self._lock:
            self._con.close()


def abrir(pasta: str, arquivo: str = "memoria_leve.sqlite3") -> ColecaoLeve:
    """Abre (ou cria) a memória leve dentro de `pasta` — no celular, a pasta de dados do app."""
    return ColecaoLeve(os.path.join(str(pasta), arquivo))
