"""
Zenith — OUTRAS LINGUAGENS e `pip` GUIADO (v1.7, tarefa T5).

Até a v1.6 o Zenith sabia criar programas em várias linguagens, mas só sabia RODAR Python
e páginas web. Este módulo fecha a outra metade:

  * descobre qual compilador/interpretador existe no PC (gcc, g++, javac/java, node, rustc, go,
    arduino-cli, dotnet, lua, php, ruby, dart, octave…) SEM instalar nada;
  * monta o PLANO de compilar/rodar (lista de comandos) — quem executa é o executor de sempre,
    com a aprovação do usuário (Pilar 1). Nada aqui roda comando, abre rede ou mexe em arquivo;
  * quando falta a ferramenta, explica como instalar em uma frase (winget/apt/site oficial);
  * `pip` guiado: mostra pacote, versão, licença e resumo ANTES, e só devolve o comando —
    a instalação é uma ação aprovada como qualquer outra.

Nada é instalado por este módulo. A mensagem ao usuário sempre diz o que vai rodar.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

# Cada linguagem: as ferramentas que precisam existir, como compilar/rodar e como instalar.
LINGUAGENS = {
    "python": {"nome": "Python", "ferramentas": [], "como": "já vem com o Zenith"},
    "c": {"nome": "C", "ferramentas": ["gcc"],
          "como": "instale o MSYS2/MinGW (winget install MSYS2.MSYS2) ou o Visual Studio Build Tools"},
    "cpp": {"nome": "C++", "ferramentas": ["g++"],
            "como": "instale o MSYS2/MinGW (winget install MSYS2.MSYS2)"},
    "java": {"nome": "Java", "ferramentas": ["javac", "java"],
             "como": "instale o JDK (winget install EclipseAdoptium.Temurin.21.JDK)"},
    "javascript": {"nome": "JavaScript", "ferramentas": ["node"],
                   "como": "instale o Node.js (winget install OpenJS.NodeJS.LTS)"},
    "typescript": {"nome": "TypeScript", "ferramentas": ["node", "npx"],
                   "como": "instale o Node.js e rode: npm install -g typescript"},
    "rust": {"nome": "Rust", "ferramentas": ["rustc"],
             "como": "instale o Rust (winget install Rustlang.Rustup)"},
    "go": {"nome": "Go", "ferramentas": ["go"],
           "como": "instale o Go (winget install GoLang.Go)"},
    "csharp": {"nome": "C#", "ferramentas": ["dotnet"],
               "como": "instale o .NET SDK (winget install Microsoft.DotNet.SDK.8)"},
    "arduino": {"nome": "Arduino", "ferramentas": ["arduino-cli"],
                "como": "instale o arduino-cli (winget install ArduinoSA.CLI) e a placa: arduino-cli core install arduino:avr"},
    "lua": {"nome": "Lua", "ferramentas": ["lua"], "como": "winget install DEVCOM.Lua"},
    "php": {"nome": "PHP", "ferramentas": ["php"], "como": "winget install PHP.PHP"},
    "ruby": {"nome": "Ruby", "ferramentas": ["ruby"], "como": "winget install RubyInstallerTeam.Ruby"},
    "dart": {"nome": "Dart", "ferramentas": ["dart"], "como": "winget install Google.DartSDK"},
    "octave": {"nome": "Octave", "ferramentas": ["octave"], "como": "winget install GNU.Octave"},
}

EXT_LINGUAGEM = {
    ".py": "python", ".pyw": "python", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".java": "java", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript", ".rs": "rust", ".go": "go",
    ".cs": "csharp", ".ino": "arduino", ".lua": "lua", ".php": "php", ".rb": "ruby", ".dart": "dart",
    ".m": "octave",
}

# O que "rodar" significa em cada uma (o principal vira o comando final).
_CMDS = {
    "c": lambda exe: ([["gcc", "{principal}", "-O2", "-o", "{exe}"]], [["{exe}"]]),
    "cpp": lambda exe: ([["g++", "{principal}", "-std=c++17", "-O2", "-o", "{exe}"]], [["{exe}"]]),
    "java": lambda exe: ([["javac", "{principal}"]], [["java", "-cp", ".", "{classe}"]]),
    "javascript": lambda exe: ([], [["node", "{principal}"]]),
    "typescript": lambda exe: ([], [["npx", "ts-node", "{principal}"]]),
    "rust": lambda exe: ([["rustc", "{principal}", "-O", "-o", "{exe}"]], [["{exe}"]]),
    "go": lambda exe: ([], [["go", "run", "{principal}"]]),
    "csharp": lambda exe: ([], [["dotnet", "run"]]),
    "arduino": lambda exe: ([["arduino-cli", "compile", "--fqbn", "{placa}", "{principal}"]], []),
    "lua": lambda exe: ([], [["lua", "{principal}"]]),
    "php": lambda exe: ([], [["php", "{principal}"]]),
    "ruby": lambda exe: ([], [["ruby", "{principal}"]]),
    "dart": lambda exe: ([], [["dart", "run", "{principal}"]]),
    "octave": lambda exe: ([], [["octave", "--no-gui", "--eval", "run('{principal}')"]]),
}


class ErroLinguagem(Exception):
    """Mensagem pronta pro chat."""


def linguagem_de(arquivo: str) -> str:
    return EXT_LINGUAGEM.get(Path(str(arquivo)).suffix.lower(), "")


def detectar(which=None) -> dict:
    """{linguagem: {nome, ok, ferramentas: {nome: caminho}, falta: [...], como}} — sem instalar nada."""
    which = which or shutil.which
    saida = {}
    for chave, info in LINGUAGENS.items():
        achadas, falta = {}, []
        for f in info["ferramentas"]:
            caminho = which(f)
            if caminho:
                achadas[f] = caminho
            else:
                falta.append(f)
        ok = not falta or chave == "python"
        saida[chave] = {"nome": info["nome"], "ok": ok, "ferramentas": achadas,
                        "falta": falta, "como": info["como"]}
    return saida


def plano_para(pasta, principal: str, placa: str = "arduino:avr:uno", det: dict = None) -> dict:
    """Monta o plano (comandos, em ordem) para compilar/rodar o arquivo principal.

    Devolve {"ok", "linguagem", "comandos": [[...], ...], "como_instalar", "explicacao"}.
    Não executa nada: cada comando passa pela aprovação normal.
    """
    p = Path(str(pasta))
    nome = str(principal or "").strip()
    ling = linguagem_de(nome)
    if not ling:
        raise ErroLinguagem(f"Não sei rodar '{Path(nome).suffix or nome}' ainda. Sei: "
                            + ", ".join(sorted({i['nome'] for i in LINGUAGENS.values()})) + ".")
    if ling == "python":
        return {"ok": True, "linguagem": "Python", "comandos": [[sys.executable or "python", nome]],
                "como_instalar": "", "explicacao": "Python roda direto."}
    info = LINGUAGENS[ling]
    det = det or detectar()
    estado = det.get(ling, {})
    if estado.get("falta"):
        return {"ok": False, "linguagem": info["nome"], "comandos": [], "como_instalar": info["como"],
                "explicacao": f"Para rodar {info['nome']} falta: {', '.join(estado['falta'])}. {info['como']}."}
    stem = Path(nome).stem
    exe = stem + (".exe" if sys.platform == "win32" else "")
    compilar, rodar = _CMDS.get(ling, (lambda _e: ([], [])))(exe)
    mapa = {"{principal}": nome, "{exe}": str(p / exe) if exe else "", "{classe}": stem, "{placa}": placa}
    def montar(cmds):
        return [[mapa.get(t, t) for t in c] for c in cmds]
    comandos = montar(compilar) + montar(rodar)
    if ling == "arduino":
        explicacao = ("Compilar para a placa (arduino-cli). Para GRAVAR na placa é outro comando, com a placa ligada na USB.")
    else:
        explicacao = f"{info['nome']}: {'compilar e depois rodar' if compilar else 'rodar direto'} (cada comando com a sua aprovação)."
    return {"ok": True, "linguagem": info["nome"], "comandos": comandos, "como_instalar": "", "explicacao": explicacao}


def formatar_plano(plano: dict) -> str:
    linhas = [f"🧰 {plano.get('linguagem', '?')} — {plano.get('explicacao', '')}"]
    if plano.get("comandos"):
        linhas.append("Comandos (cada um pede a sua aprovação):")
        for c in plano["comandos"]:
            linhas.append("  " + " ".join(str(x) for x in c))
    if plano.get("como_instalar") and not plano.get("ok"):
        linhas.append("Para instalar: " + plano["como_instalar"])
    return "\n".join(linhas)


# --------------------------------------------------------------------------------- pip guiado
def _http_json(url: str, timeout: float = 8.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:      # noqa: S310 — https fixo do PyPI
        return json.loads(r.read().decode("utf-8", "replace"))


def info_pacote(pacote: str, http=None) -> dict:
    """Consulta o PyPI (só leitura) e devolve nome, versão, licença e resumo. `http` é injetável no teste."""
    nome = str(pacote or "").strip()
    if not nome:
        raise ErroLinguagem("Qual pacote? Ex.: /instalar requests")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", nome):
        raise ErroLinguagem("Nome de pacote inválido (só letras, números, ponto, hífen e _).")
    http = http or _http_json
    dados = http(f"https://pypi.org/pypi/{nome}/json")
    info = (dados or {}).get("info") or {}
    licenca = str(info.get("license") or "").strip()
    if not licenca or len(licenca) > 40:
        for c in info.get("classifiers") or []:
            if str(c).startswith("License ::"):
                licenca = str(c).split("::")[-1].strip()
                break
    return {"nome": info.get("name") or nome, "versao": info.get("version") or "?",
            "licenca": licenca or "não informada", "resumo": (info.get("summary") or "")[:200],
            "requer": info.get("requires_python") or ""}


def formatar_pacote(i: dict) -> str:
    return (f"📦 {i['nome']} {i['versao']} — licença: {i['licenca']}\n{i['resumo']}\n"
            f"(Para instalar: /instalar {i['nome']} confirmar — vai pedir a sua aprovação e usar o pip do Python do Zenith.)")


def comando_pip(pacote: str, versao: str = "") -> list:
    nome = str(pacote or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", nome):
        raise ErroLinguagem("Nome de pacote inválido.")
    alvo = f"{nome}=={versao}" if versao else nome
    return [sys.executable or "python", "-m", "pip", "install", alvo]
