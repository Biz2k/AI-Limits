"""Проверка логики AI Limits на вымышленных данных.

Настоящие учётные данные не читаются и не меняются: папка данных — временная, диспетчер учётных данных Windows,
запросы в сеть, закрытие и запуск IDE подменены. Запуск: python tests\\test_backend.py
"""
import json
import os
import socket
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k in ("ANTIGRAVITY_OAUTH_CLIENT_ID", "ANTIGRAVITY_OAUTH_CLIENT_SECRET", "ANTIGRAVITY_USER_AGENT"):
    os.environ.pop(_k, None)

import claude_switch  # noqa: E402
import cloud  # noqa: E402
import codex_switch  # noqa: E402
import accounts  # noqa: E402
import history  # noqa: E402
import i18n  # noqa: E402
import ide_local  # noqa: E402
import ide_switch  # noqa: E402
import limits  # noqa: E402
import storage  # noqa: E402
import winapi  # noqa: E402

i18n.set_lang("ru")  # сообщения логики проверяются по русским исходным строкам
TMP = tempfile.mkdtemp(prefix="ailimits_test_")
storage.APPDIR = TMP
storage.ACCOUNTS_FILE = os.path.join(TMP, "accounts.json")
storage.KEYS_FILE = os.path.join(TMP, "keys.dat")
storage.IDE_BACKUP_DIR = os.path.join(TMP, "ide_backups")
storage.ANTIGRAVITY_APPDATA = os.path.join(TMP, "Antigravity")
storage.APP_LOG = os.path.join(TMP, "app.log")
ide_local.IDE_LOG = os.path.join(TMP, "ide_switch.log")
limits.CACHE_FILE = os.path.join(TMP, "cache.json")
os.makedirs(storage.ANTIGRAVITY_APPDATA)
os.makedirs(storage.IDE_BACKUP_DIR)
APP_STORAGE = os.path.join(storage.ANTIGRAVITY_APPDATA, "app_storage.json")

FAKE_R = "1//0fake-refresh-token-for-test"
FAKE_A = "ya29.fake-access-token-for-test"
WIN = os.name == "nt"
real_sleep = time.sleep


def plain_secrets():
    """Файлы временной папки данных, в которых секрет лежит открытым текстом."""
    bad = []
    for root, _, files in os.walk(TMP):
        if root.startswith(storage.ANTIGRAVITY_APPDATA):  # это «папка IDE», а не данные программы
            continue
        for n in files:
            with open(os.path.join(root, n), "rb") as f:
                d = f.read()
            if b"1//" in d or b"ya29." in d or b"GOCSPX-fake" in d:
                bad.append(n)
    return bad


def expect_error(kind, fn):
    try:
        fn()
    except kind as e:
        return str(e)
    raise AssertionError(f"ожидалась ошибка {kind.__name__}")


def step(text):
    print("  ok ", text)


# ------------------------------------------------------------------ шифрование
def test_dpapi():
    assert storage.unprotect_text(storage.protect_text(FAKE_R)) == FAKE_R
    assert storage.unprotect_bytes(storage.protect_bytes(b"abc")) == b"abc"
    assert storage.unprotect_bytes(b"plain") == b"plain" and storage.unprotect_text("plain") == "plain"
    if WIN:
        assert storage.protect_text(FAKE_R).startswith("dpapi:")
        assert storage.protect_bytes(b"abc").startswith(storage._DPAPI_MAGIC)
    step("DPAPI: строка и файл шифруются и расшифровываются")


def test_accounts_migration():
    with open(storage.ACCOUNTS_FILE, "w") as f:
        json.dump({"accounts": [{"email": "a@example.com", "refresh_token": FAKE_R, "project": "p"}]}, f)
    old_copy = os.path.join(storage.IDE_BACKUP_DIR, "gemini_antigravity_20260101_000000.json")
    with open(old_copy, "wb") as f:
        f.write(json.dumps({"token": {"access_token": FAKE_A, "refresh_token": FAKE_R}}).encode())
    assert plain_secrets()
    done = cloud.protect_stored_secrets()
    accs = cloud.load_accounts()
    assert accs[0]["refresh_token"] == FAKE_R and accs[0]["project"] == "p"
    if WIN:
        assert done == 2 and not plain_secrets(), plain_secrets()
        assert cloud.protect_stored_secrets() == 0
    step("данные прежней версии перешифровываются при запуске, повтор ничего не меняет")

    cloud.save_accounts(accs + [{"email": "b@example.com", "refresh_token": FAKE_R + "2", "project": None}])
    assert [a["refresh_token"] for a in cloud.load_accounts()] == [FAKE_R, FAKE_R + "2"]
    if WIN:
        assert not plain_secrets()
        with open(storage.ACCOUNTS_FILE) as f:
            raw = json.load(f)
        raw["accounts"][0]["refresh_token"] = "dpapi:AAAA"  # токен с «другого компьютера»
        with open(storage.ACCOUNTS_FILE, "w") as f:
            json.dump(raw, f)
        accs = cloud.load_accounts()
        assert accs[0]["refresh_token"] == ""
        cloud.save_accounts(accs)
        with open(storage.ACCOUNTS_FILE) as f:
            text = f.read()
        assert json.loads(text)["accounts"][0]["refresh_token"] == "dpapi:AAAA" and "_stored" not in text
        cloud.G_CLIENT_ID = cloud.G_CLIENT_SECRET = "x"
        assert "не расшифрован" in expect_error(RuntimeError, lambda: cloud.g_access_token(accs[0]))
        cloud.G_CLIENT_ID = cloud.G_CLIENT_SECRET = ""
    step("аккаунты: сохранение, чтение, не расшифровавшийся токен не теряется")
    return old_copy


def test_keys():
    assert not os.path.exists(storage.KEYS_FILE)
    assert "нужны оба" in expect_error(ValueError, lambda: cloud.set_google_keys("", "x"))
    src = cloud.set_google_keys(" fake-id.apps.example ", "GOCSPX-fake-secret")
    assert src == "зашифрованный файл" and cloud.G_CLIENT_ID == "fake-id.apps.example"
    assert not WIN or not plain_secrets(), plain_secrets()
    cloud.G_CLIENT_ID = ""
    assert cloud.load_google_keys() == "зашифрованный файл" and cloud.G_CLIENT_SECRET == "GOCSPX-fake-secret"
    os.environ["ANTIGRAVITY_OAUTH_CLIENT_ID"], os.environ["ANTIGRAVITY_OAUTH_CLIENT_SECRET"] = "env-id", "env-s"
    assert cloud.load_google_keys() == "переменные окружения" and cloud.G_CLIENT_ID == "env-id"
    del os.environ["ANTIGRAVITY_OAUTH_CLIENT_ID"], os.environ["ANTIGRAVITY_OAUTH_CLIENT_SECRET"]
    assert cloud.load_google_keys() == "зашифрованный файл"
    assert limits.G_KEYS_SOURCE == "зашифрованный файл"  # через limits видно текущее значение
    step("OAuth-ключи: keys.dat зашифрован, переменные окружения важнее файла")


