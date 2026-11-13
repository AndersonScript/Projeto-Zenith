# Zenith — Histórico de mudanças

**Do primeiro protótipo até 01/11/2026**

Documento de registro do Projeto Zenith. Idealizador e desenvolvedor: **Anderson** — Etec Itaquera, Curso Técnico em Automação Industrial; Fatec Itaquera; Iniciação Científica em Física e Matemática.

> **Como ler este documento.** Cada fase diz o que entrou, o que foi *provado* e o que ficou pendente. A regra é a mesma do projeto: o que não foi visto rodando aparece marcado como não testado. Número de testes é o da suíte de Python (`py -3 -m unittest discover -s tests`), que não precisa de Godot, internet nem chaves de API.

---

## Resumo em uma olhada

| Fase | Quando | O que marcou | Testes |
|---|---|---|---|
| Protótipos v1.0 → v1.5 | outubro/2026 | Cérebro, Corpo, voz, memória, instalador, edição pública | 1018 → 1076 |
| Rodadas v22 → v30 | outubro/2026 | Interface no Godot, TFT do carrinho, vídeo, anexos, correções de vício | 441 → 860 |
| v1.10 | 29–30/10/2026 | Diagnóstico real das IAs, cotas, `print()`, carrinho | 1503 → 1507 |
| Launcher 1.0.1 | 30/10/2026 | Certificado SSL, apagar por partes, `LimparZenith` | 1526 |
| 1.0 Oficial | 31/10/2026 | Site no ar, Release, hashes, README | 1526 |
| Correção de vídeo e acervo | 01/11/2026 | Tela preta, site redesenhado, documento 2.0, histórico | ver seção 6 |

---

## 1. Fase 1 — os protótipos (v1.0 a v1.5)

Aqui o Zenith deixou de ser uma ideia e virou um programa que abre, conversa, tem avatar e instala. Cada versão foi feita em cima da anterior, com um changelog próprio.

### 1.1 v1.0 — a primeira versão oficial (18/10/2026)

- **Quem criou** aparece no menu de Configurações, como pedido.
- **A versão mostra a data do build**, para nunca mais confundir `.exe` velho com `.exe` novo.
- **Chave digitada no chat não fica guardada** (A2): se você colar uma chave na conversa por engano, ela não vai para o histórico.
- **Comando desconhecido não vai para a IA** (A5): evita que um `/algumacoisa` seja interpretado como pergunta.
- **Markdown não perde mais as quebras de linha** (A6).
- **`/video` aceita o caminho do jeito que o Windows copia** (A7), com aspas e acentos.
- **IA local**: contrato da tela e o que o PC aguenta (A8/A20, parte).
- **Bug grave corrigido:** o build **não apaga mais os dados do usuário** (A18) — provado antes e depois.
- **Legenda queimada** funcionava mal com apóstrofo, acento ou colchete no nome do arquivo (A19).
- **Limpeza**: saíram arquivos que o programa não usava mais.

### 1.2 v1.1 — ícones, Estúdio e Chaves

- **Defeito crítico da v1.0 corrigido** (o primeiro item do changelog da versão).
- **Ícones próprios** no lugar dos emojis — visto rodando.
- **Estúdio de Aparência** (Configurações → Estúdio) — visto rodando.
- **Tela de Chaves** (Configurações → Chaves) — vista rodando com dados de mentira.

### 1.3 v1.2 — saúde do programa e desempenho

- **Saúde do Zenith** (Configurações → Sobre): o programa passa a se autodiagnosticar. 17 testes novos.
- **Guarda de desempenho dos efeitos**: em máquina fraca os efeitos se desligam sozinhos (lógica provada; desempenho real não medido).
- **Meus temas** + aviso de contraste no Estúdio.

### 1.4 v1.3 — cartões de atividade

- **Cartões de atividade no meio do chat**: o que ela está fazendo aparece como cartão, não como texto solto. 16 testes novos.
- **O build explica o erro do `pip`** em vez de só falhar.
- Suíte: **1018 testes**.

