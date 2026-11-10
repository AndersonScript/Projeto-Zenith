# Como contribuir

Obrigado por querer ajudar! O Zenith é feito em **duas partes**:
- **Cérebro** (`brain/`, Python): conversa, memória, ferramentas, aprovação de ações.
- **Corpo** (`body/zenith/`, Godot 4): janela, avatar VRM, interface.

## Antes de abrir um pull request
1. Rode os testes: `python -m unittest discover -s tests -t .` (têm que passar; não precisam de Godot, internet nem chaves).
2. Rode `python tools/preparar_publico.py --so-conferir`: ele acusa chave de API, caminho pessoal ou arquivo que não pode ir ao GitHub.
3. Mexeu em `.gd` (Godot)? Diga no PR o que você **testou rodando** no Godot e o que não deu para testar.

## Regras do projeto (não negociáveis)
- **Aprovação sempre**: nenhuma ação roda sem a pessoa aprovar. A lista de bloqueios do Gatekeeper vale para tudo.
- **Privacidade**: nunca coloque chaves, conversas ou dados de alguém em arquivos do repositório (nem em teste).
- **Sem telemetria**, sem enviar dados para fora sem a pessoa pedir.
- **Interface sem emoji e sem ícones copiados**: ícones próprios (veja `assets/`).

## Ideias e bugs
Abra uma *issue* contando o que aconteceu, o que esperava e a versão (`/versao` no chat).
