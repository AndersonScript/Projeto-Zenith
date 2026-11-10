"""
Zenith — Comandos rápidos com "/" (resolvidos localmente, sem gastar IA).

Digitou algo que começa com "/" e é um comando conhecido? Responde aqui
mesmo, na hora, sem mandar nada pra IA, sem entrar no histórico da conversa
e sem poluir a memória de longo prazo. Texto que NÃO é comando conhecido
(inclusive caminhos de arquivo como "/home/x") passa direto pra IA como
sempre — `tratar()` devolve None.

É também o caminho barato pra ganhar função nova sem mexer na interface
do Godot (a parte mais frágil do projeto): comando novo = uma função aqui.

`tratar(texto, ctx)` devolve None (não é comando) ou um dict:
    {"resposta": str, "acao": None | "test_voice" | "nota_voz" | "pausar" | "retomar"
                                    | "diario" | "diagnostico" | "relatorio"}
(as "acao" são coisas que só o Cérebro sabe fazer — mexer em microfone, chamar a IA,
cancelar pendências — o comando só decide; quem executa é zenith_headless.py)
`ctx` é um dict com o que os comandos precisam do resto do sistema:
    ctx["settings"]  -> objeto de configurações (get/update)
    ctx["versao"]    -> texto da versão (opcional)
    ctx["memory"]    -> ZenithMemory (opcional; /memorias e /esquecer)
    ctx["conv_id"]   -> id da conversa ativa (opcional; /exportar_conversa)
    ctx["lembretes"] -> zenith_lembretes.Lembretes (opcional; padrão = o arquivo de sempre)
"""
import datetime
import re
from pathlib import Path

from brain import zenith_actionlog as _log
from brain import zenith_lembretes as _lembretes
from brain import zenith_modos as _modos
from brain import zenith_notes as _notas
from brain import zenith_pausa as _pausa
from brain import zenith_conhecimento as _conhec   # v22
from brain import zenith_contexto as _ctx          # v22
from brain import zenith_programa as _programa     # v22
from brain import zenith_busca as _busca           # v22
from brain import zenith_gemini as _gem            # v23
from brain import zenith_habilidades as _hab       # v23
from brain import zenith_pendencias as _pend       # v25
from brain import zenith_tema as _tema             # v25

_AJUDA = (
    "🧭 Comandos disponíveis (resolvidos aqui, sem gastar IA — exceto /diario):\n"
    "\n— Controle (Pilar 1) —\n"
    "• /pausar [motivo] — SILÊNCIO TOTAL: cancela pedidos pendentes, desliga o microfone e a fala, "
    "nada vai pra IA e ela não propõe ação até você usar /retomar\n"
    "• /retomar — libera de novo\n"
    "• /log [n] — últimas n ações que rodaram (ou foram negadas/vetadas)\n"
    "• /exportar_log — salva o histórico de ações em Markdown\n"
    "\n— Modos e memória —\n"
    "• /modo [estudo|lab|codigo|tutor|ensinar|quiz|debate|jogo|eletronica|normal] — muda o estilo da Zenith (sem mexer nas regras/aprovações)\n"
    "• /diario — a Zenith resume a conversa e guarda como memória 📎 (usa a IA)\n"
    "• /memorias [termo] — lista o que ela lembra, com um id curto\n"
    "• /esquecer <id> — esquece UMA memória (id de /memorias)\n"
    "• /exportar_conversa — salva a conversa atual em Markdown\n"
    "\n— Lembretes —\n"
    "• /lembrar <quando> <o quê> — ex.: /lembrar 15:30 entregar relatório · em 20min tirar o pão · "
    "amanhã 7h30 prova · sexta 14h reunião · 25/12 9h ligar\n"
    "• /lembretes — lista os pendentes · /lembrete_apagar <número>\n"
    "\n— Notas de laboratório —\n"
    "• /nota <texto> — anotação com data e hora (use #tags: /nota #exp3 tensão 4,98 V)\n"
    "• /nota_voz — a próxima coisa que você falar no microfone vira nota (não vai pro chat)\n"
    "• /notas [#tag] [n] — últimas notas (filtre por tag) · /tags — tags em uso\n"
    "• /exportar_notas — Markdown · /exportar_notas_csv [#tag] — CSV pro Excel\n"
    "\n— Inteligência, criar e conhecimento (v22) —\n"
    "• /inteligencia [max|equilibrado|economico] — quanto da conversa ela lembra e se raciocina antes de responder\n"
    "• /contexto [max|equilibrado|economico|desligado] — mostra/ajusta quanto da conversa vai junto de cada pergunta\n"
    "• /biblia [id] — cartões de conhecimento (inclui os que ela aprendeu) · /biblia apagar <id> apaga um aprendido\n"
    "• /programas — lista os programas/sites que ela criou · /parar_programa [nome] — fecha um que está rodando\n"
    "• /testar_busca — testa, com a sua internet, cada fonte de busca de texto e de imagem (✓/✗)\n"
    "• Escreva em config/ZENITH.md o que ela deve SEMPRE saber de você (reinicie depois de editar)\n"
    "\n— v23: modelo, habilidades, olhos e fundo —\n"
    "• /ajustes — consertos que ela propôs no próprio código · /ajuste ver|testar|aplicar|recusar|desfazer N · /codigo <arquivo> [inicio-fim]\n"
    "• /modelos — lista os modelos Gemini que a SUA chave enxerga · /modelo gemini <id> troca (ex.: gemini-3.5-flash)\n"
    "• /habilidades — o que ela criou sozinha · /habilidade ver|apagar|confiar|desconfiar <nome>\n"
    "• /observar [camera|tela] [segundos] [minutos] [motivo] — ela acompanha ao vivo (você aprova; o aviso de observação aparece) · /parar_observacao\n"
    "• /presenca [tela|camera|parar] — ela fica de olho o dia todo (uma aprovação só, a cada 15 s, até 8 h)\n"
    "• /velocidade [rapido|equilibrado|profundo] — o quanto ela PENSA antes de falar (rapido = conversa fluida; profundo = estudo/lição)\n"
    "• /tft [status|ligar|desligar|teste|enquadre rosto|busto|corpo|porta COM7|porta auto|fps N|zoom X|cor #hex] — a Zenith no display TFT do ESP32-S3 (USB)\n"
    "• /pendencias · /pendencia add|feito|apagar — o que você pediu e ela ainda não entregou (ela vê em TODA conversa)\n"
    "• /projeto [nome|novo nome|texto ...|ver|desligar] — o roteiro/briefing ativo que ela segue à risca (ex.: /projeto novo etec)\n"
    "• /tema [roxo|verde|rosa|amoled|claro|...|cor #hex|fundo #hex|padrao] — cores da interface (aplica na próxima abertura)\n"
    "• /fundo_avatar [transparente|solido|chroma|auto] [#cor] — se o fundo do avatar aparecer PRETO em outro PC, use solido\n"
    "\n— v26: parar, matemática e LaTeX —\n"
    "• /parar — para TUDO na hora (ou diga/escreva \"calma aí, Zenith\", \"para\", \"pare tudo\") · tem o botão ⏹ no topo\n"
    "• /imagem [pro] [16:9] <descrição> — cria uma imagem de verdade com IA (Gemini; pode ter custo)\n"
    "• /aparencia [cabelo #hex olhos #hex roupa #hex detalhe #hex | padrao] — as cores do autorretrato dela\n"
    "• /latex <equação> — desenha a equação em imagem (/latex claro … preto no branco · /latex transparente … PNG sem fundo)\n"
    "• /formula [mecanica|optica|derivadas|integrais|vetorial|ondas|maxwell] [página] · /formula buscar <palavra> — folhas de fórmulas\n"
    "• /derivar <f(x)> [em x] · /integrar <f(x)> [de a ate b] · /limite <f(x)> quando x->a — conta exata, conferida pelo programa\n"
    "\n— v28: vídeo, anexos, pastas, biblioteca e contas —\n"
    "• /video <operação> <arquivo> … — edita e cria vídeo (o original nunca é alterado). Digite só /video pra ver todas: cortar, gif, "
    "velocidade, audio, mudo, juntar, converter, frame, girar, redimensionar, narrar, e na v30: efeito, vertical (9:16 pra Shorts), transicao e legenda\n"
    "• /organizar <pasta> [limpar|organizar|tudo] [agressivo] — olha a pasta (só leitura), mostra o PLANO e você aprova; o inútil vai pra quarentena\n"
    "• /quarentena [desfazer [carimbo] | esvaziar confirmar] — lista as limpezas, devolve tudo ou apaga de verdade\n"
    "• /biblioteca [add <arquivo|pasta> | buscar <pergunta> | remover <nome>] — seus PDFs/apostilas/datasheets; ela responde citando arquivo e página\n"
    "• /conta <expressão> — conta exata, sem gastar IA (as contas escritas nas respostas dela também são conferidas sozinhas)\n"
    "• Anexe QUALQUER arquivo (zip, Word, Excel, PowerPoint, PDF, vídeo, código colado) e clique nele pra abrir a miniatura/prévia\n"
    "\n— v30: chaves, uma IA só e IA local —\n"
    "• /chaves — suas chaves por IA e quem está em espera · /chave add gemini <chave> soma OUTRA chave (troca automática quando a cota estoura)\n"
    "• /rota — uma IA só com as ferramentas de todas: quem conversa, quem vê imagem, quem cria imagem · /rota visao openai · /rota limpar\n"
    "• /local — IA local opcional no seu PC, sem chave (Ollama/LM Studio): /local ligar · /local baixar · /local papel reserva|principal\n"
    "\n— v1.7: conversa, cadernos, linguagens e PC —\n"
    "• /conversa [ligar|desligar|status] — microfone sempre aberto (uma aprovação por sessão; para de ouvir enquanto ela fala)\n"
    "• /cadernos [novo <assunto>|add <arquivo|pasta>|usar <nome>|perguntar <pergunta>|professora <tema>|apagar <nome>] — estudos com fonte e página\n"
    "• /linguagens — o que este PC já sabe compilar/rodar (sem instalar nada)\n"
    "• /instalar <pacote> — mostra versão e licença antes; com 'confirmar' pede a aprovação do pip\n"
    "• /dancar [BPM] [animada|suave|robotica] — dança no ritmo pedido · /movimentos encadear careta, pulo, dancar — em sequência\n"
    "• /local recomendar — mede a memória/CPU do PC e diz qual modelo local não trava\n"
    "\n— Diagnóstico —\n"
    "• /diagnostico — testa tudo (pastas, chaves, bibliotecas, voz, rede...) com ✓/⚠/✗\n"
    "• /relatorio — texto pra pedir ajuda (SEM chaves nem conversas)\n"
    "• /testar_voz — toca uma frase fixa e mostra o diagnóstico da voz (Edge-TTS / RVC)\n"
    "• /voz_emocao — liga/desliga a variação de tom e velocidade conforme a emoção\n"
    "• /avatar_diag — o que o Zenith achou pra importar avatar sozinho (Godot, projeto, pacote)\n"
    "• /versao — mostra a versão (e a data do build)\n"
    "• /sobre — quem criou o Zenith e a apresentação do projeto\n"
    "• /ajuda — esta lista"
)


def _pasta_exportacao() -> Path:
    from brain.zenith_settings import CREATION_DIR
    return Path(CREATION_DIR) / "exports"


def _carimbo() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def _numero(arg: str, padrao: int, maximo: int = 100) -> int:
    m = re.search(r"\d+", arg or "")
    if not m:
        return padrao
    return max(1, min(int(m.group()), maximo))


