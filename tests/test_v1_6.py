"""v1.6 — movimentos do avatar (pulo de verdade, dança, câmera, janela, caretas) e movimentos criados pela IA."""
import json
import math
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                      # noqa: E402
_stubs.instalar()                             # falsifica google.genai etc. — nenhum teste usa rede
from brain import zenith_movimentos as M      # noqa: E402
from brain import zenith_gestos as G          # noqa: E402
from brain import zenith_commands as CMD      # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="zenith_v16_"))
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)


class ProntosTests(unittest.TestCase):
    def test_todos_os_prontos_sao_validos_e_estao_nos_limites(self):
        self.assertGreaterEqual(len(M.PRONTOS), 14)
        for nome, c in M.PRONTOS.items():
            novo, avisos, erro = M.validar(c, nome)
            self.assertEqual(erro, "", f"{nome}: {erro}")
            self.assertEqual(avisos, [], f"{nome} precisou de ajuste: {avisos}")
            self.assertLessEqual(c["duracao"] * c["repetir"], M.TEMPO_TOTAL_MAX, nome)

    def test_o_pulo_sobe_de_verdade(self):
        """O 'pulinho' antigo era uma vibração de 1,2 cm que nem era aplicada. O pulo novo sobe dezenas de centímetros."""
        alturas = [M.avaliar(M.PRONTOS["pulo"], i * 0.01)["corpo_y"] for i in range(0, 116)]
        self.assertGreater(max(alturas), 0.20)
        self.assertLess(max(alturas), 0.40)
        self.assertAlmostEqual(alturas[-1], 0.0, places=3)           # termina no chão
        self.assertAlmostEqual(alturas[0], 0.0, places=3)
        self.assertLess(min(alturas), 0.0)                           # agacha antes de pular

    def test_a_janela_pula_junto_e_volta(self):
        c = M.PRONTOS["pulo"]
        dy = [M.avaliar(c, i * 0.01)["janela_dy"] for i in range(0, 116)]
        self.assertLess(min(dy), -40)
        self.assertAlmostEqual(dy[-1], 0.0, places=3)

    def test_dancar_repete_e_volta_ao_ponto_de_partida(self):
        c = M.PRONTOS["dancar"]
        self.assertEqual(c["repetir"], 2)
        a, b = M.avaliar(c, 0.0), M.avaliar(c, c["duracao"])         # início do 1º e do 2º ciclo são iguais
        for alvo in ("corpo_x", "corpo_giro", "cabeca_roll", "janela_dx"):
            self.assertAlmostEqual(a[alvo], b[alvo], places=2, msg=alvo)
        self.assertTrue(M.avaliar(c, 8.0)["fim"])
        self.assertFalse(M.avaliar(c, 7.9)["fim"])

    def test_girar_completa_uma_volta(self):
        self.assertAlmostEqual(M.avaliar(M.PRONTOS["girar"], 1.3)["corpo_giro"], 360.0, places=2)

    def test_camera_aproxima_afasta_e_volta_ao_normal(self):
        self.assertAlmostEqual(M.avaliar(M.PRONTOS["aproximar"], 1.0)["camera_zoom"], 1.6, places=3)
        self.assertAlmostEqual(M.avaliar(M.PRONTOS["afastar"], 1.0)["camera_zoom"], 0.7, places=3)
        self.assertAlmostEqual(M.avaliar(M.PRONTOS["camera_normal"], 0.8)["camera_zoom"], 1.0, places=3)

    def test_null_na_primeira_chave_parte_de_onde_estiver(self):
        c = M.PRONTOS["aproximar"]
        self.assertAlmostEqual(M.avaliar(c, 0.0, {"camera_zoom": 0.7})["camera_zoom"], 0.7, places=3)    # já estava afastada
        self.assertAlmostEqual(M.avaliar(c, 0.0)["camera_zoom"], 1.0, places=3)                          # padrão do zoom
        p = M.PRONTOS["passear"]
        self.assertAlmostEqual(M.avaliar(p, 0.0, {"janela_x": -100})["janela_x"], -100, places=3)
        self.assertAlmostEqual(M.avaliar(p, 3.4, {"janela_x": -100})["janela_x"], -520, places=3)

    def test_voltar_ao_canto_zera_a_janela(self):
        v = M.avaliar(M.PRONTOS["voltar_ao_canto"], 3.0, {"janela_x": -520, "janela_y": 0})
        self.assertAlmostEqual(v["janela_x"], 0.0, places=3)

    def test_envelope_suaviza_comeco_e_fim(self):
        self.assertEqual(M.envelope(0.0, 2.0), 0.0)
        self.assertEqual(M.envelope(2.0, 2.0), 0.0)
        self.assertEqual(M.envelope(1.0, 2.0), 1.0)
        self.assertTrue(0.0 < M.envelope(0.09, 2.0) < 1.0)

    def test_rostos_usam_so_expressoes_que_o_avatar_conhece(self):
        for nome, c in M.PRONTOS.items():
            for f in c["faixas"]:
                if f["alvo"].startswith("rosto:"):
                    self.assertIn(f["alvo"][6:], M.ROSTOS, nome)


