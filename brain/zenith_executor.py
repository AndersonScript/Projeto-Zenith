# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_executor.py — Execução de código/terminal COM Gatekeeper.
#  Regra: nunca executa por conta própria. Toda ação sensível
#  primeiro vira uma "ação pendente" para o usuário aprovar.
# ============================================================

import json
import os
import subprocess
import sys
import re
import requests
from html.parser import HTMLParser
from dataclasses import dataclass, field
from brain.zenith_settings import TEMP_DIR
from brain import zenith_busca          # v21: busca na web SEM chave de API
from brain import zenith_img            # noqa: F401 — import estático: mantém a biblioteca de imagens no .exe
from brain import zenith_parar as parar  # v26 — botão/palavra PARAR: processos abertos aqui podem ser mortos

# v1.11 — o teto de 15 s matava download/raspagem (yt-dlp, pip install, build).
# Agora o limite vem de settings.json ("tempo_comando_s"), com 60 s de padrão e
# 1800 s (30 min) de máximo. TIMEOUT_SECONDS continua existindo como PISO: nenhum
# ajuste consegue deixar um comando com menos de 15 s.
TIMEOUT_SECONDS = 15
LIMITE_PADRAO_S = 60
LIMITE_MAX_S = 1800


def limite_s() -> int:
    """Quantos segundos um código/comando pode rodar antes de ser cancelado."""
    try:
        from brain.zenith_settings import SETTINGS_FILE
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            v = int(json.load(f).get("tempo_comando_s", LIMITE_PADRAO_S))
    except Exception:
        v = LIMITE_PADRAO_S
    return max(TIMEOUT_SECONDS, min(LIMITE_MAX_S, v))


class ExecucaoParada(Exception):
    """O usuário pediu pra parar (botão ⏹, "calma aí, Zenith"...) enquanto o código/comando rodava."""


def _rodar_processo(cmd, timeout, **kw):
    """Igual ao subprocess.run(capture_output, texto UTF-8) de antes — só que o processo fica REGISTRADO em
    zenith_parar: se alguém pedir pra parar, ele é morto de verdade (antes, nada conseguia interromper um script
    que travou ou que estava longo). Devolve um subprocess.CompletedProcess."""
    g = parar.geracao()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", **kw)
    parar.registrar_processo(p)
    try:
        saida, erro = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            p.communicate(timeout=5)
        except Exception:
            pass
        raise
    finally:
        parar.liberar_processo(p)
    if parar.cancelado_desde(g):
        raise ExecucaoParada()
    return subprocess.CompletedProcess(cmd, p.returncode, saida, erro)


# FEATURE (ler URL sem precisar de chave/API de terceiro): extrator de
# texto bem simples, só com o que já vem no Python (html.parser) — de
# propósito, pra não adicionar mais uma biblioteca nova só pra isso.
# Não é tão sofisticado quanto um parser de verdade (BeautifulSoup),
# mas dá conta do recado pra páginas de conteúdo normais (notícia,
# artigo, documentação, wiki).
class _ExtratorDeTexto(HTMLParser):
    _TAGS_IGNORAR = {"script", "style", "noscript", "svg", "nav", "header", "footer"}

    def __init__(self):
        super().__init__()
        self._pedacos: list = []
        self._profundidade_ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._TAGS_IGNORAR:
            self._profundidade_ignorar += 1
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._pedacos.append("\n")

    def handle_endtag(self, tag):
        if tag in self._TAGS_IGNORAR and self._profundidade_ignorar > 0:
            self._profundidade_ignorar -= 1

    def handle_data(self, data):
        if self._profundidade_ignorar == 0:
            texto = data.strip()
            if texto:
                self._pedacos.append(texto + " ")

    def texto_final(self) -> str:
        bruto = "".join(self._pedacos)
        # Compacta espaços/linhas em branco repetidas (o HTML de verdade
        # vem cheio de indentação/quebra de linha que não é texto real).
        bruto = re.sub(r"[ \t]+", " ", bruto)
        bruto = re.sub(r"\n\s*\n+", "\n\n", bruto)
        return bruto.strip()


