"""Проверка окна AI Limits на вымышленных данных.

Окно открывается на несколько секунд; запросы, настройки, ключи и смена аккаунта IDE подменены —
настоящие данные и настройки не читаются и не меняются. Запуск: python tests\\test_gui.py
"""
import os
import sys
import time
import tkinter as tk
import traceback
from importlib.machinery import SourceFileLoader

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)
G = SourceFileLoader("limits_gui", os.path.join(SRC, "limits_gui.pyw")).load_module()
L = G.L
import autostart  # noqa: E402
import history  # noqa: E402
import i18n  # noqa: E402
import storage  # noqa: E402
import tempfile  # noqa: E402

storage.APPDIR = tempfile.mkdtemp(prefix="ailimits_gui_")  # история пишется во временную папку
RESET = history._iso(time.time() + 72 * 3600)

SAVED, SWITCHED, IDE_CALLS = [], [], []
STATE = {"week_a": 55.0, "ide_account": "a@example.com", "ide_ready_after": 0}


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
L.claude_fetch = lambda: {"plan": "pro", "limits": rows(10.0, 2.0)}
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
    yield wait(10, lambda: not app.loading and app.data and app.data[0], "данные не загрузились")
    assert app.card_order == ["claude", "a@example.com", "b@example.com"], app.card_order
    assert app.ag_res["a@example.com"]["source"] == app.IDE_SRC and app.ag_res["b@example.com"]["source"] == "облако"
    assert app.status.cget("text").startswith("Обновлено")
    step("карточки Claude и двух аккаунтов; данные IDE важнее облачных")

    card = " ".join(texts(app.cards["a@example.com"].outer))
    assert "при таком темпе хватит на 1 день 3 часа, до " in card and app.cards["a@example.com"].rows[0]._fc_on, card
    assert not app.cards["a@example.com"].rows[1]._fc_on and not app.cards["b@example.com"].rows[0]._fc_on
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
    step("прогноз: строка в карточке; всплывающее предупреждение выключено по умолчанию, не чаще раза в час")

    app.show_history("a@example.com", "Неделя", app.cards["a@example.com"].rows[0].f)
    yield wait()
    win = app.confirm_win
    assert win is not None and any("раньше сброса" in t for t in texts(win))
    assert any(isinstance(c, tk.Canvas) and c.find_all() for c in win.winfo_children()[0].winfo_children())
    win.event_generate("<Escape>")
    yield wait()
    assert app.confirm_win is None
    app.show_history("b@example.com", "5 часов", app.cards["b@example.com"].rows[1].f)
    yield wait()
    assert any("Прогноза нет" in t for t in texts(app.confirm_win))
    app.close_confirm()
    app.show_popup()
    yield wait()
    assert any(t.startswith("a — хватит на 1 день") for t in texts(app.popup)), texts(app.popup)
    assert not any("5 час" in t and "хватит" in t for t in texts(app.popup))
    app.hide_popup()
    step("график расхода по щелчку на строке; прогноз в мини-окне трея")

    cards, count = dict(app.cards), widgets(app.body)
    STATE["week_a"] = 61.0
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert app.cards == cards and widgets(app.body) == count
    assert app.ag_res["a@example.com"]["models"][0]["used"] == 61.0
    assert "61%" in " ".join(texts(app.cards["a@example.com"].outer))
    step("обновление на месте: карточки и число виджетов прежние, значение новое")

    app.open_menu()
    yield wait()
    items = texts(app.menu_win)
    for need in ("Добавить Google-аккаунт", "Сворачивать в трей при закрытии", "Предупреждения по прогнозу", "Язык", "English", "Українська",
                 "Открыть папку данных", f"AI Limits {L.__version__}"):
        assert need in items, (need, items)
    assert not any("OAuth" in t for t in items)  # ключи задаются не в окне
    app.open_menu()
    assert app.menu_win is None
    step("меню настроек открывается и закрывается, пункты на месте")

    def seen():
        return " | ".join(texts(root)) + " | " + app.status.cget("text")
    cards = len(app.cards)
    for code, words in (("en", ("Refresh", "Week", "5 hours", "Antigravity IDE data", "cloud", "Maximum",
                                "Updated", "auto 5 min", "at this pace lasts", "→ to IDE")),
                        ("uk", ("Оновити", "Тиждень", "5 годин", "дані IDE Antigravity", "хмара", "Оновлено",
                                "авто 5 хв", "за такого темпу вистачить на", "→ в IDE")),
                        ("ru", ("Обновить", "Неделя", "5 часов", "данные IDE Antigravity", "облако", "Обновлено",
                                "авто 5 мин", "при таком темпе хватит на"))):
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
    assert len(IDE_CALLS) == 3 and app.ag_res["b@example.com"]["source"] == app.IDE_SRC, len(IDE_CALLS)
    assert "IDE теперь работает под b@example.com" == app.status.cget("text"), app.status.cget("text")
    step("смена аккаунта: отмена, подтверждение, повтор опроса до появления данных IDE")

    app.alerted = set()
    app.check_alerts({"plan": "pro", "limits": rows(85.0, 2.0)}, [])
    yield wait()
    assert app.alert_win is not None and any("85" in t for t in texts(app.alert_win))
    app.hide_alert()
    app.warn = 0
    app.check_alerts({"plan": "pro", "limits": rows(99.0, 2.0)}, [])
    yield wait()
    assert app.alert_win is None
    step("предупреждение о пороге появляется; при «выкл» — нет")

    app.show_tray_menu(400, 400)
    yield wait()
    assert {"Открыть", "Обновить", "Выход"} <= set(texts(app.tray_menu))
    app.close_tray_menu()
    assert app.tray_menu is None
    step("меню иконки в трее")

    app.toggle("claude")
    yield wait()
    assert "claude" in app.collapsed and SAVED and "claude" in SAVED[-1]["collapsed"]
    cmd = autostart.autostart_command()
    assert "--autostart" in cmd and ("limits_gui.pyw" in cmd or getattr(sys, "frozen", False)), cmd
    step("сворачивание карточки сохраняется в настройках; команда автозапуска указывает на окно")

    print("Все проверки окна пройдены.")
    app.quit_app()


if __name__ == "__main__":
    drive(main())
    if FAILED:
        print(FAILED[0])
        sys.exit(1)
