/*
  Zenith TFT — ESP32-S3 + display SPI  (Zenith v24)

  O Zenith (Python) manda por USB o ROSTO da Zenith em JPEG (quadro a quadro) e este firmware desenha na TFT.
  >>> NÃO foi compilado nem testado em hardware por quem escreveu (sem ESP32 à mão). Se algo não compilar,
  >>> mande a mensagem de erro. Teste primeiro com "/tft teste" no Zenith (barras coloridas), antes do rosto.

  ── Arduino IDE ─────────────────────────────────────────────────────────────────────────────────────────
  Placa:   "ESP32S3 Dev Module"   (pacote "esp32" da Espressif, versão 3.x)
  Tools → USB CDC On Boot: "Enabled"      ← IMPORTANTE: faz o Serial ser a porta USB nativa
  Tools → USB Mode: "Hardware CDC and JTAG"   (padrão)
  Bibliotecas (Gerenciar Bibliotecas):  Adafruit GFX Library · Adafruit ST7789 (ou ILI9341 / ST7735, conforme o seu display)
                                        · TJpg_Decoder (Bodmer)
  Envie o sketch pela porta USB da placa; depois é só deixá-la plugada: o Zenith acha sozinho.

  ── Protocolo (USB serial) ──────────────────────────────────────────────────────────────────────────────
  PC → placa : "ZENITH?\n"                        placa → PC : "ZENITH-TFT 1 LARGURAxALTURA\n"
  PC → placa : 'Z' 'J' + tamanho (4 bytes, little-endian) + JPEG      placa → PC : "K\n" (ok) ou "E\n" (erro)
*/

#include <SPI.h>
#include <Adafruit_GFX.h>
#include <TJpg_Decoder.h>

// ---------- Escolha o controlador do SEU display (deixe só UMA linha ligada) ----------
#define DRIVER_ST7789         // o mais comum em módulos de 5 fios (CS/DC/RST/SCK/MOSI): 1.3" 1.54" 1.69" 2.0" (240x240 ou 240x320)
// #define DRIVER_ILI9341    // 2.2" 2.4" 2.8" 3.2" (240x320)
// #define DRIVER_ST7735     // 1.44" 1.8" (128x128 ou 128x160)

// ---------- Tamanho e rotação (confira no vendedor/datasheet do seu módulo) ----------
#define TFT_LARGURA 240
#define TFT_ALTURA  240       // 240x240 → 240 · 240x320 → 320 (se girar, troque as duas) · ST7735: 128 / 160
#define TFT_ROTACAO 0         // 0..3 — gire até o rosto ficar em pé

// ---------- Pinos TFT (SUA montagem atual no ESP32-S3) ----------
#define TFT_CS    8
#define TFT_RST   10
#define TFT_DC    9
#define PIN_SCK   12
#define PIN_MOSI  11
#define PIN_MISO  -1          // o display só recebe
// Backlight (pino BL/LED do módulo): se NÃO estiver ligado direto no 3V3, descomente e ajuste o pino:
// #define PIN_BL 14

// Se as CORES saírem trocadas (vermelho↔azul, tons estranhos), mude para true:
#define TJPG_TROCAR_BYTES false

// AJUSTADO PARA O SEU DISPLAY (FUNCIONOU NO TESTE):
#define SPI_MODO_ST7789 SPI_MODE3

#if defined(DRIVER_ST7789)
  #include <Adafruit_ST7789.h>
  Adafruit_ST7789 tft = Adafruit_ST7789(&SPI, TFT_CS, TFT_DC, TFT_RST);
#elif defined(DRIVER_ILI9341)
  #include <Adafruit_ILI9341.h>
  Adafruit_ILI9341 tft = Adafruit_ILI9341(&SPI, TFT_DC, TFT_CS, TFT_RST);
#elif defined(DRIVER_ST7735)
  #include <Adafruit_ST7735.h>
  Adafruit_ST7735 tft = Adafruit_ST7735(&SPI, TFT_CS, TFT_DC, TFT_RST);
#else
  #error "Escolha um DRIVER_* no topo do arquivo"
#endif

const size_t MAX_JPEG = 90000;       // tem que ser >= ao do Zenith (brain/zenith_tft.py: MAX_JPEG)
uint8_t *bufJpeg = nullptr;
unsigned long ultimoQuadro = 0;
bool mostrouSemSinal = false;

