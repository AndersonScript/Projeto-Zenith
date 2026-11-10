# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_history.py — Múltiplas conversas persistentes.
#
#  Antes: um único histórico linear, sem separação por conversa.
#  Agora: cada conversa tem id, título, se está fixada ("importante")
#  e sua própria lista de mensagens — é isso que alimenta a barra
#  lateral no Godot (estilo Gemini/Claude/ChatGPT).
# ============================================================

import json
import os
import threading
import uuid
from datetime import datetime

from brain.zenith_settings import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "conversations.json"
MAX_MESSAGES_PER_CONV = 500

_lock = threading.RLock()  # CORREÇÃO: era Lock() normal — get_active_id() tranca
# o arquivo e, se não houver conversa nenhuma, chama new_conversation() por
# dentro, que tentava trancar o MESMO lock de novo. Com Lock() normal isso
# trava pra sempre (deadlock) logo no primeiro uso, sem nenhum histórico
# ainda salvo. RLock() permite a mesma thread travar de novo sem travar
# nela mesma.


def _load_all() -> dict:
    if not HISTORY_FILE.exists():
        return {"conversations": [], "active_id": None}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("conversations", [])
        data.setdefault("active_id", None)
        return data
    except Exception as e:
        print(f"[Zenith/Histórico] Não deu pra ler conversations.json ({e}). Começando vazio.")
        return {"conversations": [], "active_id": None}


def _save_all(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, HISTORY_FILE)


def list_conversations() -> list:
    """Resumo pra barra lateral: sem o corpo das mensagens (fica leve)."""
    data = _load_all()
    items = [{
        "id": c["id"], "title": c.get("title") or "Nova conversa",
        "pinned": c.get("pinned", False), "created_at": c.get("created_at", ""),
        "message_count": len(c.get("messages", [])),
    } for c in data["conversations"]]
    # Fixadas primeiro, depois mais recente primeiro
    items.sort(key=lambda c: (not c["pinned"], c["created_at"]), reverse=False)
    items.sort(key=lambda c: c["pinned"], reverse=True)
    return items


def get_active_id() -> str:
    with _lock:
        data = _load_all()
        if data["active_id"] and any(c["id"] == data["active_id"] for c in data["conversations"]):
            return data["active_id"]
        return new_conversation()


def set_active_id(conv_id: str):
    with _lock:
        data = _load_all()
        if any(c["id"] == conv_id for c in data["conversations"]):
            data["active_id"] = conv_id
            _save_all(data)


def new_conversation(title: str = None) -> str:
    with _lock:
        data = _load_all()
        conv_id = uuid.uuid4().hex[:12]
        data["conversations"].insert(0, {
            "id": conv_id, "title": title or "Nova conversa", "pinned": False,
            "created_at": datetime.now().isoformat(timespec="seconds"), "messages": [],
        })
        data["active_id"] = conv_id
        _save_all(data)
        return conv_id


def get_conversation(conv_id: str) -> dict:
    data = _load_all()
    for c in data["conversations"]:
        if c["id"] == conv_id:
            return c
    return {"id": conv_id, "title": "Nova conversa", "pinned": False, "messages": []}


def append_message(conv_id: str, sender: str, text: str):
    if not text:
        return
    # v1.0 (A2) — nenhuma chave de API é gravada no conversations.json. Este é o único ponto
    # em que uma mensagem entra no arquivo, então mascarar aqui cobre toda a conversa.
    from brain import zenith_segredos as _segredos
    text = _segredos.mascarar(text)
    with _lock:
        data = _load_all()
        for c in data["conversations"]:
            if c["id"] == conv_id:
                c["messages"].append({"sender": sender, "text": text,
                                       "ts": datetime.now().isoformat(timespec="seconds")})
                c["messages"] = c["messages"][-MAX_MESSAGES_PER_CONV:]
                # Primeira mensagem do usuário vira o título automático
                # (igual Gemini/Claude/ChatGPT fazem) se ainda não foi nomeada.
                if c["title"] == "Nova conversa" and sender == "user":
                    c["title"] = (text[:42] + "…") if len(text) > 42 else text
                break
        _save_all(data)


def set_pinned(conv_id: str, pinned: bool):
    with _lock:
        data = _load_all()
        for c in data["conversations"]:
            if c["id"] == conv_id:
                c["pinned"] = pinned
                break
        _save_all(data)


def delete_conversation(conv_id: str):
    with _lock:
        data = _load_all()
        data["conversations"] = [c for c in data["conversations"] if c["id"] != conv_id]
        if data["active_id"] == conv_id:
            data["active_id"] = data["conversations"][0]["id"] if data["conversations"] else None
        _save_all(data)


def rename_conversation(conv_id: str, title: str):
    with _lock:
        data = _load_all()
        for c in data["conversations"]:
            if c["id"] == conv_id:
                c["title"] = title[:80]
                break
        _save_all(data)
