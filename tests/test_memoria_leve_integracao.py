"""Prova do port: o `ZenithMemory` do Zenith, SEM trocar o chromadb por nada falso, rodando no modo celular.

Com `ZENITH_PLATAFORMA=android`, o `zenith_memory` nem importa o chromadb e usa a memória leve (SQLite). Este teste
percorre o fluxo inteiro da memória nesse modo. Se um dia o `ZenithMemory` passar a usar um método do chromadb que a
coleção leve não tem, é ESTE teste que quebra — antes de quebrar no celular.

    python -m unittest tests.test_memoria_leve_integracao
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock


class Config(dict):
    pass


class ZenithMemoryNoCelular(unittest.TestCase):
    def setUp(self):
        self._pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self._pasta.cleanup)
        for patcher in (mock.patch.dict(os.environ, {"ZENITH_PLATAFORMA": "android"}),
                        mock.patch.dict(sys.modules)):          # sem valores = tira um retrato e devolve no fim
            patcher.start()
            self.addCleanup(patcher.stop)
        import brain
        atributo = getattr(brain, "zenith_memory", None)
        self.addCleanup(lambda: setattr(brain, "zenith_memory", atributo) if atributo is not None
                        else (hasattr(brain, "zenith_memory") and delattr(brain, "zenith_memory")))
        sys.modules.pop("brain.zenith_memory", None)
        try:
            self.mod = importlib.import_module("brain.zenith_memory")
        except Exception as e:                                  # repositório sem o zenith_memory (cópia parcial)
            self.skipTest(f"brain.zenith_memory não pôde ser importado aqui: {e}")
        self.mod.MEMORY_DIR = self._pasta.name
        self.m = self.mod.ZenithMemory(Config())
        self.addCleanup(lambda: self.m.collection.fechar())

    def test_no_celular_nao_importa_o_chromadb(self):
        self.assertIsNone(self.mod.chromadb)
        self.assertEqual(type(self.m.collection).__name__, "ColecaoLeve")

    def test_fluxo_completo(self):
        m = self.m
        m.save("Anderson", "Zenith", "me lembra que a apresentação na escola é na sexta", "Pode deixar.")
        m.save("Anderson", "Zenith", "qual o cardápio da cantina?", "Pão de queijo e suco.")
        m.save_fact("Anderson usa Godot 4.7 e Python no projeto Zenith")
        m.save_fact("Anderson usa Godot 4.7 e Python no projeto Zenith")        # repetido: não duplica
        m.save_fact("O carrinho usa um ESP32-S3 com tela TFT")
        self.assertEqual(m.collection.count(), 4)

        self.assertIn("escola", m.recall("quando é a apresentação na escola?").lower())
        self.assertIn("ESP32", m.recall("carrinho ESP32"))
        self.assertEqual(m.fatos_fixos().count("Godot"), 1)
        self.assertEqual(m.contagem_chat_raw(), 2)
        self.assertEqual(sorted(i["mem_type"] for i in m.list_recent()), ["chat_raw", "chat_raw", "fact", "fact"])

        ids, _ = m.lote_mais_antigo_para_resumir(limite=10)
        m.substituir_por_resumo(ids, "Resumo: conversas sobre escola e cantina.")
        self.assertEqual(sorted(i["mem_type"] for i in m.list_recent()), ["chat_summary", "fact", "fact"])
        self.assertEqual(m.contagem_chat_raw(), 0)

    def test_desfazer_e_esquecer(self):
        m = self.m
        novo_id = m.save("Anderson", "Zenith", "teste de cancelamento", "resposta cancelada")
        self.assertTrue(m.apagar_id(novo_id))
        self.assertEqual(m.collection.count(), 0)
        m.save_fact("segredo bobo para esquecer")
        itens = m.list_with_ids("segredo")
        self.assertEqual(len(itens), 1)
        m.forget(itens[0]["id"])
        self.assertEqual(m.collection.count(), 0)

    def test_memoria_persiste_entre_aberturas(self):
        self.m.save_fact("o Anderson mora em São Paulo")
        self.m.collection.fechar()
        de_novo = self.mod.ZenithMemory(Config())
        self.addCleanup(lambda: de_novo.collection.fechar())
        self.assertIn("São Paulo", de_novo.fatos_fixos())


if __name__ == "__main__":
    unittest.main()
