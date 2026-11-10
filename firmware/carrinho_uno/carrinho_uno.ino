// ============================================================
//  CARRINHO DO ZENITH — programa do ARDUINO UNO (+ shield HW-130)
//
//  O Uno é as PERNAS: recebe uma linha de texto e anda.
//  Quem manda a linha é o ESP32-S3 (TX do ESP32 -> pino A0 do Uno).
//  Também dá para testar digitando no Monitor Serial (9600, "Nova linha").
//
//  FORMATO DA LINHA:      <letra> <milissegundos> <velocidade>
//     F 5000 140     frente por 5 segundos, velocidade 140
//     B 2000         trás por 2 s (velocidade padrão)
//     L 700          gira para a esquerda por 0,7 s
//     R 700          gira para a direita por 0,7 s
//     S              PARA tudo agora e apaga a fila
//
//  Os comandos entram numa FILA (até 6): "F 3000" e depois "R 700" =
//  anda 3 s e então gira. O carrinho mede o tempo SOZINHO: se o cabo
//  cair no meio, ele termina o passo e para. O motor nunca fica ligado
//  "para sempre" — não existe modo de andar indefinidamente.
//
//  Biblioteca necessária: "Adafruit Motor Shield library" (V1, AFMotor.h)
// ============================================================
#include <AFMotor.h>
#include <SoftwareSerial.h>

// ---------- AJUSTES (mexa só aqui) ----------
// ATENÇÃO: os motores deste carrinho são de 5 V e a bateria é de ~12 V.
// O shield entrega ~10 V nos motores; a velocidade (PWM) é o que segura isso.
// Por isso o teto é 150 (58%): média de ~6 V no motor. NÃO aumente VEL_MAX
// sem trocar a alimentação para 6 V (ver CARRINHO_MONTAGEM.md).
const int  VEL_PADRAO = 140;          // 0 a 255
const int  VEL_MAX    = 150;          // teto de segurança: o programa nunca passa disso
const unsigned int DUR_MAX_MS    = 10000;   // um passo nunca dura mais que 10 s
const unsigned int DUR_PADRAO_MS = 1000;
const unsigned int PAUSA_ENTRE_PASSOS_MS = 150;  // solta os motores um instante entre um passo e outro

// Qual motor é de qual lado (conforme a sua montagem): M1 e M2 = direita, M3 e M4 = esquerda
const bool LADO_DIREITO[4] = { true, true, false, false };
// Se uma roda girar ao contrário das outras, troque false -> true no motor dela (em vez de trocar os fios)
const bool INVERTER[4]     = { false, false, false, false };

// ---------- peças ----------
SoftwareSerial esp(A0, A1);           // RX = A0 (recebe do ESP32), TX = A1 (não usado)
AF_DCMotor m1(1), m2(2), m3(3), m4(4);
AF_DCMotor* motor[4] = { &m1, &m2, &m3, &m4 };

struct Passo { char c; unsigned int dur; byte vel; };
const byte MAX_FILA = 6;
Passo fila[MAX_FILA];
byte filaIni = 0, filaTam = 0;

bool andando = false;
unsigned long fimMs = 0;
unsigned long pausaAte = 0;

char bufEsp[24];  byte nEsp = 0;
char bufUsb[24];  byte nUsb = 0;

// dirDireita / dirEsquerda: +1 frente, -1 trás, 0 solto
void mover(int dirDireita, int dirEsquerda, int vel) {
  for (int i = 0; i < 4; i++) {
    int d = LADO_DIREITO[i] ? dirDireita : dirEsquerda;
    if (INVERTER[i]) d = -d;
    motor[i]->setSpeed(d == 0 ? 0 : vel);
    motor[i]->run(d > 0 ? FORWARD : (d < 0 ? BACKWARD : RELEASE));
  }
}

void pararMotores() { mover(0, 0, 0); }

void aplicar(const Passo& p) {
  switch (p.c) {
    case 'F': mover( 1,  1, p.vel); break;
    case 'B': mover(-1, -1, p.vel); break;
    case 'L': mover( 1, -1, p.vel); break;   // gira no lugar para a esquerda
    case 'R': mover(-1,  1, p.vel); break;   // gira no lugar para a direita
  }
}

void limparTudo() {
  filaTam = 0; filaIni = 0;
  andando = false;
  pausaAte = 0;
  pararMotores();
}

bool enfileirar(char c, unsigned int dur, byte vel) {
  if (filaTam >= MAX_FILA) return false;
  fila[(filaIni + filaTam) % MAX_FILA] = { c, dur, vel };
  filaTam++;
  return true;
}

void iniciarProximo() {
  Passo p = fila[filaIni];
  filaIni = (filaIni + 1) % MAX_FILA;
  filaTam--;
  aplicar(p);
  fimMs = millis() + p.dur;
  andando = true;
}

// Entende uma linha como "F 5000 140". Devolve true se virou ação.
bool interpretar(char* s) {
  while (*s == ' ') s++;
  char c = *s;
  if (c >= 'a' && c <= 'z') c -= 32;            // aceita minúscula

  if (c == 'S') { limparTudo(); Serial.println(F("PAROU")); return true; }
  if (c != 'F' && c != 'B' && c != 'L' && c != 'R') {
    Serial.print(F("IGNORADO: ")); Serial.println(s);
    return false;
  }

  long dur = DUR_PADRAO_MS, vel = VEL_PADRAO;
  char* p = s + 1;
  char* fim;
  long v1 = strtol(p, &fim, 10);
  if (fim != p) {
    dur = v1; p = fim;
    long v2 = strtol(p, &fim, 10);
    if (fim != p) vel = v2;
  }
  if (dur < 50) dur = 50;
  if (dur > DUR_MAX_MS) dur = DUR_MAX_MS;
  if (vel < 60) vel = 60;
  if (vel > VEL_MAX) vel = VEL_MAX;

  if (!enfileirar(c, (unsigned int)dur, (byte)vel)) {
    Serial.println(F("FILA CHEIA"));
    return false;
  }
  Serial.print(F("OK ")); Serial.print(c); Serial.print(' ');
  Serial.print(dur); Serial.print(' '); Serial.println(vel);
  return true;
}

// Lê caracteres de um Stream, monta a linha e executa quando chega o "enter"
void lerLinhas(Stream& entrada, char* buf, byte& n, byte tam) {
  while (entrada.available()) {
    char ch = entrada.read();
    if (ch == '\n' || ch == '\r') {
      if (n > 0) { buf[n] = 0; interpretar(buf); n = 0; }
    } else if (n < tam - 1) {
      buf[n++] = ch;
    } else {
      n = 0;                                     // linha comprida demais: joga fora
    }
  }
}

void setup() {
  Serial.begin(9600);
  esp.begin(9600);
  pararMotores();
  Serial.println(F("Carrinho pronto. Comandos: F/B/L/R <ms> [vel] | S"));
}

void loop() {
  lerLinhas(esp,    bufEsp, nEsp, sizeof(bufEsp));
  lerLinhas(Serial, bufUsb, nUsb, sizeof(bufUsb));

  unsigned long agora = millis();

  // terminou o passo atual?
  if (andando && (long)(agora - fimMs) >= 0) {
    andando = false;
    pararMotores();
    pausaAte = agora + PAUSA_ENTRE_PASSOS_MS;
  }
  // tem passo na fila e já passou a pausa?
  if (!andando && filaTam > 0 && (long)(agora - pausaAte) >= 0) {
    iniciarProximo();
  }
}
