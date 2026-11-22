"""Проверка окна AI Limits на вымышленных данных.

Окно открывается на несколько секунд; запросы, настройки, ключи и смена аккаунта IDE подменены —
настоящие данные и настройки не читаются и не меняются. Запуск: python tests\\test_gui.py
"""
import os
import sys
import time
import tkinter as tk
import traceback
import types
from importlib.machinery import SourceFileLoader

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)
G = SourceFileLoader("limits_gui", os.path.join(SRC, "limits_gui.pyw")).load_module()
L = G.L
import accounts  # noqa: E402
import autostart  # noqa: E402
import history  # noqa: E402
import i18n  # noqa: E402
import storage  # noqa: E402
import tempfile  # noqa: E402
import ui_accounts  # noqa: E402

storage.APPDIR = tempfile.mkdtemp(prefix="ailimits_gui_")  # история пишется во временную папку
RESET = history._iso(time.time() + 72 * 3600)

SAVED, SWITCHED, IDE_CALLS = [], [], []
STATE = {"week_a": 55.0, "ide_account": "a@example.com", "ide_ready_after": 0, "codex": False}


def rows(week, five, reset=None):
    return [{"name": "Неделя", "used": week, "resets_at": reset}, {"name": "5 часов", "used": five, "resets_at": None}]


def fake_ide_info():
    IDE_CALLS.append(time.time())
    ready = len(IDE_CALLS) > STATE["ide_ready_after"]
    acc = STATE["ide_account"]
    return {"running": True, "email": acc,
            "accounts": {acc: {"rows": rows(STATE["week_a"], 1.0, RESET), "plan": "Pro"}} if ready else {}}


G.load_settings = lambda: {"interval": 300, "warn": 80, "geometry": "500x640+120+80", "lang": "ru"}
G.save_settings = SAVED.append
L.load_accounts = lambda: [{"email": "a@example.com"}, {"email": "b@example.com"}]
L.claude_fetch = lambda profile=None: {"plan": "pro", "limits": rows(30.0 if profile else 10.0, 2.0)}
L.claude_installed = lambda: True
L.codex_installed = lambda: STATE["codex"]  # настоящий вход Codex не читаем; карточку включает отдельный шаг
L.codex_fetch = lambda profile=None: {"plan": "plus", "limits": rows(20.0, 5.0)}
L.stored_ide_account = lambda: STATE["ide_account"]  # запись входа IDE Antigravity — подменена
L.stored_ide_login = lambda: None
accounts.claude_ide_email = lambda: "me@example.com"  # аккаунты программ — вымышленные
accounts.codex_ide_email = lambda: "cx@example.com"
L.ag_fetch = lambda acc, a=False, l=None: {"plan": "Pro", "models": rows(40.0, 3.0), "credits": None,
                                           "source": "облако"}
L.merge_with_cache = lambda ag: ag
L.local_ide_info = fake_ide_info
L.ide_installed = lambda: True
L.ide_switch_account = lambda email, on_status=None: (SWITCHED.append(email), STATE.update(ide_account=email),
                                                      email)[2]
L.protect_stored_secrets = lambda: 0

# два часа назад у аккаунта a@ было 15 % недельного лимита, сейчас 55 %: 40 % за день -> остатка хватит на 27 часов
history.record(None, [("a@example.com", {"models": rows(15.0, 1.0, RESET)})], now=time.time() - 7200)

root = tk.Tk()
app = G.App(root)


def wait(seconds=0.3, until=None, error="условие не выполнилось за отведённое время"):
    """Шаг проверки: подождать seconds секунд либо до выполнения условия until (иначе — ошибка error)."""
    return seconds, until, error


FAILED = []


def drive(steps):
    """Выполняет шаги проверки внутри основного цикла окна: фоновые потоки программы обращаются
    к окну через root.after, а это работает только при запущенном цикле."""
    def fail():
        FAILED.append(traceback.format_exc())
        root.destroy()

    def advance():
        try:
            seconds, until, error = next(steps)
        except StopIteration:
            return
        except BaseException:
            return fail()
        poll(time.time() + seconds, until, error)

    def poll(end, until, error):
        try:
            if until and until():
                return root.after(10, advance)
            if time.time() >= end:
                if until:
                    raise AssertionError(error)
                return advance()
        except BaseException:
            return fail()
        root.after(20, poll, end, until, error)

    root.after(200, advance)
    root.mainloop()


def widgets(w):
    return 1 + sum(widgets(c) for c in w.winfo_children())


def walk_all(w):
    yield w
    for c in w.winfo_children():
        yield from walk_all(c)


def texts(w):
    out = []
    for c in w.winfo_children():
        try:
            out.append(str(c.cget("text")))
        except tk.TclError:
            pass
        out += texts(c)
    return out


def step(text):
    print("  ok ", text)


