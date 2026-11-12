"""Карточки лимитов: создаются один раз, при обновлении меняются только изменившиеся значения."""
import tkinter as tk

from i18n import T
from ui_theme import (
    BG, Bar, CARD, CARD_HI, FAINT, FG, FONT, GREEN, LINE, MUTED, Tooltip, YELLOW, color_for, local_time,
    short_reset)


# ---------------------------------------------------------------- карточки (обновляются на месте)
_UNSET = object()


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
    """Строка лимита: название, время сброса, отсчёт, процент, полоса и (если есть) строка прогноза.
    Создаётся один раз, update() меняет только значения. on_click(виджет) — щелчок по строке (график расхода)."""

    def __init__(self, parent, name, on_click=None):
        self.name = name
        self.small = small = name.startswith("5")  # 5-часовой: только время, мелко и бледно
        self.f = tk.Frame(parent, bg=CARD)
        self.f.pack(fill="x", pady=(9, 0))
        top = tk.Frame(self.f, bg=CARD)
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)  # при нехватке ширины сжимается название, а не процент справа
        tk.Label(top, text=T(name), bg=CARD, fg=FG, font=(FONT, 10), anchor="w").grid(row=0, column=0, sticky="w")
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
        Tooltip(self.nodata, T("Облако сейчас отдаёт только другой лимит.\nЗначение появится, когда он сбросится,\n"
                               "или если войти этим аккаунтом в IDE Antigravity."))
        self.bar = Bar(self.f, 0, FAINT)
        self.bar.pack(fill="x", pady=(4, 0))
        self.fc = tk.Label(self.f, bg=CARD, fg=YELLOW, font=(FONT, 8), anchor="w")  # прогноз: под полосой
        self._fc_on = False
        if on_click:
            for w in (self.f, top, self.bar, *top.winfo_children()):
                w.bind("<Button-1>", lambda e: on_click(self.f), add="+")
                w.config(cursor="hand2")

    def _forecast(self, line):
        """Строка «при таком темпе хватит на …, до …» показывается, только когда лимит кончится раньше сброса.
        line — «хватит на 2 дня 5 часов, до чт 14:00» или None."""
        if line:
            _set(self.fc, text=T("при таком темпе {line}", line=line))
        if bool(line) != self._fc_on:
            self._fc_on = bool(line)
            if line:
                self.fc.pack(fill="x", pady=(2, 0))
            else:
                self.fc.pack_forget()

    def update(self, used, resets_at, seen, warn, line=None):
        self._forecast(line if used is not None else None)
        if used is None:
            for w in (self.pct, self.seen, self.rs, self.time):
                _vis(w, False)
            _vis(self.nodata, True)
            self.bar.set(0, FAINT)
            return
        col = color_for(used, warn)
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
        self._sub_on = self._content_on = False
        self._msg_pady = None
        self.outer = tk.Frame(app.body, bg=BG)
        f = tk.Frame(self.outer, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        f.pack(fill="x")
        tk.Frame(f, bg=accent, width=3).pack(side="left", fill="y")
        inner = tk.Frame(f, bg=CARD)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=14)
        h = tk.Frame(inner, bg=CARD)
        h.pack(fill="x")
        h.columnconfigure(3, weight=1)
        self.arrow = tk.Label(h, text="▾", bg=CARD, fg=MUTED, font=(FONT, 11))
        self.arrow.grid(row=0, column=0, padx=(0, 6))
        self.title = tk.Label(h, text=title, bg=CARD, fg=FG, font=(FONT, 12, "bold"))
        self.title.grid(row=0, column=1)
        for w in (self.arrow, self.title):
            w.bind("<Button-1>", lambda e: self.collapsible and app.toggle(key))
        self.badge = tk.Label(h, bg=CARD_HI, fg=accent, font=(FONT, 8, "bold"), padx=7, pady=1)
        self.badge.grid(row=0, column=2, padx=8)
        self.summary = tk.Label(h, bg=CARD, font=(FONT, 10, "bold"))
        self.summary.grid(row=0, column=4)
        self.ide = tk.Label(h, bg=CARD)
        self.ide.grid(row=0, column=5, padx=(0, 10))
        self.ide.bind("<Button-1>", lambda e: self.ide_mode == "switch" and app.switch_ide(key))
        self.ide.bind("<Enter>", lambda e: self.ide_mode == "switch" and self.ide.config(fg=FG))
        self.ide.bind("<Leave>", lambda e: self.ide_mode == "switch" and self.ide.config(fg=MUTED))
        self.ide_tip = Tooltip(self.ide, "")
        self.sub = tk.Label(inner, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w")
        self.content = tk.Frame(inner, bg=CARD)
        self.msg = tk.Label(self.content, bg=CARD, anchor="w", justify="left", wraplength=380)
        self.rows_box = tk.Frame(self.content, bg=CARD)
        self.rows_box.pack(fill="x")
        for w in (self.arrow, self.badge, self.summary, self.ide):
            _vis(w, False)

    def update(self, spec, warn):
        self.collapsible = spec["collapsible"]
        _vis(self.arrow, self.collapsible)
        _set(self.arrow, text="▸" if spec["folded"] else "▾", cursor="hand2" if self.collapsible else "")
        _set(self.title, cursor="hand2" if self.collapsible else "")
        if spec["badge"]:
            _set(self.badge, text=spec["badge"].upper())
        _vis(self.badge, bool(spec["badge"]))
        if spec["summary"]:
            _set(self.summary, text=spec["summary"][0], fg=spec["summary"][1])
        _vis(self.summary, bool(spec["summary"]))

        mode = spec["ide"]  # None | "current" | "switch"
        if mode != self.ide_mode:
            self.ide_mode = mode
            if mode == "current":
                self.ide.config(text="● IDE", bg=CARD, fg=GREEN, font=(FONT, 9, "bold"), cursor="", padx=1)
                self.ide_tip.text = T("Этот аккаунт сейчас вошёл в IDE Antigravity")
            elif mode == "switch":
                self.ide.config(text=T("→ в IDE"), bg=CARD_HI, fg=MUTED, font=(FONT, 9), cursor="hand2", padx=6)
                self.ide_tip.text = T("Сделать этот аккаунт текущим в IDE Antigravity")
            _vis(self.ide, bool(mode))

        if spec["sub"]:
            _set(self.sub, text=spec["sub"])
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
        for view, (_, used, resets_at, seen, line) in zip(self.rows, spec["rows"]):
            view.update(used, resets_at, seen, warn, line)

        sub_on, content_on = bool(spec["sub"]), bool(msg or names)
        if (sub_on, content_on) != (self._sub_on, self._content_on):
            self._sub_on, self._content_on = sub_on, content_on
            self.sub.pack_forget()
            self.content.pack_forget()
            if sub_on:
                self.sub.pack(fill="x")
            if content_on:
                self.content.pack(fill="x")
