# Manual Geral do Projeto Zenith (Documento Único Consolidado)

**Idealizador e Desenvolvedor:** Anderson  
Automação Industrial · Iniciação Científica em Física e Matemática · São Paulo, 2026

> Este documento unifica toda a documentação técnica, guias de uso, decisões de engenharia (Handoff), roteiros de teste, publicação (GitHub + Vercel + Launcher), APIs gratuitas, robótica (ESP32-S3 + Arduino Uno) e roadmap que antes estavam espalhados em mais de 40 arquivos `.md`.

---

## Sumário

1. [Visão Geral, Conceito e Pilares](#1-visão-geral-conceito-e-pilares)
2. [Mapa da Arquitetura e Pastas do Projeto](#2-mapa-da-arquitetura-e-pastas-do-projeto)
3. [Histórico de Engenharia: O que já foi resolvido (Não repetir erros)](#3-histórico-de-engenharia-o-que-já-foi-resolvido-não-repetir-erros)
4. [Controle Inteligente de Aplicativos, Antivírus e Python 3.12/3.13](#4-controle-inteligente-de-aplicativos-antivírus-e-python-312313)
5. [APIs de Imagem 100% Grátis (Cloudflare Workers AI + Pollinations)](#5-apis-de-imagem-100-grátis-cloudflare-workers-ai--pollinations)
6. [Robótica e Automação Industrial (ESP32-S3 + Arduino Uno)](#6-robótica-e-automação-industrial-esp32-s3--arduino-uno)
7. [Roteiro Completo de Testes (Passo a Passo)](#7-roteiro-completo-de-testes-passo-a-passo)
8. [Como Compilar, Publicar e Atualizar (GitHub Release + Vercel + Launcher)](#8-como-compilar-publicar-e-atualizar-github-release--vercel--launcher)
9. [Autoajuste Seguro, APK Android e Roadmap de Próximos Passos](#9-autoajuste-seguro-apk-android-e-roadmap-de-próximos-passos)

---

## 1. Visão Geral, Conceito e Pilares

O **Zenith** é um assistente pessoal corporificado, multimodal e local:
- **Local primeiro:** Chaves (`config/settings.json`), conversas (`config/conversations.json`), memória vetorial (`memory_db/`) e criações (`creations/`) ficam no computador do usuário. Zero telemetria.
- **Corpo 3D + Cérebro Python:** O Cérebro (`brain/`) pensa, lembra e executa ferramentas; o Corpo (`body/zenith/`, Godot 4.7) desenha o avatar VRM numa janela transparente sempre no topo e a Central de Controle; a Ponte (`zenith_bridge.py` / `brain_connector.gd`) liga os dois via WebSocket local (`ws://localhost:8765`, buffer de 16 MiB).
- **Personalidade (Doçura e Amargor):** Base gentil e curiosa, com humor/ironia dosada (~75% humana no cotidiano; 100% exata e rigorosa em Física, Matemática, Programação e Automação).

### Os 6 Pilares Inegociáveis
1. **Consentimento Soberano (Gatekeeper):** Nenhuma ação sensível (`<executar_python>`, `<executar_terminal>`, `<editar_video>`, `<criar_programa>`, `<criar_documento>`, `<organizar_pasta>`, `<gerar_imagem>`, `<ver_tela>`, `<ver_camera>`, `<conectar_serial>`) roda sem aprovação explícita na janela modal. Há uma lista negra de vetos absolutos (apagar disco, desligar PC, mexer em firewall/antivírus).
2. **Empatia Dinâmica:** Ao notar frustração, tristeza ou seriedade real, o tom de brincadeira para imediatamente e vira suporte.
3. **Didática de Nível Avançado:** Dá a intuição antes da fórmula, explicita unidades e hipóteses, resolve exemplo passo a passo e verifica o entendimento.
4. **Auto-preservação e Diagnóstico:** Monitora cotas, latência e falhas, traduzindo erros técnicos (404, 413, 429, 503) para português claro.
5. **Contexto Evolutivo:** Sem "amnésia de peixe" — perfil fixo, busca semântica no ChromaDB e cartões aprendidos (`<aprender>`) aprovados pelo usuário.
6. **Protocolo Antirromântico e Origem Imutável:** Qualquer flerte ou romance é recusado com postura técnica e distante. O sistema declara sempre que foi criado por **Anderson**.

---

## 2. Mapa da Arquitetura e Pastas do Projeto

| Pasta / Arquivo | O que é |
|---|---|
| `zenith_launcher.py` | Ponto de entrada principal (vira o `Zenith.exe`). Redireciona logs para `zenith_log.txt`, sobe o Cérebro (`zenith_headless.py`) em thread e abre o Corpo exportado (com fallback de vídeo `normal → sem-aa → seguro`). |
| `INICIAR_ZENITH.py` / `tools/instalar_zenith.py` | Descobre o Python 3.13 ou 3.12 da máquina, cria `.venv`, instala `requirements.txt` e abre o Zenith sem usar `.bat`. |
| `brain/zenith_core.py` | Núcleo do Cérebro: monta o prompt com a Bíblia (`zenith_biblia.py`), o contexto da conversa (`zenith_contexto.py`), chama os provedores em rodízio (`zenith_chaves.py`, `zenith_rota.py`), valida a resposta (`zenith_validator.py`) e extrai tags de ação/corpo. |
| `brain/zenith_headless.py` | Servidor WebSocket (`ws://localhost:8765`) que conversa com o Godot sem abrir janela Tkinter. |
| `brain/zenith_commands.py` | Despachante de todos os comandos `/` (`/ajuda`, `/modelo`, `/inteligencia`, `/contexto`, `/video`, `/imagem`, `/tft`, `/observar`, `/organizar`, `/quarentena`, `/biblioteca`, `/ditado`, `/conversa`, `/saude`, `/sobre`, `/versao`). Comandos desconhecidos nunca vão para a IA. |
| `brain/zenith_executor.py` & `zenith_gatekeeper.py` | Execução protegida com timeout configurável (`tempo_comando_s`: padrão 60 s, mín. 15 s, máx. 1800 s) e registro em `zenith_parar.py` para o botão **⏹ Parar** matar o processo real. |
| `brain/zenith_interaction.py`, `zenith_ditado.py`, `zenith_conversa_loop.py` | Voz (Edge-TTS >= 7.3.0 + RVC opcional), escuta por microfone (faster-whisper) e ditado ao vivo com LocalAgreement-2. |
| `brain/zenith_img.py` & `zenith_imagem_ia.py` | Criação de imagens por código (Pillow: `meme`, `cartaz`, `citacao`, `gradiente`, `colagem`, `autorretrato`) e por IA (`<gerar_imagem>` / `/imagem`). |
| `brain/zenith_video.py` | Edição e criação de vídeo com `ffmpeg` real (`cortar`, `juntar`, `velocidade`, `gif`, `legenda`, `slides`, `narrar` videoaulas com equações). |
| `brain/zenith_anexos.py`, `zenith_documentos.py`, `zenith_organizar.py`, `zenith_biblioteca.py` | Leitura segura de anexos (PDF, Word, Excel, PowerPoint, zip) em quarentena (`<conteudo_externo>` = dado, nunca ordem), geração de `.docx`/`.xlsx`, organização de pastas com desfazer e busca BM25 em apostilas/PDFs. |
| `body/zenith/` | Projeto Godot 4.7: `ui_manager.gd` (Central de Controle), `akira_body.gd` + `akira_vida.gd` (avatar VRM, expressões, respiração, SubViewport), `brain_connector.gd` (WebSocket 16 MiB), `zenith_estudio.gd` (temas e aparência), `zenith_chaves_page.gd`, `zenith_saude_page.gd`. |
| `launcher/` | `zenith_instalador.py` (código do `ZenithLauncher.exe` e da janela `JanelaLimpeza`), `limpar.py` (`LimparZenith.exe`) e `build_launcher.py`. |
| `firmware/` & `skills/carrinho.py` | Firmware do ESP32-S3 (`carrinho_esp32s3.ino`, TFT + Wi-Fi TCP 7777 + UDP 7778 + BLE) e do Arduino Uno (`carrinho_uno.ino`, 4 motores HW-130) + skill Python que controla o carrinho. |
| `site/` | Site publicado na Vercel (`index.html`, `latest.json`, `versions.json`, `vercel.json`, `docs/*.docx`). |
| `tools/` | `preparar_publico.py` (limpa dados pessoais e valida a edição pública), `gerar_release.py` (gera `Zenith_app_<v>.zip` e atualiza `site/latest.json`), `gerar_documentos.py` (gera os `.docx`), `gerar_pacote_pendrive.py`. |
| `tests/` | Suíte com mais de 1.500 testes (`py -3 -m unittest discover -s tests`), sem depender de rede, Godot ou chaves reais. |

---

## 3. Histórico de Engenharia: O que já foi resolvido (Não repetir erros)

1. **Nunca pedir permissão em texto (Regra de Ouro nº 10):** A IA não deve responder *"Posso rodar o código?"* ou citar tag vazia. Ela diz em uma frase o que vai fazer e coloca a tag completa (`<executar_python>...</executar_python>`); o `zenith_validator.py` intercepta e refaz a resposta se ela pedir permissão em texto.
2. **Por que IAs fora do Gemini "perdiam a memória" (v22):** Antes só o Gemini tinha sessão em memória; OpenAI, Groq, OpenRouter e IA local recebiam apenas a pergunta solta. Resolvido em `zenith_contexto.py`, que envia o histórico da conversa salva para qualquer provedor respeitando o orçamento de tokens.
3. **Erro 413 no Groq e Falsos Positivos no Teste de Chave do Gemini (v1.10):**
   - No Groq, o erro 413 era excesso de tokens por minuto (teto de contexto ajustado e retry automático sem histórico).
   - No Gemini, `models.list()` dava "Chave válida" mesmo quando todos os modelos respondiam 503/404. Corrigido com chamada real de chat no teste de chave.
4. **"Avatar Fantasma" na Transparência (v21):** Mexer no `alpha` de cada malha MToon fazia o interior da boca/corpo aparecer através da roupa/cabelo. Solução definitiva em `akira_body.gd`: desenhar o avatar 100% opaco numa `SubViewport` dedicada e aplicar `modulate.a` na textura inteira.
5. **Tela Preta no Avatar em Placas Antigas (01/11/2026):**
   - Causa: `window/hdr/request_hdr_output=true` + `MSAA 4x + FXAA` em janela transparente sem borda em GPUs Intel HD antigas.
   - Solução: HDR desligado no `project.godot`, `_aa_pode_ligar()` em `akira_body.gd` desligando AA em GPUs antigas, e fallback automático `normal → sem-aa → seguro` no `zenith_launcher.py`.
   - **Atenção:** Sempre que alterar arquivos em `body/zenith/`, é obrigatório **reexportar o Corpo no Godot** (`body/zenith/export/Zenith.pck` e `Zenith.exe`) antes de gerar o `Zenith_app_<versao>.zip`.
6. **`print()` sumindo no `.exe` compilado (v1.10):** O build usa `--noconsole`; por isso `--zenith-run-script` religa `stdout`/`stderr` à força ao rodar scripts criados pela IA.
7. **Build apagando dados do usuário (v1.0 / v29):** `build_exe.py` agora move `config`, `memory_db`, `models`, `creations`, `temp` e `skills` para `_dados_do_usuario_resgatados` antes de limpar `dist/`, confere arquivo por arquivo (existência + tamanho) na devolução e aborta sem apagar o resgate se algo falhar.
8. **Arquivos `.py` com CRLF:** `zenith_core.py`, `zenith_executor.py`, `zenith_gatekeeper.py` e `zenith_memory.py` usam quebras de linha CRLF e devem ser preservados.

---

## 4. Controle Inteligente de Aplicativos, Antivírus e Python 3.12/3.13

Detalhes completos também em `NOTES_ANTIVIRUS.md` (mantido na raiz porque `tests/test_v24.py` verifica sua presença).

### Por que o Controle Inteligente de Aplicativos (Smart App Control) bloqueia
O Windows 11 bloqueia binários `.exe` e `.pyd` recém-compilados sem assinatura digital Authenticode ou sem reputação na nuvem:
1. **Python 3.14 (`cp314`) vs Python 3.12 / 3.13:** No Python 3.14, bibliotecas nativas como `_pybase64.cp314-win_amd64.pyd` ainda têm pouca reputação no catálogo da Microsoft e disparam *"Parte deste aplicativo foi bloqueada"*. **Sempre gere os builds e o ambiente com Python 3.12 ou 3.13** (`tools/instalar_zenith.py` já escolhe 3.13 ou 3.12 automaticamente).
2. **`--onedir` vs `--onefile`:** Executáveis gerados pelo PyInstaller com `--onefile` extraem DLLs e `.pyd` para `%TEMP%\_MEIxxxxx` e executam de lá toda vez que abrem — comportamento idêntico ao de *droppers*, que o Controle Inteligente e heurísticas de antivírus bloqueiam. O app principal já usa `--onedir` sem UPX.
3. **Nada de `.bat` baixado da internet:** O SmartScreen bloqueia `.bat` com MOTW (Mark of the Web). Por isso a inicialização usa `INICIAR_ZENITH.py` e `build_exe.py`.

---

## 5. APIs de Imagem 100% Grátis (Cloudflare Workers AI + Pollinations)

O plano gratuito do Google AI Studio (Gemini) não inclui geração de imagens (retorna HTTP 429). As duas opções gratuitas reais verificadas são:

1. **Cloudflare Workers AI (`@cf/black-forest-labs/flux-1-schnell`) — Principal:**
   - **Grátis:** 10.000 neurons/dia sem cartão de crédito (dá para centenas/milhares de imagens 1024×1024 com `steps=4`).
   - Endpoint: `https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/@cf/black-forest-labs/flux-1-schnell`
   - Requer `Account ID` + `API Token` (template *Workers AI*).
2. **Pollinations.ai — Reserva (Zero configuração, sem chave):**
   - URL direta: `https://image.pollinations.ai/prompt/<prompt_url_encoded>?width=768&height=768&nologo=false`
   - Limite: 1 imagem a cada 45 s por IP (HTTP 402 com `Retry-After` se exceder).

---

## 6. Robótica e Automação Industrial (ESP32-S3 + Arduino Uno)

Manual de pinos detalhado em `firmware/LEIA-ME.md` (mantido em `firmware/` porque `tests/test_v24.py` o verifica).

- **Arquitetura do Carrinho:**
  - **ESP32-S3 (`firmware/carrinho_esp32s3/carrinho_esp32s3.ino`):** Exibe o rosto da Zenith no display TFT ST7789/ILI9341 (recebe quadros JPEG na porta TCP `7777`), anuncia o próprio IP por broadcast UDP na porta `7778` a cada 3 s, aceita comandos HTTP/BLE (`Zenith_Carrinho`) e envia comandos de movimento pelo pino TX para o pino `A0` (SoftwareSerial 9600 baud) do Arduino Uno.
  - **Arduino Uno (`firmware/carrinho_uno/carrinho_uno.ino`):** Controla o Motor Shield HW-130 (`AFMotor.h`) com 4 motores DC (M1/M2 direita, M3/M4 esquerda). Possui fila autônoma de até 6 passos (`F 5000 140`, `B 2000`, `L 700`, `R 700`, `S`).
  - **Trava de Segurança dos Motores:** `VEL_MAX = 150` (58% PWM, entregando ~6 V médios a partir da bateria de 12 V para proteger os motores de 5 V) e `DUR_MAX_MS = 10000` (10 s por passo).
- **Ordem de procura em `skills/carrinho.py`:**
  1. IP salvo em `config/carrinho.json`
  2. IP informado na mensagem (`carrinho ip 192.168.x.x`)
  3. Descoberta automática UDP na porta `7778`
  4. Ponto de acesso próprio do carrinho (`192.168.4.1`, rede `Zenith_Carrinho`)
  5. Cabo USB (serial)
- **Reset de fábrica das redes do ESP32-S3:** Botão na página `http://192.168.4.1`, segurar botão físico `BOOT` por 8 segundos, ou enviar `RESET` na Serial 115200.

---

## 7. Roteiro Completo de Testes (Passo a Passo)

1. **Suíte Automatizada (Python puro, sem rede):**
   ```powershell
   py -3.12 -m unittest discover -s tests
   ```
2. **Abertura e Corpo (Godot):**
   - Abrir o Zenith (`python zenith_launcher.py` ou `dist\Zenith\Zenith.exe`).
   - Verificar bolinha verde ("Conectado ao Cérebro") e se o avatar 3D aparece sem fundo preto (se a placa for antiga, testar `"body_video_modo": "seguro"` ou `/fundo_avatar solido`).
3. **Chaves e Conversa com IA:**
   - Em *Configurações → Chaves*, testar a chave do Gemini ou Groq.
   - Enviar `"Oi! Acene pra mim"` → deve responder e mover o avatar (`<corpo>gesto:acenar</corpo>`).
4. **Gatekeeper e Execução de Código:**
   - Pedir `"Rode um script Python que calcule os 10 primeiros quadrados perfeitos"` → deve abrir a janela de confirmação (sem pedir permissão em texto antes) e mostrar a saída do `print()` no chat.
5. **Imagens, Anexos e Vídeo:**
   - Pedir `"Faça um meme sobre programação"` → gera imagem com `zenith_img.meme()` e exibe no chat.
   - Colar um print com `Ctrl+V` (e anexar mais um arquivo pelo clipe 📎) → os cartões de anexo somam na barra com miniatura e botão `✕`.
6. **Voz e Microfone:**
   - Testar `/ditado` e `/conversa ligar`.
7. **Carrinho (ESP32-S3):**
   - Testar `/tft porta wifi:auto` e `"onde está o carrinho"`.

---

## 8. Como Compilar, Publicar e Atualizar (GitHub Release + Vercel + Launcher)

### Endereços Oficiais
- **Repositório de Distribuição:** `https://github.com/AndersonScript/Projeto-Zenith`
- **Site (Vercel):** `https://projeto-zenith-five.vercel.app` (Root Directory na Vercel deve ser `site`, Framework Preset `Other`).

### Passo a Passo de uma Nova Versão
1. **Exportar o Corpo no Godot (se mudou algo em `body/zenith/`):**
   Exportar para `body/zenith/export/Zenith.exe` + `Zenith.pck`.
2. **Gerar o Executável do Launcher (se mudou `launcher/`):**
   ```powershell
   py -3.12 launcher/build_launcher.py --site https://projeto-zenith-five.vercel.app
   ```
3. **Montar a Pasta Pública Limpa (varre chaves, caminhos pessoais e avatares):**
   ```powershell
   py -3.12 tools/preparar_publico.py
   ```
   Copie `body\zenith\export` para dentro da pasta gerada em `dist_publico\Zenith_Publico_v<versao>\body\zenith\export`.
4. **Gerar o Zip da Release e Atualizar `site/latest.json` e `site/versions.json`:**
   ```powershell
   py -3.12 tools/gerar_release.py --versao 1.0 --pacote dist_publico/Zenith_Publico_v1.0 --base-url https://github.com/AndersonScript/Projeto-Zenith/releases/download/v1.0 --launcher-exe dist_launcher/ZenithLauncher.exe --notas "Notas da versão"
   ```
5. **Subir na Release do GitHub e dar Push no Repositório:**
   - Na Release do GitHub (`releases/tag/v1.0`), subir `release/Zenith_app_1.0.zip`, `dist_launcher/ZenithLauncher.exe` e `dist_launcher/LimparZenith.exe`.
   - Fazer commit e push de `site/`, `launcher/` e `dist_launcher/` para o repositório `AndersonScript/Projeto-Zenith`.

---

## 9. Autoajuste Seguro, APK Android e Roadmap de Próximos Passos

- **Autoajuste (`brain/zenith_autoajuste.py`):** O Zenith nunca reescreve os próprios arquivos em `brain/`. Qualquer proposta de melhoria de código vai para `config/ajustes/propostas/`, exige `py_compile` + suíte de testes passando + aprovação no Gatekeeper, e é carregada como *overlay* em `config/ajustes/overlay/`. Se falhar 2 vezes no boot (`boot.json`), vai para quarentena automaticamente.
- **Port para Android (Planejado):** O Cérebro em Python pode rodar em segundo plano (ou na nuvem/PC local na mesma rede) enquanto o Corpo em Godot 4.7 é exportado como APK Android conectando via WebSocket ao IP do Cérebro.
- **Próximos Upgrades Prioritários:**
  1. **Design Profissional no Godot (`ui_manager.gd`):** Cápsula de digitação unificada, balões de chat com botão de copiar código/resposta, sidebar com cartão de status e navegação de Configurações em pílulas.
  2. **Download Resiliente no Launcher (`zenith_instalador.py`):** Retomada automática (`HTTP Range`) e múltiplas tentativas para não cair no meio dos 75 MB.
  3. **Geração de Imagens Grátis (`zenith_imagem_ia.py`):** Integrar Cloudflare Workers AI (FLUX.1 schnell) + Pollinations.ai.
  4. **Roteador de Especialistas (`zenith_core.py`):** Selecionar perfil (Programadora, Professora de Exatas, Pesquisadora, Automação) antes da resposta.
  5. **Voz Ao Vivo e Barge-in (`zenith_conversa_loop.py`):** Mostrar transcrição parcial ao vivo no chat e interromper a fala da Zenith ao falar.
