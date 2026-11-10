// ============================================================
//  ZENITH — Criado por Anderson
//  ZenithAndroidPlugin.kt — v1.11 (port celular): o plugin que FAZ o que o Cérebro pede ao Android.
//
//  >>> NÃO FOI COMPILADO NEM EXECUTADO. <<<  Foi escrito sem Android Studio, sem Gradle e sem Godot por perto,
//  a partir do contrato em brain/zenith_plataforma_android.py. É um PONTO DE PARTIDA honesto: ao compilar, erros de
//  nome de classe ou de assinatura do GodotPlugin são esperados — corrija e me conte o que apareceu.
//
//  Como funciona: o ponte_android.gd (Godot) chama `chamar(id, nome, argsJson)`; o resultado volta pelo sinal
//  `resposta(id, json)`; o microfone empurra pedaços pelo sinal `evento("mic.quadro", json)`.
//
//  CAPACIDADES QUE ESTE ESQUELETO ANUNCIA (só o que está implementado de fato — o resto o Cérebro trata como
//  "não existe neste aparelho" e segue sem quebrar): audio_saida, voz_local, microfone, notificacao, abrir, sistema
//  e — SÓ quando o modelo de fala em português está no aparelho — transcricao (stt.transcrever, feita com o Vosk),
//  e — SÓ quando o aparelho tem Bluetooth LE — ble (ble.enviar, para o carrinho).
//  e — v1.19 — video (video.info / video.quadros, pelo MediaMetadataRetriever), camera (camera.capturar, Camera2 sem prévia,
//  SÓ quando o aparelho tem câmera) e tela (tela.capturar, MediaProjection: o Android mostra a janela de permissão e uma
//  notificação enquanto captura; o serviço em primeiro plano está em ZenithCapturaService.kt).
//  AINDA NÃO IMPLEMENTADA (e por isso NÃO anunciada): llm_local (precisa de um servidor de IA nativo, que não existe aqui).
//  >>> video, camera e tela são da v1.19 e TAMBÉM nunca foram compilados nem rodados num aparelho. <<<
// ============================================================
package com.zenith.android

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Matrix
import android.graphics.PixelFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.Image
import android.media.ImageReader
import android.media.MediaMetadataRetriever
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Base64
import androidx.core.app.NotificationCompat
import org.godotengine.godot.Godot
import org.godotengine.godot.plugin.GodotPlugin
import org.godotengine.godot.plugin.SignalInfo
import org.godotengine.godot.plugin.UsedByGodot
import org.json.JSONArray
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.zip.ZipInputStream
import kotlin.concurrent.thread

class ZenithAndroidPlugin(godot: Godot) : GodotPlugin(godot) {

    private var tts: TextToSpeech? = null
    private var ttsPronto = false
    private val aoIniciarTts = mutableListOf<() -> Unit>()

    private var player: MediaPlayer? = null
    @Volatile private var tocando = false

    private var gravador: AudioRecord? = null
    @Volatile private var gravando = false

    // fala -> texto (Vosk): o modelo é carregado UMA vez e reaproveitado; um pedido por vez (o aparelho é pequeno)
    private var modeloVosk: Model? = null
    private val travaVosk = Any()
    @Volatile private var aquecendoVosk = false
    @Volatile private var voskQuebrado = false      // a biblioteca nativa não carregou: para de anunciar "transcricao"

    override fun getPluginName() = "ZenithAndroid"

    override fun getPluginSignals(): Set<SignalInfo> = setOf(
        SignalInfo("resposta", String::class.java, String::class.java),
        SignalInfo("evento", String::class.java, String::class.java),
    )

