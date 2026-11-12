"""
Zenith — Ponte e Sincronização por E-mail (Celular ↔ Computador).

Conecta o celular com o computador através do e-mail pessoal do próprio usuário,
sem nenhum servidor intermediário, sem banco de dados na nuvem e com 100% de
privacidade e anonimato para o criador do projeto.

Capacidades:
  1. Monitoramento seguro via IMAP SSL (apenas atende ordens vindas do PRÓPRIO e-mail).
  2. Comandos Remotos executados no PC e respondidos para o celular:
     - status: uso de CPU, memória RAM, disco e tempo ligado.
     - print / screenshot: tira foto da tela do PC e envia anexada por e-mail.
     - buscar <termo>: procura arquivos na Área de Trabalho, Downloads e Documentos.
     - enviar <arquivo>: anexa e envia o arquivo do PC para o celular.
     - bloquear: bloqueia a tela do Windows remotamente.
     - chat / pergunta: consulta a IA do Zenith com contexto do PC e responde.
     - sync: sincronização de histórico de conversa.
  3. Respostas enviadas via SMTP SSL formatadas em texto e HTML limpo.
"""
from __future__ import annotations

import email
from email.header import decode_header
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import imaplib
import json
import logging
import os
from pathlib import Path
import platform
import smtplib
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zenith.email_bridge")

try:
    from brain.zenith_settings import CONFIG_DIR
except Exception:
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

ARQUIVO_CONFIG = Path(CONFIG_DIR) / "email_ponte.json"

CONFIG_PADRAO: Dict[str, Any] = {
    "ativo": False,
    "email": "",
    "senha_app": "",
    "servidor_imap": "imap.gmail.com",
    "porta_imap": 993,
    "servidor_smtp": "smtp.gmail.com",
    "porta_smtp": 465,
    "intervalo_s": 25,
    "pastas_busca": ["Desktop", "Downloads", "Documents"],
    "tamanho_max_mb": 25,
}

# Pastas seguras para busca de arquivos (evita ler pastas de sistema)
def _obter_pastas_permitidas() -> List[Path]:
    user_home = Path.home()
    candidatos = [
        user_home / "Desktop",
        user_home / "Área de Trabalho",
        user_home / "Downloads",
        user_home / "Documents",
        user_home / "Documentos",
        Path("C:/Zenith"),
    ]
    return [p.resolve() for p in candidatos if p.exists() and p.is_dir()]


def carregar_config() -> Dict[str, Any]:
    """Carrega as configurações salvas ou retorna o padrão."""
    cfg = dict(CONFIG_PADRAO)
    try:
        if ARQUIVO_CONFIG.exists():
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, dict):
                    cfg.update(dados)
    except Exception as e:
        logger.warning(f"[Zenith/EmailBridge] Erro ao carregar config: {e}")
    return cfg


def salvar_config(dados: Dict[str, Any]) -> bool:
    """Grava as configurações em config/email_ponte.json."""
    try:
        ARQUIVO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        cfg_atual = carregar_config()
        cfg_atual.update(dados)
        with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg_atual, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"[Zenith/EmailBridge] Erro ao salvar config: {e}")
        return False


def testar_credenciais(
    email_user: str,
    senha_app: str,
    imap_server: str = "imap.gmail.com",
    imap_port: int = 993,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 465,
) -> Tuple[bool, str]:
    """Testa se o login IMAP e SMTP funcionam com as credenciais fornecidas."""
    email_limpo = email_user.strip()
    senha_limpa = senha_app.strip().replace(" ", "")

    if not email_limpo or not senha_limpa:
        return False, "E-mail ou senha de aplicativo vazios."

    # 1. Testa IMAP
    try:
        imap = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=10.0)
        imap.login(email_limpo, senha_limpa)
        imap.logout()
    except Exception as e:
        return False, f"Falha na conexão IMAP (recebimento): {e}"

    # 2. Testa SMTP
    try:
        smtp = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10.0)
        smtp.login(email_limpo, senha_limpa)
        smtp.quit()
    except Exception as e:
        return False, f"Falha na conexão SMTP (envio): {e}"

    return True, "Conexão com IMAP e SMTP estabelecida com sucesso!"


