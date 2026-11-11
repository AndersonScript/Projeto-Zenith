# Zenith — Como funciona por dentro
### Arquitetura, fluxo e as decisões de projeto · 10/11/2026

---

## 1. A ideia central

O Zenith não é um programa só: são **cinco peças** que se conversam. O raciocínio foi separar responsabilidades para que cada uma pudesse ser corrigida sem quebrar as outras.

```
            ┌──────────────────────────┐
            │  SITE (Vercel)           │  mostra, explica e redireciona
            │  index.html + latest.json│  nunca guarda o .exe
            └───────────┬──────────────┘
                        │ /baixar → GitHub Release
            ┌───────────▼──────────────┐
            │  LAUNCHER (PyInstaller)  │  instala, atualiza, conserta
            │  ZenithLauncher.exe      │  pergunta pastas, resolve Python
            └───────────┬──────────────┘
                        │ baixa ZIP, cria venv, copia app
            ┌───────────▼──────────────┐
            │  APP (Tkinter + brain/)  │  a Central de Controle
            │  Zenith.exe              │  conversa, cartões, TFT
            └───────┬──────────┬───────┘
                    │ serial   │ HTTP
        ┌───────────▼───┐  ┌───▼────────────────┐
        │ ESP32-S3      │  │ APIs (IA, imagem)  │
        │ carrinho      │  │ Cloudflare/Pollin. │
        └───────────────┘  └────────────────────┘
```

**Por que assim:** o site sozinho não instala nada; o launcher não desenha interface de uso diário; o app não sabe se instalar nem se atualizar. Cada um falha isolado — e é por isso que quase todo bug desta conversa foi resolvido mexendo em **uma** peça.

---

## 2. O caminho do usuário, passo a passo

1. **Abre o site.** Vê o cartão com versão, tamanho e SHA-256, mais a explicação de onde o arquivo vai cair e onde ficam os projetos.
2. **Clica em “Baixar o Launcher”.** `/baixar` é um redirect (307) para `releases/latest/download/ZenithLauncher.exe` no GitHub — o site **não** hospeda binário.
3. **Roda o `ZenithLauncher.exe`.** Ele pergunta **duas pastas**: onde instalar o programa/Python e onde ficar os dados (conversas, imagens, memória).
4. **O launcher prepara o ambiente:** acha ou instala o Python, cria o `venv`, instala as dependências com log, baixa o ZIP do app, confere o SHA-256, extrai.
5. **Grava `instalacao.json`** com as pastas escolhidas e a versão, cria o atalho e abre o app.
6. **O app sobe** na Central de Controle, lê `config/`, o banco de memória e começa a conversar.
7. **Atualizar** = rodar o launcher de novo: ele lê `instalacao.json`, compara com `latest.json`, baixa só o necessário e preserva `config/`, `creations/` e `memory_db/`.

---

## 3. O site

| Arquivo | Papel |
|---|---|
| `site/index.html` | página única; o cartão de download é montado por JS (`pegar("latest.json")` → `baixar(m)` → `#ultima`) |
| `site/latest.json` | **a fonte da verdade**: versão, URL do ZIP, tamanho, SHA-256, versão do Python, hashes do launcher e do limpador |
| `site/versions.json` | histórico de versões |
| `site/vercel.json` | redirects `/baixar` e `/limpar`, `cleanUrls` |

**Raciocínio:** o `latest.json` é o único ponto que precisa mudar quando sai versão nova. Por isso o `tools/gerar_release.py` **reescreve** esse arquivo em vez de alguém editar à mão — hash digitado errado = download recusado.

**Regra dura:** `preparar_publico.py` barra `Itaquera`, `Itaquaera`, `Caderno Aberto`, `<usuario>` e o nome antigo do projeto. Se achar, **falha de propósito**. É a trava para não vazar dado pessoal no pacote público.

---

## 4. O launcher (`launcher/zenith_instalador.py`)

É o componente mais “chato” e o que mais deu problema — porque instalar em Windows é uma sequência de imprevistos.

**Funções principais e o porquê de cada uma:**

