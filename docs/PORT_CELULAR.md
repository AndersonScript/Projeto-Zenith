# Zenith no celular — port, não reescrita (v1.11, rascunho)

Este documento acompanha os arquivos novos de `brain/` e `tests/`. Nada aqui altera o Zenith do PC.

## 0. As metas (ditas pelo Anderson, não negociáveis)

1. **Tudo no próprio celular.** Sem PC, sem servidor, sem "nada por fora". Não existe "modo PC" nesta versão.
2. **Igualzinho ao do PC**, adaptado ao celular: mesmo Cérebro, mesmo Corpo, mesmo visual (layout em retrato).
3. **VRM e IA local no aparelho.**
4. **Funcionar em qualquer celular (Android)**, com *downgrade*: a pessoa desliga ou reduz o que o aparelho dela
   não aguenta (VRM, voz, câmera, memória, IA local) e o resto continua.

## 1. O desenho

```
┌───────────────────────── um único celular Android ─────────────────────────┐
│  Corpo (Godot, o APK)  ──WebSocket ws://localhost:8765──  Cérebro (Python)  │
│   avatar VRM, chat, telas                                 28 mil linhas      │
│        ▲                                                       │             │
│        └──── ponte: microfone, câmera, tela, voz, Bluetooth ◄──┘             │
│                                                                               │
│   IA local: servidor llama.cpp dentro do app (127.0.0.1:8080/v1) ← o Cérebro │
│             o trata como mais uma IA do catálogo (igual ao Ollama no PC)     │
└───────────────────────────────────────────────────────────────────────────────┘
```

O `localhost` do Corpo→Cérebro, que no APK_ANDROID.md era o problema, deixa de ser: os dois moram no mesmo aparelho.
O que muda é só **como o Python alcança o hardware**, e é para isso que serve a camada de plataforma.

## 2. O que já está neste pacote

| Arquivo | Para quê | Estado |
|---|---|---|
| `brain/zenith_plataforma.py` | Interface única do que muda entre PC e celular; `detectar()` reconhece o Termux | testado |
| `brain/zenith_plataforma_android.py` | Implementação Android: o Cérebro pede, o app faz, por uma ponte JSON | testado com ponte falsa |
| `brain/zenith_plataforma_pc.py` | Lado PC: tela, câmera, notificação, abrir. Voz/microfone continuam nos módulos atuais | testado com bibliotecas falsas |
| `brain/zenith_memoria_leve.py` | Coleção SQLite com a mesma API do chromadb, para o celular | testado, **inclusive com o `ZenithMemory` real** |
| `brain/zenith_downgrade.py` | Lógica da tela de Desempenho: perfis, recomendação, escada de rebaixamento, IA local | testado |
| `brain/zenith_memory.py`, `zenith_vision.py`, `zenith_notify.py`, `zenith_gatekeeper.py`, `zenith_interaction.py` | **Já migrados** (ver `migracao.diff`). No PC nada muda; com `ZENITH_PLATAFORMA=android` (ou no Termux) usam a plataforma. `zenith_interaction` é a **voz**: falar (voz do Android, sem internet) e escutar (microfone + transcrição do Android, com a mesma detecção de silêncio do PC) | testado com Android falso |
| `brain/zenith_ponte_corpo.py`, `brain/zenith_headless.py`, `body/zenith/ponte_android.gd`, `body/zenith/brain_connector.gd`, `android_plugin/` | A ponte com o Android (seção 5) | Python testado; Godot **compila no 4.7.1** (v1.13, `--check-only`), mas não foi executado no Android; Kotlin **nunca compilado** |
| `body/zenith/zenith_desempenho_page.gd`, `zenith_desempenho_aplicar.gd`, `ui_manager.gd` (4 acréscimos defensivos) | A tela de Desempenho (seção 8) | Python testado; Godot **compila no 4.7.1** (v1.13), a tela de Desempenho não foi aberta |
| `tests/test_port_celular*.py`, `test_memoria_leve_integracao.py`, `test_importa_no_celular.py` | 150 testes novos, sem Android e sem internet. `test_importa_no_celular` é uma **trava**: cada módulo do Cérebro precisa importar num "celular simulado"; `test_port_celular_godot` trava a consistência Python↔GDScript↔Kotlin | passam no Linux |

Rodar: `python -m unittest discover -s tests -t .`

