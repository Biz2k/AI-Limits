"""Папка данных AI Limits: пути, шифрование DPAPI, журнал ошибок, запись файлов."""
import datetime as dt
import json
import os
import sys
import threading

from version import __version__


# ---------------------------------------------------------------- пути / конфиг
APPDIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), "ai-limits")
ACCOUNTS_FILE = os.path.join(APPDIR, "accounts.json")
CLAUDE_CREDS = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
ANTIGRAVITY_APPDATA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), "Antigravity")
IDE_BACKUP_DIR = os.path.join(APPDIR, "ide_backups")
APP_LOG = os.path.join(APPDIR, "app.log")  # необработанные ошибки
APP_LOG_MAX = 512 * 1024                   # больше — файл уходит в app.log.1 (хранится один старый)


KEYS_FILE = os.path.join(APPDIR, "keys.dat")  # OAuth-ключи Antigravity, зашифрованы DPAPI
_DPAPI_MAGIC = b"AILIMITS-DPAPI-1\n"         # начало зашифрованного файла
_DPAPI_PREFIX = "dpapi:"                      # начало зашифрованной строки внутри JSON
_DPAPI_ENTROPY = b"ai-limits"


def _dpapi(data, protect):
    """Шифрование Windows DPAPI: расшифровать может только та же учётная запись Windows на этом компьютере."""
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw):
        buf = ctypes.create_string_buffer(raw, len(raw))
        return BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.POINTER(BLOB), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
    fn.restype = wintypes.BOOL
    src, _keep1 = blob(data)
    ent, _keep2 = blob(_DPAPI_ENTROPY)
    out = BLOB()
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out)):  # 0x1 — без окон
        raise RuntimeError("DPAPI: не удалось " + ("зашифровать" if protect else "расшифровать") +
                           f" (код {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect_bytes(data):
    """Содержимое файла -> зашифрованное (с меткой в начале). Не на Windows — без изменений."""
    if os.name != "nt" or data.startswith(_DPAPI_MAGIC):
        return data
    return _DPAPI_MAGIC + _dpapi(data, True)


def unprotect_bytes(data):
    """Обратно; файл без метки (записан прежней версией) возвращается как есть."""
    return _dpapi(data[len(_DPAPI_MAGIC):], False) if data.startswith(_DPAPI_MAGIC) else data


def protect_text(text):
    """Строка (токен) -> «dpapi:…» для хранения в JSON. Не на Windows — без изменений."""
    if os.name != "nt" or not text or text.startswith(_DPAPI_PREFIX):
        return text
    import base64
    return _DPAPI_PREFIX + base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode("ascii")


def unprotect_text(text):
    if not isinstance(text, str) or not text.startswith(_DPAPI_PREFIX):
        return text
    import base64
    return _dpapi(base64.b64decode(text[len(_DPAPI_PREFIX):]), False).decode("utf-8")


def _mask_secrets(text):
    """Скрывает в тексте всё похожее на токены и ключи."""
    import re
    return re.sub(r"ya29\.[\w.-]{10,}|1//[\w-]{10,}|GOCSPX-[\w-]+|sk-ant-[\w-]{10,}|eyJ[\w-]{10,}\.[\w.-]+",
                  "<скрыто>", text)


def log_exception(where, exc_type, exc, tb):
    """Дописывает необработанную ошибку в app.log (версия, время, место, трассировка)."""
    import traceback
    try:
        os.makedirs(APPDIR, exist_ok=True)
        if os.path.exists(APP_LOG) and os.path.getsize(APP_LOG) > APP_LOG_MAX:
            os.replace(APP_LOG, APP_LOG + ".1")
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        with open(APP_LOG, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  v{__version__}  {where}\n{_mask_secrets(text)}\n")
    except Exception:
        pass


def install_error_log():
    """Необработанные ошибки главного потока и фоновых потоков — в app.log (в exe без консоли они иначе пропадают)."""
    def main_hook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            log_exception("главный поток", exc_type, exc, tb)
        sys.__excepthook__(exc_type, exc, tb)

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread else "?"
            log_exception(f"поток {name}", args.exc_type, args.exc_value, args.exc_traceback)
    sys.excepthook = main_hook
    threading.excepthook = thread_hook


def _migrate_from_store_python():
    """Python из Microsoft Store тайно перенаправляет %APPDATA% в папку своего пакета.
    exe-версия (не из Store) видит настоящий %APPDATA% — переносим данные оттуда один раз."""
    if os.name != "nt" or os.path.exists(os.path.join(APPDIR, "accounts.json")):
        return
    import glob
    import shutil
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages",
                           "PythonSoftwareFoundation.Python.*", "LocalCache", "Roaming", "ai-limits")
    for src in sorted(glob.glob(pattern), reverse=True):
        if os.path.exists(os.path.join(src, "accounts.json")):
            os.makedirs(APPDIR, exist_ok=True)
            for name in ("accounts.json", "cache.json", "gui.json", "keys.dat"):
                if os.path.exists(os.path.join(src, name)) and not os.path.exists(os.path.join(APPDIR, name)):
                    shutil.copy2(os.path.join(src, name), os.path.join(APPDIR, name))
            return


try:
    _migrate_from_store_python()
except Exception:
    pass


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
