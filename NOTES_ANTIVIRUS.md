# Zenith — Antivírus dando falso positivo no `.exe`

> **v28 — achado nos prints:** o aviso "Parte deste aplicativo foi bloqueado" do Windows Security citou o módulo
> `_pybase64.cp314-win_amd64.pyd` (uma biblioteca nativa de dentro do `_internal`). É o **Controle Inteligente de Aplicativos**
> barrando um `.pyd` sem assinatura. Se a biblioteca é carregada e o Windows barra, o recurso que depende dela falha em silêncio —
> hipótese (a confirmar com o `zenith_log.txt`) pra "a primeira abertura estranha / primeira mensagem sem IA".
> Dois caminhos: (1) gerar o build com **Python 3.12 ou 3.13** (mais rodas prontas, menos `.pyd` desconhecidos que o 3.14);
> (2) assinar o `.exe` e os `.pyd` (ver seção 3). Pra distribuir pra outras pessoas, o certificado é o que resolve de verdade.

Preciso ser honesto: **não existe truque de código que "desliga" a
desconfiança do antivírus.** O que existe é reduzir os motivos que
fazem heurísticas de antivírus (Windows Defender incluso) marcarem um
`.exe` como suspeito. PyInstaller gerando um `.exe` novo, não
assinado, é um dos padrões mais comuns de falso positivo — não é
peculiaridade do Zenith.

Isso dito, o que realmente ajuda, em ordem de impacto:

## 1. Use `--onedir`, não `--onefile`
Um `.exe` "onefile" descompacta a si mesmo pra uma pasta temporária
toda vez que abre — esse comportamento (auto-extração + execução) é
exatamente o padrão que heurísticas de antivírus associam a
malware/dropper. `--onedir` (uma pasta com o `.exe` + os arquivos ao
lado, sem auto-extração) dispara MUITO menos falso positivo.

Já ajustei o `build_exe.bat` pra gerar em `--onedir` por padrão
(o resultado fica em `dist\Zenith\Zenith.exe` + uma pasta `_internal`
do lado — distribua a pasta inteira, não só o `.exe`).

## 2. Não comprima com UPX
UPX reduz o tamanho do `.exe`, mas o "empacotamento" que ele faz é a
MESMA técnica que malware usa pra ofuscar assinatura de vírus — quase
todo antivírus desconfia automaticamente de binários comprimidos com
UPX. `build_exe.bat` já roda sem UPX.

## 3. Assinatura de código (o que realmente resolve de vez)
Um certificado de assinatura de código (Authenticode) faz o Windows
mostrar seu nome/empresa como editor confiável em vez de "Editor
desconhecido". Isso é o que separa definitivamente de malware aos
olhos do SmartScreen. **Isso custa dinheiro** (uns certificados EV
custam mais, mas dão reputação instantânea; certificados OV mais
baratos ainda precisam "ganhar reputação" com o tempo/downloads antes
do SmartScreen parar de avisar). Não é algo que eu consigo automatizar
por você — é uma decisão sua, de comprar ou não.

## 4. Submeta pros fornecedores de antivírus
Windows Defender: https://www.microsoft.com/en-us/wdsi/filesubmission
A maioria dos fornecedores tem um formulário parecido pra você
reportar "isso é falso positivo, aqui está meu binário". Leva alguns
dias, mas cada submissão ajuda o próximo usuário a não levar o aviso.

## 5. NÃO peça pro usuário desativar o antivírus
Você já percebeu isso certo — pedir pra desativar o antivírus é
exatamente o tipo de instrução que golpes/malware também pedem, então
isso assusta (com razão) quem for instalar. A lista acima (onedir, sem
UPX, assinatura, submissão) é o caminho certo — nenhuma dessas etapas
pede isso do usuário final.

---

## v18 — o que mudou com a importação automática de avatar (e o que checar se o antivírus reclamar)

