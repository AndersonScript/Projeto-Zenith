"""v1.5 — testes das tarefas T1 (ditado), T2 (modo conversa), T8 (comandos próprios) e T9 (atualização).



Nada aqui usa microfone, rede, Godot ou a pasta real de configuração: os motores, o reconhecedor,

o `obter` (HTTP) e a pasta de comandos são falsos/injetados.

"""

import hashlib

import json

import tempfile

import unittest

from pathlib import Path



from brain import zenith_atualizar as at

from brain import zenith_comandos_proprios as cp

from brain import zenith_commands as commands

from brain import zenith_ditado as ditado



RAIZ = Path(__file__).resolve().parent.parent





# ======================================================================

# T1 — ditado

# ======================================================================

class MotorFalso(ditado.MotorFluxo):

    """Motor de mentira: cada chamada de `alimentar` devolve o próximo texto da lista."""



    nome = "falso"



    def __init__(self, textos):

        self._textos = list(textos)

        self._fila = []

        self.fechado = False



    def alimentar(self, pcm16, taxa=16000):

        if self._textos:

            self._fila.append(("parcial", self._textos.pop(0)))



    def eventos(self):

        fila, self._fila = self._fila, []

        return fila



    def fechar(self):

        self.fechado = True





class ComandosDePontuacaoTests(unittest.TestCase):

    def test_virgula_e_ponto(self):

        self.assertEqual(ditado.formatar("ola mundo virgula tudo bem ponto"),

                         "Ola mundo, tudo bem.")



    def test_interrogacao_e_exclamacao(self):

        self.assertEqual(ditado.formatar("voce vem ponto de interrogacao"),

                         "Voce vem?")

        self.assertEqual(ditado.formatar("cuidado ponto de exclamacao"),

                         "Cuidado!")



    def test_nova_linha(self):

        self.assertEqual(ditado.formatar("primeira nova linha segunda"),

                         "Primeira" + chr(10) + "Segunda")



    def test_apagar_isso_tira_a_ultima_frase(self):

        self.assertEqual(ditado.formatar("primeira frase ponto segunda frase ponto apagar isso"),

                         "Primeira frase.")



    def test_apagar_isso_nao_quebra_texto_sem_ponto(self):

        self.assertEqual(ditado.aplicar_comandos("sem nada aqui apagar isso"), "")



    def test_maiuscula_depois_de_ponto(self):

        self.assertEqual(ditado.capitalizar("oi. tudo bem? sim! ok"), "Oi. Tudo bem? Sim! Ok")



    def test_texto_sem_comando_nao_muda_de_sentido(self):

        entrada = "a tensao medida foi 4,98 V e a corrente 0,2 A"

        self.assertEqual(ditado.formatar(entrada), "A tensao medida foi 4,98 V e a corrente 0,2 A")





class EstadoDitadoTests(unittest.TestCase):

    def test_estavel_so_cresce(self):

        estado = ditado.EstadoDitado()

        self.assertEqual(estado.atualizar("bom dia como")["stable"], "")

        self.assertEqual(estado.atualizar("bom dia como vai")["stable"], "Bom dia como")

        # Só entra no estável o que DUAS passadas seguidas concordam: "como" já vale, "vai" ainda não.

        self.assertEqual(estado.estavel, "Bom dia como")

        estado.atualizar("bom dia como vai de novo")    # terceira passada concorda em "vai"

        self.assertEqual(estado.estavel, "Bom dia como vai")

        antes = estado.estavel

        estado.atualizar("bom dia com voce")            # a nova passada discorda no fim

        self.assertTrue(estado.estavel.startswith(antes))

        self.assertEqual(estado.estavel, "Bom dia como vai")



    def test_cauda_muda_sem_mexer_no_estavel(self):

        estado = ditado.EstadoDitado()

        estado.atualizar("quero abrir o")

        a = estado.atualizar("quero abrir o navegador")

        self.assertEqual(a, {"stable": "Quero abrir o", "tail": "navegador"})

        b = estado.atualizar("quero abrir o bloco de notas")

        self.assertEqual(b["stable"], "Quero abrir o")

        self.assertEqual(b["tail"], "bloco de notas")



    def test_local_agreement_conta_o_prefixo_igual(self):

        self.assertEqual(ditado.local_agreement(["a", "b", "c"], ["a", "b", "d"]), 2)

        self.assertEqual(ditado.local_agreement([], ["a"]), 0)



    def test_finalizar_usa_a_correcao(self):

        estado = ditado.EstadoDitado()

        estado.atualizar("ola tudo bem")

        self.assertEqual(estado.finalizar("Ola, tudo bem."), "Ola, tudo bem.")





