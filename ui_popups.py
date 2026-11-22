"""Всплывающие окна AI Limits: меню настроек, подтверждение, ввод OAuth-ключей, предупреждение о пороге."""
import ctypes
import ctypes.wintypes
import os
import time
import tkinter as tk
from tkinter import font as tkfont

import i18n
import limits as L
from i18n import T
from ui_theme import fade_in
from ui_theme import (
    CARD, CARD_HI, CLAUDE, CODEX, FAINT, FG, FONT, FONT_D, FlatButton, BLUE, GOOGLE, GREEN, INTERVALS, LINE, MUTED,
    RED, YELLOW,
    color_for)
from autostart import autostart_enabled, set_autostart
from ui_cards import _set

POINTER_GAP = 24  # окно подтверждения у указателя мыши — с таким зазором, чтобы не перекрывать то, что под ним


class PopupsMixin:
    """Часть класса App (limits_gui.pyw): всплывающие окна. Пользуется полями и методами App через self."""

    # ------------------------------------------------ окно подтверждения
    def close_confirm(self, *_):
        w, self.confirm_win = getattr(self, "confirm_win", None), None
        if w:
            try:
                w.destroy()
            except tk.TclError:
                pass

    def _work_area(self, x, y):
        """Рабочая область (без панели задач) монитора, на котором находится точка (x, y)."""
        if os.name == "nt":
            try:
                class MONITORINFO(ctypes.Structure):
                    _fields_ = [("cbSize", ctypes.wintypes.DWORD), ("rcMonitor", ctypes.wintypes.RECT),
                                ("rcWork", ctypes.wintypes.RECT), ("dwFlags", ctypes.wintypes.DWORD)]
                u32 = ctypes.windll.user32
                u32.MonitorFromPoint.restype = ctypes.c_void_p
                u32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.wintypes.DWORD]
                u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(mi)
                mon = u32.MonitorFromPoint(ctypes.wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
                if mon and u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                    r = mi.rcWork
                    return r.left, r.top, r.right, r.bottom
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def confirm(self, anchor, title, text, on_yes, at_pointer=False):
        """Своё тёмное окно подтверждения (вместо системного) рядом с виджетом anchor, в пределах экрана.
        at_pointer — рядом с указателем мыши (не вплотную) и в пределах главного окна (1.5.2: удаление аккаунта
        из меню — его кнопка исчезает вместе с меню, и окно уезжало в угол экрана).
        «Да» вызывает on_yes; «Нет», Esc и щелчок мимо окна — закрывают."""
        self.close_confirm()
        px, py = self.root.winfo_pointerxy()
        ax, ay, aw, ah = anchor.winfo_rootx(), anchor.winfo_rooty(), anchor.winfo_width(), anchor.winfo_height()
        self.close_menu()  # координаты взяты до закрытия меню: anchor может лежать в нём
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=LINE)
        self.confirm_win = p
        wrap = round(self.root.winfo_fpixels("1i") / 96 * 250)
        box = tk.Frame(p, bg=CARD, padx=16, pady=14)
        box.pack(padx=1, pady=1)
        tk.Label(box, text=title, bg=CARD, fg=FG, font=(FONT, 11, "bold"), anchor="w", justify="left",
                 wraplength=wrap).pack(fill="x")
        tk.Label(box, text=text, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                 wraplength=wrap).pack(fill="x", pady=(8, 14))
        btns = tk.Frame(box, bg=CARD)
        btns.pack(fill="x")

        def yes(*_):
            self.close_confirm()
            on_yes()
        FlatButton(btns, T("Нет"), self.close_confirm).pack(side="right")
        FlatButton(btns, T("Да"), yes, bg=BLUE, fg="white", hover="#7aa2f5").pack(side="right", padx=(0, 8))

        # под кнопкой, правым краем по её правому краю; не помещается — над ней; всегда в пределах монитора
        p.update_idletasks()
        w, h = p.winfo_reqwidth(), p.winfo_reqheight()
        if at_pointer:
            x, y = px - w // 2, py + POINTER_GAP  # под указателем, с зазором
            r = self.root
            left, top = r.winfo_rootx(), r.winfo_rooty()
            right, bottom = left + r.winfo_width(), top + r.winfo_height()
            if y + h > bottom - 8:
                y = py - h - POINTER_GAP  # снизу не помещается — над указателем
            if w > right - left - 16 or h > bottom - top - 16:  # окно меньше подтверждения — по экрану
                left, top, right, bottom = self._work_area(px, py)
        else:
            left, top, right, bottom = self._work_area(ax, ay)
            x = ax + aw - w
            y = ay + ah + 6
            if y + h > bottom - 8:
                y = ay - h - 6
        x = max(left + 8, min(x, right - w - 8))
        y = max(top + 8, min(y, bottom - h - 8))
        p.geometry(f"+{x}+{y}")
        p.bind("<Escape>", self.close_confirm)
        p.bind("<Return>", yes)
        p.focus_force()
        p.bind("<FocusOut>", lambda e: self.root.after(120, self._confirm_focus_check))

    def _confirm_focus_check(self):
        w = getattr(self, "confirm_win", None)
        if not w:
            return
        f = self.root.focus_get()
        if f is None or not str(f).startswith(str(w)):
            self.close_confirm()

    # ------------------------------------------------ меню настроек
    def close_menu(self, *_):
        if getattr(self, "menu_win", None):
            self.menu_win.destroy()
            self.menu_win = None

    def open_menu(self):
        """Кнопка ⚙: открыть или закрыть меню."""
        if getattr(self, "menu_win", None):
            self.close_menu()
        else:
            self._menu_manage = False  # «Управление аккаунтами» открывается свёрнутым
            self._show_menu(False, fade=True)

    MENU_ANIM_MS = 180  # раскрытие и сворачивание «Добавить аккаунт» и «Управление аккаунтами»

    def _show_menu(self, show_remove=False, fade=False):
        """Своё тёмное меню настроек. Собирается один раз при открытии; дальше щелчки по галочкам, порогам,
        автообновлению и языку меняют только сами эти элементы (`_menu_sync`), а «Добавить аккаунт» и «Управление
        аккаунтами» плавно раскрываются внутри того же окна (`_menu_toggle`) — 1.5.6, владелец: «мерцание при каждом
        изменении», «анимация разворачивания». show_remove — выбор сервиса в «Добавить аккаунт» сразу раскрыт;
        «Управление аккаунтами» — по self._menu_manage. fade — плавно проявить (открытие кнопкой ⚙)."""
        self.close_menu()
        p = tk.Toplevel(self.root)
        if fade:
            fade_in(p)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=LINE)
        box = tk.Frame(p, bg=CARD, padx=6, pady=6)
        box.pack(padx=1, pady=1)
        self.menu_win = p
        m = self._menu = {"tr": [], "sync": [], "sections": {}}

        def tr(w, text):  # надпись, которая меняется при смене языка: запоминаем русский исходник
            w._ru = text
            m["tr"].append(w)
            return w

        mark_w = tkfont.Font(font=(FONT, 10, "bold")).measure("00") + 4  # ширина колонки отметок
        sz = max(13, round(self.root.winfo_fpixels("1i") / 96 * 14))    # сторона квадрата чекбокса

        def item(parent, text, cmd, enabled=True, mark=None, fg=FG, check=None, translate=True):
            """Строка меню. mark — функция, отдающая значок ▸/▾; check — функция, отдающая состояние галочки."""
            row = tk.Frame(parent, bg=CARD, cursor="hand2" if enabled else "arrow")
            row.pack(fill="x")
            if check is None:
                mk = tk.Label(row, text="", bg=CARD, fg=MUTED, width=2, font=(FONT, 10, "bold"))
                mk.pack(side="left")
                if mark:
                    m["sync"].append(lambda: _set(mk, text=mark()))
            else:  # чекбокс: пустой квадрат виден и без отметки
                cb = tk.Canvas(row, width=mark_w, height=sz + 2, bg=CARD, highlightthickness=0)
                cb.pack(side="left")
                x0 = (mark_w - sz) // 2
                rect = cb.create_rectangle(x0, 1, x0 + sz, 1 + sz)
                tick = cb.create_line(x0 + sz * .22, 1 + sz * .52, x0 + sz * .42, 1 + sz * .72,
                                      x0 + sz * .78, 1 + sz * .28, fill="white" if enabled else FAINT,
                                      width=max(2, sz // 7), capstyle="round", joinstyle="round")

                def draw():
                    on_ = bool(check())
                    if getattr(cb, "_on", None) is not on_:  # меняется только квадрат, и только при смене
                        cb._on = on_
                        lit = on_ and enabled
                        cb.itemconfig(rect, outline=BLUE if lit else (MUTED if enabled else FAINT),
                                      fill=BLUE if lit else CARD_HI)
                        cb.itemconfig(tick, state="normal" if on_ else "hidden")
                m["sync"].append(draw)
            lb = tk.Label(row, text=T(text) if translate else text, bg=CARD, fg=fg if enabled else FAINT,
                          font=(FONT, 10), anchor="w", padx=4, pady=5)
            if translate:
                tr(lb, text)
            lb.pack(side="left", fill="x", expand=True)
            if enabled:
                def on(_e, c=CARD_HI):
                    for w in (row, *row.winfo_children()):
                        w.config(bg=c)
                row.bind("<Enter>", on)
                row.bind("<Leave>", lambda e: on(e, CARD))
                for w in (row, *row.winfo_children()):
                    w.bind("<Button-1>", lambda e: cmd())
            return row

        def sep():
            tk.Frame(box, bg=LINE, height=1).pack(fill="x", pady=5, padx=4)

        def chips(title, options, current, setter):
            """Ряд кнопок выбора; options — (надпись, значение, переводить ли); current — функция."""
            tr(tk.Label(box, text=T(title), bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w", padx=28),
               title).pack(fill="x", pady=(4, 2))
            row = tk.Frame(box, bg=CARD)
            row.pack(fill="x", padx=(28, 8), pady=(0, 4))
            group = []
            for label, val, translate in options:
                ch = tk.Label(row, text=T(label) if translate else label, padx=9, pady=3, cursor="hand2")
                if translate:
                    tr(ch, label)
                ch.pack(side="left", padx=(0, 4))
                ch.bind("<Button-1>", lambda e, v=val: (setter(v), self._menu_sync()))
                group.append((ch, val))

            def draw():
                cur = current()
                for ch, val in group:
                    sel = val == cur
                    _set(ch, bg=BLUE if sel else CARD_HI, fg="white" if sel else MUTED,
                         font=(FONT, 9, "bold" if sel else "normal"))
            m["sync"].append(draw)

        def section(key, title, build, opened):
            """Раскрывающийся пункт: заголовок ▸/▾ и под ним рамка clip, которая при анимации обрезает содержимое."""
            sec = {"open": opened, "anim": None, "build": build}
            sec["head"] = item(box, title, lambda: self._menu_toggle(key), mark=lambda: "▾" if sec["open"] else "▸")
            sec["clip"] = clip = tk.Frame(box, bg=CARD)
            sec["inner"] = inner = tk.Frame(clip, bg=CARD)
            m["sections"][key] = sec
            if opened:
                build(inner)
                inner.pack(fill="x")
                clip.pack(fill="x", after=sec["head"])

        def run(fn):
            self.close_menu()
            fn()

        def build_add(parent):  # названия сервисов — их цветами, как в «Управлении аккаунтами» (1.5.3, владелец)
            for kind, label, color in (("claude", "Claude", CLAUDE), ("chatgpt", "ChatGPT", CODEX),
                                       ("google", "Google", GOOGLE)):
                item(parent, "   " + label, lambda k=kind: run(lambda: self.add_account(k)), fg=color,
                     translate=False)

        section("add", "Добавить аккаунт", build_add, bool(show_remove))
        section("manage", "Управление аккаунтами", lambda parent: self.accounts_list(parent, self._menu_accounts_refresh),
                bool(getattr(self, "_menu_manage", False)))
        sep()

        def toggle_topmost():
            self.root.attributes("-topmost", not self.root.attributes("-topmost"))
            self.persist()
            # окно программы стало поверх всех — меню снова над ним (1.5.6, владелец); Windows переставляет окно
            # программы не сразу, поэтому — и после обработки события
            self._menu_raise()
            self.root.after_idle(self._menu_raise)
            self.root.after(100, self._menu_raise)

        def toggle_minimize_to_tray():
            self.s["minimize_to_tray"] = not self.s.get("minimize_to_tray")
            self.persist()

        def toggle_close_to_tray():
            self.s["close_to_tray"] = not self.s.get("close_to_tray")
            self.persist()
            if getattr(self, "tray", None):  # иконка в трее появляется/исчезает сразу
                (self.tray.show if self.s["close_to_tray"] else self.tray.hide)()

        def toggle_autostart():
            try:
                set_autostart(not autostart_enabled())
            except Exception as e:
                self.say(T("Автозапуск: {error}", error=e), RED)

        def toggle_forecast_alerts():
            self.s["forecast_alerts"] = not self.s.get("forecast_alerts")
            self.persist()

        def toggle_two_columns():  # окно меняет ширину — меню переезжает под кнопку ⚙
            self.toggle_two_columns()
            self.root.update()

        tray = bool(getattr(self, "tray", None))
        for text, fn, enabled, check in (
                ("Поверх всех окон", toggle_topmost, True, lambda: bool(self.root.attributes("-topmost"))),
                ("Сворачивать в трей", toggle_minimize_to_tray, tray, lambda: self.s.get("minimize_to_tray")),
                ("Сворачивать в трей при закрытии", toggle_close_to_tray, tray, lambda: self.s.get("close_to_tray")),
                ("Автозапуск после старта системы", toggle_autostart, os.name == "nt", autostart_enabled),
                ("Предупреждения по прогнозу", toggle_forecast_alerts, True, lambda: self.s.get("forecast_alerts")),
                ("Карточки в две колонки", toggle_two_columns, True, lambda: self.s.get("two_columns"))):
            item(box, text, lambda fn=fn: (fn(), self._menu_sync()), enabled=enabled, check=check)
        chips("Автообновление", [(n, s, True) for n, s in INTERVALS], lambda: self.interval, self.set_interval)
        chips("Порог предупреждения", [(f"{v}%", v, False) for v in (70, 80, 90, 95)] + [("выкл", 0, True)],
              lambda: int(self.warn), self.set_warn)
        chips("Язык", [(name, code, False) for code, name in i18n.LANGS], i18n.lang, self.set_lang)
        sep()
        item(box, "Открыть папку данных", lambda: run(self.open_data_folder))
        tk.Label(box, text=f"AI Limits {L.__version__}", bg=CARD, fg=FAINT, font=(FONT, 8), anchor="e",
                 padx=8).pack(fill="x", pady=(2, 0))

        for f in m["sync"]:
            f()
        self._menu_place()
        # закрыть по Esc и по щелчку вне меню
        p.bind("<Escape>", self.close_menu)
        p.focus_force()
        p.bind("<FocusOut>", lambda e: self.root.after(120, self._menu_focus_check))

    def _menu_raise(self):
        """Меню ⚙ — над окном программы. После смены «Поверх всех окон» Windows ставит окно программы выше
        меню, а lift и повторный -topmost средствами Tk его не поднимают — SetWindowPos(HWND_TOPMOST)."""
        p = getattr(self, "menu_win", None)
        if p is not None and p.winfo_exists():
            try:  # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                swp = ctypes.windll.user32.SetWindowPos
                swp.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
                swp(int(p.wm_frame(), 16), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x13)
            except (AttributeError, OSError, ValueError):
                p.lift()

    def _menu_sync(self):
        """Привести открытое меню к настройкам: галочки, выбранные кнопки, значки ▸/▾, язык надписей. Меняется
        только то, что изменилось (`_set`), окно и остальные элементы не пересоздаются."""
        m, p = getattr(self, "_menu", None), getattr(self, "menu_win", None)
        if not m or not p or not p.winfo_exists():
            return
        for w in m["tr"]:
            if w.winfo_exists():
                _set(w, text=T(w._ru))
        for f in m["sync"]:
            f()
        self._menu_place()

    def _menu_place(self):
        """Меню под кнопкой ⚙; правый край — не дальше правого края кнопки «Обновить» (поле содержимого окна)."""
        p = getattr(self, "menu_win", None)
        if not p or not p.winfo_exists():
            return
        p.update_idletasks()
        bx = self.menu_btn.winfo_rootx()
        by = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height() + 4
        right = self.refresh_btn.winfo_rootx() + self.refresh_btn.winfo_width()
        geo = f"+{min(bx, right - p.winfo_reqwidth())}+{by}"
        if getattr(p, "_geo", None) != geo:
            p._geo = geo
            p.geometry(geo)

    def _menu_toggle(self, key, open_=None):
        """Раскрыть или свернуть пункт меню с анимацией: рамка clip плавно меняет высоту (ease-out,
        MENU_ANIM_MS), содержимое под ней лежит целиком и открывается сверху вниз."""
        m = getattr(self, "_menu", None)
        if not m or key not in m["sections"]:
            return
        sec = m["sections"][key]
        want = (not sec["open"]) if open_ is None else bool(open_)
        if key == "manage":
            self._menu_manage = want
        if want == sec["open"]:
            return
        sec["open"] = want
        self._menu_sync()  # ▸ → ▾
        clip, inner = sec["clip"], sec["inner"]
        cur = clip.winfo_height() if clip.winfo_manager() else 0
        if want and not sec["anim"]:  # содержимое собирается заново — список аккаунтов всегда свежий
            for w in inner.winfo_children():
                w.destroy()
            sec["build"](inner)
        inner.pack_forget()
        inner.place(x=0, y=0, relwidth=1)
        clip.pack_propagate(False)
        clip.update_idletasks()
        clip.config(width=inner.winfo_reqwidth(), height=max(cur, 1))
        if not clip.winfo_manager():
            clip.pack(fill="x", after=sec["head"])
        start, end = cur, inner.winfo_reqheight() if want else 0
        t0, token = time.monotonic(), object()
        sec["anim"] = token

        def step():
            if sec["anim"] is not token or not clip.winfo_exists():
                return  # меню закрыли или пункт щёлкнули снова — эта анимация больше не нужна
            k = min(1.0, (time.monotonic() - t0) * 1000 / self.MENU_ANIM_MS)
            clip.config(height=max(1, round(start + (end - start) * (1 - (1 - k) ** 3))))
            self._menu_place()
            if k < 1:
                self.root.after(12, step)
                return
            sec["anim"] = None
            if want:  # дальше рамка снова подстраивается под содержимое (поле имени, сообщение об ошибке)
                inner.place_forget()
                inner.pack(fill="x")
                clip.pack_propagate(True)
            else:
                clip.pack_forget()
                for w in inner.winfo_children():
                    w.destroy()
            self._menu_place()
        step()

    def _menu_accounts_refresh(self):
        """Список «Управления аккаунтами» собрать заново (переименовали, удалили, сменили язык): новый собирается
        рядом и заменяет прежний за один проход; остальное меню не трогается."""
        sec = (getattr(self, "_menu", None) or {}).get("sections", {}).get("manage")
        p = getattr(self, "menu_win", None)
        if not sec or not p or not p.winfo_exists() or not sec["open"] or sec["anim"]:
            return
        new = tk.Frame(sec["clip"], bg=CARD)
        sec["build"](new)
        sec["inner"].destroy()
        new.pack(fill="x")
        sec["inner"] = new
        self._menu_place()

    def set_lang(self, code):
        """Смена языка интерфейса. С 1.5.6 карточки и строка «макс.» не пересоздаются: уже показанным надписям
        подставляется новый текст (`CardView.retranslate`), остальное делает обычный render; прогнозы
        пересчитываются — в них есть текст. Меню ⚙ переводит само себя (`_menu_sync` после щелчка)."""
        if code == i18n.lang():
            return
        i18n.set_lang(code)
        self.s["lang"] = i18n.lang()
        self.persist()
        self.refresh_btn.config(text=T("⟳  Обновить"))
        self.menu_tip.text = T("Настройки")
        for card in self.cards.values():
            card.retranslate()
        if self.footer is not None:
            self.footer_max.config(text=T("макс."))
        self._menu_accounts_refresh()
        if self.data:
            self.update_history()
            self.render(self.data)
            self.update_tray_tip(self.data)
        self.set_status_updated()

    def open_data_folder(self):
        """Папка с настройками, журналами и резервными копиями — в Проводнике."""
        try:
            os.makedirs(L.APPDIR, exist_ok=True)
            os.startfile(L.APPDIR)
        except Exception as e:
            self.say(T("Не удалось открыть папку: {error}", error=e), RED)

    def _menu_focus_check(self):
        w = getattr(self, "menu_win", None)
        if not w:
            return
        f = self.root.focus_get()
        if f is None or not str(f).startswith(str(w)):
            self.close_menu()

    def hide_alert(self):
        w, self.alert_win = getattr(self, "alert_win", None), None
        if w:
            try:
                w.destroy()
            except tk.TclError:
                pass

    def _fade_alert(self, win, a, b, ms, then=None):
        """Плавно меняет прозрачность окна win от a до b за ms миллисекунд, затем вызывает then."""
        steps = max(1, ms // 16)

        def tick(i):
            if self.alert_win is not win:  # окно уже закрыто или заменено новым
                return
            try:
                win.attributes("-alpha", a + (b - a) * i / steps)
            except tk.TclError:
                return
            if i < steps:
                win.after(16, tick, i + 1)
            elif then:
                then()
        tick(0)

    def show_alert(self, hits, soon=()):
        """Всплывающее предупреждение о пороге — справа над часами: плавно появляется,
        через 5 секунд плавно исчезает; ✕ закрывает сразу. hits: [(название лимита, % израсходовано)]."""
        self.hide_alert()
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.attributes("-alpha", 0.0)
        p.configure(bg=LINE)
        self.alert_win = p
        box = tk.Frame(p, bg=CARD)
        box.pack(padx=1, pady=1)
        # soon: [(чей недельный лимит, «чт 14:00»)] — предупреждение по прогнозу
        accent = color_for(max(u for _, u in hits), self.warn) if hits else YELLOW
        tk.Frame(box, bg=accent, width=4).pack(side="left", fill="y")
        inner = tk.Frame(box, bg=CARD, padx=14, pady=11)
        inner.pack(side="left")
        tk.Frame(inner, bg=CARD, width=300, height=1).pack()  # минимальная ширина
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="AI Limits", bg=CARD, fg=FG, font=(FONT_D, 11, "bold")).pack(side="left")
        x = tk.Label(head, text="✕", bg=CARD, fg=MUTED, font=(FONT, 10), cursor="hand2", padx=5)
        x.pack(side="right")
        x.bind("<Enter>", lambda e: x.config(fg=FG, bg=CARD_HI))
        x.bind("<Leave>", lambda e: x.config(fg=MUTED, bg=CARD))
        x.bind("<Button-1>", lambda e: self.hide_alert())
        if hits:
            tk.Label(inner, text=T("Израсходовано больше {pct}% лимита", pct=f"{self.warn:.0f}"), bg=CARD, fg=MUTED,
                     font=(FONT, 9), anchor="w").pack(fill="x", pady=(1, 6))
        for name, used in hits[:5]:
            row = tk.Frame(inner, bg=CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{used:.0f}%", bg=CARD, fg=color_for(used, self.warn),
                     font=(FONT, 10, "bold"), width=5, anchor="e").pack(side="right")
            who, _, win = name.rpartition(" · ")  # название окна лимита в данных русское — переводим при показе
            tk.Label(row, text=f"{who} · {T(win)}", bg=CARD, fg=FG, font=(FONT, 10), anchor="w").pack(side="left")
        if len(hits) > 5:
            tk.Label(inner, text=T("и ещё {n}", n=len(hits) - 5), bg=CARD, fg=FAINT, font=(FONT, 9),
                     anchor="w").pack(fill="x", pady=(3, 0))

        if soon:
            tk.Label(inner, text=T("При таком темпе закончится раньше сброса"), bg=CARD, fg=MUTED,
                     font=(FONT, 9), anchor="w").pack(fill="x", pady=(8 if hits else 1, 6))
            for name, when in soon[:5]:
                row = tk.Frame(inner, bg=CARD)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=T("до {when}", when=when), bg=CARD, fg=YELLOW,
                         font=(FONT, 10, "bold"), anchor="e").pack(side="right", padx=(12, 0))
                tk.Label(row, text=name, bg=CARD, fg=FG, font=(FONT, 10), anchor="w").pack(side="left")

        # правый нижний угол рабочей области экрана (над часами)
        p.update_idletasks()
        w, h = p.winfo_reqwidth(), p.winfo_reqheight()
        right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
        if os.name == "nt":
            try:
                rc = ctypes.wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rc), 0):  # SPI_GETWORKAREA
                    right, bottom = rc.right, rc.bottom
            except Exception:
                pass
        p.geometry(f"+{right - w - 14}+{bottom - h - 14}")

        def fade_out():
            self._fade_alert(p, self.ALERT_ALPHA, 0.0, 450, then=self.hide_alert)
        self._fade_alert(p, 0.0, self.ALERT_ALPHA, 250, then=lambda: p.after(self.ALERT_SHOW_MS, fade_out))
