"""
Zenith — IMAGENS POR IA (v27): os "dons artísticos" da Zenith.

O que o Anderson pediu (e reforçou em 11/10/2026): não era só o autorretrato — era melhorar os dons artísticos dela em
geral, "imagens bonitas igual a você ou o Nano Banana". O que ela tinha até a v26 era só DESENHO POR CÓDIGO (Pillow:
formas, texto, degradê): ótimo pra meme, cartaz e citação, mas incapaz de pintar uma cena. Imagem de verdade só vem de um
MODELO DE IMAGEM. Este módulo liga o modelo de imagem do Gemini — a mesma chave que ela já usa pra conversar.

Modelos (consultados na documentação oficial do Google em 11/10/2026 — nomes e preços MUDAM, por isso são configuráveis):
  padrao -> "gemini-2.5-flash-image"          ("Nano Banana"; ~US$ 0,04 por imagem no plano pago)
  pro    -> "gemini-3-pro-image-preview"      ("Nano Banana Pro"; melhor, ~US$ 0,13 por imagem 1K/2K; só no plano pago)
Troque o modelo em config/settings.json: "imagem_ia_modelo".

IMPORTANTE (honestidade): eu NÃO consegui chamar o serviço real do Google daqui — o código segue a documentação e é
testado com um cliente de mentira. A primeira imagem de verdade (`/imagem um gato astronauta`) é o teste final.
Se der erro, a mensagem explica em português o que fazer (cota, plano gratuito sem imagem, chave, bloqueio de segurança).

Como é acionado:
  * você, direto:        /imagem <descrição>      (+ "pro" e/ou proporção:  /imagem pro 16:9 um castelo ao pôr do sol)
  * a Zenith, sozinha:    <gerar_imagem>descrição</gerar_imagem>   -> SEMPRE pede a sua aprovação (pode ter custo)

Lógica pura + uma chamada de rede isolada em `gerar()` (o cliente pode ser injetado nos testes).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

MODELOS = {"padrao": "gemini-2.5-flash-image", "pro": "gemini-3-pro-image-preview"}
PROPORCOES = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3")
CUSTO = {"padrao": "≈ US$ 0,04 por imagem", "pro": "≈ US$ 0,13 por imagem (1K/2K)"}
MAX_PROMPT = 1500


class ErroImagem(Exception):
    """Erro que já vem EXPLICADO em português (a mensagem vai direto pro chat)."""


def interpretar_pedido(texto: str) -> dict:
    """"pro 16:9 um castelo" -> {"qualidade": "pro", "proporcao": "16:9", "descricao": "um castelo"}.
    Só as palavras-chave do COMEÇO contam (pro/rapido, proporção); o resto é a descrição."""
    qualidade, proporcao = "padrao", "1:1"
    resto = (texto or "").strip()
    while True:
        m = re.match(r"^(pro|rapido|rápido|flash|\d{1,2}:\d{1,2})\b\s*", resto, re.I)
        if not m:
            break
        t = m.group(1).lower()
        if t == "pro":
            qualidade = "pro"
        elif t in ("rapido", "rápido", "flash"):
            qualidade = "padrao"
        elif t in PROPORCOES:
            proporcao = t
        else:
            break
        resto = resto[m.end():]
    return {"qualidade": qualidade, "proporcao": proporcao, "descricao": resto.strip()}


def modelo_para(qualidade: str, settings=None) -> str:
    """Modelo a usar: o escolhido nas configurações (padrão) ou o 'pro' pedido no comando."""
    if qualidade == "pro":
        return str((settings.get("imagem_ia_modelo_pro") if settings else None) or MODELOS["pro"])
    return str((settings.get("imagem_ia_modelo") if settings else None) or MODELOS["padrao"])


def aviso_de_custo(qualidade: str) -> str:
    return (f"Pode ter custo: gera uma imagem com IA do Google ({CUSTO.get(qualidade, CUSTO['padrao'])}; preço publicado pelo "
            f"Google, pode mudar; no plano gratuito a geração de imagem pode nem estar liberada).")


def traduzir_erro(e: Exception) -> str:
    """Erro técnico da API -> mensagem em português com o próximo passo."""
    t = f"{type(e).__name__}: {e}"
    baixo = t.lower()
    if "429" in t or "resource_exhausted" in baixo or "quota" in baixo or "rate limit" in baixo:
        return ("🎨 O Google barrou por COTA/limite de uso (erro 429). Na prática: pelo que o próprio Google informa, a geração de "
                "imagem NÃO vem no plano gratuito da API (o limite é 0) — não é erro seu nem do Zenith.\n"
                "Como resolver, passo a passo:\n"
                "1) Abra aistudio.google.com/apikey e entre com a mesma conta da sua chave.\n"
                "2) Ao lado da chave aparece o plano. Se estiver \"Free\", clique em configurar faturamento (\"Set up billing\") e "
                "vincule um cartão — o nome do botão pode mudar com o tempo.\n"
                "3) Espere alguns minutos e tente /imagem de novo (cada imagem custa centavos).\n"
                "Sem cartão? Gere a imagem no site do Gemini e anexe aqui, ou peça meme, cartaz ou citação — esses eu faço por "
                "código, de graça e sem internet.")
    if "403" in t or "permission_denied" in baixo or "billing" in baixo or "not available" in baixo or "paid" in baixo:
        return ("🎨 O Google não liberou imagem pra essa chave (erro 403). Modelos de imagem costumam exigir o PLANO PAGO "
                "(faturamento ativo no Google AI Studio). Confira a chave e o plano.")
    if "404" in t or "not found" in baixo or "is not supported" in baixo:
        return ("🎨 O modelo de imagem não foi encontrado (erro 404). Os nomes mudam com o tempo. Em config/settings.json "
                "troque \"imagem_ia_modelo\" pelo nome atual (veja ai.google.dev/gemini-api/docs/image-generation).")
    if "api key" in baixo or "api_key" in baixo or "401" in t or "invalid" in baixo and "key" in baixo:
        return "🎨 A chave do Gemini parece inválida. Confira em Configurações > IAs & Chaves."
    if "safety" in baixo or "blocked" in baixo or "prohibited" in baixo:
        return ("🎨 O Google bloqueou esse pedido por segurança. Tente descrever de outro jeito (sem pessoas reais, marcas "
                "ou conteúdo sensível).")
    if "timeout" in baixo or "connection" in baixo or "network" in baixo or "getaddrinfo" in baixo:
        return "🎨 Sem conexão com o Google agora (rede/timeout). Tente de novo em instantes."
    return f"🎨 Não consegui gerar a imagem: {t[:300]}"


def _extrair_imagem(resp):
    """(bytes, mime, texto_do_modelo) da resposta; bytes=None se não veio imagem."""
    textos = []
    for cand in (getattr(resp, "candidates", None) or []):
        conteudo = getattr(cand, "content", None)
        for parte in (getattr(conteudo, "parts", None) or []):
            inline = getattr(parte, "inline_data", None)
            dados = getattr(inline, "data", None) if inline is not None else None
            if dados:
                return dados, (getattr(inline, "mime_type", None) or "image/png"), " ".join(textos).strip()
            t = getattr(parte, "text", None)
            if t:
                textos.append(t)
    return None, None, " ".join(textos).strip()


def _chamar(cliente, tipos, modelo: str, prompt: str, proporcao: str):
    """Tenta a chamada com proporção + só-imagem; se a versão do SDK não conhece esses campos, cai pra chamada simples."""
    variantes = []
    try:
        variantes.append(tipos.GenerateContentConfig(
            response_modalities=["IMAGE"], image_config=tipos.ImageConfig(aspect_ratio=proporcao)))
    except Exception:
        pass
    try:
        variantes.append(tipos.GenerateContentConfig(response_modalities=["IMAGE"]))
    except Exception:
        pass
    variantes.append(None)
    ultimo = None
    for cfg in variantes:
        try:
            if cfg is None:
                return cliente.models.generate_content(model=modelo, contents=[prompt])
            return cliente.models.generate_content(model=modelo, contents=[prompt], config=cfg)
        except (TypeError, ValueError, AttributeError) as e:      # SDK antigo não aceita o campo: tenta a próxima variante
            ultimo = e
            continue
    raise ultimo


def gerar(prompt: str, chave: str, pasta, modelo: str = MODELOS["padrao"], proporcao: str = "1:1",
          cliente=None, tipos=None, agora=None) -> dict:
    """Gera UMA imagem e salva em <pasta>/imagens/. Devolve {"caminho", "modelo", "texto"}.
    Levanta ErroImagem (mensagem já em português). `cliente`/`tipos` existem pra teste."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ErroImagem("🎨 Faltou descrever a imagem. Ex.: /imagem um gato astronauta flutuando perto da Lua, estilo aquarela")
    if len(prompt) > MAX_PROMPT:
        prompt = prompt[:MAX_PROMPT]
    if cliente is None:
        if not chave:
            raise ErroImagem("🎨 Preciso da chave do Gemini pra gerar imagem (Configurações > IAs & Chaves). "
                             "Sem ela eu só consigo desenhar por código (meme, cartaz, citação).")
        try:
            from google import genai
            from google.genai import types as tipos
        except Exception as e:
            raise ErroImagem(f"🎨 A biblioteca do Gemini (google-genai) não está disponível aqui: {e}")
        try:
            cliente = genai.Client(api_key=chave)
        except Exception as e:
            raise ErroImagem(traduzir_erro(e))
    proporcao = proporcao if proporcao in PROPORCOES else "1:1"
    try:
        resp = _chamar(cliente, tipos, modelo, prompt, proporcao)
    except Exception as e:
        raise ErroImagem(traduzir_erro(e))
    dados, mime, texto = _extrair_imagem(resp)
    if not dados:
        motivo = ""
        try:
            motivo = str(getattr(getattr(resp, "prompt_feedback", None), "block_reason", "") or "")
        except Exception:
            pass
        extra = f" Resposta do modelo: {texto[:200]}" if texto else ""
        raise ErroImagem("🎨 O modelo não devolveu imagem" + (f" (bloqueio: {motivo})" if motivo else "")
                         + ". Pode ter sido filtro de segurança ou pedido vago demais — tente descrever com mais detalhes."
                         + extra)
    ext = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp"}.get(str(mime).lower(), "png")
    saida = Path(pasta) / "imagens"
    saida.mkdir(parents=True, exist_ok=True)
    carimbo = time.strftime("%Y%m%d_%H%M%S", time.localtime(agora or time.time()))
    caminho = saida / f"ia_{carimbo}.{ext}"
    n = 2
    while caminho.exists():
        caminho = saida / f"ia_{carimbo}_{n}.{ext}"
        n += 1
    caminho.write_bytes(dados if isinstance(dados, (bytes, bytearray)) else bytes(dados))
    return {"caminho": str(caminho), "modelo": modelo, "texto": texto}

