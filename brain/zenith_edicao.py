"""Zenith — EDIÇÃO: "Público" (GitHub, qualquer pessoa) ou "Admin" (a cópia do dono).

Ideia do Anderson: "um modo só para mim, já pronto, tipo admin de tudo; quando executo outro modo ele vira o
dos usuários comuns, para colocar no GitHub". Por isso a edição NÃO é um interruptor que alguém vira dentro do
programa: ela é decidida na hora de MONTAR a pasta de distribuição (tools/preparar_publico.py grava o arquivo
`edition.json` com "publico" e REMOVE o que é só do dono). Quem baixa a edição Pública não tem como "destravar" nada,
porque o que é do Admin nem está na pasta.

Como o programa descobre a edição (nesta ordem):
  1. variável de ambiente ZENITH_EDICAO (útil em teste);
  2. arquivo `edition.json` ao lado do programa: {"edicao": "publico"} ou {"edicao": "admin"};
  3. sem nada disso: "admin" (é a pasta de desenvolvimento do dono).

Regras da edição Pública (o que a gente PROMETE a quem baixa):
  * nenhuma chave, conversa, memória ou avatar do dono vai junto;
  * todas as permissões começam em "ask" (nada roda sem aprovação — Pilar 1);
  * zero telemetria: o programa não envia nada sobre o uso;
  * não pede "reabrir como administrador do Windows" (o instalador cuida do que for preciso).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PUBLICO = "publico"
ADMIN = "admin"
ARQUIVO = "edition.json"

# Recursos que existem SÓ na edição Admin (hoje a lista é curta de propósito: os de código e de evolução
# ainda não foram construídos; quando forem, eles entram aqui e `recurso_liberado()` já os esconde do Público).
RECURSOS_ADMIN = frozenset({
    "console_dev",           # console de desenvolvedor
    "modo_evolucao",         # a IA propõe patch -> testes -> aprovação (A24 do plano)
    "plugins_com_codigo",    # habilidades que rodam código escrito por IA
    "diagnostico_completo",  # relatório com detalhes do computador do dono
    "sementes_pessoais",     # memórias/atalhos iniciais do dono
})


def _base_dir() -> Path:
    try:
        from brain.zenith_settings import BASE_DIR
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


def _normalizar(valor) -> str:
    v = str(valor or "").strip().lower()
    if v in ("publico", "público", "public", "usuario", "usuário"):
        return PUBLICO
    if v in ("admin", "administrador", "dono", "pessoal"):
        return ADMIN
    return ""


def edicao(base_dir=None) -> str:
    """'publico' ou 'admin'. Nunca levanta erro: arquivo ausente/torto = 'admin' (pasta de desenvolvimento)."""
    env = _normalizar(os.environ.get("ZENITH_EDICAO", ""))
    if env:
        return env
    try:
        caminho = Path(base_dir) / ARQUIVO if base_dir else _base_dir() / ARQUIVO
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        achou = _normalizar(dados.get("edicao", ""))
        if achou:
            return achou
    except Exception:
        pass
    return ADMIN


def e_publico(base_dir=None) -> bool:
    return edicao(base_dir) == PUBLICO


def e_admin(base_dir=None) -> bool:
    return edicao(base_dir) == ADMIN


def recurso_liberado(nome: str, base_dir=None) -> bool:
    """True se este recurso pode aparecer/rodar nesta edição. Recurso do Admin some no Público."""
    if str(nome) in RECURSOS_ADMIN:
        return e_admin(base_dir)
    return True


def gravar(destino_dir, edicao_nome: str) -> Path:
    """Escreve edition.json (quem chama é o preparar_publico.py). Recusa valor desconhecido."""
    nome = _normalizar(edicao_nome)
    if not nome:
        raise ValueError(f"edição desconhecida: {edicao_nome!r} (use 'publico' ou 'admin')")
    caminho = Path(destino_dir) / ARQUIVO
    caminho.write_text(json.dumps({"edicao": nome, "schema": 1}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return caminho


def resumo(base_dir=None) -> str:
    return "Edição Pública" if e_publico(base_dir) else "Edição Admin (dono)"
