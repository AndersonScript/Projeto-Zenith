"""v1.7 — instalar/abrir e atualizar o Zenith sem Freebuff e sem .bat. Nenhum teste usa rede, pip de verdade ou a pasta real do Zenith."""
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tools import instalar_zenith as I           # noqa: E402
from tools import atualizar_de_zip as AT         # noqa: E402

SAIDA_PY_LAUNCHER = """Installed Pythons found by py Launcher for Windows
 -V:3.14 *        C:\\Python314\\python.exe
 -V:3.13          D:\\Programas\\AppData\\Local\\Programs\\Python\\Python313\\python.exe
 -3.12-64         D:\\Programas\\AppData\\Local\\Programs\\Python\\Python312\\python.exe
"""


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="zenith_v17_"))
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)


class PythonTests(unittest.TestCase):
    def test_classificacao(self):
        self.assertEqual([I.classificar_versao(v) for v in ((3, 13), (3, 12), (3, 11), (3, 14), (3, 9))],
                         ["otimo", "otimo", "aceito", "ruim", "ruim"])

    def test_le_a_lista_do_py_launcher_nos_dois_formatos(self):
        fake = lambda *a, **k: types.SimpleNamespace(stdout=SAIDA_PY_LAUNCHER, returncode=0)
        achados = I.listar_pythons(rodar=fake, plataforma="win32", which=lambda n: None)
        versoes = [v for v, _ in achados]
        self.assertIn((3, 14), versoes)
        self.assertIn((3, 13), versoes)
        self.assertIn((3, 12), versoes)
        self.assertTrue(any("Python313" in c for _, c in achados))

    def test_escolhe_o_313_mesmo_com_314_como_padrao(self):
        esc = I.escolher([((3, 14), "C:/P314/python.exe"), ((3, 12), "C:/P312/python.exe"), ((3, 13), "C:/P313/python.exe")])
        self.assertEqual(esc[0], (3, 13))
        self.assertEqual(esc[2], "otimo")

    def test_so_314_nao_serve_e_311_serve_com_aviso(self):
        self.assertIsNone(I.escolher([((3, 14), "x"), ((3, 9), "y")]))
        esc = I.escolher([((3, 14), "x"), ((3, 11), "z")])
        self.assertEqual((esc[0], esc[2]), ((3, 11), "aceito"))

    def test_mensagens_do_pip_em_portugues(self):
        self.assertIn("Exclusões", I.diagnosticar_pip("ERROR: [WinError 5] Acesso negado: 'x.pyd'"))
        self.assertIn("3.13", I.diagnosticar_pip("ERROR: No matching distribution found for onnxruntime"))
        self.assertIn("internet", I.diagnosticar_pip("ReadTimeoutError: HTTPSConnectionPool timed out"))
        self.assertIn("instalacao.log", I.diagnosticar_pip("erro estranho"))

    def test_sem_python_bom_mostra_o_comando_e_so_instala_se_a_pessoa_disser_sim(self):
        saida = []
        chamadas = []
        ok = I.oferecer_instalar_python(entrada=lambda _: "n", rodar=lambda *a, **k: chamadas.append(a) or types.SimpleNamespace(returncode=0),
                                        which=lambda n: "C:/winget.exe", imprimir=saida.append)
        self.assertFalse(ok)
        self.assertEqual(chamadas, [])                                   # nada instalado sem o "sim"
        self.assertIn("winget install -e --id Python.Python.3.13", "\n".join(saida))
        ok = I.oferecer_instalar_python(entrada=lambda _: "s", rodar=lambda *a, **k: chamadas.append(a) or types.SimpleNamespace(returncode=0),
                                        which=lambda n: "C:/winget.exe", imprimir=saida.append)
        self.assertTrue(ok)
        self.assertEqual(len(chamadas), 1)

    def test_sem_winget_so_explica(self):
        ok = I.oferecer_instalar_python(entrada=lambda _: "s", rodar=lambda *a, **k: self.fail("não podia rodar"),
                                        which=lambda n: None, imprimir=lambda *_: None)
        self.assertFalse(ok)


