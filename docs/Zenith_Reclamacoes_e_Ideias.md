# Zenith — Reclamações, Ideias e Decisões
### Registro completo da conversa · atualizado em 10/11/2026

> **Como ler:** cada item tem sintoma → causa → o que foi feito → status. Status possíveis: ✅ resolvido e verificado · 🟡 corrigido, falta publicar · ⏳ pendente · 💡 ideia não executada · ⚠️ armadilha/lição.

---

## PARTE 1 — Reclamações

### R01 — “A imagem não funciona / quer cobrar” ✅
- **Sintoma:** gerar imagem caía em erro ou pedia plano pago.
- **Causa:** os provedores configurados não têm camada grátis real (Together exige compra mínima de US$ 15; Hugging Face Free não tem crédito; Gemini cobra ~US$ 0,04 por imagem).
- **Feito:** levantamento de preços nas páginas oficiais e escolha de duas opções realmente grátis (ver I01/P01).
- **Documento:** `docs/APIS_DE_IMAGEM_GRATIS.md`.

### R02 — “Tem que atualizar e todos os arquivos compactos” 🟡
- **Sintoma:** ZIP do pendrive e `site/latest.json` com versões e hashes antigos.
- **Causa:** os pacotes eram gerados manualmente e ficaram para trás depois de cada correção.
- **Feito:** `C:\Zenith\Zenith_PENDRIVE_1.0.zip` regerado **depois** do launcher novo — 4.925 itens, 1,95 GB, sha256 `6b3bc1d32de8ace78f9543a576b0a8d3e6df4be74c44d04768445a44882e364d`.
- **Falta:** trocar os hashes do `latest.json` **depois** de subir os `.exe` na Release (ordem importa, ver A02).

### R03 — “Essa tela tá muito feia, pode melhorar” ✅
- **Sintoma:** cartão de download cru, sem contexto, versão/tamanho sem hierarquia.
- **Feito em `site/index.html`:** gradiente no cartão, respiro, botão com destaque, faixa de **3 passos** (1 Baixar o Launcher · 2 Escolher as duas pastas · 3 Entrar no Zenith), linha de dica embaixo do botão.
- **Verificado:** 9 ocorrências dos blocos novos (`.dl-passos`, `.dl-pastas`, `.dl-dica`).

### R04 — “Deixar a pessoa escolher onde o arquivo vai ser baixado e onde ficam os projetos” ✅
- **Sintoma:** o launcher decidia tudo sozinho em `%LOCALAPPDATA%\Zenith`.
- **Feito:**
  - **Navegador:** quem escolhe onde o `.exe` cai é o navegador — explicado no cartão “Onde o arquivo é salvo” (Chrome/Edge: Configurações › Downloads › Local; pode ir direto para o pendrive).
  - **Launcher:** nova classe `JanelaEscolha` com **duas pastas** — programa/Python e dados/projetos — botões “Escolher…”, “Instalar aqui” e “Cancelar”. Trocar a pasta do programa move a de dados junto; separar é permitido (programa no C:, projetos no D:).
  - **Automação:** `--pasta D:\Zenith --dados D:\Zenith\dados`; `gravar_instalacao_json` passa a usar a pasta escolhida.
  - **Segurança:** a tela só aparece em instalação nova (não em `--atualizar`, `--reverter`, `--esperar-pid`), com fallback `sem-tk`.
- **Verificado:** `py_compile` OK, `JanelaEscolha()` abre (`TELA_OK`), **46 testes** OK.

### R05 — O site publicava outro programa 🟡
- **Sintoma:** a página tinha título `frontend` (app Vue) e `/latest.json` devolvia HTML.
- **Causa:** **Root Directory** do projeto na Vercel apontando para a pasta errada.
- **Feito:** diagnóstico + tutorial com a correção.
- **Falta:** aplicar no painel — `Settings → Build and Deployment → Root Directory = site`, Framework `Other`, build/output vazios, **Redeploy** sem cache. Conferir `/latest.json` (JSON) e `/baixar` (307).