def main():
    print("Проверка окна (вымышленные данные)")
    yield wait(10, lambda: not app.loading and app.data, "данные не загрузились")
    info = app.tile_info
    assert app.card_order == ["claude", "a@example.com", "b@example.com"], app.card_order
    assert info["a@example.com"]["res"]["source"] == app.IDE_SRC and info["b@example.com"]["res"]["source"] == "облако"
    assert info["claude"]["title"] == "Claude Code" and info["a@example.com"]["title"] == "a", info  # имена при переходе
    assert app.names() == {"a@example.com": "a", "b@example.com": "b"} and app.s["accounts_v"] == 2
    assert app.cards["a@example.com"].title.cget("text") == "a" and app.cards["b@example.com"].title.cget("text") == "b"
    assert app.status.cget("text").startswith("Обновлено")
    step("плитки программ (Claude Code без имени, Antigravity под именем аккаунта IDE) и добавленный аккаунт;"
         " данные IDE важнее облачных; имена Google-аккаунтов — из email")

    card = " ".join(texts(app.cards["a@example.com"].outer) + texts(app.cards["b@example.com"].outer))
    assert "хватит" not in card and "облако" not in card and "Gemini" not in card, card  # ни прогноза, ни источника
    assert app.fc[("a@example.com", "Неделя")]["line"].startswith("хватит на 1 день 3 часа, до ")
    assert os.path.exists(history.history_file())
    assert getattr(app, "alert_win", None) is None and app.forecast_alerts() == []  # по умолчанию выключены
    app.s["forecast_alerts"] = True
    soon = app.forecast_alerts()
    assert len(soon) == 1 and soon[0][0] == "a", soon
    assert app.forecast_alerts() == []                                   # тот же расчёт — молчим
    key = ("a@example.com", "Неделя")
    at, eta = app.fc_alert_state[key]
    app.fc_alert_state[key] = (at - 7200, eta)
    assert app.forecast_alerts() == []                                   # час прошёл, но расчёт не изменился
    app.fc_alert_state[key] = (at - 600, eta - 7200)
    assert app.forecast_alerts() == []                                   # расчёт изменился, но часа не прошло
    app.fc_alert_state[key] = (at - 7200, eta - 7200)
    assert len(app.forecast_alerts()) == 1                               # и час прошёл, и расчёт изменился
    app.show_alert([], soon)
    yield wait()
    shown = texts(app.alert_win)
    assert "a" in shown and any(t.startswith("до ") for t in shown) and not any("неделя" in t for t in shown), shown
    app.hide_alert()
    app.s["forecast_alerts"] = False
    step("прогноз считается, но в карточках его нет; строки источника нет; всплывающее предупреждение выключено"
         " по умолчанию, не чаще раза в час")

    app.show_history("a@example.com", "Неделя", app.cards["a@example.com"].rows[0].f)
    yield wait()
    win = app.confirm_win
    assert win is not None and any("раньше сброса" in t for t in texts(win))
    yield wait(0.3)
    assert float(win.attributes("-alpha")) > 0.99                       # график проявился плавно и до конца
    cvs = [c for c in win.winfo_children()[0].winfo_children() if isinstance(c, tk.Canvas) and c.find_all()]
    assert cvs
    lines = [i for i in cvs[0].find_all() if cvs[0].type(i) == "line" and cvs[0].itemcget(i, "fill") == G.BLUE]
    wd = max(2, round(2 * app.root.winfo_fpixels("1i") / 96))
    assert lines and {float(cvs[0].itemcget(i, "width")) for i in lines} <= {wd, wd / 2}
    for i in lines:  # тонкие линии — только вертикальные спуски; горизонтальных на нуле нет
        c = cvs[0].coords(i)
        if float(cvs[0].itemcget(i, "width")) == wd / 2:
            assert len(c) == 4 and c[0] == c[2], c
    win.event_generate("<Escape>")
    yield wait()
    assert app.confirm_win is None
    row = app.cards["a@example.com"].rows[0].f
    app.show_history("a@example.com", "Неделя", row)
    yield wait()
    assert app.confirm_win is not None and "a  ·  Неделя" in texts(app.confirm_win.winfo_children()[0])
    app.show_history("a@example.com", "Неделя", row)                     # повторный щелчок по той же строке
    yield wait()
    assert app.confirm_win is None, "график не закрылся повторным щелчком"
    app.show_history("b@example.com", "5 часов", app.cards["b@example.com"].rows[1].f)
    yield wait()
    assert any("Прогноза нет" in t for t in texts(app.confirm_win))
    app.close_confirm()
    app.show_popup()
    yield wait()
    assert not any("хватит" in t for t in texts(app.popup)), texts(app.popup)
    box = app.popup.winfo_children()[0]
    labels = [w for w in walk_all(box) if isinstance(w, tk.Label)]
    xs = {w.winfo_x() for w in labels if w.cget("text") == "IDE"}
    assert xs and len(xs) == 1, xs                                      # метки IDE — одна под другой
    right = max(w.winfo_x() + w.winfo_width() for w in labels if w.cget("text").endswith("%"))
    strips = [w for w in box.grid_slaves(column=0) if isinstance(w, tk.Frame) and int(w.grid_info()["row"]) > 1]
    left = min(w.winfo_x() for w in strips)
    assert box.winfo_width() - right == left, (box.winfo_width() - right, left)  # поля справа и слева равны
    app.hide_popup()
    step("график расхода по щелчку на строке, повторный щелчок закрывает; в мини-окне трея прогноза нет")

    cards, count = dict(app.cards), widgets(app.body)
    STATE["week_a"] = 61.0
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert app.cards == cards and widgets(app.body) == count
    assert app.tile_info["a@example.com"]["res"]["models"][0]["used"] == 61.0
    assert "61%" in " ".join(texts(app.cards["a@example.com"].outer))
    step("обновление на месте: карточки и число виджетов прежние, значение новое")

    # сервер ответил 429: прежние данные остаются, запросы этой части — на паузе; данных нет — короткая строка
    calls, real_cf = [], L.claude_fetch

    def limited(profile=None):
        calls.append(profile)
        err = RuntimeError("HTTP 429: Rate limited. Please try again later.")
        err.code, err.retry_after = 429, 0
        raise err
    before = " ".join(texts(app.cards["claude"].outer))
    L.claude_fetch = limited
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert calls and " ".join(texts(app.cards["claude"].outer)) == before, texts(app.cards["claude"].outer)
    assert app.rate_pause[("ide", "claude")] > time.time() + 200
    n = len(calls)
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert len(calls) == n                                               # пауза: сервер не спрашиваем
    app.parts[("ide", "claude")], app.rate_pause = None, {}
    app.refresh()
    yield wait(10, lambda: not app.loading)
    t429 = " ".join(texts(app.cards["claude"].outer))
    assert "временно ограничил запросы" in t429 and "{" not in t429, t429
    L.claude_fetch, app.rate_pause = real_cf, {}
    app.refresh()
    yield wait(10, lambda: not app.loading and "%" in " ".join(texts(app.cards["claude"].outer)), "Claude не вернулся")
    step("сервер ответил 429: прежние данные остаются, пауза запросов; без данных — короткая строка вместо JSON")

    # нет связи (1.5.6): прежние данные остаются — бледные, значок OFFLINE; данных нет — OFFLINE и короткий текст
    def offline(profile=None):
        raise L.Offline("сеть: [Errno 11001] getaddrinfo failed")
    cc = app.cards["claude"]
    L.claude_fetch = offline
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert cc.badge.cget("text") == "OFFLINE" and cc.badge.winfo_ismapped() and cc.badge.cget("fg") == G.YELLOW
    assert "%" in " ".join(texts(cc.outer)) and "getaddrinfo" not in " ".join(texts(cc.outer))
    assert cc.rows[0].pct.cget("fg") != G.color_for(cc.rows[0].bar.used, app.warn)  # прежние данные — бледные
    app.show_popup()
    yield wait()
    assert "OFFLINE" in texts(app.popup) and "ошибка" not in texts(app.popup), texts(app.popup)
    app.hide_popup()
    app.parts[("ide", "claude")] = None
    app.refresh()
    yield wait(10, lambda: not app.loading)
    tx = " ".join(texts(cc.outer))
    assert cc.badge.cget("text") == "OFFLINE" and "Нет связи с сервером" in tx and "getaddrinfo" not in tx, tx
    L.claude_fetch = real_cf
    app.refresh()
    yield wait(10, lambda: not app.loading and "%" in " ".join(texts(cc.outer)), "Claude не вернулся")
    assert cc.badge.cget("text") != "OFFLINE"
    step("нет связи: значок OFFLINE, прежние данные бледные; без данных — «Нет связи с сервером»")

    real_ag = L.ag_fetch
    L.ag_fetch = lambda acc, a=False, l=None: dict(real_ag(acc, a, l), plan="Antigravity Starter Quota")
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert app.cards["b@example.com"].badge.cget("text") == "FREE", app.cards["b@example.com"].badge.cget("text")
    L.ag_fetch = real_ag
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert app.cards["b@example.com"].badge.cget("text") == "PRO"
    step("бесплатный тариф Google («Antigravity Starter Quota») — значок FREE")

    L.ag_fetch = lambda acc, a=False, l=None: dict(real_ag(acc, a, l), verify=True) if acc["email"] == "b@example.com" \
        else real_ag(acc, a, l)
    app.refresh()
    yield wait(10, lambda: not app.loading)
    cbv = app.cards["b@example.com"]
    assert cbv.badge.cget("text") == "LOGOUT" and cbv.badge.cget("fg") == G.RED, cbv.badge.cget("text")
    assert "Verify your account" in cbv.badge_tip.text
    assert cbv.ide_mode is None and not cbv.ide.winfo_ismapped()       # ни «→ в IDE», ни метки IDE
    assert all(r.bar.color == G.FAINT and r.pct.cget("fg") == G.FAINT for r in cbv.rows if r.bar.used), \
        [(r.bar.color, r.pct.cget("fg")) for r in cbv.rows]
    ca = app.cards["a@example.com"]
    assert ca.badge.cget("fg") == G.ACCENT["google"] and any(r.bar.color != G.FAINT for r in ca.rows if r.bar.used)
    L.ag_fetch = real_ag
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert cbv.badge.cget("text") == "PRO" and cbv.badge.cget("fg") != G.RED and not cbv.badge_tip.text
    step("Google просит подтвердить аккаунт — значок LOGOUT красным, полосы и проценты приглушены; потом — как было")

    app.open_menu()
    yield wait(0.5)
    assert float(app.menu_win.attributes("-alpha")) > 0.99            # проявилось до конца
    items = texts(app.menu_win)
    for need in ("Добавить аккаунт", "Управление аккаунтами", "Сворачивать в трей при закрытии", "Предупреждения по прогнозу", "Язык", "English", "Українська",
                 "Открыть папку данных", f"AI Limits {L.__version__}"):
        assert need in items, (need, items)
    assert not any("OAuth" in t for t in items)  # ключи задаются не в окне
    app.open_menu()
    assert app.menu_win is None
    step("меню настроек открывается и закрывается, пункты на месте")

    def seen():
        return " | ".join(texts(root)) + " | " + app.status.cget("text")
    cards = len(app.cards)
    for code, words in (("en", ("Refresh", "Week", "5 hours", "max", "Updated", "→ to IDE")),
                        ("uk", ("Оновити", "Тиждень", "5 годин", "макс.", "Оновлено", "→ в IDE")),
                        ("ru", ("Обновить", "Неделя", "5 часов", "макс.", "Обновлено"))):
        app.set_lang(code)
        yield wait()
        text = seen()
        for word in words:
            assert word in text, (code, word, text)
        assert len(app.cards) == cards and SAVED[-1]["lang"] == code
        if code != "ru":
            assert "Неделя" not in text and "Обновлено" not in text, (code, text)
            app.open_menu()
            yield wait()
            assert ("Language" if code == "en" else "Мова") in texts(app.menu_win)
            app.close_menu()
            app.show_popup()
            yield wait()
            assert any(("week" if code == "en" else "тиждень") == t for t in texts(app.popup)), texts(app.popup)
            app.hide_popup()
    assert i18n.T("нет такого перевода") == "нет такого перевода"
    step("язык интерфейса: английский, украинский и русский переключаются на лету и сохраняются")

    order_before, card_b = list(app.card_order), app.cards["b@example.com"]
    del IDE_CALLS[:]
    STATE["ide_ready_after"] = 2  # IDE отдаёт лимиты нового аккаунта только с третьего опроса
    app.switch_ide("b@example.com")
    yield wait()
    assert app.confirm_win is not None and "b@example.com" in " ".join(texts(app.confirm_win))
    app.confirm_win.event_generate("<Escape>")
    yield wait()
    assert app.confirm_win is None and not SWITCHED
    app.switch_ide("b@example.com")
    yield wait()
    app.confirm_win.event_generate("<Return>")
    yield wait(5, lambda: SWITCHED == ["b@example.com"])
    yield wait(15, lambda: app._ide_expect is None and not app.loading and not app.ide_switching, "нет данных IDE")
    t_ide = app.tile_info["b@example.com"]
    assert len(IDE_CALLS) == 3 and t_ide["ide"] and t_ide["res"]["source"] == app.IDE_SRC
    assert t_ide["title"] == "b" and not app.tile_info["a@example.com"]["ide"] and "antigravity" not in app.cards
    assert app.card_order == order_before, (order_before, app.card_order)  # плитки на местах, переехала метка IDE
    assert app.cards["b@example.com"] is card_b and card_b.ide_mode == "current" and app.cards["a@example.com"].ide_mode == "switch"
    assert "IDE теперь работает под b@example.com" == app.status.cget("text"), app.status.cget("text")
    assert not app.footer.winfo_ismapped()                              # сообщение занимает всю строку
    app.status_sticky = 0
    app.set_status_updated()
    yield wait()
    assert app.footer.winfo_ismapped() and app.status.cget("text").startswith("Обновлено")
    app.s["order"], app.collapsed = ["antigravity", "claude", "a@example.com"], {"antigravity"}  # порядок из 1.5.0
    app._last_sig = None
    app.redraw()
    yield wait()
    assert app.card_order == ["b@example.com", "claude", "a@example.com"] and app.collapsed == {"b@example.com"}
    app.s["order"], app.collapsed = [], set()
    app._last_sig = None
    app.redraw()
    yield wait()
    step("смена аккаунта: отмена, подтверждение, повтор опроса до появления данных IDE; плитки остаются на"
         " местах, метка «● IDE» переходит на новый аккаунт; на время сообщения «макс.» скрыто")

    # окно IDE открыто, а входа нет (сервера IDE нет): отдельной плитки нет, у аккаунта записи входа — «→ в IDE»
    L.local_ide_info = lambda: {"running": False, "window": True, "email": None, "accounts": {}}
    app.refresh()
    cb = app.cards["b@example.com"]
    yield wait(10, lambda: not app.loading and cb.ide_mode == "switch", "«● IDE» у IDE без входа")
    assert "antigravity" not in app.cards and cb.ide.cget("text") == "→ в IDE"
    assert app.cards["a@example.com"].ide_mode == "switch"
    # сервер новой IDE (ключ скрыт): аккаунт IDE — по записи входа, «● IDE»
    L.local_ide_info = lambda: {"running": False, "window": True, "hidden": True, "email": None, "accounts": {}}
    app.refresh()
    yield wait(10, lambda: not app.loading and cb.ide_mode == "current", "нет «● IDE» при новой IDE")
    assert cb.ide.cget("text") == "● IDE" and app.cards["a@example.com"].ide_mode == "switch"
    # аккаунт не в программе — полоса и белые надписи тусклее; в программе — как были
    ca = app.cards["a@example.com"]
    assert ca.quiet and not cb.quiet and cb.strip.cget("bg") == cb.accent and ca.strip.cget("bg") != ca.accent
    assert ca.title.cget("fg") != G.FG and cb.title.cget("fg") == G.FG
    assert ca.rows and ca.rows[0].label.cget("fg") != G.FG and cb.rows[0].label.cget("fg") == G.FG
    assert not app.cards["claude"].quiet                                 # «● Claude Code» — яркая
    assert ca.badge.cget("fg") != G.ACCENT["google"] and cb.badge.cget("fg") == G.ACCENT["google"]
    assert ca.rows[0].pct.cget("fg") != G.color_for(ca.rows[0].bar.used, app.warn)    # проценты и полосы — тоже
    assert ca.rows[0].bar.color == ca.rows[0].pct.cget("fg")
    assert cb.rows[0].pct.cget("fg") == G.color_for(cb.rows[0].bar.used, app.warn)
    L.local_ide_info = lambda: {"running": False, "window": True, "email": None, "accounts": {}}
    STATE["ide_account"] = None                                          # и записи входа нет — ни плитки, ни метки
    app.refresh()
    yield wait(10, lambda: not app.loading and cb.ide_mode == "switch", "метка IDE осталась без записи входа")
    assert "antigravity" not in app.cards
    STATE["ide_account"] = "b@example.com"
    # IDE закрыта: тоже «→ в IDE» (нажатие запустит IDE этим аккаунтом)
    L.local_ide_info = lambda: {"running": False, "window": False, "email": None, "accounts": {}}
    app.refresh()
    yield wait(10, lambda: not app.loading and app.tile_info["b@example.com"]["ide"], "нет записи входа IDE")
    yield wait()
    assert cb.ide_mode == "switch" and cb.ide.cget("text") == "→ в IDE", (cb.ide_mode, cb.ide.cget("text"))
    assert "○" not in " ".join(texts(app.body))                         # серой «○ IDE» нет (владелец)
    L.local_ide_info = fake_ide_info
    app.refresh()
    yield wait(10, lambda: not app.loading and app.cards["b@example.com"].ide_mode == "current", "IDE не вернулась")
    assert app.cards["b@example.com"].ide.cget("text") == "● IDE"
    step("IDE открыта без входа или закрыта — у аккаунта записи входа «→ в IDE», без лишней плитки и меток")

    app.alerted = set()
    fake = [("claude", {"kind": "claude", "ident": "claude:me@example.com", "title": "Claude Code", "ide": True,
                        "res": {"plan": "pro", "limits": rows(85.0, 2.0)}})]
    app.check_alerts(fake)
    yield wait()
    assert app.alert_win is not None and any("85" in t for t in texts(app.alert_win))
    app.hide_alert()
    app.warn = 0
    fake[0][1]["res"] = {"plan": "pro", "limits": rows(99.0, 2.0)}
    app.check_alerts(fake)
    yield wait()
    assert app.alert_win is None
    step("предупреждение о пороге появляется; при «выкл» — нет")

    if app.tray:
        app.q.put("hover_on")
        yield wait(0.25)
        assert getattr(app, "popup", None) is None, "мини-окно появилось раньше полсекунды"
        yield wait(1, lambda: getattr(app, "popup", None) is not None, "мини-окно не появилось через полсекунды")
        a0 = float(app.popup.attributes("-alpha"))
        yield wait(0.4)
        assert a0 < 1 and float(app.popup.attributes("-alpha")) > 0.99, (a0, app.popup.attributes("-alpha"))
        app.q.put("hover_off")
        yield wait(0.3)
        assert app.popup is None
        app.q.put("hover_on")
        yield wait(0.2)
        app.q.put("hover_off")                                         # мышь ушла раньше полсекунды
        yield wait(1)
        assert app.popup is None, "мини-окно появилось, хотя мышь ушла"
        step("мини-окно трея: через полсекунды наведения, плавно проявляется; мышь ушла раньше — не появляется")

    app.show_tray_menu(400, 400)
    yield wait()
    assert {"Открыть", "Обновить", "Выход"} <= set(texts(app.tray_menu))
    app.close_tray_menu()
    assert app.tray_menu is None
    step("меню иконки в трее")

    E = types.SimpleNamespace  # событие мыши: нужны только координаты экрана
    cl, ca, cb = (app.cards[k] for k in ("claude", "b@example.com", "a@example.com"))
    tx, ty = cl.outer.winfo_rootx() + 30, cl.outer.winfo_rooty() + 5
    assert cb.strip.winfo_width() >= 12 and str(cb.strip.cget("cursor")) == "fleur"
    cb.strip_hover(True)
    assert cb.strip.cget("bg") != cb.strip_color()                      # наведение на полоску — светлее
    cb.strip_hover(False)
    assert cb.strip.cget("bg") == cb.strip_color()
    bx, by = cb.strip.winfo_rootx() + 5, cb.strip.winfo_rooty() + 20
    app._drag_press(E(x_root=bx, y_root=by), cb)
    app._drag_motion(E(x_root=bx, y_root=by - 3))                       # меньше порога — ещё щелчок
    assert not app._drag["on"] and app.card_order == ["claude", "a@example.com", "b@example.com"]
    y_claude = cl.outer.winfo_y()
    app._drag_motion(E(x_root=tx, y_root=ty))
    assert app.card_order == ["a@example.com", "claude", "b@example.com"], app.card_order
    assert cl.outer.place_info() and "claude" in app._dnd["anim"]       # плитка Claude поехала вниз
    yield wait(0.1)
    mid = cl.outer.winfo_y()
    assert y_claude < mid < app._slot["claude"][1], (y_claude, mid, app._slot["claude"])  # плавно, а не скачком
    app._drag_release(E(x_root=tx, y_root=ty))
    yield wait(1, lambda: app._dnd is None, "плитка не доехала до места")
    assert SAVED[-1]["order"] == ["a@example.com", "claude", "b@example.com"]
    assert [int(app.cards[k].outer.grid_info()["row"]) for k in app.card_order] == [0, 1, 2]
    app.show_popup()
    yield wait()
    t = texts(app.popup)
    assert t.index("a") < t.index("Claude Code") < t.index("b"), t       # мини-окно трея — в том же порядке
    app.hide_popup()
    app.show_accounts()
    yield wait()
    t = [x.strip() for x in texts(app.menu_win)]
    assert t.index("a") < t.index("b"), t                               # «Управление аккаунтами» — тоже
    app.close_menu()
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert app.card_order == ["a@example.com", "claude", "b@example.com"]
    step("перетаскивание плитки за цветную полоску (плавно): порядок сохраняется, его повторяют мини-окно трея и меню")

    w0 = root.winfo_width()
    app.toggle_two_columns()
    yield wait(0.5)
    assert SAVED[-1]["two_columns"] and root.winfo_width() > w0 * 1.5, (w0, root.winfo_width())
    pos = {k: (int(app.cards[k].outer.grid_info()["row"]), int(app.cards[k].outer.grid_info()["column"]))
           for k in app.card_order}
    assert pos == {"a@example.com": (0, 0), "claude": (0, 1), "b@example.com": (1, 0)}, pos
    assert cb.outer.winfo_height() == cl.outer.winfo_height()           # карточки одной строки — одной высоты
    assert cb.outer.winfo_rootx() < cl.outer.winfo_rootx()
    ax, ay = ca.strip.winfo_rootx() + 5, ca.strip.winfo_rooty() + 20
    app._drag_press(E(x_root=ax, y_root=ay), ca)
    app._drag_motion(E(x_root=cb.outer.winfo_rootx() + 10, y_root=cb.outer.winfo_rooty() + 10))
    app._drag_release(E(x_root=0, y_root=0))
    assert app.card_order == ["b@example.com", "a@example.com", "claude"], app.card_order
    yield wait(1, lambda: app._dnd is None, "плитка не доехала до места")
    assert int(cl.outer.grid_info()["row"]) == 1
    app._show_menu(False)
    yield wait()
    item = next(w for w in app.menu_win.winfo_children()[0].winfo_children()
                if "Карточки в две колонки" in texts(w))
    item.winfo_children()[-1].event_generate("<Button-1>")              # галочка в меню — как щелчком
    yield wait(0.5)
    right = app.refresh_btn.winfo_rootx() + app.refresh_btn.winfo_width()
    assert app.menu_win and abs(app.menu_win.winfo_rootx() + app.menu_win.winfo_width() - right) < 4,         "меню не переехало за кнопкой ⚙"

    def chip(text):
        return next(w for w in walk_all(app.menu_win) if isinstance(w, tk.Label) and w.cget("text") == text)
    errors = []
    app.root.report_callback_exception = lambda *a: errors.append(a[1])
    old = app.warn
    on = __import__("ui_theme").BLUE                                    # выбранный порог — синий
    chip("90%").event_generate("<Button-1>")                            # при загруженных данных (22.11.2026:
    yield wait(0.3)                                                     # render(*data) падал, меню не обновлялось)
    assert app.warn == 90 and chip("90%").cget("bg") == on and chip("80%").cget("bg") != on, errors
    chip("80%").event_generate("<Button-1>")
    yield wait(0.3)
    assert app.warn == 80 and chip("80%").cget("bg") == on and chip("90%").cget("bg") != on and not errors, errors
    app.warn = old
    app.close_menu()
    assert not SAVED[-1]["two_columns"] and abs(root.winfo_width() - w0) < 4, (w0, root.winfo_width())
    assert {int(app.cards[k].outer.grid_info()["column"]) for k in app.card_order} == {0}
    app.s["order"] = []
    app.render(app.data)
    yield wait()
    assert app.card_order == ["claude", "a@example.com", "b@example.com"]
    step("две колонки: окно расширяется, перетаскивание по сетке, возврат в одну колонку; меню ⚙ следует за кнопкой")

    cl.title.event_generate("<ButtonPress-1>")                         # щелчок по названию не сворачивает
    cl.title.event_generate("<ButtonRelease-1>")
    yield wait()
    assert "claude" not in app.collapsed
    assert cl.arrow.winfo_reqheight() <= cl.title.winfo_reqheight()     # стрелка не выше названия: строка прежняя
    assert cl.arrow.winfo_reqwidth() > cl.arrow.winfo_reqheight() * 0.9 and cl.arrow.cget("text") == "▼"
    h0 = root.winfo_height()
    cl.arrow.event_generate("<Button-1>")
    yield wait(0.5)
    assert "claude" in app.collapsed
    assert root.winfo_height() < h0 - 40, (h0, root.winfo_height())     # окно подогналось под свёрнутую плитку
    cl.arrow.event_generate("<Button-1>")
    yield wait(0.5)
    assert "claude" not in app.collapsed and abs(root.winfo_height() - h0) < 4, (h0, root.winfo_height())
    cl.arrow.event_generate("<Button-1>")
    yield wait()
    assert "claude" in app.collapsed and SAVED and "claude" in SAVED[-1]["collapsed"]
    assert cl.summary.cget("text") == "90%", cl.summary.cget("text")    # свёрнутая: остаток недели, без «макс»
    app.toggle("a@example.com")
    yield wait()
    week_b = next(m["used"] for m in app.tile_info["a@example.com"]["res"]["models"] if m["name"] == "Неделя")
    assert cb.summary.cget("text") == f"{100 - week_b:.0f}%", (cb.summary.cget("text"), week_b)
    cb.full_title = "very-long-address-for-a-narrow-card@example.com"
    cb.fit_title()
    yield wait()
    assert cb.title.cget("text").endswith("…") and cb.head.winfo_reqwidth() <= cb.head.winfo_width() + 2,         (cb.title.cget("text"), cb.head.winfo_reqwidth(), cb.head.winfo_width())  # «→ в IDE» не обрезается
    cb.full_title = "a"
    cb.fit_title()
    app.toggle("a@example.com")
    app.toggle("claude")
    yield wait()
    step("свёрнутая плитка: остаток недельного лимита без «макс»; длинный email укорачивается, кнопка видна")

    status = app.status.cget("text")
    assert status.startswith("Обновлено") and "авто" not in status, status
    assert app.footer.master is app.status_row and app.footer.winfo_ismapped()
    assert app.footer.winfo_rootx() > app.status.winfo_rootx()          # «макс.» — справа в строке статуса
    labels = app.footer.winfo_children()
    assert "→" not in [w.cget("text") for w in labels] and len(labels) == 3
    assert labels[0].cget("text") == "макс." and "bold" not in str(labels[1].cget("font"))
    assert "bold" in str(labels[-1].cget("font")) and labels[-1].cget("text").endswith("%")
    left = {t["title"]: 100 - next(r["used"] for r in (t["res"].get("models") or t["res"].get("limits"))
                                   if r["name"] == "Неделя")
            for _, t in app.data if isinstance(t["res"], dict)}
    top = max(left, key=left.get)
    assert labels[1].cget("text") == top and labels[-1].cget("text") == f"{left[top]:.0f}%", (left, labels[1].cget("text"))
    assert app.tile_info["claude"]["title"] == top and labels[1].cget("fg") == G.ACCENT["claude"]  # не Google — тоже в счёт
    assert L.best_weekly([("x", {"limits": [{"name": "Неделя Opus", "used": 0.0}, {"name": "Неделя", "used": 40.0}]}),
                          ("y", {"models": [{"name": "Неделя", "used": 50.0}]})]) == ("x", 60.0)
    step("строка статуса: «Обновлено ЧЧ:ММ» без автообновления, справа «макс. email N%» без стрелки")

    tip = cb.ide_tip                                                    # «Сделать этот аккаунт текущим в IDE…»
    tip.show(None)
    yield wait()
    right = root.winfo_rootx() + root.winfo_width()
    assert tip.tip.winfo_rootx() + tip.tip.winfo_width() <= right, (tip.tip.winfo_rootx(), tip.tip.winfo_width(), right)
    tip.hide(None)
    step("всплывающая подсказка не выходит за правый край окна")

    if app.tray:
        app._fg_at = time.time()                                        # окно в фокусе -> щелчок по иконке прячет
        app.q.put("toggle")
        yield wait(1, lambda: root.state() == "withdrawn", "окно не ушло в трей")
        app.q.put("toggle")                                             # в трее -> показать
        yield wait(1, lambda: root.state() == "normal", "окно не показалось")
        app._fg_at = 0                                                  # открыто, но не в фокусе -> только фокус
        root.after(0, lambda: None)
        app.q.put("toggle")
        yield wait(0.4)
        assert root.state() == "normal"
        step("щелчок по иконке трея: окно в фокусе — в трей, иначе — показать и дать фокус")
    cmd = autostart.autostart_command()
    assert "--autostart" in cmd and ("limits_gui.pyw" in cmd or getattr(sys, "frozen", False)), cmd
    step("сворачивание карточки сохраняется в настройках; команда автозапуска указывает на окно")

    STATE["codex"] = True
    app.refresh()
    yield wait(10, lambda: not app.loading and "codex" in app.cards, "карточка Codex не появилась")
    card = " ".join(texts(app.cards["codex"].outer))
    assert "Codex" in card and "PLUS" in card and "20%" in card and "5%" in card, card
    assert app.card_order == ["claude", "codex", "a@example.com", "b@example.com"], app.card_order  # программы — первыми
    app.s["order"] = ["a@example.com", "claude", "b@example.com"]         # порядок, сохранённый до появления Codex
    app.render(app.data)
    yield wait()
    assert app.card_order[-1] == "codex", app.card_order                # новая карточка — в конце, как новый аккаунт
    app.s["order"] = []
    app.render(app.data)
    app.show_popup()
    yield wait()
    assert "Codex" in texts(app.popup), texts(app.popup)
    app.hide_popup()
    assert history.series("codex:cx@example.com", "Неделя", 0), "Codex не пишется в историю"
    STATE["codex"] = False
    app.refresh()
    yield wait(10, lambda: not app.loading and "codex" not in app.cards, "карточка Codex не исчезла")
    step("карточка Codex: есть вход Codex — есть карточка (неделя, 5 часов, план), мини-окно и история; нет — нет")

    # переименование прямо в плитке: двойной щелчок по имени, Enter; дубликат — отказ
    ccl = app.cards["claude"]
    assert "<Double-Button-1>" in ccl.title.bind()                       # двойной щелчок по имени привязан
    app.begin_rename("claude")                                          # (Tk не умеет имитировать двойной щелчок)
    yield wait()
    ent = app.rename_entry
    assert ent.winfo_ismapped() and ent.get() == "", ent.get()           # безымянная плитка — поле пустое
    ent.insert(0, "b")
    ent.event_generate("<Return>")
    yield wait()
    assert ent.winfo_exists() and "claude:me@example.com" not in app.names()  # «b» занято — не применилось
    assert any("занято" in x for x in texts(ccl.title.master)), texts(ccl.title.master)
    ent.delete(0, "end")
    ent.insert(0, "  Работа  ")
    ent.event_generate("<Return>")
    yield wait()
    assert not ent.winfo_exists() and app.names()["claude:me@example.com"] == "Работа"
    assert ccl.title.cget("text") == "Работа" and app.tile_info["claude"]["title"] == "Работа"
    assert accounts.name_error("работа", list(app.names().values())) and accounts.name_error("Codex", [])
    # щелчок мышью в любом месте, кроме поля, — выход из ввода (22.11.2026): годное имя сохраняется, негодное — нет
    elsewhere = app.cards["a@example.com"].rows[0].label
    app.begin_rename("claude")
    yield wait()
    ent = app.rename_entry
    ent.event_generate("<Button-1>")                                    # щелчок в само поле — ввод продолжается
    yield wait()
    assert ent.winfo_exists()
    ent.delete(0, "end")
    ent.insert(0, "Дом")
    elsewhere.event_generate("<Button-1>")
    yield wait()
    assert not ent.winfo_exists() and app.names()["claude:me@example.com"] == "Дом", app.names()
    app.begin_rename("claude")
    yield wait()
    ent = app.rename_entry
    ent.delete(0, "end")
    ent.insert(0, "b")                                                  # занято
    ent.event_generate("<Return>")
    yield wait()
    assert ent.winfo_exists()
    elsewhere.event_generate("<Button-1>")                              # щелчок мимо — выход без сохранения
    yield wait()
    assert not ent.winfo_exists() and app.names()["claude:me@example.com"] == "Дом"
    assert not any("занято" in x for x in texts(ccl.title.master)) and ccl.title.winfo_ismapped()
    app.set_name("claude:me@example.com", "Работа")
    yield wait()
    step("переименование двойным щелчком по имени в плитке; дубликат и название программы не применяются; щелчок мимо")

    # «Управление аккаунтами»: раскрывающийся пункт меню ⚙ (как «Добавить аккаунт»), группы по сервисам, имя и email
    app.open_menu()
    yield wait()

    def menu_item(name):
        return next(w for w in app.menu_win.winfo_children()[0].winfo_children() if name in texts(w))
    assert "Работа" not in texts(app.menu_win)                           # открывается свёрнутым
    menu_item("Добавить аккаунт").winfo_children()[-1].event_generate("<Button-1>")
    yield wait()
    colors = {w.cget("text").strip(): w.cget("fg") for w in app.menu_win.winfo_children()[0].winfo_children()
              for w in w.winfo_children() if isinstance(w, tk.Label) and w.cget("text").strip() in ("Claude", "ChatGPT", "Google")}
    assert colors == {"Claude": G.ACCENT["claude"], "ChatGPT": G.ACCENT["chatgpt"], "Google": G.ACCENT["google"]}, colors
    item = menu_item("Управление аккаунтами")
    assert item.winfo_children()[0].cget("text") == "▸"
    item.winfo_children()[-1].event_generate("<Button-1>")
    yield wait()
    t = texts(app.menu_win)
    for need in ("Управление аккаунтами", "Claude", "ChatGPT", "Google", "Работа", "me@example.com  ·  из программы",
                 "a", "a@example.com", "b", "b@example.com", "Поверх всех окон", "▾"):
        assert need in t, (need, t)
    assert "←" not in t
    assert t.index("Управление аккаунтами") < t.index("Работа") < t.index("a@example.com") < t.index("Поверх всех окон")
    # ✎ дважды подряд (поле ещё открыто, например после «имя занято») — без ошибки, то же поле
    errors = []
    app.root.report_callback_exception = lambda *a: errors.append(a[1])
    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)
    pen = next(w for w in walk(app.menu_win) if isinstance(w, tk.Label) and w.cget("text") == "✎")
    pen.event_generate("<Button-1>")
    yield wait()
    first = app.rename_entry
    first.delete(0, "end")
    first.insert(0, "a")                                                  # занято — поле остаётся
    first.event_generate("<Return>")
    yield wait()
    pen.event_generate("<Button-1>")
    yield wait()
    assert not errors, errors
    assert app.rename_entry is first and first.winfo_exists()
    first.event_generate("<Escape>")
    yield wait()
    assert not first.winfo_exists() and "Работа" in texts(app.menu_win), texts(app.menu_win)
    menu_item("Управление аккаунтами").winfo_children()[-1].event_generate("<Button-1>")  # повторный щелчок — свернуть
    yield wait()
    assert "Работа" not in texts(app.menu_win) and "Добавить аккаунт" in texts(app.menu_win)
    app.close_menu()
    step("«Управление аккаунтами» — раскрывающийся пункт меню ⚙, группы по сервисам, имя и email мелко;"
         " сервисы в «Добавить аккаунт» — их цветами")
    # добавление аккаунтов Claude и ChatGPT (вход программы подменён): совпал с программой — плитка получает имя
    STATE["codex"] = True
    started = []

    def fake_start(kind):
        started.append(kind)
        return {"kind": kind, "dir": f"{kind}-{len(started)}"}

    def fake_finish(p, **k):
        os.makedirs(os.path.join(accounts.profiles_dir(), p["dir"]), exist_ok=True)
        p["email"] = {"chatgpt": "cx@example.com", "claude": "second@example.com"}[p["kind"]]
        return p
    accounts.start_login, accounts.finish_login = fake_start, fake_finish
    real_finish = fake_finish

    def waiting_finish(p, **k):  # вход в браузере ещё не завершён — ждём отмены
        for _ in range(100):
            if p.get("_cancel"):
                raise RuntimeError("отменено")
            time.sleep(0.05)
        return real_finish(p)
    accounts.finish_login = waiting_finish
    app.add_account("chatgpt")
    yield wait()
    assert app.adding and app.cancel_lbl.winfo_ismapped() and "браузере" in app.status.cget("text")
    app.add_account("claude")                                            # новый вход отменяет незавершённый
    yield wait()
    assert app.adding and app._add_profile["kind"] == "claude"
    app.cancel_lbl.event_generate("<Button-1>")                         # «Отменить» в строке статуса
    yield wait(1)
    assert not app.adding and not app.cancel_lbl.winfo_ismapped() and app.status.cget("text") == "Вход отменён"
    assert len(accounts.load_profiles()) == 0
    accounts.finish_login = real_finish
    step("вход без окна консоли: «Отменить» в строке статуса, новый «Добавить аккаунт» отменяет незавершённый")
    app.refresh()
    yield wait(10, lambda: not app.loading and "codex" in app.cards, "нет плитки Codex")
    at = app.card_order.index("codex")
    app.add_account("chatgpt")
    yield wait(10, lambda: not app.adding and not app.loading and "codex:cx@example.com" in app.cards,
               "ChatGPT не добавился")
    tcx = app.tile_info["codex:cx@example.com"]
    assert app.names()["codex:cx@example.com"] == "cx" and tcx["title"] == "cx" and tcx["ide"]
    assert tcx["res"]["plan"] and "codex" not in app.cards and "называется" in app.status.cget("text"), \
        (list(app.cards), app.status.cget("text"))
    assert app.card_order.index("codex:cx@example.com") == at, (at, app.card_order)  # на месте плитки Codex
    app.add_account("claude")
    yield wait(10, lambda: not app.adding and not app.loading and "claude:second@example.com" in app.cards,
               "Claude не добавился")
    t2 = app.tile_info["claude:second@example.com"]
    yield wait(0.5)
    assert abs(root.winfo_height() - (app.cv.winfo_rooty() - root.winfo_rooty() + app.body.winfo_reqheight() + 14)) < 4         or root.winfo_height() >= root.winfo_screenheight() - 130, "окно не подогналось под новую плитку"
    assert t2["title"] == "second" and t2["res"]["limits"][0]["used"] == 30.0 and not t2["ide"]
    c3 = app.cards["claude:second@example.com"]
    assert c3.ide_mode == "switch_claude" and c3.ide.cget("text") == "→ в Claude", (c3.ide_mode, c3.ide.cget("text"))
    assert app.cards["claude"].ide_mode == "current_claude"           # недобавленный аккаунт Claude Code
    assert app.cards["claude"].ide.cget("text") == "● Claude Code", app.cards["claude"].ide.cget("text")
    real_cl = ui_accounts.CL.switch
    got = []
    ui_accounts.CL.switch = lambda p, on_status=None: got.append(p["email"]) or {
        "email": p["email"], "kept": {"kind": "claude", "email": "me@example.com", "dir": "claude-me"}, "created": True}
    c3.ide.event_generate("<Button-1>")
    yield wait()
    assert "Переключить Claude Code на second@example.com?" in texts(app.confirm_win)
    assert any("открытые — под прежним" in x for x in texts(app.confirm_win))  # предупреждение об открытых сеансах
    app.confirm_win.event_generate("<Return>")
    yield wait(5, lambda: got == ["second@example.com"] and not app.prog_switching, "Claude не переключился")
    assert app.status.cget("text") == "Claude Code теперь работает под second@example.com"
    assert app.names().get("claude:me@example.com") == "Работа"         # имя прежнего аккаунта сохранилось
    ui_accounts.CL.switch = real_cl
    app.status_sticky = 0
    app.add_account("claude")
    yield wait(10, lambda: not app.adding, "повтор не завершился")
    assert "уже добавлен" in app.status.cget("text") and len(accounts.load_profiles()) == 2

    # ↻ «войти заново» в «Управлении аккаунтами»: тот же аккаунт — вход заменён; другой — не тронут
    app.show_accounts()
    yield wait()
    assert texts(app.menu_win).count("↻") == 4, texts(app.menu_win)    # a, b, cx, second — у «из программы» нет
    app.close_menu()
    prof2 = next(q for q in accounts.load_profiles() if q["email"] == "second@example.com")
    with open(os.path.join(accounts.profiles_dir(), prof2["dir"], "creds.dat"), "w") as f:
        f.write("old")

    def finish_fresh(p, **k):
        p = real_finish(p)
        with open(os.path.join(accounts.profiles_dir(), p["dir"], "creds.dat"), "w") as f:
            f.write("fresh")
        return p
    accounts.finish_login = finish_fresh
    app.relogin("claude", "claude:second@example.com", "second@example.com", prof2)
    yield wait(10, lambda: not app.adding, "повторный вход Claude не завершился")
    assert app.status.cget("text") == "Вход «second» обновлён", app.status.cget("text")
    with open(os.path.join(accounts.profiles_dir(), prof2["dir"], "creds.dat")) as f:
        assert f.read() == "fresh"
    assert len(accounts.load_profiles()) == 2 and not os.path.exists(
        os.path.join(accounts.profiles_dir(), "claude-%d" % len(started)))  # временная папка входа убрана
    prof_cx = next(q for q in accounts.load_profiles() if q["kind"] == "chatgpt")
    accounts.finish_login = lambda p, **k: dict(real_finish(p), email="zz@example.com")
    app.relogin("chatgpt", "codex:cx@example.com", "cx@example.com", prof_cx)
    yield wait(10, lambda: not app.adding, "повторный вход ChatGPT не завершился")
    assert "не обновлён" in app.status.cget("text") and "zz@example.com" in app.status.cget("text")
    assert [q["email"] for q in accounts.load_profiles() if q["kind"] == "chatgpt"] == ["cx@example.com"]
    accounts.finish_login = real_finish
    saved, hints = [], []
    real_save, L.save_accounts = L.save_accounts, saved.append
    L.ag_login = lambda login_hint=None, expect=None: hints.append(login_hint) or {"email": "x@example.com", "refresh_token": "t"}
    app.relogin("google", "a@example.com", "a@example.com")
    yield wait(10, lambda: not app.adding, "повторный вход Google не завершился")
    assert hints == ["a@example.com"] and not saved and "не обновлён" in app.status.cget("text")
    L.ag_login = lambda login_hint=None, expect=None: {"email": "A@example.com", "refresh_token": "t2"}
    app.relogin("google", "a@example.com", "a@example.com")
    yield wait(10, lambda: not app.adding, "повторный вход Google не завершился")
    assert saved and [x["email"] for x in saved[-1]] == ["b@example.com", "A@example.com"], saved
    assert app.status.cget("text") == "Вход «a» обновлён", app.status.cget("text")
    L.save_accounts = real_save
    app.status_sticky = 0
    step("↻ в «Управлении аккаунтами»: повторный вход заменяет вход того же аккаунта; другой аккаунт — отказ")
    assert accounts.suggest_name("chatgpt", "b@example.com", list(app.names().values())) == "Codex b"
    step("«Добавить аккаунт»: совпавший с программой — имя у плитки программы; другой — своя плитка;"
         " повтор не добавляется; занятое имя — с приставкой сервиса")

    # «→ в Codex»: у добавленного аккаунта ChatGPT, в который Codex не вошёл, — кнопка того же вида, что «→ в IDE»
    other = {"kind": "chatgpt", "dir": "chatgpt-other", "email": "cx2@example.com", "account_id": "acc-cx2"}
    os.makedirs(os.path.join(accounts.profiles_dir(), other["dir"]), exist_ok=True)
    accounts.save_profiles(accounts.load_profiles() + [other])
    app.refresh()
    yield wait(10, lambda: not app.loading and "codex:cx2@example.com" in app.cards, "нет плитки второго ChatGPT")
    c2 = app.cards["codex:cx2@example.com"]
    assert c2.ide_mode == "switch_codex" and c2.ide.cget("text") == "→ в Codex", (c2.ide_mode, c2.ide.cget("text"))
    assert app.cards["codex:cx@example.com"].ide_mode == "current_codex"
    assert app.cards["codex:cx@example.com"].ide.cget("text") == "● Codex"
    assert app.cards["a@example.com"].ide.cget("text") in ("● IDE", "→ в IDE")
    assert c2.ide.cget("bg") == app.cards["a@example.com"].ide.cget("bg")  # одного вида с «→ в IDE»
    switched = []
    real_switch = ui_accounts.CX.switch

    def fake_switch(p, on_status=None):
        switched.append(p["email"])
        on_status("Codex: закрываю приложение…")
        return {"email": p["email"], "kept": None, "created": False, "restarted": True}
    ui_accounts.CX.switch = fake_switch
    c2.ide.event_generate("<Button-1>")
    yield wait()
    assert app.confirm_win is not None and "Переключить Codex на cx2@example.com?" in texts(app.confirm_win)
    app.confirm_win.event_generate("<Return>")
    yield wait(5, lambda: switched == ["cx2@example.com"] and not app.prog_switching, "Codex не переключился")
    assert app.status.cget("text") == "Codex теперь работает под cx2@example.com", app.status.cget("text")
    ui_accounts.CX.switch = real_switch
    accounts.remove_profile(other)
    app.status_sticky = 0
    app.refresh()
    yield wait(10, lambda: not app.loading and "codex:cx2@example.com" not in app.cards, "плитка не убралась")
    step("«→ в Codex» у другого аккаунта ChatGPT (вид как у «→ в IDE»), подтверждение, смена; у текущего — «● Codex»")

    # удаление: профиль и его папка, имя; аккаунт программы удалить нельзя
    prof = next(p for p in accounts.load_profiles() if p["kind"] == "claude")
    app.show_accounts()
    yield wait()
    cx, cy = root.winfo_rootx() + root.winfo_width() // 2, root.winfo_rooty() + 120
    root.winfo_pointerxy = lambda: (cx, cy)                             # указатель — над окном
    app.remove_account("claude:second@example.com", anchor=app.menu_win.winfo_children()[0])  # ✕ в меню
    yield wait()
    cw = app.confirm_win
    del root.winfo_pointerxy
    wx, wy, ww, wh = cw.winfo_rootx(), cw.winfo_rooty(), cw.winfo_width(), cw.winfo_height()
    assert root.winfo_rootx() <= wx and wx + ww <= root.winfo_rootx() + root.winfo_width(), (wx, ww)
    assert root.winfo_rooty() <= wy and wy + wh <= root.winfo_rooty() + root.winfo_height(), (wy, wh)
    assert wy >= cy + 20 or wy + wh <= cy - 20, (wy, wh, cy)               # рядом с указателем, но не вплотную
    cw.event_generate("<Return>")
    yield wait(10, lambda: not app.loading and "claude:second@example.com" not in app.cards, "аккаунт не удалился")
    assert not os.path.exists(os.path.join(accounts.profiles_dir(), prof["dir"]))
    assert "claude:second@example.com" not in app.names()
    app.remove_account("claude:me@example.com")                         # аккаунт программы — не удаляется
    yield wait()
    assert app.confirm_win is None
    STATE["codex"] = False
    step("удаление аккаунта: профиль, папка и имя; аккаунт программы удалить нельзя")

    print("Все проверки окна пройдены.")
    app.quit_app()


if __name__ == "__main__":
    drive(main())
    if FAILED:
        print(FAILED[0])
        sys.exit(1)
