"""
Testes das ideias do roadmap implementadas no v18 (tudo do lado Python — nenhuma
mexe no Godot): /pausar e /retomar, /modo, /lembrar, /diagnostico e /relatorio,
/diario, /memorias e /esquecer, /exportar_conversa, notas com #tag e CSV, limites
de anexo, e a trava de "a Ponte só escuta em localhost".

Rodam sem Godot, sem internet, sem áudio e sem as bibliotecas pesadas (tests/_stubs.py
injeta módulos de mentira onde faltam). Não escrevem nada na pasta config/ do projeto.

Rodar: python -m unittest tests.test_v18_ideias -v
"""
import ast
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import _stubs
_stubs.instalar()

from brain import zenith_commands as cmd
from brain import zenith_diag as diag
from brain import zenith_diario as diario
from brain import zenith_export as exportador
from brain import zenith_lembretes as lem
from brain import zenith_memoria_util as memutil
from brain import zenith_modos as modos
from brain import zenith_notes as notas
from brain import zenith_pausa as pausa
from brain import zenith_version

RAIZ = Path(__file__).resolve().parent.parent
SEGREDO = "sk-ABCDEFGHIJKLMNOPQRSTUVWX1234"


class FakeSettings:
    persona_name = "Zenith"
    user_name = "Anderson"

    def __init__(self, **dados):
        self.dados = dict(dados)

    def get(self, chave, padrao=None):
        v = self.dados.get(chave, padrao)
        return padrao if v is None else v

    def update(self, mudancas):
        self.dados.update(mudancas)


class Base(unittest.TestCase):
    def setUp(self):
        pausa._resetar()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # NENHUM teste pode tocar a pasta config/ de verdade
        self._p1 = mock.patch.object(notas, "_caminho_padrao", lambda: self.tmp / "notas.jsonl")
        self._p2 = mock.patch.object(cmd, "_pasta_exportacao", lambda: self.tmp / "exports")
        self._p1.start()
        self._p2.start()
        self.lembretes = lem.Lembretes(self.tmp / "lembretes.json")

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        self._tmp.cleanup()
        pausa._resetar()

    def comando(self, texto, **ctx):
        ctx.setdefault("settings", FakeSettings())
        ctx.setdefault("lembretes", self.lembretes)
        return cmd.tratar(texto, ctx)


# ======================================================================
class PausaTests(Base):
    def test_pausar_liga_e_pede_acao(self):
        r = self.comando("/pausar preciso focar")
        self.assertEqual(r["acao"], "pausar")
        self.assertTrue(pausa.ativo())
        self.assertIn("SILÊNCIO TOTAL", r["resposta"])

    def test_pausar_de_novo_nao_repete_efeitos(self):
        self.comando("/pausar")
        r = self.comando("/pausar")
        self.assertIsNone(r["acao"])
        self.assertIn("Modo silêncio total ativo", r["resposta"])

    def test_retomar(self):
        self.comando("/pausar")
        r = self.comando("/retomar")
        self.assertEqual(r["acao"], "retomar")
        self.assertFalse(pausa.ativo())
        self.assertIsNone(self.comando("/retomar")["acao"])      # já liberado

    def test_comandos_que_usam_ia_voz_ou_mic_ficam_bloqueados_em_silencio(self):
        self.comando("/pausar")
        for c in ("/diario", "/testar_voz", "/nota_voz"):
            r = self.comando(c)
            self.assertIsNone(r["acao"], c)
            self.assertIn("silêncio total", r["resposta"].lower(), c)

    def test_comandos_locais_seguem_funcionando_em_silencio(self):
        self.comando("/pausar")
        self.assertIn("Anotado", self.comando("/nota teste")["resposta"])
        self.assertIn("lembrete", self.comando("/lembretes")["resposta"].lower())
        self.assertIsNotNone(self.comando("/ajuda"))

    def test_estado_nao_persiste_em_disco(self):
        src = (RAIZ / "brain" / "zenith_pausa.py").read_text(encoding="utf-8")
        self.assertNotIn("open(", src)
        self.assertNotIn("write_text", src)


# ======================================================================
class ModosTests(Base):
    def test_normalizar_aceita_acento_caixa_e_apelido(self):
        self.assertEqual(modos.normalizar("Código"), "codigo")
        self.assertEqual(modos.normalizar("LAB"), "lab")
        self.assertEqual(modos.normalizar("estudar"), "estudo")
        self.assertEqual(modos.normalizar("off"), "normal")
        self.assertIsNone(modos.normalizar("xyz"))
        self.assertIsNone(modos.normalizar(""))

    def test_todo_modo_com_texto_declara_que_nao_relaxa_pilares(self):
        for nome in ("estudo", "lab", "codigo"):
            bloco = modos.prompt_extra(nome)
            self.assertIn("jamais relaxa os pilares fixos", bloco)
            self.assertIn("aprovação", bloco)
        self.assertEqual(modos.prompt_extra("normal"), "")
        self.assertEqual(modos.prompt_extra("inexistente"), "")

    def test_comando_modo_lista_e_troca(self):
        cfg = FakeSettings()
        self.assertIn("estudo", self.comando("/modo", settings=cfg)["resposta"])
        r = self.comando("/modo estudo", settings=cfg)
        self.assertEqual(cfg.dados["modo_atual"], "estudo")
        self.assertIn("Estudo", r["resposta"])
        self.comando("/modo normal", settings=cfg)
        self.assertEqual(cfg.dados["modo_atual"], "normal")

    def test_modo_desconhecido_nao_muda_nada(self):
        cfg = FakeSettings(modo_atual="lab")
        r = self.comando("/modo foguete", settings=cfg)
        self.assertEqual(cfg.dados["modo_atual"], "lab")
        self.assertIn("Não conheço", r["resposta"])

    def test_modo_entra_no_prompt_do_sistema_depois_dos_pilares(self):
        from brain.zenith_core import ZenithCore
        core = object.__new__(ZenithCore)
        core.settings = FakeSettings(modo_atual="lab", persona_description="x", user_pillars="y")
        prompt = core._build_system_prompt()
        self.assertIn("MODO LABORATÓRIO", prompt)
        self.assertGreater(prompt.index("MODO LABORATÓRIO"), prompt.index("PILARES FIXOS DO SISTEMA"))
        self.assertLess(prompt.index("MODO LABORATÓRIO"), prompt.index("PODERES DE AÇÃO"))
        core.settings = FakeSettings(modo_atual="normal")
        self.assertNotIn("MODO ", core._build_system_prompt().split("PODERES DE AÇÃO")[0].split("SECURITY")[-1][-400:])


# ======================================================================
AGORA = dt.datetime(2026, 10, 1, 14, 0, 0)   # quinta-feira


