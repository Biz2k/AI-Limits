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
GOOGLE = "#6d6af2"  # индиго (1.5.1, выбор владельца): синий сливался с бирюзовым Codex
BLUE = "#5b8def"    # общий цвет окна: кнопка «Да», галочки, выбранный вариант, линия графика, иконка
CODEX = "#22b8cf"   # бирюзовый: зелёный сливался с полосами и процентами (выбор владельца, 1.5.0)
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
FADE_IN_MS = 250  # плавное появление всплывающих окон — как у предупреждения о пороге


def fade_in(win, ms=FADE_IN_MS, alpha=1.0):
    """Плавное появление окна win. Вызывать сразу после создания Toplevel: окно становится прозрачным
    до первой отрисовки, а проявляться начинает, когда построено и размещено."""
    try:
        win.attributes("-alpha", 0.0)
    except tk.TclError:
        return
    steps = max(1, ms // 16)

    def tick(i):
        try:
            if not win.winfo_exists():
                return
            win.attributes("-alpha", alpha * i / steps)
        except tk.TclError:  # окно уже закрыто
            return
        if i < steps:
            win.after(16, tick, i + 1)
    win.after(0, tick, 1)


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
        tk.Label(self.tip, text=self.text, bg="#2a2f3a", fg=FG, font=(FONT, 9),
                 padx=8, pady=4).pack()
        self.tip.update_idletasks()
        top = self.w.winfo_toplevel()  # не выходить за правый край окна, в котором элемент
        x = max(top.winfo_rootx() + 4, min(x, top.winfo_rootx() + top.winfo_width() - self.tip.winfo_reqwidth() - 4))
        self.tip.wm_geometry(f"+{x}+{y}")

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


class ThinScrollbar(tk.Canvas):
    """Тонкая вертикальная полоса прокрутки в стиле окна (1.5.6, владелец): скруглённый ползунок цвета линий,
    светлее при наведении и пока тянут. Видна, только когда содержимое не помещается; лежит поверх правого поля
    окна (place), поэтому карточки не сдвигаются. Ползунок тянется мышью, щелчок по дорожке — на страницу."""
    W = 6
    THUMB, THUMB_HI = "#3a4150", "#566074"
    MIN_THUMB = 24

    def __init__(self, master, target, x=-7, bg=BG):
        super().__init__(master, width=self.W, bg=bg, highlightthickness=0, cursor="arrow")
        self.target, self.x = target, x
        self.first, self.last = 0.0, 1.0
        self.hover = self.drag = False
        self.shown = False
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, first, last):
        """yscrollcommand прокручиваемого Canvas."""
        self.first, self.last = float(first), float(last)
        need = self.last - self.first < 0.999
        if need != self.shown:
            self.shown = need
            if need:
                self.place(relx=1.0, x=self.x, y=2, relheight=1.0, height=-4, anchor="ne")
                tk.Misc.tkraise(self)  # у Canvas lift — это порядок фигур, а не окна
            else:
                self.place_forget()
        if need:
            self.draw()

    def _thumb(self):
        h = self.winfo_height()
        size = max(self.MIN_THUMB, (self.last - self.first) * h)
        top = self.first / max(1e-6, 1 - (self.last - self.first)) * (h - size) if self.last < 1 else h - size
        return max(0.0, top), size, h

    def draw(self):
        self.delete("all")
        if not self.shown or self.winfo_height() < 8:
            return
        top, size, _ = self._thumb()
        rounded(self, 0, top, self.W, top + size, self.W / 2, outline="",
                fill=self.THUMB_HI if self.hover or self.drag else self.THUMB)

    def _hover(self, on):
        self.hover = on
        self.draw()

    def _press(self, e):
        top, size, h = self._thumb()
        if top <= e.y <= top + size:  # за ползунок — тянуть
            self.drag, self._grab = True, e.y - top
            self.draw()
        else:  # по дорожке — на страницу в сторону щелчка
            self.target.yview_scroll(-1 if e.y < top else 1, "pages")

    def _motion(self, e):
        if not self.drag:
            return
        top, size, h = self._thumb()
        room = max(1.0, h - size)
        frac = min(1.0, max(0.0, (e.y - self._grab) / room))
        self.target.yview_moveto(frac * (1 - (self.last - self.first)))

    def _release(self, _e):
        self.drag = False
        self.draw()


class FlatButton(tk.Label):
    def __init__(self, master, text, cmd, bg=CARD_HI, fg=FG, hover="#2a2f3a", **kw):
        super().__init__(master, text=text, bg=bg, fg=fg, cursor="hand2",
                         font=(FONT, 10), padx=12, pady=6, **kw)
        self._bg, self._hover, self.cmd = bg, hover, cmd
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<Button-1>", lambda e: self.cmd())
