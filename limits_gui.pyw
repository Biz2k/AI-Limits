"""AI Limits — окно с лимитами Claude Code и Google Antigravity.

Запуск без консоли:  pythonw limits_gui.pyw   (или двойной щелчок по файлу)
Логика запросов — в limits.py рядом.
"""
import ctypes
import ctypes.wintypes
import datetime as dt
import json
import os
import sys
import threading
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import limits as L  # noqa: E402
import i18n  # noqa: E402
from i18n import T  # noqa: E402
from ui_theme import (
    BG, CLAUDE, FAINT, FG, FONT, FONT_D, FlatButton, GOOGLE, GREEN, INTERVALS, MUTED, RED, Tooltip, YELLOW,
    color_for)
from ui_cards import CardView, _set  # noqa: E402
from ui_popups import PopupsMixin  # noqa: E402
from ui_tray import TrayMixin  # noqa: E402
from ui_history import HistoryMixin  # noqa: E402

# ---------------------------------------------------------------- DPI / тема
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:  # своя группа в панели задач — иконка окна вместо иконки Python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AILimits.Monitor")
    except Exception:
        pass

SETTINGS_FILE = os.path.join(L.APPDIR, "gui.json")


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(s):
    try:
        L.atomic_write_json(SETTINGS_FILE, s)
    except Exception:
        pass