// Chamada pelo decodificador a cada bloco de pixels já decodificado
bool saidaJpeg(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t *bitmap) {
  if (y >= tft.height()) return false;
  tft.drawRGBBitmap(x, y, bitmap, w, h);
  return true;
}

void telaDeTexto(const char *l1, const char *l2) {
  tft.fillScreen(0x0000);
  tft.setTextColor(0xFFFF);
  tft.setTextSize(2);
  tft.setCursor(10, tft.height() / 2 - 24);
  tft.print(l1);
  tft.setTextSize(1);
  tft.setTextColor(0xBDF7);
  tft.setCursor(10, tft.height() / 2 + 4);
  tft.print(l2);
}

void setup() {
#ifdef PIN_BL
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, HIGH);
#endif
  Serial.setRxBufferSize(32768);       // cabe um quadro inteiro enquanto a gente desenha o anterior
  Serial.begin(115200);                // na USB nativa o número é ignorado; sem 'while(!Serial)': não trava sem PC
  Serial.setTimeout(600);

  // AJUSTADO PARA O SEU DISPLAY (CS passado como -1 para evitar conflito na inicialização)
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);

#if defined(DRIVER_ST7789)
  tft.init(TFT_LARGURA, TFT_ALTURA, SPI_MODO_ST7789);
#elif defined(DRIVER_ILI9341)
  tft.begin();
#elif defined(DRIVER_ST7735)
  tft.initR(INITR_BLACKTAB);            // se as cores/bordas ficarem estranhas, tente INITR_GREENTAB ou INITR_REDTAB
#endif
  tft.setRotation(TFT_ROTACAO);
  tft.fillScreen(0x0000);

  bufJpeg = (uint8_t *)(psramFound() ? ps_malloc(MAX_JPEG) : malloc(MAX_JPEG));
  TJpgDec.setJpgScale(1);
  TJpgDec.setSwapBytes(TJPG_TROCAR_BYTES);
  TJpgDec.setCallback(saidaJpeg);

  telaDeTexto("Zenith", "Aguardando o Zenith...");
  ultimoQuadro = millis();
}

// lê N bytes com limite de tempo; devolve quantos leu
size_t lerExato(uint8_t *dst, size_t n) {
  size_t lidos = 0;
  unsigned long limite = millis() + 800;
  while (lidos < n && millis() < limite) {
    int disp = Serial.available();
    if (disp > 0) {
      size_t quer = min((size_t)disp, n - lidos);
      lidos += Serial.readBytes(dst + lidos, quer);
      limite = millis() + 800;         // enquanto chega dado, renova o prazo
    } else {
      delay(1);
    }
  }
  return lidos;
}

void tratarQuadro() {
  uint8_t cab[4];
  if (lerExato(cab, 4) != 4) { Serial.print("E\n"); return; }
  uint32_t n = (uint32_t)cab[0] | ((uint32_t)cab[1] << 8) | ((uint32_t)cab[2] << 16) | ((uint32_t)cab[3] << 24);
  if (n == 0 || n > MAX_JPEG || bufJpeg == nullptr) {
    // tamanho absurdo: esvazia o que chegou pra ressincronizar
    while (Serial.available()) Serial.read();
    Serial.print("E\n");
    return;
  }
  if (lerExato(bufJpeg, n) != n) { Serial.print("E\n"); return; }
  uint16_t rc = TJpgDec.drawJpg(0, 0, bufJpeg, n);
  Serial.print(rc == 0 ? "K\n" : "E\n");
  ultimoQuadro = millis();
  mostrouSemSinal = false;
}

void responderAperto() {
  while (Serial.available()) {          // consome o resto da linha "ZENITH?\n"
    if (Serial.read() == '\n') break;
  }
  Serial.printf("ZENITH-TFT 1 %dx%d\n", tft.width(), tft.height());
}

void loop() {
  while (Serial.available()) {
    int b = Serial.read();
    if (b != 'Z') continue;             // procura o começo de um comando
    unsigned long limite = millis() + 100;
    while (!Serial.available() && millis() < limite) delay(1);
    int c = Serial.read();
    if (c == 'J') tratarQuadro();       // 'Z''J' = quadro JPEG
    else if (c == 'E') responderAperto();  // 'Z''E''N''I''T''H''?' = aperto de mão
  }
  // sem quadros por 6 s depois de já ter mostrado algo: avisa
  if (!mostrouSemSinal && millis() - ultimoQuadro > 6000) {
    telaDeTexto("Zenith", "Sem sinal do Zenith");
    mostrouSemSinal = true;
  }
}