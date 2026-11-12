"""Оформление окна AI Limits: цвета, шрифты, полоса лимита, кнопка, подсказка, подписи времени."""
import datetime as dt
import os
import tkinter as tk

from i18n import T, day


BG = "#0e1014"
CARD = "#171a21"
CARD_HI = "#1d212a"
LINE = "#262b36"
TRACK = "#262b36"
FG = "#e8eaef"
MUTED = "#8a91a0"
FAINT = "#5c6372"
GREEN = "#3ecf8e"
YELLOW = "#f2c94c"
RED = "#ff5c5c"
CLAUDE = "#d97757"
GOOGLE = "#5b8def"
FONT = "Segoe UI Variable Text" if os.name == "nt" else "Helvetica"
FONT_D = "Segoe UI Variable Display" if os.name == "nt" else "Helvetica"
INTERVALS = [("1 мин", 60), ("5 мин", 300), ("15 мин", 900), ("выкл", 0)]


def color_for(used, warn):
    warn = warn or 80  # предупреждение выключено — цвета как при 80%
    if used >= max(warn, 90):
        return RED
    if used >= min(warn, 70):
        return YELLOW
    return GREEN


def short_reset(iso):
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    secs = int((t - dt.datetime.now(dt.timezone.utc)).total_seconds())
    if secs <= 0:
        return T("сброшено")
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return T("{d}д {h}ч", d=d, h=h) if d else (T("{h}ч {m}м", h=h, m=f"{m:02d}") if h else T("{m}м", m=m))


def local_time(iso):
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return f"{day(t.weekday())} {t:%d.%m, %H:%M}"
    except Exception:
        return ""


# ---------------------------------------------------------------- виджеты
class Tooltip:
    def __init__(self, w, text):
        self.w, self.text, self.tip = w, text, None
        w.bind("<Enter>", self.show, add="+")
        w.bind("<Leave>", self.hide, add="+")

    def show(self, _):
        if not self.text:
            return
        x, y = self.w.winfo_rootx() + 10, self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#2a2f3a", fg=FG, font=(FONT, 9),
                 padx=8, pady=4).pack()

    def hide(self, _):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def rounded(cv, x1, y1, x2, y2, r, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class Bar(tk.Canvas):
    H = 8

    def __init__(self, master, used, color, **kw):
        super().__init__(master, height=self.H, bg=CARD, highlightthickness=0, **kw)
        self.used, self.color = used, color
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, used, color):
        if (used, color) != (self.used, self.color):
            self.used, self.color = used, color
            self.draw()

    def draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 4:
            return
        rounded(self, 0, 0, w, self.H, self.H / 2, fill=TRACK, outline="")
        fw = max(self.H, w * min(self.used, 100) / 100) if self.used > 0 else 0
        if fw:
            rounded(self, 0, 0, fw, self.H, self.H / 2, fill=self.color, outline="")


class FlatButton(tk.Label):
    def __init__(self, master, text, cmd, bg=CARD_HI, fg=FG, hover="#2a2f3a", **kw):
        super().__init__(master, text=text, bg=bg, fg=fg, cursor="hand2",
                         font=(FONT, 10), padx=12, pady=6, **kw)
        self._bg, self._hover, self.cmd = bg, hover, cmd
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<Button-1>", lambda e: self.cmd())