# ------------------------------------------------------------------ заголовок версии IDE
def test_user_agents():
    ide_local.ide_version = lambda: (2, 31, 2)
    cloud._CC_AGENTS, cloud._CC_AGENT_OK = None, {}
    agents = cloud.cc_user_agents()
    assert agents == ["antigravity/hub/2.31.2", "antigravity/hub/2.24.0", "antigravity"], agents
    calls = []

    def fake(url, data=None, headers=None, form=False, method=None):
        calls.append(headers["User-Agent"])
        if headers["User-Agent"] == agents[0]:
            raise RuntimeError("HTTP 403 отказ")
        return {"ok": 1}
    real, cloud.http_json = cloud.http_json, fake
    assert cloud.cc_post("/x", "t", {}) == {"ok": 1} and cloud.cc_post("/x", "t", {}) == {"ok": 1}
    assert calls == [agents[0], agents[1], agents[1]], calls
    # отказ одному аккаунту (403 «Verify your account») не переводит другие на прежний заголовок
    calls.clear()

    def one_bad(url, data=None, headers=None, form=False, method=None):
        calls.append((headers["Authorization"], headers["User-Agent"]))
        if headers["Authorization"] == "Bearer bad" and headers["User-Agent"] != agents[-1]:
            raise RuntimeError("HTTP 403: Verify your account to continue.")
        return {"ok": 1}
    cloud._CC_AGENT_OK, cloud._CC_VERIFY = {}, set()
    cloud.http_json = one_bad
    assert cloud.cc_post("/x", "bad", {}, "bad@example.com") == {"ok": 1}
    assert cloud.cc_post("/x", "good", {}, "good@example.com") == {"ok": 1}
    assert cloud.cc_post("/x", "bad", {}, "bad@example.com") == {"ok": 1}
    # «Verify your account» — аккаунт помечен, запасной заголовок не запоминается (в следующий раз — снова с версией)
    assert calls == [("Bearer bad", agents[0]), ("Bearer bad", agents[1]), ("Bearer bad", agents[2]),
                     ("Bearer good", agents[0]),
                     ("Bearer bad", agents[0]), ("Bearer bad", agents[1]), ("Bearer bad", agents[2])], calls
    assert cloud._CC_VERIFY == {"bad@example.com"}, cloud._CC_VERIFY
    cloud.http_json = lambda *a, **k: {"ok": 1}                          # подтвердили — пометка снимается
    assert cloud.cc_post("/x", "bad", {}, "bad@example.com") == {"ok": 1} and not cloud._CC_VERIFY
    cloud._CC_AGENT_OK = {}

    def fail(url, data=None, headers=None, form=False, method=None):
        calls.append("500")
        raise RuntimeError("HTTP 500 сбой")
    cloud.http_json = fail
    n = len(calls)
    expect_error(RuntimeError, lambda: cloud.cc_post("/x", "t", {}))
    assert len(calls) == n + 1  # при ошибке, отличной от 403, заголовок не меняется
    cloud.http_json, cloud._CC_AGENT_OK = real, {}
    step("заголовок версии IDE: при 403 берётся следующий и запоминается для аккаунта, при 500 повтора нет")


