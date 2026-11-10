"""Fala -> texto no celular (v1.12): o plugin usa o VOSK, não o reconhecedor do Android.

Por quê: o Cérebro grava o microfone pela ponte e manda ÁUDIO PRONTO a cada ~1 s pedindo o texto (é o que faz o texto
aparecer enquanto a pessoa fala). O reconhecedor do Android não recebe áudio pronto — ele abre o microfone sozinho —,
então brigaria com o Cérebro pelo microfone. O Vosk aceita áudio pronto e funciona sem internet.

Não há Android nem Gradle aqui: estes testes só conferem o TEXTO do plugin e do README. NÃO provam que o Vosk roda
no celular — provam que as peças combinam e que ninguém desfaz a decisão sem querer.

    python -m unittest tests.test_port_celular_stt
"""
from __future__ import annotations

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = RAIZ / "android_plugin"
KOTLIN = PLUGIN / "src" / "main" / "kotlin" / "com" / "zenith" / "android" / "ZenithAndroidPlugin.kt"
README = PLUGIN / "README.md"


def ler(p):
    if not p.exists():
        raise unittest.SkipTest(f"{p.name} não está neste pacote")
    return p.read_text(encoding="utf-8")


class TranscricaoComVosk(unittest.TestCase):
    def test_o_plugin_trata_a_chamada_e_usa_a_api_do_vosk_que_aceita_audio_pronto(self):
        kt = ler(KOTLIN)
        self.assertIn('"stt.transcrever" ->', kt)
        for nome in ("import org.vosk.Model", "import org.vosk.Recognizer", "acceptWaveForm", "finalResult"):
            self.assertIn(nome, kt)

    def test_nao_voltou_para_o_reconhecedor_do_android(self):
        # esse caminho abre o microfone sozinho: não encaixa no contrato (o Cérebro entrega o áudio gravado)
        self.assertNotIn("SpeechRecognizer", ler(KOTLIN))

    def test_transcricao_so_e_anunciada_quando_o_modelo_existe(self):
        kt = ler(KOTLIN)
        corpo = re.search(r"fun capacidades\(\).*?\.toString\(\)", kt, re.S).group(0)
        self.assertIn("if (transcricaoDisponivel())", corpo)
        fixa = re.search(r"mutableListOf\((.*?)\)", corpo, re.S).group(1)
        self.assertNotIn("transcricao", fixa, "transcricao não pode estar na lista fixa: sem modelo o Cérebro pediria e falharia")
        self.assertRegex(kt, r"private fun transcricaoDisponivel\(\): Boolean = !voskQuebrado && pastaModeloVosk\(\) != null")

    def test_falha_da_biblioteca_nativa_para_de_anunciar_e_responde_em_portugues(self):
        kt = ler(KOTLIN)
        self.assertIn("UnsatisfiedLinkError", kt)
        self.assertIn("voskQuebrado = true", kt)
        self.assertIn("O modelo de fala em português ainda não está neste aparelho.", kt)

    def test_audio_de_16_bits_com_byte_solto_nao_quebra(self):
        self.assertIn("pcm.size % 2", ler(KOTLIN))

    def test_a_pasta_do_modelo_e_a_mesma_no_plugin_e_no_readme(self):
        self.assertIn('"modelos/vosk-pt"', ler(KOTLIN))
        self.assertIn("modelos/vosk-pt", ler(README))

    def test_o_readme_diz_de_onde_vem_a_biblioteca_e_que_nada_foi_compilado(self):
        md = ler(README)
        self.assertIn("com.alphacephei:vosk-android", md)
        self.assertIn("NÃO COMPILADO", md.upper())


if __name__ == "__main__":
    unittest.main()
