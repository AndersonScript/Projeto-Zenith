# 🌟 Atualizações do Projeto Zenith

> **Documento Oficial de Novidades e Aprimoramentos**  
> *Versão:* **Zenith 1.0 / 1.1**  
> *Autor:* **Anderson**  
> *Repositório:* [github.com/AndersonScript/Projeto-Zenith](https://github.com/AndersonScript/Projeto-Zenith)  
> *Site Oficial:* [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app)

---

## 📱 1. Versão Celular Android (`Zenith.apk`) 100% Autônoma

A versão para celulares e tablets Android agora roda **totalmente no aparelho**, sem necessidade de nenhum computador ligado ou programas externos!

### ✨ Principais Melhorias no Celular:
* **Interface Perfeita para a Tela do Celular (Correção de Escala):**
  * Corrigida a compatibilidade de resolução lógica do canvas do Godot. A interface não é mais empurrada para fora da tela nem cortada nas laterais em aparelhos com telas compridas (como 20:9 e 21:9).
  * Todos os botões receberam áreas de toque confortáveis (mínimo de 44 px) para facilitar o uso com os dedos.
* **Janelinha da VRM (Picture-in-Picture) Redimensionável:**
  * O avatar 3D pode ser ajustado facilmente com os novos botões **`➖`** e **`➕`** na barra superior, permitindo escolher o quanto da tela você quer dedicar ao avatar e ao chat (de 22% a 65%).
* **Alternância Rápida de Enquadramento:**
  * Botão de visualização com um toque para alternar entre:
    * **`👤 Busto`**: Foco no rosto e expressões faciais da Zenith.
    * **`🔲 Médio`**: Visão da cintura para cima, ideal para conversas gesticuladas.
    * **`🧍 Todo`**: Visão de corpo inteiro dos pés à cabeça.
* **Modo Maximizar Corpo Todo (`⛶ Maximizar`):**
  * Ao tocar em **`⛶ Maximizar`**, o avatar ocupa a tela inteira em destaque, com a câmera enquadrando o corpo todo com folga para saltos e mortais.
  * No topo da tela permanece a **Barra de Atividade em Tempo Real** mostrando exatamente o que a Zenith está fazendo (pesquisando, pensando, falando) com botões rápidos de **`⏹ Parar`**, microfone e restauração do chat.
* **Suporte Completo ao Modo Paisagem (Virar o Celular de Lado):**
  * Ao girar o celular, a tela se divide automaticamente de forma equilibrada: o avatar 3D fica posicionado na metade esquerda com enquadramento centrado, e o chat na metade direita, sem que nenhum botão fique espremido ou cortado.
* **Segurança e Isolamento Local:**
  * As chaves de API das IAs no celular ficam guardadas com criptografia de ponta (`user://chaves_local.bin`), utilizando chave derivada do hardware do próprio aparelho (`OS.get_unique_id()`). Nada sai do seu celular sem sua autorização.
* **Pesquisa Web Integrada Direto no Aparelho:**
  * Pesquisa nativa via DuckDuckGo sem depender de servidores intermediários, permitindo à Zenith buscar notícias e informações na web pelo próprio celular.

---

## 🤸 2. Movimentos e Acrobacias Sem Limitações

A Zenith agora possui liberdade total de movimentação corporal em 3D, tanto no computador quanto no celular!

* **Sem Trava de Altura ou Giros:**
  * O limite de salto vertical foi expandido para até **4.5 metros** de altura e rotações completas de **720°**.
* **Compensação Dinâmica de Centro de Massa:**
  * Implementado cálculo de pivô dinâmico no centro de massa (altura da cintura/quadril) no motor 3D. Quando a Zenith realiza mortais ou estrelas, o corpo gira realisticamente pelo centro no ar, sem quebrar as articulações e sem afundar no chão.
* **Biblioteca de Movimentos Prontos Embutidos:**
  * **`mortal`**: Mortal para trás clássico (backflip) com arco completo de 360°.
  * **`mortal_frente`**: Mortal frontal com rotação invertida.
  * **`estrela`**: Estrelinha acrobática lateral completa (cartwheel).
  * **`pulo_alto`**: Salto vertical acrobático de grande alcance.
  * **`pulo_duplo`**: Sequência de dois saltos consecutivos.
  * **`dancar`**: Dança rítmica com movimentação de braços e tronco.
  * **`girar`**: Giro de corpo inteiro com celebração.
  * **`reverencia`**: Inclinação cortês e graciosa.
  * **`careta`**: Expressão divertida e descontraída.
  * **`aceno_grande`**: Aceno alegre e visível de boas-vindas.
* **Criação Livre de Movimentos pela IA:**
  * Qualquer modelo de IA conectado agora pode criar novas acrobacias inéditas em tempo real enviando tags `<criar_movimento>{...}</criar_movimento>` com quadros de animação salvos localmente.

---

## 🔍 3. Correção da Pesquisa Web e Status em Tempo Real

* **Fim do Falso "Terminou Antes da Hora":**
  * Corrigida a sincronização de estado entre o Cérebro e a interface visual. Antes, o status da barra superior ("Pesquisando...") podia se apagar no momento em que a voz terminava de falar a frase introdutória, dando a falsa impressão de término antes da pesquisa realmente acabar.
* **Status Preciso Passo a Passo:**
  * O indicador de atividade agora reflete fielmente cada etapa do processo:
    1. `🔎 Pesquisando na web: ...` (busca nos índices de pesquisa)
    2. `⚡ Analisando resultados e escrevendo a resposta...` (síntese profunda dos dados)
    3. `🗣️ Zenith falando...` (resposta final e reprodução por voz)
    4. `🟢 Zenith pronta` (retorno ao estado ocioso)
* **Leitura Multi-Passo:**
  * Quando a resposta exige ler detalhes de links encontrados, o Cérebro continua o processamento e mantém a barra de atividade ativa até a conclusão completa.

---

## 📥 4. Como Baixar e Atualizar

* **Celular Android:**
  * Baixe o APK oficial diretamente em:  
    👉 **[Download Zenith.apk (GitHub)](https://github.com/AndersonScript/Projeto-Zenith/releases/download/v1.0/Zenith.apk)**  
    *Ou pelo site oficial:* [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app)
* **Computador (Windows):**
  * O assistente oficial e atualizador de 1 clique está disponível no site oficial ou na aba de Releases do GitHub.

---

*Projeto Zenith — Criado com carinho por Anderson.*