# ------------------------------------------------------------------ прямые вызовы Windows
def test_winapi():
    if not WIN:
        return step("прямые вызовы Windows — пропущено (не Windows)")
    me = os.getpid()
    assert me in [pid for pid, _ in winapi._win_processes()]
    assert "python" in winapi._win_process_text(me, "cmd").lower()
    assert winapi._win_process_text(me, "path").lower().endswith(".exe")
    assert winapi._file_version(winapi._win_process_text(me, "path"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        assert s.getsockname()[1] in winapi._win_local_ports().get(me, [])
    assert isinstance(winapi._win_window_pids(), set)
    step("прямые вызовы Windows: процессы, командная строка, путь, версия файла, порты, окна")


# ------------------------------------------------------------------ учётные данные IDE (подменены)
STORE = {"blob": None, "user": "antigravity", "persist": 2}
LOG = []
IDE = {"run": True}


def fake_ide():
    winapi._wincred_read = lambda t: dict(STORE) if STORE.get("blob") else None

    def write(t, u, b, persist=2):
        STORE.update(blob=b, user=u, persist=persist)
        LOG.append("write")
    winapi._wincred_write = write
    winapi._wincred_delete = lambda t: STORE.update(blob=None)
    ide_local._ide_running = lambda: IDE["run"]
    ide_local.ide_server_hidden = lambda: IDE.get("hidden", False)  # настоящую IDE владельца не трогаем
    ide_local._ide_open = lambda: IDE["run"]
    ide_local.find_ide_executable = lambda: r"C:\fake\Antigravity.exe"
    ide_local.stop_ide = lambda timeout=10: (IDE.update(run=False), LOG.append("stop"))
    ide_local.start_ide = lambda exe=None: (IDE.update(run=True), LOG.append("start"))


def cred(email):
    return json.dumps({"id_token_email": email, "writer_id": "w1",
                       "token": {"access_token": FAKE_A, "refresh_token": FAKE_R}}).encode()


def set_app_storage(email):
    with open(APP_STORAGE, "w") as f:
        f.write(json.dumps({"agy.onboarding.lastLoginUsername": email, "k": "ya29.inside-app-storage"}))


def test_backup_restore(old_copy):
    STORE["blob"] = cred("old@example.com")
    set_app_storage("old@example.com")
    with open(APP_STORAGE, "rb") as f:
        original = f.read()
    meta = ide_switch.backup_ide_credentials()
    assert meta["previous_email"] == "old@example.com"
    os.remove(APP_STORAGE)
    kept, STORE["blob"] = STORE["blob"], b"changed"
    assert not WIN or not plain_secrets(), plain_secrets()
    ide_switch.restore_ide_credentials(meta)
    with open(APP_STORAGE, "rb") as f:
        assert f.read() == original
    assert STORE["blob"] == kept
    ide_switch.restore_ide_credentials({"files": {"cred": old_copy}})  # копия прежней версии, перешифрованная
    assert json.loads(STORE["blob"])["token"]["access_token"] == FAKE_A
    step("копии учётных данных IDE зашифрованы, возврат точный")


def test_restore_command():
    for n in os.listdir(storage.IDE_BACKUP_DIR):
        os.remove(os.path.join(storage.IDE_BACKUP_DIR, n))
    assert ide_switch.latest_ide_backup() is None
    assert "Резервных копий нет" in expect_error(RuntimeError, ide_switch.ide_restore_backup)
    STORE["blob"] = cred("old@example.com")
    set_app_storage("old@example.com")
    ide_switch.backup_ide_credentials()
    real_sleep(1.1)  # имена копий различаются по секундам
    STORE["blob"] = cred("new@example.com")
    set_app_storage("new@example.com")
    del LOG[:]
    meta = ide_switch.ide_restore_backup()
    assert meta["previous_email"] == "old@example.com" and b"old@example.com" in STORE["blob"]
    with open(APP_STORAGE) as f:
        assert "old@example.com" in f.read()
    assert LOG == ["stop", "write", "start"], LOG
    assert ide_switch.latest_ide_backup()["previous_email"] == "new@example.com"
    real_sleep(1.1)
    ide_switch.ide_restore_backup()
    assert b"new@example.com" in STORE["blob"]
    IDE["run"] = False
    del LOG[:]
    real_sleep(1.1)
    ide_switch.ide_restore_backup()
    assert LOG == ["stop", "write"], LOG  # закрытую IDE после возврата не запускаем
    IDE["run"] = True
    step("restore-ide: возврат, отмена возврата повтором, закрытая IDE не запускается")


def test_switch():
    cloud.load_accounts = lambda: [{"email": "new@example.com", "refresh_token": "r"}]
    cloud._need_google_keys = lambda: None
    real_http, cloud.http_json = cloud.http_json, lambda *a, **k: {"access_token": "a", "expires_in": 3599}
    time.sleep = lambda s: None

    class Srv:
        port = 1
    try:
        # сервер IDE отвечает, но входа нет -> откат
        STORE["blob"] = cred("old@example.com")

        def no_login(diag=None):
            if diag is not None:
                diag.append("процесс 1: 5000 — входа нет")
            return [(Srv(), None)]
        ide_local.find_ide_servers = no_login
        err = expect_error(RuntimeError, lambda: ide_switch.ide_switch_account("new@example.com", timeout=0.05,
                                                                              bad_token=True))
        assert "возвращён" in err and b"old@example.com" in STORE["blob"], err

        # сервер молчит -> без отката, отдельная ошибка
        def silent(diag=None):
            if diag is not None:
                diag.append("процессов language_server нет")
            return []
        ide_local.find_ide_servers = silent
        try:
            ide_switch.ide_switch_account("new@example.com", timeout=0.05)
            raise AssertionError("ожидалась IdeSwitchUnverified")
        except ide_switch.IdeSwitchUnverified:
            pass
        assert b"new@example.com" in STORE["blob"]

        # сервер новой IDE (ключ скрыт) -> сразу «проверить нельзя», без 90 с ожидания и без отката
        IDE["hidden"], began = True, time.time()
        err = expect_error(ide_switch.IdeSwitchUnverified, lambda: ide_switch.ide_switch_account("new@example.com",
                                                                                               timeout=60))
        assert time.time() - began < 10 and "новая версия IDE" in err and b"new@example.com" in STORE["blob"], err
        IDE["hidden"] = False

        # Google требует подтвердить аккаунт -> отказ до закрытия IDE, запись входа не тронута
        STORE["blob"], IDE["run"] = cred("old@example.com"), True
        real_problem = cloud.account_problem
        cloud.account_problem = lambda tok, email: "Google просит подтвердить аккаунт " + email
        del LOG[:]
        err = expect_error(RuntimeError, lambda: ide_switch.ide_switch_account("new@example.com", timeout=5))
        assert "подтвердить" in err and "stop" not in LOG and b"old@example.com" in STORE["blob"], (err, LOG)
        cloud.account_problem = real_problem

        # IDE показала другой аккаунт -> откат
        STORE["blob"] = cred("old@example.com")
        ide_local.find_ide_servers = lambda diag=None: [(Srv(), {"email": "third@example.com"})]
        err = expect_error(RuntimeError, lambda: ide_switch.ide_switch_account("new@example.com", timeout=0.05))
        assert "third@example.com" in err and b"old@example.com" in STORE["blob"]

        # нужный аккаунт -> успех
        ide_local.find_ide_servers = lambda diag=None: [(Srv(), {"email": "new@example.com"})]
        IDE["run"] = False  # IDE закрыта: проверка «уже под этим аккаунтом» не выполняется
        assert ide_switch.ide_switch_account("new@example.com", timeout=5) == "new@example.com"
        assert json.loads(STORE["blob"])["id_token_email"] == "new@example.com"

        # IDE закрыта, а в ней и так нужный аккаунт -> только запуск: не закрываем, не пишем, не проверяем
        IDE["run"] = False
        del LOG[:]
        assert ide_switch.ide_switch_account("new@example.com") == "new@example.com"
        assert LOG == ["start"], LOG

        # IDE не установлена -> запускается консольная agy.exe (учётные данные те же); сервера IDE нет — без проверки
        keep_exe, ide_local.find_ide_executable = ide_local.find_ide_executable, lambda: None
        ide_local.find_cli_executable = lambda: r"C:\fake\agy.exe"
        ide_local.start_cli = lambda path: LOG.append("cli")
        ide_local.find_ide_servers = lambda diag=None: []
        try:
            IDE["run"] = False
            STORE["blob"] = cred("old@example.com")
            del LOG[:]
            assert ide_switch.ide_switch_account("new@example.com", timeout=0.05) == "new@example.com"
            assert LOG == ["stop", "write", "cli"] and b"new@example.com" in STORE["blob"], LOG
            del LOG[:]
            assert ide_switch.ide_switch_account("new@example.com") == "new@example.com" and LOG == ["cli"], LOG
        finally:
            ide_local.find_ide_executable = keep_exe

        # IDE не закрылась -> отмена, учётные данные не тронуты
        IDE["run"] = True
        ide_local.find_ide_servers = lambda diag=None: [(Srv(), {"email": "old@example.com"})]
        STORE["blob"] = cred("old@example.com")

        def stuck(timeout=10):
            raise RuntimeError("Antigravity не закрылся за 10 с")
        keep, ide_local.stop_ide = ide_local.stop_ide, stuck
        assert "не закрылся" in expect_error(RuntimeError, lambda: ide_switch.ide_switch_account("new@example.com"))
        assert b"old@example.com" in STORE["blob"]
        ide_local.stop_ide = keep
    finally:
        time.sleep = real_sleep
        cloud.http_json = real_http
    with open(ide_local.IDE_LOG, encoding="utf-8") as f:
        log = f.read()
    assert "Ожидание 0 с" in log and "ПРОВЕРКА ОТКАТА" in log and "Откат выполнен" in log
    step("смена аккаунта: успех, откат при «входа нет» и чужом аккаунте, без отката при молчании, отказ закрытия")


# ------------------------------------------------------------------ Codex (подписка ChatGPT)
def test_codex():
    storage.CODEX_AUTH = os.path.join(storage.APPDIR, "codex_auth.json")
    assert not cloud.codex_installed()
    assert "не установлен" in expect_error(RuntimeError, cloud.codex_fetch)
    with open(storage.CODEX_AUTH, "w", encoding="utf-8") as f:
        json.dump({"auth_mode": "chatgpt", "tokens": {"access_token": "eyJfake-codex-access", "account_id": "acc-1",
                                                      "refresh_token": "fake-codex-refresh"}}, f)
    seen = {}

    def fake_http(url, data=None, headers=None, **k):
        seen.update(url=url, headers=headers)
        return {"plan_type": "plus", "rate_limit": {
            "primary_window": {"used_percent": 7, "limit_window_seconds": 18000, "reset_at": 1_800_000_000},
            "secondary_window": {"used_percent": 31.5, "limit_window_seconds": 604800, "reset_at": 1_800_500_000}}}
    real_http, cloud.http_json = cloud.http_json, fake_http
    try:
        assert cloud.codex_installed()
        res = cloud.codex_fetch()
        assert res["plan"] == "plus" and [(r["name"], r["used"]) for r in res["limits"]] == [("Неделя", 31.5), ("5 часов", 7.0)]
        assert res["limits"][0]["resets_at"] == history._iso(1_800_500_000), res
        assert seen["url"].endswith("/wham/usage") and seen["headers"]["Authorization"] == "Bearer eyJfake-codex-access"
        assert seen["headers"]["ChatGPT-Account-Id"] == "acc-1"
        with open(storage.CODEX_AUTH, encoding="utf-8") as f:
            assert "fake-codex-refresh" in f.read()                # файл Codex только читаем, токен не обновляем

        def expired(*a, **k):
            raise RuntimeError("HTTP 401: {}")
        cloud.http_json = expired
        assert "запустите Codex" in expect_error(RuntimeError, cloud.codex_fetch)
        with open(storage.CODEX_AUTH, "w", encoding="utf-8") as f:
            json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-fake"}, f)
        assert "не через аккаунт ChatGPT" in expect_error(RuntimeError, cloud.codex_fetch)
    finally:
        cloud.http_json = real_http
    step("Codex: лимиты недели и 5 часов из входа Codex, файл только читается, устаревший вход — понятная ошибка")


# ------------------------------------------------------------------ аккаунты 1.5.0
def fake_jwt(claims):
    import base64
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return "eyJhbGciOiJub25lIn0." + enc(claims) + ".sig"


def test_accounts():
    # имена: уникальны (без учёта регистра и пробелов), не пустые, не длиннее 32, не названия программ
    taken = ["alex", "Работа"]
    assert accounts.name_error("", taken) and accounts.name_error("  ", taken)
    assert accounts.name_error("ALEX", taken) and accounts.name_error(" работа ", taken)
    assert accounts.name_error("Claude Code", []) and accounts.name_error("x" * 40, [])
    assert accounts.name_error("Новое имя", taken) is None
    assert accounts.suggest_name("chatgpt", "alex@example.com", taken) == "Codex alex"
    assert accounts.suggest_name("claude", "alex@example.com", taken + ["Claude alex"]) == "Claude alex 2"
    assert accounts.suggest_name("google", "new@example.com", taken) == "new"
    assert accounts.ident("google", "A@Example.com") == "a@example.com"
    assert accounts.ident("chatgpt", "A@x") == "codex:a@x" and accounts.ident("claude", "A@x") == "claude:a@x"
    step("имена аккаунтов: дубликат не применяется, при совпадении — приставка сервиса; ключи аккаунтов")

    # вход в профиль: программа записала файл — он шифруется, открытая копия удаляется, email известен
    pc = {"kind": "claude", "dir": "claude-test"}
    home = os.path.join(accounts.profiles_dir(), pc["dir"])
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, ".credentials.json"), "w") as f:
        json.dump({"claudeAiOauth": {"accessToken": "sk-ant-oat-fake", "refreshToken": "sk-ant-ort-fake",
                                     "expiresAt": 0, "subscriptionType": "pro"}}, f)
    with open(os.path.join(home, ".claude.json"), "w") as f:
        json.dump({"oauthAccount": {"emailAddress": "c@example.com", "organizationUuid": "org-1"}}, f)
    pc = accounts.add_profile(accounts.finish_login(pc, timeout=5))
    assert pc["email"] == "c@example.com" and pc["org"] == "org-1"
    assert not os.path.exists(os.path.join(home, ".credentials.json"))
    with open(os.path.join(home, "creds.dat"), "rb") as f:
        assert b"sk-ant" not in f.read() or not WIN
    px = {"kind": "chatgpt", "dir": "chatgpt-test"}
    hx = os.path.join(accounts.profiles_dir(), px["dir"])
    os.makedirs(hx, exist_ok=True)
    access = fake_jwt({"exp": time.time() + 3600, "client_id": "app_fake"})
    with open(os.path.join(hx, "auth.json"), "w") as f:
        json.dump({"auth_mode": "chatgpt", "tokens": {"id_token": fake_jwt({"email": "x@example.com"}),
                   "access_token": access, "refresh_token": "rt-old", "account_id": "acc-x",
                   "oauth_provenance": {"client_id": "app_fake"}}}, f)
    px = accounts.add_profile(accounts.finish_login(px, timeout=5))
    assert px["email"] == "x@example.com" and px["account_id"] == "acc-x"
    assert [q["dir"] for q in accounts.load_profiles()] == ["claude-test", "chatgpt-test"]
    dup = {"kind": "chatgpt", "dir": "chatgpt-dup", "email": "X@example.com"}
    os.makedirs(os.path.join(accounts.profiles_dir(), dup["dir"]), exist_ok=True)
    assert "уже добавлен" in expect_error(RuntimeError, lambda: accounts.add_profile(dup))
    assert not os.path.exists(os.path.join(accounts.profiles_dir(), "chatgpt-dup"))
    empty = {"kind": "claude", "dir": "claude-empty"}
    os.makedirs(os.path.join(accounts.profiles_dir(), empty["dir"]), exist_ok=True)
    assert "время ожидания" in expect_error(RuntimeError, lambda: accounts.finish_login(empty, timeout=0))
    assert not os.path.exists(os.path.join(accounts.profiles_dir(), "claude-empty"))
    # вход идёт без окна; отмена останавливает программу входа и убирает папку; программа завершилась без входа —
    # в сообщении её последняя строка (без адресов)
    import subprocess as sp
    slow = {"kind": "chatgpt", "dir": "chatgpt-slow", "_out": [],
            "_proc": sp.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=0x08000000)}
    os.makedirs(os.path.join(accounts.profiles_dir(), slow["dir"]), exist_ok=True)
    accounts.cancel_login(slow)
    assert "отменено" in expect_error(RuntimeError, lambda: accounts.finish_login(slow, timeout=20))
    assert slow["_proc"].poll() is not None and not os.path.exists(os.path.join(accounts.profiles_dir(), "chatgpt-slow"))
    quit_ = {"kind": "claude", "dir": "claude-quit", "_out": ["Opening browser", "https://x/authorize?a", "Login failed: denied"],
             "_proc": sp.Popen([sys.executable, "-c", "pass"], creationflags=0x08000000)}
    os.makedirs(os.path.join(accounts.profiles_dir(), quit_["dir"]), exist_ok=True)
    assert expect_error(RuntimeError, lambda: accounts.finish_login(quit_, timeout=20)) == "Login failed: denied"
    step("профиль: вход программы шифруется, открытая копия удаляется; повтор, отмена и несостоявшийся вход"
         " не сохраняются, причина — понятная")

    # лимиты по профилю: просроченные токены обновляет AI Limits и сохраняет зашифрованными
    calls = []

    def fake_http(url, data=None, headers=None, **k):
        calls.append((url, data, headers))
        if url == cloud.CLAUDE_TOKEN_URL:
            return {"access_token": "sk-ant-oat-new", "refresh_token": "sk-ant-ort-new", "expires_in": 3600}
        if url == cloud.CLAUDE_USAGE_URL:
            return {"seven_day": {"utilization": 12, "resets_at": None}}
        if url == cloud.OPENAI_TOKEN_URL:
            return {"access_token": fake_jwt({"exp": time.time() + 9 * 86400}), "refresh_token": "rt-new",
                    "id_token": fake_jwt({"email": "x@example.com"})}
        return {"plan_type": "pro", "rate_limit": {"secondary_window": {"used_percent": 4,
                                                                         "limit_window_seconds": 604800}}}
    real_http, cloud.http_json = cloud.http_json, fake_http
    try:
        res = cloud.claude_fetch(pc)
        assert res["plan"] == "pro" and res["limits"][0]["used"] == 12.0
        assert accounts.read_secret(pc)["claudeAiOauth"]["refreshToken"] == "sk-ant-ort-new"
        res = cloud.codex_fetch(px)  # токен истекает меньше чем через сутки — обновляется заранее
        ref = next(c for c in calls if c[0] == cloud.OPENAI_TOKEN_URL)
        assert ref[1]["client_id"] == "app_fake" and ref[1]["refresh_token"] == "rt-old", ref
        assert res["plan"] == "pro" and accounts.read_secret(px)["tokens"]["refresh_token"] == "rt-new"
        assert calls[-1][2]["ChatGPT-Account-Id"] == "acc-x"
        del calls[:]
        cloud.codex_fetch(px)  # свежий токен — без обновления
        assert not any(c[0] == cloud.OPENAI_TOKEN_URL for c in calls)
    finally:
        cloud.http_json = real_http
    accounts.remove_profile(px)
    assert not os.path.exists(hx) and [q["dir"] for q in accounts.load_profiles()] == ["claude-test"]
    step("профили: лимиты Claude и ChatGPT, обновление их токенов (с сохранением), удаление вместе с папкой")

    STORE["blob"] = cred("old@example.com")
    assert ide_switch.stored_ide_login() == ("old@example.com", FAKE_R)
    history._series = None
    history.record(None, [], items=[("claude", {"limits": [{"name": "Неделя", "used": 5, "resets_at": None}]})])
    assert history.rename_key("claude", "claude:me@example.com") == 1
    history._series = None
    assert history.series("claude:me@example.com", "Неделя", 0) and not history.series("claude", "Неделя", 0)
    step("вход IDE Antigravity для закрытой IDE; перенос истории Claude/Codex на ключи аккаунтов")