**Suíte inteira do PC com tudo isto dentro: 1657 testes, 1 falha — e essa falha já existia antes de qualquer mudança.**
É o `test_mini_janela_de_anexo` (`tests/test_v28.py`): ele procura no `ui_manager.gd` o texto `_attachment_chip.gui_input.connect(`, mas desde a
faixa de anexos da v1.0.2 o código usa `cartao.gui_input.connect(`. É teste desatualizado, não defeito do programa; não mexi nele.

**Nada disso rodou num Android de verdade.** Os testes provam a lógica e o contrato; não provam o aparelho.

## 3. Mapa das 25 dependências

25 dos 92 módulos de `brain/` importam direto alguma biblioteca de plataforma ou pesada; 67 não. (Contagem só de
`import`; chamadas de `subprocess`, caminhos de Windows e `.exe` não entram, e 35 módulos citam algo assim —
parte é só texto de aviso, parte é código. Separar módulo a módulo.)

| Biblioteca | Módulos | No celular | Situação |
|---|---|---|---|
| `chromadb` | `zenith_memory` | `ColecaoLeve` (SQLite, busca por palavras) | **migrado** e testado (seção 6) |
| `sounddevice`, `pygame`, `faster_whisper` | `zenith_interaction`, `zenith_diag` | ponte `mic.*`, `audio.*`, `stt.*`, `tts.*` | `zenith_interaction` **migrado** (falar e escutar); `zenith_diag` **migrado** (v1.19: pergunta ao aparelho em vez de acusar biblioteca do PC) |
| `cv2`, `mss` | `zenith_vision`, `zenith_anexos`, `zenith_fundo` | ponte `camera.capturar`, `tela.capturar` | `zenith_vision` **migrado**; `zenith_anexos` e `zenith_fundo` **migrados** (v1.19: o vídeo vem do Android, capacidade `video`) |
| `plyer` | `zenith_notify` | `notificacao.mostrar` | **migrado** |
| `serial` | `zenith_commands`, `zenith_hardware`, `zenith_tft` | `zenith_hardware`: porta `BLE` (Bluetooth, só ida). `zenith_tft`: **Wi-Fi** (Bluetooth não leva imagem). `zenith_commands`: só a mensagem do `/tft portas` | **v1.17:** `zenith_hardware` e as mensagens migrados e testados com plataforma falsa; Bluetooth nunca falou com um carrinho de verdade |
| `ctypes` | `zenith_admin`, `zenith_captura`, `zenith_desempenho`, `zenith_diag`, `zenith_janela` | `medir_sistema()` lê `/proc/meminfo`; janela/captura sem Zenith **não existem** no celular | desligar por plataforma |
| `tkinter`, `customtkinter` | `zenith_ui`, `zenith_widgets`, `zenith_gatekeeper` | a UI antiga some (o Corpo Godot a substitui). No **Gatekeeper**, a regra (`DeterministicGuard`) é pura e porta; a janela `ApprovalWindow` não — a aprovação vira tela do Corpo | Gatekeeper **migrado** (o Tk virou opcional; era ele que impedia o `zenith_core` de importar). **Falta confirmar que o Corpo já tem a tela de aprovação** |
| `PIL` | 12 módulos | Pillow existe para Android em alguns empacotadores | **a confirmar** no empacotamento |
| `matplotlib`, `sympy` | `zenith_formulas`, `zenith_matematica`, `zenith_video` | módulo opcional, ou pedir à IA | pesados; ficam fora do núcleo |

## 4. Como migrar um módulo (exemplo)

`zenith_vision.py`, hoje (PC): `import mss` no topo e `mss.mss()` dentro de `_capture_screen_raw`. Depois:

```python
from brain import zenith_plataforma

def _capture_screen_raw(self, max_w=0, jpeg=False):
    return zenith_plataforma.obter().capturar_tela(max_w, jpeg)     # (bytes, None) ou (None, motivo)
```

A assinatura é a mesma, então quem chama não muda. Migre **um módulo por vez** e rode os testes do PC a cada um.

## 5. A ponte Cérebro ↔ Corpo ↔ Android (agora existe, em três lados)

O Cérebro pede, o Corpo repassa, o plugin Android faz. Tudo pelo **mesmo WebSocket** que o Corpo e o Cérebro já usam:

