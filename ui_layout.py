"""Расположение карточек: порядок (перетаскивание мышью за заголовок карточки) и одна или две колонки.
Порядок общий для окна, мини-окна трея, подсказки иконки и списка «Убрать Google-аккаунт» в меню ⚙."""
from ui_theme import LINE, MUTED

DRAG_START = 6     # сдвиг мыши в пикселях, после которого щелчок по заголовку становится перетаскиванием
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
        """Раскладывает карточки по self.card_order в одну или две колонки; строка «Максимум» — под ними."""
        cols = self.columns()
        for c in (0, 1):
            self.body.columnconfigure(c, weight=1 if c < cols else 0, uniform="cards" if c < cols else "")
        for i, k in enumerate(self.card_order):
            col = i % cols
            padx = (20, 20) if cols == 1 else ((20, 6) if col == 0 else (6, 20))
            self.cards[k].outer.grid(row=i // cols, column=col, sticky="nsew", padx=padx, pady=6)
        if self.footer is not None:
            if self._footer_on:
                self.footer.grid(row=(len(self.card_order) + cols - 1) // cols, column=0, columnspan=cols,
                                 sticky="we", padx=22, pady=(8, 4))
            else:
                self.footer.grid_forget()

    def toggle_two_columns(self):
        """Галочка «Карточки в две колонки»: окно расширяется (или сужается) под новое число колонок."""
        two = not self.s.get("two_columns")
        self.s["two_columns"] = two
        k = self.root.winfo_fpixels("1i") / 96
        w = self.root.winfo_width()
        w = round(2 * w - 40 * k) if two else round((w + 40 * k) / 2)
        w = max(440, min(w, self.root.winfo_screenwidth() - 40))
        self.layout_cards()
        self.fit_height(width=w)
        self.persist()

    # ------------------------------------------------ перетаскивание
    def bind_drag(self, card, widgets, click=None):
        """Заголовок карточки — ручка перетаскивания. click() — обычный щелчок (без сдвига мыши)."""
        for w in widgets:
            w.bind("<ButtonPress-1>", lambda e, c=card: self._drag_press(e, c, click), add="+")
            w.bind("<B1-Motion>", self._drag_motion, add="+")
            w.bind("<ButtonRelease-1>", self._drag_release, add="+")

    def _drag_press(self, e, card, click):
        self._drag = {"card": card, "x": e.x_root, "y": e.y_root, "on": False, "click": click}

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
            d["on"] = True
            card.frame.config(highlightbackground=MUTED)  # перетаскиваемая карточка — светлой рамкой
            self.root.config(cursor="fleur")
        new = self.drop_order(card.key, e.x_root, e.y_root)
        if new != self.card_order:
            self.card_order = new
            self.layout_cards()

    def drop_order(self, key, px, py):
        """Порядок карточек, если отпустить карточку key в точке экрана (px, py)."""
        cols = self.columns()
        others = [k for k in self.card_order if k != key]
        before = 0
        for k in others:
            w = self.cards[k].outer
            x0, y0 = w.winfo_rootx(), w.winfo_rooty()
            x1, y1 = x0 + w.winfo_width(), y0 + w.winfo_height()
            if cols == 1:
                before += py > (y0 + y1) / 2
            else:  # по строкам сетки: строка выше целиком, в той же строке — по середине карточки
                before += py > y1 or (y0 <= py <= y1 and px > (x0 + x1) / 2)
        return others[:before] + [key] + others[before:]

    def _drag_release(self, e):
        d, self._drag = getattr(self, "_drag", None), None
        if not d:
            return
        if d["on"]:
            d["card"].frame.config(highlightbackground=LINE)
            self.root.config(cursor="")
            self.s["order"] = [k for k in self.card_order if k != NO_ACCOUNTS]
            self.persist()
            if getattr(self, "popup", None):
                self.show_popup()
            if self.data:
                self.update_tray_tip(*self.data)
        elif d["click"] and max(abs(e.x_root - d["x"]), abs(e.y_root - d["y"])) < DRAG_START:
            d["click"]()