def dimensoes_proporcao(proporcao: str) -> tuple[int, int]:
    """Retorna (largura, altura) adequada para geradores de imagem baseados em 768px/1024px."""
    mapa = {
        "1:1": (768, 768),
        "16:9": (1024, 576),
        "9:16": (576, 1024),
        "4:3": (800, 600),
        "3:4": (600, 800),
        "3:2": (900, 600),
        "2:3": (600, 900),
    }
    return mapa.get(proporcao, (768, 768))


def gerar_pollinations(prompt: str, pasta, proporcao: str = "1:1", agora=None) -> dict:
    """Gera imagem 100% grátis e sem chave via Pollinations.ai (FLUX/SD)."""
    import urllib.request
    import urllib.parse
    prompt = (prompt or "").strip()
    if not prompt:
        raise ErroImagem("🎨 Faltou descrever a imagem.")
    w, h = dimensoes_proporcao(proporcao)
    url_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{url_prompt}?width={w}&height={h}&nologo=false"
    
    saida = Path(pasta) / "imagens"
    saida.mkdir(parents=True, exist_ok=True)
    carimbo = time.strftime("%Y%m%d_%H%M%S", time.localtime(agora or time.time()))
    caminho = saida / f"ia_{carimbo}.png"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Zenith/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            dados = r.read()
    except Exception as e:
        raise ErroImagem(f"🎨 Não consegui gerar no Pollinations (grátis): {e}")
        
    caminho.write_bytes(dados)
    return {"caminho": str(caminho), "modelo": "Pollinations (FLUX grátis)", "texto": "Gerado gratuitamente sem custo."}