```
Cérebro (Python)                    Corpo (Godot)                          Plugin Android (Kotlin)
AndroidPlataforma                   ponte_android.gd                       ZenithAndroidPlugin
  └ PonteCorpo ──ponte_chamar──────►  └ plugin.chamar(id, nome, json) ───►   └ faz (TTS, áudio, microfone...)
             ◄──ponte_resposta───────  ◄─ sinal resposta(id, json) ────────
             ◄──ponte_evento (mic.quadro, capacidades)───────────────────── sinal evento(nome, json)
```

| Lado | Arquivo | Estado |
|---|---|---|
| Cérebro | `brain/zenith_ponte_corpo.py` (+ poucas linhas em `zenith_headless.py`) | **testado** com um Corpo falso (17 testes) |
| Corpo | `body/zenith/ponte_android.gd` (+ gancho em `brain_connector.gd`, só ativa no Android) | **compila no Godot 4.7.1 (`--check-only`); nunca executado num Android** |
| Android | `android_plugin/` (Kotlin) | **esqueleto, nunca compilado** |
| Os três | `tests/test_port_celular_godot.py` | confere que os **nomes** combinam entre Python, GDScript e Kotlin |

Decisões que vieram de erros reais do código atual:
- **`chamar` bloqueia até a resposta, então nunca roda na thread do WebSocket** (é nela que as respostas chegam; foi o
  mesmo problema do `approval_response` na v26). Pedir ali levanta erro na hora, em vez de travar o Corpo.
- **`capacidades.listar` nunca vai à rede**: o Corpo *anuncia* o que o aparelho tem (ao conectar e quando uma permissão
  muda). Assim `tem("microfone")` é seguro de qualquer lugar, e o Cérebro pode nascer **antes** de o Corpo conectar.
- Corpo caiu no meio de um pedido → o pedido falha na hora com uma frase, sem esperar o tempo esgotar.
- Permissão do Android ainda não concedida → o Godot abre a janela de permissão e responde com uma frase clara.

**O que o plugin Android faz hoje (no papel):** medir o aparelho, tocar áudio, gerar a voz (sem internet), abrir o
microfone, notificar, abrir endereços da web e (v1.12) transcrever fala em texto com o **Vosk**, offline — **só quando
o modelo de português está no aparelho**. **O que ele ainda NÃO faz:** capturar a tela, a câmera, Bluetooth (carrinho)
e IA local. Sem o modelo, o Zenith fala no celular mas não entende o que você diz (o Cérebro trata como "não existe").
**Por que Vosk e não o reconhecedor do Android:** o Cérebro entrega ÁUDIO PRONTO (grava pela ponte, detecta o silêncio
e pede o texto a cada ~1 s); o reconhecedor do Android não recebe áudio pronto, ele abre o microfone sozinho. Whisper
dentro do app fica como módulo extra para celulares fortes. **Nada disso foi compilado nem rodou num aparelho**; o
baixador do modelo ainda não existe (cópia manual — veja o README do plugin).

## 6. Memória (já migrada)

`zenith_memory.py` agora escolhe sozinho: no PC importa o chromadb no mesmo lugar de sempre; no modo celular
(`detectar() == "android"`) nem importa o chromadb e usa `zenith_memoria_leve.abrir(MEMORY_DIR)`. O restante do arquivo
(`save`, `recall`, `fatos_fixos`, `forget`, resumo...) ficou **igual** e foi testado inteiro nesse modo.
Limite honesto: a busca é por **palavras**, não por **sentido** ("carro" não acha "automóvel"). Memória por sentido no
celular exige um modelo de embeddings pequeno; o `recomendar()` já avisa isso ao usuário.
Para levar a memória do PC: `colecao_leve.importar_de(colecao_chroma)`, uma vez.

## 7. IA local no celular

Plano: um servidor **llama.cpp** (que fala a API compatível com OpenAI) rodando dentro do app, em `127.0.0.1`. O
Cérebro já sabe usar IA por endereço (o caminho do Ollama/LM Studio); a plataforma entrega o endereço em
`endereco_llm_local()`. Modelos candidatos e RAM estimada estão em `MODELOS_CELULAR`:
0.5b ≈ 1,2 GB · 1.5b ≈ 2,6 GB · 3b ≈ 4,0 GB livres (**estimativas — medir no aparelho**).
Qualidade realista: modelos assim conversam, mas não programam bem. A IA local é o *plano B* sem internet, não a
substituta das IAs grandes.

