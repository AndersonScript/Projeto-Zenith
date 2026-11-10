"""Testes do Zenith Launcher (launcher/zenith_instalador.py) — tudo com rede, instalador do Python e pip FALSOS.

Provam: conferência do latest.json, lista de endereços permitidos, download com SHA-256, extração contra zip malicioso,
troca da pasta app com dados do usuário preservados (e volta atrás), requirements em essenciais/opcionais, e o fluxo
inteiro (primeira instalação, atualização, sem internet, reverter).
NÃO provam: o instalador real do Python, o pip real, atalhos, a janela (tkinter) nem o .exe do PyInstaller.
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from launcher import zenith_instalador as L          # noqa: E402

HOSTS = ["site.vercel.app", "github.com", "objects.githubusercontent.com", "python.org"]
URL_M = "https://site.vercel.app/latest.json"
URL_P = "https://github.com/x/zenith/releases/download/v9/app.zip"
URL_PY = "https://python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def zip_bytes(arquivos, raiz=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr((raiz + "/" if raiz else "") + nome, dados)
    return buf.getvalue()


class Resp:
    def __init__(self, dados: bytes):
        self._b = io.BytesIO(dados)
        self.headers = {"Content-Length": str(len(dados))}

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def manifesto_dict(versao, pacote_bytes, py_bytes=b"PYINSTALADOR", extra=None):
    d = {"versao": versao, "notas": "mudou x",
         "pacote": {"url": URL_P, "sha256": sha(pacote_bytes), "tamanho": len(pacote_bytes)},
         "python": {"versao": "3.12.10", "url": URL_PY, "sha256": sha(py_bytes), "tamanho": len(py_bytes)}}
    d.update(extra or {})
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zl_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


# ------------------------------------------------------------------ endereços e manifesto
class EnderecosTests(unittest.TestCase):
    def test_so_https_da_lista(self):
        self.assertTrue(L.host_permitido("https://github.com/a/b", HOSTS))
        self.assertFalse(L.host_permitido("http://github.com/a", HOSTS))
        self.assertFalse(L.host_permitido("https://evil.com/a", HOSTS))
        self.assertFalse(L.host_permitido("https://github.com.evil.com/a", HOSTS))
        self.assertFalse(L.host_permitido("file:///c:/x", HOSTS))
        self.assertFalse(L.host_permitido("", HOSTS))

    def test_local_so_quando_liberado(self):
        self.assertFalse(L.host_permitido("http://127.0.0.1:8000/x", HOSTS))
        self.assertTrue(L.host_permitido("http://127.0.0.1:8000/x", HOSTS, permitir_local=True))
        self.assertFalse(L.host_permitido("http://evil.com/x", HOSTS, permitir_local=True))

    def test_redirecionamento_para_fora_da_lista_e_recusado(self):
        h = L._RedirectSeguro(HOSTS)
        req = urllib.request.Request("https://github.com/a")
        with self.assertRaises(urllib.error.URLError):
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.com/malware.zip")
        ok = h.redirect_request(req, None, 302, "Found", {}, "https://objects.githubusercontent.com/zip")
        self.assertIsNotNone(ok)

    def test_abrir_url_recusa_endereco_fora_da_lista_sem_rede(self):
        with self.assertRaises(L.ErroInstalador):
            L.abrir_url("https://evil.com/x", HOSTS)


import urllib.request   # noqa: E402  (usado acima)


class VersaoTests(unittest.TestCase):
    def test_comparacao(self):
        self.assertGreater(L.versao_tupla("1.6.2"), L.versao_tupla("1.6.1"))
        self.assertGreater(L.versao_tupla("1.10"), L.versao_tupla("1.9.9"))
        self.assertEqual(L.versao_tupla("v1.7"), (1, 7, 0))
        self.assertEqual(L.versao_tupla("lixo"), (0, 0, 0))


class ManifestoTests(unittest.TestCase):
    def test_valido(self):
        m = L.validar_manifesto(manifesto_dict("1.7", b"zip"), HOSTS)
        self.assertEqual(m["versao"], "1.7")
        self.assertEqual(m["pacote"]["sha256"], sha(b"zip"))
        self.assertIsNone(m["launcher"])

    def test_recusa_sem_versao_sem_hash_ou_endereco_estranho(self):
        d = manifesto_dict("1.7", b"zip")
        for estraga in (lambda x: x.pop("versao"),
                        lambda x: x["pacote"].__setitem__("sha256", "abc"),
                        lambda x: x["pacote"].__setitem__("url", "https://evil.com/a.zip"),
                        lambda x: x["python"].__setitem__("url", "http://python.org/a.exe"),
                        lambda x: x.pop("python"),
                        lambda x: x["pacote"].__setitem__("tamanho", L.LIMITE_PACOTE + 1)):
            dd = json.loads(json.dumps(d))
            estraga(dd)
            with self.assertRaises(L.ErroInstalador):
                L.validar_manifesto(dd, HOSTS)

    def test_ler_manifesto_com_rede_falsa(self):
        corpo = json.dumps(manifesto_dict("1.7", b"zip")).encode()
        m = L.ler_manifesto(URL_M, HOSTS, abrir=lambda u: Resp(corpo))
        self.assertEqual(m["versao"], "1.7")

    def test_ler_manifesto_erros_viram_mensagem(self):
        def cai(u):
            raise OSError("sem rede")
        with self.assertRaises(L.ErroInstalador) as cm:
            L.ler_manifesto(URL_M, HOSTS, abrir=cai)
        self.assertIn("internet", cm.exception.dica)
        with self.assertRaises(L.ErroInstalador):
            L.ler_manifesto(URL_M, HOSTS, abrir=lambda u: Resp(b"<html>nao e json"))


# ------------------------------------------------------------------ download
class DownloadTests(Base):
    def test_baixa_e_confere(self):
        dados = b"x" * 700_000
        f = L.baixar(URL_P, self.tmp / "a.zip", sha(dados), 10**7, HOSTS, abrir=lambda u: Resp(dados))
        self.assertEqual(f.read_bytes(), dados)
        self.assertFalse((self.tmp / "a.zip.parte").exists())

    def test_hash_errado_nao_deixa_nada(self):
        with self.assertRaises(L.ErroInstalador) as cm:
            L.baixar(URL_P, self.tmp / "a.zip", sha(b"outra coisa"), 10**7, HOSTS, abrir=lambda u: Resp(b"dados"))
        self.assertIn("SHA-256", str(cm.exception))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_passou_do_limite(self):
        with self.assertRaises(L.ErroInstalador):
            L.baixar(URL_P, self.tmp / "a.zip", sha(b"y" * 1000), 500, HOSTS, abrir=lambda u: Resp(b"y" * 1000))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_cancelar_e_vazio(self):
        with self.assertRaises(L.ErroInstalador):
            L.baixar(URL_P, self.tmp / "a.zip", sha(b"z"), 10**6, HOSTS, abrir=lambda u: Resp(b"zzz"), cancelado=lambda: True)
        with self.assertRaises(L.ErroInstalador):
            L.baixar(URL_P, self.tmp / "b.zip", sha(b""), 10**6, HOSTS, abrir=lambda u: Resp(b""))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_progresso_chega_a_um(self):
        marcas = []
        d = b"p" * 600_000
        L.baixar(URL_P, self.tmp / "p.zip", sha(d), 10**7, HOSTS, progresso=marcas.append, abrir=lambda u: Resp(d))
        self.assertEqual(marcas[-1], 1.0)


# ------------------------------------------------------------------ extração
class ExtracaoTests(Base):
    def test_tira_a_pasta_raiz_unica(self):
        z = self.tmp / "a.zip"
        z.write_bytes(zip_bytes({"zenith_launcher.py": "x", "brain/a.py": "y"}, raiz="Zenith_Publico_v1.6"))
        L.extrair_seguro(z, self.tmp / "out")
        self.assertTrue((self.tmp / "out" / "zenith_launcher.py").exists())
        self.assertTrue((self.tmp / "out" / "brain" / "a.py").exists())

    def test_sem_raiz_unica_mantem(self):
        z = self.tmp / "a.zip"
        z.write_bytes(zip_bytes({"zenith_launcher.py": "x", "brain/a.py": "y"}))
        L.extrair_seguro(z, self.tmp / "out")
        self.assertTrue((self.tmp / "out" / "brain" / "a.py").exists())

    def test_recusa_caminho_perigoso(self):
        for nome in ("../fora.txt", "a/../../fora.txt", "/etc/passwd", "C:/Windows/x.dll", "..\\fora.txt"):
            z = self.tmp / "m.zip"
            z.write_bytes(zip_bytes({nome: "x", "ok.txt": "y"}))
            with self.assertRaises(L.ErroInstalador, msg=nome):
                L.extrair_seguro(z, self.tmp / "out")
            self.assertFalse((self.tmp / "fora.txt").exists())

    def test_recusa_symlink(self):
        z = self.tmp / "s.zip"
        with zipfile.ZipFile(z, "w") as zf:
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc")
        with self.assertRaises(L.ErroInstalador):
            L.extrair_seguro(z, self.tmp / "out")

    def test_limites(self):
        z = self.tmp / "g.zip"
        z.write_bytes(zip_bytes({f"a{i}.txt": "x" for i in range(5)}))
        with self.assertRaises(L.ErroInstalador):
            L.extrair_seguro(z, self.tmp / "o1", max_arquivos=3)
        with self.assertRaises(L.ErroInstalador):
            L.extrair_seguro(z, self.tmp / "o2", max_bytes=2)


# ------------------------------------------------------------------ requirements
class RequisitosTests(unittest.TestCase):
    def test_separa_essenciais_opcionais_e_tira_o_que_e_so_de_build(self):
        texto = "openai>=1.0.0\npyinstaller>=6.0.0  # build\nPillow>=10.0.0 # papel\nsympy>=1.12\n# rvc-python\n\nplyer>=2.1.0\npywin32-ctypes>=0.2.2\n"
        obrig, opc = L.ler_requisitos(texto)
        self.assertEqual(obrig, ["openai>=1.0.0", "Pillow>=10.0.0"])
        self.assertEqual(opc, ["sympy>=1.12", "plyer>=2.1.0"])

    def test_com_o_requirements_real_do_projeto(self):
        obrig, opc = L.ler_requisitos((RAIZ / "requirements.txt").read_text(encoding="utf-8"))
        nomes = " ".join(obrig).lower()
        for essencial in ("websockets", "openai", "google-genai", "chromadb", "edge-tts", "pygame-ce", "requests"):
            self.assertIn(essencial, nomes)
        self.assertNotIn("pyinstaller", nomes + " ".join(opc).lower())
        self.assertNotIn("rvc", nomes)
        self.assertGreater(len(opc), 3)


# ------------------------------------------------------------------ troca da pasta app
def monta_app(pasta, versao, usuario=False):
    pasta.mkdir(parents=True)
    (pasta / "zenith_launcher.py").write_text(f"v{versao}")
    (pasta / "brain").mkdir()
    (pasta / "brain" / "a.py").write_text(f"codigo {versao}")
    (pasta / "config").mkdir()
    (pasta / "config" / "provedores_catalogo.json").write_text(f"catalogo {versao}")
    if usuario:
        (pasta / "config" / "settings.json").write_text("do usuario")
        (pasta / "config" / "chaves.txt").write_text("SEGREDO")
        (pasta / "models").mkdir()
        (pasta / "models" / "whisper.bin").write_text("modelo grande")
        av = pasta / "body" / "zenith" / "addons" / "avatars"
        av.mkdir(parents=True)
        (av / "meu.vrm").write_text("avatar")


class TrocaTests(Base):
    def test_troca_leva_os_dados_do_usuario_e_guarda_a_anterior(self):
        raiz = self.tmp / "raiz"
        monta_app(raiz / "app", "1", usuario=True)
        monta_app(raiz / "novo", "2")
        (raiz / "novo" / "config" / "novo_padrao.json").write_text("padrao novo")
        r = L.trocar_app(raiz, raiz / "novo")
        app = raiz / "app"
        self.assertEqual((app / "brain" / "a.py").read_text(), "codigo 2")
        self.assertEqual((app / "config" / "settings.json").read_text(), "do usuario")
        self.assertEqual((app / "config" / "chaves.txt").read_text(), "SEGREDO")
        self.assertEqual((app / "models" / "whisper.bin").read_text(), "modelo grande")
        self.assertEqual((app / "body/zenith/addons/avatars/meu.vrm").read_text(), "avatar")
        self.assertEqual((app / "config" / "novo_padrao.json").read_text(), "padrao novo")      # o pacote acrescenta
        self.assertEqual((app / "config" / "provedores_catalogo.json").read_text(), "catalogo 2")   # gerenciado
        self.assertEqual((raiz / "app.anterior" / "brain" / "a.py").read_text(), "codigo 1")
        self.assertIn("config", r["movidas"])

    def test_primeira_instalacao_sem_app_antigo(self):
        raiz = self.tmp / "raiz"
        monta_app(raiz / "novo", "1")
        r = L.trocar_app(raiz, raiz / "novo")
        self.assertEqual(r["anterior"], "")
        self.assertTrue((raiz / "app" / "zenith_launcher.py").exists())

    def test_falha_no_meio_desfaz_tudo(self):
        raiz = self.tmp / "raiz"
        monta_app(raiz / "app", "1", usuario=True)
        monta_app(raiz / "novo", "2")
        real = os.replace
        chamadas = {"n": 0}

        def falha_na_ultima(a, b):
            chamadas["n"] += 1
            if str(b).endswith(os.sep + "app") and str(a).endswith("novo"):
                raise OSError("disco cheio")
            return real(a, b)
        L.os.replace = falha_na_ultima
        try:
            with self.assertRaises(OSError):
                L.trocar_app(raiz, raiz / "novo")
        finally:
            L.os.replace = real
        app = raiz / "app"
        self.assertEqual((app / "brain" / "a.py").read_text(), "codigo 1")
        self.assertEqual((app / "config" / "chaves.txt").read_text(), "SEGREDO")
        self.assertEqual((app / "models" / "whisper.bin").read_text(), "modelo grande")

    def test_reverter_volta_e_leva_os_dados_de_volta(self):
        raiz = self.tmp / "raiz"
        monta_app(raiz / "app", "1", usuario=True)
        monta_app(raiz / "novo", "2")
        L.trocar_app(raiz, raiz / "novo")
        (raiz / "app" / "config" / "settings.json").write_text("mudou na v2")
        self.assertTrue(L.reverter(raiz))
        app = raiz / "app"
        self.assertEqual((app / "brain" / "a.py").read_text(), "codigo 1")
        self.assertEqual((app / "config" / "settings.json").read_text(), "mudou na v2")
        self.assertFalse((raiz / "app.anterior").exists())
        self.assertFalse(L.reverter(raiz))


# ------------------------------------------------------------------ pequenas peças
class PecasTests(Base):
    def test_comando_do_python_e_sem_administrador(self):
        c = L.comando_instalar_python("py.exe", "D:/z/python")
        self.assertIn("/quiet", c)
        self.assertIn("InstallAllUsers=0", c)
        self.assertIn("Include_tcltk=1", c)           # o Zenith importa tkinter
        self.assertIn("PrependPath=0", c)
        self.assertIn("TargetDir=D:/z/python", c)

    def test_atalhos_escapam_aspas(self):
        s = L.script_atalhos("C:/Users/O'Neil/Zenith/ZenithLauncher.exe")
        self.assertIn("O''Neil", s)
        self.assertIn("CreateShortcut", s)

    def test_encerrar_so_o_que_esta_na_pasta(self):
        s = L.script_encerrar_pasta("C:/Zenith/app")
        self.assertIn("-like 'C:/Zenith/app\\*'", s)

    def test_trocar_executavel(self):
        a, n = self.tmp / "Launcher.exe", self.tmp / "novo.exe"
        a.write_text("velho")
        n.write_text("novo")
        self.assertTrue(L.trocar_executavel(a, n))
        self.assertEqual(a.read_text(), "novo")
        self.assertEqual((self.tmp / "Launcher.exe.antigo").read_text(), "velho")
        L.limpar_antigo(a)
        self.assertFalse((self.tmp / "Launcher.exe.antigo").exists())

    def test_instalacao_json_respeita_escolha_do_usuario(self):
        app = self.tmp / "app"
        L.gravar_instalacao_json(app, self.tmp / "dados")
        self.assertEqual(json.loads((app / "config/instalacao.json").read_text())["data_root_path"], str(self.tmp / "dados"))
        (app / "config/instalacao.json").write_text(json.dumps({"data_root_path": "D:/meus"}))
        L.gravar_instalacao_json(app, self.tmp / "dados")
        self.assertEqual(json.loads((app / "config/instalacao.json").read_text())["data_root_path"], "D:/meus")

    def test_estado_vai_e_volta(self):
        L.gravar_estado(self.tmp, {"versao": "1.7"})
        self.assertEqual(L.ler_estado(self.tmp)["versao"], "1.7")
        self.assertEqual(L.ler_estado(self.tmp / "nao_existe"), {})


# ------------------------------------------------------------------ o fluxo inteiro (tudo falso)
class UiFalsa:
    def __init__(self, resposta=True):
        self.resposta, self.mensagens, self.perguntas, self.erros = resposta, [], [], []

    def status(self, t):
        self.mensagens.append(t)

    def progresso(self, f):
        pass

    def perguntar(self, titulo, texto):
        self.perguntas.append((titulo, texto))
        return self.resposta

    def erro(self, t):
        self.erros.append(t)


class FluxoTests(Base):
    def setUp(self):
        super().setUp()
        self.raiz = self.tmp / "Zenith"
        self.comandos = []
        self.abertos = []

    def pacote(self, versao, req="openai>=1\nsympy>=1\nplyer>=1\n"):
        return zip_bytes({"zenith_launcher.py": f"v{versao}", "requirements.txt": req,
                          "config/provedores_catalogo.json": f"cat {versao}", "brain/a.py": f"c{versao}"}, raiz="Zenith")

    def rede(self, versao, pacote_bytes):
        py = b"PYINSTALADOR"
        corpo = json.dumps(manifesto_dict(versao, pacote_bytes, py)).encode()
        mapa = {URL_M: corpo, URL_P: pacote_bytes, URL_PY: py}

        def abrir(url):
            if url not in mapa:
                raise OSError("sem rede")
            return Resp(mapa[url])
        return abrir

    def exec_falso(self, falhar_opcional=None, falhar_essencial=False):
        def executar(cmd, linha=None, tempo=0, cwd=None):
            self.comandos.append(list(map(str, cmd)))
            c0 = str(cmd[0])
            if c0.endswith("python_instalador.exe"):                      # "instala" o Python
                dest = [x.split("=", 1)[1] for x in cmd if str(x).startswith("TargetDir=")][0]
                exe = L.python_exe(self.raiz)
                exe.parent.mkdir(parents=True, exist_ok=True)
                exe.write_text("python falso")
                return 0, ""
            if "-m" in cmd and "pip" in cmd:
                alvo = str(cmd[-1])
                if falhar_essencial and alvo.endswith("essenciais.txt"):
                    return 1, "ERROR: no matching distribution"
                if falhar_opcional and falhar_opcional in alvo:
                    return 1, "ERROR"
                if linha:
                    linha("Collecting openai")
                return 0, ""
            return 0, "ok"
        return executar

    def args(self, **kw):
        base = dict(pasta=str(self.raiz), manifesto="", atualizar=False, reverter=False, sem_abrir=False,
                    silencioso=True, sim=False, esperar_pid=0)
        base.update(kw)
        return SimpleNamespace(**base)

    def rodar(self, ui, abrir, **kw):
        os.environ["ZENITH_MANIFESTO"] = URL_M
        self.addCleanup(os.environ.pop, "ZENITH_MANIFESTO", None)
        orig = L.carregar_config
        L.carregar_config = lambda m="": {"manifesto": URL_M, "hosts": HOSTS, "permitir_local": False}
        try:
            return L.executar_launcher(self.args(**kw), ui, abrir=abrir,
                                       executar=kw.pop("executar", None) or self.exec_falso(),
                                       popen=lambda cmd, **k: self.abertos.append((cmd, k)) or SimpleNamespace())
        finally:
            L.carregar_config = orig

    def test_primeira_instalacao_completa(self):
        ui = UiFalsa(True)
        cod = self.rodar(ui, self.rede("1.7", self.pacote("1.7")))
        self.assertEqual(cod, 0, ui.erros)
        self.assertTrue(ui.perguntas and "Instalar" in ui.perguntas[0][0])
        self.assertEqual(L.ler_estado(self.raiz)["versao"], "1.7")
        self.assertEqual((self.raiz / "app" / "brain" / "a.py").read_text(), "c1.7")
        self.assertTrue(L.python_exe(self.raiz).exists())
        self.assertTrue(any("pip" in c for cmd in self.comandos for c in cmd))
        self.assertTrue(self.abertos)
        env = self.abertos[0][1]["env"]
        self.assertEqual(env["ZENITH_RAIZ"], str(self.raiz))
        self.assertEqual(env["ZENITH_ATUALIZAR_URL"], URL_M)
        self.assertFalse((self.raiz / "tmp").exists())                       # limpou os temporários
        dados = json.loads((self.raiz / "app/config/instalacao.json").read_text())
        self.assertEqual(dados["data_root_path"], str(self.raiz / "dados"))

    def test_nao_aceitar_nao_baixa_nada(self):
        ui = UiFalsa(False)
        cod = self.rodar(ui, self.rede("1.7", self.pacote("1.7")))
        self.assertEqual(cod, 1)
        self.assertFalse((self.raiz / "app").exists())
        self.assertEqual(self.comandos, [])
        self.assertEqual(self.abertos, [])

    def test_sem_internet_na_primeira_vez_explica(self):
        ui = UiFalsa(True)

        def cai(u):
            raise OSError("sem rede")
        self.assertEqual(self.rodar(ui, cai), 2)
        self.assertTrue(ui.erros)

    def test_sem_internet_depois_abre_a_versao_que_ja_tem(self):
        self.rodar(UiFalsa(True), self.rede("1.7", self.pacote("1.7")), sem_abrir=True)
        ui = UiFalsa(True)

        def cai(u):
            raise OSError("sem rede")
        self.abertos.clear()
        self.assertEqual(self.rodar(ui, cai), 0)
        self.assertEqual(len(self.abertos), 1)
        self.assertEqual(ui.perguntas, [])

    def test_atualizacao_pergunta_e_preserva_dados(self):
        self.rodar(UiFalsa(True), self.rede("1.7", self.pacote("1.7")), sem_abrir=True)
        (self.raiz / "app/config/chaves.txt").write_text("SEGREDO")
        ui = UiFalsa(True)
        self.comandos.clear()
        cod = self.rodar(ui, self.rede("1.8", self.pacote("1.8")), sem_abrir=True)
        self.assertEqual(cod, 0, ui.erros)
        self.assertIn("Atualização", ui.perguntas[0][0])
        self.assertIn("mudou x", ui.perguntas[0][1])
        self.assertEqual(L.ler_estado(self.raiz)["versao"], "1.8")
        self.assertEqual((self.raiz / "app/config/chaves.txt").read_text(), "SEGREDO")
        self.assertEqual((self.raiz / "app.anterior/brain/a.py").read_text(), "c1.7")
        # requirements iguais e Python igual: não instalou nada de novo
        self.assertFalse(any("pip" in c for cmd in self.comandos for c in cmd))
        self.assertFalse(any(str(cmd[0]).endswith("python_instalador.exe") for cmd in self.comandos))

    def test_recusar_atualizacao_mantem_a_versao(self):
        self.rodar(UiFalsa(True), self.rede("1.7", self.pacote("1.7")), sem_abrir=True)
        ui = UiFalsa(False)
        self.rodar(ui, self.rede("1.8", self.pacote("1.8")), sem_abrir=True)
        self.assertEqual(L.ler_estado(self.raiz)["versao"], "1.7")

    def test_requirements_novos_reinstalam_as_bibliotecas(self):
        self.rodar(UiFalsa(True), self.rede("1.7", self.pacote("1.7")), sem_abrir=True)
        self.comandos.clear()
        self.rodar(UiFalsa(True), self.rede("1.8", self.pacote("1.8", req="openai>=1\nrequests>=2\n")), sem_abrir=True)
        self.assertTrue(any("pip" in c for cmd in self.comandos for c in cmd))

    def test_hash_trocado_no_caminho_nao_instala(self):
        bom = self.pacote("1.7")
        mapa = {URL_M: json.dumps(manifesto_dict("1.7", bom)).encode(), URL_P: bom + b"adulterado", URL_PY: b"PYINSTALADOR"}
        ui = UiFalsa(True)
        cod = self.rodar(ui, lambda u: Resp(mapa[u]))
        self.assertEqual(cod, 3)
        self.assertIn("SHA-256", ui.erros[0])
        self.assertFalse((self.raiz / "app").exists())

    def test_pacote_que_nao_e_o_zenith_e_recusado(self):
        ruim = zip_bytes({"leiame.txt": "oi"})
        ui = UiFalsa(True)
        self.assertEqual(self.rodar(ui, self.rede("1.7", ruim)), 3)
        self.assertFalse((self.raiz / "app").exists())

    def test_biblioteca_opcional_que_falha_nao_derruba(self):
        ui = UiFalsa(True)
        cod = self.rodar(ui, self.rede("1.7", self.pacote("1.7")), executar=self.exec_falso(falhar_opcional="sympy"))
        self.assertEqual(cod, 0, ui.erros)

    def test_biblioteca_essencial_que_falha_para_com_explicacao(self):
        ui = UiFalsa(True)
        cod = self.rodar(ui, self.rede("1.7", self.pacote("1.7")), executar=self.exec_falso(falhar_essencial=True))
        self.assertEqual(cod, 3)
        self.assertIn("essenciais", ui.erros[0])

    def test_reverter(self):
        self.rodar(UiFalsa(True), self.rede("1.7", self.pacote("1.7")), sem_abrir=True)
        self.rodar(UiFalsa(True), self.rede("1.8", self.pacote("1.8")), sem_abrir=True)
        ui = UiFalsa(True)
        self.assertEqual(self.rodar(ui, lambda u: Resp(b""), reverter=True), 0)
        self.assertEqual((self.raiz / "app/brain/a.py").read_text(), "c1.7")


if __name__ == "__main__":
    unittest.main()
