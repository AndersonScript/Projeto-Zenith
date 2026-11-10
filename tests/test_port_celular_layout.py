"""Layout de celular, fase 1 (v1.12): confere o CONTRATO entre zenith_layout_celular.gd e a ui_manager.gd.

Por quê: o layout acessa a ui_manager por NOME, de forma dinâmica (ui.get("sidebar")). Se alguém renomear uma variável
lá, o layout deixa de achar o nó e falha SEM erro de compilação. Este teste pega isso. Não há Godot no Windows do teste:
a parte visual foi conferida à parte (tests/godot/verificar_godot.sh), e isto NÃO prova que funciona num celular.

    python -m unittest tests.test_port_celular_layout
"""
from __future__ import annotations

import pathlib
import re
import unittest

CORPO = pathlib.Path(__file__).resolve().parent.parent / "body" / "zenith"
LAYOUT = CORPO / "zenith_layout_celular.gd"
UI = CORPO / "ui_manager.gd"


def ler(p):
    if not p.exists():
        raise unittest.SkipTest(f"{p.name} não está neste pacote")
    return p.read_text(encoding="utf-8")


class LayoutCelular(unittest.TestCase):
    def test_todo_no_que_o_layout_pede_pelo_nome_existe_na_ui_manager(self):
        layout, ui = ler(LAYOUT), ler(UI)
        pedidos = set(re.findall(r'ui\.get\("([A-Za-z_0-9]+)"\)', layout))
        pedidos |= {"sidebar", "_raiz_ui", "title_label", "move_btn", "atividade_lbl", "obs_btn", "parar_btn"}
        for nome in sorted(pedidos):
            self.assertRegex(ui, rf"(?m)^var {nome}\b", f"a ui_manager.gd não declara mais 'var {nome}' (o layout de celular depende dela)")

    def test_o_gancho_so_liga_no_celular_e_o_arquivo_e_opcional(self):
        ui, layout = ler(UI), ler(LAYOUT)
        self.assertEqual(ui.count("_aplicar_layout_celular()"), 2, "uma chamada no _ready + a definição")
        self.assertIn('_script_opcional("res://zenith_layout_celular.gd")', ui)   # load() conferido: se falhar, o PC abre igual
        self.assertIn("if not candidato.ativo():", ui)
        self.assertIn('OS.get_name() == "Android"', layout)
        self.assertIn('"--layout-celular"', layout)
        self.assertNotIn("preload(", layout + ui.split("func _aplicar_layout_celular")[1].split("\nfunc ")[0])

    def test_a_gaveta_nao_usa_posicao_fixa_entre_os_filhos_da_raiz(self):
        # erro da 1ª versão: a gaveta ficava por BAIXO do chat porque a aparência põe camadas no meio dos filhos
        layout = ler(LAYOUT)
        self.assertIn("linha_principal.get_index() + 1", layout)
        self.assertNotRegex(layout, r"raiz\.move_child\([^,]+,\s*[0-9]+\)")

    def test_os_botoes_parar_ganham_alvo_de_toque_e_ficam_acessiveis(self):
        layout = ler(LAYOUT)
        self.assertIn("ALVO_TOQUE", layout)
        for nome in ("atividade_lbl", "obs_btn", "parar_btn"):
            self.assertIn(f'"{nome}"', layout)

    def test_os_argumentos_de_teste_estao_documentados_no_cabecalho(self):
        topo = ler(LAYOUT).split("const ")[0]
        for arg in ("--layout-celular", "--celular-tela=", "--visual-gaveta", "--visual-atividade"):
            self.assertIn(arg, topo)


    # ---------- fase 2 (v1.14): cartões viram telas ----------
    def test_o_ponto_unico_que_mostra_cartoes_chama_o_layout(self):
        ui = ler(UI)
        corpo = ui.split("func _show_overlay(overlay: Control, card: Control):")[1].split("\nfunc ")[0]
        self.assertIn("layout_celular.preparar_cartao(card)", corpo)
        # a regra do projeto (tests/test_v1_6): _afastar_do_avatar(card) é a 1ª linha; o layout de celular vem DEPOIS dela
        self.assertLess(corpo.index("_afastar_do_avatar(card)"), corpo.index("layout_celular.preparar_cartao(card)"))
        self.assertEqual(ui.count("layout_celular.ligar_observador()"), 1)     # ligado no _ready, não no aplicar() adiado

    def test_os_cartoes_e_as_abas_que_a_fase_2_procura_existem(self):
        ui = ler(UI)
        for nome in ("settings_card", "settings_tabs", "settings_overlay", "memories_card", "projetos_card", "approval_card", "onboarding_card"):
            self.assertRegex(ui, rf"(?m)^var {nome}\b", f"a ui_manager.gd não declara mais 'var {nome}'")

    def test_cada_aba_das_configuracoes_tem_legenda_na_lista_do_celular(self):
        ui, layout = ler(UI), ler(LAYOUT)
        legendas = re.findall(r'^\t"([^"]+)": "', layout.split("const LEGENDAS")[1].split("}")[0], re.M)
        abas = len(re.findall(r"tabs\.add_child\(_settings_tab_", ui))
        self.assertEqual(len(legendas), abas, "uma aba nova nas Configurações precisa de legenda em LEGENDAS (zenith_layout_celular.gd)")

    def test_botoes_de_aprovar_e_negar_tem_alvo_de_toque_grande(self):
        layout = ler(LAYOUT)
        self.assertIn("_alvos_de_toque(card)", layout)
        self.assertIn("maxf(no.custom_minimum_size.y, 48.0)", layout)

    def test_as_regras_gerais_nao_encolhem_texto_de_botao_que_nao_ocupa_a_folga(self):
        layout = ler(LAYOUT)
        self.assertIn("elif ocupa_folga and not no.clip_text:", layout)      # só corta o botão que já ocupa a folga
        self.assertIn("_largura_minima_real", layout)                        # texto que quebra linha conta pequeno


if __name__ == "__main__":
    unittest.main()