## 8. Downgrade — a tela de Desempenho

Recursos (do melhor ao pior): avatar `vrm→padrao`, qualidade gráfica, FPS, voz (falar), voz (escutar), câmera/tela,
memória `vetorial→leve`, IA local. Perfis: `completo` (≥10 GB RAM), `medio` (≥6), `leve` (≥4), `minimo`.
**Os limiares são estimativas.** Ficam em `LIMIARES` e podem ser trocados em `settings["downgrade_limiares"]` — ajuste
depois de medir. O módulo **só sugere**: `proximo_passo()` devolve o ajuste que menos tira do Zenith; quem aplica é a
pessoa. O piso do avatar é o padrão (regra "avatar sempre visível").

**A tela** (Configurações → Sobre, logo abaixo de "Saúde do Zenith") mede o aparelho, mostra o que recomenda e deixa
escolher cada recurso. Aplicar só vale quando a pessoa aperta o botão; a "sugestão" apenas move a escolha.

**O que cada chave faz hoje**

| Recurso | Efeito | Quem aplica | Estado |
|---|---|---|---|
| Voz (falar) | `voice_enabled`; corta a fala na hora | Cérebro | testado |
| Voz (escutar) | `permissions.microphone = never`; para a escuta | Cérebro | testado |
| Câmera e tela | `permissions.camera` e `permissions.screen = never` | Cérebro | testado |
| IA no aparelho | `ia_local_ativa = false` | Cérebro | testado |
| FPS | `Engine.max_fps` | Corpo (Godot) | escrito, não executado |
| Qualidade gráfica | escala 3D e MSAA da janela principal (no Compatibility pode ter pouco efeito) | Corpo (Godot) | escrito, não executado |
| Avatar | a escolha é guardada, mas **o Corpo ainda não troca o avatar**: o seletor aparece desativado | — | **não implementado** |
| Memória | decidida na abertura, pela plataforma (no celular é sempre a leve) | — | sem efeito ao vivo |

**É reversível, e de verdade.** Rebaixar guarda o valor que estava antes (`downgrade_guardado`); religar devolve
**exatamente** esse valor. Se a pessoa já tinha posto a câmera em `never`, ela continua `never` depois de religar: o
módulo nunca solta uma permissão por conta própria.

**Defesa do PC:** a `ui_manager.gd` carrega a tela com `load()` conferido (nunca `preload`). Se o meu arquivo novo tiver
um erro de compilação, a tela só não aparece — o resto do Zenith abre normalmente.

## 9. Provas, nesta ordem (cada uma decide o que vem depois)

- **P1 — o avatar abre?** Exportar o Corpo atual para APK e ver o VRM no celular (desempenho, tamanho, FPS). Precisa
  de JDK 17, Android SDK e templates de exportação Android (~2 GB, conforme o APK_ANDROID.md). **Se o VRM não rodar
  bem, o plano de design muda.**
- **P2 — o cérebro roda no aparelho?** Cérebro dentro do Termux + APK do Corpo conectando em `localhost`. O
  `detectar()` já trata o Termux como Android.
- **P3 — a IA local anda?** llama.cpp no celular com o 0.5b e o 1.5b: quantos tokens por segundo, quanta RAM, quanto esquenta.
- **P4 — Python dentro do APK.** Python embutido e Godot no mesmo app é o maior desconhecido técnico.

Já migrados: memória, visão (câmera e tela), notificação, Gatekeeper e voz. **Faltam (v1.19):** do lado Android, **a IA local** (precisa de um servidor nativo); a captura de tela, a câmera e o vídeo existem **só escritas**, nunca compiladas; e, da transcrição (`stt.*`), **o baixador do modelo e a medição no aparelho** (o código do Vosk existe, mas nunca foi compilado). O resto da ponte existe (seção 5), mas **nunca foi executado fora dos testes**.

Estado de importação: num celular simulado, **95 dos 97 módulos** do Cérebro já importam; os 2 que não (`zenith_ui`, `zenith_widgets`) são a interface antiga em Tk, que no celular o Corpo Godot substitui.

## 10. O que NÃO está resolvido

- Nada foi testado em Android real. Servidor llama.cpp dentro do app, Python embutido e o VRM são hipóteses.
- O Android encerra processos em segundo plano: o Cérebro precisará rodar como serviço em primeiro plano, com
  notificação fixa e custo de bateria.
