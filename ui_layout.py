"""Расположение карточек: порядок (перетаскивание мышью за цветную полоску слева) и одна или две колонки.
Порядок общий для окна, мини-окна трея, подсказки иконки и списка «Убрать Google-аккаунт» в меню ⚙."""
import time

from ui_theme import LINE, MUTED

DRAG_START = 6     # сдвиг мыши в пикселях, после которого начинается перетаскивание
ANIM_MS = 320      # сколько едет плитка на новое место (как ярлыки в Android/iOS)
FRAME_MS = 15      # шаг анимации
NO_ACCOUNTS = "\0none"  # карточка «Аккаунтов нет» — не перетаскивается и в порядке не хранится


class LayoutMixin:
    """Часть класса App (limits_gui.pyw). Настройки в gui.json: order — порядок ключей карточек
    ("claude" и email аккаунтов), two_columns — карточки в две колонки."""

    def ordered(self, keys):
        """Ключи в сохранённом порядке; неизвестные (новый аккаунт) — в конце, в прежнем порядке."""
        pos = {k: i for i, k in enumerate(self.s.get("order", []))}
        return sorted(keys, key=lambda k: (k not in pos, pos.get(k, 0)))

    def columns(self):
        return 2 if self.s.get("two_columns") else 1

    def layout_cards(self):
        """Раскладывает карточки по self.card_order в одну или две колонки."""
        if getattr(self, "_dnd", None):  # идёт перетаскивание — сетку вернёт его окончание
            return
        cols = self.columns()
        for c in (0, 1):
            self.body.columnconfigure(c, weight=1 if c < cols else 0, uniform="cards" if c < cols else "")
        for i, k in enumerate(self.card_order):
            col = i % cols
            padx = (20, 20) if cols == 1 else ((20, 6) if col == 0 else (6, 20))
            self.cards[k].outer.grid(row=i // cols, column=col, sticky="nsew", padx=padx, pady=6)

    def toggle_two_columns(self):
        """Галочка «Карточки в две колонки»: окно расширяется (или сужается) под новое число колонок."""
        two = not self.s.get("two_columns")
        self.s["two_columns"] = two
        k = self.root.winfo_fpixels("1i") / 96
        w = self.root.winfo_width()
        w = round(2 * w - 40 * k) if two else round((w + 40 * k) / 2)
        w = max(440, min(w, self.root.winfo_screenwidth() - 40))
        self.apply_minsize()
        self.layout_cards()
        self.fit_height(width=w)
        self.persist()

    # ------------------------------------------------ перетаскивание
    # Пока плитку тащат, все плитки размещаются place() по координатам: перетаскиваемая
    # едет за мышью поверх остальных, остальные плавно (ANIM_MS) съезжают на свои новые места. После отпускания
    # плитка доезжает до своего места, и раскладка возвращается в сетку (layout_cards).
    def bind_drag(self, card, handle):
        """Ручка перетаскивания — цветная полоска карточки."""
        handle.bind("<ButtonPress-1>", lambda e, c=card: self._drag_press(e, c))
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_release)

    def _drag_press(self, e, card):
        if getattr(self, "_dnd", None):  # прошлая плитка ещё доезжает
            return
        self._drag = {"card": card, "x": e.x_root, "y": e.y_root, "on": False}

    def _slots(self, order):
        """Места плиток при порядке order — как их расставит сетка: {ключ: (x, y, ширина, высота)} внутри body."""
        cols, bw = self.columns(), self.body.winfo_width()
        out, y = {}, 0
        for r in range(0, len(order), cols):
            row = order[r:r + cols]
            h = max(self.cards[k].outer.winfo_reqheight() for k in row)
            for c, k in enumerate(row):
                if cols == 1:
                    out[k] = (20, y + 6, bw - 40, h)
                else:
                    half = bw / 2
                    out[k] = (round(20 if c == 0 else half + 6), y + 6, round(half - 26), h)
            y += h + 12
        return out

    def _drag_start(self, card, e):
        d = self._drag
        d["on"] = True
        self.close_menu()
        self.cv.itemconfig(self.body_id, height=self.body.winfo_height())  # высота body не меняется, пока тащат
        self._dnd = {"anim": {}, "pos": {}, "drop": False}
        widgets = [(k, self.cards[k].outer) for k in self.card_order]
        geo = {k: (w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height()) for k, w in widgets}
        for k, w in widgets:
            x, y, ww, hh = geo[k]
            w.grid_forget()
            w.place(x=x, y=y, width=ww, height=hh)
            self._dnd["pos"][k] = (x, y)
        card.outer.lift()
        d["dx"], d["dy"] = d["x"] - card.outer.winfo_rootx(), d["y"] - card.outer.winfo_rooty()
        card.frame.config(highlightbackground=MUTED)  # перетаскиваемая плитка — светлой рамкой
        card.strip_hover(True)
        self.root.config(cursor="fleur")
        self._slot = self._slots(self.card_order)
        self._tick()

    def _drag_motion(self, e):
        d = getattr(self, "_drag", None)
        if not d:
            return
        card = d["card"]
        if not d["on"]:
            if max(abs(e.x_root - d["x"]), abs(e.y_root - d["y"])) < DRAG_START:
                return
            if card.key == NO_ACCOUNTS or len(self.card_order) < 2 or card.key not in self.card_order:
                return
            self._drag_start(card, e)
        bx, by = self.body.winfo_rootx(), self.body.winfo_rooty()
        x, y = e.x_root - bx - d["dx"], e.y_root - by - d["dy"]
        self._dnd["anim"].pop(card.key, None)
        self._dnd["pos"][card.key] = (x, y)
        card.outer.place_configure(x=x, y=y)
        new = self.drop_order(card.key, e.x_root - bx, e.y_root - by)
        if new != self.card_order:
            self.card_order = new
            self._retarget(skip=card.key)

    def drop_order(self, key, px, py):
        """Порядок плиток, если отпустить плитку key в точке (px, py) внутри body (места — из self._slot)."""
        cols = self.columns()
        others = [k for k in self.card_order if k != key]
        before = 0
        for k in others:
            x0, y0, w, h = self._slot[k]
            x1, y1 = x0 + w, y0 + h
            if cols == 1:
                before += py > (y0 + y1) / 2
            else:  # по строкам сетки: строка выше целиком, в той же строке — по середине плитки
                before += py > y1 or (y0 <= py <= y1 and px > (x0 + x1) / 2)
        return others[:before] + [key] + others[before:]

    def _retarget(self, skip=None):
        """Новые места плиток после смены порядка: каждая плавно едет со своего нынешнего места."""
        self._slot = self._slots(self.card_order)
        now = time.time()
        for k, (x, y, w, h) in self._slot.items():
            if k == skip:
                continue
            self.cards[k].outer.place_configure(width=w, height=h)
            x0, y0 = self._dnd["pos"][k]
            cur = self._dnd["anim"].get(k)
            if (x0, y0) != (x, y) and (not cur or cur[2:4] != (x, y)):
                self._dnd["anim"][k] = (x0, y0, x, y, now)

    def _tick(self):
        dnd = getattr(self, "_dnd", None)
        if not dnd:
            return
        now = time.time()
        for k, (x0, y0, x1, y1, t0) in list(dnd["anim"].items()):
            t = min(1.0, (now - t0) * 1000 / ANIM_MS)
            ease = 1 - (1 - t) ** 3  # быстро трогается и мягко останавливается
            x, y = x0 + (x1 - x0) * ease, y0 + (y1 - y0) * ease
            dnd["pos"][k] = (x, y)
            self.cards[k].outer.place_configure(x=round(x), y=round(y))
            if t >= 1:
                del dnd["anim"][k]
        if dnd["drop"] and not dnd["anim"]:
            return self._drag_finish()
        self.root.after(FRAME_MS, self._tick)

    def _drag_release(self, e):
        d, self._drag = getattr(self, "_drag", None), None
        if not d or not d["on"]:
            return
        self.root.config(cursor="")
        card = d["card"]
        x, y, w, h = self._slot[card.key]
        card.outer.place_configure(width=w, height=h)
        x0, y0 = self._dnd["pos"][card.key]
        if (x0, y0) != (x, y):
            self._dnd["anim"][card.key] = (x0, y0, x, y, time.time())  # плитка доезжает до своего места
        self._dnd["drop"] = True
        self._dnd["card"] = card

    def _drag_finish(self):
        card = self._dnd["card"]
        self._dnd = None
        for k in self.card_order:
            self.cards[k].outer.place_forget()
        self.layout_cards()
        self.cv.itemconfig(self.body_id, height=0)  # высота body снова по содержимому
        card.frame.config(highlightbackground=LINE)
        card.strip_hover(False)
        self.s["order"] = [k for k in self.card_order if k != NO_ACCOUNTS]
        self.persist()
        if getattr(self, "popup", None):
            self.show_popup()
        if self.data:
            self.update_tray_tip(self.data)
