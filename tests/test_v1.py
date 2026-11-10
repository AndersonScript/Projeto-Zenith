"""
Testes da v1.0 — a versão oficial. Cada classe aqui é uma promessa que o Anderson vai conferir
no .exe, então cada teste diz no nome o que ele garante:

  * VERSÃO: é a v1.0, e o /versao mostra a data do build.
  * CRÉDITOS: o menu de Configurações diz quem criou, e a apresentação é um arquivo que ele
    edita sem recompilar — SEM escola/faculdade no texto padrão (ele pediu isso explicitamente).
  * A2: chave de API digitada no chat NÃO fica no histórico, na memória nem no balão da tela.
  * A5: comando desconhecido NUNCA vai para a IA (antes ela inventava um "visualizador 3D").
  * A6: o "digitar ao vivo" não come mais as quebras de linha do markdown.
  * A7: o caminho que o Windows copia (com aspas duplas) funciona no /video.
  * A8: o contrato da página de Chaves devolve tudo mascarado.
  * A18: o build NUNCA apaga o resgate dos dados do usuário quando a devolução falha.
  * A19: legenda com apóstrofo/acento/colchete no nome não quebra o ffmpeg.

Rodar: python -m unittest tests.test_v1 -v
NÃO provam: a interface do Godot (a aba "Sobre" só aparece depois de reexportar o projeto),
nem um build de verdade (o teste do A18 simula a falha de cópia).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_commands as CMD
from brain import zenith_creditos as CRED
from brain import zenith_segredos as SEG
from brain import zenith_stream as STREAM
from brain import zenith_version as VER
from brain import zenith_video as V


class FakeCfg:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **d):
        self.d = dict(d)

    def get(self, chave, padrao=None):
        v = self.d.get(chave, padrao)
        return padrao if v is None else v

    def update(self, mudancas):
        self.d.update(mudancas)


# ====================================================================== versão
class VersaoOficialTests(unittest.TestCase):
    def test_e_a_versao_1_0_oficial(self):
        self.assertEqual(VER.VERSAO, "v1.0")
        self.assertEqual(VER.numero(), (1, 0, 0))      # Zenith 1.0 Oficial — a primeira versão pública
        self.assertEqual(VER.ROTULO, "1.0 Oficial")
        self.assertIn("1.0 Oficial", VER.texto())

    def test_numero_aceita_o_formato_antigo(self):
        self.assertEqual(VER.numero("v30"), (30, 0, 0))          # não quebra código antigo
        self.assertEqual(VER.numero("v1.2"), (1, 2, 0))

    def test_versao_mostra_a_data_do_build(self):
        with tempfile.TemporaryDirectory() as t:
            arquivo = Path(t) / VER.ARQUIVO_BUILD
            arquivo.write_text("18/10/2026 14:05 — v1.0 — Python 3.13.1\n", encoding="utf-8")
            with mock.patch.object(VER, "_candidatos_build", lambda: [arquivo]):
                self.assertEqual(VER.data_build(), "18/10/2026 14:05")
                self.assertIn("build de 18/10/2026 14:05", VER.texto())

    def test_sem_arquivo_de_build_nao_quebra(self):
        """Rodando do código-fonte não existe VERSAO_BUILD.txt: a data vem do próprio arquivo."""
        with mock.patch.object(VER, "_candidatos_build", lambda: [Path("nao_existe_xyz.txt")]):
            data = VER.data_build()
            self.assertIsInstance(data, str)
            self.assertLess(len(data), 60)
            self.assertIn(VER.VERSAO, VER.texto())


# ====================================================================== créditos
class QuemCriouTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zcred_")
        self.arquivo = Path(self.tmp) / "creditos.txt"
        self._orig = CRED.ARQUIVO_TEXTO
        CRED.ARQUIVO_TEXTO = self.arquivo

    def tearDown(self):
        CRED.ARQUIVO_TEXTO = self._orig
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_o_nome_do_criador_esta_certo(self):
        self.assertEqual(CRED.CRIADOR, "Anderson Ricardo de Souza Filho")
        self.assertIn("Anderson Ricardo de Souza Filho", CRED.resumo())
        self.assertEqual(CRED.dados()["criador"], "Anderson Ricardo de Souza Filho")

    def test_texto_padrao_nao_fala_de_estudo_lugar_ou_idade(self):
        """Ele pediu: 'não quero falar onde estudo e tal, isso me dá preocupação'."""
        baixo = CRED.TEXTO_PADRAO.lower()
        for proibido in ("etec", "fatec", "faculdade", "universidade", "escola", "colégio", "colegio",
                         "cursando", "estudante d", "sou estudante", "idade", "anos de idade"):
            self.assertNotIn(proibido, baixo)
        self.assertIn("Anderson Ricardo de Souza Filho", CRED.TEXTO_PADRAO)

    def test_texto_do_usuario_tem_prioridade_e_ignora_comentarios(self):
        self.arquivo.write_text("# rascunho\nMeu texto de apresentação.\n\nSegunda linha.\n", encoding="utf-8")
        self.assertTrue(CRED.dados()["personalizado"])
        self.assertEqual(CRED.texto(), "Meu texto de apresentação.\n\nSegunda linha.")
        self.assertNotIn("rascunho", CRED.texto())

    def test_arquivo_vazio_ou_so_comentario_usa_o_padrao(self):
        self.arquivo.write_text("# só comentário\n", encoding="utf-8")
        self.assertFalse(CRED.dados()["personalizado"])
        self.assertEqual(CRED.texto(), CRED.TEXTO_PADRAO)

    def test_garantir_arquivo_nunca_sobrescreve(self):
        self.assertTrue(CRED.garantir_arquivo())
        self.arquivo.write_text("meu texto", encoding="utf-8")
        self.assertFalse(CRED.garantir_arquivo())
        self.assertEqual(self.arquivo.read_text(encoding="utf-8"), "meu texto")

    def test_comando_sobre_responde_sem_ia(self):
        r = CMD.tratar("/sobre")
        self.assertIsNotNone(r)
        self.assertIn("Anderson Ricardo de Souza Filho", r["resposta"])
        self.assertIn("creditos.txt", r["resposta"])       # ensina onde editar
        self.assertTrue(r["resposta"].startswith("👤") or "Zenith" in r["resposta"])

    def test_ajuda_mostra_o_comando_sobre(self):
        self.assertIn("/sobre", CMD.tratar("/ajuda")["resposta"])


# ====================================================================== A2 — segredo
class SegredoNuncaFicaGuardadoTests(unittest.TestCase):
    CHAVE = "AIzaSyD-abcdefghijklmnopqrstuvwxyz_123456"

    def test_mascara_os_principais_provedores(self):
        for chave in (self.CHAVE, "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
                      "gsk_abcdefghijklmnopqrstuvwxyz123456", "tvly-abcdefghijklmno",
                      "hf_abcdefghijklmnopqrstuvwx"):
            texto = SEG.mascarar(f"minha chave é {chave} ok")
            self.assertNotIn(chave, texto)
            self.assertIn("••••", texto)
            self.assertIn(chave[-4:], texto)               # ainda dá para reconhecer
            self.assertIn("minha chave é", texto)          # o resto do texto fica igual

    def test_bearer_mantem_o_prefixo(self):
        texto = SEG.mascarar("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345")
        self.assertIn("Bearer ", texto)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz012345", texto)

    def test_texto_normal_nao_e_mexido(self):
        for t in ("a reunião é às 14:30", "o número 1234567890", "arquivo C:\\videos\\aula.mp4",
                  "minha senha do wifi é caseira", "", None):
            self.assertEqual(SEG.mascarar(t), t)

    def test_contem_segredo(self):
        self.assertTrue(SEG.contem_segredo(f"olha {self.CHAVE}"))
        self.assertFalse(SEG.contem_segredo("só uma frase comum"))

    def test_comando_de_chave_e_reconhecido(self):
        self.assertTrue(SEG.eh_comando_de_chave("/chave add gemini AIza..."))
        self.assertTrue(SEG.eh_comando_de_chave("  /chaves somar openai sk-1"))
        self.assertFalse(SEG.eh_comando_de_chave("/chaves"))

    def test_historico_mascara_antes_de_gravar(self):
        import shutil
        from brain import zenith_history as H
        tmp = tempfile.mkdtemp(prefix="zhist_")
        try:
            with mock.patch.object(H, "HISTORY_FILE", Path(tmp) / "conversations.json"):
                conv = H.new_conversation("teste")
                H.append_message(conv, "user", f"guarda isso: {self.CHAVE}")
                bruto = (Path(tmp) / "conversations.json").read_text(encoding="utf-8")
            self.assertNotIn(self.CHAVE, bruto)
            self.assertIn("••••", bruto)
            self.assertIn(self.CHAVE[-4:], bruto)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_conversas_antigas_sao_mascaradas_uma_vez(self):
        import shutil
        tmp = tempfile.mkdtemp(prefix="zold_")
        try:
            arquivo = Path(tmp) / "conversations.json"
            arquivo.write_text(json.dumps({"active_id": "a", "conversations": [
                {"id": "a", "title": "minha chave", "pinned": False, "messages": [
                    {"sender": "user", "text": f"/chave add gemini {self.CHAVE}"}]}]}), encoding="utf-8")
            marcador = Path(tmp) / ".mascarado"
            n = SEG.mascarar_arquivo_json(arquivo, marcador)
            self.assertEqual(n, 1)
            self.assertNotIn(self.CHAVE, arquivo.read_text(encoding="utf-8"))
            self.assertEqual(SEG.mascarar_arquivo_json(arquivo, marcador), 0)   # a 2ª vez não faz nada
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_aviso_explica_o_que_fazer(self):
        aviso = SEG.AVISO_CHAVE_NO_CHAT
        for s in ("/chave add", "Configurações", "área de transferência"):
            self.assertIn(s, aviso)


# ====================================================================== A5 — comando desconhecido
class ComandoDesconhecidoTests(unittest.TestCase):
    def test_prefixo_unico_vira_sugestao_do_comando_certo(self):
        r = CMD.tratar("/vi")
        self.assertIsNotNone(r)
        self.assertIn("/video", r["resposta"])

    def test_comando_inexistente_nunca_volta_none(self):
        r = CMD.tratar("/comandoquenaoexiste")
        self.assertIsNotNone(r)                       # antes isso ia para a IA e ela inventava
        self.assertIn("Não existe", r["resposta"])
        self.assertNotIn("chat", r.get("acao") or "")

    def test_sugere_o_mais_parecido(self):
        r = CMD.tratar("/chavs")
        self.assertIn("/chaves", r["resposta"])

    def test_caminho_e_frase_continuam_como_conversa(self):
        self.assertIsNone(CMD.tratar("/home/usuario/arquivo.txt"))
        self.assertIsNone(CMD.tratar("oi tudo bem?"))
        self.assertIsNone(CMD.tratar(""))

    def test_comando_conhecido_continua_funcionando(self):
        self.assertIn("Zenith", CMD.tratar("/versao", {"versao": "Zenith v1.0"})["resposta"])


# ====================================================================== A6 — markdown
class QuebrasDeLinhaTests(unittest.TestCase):
    def test_round_trip_exato(self):
        textos = [
            "Primeira frase. Segunda frase!\n\n### Título\n\n- item 1\n- item 2\n",
            "Escalares.\n---\n\n### 1. Definição\n\nUm vetor é...\n",
            "```python\nprint('oi')\n```\n\nDepois do bloco.\n",
            "Uma linha só sem pontuação",
            "",
        ]
        for t in textos:
            self.assertEqual("".join(STREAM.fatiar_preservando(t)), t)

    def test_nao_cria_espacos_que_nao_existiam(self):
        pedacos = STREAM.fatiar_preservando("a. b. c.")
        self.assertEqual(pedacos, ["a.", " b.", " c."])

    def test_texto_vazio(self):
        self.assertEqual(STREAM.fatiar_preservando(""), [])


# ====================================================================== A7 — caminho do Windows
class CaminhoDoVideoTests(unittest.TestCase):
    # ESTA é a linha que o Anderson digitou (16/10) e recebeu "Não achei o vídeo: (vazio)".
    LINHA = ('vertical ""C:\\Users\\joao\\Videos\\2026-10-04 14-31-36.mp4"" 2:00 corte')

    def test_aspas_duplicadas_sao_desfeitas(self):
        p = CMD._caminhos(self.LINHA)
        self.assertEqual(p[0], "vertical")
        self.assertEqual(p[1], "C:\\Users\\joao\\Videos\\2026-10-04 14-31-36.mp4")
        self.assertEqual(p[2:], ["2:00", "corte"])

    def test_aspas_curvas_do_word_tambem(self):
        p = CMD._caminhos('“C:\\a\\b.mp4” 9:16')
        self.assertEqual(p, ["C:\\a\\b.mp4", "9:16"])

    def test_caminho_sem_aspas_com_espaco_e_juntado(self):
        p = CMD._juntar_caminho(CMD._caminhos("2026-10-04 14-31-36.mp4 9:16 corte"))
        self.assertEqual(p, ["2026-10-04 14-31-36.mp4", "9:16", "corte"])

    def test_tempo_no_lugar_da_proporcao_explica_e_da_exemplo(self):
        r = CMD.tratar("/video " + self.LINHA)
        self.assertIn("TEMPO", r["resposta"])
        self.assertIn("9:16", r["resposta"])
        self.assertIn("/video cortar", r["resposta"])

    def test_horizontal_vira_16_9(self):
        r = CMD.tratar('/video vertical "C:\\a\\b.mp4" horizontal')
        self.assertEqual(r["args"]["pedido"]["proporcao"], "16:9")

    def test_modo_invalido_explica(self):
        r = CMD.tratar('/video vertical "C:\\a\\b.mp4" 9:16 esticar')
        self.assertIn("corte", r["resposta"])
        self.assertIn("fundo", r["resposta"])

    def test_operacao_errada_sugere_a_parecida(self):
        r = CMD.tratar('/video cortarr "C:\\a\\b.mp4" 0:10')
        self.assertIn("cortar", r["resposta"])

    def test_caminho_vazio_explica_com_exemplo(self):
        with self.assertRaises(V.ErroVideo) as ctx:
            V._exigir_arquivo("", "o vídeo")
        msg = str(ctx.exception)
        self.assertIn("Copiar como caminho", msg)
        self.assertIn("/video vertical", msg)
        self.assertNotIn("(vazio)", msg)

    def test_caminho_que_nao_existe_mostra_o_que_foi_entendido(self):
        with self.assertRaises(V.ErroVideo) as ctx:
            V._exigir_arquivo("C:\\pasta\\nao_existe.mp4", "o vídeo")
        self.assertIn("C:\\pasta\\nao_existe.mp4", str(ctx.exception))


# ====================================================================== A19 — legenda
class LegendaComNomePerigosoTests(unittest.TestCase):
    def test_nome_com_apostrofo_virgula_e_colchete_usa_nome_seguro(self):
        import shutil
        for nome in ("o'brien, aula [1]; final.srt", "ação e coração.srt", "C:\\casos\\a'b.srt"):
            tmp = tempfile.mkdtemp(prefix="zleg_")
            try:
                srt = Path(tmp) / Path(nome).name
                srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nOi\n", encoding="utf-8")
                capturado = {}

                def falso_rodar(argv, duracao_total=0.0, progresso=None, saida="", cwd=None):
                    capturado["argv"] = argv
                    capturado["cwd"] = cwd
                    # o filtro tem de apontar para o nome seguro, dentro da pasta temporária
                    pasta = Path(cwd)
                    alvo = pasta / V.NOME_LEGENDA_SEGURA
                    capturado["existe"] = alvo.is_file()
                    capturado["igual"] = alvo.read_text(encoding="utf-8") == srt.read_text(encoding="utf-8")
                    saida_ = argv[-1]
                    Path(saida_).write_bytes(b"video")
                    return None

                with mock.patch.object(V, "_rodar", falso_rodar), \
                        mock.patch.object(V, "duracao_de", lambda *a: 1.0):
                    V.legendar("ffmpeg", str(srt), str(srt), str(Path(tmp) / "saida.mp4"))
                filtro = capturado["argv"][capturado["argv"].index("-vf") + 1]
                self.assertTrue(filtro.startswith("subtitles='" + V.NOME_LEGENDA_SEGURA + "'"))
                self.assertNotIn(Path(nome).name, filtro)          # nada do nome original no filtro
                self.assertTrue(capturado["existe"])
                self.assertTrue(capturado["igual"])
                self.assertFalse(Path(capturado["cwd"]).exists())     # a pasta temporária foi apagada
            finally:
                shutil.rmtree(tmp, ignore_errors=True)


# ====================================================================== A18 — build
class BuildNaoApagaOsDadosTests(unittest.TestCase):
    def setUp(self):
        import shutil
        import build_exe as B
        self.B, self.shutil = B, shutil
        self.raiz = Path(tempfile.mkdtemp(prefix="zbuild_"))
        self.addCleanup(shutil.rmtree, str(self.raiz), True)
        for attr, valor in (("HERE", str(self.raiz)),
                            ("_RESGATE", str(self.raiz / "_dados_do_usuario_resgatados"))):
            original = getattr(B, attr)
            setattr(B, attr, valor)
            self.addCleanup(setattr, B, attr, original)

    def _dist(self) -> Path:
        p = self.raiz / "dist" / "Zenith"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _resgate(self) -> Path:
        return self.raiz / "_dados_do_usuario_resgatados"

    def _settings(self, pasta: Path, marca: str = "chave"):
        (pasta / "config").mkdir(parents=True, exist_ok=True)
        (pasta / "config" / "settings.json").write_text('{"gemini_key": "%s"}' % marca, encoding="utf-8")

    def test_falha_na_devolucao_MANTEM_o_resgate_e_avisa(self):
        """Era aqui que o dado do usuário morria: aviso dizia \"está no resgate\" e apagava em seguida."""
        self._settings(self._resgate())
        destino = self._dist()
        original = self.shutil.copytree

        def copytree_quebrado(*a, **k):
            raise PermissionError("arquivo em uso (simulado)")

        with mock.patch.object(self.B.shutil, "copytree", copytree_quebrado), \
                mock.patch("builtins.print") as saida:
            ok = self.B._restaurar_dados_do_usuario()
        self.assertFalse(ok)
        self.assertTrue((self._resgate() / "config" / "settings.json").is_file())    # NADA foi perdido
        texto = " ".join(str(c) for c in saida.call_args_list)
        self.assertIn("ERRO", texto)
        self.assertIn("_dados_do_usuario_resgatados", texto)                          # diz onde estão
        self.assertEqual(original, self.shutil.copytree)

    def test_devolucao_parcial_de_arquivo_tambem_mantem_o_resgate(self):
        self._settings(self._resgate(), "chave-original")
        (self._resgate() / "config" / "conversations.json").write_text("{}", encoding="utf-8")
        destino = self._dist()
        original = self.shutil.copytree

        def copytree_pela_metade(origem, alvo, **k):
            original(origem, alvo, **k)
            (Path(alvo) / "conversations.json").unlink()      # simulando o arquivo que não chegou

        with mock.patch.object(self.B.shutil, "copytree", staticmethod(copytree_pela_metade)), \
                mock.patch("builtins.print"):
            ok = self.B._restaurar_dados_do_usuario()
        self.assertFalse(ok)
        self.assertTrue(self._resgate().is_dir())
        self.assertTrue((destino / "config" / "settings.json").is_file())   # o que chegou, chegou

    def test_sucesso_apaga_o_resgate(self):
        self._settings(self._resgate())
        self.assertTrue(self.B._restaurar_dados_do_usuario())
        self.assertFalse(self._resgate().exists())
        self.assertIn("chave", (self._dist() / "config" / "settings.json").read_text(encoding="utf-8"))

    def test_sem_resgate_nao_faz_nada_e_devolve_true(self):
        self.assertTrue(self.B._restaurar_dados_do_usuario())


