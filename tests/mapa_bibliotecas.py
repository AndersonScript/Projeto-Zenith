"""Varre brain/ e skills/ e diz: que bibliotecas de fora existem, quem usa, e quais o Cérebro exige JÁ NA PARTIDA no celular.
Usado pelo teste (tests/test_port_celular_v19.py) e para gerar docs/BIBLIOTECAS_ANDROID.md."""
import ast, pathlib, sys

STDLIB = set(sys.stdlib_module_names)
PROPRIOS = {"brain", "skills", "tests", "body"}


def _topo(nome):
    p = nome.split(".")
    return ".".join(p[:2]) if p[0] == "google" and len(p) > 1 else p[0]


def _de_fora(nome):
    t = nome.split(".")[0]
    return t not in STDLIB and t not in PROPRIOS and t != "__future__"


def usos(raiz):
    """{biblioteca: {modulo_do_cerebro, ...}} — todas as bibliotecas de fora, em qualquer lugar do código."""
    achados = {}
    for pasta in ("brain", "skills"):
        for f in sorted((pathlib.Path(raiz) / pasta).glob("*.py")):
            for no in ast.walk(ast.parse(f.read_bytes().decode("utf-8"))):
                nomes = [a.name for a in no.names] if isinstance(no, ast.Import) else (
                    [no.module] if isinstance(no, ast.ImportFrom) and no.level == 0 and no.module else [])
                for n in nomes:
                    if _de_fora(n):
                        achados.setdefault(_topo(n), set()).add(f.stem)
    return achados


def _imports_de_topo(arq):
    """Imports que rodam quando o módulo é carregado (inclui os dentro de try/if, exclui os dentro de função)."""
    out = []

    def andar(corpo):
        for no in corpo:
            if isinstance(no, ast.Import):
                out.extend(a.name for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                out.append(no.module)
                out.extend(f"{no.module}.{a.name}" for a in no.names)
            elif isinstance(no, ast.Try):
                andar(no.body)
                for h in no.handlers:
                    andar(h.body)
                andar(no.orelse)
                andar(no.finalbody)
            elif isinstance(no, ast.If):
                andar(no.body)
                andar(no.orelse)
    andar(ast.parse(arq.read_bytes().decode("utf-8")).body)
    return out


def _protegido(arq, biblioteca):
    """True se TODO import de `biblioteca` no topo deste arquivo está dentro de um try (ou não existe no topo)."""
    arv = ast.parse(arq.read_bytes().decode("utf-8"))
    sem_protecao = []

    def andar(corpo, em_try):
        for no in corpo:
            nomes = [a.name for a in no.names] if isinstance(no, ast.Import) else (
                [no.module] if isinstance(no, ast.ImportFrom) and no.level == 0 and no.module else [])
            if any(_de_fora(n) and _topo(n) == biblioteca for n in nomes) and not em_try:
                sem_protecao.append(no)
            if isinstance(no, ast.Try):
                andar(no.body, True)
                for h in no.handlers:
                    andar(h.body, em_try)
                andar(no.orelse, em_try)
                andar(no.finalbody, em_try)
            elif isinstance(no, ast.If):
                por_plataforma = "android" in ast.unparse(no.test).lower()      # `if detectar() != "android": import x`
                andar(no.body, em_try or por_plataforma)
                andar(no.orelse, em_try or por_plataforma)
    andar(arv.body, False)
    return not sem_protecao


def exigidas_na_partida(raiz, entrada="brain.zenith_headless", ausentes_no_celular=()):
    """Bibliotecas de fora que o Cérebro importa no topo, SEM try, a partir de `entrada` — sem elas ele não abre.
    `ausentes_no_celular`: bibliotecas que o celular simulado não tem (o import precisa estar protegido)."""
    raiz = pathlib.Path(raiz)
    visto, fila, exigidas = set(), [entrada], {}
    while fila:
        m = fila.pop()
        if m in visto:
            continue
        visto.add(m)
        arq = raiz / pathlib.Path(*m.split(".")).with_suffix(".py")
        if not arq.is_file():
            continue
        for imp in _imports_de_topo(arq):
            if imp.split(".")[0] in ("brain", "skills"):
                fila.append(imp)
            elif _de_fora(imp):
                lib = _topo(imp)
                if not _protegido(arq, lib):
                    exigidas.setdefault(lib, set()).add(m.split(".")[-1])
    return exigidas
