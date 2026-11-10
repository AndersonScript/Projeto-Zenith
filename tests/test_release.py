"""Testes do gerador de release (tools/gerar_release.py) e da configuração do build do Launcher."""
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from launcher import build_launcher as BL            # noqa: E402
from launcher import zenith_instalador as L          # noqa: E402
from tools import gerar_release as GR                # noqa: E402

PY_SHA = "a" * 64


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zr_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pacote = self.tmp / "pacote"
        (self.pacote / "brain").mkdir(parents=True)
        (self.pacote / "zenith_launcher.py").write_text("x")
        (self.pacote / "requirements.txt").write_text("openai>=1\n")
        (self.pacote / "brain" / "zenith_version.py").write_text('VERSAO = "v1.6.1"\n')
        (self.pacote / "config").mkdir()
        (self.pacote / "config" / "provedores_catalogo.json").write_text("{}")
        exp = self.pacote / "body" / "zenith" / "export"
        exp.mkdir(parents=True)
        (exp / "Zenith.exe").write_bytes(b"MZ")


class ConferirTests(Base):
    def test_pacote_bom_passa(self):
        self.assertEqual(GR.conferir_pasta(self.pacote, "1.6.1"), [])

    def test_recusa_dado_pessoal_avatar_e_chave(self):
        (self.pacote / "config" / "settings.json").write_text("{}")
        with self.assertRaises(GR.ErroRelease):
            GR.conferir_pasta(self.pacote, "1.6.1")
        (self.pacote / "config" / "settings.json").unlink()
        (self.pacote / "meu.vrm").write_bytes(b"x")
        with self.assertRaises(GR.ErroRelease):
            GR.conferir_pasta(self.pacote, "1.6.1")
        (self.pacote / "meu.vrm").unlink()
        (self.pacote / "brain" / "a.py").write_text('K = "AIza' + "x" * 35 + '"')
        with self.assertRaises(GR.ErroRelease) as cm:
            GR.conferir_pasta(self.pacote, "1.6.1")
        self.assertIn("chave", str(cm.exception))

    def test_versao_tem_que_bater_com_o_codigo(self):
        with self.assertRaises(GR.ErroRelease) as cm:
            GR.conferir_pasta(self.pacote, "1.7")
        self.assertIn("zenith_version", str(cm.exception))

    def test_sem_corpo_exportado(self):
        shutil.rmtree(self.pacote / "body")
        with self.assertRaises(GR.ErroRelease):
            GR.conferir_pasta(self.pacote, "1.6.1")
        self.assertEqual(len(GR.conferir_pasta(self.pacote, "1.6.1", exigir_corpo=False)), 1)

    def test_nao_e_o_zenith(self):
        (self.pacote / "zenith_launcher.py").unlink()
        with self.assertRaises(GR.ErroRelease):
            GR.conferir_pasta(self.pacote, "1.6.1")


class ZipETests(Base):
    def test_zip_e_deterministico(self):
        a = GR.montar_zip(self.pacote, self.tmp / "a.zip")
        b = GR.montar_zip(self.pacote, self.tmp / "b.zip")
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["tamanho"], (self.tmp / "a.zip").stat().st_size)

    def test_exclui_lixo(self):
        (self.pacote / "brain" / "__pycache__").mkdir()
        (self.pacote / "brain" / "__pycache__" / "x.pyc").write_bytes(b"1")
        (self.pacote / "release").mkdir()
        (self.pacote / "release" / "velho.zip").write_bytes(b"1")
        GR.montar_zip(self.pacote, self.tmp / "a.zip")
        nomes = zipfile.ZipFile(self.tmp / "a.zip").namelist()
        self.assertFalse([n for n in nomes if "__pycache__" in n or "release/" in n])
        self.assertIn("Zenith/zenith_launcher.py", nomes)

    def test_o_launcher_consegue_extrair_o_zip_gerado(self):
        GR.montar_zip(self.pacote, self.tmp / "a.zip")
        L.extrair_seguro(self.tmp / "a.zip", self.tmp / "out")
        self.assertTrue((self.tmp / "out" / "zenith_launcher.py").exists())
        self.assertTrue((self.tmp / "out" / "body/zenith/export/Zenith.exe").exists())


