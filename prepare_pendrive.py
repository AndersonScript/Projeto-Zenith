# ============================================================
#  ZENITH — Criado por Anderson
#  prepare_pendrive.py — Zera uma cópia já compilada (dist/Zenith)
#  antes de levar pra um pen drive ou distribuir pra outra pessoa.
#
#  Por quê isso existe: build_exe.py copia o SEU config/ (com suas
#  chaves de API, sua Zenith personalizada, seu histórico de conversa)
#  pra dentro de dist/Zenith/config/ — ótimo pra você testar rápido o
#  build, péssimo se você distribuir essa mesma pasta sem mais nada:
#  a pessoa que abrir em outro PC herdaria suas chaves e conversas.
#
#  v19: também leva embora o que é "de marca" ou pessoal e nasceu no v18
#  (catálogo de provedores com nomes/URLs/dicas, notas, log de ações,
#  lembretes, avatares que VOCÊ adicionou) e, no fim, VARRE a pasta
#  procurando o que sobrou: padrão de chave de API, caminho pessoal e
#  endereço de provedor. Sem o catálogo, quem receber vê só "Adicionar
#  nova IA" (cola o endereço e a chave que o provedor dela fornece).
#
#  Esse script NÃO mexe no seu projeto fonte (a pasta onde este
#  arquivo está) — só limpa uma cópia já compilada, em dist/Zenith
#  por padrão, ou em qualquer pasta que você apontar. Sempre pede
#  confirmação antes de apagar qualquer coisa.
#
#  Rode com: python prepare_pendrive.py
#        ou: python prepare_pendrive.py "D:\caminho\pra\outra\copia"
#  Opções:   --sem-avatares   tira TODOS os .vrm da cópia (inclusive Zenith/Cypher),
#                              se você não tem certeza da licença de redistribuição
#            --so-varrer      não apaga nada; só roda a varredura e mostra o resultado
# ============================================================

import json
import os
import re
import shutil
import sys

# CORREÇÃO (crash de verdade no PC do Anderson — pego pela suíte de testes): este script
# imprime emoji (⚠, ✅, 🗂️) e o console do Windows usa a codificação cp1252 por padrão, que NÃO
# sabe escrever emoji. Resultado: "UnicodeEncodeError: 'charmap' codec can't encode character
# '\u26a0'" e o prepare_pendrive MORRIA NO MEIO — justamente na hora de avisar que os avatares
# removidos ainda podiam estar dentro do Zenith.pck da cópia. Ou seja: a pessoa era interrompida
# exatamente no aviso de segurança. É o mesmo mal do console que já tinha sujado o terminal do
# PyCharm antes (ver o _Vazio em zenith_launcher.py). Com errors="replace", na pior das
# hipóteses o emoji sai como "?" — nunca derruba o script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

# O que precisa ser zerado — tudo que é DADO PESSOAL, não parte do programa.
_FOLDERS_TO_EMPTY = ["memory_db", "temp", "creations", "skills",      # v23: habilidades criadas pela Zenith não vão pra cópia de distribuição
                     os.path.join("config", "biblioteca")]             # v28: a biblioteca de documentos (PDFs/apostilas) é do dono; creations/ já leva vídeos, documentos e a quarentena
_FILES_TO_REMOVE = [
    os.path.join("config", "conversations.json"),
    # v19 — dados que o v18 passou a gravar em config/:
    os.path.join("config", "zenith_notas.jsonl"),          # notas de laboratório (/nota)
    os.path.join("config", "zenith_acoes_log.jsonl"),      # log de ações aprovadas/negadas
    os.path.join("config", "zenith_acoes_log.1.jsonl"),    # (a rotação do log)
    os.path.join("config", "zenith_lembretes.json"),       # lembretes (/lembrar)
    # v19 — catálogo de provedores (nomes, URLs, dicas): fica de fora da distribuição
    os.path.join("config", "provedores_catalogo.json"),
    os.path.join("config", ".reset_pendente"),             # v20: marcador do "Resetar tudo"
    os.path.join("config", ".admin_ok"),                   # v26: cada cópia nova pergunta de novo da 1ª abertura como administrador
    os.path.join("config", ".admin_dispensado"),           # (marca antiga da v26)
    os.path.join("config", "aparencia.json"),              # v26: cores do autorretrato (personalização do dono)
    os.path.join("config", "zenith_voz_debug.log"),         # v20: log da voz (guarda caminhos pessoais)
    os.path.join("config", "biblia_extra.md"),             # v21: regras pessoais do usuário para a IA
    os.path.join("config", "ZENITH.md"),                   # v22: contexto pessoal (os cartões padrão vêm do código)
    "zenith_log.txt",
    "_zenith_voice_temp.mp3",
]
# Sobras da troca do Zenith.pck na importação de avatar — procuradas em qualquer subpasta.
_NOMES_SOBRA_PCK = ("Zenith_novo.pck", "Zenith.pck.bak")