# ------------------------------------------------------------------ вывод без токенов


def test_codex_switch():
    """«→ в Codex»: копия входа, закрытие приложения, прежний вход — в профиль, запись, проверка, запуск; откат."""
    storage.CODEX_AUTH = os.path.join(storage.APPDIR, "codex_home", "auth.json")
    os.makedirs(os.path.dirname(storage.CODEX_AUTH), exist_ok=True)

    def auth(email):
        return {"auth_mode": "chatgpt", "tokens": {"id_token": fake_jwt({"email": email}), "access_token": "at-" + email,
                                                    "refresh_token": "rt-" + email, "account_id": "acc-" + email}}
    with open(storage.CODEX_AUTH, "w", encoding="utf-8") as f:
        json.dump(auth("main@example.com"), f)
    target = {"kind": "chatgpt", "dir": "chatgpt-target", "email": "two@example.com", "account_id": "acc-two"}
    os.makedirs(os.path.join(accounts.profiles_dir(), target["dir"]), exist_ok=True)
    accounts.write_secret(target, auth("two@example.com"))
    accounts.save_profiles([q for q in accounts.load_profiles() if q["kind"] != "chatgpt"] + [target])

    app = "C:\\Program Files\\WindowsApps\\OpenAI.Codex_26.1.0_x64__pubid\\app\\ChatGPT.exe"
    procs = {}

    def launch():
        procs.update({11: ("ChatGPT.exe", app), 12: ("codex.exe", app.replace("ChatGPT.exe", "resources\\codex.exe"))})
    launch()
    calls, started = [], []
    real = (winapi._win_processes, winapi._win_process_text, winapi._run_hidden, winapi._win_window_pids,
            codex_switch.start_app)
    winapi._win_processes = lambda: [(pid, n) for pid, (n, _) in procs.items()]
    winapi._win_process_text = lambda pid, what: procs.get(pid, (None, None))[1]

    def run(args, timeout=8):
        calls.append(args)
        for pid in [p for p, (_, path) in procs.items() if "OpenAI.Codex_" in path]:
            procs.pop(pid)  # приложение закрылось
    winapi._run_hidden = run
    winapi._win_window_pids = lambda: set(procs)
    codex_switch.start_app = started.append
    try:
        assert codex_switch.app_family() == "OpenAI.Codex_pubid" and not codex_switch.cli_running()
        r = codex_switch.switch(target)
        assert r["email"] == "two@example.com" and r["created"] and r["restarted"], r
        assert accounts.codex_ide_email() == "two@example.com" and started == ["OpenAI.Codex_pubid"]
        assert calls and "/F" not in calls[0]                             # сначала — штатное закрытие
        kept = r["kept"]
        assert kept["email"] == "main@example.com" and kept in accounts.load_profiles()
        assert accounts.read_secret(kept)["tokens"]["refresh_token"] == "rt-main@example.com"  # прежний вход сохранён
        bdir = codex_switch.backups_dir()
        names = os.listdir(bdir)
        assert len(names) == 1 and b"rt-main" not in open(os.path.join(bdir, names[0]), "rb").read()  # зашифрована
        assert codex_switch.switch(target)["kept"] is None                # уже в нём — ничего не делаем

        r = codex_switch.switch(kept)                                      # обратно (приложение закрыто)
        assert accounts.codex_ide_email() == "main@example.com" and not r["created"] and not r["restarted"]
        assert accounts.read_secret(target)["tokens"]["access_token"] == "at-two@example.com"  # свежий вход — в профиль

        procs[20] = ("codex.exe", "C:\\Tools\\codex\\codex.exe")            # Codex в терминале — не трогаем
        expect_error(RuntimeError, lambda: codex_switch.switch(target))
        assert accounts.codex_ide_email() == "main@example.com"
        procs.clear()

        launch()
        started.clear()
        real_write = codex_switch._write_auth
        codex_switch._write_auth = lambda raw: real_write(
            json.dumps(auth("bad@example.com")).encode() if b"at-two@" in raw else raw)
        err = expect_error(RuntimeError, lambda: codex_switch.switch(target))  # записалось не то — откат
        codex_switch._write_auth = real_write
        assert "записался" in err and accounts.codex_ide_email() == "main@example.com", err
        assert started == ["OpenAI.Codex_pubid"]                          # приложение запущено снова
        assert len(os.listdir(bdir)) <= codex_switch.KEEP_BACKUPS
    finally:
        (winapi._win_processes, winapi._win_process_text, winapi._run_hidden, winapi._win_window_pids,
         codex_switch.start_app) = real
        for q in accounts.load_profiles():  # следующим проверкам — прежний набор профилей
            if q["kind"] == "chatgpt":
                accounts.remove_profile(q)
    step("«→ в Codex»: копия входа, штатное закрытие приложения, прежний вход — в профиль (новый, если не добавлен),"
         " запуск снова; Codex в терминале — отказ; не тот аккаунт после записи — откат")