class AmbienteTests(_Tmp):
    def test_requisitos_so_reinstalam_quando_o_arquivo_muda(self):
        req = self.d / "requirements.txt"
        marca = self.d / ".venv" / "marca"
        marca.parent.mkdir()
        req.write_text("openai\n", encoding="utf-8")
        self.assertFalse(I.requisitos_em_dia(self.d / ".venv", req, marca))
        marca.write_text(I.hash_requisitos(req), encoding="utf-8")
        self.assertTrue(I.requisitos_em_dia(self.d / ".venv", req, marca))
        req.write_text("openai\nrequests\n", encoding="utf-8")
        self.assertFalse(I.requisitos_em_dia(self.d / ".venv", req, marca))

    def test_venv_feito_com_python_errado_e_refeito(self):
        venv = self.d / ".venv"
        py = I.python_do_venv(venv)
        py.parent.mkdir(parents=True)
        py.write_text("", encoding="utf-8")
        com314 = lambda *a, **k: types.SimpleNamespace(stdout="3 14", returncode=0)
        com313 = lambda *a, **k: types.SimpleNamespace(stdout="3 13", returncode=0)
        self.assertFalse(I.venv_serve((3, 13), venv, rodar=com314))
        self.assertTrue(I.venv_serve((3, 13), venv, rodar=com313))
        self.assertFalse(I.venv_serve((3, 13), self.d / "nao_existe"))

    def test_planejar_primeira_vez_cria_e_instala(self):
        plano = I.planejar([((3, 13), "C:/p/python.exe")], venv=self.d / ".venv", req=self.d / "r.txt")
        self.assertTrue(plano["refazer_venv"] and plano["instalar"])
        self.assertEqual(plano["python"][0], (3, 13))

    def test_planejar_sem_python_bom(self):
        self.assertIsNone(I.planejar([((3, 14), "x")], venv=self.d / ".venv")["python"])

    def test_falha_do_pip_grava_log_e_devolve_o_texto(self):
        log = self.d / "temp" / "instalacao.log"
        fake = lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="saida", stderr="ERROR: No matching distribution")
        ok, texto = I.instalar_requisitos("py", self.d / "r.txt", log, rodar=fake)
        self.assertFalse(ok)
        self.assertIn("No matching", log.read_text(encoding="utf-8"))

    def test_so_conferir_nao_cria_nada(self):
        saida = []
        with mock.patch.object(I, "listar_pythons", return_value=[((3, 13), "C:/p/python.exe")]), \
                mock.patch.object(I, "VENV", self.d / ".venv"):
            codigo = I.main(["--so-conferir"], imprimir=saida.append)
        self.assertEqual(codigo, 0)
        self.assertFalse((self.d / ".venv").exists())
        self.assertIn("Python escolhido: 3.13", "\n".join(saida))

    def test_so_conferir_sem_python_bom_devolve_erro_sem_perguntar(self):
        with mock.patch.object(I, "listar_pythons", return_value=[((3, 14), "x")]):
            self.assertEqual(I.main(["--so-conferir"], imprimir=lambda *_: None), 2)

    def test_arquivos_de_entrada_existem_e_apontam_para_tools(self):
        for nome, alvo in (("INICIAR_ZENITH.py", "instalar_zenith.py"), ("ATUALIZAR_ZENITH.py", "atualizar_de_zip.py")):
            txt = (RAIZ / nome).read_text(encoding="utf-8")
            self.assertIn(alvo, txt)
        self.assertFalse(list(RAIZ.glob("INICIAR*.bat")))                   # .bat é bloqueado pelo Windows


def _zip(destino: Path, arquivos: dict, prefixo: str = "") -> Path:
    with zipfile.ZipFile(destino, "w") as z:
        for nome, conteudo in arquivos.items():
            z.writestr(prefixo + nome, conteudo)
    return destino


BASE_ZENITH = {"brain/zenith_version.py": 'VERSAO = "v9.9"\n', "body/zenith/project.godot": "x", "zenith_launcher.py": "# l\n",
               "brain/zenith_core.py": "novo\n", "config/provedores_catalogo.json": "{}", "edition.json": '{"edicao":"publico"}'}


