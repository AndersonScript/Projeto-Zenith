// ============================================================
//  CARRINHO DO ZENITH — ESP32-S3   (v1.5 · base: a SUA v1.4)
//
//  O que é igual à sua v1.4: tela 128x160 (mesma inicialização que funcionou), rostinho,
//  Bluetooth BLE (Nordic UART), página de controle, USB, comandos F/B/L/R/S/ROSTO/PING,
//  e a ponte para o Uno pelo TX (GPIO 17).
//
//  O que é NOVO na v1.5:
//   1) A VRM de verdade na tela: o Zenith manda o corpo/rosto da VRM (JPEG) por Wi-Fi e o
//      ESP32 desenha. O rostinho simples vira RESERVA (aparece quando o Zenith não está lá).
//   2) Wi-Fi inteligente (a sua ideia):
//        - 1ª vez (ou se a rede sumiu): o ESP32 CRIA a rede "Zenith_Carrinho";
//          o celular abre a página sozinho e você escolhe o Wi-Fi (o do celular, o da escola...) e a senha.
//        - Ele ENTRA nesse Wi-Fi e SALVA. Nas próximas vezes entra sozinho.
//        - Quando percebe que o computador com o Zenith está lá, APAGA a rede dele.
//        - Segure o botão BOOT por 3 s para esquecer as redes e configurar de novo.
//   3) O Zenith acha o carrinho sozinho (ele "grita" na rede: UDP 7778), sem digitar IP.
//   4) A telinha mostra o que está acontecendo: Wi-Fi, IP e se o Zenith está conectado.
//
//  CANAIS (os comandos de texto são os mesmos em todos):
//    Wi-Fi  http://IP/cmd?c=F 1000 140   (ou  /cmd?c=F&t=1000&v=140  e  /parar)
//    BLE    painel do PC (opcional: veja USAR_BLE)
//    USB    Monitor Serial
//    VRM    TCP porta 7777 (só o Zenith usa)
//     F 5000 140  frente · B 2000 trás · L 700 esquerda · R 700 direita · S para
//     ROSTO feliz · PING
//
//  ── Arduino IDE ────────────────────────────────────────────────────────────
//  Placa ESP32S3 Dev Module · pacote esp32 3.x · USB CDC On Boot = Enabled
//  Bibliotecas: Adafruit GFX · Adafruit ST7735 and ST7789 Library · TJpg_Decoder (Bodmer; só para a VRM)
//  Se der "Sketch too big": Ferramentas > Partition Scheme > "Huge APP (3MB No OTA...)"
//  NÃO foi compilado nem testado em hardware por quem escreveu. Se não compilar, mande a mensagem inteira.
// ============================================================
#include <Arduino.h>
#include <freertos/queue.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <nvs_flash.h>            // reset de fábrica: apaga a memória que guarda redes e pareamento

#define USAR_BLE 1        // 1 = Bluetooth ligado (como na v1.4) · 0 = desliga (se atrapalhar o Wi-Fi ou não conectar)
#define TEM_VRM  1        // 1 = recebe a VRM do Zenith (precisa da biblioteca TJpg_Decoder) · 0 = só o rostinho

#if USAR_BLE
  #include <BLEDevice.h>
  #include <BLEServer.h>
  #include <BLEUtils.h>
  #include <BLE2902.h>
#endif
#if TEM_VRM
  #include <TJpg_Decoder.h>
#endif

#define VERSAO "1.5"

// ╔══════════════════════ VOCÊ SÓ MEXE AQUI (se quiser) ══════════════════════╗
const char *CHAVE = "";            // vazio = qualquer um na rede manda no carrinho. Em rede de escola, ponha uma palavra
const char *AP_SENHA = "";         // vazio = a rede "Zenith_Carrinho" é aberta (como na v1.4). Com senha: 8+ caracteres
// (o nome e a senha do Wi-Fi onde ele vai entrar você coloca PELO CELULAR, na página. Não precisa mexer no código.)
// ╚════════════════════════════════════════════════════════════════════════════╝

// ---------- ligação com o Uno ----------
const int PIN_UNO_TX = 17;     // ESP32 TX -> A0 do Uno
const int PIN_UNO_RX = 18;     // reservado

// ---------- limites ----------
const long DUR_PADRAO = 1000;
const long DUR_MAX_MS = 10000;
const int  VEL_PADRAO = 140;
const int  VEL_MAX    = 150;

// ---------- Bluetooth (Nordic UART: é o que o painel procura) ----------
#define NOME_BT      "Zenith_Carrinho"
#define UUID_SERVICO "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define UUID_RX      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   // PC escreve aqui
#define UUID_TX      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   // carrinho responde aqui
#define POTENCIA_BT  ESP_PWR_LVL_P9

// ---------- Wi-Fi ----------
#define NOME_WIFI "Zenith_Carrinho"                 // a rede que o ESP32 CRIA para você configurar
const char *AP_SSID = NOME_WIFI;
const char *NOME_NA_REDE = "carrinho";              // vira  carrinho.local  quando está num Wi-Fi
const uint16_t PORTA_ROSTO = 7777;                  // o Zenith manda a VRM aqui (TCP)
const uint16_t PORTA_DESCOBERTA = 7778;             // o carrinho avisa "estou aqui" (UDP)
const int PIN_BOTAO_RESET = 0;                      // botão BOOT: segure 3 s = esquecer as redes salvas
const int MAX_REDES = 4;

// ============================================================
//  TELA (a mesma inicialização da sua v1.4)
// ============================================================
#define TEM_TELA 1

#if TEM_TELA
  #include <SPI.h>
  #include <Adafruit_GFX.h>
  #include <Adafruit_ST7735.h>

  #define TFT_CS    8
  #define TFT_RST  10
  #define TFT_DC    9
  #define TFT_SCK  12
  #define TFT_MOSI 11
  #define TFT_TAB 0          // 0 = BLACKTAB · 1 = GREENTAB · 2 = REDTAB
  #define TESTE_TELA 1       // 1 = barras de cor por 1,5 s ao ligar
  #define TFT_MHZ 10000000   // fio de jumper comprido não aguenta 15 MHz

  Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

  const uint16_t COR_FUNDO = 0x0861;
  const uint16_t COR_OLHO  = 0xFBE0;
  const uint16_t COR_APAGA = 0x7BEF;
  const uint16_t COR_OK    = 0x07E0;
  const uint16_t COR_ATENCAO = 0xFFE0;
#endif
#define TJPG_TROCAR_BYTES false   // cores trocadas (vermelho<->azul) na VRM? mude para true