- **Voz:** o Edge-TTS depende de internet (e quebrou em outubro). Para "tudo no celular", a voz base é a do Android
  (funciona em qualquer aparelho) e uma voz melhor (Piper, Kokoro) entra como módulo baixável. Para escutar:
  Vosk offline no app (decidido na v1.12, porque aceita o áudio pronto que o Cérebro entrega); Whisper pequeno fica
  como módulo extra. Os rótulos `whisper` / `sistema` de `voz_entrada` em `zenith_downgrade.py` são só nomes de nível
  (só `desligada` tem efeito) e não descrevem mais o motor — renomear fica para depois.
- RVC, firewall/antivírus e edição pesada de vídeo **não existem** no celular.
- O autoajuste que reescreve o próprio código **não existe** no celular: vira ajuste de configurações e de dados
  (catálogo de provedores, skills, prompts) vindos do `latest.json`, com SHA-256.
- Tamanho do APK: cada avatar VRM tem ~18 MB; avatares extras e modelos de IA entram como download dentro do app.
- Distribuição: a regra de verificação de desenvolvedor do Android já vale no Brasil; confirme no Android Developer
  Console o caminho gratuito para estudantes e hobistas antes de distribuir para outras pessoas.


## 13. v1.13 a v1.17 — Godot de verdade no Linux, layout de celular, projeto Android e plugin

**O que mudou na forma de testar.** O Godot 4.7.1 (a mesma versão do editor) roda no Linux sem tela, e com `xvfb` + OpenGL por
software ele **desenha a interface de verdade**. Então, a partir da v1.13, o lado Godot deixou de ser "só escrito": os 17 arquivos
`.gd` de `body/zenith/` passam no `--check-only` (o verificador pega erro de propósito: conferido com um arquivo ruim), e o layout de
celular foi **renderizado e olhado** em 390×844. Reproduzir: `tests/godot/verificar_godot.sh sintaxe` e `... prints`.
Isto **não** substitui o celular: é o Godot de PC, com tela virtual; não prova Android, toque, teclado virtual, desempenho nem o VRM
(os arquivos de avatar .vrm nem vêm no zip público, então o avatar 3D não aparece nesses prints).

**O layout (`body/zenith/zenith_layout_celular.gd`, 1 arquivo novo + 3 linhas na `ui_manager.gd`).** Só liga no Android ou com
`--layout-celular`; no PC normal nada muda — conferido: o print da interface do PC é **idêntico pixel a pixel** antes e depois.
A interface é uma `Window` à parte; no celular ela vai para baixo de uma faixa de ~34% da altura (reservada ao avatar). Fase 1:
1. a janela da interface ocupa a tela abaixo da faixa do avatar (sem borda, sem redimensionar, sem o "mover para o monitor");
2. some o botão de mover a janela do avatar (só faz sentido com duas janelas);
3. a barra lateral vira **gaveta** (300 px, ou 82% da largura), aberta pelo botão ☰; tocar em qualquer botão dentro dela a fecha;
4. "Parar", "Parar observação" e a linha de atividade saem da barra de cima (não cabem em 390 px) e ganham uma faixa própria
   logo abaixo, com botões de 44 px. Sem atividade, a faixa tem altura zero.

**Erros que o teste visual pegou (e que eu teria entregue):** a gaveta ficava desenhada *por baixo* do chat (a aparência põe camadas
de efeito no meio dos filhos da raiz; a ordem não é a que eu supus); o título "Zenith" sumia espremido; o texto da atividade era
cortado e tudo encostava nas bordas.

