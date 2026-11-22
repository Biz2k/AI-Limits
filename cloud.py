"""Запросы к Anthropic и Google: OAuth-ключи, аккаунты, лимиты Claude Code и Antigravity из облака."""
import datetime as dt
import html
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

import accounts
import ide_local
import i18n
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
_CC_AGENT_OK = {}                  # аккаунт → номер заголовка, который облако приняло ему в прошлый раз
_CC_VERIFY = set()                 # аккаунты, которым облако ответило 403 «Verify your account to continue»

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
        full = e.read().decode(errors="replace")
        msg = full[:300]
        try:  # {"error": {"message": …}} (Google, Anthropic) — в тексте ошибки только сообщение, без JSON (1.5.4)
            j = json.loads(full)
            if isinstance(j.get("error"), dict) and j["error"].get("message"):
                msg = str(j["error"]["message"])[:300]
        except (ValueError, AttributeError):
            pass
        err = RuntimeError(f"HTTP {e.code}: {msg}")
        err.body = full  # полный ответ — для разбора (ссылка подтверждения аккаунта Google)
        err.code = e.code
        try:
            err.retry_after = int((e.headers or {}).get("Retry-After") or 0)
        except (TypeError, ValueError):
            err.retry_after = 0
        raise err from None
    except urllib.error.URLError as e:
        raise Offline(T("сеть: {reason}", reason=e.reason)) from None
    except (TimeoutError, ConnectionError) as e:  # оборвалось уже во время чтения ответа
        raise Offline(T("сеть: {reason}", reason=e)) from None


class Offline(RuntimeError):
    """Нет связи с сервером: сеть недоступна, адрес не находится, сервер не ответил (1.5.6). Окно показывает у
    плитки значок OFFLINE и прежние данные, если они были."""


def is_offline(e):
    return isinstance(e, Offline)


# ================================================================ Claude Code
def _claude_usage(o, save):
    """Лимиты по входу claudeAiOauth o. Токен истёк (или истечёт в ближайшую минуту) — обновляем и сохраняем
    через save(o), так же, как это делает сам Claude Code."""
    if o.get("expiresAt", 0) < (time.time() + 60) * 1000:
        d = http_json(CLAUDE_TOKEN_URL, {"grant_type": "refresh_token",
                                         "refresh_token": o["refreshToken"],
                                         "client_id": CLAUDE_CLIENT_ID},
                      headers={"User-Agent": "claude-code/2.0"})
        o["accessToken"] = d["access_token"]
        if d.get("refresh_token"):
            o["refreshToken"] = d["refresh_token"]
        o["expiresAt"] = int((time.time() + d.get("expires_in", 3600)) * 1000)
        save(o)

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


def claude_fetch(profile=None):
    """Лимиты Claude: по входу Claude Code (~/.claude/.credentials.json) или по своему профилю AI Limits."""
    if profile is not None:
        data = accounts.read_secret(profile)
        o = data.get("claudeAiOauth") or {}
        if not o.get("accessToken"):
            raise RuntimeError(T("вход профиля потерян — удалите аккаунт и добавьте заново"))

        def save_profile(o):
            data["claudeAiOauth"] = o
            accounts.write_secret(profile, data)
        return _claude_usage(o, save_profile)

    if not os.path.exists(storage.CLAUDE_CREDS):
        raise RuntimeError(T("нет ~/.claude/.credentials.json — войдите в Claude Code командой `claude`"))
    with open(storage.CLAUDE_CREDS, encoding="utf-8") as f:
        creds = json.load(f)
    o = creds.get("claudeAiOauth") or {}
    if not o.get("accessToken"):
        raise RuntimeError(T("Claude Code не залогинен через подписку (claudeAiOauth нет)"))

    def save_main(o):
        with open(storage.CLAUDE_CREDS, encoding="utf-8") as f:  # перечитываем, чтобы не затереть чужие изменения
            fresh = json.load(f)
        fresh.setdefault("claudeAiOauth", {}).update(o)
        storage.atomic_write_json(storage.CLAUDE_CREDS, fresh)
    return _claude_usage(o, save_main)


