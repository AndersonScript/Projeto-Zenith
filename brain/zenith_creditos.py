"""
Zenith — QUEM FEZ (v1.0).

O Anderson pediu, com estas palavras: "quero que coloca no menu de configurações falando quem
criou, que é Anderson Ricardo de Souza Filho... e depois eu penso em um texto me apresentando,
que não quero falar onde estudo".

Por isso este arquivo existe em duas partes:

1. O NOME e o PAPEL ficam aqui (não mudam).
2. A APRESENTAÇÃO é um TEXTO que ele mesmo escreve em `config/creditos.txt` — sem precisar
   recompilar o .exe nem mexer em código. Enquanto esse arquivo não existir (ou estiver vazio),
   vale um texto curto e neutro, que NÃO fala de escola, faculdade, cidade, idade nem de nada
   pessoal. É de propósito: o texto padrão precisa ser seguro para ir em qualquer lugar.

Como ele edita:
    abrir a pasta do Zenith > config > creditos.txt > escrever > salvar.
    O texto aparece em /sobre, na aba "Sobre" das Configurações e no /relatorio.
"""
from __future__ import annotations

from pathlib import Path

try:
    from brain.zenith_settings import CONFIG_DIR
except Exception:                                   # pragma: no cover — usado em teste isolado
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

CRIADOR = "Anderson Ricardo de Souza Filho"
PAPEL = "Criador e desenvolvedor do Zenith"
PROJETO = "Zenith"
AVATAR = "Zenith"

# Texto padrão: seguro para qualquer leitor (sem escola, sem endereço, sem dado pessoal).
TEXTO_PADRAO = (
    "O Zenith é um projeto pessoal de assistente com avatar: um programa que conversa, "
    "entende o que você pede, mostra o que pretende fazer antes de fazer e pede a sua "
    "aprovação — no seu computador, com as suas chaves.\n"
    "\n"
    "Foi criado e é desenvolvido por Anderson Ricardo de Souza Filho, que está aprendendo "
    "programação e construindo este programa aos poucos: cada versão nasce de um problema "
    "de verdade que ele encontrou usando o próprio Zenith.\n"
    "\n"
    "O avatar é o rosto do projeto; quem pensa, aprova e cuida dos dados é você."
)

ARQUIVO_TEXTO = Path(CONFIG_DIR) / "creditos.txt"

# Marcador para não confundir o texto do usuário com o padrão.
_CABECALHO = (
    "# Escreva aqui a sua apresentação (aparece em /sobre e nas Configurações > Sobre).\n"
    "# Linhas que começam com # são ignoradas. Deixe em branco para usar o texto padrão.\n"
    "# Nada do que estiver aqui é enviado para a internet.\n\n"
)


def texto_personalizado() -> str:
    """O texto que o Anderson escreveu em config/creditos.txt (ou "" se ainda não escreveu)."""
    try:
        if not ARQUIVO_TEXTO.is_file():
            return ""
        linhas = [ln for ln in ARQUIVO_TEXTO.read_text(encoding="utf-8", errors="replace").splitlines()
                  if not ln.lstrip().startswith("#")]
        return "\n".join(linhas).strip()
    except OSError:
        return ""


def texto() -> str:
    """A apresentação em uso: a do usuário, se existir; senão a padrão."""
    proprio = texto_personalizado()
    return proprio or TEXTO_PADRAO


def garantir_arquivo() -> bool:
    """Cria config/creditos.txt com o cabeçalho explicativo (nunca sobrescreve o que já existe)."""
    try:
        if ARQUIVO_TEXTO.is_file():
            return False
        ARQUIVO_TEXTO.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_TEXTO.write_text(_CABECALHO, encoding="utf-8")
        return True
    except OSError:
        return False


def resumo() -> str:
    """Uma linha só, para o rodapé da tela e para o /relatorio."""
    return f"{PROJETO} — criado por {CRIADOR}"


def dados() -> dict:
    """Tudo o que a tela "Sobre" (Godot) precisa. Nenhum dado sensível."""
    from brain import zenith_version
    return {
        "nome": PROJETO,
        "criador": CRIADOR,
        "papel": PAPEL,
        "avatar": AVATAR,
        "texto": texto(),
        "personalizado": bool(texto_personalizado()),
        "versao": zenith_version.VERSAO,
        "versao_completa": zenith_version.texto(),
        "onde_editar": str(ARQUIVO_TEXTO),
    }


def texto_chat() -> str:
    """/sobre — o que aparece no chat (curto, em português, sem jargão)."""
    from brain import zenith_version
    linhas = [
        f"👤 {PROJETO} {zenith_version.VERSAO} — {zenith_version.DESCRICAO}",
        f"Criado por {CRIADOR}.",
        "",
        texto(),
        "",
        f"✍️ Quer mudar esta apresentação? Escreva no arquivo: {ARQUIVO_TEXTO}",
        "(não precisa recompilar nada — o texto novo aparece na próxima abertura)",
    ]
    return "\n".join(linhas)