class AtualizarTests(_Tmp):
    def _destino(self):
        d = self.d / "meu_zenith"
        for rel, txt in {"brain/zenith_core.py": "velho\n", "brain/zenith_version.py": 'VERSAO = "v1.0"\n', "zenith_launcher.py": "# l\n",
                         "body/zenith/project.godot": "x", "config/settings.json": '{"chave": "segredo"}', "edition.json": '{"edicao":"admin"}',
                         "memory_db/dados.bin": "minhas lembranças", "creations/programa/a.py": "meu código"}.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(txt, encoding="utf-8")
        return d

    def _origem(self, extra=None):
        o = self.d / "origem"
        for rel, txt in {**BASE_ZENITH, "config/settings.json": '{"chave": "VAZIO"}', "memory_db/dados.bin": "LIXO", "creations/x.py": "LIXO",
                         "arquivo_novo.py": "oi", **(extra or {})}.items():
            (o / rel).parent.mkdir(parents=True, exist_ok=True)
            (o / rel).write_text(txt, encoding="utf-8")
        return o

    def test_plano_nunca_mexe_nos_dados_do_usuario(self):
        dest, org = self._destino(), self._origem()
        plano = AT.montar_plano(org, dest)
        todos = plano["trocar"] + plano["novos"]
        self.assertNotIn("memory_db/dados.bin", todos)
        self.assertNotIn("creations/x.py", todos)
        self.assertNotIn("config/settings.json", todos)                  # existe: protegido
        self.assertNotIn("edition.json", todos)                          # a edição dele não vira a do zip
        self.assertIn("brain/zenith_core.py", plano["trocar"])
        self.assertIn("arquivo_novo.py", plano["novos"])
        self.assertIn("config/settings.json", plano["protegidos"])

    def test_catalogo_de_ias_e_atualizado_mesmo_existindo(self):
        dest, org = self._destino(), self._origem()
        (dest / "config/provedores_catalogo.json").write_text("{velho}", encoding="utf-8")
        plano = AT.montar_plano(org, dest)
        self.assertIn("config/provedores_catalogo.json", plano["trocar"])         # vem do programa: precisa chegar
        self.assertNotIn("config/settings.json", plano["trocar"])                 # as chaves e preferências dele continuam intocadas

    def test_config_que_nao_existe_ainda_e_criada(self):
        dest, org = self._destino(), self._origem()
        self.assertIn("config/provedores_catalogo.json", AT.montar_plano(org, dest)["novos"])

    def test_aplicar_troca_so_o_que_mudou_e_guarda_backup_do_velho(self):
        dest, org = self._destino(), self._origem()
        r = AT.aplicar(AT.montar_plano(org, dest), org, dest, self.d / "backups")
        self.assertEqual((dest / "brain/zenith_core.py").read_text(encoding="utf-8"), "novo\n")
        self.assertTrue((dest / "arquivo_novo.py").exists())
        self.assertEqual((dest / "memory_db/dados.bin").read_text(encoding="utf-8"), "minhas lembranças")
        self.assertEqual((dest / "config/settings.json").read_text(encoding="utf-8"), '{"chave": "segredo"}')
        self.assertEqual((dest / "edition.json").read_text(encoding="utf-8"), '{"edicao":"admin"}')
        with zipfile.ZipFile(r["backup"]) as z:
            # o backup guarda os BYTES originais (o fim de linha do texto varia com o sistema)
            self.assertEqual(z.read("brain/zenith_core.py"), b"velho" + os.linesep.encode())

    def test_arquivo_em_uso_desfaz_tudo(self):
        dest, org = self._destino(), self._origem()
        plano = AT.montar_plano(org, dest)
        original = shutil.copy2
        chamadas = {"n": 0}

        def quebra_no_segundo(a, b, *k, **kw):
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                raise PermissionError("em uso")
            return original(a, b, *k, **kw)
        with mock.patch.object(AT.shutil, "copy2", side_effect=quebra_no_segundo):
            with self.assertRaises(PermissionError):
                AT.aplicar(plano, org, dest, self.d / "backups")
        self.assertEqual((dest / "brain/zenith_core.py").read_text(encoding="utf-8"), "velho\n")       # voltou
        self.assertFalse((dest / "arquivo_novo.py").exists())

    def test_zip_com_caminho_perigoso_e_recusado(self):
        zp = _zip(self.d / "mau.zip", {"../fora.txt": "x"})
        with self.assertRaises(ValueError):
            AT.extrair_seguro(zp, self.d / "ext")
        self.assertFalse((self.d / "fora.txt").exists())

    def test_zip_com_atalho_e_recusado(self):
        zp = self.d / "link.zip"
        with zipfile.ZipFile(zp, "w") as z:
            info = zipfile.ZipInfo("brain/atalho")
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "/etc/passwd")
        with self.assertRaises(ValueError):
            AT.extrair_seguro(zp, self.d / "ext")

    def test_acha_a_raiz_mesmo_dentro_de_uma_pasta(self):
        zp = _zip(self.d / "ok.zip", BASE_ZENITH, prefixo="Zenith_v9.9/")
        AT.extrair_seguro(zp, self.d / "ext")
        raiz = AT.achar_raiz(self.d / "ext")
        self.assertEqual(raiz.name, "Zenith_v9.9")
        self.assertEqual(AT.versao_de(raiz), "v9.9")

    def test_zip_que_nao_e_do_zenith_e_recusado(self):
        zp = _zip(self.d / "outro.zip", {"readme.txt": "oi"})
        with tempfile.TemporaryDirectory() as tmp:
            AT.extrair_seguro(zp, Path(tmp))
            self.assertIsNone(AT.achar_raiz(Path(tmp)))

    def test_main_so_conferir_nao_altera_nada(self):
        dest = self._destino()
        zp = _zip(self.d / "novo.zip", BASE_ZENITH, prefixo="Zenith_v9.9/")
        saida = []
        with mock.patch.object(AT, "RAIZ", dest):
            codigo = AT.main([str(zp), "--so-conferir"], imprimir=saida.append)
        self.assertEqual(codigo, 0)
        self.assertEqual((dest / "brain/zenith_core.py").read_text(encoding="utf-8"), "velho\n")
        self.assertIn("v1.0  ->  nova: v9.9", "\n".join(saida))
        self.assertFalse((dest / "backups").exists())

    def test_main_atualiza_de_verdade(self):
        dest = self._destino()
        zp = _zip(self.d / "novo.zip", BASE_ZENITH, prefixo="Zenith_v9.9/")
        with mock.patch.object(AT, "RAIZ", dest):
            self.assertEqual(AT.main([str(zp)], imprimir=lambda *_: None), 0)
        self.assertEqual((dest / "brain/zenith_core.py").read_text(encoding="utf-8"), "novo\n")
        self.assertTrue(list((dest / "backups").glob("antes_*.zip")))

    def test_main_sem_argumento_ou_arquivo_inexistente(self):
        self.assertEqual(AT.main([], imprimir=lambda *_: None), 2)
        self.assertEqual(AT.main([str(self.d / "nao_existe.zip")], imprimir=lambda *_: None), 2)


if __name__ == "__main__":
    unittest.main()