**Fase 2 (v1.14) — telas cheias.** Uma linha na `_show_overlay` (o ponto único que abre cartões) chama `preparar_cartao`:
Configurações, Memórias e Biblioteca viram **tela cheia**; a aprovação de ações e o primeiro uso viram **diálogo largo**, com
botões de 48 px (Aprovar/Negar são trava de segurança). As Configurações ganharam navegação de celular: **lista de 8 seções ->
seção em tela cheia**, com ‹ voltar e "Salvar e Aplicar" fixo embaixo. Para a tela não estourar em 390 px, regras gerais (sem
mexer na `ui_manager`): texto, botão de linha inteira e caixa de marcar quebram linha; grade com mais de 2 colunas vira 2 (os 10
temas do Estúdio); linha de componentes que não cabe quebra para a de baixo (a linha original fica no lugar). Renderizado e
conferido: lista, Voz, Corpo/VRM, Estúdio, Chaves & IAs, Memórias e aprovação. **Não conferido com dados reais:** Aparência,
Permissões e Sobre foram vistas só com o Cérebro desligado (valores padrão); a Biblioteca com categorias e o histórico de
Memórias dependem de dados do Cérebro e foram vistos vazios; o cartão de "carregando avatar" não foi tocado.
Um erro do meu primeiro cálculo (o texto que quebra linha informa a largura do texto inteiro) transformava "texto + seletor" em
coluna de letras soltas; achado no print e corrigido (`_largura_minima_real`).

**Fase 3 — avatar, teclado e voltar.** O avatar 3D é **enquadrado na faixa de cima**: a câmera recua (o avatar fica `faixa/altura` vezes
menor, sem mexer no FOV, que distorceria) e desce no próprio plano. A fórmula foi conferida numa cena com a MESMA câmera do Corpo e
uma régua no lugar do busto: 527 px viraram 179 px (34%) com o centro em 141 px (meio da faixa de 286 px = 143). **Não foi
conferido com o avatar de verdade** (não há `.vrm` aqui): se sair torto, "Corpo / VRM > Ajustar arrastando" corrige à mão. O
**teclado virtual** empurra a interface para cima (a faixa do avatar encolhe de 286 para 120 px enquanto se digita; simulado com
`--celular-teclado=330`: janela em y=120, base em 514 = 844 − 330). O **botão/gesto voltar** fecha uma coisa por vez (gaveta ->
seção -> lista -> tela) e **não fecha a aprovação de ação** (aprovar/negar tem de ser escolha explícita); simulado: 1º voltar leva
da seção à lista, 2º fecha as Configurações. O Corpo deixou de chamar funções da janela flutuante do PC quando é Android.

**Projeto Android.** `project.godot`: em pé, `quit_on_go_back=false`, texturas ETC2/ASTC (exigência do Android com o renderizador
Compatibility), e os ajustes de janela do Android só com o sufixo `.android` (o PC não muda: print idêntico). Preset **Android** em
`export_presets.cfg` (ARM64, Gradle, internet, microfone, notificações). Conferido: o Godot 4.7.1 empacota o projeto com esse preset
(`--export-pack`, código de saída 0). **Não conferido:** exportar o APK (precisa do SDK/templates, que eu não tenho).

**Plugin Android v2 + Gradle.** O formato `.gdap` está obsoleto; agora há `android_plugin/` com `build.gradle.kts`,
`settings.gradle.kts`, manifesto sem `package=` (o Gradle atual recusa) e o addon do editor
`body/zenith/addons/zenith_android/` (diz ao Godot qual AAR empacotar e quais dependências baixar). O editor do Godot carrega o
addon sem erro. O 1º rascunho do Gradle esquecia `androidx.core` (o plugin usa `NotificationCompat`): achado e corrigido, e um
teste agora confere que toda biblioteca importada está declarada. Versões do Gradle/Kotlin/AGP **escolhidas por mim, não
verificadas juntas**. O wrapper `gradlew` não vem no pacote.

**Fala.** Baixador do modelo de fala no plugin (`modelo.baixar`, descompacta com proteção contra caminhos maliciosos) + linha
"Entender a fala (sem internet)" na seção Voz (barra de progresso renderizada a 63%, simulada). Se o microfone ou o modelo faltam,
o chat agora diz o motivo em português (antes mandava a mensagem do PC: "instale sounddevice"). **O baixador nunca baixou nada de
verdade; confirme a URL do modelo.**

**Carrinho.** Bluetooth LE no plugin (Nordic UART, nome e UUIDs idênticos aos do firmware, conferido por teste) e, no Cérebro, o
carrinho usa Bluetooth no lugar do cabo USB quando está no celular. Nunca falou com um carrinho de verdade.