    // ---------- o que este aparelho TEM (só o que está implementado) ----------
    @UsedByGodot
    fun capacidades(): String {
        val lista = mutableListOf("sistema", "audio_saida", "voz_local", "microfone", "notificacao", "abrir", "video", "tela")
        if (activity?.packageManager?.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) == true) lista.add("camera")
        if (transcricaoDisponivel()) { lista.add("transcricao"); aquecerModeloVosk() }
        if (temBle()) lista.add("ble")
        return JSONArray(lista).toString()
    }

    // ---------- ponto de entrada único ----------
    @UsedByGodot
    fun chamar(id: String, nome: String, argsJson: String) {
        val args = try { JSONObject(argsJson) } catch (e: Exception) { JSONObject() }
        try {
            when (nome) {
                "sistema.medir" -> responder(id, medirSistema())
                "audio.tocar" -> tocar(id, args.getString("caminho"), args.optDouble("volume", 1.0).toFloat())
                "audio.parar" -> { parar(); responder(id, ok()) }
                "audio.ocupado" -> responder(id, ok().put("ocupado", tocando))
                "tts.sintetizar" -> sintetizar(
                    id, args.getString("texto"), args.getString("caminho_saida"),
                    args.optDouble("velocidade", 1.0).toFloat(), args.optDouble("tom", 1.0).toFloat()
                )
                "mic.iniciar" -> iniciarMicrofone(id, args.optInt("taxa", 16000))
                "mic.parar" -> { pararMicrofone(); responder(id, ok()) }
                // o idioma do pedido é ignorado de propósito: o modelo instalado é o de português
                "stt.transcrever" -> transcrever(id, args.getString("pcm16"), args.optInt("taxa", 16000))
                // baixador do modelo de fala (chamado pela tela de Voz do Corpo, não pelo Cérebro)
                "ble.enviar" -> bleEnviar(id, args.getString("dispositivo"), args.getString("dados"))
                "modelo.estado" -> responder(id, ok().put("instalado", pastaModeloVosk() != null).put("baixando", baixandoModelo))
                "modelo.baixar" -> baixarModelo(id, args.optString("url", URL_MODELO_PADRAO), args.optString("sha256", ""))
                "video.info" -> videoInfo(id, args.getString("caminho"))
                "video.quadros" -> videoQuadros(id, args)
                "camera.capturar" -> capturarCamera(id, args.optInt("warmup", 5), args.optInt("max_w", 0))
                "tela.capturar" -> capturarTela(id, args.optInt("max_w", 0), args.optBoolean("jpeg", false))
                "notificacao.mostrar" -> notificar(id, args.optString("titulo"), args.optString("texto"))
                "app.abrir" -> abrir(id, args.getString("alvo"))
                else -> responder(id, erro("O plugin Android ainda não implementa '$nome'."))
            }
        } catch (e: Exception) {
            responder(id, erro("Falha em '$nome': ${e.message}"))
        }
    }

    // ---------- sistema ----------
    private fun medirSistema(): JSONObject {
        val ctx = activity!!.applicationContext
        val info = ActivityManager.MemoryInfo()
        (ctx.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(info)
        val gb = 1024.0 * 1024.0 * 1024.0
        val r = ok().put("ram_total_gb", info.totalMem / gb).put("ram_livre_gb", info.availMem / gb)
        val bat = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        if (bat != null) {
            val nivel = bat.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val escala = bat.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            if (nivel >= 0 && escala > 0) r.put("bateria_pct", nivel * 100.0 / escala)
            val status = bat.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            r.put("carregando", status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL)
            val temp = bat.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
            if (temp != Int.MIN_VALUE) r.put("temperatura_c", temp / 10.0)
        }
        return r
    }

    // ---------- áudio de saída: `audio.tocar` só responde DEPOIS de o som começar (contrato do Cérebro) ----------
    private fun tocar(id: String, caminho: String, volume: Float) {
        parar()
        val mp = MediaPlayer()
        player = mp
        mp.setDataSource(caminho)
        mp.setVolume(volume, volume)
        tocando = true                                   // "ocupado" desde já: o Cérebro não pode ver um falso "terminou"
        mp.setOnPreparedListener { it.start(); responder(id, ok()) }
        mp.setOnCompletionListener { tocando = false }
        mp.setOnErrorListener { _, _, _ -> tocando = false; responder(id, erro("O Android não conseguiu tocar o áudio.")); true }
        mp.prepareAsync()
    }

    private fun parar() {
        tocando = false
        player?.let { try { it.stop() } catch (ignorado: Exception) {}; it.release() }
        player = null
    }

    // ---------- voz do Android (sem internet) ----------
    private fun comTts(acao: () -> Unit) {
        if (ttsPronto) { acao(); return }
        aoIniciarTts.add(acao)
        if (tts == null) {
            tts = TextToSpeech(activity!!.applicationContext) { status ->
                ttsPronto = status == TextToSpeech.SUCCESS
                if (ttsPronto) tts?.language = Locale("pt", "BR")
                val fila = aoIniciarTts.toList(); aoIniciarTts.clear()
                if (ttsPronto) fila.forEach { it() }
            }
        }
    }

    private fun sintetizar(id: String, texto: String, caminho: String, velocidade: Float, tom: Float) {
        comTts {
            val t = tts!!
            t.setSpeechRate(velocidade); t.setPitch(tom)
            val enunciado = "zenith-$id"
            t.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) { if (utteranceId == enunciado) responder(id, ok()) }
                @Deprecated("API antiga") override fun onError(utteranceId: String?) {
                    if (utteranceId == enunciado) responder(id, erro("A voz do Android falhou ao gerar o áudio."))
                }
            })
            File(caminho).parentFile?.mkdirs()
            if (t.synthesizeToFile(texto, Bundle(), File(caminho), enunciado) != TextToSpeech.SUCCESS)
                responder(id, erro("A voz do Android recusou o pedido."))
        }
    }

    // ---------- microfone: PCM 16 bits mono, pedaços de ~100 ms, em base64, pelo evento mic.quadro ----------
    private fun iniciarMicrofone(id: String, taxa: Int) {
        pararMicrofone()
        val bloco = taxa / 10 * 2                                           // 100 ms de áudio em bytes
        val minimo = AudioRecord.getMinBufferSize(taxa, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(MediaRecorder.AudioSource.MIC, taxa, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(minimo, bloco * 4))
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            responder(id, erro("Não consegui abrir o microfone (falta a permissão ou outro app está usando)."))
            return
        }
        gravador = rec; gravando = true
        rec.startRecording()
        responder(id, ok())
        thread(name = "zenith-mic") {
            val buf = ByteArray(bloco)
            while (gravando) {
                var lidos = 0
                while (gravando && lidos < bloco) {
                    val n = rec.read(buf, lidos, bloco - lidos)
                    if (n <= 0) break
                    lidos += n
                }
                if (lidos == bloco) emitSignal("evento", "mic.quadro",
                    JSONObject().put("pcm16", Base64.encodeToString(buf, Base64.NO_WRAP)).toString())
            }
        }
    }

    private fun pararMicrofone() {
        gravando = false
        gravador?.let { try { it.stop() } catch (ignorado: Exception) {}; it.release() }
        gravador = null
    }

    // ---------- fala -> texto: Vosk (offline, aceita ÁUDIO PRONTO — é assim que o Cérebro pede) ----------
    // O Cérebro grava o microfone pela ponte, detecta o silêncio e, a cada ~1 s, manda o áudio já gravado pedindo o texto
    // (é isso que faz o texto aparecer enquanto a pessoa fala). Por isso NÃO serve o reconhecedor do Android: ele abre o
    // microfone sozinho e não recebe áudio pronto.
    // O modelo de português NÃO vai dentro do APK (~50 MB): é um módulo baixável que fica em
    //   <pasta de arquivos do app>/modelos/vosk-pt        (precisa ter as pastas "am" e "conf" direto dentro)
    // Ainda NÃO existe o baixador: para testar, copie o modelo à mão (veja o README do plugin).
    private fun pastaModeloVosk(): File? {
        val ctx = activity?.applicationContext ?: return null
        return listOfNotNull(ctx.getExternalFilesDir(null), ctx.filesDir)
            .map { File(it, "modelos/vosk-pt") }
            .firstOrNull { File(it, "am").isDirectory && File(it, "conf").isDirectory }
    }

    // Só anuncia "transcricao" se há modelo no aparelho E a biblioteca do Vosk não falhou antes.
    private fun transcricaoDisponivel(): Boolean = !voskQuebrado && pastaModeloVosk() != null

    private fun carregarModeloVosk(pasta: File): Model = synchronized(travaVosk) {
        modeloVosk ?: Model(pasta.absolutePath).also { modeloVosk = it }
    }

    // Carrega o modelo em segundo plano assim que se sabe que ele existe: a 1ª fala não paga o tempo de carga.
    private fun aquecerModeloVosk() {
        if (modeloVosk != null || aquecendoVosk) return
        val pasta = pastaModeloVosk() ?: return
        aquecendoVosk = true
        thread(name = "zenith-stt-aquecer") {
            try { carregarModeloVosk(pasta) } catch (e: Throwable) { frasePorFalhaVosk(e) } finally { aquecendoVosk = false }
        }
    }

    private fun frasePorFalhaVosk(e: Throwable): String {
        if (e is UnsatisfiedLinkError || e is NoClassDefFoundError || e is ExceptionInInitializerError) {
            voskQuebrado = true                              // o Cérebro segue sem transcrição, em vez de pedir e falhar toda vez
            return "A biblioteca de fala (Vosk) não carregou neste aparelho."
        }
        return "Falha ao transformar a fala em texto: ${e.message}"
    }

    private fun transcrever(id: String, pcm16B64: String, taxa: Int) {
        val pasta = pastaModeloVosk()
        if (pasta == null || voskQuebrado) {
            responder(id, erro("O modelo de fala em português ainda não está neste aparelho."))
            return
        }
        val pcm = try { Base64.decode(pcm16B64, Base64.DEFAULT) } catch (e: IllegalArgumentException) {
            responder(id, erro("O áudio chegou corrompido; tente falar de novo."))
            return
        }
        val util = pcm.size - (pcm.size % 2)                 // PCM de 16 bits: descarta um byte solto no fim
        thread(name = "zenith-stt") {                         // carregar o modelo e reconhecer levam segundos: fora da thread principal
            try {
                val texto = synchronized(travaVosk) {
                    val rec = Recognizer(carregarModeloVosk(pasta), taxa.toFloat())
                    try {
                        var pos = 0
                        while (pos < util) {
                            val n = minOf(8000, util - pos)
                            rec.acceptWaveForm(pcm.copyOfRange(pos, pos + n), n)
                            pos += n
                        }
                        JSONObject(rec.finalResult).optString("text", "").trim()
                    } finally { rec.close() }
                }
                responder(id, ok().put("texto", texto))
            } catch (e: Throwable) {
                responder(id, erro(frasePorFalhaVosk(e)))
            }
        }
    }

    // ---------- baixador do modelo de fala ----------
    // O modelo (~50 MB) NÃO vai no APK. É baixado AQUI, no app, porque só o app escreve na própria pasta (o Cérebro, rodando
    // em outro processo, não enxerga essa pasta). Passos: baixar -> (conferir o SHA-256 se foi informado) -> descompactar numa
    // pasta temporária -> conferir que tem "am" e "conf" -> trocar pela pasta final. Progresso e fim saem como EVENTOS
    // (modelo.progresso / modelo.pronto / modelo.erro): o Corpo mostra a barra e, no "pronto", reanuncia as capacidades.
    // A URL é a página oficial do Vosk; CONFIRA o nome/versão do arquivo antes de confiar (pode ter mudado).
    private val URL_MODELO_PADRAO = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
    @Volatile private var baixandoModelo = false

    private fun evento(nome: String, dados: JSONObject) = emitSignal("evento", nome, dados.toString())

    private fun pastaDoApp(): File? {
        val ctx = activity?.applicationContext ?: return null
        return ctx.getExternalFilesDir(null) ?: ctx.filesDir     // a mesma ordem que pastaModeloVosk() procura
    }

    private fun baixarModelo(id: String, url: String, shaEsperado: String) {
        if (baixandoModelo) {
            responder(id, erro("Já estou baixando o modelo de fala."))
            return
        }
        val base = pastaDoApp()
        if (base == null) {
            responder(id, erro("Não achei a pasta do app para guardar o modelo."))
            return
        }
        baixandoModelo = true
        responder(id, ok().put("iniciado", true))                 // a resposta é na hora; o resto vem por eventos
        thread(name = "zenith-modelo") {
            val temp = File(base, "modelos/.baixando")
            try {
                temp.deleteRecursively()
                temp.mkdirs()
                val zip = File(temp, "modelo.zip")
                evento("modelo.progresso", JSONObject().put("fase", "baixando").put("pct", 0))
                val con = URL(url).openConnection() as HttpURLConnection
                con.connectTimeout = 15000
                con.readTimeout = 30000
                if (con.responseCode !in 200..299) throw IOException("O servidor respondeu ${con.responseCode}.")
                val total = con.contentLengthLong
                val resumo = MessageDigest.getInstance("SHA-256")
                con.inputStream.use { entrada ->
                    zip.outputStream().use { saida ->
                        val buf = ByteArray(64 * 1024)
                        var lidos = 0L
                        var ultimo = -1
                        while (true) {
                            val n = entrada.read(buf)
                            if (n < 0) break
                            saida.write(buf, 0, n)
                            resumo.update(buf, 0, n)
                            lidos += n
                            val pct = if (total > 0) (lidos * 100 / total).toInt() else -1
                            if (pct != ultimo) {
                                ultimo = pct
                                evento("modelo.progresso", JSONObject().put("fase", "baixando").put("pct", pct))
                            }
                        }
                    }
                }
                con.disconnect()
                if (shaEsperado.isNotEmpty()) {
                    val hex = resumo.digest().joinToString("") { "%02x".format(it) }
                    if (!hex.equals(shaEsperado, ignoreCase = true)) throw IOException("O arquivo baixado não bate com o SHA-256 esperado.")
                }
                evento("modelo.progresso", JSONObject().put("fase", "instalando").put("pct", 100))
                val solto = File(temp, "modelo")
                solto.mkdirs()
                descompactar(zip, solto)
                val raiz = raizDoModelo(solto) ?: throw IOException("O arquivo baixado não parece um modelo de fala (faltam as pastas am e conf).")
                val destino = File(base, "modelos/vosk-pt")
                destino.deleteRecursively()
                destino.parentFile?.mkdirs()
                if (!raiz.renameTo(destino)) throw IOException("Não consegui instalar o modelo na pasta final.")
                synchronized(travaVosk) { modeloVosk = null }       // o próximo pedido carrega o modelo novo
                voskQuebrado = false
                evento("modelo.pronto", JSONObject().put("ok", true))
            } catch (e: Throwable) {
                evento("modelo.erro", JSONObject().put("erro", "Não consegui baixar o modelo de fala: ${e.message}"))
            } finally {
                temp.deleteRecursively()
                baixandoModelo = false
            }
        }
    }

    // Descompacta com proteção contra caminhos maliciosos dentro do zip ("../../algo"): nada sai da pasta de destino.
    private fun descompactar(zip: File, para: File) {
        val limite = para.canonicalPath + File.separator
        ZipInputStream(zip.inputStream().buffered()).use { z ->
            var entrada = z.nextEntry
            while (entrada != null) {
                val alvo = File(para, entrada.name)
                if (!alvo.canonicalPath.startsWith(limite)) throw IOException("O arquivo baixado tem um caminho inválido.")
                if (entrada.isDirectory) {
                    alvo.mkdirs()
                } else {
                    alvo.parentFile?.mkdirs()
                    alvo.outputStream().use { z.copyTo(it) }
                }
                z.closeEntry()
                entrada = z.nextEntry
            }
        }
    }

    // O zip do modelo costuma ter UMA pasta dentro (ex.: vosk-model-small-pt-0.3/). Devolve a pasta que tem "am" e "conf".
    private fun raizDoModelo(pasta: File): File? {
        fun serve(d: File) = File(d, "am").isDirectory && File(d, "conf").isDirectory
        if (serve(pasta)) return pasta
        return pasta.listFiles()?.firstOrNull { it.isDirectory && serve(it) }
    }

    // ---------- Bluetooth LE: falar com o carrinho (Nordic UART, os mesmos identificadores do firmware) ----------
    // O firmware (firmware/carrinho_esp32s3) anuncia "Zenith_Carrinho" com o serviço 6E400001-... e recebe os comandos
    // (uma linha de texto cada) na característica 6E400002-.... Aqui: procura pelo NOME (sem ligar para hífen, sublinhado,
    // espaço ou maiúsculas, como o painel do PC), conecta, acha a característica e escreve em pedaços de 20 bytes.
    // A conexão fica aberta para os próximos comandos; se cair, o próximo envio reconecta.
    private val UUID_SERVICO_BLE = UUID.fromString("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
    private val UUID_RX_BLE = UUID.fromString("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")      // o celular ESCREVE aqui
    private val travaBle = Any()
    private var gattBle: BluetoothGatt? = null
    private var canalBle: BluetoothGattCharacteristic? = null
    private var nomeBle: String = ""

    private fun temBle(): Boolean =
        activity?.packageManager?.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE) == true

    private fun normalizarNome(n: String): String = n.lowercase().replace(Regex("[\\s_-]"), "")

    @SuppressLint("MissingPermission")     // a permissão é pedida pelo Corpo (ponte_android.gd) ANTES de chamar
    private fun conectarBle(nome: String): BluetoothGattCharacteristic {
        synchronized(travaBle) {
            val aberto = canalBle
            if (aberto != null && gattBle != null && nomeBle == nome) return aberto
            gattBle?.close()
            gattBle = null
            canalBle = null
            val ctx = activity?.applicationContext ?: throw IOException("O app ainda não está pronto.")
            val adaptador = (ctx.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
            if (adaptador == null || !adaptador.isEnabled) throw IOException("O Bluetooth do aparelho está desligado.")
            val scanner = adaptador.bluetoothLeScanner ?: throw IOException("Este aparelho não consegue buscar Bluetooth LE.")
            val achado = CountDownLatch(1)
            var aparelho: BluetoothDevice? = null
            val busca = object : ScanCallback() {
                override fun onScanResult(tipo: Int, r: ScanResult) {
                    val n = r.device.name ?: r.scanRecord?.deviceName
                    if (n != null && normalizarNome(n) == normalizarNome(nome)) {
                        aparelho = r.device
                        achado.countDown()
                    }
                }
            }
            scanner.startScan(busca)
            val achou = achado.await(10, TimeUnit.SECONDS)
            scanner.stopScan(busca)
            val dispositivo = aparelho
            if (!achou || dispositivo == null) throw IOException("Não achei o '$nome' por Bluetooth. Ele está ligado e perto?")
            val pronto = CountDownLatch(1)
            var canal: BluetoothGattCharacteristic? = null
            val g = dispositivo.connectGatt(ctx, false, object : BluetoothGattCallback() {
                override fun onConnectionStateChange(g: BluetoothGatt, status: Int, novo: Int) {
                    if (novo == BluetoothProfile.STATE_CONNECTED) {
                        g.discoverServices()
                    } else if (novo == BluetoothProfile.STATE_DISCONNECTED) {
                        synchronized(travaBle) { canalBle = null; gattBle = null }
                        pronto.countDown()
                    }
                }
                override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                    canal = g.getService(UUID_SERVICO_BLE)?.getCharacteristic(UUID_RX_BLE)
                    pronto.countDown()
                }
            }, BluetoothDevice.TRANSPORT_LE)
            if (!pronto.await(12, TimeUnit.SECONDS) || canal == null) {
                g.close()
                throw IOException("Conectei, mas o carrinho não tem o serviço de comandos (Nordic UART).")
            }
            gattBle = g
            canalBle = canal
            nomeBle = nome
            return canal!!
        }
    }

    @SuppressLint("MissingPermission")
    private fun bleEnviar(id: String, nome: String, dadosB64: String) {
        val bytes = Base64.decode(dadosB64, Base64.DEFAULT)
        thread(name = "zenith-ble") {                              // buscar e conectar levam segundos: fora da thread principal
            try {
                val canal = conectarBle(nome)
                val g = gattBle ?: throw IOException("A conexão Bluetooth caiu.")
                var pos = 0
                while (pos < bytes.size) {
                    val parte = bytes.copyOfRange(pos, minOf(pos + 20, bytes.size))     // MTU padrão: 20 bytes úteis
                    val enviado = if (Build.VERSION.SDK_INT >= 33) {
                        g.writeCharacteristic(canal, parte, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) == BluetoothStatusCodes.SUCCESS
                    } else {
                        @Suppress("DEPRECATION")
                        run {
                            canal.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
                            canal.value = parte
                            g.writeCharacteristic(canal)
                        }
                    }
                    if (!enviado) throw IOException("O Bluetooth recusou o envio.")
                    pos += parte.size
                    Thread.sleep(30)                               // sem resposta de escrita: dá tempo ao rádio entre pedaços
                }
                responder(id, ok())
            } catch (e: Throwable) {
                synchronized(travaBle) { gattBle?.close(); gattBle = null; canalBle = null }
                responder(id, erro(e.message ?: "Falha no Bluetooth."))
            }
        }
    }

    // ---------- notificação e abrir ----------
    private fun notificar(id: String, titulo: String, texto: String) {
        val ctx = activity!!.applicationContext
        val gerente = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            gerente.createNotificationChannel(NotificationChannel("zenith", "Zenith", NotificationManager.IMPORTANCE_DEFAULT))
        gerente.notify(System.currentTimeMillis().toInt(), NotificationCompat.Builder(ctx, "zenith")
            .setSmallIcon(ctx.applicationInfo.icon).setContentTitle(titulo).setContentText(texto).setAutoCancel(true).build())
        responder(id, ok())
    }

    private fun abrir(id: String, alvo: String) {
        // Só endereços da web: o Zenith não abre programas do celular por conta própria.
        if (!(alvo.startsWith("http://") || alvo.startsWith("https://"))) {
            responder(id, erro("Por segurança, só abro endereços da web (http/https)."))
            return
        }
        activity!!.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(alvo)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        responder(id, ok())
    }

    // ---------- imagem: reduzir e codificar (usado pela câmera, pela tela e pelos quadros de vídeo) ----------
    private fun reduzir(b: Bitmap, maxLargura: Int): Bitmap {
        if (maxLargura <= 0 || b.width <= maxLargura) return b
        val h = maxOf(1, (b.height.toLong() * maxLargura / b.width).toInt())
        return Bitmap.createScaledBitmap(b, maxLargura, h, true)
    }

    private fun codificar(b: Bitmap, jpeg: Boolean, qualidade: Int): ByteArray {
        val saida = ByteArrayOutputStream()
        if (jpeg) b.compress(Bitmap.CompressFormat.JPEG, qualidade, saida) else b.compress(Bitmap.CompressFormat.PNG, 100, saida)
        return saida.toByteArray()
    }

    // ---------- vídeo (v1.19): MediaMetadataRetriever. O OpenCV quase nunca existe no celular; quem lê o vídeo é o Android. ----------
    private fun videoInfo(id: String, caminho: String) {
        thread(name = "zenith-video-info") {
            val r = MediaMetadataRetriever()
            try {
                r.setDataSource(caminho)
                val durMs = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
                var w = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
                var h = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
                val giro = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
                if (giro == 90 || giro == 270) { val t = w; w = h; h = t }       // a tela mostra o vídeo já girado
                var fps = 0.0
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && durMs > 0) {
                    val n = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_FRAME_COUNT)?.toLongOrNull() ?: 0L
                    if (n > 0) fps = n * 1000.0 / durMs
                }
                responder(id, ok().put("duracao_s", durMs / 1000.0).put("largura", w).put("altura", h).put("fps", fps))
            } catch (e: Exception) {
                responder(id, erro("O Android não conseguiu abrir esse vídeo (${e.message})."))
            } finally {
                try { r.release() } catch (ignorado: Exception) {}
            }
        }
    }

    // grava f0001.jpg, f0002.jpg... na pasta pedida; devolve {n, fps}. O limite de tempo vale (aparelho fraco não trava).
    private fun videoQuadros(id: String, args: JSONObject) {
        val caminho = args.getString("caminho")
        val pasta = File(args.getString("pasta"))
        val inicioUs = (args.optDouble("inicio_s", 0.0) * 1_000_000).toLong()
        val fps = args.optDouble("fps", 15.0).coerceIn(0.5, 30.0)
        val maxQuadros = args.optInt("max_quadros", 180).coerceIn(1, 600)
        val maxLargura = args.optInt("max_largura", 854).coerceIn(64, 3840)
        val qualidade = args.optInt("qualidade", 80).coerceIn(30, 95)
        val limiteMs = (args.optDouble("tempo_limite_s", 90.0) * 1000).toLong()
        thread(name = "zenith-video-quadros") {
            val r = MediaMetadataRetriever()
            try {
                if (!pasta.isDirectory && !pasta.mkdirs()) { responder(id, erro("Não consegui criar a pasta dos quadros.")); return@thread }
                r.setDataSource(caminho)
                val durUs = (r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L) * 1000
                val fimUs = if (durUs > 0) durUs else Long.MAX_VALUE
                val passoUs = (1_000_000 / fps).toLong()
                val inicio = System.currentTimeMillis()
                var n = 0
                var falhas = 0
                var t = inicioUs
                while (n < maxQuadros && t < fimUs && System.currentTimeMillis() - inicio < limiteMs) {
                    val quadro = r.getFrameAtTime(t, MediaMetadataRetriever.OPTION_CLOSEST)
                    if (quadro == null) {                       // sem quadro nesse instante: tenta o próximo, mas não para sempre
                        falhas++
                        if (falhas > 20) break
                        t += passoUs
                        continue
                    }
                    val pronto = reduzir(quadro, maxLargura)
                    FileOutputStream(File(pasta, "f%04d.jpg".format(n + 1))).use { pronto.compress(Bitmap.CompressFormat.JPEG, qualidade, it) }
                    if (pronto !== quadro) quadro.recycle()
                    pronto.recycle()
                    n++
                    t += passoUs
                }
                responder(id, ok().put("n", n).put("fps", fps))
            } catch (e: Exception) {
                responder(id, erro("O Android não conseguiu ler os quadros desse vídeo (${e.message})."))
            } finally {
                try { r.release() } catch (ignorado: Exception) {}
            }
        }
    }

    // ---------- câmera (v1.19): Camera2 SEM prévia na tela. Tira `warmup` fotos descartáveis (o aparelho acerta foco e luz) e fica com a última. ----------
    // A permissão CAMERA é pedida pelo Godot (ponte_android.gd) ANTES de esta função ser chamada. A foto pode sair escura na 1ª vez.
    @Volatile private var cameraOcupada = false

    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    private fun capturarCamera(id: String, warmup: Int, maxW: Int) {
        if (cameraOcupada) { responder(id, erro("A câmera já está sendo usada por outro pedido. Tente de novo.")); return }
        val ctx = activity!!.applicationContext
        val gerente = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val idCamera = try {
            gerente.cameraIdList.firstOrNull {
                gerente.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
            } ?: gerente.cameraIdList.firstOrNull()
        } catch (e: Exception) { null }
        if (idCamera == null) { responder(id, erro("Este aparelho não tem câmera que eu consiga usar.")); return }
        val carac = gerente.getCameraCharacteristics(idCamera)
        val giro = carac.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0        // o app fica sempre em pé (retrato)
        val tamanhos = carac.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)?.getOutputSizes(ImageFormat.JPEG)
        val tam = tamanhos?.filter { it.width <= 1920 }?.maxByOrNull { it.width * it.height }
            ?: tamanhos?.minByOrNull { it.width * it.height }
        if (tam == null) { responder(id, erro("A câmera não informou um tamanho de foto.")); return }
        val temFoco = carac.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES)
            ?.contains(CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_PICTURE) == true

        cameraOcupada = true
        val fio = HandlerThread("zenith-camera").also { it.start() }
        val h = Handler(fio.looper)
        val leitor = ImageReader.newInstance(tam.width, tam.height, ImageFormat.JPEG, 2)
        val acabou = AtomicBoolean(false)
        var dispositivo: CameraDevice? = null
        var sessao: CameraCaptureSession? = null
        var restantes = warmup.coerceIn(0, 15)

        fun encerrar(r: JSONObject) {
            if (!acabou.compareAndSet(false, true)) return
            try { sessao?.close() } catch (ignorado: Exception) {}
            try { dispositivo?.close() } catch (ignorado: Exception) {}
            try { leitor.close() } catch (ignorado: Exception) {}
            fio.quitSafely()
            cameraOcupada = false
            responder(id, r)
        }

        h.postDelayed({ encerrar(erro("A câmera demorou demais para responder.")) }, 12_000)

        fun pedirFoto() {
            try {
                val s = sessao ?: return
                val d = dispositivo ?: return
                val pedido = d.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                    addTarget(leitor.surface)
                    set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
                    if (temFoco) set(CaptureRequest.CONTROL_AF_MODE, CameraMetadata.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                }.build()
                s.capture(pedido, null, h)
            } catch (e: Exception) {
                encerrar(erro("Não consegui tirar a foto (${e.message})."))
            }
        }

        leitor.setOnImageAvailableListener({ origem ->
            val img = try { origem.acquireNextImage() } catch (e: Exception) { null }
            if (img != null) {
                if (restantes > 0) {
                    restantes--
                    img.close()
                    pedirFoto()
                } else {
                    try {
                        val buf = img.planes[0].buffer
                        val bytes = ByteArray(buf.remaining())
                        buf.get(bytes)
                        img.close()
                        encerrar(ok().put("imagem", Base64.encodeToString(prepararFoto(bytes, giro, maxW), Base64.NO_WRAP)))
                    } catch (e: Exception) {
                        try { img.close() } catch (ignorado: Exception) {}
                        encerrar(erro("Não consegui ler a foto (${e.message})."))
                    }
                }
            }
        }, h)

        try {
            gerente.openCamera(idCamera, object : CameraDevice.StateCallback() {
                override fun onOpened(c: CameraDevice) {
                    dispositivo = c
                    try {
                        c.createCaptureSession(listOf(leitor.surface), object : CameraCaptureSession.StateCallback() {
                            override fun onConfigured(s: CameraCaptureSession) { sessao = s; pedirFoto() }
                            override fun onConfigureFailed(s: CameraCaptureSession) { encerrar(erro("A câmera não conseguiu se preparar.")) }
                        }, h)
                    } catch (e: Exception) {
                        encerrar(erro("Não consegui abrir a sessão da câmera (${e.message})."))
                    }
                }
                override fun onDisconnected(c: CameraDevice) { encerrar(erro("A câmera foi desconectada (outro app usando?).")) }
                override fun onError(c: CameraDevice, codigo: Int) { encerrar(erro("A câmera deu erro (código $codigo).")) }
            }, h)
        } catch (e: Exception) {
            encerrar(erro("Não consegui abrir a câmera (${e.message})."))
        }
    }

    // gira a foto (o sensor da câmera é "deitado"), reduz se pediram e devolve JPEG
    private fun prepararFoto(jpeg: ByteArray, giroGraus: Int, maxLargura: Int): ByteArray {
        val original = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: throw IOException("a foto veio ilegível")
        var b = original
        if (giroGraus != 0) {
            val m = Matrix().also { it.postRotate(giroGraus.toFloat()) }
            b = Bitmap.createBitmap(original, 0, 0, original.width, original.height, m, true)
            if (b !== original) original.recycle()
        }
        val reduzida = reduzir(b, maxLargura)
        if (reduzida !== b) b.recycle()
        val bytes = codificar(reduzida, true, 85)
        reduzida.recycle()
        return bytes
    }

    // ---------- tela (v1.19): MediaProjection ----------
    // O Android mostra a janela de permissão (1ª vez de cada sessão) e uma notificação enquanto captura. A sessão fica aberta
    // (o Android 14 só deixa criar UMA tela virtual por permissão) e se fecha sozinha depois de 2 min sem pedido, ou quando
    // a pessoa toca no ícone de captura do sistema.
    private val codigoCapturaTela = 4711
    private var projecao: MediaProjection? = null
    private var telaVirtual: VirtualDisplay? = null
    private var telaLeitor: ImageReader? = null
    private var telaUltima: Image? = null                  // o quadro mais recente, guardado sem converter (converter custa)
    private val travaTela = Any()
    private var pedidoTela: Triple<String, Int, Boolean>? = null     // (id, max_w, jpeg) esperando a pessoa autorizar
    private var telaOciosa: Runnable? = null
    private val fioTela by lazy { HandlerThread("zenith-tela").also { it.start() } }
    private val maoTela by lazy { Handler(fioTela.looper) }
    private val principal = Handler(Looper.getMainLooper())

    private fun capturarTela(id: String, maxW: Int, jpeg: Boolean) {
        if (telaVirtual != null) { entregarTela(id, maxW, jpeg); return }
        if (pedidoTela != null) { responder(id, erro("Já estou esperando você autorizar a captura de tela.")); return }
        val act = activity
        if (act == null) { responder(id, erro("O app não está aberto na frente agora.")); return }
        pedidoTela = Triple(id, maxW, jpeg)
        val gerente = act.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        act.runOnUiThread {
            try {
                act.startActivityForResult(gerente.createScreenCaptureIntent(), codigoCapturaTela)
            } catch (e: Exception) {
                falharPedidoTela("Não consegui abrir a janela de permissão da tela (${e.message}).")
            }
        }
    }

    override fun onMainActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onMainActivityResult(requestCode, resultCode, data)
        if (requestCode != codigoCapturaTela) return
        if (resultCode != Activity.RESULT_OK || data == null) { falharPedidoTela("Você não autorizou a captura de tela."); return }
        val ctx = activity?.applicationContext
        if (ctx == null) { falharPedidoTela("O app não está aberto na frente agora."); return }
        // O Android 14 só aceita o serviço em primeiro plano DEPOIS da permissão, e a projeção só DEPOIS de o serviço subir.
        ZenithCapturaService.aoFicarPronto = { subiu, motivo ->
            if (subiu) iniciarProjecao(resultCode, data) else falharPedidoTela(motivo)
        }
        try {
            val i = Intent(ctx, ZenithCapturaService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i) else ctx.startService(i)
        } catch (e: Exception) {
            ZenithCapturaService.aoFicarPronto = null
            falharPedidoTela("Não consegui iniciar o serviço da captura (${e.message}).")
        }
    }

    override fun onMainDestroy() {
        encerrarTela()
        super.onMainDestroy()
    }

    private fun falharPedidoTela(frase: String) {
        val p = pedidoTela
        pedidoTela = null
        if (p != null) responder(p.first, erro(frase))
    }

    private fun iniciarProjecao(resultCode: Int, data: Intent) {
        try {
            val ctx = activity!!.applicationContext
            val gerente = ctx.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            val p = gerente.getMediaProjection(resultCode, data)
            p.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() { encerrarTela() }
            }, maoTela)
            val m = ctx.resources.displayMetrics
            val esc = if (m.widthPixels > 1080) 1080f / m.widthPixels else 1f      // tela grande demais pesa à toa
            val w = (m.widthPixels * esc).toInt().coerceAtLeast(2)
            val h = (m.heightPixels * esc).toInt().coerceAtLeast(2)
            val leitor = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 3)
            leitor.setOnImageAvailableListener({ l ->
                val novo = try { l.acquireLatestImage() } catch (e: Exception) { null }
                if (novo != null) synchronized(travaTela) { telaUltima?.close(); telaUltima = novo }
            }, maoTela)
            val v = p.createVirtualDisplay("zenith-tela", w, h, (m.densityDpi * esc).toInt().coerceAtLeast(1),
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, leitor.surface, null, maoTela)
            projecao = p
            telaLeitor = leitor
            telaVirtual = v
            val pedido = pedidoTela
            pedidoTela = null
            agendarOciosidade()
            if (pedido != null) entregarTela(pedido.first, pedido.second, pedido.third)
        } catch (e: Exception) {
            encerrarTela()
            falharPedidoTela("Não consegui começar a captura da tela (${e.message}).")
        }
    }

    private fun entregarTela(id: String, maxW: Int, jpeg: Boolean) {
        agendarOciosidade()
        thread(name = "zenith-tela-quadro") {
            try {
                val limite = System.currentTimeMillis() + 2500
                var bmp: Bitmap? = null
                while (bmp == null && System.currentTimeMillis() < limite) {
                    synchronized(travaTela) { telaUltima?.let { bmp = imagemParaBitmap(it) } }
                    if (bmp == null) Thread.sleep(60)
                }
                val b = bmp
                if (b == null) { responder(id, erro("A tela não me mandou nenhum quadro agora. Tente de novo.")); return@thread }
                val reduzida = reduzir(b, maxW)
                val bytes = codificar(reduzida, jpeg, 85)
                if (reduzida !== b) b.recycle()
                reduzida.recycle()
                responder(id, ok().put("imagem", Base64.encodeToString(bytes, Base64.NO_WRAP)))
            } catch (e: Exception) {
                responder(id, erro("Não consegui ler a tela (${e.message})."))
            }
        }
    }

    private fun imagemParaBitmap(img: Image): Bitmap {
        val plano = img.planes[0]
        plano.buffer.rewind()
        val largLinha = plano.rowStride / plano.pixelStride
        val grande = Bitmap.createBitmap(largLinha, img.height, Bitmap.Config.ARGB_8888)
        grande.copyPixelsFromBuffer(plano.buffer)
        if (largLinha == img.width) return grande
        val certo = Bitmap.createBitmap(grande, 0, 0, img.width, img.height)
        grande.recycle()
        return certo
    }

    private fun agendarOciosidade() {
        telaOciosa?.let { principal.removeCallbacks(it) }
        val r = Runnable { encerrarTela() }
        telaOciosa = r
        principal.postDelayed(r, 120_000)
    }

    private fun encerrarTela() {
        telaOciosa?.let { principal.removeCallbacks(it) }
        telaOciosa = null
        val v = telaVirtual
        val p = projecao
        val l = telaLeitor
        telaVirtual = null                        // zera ANTES de soltar: projecao.stop() chama onStop(), que chama esta função de novo
        projecao = null
        telaLeitor = null
        synchronized(travaTela) {
            try { telaUltima?.close() } catch (ignorado: Exception) {}
            telaUltima = null
        }
        try { v?.release() } catch (ignorado: Exception) {}
        try { p?.stop() } catch (ignorado: Exception) {}
        try { l?.close() } catch (ignorado: Exception) {}
        val ctx = activity?.applicationContext
        if (ctx != null) try { ctx.stopService(Intent(ctx, ZenithCapturaService::class.java)) } catch (ignorado: Exception) {}
    }

    // ---------- respostas ----------
    private fun ok() = JSONObject().put("ok", true)
    private fun erro(frase: String) = JSONObject().put("ok", false).put("erro", frase)
    private fun responder(id: String, r: JSONObject) = emitSignal("resposta", id, r.toString())
}
