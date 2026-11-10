"""
Zenith — utilidades da memória que NÃO dependem do chromadb (por isso ficam
fora de zenith_memory.py: dá pra testar sem instalar nada pesado).

Todas recebem a "collection" do ChromaDB (ou qualquer objeto com add/get/delete
no mesmo formato) e nunca levantam exceção pra quem chamou.

  * guardar_resumo()   — o /diario grava um resumo (tipo "chat_summary", o 📎)
  * listar_com_id()    — /memorias [termo]: lista com um id curto + filtro
  * apagar_por_ref()   — /esquecer <id>: esquece UM item, por id (ou prefixo)
"""
import unicodedata
import uuid
from datetime import datetime

TAMANHO_REF = 8
MIN_REF = 4


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def guardar_resumo(collection, texto: str) -> bool:
    texto = str(texto or "").strip()
    if not texto:
        return False
    try:
        collection.add(documents=[texto],
                       metadatas=[{"timestamp": datetime.now().isoformat(), "type": "chat_summary"}],
                       ids=[str(uuid.uuid4())])
        return True
    except Exception as e:
        print(f"[Zenith/Memória] não consegui guardar o resumo: {e}")
        return False


def listar_com_id(collection, termo: str = "", limite: int = 20) -> list:
    """[{"id","ref","text","timestamp","mem_type"}], mais recentes primeiro.
    `termo` filtra por trecho (sem diferenciar maiúscula/acento)."""
    try:
        if collection.count() == 0:
            return []
        tudo = collection.get(include=["documents", "metadatas"])
        quero = _norm(termo).strip()
        itens = []
        for id_, doc, meta in zip(tudo.get("ids", []), tudo.get("documents", []), tudo.get("metadatas", [])):
            if quero and quero not in _norm(doc):
                continue
            itens.append({"id": id_, "ref": str(id_)[:TAMANHO_REF], "text": doc,
                          "timestamp": (meta or {}).get("timestamp", ""),
                          "mem_type": (meta or {}).get("type", "chat_raw")})
        itens.sort(key=lambda i: i["timestamp"], reverse=True)
        return itens[:max(1, int(limite))]
    except Exception as e:
        print(f"[Zenith/Memória] erro ao listar com id: {e}")
        return []


def apagar_por_ref(collection, ref: str):
    """Esquece UMA memória. `ref` = o id curto mostrado em /memorias (ou mais longo).
    Só apaga se identificar exatamente um item. Devolve (ok, mensagem)."""
    ref = str(ref or "").strip().lower()
    if len(ref) < MIN_REF:
        return False, f"Informe pelo menos {MIN_REF} caracteres do id (veja /memorias)."
    try:
        tudo = collection.get(include=["documents"])
        achados = [(i, d) for i, d in zip(tudo.get("ids", []), tudo.get("documents", []))
                   if str(i).lower().startswith(ref)]
        if not achados:
            return False, f"Não achei nenhuma memória com o id '{ref}'. Veja /memorias."
        if len(achados) > 1:
            return False, f"O id '{ref}' bate com {len(achados)} memórias — escreva mais caracteres."
        collection.delete(ids=[achados[0][0]])
        trecho = " ".join(str(achados[0][1]).split())[:80]
        return True, f"Esqueci: “{trecho}”"
    except Exception as e:
        return False, f"Não consegui apagar agora: {e}"