class ValidacaoTests(unittest.TestCase):
    def base(self, **kw):
        d = {"nome": "teste_um", "duracao": 1.0, "faixas": [{"alvo": "corpo_y", "chaves": [[0, 0], [0.5, 0.2], [1.0, 0]]}]}
        d.update(kw)
        return d

    def test_aceita_movimento_simples(self):
        c, av, erro = M.validar(self.base())
        self.assertEqual(erro, "")
        self.assertEqual(c["repetir"], 1)

    def test_nome_ruim_ou_proibido(self):
        for nome in ("A", "1abc", "com espaco", "x" * 40, "../etc", ""):
            self.assertNotEqual(M.validar(self.base(nome=nome))[2], "", nome)
        for nome in ("beijo_no_ar", "coracao_com_a_mao", "abraco_forte", "piscadinha", "joinha_ok", "danca_sensual", "twerk", "rebolar"):
            self.assertIn("não é permitido", M.validar(self.base(nome=nome))[2], nome)
        self.assertIn("não é permitido", M.validar(self.base(descricao="faz um beijo"))[2])
        self.assertEqual(M.validar(self.base(nome="dancinha_alegre"))[2], "")        # dança comum pode

    def test_valores_fora_do_limite_sao_ajustados_e_avisados(self):
        c, av, erro = M.validar(self.base(faixas=[{"alvo": "corpo_y", "chaves": [[0, 0], [1.0, 9]]}]))
        self.assertEqual(erro, "")
        self.assertEqual(c["faixas"][0]["chaves"][1][1], 0.6)
        self.assertTrue(av)

    def test_limites_de_duracao_repeticao_e_tamanho(self):
        c, av, e = M.validar(self.base(duracao=99, repetir=99))
        self.assertLessEqual(c["duracao"], M.DURACAO_MAX)
        self.assertLessEqual(c["duracao"] * c["repetir"], M.TEMPO_TOTAL_MAX)
        self.assertNotEqual(M.validar(self.base(faixas=[{"alvo": "corpo_y", "chaves": [[i * 0.01, 0] for i in range(60)]}]))[2], "")
        muitas = [{"alvo": a, "chaves": [[0, 0], [1, 0]]} for a in list(M.LIMITES)[:14]] + [{"alvo": "rosto:happy", "chaves": [[0, 0], [1, 0]]}]
        self.assertNotEqual(M.validar(self.base(faixas=muitas))[2], "")

    def test_alvo_ou_rosto_desconhecido(self):
        self.assertIn("alvo desconhecido", M.validar(self.base(faixas=[{"alvo": "hackear", "chaves": [[0, 0], [1, 1]]}]))[2])
        self.assertIn("rosto desconhecido", M.validar(self.base(faixas=[{"alvo": "rosto:beijo", "chaves": [[0, 0], [1, 1]]}]))[2])

    def test_tempos_precisam_crescer_e_lixo_nao_passa(self):
        self.assertNotEqual(M.validar(self.base(faixas=[{"alvo": "corpo_y", "chaves": [[0.5, 0], [0.1, 0]]}]))[2], "")
        for lixo in (None, [], "texto", 5, {"nome": "ok"}, self.base(faixas="x"), self.base(duracao="a")):
            self.assertNotEqual(M.validar(lixo)[2], "", str(lixo))
        self.assertNotEqual(M.validar(self.base(faixas=[{"alvo": "corpo_y", "chaves": [[0, float("nan")], [1, 0]]}]))[2], "")

    def test_null_so_na_primeira_chave_de_alvo_persistente(self):
        ok = self.base(faixas=[{"alvo": "camera_zoom", "chaves": [[0, None], [1, 1.5]]}])
        self.assertEqual(M.validar(ok)[2], "")
        for ruim in ({"alvo": "corpo_y", "chaves": [[0, None], [1, 0]]}, {"alvo": "camera_zoom", "chaves": [[0, 1], [1, None]]}):
            self.assertIn("null", M.validar(self.base(faixas=[ruim]))[2])

    def test_bracos_exigem_vetor_valido(self):
        bom = [0, 0.1, -0.95, 0.05, 0.05, -0.95, 0.1, 1]
        self.assertEqual(M.validar(self.base(faixas=[{"alvo": "braco_dir", "chaves": [bom, [1] + bom[1:]]}]))[2], "")
        self.assertNotEqual(M.validar(self.base(faixas=[{"alvo": "braco_dir", "chaves": [[0, 0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 0, 1]]}]))[2], "")
        self.assertNotEqual(M.validar(self.base(faixas=[{"alvo": "braco_dir", "chaves": [[0, 1], [1, 1]]}]))[2], "")

    def test_mao_desconhecida_e_ignorada_com_aviso(self):
        c, av, e = M.validar(self.base(mao="garra"))
        self.assertIsNone(c["mao"])
        self.assertTrue(any("mao" in a for a in av))


