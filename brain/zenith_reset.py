"""
Zenith — "Resetar tudo" dentro do programa (v20).

Pedido do Anderson: um botão de resetar no próprio Godot (sem precisar rodar o
prepare_pendrive.py). Apaga o que é PESSOAL — memória, conversas, notas, log de ações,
lembretes, chaves de API, IAs cadastradas, persona — e deixa o programa como "primeira vez".
NÃO apaga o programa, os avatares nem os modelos de voz já baixados.

Por que é AGENDADO: no Windows não dá pra apagar arquivo que o próprio programa está usando
(a memória de longo prazo, por exemplo, fica aberta). Então o botão só grava um marcador
(config/.reset_pendente) e a limpeza roda na PRÓXIMA abertura, antes de qualquer coisa abrir
esses arquivos. Também por isso o botão pede confirmação digitada.

Nada aqui importa Godot, rede ou bibliotecas pesadas. Todas as funções recebem a pasta-base,
então os testes usam uma pasta temporária e nunca tocam no projeto real.
"""
import json
import shutil
import time
from pathlib import Path

MARCADOR = ".reset_pendente"
PALAVRA_CONFIRMACAO = "RESETAR"

# Pastas (dentro da base) que são esvaziadas
PASTAS = ("memory_db", "temp", "creations", "skills")      # v23: skills/ = habilidades que ELA criou (conteúdo da pessoa)
# Arquivos (relativos à base) apagados
ARQUIVOS = (
    "config/conversations.json",
    "config/zenith_notas.jsonl",
    "config/zenith_acoes_log.jsonl",
    "config/zenith_acoes_log.1.jsonl",
    "config/zenith_lembretes.json",
    "config/zenith_voz_debug.log",
    "config/biblia_extra.md",
    "config/ZENITH.md",                      # v22: contexto pessoal que o usuário escreveu
    "zenith_log.txt",
    "_zenith_voice_temp.mp3",
)
# Campos do settings.json zerados (chaves, caminhos e identidade pessoais)
CAMPOS_PESSOAIS = (
    "gemini_key", "openai_key", "openrouter_key", "groq_key", "tavily_api_key",
    "custom_api_url", "custom_api_key", "custom_api_model", "elevenlabs_key", "elevenlabs_voice_id",
    "rvc_model_path", "rvc_index_path", "vrm_model_path", "chat_wallpaper_path", "unlock_password",
    "data_root_path", "output_folder", "godot_executable_path", "godot_project_path", "rvc_python_exe",
)


def caminho_marcador(base) -> Path:
    return Path(base) / "config" / MARCADOR


def agendar(base, confirmacao: str) -> tuple:
    """Grava o marcador se `confirmacao` for a palavra certa. Devolve (ok, mensagem)."""
    if str(confirmacao or "").strip().upper() != PALAVRA_CONFIRMACAO:
        return False, f"Para confirmar, digite {PALAVRA_CONFIRMACAO} (em maiúsculas ou minúsculas)."
    m = caminho_marcador(base)
    try:
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(json.dumps({"agendado_em": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    except OSError as e:
        return False, f"Não consegui agendar o reset: {e}"
    return True, "Reset agendado. Feche o Zenith e abra de novo — ele abre zerado."


def cancelar(base) -> bool:
    try:
        caminho_marcador(base).unlink()
        return True
    except OSError:
        return False


def pendente(base) -> bool:
    return caminho_marcador(base).is_file()


def _esvaziar(pasta: Path, falhas: list):
    if not pasta.is_dir():
        return
    for item in pasta.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError as e:
            falhas.append(f"{item.name}: {e}")


def aplicar_se_pendente(base, log=print) -> dict:
    """Chamar ANTES de abrir settings/memória. Se houver marcador, faz a limpeza e o remove.
    Devolve {"aplicado": bool, "falhas": [...]} — nunca levanta exceção."""
    base = Path(base)
    if not pendente(base):
        return {"aplicado": False, "falhas": []}
    falhas = []
    try:
        for nome in PASTAS:
            _esvaziar(base / nome, falhas)
        for rel in ARQUIVOS:
            alvo = base / rel
            try:
                if alvo.is_file():
                    alvo.unlink()
            except OSError as e:
                falhas.append(f"{rel}: {e}")
        sj = base / "config" / "settings.json"
        if sj.is_file():
            try:
                dados = json.loads(sj.read_text(encoding="utf-8"))
                for campo in CAMPOS_PESSOAIS:
                    if campo in dados:
                        dados[campo] = ""
                dados["ai_endpoints"] = []
                dados["persona_name"] = "Zenith"
                dados["user_name"] = ""
                dados["persona_description"] = ""
                dados["user_pillars"] = ""
                dados["onboarding_done"] = False
                dados["aviso_inicial_visto"] = False
                dados["modo_atual"] = "normal"
                dados["active_ai"] = "gemini"
                sj.write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError) as e:
                # settings ilegível: apaga, o Zenith recria do zero
                try:
                    sj.unlink()
                except OSError:
                    falhas.append(f"settings.json: {e}")
    finally:
        try:
            caminho_marcador(base).unlink()
        except OSError:
            pass
    if falhas:
        log(f"[Zenith] Reset aplicado, mas {len(falhas)} item(ns) não puderam ser apagados: {falhas[:3]}")
    else:
        log("[Zenith] Reset aplicado: dados pessoais apagados (primeira abertura).")
    return {"aplicado": True, "falhas": falhas}