O Zenith.exe agora, só quando o usuário clica em "Adicionar avatar...": (1) copia um `.vrm` pra
dentro da própria pasta, (2) abre o `Godot*.exe` (editor) escondido, em linha de comando, (3)
reescreve `body/zenith/export/Zenith.pck` e (4) fecha/reabre o Corpo. Tudo dentro da pasta do
Zenith — mas "um programa não assinado que abre outro `.exe` e reescreve arquivos do próprio
diretório" é parecido, no comportamento, com o que heurísticas procuram. Não é prova de que vai
alertar; é um motivo a mais pra checar.

**Como descobrir QUAL arquivo/qual regra disparou** (isso decide a solução — sem isso qualquer
conselho é palpite): Segurança do Windows > Proteção contra vírus e ameaças > *Histórico de
proteção*. Anote: nome do arquivo, nome da ameaça (ex.: `Trojan:Win32/Wacatac...`), e a ação
(bloqueado/quarentena). Se for outro antivírus, o nome da ferramenta e a mensagem exata.

**No seu PC de desenvolvimento, SE o antivírus ativo for o Defender** (se for o Norton, pule pra seção
"Norton 360" abaixo; se a mensagem for "Parte deste aplicativo foi bloqueada", é o Controle Inteligente — seção própria acima — com outro antivírus instalado o Defender fica passivo e estes passos não adiantam;
não é pra pedir isso a usuário final — ver item 5 acima):
- Exclusão da pasta do Zenith no Defender, num PowerShell **de administrador**:
  `Add-MpPreference -ExclusionPath "C:\Zenith"` (ajuste o caminho). Isso também acelera a
  importação do Godot, que gera milhares de arquivos pequenos em `.godot/`.
- Rode `build_exe.py` num terminal **normal** (não "Executar como administrador"). O próprio
  PyInstaller avisou no seu build que a versão 7.0 vai bloquear isso — é o aviso que aparece no
  topo do log. Não há prova de que isso cause o alerta de antivírus, mas é a primeira coisa a
  tirar da equação.
- Se o Defender colocar `Zenith.pck.bak`, `Zenith_novo.pck` ou o `.exe` em quarentena no meio de
  uma importação, o Zenith avisa no chat que não conseguiu trocar o arquivo e **não perde nada**:
  o `.pck` antigo continua intacto.

**Pra distribuir pra terceiros** (o que realmente reduz alerta, além dos itens 1–4 acima):
- Recompilar o *bootloader* do PyInstaller a partir do código-fonte (precisa de um compilador C no
  Windows): o `.exe` do bootloader pré-compilado é idêntico pra todo mundo que usa PyInstaller, e é
  esse binário conhecido que muitos antivírus marcam. Um bootloader compilado por você deixa de ser
  o mesmo arquivo. Não elimina o alerta, mas costuma reduzir.
- O editor do Godot (`tools/godot/Godot_v4.x_win64.exe`), se você distribuir junto, também não é
  assinado nas builds oficiais do Windows — o SmartScreen pode avisar ao baixar. Ele vem do site
  oficial do Godot; mantenha a licença (MIT) na pasta.

---

## Controle Inteligente de Aplicativos (Smart App Control) — a causa real do bloqueio de 01–02/10/2026

**O que aconteceu.** Depois de gerar o `dist/Zenith/`, o Windows mostrou a notificação da *Segurança do
Windows*: "Parte deste aplicativo foi bloqueada — alguns recursos de `...\dist\Zenith\Zenith.exe` podem não
funcionar porque não é possível confirmar quem publicou `Zenith.exe` que o aplicativo tentou carregar". Essa
é a mensagem do **Controle Inteligente de Aplicativos** (recurso do Windows 11), não de um antivírus. (Nas
rodadas anteriores eu suspeitei do Norton só porque havia um atalho dele na área de trabalho — estava
errado; a seção sobre o Norton fica mais abaixo, só por garantia.)

**Por que.** Segundo a Microsoft, ele trata como não confiável qualquer programa **sem assinatura digital**
(ou com assinatura inválida) que ele não reconheça pela reputação na nuvem. O `Zenith.exe` do PyInstaller e o
`Zenith.exe` do Corpo (exportado do Godot) são gerados por você, a cada build, e não têm assinatura — nascem
"desconhecidos". Quando um programa que ele aceita tenta carregar um arquivo assim, ele bloqueia só **aquele
arquivo**: "a funcionalidade que depende dele não funciona, mas o resto do aplicativo pode continuar". É por
isso que parecia que "bloqueou uma parte": o Cérebro (Python) rodou — o `zenith_log.txt` foi atualizado — e
o Corpo (avatar + Central de Controle) provavelmente não abriu.

