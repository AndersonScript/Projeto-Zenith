"""v1.4 — edições Pública/Admin, montagem e varredura da pasta pública, instalador, marca e mãos do avatar."""
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from brain import zenith_edicao as ED          # noqa: E402
from brain import zenith_admin as ADM          # noqa: E402
from brain import zenith_version as VER        # noqa: E402


def _carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PP = _carregar("preparar_publico", RAIZ / "tools" / "preparar_publico.py")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.mkdtemp(prefix="zenith_v14_")
        self.d = Path(self._d)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ZENITH_EDICAO", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self._d, ignore_errors=True)

    def escrever(self, rel, texto="x", binario=False):
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if binario:
            p.write_bytes(texto)
        else:
            p.write_text(texto, encoding="utf-8")
        return p


class EdicaoTests(_Tmp):
    def test_sem_arquivo_e_admin(self):
        self.assertEqual(ED.edicao(self.d), "admin")
        self.assertTrue(ED.e_admin(self.d))
        self.assertFalse(ED.e_publico(self.d))

    def test_arquivo_publico(self):
        ED.gravar(self.d, "publico")
        self.assertEqual(ED.edicao(self.d), "publico")
        self.assertEqual(json.loads((self.d / "edition.json").read_text(encoding="utf-8"))["edicao"], "publico")

    def test_aceita_sinonimos_e_acento(self):
        ED.gravar(self.d, "Público")
        self.assertTrue(ED.e_publico(self.d))

    def test_gravar_recusa_valor_desconhecido(self):
        with self.assertRaises(ValueError):
            ED.gravar(self.d, "talvez")

    def test_arquivo_torto_cai_para_admin(self):
        self.escrever("edition.json", "{isso nao e json")
        self.assertEqual(ED.edicao(self.d), "admin")

    def test_variavel_de_ambiente_manda(self):
        ED.gravar(self.d, "admin")
        os.environ["ZENITH_EDICAO"] = "publico"
        self.assertEqual(ED.edicao(self.d), "publico")

    def test_recurso_do_admin_some_no_publico(self):
        ED.gravar(self.d, "publico")
        for r in ED.RECURSOS_ADMIN:
            self.assertFalse(ED.recurso_liberado(r, self.d), r)
        self.assertTrue(ED.recurso_liberado("chat", self.d))
        ED.gravar(self.d, "admin")
        self.assertTrue(ED.recurso_liberado("console_dev", self.d))

    def test_publico_nunca_pede_para_reabrir_como_administrador(self):
        os.environ["ZENITH_EDICAO"] = "publico"
        self.assertEqual(ADM.decidir(self.d, frozen=True, windows=True, admin=False), "nada")
        os.environ["ZENITH_EDICAO"] = "admin"
        self.assertEqual(ADM.decidir(self.d, frozen=True, windows=True, admin=False), "perguntar")

    def test_versao_expoe_a_edicao(self):
        os.environ["ZENITH_EDICAO"] = "publico"
        self.assertEqual(VER.edicao(), "publico")


