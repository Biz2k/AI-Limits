"""Иконка окна и работа с треем: сворачивание, меню иконки, мини-окно с лимитами."""
import ctypes
import ctypes.wintypes
import os
import queue
import sys
import tkinter as tk

import limits as L
from i18n import T
from ui_theme import (
    Bar, CARD, CARD_HI, CLAUDE, FAINT, FG, FONT, FONT_D, GOOGLE, GREEN, LINE, MUTED, RED, YELLOW,
    color_for)

GUI_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "limits_gui.pyw")  # главный файл окна


class TrayMixin:
    """Часть класса App (limits_gui.pyw): иконка и трей. Пользуется полями и методами App через self."""

    def make_icon(self):
        """Рисует иконку 64×64 (скруглённый квадрат + 4 столбика) и сохраняет её как .ico."""
        S, R = 64, 14
        img = tk.PhotoImage(width=S, height=S)  # пустые пиксели прозрачны
        for y in range(S):
            dy = max(R - y, y - (S - 1 - R), 0)
            dx = int(round(R - (R * R - dy * dy) ** 0.5)) if dy else 0
            img.put("#1d212a", to=(dx, y, S - dx, y + 1))
        for i, (h, col) in enumerate([(22, GREEN), (36, YELLOW), (46, CLAUDE), (30, GOOGLE)]):
            x = 9 + i * 12
            img.put(col, to=(x, 54 - h, x + 9, 54))
        self._icon = img
        # в exe (PyInstaller) папка скрипта временная — иконку кладём в папку настроек
        ico_dir = L.APPDIR if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        os.makedirs(ico_dir, exist_ok=True)
        self.ico_path = os.path.join(ico_dir, "ai_limits.ico")
        try:  # ICO с PNG внутри (поддерживается Windows Vista+)
            png_path = self.ico_path + ".png"
            img.write(png_path, format="png")
            with open(png_path, "rb") as f:
                png = f.read()
            os.remove(png_path)
            import struct
            ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", S, S, 0, 0, 1, 32, len(png), 22) + png
            with open(self.ico_path, "wb") as f:
                f.write(ico)
        except Exception:
            self.ico_path = None
        return img

    # ------------------------------------------------ трей
    def set_native_icon(self):
        """Иконка окна через WM_SETICON — её берёт панель задач."""
        if os.name != "nt" or not self.ico_path:
            return
        try:
            u = ctypes.WinDLL("user32")
            u.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            u.LoadImageW.restype = ctypes.c_void_p
            u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
            hwnd = u.GetParent(self.root.winfo_id())
            for kind, size in ((1, 48), (0, 16)):  # ICON_BIG, ICON_SMALL
                h = u.LoadImageW(None, self.ico_path, 1, size, size, 0x10)
                if h:
                    u.SendMessageW(hwnd, 0x0080, kind, h)  # WM_SETICON
            self._hicons = True
            self.set_window_appid(hwnd)
        except Exception:
            pass

    def set_window_appid(self, hwnd):
        """AppUserModelID + иконка у самого окна (IPropertyStore) — иначе Windows
        показывает в панели задач иконку пакета Python из Microsoft Store."""
        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                        ("d", ctypes.c_ubyte * 8)]

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]

        class PROPVARIANT(ctypes.Structure):
            _fields_ = [("vt", ctypes.c_uint16), ("r1", ctypes.c_uint16), ("r2", ctypes.c_uint16),
                        ("r3", ctypes.c_uint16), ("p", ctypes.c_void_p), ("pad", ctypes.c_void_p)]

        def guid(s):
            import uuid
            u = uuid.UUID(s)
            return GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))

        ctypes.windll.ole32.CoInitialize(None)
        store = ctypes.c_void_p()
        iid = guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")  # IID_IPropertyStore
        sh = ctypes.windll.shell32
        sh.SHGetPropertyStoreForWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        if sh.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store)) != 0:
            return
        vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0],
                           ctypes.POINTER(ctypes.c_void_p))
        SetValue = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                                      ctypes.POINTER(PROPVARIANT))(vtbl[6])
        Commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
        Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        fmt = "9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"  # PKEY_AppUserModel_*
        self._pv_bufs = []
        if getattr(sys, "frozen", False):  # exe: перезапуск и иконка — из самого exe
            relaunch, icon_res = f'"{sys.executable}"', sys.executable + ",0"
        else:
            pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            relaunch = f'"{pyw}" "{GUI_SCRIPT}"'
            icon_res = self.ico_path + ",0"
        values = [(2, relaunch),                        # RelaunchCommand
                  (3, icon_res),                        # RelaunchIconResource
                  (4, "AI Limits"),                     # RelaunchDisplayNameResource
                  (5, "AILimits.Monitor")]              # ID (ставим последним)
        for pid, text in values:
            buf = ctypes.create_unicode_buffer(text)
            self._pv_bufs.append(buf)
            pv = PROPVARIANT(vt=31, p=ctypes.cast(buf, ctypes.c_void_p))  # VT_LPWSTR
            key = PROPERTYKEY(guid(fmt), pid)
            SetValue(store, ctypes.byref(key), ctypes.byref(pv))
        Commit(store)
        Release(store)

    def setup_tray(self):
        self.set_native_icon()
        self.q = queue.Queue()
        self.tray = None
        if os.name != "nt" or not self.ico_path:
            return
        try:
            from tray import TrayIcon
            self.tray = TrayIcon(self.ico_path, "AI Limits", on_click=lambda: self.q.put("toggle"),
                                 menu=[(1, T("Открыть")), (2, T("Обновить")), None, (3, T("Выход"))],
                                 on_menu=self.q.put,
                                 on_hover=lambda on: self.q.put("hover_on" if on else "hover_off"),
                                 on_rclick=lambda x, y: self.q.put(("menu", x, y)))
        except Exception:
            self.tray = None
            return
        self.root.after(150, self._poll_tray)

    def tray_always(self):
        """Иконка в трее постоянно (и при открытом окне) — когда включено «Сворачивать в трей при закрытии»."""
        return bool(self.s.get("close_to_tray") and getattr(self, "tray", None))

    def _on_unmap(self, e):
        if e.widget is not self.root:
            return
        self.close_menu()  # меню настроек и окно подтверждения не остаются на экране без окна
        self.close_confirm()
        if self.root.state() == "iconic" and self.s.get("minimize_to_tray") and getattr(self, "tray", None):
            self.root.after(10, self._minimized_to_tray)  # кнопка «—»: вместо панели задач — в трей

    def _minimized_to_tray(self):
        if self.root.state() == "iconic":
            self.to_tray()

    def to_tray(self):
        """Спрятать окно и показать иконку в трее."""
        if not getattr(self, "tray", None):
            return
        self.close_menu()
        self.close_confirm()
        self.tray.show()
        self.root.withdraw()

    def show_window(self):
        if getattr(self, "tray", None) and not self.tray_always():
            self.tray.hide()  # без «в трей при закрытии» иконка есть только пока окно в трее
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _poll_tray(self):
        try:
            while True:
                ev = self.q.get_nowait()
                if isinstance(ev, tuple):  # ("menu", x, y) — правый щелчок по иконке
                    self.show_tray_menu(ev[1], ev[2])
                elif ev == "toggle":
                    if self.root.state() != "normal":
                        self.show_window()
                    else:
                        self.to_tray()
                elif ev == 1:
                    self.show_window()
                elif ev == 2:
                    self.refresh()
                elif ev == 3:
                    self.quit_app()
                    return
                elif ev == "hover_on":
                    if not getattr(self, "tray_menu", None):  # меню иконки открыто — мини-окно не показываем
                        self.show_popup()
                elif ev == "hover_off":
                    self.hide_popup()
        except queue.Empty:
            pass
        self.root.after(80, self._poll_tray)

    # ------------------------------------------------ меню иконки в трее
    def close_tray_menu(self, *_):
        w, self.tray_menu = getattr(self, "tray_menu", None), None
        if w:
            try:
                w.destroy()
            except tk.TclError:
                pass

    def show_tray_menu(self, x, y):
        """Своё тёмное меню по правому щелчку на иконке в трее (вместо системного): над курсором,
        в пределах рабочей области монитора. Закрывается выбором пункта, Esc и щелчком мимо."""
        self.close_tray_menu()
        self.hide_popup()
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=LINE)
        self.tray_menu = p
        box = tk.Frame(p, bg=CARD, padx=6, pady=6)
        box.pack(padx=1, pady=1)
        tk.Frame(box, bg=CARD, width=round(self.root.winfo_fpixels("1i") / 96 * 150), height=1).pack()

        def item(text, cmd):
            lb = tk.Label(box, text=text, bg=CARD, fg=FG, font=(FONT, 10), anchor="w", padx=14, pady=5,
                          cursor="hand2")
            lb.pack(fill="x")
            lb.bind("<Enter>", lambda e: lb.config(bg=CARD_HI))
            lb.bind("<Leave>", lambda e: lb.config(bg=CARD))
            lb.bind("<Button-1>", lambda e: (self.close_tray_menu(), cmd()))

        item(T("Открыть"), self.show_window)
        item(T("Обновить"), self.refresh)
        tk.Frame(box, bg=LINE, height=1).pack(fill="x", pady=5, padx=4)
        item(T("Выход"), self.quit_app)

        p.update_idletasks()
        w, h = p.winfo_reqwidth(), p.winfo_reqheight()
        left, top, right, bottom = self._work_area(x, y)
        px = max(left + 4, min(x, right - w - 4))
        py = max(top + 4, min(y - h, bottom - h - 4))
        p.geometry(f"+{px}+{py}")
        p.bind("<Escape>", self.close_tray_menu)
        try:  # активируем меню, чтобы работал Esc; программа при этом может быть свёрнута в трей
            p.focus_force()
        except tk.TclError:
            pass
        self.root.after(250, self._tray_menu_watch)

    def _tray_menu_watch(self):
        """Закрывает меню иконки при щелчке мимо него (окно без рамки может не получить фокус)."""
        w = getattr(self, "tray_menu", None)
        if not w:
            return
        try:
            mx, my = w.winfo_pointerxy()
            inside = (w.winfo_rootx() <= mx < w.winfo_rootx() + w.winfo_width() and
                      w.winfo_rooty() <= my < w.winfo_rooty() + w.winfo_height())
            down = os.name == "nt" and any(ctypes.windll.user32.GetAsyncKeyState(k) & 0x8000 for k in (1, 2, 4))
        except Exception:
            return self.close_tray_menu()
        if down and not inside:
            return self.close_tray_menu()
        self.root.after(50, self._tray_menu_watch)

    # ------------------------------------------------ мини-окно у трея
    def hide_popup(self):
        if getattr(self, "popup", None):
            self.popup.destroy()
            self.popup = None

    def show_popup(self):
        self.hide_popup()
        if not self.data or self.root.state() == "withdrawn" and False:
            return
        claude, ag = self.data
        rows = []
        if isinstance(claude, dict):
            d = {r["name"]: r["used"] for r in claude["limits"]}
            rows.append(("Claude Code", CLAUDE, d.get("Неделя"), d.get("5 часов"), None))
        for email, r in ag:
            if not isinstance(r, dict):
                rows.append((email.split("@")[0], GOOGLE, None, None,
                             "загрузка" if r is None else "ошибка"))
                continue
            d = {m["name"]: m["used"] for m in r["models"]}
            ide = r.get("source") == "данные IDE Antigravity"
            rows.append((email.split("@")[0], GOOGLE, d.get("Неделя"), d.get("5 часов"),
                         "IDE" if ide else None))

        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=LINE)
        box = tk.Frame(p, bg=CARD, padx=14, pady=12)
        box.pack(padx=1, pady=1)
        head = tk.Frame(box, bg=CARD)
        head.grid(row=0, column=0, columnspan=7, sticky="we", pady=(0, 8))
        tk.Label(head, text="AI Limits", bg=CARD, fg=FG, font=(FONT_D, 11, "bold")).pack(side="left")
        tk.Label(head, text=self.status.cget("text").split("  ·")[0], bg=CARD, fg=FAINT,
                 font=(FONT, 8)).pack(side="right")
        for c, t in ((2, T("неделя")), (5, T("5 часов"))):
            tk.Label(box, text=t, bg=CARD, fg=FAINT, font=(FONT, 8)).grid(row=1, column=c, columnspan=2, sticky="w")

        def cell(row, col, used):
            if used is None:
                Bar(box, 0, FAINT, width=90).grid(row=row, column=col, padx=(0, 6), sticky="we")
                tk.Label(box, text="—", bg=CARD, fg=FAINT, font=(FONT, 10), width=5,
                         anchor="e").grid(row=row, column=col + 1, padx=(0, 14))
            else:
                col_ = color_for(used, self.warn)
                Bar(box, used, col_, width=90).grid(row=row, column=col, padx=(0, 6), sticky="we")
                tk.Label(box, text=f"{used:.0f}%", bg=CARD, fg=col_, font=(FONT, 10, "bold"),
                         width=5, anchor="e").grid(row=row, column=col + 1, padx=(0, 14))

        for i, (name, accent, week, h5, note) in enumerate(rows, start=2):
            tk.Frame(box, bg=accent, width=3, height=18).grid(row=i, column=0, padx=(0, 8), pady=5)
            nm = tk.Frame(box, bg=CARD)
            nm.grid(row=i, column=1, sticky="w", padx=(0, 14))
            tk.Label(nm, text=name[:16], bg=CARD, fg=FG, font=(FONT, 10)).pack(side="left")
            if note:
                tk.Label(nm, text=T(note), bg=CARD, fg=GREEN if note == "IDE" else (MUTED if note == "загрузка" else RED),
                         font=(FONT, 8, "bold")).pack(side="left", padx=(6, 0))
            cell(i, 2, week)
            cell(i, 5, h5)
        for j, (name, line) in enumerate(self.forecast_soon()[:3]):  # прогноз по недельным лимитам
            tk.Label(box, text=f"{name} — {line}", bg=CARD, fg=YELLOW, font=(FONT, 8),
                     anchor="w").grid(row=len(rows) + 2 + j, column=0, columnspan=7, sticky="w",
                                      pady=(6 if j == 0 else 0, 0))

        p.update_idletasks()
        w, h = p.winfo_reqwidth(), p.winfo_reqheight()
        sw, sh = p.winfo_screenwidth(), p.winfo_screenheight()
        rect = self.tray.icon_rect() if getattr(self, "tray", None) else None
        if rect:  # над иконкой трея, по центру
            cx = (rect[0] + rect[2]) // 2
            x = cx - w // 2
            y = rect[1] - h - 12
            if y < 8:  # панель задач сверху — показываем под иконкой
                y = rect[3] + 12
        else:
            x, y = self.root.winfo_pointerx() - w // 2, self.root.winfo_pointery() - h - 24
        x = min(max(x, 8), sw - w - 8)
        y = min(max(y, 8), sh - h - 8)
        p.geometry(f"+{x}+{y}")
        self.popup = p

    def update_tray_tip(self, claude, ag):
        if not getattr(self, "tray", None):
            return

        def fmt(v):
            return "—" if v is None else f"{v:.0f}%"
        lines = []
        if isinstance(claude, dict):
            d = {r["name"]: r["used"] for r in claude["limits"]}
            lines.append(T("{name}  нед {week} · 5ч {five}", name="Claude",
                           week=fmt(d.get("Неделя")), five=fmt(d.get("5 часов"))))
        for email, r in ag:
            name = email.split("@")[0][:11]
            if not isinstance(r, dict):
                lines.append(f"{name}  {T('загрузка…') if r is None else T('ошибка')}")
                continue
            d = {m["name"]: m["used"] for m in r["models"]}
            lines.append(T("{name}  нед {week} · 5ч {five}", name=name, week=fmt(d.get("Неделя")),
                           five=fmt(d.get("5 часов"))))
        tip = "\n".join(lines)
        if len(tip) > 127:
            tip = tip[:126] + "…"
        self.tray.set_tip(tip or "AI Limits")