**O que o Zenith faz agora (v18)**
- `/diagnostico` mostra o estado do Controle Inteligente (lê `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy`,
  valor `VerifiedAndReputablePolicyState`: 0 desligado, 1 ligado, 2 avaliação).
- Se o Corpo não abre (erro ao iniciar, ou fecha em menos de 4 s), o launcher **mostra uma caixa de mensagem
  na tela** explicando, em vez de ficar rodando invisível.
- **Plano B automático**: tenta abrir o MESMO Corpo pelo editor oficial do Godot (`Godot --path <projeto>`,
  equivale ao F5 sem a janela do editor), que o Windows já conhece. Precisa do editor do Godot (em
  `tools/godot/`, Downloads, Desktop, raiz do disco como `C:\Godot_v4.7.1`...) e de `body/zenith/.godot/imported`
  (existe depois de abrir o projeto no editor uma vez). **Nunca foi testado no Windows de verdade.**
- A importação de avatar também explica o bloqueio quando o Godot não abre.

**O que VOCÊ pode fazer**
1. *Confirmar:* Segurança do Windows > Controle de aplicativos e navegador > Configurações do Controle
   Inteligente de Aplicativos. Se estiver "Ativado", é ele.
2. *Rodar o v18 e ver se o Plano B abriu o Corpo* (o `zenith_log.txt` diz "Plano B funcionou" ou por que não).
3. *Desligar o Controle Inteligente* — solução imediata, mas reduz a proteção do PC. Pelo FAQ atual da
   Microsoft ele pode ser desligado nas configurações do Windows Security e, em atualizações recentes, ligado
   de novo sem reinstalar o Windows (uma fonte de terceiros situa isso na atualização de março de 2026).
   **Antes de desligar, leia o que a tela do SEU Windows diz**: se avisar que não dá para religar sem
   reinstalar, não desligue ainda. Desligar só pra testar e religar depois é o uso mais seguro.
4. *Assinar o programa* — a solução de verdade (e a única que serve para entregar a outras pessoas).
   O serviço da Microsoft (Artifact Signing, antigo Trusted Signing) hoje só aceita **pessoa física dos
   EUA e do Canadá** (organizações: EUA, Canadá, UE, Reino Unido) — **não serve para você no Brasil**.
   Sobra um certificado OV de uma autoridade certificadora comum (~US$ 150–300/ano; várias exigem empresa
   registrada, então vale conferir se um MEI/CNPJ serve) ou, para projeto de código aberto, a SignPath
   Foundation. Assinatura é decisão de produto, não de código — fica no `IDEIAS_ROADMAP.md`.

**Um truque que NÃO resolve sozinho, mas ajuda:** o `Zenith.pck` não é executável, então trocá-lo (importar
avatar) não gera um "programa novo desconhecido". Já o `Zenith.exe` do PyInstaller muda a cada build.

---

## Norton 360 (só se ele TAMBÉM estiver ativo)