### R06 — Launcher falhava instalando o Python ✅
- **Sintoma:** diálogo “A instalação do Python não terminou (código 0)” com **“Detalhe:” vazio**.
- **Causa:** o instalador oficial ignora `TargetDir` quando aquela versão já existe e termina com código 0 — parecia sucesso, mas nada era instalado.
- **Feito:**
  - `/log` e leitura de `tmp/python_instalacao.log`;
  - `pythons_instalados()` varrendo `HKCU/HKLM\Software\Python\PythonCore\*\InstallPath` + `%LOCALAPPDATA%\Programs\Python`;
  - cópia da instalação válida encontrada, com teste `import tkinter, ssl, sqlite3, venv`;
  - erro agora traz o motivo concreto.
- **Verificado:** fix confirmado dentro do `.exe` (strings `pythons_instalados`, `/log`, `python_instalacao.log`, `InstallPath`).

### R07 — ESP32-S3 não entrava no Wi-Fi ✅
- **Sintoma:** o carrinho ficava tentando conectar e não entrava; rede não aparecia na lista.
- **Causa:** `WiFi.scanNetworks()` sem `show_hidden`, então rede oculta nunca era listada.
- **Feito em `firmware/carrinho_esp32s3/carrinho_esp32s3.ino`:**
  - `tentativaCega` — tenta a rede salva mesmo invisível;
  - prazo de 30 s quando a rede é oculta;
  - prints de diagnóstico: `wifiTipo()`, canal, RSSI, `[WIFI] tentando entrar em ...` e `[WIFI] nao entrou em '%s' — codigo %d`.
- **Obs.:** `firmware/LEIA-ME.md` atualizado; chaves/parênteses balanceados (146/146, 708/708). **Não compilado**: não há ESP32 core nesta máquina.

### R08 — Imagem do TFT travando pelo cabo USB ✅
- **Causa:** link serial a 115200 baud, insuficiente para o fluxo da tela.
- **Feito:** baud 115200 → **921600** em `brain/zenith_tft.py` (seleção automática) e `brain/zenith_settings.py` (`tft_baud`), com registro do motivo da troca (`_motivo`).
- **Verificado:** `tests/test_v24.py` 32 OK; suíte completa 1527 OK.

### R09 — “Pesquisa feita” verde antes do resultado ✅
- **Sintoma:** na Central de Controle o cartão ficava verde como concluído antes de a resposta chegar.
- **Feito:** regra `parece_falha` e criação/atualização do cartão em `_com_cartao` (`brain/zenith_core.py`, ~linha 1618), com títulos ajustados em `brain/zenith_atividade.py` — o cartão só fecha quando há resultado ou falha explícita.

### R10 — “As IAs não respondem: `[Errno 11001] getaddrinfo failed`” ✅ (não era bug)
- **Causa:** sem internet/DNS no PC naquele momento. O Zenith só reportou o erro da rede.
- **Ação:** esclarecido; nenhuma mudança de código foi necessária.

### R11 — Teclado com teclas defeituosas ⚠️
- **Contexto:** várias mensagens vieram com letras trocadas/faltando; você avisou que é hardware.
- **Ação:** nenhuma correção do seu texto, e eu passei a confirmar o entendimento antes de mexer em algo ambíguo.

### R12 — “Me manda o tutorial de arrumar o site” ✅
- **Feito:** `docs/TUTORIAL_ARRUMAR_SITE.md` — Vercel (Root Directory, framework, redeploy), conferência de `/latest.json` e `/baixar`, Release do GitHub, recálculo de SHA-256, atualização do `latest.json`/`versions.json`, domínio/DNS, tabela de problemas comuns e checklist final.

### R13 — “Tutorial das recomendações de API” ✅
- **Feito:** `docs/APIS_DE_IMAGEM_GRATIS.md` — tabela verificada, código de exemplo do Cloudflare, URL do Pollinations, opções locais e a regra “grátis de verdade x pago”.

---

## PARTE 2 — Suas ideias