# ======================================================================================= v1.6.2
def _comando_ajuste(nome: str, arg: str, resp):
    """/ajustes · /ajuste ver|testar|aplicar|recusar|desfazer N · /codigo <arquivo> [inicio-fim].
    Quem escreve estes comandos é SEMPRE o usuário (a IA só pode usar /codigo, que apenas lê). Nada aqui roda código
    proposto, exceto `testar`, que roda numa cópia temporária a pedido dele."""
    from brain import zenith_autoajuste as _aj
    try:
        ger = _aj.instancia()
    except Exception as e:
        return resp(f"O autoajuste não está disponível agora ({e}).")
    p = (arg or "").split()
    if nome == "codigo" or (p and p[0].lower() in ("codigo", "código")):
        if nome != "codigo":
            p = p[1:]
        if not p:
            return resp("Use: /codigo brain/zenith_movimentos.py 100-160 (mostra o trecho do meu código; até 250 linhas).")
        ini = fim = None
        if len(p) > 1:
            m = re.match(r"^(\d+)(?:-(\d+))?$", p[1])
            if not m:
                return resp("O intervalo é assim: 100-160.")
            ini = int(m.group(1))
            fim = int(m.group(2)) if m.group(2) else ini + 59
        texto, erro = ger.ler_trecho(p[0], ini, fim)
        return resp(erro if erro else f"```python\n{texto}\n```")
    if not p or p[0].lower() in ("listar", "lista", "ajuda"):
        return resp(ger.resumo())
    acao, resto = p[0].lower(), p[1:]
    if acao not in ("ver", "testar", "aplicar", "recusar", "desfazer"):
        return resp("Não conheço esse passo. Use: /ajustes, /ajuste ver N, /ajuste testar N, /ajuste aplicar N, "
                    "/ajuste recusar N, /ajuste desfazer [N].")
    numero = None
    if resto and resto[0].lstrip("#").isdigit():
        numero = int(resto[0].lstrip("#"))
    if numero is None and acao != "desfazer":
        return resp(f"Diga o número do ajuste: /ajuste {acao} N (a lista está em /ajustes).")
    if acao == "ver":
        return resp(ger.ver(numero))
    if acao == "testar":
        if ger.carregar(numero) is None:
            return resp(f"Não existe o ajuste #{numero}.")
        return {"resposta": f"Vou testar o ajuste #{numero} numa cópia temporária (roda os testes do módulo antes e depois; "
                            "pode levar alguns minutos). Nada do seu Zenith muda.",
                "acao": "ajuste_testar", "args": {"id": numero}}
    if acao == "aplicar":
        sem_teste = any(x.lower() in ("sem-teste", "semteste", "sem_teste") for x in resto[1:])
        return resp(ger.aplicar(numero, sem_teste=sem_teste)["mensagem"])
    if acao == "recusar":
        return resp(ger.recusar(numero)["mensagem"])
    return resp(ger.desfazer(numero)["mensagem"])


