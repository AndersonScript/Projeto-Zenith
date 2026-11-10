"""
Zenith — Conhecimento em cartões: a Bíblia que CRESCE e se adapta a cada IA (v22).

Junta duas coisas que nasceram em paralelo:
  * a Bíblia do Anderson (`zenith_biblia.py`: regras de ouro sempre no prompt + seções por assunto) — é a BASE;
  * os mecanismos da versão "Claude": cartões em ARQUIVO, perfil por IA, validador de formato, ZENITH.md.
e acrescenta o que faltava pra ela ficar "implantada de fábrica e crescendo com o tempo":

  1. BASE (sempre no código): as seções da Bíblia viram cartões. As regras de ouro + o corpo vão SEMPRE no prompt
     do sistema (`zenith_biblia.bloco_fixo`).
  2. CARTÕES EM ARQUIVO (config/biblia/*.md): a pessoa edita/cria; id igual ao de uma seção da base = substitui.
  3. APRENDIZADO (`<aprender>`): a própria Zenith PROPÕE um cartão novo (um erro e a correção, um detalhe de
     biblioteca, uma preferência) e a pessoa APROVA — vira `aprendido-<id>.md` e passa a ser puxado sozinho
     quando as palavras-chave aparecerem. É o jeito dela ficar mais esperta com o tempo, sob o Pilar 1:
     cartão aprendido nunca é "sempre ligado", não pode conter etiqueta de ação, passa pelo filtro de segurança
     e pode ser apagado (`/biblia apagar <id>`).
  4. PERFIL POR IA (config/biblia/perfis_modelos.json): quantos cartões e quanto texto cada IA recebe.
  5. VALIDADOR: confere o formato das etiquetas na resposta e pede UMA correção automática.

Só texto: nada aqui executa coisa alguma nem relaxa o Pilar 1.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from brain import zenith_biblia as BI

SEMPRE_BASICO = ("ferramentas",)          # IA de nível básico recebe SEMPRE o cartão de como usar as etiquetas
LIMITE_APRENDIDOS = 150
LIMITE_CORPO_APRENDIDO = 1200

PERFIS_PADRAO = {
    "padrao": {"nivel": "medio",  "max_cartoes": 3, "max_chars": 3500, "validar": True, "contexto_tokens": 32000},
    "gemini": {"nivel": "forte",  "max_cartoes": 3, "max_chars": 3500, "validar": True, "contexto_tokens": 1000000},
    "openai": {"nivel": "medio",  "max_cartoes": 3, "max_chars": 3500, "validar": True, "contexto_tokens": 128000},
    "claude": {"nivel": "forte",  "max_cartoes": 3, "max_chars": 3500, "validar": True, "contexto_tokens": 200000},
    "llama":  {"nivel": "medio",  "max_cartoes": 3, "max_chars": 3500, "validar": True, "contexto_tokens": 32000},
    # OpenRouter grátis também é apertado por minuto; o mesmo motivo do groq acima.
    # v1.10 — plano grátis do Groq: 8000 tokens por MINUTO para o pedido inteiro (log real: "Request too large ...
    # TPM: Limit 8000"). Medido aqui com o prompt de sistema do Zenith: ele sozinho já custa ~4.750 tokens, então
    # o histórico tem que caber em ~2.500. Acima disso o pedido é recusado (e o chat repete sem histórico).
    "groq":   {"nivel": "medio",  "max_cartoes": 3, "max_chars": 3500, "validar": True, "contexto_tokens": 2500},
    # IA cadastrada pelo usuário (muitas vezes um modelo local pequeno): trata como nível básico
    "custom": {"nivel": "basico", "max_cartoes": 3, "max_chars": 4500, "validar": True, "contexto_tokens": 8000},
}


def _norm(s: str) -> str:
    return BI._norm(s)


def _config_dir() -> Path:
    from brain import zenith_settings as cfg
    return Path(cfg.CONFIG_DIR)


def pasta_biblia() -> Path:
    return _config_dir() / "biblia"


# ======================================================================
#  Cartões
# ======================================================================
@dataclass
class Cartao:
    id: str
    titulo: str
    palavras: tuple
    corpo: str
    origem: str = "base"          # base | arquivo | aprendido
    modo: str = "substring"       # base casa por trecho (como a Bíblia sempre fez); arquivo casa por palavra
    sempre: str = "nao"           # nao | sim | basico
    prioridade: int = 5

    def texto(self, user: str = "", persona: str = "", pasta_criacoes: str = "") -> str:
        t = BI._preencher(self.corpo, user, persona, pasta_criacoes)
        return t.replace("{CREATION_DIR}", str(pasta_criacoes or "creations").replace("\\", "/"))


def cartoes_base() -> list:
    saida = []
    for i, chave in enumerate(BI.ORDEM_DOC):
        if chave in ("essencial", "corpo"):
            continue
        sec = BI.SECOES[chave]
        saida.append(Cartao(id=chave, titulo=sec["titulo"], palavras=tuple(_norm(g) for g in sec["gatilhos"]),
                            corpo=sec["texto"], origem="base", modo="substring",
                            sempre="basico" if chave in SEMPRE_BASICO else "nao", prioridade=20 - i))
    return saida


def parse_cartao(texto: str, nome_arquivo: str = "") -> "Cartao | None":
    """Lê um .md com cabeçalho '---' ... '---' (id, titulo, palavras, sempre, prioridade)."""
    m = re.match(r"^\s*---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", texto or "", re.S)
    if not m:
        return None
    cab = {}
    for linha in m.group(1).splitlines():
        if ":" in linha:
            k, v = linha.split(":", 1)
            cab[k.strip().lower()] = v.strip()
    cid = cab.get("id") or (Path(nome_arquivo).stem if nome_arquivo else "")
    corpo = m.group(2).strip()
    if not cid or not corpo:
        return None
    sempre = cab.get("sempre", "nao").lower()
    pr = cab.get("prioridade", "5")
    origem = "aprendido" if cid.startswith("aprendido-") else "arquivo"
    if origem == "aprendido":
        sempre = "nao"                                  # aprendido nunca é "sempre ligado"
    return Cartao(id=cid, titulo=cab.get("titulo") or cid,
                  palavras=tuple(_norm(p).strip() for p in re.split(r"[,;]", cab.get("palavras", "")) if p.strip()),
                  corpo=corpo, origem=origem, modo="palavra",
                  sempre=sempre if sempre in ("nao", "sim", "basico") else "nao",
                  prioridade=int(pr) if pr.lstrip("-").isdigit() else 5)


def carregar_cartoes(pasta=None) -> list:
    por_id = {c.id: c for c in cartoes_base()}
    pasta = Path(pasta) if pasta is not None else pasta_biblia()
    try:
        arquivos = sorted(pasta.glob("*.md")) if pasta.exists() else []
    except OSError:
        arquivos = []
    for arq in arquivos:
        try:
            c = parse_cartao(arq.read_text(encoding="utf-8", errors="replace"), arq.name)
        except OSError:
            c = None
        if c:
            por_id[c.id] = c
    return list(por_id.values())


def garantir_arquivos(pasta=None, zenith_md=None) -> list:
    """Cria (sem sobrescrever) perfis_modelos.json e o modelo do ZENITH.md. Falha em silêncio."""
    criados = []
    try:
        pasta = Path(pasta) if pasta is not None else pasta_biblia()
        pasta.mkdir(parents=True, exist_ok=True)
        perfis = pasta / "perfis_modelos.json"
        if not perfis.exists():
            perfis.write_text(json.dumps(PERFIS_PADRAO, ensure_ascii=False, indent=2), encoding="utf-8")
            criados.append(str(perfis))
        zmd = Path(zenith_md) if zenith_md is not None else _config_dir() / "ZENITH.md"
        if not zmd.exists():
            zmd.write_text(ZENITH_MD_MODELO, encoding="utf-8")
            criados.append(str(zmd))
    except OSError as e:
        print(f"[Zenith/Conhecimento] não consegui gravar os arquivos padrão ({e}); sigo com os padrões do código.")
    return criados


ZENITH_MD_MODELO = """<!--
  ZENITH.md — o que a sua Zenith deve SEMPRE saber sobre você e sobre como você trabalha.
  Escreva abaixo, em português, em tópicos curtos. Tudo que estiver FORA deste comentário vai
  junto do prompt de toda conversa (até ~3000 caracteres; o resto é cortado).

  Exemplos (apague este bloco e escreva os seus):
    - Estudo Automação Industrial; use unidades do SI e 3 algarismos significativos.
    - Quando eu pedir um programa, prefira Python e explique como rodar.

  Isto NÃO muda os pilares do sistema nem a aprovação de ações: é só contexto seu.
  Depois de editar, feche e abra o Zenith (ou salve as Configurações) para valer.
