"""Controla o carrinho 4WD (ESP32-S3 + Arduino Uno) pelo Wi-Fi. Argumentos: frente|tras|esquerda|direita <segundos>, ou parar, ou status. Ex.: frente 5 ; direita 1 ; frente 2

[Habilidade "carrinho" — Zenith. Fica em skills/carrinho.py]

Como funciona (conversa solta, sem depender da IA):
  Zenith --Wi-Fi (HTTP)--> ESP32-S3 --serial--> Arduino Uno --> motores.
  A IA só ENTREGA o pedido. Quem conta os segundos e para é o próprio carrinho.
  O carrinho NÃO responde se andou de fato: então esta habilidade diz "entreguei", nunca "andou".

Antes de usar, preencha CARRINHO_ENDERECO e CARRINHO_CHAVE (a mesma chave do sketch do ESP32).
Só usa a biblioteca padrão do Python (nada para instalar).
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

# ---------------- AJUSTES ----------------
CARRINHO_ENDERECO = "192.168.4.1"            # rede própria do carrinho. Em roteador/celular: "carrinho.local" ou o IP que aparece na telinha
CARRINHO_CHAVE = "troque-esta-chave"        # igual à CHAVE do sketch do ESP32-S3
TIMEOUT_REDE = 4                            # segundos esperando o ESP32 responder
MAX_SEGUNDOS_POR_PASSO = 10.0
MAX_PASSOS = 6

# palavra que a pessoa/IA pode usar -> letra do protocolo
_ALIAS = {
    "frente": "F", "frent": "F", "avancar": "F", "avançar": "F", "andar": "F", "ir": "F", "forward": "F", "f": "F",
    "tras": "B", "trás": "B", "re": "B", "ré": "B", "voltar": "B", "recuar": "B", "back": "B", "backward": "B", "b": "B",
    "esquerda": "L", "esq": "L", "left": "L", "l": "L",
    "direita": "R", "dir": "R", "right": "R", "r": "R",
    "parar": "S", "pare": "S", "para": "S", "stop": "S", "s": "S",
}
_NOME = {"F": "frente", "B": "trás", "L": "esquerda", "R": "direita"}


def _url(caminho, **params):
    params = {k: v for k, v in params.items() if v is not None}
    q = urllib.parse.urlencode(params)
    return "http://%s%s%s" % (CARRINHO_ENDERECO, caminho, ("?" + q) if q else "")


def _pedir(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT_REDE) as r:
        return r.read().decode("utf-8", "replace")


def _limpar(parte):
    """Tira enfeites da fala: 'ir para frente 5' -> 'frente 5'; 'vire à esquerda 1' -> 'esquerda 1'.
    'para' sozinho continua sendo PARAR."""
    parte = parte.strip()
    parte = re.sub(r"^(vire|virar|gire|girar|ande|anda|siga|seguir|va|vá|vai|ir)\s+", "", parte)
    parte = re.sub(r"\b(para|pra|pro)\s+(?=(a\s+|à\s+)?(frente|tr[aá]s|esquerda|direita)\b)", "", parte)
    parte = re.sub(r"\b(a|à)\s+(?=(esquerda|direita)\b)", "", parte)
    return parte.strip()


def _entender(args):
    """'frente 5; direita 1' -> [('F', 5.0), ('R', 1.0)]  ou  [('S', 0)] ou  [('STATUS', 0)]. Levanta ValueError."""
    texto = (args or "").strip().lower()
    if not texto:
        raise ValueError("faltou o comando. Exemplo: frente 5")
    if texto in ("status", "estado", "ping"):
        return [("STATUS", 0.0)]
    partes = re.split(r"[;\n]+|\s+depois\s+|\s+e depois\s+", texto)
    passos = []
    for parte in partes:
        parte = _limpar(parte)
        if not parte:
            continue
        palavra = re.match(r"[^\W\d_]+", parte)
        if not palavra or palavra.group(0) not in _ALIAS:
            raise ValueError("não entendi '%s'. Use frente, tras, esquerda, direita ou parar." % parte)
        letra = _ALIAS[palavra.group(0)]
        if letra == "S":
            return [("S", 0.0)]                      # parar vale sozinho e cancela o resto
        n = re.search(r"(\d+(?:[.,]\d+)?)", parte[palavra.end():])
        seg = float(n.group(1).replace(",", ".")) if n else 1.0
        seg = max(0.1, min(seg, MAX_SEGUNDOS_POR_PASSO))
        passos.append((letra, seg))
    if not passos:
        raise ValueError("nenhum passo entendido.")
    if len(passos) > MAX_PASSOS:
        raise ValueError("passos demais (máximo %d de uma vez)." % MAX_PASSOS)
    return passos


def _fmt(seg):
    return ("%g" % seg).replace(".", ",")


def rodar(args=""):
    try:
        passos = _entender(args)
    except ValueError as e:
        return "🚗 Carrinho: " + str(e)

    chave = CARRINHO_CHAVE
    enviados = []
    try:
        if passos[0][0] == "STATUS":
            info = json.loads(_pedir(_url("/status")))
            return ("🚗 Carrinho vivo: IP %s, Wi-Fi %s dBm, ligado há %s s, último comando: %s."
                    % (info.get("ip"), info.get("wifi_dbm"), info.get("ligado_ha_s"), info.get("ultimo_comando")))
        if passos[0][0] == "S":
            _pedir(_url("/parar", k=chave))
            return "🛑 Mandei PARAR para o carrinho (apaga também os passos que estavam na fila)."
        for letra, seg in passos:
            _pedir(_url("/cmd", c=letra, t=int(round(seg * 1000)), k=chave))
            enviados.append("%s %s s" % (_NOME[letra], _fmt(seg)))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return "🔑 O carrinho recusou: a chave está errada (CARRINHO_CHAVE não bate com a do ESP32)."
        return "⚠ O carrinho respondeu com erro %s." % e.code
    except (urllib.error.URLError, OSError, ValueError):
        extra = ""
        if enviados:
            try:
                _pedir(_url("/parar", k=chave))
                extra = " Como falhou no meio, mandei PARAR."
            except Exception:
                extra = " Atenção: ele pode continuar os passos que já recebeu (%s)." % "; ".join(enviados)
        return ("🔌 Não consegui falar com o carrinho em %s. Ele está ligado e no mesmo Wi-Fi que este PC?%s"
                % (CARRINHO_ENDERECO, extra))

    total = sum(s for _, s in passos)
    return ("🚗 Entreguei ao carrinho: %s (≈ %s s no total). Ele executa sozinho e não me avisa se andou de verdade — "
            "dá uma olhada nele." % ("; ".join(enviados), _fmt(total)))
