# Bibliotecas do Cérebro no Android (v1.19)

**Isto é um MAPA do que o código importa. Nada aqui foi conferido num aparelho.** A coluna "No celular" mistura o que o Cérebro
já NÃO usa lá (porque o Android entrega pela ponte) com o que eu apenas SUSPEITO sobre código nativo. Quem decide é a
**Prova 4** (Python dentro do APK) e a **Prova 2** (Cérebro no Termux): tente instalar cada "CONFERIR" e me conte o resultado.

Gerado lendo `brain/` e `skills/`; o teste `tests/test_port_celular_v19.py` quebra se aparecer biblioteca nova que não esteja aqui.

## 1. O Cérebro EXIGE estas na partida (sem elas ele nem abre)

| Biblioteca | Importada em | Natureza | No celular |
|---|---|---|---|
| `PIL` | zenith_img | Pillow: tem código nativo | CONFERIR se há versão para Android |
| `google` | zenith_core | é o pacote `google-genai` (usa pydantic e httpx) | CONFERIR se há versão para Android |
| `openai` | zenith_core | usa pydantic (parte nativa em Rust) | CONFERIR se há versão para Android |
| `requests` | zenith_executor | Python puro | provável que instale; confirmar |
| `websockets` | zenith_bridge | Python puro (tem aceleração nativa opcional) | provável que instale; confirmar |

Se uma delas não existir no Android, o primeiro passo é decidir: achar uma versão para Android, ou trocar por outra coisa.
`Pillow` e `numpy` são as mais prováveis de dar trabalho (código nativo).

## 2. Todas as outras (se faltarem, só a função que as usa para)

| Biblioteca | Quem usa | Natureza | No celular |
|---|---|---|---|
| `PyPDF2` | zenith_anexos | Python puro | provável que instale; sem ela o PDF vira uma frase |
| `av` | zenith_rvc | áudio/vídeo do RVC | NÃO existirá no celular |
| `chromadb` | zenith_memory | PC: banco de vetores pesado | NÃO usa: o celular usa a memória leve em SQLite (zenith_memoria_leve) |
| `customtkinter` | zenith_ui, zenith_widgets | janela antiga do PC | NÃO existe no celular: o Corpo (Godot) a substitui |
| `cv2` | zenith_anexos, zenith_fundo, zenith_vision | OpenCV: nativa e grande | NÃO precisa: câmera e vídeo vêm do Android (camera.capturar, video.*) |
| `edge_tts` | zenith_diag, zenith_interaction | Python puro + aiohttp | provável que instale; confirmar |
| `faster_whisper` | zenith_interaction | Whisper no PC | NÃO usa: no celular a fala vira texto no Vosk (stt.transcrever) |
| `google.genai` | zenith_imagem_ia | é o pacote `google-genai` (usa pydantic e httpx) | CONFERIR se há versão para Android |
| `imageio_ffmpeg` | zenith_video | ffmpeg embutido (edição de vídeo) | NÃO existirá no celular (edição pesada de vídeo) |
| `matplotlib` | zenith_formulas, zenith_matematica, zenith_video | tem código nativo, pesada | provavelmente fora do celular (gráficos de fórmulas/vídeo) |
| `mss` | zenith_vision | captura de tela do PC | NÃO usa: vem do Android (tela.capturar) |
| `numpy` | zenith_img, zenith_interaction, zenith_rvc | tem código nativo | CONFERIR se há versão para Android |
| `plyer` | zenith_notify | notificação do PC | NÃO usa: vem do Android (notificacao.mostrar) |
| `pygame` | zenith_diag, zenith_interaction | áudio do PC | NÃO usa: vem do Android (audio.*) |
| `pypdf` | zenith_anexos | Python puro | provável que instale; sem ela o PDF vira uma frase |
| `rvc_python` | zenith_interaction | clonagem de voz (RVC) | NÃO existirá no celular |
| `serial` | carrinho, zenith_commands, zenith_hardware, zenith_tft | pyserial (cabo USB) | NÃO usa: o carrinho vai por Bluetooth (ble.enviar) ou Wi-Fi |
| `sounddevice` | zenith_diag, zenith_interaction | microfone do PC | NÃO usa: vem do Android (mic.*) |
| `sympy` | zenith_formulas | Python puro, grande | opcional (fórmulas) |
| `vosk` | zenith_ditado | PC: ditado | NÃO usa: no celular o Vosk vai dentro do plugin Kotlin |

## 3. Como conferir de verdade (você, no aparelho)

1. No Termux (Prova 2): `pkg install python`, depois tente `pip install websockets requests openai google-genai pillow` e anote qual falha.
2. No Chaquopy/APK (Prova 4): coloque as da seção 1 no `build.gradle` e veja quais o Gradle recusa.
3. Com as da seção 1 instaladas, rode `python -m unittest tests.test_importa_no_celular` e depois o Cérebro.
