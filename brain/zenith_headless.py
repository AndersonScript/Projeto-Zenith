# ============================================================
#  ZENITH — Criado por Anderson
#  zenith_headless.py — O Cérebro SEM nenhuma janela Python.
#
#  Antes: a Central de Controle (zenith_ui.py) era uma janela CTk
#  paralela à do Corpo — duas janelas, duas experiências.
#  Agora: o Python só pensa (LLM, memória, gatekeeper) e conversa por
#  WebSocket com o Godot. TODA interface — chat, barra de conversas,
#  configurações, aprovação de ações — mora só na janela do Corpo.
# ============================================================

import threading
import uuid
import re
import time
import os

from brain.zenith_settings import ZenithSettings
from brain.zenith_core import ZenithCore, SYSTEM_NAME, CREATOR
from brain.zenith_bridge import ZenithBridge
from brain import zenith_plataforma                  # v1.11: port celular
from brain import zenith_history as history
from brain.zenith_validator import scan_persona_text, validate_path, strip_suspicious
from brain.zenith_proactive import ZenithProactive
from brain import zenith_actionlog as actionlog
from brain import zenith_notes as notes
from brain import zenith_commands as commands
from brain import zenith_notify as notify
from brain import zenith_vrm_import as vrm_import
from brain import zenith_pausa as pausa
from brain import zenith_observar as observar        # v23: observação ao vivo
from brain import zenith_emoji, zenith_captura       # v1.4: sem emoji no chat; print sem a janela do Zenith
from brain import zenith_movimentos as movimentos    # v1.6: pulo, dança, câmera, janela, caretas
from brain import zenith_presenca as presenca        # v1.7 (T3): buffer em memória + janela sensível
from brain import zenith_cadernos as cadernos_mod    # v1.7 (T6): cadernos de estudo
from brain import zenith_linguagens as linguagens_mod  # v1.7 (T5): compilar/rodar outras linguagens + pip guiado
from brain import zenith_desempenho as desempenho_mod  # v1.7 (T7): mede o PC e recomenda modelo local
from brain import zenith_stream as stream            # v24: streaming de texto e voz frase a frase
from brain import zenith_tft as tft_mod              # v24: Zenith num display TFT (ESP32-S3 por USB)
from brain import zenith_tema as tema_mod            # v25: cores da interface
from brain import zenith_lembretes as lembretes_mod
from brain import zenith_diag as diag
from brain import zenith_diario as diario
from brain import zenith_version
from brain import zenith_boas_vindas as boas_vindas
from brain import zenith_provedores as provedores
from brain import zenith_janela as janela_avatar
from brain import zenith_gestos as gestos
from brain import zenith_fundo as fundo_chat
from brain import zenith_reset as reset_dados
from brain import zenith_parar as parar              # v26: botão/palavra PARAR + o que ela está fazendo
from brain import zenith_matematica as matematica    # v26: LaTeX/fórmulas no chat
from brain import zenith_progresso as progresso_mod  # v28: barra de progresso + avisos popup no Corpo
from brain import zenith_anexos as anexos            # v28: anexo de QUALQUER tipo (zip, Word, Excel, PDF, vídeo…) + mini janela
from brain import zenith_quarentena as quarentena    # v28: texto de arquivo/web entra na IA como DADO, nunca como ordem
from brain import zenith_contas as contas            # v28: conferir as contas escritas nas respostas


