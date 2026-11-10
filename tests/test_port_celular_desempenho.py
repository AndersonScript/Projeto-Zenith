"""A tela de Desempenho (downgrade) do lado do Cérebro: medir, recomendar, aplicar e — principalmente — DESFAZER
exatamente o que estava antes. Nada muda sozinho: só quando a pessoa aplica.

    python -m unittest tests.test_port_celular_desempenho
"""
from __future__ import annotations

import copy
import unittest

from tests import _stubs
_stubs.instalar()

from brain import zenith_downgrade as dg
from brain.zenith_settings import ZenithSettings


def base():
    return {"voice_enabled": True, "ia_local_ativa": True,
            "permissions": {"microphone": "ask", "camera": "ask", "screen": "ask", "terminal": "ask"}}


def persistir(cfg, mudancas):
    """Imita o ZenithSettings.update (mescla; não apaga chaves) — o jeito real de gravar."""
    return ZenithSettings._deep_merge(copy.deepcopy(cfg), copy.deepcopy(mudancas))


class EfeitosReversiveisTests(unittest.TestCase):
    def test_rebaixar_a_voz_desliga_e_guarda_o_que_estava(self):
        r = dict(dg.perfil("completo"), voz_saida="desligada")
        m = dg.mudancas_nas_configuracoes(r, base())
        self.assertIs(m["voice_enabled"], False)
        self.assertIs(m[dg.GUARDADO]["voice_enabled"], True)
        self.assertEqual(m["downgrade"], r)
        self.assertNotIn("permissions", m)                       # não mexe no que não foi rebaixado

    def test_subir_de_novo_devolve_exatamente_o_que_era(self):
        original = base()
        original["permissions"]["camera"] = "always"             # um valor que NÃO é o padrão
        cfg = persistir(original, dg.mudancas_nas_configuracoes(dict(dg.perfil("completo"), visao="desligada"), original))
        self.assertEqual(cfg["permissions"]["camera"], "never")
        self.assertEqual(cfg["permissions"]["screen"], "never")
        cfg = persistir(cfg, dg.mudancas_nas_configuracoes(dg.perfil("completo"), cfg))
        self.assertEqual(cfg["permissions"]["camera"], "always")
        self.assertEqual(cfg["permissions"]["screen"], "ask")
        self.assertEqual(cfg["voice_enabled"], True)

    def test_um_never_que_a_pessoa_ja_tinha_continua_never_depois_de_subir(self):
        """O módulo nunca solta uma permissão sozinho: se ela mesma tinha posto 'never', continua 'never'."""
        original = base()
        original["permissions"]["microphone"] = "never"
        cfg = persistir(original, dg.mudancas_nas_configuracoes(dict(dg.perfil("completo"), voz_entrada="desligada"), original))
        cfg = persistir(cfg, dg.mudancas_nas_configuracoes(dg.perfil("completo"), cfg))
        self.assertEqual(cfg["permissions"]["microphone"], "never")

    def test_aplicar_duas_vezes_nao_sobrescreve_o_guardado_com_o_valor_ja_rebaixado(self):
        r = dict(dg.perfil("completo"), ia_local="desligada")
        cfg = persistir(base(), dg.mudancas_nas_configuracoes(r, base()))
        cfg = persistir(cfg, dg.mudancas_nas_configuracoes(r, cfg))             # a pessoa apertou Aplicar de novo
        cfg = persistir(cfg, dg.mudancas_nas_configuracoes(dg.perfil("completo"), cfg))
        self.assertIs(cfg["ia_local_ativa"], True)

    def test_ciclo_completo_volta_ao_original_nas_chaves_controladas(self):
        original = base()
        tudo_off = dict(dg.perfil("minimo"), voz_saida="desligada", voz_entrada="desligada", visao="desligada",
                        ia_local="desligada")
        cfg = persistir(original, dg.mudancas_nas_configuracoes(tudo_off, original))
        self.assertIs(cfg["voice_enabled"], False)
        self.assertIs(cfg["ia_local_ativa"], False)
        cfg = persistir(cfg, dg.mudancas_nas_configuracoes(dg.perfil("completo"), cfg))
        for chave in ("voice_enabled", "ia_local_ativa"):
            self.assertEqual(cfg[chave], original[chave])
        self.assertEqual(cfg["permissions"], original["permissions"])
        self.assertTrue(all(v is None for v in cfg[dg.GUARDADO].values()), "sobrou algo guardado")

    def test_avatar_graficos_fps_e_memoria_nao_tocam_nas_configuracoes_do_cerebro(self):
        r = dict(dg.perfil("completo"), avatar="padrao", qualidade_grafica="baixa", fps=20, memoria="leve")
        m = dg.mudancas_nas_configuracoes(r, base())
        self.assertEqual(set(m) - {"downgrade", dg.GUARDADO}, set())

    def test_configuracao_que_nao_existe_nao_e_inventada(self):
        m = dg.mudancas_nas_configuracoes(dict(dg.perfil("completo"), ia_local="desligada"), {"voice_enabled": True})
        self.assertIs(m["ia_local_ativa"], False)
        self.assertNotIn("ia_local_ativa", {k for k, v in m[dg.GUARDADO].items() if v is not None})

    def test_valores_do_godot_em_float_sao_aceitos_e_lixo_nao(self):
        r = dg.perfil("completo")
        r["fps"] = 60.0
        self.assertEqual(dg.validar(r)["fps"], 60)
        self.assertIsInstance(dg.validar(r)["fps"], int)
        for lixo in (True, 61, "60", None):
            with self.assertRaises(ValueError):
                dg.validar(dict(dg.perfil("completo"), fps=lixo))


