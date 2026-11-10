"""Contratos da v1.14 (port celular): plugin v2, Gradle, preset Android, project.godot, Corpo e auditoria de Windows.

Tudo aqui é TEXTO e estrutura: não há Android, Gradle nem JDK neste teste. Serve para as peças não se separarem (nome do plugin
no manifesto x Kotlin x addon do editor, versões iguais, eventos do baixador) e para ninguém reintroduzir chamadas de Windows
sem proteção. NÃO prova que o APK compila ou roda.

    python -m unittest tests.test_port_celular_fase3
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = RAIZ / "android_plugin"
CORPO = RAIZ / "body" / "zenith"
KOTLIN = PLUGIN / "src" / "main" / "kotlin" / "com" / "zenith" / "android" / "ZenithAndroidPlugin.kt"


def ler(p):
    if not p.exists():
        raise unittest.SkipTest(f"{p.name} não está neste pacote")
    return p.read_text(encoding="utf-8")


class PluginV2(unittest.TestCase):
    def test_o_manifesto_declara_o_plugin_com_o_nome_e_a_classe_certos(self):
        m = ler(PLUGIN / "src" / "main" / "AndroidManifest.xml")
        nome = re.search(r'org\.godotengine\.plugin\.v2\.(\w+)', m).group(1)
        classe = re.search(r'android:value="([\w.]+)"', m.split("plugin.v2")[1]).group(1)
        kt = ler(KOTLIN)
        self.assertEqual(classe, "com.zenith.android.ZenithAndroidPlugin")
        self.assertIn("package com.zenith.android", kt)
        self.assertIn(f'"{nome}"', kt, "o nome do manifesto tem de ser o getPluginName() do Kotlin")
        self.assertIn(f'NOME := "{nome}"', ler(CORPO / "addons" / "zenith_android" / "plugin.gd"))
        self.assertIn(f'rootProject.name = "{nome}"', ler(PLUGIN / "settings.gradle.kts"))

    def test_o_manifesto_nao_usa_package_que_o_gradle_atual_recusa(self):
        self.assertNotRegex(ler(PLUGIN / "src" / "main" / "AndroidManifest.xml"), r"<manifest[^>]*\spackage=")
        self.assertIn('namespace = "com.zenith.android"', ler(PLUGIN / "build.gradle.kts"))

    def test_as_versoes_do_gradle_e_do_addon_sao_as_mesmas(self):
        g, a = ler(PLUGIN / "build.gradle.kts"), ler(CORPO / "addons" / "zenith_android" / "plugin.gd")
        vosk = re.search(r'val voskVersion = "([^"]+)"', g).group(1)
        core = re.search(r'val androidxCore = "([^"]+)"', g).group(1)
        self.assertIn(f"com.alphacephei:vosk-android:{vosk}", a)
        self.assertIn(f"androidx.core:core:{core}", a)

    def test_toda_biblioteca_que_o_kotlin_importa_esta_declarada(self):
        kt, g = ler(KOTLIN), ler(PLUGIN / "build.gradle.kts")
        if "import androidx.core" in kt:
            self.assertIn("androidx.core:core", g)           # o 1º rascunho esqueceu esta (NotificationCompat)
        if "import org.vosk" in kt:
            self.assertIn("vosk-android", g)
        if "import org.godotengine" in kt:
            self.assertIn("org.godotengine:godot", g)

    def test_o_addon_aponta_para_os_aars_que_o_gradle_gera(self):
        a, g = ler(CORPO / "addons" / "zenith_android" / "plugin.gd"), ler(PLUGIN / "build.gradle.kts")
        self.assertIn('zenith_android/bin/debug/" + NOME + "-debug.aar', a)
        self.assertIn('zenith_android/bin/release/" + NOME + "-release.aar', a)
        # sem o AAR compilado o export NÃO falha: o APK sai sem o plugin (Prova 1 sem compilar o Kotlin)
        self.assertIn("FileAccess.file_exists", a)
        self.assertIn("return PackedStringArray()", a)
        self.assertIn("addons/zenith_android/bin", g)
        self.assertIn('"copiarAAR"', g)

    def test_o_addon_esta_ligado_no_project_godot(self):
        self.assertIn("res://addons/zenith_android/plugin.cfg", ler(CORPO / "project.godot"))

    def test_as_permissoes_do_bluetooth_estao_no_manifesto_e_no_mapa_do_godot(self):
        m, gd = ler(PLUGIN / "src" / "main" / "AndroidManifest.xml"), ler(CORPO / "ponte_android.gd")
        mapa = re.search(r'"ble\.enviar":\s*"([^"]+)"', gd).group(1)
        for perm in mapa.split("|"):
            self.assertIn(f"android.permission.{perm}", m)

    def test_os_eventos_do_baixador_sao_os_mesmos_no_kotlin_no_godot_e_na_tela(self):
        kt, gd, lay = ler(KOTLIN), ler(CORPO / "ponte_android.gd"), ler(CORPO / "zenith_layout_celular.gd")
        for ev in ("modelo.progresso", "modelo.pronto", "modelo.erro"):
            self.assertIn(f'"{ev}"', kt)
            self.assertIn(f'"{ev}"', lay)
        self.assertIn('nome.begins_with("modelo.")', gd)
        self.assertIn('"modelo.baixar"', kt)
        self.assertIn('"modelo.estado"', kt)
        self.assertIn("_anunciar_capacidades()", gd.split('nome == "modelo.pronto"')[1][:200])   # no "pronto" o Cérebro é avisado


class ProjetoAndroid(unittest.TestCase):
    def test_project_godot_esta_pronto_para_o_celular_sem_mudar_o_pc(self):
        p = ler(CORPO / "project.godot")
        for linha in ("window/handheld/orientation=1", "config/quit_on_go_back=false",
                      "textures/vram_compression/import_etc2_astc=true", "window/subwindows/embed_subwindows.android=true"):
            self.assertIn(linha, p)
        # o que é do PC continua valendo no PC: as trocas do Android são só com o sufixo .android
        self.assertIn("window/subwindows/embed_subwindows=false", p)

    def test_o_preset_android_existe_em_pe_e_sem_o_estilo_antigo_de_plugin(self):
        e = ler(CORPO / "export_presets.cfg")
        self.assertIn('platform="Android"', e)
        for linha in ("gradle_build/use_gradle_build=true", "architectures/arm64-v8a=true",
                      "permissions/internet=true", "permissions/record_audio=true"):
            self.assertIn(linha, e)
        self.assertNotIn("plugins/ZenithAndroid=true", e)    # estilo v1 (.gdap), obsoleto


class CorpoNoCelular(unittest.TestCase):
    def test_o_corpo_nao_mexe_em_janela_de_pc_no_android(self):
        b = ler(CORPO / "akira_body.gd")
        self.assertGreaterEqual(b.count('if OS.get_name() != "Android": '), 6)
        for funcao in ("func update_window_properties", "func _mov_aplicar_janela"):
            self.assertIn('OS.get_name() == "Android"', b.split(funcao)[1].split("\nfunc ")[0])

    def test_a_fase_3_do_layout_existe_e_esta_ligada(self):
        lay = ler(CORPO / "zenith_layout_celular.gd")
        for trecho in ("func deslocamento_da_camera", "func _enquadrar_avatar", "func voltar()", "func _ciclo_teclado",
                       "_enquadrar_avatar.call_deferred()", "_ligar_voltar()", "_iniciar_teclado()"):
            self.assertIn(trecho, lay)

    def test_voltar_nao_fecha_a_aprovacao_de_acao(self):
        corpo = ler(CORPO / "zenith_layout_celular.gd").split("func voltar()")[1].split("\nfunc ")[0]
        self.assertIn("approval_overlay", corpo)
        self.assertLess(corpo.index("approval_overlay"), corpo.index("settings_overlay"))

    def test_hide_overlay_recebe_so_um_argumento(self):
        # erro do 1º rascunho: o layout chamava _hide_overlay(overlay, card)
        self.assertRegex(ler(CORPO / "ui_manager.gd"), r"func _hide_overlay\(overlay: Control\):")
        self.assertIn("ui._hide_overlay(overlay)", ler(CORPO / "zenith_layout_celular.gd"))


class AuditoriaDeWindows(unittest.TestCase):
    """Auditoria da v1.14: nenhum módulo do Cérebro chama o Windows direto sem proteção.
    Se este teste falhar, uma chamada nova de Windows apareceu: proteja-a (checagem de sistema ou try/except) e só depois a
    acrescente à lista abaixo, com o motivo."""
    PROTEGIDOS_STARTFILE = {"zenith_atualizar.py", "zenith_plataforma_pc.py", "zenith_projetos.py"}
    PROTEGIDOS_WINDLL = {"zenith_admin.py", "zenith_captura.py", "zenith_janela.py", "zenith_desempenho.py", "zenith_diag.py"}

    def _arquivos(self):
        pasta = RAIZ / "brain"
        if not pasta.exists():
            self.skipTest("brain/ não está neste pacote")
        return sorted(pasta.glob("*.py"))

    def test_startfile_so_nos_modulos_revisados(self):
        achou = {f.name for f in self._arquivos() if re.search(r"\bos\.startfile\(", f.read_text(encoding="utf-8", errors="replace"))}
        self.assertLessEqual(achou, self.PROTEGIDOS_STARTFILE, f"os.startfile novo sem revisão: {achou - self.PROTEGIDOS_STARTFILE}")

    def test_windll_so_nos_modulos_revisados(self):
        achou = {f.name for f in self._arquivos() if "windll" in f.read_text(encoding="utf-8", errors="replace")}
        self.assertLessEqual(achou, self.PROTEGIDOS_WINDLL, f"windll novo sem revisão: {achou - self.PROTEGIDOS_WINDLL}")

    def test_nenhuma_flag_de_processo_so_do_windows_sem_getattr(self):
        ruins = []
        for f in self._arquivos():
            for n, linha in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.search(r"subprocess\.(CREATE_[A-Z_]+|DETACHED_PROCESS|STARTUPINFO|STARTF_)", linha) and "getattr" not in linha:
                    ruins.append(f"{f.name}:{n}")
        self.assertEqual(ruins, [], "flag de processo do Windows sem getattr quebra no Android")

    def test_admin_captura_e_janela_degradam_sem_erro_fora_do_windows(self):
        from brain import zenith_admin, zenith_captura, zenith_janela
        for plataforma in ("linux", "android"):
            with mock.patch.object(sys, "platform", plataforma), mock.patch.object(os, "name", "posix"):
                self.assertIsNone(zenith_admin.e_admin())
                self.assertEqual(zenith_admin.decidir(tempfile.mkdtemp()), "nada")
                self.assertFalse(zenith_admin.reabrir_como_admin())
                self.assertEqual(zenith_captura.titulo_ativo(), "")
                self.assertFalse(zenith_janela.suportado())
                ok, _msg = zenith_janela.definir_clique_atravessa(1, True)
                self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
