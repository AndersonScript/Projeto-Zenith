# ZENITH — DOCUMENTO MESTRE
### Programação, decisões, reclamações e ideias · 10/11/2026

---

## PARTE 0 — Sobre este documento

**O que ele é:** o registro completo do Zenith reunido nesta conversa — como o programa é construído por dentro, por que cada escolha foi feita, o que reclamou, o que foi corrigido, o que ficou pendente e o que ainda é só ideia.

**Como foi levantado:** medições reais feitas durante a conversa (contagem de testes, tamanhos, hashes, compilações) + o histórico técnico registrado. Onde não houve acesso ao código, está marcado como lacuna na Parte 10 — não há invenção de detalhe.

**Status:** ✅ feito e verificado · 🟡 corrigido, falta publicar · ⏳ pendente · 💡 ideia · ⚠️ armadilha

---

## PARTE 1 — O produto

O Zenith é um assistente para Windows com interface própria, memória local das conversas, geração de imagens e ligação opcional com uma tela física (ESP32-S3 + TFT). Funciona com provedores de IA escolhidos pelo usuário, incluindo opções **gratuitas**, e guarda os dados numa pasta definida pelo usuário.

**Promessas que o projeto assumiu:**
1. Não exigir que o usuário instale Python nem configure ambiente.
2. Ser gratuito no uso básico, com caminho grátis real para imagem.
3. Nunca esconder o que está fazendo (cartões de atividade, mensagens de erro com motivo).
4. Não misturar dados pessoais com o pacote público.
5. Deixar o usuário decidir onde ficam programa e dados.

---

## PARTE 2 — Programação

### 2.1 Arquitetura em cinco camadas

```
SITE (Vercel)      → apresenta, publica versão, redireciona download
   ↓ /baixar (307)
LAUNCHER (.exe)    → instala/atualiza, escolhe pastas, resolve Python, confere hash
   ↓ instala venv + app
APP (Tkinter+brain)→ Central de Controle: conversa, cartões, imagem, memória
   ↓ serial USB              ↓ HTTP
ESP32-S3 (TFT/Wi-Fi)     Provedores de IA (texto/imagem)
```

**Racional:** isolar camadas para que uma falha não derrube as outras e para que cada correção tenha um lugar óbvio. Quase todos os problemas desta conversa foram resolvidos tocando **uma** camada.

### 2.2 Site (`site/`)

| Arquivo | Conteúdo | Papel técnico |
|---|---|---|
| `index.html` | página única (~442 linhas) | cartão de download montado por JS: `pegar("latest.json")` → `baixar(m)` → injeta em `#ultima` |
| `latest.json` | versão 1.0 · `Zenith_app_1.0.zip` (75.272.569 B) · Python 3.12.10 · launcher/limpar 1.0.1 | **fonte da verdade** de versão, URL, tamanho e SHA-256 |
| `versions.json` | histórico | registro de versões anteriores |
| `vercel.json` | redirects e `cleanUrls` | `/baixar` → Release do GitHub · `/limpar` → limpador |

**Decisões de design da página:** passos numerados (baixar → escolher pastas → usar), cartão “Onde o arquivo é salvo” (quem decide é o navegador) e “Onde ficam os seus projetos” (quem decide é o launcher). Objetivo: eliminar a dúvida “onde foi parar o arquivo”.

**Causa do incidente R05:** o projeto na Vercel publicava a pasta errada (Root Directory), servindo um app Vue com título `frontend`; por consequência `/latest.json` devolvia HTML. Correção: Root Directory = `site`, Framework `Other`, build/output vazios, redeploy sem cache.

### 2.3 Launcher (`launcher/zenith_instalador.py`, 1.545+ linhas)

**Funções e responsabilidade:**

| Função | O que faz | Por que existe |
|---|---|---|
| `raiz_padrao()` | caminho padrão (`%LOCALAPPDATA%\Zenith`) | sugestão inicial na tela de escolha |
| `pythons_instalados()` | varre `HKCU/HKLM\Software\Python\PythonCore\*\InstallPath` + `%LOCALAPPDATA%\Programs\Python` | o instalador oficial devolve código 0 sem instalar quando a versão já existe |
| `python_exe()` | resolve o interpretador (venv → sistema) | nunca depender de `python` no PATH |
| `caminhos_do_app()` | lê `instalacao.json` e devolve onde app/dados moram | desacopla programa de dados |
| `instalar_python()` | executa com `/log`, lê `tmp/python_instalacao.log`, valida `import tkinter, ssl, sqlite3, venv`, e se falhar **copia** instalação válida | sem `tkinter` não há UI; sem `ssl` não há download; sem `venv` não há isolamento |
| `instalar_ou_atualizar(pasta, dados=None, ...)` | baixa ZIP, confere SHA-256, extrai, cria venv, instala dependências, grava `instalacao.json` | um único caminho para instalar e atualizar |
| `executar_launcher()` | inicia o app e encerra; `--esperar-pid` espera o processo antigo | atualização não pode acontecer com o app aberto |
| `JanelaEscolha` | duas pastas (programa/dados), “Escolher…”, “Instalar aqui”, “Cancelar” | R04 — usuário decide onde instala |
| `JanelaTk` | progresso da instalação | retorno visível durante etapas longas |
| `JanelaLimpeza` | “O que você quer apagar?” | limpeza seletiva, não destrutiva |
| `main()` | modos: tela nova (instalação limpa), `--pasta`, `--dados`, `--atualizar`, `--reverter`, `--esperar-pid`; fallback `sem-tk` | tela só aparece onde faz sentido, sem quebrar automação |

**Fluxo de decisão da instalação:** descobrir ambiente → garantir pastas escolhidas → baixar com verificação → montar venv → gravar estado → criar atalho → abrir app. A ordem importa: baixar antes de saber onde gravar foi o que fazia o instalador parecer travado.

### 2.4 App e `brain/`

| Módulo | Responsabilidade | Detalhe conhecido |
|---|---|---|
| `brain/zenith_core.py` | orquestra conversa e cartões | `_com_cartao` (~linha 1618) cria/atualiza o cartão; só conclui com resultado ou falha |
| `brain/zenith_atividade.py` | títulos/estado dos cartões | `parece_falha` decide verde vs. vermelho (R09) |
| `brain/zenith_tft.py` | envio da imagem para TFT por serial | baud automático 115200 → 921600, com `_motivo` registrando a razão da escolha |
| `brain/zenith_settings.py` | preferências | `tft_baud` e chaves de provedores |
| `brain/zenith_imagegen.py` | geração de imagem | provedor configurável (Cloudflare / Pollinations) |

