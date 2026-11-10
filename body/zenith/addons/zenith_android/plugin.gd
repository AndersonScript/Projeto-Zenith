@tool
extends EditorPlugin
# Plugin v2 do Godot (4.2+): o editor empacota o AAR do plugin Android e suas dependências no APK.
# O AAR é gerado por android_plugin/ (Gradle) e copiado para bin/debug e bin/release. Sem ele, o export Android sai SEM
# plugin: o app abre, mas sem microfone/voz do aparelho (o Corpo avisa no log: "Plugin Android ... não encontrado").

var export_plugin: AndroidExportPlugin

func _enter_tree() -> void:
	export_plugin = AndroidExportPlugin.new()
	add_export_plugin(export_plugin)

func _exit_tree() -> void:
	remove_export_plugin(export_plugin)
	export_plugin = null

class AndroidExportPlugin extends EditorExportPlugin:
	const NOME := "ZenithAndroid"
	# Mantenha IGUAL ao voskVersion de android_plugin/build.gradle.kts.
	const VOSK := "com.alphacephei:vosk-android:0.3.75"
	const ANDROIDX_CORE := "androidx.core:core:1.13.1"      # igual ao androidxCore do build.gradle.kts

	func _supports_platform(platform: EditorExportPlatform) -> bool:
		return platform is EditorExportPlatformAndroid

	# Caminhos RELATIVOS à pasta addons/.
	# Se o AAR ainda NÃO foi compilado (android_plugin/ -> tarefa copiarAAR), o APK sai SEM o plugin em vez de o export falhar:
	# assim dá para fazer a Prova 1 (o avatar abre no celular?) antes de compilar o Kotlin. Sem plugin o app abre, mas sem
	# microfone, voz e notificações do aparelho.
	func _aar(debug: bool) -> String:
		return ("zenith_android/bin/debug/" + NOME + "-debug.aar") if debug else ("zenith_android/bin/release/" + NOME + "-release.aar")

	func _aar_existe(debug: bool) -> bool:
		return FileAccess.file_exists("res://addons/" + _aar(debug))

	func _get_android_libraries(platform: EditorExportPlatform, debug: bool) -> PackedStringArray:
		if not _aar_existe(debug):
			push_warning("[Zenith Android] %s não encontrado: o APK sai SEM o plugin (rode a tarefa copiarAAR em android_plugin/)." % _aar(debug))
			return PackedStringArray()
		return PackedStringArray([_aar(debug)])

	# O AAR não embute dependências: o Godot as baixa da Maven Central ao montar o APK. Sem o AAR não há quem as use.
	func _get_android_dependencies(platform: EditorExportPlatform, debug: bool) -> PackedStringArray:
		if not _aar_existe(debug):
			return PackedStringArray()
		return PackedStringArray([VOSK, ANDROIDX_CORE])

	func _get_name() -> String:
		return NOME
