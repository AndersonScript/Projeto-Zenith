// ============================================================
//  ZENITH — Criado por Anderson
//  ZenithCapturaService.kt — v1.19 (port celular)
//
//  >>> NÃO FOI COMPILADO NEM EXECUTADO. <<<
//
//  O Android EXIGE um serviço em primeiro plano (com notificação visível) enquanto a tela está sendo capturada pela
//  MediaProjection. Este serviço não captura nada: só existe para o Android deixar o plugin capturar. Quem avisa o plugin de que
//  o serviço subiu é o `aoFicarPronto` (o plugin só cria a projeção DEPOIS disso — regra do Android 14).
// ============================================================
package com.zenith.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ZenithCapturaService : Service() {

    companion object {
        /** (subiu, motivo): chamado UMA vez, logo depois de o serviço virar "primeiro plano" (ou de falhar). */
        @Volatile var aoFicarPronto: ((Boolean, String) -> Unit)? = null
        private const val CANAL = "zenith_captura"
        private const val NOTIFICACAO = 4712
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(NotificationChannel(CANAL, "Captura de tela", NotificationManager.IMPORTANCE_LOW))
        }
        val aviso = NotificationCompat.Builder(this, CANAL)
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("Zenith")
            .setContentText("Estou vendo a tela porque você pediu.")
            .setOngoing(true)
            .build()
        val acao = aoFicarPronto
        aoFicarPronto = null
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICACAO, aviso, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
            } else {
                startForeground(NOTIFICACAO, aviso)
            }
        } catch (e: Exception) {
            acao?.invoke(false, "O Android não deixou a captura de tela começar (${e.message}).")
            stopSelf()
            return START_NOT_STICKY
        }
        acao?.invoke(true, "")
        return START_NOT_STICKY
    }
}
