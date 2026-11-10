"""Avatar simples do downgrade (v1.17): um personagem low-poly desenhado em código, no lugar do VRM em celulares fracos.

Confere o CONTRATO entre o Corpo (akira_body.gd), a tela de Desempenho, o Cérebro (zenith_downgrade.py) e o próprio avatar:
os nomes de estado/expressão que o Corpo aceita têm de ser conhecidos pelo avatar simples (senão ele ficaria mudo/inexpressivo
quando alguém trocar o nome de uma expressão num lado só). A parte visual foi conferida à parte, renderizando no Godot de PC
(tests/godot/verificar_godot.sh prints). Isto NÃO prova que o avatar simples agrada num celular real nem o compara ao VRM.

    python -m unittest tests.test_port_celular_avatar_simples
"""
from __future__ import annotations

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CORPO = RAIZ / "body" / "zenith"


def ler(p):
    if not p.exists():
        raise unittest.SkipTest(f"{p.name} não está neste pacote")
    return p.read_text(encoding="utf-8")


def corpo_da_funcao(fonte, assinatura):
    return fonte.split(assinatura)[1].split("\nfunc ")[0]


class AvatarSimples(unittest.TestCase):
    def test_o_avatar_conhece_todas_as_expressoes_que_o_corpo_aceita(self):
        body, av = ler(CORPO / "akira_body.gd"), ler(CORPO / "zenith_avatar_simples.gd")
        f = corpo_da_funcao(body, "func set_expression(expression_name: String):")
        nomes = set()
        for linha in re.findall(r'^\t\t((?:"[a-z_]+",?\s*)+):', f, re.M):
            nomes |= set(re.findall(r'"([a-z_]+)"', linha))
        self.assertGreaterEqual(len(nomes), 8, "não consegui extrair as expressões do akira_body.gd")
        for nome in sorted(nomes):
            self.assertIn(f'"{nome}"', av, f"o avatar simples não conhece a expressão '{nome}' que o Corpo aceita")

    def test_o_avatar_conhece_os_estados_de_vida_do_corpo(self):
        body, av = ler(CORPO / "akira_body.gd"), ler(CORPO / "zenith_avatar_simples.gd")
        f = corpo_da_funcao(body, "func set_life_state(state_name: String):")
        nomes = set(re.findall(r'"([a-z_]+)"', f))
        self.assertTrue({"thinking", "speaking", "greeting"} <= nomes | {"greeting"})
        for nome in sorted(nomes):
            self.assertIn(f'"{nome}"', av, f"o avatar simples não conhece o estado '{nome}'")

    def test_o_corpo_repassa_estado_e_expressao_ao_avatar_simples(self):
        body = ler(CORPO / "akira_body.gd")
        self.assertIn("_avatar_simples.set_life_state(state_name)", corpo_da_funcao(body, "func set_life_state(state_name: String):"))
        self.assertIn("_avatar_simples.set_expression(expression_name)", corpo_da_funcao(body, "func set_expression(expression_name: String):"))
        # estas chamadas vêm ANTES das do VRM: o avatar simples responde mesmo se o VRM nem existir
        f = corpo_da_funcao(body, "func set_expression(expression_name: String):")
        self.assertLess(f.index("_avatar_simples.set_expression"), f.index("if not mesh_instance"))

    def test_trocar_de_avatar_nao_descarrega_o_vrm_e_volta_com_false(self):
        f = corpo_da_funcao(ler(CORPO / "akira_body.gd"), "func usar_avatar_simples(ativo: bool) -> String:")
        self.assertIn("vrm.visible = false", f)
        self.assertIn("vrm.visible = true", f)
        self.assertIn("ResourceLoader.exists(caminho)", f)          # load() conferido: se o arquivo faltar, devolve frase em português
        self.assertNotIn("preload(", f)
        self.assertNotIn("queue_free()\n\t\tvrm", f)

    def test_a_tela_de_desempenho_aplica_o_avatar_e_o_seletor_nao_esta_mais_desligado(self):
        ap, pg = ler(CORPO / "zenith_desempenho_aplicar.gd"), ler(CORPO / "zenith_desempenho_page.gd")
        self.assertIn('recursos.has("avatar")', ap)
        self.assertIn('== "padrao"', ap)
        self.assertIn("usar_avatar_simples", ap)
        self.assertNotIn("seletor.disabled = true", pg)

    def test_os_valores_de_avatar_sao_os_mesmos_no_cerebro_e_no_corpo(self):
        from brain import zenith_downgrade as d
        self.assertEqual(tuple(d.RECURSOS["avatar"]), ("vrm", "padrao"))
        self.assertEqual(d.PERFIS["minimo"]["avatar"], "padrao")       # o piso do downgrade é o avatar padrão, nunca "sem avatar"
        self.assertEqual(d.PERFIS["completo"]["avatar"], "vrm")
        self.assertIn('"padrao"', ler(CORPO / "zenith_desempenho_aplicar.gd"))


if __name__ == "__main__":
    unittest.main()