def tratar(texto: str, ctx: dict = None):
    ctx = ctx or {}
    bruto = (texto or "").strip()
    m = re.match(r"^/([A-Za-zÀ-ÿ_]+)\b\s*(.*)$", bruto, re.S)
    if not m:
        return None
    nome = m.group(1).lower()
    arg = m.group(2).strip()

    def resp(t, acao=None):
        return {"resposta": t, "acao": acao}

    if nome in ("ajuda", "help", "comandos"):
        return resp(_AJUDA)

    # v1.5 — T8: seus próprios comandos (listar/criar/apagar). Só montam pedido.
    if nome == "comando":
        from brain import zenith_comandos_proprios as _cp
        return resp(_cp.tratar(arg))

    # v1.6.2 — ela propõe consertos no próprio código; você testa e aprova (/codigo só LÊ).
    if nome in ("ajustes", "ajuste", "codigo", "código"):
        return _comando_ajuste("codigo" if nome in ("codigo", "código") else nome, arg, resp)

    # v1.5 — T9: atualização com conferência de SHA-256, nunca automática.
    if nome in ("atualizar", "atualizacao", "atualização"):
        passo = (arg or "consultar").split()[0].lower() if arg else "consultar"
        if passo not in ("consultar", "checar", "baixar", "instalar"):
            return resp("Use /atualizar (ver a versão nova), /atualizar baixar (conferir o SHA-256) "
                        "ou /atualizar instalar (abrir o instalador).")
        passo = {"checar": "consultar"}.get(passo, passo)
        return {"resposta": "", "acao": "atualizar", "args": {"passo": passo}}

    if nome in ("versao", "versão", "version"):
        return resp("ℹ️ " + str(ctx.get("versao") or "Zenith"))

    if nome in ("sobre", "créditos", "creditos", "autor", "quemfez", "quem_fez"):
        from brain import zenith_creditos as _creditos
        return resp(_creditos.texto_chat())

    # v26 — PARAR (botão ⏹ do Corpo, /parar, ou "calma aí, Zenith"): vale até em silêncio total
    if nome in ("parar", "pare", "stop", "cancelar"):
        return resp("", acao="parar")

    # v1.7 — /conversa [ligar|desligar|status]: conversa por voz sem apertar o microfone a cada frase
    if nome in ("conversa", "conversar", "voz_continua"):
        modo = (arg.strip().lower().split() or [""])[0]
        if modo not in ("", "ligar", "on", "desligar", "off", "parar", "sair", "status"):
            return resp("Uso: /conversa ligar · /conversa desligar · /conversa status")
        # sem argumento é STATUS: ligar o microfone exige dizer "ligar" (Pilar 1)
        return {"resposta": "", "acao": "conversa", "args": {"modo": modo or "status"}}

    # Silêncio total (/pausar): comandos que falam com a IA, o microfone ou a voz NÃO rodam.
    # Fica ANTES de qualquer outro tratamento de propósito — o teste de regressão pegou um caso
    # em que /testar_voz e /nota_voz passavam porque eram tratados mais acima.
    if _pausa.ativo() and nome in ("diario", "diário", "testar_voz", "testarvoz", "nota_voz", "observar", "presenca", "presença"):
        return resp(_pausa.mensagem_bloqueio())

    if nome in ("log", "historico", "histórico"):
        return resp(_log.formatar_recentes(_numero(arg, 10, 50)))

    if nome == "exportar_log":
        destino = _pasta_exportacao() / f"zenith_log_{_carimbo()}.md"
        try:
            n = _log.exportar_markdown(destino)
            return resp(f"💾 {n} evento(s) exportados para:\n{destino}")
        except Exception as e:
            return resp(f"❌ Não consegui exportar o log: {e}")

    if nome in ("nota", "anotar"):
        if not arg:
            return resp("📝 Use assim: /nota <o que você quer anotar>")
        ok = _notas.adicionar(arg, origem="texto")
        return resp("📝 Anotado." if ok else "❌ Não consegui salvar a nota.")

    if nome == "nota_voz":
        return resp("🎙️ Ok — aperte o microfone e fale. O que eu ouvir vira NOTA "
                    "(não vai pro chat). Vale só pra próxima fala.", acao="nota_voz")

    if nome == "notas":
        tag = next((t for t in arg.split() if t.startswith("#")), "")
        resto = " ".join(t for t in arg.split() if not t.startswith("#"))
        return resp(_notas.formatar(_numero(resto, 10, 100), tag=tag))

    if nome == "tags":
        usadas = _notas.tags_usadas()
        if not usadas:
            return resp("🏷️ Nenhuma tag ainda. Escreva #tag dentro da nota: /nota #experimento3 medi 4,98 V")
        return resp("🏷️ Tags em uso:\n" + "\n".join(f"• #{t} — {n} nota(s)" for t, n in usadas[:30])
                    + "\nVeja as notas de uma tag com /notas #tag")

    if nome in ("exportar_notas_csv", "notas_csv"):
        tag = next((t for t in arg.split() if t.startswith("#")), "")
        sufixo = f"_{_notas.normalizar_tag(tag)}" if tag else ""
        destino = _pasta_exportacao() / f"zenith_notas{sufixo}_{_carimbo()}.csv"
        try:
            n = _notas.exportar_csv(destino, tag=tag)
            return resp(f"💾 {n} nota(s) exportadas em CSV (separador ';', abre direto no Excel):\n{destino}")
        except Exception as e:
            return resp(f"❌ Não consegui exportar as notas: {e}")

    if nome == "exportar_notas":
        destino = _pasta_exportacao() / f"zenith_notas_{_carimbo()}.md"
        try:
            n = _notas.exportar_markdown(destino)
            return resp(f"💾 {n} nota(s) exportadas para:\n{destino}")
        except Exception as e:
            return resp(f"❌ Não consegui exportar as notas: {e}")

    if nome in ("testar_voz", "testarvoz"):
        return resp("🔊 Testando a voz...", acao="test_voice")

    if nome in ("voz_emocao", "voz_emoção"):
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        novo = not bool(cfg.get("voice_expression_modulation", True))
        cfg.update({"voice_expression_modulation": novo})
        return resp("🎭 Variação de tom/velocidade por emoção: " + ("LIGADA" if novo else "DESLIGADA") + ".")

    if nome in ("avatar_diag", "avatardiag", "diag_avatar"):
        # v18 — diagnóstico da importação automática de avatar: mostra o que foi
        # (ou não) encontrado, sem rodar o Godot nem mudar nada.
        try:
            from brain import zenith_vrm_import as vi
            from brain.zenith_settings import BASE_DIR
            cfg = ctx.get("settings")
            env = vi.localizar_ambiente(BASE_DIR, cfg.get if cfg is not None else None)
            linhas = ["🔎 Importação automática de avatar — o que eu achei:",
                      f"• Editor do Godot: {env['godot_bin'] or 'NÃO ACHEI'}",
                      f"• Projeto Godot: {env['project_dir'] or 'NÃO ACHEI'}",
                      f"• Zenith.pck em uso: {env['pck_destino'] or 'NÃO ACHEI'}",
                      f"• Preset de exportação: {env['export_preset']}"]
            if env["faltando"]:
                linhas.append("⚠ " + vi.explicar_faltando(env["faltando"], BASE_DIR))
            else:
                linhas.append("✓ Tudo encontrado — \"Adicionar avatar\" deve funcionar.")
            return resp("\n".join(linhas))
        except Exception as e:
            return resp(f"❌ Não consegui fazer o diagnóstico: {e}")

    # ------------------------------------------------------------------
    # v18 — controle (Pilar 1), modos, lembretes, memória, exportação, diagnóstico
    # ------------------------------------------------------------------
    if nome in ("pausar", "silencio", "silêncio", "panico", "pânico"):
        if _pausa.pausar(arg):
            return resp("⏸️ SILÊNCIO TOTAL ligado. Cancelei o que estava pendente, desliguei o microfone e "
                        "a fala. Não vou mandar nada pra IA nem propor ações até você digitar /retomar.",
                        acao="pausar")
        return resp(_pausa.mensagem_bloqueio())

    if nome in ("retomar", "liberar", "continuar"):
        if _pausa.retomar():
            return resp("▶️ Liberado. Voltei ao normal — a aprovação de ações continua valendo, como sempre.",
                        acao="retomar")
        return resp("▶️ Já estava liberado.")

    # ---------- v22: programas criados pela Zenith ----------
    if nome == "programas":
        return resp(_programa.listar())

    if nome in ("projetos", "biblioteca_zenith", "bibliotecazenith", "meus_projetos", "criacoes", "criações"):
        # v1.6 — Biblioteca/Projetos Zenith: o que ela criou, por assunto (programas por linguagem, sites, imagens, vídeos, documentos)
        from brain import zenith_projetos as _pj
        return resp(_pj.formatar_texto(_pj.indexar()), acao="projetos_enviar")

    if nome in ("parar_programa", "pararprograma"):
        fechados = _programa.parar(arg)
        if fechados:
            return resp("⏹️ Fechei: " + ", ".join(fechados) + ".")
        return resp("⏹️ Nenhum programa meu estava rodando" + (f" com o nome '{arg}'" if arg else "")
                    + ". (/programas mostra os que existem.)")

    # ---------- v22: Bíblia (cartões) ----------
    if nome in ("biblia", "bíblia", "cartoes", "cartões"):
        partes = arg.split()
        if partes and partes[0].lower() in ("apagar", "esquecer", "remover") and len(partes) > 1:
            return resp(_conhec.apagar_aprendizado(partes[1]))
        if partes:
            alvo = partes[0].lower()
            c = next((x for x in _conhec.carregar_cartoes() if x.id.lower() == alvo), None)
            if c is None:
                return resp(f"❌ Não achei o cartão '{alvo}'.\n" + _conhec.listar_cartoes())
            return resp(f"📖 {c.titulo} (id: {c.id})\n\n" + c.texto())
        return resp(_conhec.listar_cartoes())

    if nome in ("testar_busca", "testarbusca"):
        return resp(_busca.texto_autoteste())

    # ---------- v23: modelo do Gemini ----------
    if nome in ("modelos", "modelo_lista"):
        return resp("🧠 Consultando os modelos que a sua chave do Gemini enxerga…", acao="listar_modelos")

    if nome == "modelo":
        cfg = ctx.get("settings")
        core = ctx.get("core")
        partes = arg.split()
        atual = _gem.normalizar(cfg.get("gemini_modelo", "")) if cfg is not None else ""
        em_uso = getattr(core, "_modelo_em_uso", "") if core is not None else ""
        if partes and cfg is not None and partes[0].lower() in ("openai", "claude", "llama", "openrouter", "groq"):
            # v1.6.1 — modelo das outras IAs (antes só dava para trocar o do Gemini)
            from brain import zenith_modelos as _mod
            slot = "claude" if partes[0].lower() in ("openrouter", "llama") else partes[0].lower()
            ov = dict(cfg.get("modelos_override", {}) or {})
            if len(partes) == 1:
                return resp(f"🧠 Modelo da {_mod.NOMES.get(slot, slot)}: {ov.get(slot) or _mod.padrao(slot)}"
                            + ("" if ov.get(slot) else " (padrão do Zenith; se a sua conta não enxergar, ele procura outro sozinho)")
                            + f"\nTrocar: /modelo {partes[0].lower()} <nome-do-modelo> · Voltar ao padrão: /modelo {partes[0].lower()} auto")
            alvo = partes[1].strip()
            if alvo.lower() == "auto":
                ov.pop(slot, None)
                ov.pop("llama", None) if slot == "claude" else None
                cfg.update({"modelos_override": ov})
                return resp(f"🧠 {_mod.NOMES.get(slot, slot)}: voltou ao modelo padrão ({_mod.padrao(slot)}).")
            if not re.match(r"^[A-Za-z0-9._:/\-]{2,100}$", alvo):
                return resp("❌ Nome de modelo inválido. Exemplo: /modelo groq llama-3.3-70b-versatile")
            ov[slot] = alvo
            if slot == "claude":
                ov["llama"] = alvo
            cfg.update({"modelos_override": ov})
            return resp(f"🧠 {_mod.NOMES.get(slot, slot)}: vou usar {alvo} a partir da próxima mensagem. Teste com o botão "
                        "\"Testar todas as chaves\" (Configurações > Chaves & IAs).")
        if not partes or cfg is None:
            return resp(f"🧠 Modelo do Gemini: {atual or _gem.MODELO_PADRAO}"
                        + (f" (último que respondeu: {em_uso})" if em_uso else "")
                        + f"\nSe ele falhar, tento: {', '.join(_gem.cadeia_de_modelos(atual)[1:]) or '—'}."
                        + "\nVer os disponíveis: /modelos · Trocar: /modelo gemini <id> · Voltar ao padrão: /modelo auto"
                        + "\nOutras IAs: /modelo openai|groq|openrouter <modelo>")
        if partes[0].lower() == "auto":
            cfg.update({"gemini_modelo": _gem.MODELO_PADRAO})
            return resp(f"🧠 Modelo do Gemini: {_gem.MODELO_PADRAO} (padrão).")
        alvo = partes[1] if partes[0].lower() == "gemini" and len(partes) > 1 else partes[0]
        alvo = _gem.normalizar(alvo)
        if not re.match(r"^gemini-[a-z0-9.\-]+$", alvo, re.I):
            return resp("❌ Nome de modelo inválido. Exemplo: /modelo gemini gemini-3.5-flash (veja /modelos).")
        cfg.update({"gemini_modelo": alvo})
        return resp(f"🧠 Modelo do Gemini: {alvo}. Vale a partir da próxima mensagem. "
                    f"(Se o nome não existir pra sua chave, uso os de reserva e aviso no console.)")

    # ---------- v25: pendências, projeto ativo e tema ----------
    if nome in ("pendencias", "pendências", "pendencia", "pendência"):
        partes = arg.split(None, 1)
        sub = partes[0].lower() if partes else ""
        resto = partes[1].strip() if len(partes) > 1 else ""
        if nome.startswith("pendencias") or nome.startswith("pendências") or not sub:
            return resp(_pend.resumo_lista())
        if sub in ("add", "novo", "adicionar") and resto:
            p_ = _pend.adicionar(resto, origem="você")
            return resp(f"📌 Anotado: {p_['id']}. {p_['texto']}" if p_ else "📌 Não consegui anotar (texto vazio ou lista cheia: 40).")
        if sub in ("feito", "concluir", "ok") and resto:
            return resp("📌 Pendência concluída." if _pend.concluir(resto) else "📌 Não achei essa pendência (veja /pendencias).")
        if sub in ("apagar", "remover", "del") and resto:
            return resp("📌 Pendência apagada." if _pend.apagar(resto) else "📌 Não achei essa pendência (veja /pendencias).")
        return resp("📌 Uso: /pendencias · /pendencia add <texto> · /pendencia feito <número> · /pendencia apagar <número>")

    if nome in ("projeto", "projetos"):
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        partes = arg.split(None, 2)
        sub = partes[0].lower() if partes else ""
        ativo = cfg.get("projeto_ativo", "") or ""
        if not sub:
            lista = ", ".join(_pend.projetos()) or "(nenhum ainda)"
            return resp(f"📁 Projeto ativo: {ativo or 'nenhum'}.  Projetos: {lista}.\nUsar: /projeto <nome> · Criar: /projeto novo <nome> [roteiro] · "
                        "Acrescentar: /projeto texto <texto> · Ler: /projeto ver · Desligar: /projeto desligar")
        if sub == "novo" and len(partes) > 1:
            try:
                n = _pend.criar(partes[1], partes[2] if len(partes) > 2 else "")
            except ValueError as e:
                return resp(f"📁 {e}")
            cfg.update({"projeto_ativo": n})
            return resp(f"📁 Projeto '{n}' criado e ATIVO. Agora ela segue o que estiver nele em toda mensagem. "
                        "Cole o roteiro com /projeto texto <roteiro> (ou edite config/projetos/" + n + ".md).")
        if sub in ("texto", "roteiro", "add") and len(partes) > 1:
            if not ativo:
                return resp("📁 Nenhum projeto ativo. Crie um: /projeto novo <nome>")
            trecho = arg.split(None, 1)[1]
            return resp("📁 Acrescentado ao projeto." if _pend.acrescentar(ativo, trecho) else
                        "📁 Não consegui acrescentar (texto suspeito, vazio ou o projeto passou de 12 mil caracteres).")
        if sub == "ver":
            corpo = _pend.ler_projeto(ativo).strip() if ativo else ""
            return resp(f"📁 {ativo}:\n{corpo[:3000]}" + ("\n…" if len(corpo) > 3000 else "") if corpo else "📁 Nenhum projeto ativo (ou vazio).")
        if sub in ("desligar", "off", "nenhum"):
            cfg.update({"projeto_ativo": ""})
            return resp("📁 Nenhum projeto ativo agora (o arquivo continua guardado).")
        if sub in ("apagar", "remover") and len(partes) > 1:
            if _pend.apagar_projeto(partes[1]):
                if _pend.nome_valido(partes[1]) == ativo:
                    cfg.update({"projeto_ativo": ""})
                return resp("📁 Projeto apagado.")
            return resp("📁 Não achei esse projeto.")
        if _pend.existe(sub):
            cfg.update({"projeto_ativo": _pend.nome_valido(sub)})
            return resp(f"📁 Projeto ativo: {_pend.nome_valido(sub)}.")
        return resp(f"📁 Não existe o projeto '{sub}'. Crie com /projeto novo {sub}.")

    if nome == "tema":
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        partes = arg.split()
        sub = partes[0].lower() if partes else ""
        valor = partes[1] if len(partes) > 1 else ""
        if not sub:
            return resp(f"🎨 Tema atual: {cfg.get('ui_tema_preset', 'ciano')}"
                        + (f", destaque {cfg.get('ui_tema_destaque')}" if cfg.get("ui_tema_destaque") else "")
                        + (f", fundo {cfg.get('ui_tema_fundo')}" if cfg.get("ui_tema_fundo") else "") + ".\n" + _tema.lista_texto())
        if sub in ("padrao", "padrão", "reset", "normal"):
            cfg.update({"ui_tema_preset": "ciano", "ui_tema_destaque": "", "ui_tema_fundo": ""})
            return resp("🎨 Tema padrão (ciano). Reabra o Zenith pra ver.", acao="ui_tema")
        if sub in ("cor", "destaque", "fundo"):
            if not _tema.eh_hex(valor):
                return resp("🎨 Use uma cor assim: #ff8800 (6 dígitos). Ex.: /tema cor #ff8800 · /tema fundo #101820")
            cfg.update({("ui_tema_fundo" if sub == "fundo" else "ui_tema_destaque"): _tema.normalizar_hex(valor)})
            return resp(f"🎨 {'Fundo' if sub == 'fundo' else 'Destaque'}: {_tema.normalizar_hex(valor)}. Reabra o Zenith pra ver.", acao="ui_tema")
        if sub in _tema.PRESETS:
            cfg.update({"ui_tema_preset": sub, "ui_tema_destaque": "", "ui_tema_fundo": ""})
            return resp(f"🎨 Tema: {sub}. Reabra o Zenith pra ver (a interface é montada ao iniciar)."
                        + (" (Modo claro é experimental.)" if sub == "claro" else ""), acao="ui_tema")
        return resp("🎨 Não conheço esse tema. " + _tema.lista_texto())

    # ---------- v24: display TFT ----------
    if nome == "tft":
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        partes = arg.split()
        sub = partes[0].lower() if partes else "status"
        valor = partes[1] if len(partes) > 1 else ""
        if sub == "status":
            return resp("", acao="tft_status")
        if sub in ("ligar", "on"):
            cfg.update({"tft_ativo": True})
            return resp("🖥 TFT ligado: procuro a placa ESP32-S3 na USB.", acao="tft")
        if sub in ("desligar", "off"):
            cfg.update({"tft_ativo": False})
            return resp("🖥 TFT desligado.", acao="tft")
        if sub in ("teste", "test"):
            return resp("🖥 Mandando um quadro de teste pra placa…", acao="tft_teste")
        if sub in ("portas", "listar"):        # v1.0.1 — "está na COM5 e ele lê a COM7": agora dá pra ver
            try:
                from serial.tools import list_ports as _lp
                achadas = list(_lp.comports())
            except Exception as e:
                try:                                   # v1.17 (port celular): no celular não há porta USB; o caminho é o Wi-Fi
                    from brain import zenith_plataforma
                    if zenith_plataforma.detectar() == "android":
                        return resp("🖥 No celular não há porta USB para a TFT. Use o Wi-Fi do carrinho: /tft porta wifi:auto "
                                    "(ou /tft porta wifi:IP).")
                except Exception:
                    pass
                return resp(f"❌ Não consegui listar as portas: {e}. Falta o pyserial? (pip install pyserial)")
            if not achadas:
                return resp("🖥 Nenhuma porta COM encontrada. A placa está ligada e o cabo é de DADOS (não só de carga)?")
            try:
                from brain.zenith_tft import VIDS_PLACA as _vids
            except Exception:
                _vids = {0x303A}
            linhas = ["🖥 Portas do computador:"]
            _da_placa = []
            for _p in achadas:
                _vid = getattr(_p, "vid", None)
                _desc = str(getattr(_p, "description", "") or "")
                _vid_txt = f"VID {_vid:04X}" if _vid else "VID ----"
                if "bluetooth" in _desc.lower():
                    _marca = "  (Bluetooth: não serve pra placa)"
                elif _vid in _vids:
                    _marca = "  ← a placa (use esta)"
                    _da_placa.append(_p.device)
                else:
                    _marca = ""
                linhas.append(f"• {_p.device} · {_vid_txt} · {_desc}{_marca}")
            linhas.append(("Use: /tft porta " + _da_placa[0] + "   e depois /tft teste") if _da_placa
                          else "Nenhuma porta parece ser a placa. Confira se o cabo é de DADOS e se o driver "
                               "do conversor USB-serial (CH340/CH343/CP210x) está instalado.")
            return resp("\n".join(linhas))
        if sub == "porta":
            if not valor:
                return resp("🖥 Uso: /tft porta COM5 · /tft porta wifi:auto (acha o carrinho) · /tft porta wifi:IP · /tft porta auto.\n"
                            "Dica: /tft portas mostra qual COM é a placa.")
            if valor.lower() != "auto" and not re.match(r"^(COM\d{1,3}|/dev/tty[A-Za-z0-9._-]+|(wifi:|tcp://)[A-Za-z0-9._-]+(:\d{2,5})?)$", valor, re.I):
                return resp("❌ Porta inválida. Exemplos: COM7 · /dev/ttyACM0 · wifi:auto · wifi:carrinho.local · wifi:192.168.0.50 · auto")
            cfg.update({"tft_porta": "" if valor.lower() == "auto" else valor})
            return resp(f"🖥 Porta do TFT: {valor}.", acao="tft")
        if sub in ("enquadre", "enquadramento", "quadro"):
            alvo = valor.lower()
            if alvo not in ("rosto", "busto", "corpo"):
                return resp("🖥 Uso: /tft enquadre rosto (cabeça e ombros) · busto (peito pra cima, braços aparecem) · corpo (inteira)")
            cfg.update({"tft_enquadre": alvo})
            return resp(f"🖥 Enquadre do TFT: {alvo}. Ajuste fino: /tft zoom.", acao="tft")
        if sub in ("fps", "zoom", "cor"):
            try:
                if sub == "fps":
                    cfg.update({"tft_fps": max(1, min(30, int(valor)))})
                elif sub == "zoom":
                    cfg.update({"tft_zoom": max(0.3, min(3.0, float(valor.replace(",", "."))))})
                else:
                    if not re.match(r"^#[0-9a-fA-F]{6}$", valor):
                        raise ValueError
                    cfg.update({"tft_cor": valor})
            except ValueError:
                return resp(f"❌ Valor inválido pra {sub}. Exemplos: /tft fps 12 · /tft zoom 1.3 · /tft cor #101830")
            return resp(f"🖥 TFT {sub} = {valor}. Vale já.", acao="tft")
        return resp("🖥 Uso: /tft [status|portas|ligar|desligar|teste|porta COM5|porta wifi:IP|porta auto|fps N|zoom X|cor #hex]")

    # ---------- v24: velocidade (raciocínio) ----------
    if nome in ("velocidade", "rapidez"):
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        alvo = (arg.split() or [""])[0].lower()
        apelidos = {"rapido": "rapido", "rápido": "rapido", "fluido": "rapido", "conversa": "rapido",
                    "equilibrado": "equilibrado", "normal": "equilibrado", "medio": "equilibrado",
                    "profundo": "profundo", "estudo": "profundo", "lento": "profundo", "pensar": "profundo"}
        atual = cfg.get("velocidade", "rapido")
        if not alvo:
            return resp(f"⚡ Velocidade: {atual}.\n• rapido — conversa fluida (pensa pouco em papo casual; mais em conta/código)\n"
                        "• equilibrado — pensa um pouco mais\n• profundo — pensa o máximo (estudo, lição, projeto difícil)\n"
                        "Trocar: /velocidade rapido|equilibrado|profundo. (O modo econômico de Configurações sempre pensa o mínimo.)")
        novo = apelidos.get(alvo)
        if novo is None:
            return resp("❌ Use: /velocidade rapido | equilibrado | profundo")
        cfg.update({"velocidade": novo})
        return resp(f"⚡ Velocidade: {novo}. Vale a partir da próxima mensagem.")

    # ---------- v23: habilidades que ela cria ----------
    if nome in ("habilidades", "skills"):
        return resp(_hab.resumo_lista(ctx.get("settings")))

    if nome in ("habilidade", "skill"):
        cfg = ctx.get("settings")
        partes = arg.split()
        sub = partes[0].lower() if partes else ""
        alvo = partes[1].lower() if len(partes) > 1 else ""
        if sub not in ("ver", "apagar", "confiar", "desconfiar") or not alvo:
            return resp("🧩 Uso: /habilidade ver <nome> · apagar <nome> · confiar <nome> (roda sem perguntar) · "
                        "desconfiar <nome>. Lista: /habilidades")
        if not _hab.existe(alvo):
            return resp(f"🧩 Não existe a habilidade '{alvo}'. Veja /habilidades.")
        if sub == "ver":
            cod = _hab.ler_codigo(alvo)
            return resp(f"🧩 {alvo} — {_hab.descricao_de(alvo)}\n{'─' * 30}\n{cod[:3500]}" + ("\n…" if len(cod) > 3500 else ""))
        if sub == "apagar":
            _hab.apagar(alvo)
            if cfg is not None:
                cfg.update({"habilidades_confiaveis": [n for n in _hab.confiaveis(cfg) if n != alvo]})
            return resp(f"🧩 Habilidade '{alvo}' apagada.")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        lista = [n for n in _hab.confiaveis(cfg) if n != alvo]
        if sub == "confiar":
            lista.append(alvo)
            cfg.update({"habilidades_confiaveis": lista})
            return resp(f"🧩 '{alvo}' agora roda SEM pedir aprovação a cada uso (a lista negra do Gatekeeper continua "
                        f"valendo). Desfaça com /habilidade desconfiar {alvo}.")
        cfg.update({"habilidades_confiaveis": lista})
        return resp(f"🧩 '{alvo}' volta a pedir aprovação a cada uso.")

    # ---------- v23: observação ao vivo ----------
    if nome in ("observar", "observacao", "observação"):
        tipo, intervalo, minutos, motivo = "camera", None, None, []
        cfg = ctx.get("settings")
        for tok in arg.split():
            baixo = tok.lower()
            if baixo in ("tela", "screen", "monitor"):
                tipo = "screen"
            elif baixo in ("camera", "câmera", "cam", "webcam"):
                tipo = "camera"
            elif tok.isdigit() and intervalo is None:
                intervalo = int(tok)
            elif tok.isdigit() and minutos is None:
                minutos = int(tok)
            else:
                motivo.append(tok)
        return {"resposta": f"👁 Vou pedir a sua aprovação pra observar {'a tela' if tipo == 'screen' else 'a câmera'}…",
                "acao": "observar",
                "args": {"tipo": tipo, "intervalo": intervalo or (cfg.get("observar_intervalo_s", 20) if cfg is not None else 20),
                         "minutos": minutos or (cfg.get("observar_max_minutos", 15) if cfg is not None else 15),
                         "motivo": " ".join(motivo)}}

    if nome in ("movimentos", "movimento"):
        # v1.6 — lista, toca e apaga movimentos do avatar
        from brain import zenith_movimentos as _mv
        lib = _mv.biblioteca()
        partes = arg.strip().split()
        if not partes or (nome == "movimentos" and partes[0].lower() in ("listar", "lista")):
            prontos = [n for n, c in sorted(lib.items()) if c.get("autor") == "zenith"]
            criados = [n for n, c in sorted(lib.items()) if c.get("autor") != "zenith"]
            txt = ("Movimentos do avatar:\n  Prontos: " + ", ".join(prontos) + "\n  Criados: " + (", ".join(criados) or "nenhum ainda") +
                   "\nPara ver um: /movimento <nome>. Para apagar um criado: /movimentos apagar <nome>. "
                   "Peça \"crie um movimento de ...\" e ela inventa um novo.")
            return resp(txt)
        if partes[0].lower() == "apagar" and len(partes) > 1:
            if _mv.apagar(partes[1]):
                return resp(f"Apaguei o movimento {partes[1]}.", acao="mov_recarregar")
            return resp(f"Não achei um movimento criado chamado {partes[1]} (os prontos não podem ser apagados).")
        if partes[0].lower() in ("encadear", "seguidos", "fila", "sequencia", "sequência") and len(partes) > 1:
            # v1.7 (T11c) — "faz uma careta, pula e dança"
            texto = " ".join(partes[1:])
            nomes = list(_mv.inferir_do_pedido(texto, set(lib)))
            if not nomes:
                nomes = [x.strip().lower() for x in re.split(r"[,;/]|\s+e\s+", texto) if x.strip()]
            fila = _mv.encadear(nomes, _mv.escala_do_pedido(arg), disponiveis=set(lib))
            if not fila:
                return resp("Não achei esses movimentos. Use /movimentos para ver a lista.")
            return {"resposta": "Tocando em sequência: " + " → ".join(f["nome"] for f in fila)
                             + (" (mais devagar)" if fila[0]["escala"] > 1 else ""),
                    "acao": "mov_fila", "args": {"fila": fila}}
        alvo = partes[0].lower()
        if alvo in lib:
            return {"resposta": f"Tocando: {alvo}. ({lib[alvo].get('descricao', '')})", "acao": "mov_tocar",
                    "args": {"nome": alvo, "escala": _mv.escala_do_pedido(arg)}}
        return resp(f"Não conheço o movimento \"{alvo}\". Use /movimentos para ver a lista.")

    if nome in ("presenca", "presença"):
        # v1.4 — "ela sempre olhando": atalho do /observar para o dia todo (a cada 15 s, até 8 h), com UMA aprovação.
        # Continua valendo o Pilar 1: aprovação, indicador visível e /parar_observacao a qualquer momento.
        baixo = arg.strip().lower()
        if baixo in ("parar", "desligar", "off", "sair", "para"):
            return resp("Parando a presença…", acao="parar_observacao")
        tipo = "camera" if baixo.startswith(("cam", "câm", "web")) else "screen"
        return {"resposta": f"Vou pedir a sua aprovação para ficar de olho {'na câmera' if tipo == 'camera' else 'na tela'} "
                            "enquanto você trabalha. Você pode parar quando quiser com /presenca parar.",
                "acao": "observar",
                "args": {"tipo": tipo, "intervalo": 15, "minutos": 480,
                         "motivo": "presença: acompanhar o que estou fazendo e ajudar sem eu pedir; só fale quando tiver algo útil"}}

    if nome in ("parar_observacao", "parar_observação", "parar_observar", "pararobservacao"):
        return resp("👁 Parando a observação…", acao="parar_observacao")

    # ---------- v23: fundo da janela do avatar ----------
    if nome in ("fundo_avatar", "fundo"):
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        partes = arg.split()
        modos = {"auto": "auto", "automatico": "auto", "automático": "auto", "transparente": "transparente",
                 "solido": "solido", "sólido": "solido", "preto": "solido", "chroma": "chroma", "verde": "chroma"}
        if not partes:
            return resp(f"🖼 Fundo do avatar: {cfg.get('avatar_fundo_modo', 'auto')} (cor {cfg.get('avatar_fundo_cor', '#0b1020')}).\n"
                        "Opções: transparente (normal) · solido (se aparecer um quadrado PRETO em outro PC) · "
                        "chroma (verde, pra OBS) · auto. Exemplo: /fundo_avatar solido #101830")
        modo = modos.get(partes[0].lower())
        if modo is None:
            return resp("❌ Use: /fundo_avatar transparente | solido | chroma | auto  (opcional: uma cor, ex.: #101830)")
        novo = {"avatar_fundo_modo": modo}
        for p_ in partes[1:]:
            if re.match(r"^#[0-9a-fA-F]{6}$", p_):
                novo["avatar_fundo_cor"] = p_
        cfg.update(novo)
        return resp(f"🖼 Fundo do avatar: {modo}. Aplicado agora." + (" (Se for 'solido' e a cor não agradar, passe outra: /fundo_avatar solido #101830.)" if modo == "solido" else ""),
                    acao="fundo_avatar")

    # ---------- v22: contexto da conversa e "nível de inteligência" ----------
    if nome in ("contexto", "tokens"):
        cfg = ctx.get("settings")
        if arg and cfg is not None:
            novo = arg.split()[0].lower()
            novo = "desligado" if novo in ("desligado", "off", "nenhum") else _ctx.normalizar_modo(novo)
            cfg.update({"contexto_modo": novo})
            return resp(f"📏 Memória de conversa: modo {novo}.\n" + _formatar_contexto(ctx))
        return resp(_formatar_contexto(ctx))

    if nome in ("inteligencia", "inteligência", "nivel"):
        cfg = ctx.get("settings")
        if cfg is None:
            return resp("⚠️ Configurações indisponíveis agora.")
        if not arg:
            return resp("🧠 Uso: /inteligencia max (lembra o máximo da conversa e raciocina antes de responder) · "
                        "equilibrado · economico (gasta menos tokens).\nAgora: contexto " + str(cfg.get("contexto_modo", "max"))
                        + " · raciocínio " + str(cfg.get("thinking_mode", "pensante")) + ".")
        modo = _ctx.normalizar_modo(arg.split()[0])
        pensar = "economico" if modo == "economico" else "pensante"
        cfg.update({"contexto_modo": modo, "thinking_mode": pensar})
        core = ctx.get("core")
        try:
            if core is not None:
                core.reload_api_keys(cfg)          # recria a sessão com o novo modo de raciocínio (mantém a conversa)
        except Exception as e:
            print(f"[Zenith] /inteligencia: sessão não recriada agora ({e}); vale na próxima abertura.")
        return resp(f"🧠 Inteligência: {modo} — contexto {modo}, raciocínio {pensar}.")

    if nome == "modo":
        cfg = ctx.get("settings")
        if not arg:
            atual = cfg.get("modo_atual", "normal") if cfg is not None else "normal"
            return resp(_modos.formatar_lista(atual))
        escolhido = _modos.normalizar(arg.split()[0])
        if escolhido is None:
            return resp(f"❌ Não conheço o modo '{arg.split()[0]}'.\n" + _modos.formatar_lista(
                cfg.get("modo_atual", "normal") if cfg is not None else "normal"))
        if cfg is None:
            return resp("❌ Configurações indisponíveis agora.")
        cfg.update({"modo_atual": escolhido})
        m = _modos.MODOS[escolhido]
        return resp(f"🎛️ Modo {m['rotulo']} ligado — {m['resumo']}. "
                    f"(Só muda o estilo; as regras e a aprovação de ações continuam iguais.) "
                    f"Volte com /modo normal.")

    if nome in ("lembrar", "lembrete", "alarme"):
        banco = ctx.get("lembretes") or _lembretes.Lembretes()
        try:
            quando, msg = _lembretes.interpretar(arg)
        except _lembretes.ErroLembrete as e:
            return resp(f"⏰ {e}")
        item = banco.adicionar(quando, msg)
        agora = datetime.datetime.now()
        dia = ("hoje" if quando.date() == agora.date() else
               "amanhã" if quando.date() == agora.date() + datetime.timedelta(days=1) else quando.strftime("%d/%m/%Y"))
        return resp(f"⏰ Combinado: {dia} às {quando.strftime('%H:%M')} — {msg}\n"
                    f"(fica salvo mesmo se você fechar o Zenith; apagar: /lembrete_apagar {item['id']})")

    if nome in ("lembretes", "alarmes"):
        return resp((ctx.get("lembretes") or _lembretes.Lembretes()).formatar())

    if nome in ("lembrete_apagar", "lembrete_remover", "lembrete_cancelar"):
        if not arg:
            return resp("⏰ Use: /lembrete_apagar <número da lista de /lembretes>")
        feito = (ctx.get("lembretes") or _lembretes.Lembretes()).remover(arg)
        return resp(f"⏰ Apaguei: {feito['texto']}" if feito else "⏰ Não achei esse lembrete. Veja /lembretes.")

    if nome in ("diario", "diário"):
        return resp("📔 Escrevendo o diário desta conversa...", acao="diario")

    if nome in ("diagnostico", "diagnóstico", "testar_tudo", "testartudo"):
        return resp("🩺 Testando tudo (leva alguns segundos)...", acao="diagnostico")

    if nome in ("relatorio", "relatório"):
        return resp("📋 Montando o relatório (sem chaves nem conversas)...", acao="relatorio")

    if nome in ("memorias", "memórias", "memoria", "memória"):
        mem = ctx.get("memory")
        if mem is None:
            return resp("❌ A memória não está disponível agora.")
        itens = mem.list_with_ids(arg, 15)
        if not itens:
            return resp("🧠 Nada encontrado." if arg else "🧠 A memória ainda está vazia.")
        icone = {"fact": "⭐", "chat_summary": "📎", "chat_raw": "💬"}
        linhas = [f"🧠 {len(itens)} memória(s)" + (f" com “{arg}”" if arg else " mais recentes") + " — apague uma com /esquecer <id>:"]
        for it in itens:
            texto = " ".join(str(it["text"]).split())
            linhas.append(f"{icone.get(it['mem_type'], '•')} [{it['ref']}] {texto[:110]}{'…' if len(texto) > 110 else ''}")
        return resp("\n".join(linhas))

    if nome in ("esquecer", "esqueca", "esqueça"):
        mem = ctx.get("memory")
        if mem is None:
            return resp("❌ A memória não está disponível agora.")
        if not arg:
            return resp("🧠 Use: /esquecer <id> (o id aparece entre [colchetes] em /memorias)")
        ok, msg = mem.forget(arg.split()[0])
        return resp(("🧠 " if ok else "⚠ ") + msg)

    if nome in ("exportar_conversa", "exportarconversa"):
        conv_id = ctx.get("conv_id")
        if not conv_id:
            return resp("❌ Não sei qual é a conversa ativa agora.")
        try:
            from brain import zenith_export as _exp
            from brain import zenith_history as _hist
            conv = _hist.get_conversation(conv_id)
            cfg = ctx.get("settings")
            persona = getattr(cfg, "persona_name", None) or "Zenith"
            usuario = getattr(cfg, "user_name", None) or "Você"
            destino = _pasta_exportacao() / _exp.nome_sugerido(conv, _carimbo())
            n = _exp.exportar_conversa(conv, destino, persona=persona, usuario=usuario)
            return resp(f"💾 {n} mensagem(ns) exportadas para:\n{destino}")
        except Exception as e:
            return resp(f"❌ Não consegui exportar a conversa: {e}")

    # v27 — /imagem: imagem de verdade por IA (Gemini). Digitar o comando = aprovar (o custo é avisado na resposta).
    if nome in ("imagem", "imagina", "gerar_imagem"):
        from brain import zenith_imagem_ia as _ia
        pedido = _ia.interpretar_pedido(arg)
        if not pedido["descricao"]:
            return resp("🎨 Use assim: /imagem um gato astronauta flutuando perto da Lua, estilo aquarela\n"
                        "Opções no começo: pro (qualidade melhor, mais caro) e a proporção (16:9, 9:16, 4:3, 1:1...).\n"
                        "Ex.: /imagem pro 16:9 um castelo medieval ao pôr do sol\n" + _ia.aviso_de_custo("padrao"))
        out = resp("", acao="imagem_ia")
        out["args"] = {"texto": arg}
        return out

    # v26 — /aparencia: as cores do autorretrato (ele é um desenho por código; o padrão são as cores do avatar atual)
    if nome in ("aparencia", "aparência"):
        from brain import zenith_img as _img
        a = arg.strip().lower()
        if a in ("padrao", "padrão", "reset", "resetar"):
            _img.apagar_aparencia()
            return resp("🎨 Voltei às cores padrão do autorretrato (cabelo azul-turquesa, olhos verde-água, moletom azul-claro).")
        pares = re.findall(r"(cabelo|olhos|roupa|detalhe)\s+(#?[0-9a-fA-F]{6})", arg, re.I)
        if pares:
            cores = _img.salvar_aparencia({k.lower(): v for k, v in pares})
            return resp("🎨 Aparência do autorretrato salva: " + " · ".join(f"{k} {v}" for k, v in cores.items()))
        cores = _img.ler_aparencia()
        return resp("🎨 Cores atuais do autorretrato: " + " · ".join(f"{k} {v}" for k, v in cores.items())
                    + "\nPra mudar: /aparencia cabelo #7ad0e8 olhos #3ccfb4 roupa #8ed3d8 detalhe #6a4332 · /aparencia padrao")

    # ---------------------------------------------------------------- v28
    if nome in ("conta", "calcular", "calc"):
        from brain import zenith_contas as _contas
        return resp(_contas.comando(arg))

    if nome == "video" or nome == "vídeo":
        return _comando_video(arg, resp)

    if nome in ("organizar", "organiza"):
        return _comando_organizar(arg, resp)

    if nome in ("quarentena", "restaurar"):
        return _comando_quarentena(arg, resp)

    if nome in ("biblioteca", "biblio", "livraria"):
        return _comando_biblioteca(arg, resp)

    # ---------------------------------------------------------------- v1.7: cadernos, linguagens, pip
    if nome in ("cadernos", "caderno"):
        return _comando_cadernos(arg, resp)

    if nome in ("linguagens", "compiladores", "rodar_em"):
        return _comando_linguagens(arg, resp)

    if nome in ("instalar", "pip", "pacote"):
        return _comando_instalar(arg, resp)

    if nome in ("dancar", "dançar", "danca", "dança"):
        from brain import zenith_movimentos as _mv
        partes = arg.lower().split()
        bpm = next((int(x) for x in partes if x.isdigit()), 100)
        estilo = next((x for x in partes if x in _mv.ESTILOS_DANCA), "animada")
        _clipe, erro = _mv.gerar_danca(bpm, estilo)
        if erro:
            return resp(f"💃 {erro}. Ex.: /dancar 120 animada ({', '.join(_mv.ESTILOS_DANCA)})")
        return {"resposta": f"💃 Dançando a {bpm} BPM, estilo {estilo}.", "acao": "mov_danca",
                "args": {"bpm": bpm, "estilo": estilo}}

    # ---------------------------------------------------------------- v30: chaves, rota e IA local
    if nome in ("chaves", "chave", "keys"):
        return _comando_chaves(nome, arg, resp, ctx)

    if nome in ("rota", "singularidade", "roteador"):
        return _comando_rota(arg, resp, ctx)

    if nome in ("local", "ia_local", "ialocal"):
        return _comando_local(arg, resp, ctx)

    # v26 — matemática: /latex, /formula, /derivar, /integrar, /limite (a conta é do computador, não da IA)
    from brain import zenith_formulas as _formulas
    r = _formulas.analisar_comando(nome, arg)
    if r is not None:
        out = resp(r["resposta"], r["acao"])
        if r.get("args"):
            out["args"] = r["args"]
        return out

    # v1.0 (A5) — UMA palavra começando com "/" que não existe: NUNCA vai pra IA.
    # Antes, `/vi` virava conversa e a IA inventava um "visualizador 3D" que não existe; o mesmo
    # acontecia com qualquer /xyz. Caminhos (/home/x) e frases (/algo com espaço) continuam
    # passando como conversa normal.
    # v1.5 — comandos PRÓPRIOS do usuário (T8), com ou sem argumento: só monta o pedido,
    # não executa código. Fica ANTES da recusa de comando inexistente.
    from brain import zenith_comandos_proprios as _cp
    pedido = _cp.expandir(nome, arg)
    if pedido:
        return {"resposta": "", "acao": "pedido_proprio", "args": {"texto": pedido}}

    if not arg and re.fullmatch(r"/[A-Za-zÀ-ÿ_]+", bruto):
        return resp(_comando_desconhecido(nome))

    return None   # "/algo com argumentos" desconhecido → segue pra IA normalmente


