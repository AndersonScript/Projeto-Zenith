"""Zenith — DOWNGRADE (v1.11): o mesmo Zenith do PC, com chaves para o celular aguentar.

A ideia é a do Anderson: o app vem COMPLETO, igual ao do PC (VRM, voz, visão, memória, IA local), e a pessoa
RABAIXA o que o aparelho dela não aguenta — tira o VRM, a voz, a câmera... — sem perder o resto. Este módulo é
a lógica pura dessa tela de "Desempenho" (sem Android, sem Godot, sem rede): recebe a medida do aparelho e
devolve o que recomenda; a tela só mostra e grava.

Princípios (herdados do `zenith_desempenho` do PC)
--------------------------------------------------
* Só mede e recomenda. NUNCA muda nada sozinho: esquentou ou travou -> `proximo_passo()` devolve uma SUGESTÃO,
  e quem aplica é a pessoa (aprovação, como em todo o resto do Zenith).
* Se não deu para medir a memória, não chuta: devolve `ok=False` com o motivo.
* Os limiares ficam numa constante e podem ser trocados em `settings["downgrade_limiares"]` — nada de número
  mágico escondido (foi a lição dos erros da v1.10). OS VALORES INICIAIS SÃO ESTIMATIVAS: ajuste depois de
  medir num celular de verdade.
* Regra do projeto: o avatar fica sempre visível. O piso é o avatar PADRÃO (o visual do código), nunca "sem
  avatar". Se um dia quiser "só texto", é acrescentar um valor em RECURSOS["avatar"].
"""
from __future__ import annotations

import copy

# Cada recurso: valores do MELHOR para o PIOR. Rebaixar = andar um passo para a direita.
RECURSOS = {
    "avatar": ("vrm", "padrao"),
    "qualidade_grafica": ("alta", "media", "baixa"),
    "fps": (60, 30, 20),
    "voz_saida": ("local", "desligada"),
    "voz_entrada": ("whisper", "sistema", "desligada"),
    "visao": ("ligada", "desligada"),
    "memoria": ("vetorial", "leve"),
    "ia_local": ("ligada", "desligada"),
}

# Ordem em que a SUGESTÃO rebaixa: o que menos dói primeiro; o avatar VRM e a voz da saída ficam por último.
ESCADA = ("qualidade_grafica", "fps", "ia_local", "visao", "voz_entrada", "memoria", "avatar", "voz_saida")

ROTULOS = {
    "avatar": "Avatar", "qualidade_grafica": "Qualidade gráfica", "fps": "Quadros por segundo",
    "voz_saida": "Voz (falar)", "voz_entrada": "Voz (escutar)", "visao": "Câmera e tela",
    "memoria": "Memória", "ia_local": "IA no aparelho",
}

PERFIS = {
    "completo": {"avatar": "vrm", "qualidade_grafica": "alta", "fps": 60, "voz_saida": "local",
                 "voz_entrada": "whisper", "visao": "ligada", "memoria": "vetorial", "ia_local": "ligada"},
    "medio": {"avatar": "vrm", "qualidade_grafica": "media", "fps": 30, "voz_saida": "local",
              "voz_entrada": "sistema", "visao": "ligada", "memoria": "leve", "ia_local": "ligada"},
    "leve": {"avatar": "vrm", "qualidade_grafica": "baixa", "fps": 20, "voz_saida": "local",
             "voz_entrada": "sistema", "visao": "desligada", "memoria": "leve", "ia_local": "desligada"},
    "minimo": {"avatar": "padrao", "qualidade_grafica": "baixa", "fps": 20, "voz_saida": "local",
               "voz_entrada": "sistema", "visao": "desligada", "memoria": "leve", "ia_local": "desligada"},
}

# RAM TOTAL mínima (GB) para cada perfil, do melhor para o pior. ESTIMATIVAS: medir num aparelho real.
LIMIARES = {"completo": 10.0, "medio": 6.0, "leve": 4.0}

