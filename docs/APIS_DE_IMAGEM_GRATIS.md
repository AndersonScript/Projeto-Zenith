# APIs de Imagem 100% Grátis para o Zenith
### Levantamento verificado · Atualizado em 10/11/2026

> **Regra de ouro:** muitos serviços anunciam "Free Tier", mas exigem cartão de crédito ou compra mínima de créditos (ex.: Together AI exige US$ 15; Hugging Face Free não inclui créditos para FLUX; Gemini cobra ~US$ 0,04 por imagem e bloqueia no plano gratuito com erro 429/403). Abaixo estão as **duas opções realmente gratuitas** já integradas ao Zenith (`brain/zenith_imagem_ia.py`).

---

## 1. Pollinations.ai (Padrão Automático — Sem Chave e Sem Cadastro)

- **Custo:** 100% grátis, sem cadastro, sem cartão e sem chave de API.
- **Modelo:** FLUX / Stable Diffusion via endpoint HTTP direto.
- **Como funciona no Zenith:**
  - Endpoint: `https://image.pollinations.ai/prompt/<descricao>?width=<w>&height=<h>&nologo=false`
  - Função: `gerar_pollinations(prompt, pasta, proporcao="1:1")` em `brain/zenith_imagem_ia.py`.
  - Acionado automaticamente quando não há chave paga ou quando o Gemini retorna erro de cota/faturamento (429/403), tanto no PC quanto no Celular Standalone (`body/zenith/brain_connector.gd`).

---

## 2. Cloudflare Workers AI (Principal com Conta Gratuita — Sem Cartão)

- **Custo:** 10.000 neurons/dia grátis (sem exigir cartão de crédito). Se passar da cota diária, apenas recusa até 00:00 UTC (**nunca cobra**).
- **Modelo:** `@cf/black-forest-labs/flux-1-schnell` (até 1024×1024, sem marca d'água).
- **Como configurar no Zenith:**
  1. Crie uma conta gratuita em `https://dash.cloudflare.com`.
  2. No menu lateral, clique em **AI → Workers AI → Use REST API**.
  3. Copie seu **Account ID** e clique em **Create a Workers AI API Token** para gerar o token.
  4. Salve em `config/settings.json` (ou nas Configurações do Zenith):
     ```json
     {
       "cloudflare_account_id": "SEU_ACCOUNT_ID",
       "cloudflare_api_token": "SEU_TOKEN"
     }
     ```
- **Função no Zenith:** `gerar_cloudflare(prompt, account_id, token, pasta, proporcao="1:1")` em `brain/zenith_imagem_ia.py`.

---

## 3. Comparativo de Preços Verificados

| Provedor | É grátis de verdade? | Exige cartão? | Detalhe real |
|---|---|---|---|
| **Pollinations.ai** | ✅ Sim | ❌ Não | Sem chave, ~1 imagem a cada 45s, até 1024px |
| **Cloudflare Workers AI** | ✅ Sim (10k neurons/dia) | ❌ Não | FLUX.1 schnell sem marca d'água |
| **Google Gemini Imagen** | ❌ Não na API gratuita | ✅ Sim (Billing) | ~US$ 0,04/img (`gemini-2.5-flash-image`), erro 429 no plano Free |
| **Together AI** | ❌ Não | ✅ Sim | Exige compra mínima de US$ 15 |
| **Hugging Face Inference** | ❌ Não para FLUX | ✅ Sim (PRO) | Exige plano PRO (US$ 9/mês) para modelos grandes |
| **Local (ComfyUI / Fooocus)** | ✅ Sim (usa sua GPU) | ❌ Não | Sem limite, roda 100% offline na sua placa de vídeo |
