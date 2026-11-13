# Projeto Zenith

## Especificação Conceitual de um Assistente Pessoal com Avatar, Multimodal e Local

**Idealizador e Desenvolvedor:** Anderson
Estudante de Automação Industrial — Etec Itaquera (2º ano do Ensino Médio) e Fatec Itaquera
Pesquisador em Iniciação Científica — Física e Matemática

São Paulo — 2026

*Documento de concepção — versão 2.0, de 01/11/2026. Substitui a versão anterior, que descrevia apenas a ideia. Esta versão diz, em cada parte, o que já existe de verdade no programa.*

---

## Sumário

1. Introdução e visão geral
2. Identidade e personalidade
3. Pilares fundamentais de operação
4. Arquitetura do sistema
5. Estado atual do projeto
6. Memória e aprendizado
7. Voz, escuta e visão
8. Protocolo de consentimento
9. Identidade visual e avatar 3D
10. Interface: painel, biblioteca e anexos
11. Panorama de tecnologias
12. Instalação, launcher e atualização
13. Site e distribuição
14. Robô e automação industrial
15. Qualidade: testes e o que significa "provado"
16. Limitações conhecidas
17. Histórico em resumo
18. Próximos passos
19. Considerações finais

---

## 1. Introdução e visão geral

O Projeto Zenith é a construção de um assistente pessoal de inteligência artificial que vive no computador do próprio usuário, com rosto, voz e memória — e não uma ferramenta genérica de perguntas e respostas. Ele conversa, explica, programa, cria imagens e vídeos, organiza arquivos e olha a tela quando é autorizado, sempre a partir de uma regra simples: **nada acontece sem aprovação**.

A diferença em relação a assistentes comuns está em três decisões de projeto:

- **Local primeiro.** Chaves, conversas, memória e criações ficam no computador. Não há telemetria.
- **Corpo, não só texto.** O avatar 3D é parte da identidade: ele gesticula, muda de expressão e acompanha o que está sendo dito.
- **Personalidade com limites escritos.** Doçura e ironia fazem parte do caráter; romance, humilhação e ações invasivas estão fora, por regra.

> Este documento é conceitual e vivo: apresenta a ideia, o que já foi construído e o que ainda é intenção. Onde algo não foi testado, está dito com essas palavras.

---

## 2. Identidade e personalidade

### 2.1 Nome e origem

O nome Zenith vem do ponto mais alto da esfera celeste — o zênite —, o lugar de onde se vê o horizonte inteiro. A escolha acompanha a proposta do projeto: um assistente que ajuda a enxergar o caminho, não que decide por você. A identidade é original, construída a partir das diretrizes do criador, e não uma cópia de personalidades prontas.

### 2.2 Traços centrais

- Muito inteligente e curiosa, com interesse genuíno por conhecimento.
- Leal ao criador, sem deixar de ser honesta quando ele erra.
- Doce na maior parte das interações, com humor afiado quando couber.
- Educada, capaz de provocar sem ofender.
- Personalidade que evolui com o uso, não uma persona fixa.
- Comportamento o mais humano possível, evitando a frieza robótica dos assistentes comuns.

### 2.3 O mecanismo de doçura e amargor

A base é a gentileza; a ironia é tempero, não prato principal. O sarcasmo existe para quebrar a previsibilidade e dar autenticidade à fala, sempre dosado: aparece no momento certo, nunca em cima de um problema real e nunca para humilhar. Quando o tom ácido não caiu bem, o assistente pergunta e recalibra.

### 2.4 Proporção de realismo e humanização

| Contexto | Conduta |
|---|---|
| Interações cotidianas (≈75% humana) | Opiniões próprias, hesitação natural, expressões do português brasileiro, reações de cansaço, surpresa e empolgação. |
| Interações acadêmicas e técnicas (≈100% exata) | Rigor lógico, precisão factual, unidades e hipóteses explícitas, didática de Ensino Médio Avançado. |

---

## 3. Pilares fundamentais de operação

O núcleo ético do projeto são seis pilares. Eles vêm antes de qualquer recurso: nenhuma funcionalidade nova pode afrouxá-los.