// ---------- estado do rostinho / comandos ----------
int  rosto = 0;                     // 0 normal · 1 feliz · 2 pensando · 3 falando
bool olhosFechados = false;
unsigned long proxPiscar = 0;
unsigned long fimPiscada = 0;
unsigned long ultimoDesenho = 0;
String ultimoComando = "aguardando";
unsigned long ultimoComandoEm = 0;

char bufLinha[64];
byte nLinha = 0;

// ---------- Bluetooth ----------
#if USAR_BLE
BLECharacteristic *pTx = nullptr;
BLEAdvertising *pAnuncio = nullptr;
QueueHandle_t filaBle = nullptr;
volatile int  conexoes = 0;
volatile bool evConectou = false;
volatile bool evDesconectou = false;
unsigned long proxAnuncio = 0;
unsigned long helloEm = 0;
#endif
volatile bool btConectado = false;

// ---------- rede ----------
Preferences prefs;
WebServer web(80);
DNSServer dns;
WiFiUDP udp;
WiFiServer servidorRosto(PORTA_ROSTO);
WiFiClient clienteRosto;

String redeSsid[MAX_REDES];
String redeSenha[MAX_REDES];
int nRedes = 0;
bool apLigado = false;                 // a rede "Zenith_Carrinho" está no ar
bool staOk = false;                    // estamos dentro de um Wi-Fi
String ssidAtual = "";
String listaVisivel = "";              // <option> das redes vistas no boot (para a página /rede)
unsigned long tentativaDesde = 0;      // quando começou a tentar entrar numa rede (0 = não está tentando)
bool tentativaCega = false;            // 01/11: tentando uma rede salva que a varredura NÃO viu (SSID oculto)
unsigned long reiniciarEm = 0;
unsigned long resetEm = 0;              // reset de fábrica pedido pela página (só depois de responder)

// ---------- Zenith / VRM ----------
bool zenithConectado = false;
bool zenithViaAP = false;
unsigned long zenithDesde = 0;
unsigned long ultimoQuadro = 0;
unsigned long quadros = 0;
bool modoVrm = false;                  // true enquanto chegam quadros da VRM
unsigned long segurarTelaAte = 0;      // enquanto não passar, não desenha quadros (mostra um aviso)
bool precisaRedesenhar = false;
String rodapeAtual = "";
const size_t MAX_JPEG = 32000;         // a VRM em 128x160 pesa 3-12 KB
uint8_t *bufJpeg = nullptr;

bool podeConfigurarRede();
void toastTela(const String &l1, const String &l2);
void resetDeFabrica();

