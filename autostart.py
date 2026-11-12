"""Автозапуск AI Limits вместе с Windows (раздел реестра Run текущего пользователя)."""
import os
import sys

GUI_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "limits_gui.pyw")  # главный файл окна


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "AI Limits"


def autostart_command():
    """Команда автозапуска этой копии программы. С ключом --autostart окно прячется в трей,
    только если включено «Сворачивать в трей при закрытии»."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --autostart'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), os.path.basename(exe).lower().replace("python", "pythonw", 1))
    if "pythonw" not in os.path.basename(exe).lower() and os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{GUI_SCRIPT}" --autostart'


def autostart_enabled(name=RUN_NAME):
    """Есть ли запись автозапуска в реестре (HKCU\\…\\Run)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, name)[0])
    except Exception:
        return False


def set_autostart(on, name=RUN_NAME):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass
