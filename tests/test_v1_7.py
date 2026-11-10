"""v1.7 — presença em vídeo, microfone contínuo, programas testados, outras linguagens, cadernos,
PC medido e movimentos com ritmo/fila/escala. Tudo com falsos: sem câmera, sem microfone, sem rede,
sem Godot e sem tocar em `config/` (cada teste usa a sua pasta temporária)."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                      # noqa: E402
_stubs.instalar()
from brain import zenith_presenca as P        # noqa: E402
from brain import zenith_programa as PROG     # noqa: E402
from brain import zenith_linguagens as LING   # noqa: E402
from brain import zenith_cadernos as CAD      # noqa: E402
from brain import zenith_desempenho as DES    # noqa: E402
from brain import zenith_movimentos as MOV    # noqa: E402
from brain import zenith_commands as CMD      # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="zenith_v17_"))
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)


def _png(cor=(120, 60, 200), lado=8):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (lado, lado), cor).save(b, format="PNG")
    return b.getvalue()


# ============================================================================================= T3
class PresencaTests(_Tmp):
    def test_janela_sensivel_reconhece_senha_banco_e_pagamento(self):
        for titulo in ("1Password — Login", "Bitwarden", "Nubank - conta", "Pix - transferir",
                       "Banco do Brasil", "senha do wifi", "KeePassXC"):
            self.assertTrue(P.titulo_sensivel(titulo), titulo)

    def test_janela_normal_nao_pausa(self):
        for titulo in ("", "Calculadora", "Visual Studio Code", "Simulador de física", "Explorer"):
            self.assertFalse(P.titulo_sensivel(titulo), titulo)

    def test_buffer_e_circular_e_limitado(self):
        b = P.BufferQuadros(maximo=3)
        for i in range(5):
            b.adicionar(_png((i * 20, 10, 10)), f"q{i}", marca="screen")
        self.assertEqual(len(b), 3)
        self.assertEqual(b.descartados, 2)
        self.assertEqual(b.ultimos(3), [_png((40, 10, 10)), _png((60, 10, 10)), _png((80, 10, 10))])

    def test_buffer_nunca_escreve_em_disco(self):
        pasta = self.d / "vazia"
        pasta.mkdir()
        b = P.BufferQuadros()
        b.adicionar(_png(), "tela")
        b.mini_video(3)
        self.assertEqual(list(pasta.iterdir()), [])

    def test_em_janela_sensivel_nao_captura_e_avisa_uma_vez(self):
        chamadas, avisos = [], []
        pres = P.Presenca(lambda tipo: chamadas.append(tipo) or (_png(), None),
                          titulo_atual=lambda: "1Password — Login", avisar=avisos.append)
        img, erro = pres.capturar("screen")
        self.assertIsNone(img)
        self.assertIn("sensível", erro)
        self.assertEqual(chamadas, [])
        self.assertTrue(pres.pausada)
        pres.capturar("screen")
        self.assertEqual(len(avisos), 1, "o aviso de pausa aparece uma vez, não a cada captura")

    def test_captura_normal_guarda_no_buffer(self):
        pres = P.Presenca(lambda tipo: (_png(), None), titulo_atual=lambda: "Calculadora")
        img, erro = pres.capturar("screen")
        self.assertTrue(img)
        self.assertIsNone(erro)
        self.assertEqual(len(pres.buffer), 1)
        self.assertEqual(len(pres.buffer.ultimos(3, "screen")), 1)

    def test_deteccao_de_mudanca_compara_com_o_ultimo_enviado(self):
        pres = P.Presenca(lambda tipo: (_png(), None))
        a, b = _png((255, 255, 255)), _png((0, 0, 0))
        self.assertTrue(pres.mudou(a))
        self.assertFalse(pres.mudou(a))
        self.assertTrue(pres.mudou(b))

    def test_olha_a_tela_usa_o_quadro_mais_novo_sem_nova_aprovacao(self):
        pres = P.Presenca(lambda tipo: (_png(), None))
        self.assertEqual(pres.quadros_para_pedido("screen"), [])
        pres.capturar("screen")
        pres.capturar("camera")
        quadros = pres.quadros_para_pedido("screen")
        self.assertEqual(len(quadros), 1)
        self.assertEqual(len(pres.buffer.ultimos(6, "camera")), 1)

    def test_mini_video_junta_os_quadros_numa_imagem_so(self):
        from PIL import Image
        pres = P.Presenca(lambda tipo: (_png(), None))
        for cor in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
            pres.buffer.adicionar(_png(cor, 16), "tela", marca="screen")
        quadros = pres.quadros_para_pedido("screen")
        self.assertEqual(len(quadros), 1, "a IA recebe UMA imagem (funciona em qualquer provedor)")
        im = Image.open(io.BytesIO(quadros[0]))
        self.assertGreater(im.width, 16, "a grade é maior que um quadro só")

    def test_resumo_nao_mente(self):
        pres = P.Presenca(lambda tipo: (_png(), None))
        self.assertIn("nenhum quadro", pres.resumo())
        pres.capturar("screen")
        self.assertIn("memória", pres.resumo())
        self.assertIn("disco", pres.resumo())


# ============================================================================================ T10
class _ConversaFalsa:
    def __init__(self):
        self.estado = "desligado"
        self.ligada = False
        self.blocos = []
        self.falando = []

    def ligar(self, aprovado=False, persistente=False):
        if not aprovado:
            self.estado = "desligado"
            return False, "precisa de aprovação"
        self.estado = self.ligada = True
        return True, "Modo conversa ligado."

    def desligar(self):
        self.estado = "desligado"
        self.ligada = False
        return True, "desligado"

    def ao_audio(self, pcm, taxa):
        self.blocos.append((len(pcm), taxa))
        return []

    def ela_falando(self, falando):
        self.falando.append(falando)

    def resumo(self):
        return "Modo conversa: ouvindo"


class _FluxoFalso:
    def __init__(self):
        self.fechado = False
        self.lidos = 0

    def ler(self):
        self.lidos += 1
        return b"\x01\x00" * 160

    def fechar(self):
        self.fechado = True


# ============================================================================================= T4
class ProgramasTestadosTests(_Tmp):
    def test_reconhece_erro_na_primeira_tela(self):
        self.assertTrue(PROG.parece_erro("ERRO! Ajuste o ângulo e a velocidade"))
        self.assertTrue(PROG.parece_erro("Traceback (most recent call last):"))
        self.assertTrue(PROG.parece_erro("ValueError: inválido"))
        self.assertTrue(PROG.parece_erro("Uncaught TypeError: x is not defined"))

    def test_saida_limpa_nao_e_erro(self):
        self.assertEqual(PROG.parece_erro("Jogo iniciado\nPontos: 10"), "")
        self.assertEqual(PROG.parece_erro(""), "")

    def _prog(self, nome="teste", texto="print(1)"):
        return PROG.ProgramaProposto(nome=nome, tipo="console", abrir="main.py", arquivos={"main.py": texto})

    def test_corrige_uma_vez_e_entrega(self):
        p = self._prog()
        saidas = ["❌ O programa abriu mostrando um erro: ERRO! Ajuste o ângulo",
                  "✅ O programa rodou e terminou sem erro. Sai\u0301da:\nok"]
        correcoes, avisos = [], []
        novo = self._prog("teste", "print(2)")
        r = PROG.executar_com_correcao(
            p, lambda prog, log, n: correcoes.append((n, log)) or novo,
            executar_fn=lambda prog: saidas.pop(0), avisar=avisos.append, tentativas=2)
        self.assertIn("Correção 1 funcionou", r)
        self.assertEqual(len(correcoes), 1)
        self.assertTrue(avisos and "Correção 1" in avisos[0])

    def test_falha_sempre_para_na_segunda_e_avisa(self):
        p = self._prog()
        n = {"i": 0}

        def executar(_prog):
            n["i"] += 1
            return "❌ O programa fechou com erro (código 1)"

        chamadas = []
        r = PROG.executar_com_correcao(p, lambda prog, log, k: chamadas.append(k) or self._prog("teste", f"print({k})"),
                                       executar_fn=executar, tentativas=2)
        self.assertEqual(chamadas, [1, 2])
        self.assertEqual(n["i"], 3)
        self.assertIn("Tentei corrigir 2 vez", r)

    def test_sem_correcao_diz_o_que_ficou_errado(self):
        r = PROG.executar_com_correcao(self._prog(), lambda *a: None,
                                       executar_fn=lambda prog: "❌ fechou com erro", tentativas=2)
        self.assertIn("Não consegui corrigir", r)
        self.assertIn("fechou com erro", r)


# ============================================================================================= T5
class LinguagensTests(unittest.TestCase):
    def test_plano_de_c_compila_e_roda(self):
        plano = LING.plano_para(".", "main.c", det={"c": {"falta": []}})
        self.assertTrue(plano["ok"])
        self.assertEqual(plano["comandos"][0][:2], ["gcc", "main.c"])
        self.assertEqual(len(plano["comandos"][1]), 1)
        self.assertIn("main", plano["comandos"][1][0])

    def test_falta_compilador_explica_como_instalar(self):
        plano = LING.plano_para(".", "Main.java", det={"java": {"falta": ["javac", "java"]}})
        self.assertFalse(plano["ok"])
        self.assertIn("JDK", plano["como_instalar"])
        self.assertIn("winget", LING.formatar_plano(plano))

    def test_javascript_e_python_rodam_direto(self):
        js = LING.plano_para(".", "app.js", det={"javascript": {"falta": []}})
        self.assertEqual(js["comandos"], [["node", "app.js"]])
        py = LING.plano_para(".", "main.py")
        self.assertEqual(py["comandos"][0][-1], "main.py")

    def test_linguagem_desconhecida_e_clara(self):
        with self.assertRaises(LING.ErroLinguagem):
            LING.plano_para(".", "arquivo.xyz")

    def test_pip_mostra_versao_e_licenca(self):
        def http(_url):
            return {"info": {"name": "requests", "version": "2.32.0", "license": "Apache-2.0",
                             "summary": "HTTP para humanos", "requires_python": ">=3.8"}}

        info = LING.info_pacote("requests", http=http)
        self.assertEqual(info["versao"], "2.32.0")
        self.assertEqual(info["licenca"], "Apache-2.0")
        self.assertIn("Apache-2.0", LING.formatar_pacote(info))

    def test_licenca_vazia_usa_classificador(self):
        def http(_url):
            return {"info": {"name": "x", "version": "1", "license": "",
                             "classifiers": ["License :: OSI Approved :: MIT License"]}}

        self.assertEqual(LING.info_pacote("x", http=http)["licenca"], "MIT License")

    def test_comando_pip_nao_aceita_nome_estranho(self):
        self.assertIn("requests", LING.comando_pip("requests")[-1])
        for ruim in ("", "; rm -rf", "a b"):
            with self.assertRaises(LING.ErroLinguagem):
                LING.comando_pip(ruim)


# ============================================================================================= T6
class _BibFalsa:
    def __init__(self):
        self.docs = {}
        self.trechos = []

    def adicionar(self, caminho, progresso=None):
        nome = Path(caminho).name
        self.docs[nome] = {"id": nome, "nome": nome, "paginas": 3}
        self.trechos.append({"arquivo": nome, "pagina": 1, "texto": "A força é massa vezes aceleração. "
                                                                  "Newton disse que a ação gera reação."})
        return {"adicionados": [self.docs[nome]], "repetidos": [], "erros": []}

    def documentos(self):
        return list(self.docs.values())

    def buscar(self, pergunta, k=5):
        return [{"arquivo": t["arquivo"], "pagina": t["pagina"], "texto": t["texto"], "pontos": 9.0,
                 "casados": 2, "cobertura": 1.0} for t in self.trechos][:k]


class CadernosTests(_Tmp):
    def _cad(self):
        return CAD.Cadernos(pasta=self.d, biblioteca=_BibFalsa())

    def test_cria_usa_e_apaga(self):
        cad = self._cad()
        c = cad.criar("Leis de Newton", "física")
        self.assertEqual(cad.ativo()["nome"], "Leis de Newton")
        cad.criar("Eletrônica")
        self.assertEqual(cad.usar("leis")["nome"], "Leis de Newton")
        self.assertTrue(cad.apagar("Eletrônica"))
        self.assertEqual(len(cad.listar()), 1)

    def test_fonte_entra_no_caderno(self):
        cad = self._cad()
        cad.criar("Física")
        arq = self.d / "apostila.pdf"
        arq.write_bytes(b"x")
        r = cad.adicionar("", str(arq))
        self.assertEqual(r["fontes"], ["apostila.pdf"])
        self.assertEqual(len(cad.ativo()["fontes"]), 1)

    def test_busca_so_traz_o_que_e_do_caderno(self):
        cad = self._cad()
        cad.criar("Física")
        (self.d / "a.pdf").write_bytes(b"x")
        cad.adicionar("", str(self.d / "a.pdf"))
        cad.bib.trechos.append({"arquivo": "outro.pdf", "pagina": 9, "texto": "nada a ver"})
        achados = cad.buscar("", "força", 5)
        self.assertTrue(achados)
        self.assertTrue(all(a["arquivo"] == "a.pdf" for a in achados))

    def test_resposta_cita_arquivo_e_pagina(self):
        cad = self._cad()
        cad.criar("Física")
        (self.d / "newton.pdf").write_bytes(b"x")
        cad.adicionar("", str(self.d / "newton.pdf"))
        r = cad.responder("", "força")
        self.assertIn("[newton.pdf, p. 1]", r["texto"])
        self.assertEqual(r["fontes"][0]["pagina"], 1)

    def test_sem_fonte_nao_inventa(self):
        cad = self._cad()
        cad.criar("Vazio")
        r = cad.responder("", "qualquer coisa")
        self.assertIn("Não achei", r["texto"])
        self.assertEqual(r["fontes"], [])

    def test_modo_professora_explica_e_pergunta(self):
        cad = self._cad()
        cad.criar("Física")
        (self.d / "newton.pdf").write_bytes(b"x")
        cad.adicionar("", str(self.d / "newton.pdf"))
        r = cad.professora("", "força")
        self.assertGreaterEqual(len(r["passos"]), 3)
        self.assertIn("?", r["pergunta"])
        self.assertTrue(r["fontes"])

    def test_tela_recebe_os_cadernos(self):
        cad = self._cad()
        cad.criar("Física")
        e = cad.estado_para_tela()
        self.assertEqual(e["action"], "cadernos_data")
        self.assertEqual(e["cadernos"][0]["nome"], "Física")


# ============================================================================================= T7
class DesempenhoTests(unittest.TestCase):
    def test_mede_com_psutil_falso(self):
        class VM:
            total, available = 16 * 1024 ** 3, 9 * 1024 ** 3

        class PS:
            @staticmethod
            def virtual_memory():
                return VM()

            @staticmethod
            def cpu_percent(interval=0.2):
                return 12.0

            @staticmethod
            def cpu_count():
                return 8

        m = DES.medir(psutil_mod=PS)
        self.assertEqual(m["ram_total_gb"], 16.0)
        self.assertEqual(m["ram_livre_gb"], 9.0)
        self.assertEqual(m["nucleos"], 8)

    def test_recomenda_o_modelo_que_cabe(self):
        rec = DES.recomendar({"ram_livre_gb": 4.5, "ram_total_gb": 16, "nucleos": 8, "disco_livre_gb": 50})
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["modelo"], "qwen2.5:1.5b")

    def test_mais_ram_recomenda_modelo_melhor(self):
        rec = DES.recomendar({"ram_livre_gb": 6.0, "ram_total_gb": 16, "nucleos": 16, "disco_livre_gb": 50})
        self.assertEqual(rec["modelo"], "llama3.2:3b")
        grande = DES.recomendar({"ram_livre_gb": 12.0, "ram_total_gb": 32, "nucleos": 16, "disco_livre_gb": 50})
        self.assertEqual(grande["modelo"], "qwen2.5:7b", "com folga, recomenda o melhor que cabe")

    def test_pc_pequeno_nao_recebe_modelo(self):
        rec = DES.recomendar({"ram_livre_gb": 1.0, "ram_total_gb": 4, "nucleos": 2, "disco_livre_gb": 50})
        self.assertFalse(rec["ok"])
        self.assertIn("travar", rec["motivo"])

    def test_sem_medida_nao_chuta(self):
        rec = DES.recomendar({"ram_livre_gb": None, "ram_total_gb": None})
        self.assertFalse(rec["ok"])
        self.assertIn("não consegui medir", rec["motivo"].lower())

    def test_modelos_recomendados_batem_com_a_ia_local(self):
        from brain import zenith_ia_local as IL
        nomes_local = {m["modelo"] for m in IL.RECOMENDADOS}
        self.assertTrue(nomes_local <= {m["modelo"] for m in DES.MODELOS}, "as duas listas não podem divergir")

    def test_texto_mostra_a_conta(self):
        m = {"ram_total_gb": 16.0, "ram_livre_gb": 9.0, "cpu_pct": 8.0, "nucleos": 8, "disco_livre_gb": 100}
        t = DES.formatar(m, DES.recomendar(m))
        self.assertIn("9.0 GB livres", t)
        self.assertIn("Recomendo", t)
        self.assertIn("/local baixar", t)


# ============================================================================================ T11
class MovimentosRicosTests(unittest.TestCase):
    def test_mais_movimentos_prontos_e_todos_validos(self):
        for nome in ("aceno_grande", "tchau", "pensando", "reverencia", "cansada", "animada"):
            self.assertIn(nome, MOV.PRONTOS)
        for nome, c in MOV.PRONTOS.items():
            _novo, avisos, erro = MOV.validar(c, nome)
            self.assertEqual(erro, "", nome)
            self.assertEqual(avisos, [], nome)

    def test_danca_no_ritmo_pedido(self):
        lenta, erro1 = MOV.gerar_danca(60, "suave")
        rapida, erro2 = MOV.gerar_danca(180, "animada")
        self.assertEqual((erro1, erro2), ("", ""))
        self.assertGreater(lenta["duracao"], rapida["duracao"], "60 BPM tem compasso mais longo que 180")

    def test_bpm_e_estilo_invalidos(self):
        self.assertIn("BPM", MOV.gerar_danca(10)[1])
        self.assertIn("BPM", MOV.gerar_danca("abc")[1])
        self.assertIn("estilo", MOV.gerar_danca(100, "funk")[1])

    def test_encadear_so_usa_o_que_existe_e_respeita_a_fila(self):
        fila = MOV.encadear(["careta", "pulo", "nao_existe"], 1.0)
        self.assertEqual([f["nome"] for f in fila], ["careta", "pulo"])
        grande = MOV.encadear([c for c in MOV.PRONTOS], 1.0)
        self.assertEqual(len(grande), MOV.FILA_MAX)

    def test_escala_do_pedido(self):
        self.assertEqual(MOV.escala_do_pedido("faz isso mais devagar"), 1.4)
        self.assertEqual(MOV.escala_do_pedido("bem mais devagar"), 1.8)
        self.assertEqual(MOV.escala_do_pedido("agora mais rápido"), 0.75)
        self.assertEqual(MOV.escala_do_pedido("faz de novo"), 1.0)

    def test_variante_estica_os_tempos(self):
        lento = MOV.variante(MOV.PRONTOS["pulo"], 1.5)
        self.assertAlmostEqual(lento["duracao"], MOV.PRONTOS["pulo"]["duracao"] * 1.5, places=2)
        self.assertGreater(lento["faixas"][0]["chaves"][-1][0], MOV.PRONTOS["pulo"]["faixas"][0]["chaves"][-1][0])

    def test_comando_dancar(self):
        r = CMD.tratar("/dancar 110 suave", {})
        self.assertEqual(r["acao"], "mov_danca")
        self.assertEqual(r["args"], {"bpm": 110, "estilo": "suave"})

    def test_comando_encadear(self):
        r = CMD.tratar("/movimentos encadear careta, pulo, dancar", {})
        self.assertEqual(r["acao"], "mov_fila")
        self.assertEqual([f["nome"] for f in r["args"]["fila"]], ["careta", "pulo", "dancar"])

    def test_comando_movimento_mais_devagar(self):
        r = CMD.tratar("/movimento pulo mais devagar", {})
        self.assertEqual(r["acao"], "mov_tocar")
        self.assertEqual(r["args"]["escala"], 1.4)


# ============================================================================================ comandos
class ComandosV17Tests(_Tmp):
    def test_conversa_precisa_do_ligar_explicito(self):
        r = CMD.tratar("/conversa", {})
        self.assertEqual(r["acao"], "conversa")
        self.assertEqual(r["args"], {"modo": "status"})     # sem argumento NÃO abre o microfone
        r = CMD.tratar("/conversa ligar", {})
        self.assertEqual(r["args"], {"modo": "ligar"})
        r = CMD.tratar("/conversa desligar", {})
        self.assertEqual(r["args"], {"modo": "desligar"})

    def test_cadernos_usa_o_caderno_padrao(self):
        cad = CAD.Cadernos(pasta=self.d, biblioteca=_BibFalsa())
        with mock.patch.object(CAD, "padrao", return_value=cad):
            r = CMD.tratar("/cadernos novo Leis de Newton", {})
            self.assertIn("criado", r["resposta"])
            self.assertIn("Leis de Newton", CMD.tratar("/cadernos", {})["resposta"])

    def test_instalar_mostra_antes_e_so_instala_com_confirmar(self):
        from brain import zenith_linguagens as L
        info = {"nome": "requests", "versao": "2.32.0", "licenca": "Apache-2.0", "resumo": "HTTP"}
        with mock.patch.object(L, "info_pacote", return_value=info):
            r = CMD.tratar("/instalar requests", {})
        self.assertIn("Apache-2.0", r["resposta"])
        self.assertIsNone(r["acao"])
        r = CMD.tratar("/instalar requests confirmar", {})
        self.assertEqual(r["acao"], "pip_instalar")
        self.assertEqual(r["args"], {"pacote": "requests"})

    def test_instalar_nome_ruim_nao_consulta_nada(self):
        r = CMD.tratar("/instalar ; rm -rf", {})
        self.assertIn("inválido", r["resposta"])

    def test_local_recomendar(self):
        class Cfg:
            def get(self, _k, padrao=None):
                return padrao

            def update(self, _d):
                pass

        r = CMD.tratar("/local recomendar", {"settings": Cfg()})
        self.assertIn("Este PC", r["resposta"])

    def test_linguagens_nao_instala_nada(self):
        r = CMD.tratar("/linguagens", {})
        self.assertIn("Python", r["resposta"])
        self.assertIn("Peça", r["resposta"])

    def test_ajuda_tem_os_comandos_novos(self):
        r = CMD.tratar("/ajuda", {})
        for cmd in ("/conversa", "/cadernos", "/linguagens", "/instalar", "/dancar", "/local"):
            self.assertIn(cmd, r["resposta"])


if __name__ == "__main__":
    unittest.main()