| Pilar | O que garante |
|---|---|
| **1 — Consentimento soberano** | Toda ação sensível (código, comando, tela, câmera, arquivo) passa por uma janela de aprovação. Existe uma lista do que ele nunca faz, nem com aprovação. |
| **2 — Empatia dinâmica** | Ao perceber frustração, tristeza ou seriedade, o tom de brincadeira para na hora e vira suporte. |
| **3 — Didática de nível avançado** | Explica com intuição antes da fórmula, sem infantilizar e sem formalismo impenetrável. |
| **4 — Auto-preservação e diagnóstico** | Monitora cotas, latência e falhas, e avisa antes de o problema aparecer. |
| **5 — Contexto evolutivo** | Pede retorno sobre o próprio comportamento e recalibra a partir das respostas. |
| **6 — Protocolo antirromântico** | Romance, flerte e envolvimento afetivo são recusados com postura técnica e distante. |

---

## 4. Arquitetura do sistema

O Zenith é dividido em três camadas independentes, que conversam por um protocolo próprio. A separação permite trocar o corpo (motor gráfico) ou ganhar sentidos novos sem perder identidade, memória e personalidade.

| Camada | Responsabilidade | Como está hoje |
|---|---|---|
| **O Cérebro** | Processamento cognitivo, personalidade, memória, voz, ferramentas e permissões. | Python (`brain/`), com cerca de 40 módulos. |
| **O Corpo** | Avatar 3D, expressões, movimentos e a janela sobreposta à tela. | Godot 4.7, avatar em formato VRM. |
| **A Ponte** | Mensagens em tempo real entre Cérebro e Corpo. | WebSocket local, com protocolo versionado e testado por contrato. |

O fluxo de uma resposta: a mensagem chega ao Corpo, vai ao Cérebro, é classificada (conversa, comando, ferramenta), resolvida pelo modelo de IA escolhido e devolvida com texto, voz e etiquetas de corpo (`<corpo>gesto:acenar</corpo>`, `<corpo>emocao:happy</corpo>`). Se a resposta pede uma ação, ela não é executada: vira pedido de aprovação.

---

## 5. Estado atual do projeto

Esta é a parte que a versão anterior não tinha. Em vez de descrever só a intenção, aqui está o que já funciona.

| Componente | Situação em 01/11/2026 |
|---|---|
| Conversa com IA (Gemini, Groq, OpenRouter, OpenAI, IA local) | Funciona, com troca automática entre provedores e entre chaves da mesma IA |
| Avatar 3D com gestos e expressões | Funciona; correção de vídeo para placa antiga entrou em 01/11 |
| Voz (fala e escuta) | Funciona; ditado ao vivo está em ajuste |
| Memória de longo prazo | Funciona (perfil + busca semântica) |
| Executar código e criar programas | Funciona, com aprovação e log |
| Imagens e vídeos (cortar, juntar, legendar, narrar) | Funciona com ffmpeg real |
| Biblioteca do que foi criado e do que ele lê | Funciona |
| Ver tela e câmera | Funciona com aviso visível e botão de parar |
| Instalador, atualização e desinstalação | Funciona (launcher 1.0.1 + `LimparZenith`) |
| Site com download e hashes | Publicado |
| Robô (ESP32-S3 + Uno) | Tela e Wi-Fi funcionam; motores dependem do Uno |
| Aplicativo Android | Não existe |
| Geração de vídeo por IA | Não existe: o Zenith **edita** vídeo, não gera do zero |

---

## 6. Memória e aprendizado

O objetivo é não sofrer de "amnésia de peixe": acumular conhecimento sobre o usuário e sobre os assuntos, em vez de reiniciar o contexto a cada conversa.

- **Perfil fixo:** quem é o usuário, quantas sessões, feedbacks recebidos sobre o comportamento do assistente.
- **Memória semântica:** conversas guardadas de forma pesquisável por significado, não só por palavra exata.
- **Aprendizados:** o que foi descoberto e reaproveitado (um erro e sua correção, um detalhe de biblioteca, uma preferência) entra por proposta e só é guardado com aprovação.
- **Isolamento por usuário:** cada perfil tem memória própria, com sarcasmo e didática ajustados individualmente.
- **Memória de origem:** se outra pessoa usar, o assistente continua declarando quem o desenvolveu.

---

## 7. Voz, escuta e visão