class BibliotecaTests(_Tmp):
    def test_ia_cria_salva_e_recarrega(self):
        bruto = json.dumps(self_base := {"nome": "aceno_duplo", "duracao": 1.5, "mao": "aberta", "faixas": [
            {"alvo": "corpo_y", "chaves": [[0, 0], [0.4, 0.1], [1.5, 0]]}, {"alvo": "rosto:happy", "chaves": [[0, 0], [0.3, 0.8], [1.5, 0]]}]})
        c, av, erro = M.criar_de_texto("```json\n" + bruto + "\n```", self.d)
        self.assertEqual(erro, "")
        self.assertTrue((self.d / "aceno_duplo.json").is_file())
        lib = M.biblioteca(self.d)
        self.assertIn("aceno_duplo", lib)
        self.assertEqual(lib["aceno_duplo"]["autor"], "ia")
        self.assertIn("pulo", lib)

    def test_nao_deixa_substituir_um_pronto_nem_gravar_proibido(self):
        base = {"duracao": 1, "faixas": [{"alvo": "corpo_y", "chaves": [[0, 0], [1, 0.1]]}]}
        self.assertIn("pronto", M.salvar(dict(base, nome="pulo"), self.d)[2])
        self.assertIn("não é permitido", M.salvar(dict(base, nome="beijo_no_ar"), self.d)[2])
        self.assertFalse(list(self.d.glob("*.json")))

    def test_json_quebrado_vira_erro_claro(self):
        self.assertIn("não abriu", M.criar_de_texto("{isso nao e json", self.d)[2])

    def test_arquivo_adulterado_na_pasta_e_ignorado(self):
        (self.d / "perigo.json").write_text(json.dumps({"nome": "perigo", "duracao": 1, "faixas": [{"alvo": "apagar_disco", "chaves": [[0, 0], [1, 1]]}]}))
        (self.d / "lixo.json").write_text("{{{")
        self.assertNotIn("perigo", M.carregar_criados(self.d))

    def test_apagar_so_apaga_criado(self):
        M.salvar({"nome": "meu_mov", "duracao": 1, "faixas": [{"alvo": "corpo_y", "chaves": [[0, 0], [1, 0.1]]}]}, self.d)
        self.assertTrue(M.apagar("meu_mov", self.d))
        self.assertFalse(M.apagar("meu_mov", self.d))
        self.assertFalse(M.apagar("pulo", self.d))
        self.assertFalse(M.apagar("../../etc/passwd", self.d))

    def test_limite_da_biblioteca(self):
        with mock.patch.object(M, "BIBLIOTECA_MAX", 2):
            for i in range(2):
                self.assertEqual(M.salvar({"nome": f"mov_{i}", "duracao": 1, "faixas": [{"alvo": "corpo_y", "chaves": [[0, 0], [1, 0.1]]}]}, self.d)[2], "")
            self.assertIn("já tem", M.salvar({"nome": "mov_9", "duracao": 1, "faixas": [{"alvo": "corpo_y", "chaves": [[0, 0], [1, 0.1]]}]}, self.d)[2])

    def test_etiqueta_criar_movimento_sai_do_texto(self):
        txt, brutos = M.extrair_criacoes('Claro! <criar_movimento>{"nome":"x1"}</criar_movimento> Pronto.')
        self.assertEqual(brutos, ['{"nome":"x1"}'])
        self.assertNotIn("criar_movimento", txt)
        from brain import zenith_tags
        self.assertIn("criar_movimento", zenith_tags.TAGS_INTERNAS)

    def test_formato_de_exemplo_do_prompt_e_valido(self):
        bruto = re.search(r"<criar_movimento>(.*)</criar_movimento>", M.FORMATO_CRIAR, re.S).group(1)
        c, av, erro = M.criar_de_texto(bruto, self.d)
        self.assertEqual(erro, "", erro)


