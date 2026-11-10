# Segurança

O Zenith roda no computador de quem usa e pode executar código e comandos — por isso a regra principal é:
**nada roda sem a aprovação da pessoa**, e existe uma lista de coisas que ele nunca faz, nem com aprovação.

## Como reportar uma falha de segurança
Abra uma *Security Advisory* privada na aba **Security** do repositório (não abra uma issue pública).
Conte o que acontece, como reproduzir e qual o impacto. Respondemos assim que possível.

## O que consideramos falha séria
- uma ação rodar **sem** a janela de aprovação;
- o Zenith conseguir passar pela lista de bloqueios (apagar disco, desligar o PC, mexer no antivírus/firewall);
- uma chave de API ou conversa aparecer em log, arquivo de distribuição ou rede;
- qualquer envio de dados que o usuário não tenha pedido.

## Sobre a confiança no instalador
Confira o **SHA-256** do instalador na página de download. Enquanto o instalador não tiver assinatura digital, o
Windows pode mostrar o aviso "Windows protegeu seu PC": confira o hash antes de continuar.
