"""
Zenith — IA LOCAL (opcional, "Avançado"): o último recurso do Megazord (v30).

Pedido do Anderson: poder rodar um modelo no próprio PC, aceitando que "põe o computador
em risco/pesado", baixando o modelo sozinho e SOMANDO ao conjunto — não substituindo as
nuvens. O PC dele é um Ryzen sem placa de vídeo: um modelo pequeno roda a 100% de CPU e
demora dezenas de segundos por resposta. Isso é dito na cara, não escondido.

Como funciona (sem SDK nova — só HTTP local):
  * OLLAMA:      http://127.0.0.1:11434      (/api/tags lista, /api/pull baixa, /api/chat conversa)
  * LM STUDIO:   http://127.0.0.1:1234/v1    (compatível com OpenAI; o Zenith já sabe usar via "Minhas IAs")

Regras:
  * NADA é baixado sem o usuário mandar (/local baixar). `ia_local_baixar_sozinho` só vale
    se ele ligar isso de propósito.
  * Ligar a IA local NÃO troca a IA ativa: ela entra como RESERVA (depois das nuvens), a não
    ser que o usuário peça papel "principal".
  * Nenhum dado sai do PC quando quem responde é a local — e o aviso no chat diz isso.

Rede isolada em `_http_json` / `_http_linhas` para os testes injetarem um servidor de mentira.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

CANDIDATOS = (
    {"tipo": "ollama", "nome": "Ollama", "url": "http://127.0.0.1:11434", "tags": "/api/tags"},
    {"tipo": "lmstudio", "nome": "LM Studio", "url": "http://127.0.0.1:1234/v1", "tags": "/models"},
)

MSG_SEM_SERVIDOR_CELULAR = (
    "📱 A IA local ainda não está respondendo neste aparelho.\n"
    "Ela é opcional e não usa chave nenhuma — serve para o Zenith continuar respondendo sem internet.\n\n"
    "No celular ela é um módulo do próprio app: se ele estiver instalado e ligado, o Zenith o encontra sozinho. "
    "Se não estiver, o Zenith segue com as IAs da nuvem.\n\n"
    "Aviso honesto: um modelo pequeno no celular conversa, mas é lento e não programa bem. "
    "Por isso ela entra como RESERVA, não no lugar das nuvens."
)


def _no_celular() -> bool:
    try:
        from brain import zenith_plataforma
        return zenith_plataforma.detectar() == "android"
    except Exception:
        return False


def msg_sem_servidor() -> str:
    """A frase de "IA local não está respondendo" certa para onde o Zenith está (PC ou celular)."""
    return MSG_SEM_SERVIDOR_CELULAR if _no_celular() else MSG_SEM_SERVIDOR


def _endereco_do_aparelho() -> str:
    """(v1.19) A URL da IA que roda DENTRO do celular (servidor do app), ou "" se o aparelho não tem. Sempre termina em /v1."""
    try:
        from brain import zenith_plataforma
        if zenith_plataforma.detectar() != "android":
            return ""
        plat = zenith_plataforma.obter()
        if not plat.tem("llm_local"):
            return ""
        url = str(plat.endereco_llm_local() or "").strip().rstrip("/")
    except Exception:
        return ""
    if not url:
        return ""
    return url if url.endswith("/v1") else url + "/v1"


# Modelos pequenos que dão conta de conversa/português em CPU. O primeiro é o padrão.
RECOMENDADOS = (
    {"modelo": "qwen2.5:1.5b", "tamanho": "≈1 GB", "nota": "conversa e português razoáveis; ~10–25 s por resposta num Ryzen sem GPU"},
    {"modelo": "llama3.2:3b", "tamanho": "≈2 GB", "nota": "melhor qualidade, ~20–40 s por resposta"},
)
MODELO_PADRAO = RECOMENDADOS[0]["modelo"]

MSG_SEM_SERVIDOR = (
    "🖥 A IA local ainda não está respondendo neste PC.\n"
    "Ela é opcional e não usa chave nenhuma — serve para o Zenith continuar respondendo quando "
    "a internet ou a cota das nuvens acabam.\n\n"
    "O jeito mais simples (uma vez só):\n"
    "1. Instale o Ollama (site oficial: ollama.com) — é um programa normal, sem placa de vídeo também roda.\n"
    "2. Abra o Zenith de novo (ou rode /local ligar) e depois /local baixar.\n"
    "3. O modelo pequeno tem ≈1 GB e fica no seu PC; depois disso funciona sem internet.\n\n"
    "Aviso honesto: no seu Ryzen sem placa de vídeo a resposta local demora dezenas de segundos. "
    "Por isso ela entra como RESERVA, não no lugar do Gemini."
)


def _get(obj, chave, padrao=None):
    if obj is None:
        return padrao
    if hasattr(obj, "get"):
        try:
            v = obj.get(chave, padrao)
            return padrao if v is None else v
        except TypeError:
            pass
    if isinstance(obj, dict):
        v = obj.get(chave, padrao)
        return padrao if v is None else v
    return padrao


def _bool(obj, chave, padrao=False) -> bool:
    v = _get(obj, chave, padrao)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "sim", "yes", "on")


# ------------------------------------------------------------------ rede (isolada p/ teste)
def _http_json(url: str, timeout: float = 2.0, dados: dict = None, metodo: str = "GET"):
    corpo = json.dumps(dados).encode("utf-8") if dados is not None else None
    req = urllib.request.Request(url, data=corpo, method=metodo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        bruto = r.read().decode("utf-8", "replace")
    return json.loads(bruto) if bruto.strip() else {}


def _http_linhas(url: str, dados: dict, timeout: float = 30.0, ao_linha=None):
    """POST que devolve JSON por linha (o /api/pull do Ollama). Chama ao_linha(dict)."""
    corpo = json.dumps(dados).encode("utf-8")
    req = urllib.request.Request(url, data=corpo, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for linha in r:
            texto = linha.decode("utf-8", "replace").strip()
            if not texto:
                continue
            try:
                item = json.loads(texto)
            except ValueError:
                continue
            if ao_linha:
                ao_linha(item)
            if item.get("error"):
                raise RuntimeError(str(item["error"]))
    return True


# ------------------------------------------------------------------ detecção
def detectar(settings=None, timeout: float = 2.0, http=_http_json) -> dict:
    """Procura um servidor local. Devolve {rodando, tipo, nome, url, modelos, erro}."""
    url_escolhida = str(_get(settings, "ia_local_url", "") or "").strip().rstrip("/")
    alvos = []
    if url_escolhida:
        alvos.append({"tipo": "custom", "nome": "servidor local", "url": url_escolhida,
                      "tags": "/api/tags" if "11434" in url_escolhida else "/models"})
    do_aparelho = _endereco_do_aparelho()          # celular: o servidor do próprio app vem antes dos de sempre
    if do_aparelho:
        alvos.append({"tipo": "celular", "nome": "IA do aparelho", "url": do_aparelho, "tags": "/models"})
    alvos.extend(CANDIDATOS)
    ultimo_erro = ""
    vistos = set()
    for alvo in alvos:
        if alvo["url"] in vistos:
            continue
        vistos.add(alvo["url"])
        try:
            dados = http(alvo["url"] + alvo["tags"], timeout=timeout)
        except Exception as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
            continue
        modelos = _modelos_de(dados, alvo["tipo"])
        return {"rodando": True, "tipo": alvo["tipo"], "nome": alvo["nome"],
                "url": alvo["url"], "modelos": modelos, "erro": ""}
    return {"rodando": False, "tipo": "", "nome": "", "url": "", "modelos": [], "erro": ultimo_erro}


def _modelos_de(dados, tipo: str) -> list:
    if not isinstance(dados, dict):
        return []
    if tipo in ("ollama", "custom") and isinstance(dados.get("models"), list):
        return [str(m.get("name") or m.get("model") or "") for m in dados["models"] if isinstance(m, dict)]
    if isinstance(dados.get("data"), list):          # formato OpenAI (/v1/models)
        return [str(m.get("id") or "") for m in dados["data"] if isinstance(m, dict)]
    return []


def modelo_escolhido(settings=None, det: dict = None) -> str:
    """O modelo configurado; se vazio, o primeiro já baixado; senão o recomendado."""
    escolhido = str(_get(settings, "ia_local_modelo", "") or "").strip()
    if escolhido:
        return escolhido
    if det and det.get("modelos"):
        return det["modelos"][0]
    return MODELO_PADRAO


def url_para_cliente(settings=None, det: dict = None) -> str:
    """Endereço no formato OpenAI (o Zenith já conversa com qualquer servidor assim)."""
    if det and det.get("url"):
        url = det["url"]
    else:
        url = str(_get(settings, "ia_local_url", "") or "").strip()
    if not url:
        return ""
    url = url.rstrip("/")
    if url.endswith("/v1"):
        return url
    if ":11434" in url:                  # Ollama também aceita /v1 (compatível com OpenAI)
        return url + "/v1"
    return url + "/v1"


def status_texto(settings=None, det: dict = None) -> str:
    ligada = _bool(settings, "ia_local_ativa", False)
    det = det or detectar(settings)
    linhas = ["📱 IA local (roda no seu aparelho, sem chave):" if _no_celular() else "🖥 IA local (roda no seu PC, sem chave):"]
    linhas.append("• " + ("LIGADA como reserva" if ligada else "desligada"))
    if det.get("rodando"):
        linhas.append(f"• Servidor: {det['nome']} em {det['url']}")
        if det.get("modelos"):
            linhas.append("• Modelos baixados: " + ", ".join(det["modelos"][:6]))
        else:
            linhas.append("• Modelos baixados: nenhum ainda — /local baixar")
    else:
        linhas.append("• Servidor: não encontrado agora")
    linhas.append(f"• Modelo em uso: {modelo_escolhido(settings, det)}")
    linhas.append("• Papel: " + ("primeiro da fila" if str(_get(settings, 'ia_local_papel', 'reserva')) == 'principal'
                                 else "reserva (entra quando nuvem/cota falham)"))
    linhas.append("\nComandos: /local ligar · /local desligar · /local baixar [modelo] · /local modelo <nome> · "
                  "/local papel reserva|principal")
    if not det.get("rodando"):
        linhas.append("\n" + msg_sem_servidor())
    return "\n".join(linhas)


# ------------------------------------------------------------------ baixar modelo
def puxar_modelo(modelo: str, url: str = "http://127.0.0.1:11434", progresso=None,
                 timeout: float = 30.0, linhas=_http_linhas) -> dict:
    """Baixa um modelo no Ollama, com progresso. Só roda quando o usuário pede."""
    modelo = (modelo or MODELO_PADRAO).strip()
    if url.rstrip("/").endswith("/v1"):
        url = url.rstrip("/")[:-3]

    def ao_linha(item):
        if not progresso:
            return
        total = item.get("total")
        feito = item.get("completed")
        pct = int(100 * float(feito) / float(total)) if total and feito is not None else None
        texto = str(item.get("status") or "").strip()
        progresso(pct, texto)

    try:
        linhas(url.rstrip("/") + "/api/pull", {"model": modelo, "stream": True}, timeout=timeout, ao_linha=ao_linha)
    except Exception as e:
        return {"ok": False, "modelo": modelo,
                "mensagem": f"❌ Não consegui baixar o modelo '{modelo}': {e}\n"
                            f"Confira se o Ollama está aberto (/local) e se há espaço em disco."}
    return {"ok": True, "modelo": modelo,
            "mensagem": f"✅ Modelo '{modelo}' pronto. Agora ele entra como reserva: /local ligar."}


def garantir_modelo(settings=None, det: dict = None, progresso=None) -> str:
    """Se a IA local está ligada e o modelo pedido não existe, baixa SÓ se o usuário autorizou
    (`ia_local_baixar_sozinho`). Devolve "" (nada a fazer) ou uma linha para o chat."""
    det = det or detectar(settings)
    if not det.get("rodando") or det.get("tipo") != "ollama":
        return ""
    modelo = modelo_escolhido(settings, det)
    if modelo in (det.get("modelos") or []):
        return ""
    if not _bool(settings, "ia_local_baixar_sozinho", False):
        return (f"🖥 A IA local está ligada, mas o modelo '{modelo}' ainda não foi baixado. "
                f"Rode /local baixar (≈1 GB, uma vez só).")
    r = puxar_modelo(modelo, det.get("url") or "http://127.0.0.1:11434", progresso=progresso)
    return r["mensagem"]


def iniciar_servidor(espera_s: float = 8.0) -> dict:
    """Tenta abrir o Ollama se ele estiver instalado mas fechado (sem admin, sem janela)."""
    exe = shutil.which("ollama") or ""
    if not exe:
        for cand in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                     os.path.expandvars(r"%PROGRAMFILES%\Ollama\ollama.exe")):
            if cand and os.path.isfile(cand):
                exe = cand
                break
    if not exe:
        return {"ok": False, "mensagem": msg_sem_servidor()}
    try:
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    except Exception as e:
        return {"ok": False, "mensagem": f"❌ Achei o Ollama em {exe}, mas não consegui abrir: {e}"}
    fim = time.time() + max(1.0, espera_s)
    while time.time() < fim:
        det = detectar(timeout=1.0)
        if det.get("rodando"):
            return {"ok": True, "mensagem": f"✅ Servidor local no ar ({det['nome']}).", "detalhe": det}
        time.sleep(0.4)
    return {"ok": False, "mensagem": "⚠️ Abri o Ollama, mas ele ainda não respondeu. Tente /local em alguns segundos."}


# ------------------------------------------------------------------ configuração
def configurar(settings, ligar: bool = None, modelo: str = None, papel: str = None,
               url: str = None, baixar_sozinho: bool = None) -> dict:
    """Muda a configuração da IA local — sempre em resposta a um comando do usuário."""
    mudancas = {}
    if ligar is not None:
        mudancas["ia_local_ativa"] = bool(ligar)
    if modelo is not None:
        mudancas["ia_local_modelo"] = str(modelo or "").strip()
    if papel is not None:
        p = str(papel or "").strip().lower()
        if p not in ("reserva", "principal"):
            return {"ok": False, "mensagem": "Papel inválido: use reserva (padrão) ou principal."}
        mudancas["ia_local_papel"] = p
    if url is not None:
        mudancas["ia_local_url"] = str(url or "").strip()
    if baixar_sozinho is not None:
        mudancas["ia_local_baixar_sozinho"] = bool(baixar_sozinho)
    if not mudancas:
        return {"ok": False, "mensagem": "Nada para mudar."}
    settings.update(mudancas)
    return {"ok": True, "mensagem": "✅ Configuração da IA local atualizada.", "mudancas": mudancas}


def explicar_papel(papel: str) -> str:
    if str(papel).lower() == "principal":
        return ("A IA local passa a ser a PRIMEIRA da fila: mais privada e sem cota, mas bem mais lenta "
                "no seu PC. As nuvens continuam como reserva se ela falhar.")
    return ("A IA local fica por último: entra quando a nuvem/cota falha (é o que você pediu — somar, "
            "não substituir). Nada do que ela responder sai do seu PC.")
