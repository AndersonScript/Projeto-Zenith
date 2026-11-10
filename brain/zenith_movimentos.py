"""Zenith — MOVIMENTOS (v1.6): pulo de verdade, dança, câmera, passeio da janela, rostos — e a IA cria os dela.

Por que existe: o usuário pediu "faz uma careta e dá um pulo" e a IA respondeu "Feito! Dei o pulo", mas NADA aconteceu.
Havia duas causas: (1) o "pulinho" antigo era uma vibração de 1,2 cm que nem era aplicada na tela; (2) a IA não sabia quais
movimentos existiam e inventava que tinha feito. Agora:

  * um MOVIMENTO é um pequeno arquivo de dados (JSON): faixas de valores no tempo ("corpo_y sobe 27 cm em 0,3 s").
    O Corpo (Godot) só sabe TOCAR dados; não há código escrito por IA rodando em lugar nenhum;
  * a biblioteca tem movimentos prontos (pulo, dança, giro, caretas, aproximar/afastar a câmera, passear com a janela)
    e a IA pode CRIAR novos com <criar_movimento>{...}</criar_movimento>; eles são validados aqui (limites de altura,
    duração, lista de coisas proibidas) e guardados em config/movimentos/;
  * se a IA disser que fez um movimento sem usar a etiqueta, ou se o usuário PEDIR ("dá um pulo"), o Cérebro toca o
    movimento certo do mesmo jeito: o que ela diz que fez, acontece.

Pilar 6 (antirromântico): nomes e descrições com beijo, coração, abraço, piscadinha, "OK" (gesto ofensivo no Brasil) ou
conteúdo sensual são recusados. Janela: só a janela do avatar se move, dentro da tela, e `/parar` interrompe tudo.

Mensagens para o Corpo (Godot):
  {"action": "movement_library", "clips": {nome: clipe, ...}}   biblioteca completa (ao conectar e quando muda)
  {"action": "movement_play", "nome": "pulo", "escala": 1.0}      toca (enfileira até 4)
  {"action": "movement_stop"}                                     para tudo (a câmera/janela ficam onde estão)
  {"action": "movement_config", "janela": true, "camera": true}   liga/desliga janela e câmera
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------------------------------------------------
# vocabulário (o que um movimento pode mexer) e limites — o Corpo repete estes mesmos limites por segurança
# ---------------------------------------------------------------------------------------------------------------------
LIMITES = {
    # corpo inteiro do avatar (metros / graus) — limites ampliados para mortais, pulos e acrobacias sem travas
    "corpo_x": (-3.0, 3.0), "corpo_y": (-1.5, 4.5), "corpo_z": (-3.0, 3.0),
    "corpo_giro": (-1080.0, 1080.0), "corpo_roll": (-720.0, 720.0), "corpo_pitch": (-720.0, 720.0),
    # cabeça (graus)
    "cabeca_pitch": (-70.0, 70.0), "cabeca_yaw": (-100.0, 100.0), "cabeca_roll": (-70.0, 70.0),
    # câmera do avatar: zoom e deslocamento
    "camera_zoom": (0.2, 4.0), "camera_x": (-2.0, 2.0), "camera_y": (-2.0, 2.0),
    # janela do avatar: posição em pixels
    "janela_x": (-2500.0, 2500.0), "janela_y": (-1500.0, 1500.0),
    "janela_dx": (-500.0, 500.0), "janela_dy": (-500.0, 500.0),
}
PERSISTENTES = ("camera_zoom", "camera_x", "camera_y", "janela_x", "janela_y")   # aceitam `null` na 1ª chave = "de onde estiver"
PADRAO_ATUAL = {"camera_zoom": 1.0}                                              # os demais partem de 0
ROSTOS = ("happy", "angry", "sad", "relaxed", "surprised", "aa", "ih", "ou", "ee", "oh", "blink")   # faixa "rosto:<nome>" 0..1
BRACOS = ("braco_dir", "braco_esq")      # chave: [t, ux,uy,uz, lx,ly,lz, peso?] (ux = para fora, uy = para cima, uz = para frente)
MAOS = ("relaxada", "aberta", "pensar", "punho", "apontar")
DURACAO_MAX, REPETIR_MAX, FAIXAS_MAX, CHAVES_MAX, BIBLIOTECA_MAX, FILA_MAX = 12.0, 8, 14, 48, 100, 4
TEMPO_TOTAL_MAX = 45.0

NOME_OK = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
# Pilar 6 — nada de gestos românticos/ofensivos/sensuais (comparado sem acento, em minúsculas)
_PROIBIDAS = re.compile(
    r"beij|coracao|abraco|abracar|piscadinha|piscar_olho|pisca_olho|\bok\b|_ok_|^ok_|_ok$|joinha_ok|sensual|sexy|sexual|rebol|"
    r"twerk|strip|lap_?dance|erotic|nude|nua\b|kiss|heart|hug|wink|dedo_do_meio|middle_finger|facepalm_ofensivo")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------------------------------------------------
# validação
# ---------------------------------------------------------------------------------------------------------------------
def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        raise ValueError("valor não numérico")
    return float(x)


def _clamp(v, lo, hi, avisos, onde):
    if v < lo or v > hi:
        avisos.append(f"{onde}: {v:g} fora de [{lo:g}, {hi:g}] — ajustei")
        return min(max(v, lo), hi)
    return v


def validar(dados, nome=None):
    """Confere um movimento vindo da IA/usuário. Devolve (clipe_limpo, avisos, erro). Se `erro` != "" o clipe é None."""
    avisos = []
    try:
        if not isinstance(dados, dict):
            return None, avisos, "o movimento precisa ser um objeto JSON"
        nome = str(nome or dados.get("nome") or "").strip().lower()
        if not NOME_OK.match(nome):
            return None, avisos, "nome inválido (use letras minúsculas, números e _; de 2 a 32 caracteres, começando por letra)"
        descricao = str(dados.get("descricao") or "")[:200]
        if _PROIBIDAS.search(_sem_acento(nome)) or _PROIBIDAS.search(_sem_acento(descricao)):
            return None, avisos, "esse tipo de movimento não é permitido (o Zenith não faz gestos românticos, sensuais ou ofensivos)"
        dur = _clamp(_num(dados.get("duracao", 1.0)), 0.3, DURACAO_MAX, avisos, "duracao")
        repetir = int(_clamp(_num(dados.get("repetir", 1)), 1, REPETIR_MAX, avisos, "repetir"))
        if dur * repetir > TEMPO_TOTAL_MAX:
            repetir = max(1, int(TEMPO_TOTAL_MAX // dur))
            avisos.append(f"duração total passava de {TEMPO_TOTAL_MAX:g} s — repetir virou {repetir}")
        mao = dados.get("mao")
        if mao is not None and mao not in MAOS:
            avisos.append(f"mao '{mao}' não existe — ignorei (use: {', '.join(MAOS)})")
            mao = None
        faixas_in = dados.get("faixas")
        if not isinstance(faixas_in, list) or not faixas_in:
            return None, avisos, "faltam as faixas (lista 'faixas' com pelo menos uma)"
        if len(faixas_in) > FAIXAS_MAX:
            return None, avisos, f"faixas demais (máximo {FAIXAS_MAX})"
        faixas, vistos = [], set()
        for k, f in enumerate(faixas_in):
            alvo = str(f.get("alvo", "")).strip().lower() if isinstance(f, dict) else ""
            onde = f"faixa {k + 1} ({alvo or '?'})"
            tipo = "bracos" if alvo in BRACOS else "rosto" if alvo.startswith("rosto:") else "escalar"
            if tipo == "rosto" and alvo[6:] not in ROSTOS:
                return None, avisos, f"{onde}: rosto desconhecido. Use rosto:<{'|'.join(ROSTOS)}>"
            if tipo == "escalar" and alvo not in LIMITES:
                return None, avisos, f"{onde}: alvo desconhecido. Alvos: {', '.join(sorted(LIMITES))}, rosto:<nome>, {', '.join(BRACOS)}"
            if alvo in vistos:
                return None, avisos, f"{onde}: alvo repetido"
            vistos.add(alvo)
            chaves_in = f.get("chaves")
            if not isinstance(chaves_in, list) or len(chaves_in) < 2:
                return None, avisos, f"{onde}: precisa de pelo menos 2 chaves"
            if len(chaves_in) > CHAVES_MAX:
                return None, avisos, f"{onde}: chaves demais (máximo {CHAVES_MAX})"
            chaves, t_ant = [], -1.0
            for j, c in enumerate(chaves_in):
                if not isinstance(c, list) or not c:
                    return None, avisos, f"{onde}: chave {j + 1} inválida"
                t = _clamp(_num(c[0]), 0.0, dur, avisos, f"{onde}, tempo")
                if t < t_ant:
                    return None, avisos, f"{onde}: os tempos precisam crescer (chave {j + 1})"
                t_ant = t
                if tipo == "bracos":
                    if len(c) not in (7, 8):
                        return None, avisos, f"{onde}: cada chave é [t, ux,uy,uz, lx,ly,lz, peso]"
                    vet = [_clamp(_num(x), -1.0, 1.0, avisos, onde) for x in c[1:7]]
                    if math.sqrt(sum(x * x for x in vet[:3])) < 0.2 or math.sqrt(sum(x * x for x in vet[3:])) < 0.2:
                        return None, avisos, f"{onde}: vetor do braço quase zero (chave {j + 1})"
                    peso = _clamp(_num(c[7]) if len(c) == 8 else 1.0, 0.0, 1.0, avisos, onde)
                    chaves.append([t] + vet + [peso])
                else:
                    if len(c) != 2:
                        return None, avisos, f"{onde}: cada chave é [t, valor]"
                    if c[1] is None:
                        if j != 0 or alvo not in PERSISTENTES:
                            return None, avisos, f"{onde}: 'null' (= de onde estiver) só vale na PRIMEIRA chave de {', '.join(PERSISTENTES)}"
                        chaves.append([t, None])
                    else:
                        lo, hi = (0.0, 1.0) if tipo == "rosto" else LIMITES[alvo]
                        chaves.append([t, _clamp(_num(c[1]), lo, hi, avisos, onde)])
            faixas.append({"alvo": alvo, "chaves": chaves})
        return {"nome": nome, "descricao": descricao, "duracao": dur, "repetir": repetir, "mao": mao,
                "suave": bool(dados.get("suave", True)), "faixas": faixas}, avisos, ""
    except (ValueError, TypeError, AttributeError) as e:
        return None, avisos, f"movimento mal formado: {e}"


# ---------------------------------------------------------------------------------------------------------------------
# a conta do tempo (o Corpo em GDScript repete exatamente esta lógica)
# ---------------------------------------------------------------------------------------------------------------------
def _suave(u):
    return u * u * (3.0 - 2.0 * u)


def _interpola(chaves, t, suave, atual):
    """chaves: [[t, v...], ...]. Devolve float (escalar) ou lista (vetor). `atual` substitui um `null` na 1ª chave."""
    def val(c):
        v = c[1:]
        if len(v) == 1:
            return atual if v[0] is None else v[0]
        return list(v)
    if t <= chaves[0][0]:
        return val(chaves[0])
    for a, b in zip(chaves, chaves[1:]):
        if t <= b[0]:
            span = b[0] - a[0]
            u = 1.0 if span <= 1e-9 else (t - a[0]) / span
            u = _suave(u) if suave else u
            va, vb = val(a), val(b)
            if isinstance(va, list):
                return [x + (y - x) * u for x, y in zip(va, vb)]
            return va + (vb - va) * u
    return val(chaves[-1])


def envelope(t_total, dur_total, entrada=0.18, saida=0.25):
    """Peso 0..1 que suaviza o começo e o fim (braços, cabeça e rosto saem do natural e voltam sem tranco)."""
    a = _suave(min(1.0, max(0.0, t_total / entrada)))
    b = _suave(min(1.0, max(0.0, (dur_total - t_total) / saida)))
    return min(a, b)


def avaliar(clipe, t_total, atual=None):
    """Valores de todas as faixas no instante `t_total` (segundos desde o início). `atual` = {alvo: valor atual} para os null."""
    atual = atual or {}
    dur = clipe["duracao"]
    total = dur * clipe.get("repetir", 1)
    t = min(max(t_total, 0.0), total)
    t_local = dur if t >= total else t % dur
    saida = {"peso": envelope(t, total), "fim": t_total >= total}
    for f in clipe["faixas"]:
        base = atual.get(f["alvo"], PADRAO_ATUAL.get(f["alvo"], 0.0))
        saida[f["alvo"]] = _interpola(f["chaves"], t_local, clipe.get("suave", True), base)
    return saida


# ---------------------------------------------------------------------------------------------------------------------
# movimentos prontos
# ---------------------------------------------------------------------------------------------------------------------
_BRACO_BAIXO = [0.10, -0.95, 0.05, 0.05, -0.95, 0.10]
_BRACO_ALTO = [0.55, 0.80, 0.10, 0.35, 0.90, 0.15]
_BRACO_ABERTO = [0.85, 0.15, 0.05, 0.75, 0.25, 0.10]


def _amostras(f, dur, passo):
    n = int(round(dur / passo))
    return [[round(i * passo, 4), round(f(i * passo), 4)] for i in range(n + 1)]


def _braco(t, pose, peso=1.0):
    return [t] + list(pose) + [peso]


def _prontos():
    p = {}
    # --- Movimentos Acrobáticos e Especiais (sem limitações de altura ou rotação) ---
    p["mortal"] = {
        "descricao": "Salto mortal para trás completo (backflip de 360 graus) com subida de 1.4m.",
        "duracao": 1.3, "repetir": 1, "suave": True, "mao": "aberta",
        "faixas": [
            {"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.15, -0.18], [0.65, 1.4], [1.1, 0.05], [1.2, -0.05], [1.3, 0.0]]},
            {"alvo": "corpo_pitch", "chaves": [[0.0, 0.0], [0.15, 15.0], [0.38, -90.0], [0.65, -180.0], [0.92, -270.0], [1.15, -360.0], [1.3, -360.0]]},
            {"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.8], [1.0, 0.8], [1.3, 0.0]]}
        ]
    }
    p["mortal_frente"] = {
        "descricao": "Salto mortal para frente (frontflip de 360 graus).",
        "duracao": 1.3, "repetir": 1, "suave": True, "mao": "aberta",
        "faixas": [
            {"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.15, -0.18], [0.65, 1.4], [1.1, 0.05], [1.2, -0.05], [1.3, 0.0]]},
            {"alvo": "corpo_pitch", "chaves": [[0.0, 0.0], [0.15, -15.0], [0.38, 90.0], [0.65, 180.0], [0.92, 270.0], [1.15, 360.0], [1.3, 360.0]]},
            {"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.8], [1.0, 0.8], [1.3, 0.0]]}
        ]
    }
    p["pulo_alto"] = {
        "descricao": "Pulo bem alto de verdade (1.6 metros), comemorando com os dois braços para cima.",
        "duracao": 1.4, "repetir": 1, "suave": True, "mao": "aberta",
        "faixas": [
            {"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.18, -0.22], [0.65, 1.6], [1.15, 0.05], [1.25, -0.05], [1.4, 0.0]]},
            {"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.9], [1.1, 0.9], [1.4, 0.0]]}
        ]
    }
    p["estrela"] = {
        "descricao": "Acrobacia de virar estrela (giro lateral de 360 graus).",
        "duracao": 1.4, "repetir": 1, "suave": True, "mao": "aberta",
        "faixas": [
            {"alvo": "corpo_x", "chaves": [[0.0, 0.0], [0.35, -0.45], [0.7, 0.0], [1.05, 0.45], [1.4, 0.0]]},
            {"alvo": "corpo_y", "chaves": [[0.0, 0.0], [0.25, 0.4], [0.7, 0.95], [1.15, 0.25], [1.4, 0.0]]},
            {"alvo": "corpo_roll", "chaves": [[0.0, 0.0], [0.7, 180.0], [1.4, 360.0]]},
            {"alvo": "rosto:happy", "chaves": [[0.0, 0.0], [0.3, 0.7], [1.1, 0.7], [1.4, 0.0]]}
        ]
    }
    p["pulo"] = {"descricao": "Um pulo de verdade (uns 27 cm), de braços para cima e sorrindo.", "duracao": 1.15, "mao": "aberta", "faixas": [
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.14, -0.035], [0.46, 0.27], [0.80, 0.0], [0.92, -0.02], [1.15, 0]]},
        {"alvo": "janela_dy", "chaves": [[0, 0], [0.46, -55], [0.80, 0], [1.15, 0]]},
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.14, _BRACO_BAIXO, 0.3), _braco(0.46, _BRACO_ALTO), _braco(0.85, _BRACO_ALTO, 0.4), _braco(1.15, _BRACO_BAIXO, 0)]},
        {"alvo": "braco_esq", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.14, _BRACO_BAIXO, 0.3), _braco(0.46, _BRACO_ALTO), _braco(0.85, _BRACO_ALTO, 0.4), _braco(1.15, _BRACO_BAIXO, 0)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.3, 0.7], [0.9, 0.7], [1.15, 0]]}]}
    p["pulo_duplo"] = {"descricao": "Dois pulos seguidos, comemorando.", "duracao": 2.0, "mao": "aberta", "faixas": [
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.12, -0.03], [0.40, 0.25], [0.72, 0.0], [0.84, -0.03], [1.20, 0.30], [1.62, 0.0], [1.75, -0.02], [2.0, 0]]},
        {"alvo": "janela_dy", "chaves": [[0, 0], [0.40, -50], [0.72, 0], [1.20, -65], [1.62, 0], [2.0, 0]]},
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.4, _BRACO_ALTO), _braco(1.2, _BRACO_ALTO), _braco(2.0, _BRACO_BAIXO, 0)]},
        {"alvo": "braco_esq", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.4, _BRACO_ALTO), _braco(1.2, _BRACO_ALTO), _braco(2.0, _BRACO_BAIXO, 0)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.4, 0.8], [1.6, 0.8], [2.0, 0]]}]}
    s2 = 2 * math.pi
    p["dancar"] = {"descricao": "Dança animada: balança o corpo, gira os ombros, alterna os braços e balança a janela.", "duracao": 4.0, "repetir": 2, "mao": "aberta", "faixas": [
        {"alvo": "corpo_x", "chaves": _amostras(lambda t: 0.07 * math.sin(s2 * t / 2), 4.0, 0.125)},
        {"alvo": "corpo_y", "chaves": _amostras(lambda t: 0.04 * abs(math.sin(math.pi * t / 0.5)), 4.0, 0.125)},
        {"alvo": "corpo_giro", "chaves": _amostras(lambda t: 22 * math.sin(s2 * t / 2), 4.0, 0.125)},
        {"alvo": "corpo_roll", "chaves": _amostras(lambda t: 6 * math.sin(s2 * t / 2 + math.pi / 2), 4.0, 0.125)},
        {"alvo": "cabeca_roll", "chaves": _amostras(lambda t: 10 * math.sin(s2 * t / 1), 4.0, 0.125)},
        {"alvo": "janela_dx", "chaves": _amostras(lambda t: 22 * math.sin(s2 * t / 2), 4.0, 0.125)},
        {"alvo": "braco_dir", "chaves": [_braco(i * 0.5, _BRACO_ALTO if i % 2 == 0 else _BRACO_ABERTO) for i in range(9)]},
        {"alvo": "braco_esq", "chaves": [_braco(i * 0.5, _BRACO_ABERTO if i % 2 == 0 else _BRACO_ALTO) for i in range(9)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0.6], [4.0, 0.6]]}]}
    p["girar"] = {"descricao": "Uma volta completa em pé.", "duracao": 1.3, "mao": "aberta", "faixas": [
        {"alvo": "corpo_giro", "chaves": [[0, 0], [1.3, 360]]},
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.3, 0.05], [1.0, 0.05], [1.3, 0]]},
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.3, _BRACO_ABERTO), _braco(1.0, _BRACO_ABERTO), _braco(1.3, _BRACO_BAIXO, 0)]},
        {"alvo": "braco_esq", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.3, _BRACO_ABERTO), _braco(1.0, _BRACO_ABERTO), _braco(1.3, _BRACO_BAIXO, 0)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.4, 0.6], [1.0, 0.6], [1.3, 0]]}]}
    p["careta"] = {"descricao": "Uma careta engraçada: testa franzida, boca em 'o', cabeça de lado.", "duracao": 2.2, "faixas": [
        {"alvo": "rosto:angry", "chaves": [[0, 0], [0.25, 0.55], [1.9, 0.55], [2.2, 0]]},
        {"alvo": "rosto:oh", "chaves": [[0, 0], [0.25, 0.85], [1.9, 0.85], [2.2, 0]]},
        {"alvo": "rosto:surprised", "chaves": [[0, 0], [0.25, 0.45], [1.9, 0.45], [2.2, 0]]},
        {"alvo": "cabeca_roll", "chaves": [[0, 0], [0.25, -16], [1.9, -16], [2.2, 0]]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.25, 6], [1.9, 6], [2.2, 0]]}]}
    p["cara_de_espanto"] = {"descricao": "Olhos arregalados e boca aberta, de susto.", "duracao": 1.8, "faixas": [
        {"alvo": "rosto:surprised", "chaves": [[0, 0], [0.15, 1.0], [1.5, 1.0], [1.8, 0]]},
        {"alvo": "rosto:oh", "chaves": [[0, 0], [0.15, 0.7], [1.5, 0.7], [1.8, 0]]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.15, -8], [1.5, -8], [1.8, 0]]},
        {"alvo": "corpo_z", "chaves": [[0, 0], [0.15, -0.05], [1.5, -0.05], [1.8, 0]]}]}
    p["cara_de_sono"] = {"descricao": "Olhos pesados e cabeça caindo, de sono.", "duracao": 2.6, "faixas": [
        {"alvo": "rosto:blink", "chaves": [[0, 0], [0.5, 0.7], [2.1, 0.7], [2.6, 0]]},
        {"alvo": "rosto:relaxed", "chaves": [[0, 0], [0.5, 0.6], [2.1, 0.6], [2.6, 0]]},
        {"alvo": "rosto:aa", "chaves": [[0, 0], [0.8, 0.0], [1.2, 0.5], [1.6, 0.0], [2.6, 0]]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.7, 14], [2.0, 14], [2.6, 0]]}]}
    p["cara_brava"] = {"descricao": "Cara fechada de brava (de brincadeira).", "duracao": 1.9, "faixas": [
        {"alvo": "rosto:angry", "chaves": [[0, 0], [0.2, 0.9], [1.6, 0.9], [1.9, 0]]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.2, 8], [1.6, 8], [1.9, 0]]},
        {"alvo": "corpo_z", "chaves": [[0, 0], [0.2, 0.04], [1.6, 0.04], [1.9, 0]]}]}
    p["aproximar"] = {"descricao": "Aproxima a câmera (zoom 1,6x). Fica assim até 'camera_normal'.", "duracao": 1.0, "faixas": [
        {"alvo": "camera_zoom", "chaves": [[0, None], [1.0, 1.6]]}]}
    p["afastar"] = {"descricao": "Afasta a câmera (zoom 0,7x) para mostrar mais do corpo. Fica assim até 'camera_normal'.", "duracao": 1.0, "faixas": [
        {"alvo": "camera_zoom", "chaves": [[0, None], [1.0, 0.7]]}]}
    p["camera_normal"] = {"descricao": "Volta a câmera para o enquadramento normal.", "duracao": 0.8, "faixas": [
        {"alvo": "camera_zoom", "chaves": [[0, None], [0.8, 1.0]]}, {"alvo": "camera_x", "chaves": [[0, None], [0.8, 0]]},
        {"alvo": "camera_y", "chaves": [[0, None], [0.8, 0]]}]}
    p["passear"] = {"descricao": "Anda com a janela pela tela, balançando como se tivesse pernas (vai para a esquerda).", "duracao": 3.4, "faixas": [
        {"alvo": "janela_x", "chaves": [[0, None], [3.2, -520]]},
        {"alvo": "corpo_y", "chaves": _amostras(lambda t: 0.03 * abs(math.sin(math.pi * t / 0.5)) * min(1.0, t / 0.2, (3.4 - t) / 0.2) if 0 <= t <= 3.4 else 0.0, 3.4, 0.1)},
        {"alvo": "cabeca_roll", "chaves": _amostras(lambda t: 4 * math.sin(s2 * t / 1.0) * min(1.0, t / 0.3, (3.4 - t) / 0.3), 3.4, 0.1)}]}
    p["voltar_ao_canto"] = {"descricao": "Volta com a janela para o cantinho de sempre.", "duracao": 3.0, "faixas": [
        {"alvo": "janela_x", "chaves": [[0, None], [2.8, 0]]}, {"alvo": "janela_y", "chaves": [[0, None], [2.8, 0]]},
        {"alvo": "corpo_y", "chaves": _amostras(lambda t: 0.03 * abs(math.sin(math.pi * t / 0.5)) * min(1.0, t / 0.2, (3.0 - t) / 0.2) if 0 <= t <= 3.0 else 0.0, 3.0, 0.1)}]}
    p["pulo_longe"] = {"descricao": "Pula em arco até o lado esquerdo da tela.", "duracao": 1.4, "faixas": [
        {"alvo": "janela_x", "chaves": [[0, None], [1.3, -380]]},
        {"alvo": "janela_dy", "chaves": [[0, 0], [0.7, -110], [1.4, 0]]},
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.15, -0.03], [0.55, 0.22], [1.2, 0], [1.4, 0]]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.4, 0.6], [1.1, 0.6], [1.4, 0]]}]}
    # ---------------- v1.7 (T11): mais movimentos prontos, todos só dados
    p["aceno_grande"] = {"descricao": "Aceno grande com o braço direito para cima, sorrindo.", "duracao": 1.8, "mao": "aberta", "faixas": [
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.3, 0.02], [1.5, 0.02], [1.8, 0]]},
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.3, _BRACO_ALTO),
                                         _braco(0.55, [0.6, 0.85, 0.1, 0.85, 0.4, 0.2]),
                                         _braco(0.85, _BRACO_ALTO), _braco(1.15, [0.6, 0.85, 0.1, 0.85, 0.4, 0.2]),
                                         _braco(1.45, _BRACO_ALTO), _braco(1.8, _BRACO_BAIXO, 0)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.3, 0.8], [1.5, 0.8], [1.8, 0]]},
        {"alvo": "cabeca_roll", "chaves": [[0, 0], [0.3, -5], [1.5, -5], [1.8, 0]]}]}
    p["tchau"] = {"descricao": "Dá tchau com a mão, de leve.", "duracao": 2.2, "mao": "aberta", "faixas": [
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.4, _BRACO_ALTO),
                                         _braco(0.7, [0.6, 0.85, 0.1, 0.8, 0.45, 0.2]),
                                         _braco(1.0, _BRACO_ALTO), _braco(1.3, [0.6, 0.85, 0.1, 0.8, 0.45, 0.2]),
                                         _braco(1.6, _BRACO_ALTO), _braco(2.2, _BRACO_BAIXO, 0)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.4, 0.6], [1.9, 0.6], [2.2, 0]]}]}
    p["pensando"] = {"descricao": "Mão no queixo, olhando para cima — pensando.", "duracao": 3.0, "mao": "pensar", "faixas": [
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0),
                                         _braco(0.6, [0.15, 0.45, 0.55, 0.25, 0.95, 0.30]),
                                         _braco(2.4, [0.15, 0.45, 0.55, 0.25, 0.95, 0.30]), _braco(3.0, _BRACO_BAIXO, 0)]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.6, -10], [2.4, -10], [3.0, 0]]},
        {"alvo": "cabeca_roll", "chaves": [[0, 0], [0.6, 8], [2.4, 8], [3.0, 0]]},
        {"alvo": "rosto:relaxed", "chaves": [[0, 0], [0.6, 0.6], [2.4, 0.6], [3.0, 0]]}]}
    p["reverencia"] = {"descricao": "Uma reverência educada, de cabeça baixa.", "duracao": 1.9, "mao": "relaxada", "faixas": [
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.5, -0.06], [1.4, -0.06], [1.9, 0]]},
        {"alvo": "corpo_z", "chaves": [[0, 0], [0.5, -0.05], [1.4, -0.05], [1.9, 0]]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.5, 24], [1.4, 24], [1.9, 0]]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.5, 0.4], [1.4, 0.4], [1.9, 0]]}]}
    p["cansada"] = {"descricao": "Ombros caídos, olhos pesados — cansada.", "duracao": 3.2, "faixas": [
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.6, -0.03], [2.6, -0.03], [3.2, 0]]},
        {"alvo": "cabeca_pitch", "chaves": [[0, 0], [0.6, 14], [2.6, 14], [3.2, 0]]},
        {"alvo": "rosto:blink", "chaves": [[0, 0], [0.6, 0.75], [2.6, 0.75], [3.2, 0]]},
        {"alvo": "rosto:relaxed", "chaves": [[0, 0], [0.6, 0.5], [2.6, 0.5], [3.2, 0]]},
        {"alvo": "cabeca_roll", "chaves": [[0, 0], [1.2, 6], [2.2, -4], [3.2, 0]]}]}
    p["animada"] = {"descricao": "Pulinhos curtos no lugar, de braços abertos, toda animada.", "duracao": 2.0, "mao": "aberta", "faixas": [
        {"alvo": "corpo_y", "chaves": [[0, 0], [0.25, 0.08], [0.5, 0], [0.75, 0.08], [1.0, 0], [1.25, 0.08], [1.5, 0], [2.0, 0]]},
        {"alvo": "braco_dir", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.3, _BRACO_ABERTO), _braco(1.6, _BRACO_ABERTO), _braco(2.0, _BRACO_BAIXO, 0)]},
        {"alvo": "braco_esq", "chaves": [_braco(0, _BRACO_BAIXO, 0), _braco(0.3, _BRACO_ABERTO), _braco(1.6, _BRACO_ABERTO), _braco(2.0, _BRACO_BAIXO, 0)]},
        {"alvo": "rosto:happy", "chaves": [[0, 0], [0.3, 0.9], [1.7, 0.9], [2.0, 0]]}]}

    out = {}
    for nome, d in p.items():
        clipe, avisos, erro = validar(dict(d, nome=nome))
        assert clipe is not None, f"movimento pronto '{nome}' inválido: {erro}"
        out[nome] = dict(clipe, autor="zenith")
    return out


PRONTOS = _prontos()
NOMES_PRONTOS = frozenset(PRONTOS)


# ---------------------------------------------------------------------------------------------------------------------
# v1.7 (T11) — ritmo (BPM), encadear movimentos e a escala ("mais devagar / mais rápido")
# ---------------------------------------------------------------------------------------------------------------------
ESTILOS_DANCA = ("animada", "suave", "robotica")
BPM_MIN, BPM_MAX = 50, 200


def gerar_danca(bpm: int = 100, estilo: str = "animada"):
    """Dança NO RITMO pedido: gera o clipe (dados) a partir do BPM. Devolve (clipe|None, erro)."""
    try:
        bpm = int(round(float(bpm)))
    except (TypeError, ValueError):
        return None, "BPM inválido (use um número, ex.: 120)"
    if bpm < BPM_MIN or bpm > BPM_MAX:
        return None, f"BPM fora da faixa: use de {BPM_MIN} a {BPM_MAX}"
    estilo = str(estilo or "animada").strip().lower()
    if estilo not in ESTILOS_DANCA:
        return None, f"estilo desconhecido (use: {', '.join(ESTILOS_DANCA)})"
    batida = 60.0 / bpm
    dur = round(min(DURACAO_MAX, batida * 8), 3)          # dois compassos de 4 tempos
    amp = {"animada": 1.0, "suave": 0.6, "robotica": 0.8}[estilo]
    repetir = 1 if dur * 2 > TEMPO_TOTAL_MAX else 2
    s2 = 2 * math.pi
    faixas = [
        {"alvo": "corpo_x", "chaves": _amostras(lambda t: 0.07 * amp * math.sin(s2 * t / (batida * 2)), dur, round(batida / 4, 3))},
        {"alvo": "corpo_y", "chaves": _amostras(lambda t: 0.04 * amp * abs(math.sin(math.pi * t / batida)), dur, round(batida / 4, 3))},
        {"alvo": "corpo_giro", "chaves": _amostras(lambda t: 18 * amp * math.sin(s2 * t / (batida * 2)), dur, round(batida / 4, 3))},
        {"alvo": "corpo_roll", "chaves": _amostras(lambda t: 5 * amp * math.sin(s2 * t / (batida * 2) + math.pi / 2), dur, round(batida / 4, 3))},
        {"alvo": "janela_dx", "chaves": _amostras(lambda t: 16 * amp * math.sin(s2 * t / (batida * 2)), dur, round(batida / 4, 3))},
        {"alvo": "rosto:happy", "chaves": [[0, 0.6], [dur, 0.6]]},
    ]
    if estilo == "robotica":
        faixas.append({"alvo": "cabeca_yaw", "chaves": _amostras(
            lambda t: 14 * math.copysign(1.0, math.sin(s2 * t / (batida * 2))) if abs(math.sin(s2 * t / (batida * 2))) > 0.2 else 0.0,
            dur, round(batida / 4, 3))})
    else:
        faixas.append({"alvo": "cabeca_roll", "chaves": _amostras(
            lambda t: 8 * amp * math.sin(s2 * t / batida), dur, round(batida / 4, 3))})
    faixas.append({"alvo": "braco_dir", "chaves": [_braco(i * batida / 2, _BRACO_ALTO if i % 2 == 0 else _BRACO_ABERTO,
                                                         0.6 + 0.4 * amp) for i in range(max(2, int(dur / (batida / 2)) + 1))]})
    faixas.append({"alvo": "braco_esq", "chaves": [_braco(i * batida / 2, _BRACO_ABERTO if i % 2 == 0 else _BRACO_ALTO,
                                                        0.6 + 0.4 * amp) for i in range(max(2, int(dur / (batida / 2)) + 1))]})
    clipe, avisos, erro = validar({"nome": f"danca_{estilo}_{bpm}", "descricao": f"Dança {estilo} a {bpm} BPM",
                                   "duracao": dur, "repetir": repetir, "mao": "aberta", "faixas": faixas})
    if erro:
        return None, erro
    return dict(clipe, autor="zenith"), ""


def escala_do_pedido(texto: str) -> float:
    """"faz isso mais devagar" -> 1.4 · "mais rápido" -> 0.75 · "bem devagar" -> 1.8 · sem pedido -> 1.0

    `escala` é o multiplicador de TEMPO do `movement_play` (1.0 = ritmo normal; >1 mais devagar)."""
    t = _sem_acento(str(texto or "")).lower()
    if re.search(r"\bbem (mais )?(devagar|lento|vagaroso)\b|\bmuito (mais )?(devagar|lento)\b", t):
        return 1.8
    if re.search(r"\bmais (devagar|lento|vagaroso)\b|\bdevagar\b|\blentamente\b|\bcalma\b", t):
        return 1.4
    if re.search(r"\bbem (mais )?(rapido|depressa)\b|\bmuito (mais )?(rapido|depressa)\b", t):
        return 0.6
    if re.search(r"\bmais (rapido|depressa)\b|\brapido\b|\bdepressa\b|\bacelera\b", t):
        return 0.75
    return 1.0


def variante(clipe: dict, escala: float):
    """Devolve o MESMO movimento com os tempos multiplicados (para quando o Corpo não honrar `escala`)."""
    try:
        e = float(escala)
    except (TypeError, ValueError):
        return None
    if e <= 0 or abs(e - 1.0) < 1e-6:
        return clipe
    dur = min(DURACAO_MAX / max(1, clipe.get("repetir", 1)), clipe["duracao"] * e)
    faixas = [{"alvo": f["alvo"], "chaves": [[min(dur, c[0] * e)] + list(c[1:]) for c in f["chaves"]]}
              for f in clipe["faixas"]]
    novo, _av, erro = validar({"nome": clipe["nome"], "descricao": clipe.get("descricao", ""),
                               "duracao": dur, "repetir": clipe.get("repetir", 1),
                               "mao": clipe.get("mao"), "suave": clipe.get("suave", True), "faixas": faixas})
    return None if erro else dict(novo, autor=clipe.get("autor", "zenith"))


def encadear(nomes, escala: float = 1.0, disponiveis=None) -> list:
    """"faz uma careta, pula e dança" -> [{"nome": "careta", "escala": 1.0}, ...] (até FILA_MAX).

    Só entram movimentos que existem (`disponiveis` = nomes da biblioteca); o resto é ignorado.
    A fila do Corpo é de 4 — mais do que isso não tocaria, então não prometemos."""
    if isinstance(nomes, str):
        nomes = [nomes]
    validos = set(disponiveis if disponiveis is not None else NOMES_PRONTOS)
    try:
        e = max(0.3, min(3.0, float(escala)))
    except (TypeError, ValueError):
        e = 1.0
    saida = []
    for n in nomes or []:
        nome = str(n or "").strip().lower()
        if nome in validos and nome not in [s["nome"] for s in saida]:
            saida.append({"nome": nome, "escala": e})
        if len(saida) >= FILA_MAX:
            break
    return saida


# ---------------------------------------------------------------------------------------------------------------------
# biblioteca (movimentos criados ficam em config/movimentos/<nome>.json)
# ---------------------------------------------------------------------------------------------------------------------
def pasta_padrao() -> Path:
    from brain.zenith_settings import CONFIG_DIR
    return Path(CONFIG_DIR) / "movimentos"


def carregar_criados(pasta=None) -> dict:
    pasta = Path(pasta) if pasta else pasta_padrao()
    out = {}
    try:
        for arq in sorted(pasta.glob("*.json"))[:BIBLIOTECA_MAX]:
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            clipe, _av, erro = validar(dados, nome=arq.stem)
            if clipe and clipe["nome"] not in PRONTOS:
                out[clipe["nome"]] = dict(clipe, autor=str(dados.get("autor", "ia"))[:12])
    except OSError:
        pass
    return out


def biblioteca(pasta=None) -> dict:
    """Prontos + criados (um criado nunca substitui um pronto)."""
    lib = dict(carregar_criados(pasta))
    lib.update(PRONTOS)
    return lib


def salvar(dados, pasta=None, autor="ia"):
    """Valida e guarda um movimento novo. Devolve (clipe|None, avisos, erro)."""
    clipe, avisos, erro = validar(dados)
    if erro:
        return None, avisos, erro
    if clipe["nome"] in PRONTOS:
        return None, avisos, f"'{clipe['nome']}' é um movimento pronto do Zenith; escolha outro nome"
    pasta = Path(pasta) if pasta else pasta_padrao()
    pasta.mkdir(parents=True, exist_ok=True)
    existentes = list(pasta.glob("*.json"))
    if len(existentes) >= BIBLIOTECA_MAX and not (pasta / f"{clipe['nome']}.json").exists():
        return None, avisos, f"a biblioteca já tem {BIBLIOTECA_MAX} movimentos; apague algum com /movimentos apagar <nome>"
    gravar = dict(clipe, autor=autor)
    (pasta / f"{clipe['nome']}.json").write_text(json.dumps(gravar, ensure_ascii=False, indent=1), encoding="utf-8")
    return gravar, avisos, ""


def apagar(nome, pasta=None) -> bool:
    nome = str(nome or "").strip().lower()
    if not NOME_OK.match(nome) or nome in PRONTOS:
        return False
    alvo = (Path(pasta) if pasta else pasta_padrao()) / f"{nome}.json"
    try:
        alvo.unlink()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------------------------------------------------
# a IA cria movimentos:  <criar_movimento>{...json...}</criar_movimento>
# ---------------------------------------------------------------------------------------------------------------------
_RX_CRIAR = re.compile(r"<criar_movimento>(.*?)</criar_movimento>", re.S | re.I)


def extrair_criacoes(texto: str):
    """Devolve (texto_sem_as_etiquetas, [json_bruto, ...])."""
    brutos = [m.group(1).strip() for m in _RX_CRIAR.finditer(texto or "")][:3]
    return _RX_CRIAR.sub("", texto or "").strip(), brutos


def criar_de_texto(bruto: str, pasta=None):
    """Lê o JSON que a IA escreveu, valida e guarda. Devolve (clipe|None, avisos, erro)."""
    limpo = re.sub(r"^```(?:json)?|```$", "", bruto.strip(), flags=re.M).strip()
    try:
        dados = json.loads(limpo)
    except ValueError as e:
        return None, [], f"o JSON do movimento não abriu ({e})"
    return salvar(dados, pasta)


# ---------------------------------------------------------------------------------------------------------------------
# "o que ela diz que fez, acontece" e "o que o usuário pede, acontece"
# ---------------------------------------------------------------------------------------------------------------------
_PEDIDOS = (
    ("mortal_frente", r"\bmortal (de|para|pra) frente\b|\bfrontflip\b"),
    ("mortal", r"\bmortal\b|\bsalto mortal\b|\bbackflip\b|\bmortal de costas\b|\bda um mortal\b|\bfaz um mortal\b|\bacrobacia\b"),
    ("pulo_alto", r"\bpulo alto\b|\bpula alto\b|\bpule alto\b|\bsalto alto\b|\bpulo bem alto\b"),
    ("estrela", r"\bestrela\b|\bestrelinha\b|\bcartwheel\b|\bvirar estrela\b"),
    ("pulo_longe", r"\bpul\w* (pra|para) (la|o canto|outro lado|o lado)"),
    ("pulo_duplo", r"\bpulo duplo\b|\bdois pulos\b|\bpula duas vezes\b"),
    ("pulo", r"\bpulo\b|\bpulinho\b|\bpula\b|\bpule\b|\bpular\b|\bsalta\b|\bsaltar\b|\bpula pula\b"),
    ("dancar", r"\bdanca\b|\bdance\b|\bdancar\b|\bdancando\b|\bbaila\b|\bbailar\b|\bdancinha\b"),
    ("aceno_grande", r"\bacen\w*\b|\bda (um )?tchau\b"),
    ("tchau", r"\btchau\b|\badeus\b|\bate logo\b"),
    ("reverencia", r"\breverencia\b|\bmesura\b|\bfaz uma curva\b"),
    ("pensando", r"\bmao no queixo\b|\bfinge (que )?(esta )?pensando\b|\bpensativ\w+\b"),
    ("cansada", r"\bfinge (que )?(esta )?cansad\w+\b|\bfaz (uma )?cara de cansad\w+\b|\bboceja\w*\b"),
    ("animada", r"\bfaz (uma )?cara de animad\w+\b|\bfinge (que )?(esta )?animad\w+\b"),
    ("careta", r"\bcareta\b"),
    ("cara_de_espanto", r"\bcara de (espanto|susto|surpresa)\b|\bfaz (um )?susto\b"),
    ("cara_de_sono", r"\bcara de sono\b|\bfinge que esta com sono\b"),
    ("cara_brava", r"\bcara de brava\b|\bcara de bravo\b|\bfica brava\b|\bcara feia\b"),
    ("girar", r"\bgira\b|\bgirar\b|\bgire\b|\bda uma volta\b|\bgiro\b"),
    ("camera_normal", r"\b(camera|enquadramento|zoom)\b.{0,25}\b(normal|padrao|original)\b|\bvolta (a|o) (camera|zoom|enquadramento)\b"),
    ("aproximar", r"\baproxim\w*.{0,25}\b(camera|perto|zoom)\b|\bchega mais perto\b|\bchegar mais perto\b|\bzoom in\b|\bmais perto da camera\b"),
    ("afastar", r"\bafast\w*.{0,25}\b(camera|longe|zoom)\b|\bmais longe\b|\bzoom out\b|\bse afasta\b|\bafasta a camera\b"),
    ("voltar_ao_canto", r"\bvolta (pro|para o|pra) (canto|seu lugar)\b|\bvolta pro canto\b|\bvolta pra ca\b"),
    ("passear", r"\bpasseia\b|\bpassear\b|\banda pela tela\b|\bcaminha\b|\bande pela tela\b|\bvai pro canto\b|\bvai para o canto\b|\banda ai\b"),
)
_AFIRMACOES = (
    ("mortal_frente", r"\bdei (um |o )?mortal (de|para|pra) frente\b|\bfiz (um |o )?mortal (de|para|pra) frente\b"),
    ("mortal", r"\bdei (um |o )?mortal\b|\bfiz (um |o )?mortal\b|\bdando (um )?mortal\b|\bbackflip\b"),
    ("pulo_alto", r"\bpulei (bem )?alto\b|\bdei (um |o )?pulo alto\b|\bsaltei alto\b"),
    ("estrela", r"\bfiz (uma |a )?estrela\b|\bfiz (uma |a )?estrelinha\b|\bvirei estrela\b"),
    ("pulo_duplo", r"\bpulei duas vezes\b|\bdei dois pulos\b"),
    ("pulo", r"\bpulei\b|\bdei (um |o )?pulo\b|\bdei (um )?pulinho\b|\bdei pulinhos\b|\bestou pulando\b|\bdando um pulo\b"),
    ("dancar", r"\bdancei\b|\bestou dancando\b|\bdancando um pouco\b|\bfiz uma dancinha\b|\bfiz uma danca\b"),
    ("careta", r"\bfiz (a |uma )?careta\b|\bfazendo (a |uma )?careta\b"),
    ("aceno_grande", r"\bacenei\b|\bdei (um )?tchau\b"),
    ("tchau", r"\bdei tchau\b|\bmandei um tchau\b"),
    ("reverencia", r"\bfiz uma reverencia\b|\bme curvei\b"),
    ("pensando", r"\bfiquei pensando\b|\bpousei a mao no queixo\b"),
    ("girar", r"\bgirei\b|\bdei uma volta\b"),
    ("aproximar", r"\bme aproximei\b|\baproximei a camera\b|\bcheguei mais perto\b|\bchegando mais perto\b"),
    ("afastar", r"\bme afastei\b|\bafastei a camera\b"),
)


def _norm(texto: str) -> str:
    t = re.sub(r"```.*?```", " ", str(texto or ""), flags=re.S)
    t = re.sub(r"pulo do gato|salto de linha|pula linha", " ", t, flags=re.I)        # expressões que não são pedido de pulo
    return re.sub(r"\s+", " ", _sem_acento(t)).strip()


def _casar(tabela, texto, biblioteca_nomes):
    achados = []
    for nome, rx in tabela:
        if nome in biblioteca_nomes and re.search(rx, texto):
            # variantes específicas ganham do simples
            if nome == "pulo" and any(x in achados for x in ("pulo_duplo", "pulo_longe", "pulo_alto")):
                continue
            if nome == "mortal" and "mortal_frente" in achados:
                continue
            achados.append(nome)
    return achados


def inferir_do_pedido(texto_usuario: str, nomes=None) -> list:
    """Movimentos que o usuário PEDIU numa mensagem curta ('faz uma careta e dá um pulo' -> ['pulo', 'careta'] na ordem do texto)."""
    t = _norm(texto_usuario)
    if not t or len(t) > 180:
        return []
    nomes = set(nomes or NOMES_PRONTOS)
    achados = _casar(_PEDIDOS, t, nomes)
    pos = {}
    for nome, rx in _PEDIDOS:
        m = re.search(rx, t)
        if m and nome in achados:
            pos[nome] = m.start()
    return sorted(achados, key=lambda n: pos.get(n, 0))[:FILA_MAX]


def inferir_do_que_ela_disse(resposta: str, nomes=None) -> list:
    """Movimentos que a IA AFIRMOU ter feito ('dei o pulo', 'fiz a careta'). Serve para o que ela diz ser verdade."""
    t = _norm(resposta)
    if not t:
        return []
    return _casar(_AFIRMACOES, t, set(nomes or NOMES_PRONTOS))[:FILA_MAX]


def descricao_para_prompt(pasta=None) -> str:
    """Texto curto para a IA saber o que existe (entra no cartão 'O corpo' da Bíblia)."""
    lib = biblioteca(pasta)
    prontos = ", ".join(sorted(n for n, c in lib.items() if c.get("autor") == "zenith"))
    criados = ", ".join(sorted(n for n, c in lib.items() if c.get("autor") != "zenith")) or "(nenhum ainda)"
    return (f"Movimentos prontos: {prontos}. Criados por você ou pelo usuário: {criados}. "
            "Para fazer um: <corpo>movimento:pulo</corpo>. NUNCA diga que pulou/dançou/fez careta sem usar a etiqueta. "
            "Se o movimento que o usuário quer não existe, crie com <criar_movimento>{json}</criar_movimento> (formato no cartão) "
            "ou diga honestamente que ainda não existe.")


FORMATO_CRIAR = (
    '<criar_movimento>{"nome":"comemoracao_dupla","descricao":"...","duracao":1.5,"repetir":1,"mao":"aberta","faixas":['
    '{"alvo":"corpo_y","chaves":[[0,0],[0.4,0.1],[1.5,0]]},'
    '{"alvo":"rosto:happy","chaves":[[0,0],[0.3,0.8],[1.5,0]]},'
    '{"alvo":"braco_dir","chaves":[[0,0.1,-0.95,0.05,0.05,-0.95,0.1,0],[0.5,0.7,0.6,0.2,0.4,0.85,0.2,1],[1.5,0.1,-0.95,0.05,0.05,-0.95,0.1,0]]}]}</criar_movimento>')
