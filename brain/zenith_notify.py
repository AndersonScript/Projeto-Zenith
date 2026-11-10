"""
Zenith — Notificação nativa do Windows (quando uma ação longa termina).

Usa a biblioteca OPCIONAL `plyer` (pip install plyer). De propósito NÃO
abre PowerShell nem processo externo: num app que já sofre com falso
positivo de antivírus, lançar powershell.exe piora. Sem plyer instalado,
esta função só devolve False e o resto do Zenith segue normal — o Corpo
(Godot) ainda pisca o ícone na barra de tarefas como aviso alternativo.
Nunca levanta exceção.
"""


def notificar(titulo: str, mensagem: str, segundos: int = 8) -> bool:
    from brain import zenith_plataforma
    if zenith_plataforma.detectar() == "android":      # v1.11 — celular: a notificação é do Android (pela ponte)
        try:
            return bool(zenith_plataforma.obter().notificar(str(titulo)[:64], str(mensagem)[:240] or " "))
        except Exception:
            return False
    try:
        from plyer import notification
    except Exception:
        return False
    try:
        notification.notify(
            title=str(titulo)[:64],
            message=str(mensagem)[:240] or " ",
            app_name="Zenith",
            timeout=int(segundos),
        )
        return True
    except Exception as e:
        print(f"[Zenith/Notificação] não consegui notificar: {e}")
        return False
