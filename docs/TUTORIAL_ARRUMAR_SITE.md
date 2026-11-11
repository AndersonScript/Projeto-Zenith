# Tutorial Passo a Passo — Arrumar e Publicar o Site do Zenith (Vercel + GitHub Releases)
### Atualizado em 10/11/2026

---

## 1. Corrigir o Root Directory na Vercel (Caso o site mostre outro app ou `/latest.json` devolva HTML)

1. Acesse o painel da Vercel (`https://vercel.com/dashboard`) e abra o projeto **projeto-zenith-five**.
2. Vá em **Settings → Build and Deployment** (ou **General → Root Directory**).
3. Em **Root Directory**, clique em **Edit** e defina exatamente:
   ```
   site
   ```
4. Em **Framework Preset**, selecione **Other** (com Build Command e Output Directory vazios).
5. Vá na aba **Deployments**, clique nos três pontinhos (`⋯`) do último deploy e escolha **Redeploy** (desmarque *Use existing Build Cache*).
6. **Teste no navegador:**
   - `https://projeto-zenith-five.vercel.app/latest.json` → deve mostrar o JSON com a versão `1.0` e os hashes SHA-256.
   - `https://projeto-zenith-five.vercel.app/baixar` → deve iniciar o download do `ZenithLauncher.exe`.

---

## 2. Ordem Correta para Publicar Nova Versão (Regra A02)

> ⚠️ **Importante:** Sempre suba os arquivos `.exe` / `.apk` / `.zip` na Release do GitHub **ANTES** de atualizar o `site/latest.json`. Se atualizar o `latest.json` antes, quem baixar durante o intervalo receberá erro de "SHA-256 não confere".

### Passo a passo automatizado:
```powershell
# 1. Limpar dados pessoais e montar pacote público
py -3 tools/preparar_publico.py

# 2. Calcular SHA-256 dos executáveis
certutil -hashfile dist_launcher\ZenithLauncher.exe SHA256
certutil -hashfile dist_launcher\LimparZenith.exe SHA256
certutil -hashfile body\zenith\export\Zenith.apk SHA256

# 3. Subir os binários na Release do GitHub (https://github.com/AndersonScript/Projeto-Zenith/releases)
# 4. Atualizar latest.json e site/latest.json e fazer git push
```
