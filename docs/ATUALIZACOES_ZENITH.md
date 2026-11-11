# 🌟 Zenith — Registro Oficial de Atualizações & Melhorias

> **Projeto Zenith** — Assistente Pessoal com Avatar 3D VRM & Inteligência Artificial  
> *Criador & Diretor do Projeto:* **Anderson**  
> *Versão:* **1.18 (Android Mobile) / 1.0 (Windows PC)**  
> *Data:* **10/11/2026**  
> *Repositório GitHub:* [github.com/AndersonScript/Projeto-Zenith](https://github.com/AndersonScript/Projeto-Zenith)  
> *Site Oficial:* [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app)

---

## 📱 1. Versão Celular Android (`Zenith.apk`) 100% Autônoma

A versão de celular agora roda **100% no aparelho**, sem depender do computador estar ligado! Todas as correções críticas de abertura, estabilidade e visual foram resolvidas e verificadas:

### 🛠️ Correção do Fechamento Involuntário (Crash na Abertura)
* **Diagnóstico da Causa Raiz:** Ao abrir o app no modo celular standalone, uma chamada recursiva síncrona infinita ocorria entre o carregamento da lista de conversas (`_emitir_conversas_mobile`) e o manipulador de interface (`_on_conversation_loaded`), estourando a pilha de execução do Godot (Stack Overflow após 1024 chamadas em milissegundos). Além disso, havia um erro de sintaxe de escopo em constantes de layout.
* **Solução Definitiva:** Adicionadas travas de segurança atômicas (`_emitindo_conversas` e `_conversa_inicial_carregada`), carregamento postergado e resolução das variáveis de tela. O aplicativo agora inicializa instantaneamente e com estabilidade máxima, sem travar nem fechar!

### 🎨 Visual & Enquadramento Impecável (Estilo Claude)
* **Barra Superior Limpa & Arejada:** Baseada no design minimalista e moderno do aplicativo Claude:
  * Botão de menu lateral **`☰`** na esquerda com acesso rápido a conversas e configurações.
  * Título **Zenith** amplo, nítido e centralizado — sem cortes ou textos espremidos ("Con...").
  * Botões de controle de avatar compactos e elegantes com cantos arredondados:
    * **`👤 Busto`**: Foco no rosto e nas expressões faciais detalhadas.
    * **`🔲 Médio`**: Visão da cintura para cima, ideal para conversas com gestos naturais.
    * **`🧍 Todo`**: Visão completa da cabeça aos pés.
    * **`⛶`**: Maximizar avatar em tela cheia para ver acrobacias e danças.
* **Pílula de Digitação no Rodapé:**
  * Caixa de texto arredondada estilo pílula moderna com botões de microfone e envio integrados.
  * Margem de segurança inferior garantida (14-16 px) para nunca ficar colada ou encoberta pela barra de navegação/gestos do Android.
* **Suporte Completo ao Modo Paisagem (Celular Deitado):**
  * Divisão harmoniosa automática: avatar 3D à esquerda e chat à direita, sem sobreposição de controles.

### 🖼️ Geração Gratuita de Imagens no Celular
* **Comando `/imagem` Standalone:** Agora você pode pedir `/imagem <descrição>` ou "desenhe um astronauta na lua" diretamente no celular. A Zenith gera e exibe a imagem em alta resolução via Pollinations sem custos e sem requerer chaves de API pagas.

---

## 🤸 2. Movimentos e Acrobacias Sem Limites

Tanto no computador quanto no celular Android, o avatar 3D conta com física de movimentos acrobáticos completa:
* **Mortais:** Mortais para trás e mortais para frente acionados por voz ou texto ("dê um mortal", "mortal de frente").
* **Saltos:** Pulo normal, pulo alto e salto duplo.
* **Acrobacias & Dança:** Estrela/estrelinha lateral, giro 360°, dança, reverência e careta expressiva.
* **Sem Bloqueios de Câmera:** Os limites rígidos de altura de salto foram removidos para permitir acrobacias aéreas completas.

---

## 💻 3. Versão Desktop PC (Windows)

* **Launcher com Escolha Livre de Pastas:** O instalador/launcher permite ao usuário escolher onde instalar o Zenith e onde salvar os arquivos e projetos (ex: Drive C:, D: ou Pendrive).
* **Compatibilidade e Modo Headless:** Execução em modo invisível ou em janela flutuante com suporte a transparência de fundo (DWM).
* **Chaves de IA e Modelos:** Suporte nativo a Gemini (Google), Groq, OpenAI, Anthropic Claude e modelos locais.

---

## 📦 4. Como Baixar e Instalar

* **📱 Android:** Baixe o arquivo **`Zenith.apk`** diretamente na pasta **Downloads** do seu computador ou celular, ou baixe pela aba [Releases do GitHub](https://github.com/AndersonScript/Projeto-Zenith/releases/download/v1.0/Zenith.apk). Basta tocar e instalar.
* **💻 Windows:** Baixe o **`ZenithLauncher.exe`** ou o pacote completo pelo site oficial: [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app).