### 1.5 v1.4 — público × admin e o instalador

- **Só "Zenith"**: varredura para tirar nomes antigos do programa.
- **Edição Pública × Admin**: duas edições do mesmo código.
- **Instalador**: escrito nesta versão, **ainda não compilado**.
- **Abertura e marca**, **dedos** (mãos do avatar), **print sem a janela do Zenith**, **"ela sempre olhando"** (comando de observação), **filtro de emoji**, **repositório** no GitHub.
- Suíte: **1076 testes** (1018 + 58).

### 1.6 v1.5 — ditado ao vivo e atualização segura

- **T1 — Ditado ao vivo, do jeito do Word**: o texto aparece enquanto você fala (módulo + testes; a tela não foi vista).
- **T2 — Modo conversa**: microfone sempre aberto (módulo + testes; falta ligar ao microfone real).
- **T8 — Comandos próprios**: você cria seus comandos.
- **T9 — Atualização com segurança**: baixar, conferir e poder voltar (testado; nenhum download real feito).
- **`--so-conferir` da edição pública** — defeito da v1.4, corrigido.

---

## 2. Fase 2 — as rodadas v22 a v30

Fase de integração: a interface foi para o Godot, o carrinho ganhou tela, o vídeo ficou de verdade e cada teste do Anderson virou uma rodada de correções.

### 2.1 v22 — a mistura das duas v21

Duas linhas de trabalho paralelas (a do Anderson e a de outra IA) foram fundidas. O changelog registra as **decisões da mistura** (as duas tinham coisas com o mesmo nome), a lista de arquivos novos e dos arquivos editados só com ganchos.

### 2.2 v23 — o erro do "pede permissão em texto"

- **"Cadê o poder do Gemini?"**: achados no código e na documentação do Google.
- **"Ela pede permissão em texto / dá desculpa / não faz nada"**: aqui foi identificado o **erro real** por trás do print — pedir licença em texto em vez de usar a etiqueta que abre a janela de aprovação. Virou a regra de ouro nº 10 da Bíblia.
- **Habilidades maleáveis**: ela pode se estender criando habilidades, com o Pilar 1 preservado.
- **Recursos trazidos dos vídeos da Shogun**.
- **Fundo PRETO do avatar em outro computador** — primeiro registro do problema de vídeo que voltaria em 01/11.
- **Chat "picado" em PC lento**.

### 2.3 v24 — velocidade e a tela do carrinho

- **"Delay muito grande"**: medido onde o tempo ia, e o que mudou.
- **o avatar no display TFT** do ESP32-S3 por USB.
- **Antivírus**: o que fazer quando o Windows reclama.
- Suíte: **595 testes**.

### 2.4 v25 — a tela preta no PC da mãe

Rodada dedicada ao relato de tela preta em outra máquina, com roteiro de investigação (placa, driver, janela transparente). Suíte: **627 testes**.

### 2.5 v26 e v27 — o teste real do Anderson

- v26: um **bug que ele não tinha como ver** foi encontrado no caminho. Suíte: **701 testes**.
- v27: o teste real da v26 mostrou **19 falhas + 1 erro**; todas corrigidas, mais os pedidos novos. Suíte: **742 testes**.

### 2.6 v28 — vídeo de verdade

- Revisão de três arquivos "v28" produzidos por outra IA, com correções.
- **ffmpeg real** exercitado: cortar, GIF, juntar, narrar.
- **Protocolo Cérebro → Corpo** ganhou mensagens novas.
- Configurações novas, todas opcionais. Suíte: **860 testes**.

### 2.7 v30 — várias chaves, uma IA só

- **Várias chaves da MESMA IA**, com troca automática quando uma estoura.
- **"Singularidade"**: uma IA só, com as ferramentas de todas.
- **IA local opcional** no modo Avançado.
- **Vídeo**: efeitos, 9:16 para Shorts, transições e legenda queimada.

---

## 3. v1.10 — as IAs que "não funcionavam" (29–30/10/2026)

Este é o changelog mais importante da fase: tudo foi medido com **chamada real** a cada serviço, não por leitura de código.

