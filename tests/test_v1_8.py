"""v1.8 — a conexão Cérebro↔Corpo caía em laço com conversas longas (WebSocket 1009 "Message too big").

O que aconteceu de verdade: a conversa de boas-vindas tinha ~76 KB; o WebSocketPeer do Godot recusa
por padrão qualquer mensagem acima de 64 KiB e, ao receber uma, FECHA a conexão. O Corpo
reconectava, levava a mesma mensagem grande e caía de novo — a janela ficava "desconectado",
com o seletor de IA e a lista de conversas vazios, porque as configurações nunca chegavam.

Aqui não roda Godot nem rede: o que estes testes travam é justamente o que estava errado e o
que ninguém veria voltar — o teto de mensagem do Corpo (que é dele, não do Cérebro) e o teto
do servidor Python, que cortava em 1 MiB.
"""
import asyncio
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests import _stubs                      # noqa: E402
_stubs.instalar()                             # falsifica google.genai etc. — nenhum teste usa rede

CONECTOR = RAIZ / "body/zenith/brain_connector.gd"
MIB = 1024 * 1024


def texto_do_conector() -> str:
    return CONECTOR.read_text(encoding="utf-8")


def teto_do_corpo(texto: str = "") -> int:
    """Lê o valor de `const TAMANHO_MAXIMO_MENSAGEM := ...` no brain_connector.gd."""
    m = re.search(r"const\s+TAMANHO_MAXIMO_MENSAGEM\s*:=\s*([0-9_*\s]+)", texto or texto_do_conector())
    if not m:
        raise AssertionError("o Corpo não define TAMANHO_MAXIMO_MENSAGEM (o teto de 64 KiB voltou)")
    return int(eval(m.group(1).replace("_", ""), {"__builtins__": {}}))


class BufferDoCorpoTests(unittest.TestCase):
    def test_o_corpo_aumenta_o_teto_antes_de_conectar(self):
        """Sem isto, o Godot fecha a conexão (1009) em toda mensagem acima de 64 KiB."""
        t = texto_do_conector()
        self.assertGreaterEqual(teto_do_corpo(t), 8 * MIB)
        self.assertIn("websocket.inbound_buffer_size = TAMANHO_MAXIMO_MENSAGEM", t)
        self.assertIn("websocket.outbound_buffer_size = TAMANHO_MAXIMO_MENSAGEM", t)

    def test_o_teto_vale_antes_do_primeiro_connect(self):
        """Ajustar o buffer DEPOIS de conectar não serve de nada: a primeira mensagem já cai."""
        t = texto_do_conector()
        self.assertLess(t.index("inbound_buffer_size = TAMANHO_MAXIMO_MENSAGEM"),
                        t.index("connect_to_url"))

    def test_a_maior_conversa_de_verdade_cabe(self):
        """A conversa que derrubava a janela tinha ~76 KB; o teto tem que ser folgado."""
        self.assertGreater(teto_do_corpo(), 200_000)

    def test_o_corpo_continua_reconectando_se_cair(self):
        """A correção não pode ter desligado a rede de segurança: caiu, tenta de novo."""
        t = texto_do_conector()
        self.assertIn("_reconnect_cooldown", t)
        self.assertIn("STATE_CLOSED", t)
        self.assertIn("_try_connect()", t)


class ServidorDoCerebroTests(unittest.TestCase):
    def test_o_servidor_aceita_mensagem_maior_que_1_mib(self):
        """O `websockets` corta em 1 MiB por padrão: um quadro do TFT ou uma imagem fechava a conexão."""
        from brain import zenith_bridge as B

        capturado = {}

        class _ServidorFalso:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        async def _serve_falso(handler, host, port, **kw):
            capturado.update({"host": host, "port": port, **kw})
            return _ServidorFalso()

        async def _rodar():
            ponte = B.ZenithBridge.__new__(B.ZenithBridge)     # sem threads, sem porta, sem rede
            with mock.patch.object(B.websockets, "serve", _serve_falso), \
                 mock.patch("builtins.print"):
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(ponte._start_server(), timeout=0.05)

        asyncio.run(_rodar())
        self.assertEqual(capturado.get("port"), 8765)
        self.assertIn("max_size", capturado, "o servidor voltou ao teto padrão de 1 MiB")
        self.assertGreaterEqual(capturado["max_size"], 8 * MIB)
        self.assertEqual(capturado.get("ping_interval"), 20)    # a rede de segurança continua ligada


# ---------------------------------------------------------------- Gemini: nome de modelo aposentado
class ClienteGeminiFalso:
    """Só aceita os modelos de `validos`; para o resto responde o mesmo 404 que o Google mandou:
    "models/gemini-2.5-flash is no longer available to new users". `list()` devolve o que a conta enxerga."""

    def __init__(self, validos, ids):
        self.validos = set(validos)
        self.ids = list(ids)
        self.chamadas = []
        cliente = self

        class Models:
            def generate_content(self, **kw):
                nome = kw.get("model")
                cliente.chamadas.append(nome)
                if nome not in cliente.validos:
                    raise RuntimeError(
                        "404 NOT_FOUND: models/%s is no longer available to new users. Please update your code" % nome)
                return SimpleNamespace(text="resposta de " + nome)

            def list(self):
                return [SimpleNamespace(name=i) for i in cliente.ids]

        self.models = Models()