# ======================================================================================= v28
# v1.0 — O PROBLEMA REAL DO ANDERSON (16/10): ele copiou o caminho no Windows ("Copiar como caminho"
# já vem COM aspas), colou e ainda colocou outras aspas: `/video vertical ""C:\...\a.mp4"" 2:00 corte`.
# O resultado era "Não achei o vídeo: (vazio)". Aqui as aspas repetidas e as aspas "bonitas" (curvas)
# são normalizadas antes de dividir os argumentos.
_ASPAS = {"“": '"', "”": '"', "„": '"', "‟": '"', "‘": "'", "’": "'", "‚": "'", "′": "'", "″": '"',
          "＂": '"'}

_EXT_CAMINHO = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg", ".ts",
                ".gif", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".srt", ".txt", ".png", ".jpg", ".jpeg")


def _parece_caminho(t: str) -> bool:
    return bool(t) and (t.lower().endswith(_EXT_CAMINHO) or Path(t).is_file())


def _juntar_caminho(partes: list) -> list:
    r"""Caminho colado SEM aspas (com espaço no nome): junta os pedaços até a extensão do arquivo.

    Ex.: `C:\Users\joao\Videos\2026-10-04 14-31-36.mp4 9:16` chegava como 3 pedaços e o programa
    lia o caminho pela metade. Aqui vira um pedaço só e o resto do comando continua igual."""
    if not partes or _parece_caminho(partes[0]):
        return partes
    acumulado = partes[0]
    for i in range(1, len(partes)):
        acumulado += " " + partes[i]
        if _parece_caminho(acumulado):
            return [acumulado] + partes[i + 1:]
    return partes