def claude_installed():
    """Есть ли вход Claude Code — тогда есть плитка программы Claude Code."""
    return os.path.exists(storage.CLAUDE_CREDS)


# ================================================================ Codex (подписка ChatGPT)
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"  # неофициальный адрес, им пользуется Codex


def codex_installed():
    """Есть ли вход Codex (~/.codex/auth.json) — тогда в окне есть карточка Codex. Быстро, без сети."""
    return os.path.exists(storage.CODEX_AUTH)


def _codex_window(w):
    """Название окна лимита Codex по его длине: 5 часов или неделя."""
    secs = w.get("limit_window_seconds") or 0
    return "Неделя" if secs >= 6 * 86400 else ("5 часов" if 4 * 3600 <= secs <= 6 * 3600 else None)


OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_REFRESH_BEFORE = 86400  # профиль: обновить токен, если до истечения меньше суток


def _codex_refresh(profile, data):
    """Новый access-токен профиля ChatGPT (refresh-токен при этом меняется — сохраняем сразу)."""
    t = data.get("tokens") or {}
    cid = (t.get("oauth_provenance") or {}).get("client_id") or accounts.jwt_claims(t.get("access_token", "")).get("client_id")
    try:
        d = http_json(OPENAI_TOKEN_URL, {"client_id": cid, "grant_type": "refresh_token",
                                         "refresh_token": t.get("refresh_token"), "scope": "openid profile email"})
    except Offline:
        raise  # нет связи — вход тут ни при чём
    except RuntimeError as e:
        raise RuntimeError(T("вход профиля устарел — удалите аккаунт и добавьте заново ({error})", error=e)) from None
    for k in ("id_token", "access_token", "refresh_token"):
        if d.get(k):
            t[k] = d[k]
    data["tokens"] = t
    data["last_refresh"] = dt.datetime.now(dt.timezone.utc).isoformat()
    accounts.write_secret(profile, data)
    return t


def codex_fetch(profile=None):
    """Лимиты Codex: {"plan", "limits": [неделя, 5 часов]}. Без profile — аккаунт, под которым вошёл сам Codex;
    его токен только читается (обновляет его сам Codex, живёт около 10 дней), чтобы не сбить ему вход.
    Свой профиль AI Limits обновляет токен сам: этим входом больше никто не пользуется."""
    if profile is not None:
        data = accounts.read_secret(profile)
        tokens = data.get("tokens") or {}
        if accounts.jwt_claims(tokens.get("access_token", "")).get("exp", 0) < time.time() + CODEX_REFRESH_BEFORE:
            tokens = _codex_refresh(profile, data)
        try:
            return _codex_usage(tokens)
        except RuntimeError as e:
            if not str(e).startswith("HTTP 401"):
                raise
        return _codex_usage(_codex_refresh(profile, data))
    if not codex_installed():
        raise RuntimeError(T("Codex не установлен или в него не входили"))
    with open(storage.CODEX_AUTH, encoding="utf-8") as f:
        tokens = (json.load(f).get("tokens") or {})
    if not tokens.get("access_token"):
        raise RuntimeError(T("Codex вошёл не через аккаунт ChatGPT — лимитов подписки нет"))
    try:
        return _codex_usage(tokens)
    except RuntimeError as e:
        if str(e).startswith("HTTP 401"):
            raise RuntimeError(T("вход Codex устарел — запустите Codex, он обновит его сам")) from None
        raise