def gerar_cloudflare(prompt: str, account_id: str, token: str, pasta, proporcao: str = "1:1", agora=None) -> dict:
    """Gera imagem usando o plano gratuito de 10.000 neurons/dia da Cloudflare Workers AI (FLUX.1 schnell)."""
    import base64
    import json
    import urllib.request
    prompt = (prompt or "").strip()
    if not prompt or not account_id or not token:
        raise ErroImagem("🎨 Para gerar com Cloudflare, configure o Account ID e Token.")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    corpo = json.dumps({"prompt": prompt, "steps": 4}).encode("utf-8")
    req = urllib.request.Request(url, data=corpo, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Zenith/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read().decode("utf-8"))
            img_b64 = resp["result"]["image"]
            dados = base64.b64decode(img_b64)
    except Exception as e:
        raise ErroImagem(f"🎨 Falha na Cloudflare Workers AI: {e}")
    saida = Path(pasta) / "imagens"
    saida.mkdir(parents=True, exist_ok=True)
    carimbo = time.strftime("%Y%m%d_%H%M%S", time.localtime(agora or time.time()))
    caminho = saida / f"ia_{carimbo}.png"
    caminho.write_bytes(dados)
    return {"caminho": str(caminho), "modelo": "Cloudflare Workers AI (FLUX.1)", "texto": "Gerado via Cloudflare Workers AI."}