def _caminhos(arg: str) -> list:
    """Divide os argumentos respeitando aspas (caminho do Windows com espaço) e sem tratar \\ como escape."""
    import shlex
    t = str(arg or "")
    for de, para in _ASPAS.items():
        t = t.replace(de, para)
    while '""' in t:                    # ""C:\a b\x.mp4"" -> "C:\a b\x.mp4"
        t = t.replace('""', '"')
    try:
        partes = shlex.split(t, posix=False)
    except ValueError:
        partes = t.split()
    return [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in partes]


_USO_VIDEO = (
    "🎬 Editar vídeo — o original NUNCA é alterado; o resultado vai pra creations/videos/.\n"
    "• /video cortar <arquivo> <início> [fim]      (tempo: 90 ou 1:30)\n"
    "• /video gif <arquivo> [início] [fim]\n"
    "• /video velocidade <arquivo> <fator>         (2 = o dobro, 0.5 = metade)\n"
    "• /video audio <arquivo> [mp3|wav] · /video mudo <arquivo>\n"
    "• /video juntar <a> <b> [c ...] · /video converter <arquivo> <mp4|webm|mkv|mov|avi|mp3|wav>\n"
    "• /video frame <arquivo> <tempo> · /video girar <arquivo> <90|180|270> · /video redimensionar <arquivo> <largura>\n"
    "• /video narrar <roteiro.txt> [escuro|claro|neon] — cada parágrafo vira um slide com a minha voz + legenda .srt\n"
    "• /video efeito <arquivo> <pb|sepia|vintage|antigo|cinema|neon|sonho|vinheta|nitido|espelho|desfoque> [força]\n"
    "• /video vertical <arquivo> [9:16|1:1|4:5|16:9] [corte|fundo] — Shorts/Reels prontos (corte preenche, fundo põe barras desfocadas)\n"
    "• /video transicao <a> <b> [fade|dissolve|slideleft|circleopen|pixelize|zoomin] [segundos]\n"
    "• /video legenda <arquivo> <legenda.srt> — queima a legenda no vídeo (aparece sempre, igual Shorts)\n"
    "Caminho: cole como o Windows copia (Shift + botão direito > \"Copiar como caminho\"). Se ele vier com aspas, "
    "NÃO precisa pôr outras — se puser, eu desfaço sozinho. Caminho sem aspas (com espaço) também funciona.\n"
    "Também dá pra só pedir em português (\"corta esse vídeo do 1:30 ao 2:10\"): eu monto e você aprova.")