# Avatares que já vêm no projeto. Qualquer OUTRO .vrm em body/zenith/addons/avatars foi
# adicionado por você ("Adicionar avatar...") e não vai pra distribuição.
# 1.0 Oficial: só o mascote Zenith viaja. Os VRMs prontos de terceiros saíram da
# distribuição — o Anderson vai desenhar o mascote oficial. Enquanto ele não existir, a pasta do
# avatar vai vazia e o Corpo desenha o visual padrão do código (vrm_model_path vazio).
AVATARES_DE_FABRICA = ("Zenith.vrm",)
_PASTA_AVATARES = os.path.join("body", "zenith", "addons", "avatars")
_PASTA_CACHE_IMPORT = os.path.join("body", "zenith", ".godot", "imported")

# settings.json não é removido — é RESETADO pros valores padrão (ver
# reset_settings_json), assim a pasta config/ continua existindo e
# válida, só sem nada pessoal seu dentro. onboarding_done sempre volta
# pra False, senão a tela de "criar sua IA" não apareceria no PC novo.
_KEEP_BUT_RESET = ["persona_name", "user_name", "persona_description", "user_pillars"]

_CAMPOS_PESSOAIS = [
    "gemini_key", "openai_key", "openrouter_key", "groq_key", "tavily_api_key",
    "custom_api_url", "custom_api_key", "custom_api_model",
    "ai_endpoints", "elevenlabs_key", "elevenlabs_voice_id",
    "rvc_model_path", "rvc_index_path", "vrm_model_path",
    "chat_wallpaper_path", "unlock_password", "data_root_path",
    "output_folder", "godot_executable_path", "godot_project_path",
    "rvc_python_exe",                                       # v20: caminho do Python 3.10 do RVC
]

