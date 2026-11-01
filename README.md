# Zenith

**Um assistente pessoal com avatar 3D, que roda no seu computador e só age com a sua aprovação.**

Zenith 1.0 Oficial — funciona no dia a dia do autor, mas ainda tem arestas. O que ainda não existe
está listado no fim, sem enfeite.

**Site e download:** https://projeto-zenith-five.vercel.app
**Última versão:** https://github.com/AndersonScript/Projeto-Zenith/releases/latest

---

## O que ele faz

- **Conversa** com a IA que você escolher (Gemini, OpenAI, Claude, Groq e outras), por voz ou texto,
  com um avatar 3D em formato VRM na tela.
- **Programa com você**: escreve, mostra o código antes e roda quando você aprova — e devolve o que o
  programa imprimiu.
- **Cria e edita**: imagens, vídeos (cortar, juntar, legendar, narrar) e documentos.
- **Organiza o computador**: arruma pastas, lê documentos e planilhas que você anexa.
- **Enxerga quando você deixa**: tela e câmera, com aviso visível e botão de parar.
- **Fala com o carrinho**: ESP32-S3 com tela TFT (rosto) e Arduino Uno nos motores — por Wi-Fi,
  Bluetooth ou cabo. O firmware está dentro do pacote de instalação (`firmware/`).

## As regras que não mudam

1. **Nada roda sem a sua aprovação.** Código, comandos, abrir programas, ver a tela: tudo passa por
   uma janela de confirmação.
2. **Existe uma lista do que ele nunca faz**, nem com aprovação (apagar disco, desligar o PC, mexer em
   antivírus e firewall).
3. **Suas chaves, conversas e memória ficam no seu computador.** Não há telemetria.
4. **Sem pegadinha**: o código do programa vai dentro do pacote, para você ler.

## Instalar (Windows 10/11, 64 bits)

1. Baixe o **`ZenithLauncher.exe`** na página de releases (ou pelo site).
2. Confira o **SHA-256** publicado em `SHA256_HASHES.txt`, na mesma release:
   no Windows, `certutil -hashfile ZenithLauncher.exe SHA256`.
3. Abra o instalador. Ele mostra **onde vai instalar** e **onde guardar suas criações**.
   Não precisa ser administrador.
4. Na primeira vez, o Zenith pede o seu nome e uma chave de IA.

> O instalador ainda **não tem assinatura digital**, então o Windows pode mostrar
> "O Windows protegeu o seu PC". É por isso que o SHA-256 é publicado junto.

## O que tem neste repositório

Este repositório é a parte de **distribuição**, não o código-fonte completo:

| Pasta | O que é |
|---|---|
| `site/` | a página publicada no Vercel (`index.html`, `latest.json`) |
| `launcher/` | o código do instalador (`ZenithLauncher.exe`) e do `LimparZenith.exe` |
| `dist_launcher/` | os dois `.exe` já compilados |

O programa completo (Cérebro em Python, Corpo em Godot, firmware do carrinho, testes e documentação)
vai dentro do pacote da release, `Zenith_app_1.0.zip`.

## O que ainda não existe

Microfone com texto aparecendo enquanto você fala no estilo do Word, biblioteca de cadernos,
aplicativo Android, versão completa para ESP32 sem o Arduino e CLP.
Geração de vídeo por IA: hoje o Zenith **edita** vídeo, não o **gera** do zero.

## Licença

O código do Zenith é MIT. Godot, o addon VRM, as bibliotecas Python e as fontes mantêm as próprias
licenças. Os modelos de IA e os serviços que você conectar seguem os termos deles.