# Modelos locais para celular (arquivo quantizado). Mesma regra do PC: precisa de ~1,7x o arquivo de RAM.
# 1.5b e 3b vêm da lista do PC; o 0.5b é estimativa. Confirmar no aparelho.
MODELOS_CELULAR = (
    {"modelo": "qwen2.5:0.5b", "arquivo_gb": 0.4, "ram_gb": 1.2, "nota": "respostas curtas, português simples"},
    {"modelo": "qwen2.5:1.5b", "arquivo_gb": 1.0, "ram_gb": 2.6, "nota": "conversa razoável em português"},
    {"modelo": "llama3.2:3b", "arquivo_gb": 2.0, "ram_gb": 4.0, "nota": "melhor qualidade; exige muita RAM livre"},
)
RESERVA_AVATAR_GB = {"vrm": 1.5, "padrao": 0.5}      # RAM que o avatar já usa antes de a IA carregar
FOLGA_GB = 1.0                                         # o celular precisa continuar utilizável
TEMPERATURA_ALERTA_C = 42.0
BATERIA_ALERTA_PCT = 20


def validar(recursos: dict) -> dict:
    """Confere chaves e valores; devolve uma cópia. Levanta ValueError com a frase do problema."""
    if set(recursos) != set(RECURSOS):
        faltam = sorted(set(RECURSOS) - set(recursos))
        sobram = sorted(set(recursos) - set(RECURSOS))
        raise ValueError(f"Configuração de desempenho inválida (faltam {faltam}, sobram {sobram}).")
    limpo = {}
    for chave, valor in recursos.items():
        if isinstance(valor, float) and valor.is_integer():
            valor = int(valor)                      # o Godot manda 60 como 60.0
        if isinstance(valor, bool) or valor not in RECURSOS[chave]:
            raise ValueError(f"'{valor}' não é um valor válido para {ROTULOS[chave]} "
                             f"(opções: {', '.join(map(str, RECURSOS[chave]))}).")
        limpo[chave] = valor
    return limpo


def perfil(nome: str) -> dict:
    if nome not in PERFIS:
        raise ValueError(f"Perfil desconhecido: {nome!r} (opções: {', '.join(PERFIS)}).")
    return copy.deepcopy(PERFIS[nome])


def escolher_modelo_local(medida: dict, avatar: str = "vrm", modelos=MODELOS_CELULAR) -> dict:
    """Maior modelo que cabe na RAM livre depois do avatar e da folga. {ok, modelo, motivo, ...}."""
    livre = medida.get("ram_livre_gb")
    referencia = livre if livre is not None else None
    if referencia is None:
        return {"ok": False, "modelo": "", "motivo": "Não consegui medir a memória livre deste celular — "
                                                     "sem isso eu não chuto o tamanho da IA local."}
    disponivel = round(referencia - RESERVA_AVATAR_GB.get(avatar, 1.5) - FOLGA_GB, 2)   # 2 casas: evita 2.5999999 < 2.6
    disco = medida.get("disco_livre_gb")
    escolhido = None
    for m in modelos:
        if disponivel >= m["ram_gb"] and (disco is None or disco >= m["arquivo_gb"]):
            escolhido = m
    if not escolhido:
        return {"ok": False, "modelo": "",
                "motivo": (f"Com {referencia:.1f} GB livres (e o avatar usando parte), nenhum modelo local "
                           f"cabe sem travar o celular — o menor pede ~{modelos[0]['ram_gb']:.1f} GB livres. "
                           "Feche outros apps e peça de novo, ou use só as IAs da internet.")}
    return {"ok": True, "modelo": escolhido["modelo"], "arquivo_gb": escolhido["arquivo_gb"],
            "ram_gb": escolhido["ram_gb"],
            "motivo": (f"Com {referencia:.1f} GB livres, o {escolhido['modelo']} "
                       f"({escolhido['arquivo_gb']:.1f} GB no armazenamento) cabe com folga — {escolhido['nota']}.")}