def test_claude_switch():
    """«→ в Claude»: копия входа, прежний вход — в профиль, запись токенов и аккаунта без потери остального, откат."""
    home = os.path.join(storage.APPDIR, "claude_home")
    os.makedirs(home, exist_ok=True)
    real_cfg, real_creds = claude_switch.config_path, storage.CLAUDE_CREDS
    claude_switch.config_path = lambda: os.path.join(home, ".claude.json")
    storage.CLAUDE_CREDS = os.path.join(home, ".claude", ".credentials.json")

    def oauth(email):
        return {"accessToken": "sk-ant-oat-" + email, "refreshToken": "sk-ant-ort-" + email, "expiresAt": 1}
    storage.atomic_write_json(storage.CLAUDE_CREDS, {"claudeAiOauth": oauth("main@example.com"), "mcpOAuth": {"m": 1}})
    storage.atomic_write_json(claude_switch.config_path(), {
        "projects": {"x": 1}, "oauthAccount": {"emailAddress": "main@example.com", "organizationUuid": "org-main"}})
    target = {"kind": "claude", "dir": "claude-target", "email": "two@example.com", "org": "org-two"}
    os.makedirs(os.path.join(accounts.profiles_dir(), target["dir"]), exist_ok=True)
    accounts.write_secret(target, {"claudeAiOauth": oauth("two@example.com")})
    storage.atomic_write_json(accounts.profile_path(target, ".claude.json"),
                              {"oauthAccount": {"emailAddress": "two@example.com", "organizationUuid": "org-two",
                                                "displayName": "Two"}})
    before = accounts.load_profiles()
    accounts.save_profiles(before + [target])
    try:
        r = claude_switch.switch(target)
        cfg = json.load(open(claude_switch.config_path(), encoding="utf-8"))
        creds = json.load(open(storage.CLAUDE_CREDS, encoding="utf-8"))
        assert r["email"] == "two@example.com" and r["created"], r
        assert cfg["oauthAccount"]["displayName"] == "Two" and cfg["projects"] == {"x": 1}   # остальное не тронуто
        assert creds["claudeAiOauth"]["accessToken"] == "sk-ant-oat-two@example.com" and creds["mcpOAuth"] == {"m": 1}
        kept = r["kept"]
        assert kept["email"] == "main@example.com" and kept["org"] == "org-main"
        saved = accounts.read_secret(kept)
        assert saved["claudeAiOauth"]["refreshToken"] == "sk-ant-ort-main@example.com"
        assert saved["oauthAccount"]["organizationUuid"] == "org-main"
        names = os.listdir(claude_switch.backups_dir())
        assert len(names) == 1 and b"sk-ant" not in open(os.path.join(claude_switch.backups_dir(), names[0]), "rb").read()
        assert claude_switch.switch(target)["kept"] is None                # уже в нём — ничего не делаем

        r = claude_switch.switch(kept)                                     # обратно — аккаунт и токены прежние
        cfg = json.load(open(claude_switch.config_path(), encoding="utf-8"))
        assert cfg["oauthAccount"]["emailAddress"] == "main@example.com" and not r["created"]
        assert accounts.read_secret(target)["claudeAiOauth"]["accessToken"] == "sk-ant-oat-two@example.com"

        real_write = claude_switch._write
        claude_switch._write = lambda o, a: real_write(o, dict(a, emailAddress="bad@example.com")) \
            if (a or {}).get("emailAddress") == "two@example.com" else real_write(o, a)
        err = expect_error(RuntimeError, lambda: claude_switch.switch(target))  # записалось не то — откат
        claude_switch._write = real_write
        cfg = json.load(open(claude_switch.config_path(), encoding="utf-8"))
        creds = json.load(open(storage.CLAUDE_CREDS, encoding="utf-8"))
        assert "записался" in err and cfg["oauthAccount"]["emailAddress"] == "main@example.com", err
        assert creds["claudeAiOauth"]["accessToken"] == "sk-ant-oat-main@example.com"
    finally:
        claude_switch.config_path, storage.CLAUDE_CREDS = real_cfg, real_creds
        for q in accounts.load_profiles():
            if q["dir"] not in {b["dir"] for b in before}:
                accounts.remove_profile(q)
    step("«→ в Claude»: копия входа, прежний вход — в профиль (новый, если не добавлен), токены и аккаунт"
         " записаны без потери настроек и mcpOAuth; не тот аккаунт после записи — откат")


