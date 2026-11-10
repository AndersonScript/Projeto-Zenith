"""
Zenith — busca na web e de imagens SEM chave de API (v21).

Pedido do Anderson: "deixa ela pesquisar imagens ou qualquer outra coisa sem ser por API, tipo
a ideia da Tavily — não existe outro caminho?". Existe: o mesmo que uma pessoa faz no navegador.
Aqui o Zenith pede a página de resultados (como um navegador), e lê o que vem — sem cadastro,
sem chave, sem cobrança. Só `requests` + biblioteca padrão (nenhuma dependência nova).

TEXTO   : 1) DuckDuckGo (versão HTML)  2) Bing  3) Wikipédia (API pública oficial, sem chave)
IMAGENS : 1) Bing Imagens  2) Wikimedia Commons (imagens livres)  3) Openverse (imagens livres)

Honestidade sobre o que isto É e NÃO É:
  * Páginas de resultado de buscadores não são uma "API" com contrato: o HTML pode mudar ou o
    buscador pode pedir CAPTCHA se houver muitas buscas seguidas. Por isso são 3 fontes em
    sequência — se uma falha, a próxima assume — e a mensagem de erro diz o que aconteceu.
  * A Wikipédia/Commons/Openverse têm API pública oficial: são a rede de segurança.
  * Se o usuário TEM uma chave da Tavily, ela continua sendo usada primeiro (opcional).

Segurança do download de imagem (a IA escolhe a URL): só http/https, bloqueia endereço
local/privado (SSRF), limite de tamanho, confere que o arquivo é MESMO uma imagem e nunca
executa nada.

Nenhuma função deste módulo levanta exceção para quem chama; o retorno diz `ok` e `erros`.
"""
import base64
import html as _html
import ipaddress
import json
import os
import re
import socket
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

try:                                    # pragma: no cover — import defensivo
    import requests
except Exception:                       # pragma: no cover
    requests = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
CABECALHOS = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
              "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
TEMPO = 12
TETO_BYTES_IMAGEM = 8 * 1024 * 1024
EXT_POR_MIME = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                "image/gif": ".gif", "image/bmp": ".bmp"}


# ------------------------------------------------------------------ utilidades
def _limpar(texto: str, limite: int = 400) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = _html.unescape(texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:limite] + ("..." if len(texto) > limite else "")


def _desembrulhar_ddg(href: str) -> str:
    """O DuckDuckGo embrulha o link: //duckduckgo.com/l/?uddg=<url codificada>&rut=..."""
    href = _html.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href or href.startswith("/l/"):
        q = parse_qs(urlparse(href).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    return href


def _desembrulhar_bing(href: str) -> str:
    """O Bing às vezes embrulha: https://www.bing.com/ck/a?...&u=a1<base64 da url>"""
    href = _html.unescape(href or "")
    if "bing.com/ck/a" in href:
        q = parse_qs(urlparse(href).query)
        u = (q.get("u") or [""])[0]
        if u.startswith("a1"):
            b = u[2:]
            b += "=" * (-len(b) % 4)
            try:
                return base64.urlsafe_b64decode(b).decode("utf-8", "replace")
            except Exception:
                return href
    return href


def _http_url(u: str) -> bool:
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))


