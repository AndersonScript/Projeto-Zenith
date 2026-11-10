"""
Testes do v18: brain/zenith_vrm_import.py + brain/zenith_body_control.py.

NÃO existe Godot neste ambiente de desenvolvimento. Por isso:
  * o "Godot" aqui é um script falso (FAKE_GODOT) que imita só os ARGUMENTOS
    de linha de comando (--version, --import, --export-pack) e cria os mesmos
    arquivos que o de verdade cria (.import, cena em .godot/imported, .pck);
  * estes testes provam a NOSSA lógica (autodetecção, cópia sem duplicar,
    repetição, limpeza em caso de falha, verificação de que o avatar entrou
    no .pck, troca com backup, reinício do Corpo) — NÃO provam que o Godot de
    verdade se comporta assim. Isso só dá pra confirmar rodando na máquina do
    Anderson (veja o passo a passo no HANDOFF).

Rodar: python -m unittest tests.test_vrm_import -v
"""
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brain import zenith_body_control as bc
from brain import zenith_vrm_import as vi

# Imita o editor do Godot. FAKE_GODOT_MODO muda o comportamento:
#   ok (padrão) | falha_1a (1ª importação não gera nada, a 2ª sim) | nunca_importa
#   sem_avatar_no_pck | pck_pequeno | versao_antiga | nao_e_godot
FAKE_GODOT = r'''#!{py}
import os, sys, hashlib
modo = os.environ.get("FAKE_GODOT_MODO", "ok")
args = sys.argv[1:]
if "--version" in args:
    if modo == "nao_e_godot":
        print("isso nao e o godot"); sys.exit(0)
    print("4.3.0.stable.official.fake" if modo == "versao_antiga" else "4.7.1.stable.official.fake")
    sys.exit(0)
proj = args[args.index("--path") + 1]
av = os.path.join(proj, "addons", "avatars")
imp = os.path.join(proj, ".godot", "imported")
if "--import" in args:
    contador = os.path.join(proj, ".fake_contador")
    n = int(open(contador).read()) + 1 if os.path.exists(contador) else 1
    open(contador, "w").write(str(n))
    if modo == "nunca_importa" or (modo == "falha_1a" and n == 1):
        sys.exit(0)
    os.makedirs(imp, exist_ok=True)
    for f in os.listdir(av):
        if f.lower().endswith(".vrm") and not os.path.exists(os.path.join(av, f + ".import")):
            h = hashlib.md5(f.encode()).hexdigest()
            rel = "res://.godot/imported/%s-%s.scn" % (f, h)
            open(os.path.join(av, f + ".import"), "w").write('[remap]\n\nimporter="scene"\npath="%s"\n' % rel)
            open(os.path.join(proj, rel[6:]), "wb").write(b"S" * 5000)
    sys.exit(0)
if "--export-pack" in args:
    saida = args[args.index("--export-pack") + 2]
    tam = 2000 if modo == "pck_pequeno" else 1_500_000
    corpo = bytearray(b"P" * tam)
    if modo != "sem_avatar_no_pck" and os.path.isdir(imp):
        nomes = "".join(".godot/imported/" + f + "\n" for f in os.listdir(imp)).encode()
        corpo[100:100 + len(nomes)] = nomes
    open(saida, "wb").write(bytes(corpo))
    sys.exit(0)
sys.exit(2)
'''


# v27 — estes testes usam um "Godot falso" (script executável com chmod), que só existe em Linux/macOS. No Windows o
# Zenith procura o Godot REAL do seu PC (C:\\Godot...), então os testes davam falha por motivo nenhum de código. O que
# vale no Windows é importar um avatar de verdade no Zenith.
_SO_POSIX = unittest.skipIf(os.name == "nt", "usa um Godot falso (script executável): só roda em Linux/macOS")