**Regra de produto embutida no código:** cartão verde antes do resultado destrói a confiança na tela inteira — por isso a verificação de falha é parte do fluxo, não enfeite.

### 2.5 Firmware (`firmware/carrinho_esp32s3/carrinho_esp32s3.ino`)

- **Wi-Fi:** `escanearEEscolher` lista redes; `tentativaCega` tenta a rede salva mesmo invisível (oculta); prazo de 30 s nesse caso.
- **Diagnóstico:** imprime `wifiTipo()`, canal, RSSI, `[WIFI] tentando entrar em ...` e `[WIFI] nao entrou em '%s' — codigo %d`.
- **Configuração:** `USAR_BLE` (~linha 44) e `TEM_VRM` (~linha 45) adaptam a mesma placa a montagens diferentes.
- **Integridade do arquivo:** chaves 146/146 e parênteses 708/708 balanceados — **não compilado** (não há ESP32 core nesta máquina).
- **Causa raiz do R07:** `WiFi.scanNetworks()` sem `show_hidden` não lista rede oculta, então a rede “não existia” para o código.

### 2.6 Ferramentas (`tools/`, `build_exe.py`)

| Ferramenta | Faz | Quando |
|---|---|---|
| `build_exe.py` | compila `dist\Zenith\Zenith.exe` (PyInstaller, ~10 min) | mudanças no `brain/` |
| `launcher/build_launcher.py --site <url>` | compila launcher + limpador (~2 min) | mudanças no instalador |
| `tools/preparar_publico.py` | higieniza e **barra** `Itaquera|Itaquaera|Caderno Aberto|ander` e o nome antigo | sempre antes de publicar |
| `tools/gerar_release.py` | gera ZIP, calcula SHA-256, reescreve `latest.json`/`versions.json` | a cada versão |
| `tools/gerar_pacote_pendrive.py` | ZIP único para o pendrive | ao atualizar o pen drive |
| `prepare_pendrive.py` | **zera** a cópia (tira chaves/conversas) | só quando o objetivo é distribuir limpo |

### 2.7 Dados: onde fica o quê

| Caminho | Conteúdo | Vai para o público? |
|---|---|---|
| `config/` | chaves de API, preferências | ❌ nunca |
| `creations/` | imagens e criações | ❌ nunca |
| `memory_db/` | SQLite de conversas | ❌ nunca |
| `chaves_estado.json` | estado das chaves | ❌ nunca |
| `instalacao.json` | pastas escolhidas + versão | ❌ local |

### 2.8 Pipeline de publicação

```
código → testes → build_exe / build_launcher → preparar_publico (higieniza)
      → gerar_release (ZIP + SHA-256 + latest.json) → upload na Release
      → commit do site → Vercel publica → conferir /latest.json e /baixar
```

⚠️ **Ordem obrigatória:** Release **primeiro**, hash **depois**. Invertido, o launcher recusa o download (“hash não confere”).

### 2.9 Verificações feitas nesta conversa

- Suíte completa: **1.527 testes OK** (~130 s). `tests/test_v24.py`: 32 OK.
- Launcher: **46 testes OK** (`test_launcher` + `test_v30_launcher_print`), `py_compile` OK.
- `JanelaEscolha()` instanciada com sucesso (`TELA_OK`).
- `dist_launcher\ZenithLauncher.exe` — 12.777.857 B · sha256 `7bbee9c4…49552f17`
- `dist_launcher\LimparZenith.exe` — 12.780.293 B · sha256 `b465117b…c21375a6`
- `C:\Zenith\Zenith_PENDRIVE_1.0.zip` — 1,95 GB, 4.925 itens, sha256 `6b3bc1d3…822e364d`
- `D:\Zenith\dist\Zenith` — 4.096 arquivos copiados preservando `config`, `creations`, `memory_db`.

### 2.10 Armadilhas técnicas aprendidas

| # | Armadilha |
|---|---|
| A01 | `run_terminal_command` recusa timeout > 300 s; jobs longos vão em BACKGROUND |
| A02 | Release antes do hash, nunca o contrário |
| A03 | Git Bash converte `/E` em caminho → usar `//E //XD` no `robocopy` |
| A04 | `code_search`/`glob` com cwd relativo não alcançam `C:\Zenith\Zenith` (fora do workspace) |
| A05 | `latest.json` devolvendo HTML = Root Directory errado, não bug de JS |
| A06 | Instalador do Python retorna 0 sem instalar quando a versão já existe |
| A07 | `getaddrinfo failed` = rede/DNS do PC, não bug do app |
| A08 | Rede oculta não aparece em `scanNetworks()` sem `show_hidden` |
| A09 | Cartão de atividade fechado cedo = usuário perde a confiança na tela |

---

## PARTE 3 — Reclamações

| # | Reclamação | Causa | Status |
|---|---|---|---|
| R01 | Imagem não funciona / quer cobrar | provedores sem camada grátis real | ✅ duas opções grátis |
| R02 | “Atualizar todos os arquivos compactos” | ZIP e hashes defasados | 🟡 ZIP ok; hashes dependem do upload |
| R03 | Tela de download muito feia | cartão cru, sem contexto | ✅ refeito |
| R04 | Não poder escolher onde baixar / onde ficam os projetos | launcher decidia tudo | ✅ `JanelaEscolha` + `--pasta/--dados` |
| R05 | Site mostrava outro programa | Root Directory da Vercel | 🟡 tutorial pronto, falta aplicar |
| R06 | Launcher falhava no Python (código 0, detalhe vazio) | instalador ignora `TargetDir` quando versão existe | ✅ detecção + cópia + log |
| R07 | ESP32-S3 não entrava no Wi-Fi | rede oculta não listada | ✅ `tentativaCega` + diagnóstico |
| R08 | TFT travando pelo cabo | 115200 baud insuficiente | ✅ 921600 automático |
| R09 | “Pesquisa feita” verde antes do resultado | cartão concluído cedo | ✅ `parece_falha` |
| R10 | `getaddrinfo failed` nas IAs | sem internet/DNS no PC | ✅ esclarecido (não era bug) |
| R11 | Teclado com teclas defeituosas | hardware | ⚠️ registrado, sem correção de texto |
| R12 | Falta tutorial de arrumar o site | — | ✅ `docs/TUTORIAL_ARRUMAR_SITE.md` |
| R13 | Falta tutorial das APIs | listas de “grátis” mentem | ✅ `docs/APIS_DE_IMAGEM_GRATIS.md` |

---

## PARTE 4 — Suas ideias