def _extrair_texto_de_html(html: str) -> str:
    parser = _ExtratorDeTexto()
    try:
        parser.feed(html)
    except Exception:
        pass   # HTML malformado — devolve o que já tiver conseguido extrair até aqui
    return parser.texto_final()


@dataclass
class PendingAction:
    """Ação sensível gerada pela IA, esperando aprovação humana."""
    kind: str              # "python" | "terminal" | "serial"
    content: str           # código ou comando
    description: str = ""  # explicação em linguagem humana
    # FEATURE (ações em várias etapas): toda ação nasce sabendo qual foi o
    # PEDIDO ORIGINAL do usuário e em que passo da cadeia está — é o que
    # permite, depois de aprovada e executada, decidir sozinha se a tarefa
    # já terminou ou se falta mais um passo (ver continuar_cadeia() em
    # zenith_core.py). chain_step=0 significa "ainda não rodou nenhuma
    # ação nesta tarefa" (a primeira desta conversa).
    chain_original: str = ""
    chain_step: int = 0

    def preview(self) -> str:
        """Texto seguro para mostrar ao usuário ANTES de aprovar."""
        if self.kind in ("program", "learn", "skill_create", "skill_run", "observe"):   # v22/v23 — resumo antes de aprovar
            try:
                if self.kind == "program":
                    from brain import zenith_programa
                    return zenith_programa.preview_text(self.content)
                if self.kind == "skill_create":
                    from brain import zenith_habilidades
                    return zenith_habilidades.preview_criar(self.content)
                if self.kind == "skill_run":
                    from brain import zenith_habilidades
                    return zenith_habilidades.preview_usar(self.content)
                if self.kind == "observe":
                    from brain import zenith_observar
                    return zenith_observar.preview_text(self.content)
                from brain import zenith_conhecimento
                return zenith_conhecimento.preview_aprender(self.content)
            except Exception:
                pass
        if self.kind in ("video", "document", "organize"):    # v28 — resumo em português antes de aprovar
            try:
                if self.kind == "video":
                    from brain import zenith_video as _v
                    from brain.zenith_settings import CREATION_DIR as _cd
                    return _v.preview_text(self.content, str(_cd / "videos"))
                if self.kind == "document":
                    from brain import zenith_documentos as _d
                    return _d.preview_text(self.content)
                import json as _json
                from brain import zenith_organizar as _o
                return _o.formatar_plano(_json.loads(self.content))
            except Exception:
                pass
        if self.kind == "image_gen":                      # v27 — a pessoa vê o que vai ser pedido e que PODE TER CUSTO
            try:
                from brain import zenith_imagem_ia as _ia
                return f"[GERAR IMAGEM POR IA]\n{'─' * 40}\n{self.content.strip()[:600]}\n\n{_ia.aviso_de_custo('padrao')}"
            except Exception:
                pass
        linhas = self.content.strip().splitlines()
        corpo = "\n".join(linhas[:15])
        extra = f"\n... (+{len(linhas) - 15} linhas)" if len(linhas) > 15 else ""
        return f"[{self.kind.upper()}] {self.description}\n{'─' * 40}\n{corpo}{extra}"


