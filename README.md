<p align="center"><img src="assets/zenith_logo_horizontal.png" alt="Zenith" width="560"></p>

<p align="center"><b>Um assistente pessoal com avatar 3D VRM que roda no seu computador e celular Android, só agindo com a sua aprovação.</b></p>

---

### 🚀 Novidades Recentes (Zenith 1.0 / 1.1)
> 📄 **Documento completo e detalhado das atualizações:** [Consulte ATUALIZACOES_ZENITH.md](ATUALIZACOES_ZENITH.md)

* 📱 **Versão Celular Android 100% Autônoma (`Zenith.apk`):** Roda direto no celular sem precisar de computador! Conta com janelinha VRM flutuante/redimensionável (`➖` / `➕`), alternância de enquadramento (`👤 Busto` / `🔲 Médio` / `🧍 Todo`), modo **Maximizar Corpo Todo (`⛶`)**, suporte ao modo paisagem (virar de lado), e armazenamento criptografado de chaves locais.
* 🤸 **Movimentos Acrobáticos Sem Limitações:** Suporte completo a mortais para trás e para frente com compensação do centro de massa no motor 3D, estrelinhas laterais, pulos altos, duplos, giros, danças e criação livre de movimentos pela IA em tempo real!
* 🔍 **Pesquisa Web com Status em Tempo Real:** Sem cortes prematuros de status — acompanhe cada fase da busca e síntese na barra superior.
* 🛡️ **Segurança e Privacidade Total:** Seus dados e chaves nunca saem do seu aparelho sem sua aprovação explícita.

---

## O que o Zenith faz

- **Conversa** com a IA que você escolher (Gemini, OpenAI, Claude, Groq e outras), por voz ou texto, com um avatar 3D em formato VRM.
- **Programa com você**: escreve e roda programas, mostra o código antes e conta o que deu certo ou errado.
- **Cria e edita**: imagens (por serviços de IA e por busca), vídeos (cortar, juntar, legendar, narrar) e documentos.
- **Organiza o computador e celular**: arruma pastas, lê documentos e planilhas que você anexa.
- **Enxerga quando você deixa**: tela e câmera, uma foto ou observação ao vivo, sempre com um aviso visível e botão de parar.
- **Aprende como você trabalha**: guarda o que você pede que ele lembre, e adapta o jeito de ensinar e programar.

## As regras que não mudam

1. **Nada roda sem a sua aprovação.** Código, comandos, abrir programas, ver a tela: tudo aparece numa janela para você aprovar.
2. **Existe uma lista de coisas que ele nunca faz**, nem com aprovação (apagar o disco, desligar o PC, mexer em antivírus e firewall).
3. **Suas chaves, conversas e memória ficam só no seu aparelho.** Não há telemetria.
4. **Sem pegadinha**: o código está aqui para você ler.

## Instalar e Usar

* **📱 No Celular (Android):**
  * Baixe o APK oficial direto pelo site ou pelo link de Release: [Download Zenith.apk](https://github.com/AndersonScript/Projeto-Zenith/releases/download/v1.0/Zenith.apk).
* **💻 No Computador (Windows 10/11, 64 bits):**
  * Baixe pelo site [projeto-zenith-five.vercel.app](https://projeto-zenith-five.vercel.app) ou direto em [Releases](https://github.com/AndersonScript/Projeto-Zenith/releases/latest).
  * O arquivo do programa é o `Zenith_app_1.0.zip`; o `ZenithLauncher.exe` baixa e instala o ambiente para você com 1 clique.

## Para quem quer mexer no código

O projeto tem duas partes principais: o **Cérebro** (`brain/`, Python) e o **Corpo** (`body/zenith/`, Godot 4.7).

```bash
python -m unittest discover -s tests -t .      # testes unitários
python zenith_launcher.py                        # roda direto do código fonte
python tools/preparar_publico.py                 # confere integridade e limpa dados pessoais
```

---
*Criado com dedicação por Anderson.*
