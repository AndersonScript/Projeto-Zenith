# -*- coding: utf-8 -*-
"""v1.12 — "Código executado (sem saída de texto)" de novo.

O QUE ACONTECIA: quando a Zenith executa um script pelo .exe, o launcher roda em modo
script e a saída do script deveria ir para o pipe que o Cérebro lê. Só que o próprio
launcher, no topo do arquivo, troca sys.stdout/sys.stderr pelo zenith_log.txt — então
sys.stdout NUNCA é None e o conserto antigo ("só troca se for None") nem era acionado:
todo print() do script caía no log, o pipe ficava vazio e a Zenith respondia
"Código executado (sem saída de texto)".

A CORREÇÃO: no modo script o redirecionamento é FORÇADO (`_garantir_saida_padrao(forcar=True)`).
Este teste é a trava: se alguém voltar a confiar em "só troca se for None", ele quebra.

Como rodar só ele:
    py -3 -m unittest tests.test_v30_launcher_print -v
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("ZENITH_TESTE", "1")
import zenith_launcher as ZL  # noqa: E402  (o ZENITH_TESTE acima impede o redirecionamento no import)


class _FluxoFalso:
    """Faz o papel do fluxo ligado ao PIPE do processo pai."""

    def __init__(self):
        self.escrito = []

    def write(self, texto):
        self.escrito.append(texto)
        return len(texto)

    def flush(self):
        pass


class SaidaDoScriptTests(unittest.TestCase):
    def setUp(self):
        self._stdout_antes = sys.stdout
        self._stderr_antes = sys.stderr
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        sys.stdout = self._stdout_antes
        sys.stderr = self._stderr_antes

    def test_sem_forcar_nao_mexe_num_stdout_que_ja_existe(self):
        """Fora do modo script, o log continua sendo o destino (não muda o comportamento do app)."""
        log = _FluxoFalso()
        sys.stdout, sys.stderr = log, log
        with mock.patch.object(ZL, "_fluxo_do_processo", return_value=_FluxoFalso()) as m:
            ZL._garantir_saida_padrao()
        m.assert_not_called()
        self.assertIs(sys.stdout, log)

    def test_forcando_manda_o_print_para_o_pipe_do_pai(self):
        """O caso do defeito: sys.stdout já aponta pro zenith_log.txt e mesmo assim tem que ir pro pipe."""
        log = _FluxoFalso()
        sys.stdout, sys.stderr = log, log
        pipe_out, pipe_err = _FluxoFalso(), _FluxoFalso()
        fluxos = {1: pipe_out, 2: pipe_err}
        with mock.patch.object(ZL, "_fluxo_do_processo", side_effect=lambda fd: fluxos[fd]):
            ZL._garantir_saida_padrao(forcar=True)
        self.assertIs(sys.stdout, pipe_out)
        self.assertIs(sys.stderr, pipe_err)
        print("saída de verdade")
        self.assertEqual("".join(pipe_out.escrito), "saída de verdade\n")
        self.assertEqual(log.escrito, [])          # nada foi parar no log

    def test_sem_canal_nenhum_nao_derruba_o_script(self):
        """Se não houver pipe (rodando na mão), segue sem saída em vez de estourar exceção."""
        log = _FluxoFalso()
        sys.stdout, sys.stderr = log, log
        with mock.patch.object(ZL, "_fluxo_do_processo", return_value=None):
            ZL._garantir_saida_padrao(forcar=True)
        self.assertIs(sys.stdout, log)              # manteve o que havia, sem quebrar


if __name__ == "__main__":
    unittest.main(verbosity=2)