**Avatar simples (v1.17).** O "avatar padrão" do downgrade não existia: era o próprio VRM. Agora há `zenith_avatar_simples.gd`: um
personagem **low-poly desenhado em código** (esferas, cápsulas e caixas; sem `.vrm`, sem esqueleto, sem sombreador MToon) com respiração,
piscar, cabeça que inclina/gira, boca que fala e as expressões feliz/brava/triste/surpresa/neutra. Usa os MESMOS nomes de estado e de
expressão do VRM (`set_life_state`/`set_expression`; um teste extrai os nomes do `akira_body.gd` e confere que o avatar os conhece).
`akira_body.usar_avatar_simples(true|false)` esconde o VRM (não o descarrega) e mostra o personagem; a tela de Desempenho (seletor
"Avatar", que deixou de ficar desligado) chama isso pelo mesmo caminho do FPS/qualidade. O piso do downgrade (`minimo`) é `padrao`.
**Visto:** renderizado em 6 estados com a câmera REAL do Corpo; aplicado no Corpo de verdade por `aplicar({"recursos":{"avatar":"padrao"}})`;
e a prévia do celular completa (avatar enquadrado na faixa de cima + interface embaixo). Erros que o teste visual pegou: as
sobrancelhas ficavam escondidas pelo cabelo e, depois, com o giro trocado (a "brava" saía com cara de triste). **Limites honestos:** o VRM
escondido continua na memória e o `_process` do Corpo ainda o consulta (o ganho é na hora de DESENHAR); o visual é simples de propósito
e nunca foi comparado ao VRM nem visto num celular real; a escolha só é aplicada quando a tela de Desempenho (ou o Cérebro, na conexão)
manda `avatar`.

**Auditoria de Windows (`brain/`).** 37 módulos citam algo de Windows, mas **nenhum quebra fora do Windows**: as 63 linhas
sinalizadas eram quase todas texto (docstrings, mensagens, regras de segurança que citam ".exe"). As poucas chamadas diretas
(`os.startfile`, `ctypes.windll`, flags de processo) estão protegidas por checagem de sistema ou `try/except`, e `admin`,
`captura` e `janela` devolvem valores seguros fora do Windows (testado simulando Linux e Android). Um teste trava isso: chamada nova
de Windows sem revisão falha a suíte. É análise estática + chamada dos pontos de entrada; **não** rodei cada recurso.

**Funciona só no PC (de propósito, não é defeito):** clonagem de voz (RVC), importar avatar pelo editor do Godot (`zenith_vrm_import`),
atualização por instalador `.exe`, firewall/antivírus, reabrir como administrador, o auto-ajuste que reescreve o código.

**FALTA (nada disto existe):**
- **Plugin:** (v1.19 escreveu captura de tela, câmera e vídeo — seção 15 —, sem compilar) servidor de IA
  local (exige compilar o llama.cpp para Android) e o **serviço em primeiro plano** que mantém o Cérebro vivo — este depende da
  **Prova 4** (como o Python vai dentro do app; sem isso não dá para escrevê-lo).
- **Cérebro:** (v1.19: anexos, fundo, diag, desempenho e IA local migrados — seção 15.) (v1.17) o carrinho por Bluetooth cobre `skills/carrinho.py` e a porta `BLE` do `zenith_hardware` (só ida: o plugin
  escreve e não lê de volta). A TFT **não** usa Bluetooth — imagem só passa por cabo ou Wi-Fi —, então no celular o caminho é
  `/tft porta wifi:auto` (já existia no código). Memória por sentido (embeddings) é opcional.
- **Corpo:** Biblioteca com categorias e Memórias com histórico só
  foram vistas vazias.
- **Só o aparelho real responde:** toque, tamanho dos botões, fluidez, bateria, o Vosk, o Bluetooth, o enquadramento do avatar.

## 14. v1.17 (segundo chat) — hardware e TFT no celular (só Python, plataforma falsa)

**Nota do v1.18:** dois chats trabalharam ao mesmo tempo e os dois chamaram o resultado de "v1.17". O avatar simples (Corpo, seção 13) e o
hardware/TFT (esta seção, Cérebro) não mexem nos mesmos arquivos de código; o v1.18 é a junção dos dois, com a suíte inteira rodando junta.

**O que mudou (3 arquivos que já existiam + 1 teste novo):**
- `brain/zenith_hardware.py`: a "porta" `BLE` (ou `BLE:NomeDoDispositivo`) manda a linha por Bluetooth LE, pelo plugin (`ble.enviar`). É só IDA:
  o plugin escreve e não lê de volta, então nunca há resposta do aparelho (a frase devolvida diz isso). No PC nada muda. Sem cabo e sem
  pyserial no celular, a mensagem deixa de mandar instalar o pyserial e diz o que usar.