def test_no_tokens_in_output():
    cloud.load_accounts = lambda: [{"email": "a@example.com", "refresh_token": FAKE_R}]
    cloud.claude_fetch = lambda: {"plan": "pro", "limits": []}
    cloud.codex_installed = lambda: True
    cloud.codex_fetch = lambda profile=None: {"plan": "plus", "limits": [{"name": "Неделя", "used": 12.0, "resets_at": None}]}
    cloud.claude_fetch = lambda profile=None: {"plan": "pro", "limits": []}
    ide_local.local_ide_quota = lambda: {}
    cloud.ag_fetch = lambda acc, all_models=False, local=None: {"plan": "Pro", "models": [], "credits": None,
                                                                 "source": "облако"}
    claude, ag, codex, profiles = limits.collect(False)
    assert [p["email"] for p, _ in profiles] == ["c@example.com"]      # профиль Claude из test_accounts
    out = json.dumps(limits.to_jsonable(claude, ag, codex, profiles), ensure_ascii=False)
    assert '"claude:c@example.com"' in out and "Claude · c@example.com" in limits.render(claude, ag, 80, codex, profiles)
    assert "a@example.com" in out and '"codex": {"plan": "plus"' in out, out
    assert "Codex" in limits.render(claude, ag, 80, codex)
    assert not any(x in out for x in ("1//", "ya29.", "dpapi:", "refresh_token")), out
    ide_local._ide_log("проверка", {"access_token": FAKE_A + "x" * 80, "t": FAKE_R + "y" * 80})
    with open(ide_local.IDE_LOG, encoding="utf-8") as f:
        assert "ya29." not in f.read()
    try:
        raise RuntimeError("сбой с токеном " + FAKE_A + "z" * 40)
    except RuntimeError:
        storage.log_exception("проверка", *sys.exc_info())
    with open(storage.APP_LOG, encoding="utf-8") as f:
        text = f.read()
    assert limits.__version__ in text and "ya29.fake" not in text, text[-300:]
    step("вывод --json, журнал смены аккаунта и журнал ошибок без токенов")