class LembretesInterpretarTests(unittest.TestCase):
    def q(self, texto):
        return lem.interpretar(texto, AGORA)

    def test_hora_simples_hoje_e_amanha_se_ja_passou(self):
        self.assertEqual(self.q("15:30 entregar relatório"), (dt.datetime(2026, 10, 1, 15, 30), "entregar relatório"))
        self.assertEqual(self.q("13:00 almoço")[0], dt.datetime(2026, 10, 2, 13, 0))

    def test_formatos_de_hora(self):
        for txt in ("7h30 x", "07:30 x", "às 7h30 x", "7 horas e 30 x"):
            if txt.startswith("7 horas"):
                continue
            self.assertEqual(self.q("amanhã " + txt)[0], dt.datetime(2026, 10, 2, 7, 30), txt)
        self.assertEqual(self.q("amanhã 8h")[0], dt.datetime(2026, 10, 2, 8, 0))

    def test_relativo(self):
        self.assertEqual(self.q("em 20min tirar o pão"), (AGORA + dt.timedelta(minutes=20), "tirar o pão"))
        self.assertEqual(self.q("em 2h reunião")[0], AGORA + dt.timedelta(hours=2))
        self.assertEqual(self.q("em 1h30 almoço")[0], AGORA + dt.timedelta(hours=1, minutes=30))
        self.assertEqual(self.q("em 45 minutos ligar")[0], AGORA + dt.timedelta(minutes=45))

    def test_dia_da_semana(self):
        self.assertEqual(self.q("sexta 14h reunião da IC"), (dt.datetime(2026, 10, 2, 14, 0), "reunião da IC"))
        self.assertEqual(self.q("quinta 10:00 x")[0], dt.datetime(2026, 10, 8, 10, 0))     # já passou hoje -> semana que vem
        self.assertEqual(self.q("quinta-feira 15h x")[0], dt.datetime(2026, 10, 1, 15, 0))
        self.assertEqual(self.q("sábado 9h x")[0], dt.datetime(2026, 10, 3, 9, 0))

    def test_datas(self):
        self.assertEqual(self.q("25/12 9h ligar pra vó"), (dt.datetime(2026, 12, 25, 9, 0), "ligar pra vó"))
        self.assertEqual(self.q("1/1 8h x")[0], dt.datetime(2027, 1, 1, 8, 0))               # já passou -> ano que vem
        self.assertEqual(self.q("05/10/2026 08:15 x")[0], dt.datetime(2026, 10, 5, 8, 15))
        self.assertEqual(self.q("2026-10-05 10:00 x")[0], dt.datetime(2026, 10, 5, 10, 0))
        self.assertEqual(self.q("depois de amanhã 9h x")[0], dt.datetime(2026, 10, 3, 9, 0))

    def test_mensagem_limpa_de_conectivos(self):
        self.assertEqual(self.q("16h30: pagar boleto")[1], "pagar boleto")
        self.assertEqual(self.q("às 16h de comprar leite")[1], "comprar leite")
        self.assertEqual(self.q("15:30")[1], "Lembrete")

    def test_erros_explicam(self):
        casos = {"": "Use assim", "texto sem hora": "Não achei a hora", "25:00 x": "não existe",
                 "12:75 x": "não existe", "31/02 9h x": "data não existe", "em 0min x": "maior que zero",
                 "hoje 9h x": "já passou", "05/10/2020 9h x": "já passaram"}
        for texto, trecho in casos.items():
            with self.assertRaises(lem.ErroLembrete, msg=texto) as ctx:
                self.q(texto)
            self.assertIn(trecho, str(ctx.exception), texto)


class LembretesArmazenamentoTests(Base):
    def test_persistem_entre_instancias_e_ordenam(self):
        self.lembretes.adicionar(AGORA + dt.timedelta(hours=3), "depois")
        self.lembretes.adicionar(AGORA + dt.timedelta(hours=1), "antes")
        outra = lem.Lembretes(self.tmp / "lembretes.json")
        self.assertEqual([d["texto"] for d in outra.pendentes()], ["antes", "depois"])

    def test_remover_por_numero_e_por_id(self):
        a = self.lembretes.adicionar(AGORA + dt.timedelta(hours=1), "a")
        self.lembretes.adicionar(AGORA + dt.timedelta(hours=2), "b")
        self.assertEqual(self.lembretes.remover("1")["texto"], "a")
        self.assertEqual(self.lembretes.remover("99"), None)
        self.assertEqual(len(self.lembretes.pendentes()), 1)
        c = self.lembretes.adicionar(AGORA + dt.timedelta(hours=5), "c")
        self.assertEqual(self.lembretes.remover(c["id"])["texto"], "c")

    def test_arquivo_corrompido_nao_derruba(self):
        (self.tmp / "lembretes.json").write_text("{isso nao é json", encoding="utf-8")
        self.assertEqual(self.lembretes.pendentes(), [])
        self.lembretes.adicionar(AGORA, "ainda funciona")
        self.assertEqual(len(self.lembretes.pendentes()), 1)

    def test_escrita_atomica_nao_deixa_tmp(self):
        self.lembretes.adicionar(AGORA, "x")
        self.assertEqual([p.name for p in self.tmp.glob("lembretes*")], ["lembretes.json"])

    def test_comandos_de_ponta_a_ponta(self):
        r = self.comando("/lembrar em 30min tirar o pão")
        self.assertIn("tirar o pão", r["resposta"])
        self.assertEqual(len(self.lembretes.pendentes()), 1)
        self.assertIn("tirar o pão", self.comando("/lembretes")["resposta"])
        self.assertIn("Apaguei", self.comando("/lembrete_apagar 1")["resposta"])
        self.assertEqual(self.lembretes.pendentes(), [])
        self.assertIn("Use assim", self.comando("/lembrar")["resposta"])


class AgendadorTests(Base):
    def _ag(self, callback, agora):
        return lem.Agendador(self.lembretes, callback, agora=lambda: agora)

    def test_dispara_so_o_que_venceu_e_remove(self):
        self.lembretes.adicionar(AGORA - dt.timedelta(minutes=1), "venceu")
        self.lembretes.adicionar(AGORA + dt.timedelta(hours=1), "futuro")
        vistos = []
        n = self._ag(lambda d, atraso: vistos.append((d["texto"], round(atraso))), AGORA).verificar()
        self.assertEqual(n, 1)
        self.assertEqual(vistos, [("venceu", 1)])
        self.assertEqual([d["texto"] for d in self.lembretes.pendentes()], ["futuro"])

    def test_callback_false_adia_sem_perder(self):
        self.lembretes.adicionar(AGORA - dt.timedelta(minutes=5), "adiado")
        ag = self._ag(lambda d, a: False, AGORA)
        self.assertEqual(ag.verificar(), 0)
        self.assertEqual(len(self.lembretes.pendentes()), 1)          # continua lá
        ag.callback = lambda d, a: True
        self.assertEqual(ag.verificar(), 1)

    def test_excecao_no_callback_nao_perde_o_lembrete(self):
        self.lembretes.adicionar(AGORA - dt.timedelta(minutes=5), "x")

        def quebra(d, a):
            raise RuntimeError("boom")
        self.assertEqual(self._ag(quebra, AGORA).verificar(), 0)
        self.assertEqual(len(self.lembretes.pendentes()), 1)

    def test_atrasado_por_zenith_fechado_dispara_ao_abrir(self):
        self.lembretes.adicionar(AGORA - dt.timedelta(hours=3), "dormiu")
        atrasos = []
        self._ag(lambda d, a: atrasos.append(round(a)), AGORA).verificar()
        self.assertEqual(atrasos, [180])

    def test_thread_start_stop(self):
        ag = lem.Agendador(self.lembretes, lambda d, a: True, intervalo=0.05)
        ag.start()
        ag.start()                                                     # idempotente
        self.lembretes.adicionar(dt.datetime.now() - dt.timedelta(seconds=1), "real")
        for _ in range(60):
            if not self.lembretes.pendentes():
                break
            import time
            time.sleep(0.05)
        ag.stop()
        self.assertEqual(self.lembretes.pendentes(), [])