- `raiz_padrao()` — caminho padrão (`%LOCALAPPDATA%\Zenith`), usado como sugestão na tela de escolha.
- `pythons_instalados()` — procura Python no registro (`HKCU/HKLM\...\PythonCore\*\InstallPath`) **e** em `%LOCALAPPDATA%\Programs\Python`. **Motivo:** o instalador oficial responde “código 0” sem instalar quando a versão já existe; então antes de instalar, o launcher procura o que já existe.
- `python_exe()` — devolve o interpretador utilizável (o do venv, se houver; senão o do sistema).
- `caminhos_do_app()` — resolve onde o app mora a partir do `instalacao.json`.
- `instalar_python()` — roda o instalador com `/log`, lê `tmp/python_instalacao.log`, e se falhar tenta **copiar** uma instalação válida encontrada (testando `import tkinter, ssl, sqlite3, venv`). **Motivo:** sem `tkinter` não há interface; sem `ssl` não há download; sem `venv` não há isolamento.
- `instalar_ou_atualizar(pasta, dados=None, ...)` — baixa o ZIP, confere hash, extrai, cria venv, instala dependências, grava `instalacao.json`. `dados` separa programa de conteúdo.
- `executar_launcher()` — inicia o app e sai de cena. `--esperar-pid` permite ao app pedir atualização e o launcher esperar o processo antigo fechar.
- **`JanelaEscolha`** — tela nova: duas caixas de caminho, “Escolher…”, “Instalar aqui”, “Cancelar”. Trocar a pasta do programa move a de dados junto; separar é permitido.
- `JanelaTk` — interface de progresso. `JanelaLimpeza` (no `LimparZenith.exe`) — pergunta **o que** apagar em vez de varrer tudo.
- `main()` — decide o modo: instalação nova (mostra a tela de pastas), `--pasta`, `--dados`, `--atualizar`, `--reverter`, `--esperar-pid`, ou fallback `sem-tk`.

**Raciocínio da ordem:** primeiro descobrir o ambiente (Python), depois garantir as pastas (escolha do usuário), só então baixar. Baixar antes de saber onde gravar é o que fazia o instalador parecer “travado”.

---

## 5. O app e o `brain/`

O app é a carcaça (Tkinter) e o `brain/` é o cérebro, fatiado por responsabilidade:

| Módulo | Responsabilidade | Detalhe importante |
|---|---|---|
| `brain/zenith_core.py` | orquestra a conversa e os cartões | `_com_cartao` (~linha 1618) cria/atualiza o cartão de atividade — só fecha quando há resultado **ou** falha |
| `brain/zenith_atividade.py` | títulos e estado dos cartões | `parece_falha` decide se o cartão vira erro em vez de “concluído” |
| `brain/zenith_tft.py` | manda a imagem para a tela TFT via serial | baud automático (115200 → 921600) com `_motivo` registrando a escolha |
| `brain/zenith_settings.py` | preferências persistidas | `tft_baud`, provedores, caminhos |
| `brain/zenith_imagegen.py` | geração de imagem | provedor escolhido nas configurações (Cloudflare/Pollinations) |

**Dados do usuário (nunca vão para o público):** `config/` (chaves de API), `creations/` (imagens e criações), `memory_db/` (SQLite com conversas). O `prepare_pendrive.py` **zera** essa pasta de propósito — por isso, ao copiar para o pendrive, usei `robocopy` com `//XD config creations memory_db`.

**Raciocínio dos cartões:** a Central de Controle mostra o que está acontecendo. Se o cartão fecha verde antes da resposta, o usuário perde a confiança na tela inteira. Daí a regra: cartão só conclui com resultado real.

---

## 6. O firmware do carrinho (ESP32-S3)

`firmware/carrinho_esp32s3/carrinho_esp32s3.ino` — três frentes:

1. **Wi-Fi:** `escanearEEscolher` lista redes; se a rede salva não aparecer (oculta), `tentativaCega` tenta entrar direto, com prazo de 30 s. Diagnóstico no Serial: `wifiTipo()` (aberta/WPA2/WPA3), canal, RSSI, `[WIFI] tentando entrar em ...` e `[WIFI] nao entrou em '%s' — codigo %d`.
2. **Comunicação:** o app fala com a placa pela serial — é o mesmo link que empurra a imagem para o TFT (por isso o baud importa tanto).
3. **Configuração:** `USAR_BLE` (linha ~44) e `TEM_VRM` (linha ~45) ligam/desligam Bluetooth e leitura de tensão, para a mesma placa servir em montagens diferentes.

