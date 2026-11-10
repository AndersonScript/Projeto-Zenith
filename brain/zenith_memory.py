# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_memory.py — Memória semântica de longo prazo (ChromaDB).
#  Corrigido: nomes vêm do perfil (antes "Anderson" era fixo).
# ============================================================

import uuid
from datetime import datetime
from brain import zenith_plataforma
from brain.zenith_settings import MEMORY_DIR

# v1.11 (port celular) — o chromadb (com onnxruntime) é pesado e não é garantido no Android. No celular a coleção
# vem do SQLite leve (zenith_memoria_leve), que imita só o pedaço do chromadb que o Zenith usa. No PC nada muda:
# o import abaixo continua acontecendo aqui, no mesmo momento de sempre.
if zenith_plataforma.detectar() != "android":
    import chromadb
    from chromadb.config import Settings as ChromaSettings
else:
    chromadb = None
    ChromaSettings = None


class ZenithMemory:
    def __init__(self, settings):
        self.settings = settings        # v23: limites de busca/fatos fixos vêm daqui (com padrões seguros)
        # CORREÇÃO (crash no .exe: "No module named
        # 'chromadb.telemetry.product.posthog'"): o chromadb resolve a
        # classe de telemetria (posthog) por uma string de config,
        # importada dinamicamente via importlib — análise estática do
        # PyInstaller não enxerga isso, então o .pth ficava faltando no
        # pacote. anonymized_telemetry=False evita essa importação por
        # completo (e de quebra é mais privado — nada sai da sua
        # máquina). Combinado com --collect-all chromadb no
        # build_exe.py (defesa em duas camadas, igual foi feito pro
        # microfone/câmera).
        if chromadb is None:        # v1.11 — celular: memória leve (busca por palavras), mesma interface
            from brain import zenith_memoria_leve
            self.client = None
            self.collection = zenith_memoria_leve.abrir(MEMORY_DIR)
            print("🧠 Memória de longo prazo carregada (leve, para o celular).")
            return
        self.client = chromadb.PersistentClient(
            path=str(MEMORY_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="zenith_long_term_memory",
            metadata={"hnsw:space": "l2"})
        print("🧠 Memória de longo prazo carregada.")

    def save(self, user_name: str, persona_name: str, user_msg: str, ai_response: str):
        # AJUSTE (memória mais organizada): marca explicitamente como
        # "chat_raw" — a troca crua do dia a dia. Diferente de um "fato"
        # (ver save_fact), isso aqui é candidato a ser resumido/apagado
        # mais tarde por _prune_if_needed(), então nunca guarde algo
        # importante SÓ aqui.
        novo_id = str(uuid.uuid4())
        # v1.0 (A2) — chave de API nunca vai para a memória de longo prazo.
        from brain import zenith_segredos as _segredos
        self.collection.add(
            documents=[f"{user_name}: {_segredos.mascarar(user_msg)}\n{persona_name}: {_segredos.mascarar(ai_response)}"],
            metadatas=[{"timestamp": datetime.now().isoformat(), "type": "chat_raw"}],
            ids=[novo_id])
        return novo_id          # v27: quem chama pode desfazer (resposta cancelada com o ⏹ não deve virar "memória")

    def apagar_id(self, id_: str):
        """v27 — remove UMA troca da memória pelo id que save() devolveu (usado quando o usuário manda PARAR)."""
        try:
            self.collection.delete(ids=[id_])
            return True
        except Exception as e:
            print(f"[Zenith/Memória] não consegui desfazer a troca {id_}: {e}")
            return False

    # FEATURE (memória mais organizada — fato permanente): usado quando a
    # IA marca algo como digno de lembrar de verdade (ver <lembrar> em
    # zenith_core.py) — nome, preferência, projeto em andamento, decisão
    # tomada. Fica marcado "fact" e NUNCA é apagado/resumido pela poda
    # automática (ver _prune_if_needed) — só a troca crua do dia a dia é.
    def save_fact(self, fact_text: str):
        from brain import zenith_segredos as _segredos
        fact_text = _segredos.mascarar(fact_text.strip())
        if not fact_text:
            return
        # v23: não grava o mesmo fato duas vezes (a IA repete <lembrar> com frequência)
        try:
            norma = " ".join(fact_text.lower().split())
            existentes = self.collection.get(where={"type": "fact"}, include=["documents"])
            for doc in (existentes.get("documents") or []):
                if " ".join(str(doc).lower().split()) == norma:
                    return
        except Exception:
            pass
        self.collection.add(
            documents=[fact_text],
            metadatas=[{"timestamp": datetime.now().isoformat(), "type": "fact"}],
            ids=[str(uuid.uuid4())])

    def _cfg(self, chave: str, padrao):
        try:
            v = self.settings.get(chave, padrao)
            return padrao if v is None else v
        except Exception:
            return padrao

    def recall(self, query: str, n_results: int = 6) -> str:
        """v24 — UMA consulta ao banco (um só cálculo de embedding; na v23 eram três, e isso pesava em PC lento).
        Pega os ~16 mais parecidos de qualquer tipo, descarta o que está longe demais do assunto
        (`memoria_dist_max`, padrão 1.25) e devolve até `memoria_recall_n`: FATOS primeiro (têm bônus), depois
        resumos, depois conversas cruas."""
        try:
            if self.collection.count() == 0:
                return ""
            n_results = int(self._cfg("memoria_recall_n", n_results))
            dist_max = float(self._cfg("memoria_dist_max", 1.25))
            r = self.collection.query(query_texts=[query], n_results=16, include=["documents", "distances", "metadatas"])
            docs = (r.get("documents") or [[]])[0]
            dists = (r.get("distances") or [[]])[0] if r.get("distances") else [0.0] * len(docs)
            metas = (r.get("metadatas") or [[]])[0] if r.get("metadatas") else [{}] * len(docs)
            bonus = {"fact": 0.25, "chat_summary": 0.1}
            achados = []
            for doc, dist, meta in zip(docs, dists, metas):
                tipo = (meta or {}).get("type", "chat_raw")
                achados.append((float(dist) - bonus.get(tipo, 0.0), float(dist), tipo, str(doc)))
            achados.sort(key=lambda a: a[0])
            vistos, saida, n_fatos = set(), [], 0
            for _, dist, tipo, doc in achados:
                chave = " ".join(doc.lower().split())
                if chave in vistos or (dist > dist_max and tipo != "fact"):
                    continue
                vistos.add(chave)
                saida.append(doc)
                if len(saida) >= n_results:
                    break
            return "\n".join(saida)
        except Exception as e:
            print(f"[Zenith] Erro na memória: {e}")
            return ""

    def fatos_fixos(self, max_chars: int = 2000) -> str:
        """v23 — o que ela SABE sobre a pessoa, sempre à mão: os fatos permanentes (<lembrar>), mais recentes
        primeiro, até `max_chars`. Vai no prompt do sistema de TODA mensagem (memória "implantada")."""
        try:
            max_chars = int(self._cfg("memoria_fatos_fixos_chars", max_chars))
            if max_chars <= 0 or self.collection.count() == 0:
                return ""
            tudo = self.collection.get(where={"type": "fact"}, include=["documents", "metadatas"])
            pares = list(zip(tudo.get("documents") or [], tudo.get("metadatas") or []))
            pares.sort(key=lambda p: (p[1] or {}).get("timestamp", ""), reverse=True)
            linhas, usado = [], 0
            for doc, _meta in pares:
                linha = "- " + " ".join(str(doc).split())
                if usado + len(linha) > max_chars:
                    break
                linhas.append(linha)
                usado += len(linha) + 1
            return "\n".join(linhas)
        except Exception as e:
            print(f"[Zenith] Erro lendo fatos fixos: {e}")
            return ""

    def list_recent(self, limit: int = 30) -> list:
        """FEATURE (mostrar o que ela lembra): a memória semântica
        (recall) só busca contexto POR TRÁS DOS PANOS pra cada
        resposta — não existia um jeito de simplesmente OLHAR o que
        já foi guardado. Isso alimenta o painel "🧠 Memórias" no
        Corpo: pega tudo do ChromaDB e devolve as mais recentes
        primeiro, com um resuminho de cada uma."""
        try:
            if self.collection.count() == 0:
                return []
            tudo = self.collection.get(include=["documents", "metadatas"])
            itens = []
            for doc, meta in zip(tudo.get("documents", []), tudo.get("metadatas", [])):
                itens.append({
                    "text": doc,
                    "timestamp": (meta or {}).get("timestamp", ""),
                    # FEATURE (memória mais organizada): "fact" | "chat_summary" |
                    # "chat_raw" — deixa o painel "🧠 Memórias" mostrar cada tipo
                    # diferente (ver _on_memories_list em ui_manager.gd).
                    "mem_type": (meta or {}).get("type", "chat_raw"),
                })
            itens.sort(key=lambda i: i["timestamp"], reverse=True)
            return itens[:limit]
        except Exception as e:
            print(f"[Zenith] Erro ao listar memórias: {e}")
            return []

    # ==================== FEATURE: memória mais organizada ====================
    # Antes, TODA troca de chat virava um documento cru na memória, pra
    # sempre — sem separar o que é "fato" do que é conversa fiada, e sem
    # nunca resumir nada. Isso tem dois problemas: 1) o painel de memórias
    # vira uma lista infinita de "oi/tudo bem", sem destacar o que
    # realmente importa; 2) quanto mais se usa o Zenith, mais devagar (e
    # mais caro, se o provedor cobrar por token) fica CADA resposta nova,
    # porque a busca semântica (recall) passa a vasculhar um histórico
    # cru cada vez maior. A solução tem duas partes: fatos marcados
    # explicitamente (save_fact, acima) nunca são tocados aqui; já a
    # conversa crua do dia a dia, quando passa de LIMITE_CHAT_RAW
    # documentos, tem o lote mais antigo resumido em UM documento só
    # (ver ZenithCore._resumir_memorias_antigas_se_preciso, que chama os
    # métodos abaixo) e os originais são apagados.
    LIMITE_CHAT_RAW = 200
    LOTE_PARA_RESUMIR = 100

    def contagem_chat_raw(self) -> int:
        try:
            tudo = self.collection.get(where={"type": "chat_raw"}, include=[])
            return len(tudo.get("ids", []))
        except Exception as e:
            print(f"[Zenith/Memória] Erro contando conversas: {e}")
            return 0

    def lote_mais_antigo_para_resumir(self, limite: int = LOTE_PARA_RESUMIR):
        """Retorna (ids, textos) do lote mais antigo de chat_raw — NÃO
        apaga nada aqui, só lê. Quem decide resumir e chama
        substituir_por_resumo() depois é o ZenithCore (é ele quem tem
        acesso ao provedor de IA pra gerar o resumo em si)."""
        try:
            tudo = self.collection.get(where={"type": "chat_raw"}, include=["documents", "metadatas"])
            pares = list(zip(tudo.get("ids", []), tudo.get("documents", []), tudo.get("metadatas", [])))
            pares.sort(key=lambda p: (p[2] or {}).get("timestamp", ""))
            lote = pares[:limite]
            return [p[0] for p in lote], [p[1] for p in lote]
        except Exception as e:
            print(f"[Zenith/Memória] Erro pegando lote pra resumir: {e}")
            return [], []

    def substituir_por_resumo(self, ids_originais: list, texto_resumo: str):
        """Apaga o lote cru e guarda UM documento resumo no lugar,
        marcado "chat_summary" (nem "fact" nem "chat_raw" — não conta
        pra próxima poda, mas também não é tratado como fato
        permanente do usuário)."""
        texto_resumo = texto_resumo.strip()
        if not texto_resumo or not ids_originais:
            return
        self.collection.add(
            documents=[texto_resumo],
            metadatas=[{"timestamp": datetime.now().isoformat(), "type": "chat_summary"}],
            ids=[str(uuid.uuid4())])
        try:
            self.collection.delete(ids=ids_originais)
        except Exception as e:
            print(f"[Zenith/Memória] Resumo salvo, mas não consegui apagar o lote " +
                  f"original ({len(ids_originais)} itens): {e}")

    # ==================== v18: diário / listar com id / esquecer UM item ====================
    # A lógica mora em zenith_memoria_util.py (testável sem instalar o chromadb).
    def save_summary(self, texto: str) -> bool:
        from brain import zenith_memoria_util as u
        return u.guardar_resumo(self.collection, texto)

    def list_with_ids(self, termo: str = "", limite: int = 20) -> list:
        from brain import zenith_memoria_util as u
        return u.listar_com_id(self.collection, termo, limite)

    def forget(self, ref: str):
        from brain import zenith_memoria_util as u
        return u.apagar_por_ref(self.collection, ref)