def recomendar(medida: dict, memoria_vetorial_disponivel: bool = False, limiares: dict | None = None) -> dict:
    """Escolhe o perfil pela RAM total e ajusta pelos detalhes. Devolve:
    {ok, perfil, recursos, modelo_local, motivos[], avisos[]}. Não aplica nada."""
    lim = {**LIMIARES, **(limiares or {})}
    total = medida.get("ram_total_gb")
    if total is None:
        return {"ok": False, "perfil": "", "recursos": {}, "modelo_local": None, "motivos": [],
                "avisos": ["Não consegui medir a memória deste celular — sem isso eu não chuto o perfil. "
                           "Escolha um perfil à mão."]}
    nome = next((p for p in ("completo", "medio", "leve") if total >= lim[p]), "minimo")
    recursos = perfil(nome)
    motivos = [f"Este celular tem {total:.1f} GB de RAM: perfil {nome}."]
    avisos = []

    if recursos["memoria"] == "vetorial" and not memoria_vetorial_disponivel:
        recursos["memoria"] = "leve"
        avisos.append("Memória por sentido (vetorial) ainda não existe no celular; usando a memória leve, "
                      "que busca por palavras.")

    modelo = None
    if recursos["ia_local"] == "ligada":
        modelo = escolher_modelo_local(medida, recursos["avatar"])
        if modelo["ok"]:
            motivos.append(modelo["motivo"])
        else:
            recursos["ia_local"] = "desligada"
            avisos.append(modelo["motivo"])
            modelo = None

    temp, bat, carregando = medida.get("temperatura_c"), medida.get("bateria_pct"), medida.get("carregando")
    if temp is not None and temp >= TEMPERATURA_ALERTA_C:
        avisos.append(f"O celular está quente ({temp:.0f} °C). Se travar, rebaixe um passo (veja a sugestão).")
    if bat is not None and bat <= BATERIA_ALERTA_PCT and not carregando:
        avisos.append(f"Bateria em {bat:.0f}%. IA local, câmera e avatar VRM gastam muito: considere rebaixar.")
    return {"ok": True, "perfil": nome, "recursos": validar(recursos), "modelo_local": modelo,
            "motivos": motivos, "avisos": avisos}


def proximo_passo(recursos: dict, motivo: str = "") -> dict | None:
    """Primeiro recurso da ESCADA que ainda dá para rebaixar. Devolve a SUGESTÃO (não aplica). None = no piso."""
    validar(recursos)
    for chave in ESCADA:
        opcoes = RECURSOS[chave]
        atual = opcoes.index(recursos[chave])
        if atual + 1 < len(opcoes):
            return {"recurso": chave, "rotulo": ROTULOS[chave], "de": recursos[chave], "para": opcoes[atual + 1],
                    "motivo": motivo or "O celular está sofrendo; este é o ajuste que menos tira do Zenith."}
    return None


def aplicar(recursos: dict, recurso: str, valor) -> dict:
    """Devolve uma cópia com UM recurso trocado (a pessoa tocou na chave). Valida antes."""
    novo = dict(recursos)
    novo[recurso] = valor
    return validar(novo)


def para_settings(recursos: dict) -> dict:
    """O que gravar em settings['downgrade']."""
    return validar(recursos)


def de_settings(settings: dict) -> dict | None:
    """Lê settings['downgrade']. None = a pessoa ainda não escolheu (a primeira abertura mede e recomenda).
    Valor inválido (arquivo editado à mão, versão antiga) também vira None em vez de derrubar o app."""
    bruto = (settings or {}).get("downgrade")
    if not isinstance(bruto, dict):
        return None
    try:
        return validar(bruto)
    except ValueError:
        return None


