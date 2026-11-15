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
    assert any(isinstance(c, tk.Canvas) and c.find_all() for c in win.winfo_children()[0].winfo_children())
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
    assert cb.strip.cget("bg") != cb.accent                             # наведение на полоску — светлее
    cb.strip_hover(False)
    assert cb.strip.cget("bg") == cb.accent
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
    step("переименование двойным щелчком по имени в плитке; дубликат и название программы не применяются")

    # «Управление аккаунтами»: на месте меню, «←» обратно, группы по сервисам, имя и email
    app.open_menu()
    yield wait()
    item = next(w for w in app.menu_win.winfo_children()[0].winfo_children() if "Управление аккаунтами" in texts(w))
    item.winfo_children()[-1].event_generate("<Button-1>")
    yield wait()
    t = texts(app.menu_win)
    for need in ("Управление аккаунтами", "Claude", "ChatGPT", "Google", "Работа", "me@example.com  ·  из программы",
                 "a", "a@example.com", "b", "b@example.com", "←"):
        assert need in t, (need, t)
    assert t.index("Claude") < t.index("Работа") < t.index("ChatGPT") < t.index("Google") < t.index("a@example.com")
    back = next(w for w in app.menu_win.winfo_children()[0].winfo_children()[0].winfo_children() if w.cget("text") == "←")
    back.event_generate("<Button-1>")
    yield wait()
    assert "Добавить аккаунт" in texts(app.menu_win)
    app.close_menu()
    step("«Управление аккаунтами»: на месте меню ⚙, «←» — назад, группы по сервисам, имя и email мелко")

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
    assert app.cards["claude:second@example.com"].ide_mode is None      # кнопки «→ в …» у Claude пока нет
    app.add_account("claude")
    yield wait(10, lambda: not app.adding, "повтор не завершился")
    assert "уже добавлен" in app.status.cget("text") and len(accounts.load_profiles()) == 2
    assert accounts.suggest_name("chatgpt", "b@example.com", list(app.names().values())) == "Codex b"
    step("«Добавить аккаунт»: совпавший с программой — имя у плитки программы; другой — своя плитка;"
         " повтор не добавляется; занятое имя — с приставкой сервиса")

    # удаление: профиль и его папка, имя; аккаунт программы удалить нельзя
    prof = next(p for p in accounts.load_profiles() if p["kind"] == "claude")
    app.remove_account("claude:second@example.com")
    yield wait()
    app.confirm_win.event_generate("<Return>")
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