| IA | O que a chamada devolveu | Veredito |
|---|---|---|
| Gemini (chave 1) | respondeu "Ok" no `gemini-2.5-flash` | funciona |
| Gemini (chave 2) | 404 "no longer available to new users" | chave boa, conta nova, nome aposentado |
| Gemini 3.5/3.8 | 503 "high demand" nas duas chaves | sobrecarga do Google |
| OpenAI | 429 `insufficient_quota` | chave válida, conta sem crédito |
| OpenRouter | 429 "rate-limited upstream" no grátis | congestionamento do plano grátis |
| Groq | respondeu `openai/gpt-oss-120b` | funciona |

**O defeito de verdade:** a tela dizia "Chave do Gemini válida" sem nunca conversar com o Gemini — o teste só listava modelos, e listar funciona mesmo com todos em 503/404. Corrigido com teste de chat real para o Gemini, mensagem em português dizendo o motivo (sobrecarga, cota, chave recusada, nome morto) e 3 testes novos com as mensagens reais do Google.

**O Groq e o 413:** o erro não era saldo, era **tamanho do pedido** (limite de 8.000 tokens por minuto). Criada a categoria de erro `contexto`, repetição automática sem histórico e teto de contexto de 32.000 → 2.500 tokens.

**Também nesta rodada:**

- `print()` do script não sumia mais no `.exe` (`--zenith-run-script` religa a saída à força).
- `/tft porta wifi:IP` nunca esteve errado: era build antigo aberto.
- Vários anexos de uma vez, somando em vez de substituir.
- Carrinho passou a ser procurado direto no ESP32 (IP salvo → IP informado → descoberta UDP → rede própria → cabo USB).
- Teto de 15 s dos comandos virou `tempo_comando_s` (padrão 60, máximo 1800).

---

## 4. Launcher 1.0.1 — certificado e apagar por partes (30/10/2026)

**O erro do certificado.** `CERTIFICATE_VERIFY_FAILED` ao baixar o pacote: o Windows daquela máquina não tinha a raiz que assina o certificado do site. O `certifi` passou a ir **dentro** do `.exe`, e o contexto HTTPS confia no Windows **e** nele. A mensagem agora fala de certificado e de data/hora, não de "confira a internet".

**Apagar por partes.** `LimparZenith.exe` abre uma janela com uma caixinha por tipo de coisa:

| Caixinha | Apaga |
|---|---|
| Conversas e histórico | conversas, notas, lembretes, log de ações |
| Memória de longo prazo | `memory_db/` |
| Chaves de API | zera as chaves no `settings.json`, mantendo nome e persona |
| Fotos e vídeos gerados | `creations/` |
| Programas que ela criou | `skills/` |
| Temporários | `temp/` |
| Arquivos que você escreveu | `ZENITH.md`, `biblia_extra.md` |
| **DESINSTALAR TUDO** | + programa, Python dele, dados fora da instalação, atalhos, dados do Corpo |

Travas: pergunta antes; fecha o Zenith antes de apagar; nunca apaga raiz de disco, pasta de usuário ou pasta de sistema; informa MB liberados e o que ficou preso. Também funciona sem janela (`--limpar historico,chaves`, `--limpar tudo`, `--desinstalar`).

Suíte: **1526 testes** (40 pulados).

---

## 5. 1.0 Oficial no ar (31/10/2026)

- **Site publicado** com a página do projeto, o cartão de download, os hashes e o histórico de versões.
- **`latest.json`** com Launcher (12.747.600 bytes, `7191523e…`), Limpar (`4165b77e…`) e o pacote (75.272.569 bytes, `06947bb2…`).
- **Release `v1.0`** no GitHub com os três arquivos.
- **README do repositório** e **notas da release** escritos.

---

## 6. Tela preta, site novo e acervo (01/11/2026)

Rodada aberta com sete fotos do Anderson: a janela do avatar **toda preta** com o programa vivo no Gerenciador de Tarefas, o aviso do "Controle de Aplicativo Inteligente", a página de download e a janela do LimparZenith.

