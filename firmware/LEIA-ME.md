# Carrinho Zenith — ESP32-S3 sozinho (v1.5, em cima da sua v1.4)

Por enquanto **só o ESP32-S3** (sem o Arduino). O Arduino Uno e os motores ficam para depois; o código deles
já está na pasta `carrinho_uno/`, mas **não precisa tocar nele agora**.

## 1. O que a v1.5 muda na sua v1.4
Mantive o que funcionou: a inicialização da tela (a mesma da sua v1.4), o rostinho, o Bluetooth, a página de controle,
os comandos de texto e o TX para o Uno.

| Novo | O que faz |
|---|---|
| **VRM na tela** | O Zenith manda o corpo/rosto da VRM e o ESP32 desenha na TFT. O rostinho vira **reserva**: aparece quando o Zenith não está lá. |
| **Wi-Fi inteligente (a sua ideia)** | Veja o item 2. |
| **O Zenith acha o carrinho sozinho** | O carrinho avisa "estou aqui" na rede (UDP 7778). No Zenith: `/tft porta wifi:auto`. Sem digitar IP. |
| **Telinha informativa** | Mostra a rede, o IP e `PC ok`/`PC --`, e avisos em tela cheia ("Wi-Fi conectado!", "Zenith conectado!"). |
| **Painel de check-up** | Na página (e em `/status`): ✓ Tela, ✓ Wi-Fi + IP, ✓ Zenith + quadros, Bluetooth. |
| **Botão BOOT** | Solte entre 3 e 8 s = esquece as redes salvas. Segure **8 s** = **reset de fábrica** (redes + preferências + pareamento Bluetooth). |
| **Reset de tudo** | Também pela página (`/reset`) e pelo USB (digite `RESET`). Veja o item 7. |

### Ligação dos fios (os MESMOS pinos da sua v1.4 — não mudei nada)

**Tela TFT (ST7735 1.8" 128×160, a da foto) no ESP32-S3:**

| Pino da tela | Vai no ESP32-S3 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| **CS** | **GPIO 8** |
| RESET (RES) | GPIO 10 |
| A0 / DC | GPIO 9 |
| SDA / MOSI | GPIO 11 |
| SCK / CLK | GPIO 12 |
| LED (luz de fundo) | 3V3 |

Use **3V3**, nunca 5 V nos pinos de lógica da tela: o ESP32-S3 não é tolerante a 5 V e queima o pino.

**ESP32-S3 para o Arduino Uno (só dois fios):**

| ESP32-S3 | Arduino Uno |
|---|---|
| GPIO 17 (TX) | A0 |
| GND | GND |

O Uno recebe as mesmas linhas de texto (`F 5000 140`, `B 2000`, `L 700`, `R 700`, `S`) e é ele que conta o tempo.

## 2. Como o Wi-Fi funciona agora (o seu fluxo)
1. **Primeira vez, ou rede que sumiu:** o ESP32 cria o Wi-Fi **Zenith_Carrinho** (aberto, como na v1.4).
2. Você entra nele e escolhe **o Wi-Fi onde ele vai ficar** (o hotspot do celular, o da escola...) e digita a senha. Não mexe em código.
3. Ele **entra nesse Wi-Fi e salva** (guarda até 4 redes). Nas próximas vezes entra sozinho.
4. Quando o computador com o Zenith aparece **por esse Wi-Fi**, ele **apaga a rede Zenith_Carrinho**.
5. Se ele não entrar em 20 s, ou a rede cair por 30 s, a Zenith_Carrinho volta para você corrigir.

**Isso resolve o seu problema:** o PC fica no mesmo Wi-Fi que a internet dele (ex.: o hotspot do celular) e o carrinho entra nesse mesmo Wi-Fi.
Não precisa de cabo nem de segunda placa de Wi-Fi.

**Regras que o próprio ESP32 segue:**
- A rede dele só some se o Zenith veio **pelo Wi-Fi de fora**. Se o Zenith estiver conectado **pela rede do carrinho**, ela fica (senão cortaria a conexão).
- Só quem está **na rede do carrinho** muda o Wi-Fi (ou quem souber a `CHAVE`, se você definir uma). Gente de fora não reconfigura.

**Cuidados no mundo real:**
- O ESP32 só entra em Wi-Fi de **2,4 GHz**. No celular: Android → Ponto de acesso → "Banda 2,4 GHz"; iPhone → "Maximizar compatibilidade".
- **Ligue o hotspot ANTES de ligar o carrinho.** Se esqueceu, aperte o botão **RST** da placa para ele procurar de novo.
- O celular que **é** o hotspot normalmente não consegue entrar no Wi-Fi do carrinho ao mesmo tempo. Para configurar, use **o PC ou outro celular**.
- Redes de escola com **página de login** (portal) ou com isolamento entre aparelhos não funcionam. Nesse caso use o hotspot do celular.
- Ao conectar, o aparelho que configurou pode perder a rede do carrinho por alguns segundos. É normal.
- **Ocultar SSID (rede escondida)**: até 01/11 o carrinho **nunca** entrava numa rede oculta — a varredura
  não devolve o nome, então ele não encontrava a rede salva e abria a `Zenith_Carrinho` sozinho. Agora ele
  tenta a rede salva mesmo sem vê-la (espera até 30 s). Ao configurar, **digite o nome à mão**: a lista da
  página só mostra redes visíveis. Se puder, deixe o SSID visível — entra em 2 s em vez de 10-20 s.

## 3. Teste do ESP32-S3 sozinho, passo a passo
**A) Preparar o Arduino IDE** (na sua captura aparece "Nenhuma placa selecionada")
1. O cadeado na aba do arquivo significa "somente leitura": use **Arquivo → Salvar como** e salve em Documentos\Arduino com o nome `zenith_carrinho_v15`.
2. **Ferramentas → Placa → esp32 → ESP32S3 Dev Module**.
3. Ferramentas: **USB CDC On Boot = Enabled**; **Partition Scheme = Huge APP (3MB No OTA...)**; escolha a **Porta**.
4. Bibliotecas (Gerenciar Bibliotecas): *Adafruit GFX*, *Adafruit ST7735 and ST7789 Library*, *TJpg_Decoder* (Bodmer).
5. No aviso "Atualizações disponíveis" clique **DEPOIS**: não atualize nada agora.
6. **Não precisa preencher nenhuma linha.** O nome e a senha do Wi-Fi você coloca pelo celular/PC, depois. (`CHAVE` e `AP_SENHA` são opcionais.)
7. Clique em **Carregar** (a seta →).