# Operações que o /video conhece (para a sugestão de erro de digitação).
_OPS_VIDEO = ("cortar", "gif", "velocidade", "audio", "mudo", "juntar", "converter", "frame", "girar",
              "redimensionar", "efeito", "vertical", "enquadrar", "transicao", "legenda", "narrar")

# Proporção aceita pelo enquadrar/vertical (o Anderson digitou "2:00" no lugar dela).
_PROPORCOES_VIDEO = {"9:16": "9:16", "vertical": "9:16", "shorts": "9:16", "reels": "9:16", "tiktok": "9:16",
                     "16:9": "16:9", "horizontal": "16:9", "youtube": "16:9", "paisagem": "16:9",
                     "1:1": "1:1", "quadrado": "1:1", "4:5": "4:5", "4:3": "4:3", "3:4": "3:4"}


def _sugerir_op(palavra: str) -> str:
    import difflib
    achadas = difflib.get_close_matches((palavra or "").lower(), list(_OPS_VIDEO), n=1, cutoff=0.6)
    return f" Você quis dizer “{achadas[0]}”?" if achadas else ""


def _comando_video(arg: str, resp):
    p = _caminhos(arg)
    if not p:
        return resp(_USO_VIDEO)
    op, resto = p[0].lower(), _juntar_caminho(p[1:])
    nomes = {"corte": "cortar", "acelerar": "velocidade", "velocidade": "velocidade", "mp3": "audio", "extrair_audio": "audio",
             "muto": "mudo", "remover_audio": "mudo", "unir": "juntar", "converte": "converter", "rotacionar": "girar",
             "resize": "redimensionar", "criar": "narrar", "aula": "narrar"}
    op = nomes.get(op, op)

    def pedido(d, texto):
        out = resp(f"🎬 {texto}")
        out["acao"] = "video"
        out["args"] = {"pedido": d}
        return out
    falta = resp(f"🎬 Faltou algo nesse comando.\n{_USO_VIDEO}")
    if op == "cortar":
        if len(resto) < 2:
            return falta
        return pedido({"op": "cortar", "entrada": resto[0], "inicio": resto[1], "fim": resto[2] if len(resto) > 2 else ""},
                      f"Cortando {resto[0]} a partir de {resto[1]}" + (f" até {resto[2]}" if len(resto) > 2 else "") + "…")
    if op == "gif":
        if not resto:
            return falta
        return pedido({"op": "gif", "entrada": resto[0], "inicio": resto[1] if len(resto) > 1 else 0, "fim": resto[2] if len(resto) > 2 else ""},
                      f"Fazendo um GIF de {resto[0]}…")
    if op == "velocidade":
        if len(resto) < 2:
            return falta
        return pedido({"op": "velocidade", "entrada": resto[0], "fator": resto[1]}, f"Mudando a velocidade de {resto[0]} pra {resto[1]}x…")
    if op == "audio":
        if not resto:
            return falta
        return pedido({"op": "extrair_audio", "entrada": resto[0], "formato": resto[1] if len(resto) > 1 else "mp3"},
                      f"Extraindo o áudio de {resto[0]}…")
    if op == "mudo":
        if not resto:
            return falta
        return pedido({"op": "remover_audio", "entrada": resto[0]}, f"Tirando o áudio de {resto[0]}…")
    if op == "juntar":
        if len(resto) < 2:
            return falta
        return pedido({"op": "juntar", "entradas": resto}, f"Juntando {len(resto)} vídeos…")
    if op == "converter":
        if len(resto) < 2:
            return falta
        return pedido({"op": "converter", "entrada": resto[0], "formato": resto[1]}, f"Convertendo {resto[0]} pra {resto[1]}…")
    if op == "frame":
        if len(resto) < 2:
            return falta
        return pedido({"op": "frame", "entrada": resto[0], "tempo": resto[1]}, f"Tirando um quadro de {resto[0]} em {resto[1]}…")
    if op == "girar":
        if len(resto) < 2:
            return falta
        return pedido({"op": "girar", "entrada": resto[0], "graus": resto[1]}, f"Girando {resto[0]} em {resto[1]}°…")
    if op == "redimensionar":
        if len(resto) < 2:
            return falta
        return pedido({"op": "redimensionar", "entrada": resto[0], "largura": resto[1]}, f"Redimensionando {resto[0]}…")
    if op in ("efeito", "filtro", "cor", "estilo"):
        if len(resto) < 2:
            return falta
        return pedido({"op": "efeito", "entrada": resto[0], "estilo": resto[1],
                       "forca": resto[2] if len(resto) > 2 else 1.0},
                      f"Aplicando o efeito “{resto[1]}” em {resto[0]}…")
    if op in ("vertical", "shorts", "reels", "tiktok", "enquadrar", "formato"):
        if not resto:
            return falta
        prop_bruta = resto[1] if len(resto) > 1 else "9:16"
        prop = _PROPORCOES_VIDEO.get(prop_bruta.lower())
        if not prop:
            # Caso real (16/10): `/video vertical ""…mp4"" 2:00 corte` — o 2:00 era o TEMPO de corte,
            # não a proporção. Antes isso virava um enquadramento com "2:00" e falhava no ffmpeg
            # com uma mensagem incompreensível.
            if re.fullmatch(r"\d{1,3}:\d{2}", prop_bruta or ""):
                return resp(
                    f"🎬 “{prop_bruta}” é um TEMPO, não uma proporção.\n"
                    "Proporções: 9:16 (Shorts/Reels/TikTok), 16:9 (YouTube/horizontal), 1:1, 4:5.\n"
                    f"Exemplo certo: /video vertical \"{resto[0]}\" 9:16 corte\n"
                    f"Para CORTAR um pedaço: /video cortar \"{resto[0]}\" 0:10 2:00")
            return resp(f"🎬 Não conheço a proporção “{prop_bruta}”.\n"
                        "Use: 9:16 (Shorts), 16:9 (horizontal/YouTube), 1:1, 4:5.\n"
                        f"Exemplo: /video vertical \"{resto[0]}\" 9:16 corte")
        modo = (resto[2] if len(resto) > 2 else "corte").lower()
        if modo in ("horizontal", "vertical", "paisagem"):     # atalho: `enquadrar arquivo horizontal`
            prop, modo = _PROPORCOES_VIDEO[modo], "corte"
        if modo not in ("corte", "fundo"):
            return resp(f"🎬 “{modo}” não é um modo de enquadramento.\n"
                        "Use: corte (preenche a tela cortando as sobras) ou fundo (vídeo inteiro com barras desfocadas).\n"
                        f"Exemplo: /video vertical \"{resto[0]}\" {prop} corte")
        return pedido({"op": "enquadrar", "entrada": resto[0], "proporcao": prop, "modo": modo},
                      f"Enquadrando {resto[0]} em {prop} ({modo}) — pronto pra Shorts/Reels…")
    if op in ("transicao", "transição", "transicionar"):
        if len(resto) < 2:
            return falta
        tipo = resto[2] if len(resto) > 2 else "fade"
        seg = resto[3] if len(resto) > 3 else 0.7
        return pedido({"op": "transicao", "entradas": resto[:2], "tipo": tipo, "segundos": seg},
                      f"Juntando os 2 vídeos com transição “{tipo}”…")
    if op in ("legenda", "legendar", "legendas", "subtitle"):
        if len(resto) < 2:
            return falta
        return pedido({"op": "legendar", "entrada": resto[0], "srt": resto[1]},
                      f"Queimando a legenda em {resto[0]}…")
    if op == "narrar":
        if not resto:
            return falta
        arq = Path(resto[0])
        if not arq.is_file():
            return resp(f"🎬 Não achei o arquivo do roteiro: {resto[0]}\nEscreva as cenas num .txt, separadas por uma linha em branco.")
        try:
            roteiro = arq.read_text(encoding="utf-8", errors="replace")[:60000]
        except OSError as e:
            return resp(f"🎬 Não consegui abrir o roteiro: {e}")
        tema = next((t for t in resto[1:] if t.lower() in ("escuro", "claro", "neon")), "escuro").lower()
        titulo = " ".join(t for t in resto[1:] if t.lower() not in ("escuro", "claro", "neon")) or arq.stem.replace("_", " ")
        return pedido({"op": "narrar", "roteiro": roteiro, "titulo": titulo, "tema": tema},
                      f"Montando o vídeo de aula “{titulo}” (slide + minha voz + legenda)…")
    return resp(f"🎬 Não conheço a operação “{op}”.{_sugerir_op(op)}\n{_USO_VIDEO}")


