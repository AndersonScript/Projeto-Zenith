"""
Zenith — Lembretes e alarmes que sobrevivem a reiniciar (/lembrar, /lembretes).

    /lembrar 15:30 entregar o relatório
    /lembrar em 20min tirar o pão do forno
    /lembrar amanhã 7h30 prova de física
    /lembrar sexta 14h reunião da IC
    /lembrar 25/12 9h ligar pra vó

Três peças, todas sem dependência fora da biblioteca padrão:
  * interpretar()  — entende o horário escrito em português;
  * Lembretes      — guarda em config/zenith_lembretes.json (escrita atômica);
  * Agendador      — thread que confere de tempos em tempos e dispara.

Se o Zenith estava fechado na hora, o lembrete dispara assim que abrir (marcado
como atrasado) — não se perde. O callback pode devolver False pra ADIAR o
disparo (usado pelo modo silêncio total: nada toca nem aparece até /retomar).
Nunca levanta exceção pra quem chamou, exceto ErroLembrete (mensagem pronta
pra mostrar ao usuário) em interpretar().
"""
import datetime
import json
import os
import re
import threading
import unicodedata
import uuid
from pathlib import Path

_DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}
_USO = ("Use assim: /lembrar <quando> <o quê> — ex.: /lembrar 15:30 entregar relatório · "
        "/lembrar em 20min tirar o pão · /lembrar amanhã 7h30 prova · /lembrar sexta 14h reunião · "
        "/lembrar 25/12 9h ligar pra vó")


class ErroLembrete(ValueError):
    """Mensagem já escrita pra mostrar ao usuário."""


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_RE_RELATIVO = re.compile(
    r"^em\s+(?:(\d+)\s*(?:h|hr|hrs|hora|horas)(?:\s*(?:e\s*)?(\d+)\s*(?:min|minutos?|m)?)?"
    r"|(\d+)\s*(?:min|minutos?|m))\b\s*")
_RE_HORA = re.compile(r"^(?:(?:as|a)\s+)?(\d{1,2})(?:\s*:\s*(\d{2})|\s*h\s*(\d{2})?|\s*horas?)(?=\s|$|[,.;:\-–])\s*")
_RE_DATA_BR = re.compile(r"^(?:dia\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*")
_RE_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s*")
_RE_DIA_SEMANA = re.compile(r"^(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:\s*-?\s*feira)?\b\s*")


def _limpar_mensagem(msg: str) -> str:
    msg = msg.strip()
    msg = re.sub(r"^[:\-–,.]\s*", "", msg)
    msg = re.sub(r"(?i)^(de|pra|para|que)\s+", "", msg)
    return msg.strip()


def interpretar(texto: str, agora=None):
    """'15:30 entregar relatório' -> (datetime, 'entregar relatório').
    Levanta ErroLembrete com explicação se não entender ou se o horário já passou."""
    agora = (agora or datetime.datetime.now()).replace(microsecond=0)
    bruto = str(texto or "").strip()
    if not bruto:
        raise ErroLembrete(_USO)
    base = _sem_acento(bruto.lower())
    if len(base) != len(bruto):          # alinhamento de índices (texto já decomposto): cai pro simples
        base = bruto.lower()

    # --- relativo: "em 20min", "em 2h", "em 1h30" ---
    m = _RE_RELATIVO.match(base)
    if m:
        if m.group(3):
            delta = datetime.timedelta(minutes=int(m.group(3)))
        else:
            delta = datetime.timedelta(hours=int(m.group(1)), minutes=int(m.group(2) or 0))
        if delta.total_seconds() <= 0:
            raise ErroLembrete("O tempo precisa ser maior que zero. " + _USO)
        msg = _limpar_mensagem(bruto[m.end():])
        return agora + delta, msg or "Lembrete"

    # --- data (opcional) ---
    pos, data, explicita, tipo = 0, agora.date(), False, "hoje"
    resto = base
    if resto.startswith("hoje"):
        pos, explicita, tipo = 4, True, "hoje"
    elif resto.startswith("amanha"):
        pos, data, explicita, tipo = 6, agora.date() + datetime.timedelta(days=1), True, "amanha"
    elif resto.startswith("depois de amanha"):
        pos, data, explicita, tipo = 16, agora.date() + datetime.timedelta(days=2), True, "amanha"
    else:
        md = _RE_DIA_SEMANA.match(resto)
        if md:
            alvo = _DIAS_SEMANA[md.group(1)]
            falta = (alvo - agora.weekday()) % 7
            pos, data, explicita, tipo = md.end(), agora.date() + datetime.timedelta(days=falta), True, "semana"
        else:
            md = _RE_DATA_ISO.match(resto)
            if md:
                try:
                    data = datetime.date(int(md.group(1)), int(md.group(2)), int(md.group(3)))
                except ValueError:
                    raise ErroLembrete("Essa data não existe. " + _USO)
                pos, explicita, tipo = md.end(), True, "data_completa"
            else:
                md = _RE_DATA_BR.match(resto)
                if md:
                    ano = md.group(3)
                    try:
                        if ano:
                            ano_n = int(ano) + (2000 if len(ano) == 2 else 0)
                            data, tipo = datetime.date(ano_n, int(md.group(2)), int(md.group(1))), "data_completa"
                        else:
                            data, tipo = datetime.date(agora.year, int(md.group(2)), int(md.group(1))), "data_sem_ano"
                    except ValueError:
                        raise ErroLembrete("Essa data não existe. " + _USO)
                    pos, explicita = md.end(), True
    resto = resto[pos:].lstrip()

    mh = _RE_HORA.match(resto)
    if not mh:
        raise ErroLembrete("Não achei a hora. " + _USO)
    hora = int(mh.group(1))
    minuto = int(mh.group(2) or mh.group(3) or 0)
    if hora > 23 or minuto > 59:
        raise ErroLembrete("Essa hora não existe (use de 0:00 a 23:59). " + _USO)
    msg = _limpar_mensagem(bruto[len(bruto) - len(resto) + mh.end():])
    quando = datetime.datetime.combine(data, datetime.time(hora, minuto))

    if quando <= agora:
        if tipo == "hoje" and explicita:
            raise ErroLembrete(f"Hoje às {hora:02d}:{minuto:02d} já passou. Use amanhã ou outra hora.")
        if tipo == "semana":
            quando += datetime.timedelta(days=7)
        elif tipo == "data_sem_ano":
            quando = quando.replace(year=quando.year + 1)
        elif tipo == "data_completa":
            raise ErroLembrete("Essa data e hora já passaram.")
        elif not explicita:
            quando += datetime.timedelta(days=1)       # só "15:30" e já passou hoje -> amanhã
        else:
            raise ErroLembrete("Esse horário já passou.")
    return quando, msg or "Lembrete"