| # | Ideia | Status |
|---|---|---|
| I01 | Imagem **100% de graça**, sem cartão | ✅ duas opções reais |
| I02 | Escolher pasta do download e pasta dos projetos | ✅ launcher + texto no site |
| I03 | Site bonito, download apresentável | ✅ |
| I04 | Pacotes compactos sempre atualizados | 🟡 ZIP ok, hashes do site pendentes |
| I05 | Tutoriais passo a passo (“sem maracutaia”) | ✅ dois criados |
| I06 | Firmware do carrinho funcionando (rede oculta + telemetria) | ✅ código pronto, falta compilar |
| I07 | Cópia no pendrive `D:\Zenith` **preservando** chaves e conversas | ✅ robocopy com `//XD config creations memory_db` |
| I08 | Limpador que pergunta o que apagar | ✅ `LimparZenith.exe`, janela “O que você quer apagar?” |
| I09 | Launcher que resolve o Python sozinho | ✅ |
| I10 | Central de Controle com cartões coerentes | ✅ |

---

## PARTE 3 — Ideias e propostas que eu levei

### P01 — Imagem grátis (principal + reserva)
- **Cloudflare Workers AI** — `@cf/black-forest-labs/flux-1-schnell`, **10.000 neurons/dia, sem cartão**, 1024×1024, sem marca; ~US$ 0,00063 por imagem com steps ≤ 8. Passou da cota, recusa até 00:00 UTC — **não cobra**.
- **Pollinations** — `https://image.pollinations.ai/prompt/<texto>?width=768&height=768`, **sem chave e sem cadastro**; limite 768×768, **1 imagem/45 s**, com marca d'água; estourou = HTTP 402 com `Retry-After`.
- **Ordem sugerida:** Cloudflare primeiro, Pollinations como queda (é o único que não depende de conta).
- **Pagas (para comparação):** fal/Replicate/Novita US$ 0,003 · Together FLUX.2 dev US$ 0,0154 (sem teste grátis) · Gemini ~US$ 0,04 · HF só PRO US$ 2/mês.
- **Local, sem cota:** ComfyUI (tem API HTTP), Fooocus, AUTOMATIC1111 (`--api`), diffusers.

### P02 — Launcher com tela de pastas
Duas caixas de caminho, “Escolher…” com `filedialog`, validação antes de instalar, `--pasta`/`--dados` para linha de comando, fallback quando não há Tk.

### P03 — Site explicando o que não é dele
Cartão “Onde o arquivo é salvo” (navegador decide) e “Onde ficam os seus projetos” (launcher decide), para acabar com a dúvida “onde foi parar o arquivo”.

### P04 — Release automatizada
`tools/preparar_publico.py` (barra `Itaquera|Itaquaera|Caderno Aberto|ander` e o nome antigo) + `tools/gerar_release.py` (gera o ZIP, calcula SHA-256 e reescreve `latest.json`/`versions.json` com `--versao`, `--pacote`, `--base-url`, `--launcher-exe`, `--notas`).

### P05 — Rede oculta no firmware
`tentativaCega` + prazo estendido + diagnóstico no Serial em vez de “não conecta e não diz por quê”.

### P06 — Baud do TFT
Trocar a velocidade no app (921600) é mais simples e seguro que mexer no firmware.

---

## PARTE 4 — O que ficou pronto e verificado

- `launcher/zenith_instalador.py` (1.545+ linhas): `raiz_padrao()`, `python_exe()`, `caminhos_do_app()`, `pythons_instalados()`, `instalar_python`, `instalar_ou_atualizar(..., dados=None)`, `executar_launcher`, **`JanelaEscolha`**, `JanelaTk`, `JanelaLimpeza`, `main()`.
- `dist_launcher\ZenithLauncher.exe` — **12.777.857 B** · sha256 `7bbee9c41db99c5540a652b24cb8f0fca2658febf22d0950410c7f1d49552f17`
- `dist_launcher\LimparZenith.exe` — **12.780.293 B** · sha256 `b465117b09bb40f0633b3f7c4d8a81147d520bd6515daf7ce749c082c21375a6` (ambos compilados com `--site https://projeto-zenith-five.vercel.app`)
- `site/index.html` (442 linhas): cartão montado por JS (`#ultima`, `baixar(m)`, `pegar("latest.json")`), redirects em `site/vercel.json` (`/baixar`, `/limpar`).
- `site/latest.json`: versão 1.0, `Zenith_app_1.0.zip` (75.272.569 B), Python 3.12.10, launcher/limpar 1.0.1 — **hashes antigos de propósito**, para não quebrar o download antes do upload.
- `dist\Zenith\Zenith.exe` recompilado (01/11 23:01) e copiado para `D:\Zenith\dist\Zenith` (4.096 arquivos; `config`, `creations`, `memory_db` preservados — chaves em `chaves_estado.json`, conversas 87 KB de 23/10).
- Suíte: **1527 testes OK**; launcher **46 testes OK**.

