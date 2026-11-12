"""Запросы к Anthropic и Google: OAuth-ключи, аккаунты, лимиты Claude Code и Antigravity из облака."""
import datetime as dt
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import ide_local
from i18n import T
import storage


# Claude Code (OAuth-клиент самого Claude Code)
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# Google Antigravity (OAuth-клиент приложения Antigravity). В программе и в exe ключей нет — они берутся:
# 1) из переменных окружения ANTIGRAVITY_OAUTH_CLIENT_ID / _SECRET;
# 2) из зашифрованного файла keys.dat в папке данных (меню ⚙ → «OAuth-ключи Antigravity», `limits.py keys`);
# 3) при запуске из исходников — из local_keys.py (не хранится в git, образец: local_keys.example.py).
G_CLIENT_ID = G_CLIENT_SECRET = ""
G_KEYS_SOURCE = None  # откуда взяты ключи: "переменные окружения" | "зашифрованный файл" | "local_keys.py" | None


def load_google_keys():
    """Читает ключи OAuth (порядок — см. выше) в G_CLIENT_ID / G_CLIENT_SECRET; возвращает источник или None."""
    global G_CLIENT_ID, G_CLIENT_SECRET, G_KEYS_SOURCE
    found = ("", "", None)
    env = (os.environ.get("ANTIGRAVITY_OAUTH_CLIENT_ID"), os.environ.get("ANTIGRAVITY_OAUTH_CLIENT_SECRET"))
    if all(env):
        found = (env[0], env[1], "переменные окружения")
    if not found[2]:
        try:
            with open(storage.KEYS_FILE, "rb") as f:
                d = json.loads(storage.unprotect_bytes(f.read()).decode("utf-8"))
            if d.get("client_id") and d.get("client_secret"):
                found = (d["client_id"], d["client_secret"], "зашифрованный файл")
        except Exception:
            pass
    if not found[2] and not getattr(sys, "frozen", False):
        try:  # имя модуля строкой, чтобы PyInstaller не вшил файл с ключами в exe
            import importlib
            mod = importlib.import_module("local_keys")
            if getattr(mod, "G_CLIENT_ID", "") and getattr(mod, "G_CLIENT_SECRET", ""):
                found = (mod.G_CLIENT_ID, mod.G_CLIENT_SECRET, "local_keys.py")
        except Exception:
            pass
    G_CLIENT_ID, G_CLIENT_SECRET, G_KEYS_SOURCE = found
    return G_KEYS_SOURCE


