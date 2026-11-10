# Zenith — licenças de terceiros

Este arquivo existe porque o Zenith usa bibliotecas e arquivos feitos por outras pessoas. A licença
de cada um vale mais do que a nossa vontade: antes de **distribuir** o `.exe` (GitHub, pendrive,
amigo), confira esta lista.

> **O que está marcado `CONFERIR` não foi verificado por mim.** Não inventei licença: quando não
> tenho certeza, está dito aqui. Os dois itens mais importantes para distribuição estão no fim
> (ffmpeg e avatares) — eles não são "detalhe técnico", são o que pode impedir de publicar.

## Bibliotecas Python (Cérebro)

| Pacote | Licença | Observação |
|---|---|---|
| `websockets` | BSD-3-Clause | conexão Corpo ↔ Cérebro |
| `openai` | Apache-2.0 | cliente usado também para Groq/OpenRouter/LM Studio |
| `google-genai` | Apache-2.0 | Gemini |
| `chromadb` | Apache-2.0 | memória de longo prazo (local) |
| `onnxruntime` / `tokenizers` | MIT / Apache-2.0 | embeddings do chromadb |
| `matplotlib` | Licença própria (base PSF, compatível com uso comercial) | gráficos e equações |
| `Pillow` | MIT-CMU (HPND) | imagens/papel de parede |
| `edge-tts` | GPL-3.0 | voz online da Microsoft — **copyleft**: se você redistribuir o `.exe`, revise |
| `pygame-ce` | LGPL-2.1 | tocar áudio |
| `requests` | Apache-2.0 | HTTP |
| `plyer` | MIT | notificação do Windows (opcional) |
| `pyserial` | BSD-3-Clause | Arduino/ESP32 |
| `mss` | MIT | captura de tela |
| `opencv-python-headless` | Apache-2.0 | câmera |
| `numpy` | BSD-3-Clause | áudio |
| `sounddevice` | MIT | microfone |
| `faster-whisper` | MIT | transcrição local (o **modelo** baixado tem licença própria, MIT/OpenAI Whisper) |
| `sympy` | BSD-3-Clause | conta exata (opcional) |
| `psutil` | BSD-3-Clause | medir RAM/CPU/disco para recomendar IA local (opcional, v1.7) |
| `pywin32-ctypes` | BSD-3-Clause | ícone do `.exe` (ferramenta de build) |
| `PyInstaller` | GPL-2.0 **com exceção** para empacotamento de programas | permite distribuir o `.exe` |
| `customtkinter` | MIT | usado por utilitários antigos |
| `pygame` (variante antiga) | LGPL-2.1 | substituído por `pygame-ce` |

## Motor e firmware

| Item | Licença | Observação |
|---|---|---|
| **Godot Engine 4.x** | MIT | o Corpo (avatar/interface). Pode ser redistribuído mantendo o aviso de copyright |
| Addon **VRM** do Godot | MIT | carrega o avatar `.vrm` |
| `firmware/` (ESP32 / pistão) | código do projeto | bibliotecas do Arduino/ESP32 têm licença própria (LGPL/Apache) |

## ⚠️ 1. ffmpeg (edição de vídeo) — **CONFERIR antes de distribuir**

O Zenith usa o `ffmpeg` que vem com o pacote `imageio-ffmpeg` (ou o que estiver em
`tools/ffmpeg/`). **A licença depende do binário**: builds com `libx264` são **GPL** (o mais comum);
builds sem ele podem ser LGPL.

- Uso pessoal: sem problema.
- **Distribuir o `.exe` com o ffmpeg dentro**: você precisa cumprir a GPL do binário (oferecer o
  código-fonte correspondente e os avisos) **ou** trocar por um build LGPL.
- Ação prática: rodar `ffmpeg -version` e ler a linha de configuração (`--enable-gpl` aparece nos
  builds GPL). Registrar aqui a versão e a origem do binário usado.

## ⚠️ 2. Avatares VRM — **CONFERIR antes de distribuir**

`body/zenith/addons/avatars/Zenith.vrm` e `Cypher.vrm` **não são deste projeto** e não têm licença
registrada nesta pasta. Antes de publicar o Zenith no GitHub (ou mandar para outra pessoa), é
preciso **conferir os termos do criador de cada avatar** (a maioria permite uso pessoal e proíbe
redistribuição do modelo).

Enquanto isso não estiver resolvido:

- o Zenith pessoal do Anderson pode usar os dois normalmente;
- a **edição pública** (quando existir) deve sair com um avatar livre, licenciado para
  redistribuição — ou sem avatar nenhum.

## Feitos para este projeto

| Item | Autor | Licença |
|---|---|---|
| Código do Zenith (Cérebro Python + Corpo Godot) | Anderson Ricardo de Souza Filho | a definir (aberto ou fechado — decisão dele) |
| `assets/zenith_icon.ico`, `body/zenith/icon.svg` | Anderson | uso do projeto |
| Textos, guias e documentação | Anderson | uso do projeto |

## Como manter esta lista

Ao adicionar uma biblioteca, fonte, ícone, som ou modelo novo:

1. abra a página oficial do item e leia a licença;
2. escreva aqui: nome, autor, licença, link e **data da conferência**;
3. se for para **distribuir**, confira se a licença permite redistribuição dentro de um `.exe`.

## Adicionado na v1.1 (19/10/2026)

| Item | Autor | Licença | Observação |
|---|---|---|---|
| 51 ícones em `body/zenith/assets/icones/` | desenhados do zero para o Zenith (pacote `ICONES_ZENITH_originais`, + 4 novos: atualizar, salvar, desfazer, estrela) | originais do projeto — sem terceiros, sem emoji | podem ser usados, modificados e distribuídos com o Zenith |
| Shader `zenith_fx.gdshader` (aurora, fogo, plasma, tinta...) | escrito do zero para o Zenith | original do projeto | não copia shader de ninguém |