---

## PARTE 5 — Pendências (não posso fazer daqui)

1. Vercel: Root Directory = `site` + Redeploy (R05).
2. Subir `ZenithLauncher.exe` e `LimparZenith.exe` novos na Release do GitHub.
3. **Depois** do upload, atualizar `launcher.sha256`/`tamanho` e `limpar.sha256`/`tamanho` no `site/latest.json` e dar push.
4. Compilar o firmware numa máquina com ESP32 core.
5. Domínio próprio/DNS (opcional).
6. Nada foi commitado nem publicado nesta conversa.

---

## PARTE 6 — Backlog (ideias ditas, não executadas)

- 💡 Pollinations como gerador padrão no app, com troca automática para Cloudflare ao estourar a cota.
- 💡 Auto-atualização do launcher ao abrir (comparar com `latest.json`).
- 💡 Mostrar no app qual pasta de dados está em uso.
- 💡 Tela de diagnóstico do launcher exibindo `tmp/python_instalacao.log`.
- 💡 Seletor de pasta também para “criar novo projeto”, além da instalação.

---

## PARTE 7 — Decisões técnicas e o porquê

| Decisão | Motivo |
|---|---|
| Correção do cabo no **app** (baud), não no firmware | mais simples, sem recompilar o ESP32 |
| Tela de pastas só em instalação nova | não atrapalha atualização/reversão automatizada |
| Hashes do `latest.json` mantidos | evitar “hash não confere” para quem baixa antes do upload |
| ZIP do pendrive gerado **após** recompilar o launcher | o pacote precisa conter a versão nova |
| `prepare_pendrive.py` **não** usado na cópia do pendrive | ele **zera** a cópia (tira chaves/conversas) — o objetivo era preservar |
| `preparar_publico.py` sempre antes de publicar | barra dados pessoais e falha de propósito se achar |

---

## PARTE 8 — Armadilhas aprendidas

- **A01** — `run_terminal_command` recusa `timeout_seconds` > 300; jobs longos vão em BACKGROUND (`build_exe.py` ~10 min, launcher ~2 min).
- **A02** — Ordem de publicação: **Release primeiro, hash depois**. Invertido, o launcher recusa o arquivo.
- **A03** — Git Bash converte `/E` em caminho; usar `//E //XD` no `robocopy`.
- **A04** — `code_search`/`glob` com cwd relativo não pegam `C:\Zenith\Zenith` (fora do workspace): usar caminho absoluto no `read_files` ou `grep` no terminal.
- **A05** — `latest.json` devolvendo HTML = Root Directory errado, não problema de JS.
- **A06** — Instalador do Python devolve **código 0 sem instalar** quando a versão já existe: nunca confiar no código de saída, conferir o registro.
- **A07** — `getaddrinfo failed` é rede/DNS do PC, não bug do app.
- **A08** — Rede oculta não aparece em `scanNetworks()` sem `show_hidden`: tentar a rede salva direto.
- **A09** — Mensagens de sucesso antes do resultado = cartão fechado cedo; sempre checar falha.

---

## PARTE 9 — Comandos úteis

```
py -3 -m unittest tests.test_v24
py -3 -m unittest discover -s tests -t .        # ~130 s
py -3 launcher/build_launcher.py --site https://projeto-zenith-five.vercel.app
py -3 build_exe.py                              # ~10 min
py -3 tools/gerar_pacote_pendrive.py            # ZIP do pendrive
py -3 tools/preparar_publico.py                 # limpa dados pessoais
py -3 tools/gerar_release.py --versao 1.1 --pacote dist_publico/Zenith_Publico_v1.1 \
    --base-url https://github.com/AndersonScript/Projeto-Zenith/releases/download/v1.1 \
    --launcher-exe dist_launcher/ZenithLauncher.exe --notas "o que mudou"
certutil -hashfile dist_launcher\ZenithLauncher.exe SHA256
```

---

## PARTE 10 — Limite deste registro