-->
"""


# ======================================================================
#  Perfis por IA
# ======================================================================
def carregar_perfis(pasta=None) -> dict:
    perfis = {k: dict(v) for k, v in PERFIS_PADRAO.items()}
    pasta = Path(pasta) if pasta is not None else pasta_biblia()
    try:
        arq = pasta / "perfis_modelos.json"
        if arq.exists():
            extra = json.loads(arq.read_text(encoding="utf-8"))
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if isinstance(v, dict):
                        perfis.setdefault(str(k), {}).update(v)
    except (OSError, ValueError):
        pass
    return perfis


def perfil_para(ia: str, pasta=None) -> dict:
    """Perfil da IA em uso ('gemini', 'openai', 'custom:abc'...). Desconhecida → 'padrao'; 'custom:*' → 'custom'."""
    perfis = carregar_perfis(pasta)
    chave = str(ia or "")
    if chave not in perfis:
        chave = "custom" if chave.startswith("custom") else "padrao"
    base = dict(perfis["padrao"])
    base.update(perfis.get(chave, {}))
    if base.get("nivel") not in ("forte", "medio", "basico"):
        base["nivel"] = "medio"
    return base


# ======================================================================
#  Seleção
# ======================================================================
def _casa(c: Cartao, msg_norm: str) -> int:
    n = 0
    for p in c.palavras:
        if not p:
            continue
        if c.modo == "substring":
            ok = p in msg_norm
        else:
            padrao = rf"(?<![a-z0-9]){re.escape(p)}" + (r"(?![a-z0-9])" if len(p) <= 3 else "")
            ok = re.search(padrao, msg_norm) is not None
        n += 1 if ok else 0
    return n


def selecionar(mensagem: str, ia: str = "", pasta=None, cartoes=None, perfil=None) -> list:
    """Cartões que combinam com a mensagem, dentro do orçamento do perfil da IA (mais fortes primeiro)."""
    perfil = perfil or perfil_para(ia, pasta)
    cartoes = cartoes if cartoes is not None else carregar_cartoes(pasta)
    msg = _norm(mensagem)
    basico = perfil.get("nivel") == "basico"
    pont = []
    for c in cartoes:
        acertos = _casa(c, msg) if msg.strip() else 0
        fixo = c.sempre == "sim" or (c.sempre == "basico" and basico)
        if acertos == 0 and not fixo:
            continue
        pont.append((1 if fixo else 0, acertos, c.prioridade, c))
    pont.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    maximo = int(perfil.get("max_cartoes", 3))
    orcamento = int(perfil.get("max_chars", 3500))
    escolhidos, usado = [], 0
    for _f, _a, _p, c in pont:
        if len(escolhidos) >= maximo:
            break
        tam = len(c.corpo) + len(c.titulo) + 8
        if usado + tam > orcamento and escolhidos:
            continue
        escolhidos.append(c)
        usado += tam
    return escolhidos


def guia_para(mensagem: str, ia: str = "", user: str = "", persona: str = "Zenith", pasta_criacoes: str = "",
              pasta=None) -> str:
    """Texto dos cartões relevantes (ou ''). Substitui `zenith_biblia.guia_para` no Cérebro: mesmas seções,
    mais os cartões do usuário e os aprendidos, com orçamento por perfil de IA."""
    escolhidos = selecionar(mensagem, ia, pasta)
    if not escolhidos:
        return ""
    blocos = [f"### {c.titulo}\n" + c.texto(user, persona, pasta_criacoes) for c in escolhidos]
    return "[Guia da Bíblia do Zenith para esta tarefa — siga]:\n" + "\n\n".join(blocos)


# ======================================================================
#  Aprendizado: <aprender id="..." palavras="a, b">texto</aprender>
# ======================================================================
_RE_APRENDER = re.compile(r"<aprender\b([^>]*)>(.*?)</aprender>", re.S | re.I)
_RE_ATTR = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_RE_TAG_ACAO = re.compile(r"<\s*/?\s*(executar_python|executar_terminal|conectar_serial|ver_tela|ver_camera|buscar_web|"
                          r"ler_url|buscar_imagem|gerar_imagem|criar_programa|aprender|corpo|arquivo|lembrar|\
                          editar_video|organizar_pasta|criar_documento)\b", re.I)


def interpretar_aprender(conteudo: str) -> dict:
    """{'id','palavras','corpo','erros'}. Não levanta exceção."""
    r = {"id": "", "palavras": [], "corpo": "", "erros": []}
    m = _RE_APRENDER.search(conteudo or "")
    if not m:
        r["erros"].append("não achei a etiqueta <aprender>...</aprender> completa")
        return r
    at = {k.lower(): (a or b or "") for k, a, b in _RE_ATTR.findall(m.group(1))}
    cid = re.sub(r"[^a-z0-9-]+", "-", _norm(at.get("id", "")).strip()).strip("-")[:40]
    palavras = [p.strip() for p in re.split(r"[,;]", at.get("palavras", "")) if p.strip()]
    corpo = m.group(2).strip()
    if not 3 <= len(cid) <= 40:
        r["erros"].append("o id precisa ter de 3 a 40 letras/números/hífens (ex.: pygame-teclas)")
    if not 1 <= len(palavras) <= 12 or any(not 3 <= len(_norm(p)) <= 30 for p in palavras):
        r["erros"].append("informe de 1 a 12 palavras-chave de 3 a 30 letras")
    if not 20 <= len(corpo) <= LIMITE_CORPO_APRENDIDO:
        r["erros"].append(f"o texto precisa ter de 20 a {LIMITE_CORPO_APRENDIDO} caracteres")
    if _RE_TAG_ACAO.search(corpo):
        r["erros"].append("o texto não pode conter etiquetas de ação (<...>)")
    r.update(id=f"aprendido-{cid}" if cid else "", palavras=[_norm(p).strip() for p in palavras], corpo=corpo)
    return r


def preview_aprender(conteudo: str, pasta=None) -> str:
    r = interpretar_aprender(conteudo)
    linhas = [f"[APRENDER] {r['id'] or '(sem id)'}",
              f"Palavras que ativam: {', '.join(r['palavras']) or '?'}",
              f"Vai ser gravado em: {(Path(pasta) if pasta is not None else pasta_biblia()) / (r['id'] + '.md')}",
              "─" * 40, r["corpo"] or "(vazio)"]
    if r["erros"]:
        linhas.append("⚠ Problemas: " + "; ".join(r["erros"]))
    return "\n".join(linhas)


def salvar_aprendizado(conteudo: str, pasta=None) -> str:
    """Grava o cartão aprendido (depois da aprovação). Devolve a mensagem pro usuário."""
    r = interpretar_aprender(conteudo)
    if r["erros"]:
        return "❌ Não guardei o aprendizado: " + "; ".join(r["erros"])
    corpo = r["corpo"]
    try:
        from brain.zenith_validator import strip_suspicious
        if strip_suspicious(corpo) != corpo:
            return "❌ Não guardei: o texto tem um trecho que o filtro de segurança barrou."
    except Exception:
        pass
    pasta = Path(pasta) if pasta is not None else pasta_biblia()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        ja = list(pasta.glob("aprendido-*.md"))
        alvo = pasta / f"{r['id']}.md"
        if len(ja) >= LIMITE_APRENDIDOS and not alvo.exists():
            return f"❌ Já tenho {LIMITE_APRENDIDOS} aprendizados guardados. Apague alguns com /biblia apagar <id>."
        existia = alvo.exists()
        alvo.write_text("---\n" f"id: {r['id']}\ntitulo: Aprendido: {r['id'][10:]}\n"
                        f"palavras: {', '.join(r['palavras'])}\nsempre: nao\nprioridade: 6\n---\n{corpo}\n", encoding="utf-8")
    except OSError as e:
        return f"❌ Não consegui gravar o aprendizado: {e}"
    return (f"🧠 {'Atualizei' if existia else 'Guardei'} o aprendizado “{r['id']}”. Ele passa a ser usado quando "
            f"aparecerem: {', '.join(r['palavras'])}. (Apagar: /biblia apagar {r['id']}.)")


def apagar_aprendizado(cid: str, pasta=None) -> str:
    cid = str(cid or "").strip().lower()
    if not cid.startswith("aprendido-") or not re.match(r"^aprendido-[a-z0-9-]{3,40}$", cid):
        return "❌ Só dá pra apagar aqui os cartões que eu aprendi (id começa com “aprendido-”). Os outros são arquivos seus: apague o .md."
    alvo = (Path(pasta) if pasta is not None else pasta_biblia()) / f"{cid}.md"
    if not alvo.exists():
        return f"❌ Não achei o aprendizado “{cid}”."
    try:
        alvo.unlink()
    except OSError as e:
        return f"❌ Não consegui apagar: {e}"
    return f"🗑️ Apaguei o aprendizado “{cid}”."


# ======================================================================
#  Validador de formato
# ======================================================================
_TAGS_ACAO = ("executar_python", "executar_terminal", "conectar_serial", "ver_tela", "ver_camera",
              "buscar_web", "ler_url", "buscar_imagem", "gerar_imagem", "criar_programa", "aprender",
              "criar_habilidade", "usar_habilidade", "observar",
              "editar_video", "organizar_pasta", "criar_documento")       # v23 (+ gerar_imagem na v27; vídeo/pasta/documento na v28)
_TAGS_TODAS = _TAGS_ACAO + ("lembrar", "arquivo", "corpo", "comando", "pendencia", "concluir", "projeto")


def validar_resposta(texto: str) -> list:
    """Lista de problemas de formato (vazia = ok). Só olha o que dá pra checar sem adivinhar intenção."""
    t = texto or ""
    problemas = []
    for tag in _TAGS_TODAS:
        abre = len(re.findall(rf"<{tag}\b", t))
        fecha = len(re.findall(rf"</{tag}>", t))
        if abre != fecha:
            problemas.append(f"a etiqueta <{tag}> foi aberta {abre}x e fechada {fecha}x (toda etiqueta precisa de </{tag}>)")
    usadas = [tag for tag in _TAGS_ACAO if re.search(rf"<{tag}\b", t)]
    if len(usadas) > 1:
        problemas.append("mais de uma ação na mesma resposta (" + ", ".join(usadas) + ") — mande UMA ação por vez")
    for tag in ("executar_python", "executar_terminal", "buscar_web", "buscar_imagem", "gerar_imagem", "ver_tela", "ver_camera",
                "editar_video", "organizar_pasta"):
        for corpo in re.findall(rf"<{tag}>(.*?)</{tag}>", t, re.S):
            if not corpo.strip():
                problemas.append(f"a etiqueta <{tag}> está vazia")
    for corpo in re.findall(r"<ler_url>(.*?)</ler_url>", t, re.S):
        if not re.match(r"^\s*https?://\S+\s*$", corpo):
            problemas.append("<ler_url> precisa conter só um endereço começando com http:// ou https://")
    for corpo in re.findall(r"<conectar_serial>(.*?)</conectar_serial>", t, re.S):
        if not re.match(r"^\s*[^;\s]+;\d{3,7};\S.*$", corpo.strip(), re.S):
            problemas.append("<conectar_serial> precisa de PORTA;BAUD;COMANDO (ex.: COM3;9600;LIGAR_LED)")
    for corpo in re.findall(r"<executar_python>(.*?)</executar_python>", t, re.S):
        if re.search(r"\bplt\.show\s*\(", corpo):
            problemas.append("o código usa plt.show() (trava sem mostrar nada) — use plt.savefig(...)")
        if re.search(r"(?<![\w.])input\s*\(", corpo):
            problemas.append("o código usa input() — não há teclado nesse modo (use <criar_programa tipo=\"console\">)")
    return problemas


# ----------------------------------------------------------------------
#  v23 — ATITUDE: o erro que o Anderson viu no teste ("preciso da sua aprovação… vou inserir a tag ``", "como IA,
#  não tenho forma física"). O Zenith JÁ pede a aprovação sozinho quando a etiqueta aparece; pedir licença em texto
#  só atrasa. E "não consigo" sem tentar é desculpa. Heurística: só vale quando a resposta NÃO traz etiqueta de
#  ação, e não dispara quando a pessoa está perguntando sobre as regras/aprovações em si.
# ----------------------------------------------------------------------
_PEDE_LICENCA = re.compile(
    r"preciso\s+(?:d[ae]\s+)?(?:sua\s+|uma\s+)?(?:aprova[cç][aã]o|autoriza[cç][aã]o|permiss[aã]o)|"
    r"aguardo\s+(?:a\s+)?sua\s+(?:aprova|autoriza|permiss)|"
    r"assim\s+que\s+voc[eê]\s+(?:aprovar|autorizar|permitir)|"
    r"se\s+voc[eê]\s+(?:aprovar|autorizar|permitir)|"
    r"voc[eê]\s+(?:aprova|autoriza|permite)\s+que\s+eu|"
    r"vou\s+inserir\s+(?:a|uma)\s+(?:tag|etiqueta)|"
    r"(?:tag|etiqueta)\s*[`'\"]{2}", re.I)
_TAG_VAZIA = re.compile(r"`\s*`")
_DESCULPA = re.compile(
    r"(?:n[aã]o|nunca)\s+tenho\s+(?:uma\s+)?forma\s+f[ií]sica|"
    r"como\s+(?:uma\s+)?ia,?\s+(?:eu\s+)?n[aã]o\s+(?:tenho|posso|consigo)|"
    r"sou\s+(?:apenas|s[oó])\s+uma\s+ia\b|"
    r"est[aá]\s+al[eé]m\s+d[ao]s?\s+minhas?\s+capacidades?|"
    r"n[aã]o\s+(?:tenho|possuo)\s+(?:a\s+)?capacidade\s+de|"
    r"n[aã]o\s+consigo\s+(?:criar|fazer|gerar|desenhar)\s+(?:imagens?|desenhos?|um\s+site|sites|programas?)", re.I)
_ADIA = re.compile(
    r"(?:deix(?:a|ar|emos|amos)|vamos\s+deixar|podemos\s+deixar|melhor\s+deixar)\b[^.!?\n]{0,60}\b(?:para|pra)\s+(?:depois|mais\s+tarde|outra\s+hora|amanh[aã])|"
    r"(?:depois|mais\s+tarde)\s+(?:a\s+gente|eu|n[oó]s)\s+(?:faz|fa[cç]o|fazemos|v[eê]|vemos)", re.I)
_USUARIO_ADIA = re.compile(r"depois|mais\s+tarde|amanh[aã]|lembr|agend|quando\s+eu", re.I)
_PERGUNTA_SOBRE_REGRAS = re.compile(r"pilar|aprova|permiss|seguran|como\s+funciona|o\s+que\s+(?:[eé]|voc[eê]\s+pode)|regra", re.I)


def problemas_de_atitude(resposta: str, mensagem_original: str = "") -> list:
    """Problemas de ATITUDE (vazia = ok): pedir licença em texto, citar etiqueta vazia ou dar desculpa pronta, numa
    resposta que não usa nenhuma ferramenta."""
    t = resposta or ""
    if not t.strip() or any(re.search(rf"<{tag}\b", t) for tag in _TAGS_ACAO):
        return []
    if _PERGUNTA_SOBRE_REGRAS.search(mensagem_original or ""):
        return []
    problemas = []
    if _PEDE_LICENCA.search(t) or _TAG_VAZIA.search(t):
        problemas.append("pediu aprovação/permissão em TEXTO (ou citou uma etiqueta vazia) em vez de usar a ferramenta — "
                         "o Zenith já mostra sozinho a janela de aprovação quando você coloca a etiqueta")
    if _ADIA.search(t) and not _USUARIO_ADIA.search(mensagem_original or ""):
        problemas.append("adiou o pedido (\"deixa pra depois\") em vez de FAZER agora — se for grande, entregue a 1ª parte e "
                         "anote o resto com <pendencia>texto</pendencia>")
    if _DESCULPA.search(t):
        problemas.append("deu uma desculpa pronta (\"não tenho forma física\", \"sou só uma IA\", \"está além das minhas "
                         "capacidades\") em vez de tentar: você TEM corpo e tem ferramentas (código Python, busca, câmera, "
                         "criar programa, criar habilidade)")
    return problemas


def pedido_de_acao(resposta: str, problemas: list, mensagem_original: str = "") -> str:
    lista = "\n".join(f"- {p}" for p in problemas)
    return ("[Verificação automática de atitude do Zenith] Sua resposta anterior tem o(s) problema(s):\n"
            f"{lista}\n\n"
            f"Pedido original do usuário: \"{mensagem_original}\"\n\n"
            "Refaça a resposta: diga em UMA frase o que vai fazer e COLOQUE a etiqueta certa AGORA (ex.: código Python em "
            "<executar_python> — para desenhar/gerar imagem use `from brain.zenith_img import autorretrato, meme, cartaz`; "
            "<ver_camera>/<ver_tela> para olhar; <buscar_web>; <criar_programa>; <criar_habilidade>). Não peça licença em "
            "texto, não cite etiqueta vazia. Só se for realmente impossível, diga exatamente o que falta e o que você faz "
            "no lugar. Mantenha a personalidade. Não mencione esta verificação.\n\nResposta anterior:\n<<<\n"
            + (resposta or "") + "\n>>>")


def pedido_de_correcao(resposta: str, problemas: list, mensagem_original: str = "") -> str:
    lista = "\n".join(f"- {p}" for p in problemas)
    return ("[Verificação automática de formato do Zenith] Sua resposta anterior tem problema(s) de formato:\n"
            f"{lista}\n\n"
            f"Pedido original do usuário: \"{mensagem_original}\"\n\n"
            "Reescreva a resposta INTEIRA corrigindo SÓ isso e mantendo o mesmo conteúdo e o mesmo tom. "
            "Não mencione esta verificação.\n\nResposta anterior:\n<<<\n" + (resposta or "") + "\n>>>")


# ======================================================================
#  Medidor
# ======================================================================
def estimar_tokens(texto: str) -> int:
    return max(0, (len(texto or "") + 3) // 4)


def barra(percentual: float, largura: int = 20) -> str:
    p = max(0.0, min(100.0, percentual))
    cheio = int(round(largura * p / 100.0))
    return "█" * cheio + "░" * (largura - cheio)


def listar_cartoes(pasta=None) -> str:
    cs = carregar_cartoes(pasta)
    aprendidos = [c for c in cs if c.origem == "aprendido"]
    linhas = [f"📖 Bíblia do Zenith — {len(cs)} cartões ({len(aprendidos)} aprendidos por mim) · regras de ouro e corpo vão SEMPRE no prompt."]
    for c in sorted(cs, key=lambda x: (x.origem != "base", -x.prioridade, x.id)):
        marca = {"base": "", "arquivo": " · seu arquivo", "aprendido": " · aprendido"}[c.origem]
        fixo = " · sempre p/ IA de nível básico" if c.sempre == "basico" else (" · SEMPRE" if c.sempre == "sim" else "")
        linhas.append(f"• {c.id} — {c.titulo}{marca}{fixo}\n   ativa com: {', '.join(c.palavras[:7])}{'…' if len(c.palavras) > 7 else ''}")
    linhas.append("Ver um: /biblia <id> · Apagar um aprendido: /biblia apagar <id> · Seus cartões: arquivos .md em config/biblia/ "
                  "(id igual ao de uma seção = substitui).")
    return "\n".join(linhas)
