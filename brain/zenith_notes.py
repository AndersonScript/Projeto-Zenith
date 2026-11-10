"""
Zenith — Bloco de notas rápido (observações de laboratório, ideias, etc.).

Separado do chat e da memória de longo prazo da Zenith: aqui só entra o que
você mandar de propósito (/nota ..., ou /nota_voz e falar). Cada nota leva
data/hora. Dá pra listar (/notas), exportar em Markdown (/exportar_notas) e,
desde o v18, marcar com #tags (ex.: "/nota #experimento3 tensão 4,98 V"),
filtrar por tag (/notas #experimento3) e exportar em CSV pro Excel.
Nunca levanta exceção pra quem chamou.
"""
import csv
import datetime
import json
import re
from pathlib import Path

# #tag: letras (com acento), números, _ e -, até 30 caracteres. Não pega "#" solto
# nem o "#" no meio de uma palavra/URL (ex.: "pagina#secao").
_RE_TAG = re.compile(r"(?<![\w/#])#([\wÀ-ÿ\-]{1,30})", re.UNICODE)


def extrair_tags(texto: str) -> list:
    """['experimento3', 'lab'] — minúsculas, sem repetir, na ordem em que aparecem."""
    vistas, tags = set(), []
    for m in _RE_TAG.finditer(str(texto or "")):
        t = m.group(1).lower().strip("-_")
        if t and t not in vistas:
            vistas.add(t)
            tags.append(t)
    return tags


def normalizar_tag(tag: str) -> str:
    return str(tag or "").strip().lstrip("#").lower()


def _caminho_padrao() -> Path:
    from brain.zenith_settings import CONFIG_DIR
    return Path(CONFIG_DIR) / "zenith_notas.jsonl"


def adicionar(texto: str, origem: str = "texto", caminho=None) -> bool:
    texto = str(texto or "").strip()
    if not texto:
        return False
    try:
        p = Path(caminho) if caminho else _caminho_padrao()
        p.parent.mkdir(parents=True, exist_ok=True)
        nota = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "texto": texto, "origem": origem}
        tags = extrair_tags(texto)
        if tags:
            nota["tags"] = tags
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(nota, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"[Zenith/Notas] não consegui gravar: {e}")
        return False


def listar(n: int = 10, caminho=None, tag: str = "") -> list:
    try:
        p = Path(caminho) if caminho else _caminho_padrao()
        if not p.exists():
            return []
        notas = []
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        notas.append(json.loads(linha))
                    except ValueError:
                        continue
        alvo = normalizar_tag(tag)
        if alvo:
            notas = [x for x in notas if alvo in (x.get("tags") or extrair_tags(x.get("texto", "")))]
        return notas[-max(1, int(n)):]
    except Exception:
        return []


def tags_usadas(caminho=None) -> list:
    """[(tag, quantas_notas)] da mais usada pra menos usada."""
    contagem = {}
    for x in listar(1_000_000, caminho):
        for t in (x.get("tags") or extrair_tags(x.get("texto", ""))):
            contagem[t] = contagem.get(t, 0) + 1
    return sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))


def formatar(n: int = 10, caminho=None, tag: str = "") -> str:
    notas = listar(n, caminho, tag=tag)
    if not notas:
        if normalizar_tag(tag):
            return f"📝 Nenhuma nota com #{normalizar_tag(tag)}. Veja as tags em uso com /tags."
        return "📝 Nenhuma nota ainda. Use /nota <texto> (ou /nota_voz e fale)."
    de_tag = f" com #{normalizar_tag(tag)}" if normalizar_tag(tag) else ""
    linhas = [f"📝 Últimas {len(notas)} notas{de_tag}:"]
    for x in notas:
        quando = str(x.get("ts", ""))[:19].replace("T", " ")
        marca = "🎙️" if x.get("origem") == "voz" else "•"
        linhas.append(f"{marca} {quando} — {x.get('texto', '')}")
    return "\n".join(linhas)


def exportar_markdown(destino, caminho=None) -> int:
    notas = listar(100000, caminho)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    linhas = ["# Zenith — notas", ""]
    dia = None
    for x in notas:
        d, _, h = str(x.get("ts", "")).partition("T")
        if d != dia:
            dia = d
            linhas += ["", f"## {d}", ""]
        origem = " 🎙️" if x.get("origem") == "voz" else ""
        linhas.append(f"- **{h[:5]}**{origem} — {x.get('texto', '')}")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return len(notas)


def _celula_segura(valor) -> str:
    """Evita 'injeção de fórmula' no Excel: célula que começa com = + - @ vira texto."""
    v = str(valor if valor is not None else "")
    return ("'" + v) if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def exportar_csv(destino, caminho=None, tag: str = "") -> int:
    """CSV pro Excel em português: separador ';' (o padrão do Excel pt-BR) e UTF-8 com
    BOM (senão os acentos quebram). Colunas: data;hora;origem;tags;texto."""
    notas = listar(1_000_000, caminho, tag=tag)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(["data", "hora", "origem", "tags", "texto"])
        for x in notas:
            d, _, h = str(x.get("ts", "")).partition("T")
            tags = x.get("tags") or extrair_tags(x.get("texto", ""))
            w.writerow([d, h[:8], x.get("origem", "texto"), " ".join("#" + t for t in tags),
                        _celula_segura(x.get("texto", ""))])
    return len(notas)