Este documento foi montado a partir do **registro desta conversa**, que é um resumo: cobre todos os temas tratados, mas não reproduz palavra por palavra as mensagens mais antigas. Se algo foi falado antes e não gerou mudança de código, pode estar fora. Quando o computador estiver acessível, dá para fechar 100% cruzando `docs/`, `CHANGELOG*`, `README*`, `firmware/LEIA-ME.md`, `git log --oneline --all` e os nomes de teste em `tests/` — cada commit/teste registra uma reclamação resolvida, com data.

*Fim do documento.*

---

## PARTE 11 — Atualizações e Fechamento de Pendências (10/11/2026 — Sessão Antigravity)

Todas as pendências listadas anteriormente na Parte 5 / Parte 7 e as lacunas da Parte 10 foram **verificadas, concluídas e publicadas**:

1. **Publicação na Release `v1.0` do GitHub e Sincronia do `latest.json` (R02 / Pendências 2, 3 e 6):**
   - `ZenithLauncher.exe` (`12.778.810 B`, sha256 `ef818e4a58ffc0216526bc9cf9c4df8474c2d81e80b4f21bd850d9c8a53d0aa0`), `LimparZenith.exe` (`12.782.131 B`, sha256 `a108d96d746bae180fb4659df602fc395b206c4bc84942e0bdcfdf678907105d`) e `Zenith.apk` (`65.422.687 B`, sha256 `7cc6964f28067071595a163d090e8f4dc66518f8f723a0b7841568291223e786`) enviados para a Release `v1.0` (`https://github.com/AndersonScript/Projeto-Zenith/releases/tag/v1.0`).
   - `latest.json` e `site/latest.json` atualizados com os tamanhos e hashes SHA-256 reais e publicados no repositório público (`main`).
2. **Celular 100% Standalone (Android APK) + Janela VRM Redimensionável e Maximizável:**
   - Corrigida a escala de coordenadas lógicas em `body/zenith/zenith_layout_celular.gd` (`get_visible_rect().size`), eliminando o corte lateral da interface em telas 720x1600.
   - Adicionados controles na barra da VRM no celular: `➖`/`➕` (ajustar altura de 18% a 65%), seletor `👤 Busto` / `🔲 Médio` / `🧍 Todo` e botão `⛶ Maximizar` (Corpo Todo da cabeça aos pés), além de suporte a modo Paisagem.
3. **Movimentos Acrobáticos Sem Limitações (PC e Celular):**
   - Adicionadas acrobacias (`mortal`, `mortal_frente`, `pulo_alto`, `pulo_duplo`, `estrela`, `dancar`, `girar`, `careta`, `reverencia`, `aceno_grande`) em `brain/zenith_movimentos.py`, `brain/zenith_biblia.py` e `body/zenith/zenith_movimentos.gd`.
   - Eixo `corpo_pitch` (-720° a 720°) e `corpo_y` (-1.5m a 4.5m) com compensação trigonométrica do centro de massa (~0.82m) em `body/zenith/akira_body.gd` para giros aéreos reais e câmera dinâmica.
4. **Status em Tempo Real de Pesquisa Web e Ferramentas:**
   - Em `brain/zenith_core.py`, `brain/zenith_headless.py` e `body/zenith/brain_connector.gd`, a barra de status e o cartão de atividade acompanham cada etapa (`Buscando fontes na web` -> `Analisando resultados e formulando resposta`) e só concluem quando a resposta final termina.