# ======================================================================
class DiagnosticoTests(Base):
    def _pastas(self):
        return {"config": self.tmp / "c", "temporários": self.tmp / "t"}

    def test_testar_tudo_formata_e_nunca_mostra_chave(self):
        cfg = FakeSettings(gemini_key=SEGREDO, tavily_api_key=SEGREDO + "9", active_ai="gemini")
        res = diag.testar_tudo(cfg, rede=False, pastas=self._pastas())
        texto = diag.formatar(res)
        self.assertNotIn(SEGREDO, texto)
        self.assertIn("Chaves de IA", texto)
        self.assertIn("Gemini", texto)
        self.assertTrue(texto.startswith("🩺 Diagnóstico:"))
        self.assertTrue((self.tmp / "c").is_dir())                      # a checagem de pasta cria e remove o arquivo-teste
        self.assertEqual(list((self.tmp / "c").iterdir()), [])

    def test_sem_nenhuma_ia_e_erro(self):
        res = diag.testar_tudo(FakeSettings(), rede=False, pastas=self._pastas())
        chaves = next(r for r in res if r["nome"] == "Chaves de IA")
        self.assertEqual(chaves["status"], diag.ERRO)

    @unittest.skipIf(os.name == "nt", "o caminho /proc só existe no Linux (no Windows isso CRIAVA C:\\proc\\nao_pode_aqui)")
    def test_pasta_sem_permissao_vira_erro(self):
        r = diag._checar_pasta("x", Path("/proc/nao_pode_aqui"))
        self.assertEqual(r["status"], diag.ERRO)

    def test_uma_checagem_que_explode_nao_derruba_as_outras(self):
        with mock.patch.object(diag, "_checar_chaves", side_effect=RuntimeError("bug")):
            res = diag.testar_tudo(FakeSettings(), rede=False, pastas=self._pastas())
        chaves = next(r for r in res if r["nome"] == "Chaves de IA")
        self.assertEqual(chaves["status"], diag.AVISO)
        self.assertIn("bug", chaves["detalhe"])
        self.assertGreater(len(res), 8)

    def test_estado_mostra_silencio_total(self):
        pausa.pausar()
        res = diag.testar_tudo(FakeSettings(), rede=False, pastas=self._pastas())
        estado = next(r for r in res if r["nome"] == "Estado")
        self.assertEqual(estado["status"], diag.AVISO)
        self.assertIn("SILÊNCIO", estado["detalhe"])

    def test_anonimizar_caminhos_e_segredos(self):
        t = diag.anonimizar(rf"C:\Users\joao\AppData\x e /home/maria/y e senha=abc123 e {SEGREDO}")
        self.assertNotIn("joao", t)
        self.assertNotIn("maria", t)
        self.assertNotIn("abc123", t)
        self.assertNotIn(SEGREDO, t)
        self.assertIn(r"C:\Users\<usuario>", t)
        self.assertIn("/home/<usuario>", t)

    def test_relatorio_nao_vaza_nada_pessoal(self):
        (self.tmp / "zenith_log.txt").write_text(
            f"ok\nerro em C:\\Users\\joao\\x chave {SEGREDO}\n", encoding="utf-8")
        cfg = FakeSettings(gemini_key=SEGREDO, user_name="Fulano Secreto", persona_description="DESCRICAO-PRIVADA",
                           user_pillars="PILAR-PRIVADO", elevenlabs_key=SEGREDO, active_ai="gemini")
        rel = diag.relatorio(cfg, base_dir=self.tmp, rede=False, agora=AGORA, pastas=self._pastas())
        for proibido in (SEGREDO, "Fulano Secreto", "DESCRICAO-PRIVADA", "PILAR-PRIVADO", "joao"):
            self.assertNotIn(proibido, rel, proibido)
        self.assertIn(f"Zenith {zenith_version.VERSAO}", rel)   # sem fixar o número da versão
        self.assertIn("2026-10-01 14:00", rel)
        self.assertIn("sem chaves de API, sem conversas", rel)

    def test_comandos_pedem_acao_ao_cerebro(self):
        self.assertEqual(self.comando("/diagnostico")["acao"], "diagnostico")
        self.assertEqual(self.comando("/relatorio")["acao"], "relatorio")
        self.assertEqual(self.comando("/diario")["acao"], "diario")


