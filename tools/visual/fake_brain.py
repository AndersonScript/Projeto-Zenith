"""Cérebro de mentira para testar a INTERFACE (Godot) sem IA, sem chaves e sem internet.

Uso:  python tools/visual/fake_brain.py   (porta 8765, a mesma do Cérebro de verdade)
Ele responde o mínimo que o Corpo pede e manda mensagens de exemplo (texto, código,
tabela, aviso, progresso) para a gente VER como a tela fica.
"""
import asyncio, json, sys, os, tempfile, pathlib
import websockets

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))


class _BibFalsa:
    """Biblioteca de documentos de mentira (só para ver a aba Fontes)."""
    def documentos(self):
        return [{"id": "a1", "nome": "Apostila_Automacao_Industrial.pdf", "paginas": 148, "trechos": 612, "adicionado": "2026-10-20 21:14"},
                {"id": "b2", "nome": "Datasheet_ESP32-S3.pdf", "paginas": 62, "trechos": 240, "adicionado": "2026-10-21 08:02"},
                {"id": "c3", "nome": "Mecanica_Classica_notas.docx", "paginas": 31, "trechos": 97, "adicionado": "2026-10-22 19:40"}]


def dados_biblioteca():
    """Índice de exemplo: o que ela criou + o que ela usa como base (mesmo formato do Cérebro de verdade)."""
    from brain import zenith_projetos as pj, zenith_fontes as fontes
    r = pathlib.Path(tempfile.mkdtemp(prefix="zenith_fake_")) / "creations"
    def f(rel, txt=b"x"):
        q = r / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_bytes(txt if isinstance(txt, bytes) else txt.encode())
    for rel in ("programas/simulador_de_projeteis/index.html", "programas/simulador_de_projeteis/app.js", "programas/simulador_de_projeteis/estilo.css",
                "programas/jogo_da_velha/main.py", "programas/jogo_da_velha/util.py", "programas/jogo_da_velha/placar.py",
                "programas/relogio/relogio.py", "programas/blink/blink.ino", "programas/calculadora_c/calc.c", "programas/calculadora_c/calc.h",
                "web/pagina_do_canal.html", "imagens/autorretrato.png", "imagens/meme_euler.png", "videos/aula_derivadas.mp4",
                "documentos/relatorio_fisica.docx"):
        f(rel)
    ind = pj.indexar(r)
    ind["categorias"] += fontes.categorias(bib=_BibFalsa(), user="Anderson", persona="Zenith", pasta_criacoes=str(r), pasta_biblia=r / "sem_cartoes", extra="")
    return dict(ind, action="projetos_dados")

HISTORICO = [
    {"sender": "user", "text": "Explique Euler–Lagrange passo a passo."},
    {"sender": "ai", "text": "Claro! Vamos devagar.\n\n**Passo 1.** Escolha as coordenadas generalizadas.\n\n- lista de exemplo\n- outro item\n\n```python\nfor i in range(3):\n    print(i)\n```\n\nPosso continuar?"},
    {"sender": "user", "text": "Pode sim, e depois faz um resumo."},
]
CONVERSAS = [
    {"id": "c1", "title": "Euler–Lagrange", "pinned": True, "created_at": "2026-10-18T10:00", "message_count": 3},
    {"id": "c2", "title": "Ladder e Grafcet", "pinned": False, "created_at": "2026-10-17T10:00", "message_count": 8},
    {"id": "c3", "title": "Roteiro do canal", "pinned": False, "created_at": "2026-10-10T10:00", "message_count": 5},
]
CMDS = [{"cmd": "/video", "uso": "<operação> <arquivo>", "desc": "edita vídeo"},
        {"cmd": "/imagem", "uso": "<descrição>", "desc": "cria uma imagem"},
        {"cmd": "/chaves", "uso": "", "desc": "mostra as chaves de IA"}]
SETTINGS = {"persona_name": "Zenith", "user_name": "Anderson", "onboarding_done": True}
CHAVES = {"action": "chaves_estado", "provedores": [
    {"id": "gemini", "nome": "Gemini", "chaves": [
        {"idx": 0, "mascara": "••••4_Rw", "principal": True, "estado": "livre", "segundos": 0},
        {"idx": 1, "mascara": "••••cet0", "principal": False, "estado": "castigo", "segundos": 42}]},
    {"id": "groq", "nome": "Groq", "chaves": []}],
    "rota": {}, "ia_local": {"ligada": False, "modelo": "", "servidor": ""},
    "como_obter": {"gemini": {"onde": "aistudio.google.com/apikey", "dica": "Entre com a conta Google e crie a chave.", "gratis": True}}}

