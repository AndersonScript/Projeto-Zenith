"""v1.10 — Launcher: download com certificado que funciona e limpeza por partes/desinstalação.

Dois casos reais de 30/10/2026:
  1. o download parava em `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`;
  2. não havia como apagar só o histórico, só as chaves, só as fotos — nem desinstalar de verdade.
"""
import json
import shutil
import ssl
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from launcher import zenith_instalador as ZI          # noqa: E402


class CertificadoTests(unittest.TestCase):
    def test_contexto_confia_no_certifi_embutido(self):
        ctx = ZI.contexto_ssl()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        # o certifi traz centenas de raízes; sem elas o Windows antigo recusava o site
        self.assertGreater(ctx.cert_store_stats()["x509_ca"], 50)

    def test_erro_de_certificado_ganha_explicacao_propria(self):
        e = urllib.error.URLError(ssl.SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"))
        err = ZI._erro_de_rede(e)
        self.assertIn("certificado", str(err))
        self.assertIn("data e a hora", err.dica)
        self.assertIn("baixe pelo navegador", err.dica)

    def test_erro_de_rede_comum_continua_generico(self):
        err = ZI._erro_de_rede(urllib.error.URLError("sem rota para o host"))
        self.assertIn("Falha ao baixar", str(err))
        self.assertNotIn("certificado", str(err))


def montar_instalacao(tmp: Path, dados_fora: bool = False):
    """Uma instalação de mentira com o mesmo formato que o Launcher cria."""
    raiz = tmp / "Zenith"
    app = raiz / "app"
    (app / "config").mkdir(parents=True)
    (app / "skills").mkdir()
    dados = (tmp / "Zenith-dados") if dados_fora else (raiz / "dados")
    for sub in ("creations", "temp", "memory_db"):
        (dados / sub).mkdir(parents=True, exist_ok=True)
    (app / "config" / "settings.json").write_text(json.dumps({
        "gemini_key": "AIza-segredo", "groq_key": "gsk-segredo", "openrouter_key": "sk-or-segredo",
        "user_name": "Anderson", "ai_endpoints": [{"nome": "x"}], "persona_name": "Zenith"}), encoding="utf-8")
    (app / "config" / "instalacao.json").write_text(json.dumps({"data_root_path": str(dados)}), encoding="utf-8")
    (app / "config" / "conversations.json").write_text('{"conversas": [1, 2]}', encoding="utf-8")
    (app / "config" / "zenith_lembretes.json").write_text("[]", encoding="utf-8")
    (app / "config" / "ZENITH.md").write_text("coisas pessoais", encoding="utf-8")
    (app / "zenith_log.txt").write_text("log", encoding="utf-8")
    (app / "skills" / "minha_habilidade.py").write_text("print(1)", encoding="utf-8")
    (dados / "creations" / "foto.png").write_bytes(b"x" * 1000)
    (dados / "creations" / "video.mp4").write_bytes(b"x" * 2000)
    (dados / "temp" / "rascunho.txt").write_text("r", encoding="utf-8")
    (dados / "memory_db" / "chroma.sqlite3").write_bytes(b"m" * 500)
    return raiz, dados


class LimparPorPartesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zl_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.raiz, self.dados = montar_instalacao(self.tmp)
        self.config = self.raiz / "app" / "config"

    def limpar(self, *cats):
        return ZI.limpar_pedacos(self.raiz, list(cats), log=lambda *a, **k: None)

    def test_historico_apaga_conversas_e_deixa_o_resto(self):
        rel = self.limpar("historico")
        self.assertFalse((self.config / "conversations.json").exists())
        self.assertFalse((self.config / "zenith_lembretes.json").exists())
        self.assertFalse((self.raiz / "app" / "zenith_log.txt").exists())
        self.assertTrue((self.config / "settings.json").exists())
        self.assertTrue((self.config / "ZENITH.md").exists())
        self.assertTrue((self.dados / "creations" / "foto.png").exists())
        self.assertGreater(rel["itens"], 2)

    def test_chaves_zera_so_as_chaves(self):
        self.limpar("chaves")
        dados = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(dados["gemini_key"], "")
        self.assertEqual(dados["groq_key"], "")
        self.assertEqual(dados["openrouter_key"], "")
        self.assertEqual(dados["ai_endpoints"], [])
        self.assertEqual(dados["user_name"], "Anderson")          # identidade não é chave
        self.assertTrue((self.config / "conversations.json").exists())

    def test_fotos_apaga_imagens_e_videos(self):
        self.limpar("fotos")
        self.assertEqual(list((self.dados / "creations").iterdir()), [])
        self.assertTrue((self.dados / "memory_db" / "chroma.sqlite3").exists())

    def test_memoria_apaga_a_memoria_de_longo_prazo(self):
        self.limpar("memoria")
        self.assertEqual(list((self.dados / "memory_db").iterdir()), [])
        self.assertTrue((self.dados / "creations" / "foto.png").exists())

    def test_programas_apaga_o_que_ela_criou(self):
        self.limpar("programas")
        self.assertEqual(list((self.raiz / "app" / "skills").iterdir()), [])

    def test_pessoal_apaga_o_que_o_usuario_escreveu(self):
        self.limpar("pessoal")
        self.assertFalse((self.config / "ZENITH.md").exists())
        self.assertTrue((self.config / "conversations.json").exists())

    def test_temporarios_apaga_rascunhos(self):
        self.limpar("temporarios")
        self.assertEqual(list((self.dados / "temp").iterdir()), [])

    def test_tudo_limpa_tudo_menos_o_programa(self):
        self.limpar("tudo")
        self.assertTrue((self.raiz / "app" / "config" / "settings.json").exists())   # o programa fica
        self.assertFalse((self.config / "conversations.json").exists())
        self.assertFalse((self.config / "ZENITH.md").exists())
        self.assertEqual(list((self.dados / "creations").iterdir()), [])
        self.assertEqual(list((self.dados / "memory_db").iterdir()), [])

    def test_nome_errado_e_recusado(self):
        with self.assertRaises(ZI.ErroInstalador):
            ZI.ler_categorias("historico,bananas")

    def test_aceita_virgula_espaco_e_ponto_e_virgula(self):
        self.assertEqual(ZI.ler_categorias("historico; chaves,fotos"),
                         ["chaves", "fotos", "historico"])

    def test_dados_em_pasta_escolhida_pelo_usuario(self):
        tmp2 = Path(tempfile.mkdtemp(prefix="zl2_"))
        self.addCleanup(shutil.rmtree, tmp2, True)
        raiz2, dados2 = montar_instalacao(tmp2, dados_fora=True)
        ZI.limpar_pedacos(raiz2, ["fotos"], log=lambda *a, **k: None)
        self.assertEqual(list((dados2 / "creations").iterdir()), [])


class DesinstalarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zd_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.raiz, self.dados = montar_instalacao(self.tmp, dados_fora=True)
        p = mock.patch.object(ZI, "_atalhos", lambda: [])
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(ZI.time, "sleep", lambda *_: None)
        p.start()
        self.addCleanup(p.stop)
        self.ui = mock.Mock()

    def test_apaga_a_instalacao_a_pasta_de_dados_e_nao_sobra_nada(self):
        codigo = ZI.desinstalar_tudo(self.raiz, self.ui, executar=lambda *a, **k: (0, ""))
        self.assertEqual(codigo, 0)
        self.assertFalse(self.raiz.exists())
        self.assertFalse(self.dados.exists())
        self.assertTrue(any("MB liberados" in str(c.args[0]) for c in self.ui.status.call_args_list))

    def test_nao_apaga_raiz_de_disco_nem_a_pasta_do_usuario(self):
        self.assertFalse(ZI._pode_apagar(Path("C:/")))
        self.assertFalse(ZI._pode_apagar(Path.home()))
        self.assertFalse(ZI._pode_apagar(self.tmp / "nao_existe"))
        self.assertTrue(ZI._pode_apagar(self.raiz))

    def test_desinstalar_pergunta_antes_e_respeita_o_nao(self):
        args = mock.Mock(pasta=str(self.raiz), desinstalar=True, limpar=None)
        ui = mock.Mock()
        ui.perguntar.return_value = False
        self.assertEqual(ZI.executar_limpeza(args, ui), 0)
        self.assertTrue(self.raiz.exists())          # disse não: nada foi apagado

    def test_desinstalar_com_sim_apaga(self):
        args = mock.Mock(pasta=str(self.raiz), desinstalar=True, limpar=None)
        ui = mock.Mock()
        ui.perguntar.return_value = True
        with mock.patch.object(ZI, "desinstalar_tudo", return_value=0) as d:
            self.assertEqual(ZI.executar_limpeza(args, ui), 0)
            d.assert_called_once()

    def test_limpar_pela_linha_de_comando_pergunta_e_apaga(self):
        args = mock.Mock(pasta=str(self.raiz), desinstalar=False, limpar="conversas")   # nome inválido
        ui = mock.Mock()
        ui.perguntar.return_value = True
        self.assertEqual(ZI.executar_limpeza(args, ui), 3)
        self.assertTrue((self.raiz / "app" / "config" / "conversations.json").exists())


if __name__ == "__main__":
    unittest.main()