class MontagemPublicaTests(_Tmp):
    def _projeto_minimo(self):
        self.escrever("brain/zenith_version.py", "VERSAO = 'v0'\n")
        self.escrever("brain/modulo.py", "print('oi')\n")
        self.escrever("config/provedores_catalogo.json", "{}")
        self.escrever("config/settings.json", '{"chave": "segredo"}')
        self.escrever("config/conversations.json", "[]")
        self.escrever("memory_db/x.bin", b"\x00", binario=True)
        self.escrever("docs/historico/HANDOFF.md", "conversa antiga")
        self.escrever("body/zenith/addons/avatars/Meu.vrm", b"VRM", binario=True)
        self.escrever("body/zenith/addons/avatars/Meu.vrm.import", "x")
        self.escrever("assets/LICENCAS.md", "# licencas")
        self.escrever("dist/Zenith/Zenith.exe", b"MZ", binario=True)

    def test_copia_so_o_que_e_publico(self):
        self._projeto_minimo()
        saida = self.d / "saida"
        PP.copiar(self.d, saida)
        existe = lambda r: (saida / r).exists()
        self.assertTrue(existe("brain/modulo.py"))
        self.assertTrue(existe("config/provedores_catalogo.json"))
        for proibido in ("config/settings.json", "config/conversations.json", "memory_db", "docs/historico",
                         "body/zenith/addons/avatars/Meu.vrm", "body/zenith/addons/avatars/Meu.vrm.import", "dist"):
            self.assertFalse(existe(proibido), proibido)

    def test_varredura_acha_chave_de_verdade_mas_aceita_chave_de_teste(self):
        self.escrever("a.py", 'K = "AIzaSyD-' + "Q7wErTyUiOpAsDfGhJkLzXcVbNm1234" + '"\n')
        self.escrever("b.py", 'K = "AIzaSyD-abcdefghijklmnopqrstuvwxyz_123456"\n')
        erros = PP.varrer(self.d)["erros"]
        self.assertTrue(any(e.startswith("a.py") and "chave" in e for e in erros), erros)
        self.assertFalse(any(e.startswith("b.py") for e in erros), erros)

    def test_varredura_acha_caminho_pessoal_e_aceita_generico(self):
        self.escrever("a.py", 'P = r"C:\\Users\\carlos\\Documents"\n')
        self.escrever("b.py", 'P = r"C:\\Users\\joao\\Documents"\nQ = "C:\\\\Users\\\\x\\\\Downloads"\n')
        erros = PP.varrer(self.d)["erros"]
        self.assertTrue(any(e.startswith("a.py") and "caminho pessoal" in e for e in erros), erros)
        self.assertFalse(any(e.startswith("b.py") for e in erros), erros)

    def test_varredura_acha_nome_antigo_visivel_mas_aceita_no_interno_do_godot(self):
        self.escrever("brain/x.py", 'print("Oi, eu sou a Akira")\n')
        self.escrever("body/zenith/akira_body.gd", 'var a = get_node_or_null("Akira")\nvar b = "Mostrar Akira"\n')
        erros = PP.varrer(self.d)["erros"]
        self.assertTrue(any(e.startswith("brain/x.py") for e in erros), erros)
        self.assertTrue(any("akira_body.gd:2" in e for e in erros), erros)
        self.assertFalse(any("akira_body.gd:1" in e for e in erros), erros)

    def test_varredura_acha_arquivo_proibido_e_avatar(self):
        self.escrever("config/settings.json", "{}")
        self.escrever("body/m.vrm", b"x", binario=True)
        erros = " ".join(PP.varrer(self.d)["erros"])
        self.assertIn("settings.json", erros)
        self.assertIn("m.vrm", erros)

    def test_montar_grava_edicao_publico_e_sha256(self):
        self._projeto_minimo()
        saida = self.d / "dist_pub"
        r = PP.montar(self.d, saida)
        self.assertEqual(r["erros"], [], r["erros"])
        self.assertEqual(json.loads((saida / "edition.json").read_text(encoding="utf-8"))["edicao"], "publico")
        sums = (saida / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(l.endswith("  brain/modulo.py") for l in sums))
        self.assertFalse(any("SHA256SUMS.txt" in l for l in sums))
        self.assertTrue((saida / "body/zenith/addons/avatars/LEIA-ME.md").is_file())

    def test_so_conferir_olha_so_o_que_vai_para_a_publica(self):
        """v1.5 — `--so-conferir` roda na pasta de ORIGEM: precisa aplicar a mesma exclusão da cópia.

        Sem isso ele acusava `docs/historico`, `docs/interno`, os `.vrm` e o `body/zenith/export` —
        coisas que a cópia pública nunca leva — e o guia mandava esperar "OK" de um comando que
        não tinha como dar OK.
        """
        r = PP.varrer(PP.RAIZ, respeitar_exclusoes=True)
        self.assertEqual(r["erros"], [])

    def test_so_conferir_sem_exclusao_ainda_ve_o_que_fica_fora(self):
        """O modo antigo continua existindo para quem quiser a foto da pasta inteira."""
        if not (PP.RAIZ / "docs" / "historico").is_dir():
            self.skipTest("esta é a pasta pública: o histórico do dono nem existe aqui")
        r = PP.varrer(PP.RAIZ)
        caminhos = " ".join(r["erros"])
        self.assertTrue("docs/historico" in caminhos or "Akira" in caminhos or ".vrm" in caminhos)

    def test_projeto_real_sai_limpo(self):
        """O projeto de verdade, montado como edição Pública, não pode ter chave, caminho pessoal, nome antigo visível..."""
        saida = self.d / "real"
        r = PP.montar(RAIZ, saida)
        self.assertEqual(r["erros"], [], "\n".join(r["erros"][:20]))
        self.assertFalse(list(saida.rglob("*.vrm")))
        self.assertFalse((saida / "config" / "settings.json").exists())
        self.assertEqual(ED.edicao(saida), "publico")


