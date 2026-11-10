"""Zenith — atualização com segurança (v1.5, tarefa T9).

Regra do projeto: **nunca silencioso, nunca automático**. Este módulo só faz o trabalho chato e
verificável; quem decide é o usuário, digitando:

    /atualizar                 -> consulta o versions.json, mostra a versão nova e as notas
    /atualizar baixar          -> baixa para a pasta temporária e CONFERE o SHA-256
    /atualizar instalar        -> abre o instalador (só depois de você pedir)

O que ele garante:
  - só fala com o endereço que está em `atualizar_url` nas Configurações (HTTPS por padrão);
  - recusa arquivo maior que `LIMITE_BYTES` (não enche o disco);
  - **confere o SHA-256** antes de qualquer coisa ser aberta; hash diferente = arquivo apagado;
  - não roda nada: `abrir_instalador()` só abre o que já foi baixado e conferido.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import tempfile
import urllib.request
from pathlib import Path

LIMITE_BYTES = 400 * 1024 * 1024          # 400 MB — um instalador do Zenith tem ~150 MB
TEMPO_LIMITE = 15
ARQUIVO_BAIXADO = "zenith_atualizacao"
SHA_VALIDO = re.compile("^[0-9a-f]{64}$")


def _contexto_ssl():
    """HTTPS confiando no Windows E no certifi (que vem junto com o Zenith).
    Sem isto, num Windows com raízes de certificado antigas o /atualizar morre em
    'CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate'."""
    try:
        ctx = ssl.create_default_context()
    except Exception:
        return None
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return ctx


def _obter_padrao(url: str, tempo: int = TEMPO_LIMITE) -> bytes:
    ctx = _contexto_ssl()
    abridor = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx)) if ctx else urllib.request.build_opener()
    abridor.addheaders = [("User-Agent", "Zenith/%s" % (globals().get("VERSAO", "1.0")))]
    with abridor.open(url, timeout=tempo) as resposta:      # noqa: S310 (só http(s) validado antes)
        return resposta.read(LIMITE_BYTES + 1)


def _url_ok(url: str) -> bool:
    u = str(url or "").strip()
    if not (u.startswith("https://") or u.startswith("http://localhost") or u.startswith("http://127.0.0.1")):
        return False
    return " " not in u


def consultar(url: str, obter=None, tempo: int = TEMPO_LIMITE) -> tuple:
    """Lê o `versions.json`. Devolve (info, erro). Nunca levanta, nunca instala nada."""
    if not _url_ok(url):
        return {}, "Endereço de atualização inválido (precisa ser https). Confira em Configurações."
    baixar = obter or _obter_padrao
    try:
        bruto = baixar(str(url), tempo)
    except Exception as e:
        return {}, f"Não consegui consultar o servidor de atualização: {e}"
    try:
        dados = json.loads(bruto.decode("utf-8") if isinstance(bruto, bytes) else str(bruto))
    except Exception as e:
        return {}, f"O servidor respondeu algo que não é o versions.json: {e}"
    if not isinstance(dados, dict) or not str(dados.get("versao") or "").strip():
        return {}, "O versions.json não diz qual é a versão."
    info = {
        "versao": str(dados.get("versao")).strip(),
        "notas": str(dados.get("notas") or "").strip()[:4000],
        "url": str(dados.get("url") or dados.get("arquivo") or "").strip(),
        "sha256": str(dados.get("sha256") or "").strip().lower(),
        "tamanho": int(dados.get("tamanho") or 0),
    }
    return info, ""


def ha_novidade(info: dict, versao_atual: str) -> bool:
    """True se a versão do servidor é maior que a que está rodando."""
    try:
        from brain.zenith_version import numero
    except Exception:
        return False
    try:
        return numero(info.get("versao", "")) > numero(versao_atual)
    except Exception:
        return False


def planejar(info: dict, versao_atual: str) -> dict:
    """Diz o que aconteceria, sem fazer nada. `ok=False` + `motivo` quando não dá para seguir."""
    if not info:
        return {"ok": False, "motivo": "sem informação de versão"}
    if not ha_novidade(info, versao_atual):
        return {"ok": True, "ha_novidade": False, "versao": info.get("versao", ""),
                "motivo": f"Você já está na versão mais nova ({versao_atual})."}
    if not _url_ok(info.get("url", "")):
        return {"ok": False, "motivo": "O versions.json não traz um endereço https válido do instalador."}
    if not SHA_VALIDO.match(str(info.get("sha256", ""))):
        return {"ok": False, "motivo": "O versions.json não traz o SHA-256 do arquivo — sem ele eu não baixo."}
    if info.get("tamanho", 0) and int(info["tamanho"]) > LIMITE_BYTES:
        return {"ok": False, "motivo": "O arquivo é maior do que o limite de segurança (400 MB)."}
    return {"ok": True, "ha_novidade": True, "versao": info["versao"], "url": info["url"],
            "sha256": info["sha256"], "notas": info.get("notas", ""), "tamanho": info.get("tamanho", 0)}


def baixar(plano: dict, obter=None, pasta=None, progresso=None) -> tuple:
    """Baixa e confere o SHA-256. Devolve (caminho, erro). Hash errado => arquivo apagado."""
    if not plano or not plano.get("ok") or not plano.get("ha_novidade"):
        return "", plano.get("motivo", "nada para baixar") if plano else "nada para baixar"
    baixar_url = obter or _obter_padrao
    try:
        dados = baixar_url(plano["url"], TEMPO_LIMITE)
    except Exception as e:
        return "", f"Falha ao baixar: {e}"
    dados = bytes(dados or b"")
    if not dados:
        return "", "O servidor mandou um arquivo vazio."
    if len(dados) > LIMITE_BYTES:
        return "", "O arquivo passou do limite de segurança — baixei e descartei."
    if progresso:
        try:
            progresso(1.0)
        except Exception:
            pass
    achado = hashlib.sha256(dados).hexdigest()
    if achado != plano["sha256"]:
        return "", ("O SHA-256 não confere — o arquivo pode ter sido trocado no caminho. "
                    "Não abri nada e descartei o download.")
    destino = Path(pasta or tempfile.gettempdir()) / f"{ARQUIVO_BAIXADO}_{plano['versao']}.exe"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
    except OSError as e:
        return "", f"Baixou e conferiu, mas não consegui salvar: {e}"
    return str(destino), ""


def abrir_instalador(caminho: str, aprovado: bool = False, abrir=None) -> tuple:
    """Abre o instalador — só com `aprovado=True` e só um .exe que existe."""
    if not aprovado:
        return False, ("Baixei e conferi, mas NÃO abri nada. Confira as notas e, se quiser instalar, "
                       "use /atualizar instalar.")
    p = Path(str(caminho or ""))
    if not p.is_file():
        return False, "O instalador não está mais na pasta temporária — use /atualizar baixar de novo."
    if p.suffix.lower() != ".exe":
        return False, "O arquivo baixado não é um instalador .exe — não vou abrir."
    try:
        if abrir is not None:
            abrir(str(p))
        else:
            import os
            os.startfile(str(p))          # noqa: S606 (decisão explícita do usuário)
    except Exception as e:
        return False, f"Não consegui abrir o instalador: {e}"
    return True, f"Abrindo o instalador: {p.name}. Feche o Zenith antes de continuar."


def abrir_launcher(caminho: str, pid: int, aprovado: bool = False, popen=None) -> tuple:
    """v1.6.2 — quem instalou o Zenith pelo Launcher atualiza POR ELE (ele baixa, confere o SHA-256, troca a pasta guardando a
    anterior e mantém seus dados). Aqui só o ABRIMOS, com `--atualizar --esperar-pid`: ele espera este Zenith fechar.
    Só com `aprovado=True` (o usuário digitou /atualizar) e só um .exe que existe."""
    if not aprovado:
        return False, "Não abri o Launcher: falta o seu pedido (/atualizar instalar)."
    p = Path(str(caminho or ""))
    if not p.is_absolute() or not p.is_file() or p.suffix.lower() != ".exe":
        return False, "Não achei o Launcher do Zenith neste computador. Abra o Zenith pelo atalho do Launcher e tente de novo."
    try:
        import subprocess
        (popen or subprocess.Popen)([str(p), "--atualizar", "--esperar-pid", str(int(pid))], close_fds=True,
                                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except Exception as e:
        return False, f"Não consegui abrir o Launcher: {e}"
    return True, ("Abri o Launcher. Feche o Zenith agora (pelo X da janela ou pela bandeja): ele espera fechar, baixa a versão nova, "
                  "confere o SHA-256, guarda a versão atual (dá para voltar) e abre o Zenith de novo. Suas configurações e chaves ficam.")


def formatar(info: dict, plano: dict, versao_atual: str) -> str:
    """Texto para o chat (sem emoji, sem promessa do que não foi feito)."""
    if not plano.get("ok"):
        return "Não vou atualizar: " + str(plano.get("motivo") or "motivo desconhecido")
    if not plano.get("ha_novidade"):
        return f"Você já está na versão mais nova ({versao_atual})."
    linhas = [f"Versão nova disponível: {plano['versao']} (você tem {versao_atual})."]
    if plano.get("notas"):
        linhas.append("O que mudou:")
        linhas.append(plano["notas"])
    if plano.get("tamanho"):
        linhas.append(f"Tamanho: {int(plano['tamanho']) / 1e6:.1f} MB")
    linhas.append(f"SHA-256: {plano['sha256'][:16]}… (conferido depois do download)")
    linhas.append("Nada foi baixado nem instalado. Para baixar e conferir: /atualizar baixar")
    return "\n".join(linhas)