def _comando_organizar(arg: str, resp):
    from brain import zenith_organizar as _org
    palavras = {"limpar": "limpar", "organizar": "organizar", "tudo": "tudo"}
    modo, agressivo = "tudo", False
    p = _caminhos(arg)
    while p and p[-1].lower() in (*palavras, "agressivo"):
        ult = p.pop().lower()
        if ult == "agressivo":
            agressivo = True
        else:
            modo = palavras[ult]
    pasta = " ".join(p).strip() if len(p) != 1 else p[0]
    if not pasta:
        return resp("🗂️ Use: /organizar <pasta> [limpar|organizar|tudo] [agressivo]\n"
                    "• limpar = só o inútil (vazios, lixo, downloads incompletos, cópias exatas) · organizar = arruma por tipo · tudo (padrão) = os dois\n"
                    "• agressivo = inclui instaladores (.exe/.msi) com mais de 90 dias\n"
                    "Ex.: /organizar \"C:\\Users\\voce\\Downloads\" limpar\n"
                    "Eu só olho primeiro e mostro o PLANO — nada muda até você aprovar, e o inútil vai pra quarentena (dá pra desfazer).")
    out = resp("")
    out["acao"] = "organizar"
    out["args"] = {"pasta": pasta, "modo": modo, "agressivo": agressivo}
    return out


# ======================================================================================= v30
def _comando_chaves(nome: str, arg: str, resp, ctx: dict):
    """Várias chaves da MESMA IA, com troca automática. A chave digitada aqui NÃO vai pra IA nem
    pro histórico da conversa (comandos são resolvidos antes); fica só no settings.json do PC."""
    from brain import zenith_chaves as _ch
    cfg = ctx.get("settings")
    if cfg is None:
        return resp("⚠️ Configurações indisponíveis agora.")
    p = _caminhos(arg)
    sub = p[0].lower() if p else ""
    if nome == "chaves" and sub not in ("status", "ver", "lista", "add", "adicionar", "somar", "remover", "apagar",
                                        "del", "testar", "teste", "verificar", "esquecer", "limpar", "liberar"):
        sub = "status"
    if sub in ("", "status", "ver", "lista"):
        return resp(_ch.Rotador(cfg).texto_relatorio())
    if sub in ("add", "adicionar", "somar"):
        if len(p) < 3:
            return resp("🔑 Use: /chave add gemini A_SUA_CHAVE_AQUI\n"
                        "Provedores: gemini, openai, claude (OpenRouter), groq, custom:<id>.\n"
                        "Pode repetir quantas vezes quiser — a Zenith usa uma de cada vez e troca sozinha quando uma "
                        "estoura a cota. A chave fica só no seu PC (settings.json); este comando não gasta IA nem entra "
                        "no histórico da conversa.")
        r = _ch.adicionar_chave(cfg, p[1], p[2])
        txt = r["mensagem"] + ("\nVeja todas com /chaves." if r.get("ok") else "")
        if r.get("ok"):
            # v1.0 (A2d) — a chave pode estar na área de transferência e no histórico do teclado.
            txt += ("\n\n🔐 Esta mensagem não entra no histórico da conversa, mas ela ainda está na sua "
                    "área de transferência. Apague de lá e, se quiser o caminho mais seguro, use "
                    "Configurações > IAs & Chaves.")
        return resp(txt, acao="recarregar_ia" if r.get("ok") else None)
    if sub in ("remover", "apagar", "del"):
        if len(p) < 3:
            return resp("🔑 Use: /chave remover <provedor> <número> — o número vem de /chaves "
                        "(1 = a primeira chave EXTRA; a principal se apaga em Configurações).")
        try:
            n = int(p[2])
        except ValueError:
            return resp("🔑 O número da chave precisa ser 1, 2, 3…")
        r = _ch.remover_chave(cfg, p[1], n)
        return resp(r["mensagem"], acao="recarregar_ia" if r.get("ok") else None)
    if sub in ("testar", "teste", "verificar"):
        if ctx.get("core") is None:
            return resp("⚠️ Só consigo testar as chaves com o Cérebro ligado.")
        return resp("🔑 Testando cada chave (é uma chamada barata, não gasta resposta)...", acao="testar_chaves")
    if sub in ("esquecer", "limpar", "liberar"):
        _ch.Rotador(cfg).esquecer_castigos()
        return resp("🔑 Liberei as chaves que estavam em espera. Se a cota ainda estiver estourada, elas voltam "
                    "a ficar de castigo na próxima tentativa (sem quebrar a conversa — a próxima chave assume).")
    return resp("🔑 Uso: /chaves · /chave add <provedor> <chave> · /chave remover <provedor> <n> · "
                "/chaves testar · /chaves esquecer")


def _comando_rota(arg: str, resp, ctx: dict):
    """Mostra/ajusta QUEM faz o quê (a 'singularidade'): texto, visão e imagem."""
    from brain import zenith_rota as _rota
    from brain import zenith_chaves as _ch
    cfg = ctx.get("settings")
    if cfg is None:
        return resp("⚠️ Configurações indisponíveis agora.")
    core = ctx.get("core")
    if core is not None:
        try:
            disponiveis = core.available_providers()
        except Exception:
            disponiveis = []
    else:
        disponiveis = []
    if not disponiveis:
        rot = _ch.Rotador(cfg)
        disponiveis = [p for p in ("gemini", "openai", "claude", "groq", "local") if rot.chaves(p)]
        disponiveis += [f"custom:{ep.get('id')}" for ep in (cfg.get("ai_endpoints", []) or [])
                        if isinstance(ep, dict) and ep.get("id") and ep.get("api_url")]
    p = _caminhos(arg)
    if not p:
        return resp(_rota.texto_mapa(disponiveis, cfg))
    sub = p[0].lower()
    if sub in ("limpar", "padrao", "padrão", "auto", "reset"):
        return resp(_rota.definir_preferencia(cfg, "limpar")["mensagem"], acao="recarregar_ia")
    if sub == "capacidades":
        if len(p) < 3:
            return resp("🧠 Use: /rota capacidades <provedor> texto,visao\n"
                        "Serve pra dizer que a SUA IA personalizada/local enxerga imagem (ou pra tirar uma "
                        "capacidade que você não quer usar nela).")
        prov = p[1]
        caps = [c.strip().lower() for c in re.split(r"[,; ]+", p[2]) if c.strip()]
        invalidas = [c for c in caps if c not in _rota.CAPACIDADES]
        if invalidas:
            return resp(f"🧠 Não conheço: {', '.join(invalidas)}. Use: {', '.join(_rota.CAPACIDADES)}.")
        ajustes = dict(cfg.get("ia_capacidades", {}) or {})
        ajustes[prov] = caps
        cfg.update({"ia_capacidades": ajustes})
        nomes = ", ".join(_rota.NOMES_CAP.get(c, c) for c in caps) or "nada"
        return resp(f"🧠 {_rota.rotulo(prov, cfg)} agora faz: {nomes}.", acao="recarregar_ia")
    if sub in _rota.CAPACIDADES:
        if sub in _rota.LOCAIS:
            return resp(f"🔒 {_rota.NOMES_CAP.get(sub, sub)} roda no seu PC e não depende de escolher IA.")
        if len(p) == 1:
            ordem = _rota.escolher(sub, disponiveis, cfg.get("active_ai", ""), cfg)
            nomes = " → ".join(_rota.rotulo(x, cfg) for x in ordem) or "ninguém disponível"
            return resp(f"🔀 Para {_rota.NOMES_CAP.get(sub, sub)}: {nomes}")
        prov = p[1]
        if prov.lower() in ("nenhum", "ninguem", "ninguém", "auto"):
            return resp(_rota.definir_preferencia(cfg, sub)["mensagem"], acao="recarregar_ia")
        r = _rota.definir_preferencia(cfg, sub, prov)
        return resp(r["mensagem"], acao="recarregar_ia" if r.get("ok") else None)
    return resp("🔀 Uso: /rota · /rota visao openai · /rota texto gemini · /rota capacidades custom:abc texto,visao · /rota limpar")


def _comando_local(arg: str, resp, ctx: dict):
    """IA local OPCIONAL (Ollama/LM Studio no próprio PC): sem chave, entra como reserva."""
    from brain import zenith_ia_local as _local
    cfg = ctx.get("settings")
    if cfg is None:
        return resp("⚠️ Configurações indisponíveis agora.")
    p = _caminhos(arg)
    sub = p[0].lower() if p else ""
    if sub in ("", "status", "ver"):
        return resp(_local.status_texto(cfg))
    if sub in ("ligar", "on", "ativar"):
        det = _local.detectar(cfg, timeout=1.5)
        _local.configurar(cfg, ligar=True)
        if not det.get("rodando"):
            return resp("⚠️ Marquei a IA local como ligada, mas o servidor local não respondeu agora.\n\n"
                        + _local.msg_sem_servidor(), acao="recarregar_ia")
        extra = "" if det.get("modelos") else "\nAinda não há modelo baixado — /local baixar (≈1 GB, uma vez só)."
        return resp(f"✅ IA local ligada como reserva ({det['nome']} em {det['url']}). "
                    f"Ela entra quando a nuvem/cota falhar — nada do que ela responder sai do seu PC.{extra}",
                    acao="recarregar_ia")
    if sub in ("desligar", "off", "desativar"):
        _local.configurar(cfg, ligar=False)
        return resp("🖥 IA local desligada. As nuvens continuam normais.", acao="recarregar_ia")
    if sub in ("baixar", "download", "instalar"):
        if ctx.get("core") is None:
            return resp("⚠️ Só consigo baixar o modelo com o Cérebro ligado.")
        modelo = p[1] if len(p) > 1 else ""
        out = resp(f"🖥 Baixando o modelo local {modelo or '(o recomendado)'}… isso pode levar alguns minutos e "
                   f"uns 1–2 GB. Vou avisando.")
        out["acao"] = "baixar_local"
        out["args"] = {"modelo": modelo}
        return out
    if sub in ("recomendar", "recomendacao", "recomendação", "medir", "pc"):
        # v1.7 (T7) — mede o PC e recomenda um modelo que não trava
        from brain import zenith_desempenho as _desemp
        medida = _desemp.medir()
        rec = _desemp.recomendar(medida)
        return resp(_desemp.formatar(medida, rec))
    if sub in ("modelo", "model"):
        if len(p) < 2:
            return resp("🖥 Use: /local modelo qwen2.5:1.5b (o nome como aparece em /local).")
        _local.configurar(cfg, modelo=" ".join(p[1:]))
        return resp(f"🖥 Modelo local definido: {' '.join(p[1:])}.", acao="recarregar_ia")
    if sub in ("papel", "role"):
        if len(p) < 2 or p[1].lower() not in ("reserva", "principal"):
            return resp("🖥 Use: /local papel reserva (padrão: entra quando a nuvem falha) ou /local papel principal "
                        "(ela passa a responder primeiro — mais privada, bem mais lenta).")
        _local.configurar(cfg, papel=p[1].lower())
        return resp("🖥 " + _local.explicar_papel(p[1]), acao="recarregar_ia")
    return resp("🖥 Uso: /local · /local ligar · /local desligar · /local baixar [modelo] · /local modelo <nome> · "
                "/local papel reserva|principal")


def _pasta_quarentena() -> str:
    from brain.zenith_settings import CREATION_DIR
    return str(Path(CREATION_DIR) / "quarentena")