// ============================================================
//  PÁGINA DE CONTROLE
// ============================================================
const char PAGINA[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>Carrinho Zenith</title>
<style>
body{margin:0;padding:14px;background:#10141c;color:#e8edf5;font-family:system-ui,sans-serif;text-align:center;touch-action:manipulation}
h1{font-size:20px;margin:4px 0 14px}
.g{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;max-width:340px;margin:0 auto 16px}
button{border:0;border-radius:14px;padding:22px 0;font-size:26px;font-weight:700;background:#f5a623;color:#111}
button:active{filter:brightness(.75)}
.p{background:#e5484d;color:#fff;font-size:17px}
.f{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:14px 0}
.f button{padding:10px 14px;font-size:15px;background:#2a3550;color:#e8edf5}
label{display:block;margin:10px auto;max-width:340px;font-size:14px;color:#9fb0c9}
input{width:100%}
#s{min-height:20px;color:#7ee0a0;font-size:14px}
#r{margin:14px auto 4px;max-width:340px;font-size:13px;color:#9fb0c9;line-height:1.6}
a{color:#f5a623}
</style></head><body>
<h1>Carrinho Zenith</h1>
<div class="g">
<span></span><button onclick="m('F')">▲</button><span></span>
<button onclick="m('L')">◀</button><button class="p" onclick="c('S')">PARAR</button><button onclick="m('R')">▶</button>
<span></span><button onclick="m('B')">▼</button><span></span>
</div>
<label>Duração: <b id="dv">700</b> ms
<input id="d" type="range" min="200" max="3000" step="100" value="700" oninput="$('dv').textContent=this.value"></label>
<label>Velocidade: <b id="vv">140</b>
<input id="v" type="range" min="60" max="150" step="5" value="140" oninput="$('vv').textContent=this.value"></label>
<div class="f">
<button onclick="c('ROSTO normal')">normal</button><button onclick="c('ROSTO feliz')">feliz</button>
<button onclick="c('ROSTO pensando')">pensando</button><button onclick="c('ROSTO falando')">falando</button>
</div>
<label id="kk" style="display:none">Chave: <input id="k" type="password"></label>
<div id="s"></div>
<div id="r">verificando...</div>
<p><a href="/rede">Conectar a um Wi-Fi</a></p>
<div class="f"><button style="background:#3a2030;color:#ff9aa8" onclick="resetFab()">Reset de tudo</button></div>
<script>
function resetFab(){
  if(!confirm('Reset de TUDO: apaga as redes salvas e o pareamento Bluetooth. O carrinho reinicia sozinho. Continuar?'))return;
  fetch('/reset?confirma=sim').then(r=>r.text()).then(t=>{document.body.innerHTML='<div style="font-family:system-ui;background:#10141c;color:#e8edf5;padding:20px">'+t+'</div>'});
}
</script>
<script>
const $=i=>document.getElementById(i);
function c(x){
  const k=$('k').value;
  fetch('/cmd?c='+encodeURIComponent(x)+(k?'&k='+encodeURIComponent(k):'')).then(r=>r.text())
    .then(t=>$('s').textContent=x+' → '+t)
    .catch(()=>$('s').textContent='sem conexão com o carrinho');
}
function m(k){c(k+' '+$('d').value+' '+$('v').value)}
function st(){
  fetch('/status').then(r=>r.json()).then(j=>{
    if(j.chave)$('kk').style.display='block';
    $('r').innerHTML=
      (j.tela?'✓':'✗')+' Tela &nbsp; '+
      (j.wifi?'✓ Wi-Fi: '+j.wifi+' ('+j.ip+')':'⚠ sem Wi-Fi (rede própria '+(j.ap?'ligada':'desligada')+')')+'<br>'+
      (j.zenith?'✓ Zenith conectado ('+j.quadros+' quadros)':'⚠ Zenith não conectado')+' &nbsp; '+
      (j.ble?'✓ Bluetooth':'· Bluetooth livre');
  }).catch(()=>{$('r').textContent='sem resposta do carrinho'});
}
st();setInterval(st,3000);
</script></body></html>
)rawliteral";

// ============================================================
//  TELA
// ============================================================
#if TEM_TELA
void desenharOlhos(bool fechado, int deslocaY) {
  tft.fillRect(24, 42, 80, 48, COR_FUNDO);
  if (fechado) {
    tft.fillRoundRect(30, 64, 26, 5, 2, COR_OLHO);
    tft.fillRoundRect(72, 64, 26, 5, 2, COR_OLHO);
  } else {
    tft.fillRoundRect(30, 46, 26, 38, 9, COR_OLHO);
    tft.fillRoundRect(72, 46, 26, 38, 9, COR_OLHO);
    tft.fillCircle(43, 65 + deslocaY, 6, COR_FUNDO);
    tft.fillCircle(85, 65 + deslocaY, 6, COR_FUNDO);
  }
}

void desenharBoca(int estado, unsigned long agora) {
  tft.fillRect(38, 92, 52, 30, COR_FUNDO);
  switch (estado) {
    case 1:
      tft.fillRect(44, 96, 8, 5, COR_OLHO);
      tft.fillRect(52, 101, 24, 5, COR_OLHO);
      tft.fillRect(76, 96, 8, 5, COR_OLHO);
      break;
    case 2:
      tft.fillRect(52, 102, 20, 5, COR_OLHO);
      break;
    case 3: {
      int h = 5 + (int)((agora / 110) % 3) * 5;
      tft.fillRoundRect(52, 100, 24, h, 3, COR_OLHO);
      break;
    }
    default:
      tft.fillRoundRect(54, 102, 20, 5, 2, COR_OLHO);
  }
}

// rodapé do rostinho: duas linhas (21 letras cada)
void mostrarRodape(const String &l1, const String &l2) {
  String chave = l1 + "|" + l2;
  if (chave == rodapeAtual) return;
  rodapeAtual = chave;
  tft.fillRect(0, 128, 128, 32, COR_FUNDO);
  tft.setTextSize(1);
  tft.setTextColor(COR_APAGA, COR_FUNDO);
  tft.setCursor(4, 132);
  tft.print(l1.substring(0, 21));
  tft.setCursor(4, 146);
  tft.print(l2.substring(0, 21));
}

void testeDeCores() {
  tft.fillRect(0,   0, 32, 160, 0xF800);
  tft.fillRect(32,  0, 32, 160, 0x07E0);
  tft.fillRect(64,  0, 32, 160, 0x001F);
  tft.fillRect(96,  0, 32, 160, 0xFFFF);
  delay(1500);
}

void telaInicio() {
  tft.fillScreen(COR_FUNDO);
  desenharOlhos(false, 0);
  desenharBoca(rosto, millis());
  rodapeAtual = "";
}

// aviso de tela cheia (ex.: "Wi-Fi conectado!"); segura os quadros da VRM por 1,8 s
void toastTela(const String &l1, const String &l2) {
  tft.fillScreen(0x0000);
  tft.setTextWrap(false);
  tft.setTextSize(1);
  tft.setTextColor(COR_OK);
  tft.setCursor(6, 56);
  tft.print(l1.substring(0, 21));
  tft.setTextColor(0xFFFF);
  tft.setCursor(6, 76);
  tft.print(l2.substring(0, 21));
  segurarTelaAte = millis() + 1800;
  precisaRedesenhar = true;
}

String ipTexto() {
  if (staOk) return WiFi.localIP().toString();
  if (apLigado) return WiFi.softAPIP().toString();
  return String("-");
}

void atualizarTela() {
  unsigned long agora = millis();

  if ((long)(agora - segurarTelaAte) < 0) return;          // aviso na tela: não mexe

  if (modoVrm) {                                           // a VRM do Zenith está chegando: ela manda na tela
    if (agora - ultimoQuadro > 4000) { modoVrm = false; telaInicio(); }
    return;
  }
  if (precisaRedesenhar) { precisaRedesenhar = false; telaInicio(); }

  if (!olhosFechados && (long)(agora - proxPiscar) >= 0) {
    olhosFechados = true;
    fimPiscada = agora + 130;
    desenharOlhos(true, 0);
  } else if (olhosFechados && (long)(agora - fimPiscada) >= 0) {
    olhosFechados = false;
    proxPiscar = agora + 2600 + (millis() % 2800);
    desenharOlhos(false, rosto == 2 ? -4 : 0);
  }

  if (rosto == 3 && agora - ultimoDesenho > 90) {
    ultimoDesenho = agora;
    desenharBoca(3, agora);
  }

  static unsigned long ultimoRodape = 0;
  if (agora - ultimoRodape > 400) {
    ultimoRodape = agora;
    String l1, l2;
    if (staOk)        l1 = "Wi-Fi " + ssidAtual;
    else if (apLigado) l1 = "Rede " + String(AP_SSID);
    else if (tentativaDesde) l1 = "Entrando no Wi-Fi...";
    else              l1 = "Sem rede";
    if (agora - ultimoComandoEm < 4000 && ultimoComandoEm != 0) l2 = ultimoComando;
    else l2 = ipTexto() + (zenithConectado ? " PC ok" : " PC --");
    mostrarRodape(l1, l2);
  }
}
#endif

// ============================================================
//  RESPOSTA (volta para BLE e USB). Só é chamada pelo loop().
// ============================================================
void avisar(const char *texto) {
  Serial.println(texto);
#if USAR_BLE
  if (pTx && btConectado) {
    pTx->setValue((uint8_t *)texto, strlen(texto));
    pTx->notify();
  }
#endif
}

// ============================================================
//  PONTE PARA O UNO + comandos
// ============================================================
void enviarUno(const char *linha) {
  Serial1.print(linha);
  Serial1.print('\n');
  char resp[40];
  snprintf(resp, sizeof(resp), "OK %s", linha);
  avisar(resp);
}

void mudarRosto(String nome) {
  nome.trim();
  nome.toLowerCase();
  if (nome == "feliz")         rosto = 1;
  else if (nome == "pensando") rosto = 2;
  else if (nome == "falando")  rosto = 3;
  else                         rosto = 0;
#if TEM_TELA
  if (!modoVrm) {
    desenharBoca(rosto, millis());
    desenharOlhos(false, rosto == 2 ? -4 : 0);
  }
#endif
  char resp[32];
  snprintf(resp, sizeof(resp), "OK rosto %s", nome.c_str());
  avisar(resp);
}

void processarLinha(String linha) {
  linha.trim();
  if (linha.length() == 0) return;

  String cima = linha;
  cima.toUpperCase();

  if (cima == "PING") { avisar("PONG " VERSAO); return; }

  // Reset pelo USB/painel (último recurso quando nem a rede nem a página respondem)
  if (cima == "RESET" || cima == "RESET TUDO" || cima == "FORMATAR") {
    avisar("RESET DE FABRICA em 2 s");
    resetDeFabrica();
    return;
  }
  if (cima == "RESET REDES") {
    limparRedes();
    avisar("redes apagadas — reiniciando");
    reiniciarEm = millis() + 1200;
    return;
  }

  if (cima.startsWith("ROSTO")) { mudarRosto(linha.substring(5)); return; }

  if (cima == "S" || cima == "PARAR" || cima == "STOP") {
    enviarUno("S");
    ultimoComando = "PARAR";
    ultimoComandoEm = millis();
    return;
  }

  char c = cima[0];
  if (c != 'F' && c != 'B' && c != 'L' && c != 'R') {
    char resp[48];
    snprintf(resp, sizeof(resp), "ERRO comando: %s", linha.c_str());
    avisar(resp);
    return;
  }

  long dur = 0, vel = 0;
  int lidos = sscanf(cima.c_str() + 1, "%ld %ld", &dur, &vel);
  if (lidos < 1) { dur = DUR_PADRAO; }
  if (lidos < 2) { vel = VEL_PADRAO; }
  if (dur < 50)  { dur = 50; }
  if (dur > DUR_MAX_MS) { dur = DUR_MAX_MS; }
  if (vel < 60)  { vel = 60; }
  if (vel > VEL_MAX)    { vel = VEL_MAX; }

  char cmd[24];
  snprintf(cmd, sizeof(cmd), "%c %ld %ld", c, dur, vel);
  enviarUno(cmd);
  ultimoComando = cmd;
  ultimoComandoEm = millis();
}

void alimentar(char ch) {
  if (ch == '\n' || ch == '\r') {
    if (nLinha > 0) {
      bufLinha[nLinha] = 0;
      processarLinha(String(bufLinha));
      nLinha = 0;
    }
  } else if (nLinha < sizeof(bufLinha) - 1) {
    bufLinha[nLinha++] = ch;
  } else {
    nLinha = 0;
  }
}

void lerDoUsb() {
  while (Serial.available()) alimentar((char)Serial.read());
}

#if USAR_BLE
void lerDoBle() {
  char ch;
  while (xQueueReceive(filaBle, &ch, 0) == pdTRUE) alimentar(ch);
}

// ============================================================
//  BLUETOOTH (igual à sua v1.4). Os callbacks só guardam bytes / levantam bandeiras.
// ============================================================
class CallbackRx : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) {
    uint8_t *d = c->getData();
    size_t n = c->getLength();
    for (size_t i = 0; i < n; i++) {
      char ch = (char)d[i];
      xQueueSend(filaBle, &ch, 0);
    }
  }
};

class CallbackServidor : public BLEServerCallbacks {
  void onConnect(BLEServer *s) {
    conexoes = conexoes + 1;
    btConectado = true;
    evConectou = true;
  }
  void onDisconnect(BLEServer *s) {
    if (conexoes > 0) conexoes = conexoes - 1;
    btConectado = (conexoes > 0);
    evDesconectou = true;
  }
};

void iniciarBluetooth() {
  BLEDevice::init(NOME_BT);
  BLEDevice::setPower(POTENCIA_BT);
  BLEDevice::setMTU(128);              // linhas de comando cabem inteiras de uma vez

  BLEServer *pServidor = BLEDevice::createServer();
  pServidor->setCallbacks(new CallbackServidor());

  BLEService *pServico = pServidor->createService(UUID_SERVICO);

  BLECharacteristic *pRx = pServico->createCharacteristic(
      UUID_RX, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  pRx->setCallbacks(new CallbackRx());

  pTx = pServico->createCharacteristic(UUID_TX, BLECharacteristic::PROPERTY_NOTIFY);
  pTx->addDescriptor(new BLE2902());

  pServico->start();

  pAnuncio = pServidor->getAdvertising();
  pAnuncio->addServiceUUID(UUID_SERVICO);
  pAnuncio->setName(NOME_BT);          // sem isto, alguns PCs não mostram o nome na busca
  pAnuncio->setMinInterval(0x20);      // anuncia mais rápido = o painel acha em segundos
  pAnuncio->setMaxInterval(0x40);
  pAnuncio->setScanResponse(true);
  pAnuncio->start();
  Serial.println("[BT] anunciando como " NOME_BT);
}

void tratarEventosBle() {
  unsigned long agora = millis();

  if (evConectou) {
    evConectou = false;
    Serial.println("[BT] PC conectado");
    helloEm = agora + 1200;
    proxAnuncio = agora + 300;
  }
  if (evDesconectou) {
    evDesconectou = false;
    Serial.println("[BT] PC desconectou");
    if (!btConectado) Serial1.print("S\n");
    proxAnuncio = agora + 300;
  }
  if (helloEm != 0 && (long)(agora - helloEm) >= 0) {
    helloEm = 0;
    if (btConectado) avisar("ZENITH-CARRINHO " VERSAO);
  }
  if (proxAnuncio != 0 && (long)(agora - proxAnuncio) >= 0) {
    proxAnuncio = 0;
    pAnuncio->start();
  }
  static unsigned long ultimaGarantia = 0;
  if (!btConectado && agora - ultimaGarantia > 10000) {
    ultimaGarantia = agora;
    pAnuncio->start();
  }
}
#endif

// ============================================================
//  REDES SALVAS (guardadas na memória do ESP32: sobrevivem a desligar)
// ============================================================
String chaveNome(const char *prefixo, int i) { return String(prefixo) + String(i); }

void carregarRedes() {
  nRedes = 0;
  prefs.begin("rede", true);
  for (int i = 0; i < MAX_REDES; i++) {
    String s = prefs.getString(chaveNome("s", i).c_str(), "");
    if (s.length() == 0) continue;
    redeSsid[nRedes] = s;
    redeSenha[nRedes] = prefs.getString(chaveNome("p", i).c_str(), "");
    nRedes++;
  }
  prefs.end();
}

// a rede nova vai para o 1º lugar; repetidas somem; guarda no máximo MAX_REDES
void salvarRede(const String &ssid, const String &senha) {
  String s[MAX_REDES], p[MAX_REDES];
  int n = 0;
  s[n] = ssid; p[n] = senha; n++;
  for (int i = 0; i < nRedes && n < MAX_REDES; i++) {
    if (redeSsid[i] == ssid) continue;
    s[n] = redeSsid[i]; p[n] = redeSenha[i]; n++;
  }
  prefs.begin("rede", false);
  for (int i = 0; i < MAX_REDES; i++) {
    prefs.putString(chaveNome("s", i).c_str(), i < n ? s[i] : String(""));
    prefs.putString(chaveNome("p", i).c_str(), i < n ? p[i] : String(""));
  }
  prefs.end();
  carregarRedes();
}

void limparRedes() {
  prefs.begin("rede", false);
  prefs.clear();
  prefs.end();
  nRedes = 0;
}

String htmlSeguro(String t) {
  t.replace("&", "&amp;"); t.replace("<", "&lt;"); t.replace(">", "&gt;"); t.replace("\"", "&quot;");
  return t;
}

String jsonSeguro(String t) {
  t.replace("\\", " "); t.replace("\"", "'");
  return t;
}

// ============================================================
//  WI-FI
// ============================================================
// 01/11 — diagnóstico: traduz o tipo de segurança que a varredura devolveu
// (é isso que explica "funciona no Wi-Fi de casa e não no hotspot do celular").
const char *wifiTipo(wifi_auth_mode_t t) {
  switch (t) {
    case WIFI_AUTH_OPEN:            return "aberta";
    case WIFI_AUTH_WEP:             return "WEP";
    case WIFI_AUTH_WPA_PSK:         return "WPA";
    case WIFI_AUTH_WPA2_PSK:        return "WPA2";
    case WIFI_AUTH_WPA_WPA2_PSK:    return "WPA/WPA2";
    case WIFI_AUTH_WPA3_PSK:        return "WPA3 (o ESP32 NAO entra)";
    case WIFI_AUTH_WPA2_WPA3_PSK:   return "WPA2/WPA3 (pode falhar)";
    case WIFI_AUTH_ENTERPRISE:      return "WPA-Enterprise";
    default:                        return "outra";
  }
}

// Procura redes. Enche listaVisivel e devolve o índice da conhecida com melhor sinal (ou -1).
int escanearEEscolher() {
  WiFi.mode(WIFI_STA);
  int achadas = WiFi.scanNetworks();
  if (achadas < 0) achadas = 0;
  // Log no Monitor Serial (115200): mostra EXATAMENTE o que a placa vê — canal, sinal e segurança.
  // É aqui que aparece se o hotspot do celular está em 5 GHz (canal 36+), em WPA3 ou invisível.
  Serial.printf("[WIFI] varredura: %d redes\n", achadas);
  for (int j = 0; j < achadas && j < 15; j++) {
    String nome = WiFi.SSID(j);
    Serial.printf("   %2d) %-24s canal %2d  sinal %4d  %s\n", j + 1,
                  nome.length() ? nome.c_str() : "(oculta)",
                  WiFi.channel(j), (int)WiFi.RSSI(j), wifiTipo(WiFi.encryptionType(j)));
  }
  listaVisivel = "";
  for (int j = 0; j < achadas && j < 15; j++) {
    String nome = WiFi.SSID(j);
    if (nome.length() == 0) continue;
    listaVisivel += "<option value=\"" + htmlSeguro(nome) + "\">";
  }
  int melhor = -1, melhorSinal = -1000;
  for (int i = 0; i < nRedes; i++) {
    for (int j = 0; j < achadas; j++) {
      if (WiFi.SSID(j) == redeSsid[i] && WiFi.RSSI(j) > melhorSinal) { melhor = i; melhorSinal = WiFi.RSSI(j); }
    }
  }
  if (nRedes == 0) {
    Serial.println("[WIFI] nenhuma rede salva: vou criar a Zenith_Carrinho");
  } else if (melhor < 0) {
    Serial.printf("[WIFI] nenhuma das %d redes salvas apareceu na varredura"
                  " (SSID oculto?) — vou tentar a mais recente mesmo assim\n", nRedes);
  } else {
    Serial.printf("[WIFI] rede salva encontrada: %s\n", redeSsid[melhor].c_str());
  }
  WiFi.scanDelete();
  return melhor;
}

void iniciarEntrada(const String &ssid, const String &senha) {
  WiFi.setHostname(NOME_NA_REDE);
  WiFi.mode(apLigado ? WIFI_AP_STA : WIFI_STA);
  Serial.printf("[WIFI] tentando entrar em '%s' (senha de %d caracteres)\n", ssid.c_str(), (int)senha.length());
  WiFi.begin(ssid.c_str(), senha.c_str());
  tentativaDesde = millis();
  ssidAtual = ssid;
}

void iniciarAP() {
  if (apLigado) return;
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
  // canal 0 = o rádio acompanha o canal do Wi-Fi em que ele entrar (evita queda quando
  // o celular troca de canal) · até 4 aparelhos ao mesmo tempo
  WiFi.softAP(AP_SSID, strlen(AP_SENHA) >= 8 ? AP_SENHA : nullptr, 0, 0, 4);
  dns.start(53, "*", IPAddress(192, 168, 4, 1));
  apLigado = true;
  Serial.println("[WIFI] rede criada: " NOME_WIFI "  http://192.168.4.1");
}

void desligarAP() {
  if (!apLigado) return;
  dns.stop();
  WiFi.softAPdisconnect(true);
  apLigado = false;
  Serial.println("[WIFI] rede propria desligada (o Zenith ja esta na rede)");
#if TEM_TELA
  toastTela("Rede propria apagada", "Zenith ja esta aqui");
#endif
}

// A regra da sua ideia: só apaga a rede própria se (1) já estamos dentro de um Wi-Fi, (2) o computador com o
// Zenith está conectado há mais de 3 s e (3) ele NÃO veio pela rede própria (senão apagaria a própria conexão dele).
bool deveDesligarAP(bool ap, bool sta, bool zenith, bool viaAP, unsigned long zenithHaMs) {
  return ap && sta && zenith && !viaAP && zenithHaMs > 3000;
}

void acompanharRede() {
  unsigned long agora = millis();
  bool ligado = (WiFi.status() == WL_CONNECTED);

  if (ligado && !staOk) {                       // acabou de entrar
    staOk = true;
    tentativaDesde = 0;
    tentativaCega = false;
    ssidAtual = WiFi.SSID();
    if (MDNS.begin(NOME_NA_REDE)) MDNS.addService("http", "tcp", 80);
    Serial.println("[WIFI] conectado em " + ssidAtual + "  IP " + WiFi.localIP().toString());
#if TEM_TELA
    toastTela("Wi-Fi conectado!", WiFi.localIP().toString());
#endif
  } else if (!ligado && staOk) {                // perdeu a rede
    staOk = false;
    Serial.println("[WIFI] perdeu a rede");
  }

  // tentou entrar e não deu em 20 s (30 s se a rede é oculta, que demora mais para responder):
  // abre a rede própria para você corrigir o nome/senha
  unsigned long prazoTentativa = tentativaCega ? 30000 : 20000;
  if (tentativaDesde != 0 && !ligado && agora - tentativaDesde > prazoTentativa) {
    tentativaDesde = 0;
    tentativaCega = false;
    WiFi.disconnect();
    // código do motivo: 1=SSID nao encontrado · 4=senha errada · 6/7/8=falha de associação
    // (2.4 GHz x 5 GHz, WPA3 ou sinal fraco). É a linha que diz POR QUE não entrou.
    Serial.printf("[WIFI] nao entrou em '%s' — codigo %d\n", ssidAtual.c_str(), (int)WiFi.status());
    iniciarAP();
#if TEM_TELA
    toastTela("Nao entrou no Wi-Fi", "Use a rede Zenith_Carrinho");
#endif
  }

  // sem Wi-Fi e sem rede própria (ex.: a rede caiu): liga a rede própria depois de 30 s
  static unsigned long semRedeDesde = 0;
  if (!ligado && !apLigado && tentativaDesde == 0) {
    if (semRedeDesde == 0) semRedeDesde = agora;
    if (agora - semRedeDesde > 30000) { semRedeDesde = 0; iniciarAP(); }
  } else {
    semRedeDesde = 0;
  }

  if (deveDesligarAP(apLigado, staOk, zenithConectado, zenithViaAP, agora - zenithDesde)) desligarAP();
}

// o carrinho "grita" onde está, para o Zenith achar sozinho (sem digitar IP)
void anunciarPresenca() {
  static unsigned long ultimo = 0;
  unsigned long agora = millis();
  if (agora - ultimo < 3000) return;
  ultimo = agora;
  if (staOk) {
    String msg = String("ZENITH-CARRINHO ") + VERSAO + " " + WiFi.localIP().toString() + " " + String(PORTA_ROSTO) + " " + NOME_NA_REDE;
    udp.beginPacket(WiFi.broadcastIP(), PORTA_DESCOBERTA);
    udp.print(msg);
    udp.endPacket();
  }
  if (apLigado) {
    String msg = String("ZENITH-CARRINHO ") + VERSAO + " 192.168.4.1 " + String(PORTA_ROSTO) + " " + NOME_NA_REDE;
    udp.beginPacket(IPAddress(192, 168, 4, 255), PORTA_DESCOBERTA);
    udp.print(msg);
    udp.endPacket();
  }
}

// ============================================================
//  RESET DE FÁBRICA — o "começar de zero" quando nada conecta.
//  Apaga: redes salvas, preferências e o PAREAMENTO Bluetooth (o PC precisa parear de novo).
//  Não apaga o programa: o firmware continua, só as configurações somem.
// ============================================================
void resetDeFabrica() {
  Serial.println("[RESET] apagando redes, preferencias e pareamento...");
#if TEM_TELA
  toastTela("Reset de fabrica", "Reiniciando...");
#endif
  // 1) desliga os rádios e os servidores antes de mexer na memória
  dns.stop();
  web.stop();
  udp.stop();
  servidorRosto.stop();
#if USAR_BLE
  BLEDevice::deinit(true);              // solta o Bluetooth (senão o pareamento fica na RAM)
#endif
  WiFi.disconnect(true, true);
  WiFi.mode(WIFI_OFF);
  delay(500);

  // 2) apaga a memória inteira: redes salvas, preferências e pareamentos Bluetooth.
  //    O programa gravado no chip NÃO é afetado — só as configurações.
  esp_err_t e = nvs_flash_erase();
  if (e != ESP_OK) { nvs_flash_init(); e = nvs_flash_erase(); }
  Serial.printf("[RESET] memoria apagada (codigo %d). Reiniciando...\n", (int)e);
  delay(400);
  ESP.restart();
}

// BOOT: solte entre 3 e 8 s = esquece as redes · segure 8 s = reset de fábrica
void vigiarBotaoReset() {
  static unsigned long desde = 0;
  static bool avisouTotal = false;

  if (digitalRead(PIN_BOTAO_RESET) == LOW) {
    if (desde == 0) desde = millis();
    unsigned long segurou = millis() - desde;
    if (segurou > 8000) {
      desde = 0;
      resetDeFabrica();
    } else if (segurou > 3000 && !avisouTotal) {
      avisouTotal = true;
#if TEM_TELA
      toastTela("Solte: esquecer redes", "8 s = reset total");
#endif
    }
  } else if (desde != 0) {
    unsigned long segurou = millis() - desde;
    desde = 0;
    if (segurou > 3000 && !avisouTotal) {
      limparRedes();
#if TEM_TELA
      toastTela("Redes apagadas", "Reiniciando...");
#endif
      delay(1200);
      ESP.restart();
    }
    avisouTotal = false;
  }
}

// ============================================================
//  VRM (quadros JPEG do Zenith por TCP)
// ============================================================
#if TEM_VRM
bool saidaJpeg(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t *bitmap) {
  if (y >= tft.height()) return false;
  tft.drawRGBBitmap(x, y, bitmap, w, h);
  return true;
}

size_t lerExato(Stream &s, uint8_t *dst, size_t n) {
  size_t lidos = 0;
  unsigned long limite = millis() + 800;
  while (lidos < n && millis() < limite) {
    int disp = s.available();
    if (disp > 0) {
      size_t quer = min((size_t)disp, n - lidos);
      lidos += s.readBytes(dst + lidos, quer);
      limite = millis() + 800;
    } else {
      delay(1);
    }
  }
  return lidos;
}

void tratarQuadro(Stream &s) {
  uint8_t cab[4];
  if (lerExato(s, cab, 4) != 4) { s.print("E\n"); return; }
  uint32_t n = (uint32_t)cab[0] | ((uint32_t)cab[1] << 8) | ((uint32_t)cab[2] << 16) | ((uint32_t)cab[3] << 24);
  if (n == 0 || n > MAX_JPEG || bufJpeg == nullptr) {
    while (s.available()) s.read();
    s.print("E\n");
    return;
  }
  if (lerExato(s, bufJpeg, n) != n) { s.print("E\n"); return; }
  ultimoQuadro = millis();
  quadros++;
  if ((long)(millis() - segurarTelaAte) < 0) { s.print("K\n"); return; }   // aviso na tela: não desenha agora
  uint16_t rc = TJpgDec.drawJpg(0, 0, bufJpeg, n);
  modoVrm = true;
  s.print(rc == 0 ? "K\n" : "E\n");
}

void responderAperto(Stream &s) {
  while (s.available()) {
    if (s.read() == '\n') break;
  }
  s.printf("ZENITH-TFT 1 %dx%d\n", tft.width(), tft.height());
}

void processarRosto(Stream &s) {
  while (s.available()) {
    int b = s.read();
    if (b != 'Z') continue;
    unsigned long limite = millis() + 100;
    while (!s.available() && millis() < limite) delay(1);
    int c = s.read();
    if (c == 'J') tratarQuadro(s);
    else if (c == 'E') responderAperto(s);
  }
}
#endif

// aceita o Zenith, percebe quando ele chega e quando sai
void tratarClienteRosto() {
  if (!clienteRosto || !clienteRosto.connected()) {
    WiFiClient novo = servidorRosto.accept();
    if (novo) {
      clienteRosto.stop();
      clienteRosto = novo;
      clienteRosto.setNoDelay(true);
      IPAddress r = clienteRosto.remoteIP(), a = WiFi.softAPIP();
      zenithViaAP = apLigado && r[0] == a[0] && r[1] == a[1] && r[2] == a[2];
    }
  }
  bool agoraLigado = clienteRosto && clienteRosto.connected();
  if (agoraLigado && !zenithConectado) {
    zenithConectado = true;
    zenithDesde = millis();
    Serial.println("[ZENITH] conectado");
#if TEM_TELA
    toastTela("Zenith conectado!", zenithViaAP ? "pela rede do carrinho" : "pelo Wi-Fi");
#endif
  } else if (!agoraLigado && zenithConectado) {
    zenithConectado = false;
    Serial.println("[ZENITH] desconectou");
  }
#if TEM_VRM
  if (agoraLigado) processarRosto(clienteRosto);
#endif
}

// ============================================================
//  SERVIDOR WEB
// ============================================================
bool chaveOk() {
  if (strlen(CHAVE) == 0) return true;
  return web.arg("k") == CHAVE;
}

bool veioDoAP() {
  IPAddress r = web.client().remoteIP(), a = WiFi.softAPIP();
  return apLigado && r[0] == a[0] && r[1] == a[1] && r[2] == a[2];
}

// configurar Wi-Fi: com CHAVE, precisa dela; sem CHAVE, só quem está na rede própria do carrinho
bool podeConfigurarRede() {
  if (strlen(CHAVE) > 0) return chaveOk();
  return veioDoAP();
}

void rotaRaiz() {
  web.sendHeader("Cache-Control", "no-store");
  web.send_P(200, "text/html; charset=utf-8", PAGINA);
}

void rotaCmd() {
  if (!chaveOk()) { web.send(401, "text/plain", "chave errada"); return; }
  String c = web.arg("c");
  if (c.length() == 0) { web.send(400, "text/plain", "ERRO"); return; }
  if (web.hasArg("t")) {                           // formato do skill: c=F&t=1000&v=140
    c += " " + web.arg("t");
    if (web.hasArg("v")) c += " " + web.arg("v");
  }
  processarLinha(c);
  web.send(200, "text/plain", "OK");
}

void rotaParar() {
  if (!chaveOk()) { web.send(401, "text/plain", "chave errada"); return; }
  processarLinha("S");
  web.send(200, "text/plain", "OK");
}

void rotaStatus() {
  bool ble = false;
#if USAR_BLE
  ble = btConectado;
#endif
  String j = "{\"ok\":true,\"versao\":\"" VERSAO "\"";
  j += ",\"tela\":" + String(TEM_TELA ? "true" : "false");
  j += ",\"wifi\":\"" + (staOk ? jsonSeguro(ssidAtual) : String("")) + "\"";
  j += ",\"ip\":\"" + ipTexto() + "\"";
  j += ",\"ap\":" + String(apLigado ? "true" : "false");
  j += ",\"zenith\":" + String(zenithConectado ? "true" : "false");
  j += ",\"quadros\":" + String(quadros);
  j += ",\"ble\":" + String(ble ? "true" : "false");
  j += ",\"chave\":" + String(strlen(CHAVE) > 0 ? "true" : "false");
  j += ",\"memoria_kb\":" + String(ESP.getFreeHeap() / 1024);
  j += ",\"ligado_ha_s\":" + String(millis() / 1000);
  j += ",\"ultimo_comando\":\"" + jsonSeguro(ultimoComando) + "\"}";
  web.sendHeader("Access-Control-Allow-Origin", "*");
  web.send(200, "application/json", j);
}

void rotaRede() {
  String h = "<!DOCTYPE html><html lang=pt-BR><head><meta charset=UTF-8>"
             "<meta name=viewport content='width=device-width,initial-scale=1'><title>Wi-Fi do carrinho</title>"
             "<style>body{font-family:system-ui,sans-serif;background:#10141c;color:#e8edf5;padding:16px;max-width:380px;margin:auto}"
             "input,button{font-size:18px;padding:12px;margin:6px 0;width:100%;box-sizing:border-box;border-radius:10px;border:0}"
             "input{background:#fff;color:#111}button{background:#f5a623;color:#111;font-weight:700}"
             "a{color:#f5a623}.n{color:#9fb0c9;font-size:14px;line-height:1.5}</style></head><body>"
             "<h2>Wi-Fi do carrinho</h2>"
             "<p class=n id=e>carregando...</p>"
             "<form method=POST action=/rede/salvar>";
  if (strlen(CHAVE) > 0) h += "<input name=k type=password placeholder='chave do carrinho'>";
  h += "<input name=s list=r placeholder='nome do Wi-Fi (ex.: o do seu celular)'><datalist id=r>" + listaVisivel + "</datalist>"
       "<input name=p type=password placeholder='senha do Wi-Fi'>"
       "<button>Conectar e salvar</button></form>"
       "<p class=n>Redes salvas: ";
  if (nRedes == 0) h += "nenhuma";
  for (int i = 0; i < nRedes; i++) h += (i ? ", " : "") + htmlSeguro(redeSsid[i]);
  h += "</p>"
       "<form method=POST action=/rede/apagar onsubmit=\"return confirm('Esquecer todas as redes salvas?')\">";
  if (strlen(CHAVE) > 0) h += "<input name=k type=password placeholder='chave do carrinho'>";
  h += "<button style='background:#e5484d;color:#fff'>Esquecer redes salvas</button></form>"
       "<p class=n>Depois de conectar, o celular pode perder o Wi-Fi do carrinho por alguns segundos. "
       "Conecte o PC com o Zenith no <b>mesmo</b> Wi-Fi: o carrinho apaga a rede dele sozinho quando o Zenith aparecer.</p>"
       "<p><a href=/>Voltar ao painel</a></p>"
       "<script>function st(){fetch('/status').then(r=>r.json()).then(j=>{document.getElementById('e').textContent="
       "(j.wifi?'✓ Conectado em '+j.wifi+' (IP '+j.ip+')':'Sem Wi-Fi ainda')+(j.zenith?' · ✓ Zenith conectado':' · Zenith não conectado');})}"
       "st();setInterval(st,2500);</script></body></html>";
  web.sendHeader("Cache-Control", "no-store");
  web.send(200, "text/html; charset=utf-8", h);
}

void rotaRedeSalvar() {
  if (!podeConfigurarRede()) { web.send(401, "text/plain", "sem permissao (chave errada ou fora da rede do carrinho)"); return; }
  String s = web.arg("s"), p = web.arg("p");
  s.trim();
  if (s.length() == 0 || s.length() > 32) { web.send(400, "text/plain", "nome do Wi-Fi vazio ou maior que 32 letras"); return; }
  if (p.length() > 63 || (p.length() > 0 && p.length() < 8)) { web.send(400, "text/plain", "senha: 8 a 63 caracteres (ou vazia se a rede for aberta)"); return; }
  salvarRede(s, p);
  iniciarEntrada(s, p);
  web.send(200, "text/html; charset=utf-8",
           "<!DOCTYPE html><meta charset=UTF-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           "<body style='font-family:system-ui;background:#10141c;color:#e8edf5;padding:20px'>"
           "<h3>Salvo! Entrando em " + htmlSeguro(s) + "...</h3>"
           "<p>Espere uns 15 segundos. A telinha vai mostrar o IP. Se o seu celular perder a rede do carrinho, é normal.</p>"
           "<p><a style='color:#f5a623' href=/rede>Ver como ficou</a></p></body>");
}

// Reset de fábrica pela página. Só de dentro da rede do carrinho (ou com a CHAVE),
// e só com ?confirma=sim para ninguém apertar sem querer.
void rotaReset() {
  if (!podeConfigurarRede()) { web.send(401, "text/plain", "sem permissao (chave errada ou fora da rede do carrinho)"); return; }
  if (!web.hasArg("confirma")) { web.send(400, "text/plain", "faltou ?confirma=sim"); return; }
  web.sendHeader("Cache-Control", "no-store");
  web.send(200, "text/html; charset=utf-8",
           "<!DOCTYPE html><meta charset=UTF-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           "<body style='font-family:system-ui;background:#10141c;color:#e8edf5;padding:20px'>"
           "<h3>Reset de fábrica</h3><p>Redes e pareamento Bluetooth apagados. O carrinho vai reiniciar "
           "e criar a rede <b>Zenith_Carrinho</b> de novo. Pode fechar esta página.</p></body>");
  resetEm = millis() + 1500;
}

void rotaRedeApagar() {
  if (!podeConfigurarRede()) { web.send(401, "text/plain", "sem permissao"); return; }
  limparRedes();
  web.send(200, "text/plain", "Redes esquecidas. Reiniciando...");
  reiniciarEm = millis() + 1500;
}

// portal cativo: enquanto a rede própria está no ar, qualquer endereço abre a página
void rotaPortal() {
  if (apLigado) {
    web.sendHeader("Location", "http://192.168.4.1/", true);
    web.send(302, "text/plain", "");
  } else {
    web.send(404, "text/plain", "nao existe");
  }
}

void iniciarServidorWeb() {
  web.on("/", rotaRaiz);
  web.on("/cmd", rotaCmd);
  web.on("/parar", rotaParar);
  web.on("/status", rotaStatus);
  web.on("/rede", HTTP_GET, rotaRede);
  web.on("/rede/salvar", HTTP_POST, rotaRedeSalvar);
  web.on("/rede/apagar", HTTP_POST, rotaRedeApagar);
  web.on("/reset", HTTP_ANY, rotaReset);
  web.onNotFound(rotaPortal);
  web.begin();
  servidorRosto.begin();
  udp.begin(PORTA_DESCOBERTA);
}

// ============================================================
void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  Serial1.begin(9600, SERIAL_8N1, PIN_UNO_RX, PIN_UNO_TX);
  pinMode(PIN_BOTAO_RESET, INPUT_PULLUP);

#if USAR_BLE
  filaBle = xQueueCreate(256, sizeof(char));
#endif

#if TEM_TELA
  SPI.begin(TFT_SCK, -1, TFT_MOSI, TFT_CS);
  tft.setSPISpeed(TFT_MHZ);
  #if TFT_TAB == 0
    tft.initR(INITR_BLACKTAB);
  #elif TFT_TAB == 1
    tft.initR(INITR_GREENTAB);
  #else
    tft.initR(INITR_REDTAB);
  #endif
  tft.setRotation(0);
  tft.setTextWrap(false);
  #if TESTE_TELA
    testeDeCores();
  #endif
  telaInicio();
  mostrarRodape("Procurando Wi-Fi...", "");
  proxPiscar = millis() + 3000;
#endif

#if TEM_VRM
  bufJpeg = (uint8_t *)(psramFound() ? ps_malloc(MAX_JPEG) : malloc(MAX_JPEG));
  TJpgDec.setJpgScale(1);
  TJpgDec.setSwapBytes(TJPG_TROCAR_BYTES);
  TJpgDec.setCallback(saidaJpeg);
#endif

  // Wi-Fi: entra numa rede salva; se não tem ou não achou, cria a rede "Zenith_Carrinho"
  carregarRedes();
  int idx = escanearEEscolher();
  // 01/11 — "está salvo mas nunca entra": com Ocultar SSID ligado no celular, a rede salva NÃO
  // aparece na varredura (o ESP32 recebe o nome vazio) e o código antigo desistia sem tentar.
  // Agora, se nada conhecido apareceu mas existe rede salva, ele tenta a mais recente assim mesmo:
  // o Wi-Fi do ESP32 entra em rede oculta normalmente quando recebe nome + senha.
  tentativaCega = (idx < 0 && nRedes > 0);
  if (tentativaCega) idx = 0;
  if (idx >= 0) iniciarEntrada(redeSsid[idx], redeSenha[idx]);
  else          iniciarAP();

#if USAR_BLE
  iniciarBluetooth();
#endif
  iniciarServidorWeb();

  Serial.println("ZENITH-CARRINHO " VERSAO);
  Serial.println("F/B/L/R <ms> [vel] · S · ROSTO <nome> · PING");
}

void loop() {
  vigiarBotaoReset();
  lerDoUsb();
#if USAR_BLE
  lerDoBle();
  tratarEventosBle();
#endif
  acompanharRede();
  if (apLigado) dns.processNextRequest();
  web.handleClient();
  tratarClienteRosto();
  anunciarPresenca();
  if (reiniciarEm != 0 && (long)(millis() - reiniciarEm) >= 0) ESP.restart();
  if (resetEm != 0 && (long)(millis() - resetEm) >= 0) { resetEm = 0; resetDeFabrica(); }
#if TEM_TELA
  atualizarTela();
#endif
  delay(2);
}
