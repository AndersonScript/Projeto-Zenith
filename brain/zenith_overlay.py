"""Zenith — ajustes de código aprovados (camada de cima) e inicialização segura (v1.6.2).

Por que existe: o Zenith não pode trocar o arquivo de um programa que está EXECUTANDO (e, no .exe fechado, nem existe
arquivo .py para trocar). Então um ajuste aprovado pelo usuário NÃO mexe nos arquivos instalados: ele vira uma cópia na
pasta `config/ajustes/overlay/`, e no PRÓXIMO início o Zenith carrega essa cópia no lugar do original. Desfazer = apagar a
cópia. Uma atualização do Zenith (Launcher) troca os originais e não perde nem quebra os ajustes (o hash é conferido).

Garantias deste módulo (só biblioteca padrão; roda ANTES de qualquer outro módulo do Zenith):
  * só carrega arquivo `zenith_*.py` que está no manifesto, com o SHA-256 igual ao aprovado (cópia alterada = ignorada);
  * NUNCA substitui um módulo PROTEGIDO (aprovação, executor, segredos, configurações, atualização, o próprio mecanismo...)
    mesmo que alguém escreva isso no manifesto;
  * modo seguro: se o Zenith não chegou a ficar de pé em 2 inícios seguidos com ajustes ativos, os ajustes vão para a
    quarentena e o Zenith abre limpo (a pasta `quarentena/` guarda o que foi tirado, para você ver).
"""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

PACOTE = "brain"
NOME_VALIDO = re.compile(r"^zenith_[a-z0-9_]+\.py$")
LIMITE_TENTATIVAS = 2

# Nenhum ajuste (nem de dentro, nem escrito à mão no manifesto) pode substituir estes módulos.
PROTEGIDOS = frozenset({
    # aprovação e execução (Pilar 1) e segurança de conteúdo
    "zenith_gatekeeper.py", "zenith_executor.py", "zenith_validator.py", "zenith_content_safety.py",
    "zenith_quarentena.py", "zenith_actionlog.py", "zenith_parar.py", "zenith_pausa.py",
    # segredos, configurações, edição, versão e atualização
    "zenith_segredos.py", "zenith_settings.py", "zenith_chaves.py", "zenith_contas.py", "zenith_admin.py",
    "zenith_edicao.py", "zenith_version.py", "zenith_atualizar.py", "zenith_bootstrap.py", "zenith_reset.py",
    "zenith_export.py",
    # ligações do Cérebro com o resto (aqui moram as regras e os pilares)
    "zenith_core.py", "zenith_headless.py", "zenith_commands.py", "zenith_bridge.py", "zenith_tags.py",
    "zenith_main.py", "zenith_body_control.py", "zenith_comandos_proprios.py",
    # este mecanismo
    "zenith_overlay.py", "zenith_autoajuste.py",
})


def sha256_arquivo(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


# ------------------------------------------------------------------ manifesto
def _json(caminho: Path, padrao):
    try:
        v = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return v if isinstance(v, type(padrao)) else padrao
    except Exception:
        return padrao


def _gravar_json(caminho: Path, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


def ler_manifesto(pasta) -> dict:
    m = _json(Path(pasta) / "manifesto.json", {})
    m.setdefault("arquivos", {})          # {"zenith_x.py": {"sha256":..., "id":..., "quando":...}}
    m.setdefault("pilhas", {})            # {"zenith_x.py": [id, id, ...]} (o último é o que vale)
    m.setdefault("historico", [])
    return m


def gravar_manifesto(pasta, m: dict):
    _gravar_json(Path(pasta) / "manifesto.json", m)


def pasta_overlay(pasta) -> Path:
    return Path(pasta) / "overlay"


# ------------------------------------------------------------------ o carregador
class BuscadorOverlay(importlib.abc.MetaPathFinder):
    """Colocado no INÍCIO de sys.meta_path: `brain.zenith_x` sai da cópia aprovada, se existir."""

    def __init__(self, pacote: str, mapa: dict):
        self.pacote, self.mapa = pacote, dict(mapa)       # {"zenith_x": Path}

    def find_spec(self, fullname, path=None, target=None):
        partes = fullname.split(".")
        if len(partes) != 2 or partes[0] != self.pacote:
            return None
        arq = self.mapa.get(partes[1])
        if not arq:
            return None
        return importlib.util.spec_from_file_location(fullname, str(arq))


def desinstalar():
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, BuscadorOverlay)]


