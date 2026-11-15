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
    assert not any("хватит" in t for t in texts(app.popup)), texts(app.popup)
    app.hide_popup()
    step("график расхода по щелчку на строке; в мини-окне трея прогноза нет")

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
    for code, words in (("en", ("Refresh", "Week", "5 hours", "Maximum", "Updated", "auto 5 min", "→ to IDE")),
                        ("uk", ("Оновити", "Тиждень", "5 годин", "Оновлено", "авто 5 хв", "→ в IDE")),
                        ("ru", ("Обновить", "Неделя", "5 часов", "Обновлено", "авто 5 мин"))):
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

    E = types.SimpleNamespace  # событие мыши: нужны только координаты экрана
    cl, ca, cb = (app.cards[k] for k in ("claude", "a@example.com", "b@example.com"))
    tx, ty = cl.outer.winfo_rootx() + 30, cl.outer.winfo_rooty() + 5
    bx, by = cb.title.winfo_rootx() + 5, cb.title.winfo_rooty() + 5
    app._drag_press(E(x_root=bx, y_root=by), cb, None)
    app._drag_motion(E(x_root=bx, y_root=by - 3))                       # меньше порога — ещё щелчок
    assert not app._drag["on"] and app.card_order == ["claude", "a@example.com", "b@example.com"]
    app._drag_motion(E(x_root=tx, y_root=ty))
    assert app.card_order == ["b@example.com", "claude", "a@example.com"], app.card_order
    app._drag_release(E(x_root=tx, y_root=ty))
    yield wait()
    assert SAVED[-1]["order"] == ["b@example.com", "claude", "a@example.com"]
    assert [int(app.cards[k].outer.grid_info()["row"]) for k in app.card_order] == [0, 1, 2]
    app.show_popup()
    yield wait()
    t = texts(app.popup)
    assert t.index("b") < t.index("Claude Code") < t.index("a"), t       # мини-окно трея — в том же порядке
    app.hide_popup()
    app._show_menu(True)
    yield wait()
    t = [x.strip() for x in texts(app.menu_win)]
    assert t.index("✕  b@example.com") < t.index("✕  a@example.com"), t  # список «Убрать» — тоже
    app.close_menu()
    app.refresh()
    yield wait(10, lambda: not app.loading)
    assert app.card_order == ["b@example.com", "claude", "a@example.com"]
    step("перетаскивание карточки за заголовок: порядок сохраняется, его повторяют мини-окно трея и меню")

    w0 = root.winfo_width()
    app.toggle_two_columns()
    yield wait(0.5)
    assert SAVED[-1]["two_columns"] and root.winfo_width() > w0 * 1.5, (w0, root.winfo_width())
    pos = {k: (int(app.cards[k].outer.grid_info()["row"]), int(app.cards[k].outer.grid_info()["column"]))
           for k in app.card_order}
    assert pos == {"b@example.com": (0, 0), "claude": (0, 1), "a@example.com": (1, 0)}, pos
    assert cb.outer.winfo_height() == cl.outer.winfo_height()           # карточки одной строки — одной высоты
    assert cb.outer.winfo_rootx() < cl.outer.winfo_rootx()
    ax, ay = ca.title.winfo_rootx() + 5, ca.title.winfo_rooty() + 5
    app._drag_press(E(x_root=ax, y_root=ay), ca, None)
    app._drag_motion(E(x_root=cb.outer.winfo_rootx() + 10, y_root=cb.outer.winfo_rooty() + 10))
    app._drag_release(E(x_root=0, y_root=0))
    assert app.card_order == ["a@example.com", "b@example.com", "claude"], app.card_order
    yield wait()
    assert int(cl.outer.grid_info()["row"]) == 1
    app.toggle_two_columns()
    yield wait(0.5)
    assert not SAVED[-1]["two_columns"] and abs(root.winfo_width() - w0) < 4, (w0, root.winfo_width())
    assert {int(app.cards[k].outer.grid_info()["column"]) for k in app.card_order} == {0}
    app.s["order"] = []
    app.render(*app.data)
    yield wait()
    assert app.card_order == ["claude", "a@example.com", "b@example.com"]
    step("две колонки: окно расширяется, перетаскивание по сетке, возврат в одну колонку")

    cl.title.event_generate("<ButtonPress-1>")
    cl.title.event_generate("<ButtonRelease-1>")
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