class DitadoTests(unittest.TestCase):

    def test_mensagens_do_contrato(self):

        enviadas = []

        d = ditado.Ditado(MotorFalso(["bom dia", "bom dia como", "bom dia como vai"]),

                          enviar=enviadas.append)

        for _ in range(3):

            d.alimentar(b"\x00\x01")

        self.assertTrue(enviadas)

        self.assertTrue(all(m["action"] == "voice_partial" for m in enviadas))

        self.assertTrue(all(set(m) == {"action", "stable", "tail"} for m in enviadas))

        self.assertEqual(enviadas[-1]["stable"], "Bom dia como")

        self.assertEqual(enviadas[-1]["tail"], "vai")



    def test_nao_repete_mensagem_igual(self):

        enviadas = []

        d = ditado.Ditado(MotorFalso(["oi", "oi", "oi"]), enviar=enviadas.append)

        for _ in range(3):

            d.alimentar(b"x")

        # 1ª passada: cauda "Oi"; 2ª: "Oi" virou estável; 3ª: nada mudou -> não repete.

        self.assertEqual(len(enviadas), 2)

        self.assertNotEqual(enviadas[0], enviadas[1])



    def test_final_leva_o_texto_corrigido(self):

        enviadas = []

        motor = MotorFalso([])

        motor.eventos = lambda: [("final", "ola mundo virgula tudo bem")]

        d = ditado.Ditado(motor, enviar=enviadas.append)

        msg = d.drenar()[0]

        self.assertEqual(msg["action"], "voice_final")

        self.assertEqual(msg["text"], "Ola mundo, tudo bem")



    def test_correcao_externa_manda_no_final(self):

        motor = MotorFalso([])

        motor.eventos = lambda: [("final", "texto bruto")]

        d = ditado.Ditado(motor, correcao=lambda _t: "texto corrigido")

        self.assertEqual(d.fechar()["text"], "Texto corrigido")



    def test_motor_janela_limita_o_buffer(self):

        vistos = []



        def transcrever(audio):

            vistos.append(len(audio))

            return "oi"



        motor = ditado.MotorJanela(transcrever, taxa=1000, janela_s=1.0, passo_s=0.5)

        for _ in range(10):

            motor.alimentar(b"\x00\x00" * 700)     # 1400 bytes (0,7 s) por bloco

        self.assertTrue(vistos)

        self.assertLessEqual(max(vistos), 2000)     # 1 s a 1000 Hz, 2 bytes por amostra





# ======================================================================

# T2 — modo conversa

# ======================================================================

class ComandosPropriosTests(unittest.TestCase):

    def setUp(self):

        self._tmp = tempfile.TemporaryDirectory()

        self.base = Path(self._tmp.name)



    def tearDown(self):

        self._tmp.cleanup()



    def test_criar_e_expandir(self):

        ok, msg = cp.adicionar("resumo", "Resuma em 5 linhas: {argumento}", self.base)

        self.assertTrue(ok, msg)

        self.assertEqual(cp.expandir("resumo", "a aula de fisica", self.base),

                         "Resuma em 5 linhas: a aula de fisica")



    def test_nome_invalido_e_recusado(self):

        for nome in ("", "com espaço", "1abc", "A", "x" * 30):

            ok, _ = cp.adicionar(nome, "pedido {argumento}", self.base)

            self.assertFalse(ok, nome)



    def test_nao_rouba_comando_do_zenith(self):

        ok, msg = cp.adicionar("pausar", "texto {argumento}", self.base)

        self.assertFalse(ok)

        self.assertIn("já é um comando", msg)



    def test_sem_marcador_recebe_o_argumento_no_fim(self):

        cp.adicionar("traduzir", "Traduza para o ingles", self.base)

        self.assertEqual(cp.expandir("traduzir", "bom dia", self.base),

                         "Traduza para o ingles bom dia")



    def test_apagar(self):

        cp.adicionar("resumo", "Resuma: {argumento}", self.base)

        ok, _ = cp.apagar("resumo", self.base)

        self.assertTrue(ok)

        self.assertIsNone(cp.expandir("resumo", "x", self.base))



    def test_arquivo_torto_nao_quebra(self):

        (self.base / cp.ARQUIVO).write_text("{isso não é json", encoding="utf-8")

        self.assertEqual(cp.carregar(self.base), {})

        self.assertIsNone(cp.expandir("qualquer", "x", self.base))



    def test_nao_executa_codigo(self):

        cp.adicionar("perigoso", "rm -rf / {argumento}", self.base)

        self.assertEqual(cp.expandir("perigoso", "tudo", self.base), "rm -rf / tudo")



    def test_tratar_lista_e_cria(self):

        texto = cp.tratar("", self.base)

        self.assertIn("Nenhum comando próprio", texto)

        texto = cp.tratar("add oi :: Diga oi para {argumento}", self.base)

        self.assertIn("/oi", texto)

        self.assertIn("Diga oi para", cp.tratar("", self.base))





