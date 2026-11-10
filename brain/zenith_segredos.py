"""
Zenith — SEGREDOS QUE NUNCA DEVEM FICAR GUARDADOS (v1.0, tarefa A2).

O que aconteceu de verdade (17/10): o Anderson digitou uma chave de API INTEIRA no chat
(`/chave add gemini AIza...`) e ela ficou visível no balão e salva no histórico. Uma chave
que aparece em texto puro numa conversa salva, num arquivo de memória ou num log é uma
chave comprometida — ele já teve que trocar essa.

Este módulo é o único lugar que sabe reconhecer e mascarar uma chave:

    mascarar("/chave add gemini AIzaSyD...cet0")  ->  "/chave add gemini ••••cet0"
    contem_segredo("minha chave é sk-abc...")     ->  True

Formato da máscara: `••••` + os 4 últimos caracteres (igual ao resto do Zenith). Assim o
usuário reconhece a chave sem que o valor possa ser usado por quem ler o arquivo.

É lógica pura (sem rede, sem disco): o mascaramento dos arquivos antigos fica em
`mascarar_arquivo_json`, e quem chama decide quando rodar.
"""
from __future__ import annotations

import json
import os
import re

MASCARA = "••••"

# Padrões dos provedores que o Zenith usa. Deliberadamente específicos: mascarar texto normal
# (uma frase qualquer, um número de 10 dígitos) seria pior do que não mascarar nada.
PADROES = (
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),                       # Google / Gemini
    re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"),       # OpenAI / Anthropic (sk-ant-)
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{20,}"),                     # Groq
    re.compile(r"\btvly-[A-Za-z0-9_\-]{10,}"),                    # Tavily
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),                         # Hugging Face
    re.compile(r"\b(?:xai|r8|pplx)-[A-Za-z0-9_\-]{20,}"),         # xAI / Replicate / Perplexity
)

# "Bearer <token>" — o token em si nunca deve ser guardado; o prefixo fica (é o que explica o erro).
_BEARER = re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._\-]{16,})")

# Comando que MANDA uma chave. A resposta dele avisa para limpar a área de transferência.
_COMANDO_CHAVE = re.compile(r"(?i)^\s*/chaves?\s+(add|adicionar|somar)\b")


def _mascarar_valor(valor: str) -> str:
    return MASCARA + (valor[-4:] if len(valor) >= 4 else "")


def mascarar(texto: str) -> str:
    """Troca qualquer chave reconhecível por `••••1234`. Texto sem chave volta idêntico."""
    if not texto:
        return texto
    saida = str(texto)
    for padrao in PADROES:
        saida = padrao.sub(lambda m: _mascarar_valor(m.group(0)), saida)
    saida = _BEARER.sub(lambda m: m.group(1) + _mascarar_valor(m.group(2)), saida)
    return saida


def contem_segredo(texto: str) -> bool:
    """True se o texto tem cara de chave de API (usado para avisar no chat)."""
    if not texto:
        return False
    return any(p.search(str(texto)) for p in PADROES) or bool(_BEARER.search(str(texto)))


def eh_comando_de_chave(texto: str) -> bool:
    return bool(_COMANDO_CHAVE.match(texto or ""))


AVISO_CHAVE_NO_CHAT = (
    "🔐 Parece que você colou uma **chave de API** na conversa. Eu não guardei o valor: "
    "no histórico e na memória ela fica só como •••• (últimos 4 caracteres).\n"
    "Para cadastrar de um jeito seguro, use `/chave add gemini A_CHAVE` (o comando não entra no "
    "histórico) ou o menu Configurações > IAs & Chaves. Depois apague a mensagem da área de "
    "transferência (Ctrl+Shift+V mostra o que está lá) e, se ela já circulou, troque a chave no "
    "site do provedor."
)


def mascarar_dados(dados) -> tuple:
    """Mascara um dicionário de conversas JÁ CARREGADO. Devolve (dados, quantas mensagens mudaram)."""
    mudadas = 0
    if not isinstance(dados, dict):
        return dados, 0

    def _trata(txt):
        nonlocal mudadas
        novo = mascarar(txt)
        if novo != txt:
            mudadas += 1
        return novo

    for conversa in dados.get("conversations", []) or []:
        if not isinstance(conversa, dict):
            continue
        if isinstance(conversa.get("title"), str):
            conversa["title"] = _trata(conversa["title"])
        for msg in conversa.get("messages", []) or []:
            if isinstance(msg, dict) and isinstance(msg.get("text"), str):
                msg["text"] = _trata(msg["text"])
    return dados, mudadas


def mascarar_arquivo_json(caminho, marcador=None) -> int:
    """Varre UM arquivo JSON de conversas e mascara o que for chave. Devolve quantas mensagens mudaram.

    `marcador`, se existir, evita repetir a varredura a cada abertura (é uma varredura única).
    Nunca levanta exceção: se o arquivo estiver corrompido, devolve 0 e a vida segue.
    """
    caminho = str(caminho)
    if marcador and os.path.exists(str(marcador)):
        return 0
    mudadas = 0
    try:
        if os.path.isfile(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
            dados, mudadas = mascarar_dados(dados)
            if mudadas:
                tmp = caminho + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(dados, f, indent=2, ensure_ascii=False)
                os.replace(tmp, caminho)
    except Exception as e:                                  # nunca derrubar o programa por causa disto
        print(f"[Zenith/Segredos] não consegui varrer {caminho}: {e}")
        return 0
    if marcador:
        try:
            with open(str(marcador), "w", encoding="utf-8") as f:
                f.write(f"v1.0 — {mudadas} mensagem(ns) mascarada(s)\n")
        except OSError:
            pass
    return mudadas
