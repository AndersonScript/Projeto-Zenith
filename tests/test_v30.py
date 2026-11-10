"""
Testes do v30 — o que o Anderson pediu em 16/10 e ainda não existia (ou existia pela metade):

  1. "INFINITAS APIs DA MESMA IA": várias chaves por provedor, em rodízio, com quarentena
     quando uma estoura cota/chave inválida — a conversa não quebra e o usuário fica sabendo.
  2. "VIRAR UMA SINGULARIDADE": roteador por CAPACIDADE (texto, visão, imagem) com fallback
     automático e aviso transparente; nuvem/local escolhidos sem o usuário trocar na mão.
  3. "AVANÇADO + IA LOCAL": detectar Ollama/LM Studio, baixar modelo só quando pedido, entrar
     como reserva (Megazord), nunca substituindo a nuvem sem o usuário mandar.
  4. VÍDEO: efeitos, transição, 9:16 pra Shorts e legenda queimada (ffmpeg de verdade).
  5. Comandos /chaves, /rota e /local (o caminho barato, sem mexer no Godot).

Rodar: python -m unittest tests.test_v30 -v
NÃO provam: o serviço real de nenhum provedor (as chaves são de mentira), nem o Ollama de
verdade (não está instalado neste PC) — a detecção é testada com um servidor de mentira.
Os testes de vídeo usam o ffmpeg real (imageio-ffmpeg) e ficam "skipped" se ele não existir.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests import _stubs
_stubs.instalar()

from brain import zenith_chaves as CH
from brain import zenith_commands as CMD
from brain import zenith_ia_local as LOCAL
from brain import zenith_rota as ROTA
from brain import zenith_video as V
from brain.zenith_settings import DEFAULT_SETTINGS


class FakeCfg:
    """settings de mentira: dict + get/update, igual ao ZenithSettings no que os módulos usam."""
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **d):
        self.d = dict(d)

    def get(self, chave, padrao=None):
        v = self.d.get(chave, padrao)
        return padrao if v is None else v

    def update(self, mudancas):
        self.d.update(mudancas)

    def save(self, novo):
        self.d = dict(novo)


def _rotador(cfg, tmp: str) -> CH.Rotador:
    return CH.Rotador(cfg, arquivo=os.path.join(tmp, "chaves.txt"),
                      estado=os.path.join(tmp, "estado.json"))


# ======================================================================
class ChavesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zch_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_arquivo_aceita_comentario_duplicada_e_varios_provedores(self):
        p = Path(self.tmp) / "chaves.txt"
        p.write_text("# minhas chaves\ngemini = AIzaAAA1\n\nGEMINI = AIzaAAA1\nopenai: sk-AAA2\n"
                     "AIzaAAA3\n# gemini = AIzaIGNORADA\n", encoding="utf-8")
        lido = CH.ler_arquivo(p)
        self.assertEqual(lido["gemini"], ["AIzaAAA1", "AIzaAAA3"])
        self.assertEqual(lido["openai"], ["sk-AAA2"])

    def test_principal_primeiro_depois_extras_e_arquivo(self):
        Path(self.tmp, "chaves.txt").write_text("gemini = AIzaFILE\n", encoding="utf-8")
        cfg = FakeCfg(gemini_key="AIzaMAIN", chaves_extras={"gemini": ["AIzaEXTRA"]})
        r = _rotador(cfg, self.tmp)
        self.assertEqual(r.chaves("gemini"), ["AIzaMAIN", "AIzaEXTRA", "AIzaFILE"])

    def test_rodizio_alterna_e_pula_quem_esta_de_castigo(self):
        cfg = FakeCfg(gemini_key="k1", chaves_extras={"gemini": ["k2", "k3"]})
        agora = [1000.0]
        r = CH.Rotador(cfg, arquivo=os.path.join(self.tmp, "x.txt"),
                       estado=os.path.join(self.tmp, "e.json"), relogio=lambda: agora[0])
        self.assertEqual(r.proxima("gemini")[0], "k1")
        self.assertEqual(r.proxima("gemini")[0], "k2")
        r.marcar_erro("gemini", "k2", "429 RESOURCE_EXHAUSTED quota exceeded")
        depois = [r.proxima("gemini")[0] for _ in range(4)]
        self.assertNotIn("k2", depois)                       # de castigo não é tentada
        self.assertEqual(set(depois), {"k1", "k3"})         # e continua alternando entre as boas
        agora[0] += CH.TEMPO_ESPERA["cota"] + 1
        self.assertIn("k2", [r.proxima("gemini")[0] for _ in range(6)])

    def test_chave_invalida_fica_24h_e_cota_15min(self):
        cfg = FakeCfg(gemini_key="k1", chaves_extras={"gemini": ["k2"]})
        agora = [0.0]
        r = CH.Rotador(cfg, arquivo=os.path.join(self.tmp, "x.txt"),
                       estado=os.path.join(self.tmp, "e.json"), relogio=lambda: agora[0])
        r.marcar_erro("gemini", "k1", "API key not valid. Please pass a valid API key.")
        self.assertEqual(r._info("gemini", "k1")["motivo"], "invalida")
        self.assertGreaterEqual(r._info("gemini", "k1")["ate"], 24 * 3600 - 1)
        r.marcar_erro("gemini", "k2", "429 quota exceeded")
        self.assertLessEqual(r._info("gemini", "k2")["ate"], 15 * 60 + 1)

    def test_erro_de_modelo_nao_castiga_a_chave(self):
        cfg = FakeCfg(gemini_key="k1")
        r = _rotador(cfg, self.tmp)
        self.assertEqual(r.marcar_erro("gemini", "k1", "404 model not found"), "modelo")
        self.assertTrue(r.disponivel("gemini", "k1"))
        self.assertFalse(r._info("gemini", "k1"))

    def test_todas_de_castigo_nao_devolve_chave(self):
        cfg = FakeCfg(gemini_key="k1")
        agora = [10.0]
        r = CH.Rotador(cfg, arquivo=os.path.join(self.tmp, "x.txt"),
                       estado=os.path.join(self.tmp, "e.json"), relogio=lambda: agora[0])
        r.marcar_erro("gemini", "k1", "429 quota exceeded")
        self.assertEqual(r.proxima("gemini"), (None, -1))
        self.assertFalse(r.alguma_livre("gemini"))

    def test_sucesso_perdoa_e_estado_nao_guarda_a_chave(self):
        cfg = FakeCfg(gemini_key="AIzaSEGREDO1234")
        r = _rotador(cfg, self.tmp)
        r.marcar_erro("gemini", "AIzaSEGREDO1234", "429 quota exceeded")
        estado = Path(self.tmp, "estado.json").read_text(encoding="utf-8")
        self.assertNotIn("AIzaSEGREDO1234", estado)
        self.assertIn(CH._hash("AIzaSEGREDO1234"), estado)
        r.marcar_ok("gemini", "AIzaSEGREDO1234")
        self.assertTrue(r.disponivel("gemini", "AIzaSEGREDO1234"))

    def test_relatorio_mostra_so_os_ultimos_4(self):
        cfg = FakeCfg(gemini_key="AIzaSEGREDO1234")
        txt = _rotador(cfg, self.tmp).texto_relatorio()
        self.assertIn("••••1234", txt)
        self.assertNotIn("AIzaSEGREDO1234", txt)
        self.assertIn("Gemini", txt)

    def test_adicionar_e_remover_chave_extra(self):
        cfg = FakeCfg(gemini_key="AIzaMAIN")
        r = CH.adicionar_chave(cfg, "gemini", "AIzaNOVA9999")
        self.assertTrue(r["ok"])
        self.assertEqual(cfg.get("chaves_extras"), {"gemini": ["AIzaNOVA9999"]})
        self.assertNotIn("AIzaNOVA9999", r["mensagem"])
        repetida = CH.adicionar_chave(cfg, "gemini", "AIzaNOVA9999")
        self.assertFalse(repetida["ok"])
        self.assertIn("já está cadastrada", repetida["mensagem"])
        cfg2 = FakeCfg(gemini_key="AIzaMAIN", chaves_extras={"gemini": ["AIzaNOVA9999"]})
        self.assertFalse(CH.remover_chave(cfg2, "gemini", 0)["ok"])       # 0 é a principal
        self.assertTrue(CH.remover_chave(cfg2, "gemini", 1)["ok"])
        self.assertEqual(cfg2.get("chaves_extras"), {})

    def test_classificacao_de_erros(self):
        self.assertEqual(CH.classificar_motivo("429 Too Many Requests"), "cota")
        self.assertEqual(CH.classificar_motivo("insufficient_quota"), "cota")
        self.assertEqual(CH.classificar_motivo("401 Unauthorized"), "invalida")
        self.assertEqual(CH.classificar_motivo("503 UNAVAILABLE"), "instavel")
        self.assertEqual(CH.classificar_motivo("model not found"), "modelo")
        self.assertEqual(CH.classificar_motivo("qualquer coisa"), "outro")


# ======================================================================
class RotaTests(unittest.TestCase):
    def test_capacidades_padrao(self):
        self.assertIn("imagem", ROTA.capacidades("gemini"))
        self.assertIn("visao", ROTA.capacidades("openai"))
        self.assertNotIn("imagem", ROTA.capacidades("openai"))
        self.assertEqual(ROTA.capacidades("local"), {"texto"})

    def test_ajuste_do_usuario_marca_visao_na_ia_local(self):
        cfg = FakeCfg(ia_capacidades={"local": ["texto", "visao"]})
        self.assertTrue(ROTA.pode("local", "visao", cfg))
        self.assertFalse(ROTA.pode("local", "imagem", cfg))

    def test_ativa_primeiro_e_local_por_ultimo_como_reserva(self):
        cfg = FakeCfg(active_ai="openai")
        ordem = ROTA.escolher("texto", ["local", "gemini", "openai"], "openai", cfg)
        self.assertEqual(ordem, ["openai", "gemini", "local"])

    def test_local_pode_ser_principal(self):
        cfg = FakeCfg(ia_local_papel="principal")
        ordem = ROTA.escolher("texto", ["gemini", "local"], "gemini", cfg)
        self.assertEqual(ordem[0], "gemini")             # a ativa ainda manda
        self.assertEqual(ROTA.escolher("texto", ["gemini", "local"], "local", cfg)[0], "local")

    def test_preferencia_por_capacidade_vem_depois_da_ativa(self):
        cfg = FakeCfg(rota_preferida={"visao": "openai"})
        ordem = ROTA.escolher("visao", ["gemini", "openai", "claude"], "gemini", cfg)
        self.assertEqual(ordem[:2], ["gemini", "openai"])

    def test_quem_nao_sabe_ver_fica_fora(self):
        ordem = ROTA.escolher("visao", ["groq", "openai", "custom:x"], "groq", FakeCfg())
        self.assertNotIn("groq", ordem)
        self.assertEqual(ordem[0], "openai")
        self.assertEqual(ROTA.escolher("imagem", ["openai", "groq"], "openai"), [])

    def test_aviso_de_troca_e_transparente(self):
        cfg = FakeCfg(ai_endpoints=[{"id": "x", "name": "Minha IA"}])
        a = ROTA.aviso("visao", "groq", "openai", cfg)
        self.assertIn("Para ver a imagem", a)
        self.assertIn("Groq", a)
        b = ROTA.aviso("texto", "gemini", "custom:x", cfg)
        self.assertIn("Minha IA", b)
        self.assertEqual(ROTA.aviso("texto", "gemini", "gemini", cfg), "")

    def test_mapa_e_texto_nao_inventa_capacidade(self):
        cfg = FakeCfg(active_ai="gemini", gemini_key="k")
        txt = ROTA.texto_mapa(["gemini"], cfg)
        for s in ("Conversar:", "Ver imagens/tela:", "Criar imagem:", "No seu PC", "IA local"):
            self.assertIn(s, txt)

    def test_definir_e_limpar_preferencia(self):
        cfg = FakeCfg(rota_preferida={"texto": "groq"})
        self.assertFalse(ROTA.definir_preferencia(cfg, "voz", "x")["ok"])
        self.assertTrue(ROTA.definir_preferencia(cfg, "visao", "openai")["ok"])
        self.assertEqual(cfg.get("rota_preferida")["visao"], "openai")
        ROTA.definir_preferencia(cfg, "limpar")
        self.assertEqual(cfg.get("rota_preferida"), {})


# ======================================================================
class LocalTests(unittest.TestCase):
    def test_detecta_ollama_e_le_modelos(self):
        def fake_http(url, timeout=2.0):
            if url.startswith("http://127.0.0.1:11434"):
                return {"models": [{"name": "qwen2.5:1.5b"}, {"name": "llama3.2:3b"}]}
            raise OSError("connection refused")
        det = LOCAL.detectar(FakeCfg(), http=fake_http)
        self.assertTrue(det["rodando"])
        self.assertEqual(det["tipo"], "ollama")
        self.assertEqual(det["modelos"], ["qwen2.5:1.5b", "llama3.2:3b"])

    def test_sem_servidor_explica_sem_prometer_o_que_nao_tem(self):
        def fake_http(url, timeout=2.0):
            raise OSError("connection refused")
        det = LOCAL.detectar(FakeCfg(), http=fake_http)
        self.assertFalse(det["rodando"])
        txt = LOCAL.status_texto(FakeCfg(), det)
        self.assertIn("não encontrado", txt)
        self.assertIn("ollama.com", txt)
        self.assertIn("Ryzen", txt)                     # honestidade sobre a lentidão

    def test_url_do_cliente_vira_formato_openai(self):
        self.assertEqual(LOCAL.url_para_cliente(FakeCfg(ia_local_url="http://127.0.0.1:11434")),
                         "http://127.0.0.1:11434/v1")
        self.assertEqual(LOCAL.url_para_cliente(FakeCfg(ia_local_url="http://127.0.0.1:1234/v1")),
                         "http://127.0.0.1:1234/v1")

    def test_puxar_modelo_relata_progresso_e_erro(self):
        vistos = []

        def linhas_ok(url, dados, timeout=30.0, ao_linha=None):
            self.assertTrue(url.endswith("/api/pull"))
            self.assertEqual(dados["model"], "qwen2.5:1.5b")
            ao_linha({"status": "pulling", "total": 100, "completed": 40})
            ao_linha({"status": "success"})
            return True

        r = LOCAL.puxar_modelo("qwen2.5:1.5b", "http://127.0.0.1:11434",
                               progresso=lambda pct, t: vistos.append((pct, t)), linhas=linhas_ok)
        self.assertTrue(r["ok"])
        self.assertEqual(vistos[0], (40, "pulling"))

        def linhas_erro(url, dados, timeout=30.0, ao_linha=None):
            raise OSError("disco cheio")
        r2 = LOCAL.puxar_modelo("x", linhas=linhas_erro)
        self.assertFalse(r2["ok"])
        self.assertIn("disco cheio", r2["mensagem"])

    def test_nao_baixa_sozinho_sem_autorizacao(self):
        det = {"rodando": True, "tipo": "ollama", "modelos": [], "url": "http://127.0.0.1:11434"}
        cfg = FakeCfg(ia_local_ativa=True, ia_local_modelo="qwen2.5:1.5b")
        with mock.patch.object(LOCAL, "puxar_modelo", side_effect=AssertionError("não devia baixar")):
            msg = LOCAL.garantir_modelo(cfg, det)
        self.assertIn("não foi baixado", msg)
        self.assertIn("/local baixar", msg)

    def test_papel_principal_explica_o_custo(self):
        self.assertIn("mais lenta", LOCAL.explicar_papel("principal"))
        self.assertIn("por último", LOCAL.explicar_papel("reserva"))


# ======================================================================
class _FakeCompletions:
    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.chamadas = resposta, erro, []

    def create(self, **kw):
        self.chamadas.append(kw)
        if self.erro:
            raise RuntimeError(self.erro)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=self.resposta))])


def _cliente(resposta=None, erro=None):
    comp = _FakeCompletions(resposta, erro)
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=comp)), comp


class CoreRotacaoTests(unittest.TestCase):
    def setUp(self):
        from brain.zenith_core import ZenithCore
        self.tmp = tempfile.mkdtemp(prefix="zcore30_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        core = object.__new__(ZenithCore)
        core.settings = FakeCfg(active_ai="openai", contexto_modo="desligado")
        core.ia_ativa = "openai"
        core.conv_id = "c1"
        core.client = None
        core.chat = None
        core._clients = {}
        core._clientes_por_chave = {}
        core._custom_models = {}
        core._custom_names = {}
        core._midias = []
        core._hist_depth = 0
        core._modelo_em_uso = ""
        core.rotador = CH.Rotador(core.settings, arquivo=os.path.join(self.tmp, "x.txt"),
                                  estado=os.path.join(self.tmp, "e.json"))
        core._build_system_prompt = lambda: "sistema"
        core._historico_para_provedor = lambda prompt: []
        self.core = core

    def test_rotacao_usa_a_proxima_chave_quando_a_primeira_estoura(self):
        c1, _ = _cliente(erro="429 RESOURCE_EXHAUSTED quota exceeded")
        c2, comp2 = _cliente("resposta da chave 2")
        self.core._clientes_por_chave["openai"] = [
            {"chave": "k1", "cliente": c1}, {"chave": "k2", "cliente": c2}]
        self.assertEqual(self.core._call_provider_raw("openai", "oi"), "resposta da chave 2")
        self.assertEqual(len(c1.chat.completions.chamadas), 1)
        self.assertEqual(len(comp2.chamadas), 1)
        self.assertFalse(self.core.rotador.disponivel("openai", "k1"))
        # a próxima mensagem vai direto na chave boa
        self.core._call_provider_raw("openai", "oi de novo")
        self.assertEqual(len(c1.chat.completions.chamadas), 1)

    def test_chave_invalida_tambem_troca_e_nao_quebra(self):
        c1, _ = _cliente(erro="401 Unauthorized invalid api key")
        c2, _ = _cliente("ok")
        self.core._clientes_por_chave["openai"] = [{"chave": "a", "cliente": c1}, {"chave": "b", "cliente": c2}]
        self.assertEqual(self.core._call_provider_raw("openai", "oi"), "ok")

    def test_erro_de_modelo_nao_gasta_as_outras_chaves(self):
        c1, _ = _cliente(erro="model not found")
        c2, comp2 = _cliente("não devia chegar aqui")
        self.core._clientes_por_chave["openai"] = [{"chave": "a", "cliente": c1}, {"chave": "b", "cliente": c2}]
        with self.assertRaises(RuntimeError):
            self.core._call_provider_raw("openai", "oi")
        self.assertEqual(len(comp2.chamadas), 0)

    def test_visao_escolhe_quem_enxerga_e_avisa(self):
        vistos = []

        def raw(prov, prompt, image_bytes=None, image_mime=None):
            vistos.append((prov, bool(image_bytes)))
            return f"resposta de {prov}"

        self.core._call_provider_raw = raw
        self.core._clientes_por_chave = {"openai": [{"chave": "", "cliente": object()}],
                                         "gemini": [{"chave": "", "cliente": object()}]}
        self.core.settings = FakeCfg(active_ai="openai", ia_capacidades={"openai": ["texto"]})
        txt = self.core._call_provider("o que tem na imagem?", image_bytes=b"x", image_mime="image/png")
        self.assertEqual(vistos, [("gemini", True)])
        self.assertIn("Para ver a imagem", txt)
        self.assertIn("resposta de gemini", txt)

    def test_sem_visao_responde_texto_e_diz_que_nao_viu(self):
        self.core._call_provider_raw = lambda prov, p, image_bytes=None, image_mime=None: "só texto"
        self.core._clientes_por_chave = {"groq": [{"chave": "", "cliente": object()}]}
        self.core.settings = FakeCfg(active_ai="groq")
        txt = self.core._call_provider("e aí?", image_bytes=b"x", image_mime="image/png")
        self.assertIn("enxerga imagem", txt)
        self.assertIn("só texto", txt)

    def test_todas_as_chaves_em_espera_explica_em_vez_de_bater_de_novo(self):
        self.core.settings.d["openai_key"] = "k1"
        self.core.settings.d["chaves_extras"] = {"openai": ["k2"]}
        self.core._clientes_por_chave["openai"] = [{"chave": "k1", "cliente": object()},
                                                   {"chave": "k2", "cliente": object()}]
        self.core.rotador.marcar_erro("openai", "k1", "429 quota exceeded")
        self.core.rotador.marcar_erro("openai", "k2", "429 quota exceeded")
        with self.assertRaises(RuntimeError) as ctx:
            self.core._call_provider_raw("openai", "oi")
        self.assertIn("em espera", str(ctx.exception))

    def test_nenhuma_ia_responde_erro_explica_que_tentou_todas(self):
        def raw(prov, *a, **k):
            raise RuntimeError("cota estourada")
        self.core._call_provider_raw = raw
        self.core._clientes_por_chave = {"gemini": [{"chave": "", "cliente": object()}],
                                         "openai": [{"chave": "", "cliente": object()}]}
        self.core.settings = FakeCfg(active_ai="gemini")
        with self.assertRaises(RuntimeError) as ctx:
            self.core._call_provider("oi")
        self.assertIn("tentei", str(ctx.exception))
        self.assertIn("gemini", str(ctx.exception))

    def test_claude_e_llama_nao_sao_tentados_duas_vezes(self):
        self.assertEqual(self.core._sem_alias(["claude", "llama", "gemini"]), ["claude", "gemini"])

    def test_imagem_tambem_respeita_o_rodizio(self):
        from brain import zenith_imagem_ia as IA
        chamadas = []

        def gerar(desc, chave, pasta, modelo=None, proporcao=None):
            chamadas.append(chave)
            if chave == "k1":
                raise IA.ErroImagem("🎨 O Google barrou por COTA/limite de uso (erro 429)")
            return {"caminho": os.path.join(self.tmp, "img.png"), "modelo": "m", "texto": ""}

        Path(self.tmp, "img.png").write_bytes(b"png")
        self.core._clientes_por_chave["gemini"] = [{"chave": "k1", "cliente": object()},
                                                   {"chave": "k2", "cliente": object()}]
        self.core.settings = FakeCfg(active_ai="gemini")
        with mock.patch.object(IA, "gerar", gerar):
            txt = self.core._gerar_imagem_ia("um gato")
        self.assertEqual(chamadas, ["k1", "k2"])
        self.assertIn("Pronto", txt)

    def test_available_providers_inclui_local_e_personalizada(self):
        self.core._clientes_por_chave = {
            "gemini": [{"chave": "", "cliente": object()}],
            "local": [{"chave": "", "cliente": object()}],
            "custom:x": [{"chave": "", "cliente": object()}]}
        provs = self.core.available_providers()
        self.assertIn("local", provs)
        self.assertIn("custom:x", provs)


# ======================================================================
class _VideoBase(unittest.TestCase):
    ff = None

    @classmethod
    def setUpClass(cls):
        cls.ff = V.achar_ffmpeg(str(RAIZ))
        if not cls.ff:
            raise unittest.SkipTest("sem ffmpeg neste computador")
        cls.tmp = tempfile.mkdtemp(prefix="zvid30_")
        cls.a = os.path.join(cls.tmp, "a.mp4")
        cls.b = os.path.join(cls.tmp, "b.mp4")
        for caminho, cor in ((cls.a, "red"), (cls.b, "blue")):
            subprocess.run([cls.ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                            "-i", f"color=c={cor}:s=320x180:r=24:d=1.2", "-f", "lavfi",
                            "-i", "sine=frequency=440:duration=1.2", "-shortest",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", caminho], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), True)

    def info(self, caminho):
        r = subprocess.run([self.ff, "-hide_banner", "-i", caminho, "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        import re
        tam = re.search(r"Video: .*?, (\d+)x(\d+)", r.stderr)
        dur = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
        seg = (int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))) if dur else 0
        return (int(tam.group(1)), int(tam.group(2))) if tam else None, round(seg, 2)


class Video30Tests(_VideoBase):
    def test_efeito_e_alias_em_portugues(self):
        for estilo in ("pb", "preto e branco", "sepia", "vintage", "cinema", "neon", "sonho", "espelho", "nitido"):
            self.assertTrue(V.filtro_do_estilo(estilo))
        self.assertIn("gblur", V.filtro_do_estilo("desfoque", 2.0))
        with self.assertRaises(V.ErroVideo):
            V.filtro_do_estilo("arco-iris-x")

    def test_efeito_gera_arquivo_do_mesmo_tamanho(self):
        saida = os.path.join(self.tmp, "efeito.mp4")
        V.efeito(self.ff, self.a, "pb", saida)
        tam, dur = self.info(saida)
        self.assertEqual(tam, (320, 180))
        self.assertAlmostEqual(dur, 1.2, delta=0.3)

    def test_vertical_9_16_nos_dois_modos(self):
        for modo in ("corte", "fundo"):
            saida = os.path.join(self.tmp, f"v_{modo}.mp4")
            V.enquadrar(self.ff, self.a, saida, "9:16", modo)
            self.assertEqual(self.info(saida)[0], (1080, 1920))
        with self.assertRaises(V.ErroVideo):
            V.enquadrar(self.ff, self.a, os.path.join(self.tmp, "x.mp4"), "7:3")

    def test_transicao_junta_dois_e_encurta_pela_duracao_da_transicao(self):
        saida = os.path.join(self.tmp, "trans.mp4")
        V.transicao(self.ff, [self.a, self.b], saida, "fade", 0.4)
        tam, dur = self.info(saida)
        self.assertEqual(tam, (1280, 720))
        self.assertAlmostEqual(dur, 1.2 + 1.2 - 0.4, delta=0.35)
        with self.assertRaises(V.ErroVideo):
            V.transicao(self.ff, [self.a], os.path.join(self.tmp, "y.mp4"))

    def test_legenda_queimada_muda_o_arquivo(self):
        srt = os.path.join(self.tmp, "l.srt")
        Path(srt).write_text("1\n00:00:00,100 --> 00:00:01,000\nOlá, Anderson!\n", encoding="utf-8")
        saida = os.path.join(self.tmp, "leg.mp4")
        V.legendar(self.ff, self.a, srt, saida)
        self.assertTrue(os.path.getsize(saida) > os.path.getsize(self.a) * 0.5)

    def test_despachante_aceita_as_operacoes_novas_e_os_aliases(self):
        r = V.executar_pedido({"op": "shorts", "entrada": self.a, "proporcao": "9:16", "modo": "fundo"},
                              os.path.join(self.tmp, "out"), ffmpeg=self.ff)
        self.assertEqual(self.info(r["saida"])[0], (1080, 1920))
        prev = V.preview_text({"op": "efeito", "entrada": self.a, "estilo": "cinema"})
        self.assertIn("efeito", prev)
        self.assertIn("cinema", prev)


# ======================================================================
class Comandos30Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zcmd30_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def cfg(self, **d):
        base = {"gemini_key": "AIzaMAIN", "chaves_extras": {}, "active_ai": "gemini",
                "ia_local_ativa": False, "rota_preferida": {}}
        base.update(d)
        return FakeCfg(**base)

    def test_chaves_lista_sem_vazar_a_chave(self):
        r = CMD.tratar("/chaves", {"settings": self.cfg()})
        self.assertIn("Gemini", r["resposta"])
        self.assertIn("••••", r["resposta"])
        self.assertNotIn("AIzaMAIN", r["resposta"])

    def test_chave_add_pede_recarregar_e_nao_mostra_a_chave(self):
        cfg = self.cfg()
        r = CMD.tratar("/chave add gemini AIzaNOVA1234", {"settings": cfg})
        self.assertEqual(r["acao"], "recarregar_ia")
        self.assertNotIn("AIzaNOVA1234", r["resposta"])
        self.assertEqual(cfg.get("chaves_extras"), {"gemini": ["AIzaNOVA1234"]})

    def test_chave_add_sem_argumentos_ensina_o_formato(self):
        r = CMD.tratar("/chave add gemini", {"settings": self.cfg()})
        self.assertIn("/chave add gemini", r["resposta"])
        self.assertIsNone(r.get("acao"))

    def test_rota_mostra_as_tres_capacidades_e_a_local(self):
        r = CMD.tratar("/rota", {"settings": self.cfg()})
        for s in ("Conversar", "Ver imagens/tela", "Criar imagem", "IA local"):
            self.assertIn(s, r["resposta"])

    def test_rota_define_preferencia(self):
        cfg = self.cfg()
        r = CMD.tratar("/rota visao openai", {"settings": cfg})
        self.assertEqual(r["acao"], "recarregar_ia")
        self.assertEqual(cfg.get("rota_preferida"), {"visao": "openai"})

    def test_local_status_e_ligar(self):
        cfg = self.cfg()
        with mock.patch.object(LOCAL, "detectar", return_value={
                "rodando": True, "tipo": "ollama", "nome": "Ollama",
                "url": "http://127.0.0.1:11434", "modelos": ["qwen2.5:1.5b"], "erro": ""}):
            r = CMD.tratar("/local", {"settings": cfg})
            self.assertIn("desligada", r["resposta"])
            r2 = CMD.tratar("/local ligar", {"settings": cfg})
        self.assertEqual(r2["acao"], "recarregar_ia")
        self.assertTrue(cfg.get("ia_local_ativa"))
        self.assertIn("reserva", r2["resposta"])

    def test_local_baixar_vira_acao_de_thread(self):
        r = CMD.tratar("/local baixar qwen2.5:1.5b", {"settings": self.cfg(), "core": object()})
        self.assertEqual(r["acao"], "baixar_local")
        self.assertEqual(r["args"]["modelo"], "qwen2.5:1.5b")

    def test_video_ganhou_efeito_vertical_transicao_e_legenda(self):
        for cmd, op in (("/video efeito a.mp4 pb", "efeito"),
                        ("/video vertical a.mp4 9:16 fundo", "enquadrar"),
                        ("/video transicao a.mp4 b.mp4 fade 0.5", "transicao"),
                        ("/video legenda a.mp4 l.srt", "legendar")):
            r = CMD.tratar(cmd, {"settings": self.cfg()})
            self.assertEqual(r["acao"], "video", cmd)
            self.assertEqual(r["args"]["pedido"]["op"], op, cmd)

    def test_ajuda_menciona_os_comandos_novos(self):
        txt = CMD.tratar("/ajuda", {})["resposta"]
        for s in ("/chaves", "/chave add", "/rota", "/local", "efeito", "vertical", "transicao", "legenda"):
            self.assertIn(s, txt)


# ======================================================================
class Configuracoes30Tests(unittest.TestCase):
    def test_versao_e_v30_ou_maior(self):
        from brain import zenith_version
        self.assertGreaterEqual(zenith_version.numero(), (1, 0, 0))

    def test_defaults_novos_existem_e_sao_seguros(self):
        self.assertEqual(DEFAULT_SETTINGS["chaves_extras"], {})
        self.assertEqual(DEFAULT_SETTINGS["rota_preferida"], {})
        self.assertFalse(DEFAULT_SETTINGS["ia_local_ativa"])
        self.assertFalse(DEFAULT_SETTINGS["ia_local_baixar_sozinho"])
        self.assertEqual(DEFAULT_SETTINGS["ia_local_papel"], "reserva")

    def test_prompt_da_ia_ensina_as_operacoes_novas_de_video(self):
        src = (RAIZ / "brain" / "zenith_core.py").read_text(encoding="utf-8")
        for s in ("enquadrar (proporcao 9:16", "efeito (estilo:", "transicao", "legendar (srt"):
            self.assertIn(s, src)

    def test_core_nao_imprime_a_chave_crua_em_log(self):
        src = (RAIZ / "brain" / "zenith_core.py").read_text(encoding="utf-8")
        self.assertIn("mascarar(chave)", src)
        for linha in src.splitlines():
            if "print(" in linha and "{chave}" in linha:
                self.assertIn("mascarar", linha, f"linha imprime a chave crua: {linha.strip()}")


if __name__ == "__main__":
    unittest.main()