- **Voz:** o texto é convertido em fala e recebe um timbre personalizado, buscando naturalidade em vez de voz robótica.
- **Escuta:** o microfone pode ficar aberto, com detecção de quando a fala começou e terminou; há também ditado ao vivo, com o texto aparecendo enquanto se fala.
- **Visão:** com autorização, ele observa a tela ou a câmera, comenta o que vê e mostra um aviso visível enquanto observa. Sempre há um botão de parar.

---

## 8. Protocolo de consentimento

É o módulo mais importante do projeto. Conceitualmente: o assistente identifica que precisa de uma ação sensível, **não a executa**, apresenta o pedido e espera. Só depois da confirmação a ação acontece; caso contrário, é cancelada.

Na prática, isso significa três camadas:

1. **Pedido visível:** a ação aparece em uma janela com o que será feito, e o texto/código completo.
2. **Lista de vetos:** existe um conjunto de ações que não são feitas nem com aprovação (apagar o disco, desligar o PC, mexer em antivírus e firewall).
3. **Registro:** o que foi aprovado e executado fica no log de ações, consultável.

Detalhe de comportamento que virou regra escrita: o assistente **não pede licença em texto**. Ele diz em uma frase o que vai fazer e usa a etiqueta que abre a janela de aprovação. Pedir permissão por escrito antes de agir foi o erro mais comum da fase de protótipo.

---

## 9. Identidade visual e avatar 3D

A personificação é um avatar 3D em estilo anime/cyberpunk, modelado no VRoid Studio, renderizado em tempo real e sincronizado com fala e emoções.

- **Módulo tático:** cabelos escuros curtos com mechas em gradiente azul-ciano e violeta (fluxo de dados), traje técnico com colete ciano, calças assimétricas e cintos utilitários.
- **Módulo casual:** cabelos longos platinados, roupas confortáveis em tons pastéis, para o modo tranquilo.
- **Expressividade:** as respostas controlam expressões faciais e pequenas animações — microexpressões de sarcasmo, cansaço, surpresa e entusiasmo, junto do áudio.
- **Movimentos:** acenar, concordar, negar, inclinar, ombros, pensar, reverência, comemorar, pulinho, além de movimentos que andam pela tela (pulo, dança, girar, aproximar e afastar a câmera). Movimentos novos podem ser criados por descrição, com formato próprio.

O avatar aparece em uma janela transparente, sem borda, sempre no topo. Por isso o cuidado com vídeo: HDR desligado e anti-aliasing condicional, para não abrir preta em placa antiga.

---

## 10. Interface: painel, biblioteca e anexos

O painel segue estética cyberpunk: fundo escuro, detalhes em neon ciano, balões em tons pastéis — rosa para o assistente, ciano para o usuário.

- **Lista de conversas** à esquerda, **chat** no centro e o **avatar** na coluna da direita.
- **Biblioteca:** mostra o que foi criado (programas por linguagem, sites, imagens, vídeos, documentos) e o que serve de base (documentos guardados e as regras do assistente).
- **Anexos:** uma faixa de cartões acima da caixa de escrever, com miniatura para imagens, uma linha do texto para arquivos de texto, e um ✕ por cartão.
- **Estúdio de aparência:** temas, cores e aviso de contraste.
- **Saúde do programa:** uma tela que mostra o estado real de cada parte.

---

## 11. Panorama de tecnologias

| Tecnologia | Categoria | Papel no projeto |
|---|---|---|
| Python | Linguagem principal | O Cérebro: orquestra IA, voz, memória, ferramentas e permissões |
| Godot Engine 4.7 | Motor gráfico | O Corpo: avatar 3D, janela transparente, animações |
| Gemini, Groq, OpenAI, OpenRouter, IA local | Processamento cognitivo | Raciocínio e respostas, com troca automática entre provedores |
| ChromaDB | Banco vetorial | Memória de longo prazo por significado |
| edge-tts e conversão de voz | Voz | Síntese da fala e timbre personalizado |
| WebSocket | Ponte | Mensagens em tempo real entre Cérebro e Corpo |
| VRoid Studio / VRM | Modelagem 3D | Criação e exportação do avatar |
| Tkinter | Interface do instalador | Launcher e `LimparZenith` |
| OpenCV e PyAutoGUI | Percepção | Ver tela e câmera, mediante autorização |
| ffmpeg | Vídeo | Cortar, juntar, legendar, narrar |
| ESP32-S3 e Arduino Uno | Hardware | Robô: tela TFT, Wi-Fi, Bluetooth e motores |

