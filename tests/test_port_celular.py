"""Testes do port para celular (v1.11). Não precisam de Android, Godot, internet, chaves nem das bibliotecas
pesadas: a ponte, o mss, o opencv e o plyer são trocados por falsos.

    python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import base64
import os
import tempfile
import unittest
from unittest import mock

from brain import zenith_downgrade as dg
from brain import zenith_memoria_leve as ml
from brain import zenith_plataforma as pl
from brain.zenith_plataforma_android import AndroidPlataforma
from brain.zenith_plataforma_pc import PCPlataforma

MEMINFO = """MemTotal:        3856432 kB
MemFree:          210000 kB
MemAvailable:    1500000 kB
Buffers:           10000 kB
"""


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


class PontaFalsa:
    """Imita o app Android: guarda as chamadas e devolve respostas combinadas."""

    def __init__(self, respostas=None, capacidades=None):
        self.chamadas = []
        self.respostas = respostas or {}
        self.capacidades = capacidades if capacidades is not None else []
        self.assinantes = {}

    def chamar(self, nome, **args):
        self.chamadas.append((nome, args))
        if nome == "capacidades.listar":
            return self.capacidades
        r = self.respostas.get(nome, {"ok": True})
        if isinstance(r, Exception):
            raise r
        return r

    def assinar(self, evento, funcao):
        self.assinantes.setdefault(evento, []).append(funcao)

    def desassinar(self, evento, funcao):
        self.assinantes[evento].remove(funcao)

    def emitir(self, evento, dados):
        for f in list(self.assinantes.get(evento, [])):
            f(dados)

    def ultima(self, nome):
        return [a for n, a in self.chamadas if n == nome][-1]


# ============================== plataforma base =====================================================
class PlataformaBaseTests(unittest.TestCase):
    def setUp(self):
        pl.definir(None)

    def tearDown(self):
        pl.definir(None)
        pl.registrar_ponte(None)

    def test_detectar_forcado(self):
        with mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"}):
            self.assertEqual(pl.detectar(), "android")

    def test_detectar_termux_pelas_variaveis(self):
        env = {"ANDROID_ROOT": "/system", "ANDROID_DATA": "/data"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("ZENITH_PLATAFORMA", None)
            self.assertEqual(pl.detectar(), "android")

    def test_parse_meminfo(self):
        total, livre = pl._parse_meminfo(MEMINFO)
        self.assertAlmostEqual(total, 3856432 * 1024 / 1024 ** 3, places=3)
        self.assertAlmostEqual(livre, 1500000 * 1024 / 1024 ** 3, places=3)

    def test_parse_meminfo_sem_memavailable_soma_livre_buffers_cache(self):
        total, livre = pl._parse_meminfo("MemTotal: 1048576 kB\nMemFree: 524288 kB\nBuffers: 0 kB\nCached: 0 kB\n")
        self.assertAlmostEqual(livre, 0.5, places=3)

    def test_parse_meminfo_lixo_nao_chuta(self):
        self.assertEqual(pl._parse_meminfo("isso não é meminfo"), (None, None))

    def test_medir_sistema_usa_meminfo_injetado(self):
        m = pl.medir_sistema(meminfo=MEMINFO)
        self.assertEqual(m["ram_total_gb"], 3.7)
        self.assertEqual(m["fonte"], "meminfo")
        for chave in ("bateria_pct", "carregando", "temperatura_c"):
            self.assertIn(chave, m)

    def test_capacidade_ausente_vira_frase_em_portugues(self):
        base = pl.Plataforma()
        with self.assertRaises(pl.Indisponivel) as ctx:
            base.tocar_audio("x.mp3")
        self.assertIn("não dá para", str(ctx.exception))

    def test_captura_sem_capacidade_devolve_tupla_do_codigo_antigo(self):
        self.assertEqual(pl.Plataforma().capturar_tela()[0], None)
        self.assertIn("tirar uma foto", pl.Plataforma().capturar_camera()[1])

    def test_capacidade_desconhecida_e_erro_de_programacao(self):
        with self.assertRaises(ValueError):
            pl.Plataforma()._exigir("telepatia")

    def test_obter_android_e_registrar_ponte_zera_o_cache(self):
        with mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"}):
            sem_ponte = pl.obter()
            self.assertIsInstance(sem_ponte, AndroidPlataforma)
            self.assertFalse(sem_ponte.tem("tela"))
            pl.registrar_ponte(PontaFalsa(capacidades=["tela"]))
            com_ponte = pl.obter()
            self.assertIsNot(sem_ponte, com_ponte)
            self.assertTrue(com_ponte.tem("tela"))

    def test_obter_pc(self):
        with mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "windows"}):
            self.assertIsInstance(pl.obter(), PCPlataforma)


# ============================== plataforma Android =====================================================
class AndroidTests(unittest.TestCase):
    def test_sem_ponte_tudo_indisponivel_mas_medir_funciona(self):
        a = AndroidPlataforma(None)
        self.assertEqual(a.capacidades, frozenset({"sistema"}))
        self.assertIsNone(a.capturar_tela()[0])
        self.assertIn("ram_total_gb", a.medir())

    def test_capacidades_vem_do_aparelho_e_ignora_nome_inventado(self):
        a = AndroidPlataforma(PontaFalsa(capacidades=["tela", "camera", "poder_secreto"]))
        self.assertTrue(a.tem("tela") and a.tem("camera"))
        self.assertFalse(a.tem("poder_secreto"))
        self.assertFalse(a.tem("microfone"))

    def test_capacidades_em_dict(self):
        p = PontaFalsa()
        p.capacidades = {"capacidades": ["abrir"]}
        self.assertTrue(AndroidPlataforma(p).tem("abrir"))

    def test_capturar_tela_decodifica_base64_e_repassa_argumentos(self):
        p = PontaFalsa({"tela.capturar": {"ok": True, "imagem": b64(b"\x89PNGdados")}}, ["tela"])
        img, erro = AndroidPlataforma(p).capturar_tela(max_w=640, jpeg=True)
        self.assertEqual((img, erro), (b"\x89PNGdados", None))
        self.assertEqual(p.ultima("tela.capturar"), {"max_w": 640, "jpeg": True})

    def test_erro_do_android_vira_tupla_com_a_frase(self):
        p = PontaFalsa({"camera.capturar": {"ok": False, "erro": "Permissão da câmera negada."}}, ["camera"])
        self.assertEqual(AndroidPlataforma(p).capturar_camera(), (None, "Permissão da câmera negada."))

    def test_ponte_que_explode_nao_derruba_o_cerebro(self):
        p = PontaFalsa({"tela.capturar": RuntimeError("binder morreu")}, ["tela"])
        img, erro = AndroidPlataforma(p).capturar_tela()
        self.assertIsNone(img)
        self.assertIn("binder morreu", erro)

    def test_imagem_corrompida(self):
        p = PontaFalsa({"tela.capturar": {"ok": True, "imagem": "###"}}, ["tela"])
        self.assertIn("corrompida", AndroidPlataforma(p).capturar_tela()[1])

    def test_tocar_audio(self):
        p = PontaFalsa(capacidades=["audio_saida"])
        AndroidPlataforma(p).tocar_audio("/data/voz.mp3", volume=0.5)
        self.assertEqual(p.ultima("audio.tocar"), {"caminho": "/data/voz.mp3", "volume": 0.5})

    def test_microfone_entrega_bytes_decodificados_e_para_de_escutar(self):
        p = PontaFalsa(capacidades=["microfone"])
        a, recebidos = AndroidPlataforma(p), []
        a.iniciar_microfone(recebidos.append, taxa=16000)
        p.emitir("mic.quadro", {"pcm16": b64(b"\x01\x02\x03\x04")})
        self.assertEqual(recebidos, [b"\x01\x02\x03\x04"])
        self.assertEqual(p.ultima("mic.iniciar"), {"taxa": 16000})
        a.parar_microfone()
        self.assertEqual(p.assinantes["mic.quadro"], [])
        p.emitir("mic.quadro", {"pcm16": b64(b"\x09")})
        self.assertEqual(len(recebidos), 1)

    def test_quadro_ruim_nao_derruba_a_escuta(self):
        p = PontaFalsa(capacidades=["microfone"])
        a = AndroidPlataforma(p)

        def estoura(_):
            raise RuntimeError("boom")

        a.iniciar_microfone(estoura)
        p.emitir("mic.quadro", {"pcm16": b64(b"\x01")})     # não levanta

    def test_microfone_que_falha_ao_iniciar_nao_deixa_assinatura_pendurada(self):
        p = PontaFalsa({"mic.iniciar": {"ok": False, "erro": "Sem permissão do microfone."}}, ["microfone"])
        with self.assertRaises(pl.Indisponivel):
            AndroidPlataforma(p).iniciar_microfone(lambda b: None)
        self.assertEqual(p.assinantes.get("mic.quadro", []), [])

    def test_transcrever(self):
        p = PontaFalsa({"stt.transcrever": {"ok": True, "texto": "olá Zenith"}}, ["transcricao"])
        self.assertEqual(AndroidPlataforma(p).transcrever(b"\x00\x01"), "olá Zenith")
        enviado = p.ultima("stt.transcrever")
        self.assertEqual(base64.b64decode(enviado["pcm16"]), b"\x00\x01")
        self.assertEqual((enviado["taxa"], enviado["idioma"]), (16000, "pt"))

    def test_sintetizar_voz_local(self):
        p = PontaFalsa(capacidades=["voz_local"])
        self.assertTrue(AndroidPlataforma(p).sintetizar("oi", "/data/x.wav", voz="pt-BR", tom=1.1))
        self.assertEqual(p.ultima("tts.sintetizar")["voz"], "pt-BR")

    def test_ble_envia_bytes_em_base64(self):
        p = PontaFalsa(capacidades=["ble"])
        self.assertTrue(AndroidPlataforma(p).ble_enviar("Zenith-Carrinho", b"F\n"))
        self.assertEqual(base64.b64decode(p.ultima("ble.enviar")["dados"]), b"F\n")

    def test_llm_local_endereco(self):
        p = PontaFalsa({"llm.endereco": {"ok": True, "url": "http://127.0.0.1:8080/v1"}}, ["llm_local"])
        self.assertEqual(AndroidPlataforma(p).endereco_llm_local(), "http://127.0.0.1:8080/v1")

    def test_llm_local_desligada_no_downgrade_nao_e_anunciada(self):
        a = AndroidPlataforma(PontaFalsa(capacidades=["tela"]))
        with self.assertRaises(pl.Indisponivel):
            a.endereco_llm_local()

    def test_medir_prefere_os_numeros_do_android(self):
        p = PontaFalsa({"sistema.medir": {"ok": True, "ram_total_gb": 8.0, "ram_livre_gb": 3.1,
                                          "bateria_pct": 55, "carregando": False, "temperatura_c": 38.5}},
                       ["sistema"])
        m = AndroidPlataforma(p).medir()
        self.assertEqual((m["ram_total_gb"], m["bateria_pct"], m["fonte"]), (8.0, 55, "android"))

    def test_notificar_e_abrir(self):
        p = PontaFalsa(capacidades=["notificacao", "abrir"])
        a = AndroidPlataforma(p)
        self.assertTrue(a.notificar("Zenith", "Resumo do dia pronto"))
        self.assertTrue(a.abrir("https://exemplo.com"))
        self.assertEqual(p.ultima("app.abrir"), {"alvo": "https://exemplo.com"})


# ============================== plataforma PC (falsos) ====================================================
class FalsoMss:
    class tools:
        @staticmethod
        def to_png(rgb, size):
            return b"PNG:" + bytes(size_str(size), "ascii")

    class _Shot:
        rgb, size = b"\x00" * 12, (2, 2)

    class _Sct:
        monitors = [{}, {"w": 2}]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def grab(self, monitor):
            return FalsoMss._Shot()

    @staticmethod
    def mss():
        return FalsoMss._Sct()


def size_str(size):
    return f"{size[0]}x{size[1]}"


class PCTests(unittest.TestCase):
    def test_sem_bibliotecas_diz_o_que_falta(self):
        pc = PCPlataforma(mss_mod=None, cv2_mod=None, plyer_mod=None)
        self.assertFalse(pc.tem("tela") or pc.tem("camera") or pc.tem("notificacao"))
        self.assertIn("mss", pc.capturar_tela()[1])
        self.assertIn("opencv", pc.capturar_camera()[1])
        with self.assertRaises(pl.Indisponivel):
            pc.notificar("a", "b")

    def test_tela_png_com_mss_falso(self):
        pc = PCPlataforma(mss_mod=FalsoMss, cv2_mod=None, plyer_mod=None)
        self.assertEqual(pc.capturar_tela(), (b"PNG:2x2", None))

    def test_tela_redimensionada_jpeg_com_pillow(self):
        pc = PCPlataforma(mss_mod=FalsoMss, cv2_mod=None, plyer_mod=None)
        img, erro = pc.capturar_tela(max_w=1, jpeg=True)
        self.assertIsNone(erro)
        self.assertTrue(img.startswith(b"\xff\xd8"))               # cabeçalho JPEG

    def test_notificar_com_plyer_falso(self):
        chamadas = []
        plyer = mock.Mock()
        plyer.notification.notify = lambda **kw: chamadas.append(kw)
        pc = PCPlataforma(mss_mod=None, cv2_mod=None, plyer_mod=plyer)
        self.assertTrue(pc.notificar("Zenith", "ok"))
        self.assertEqual(chamadas[0]["title"], "Zenith")

    def test_microfone_continua_nos_modulos_atuais(self):
        self.assertFalse(PCPlataforma(None, None, None).tem("microfone"))


# ============================== memória leve ==========================================================
class MemoriaLeveTests(unittest.TestCase):
    def setUp(self):
        self.c = ml.ColecaoLeve()
        self.c.add(
            ids=["a", "b", "c", "d"],
            documents=["O Anderson gosta de programar em Python e Godot",
                       "A apresentação na escola é na sexta-feira",
                       "Cardápio da cantina: pão de queijo e suco",
                       "Anderson: me lembra do carrinho\nZenith: claro, o carrinho usa ESP32-S3"],
            metadatas=[{"type": "fact"}, {"type": "fact"}, {"type": "chat_raw"}, {"type": "chat_raw"}])

    def test_count_get_delete(self):
        self.assertEqual(self.c.count(), 4)
        self.assertEqual(self.c.get(where={"type": "fact"})["ids"], ["a", "b"])
        self.c.delete(ids=["a"])
        self.assertEqual(self.c.count(), 3)
        self.c.delete(where={"type": "chat_raw"})
        self.assertEqual(self.c.get()["ids"], ["b"])

    def test_get_respeita_include(self):
        r = self.c.get(include=["documents"])
        self.assertIn("documents", r)
        self.assertNotIn("metadatas", r)

    def test_id_repetido_e_ignorado(self):
        self.c.add(ids=["a"], documents=["outro texto"], metadatas=[{}])
        self.assertEqual(self.c.count(), 4)
        self.assertIn("Anderson", self.c.get(ids=["a"])["documents"][0])

    def test_tamanhos_diferentes_dao_erro(self):
        with self.assertRaises(ValueError):
            self.c.add(ids=["x", "y"], documents=["só um"])

    def test_query_acha_o_assunto_certo_primeiro(self):
        r = self.c.query(query_texts=["quando é a apresentação na escola?"], n_results=3)
        self.assertEqual(r["ids"][0][0], "b")

    def test_query_ignora_acento_e_maiuscula(self):
        r = self.c.query(query_texts=["APRESENTACAO"], n_results=2)
        self.assertEqual(r["ids"][0][:1], ["b"])

    def test_query_radical_programar_programacao(self):
        r = self.c.query(query_texts=["programação"], n_results=2)
        self.assertEqual(r["ids"][0][:1], ["a"])

    def test_query_sem_assunto_devolve_vazio_e_nao_inventa(self):
        r = self.c.query(query_texts=["xilofone submarino"], n_results=5)
        self.assertEqual(r["documents"], [[]])

    def test_distancia_na_escala_do_recall(self):
        """`recall` descarta dist > 1.25 (exceto fatos): casar tudo = 0, casar quase nada passa de 1.25."""
        r = self.c.query(query_texts=["apresentação escola sexta-feira"], n_results=2)
        self.assertEqual(r["ids"][0][0], "b")
        self.assertLess(r["distances"][0][0], 0.2)
        r2 = self.c.query(query_texts=["apresentação carro violão jardim hospital escola"], n_results=3)
        self.assertGreater(r2["distances"][0][0], 1.25)

    def test_query_com_where(self):
        r = self.c.query(query_texts=["carrinho"], n_results=5, where={"type": "fact"})
        self.assertEqual(r["ids"][0], [])
        r = self.c.query(query_texts=["carrinho"], n_results=5, where={"type": {"$in": ["chat_raw"]}})
        self.assertEqual(r["ids"][0], ["d"])

    def test_formato_igual_ao_que_zenith_memory_le(self):
        r = self.c.query(query_texts=["carrinho"], n_results=16, include=["documents", "distances", "metadatas"])
        docs = (r.get("documents") or [[]])[0]
        dists = (r.get("distances") or [[]])[0]
        metas = (r.get("metadatas") or [[]])[0]
        self.assertEqual(len(docs), len(dists))
        self.assertEqual(len(docs), len(metas))
        self.assertEqual(metas[0]["type"], "chat_raw")

    def test_persiste_em_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            c1 = ml.abrir(pasta)
            c1.add(["x"], ["lembrete do café"], [{"type": "fact"}])
            c1.fechar()
            c2 = ml.abrir(pasta)
            self.assertEqual(c2.count(), 1)
            self.assertEqual(c2.query(["café"], 1)["ids"][0], ["x"])
            c2.fechar()

    def test_importar_de_outra_colecao(self):
        nova = ml.ColecaoLeve()
        self.assertEqual(nova.importar_de(self.c), 4)
        self.assertEqual(nova.get(where={"type": "fact"})["ids"], ["a", "b"])


# ============================== downgrade ====================================================================
def medida(total=8.0, livre=4.0, **extra):
    base = {"ram_total_gb": total, "ram_livre_gb": livre, "nucleos": 8, "disco_livre_gb": 20.0,
            "bateria_pct": None, "carregando": None, "temperatura_c": None}
    base.update(extra)
    return base


class DowngradeTests(unittest.TestCase):
    def test_perfis_sao_validos(self):
        for nome in dg.PERFIS:
            dg.validar(dg.perfil(nome))

    def test_perfil_por_ram(self):
        self.assertEqual(dg.recomendar(medida(12, 6))["perfil"], "completo")
        self.assertEqual(dg.recomendar(medida(8, 4))["perfil"], "medio")
        self.assertEqual(dg.recomendar(medida(5, 2.5))["perfil"], "leve")
        self.assertEqual(dg.recomendar(medida(2, 0.8))["perfil"], "minimo")

    def test_nao_mediu_nao_chuta(self):
        r = dg.recomendar({"ram_total_gb": None})
        self.assertFalse(r["ok"])
        self.assertIn("não chuto", r["avisos"][0])

    def test_vetorial_so_com_a_pecas_existir(self):
        r = dg.recomendar(medida(12, 6))
        self.assertEqual(r["recursos"]["memoria"], "leve")
        self.assertTrue(any("vetorial" in a for a in r["avisos"]))
        r = dg.recomendar(medida(12, 6), memoria_vetorial_disponivel=True)
        self.assertEqual(r["recursos"]["memoria"], "vetorial")

    def test_modelo_local_cabe_ou_desliga_com_motivo(self):
        r = dg.recomendar(medida(8, 5.0))
        self.assertEqual(r["recursos"]["ia_local"], "ligada")
        self.assertTrue(r["modelo_local"]["ok"])
        r = dg.recomendar(medida(8, 2.0))
        self.assertEqual(r["recursos"]["ia_local"], "desligada")
        self.assertIsNone(r["modelo_local"])
        self.assertTrue(any("nenhum modelo local" in a for a in r["avisos"]))

    def test_escolhe_o_maior_modelo_que_cabe(self):
        self.assertEqual(dg.escolher_modelo_local(medida(livre=4.0))["modelo"], "qwen2.5:0.5b")
        self.assertEqual(dg.escolher_modelo_local(medida(livre=6.0))["modelo"], "qwen2.5:1.5b")
        self.assertEqual(dg.escolher_modelo_local(medida(livre=9.0))["modelo"], "llama3.2:3b")

    def test_fronteira_exata_cabe(self):
        # 5.1 livre - 1.5 (VRM) - 1.0 (folga) = 2.6 = exatamente o que o 1.5b pede
        self.assertEqual(dg.escolher_modelo_local(medida(livre=5.1))["modelo"], "qwen2.5:1.5b")

    def test_modelo_nao_cabe_no_armazenamento(self):
        r = dg.escolher_modelo_local(medida(livre=9.0, disco_livre_gb=1.5))
        self.assertEqual(r["modelo"], "qwen2.5:1.5b")

    def test_avatar_padrao_libera_ram_para_a_ia(self):
        com_vrm = dg.escolher_modelo_local(medida(livre=5.1), avatar="vrm")
        sem_vrm = dg.escolher_modelo_local(medida(livre=5.1), avatar="padrao")
        self.assertEqual(com_vrm["modelo"], "qwen2.5:1.5b")
        self.assertEqual(sem_vrm["modelo"], "qwen2.5:1.5b")
        self.assertEqual(dg.escolher_modelo_local(medida(livre=6.4), avatar="padrao")["modelo"], "llama3.2:3b")
        self.assertEqual(dg.escolher_modelo_local(medida(livre=6.4), avatar="vrm")["modelo"], "qwen2.5:1.5b")

    def test_limiares_trocaveis(self):
        self.assertEqual(dg.recomendar(medida(8, 4), limiares={"completo": 8.0})["perfil"], "completo")

    def test_avisos_de_calor_e_bateria_sem_mudar_nada(self):
        r = dg.recomendar(medida(8, 4, temperatura_c=45.0, bateria_pct=10, carregando=False))
        textos = " ".join(r["avisos"])
        self.assertIn("quente", textos)
        self.assertIn("Bateria", textos)
        self.assertEqual(r["perfil"], "medio")
        r = dg.recomendar(medida(8, 4, bateria_pct=10, carregando=True))
        self.assertNotIn("Bateria", " ".join(r["avisos"]))

    def test_escada_desce_um_passo_por_vez_e_termina_no_piso(self):
        rec = dg.perfil("completo")
        primeiro = dg.proximo_passo(rec)
        self.assertEqual((primeiro["recurso"], primeiro["de"], primeiro["para"]), ("qualidade_grafica", "alta", "media"))
        passos = 0
        while True:
            s = dg.proximo_passo(rec)
            if s is None:
                break
            rec = dg.aplicar(rec, s["recurso"], s["para"])
            passos += 1
            self.assertLess(passos, 30)
        self.assertEqual(rec["avatar"], "padrao")                  # piso: nunca "sem avatar"
        self.assertEqual(rec["voz_saida"], "desligada")
        self.assertIsNone(dg.proximo_passo(rec))

    def test_escada_deixa_avatar_e_voz_para_o_fim(self):
        rec, ordem = dg.perfil("completo"), []
        while (s := dg.proximo_passo(rec)):
            ordem.append(s["recurso"])
            rec = dg.aplicar(rec, s["recurso"], s["para"])
        self.assertLess(ordem.index("ia_local"), ordem.index("avatar"))
        self.assertLess(ordem.index("avatar"), ordem.index("voz_saida"))

    def test_validar_em_portugues(self):
        with self.assertRaises(ValueError) as ctx:
            dg.aplicar(dg.perfil("medio"), "avatar", "sem_avatar")
        self.assertIn("não é um valor válido", str(ctx.exception))
        with self.assertRaises(ValueError):
            dg.validar({"avatar": "vrm"})

    def test_settings_ida_e_volta_e_arquivo_estragado_vira_none(self):
        rec = dg.perfil("leve")
        self.assertEqual(dg.de_settings({"downgrade": dg.para_settings(rec)}), rec)
        self.assertIsNone(dg.de_settings({}))
        self.assertIsNone(dg.de_settings({"downgrade": {"avatar": "hologram"}}))
        self.assertIsNone(dg.de_settings({"downgrade": "texto"}))

    def test_formatar_mostra_perfil_e_avisos(self):
        m = medida(8, 4, bateria_pct=15, carregando=False)
        txt = dg.formatar(m, dg.recomendar(m))
        self.assertIn("Perfil recomendado: medio", txt)
        self.assertIn("Bateria", txt)

    def test_o_downgrade_nunca_muda_sozinho(self):
        rec = dg.perfil("completo")
        copia = dict(rec)
        dg.proximo_passo(rec)
        dg.recomendar(medida())
        self.assertEqual(rec, copia)


if __name__ == "__main__":
    unittest.main()