# ---------------- varredura ----------------
# Endereços de provedor que NÃO podem sobrar em arquivo de texto da distribuição.
HOSTS_DE_PROVEDOR = (
    "openrouter.ai", "api.groq.com", "console.groq.com", "aistudio.google.com",
    "generativelanguage.googleapis.com", "platform.openai.com", "api.openai.com",
    "api.together.xyz", "api.anthropic.com", "tavily.com",
)
_PADROES_CHAVE = [
    ("chave de API (sk-…)", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("chave de API (AIza…)", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("chave de API (gsk_…)", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("chave de API (tvly-…)", re.compile(r"\btvly-[A-Za-z0-9\-]{10,}")),
]
_CAMPO_SEGREDO_JSON = re.compile(
    r'"(?:[A-Za-z_]*_key|api_key|unlock_password)"\s*:\s*"([^"\s]{4,})"', re.IGNORECASE)
_CAMINHO_PESSOAL = re.compile(
    r"(?:[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}(?!Public\b|Default\b|All Users\b|<usuario>)[^\\/\s\"']+"
    r"|/home/(?!<usuario>)[^/\s\"']+|/Users/(?!Shared\b|<usuario>)[^/\s\"']+)")
_EXT_TEXTO = (".json", ".jsonl", ".md", ".txt", ".cfg", ".gd", ".tres", ".godot", ".html",
              ".bat", ".ini", ".import", ".py", ".csv", ".log", ".toml", ".yml", ".yaml")
_PASTAS_IGNORADAS = {"_internal", ".godot", "models", "__pycache__", "addons", ".git", "tools"}
_TETO_ARQUIVO = 2 * 1024 * 1024


def _parse_args(argv):
    opcoes = {a for a in argv if a.startswith("--")}
    caminhos = [a for a in argv if not a.startswith("--")]
    alvo = os.path.abspath(caminhos[0]) if caminhos else os.path.join(HERE, "dist", "Zenith")
    return alvo, opcoes


def reset_settings_json(target: str):
    settings_path = os.path.join(target, "config", "settings.json")
    if not os.path.isfile(settings_path):
        return
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Pendrive] Não consegui ler settings.json ({e}) — apagando e "
              f"deixando o Zenith recriar do zero na próxima abertura.")
        os.remove(settings_path)
        return

    # Zera TUDO que é pessoal: chaves de API, identidade da IA, senha
    # de desbloqueio, IAs personalizadas cadastradas, pasta de dados
    # customizada (se apontava pra algo só do seu PC).
    for campo in _CAMPOS_PESSOAIS:
        if campo in data:
            data[campo] = [] if isinstance(data.get(campo), list) else ""

    for campo in _KEEP_BUT_RESET:
        data[campo] = "" if campo != "persona_name" else "Zenith"

    data["onboarding_done"] = False        # a pessoa que abrir vê a tela de boas-vindas
    data["aviso_inicial_visto"] = False    # v19: o aviso de primeiro uso aparece de novo
    data["modo_atual"] = "normal"          # v19: volta pro modo padrão
    data["active_ai"] = "gemini"           # (a 1ª IA que a pessoa cadastrar vira a ativa sozinha)

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print("[Pendrive] settings.json resetado (chaves, persona e IAs personalizadas zeradas).")


def remover_sobras_pck(target: str) -> list:
    """Remove Zenith_novo.pck / Zenith.pck.bak (restos da importação de avatar), em qualquer subpasta."""
    removidos = []
    for raiz, pastas, arquivos in os.walk(target):
        pastas[:] = [p for p in pastas if p not in ("_internal",)]
        for nome in arquivos:
            if nome in _NOMES_SOBRA_PCK:
                caminho = os.path.join(raiz, nome)
                try:
                    os.remove(caminho)
                    removidos.append(os.path.relpath(caminho, target))
                except OSError as e:
                    print(f"[Pendrive] Não consegui remover {caminho}: {e}")
    return removidos


def avatares_extras(target: str, sem_avatares: bool = False) -> list:
    """Nomes dos .vrm a tirar: os que não são de fábrica (ou TODOS com --sem-avatares)."""
    pasta = os.path.join(target, _PASTA_AVATARES)
    if not os.path.isdir(pasta):
        return []
    alvo = []
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith(".vrm"):
            continue
        if sem_avatares or nome not in AVATARES_DE_FABRICA:
            alvo.append(nome)
    return alvo


def remover_avatares(target: str, nomes: list) -> list:
    """Apaga cada .vrm, seu .vrm.import e o cache importado do Godot. Devolve o que removeu."""
    removidos = []
    pasta = os.path.join(target, _PASTA_AVATARES)
    cache = os.path.join(target, _PASTA_CACHE_IMPORT)
    for nome in nomes:
        for sufixo in ("", ".import"):
            caminho = os.path.join(pasta, nome + sufixo)
            if os.path.isfile(caminho):
                os.remove(caminho)
                removidos.append(os.path.relpath(caminho, target))
        if os.path.isdir(cache):
            prefixo = nome + "-"          # o Godot grava "<arquivo>.vrm-<hash>.scn" etc.
            for item in os.listdir(cache):
                if item.startswith(prefixo):
                    caminho = os.path.join(cache, item)
                    try:
                        os.remove(caminho)
                        removidos.append(os.path.relpath(caminho, target))
                    except OSError:
                        pass
    return removidos


def _eh_texto(nome: str) -> bool:
    return nome.lower().endswith(_EXT_TEXTO)


def varrer_distribuicao(target: str) -> list:
    """Procura, em arquivos de TEXTO da cópia, o que não deveria ir pra outra pessoa:
    chave de API, caminho pessoal e endereço de provedor. Devolve [(arquivo, tipo, trecho)].
    O trecho de chave sai MASCARADO. Não olha _internal/, .godot/, models/, addons/ e tools/."""
    achados = []
    for raiz, pastas, arquivos in os.walk(target):
        pastas[:] = [p for p in pastas if p not in _PASTAS_IGNORADAS]
        for nome in arquivos:
            if not _eh_texto(nome):
                continue
            caminho = os.path.join(raiz, nome)
            rel = os.path.relpath(caminho, target)
            try:
                if os.path.getsize(caminho) > _TETO_ARQUIVO:
                    continue
                with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                    texto = f.read()
            except OSError:
                continue
            for tipo, padrao in _PADROES_CHAVE:
                for m in padrao.finditer(texto):
                    achados.append((rel, tipo, m.group(0)[:4] + "…(mascarado)"))
            if nome.lower().endswith((".json", ".jsonl")):
                for m in _CAMPO_SEGREDO_JSON.finditer(texto):
                    achados.append((rel, "campo de segredo preenchido", "…(mascarado)"))
            for m in _CAMINHO_PESSOAL.finditer(texto):
                achados.append((rel, "caminho pessoal", m.group(0)))
            baixo = texto.lower()
            for host in HOSTS_DE_PROVEDOR:
                if host in baixo:
                    achados.append((rel, "endereço de provedor", host))
    # caminhos pessoais "soltos" no settings.json (D:/Código em Python/…, etc.)
    sj = os.path.join(target, "config", "settings.json")
    if os.path.isfile(sj):
        try:
            with open(sj, "r", encoding="utf-8") as f:
                dados = json.load(f)
            for k, v in dados.items():
                if isinstance(v, str) and v.strip() and (k.endswith("_path") or k.endswith("_folder")
                                                         or k in ("output_folder",)):
                    achados.append((os.path.join("config", "settings.json"), "caminho pessoal", f"{k}={v}"))
        except Exception:
            pass
    vistos, unicos = set(), []
    for a in achados:
        if a not in vistos:
            vistos.add(a)
            unicos.append(a)
    return unicos


def _mostrar_varredura(achados: list):
    if not achados:
        print("[Pendrive] Varredura: nada suspeito encontrado nos arquivos de texto da cópia. ✓")
        return
    print(f"[Pendrive] ⚠ Varredura: {len(achados)} item(ns) pra você olhar antes de distribuir:")
    for arquivo, tipo, trecho in achados[:40]:
        print(f"    - {arquivo}: {tipo} → {trecho}")
    if len(achados) > 40:
        print(f"    ... e mais {len(achados) - 40}.")


def main(argv=None):
    target, opcoes = _parse_args(sys.argv[1:] if argv is None else argv)
    if not os.path.isdir(target):
        print(f"[Pendrive] Não encontrei a pasta '{target}'. Rode 'python build_exe.py' "
              f"primeiro, ou passe o caminho certo como argumento.")
        return

    if "--so-varrer" in opcoes:
        _mostrar_varredura(varrer_distribuicao(target))
        return

    sem_avatares = "--sem-avatares" in opcoes
    extras = avatares_extras(target, sem_avatares)

    print(f"[Pendrive] Isso vai APAGAR de forma PERMANENTE, dentro de:\n    {target}\n")
    print("  - Memória de longo prazo (memory_db/)")
    print("  - Conversas salvas (config/conversations.json)")
    print("  - Notas, log de ações e lembretes (config/zenith_*.jsonl / .json)")
    print("  - Catálogo de provedores de IA (config/provedores_catalogo.json) — sem ele não sobra")
    print("    nome, endereço nem dica de provedor na interface")
    print("  - Arquivos temporários e criações (temp/, creations/ — inclui vídeos, documentos e a quarentena)")
    print("  - Biblioteca de documentos (config/biblioteca/)")
    print("  - Chaves de API, IAs personalizadas e persona (config/settings.json é resetado)")
    if extras:
        print(f"  - Avatares {'(TODOS)' if sem_avatares else 'que você adicionou'}: {', '.join(extras)}")
    print("\nO PROGRAMA em si (Zenith.exe, o Corpo/Godot, os modelos de voz já baixados "
          "em models/) NÃO é tocado — só o que é dado pessoal seu.\n")
    resposta = input("Confirma? Digite SIM para continuar: ").strip().upper()
    if resposta != "SIM":
        print("[Pendrive] Cancelado — nada foi apagado.")
        return

    for pasta in _FOLDERS_TO_EMPTY:
        caminho = os.path.join(target, pasta)
        if os.path.isdir(caminho):
            shutil.rmtree(caminho)
            os.makedirs(caminho, exist_ok=True)
            print(f"[Pendrive] {pasta}/ esvaziada.")

    for arquivo in _FILES_TO_REMOVE:
        caminho = os.path.join(target, arquivo)
        if os.path.isfile(caminho):
            os.remove(caminho)
            print(f"[Pendrive] {arquivo} removido.")

    for r in remover_sobras_pck(target):
        print(f"[Pendrive] {r} removido (sobra da importação de avatar).")

    if extras:
        for r in remover_avatares(target, extras):
            print(f"[Pendrive] {r} removido.")
        print("[Pendrive] ⚠ Os avatares removidos AINDA podem estar dentro do Zenith.pck desta cópia "
              "(a importação regrava o pacote). Pra ter certeza, gere a distribuição de um build novo: "
              "rode build_exe.py com a pasta addons/avatars/ do projeto só com os avatares que você "
              "quer distribuir.")

    reset_settings_json(target)

    rvc_env = os.path.join(target, "tools", "rvc")
    if os.path.isdir(rvc_env):
        print("[Pendrive] ⚠ Existe tools/rvc/ nesta cópia (o ambiente do RVC, ~2 GB, ligado ao SEU computador). "
              "Apague essa pasta antes de distribuir — quem receber roda o instalar_rvc.bat se quiser a voz RVC.")

    _mostrar_varredura(varrer_distribuicao(target))

    print("\n============================================================")
    print(" Pronto! Essa cópia está zerada e pronta pro pen drive.")
    print(" Quando alguém abrir o Zenith.exe pela primeira vez num PC")
    print(" novo, a tela de boas-vindas vai perguntar o nome da IA —")
    print(" pode manter Zenith ou criar a IA da pessoa do zero. Em")
    print(" Configurações > IAs & Chaves ela cola o endereço e a chave")
    print(" do provedor dela em \"Adicionar nova IA\".")
    print("============================================================")


if __name__ == "__main__":
    main()
