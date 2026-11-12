# 🌟 Zenith — Registro Oficial de Atualizações & Melhorias

> **Projeto Zenith** — Assistente Pessoal com Avatar 3D VRM & Inteligência Artificial  
> *Criador & Diretor do Projeto:* **Anderson**  
> *Versão:* **1.19 (Android Mobile) / 1.0 (Windows PC)**  
> *Data:* **11/11/2026**  
> *Repositório GitHub:* [github.com/AndersonScript/Projeto-Zenith](https://github.com/AndersonScript/Projeto-Zenith)  
> *Site Oficial:* [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app)

---

## 📱 1. Novidades da Versão Celular Android (`Zenith.apk` v1.19)

### 🤖 1.1 Correção Definitiva da API de IA (Google Gemini & Claude)
* **Diagnóstico da Causa Raiz:** Ao inserir a chave do Google AI Studio, a IA retornava o erro:  
  `Erro: models/gemini-1.5-flash is not found for API version v1beta, or is not supported for generateContent`.  
  O Google aposentou o identificador fixo `gemini-1.5-flash` na versão `v1beta` para chaves criadas recentemente, exigindo as novas versões da família Gemini 2.x.
* **Solução com Fallback Automático e Silencioso:**
  * O Zenith agora implementa uma esteira inteligente de modelos modernos:  
    `gemini-2.5-flash` ➔ `gemini-2.0-flash` ➔ `gemini-1.5-flash-latest` ➔ `gemini-2.5-flash-lite` ➔ `gemini-2.0-flash-lite` ➔ `gemini-1.5-pro`.
  * Se o Google recusar ou retornar erro 404 em algum modelo, o aplicativo passa instantaneamente e de forma transparente para o próximo da fila, garantindo resposta imediata sem erros na tela.
  * **Suporte Nativo a Chaves Claude (Anthropic):** Inserindo qualquer chave iniciada em `sk-ant-`, o Zenith conversa diretamente com a API oficial da Anthropic utilizando o modelo ultrarrápido `claude-3-5-haiku-20241022`.

### 🪟 1.2 Janela Flutuante 3D Móvel com Fundo Transparente (PiP)
* **Zero Fundo Preto:** O avatar 3D agora é renderizado através de um `SubViewport` com canal alfa puro (`transparent_bg = true`). A Akira aparece flutuando de forma nítida, sem nenhuma caixa preta ao redor!
* **Janela Móvel Arrastável com o Dedo:**
  * No modo flutuante, o avatar fica alojado em um card com cantos arredondados, borda de vidro sutil e cabeçalho de arrasto `⋮⋮ Zenith 3D`.
  * Você pode tocar no cabeçalho e arrastar a Akira para **qualquer posição da tela** enquanto digita ou lê as respostas da IA.
  * Botão de minimizar `—` que recolhe o avatar para uma bolha discreta e botão `↺` para reposicionar instantaneamente.

### 🧍 1.3 Quatro Modos de Exibição com 1 Toque
Um único botão moderno no topo permite alternar facilmente entre os 4 estilos visuais:
1. **`📱 Flutuante`:** Chat 100% em tela cheia estilo Claude/ChatGPT com a janela 3D móvel flutuando sobre o chat.
2. **`🧍 Corpo Cheio`:** A câmera se afasta e se posiciona perfeitamente para enquadrar a Akira dos pés à cabeça, com o chat ocupando a parte inferior. Perfeito para assistir a saltos, danças e mortais completos enquanto conversa.
3. **`💬 Só Chat`:** Foco total na leitura e digitação, com o avatar recolhido em uma bolha minimalista.
4. **`🔲 No Topo`:** Visor clássico no topo da tela com divisor ajustável.

### 🔄 1.4 Giro 3D com o Dedo (Virar de Lado)
* Basta deslizar o dedo horizontalmente sobre a área do avatar 3D para virar a Akira em 360° para a esquerda ou para a direita em tempo real.
* Dê dois toques rápidos sobre o avatar para restaurar a rotação frontal automaticamente.

### 🧹 1.5 Barra de Atividades Limpa & Discreta
* O antigo banner vermelho volumoso de "Parar" foi substituído por uma barra minimalista e elegante de 26px que só fica visível enquanto a IA está gerando respostas ou pesquisando, recolhendo-se a zero pixels quando ociosa.

---

## 🤸 2. Movimentos & Acrobacias Sem Limites

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