Passos conferidos nas páginas oficiais do Norton ("Exclude files and folders from Norton scans" e "Submit a
file or URL to Norton for review"); os nomes dos menus mudam um pouco entre versões.

**1. Descobrir o que ele barrou.** No Norton, abra o histórico de segurança / quarentena. Anote:
o nome do arquivo, o **nome da detecção** (ex.: `Heur.AdvML.B`, `WS.Reputation.1`, algo do SONAR) e o
**Alert ID** (fica embaixo do aviso que aparece). Sem isso não dá pra escolher a solução certa.

**2. Excluir a pasta do Zenith — nas DUAS listas** (só no seu PC de desenvolvimento; o próprio
Norton avisa que isso reduz a proteção do que está na pasta):
Norton > **Settings** > **Antivirus** > aba **Scans and Risks** > em *Exclusions / Low Risks*, clique
em **Configure** em cada uma destas linhas e adicione a pasta (**Add Folders**, incluindo subpastas):
- *Items to Exclude from Scans*
- *Items to Exclude from Auto-Protect, Script Control, Behavioral Protection and Download
  Intelligence Detection*
Pasta a excluir: a raiz do projeto (ex.: `C:\Zenith`, que cobre `Zenith\dist` e `Zenith\build`).
Se o Norton já mandou algo pra quarentena, restaure DEPOIS de criar a exclusão.

**3. Enviar como falso positivo** (o que de fato ajuda a longo prazo): https://submit.norton.com >
*URL and File Submission* > *Open submit form* em **False positive** > e-mail, nome da detecção,
Alert ID e o arquivo. Regras do Norton: 1 arquivo por envio (coloque num ZIP/RAR **sem senha**),
até 500 MB. Envie só o `.exe` que foi detectado (`dist\Zenith\Zenith.exe`), não a pasta inteira.
Quando ele atualizar o build, o hash muda — pode precisar reenviar.

**4. Hipótese sobre a importação de avatar (NÃO confirmada).** O Norton tem proteção
comportamental (SONAR): um programa sem assinatura que abre outro `.exe` (o Godot) e escreve
milhares de arquivos pequenos em `.godot/imported/` pode ser barrado ou ficar muito lento — o que
explicaria a importação do 1º teste não terminar. Se for isso, a exclusão do passo 2 deve resolver
as duas coisas. Se a importação continuar parada com a pasta excluída, a causa é outra (ver
`zenith_log.txt`).


---

## v24 — "deu problema no antivírus de novo": o que dá pra saber, o que não dá e o que mudou

**O que eu NÃO sei:** qual antivírus e qual mensagem apareceram desta vez (eu não vejo a sua tela). Isso decide a solução —
sem o texto exato é palpite. Anote: **onde** apareceu (gerando o build / abrindo o `Zenith.exe` / abrindo o avatar), o
**nome da detecção** (ex.: `WS.Reputation.1`, `Heur.AdvML.B`, `Trojan:Win32/Wacatac…`) ou a frase ("Parte deste aplicativo foi
bloqueada" = Controle Inteligente de Aplicativos, não antivírus) e, no Norton, o **Alert ID**.

**Por que volta "de novo" a cada build (isto eu sei):** cada `build_exe.py` gera um `Zenith.exe` com hash **novo**. Para o
Controle Inteligente de Aplicativos, o SmartScreen e a "reputação" do Norton (`WS.Reputation`), arquivo novo e sem assinatura
= **desconhecido** = suspeito, mesmo sendo exatamente o mesmo código de ontem. Não é algo que um truque de código elimine
(as seções acima continuam valendo: `--onedir`, sem UPX, não rodar como administrador, enviar falso positivo).

### O que mudou no v24 (ajuda, mas não é mágica)
- **Metadados dentro do `.exe`** (`--version-file`: produto, descrição, versão — aba *Detalhes* do Windows). Um `.exe` sem
  nenhum metadado é um ponto contra ele nos motores de "aprendizado de máquina". Honesto e inofensivo; não resolve sozinho.
- **`dist/Zenith/HASHES_SHA256.txt`** com o hash de cada `.exe`/`.pck` do build: serve pra procurar no VirusTotal, preencher o
  formulário de falso positivo (Norton/Microsoft) e conferir que a cópia em outro PC é a mesma que você gerou.

### A mudança que mais reduz o problema no SEU PC de desenvolvimento: **pare de gerar o `.exe` a cada teste**
O `.exe` é pra **distribuir**. Pra testar, rode do código — o programa que o Windows executa é o `python.exe` do seu venv
(assinado, já conhecido), e não um arquivo novo:
1. No PyCharm/terminal, com o venv do projeto: `python zenith_launcher.py` (na pasta do projeto). *(Não use `.bat`: o Windows
   bloqueia `.bat` baixado — foi por isso que o `build_exe.bat` foi aposentado.)*
2. O Corpo (Godot) abre pelo `body/zenith/export/Zenith.exe` que você já tem — esse arquivo **não muda** entre os meus
   pacotes (só o `.pck` e os `.gd`), então a reputação dele não zera — ou, se o Windows barrar, pelo **Plano B**
   (editor do Godot com `--path`, que lê os `.gd` direto, sem exportar nada).
3. **Os scripts do Godot mudaram no v24** (TFT, fundo do avatar, observação, balão): se você usa o `Zenith.exe` exportado,
   **exporte de novo** (Project → Export → Windows Desktop → *Export PCK/ZIP* basta, se o `.exe` for o mesmo); pelo Plano B
   não precisa exportar.
4. Só gere o `.exe` (`python build_exe.py`, num terminal **normal**) quando for entregar a alguém.

### Comportamentos novos que um antivírus comportamental (Norton SONAR, por ex.) pode notar
Nenhum é malicioso, mas são do tipo que motores heurísticos observam; se algum alerta citar um deles, já sabe a origem:
| Comportamento | De onde vem | Como desligar |
|---|---|---|
| Listar portas COM e, se achar a placa, escrever nela | `zenith_tft.py` (TFT no ESP32-S3) | `/tft desligar` (ou `tft_ativo: false`) |
| Capturar a tela/câmera repetidamente e enviar a uma IA na nuvem | `/observar` (só com a sua aprovação, 🔴 visível, para sozinho em 15 min) | não usar `/observar`; `/parar_observacao` |
| Rodar scripts Python que a própria Zenith escreveu | habilidades (`skills/`), sempre com aprovação | `habilidades_ativas: false` |
| Abrir o Godot e reescrever o `.pck` | importar avatar (v18) | — |

### Se o alerta for do **Norton** e você só quer trabalhar
Exclua a pasta do projeto **nas duas listas** (passo 2 da seção "Norton 360" acima) e envie **só o `Zenith.exe` detectado**
em https://submit.norton.com (passo 3), colando o **hash** que está em `HASHES_SHA256.txt`. A cada build novo o hash muda e
pode ser preciso enviar de novo — outro motivo pra não gerar `.exe` a cada teste.


---

## v25 — o aviso real: "Parte deste aplicativo foi bloqueada… uv.exe … python.exe"

O texto exato que apareceu (captura do Anderson): *"Alguns recursos do `C:\Users\joao\.local\bin\uv.exe` podem não funcionar porque
não é possível confirmar quem publicou `python.exe` que o aplicativo tentou carregar."* — notificação **Segurança do Windows**.

**O que isso é:** o **Controle Inteligente de Aplicativos** (Smart App Control, Windows 11) — **não é antivírus, e não é o Zenith.**
Quem foi barrado é o **`uv.exe`** (gerenciador de pacotes/ambientes do Python, que o PyCharm usa nos bastidores) ao tentar carregar um
`python.exe` **sem assinatura** (muito provavelmente o do `.venv` criado pelo próprio `uv`). Por isso aparece "toda vez que eu mexo
em qualquer coisa": é o PyCharm chamando o `uv`, não o `Zenith.exe`. *(Pelos caminhos, é a explicação mais provável; eu não vejo o seu PyCharm.)*

**Como resolver (do mais seguro pro menos):**
1. **PyCharm → Settings → Project: Zenith → Python Interpreter**: se o tipo for **uv**, troque para **Virtualenv/Existing** apontando pra
   `C:\Zenith\.venv\Scripts\python.exe`; ou recrie o ambiente com o Python oficial (assinado): `py -3.14 -m venv .venv` e
   `.venv\Scripts\pip install -r requirements.txt` (+ `pip install plyer pyserial`).
2. Se você não usa o `uv` pra mais nada: `uv self uninstall` (ou apague `C:\Users\joao\.local\bin\uv.exe`).
3. **Desligar o Controle Inteligente** (Segurança do Windows → Controle de aplicativos e navegador). É a opção que *resolve tudo*,
   mas **reduz a proteção** e, em muitas versões do Windows 11, **não dá pra religar sem reinstalar** — decisão sua.
O `build_exe.py` rodou **certo** no seu print (metadados de versão gravados, `HASHES_SHA256.txt` gerado). Dois avisos dele ainda valem:
rode num terminal **sem administrador** e `pip install plyer` (notificação do Windows).