def _comando_quarentena(arg: str, resp):
    from brain import zenith_organizar as _org
    p = _caminhos(arg)
    sub = p[0].lower() if p else ""
    if sub in ("", "lista", "listar", "ver"):
        return resp(_org.formatar_quarentenas(_pasta_quarentena()))
    if sub in ("desfazer", "voltar", "restaurar"):
        try:
            r = _org.desfazer(_pasta_quarentena(), p[1] if len(p) > 1 else "")
        except _org.ErroOrganizar as e:
            return resp(str(e))
        txt = f"↩ Desfeito ({r['carimbo']}): {r['voltaram']} arquivo(s) voltaram pro lugar de origem."
        if r["falhas"]:
            txt += "\n⚠ " + "; ".join(r["falhas"][:5])
        return resp(txt)
    if sub in ("esvaziar", "apagar", "limpar"):
        if len(p) < 2 or p[1].lower() != "confirmar":
            itens = _org.listar_quarentenas(_pasta_quarentena())
            tam = sum(i["bytes"] for i in itens if not i["desfeito"])
            return resp(f"⚠ Isso APAGA DE VERDADE o que está na quarentena ({_org.tamanho_legivel(tam)}) — não dá pra desfazer depois.\n"
                        "Se tem certeza, digite: /quarentena esvaziar confirmar")
        r = _org.esvaziar(_pasta_quarentena())
        return resp(f"🗑 Pronto: {r['apagados']} arquivo(s) apagados de vez ({_org.tamanho_legivel(r['bytes'])} liberados).")
    return resp("🗂️ Use: /quarentena (lista) · /quarentena desfazer [carimbo] · /quarentena esvaziar confirmar")


def _comando_biblioteca(arg: str, resp):
    from brain import zenith_biblioteca as _bib
    b = _bib.padrao()
    p = _caminhos(arg)
    sub = p[0].lower() if p else ""
    if sub in ("", "lista", "listar", "ver"):
        return resp(_bib.formatar_lista(b))
    if sub in ("add", "adicionar", "guardar", "incluir"):
        caminho = " ".join(p[1:]).strip() if len(p) > 2 else (p[1] if len(p) == 2 else "")
        if not caminho:
            return resp("📚 Use: /biblioteca add <arquivo ou pasta> — aceito PDF, Word, PowerPoint, Excel e texto/código.")
        out = resp(f"📚 Guardando na biblioteca: {caminho} …")
        out["acao"] = "biblioteca_add"
        out["args"] = {"caminho": caminho}
        return out
    if sub in ("buscar", "busca", "procurar", "b"):
        pergunta = " ".join(p[1:]).strip()
        if not pergunta:
            return resp("📚 Use: /biblioteca buscar <pergunta>")
        return resp(_bib.formatar_busca(b.buscar(pergunta, 5)))
    if sub in ("remover", "apagar", "tirar"):
        nome = " ".join(p[1:]).strip()
        try:
            d = b.remover(nome)
        except _bib.ErroBiblioteca as e:
            return resp(str(e))
        return resp(f"📚 Tirei “{d['nome']}” da biblioteca (o arquivo original não foi tocado).")
    return resp("📚 Use: /biblioteca (lista) · /biblioteca add <caminho> · /biblioteca buscar <pergunta> · /biblioteca remover <nome>")


def _comando_cadernos(arg: str, resp):
    """v1.7 (T6) — cadernos de estudo: fontes, busca com citação e Modo Professora."""
    from brain import zenith_cadernos as _cad
    cad = _cad.padrao()
    bruto = (arg or "").strip()
    sub = bruto.split(" ", 1)[0].lower() if bruto else ""
    resto = bruto[len(sub):].strip()
    try:
        if sub in ("", "lista", "listar", "ver"):
            return resp(_cad.formatar_lista(cad))
        if sub in ("novo", "criar", "nova"):
            c = cad.criar(resto)
            return resp(f"📓 Caderno '{c['nome']}' criado e ativo. Guarde o material: /cadernos add <arquivo ou pasta>")
        if sub in ("usar", "abrir", "ativo"):
            c = cad.usar(resto)
            return resp(f"📓 Caderno ativo: {c['nome']} ({len(c['fontes'])} fonte(s)).")
        if sub in ("add", "adicionar", "guardar"):
            if not resto:
                return resp("📓 Use: /cadernos add <arquivo ou pasta>")
            return {"resposta": f"📓 Guardando {resto} no caderno…", "acao": "caderno_add", "args": {"caminho": resto}}
        if sub in ("perguntar", "buscar", "pergunta"):
            if not resto:
                return resp("📓 Use: /cadernos perguntar <pergunta>")
            return resp(cad.responder("", resto)["texto"])
        if sub in ("professora", "professor", "estudar"):
            if not resto:
                return resp("📓 Use: /cadernos professora <tema>")
            return resp(cad.professora("", resto)["texto"])
        if sub in ("apagar", "remover"):
            ok = cad.apagar(resto)
            return resp(f"📓 Caderno '{resto}' apagado (os arquivos originais não foram tocados)." if ok
                        else f"📓 Não achei o caderno '{resto}'.")
    except _cad.ErroCaderno as e:
        return resp(f"📓 {e}")
    return resp("📓 Use: /cadernos · /cadernos novo <assunto> · /cadernos add <arquivo|pasta> · "
                "/cadernos perguntar <pergunta> · /cadernos professora <tema> · /cadernos apagar <nome>")


def _comando_linguagens(arg: str, resp):
    """v1.7 (T5) — quais compiladores existem neste PC (sem instalar nada)."""
    from brain import zenith_linguagens as _ling
    det = _ling.detectar()
    linhas = ["🧰 O que este PC já sabe rodar:"]
    for chave, i in det.items():
        if chave == "python":
            linhas.append(f"• {i['nome']}: sim (o próprio Zenith)")
        elif i["ok"]:
            linhas.append(f"• {i['nome']}: sim")
        else:
            linhas.append(f"• {i['nome']}: não (falta {', '.join(i['falta'])}) — {i['como']}")
    linhas.append("\nPeça \"cria um programa em <linguagem>\" e eu gravo; para rodar, cada comando pede aprovação.")
    return resp("\n".join(linhas))


def _comando_instalar(arg: str, resp):
    """v1.7 (T5) — pip guiado: mostra pacote, versão e licença ANTES; instalar é ação aprovada."""
    from brain import zenith_linguagens as _ling
    partes = (arg or "").split()
    if not partes:
        return resp("📦 Use: /instalar <pacote> (mostro versão e licença) · /instalar <pacote> confirmar (pede a aprovação)")
    pacote = partes[0]
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", pacote):
        return resp("📦 Nome de pacote inválido. Ex.: /instalar requests")
    if "confirmar" not in [p.lower() for p in partes[1:]]:
        try:
            info = _ling.info_pacote(pacote)
        except Exception as e:
            return resp(f"📦 Não consegui consultar o PyPI agora ({type(e).__name__}). Sem a versão e a licença eu não instalo. "
                        "Tente de novo com internet.")
        return resp(_ling.formatar_pacote(info))
    return {"resposta": f"📦 Vou instalar o pacote '{pacote}' com o pip do Python do Zenith — isso pede a sua aprovação.",
            "acao": "pip_instalar", "args": {"pacote": pacote}}


def _comando_desconhecido(nome: str) -> str:
    """Resposta para um /comando que não existe: sugere o mais parecido em vez de entregar pra IA."""
    import difflib
    itens = lista_para_autocompletar()
    usos = {i["cmd"].lstrip("/"): i["uso"] for i in itens}
    nomes = sorted(usos)
    comecam = [n for n in nomes if n.startswith(nome)]
    if len(comecam) == 1:
        alvo = comecam[0]
        uso = (" " + usos.get(alvo, "")).rstrip()
        return f"❓ Ainda não existe o comando /{nome}. Você quis dizer /{alvo}{uso}?\nVeja tudo com /ajuda."
    # Antes de sugerir comando, vê se o que a pessoa quis era uma OPERAÇÃO do /video
    # ("cortarr" não é comando; é `/video cortar`).
    op_video = difflib.get_close_matches(nome, list(_OPS_VIDEO), n=1, cutoff=0.6)
    if op_video:
        return (f"❓ Não existe o comando /{nome}. Você quis dizer /video {op_video[0]}?\n"
                f"Exemplo: /video {op_video[0]} \"C:\\caminho\\video.mp4\" …\nVeja tudo com /ajuda.")
    parecidos = difflib.get_close_matches(nome, nomes, n=3, cutoff=0.55)
    dicas = parecidos + [n for n in comecam if n not in parecidos]
    dicas += [n for n in nomes if nome in n and n not in dicas][:3]
    if dicas:
        lista = ", ".join("/" + n for n in dicas[:5])
        return f"❓ Não existe o comando /{nome}. Você quis dizer: {lista}?\nVeja a lista completa com /ajuda."
    return (f"❓ Não existe o comando /{nome}.\nVeja a lista completa com /ajuda — "
            "ou escreva a mesma coisa sem a barra, que eu respondo como conversa.")


def lista_para_autocompletar() -> list:
    """[{"cmd": "/imagem", "uso": "[pro] [16:9] <descrição>", "desc": "…"}] — tirada da própria /ajuda (nunca fica desatualizada)."""
    itens, vistos = [], set()
    for linha in _AJUDA.splitlines():
        if not linha.startswith("• /"):
            continue
        corpo = linha[2:]
        desc = ""
        if " — " in corpo:
            corpo, _, desc = corpo.partition(" — ")
        for seg in re.split(r"\s+·\s+(?=/)", corpo):
            m = re.match(r"^(/[A-Za-zÀ-ÿ_]+)\s*(.*)$", seg.strip())
            if not m or m.group(1) in vistos:
                continue
            vistos.add(m.group(1))
            itens.append({"cmd": m.group(1), "uso": m.group(2).strip()[:60], "desc": desc.strip()[:110]})
    for extra in ("/parar", "/pausar", "/retomar"):       # existem mesmo quando a linha da ajuda mistura vários
        if extra not in vistos:
            itens.append({"cmd": extra, "uso": "", "desc": ""})
    return sorted(itens, key=lambda i: i["cmd"])


def _formatar_contexto(ctx: dict) -> str:
    """/contexto — estimativa do que vai pra IA a cada mensagem (v22). Só ordem de grandeza (~4 caracteres
    por token); a janela real depende do modelo, por isso o perfil traz um tamanho aproximado editável."""
    cfg = ctx.get("settings")
    core = ctx.get("core")
    ia = getattr(core, "ia_ativa", None) or (cfg.get("active_ai", "gemini") if cfg is not None else "gemini")
    perfil = _conhec.perfil_para(ia)
    modo = _ctx.normalizar_modo(cfg.get("contexto_modo", "max")) if cfg is not None else "max"
    desligado = cfg is not None and cfg.get("contexto_modo", "") == "desligado"
    linhas = [f"📏 Contexto (estimativa) — IA em uso: {ia} · nível {perfil.get('nivel')} · memória de conversa: "
              f"{'DESLIGADA' if desligado else modo}"]
    fixo = 0
    try:
        if core is not None:
            sis = _conhec.estimar_tokens(core._build_system_prompt())
            fixo += sis
            linhas.append(f"• Instruções do sistema (pilares, Bíblia fixa, regras suas, ferramentas): ~{sis} tokens")
    except Exception:
        pass
    cartoes = _conhec.estimar_tokens("x" * int(perfil.get("max_chars", 0)))
    fixo += cartoes
    linhas.append(f"• Cartões da Bíblia por mensagem: até {perfil.get('max_cartoes')} (~{cartoes} tokens no máximo)")
    conv = None
    try:
        if core is not None and getattr(core, "conv_id", None) and not desligado:
            conv = core._contexto_montado("")
    except Exception:
        conv = None
    if conv is not None:
        fixo += conv["tokens"]
        extra = f"; {conv['descartadas']} mais antigas viram resumo" if conv["descartadas"] else ""
        linhas.append(f"• Conversa atual: {len(conv['turnos'])} mensagens vão junto (~{conv['tokens']} tokens, "
                      f"orçamento {conv['orcamento']}){extra}")
    janela = int(perfil.get("contexto_tokens", 32000))
    pct = 100.0 * fixo / janela if janela else 0.0
    linhas.append(f"Total ≈ {fixo} tokens de ~{janela} de janela aproximada  [{_conhec.barra(pct)}] {pct:.1f}%")
    linhas.append("Mudar: /contexto max|equilibrado|economico|desligado · tamanhos em config/biblia/perfis_modelos.json. "
                  "Passou de ~70%? Abra uma conversa nova (/diario guarda o resumo como memória).")
    return "\n".join(linhas)