| # | Ideia | Status |
|---|---|---|
| I01 | Imagem 100% grátis, sem cartão | ✅ |
| I02 | Escolher pasta do download e dos projetos | ✅ |
| I03 | Site bonito | ✅ |
| I04 | Pacotes compactos sempre atualizados | 🟡 |
| I05 | Tutoriais passo a passo | ✅ |
| I06 | Firmware do carrinho funcionando | ✅ código / ⏳ compilar |
| I07 | Pendrive preservando chaves e conversas | ✅ |
| I08 | Limpador que pergunta o que apagar | ✅ |
| I09 | Launcher resolve o Python sozinho | ✅ |
| I10 | Central de Controle com cartões coerentes | ✅ |

---

## PARTE 5 — Ideias e propostas técnicas

### P01 — Imagem grátis
- **Cloudflare Workers AI** — `@cf/black-forest-labs/flux-1-schnell` · 10.000 neurons/dia, **sem cartão** · 1024×1024 · sem marca · ~US$ 0,00063/imagem (steps ≤ 8) · cota estourada = recusa até 00:00 UTC, **sem cobrança**.
- **Pollinations** — `image.pollinations.ai/prompt/<texto>?width=768&height=768` · **sem chave** · 768×768 · 1 img/45 s · com marca · limite = HTTP 402 com `Retry-After`.
- **Ordem:** Cloudflare principal, Pollinations reserva.
- **Pagas (referência):** fal/Replicate/Novita US$ 0,003 · Together FLUX.2 dev US$ 0,0154 (sem teste grátis) · Gemini ~US$ 0,04 · HF só PRO US$ 2/mês.
- **Local:** ComfyUI (API HTTP), Fooocus, AUTOMATIC1111 (`--api`), diffusers.

### P02 — Launcher com tela de pastas (executado)
Duas caixas de caminho, `filedialog`, validação, `--pasta/--dados`, fallback sem Tk.

### P03 — Site explicando o que não é dele (executado)
Cartões “Onde o arquivo é salvo” e “Onde ficam os seus projetos”.

### P04 — Release automatizada (executado)
`preparar_publico.py` + `gerar_release.py` com hash calculado, nunca digitado.

### P05 — Rede oculta no firmware (executado)
`tentativaCega`, prazo estendido, diagnóstico no Serial.

### P06 — Baud do TFT no app (executado)
921600 automático com registro do motivo, em vez de recompilar firmware.

---

## PARTE 6 — Backlog (ideias ainda não feitas)

- 💡 Pollinations como padrão no app, com troca automática para Cloudflare ao estourar cota.
- 💡 Auto-atualização do launcher ao abrir (comparar com `latest.json`).
- 💡 Mostrar no app qual pasta de dados está em uso.
- 💡 Tela de diagnóstico exibindo `tmp/python_instalacao.log`.
- 💡 Seletor de pasta também ao criar novo projeto, não só na instalação.
- 💡 Página “Como funciona” publicada no site (texto pronto nesta conversa).

---

## PARTE 7 — Pendências

1. Vercel: Root Directory = `site` + Redeploy (R05).
2. Subir `ZenithLauncher.exe` e `LimparZenith.exe` na Release.
3. Depois do upload: atualizar `launcher.sha256`/`tamanho` e `limpar.sha256`/`tamanho` no `latest.json` + push.
4. Compilar o firmware em máquina com ESP32 core.
5. Domínio próprio/DNS (opcional).
6. Nada foi commitado nem publicado nesta conversa.

---

## PARTE 8 — Como eu penso um problema daqui

1. **Separar sintoma de causa.** “Site feio” era CSS; “site mostra outro app” era Root Directory — mesma página, causas opostas.
2. **Procurar o nível certo.** Cabo lento se resolve no app (baud), não no firmware.
3. **Desconfiar de “deu certo”.** Código 0 do Python era mentira; hash declarado pode ser de outro arquivo.
4. **Nunca misturar público com pessoal.** `config`/`creations`/`memory_db` ficam fora do pacote, com checagem que falha de propósito.
5. **Manter o usuário no controle.** Pastas, o que apagar, qual provedor — decisões que mudam a vida dele não ficam escondidas em constante.
6. **Texto embaralhado?** Confirmar antes de mexer; mexer no lugar errado custa mais que perguntar.

---

## PARTE 9 — Glossário

**Launcher** instalador/atualizador · **SHA-256** impressão digital do arquivo · **cota** limite gratuito diário do provedor · **venv** ambiente Python isolado · **TFT** tela ligada à placa · **ESP32-S3** microcontrolador do carrinho · **rede oculta** Wi-Fi que não transmite o nome · **cartão de atividade** bloco na Central de Controle que mostra o que está acontecendo.

---

## PARTE 10 — Lacunas assumidas

Este documento é completo **no que foi tratado nesta conversa**, mas não é a leitura do código-fonte. Faltam, por dependerem do computador acessível:

- lista real de todos os módulos do `brain/` (citei os cinco conhecidos);
- assinatura e corpo de cada função, com número de linha;
- formato completo de `instalacao.json`, `chaves_estado.json` e do esquema SQLite;
- protocolo serial app ↔ ESP32 (comandos e formato dos pacotes de imagem);
- conteúdo integral do `.ino` (pinos, bibliotecas, tratamento de `USAR_BLE`/`TEM_VRM`);
- funções reais do JS do site além de `pegar()`/`baixar()`.

Quando houver acesso, isso vira a **Parte 2.11 — Mapa do código**, gerada por varredura de arquivos, com cada afirmação apontando arquivo e linha. Aí o documento deixa de depender de memória.

*Fim do documento.*

---

## PARTE 2.11 — Mapa Completo do Código (Gerado por Varredura Real do Disco)

Esta seção preenche integralmente a lacuna apontada na Parte 10, varrendo todos os módulos de `brain/` (Python) e `body/zenith/` (Godot 4.7 GDScript).

### A. Cérebro Python (`brain/` — 98 módulos)