class ComandoNoChatTests(unittest.TestCase):

    def test_comando_desconhecido_com_modelo_vira_pedido(self):

        with tempfile.TemporaryDirectory() as tmp:

            cp.adicionar("resumo", "Resuma: {argumento}", tmp)

            original = cp._pasta

            cp._pasta = lambda base=None: Path(tmp)      # o comando usa a pasta real; aqui é falso

            try:

                cmd = commands.tratar("/resumo o texto todo")

            finally:

                cp._pasta = original

        self.assertIsNotNone(cmd)

        self.assertEqual(cmd["acao"], "pedido_proprio")

        self.assertEqual(cmd["args"]["texto"], "Resuma: o texto todo")



    def test_atualizar_exige_passo_valido(self):

        cmd = commands.tratar("/atualizar")

        self.assertEqual(cmd["acao"], "atualizar")

        self.assertEqual(cmd["args"]["passo"], "consultar")

        self.assertEqual(commands.tratar("/atualizar baixar")["args"]["passo"], "baixar")

        self.assertIn("Use /atualizar", commands.tratar("/atualizar foguete")["resposta"])



    def test_comando_lista_sem_quebrar(self):

        cmd = commands.tratar("/comando")

        self.assertIn("comando", cmd["resposta"].lower())





# ======================================================================

# T9 — atualização

# ======================================================================

class AtualizacaoTests(unittest.TestCase):

    def _info(self, versao="v9.9", sha=None, url="https://exemplo/zenith.exe", tamanho=10):

        dados = b"conteudo-do-instalador"

        return {"versao": versao, "notas": "corrige a tela de chaves",

                "url": url, "sha256": sha or hashlib.sha256(dados).hexdigest(),

                "tamanho": tamanho}, dados



    def test_consulta_le_o_versions_json(self):

        info, dados = self._info()

        achado, erro = at.consultar("https://exemplo/versions.json",

                                    obter=lambda url, tempo=15: json.dumps(info).encode("utf-8"))

        self.assertEqual(erro, "")

        self.assertEqual(achado["versao"], "v9.9")



    def test_endereco_sem_https_e_recusado(self):

        _, erro = at.consultar("http://exemplo/versions.json")

        self.assertIn("https", erro)



    def test_servidor_fora_do_ar_nao_levanta(self):

        def explode(_url, tempo=15):

            raise OSError("sem rede")

        _, erro = at.consultar("https://exemplo/versions.json", obter=explode)

        self.assertIn("sem rede", erro)



    def test_planejar_recusa_sem_sha(self):

        info, _ = self._info(sha="nao-e-um-sha")

        plano = at.planejar(info, "v1.4")

        self.assertFalse(plano["ok"])

        self.assertIn("SHA-256", plano["motivo"])



    def test_planejar_recusa_url_estranha(self):

        info, _ = self._info(url="ftp://exemplo/zenith.exe")

        self.assertFalse(at.planejar(info, "v1.4")["ok"])



    def test_versao_igual_nao_e_novidade(self):

        info, _ = self._info(versao="v1.4")

        plano = at.planejar(info, "v1.4")

        self.assertTrue(plano["ok"])

        self.assertFalse(plano["ha_novidade"])



    def test_baixar_confere_sha_e_salva(self):

        info, dados = self._info()

        plano = at.planejar(info, "v1.4")

        with tempfile.TemporaryDirectory() as tmp:

            caminho, erro = at.baixar(plano, obter=lambda url, tempo=15: dados, pasta=tmp)

            self.assertEqual(erro, "")

            self.assertTrue(Path(caminho).is_file())

            self.assertEqual(Path(caminho).read_bytes(), dados)



    def test_sha_diferente_nao_salva_nada(self):

        info, dados = self._info(sha="0" * 64)

        plano = at.planejar(info, "v1.4")

        with tempfile.TemporaryDirectory() as tmp:

            caminho, erro = at.baixar(plano, obter=lambda url, tempo=15: dados, pasta=tmp)

            self.assertEqual(caminho, "")

            self.assertIn("SHA-256", erro)

            self.assertEqual(list(Path(tmp).iterdir()), [])



    def test_nao_abre_sem_pedido_explicito(self):

        ok, msg = at.abrir_instalador("qualquer.exe")

        self.assertFalse(ok)

        self.assertIn("NÃO abri", msg)



    def test_nao_abre_arquivo_que_nao_e_exe(self):

        with tempfile.TemporaryDirectory() as tmp:

            alvo = Path(tmp) / "notas.txt"

            alvo.write_text("x", encoding="utf-8")

            ok, msg = at.abrir_instalador(str(alvo), aprovado=True)

            self.assertFalse(ok)



    def test_formatar_nao_promete_instalacao(self):

        info, _ = self._info()

        texto = at.formatar(info, at.planejar(info, "v1.4"), "v1.4")

        self.assertIn("v9.9", texto)

        self.assertIn("/atualizar baixar", texto)

        self.assertIn("Nada foi baixado", texto)





if __name__ == "__main__":

    unittest.main()

