"""
Zenith — CADERNOS DE ESTUDO (v1.7, tarefa T6).

A `zenith_biblioteca.py` guarda os documentos e busca trechos com BM25. O que faltava era
organizar o estudo: **cadernos por assunto**, cada um com as suas fontes, respostas que citam
arquivo e página, e o **Modo Professora** (explica passo a passo e faz uma pergunta).

  /cadernos                       lista os cadernos e as fontes
  /cadernos novo <assunto>         cria (ex.: /cadernos novo Leis de Newton)
  /cadernos add <arquivo|pasta>    guarda o material DENTRO do caderno ativo
  /cadernos usar <assunto>         escolhe o caderno ativo
  /cadernos perguntar <pergunta>    responde citando [arquivo, p. N]
  /cadernos professora <tema>       modo professora
  /cadernos apagar <assunto>        apaga o caderno (os arquivos originais NÃO são tocados)

Nada sai do computador: a busca é local (BM25, sem embeddings), o índice fica em
`config/biblioteca/` e os cadernos em `config/cadernos.json`. A resposta "de verdade" é
escrita pela IA com o contexto de `contexto_para_ia()` — que já vem embrulhado como conteúdo
externo em quarentena, com a ordem de citar a fonte.

Mensagens para o Corpo (tela "Cadernos"): `{"action": "cadernos_data", "cadernos": [...],
"ativo": "..."}`
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from brain import zenith_biblioteca as bib_mod

ACAO_TELA = "cadernos_data"
MAX_CADERNOS = 60
MAX_FONTES = 80


class ErroCaderno(Exception):
    """Mensagem já em português, pronta pro chat."""


def _pasta_padrao() -> Path:
    from brain.zenith_settings import CONFIG_DIR
    return Path(CONFIG_DIR)


class Cadernos:
    """Cadernos por assunto em cima da biblioteca única (o mesmo índice, sem cópia)."""

    def __init__(self, pasta=None, biblioteca=None):
        self.pasta = Path(pasta) if pasta else _pasta_padrao()
        self.arquivo = self.pasta / "cadernos.json"
        self.bib = biblioteca or bib_mod.padrao()
        self._dados = None

    # ---------------------------------------------------------------- persistência
    def _carregar(self) -> dict:
        if self._dados is None:
            try:
                self._dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._dados = {"cadernos": [], "ativo": ""}
            self._dados.setdefault("cadernos", [])
            self._dados.setdefault("ativo", "")
        return self._dados

    def _salvar(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._dados, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.arquivo)

    # ---------------------------------------------------------------- cadernos
    def listar(self) -> list:
        return sorted(self._carregar()["cadernos"], key=lambda c: c["nome"].lower())

    def achar(self, nome: str):
        q = str(nome or "").strip().lower()
        if not q:
            q = str(self._carregar().get("ativo") or "").lower()
            if not q:
                return None
        for c in self.listar():
            if c["nome"].lower() == q:
                return c
        for c in self.listar():
            if q in c["nome"].lower():
                return c
        return None

    def ativo(self):
        return self.achar("")

    def criar(self, nome: str, assunto: str = "") -> dict:
        nome = " ".join(str(nome or "").split())[:60]
        if not nome:
            raise ErroCaderno("Qual o nome do caderno? Ex.: /cadernos novo Leis de Newton")
        dados = self._carregar()
        if self.achar(nome) and any(c["nome"].lower() == nome.lower() for c in dados["cadernos"]):
            raise ErroCaderno(f"Já existe um caderno chamado '{nome}'.")
        if len(dados["cadernos"]) >= MAX_CADERNOS:
            raise ErroCaderno(f"Você já tem {MAX_CADERNOS} cadernos — apague algum com /cadernos apagar <nome>.")
        c = {"nome": nome, "assunto": " ".join(str(assunto or "").split())[:200], "fontes": [],
             "criado": time.strftime("%Y-%m-%d %H:%M")}
        dados["cadernos"].append(c)
        dados["ativo"] = nome
        self._salvar()
        return c

    def apagar(self, nome: str) -> bool:
        c = self.achar(nome)
        if not c or c["nome"].lower() != str(nome or "").strip().lower():
            return False
        dados = self._carregar()
        dados["cadernos"] = [x for x in dados["cadernos"] if x["nome"] != c["nome"]]
        if dados.get("ativo") == c["nome"]:
            dados["ativo"] = dados["cadernos"][0]["nome"] if dados["cadernos"] else ""
        self._salvar()
        return True

    def usar(self, nome: str) -> dict:
        c = self.achar(nome)
        if not c:
            raise ErroCaderno(f"Não achei o caderno '{nome}'. Veja /cadernos.")
        self._carregar()["ativo"] = c["nome"]
        self._salvar()
        return c

    # ---------------------------------------------------------------- fontes
    def adicionar(self, nome: str, caminho: str, progresso=None) -> dict:
        """Guarda o arquivo/pasta na biblioteca E registra a fonte no caderno."""
        c = self.usar(nome) if nome else self.ativo()
        if not c:
            raise ErroCaderno("Crie primeiro um caderno: /cadernos novo <assunto>")
        res = self.bib.adicionar(caminho, progresso=progresso)
        nomes = [d["nome"] for d in res["adicionados"] + res["repetidos"]]
        atuais = {f["arquivo"] for f in c["fontes"]}
        for n in nomes:
            if n not in atuais and len(c["fontes"]) < MAX_FONTES:
                doc = next((d for d in self.bib.documentos() if d["nome"] == n), {})
                c["fontes"].append({"arquivo": n, "paginas": doc.get("paginas", 0),
                                    "adicionado": time.strftime("%Y-%m-%d")})
                atuais.add(n)
        self._salvar()
        return {**res, "caderno": c["nome"], "fontes": [f["arquivo"] for f in c["fontes"]]}

    def remover_fonte(self, nome: str, arquivo: str) -> bool:
        c = self.achar(nome)
        if not c:
            return False
        antes = len(c["fontes"])
        c["fontes"] = [f for f in c["fontes"] if f["arquivo"].lower() != str(arquivo).lower()]
        self._salvar()
        return len(c["fontes"]) < antes

    # ---------------------------------------------------------------- busca
    def buscar(self, nome: str, pergunta: str, k: int = 5) -> list:
        c = self.achar(nome)
        if not c:
            raise ErroCaderno("Nenhum caderno ativo. Crie um com /cadernos novo <assunto>.")
        permitidos = {f["arquivo"] for f in c["fontes"]}
        achados = self.bib.buscar(pergunta, k=max(k * 3, k))
        return [r for r in achados if r["arquivo"] in permitidos][:k]

    def responder(self, nome: str, pergunta: str, k: int = 3) -> dict:
        """Resposta CURTA com as citações (sem IA): os trechos e de onde vieram."""
        achados = self.buscar(nome, pergunta, k)
        fontes = [{"arquivo": r["arquivo"], "pagina": r["pagina"], "trecho": " ".join(r["texto"].split())[:400]}
                  for r in achados]
        if not fontes:
            return {"texto": "Não achei nada sobre isso neste caderno. Confira se o material foi adicionado "
                             "com /cadernos add <arquivo> (ou pergunte de outro jeito).",
                    "fontes": []}
        linhas = [f"Encontrei {len(fontes)} trecho(s) no caderno:"]
        for f in fontes:
            linhas.append(f"• [{f['arquivo']}, p. {f['pagina']}] {f['trecho']}")
        linhas.append("Se quiser a explicação completa, peça: /cadernos professora <tema>.")
        return {"texto": "\n".join(linhas), "fontes": fontes}

    def contexto_para_ia(self, nome: str, pergunta: str, k: int = 3, usuario: str = "o usuário") -> str:
        """Trechos do caderno embrulhados como conteúdo externo — a IA responde citando [arquivo, p. N]."""
        from brain import zenith_quarentena as quarentena
        achados = self.buscar(nome, pergunta, k)
        if not achados:
            return ""
        corpo = "\n\n".join(f"[{r['arquivo']}, p. {r['pagina']}]\n{r['texto']}" for r in achados)
        return (quarentena.envolver(corpo, "caderno de estudos do usuário", usuario) +
                "\nUse os trechos acima para responder e CITE a fonte no formato [arquivo, p. N]. "
                "Se não bastarem, diga o que falta em vez de inventar.")

    # ---------------------------------------------------------------- Modo Professora
    def professora(self, nome: str, tema: str) -> dict:
        """Plano de estudo passo a passo + uma pergunta de compreensão, tudo ancorado nas fontes."""
        achados = self.buscar(nome, tema, 3)
        if not achados:
            return {"tema": tema, "passos": [], "pergunta": "", "fontes": [],
                    "texto": "Não achei o tema neste caderno. Adicione o material (/cadernos add) ou mude o tema."}
        principal = achados[0]
        trecho = " ".join(principal["texto"].split())
        frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", trecho) if len(f.strip()) > 25][:4]
        passos = [
            f"1. Comece pela ideia central: {trecho[:240]}{'…' if len(trecho) > 240 else ''}",
            f"2. Entenda o porquê: {frases[0] if frases else '…'}",
            f"3. Veja como se aplica: {frases[1] if len(frases) > 1 else 'procure um exemplo no material.'}",
            f"4. Confira você mesmo: {frases[2] if len(frases) > 2 else 'refaça um exercício do material.'}",
        ]
        pergunta = (f"Com as suas palavras: por que {tema.strip()} funciona assim? "
                    f"(Responda em 2 frases; eu confiro com o material e digo o que faltou.)")
        fontes = [{"arquivo": r["arquivo"], "pagina": r["pagina"]} for r in achados]
        return {"tema": tema, "passos": passos, "pergunta": pergunta, "fontes": fontes,
                "texto": "Modo Professora — " + tema + "\n" + "\n".join(passos) + "\n\n" + pergunta}

    # ---------------------------------------------------------------- tela
    def estado_para_tela(self) -> dict:
        ativo = self.ativo()
        return {"action": ACAO_TELA, "ativo": ativo["nome"] if ativo else "",
                "cadernos": [{"nome": c["nome"], "assunto": c["assunto"], "fontes": len(c["fontes"]),
                              "arquivos": [f["arquivo"] for f in c["fontes"][:12]]} for c in self.listar()]}


def formatar_lista(cad: Cadernos) -> str:
    itens = cad.listar()
    if not itens:
        return ("📓 Nenhum caderno ainda.\nCrie um com: /cadernos novo Leis de Newton\n"
                "Depois guarde o material: /cadernos add <arquivo ou pasta>")
    ativo = cad.ativo()
    linhas = [f"📓 Cadernos ({len(itens)})" + (f" — ativo: {ativo['nome']}" if ativo else "")]
    for c in itens:
        linhas.append(f"• {c['nome']} — {len(c['fontes'])} fonte(s)" + (f" · {c['assunto']}" if c["assunto"] else ""))
    linhas.append("Usar: /cadernos usar <nome> · Perguntar: /cadernos perguntar <pergunta> · "
                  "Professora: /cadernos professora <tema>")
    return "\n".join(linhas)


_PADRAO = None


def padrao() -> Cadernos:
    global _PADRAO
    if _PADRAO is None:
        _PADRAO = Cadernos()
    return _PADRAO