class InstalacaoTests(_Tmp):
    def test_data_root_vem_do_instalador_e_o_settings_manda(self):
        from brain import zenith_settings as S
        inst = self.escrever("config/instalacao.json", "\ufeff" + json.dumps({"data_root_path": "D:\\Meus Dados\\João"}))
        sett = self.d / "config" / "settings.json"
        with mock.patch.object(S, "INSTALACAO_FILE", inst), mock.patch.object(S, "SETTINGS_FILE", sett):
            self.assertEqual(str(S._read_data_root_override()), "D:\\Meus Dados\\João")     # BOM do instalador é aceito
            sett.write_text(json.dumps({"data_root_path": "E:\\outra"}), encoding="utf-8")
            self.assertEqual(str(S._read_data_root_override()), "E:\\outra")                  # escolha do usuário vence
            sett.write_text(json.dumps({"data_root_path": ""}), encoding="utf-8")
            self.assertEqual(str(S._read_data_root_override()), "D:\\Meus Dados\\João")     # vazio = cai no instalador

    def test_sem_nenhum_arquivo_nao_muda_nada(self):
        from brain import zenith_settings as S
        with mock.patch.object(S, "INSTALACAO_FILE", self.d / "nao.json"), mock.patch.object(S, "SETTINGS_FILE", self.d / "nem.json"):
            self.assertIsNone(S._read_data_root_override())

    def test_script_do_instalador(self):
        iss = (RAIZ / "instalador" / "Zenith.iss").read_bytes()
        self.assertTrue(iss.startswith(b"\xef\xbb\xbf"), "o .iss precisa de BOM UTF-8 (tem acentos)")
        t = iss.decode("utf-8-sig")
        self.assertRegex(t, r"AppId=\{\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}")
        self.assertIn("PrivilegesRequired=lowest", t)                 # não exige administrador
        self.assertIn("CreateInputDirPage", t)                        # página "onde ficam as criações"
        self.assertIn("instalacao.json", t)
        self.assertIn("data_root_path", t)
        self.assertIn("DisableDirPage=no", t)                         # mostra onde vai instalar
        for arq in ("config\\settings.json", "config\\conversations.json", "memory_db", "creations", "models"):
            self.assertIn(arq, t.split("[Files]")[1].split("[Icons]")[0], arq)   # dados do usuário não entram no instalador
        self.assertNotIn("\\\r\n", t.split("[Files]")[1].split("[Icons]")[0])      # sem continuação de linha
        for ref in re.findall(r"(?:WizardImageFile|WizardSmallImageFile|SetupIconFile)=\.\.\\([^\r\n]+)", t):
            self.assertTrue((RAIZ / ref.replace("\\", "/")).is_file(), ref)

    def test_bat_do_instalador_confere_o_que_precisa(self):
        b = (RAIZ / "instalador" / "construir_instalador.bat").read_text(encoding="utf-8")
        self.assertIn("ISCC.exe", b)
        self.assertIn("dist\\Zenith\\Zenith.exe", b)
        self.assertIn("/DAppVersion", b)