- `brain/zenith_tft.py` e `brain/zenith_commands.py` (`/tft portas`): no celular, sem pyserial, a frase manda usar `/tft porta wifi:auto`.
  **A TFT não usa Bluetooth:** a TFT recebe quadros JPEG e o plugin só tem `ble.enviar` (sem leitura nem confirmação); imagem só passa por
  cabo ou Wi-Fi. O Wi-Fi já existia no código (`SocketComoSerial`, `wifi:auto`).
- `tests/test_port_celular_hardware_ble.py`: 19 testes. Suíte desse chat: **1723 testes, 1 falha** (a antiga, `test_mini_janela_de_anexo`); junta com o avatar simples (v1.18): **1729 testes, 1 falha**.

**O que NÃO está provado:** o Bluetooth nunca falou com um carrinho de verdade; o plugin Kotlin nunca foi compilado; o Wi-Fi da TFT
no celular nunca foi testado num aparelho (só o código de rede, que é o mesmo do PC).

## 15. v1.19 — fechando o que dava para escrever (Python testado com plataforma falsa; Kotlin só escrito)

**Cérebro (testado só no PC, com Android de mentira — 38 testes em `tests/test_port_celular_v19.py`):**
- **Capacidade nova `video`** (`video.info`, `video.quadros`): no PC quem lê vídeo continua sendo o OpenCV; no celular, sem OpenCV, o
  Cérebro pede ao Android. `zenith_anexos` (miniatura e duração do vídeo anexado; a miniatura do celular sai em JPEG, a do PC em PNG)
  e `zenith_fundo` (vídeo vira quadros `f0001.jpg...`, o mesmo formato do PC) usam isso. Sem a capacidade, o fundo diz uma frase honesta.
- **`zenith_desempenho`:** no celular `medir()` traz bateria e temperatura (o plugin já as media; o Python não as usava) e o texto
  diz "Este aparelho". No PC nada mudou. O downgrade já usava esses números.
- **`zenith_ia_local`:** `detectar()` acha o servidor do próprio app (`endereco_llm_local()`) antes dos de sempre; as mensagens do
  celular não mandam instalar o Ollama. **Mas o servidor de IA nativo NÃO existe** (precisa compilar o llama.cpp para Android).
- **`zenith_diag`:** no celular lista o aparelho (memória, bateria, temperatura) e o que o app anuncia, em vez de acusar
  `pygame`/`sounddevice`/`mss` não instalados. No PC a lista é a de sempre.
- **`docs/BIBLIOTECAS_ANDROID.md`:** mapa de tudo o que o Cérebro importa de fora; na PARTIDA ele exige `websockets`, `requests`,
  `openai`, `google-genai` e `Pillow`. **Nenhuma foi conferida num aparelho** (as de código nativo estão marcadas CONFERIR).
  Um teste quebra se aparecer biblioteca nova sem entrada no documento.
- Os tempos de espera da ponte subiram: `video.quadros` 110 s (o plugin desiste em 90 s) e `tela.capturar` 60 s (a pessoa lê a janela do Android).

**Plugin Kotlin (ESCRITO, NUNCA COMPILADO — espere erros no primeiro build):**
- `video.info` / `video.quadros` (MediaMetadataRetriever), `camera.capturar` (Camera2 sem prévia; a 1ª foto pode sair escura) e
  `tela.capturar` (MediaProjection + `ZenithCapturaService`, serviço em primeiro plano do tipo `mediaProjection`, notificação visível,
  fecha sozinho depois de 2 min sem pedido). Manifesto: CAMERA, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MEDIA_PROJECTION.
- Os testes só conferem o TEXTO: nomes iguais nos três lados, chaves que fecham, e a ordem que o Android 14 exige na captura de tela
  (permissão -> serviço -> projeção -> callback antes da tela virtual). **Não provam que compila nem que o Android obedece.**
- Achado pelo teste novo: duas funções do v1.16 usavam `catch (_: Exception)`, que o Kotlin 2.0.21 pode recusar; trocado por um nome.

**Continua FALTANDO:** servidor de IA local (llama.cpp), serviço que mantém o Cérebro vivo (Prova 4), API de imagens (a escolha é do
Anderson), calibrar os limites do downgrade, e tudo o que só um aparelho real responde.