def _codex_usage(tokens):
    u = http_json(CODEX_USAGE_URL, headers={
        "Authorization": "Bearer " + tokens["access_token"],
        "ChatGPT-Account-Id": tokens.get("account_id") or "",
        "User-Agent": "codex_cli_rs",
        "Accept": "application/json",
    })
    rows = []
    for key in ("secondary_window", "primary_window"):  # неделя сверху, как у Claude
        w = (u.get("rate_limit") or {}).get(key)
        name = _codex_window(w) if isinstance(w, dict) else None
        if name and w.get("used_percent") is not None:
            reset = w.get("reset_at")
            rows.append({"name": name, "used": float(w["used_percent"]),
                         "resets_at": dt.datetime.fromtimestamp(reset, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                         if reset else None})
    rows.sort(key=lambda r: r["name"] != "Неделя")
    return {"plan": u.get("plan_type") or "?", "limits": rows}


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


def cc_post(path, token, body, key=None):
    """Запрос к облаку Antigravity. Если версию клиента отвергли (HTTP 403) — повтор со следующим заголовком
    из cc_user_agents(); принятый заголовок запоминается до конца работы программы — **для каждого аккаунта
    (key) отдельно**: 403 бывает и у одного аккаунта («Verify your account to continue»), и общий запомненный
    заголовок (1.5.3) переводил все аккаунты на безымянный «antigravity», с которым группы Gemini нет.
    Отказ «Verify your account» (1.5.4) — Google просит подтвердить аккаунт: аккаунт попадает в _CC_VERIFY, а
    запасной заголовок не запоминается — в следующий раз снова пробуется заголовок с версией IDE (вдруг уже
    подтвердили); первый принятый без этого отказа запрос убирает аккаунт из _CC_VERIFY."""
    agents = cc_user_agents()
    start = _CC_AGENT_OK.get(key, 0)
    start = start if start < len(agents) else 0
    verify = False
    for i in range(start, len(agents)):
        try:
            res = http_json(CC_BASE + path, body,
                            headers={"Authorization": "Bearer " + token, "User-Agent": agents[i]})
            if verify:
                _CC_VERIFY.add(key)
            else:
                _CC_AGENT_OK[key] = i
                _CC_VERIFY.discard(key)
            return res
        except RuntimeError as e:
            if not str(e).startswith("HTTP 403") or i == len(agents) - 1:
                if verify:
                    _CC_VERIFY.add(key)
                raise
            verify = verify or "verify your account" in str(e).lower()


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
    key = acc["email"].lower()
    lca = cc_post("/v1internal:loadCodeAssist", token, {"metadata": CC_META}, key)
    project = extract_project(lca) or acc.get("project")
    body = {"project": project} if project else {}
    plan = (lca.get("paidTier") or {}).get("name") or (lca.get("currentTier") or {}).get("name") or ""
    rows, source = None, "облако"
    try:
        rows = _summary_rows(cc_post("/v1internal:retrieveUserQuotaSummary", token, body, key))
    except Exception:
        pass
    verify = key in _CC_VERIFY  # Google просит подтвердить аккаунт — в окне значок LOGOUT (1.5.4)
    if not rows:
        rows = _bucket_rows(cc_post("/v1internal:retrieveUserQuota", token, body, key))
        source = "облако · действующий лимит"
    res = {"plan": plan, "models": rows, "credits": None, "source": source}
    if verify:
        res["verify"] = True
    return res


def validation_links(e):
    """(ссылка «Verify your account», ссылка «Learn more») из отказа облака 403 VALIDATION_REQUIRED или (None, None).
    Берутся только адреса Google."""
    try:
        for d in json.loads(getattr(e, "body", "") or "{}").get("error", {}).get("details", []):
            meta = d.get("metadata") or {}
            url = meta.get("validation_url")
            if url and url.startswith("https://accounts.google.com/"):
                more = meta.get("validation_learn_more_url") or ""
                return url, more if more.startswith("https://support.google.com/") else None
    except (ValueError, AttributeError):
        pass
    return None, None


def validation_url(e):
    return validation_links(e)[0]


def account_problem(access_token, email):
    """Проверка аккаунта Google в облаке перед «→ в IDE» (1.5.4): Google требует подтвердить аккаунт —
    текст причины; иначе (в том числе облако недоступно) — None, переключению не мешаем."""
    try:
        lca = cc_post("/v1internal:loadCodeAssist", access_token, {"metadata": CC_META}, email.lower())
        project = extract_project(lca)
        http_json(CC_BASE + "/v1internal:retrieveUserQuotaSummary", {"project": project} if project else {},
                  headers={"Authorization": "Bearer " + access_token, "User-Agent": cc_user_agents()[0]})
    except Exception as e:
        if validation_url(e) or "VALIDATION_REQUIRED" in (getattr(e, "body", "") or ""):
            return T("Google просит подтвердить аккаунт {email} — переключение отменено. Войдите в него заново "
                     "кнопкой ↻ в «Управлении аккаунтами»", email=email)
    return None


# страница в браузере после входа Google — в стиле окна программы (цвета ui_theme), на языке программы (1.5.4)
_PAGE_CSS = """
:root{--bg:#0e1014;--card:#171a21;--hi:#1d212a;--line:#262b36;--fg:#e8eaef;--muted:#8a91a0;--faint:#5c6372;
--blue:#5b8def;--green:#3ecf8e;--yellow:#f2c94c;--red:#ff5c5c}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--fg);font:15px/1.5 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;padding:24px 16px}
.card{width:100%;max-width:460px;background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:32px 32px 26px;text-align:center;border-left:6px solid var(--accent)}
.icon{width:56px;height:56px;margin:0 auto 18px;border-radius:50%;display:flex;align-items:center;
justify-content:center;font-size:28px;font-weight:700;color:var(--accent);background:var(--hi);
border:2px solid var(--accent)}
h1{font:600 21px/1.3 "Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;margin:0 0 10px}
p{margin:0 0 6px;color:var(--muted)}
.email{color:var(--fg);font-weight:600;word-break:break-all}
.actions{margin-top:24px}
.btn{display:inline-block;background:var(--blue);color:#fff;text-decoration:none;font-weight:600;
padding:10px 22px;border-radius:8px}
.btn:hover{filter:brightness(1.12)}
.note{margin-top:10px;font-size:13px;color:var(--faint)}
.note a{color:var(--blue)}
.foot{margin-top:26px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--faint)}
"""


def _login_page(kind, title, text="", email=None, button=None, note=None):
    """Страница результата входа Google. kind — ok / warn / error; text может содержать «{email}» — подставляется
    выделенный email; button — (надпись, адрес); note — (текст, надпись ссылки, адрес) мелко под кнопкой."""
    accent, icon = {"ok": ("var(--green)", "✓"), "warn": ("var(--yellow)", "!"),
                    "error": ("var(--red)", "✕")}[kind]
    e = html.escape
    body = e(text)
    if email:
        body = body.replace(e("{email}"), f"<span class='email'>{e(email)}</span>")
    parts = [f"<div class='icon'>{icon}</div>", f"<h1>{e(title)}</h1>"]
    if text:
        parts.append(f"<p>{body}</p>")
    if button:
        parts.append(f"<div class='actions'><a class='btn' href='{e(button[1], quote=True)}'>{e(button[0])}</a>")
        if note:
            parts.append(f"<div class='note'>{e(note[0])} <a href='{e(note[2], quote=True)}' target='_blank' "
                         f"rel='noopener'>{e(note[1])}</a></div>")
        parts.append("</div>")
    parts.append("<div class='foot'>AI Limits</div>")
    return (f"<!doctype html><html lang='{i18n.lang()}'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>AI Limits</title><style>{_PAGE_CSS}</style></head>"
            f"<body><div class='card' style='--accent:{accent}'>{''.join(parts)}</div></body></html>").encode("utf-8")


def ag_login(login_hint=None, expect=None):
    """OAuth-вход через браузер с приёмом кода на 127.0.0.1. login_hint — email, который Google предложит
    сразу (повторный вход в добавленный аккаунт, 1.5.4). С 1.5.4 страница «Готово» показывается только после
    обмена кода на токен, получения email (expect — нужный email: другой — отказ) и проверки облака: если Google
    требует подтвердить аккаунт (403 VALIDATION_REQUIRED), браузер сразу переадресуется на страницу подтверждения
    Google (с 22.11.2026; своей страницы с кнопкой нет); аккаунт сохраняется (вход получен), в ответе — verify_url."""
    _need_google_keys()
    state = secrets.token_urlsafe(16)
    result = {}

    def finish(code, redirect):
        tok = http_json(G_TOKEN_URL, {"code": code, "client_id": G_CLIENT_ID,
                                      "client_secret": G_CLIENT_SECRET, "redirect_uri": redirect,
                                      "grant_type": "authorization_code"}, form=True)
        if not tok.get("refresh_token"):
            raise RuntimeError(T("Google не выдал refresh_token — попробуйте ещё раз"))
        info = http_json("https://www.googleapis.com/oauth2/v2/userinfo",
                         headers={"Authorization": "Bearer " + tok["access_token"]})
        email = info.get("email") or ""
        if not email:
            raise RuntimeError(T("Не удалось узнать email вошедшего аккаунта"))
        if expect and email.lower() != expect.lower():
            raise RuntimeError(T("в браузере выбран {got}, а не {email} — вход не обновлён", got=email, email=expect))
        acc = {"email": email, "refresh_token": tok["refresh_token"], "project": None}
        try:
            lca = cc_post("/v1internal:loadCodeAssist", tok["access_token"], {"metadata": CC_META}, email.lower())
            acc["project"] = extract_project(lca)
            body = {"project": acc["project"]} if acc["project"] else {}
            http_json(CC_BASE + "/v1internal:retrieveUserQuotaSummary", body,
                      headers={"Authorization": "Bearer " + tok["access_token"], "User-Agent": cc_user_agents()[0]})
        except Exception as e:  # облако недоступно — вход всё равно получен; требует подтверждения — скажем
            acc["verify_url"] = validation_url(e)
        return acc

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in qs or "error" in qs:
                q = {k: v[0] for k, v in qs.items()}
                if "code" in q and q.get("state") == state:
                    try:
                        result["acc"] = acc = finish(q["code"], redirect)
                        if acc.get("verify_url"):  # сразу на страницу подтверждения Google (владелец, 22.11.2026)
                            self.send_response(302)
                            self.send_header("Location", acc["verify_url"])
                            self.end_headers()
                            return
                        else:
                            page = _login_page("ok", T("Готово"),
                                               T("Вход в {email} выполнен. Эту вкладку можно закрыть.", email="{email}"),
                                               acc["email"])
                    except Exception as e:
                        result["fail"] = str(e)
                        page = _login_page("error", T("Вход не выполнен"), str(e))
                else:
                    result["fail"] = q.get("error") or T("неверный ответ Google")
                    page = _login_page("error", T("Вход не выполнен"), result["fail"])
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}/callback"
    params = {"client_id": G_CLIENT_ID, "redirect_uri": redirect, "response_type": "code",
              "scope": G_SCOPES, "access_type": "offline", "prompt": "consent select_account",
              "state": state}
    if login_hint:
        params["login_hint"] = login_hint
    url = G_AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("Открываю браузер для входа в Google. Если не открылся — откройте ссылку вручную:\n")
    print(url + "\n")
    webbrowser.open(url)
    th = threading.Thread(target=lambda: [srv.handle_request() for _ in range(20) if not result], daemon=True)
    th.start()
    th.join(timeout=300)
    srv.server_close()
    if "acc" in result:
        return result["acc"]
    raise RuntimeError(result.get("fail") or T("вход не завершён: {reason}", reason=T("таймаут")))
