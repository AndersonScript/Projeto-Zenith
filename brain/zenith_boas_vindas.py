"""
Zenith — Aviso de primeiro uso (roadmap 4.4.1: "Aviso explícito no primeiro uso").

Mostrado UMA vez, no chat, quando o Corpo conecta pela primeira vez. Diz em poucas
linhas o que a Zenith PODE fazer, o que ela NUNCA faz, pra onde vão as mensagens e como
parar tudo. Quem usa o Zenith sem ter lido o documento conceitual precisa saber disso
antes de aprovar a primeira ação (Pilar 1 só vale se a pessoa entende o que aprova).
"""

TEXTO = (
    "**👋 Oi! Antes de começar, o essencial:**\n\n"
    "- **Eu NUNCA executo nada no seu computador sem você aprovar** (Pilar 1). Toda ação aparece numa janela mostrando "
    "o que vai rodar — você aprova ou nega.\n"
    "- **Tem coisas que eu não faço nem com aprovação:** apagar disco, desligar o PC, mexer no antivírus ou no firewall.\n"
    "- **O que você escreve vai pra IA que escolheu** (na nuvem, a menos que seja um modelo local) — não cole senhas. "
    "Histórico, memória e notas ficam só neste computador.\n"
    "- **Parar tudo:** /pausar (e /retomar). /ajuda lista os comandos e /diagnostico confere se está tudo certo.\n\n"
    "*(Esta mensagem aparece só uma vez.)*"
)


def deve_mostrar(settings) -> bool:
    try:
        return not bool(settings.get("aviso_inicial_visto", False))
    except Exception:
        return False        # na dúvida, não incomoda