| Arquivo | Linhas | Papel / Descrição | Principais Classes e Funções (com linha) |
|---|---:|---|---|
| `brain/aplicar_wifi_tft.py` | 291 | Zenith — liga o display TFT do ESP32-S3 por WI-FI (além da USB). | `_ler` (L210), `_gravar` (L216), `_trocar` (L222), `aplicar` (L229), `desfazer` (L270) |
| `brain/zenith_actionlog.py` | 146 | Zenith — Log de ações aprovadas (Pilar 1: consentimento explícito). | `_caminho_padrao` (L41), `mascarar_segredos` (L46), `_trecho` (L52), `registrar` (L58), `recentes` (L87), `formatar_recentes` (L112) (+1) |
| `brain/zenith_admin.py` | 104 | Zenith — PRIMEIRA ABERTURA DO .EXE COMO ADMINISTRADOR (v26). | `e_admin` (L38), `decidir` (L49), `marcar` (L71), `perguntar_reabrir` (L80), `reabrir_como_admin` (L93) |
| `brain/zenith_anexos.py` | 527 | Zenith — ANEXOS DE QUALQUER TIPO (v28). | `tamanho_legivel` (L53), `tipo_do_arquivo` (L63), `_limpar_xml` (L84), `_ler_zip_membro` (L91), `texto_docx` (L103), `texto_pptx` (L116) (+20) |
| `brain/zenith_atividade.py` | 81 | v1.3 — cartões de atividade no meio do chat ("Adicionando à memória…", "Executando código…", "Pesquisando na w | `novo_id` (L41), `_cortar` (L45), `montar` (L52), `descrever_acao` (L65), `parece_falha` (L76) |
| `brain/zenith_atualizar.py` | 204 | Zenith — atualização com segurança (v1.5, tarefa T9). | `_contexto_ssl` (L32), `_obter_padrao` (L48), `_url_ok` (L56), `consultar` (L63), `ha_novidade` (L88), `planejar` (L100) (+4) |
| `brain/zenith_autoajuste.py` | 553 | Zenith — a IA propõe consertos no PRÓPRIO código; quem decide é o usuário (v1.6.2). | `class ErroAjuste` (L68), `_contar` (L72), `_imports` (L76), `_stdlib` (L90), `normalizar_arquivo` (L94), `extrair_propostas` (L100) (+4) |
| `brain/zenith_biblia.py` | 327 | Zenith — a "Bíblia": conhecimento equalizado para qualquer IA (v21). | `_norm` (L224), `_preencher` (L229), `carregar_extra` (L234), `bloco_fixo` (L254), `secoes_para` (L265), `guia_para` (L281) (+1) |
| `brain/zenith_biblioteca.py` | 310 | Zenith — BIBLIOTECA DE DOCUMENTOS (v28) — o "NotebookLM local". | `class ErroBiblioteca` (L48), `_pasta_padrao` (L52), `_sem_acento` (L57), `tokenizar` (L61), `_quebrar_em_trechos` (L67), `extrair_paginas` (L87) (+5) |
| `brain/zenith_boas_vindas.py` | 27 | Zenith — Aviso de primeiro uso (roadmap 4.4.1: "Aviso explícito no primeiro uso"). | `deve_mostrar` (L22) |
| `brain/zenith_body_control.py` | 152 | Zenith — controle do processo do Corpo (brain/zenith_body_control.py). | `supervisionando` (L39), `corpo_exe` (L43), `corpo_vivo` (L48), `_resetar` (L53), `supervisionar` (L64), `_parar_corpo` (L97) (+1) |
| `brain/zenith_bootstrap.py` | 132 | Módulo do Cérebro | `_is_frozen` (L63), `_missing_packages` (L67), `_pip_env` (L77), `ensure_dependencies` (L92) |
| `brain/zenith_bridge.py` | 171 | Módulo do Cérebro | `class ZenithBridge` (L30) |
| `brain/zenith_busca.py` | 491 | Zenith — busca na web e de imagens SEM chave de API (v21). | `_limpar` (L53), `_desembrulhar_ddg` (L60), `_desembrulhar_bing` (L72), `_http_url` (L88), `class _Ancoras` (L93), `parse_ddg_html` (L116) (+23) |
| `brain/zenith_cadernos.py` | 244 | Zenith — CADERNOS DE ESTUDO (v1.7, tarefa T6). | `class ErroCaderno` (L39), `_pasta_padrao` (L43), `class Cadernos` (L48), `formatar_lista` (L222), `padrao` (L239) |
| `brain/zenith_captura.py` | 167 | Zenith — CAPTURA DE TELA SEM A JANELA DO PRÓPRIO ZENITH POR CIMA (v1.4). | `_enumerar_janelas_zenith` (L32), `titulo_ativo` (L81), `_tamanho_da_tela` (L102), `_esconder` (L110), `_mostrar` (L118), `_fracao_da_tela` (L128) (+2) |
| `brain/zenith_chaves.py` | 550 | Zenith — VÁRIAS CHAVES DA MESMA IA, com troca automática (v30). | `_get` (L80), `normalizar_provedor` (L96), `mascarar` (L105), `_hash` (L115), `_limpar` (L120), `ler_arquivo` (L130) (+10) |
| `brain/zenith_comandos_proprios.py` | 154 | Zenith — comandos próprios do usuário (v1.5, tarefa T8). | `_pasta` (L32), `_caminho` (L42), `carregar` (L46), `_salvar` (L65), `adicionar` (L76), `apagar` (L100) (+3) |
| `brain/zenith_commands.py` | 1571 | Zenith — Comandos rápidos com "/" (resolvidos localmente, sem gastar IA). | `_pasta_exportacao` (L123), `_carimbo` (L128), `_numero` (L132), `_comando_ajuste` (L140), `tratar` (L191), `_parece_caminho` (L975) (+17) |
| `brain/zenith_conhecimento.py` | 485 | Zenith — Conhecimento em cartões: a Bíblia que CRESCE e se adapta a cada IA (v22). | `_norm` (L52), `_config_dir` (L56), `pasta_biblia` (L61), `class Cartao` (L69), `cartoes_base` (L84), `parse_cartao` (L96) (+18) |
| `brain/zenith_contas.py` | 175 | Zenith — CONFERIR CONTAS (v28). | `class ErroConta` (L33), `_normalizar` (L37), `_avaliar_no` (L48), `avaliar` (L82), `formatar` (L95), `_numero_escrito` (L103) (+3) |
| `brain/zenith_content_safety.py` | 112 | Módulo do Cérebro | `check` (L54), `log_incident` (L77), `vrm_filename_suspicious` (L110) |
| `brain/zenith_contexto.py` | 165 | Zenith — Contexto da conversa: a Zenith passa a LEMBRAR do que acabou de ser dito, com qualquer IA (v22). | `normalizar_modo` (L41), `estimar_tokens` (L47), `orcamento_tokens` (L51), `_cortar_no_meio` (L58), `limpar` (L65), `resumo_extrativo` (L88) (+4) |
| `brain/zenith_conversa_loop.py` | 101 | Zenith — CONVERSA POR VOZ sem apertar nada (v1.7). | `_agendar_thread` (L28), `class ConversaContinua` (L34) |
| `brain/zenith_core.py` | 2100 | Módulo do Cérebro | — |
| `brain/zenith_creditos.py` | 121 | Zenith — QUEM FEZ (v1.0). | `texto_personalizado` (L57), `texto` (L69), `garantir_arquivo` (L75), `resumo` (L87), `dados` (L92), `texto_chat` (L108) |
| `brain/zenith_desempenho.py` | 184 | Zenith — O PC MEDIDO e a RECOMENDAÇÃO de IA local (v1.7, tarefa T7). | `_memoria_windows` (L41), `_plataforma_do_celular` (L64), `_eh_celular` (L73), `medir` (L81), `recomendar` (L126), `formatar` (L159) |
| `brain/zenith_diag.py` | 550 | Zenith — "Testar tudo" (/diagnostico) e "Relatório de diagnóstico" (/relatorio). | `_tem_modulo` (L56), `_versao_pip` (L63), `_item` (L72), `_pastas_de_dados` (L76), `_checar_pasta` (L82), `_checar_chaves` (L93) (+22) |
| `brain/zenith_diario.py` | 60 | Zenith — Diário (/diario): a Zenith resume a conversa atual e guarda como memória | `montar_transcricao` (L18), `montar_prompt` (L34), `gerar` (L42) |
| `brain/zenith_ditado.py` | 376 | Zenith — ditado ao vivo, do jeito do Word (v1.5, tarefa T1). | `_espaco_depois` (L64), `_simbolo` (L76), `apagar_ultima_frase` (L83), `aplicar_comandos` (L98), `capitalizar` (L120), `formatar` (L137) (+9) |
| `brain/zenith_documentos.py` | 379 | Zenith — CRIAR WORD e EXCEL (v28). | `class ErroDocumento` (L34), `_nome_seguro` (L38), `_caminho_novo` (L43), `_estilo` (L71), `_runs` (L97), `_par` (L113) (+14) |
| `brain/zenith_downgrade.py` | 278 | Zenith — DOWNGRADE (v1.11): o mesmo Zenith do PC, com chaves para o celular aguentar. | `validar` (L71), `perfil` (L88), `escolher_modelo_local` (L94), `recomendar` (L118), `proximo_passo` (L156), `aplicar` (L168) (+7) |
| `brain/zenith_edicao.py` | 102 | Zenith — EDIÇÃO: "Público" (GitHub, qualquer pessoa) ou "Admin" (a cópia do dono). | `_base_dir` (L41), `_normalizar` (L49), `edicao` (L58), `e_publico` (L75), `e_admin` (L79), `recurso_liberado` (L83) (+2) |
| `brain/zenith_emoji.py` | 89 | Zenith — SEM EMOJI no chat (v1.4). | `_troca` (L38), `remover` (L50), `limpar_mensagem` (L67) |
| `brain/zenith_executor.py` | 363 | Módulo do Cérebro | `limite_s` (L30), `class ExecucaoParada` (L41), `_rodar_processo` (L45), `class _ExtratorDeTexto` (L75), `_extrair_texto_de_html` (L108), `class PendingAction` (L118) (+1) |
| `brain/zenith_export.py` | 49 | Zenith — Exportar conversa em Markdown (/exportar_conversa). | `_slug` (L15), `nome_sugerido` (L20), `conversa_para_markdown` (L24), `exportar_conversa` (L43) |
| `brain/zenith_fontes.py` | 139 | Zenith — FONTES: o que ela usa como BASE para responder (v1.6.1). | `_cortar` (L29), `_item_cartao` (L36), `_item_fixo` (L44), `categoria_fontes` (L52), `categoria_biblia` (L74), `categorias` (L112) (+2) |
| `brain/zenith_formulas.py` | 460 | Zenith — FÓRMULAS e CÁLCULO (v26): o "caderno" de física/cálculo do Anderson dentro do chat. | `_sem_acento` (L125), `listar_assuntos` (L129), `pagina_do_assunto` (L138), `buscar` (L147), `_fonte_rotulo` (L158), `renderizar_folha` (L168) (+13) |
| `brain/zenith_fundo.py` | 300 | Zenith — fundo do chat com QUALQUER imagem ou vídeo (v20). | `class ErroFundo` (L43), `_chave` (L47), `classificar` (L53), `_abrir_pillow` (L68), `_salvar_png` (L81), `_quadros_de_animacao_pillow` (L92) (+8) |
| `brain/zenith_gatekeeper.py` | 272 | Módulo do Cérebro | `class ApprovalWindow` (L35), `class DeterministicGuard` (L201) |
| `brain/zenith_gemini.py` | 198 | Zenith — Gemini: qual modelo usar e como ligar o raciocínio (v23). | `normalizar` (L40), `eh_gemini3` (L46), `eh_gemini25` (L50), `eh_pro` (L54), `dificil` (L58), `thinking_kwargs` (L71) (+7) |
| `brain/zenith_gestos.py` | 147 | Zenith — escolha de expressão e gesto a partir do texto da resposta (v20). | `_palavras` (L35), `_tem` (L39), `escolher_expressao` (L49), `escolher_gesto` (L71), `extrair_comandos_corpo` (L119) |
| `brain/zenith_habilidades.py` | 298 | Zenith — HABILIDADES: a Zenith se estende sozinha, sem mexer no próprio código (v23). | `class ErroHabilidade` (L55), `_atributos` (L60), `_limpar_codigo` (L64), `parse_criar` (L70), `parse_usar` (L97), `analisar_codigo` (L109) (+15) |
| `brain/zenith_hardware.py` | 135 | Módulo do Cérebro | `_plataforma_android` (L26), `_ble_liberado` (L37), `nome_ble_da_porta` (L42), `class ZenithHardware` (L52) |
| `brain/zenith_headless.py` | 2447 | Módulo do Cérebro | `class ZenithHeadlessBrain` (L59), `run` (L2435) |
| `brain/zenith_history.py` | 152 | Módulo do Cérebro | `_load_all` (L30), `_save_all` (L44), `list_conversations` (L52), `get_active_id` (L66), `set_active_id` (L74), `new_conversation` (L82) (+5) |
| `brain/zenith_ia_local.py` | 340 | Zenith — IA LOCAL (opcional, "Avançado"): o último recurso do Megazord (v30). | `_no_celular` (L48), `msg_sem_servidor` (L56), `_endereco_do_aparelho` (L61), `_get` (L98), `_bool` (L113), `_http_json` (L121) (+11) |
| `brain/zenith_imagem_ia.py` | 264 | Módulo do Cérebro | — |
| `brain/zenith_img.py` | 396 | Zenith — criação de imagens de alto nível (v21). | `pasta_criacoes` (L43), `fonte` (L58), `_cor` (L70), `_tema` (L79), `gradiente` (L83), `fundo_decorado` (L114) (+15) |
| `brain/zenith_interaction.py` | 1129 | Módulo do Cérebro | `_log_voz` (L54), `parametros_de_voz` (L127), `class ZenithInteraction` (L141), `_audio_tocar` (L939), `_audio_ocupado` (L948), `_audio_descarregar` (L957) (+2) |
| `brain/zenith_janela.py` | 138 | Zenith — janela do avatar: clique que atravessa DE VERDADE (Windows). | `class _Win32` (L35), `_api` (L82), `suportado` (L89), `escolher_janela_avatar` (L93), `definir_clique_atravessa` (L107) |
| `brain/zenith_lembretes.py` | 283 | Zenith — Lembretes e alarmes que sobrevivem a reiniciar (/lembrar, /lembretes). | `class ErroLembrete` (L36), `_sem_acento` (L40), `_limpar_mensagem` (L53), `interpretar` (L60), `_caminho_padrao` (L147), `class Lembretes` (L152) (+1) |
| `brain/zenith_linguagens.py` | 191 | Zenith — OUTRAS LINGUAGENS e `pip` GUIADO (v1.7, tarefa T5). | `class ErroLinguagem` (L81), `linguagem_de` (L85), `detectar` (L89), `plano_para` (L107), `formatar_plano` (L142), `_http_json` (L154) (+3) |
| `brain/zenith_main.py` | 28 | Módulo do Cérebro | `main` (L19) |
| `brain/zenith_matematica.py` | 615 | Zenith — MATEMÁTICA E LaTeX NO CHAT (v26). | `_arg` (L87), `_arg_opcional` (L111), `_limites` (L123), `class _Estilo` (L139), `_conv` (L202), `latex_para_unicode` (L294) (+18) |
| `brain/zenith_memoria_leve.py` | 196 | Zenith — MEMÓRIA LEVE (v1.11): a coleção do chromadb, trocada por SQLite puro (para o celular). | `_tokens` (L45), `_casa` (L56), `class ColecaoLeve` (L84), `abrir` (L193) |
| `brain/zenith_memoria_util.py` | 80 | Zenith — utilidades da memória que NÃO dependem do chromadb (por isso ficam | `_norm` (L20), `guardar_resumo` (L25), `listar_com_id` (L39), `apagar_por_ref` (L61) |
| `brain/zenith_memory.py` | 260 | Módulo do Cérebro | `class ZenithMemory` (L23) |
| `brain/zenith_modelos.py` | 214 | Zenith — QUAL MODELO usar em cada IA, e o que dizer quando uma IA falha (v1.6.1). | `grupo` (L43), `padrao` (L47), `_t` (L53), `eh_erro_de_parametro` (L58), `eh_erro_de_politica` (L65), `eh_limite_da_chave` (L70) (+7) |
| `brain/zenith_modos.py` | 162 | Zenith — Modos de conversa (/modo estudo / lab / codigo / normal). | `_sem_acento` (L135), `normalizar` (L139), `prompt_extra` (L146), `formatar_lista` (L155) |
| `brain/zenith_movimentos.py` | 675 | Zenith — MOVIMENTOS (v1.6): pulo de verdade, dança, câmera, passeio da janela, rostos — e a IA cria os dela. | `_sem_acento` (L62), `_num` (L69), `_clamp` (L75), `validar` (L82), `_suave` (L161), `_interpola` (L165) (+21) |
| `brain/zenith_notes.py` | 146 | Zenith — Bloco de notas rápido (observações de laboratório, ideias, etc.). | `extrair_tags` (L22), `normalizar_tag` (L33), `_caminho_padrao` (L37), `adicionar` (L42), `listar` (L62), `tags_usadas` (L84) (+4) |
| `brain/zenith_notify.py` | 35 | Zenith — Notificação nativa do Windows (quando uma ação longa termina). | `notificar` (L13) |
| `brain/zenith_observar.py` | 203 | Zenith — OBSERVAÇÃO AO VIVO: ela acompanha a câmera ou a tela enquanto você trabalha (v23). | `_int` (L44), `parse` (L51), `montar_tag` (L66), `preview_text` (L70), `diferenca` (L85), `prompt_de_observacao` (L100) (+1) |
| `brain/zenith_organizar.py` | 439 | Zenith — ORGANIZAR PASTAS e LIMPAR ARQUIVOS INÚTEIS (v28). | `class ErroOrganizar` (L58), `_pastas_de_sistema` (L63), `_dentro_de` (L75), `pasta_protegida` (L83), `categoria_de` (L119), `tamanho_legivel` (L127) (+11) |
| `brain/zenith_overlay.py` | 176 | Zenith — ajustes de código aprovados (camada de cima) e inicialização segura (v1.6.2). | `sha256_arquivo` (L49), `_json` (L58), `_gravar_json` (L66), `ler_manifesto` (L74), `gravar_manifesto` (L82), `pasta_overlay` (L86) (+7) |
| `brain/zenith_parar.py` | 160 | Zenith — PARAR e "o que ela está fazendo agora" (v26). | `geracao` (L34), `cancelado_desde` (L38), `solicitar` (L43), `registrar_processo` (L54), `liberar_processo` (L59), `matar_processos` (L64) (+4) |
| `brain/zenith_pausa.py` | 62 | Zenith — Modo silêncio total (/pausar e /retomar). Pilar 1: o usuário sempre | `ativo` (L22), `pausar` (L27), `retomar` (L36), `desde_texto` (L45), `mensagem_bloqueio` (L51), `_resetar` (L58) |
| `brain/zenith_pendencias.py` | 223 | Zenith — PENDÊNCIAS e PROJETO ATIVO: ela não esquece o que você pediu, nem o roteiro (v25). | `_norma` (L39), `_ler` (L43), `_gravar` (L54), `listar` (L60), `adicionar` (L64), `concluir` (L82) (+13) |
| `brain/zenith_plataforma.py` | 261 | Zenith — camada de PLATAFORMA: o que muda entre o PC e o celular (v1.11, port Android). | `class Indisponivel` (L33), `_ler_arquivo` (L54), `_parse_meminfo` (L62), `medir_sistema` (L81), `class Plataforma` (L115), `detectar` (L227) (+3) |
| `brain/zenith_plataforma_android.py` | 249 | Zenith — plataforma ANDROID (v1.11): o Cérebro pede, o app Android faz. | `class AndroidPlataforma` (L52) |
| `brain/zenith_plataforma_pc.py` | 119 | Zenith — plataforma PC (v1.11): o lado "Windows" da mesma interface. | `_importar` (L27), `class PCPlataforma` (L34) |
| `brain/zenith_ponte_corpo.py` | 136 | Zenith — PONTE ATÉ O ANDROID, pelo Corpo (v1.11, port celular). | `class PonteCorpo` (L35) |
| `brain/zenith_presenca.py` | 206 | Zenith — PRESENÇA EM VÍDEO (v1.7, tarefa T3): "ela sempre olhando", de verdade. | `_sem_acento` (L50), `titulo_sensivel` (L54), `diferenca` (L62), `class BufferQuadros` (L68), `class Presenca` (L136) |
| `brain/zenith_proactive.py` | 55 | Módulo do Cérebro | `class ZenithProactive` (L15) |
| `brain/zenith_programa.py` | 535 | Zenith — Modo "criar programa" (v21). | `limpar_codigo` (L67), `_attrs` (L77), `nome_seguro_pasta` (L81), `nome_arquivo_seguro` (L86), `class ProgramaProposto` (L106), `interpretar` (L114) (+17) |
| `brain/zenith_progresso.py` | 197 | Zenith — PROGRESSO e AVISOS POPUP (v28). | `msg_progresso` (L38), `msg_aviso` (L54), `class Progresso` (L64), `class Nulo` (L175) |
| `brain/zenith_projetos.py` | 263 | Zenith — BIBLIOTECA / PROJETOS (v1.6): tudo o que ela criou, separado por assunto, visível no painel "Bibliote | `raiz_padrao` (L55), `dentro_das_criacoes` (L60), `_arquivos` (L70), `_info` (L84), `_projeto` (L92), `_achar_midia` (L110) (+5) |
| `brain/zenith_provedores.py` | 329 | Zenith — provedores de IA: catálogo OPCIONAL + visão unificada das "entradas de IA". | `class ErroProvedor` (L52), `catalogo_vazio` (L57), `_txt` (L61), `_url_ok` (L65), `_limpar_catalogo` (L70), `carregar_catalogo` (L119) (+12) |
| `brain/zenith_quarentena.py` | 95 | Zenith — QUARENTENA DE CONTEÚDO EXTERNO (v28). | `_sem_acento` (L55), `neutralizar` (L59), `achar_suspeitas` (L66), `envolver` (L79), `esta_embrulhado` (L93) |
| `brain/zenith_reset.py` | 141 | Zenith — "Resetar tudo" dentro do programa (v20). | `caminho_marcador` (L49), `agendar` (L53), `cancelar` (L66), `pendente` (L74), `_esvaziar` (L78), `aplicar_se_pendente` (L91) |
| `brain/zenith_rota.py` | 255 | Zenith — ROTEADOR POR CAPACIDADE: "uma IA só, com as ferramentas de todas" (v30). | `_get` (L63), `_base` (L78), `rotulos` (L84), `rotulo` (L97), `capacidades` (L101), `pode` (L120) (+9) |
| `brain/zenith_rvc.py` | 284 | Zenith — voz RVC rodando num Python 3.10 À PARTE (v20). | `python_valido` (L91), `candidatos_python` (L101), `achar_python_rvc` (L116), `mp3_para_wav` (L123), `class RVCExterno` (L158) |
| `brain/zenith_segredos.py` | 136 | Zenith — SEGREDOS QUE NUNCA DEVEM FICAR GUARDADOS (v1.0, tarefa A2). | `_mascarar_valor` (L46), `mascarar` (L50), `contem_segredo` (L61), `eh_comando_de_chave` (L68), `mascarar_dados` (L82), `mascarar_arquivo_json` (L106) |
| `brain/zenith_settings.py` | 450 | Módulo do Cérebro | `_resolve_base_dir` (L28), `_ler_data_root` (L58), `_read_data_root_override` (L68), `class ZenithSettings` (L322) |
| `brain/zenith_stream.py` | 257 | Zenith — STREAMING de verdade: a resposta sai frase a frase ENQUANTO o modelo ainda gera (v24). | `class Portao` (L31), `fatiar_preservando` (L159), `_norm` (L181), `reconciliar` (L185), `class SessaoDeEntrega` (L210) |
| `brain/zenith_tags.py` | 170 | Zenith — filtro de TAGS (v26): nenhuma etiqueta interna aparece no chat, mesmo escrita errado. | `_norm` (L54), `distancia` (L59), `parecida_com` (L76), `_fora_do_codigo` (L92), `_troca` (L103), `corrigir_tags` (L112) (+3) |
| `brain/zenith_tema.py` | 93 | Zenith — TEMA de cores da interface (v25). Pedido do Anderson: "personalização de cores que só fica no azul cl | `_rgb` (L28), `_hex` (L36), `_mix` (L40), `eh_hex` (L44), `normalizar_hex` (L48), `paleta` (L52) (+2) |
| `brain/zenith_tft.py` | 488 | Zenith — TFT: a Zenith num mini-display ligado por USB a um ESP32-S3 (v24). | `enquadre_valido` (L61), `parse_resposta` (L67), `montar_pacote` (L73), `quadro_de_teste` (L77), `eh_wifi` (L101), `aviso_sem_pyserial` (L106) (+8) |
| `brain/zenith_theme.py` | 84 | Módulo do Cérebro | `ease_out_cubic` (L70), `lerp_color` (L75) |
| `brain/zenith_ui.py` | 609 | Módulo do Cérebro | `class GodotProcessManager` (L50), `class TopBar` (L89), `class ChatArea` (L130), `class ZenithApp` (L183), `class SettingsWindow` (L380), `run` (L602) |
| `brain/zenith_validator.py` | 116 | Módulo do Cérebro | `scan_persona_text` (L45), `strip_suspicious` (L58), `validate_path` (L95) |
| `brain/zenith_verificar.py` | 116 | Zenith — "VERIFICAR ANTES DE AFIRMAR" (v26). | `_norm` (L35), `caminhos_citados` (L39), `_arquivos_recentes` (L50), `conferir` (L75) |
| `brain/zenith_version.py` | 80 | Zenith — versão em um lugar só (mostrada em /versao, no diagnóstico e no relatório). | `edicao` (L22), `numero` (L35), `_candidatos_build` (L41), `data_build` (L58), `texto` (L76) |
| `brain/zenith_video.py` | 1061 | Zenith — EDITAR e CRIAR VÍDEO (v28). | `class ErroVideo` (L46), `achar_ffmpeg` (L51), `tempo_para_segundos` (L76), `_carimbo` (L93), `_limpar_nome` (L97), `_unico` (L102) (+48) |
| `brain/zenith_vision.py` | 94 | Módulo do Cérebro | `class ZenithVision` (L28) |
| `brain/zenith_vrm_import.py` | 597 | Zenith — importação automática de avatar (brain/zenith_vrm_import.py) — v18. | `_flags_sem_janela` (L53), `_rodar` (L57), `_com_repeticao` (L77), `_dica_bloqueio` (L92), `_sha256` (L106), `_nome_seguro` (L114) (+18) |
| `brain/zenith_widgets.py` | 268 | Módulo do Cérebro | `safe_font` (L22), `class PulseDot` (L35), `class TypingIndicator` (L91), `class SegmentedToggle` (L123), `class GlowSlider` (L183), `class AnimatedBubble` (L236) |

### B. Corpo e Central de Controle Godot 4.7 (`body/zenith/` — 18 scripts)

| Arquivo | Linhas | Papel / Descrição | Principais Funções (com linha) |
|---|---:|---|---|
| `body/zenith/akira_body.gd` | 1986 | CORREÇÃO (transparência "não funciona"): mesh_instance (acima) é só a | `_debug_log()` (L144), `_load_or_capture_anchor()` (L156), `_save_anchor()` (L186), `_save_manual_adjust()` (L194), `set_manual_vrm_adjust()` (L209), `reset_manual_vrm_adjust()` (L226) (+79) |
| `body/zenith/akira_vida.gd` | 865 | ============================================================ | `setup()` (L148), `_preparar_maos()` (L179), `_norm()` (L191), `_find_bone()` (L195), `_has()` (L209), `_compute_frame()` (L213) (+31) |
| `body/zenith/brain_connector.gd` | 1001 | Sinais atualizados | `_ready()` (L74), `_modo_celular()` (L103), `_cerebro_local()` (L106), `is_connected_to_brain()` (L109), `_obter_url_servidor()` (L112), `definir_servidor()` (L125) (+64) |
| `body/zenith/ponte_android.gd` | 136 | ============================================================ | `configurar()` (L33), `_ao_receber()` (L46), `chamar_local()` (L58), `_atender()` (L64), `_primeira_permissao_faltando()` (L77), `_permissao_concedida()` (L83) (+8) |
| `body/zenith/ui_manager.gd` | 5375 | ============================================================ | `_tema_carregar_local()` (L180), `_on_ui_tema()` (L200), `_ready()` (L215), `_process()` (L259), `_sync_adjust_fields()` (L273), `_sem_emoji()` (L294) (+180) |
| `body/zenith/zenith_aparencia.gd` | 565 | ZENITH — Estúdio de Aparência (motor). | `iniciar()` (L83), `area_padrao()` (L103), `escolher_efeito()` (L106), `area()` (L117), `_carregar()` (L122), `salvar()` (L147) (+35) |
| `body/zenith/zenith_avatar_simples.gd` | 190 | ══════════════════════════════════════════════════════════════════════════════════════════════════════════════ | `_ready()` (L50), `_material()` (L53), `_peca()` (L63), `_esfera()` (L73), `_capsula()` (L81), `_caixa()` (L89) (+4) |
| `body/zenith/zenith_cartoes.gd` | 180 | ZENITH — cartões de atividade no meio do chat: "Adicionando à memória…", "Executando código…", "Pesquisando na | `iniciar()` (L19), `abrir_todos()` (L24), `limpar()` (L31), `atualizar()` (L35), `_podar()` (L54), `_criar()` (L59) (+1) |
| `body/zenith/zenith_chaves_page.gd` | 321 | ZENITH — página "Chaves" das Configurações (contrato A8 do Cérebro). | `_salvar_chave_local()` (L23), `_carregar_chaves_locais()` (L33), `montar()` (L42), `pedir()` (L129), `_dizer()` (L134), `ao_estado()` (L140) (+7) |
| `body/zenith/zenith_desempenho_aplicar.gd` | 34 | ============================================================ | `aplicar()` (L16) |
| `body/zenith/zenith_desempenho_page.gd` | 150 | ============================================================ | `montar()` (L36), `_pedir()` (L73), `ao_estado()` (L78), `_usar_sugestao()` (L116), `_aplicar()` (L125), `_nome()` (L134) (+2) |
| `body/zenith/zenith_estudio.gd` | 348 | ZENITH — página "Estúdio" das Configurações: o usuário escolhe tudo, ao vivo. | `montar()` (L8), `_refazer()` (L28), `_temas()` (L34), `_meus_temas()` (L62), `_dizer()` (L104), `_popular_temas()` (L109) (+5) |
| `body/zenith/zenith_fx.gd` | 59 | ZENITH — camada de fundo de UMA área da interface (histórico, chat, barra de cima...). | `_init()` (L14), `aplicar()` (L22), `animado()` (L53), `tempo()` (L56) |
| `body/zenith/zenith_icones.gd` | 96 | ZENITH — ícones próprios (51 SVGs originais em res://assets/icones/, traço branco 24x24). | `existe()` (L19), `tex()` (L22), `separar()` (L33), `aplicar()` (L48), `texto_com_icone()` (L68), `so_icone()` (L81) (+1) |
| `body/zenith/zenith_layout_celular.gd` | 868 | ══════════════════════════════════════════════════════════════════════════════════════════════════════════════ | `ativo()` (L41), `_tamanho_da_tela()` (L47), `_margem_baixo()` (L68), `ligar_observador()` (L81), `aplicar()` (L85), `_ao_tamanho_mudou()` (L120) (+42) |
| `body/zenith/zenith_maos.gd` | 219 | ====================================================================== | `_norm()` (L75), `_achar()` (L79), `_nomes_da_junta()` (L87), `preparar()` (L105), `atualizar()` (L180), `soltar()` (L213) |
| `body/zenith/zenith_movimentos.gd` | 322 | ====================================================================== | `_init()` (L36), `_carregar_padroes()` (L40), `_carregar_locais()` (L138), `_salvar_locais()` (L151), `definir_todos()` (L166), `adicionar()` (L175) (+11) |
| `body/zenith/zenith_saude_page.gd` | 124 | ZENITH — seção "Saúde do Zenith" (Configurações → Sobre). | `montar()` (L20), `_dizer()` (L59), `rodar()` (L64), `ao_resultado()` (L72), `_linha()` (L93) |

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
