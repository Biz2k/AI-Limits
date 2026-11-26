"""Смена аккаунта Codex (1.5.2): вход выбранного профиля ChatGPT подставляется в ~/.codex/auth.json.

Порядок, как у смены аккаунта IDE: копия нынешнего входа (зашифрована) → закрыть приложение Codex (оно держит вход
в памяти и при обновлении токена записало бы прежний аккаунт обратно) → сохранить нынешний вход в профиль его
аккаунта (если аккаунт не добавлен — профиль создаётся: на него можно вернуться) → записать вход профиля → проверить
→ запустить приложение снова, если оно было запущено. Сбой после записи — прежний вход возвращается из копии.
Codex, запущенный в терминале (codex.exe не из пакета приложения), не закрываем: просим закрыть самого.
"""
import json
import os
import subprocess
import time
import uuid

import accounts
import storage
import winapi
from i18n import T

APP_PKG = "\\OpenAI.Codex_"   # приложение Codex из Microsoft Store: ...\WindowsApps\OpenAI.Codex_<версия>_x64__<id>\
KEEP_BACKUPS = 5


def backups_dir():
    return os.path.join(storage.APPDIR, "codex_backups")


def _procs():
    """[(pid, имя, путь)] процессов Codex: приложения из пакета и консольной codex.exe."""
    out = []
    for pid, name in winapi._win_processes():
        low = name.lower()
        if low not in ("chatgpt.exe", "codex.exe") and not low.startswith("codex-"):
            continue
        path = winapi._win_process_text(pid, "path") or ""
        if APP_PKG.lower() in path.lower() or low == "codex.exe":
            out.append((pid, low, path))
    return out


def app_pids():
    return [pid for pid, _, path in _procs() if APP_PKG.lower() in path.lower()]


def cli_running():
    """Запущена ли консольная Codex (codex.exe не из пакета приложения)."""
    return any(name == "codex.exe" and APP_PKG.lower() not in path.lower() for _, name, path in _procs())


def app_family():
    """Имя семейства пакета приложения Codex (OpenAI.Codex_<id>) по пути запущенного процесса или None."""
    for _, _, path in _procs():
        i = path.lower().find(APP_PKG.lower())
        if i >= 0:
            folder = path[i + 1:].split("\\")[0]          # OpenAI.Codex_26.1111.9265.0_x64__2p2nqsd0c76g0
            return folder.split("_")[0] + "_" + folder.rsplit("__", 1)[-1]
    return None


def stop_app(timeout=10):
    """Закрывает приложение Codex: сначала штатно (taskkill без /F), без окон — оставшееся принудительно.
    Окно не закрылось за timeout секунд — RuntimeError, вход ещё не тронут."""
    pids = app_pids()
    if not pids:
        return
    for pid in pids:
        try:
            winapi._run_hidden(["taskkill", "/PID", str(pid)], timeout=10)
        except Exception:
            pass
    deadline = time.time() + timeout
    while True:
        left = set(app_pids())
        if not left:
            break
        if not (left & winapi._win_window_pids()):  # окон нет — остались фоновые процессы
            for pid in left:
                try:
                    winapi._run_hidden(["taskkill", "/F", "/T", "/PID", str(pid)], timeout=10)
                except Exception:
                    pass
            time.sleep(0.7)
            if app_pids():
                raise RuntimeError(T("Codex не закрылся за {timeout} с", timeout=timeout))
            break
        if time.time() > deadline:
            raise RuntimeError(T("Codex не закрылся за {timeout} с", timeout=timeout))
        time.sleep(0.5)
    time.sleep(0.8)


def start_app(family):
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{family}!App"], creationflags=0x08000000)


def _read_auth():
    try:
        with open(storage.CODEX_AUTH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _write_auth(raw):
    os.makedirs(os.path.dirname(storage.CODEX_AUTH), exist_ok=True)
    tmp = storage.CODEX_AUTH + ".ai-limits.tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, storage.CODEX_AUTH)


def backup(raw):
    """Зашифрованная копия входа Codex; хранятся KEEP_BACKUPS последних."""
    d = backups_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, time.strftime("auth_%Y%m%d_%H%M%S.dat"))
    with open(path, "wb") as f:
        f.write(storage.protect_bytes(raw))
    for old in sorted(n for n in os.listdir(d) if n.startswith("auth_"))[:-KEEP_BACKUPS]:
        os.remove(os.path.join(d, old))
    return path


def _keep_current(raw):
    """Нынешний вход Codex — в профиль его аккаунта (свежие токены). Профиля нет — создаётся. Возвращает
    (профиль, создан ли)."""
    data = json.loads(raw.decode("utf-8"))
    email, account_id = accounts.codex_identity(data)
    if not email:
        return None, False
    key = accounts.ident("chatgpt", email)
    for p in accounts.load_profiles():
        if p["kind"] == "chatgpt" and accounts.ident("chatgpt", p["email"]) == key:
            accounts.write_secret(p, data)
            return p, False
    p = {"kind": "chatgpt", "dir": f"chatgpt-{uuid.uuid4().hex[:8]}", "email": email, "account_id": account_id}
    os.makedirs(os.path.join(accounts.profiles_dir(), p["dir"]), exist_ok=True)
    accounts.write_secret(p, data)
    accounts.save_profiles(accounts.load_profiles() + [p])
    return p, True


def adopt_current(ignored=()):
    """Сохраняет текущий вход Codex в профиль AI Limits, если его там ещё нет и он не в ignored.
    Возвращает созданный профиль (dict) или None."""
    raw = _read_auth()
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    email, _ = accounts.codex_identity(data)
    if not email or not (data.get("tokens") or {}).get("access_token"):
        return None
    key = accounts.ident("chatgpt", email)
    if key in {(x or "").lower() for x in (ignored or ())}:
        return None
    if any(p["kind"] == "chatgpt" and accounts.ident("chatgpt", p["email"]) == key for p in accounts.load_profiles()):
        return None
    p, created = _keep_current(raw)
    return p if created else None


def switch(profile, on_status=lambda s: None):
    """Сделать профиль ChatGPT аккаунтом Codex. Возвращает {"email": новый, "kept": профиль прежнего аккаунта,
    "created": создан ли он сейчас, "restarted": перезапущено ли приложение}."""
    target = accounts.read_secret(profile)
    t_email = accounts.codex_identity(target)[0]
    if not t_email:
        raise RuntimeError(T("во входе профиля нет аккаунта ChatGPT — добавьте его заново"))
    before = _read_auth()
    if before and accounts.codex_identity(json.loads(before.decode("utf-8")))[0] == t_email:
        return {"email": t_email, "kept": None, "created": False, "restarted": False}
    if cli_running():
        raise RuntimeError(T("Codex запущен в терминале — закройте его и повторите"))
    if before:
        backup(before)
    family = app_family()
    if family:
        on_status(T("Codex: закрываю приложение…"))
        stop_app()
    now = _read_auth()  # приложение могло обновить токен, пока закрывалось
    kept, created = _keep_current(now) if now else (None, False)
    try:
        _write_auth(json.dumps(target, indent=2).encode("utf-8"))
        got = accounts.codex_identity(json.loads(_read_auth().decode("utf-8")))[0]
        if got != t_email:
            raise RuntimeError(T("в Codex записался {now}, а не {email}", now=got or T("никто"), email=t_email))
    except Exception:
        if now:
            _write_auth(now)
        if family:
            start_app(family)
        raise
    if family:
        on_status(T("Codex: запускаю приложение…"))
        start_app(family)
    return {"email": t_email, "kept": kept, "created": created, "restarted": bool(family)}
