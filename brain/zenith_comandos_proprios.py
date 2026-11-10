"""Zenith — comandos próprios do usuário (v1.5, tarefa T8).

A lista de comandos já existia (`/ajuda`); o que faltava era a pessoa poder criar os dela.
Um comando próprio é **só um modelo de pedido**: um nome curto e um texto com `{argumento}`.
Nada aqui executa código, abre programa ou fala com a IA sozinho — quem monta o pedido e manda
para o chat é o `zenith_headless.py`, com a mesma aprovação de sempre.

    /comando                                    lista os seus comandos
    /comando add resumo :: Resuma em 5 linhas: {argumento}
    /comando apagar resumo

Guardado em `config/comandos_proprios.json` (dentro da sua pasta de dados, nunca no código).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ARQUIVO = "comandos_proprios.json"
NOME_VALIDO = re.compile("^[a-z][a-z0-9_]{1,19}$")
MARCADOR = "{argumento}"
LIMITE_COMANDOS = 50
LIMITE_MODELO = 2000
_PALAVRAS_RESERVADAS = {
    "ajuda", "comandos", "parar", "pausar", "retomar", "log", "nota", "notas", "lembrar",
    "lembretes", "diario", "diagnostico", "relatorio", "versao", "sobre", "tema", "modelos",
    "chaves", "rota", "local", "video", "biblioteca", "atualizar", "conversa", "comando",
}


def _pasta(base=None) -> Path:
    if base is not None:
        return Path(base)
    try:
        from brain.zenith_settings import CONFIG_DIR
        return Path(CONFIG_DIR)
    except Exception:
        return Path("config")


def _caminho(base=None) -> Path:
    return _pasta(base) / ARQUIVO


def carregar(base=None) -> dict:
    """Devolve {nome: modelo}. Arquivo torto/ilegível = dicionário vazio (nunca levanta)."""
    caminho = _caminho(base)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    itens = dados.get("comandos") if isinstance(dados, dict) else dados
    if not isinstance(itens, dict):
        return {}
    limpos = {}
    for nome, modelo in itens.items():
        n = str(nome).strip().lower()
        m = str(modelo or "").strip()
        if NOME_VALIDO.match(n) and m:
            limpos[n] = m[:LIMITE_MODELO]
    return limpos


def _salvar(comandos: dict, base=None) -> bool:
    caminho = _caminho(base)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps({"versao": 1, "comandos": comandos}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        return True
    except OSError:
        return False


def adicionar(nome: str, modelo: str, base=None) -> tuple:
    """Cria ou substitui um comando. Devolve (ok, mensagem)."""
    n = str(nome or "").strip().lower().lstrip("/")
    m = str(modelo or "").strip()
    if not NOME_VALIDO.match(n):
        return False, ("O nome do comando precisa ter de 2 a 20 caracteres, começar com letra e usar "
                       "só letras minúsculas, números e _ (ex.: resumo_aula).")
    if n in _PALAVRAS_RESERVADAS:
        return False, f"/{n} já é um comando do Zenith — escolha outro nome."
    if not m:
        return False, "Escreva o pedido. Use {argumento} onde entra o que você digitar depois do comando."
    if len(m) > LIMITE_MODELO:
        return False, f"O pedido é longo demais (máximo {LIMITE_MODELO} caracteres)."
    comandos = carregar(base)
    if n not in comandos and len(comandos) >= LIMITE_COMANDOS:
        return False, f"Você já tem {LIMITE_COMANDOS} comandos próprios — apague um antes de criar outro."
    if MARCADOR not in m:
        m = m + " " + MARCADOR
    comandos[n] = m
    if not _salvar(comandos, base):
        return False, "Não consegui salvar o arquivo de comandos."
    return True, f"Comando /{n} salvo. Escreva /{n} <o que quiser> e eu monto o pedido com isso."


def apagar(nome: str, base=None) -> tuple:
    n = str(nome or "").strip().lower().lstrip("/")
    comandos = carregar(base)
    if n not in comandos:
        return False, f"Não existe o comando /{n}."
    comandos.pop(n)
    if not _salvar(comandos, base):
        return False, "Não consegui salvar o arquivo de comandos."
    return True, f"Comando /{n} apagado."


def expandir(nome: str, argumento: str = "", base=None):
    """Devolve o pedido pronto (texto), ou None se o comando não existe.

    Não executa nada: é só `modelo.replace("{argumento}", argumento)`.
    """
    n = str(nome or "").strip().lower().lstrip("/")
    modelo = carregar(base).get(n)
    if not modelo:
        return None
    return modelo.replace(MARCADOR, str(argumento or "").strip()).strip()


def formatar_lista(base=None) -> str:
    comandos = carregar(base)
    if not comandos:
        return ("Nenhum comando próprio ainda. Crie um assim:\n"
                "/comando add resumo :: Resuma em 5 linhas: {argumento}\n"
                "Depois use /resumo <texto>. Um comando próprio não executa código: ele só monta o pedido.")
    linhas = ["Seus comandos (não executam código: só montam o pedido):"]
    for nome in sorted(comandos):
        linhas.append(f"• /{nome} — {comandos[nome]}")
    linhas.append("Apague com /comando apagar <nome>.")
    return "\n".join(linhas)


def tratar(arg: str, base=None) -> str:
    """Resolve `/comando ...` (lista, add, apagar). Devolve o texto da resposta."""
    partes = (arg or "").strip()
    if not partes:
        return formatar_lista(base)
    if partes.lower().startswith("add "):
        resto = partes[4:]
        if "::" not in resto:
            return ("Use assim: /comando add <nome> :: <pedido com {argumento}>\n"
                    "Exemplo: /comando add resumo :: Resuma em 5 linhas: {argumento}")
        nome, modelo = resto.split("::", 1)
        ok, msg = adicionar(nome.strip(), modelo.strip(), base)
        return ("✅ " if ok else "❌ ") + msg
    if partes.lower().startswith(("apagar ", "remover ", "excluir ")):
        nome = partes.split(None, 1)[1]
        ok, msg = apagar(nome, base)
        return ("✅ " if ok else "❌ ") + msg
    return formatar_lista(base)