class ZenithExecutor:

    def create_pending(self, kind: str, content: str, description: str = "") -> PendingAction:
        """Cria a ação pendente (NÃO executa nada aqui)."""
        return PendingAction(kind=kind, content=content.strip(), description=description)

    # ---------------- PYTHON ----------------
    def run_python(self, action: PendingAction, approved: bool) -> str:
        if not approved:
            return "⛔ Ação bloqueada: execução de código sem aprovação."
        script = TEMP_DIR / "_zenith_script_temp.py"
        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)      # v23: pasta nova/limpa (ex.: cópia de pendrive) não pode quebrar a execução
            script.write_text(action.content, encoding="utf-8")
            # CORREÇÃO (execução de código quebrada no .exe compilado):
            # sys.executable rodando via "python zenith_launcher.py" é
            # um python.exe de verdade — mas no .exe compilado é o
            # PRÓPRIO Zenith.exe, que não sabe rodar um .py sozinho por
            # padrão (abriria o app inteiro de novo). Ver
            # zenith_launcher.py::_try_run_as_script_runner para o
            # modo especial que resolve isso no lado do .exe.
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--zenith-run-script", str(script)]
            else:
                cmd = [sys.executable, str(script)]
            # v21: o script da IA pode fazer `from brain.zenith_img import meme` — fora do .exe
            # isso exige a pasta do projeto no PYTHONPATH (no .exe o módulo já vai dentro).
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            if not getattr(sys, "frozen", False):
                raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                env["PYTHONPATH"] = raiz + os.pathsep + env.get("PYTHONPATH", "")
            r = _rodar_processo(cmd, timeout=limite_s(), cwd=str(TEMP_DIR), env=env)     # v26: dá pra PARAR de verdade
            # CORREÇÃO (mensagem de sucesso mentirosa): antes isso aqui
            # devolvia SÓ r.stdout, ignorando completamente
            # r.returncode e r.stderr — se o script desse erro (ou
            # travasse antes de imprimir qualquer coisa) sem nada no
            # stdout, a pessoa via "✅ Código executado (sem saída de
            # texto)." como se tivesse dado tudo certo, quando na
            # verdade tinha falhado silenciosamente. Agora só mostra
            # sucesso de verdade quando o código termina sem erro.
            saida = (r.stdout or "").strip()
            erro = (r.stderr or "").strip()
            if r.returncode != 0:
                detalhe = erro or saida or f"código de saída {r.returncode}, sem mensagem de erro"
                return f"❌ O script terminou com erro (código {r.returncode}):\n{detalhe}"
            if saida:
                return saida
            if erro:
                # returncode 0 mas escreveu algo em stderr (comum em
                # avisos/warnings) — mostra mesmo assim, não esconde.
                return f"✅ Código executado (com avisos):\n{erro}"
            return "✅ Código executado (sem saída de texto)."
        except ExecucaoParada:
            return "⏹ Parei o código no meio, a pedido seu."
        except subprocess.TimeoutExpired:
            return (f"⏱️ Código cancelado: passou de {limite_s()}s. Se ele precisa de mais tempo, aumente "
                    "'tempo_comando_s' em config/settings.json (até 1800).")
        except Exception as e:
            return f"❌ Erro: {e}"
        finally:
            if script.exists():
                script.unlink()   # limpa o temporário

    # ---------------- BUSCA NA WEB ----------------
    # FEATURE (busca na web): diferente de python/terminal, isso aqui não
    # tem efeito colateral nenhum — só lê resultados públicos de busca.
    # Por isso ela pode rodar tanto pelo fluxo normal de aprovação
    # (approve_action) quanto automaticamente quando a permissão
    # "web_search" estiver em "always" (ver zenith_core.pensar()).
    def run_websearch(self, query: str, api_key: str = "") -> str:
        """v21 — SEM chave de API: usa DuckDuckGo/Bing/Wikipédia (zenith_busca). Se a pessoa TEM uma
        chave da Tavily, ela é tentada primeiro (opcional) e, se falhar, cai no buscador sem chave."""
        query = query.strip()
        if api_key:
            try:
                r = requests.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": query, "max_results": 5, "search_depth": "basic"},
                    timeout=15,
                )
                r.raise_for_status()
                resultados = r.json().get("results", [])
                if resultados:
                    linhas = [f"Resultados da busca por \"{query}\":"]
                    for item in resultados[:5]:
                        trecho = (item.get("content") or "").strip()
                        if len(trecho) > 400:
                            trecho = trecho[:400] + "..."
                        linhas.append(f"- {(item.get('title') or '').strip()} ({(item.get('url') or '').strip()}): {trecho}")
                    return "\n".join(linhas)
            except Exception:
                pass          # Tavily é só um extra: cai no buscador sem chave
        res = zenith_busca.buscar_texto(query, maximo=5)
        return zenith_busca.formatar_texto(query, res)

    def run_image_search(self, query: str, pasta, maximo: int = 3):
        """v21 — busca imagens SEM chave e baixa até `maximo` (com checagem de segurança).
        Devolve (texto_para_a_IA, [caminhos_baixados])."""
        query = query.strip()
        res = zenith_busca.buscar_imagens(query, maximo=max(maximo + 3, 6))
        arquivos = []
        if res.get("ok"):
            for i, it in enumerate(res["resultados"]):
                if len(arquivos) >= maximo:
                    break
                for url in (it.get("url"), it.get("miniatura")):
                    if not url:
                        continue
                    r = zenith_busca.baixar_imagem(url, pasta, nome=f"{query[:24]}_{i + 1}")
                    if r.get("ok"):
                        arquivos.append(r["path"])
                        break
        return zenith_busca.formatar_imagens(query, res, arquivos), arquivos

    # ---------------- LER UMA URL ESPECÍFICA ----------------
    # FEATURE (ler o conteúdo de uma URL) / CORREÇÃO (não devia precisar
    # de chave nenhuma pra isso): a primeira versão disso reaproveitava a
    # API da Tavily (que precisa de chave) até pra abrir um link que o
    # PRÓPRIO USUÁRIO já mandou — desnecessário, já que abrir uma URL e
    # extrair o texto é algo que dá pra fazer direto, sem intermediário
    # nenhum. Agora o caminho principal é uma requisição HTTP comum
    # (sem chave, sem custo, sem depender de terceiro); a Tavily (se
    # tiver chave configurada) só entra como PLANO B, pra páginas que
    # dependem pesado de JavaScript pra montar o conteúdo (onde uma
    # requisição comum só traria a casca vazia da página).
    def run_read_url(self, url: str, tavily_key: str = "") -> str:
        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return f"⚠️ '{url}' não parece um link válido (preciso de algo começando com http:// ou https://)."

        conteudo = ""
        erro_direto = ""
        try:
            r = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Zenith/1.0"})
            r.raise_for_status()
            conteudo = _extrair_texto_de_html(r.text)
        except Exception as e:
            erro_direto = str(e)

        # Página "vazia demais" (menos de ~200 caracteres de texto de verdade)
        # é sinal clássico de site que só monta o conteúdo via JavaScript no
        # navegador — uma requisição comum nunca vai ver esse texto.
        precisa_plano_b = erro_direto != "" or len(conteudo.strip()) < 200
        if precisa_plano_b and tavily_key:
            try:
                r2 = requests.post("https://api.tavily.com/extract",
                    json={"api_key": tavily_key, "urls": [url]}, timeout=20)
                r2.raise_for_status()
                data = r2.json()
                resultados = data.get("results", [])
                if resultados:
                    conteudo = (resultados[0].get("raw_content") or "").strip()
            except Exception:
                pass   # se o plano B também falhar, segue com o que já tinha (se tinha algo)

        if not conteudo.strip():
            if erro_direto:
                return f"❌ Erro abrindo o link: {erro_direto}"
            return (f"⚠️ Abri {url}, mas não achei texto de verdade pra extrair — a página " +
                "provavelmente depende de JavaScript pra montar o conteúdo (um app, não um " +
                "site tradicional). Tente outro link do mesmo assunto (uma busca costuma achar " +
                "uma versão em texto).")

        TETO = 12000  # não deixa uma página gigante estourar o contexto da IA
        if len(conteudo) > TETO:
            conteudo = conteudo[:TETO] + "\n[...conteúdo cortado, página muito grande...]"
        return f"Conteúdo de {url}:\n{conteudo}"

    # ---------------- TERMINAL ----------------
    def run_terminal(self, action: PendingAction, approved: bool) -> str:
        if not approved:
            return "⛔ Ação bloqueada: comando de terminal sem aprovação."
        try:
            r = _rodar_processo(action.content, shell=True, timeout=limite_s(), cwd=str(TEMP_DIR))   # v26
            if r.returncode == 0:
                return r.stdout or "✅ Comando executado."
            return f"❌ Erro no terminal:\n{r.stderr}"
        except ExecucaoParada:
            return "⏹ Parei o comando no meio, a pedido seu."
        except subprocess.TimeoutExpired:
            return (f"⏱️ Comando cancelado: passou de {limite_s()}s. Se ele precisa de mais tempo, aumente "
                    "'tempo_comando_s' em config/settings.json (até 1800).")
        except Exception as e:
            return f"❌ Erro: {e}"