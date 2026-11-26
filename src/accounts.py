"""Аккаунты (версия 1.5.0): свои профили Claude и ChatGPT, имена аккаунтов в AI Limits, аккаунты программ.

Профиль — отдельная папка %APPDATA%\\ai-limits\\profiles\\<тип>-<id>, в которую входит сама программа:
`claude auth login` (CLAUDE_CONFIG_DIR) или `codex login` (CODEX_HOME). После входа файл с токенами
программы шифруется DPAPI (creds.dat), открытая копия удаляется — как остальные токены AI Limits.
Список профилей — profiles.json (без токенов). Имена — в настройках окна (gui.json, "names": {ключ: имя}).

Ключ аккаунта (он же ключ истории): Google — email в нижнем регистре (как в прежних версиях),
Claude — "claude:<email>", ChatGPT — "codex:<email>".
"""
import base64
import glob
import json
import os
import shutil
import subprocess
import threading
import time
import uuid

import storage
from i18n import T

KINDS = ("claude", "chatgpt", "google")
SERVICE = {"claude": "Claude", "chatgpt": "Codex", "google": "Google"}          # приставка к имени при совпадении
PRODUCT = {"claude": "Claude Code", "chatgpt": "Codex", "google": "Antigravity"}  # плитка программы без имени
IDE_KEY = {"claude": "claude", "chatgpt": "codex", "google": "antigravity"}      # ключ плитки программы
NAME_MAX = 32
LOGIN_TIMEOUT = 600  # с: сколько ждать входа в окне программы


def ident(kind, email):
    """Ключ аккаунта: и для плитки, и для истории."""
    e = (email or "").strip().lower()
    return e if kind == "google" else ("codex:" if kind == "chatgpt" else "claude:") + e


# ---------------------------------------------------------------- имена
def _norm(name):
    return " ".join((name or "").split()).casefold()


def reserved_names():
    return {_norm(n) for n in PRODUCT.values()}


def name_error(name, taken):
    """Ошибка нового имени или None. taken — имена, уже занятые другими аккаунтами."""
    name = " ".join((name or "").split())
    if not name:
        return T("Имя не может быть пустым")
    if len(name) > NAME_MAX:
        return T("Имя длиннее {n} символов", n=NAME_MAX)
    if _norm(name) in {_norm(t) for t in taken} | reserved_names():
        return T("Имя «{name}» уже занято", name=name)
    return None


def suggest_name(kind, email, taken):
    """Имя по умолчанию: часть email до «@»; если занято — с приставкой сервиса («Codex alex»), затем с номером."""
    local = (email or "").split("@")[0].strip() or SERVICE[kind]
    local = local[:NAME_MAX]
    cands = [local, f"{SERVICE[kind]} {local}"[:NAME_MAX]]
    cands += [f"{SERVICE[kind]} {local} {i}"[:NAME_MAX] for i in range(2, 50)]
    return next(c for c in cands if not name_error(c, taken))


def suggest_product_name(kind, taken):
    """Имя по умолчанию для автоматически сохранённого аккаунта программы:
    Antigravity / Claude Code / Codex; если занято — Antigravity1, Antigravity2 и т.д."""
    base = PRODUCT[kind]
    used = {_norm(t) for t in taken}
    if _norm(base) not in used:
        return base
    for i in range(1, 1000):
        cand = f"{base}{i}"[:NAME_MAX]
        if _norm(cand) not in used:
            return cand
    return f"{base}{uuid.uuid4().hex[:4]}"[:NAME_MAX]


# ---------------------------------------------------------------- профили
def profiles_dir():
    return os.path.join(storage.APPDIR, "profiles")


def profiles_file():
    return os.path.join(storage.APPDIR, "profiles.json")


def load_profiles():
    """[{"kind", "email", "dir", ...}] — свои профили Claude и ChatGPT."""
    try:
        with open(profiles_file(), encoding="utf-8") as f:
            return [p for p in json.load(f).get("profiles", []) if p.get("kind") in ("claude", "chatgpt")]
    except (OSError, ValueError):
        return []


def save_profiles(profiles):
    storage.atomic_write_json(profiles_file(), {"profiles": profiles})


def profile_path(p, name):
    return os.path.join(profiles_dir(), p["dir"], name)