# ---------------------------------------------------------------- приложение
class App(PopupsMixin, TrayMixin, HistoryMixin):
    def __init__(self, root, autostart=False):
        self.root = root
        self.s = load_settings()
        i18n.set_lang(self.s.get("lang", i18n.DEFAULT))  # язык интерфейса
        self.warn = float(self.s.get("warn", 80))
        self.interval = int(self.s.get("interval", 300))
        self.all_models = bool(self.s.get("all_models", False))
        self.loading = False
        self.timer = None
        self.data = None
        self.alerted = set()
        self.collapsed = set(self.s.get("collapsed", []))

        root.title("AI Limits")
        root.configure(bg=BG)
        root.minsize(440, 300)
        root.geometry(self.s.get("geometry", "500x720"))
        root.attributes("-topmost", bool(self.s.get("topmost", False)))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        # меню настроек не должно оставаться на экране, когда окно свёрнуто, спрятано в трей или закрыто
        root.bind("<Unmap>", self._on_unmap, add="+")
        self.dark_titlebar()

        # header
        hdr = tk.Frame(root, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(18, 6))
        tk.Label(hdr, text="AI Limits", bg=BG, fg=FG, font=(FONT_D, 18, "bold")).pack(side="left")
        # справа налево: Обновить, ⚙  → на экране: ⚙, Обновить
        self.refresh_btn = FlatButton(hdr, T("⟳  Обновить"), self.refresh)
        self.refresh_btn.pack(side="right")
        self.menu_btn = FlatButton(hdr, "⚙", self.open_menu)
        self.menu_btn.pack(side="right", padx=(0, 6))
        self.menu_tip = Tooltip(self.menu_btn, T("Настройки"))
        self.status = tk.Label(root, text="", bg=BG, fg=FAINT, font=(FONT, 9), anchor="w")
        root.iconphoto(True, self.make_icon())
        self.status.pack(fill="x", padx=20)

        # scrollable body
        wrap = tk.Frame(root, bg=BG)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        self.cv = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        self.body = tk.Frame(self.cv, bg=BG)
        self.body_id = self.cv.create_window((0, 0), window=self.body, anchor="nw")
        self.cv.pack(side="left", fill="both", expand=True)
        self.body.bind("<Configure>", self._on_body)
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(self.body_id, width=e.width))
        root.bind_all("<MouseWheel>", self._wheel)
        tk.Frame(root, bg=BG, height=12).pack(fill="x")

        self.cards, self.card_order, self.footer = {}, [], None  # карточки живут всё время работы окна
        self.setup_tray()
        if self.tray_always():
            if autostart:  # автозапуск с галочкой «в трей при закрытии»: без окна
                root.withdraw()
            self._tray_when_ready()  # с этой галочкой иконка в трее есть всегда
        self.render_placeholder(T("Загрузка…"))
        self.refresh()

    def _tray_when_ready(self):
        """Показать иконку в трее, как только поток трея создал своё окно."""
        if getattr(self.tray, "hwnd", None):
            self.tray.show()
        else:
            self.root.after(100, self._tray_when_ready)

    # ------------------------------------------------ системное
    def dark_titlebar(self):
        if os.name != "nt":
            return
        try:
            self.root.update()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            v = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass

    def fit_height(self):
        self.root.update_idletasks()
        need = (self.cv.winfo_rooty() - self.root.winfo_rooty()) + self.body.winfo_reqheight() + 14
        need = min(need, self.root.winfo_screenheight() - 120)
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{self.root.winfo_width()}x{need}+{x}+{y}")

    def _on_body(self, _):
        self.cv.configure(scrollregion=self.cv.bbox("all"))

    def _wheel(self, e):
        if self.body.winfo_reqheight() > self.cv.winfo_height():
            self.cv.yview_scroll(int(-e.delta / 120) * 2, "units")

    def persist(self):
        self.s.update(warn=self.warn, interval=self.interval, all_models=self.all_models,
                      topmost=bool(self.root.attributes("-topmost")), geometry=self.root.geometry(),
                      collapsed=sorted(self.collapsed))
        save_settings(self.s)

    def on_close(self):
        """Кнопка ✕ окна: в трей (если включено в настройках) или выход."""
        self.close_menu()
        if self.s.get("close_to_tray") and getattr(self, "tray", None):
            self.persist()
            self.to_tray()
        else:
            self.quit_app()

    def quit_app(self):
        if self.root.state() != "withdrawn":
            self.persist()
        if getattr(self, "tray", None):
            self.tray.stop()
        self.root.destroy()

    def set_interval(self, s):
        self.interval = s
        self.persist()
        self.schedule()

    def set_warn(self, p):
        self.warn = float(p)
        self.persist()
        if self.data:
            self.render(*self.data)

    # ------------------------------------------------ загрузка
    def schedule(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.interval:
            self.timer = self.root.after(self.interval * 1000, self.refresh)

    # Загрузка по частям: окно рисуется сразу, Claude, IDE и каждый аккаунт Google
    # грузятся в своих потоках и появляются по мере готовности (None = ещё грузится).
    IDE_SRC = "данные IDE Antigravity"

    def refresh(self):
        if self.loading:
            return
        self.loading = True
        self.refresh_btn.config(fg=MUTED)
        accs = L.load_accounts()
        prev = dict(getattr(self, "ag_res", {}))
        order = [a["email"] for a in accs]
        order += [e for e in getattr(self, "ag_order", []) if e not in order and
                  isinstance(prev.get(e), dict) and prev[e].get("ide_only")]
        self.ag_order = order
        self.ag_res = {e: prev.get(e) for e in order}          # старые значения остаются видны
        if not hasattr(self, "claude_res"):
            self.claude_res = None
        self.local_emails = set()
        self.pending = {"claude", "local", *[("ag", e) for e in order]}
        self.redraw()

        def run(key, fn, *args):
            try:
                val = fn(*args)
            except Exception as e:  # noqa
                val = e
            self.root.after(0, self._on_part, key, val)

        threading.Thread(target=run, args=("claude", L.claude_fetch), daemon=True).start()
        threading.Thread(target=run, args=("local", L.local_ide_info), daemon=True).start()
        for a in accs:
            threading.Thread(target=run, args=(("ag", a["email"]), L.ag_fetch, a, False, None),
                             daemon=True).start()

    def _merge(self, email, res):
        if isinstance(res, dict):
            return L.merge_with_cache([(email, res)])[0][1]
        return res

    def _on_part(self, key, val):
        self.pending.discard(key)
        if key == "claude":
            self.claude_res = val
        elif key == "local":
            val = val if isinstance(val, dict) else {}
            self.ide_running = bool(val.get("running"))
            for email, li in val.get("accounts", {}).items():
                known = next((e for e in self.ag_order if e.lower() == email), None)
                res = {"plan": li["plan"], "models": li["rows"], "credits": None, "source": self.IDE_SRC}
                if known is None:  # аккаунт IDE, не добавленный в список
                    known = email
                    self.ag_order.append(email)
                    res["ide_only"] = True
                self.local_emails.add(known)
                self.pending.discard(("ag", known))
                self.ag_res[known] = self._merge(known, res)
        else:
            email = key[1]
            if email not in self.local_emails:  # данные IDE точнее облачных
                self.ag_res[email] = self._merge(email, val)
        shown = getattr(self, "data", None)  # что сейчас на экране
        if not shown or shown[0] is None or any(r is None for _, r in shown[1]):
            self.redraw()  # есть карточки «Загрузка…» — заполняем их по мере прихода данных
        if not self.pending:
            self._all_done()

    def _all_done(self):
        self.loading = False
        self.refresh_btn.config(fg=FG)
        self.update_history()  # запись в историю и прогнозы — до перерисовки, строка прогноза есть в карточке
        self.redraw()  # при обновлении уже показанных данных — одна перерисовка на всё обновление
        if not getattr(self, "_fitted", False) and self.root.state() == "normal":  # высота окна по содержимому
            self._fitted = True
            self.fit_height()
        self._updated_at = dt.datetime.now()  # время последнего полного обновления — для строки статуса
        want = getattr(self, "_ide_expect", None)  # после смены аккаунта IDE ждём его данные из самой IDE
        if want:
            if want[0] in {e.lower() for e in self.local_emails} or want[1] <= 0:
                self._ide_expect = None
            else:  # IDE ещё не отдала лимиты нового аккаунта — спросить снова через 3 с
                want[1] -= 1
                self.root.after(3000, self.refresh)
        self.set_status_updated()
        self.update_tray_tip(*self.data)
        self.check_alerts(*self.data)
        self.schedule()

    def redraw(self):
        self.data = (self.claude_res, [(e, self.ag_res.get(e)) for e in self.ag_order])
        sig = repr((self.data, getattr(self, "ide_running", False),
                    sorted((k, fc["line"]) for k, fc in getattr(self, "fc", {}).items())))
        if sig == getattr(self, "_last_sig", None):  # ничего не изменилось — не перерисовываем
            return
        self._last_sig = sig
        self.render(*self.data)

    # ------------------------------------------------ аккаунты
    def add_account(self):
        self.status.config(text=T("Войдите в Google в открывшемся браузере…"), fg=GOOGLE)

        def work():
            try:
                acc = L.ag_login()
                accs = [x for x in L.load_accounts() if x["email"] != acc["email"]] + [acc]
                L.save_accounts(accs)
                self.root.after(0, lambda: (self.status.config(text=T("Добавлен {email}", email=acc["email"]),
                                                               fg=GREEN), self.refresh()))
            except Exception as e:
                failed = T("Вход не выполнен: {error}", error=e)  # текст — сейчас: вне except имени e уже нет
                self.root.after(0, lambda: self.status.config(text=failed, fg=RED))
        threading.Thread(target=work, daemon=True).start()

    def switch_ide(self, email):
        if getattr(self, "ide_switching", False):
            return
        card = self.cards.get(email)
        self.confirm(card.ide if card else self.menu_btn,
                     T("Переключить IDE на {email}?", email=email),
                     T("Antigravity перезапустится, незавершённые ответы агента прервутся."),
                     lambda: self._switch_ide_go(email))

    def _switch_ide_go(self, email):
        if getattr(self, "ide_switching", False):
            return
        self.ide_switching = True
        self.status.config(text=T("IDE: подготовка…"), fg=GOOGLE)

        def say(text):
            self.root.after(0, lambda: self.status.config(text=text, fg=GOOGLE))

        def work():
            try:
                now = L.ide_switch_account(email, on_status=say)
                ok = (now or "").lower() == email.lower()
                msg, col = ((T("IDE теперь работает под {email}", email=now), GREEN) if ok else
                            (T("В IDE вошёл {now}, а не {email}", now=now or T("никто"), email=email), YELLOW))
                expect = email if ok else None
            except L.IdeSwitchUnverified as e:
                msg, col, expect = str(e), YELLOW, email
            except Exception as e:
                msg, col, expect = T("Не удалось сменить аккаунт: {error}", error=e), RED, None
            import time as _t
            hold = 10 if col == GREEN else 20  # успех убираем через 10 с, ошибку держим до следующего обновления
            self.status_sticky = _t.time() + hold
            self.ide_switching = False
            def done():
                # лимиты нового аккаунта нужны из IDE: обновляем сразу и повторяем, пока IDE их не отдаст (до 10 раз)
                self._ide_expect = [expect.lower(), 10] if expect else None
                self.refresh()
                self.status.config(text=msg, fg=col)
            self.root.after(0, done)
            if col == GREEN:  # вернуть строку «Обновлено …»
                self.root.after(hold * 1000 + 200, self.set_status_updated)
        threading.Thread(target=work, daemon=True).start()

    def remove_account(self, email):
        def go():
            L.save_accounts([x for x in L.load_accounts() if x["email"] != email])
            self.refresh()
        self.confirm(self.menu_btn, T("Убрать {email} из списка?", email=email),
                     T("Вернуть его можно через «Добавить Google-аккаунт»."), go)

    # ------------------------------------------------ оповещения
    def check_alerts(self, claude, ag):
        hits = []
        if isinstance(claude, dict):
            hits += [("Claude · " + r["name"], r["used"]) for r in claude["limits"]]
        for email, r in ag:
            if isinstance(r, dict):
                hits += [(f"{email} · {m['name']}", m["used"]) for m in r["models"] if m["used"] is not None]
        soon = self.forecast_alerts()  # по прогнозу (если включено в меню): недельный лимит кончится раньше сброса
        if not self.warn:  # предупреждение выключено
            self.alerted = set()
            return
        new = [(k, u) for k, u in hits if u >= self.warn and k not in self.alerted]
        self.alerted = {k for k, u in hits if u >= self.warn}
        if new or soon:
            self.show_alert(sorted(new, key=lambda h: -h[1]), soon)

    ALERT_SHOW_MS = 5000   # сколько висит всплывающее предупреждение
    ALERT_ALPHA = 0.97

    # ------------------------------------------------ отрисовка
    def render_placeholder(self, text):
        self._placeholder = tk.Label(self.body, text=text, bg=BG, fg=MUTED, font=(FONT, 11))
        self._placeholder.pack(pady=40)

    def toggle(self, key):
        self.collapsed ^= {key}
        self.persist()
        if self.data:
            self.render(*self.data)

    def render(self, claude, ag):
        """Приводит карточки в соответствие с данными. Карточки и строки создаются один раз и дальше
        обновляются на месте (значения, полосы, время, метка IDE); состав карточек меняется только
        при добавлении/удалении аккаунта."""
        if getattr(self, "_placeholder", None):
            self._placeholder.destroy()
            self._placeholder = None

        def spec(**kw):
            return dict(dict(collapsible=False, folded=False, badge="", sub="", summary=None, ide=None,
                             msg=None, rows=[]), **kw)

        loading = (T("Загрузка…"), MUTED, (FONT, 10, "italic"), (10, 2))

        def failed(e):
            return (str(e), RED, (FONT, 9), (8, 0))

        specs = []  # (ключ, заголовок, цвет, описание)
        # Claude
        if claude is None:
            specs.append(("claude", "Claude Code", CLAUDE, spec(msg=loading)))
        elif isinstance(claude, Exception):
            specs.append(("claude", "Claude Code", CLAUDE, spec(msg=failed(claude))))
        else:
            folded = "claude" in self.collapsed
            mx = max((r["used"] for r in claude["limits"]), default=0)
            specs.append(("claude", "Claude Code", CLAUDE, spec(
                collapsible=True, folded=folded, badge=claude["plan"],
                summary=(T("макс {pct}%", pct=f"{mx:.0f}"), color_for(mx, self.warn)) if folded else None,
                rows=[] if folded else [(r["name"], r["used"], r["resets_at"], None, self.fc_line("claude", r["name"]))
                                        for r in claude["limits"]])))

        # Antigravity
        ide_running = getattr(self, "ide_running", False)  # IDE запущена (даже без входа)
        if not ag:
            specs.append(("\0none", "Google Antigravity", GOOGLE, spec(
                msg=(T("Аккаунтов нет. Добавьте его в меню ⚙ → «Добавить Google-аккаунт»."),
                     MUTED, (FONT, 10), (8, 0)))))
        for email, res in ag:
            if res is None:
                specs.append((email, email, GOOGLE, spec(sub="Gemini", msg=loading)))
                continue
            if isinstance(res, Exception):
                specs.append((email, email, GOOGLE, spec(msg=failed(res))))
                continue
            seen, models = set(), []  # убрать дубли (одинаковые имя и квота)
            for m in res["models"]:
                k = (m["name"], m["used"], m["resets_at"])
                if k not in seen:
                    seen.add(k)
                    models.append(m)
            folded = email in self.collapsed
            mx = max((m["used"] for m in models if m["used"] is not None), default=0)
            plan = res.get("plan", "")
            plan = "ULTRA" if "ultra" in plan.lower() else ("PRO" if "pro" in plan.lower() else plan)
            if res.get("source") == "данные IDE Antigravity":
                ide = "current"
            elif ide_running or L.ide_installed():  # быстрая проверка: render идёт в потоке интерфейса
                ide = "switch"
            else:
                ide = None
            specs.append((email, email, GOOGLE, spec(
                collapsible=True, folded=folded, badge=plan, sub="Gemini  ·  " + T(res.get("source", "")), ide=ide,
                summary=(T("макс {pct}%", pct=f"{mx:.0f}"), color_for(mx, self.warn)) if folded else None,
                msg=None if models else (T("Нет данных о лимитах Gemini"), MUTED, (FONT, 10), (8, 0)),
                rows=[] if folded else [(m["name"], m["used"], m["resets_at"], m.get("seen"),
                                         self.fc_line(email, m["name"])) for m in models])))

        if self.footer is None:  # строка «Максимум» под карточками
            self.footer = tk.Frame(self.body, bg=BG)
            self._footer_on = False
            tk.Label(self.footer, text=T("Максимум"), bg=BG, fg=FAINT, font=(FONT, 9)).pack(side="left", padx=(0, 6))
            self.footer_email = tk.Label(self.footer, bg=BG, fg=GOOGLE, font=(FONT, 10, "bold"))
            self.footer_email.pack(side="left", padx=(0, 6))
            tk.Label(self.footer, text="→", bg=BG, fg=FAINT, font=(FONT, 10, "bold")).pack(side="left", padx=(0, 6))
            self.footer_pct = tk.Label(self.footer, bg=BG, fg=GREEN, font=(FONT, 10, "bold"))
            self.footer_pct.pack(side="left", padx=(0, 6))

        keys = [s[0] for s in specs]
        if keys != self.card_order:  # добавили/убрали аккаунт — меняем набор карточек
            for k in set(self.cards) - set(keys):
                self.cards.pop(k).outer.destroy()
            for k, title, accent, _ in specs:
                if k not in self.cards:
                    self.cards[k] = CardView(self, k, title, accent)
            for k in self.card_order:
                if k in self.cards:
                    self.cards[k].outer.pack_forget()
            self.footer.pack_forget()
            self._footer_on = False
            for k in keys:
                self.cards[k].outer.pack(fill="x", padx=20, pady=6)
            self.card_order = keys
        for k, _, _, s in specs:
            self.cards[k].update(s, self.warn)

        best = L.best_weekly(ag)  # по остатку недельного лимита
        footer_on = bool(best and len(ag) > 1)
        if footer_on:
            _set(self.footer_email, text=best[0])
            _set(self.footer_pct, text=f"{best[1]:.0f}%")
        if footer_on != self._footer_on:
            self._footer_on = footer_on
            if footer_on:
                self.footer.pack(fill="x", padx=22, pady=(8, 4))
            else:
                self.footer.pack_forget()

        self.set_status_updated()

    def set_status_updated(self):
        import time as _t  # сообщение о смене аккаунта IDE не затираем ещё 20 секунд
        if getattr(self, "ide_switching", False) or _t.time() < getattr(self, "status_sticky", 0):
            return
        nxt = T("  ·  авто {interval}", interval=T(dict((s, n) for n, s in INTERVALS)[self.interval])) \
            if self.interval else ""
        if not getattr(self, "_updated_at", None):
            return  # первая загрузка ещё идёт
        self.status.config(text=T("Обновлено {time}{auto}", time=f"{self._updated_at:%H:%M}", auto=nxt), fg=FAINT)


def main():
    if os.name == "nt":
        try:
            import tray
            if tray.activate_running_instance():
                return  # уже запущено — показали существующее окно
        except Exception:
            pass
    L.install_error_log()
    try:
        L.protect_stored_secrets()  # данные прежних версий — в зашифрованный вид
    except Exception:
        pass
    root = tk.Tk()
    # ошибки в обработчиках кнопок и таймеров Tk — тоже в журнал
    root.report_callback_exception = lambda t, e, tb: L.log_exception("обработчик окна", t, e, tb)
    App(root, autostart=bool({"--autostart", "--tray"} & set(sys.argv[1:])))
    root.mainloop()


if __name__ == "__main__":
    main()