async def mandar_cartoes(ws):
    """Cartões de atividade de exemplo (memória, código, pesquisa em andamento, erro)."""
    async def send(d): await ws.send(json.dumps(d))
    await asyncio.sleep(3)
    await send({"action": "cartao_atividade", "id": "m1", "tipo": "memoria", "titulo": "Adicionando à memória", "estado": "rodando",
                "detalhe": "Fulano estuda Automação Industrial no curso técnico"})
    await asyncio.sleep(0.6)
    await send({"action": "cartao_atividade", "id": "m1", "tipo": "memoria", "titulo": "Memória adicionada", "estado": "ok",
                "detalhe": "Fulano estuda Automação Industrial no curso técnico"})
    codigo = "import math\n\ndef energia_cinetica(m, v):\n    return 0.5 * m * v ** 2\n\nprint(energia_cinetica(2.0, 3.0))\n\n— Resultado —\n9.0"
    await send({"action": "cartao_atividade", "id": "c1", "tipo": "codigo", "titulo": "Código executado", "estado": "ok", "detalhe": codigo})
    await send({"action": "cartao_atividade", "id": "b1", "tipo": "busca", "titulo": "Pesquisando na web", "estado": "rodando",
                "detalhe": "equação de Euler-Lagrange pêndulo duplo"})
    await send({"action": "cartao_atividade", "id": "t1", "tipo": "terminal", "titulo": "Não foi feito: executando comando no terminal", "estado": "erro",
                "detalhe": "rm -rf /\n\n— Resultado —\n❌ comando bloqueado pela lista de segurança"})

async def handler(ws):
    print("[fake] Corpo conectou", flush=True)
    async def send(d): await ws.send(json.dumps(d))
    await send({"action": "brain_ready"})
    async for raw in ws:
        d = json.loads(raw); a = d.get("action")
        print("[fake] <-", a, flush=True)
        if a in ("request_sync", "load_conversation"):
            await send({"action": "conversation_loaded", "id": "c1", "title": "Euler–Lagrange", "messages": HISTORICO})
            if not getattr(ws, "_cartoes_enviados", False):
                ws._cartoes_enviados = True
                asyncio.create_task(mandar_cartoes(ws))
        elif a == "list_conversations":
            await send({"action": "conversations_list", "items": CONVERSAS})
        elif a == "list_projetos":
            await send(dados_biblioteca())
        elif a == "get_settings":
            await send({"action": "settings_data", "settings": SETTINGS})
        elif a == "pedir_comandos":
            await send({"action": "comandos_lista", "itens": CMDS})
        elif a == "chaves_listar":
            await send(CHAVES)
        elif a == "diagnostico_rodar":
            itens = [
                {"nome": "Versão", "status": "ok", "detalhe": "Zenith v1.2 · Python 3.12.3"},
                {"nome": "Teste de fala", "status": "erro", "detalhe": "o serviço de voz recusou (erro 403) — costuma ser edge-tts desatualizado: pip install -U edge-tts"},
                {"nome": "ffmpeg", "status": "aviso", "detalhe": "não encontrado — o /video e a conversão de fundo precisam dele. No terminal do Zenith: pip install imageio-ffmpeg (e abra o Zenith de novo)"},
                {"nome": "Administrador", "status": "aviso", "detalhe": "não — na PRIMEIRA vez, o Zenith.exe precisa ser aberto como administrador (botão direito → Executar como administrador)"},
                {"nome": "Saída de áudio", "status": "ok", "detalhe": "responde (44100 Hz)"},
                {"nome": "Internet", "status": "ok", "detalhe": "conectado"},
                {"nome": "Módulos nativos", "status": "ok", "detalhe": "carregam normalmente"},
                {"nome": "Espaço em disco", "status": "ok", "detalhe": "182 GB livres"},
            ]
            await send({"action": "diagnostico_resultado", "itens": itens, "relatorio": "Zenith — relatório de diagnóstico\n(exemplo)", "arquivo": "/tmp/relatorio.txt", "resumo": {"ok": 5, "aviso": 2, "erro": 1}})
        elif a == "chat":
            await send({"action": "chat_message", "sender": "ai", "text": "(Cérebro de mentira) Recebi: " + d.get("text", "")})

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("[fake] ouvindo em ws://localhost:8765", flush=True)
        await asyncio.Future()

asyncio.run(main())