# ======================================================================
class NotasTagsCsvTests(Base):
    def test_extrair_tags(self):
        self.assertEqual(notas.extrair_tags("#Exp3 tensão #lab e #exp3 de novo #ação-1"), ["exp3", "lab", "ação-1"])
        self.assertEqual(notas.extrair_tags("veja pagina#secao e http://x/#frag e # solto"), [])
        self.assertEqual(notas.extrair_tags(""), [])

    def test_adicionar_guarda_tags_e_filtra(self):
        notas.adicionar("#exp3 medi 4,98 V")
        notas.adicionar("sem tag nenhuma")
        notas.adicionar("#exp3 #lab de novo 5,01 V")
        self.assertEqual(len(notas.listar(10)), 3)
        self.assertEqual(len(notas.listar(10, tag="exp3")), 2)
        self.assertEqual(len(notas.listar(10, tag="#EXP3")), 2)
        self.assertEqual(notas.tags_usadas(), [("exp3", 2), ("lab", 1)])
        self.assertIn("com #exp3", notas.formatar(10, tag="exp3"))
        self.assertIn("Nenhuma nota com #zzz", notas.formatar(10, tag="zzz"))

    def test_notas_antigas_sem_campo_tags_continuam_funcionando(self):
        (self.tmp / "notas.jsonl").write_text(
            json.dumps({"ts": "2026-01-01T10:00:00-03:00", "texto": "velha #antiga", "origem": "texto"}) + "\n",
            encoding="utf-8")
        self.assertEqual(len(notas.listar(10, tag="antiga")), 1)

    def test_csv_formato_excel_ptbr(self):
        notas.adicionar("#exp3 medi 4,98 V; com ponto e vírgula")
        notas.adicionar("=1+1 tentativa de fórmula")
        destino = self.tmp / "n.csv"
        self.assertEqual(notas.exportar_csv(destino), 2)
        cru = destino.read_bytes()
        self.assertTrue(cru.startswith(b"\xef\xbb\xbf"))                  # BOM: acentos certos no Excel
        linhas = list(csv.reader(io.StringIO(cru.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(linhas[0], ["data", "hora", "origem", "tags", "texto"])
        self.assertEqual(linhas[1][3], "#exp3")
        self.assertIn("ponto e vírgula", linhas[1][4])                    # ';' dentro do texto não quebra coluna
        self.assertTrue(linhas[2][4].startswith("'="))                    # fórmula neutralizada
        self.assertEqual(notas.exportar_csv(self.tmp / "so_exp3.csv", tag="exp3"), 1)

    def test_comandos_notas_tags_csv(self):
        self.comando("/nota #exp3 medi 4,98 V")
        self.comando("/nota outra coisa")
        self.assertIn("#exp3 — 1 nota", self.comando("/tags")["resposta"])
        r = self.comando("/notas #exp3")
        self.assertIn("medi 4,98 V", r["resposta"])
        self.assertNotIn("outra coisa", r["resposta"])
        r = self.comando("/exportar_notas_csv #exp3")
        self.assertIn("1 nota(s)", r["resposta"])
        self.assertTrue(list((self.tmp / "exports").glob("zenith_notas_exp3_*.csv")))


# ======================================================================
class FakeColecao:
    """Imita o miolo da collection do ChromaDB usado em zenith_memoria_util."""

    def __init__(self):
        self.docs = {}

    def add(self, documents, metadatas, ids):
        for d, m, i in zip(documents, metadatas, ids):
            self.docs[i] = (d, m)

    def count(self):
        return len(self.docs)

    def get(self, include=None, **_):
        ids = list(self.docs)
        return {"ids": ids, "documents": [self.docs[i][0] for i in ids], "metadatas": [self.docs[i][1] for i in ids]}

    def delete(self, ids):
        for i in ids:
            self.docs.pop(i, None)


class MemoriaTests(Base):
    def setUp(self):
        super().setUp()
        self.col = FakeColecao()

    def test_guardar_resumo_marca_chat_summary(self):
        self.assertTrue(memutil.guardar_resumo(self.col, "  resumo do dia  "))
        (doc, meta), = self.col.docs.values()
        self.assertEqual(doc, "resumo do dia")
        self.assertEqual(meta["type"], "chat_summary")
        self.assertFalse(memutil.guardar_resumo(self.col, "   "))

    def test_listar_filtra_sem_acento_e_ordena(self):
        self.col.add(["Prova de Física amanhã"], [{"timestamp": "2026-10-01T10:00", "type": "fact"}], ["aaaa1111-x"])
        self.col.add(["conversa sobre café"], [{"timestamp": "2026-10-02T10:00", "type": "chat_raw"}], ["bbbb2222-x"])
        todos = memutil.listar_com_id(self.col)
        self.assertEqual([i["ref"] for i in todos], ["bbbb2222", "aaaa1111"])           # mais recente primeiro
        achados = memutil.listar_com_id(self.col, "fisica")
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["mem_type"], "fact")

    def test_esquecer_por_prefixo_unico(self):
        self.col.add(["a"], [{}], ["aaaa1111-x"])
        self.col.add(["b"], [{}], ["bbbb2222-x"])
        ok, msg = memutil.apagar_por_ref(self.col, "aaaa")
        self.assertTrue(ok)
        self.assertIn("Esqueci", msg)
        self.assertEqual(list(self.col.docs), ["bbbb2222-x"])

    def test_esquecer_recusa_curto_ambiguo_e_inexistente(self):
        self.col.add(["a"], [{}], ["aaaa1111-x"])
        self.col.add(["b"], [{}], ["aaaa2222-x"])
        self.assertFalse(memutil.apagar_por_ref(self.col, "aa")[0])
        ok, msg = memutil.apagar_por_ref(self.col, "aaaa")
        self.assertFalse(ok)
        self.assertIn("2 memórias", msg)
        self.assertFalse(memutil.apagar_por_ref(self.col, "zzzz")[0])
        self.assertEqual(len(self.col.docs), 2)                                      # nada foi apagado

    def test_comandos_memorias_e_esquecer(self):
        class Mem:
            collection = self.col

            def list_with_ids(s, termo="", limite=20):
                return memutil.listar_com_id(self.col, termo, limite)

            def forget(s, ref):
                return memutil.apagar_por_ref(self.col, ref)
        self.col.add(["gosta de café"], [{"timestamp": "2026-10-01T10:00", "type": "fact"}], ["cafe1234-x"])
        r = self.comando("/memorias", memory=Mem())
        self.assertIn("[cafe1234]", r["resposta"])
        self.assertIn("⭐", r["resposta"])
        self.assertIn("Esqueci", self.comando("/esquecer cafe1234", memory=Mem())["resposta"])
        self.assertIn("vazia", self.comando("/memorias", memory=Mem())["resposta"])
        self.assertIn("não está disponível", self.comando("/memorias")["resposta"])


# ======================================================================
class DiarioTests(Base):
    MSGS = [{"sender": "user", "text": "vamos montar o circuito"}, {"sender": "ai", "text": "bora"},
            {"sender": "user", "text": f"minha chave é {SEGREDO}"}, {"sender": "ai", "text": "não mostre isso"}]

    class Core:
        def __init__(self, resposta="Hoje montamos o circuito.", erro=None):
            self.resposta, self.erro, self.prompts = resposta, erro, []

        def _call_provider(self, prompt):
            self.prompts.append(prompt)
            if self.erro:
                raise RuntimeError(self.erro)
            return self.resposta

    class Mem:
        def __init__(self, ok=True):
            self.ok, self.guardado = ok, []

        def save_summary(self, t):
            self.guardado.append(t)
            return self.ok

    def test_sucesso_guarda_resumo_com_data(self):
        core, mem = self.Core(), self.Mem()
        r = diario.gerar(core, mem, self.MSGS, "Zenith", "Anderson", agora=AGORA)
        self.assertTrue(r["ok"], r)
        self.assertIn("📔 Diário de 01/10/2026 14:00", mem.guardado[0])
        self.assertIn("Hoje montamos o circuito.", mem.guardado[0])

    def test_segredos_nao_vao_pro_provedor(self):
        core = self.Core()
        diario.gerar(core, self.Mem(), self.MSGS, "Zenith", "Anderson")
        self.assertNotIn(SEGREDO, core.prompts[0])

    def test_conversa_curta_demais(self):
        r = diario.gerar(self.Core(), self.Mem(), self.MSGS[:2], "Zenith", "Anderson")
        self.assertFalse(r["ok"])
        self.assertIn("curta demais", r["mensagem"])

    def test_erro_do_provedor_e_falha_ao_guardar(self):
        self.assertIn("Não consegui", diario.gerar(self.Core(erro="503"), self.Mem(), self.MSGS, "A", "B")["mensagem"])
        r = diario.gerar(self.Core(), self.Mem(ok=False), self.MSGS, "A", "B")
        self.assertFalse(r["ok"])
        self.assertIn("não consegui guardar", r["mensagem"])
        self.assertFalse(diario.gerar(self.Core(resposta="  "), self.Mem(), self.MSGS, "A", "B")["ok"])

    def test_transcricao_pega_o_fim_da_conversa(self):
        muitas = [{"sender": "user", "text": f"mensagem {i} " + "x" * 500} for i in range(100)]
        t = diario.montar_transcricao(muitas, "Zenith", "Anderson")
        self.assertLessEqual(len(t), diario.MAX_CARACTERES + 100)
        self.assertIn("mensagem 99", t)
        self.assertNotIn("mensagem 0 ", t)


# ======================================================================
class ExportarConversaTests(Base):
    CONV = {"id": "c1", "title": "Teste de física", "messages": [
        {"sender": "user", "text": "oi", "ts": "2026-10-01T09:05:00"},
        {"sender": "ai", "text": f"olá!\nlinha dois\n\nsegredo {SEGREDO}", "ts": "2026-10-01T09:05:10"},
        {"sender": "user", "text": "tchau", "ts": "2026-10-02T10:00:00"},
        {"sender": "ai", "text": "", "ts": "2026-10-02T10:00:05"}]}

    def test_markdown(self):
        md = exportador.conversa_para_markdown(self.CONV, "Zenith", "Anderson")
        self.assertTrue(md.startswith("# Teste de física"))
        self.assertIn("## 2026-10-01", md)
        self.assertIn("## 2026-10-02", md)
        self.assertIn("**Anderson** · 09:05", md)
        self.assertIn("> olá!", md)
        self.assertIn("> linha dois", md)
        self.assertNotIn(SEGREDO, md)

    def test_exportar_conta_so_mensagens_com_texto(self):
        destino = self.tmp / "sub" / "c.md"
        self.assertEqual(exportador.exportar_conversa(self.CONV, destino), 3)
        self.assertTrue(destino.is_file())

    def test_nome_sugerido_seguro(self):
        n = exportador.nome_sugerido({"title": "a/b:c?*d"}, "20261001_0905")
        self.assertRegex(n, r"^zenith_conversa_[\w]+_20261001_0905\.md$")
        self.assertNotRegex(n, r"[/\\:?*]")

    def test_comando(self):
        with mock.patch("brain.zenith_history.get_conversation", return_value=self.CONV):
            r = self.comando("/exportar_conversa", conv_id="c1")
        self.assertIn("3 mensagem(ns)", r["resposta"])
        self.assertTrue(list((self.tmp / "exports").glob("zenith_conversa_*.md")))
        self.assertIn("conversa ativa", self.comando("/exportar_conversa")["resposta"])


# ======================================================================
class HeadlessTests(Base):
    """Exercita zenith_headless.py de verdade (sem __init__: nada de ponte/IA/áudio)."""

    def setUp(self):
        super().setUp()
        from brain import zenith_headless as h
        self.h = h
        b = object.__new__(h.ZenithHeadlessBrain)
        b.settings = FakeSettings(proactive_enabled=True, voice_enabled=False)
        b.active_conv_id = "conv1"
        b._pending_approvals = {}
        b._pending_mic_approvals = set()
        b._proxima_fala_vira_nota = False
        b._mic_aprovado_nesta_sessao = False
        b.enviados = []
        b.bridge = mock.Mock(is_connected=True)
        b.bridge.send = b.enviados.append
        b.interaction = mock.Mock()
        b.proactive = mock.Mock()
        b.core = mock.Mock()
        b.lembretes = self.lembretes
        self.b = b
        self._hist = mock.patch.object(h.history, "append_message")
        self.append = self._hist.start()
        self._log = mock.patch.object(h.actionlog, "registrar")
        self.registrar = self._log.start()

    def tearDown(self):
        self._hist.stop()
        self._log.stop()
        super().tearDown()

    def textos(self):
        return [m.get("text", "") for m in self.b.enviados if m.get("action") == "chat_message"]

    def test_em_silencio_texto_normal_nao_vai_pra_ia(self):
        pausa.pausar()
        with mock.patch.object(self.h.threading, "Thread") as thread:
            self.b._handle_chat({"text": "oi Zenith"})
        thread.assert_not_called()
        self.assertTrue(any("silêncio total" in t.lower() for t in self.textos()))
        self.append.assert_not_called()                                  # nem entra no histórico

    def test_em_silencio_caminho_de_arquivo_parecido_com_comando_tambem_bloqueia(self):
        pausa.pausar()
        with mock.patch.object(self.h.threading, "Thread") as thread:
            self.b._handle_chat({"text": "/home/x/arquivo.txt o que é isso?"})
        thread.assert_not_called()

    def test_em_silencio_anexo_bloqueia(self):
        pausa.pausar()
        with mock.patch.object(self.h.threading, "Thread") as thread:
            self.b._handle_chat({"text": "", "attachment_path": "x.txt"})
        thread.assert_not_called()

    def test_retomar_funciona_em_silencio_e_libera(self):
        pausa.pausar()
        self.b._handle_chat({"text": "/retomar"})
        self.assertFalse(pausa.ativo())
        self.b.proactive.start.assert_called_once()
        with mock.patch.object(self.h.threading, "Thread") as thread:
            self.b._handle_chat({"text": "oi"})
        thread.assert_called_once()                                      # agora vai pra IA

    def test_pausar_cancela_pendentes_registra_e_para_tudo(self):
        pend = mock.Mock(kind="run_python", description="rodar script")
        self.b._pending_approvals = {"r1": pend}
        self.b._pending_mic_approvals = {"m1"}
        self.b._proxima_fala_vira_nota = True
        self.b._handle_chat({"text": "/pausar"})
        self.assertTrue(pausa.ativo())
        self.assertEqual(self.b._pending_approvals, {})
        self.assertEqual(self.b._pending_mic_approvals, set())
        self.assertFalse(self.b._proxima_fala_vira_nota)
        self.registrar.assert_called_once()
        self.assertEqual(self.registrar.call_args.args[:3], ("run_python", "rodar script", "negada"))
        self.assertIn("silêncio total", self.registrar.call_args.kwargs["detalhe"])
        self.b.interaction.parar_de_escutar.assert_called_once()
        self.b.interaction.parar_de_falar.assert_called_once()
        self.b.proactive.stop.assert_called_once()

    def test_aprovacao_antiga_clicada_depois_de_pausar_nao_executa_nada(self):
        pend = mock.Mock(kind="run_python", description="x")
        self.b._pending_approvals = {"r1": pend}
        self.b._handle_chat({"text": "/pausar"})
        self.b._handle_approval_response({"request_id": "r1", "approved": True})
        self.b.core.approve_action.assert_not_called()

    def test_resposta_da_ia_que_chega_depois_de_pausar_e_descartada(self):
        pausa.pausar()
        pend = mock.Mock()
        self.b._request_approval = mock.Mock()
        self.b._deliver_result({"text": "faça isso", "pending_action": pend})
        self.b._request_approval.assert_not_called()
        self.append.assert_not_called()
        self.assertEqual(self.textos(), [])

    def test_fala_espontanea_e_microfone_bloqueados(self):
        pausa.pausar()
        self.b._falar_espontaneamente()
        self.b.core.pensar.assert_not_called()
        self.b._handle_mic_start({})
        self.assertTrue(any("silêncio total" in t.lower() for t in self.textos()))
        self.assertIn({"action": "mic_state", "listening": False}, self.b.enviados)

    def test_disparar_lembrete(self):
        item = {"id": "a", "texto": "tirar o pão", "quando": "2026-10-01T14:00:00"}
        pausa.pausar()
        self.assertFalse(self.b._disparar_lembrete(item, 0))             # adia
        self.append.assert_not_called()
        pausa._resetar()
        self.assertTrue(self.b._disparar_lembrete(item, 0))
        self.assertIn("⏰ Lembrete: tirar o pão", self.textos()[0])
        self.assertTrue(any(m.get("action") == "notify" for m in self.b.enviados))
        self.append.assert_called_once()

    def test_lembrete_atrasado_explica(self):
        item = {"id": "a", "texto": "prova", "quando": "2026-10-01T09:00:00"}
        self.b._disparar_lembrete(item, 185)
        self.assertIn("passou 3h05min", self.textos()[0])

    def test_lembrete_sem_corpo_conectado_usa_notificacao_nativa(self):
        self.b.bridge.is_connected = False
        with mock.patch.object(self.h.notify, "notificar") as nativo:
            self.b._disparar_lembrete({"id": "a", "texto": "x", "quando": "2026-10-01T14:00:00"}, 0)
        nativo.assert_called_once()

    def test_anexo_imagem_grande_demais_e_recusado_sem_ler(self):
        img = self.tmp / "grande.png"
        img.write_bytes(b"0" * 5000)
        with mock.patch.object(self.h.ZenithHeadlessBrain, "_MAX_IMAGEM_BYTES", 1000):
            texto, dados, mime, erro = self.b._ler_anexo(str(img))
        self.assertIsNone(dados)
        self.assertIn("grande demais", erro)

    def test_anexo_de_texto_enorme_le_so_o_comeco(self):
        arq = self.tmp / "log.txt"
        arq.write_text("a" * 100_000, encoding="utf-8")
        with mock.patch("builtins.open", wraps=open) as aberto:
            texto, _, _, erro = self.b._ler_anexo(str(arq))
        self.assertIsNone(erro)
        self.assertIn("cortado", texto)
        self.assertLess(len(texto), 20_500)
        self.assertTrue(aberto.called)

    def test_anexo_pequeno_continua_inteiro(self):
        arq = self.tmp / "nota.txt"
        arq.write_text("conteúdo curto", encoding="utf-8")
        texto, _, _, erro = self.b._ler_anexo(str(arq))
        self.assertIsNone(erro)
        self.assertIn("conteúdo curto", texto)
        self.assertNotIn("cortado", texto)

    def test_rodar_diario_usa_memoria_e_manda_resultado(self):
        self.b.core.memory.save_summary.return_value = True
        self.b.core._call_provider.return_value = "Dia produtivo."
        self.b.settings.persona_name = "Zenith"
        self.b.settings.user_name = "Anderson"
        msgs = [{"sender": "user", "text": "a"}, {"sender": "ai", "text": "b"}, {"sender": "user", "text": "c"}]
        with mock.patch.object(self.h.history, "get_conversation", return_value={"messages": msgs}):
            self.b._rodar_diario()
        self.assertIn("Diário guardado", self.textos()[0])
        self.b.core.memory.save_summary.assert_called_once()


# ======================================================================
class SmartAppControlTests(Base):
    """Controle Inteligente de Aplicativos: detecção + avisos (nada disso toca o Windows de verdade)."""

    def _estado(self, valor, windows=True):
        with mock.patch.object(diag.os, "name", "nt" if windows else "posix"), \
             mock.patch.object(diag, "_ler_valor_sac", return_value=valor):
            return diag.estado_controle_inteligente()

    def test_interpretacao_dos_valores(self):
        self.assertEqual(self._estado(1)[0], "ligado")
        self.assertEqual(self._estado(2)[0], "avaliacao")
        self.assertEqual(self._estado(0)[0], "desligado")
        self.assertEqual(self._estado(None)[0], "desconhecido")
        cod, txt = self._estado(7)
        self.assertEqual(cod, "desconhecido")
        self.assertIn("7", txt)
        self.assertEqual(self._estado(1, windows=False)[0], "nao_windows")

    def test_leitura_do_registro_fora_do_windows_nao_quebra(self):
        with mock.patch.object(diag.os, "name", "posix"):
            self.assertIsNone(diag._ler_valor_sac())

    def test_diagnostico_avisa_quando_ligado_e_explica(self):
        with mock.patch.object(diag, "estado_controle_inteligente",
                               return_value=("ligado", "LIGADO — bloqueia programas sem assinatura digital")):
            item = diag._checar_controle_inteligente()
        self.assertEqual(item["status"], diag.AVISO)
        self.assertIn("NOTES_ANTIVIRUS.md", item["detalhe"])
        self.assertIn("sem assinatura", item["detalhe"])

    def test_diagnostico_ok_quando_desligado_ou_fora_do_windows(self):
        for cod in ("desligado", "nao_windows", "desconhecido"):
            with mock.patch.object(diag, "estado_controle_inteligente", return_value=(cod, "x")):
                self.assertEqual(diag._checar_controle_inteligente()["status"], diag.OK, cod)

    def test_testar_tudo_inclui_a_checagem_e_ela_pode_falhar_sem_derrubar(self):
        pastas = {"config": self.tmp / "c"}
        res = diag.testar_tudo(FakeSettings(), rede=False, pastas=pastas)
        self.assertTrue(any(r["nome"] == "Controle Inteligente de Aplicativos" for r in res))
        with mock.patch.object(diag, "_checar_controle_inteligente", side_effect=RuntimeError("bug")):
            res = diag.testar_tudo(FakeSettings(), rede=False, pastas=pastas)
        item = next(r for r in res if r["nome"] == "Controle Inteligente de Aplicativos")
        self.assertEqual(item["status"], diag.AVISO)

    def test_importacao_explica_o_bloqueio_quando_godot_nao_abre(self):
        from brain import zenith_vrm_import as vi
        with mock.patch.object(diag, "estado_controle_inteligente", return_value=("ligado", "x")):
            self.assertIn("Controle Inteligente", vi._dica_bloqueio())
        with mock.patch.object(diag, "estado_controle_inteligente", return_value=("desligado", "x")):
            self.assertEqual(vi._dica_bloqueio(), "")
        with mock.patch.object(diag, "estado_controle_inteligente", side_effect=RuntimeError("x")):
            self.assertEqual(vi._dica_bloqueio(), "")


class LauncherCorpoBloqueadoTests(unittest.TestCase):
    """O launcher precisa AVISAR NA TELA quando o Windows barra o Corpo (antes só escrevia no log)."""

    @classmethod
    def setUpClass(cls):
        import importlib
        import os
        os.environ["ZENITH_TESTE"] = "1"
        cls.launcher = importlib.import_module("zenith_launcher")

    def setUp(self):
        self.avisos = []
        # NUNCA instanciar o ZenithSettings de verdade aqui: o construtor grava config/settings.json do projeto
        import brain.zenith_settings as zs

        class _SettingsFalso:
            def get(self, chave, padrao=None):
                return padrao
        self._s = mock.patch.object(zs, "ZenithSettings", _SettingsFalso)
        self._s.start()
        self._p = mock.patch.object(self.launcher, "_avisar_na_tela", lambda t, x: self.avisos.append((t, x)))
        self._p.start()
        # só o caminho recomendado (body/zenith/export/Zenith.exe) "existe"
        self._f = mock.patch("os.path.isfile", lambda p: str(p).replace("\\", "/").endswith("export/Zenith.exe"))
        self._f.start()

    def tearDown(self):
        self._p.stop()
        self._f.stop()
        self._s.stop()

    def test_popen_levanta_oserror_avisa_e_devolve_none(self):
        erro = OSError("bloqueado")
        erro.winerror = 4551
        with mock.patch.object(self.launcher.subprocess, "Popen", side_effect=erro):
            proc, caminho = self.launcher._launch_godot_body()
        self.assertIsNone(proc)
        self.assertEqual(caminho, "")
        self.assertEqual(len(self.avisos), 1)
        self.assertIn("bloqueou", self.avisos[0][0])
        self.assertIn("4551", self.avisos[0][1])
        self.assertIn("NOTES_ANTIVIRUS.md", self.avisos[0][1])

    def test_corpo_que_fecha_logo_depois_de_abrir_avisa(self):
        fake = mock.Mock()
        fake.wait.return_value = 3221225781
        with mock.patch.object(self.launcher.subprocess, "Popen", return_value=fake):
            proc, caminho = self.launcher._launch_godot_body()
        self.assertIs(proc, fake)
        self.assertEqual(len(self.avisos), 1)
        self.assertIn("fechou", self.avisos[0][0])
        self.assertIn("3221225781", self.avisos[0][1])

    def test_corpo_normal_nao_gera_aviso(self):
        fake = mock.Mock()
        fake.wait.side_effect = self.launcher.subprocess.TimeoutExpired("x", 4)
        with mock.patch.object(self.launcher.subprocess, "Popen", return_value=fake):
            proc, caminho = self.launcher._launch_godot_body()
        self.assertIs(proc, fake)
        self.assertEqual(self.avisos, [])

    def test_texto_menciona_o_controle_inteligente_so_quando_ligado(self):
        from brain import zenith_diag
        with mock.patch.object(zenith_diag, "estado_controle_inteligente", return_value=("ligado", "x")):
            self.assertIn("CONTROLE INTELIGENTE", self.launcher._texto_corpo_bloqueado("d"))
        with mock.patch.object(zenith_diag, "estado_controle_inteligente", return_value=("desligado", "x")):
            self.assertNotIn("CONTROLE INTELIGENTE", self.launcher._texto_corpo_bloqueado("d"))

    # ---- plano B: abrir o Corpo pelo editor oficial do Godot ----
    def _env(self, godot="C:/Godot/Godot_v4.7.1.exe", projeto="C:/Zenith/body/zenith"):
        return {"godot_bin": godot, "project_dir": projeto, "pck_destino": "", "export_preset": "x",
                "faltando": [], "log": ""}

    def _isdir_cache(self, com_cache=True):
        return lambda p: str(p).replace("\\", "/").endswith(".godot/imported") and com_cache

    def test_plano_b_salva_o_dia_quando_o_exe_exportado_e_bloqueado(self):
        erro = OSError("bloqueado")
        erro.winerror = 4551
        plano_b = mock.Mock()
        plano_b.wait.side_effect = self.launcher.subprocess.TimeoutExpired("x", 4)
        chamadas = []

        def popen(cmd, **kw):
            chamadas.append(cmd)
            if len(chamadas) == 1:
                raise erro
            return plano_b
        from brain import zenith_vrm_import as vi
        with mock.patch.object(self.launcher.subprocess, "Popen", side_effect=popen), \
             mock.patch.object(vi, "localizar_ambiente", return_value=self._env()), \
             mock.patch("os.path.isdir", self._isdir_cache(True)):
            proc, caminho = self.launcher._launch_godot_body()
        self.assertIs(proc, plano_b)
        self.assertEqual(caminho, "C:/Godot/Godot_v4.7.1.exe")
        self.assertEqual(chamadas[1], ["C:/Godot/Godot_v4.7.1.exe", "--path", "C:/Zenith/body/zenith"])
        self.assertEqual(self.avisos, [])                       # funcionou: ninguém precisa ser incomodado

    def test_plano_b_quando_o_exe_abre_e_fecha_logo(self):
        exportado = mock.Mock()
        exportado.wait.return_value = 1
        plano_b = mock.Mock()
        plano_b.wait.side_effect = self.launcher.subprocess.TimeoutExpired("x", 4)
        from brain import zenith_vrm_import as vi
        with mock.patch.object(self.launcher.subprocess, "Popen", side_effect=[exportado, plano_b]), \
             mock.patch.object(vi, "localizar_ambiente", return_value=self._env()), \
             mock.patch("os.path.isdir", self._isdir_cache(True)):
            proc, _ = self.launcher._launch_godot_body()
        self.assertIs(proc, plano_b)
        self.assertEqual(self.avisos, [])

    def test_plano_b_indisponivel_sem_godot_avisa_na_tela(self):
        erro = OSError("bloqueado")
        from brain import zenith_vrm_import as vi
        with mock.patch.object(self.launcher.subprocess, "Popen", side_effect=erro), \
             mock.patch.object(vi, "localizar_ambiente", return_value=self._env(godot="")):
            proc, _ = self.launcher._launch_godot_body()
        self.assertIsNone(proc)
        self.assertEqual(len(self.avisos), 1)

    def test_plano_b_sem_cache_do_projeto_nao_tenta(self):
        from brain import zenith_vrm_import as vi
        with mock.patch.object(self.launcher.subprocess, "Popen", side_effect=OSError("x")) as popen, \
             mock.patch.object(vi, "localizar_ambiente", return_value=self._env()), \
             mock.patch("os.path.isdir", self._isdir_cache(False)):
            proc, _ = self.launcher._launch_godot_body()
        self.assertIsNone(proc)
        self.assertEqual(popen.call_count, 1)                   # só a tentativa do exe exportado
        self.assertEqual(len(self.avisos), 1)

    def test_plano_b_que_tambem_fecha_logo_avisa(self):
        plano_b = mock.Mock()
        plano_b.wait.return_value = 2
        from brain import zenith_vrm_import as vi
        with mock.patch.object(self.launcher.subprocess, "Popen", side_effect=[OSError("x"), plano_b]), \
             mock.patch.object(vi, "localizar_ambiente", return_value=self._env()), \
             mock.patch("os.path.isdir", self._isdir_cache(True)):
            proc, _ = self.launcher._launch_godot_body()
        self.assertIsNone(proc)
        self.assertEqual(len(self.avisos), 1)

    def test_importar_o_launcher_nao_criou_log_no_projeto(self):
        self.assertFalse((RAIZ / "zenith_log.txt").exists())


# ======================================================================
class GatekeeperVetoTests(unittest.TestCase):
    """Comandos que NEM COM APROVAÇÃO passam (camada determinística, independe da IA)."""

    @classmethod
    def setUpClass(cls):
        from brain.zenith_gatekeeper import DeterministicGuard
        cls.guard = DeterministicGuard("Anderson")

    def test_destrutivos_e_adulteracao_de_seguranca_sao_vetados(self):
        vetar = [
            ("terminal", "cipher /w:C:"), ("terminal", "rd /s /q C:\\x"), ("terminal", "del C:\\pasta\\* /s /q"),
            ("terminal", "Format-Volume -DriveLetter D"), ("terminal", "wbadmin delete catalog"),
            ("terminal", "Remove-Item C:\\ -Recurse -Force"), ("terminal", "Remove-Item -Recurse -Force 'D:\\'"),
            ("terminal", "net user hacker 123 /add"),
            ("terminal", "Add-MpPreference -ExclusionPath C:\\Zenith"),
            ("terminal", "Set-MpPreference -DisableRealtimeMonitoring $true"),
            ("terminal", "sc stop WinDefend"), ("terminal", "netsh advfirewall set allprofiles state off"),
            ("terminal", "powershell -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQA"),
            ("python", "import subprocess\nsubprocess.run('shutdown /s')"),
            ("python", "import shutil, pathlib\nshutil.rmtree(pathlib.Path.home())"),
            ("python", "os.system('powershell Add-MpPreference -ExclusionPath C:/')"),
        ]
        for tipo, conteudo in vetar:
            self.assertIsNotNone(self.guard.check_action(tipo, conteudo), conteudo)

    def test_o_padrao_cipher_antigo_nunca_casava_no_comeco_do_comando(self):
        self.assertIsNotNone(self.guard.check_action("terminal", "cipher /w:D"))

    def test_uso_normal_nao_e_vetado(self):
        liberar = [
            ("terminal", "dir"), ("terminal", "python script.py"), ("terminal", "pip install requests"),
            ("terminal", "del arquivo.txt"), ("terminal", "Remove-Item .\\temp\\x.txt"),
            ("terminal", "Remove-Item .\\temp -Recurse"),
            ("terminal", "Remove-Item C:\\Zenith\\creations\\teste.txt -Recurse"),
            ("terminal", "net use Z: \\\\servidor\\pasta"), ("terminal", "git status"), ("terminal", "ipconfig /all"),
            ("terminal", "powershell Get-Process"), ("terminal", "powershell -File x.ps1"),
            ("python", "print('olá')"), ("python", "import shutil; shutil.rmtree('temp_dir')"),
        ]
        for tipo, conteudo in liberar:
            self.assertIsNone(self.guard.check_action(tipo, conteudo), conteudo)


class AvisoInicialTests(Base):
    def test_texto_cobre_o_essencial(self):
        from brain import zenith_boas_vindas as bv
        for trecho in ("NUNCA executo", "/pausar", "/retomar", "nuvem", "só uma vez", "antivírus"):
            self.assertIn(trecho, bv.TEXTO)

    def test_aparece_uma_vez_so(self):
        from brain import zenith_headless as h
        b = object.__new__(h.ZenithHeadlessBrain)
        b.settings = FakeSettings()
        b.enviados = []
        b.bridge = mock.Mock()
        b.bridge.send = b.enviados.append
        b._mostrar_aviso_inicial()
        b._mostrar_aviso_inicial()
        textos = [m["text"] for m in b.enviados if m.get("action") == "chat_message"]
        self.assertEqual(len(textos), 1)
        self.assertTrue(b.settings.dados["aviso_inicial_visto"])

    def test_nao_aparece_se_ja_visto_ou_se_as_configuracoes_quebram(self):
        from brain import zenith_boas_vindas as bv
        self.assertFalse(bv.deve_mostrar(FakeSettings(aviso_inicial_visto=True)))
        self.assertFalse(bv.deve_mostrar(object()))

    def test_chave_tem_padrao_falso(self):
        from brain.zenith_settings import DEFAULT_SETTINGS
        self.assertIs(DEFAULT_SETTINGS["aviso_inicial_visto"], False)


class BuscaDoGodotNasRaizesTests(unittest.TestCase):
    def test_fora_do_windows_nao_varre_nada(self):
        from brain import zenith_vrm_import as vi
        with mock.patch.object(vi.os, "name", "posix"):
            self.assertEqual(vi._achar_godot_nas_raizes(), [])

    def test_no_windows_so_olha_pastas_godot_na_raiz(self):
        from brain import zenith_vrm_import as vi
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            (raiz / "Godot_v4.7.1").mkdir()
            (raiz / "Godot_v4.7.1" / "Godot_v4.7.1-stable_win64.exe").write_text("x")
            (raiz / "Windows").mkdir()
            (raiz / "Windows" / "Godot_falso.exe").write_text("x")      # fora de "Godot*": nunca é olhada
            with mock.patch.object(vi.os, "name", "nt"), \
                 mock.patch.object(vi, "Path", lambda x: raiz if str(x).startswith("C:") else Path("/nao/existe/__")), \
                 mock.patch.object(vi, "_parece_godot", lambda p: p.suffix == ".exe" and p.name.lower().startswith("godot")):
                achados = vi._achar_godot_nas_raizes()
        self.assertEqual([p.name for p in achados], ["Godot_v4.7.1-stable_win64.exe"])


# ======================================================================
class SegurancaRegressaoTests(unittest.TestCase):
    def test_ponte_so_escuta_em_localhost(self):
        """Trava de regressão (roadmap 4.4.1-b): se alguém trocar o host da Ponte por
        0.0.0.0 / '' / outro IP, este teste quebra."""
        src = (RAIZ / "brain" / "zenith_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("0.0.0.0", src)
        self.assertNotRegex(src, r"serve\(\s*[^,]+,\s*(\"\"|'')")
        arvore = ast.parse(src)
        hosts = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and getattr(no.func, "attr", "") == "serve":
                self.assertGreaterEqual(len(no.args), 2)
                alvo = no.args[1]
                self.assertIsInstance(alvo, ast.Constant, "o host da Ponte deve ser uma constante literal")
                hosts.append(alvo.value)
        self.assertTrue(hosts, "não achei websockets.serve(...) na Ponte")
        for h in hosts:
            self.assertIn(h, ("localhost", "127.0.0.1", "::1"))

    def test_versao_unica(self):
        self.assertRegex(zenith_version.VERSAO, r"^v\d+")
        self.assertIn(zenith_version.VERSAO, zenith_version.texto())

    def test_chave_nova_de_modo_tem_padrao(self):
        from brain.zenith_settings import DEFAULT_SETTINGS
        self.assertEqual(DEFAULT_SETTINGS["modo_atual"], "normal")


if __name__ == "__main__":
    unittest.main()
