"""Os TRÊS lados da ponte têm que falar a mesma língua: Python (Cérebro), GDScript (Corpo) e Kotlin (plugin Android).

Não há Godot nem Android aqui para executar o Corpo e o plugin, então estes testes conferem o TEXTO dos arquivos —
o mesmo estilo que o projeto já usa para o Godot (tests/test_v28.py). Eles não provam que funciona; provam que os
nomes combinam, para uma divergência (um nome trocado numa ponta) quebrar AQUI e não no celular de alguém.

    python -m unittest tests.test_port_celular_godot
"""
from __future__ import annotations

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
GD = RAIZ / "body" / "zenith" / "ponte_android.gd"
CONECTOR = RAIZ / "body" / "zenith" / "brain_connector.gd"
KOTLIN = RAIZ / "android_plugin" / "src" / "main" / "kotlin" / "com" / "zenith" / "android" / "ZenithAndroidPlugin.kt"
MANIFESTO = RAIZ / "android_plugin" / "src" / "main" / "AndroidManifest.xml"
PY_ANDROID = RAIZ / "brain" / "zenith_plataforma_android.py"
PY_PONTE = RAIZ / "brain" / "zenith_ponte_corpo.py"
PY_HEADLESS = RAIZ / "brain" / "zenith_headless.py"
UI = RAIZ / "body" / "zenith" / "ui_manager.gd"
PAGINA = RAIZ / "body" / "zenith" / "zenith_desempenho_page.gd"
APLICADOR = RAIZ / "body" / "zenith" / "zenith_desempenho_aplicar.gd"

# capacidade -> chamadas que o Python faz para ela (o contrato)
CONTRATO = {
    "sistema": {"sistema.medir"},
    "audio_saida": {"audio.tocar", "audio.parar", "audio.ocupado"},
    "voz_local": {"tts.sintetizar"},
    "microfone": {"mic.iniciar", "mic.parar"},
    "notificacao": {"notificacao.mostrar"},
    "abrir": {"app.abrir"},
    "transcricao": {"stt.transcrever"},
    "tela": {"tela.capturar"},
    "camera": {"camera.capturar"},
    "ble": {"ble.enviar"},
    "llm_local": {"llm.endereco"},
    "video": {"video.info", "video.quadros"},
}
# v1.12: "transcricao" passou a existir (Vosk). v1.19: "tela", "camera" e "video" passaram a existir (escritos, nunca compilados).
NAO_IMPLEMENTADAS_NO_PLUGIN = {"llm_local"}


def ler(p):
    if not p.exists():
        raise unittest.SkipTest(f"{p.name} não está neste pacote")
    return p.read_text(encoding="utf-8")


class ContratoPythonKotlin(unittest.TestCase):
    def test_o_python_so_pede_o_que_o_contrato_conhece(self):
        usadas = set(re.findall(r'(?:_chamar|_imagem)\([^)]*?"([a-z_]+\.[a-z_]+)"', ler(PY_ANDROID)))
        usadas |= set(re.findall(r'_chamar\("([a-z_]+\.[a-z_]+)"', ler(PY_ANDROID)))
        usadas.discard("capacidades.listar")                  # essa é respondida localmente pela PonteCorpo
        esperadas = set().union(*CONTRATO.values())
        self.assertEqual(usadas, esperadas, "O Python passou a pedir (ou deixou de pedir) algo fora do contrato.")

    def test_o_plugin_implementa_toda_chamada_das_capacidades_que_anuncia(self):
        kt = ler(KOTLIN)
        anunciadas = set(re.findall(r'"([a-z_]+)"', re.search(r"fun capacidades\(\).*?\.toString\(\)", kt, re.S).group(0)))
        anunciadas.discard("capacidades")
        self.assertTrue(anunciadas, "o plugin não anuncia nada?")
        desconhecidas = anunciadas - set(CONTRATO)
        self.assertEqual(desconhecidas, set(), "o plugin anuncia capacidade que o Cérebro não conhece")
        for cap in anunciadas:
            for chamada in CONTRATO[cap]:
                self.assertIn(f'"{chamada}"', kt, f"o plugin anuncia '{cap}' mas não trata '{chamada}'")

    def test_o_plugin_nao_anuncia_o_que_nao_implementou(self):
        kt = ler(KOTLIN)
        anunciadas = set(re.findall(r'"([a-z_]+)"', re.search(r"fun capacidades\(\).*?\.toString\(\)", kt, re.S).group(0)))
        self.assertEqual(anunciadas & NAO_IMPLEMENTADAS_NO_PLUGIN, set())
        for cap in NAO_IMPLEMENTADAS_NO_PLUGIN:
            for chamada in CONTRATO[cap]:
                self.assertNotIn(f'"{chamada}" ->', kt, f"'{chamada}' parece implementada: anuncie '{cap}' e atualize este teste")

    def test_nomes_do_plugin_batem_nos_tres_lados(self):
        kt, gd, mf = ler(KOTLIN), ler(GD), ler(MANIFESTO)
        self.assertIn('getPluginName() = "ZenithAndroid"', kt)
        self.assertIn('NOME_PLUGIN := "ZenithAndroid"', gd)
        self.assertIn("org.godotengine.plugin.v2.ZenithAndroid", mf)
        self.assertIn("com.zenith.android.ZenithAndroidPlugin", mf)
        self.assertIn("package com.zenith.android", kt)
        for sinal in ("resposta", "evento"):
            self.assertIn(f'SignalInfo("{sinal}"', kt)
            self.assertIn(f'_plugin.connect("{sinal}"', gd)

    def test_permissoes_pedidas_no_godot_existem_no_manifesto_e_nas_chamadas(self):
        gd, mf, kt = ler(GD), ler(MANIFESTO), ler(KOTLIN)
        ainda_nao = set().union(*(CONTRATO[c] for c in NAO_IMPLEMENTADAS_NO_PLUGIN))
        for chamada, permissao in re.findall(r'"([a-z_]+\.[a-z_]+)": "([A-Z_]+)"', gd):
            if chamada in ainda_nao:                           # o Godot já sabe pedir a permissão; o plugin ainda não tem a chamada
                continue
            self.assertIn(f'"{chamada}"', kt)
            self.assertIn(f"android.permission.{permissao}", mf)