# ------------------------------------------------------------------ parsers (HTML -> dados)
class _Ancoras(HTMLParser):
    """Coleta cada <a>: atributos + texto interno (sem aninhar)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.itens = []
        self._atual = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._atual = {"attrs": dict(attrs), "texto": []}

    def handle_endtag(self, tag):
        if tag == "a" and self._atual is not None:
            self._atual["texto"] = "".join(self._atual["texto"])
            self.itens.append(self._atual)
            self._atual = None

    def handle_data(self, data):
        if self._atual is not None:
            self._atual["texto"].append(data)


def parse_ddg_html(texto_html: str, maximo: int = 8) -> list:
    """Resultados do html.duckduckgo.com/html: <a class="result__a"> (título+link) e
    <a class="result__snippet"> (trecho), na mesma ordem."""
    p = _Ancoras()
    try:
        p.feed(texto_html or "")
    except Exception:
        pass
    saida, pendente = [], None
    for a in p.itens:
        classes = (a["attrs"].get("class") or "")
        if "result__a" in classes:
            url = _desembrulhar_ddg(a["attrs"].get("href", ""))
            if _http_url(url) and "duckduckgo.com/y.js" not in url:       # y.js = anúncio
                pendente = {"titulo": _limpar(a["texto"], 160), "url": url, "trecho": ""}
                saida.append(pendente)
            else:
                pendente = None
        elif "result__snippet" in classes and pendente is not None and not pendente["trecho"]:
            pendente["trecho"] = _limpar(a["texto"])
        if len(saida) >= maximo:
            break
    return saida


def parse_bing_html(texto_html: str, maximo: int = 8) -> list:
    """Resultados do Bing: blocos <li class="b_algo"> com <h2><a href> e um <p> de trecho."""
    saida = []
    for bloco in re.split(r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"', texto_html or "")[1:]:
        bloco = bloco.split("</li>")[0]
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', bloco, re.S)
        if not m:
            continue
        url = _desembrulhar_bing(m.group(1))
        if not _http_url(url):
            continue
        t = re.search(r"<p[^>]*>(.*?)</p>", bloco, re.S)
        saida.append({"titulo": _limpar(m.group(2), 160), "url": url, "trecho": _limpar(t.group(1)) if t else ""})
        if len(saida) >= maximo:
            break
    return saida


def parse_bing_imagens(texto_html: str, maximo: int = 8) -> list:
    """Bing Imagens: cada <a class="iusc" m='{"murl":...,"turl":...,"t":...}'> (JSON no atributo m)."""
    saida = []
    # O Bing escreve o JSON no atributo m="{&quot;murl&quot;:...}" (aspas duplas + entidades); aceita
    # também aspas simples, por garantia.
    for m in re.finditer(r'<a[^>]+class="[^"]*\biusc\b[^"]*"[^>]*?\sm=(["\'])(.*?)\1', texto_html or "", re.S):
        try:
            dados = json.loads(_html.unescape(m.group(2)))
        except ValueError:
            continue
        url = dados.get("murl") or ""
        if not _http_url(url):
            continue
        saida.append({"titulo": _limpar(dados.get("t", ""), 160), "url": url,
                      "miniatura": dados.get("turl", ""), "pagina": dados.get("purl", ""),
                      "licenca": "", "fonte": "Bing Imagens"})
        if len(saida) >= maximo:
            break
    return saida


def parse_wikipedia(dados: dict, idioma: str = "pt", maximo: int = 5) -> list:
    saida = []
    for it in (dados.get("query", {}) or {}).get("search", [])[:maximo]:
        titulo = it.get("title", "")
        saida.append({"titulo": titulo, "url": f"https://{idioma}.wikipedia.org/wiki/" + quote_plus(titulo.replace(" ", "_")),
                      "trecho": _limpar(it.get("snippet", ""))})
    return saida


def parse_commons(dados: dict, maximo: int = 8) -> list:
    saida = []
    paginas = (dados.get("query", {}) or {}).get("pages", {}) or {}
    for pg in sorted(paginas.values(), key=lambda x: x.get("index", 0)):
        info = (pg.get("imageinfo") or [{}])[0]
        url = info.get("url") or ""
        if not _http_url(url):
            continue
        meta = info.get("extmetadata", {}) or {}
        saida.append({"titulo": re.sub(r"^File:", "", pg.get("title", "")), "url": info.get("thumburl") or url,
                      "miniatura": info.get("thumburl", ""), "pagina": info.get("descriptionurl", ""),
                      "licenca": (meta.get("LicenseShortName", {}) or {}).get("value", ""),
                      "fonte": "Wikimedia Commons"})
        if len(saida) >= maximo:
            break
    return saida


def parse_openverse(dados: dict, maximo: int = 8) -> list:
    saida = []
    for it in (dados.get("results") or [])[:maximo]:
        url = it.get("url") or ""
        if not _http_url(url):
            continue
        lic = (it.get("license") or "").upper()
        saida.append({"titulo": _limpar(it.get("title", ""), 160), "url": url, "miniatura": it.get("thumbnail", ""),
                      "pagina": it.get("foreign_landing_url", ""),
                      "licenca": (("CC " + lic) if lic else "") + (" " + str(it.get("license_version") or "") if lic else ""),
                      "fonte": "Openverse"})
    return saida


def parece_bloqueio(texto_html: str) -> bool:
    """CAPTCHA / 'anomaly' / página de desafio em vez de resultados."""
    baixo = (texto_html or "")[:20000].lower()
    return any(s in baixo for s in ("anomaly-modal", "unusual traffic", "captcha", "are you a human",
                                    "challenge-form", "verify you are a human"))


# ------------------------------------------------------------------ rede
def _sessao(sessao):
    if sessao is not None:
        return sessao
    if requests is None:
        raise RuntimeError("a biblioteca 'requests' não está disponível")
    s = requests.Session()
    s.headers.update(CABECALHOS)
    return s


def _get(sessao, url, **kw):
    r = sessao.get(url, timeout=kw.pop("timeout", TEMPO), **kw)
    r.raise_for_status()
    return r


def _fonte_ddg(q, sessao, maximo):
    r = sessao.post("https://html.duckduckgo.com/html/", data={"q": q, "kl": "br-pt"}, timeout=TEMPO,
                    headers=CABECALHOS)
    r.raise_for_status()
    res = parse_ddg_html(r.text, maximo)
    if not res and parece_bloqueio(r.text):
        raise RuntimeError("o DuckDuckGo pediu verificação (muitas buscas seguidas)")
    return res


def _fonte_bing(q, sessao, maximo):
    r = _get(sessao, f"https://www.bing.com/search?q={quote_plus(q)}&setlang=pt-BR&cc=BR", headers=CABECALHOS)
    res = parse_bing_html(r.text, maximo)
    if not res and parece_bloqueio(r.text):
        raise RuntimeError("o Bing pediu verificação (muitas buscas seguidas)")
    return res


def _fonte_wikipedia(q, sessao, maximo):
    r = _get(sessao, "https://pt.wikipedia.org/w/api.php", params={
        "action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": maximo, "utf8": 1},
        headers=CABECALHOS)
    return parse_wikipedia(r.json(), "pt", maximo)


FONTES_TEXTO = (("DuckDuckGo", _fonte_ddg), ("Bing", _fonte_bing), ("Wikipédia", _fonte_wikipedia))


def buscar_texto(consulta: str, maximo: int = 5, sessao=None, fontes=None) -> dict:
    """{'ok', 'fonte', 'resultados': [{titulo,url,trecho}], 'erros': [str]}"""
    consulta = (consulta or "").strip()
    if not consulta:
        return {"ok": False, "fonte": "", "resultados": [], "erros": ["consulta vazia"]}
    erros = []
    try:
        s = _sessao(sessao)
    except Exception as e:
        return {"ok": False, "fonte": "", "resultados": [], "erros": [str(e)]}
    for nome, fn in (fontes or FONTES_TEXTO):
        try:
            res = fn(consulta, s, maximo)
        except Exception as e:
            erros.append(f"{nome}: {e}")
            continue
        if res:
            return {"ok": True, "fonte": nome, "resultados": res[:maximo], "erros": erros}
        erros.append(f"{nome}: sem resultados")
    return {"ok": False, "fonte": "", "resultados": [], "erros": erros}


def _fonte_bing_img(q, sessao, maximo):
    r = _get(sessao, f"https://www.bing.com/images/search?q={quote_plus(q)}&form=HDRSC2&first=1&adlt=strict",
             headers=CABECALHOS)
    res = parse_bing_imagens(r.text, maximo)
    if not res and parece_bloqueio(r.text):
        raise RuntimeError("o Bing pediu verificação (muitas buscas seguidas)")
    return res


def _fonte_commons(q, sessao, maximo):
    r = _get(sessao, "https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "generator": "search", "gsrsearch": "filetype:bitmap " + q, "gsrnamespace": 6,
        "gsrlimit": maximo, "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 900,
        "format": "json", "utf8": 1}, headers=CABECALHOS)
    return parse_commons(r.json(), maximo)


def _fonte_openverse(q, sessao, maximo):
    r = _get(sessao, "https://api.openverse.org/v1/images/", params={"q": q, "page_size": maximo, "mature": "false"},
             headers=CABECALHOS)
    return parse_openverse(r.json(), maximo)


FONTES_IMAGEM = (("Bing Imagens", _fonte_bing_img), ("Wikimedia Commons", _fonte_commons), ("Openverse", _fonte_openverse))


def buscar_imagens(consulta: str, maximo: int = 5, sessao=None, fontes=None) -> dict:
    """{'ok', 'fonte', 'resultados': [{titulo,url,miniatura,pagina,licenca,fonte}], 'erros': [str]}"""
    consulta = (consulta or "").strip()
    if not consulta:
        return {"ok": False, "fonte": "", "resultados": [], "erros": ["consulta vazia"]}
    erros = []
    try:
        s = _sessao(sessao)
    except Exception as e:
        return {"ok": False, "fonte": "", "resultados": [], "erros": [str(e)]}
    for nome, fn in (fontes or FONTES_IMAGEM):
        try:
            res = fn(consulta, s, maximo)
        except Exception as e:
            erros.append(f"{nome}: {e}")
            continue
        if res:
            return {"ok": True, "fonte": nome, "resultados": res[:maximo], "erros": erros}
        erros.append(f"{nome}: sem resultados")
    return {"ok": False, "fonte": "", "resultados": [], "erros": erros}


# ------------------------------------------------------------------ segurança do download
def url_publica(url: str, resolver=None) -> tuple:
    """(ok, motivo). Só http/https e SÓ endereços públicos: bloqueia localhost, rede local,
    link-local (169.254.x, inclui metadados de nuvem) e afins."""
    try:
        p = urlparse(url)
    except ValueError:
        return False, "endereço inválido"
    if p.scheme not in ("http", "https") or not p.hostname:
        return False, "só aceito endereços http:// ou https://"
    host = p.hostname
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = (resolver or socket.getaddrinfo)(host, None)
            ips = [ipaddress.ip_address(i[4][0]) for i in infos]
        except Exception:
            return False, "não consegui resolver o endereço"
    for ip in ips:
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False, "endereço local/privado bloqueado por segurança"
    return True, ""


def _nome_seguro(texto: str, padrao: str = "imagem") -> str:
    base = re.sub(r"[^\w\-]+", "_", texto or "", flags=re.UNICODE).strip("_")[:40]
    return base or padrao


def baixar_imagem(url: str, pasta, nome: str = "", sessao=None, resolver=None) -> dict:
    """Baixa UMA imagem para `pasta`. {'ok', 'path', 'msg', 'bytes'}. Confere tipo e conteúdo."""
    ok, motivo = url_publica(url, resolver)
    if not ok:
        return {"ok": False, "msg": motivo}
    try:
        s = _sessao(sessao)
        r = s.get(url, timeout=TEMPO + 6, stream=True, headers=CABECALHOS, allow_redirects=True)
        r.raise_for_status()
        # o redirecionamento também não pode levar a um endereço interno
        final = getattr(r, "url", url) or url
        if final != url:
            ok2, motivo2 = url_publica(final, resolver)
            if not ok2:
                return {"ok": False, "msg": "redirecionou para " + motivo2}
        tipo = (r.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
        if tipo and not tipo.startswith("image/"):
            return {"ok": False, "msg": f"o link não é uma imagem (é {tipo})"}
        corpo = bytearray()
        for pedaco in r.iter_content(65536):
            corpo += pedaco
            if len(corpo) > TETO_BYTES_IMAGEM:
                return {"ok": False, "msg": "imagem grande demais (limite 8 MB)"}
        if not corpo:
            return {"ok": False, "msg": "arquivo vazio"}
        try:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(bytes(corpo))) as im:
                im.verify()
                formato = (im.format or "").lower()
        except Exception:
            return {"ok": False, "msg": "o arquivo baixado não é uma imagem válida"}
        ext = EXT_POR_MIME.get(tipo) or {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "gif": ".gif",
                                          "bmp": ".bmp"}.get(formato, ".jpg")
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        base = _nome_seguro(nome or os.path.basename(urlparse(url).path))
        destino = pasta / (base + ext)
        k = 1
        while destino.exists():
            k += 1
            destino = pasta / f"{base}_{k}{ext}"
        destino.write_bytes(bytes(corpo))
        return {"ok": True, "path": str(destino), "msg": "", "bytes": len(corpo)}
    except Exception as e:
        return {"ok": False, "msg": f"falha no download: {e}"}


# ------------------------------------------------------------------ texto pronto para a IA
def formatar_texto(consulta: str, res: dict) -> str:
    if not res.get("ok"):
        det = "; ".join(res.get("erros", [])[:3]) or "sem detalhes"
        return (f"❌ Não consegui buscar \"{consulta}\" agora ({det}). Isso pode ser uma queda temporária "
                f"do buscador ou excesso de buscas seguidas — tente de novo em alguns minutos.")
    linhas = [f"Resultados da busca por \"{consulta}\" (via {res['fonte']}, sem chave de API):"]
    for it in res["resultados"]:
        trecho = it.get("trecho") or ""
        linhas.append(f"- {it.get('titulo','')} ({it.get('url','')})" + (f": {trecho}" if trecho else ""))
    return "\n".join(linhas)


def formatar_imagens(consulta: str, res: dict, arquivos: list) -> str:
    if not res.get("ok"):
        det = "; ".join(res.get("erros", [])[:3]) or "sem detalhes"
        return (f"❌ Não consegui buscar imagens de \"{consulta}\" agora ({det}). Tente de novo em alguns "
                f"minutos, ou descreva outra palavra-chave.")
    linhas = [f"Imagens encontradas para \"{consulta}\" (via {res['fonte']}, sem chave de API):"]
    for i, it in enumerate(res["resultados"], 1):
        lic = f" [{it['licenca']}]" if it.get("licenca") else ""
        linhas.append(f"{i}. {it.get('titulo') or 'sem título'}{lic} — {it.get('url','')}"
                      + (f" (página: {it['pagina']})" if it.get("pagina") else ""))
    if arquivos:
        linhas.append("Salvei estas no computador (a pessoa já está vendo no chat):")
        linhas += [f"- {a}" for a in arquivos]
    else:
        linhas.append("(não consegui baixar nenhuma delas; os links acima continuam valendo.)")
    linhas.append("Direitos: imagens da web têm dono — pra uso público, prefira as de licença livre (Commons/Openverse) "
                  "e cite a fonte.")
    return "\n".join(linhas)

# ======================================================================
#  Autoteste (/testar_busca) — roda NO PC DA PESSOA, com a rede dela (v22)
# ======================================================================
def testar_fontes() -> list:
    """[(nome, ok, detalhe)] — tenta CADA fonte de texto e de imagem com uma consulta pequena (sem parar na
    primeira que funciona, ao contrário da busca normal). Mostra, na prática, o que está funcionando hoje."""
    saida = []
    try:
        s = _sessao(None)
    except Exception as e:
        return [("Conexão", False, str(e)[:110])]
    for rotulo, fontes, consulta in (("Texto", FONTES_TEXTO, "Albert Einstein"), ("Imagem", FONTES_IMAGEM, "gato")):
        for nome, fn in fontes:
            try:
                n = len(fn(consulta, s, 3))
                saida.append((f"{rotulo}: {nome}", n > 0, f"{n} resultado(s)" if n else "respondeu, mas sem resultados"))
            except Exception as e:
                saida.append((f"{rotulo}: {nome}", False, str(e)[:110]))
    return saida


def texto_autoteste() -> str:
    linhas = ["🔧 Teste das fontes de busca (com a SUA internet agora):"]
    res = testar_fontes()
    alguma_txt = any(ok for n, ok, _ in res if n.startswith("Texto"))
    alguma_img = any(ok for n, ok, _ in res if n.startswith("Imagem"))
    for nome, ok, detalhe in res:
        linhas.append(f"{'✓' if ok else '✗'} {nome}: {detalhe}")
    if alguma_txt and alguma_img:
        linhas.append("Tudo certo: basta UMA fonte de texto e UMA de imagem funcionando pra Zenith pesquisar sem chave. "
                      "As de buscador são raspagem e podem falhar de vez em quando; Wikipédia/Commons/Openverse são abertas.")
    else:
        faltam = " e ".join(x for x, ok in (("de texto", alguma_txt), ("de imagem", alguma_img)) if not ok)
        linhas.append(f"Nenhuma fonte {faltam} respondeu: confira a internet, o antivírus e o firewall. "
                      "A Tavily (chave) continua como plano B para texto.")
    return "\n".join(linhas)
