# Receita — Zenith mexendo um pistão (atuador linear) pelo ESP32

> **Esqueleto NÃO testado em hardware.** Foi escrito a partir do que aparece no vídeo do Miyauti (Shogun → Bluetooth →
> ESP32 → pistão) e de práticas comuns. Teste **sem carga**, com a mão longe, com a fonte que você puder desligar rápido.
> Use `/modo eletronica`: ela guia a montagem uma etapa por vez e pode **olhar a mesa** com `/observar camera`.

## Segurança (leia antes de ligar qualquer coisa)
1. **O ESP32 não alimenta o pistão.** O pino dá miliamperes; o atuador pede de 1 a 10 A. Precisa de **driver** (ponte H de
   potência, ex.: **BTS7960**; L298N só serve pra atuadores pequenos) e **fonte externa** (ex.: 12 V compatível com o atuador).
2. **GND comum**: o GND da fonte, do driver e do ESP32 precisam estar ligados entre si.
3. **ESP32 é 3,3 V.** Nunca ligue 5 V direto num pino dele. O BTS7960 aceita sinal de 3,3 V no lado lógico (confira o seu módulo).
4. Primeiro **meça** (multímetro): tensão da fonte, polaridade, continuidade. Só depois ligue o atuador.
5. Atuador linear tem **fim de curso**: se ele bater no limite com o motor ainda ligado, a corrente dispara. O firmware abaixo
   limita cada movimento a 3 s (`MAX_MS`) — ajuste ao curso do SEU atuador, e use chaves fim-de-curso se tiver.
6. Tenha um jeito de **cortar a energia** à mão (chave geral/fonte com botão).

## Ligação (BTS7960 + ESP32 — confira o seu módulo)
| Módulo BTS7960 | ESP32 |
|---|---|
| RPWM | GPIO 25 |
| LPWM | GPIO 26 |
| R_EN e L_EN (juntos) | GPIO 27 |
| VCC (lógico) | 3V3 |
| GND (lógico) | GND |
| B+ / B− (potência) | + / − da fonte externa |
| M+ / M− | fios do atuador |

## Firmware (Arduino IDE, placa "ESP32 Dev Module"; Bluetooth clássico — não funciona em ESP32-S3/C3)
Comandos de texto, um por linha: `E1500` estende por 1500 ms · `R1000` recolhe por 1000 ms · `S` pára · `?` status.

```cpp
#include "BluetoothSerial.h"
BluetoothSerial SerialBT;

const int R_PWM = 25, L_PWM = 26, EN_PINS = 27;
const unsigned long MAX_MS = 3000;     // trava de segurança por movimento (ajuste ao curso do atuador)
unsigned long fimMov = 0;

void parar() { digitalWrite(R_PWM, LOW); digitalWrite(L_PWM, LOW); fimMov = 0; }

void mover(bool estender, unsigned long ms) {
  parar();
  if (ms == 0) return;
  if (ms > MAX_MS) ms = MAX_MS;
  digitalWrite(estender ? R_PWM : L_PWM, HIGH);
  fimMov = millis() + ms;
}

void setup() {
  pinMode(R_PWM, OUTPUT); pinMode(L_PWM, OUTPUT); pinMode(EN_PINS, OUTPUT);
  digitalWrite(EN_PINS, HIGH);
  parar();
  Serial.begin(115200);
  SerialBT.begin("Zenith-Pistao");      // aparece no pareamento do Windows
}

void tratar(Stream &s) {
  String c = s.readStringUntil('\n'); c.trim(); c.toUpperCase();
  if (c.length() == 0) return;
  if (c[0] == 'E' || c[0] == 'R') { mover(c[0] == 'E', c.substring(1).toInt()); s.println("OK mover"); }
  else if (c[0] == 'S') { parar(); s.println("OK parou"); }
  else if (c[0] == '?') { s.println(fimMov ? "movendo" : "parado"); }
  else s.println("comando desconhecido");
}

void loop() {
  if (fimMov && millis() >= fimMov) { parar(); SerialBT.println("OK fim do movimento"); }
  if (SerialBT.available()) tratar(SerialBT);
  if (Serial.available()) tratar(Serial);
}
```

## Pelo Windows
1. Pareie o "Zenith-Pistao" nas configurações de Bluetooth. O Windows cria uma porta **COM** (veja em *Mais opções de
   Bluetooth → Portas COM*, a de saída). Ou ligue por cabo USB e use a COM do ESP32.
2. Teste à mão primeiro (PuTTY ou o Monitor Serial): `E500`, `S`, `R500`.

## Pela Zenith
**Direto, sem habilidade** (uma vez só): `<conectar_serial>COM5;115200;E1500</conectar_serial>` — ela pede, você aprova.

**Como habilidade** (reutilizável): peça "cria uma habilidade pra controlar o pistão" e confira o código na janela. Algo assim:

```python
"""Controla o pistão (atuador linear) do ESP32 por Bluetooth/serial. Args: 'E 1500', 'R 1000', 'S' ou '?'."""
PORTA = "COM5"          # troque pela porta do seu ESP32
BAUD = 115200

def rodar(args: str = "") -> str:
    import serial
    partes = (args or "").upper().split()
    if not partes or partes[0] not in ("E", "R", "S", "?"):
        return "Uso: E <ms> | R <ms> | S | ?"
    ms = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 0
    ms = min(ms, 3000)                       # a trava de segurança também vale aqui
    cmd = partes[0] + (str(ms) if partes[0] in ("E", "R") else "")
    with serial.Serial(PORTA, BAUD, timeout=2) as porta:
        porta.write((cmd + "\n").encode())
        return porta.readline().decode(errors="replace").strip() or "(sem resposta do ESP32)"
```
Depois, `/habilidade confiar pistao` faz ela usar **sem pedir aprovação a cada movimento** — só faça isso depois de testar bem, e
lembre que `/pausar` e `/parar_observacao` continuam valendo.

## Ideia do vídeo: a IA empurrando o monstro no jogo
No vídeo o gatilho vem do jogo/chat. Aqui o caminho seria: `/observar tela` (ela vê o jogo) → ela decide → habilidade `pistao`.
Atenção: **automatizar ações num jogo online pode violar os termos de uso** (risco de banimento) — é decisão sua.
