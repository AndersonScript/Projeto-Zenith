"""
Zenith — O PC MEDIDO e a RECOMENDAÇÃO de IA local (v1.7, tarefa T7).

A `zenith_ia_local.py` já sabia conversar com o Ollama/LM Studio, baixar modelo e entrar como
reserva. Faltava a pergunta que decide TUDO num Ryzen sem placa de vídeo: **qual modelo cabe
sem travar o computador?**

Este módulo só mede e recomenda; nada instala, nada baixa.

  * `medir()` usa `psutil` (opcional) — RAM total/livre, uso de CPU, núcleos, disco livre. Sem
    psutil, ainda dá o que é possível pela biblioteca padrão (núcleos, disco) e diz o que falta;
  * `recomendar(medida)` escolhe um modelo da lista da IA local que caiba na RAM livre COM folga
    (o modelo precisa de ~1,7× o tamanho do arquivo para rodar), com o motivo em uma frase;
  * `formatar()` monta o texto do chat. Instalar continua sendo `/local baixar`, com aprovação
    e mostrando o tamanho — nada é baixado por este módulo.

Regra de honestidade: se a RAM não puder ser medida, a recomendação vem como "não sei medir" em
vez de um chute; o usuário decide.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

um_gb = 1024 ** 3

# Tamanho do arquivo do modelo e RAM necessária para rodar (≈1,7× o arquivo, mais o sistema).
MODELOS = (
    {"modelo": "qwen2.5:1.5b", "arquivo_gb": 1.0, "ram_gb": 2.6,
     "nota": "conversa e português razoáveis; ~10–25 s por resposta num Ryzen sem GPU"},
    {"modelo": "llama3.2:3b", "arquivo_gb": 2.0, "ram_gb": 4.0,
     "nota": "melhor qualidade, ~20–40 s por resposta"},
    {"modelo": "qwen2.5:7b", "arquivo_gb": 4.7, "ram_gb": 8.0,
     "nota": "bem melhor, mas exige um PC com bastante RAM; lento em CPU"},
)
FOLGA_GB = 1.5          # o computador precisa continuar utilizável depois de carregar o modelo


def _memoria_windows():
    """RAM total/livre pelo Windows (sem psutil). Devolve (total_gb, livre_gb) ou (None, None)."""
    if os.name != "nt":
        return None, None
    try:
        import ctypes

        class _MEMSTATUS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MEMSTATUS()
        st.dwLength = ctypes.sizeof(_MEMSTATUS)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None, None
        return st.ullTotalPhys / um_gb, st.ullAvailPhys / um_gb
    except Exception:
        return None, None


def _plataforma_do_celular():
    """(v1.19) A plataforma Android quando o Cérebro roda no celular; fora dele, None (o PC continua como sempre foi)."""
    try:
        from brain import zenith_plataforma
        return zenith_plataforma.obter() if zenith_plataforma.detectar() == "android" else None
    except Exception:
        return None


def _eh_celular(medida: dict) -> bool:
    return medida.get("fonte") == "android" or "bateria_pct" in medida


_CHAVES_DO_ANDROID = ("ram_total_gb", "ram_livre_gb", "cpu_pct", "nucleos", "disco_livre_gb",
                      "bateria_pct", "carregando", "temperatura_c")


def medir(psutil_mod=None, disco: str = "") -> dict:
    """Mede o PC (ou, no celular, o aparelho: aí vêm também bateria e temperatura). `psutil_mod` é injetável no teste."""
    medida = {"ram_total_gb": None, "ram_livre_gb": None, "cpu_pct": None, "nucleos": os.cpu_count() or 0,
              "disco_livre_gb": None, "fonte": ""}
    try:
        alvo = disco or (os.environ.get("SystemDrive", "C:") + os.sep if os.name == "nt" else "/")
        medida["disco_livre_gb"] = round(shutil.disk_usage(alvo).free / um_gb, 1)
    except OSError:
        pass
    if psutil_mod is not None:
        try:
            vm = psutil_mod.virtual_memory()
            medida.update(ram_total_gb=round(vm.total / um_gb, 1), ram_livre_gb=round(vm.available / um_gb, 1),
                          cpu_pct=float(psutil_mod.cpu_percent(interval=0.2)),
                          nucleos=int(psutil_mod.cpu_count() or medida["nucleos"]), fonte="psutil")
            return medida
        except Exception:
            pass
    plat = _plataforma_do_celular() if psutil_mod is None else None
    if plat is not None:                      # celular: quem sabe a bateria e a temperatura é o Android (pela ponte)
        try:
            m = plat.medir()
        except Exception:
            m = None
        if isinstance(m, dict) and m.get("ram_total_gb") is not None:
            for k in _CHAVES_DO_ANDROID:
                if m.get(k) is not None:
                    medida[k] = m[k]
            for k in ("bateria_pct", "carregando", "temperatura_c"):
                medida.setdefault(k, None)
            medida["fonte"] = "android"
            return medida
    total, livre = _memoria_windows()
    if total is None:
        try:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / um_gb
            livre = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / um_gb
        except (AttributeError, ValueError, OSError):
            total = livre = None
    if total is not None:
        medida.update(ram_total_gb=round(total, 1), ram_livre_gb=round(livre, 1) if livre is not None else None,
                      fonte="windows" if os.name == "nt" else "unix")
    return medida


def recomendar(medida: dict, modelos=MODELOS) -> dict:
    """Escolhe o melhor modelo que caiba na RAM livre com folga. Devolve {modelo, motivo, ok}."""
    livre = medida.get("ram_livre_gb")
    total = medida.get("ram_total_gb")
    disco = medida.get("disco_livre_gb")
    referencia = livre if livre is not None else total
    if referencia is None:
        if _eh_celular(medida):
            return {"ok": False, "modelo": "", "motivo": "Não consegui medir a memória deste aparelho — "
                                                          "sem isso eu não chuto. Tente de novo em alguns segundos."}
        return {"ok": False, "modelo": "", "motivo": "Não consegui medir a memória deste PC — "
                                                      "sem isso eu não chuto. Instale o psutil "
                                                      "(py -m pip install psutil) e peça de novo."}
    escolhido = None
    for m in modelos:
        precisa = m["ram_gb"] + FOLGA_GB
        if referencia >= precisa and (disco is None or disco >= m["arquivo_gb"]):
            escolhido = m                    # fica com o MAIOR que cabe: melhor qualidade sem travar
    if not escolhido:
        return {"ok": False, "modelo": "",
                "motivo": (f"Com {referencia:.1f} GB livres, nenhum modelo da lista roda sem travar "
                           f"{'o aparelho' if _eh_celular(medida) else 'o PC'} "
                           f"(o menor pede ~{modelos[0]['ram_gb'] + FOLGA_GB:.1f} GB). Feche outros programas "
                           "e peça de novo, ou continue nas nuvens.")}
    motivo = (f"Com {referencia:.1f} GB de RAM livre e {medida.get('nucleos') or '?'} núcleos, "
              f"o {escolhido['modelo']} ({escolhido['arquivo_gb']:.1f} GB no disco) cabe com folga — "
              f"{escolhido['nota']}.")
    if medida.get("cpu_pct") is not None:
        motivo += f" A CPU está em {medida['cpu_pct']:.0f}% agora."
    return {"ok": True, "modelo": escolhido["modelo"], "motivo": motivo, "arquivo_gb": escolhido["arquivo_gb"],
            "ram_gb": escolhido["ram_gb"]}


def formatar(medida: dict, rec: dict = None) -> str:
    celular = _eh_celular(medida)
    linhas = ["📱 Este aparelho:" if celular else "🖥 Este PC:"]
    if medida.get("ram_total_gb") is None:
        linhas.append("• Memória: não consegui medir" + ("" if celular else " (py -m pip install psutil)"))
    else:
        linhas.append(f"• Memória: {medida['ram_livre_gb']:.1f} GB livres de {medida['ram_total_gb']:.1f} GB")
    if medida.get("cpu_pct") is not None:
        linhas.append(f"• CPU: {medida['cpu_pct']:.0f}% em uso · {medida.get('nucleos') or '?'} núcleos")
    else:
        linhas.append(f"• CPU: {medida.get('nucleos') or '?'} núcleos")
    if medida.get("disco_livre_gb") is not None:
        linhas.append(f"• Disco: {medida['disco_livre_gb']:.1f} GB livres")
    if medida.get("bateria_pct") is not None:
        linhas.append(f"• Bateria: {medida['bateria_pct']:.0f}%" + (" (carregando)" if medida.get("carregando") else ""))
    if medida.get("temperatura_c") is not None:
        linhas.append(f"• Temperatura da bateria: {medida['temperatura_c']:.1f} °C")
    if rec:
        linhas.append("")
        linhas.append(("✅ Recomendo: " + rec["modelo"]) if rec.get("ok") else "⚠ Nenhum modelo recomendado.")
        linhas.append(rec["motivo"])
        if rec.get("ok"):
            linhas.append(f"Para usar: /local baixar {rec['modelo']} (≈{rec.get('arquivo_gb', 1):.1f} GB, "
                          "só baixa com a sua aprovação) e depois /local ligar.")
    return "\n".join(linhas)