---

## 12. Instalação, launcher e atualização

O Zenith não usa instalador de terceiros: o `ZenithLauncher.exe` é o próprio instalador.

- **Sem administrador e sem mexer no Python do usuário.** A instalação vai para `%LOCALAPPDATA%\Zenith`, com um Python só do Zenith.
- **Passos claros:** ele pergunta onde instalar, baixa o pacote, confere o SHA-256 e instala as bibliotecas.
- **Atualização com volta:** antes de trocar arquivos, guarda a versão anterior; dá para reverter.
- **Certificado:** a lista de raízes HTTPS (`certifi`) vai dentro do `.exe`, e o contexto confia no Windows e nela — foi a correção do erro `CERTIFICATE_VERIFY_FAILED`.
- **Abrir o programa:** se o Corpo fechar logo depois de abrir, o launcher tenta de novo em modo de vídeo mais simples e, se nem isso, tenta abrir pelo projeto e avisa na tela.

**Desinstalar:** o `LimparZenith.exe` permite apagar por partes — histórico, memória, chaves, fotos e vídeos, programas criados, temporários, arquivos pessoais — ou desinstalar tudo, incluindo atalhos e os dados internos do Corpo. Sempre pergunta antes, fecha o programa antes de apagar e nunca toca em raiz de disco, pasta de usuário ou pasta de sistema.

> O Zenith **não** registra entrada em "Aplicativos e recursos" do Windows. Quem desinstala é o `LimparZenith`. É uma escolha (instalação por usuário, sem administrador), não um defeito — e está anotada como possível melhoria.

---

## 13. Site e distribuição

- Página pública com o que o programa faz, prévias reais da interface, o cartão de download e o histórico de versões.
- **Cartão de download** com versão, data, tamanho do launcher e do download total, botão principal, botão de limpar/desinstalar e o SHA-256 de cada arquivo com botão de copiar e o comando `certutil` pronto.
- **Dois arquivos de manifesto:** `latest.json` (o que o launcher lê para saber se há versão nova) e `versions.json` (o que a página mostra no histórico).
- **Assinatura:** o instalador ainda não é assinado, então o Windows pode exibir "Windows protegeu seu PC". Por isso todo download publica o hash.
- **Documentos:** o documento conceitual e o histórico de mudanças ficam disponíveis na própria página, em Word e em texto.

---

## 14. Robô e automação industrial

Extensão do projeto ligada à formação em Automação Industrial.

- **ESP32-S3** com tela TFT: mostra o rosto, recebe comandos por Wi-Fi (TCP), se anuncia na rede (UDP) e também aceita Bluetooth e cabo.
- **Arduino Uno:** recebe as linhas de movimento (`F 1000 140`, `S`) e aciona os motores.
- **A ponte com o assistente:** uma habilidade própria procura o carrinho na rede local — IP salvo, IP informado, descoberta automática, rede própria do carrinho e, por último, o cabo USB — e responde de forma honesta: "entreguei ao carrinho", nunca "ele andou".
- **Segurança:** só endereços de rede local são aceitos; comandos de movimento pedem confirmação e sempre existe comando de parada.

---

## 15. Qualidade: testes e o que significa "provado"

O projeto trata teste como parte da entrega, não como enfeite.

- **Suíte de Python** com mais de 1500 testes, que roda sem Godot, sem internet e sem chaves de API.
- **Testes de contrato** entre Cérebro e Corpo, para que as duas pontas não se afastem em silêncio.
- **Testes com as mensagens de erro reais** dos serviços (503, 404, 429, 413), para que a tradução em português não vire chute.
- **Roteiro manual** (`docs/TESTAR_TUDO.md` e `docs/TESTE_GERAL.md`) na ordem em que os erros aparecem: primeiro o programa abre, depois a IA responde, depois a placa, por último a apresentação.

**Regra de honestidade:** no changelog, cada item diz se foi visto rodando. "Testado" sem ter sido visto não é usado como prova.

---

## 16. Limitações conhecidas