def remove_profile(p):
    """Удаляет профиль из списка и его папку."""
    save_profiles([q for q in load_profiles() if q.get("dir") != p.get("dir")])
    shutil.rmtree(os.path.join(profiles_dir(), p["dir"]), ignore_errors=True)


def read_secret(p):
    """Расшифрованный файл входа профиля (dict)."""
    with open(profile_path(p, "creds.dat"), "rb") as f:
        return json.loads(storage.unprotect_bytes(f.read()).decode("utf-8"))


def write_secret(p, data):
    path = profile_path(p, "creds.dat")
    with open(path + ".tmp", "wb") as f:
        f.write(storage.protect_bytes(json.dumps(data).encode("utf-8")))
    os.replace(path + ".tmp", path)


# ---------------------------------------------------------------- аккаунты программ
def jwt_claims(token):
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except Exception:
        return {}


def codex_identity(auth):
    """(email, account_id) из auth.json Codex."""
    t = (auth or {}).get("tokens") or {}
    return jwt_claims(t.get("id_token") or "").get("email"), t.get("account_id")


def claude_ide_email():
    """Email аккаунта, под которым вошёл Claude Code (~/.claude.json → oauthAccount)."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".claude.json"), encoding="utf-8") as f:
            return (json.load(f).get("oauthAccount") or {}).get("emailAddress")
    except (OSError, ValueError):
        return None


def codex_ide_email():
    try:
        with open(storage.CODEX_AUTH, encoding="utf-8") as f:
            return codex_identity(json.load(f))[0]
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- вход через программу
def find_cli(kind):
    """Путь к claude.exe / codex.exe или None."""
    name = "claude" if kind == "claude" else "codex"
    found = shutil.which(name)
    if found:
        return found
    home, local = os.path.expanduser("~"), os.environ.get("LOCALAPPDATA", "")
    if kind == "claude":
        cands = [os.path.join(home, ".local", "bin", "claude.exe")]
        cands += sorted(glob.glob(os.path.join(local, "Claude-Data", "*", "claude-code", "*", "*", "claude.exe")),
                        key=os.path.getmtime, reverse=True)
    else:
        cands = [os.path.join(local, "Programs", "OpenAI", "Codex", "bin", "codex.exe")]
    return next((c for c in cands if os.path.exists(c)), None)


def start_login(kind):
    """Создаёт папку нового профиля и запускает вход программы **без окна консоли**: программа сама открывает
    страницу входа в браузере по умолчанию и ждёт ответа на localhost. Вывод программы собирается в p["_out"]
    (для сообщения об ошибке). Возвращает профиль (dict)."""
    cli = find_cli(kind)
    if not cli:
        raise RuntimeError(T("Не найден Claude Code (claude.exe) — установите его") if kind == "claude"
                           else T("Не найден Codex (codex.exe) — установите его"))
    p = {"kind": kind, "dir": f"{kind}-{uuid.uuid4().hex[:8]}"}
    home = os.path.join(profiles_dir(), p["dir"])
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ)
    if kind == "claude":
        env["CLAUDE_CONFIG_DIR"] = home
        args = [cli, "auth", "login", "--claudeai"]
    else:
        env["CODEX_HOME"] = home
        args = [cli, "login"]
    proc = subprocess.Popen(args, env=env, cwd=home, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=0x08000000)  # CREATE_NO_WINDOW
    p["_proc"], p["_out"] = proc, []
    threading.Thread(target=lambda: p["_out"].extend(
        line.decode("utf-8", errors="replace").strip() for line in iter(proc.stdout.readline, b"")), daemon=True).start()
    return p


def cancel_login(p):
    """Отменить незавершённый вход: остановить программу и убрать папку профиля."""
    p["_cancel"] = True
    proc = p.get("_proc")
    if proc is not None and proc.poll() is None:
        proc.kill()


def _login_error(p):
    """Почему программа завершилась без входа: последняя содержательная строка её вывода (без адресов)."""
    for line in reversed(p.get("_out") or []):
        if line and "http" not in line and len(line) < 200:
            return line
    return T("программа входа завершилась без входа")


def _claude_status(p):
    """`claude auth status --json` для папки профиля (email, orgId, subscriptionType)."""
    cli = find_cli("claude")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=os.path.join(profiles_dir(), p["dir"]))
    out = subprocess.run([cli, "auth", "status", "--json"], env=env, capture_output=True, timeout=60,
                         creationflags=0x08000000).stdout  # CREATE_NO_WINDOW
    return json.loads(out.decode("utf-8", errors="replace") or "{}")


def finish_login(p, timeout=LOGIN_TIMEOUT, cancelled=None):
    """Ждёт, пока программа запишет вход в папку профиля; затем шифрует его и заполняет email.
    Возвращает профиль без служебных полей. Вход отменён, программа завершилась без входа или время вышло —
    RuntimeError с понятной причиной."""
    cancelled = cancelled or (lambda: p.get("_cancel"))
    home = os.path.join(profiles_dir(), p["dir"])
    src = os.path.join(home, ".credentials.json" if p["kind"] == "claude" else "auth.json")
    deadline = time.time() + timeout
    proc, exited_at = p.get("_proc"), None
    while True:
        data = None
        try:
            with open(src, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        ok = data and ((data.get("claudeAiOauth") or {}).get("accessToken") if p["kind"] == "claude"
                       else ((data.get("tokens") or {}).get("access_token")))
        if ok:
            break
        if proc is not None and proc.poll() is not None:  # программа входа завершилась — даём файлу 5 с появиться
            exited_at = exited_at or time.time()
        reason = (T("отменено") if cancelled() else T("время ожидания вышло") if time.time() > deadline
                  else _login_error(p) if exited_at and time.time() - exited_at > 5 else None)
        if reason:
            if proc is not None and proc.poll() is None:
                proc.kill()
            shutil.rmtree(home, ignore_errors=True)
            raise RuntimeError(reason)
        time.sleep(1)
    if p["kind"] == "claude":
        st = {}
        try:
            with open(os.path.join(home, ".claude.json"), encoding="utf-8") as f:
                oa = json.load(f).get("oauthAccount") or {}
            st = {"email": oa.get("emailAddress"), "orgId": oa.get("organizationUuid")}
        except (OSError, ValueError):
            pass
        if not st.get("email"):
            st = _claude_status(p)
        p["email"], p["org"] = st.get("email"), st.get("orgId")
    else:
        p["email"], p["account_id"] = codex_identity(data)
    if not p.get("email"):
        shutil.rmtree(home, ignore_errors=True)
        raise RuntimeError(T("Не удалось узнать email вошедшего аккаунта"))
    write_secret(p, data)
    os.remove(src)  # открытую копию токенов не храним
    if proc and proc.poll() is None:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    return {k: v for k, v in p.items() if not k.startswith("_")}


def relogin_profile(old, new):
    """Повторный вход в добавленный профиль (1.5.4): вход из новой папки new (после finish_login) переносится
    в папку профиля old, данные профиля обновляются; папка new удаляется в любом случае. Вошли в другой
    аккаунт — RuntimeError, профиль old не тронут."""
    newdir = os.path.join(profiles_dir(), new["dir"])
    try:
        if ident(new["kind"], new["email"]) != ident(old["kind"], old["email"]):
            raise RuntimeError(T("в браузере выбран {got}, а не {email} — вход не обновлён",
                                 got=new["email"], email=old["email"]))
        olddir = os.path.join(profiles_dir(), old["dir"])
        os.makedirs(olddir, exist_ok=True)
        for name in os.listdir(newdir):
            dst = os.path.join(olddir, name)
            if os.path.isdir(dst) and not os.path.islink(dst):
                shutil.rmtree(dst, ignore_errors=True)
            os.replace(os.path.join(newdir, name), dst)
        profs = load_profiles()
        for q in profs:
            if q["dir"] == old["dir"]:
                q.update({k: v for k, v in new.items() if k != "dir" and not k.startswith("_")})
                old = q
        save_profiles(profs)
        return old
    finally:
        shutil.rmtree(newdir, ignore_errors=True)


def add_profile(p):
    """Сохраняет новый профиль. Тот же аккаунт уже добавлен — RuntimeError, новая папка удаляется."""
    profs = load_profiles()
    if any(q["kind"] == p["kind"] and ident(q["kind"], q["email"]) == ident(p["kind"], p["email"]) for q in profs):
        shutil.rmtree(os.path.join(profiles_dir(), p["dir"]), ignore_errors=True)
        raise RuntimeError(T("Аккаунт {email} уже добавлен", email=p["email"]))
    save_profiles(profs + [p])
    return p