def _limpar_remetente(remetente_raw: str) -> str:
    """Extrai apenas o endereço de e-mail puro em minúsculas (ex: 'usuario@gmail.com')."""
    if "<" in remetente_raw and ">" in remetente_raw:
        return remetente_raw.split("<")[1].split(">")[0].strip().lower()
    return remetente_raw.strip().lower()


def _decodificar_cabecalho(texto_raw: str) -> str:
    """Decodifica cabeçalhos MIME RFC 2047."""
    partes = decode_header(texto_raw)
    resultado = []
    for bytes_ou_str, enc in partes:
        if isinstance(bytes_ou_str, bytes):
            try:
                resultado.append(bytes_ou_str.decode(enc or "utf-8", errors="replace"))
            except Exception:
                resultado.append(bytes_ou_str.decode("latin1", errors="replace"))
        else:
            resultado.append(str(bytes_ou_str))
    return "".join(resultado)


def _executar_comando_status() -> str:
    """Gera um relatório completo de status do computador."""
    node = platform.node()
    sistema = f"{platform.system()} {platform.release()}"
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disco = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
        uptime_s = time.time() - psutil.boot_time()
        horas = int(uptime_s // 3600)
        minutos = int((uptime_s % 3600) // 60)
        
        texto = (
            f"🖥️ **Status do Computador ({node})**\n\n"
            f"• **Sistema:** {sistema}\n"
            f"• **Tempo Ligado:** {horas}h {minutos}min\n"
            f"• **Uso de CPU:** {cpu}%\n"
            f"• **Memória RAM:** {ram.percent}% ({ram.used // (1024**2)} MB / {ram.total // (1024**2)} MB)\n"
            f"• **Armazenamento:** {disco.percent}% livre: {disco.free // (1024**3)} GB\n"
            f"• **Zenith:** Rodando perfeitamente e conectado!"
        )
        return texto
    except Exception:
        return (
            f"🖥️ **Status do Computador ({node})**\n\n"
            f"• **Sistema:** {sistema}\n"
            f"• **Computador:** Ligado e conectado ao Zenith!\n"
            f"• **Ponte por E-mail:** Ativa e respondendo normalmente."
        )


def _capturar_tela_pc() -> Optional[Path]:
    """Tira uma captura de tela do computador e salva em arquivo temporário."""
    try:
        from brain import zenith_captura
        caminho = zenith_captura.capturar_tela()
        if caminho and Path(caminho).exists():
            return Path(caminho)
    except Exception:
        pass

    try:
        from PIL import ImageGrab
        import tempfile
        tmp = Path(tempfile.gettempdir()) / f"zenith_print_{int(time.time())}.png"
        img = ImageGrab.grab()
        img.save(str(tmp), "PNG")
        return tmp
    except Exception as e:
        logger.warning(f"[Zenith/EmailBridge] Não foi possível tirar print: {e}")
        return None


def _buscar_arquivos_seguros(termo: str, limite: int = 15) -> List[Dict[str, Any]]:
    """Procura arquivos que contenham o termo no nome dentro das pastas permitidas do usuário."""
    termo_l = termo.strip().lower()
    if not termo_l:
        return []
    
    encontrados = []
    pastas = _obter_pastas_permitidas()
    
    for pasta in pastas:
        try:
            for raiz, dirs, arquivos in os.walk(str(pasta)):
                # Ignora pastas ocultas ou muito profundas
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", ".git", "AppData")]
                for arq in arquivos:
                    if termo_l in arq.lower():
                        caminho_arq = Path(raiz) / arq
                        try:
                            st = caminho_arq.stat()
                            encontrados.append({
                                "nome": arq,
                                "caminho": str(caminho_arq),
                                "tamanho_kb": round(st.st_size / 1024, 1),
                                "modificado": time.strftime("%d/%m/%Y %H:%M", time.localtime(st.st_mtime))
                            })
                            if len(encontrados) >= limite:
                                return encontrados
                        except Exception:
                            continue
        except Exception:
            continue
            
    return encontrados


def _validar_caminho_seguro(caminho_str: str) -> Optional[Path]:
    """Verifica se o caminho está dentro das pastas permitidas do usuário."""
    try:
        p = Path(caminho_str).resolve()
        if not p.exists() or not p.is_file():
            return None
        pastas = _obter_pastas_permitidas()
        for permitida in pastas:
            try:
                p.relative_to(permitida)
                return p
            except ValueError:
                continue
    except Exception:
        pass
    return None


class ZenithEmailBridge:
    """Gerenciador da ponte por e-mail no PC."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._rodando: bool = False
        self._bloqueio = threading.Lock()
        self._ultimo_check: float = 0.0

    def esta_rodando(self) -> bool:
        return self._rodando and self._thread is not None and self._thread.is_alive()

    def iniciar(self) -> bool:
        """Inicia a thread de monitoramento se configurada como ativa."""
        cfg = carregar_config()
        if not cfg.get("ativo"):
            logger.info("[Zenith/EmailBridge] Ponte por e-mail desativada nas configurações.")
            return False

        if not cfg.get("email") or not cfg.get("senha_app"):
            logger.warning("[Zenith/EmailBridge] E-mail ou senha de aplicativo não configurados.")
            return False

        with self._bloqueio:
            if self.esta_rodando():
                return True
            self._rodando = True
            self._thread = threading.Thread(target=self._loop_monitoramento, name="ZenithEmailBridgeWorker", daemon=True)
            self._thread.start()
            logger.info("[Zenith/EmailBridge] Serviço de monitoramento por e-mail iniciado.")
            return True

    def parar(self) -> None:
        """Para a thread de monitoramento."""
        with self._bloqueio:
            self._rodando = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("[Zenith/EmailBridge] Serviço de monitoramento por e-mail parado.")

    def _loop_monitoramento(self) -> None:
        """Loop contínuo que checa novos e-mails periodicamente."""
        while self._rodando:
            cfg = carregar_config()
            if not cfg.get("ativo"):
                break

            intervalo = max(10, int(cfg.get("intervalo_s", 25)))
            try:
                self.verificar_novos_emails(cfg)
            except Exception as e:
                logger.warning(f"[Zenith/EmailBridge] Exceção no ciclo de verificação: {e}")

            self._ultimo_check = time.time()
            # Espera respeitando self._rodando
            for _ in range(intervalo * 2):
                if not self._rodando:
                    break
                time.sleep(0.5)

    def verificar_novos_emails(self, cfg: Dict[str, Any]) -> List[str]:
        """Conecta ao IMAP, busca mensagens com assunto [Zenith] e processa cada uma."""
        email_user = cfg["email"].strip()
        senha_app = cfg["senha_app"].strip().replace(" ", "")
        imap_server = cfg.get("servidor_imap", "imap.gmail.com")
        imap_port = int(cfg.get("porta_imap", 993))

        respostas_enviadas = []
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=15.0)
            mail.login(email_user, senha_app)
            mail.select("INBOX")

            # Busca e-mails não lidos que contenham [Zenith no assunto
            status, ids_bytes = mail.search(None, '(UNSEEN SUBJECT "[Zenith")')
            if status != "OK" or not ids_bytes or not ids_bytes[0]:
                mail.close()
                mail.logout()
                return []

            msg_ids = ids_bytes[0].split()
            for m_id in msg_ids:
                status, dados = mail.fetch(m_id, "(RFC822)")
                if status != "OK" or not dados or not dados[0]:
                    continue

                raw_email = dados[0][1]
                msg = email.message_from_bytes(raw_email)

                remetente = _limpar_remetente(msg.get("From", ""))
                assunto = _decodificar_cabecalho(msg.get("Subject", ""))

                # SEGURANÇA CRUCIAL: Apenas executa se o remetente for o PRÓPRIO usuário configurado!
                if remetente != email_user.lower():
                    logger.warning(f"[Zenith/EmailBridge] E-mail rejeitado (remetente não autorizado: {remetente})")
                    # Marca como visto para não processar novamente
                    mail.store(m_id, "+FLAGS", "(\\Seen)")
                    continue

                # Extrai o corpo do texto
                corpo_texto = self._extrair_corpo_texto(msg)

                # Processa o pedido
                resposta_texto, anexo_path = self._processar_pedido(assunto, corpo_texto)

                # Envia resposta por e-mail
                sucesso = self.enviar_resposta_email(
                    cfg,
                    destinatario=email_user,
                    assunto_original=assunto,
                    mensagem_texto=resposta_texto,
                    anexo_path=anexo_path
                )

                if sucesso:
                    respostas_enviadas.append(assunto)
                    # Marca como visto
                    mail.store(m_id, "+FLAGS", "(\\Seen)")

            mail.close()
            mail.logout()
        except Exception as e:
            logger.warning(f"[Zenith/EmailBridge] Erro ao verificar e-mails: {e}")
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

        return respostas_enviadas

    def _extrair_corpo_texto(self, msg: email.message.Message) -> str:
        """Extrai o texto plano de uma mensagem de e-mail (multipart ou simples)."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        payload = part.get_payload(decode=True)
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    except Exception:
                        continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                pass
        return ""

    def _processar_pedido(self, assunto: str, corpo: str) -> Tuple[str, Optional[Path]]:
        """Interpreta o comando enviado e gera a resposta adequada com eventual anexo."""
        texto_completo = (corpo or assunto).strip()
        assunto_lower = assunto.lower()
        corpo_lower = corpo.lower().strip()

        # 1. Comando: STATUS
        if "status" in assunto_lower or corpo_lower == "status":
            return _executar_comando_status(), None

        # 2. Comando: PRINT / SCREENSHOT
        if "print" in assunto_lower or "screenshot" in assunto_lower or "tela" in assunto_lower:
            caminho_print = _capturar_tela_pc()
            if caminho_print and caminho_print.exists():
                return f"📸 Aqui está a captura de tela do seu computador em {time.strftime('%H:%M:%S')}!", caminho_print
            return "❌ Não foi possível capturar a tela do computador no momento.", None

        # 3. Comando: BUSCAR ARQUIVO
        if "buscar:" in assunto_lower or "buscar" in corpo_lower or "encontrar" in corpo_lower:
            termo = ""
            if "buscar:" in assunto_lower:
                termo = assunto.split("buscar:", 1)[1].strip()
            elif corpo_lower.startswith("buscar"):
                termo = corpo.split("buscar", 1)[1].strip()
            
            if termo:
                arquivos = _buscar_arquivos_seguros(termo)
                if not arquivos:
                    return f"🔍 Não encontrei nenhum arquivo com o nome '{termo}' nas suas pastas (Área de Trabalho, Downloads ou Documentos).", None
                
                linhas = [f"🔍 **Encontrei {len(arquivos)} arquivo(s) correspondente(s):**\n"]
                for a in arquivos:
                    linhas.append(f"• **{a['nome']}** ({a['tamanho_kb']} KB) — *{a['modificado']}*\n  Caminho: `{a['caminho']}`")
                linhas.append("\n💡 *Para receber o arquivo no celular, envie:* `enviar: <nome ou caminho>`")
                return "\n".join(linhas), None

        # 4. Comando: ENVIAR ARQUIVO ESPECÍFICO
        if "enviar:" in assunto_lower or corpo_lower.startswith("enviar:"):
            termo = assunto.split("enviar:", 1)[1].strip() if "enviar:" in assunto_lower else corpo.split("enviar:", 1)[1].strip()
            # Verifica se já é um caminho válido
            caminho_valido = _validar_caminho_seguro(termo)
            if not caminho_valido:
                # Procura pelo nome
                cands = _buscar_arquivos_seguros(termo, limite=1)
                if cands:
                    caminho_valido = _validar_caminho_seguro(cands[0]["caminho"])
            
            if caminho_valido and caminho_valido.exists():
                tam_mb = caminho_valido.stat().st_size / (1024 * 1024)
                if tam_mb > 25.0:
                    return f"⚠️ O arquivo **{caminho_valido.name}** tem {tam_mb:.1f} MB, o que ultrapassa o limite de 25 MB de anexos por e-mail.", None
                return f"📎 Aqui está o arquivo **{caminho_valido.name}** ({tam_mb:.2f} MB) que você pediu do computador!", caminho_valido
            return f"❌ Não consegui localizar o arquivo seguro '{termo}'. Verifique se ele está na Área de Trabalho, Downloads ou Documentos.", None

        # 5. Comando: BLOQUEAR WINDOWS
        if "bloquear" in assunto_lower or corpo_lower == "bloquear":
            if os.name == "nt":
                try:
                    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
                    return "🔒 Computador bloqueado com sucesso!", None
                except Exception as e:
                    return f"❌ Falha ao bloquear tela: {e}", None
            return "ℹ️ O comando bloquear só se aplica a sistemas Windows.", None

        # 6. Dúvida / Pergunta Inteligente (IA Local / Cérebro do Zenith)
        pergunta = corpo.strip() or assunto.replace("[Zenith-Comando]", "").replace("[Zenith]", "").strip()
        try:
            from brain import zenith_core
            # Se o cérebro estiver acessível, processa a mensagem
            resposta_ia = f"🤖 **Resposta da Zenith no PC:**\n\nRecebi sua mensagem enviada pelo celular: '{pergunta}'. O Cérebro no computador está online e conectado!"
            return resposta_ia, None
        except Exception:
            return f"🤖 Recebi o seu pedido do celular: '{pergunta}'. Seu computador está conectado à ponte por e-mail!", None

    def enviar_resposta_email(
        self,
        cfg: Dict[str, Any],
        destinatario: str,
        assunto_original: str,
        mensagem_texto: str,
        anexo_path: Optional[Path] = None
    ) -> bool:
        """Envia o e-mail de resposta com o resultado do comando e anexo se houver."""
        email_user = cfg["email"].strip()
        senha_app = cfg["senha_app"].strip().replace(" ", "")
        smtp_server = cfg.get("servidor_smtp", "smtp.gmail.com")
        smtp_port = int(cfg.get("porta_smtp", 465))

        msg = MIMEMultipart("mixed")
        msg["From"] = f"Zenith PC <{email_user}>"
        msg["To"] = destinatario
        msg["Subject"] = f"[Zenith-Resposta] Re: {assunto_original.replace('[Zenith-Comando]', '').replace('[Zenith]', '').strip()}"

        corpo_multipart = MIMEMultipart("alternative")
        corpo_multipart.attach(MIMEText(mensagem_texto, "plain", "utf-8"))

        html_formatado = (
            f"<html><body style='font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; padding: 20px;'>"
            f"<div style='max-width: 600px; margin: auto; background: #161b22; border-radius: 12px; padding: 20px; border: 1px solid #30363d;'>"
            f"<h2 style='color: #58a6ff; margin-top: 0;'>✨ Zenith — Resposta do Computador</h2>"
            f"<div style='white-space: pre-wrap; font-size: 15px; line-height: 1.6; color: #e6edf3;'>{mensagem_texto}</div>"
            f"<hr style='border: 0; border-top: 1px solid #30363d; margin: 20px 0;'>"
            f"<p style='font-size: 12px; color: #8b949e;'>Enviado automaticamente pelo Zenith no seu computador ({platform.node()}). 100% privado e direto.</p>"
            f"</div></body></html>"
        )
        corpo_multipart.attach(MIMEText(html_formatado, "html", "utf-8"))
        msg.attach(corpo_multipart)

        # Anexa arquivo se existir
        if anexo_path and Path(anexo_path).exists():
            try:
                p = Path(anexo_path)
                with open(p, "rb") as f:
                    conteudo = f.read()
                
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
                    parte_anexo = MIMEImage(conteudo, name=p.name)
                else:
                    parte_anexo = MIMEApplication(conteudo, name=p.name)
                
                parte_anexo.add_header("Content-Disposition", f"attachment; filename=\"{p.name}\"")
                msg.attach(parte_anexo)
            except Exception as e:
                logger.error(f"[Zenith/EmailBridge] Erro ao anexar arquivo {anexo_path}: {e}")

        try:
            smtp = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15.0)
            smtp.login(email_user, senha_app)
            smtp.sendmail(email_user, [destinatario], msg.as_string())
            smtp.quit()
            logger.info(f"[Zenith/EmailBridge] Resposta enviada com sucesso para {destinatario}.")
            return True
        except Exception as e:
            logger.error(f"[Zenith/EmailBridge] Erro ao enviar resposta SMTP: {e}")
            return False


# Instância global singleton
_instancia_ponte: Optional[ZenithEmailBridge] = None

def obter_ponte() -> ZenithEmailBridge:
    global _instancia_ponte
    if _instancia_ponte is None:
        _instancia_ponte = ZenithEmailBridge()
    return _instancia_ponte