class FalsoSettings:
    def __init__(self, cfg):
        self.settings = cfg
        self.gravacoes = 0

    def update(self, mudancas):
        self.settings = ZenithSettings._deep_merge(self.settings, copy.deepcopy(mudancas))
        self.gravacoes += 1

    def get(self, chave, padrao=None):
        return self.settings.get(chave, padrao)


class FalsaVoz:
    def __init__(self):
        self.chamadas = []

    def parar_de_falar(self):
        self.chamadas.append("falar")

    def parar_de_escutar(self):
        self.chamadas.append("escutar")


class FalsaPonte:
    def __init__(self):
        self.enviadas = []

    def send(self, d):
        self.enviadas.append(d)


def cerebro(cfg=None):
    from brain.zenith_headless import ZenithHeadlessBrain
    hl = ZenithHeadlessBrain.__new__(ZenithHeadlessBrain)
    hl.settings, hl.bridge, hl.interaction = FalsoSettings(cfg if cfg is not None else base()), FalsaPonte(), FalsaVoz()
    return hl


class CerebroDesempenhoTests(unittest.TestCase):
    def test_pedir_devolve_o_estado_completo_para_a_tela(self):
        hl = cerebro()
        hl._on_message({"action": "desempenho_pedir"})
        (msg,) = hl.bridge.enviadas
        self.assertEqual(msg["action"], "desempenho_estado")
        self.assertTrue(msg["ok"])
        self.assertFalse(msg["escolhido"])                      # ela ainda não escolheu nada
        self.assertEqual(set(msg["opcoes"]), set(dg.RECURSOS))
        self.assertEqual(msg["opcoes"]["avatar"], ["vrm", "padrao"])
        self.assertIn("ram_total_gb", msg["medida"])
        self.assertIn("Este celular", msg["texto"])
        dg.validar(msg["recursos"])
        self.assertEqual(hl.settings.gravacoes, 0)              # só medir e recomendar: NADA é gravado

    def test_aplicar_grava_para_o_corpo_para_a_voz_e_confirma(self):
        hl = cerebro()
        escolha = dict(dg.perfil("completo"), voz_saida="desligada", voz_entrada="desligada")
        hl._on_message({"action": "desempenho_aplicar", "recursos": escolha})
        self.assertIs(hl.settings.settings["voice_enabled"], False)
        self.assertEqual(hl.settings.settings["permissions"]["microphone"], "never")
        self.assertEqual(sorted(hl.interaction.chamadas), ["escutar", "falar"])      # parou na hora
        acoes = [m["action"] for m in hl.bridge.enviadas]
        self.assertEqual(acoes, ["desempenho_config", "desempenho_estado"])
        self.assertEqual(hl.bridge.enviadas[0]["recursos"], escolha)
        estado = hl.bridge.enviadas[1]
        self.assertTrue(estado["escolhido"])
        self.assertIn("Pronto", estado["mensagem"])

    def test_escolha_invalida_e_recusada_em_portugues_e_nada_e_gravado(self):
        hl = cerebro()
        hl._on_message({"action": "desempenho_aplicar", "recursos": dict(dg.perfil("completo"), avatar="sem_avatar")})
        (msg,) = hl.bridge.enviadas
        self.assertFalse(msg["ok"])
        self.assertIn("não é um valor válido", msg["mensagem"])
        self.assertEqual(hl.settings.gravacoes, 0)
        self.assertEqual(hl.interaction.chamadas, [])

    def test_voltar_ao_completo_devolve_as_configuracoes(self):
        hl = cerebro()
        hl._on_message({"action": "desempenho_aplicar", "recursos": dict(dg.perfil("completo"), voz_saida="desligada", ia_local="desligada")})
        hl.bridge.enviadas.clear()
        hl._on_message({"action": "desempenho_aplicar", "recursos": dg.perfil("completo")})
        self.assertIs(hl.settings.settings["voice_enabled"], True)
        self.assertIs(hl.settings.settings["ia_local_ativa"], True)
        self.assertEqual(hl.interaction.chamadas, ["falar"])     # só parou ao desligar; ao religar não "fala" nada

    def test_config_so_vai_ao_corpo_se_a_pessoa_ja_escolheu(self):
        hl = cerebro()
        hl._enviar_desempenho_config()
        self.assertEqual(hl.bridge.enviadas, [])
        hl2 = cerebro({"downgrade": dg.perfil("leve")})
        hl2._enviar_desempenho_config()
        self.assertEqual(hl2.bridge.enviadas, [{"action": "desempenho_config", "recursos": dg.perfil("leve")}])

    def test_arquivo_de_configuracao_estragado_nao_derruba_a_tela(self):
        hl = cerebro({"downgrade": {"avatar": "hologram"}})
        hl._on_message({"action": "desempenho_pedir"})
        self.assertTrue(hl.bridge.enviadas[0]["ok"])
        self.assertFalse(hl.bridge.enviadas[0]["escolhido"])


if __name__ == "__main__":
    unittest.main()
