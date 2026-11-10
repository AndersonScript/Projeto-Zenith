# Carrinho do Zenith — montagem, energia e teste (SEM CABO)

```
PC  --Bluetooth (BLE)-->  ESP32-S3  --2 fios-->  Arduino Uno  -->  4 motores
                              |  rosto na TFT 128x160
```

O PC não fica preso ao carrinho. Quem conversa com ele é o **painel**
(`tools/carrinho_painel.py`), que abre no navegador e fala Bluetooth sozinho.
A Zenith só pede ao painel ("anda 3 segundos"); ela não conhece o rádio.

| Peça | Cuida de | Não sabe |
|---|---|---|
| **PC** (painel) | o pedido: frente, trás, girar, quanto tempo | nada de motor |
| **ESP32-S3** | Bluetooth, rosto na tela, e repassar ao Uno | para onde ir |
| **Uno** | conta o tempo e **para sozinho**; teto de 10 s; fila de 6 | nada de rádio |

Se o Bluetooth cair no meio de um passo, o Uno termina aquele passo e para. Além disso,
o ESP32 manda `S` (parar) no instante em que a conexão cai. Não existe "andar para sempre".

---

## 1. Energia (isto mudou: não tem mais cabo para alimentar)

Há dois jeitos. Os dois funcionam; escolha um e **não misture**.

### Opção A — tudo pela bateria de 12 V (uma fonte só)

| De | Para | Observação |
|---|---|---|
| Bateria 12 V (+ e −) | borne **PWR** do shield | é a única energia do carrinho |
| Shield **PWR** (jumper) | → alimenta o Uno | **jumper PWR DENTRO** (o do shield) |
| Uno **5V** | ESP32 **5V** | o Uno repassa; ~200 mA no total |

Nada de power bank e nada de USB. O regulador do shield converte 12 V → 5 V e alimenta
Uno + ESP32 juntos.

**Duas conferências obrigatórias (é o que evita surpresa no meio da apresentação):**
1. Com tudo ligado, **multímetro no pino 5V do Uno**: tem que dar **4,7 V ou mais**.
   Se der menos (~4,3 V), o jumper está passando pelo regulador do Uno e não sobra tensão
   para o ESP32 — nesse caso use a Opção B.
2. Depois de **5 minutos** ligado, **encoste no regulador** do shield (a peça de 3 pernas
   perto do jumper). Morno, tudo bem. Se não conseguir segurar o dedo, ele está cozinhando:
   a conta é (12 V − 5 V) × 0,2 A ≈ **1,4 W** num componente sem dissipador.

### Opção B — power bank para a cabeça

| De | Para | Observação |
|---|---|---|
| **power bank** (USB 5 V) | ESP32-S3 | a cabeça tem energia própria |
| ESP32 **5V** | Uno **5V** | ~50 mA, sobra folga |
| Bateria 12 V (+ e −) | borne de motor do shield | **jumper PWR do shield FORA** |

Mais cabos, zero calor. É a opção que eu usaria se o carrinho for ficar ligado muito tempo.

**Nos dois casos o GND é comum** — ele já vai no fio ESP32 ↔ Uno.

> **A conta que queima motor:** os seus motores são de **5 V** e a bateria é **12 V**; o
> L293D derruba ~1,5 V, então a roda recebe ~10 V. Por isso o teto de velocidade é **150 de
> 255** (58%) — média perto de 6 V no motor. Depois de 1 minuto, **encoste no motor**: quente
> demais → baixe `VEL_MAX` para 120, ou ligue os dois islotes de pilha em **paralelo (6 V)**.

## 2. Fios

### ESP32-S3 ↔ Uno (2 fios + GND)

| ESP32-S3 | Arduino Uno | Para que serve |
|---|---|---|
| **GPIO 17** (TX) | **A0** | o ESP32 fala, o Uno escuta |
| **GND** | **GND** | obrigatório |
| GPIO 18 | A1 (opcional) | reservado |

Só um lado fala: 3,3 V do ESP32 no Uno funciona; **5 V do Uno num pino do ESP32 queima**.

### Tela TFT 1,8" (128×160)

| TFT | ESP32-S3 |
|---|---|
| VCC / LED | 3V3 |
| GND | GND |
| CS | GPIO 8 |
| RESET | GPIO 10 |
| A0 (DC) | GPIO 9 |
| SDA (MOSI) | GPIO 11 |
| SCK | GPIO 12 |

Os pinos do cartão SD ficam **sem ligar**. São os mesmos pinos do firmware antigo da TFT.

### Antena (o detalhe que decide o alcance)

Deixe a ponta da placa do ESP32 **longe dos motores** e não passe o fio do motor por cima
dela. Motor escovado faz chiado de rádio e come o alcance: 10 m com folga, 20 m no aberto.

## 3. Gravar

**a) Uno** — `carrinho_uno/carrinho_uno.ino` (pasta com o mesmo nome do arquivo).
Biblioteca **Adafruit Motor Shield library (V1, AFMotor)**. Monitor Serial 9600.