# ------------------------------------------------------------------ история и прогноз
def test_history():
    history._series = None
    t0 = 1_800_000_000.0  # условное «сейчас»
    H = 3600
    iso = history._iso

    def claude(week, five, reset):
        return {"plan": "pro", "limits": [
            {"name": "Неделя", "used": week, "resets_at": iso(reset)},
            {"name": "5 часов", "used": five, "resets_at": iso(t0 + 4 * H)}]}

    reset = t0 + 5 * 24 * H
    week = "Неделя"
    assert history.record(claude(40, 1, reset), [], now=t0) == 2
    assert history.record(claude(40, 1, reset), [], now=t0 + 60) == 0    # то же значение через минуту
    assert history.record(claude(40, 1, reset), [], now=t0 + 700) == 2   # то же значение через 10+ минут
    cached = [("a@example.com", {"models": [{"name": "Неделя", "used": 50, "resets_at": iso(reset), "seen": "x"},
                                            {"name": "5 часов", "used": None, "resets_at": None}]})]
    assert history.record(None, cached, now=t0 + 800) == 0               # значения из кэша и пустые не пишем
    assert history.forecast("claude", week, 40.2, iso(reset), now=t0 + 1800) is None  # мало данных
    step("история: запись, пропуск повторов и значений из кэша")

    # недельный лимит: 20 % за двухчасовую сессию считаются расходом за сутки, а не темпом на круглые сутки
    now = t0 + 2 * H
    fc = history.forecast("claude", week, 60, iso(reset), now=now)
    assert fc and fc["before_reset"] and abs(fc["rate"] - 20 / 24) < 0.01 and abs(fc["left"] - 48 * H) < 5, fc
    assert fc["line"].startswith("хватит на 2 дня, до ") and fc["when"] == history.when_text(now + 48 * H, now)
    far = history.forecast("claude", week, 60, iso(now + 10 * H), now=now)
    assert far and not far["before_reset"] and far["line"] is None       # сброс наступит раньше исчерпания
    assert history.forecast("claude", week, 40, iso(reset), now=now) is None    # расход не растёт
    assert history.forecast("claude", week, 100, iso(reset), now=now) is None
    assert history.forecast("claude", "Другое окно", 60, iso(reset), now=now) is None
    # 5-часовой лимит: темп текущей сессии — 30 % за час, остаток 69 % -> 2 часа 18 минут
    five = history.forecast("claude", "5 часов", 31, iso(t0 + 4 * H), now=t0 + H)
    assert five and five["before_reset"] and abs(five["rate"] - 30) < 0.01, five
    assert five["line"].startswith("хватит на 2 часа 18 минут, до "), five["line"]
    assert set(history.forecasts(claude(60, 1, reset), [], now=now)) == {("claude", week)}
    step("прогноз: суточный расход для недели, темп сессии для 5 часов, «хватит на …, до …»")

    def acc(used, ts):  # сброс лимита: темп считается только по точкам после падения
        return history.record(None, [("B@example.com", {"models": [
            {"name": "Неделя", "used": used, "resets_at": iso(ts + 100 * H)}]})], now=ts)
    acc(90, t0), acc(95, t0 + H), acc(2, t0 + 2 * H), acc(3, t0 + 3 * H)
    fc = history.forecast("b@example.com", "Неделя", 4, iso(t0 + 104 * H), now=t0 + 4 * H)
    assert fc and abs(fc["rate"] - 2 / 24) < 0.01, fc                    # после сброса: 2 -> 4, то есть 2 % в сутки
    assert len(history.series("B@example.com", "Неделя", t0)) == 4
    step("прогноз после сброса лимита считается заново")

    now = t0 + 5 * H  # хранение 60 дней: старые строки убираются из файла при загрузке
    with open(history.history_file(), "a", encoding="utf-8", newline="") as f:
        f.write(iso(now - 61 * 86400) + ",claude,5 часов,7,\nиспорченная строка\n")
        f.write(iso(now - 60) + ",claude,Неделя (все модели),77,\n")  # прежнее название окна
    history._series = None
    data = history.load(now)
    assert all(ts >= now - 60 * 86400 for pts in data.values() for ts, _, _ in pts)
    with open(history.history_file(), encoding="utf-8") as f:
        text = f.read()
    assert "испорченная" not in text and iso(now - 61 * 86400) not in text and iso(t0) in text
    history._series = None
    assert sum(len(p) for p in history.load(now).values()) == sum(len(p) for p in data.values())
    assert history.series("claude", "Неделя", now - 120)[-1][1] == 77 and ("claude", "Неделя (все модели)") not in data
    assert ":" in history.when_text(now, now) and len(history.when_text(now + 3 * 86400, now).split()) == 2
    step("история хранится 60 дней: устаревшие и испорченные строки убираются")

    # график: простой между сессиями — значение держится до сброса, падает до нуля, лежит на нуле до новой точки
    pts = [(0, 10, 9000), (600, 40, 9000), (40000, 2, 58000), (40600, 5, 58000)]
    assert history.graph_path(pts) == [
        (False, [(0, 10), (600, 40), (9000, 40)]),
        (True, [(9000, 40), (9000, 0.0), (40000, 0.0), (40000, 2)]),
        (False, [(40000, 2), (40600, 5)])], history.graph_path(pts)
    # сброс без известного времени: вертикальный спуск у следующей точки, дальше нули — тонко
    pts = [(0, 90, None), (600, 100, None), (1200, 0, None), (1800, 0, None), (2400, 7, None)]
    assert history.graph_path(pts) == [
        (False, [(0, 90), (600, 100), (1200, 100)]),
        (True, [(1200, 100), (1200, 0), (1800, 0)]),
        (False, [(1800, 0), (2400, 7)])], history.graph_path(pts)
    step("график: без косой линии через простой; сбросы и нули отдельно (тонкой линией)")


# ------------------------------------------------------------------ переводы
def test_translations():
    import ast
    import re
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    used = {}
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith((".py", ".pyw")) or name == "i18n.py":
            continue
        with open(os.path.join(src_dir, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "T" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                used.setdefault(n.args[0].value, []).append((name, n.lineno, {k.arg for k in n.keywords}))
    assert len(used) > 100, len(used)
    fields = lambda s: set(re.findall(r"\{(\w+)\}", s))
    for text, places in used.items():
        assert text in i18n.TEXTS, ("нет перевода", text, places[0][:2])
        for name, line, given in places:  # все подстановки строки переданы при вызове
            assert fields(text) <= given, ("не переданы подстановки", text, name, line)
    for text, pair in i18n.TEXTS.items():
        assert len(pair) == 2 and all(pair), text
        for tr in pair:
            assert fields(tr) == fields(text), ("подстановки перевода не совпадают", text, tr)
    for name in ("Неделя", "5 часов", "облако", "данные IDE Antigravity", "1 мин", "выкл"):
        assert name in i18n.TEXTS, name  # строки, которые переводятся при показе, а не в месте появления
    assert i18n.set_lang("xx") == "en" and i18n.T("Неделя") == "Week" and i18n.day(0) == "Mon"
    assert i18n.set_lang("uk") == "uk" and i18n.T("Добавлен {email}", email="a@b") == "Додано a@b"
    assert i18n.duration(2 * 86400 + 5 * 3600) == "2 дні 5 годин" and i18n.duration(3600) == "1 годину"
    i18n.set_lang("en")
    assert i18n.duration(86400) == "1 day" and i18n.duration(2 * 86400 + 3600) == "2 days 1 hour"
    i18n.set_lang("ru")
    assert [i18n.duration(s) for s in (60, 21 * 60, 2 * 3600, 5 * 3600 + 120, 11 * 86400, 86400 + 3600)] == \
        ["1 минуту", "21 минуту", "2 часа", "5 часов 2 минуты", "11 дней", "1 день 1 час"]
    i18n.set_lang("en")
    assert i18n.T("сеть: {reason}", reason="x") == "network: x"
    assert i18n.set_lang("ru") == "ru" and i18n.T("Неделя") == "Неделя"
    step(f"переводы: {len(used)} строк интерфейса, у каждой есть английский и украинский вариант")


# ------------------------------------------------------------------ вход Google: страница «Готово» — только после токена
def test_google_login_page():
    import threading
    import urllib.parse
    import urllib.request
    T = i18n.T
    pages, threads, mode = [], [], {}

    def fake_open(url):  # «браузер»: Google сразу возвращает его на 127.0.0.1 с кодом
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        mode["hint"] = q.get("login_hint", [None])[0]
        cb = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "c1", "state": q["state"][0]})
        th = threading.Thread(target=lambda: pages.append(urllib.request.urlopen(cb, timeout=20).read().decode()))
        th.start()
        threads.append(th)

    def fake_http(url, data=None, headers=None, form=False, method=None):
        if url == cloud.G_TOKEN_URL:
            if mode.get("no_refresh"):
                return {"access_token": "a"}
            return {"access_token": "a", "refresh_token": "1//fake-login-refresh"}
        if "userinfo" in url:
            return {"email": "v@example.com"}
        if "loadCodeAssist" in url:
            return {"cloudaicompanionProject": "proj"}
        if mode.get("verify"):
            err = RuntimeError("HTTP 403: Verify your account to continue.")
            err.body = json.dumps({"error": {"code": 403, "details": [{"reason": "VALIDATION_REQUIRED", "metadata": {
                "validation_url": "https://accounts.google.com/v3/signin/continue?plt=fake&x=1",
                "validation_learn_more_url": "https://support.google.com/accounts?p=al_alert"}}]}})
            raise err
        return {"groups": []}

    real = (cloud.webbrowser.open, cloud.http_json, cloud.G_CLIENT_ID, cloud.G_CLIENT_SECRET)
    cloud.webbrowser.open, cloud.http_json = fake_open, fake_http
    cloud.G_CLIENT_ID = cloud.G_CLIENT_SECRET = "x"

    def run(**kw):
        del pages[:], threads[:]
        try:
            return cloud.ag_login(**kw)
        finally:
            [th.join(10) for th in threads]
    try:
        acc = run()
        assert acc == {"email": "v@example.com", "refresh_token": "1//fake-login-refresh", "project": "proj"}, acc
        assert T("Готово") in pages[0] and "v@example.com" in pages[0] and "class='card'" in pages[0], pages
        mode["verify"] = True                                              # Google требует подтвердить аккаунт
        acc = run(login_hint="v@example.com", expect="v@example.com")
        assert mode["hint"] == "v@example.com" and acc["verify_url"].startswith("https://accounts.google.com/")
        assert T("Google просит подтвердить аккаунт") in pages[0] and "class='btn'" in pages[0]
        assert "href='https://accounts.google.com/v3/signin/continue?plt=fake&amp;x=1'" in pages[0], pages[0]
        assert "support.google.com/accounts?p=al_alert" in pages[0]       # «справка Google» под кнопкой
        mode["verify"] = False
        msg = expect_error(RuntimeError, lambda: run(expect="other@example.com"))  # выбран другой аккаунт
        assert "other@example.com" in msg and "не обновлён" in msg or "not updated" in msg, msg
        assert T("Вход не выполнен") in pages[0] and "other@example.com" in pages[0]
        mode["no_refresh"] = True                                          # токена нет — и «Готово» нет
        expect_error(RuntimeError, lambda: run())
        assert T("Вход не выполнен") in pages[0], pages[0]
        mode["no_refresh"] = False
        i18n.set_lang("en")                                                # страница — на языке программы
        run()
        assert "<html lang='en'>" in pages[0] and "Signed in to" in pages[0] and "You can close this tab" in pages[0]
        i18n.set_lang("ru")
    finally:
        cloud.webbrowser.open, cloud.http_json, cloud.G_CLIENT_ID, cloud.G_CLIENT_SECRET = real
    step("вход Google: «Готово» в браузере — только после получения токена и email; требует подтверждения — "
         "ссылка Google на странице; другой аккаунт или нет токена — ошибка на странице")