### 6.1 A tela preta — causa provável e as três correções

O Corpo (Godot 4.7, renderizador `gl_compatibility`) pedia **saída HDR** e ligava **MSAA 4x + FXAA** numa janela transparente, sem borda e sempre no topo. Em placa antiga (Intel HD Graphics, driver velho) essa combinação não desenha nada e sobra o preto — sem erro, sem mensagem.

| Arquivo | Mudança | Efeito |
|---|---|---|
| `body/zenith/project.godot` | `window/hdr/request_hdr_output` de `true` para `false` | tira o pedido de HDR, que em tela comum deixa a janela preta |
| `body/zenith/akira_body.gd` | novo `_aa_pode_ligar()` | desliga MSAA/FXAA sozinho em placa antiga; em placa boa nada muda |
| `zenith_launcher.py` | `_modo_video()` + `_comando_corpo()` + cadeia `normal → sem-aa → seguro` | se o Corpo morrer em menos de 4 s, tenta de novo sem os efeitos |

Saída manual para quem abre preta mas não fecha: `"body_video_modo": "seguro"` em `config/settings.json`, ou `ZENITH_VIDEO=seguro` na linha de comando. O log passa a registrar o modo de vídeo usado.

**Não reproduzido aqui:** a tela preta foi vista só pelas fotos. As correções atacam as três suspeitas reais e fazem o erro aparecer no log em vez de ficar silencioso.

### 6.2 O site

Página refeita: cabeçalho fixo, hero com selos, recursos em cartões, biblioteca em duas colunas, **cartão de download** com versão, data, tamanho do Launcher e do download total, botão principal e "Limpar ou desinstalar", SHA-256 com botão Copiar e o "como conferir" com o comando `certutil` pronto. Sem dependência externa e com tema claro e escuro.

### 6.3 Este acervo

- **Documento conceitual 2.0** (`docs/DOCUMENTO_DO_PROJETO.md`): a especificação atualizada, agora dizendo em cada parte o que já existe.
- **Este histórico** (`docs/HISTORICO_DE_MUDANCAS.md`), do protótipo até aqui.
- Ambos publicados no site em **Word (.docx)** e em texto (`.md`), com resumo na página.
- **`docs/TESTE_GERAL.md`**: roteiro para testar cada parte, do jeito que se descobre o erro no passo pequeno.

### 6.4 A janela de limpeza

Redesenhada: cada categoria virou um cartão com o que apaga e o **tamanho em disco**, com "marcar tudo / limpar seleção", aviso de consequência e resumo antes de confirmar.

---

## 7. O que foi provado e o que não foi

| Assunto | Situação |
|---|---|
| Suíte de Python | provada (roda sem Godot, sem internet, sem chaves) |
| Cérebro ↔ Corpo (protocolo) | provado por testes de contrato |
| Chamadas de IA | provadas com chave real (29/10); dependem de cota e do serviço |
| ffmpeg (cortar, juntar, narrar) | provado com arquivos reais |
| Launcher e `LimparZenith` | provados numa instalação falsa; download real de ponta a ponta nem sempre |
| Avatar no Godot | provado em checagem de scripts; a tela final depende da placa |
| Tela preta em notebook antigo | **não reproduzida** — correções preventivas |
| Robô (ESP32-S3 + Uno) | provado com placa falsa por HTTP; hardware real depende da placa |
| Bluetooth, Wi-Fi do carrinho, motores | não testados |
| Instalador assinado | não existe ainda (por isso o SHA-256) |

---

## 8. Como este histórico é mantido

1. Cada rodada ganha uma seção com data, o que mudou, o que foi provado e o que ficou pendente.
2. Os changelogs por versão continuam em `docs/historico/MUDANCAS_v*.md` — este documento é a visão de cima.
3. Ao publicar uma versão, atualizar também `site/versions.json` (o site lê esse arquivo).
4. O `.docx` é gerado a partir deste texto: `py -3 tools/gerar_documentos.py`.