class ZenithHeadlessBrain:
    _entrega_lock = threading.RLock()     # v23: resposta do chat e comentário da observação não se atropelam
    observador = None                     # v23: criado no __init__ (None em testes que montam o objeto na mão)
    tft = None                            # v24: idem (ligação com o display TFT)
    _atividade_atual = ("ocioso", "")     # v26: o que ela está fazendo agora (mostrado no Corpo)
    _conversa_voz = None                  # v1.7: /conversa (criada sob demanda; atributo de classe para instâncias montadas sem __init__)
    _sessao_atual = None                  # v26: sessão de streaming em andamento (pra o PARAR cortar)

    def __init__(self):
        # v20: se o usuário pediu "Resetar tudo", a limpeza roda AGORA — antes de abrir settings,
        # memória e histórico (no Windows não dá pra apagar arquivo que está em uso).
        try:
            from brain.zenith_settings import BASE_DIR as _base
            reset_dados.aplicar_se_pendente(_base)
        except Exception as e:
            print(f"[Zenith] Falha ao aplicar o reset pendente: {e}")
        self.settings = ZenithSettings()
        # v22 — cria (sem sobrescrever) config/biblia/perfis_modelos.json e config/ZENITH.md na primeira abertura
        try:
            from brain import zenith_conhecimento
            zenith_conhecimento.garantir_arquivos()
        except Exception as e:
            print(f"[Zenith/Conhecimento] arquivos padrão não criados: {e}")
        # v1.0 — config/creditos.txt: o texto de apresentação que o próprio Anderson escreve
        # (aparece no /sobre e em Configurações > Sobre), sem precisar recompilar nada.
        try:
            from brain import zenith_creditos
            zenith_creditos.garantir_arquivo()
        except Exception as e:
            print(f"[Zenith/Créditos] não criei o creditos.txt: {e}")
        self.core = ZenithCore(self.settings)
        self._aplicar_flags_v14()
        # v28 — o core (que não conhece o Corpo) pede a barra de progresso e a voz-em-arquivo por estes ganchos
        self.core.progresso_factory = self._novo_progresso
        self.core.atividade_fn = self._ao_cartao_atividade                 # v1.3 — cartões de atividade + sincronia do status no topo
        self.core.tts_arquivo_fn = self._tts_para_arquivo
        # v1.7 (T3) — presença em vídeo: a captura passa por aqui (buffer em memória, janela sensível,
        # quadro mais novo para o "olha a minha tela"). O Observador continua sendo o dono do laço.
        self.presenca = presenca.Presenca(
            self._obs_capturar, titulo_atual=zenith_captura.titulo_ativo,
            avisar=lambda texto: self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})
            if getattr(self, "bridge", None) is not None else None)
        try:
            self.core.presenca_fn = self.presenca.quadros_para_pedido
        except Exception as e:
            print(f"[Zenith/Presença] não liguei a resposta rápida: {e}")
        # v23 — observação ao vivo (câmera/tela): começa SÓ com aprovação; o laço roda numa thread própria
        self.observador = observar.Observador(
            capturar=self.presenca.capturar, comentar=self.core.observar_comentar,
            publicar=self._obs_publicar, estado=self._obs_estado)

        # CORREÇÃO CRÍTICA: tudo que os callbacks da Ponte podem tocar
        # precisa existir ANTES da Ponte subir — ela já começa a aceitar
        # conexão numa thread própria assim que é criada, e o Corpo
        # conecta rápido o suficiente pra pegar o Cérebro no meio do
        # __init__. Isso causava exatamente "conecta e cai na hora",
        # sempre: o callback de conexão tentava usar self.active_conv_id
        # / self.interaction antes deles serem atribuídos.
        self.active_conv_id = history.get_active_id()
        # v1.0 (A2c) — varredura ÚNICA das conversas antigas: se alguma chave foi digitada no chat
        # antes desta versão, ela fica mascarada no arquivo (uma vez só, marcada em config/).
        try:
            from brain import zenith_segredos as _segredos
            from brain.zenith_settings import CONFIG_DIR as _cfg
            n = _segredos.mascarar_arquivo_json(history.HISTORY_FILE, _cfg / ".segredos_mascarados")
            if n:
                print(f"[Zenith/Segredos] {n} mensagem(ns) antiga(s) tinham chave de API — valor mascarado.")
        except Exception as e:
            print(f"[Zenith/Segredos] varredura das conversas antigas falhou: {e}")
        try:
            self.core.definir_conversa(self.active_conv_id)     # v22: a Zenith lembra desta conversa (todas as IAs)
        except Exception as e:
            print(f"[Zenith/Contexto] não carreguei o histórico da conversa ativa: {e}")
        self._pending_approvals = {}   # request_id -> PendingAction
        self._ai_selecionar = ""       # v19: IA recém-adicionada (o Corpo seleciona na caixinha uma vez)
        self._pending_mic_approvals = set()   # request_id (aprovação do mic é
                                               # mais simples, não carrega uma
                                               # PendingAction do executor)
        # AJUSTE (mic "com delay enorme" / "aperto e não acontece nada"):
        # antes, TODO clique no microfone abria um pop-up de aprovação
        # — mesmo o 5º, 10º, 50º clique na mesma sessão. Pra quem tá
        # apresentando o Zenith ao vivo, isso trava a conversa: aperta,
        # nada parece acontecer na hora (o pop-up pode nem estar visível
        # dependendo da posição da janela), aí a pessoa desiste e digita.
        # Mantém a pergunta de segurança na PRIMEIRA vez (ninguém liga o
        # microfone sem eu perguntar antes) — da segunda vez em diante,
        # NA MESMA sessão (fecha o programa = pergunta nasce de novo),
        # já escuta na hora do clique.
        self._mic_aprovado_nesta_sessao = False
        self._proxima_fala_vira_nota = False   # v14: /nota_voz
        self._conversa_voz = None              # v1.7: /conversa (microfone sem apertar nada); criada na primeira vez

        # v1.11 (port celular) — no Android o Cérebro pede microfone, voz e câmera ao app PELO CORPO, usando o WebSocket que
        # já existe (ver zenith_ponte_corpo.py). A ponte nasce ANTES da voz (que pergunta o que o aparelho tem); o `enviar`
        # só olha `self.bridge` na hora de usar, quando ele já existe. No PC isto não faz nada.
        self._ponte_corpo = None
        if zenith_plataforma.detectar() == "android":
            from brain.zenith_ponte_corpo import PonteCorpo
            self._ponte_corpo = PonteCorpo(lambda dados: self.bridge.send(dados))
            zenith_plataforma.registrar_ponte(self._ponte_corpo)

        from brain.zenith_interaction import ZenithInteraction
        self.interaction = ZenithInteraction(self.settings)
        try:
            self.interaction.precarregar_whisper()          # v27: o modelo de transcrição carrega em segundo plano
        except Exception as e:
            print(f"[Zenith/Voz] pré-carga do Whisper: {e}")

        self.proactive = ZenithProactive(minutos_inatividade=self.settings.get("proactive_minutes", 15))
        self.proactive.set_callback(self._falar_espontaneamente)

        # v18 — lembretes (/lembrar): sobrevivem a reiniciar; o agendador confere a cada 15 s
        # e dispara os vencidos (os que venceram com o Zenith fechado saem assim que abre).
        # O armazenamento nasce ANTES da ponte (um comando pode chegar assim que ela subir).
        self.lembretes = lembretes_mod.Lembretes()

        # Só agora, com tudo pronto, a Ponte pode subir e aceitar conexão.
        self.bridge = ZenithBridge()
        self.bridge.set_state_callback(self._on_state)
        self.bridge.set_message_callback(self._on_message)

        # O agendador só COMEÇA depois da ponte existir (o disparo usa self.bridge).
        self.agendador = lembretes_mod.Agendador(self.lembretes, self._disparar_lembrete)
        self.agendador.start()

        # v24 — display TFT: procura sozinha a placa ESP32-S3 na USB e, se achar, manda o rosto da Zenith pra ela
        self.tft = tft_mod.TftLink(self.settings, self.bridge.send)
        self.tft.iniciar()

    # ---------------- conexão ----------------
    def _on_state(self, connected: bool):
        if getattr(self, "_ponte_corpo", None) is not None:        # v1.11: o Corpo (Android) conectou/caiu
            self._ponte_corpo.definir_conectado(connected)
        if connected:
            self.bridge.send({"action": "conversations_list", "items": history.list_conversations()})
            self._send_conversation_loaded(self.active_conv_id)
            self._mostrar_aviso_inicial()
            self.bridge.send({"action": "settings_data", "settings": self._settings_for_ui()})
            # Aplica a transparência salva assim que o Corpo conecta —
            # antes só acontecia se você abrisse Configurações e salvasse
            # de novo; agora persiste entre sessões de verdade.
            self.bridge.send({"action": "transparency", "value": self.settings.get("body_transparency", 1.0)})
            self._enviar_fundo_avatar()            # v23: fundo transparente / sólido / chroma
            self._enviar_tema()                    # v25: paleta de cores da interface (o Godot guarda e usa na próxima abertura)
            self._enviar_comandos()                # v28: lista pro autocompletar de "/"
            self._enviar_movimentos()              # v1.6: biblioteca de movimentos para o Corpo
            self._enviar_desempenho_config()       # v1.11: o downgrade escolhido (FPS, gráficos...) vale já na abertura
            self._avisar_novo_computador()
            if self.tft is not None:
                self.tft.reenviar_config()          # v24: o Godot acabou de (re)conectar: repete se há TFT ligado
            if self.settings.get("proactive_enabled", True):
                self.proactive.start()
            threading.Thread(target=self._checar_atualizacao_segundo_plano, daemon=True).start()


    def _checar_atualizacao_segundo_plano(self):
        try:
            url = str(self.settings.get("atualizar_url", "") or "").strip() or "https://projeto-zenith-five.vercel.app/versions.json"
            from brain import zenith_atualizar as at
            info, erro = at.consultar(url)
            if not erro and at.ha_novidade(info, zenith_version.VERSAO):
                self.bridge.send({
                    "action": "atualizacao_disponivel",
                    "versao": info["versao"],
                    "notas": info.get("notas", ""),
                    "url": info.get("url", ""),
                    "tamanho": info.get("tamanho", 0)
                })
        except Exception as e:
            print(f"[Zenith/Atualizar] Checagem em segundo plano: {e}")

    def _mostrar_aviso_inicial(self):
        """v18 — uma vez só: o que a Zenith pode/não pode fazer, pra onde vão as mensagens, /pausar."""
        try:
            if boas_vindas.deve_mostrar(self.settings):
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": boas_vindas.TEXTO})
                self.settings.update({"aviso_inicial_visto": True})
        except Exception as e:
            print(f"[Zenith/Boas-vindas] erro: {e}")

    # ---------------- fala espontânea (sem o usuário mandar nada) ----------------
    def _falar_espontaneamente(self):
        if pausa.ativo():          # v18: silêncio total — nada de puxar assunto
            return
        try:
            resultado = self.core.pensar(
                "[Sistema: um tempo se passou sem nenhuma mensagem sua. Puxe "
                "assunto por conta própria, algo breve e natural, na sua "
                "personalidade normal — não mencione que isso foi um lembrete "
                "automático.]"
            )
            texto = resultado.get("text", "")
            if texto and not resultado.get("blocked"):
                history.append_message(self.active_conv_id, "ai", texto)
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})
                if self.settings.get("voice_enabled", True):
                    self.interaction.falar_async(
                        texto,
                        on_start=lambda: self._estado("speaking"),
                        on_end=lambda: self._estado("idle"),
                    )
        except Exception as e:
            print(f"[Zenith/Proatividade] Erro ao falar espontaneamente: {e}")

    # ---------------- roteador de mensagens do Corpo ----------------
    def _on_message(self, data: dict):
        if getattr(self, "_ponte_corpo", None) is not None and self._ponte_corpo.tratar_mensagem(data):
            return              # v1.11: resposta/evento da ponte com o Android — não é um comando do usuário
        action = data.get("action")
        handler = {
            "chat": self._handle_chat,
            "ver_anexo": self._handle_ver_anexo,              # v28 — clicou num anexo: mini janela com prévia
            "pedir_comandos": lambda d: self._enviar_comandos(),   # v28 — autocompletar
            "list_conversations": self._handle_list_conversations,
            "new_conversation": self._handle_new_conversation,
            "checar_atualizacao": lambda d: threading.Thread(target=self._checar_atualizacao_segundo_plano, daemon=True).start(),
            "aplicar_atualizacao": lambda d: threading.Thread(target=self._rodar_atualizar, args=("instalar",), daemon=True).start(),
            "load_conversation": self._handle_load_conversation,
            "pin_conversation": self._handle_pin_conversation,
            "rename_conversation": self._handle_rename_conversation,
            "list_memories": self._handle_list_memories,
            "list_projetos": self._handle_list_projetos,            # v1.6: painel Biblioteca
            "fonte_add": self._handle_fonte_add,                    # v1.6.1: Biblioteca > Fontes (adicionar documento)
            "fonte_remover": self._handle_fonte_remover,
            "fonte_apagar_aprendido": self._handle_fonte_apagar_aprendido,
            "open_projeto": self._handle_open_projeto,
            "view_projeto": self._handle_view_projeto,
            "delete_conversation": self._handle_delete_conversation,
            "get_settings": self._handle_get_settings,
            "save_settings": self._handle_save_settings,
            "test_api_key": self._handle_test_api_key,
            "approval_response": self._handle_approval_response,
            "unlock": self._handle_unlock,
            "mic_start": self._handle_mic_start,
            "mic_stop": self._handle_mic_stop,
            "add_ai_endpoint": self._handle_add_ai_endpoint,
            "remove_ai_endpoint": self._handle_remove_ai_endpoint,
            "save_ai_entry": self._handle_save_ai_entry,
            "set_click_through": self._handle_set_click_through,
            "prepare_wallpaper": self._handle_prepare_wallpaper,
            "schedule_reset": self._handle_schedule_reset,
            "cancel_reset": self._handle_cancel_reset,
            "remove_ai_entry": self._handle_remove_ai_entry,
            "test_voice": self._handle_test_voice,
            "toast": self._handle_toast,
            "import_vrm_python": self._handle_import_vrm_python,
            "tft_frame": self._handle_tft_frame,           # v24
            "chaves_listar": self._handle_chaves_listar,   # v1.0 — página Chaves (A8)
            "chave_add": self._handle_chave_add,
            "chave_remover": self._handle_chave_remover,
            "chaves_testar": self._handle_chaves_testar,
            "ia_local": self._handle_ia_local_tela,
            "sobre": self._handle_sobre,                   # v1.0 — quem criou o Zenith
            "diagnostico_rodar": self._handle_diagnostico_rodar,   # v1.2 — "Saúde do Zenith" (Configurações → Sobre)
            "desempenho_pedir": self._handle_desempenho_pedir,     # v1.11 — Desempenho (downgrade)
            "desempenho_aplicar": self._handle_desempenho_aplicar,
        }.get(action)
        if handler:
            if action == "approval_response":
                # v26 — CORREÇÃO IMPORTANTE: este método roda DENTRO do laço do WebSocket (zenith_bridge._handler).
                # Aprovar uma ação executa o código/busca e depois ainda chama a IA de novo (cadeia) — tudo isso
                # travava o laço inteiro: enquanto durava, NENHUMA mensagem do Corpo era lida (nem o PARAR) e
                # nenhuma atualização chegava na tela (status, texto, imagem). Numa thread, a ponte continua viva.
                threading.Thread(target=handler, args=(data,), daemon=True).start()
            else:
                handler(data)

    # ---------------- v26: o que ela está fazendo + PARAR ----------------
    def _conversa(self):
        """v1.7 — a conversa por voz contínua (criada sob demanda)."""
        if self._conversa_voz is None:
            from brain import zenith_conversa_loop as cv
            self._conversa_voz = cv.ConversaContinua(
                abrir_microfone=lambda: self._handle_mic_start({}),
                avisar=lambda estado: self.bridge.send({"action": "conversa_estado", "estado": estado}),
                pode_abrir=lambda: self._atividade_atual[0] not in ("falando", "pensando", "rodando"))
        return self._conversa_voz

    _cartao_rodando_topo = None

    def _ao_cartao_atividade(self, cartao: dict):
        try:
            self.bridge.send(cartao)
            est = cartao.get("estado", "")
            titulo = str(cartao.get("titulo", "") or "")
            tipo = str(cartao.get("tipo", "") or "")
            if est == "rodando":
                est_topo = "buscando" if tipo == "busca" else ("programando" if tipo == "codigo" else "rodando")
                self._cartao_rodando_topo = (est_topo, titulo)
                self._atividade(est_topo, titulo)
            elif est in ("ok", "erro"):
                self._cartao_rodando_topo = None
        except Exception as e:
            print(f"[Zenith/CartaoAtividade] {e}")

    def _estado(self, nome: str):
        """Estado do corpo (thinking/speaking/idle) — igual ao que sempre foi enviado — e, junto, a linha de status
        que o Corpo mostra ("🧠 Pensando", "🔊 Falando"...). Se o TTS de uma frase inicial terminar enquanto uma busca
        ou ação ainda está rodando, preserva o status real da ação em vez de mostrar ocioso antes da hora."""
        if nome == "idle":
            if getattr(self, "_cartao_rodando_topo", None) is not None:
                est_t, txt_t = self._cartao_rodando_topo
                self._atividade(est_t, txt_t)
                return
            if getattr(getattr(self, "core", None), "is_processing", False):
                self._atividade("pensando")
                return
            if bool(getattr(self, "_pending_approvals", None)):
                self._atividade("aguardando")
                return
        self.bridge.send({"action": "do", "name": "state:" + nome})
        if nome == "idle" and self._conversa_voz is not None:
            self._conversa_voz.ao_ficar_ocioso()          # v1.7: terminou de responder: volta a escutar
        self._atividade({"thinking": "pensando", "speaking": "falando", "idle": "ocioso"}.get(nome, "ocioso"))

    def _atividade(self, estado: str, texto: str = ""):
        """Manda a linha de status pro Corpo (só quando muda). `estado` ∈ zenith_parar.ESTADOS."""
        if (estado, texto) == self._atividade_atual:
            return
        self._atividade_atual = (estado, texto)
        try:
            self.bridge.send(parar.mensagem_atividade(estado, texto))
        except Exception as e:
            print(f"[Zenith/Atividade] {e}")

    def _ha_algo_em_andamento(self) -> bool:
        return (self._atividade_atual[0] not in ("ocioso",)
                or bool(getattr(self, "_pending_approvals", None))
                or self._sessao_atual is not None)

    def _parar_tudo(self, motivo: str = "você pediu"):
        """v26 — PARAR: botão ⏹, /parar, "calma aí, Zenith" (texto ou voz). Corta tudo o que estiver em andamento:
        resultado de tarefa velha é descartado, processos que o Zenith abriu são mortos, a voz e o streaming param,
        o microfone desliga e os pedidos de aprovação abertos viram letra morta (ficam no log como "negada")."""
        havia = self._ha_algo_em_andamento()
        parar.solicitar(motivo)
        try:
            self.bridge.send({"action": "movement_stop"})      # v1.6: pára pulo/dança/passeio (câmera e janela ficam onde estão)
        except Exception:
            pass
        sessao = self._sessao_atual
        self._sessao_atual = None
        if sessao is not None:
            try:
                sessao.cancelar()
            except Exception:
                pass
        cancelados = getattr(self, "_pedidos_cancelados", None)
        if cancelados is None:
            cancelados = self._pedidos_cancelados = set()
        for rid, pend in list(self._pending_approvals.items()):
            cancelados.add(rid)
            try:
                actionlog.registrar(pend.kind, pend.description, "negada",
                                    detalhe=f"cancelada: {motivo}", conversa=self.active_conv_id)
            except Exception:
                pass
        self._pending_approvals.clear()
        for rid in list(self._pending_mic_approvals):
            cancelados.add(rid)
        self._pending_mic_approvals.clear()
        self._proxima_fala_vira_nota = False
        try:
            self._parar_observacao(motivo, avisar=False)
        except Exception:
            pass
        try:
            self.interaction.parar_de_escutar()
            self.interaction.parar_de_falar()
        except Exception as e:
            print(f"[Zenith/Parar] erro parando mic/voz: {e}")
        self.bridge.send({"action": "mic_state", "listening": False})
        self._estado("idle")
        self.bridge.send({"action": "chat_message", "sender": "ai",
                          "text": ("⏹ Parei. O que estava em andamento foi cancelado — é só pedir de novo quando quiser."
                                   if havia else "⏹ Tudo parado por aqui — não tinha nada em andamento. 🙂")})

    # ---------------- v26: matemática ----------------
    def _pasta_matematica(self):
        from brain.zenith_settings import CREATION_DIR
        from pathlib import Path
        return Path(CREATION_DIR) / "matematica"

    def _estilo_equacao(self):
        """Cores das imagens de equação: fundo/texto escolhidos nas configurações (padrão: escuro, combina com o chat)."""
        try:
            return matematica.EstiloImagem(fundo=self.settings.get("latex_fundo", "#10142b") or None,
                                           texto=self.settings.get("latex_texto", "#eef1ff"))
        except Exception:
            return matematica.ESTILO_ESCURO

    def _enviar_imagens_matematica(self, imagens):
        for caminho, legenda in imagens or []:
            self.bridge.send({"action": "chat_image", "path": caminho, "caption": legenda})

    def _rodar_matematica(self, args: dict):
        """/latex, /formula, /derivar... numa thread (desenhar leva ~1 s; o sympy, um pouco mais)."""
        from brain import zenith_formulas
        self._atividade("rodando", "Fazendo a conta" if args.get("tipo") in ("derivar", "integrar", "limite") else "Desenhando a equação")
        try:
            r = zenith_formulas.executar(args, self._pasta_matematica())
            if r.get("texto"):
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": r["texto"]})
            self._enviar_imagens_matematica(r.get("imagens"))
            # v27 — os comandos agora FALAM (você notou: "só não falou nada quando mandei isso"). Desliga com
            # `comandos_falam: false`. A fala lê a equação em português, não o LaTeX.
            if (r.get("fala") and self.settings.get("comandos_falam", True) and self.settings.get("voice_enabled", True)
                    and getattr(self.interaction, "pode_falar", lambda: False)()):
                try:
                    self.interaction.falar_async(r["fala"], on_start=lambda: self._estado("speaking"),
                                                 on_end=lambda: self._estado("idle"))
                except Exception as e:
                    print(f"[Zenith/Voz] comando mudo: {e}")
        except Exception as e:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": f"❌ Não consegui fazer a conta: {e}"})
        finally:
            self._atividade("ocioso")

    def _desfazer_troca_cancelada(self):
        """v27 — resposta descartada pelo PARAR: tira a troca da memória de longo prazo (ver core.desfazer_ultima_troca)."""
        try:
            self.core.desfazer_ultima_troca()
        except Exception as e:
            print(f"[Zenith/Parar] não consegui desfazer a troca: {e}")

    # ---------------- v28: progresso, vídeo, pastas, biblioteca, anexos, autocompletar ----------------
    def _novo_progresso(self, titulo: str, **kw):
        """Barra de progresso + aviso popup no Corpo (ver zenith_progresso). Usado também pelo core via gancho."""
        return progresso_mod.Progresso(self.bridge.send, titulo, **kw)

    def _tts_para_arquivo(self, texto: str, caminho: str) -> bool:
        """A voz da Zenith num arquivo (narração de vídeo). Sem motor de voz/sem internet: False e o vídeo sai mudo."""
        try:
            return bool(self.interaction.sintetizar_para_arquivo(texto, caminho))
        except Exception as e:
            print(f"[Zenith/Voz] sem voz pro vídeo: {e}")
            return False

    def _dizer(self, texto: str):
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

    def _rodar_video(self, args: dict):
        import json as _json
        self._atividade(*parar.estado_da_acao("video"))
        try:
            txt = self.core._executar_video(_json.dumps(args.get("pedido") or {}, ensure_ascii=False))
            self._dizer(txt)
            self._enviar_midias()
        except Exception as e:
            self._dizer(f"🎬 Deu erro no vídeo: {type(e).__name__}: {e}")
        finally:
            self._atividade("ocioso")

    def _rodar_organizar(self, args: dict):
        """Só LÊ a pasta e mostra o plano na janela de aprovação. Nada é mexido sem o seu OK."""
        import json as _json
        self._atividade("rodando", "Olhando a pasta")
        pend = None
        try:
            with self._novo_progresso("Olhando a pasta", detalhe="Só leitura — nada vai ser mexido ainda", avisar_no_fim=False) as p:
                pend = self.core._pendente_organizar(_json.dumps(args, ensure_ascii=False))
            veto = self.core.guard.check_action(pend.kind, pend.content)
            if veto:
                self._dizer(f"⛔ {veto}")
                pend = None
        except Exception as e:
            self._dizer(f"🗂️ Não consegui olhar a pasta: {type(e).__name__}: {e}")
            pend = None
        if pend is not None:
            self._request_approval(pend)
        else:
            self._atividade("ocioso")

    def _rodar_biblioteca_add(self, args: dict):
        from brain import zenith_biblioteca as bib
        caminho = str(args.get("caminho", "")).strip().strip('"')
        self._atividade("aprendendo", "Guardando na biblioteca")
        try:
            with self._novo_progresso("Guardando na biblioteca", detalhe=os.path.basename(caminho), avisar_no_fim=True) as p:
                res = bib.padrao().adicionar(caminho, progresso=p.callback())
            linhas = []
            if res["adicionados"]:
                linhas.append("📚 Guardei na biblioteca: " + ", ".join(f"{d['nome']} ({d['trechos']} trechos)" for d in res["adicionados"][:8]) +
                              (f" (+{len(res['adicionados']) - 8})" if len(res["adicionados"]) > 8 else "") + ".")
            if res["repetidos"]:
                linhas.append("(já estavam lá: " + ", ".join(d["nome"] for d in res["repetidos"][:5]) + ")")
            if res["erros"]:
                linhas.append("⚠ " + "; ".join(res["erros"][:4]))
            if res["adicionados"]:
                linhas.append("Agora é só perguntar — eu respondo citando o arquivo e a página. (/biblioteca buscar <pergunta> mostra os trechos.)")
            self._dizer("\n".join(linhas) or "📚 Nada novo pra guardar.")
        except bib.ErroBiblioteca as e:
            self._dizer(str(e))
        except Exception as e:
            self._dizer(f"📚 Não consegui guardar: {type(e).__name__}: {e}")
        finally:
            self._atividade("ocioso")

    def _handle_ver_anexo(self, data: dict):
        """Clicou num anexo (no chat ou na barra de envio): o Corpo abre uma mini janela com o que eu mostro aqui."""
        caminho = str(data.get("path", "") or "").strip()

        def _rodar():
            from brain.zenith_settings import TEMP_DIR
            try:
                r = anexos.resumo_para_visualizador(caminho, str(TEMP_DIR))
            except Exception as e:
                r = {"tipo": "outro", "nome": os.path.basename(caminho), "caminho": caminho, "tamanho": "",
                     "texto": f"Não consegui abrir a prévia: {e}", "miniatura": ""}
            self.bridge.send({"action": "anexo_resumo", **r})
        threading.Thread(target=_rodar, daemon=True).start()

    def _enviar_comandos(self):
        try:
            self.bridge.send({"action": "comandos_lista", "itens": commands.lista_para_autocompletar()})
        except Exception as e:
            print(f"[Zenith/Comandos] lista pro autocompletar: {e}")

    def _rodar_imagem_ia(self, args: dict):
        """v27 — /imagem: você digitou o comando, então o pedido É a sua aprovação (e o aviso de custo vai junto)."""
        from brain import zenith_imagem_ia as ia
        from brain.zenith_settings import CREATION_DIR
        geracao = parar.geracao()
        info = ia.interpretar_pedido(args.get("texto", ""))
        self._atividade(*parar.estado_da_acao("image_gen"))
        try:
            with self._novo_progresso("Criando a imagem com IA", detalhe="Esperando o gerador desenhar…", cancelavel=True,
                                      avisar_no_fim=False):
                chave_gem = str(self.settings.get("gemini_key", "") or "").strip()
                if not chave_gem:
                    r = ia.gerar_gratis(info["descricao"], CREATION_DIR, proporcao=info["proporcao"], settings=self.settings)
                else:
                    try:
                        r = ia.gerar(info["descricao"], chave_gem, CREATION_DIR,
                                     modelo=ia.modelo_para(info["qualidade"], self.settings), proporcao=info["proporcao"])
                    except ia.ErroImagem as e_gem:
                        if "O Google barrou por COTA" in str(e_gem) or "O Google não liberou imagem" in str(e_gem):
                            r = ia.gerar_gratis(info["descricao"], CREATION_DIR, proporcao=info["proporcao"], settings=self.settings)
                        else:
                            raise
            if parar.cancelado_desde(geracao):            # você mandou parar enquanto trabalhava
                return
            extra = f"\n{r['texto']}" if r.get("texto") else ""
            custo_txt = "Gerado gratuitamente." if "Pollinations" in r.get("modelo", "") or "Cloudflare" in r.get("modelo", "") else ia.aviso_de_custo(info["qualidade"])
            self.bridge.send({"action": "chat_message", "sender": "ai",
                              "text": f"🎨 Pronto! Criei a imagem com {r['modelo']}.{extra}\n({custo_txt})"})
            self.bridge.send({"action": "chat_image", "path": r["caminho"], "caption": "Imagem criada com IA"})
        except ia.ErroImagem as e:
            if not parar.cancelado_desde(geracao):
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": str(e)})
        except Exception as e:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": f"❌ Erro ao gerar a imagem: {e}"})
        finally:
            self._atividade("ocioso")

    def _mic_parcial(self, texto: str):
        """v27 — transcrição AO VIVO: o texto provisório aparece na caixa enquanto você fala; o final o substitui.
        Usa a mesma mensagem do texto final (o Corpo só troca o conteúdo da caixa) — nenhuma mudança no Godot."""
        if texto:
            self.bridge.send({"action": "mic_transcript", "text": texto, "parcial": True})

    def _mic_fase(self, fase: str):
        """v26 — fase do microfone pro Corpo desenhar (ouvindo / captando / transcrevendo / enviado / nada)."""
        rotulos = {"ouvindo": "Ouvindo… pode falar", "captando": "Captando sua voz", "transcrevendo": "Transcrevendo…",
                   "enviado": "Entendi — texto na caixa", "nada": "Não entendi nada"}
        self.bridge.send({"action": "mic_fase", "fase": fase, "texto": rotulos.get(fase, "")})

    # ---------------- chat ----------------
    def _handle_chat(self, data):
        text = data.get("text", "")
        # v1.0.1 — VÁRIOS anexos na mesma mensagem (pedido do Anderson: "mais de uma foto, colada ou não,
        # arquivo de texto etc."). O Corpo manda a lista em `attachment_paths`; `attachment_path` continua
        # aceito (compatibilidade) e entra como o primeiro da lista.
        lista = [str(p) for p in (data.get("attachment_paths") or []) if p]
        unico = data.get("attachment_path", "") or ""
        if unico and unico not in lista:
            lista.insert(0, unico)
        anexo = lista[0] if lista else ""
        if not text and not lista:
            return
        self.proactive.marcar_atividade()
        self._ultimo_pedido = text or ""           # v1.6 — o pedido do usuário (para "dá um pulo" virar pulo de verdade)
        # v14 — comandos "/..." resolvidos aqui, sem IA e sem entrar no
        # histórico/memória (ver zenith_commands.py). Texto que não é
        # comando conhecido segue o caminho normal. (Em silêncio total os
        # comandos continuam valendo — senão não haveria como /retomar.)
        if text and not lista:
            try:
                cmd = commands.tratar(text, {"settings": self.settings,
                                              "versao": zenith_version.texto(),
                                              "memory": getattr(self.core, "memory", None),
                                              "conv_id": self.active_conv_id,
                                              "lembretes": getattr(self, "lembretes", None),
                                              "core": self.core})            # v22: /contexto e /inteligencia usam o core
            except Exception as e:
                print(f"[Zenith/Comandos] erro: {e}")
                cmd = None
            if cmd is not None:
                self._executar_comando(cmd)
                return
        # v26 — "calma aí, Zenith" / "para" / "pare tudo" (digitado OU falado): para tudo, sem ir pra IA. Vale até em
        # silêncio total (é justamente o pedido de parar). Só mensagens CURTAS que são basicamente um pedido de parar.
        if text and not lista and parar.eh_pedido_de_parada(text, getattr(self.settings, "persona_name", "Zenith")):
            self._parar_tudo("você pediu (palavra de parada)")
            return
        if pausa.ativo():          # v18 — Pilar 1: em silêncio total NADA vai pra IA
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": pausa.mensagem_bloqueio()})
            self._estado("idle")
            return
        # v1.0 (A2) — chave de API digitada no chat: avisa e NUNCA manda o valor para a IA, para o
        # histórico nem para a memória (antes ele digitou uma chave inteira e ela ficou no balão).
        try:
            from brain import zenith_segredos as _segredos
            if text and _segredos.contem_segredo(text):
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": _segredos.AVISO_CHAVE_NO_CHAT})
                text = _segredos.mascarar(text)
        except Exception as e:
            print(f"[Zenith/Segredos] não consegui checar a mensagem: {e}")
        nomes = ", ".join(os.path.basename(p) for p in lista)
        history.append_message(self.active_conv_id, "user",
                                (f"📎 {nomes}\n{text}" if lista else text))
        self._estado("thinking")
        threading.Thread(target=self._think, args=(text, lista), daemon=True).start()

    # FEATURE (anexar arquivo/imagem): extensões de imagem viram uma
    # chamada multimodal de verdade (a IA "vê" o arquivo, se o provedor
    # ativo tiver suporte a visão); extensões de texto simples são lidas
    # e coladas no contexto da mensagem — mais simples e funciona com
    # QUALQUER provedor, mesmo os sem visão. Outros tipos (pdf/docx/etc)
    # ainda não têm leitor — avisa em vez de falhar silenciosamente.
    _EXT_IMAGEM = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
    # AMPLIADO (liberdade de anexar "qualquer coisa"): a lista antiga
    # (.txt/.md/.py/.json/.csv/.log) cobria só o básico. Qualquer coisa
    # que seja texto puro de verdade (não precisa de biblioteca nenhuma
    # pra ler, é só abrir e decodificar) agora entra — código de várias
    # linguagens, configs, dados estruturados, scripts, web. Isso NÃO
    # inclui formatos binários "disfarçados" de documento (PDF, DOCX,
    # XLSX, ZIP...) — ler esses como texto puro produziria só lixo
    # ilegível, então continuam caindo na mensagem de aviso abaixo até
    # ganharem um leitor de verdade (biblioteca dedicada, decisão em
    # separado por causa do peso/risco de cada uma).
    _EXT_TEXTO = {
        ".txt", ".md", ".markdown", ".log", ".csv", ".tsv",
        ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
        ".xml", ".html", ".htm", ".css", ".svg",
        ".py", ".pyw", ".gd", ".gdshader", ".js", ".mjs", ".ts", ".jsx", ".tsx",
        ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
        ".sh", ".bash", ".ps1", ".bat", ".sql", ".r", ".lua", ".swift", ".dart",
    }
    # Arquivos de texto comuns SEM extensão de verdade (ex: "Dockerfile",
    # ".gitignore") — os.path.splitext() trata um nome que começa com "."
    # como tendo extensão VAZIA (".gitignore" -> ext == ""), então esses
    # precisam ser reconhecidos pelo nome completo, não por _EXT_TEXTO.
    _MAX_IMAGEM_BYTES = 15_000_000   # v18: imagem acima disso é recusada antes de ler
    _NOMES_TEXTO = {"dockerfile", "makefile", ".gitignore", ".gitattributes",
                    ".editorconfig", ".env", "license", "readme"}

    def _ler_anexo(self, caminho: str):
        """Retorna (texto_extra, image_bytes, image_mime, erro)."""
        ext = os.path.splitext(caminho)[1].lower()
        nome = os.path.basename(caminho)
        try:
            if ext in self._EXT_IMAGEM:
                if os.path.getsize(caminho) > self._MAX_IMAGEM_BYTES:
                    return (None, None, None,
                            f"⚠️ A imagem '{nome}' é grande demais "
                            f"({os.path.getsize(caminho) / 1_000_000:.0f} MB; o limite é "
                            f"{self._MAX_IMAGEM_BYTES // 1_000_000} MB). Reduza e tente de novo.")
                with open(caminho, "rb") as f:
                    dados = f.read()
                return (f"[Imagem anexada: {nome}]", dados, self._EXT_IMAGEM[ext], None)
            if ext in self._EXT_TEXTO or nome.lower() in self._NOMES_TEXTO:
                TETO = 19000  # não deixa um arquivo gigante estourar o contexto da IA (v28: 19000 + o embrulho de quarentena ≈ 20000)
                # v18: lê só o começo (TETO+1 caracteres) — antes lia o arquivo INTEIRO na memória
                # e só depois cortava; um log de vários GB travava o Zenith.
                with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                    conteudo = f.read(TETO + 1)
                if len(conteudo) > TETO:
                    conteudo = conteudo[:TETO] + "\n[...conteúdo cortado, arquivo muito grande...]"
                # v28 — o que está DENTRO do arquivo é dado de fora: entra embrulhado (ver zenith_quarentena)
                return (quarentena.envolver(f"[Conteúdo do arquivo anexado '{nome}']:\n{conteudo}", nome,
                                            self.settings.user_name), None, None, None)
            # v28 — qualquer outro tipo (zip, Word, Excel, PowerPoint, PDF, vídeo, áudio, desconhecido): nunca mais "não sei ler"
            from brain.zenith_settings import TEMP_DIR
            return anexos.ler_anexo_geral(caminho, str(TEMP_DIR), usuario=self.settings.user_name)
        except Exception as e:
            return (None, None, None, f"⚠️ Não consegui ler o arquivo anexado: {e}")

    MAX_ANEXOS = 8            # v1.0.1: teto de anexos por mensagem (o Corpo também limita)

    def _combinar_imagens(self, imagens):
        """Junta várias imagens numa só, empilhadas, porque o modelo recebe UMA imagem por vez. Devolve os
        bytes PNG, ou None se não der (sem PIL, arquivo corrompido, altura absurda)."""
        try:
            from PIL import Image
            import io
            abertas = []
            for dados, _mime, nome in imagens:
                im = Image.open(io.BytesIO(dados)).convert("RGB")
                if im.width > 1200:
                    im = im.resize((1200, max(1, int(im.height * 1200 / im.width))), Image.LANCZOS)
                abertas.append(im)
            largura = max(im.width for im in abertas)
            altura = sum(im.height for im in abertas) + 8 * (len(abertas) - 1)
            if altura > 4000:                 # teto de sanidade: imagem gigante não vai pro modelo
                return None
            tela = Image.new("RGB", (largura, altura), (16, 20, 28))
            y = 0
            for im in abertas:
                tela.paste(im, ((largura - im.width) // 2, y))
                y += im.height + 8
            saida = io.BytesIO()
            tela.save(saida, format="PNG")
            return saida.getvalue()
        except Exception as e:
            print(f"[Zenith/Anexos] não consegui juntar as imagens: {e}")
            return None

    def _think(self, text, attachment_path=""):
        # v1.0.1 — aceita UM caminho (str) ou VÁRIOS (lista). Imagens múltiplas viram uma só montagem;
        # textos/documentos de qualquer tipo entram somados no contexto, cada um com seu cabeçalho.
        caminhos = (attachment_path if isinstance(attachment_path, (list, tuple))
                    else ([attachment_path] if attachment_path else []))
        caminhos = [str(c) for c in caminhos if c]
        image_bytes, image_mime = None, None
        extras, imagens = [], []
        if len(caminhos) > self.MAX_ANEXOS:
            sobrando = len(caminhos) - self.MAX_ANEXOS
            caminhos = caminhos[:self.MAX_ANEXOS]
            extras.append(f"[Aviso: {sobrando} anexo(s) ficaram de fora — o limite é {self.MAX_ANEXOS} por mensagem.]")
        for caminho in caminhos:
            extra, img_bytes, img_mime, erro = self._ler_anexo(caminho)
            if erro:
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": erro})
                self._estado("idle")
                return
            if img_bytes:
                imagens.append((img_bytes, img_mime, os.path.basename(caminho)))
            elif extra:
                extras.append(extra)
        if len(imagens) == 1:
            image_bytes, image_mime = imagens[0][0], imagens[0][1]
            extras.insert(0, f"[Imagem anexada: {imagens[0][2]}]")
        elif len(imagens) > 1:
            combinada = self._combinar_imagens(imagens)
            nomes = ", ".join(i[2] for i in imagens)
            if combinada:
                image_bytes, image_mime = combinada, "image/png"
                extras.insert(0, f"[{len(imagens)} imagens anexadas, una acima da outra: {nomes}]")
            else:
                image_bytes, image_mime = imagens[0][0], imagens[0][1]
                extras.insert(0, f"[Só a primeira imagem pôde ser enviada ({imagens[0][2]}); as outras não couberam: {nomes}]")
        if extras:
            texto_extra = "\n\n".join(extras)
            text = f"{texto_extra}\n\n{text}" if text else texto_extra
        sessao = self._abrir_sessao_stream()          # v24: a resposta sai frase a frase enquanto o modelo ainda gera
        self._sessao_atual = sessao                   # v26: o PARAR consegue cortar o streaming
        geracao = parar.geracao()                     # v26: se mandarem parar enquanto ela pensa, o resultado é descartado
        try:
            result = self.core.pensar(text, image_bytes=image_bytes, image_mime=image_mime,
                                      on_text=sessao.ao_liberar if sessao else None)
        except Exception as e:
            if sessao is not None:
                sessao.cancelar()
            # Rede de segurança: se ALGO explodir aqui (erro de rede, bug,
            # o que for), a pessoa recebe uma mensagem de erro no chat em
            # vez da conversa travar em silêncio pra sempre — foi
            # exatamente isso que causou o "manda mensagem e nunca
            # responde" que você viu.
            print(f"[Zenith/Cérebro] Erro processando mensagem: {e}")
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": f"❌ Deu erro processando isso: {e}"})
            self._estado("idle")
            return

        try:
            self._deliver_result(result, sessao, geracao)
        finally:
            if self._sessao_atual is sessao:
                self._sessao_atual = None

    def _abrir_sessao_stream(self):
        """v24 — sessão que leva cada frase liberada pelo portão do core até o balão do chat e até a voz.
        None = streaming desligado (em Configurações ou `streaming_real`/`response_streaming` = false)."""
        if not (self.settings.get("streaming_real", True) and self.settings.get("response_streaming", True)):
            return None
        caixa = {}

        def criar_fala():
            if not self.settings.get("voice_enabled", True) or not getattr(self.interaction, "pode_falar", lambda: False)():
                return None
            sess = caixa.get("sessao")
            expr = self._guess_expression(sess.liberado) if sess is not None else "neutral"
            return self.interaction.falar_stream_iniciar(
                on_start=lambda: self._estado("speaking"),
                on_end=lambda: self._estado("idle"),
                expressao=expr)

        caixa["sessao"] = stream.SessaoDeEntrega(self.bridge.send, criar_fala=criar_fala, pausado=pausa.ativo)
        return caixa["sessao"]

    def _deliver_result(self, result: dict, sessao=None, geracao=None):
        with self._entrega_lock:               # v23: uma entrega por vez (chat × observação ao vivo)
            self._deliver_result_sem_trava(result, sessao, geracao)

    def _deliver_result_sem_trava(self, result: dict, sessao=None, geracao=None):
        """Extraído de _think() pra poder ser reusado também quando uma
        AÇÃO EM VÁRIAS ETAPAS continua sozinha (ver continuar_cadeia() em
        zenith_core.py + _handle_approval_response abaixo) — o texto
        final de cada passo passa pelo MESMO caminho de entrega (streaming,
        TTS, aprovação da próxima ação) que uma resposta normal de chat."""
        if pausa.ativo() or (geracao is not None and parar.cancelado_desde(geracao)):
            # v18 — pausou enquanto a IA pensava: descarta a resposta e a ação proposta.
            # v26 — mesma coisa se mandaram PARAR enquanto ela pensava (botão ⏹ / "calma aí, Zenith").
            if sessao is not None:
                sessao.cancelar()  # v24: e corta o que já tinha começado a sair em streaming
            self._desfazer_troca_cancelada()
            self._estado("idle")
            return
        resp_text = result.get("text", "")
        pending = result.get("pending_action")
        veto = result.get("veto_reason")

        # v26 — MATEMÁTICA: a equação vira texto legível no balão + IMAGEM bonita logo abaixo, e a VOZ lê em português
        # ("x ao quadrado") em vez de soletrar a barra invertida. Sem matemática no texto = não faz nada.
        hist_text, fala_text, imagens_math, falhas_math = resp_text, resp_text, [], []
        if resp_text and self.settings.get("latex_ativo", True):
            try:
                rm = matematica.processar_resposta(resp_text, self._pasta_matematica(), self._estilo_equacao())
                resp_text, hist_text, fala_text, imagens_math = rm.chat, rm.historico, rm.fala, rm.imagens
                falhas_math = rm.falhas
            except Exception as e:
                print(f"[Zenith/Matemática] resposta entregue sem tratar a equação: {e}")

        if resp_text:
            history.append_message(self.active_conv_id, "ai", hist_text)
            # FEATURE (resposta em streaming): a MESMA resposta já
            # aprovada (passou pela segurança e extração de ações
            # normalmente, sem mudar nada disso) — o streaming só muda
            # COMO ela chega no chat. Em vez de um "chat_message" só, vai
            # em pedacinhos (frase por frase, reaproveitando o mesmo
            # separador já usado pra TTS) com um respiro pequeno entre
            # cada um, dando o efeito de "digitando ao vivo" sem abrir
            # mão da checagem de conteúdo acontecer ANTES de qualquer
            # coisa aparecer pro usuário.
            expressao = self._guess_expression(resp_text)
            entregue = False
            if sessao is not None and sessao.iniciada:
                # v24 — as primeiras frases JÁ saíram (texto e voz) enquanto o modelo gerava. Confere com o texto FINAL
                # (depois de segurança, validador, etiquetas): se bate, entrega só o que faltava; se não bate
                # (ex.: o validador reescreveu), corta a voz e entrega o final inteiro, no caminho de sempre.
                ok, resto = stream.reconciliar(sessao.liberado, resp_text)
                if ok:
                    resto_fala = None
                    if fala_text != resp_text:                    # v26: o que se LÊ difere do que se VÊ (equações)
                        ok_f, rf = stream.reconciliar(sessao.liberado_fala, fala_text)
                        resto_fala = rf if ok_f else None
                    sessao.entregar_resto(resto, resto_fala)
                    entregue = True
                else:
                    sessao.cancelar()
            if not entregue:
                # v24 — a VOZ começa ANTES do texto (o áudio da 1ª frase demora ~1 s pra ficar pronto, então ele corre
                # em paralelo) e o "digitando ao vivo" perdeu as pausas artificiais (eram até 0,6 s POR FRASE: uma
                # resposta de 6 frases esperava ~3,5 s à toa depois de o modelo já ter terminado).
                if self.settings.get("voice_enabled", True):
                    self.interaction.falar_async(
                        fala_text,                                # v26: equações em português falado
                        on_start=lambda: self._estado("speaking"),
                        on_end=lambda: self._estado("idle"),
                        expressao=expressao,
                    )
                if self.settings.get("response_streaming", True):
                    # v1.0 (A6): o texto é dividido SEM perder nada — antes isto colava um espaço no fim de
                    # cada pedaço e comia as quebras de linha (markdown virava um parágrafo só).
                    pedacos = stream.fatiar_preservando(resp_text.strip())
                    for pedaco in pedacos:
                        self.bridge.send({"action": "chat_stream_chunk", "delta": pedaco, "done": False})
                        time.sleep(min(0.08, 0.01 + len(pedaco) * 0.0015))
                    self.bridge.send({"action": "chat_stream_chunk", "delta": "", "done": True})
                else:
                    self.bridge.send({"action": "chat_message", "sender": "ai", "text": resp_text})
            self._enviar_imagens_matematica(imagens_math)       # v26: cartões com as equações desenhadas
            if self.settings.get("conferir_contas", True):       # v28: o computador refaz as contas escritas na resposta
                try:
                    aviso_contas = contas.aviso_para(contas.verificar_texto(resp_text))
                    if aviso_contas:
                        self.bridge.send({"action": "chat_message", "sender": "ai", "text": aviso_contas})
                except Exception as e:
                    print(f"[Zenith/Contas] não consegui conferir: {e}")
            if falhas_math:                                     # v27: o texto da equação já está no balão; só avisa
                nums = ", ".join(str(n) for n in falhas_math)
                self.bridge.send({"action": "chat_message", "sender": "ai",
                                  "text": f"(Não consegui desenhar a imagem da equação {nums} — a fórmula está escrita no texto acima.)"})
            # v21: se a IA escreveu <corpo>...</corpo>, o que ELA pediu manda; o palpite automático
            # só preenche o que ela não pediu.
            cmds = result.get("body_cmds") or []
            emocao_ia = next((n for t, n in cmds if t == "emocao"), None)
            gesto_ia = next((n for t, n in cmds if t == "gesto"), None)
            if emocao_ia:
                expressao = emocao_ia
            self.bridge.send({"action": "expression", "type": expressao})
            # v20: um gesto leve conforme o que ela diz (acenar no "oi", concordar no "sim"...).
            # Só quando o sinal é claro, e dá pra desligar em Configurações > Corpo / VRM > Vida.
            movs = self._movimentos_da_resposta(getattr(self, "_ultimo_pedido", ""), resp_text, cmds, result.get("mov_criacoes") or [])   # v1.6
            self._ultimo_pedido = ""                    # só vale para a primeira resposta a esse pedido
            self._receber_propostas_ajuste(result.get("propostas_ajuste") or [])     # v1.6.2
            if movs:
                self._tocar_movimentos(movs)
            elif gesto_ia:
                self.bridge.send({"action": "do", "name": "gesture:" + gesto_ia})
            elif self.settings.get("vida_gestos_ia", True) and self.settings.get("vida_nivel", "suave") != "desligado":
                gesto = gestos.escolher_gesto(resp_text)
                if gesto:
                    self.bridge.send({"action": "do", "name": "gesture:" + gesto})
            # (a voz agora começa antes do texto, acima, ou frase a frase pela sessão de streaming)
            if not self.settings.get("voice_enabled", True):
                self._estado("idle")
        else:
            if sessao is not None:
                sessao.cancelar()
            self._estado("idle")

        self._enviar_midias()          # v21: imagens que ela baixou/criou aparecem no chat
        for c in (result.get("comandos_auto") or []):          # v23: comandos que ELA acionou sozinha (leitura/estilo)
            self.bridge.send({"action": "chat_message", "sender": "ai",
                              "text": f"🔧 (a Zenith usou /{c['nome']})\n{c['saida']}"})

        if result.get("blocked"):
            return

        if pending and veto:
            actionlog.registrar(pending.kind, pending.description, "vetada", detalhe=str(veto),
                                conversa=self.active_conv_id)
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": f"⛔ {veto}"})
            return

        if pending:
            self._request_approval(pending)

    def _enviar_midias(self):
        """v21 — manda para o Corpo as imagens que a IA criou ou baixou (fila do core)."""
        try:
            for m in self.core.pegar_midias():
                self.bridge.send({"action": "chat_image", "path": m["path"], "caption": m.get("caption", "")})
        except Exception as e:
            print(f"[Zenith] Não consegui enviar a imagem pro chat: {e}")

    @staticmethod
    def _guess_expression(text: str) -> str:
        # v20: palavras inteiras e mais emoções (o antigo casava "rs" dentro de "versão"...)
        return gestos.escolher_expressao(text)

    # ---------------- aprovação de ações (Pilar 1, agora renderizada no Godot) ----------------
    def _request_approval(self, pending_action):
        request_id = uuid.uuid4().hex[:10]
        self._pending_approvals[request_id] = pending_action
        self._atividade("aguardando")          # v26: "✋ Esperando sua aprovação"
        self.bridge.send({
            "action": "approval_request",
            "request_id": request_id,
            "kind": pending_action.kind,
            "description": pending_action.description,
            "preview": pending_action.preview(),
        })

    def _handle_approval_response(self, data):
        request_id = data.get("request_id")
        approved = bool(data.get("approved"))

        # CORREÇÃO/FEATURE (microfone): pedidos de permissão do
        # microfone usam o MESMO protocolo approval_request/response que
        # já existia pras ações sensíveis do Pilar 1 — reaproveita a
        # aprovação/negação, mas o "aprovado" aqui liga o microfone em
        # vez de rodar uma PendingAction do executor.
        if request_id in self._pending_mic_approvals:
            self._pending_mic_approvals.discard(request_id)
            actionlog.registrar("microfone", "Ligar o microfone", "aprovada" if approved else "negada",
                                conversa=self.active_conv_id)
            if approved:
                self._mic_aprovado_nesta_sessao = True
                self._start_listening()
            else:
                self.bridge.send({"action": "chat_message", "sender": "ai",
                                   "text": "Tudo bem, sem microfone então. 🙂"})
            return

        pending = self._pending_approvals.pop(request_id, None)
        if not pending:
            if request_id in (getattr(self, "_pedidos_cancelados", None) or ()):
                # v26 — o pedido foi cancelado quando você mandou parar: avisa em vez de ficar mudo
                self.bridge.send({"action": "chat_message", "sender": "ai",
                                  "text": "⏹ Esse pedido foi cancelado quando você mandou parar — peça de novo se ainda quiser."})
            return
        if not approved:
            actionlog.registrar(pending.kind, pending.description, "negada", conversa=self.active_conv_id)
            resultado = "⛔ Ação negada por você. (Pilar 1 respeitado)"
            history.append_message(self.active_conv_id, "ai", resultado)
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": resultado})
            self._atividade("ocioso")
            return
        geracao = parar.geracao()                       # v26: se mandarem PARAR no meio, nada do que vem abaixo aparece
        self._atividade(*parar.estado_da_acao(pending.kind))   # v26: "⚙️ Rodando o código", "🔎 Pesquisando na web"...

        if pending.kind == "observe":          # v23: quem liga o observador é o Cérebro
            resultado = self._iniciar_observacao(pending.content)
            actionlog.registrar(pending.kind, pending.description, "aprovada", conversa=self.active_conv_id)
            history.append_message(self.active_conv_id, "ai", resultado)
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": resultado})
            return
        resultado = self.core.approve_action(pending)
        if parar.cancelado_desde(geracao):              # v26: mandaram parar enquanto rodava — descarta tudo
            self._desfazer_troca_cancelada()
            self._estado("idle")
            return
        self._enviar_midias()          # v21: ex.: a imagem que o script criou, ou as que a busca baixou
        actionlog.registrar(pending.kind, pending.description, "aprovada",
                            detalhe=str(resultado).splitlines()[0] if str(resultado).strip() else "",
                            conversa=self.active_conv_id)
        history.append_message(self.active_conv_id, "ai", resultado)

        # FEATURE (ações em várias etapas): antes, o resultado da ação
        # era sempre a ÚLTIMA coisa que acontecia — mesmo se a tarefa
        # pedida precisasse de mais de um passo (ex: "lê esse arquivo e
        # depois monta um gráfico com os dados"), a Zenith tinha que parar
        # e esperar o usuário mandar mensagem de novo pedindo o próximo
        # passo. Agora, com a permissão ligada, o resultado volta pra
        # própria IA (continuar_cadeia) pra ela decidir: terminou? responde
        # normal. Falta mais passo? prepara a próxima ação — que passa
        # pela MESMA aprovação de sempre (Pilar 1 não é pulado por estar
        # em cadeia). Busca e leitura de URL são exceção: `approve_action`
        # já devolve uma resposta pronta e sintetizada pra essas (ver
        # `_search_and_answer`/`_read_url_and_answer`), então encadear de
        # novo seria uma chamada de IA a mais sem necessidade.
        if self.settings.get("multi_step_actions", True) and pending.kind not in ("search", "read_url", "image_search", "image_gen", "learn", "observe",
                                                                       "video", "document", "organize"):    # v28: resultado pronto, sem chamada extra à IA
            self._atividade("pensando", "Pensando no próximo passo")
            resultado_dict = self.core.continuar_cadeia(
                resultado, pending.chain_original or resultado, pending.chain_step + 1)
            self._deliver_result(resultado_dict, None, geracao)
            # v14 — a cadeia acabou (nenhuma próxima ação esperando aprovação)?
            if not resultado_dict.get("pending_action"):
                self._avisar_fim_de_cadeia(pending, resultado_dict.get("text", ""))
        else:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": resultado})
            self._avisar_fim_de_cadeia(pending, resultado)
            self._atividade("ocioso")

    # ---------------- microfone (era um stub — agora captura e transcreve de verdade) ----------------
    def _handle_mic_start(self, data):
        if pausa.ativo():          # v18 — silêncio total: microfone não liga
            self.bridge.send({"action": "mic_state", "listening": False})
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": pausa.mensagem_bloqueio()})
            return
        perms = self.settings.get("permissions", {})
        estado = perms.get("microphone", "ask") if isinstance(perms, dict) else "ask"

        if estado == "never":
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": "🎙️ O uso do microfone está desativado nas suas permissões "
                                       "(Configurações > Permissões)."})
            return

        if self._mic_aprovado_nesta_sessao:
            # Já perguntou uma vez nesta sessão — escuta direto, sem
            # pop-up de novo (ver comentário no __init__).
            self._start_listening()
            return

        # Segunda camada de defesa (a primeira é a UI em ui_manager.gd,
        # que nem oferece "always" pra microphone/camera): mesmo que
        # alguém force "always" editando o settings.json na mão, o
        # microfone SEMPRE pede confirmação antes de gravar — câmera e
        # microfone são sensíveis demais num app de companhia com avatar
        # pra confiar só na trava da interface.
        request_id = uuid.uuid4().hex[:10]
        self._pending_mic_approvals.add(request_id)
        self.bridge.send({
            "action": "approval_request",
            "request_id": request_id,
            "kind": "microphone",
            "description": "Zenith quer ativar o microfone pra te ouvir.",
            "preview": "Vai gravar áudio do seu microfone até você apertar o botão de novo "
                       "(ou depois de 60s de segurança) e transcrever localmente — nada é "
                       "enviado pra nenhuma nuvem.",
        })

    def _handle_mic_stop(self, data):
        self.interaction.parar_de_escutar()

    def _start_listening(self):
        self.bridge.send({"action": "mic_state", "listening": True})

        def _ao_transcrever(texto: str):
            self.bridge.send({"action": "mic_state", "listening": False})
            self._mic_fase("enviado" if texto else "nada")          # v26
            if texto and self._proxima_fala_vira_nota:
                # v14 — /nota_voz: vira nota com data/hora, não vai pro chat
                self._proxima_fala_vira_nota = False
                ok_nota = notes.adicionar(texto, origem="voz")
                self.bridge.send({"action": "chat_message", "sender": "ai",
                                   "text": ("📝 Nota salva: " + texto) if ok_nota else "❌ Não consegui salvar a nota."})
            elif texto:
                # Manda pro Godot preencher a caixa de texto do chat com
                # a transcrição — o usuário revisa/edita e aperta
                # Enviar, igual digitando, em vez de mandar direto sem
                # o usuário ver o que foi entendido.
                # v1.7: com a conversa por voz LIGADA (o usuário digitou /conversa ligar) o Corpo envia sozinho:
                # o texto aparece na conversa como se tivesse sido digitado, sem apertar nada.
                auto = self._conversa_voz is not None and self._conversa_voz.ao_transcrever(texto) == "enviar"
                self.bridge.send({"action": "mic_transcript", "text": texto, **({"enviar": True} if auto else {})})
            elif self._conversa_voz is not None and self._conversa_voz.ligada:
                # v1.7: na conversa por voz, "não ouvi nada" não vira mensagem no chat a cada tentativa; ela tenta de novo
                # e, depois de algumas vezes, se desliga sozinha avisando.
                if self._conversa_voz.ao_transcrever("") == "desligou":
                    self.bridge.send({"action": "chat_message", "sender": "ai",
                                      "text": "Não ouvi ninguém, então desliguei a conversa por voz. Para voltar: /conversa ligar."})
            else:
                # v29 — ANTES: só "não consegui entender nada — tenta de novo?". O Anderson apertou o
                # microfone 4 vezes seguidas e recebeu essa frase 4 vezes, sem NENHUMA pista do motivo
                # (microfone mudo? dispositivo errado? silêncio? ruído?). Agora o Zenith mede o que
                # gravou e diz o que fazer.
                detalhe = self.interaction.explicacao_falha_mic()
                aviso = "🎙️ Não consegui entender nada."
                aviso += (" " + detalhe) if detalhe else " Tenta de novo?"
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": aviso})

        ok = self.interaction.comecar_a_escutar(_ao_transcrever, on_fase=self._mic_fase,       # v26: ouvindo/captando/transcrevendo
                                                on_parcial=self._mic_parcial)                  # v27: texto ao vivo na caixa
        if not ok:
            self.bridge.send({"action": "mic_state", "listening": False})
            try:
                motivo = self.interaction.motivo_de_nao_escutar()    # v1.14: no celular a frase certa; no PC, ""
            except Exception:
                motivo = ""
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": ("❌ " + motivo) if motivo else
                                       "❌ Não consegui acessar o microfone — confira se ele está "
                                       "conectado, ou se 'sounddevice'/'faster-whisper' estão "
                                       "instalados (veja requirements.txt)."})

    # ---------------- v14: comandos, aviso de fim de cadeia, testar voz ----------------
    def _executar_comando(self, cmd: dict):
        if cmd.get("resposta"):                    # v24: alguns comandos (ex.: /tft) respondem só pela ação
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": cmd["resposta"]})
        acao = cmd.get("acao")
        if acao == "parar":                           # v26 — /parar (e o botão ⏹ do Corpo)
            if self._conversa_voz is not None and self._conversa_voz.ligada:
                self._conversa_voz.desligar("você mandou parar")
            self._parar_tudo("você pediu (/parar)")
        elif acao == "conversa":                      # v1.7 — /conversa [ligar|desligar|status]: você digitou, então o pedido É a aprovação
            modo = str((cmd.get("args") or {}).get("modo", "")).lower()
            conv = self._conversa()
            if modo in ("desligar", "off", "parar", "sair"):
                texto = conv.desligar("você pediu")
            elif modo == "status":
                texto = conv.status()
            else:
                perms = self.settings.get("permissions", {})
                if pausa.ativo():
                    texto = pausa.mensagem_bloqueio()
                elif (perms.get("microphone", "ask") if isinstance(perms, dict) else "ask") == "never":
                    texto = "O microfone está bloqueado em Configurações > Permissões. Libere lá para usar a conversa por voz."
                else:
                    texto = conv.ligar()              # o microfone ainda passa pela aprovação de sempre (1ª vez da sessão)
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})
        elif acao == "matematica":                    # v26 — /latex, /formula, /derivar, /integrar, /limite
            threading.Thread(target=self._rodar_matematica, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "imagem_ia":                     # v27 — /imagem <descrição>: imagem de verdade por IA
            threading.Thread(target=self._rodar_imagem_ia, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "video":                         # v28 — /video ...: você digitou, então o pedido É a aprovação
            threading.Thread(target=self._rodar_video, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "organizar":                     # v28 — /organizar <pasta>: monta o PLANO e pede a sua aprovação
            threading.Thread(target=self._rodar_organizar, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "biblioteca_add":                # v28 — /biblioteca add <arquivo|pasta>
            threading.Thread(target=self._rodar_biblioteca_add, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "test_voice":
            self._handle_test_voice({})
        elif acao == "nota_voz":
            self._proxima_fala_vira_nota = True
        elif acao == "pausar":
            self._aplicar_pausa()
        elif acao == "retomar":
            if self.settings.get("proactive_enabled", True):
                self.proactive.start()
        elif acao == "diario":
            threading.Thread(target=self._rodar_diario, daemon=True).start()
        elif acao == "diagnostico":
            threading.Thread(target=self._rodar_diagnostico, daemon=True).start()
        elif acao == "relatorio":
            threading.Thread(target=self._rodar_relatorio, daemon=True).start()
        elif acao == "observar":                      # v23 — /observar [camera|tela] [segundos] [minutos]
            try:
                args = cmd.get("args") or {}
                tag = observar.montar_tag(args.get("tipo", "camera"), args.get("intervalo", self.settings.get("observar_intervalo_s", 20)),
                                          args.get("minutos", self.settings.get("observar_max_minutos", 15)), args.get("motivo", ""))
                pend = self.core.executor.create_pending("observe", tag, "observar ao vivo")
                self._request_approval(pend)
            except Exception as e:
                self.bridge.send({"action": "chat_message", "sender": "ai", "text": f"👁 Não consegui preparar a observação: {e}"})
        elif acao == "parar_observacao":
            self._parar_observacao("você pediu")
        elif acao == "projetos_enviar":               # v1.6 — /projetos: manda os dados para o painel também
            self._handle_list_projetos()
        elif acao == "mov_tocar":                     # v1.6 — /movimento <nome> [mais devagar]
            self._tocar_movimentos([cmd.get("args", {}).get("nome", "")],
                                   float((cmd.get("args") or {}).get("escala", 1.0) or 1.0))
        elif acao == "mov_recarregar":                # v1.6 — depois de /movimentos apagar
            self._enviar_movimentos()
        elif acao == "mov_danca":                     # v1.7 (T11b) — /dancar [BPM] [estilo]
            self._tocar_danca(cmd.get("args") or {})
        elif acao == "mov_fila":                      # v1.7 (T11c) — /movimentos encadear …
            self._tocar_fila(cmd.get("args") or {})
        elif acao == "conversa":                      # v1.7 (T10) — /conversa ligar|desligar|status
            self._rodar_conversa(cmd.get("args") or {})
        elif acao == "caderno_add":                   # v1.7 (T6) — /cadernos add
            threading.Thread(target=self._rodar_caderno_add, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "pip_instalar":                  # v1.7 (T5) — /instalar <pacote> confirmar
            threading.Thread(target=self._rodar_pip, args=(cmd.get("args") or {},), daemon=True).start()
        elif acao == "fundo_avatar":                  # v23
            self._enviar_fundo_avatar()
        elif acao == "ui_tema":                       # v25
            self._enviar_tema()
        elif acao == "tft_status":                    # v24 — /tft (sem argumentos)
            texto = self.tft.status() if self.tft is not None else "🖥 TFT indisponível."
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto +
                              "\nComo ligar: firmware/LEIA-ME.md (Arduino IDE) → plugue o ESP32-S3 na USB → o Zenith acha sozinho. "
                              "Se a sua placa usa ponte USB-serial (CH340/CP210x), use /tft porta COM7."})
        elif acao in ("tft", "tft_teste"):            # v24 — /tft ...
            if self.tft is not None:
                self.tft.reenviar_config()
                if acao == "tft_teste":
                    self.bridge.send({"action": "chat_message", "sender": "ai", "text": self.tft.enviar_teste()})
        elif acao == "listar_modelos":                # v23 — pede à API quais modelos a SUA chave enxerga (rede)
            threading.Thread(target=self._rodar_listar_modelos, daemon=True).start()
        elif acao == "recarregar_ia":                 # v30 — /chave, /rota, /local: vale já na próxima mensagem
            try:
                self.core.reload_api_keys(self.settings)
            except Exception as e:
                print(f"[Zenith/IA] recarregar depois do comando falhou: {e}")
        elif acao == "testar_chaves":                 # v30 — /chaves testar
            threading.Thread(target=self._rodar_testar_chaves, daemon=True).start()
        elif acao == "ajuste_testar":                 # v1.6.2 — /ajuste testar N (roda os testes numa cópia temporária)
            try:
                id_ajuste = int((cmd.get("args") or {}).get("id") or 0)
            except (TypeError, ValueError):
                id_ajuste = 0
            threading.Thread(target=self._rodar_ajuste_testar, args=(id_ajuste,), daemon=True).start()
        elif acao == "pedido_proprio":                # v1.5 — comando próprio: vira um pedido normal no chat
            pedido = str((cmd.get("args") or {}).get("texto") or "").strip()
            if pedido:
                threading.Thread(target=self._handle_chat, args=({"text": pedido},), daemon=True).start()
        elif acao == "atualizar":                     # v1.5 — /atualizar [baixar|instalar]
            threading.Thread(target=self._rodar_atualizar,
                             args=((cmd.get("args") or {}).get("passo", "consultar"),), daemon=True).start()
        elif acao == "baixar_local":                  # v30 — /local baixar [modelo]
            threading.Thread(target=self._rodar_baixar_local,
                             args=((cmd.get("args") or {}).get("modelo", ""),), daemon=True).start()

    # ---------------- v18: silêncio total, lembretes, diário, diagnóstico ----------------
    def _aplicar_pausa(self):
        """Efeitos de /pausar (o ESTADO já foi ligado em zenith_commands). Cancela o que
        estava pendente — cada cancelamento vai pro log de ações como "negada" (Pilar 1:
        o que não foi aprovado não roda, e fica registrado) —, para microfone e fala e
        silencia a fala espontânea. Pedidos de aprovação que ainda estejam abertos na
        tela viram letra morta: ao clicar, o Cérebro não os reconhece mais."""
        for pend in list(self._pending_approvals.values()):
            try:
                actionlog.registrar(pend.kind, pend.description, "negada",
                                    detalhe="cancelada pelo modo silêncio total", conversa=self.active_conv_id)
            except Exception:
                pass
        self._pending_approvals.clear()
        self._pending_mic_approvals.clear()
        self._proxima_fala_vira_nota = False
        self._parar_observacao("modo silêncio total (/pausar)", avisar=False)     # v23
        try:
            self.interaction.parar_de_escutar()
            self.interaction.parar_de_falar()
        except Exception as e:
            print(f"[Zenith/Pausa] erro parando mic/voz: {e}")
        try:
            self.proactive.stop()
        except Exception:
            pass
        self.bridge.send({"action": "mic_state", "listening": False})
        self._estado("idle")

    def _disparar_lembrete(self, item: dict, atraso_min: float):
        """Chamado pelo agendador. Devolve False pra ADIAR (silêncio total)."""
        if pausa.ativo():
            return False
        texto = f"⏰ Lembrete: {item.get('texto', '')}"
        if atraso_min >= 2:
            horas, minutos = divmod(int(atraso_min), 60)
            texto += f"  (era pra {item.get('quando', '')[11:16]}; passou {horas}h{minutos:02d}min — o Zenith estava fechado)" \
                if horas else f"  (era pra {item.get('quando', '')[11:16]}; atrasou {minutos} min)"
        try:
            history.append_message(self.active_conv_id, "ai", texto)
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})
            if self.bridge.is_connected:
                # O Corpo pisca a barra de tarefas e, com a Central fora de foco, devolve "toast"
                # pra cá mostrar a notificação nativa (mesmo caminho do fim de ação em cadeia).
                self.bridge.send({"action": "notify", "title": "Lembrete", "body": str(item.get("texto", ""))[:200]})
            else:
                notify.notificar("Lembrete", str(item.get("texto", ""))[:200])
        except Exception as e:
            print(f"[Zenith/Lembretes] erro ao avisar: {e}")
        return True

    def _rodar_diario(self):
        r = diario.gerar(self.core, self.core.memory, history.get_conversation(self.active_conv_id).get("messages", []),
                         self.settings.persona_name, self.settings.user_name or "o usuário")
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": r["mensagem"]})

    def _rodar_diagnostico(self):
        from brain.zenith_settings import BASE_DIR
        try:
            texto = diag.formatar(diag.testar_tudo(self.settings, base_dir=BASE_DIR))
        except Exception as e:
            texto = f"❌ O diagnóstico em si falhou: {e}"
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

    def _rodar_relatorio(self):
        from brain.zenith_settings import BASE_DIR, CREATION_DIR
        import datetime as _dt
        try:
            texto = diag.relatorio(self.settings, base_dir=BASE_DIR, rede=True)
            destino = os.path.join(str(CREATION_DIR), "exports",
                                   f"zenith_relatorio_{_dt.datetime.now():%Y%m%d_%H%M}.txt")
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "w", encoding="utf-8") as f:
                f.write(texto)
            texto += f"\n\n💾 Também salvei em: {destino}"
        except Exception as e:
            texto = f"❌ Não consegui montar o relatório: {e}"
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

    def _avisar_fim_de_cadeia(self, pending, texto_final: str):
        """Pede pro Corpo avisar (pisca a barra de tarefas e, se a Central
        não estiver em foco, o Corpo devolve 'toast' pra cá mostrar a
        notificação nativa). Nunca levanta exceção."""
        try:
            if not self.settings.get("notify_on_chain_end", True):
                return
            resumo = (texto_final or "").strip().splitlines()
            corpo = (resumo[0] if resumo else pending.description) or "Terminei o que você pediu."
            self.bridge.send({"action": "notify", "title": "Zenith terminou",
                              "body": corpo[:200]})
        except Exception as e:
            print(f"[Zenith/Notificação] erro: {e}")

    def _handle_toast(self, data):
        notify.notificar(data.get("title", "Zenith"), data.get("body", ""))

    # v17 — "Adicionar avatar ao projeto" usado FORA do editor do Godot
    # (rodando o .exe): o Corpo não consegue importar sozinho (essa API
    # só existe dentro do próprio editor), então pede pro Cérebro fazer
    # via linha de comando do Godot (ver zenith_vrm_import.py). Roda numa
    # thread à parte porque pode levar de segundos a minutos — nunca
    # visto rodando de verdade, então o tempo real é uma incógnita.
    def _handle_import_vrm_python(self, data):
        """v18 — "Adicionar avatar" rodando o .exe: o Corpo manda o caminho do .vrm e
        o Cérebro faz TUDO (copiar pra res://addons/avatars, importar com o Godot em
        linha de comando, reempacotar o .pck e reiniciar o Corpo). Nada pra configurar:
        zenith_vrm_import.localizar_ambiente() acha o Godot/projeto/preset/pck sozinho."""
        caminho = str(data.get("path", "") or "").strip()

        def _bolha(texto, historico=False):
            if historico:
                history.append_message(self.active_conv_id, "ai", texto)
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

        def _rodar():
            from brain import zenith_body_control
            from brain.zenith_settings import BASE_DIR

            ok_caminho, motivo = validate_path(caminho, "vrm")
            if not ok_caminho or not caminho:
                _bolha(f"⚠ {motivo or 'não recebi o caminho do arquivo .vrm.'}")
                return

            env = vrm_import.localizar_ambiente(BASE_DIR, self.settings.get)
            if env["log"]:
                print("[Zenith/Importação de avatar] " + env["log"])
            if env["faltando"]:
                _bolha("⚠ " + vrm_import.explicar_faltando(env["faltando"], BASE_DIR))
                return

            def _gravar_antes_do_reinicio(info):
                # Já deixa o avatar novo como o atual: depois do reinício o Corpo
                # carrega ele sozinho (mesmo caminho do "vrm_model_path" de sempre).
                self.settings.update({"vrm_model_path": info["avatar_path"]})
                history.append_message(
                    self.active_conv_id, "ai",
                    f"✓ Avatar \"{info['nome']}\" importado e já definido como o atual. "
                    f"Se preferir o anterior, é só clicar em \"Usar\" na lista de "
                    f"Configurações > Corpo / VRM.")

            _bolha("⏳ Vou importar o avatar (copiar, importar no Godot e reempacotar). "
                   "Isso leva de 1 a alguns minutos: espere a barra terminar e não feche o Zenith.")
            barra = self._novo_progresso("Importando o avatar", bloqueia=True, timeout=90,
                                         detalhe="Isso pode levar alguns minutos — não feche o Zenith", avisar_no_fim=True)
            barra.comecar()
            try:
                resultado = vrm_import.importar_vrm(
                    caminho, env,
                    progresso=lambda m: barra.etapa(m.rstrip("."), None, forcar=True),
                    trocar=zenith_body_control.trocar_e_reiniciar,
                    antes_de_trocar=_gravar_antes_do_reinicio)
            except Exception as e:
                barra.fim(ok=False, detalhe=f"{type(e).__name__}: {e}"[:150])
                raise
            barra.fim(ok=bool(resultado.get("ok")), detalhe=resultado.get("mensagem", "")[:150] if not resultado.get("ok") else "")

            if resultado.get("log"):
                print("[Zenith/Importação de avatar]\n" + resultado["log"])
            if resultado["ok"] and resultado.get("reiniciou"):
                return   # a mensagem final já está no histórico — o Corpo novo mostra ao reconectar
            icone = "✓" if resultado["ok"] else "⚠"
            texto = f"{icone} {resultado['mensagem']}"
            if not resultado["ok"]:
                texto += " (o log completo está em zenith_log.txt, ao lado do Zenith.exe)"
            _bolha(texto, historico=bool(resultado.get("reiniciou")) or resultado["ok"])

        threading.Thread(target=_rodar, daemon=True).start()

    def _handle_test_voice(self, data):
        if not self.settings.get("voice_enabled", True):
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": "🔇 A voz está desligada (Configurações > Voz). Ligue e teste de novo."})
            return
        frase = ("Olá! Este é um teste de voz. Se você está me ouvindo, "
                 "a voz está funcionando direitinho.")

        def _ao_terminar():
            self._estado("idle")
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": "🔊 Diagnóstico da voz:\n" + self.interaction.diagnostico_voz()})

        self.interaction.falar_async(
            frase,
            on_start=lambda: self._estado("speaking"),
            on_end=_ao_terminar,
            expressao="happy",
        )

    # ---------------- conversas ----------------
    def _handle_list_conversations(self, data):
        self.bridge.send({"action": "conversations_list", "items": history.list_conversations()})

    def _handle_new_conversation(self, data):
        self.active_conv_id = history.new_conversation()
        self._send_conversation_loaded(self.active_conv_id)
        self.bridge.send({"action": "conversations_list", "items": history.list_conversations()})

    def _handle_load_conversation(self, data):
        conv_id = data.get("id")
        if not conv_id:
            return
        self.active_conv_id = conv_id
        history.set_active_id(conv_id)
        self._send_conversation_loaded(conv_id)

    def _handle_pin_conversation(self, data):
        history.set_pinned(data.get("id"), bool(data.get("pinned", True)))
        self.bridge.send({"action": "conversations_list", "items": history.list_conversations()})

    def _handle_rename_conversation(self, data):
        # FEATURE (renomear conversa): já existia rename_conversation()
        # em zenith_history.py, só faltava esse fio ligando o pedido do
        # Corpo (Godot) até ele.
        conv_id = data.get("id")
        title = (data.get("title") or "").strip()
        if conv_id and title:
            history.rename_conversation(conv_id, title)
        self.bridge.send({"action": "conversations_list", "items": history.list_conversations()})

    # ---------------- v1.6: Biblioteca / Projetos Zenith ----------------
    def _handle_list_projetos(self, data=None):
        from brain import zenith_projetos as pj
        from brain import zenith_fontes as fontes
        try:
            ind = pj.indexar()
            # v1.6.1: junta "o que ela criou" com "o que ela usa como base" (documentos guardados + Bíblia) no mesmo painel
            ind["categorias"] = list(ind.get("categorias", [])) + fontes.categorias(
                user=str(self.settings.get("user_name", "") or ""), persona=str(self.settings.get("persona_name", "Zenith") or "Zenith"),
                pasta_criacoes=str(pj.raiz_padrao()))
            self.bridge.send(dict(ind, action="projetos_dados"))
        except Exception as e:
            print(f"[Zenith/Projetos] {e}")
            self.bridge.send({"action": "projetos_dados", "pasta": "", "total": 0, "categorias": []})

    def _handle_fonte_add(self, data):
        """v1.6.1 — o painel Biblioteca > Fontes: documento escolhido pela pessoa no seletor de arquivos (mesma rotina do /biblioteca add)."""
        caminho = str((data or {}).get("caminho", "") or "").strip()
        if not caminho:
            return

        def _fazer():
            self._rodar_biblioteca_add({"caminho": caminho})
            self._handle_list_projetos()
        threading.Thread(target=_fazer, daemon=True).start()

    def _handle_fonte_remover(self, data):
        """v1.6.1 — tira um documento do índice da biblioteca (o arquivo original não é tocado)."""
        from brain import zenith_fontes as fontes
        _ok, msg = fontes.tirar_fonte(str((data or {}).get("id", "")))
        self._dizer(msg)
        self._handle_list_projetos()

    def _handle_fonte_apagar_aprendido(self, data):
        """v1.6.1 — apaga um cartão que a própria Zenith aprendeu (só `aprendido-...`)."""
        from brain import zenith_fontes as fontes
        _ok, msg = fontes.apagar_aprendido(str((data or {}).get("id", "")))
        self._dizer(msg)
        self._handle_list_projetos()

    def _handle_open_projeto(self, data):
        from brain import zenith_projetos as pj
        ok, msg = pj.abrir_no_explorador(str((data or {}).get("caminho", "")))
        if not ok:
            self._dizer(msg)

    def _handle_view_projeto(self, data):
        from brain import zenith_projetos as pj
        img = pj.caminho_de_imagem(str((data or {}).get("caminho", "")))
        if img:
            self.bridge.send({"action": "chat_image", "path": img, "caption": os.path.basename(img)})
        else:
            self._dizer("Só consigo mostrar no chat imagens que estão na pasta de criações.")

    def _handle_list_memories(self, data):
        # FEATURE ("mostra as coisas que ela lembra"): expõe pro Corpo
        # o que já está guardado na memória de longo prazo — não é
        # uma nova capacidade da IA, é só deixar VISÍVEL uma que já
        # existia (o recall já rodava por trás de cada resposta).
        itens = self.core.memory.list_recent(limit=int(data.get("limit", 30)))
        self.bridge.send({"action": "memories_list", "items": itens})

    def _handle_delete_conversation(self, data):
        conv_id = data.get("id")
        history.delete_conversation(conv_id)
        if conv_id == self.active_conv_id:
            remaining = history.list_conversations()
            self.active_conv_id = remaining[0]["id"] if remaining else history.new_conversation()
            self._send_conversation_loaded(self.active_conv_id)
        self.bridge.send({"action": "conversations_list", "items": history.list_conversations()})

    def _send_conversation_loaded(self, conv_id):
        try:
            self.core.definir_conversa(conv_id)      # v22: nova/troca/apagar → sessão e histórico da conversa certa
        except Exception as e:
            print(f"[Zenith/Contexto] histórico não recolocado: {e}")
        conv = history.get_conversation(conv_id)
        self.bridge.send({
            "action": "conversation_loaded",
            "id": conv["id"], "title": conv.get("title", ""),
            "messages": [{"sender": m["sender"], "text": m["text"]} for m in conv.get("messages", [])],
        })

    # ---------------- configurações (agora editadas 100% pelo Godot) ----------------
    def _settings_for_ui(self) -> dict:
        # Manda o dicionário inteiro — é rodando local, sem servidor
        # remoto no meio, então não tem por que esconder as próprias
        # chaves do próprio dono delas na tela de configurações.
        d = dict(self.settings.settings)
        # v19: visão unificada das IAs (a caixinha do painel "IAs & Chaves"). Vem do catálogo
        # OPCIONAL — sem ele (cópia de distribuição) a lista traz só as IAs que a pessoa cadastrou.
        try:
            d["_ai_ui"] = provedores.dados_para_ui(d)
        except Exception as e:
            print(f"[Zenith] Não consegui montar a lista de IAs: {e}")
            d["_ai_ui"] = {"entradas": [], "atalhos": [], "catalogo_vazio": True}
        d["_ai_ui"]["selecionar"] = getattr(self, "_ai_selecionar", "")
        self._ai_selecionar = ""
        return d

    def _handle_get_settings(self, data):
        self.bridge.send({"action": "settings_data", "settings": self._settings_for_ui()})

    @staticmethod
    def _maybe_convert_video_wallpaper(path: str):
        """Retorna (caminho_final, aviso_ou_none). Converte vídeos comuns
        (e agora GIF animado) pra .ogv via ffmpeg automaticamente, se o
        ffmpeg existir no sistema. Não mexe em caminho vazio, imagem
        estática, ou já-.ogv.

        NOVO (GIF sem animar): antes, .gif entrava só pela lista de
        "imagem" do validador (zenith_validator.py) — o Godot carrega
        isso como imagem ESTÁTICA (primeiro quadro só), então um GIF
        animado escolhido como fundo virava uma foto parada, sem avisar
        por quê. Agora GIF passa pelo mesmo caminho de conversão que
        vídeo — vira .ogv de verdade (com animação) quando o ffmpeg
        está disponível, do jeito que o Godot sabe tocar nativamente. Se
        não tiver ffmpeg, cai pro comportamento antigo (imagem estática
        do validador) — silencioso, mas não quebra nada.
        """
        import shutil
        import subprocess
        from pathlib import Path

        if not path:
            return path, None
        p = Path(path)
        ext = p.suffix.lower()
        if ext not in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif"):
            return path, None   # não é vídeo/gif, ou já é .ogv/imagem — segue normal

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            if ext == ".gif":
                return path, None   # sem ffmpeg: deixa cair pro caminho de imagem estática (GIF ainda é aceito, só que parado)
            return path, (
                "chat_wallpaper_path: você escolheu um vídeo (" + ext + "), mas o Zenith não "
                "encontrou o ffmpeg instalado neste computador pra converter automaticamente. "
                "Instale o ffmpeg (ffmpeg.org) e tente salvar de novo, ou converta manualmente "
                "com: ffmpeg -i \"" + str(p) + "\" -c:v libtheora -c:a libvorbis fundo.ogv"
            )

        destino = p.with_suffix(".ogv")
        try:
            r = subprocess.run(
                [ffmpeg, "-y", "-i", str(p), "-c:v", "libtheora", "-q:v", "7",
                 "-c:a", "libvorbis", str(destino)],
                capture_output=True, text=True, timeout=120)
            if r.returncode == 0 and destino.exists():
                return str(destino), None
            if ext == ".gif":
                return path, None   # falhou convertendo o GIF: melhor um fundo parado do que travar o salvamento
            return path, (f"chat_wallpaper_path: tentei converter '{p.name}' pra .ogv "
                           f"automaticamente e não deu certo (ffmpeg retornou erro) — "
                           f"caminho não foi salvo.")
        except Exception as e:
            if ext == ".gif":
                return path, None
            return path, f"chat_wallpaper_path: erro convertendo vídeo automaticamente ({e})."

    def _handle_save_settings(self, data):
        changes = data.get("changes", {})
        warnings = []
        from brain.zenith_content_safety import vrm_filename_suspicious

        # FEATURE (fundo em .mp4 "ou uma transformação"): a maioria das
        # pessoas não tem ffmpeg na cabeça nem quer converter nada na
        # mão. Se chegar um vídeo comum aqui (mp4/mov/webm/mkv/avi) e o
        # ffmpeg estiver disponível no sistema, converte sozinho pra
        # .ogv (formato que o Godot lê nativamente) antes mesmo de
        # validar o caminho — a pessoa só escolhe o mp4 de sempre e o
        # Zenith cuida do resto. Se não tiver ffmpeg instalado, cai pra
        # trás normalmente (o validador recusa com a mensagem de sempre),
        # mas com um aviso mais claro do que fazer.
        # v20: o fundo aceita qualquer imagem/vídeo; a conversão (sem ffmpeg) acontece sob demanda em
        # _handle_prepare_wallpaper quando o Corpo pede. O caminho salvo é sempre o ORIGINAL do usuário.

        for key in ("persona_description", "user_pillars"):
            if key in changes:
                hits = scan_persona_text(changes[key])
                if hits:
                    warnings.append(f"{key}: trecho suspeito ignorado (\"{hits[0]}\") — "
                                     f"o filtro de segurança remove isso automaticamente do prompt.")

        for key, kind in (("vrm_model_path", "vrm"), ("chat_wallpaper_path", "image"),
                          ("rvc_model_path", "rvc_model"), ("rvc_index_path", "rvc_index")):
            if key in changes:
                ok, motivo = validate_path(changes[key], kind)
                if not ok:
                    warnings.append(f"{key}: {motivo} — caminho não foi salvo.")
                    changes[key] = self.settings.get(key, "")  # mantém o valor anterior

        # v20: o python.exe do RVC é EXECUTADO pelo Zenith — só aceita um arquivo que se chame python(.exe).
        if "rvc_python_exe" in changes and str(changes["rvc_python_exe"] or "").strip():
            from brain.zenith_rvc import python_valido
            if not python_valido(changes["rvc_python_exe"]):
                warnings.append("rvc_python_exe: precisa ser o caminho de um arquivo python.exe que exista "
                                 "— caminho não foi salvo.")
                changes["rvc_python_exe"] = self.settings.get("rvc_python_exe", "")

        # Checagem extra específica do VRM: nome de arquivo com termo
        # associado a menor de idade. Isso NÃO é uma garantia — não dá pra
        # "olhar" o modelo 3D e saber se representa uma criança — mas pega
        # o caso óbvio, e a recusa é definitiva, não um simples aviso.
        if "vrm_model_path" in changes and vrm_filename_suspicious(changes["vrm_model_path"]):
            warnings.append("vrm_model_path: nome de arquivo recusado — indica conteúdo "
                             "envolvendo menor de idade. Isso não é negociável.")
            changes["vrm_model_path"] = self.settings.get("vrm_model_path", "")

        # Piso de segurança: câmera e microfone NUNCA podem ir pra "always"
        # (executar sem perguntar) num app de companhia com avatar/voz —
        # o risco de uso indevido é alto demais pra deixar isso configurável
        # sem confirmação. "ask" ou "never" continuam livres.
        if "permissions" in changes:
            perms = changes["permissions"]
            for sensitive in ("camera", "microphone"):
                if perms.get(sensitive) == "always":
                    perms[sensitive] = "ask"
                    warnings.append(f"Permissão '{sensitive}': 'sempre permitir' não é "
                                     f"oferecido por segurança — voltou pra 'perguntar'.")

        self.settings.update(changes)
        self._aplicar_flags_v14()
        self.core.reload_api_keys(self.settings)
        if "tts_volume" in changes:
            self.interaction.set_volume(changes["tts_volume"])
        if "proactive_minutes" in changes:
            self.proactive.set_intervalo(changes["proactive_minutes"])
        if "proactive_enabled" in changes:
            if changes["proactive_enabled"]:
                self.proactive.start()
            else:
                self.proactive.stop()
        # CORREÇÃO: a transparência era salva no Cérebro mas NUNCA
        # repassada de volta pro Corpo aplicar de verdade — o slider
        # "funcionava" (salvava o número), só não fazia nada visível.
        if "body_transparency" in changes:
            self.bridge.send({"action": "transparency", "value": changes["body_transparency"]})
        self.bridge.send({"action": "settings_saved", "warnings": warnings})

    def _enviar_tema(self):
        self.bridge.send({"action": "ui_tema", "paleta": tema_mod.paleta_dos_settings(self.settings)})

    # ---------------- v24: TFT ----------------
    def _handle_tft_frame(self, data):
        """Quadro do rosto da Zenith vindo do Godot (JPEG em base64) -> placa. Só guarda o mais recente."""
        if self.tft is not None:
            self.tft.on_quadro(tft_mod.decodificar_quadro_base64(data.get("jpg", "")))

    # ---------------- v23: observação ao vivo, fundo do avatar, modelos ----------------
    # ---------------- v1.7 (T6): caderno ----------------
    def _rodar_caderno_add(self, args: dict):
        caminho = str((args or {}).get("caminho") or "")
        try:
            cad = cadernos_mod.padrao()
            res = cad.adicionar("", caminho,
                                progresso=lambda pct, det=None: self.bridge.send(
                                    {"action": "progress", "value": max(0.0, min(1.0, float(pct or 0) / 100.0)),
                                     "text": det or "Guardando no caderno…"}))
            texto = (f"📓 No caderno '{res['caderno']}': {len(res['adicionados'])} arquivo(s) novo(s), "
                     f"{len(res['repetidos'])} já estavam. Fontes: {len(res['fontes'])}.")
            if res.get("erros"):
                texto += "\n⚠ " + "; ".join(res["erros"][:5])
        except Exception as e:
            texto = f"📓 Não consegui guardar: {e}"
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

    # ---------------- v1.7 (T5): pip guiado ----------------
    def _rodar_pip(self, args: dict):
        pacote = str((args or {}).get("pacote") or "")
        try:
            info = linguagens_mod.info_pacote(pacote)
            cmd = linguagens_mod.comando_pip(info["nome"], info["versao"])
        except Exception as e:
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": f"📦 Não consegui conferir o pacote no PyPI ({type(e).__name__}). Sem a versão e a licença eu não instalo."})
            return
        self.bridge.send({"action": "chat_message", "sender": "ai",
                           "text": f"📦 Instalando {info['nome']} {info['versao']} (licença: {info['licenca']})…"})
        try:
            r = __import__("subprocess").run(cmd, capture_output=True, text=True, timeout=300)
            saida = (r.stdout or "") + (r.stderr or "")
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": (
                ("✅ Instalado: " if r.returncode == 0 else "❌ O pip falhou: ") + info["nome"] + " " + info["versao"]
                + ("\n" + "\n".join(saida.strip().splitlines()[-6:]) if saida.strip() else ""))})
        except Exception as e:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": f"❌ Não consegui rodar o pip: {e}"})

    # ---------------- v1.7 (T11): dança por BPM e fila de movimentos ----------------
    def _enviar_biblioteca_movimentos(self, extra: dict = None):
        lib = movimentos.biblioteca()
        if extra:
            lib.update(extra)
        self.bridge.send({"action": "movement_library", "clips": lib})

    def _tocar_danca(self, args: dict):
        clipe, erro = movimentos.gerar_danca((args or {}).get("bpm", 100), (args or {}).get("estilo", "animada"))
        if erro or not clipe:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": "💃 " + (erro or "não consegui montar a dança")})
            return
        self._enviar_biblioteca_movimentos({clipe["nome"]: clipe})
        self.bridge.send({"action": "movement_play", "nome": clipe["nome"], "escala": 1.0})

    def _tocar_fila(self, args: dict):
        fila = (args or {}).get("fila") or []
        for passo in fila:
            self.bridge.send({"action": "movement_play", "nome": passo["nome"], "escala": passo.get("escala", 1.0)})

    def _obs_capturar(self, tipo: str):
        if tipo == "screen":
            return self.core.vision.capture_screen(max_w=1280, jpeg=True, ocultar_area=0.25)   # v1.4: só some a janela GRANDE
        return self.core.vision.capture_camera(max_w=1280)

    def _obs_publicar(self, texto: str):
        try:
            self._deliver_result({"text": "👁 " + texto, "pending_action": None, "blocked": False})
        except Exception as e:
            print(f"[Zenith/Observar] não consegui publicar: {e}")

    def _obs_estado(self, ativo: bool, tipo: str, info: str):
        self.bridge.send({"action": "observando", "ativo": bool(ativo), "tipo": tipo, "info": info})
        if not ativo:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": f"👁 Parei de observar ({info})."})

    # ---------------- v1.6: movimentos ----------------
    def _enviar_movimentos(self):
        """Manda a biblioteca (prontos + criados) para o Corpo e ensina o Cérebro quais nomes existem."""
        try:
            lib = movimentos.biblioteca()
            gestos.MOVIMENTOS_CONHECIDOS.clear()
            gestos.MOVIMENTOS_CONHECIDOS.update(lib)
            self.bridge.send({"action": "movement_library", "clips": lib})
            self.bridge.send({"action": "movement_config", "janela": bool(self.settings.get("movimentos_janela", True)),
                              "camera": bool(self.settings.get("movimentos_camera", True))})
        except Exception as e:
            print(f"[Zenith/Movimentos] não consegui enviar a biblioteca: {e}")

    def _tocar_movimentos(self, nomes, escala: float = 1.0):
        if not self.settings.get("movimentos_ativos", True) or not nomes:
            return
        try:
            escala = max(0.3, min(3.0, float(escala)))
        except (TypeError, ValueError):
            escala = 1.0
        for nome in list(nomes)[:movimentos.FILA_MAX]:
            self.bridge.send({"action": "movement_play", "nome": nome, "escala": escala})

    def _criar_movimentos_da_ia(self, brutos):
        """A IA escreveu <criar_movimento>: valida, guarda, manda ao Corpo e CONTA ao usuário o que aconteceu de verdade."""
        criou = False
        for bruto in brutos:
            clipe, avisos, erro = movimentos.criar_de_texto(bruto)
            if erro:
                self.bridge.send({"action": "chat_message", "sender": "ai",
                                  "text": f"(Não consegui criar esse movimento: {erro})"})
                continue
            criou = True
            extra = (" Ajustes: " + "; ".join(avisos[:3]) + ".") if avisos else ""
            self.bridge.send({"action": "chat_message", "sender": "ai",
                              "text": f"Criei o movimento \"{clipe['nome']}\" ({clipe['duracao']:g} s, {len(clipe['faixas'])} faixas). "
                                      f"Para repetir: /movimento {clipe['nome']}.{extra}"})
        if criou:
            self._enviar_movimentos()

    def _receber_propostas_ajuste(self, brutos):
        """v1.6.2 — a IA propôs consertos no PRÓPRIO código. O Cérebro só valida e guarda (nada roda, nada muda) e avisa
        no chat o número do ajuste (ou por que foi recusado). Quem testa e aplica é o usuário, com /ajuste."""
        if not brutos:
            return
        try:
            from brain import zenith_autoajuste as aj
            ger = aj.instancia()
        except Exception as e:
            print(f"[Zenith/Ajuste] módulo indisponível: {e}")
            return
        for bruto in list(brutos)[:3]:
            try:
                r = ger.propor(bruto)
            except Exception as e:
                r = {"ok": False, "mensagem": f"Não consegui registrar o ajuste que propus ({e})."}
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": r["mensagem"]})

    def _rodar_ajuste_testar(self, id_ajuste: int):
        """v1.6.2 — /ajuste testar N: único momento em que o código proposto roda (numa cópia temporária, a seu pedido)."""
        try:
            from brain import zenith_autoajuste as aj
            r = aj.instancia().testar(id_ajuste)
            texto = r["mensagem"]
        except Exception as e:
            texto = f"Não consegui testar o ajuste #{id_ajuste}: {e}"
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

    def _movimentos_da_resposta(self, texto_usuario, resposta, cmds, criacoes):
        """Quais movimentos tocar agora: os que ela pediu com <corpo>movimento:..</corpo>, os que o usuário PEDIU ('dá um pulo')
        e os que ela AFIRMOU ter feito. Assim o que ela diz que fez, acontece. Também cria os <criar_movimento>."""
        if not self.settings.get("movimentos_ativos", True):
            return []
        try:
            if criacoes:
                self._criar_movimentos_da_ia(criacoes)
            nomes = set(movimentos.biblioteca())
            gestos.MOVIMENTOS_CONHECIDOS.update(nomes)
            lista = [n for t, n in (cmds or []) if t == "movimento" and n in nomes]
            for n in movimentos.inferir_do_pedido(texto_usuario, nomes) + movimentos.inferir_do_que_ela_disse(resposta, nomes):
                if n not in lista:
                    lista.append(n)
            return lista[:movimentos.FILA_MAX]
        except Exception as e:
            print(f"[Zenith/Movimentos] {e}")
            return []

    def _aplicar_flags_v14(self):
        """v1.4 — liga/desliga o filtro de emoji e a captura sem a janela do Zenith, conforme as Configurações."""
        try:
            zenith_emoji.ATIVO = bool(self.settings.get("sem_emoji", True))
            zenith_captura.ATIVO = bool(self.settings.get("captura_sem_zenith", True))
            self.bridge.send({"action": "movement_config", "janela": bool(self.settings.get("movimentos_janela", True)),
                              "camera": bool(self.settings.get("movimentos_camera", True))})
        except Exception:
            pass

    def _iniciar_observacao(self, conteudo: str) -> str:
        try:
            o = observar.parse(conteudo, self.settings.get("observar_intervalo_s", 20), self.settings.get("observar_max_minutos", 15))
        except ValueError as e:
            return f"👁 Não consegui iniciar: {e}"
        return self.observador.iniciar(o["tipo"], o["intervalo"], o["minutos"], o["motivo"], self.settings.user_name)

    def _parar_observacao(self, motivo: str, avisar: bool = True):
        if self.observador is None:
            return
        if self.observador.parar(motivo) is False and avisar:
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": "👁 Não estou observando nada agora."})

    def _enviar_fundo_avatar(self):
        self.bridge.send({"action": "avatar_fundo", "modo": self.settings.get("avatar_fundo_modo", "auto"),
                          "cor": self.settings.get("avatar_fundo_cor", "#0b1020")})

    def _avisar_novo_computador(self):
        """v23 — a janela do avatar depende de transparência do Windows/driver; em alguns PCs vira um quadrado preto.
        Na primeira abertura em CADA computador, avisa como resolver (uma vez)."""
        try:
            import platform
            pc = platform.node() or "pc"
            if self.settings.get("avatar_fundo_pc", "") == pc:
                return
            self.settings.update({"avatar_fundo_pc": pc})
            if self.settings.get("avatar_fundo_modo", "auto") == "auto":
                self.bridge.send({"action": "chat_message", "sender": "ai", "text":
                    "🖼 Se o fundo do meu avatar apareceu PRETO (alguns PCs/drivers não suportam janela transparente), "
                    "digite /fundo_avatar solido — ou /fundo_avatar chroma (verde, bom pra OBS). "
                    "/fundo_avatar transparente volta ao normal."})
        except Exception as e:
            print(f"[Zenith] aviso de novo computador falhou: {e}")

    def _rodar_listar_modelos(self):
        try:
            from brain import zenith_gemini as gem
            ids = self.core.listar_modelos_gemini()
            atual = self.settings.get("gemini_modelo", "")
            sugerido = gem.melhor_modelo(ids)
            texto = ("🧠 Modelos Gemini que a SUA chave enxerga:\n" + gem.formatar_lista(ids, atual) +
                     (f"\n\nSugestão estável: {sugerido}" if sugerido else "") +
                     "\nTrocar: /modelo gemini <id>")
        except Exception as e:
            texto = f"🧠 Não consegui listar os modelos agora ({str(e)[:140]}). Confira a chave do Gemini em Configurações."
        self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

    # ---------------- v30: chaves em rodízio, rota e IA local ----------------
    def _rodar_atualizar(self, passo: str = "consultar"):
        """v1.5 (T9) — consulta, baixa com SHA-256 conferido e só abre o instalador com pedido explícito.
        Nunca é automático: só roda quando o usuário digita /atualizar."""
        from brain import zenith_atualizar as at

        def falar(texto: str):
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": texto})

        url = str(self.settings.get("atualizar_url", "") or "").strip() or os.environ.get("ZENITH_ATUALIZAR_URL", "").strip()   # v1.6.2: o Launcher informa
        if not url:
            falar("A atualização não está configurada: coloque o endereço do versions.json em "
                  "Configurações (atualizar_url). Nada foi baixado nem aberto.")
            return
        info, erro = at.consultar(url)
        if erro:
            falar("Não consegui consultar o servidor de atualização: " + erro)
            return
        plano = at.planejar(info, zenith_version.VERSAO)
        if not plano.get("ha_novidade"):
            falar(at.formatar(info, plano, zenith_version.VERSAO))
            return
        falar(at.formatar(info, plano, zenith_version.VERSAO))
        launcher = os.environ.get("ZENITH_LAUNCHER", "").strip()
        if launcher:                                   # v1.6.2 — instalado pelo Launcher: é ELE quem baixa, confere e troca
            if passo == "consultar":
                falar("Para atualizar: /atualizar instalar (abro o Launcher, você fecha o Zenith e ele faz o resto).")
                return
            ok, msg = at.abrir_launcher(launcher, os.getpid(), aprovado=True)
            falar(msg)
            return
        if passo == "consultar":
            return
        if passo == "instalar" and not getattr(self, "_instalador_baixado", ""):
            falar("Ainda não baixei nada. Use /atualizar baixar primeiro (eu confiro o SHA-256).")
            return
        if passo == "baixar":
            caminho, erro = at.baixar(plano)
            if erro:
                falar("Não baixei: " + erro)
                return
            self._instalador_baixado = caminho
            falar("Baixado e conferido (SHA-256 igual ao publicado): " + caminho
                  + chr(10) + "Nada foi aberto. Se quiser instalar: /atualizar instalar")
            return
        ok, msg = at.abrir_instalador(getattr(self, "_instalador_baixado", ""), aprovado=True)
        falar(msg)

    def _rodar_testar_chaves(self):
        """Testa cada chave cadastrada (chamada barata: listar modelos) e diz quais estão de castigo."""
        from brain import zenith_chaves as ch

        def enviar(t):
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": t})

        try:
            rot = ch.Rotador(self.settings)
        except Exception as e:
            enviar(f"🔑 Não consegui ler as chaves agora: {e}")
            return
        linhas = ["🔑 Testando as chaves (uma chamada barata em cada — não gasta resposta):"]
        algum = False
        for item in rot.resumo():
            prov = item["provedor"]
            if prov == "local" or prov.startswith("custom:") or prov == "custom":
                linhas.append(f"• {item['nome']}: teste individual não se aplica (use /chaves para ver o estado)")
                continue
            for chave in rot.chaves(prov):
                algum = True
                try:
                    ok, msg = self.core.test_api_key(prov, chave)
                except Exception as e:
                    ok, msg = False, str(e)[:120]
                linhas.append(f"{'✓' if ok else '✗'} {item['nome']} {ch.mascarar(chave)} — {msg}")
        if not algum:
            linhas.append("Nenhuma chave de nuvem cadastrada ainda. /chave add gemini <chave>")
        presas = [i for i in rot.resumo() if i["presas"]]
        if presas:
            linhas.append("\nEm espera (cota/chave): " + "; ".join(
                f"{i['nome']} ({len(i['presas'])})" for i in presas) + ". /chaves esquecer libera.")
        enviar("\n".join(linhas))

    # ================================================================ v1.0 — PÁGINA DE CHAVES (A8)
    # Contrato combinado com a tela do Godot (Configurações > Chaves). A chave SEMPRE vai mascarada
    # para o Corpo; o valor inteiro só entra (numa direção) quando o usuário digita uma chave nova.
    def _enviar_estado_chaves(self):
        from brain import zenith_chaves as ch
        try:
            estado = ch.estado_para_tela(self.settings)
        except Exception as e:
            self.bridge.send({"action": "chaves_resultado", "ok": False,
                              "msg": f"Não consegui ler as chaves agora: {e}"})
            return
        self.bridge.send(dict({"action": "chaves_estado"}, **estado))

    def _handle_chaves_listar(self, data):
        self._enviar_estado_chaves()

    def _handle_diagnostico_rodar(self, data):
        """v1.2 — roda o diagnóstico numa thread (tem teste de internet e de voz) e devolve a lista pra tela."""
        threading.Thread(target=self._diagnostico_para_tela, daemon=True).start()

    def _diagnostico_para_tela(self):
        from brain.zenith_settings import BASE_DIR, CREATION_DIR
        import datetime as _dt
        try:
            itens = diag.testar_tudo(self.settings, base_dir=BASE_DIR, rede=True)
            texto = diag.relatorio(self.settings, base_dir=BASE_DIR, resultados=itens)
            destino = ""
            try:
                destino = os.path.join(str(CREATION_DIR), "exports", f"zenith_relatorio_{_dt.datetime.now():%Y%m%d_%H%M}.txt")
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "w", encoding="utf-8") as f:
                    f.write(texto)
            except Exception:
                destino = ""
            resumo = {k: sum(1 for i in itens if i.get("status") == k) for k in ("ok", "aviso", "erro")}
            self.bridge.send({"action": "diagnostico_resultado", "itens": itens, "relatorio": texto,
                              "arquivo": destino, "resumo": resumo})
        except Exception as e:
            self.bridge.send({"action": "diagnostico_resultado", "relatorio": "", "arquivo": "",
                              "itens": [{"nome": "Diagnóstico", "status": "erro", "detalhe": f"o diagnóstico em si falhou: {e}"}],
                              "resumo": {"ok": 0, "aviso": 0, "erro": 1}})

    # ---------------- v1.11 (port celular): Desempenho / downgrade ----------------
    def _estado_desempenho(self, mensagem: str = "", ok: bool = True) -> dict:
        """Tudo que a tela de Desempenho precisa: o aparelho medido, o que o Zenith recomenda, o que está valendo."""
        from brain import zenith_downgrade as dg
        medida = zenith_plataforma.obter().medir()
        rec = dg.recomendar(medida)
        escolhido = dg.de_settings(self.settings.settings)
        recursos = escolhido or (rec["recursos"] if rec["ok"] else dg.perfil("completo"))
        return {"action": "desempenho_estado", "ok": ok, "mensagem": mensagem, "escolhido": escolhido is not None,
                "medida": medida, "recomendacao": rec, "recursos": recursos,
                "opcoes": {k: list(v) for k, v in dg.RECURSOS.items()}, "rotulos": dg.ROTULOS,
                "sugestao": dg.proximo_passo(recursos) or {}, "texto": dg.formatar(medida, rec)}

    def _handle_desempenho_pedir(self, data):
        try:
            self.bridge.send(self._estado_desempenho())
        except Exception as e:
            self.bridge.send({"action": "desempenho_estado", "ok": False, "mensagem": f"Não consegui medir o aparelho: {e}"})

    def _handle_desempenho_aplicar(self, data):
        """A pessoa escolheu o que rebaixar. Nada aqui acontece sozinho: só quando ela aplica."""
        from brain import zenith_downgrade as dg
        try:
            recursos = dg.validar(data.get("recursos") or {})
        except ValueError as e:
            self.bridge.send(self._estado_desempenho(str(e), ok=False))
            return
        self.settings.update(dg.mudancas_nas_configuracoes(recursos, self.settings.settings))
        try:
            if recursos["voz_saida"] == "desligada":
                self.interaction.parar_de_falar()
            if recursos["voz_entrada"] == "desligada":
                self.interaction.parar_de_escutar()
        except Exception as e:
            print(f"[Zenith/Desempenho] ao parar a voz: {e}")
        self._enviar_desempenho_config()
        self.bridge.send(self._estado_desempenho("Pronto: os ajustes foram aplicados."))

    def _enviar_desempenho_config(self):
        """Manda ao Corpo o que ele mesmo aplica (FPS, qualidade gráfica, avatar). Sem escolha feita, não manda nada."""
        from brain import zenith_downgrade as dg
        recursos = dg.de_settings(self.settings.settings)
        if recursos:
            self.bridge.send({"action": "desempenho_config", "recursos": recursos})

    def _handle_sobre(self, data):
        """v1.0 — a aba "Sobre" das Configurações pergunta quem fez o Zenith.
        O texto vem de config/creditos.txt (editável sem recompilar)."""
        from brain import zenith_creditos as creditos
        try:
            self.bridge.send(dict({"action": "sobre"}, **creditos.dados()))
        except Exception as e:
            self.bridge.send({"action": "sobre", "criador": creditos.CRIADOR, "papel": creditos.PAPEL,
                              "texto": creditos.TEXTO_PADRAO, "erro": str(e)})

    def _handle_chave_add(self, data):
        """Adiciona uma chave vinda da TELA (nunca do chat). Devolve resultado + estado novo."""
        from brain import zenith_chaves as ch
        r = ch.adicionar_chave(self.settings, data.get("provedor", ""), data.get("chave", ""))
        self.bridge.send({"action": "chaves_resultado", "ok": bool(r.get("ok")), "msg": r.get("mensagem", "")})
        if r.get("ok"):
            self._recarregar_chaves()
        self._enviar_estado_chaves()

    def _handle_chave_remover(self, data):
        from brain import zenith_chaves as ch
        try:
            indice = int(data.get("idx", 0))
        except (TypeError, ValueError):
            indice = -1
        r = ch.remover_chave(self.settings, data.get("provedor", ""), indice)
        self.bridge.send({"action": "chaves_resultado", "ok": bool(r.get("ok")), "msg": r.get("mensagem", "")})
        if r.get("ok"):
            self._recarregar_chaves()
        self._enviar_estado_chaves()

    def _recarregar_chaves(self):
        try:
            self.core.reload_api_keys(self.settings)
        except Exception as e:
            print(f"[Zenith/Chaves] recarregar depois de mexer nas chaves falhou: {e}")

    def _handle_chaves_testar(self, data):
        """Testa cada chave de verdade e manda UM `chaves_teste` por chave, conforme termina."""
        threading.Thread(target=self._testar_chaves_para_tela, daemon=True).start()

    def _testar_chaves_para_tela(self):
        from brain import zenith_chaves as ch
        try:
            rot = ch.Rotador(self.settings)
        except Exception as e:
            self.bridge.send({"action": "chaves_resultado", "ok": False, "msg": f"Não consegui ler as chaves: {e}"})
            return
        falhas_429 = {}
        for item in rot.resumo():
            prov = item["provedor"]
            if prov == "local" or prov.startswith("custom:") or prov == "custom":
                continue
            for idx, chave in enumerate(rot.chaves(prov)):
                try:
                    ok, msg = self.core.test_api_key(prov, chave)
                    # v1.6.1: "chave válida" só diz que a chave existe (o teste lista modelos). Para OpenAI/OpenRouter/Groq
                    # faz também UMA pergunta mínima ao chat, com o modelo que o Zenith usa — é aí que as falhas apareciam.
                    # v1.10: o GEMINI entra na mesma regra. Era o único que só era "listado" e por isso a tela dizia
                    # "Chave do Gemini válida" enquanto todos os modelos respondiam 503/404 e a conversa não acontecia.
                    if (ok and prov in ("gemini", "openai", "claude", "groq") and not msg.startswith("Chave parece válida")
                            and self.settings.get("teste_real_chaves", True) is not False):
                        ok, msg = self.core.testar_chat(prov, chave)
                except Exception as e:
                    ok, msg = False, str(e)[:120]
                if "429" in str(msg) or "quota" in str(msg).lower() or "limite" in str(msg).lower():
                    falhas_429[prov] = falhas_429.get(prov, 0) + 1
                self.bridge.send({"action": "chaves_teste", "provedor": prov, "idx": idx,
                                  "mascara": ch.mascarar(chave), "ok": bool(ok), "msg": str(msg)})
            if falhas_429.get(prov, 0) >= 2:
                # A cota do Gemini é POR PROJETO do Google: duas chaves do mesmo projeto não somam.
                self.bridge.send({"action": "chaves_teste", "provedor": prov, "idx": -1, "ok": False,
                                  "msg": "Duas chaves deste provedor falharam por cota no mesmo minuto — "
                                         "provavelmente são do MESMO projeto (a cota é por projeto). "
                                         "Use outro projeto ou outro provedor."})
        self.bridge.send({"action": "chaves_teste_fim"})
        self._enviar_estado_chaves()

    def _handle_ia_local_tela(self, data):
        """Liga/desliga/baixa o modelo local a partir da página de Configurações."""
        from brain import zenith_ia_local as L
        acao = str(data.get("acao", "")).lower()
        if acao == "baixar":
            threading.Thread(target=self._rodar_baixar_local,
                             args=(str(data.get("modelo", "")),), daemon=True).start()
            self.bridge.send({"action": "chaves_resultado", "ok": True, "msg": "Baixando o modelo local…"})
            return
        if acao in ("ligar", "desligar"):
            r = L.configurar(self.settings, ligar=(acao == "ligar"))
            self.bridge.send({"action": "chaves_resultado", "ok": True, "msg": r.get("mensagem", "Feito.")})
            self._recarregar_chaves()
            self._enviar_estado_chaves()
            return
        self.bridge.send({"action": "chaves_resultado", "ok": False, "msg": "Ação de IA local desconhecida."})

    def _rodar_baixar_local(self, modelo: str = ""):
        """Baixa o modelo local com aviso de progresso — só quando o usuário pediu /local baixar."""
        from brain import zenith_ia_local as L

        def enviar(t):
            self.bridge.send({"action": "chat_message", "sender": "ai", "text": t})

        det = L.detectar(self.settings, timeout=2.0)
        if not det.get("rodando"):
            enviar(L.msg_sem_servidor())
            return
        modelo = (modelo or L.modelo_escolhido(self.settings, det)).strip()
        enviar(f"🖥 Baixando o modelo local “{modelo}”… (pode levar alguns minutos; dá pra continuar conversando)")
        enviado = [-25]

        def prog(pct, texto):
            if pct is not None and pct - enviado[0] >= 25:
                enviado[0] = pct
                enviar(f"🖥 {pct}% {texto}".strip())

        r = L.puxar_modelo(modelo, det.get("url") or "http://127.0.0.1:11434", progresso=prog)
        enviar(r["mensagem"])
        if r.get("ok"):
            L.configurar(self.settings, modelo=modelo, ligar=True)
            try:
                self.core.reload_api_keys(self.settings)
            except Exception as e:
                print(f"[Zenith/IA local] recarregar depois do download falhou: {e}")

    def _handle_test_api_key(self, data):
        provider = data.get("provider", "")
        key = data.get("key", "")
        custom_url = data.get("custom_url", "")
        threading.Thread(target=self._run_key_test, args=(provider, key, custom_url), daemon=True).start()

    def _run_key_test(self, provider, key, custom_url):
        valid, message = self.core.test_api_key(provider, key, custom_url)
        self.bridge.send({"action": "api_key_test_result", "provider": provider,
                           "valid": valid, "message": message})

    # ---------------- Gerenciador Dinâmico de Endpoints de IA (multi-IA) ----------------
    def _handle_add_ai_endpoint(self, data):
        name = (data.get("name") or "").strip()
        api_url = (data.get("api_url") or "").strip()
        api_key = (data.get("api_key") or "").strip()
        model_name = (data.get("model_name") or "").strip()

        if not name or not api_url or not model_name:
            self.bridge.send({"action": "chat_message", "sender": "ai",
                               "text": "⚠️ Pra adicionar uma IA preciso pelo menos do Nome, "
                                       "da URL do Endpoint e do Nome do Modelo."})
            return

        endpoints = list(self.settings.get("ai_endpoints", []) or [])
        new_id = uuid.uuid4().hex[:10]
        endpoints.append({
            "id": new_id, "name": name, "api_url": api_url,
            "api_key": api_key, "model_name": model_name,
        })
        self.settings.update({"ai_endpoints": endpoints})
        self.core.reload_api_keys(self.settings)
        self.bridge.send({"action": "settings_data", "settings": self._settings_for_ui()})
        self.bridge.send({"action": "chat_message", "sender": "ai",
                           "text": f"✅ '{name}' adicionada — já dá pra escolher ela em "
                                   f"Provedor ativo."})

    def _handle_remove_ai_endpoint(self, data):
        ep_id = data.get("id", "")
        endpoints = [e for e in (self.settings.get("ai_endpoints", []) or []) if e.get("id") != ep_id]
        self.settings.update({"ai_endpoints": endpoints})
        # Se a IA removida era a que estava ativa, volta pro Gemini (o
        # padrão) em vez de deixar active_ai apontando pra um provider
        # que não existe mais.
        if self.settings.get("active_ai", "") == f"custom:{ep_id}":
            self.settings.update({"active_ai": "gemini"})
        self.core.reload_api_keys(self.settings)
        self.bridge.send({"action": "settings_data", "settings": self._settings_for_ui()})

    # ---------------- v20: "Resetar tudo" (agendado para a próxima abertura) ----------------
    def _handle_schedule_reset(self, data):
        from brain.zenith_settings import BASE_DIR as _base
        ok, msg = reset_dados.agendar(_base, str(data.get("confirm") or ""))
        self.bridge.send({"action": "reset_scheduled", "ok": ok, "message": msg})

    def _handle_cancel_reset(self, data):
        from brain.zenith_settings import BASE_DIR as _base
        reset_dados.cancelar(_base)
        self.bridge.send({"action": "reset_scheduled", "ok": False, "message": "Reset cancelado."})

    # ---------------- v20: fundo do chat com qualquer imagem/vídeo ----------------
    def _handle_prepare_wallpaper(self, data):
        """O Corpo pede para preparar o arquivo de fundo. Roda numa thread (vídeo leva alguns
        segundos na 1ª vez; depois vem do cache) e responde com `wallpaper_ready`."""
        caminho = str(data.get("path") or "").strip()

        def _trabalho():
            try:
                from brain.zenith_settings import TEMP_DIR
                res = fundo_chat.preparar(caminho, TEMP_DIR)
            except Exception as e:  # pragma: no cover — defensivo
                res = {"ok": False, "msg": f"Falha preparando o fundo: {e}"}
            res = dict(res)
            res["action"] = "wallpaper_ready"
            res["origem"] = caminho
            self.bridge.send(res)

        threading.Thread(target=_trabalho, daemon=True, name="zenith-fundo").start()

    # ---------------- v20: clique que atravessa a janela do avatar (Windows) ----------------
    def _handle_set_click_through(self, data):
        """O Corpo manda o PID dele e se a janela do avatar deve deixar o clique atravessar.
        Idempotente (o Corpo repete a cada 3 s): só avisa no log quando o resultado muda."""
        ativo = bool(data.get("active", True))
        ok, msg = janela_avatar.definir_clique_atravessa(data.get("pid"), ativo)
        chave = (ativo, ok)
        if getattr(self, "_ultimo_click_through", None) != chave:
            self._ultimo_click_through = chave
            print(f"[Zenith] Clique-atravessa ({'ligado' if ativo else 'desligado'}): {'ok' if ok else 'não aplicado'} — {msg}")

    # ---------------- v19: painel "IAs & Chaves" de uma IA por vez ----------------
    def _ai_reply(self, ok: bool, msg: str):
        # Reaproveita o canal do "Testar chave" (api_key_test_result) com um provider fixo
        # ("ai_panel"): o Corpo já sabe mostrar isso no rótulo de status do painel.
        self.bridge.send({"action": "api_key_test_result", "provider": "ai_panel",
                          "valid": bool(ok), "message": msg})

    def _handle_save_ai_entry(self, data):
        """Grava UMA IA (ou serviço) do painel. id '__novo__' = cadastrar IA personalizada."""
        eid = str(data.get("id") or "").strip()
        campos = {"nome": data.get("nome"), "url": data.get("url"),
                  "chave": data.get("chave"), "modelo": data.get("modelo")}
        atual = self.settings.settings
        antes = [e["id"] for e in provedores.montar_entradas(atual) if e["eh_llm"] and e["configurada"]]
        try:
            if not eid or eid == provedores.NOVO:
                eid, mud = provedores.nova_endpoint(atual, campos)
                msg = "IA adicionada."
                self._ai_selecionar = eid
            else:
                mud = provedores.salvar_entrada(atual, eid, campos)
                msg = "Salvo."
        except provedores.ErroProvedor as e:
            self._ai_reply(False, str(e))
            return
        # Nenhuma IA estava pronta (caso típico da cópia de pendrive, onde o padrão "gemini"
        # nem existe) => a primeira que ficar pronta já vira a ativa, sem a pessoa precisar saber.
        futuro = dict(atual)
        futuro.update(mud)
        pronta = {e["id"]: e for e in provedores.montar_entradas(futuro)}
        if not antes and eid in pronta and pronta[eid]["eh_llm"] and pronta[eid]["configurada"]:
            mud["active_ai"] = eid
            msg += " Ela já é a IA ativa."
        self.settings.update(mud)
        self.core.reload_api_keys(self.settings)
        self.bridge.send({"action": "settings_data", "settings": self._settings_for_ui()})
        self._ai_reply(True, msg)

    def _handle_remove_ai_entry(self, data):
        eid = str(data.get("id") or "").strip()
        try:
            mud = provedores.remover_entrada(self.settings.settings, eid)
        except provedores.ErroProvedor as e:
            self._ai_reply(False, str(e))
            return
        self.settings.update(mud)
        self.core.reload_api_keys(self.settings)
        self.bridge.send({"action": "settings_data", "settings": self._settings_for_ui()})
        self._ai_reply(True, "Removida.")

    # ---------------- desbloqueio (Stranger Danger) ----------------
    def _handle_unlock(self, data):
        senha = data.get("password", "")
        ok = self.core.unlock(senha)
        self.bridge.send({"action": "unlock_result", "success": ok})


def run():
    print("=" * 60)
    print(f"  {SYSTEM_NAME} — Cérebro (modo headless, sem janela Python)")
    print(f"  Criado por {CREATOR}")
    print("  Toda a interface agora vive na janela do Corpo (Godot).")
    print("=" * 60)
    brain = ZenithHeadlessBrain()
    threading.Event().wait()  # mantém o processo vivo (a Ponte roda em threads próprias)


if __name__ == "__main__":
    run()
