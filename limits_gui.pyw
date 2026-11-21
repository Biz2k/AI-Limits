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
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import limits as L  # noqa: E402
import i18n  # noqa: E402
from i18n import T  # noqa: E402
from ui_theme import (
    BG, BLUE, FAINT, FG, FONT, FONT_D, FlatButton, GOOGLE, GREEN, MUTED, RED, Tooltip, YELLOW,
    color_for)
from ui_cards import CardView, _set  # noqa: E402
from ui_popups import PopupsMixin  # noqa: E402
from ui_tray import TrayMixin  # noqa: E402
from ui_history import HistoryMixin  # noqa: E402
from ui_layout import LayoutMixin  # noqa: E402
from ui_accounts import ACCENT, AccountsMixin  # noqa: E402

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
class App(PopupsMixin, TrayMixin, HistoryMixin, LayoutMixin, AccountsMixin):
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
        self.parts = None  # загруженные данные: {часть: dict | исключение | None (грузится)}
        try:
            self.migrate_accounts()  # данные прежних версий — в вид 1.5.0 (один раз)
        except Exception as e:
            L.log_exception("перевод аккаунтов", type(e), e, e.__traceback__)

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
        # строка под заголовком: слева «Обновлено ЧЧ:ММ» (и сообщения), справа «макс. email → 100%»
        self.status_row = tk.Frame(root, bg=BG)
        self.status_row.pack(fill="x", padx=20)
        self.status = tk.Label(self.status_row, text="", bg=BG, fg=FAINT, font=(FONT, 9), anchor="w")
        root.iconphoto(True, self.make_icon())
        self.status.pack(side="left", fill="x", expand=True)

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

    def fit_height(self, width=None):
        """Высота окна по содержимому; width — заодно новая ширина (смена числа колонок)."""
        self.root.update_idletasks()
        need = (self.cv.winfo_rooty() - self.root.winfo_rooty()) + self.body.winfo_reqheight() + 14
        need = min(need, self.root.winfo_screenheight() - 120)
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{width or self.root.winfo_width()}x{need}+{x}+{y}")
        self._fit_req = self.body.winfo_reqheight()

    def autofit(self):
        """Подогнать высоту окна, если высота содержимого изменилась: свернули/развернули плитку, добавили или
        убрали аккаунт, плитка заполнилась после «Загрузка…». Развёрнутое на весь экран окно не трогаем."""
        if not getattr(self, "_fitted", False) or self.root.state() != "normal" or getattr(self, "_dnd", None):
            return
        self.root.update_idletasks()
        if self.body.winfo_reqheight() != getattr(self, "_fit_req", None):
            self.fit_height()

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

    # Загрузка по частям: окно рисуется сразу, а программы (Claude Code, Codex, IDE Antigravity), каждый
    # Google-аккаунт и каждый свой профиль грузятся в своих потоках и появляются по мере готовности.
    IDE_SRC = "данные IDE Antigravity"

    RATE_PAUSE = 300  # сервер ответил 429 и не сказал, сколько ждать — пауза запросов этой части, с

    def refresh(self, ide_only=False):
        """Обновить всё. ide_only — только IDE Antigravity и Google (повторы после смены аккаунта IDE: Claude и Codex
        в них не нужны). Часть, которой сервер ответил 429, не запрашивается до конца паузы — её данные остаются."""
        if self.loading:
            return
        self.loading = True
        self.refresh_btn.config(fg=MUTED)
        jobs = self.plan_jobs()
        prev = self.parts or {}
        self.parts = {k: prev.get(k) for k in jobs if k != "local"}  # старые значения остаются видны
        now, pause = time.time(), getattr(self, "rate_pause", {})
        for k in list(jobs):
            if k == "local":
                continue
            if pause.get(k, 0) > now or ide_only and not (k[0] == "google" or k == ("ide", "google")):
                del jobs[k]  # пауза после 429 или повтор только ради IDE — прежнее значение остаётся
        self.pending = set(jobs)
        self.redraw()

        def run(key, fn, *args):
            try:
                val = fn(*args)
            except Exception as e:  # noqa
                val = e
            self.root.after(0, self._on_part, key, val)

        for key, (fn, *args) in jobs.items():
            threading.Thread(target=run, args=(key, fn, *args), daemon=True).start()

    def _merge(self, email, res):
        if isinstance(res, dict):
            return L.merge_with_cache([(email, res)])[0][1]
        return res

    def _on_part(self, key, val):
        self.pending.discard(key)
        if getattr(val, "code", None) == 429:  # сервер временно ограничил запросы (1.5.4)
            wait = getattr(val, "retry_after", 0) or self.RATE_PAUSE
            self.rate_pause = getattr(self, "rate_pause", {})
            self.rate_pause[key] = time.time() + wait
            old = (self.parts or {}).get(key)
            if isinstance(old, dict):
                val = old  # прежние данные остаются, пока сервер снова не начнёт отвечать
            else:
                val = RuntimeError(T("Сервер временно ограничил запросы — повторю через {min} мин",
                                     min=max(1, round(wait / 60))))
        if key == "local":
            val = val if isinstance(val, dict) else {}
            self.ide_local = val
            self.ide_running = bool(val.get("running") or val.get("window") or val.get("hidden"))
            if val.get("email"):  # запущенная IDE знает свой аккаунт точнее записи входа
                self.ide_email["google"] = val["email"]
            # окно IDE открыто, а входа нет (1.5.4): у аккаунта записи входа — «→ в IDE», отдельной плитки нет
            # сервер новой IDE (ключ скрыт) спросить нельзя — аккаунт IDE = запись входа, «● IDE» как обычно
            self.ide_nologin = self.ide_running and not val.get("email") and not val.get("hidden")
        elif key[0] == "google" or key == ("ide", "google"):
            email = key[1] if key[0] == "google" else (self.ide_email.get("google") or "")
            self.parts[key] = self._merge(email, val)
        else:
            self.parts[key] = val
        shown = getattr(self, "data", None) or []  # что сейчас на экране
        if not shown or any(t["res"] is None for _, t in shown):
            self.redraw()  # есть карточки «Загрузка…» — заполняем их по мере прихода данных
        if not self.pending:
            self._all_done()

    def _all_done(self):
        self.loading = False
        self.refresh_btn.config(fg=FG)
        self.redraw()
        self.update_history()  # запись в историю и прогнозы
        if not getattr(self, "_fitted", False) and self.root.state() == "normal":  # высота окна по содержимому
            self._fitted = True
            self.fit_height()
        self._updated_at = dt.datetime.now()  # время последнего полного обновления — для строки статуса
        want = getattr(self, "_ide_expect", None)  # после смены аккаунта IDE ждём его данные из самой IDE
        if want:
            got = (self.ide_local or {}).get("accounts", {}) if getattr(self, "ide_local", None) else {}
            if want[0] in got or want[1] <= 0:
                self._ide_expect = None
            else:  # IDE ещё не отдала лимиты нового аккаунта — спросить снова через 3 с (только IDE и Google)
                want[1] -= 1
                self.root.after(3000, lambda: self.refresh(ide_only=True))
        self.set_status_updated()
        self.update_tray_tip(self.data)
        self.check_alerts(self.data)
        self.schedule()

    def redraw(self):
        self.data = self.build_tiles()
        sig = repr(([(k, {x: v for x, v in t.items() if x != "profile"}) for k, t in self.data],
                    getattr(self, "ide_running", False), getattr(self, "ide_nologin", False),
                    sorted(self.names().items())))
        if sig == getattr(self, "_last_sig", None):  # ничего не изменилось — не перерисовываем
            return
        self._last_sig = sig
        self.render(self.data)

    # ------------------------------------------------ аккаунты
    def switch_ide(self, email):
        if email.startswith(("codex:", "claude:")):  # плитки ChatGPT и Claude — «→ в Codex», «→ в Claude»
            return self.switch_program(email)
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
        self.say(T("IDE: подготовка…"), GOOGLE)

        def say(text):
            self.root.after(0, lambda: self.say(text, GOOGLE))

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
                self.say(msg, col)
            self.root.after(0, done)
            if col == GREEN:  # вернуть строку «Обновлено …»
                self.root.after(hold * 1000 + 200, self.set_status_updated)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------ оповещения
    def check_alerts(self, tiles):
        hits = []
        for _, t in tiles:
            if isinstance(t["res"], dict):
                rows = t["res"].get("limits") or t["res"].get("models") or []
                hits += [(t["title"] + " · " + T(r["name"]), r["used"]) for r in rows if r.get("used") is not None]
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
        self._placeholder.grid(row=0, column=0, columnspan=2, pady=40)
        self.body.columnconfigure(0, weight=1)

    def toggle(self, key):
        self.collapsed ^= {key}
        self.persist()
        if self.data:
            self.render(self.data)
        self.autofit()

    def render(self, tiles):
        """Приводит карточки в соответствие с данными. Карточки и строки создаются один раз и дальше
        обновляются на месте (значения, полосы, время, метка IDE); состав карточек меняется только
        при добавлении/удалении аккаунта."""
        if getattr(self, "_placeholder", None):
            self._placeholder.destroy()
            self._placeholder = None

        def spec(**kw):
            return dict(dict(collapsible=False, folded=False, badge="", summary=None, ide=None,
                             msg=None, rows=[], title=None, badge_fg=None, badge_tip="", dim=False,
                             quiet=False), **kw)

        loading = (T("Загрузка…"), MUTED, (FONT, 10, "italic"), (10, 2))

        def failed(e):
            return (str(e), RED, (FONT, 9), (8, 0))

        specs = []  # (ключ, заголовок, цвет, описание)
        ide_running = getattr(self, "ide_running", False)  # IDE запущена (даже без входа)
        if not tiles:
            specs.append(("\0none", "AI Limits", BLUE, spec(
                msg=(T("Аккаунтов нет. Добавьте его в меню ⚙ → «Добавить аккаунт»."), MUTED, (FONT, 10), (8, 0)))))
        for key, t in tiles:
            title, accent, res = t["title"], ACCENT[t["kind"]], t["res"]
            mode = self.switch_mode(t, ide_running)
            # аккаунт не вошёл ни в Claude Code, ни в Codex, ни в IDE — полоса и надписи тусклее (1.5.4)
            quiet = not (mode or "").startswith("current")
            if res is None:
                specs.append((key, title, accent, spec(msg=loading, ide=mode, quiet=quiet)))
                continue
            if isinstance(res, Exception):
                specs.append((key, title, accent, spec(msg=failed(res), ide=mode, quiet=quiet)))
                continue
            seen, rows = set(), []  # убрать дубли (одинаковые имя и квота)
            for r in res.get("limits") or res.get("models") or []:
                k = (r["name"], r["used"], r["resets_at"])
                if k not in seen:
                    seen.add(k)
                    rows.append(r)
            folded = key in self.collapsed
            plan = res.get("plan") or ""
            if t["kind"] == "google":
                low = plan.lower()  # бесплатный тариф Google называет «Antigravity Starter Quota» — значок FREE
                plan = ("ULTRA" if "ultra" in low else "PRO" if "pro" in low else
                        "FREE" if "starter" in low or "free" in low else plan)
            off = bool(res.get("verify"))  # Google просит подтвердить аккаунт: значок LOGOUT красным, полосы бледные
            summary = self.weekly_left(rows) if folded else None
            if off and summary:
                summary = (summary[0], FAINT)
            specs.append((key, title, accent, spec(
                collapsible=True, folded=folded, badge="LOGOUT" if off else plan,
                ide=None if off else mode,  # у LOGOUT нет ни кнопки «→ в …», ни метки IDE (владелец)
                badge_fg=RED if off else None, dim=off, quiet=quiet,
                badge_tip=T("Google просит подтвердить этот аккаунт (Verify your account).\n"
                            "Лимиты Gemini недоступны, пока вы не войдёте им в IDE Antigravity\n"
                            "и не подтвердите аккаунт.") if off else "",
                summary=summary,
                msg=None if rows or folded else (T("Нет данных о лимитах Gemini") if t["kind"] == "google"
                                                 else T("Нет данных о лимитах"), MUTED, (FONT, 10), (8, 0)),
                rows=[] if folded else [(r["name"], r["used"], r["resets_at"], r.get("seen")) for r in rows])))

        if self.footer is None:  # «макс. email 100%» — справа в строке статуса
            self.footer = tk.Frame(self.status_row, bg=BG)
            self._footer_on = False
            tk.Label(self.footer, text=T("макс."), bg=BG, fg=FAINT, font=(FONT, 9)).pack(side="left", padx=(0, 5))
            self.footer_email = tk.Label(self.footer, bg=BG, fg=GOOGLE, font=(FONT, 9))
            self.footer_email.pack(side="left", padx=(0, 5))
            self.footer_pct = tk.Label(self.footer, bg=BG, fg=GREEN, font=(FONT, 10, "bold"))
            self.footer_pct.pack(side="left")

        keys = self.ordered([s[0] for s in specs])  # порядок — как пользователь расставил перетаскиванием
        relayout = keys != self.card_order
        if relayout:  # добавили/убрали аккаунт — меняем набор карточек
            for k in set(self.cards) - set(keys):
                self.cards.pop(k).outer.destroy()
            for k, title, accent, _ in specs:
                if k not in self.cards:
                    self.cards[k] = CardView(self, k, title, accent)
            self.card_order = keys
        for k, title, _, s in specs:
            s["title"] = title
            self.cards[k].update(s, self.warn)

        every = [(t["title"], t["res"]) for _, t in tiles]
        best = L.best_weekly([(n, r) for n, r in every if not (isinstance(r, dict) and r.get("verify"))])  # наибольший остаток недельного лимита среди всех аккаунтов всех сервисов (1.5.1)
        footer_on = bool(best and len(every) > 1)
        if footer_on:
            kind = next(t["kind"] for _, t in tiles if t["title"] == best[0])
            _set(self.footer_email, text=best[0], fg=ACCENT[kind])  # имя — цветом сервиса
            _set(self.footer_pct, text=f"{best[1]:.0f}%")
        self._footer_on = footer_on
        self._sync_footer()
        if relayout:
            self.layout_cards()
        self.root.after_idle(self.autofit)  # содержимое стало выше или ниже — подогнать окно

        self.set_status_updated()

    def weekly_left(self, rows):
        """Свёрнутая плитка: остаток недельного лимита («72%»), цвет — по израсходованному."""
        used = next((r["used"] for r in rows if r["name"].startswith("Неделя") and r["used"] is not None), None)
        return ("—", FAINT) if used is None else (f"{100 - used:.0f}%", color_for(used, self.warn))

    def set_status_updated(self):
        import time as _t  # сообщение о смене аккаунта IDE не затираем ещё 20 секунд
        if getattr(self, "ide_switching", False) or _t.time() < getattr(self, "status_sticky", 0):
            return
        if not getattr(self, "_updated_at", None):
            return  # первая загрузка ещё идёт
        self.status.config(text=T("Обновлено {time}", time=f"{self._updated_at:%H:%M}"), fg=FAINT)
        self._status_msg = False
        self._sync_footer()

    def say(self, text, fg):
        """Сообщение в строке статуса (смена аккаунта, ошибки): на время показа строка занята им целиком —
        «макс. …» справа скрыта и вернётся вместе с «Обновлено ЧЧ:ММ»."""
        self._status_msg = True
        self.status.config(text=text, fg=fg)
        self._sync_footer()

    def _sync_footer(self):
        """«макс. email → N%» виден, если есть что показать и в строке статуса нет сообщения."""
        if self.footer is None:
            return
        on = bool(getattr(self, "_footer_on", False)) and not getattr(self, "_status_msg", False)
        if on != bool(self.footer.winfo_manager()):
            if on:
                self.footer.pack(side="right", before=self.status)
            else:
                self.footer.pack_forget()


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
