"""История лимитов в окне: запись при обновлении, прогноз, окно с графиком расхода."""
import datetime as dt
import time
import tkinter as tk

import history as H
import limits as L
from i18n import T, day
from ui_theme import CARD, CARD_HI, FAINT, FG, FONT, GOOGLE, GREEN, LINE, MUTED, YELLOW, color_for


class HistoryMixin:
    """Часть класса App (limits_gui.pyw): история и прогноз. Пользуется полями и методами App через self."""

    def update_history(self):
        """После полного обновления: дописать значения в историю и пересчитать прогнозы (self.fc)."""
        try:
            ag = [(e, self.ag_res.get(e)) for e in self.ag_order]
            H.record(self.claude_res, ag)
            self.fc = H.forecasts(self.claude_res, ag)
        except Exception as e:  # история — вспомогательная: её сбой не должен мешать показу лимитов
            self.fc = {}
            L.log_exception("история лимитов", type(e), e, e.__traceback__)

    def fc_line(self, key, window):
        """«хватит на 2 дня 5 часов, до чт 14:00», если по прогнозу лимит кончится раньше сброса; иначе None."""
        fc = getattr(self, "fc", {}).get((key.lower(), window))
        return fc["line"] if fc else None

    ALERT_GAP = 3600     # предупреждение по прогнозу об одном лимите — не чаще раза в час
    ALERT_SHIFT = 1800   # …и только если расчётное время исчерпания сдвинулось хотя бы на полчаса

    def _weekly_soon(self):
        """Недельные лимиты, которые по прогнозу кончатся раньше сброса: [(ключ, окно, прогноз)], ближайшие первыми."""
        return sorted(((k, w, fc) for (k, w), fc in getattr(self, "fc", {}).items()
                       if fc["before_reset"] and w.lower().startswith("нед")), key=lambda x: x[2]["eta"])

    @staticmethod
    def _who(key):
        return "Claude" if key == "claude" else key.split("@")[0]

    def forecast_soon(self):
        """Для мини-окна трея: [(чей лимит, «хватит на …, до …»)] — только недельные лимиты."""
        return [(self._who(k), fc["line"]) for k, _, fc in self._weekly_soon()]

    def forecast_alerts(self):
        """Всплывающие предупреждения по прогнозу: [(чей лимит, «чт 14:00»)]. Включаются галочкой в меню ⚙
        (по умолчанию выключены); об одном лимите — не чаще раза в час и только при изменившемся расчёте."""
        if not self.s.get("forecast_alerts"):
            return []
        state = self.__dict__.setdefault("fc_alert_state", {})  # {(ключ, окно): (когда предупредили, расчёт)}
        now, new = time.time(), []
        for k, w, fc in self._weekly_soon():
            last = state.get((k, w))
            if last and (now - last[0] < self.ALERT_GAP or abs(fc["eta"] - last[1]) < self.ALERT_SHIFT):
                continue
            state[(k, w)] = (now, fc["eta"])
            new.append((self._who(k), fc["when"]))
        return new

    def show_history(self, key, window, anchor):
        """Окно с графиком расхода лимита (щелчок по строке лимита): 7 дней для недельного, сутки для 5-часового.
        Закрывается по Esc и щелчку мимо — как окно подтверждения."""
        self.close_confirm()
        self.close_menu()
        week = window.lower().startswith("нед")
        span = 7 * 86400 if week else 86400
        now = time.time()
        pts = H.series(key, window, now - span)
        fc = getattr(self, "fc", {}).get((key.lower(), window))

        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=LINE)
        self.confirm_win = p
        k = self.root.winfo_fpixels("1i") / 96  # масштаб экрана
        box = tk.Frame(p, bg=CARD, padx=16, pady=14)
        box.pack(padx=1, pady=1)
        tk.Label(box, text=("Claude Code" if key == "claude" else key) + "  ·  " + T(window), bg=CARD, fg=FG,
                 font=(FONT, 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(box, text=T("Расход за 7 дней") if week else T("Расход за сутки"), bg=CARD, fg=MUTED,
                 font=(FONT, 9), anchor="w").pack(fill="x", pady=(2, 8))

        w, h = round(340 * k), round(150 * k)
        left, bottom, top = round(34 * k), round(18 * k), round(6 * k)
        cv = tk.Canvas(box, width=w, height=h, bg=CARD, highlightthickness=0)
        cv.pack()

        def x(ts):
            return left + (ts - (now - span)) / span * (w - left - 4)

        def y(used):
            return top + (100 - max(0, min(100, used))) / 100 * (h - top - bottom)

        for v in (0, 50, 100):
            cv.create_line(left, y(v), w - 4, y(v), fill=LINE)
            cv.create_text(left - 6, y(v), text=f"{v}%", fill=FAINT, font=(FONT, 8), anchor="e")
        # подписи по времени: полночь каждого дня либо каждые 6 часов
        t = dt.datetime.fromtimestamp(now - span).replace(minute=0, second=0, microsecond=0)
        step = dt.timedelta(days=1) if week else dt.timedelta(hours=6)
        t = t.replace(hour=0) + dt.timedelta(days=1) if week else t + dt.timedelta(hours=6 - t.hour % 6)
        while t.timestamp() < now:
            cv.create_line(x(t.timestamp()), top, x(t.timestamp()), h - bottom, fill=CARD_HI)
            cv.create_text(x(t.timestamp()), h - bottom + 3, anchor="n", fill=FAINT, font=(FONT, 8),
                           text=day(t.weekday()) if week else f"{t:%H}:00")
            t += step
        if len(pts) > 1:
            cv.create_line([c for ts, used in pts for c in (x(ts), y(used))], fill=GOOGLE, width=max(2, round(2 * k)),
                           joinstyle="round")
        if pts:
            ts, used = pts[-1]
            r = max(3, round(3 * k))
            cv.create_oval(x(ts) - r, y(used) - r, x(ts) + r, y(used) + r, fill=color_for(used, self.warn), outline="")
        else:
            cv.create_text((left + w) / 2, (top + h - bottom) / 2, fill=FAINT, font=(FONT, 9),
                           text=T("Истории пока нет — она копится при каждом обновлении"))

        if fc and fc["before_reset"]:
            text, col = T("При таком темпе {line} — раньше сброса ({reset}).", line=fc["line"],
                          reset=H.when_text(fc["reset"])), YELLOW
        elif fc:
            text, col = T("При таком темпе лимита хватит до сброса."), GREEN
        else:
            text, col = T("Прогноза нет: мало данных или расход не растёт."), MUTED
        tk.Label(box, text=text, bg=CARD, fg=col, font=(FONT, 9), anchor="w", justify="left",
                 wraplength=w).pack(fill="x", pady=(8, 0))

        p.update_idletasks()
        pw, ph = p.winfo_reqwidth(), p.winfo_reqheight()
        ax, ay = anchor.winfo_rootx(), anchor.winfo_rooty()
        l, t_, r_, b = self._work_area(ax, ay)
        px = ax + (anchor.winfo_width() - pw) // 2
        py = ay + anchor.winfo_height() + 6
        if py + ph > b - 8:
            py = ay - ph - 6
        p.geometry(f"+{max(l + 8, min(px, r_ - pw - 8))}+{max(t_ + 8, min(py, b - ph - 8))}")
        p.bind("<Escape>", self.close_confirm)
        p.bind("<Button-1>", self.close_confirm)
        p.focus_force()
        p.bind("<FocusOut>", lambda e: self.root.after(120, self._confirm_focus_check))