def formatar(medida: dict, rec: dict) -> str:
    """Texto para o chat/tela (no mesmo estilo do `zenith_desempenho.formatar` do PC)."""
    linhas = ["📱 Este celular:"]
    if medida.get("ram_total_gb") is None:
        linhas.append("• Memória: não consegui medir")
    else:
        livre = medida.get("ram_livre_gb")
        linhas.append(f"• Memória: {livre:.1f} GB livres de {medida['ram_total_gb']:.1f} GB"
                      if livre is not None else f"• Memória: {medida['ram_total_gb']:.1f} GB no total")
    linhas.append(f"• Núcleos: {medida.get('nucleos') or '?'}")
    if medida.get("disco_livre_gb") is not None:
        linhas.append(f"• Armazenamento livre: {medida['disco_livre_gb']:.1f} GB")
    if medida.get("bateria_pct") is not None:
        linhas.append(f"• Bateria: {medida['bateria_pct']:.0f}%" + (" (carregando)" if medida.get("carregando") else ""))
    if rec.get("ok"):
        linhas += ["", f"✅ Perfil recomendado: {rec['perfil']}"]
        linhas += [f"• {ROTULOS[k]}: {v}" for k, v in rec["recursos"].items()]
    linhas += [f"• {m}" for m in rec.get("motivos", [])]
    linhas += [f"⚠ {a}" for a in rec.get("avisos", [])]
    return "\n".join(linhas)


# ---- efeito nas configurações do Cérebro (REVERSÍVEL) -------------------------------------------------------------
# Rebaixar um recurso muda uma configuração que já existe (ex.: desligar a voz = voice_enabled False). Para a pessoa
# poder SUBIR de novo sem perder nada, o valor que estava antes fica guardado e é devolvido EXATAMENTE como era —
# inclusive um "never" que ela mesma tinha posto. O módulo nunca solta uma permissão por conta própria.
GUARDADO = "downgrade_guardado"


def _rebaixados(recursos: dict) -> dict:
    """caminho da configuração (ex.: 'permissions.camera') -> valor que ela recebe quando o recurso está rebaixado.
    Recurso que não mexe em nenhuma configuração do Cérebro (avatar, gráficos, FPS, memória) não aparece aqui."""
    r = {}
    if recursos["voz_saida"] == "desligada":
        r["voice_enabled"] = False
    if recursos["voz_entrada"] == "desligada":
        r["permissions.microphone"] = "never"
    if recursos["visao"] == "desligada":
        r["permissions.camera"] = "never"
        r["permissions.screen"] = "never"
    if recursos["ia_local"] == "desligada":
        r["ia_local_ativa"] = False
    return r


_CONTROLADOS = ("voice_enabled", "permissions.microphone", "permissions.camera", "permissions.screen", "ia_local_ativa")


def _ler(cfg: dict, caminho: str):
    atual = cfg
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


def _gravar(destino: dict, caminho: str, valor) -> None:
    partes = caminho.split(".")
    for parte in partes[:-1]:
        destino = destino.setdefault(parte, {})
    destino[partes[-1]] = valor


def mudancas_nas_configuracoes(recursos: dict, settings: dict) -> dict:
    """O que gravar nas configurações para `recursos` valerem. Devolve um dicionário PARCIAL (para `settings.update`):
    as configurações controladas, `downgrade` (a escolha) e `downgrade_guardado` (o que estava antes).
    Entradas de `downgrade_guardado` com valor None significam "nada guardado" (o `update` não apaga chaves)."""
    recursos = validar(recursos)
    rebaixados = _rebaixados(recursos)
    guardado = {k: v for k, v in (settings.get(GUARDADO) or {}).items() if v is not None}
    saida: dict = {}
    for caminho in _CONTROLADOS:
        if caminho in rebaixados:
            if caminho not in guardado:
                anterior = _ler(settings, caminho)
                if anterior is not None:
                    guardado[caminho] = anterior
            _gravar(saida, caminho, rebaixados[caminho])
        elif caminho in guardado:
            _gravar(saida, caminho, guardado.pop(caminho))        # devolve exatamente o que estava antes
    marcadores = {k: None for k in _CONTROLADOS}                  # None = apagado
    marcadores.update(guardado)
    saida["downgrade"] = recursos
    saida[GUARDADO] = marcadores
    return saida
