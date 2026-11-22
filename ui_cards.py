"""Карточки лимитов: создаются один раз, при обновлении меняются только изменившиеся значения."""
import tkinter as tk
import tkinter.font as tkfont

from i18n import T
from ui_theme import (
    BG, Bar, CARD, CARD_HI, FAINT, FG, FONT, GREEN, LINE, MUTED, Tooltip, YELLOW, color_for, local_time,
    short_reset)


# ---------------------------------------------------------------- карточки (обновляются на месте)
_UNSET = object()


def lighter(color, k=0.4):
    """Цвет #rrggbb, смешанный с белым на долю k."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(v + (255 - v) * k) for v in (r, g, b))


def mix(color, other, k):
    """Цвет #rrggbb, смешанный с other на долю k."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * k) for x, y in zip(a, b))


# плитка аккаунта, который сейчас не вошёл ни в одну программу (1.5.4, владелец): полоса и белые надписи тусклее
DIM_STRIP = 0.55   # доля цвета фона в полосе
DIM_TEXT = 0.35    # доля цвета фона в надписях
DIM_COLOR = 0.5    # доля цвета фона в процентах, полосах лимитов и значке тарифа


def _set(w, **kw):
    """config только для изменившихся параметров: неизменённый виджет не перерисовывается."""
    st = w.__dict__.setdefault("_st", {})
    ch = {k: v for k, v in kw.items() if st.get(k, _UNSET) != v}
    if ch:
        w.config(**ch)
        st.update(ch)


def _vis(w, on):
    """Показать/спрятать виджет, размещённый через grid (место в сетке за ним сохраняется)."""
    if getattr(w, "_on", True) != on:
        w._on = on
        (w.grid if on else w.grid_remove)()


class RowView:
    """Строка лимита: название, время сброса, отсчёт, процент и полоса.
    Создаётся один раз, update() меняет только значения. on_click(виджет) — щелчок по строке (график расхода)."""

    def __init__(self, parent, name, on_click=None):
        self.name = name
        self.small = small = name.startswith("5")  # 5-часовой: только время, мелко и бледно
        self.f = tk.Frame(parent, bg=CARD)
        self.f.pack(fill="x", pady=(9, 0))
        top = tk.Frame(self.f, bg=CARD)
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)  # при нехватке ширины сжимается название, а не процент справа
        self.label = tk.Label(top, text=T(name), bg=CARD, fg=FG, font=(FONT, 10), anchor="w")
        self.label.grid(row=0, column=0, sticky="w")
        self.time = tk.Label(top, bg=CARD, fg=FAINT if small else "#d3d7df", font=(FONT, 8 if small else 9))
        self.time.grid(row=0, column=2, padx=(0, 8 if small else 10))
        self.rs = tk.Label(top, bg=CARD, fg=FAINT if small else "#b4bac6", font=(FONT, 8 if small else 9))
        self.rs.grid(row=0, column=3, padx=(0, 4 if small else 6))
        self.seen = tk.Label(top, text="≈", bg=CARD, fg=YELLOW, font=(FONT, 10, "bold"))
        self.seen.grid(row=0, column=4)
        self.seen_tip = Tooltip(self.seen, "")
        self.pct = tk.Label(top, bg=CARD, font=(FONT, 10, "bold"), width=5, anchor="e")
        self.pct.grid(row=0, column=5)
        self.nodata = tk.Label(top, text=T("нет данных"), bg=CARD, fg=FAINT, font=(FONT, 9, "italic"))
        self.nodata.grid(row=0, column=5, sticky="e")
        self.nodata_tip = Tooltip(self.nodata, "")
        self.retranslate()
        self.bar = Bar(self.f, 0, FAINT)
        self.bar.pack(fill="x", pady=(4, 0))
        if on_click:
            for w in (self.f, top, self.bar, *top.winfo_children()):
                w.bind("<Button-1>", lambda e: on_click(self.f), add="+")
                w.config(cursor="hand2")

    def retranslate(self):
        """Надписи строки — на текущем языке (смена языка без пересоздания, 1.5.6)."""
        _set(self.label, text=T(self.name))
        _set(self.nodata, text=T("нет данных"))
        self.nodata_tip.text = T("Облако сейчас отдаёт только другой лимит.\nЗначение появится, когда он сбросится,\n"
                                 "или если войти этим аккаунтом в IDE Antigravity.")

    def update(self, used, resets_at, seen, warn, dim=False, quiet=False):
        """dim — аккаунт отключён (Google просит подтвердить его): процент и полоса приглушены.
        quiet — аккаунт не вошёл ни в одну программу: название строки и время сброса тусклее."""
        fade = (lambda c: mix(c, CARD, DIM_TEXT)) if quiet else (lambda c: c)
        _set(self.label, fg=fade(FG))
        if not self.small:
            _set(self.time, fg=fade("#d3d7df"))
            _set(self.rs, fg=fade("#b4bac6"))
        if used is None:
            for w in (self.pct, self.seen, self.rs, self.time):
                _vis(w, False)
            _vis(self.nodata, True)
            self.bar.set(0, FAINT)
            return
        col = FAINT if dim else color_for(used, warn)
        if quiet and not dim:
            col = mix(col, CARD, DIM_COLOR)
        _vis(self.nodata, False)
        _set(self.pct, text=f"{used:.0f}%", fg=col)
        _vis(self.pct, True)
        self.seen_tip.text = (T("Сохранённое значение от {seen}.\nСейчас облако отдаёт другой лимит.", seen=seen)
                              if seen else "")
        _vis(self.seen, bool(seen))
        rs = short_reset(resets_at)
        if rs:
            _set(self.rs, text=f"↻ {rs}")
            _set(self.time, text=local_time(resets_at)[-5:] if self.small else local_time(resets_at))
        _vis(self.rs, bool(rs))
        _vis(self.time, bool(rs))
        self.bar.set(used, col)