def instalar(pasta, pacote: str = PACOTE) -> dict:
    """Liga os ajustes aprovados. Devolve {'ativos': [...], 'ignorados': [(nome, motivo)], 'ja_importados': [...]}."""
    desinstalar()
    m = ler_manifesto(pasta)
    ativos, ignorados, mapa = [], [], {}
    for nome, info in sorted(m["arquivos"].items()):
        arq = pasta_overlay(pasta) / nome
        if not NOME_VALIDO.match(nome):
            ignorados.append((nome, "nome inválido"))
        elif nome in PROTEGIDOS:
            ignorados.append((nome, "módulo protegido"))
        elif not arq.is_file():
            ignorados.append((nome, "arquivo sumiu"))
        elif sha256_arquivo(arq) != str((info or {}).get("sha256", "")).lower():
            ignorados.append((nome, "o arquivo não é o que foi aprovado (hash diferente)"))
        else:
            ativos.append(nome)
            mapa[nome[:-3]] = arq
    ja = [f"{pacote}.{n[:-3]}" for n in ativos if f"{pacote}.{n[:-3]}" in sys.modules]
    if mapa:
        sys.meta_path.insert(0, BuscadorOverlay(pacote, mapa))
    return {"ativos": ativos, "ignorados": ignorados, "ja_importados": ja}


# ------------------------------------------------------------------ início seguro
def _boot(pasta) -> dict:
    return _json(Path(pasta) / "boot.json", {})


def quarentenar(pasta, motivo: str) -> str:
    """Tira todos os ajustes de circulação (move para quarentena/<data>/). Devolve a pasta da quarentena."""
    pasta = Path(pasta)
    destino = pasta / "quarentena" / time.strftime("%Y%m%d_%H%M%S")
    destino.mkdir(parents=True, exist_ok=True)
    ov = pasta_overlay(pasta)
    if ov.exists():
        shutil.move(str(ov), str(destino / "overlay"))
    m = ler_manifesto(pasta)
    (destino / "motivo.txt").write_text(motivo, encoding="utf-8")
    (destino / "manifesto.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    m["historico"].append({"quando": time.strftime("%Y-%m-%d %H:%M"), "evento": "quarentena", "motivo": motivo})
    m["arquivos"], m["pilhas"] = {}, {}
    gravar_manifesto(pasta, m)
    return str(destino)


def iniciar_boot(pasta) -> dict:
    """Chame ANTES de instalar(). Conta uma tentativa de início; se já falharam duas seguidas com ajustes ativos,
    manda os ajustes para a quarentena. -> {'modo_seguro': bool, 'motivo': str}"""
    pasta = Path(pasta)
    estado = _boot(pasta)
    tentativas = int(estado.get("tentativas", 0) or 0)
    ativos = len(ler_manifesto(pasta)["arquivos"])
    if ativos and tentativas >= LIMITE_TENTATIVAS:
        motivo = f"O Zenith não chegou a abrir em {tentativas} inícios seguidos com {ativos} ajuste(s) ativo(s)."
        quarentenar(pasta, motivo)
        _gravar_json(pasta / "boot.json", {"tentativas": 0})
        return {"modo_seguro": True, "motivo": motivo}
    _gravar_json(pasta / "boot.json", {"tentativas": tentativas + 1, "quando": time.strftime("%Y-%m-%d %H:%M:%S")})
    return {"modo_seguro": False, "motivo": ""}


def boot_ok(pasta):
    """O Zenith ficou de pé: zera a contagem."""
    _gravar_json(Path(pasta) / "boot.json", {"tentativas": 0, "ok_em": time.strftime("%Y-%m-%d %H:%M:%S")})