class FazerOQueDizTests(unittest.TestCase):
    NOMES = set(M.PRONTOS)

    def test_pedidos_do_usuario(self):
        casos = {"faz uma careta e dá um pulo": ["careta", "pulo"], "dá um pulo": ["pulo"], "dança!": ["dancar"], "dança pra mim": ["dancar"],
                 "chega mais perto da câmera": ["aproximar"], "afasta a câmera": ["afastar"], "volta a câmera ao normal": ["camera_normal"],
                 "pula pra lá": ["pulo_longe"], "dá um pulo duplo": ["pulo_duplo"], "gira": ["girar"], "passeia pela tela": ["passear"],
                 "volta pro canto": ["voltar_ao_canto"], "faz cara de sono": ["cara_de_sono"]}
        for texto, esperado in casos.items():
            self.assertEqual(M.inferir_do_pedido(texto, self.NOMES), esperado, texto)

    def test_conversa_normal_nao_dispara(self):
        for texto in ("quanto é 2+2", "explica o pulo do gato no código", "preciso que você salte uma linha", "me ajuda com cálculo",
                      "o servidor Zoom caiu", "x" * 300 + " dança"):
            self.assertEqual(M.inferir_do_pedido(texto, self.NOMES), [], texto[:30])

    def test_so_toca_o_que_existe(self):
        self.assertEqual(M.inferir_do_pedido("dá um pulo", {"careta"}), [])

    def test_o_que_ela_diz_que_fez_acontece(self):
        self.assertEqual(M.inferir_do_que_ela_disse("Feito! Fiz a careta mais invocada que consegui e dei o pulo.", self.NOMES), ["pulo", "careta"])
        self.assertEqual(M.inferir_do_que_ela_disse("Dancei um pouquinho pra você", self.NOMES), ["dancar"])
        self.assertEqual(M.inferir_do_que_ela_disse("Posso dar um pulo se você quiser.", self.NOMES), [])      # oferecer não é fazer
        self.assertEqual(M.inferir_do_que_ela_disse("```python\nprint('pulei')\n```", self.NOMES), [])           # código não conta

    def test_corpo_movimento_e_gesto_pulinho_viram_movimento(self):
        G.MOVIMENTOS_CONHECIDOS.clear()
        G.MOVIMENTOS_CONHECIDOS.update(M.PRONTOS)
        try:
            limpo, cmds = G.extrair_comandos_corpo("Oi <corpo>movimento:pulo</corpo> tudo bem <corpo>gesto:careta</corpo>")
            self.assertEqual(cmds, [("movimento", "pulo"), ("movimento", "careta")])
            self.assertNotIn("corpo", limpo)
            _, cmds = G.extrair_comandos_corpo("<corpo>movimento:inventado</corpo>")
            self.assertEqual(cmds, [])
        finally:
            G.MOVIMENTOS_CONHECIDOS.clear()


class ComandosTests(_Tmp):
    def test_lista_toca_e_apaga(self):
        r = CMD.tratar("/movimentos", {})
        self.assertIn("pulo", r["resposta"])
        r = CMD.tratar("/movimento pulo", {})
        self.assertEqual((r["acao"], r["args"]["nome"]), ("mov_tocar", "pulo"))
        self.assertIn("Não conheço", CMD.tratar("/movimento nao_existe_mesmo", {})["resposta"])
        self.assertIn("não podem", CMD.tratar("/movimentos apagar pulo", {})["resposta"])