class ContratoPythonGodot(unittest.TestCase):
    def test_mensagens_da_ponte_tem_o_mesmo_nome_nos_dois_lados(self):
        py, gd, con = ler(PY_PONTE), ler(GD), ler(CONECTOR)
        for acao in ("ponte_chamar", "ponte_resposta", "ponte_evento", "ponte_pedir_capacidades"):
            self.assertIn(f'"{acao}"', py, f"{acao} sumiu do Python")
            self.assertIn(acao, gd + con, f"{acao} sumiu do Godot")
        self.assertIn('"capacidades"', py)
        self.assertIn('"evento": "capacidades"', gd)

    def test_formato_das_mensagens_que_o_godot_manda(self):
        gd = ler(GD)
        self.assertIn('{"action": "ponte_resposta", "id": id, "resposta": resposta}', gd)
        self.assertIn('{"action": "ponte_evento", "evento": nome, "dados": dado}', gd)
        self.assertIn('{"action": "ponte_evento", "evento": "capacidades", "dados": {"lista": lista}}', gd)

    def test_conector_so_liga_a_ponte_no_android(self):
        con = ler(CONECTOR)
        self.assertIn('signal ponte_mensagem(dados)', con)
        self.assertRegex(con, r'"ponte_chamar", "ponte_pedir_capacidades":\r?\n\t+emit_signal\("ponte_mensagem", data\)')
        corpo = re.search(r"func _iniciar_ponte_android\(\):(.*?)\r?\nfunc ", con, re.S).group(1)
        self.assertLess(corpo.index('OS.get_name() != "Android"'), corpo.index("load("),
                        "o carregamento da ponte tem que vir DEPOIS do teste de plataforma: no PC nada carrega")
        self.assertIn('load("res://ponte_android.gd")', corpo)
        self.assertRegex(con, r"_try_connect\(\)\r?\n\t_iniciar_ponte_android\(\)")


class EstiloGDScript(unittest.TestCase):
    def test_gdscript_indenta_so_com_tab(self):
        for arq in (GD, CONECTOR, PAGINA, APLICADOR):
            for n, linha in enumerate(ler(arq).splitlines(), 1):
                self.assertFalse(re.match(r"^ +\S", linha) and not linha.lstrip().startswith("#"),
                                 f"{arq.name}:{n} indenta com espaço (o Godot não aceita misturar com tab)")

    def test_conector_manteve_as_quebras_de_linha_do_projeto(self):
        bruto = CONECTOR.read_bytes()
        self.assertEqual(bruto.count(b"\n"), bruto.count(b"\r\n"), "brain_connector.gd misturou LF com CRLF")

    def test_ponte_nao_chama_nada_que_so_existe_no_pc(self):
        gd = ler(GD)
        for proibido in ("DisplayServer.window", "OS.shell_open", "FileDialog"):
            self.assertNotIn(proibido, gd)



