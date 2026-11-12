# 🌟 Zenith — Registro Oficial de Atualizações & Melhorias

> **Projeto Zenith** — Assistente Pessoal com Avatar 3D VRM & Inteligência Artificial  
> *Criador & Diretor do Projeto:* **Anderson**  
> *Versão:* **1.21 (Android Mobile) / 1.0 (Windows PC)**  
> *Data:* **12/11/2026**  
> *Repositório GitHub:* [github.com/AndersonScript/Projeto-Zenith](https://github.com/AndersonScript/Projeto-Zenith)  
> *Site Oficial:* [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app)

---

## 🎭 1. Correção Crítica do Avatar no APK Android (Expressões Faciais, Sincronização Labial & Movimentos Acrobáticos)

Com base no relato do Anderson (*"descobri uma coisa na versão APK ela não muda nem o rosto e nem se movimenta"*), investigamos a fundo o ciclo de renderização e animação do avatar no APK e corrigimos 5 causas raízes:

1. **Desacoplamento do Prefixo de Estado (`state_speaking` vs `state:speaking`):**
   * O conector emitia `"state_speaking"` e `"state_idle"` com underline, enquanto o corpo 3D aguardava `"state:"` com dois-pontos. Isso impedia o avatar de transitar para o estado `SPEAKING` ou `THINKING`.
   * **Correção:** O avatar agora reconhece todos os formatos (`state_speaking`, `state:speaking`, `speaking`, `state_thinking`, `state_idle`).
2. **Sincronização Labial (Visemes) e Gesticulação ao Falar:**
   * Com o estado `SPEAKING` ativo, o motor `akira_vida.gd` agora movimenta a boca continuamente (visemes `aa`, `ih`, `ou`, `ee`, `oh`) em tempo real enquanto fala por voz ou texto, move o braço gesticulando e acena a cabeça ritmicamente.
3. **Expressões Faciais Vivas e Ricas em Blend Shapes:**
   * Aumentada a força expressiva (`_emotion_strength = 0.75`), integrados os blend shapes VRoid (`Fcl_ALL_Joy`, `Fcl_ALL_Angry`, `Fcl_ALL_Sorrow`, `Fcl_ALL_Surprised`) e o conector agora seleciona expressões faciais vivas por padrão (sorriso alegre em cumprimentos, curiosidade em perguntas, calma em respostas longas).
4. **Respiração Visível e Micro-Movimentos de Ociosidade:**
   * A respiração anterior oscilava o nó raiz da cena, movendo a câmera junto e anulando o movimento relativo. Agora a respiração vertical (1.2 cm) e rotação peitoral (0.035 radianos) atuam diretamente sobre o modelo da Akira, tornando a respiração calma e visível.
   * Ativados micro-gestos naturais mesmo no modo padrão `suave` (inclinar de cabeça, concordar sutil, ajeitar postura a cada 10-20 segundos).
5. **Comandos Acrobáticos 100% Locais no Celular (Sem Chave):**
   * Pedidos como "mortal", "mortal de costas", "mortal de frente", "pula", "dança", "careta", "gira", "reverência" ou "acena" são executados imediatamente em 3D, com acrobacia completa e resposta simpática da Zenith, funcionando 100% offline mesmo sem chave de API configurada.
6. **Sincronização de Câmera e FOV no SubViewport Móvel:**
   * A câmera secundária do card flutuante móvel agora copia a posição, FOV, planos near/far e proporção de aspecto da câmera principal quadro a quadro, mantendo o enquadramento perfeito durante giros e acrobacias.

---

## 📧 2. Nova Ponte por E-mail (Celular ↔ Computador) — 100% Privada e Sem Banco de Dados
 de Dados

Atendendo à visão do Anderson de manter o projeto **100% anônimo, descentralizado e sem custos de banco de dados na nuvem**, criamos a **Ponte por E-mail**:

* **Zero Servidores Centrais e Zero Banco de Dados:** Você e os usuários não dependem de Supabase, Firebase ou servidores externos. Cada usuário conecta o celular e o computador através da sua própria conta de e-mail (Gmail, Outlook ou qualquer provedor IMAP/SMTP).
* **Anonimato e Custo Zero para o Criador:** O criador do Zenith não armazena dados de ninguém, não tem despesas de infraestrutura e não corre riscos com vazamentos de dados de terceiros.
* **Funciona em Qualquer Lugar:** Como o e-mail é uma infraestrutura global, a conexão funciona mesmo quando o usuário estiver na rua no 4G/5G, sem precisar de roteamento de portas ou Wi-Fi compartilhado.

### 🎮 O que você pode fazer pelo E-mail:
1. **Status Remoto do PC (`[Zenith] status`):**
   * O celular recebe um relatório completo do computador: uso de CPU, memória RAM, espaço livre em disco, tempo ligado e estado do Zenith.
2. **Captura de Tela Remota (`[Zenith] print` ou `screenshot`):**
   * O computador tira uma foto instantânea da tela e envia anexada por e-mail para o celular.
3. **Buscar Arquivos no PC (`[Zenith] buscar <nome>`):**
   * Procura arquivos com segurança nas pastas do usuário (Área de Trabalho, Downloads, Documentos) e devolve a lista com tamanhos e datas de modificação.
4. **Enviar Arquivos do PC para o Celular (`[Zenith] enviar <arquivo>`):**
   * O computador anexa o arquivo encontrado (até 25 MB) e envia diretamente para o e-mail do usuário.
5. **Bloquear o Computador (`[Zenith] bloquear`):**
   * Bloqueia a estação de trabalho do Windows à distância.
6. **Perguntas e Chat com o Cérebro do PC (`[Zenith] <pergunta>`):**
   * A IA do computador processa a mensagem com o histórico e as memórias locais e responde formatada em texto e HTML limpo.

### 🛡️ Trava de Segurança Antifalsificação:
* O computador **apenas executa ordens se o remetente for exatamente o e-mail do próprio dono** configurado no app. E-mails de terceiros são ignorados e descartados imediatamente.

---

## 📱 2. Versão Celular Android (`Zenith.apk` v1.20)

### 🤖 2.1 Correção Definitiva da API de IA (Google Gemini & Claude)
* **Fallback Automático e Silencioso:** Esteira inteligente com modelos modernos (`gemini-2.5-flash` ➔ `gemini-2.0-flash` ➔ `gemini-1.5-flash-latest` ➔ `gemini-2.5-flash-lite` ➔ `gemini-2.0-flash-lite` ➔ `gemini-1.5-pro`). Se o Google recusar ou aposentar algum modelo, o app tenta o próximo instantaneamente sem exibir erro na tela.
* **Suporte a Chaves Claude:** Aceita chaves `sk-ant-` diretamente com o modelo `claude-3-5-haiku-20241022`.

### 🪟 2.2 Janela Flutuante 3D Móvel com Fundo Transparente (PiP)
* **Zero Fundo Preto:** Renderização com canal alfa puro (`transparent_bg = true`).
* **Arrastável pelo Toque:** Mova a Akira para qualquer lugar da tela com o dedo pelo cabeçalho `⋮⋮ Zenith 3D`. Botão de minimizar `—` em bolha discreta e `↺` para reposicionar.

### 🧍 2.3 Quatro Modos de Exibição com 1 Toque
1. **`📱 Flutuante`:** Chat 100% tela cheia estilo Claude com a janela 3D móvel flutuando.
2. **`🧍 Corpo Cheio`:** Câmera recuada enquadrando da cabeça aos pés para ver acrobacias e saltos completos enquanto conversa.
3. **`💬 Só Chat`:** Foco total no texto, avatar recolhido.
4. **`🔲 No Topo`:** Visor clássico superior.

### 🔄 2.4 Giro 3D com o Dedo
* Arraste o dedo na horizontal para girar o avatar 3D em 360°. Toque duplo restaura o ângulo frontal.

---

## 💻 3. Versão Desktop PC (Windows)

* **Nova Aba "Ponte E-mail":** Configuração direta de e-mail e senha de aplicativo, teste de conexão IMAP/SMTP em tempo real e chave de ativação do monitoramento.
* **Launcher com Escolha Livre de Pastas:** Instalador/launcher permite escolher onde instalar o Zenith e onde salvar dados e projetos.
* **Transparência DWM e Modo Invisível:** Execução em janela flutuante com fundo transparente no Windows.

---

## 📦 4. Onde Baixar e Arquivos Atualizados

* **📱 Android:** Baixe o arquivo **`Zenith.apk`** diretamente na pasta **Downloads** do seu computador ([Zenith.apk](file:///C:/Users/ander/Downloads/Zenith.apk)), ou pela aba [Releases do GitHub](https://github.com/AndersonScript/Projeto-Zenith/releases/download/v1.0/Zenith.apk).
* **💻 Windows:** Baixe o **`ZenithLauncher.exe`** ou o pacote completo pelo site oficial: [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app).
