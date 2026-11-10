# Plugin Android do Zenith (ZenithAndroid) — ESQUELETO NÃO COMPILADO

Este plugin é o que **faz** no Android o que o Cérebro pede: tocar áudio, gerar a voz (sem internet), abrir o microfone,
notificar, medir o aparelho. O Godot o chama por `body/zenith/ponte_android.gd`.

**Estado honesto:** foi escrito sem Android Studio, sem Gradle e sem Godot — a partir do contrato em
`brain/zenith_plataforma_android.py`. Nunca foi compilado. Erros de nome de classe ou de assinatura do `GodotPlugin`
são esperados no primeiro build; corrija e me conte a mensagem.

## O que ele anuncia (e o que NÃO)
Sempre anuncia o que está implementado: `sistema`, `audio_saida`, `voz_local`, `microfone`, `notificacao`, `abrir`; e `ble` quando o
aparelho tem Bluetooth LE.
Anuncia `transcricao` (fala → texto, com o **Vosk**) **só quando o modelo de português está no aparelho** — sem modelo, o
Cérebro trata como "não existe" e segue sem quebrar (o Zenith fala, mas não entende você).
**v1.19 — escritos, NUNCA compilados nem rodados num aparelho** (provavelmente darão erro no primeiro build; cole a mensagem):
- `video` (`video.info`, `video.quadros`): o `MediaMetadataRetriever` lê o vídeo; o OpenCV quase nunca existe no celular. Sempre anunciado.
- `camera` (`camera.capturar`): Camera2 **sem prévia**; tira `warmup` fotos descartáveis e fica com a última (a 1ª foto pode sair
  escura). Anunciada só se o aparelho tem câmera; a permissão CAMERA é pedida pelo Godot na hora de usar.
- `tela` (`tela.capturar`): MediaProjection. O Android mostra a janela de permissão (1ª vez de cada sessão) e uma notificação
  enquanto captura (`ZenithCapturaService.kt`, serviço em primeiro plano do tipo `mediaProjection`). A sessão fecha sozinha
  depois de 2 min sem pedido. **Não é** o serviço que mantém o Cérebro vivo em segundo plano (esse depende da Prova 4).
**Ainda não existe** (e por isso não é anunciado): `llm_local` — precisa de um servidor de IA nativo (llama.cpp), que não dá para
escrever sem compilar código nativo.

## Fala → texto (Vosk) — v1.12, NÃO COMPILADO nem testado num aparelho
**Por que Vosk e não o reconhecedor do Android:** o Cérebro grava o microfone pela ponte e, a cada ~1 s, manda o áudio
*já gravado* pedindo o texto (é o que faz o texto aparecer enquanto você fala). O reconhecedor do Android não recebe
áudio pronto — ele abre o microfone sozinho — e brigaria com o Cérebro. O Vosk recebe áudio pronto e roda sem internet.
Um Whisper dentro do app fica como módulo extra para celulares fortes (mais preciso, bem mais pesado).

1. **Biblioteca:** no `build.gradle` do módulo do plugin, repositório `mavenCentral()` e
   `implementation("com.alphacephei:vosk-android:0.3.75")` (versão vista na Maven Central em 01/11/2026 — confirme a
   mais recente na hora). Se o build ou o app reclamar de `libjnidispatch.so`, acrescente também
   `implementation("net.java.dev.jna:jna:5.18.1@aar")`. **Não verifiquei** se o Godot leva essas dependências para dentro
   do APK sozinho; se não levar, declare-as também no `build.gradle` do modelo de compilação do projeto.
2. **Modelo de português:** baixe o modelo *small* de português em https://alphacephei.com/vosk/models (o nome visto
   foi `vosk-model-small-pt-0.3`), descompacte e deixe as pastas `am`, `conf`, `graph`… **direto** dentro de
   `<pasta de arquivos do app>/modelos/vosk-pt/`. O plugin procura primeiro em `getExternalFilesDir(null)`
   (`/sdcard/Android/data/<id do pacote do seu preset>/files/modelos/vosk-pt/`, dá para copiar com `adb push`; no
   Android 11+ o gerenciador de arquivos do celular costuma não deixar mexer nessa pasta) e depois em `filesDir`.
   O modelo **não** vai dentro do APK (~50 MB): no produto final será um módulo baixável — **o baixador ainda não existe**.
3. O plugin carrega o modelo em segundo plano assim que anuncia `transcricao`, para a 1ª fala não esperar.
4. Em vez de copiar à mão, use o **baixador** (seção seguinte).