class DesempenhoPythonGodot(unittest.TestCase):
    """A tela de Desempenho: Python (zenith_downgrade + headless) e GDScript (página, aplicador, conector, ui_manager)."""

    def test_mensagens_tem_o_mesmo_nome_nos_dois_lados(self):
        py, con = ler(PY_HEADLESS), ler(CONECTOR)
        for acao in ("desempenho_pedir", "desempenho_aplicar", "desempenho_estado", "desempenho_config"):
            self.assertIn(f'"{acao}"', py, f"{acao} sumiu do Cérebro")
            self.assertIn(f'"{acao}"', con, f"{acao} sumiu do conector")

    def test_conector_tem_os_sinais_e_os_pedidos_que_a_pagina_usa(self):
        con, pag = ler(CONECTOR), ler(PAGINA)
        self.assertIn("signal desempenho_estado(dados)", con)
        self.assertIn("signal desempenho_config(dados)", con)
        for metodo in ("request_desempenho", "aplicar_desempenho"):
            self.assertIn(f"func {metodo}(", con)
            self.assertIn(f"brain.{metodo}(", pag)
            self.assertIn(f'has_method("{metodo}")', pag)

    def test_a_pagina_cobre_todos_os_recursos_e_todos_os_valores(self):
        from brain import zenith_downgrade as dg
        pag = ler(PAGINA)
        ordem = re.search(r"const ORDEM := \[(.*?)\]", pag, re.S).group(1)
        self.assertEqual(set(re.findall(r'"([a-z_]+)"', ordem)), set(dg.RECURSOS), "a tela não cobre todos os recursos")
        nomes = re.search(r"const NOMES := \{(.*?)\n\}", pag, re.S).group(1)
        tem_nome = set(re.findall(r'"([a-z]+)":', nomes))
        for chave, valores in dg.RECURSOS.items():
            for valor in valores:
                if isinstance(valor, str):
                    self.assertIn(valor, tem_nome, f"falta o texto para '{valor}' ({chave}) na tela")

    def test_a_sugestao_so_move_a_escolha_e_nao_aplica(self):
        pag = ler(PAGINA)
        corpo = re.search(r"func _usar_sugestao\(\).*?\n\nfunc ", pag, re.S).group(0)
        self.assertNotIn("aplicar_desempenho", corpo, "a sugestão não pode aplicar sozinha")
        self.assertIn("Aperte Aplicar", corpo)

    def test_avatar_nao_finge_que_funciona(self):
        # O princípio (v1.11): a tela NÃO mostra um controle ligado que não faz nada. Enquanto o Corpo não trocava de avatar, o
        # seletor ficava desligado. Desde a v1.17 o Corpo troca (avatar simples): então ele só pode estar ligado se a troca existir.
        pag = ler(PAGINA)
        self.assertIn('if chave == "avatar":', pag)
        pasta = PAGINA.parent
        troca_existe = ("func usar_avatar_simples(" in ler(pasta / "akira_body.gd")
                        and "usar_avatar_simples" in ler(pasta / "zenith_desempenho_aplicar.gd"))
        seletor_desligado = "seletor.disabled = true" in pag
        self.assertNotEqual(troca_existe, seletor_desligado,
                            "seletor de avatar ligado sem troca no Corpo (finge) ou desligado mesmo com a troca pronta")

    def test_ui_manager_carrega_a_tela_de_forma_defensiva(self):
        ui = ler(UI)
        self.assertNotIn('preload("res://zenith_desempenho', ui, "preload quebraria a ui inteira se o arquivo falhar")
        self.assertIn('load(caminho)', ui)
        self.assertIn("can_instantiate()", ui)
        self.assertIn('_script_opcional("res://zenith_desempenho_page.gd")', ui)
        self.assertIn('_script_opcional("res://zenith_desempenho_aplicar.gd")', ui)
        self.assertRegex(ui, r"_montar_desempenho\(v\)[^\n]*\r?\n\r?\n\t_section\(v, \"Créditos\"\)")

    def test_ui_manager_manteve_as_quebras_de_linha_do_projeto(self):
        bruto = UI.read_bytes()
        self.assertEqual(bruto.count(b"\n"), bruto.count(b"\r\n"), "ui_manager.gd misturou LF com CRLF")

    def test_o_aplicador_so_toca_no_que_e_do_corpo(self):
        ap = ler(APLICADOR)
        self.assertIn("Engine.max_fps", ap)
        for nao_e_do_corpo in ("voice", "microphone", "permissions", "ia_local"):
            self.assertNotIn(nao_e_do_corpo, ap)


if __name__ == "__main__":
    unittest.main()