**A2) Se preferir NÃO usar a Arduino IDE** (já compilado e testado): grave o arquivo
`carrinho_esp32s3/carrinho_v15_pronto.bin` com o gravador da sua preferência (por exemplo o **ESP32 Flash
Download Tool**, ou `esptool` no endereço **0x0**). Já vem com o bootloader, as partições (`Huge APP`) e o
firmware juntos. A IDE continua sendo o caminho normal — este binário é o atalho para quando o Arduino IDE
da escola estiver sem as bibliotecas.

**B) O que deve acontecer na telinha**
Barras coloridas por 1,5 s, depois os olhos e a boca, e no rodapé `Rede Zenith_Carrinho` / `192.168.4.1 PC --`.

**C) Testar a rede do carrinho**
No PC (ou celular), entre no Wi-Fi **Zenith_Carrinho**. A página abre sozinha (ou vá em `192.168.4.1`). Aperte os botões de rosto e veja a telinha mudar. O quadro de check-up mostra `✓ Tela`.

**D) Fazer ele entrar no seu Wi-Fi**
1. Ligue o **hotspot do celular** (2,4 GHz) com nome e senha de 8+ caracteres.
2. No PC, ainda no Zenith_Carrinho, clique em **Conectar a um Wi-Fi** (ou `192.168.4.1/rede`), escolha o hotspot, digite a senha e **Conectar e salvar**.
3. Em uns 15 s a telinha mostra **"Wi-Fi conectado!"** e o IP.
4. Agora **ligue o PC nesse hotspot**.

**E) A VRM na telinha**
1. Uma vez só, na pasta do Zenith (a que tem `brain/`), com o Zenith fechado: `python aplicar_wifi_tft.py`. (Faz cópia `.bak_wifi`; desfaz com `--desfazer`.)
2. Abra o Zenith e digite **`/tft porta wifi:auto`** e depois **`/tft teste`**. O Windows pode perguntar sobre o firewall: **permita** (é o aviso do carrinho por UDP).
3. A telinha mostra **"Zenith conectado!"**. Em 3 s a rede **Zenith_Carrinho some** e a VRM aparece. Para ver o corpo inteiro: `/tft enquadre corpo` (ou `busto`, `rosto`).
4. Se o `wifi:auto` não achar (algumas redes bloqueiam o aviso), use o IP que aparece na telinha: `/tft porta wifi:192.168.x.x`.