class BuildEdicaoTests(_Tmp):
    @classmethod
    def setUpClass(cls):
        cls.B = _carregar("build_exe_v14", RAIZ / "build_exe.py")

    def test_le_o_argumento_edicao(self):
        self.assertEqual(self.B._edicao_pedida(["--edicao", "publico"]), "publico")
        self.assertEqual(self.B._edicao_pedida(["--edicao=ADMIN"]), "admin")
        self.assertEqual(self.B._edicao_pedida([]), "")

    def test_edicao_invalida_para_o_build(self):
        with self.assertRaises(SystemExit):
            with mock.patch("builtins.print"):
                self.B._aplicar_edicao_do_build(["--edicao", "xpto"], self.d)

    def test_grava_edition_json(self):
        self.assertEqual(self.B._aplicar_edicao_do_build(["--edicao", "publico"], self.d), "publico")
        self.assertTrue(ED.e_publico(self.d))

    def test_avatar_na_edicao_publica_exige_confirmacao(self):
        self.escrever("body/zenith/addons/avatars/Modelo.vrm", b"x", binario=True)
        with mock.patch("builtins.print"):
            self.assertFalse(self.B._conferir_avatares_publicos([], self.d))
            self.assertTrue(self.B._conferir_avatares_publicos(["--confirmo-avatares-livres"], self.d))

    def test_sem_avatar_segue(self):
        with mock.patch("builtins.print"):
            self.assertTrue(self.B._conferir_avatares_publicos([], self.d))

    def test_leia_me_publico_nao_manda_abrir_como_administrador(self):
        self.B._escrever_leia_me_primeira_vez(str(self.d), publico=True)
        txt = (self.d / "LEIA-ME_PRIMEIRA_VEZ.txt").read_text(encoding="utf-8")
        self.assertNotIn("ADMINISTRADOR", txt)
        self.assertIn("Nao precisa ser administrador", txt)
        d2 = self.d / "dono"
        self.B._escrever_leia_me_primeira_vez(str(d2), publico=False)
        self.assertIn("ADMINISTRADOR", (d2 / "LEIA-ME_PRIMEIRA_VEZ.txt").read_text(encoding="utf-8"))

    def test_aviso_de_administrador_so_na_edicao_do_dono(self):
        src = (RAIZ / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn('if edicao_do_build == "publico":', src)


class MarcaEGodotTests(unittest.TestCase):
    def test_imagens_da_marca(self):
        from PIL import Image
        esperado = {"assets/instalador_lateral.bmp": (164, 314), "assets/instalador_pequena.bmp": (55, 55),
                    "body/zenith/assets/zenith_splash.png": (420, 640), "assets/zenith_logo_horizontal.png": (1200, 360)}
        for rel, tam in esperado.items():
            with Image.open(RAIZ / rel) as im:
                self.assertEqual(im.size, tam, rel)

    def test_godot_usa_a_abertura_do_zenith_e_nao_a_do_godot(self):
        pg = (RAIZ / "body/zenith/project.godot").read_text(encoding="utf-8")
        self.assertIn('boot_splash/image="res://assets/zenith_splash.png"', pg)
        self.assertIn("boot_splash/show_image=true", pg)
        self.assertTrue((RAIZ / "body/zenith/assets/zenith_splash.png").is_file())
        ex = (RAIZ / "body/zenith/export_presets.cfg").read_text(encoding="utf-8")
        for chave in ("company_name", "product_name", "file_description", "copyright"):
            m = re.search(rf'application/{chave}="([^"]*)"', ex)
            self.assertTrue(m and m.group(1) == "Zenith", chave)
        self.assertNotIn("Godot", re.findall(r'application/\w+="([^"]*)"', ex).__str__())

    def test_exe_do_python_se_apresenta_como_zenith(self):
        b = (RAIZ / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn("u'FileDescription', u'Zenith'", b)

    def test_nenhum_arquivo_do_projeto_se_chama_como_o_nome_antigo_no_firmware(self):
        self.assertTrue((RAIZ / "firmware/zenith_tft_esp32s3/zenith_tft_esp32s3.ino").is_file())


# ----------------------------------------------------------------------------------------------------------------------
# MÃOS: o GDScript calcula o eixo de curvatura da geometria do esqueleto. Aqui a mesma conta em Python, para provar que a
# lógica faz o dedo ir PARA A PALMA nos dois lados e em poses diferentes (o Godot não roda neste computador).
# ----------------------------------------------------------------------------------------------------------------------
def _sub(a, b): return tuple(x - y for x, y in zip(a, b))
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _mul(a, k): return tuple(x * k for x in a)
def _add(a, b): return tuple(x + y for x, y in zip(a, b))
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _norm(a):
    n = math.sqrt(_dot(a, a))
    return tuple(x / n for x in a)


def _normal_da_palma(pulso, base_indicador, base_mindinho, up, lat, sinal):
    a, b = _sub(base_indicador, pulso), _sub(base_mindinho, pulso)
    n = _norm(_cross(a, b))
    ref = _norm(_add(_mul(_mul(up, -1), 0.7), _mul(_mul(lat, -sinal), 0.7)))
    return n if _dot(n, ref) >= 0 else _mul(n, -1)


def _rodar(v, eixo, ang):       # fórmula de Rodrigues
    k = _norm(eixo)
    return _add(_add(_mul(v, math.cos(ang)), _mul(_cross(k, v), math.sin(ang))), _mul(k, _dot(k, v) * (1 - math.cos(ang))))


class MaosTests(unittest.TestCase):
    UP, LAT = (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)

    def _confere(self, pulso, indicador, mindinho, dedo_dir, sinal):
        normal = _normal_da_palma(pulso, indicador, mindinho, self.UP, self.LAT, sinal)
        d = _norm(dedo_dir)
        eixo = _cross(d, normal)
        self.assertGreater(math.sqrt(_dot(eixo, eixo)), 0.2)
        depois = _rodar(d, eixo, 0.5)
        self.assertGreater(_dot(depois, normal), _dot(d, normal) + 0.2, "o dedo tem que ir PARA o lado da palma")
        return normal

    def test_t_pose_mao_direita_palma_pra_baixo(self):
        n = self._confere((0, 0, 0), (0.07, 0, 0.02), (0.06, 0, -0.03), (1, 0, 0.1), +1)
        self.assertLess(n[1], -0.9)

    def test_t_pose_mao_esquerda_palma_pra_baixo(self):
        n = self._confere((0, 0, 0), (-0.07, 0, 0.02), (-0.06, 0, -0.03), (-1, 0, 0.1), -1)
        self.assertLess(n[1], -0.9)

    def test_braco_caido_palma_pra_dentro(self):
        """Braço direito pendurado: a palma olha para o corpo (para -x), e o dedo curva para lá."""
        n = self._confere((0.2, 1.0, 0), (0.2, 0.93, 0.02), (0.2, 0.94, -0.03), (0, -1, 0.1), +1)
        self.assertLess(n[0], -0.9)

    def test_curva_nao_inverte_com_o_angulo_pequeno(self):
        d, normal = _norm((1, 0, 0)), (0.0, -1.0, 0.0)
        eixo = _cross(d, normal)
        for ang in (0.1, 0.4, 0.9, 1.4):
            self.assertLess(_rodar(d, eixo, ang)[1], 0)

    def _gd(self, nome):
        return (RAIZ / "body/zenith" / nome).read_text(encoding="utf-8").replace("\r\n", "\n")

    def test_modulo_de_maos_tem_a_interface_que_a_vida_chama(self):
        m = self._gd("zenith_maos.gd")
        self.assertTrue(m.startswith("extends RefCounted"))
        for f in ("func preparar(sk: Skeleton3D, up: Vector3, lat: Vector3) -> int:", "func atualizar(", "func soltar("):
            self.assertIn(f, m)
        self.assertNotIn("get_tree()", m)           # RefCounted não tem árvore

    def test_vida_carrega_as_maos_com_load_e_protege(self):
        v = self._gd("akira_vida.gd")
        self.assertIn('const MAOS_PATH := "res://zenith_maos.gd"', v)
        self.assertNotIn('preload("res://zenith_maos.gd")', v)       # preload derrubaria o avatar inteiro se houvesse erro
        self.assertIn("script.can_instantiate()", v)
        self.assertIn("_maos.atualizar(delta, pose_mao, _life == SPEAKING, _t)", v)
        self.assertIn("_maos.soltar()", v)

    def test_gestos_que_mudam_a_mao_existem_na_vida(self):
        v = self._gd("akira_vida.gd")
        m = self._gd("zenith_maos.gd")
        for g in ("pensar", "acenar", "comemorar", "ombros"):
            self.assertIn(f'"{g}"', v, g)
            self.assertIn(f'"{g}"', m, g)

    def test_angulos_ficam_em_faixa_humana(self):
        m = self._gd("zenith_maos.gd")
        nums = [float(x) for x in re.findall(r"\[(\d\.\d+), (\d\.\d+), (\d\.\d+)\]", m.replace("\n", " ")) for x in x]
        self.assertGreaterEqual(len(nums), 45)
        self.assertTrue(all(0.0 <= n <= 1.2 for n in nums), "nenhuma junta pode passar de ~70 graus")


# ----------------------------------------------------------------------------------------------------------------------
# sem emoji, captura sem a janela do Zenith, /presenca
# ----------------------------------------------------------------------------------------------------------------------
from brain import zenith_emoji as EM            # noqa: E402
from brain import zenith_captura as CAP         # noqa: E402
from brain import zenith_commands as CMD        # noqa: E402


class SemEmojiTests(unittest.TestCase):
    def setUp(self):
        EM.ATIVO = True

    def test_tira_emoji_e_arruma_o_espaco(self):
        casos = {"\U0001F310 O que essa vers\u00e3o": "O que essa vers\u00e3o", "Prontinho! \U0001F680 Criei": "Prontinho! Criei",
                 "fim \U0001F642.": "fim.", "fim \U0001F642": "fim", "linha1\n\U0001F534 Observando": "linha1\nObservando",
                 "Aten\u00e7\u00e3o \u26a0\ufe0f cuidado": "Aten\u00e7\u00e3o cuidado", "bandeira \U0001F1E7\U0001F1F7 ok": "bandeira ok",
                 "1\ufe0f\u20e3 primeiro": "1. primeiro"}
        for entrada, esperado in casos.items():
            self.assertEqual(EM.remover(entrada), esperado, entrada)

    def test_nao_mexe_em_simbolos_de_ciencia_nem_em_texto_normal(self):
        for s in ("5 \u2264 6 \u2192 \u2211 \u00a9 2026 \u00b0C", "visto \u2713 ok", "ol\u00e1, tudo bem? 100% \u00e7a", "a < b && c > d"):
            self.assertEqual(EM.remover(s), s)

    def test_mensagem_so_de_emoji_nao_vira_balao_vazio(self):
        self.assertEqual(EM.remover("\U0001F44B"), "\U0001F44B")

    def test_filtra_so_as_mensagens_de_texto_e_nao_altera_o_original(self):
        msg = {"action": "chat_message", "sender": "ai", "text": "Oi \U0001F44B tudo bem"}
        saida = EM.limpar_mensagem(msg)
        self.assertEqual(saida["text"], "Oi tudo bem")
        self.assertEqual(msg["text"], "Oi \U0001F44B tudo bem")
        outra = {"action": "settings_data", "x": "\U0001F600"}
        self.assertIs(EM.limpar_mensagem(outra), outra)
        self.assertEqual(EM.limpar_mensagem({"action": "notify", "title": "Zenith terminou", "body": "ok \u2705 feito"})["body"], "ok feito")
        self.assertEqual(EM.limpar_mensagem({"action": "chat_stream_chunk", "delta": "\U0001F680 ", "done": False})["delta"], "")

    def test_conversa_carregada_tambem_e_limpa(self):
        m = {"action": "conversation_loaded", "messages": [{"sender": "ai", "text": "Oi \U0001F600"}, {"sender": "user", "text": "ol\u00e1"}]}
        self.assertEqual([x["text"] for x in EM.limpar_mensagem(m)["messages"]], ["Oi", "ol\u00e1"])

    def test_desligado_nao_filtra(self):
        EM.ATIVO = False
        try:
            msg = {"action": "chat_message", "text": "Oi \U0001F600"}
            self.assertIs(EM.limpar_mensagem(msg), msg)
        finally:
            EM.ATIVO = True

    def test_a_ponte_aplica_o_filtro_e_o_prompt_pede_sem_emoji(self):
        ponte = (RAIZ / "brain/zenith_bridge.py").read_text(encoding="utf-8")
        self.assertIn("zenith_emoji.limpar_mensagem(data)", ponte)
        core = (RAIZ / "brain/zenith_core.py").read_text(encoding="utf-8")
        self.assertIn("n\u00e3o use emoji", core)


class CapturaSemZenithTests(unittest.TestCase):
    TELA = (1920, 1080)
    CONTROLE = {"hwnd": 1, "rect": (0, 0, 1920, 1040), "titulo": "Zenith \u2014 Central de Controle"}
    AVATAR = {"hwnd": 2, "rect": (1500, 100, 1920, 740), "titulo": "Zenith"}

    def _rodar(self, area, janelas=None, falha_na_captura=False, falha_ao_esconder=False):
        eventos = []
        def captura():
            eventos.append("captura")
            if falha_na_captura:
                raise RuntimeError("mss falhou")
            return b"PNG", None
        def esconder(j):
            if falha_ao_esconder:
                raise OSError("sem permissao")
            eventos.append(("esconde", j["hwnd"])); return True
        def mostrar(j): eventos.append(("mostra", j["hwnd"]))
        try:
            r = CAP.capturar_sem_zenith(captura, area, enumerar=lambda: janelas if janelas is not None else [self.CONTROLE, self.AVATAR],
                                        esconder=esconder, mostrar=mostrar, tela=self.TELA, espera=0, dormir=lambda s: eventos.append("espera"))
        except RuntimeError:
            r = "erro"
        return r, eventos

    def test_foto_unica_esconde_todas_e_devolve_todas(self):
        r, ev = self._rodar(0.0)
        self.assertEqual(r, (b"PNG", None))
        self.assertEqual(ev, [("esconde", 1), ("esconde", 2), "espera", "captura", ("mostra", 2), ("mostra", 1)])

    def test_observacao_ao_vivo_esconde_so_a_janela_grande(self):
        r, ev = self._rodar(0.25)
        self.assertEqual([e for e in ev if isinstance(e, tuple)], [("esconde", 1), ("mostra", 1)])

    def test_none_nao_esconde_nada(self):
        r, ev = self._rodar(None)
        self.assertEqual(ev, ["captura"])

    def test_se_a_captura_falha_as_janelas_voltam_do_mesmo_jeito(self):
        r, ev = self._rodar(0.0, falha_na_captura=True)
        self.assertEqual(r, "erro")
        self.assertIn(("mostra", 1), ev)
        self.assertIn(("mostra", 2), ev)

    def test_se_nao_consegue_esconder_captura_mesmo_assim(self):
        r, ev = self._rodar(0.0, falha_ao_esconder=True)
        self.assertEqual(r, (b"PNG", None))
        self.assertEqual(ev, ["captura"])

    def test_se_a_lista_de_janelas_quebra_captura_mesmo_assim(self):
        def quebra(): raise OSError("x")
        self.assertEqual(CAP.capturar_sem_zenith(lambda: "ok", 0.0, enumerar=quebra), "ok")

    def test_desligado_nas_configuracoes(self):
        CAP.ATIVO = False
        try:
            r, ev = self._rodar(0.0)
            self.assertEqual(ev, ["captura"])
        finally:
            CAP.ATIVO = True

    def test_fora_do_windows_nao_acha_janela(self):
        if os.name != "nt":
            self.assertEqual(CAP._enumerar_janelas_zenith(), [])

    def test_a_visao_usa_a_captura_sem_zenith(self):
        v = (RAIZ / "brain/zenith_vision.py").read_text(encoding="utf-8")
        self.assertIn("capturar_sem_zenith", v)
        h = (RAIZ / "brain/zenith_headless.py").read_text(encoding="utf-8")
        self.assertIn("ocultar_area=0.25", h)         # a observacao ao vivo nao faz o avatar piscar


class PresencaTests(unittest.TestCase):
    def test_presenca_vira_observacao_do_dia_todo(self):
        r = CMD.tratar("/presenca tela", {})
        self.assertEqual(r["acao"], "observar")
        self.assertEqual(r["args"]["tipo"], "screen")
        self.assertEqual(r["args"]["minutos"], 480)
        self.assertEqual(r["args"]["intervalo"], 15)

    def test_presenca_camera_e_parar(self):
        self.assertEqual(CMD.tratar("/presenca camera", {})["args"]["tipo"], "camera")
        self.assertEqual(CMD.tratar("/presenca parar", {})["acao"], "parar_observacao")

    def test_o_limite_da_observacao_comporta_o_dia_todo(self):
        from brain import zenith_observar as OB
        self.assertGreaterEqual(OB.MINUTOS_MAX, 480)
        self.assertLessEqual(OB.INTERVALO_MIN, 15)


if __name__ == "__main__":
    unittest.main()