**Raciocínio:** firmware sem diagnóstico é caixa-preta. Antes o sintoma era “não conecta”; agora o Serial diz **por quê** (rede não achada, senha errada, código de status do `WiFi.begin`).

---

## 7. As ferramentas (`tools/`)

| Ferramenta | O que faz | Quando usar |
|---|---|---|
| `build_exe.py` | compila o app em `dist\Zenith\Zenith.exe` | toda mudança no `brain/` (~10 min) |
| `launcher/build_launcher.py --site <url>` | compila launcher + limpador | toda mudança no instalador (~2 min) |
| `tools/preparar_publico.py` | remove dados pessoais e **barra** termos proibidos | **sempre** antes de publicar |
| `tools/gerar_release.py` | gera `Zenith_app_<versao>.zip`, calcula SHA-256 e reescreve `latest.json`/`versions.json` | ao lançar versão |
| `tools/gerar_pacote_pendrive.py` | monta o ZIP único para levar no pendrive | ao atualizar o pendrive |

**Raciocínio:** qualquer passo manual repetido é um lugar para errar. Os hashes, principalmente — ninguém calcula SHA-256 de 75 MB à mão duas vezes sem trocar um dígito.

---

## 8. Testes: a rede de segurança

- `tests/test_v24.py` — 32 testes do TFT/baud.
- `tests/test_launcher.py` + `tests/test_v30_launcher_print.py` — **46 testes** do instalador (inclui o caso “Python já instalado”).
- Suíte completa: `py -3 -m unittest discover -s tests -t .` → **1527 testes OK** (~130 s).

**Raciocínio:** o launcher mexe em registro, arquivos e processos — coisas que quebram em silêncio. Os testes existem justamente porque o erro “código 0 sem instalar” passaria despercebido por qualquer verificação superficial.

---

## 9. Como eu penso um problema daqui

Padrão que usei a conversa inteira:

1. **Separar sintoma de causa.** “O site está feio” era CSS; “o site mostra outro app” era Root Directory. Mesma página, causas opostas.
2. **Procurar o nível certo.** Cabo lento se resolve no app (baud), não no firmware. Instalação que falha se resolve lendo o log, não aumentando timeout.
3. **Desconfiar de “deu certo”.** Código de saída 0 do Python era mentira; hash declarado no `latest.json` pode ser de outro arquivo. Verificar > confiar.
4. **Não misturar o público com o pessoal.** `config/`, `creations/`, `memory_db/` nunca entram no pacote; a checagem é automática e falha de propósito.
5. **Manter o usuário no controle.** Pasta de programa, pasta de dados, o que apagar, qual provedor de imagem — decisões que mudam a vida dele não ficam escondidas em constante de código.
6. **Quando o texto vem embaralhado** (teclado com defeito), confirmar o entendimento antes de mexer — mexer no lugar errado custa mais que perguntar.

---

## 10. Onde está cada coisa

```
C:\Zenith\Zenith\
├─ brain\              núcleo do app (core, tft, settings, atividade, imagegen)
├─ launcher\           instalador + limpador (zenith_instalador.py, build_launcher.py)
├─ site\               index.html, latest.json, versions.json, vercel.json
├─ firmware\
│  └─ carrinho_esp32s3\  .ino + LEIA-ME.md
├─ tools\              gerar_release, preparar_publico, gerar_pacote_pendrive
├─ tests\              suíte (1527 testes)
├─ docs\               tutoriais e avaliações
├─ dist\Zenith\        app compilado (Zenith.exe)
├─ dist_launcher\      ZenithLauncher.exe, LimparZenith.exe
└─ dist_publico\       cópia higienizada para publicar
```

Fora do projeto: `C:\Zenith\Zenith_PENDRIVE_1.0.zip` (pacote do pendrive) e `D:\Zenith` (cópia no pen drive, com dados preservados).

---

## 11. Limite deste documento

O desenho acima é o do Zenith como ele está hoje: as cinco camadas, os fluxos e as decisões estão corretos, e os números (1.527 testes, 46 do launcher, tamanhos e hashes) foram medidos nesta conversa. O que ele **não** faz é listar linha por linha cada função de todos os módulos do `brain/` — para isso é preciso abrir os arquivos, o que exige o computador acessível. Quando voltar, eu complemento com um mapa “arquivo → função → o que faz” gerado direto do código, sem depender de memória.

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