**F) Outros lugares**
Com a rede salva por perto, ele entra sozinho. Num lugar novo: sem rede conhecida a Zenith_Carrinho aparece sozinha; repita o passo D.
Para esquecer tudo: segure o botão **BOOT** por 3 s.

## 4. Bluetooth

**Achado o defeito (29/10):** o painel do PC procurava por `Zenith-Carrinho` (com hífen) e o ESP32 anunciava
`Zenith_Carrinho` (com sublinhado). A comparação era exata, então o painel **nunca achava** o carrinho — o
Bluetooth não estava quebrado, cada lado procurava um nome diferente. Já está corrigido nos dois lados:
- `tools/carrinho_painel.py` agora aceita `Zenith-Carrinho`, `Zenith_Carrinho`, `Zenith Carrinho` (ignora hífen,
  sublinhado, espaço e maiúsculas) e, se o nome vier estranho, aceita o aparelho que anuncia o serviço Nordic UART.
- O firmware passou a anunciar o nome **e** o serviço, com intervalo de anúncio curto (`setName`, `setMinInterval`),
  e MTU 128 para a linha de comando caber inteira.

Como testar, na ordem:
1. **Painel do PC** (é o caminho normal):
   ```
   pip install bleak pyserial
   python tools\carrinho_painel.py
   ```
   Ele abre uma página em `http://127.0.0.1:8777` com os botões e mostra o estado da conexão.
2. **Celular** (para saber se o problema é o PC): app **nRF Connect** → procure `Zenith_Carrinho` → conectar.
   Se aparecer e conectar, o ESP32 está certo e o problema era o PC.
3. **USB (último recurso, sempre funciona)**:
   ```
   python tools\carrinho_painel.py --usb        (ou --listar para ver as portas COM)
   ```
   Pelo cabo, o carrinho responde igual ao Bluetooth, sem rádio nenhum no meio.

Se o Bluetooth atrapalhar o Wi-Fi, mude `#define USAR_BLE 1` para `0` no topo do arquivo: o resto continua igual.
Com Wi-Fi + Bluetooth ligados juntos o rádio é dividido; depois que a rede do carrinho sai do ar isso melhora.

## 5. O que foi e não foi testado
- **Testado aqui:** a lógica nova do ESP32 em simulação no PC (redes salvas, limite de 4, rede repetida, apagar a rede do carrinho só quando seguro, cenários
  de entrar/falhar/cair); o patch do Zenith aplicado numa cópia do v1.9 Público contra um ESP32 de mentira (conexão, quadros byte a byte, queda e
  reconexão, descoberta automática, recusa de endereço de internet): 17 testes novos e os 122 antigos passam; a sintaxe do arquivo nas 4 combinações
  (com/sem Bluetooth, com/sem VRM).
- **Não testado:** compilar **de verdade** no ESP32-S3 e qualquer coisa em **hardware real** (tela, Wi-Fi, Bluetooth). Se não compilar, mande a mensagem inteira.
- **Não mexi** nos pendentes do Zenith que você listou (GitHub, imagem colada que não aparece no chat, "em que ela se baseou", limite de 15 s dos comandos).

## 7. Reset de tudo (quando nada conecta)

Três caminhos, do mais fácil ao de último recurso. Os três fazem a mesma coisa: apagam **redes salvas,
preferências e o pareamento Bluetooth**. O programa gravado no chip **não** é apagado.

| Onde | Como |
|---|---|
| **Página** | `http://192.168.4.1/` → botão **Reset de tudo** (confirma antes) · ou `http://192.168.4.1/reset?confirma=sim` |
| **Placa** | Segure o botão **BOOT** por **8 segundos** (a telinha avisa aos 3 s: "8 s = reset total") |
| **USB** | Monitor Serial em **115200**, digite `RESET` e Enter (ou `RESET REDES` para apagar só as redes) |

Depois do reset o carrinho reinicia sozinho e cria a rede **Zenith_Carrinho** de novo — do zero.
Só quem está na rede do carrinho (ou quem sabe a `CHAVE`) pode mandar o reset pela página.

## 8. Para a etapa do Arduino (depois)
`carrinho_uno/carrinho_uno.ino` recebe as mesmas linhas (`F 5000 140`, `S`...) pelo A0, com fila, limites e parada. A ligação é GPIO 17 → A0 e GND com GND.
A página `/cmd?c=F 1000 140` da v1.4 continua funcionando, e `/cmd?c=F&t=1000&v=140` e `/parar` também (usados pela habilidade `skills/carrinho.py`).