class Cenario:
    """BASE falsa: body/zenith (projeto) + export/Zenith.exe+.pck + um Godot falso + um .vrm."""

    def __init__(self, tmp: Path, modo="ok", com_godot=True):
        self.tmp = tmp
        self.base = tmp / "Zenith"
        self.project = self.base / "body" / "zenith"
        (self.project / "addons" / "avatars").mkdir(parents=True)
        (self.project / "project.godot").write_text(
            '[application]\nconfig/features=PackedStringArray("4.7", "GL Compatibility")\n')
        (self.project / "export_presets.cfg").write_text(
            '[preset.0]\n\nname="Windows Desktop"\nplatform="Windows Desktop"\n'
            'encrypt_directory=false\n\n[preset.0.options]\n\nbinary_format/embed_pck=false\n')
        self.export = self.project / "export"
        self.export.mkdir()
        (self.export / "Zenith.exe").write_bytes(b"exe")
        self.pck = self.export / "Zenith.pck"
        self.pck.write_bytes(b"pck antigo" * 500)
        self.godot = None
        if com_godot:
            d = self.base / "tools" / "godot"
            d.mkdir(parents=True)
            self.godot = d / "Godot_v4.7.1-stable_fake"
            self.godot.write_text(FAKE_GODOT.format(py=sys.executable))
            self.godot.chmod(self.godot.stat().st_mode | stat.S_IEXEC)
        self.origem = tmp / "Externo" / "NovoAvatar.vrm"
        self.origem.parent.mkdir()
        self.origem.write_bytes(b"vrm de mentira " * 100)
        os.environ["FAKE_GODOT_MODO"] = modo

    def env(self, **over):
        e = vi.localizar_ambiente(self.base)
        e.update(over)
        return e


def com_cenario(modo="ok", com_godot=True):
    def deco(fn):
        def inner(self):
            with tempfile.TemporaryDirectory() as t:
                c = Cenario(Path(t), modo, com_godot)
                try:
                    fn(self, c)
                finally:
                    os.environ.pop("FAKE_GODOT_MODO", None)
        inner.__name__ = fn.__name__
        return inner
    return deco