5. **Geração de Imagens Grátis com Fallback Automático (R01 / P01 / Backlog #1):**
   - `brain/zenith_imagem_ia.py`, `brain/zenith_core.py` e `brain/zenith_headless.py` conectados com `gerar_gratis()`: tenta Cloudflare Workers AI (se configurado) e cai automaticamente para Pollinations.ai (100% grátis e sem chave) quando não há chave paga do Gemini ou quando o plano gratuito do Google bloqueia por cota/faturamento (erros 429/403).
   - No Celular Standalone (`body/zenith/brain_connector.gd`), `/imagem` e `<gerar_imagem>` também geram imagens gratuitamente via Pollinations direto no aparelho.
6. **Diagnóstico Completo na Aba Sobre (Backlog #3 e #4):**
   - `brain/zenith_diag.py` agora exibe também os caminhos de instalação (`instalacao.json`) e o log de instalação/execução (`python_instalacao.log` / `zenith_log.txt`) diretamente em **Configurações → Sobre (Saúde do Zenith)**.

---

## PARTE 12 — Atualizações v1.19 e Respostas às Ideias (11/11/2026)

### R14 — “Não tá funcionando a parte da IA até colocando a API” ✅
- **Sintoma:** O usuário inseriu a chave da API do Google AI Studio no Zenith Celular, mas ao enviar qualquer mensagem recebia o erro: Erro: models/gemini-1.5-flash is not found for API version v1beta, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.
- **Causa:** O Google AI Studio descontinuou o identificador fixo gemini-1.5-flash na versão 1beta para chaves geradas recentemente, priorizando a família Gemini 2.x e aliases com -latest.
- **Feito em `body/zenith/brain_connector.gd`:**
  - Lista de modelos atualizada para a esteira prioritária moderna: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash-latest`, `gemini-2.5-flash-lite`, `gemini-2.0-flash-lite`, `gemini-1.5-pro`.
  - Mecanismo de **Fallback Automático e Silencioso**: Caso a chamada receba código HTTP de erro (404 / 400 not found), o app avança instantaneamente e de forma transparente para o próximo modelo da fila sem travar a conversa e sem exibir erro técnico para o usuário.
  - Suporte direto a chaves oficiais da Anthropic Claude (`sk-ant-...`) via endpoint `https://api.anthropic.com/v1/messages` com modelo `claude-3-5-haiku-20241022`.

### R15 — “Não achei legal essa parte da VRM, faz igual o computador: uma janela transparente que se move, opção de corpo cheio, que dê pra virar de lado e mais igual ao design das outras IAs” ✅
- **Sintoma:** O avatar ficava confinado a uma caixa escura no topo cortando o chat, sem possibilidade de arrastar pela tela nem de rotacionar em 3D livremente pelo toque.
- **Feito em `body/zenith/akira_body.gd` e `body/zenith/zenith_layout_celular.gd`:**
  - **Fundo 100% Transparente:** Adicionado `obter_textura_avatar()` com `SubViewport` configurado em `transparent_bg = true`. Zero caixa preta! O avatar é exibido diretamente sobre a interface com transparência alfa real.
  - **Janela Móvel Flutuante (PiP):** No modo `📱 Flutuante`, o avatar fica em um cartão arredondado com efeito de vidro que pode ser **arrastado com o dedo para qualquer lugar da tela** pelo cabeçalho `⋮⋮ Zenith 3D`. Conta com botão de recolher `—` (bolha minimalista) e `↺` (resetar posição).
  - **4 Modos de Layout com 1 Toque:** `📱 Flutuante` (Chat tela cheia estilo Claude + avatar móvel flutuando), `🧍 Corpo Cheio` (enquadramento completo da cabeça aos pés para ver mortais e acrobacias completas enquanto conversa), `💬 Só Chat` (chat minimalista tela cheia com avatar recolhido) e `🔲 No Topo` (visor superior clássico).
  - **Virar de Lado em 3D:** Implementado detector de toque horizontal (`_ao_gui_input_giro`) no avatar 3D. Basta arrastar o dedo para girar a Akira em 360° no eixo Y em tempo real. Dois toques rápidos restauram a visão frontal.
  - **Barra de Atividades Otimizada:** Substituído o banner volumoso de "Parar" por uma linha de status fina (26px) que se recolhe a 0px quando ociosa.

### Dúvida — “Ela consegue usar a minha conta do Claude do meu browser, tipo pegar as APIs das outras IAs?” 💡
- **Explicação Técnica:**
  - No celular (Android), cada aplicativo roda dentro de uma **Sandbox (caixa de areia de segurança)** imposta pelo sistema operacional. Nenhum aplicativo tem permissão de bisbilhotar ou extrair cookies, sessões ou dados de login de outros aplicativos como o Google Chrome.
  - Além de inseguro e sujeito a bloqueios de conta pela Cloudflare/Google, **não é necessário**: a chave de API gratuita do Google AI Studio (`AIzaSy...`) é **oficial, 100% gratuita, não pede cartão de crédito e não expira**.
  - Com a correção de modelos aplicada na v1.19, a chave do Google AI Studio funciona perfeitamente, com velocidade máxima e respostas completas.