# ====================================================================== A8 — contrato das chaves
class ContratoDasChavesTests(unittest.TestCase):
    def _cfg(self):
        return FakeCfg(gemini_key="AIzaSyD-abcdefghijklmnopqrstuvwxyz_123456",
                       chaves_extras={"gemini": ["AIzaSyD-outrachave-abcdefghijklmnopqrstu"]},
                       active_ai="gemini")

    def test_estado_da_tela_vem_todo_mascarado(self):
        from brain import zenith_chaves as CH
        with tempfile.TemporaryDirectory() as t:
            cfg = self._cfg()
            rot = CH.Rotador(cfg, arquivo=os.path.join(t, "chaves.txt"), estado=os.path.join(t, "e.json"))
            estado = CH.estado_para_tela(cfg, rot)
            self.assertEqual(estado["versao_contrato"], 1)
            bruto = json.dumps(estado, ensure_ascii=False)
            self.assertNotIn("AIzaSyD-abcdefghijklmnopqrstuvwxyz_123456", bruto)
            self.assertNotIn("AIzaSyD-outrachave", bruto)
            gem = next(p for p in estado["provedores"] if p["id"] == "gemini")
            self.assertEqual(len(gem["chaves"]), 2)
            self.assertTrue(gem["chaves"][0]["principal"])
            self.assertFalse(gem["chaves"][1]["principal"])
            self.assertEqual(gem["chaves"][0]["estado"], "livre")
            self.assertIn("ia_local", estado)
            self.assertIn("rota", estado)

    def test_estado_marca_castigo_e_invalida(self):
        from brain import zenith_chaves as CH
        with tempfile.TemporaryDirectory() as t:
            cfg = self._cfg()
            agora = [1000.0]
            rot = CH.Rotador(cfg, arquivo=os.path.join(t, "chaves.txt"), estado=os.path.join(t, "e.json"),
                             relogio=lambda: agora[0])
            rot.marcar_erro("gemini", cfg.get("gemini_key"), "429 quota exceeded")
            estado = CH.estado_para_tela(cfg, rot)
            primeira = next(p for p in estado["provedores"] if p["id"] == "gemini")["chaves"][0]
            self.assertEqual(primeira["estado"], "castigo")
            self.assertGreater(primeira["segundos"], 0)

    def test_como_obter_aponta_o_site_do_provedor(self):
        info = CRED  # só para deixar claro que este teste é de tela, não de créditos
        from brain import zenith_chaves as CH
        link = CH.link_para_pegar_chave("gemini")
        self.assertEqual(link.get("onde"), "aistudio.google.com/apikey")
        self.assertTrue(link.get("dica"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