def core_gemini(cliente, escolhido="gemini-2.5-flash"):
    """Core sem o __init__ pesado: só o que a chamada ao Gemini usa."""
    from brain import zenith_core
    c = zenith_core.ZenithCore.__new__(zenith_core.ZenithCore)
    c.client = cliente
    c.settings = {"gemini_modelo": escolhido}
    c._modelo_em_uso = ""
    c._msg_atual = "oi"
    c._gemini_contents = lambda *a, **k: []
    c._gemini_config = lambda modelo, msg, sem: {"modelo": modelo}
    c._portao = lambda: None
    return c


class ModeloAposentadoTests(unittest.TestCase):
    """O caso real de 24/10: a chave é boa, mas `gemini-2.5-flash` não existe mais para conta nova."""

    def test_descobre_um_modelo_que_a_chave_enxerga_e_responde(self):
        cli = ClienteGeminiFalso(validos={"gemini-3.7-flash"}, ids=["models/gemini-3.7-flash"])
        c = core_gemini(cli)
        with mock.patch("builtins.print"):
            texto = c._gemini_chamar("oi")
        self.assertEqual(texto, "resposta de gemini-3.7-flash")
        self.assertEqual(c._modelo_em_uso, "gemini-3.7-flash")
        self.assertIn("gemini-3.7-flash", cli.chamadas)

    def test_a_segunda_mensagem_nao_repete_o_404(self):
        cli = ClienteGeminiFalso(validos={"gemini-3.7-flash"}, ids=["models/gemini-3.7-flash"])
        c = core_gemini(cli)
        with mock.patch("builtins.print"):
            c._gemini_chamar("oi")
            cli.chamadas.clear()
            c._gemini_chamar("de novo")
        self.assertEqual(cli.chamadas, ["gemini-3.7-flash"])   # acertou de primeira, sem repetir o nome velho

    def test_trocar_o_modelo_em_modelo_manda_mais_que_o_cache(self):
        cli = ClienteGeminiFalso(validos={"gemini-3.7-flash"}, ids=["models/gemini-3.7-flash"])
        c = core_gemini(cli)
        with mock.patch("builtins.print"):
            c._gemini_chamar("oi")
        c.settings["gemini_modelo"] = "gemini-3.7-flash"
        self.assertEqual(c._gemini_modelo(), "gemini-3.7-flash")

    def test_se_nem_a_descoberta_salvar_ela_avisa_em_vez_de_fingir(self):
        cli = ClienteGeminiFalso(validos=set(), ids=["models/gemini-3.7-flash"])
        c = core_gemini(cli)
        with mock.patch("builtins.print"):
            with self.assertRaises(RuntimeError):
                c._gemini_chamar("oi")

    def test_sem_lista_de_modelos_a_mensagem_original_sobe(self):
        class SemLista(ClienteGeminiFalso):
            def __init__(self):
                super().__init__(validos=set(), ids=[])

                class SoGenerate:
                    def generate_content(self, **kw):
                        raise RuntimeError("404 NOT_FOUND: unknown model")
                self.models = SoGenerate()
        c = core_gemini(SemLista())
        with mock.patch("builtins.print"):
            with self.assertRaises(RuntimeError) as ctx:
                c._gemini_chamar("oi")
        self.assertIn("404", str(ctx.exception))


class DadosResgatadosTests(unittest.TestCase):
    """v1.8 — o build guarda os dados do usuário; essa pasta não pode ir para a edição Pública.

    Ela carrega settings/conversas do dono (e o modelo de `config/ZENITH.md`, que fala do nome
    antigo): sem exclusão, o `--so-conferir` nunca dava OK depois de um build — e pior, a pasta
    inteira entrava no pacote público.
    """

    def test_a_pasta_de_dados_resgatados_fica_fora(self):
        from tools import preparar_publico as PP
        for rel in ("_dados_do_usuario_resgatados/config/settings.json",
                    "_dados_do_usuario_resgatados/config/ZENITH.md",
                    "_dados_do_usuario_resgatados/memory_db/x.db"):
            self.assertTrue(PP._excluir(Path(rel)), rel)

    def test_varredura_com_exclusao_nao_acusa_os_dados_resgatados(self):
        from tools import preparar_publico as PP
        d = Path(tempfile.mkdtemp(prefix="zenith_v18_"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / "brain").mkdir()
        (d / "brain" / "ok.py").write_text("print('oi')\n", encoding="utf-8")
        resgate = d / "_dados_do_usuario_resgatados" / "config"
        resgate.mkdir(parents=True)
        antigo = "Aki" + "ra"          # montado: este arquivo não pode conter o nome antigo nem no texto
        (resgate / "ZENITH.md").write_text(f"o que a sua {antigo} deve saber\n", encoding="utf-8")
        self.assertEqual(PP.varrer(d, respeitar_exclusoes=True)["erros"], [])
        self.assertTrue(PP.varrer(d)["erros"], "sem exclusão a varredura precisa continuar vendo")


if __name__ == "__main__":
    unittest.main()