# ------------------------------------------------------------------ ошибки HTTP: коротко, с кодом и Retry-After
def test_http_errors():
    import email.message
    import io
    import urllib.error
    real = cloud.urllib.request.urlopen

    def fail(body, code=429, retry=None):
        def urlopen(req, timeout=None):
            h = email.message.Message()
            if retry:
                h["Retry-After"] = retry
            raise urllib.error.HTTPError(req.full_url, code, "x", h, io.BytesIO(body.encode()))
        return urlopen
    try:
        cloud.urllib.request.urlopen = fail(json.dumps({"type": "error", "error": {
            "type": "rate_limit_error", "message": "Rate limited. Please try again later."}}), retry="120")
        e = expect_error(RuntimeError, lambda: cloud.http_json("https://example.com/x"))
        assert e == "HTTP 429: Rate limited. Please try again later.", e
        try:
            cloud.http_json("https://example.com/x")
        except RuntimeError as err:
            assert err.code == 429 and err.retry_after == 120 and "rate_limit_error" in err.body
        cloud.urllib.request.urlopen = fail("plain text", code=500)
        assert expect_error(RuntimeError, lambda: cloud.http_json("https://example.com/x")) == "HTTP 500: plain text"
    finally:
        cloud.urllib.request.urlopen = real
    step("ошибка HTTP: в тексте только сообщение сервера (без JSON), код и Retry-After — в полях ошибки")


# ------------------------------------------------------------------ новая IDE: ключ сервера — из hub_<порт>.json
def test_ide_hub():
    hub = os.path.join(TMP, "daemon")
    os.makedirs(hub, exist_ok=True)
    with open(os.path.join(hub, "hub_2222.json"), "w", encoding="utf-8") as f:
        json.dump({"pid": 4242, "httpsPort": 1111, "httpPort": 2222, "lsVersion": "2.34.0", "csrfToken": "tok-fake"}, f)
    with open(os.path.join(hub, "hub_3333.json"), "w", encoding="utf-8") as f:   # другой (старый) процесс
        json.dump({"pid": 9999, "httpsPort": 3331, "httpPort": 3333, "csrfToken": "other"}, f)
    real = (ide_local.hub_dir, ide_local._ide_ls_processes, ide_local.IdeServer.status, winapi._win_local_ports)
    asked = []

    def status(self):
        asked.append((self.port, self.scheme, self.csrf))
        if (self.port, self.scheme, self.csrf) == (1111, "https", "tok-fake"):
            return {"userStatus": {"email": "n@example.com"}}
        raise RuntimeError("401")
    ide_local.hub_dir = lambda: hub
    ide_local._ide_ls_processes = lambda: [{"id": 4242, "cmd": "language_server.exe --standalone --override_ide_name "
                                            "antigravity --read_host_bridge_token_from_stdin"}]
    ide_local.IdeServer.status = status
    winapi._win_local_ports = lambda: (_ for _ in ()).throw(AssertionError("таблица соединений не нужна"))
    try:
        ide_local._IDE_PORTS.clear()
        found = ide_local.find_ide_servers()
        assert [(s.port, us) for s, us in found] == [(1111, {"email": "n@example.com"})], found
        assert not ide_local.ide_server_hidden()
        os.remove(os.path.join(hub, "hub_2222.json"))                      # файла нет — спросить нельзя
        ide_local._IDE_PORTS.clear()
        diag = []
        assert ide_local.find_ide_servers(diag) == [] and ide_local.ide_server_hidden(), diag
    finally:
        ide_local.hub_dir, ide_local._ide_ls_processes, ide_local.IdeServer.status, winapi._win_local_ports = real
        ide_local._IDE_PORTS.clear()
    step("новая IDE: ключ и порт сервера — из hub_<порт>.json по PID; без файла — «спросить нельзя»")


def main():
    print("Проверка логики (вымышленные данные, папка", TMP + ")")
    test_dpapi()
    old_copy = test_accounts_migration()
    test_keys()
    test_user_agents()
    test_winapi()
    test_ide_hub()
    fake_ide()
    test_backup_restore(old_copy)
    test_restore_command()
    test_switch()
    test_codex()
    test_google_login_page()
    test_http_errors()
    test_accounts()
    test_codex_switch()
    test_claude_switch()
    test_no_tokens_in_output()
    test_history()
    test_translations()
    left = plain_secrets() if WIN else []
    assert not left, left
    print("Все проверки логики пройдены.")


if __name__ == "__main__":
    main()
