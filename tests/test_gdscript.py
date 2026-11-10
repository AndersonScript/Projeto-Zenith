"""v1.1 — rede de segurança do Corpo (Godot).

Por que existe: a v1.0 saiu com `ui_manager.gd` que NÃO CARREGAVA (regex com `\\-` e `\\s` dentro de aspas
comuns — o GDScript recusa), e os 974 testes de Python passaram mesmo assim, porque nenhum deles enxerga o Godot.

Duas camadas:
  1. LINT em Python puro (roda em qualquer máquina): barra de escape inválida dentro de string comum.
  2. CHECAGEM COM O GODOT DE VERDADE (só roda se houver Godot: variável ZENITH_GODOT_CHECK, PATH, C:\\Godot\\ ou tools/godot/):
     `godot --headless --path body/zenith --check-only --script res://<arquivo>.gd` para cada .gd do Corpo.
"""
import os
import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CORPO = RAIZ / "body" / "zenith"
ESCAPES_VALIDOS = set("abfnrtv\"'\\u")


def arquivos_gd():
    return sorted(p for p in CORPO.glob("*.gd"))


def escapes_invalidos(texto: str):
    """Devolve [(linha, trecho)] com `\\x` inválido dentro de strings comuns (strings r"..." são brutas e valem)."""
    achados = []
    i, n, linha = 0, len(texto), 1
    while i < n:
        c = texto[i]
        if c == "\n":
            linha += 1
            i += 1
        elif c == "#":                                   # comentário até o fim da linha
            while i < n and texto[i] != "\n":
                i += 1
        elif c in "\"'":
            bruta = i > 0 and texto[i - 1] == "r" and (i < 2 or not (texto[i - 2].isalnum() or texto[i - 2] == "_"))
            triplo = texto[i:i + 3] == c * 3
            aspa = c * 3 if triplo else c
            i += len(aspa)
            while i < n and texto[i:i + len(aspa)] != aspa:
                if texto[i] == "\n":
                    linha += 1
                    if not triplo:
                        break
                if texto[i] == "\\" and i + 1 < n:
                    if not bruta and texto[i + 1] not in ESCAPES_VALIDOS and texto[i + 1] != "\n":
                        achados.append((linha, texto[i:i + 2]))
                    i += 2
                    continue
                i += 1
            i += len(aspa) if texto[i:i + len(aspa)] == aspa else 0
        else:
            i += 1
    return achados


def achar_godot():
    env = os.environ.get("ZENITH_GODOT_CHECK")
    if env and Path(env).exists():
        return env
    for nome in ("godot", "godot4", "Godot_v4.7.1-stable_linux.x86_64"):
        achado = shutil.which(nome)
        if achado:
            return achado
    candidatos = list(Path("C:/Godot").glob("Godot_v4.7*.exe")) if os.name == "nt" else []
    candidatos += list((RAIZ / "tools" / "godot").glob("*Godot*")) if (RAIZ / "tools" / "godot").exists() else []
    candidatos = [c for c in candidatos if "console" in c.name.lower()] + candidatos
    return str(candidatos[0]) if candidatos else None


class TestLintGDScript(unittest.TestCase):
    def test_o_lint_pega_o_defeito_da_v1_0(self):
        ruim = 'const P := [\n\t"AIza[0-9A-Za-z_\\-]{30,}",\n\t"\\bBearer\\s+[A-Za-z0-9]{16,}"\n]\n'
        invalidos = [t for _, t in escapes_invalidos(ruim)]
        self.assertIn("\\-", invalidos)
        self.assertIn("\\s", invalidos)

    def test_string_bruta_e_comentario_nao_acusam(self):
        bom = 'const P := [r"AIza[0-9A-Za-z_\\-]{30,}", "ok\\n", "aspas \\" e \\\\"]  # um \\- num comentário\n'
        self.assertEqual(escapes_invalidos(bom), [])

    def test_nenhum_gd_do_corpo_tem_escape_invalido(self):
        for gd in arquivos_gd():
            with self.subTest(arquivo=gd.name):
                achados = escapes_invalidos(gd.read_text(encoding="utf-8"))
                self.assertEqual(achados, [], f"{gd.name}: escape inválido (use r\"...\" para regex): {achados[:5]}")


@unittest.skipUnless(achar_godot(), "Godot 4.7 não encontrado (defina ZENITH_GODOT_CHECK=caminho ou ponha em C:\\Godot\\) — pulando")
class TestGodotCheckOnly(unittest.TestCase):
    def test_todos_os_gd_do_corpo_carregam(self):
        godot = achar_godot()
        for gd in arquivos_gd():
            with self.subTest(arquivo=gd.name):
                r = subprocess.run([godot, "--headless", "--path", str(CORPO), "--check-only", "--script", f"res://{gd.name}"],
                                   capture_output=True, text=True, timeout=120)
                saida = (r.stdout or "") + (r.stderr or "")
                ruins = [l for l in saida.splitlines() if "SCRIPT ERROR" in l or "Parse Error" in l or "Compile Error" in l]
                self.assertEqual(ruins, [], f"{gd.name} não carrega no Godot:\n" + "\n".join(saida.splitlines()[:12]))

    def test_autoteste_dos_meus_temas_e_do_contraste(self):
        """Salvar/importar/aplicar tema, saneamento de tema vindo de fora (arquivo malicioso) e contraste dos 10 temas prontos."""
        script = RAIZ / "tools" / "visual" / "selftest_temas.gd"
        r = subprocess.run([achar_godot(), "--headless", "--path", str(CORPO), "--script", str(script)],
                           capture_output=True, text=True, timeout=180)
        saida = (r.stdout or "") + (r.stderr or "")
        falhas = [l for l in saida.splitlines() if l.startswith("FALHA")]
        self.assertIn("SELFTEST_OK", saida, "autoteste dos temas falhou:\n" + "\n".join(falhas or saida.splitlines()[-12:]))


if __name__ == "__main__":
    unittest.main()