class CardView:
    """Карточка (Claude Code или Google-аккаунт). Рамка, заголовок и строки создаются один раз;
    update(spec) меняет только то, что изменилось в данных."""

    def __init__(self, app, key, title, accent):
        self.app, self.key = app, key
        self.rows, self.collapsible, self.ide_mode = [], False, None
        self._content_on = False
        self._msg_pady = None
        self.outer = tk.Frame(app.body, bg=BG)
        self.frame = f = tk.Frame(self.outer, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        f.pack(fill="both", expand=True)  # в две колонки карточки одной строки — одной высоты
        # цветная полоска слева — ручка перетаскивания: при наведении светлеет, курсор «переместить»
        self.accent, self.quiet = accent, False
        self.strip = tk.Frame(f, bg=accent, width=12, cursor="fleur")
        self.strip.pack(side="left", fill="y")
        self.strip.bind("<Enter>", lambda e: self.strip_hover(True))
        self.strip.bind("<Leave>", lambda e: self.strip_hover(False))
        app.bind_drag(self, self.strip)
        inner = tk.Frame(f, bg=CARD)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=14)
        h = tk.Frame(inner, bg=CARD)
        h.pack(fill="x")
        h.columnconfigure(3, weight=1)
        self.head = h
        h.bind("<Configure>", lambda e: self.fit_title())
        # стрелка сворачивания — заметная, светлеет при наведении; щелчок по названию плитку не сворачивает
        # крупный треугольник ▼/▶ мелким шрифтом: стрелка заметнее, а высота строки — как у названия;
        # кнопка шире (padx), а не выше
        self.arrow = tk.Label(h, text="▼", bg=CARD, fg="#aab0bc", font=(FONT, 9), padx=7, pady=0)
        self.arrow.grid(row=0, column=0, padx=(0, 6))
        self.arrow.bind("<Enter>", lambda e: self.collapsible and self.arrow.config(fg=FG, bg=CARD_HI))
        self.arrow.bind("<Leave>", lambda e: self.arrow.config(fg="#aab0bc", bg=CARD))
        self.full_title = title
        self.title = tk.Label(h, text=title, bg=CARD, fg=FG, font=(FONT, 12, "bold"))
        self.title.grid(row=0, column=1)
        self.badge = tk.Label(h, bg=CARD_HI, fg=accent, font=(FONT, 8, "bold"), padx=7, pady=1)
        self.badge.grid(row=0, column=2, padx=8)
        self.badge_tip = Tooltip(self.badge, "")
        self.summary = tk.Label(h, bg=CARD, font=(FONT, 10, "bold"))
        self.summary.grid(row=0, column=4, padx=(0, 8))
        self.ide = tk.Label(h, bg=CARD)
        self.ide.grid(row=0, column=5, padx=(0, 10))
        sw = lambda: (self.ide_mode or "").startswith("switch")  # noqa: E731
        self.ide.bind("<Button-1>", lambda e: sw() and app.switch_ide(key))
        self.ide.bind("<Enter>", lambda e: sw() and self.ide.config(fg=FG))
        self.ide.bind("<Leave>", lambda e: sw() and self.ide.config(fg=MUTED))
        self.ide_tip = Tooltip(self.ide, "")
        self.arrow.bind("<Button-1>", lambda e: self.collapsible and app.toggle(key))
        self.title.bind("<Double-Button-1>", lambda e: app.begin_rename(key))  # переименовать прямо в плитке
        self.content = tk.Frame(inner, bg=CARD)
        self.msg = tk.Label(self.content, bg=CARD, anchor="w", justify="left", wraplength=380)
        self.rows_box = tk.Frame(self.content, bg=CARD)
        self.rows_box.pack(fill="x")
        for w in (self.arrow, self.badge, self.summary, self.ide):
            _vis(w, False)

    def fit_title(self):
        """Длинный email в заголовке укорачивается «…», чтобы значок, остаток и «→ в IDE» не обрезались."""
        width = self.head.winfo_width()
        if width <= 1:
            return
        pads = {self.arrow: 6, self.badge: 16, self.summary: 8, self.ide: 10}
        room = width - sum(w.winfo_reqwidth() + pad for w, pad in pads.items() if getattr(w, "_on", True)) - 8
        font = tkfont.Font(font=self.title.cget("font"))
        text = self.full_title
        if font.measure(text) > room:
            while len(text) > 4 and font.measure(text + "…") > room:
                text = text[:-1]
            text += "…"
        _set(self.title, text=text)

    def strip_color(self):
        """Цвет полосы: у плитки аккаунта не в программе — приглушённый."""
        return mix(self.accent, CARD, DIM_STRIP) if getattr(self, "quiet", False) else self.accent

    def strip_hover(self, on):
        """Подсветка полоски: светлее при наведении и пока плитку тащат."""
        drag = getattr(self.app, "_drag", None) or getattr(self.app, "_dnd", None) or {}
        base = self.strip_color()
        self.strip.config(bg=lighter(base) if on or drag.get("card") is self else base)

    def retranslate(self):
        """Смена языка (1.5.6): строки лимитов меняют текст на месте; метку и кнопку «→ в …» следующий update
        перепишет заново (ide_mode сброшен). Остальные надписи приходят в spec при render."""
        for r in self.rows:
            r.retranslate()
        self.ide_mode = False  # не None и не строка

    def update(self, spec, warn):
        self.collapsible = spec["collapsible"]
        quiet = spec.get("quiet", False)
        if quiet != getattr(self, "quiet", False):
            self.quiet = quiet
            self.strip.config(bg=self.strip_color())
        _set(self.title, fg=mix(FG, CARD, DIM_TEXT) if quiet else FG)
        _vis(self.arrow, self.collapsible)
        _set(self.arrow, text="▶" if spec["folded"] else "▼", cursor="hand2" if self.collapsible else "",
             font=(FONT, 10 if spec["folded"] else 9))  # ▶ в этом шрифте мельче ▼ — на пункт крупнее
        if spec.get("title") and spec["title"] != self.full_title:  # имя аккаунта сменилось
            self.full_title = spec["title"]
            self.fit_title()
        if spec["badge"]:
            # значок тарифа у тусклой плитки тоже тусклый; LOGOUT (свой цвет) — всегда яркий
            _set(self.badge, text=spec["badge"].upper(), fg=spec.get("badge_fg") or (
                mix(self.accent, CARD, DIM_COLOR) if quiet else self.accent))
        self.badge_tip.text = spec.get("badge_tip") or ""
        _vis(self.badge, bool(spec["badge"]))
        if spec["summary"]:
            _set(self.summary, text=spec["summary"][0],
                 fg=mix(spec["summary"][1], CARD, DIM_COLOR) if quiet else spec["summary"][1])
        _vis(self.summary, bool(spec["summary"]))

        mode = spec["ide"]  # None | "current" | "switch"; "_codex" / "_claude" — программа Codex / Claude Code
        if mode != self.ide_mode:
            self.ide_mode = mode
            prog = (mode or "").partition("_")[2]
            if mode and mode.startswith("current"):
                # «● Codex» / «● Claude Code» (1.5.4, владелец: рядом с «→ в Codex» надпись «IDE» путала)
                self.ide.config(text={"codex": "● Codex", "claude": "● Claude Code"}.get(prog, "● IDE"),
                                bg=CARD, fg=GREEN, font=(FONT, 9, "bold"), cursor="", padx=1)
                self.ide_tip.text = {"codex": T("Этот аккаунт сейчас вошёл в Codex"),
                                     "claude": T("Этот аккаунт сейчас вошёл в Claude Code")}.get(
                                         prog, T("Этот аккаунт сейчас вошёл в IDE Antigravity"))
            elif mode:  # кнопки смены аккаунта программы — одного вида у всех сервисов (решение владельца)
                self.ide.config(text={"codex": T("→ в Codex"), "claude": T("→ в Claude")}.get(prog, T("→ в IDE")),
                                bg=CARD_HI, fg=MUTED, font=(FONT, 9), cursor="hand2", padx=6)
                self.ide_tip.text = {"codex": T("Сделать этот аккаунт текущим в Codex"),
                                     "claude": T("Сделать этот аккаунт текущим в Claude Code")}.get(
                                         prog, T("Сделать этот аккаунт текущим в IDE Antigravity"))
            _vis(self.ide, bool(mode))

        msg = spec["msg"]  # (текст, цвет, шрифт, отступы) или None
        if msg:
            _set(self.msg, text=msg[0], fg=msg[1], font=msg[2])
        if (msg[3] if msg else None) != self._msg_pady:
            self._msg_pady = msg[3] if msg else None
            self.msg.pack_forget()
            if msg:
                self.msg.pack(fill="x", pady=msg[3], before=self.rows_box)

        names = [r[0] for r in spec["rows"]]
        if names != [r.name for r in self.rows]:  # состав строк изменился (сворачивание, новые окна лимитов)
            for r in self.rows:
                r.f.destroy()
            self.rows = [RowView(self.rows_box, n, lambda w, n=n: self.app.show_history(self.key, n, w))
                         for n in names]
            if not names:
                self.rows_box.config(height=1)  # пустая рамка не держит прежнюю высоту
        for view, (_, used, resets_at, seen) in zip(self.rows, spec["rows"]):
            view.update(used, resets_at, seen, warn, spec.get("dim", False), quiet)

        content_on = bool(msg or names)
        if content_on != self._content_on:
            self._content_on = content_on
            if content_on:
                self.content.pack(fill="x")
            else:
                self.content.pack_forget()
        self.head.after_idle(self.fit_title)
