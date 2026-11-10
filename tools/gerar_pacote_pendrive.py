"""
Monta o pacote do pendrive a partir do COMPUTADOR (C:\\Zenith) — 31/10/2026.

Uso:
    py -3 tools/gerar_pacote_pendrive.py

O que ele faz
-------------
Pega o projeto como está no computador e cria UM zip único:

    Zenith_PENDRIVE_1.0.zip
      LEIA-ME_PRIMEIRO.txt
      COPIAR_PARA_PENDRIVE.bat
      ZenithLauncher.exe        (o de hoje, com o certificado dentro)
      LimparZenith.exe          (apagar por partes / desinstalar)
      Zenith_app_1.0.zip        (o pacote público de 76 MB)
      Zenith/...                (o projeto inteiro: código, Corpo exportado,
                                 dist/Zenith já montado, firmware, docs)

O que ele NÃO leva (de propósito)
---------------------------------
    chaves de API, conversas, notas, lembretes, log de ações, memória de longo
    prazo, criações, temporários, habilidades criadas, ZENITH.md, instalação.
    Também pula lixo: __pycache__, *.pyc, arquivos .bak*, pasta de resgate do
    build, build/ do PyInstaller e dist_publico/ (artefato de outra edição).

Por que zip único: o hash de UM arquivo prova a cópia inteira. O pendrive deste
PC já corrompeu arquivos avulsos (blocos virando zero, arquivo truncado) — com
um zip só, o COPIAR_PARA_PENDRIVE.bat consegue provar se a cópia está íntegra.

Sem compressão (ZIP_STORED): o conteúdo é quase todo binário já comprimido
(.exe, .bin, .vrm, .pyd), então deflate gastaria minutos para economizar pouco.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]             # tools/ -> Zenith/ -> C:\Zenith
PROJETO = RAIZ / "Zenith"
ENTREGA = RAIZ / "_PARA_O_GITHUB"
SAIDA = RAIZ / "Zenith_PENDRIVE_1.0.zip"

# pastas que nunca entram (lixo de build / artefatos de outra edição)
PASTAS_FORA = {
    "__pycache__", ".git", ".idea", ".vscode",
    "dist_publico",          # edição pública separada, não é o app do dia a dia
    "build", "_build",       # sobras do PyInstaller
    "_dados_do_usuario_resgatados",   # resgate do build (dados do dono)
}

# pastas de DADOS DO USUÁRIO — fora do pacote, em qualquer nível
PASTAS_PESSOAIS = {"memory_db", "temp", "creations", "skills", "models_cache"}

# arquivos pessoais (nome exato ou prefixo), em qualquer nível
ARQUIVOS_PESSOAIS = {
    "conversations.json", "settings.json", "instalacao.json",
    "zenith_notas.jsonl", "zenith_lembretes.json", "ZENITH.md",
    "biblia_extra.md", "biblia.md", ".reset_pendente",
    "zenith_voz_debug.log", "zenith_log.txt",
}
PREFIXOS_PESSOAIS = ("zenith_acoes_log", "conversations.")
# qualquer coisa com .bak no meio do nome: zenith_commands.py.bak_wifi, etc.
SUFIXOS_LIXO = (".bak", ".bak_wifi", ".orig", ".old", "~")


def _pular(caminho: Path) -> bool:
    nome = caminho.name
    if nome in PASTAS_FORA or nome in PASTAS_PESSOAIS:
        return True
    # Zenith/models é a MESMA pasta que dist/Zenith/models (464 MB cada): o app
    # que roda é o de dist/, então a cópia da raiz não vai — só pesaria no
    # pendrive. Sem ela, quem rodar a partir do CÓDIGO baixa o modelo de novo.
    if nome == "models" and caminho.parent == PROJETO:
        return True
    if nome.endswith(".pyc"):
        return True
    if nome in ARQUIVOS_PESSOAIS:
        return True
    # settings.json e QUALQUER backup dele (settings.json.antes_do_ajuste_mic,
    # settings.json.bak...) — todos carregam chave de API de quem configurou.
    if "settings.json" in nome:
        return True
    if any(nome.startswith(p) for p in PREFIXOS_PESSOAIS):
        return True
    if any(nome.endswith(s) for s in SUFIXOS_LIXO) or ".bak." in nome or ".bak_" in nome:
        return True
    return False


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _conferir_exes() -> list[Path]:
    """Os três arquivos de entrega precisam bater com o que o site publica."""
    manifesto = json.loads((PROJETO / "site" / "latest.json").read_text(encoding="utf-8"))
    esperado = {
        "ZenithLauncher.exe": manifesto["launcher"],
        "LimparZenith.exe": manifesto["limpar"],
        "Zenith_app_1.0.zip": manifesto["pacote"],
    }
    faltando = []
    for nome, info in esperado.items():
        p = ENTREGA / nome
        if not p.is_file():
            print(f"  [X] falta {nome} em {ENTREGA}")
            faltando.append(p)
            continue
        tam = p.stat().st_size
        if tam != info["tamanho"]:
            print(f"  [!] {nome}: tamanho {tam:,} != {info['tamanho']:,} do latest.json")
        h = _sha256(p)
        marca = "ok" if h == info["sha256"] else "DIFERENTE do latest.json"
        print(f"  {nome:22} {tam:12,}  {h[:16]}  {marca}")
    return faltando


def main() -> int:
    if not PROJETO.is_dir():
        print(f"[X] Não achei o projeto em {PROJETO}")
        return 1

    print("=== Conferindo os arquivos de entrega")
    faltando = _conferir_exes()

    print("\n=== Montando o zip (pode levar alguns minutos)")
    total = 0
    arquivos = 0
    with zipfile.ZipFile(SAIDA, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        # 1) arquivos soltos na raiz de C:\Zenith
        for nome in ("LEIA-ME_PRIMEIRO.txt", "COPIAR_PARA_PENDRIVE.bat"):
            p = RAIZ / nome
            if p.is_file():
                z.write(p, nome)
                total += p.stat().st_size
                arquivos += 1
                print(f"  + {nome}")

        # 2) os três de entrega (Launcher, Limpar, pacote público)
        for nome in ("ZenithLauncher.exe", "LimparZenith.exe", "Zenith_app_1.0.zip"):
            p = ENTREGA / nome
            if p.is_file():
                z.write(p, nome)
                total += p.stat().st_size
                arquivos += 1
                print(f"  + {nome}  ({p.stat().st_size:,} bytes)")

        # 3) o projeto inteiro, sem dados pessoais e sem lixo
        for raiz, pastas, nomes in os.walk(PROJETO):
            raiz_p = Path(raiz)
            pastas[:] = [d for d in pastas if not _pular(raiz_p / d)]
            for n in nomes:
                p = raiz_p / n
                if _pular(p):
                    continue
                try:
                    z.write(p, str(p.relative_to(RAIZ)))
                    total += p.stat().st_size
                    arquivos += 1
                except OSError as e:
                    print(f"  [!] não consegui incluir {p}: {e}")

    tam = SAIDA.stat().st_size
    h = _sha256(SAIDA)
    print("\n=== Pronto")
    print(f"  arquivo : {SAIDA}")
    print(f"  itens   : {arquivos}")
    print(f"  tamanho : {tam:,} bytes ({tam/1e9:.2f} GB)  [soma dos itens: {total/1e9:.2f} GB]")
    print(f"  SHA-256 : {h}")
    (SAIDA.with_suffix(".zip.sha256")).write_text(f"{h}  {SAIDA.name}\n", encoding="utf-8")
    if faltando:
        print("\n[!] Faltou arquivo de entrega — o zip saiu incompleto de propósito? Confira acima.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
