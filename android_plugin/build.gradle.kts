// NÃO COMPILADO. Biblioteca Android (AAR) do plugin do Zenith.
// As VERSÕES abaixo são as que eu escolhi (não verifiquei se combinam): se o Android Studio reclamar, use as que ele sugerir.
// A versão do Godot tem de ser IGUAL à do editor que vai exportar o APK (aqui, 4.7.1) e existir na Maven Central.
plugins {
    id("com.android.library") version "8.7.3"
    kotlin("android") version "2.0.21"
}

val godotVersion = "4.7.1.stable"
val voskVersion = "0.3.75"
val androidxCore = "1.13.1"

android {
    namespace = "com.zenith.android"
    compileSdk = 35
    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // A biblioteca do Godot fica na Maven Central (vem junto no APK pelo próprio Godot).
    implementation("org.godotengine:godot:$godotVersion")
    // Reconhecimento de fala offline. O AAR NÃO embute estas dependências: o script do editor
    // (body/zenith/addons/zenith_android/plugin.gd) as repassa ao Godot, que as põe no APK.
    implementation("com.alphacephei:vosk-android:$voskVersion")
    implementation("androidx.core:core:$androidxCore")      // NotificationCompat (notificações)
}

// Copia os AARs prontos para o addon do Corpo, que é onde o Godot os procura.
val destinoDoCorpo = layout.projectDirectory.dir("../body/zenith/addons/zenith_android/bin")
tasks.register<Copy>("copiarAARDebug") {
    dependsOn("assembleDebug")
    from(layout.buildDirectory.dir("outputs/aar")) { include("*-debug.aar") }
    into(destinoDoCorpo.dir("debug"))
}
tasks.register<Copy>("copiarAARRelease") {
    dependsOn("assembleRelease")
    from(layout.buildDirectory.dir("outputs/aar")) { include("*-release.aar") }
    into(destinoDoCorpo.dir("release"))
}
tasks.register("copiarAAR") { dependsOn("copiarAARDebug", "copiarAARRelease") }