class HeadlessTests(unittest.TestCase):
    def _headless(self, settings=None):
        from brain import zenith_headless as H
        h = object.__new__(H.ZenithHeadlessBrain)
        h.settings = mock.MagicMock()
        cfg = {"movimentos_ativos": True, "movimentos_janela": True, "movimentos_camera": True}
        cfg.update(settings or {})
        h.settings.get = lambda k, d=None: cfg.get(k, d)
        h.bridge = mock.MagicMock()
        return h

    def test_pedido_do_usuario_e_fala_dela_viram_movimentos(self):
        h = self._headless()
        with mock.patch.object(M, "biblioteca", return_value=dict(M.PRONTOS)):
            movs = h._movimentos_da_resposta("faz uma careta e dá um pulo", "Feito! Fiz a careta e dei o pulo.", [], [])
        self.assertEqual(movs, ["careta", "pulo"])

    def test_o_que_a_ia_pediu_na_etiqueta_vem_primeiro_e_nao_repete(self):
        h = self._headless()
        with mock.patch.object(M, "biblioteca", return_value=dict(M.PRONTOS)):
            movs = h._movimentos_da_resposta("oi", "Dancei!", [("movimento", "girar")], [])
        self.assertEqual(movs, ["girar", "dancar"])

    def test_desligado_nas_configuracoes_nao_toca_nada(self):
        h = self._headless({"movimentos_ativos": False})
        self.assertEqual(h._movimentos_da_resposta("dá um pulo", "dei o pulo", [], []), [])
        h._tocar_movimentos(["pulo"])
        h.bridge.send.assert_not_called()

    def test_tocar_manda_a_mensagem_certa(self):
        h = self._headless()
        h._tocar_movimentos(["pulo", "careta"])
        enviados = [c.args[0] for c in h.bridge.send.call_args_list]
        self.assertEqual(enviados, [{"action": "movement_play", "nome": "pulo", "escala": 1.0}, {"action": "movement_play", "nome": "careta", "escala": 1.0}])

    def test_criacao_da_ia_e_confirmada_ao_usuario_so_se_deu_certo(self):
        h = self._headless()
        pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, pasta, True)
        with mock.patch.object(M, "pasta_padrao", return_value=pasta):
            h._criar_movimentos_da_ia(['{"nome":"beijo_no_ar","duracao":1,"faixas":[{"alvo":"corpo_y","chaves":[[0,0],[1,0.1]]}]}'])
            textos = [c.args[0].get("text", "") for c in h.bridge.send.call_args_list]
            self.assertTrue(any("Não consegui criar" in t for t in textos), textos)
            self.assertFalse(any(t.startswith("Criei o movimento") for t in textos))
            h.bridge.send.reset_mock()
            h._criar_movimentos_da_ia(['{"nome":"giro_feliz","duracao":1,"faixas":[{"alvo":"corpo_giro","chaves":[[0,0],[1,360]]}]}'])
            textos = [c.args[0].get("text", "") for c in h.bridge.send.call_args_list]
            self.assertTrue(any(t.startswith('Criei o movimento "giro_feliz"') for t in textos), textos)
            acoes = [c.args[0].get("action") for c in h.bridge.send.call_args_list]
            self.assertIn("movement_library", acoes)

    def test_parar_manda_movement_stop(self):
        src = (RAIZ / "brain/zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn('"action": "movement_stop"', src)


class GodotEstruturaTests(unittest.TestCase):
    def _gd(self, nome):
        return (RAIZ / "body/zenith" / nome).read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_interpretador_tem_a_interface_que_o_corpo_chama(self):
        m = self._gd("zenith_movimentos.gd")
        self.assertTrue(m.startswith("extends RefCounted"))
        for f in ("func definir_todos(", "func tocar(", "func parar(", "func ativo(", "func atualizar(delta: float) -> Dictionary:",
                  "func definir_persistente(", "func persistente(", "func existe("):
            self.assertIn(f, m)

    def test_limites_do_corpo_batem_com_os_do_cerebro(self):
        m = self._gd("zenith_movimentos.gd")
        for alvo, (lo, hi) in M.LIMITES.items():
            achado = re.search(rf'"{alvo}": \[(-?[\d.]+), (-?[\d.]+)\]', m)
            self.assertIsNotNone(achado, alvo)
            self.assertAlmostEqual(float(achado.group(1)), lo, places=3, msg=alvo)
            self.assertAlmostEqual(float(achado.group(2)), hi, places=3, msg=alvo)

    def test_corpo_carrega_com_load_e_protege(self):
        b = self._gd("akira_body.gd")
        self.assertIn('const MOV_PATH := "res://zenith_movimentos.gd"', b)
        self.assertNotIn('preload("res://zenith_movimentos.gd")', b)
        self.assertIn("script.can_instantiate()", b)
        self.assertIn("_mov_tick(delta)", b)
        self.assertIn("connector.movimento.connect(_on_movimento)", b)
        self.assertIn("window_set_position", b[b.index("func _mov_aplicar_janela"):])
        self.assertIn("clampf(alvo.x", b)                       # a janela nunca sai da tela
        self.assertIn("_force_redraw()", b[b.index("func _mov_aplicar_janela"):])

    def test_conector_tem_o_sinal_e_as_quatro_acoes(self):
        c = self._gd("brain_connector.gd")
        self.assertIn("signal movimento(dados)", c)
        self.assertIn('"movement_library", "movement_play", "movement_stop", "movement_config":', c)

    def test_vida_aplica_bracos_cabeca_e_rosto_do_movimento(self):
        v = self._gd("akira_vida.gd")
        for trecho in ("func mov_set(d: Dictionary):", '_mov.has("braco_dir")', 'float(_mov.get("cabeca_pitch", 0.0))', '_mov["rosto"]'):
            self.assertIn(trecho, v)

    def test_maos_aceitam_a_pose_pedida_pelo_movimento(self):
        m = self._gd("zenith_maos.gd")
        for pose in M.MAOS:
            self.assertIn(f'"{pose}": {{', m, pose)

    def test_nomes_de_alvo_do_gd_existem_no_python(self):
        m = self._gd("zenith_movimentos.gd")
        for alvo in re.findall(r'^\t"(\w+)": \[-?[\d.]+, -?[\d.]+\]', m, flags=re.M):
            self.assertIn(alvo, M.LIMITES)


# ----------------------------------------------------------------------------------------------------------------------
# Biblioteca / Projetos, nome salvo, cartão de falha, painel x avatar, emoji no Corpo
# ----------------------------------------------------------------------------------------------------------------------
from brain import zenith_projetos as PJ        # noqa: E402
from brain import zenith_atividade as AT       # noqa: E402


class ProjetosTests(_Tmp):
    def _criacoes(self):
        r = self.d / "creations"
        def f(rel, txt="x"):
            p = r / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(txt.encode() if isinstance(txt, str) else txt)
        f("programas/jogo_da_velha/main.py", "print(1)")
        f("programas/jogo_da_velha/util.py")
        f("programas/jogo_da_velha/_zenith_log.txt", "log")
        f("programas/jogo_da_velha/_backup/2026/main.py", "velho")
        f("programas/simulador/index.html", "<html>")
        f("programas/simulador/app.js")
        f("programas/simulador/estilo.css")
        f("programas/blink/blink.ino")
        f("web/pagina.html", "<html>")
        f("imagens/gato.png", b"\x89PNG")
        f("imagens/cachorro.jpg", b"\xff\xd8")
        f("videos/aula.mp4", b"\x00")
        f("documentos/relatorio.docx", b"PK")
        f("quarentena/coisa.png", b"\x89PNG")
        f("programas/_backup/x.py")
        return r

    def test_indexa_por_categoria_e_linguagem(self):
        r = self._criacoes()
        ind = PJ.indexar(r)
        cats = {c["id"]: c for c in ind["categorias"]}
        self.assertEqual(cats["programas"]["total"], 3)
        grupos = {g["titulo"].split(" (")[0]: g for g in cats["programas"]["grupos"]}
        self.assertEqual(set(grupos), {"Python", "Web", "Arduino"})
        velha = grupos["Python"]["itens"][0]
        self.assertEqual((velha["nome"], velha["arquivos"]), ("jogo_da_velha", 2))      # sem log nem backup
        self.assertEqual(grupos["Web"]["itens"][0]["linguagens"], ["Web"])               # html + css + js = um projeto Web
        self.assertEqual(cats["sites"]["total"], 1)
        self.assertEqual(cats["imagens"]["total"], 2)                                   # a de quarentena não entra
        self.assertEqual(cats["videos"]["total"], 1)
        self.assertEqual(cats["documentos"]["total"], 1)
        self.assertEqual(ind["total"], 3 + 1 + 2 + 1 + 1)

    def test_pasta_vazia_ou_inexistente_nao_quebra(self):
        ind = PJ.indexar(self.d / "nao_existe")
        self.assertEqual(ind["total"], 0)
        self.assertIn("Ainda não há nada", PJ.formatar_texto(ind))

    def test_texto_do_chat_lista_o_que_tem(self):
        txt = PJ.formatar_texto(PJ.indexar(self._criacoes()))
        for esperado in ("Programas (3)", "Python", "jogo_da_velha", "Imagens (2)", "Vídeos (1)", "Documentos (1)"):
            self.assertIn(esperado, txt)

    def test_painel_so_abre_coisas_dentro_das_criacoes(self):
        r = self._criacoes()
        self.assertTrue(PJ.dentro_das_criacoes(r / "imagens/gato.png", r))
        self.assertFalse(PJ.dentro_das_criacoes(r / ".." / "config" / "settings.json", r))
        self.assertFalse(PJ.dentro_das_criacoes("C:\\Windows\\System32\\cmd.exe", r))
        self.assertFalse(PJ.dentro_das_criacoes("../../etc/passwd", r))
        chamado = []
        ok, msg = PJ.abrir_no_explorador(r / "imagens/gato.png", r, abridor=chamado.append)
        self.assertTrue(ok)
        self.assertEqual(len(chamado), 1)
        ok, msg = PJ.abrir_no_explorador(self.d / "fora.txt", r, abridor=chamado.append)
        self.assertFalse(ok)
        self.assertEqual(len(chamado), 1)                                # nada foi aberto

    def test_link_simbolico_para_fora_e_recusado(self):
        r = self._criacoes()
        fora = self.d / "segredo.txt"
        fora.write_text("x")
        try:
            (r / "imagens" / "atalho.png").symlink_to(fora)
        except (OSError, NotImplementedError):
            self.skipTest("sem suporte a symlink aqui")
        self.assertFalse(PJ.dentro_das_criacoes(r / "imagens" / "atalho.png", r))

    def test_ver_no_chat_so_imagem(self):
        r = self._criacoes()
        self.assertIsNotNone(PJ.caminho_de_imagem(r / "imagens/gato.png", r))
        self.assertIsNone(PJ.caminho_de_imagem(r / "programas/jogo_da_velha/main.py", r))
        self.assertIsNone(PJ.caminho_de_imagem(r / "imagens/nao_existe.png", r))

    def test_comando_projetos_e_o_painel(self):
        r = CMD.tratar("/projetos", {})
        self.assertEqual(r["acao"], "projetos_enviar")
        self.assertNotEqual(CMD.tratar("/programas", {}).get("acao"), "projetos_enviar")     # /programas continua sendo os que estão rodando

    def test_handlers_do_headless_e_o_painel_do_godot(self):
        h = (RAIZ / "brain/zenith_headless.py").read_text(encoding="utf-8")
        for chave in ('"list_projetos": self._handle_list_projetos', '"open_projeto"', '"view_projeto"'):
            self.assertIn(chave, h)
        c = (RAIZ / "body/zenith/brain_connector.gd").read_text(encoding="utf-8")
        self.assertIn("signal projetos_dados(dados)", c)
        self.assertIn("func request_projetos()", c)
        u = (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8")
        for trecho in ("func _build_projetos_overlay", "func _on_projetos_dados", "brain.projetos_dados.connect(_on_projetos_dados)",
                       "_show_overlay(projetos_overlay, projetos_card)", "brain.request_abrir_projeto(caminho)"):
            self.assertIn(trecho, u)


class NomeSalvoTests(_Tmp):
    def _carregar(self, conteudo):
        from brain import zenith_settings as S
        arq = self.d / "settings.json"
        if conteudo is not None:
            arq.write_text(json.dumps(conteudo), encoding="utf-8")
        with mock.patch.object(S, "SETTINGS_FILE", arq), mock.patch.object(S, "_LEGACY_FILES", []):
            return S.ZenithSettings().settings

    def test_nome_antigo_vira_zenith_uma_vez(self):
        s = self._carregar({"persona_name": "Akira", "onboarding_done": True})   # legado-ok
        self.assertEqual(s["persona_name"], "Zenith")
        self.assertTrue(s["persona_migrada_v16"])

    def test_se_a_pessoa_escolher_o_nome_antigo_depois_ele_fica(self):
        s = self._carregar({"persona_name": "Akira", "persona_migrada_v16": True, "onboarding_done": True})   # legado-ok
        self.assertEqual(s["persona_name"], "Akira")   # legado-ok

    def test_outro_nome_nao_e_mexido(self):
        self.assertEqual(self._carregar({"persona_name": "Luna", "onboarding_done": True})["persona_name"], "Luna")

    def test_instalacao_nova_comeca_com_zenith(self):
        self.assertEqual(self._carregar(None)["persona_name"], "Zenith")


class CartaoDeFalhaTests(unittest.TestCase):
    def test_nao_achei_nao_e_sucesso(self):
        for txt in ("Não achei o vídeo neste caminho:\nC:\\x.mp4", "Não consegui abrir o arquivo", "Erro: arquivo inexistente",
                    "Deu erro no vídeo: OSError", "Falhou ao cortar", "nao encontrei a pasta"):
            self.assertTrue(AT.parece_falha(txt), txt)

    def test_sucesso_continua_sucesso(self):
        for txt in ("Pronto, gerei a imagem", "Vídeo cortado e salvo em creations/videos/a.mp4", "42", "Resultado: 5", ""):
            self.assertFalse(AT.parece_falha(txt), txt)
        self.assertTrue(AT.parece_falha("❌ não deu"))


class PainelEEmojiNoCorpoTests(unittest.TestCase):
    def _u(self):
        return (RAIZ / "body/zenith/ui_manager.gd").read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_configuracoes_nao_passam_por_baixo_do_avatar(self):
        u = self._u()
        self.assertIn("func _afastar_do_avatar(card: Control):", u)
        self.assertIn("DisplayServer.window_get_position(0)", u)
        self.assertIn("r_chat.intersects(r_avatar)", u)
        corpo = u[u.index("func _show_overlay"):]
        self.assertTrue(corpo.split("\n", 2)[1].strip() == "_afastar_do_avatar(card)", "tem que ser a 1ª linha de _show_overlay")

    def test_bolhas_da_ia_e_o_aviso_de_espera_sem_emoji(self):
        u = self._u()
        self.assertIn("func _sem_emoji(s: String) -> String:", u)
        self.assertIn("\t\ttext = _sem_emoji(text)", u)
        self.assertNotIn('aviso.text = "\u23f3', u)                  # rótulos diretos (não passam por _add_bubble) já sem a ampulheta
        self.assertNotIn('w["titulo"].text = "\u23f3', u)

    def test_regex_de_emoji_do_corpo_cobre_as_mesmas_faixas_do_cerebro(self):
        from brain import zenith_emoji as E
        u = self._u()
        linha = [l for l in u.split("\n") if "_rx_emoji.compile(" in l][0]
        for faixa in ("1F000", "1FAFF", "2600", "26FF", "FE0F", "200D", "20E3", "2B50", "23F3"):
            self.assertIn(f"x{{{faixa}}}", linha)
        for c in ("\U0001F680", "\u26a0", "\u23f3", "\u2705", "\u2b50"):
            self.assertNotEqual(E.remover("a " + c + " b"), "a " + c + " b")

    def test_icones_para_a_biblioteca(self):
        i = (RAIZ / "body/zenith/zenith_icones.gd").read_text(encoding="utf-8")
        self.assertIn('"📚": "biblioteca"', i)
        for nome in ("biblioteca", "pasta", "video", "imagem", "codigo"):
            self.assertTrue((RAIZ / "body/zenith/assets/icones" / f"{nome}.svg").is_file(), nome)


if __name__ == "__main__":
    unittest.main()