def set_google_keys(client_id, client_secret):
    """Сохраняет ключи OAuth в keys.dat (DPAPI) и сразу начинает ими пользоваться."""
    client_id, client_secret = (client_id or "").strip(), (client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValueError("нужны оба значения: id и secret")
    os.makedirs(storage.APPDIR, exist_ok=True)
    raw = json.dumps({"client_id": client_id, "client_secret": client_secret}).encode("utf-8")
    tmp = storage.KEYS_FILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(storage.protect_bytes(raw))
    os.replace(tmp, storage.KEYS_FILE)
    if os.name != "nt":
        os.chmod(storage.KEYS_FILE, 0o600)
    return load_google_keys()


load_google_keys()
G_SCOPES = "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email"
G_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
G_TOKEN_URL = "https://oauth2.googleapis.com/token"
CC_BASE = "https://daily-cloudcode-pa.googleapis.com"  # этот же адрес использует IDE
CC_META = {"ideType": "ANTIGRAVITY", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}
# Облако отдаёт группу «Gemini Models» (неделя + 5 часов) только клиенту, назвавшемуся свежей версией IDE;
# безымянному "antigravity" — лишь «Claude and GPT models». Порядок попыток — cc_user_agents():
# переменная окружения ANTIGRAVITY_USER_AGENT либо версия установленной IDE (если она новее CC_IDE_VERSION_MIN),
# затем CC_IDE_VERSION_MIN, затем безымянный. Переход к следующему — только при отказе HTTP 403.
CC_IDE_VERSION_MIN = (2, 24, 0)    # с этой версией группа Gemini приходила 12.11.2026
CC_USER_AGENT_OLD = "antigravity"  # запасной: принимается всегда, но без лимитов Gemini в сводке
_CC_AGENTS = None                  # список заголовков (кэш)
_CC_AGENT_OK = 0                   # номер заголовка, который облако приняло в прошлый раз

TIMEOUT = 25


# ---------------------------------------------------------------- http
def _need_google_keys():
    if not (G_CLIENT_ID and G_CLIENT_SECRET):
        raise RuntimeError(T("нет OAuth-ключей Antigravity — задайте их: python limits.py keys или переменные окружения (см. README)"))


def http_json(url, data=None, headers=None, form=False, method=None):
    headers = dict(headers or {})
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            body = json.dumps(data).encode()
            headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {txt}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(T("сеть: {reason}", reason=e.reason)) from None


# ================================================================ Claude Code
def claude_fetch():
    if not os.path.exists(storage.CLAUDE_CREDS):
        raise RuntimeError(T("нет ~/.claude/.credentials.json — войдите в Claude Code командой `claude`"))
    with open(storage.CLAUDE_CREDS, encoding="utf-8") as f:
        creds = json.load(f)
    o = creds.get("claudeAiOauth") or {}
    if not o.get("accessToken"):
        raise RuntimeError(T("Claude Code не залогинен через подписку (claudeAiOauth нет)"))

    # токен истёк (или истечёт в ближайшую минуту) — обновляем и сохраняем обратно,
    # так же, как это делает сам Claude Code
    if o.get("expiresAt", 0) < (time.time() + 60) * 1000:
        d = http_json(CLAUDE_TOKEN_URL, {"grant_type": "refresh_token",
                                         "refresh_token": o["refreshToken"],
                                         "client_id": CLAUDE_CLIENT_ID},
                      headers={"User-Agent": "claude-code/2.0"})
        # перечитываем файл прямо перед записью, чтобы не затереть чужие изменения
        with open(storage.CLAUDE_CREDS, encoding="utf-8") as f:
            creds = json.load(f)
        o = creds.setdefault("claudeAiOauth", {})
        o["accessToken"] = d["access_token"]
        if d.get("refresh_token"):
            o["refreshToken"] = d["refresh_token"]
        o["expiresAt"] = int((time.time() + d.get("expires_in", 3600)) * 1000)
        storage.atomic_write_json(storage.CLAUDE_CREDS, creds)

    u = http_json(CLAUDE_USAGE_URL, headers={
        "Authorization": "Bearer " + o["accessToken"],
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-code/2.0",
    })
    rows = []
    names = {"seven_day": "Неделя", "seven_day_opus": "Неделя Opus",
             "seven_day_sonnet": "Неделя Sonnet", "five_hour": "5 часов"}
    for key, label in names.items():
        v = u.get(key)
        if isinstance(v, dict) and v.get("utilization") is not None:
            rows.append({"name": label, "used": float(v["utilization"]), "resets_at": v.get("resets_at")})
    ex = u.get("extra_usage") or {}
    return {"plan": o.get("subscriptionType", "?"), "limits": rows,
            "extra_usage": ex.get("is_enabled", False)}


# ================================================================ Antigravity
def load_accounts():
    """Аккаунты Google с расшифрованными refresh_token. Файл прежней версии (токены открытым текстом)
    читается как есть и тут же пересохраняется зашифрованным."""
    if not os.path.exists(storage.ACCOUNTS_FILE):
        return []
    with open(storage.ACCOUNTS_FILE, encoding="utf-8") as f:
        accs = json.load(f).get("accounts", [])
    plain = False
    for a in accs:
        t = a.get("refresh_token")
        if isinstance(t, str) and t.startswith(storage._DPAPI_PREFIX):
            try:
                a["refresh_token"] = storage.unprotect_text(t)
            except Exception:  # файл перенесён с другого компьютера или из другой учётной записи
                a["refresh_token"], a["_stored"] = "", t
        elif t:
            plain = True
    if plain and os.name == "nt":
        try:
            save_accounts(accs)
        except Exception:
            pass
    return accs


def save_accounts(accs):
    """Записывает аккаунты; refresh_token шифруется DPAPI (на Windows)."""
    out = []
    for a in accs:
        b = {k: v for k, v in a.items() if not k.startswith("_")}
        # не расшифрованный токен сохраняем в прежнем виде, а не затираем пустым
        b["refresh_token"] = a["_stored"] if a.get("_stored") and not a.get("refresh_token") \
            else storage.protect_text(a.get("refresh_token"))
        out.append(b)
    storage.atomic_write_json(storage.ACCOUNTS_FILE, {"accounts": out})
    if os.name != "nt":
        os.chmod(storage.ACCOUNTS_FILE, 0o600)


def protect_stored_secrets():
    """Перевод данных прежних версий в зашифрованный вид: accounts.json и копии учётных данных IDE.
    Вызывается при запуске; ничего не делает, если всё уже зашифровано. Возвращает число перешифрованных файлов."""
    if os.name != "nt":
        return 0
    done = 0
    try:
        with open(storage.ACCOUNTS_FILE, encoding="utf-8") as f:
            was_plain = any(a.get("refresh_token") and not str(a["refresh_token"]).startswith(storage._DPAPI_PREFIX)
                            for a in json.load(f).get("accounts", []))
        if was_plain:
            load_accounts()
            done += 1
    except Exception:
        pass
    try:
        names = os.listdir(storage.IDE_BACKUP_DIR)
    except OSError:
        names = []
    for n in names:
        if not n.startswith(("gemini_antigravity_", "app_storage_")):
            continue
        path = os.path.join(storage.IDE_BACKUP_DIR, n)
        try:
            with open(path, "rb") as f:
                data = f.read()
            if data and not data.startswith(storage._DPAPI_MAGIC):
                with open(path + ".tmp", "wb") as f:
                    f.write(storage.protect_bytes(data))
                os.replace(path + ".tmp", path)
                done += 1
        except Exception:
            pass
    return done


def g_access_token(acc):
    _need_google_keys()
    if not acc.get("refresh_token"):
        raise RuntimeError(T("токен аккаунта не расшифрован (данные с другого компьютера?) — добавьте аккаунт заново"))
    d = http_json(G_TOKEN_URL, {"client_id": G_CLIENT_ID, "client_secret": G_CLIENT_SECRET,
                                "refresh_token": acc["refresh_token"], "grant_type": "refresh_token"},
                  form=True)
    return d["access_token"]


def cc_user_agents():
    """Заголовки User-Agent для облака Antigravity в порядке попыток."""
    global _CC_AGENTS
    if _CC_AGENTS is None:
        own = os.environ.get("ANTIGRAVITY_USER_AGENT")
        if own:
            agents = [own]
        else:
            agents = ["antigravity/hub/%d.%d.%d" % CC_IDE_VERSION_MIN]
            v = ide_local.ide_version()
            if v and v > CC_IDE_VERSION_MIN:
                agents.insert(0, "antigravity/hub/%d.%d.%d" % v)
        if CC_USER_AGENT_OLD not in agents:
            agents.append(CC_USER_AGENT_OLD)
        _CC_AGENTS = agents
    return _CC_AGENTS


def cc_post(path, token, body):
    """Запрос к облаку Antigravity. Если версию клиента отвергли (HTTP 403) — повтор со следующим заголовком
    из cc_user_agents(); принятый заголовок запоминается до конца работы программы."""
    global _CC_AGENT_OK
    agents = cc_user_agents()
    start = _CC_AGENT_OK if _CC_AGENT_OK < len(agents) else 0
    for i in range(start, len(agents)):
        try:
            res = http_json(CC_BASE + path, body,
                            headers={"Authorization": "Bearer " + token, "User-Agent": agents[i]})
            _CC_AGENT_OK = i
            return res
        except RuntimeError as e:
            if not str(e).startswith("HTTP 403") or i == len(agents) - 1:
                raise


def extract_project(resp):
    p = resp.get("cloudaicompanionProject")
    if isinstance(p, dict):
        p = p.get("id")
    return p


# Показываем только лимиты моделей Gemini.
# Источники, по убыванию точности:
#   1) локальный сервер запущенной IDE Antigravity (для аккаунта, вошедшего в IDE) —
#      отдельно недельный и 5-часовой лимит, ровно как в настройках Antigravity;
#   2) облако daily-cloudcode-pa: сводка retrieveUserQuotaSummary (если в ней есть группа Gemini);
#   3) облако: retrieveUserQuota — один действующий (самый строгий) лимит Gemini.
WIN_NAMES = {"weekly": "Неделя", "5h": "5 часов"}


def _summary_rows(summary):
    """Строки лимитов группы Gemini из ответа retrieveUserQuotaSummary."""
    for g in (summary or {}).get("groups", []):
        if "gemini" not in (g.get("displayName", "") + g.get("description", "")).lower():
            continue
        rows = []
        for b in g.get("buckets", []):
            rem = b.get("remainingFraction")
            rem = 1.0 if rem is None else float(rem)
            rows.append({"name": WIN_NAMES.get(b.get("window"), b.get("displayName", "?")),
                         "used": round((1 - rem) * 100, 1), "resets_at": b.get("resetTime")})
        order = {"Неделя": 0, "5 часов": 1}
        return sorted(rows, key=lambda r: order.get(r["name"], 9))
    return None


def _bucket_rows(quota):
    """Один действующий лимит Gemini из retrieveUserQuota."""
    gem = [b for b in (quota or {}).get("buckets", [])
           if b.get("modelId", "").startswith("gemini") and "image" not in b.get("modelId", "")]
    if not gem:
        return []
    b = min(gem, key=lambda x: float(x.get("remainingFraction", 1)))
    rem = float(b.get("remainingFraction", 1))
    name = "Действующий лимит"
    try:
        t = dt.datetime.fromisoformat(b["resetTime"].replace("Z", "+00:00"))
        hours = (t - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
        name = "Неделя" if hours > 5.2 else "5 часов"
    except Exception:
        pass
    return [{"name": name, "used": round((1 - rem) * 100, 1), "resets_at": b.get("resetTime")}]


def ag_fetch(acc, all_models=False, local=None):
    if local and acc["email"].lower() in local:
        li = local[acc["email"].lower()]
        return {"plan": li["plan"], "models": li["rows"], "credits": None,
                "source": "данные IDE Antigravity"}
    token = g_access_token(acc)
    lca = cc_post("/v1internal:loadCodeAssist", token, {"metadata": CC_META})
    project = extract_project(lca) or acc.get("project")
    body = {"project": project} if project else {}
    plan = (lca.get("paidTier") or {}).get("name") or (lca.get("currentTier") or {}).get("name") or ""
    rows, source = None, "облако"
    try:
        rows = _summary_rows(cc_post("/v1internal:retrieveUserQuotaSummary", token, body))
    except Exception:
        pass
    if not rows:
        rows = _bucket_rows(cc_post("/v1internal:retrieveUserQuota", token, body))
        source = "облако · действующий лимит"
    return {"plan": plan, "models": rows, "credits": None, "source": source}


def ag_login():
    """OAuth-вход через браузер с приёмом кода на 127.0.0.1."""
    _need_google_keys()
    state = secrets.token_urlsafe(16)
    result = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in qs or "error" in qs:
                result.update({k: v[0] for k, v in qs.items()})
                ok = "code" in qs and qs.get("state", [""])[0] == state
                msg = T("Готово, можно закрыть вкладку.") if ok else T("Ошибка входа, см. консоль.")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2>".encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}/callback"
    url = G_AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": G_CLIENT_ID, "redirect_uri": redirect, "response_type": "code",
        "scope": G_SCOPES, "access_type": "offline", "prompt": "consent select_account",
        "state": state})
    print("Открываю браузер для входа в Google. Если не открылся — откройте ссылку вручную:\n")
    print(url + "\n")
    webbrowser.open(url)
    th = threading.Thread(target=lambda: [srv.handle_request() for _ in range(20) if not result], daemon=True)
    th.start()
    th.join(timeout=300)
    srv.server_close()
    if result.get("state") != state or "code" not in result:
        raise RuntimeError(T("вход не завершён: {reason}", reason=result.get("error") or T("таймаут")))

    tok = http_json(G_TOKEN_URL, {"code": result["code"], "client_id": G_CLIENT_ID,
                                  "client_secret": G_CLIENT_SECRET, "redirect_uri": redirect,
                                  "grant_type": "authorization_code"}, form=True)
    if not tok.get("refresh_token"):
        raise RuntimeError(T("Google не выдал refresh_token — попробуйте ещё раз"))
    info = http_json("https://www.googleapis.com/oauth2/v2/userinfo",
                     headers={"Authorization": "Bearer " + tok["access_token"]})
    email = info.get("email", "unknown")
    project = None
    try:
        project = extract_project(cc_post("/v1internal:loadCodeAssist", tok["access_token"],
                                          {"metadata": CC_META}))
    except Exception:
        pass
    return {"email": email, "refresh_token": tok["refresh_token"], "project": project}