# ----------------------------------------------------------------------
@_SO_POSIX
class AutodeteccaoTests(unittest.TestCase):
    @com_cenario()
    def test_acha_tudo_sozinho(self, c):
        e = c.env()
        self.assertEqual(e["faltando"], [])
        self.assertEqual(Path(e["godot_bin"]), c.godot)
        self.assertEqual(Path(e["project_dir"]), c.project)
        self.assertEqual(Path(e["pck_destino"]), c.pck)
        self.assertEqual(e["export_preset"], "Windows Desktop")

    @com_cenario(com_godot=False)
    def test_sem_godot_explica_onde_colocar(self, c):
        with mock.patch.object(vi, "_pastas_para_procurar_godot", lambda b: [b / "tools" / "godot"]), \
             mock.patch("shutil.which", return_value=None):
            e = vi.localizar_ambiente(c.base)
        self.assertEqual(e["godot_bin"], "")
        self.assertTrue(any("editor do Godot" in f for f in e["faltando"]))
        texto = vi.explicar_faltando(e["faltando"], c.base)
        self.assertIn("tools", texto)
        self.assertIn("Editor do Godot", texto)

    @com_cenario()
    def test_sem_corpo_exportado_avisa(self, c):
        (c.export / "Zenith.exe").unlink()
        e = vi.localizar_ambiente(c.base)
        self.assertTrue(any("Corpo exportado" in f for f in e["faltando"]))

    @com_cenario()
    def test_override_das_configuracoes_vence_se_valido(self, c):
        outro = c.base / "Godot_outro"
        outro.write_text(FAKE_GODOT.format(py=sys.executable))
        outro.chmod(outro.stat().st_mode | stat.S_IEXEC)
        e = vi.localizar_ambiente(c.base, lambda k, d="": str(outro) if k == "vrm_auto_import_godot_bin" else d)
        self.assertEqual(Path(e["godot_bin"]), outro)

    @com_cenario()
    def test_override_invalido_cai_pra_busca_automatica(self, c):
        e = vi.localizar_ambiente(c.base, lambda k, d="": "C:/nao/existe/Godot.exe" if k == "vrm_auto_import_godot_bin" else d)
        self.assertEqual(Path(e["godot_bin"]), c.godot)
        self.assertIn("não serve", e["log"])

    @com_cenario()
    def test_override_que_nao_parece_godot_e_ignorado(self, c):
        estranho = c.base / "calc.exe"
        estranho.write_text("x")
        estranho.chmod(estranho.stat().st_mode | stat.S_IEXEC)
        e = vi.localizar_ambiente(c.base, lambda k, d="": str(estranho) if k == "vrm_auto_import_godot_bin" else d)
        self.assertEqual(Path(e["godot_bin"]), c.godot)

    def test_prefere_versao_mais_nova_e_console(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t) / "Z"
            d = base / "tools" / "godot"
            d.mkdir(parents=True)
            nomes = ["Godot_v4.6.2-stable_win64.exe", "Godot_v4.7.1-stable_win64.exe",
                     "Godot_v4.7.1-stable_win64_console.exe", "Godot_v4.7-export_templates.exe"]
            for n in nomes:
                (d / n).write_text("x")
            with mock.patch.object(vi, "_pastas_para_procurar_godot", lambda b: [b / "tools" / "godot"]), \
                 mock.patch("shutil.which", return_value=None), \
                 mock.patch.object(vi, "_parece_godot", lambda p: p.suffix == ".exe" and p.name.lower().startswith("godot")
                                   and "template" not in p.name.lower() and "export" not in p.name.lower()):
                achado = vi.localizar_godot(base, versao_minima=(4, 7))
            self.assertEqual(achado.name, "Godot_v4.7.1-stable_win64_console.exe")

    def test_le_presets_e_embed_pck(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "export_presets.cfg").write_text(
                '[preset.0]\nname="Linux"\nplatform="Linux"\n[preset.0.options]\nbinary_format/embed_pck=false\n'
                '[preset.1]\nname="Meu Win"\nplatform="Windows Desktop"\nencrypt_directory=true\n'
                '[preset.1.options]\nbinary_format/embed_pck=true\n')
            ps = vi._ler_presets(Path(t))
            self.assertEqual([p["nome"] for p in ps], ["Linux", "Meu Win"])
            self.assertFalse(ps[0]["embute_pck"])
            self.assertTrue(ps[1]["embute_pck"])
            self.assertTrue(ps[1]["encripta_diretorio"])

    def test_versao_do_projeto(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "project.godot").write_text('config/features=PackedStringArray("4.7", "GL Compatibility")\n')
            self.assertEqual(vi.versao_do_projeto(Path(t)), (4, 7))


