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

import cloud  # noqa: E402
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
    cloud._CC_AGENTS, cloud._CC_AGENT_OK = None, 0
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
    cloud._CC_AGENT_OK = 0

    def fail(url, data=None, headers=None, form=False, method=None):
        calls.append("500")
        raise RuntimeError("HTTP 500 сбой")
    cloud.http_json = fail
    n = len(calls)
    expect_error(RuntimeError, lambda: cloud.cc_post("/x", "t", {}))
    assert len(calls) == n + 1  # при ошибке, отличной от 403, заголовок не меняется
    cloud.http_json, cloud._CC_AGENT_OK = real, 0
    step("заголовок версии IDE: при 403 берётся следующий и запоминается, при 500 повтора нет")


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


# ------------------------------------------------------------------ вывод без токенов
def test_no_tokens_in_output():
    cloud.load_accounts = lambda: [{"email": "a@example.com", "refresh_token": FAKE_R}]
    cloud.claude_fetch = lambda: {"plan": "pro", "limits": []}
    ide_local.local_ide_quota = lambda: {}
    cloud.ag_fetch = lambda acc, all_models=False, local=None: {"plan": "Pro", "models": [], "credits": None,
                                                                 "source": "облако"}
    claude, ag = limits.collect(False)
    out = json.dumps(limits.to_jsonable(claude, ag), ensure_ascii=False)
    assert "a@example.com" in out
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


def main():
    print("Проверка логики (вымышленные данные, папка", TMP + ")")
    test_dpapi()
    old_copy = test_accounts_migration()
    test_keys()
    test_user_agents()
    test_winapi()
    fake_ide()
    test_backup_restore(old_copy)
    test_restore_command()
    test_switch()
    test_no_tokens_in_output()
    test_history()
    test_translations()
    left = plain_secrets() if WIN else []
    assert not left, left
    print("Все проверки логики пройдены.")


if __name__ == "__main__":
    main()