def _caminho_padrao() -> Path:
    from brain.zenith_settings import CONFIG_DIR
    return Path(CONFIG_DIR) / "zenith_lembretes.json"


class Lembretes:
    """Armazenamento. Cada item: {"id","quando"(ISO local),"texto","criado"}."""

    def __init__(self, caminho=None):
        self._caminho = Path(caminho) if caminho else None
        self._lock = threading.RLock()

    @property
    def caminho(self) -> Path:
        return self._caminho or _caminho_padrao()

    def _ler(self) -> list:
        try:
            p = self.caminho
            if not p.exists():
                return []
            dados = json.loads(p.read_text(encoding="utf-8", errors="replace") or "[]")
            return [d for d in dados if isinstance(d, dict) and d.get("quando") and d.get("id")]
        except (OSError, ValueError):
            return []

    def _gravar(self, itens: list) -> bool:
        try:
            p = self.caminho
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, p)
            return True
        except OSError as e:
            print(f"[Zenith/Lembretes] não consegui gravar: {e}")
            return False

    def adicionar(self, quando: datetime.datetime, texto: str) -> dict:
        item = {"id": uuid.uuid4().hex[:6], "quando": quando.replace(microsecond=0).isoformat(),
                "texto": str(texto or "Lembrete").strip() or "Lembrete",
                "criado": datetime.datetime.now().replace(microsecond=0).isoformat()}
        with self._lock:
            itens = self._ler()
            itens.append(item)
            self._gravar(itens)
        return item

    def pendentes(self) -> list:
        with self._lock:
            return sorted(self._ler(), key=lambda d: d["quando"])

    def vencidos(self, agora=None) -> list:
        agora = (agora or datetime.datetime.now()).replace(microsecond=0).isoformat()
        return [d for d in self.pendentes() if d["quando"] <= agora]

    def marcar_disparado(self, id_: str) -> bool:
        with self._lock:
            itens = self._ler()
            novos = [d for d in itens if d["id"] != id_]
            return len(novos) != len(itens) and self._gravar(novos)

    def remover(self, ref) -> "dict | None":
        """ref: número da lista de /lembretes (1, 2, ...) ou o id. Devolve o item removido."""
        with self._lock:
            lista = self.pendentes()
            alvo = None
            ref = str(ref or "").strip().lstrip("#")
            if ref.isdigit() and 1 <= int(ref) <= len(lista):
                alvo = lista[int(ref) - 1]
            else:
                alvo = next((d for d in lista if d["id"] == ref), None)
            if alvo is None:
                return None
            self.marcar_disparado(alvo["id"])
            return alvo

    def formatar(self, agora=None) -> str:
        lista = self.pendentes()
        if not lista:
            return "⏰ Nenhum lembrete pendente. Use /lembrar <quando> <o quê>."
        agora = agora or datetime.datetime.now()
        linhas = [f"⏰ {len(lista)} lembrete(s) pendente(s):"]
        for i, d in enumerate(lista, 1):
            q = datetime.datetime.fromisoformat(d["quando"])
            dia = ("hoje" if q.date() == agora.date() else
                   "amanhã" if q.date() == agora.date() + datetime.timedelta(days=1) else q.strftime("%d/%m"))
            linhas.append(f"{i}. {dia} {q.strftime('%H:%M')} — {d['texto']}")
        linhas.append("Apagar: /lembrete_apagar <número>")
        return "\n".join(linhas)


class Agendador:
    """Thread que confere os lembretes. callback(lembrete, atraso_minutos) -> False adia."""

    def __init__(self, lembretes: Lembretes, callback, intervalo: float = 15.0, agora=None):
        self.lembretes = lembretes
        self.callback = callback
        self.intervalo = intervalo
        self._agora = agora or datetime.datetime.now
        self._parar = threading.Event()
        self._thread = None

    def verificar(self) -> int:
        """Dispara o que venceu. Devolve quantos foram disparados (testável sem thread)."""
        disparados = 0
        agora = self._agora()
        for d in self.lembretes.vencidos(agora):
            try:
                atraso = (agora - datetime.datetime.fromisoformat(d["quando"])).total_seconds() / 60.0
                tratado = self.callback(d, atraso) if self.callback else True
            except Exception as e:
                print(f"[Zenith/Lembretes] erro no disparo: {e}")
                tratado = False
            if tratado is not False:
                self.lembretes.marcar_disparado(d["id"])
                disparados += 1
        return disparados

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="zenith-lembretes")
        self._thread.start()

    def stop(self):
        self._parar.set()

    def _loop(self):
        while not self._parar.is_set():
            try:
                self.verificar()
            except Exception as e:
                print(f"[Zenith/Lembretes] erro no agendador: {e}")
            self._parar.wait(self.intervalo)