# ----------------------------------------------------------------------
@_SO_POSIX
class ValidacaoTests(unittest.TestCase):
    def test_sem_ambiente_nao_tenta_nada(self):
        with mock.patch("subprocess.run") as run:
            r = vi.importar_vrm("qualquer.vrm", {})
        run.assert_not_called()
        self.assertFalse(r["ok"])

    @com_cenario()
    def test_origem_nao_existe(self, c):
        r = vi.importar_vrm(str(c.tmp / "fantasma.vrm"), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("não achei o arquivo", r["mensagem"])

    @com_cenario()
    def test_extensao_errada(self, c):
        png = c.tmp / "x.png"
        png.write_bytes(b"x")
        r = vi.importar_vrm(str(png), c.env())
        self.assertFalse(r["ok"])
        self.assertIn(".vrm", r["mensagem"])

    @com_cenario()
    def test_nome_suspeito_e_recusado_sem_rodar_nada(self, c):
        suspeito = c.tmp / "Externo" / "kid.vrm"
        suspeito.write_bytes(b"x")
        with mock.patch("subprocess.run") as run:
            r = vi.importar_vrm(str(suspeito), c.env())
        run.assert_not_called()
        self.assertFalse(r["ok"])
        self.assertIn("recusado", r["mensagem"])
        self.assertFalse((c.project / "addons" / "avatars" / "kid.vrm").exists())

    @com_cenario()
    def test_preset_que_embute_pck_e_recusado(self, c):
        (c.project / "export_presets.cfg").write_text(
            '[preset.0]\nname="Windows Desktop"\nplatform="Windows Desktop"\n'
            '[preset.0.options]\nbinary_format/embed_pck=true\n')
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("embute", r["mensagem"])

    @com_cenario(modo="versao_antiga")
    def test_editor_mais_antigo_que_o_projeto_e_recusado(self, c):
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("mais antigo", r["mensagem"])

    @com_cenario(modo="nao_e_godot")
    def test_executavel_que_nao_e_godot_e_recusado(self, c):
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("--version", r["mensagem"])

    def test_nome_seguro(self):
        n = vi._nome_seguro('Minha Modelo #1 (final):v2?.vrm')
        for ruim in '#():?':
            self.assertNotIn(ruim, n)
        self.assertTrue(n.endswith(".vrm"))
        self.assertEqual(vi._nome_seguro("???.vrm"), "avatar.vrm")
        self.assertEqual(vi._nome_seguro("Zenith.vrm"), "Zenith.vrm")


# ----------------------------------------------------------------------
@_SO_POSIX
class FluxoCompletoTests(unittest.TestCase):
    @com_cenario()
    def test_sucesso_ponta_a_ponta(self, c):
        etapas, gravado = [], []
        r = vi.importar_vrm(str(c.origem), c.env(), progresso=etapas.append,
                            antes_de_trocar=gravado.append)
        self.assertTrue(r["ok"], r["log"])
        self.assertEqual(r["nome"], "NovoAvatar")
        self.assertEqual(r["avatar_path"], "res://addons/avatars/NovoAvatar.vrm")
        self.assertFalse(r["reiniciou"])                      # sem supervisor: pede pra reabrir
        self.assertIn("FECHE E ABRA", r["mensagem"])
        av = c.project / "addons" / "avatars"
        self.assertTrue((av / "NovoAvatar.vrm").is_file())
        self.assertTrue((av / "NovoAvatar.vrm.import").is_file())
        self.assertEqual(c.pck.stat().st_size, 1_500_000)     # .pck trocado pelo novo
        self.assertTrue((c.export / "Zenith.pck.bak").is_file())   # antigo guardado
        self.assertEqual((c.export / "Zenith.pck.bak").read_bytes(), b"pck antigo" * 500)
        self.assertFalse((c.export / "Zenith_novo.pck").exists())  # sem sobra
        self.assertEqual(gravado, [{"nome": "NovoAvatar", "avatar_path": "res://addons/avatars/NovoAvatar.vrm"}])
        self.assertGreaterEqual(len(etapas), 4)
        self.assertIn("Copiando", etapas[0])

    @com_cenario()
    def test_mesmo_arquivo_duas_vezes_nao_duplica(self, c):
        vi.importar_vrm(str(c.origem), c.env())
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertTrue(r["ok"], r["log"])
        self.assertEqual(r["nome"], "NovoAvatar")
        nomes = sorted(p.name for p in (c.project / "addons" / "avatars").glob("*.vrm"))
        self.assertEqual(nomes, ["NovoAvatar.vrm"])
        self.assertIn("já está no projeto", r["log"])

    @com_cenario()
    def test_mesmo_nome_conteudo_diferente_vira_2(self, c):
        vi.importar_vrm(str(c.origem), c.env())
        c.origem.write_bytes(b"outro modelo " * 100)
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertTrue(r["ok"], r["log"])
        self.assertEqual(r["nome"], "NovoAvatar_2")
        self.assertTrue((c.project / "addons" / "avatars" / "NovoAvatar.vrm").is_file())   # o antigo segue lá

    @com_cenario()
    def test_nao_mexe_no_arquivo_de_origem(self, c):
        antes = c.origem.read_bytes()
        vi.importar_vrm(str(c.origem), c.env())
        self.assertTrue(c.origem.is_file())
        self.assertEqual(c.origem.read_bytes(), antes)

    @com_cenario(modo="falha_1a")
    def test_segunda_passada_quando_a_primeira_nao_gera_nada(self, c):
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertTrue(r["ok"], r["log"])
        self.assertEqual(r["log"].count("--import"), 2)

    @com_cenario(modo="nunca_importa")
    def test_importacao_que_nunca_funciona_limpa_tudo(self, c):
        pck_antes = c.pck.read_bytes()
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("não importou", r["mensagem"])
        self.assertEqual(list((c.project / "addons" / "avatars").glob("*")), [])   # nada ficou pra trás
        self.assertEqual(c.pck.read_bytes(), pck_antes)                            # .pck intacto

    @com_cenario(modo="sem_avatar_no_pck")
    def test_pck_sem_o_avatar_nao_e_trocado(self, c):
        pck_antes = c.pck.read_bytes()
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("NÃO entrou", r["mensagem"])
        self.assertEqual(c.pck.read_bytes(), pck_antes)
        self.assertFalse((c.export / "Zenith_novo.pck").exists())

    @com_cenario(modo="pck_pequeno")
    def test_pck_pequeno_demais_nao_e_trocado(self, c):
        pck_antes = c.pck.read_bytes()
        r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("incompleto", r["mensagem"])
        self.assertEqual(c.pck.read_bytes(), pck_antes)

    @com_cenario()
    def test_timeout_na_importacao_limpa_o_que_copiou(self, c):
        real = subprocess.run

        def _run(cmd, **kw):
            if "--import" in cmd:
                raise subprocess.TimeoutExpired(cmd, 1)
            return real(cmd, **kw)
        with mock.patch("subprocess.run", _run):
            r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertEqual(list((c.project / "addons" / "avatars").glob("*")), [])

    @com_cenario()
    def test_timeout_na_exportacao_preserva_pck_antigo(self, c):
        real = subprocess.run

        def _run(cmd, **kw):
            if "--export-pack" in cmd:
                raise subprocess.TimeoutExpired(cmd, 1)
            return real(cmd, **kw)
        pck_antes = c.pck.read_bytes()
        with mock.patch("subprocess.run", _run):
            r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertEqual(c.pck.read_bytes(), pck_antes)

    @com_cenario()
    def test_arquivo_preso_por_antivirus_tenta_de_novo_e_consegue(self, c):
        real = os.replace
        chamadas = {"n": 0}

        def _replace(a, b):
            chamadas["n"] += 1
            if chamadas["n"] <= 2:
                raise PermissionError("[WinError 32] arquivo em uso por outro processo")
            return real(a, b)
        with mock.patch.object(vi, "ESPERA_ARQUIVO", 0), mock.patch("os.replace", _replace):
            r = vi.importar_vrm(str(c.origem), c.env())
        self.assertTrue(r["ok"], r["log"])
        self.assertEqual(chamadas["n"], 3)
        self.assertIn("tentando de novo", r["log"])

    @com_cenario()
    def test_arquivo_sempre_preso_explica_antivirus_e_nao_perde_nada(self, c):
        def _replace(a, b):
            raise PermissionError("[WinError 5] acesso negado")
        pck_antes = c.pck.read_bytes()
        with mock.patch.object(vi, "ESPERA_ARQUIVO", 0), mock.patch.object(vi, "TENTATIVAS_ARQUIVO", 2), \
             mock.patch("os.replace", _replace):
            r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("antivírus", r["mensagem"])
        self.assertEqual(c.pck.read_bytes(), pck_antes)
        self.assertFalse((c.export / "Zenith_novo.pck").exists())

    @com_cenario()
    def test_uma_importacao_de_cada_vez(self, c):
        self.assertTrue(vi._em_andamento.acquire(blocking=False))
        try:
            r = vi.importar_vrm(str(c.origem), c.env())
        finally:
            vi._em_andamento.release()
        self.assertFalse(r["ok"])
        self.assertIn("em andamento", r["mensagem"])

    @com_cenario()
    def test_nunca_levanta_excecao(self, c):
        with mock.patch.object(vi, "_rodar", side_effect=RuntimeError("explodiu")):
            r = vi.importar_vrm(str(c.origem), c.env())
        self.assertFalse(r["ok"])
        self.assertIn("erro inesperado", r["mensagem"])


# ----------------------------------------------------------------------
@_SO_POSIX
class SupervisorDoCorpoTests(unittest.TestCase):
    """Usa processos de verdade (python dormindo) no lugar do Zenith.exe."""

    def setUp(self):
        bc._resetar()
        self.lancados = []

    def tearDown(self):
        for p in self.lancados:
            if p.poll() is None:
                p.kill()
        bc._resetar()

    def _lancar(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.lancados.append(p)
        return p, "Zenith.exe"

    def _subir_supervisor(self):
        t = threading.Thread(target=bc.supervisionar, args=(self._lancar, lambda m: None), daemon=True)
        t.start()
        for _ in range(100):
            if bc.corpo_vivo():
                break
            time.sleep(0.05)
        return t

    def test_sem_supervisor_so_executa_a_troca(self):
        r = bc.trocar_e_reiniciar(lambda: "feito")
        self.assertEqual(r, {"reiniciou": False, "resultado": "feito", "erro": ""})

    def test_troca_para_o_corpo_executa_e_sobe_de_novo(self):
        t = self._subir_supervisor()
        self.assertEqual(len(self.lancados), 1)
        primeiro = self.lancados[0]

        durante = {}

        def troca():
            durante["corpo_parado"] = primeiro.poll() is not None
            return True
        r = bc.trocar_e_reiniciar(troca)
        self.assertTrue(r["reiniciou"])
        self.assertTrue(durante["corpo_parado"])          # a troca rodou COM o Corpo parado
        for _ in range(100):
            if len(self.lancados) == 2 and bc.corpo_vivo():
                break
            time.sleep(0.05)
        self.assertEqual(len(self.lancados), 2)           # e um Corpo novo subiu
        self.assertTrue(t.is_alive())                     # o launcher continua de pé

        self.lancados[1].kill()                           # usuário fecha o Corpo → tudo encerra
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(len(self.lancados), 2)

    def test_troca_que_falha_ainda_relanca_o_corpo(self):
        t = self._subir_supervisor()

        def _quebra():
            raise OSError("disco cheio")
        r = bc.trocar_e_reiniciar(_quebra)
        self.assertIn("disco cheio", r["erro"])
        for _ in range(100):
            if len(self.lancados) == 2:
                break
            time.sleep(0.05)
        self.assertEqual(len(self.lancados), 2)
        self.lancados[1].kill()
        t.join(5)

    def test_fechar_o_corpo_na_mao_encerra_o_supervisor(self):
        t = self._subir_supervisor()
        self.lancados[0].kill()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(len(self.lancados), 1)           # NÃO relançou: foi o usuário que fechou

    def test_pipeline_completo_com_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = Cenario(Path(tmp))
            try:
                t = self._subir_supervisor()
                r = vi.importar_vrm(str(c.origem), c.env(), trocar=bc.trocar_e_reiniciar)
                self.assertTrue(r["ok"], r["log"])
                self.assertTrue(r["reiniciou"])
                self.assertIn("reiniciou sozinho", r["mensagem"])
                self.assertEqual(c.pck.stat().st_size, 1_500_000)
                for _ in range(100):
                    if len(self.lancados) == 2:
                        break
                    time.sleep(0.05)
                self.assertEqual(len(self.lancados), 2)
                self.lancados[-1].kill()
                t.join(5)
            finally:
                os.environ.pop("FAKE_GODOT_MODO", None)


class ComandoDiagnosticoTests(unittest.TestCase):
    def test_avatar_diag_responde_sem_quebrar(self):
        from brain import zenith_commands as cmd
        r = cmd.tratar("/avatar_diag", {"settings": None})
        self.assertIsNotNone(r)
        self.assertIn("Importação automática de avatar", r["resposta"])

    def test_ajuda_lista_o_comando(self):
        from brain import zenith_commands as cmd
        self.assertIn("/avatar_diag", cmd.tratar("/ajuda", {})["resposta"])


if __name__ == "__main__":
    unittest.main()