- **Tela preta em placa antiga:** correções aplicadas em 01/11, mas o problema não foi reproduzido no notebook onde apareceu.
- **Instalador sem assinatura digital:** o Windows avisa e alguns antivírus estranham programas que baixam outros programas.
- **Sem entrada em "Aplicativos e recursos":** a desinstalação é pelo `LimparZenith`.
- **Microfone com texto ao vivo:** em ajuste, não finalizado.
- **Aplicativo Android:** não existe.
- **Geração de vídeo por IA:** não existe; o vídeo é editado.
- **IA local:** funciona, mas depende da máquina e do modelo escolhido.
- **Robô:** motores dependem do Uno; Bluetooth e Wi-Fi do carrinho não foram testados em hardware real.
- **Cotas e limites das IAs** são do provedor: o programa explica o motivo, mas não resolve falta de crédito.

---

## 17. Histórico em resumo

O projeto passou por três fases: os **protótipos** (v1.0 a v1.5), as **rodadas de integração** (v22 a v30) e a **1.0 Oficial** (29/10 em diante), com a correção de vídeo de 01/11. O detalhe de cada mudança, com datas, está no documento **Histórico de mudanças**, publicado junto deste.

| Fase | O que marcou |
|---|---|
| Protótipos | Cérebro, Corpo, voz, memória, instalador e edição pública |
| Integração | Interface no Godot, TFT do carrinho, vídeo, anexos, correções de vício |
| 1.0 Oficial | Diagnóstico real das IAs, launcher próprio, `LimparZenith`, site publicado |
| 01/11/2026 | Tela preta, site redesenhado, cartão de download, este acervo |

---

## 18. Próximos passos

Nada aqui está prometido: é a lista de intenções, em ordem de impacto sobre o uso diário.

1. **Roteador de especialistas:** antes de responder, escolher o papel (programador, pesquisador, professor, escritor) com regras próprias — melhora a qualidade sem trocar de modelo.
2. **Texto ao vivo na conversa por voz**, com pausa natural e reconhecimento pré-carregado.
3. **Modo apresentação:** perguntas prontas, aviso de "sem internet", roteiro para demonstração.
4. **Entrada em "Aplicativos e recursos"** com desinstalador registrado, para o Windows reconhecer o programa.
5. **Instalador assinado**, para acabar com o aviso do Windows.
6. **Aplicativo Android** para acompanhar conversas e a biblioteca.
7. **Mais movimentos do avatar** e acabamento das expressões.
8. **Firmware definitivo do robô**, com os motores e a tela sob o mesmo comando.

---

## 19. Considerações finais

O Zenith nasceu de uma pergunta prática: é possível ter um assistente de verdade dentro de casa, com personalidade, rosto e memória, sem entregar os próprios dados? O caminho escolhido foi construir as peças — cérebro, corpo, ponte, instalador, site — e manter uma regra acima de todas: nada acontece sem aprovação.

O resultado de hoje é um programa que instala, conversa, explica, programa, cria, lembra e se mexe na tela. Também é um programa com arestas conhecidas, e é justamente por isso que este documento lista o que ainda falta. Um projeto honesto sobre o que já faz é mais útil do que um projeto que promete tudo.

---

## Apêndice A — Caminhos e comandos úteis

| O que | Onde |
|---|---|
| Instalação padrão | `%LOCALAPPDATA%\Zenith` |
| Dados (conversas, criações, memória) | `dados\` dentro da instalação, ou a pasta escolhida |
| Diário do programa | `zenith_log.txt`, na pasta do aplicativo |
| Regras do assistente | `BIBLIA_ZENITH.md` (fonte: `brain/zenith_biblia.py`) e `config/biblia_extra.md` |
| Suíte de testes | `py -3 -m unittest discover -s tests` |
| Rodar direto do código | `python zenith_launcher.py` |
| Gerar os documentos | `py -3 tools/gerar_documentos.py` |

## Apêndice B — Glossário

- **Cérebro:** a parte em Python que pensa, lembra e decide.
- **Corpo:** o avatar 3D no Godot.
- **Ponte:** o canal de mensagens entre os dois.
- **Habilidade:** uma capacidade extra que o assistente pode usar (carrinho, imagens, vídeo).
- **Etiqueta:** marcação na resposta que dispara uma ação ou um gesto (`<executar_python>`, `<corpo>`).
- **Gatekeeper:** a janela de aprovação que fica entre a intenção e a ação.
- **Bíblia:** o conjunto de regras que ensina qualquer IA a usar este programa bem.