**Não medido (precisa de um celular de verdade):** quanta RAM o modelo ocupa carregado, quanto tempo leva cada
transcrição de ~1 s de áudio, quanto esquenta/gasta bateria com a transcrição ao vivo, e o quanto ele erra em português.
Se a transcrição ao vivo pesar, o Cérebro pode pedir menos vezes (é uma decisão do lado Python, não do plugin).

## Bluetooth LE (carrinho) — v1.14, NÃO COMPILADO nem testado num aparelho
`ble.enviar` fala com o carrinho pelo **Nordic UART**, com o MESMO nome e UUIDs do firmware (`Zenith_Carrinho`, serviço
`6E400001-…`, escrita `6E400002-…` — um teste confere que Kotlin e firmware não se separem). Procura o dispositivo pelo nome
(sem ligar para maiúsculas, hífen, sublinhado ou espaço), conecta, escreve em pedaços de 20 bytes e **mantém a conexão** para os
próximos comandos. Pede as permissões `BLUETOOTH_SCAN` e `BLUETOOTH_CONNECT` (o Android pede uma por vez: concedeu uma, peça o
comando de novo). No Cérebro, o carrinho usa Wi-Fi primeiro e, no celular, o Bluetooth no lugar do cabo USB.

## Baixador do modelo de fala — v1.14, NÃO COMPILADO nem testado num aparelho
`modelo.baixar` baixa o zip, confere o SHA-256 (se informado), descompacta com proteção contra caminhos maliciosos no zip, confere
que tem `am` e `conf` e instala em `modelos/vosk-pt`. Progresso e fim saem como eventos (`modelo.progresso`, `modelo.pronto`,
`modelo.erro`); a tela **Configurações → Voz → "Entender a fala (sem internet)"** mostra a barra e o botão. **Confira a URL**
(`URL_MODELO_PADRAO` no Kotlin: página oficial do Vosk, nome do arquivo visto como `vosk-model-small-pt-0.3.zip`): ela pode ter
mudado, e eu não consegui baixar de verdade daqui.

## Como compilar e ligar (plugin v2 do Godot 4.2+; o formato `.gdap` antigo está obsoleto)
Pré-requisitos (só você): **JDK 17** e o **Android SDK**, ou o **Android Studio** (ele traz os dois).
1. Abra a pasta `android_plugin/` no Android Studio (ou use o Gradle de linha de comando; o *wrapper* `gradlew` **não vem no
   pacote**: gere com `gradle wrapper` ou deixe o Android Studio criar).
2. Rode a tarefa **`copiarAAR`** (`./gradlew copiarAAR`). Ela compila e copia `ZenithAndroid-debug.aar` e
   `ZenithAndroid-release.aar` para `body/zenith/addons/zenith_android/bin/debug` e `.../release`.
3. No Godot: *Projeto → Instalar Modelo de Compilação do Android* (build com Gradle) e, em *Configurações do Editor → Exportar →
   Android*, aponte o JDK e o SDK. O addon **Zenith Android** já vem ligado no `project.godot` (confira em *Projeto →
   Configurações do Projeto → Plugins*): ele é quem diz ao Godot qual AAR empacotar e quais dependências baixar.
4. O preset **Android** já existe (em pé, ARM64, permissões de internet, microfone e notificações). Exporte o APK.
5. **Versões que eu escolhi e NÃO verifiquei juntas:** Android Gradle Plugin 8.7.3, Kotlin 2.0.21, compileSdk 35, minSdk 24,
   `org.godotengine:godot:4.7.1.stable` (tem de ser IGUAL à do editor e existir na Maven Central), Vosk 0.3.75, androidx.core
   1.13.1. Se o Android Studio reclamar, use as versões que ele sugerir e mantenha `voskVersion`/`androidxCore` do
   `build.gradle.kts` iguais às constantes de `addons/zenith_android/plugin.gd`.
6. **O primeiro build quase certamente dará erro** (nunca foi compilado). Cole aqui a primeira mensagem.

## Limites que você vai encontrar
- `tts.sintetizar` escreve o arquivo no caminho que o Cérebro mandou; o Python precisa **ler esse mesmo caminho**.
  Com o Python **dentro do app**, é a pasta de dados do app (funciona). Com o **Termux** (outro app), as pastas são
  separadas — o arquivo não é compartilhado, então a voz não funciona no teste de Termux.
- `emitSignal` de uma thread de fundo (microfone, TTS) é o ponto mais incerto da integração com o Godot.