class ManifestoTests(Base):
    def test_o_manifesto_gerado_passa_na_validacao_do_launcher(self):
        info = GR.montar_zip(self.pacote, self.tmp / "Zenith_app_1.6.1.zip")
        man = GR.montar_manifesto("v1.6.1", "a\nb", "https://github.com/u/z/releases/download/v1.6.1", info,
                                  "Zenith_app_1.6.1.zip", "3.12.10", "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe",
                                  PY_SHA, 0,
                                  {"versao": "1.0.0", "arquivo": "ZenithLauncher.exe", "url": "https://github.com/u/z/releases/download/v1.6.1/ZenithLauncher.exe",
                                   "sha256": "b" * 64, "tamanho": 1000})
        hosts = ["github.com", "www.python.org"]
        ok = L.validar_manifesto(json.loads(json.dumps(man)), hosts)
        self.assertEqual(ok["versao"], "1.6.1")
        self.assertEqual(ok["launcher"]["sha256"], "b" * 64)
        self.assertEqual(man["url"], man["pacote"]["url"])                 # chaves do /atualizar de dentro do Zenith
        self.assertEqual(man["sha256"], man["pacote"]["sha256"])

    def test_versions_json_acumula_sem_duplicar(self):
        man = {"versao": "1.6.1", "data": "2026-10-24", "pacote": {"tamanho": 5, "sha256": "c" * 64}}
        arq = self.tmp / "versions.json"
        arq.write_text(json.dumps({"repositorio": "https://github.com/u/z", "versoes": [{"versao": "1.6", "data": "x"}, {"versao": "1.6.1", "data": "velho"}]}))
        GR.atualizar_versions_json(arq, man, ["nota"])
        d = json.loads(arq.read_text())
        self.assertEqual([v["versao"] for v in d["versoes"]], ["1.6.1", "1.6"])
        self.assertEqual(d["versoes"][0]["notas"], ["nota"])
        self.assertEqual(d["repositorio"], "https://github.com/u/z")

    def test_main_ponta_a_ponta_sem_rede(self):
        site, saida = self.tmp / "site", self.tmp / "release"
        cod = GR.main(["--versao", "1.6.1", "--pacote", str(self.pacote), "--base-url", "https://github.com/u/z/releases/download/v1.6.1",
                       "--python-sha256", PY_SHA, "--site", str(site), "--saida", str(saida), "--notas", "um; dois"])
        self.assertEqual(cod, 0)
        man = json.loads((site / "latest.json").read_text())
        self.assertEqual(man["notas"], "um\ndois")
        zip_ = saida / "Zenith_app_1.6.1.zip"
        self.assertEqual(man["pacote"]["sha256"], __import__("hashlib").sha256(zip_.read_bytes()).hexdigest())
        L.validar_manifesto(man, ["github.com", "www.python.org"])
        self.assertEqual(GR.main(["--versao", "9.9", "--pacote", str(self.pacote), "--base-url", "https://x", "--python-sha256", PY_SHA,
                                  "--site", str(site), "--saida", str(saida)]), 1)


class ConfigDoBuildTests(unittest.TestCase):
    def test_config_do_launcher(self):
        c = BL.montar_config("https://zenith-app.vercel.app/", ["meu.cdn.com", "github.com"])
        self.assertEqual(c["manifesto"], "https://zenith-app.vercel.app/latest.json")
        self.assertEqual(c["hosts"][0], "zenith-app.vercel.app")
        self.assertIn("www.python.org", c["hosts"])
        self.assertEqual(c["hosts"].count("github.com"), 1)
        self.assertFalse(c["permitir_local"])

    def test_site_precisa_ser_https(self):
        with self.assertRaises(SystemExit):
            BL.montar_config("http://zenith.vercel.app")


if __name__ == "__main__":
    unittest.main()