**b) ESP32-S3** — `carrinho_esp32s3/carrinho_esp32s3.ino`.
Placa **ESP32S3 Dev Module**, pacote esp32 **3.x**, **USB CDC On Boot = Enabled**.
Bibliotecas: *Adafruit GFX* e *Adafruit ST7735 and ST7789*.
BLE já vem no pacote da Espressif — **não instale nada de Bluetooth**.
Se a tela atrapalhar: `#define TEM_TELA 0` e o carrinho anda igual.

**c) Computador** — uma biblioteca só (não é aplicativo):

```
pip install bleak
```

Ela já foi instalada nesta máquina. Se algum dia faltar, o painel avisa exatamente isso.

## 4. Teste, do mais seguro para o menos

1. **Rodas no ar, só o Uno** (com o cabo USB dele): Monitor Serial 9600, `F 1000`. *(você já viu funcionar)*
2. **Só o ESP32**, no power bank. `python tools/carrinho_painel.py --procurar` tem que listar
   `Zenith-Carrinho`. Se não listar: carrinho ligado? Bluetooth do PC ligado?
3. **O painel:** `python tools/carrinho_painel.py` (abre o navegador sozinho). O topo mostra
   `Bluetooth Zenith-Carrinho`. Se disser "sem conexão", ele tenta de novo a cada 5 s — é só esperar.
4. **Os dois, rodas no ar.** "frente" 1 segundo. O painel mostra `entregue ao carrinho: F 1000 140`.
5. **Rosto:** feliz / pensando / falando.
6. **No chão**, 1 segundo por vez, espaço livre, PARAR à mão. Comece perto do PC.
7. **Distância:** afaste o carrinho andando e veja onde o aviso de "sem conexão" aparece.
8. **Zenith:** *"anda para frente 3 segundos"* — ela pede aprovação (Pilar 1) e entrega ao painel.

Ainda dá para testar **com cabo** quando quiser: `python tools/carrinho_painel.py --usb`.
Os dois canais funcionam ao mesmo tempo (o ESP32 escuta BLE e USB juntos).

## 5. Se não funcionar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `--procurar` não lista nada | carrinho desligado, sem power bank, ou PC sem Bluetooth | ligue o carrinho; veja o Gerenciador de Dispositivos |
| "o Bluetooth do Windows não respondeu" | PC sem adaptador (desktop comum) | dongle USB Bluetooth 4.0+ ou use `--usb` |
| Painel diz "sem conexão" e não muda | outra coisa conectada no carrinho | feche outro painel/terminal aberto |
| Reinicia sozinho pouco depois de ligar (Opção A) | regulador do shield esquentando | Opção B (power bank) ou um step-down 12→5 V |
| Conecta, mas a roda não mexe | fio TX/GND, ou Uno sem energia | confira GPIO 17 → A0, GND comum, LED do Uno |
| Anda e para no meio do quintal | fora de alcance / motor atrapalhando a antena | aproxime; afaste a placa dos motores |
| Uma roda gira ao contrário | montagem daquele motor | em `carrinho_uno.ino`, `INVERTER` → `true` |
| Motor esquentando | 12 V em motor de 5 V | `VEL_MAX 120`, ou pilhas em paralelo (6 V) |
| Tela apagada | LED do módulo sem alimentação | pino LED no 3V3 |
| Tela com borda deslocada / cores trocadas | variante do controlador | troque `TFT_TAB` (0 → 1 → 2) |
| Fila enche e ele fica surdo | 6 passos por vez (limite do Uno) | espere ou mande `S` |
| `pip install bleak` falha | sem internet no PC | é a única dependência; sem ela, use `--usb` |

## 6. O que foi e o que não foi testado

- **Conferido aqui:** o painel rodando de verdade (modo `--simular`), a habilidade respondendo
  aos pedidos em português, os limites (10 s, fila de 6), e a suíte inteira do Zenith.
- **Não testado:** os dois `.ino` **não foram compilados** (não há compilador ESP32 nesta
  máquina) e **nada rodou em hardware** — nem o Bluetooth, nem a tela. Se o Arduino IDE
  reclamar, mande a mensagem completa: normalmente é biblioteca faltando ou pino.

## 7. Por que BLE e não "Bluetooth normal"

O ESP32-S3 só tem **BLE**. Ele não aparece em "Dispositivos Bluetooth" do Windows como um
HC-05 e não pede pareamento. Quem conversa com ele é o painel, que procura pelo nome
`Zenith-Carrinho`. É por isso que existe `--procurar`: para você ver o que está no ar.

## 8. Próximo passo (quando quiser)

O rosto de verdade (o VRM 3D dela): hoje a tela desenha olhos e boca. Mandar o avatar
renderizado exigiria o PC desenhando e enviando quadro a quadro por BLE — dá, mas em 2 a 4
quadros por segundo, e é trabalho à parte. O que existe agora já dá cara, piscada e boca
falando sem depender de nada.
