"""Всплывающие окна AI Limits: меню настроек, подтверждение, ввод OAuth-ключей, предупреждение о пороге."""
import ctypes
import ctypes.wintypes
import os
import tkinter as tk
from tkinter import font as tkfont

import i18n
import limits as L
from i18n import T
from ui_theme import (
    CARD, CARD_HI, FAINT, FG, FONT, FONT_D, FlatButton, GOOGLE, GREEN, INTERVALS, LINE, MUTED, RED, YELLOW,
    color_for)
from autostart import autostart_enabled, set_autostart


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

    def confirm(self, anchor, title, text, on_yes):
        """Своё тёмное окно подтверждения (вместо системного) рядом с виджетом anchor, в пределах экрана.
        «Да» вызывает on_yes; «Нет», Esc и щелчок мимо окна — закрывают."""
        self.close_confirm()
        self.close_menu()
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
        FlatButton(btns, T("Да"), yes, bg=GOOGLE, fg="white", hover="#7aa2f5").pack(side="right", padx=(0, 8))

        # под кнопкой, правым краем по её правому краю; не помещается — над ней; всегда в пределах монитора
        p.update_idletasks()
        w, h = p.winfo_reqwidth(), p.winfo_reqheight()
        ax, ay = anchor.winfo_rootx(), anchor.winfo_rooty()
        left, top, right, bottom = self._work_area(ax, ay)
        x = ax + anchor.winfo_width() - w
        y = ay + anchor.winfo_height() + 6
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
            self._show_menu(False)

    def _show_menu(self, show_remove):
        """Своё тёмное меню настроек: отметки и выбор видны на тёмном фоне."""
        self.close_menu()
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=LINE)
        box = tk.Frame(p, bg=CARD, padx=6, pady=6)
        box.pack(padx=1, pady=1)
        self.menu_win = p

        mark_w = tkfont.Font(font=(FONT, 10, "bold")).measure("00") + 4  # ширина колонки отметок
        sz = max(13, round(self.root.winfo_fpixels("1i") / 96 * 14))    # сторона квадрата чекбокса

        def item(text, cmd, enabled=True, mark=None, fg=FG, check=None):
            row = tk.Frame(box, bg=CARD, cursor="hand2" if enabled else "arrow")
            row.pack(fill="x")
            if check is None:
                tk.Label(row, text=mark or "", bg=CARD, fg=MUTED, width=2,
                         font=(FONT, 10, "bold")).pack(side="left")
            else:  # чекбокс: пустой квадрат виден и без отметки
                cb = tk.Canvas(row, width=mark_w, height=sz + 2, bg=CARD, highlightthickness=0)
                cb.pack(side="left")
                x0 = (mark_w - sz) // 2
                on_ = check and enabled
                cb.create_rectangle(x0, 1, x0 + sz, 1 + sz, outline=GOOGLE if on_ else (MUTED if enabled else FAINT),
                                    fill=GOOGLE if on_ else CARD_HI)
                if check:
                    cb.create_line(x0 + sz * .22, 1 + sz * .52, x0 + sz * .42, 1 + sz * .72,
                                   x0 + sz * .78, 1 + sz * .28, fill="white" if enabled else FAINT,
                                   width=max(2, sz // 7), capstyle="round", joinstyle="round")
            lb = tk.Label(row, text=text, bg=CARD, fg=fg if enabled else FAINT,
                          font=(FONT, 10), anchor="w", padx=4, pady=5)
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
            tk.Label(box, text=title, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w",
                     padx=28).pack(fill="x", pady=(4, 2))
            row = tk.Frame(box, bg=CARD)
            row.pack(fill="x", padx=(28, 8), pady=(0, 4))
            for label, val in options:
                sel = val == current
                ch = tk.Label(row, text=label, bg=GOOGLE if sel else CARD_HI,
                              fg="white" if sel else MUTED, font=(FONT, 9, "bold" if sel else "normal"),
                              padx=9, pady=3, cursor="hand2")
                ch.pack(side="left", padx=(0, 4))
                ch.bind("<Button-1>", lambda e, v=val: (setter(v), self._show_menu(show_remove)))

        def run(fn):
            self.close_menu()
            fn()

        accs = L.load_accounts()
        item(T("Добавить Google-аккаунт"), lambda: run(self.add_account))
        item(T("Убрать Google-аккаунт"), lambda: self._show_menu(not show_remove), enabled=bool(accs),
             mark="▾" if show_remove else "▸")
        if show_remove and accs:
            for a in accs:
                item(f"   ✕  {a['email']}", lambda e=a["email"]: run(lambda: self.remove_account(e)),
                     fg=MUTED)
        sep()
        topmost = bool(self.root.attributes("-topmost"))
        item(T("Поверх всех окон"),
             lambda: (self.root.attributes("-topmost", not topmost), self.persist(),
                      self._show_menu(show_remove)),
             check=topmost)

        def toggle_minimize_to_tray():
            self.s["minimize_to_tray"] = not self.s.get("minimize_to_tray")
            self.persist()
            self._show_menu(show_remove)

        def toggle_close_to_tray():
            self.s["close_to_tray"] = not self.s.get("close_to_tray")
            self.persist()
            if getattr(self, "tray", None):  # иконка в трее появляется/исчезает сразу
                (self.tray.show if self.s["close_to_tray"] else self.tray.hide)()
            self._show_menu(show_remove)

        def toggle_autostart():
            try:
                set_autostart(not autostart_enabled())
            except Exception as e:
                self.status.config(text=T("Автозапуск: {error}", error=e), fg=RED)
            self._show_menu(show_remove)

        def toggle_forecast_alerts():
            self.s["forecast_alerts"] = not self.s.get("forecast_alerts")
            self.persist()
            self._show_menu(show_remove)

        item(T("Сворачивать в трей"), toggle_minimize_to_tray,
             enabled=bool(getattr(self, "tray", None)), check=bool(self.s.get("minimize_to_tray")))
        item(T("Сворачивать в трей при закрытии"), toggle_close_to_tray,
             enabled=bool(getattr(self, "tray", None)), check=bool(self.s.get("close_to_tray")))
        item(T("Автозапуск после старта системы"), toggle_autostart, enabled=os.name == "nt",
             check=autostart_enabled())
        item(T("Предупреждения по прогнозу"), toggle_forecast_alerts, check=bool(self.s.get("forecast_alerts")))
        chips(T("Автообновление"), [(T(n), s) for n, s in INTERVALS], self.interval, self.set_interval)
        chips(T("Порог предупреждения"), [(f"{v}%", v) for v in (70, 80, 90, 95)] + [(T("выкл"), 0)], int(self.warn),
              lambda v: self.set_warn(v))
        chips(T("Язык"), [(name, code) for code, name in i18n.LANGS], i18n.lang(), self.set_lang)
        sep()
        item(T("Открыть папку данных"), lambda: run(self.open_data_folder))
        tk.Label(box, text=f"AI Limits {L.__version__}", bg=CARD, fg=FAINT, font=(FONT, 8), anchor="e",
                 padx=8).pack(fill="x", pady=(2, 0))

        p.update_idletasks()
        bx = self.menu_btn.winfo_rootx()
        by = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height() + 4
        # правый край меню — не дальше правого края кнопки «Обновить» (поле содержимого окна)
        right = self.refresh_btn.winfo_rootx() + self.refresh_btn.winfo_width()
        bx = min(bx, right - p.winfo_reqwidth())
        p.geometry(f"+{bx}+{by}")
        # закрыть по Esc и по щелчку вне меню
        p.bind("<Escape>", self.close_menu)
        p.focus_force()
        p.bind("<FocusOut>", lambda e: self.root.after(120, self._menu_focus_check))

    def set_lang(self, code):
        """Смена языка интерфейса. Надписи, созданные один раз (кнопки, карточки, строка «Максимум»),
        пересоздаются; прогнозы пересчитываются — в них есть текст."""
        i18n.set_lang(code)
        self.s["lang"] = i18n.lang()
        self.persist()
        self.refresh_btn.config(text=T("⟳  Обновить"))
        self.menu_tip.text = T("Настройки")
        for card in self.cards.values():
            card.outer.destroy()
        if self.footer is not None:
            self.footer.destroy()
        self.cards, self.card_order, self.footer = {}, [], None
        self._last_sig = None
        if self.data:
            self.update_history()
            self.render(*self.data)
            self.update_tray_tip(*self.data)
        self.set_status_updated()

    def open_data_folder(self):
        """Папка с настройками, журналами и резервными копиями — в Проводнике."""
        try:
            os.makedirs(L.APPDIR, exist_ok=True)
            os.startfile(L.APPDIR)
        except Exception as e:
            self.status.config(text=T("Не удалось открыть папку: {error}", error=e), fg=RED)

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
