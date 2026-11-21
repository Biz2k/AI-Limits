"""Аккаунты в окне (1.5.0): плитки программ и добавленных аккаунтов, имена, добавление аккаунтов,
окно «Управление аккаунтами» и переименование прямо в плитке.

Добавленный аккаунт всегда показывается своей плиткой (ключ — ключ аккаунта); если программа вошла в него,
у плитки метка «● IDE». Плитка программы (ключ "claude", "codex", "antigravity") — только для аккаунта программы,
которого нет среди добавленных: без имени — с названием программы. Имена: s["names"] = {ключ: имя}.
"""
import threading
import time
import tkinter as tk

import accounts as A
import claude_switch as CL
import codex_switch as CX
import history as H
import limits as L
from i18n import T
from ui_theme import (
    BLUE, CARD, CARD_HI, CLAUDE, CODEX, FAINT, FG, FONT, GOOGLE, GREEN, LINE, MUTED, RED, YELLOW, Tooltip)

ACCENT = {"claude": CLAUDE, "chatgpt": CODEX, "google": GOOGLE}
GROUP = {"claude": "Claude", "chatgpt": "ChatGPT", "google": "Google"}


class AccountsMixin:
    """Часть класса App (limits_gui.pyw)."""

    # ------------------------------------------------ имена
    def names(self):
        return self.s.setdefault("names", {})

    def taken_names(self, except_ident=None):
        return [n for i, n in self.names().items() if i != except_ident]

    def set_name(self, ident, name):
        """Новое имя аккаунта. Возвращает текст ошибки (дубликат, пустое) или None."""
        err = A.name_error(name, self.taken_names(ident))
        if err:
            return err
        self.names()[ident] = " ".join(name.split())
        self.persist()
        self._last_sig = None
        if getattr(self, "parts", None) is not None:
            self.redraw()
            self.update_tray_tip(self.data)
        return None

    # ------------------------------------------------ данные прежних версий (один раз)
    def migrate_accounts(self):
        """Переход на 1.5.0: имена добавленных Google-аккаунтов, ключи плиток в нижнем регистре, плитка программы
        Antigravity в сохранённом порядке, история Claude/Codex — под ключами их аккаунтов."""
        if self.s.get("accounts_v", 0) >= 2:
            return
        names = self.names()
        for a in L.load_accounts():
            key = a["email"].lower()
            if key not in names:
                names[key] = A.suggest_name("google", a["email"], list(names.values()))
        low = lambda k: k.lower() if "@" in k else k  # noqa: E731
        order = [low(k) for k in self.s.get("order", [])]
        if order and "antigravity" not in order:
            first = next((i for i, k in enumerate(order) if "@" in k), len(order))
            order.insert(first, "antigravity")
        if order:
            self.s["order"] = order
        self.collapsed = {low(k) for k in self.collapsed}
        for old, kind, email in (("claude", "claude", A.claude_ide_email()), ("codex", "chatgpt", A.codex_ide_email())):
            if email:
                try:
                    H.rename_key(old, A.ident(kind, email))
                except Exception as e:  # история — вспомогательная
                    L.log_exception("перенос истории", type(e), e, e.__traceback__)
        self.s["accounts_v"] = 2
        self.persist()

    # ------------------------------------------------ что загружать
    def plan_jobs(self):
        """Аккаунты программ и задания загрузки: {часть: (функция, аргументы…)}."""
        self.g_accs = L.load_accounts()
        self.profiles = A.load_profiles()
        self.has_prog = {"claude": L.claude_installed(), "chatgpt": L.codex_installed()}
        self.ide_email = {"claude": A.claude_ide_email() if self.has_prog["claude"] else None,
                          "chatgpt": A.codex_ide_email() if self.has_prog["chatgpt"] else None,
                          "google": L.stored_ide_account()}  # закрытая IDE; запущенная уточнит в "local"
        jobs = {"local": (L.local_ide_info,)}
        if self.has_prog["claude"]:
            jobs[("ide", "claude")] = (L.claude_fetch,)
        if self.has_prog["chatgpt"]:
            jobs[("ide", "chatgpt")] = (L.codex_fetch,)
        for a in self.g_accs:
            jobs[("google", a["email"].lower())] = (L.ag_fetch, a, False, None)
        for p in self.profiles:
            if A.ident(p["kind"], p["email"]) != A.ident(p["kind"], self.ide_email.get(p["kind"]) or ""):
                jobs[("profile", p["dir"])] = (L.claude_fetch if p["kind"] == "claude" else L.codex_fetch, p)
        rec = self.ide_email["google"]
        if rec and rec.lower() not in {a["email"].lower() for a in self.g_accs}:
            login = L.stored_ide_login()  # аккаунт закрытой IDE не добавлен — лимиты по её же входу из облака
            if login and login[1]:
                jobs[("ide", "google")] = (L.ag_fetch, {"email": login[0], "refresh_token": login[1]}, False, None)
        return jobs

    # ------------------------------------------------ плитки
    def _google_res(self, email):
        e = email.lower()
        li = (getattr(self, "ide_local", None) or {}).get("accounts", {}).get(e)
        if li:  # данные запущенной IDE точнее облачных
            return self._merge(email, {"plan": li["plan"], "models": li["rows"], "credits": None,
                                       "source": self.IDE_SRC})
        if ("google", e) in self.parts:
            return self.parts[("google", e)]
        return self.parts.get(("ide", "google"))

    def build_tiles(self):
        """[(ключ плитки, плитка)]; плитка: kind, ident (ключ аккаунта и истории), email, title, ide, res."""
        names, tiles, ide_ident = self.names(), [], {}
        running = getattr(self, "ide_running", False)
        added = {a["email"].lower() for a in self.g_accs} | {A.ident(p["kind"], p["email"]) for p in self.profiles}
        for kind in A.KINDS:
            email = self.ide_email.get(kind)
            if email and A.ident(kind, email) in added:
                ide_ident[kind] = A.ident(kind, email)  # добавленный аккаунт программы — на своей плитке
                self._adopt_key(A.IDE_KEY[kind], ide_ident[kind])
        for kind in A.KINDS:
            if kind in ide_ident:
                continue
            email = self.ide_email.get(kind)
            if kind == "google":  # IDE без входа и без записи входа — плитки нет (1.5.4, владелец)
                present = bool(email)
            else:
                present = self.has_prog.get(kind)
            if not present:
                continue
            ident = A.ident(kind, email) if email else A.IDE_KEY[kind]
            ide_ident[kind] = ident
            res = self._google_res(email) if kind == "google" else self.parts.get(("ide", kind))
            tiles.append((A.IDE_KEY[kind], {"kind": kind, "ident": ident, "email": email, "ide": True,
                                            "title": names.get(ident) or A.PRODUCT[kind], "res": res}))
        # добавленные аккаунты — всегда под своим ключом: после смены аккаунта программы («→ в IDE») плитки
        # остаются на местах, переезжает только метка «● IDE» (замечание владельца 15.11.2026)
        for a in self.g_accs:
            ident = a["email"].lower()
            ide = ident == ide_ident.get("google")
            tiles.append((ident, {"kind": "google", "ident": ident, "email": a["email"], "ide": ide,
                                  "title": names.get(ident) or a["email"],
                                  "res": self._google_res(a["email"]) if ide else self.parts.get(("google", ident))}))
        for p in self.profiles:
            ident = A.ident(p["kind"], p["email"])
            ide = ident == ide_ident.get(p["kind"])
            tiles.append((ident, {"kind": p["kind"], "ident": ident, "email": p["email"], "ide": ide,
                                  "title": names.get(ident) or p["email"], "profile": p,
                                  "res": self.parts.get(("ide", p["kind"]) if ide else ("profile", p["dir"]))}))
        self.tile_info = dict(tiles)
        return tiles

    def _adopt_key(self, prog, ident):
        """1.5.0 хранила добавленный аккаунт программы под ключом плитки программы: если в сохранённом порядке
        (и в свёрнутых) есть ключ программы, а аккаунта нет, аккаунт встаёт на его место — плитка не прыгает.
        То же при добавлении аккаунта, в который вошла программа: он занимает место её плитки."""
        order = self.s.get("order") or [k for k in getattr(self, "card_order", []) if not k.startswith("\0")]
        if prog in order and ident not in order:
            order[order.index(prog)] = ident
            self.s["order"] = order
            if prog in self.collapsed:
                self.collapsed ^= {prog, ident}
            self.persist()

    def tile_title(self, ident):
        """Как называется плитка аккаунта с ключом ident (для графика и предупреждений)."""
        for t in getattr(self, "tile_info", {}).values():
            if t["ident"] == ident:
                return t["title"]
        return self.names().get(ident) or ident

    # ------------------------------------------------ все аккаунты (для «Управления аккаунтами»)
    def all_accounts(self):
        """{вид: [(ключ, имя или None, email, добавлен ли, профиль)]} — добавленные и аккаунты программ."""
        out = {k: [] for k in A.KINDS}
        names, seen = self.names(), set()
        for a in L.load_accounts():
            i = a["email"].lower()
            out["google"].append((i, names.get(i), a["email"], True, None))
            seen.add(i)
        for p in A.load_profiles():
            i = A.ident(p["kind"], p["email"])
            out[p["kind"]].append((i, names.get(i), p["email"], True, p))
            seen.add(i)
        for kind in A.KINDS:
            email = getattr(self, "ide_email", {}).get(kind)
            if email and A.ident(kind, email) not in seen:
                i = A.ident(kind, email)
                out[kind].append((i, names.get(i), email, False, None))
        pos = {k: n for n, k in enumerate(self.card_order)}
        for kind in out:  # в порядке плиток; недобавленный аккаунт программы — на месте плитки программы
            out[kind].sort(key=lambda r, k=kind: pos.get(r[0] if r[3] else A.IDE_KEY[k], 999))
        return out

    def notify(self, text, color, hold=10):
        """Сообщение в строке статуса, которое обновление окна не затирает hold секунд."""
        self.status_sticky = time.time() + hold
        self.say(text, color)
        self.root.after(hold * 1000 + 200, self.set_status_updated)

    # ------------------------------------------------ добавление
    def relogin(self, kind, ident, email, prof=None):
        """Кнопка ↻ в «Управлении аккаунтами» (1.5.4): войти в добавленный аккаунт заново — свежие токены."""
        self.close_menu()
        self.add_account(kind, relogin={"ident": ident, "email": email, "prof": prof})

    def add_account(self, kind="google", relogin=None):
        """Добавить аккаунт: Google — вход в браузере; Claude и ChatGPT — вход самой программы в окне консоли
        в отдельную папку профиля. Совпал с аккаунтом программы — плитка программы получает его имя.
        relogin — повторный вход в уже добавленный аккаунт (↻): вход заменяется, только если это тот же аккаунт."""
        if getattr(self, "adding", False):
            self.cancel_add()  # предыдущий незавершённый вход — отменить, начать новый
        self._add_token = token = getattr(self, "_add_token", 0) + 1
        p = None
        if kind == "google":
            self.say(T("Войдите в {email} в открывшемся браузере…", email=relogin["email"]) if relogin
                     else T("Войдите в Google в открывшемся браузере…"), GOOGLE)
        elif relogin:
            try:
                p = A.start_login(kind)
            except Exception as e:
                self.notify(str(e), RED, hold=20)
                return
            self.say(T("Войдите в {email} в открывшемся браузере…", email=relogin["email"]), ACCENT[kind])
        else:
            try:
                p = A.start_login(kind)
            except Exception as e:
                self.notify(str(e), RED, hold=20)
                return
            self.say(T("Войдите в аккаунт Claude в открывшемся браузере…") if kind == "claude"
                     else T("Войдите в аккаунт ChatGPT в открывшемся браузере…"), ACCENT[kind])
        self.adding, self._add_profile = True, p
        self._show_cancel(True)

        def work():
            verify = None
            try:
                if kind == "google":
                    acc = (L.ag_login(login_hint=relogin["email"], expect=relogin["email"]) if relogin
                           else L.ag_login())
                    verify = acc.pop("verify_url", None)  # вход получен, но Google просит подтвердить аккаунт
                    if relogin and acc["email"].lower() != relogin["email"].lower():
                        raise RuntimeError(T("в браузере выбран {got}, а не {email} — вход не обновлён",
                                             got=acc["email"], email=relogin["email"]))
                    L.save_accounts([x for x in L.load_accounts() if x["email"].lower() != acc["email"].lower()]
                                    + [acc])
                    email = acc["email"]
                elif relogin:
                    email = A.relogin_profile(relogin["prof"], A.finish_login(p))["email"]
                else:
                    email = A.add_profile(A.finish_login(p))["email"]
                ident = A.ident(kind, email)

                def done():
                    if token != self._add_token:  # этот вход уже отменён и заменён новым
                        return
                    self.adding = False
                    self._show_cancel(False)
                    names = self.names()
                    if kind == "google" and verify:
                        self.notify(T("Вход {email} получен, но Google просит подтвердить аккаунт — "
                                      "ссылка на странице в браузере", email=email), YELLOW, hold=20)
                        self.refresh()
                        return
                    if relogin:
                        self.notify(T("Вход «{name}» обновлён", name=names.get(ident) or email), GREEN)
                        self.refresh()
                        return
                    if ident not in names:
                        names[ident] = A.suggest_name(kind, email, self.taken_names(ident))
                        self.persist()
                    now_in = {"claude": A.claude_ide_email, "chatgpt": A.codex_ide_email}.get(
                        kind, lambda: (getattr(self, "ide_email", {}) or {}).get("google"))()  # аккаунт программы сейчас
                    match = ident == A.ident(kind, now_in or "")
                    self.notify(T("{product}: аккаунт {email} теперь называется «{name}»", product=A.PRODUCT[kind],
                                  email=email, name=names[ident]) if match else
                                T("Добавлен {email} — «{name}»", email=email, name=names[ident]), GREEN)
                    self.refresh()
                self.root.after(0, done)
            except Exception as e:
                failed = T("Вход не выполнен: {error}", error=e)  # текст — сейчас: вне except имени e уже нет

                def fail():
                    if token != self._add_token:
                        return
                    self.adding = False
                    self._show_cancel(False)
                    self.notify(failed, RED, hold=20)
                self.root.after(0, fail)
        threading.Thread(target=work, daemon=True).start()

    def cancel_add(self):
        """Отменить незавершённый вход (ссылка «Отменить» в строке статуса или новый «Добавить аккаунт»)."""
        if getattr(self, "_add_profile", None):
            A.cancel_login(self._add_profile)
        self._add_token = getattr(self, "_add_token", 0) + 1
        self.adding, self._add_profile = False, None
        self._show_cancel(False)
        self.notify(T("Вход отменён"), MUTED, hold=5)

    def _show_cancel(self, on):
        """Ссылка «Отменить» справа в строке статуса, пока идёт вход в аккаунт."""
        lbl = getattr(self, "cancel_lbl", None)
        if lbl is None:
            lbl = self.cancel_lbl = tk.Label(self.status_row, text=T("Отменить"), bg=self.status.cget("bg"), fg=MUTED,
                                             font=(FONT, 9, "underline"), cursor="hand2")
            lbl.bind("<Button-1>", lambda e: self.cancel_add())
        if on:
            lbl.config(text=T("Отменить"))
            lbl.pack(side="right", before=self.status)
        else:
            lbl.pack_forget()

    # ------------------------------------------------ смена аккаунта программы (кнопки «→ в IDE», «→ в Codex»)
    def switch_mode(self, t, ide_running):
        """Метка или кнопка плитки: "current"/"switch" (IDE Antigravity), "current_codex"/"switch_codex" (Codex)."""
        if t["kind"] == "google":
            # «● IDE» — только у аккаунта запущенной IDE со входом; IDE закрыта или открыта без входа — у аккаунта
            # её записи входа обычная «→ в IDE» (1.5.4, владелец: серой «○ IDE» быть не должно)
            if t["ide"] and ide_running and not getattr(self, "ide_nologin", False):
                return "current"
            return "switch" if ide_running or L.ide_installed() else None
        suffix = {"chatgpt": "_codex", "claude": "_claude"}[t["kind"]]
        if t["ide"]:
            return "current" + suffix
        return "switch" + suffix if t.get("profile") and self.has_prog.get(t["kind"]) else None

    def switch_program(self, key):
        """Кнопка «→ в Codex» / «→ в Claude»: подтверждение, затем смена аккаунта программы в потоке."""
        if getattr(self, "prog_switching", False):
            return
        t, card = getattr(self, "tile_info", {}).get(key), self.cards.get(key)
        if not t or not t.get("profile"):
            return
        if t["kind"] == "chatgpt":
            title = T("Переключить Codex на {email}?", email=t["email"])
            text = T("Приложение Codex перезапустится, незавершённые ответы прервутся. Прежний вход "
                     "сохранится в AI Limits — на него можно вернуться.")
        else:
            title = T("Переключить Claude Code на {email}?", email=t["email"])
            text = T("Новые сеансы Claude Code начнут работать под этим аккаунтом, открытые — под прежним до "
                     "перезапуска; открытый сеанс может вернуть прежний вход, тогда повторите смену. Прежний вход "
                     "сохранится в AI Limits — на него можно вернуться.")
        self.confirm(card.ide if card else self.menu_btn, title, text,
                     lambda: self._switch_program_go(t["kind"], t["profile"]))

    def _switch_program_go(self, kind, profile):
        self.prog_switching = True
        color, mod = (CODEX, CX) if kind == "chatgpt" else (CLAUDE, CL)
        self.say(T("Codex: подготовка…") if kind == "chatgpt" else T("Claude: подготовка…"), color)

        def work():
            try:
                r = mod.switch(profile, on_status=lambda s: self.root.after(0, lambda: self.say(s, color)))
                failed = None
            except Exception as e:
                r, failed = None, (T("Не удалось сменить аккаунт Codex: {error}", error=e) if kind == "chatgpt"
                                   else T("Не удалось сменить аккаунт Claude Code: {error}", error=e))

            def done():
                self.prog_switching = False
                if failed:
                    self.notify(failed, RED, hold=20)
                    return
                kept = r.get("kept")
                if r.get("created") and kept:  # прежний аккаунт программы добавлен сам — дать ему имя
                    ident = A.ident(kind, kept["email"])
                    if ident not in self.names():
                        self.names()[ident] = A.suggest_name(kind, kept["email"], self.taken_names(ident))
                        self.persist()
                self.notify(T("Codex теперь работает под {email}", email=r["email"]) if kind == "chatgpt"
                            else T("Claude Code теперь работает под {email}", email=r["email"]), GREEN)
                self.refresh()
            self.root.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def remove_account(self, ident, anchor=None):
        """Удалить добавленный аккаунт (и папку его профиля) и его имя."""
        kind, email, prof = None, ident, None
        for k, rows in self.all_accounts().items():
            for i, name, e, stored, p in rows:
                if i == ident and stored:
                    kind, email, prof = k, e, p

        def go():
            if kind == "google":
                L.save_accounts([x for x in L.load_accounts() if x["email"].lower() != ident])
            elif prof:
                A.remove_profile(prof)
            self.names().pop(ident, None)
            self.persist()
            self.refresh()
            if getattr(self, "menu_win", None) or getattr(self, "_menu_manage", False):
                self.show_accounts()
        if kind:
            self.confirm(anchor or self.menu_btn, T("Удалить «{name}» ({email})?", name=self.names().get(ident) or email,
                                                    email=email),
                         T("Вернуть его можно через «Добавить аккаунт»."), go, at_pointer=True)

    # ------------------------------------------------ «Управление аккаунтами» (раскрывающийся пункт меню ⚙)
    def show_accounts(self):
        """Меню ⚙ с раскрытым «Управлением аккаунтами» (1.5.3: раньше — отдельное окно на месте меню)."""
        self._menu_manage = True
        self._show_menu(False)

    def accounts_list(self, box, redraw):
        """Аккаунты по сервисам внутри меню: группа — цветом сервиса, строка — имя и мелко email, ✎ и ✕."""
        for kind, rows in self.all_accounts().items():
            tk.Label(box, text=GROUP[kind], bg=CARD, fg=ACCENT[kind], font=(FONT, 9, "bold"),
                     anchor="w").pack(fill="x", pady=(6, 1), padx=(30, 4))
            if not rows:
                tk.Label(box, text=T("нет аккаунтов"), bg=CARD, fg=FAINT, font=(FONT, 9),
                         anchor="w").pack(fill="x", padx=(38, 4))
            for ident, name, email, stored, prof in rows:
                self._account_row(box, kind, ident, name, email, stored, redraw, prof)
        tk.Frame(box, bg=CARD, height=4).pack()

    def _account_row(self, box, kind, ident, name, email, stored, redraw=None, prof=None):
        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", padx=(36, 2), pady=1)
        text = tk.Frame(row, bg=CARD)
        text.pack(side="left", fill="x", expand=True)
        title = tk.Label(text, text=name or A.PRODUCT[kind], bg=CARD, fg=FG if name else MUTED, font=(FONT, 10), anchor="w")
        title.pack(fill="x")
        sub = email + ("" if stored else "  ·  " + T("из программы"))
        tk.Label(text, text=sub, bg=CARD, fg=FAINT, font=(FONT, 8), anchor="w").pack(fill="x")

        def button(label, tip_cmd):
            b = tk.Label(row, text=label, bg=CARD, fg=MUTED, font=(FONT, 10), cursor="hand2", padx=6, pady=2)
            b.pack(side="right")
            b.bind("<Enter>", lambda e: b.config(bg=CARD_HI, fg=FG))
            b.bind("<Leave>", lambda e: b.config(bg=CARD, fg=MUTED))
            b.bind("<Button-1>", lambda e: tip_cmd(b))
            return b
        if stored:
            button("✕", lambda b: self.remove_account(ident, b))
        button("✎", lambda b: self._rename_entry(title, ident, name or "", on_done=redraw or self.show_accounts))
        if stored and (kind == "google" or prof):  # ↻ — войти заново, обновить токены (1.5.4)
            Tooltip(button("↻", lambda b: self.relogin(kind, ident, email, prof)),
                    T("Войти в аккаунт заново — обновить вход"))

    # ------------------------------------------------ переименование
    def _rename_entry(self, label, ident, current, on_done=None, font=None):
        """Поле ввода на месте надписи label: Enter или щелчок мимо — сохранить, Esc — отменить.
        Занятое или пустое имя не применяется: поле остаётся, рядом — сообщение.
        Поле уже открыто (повторный ✎, 1.5.4: раньше — TclError «isn't packed») — только фокус в него."""
        open_ent = getattr(label, "_rename_ent", None)
        if open_ent is not None and open_ent.winfo_exists():
            open_ent.focus_set()
            return open_ent
        parent = label.master
        var = tk.StringVar(value=current)
        ent = tk.Entry(parent, textvariable=var, bg=CARD_HI, fg=FG, insertbackground=FG, relief="flat",
                       font=font or label.cget("font"), highlightthickness=1, highlightbackground=LINE,
                       highlightcolor=BLUE)
        info = label.grid_info() if label.winfo_manager() == "grid" else None
        if info:
            ent.grid(row=info["row"], column=info["column"], sticky="w", padx=info.get("padx", 0))
            label.grid_remove()
        else:
            ent.pack(fill="x", before=label)
            label.pack_forget()
        err = tk.Label(parent, bg=CARD, fg=RED, font=(FONT, 8), anchor="w")
        state = {"done": False}

        def close(save):
            if state["done"]:
                return
            if save:
                problem = self.set_name(ident, var.get())
                if problem:
                    err.config(text=problem)
                    if info:
                        err.grid(row=info["row"] + 1, column=info["column"], columnspan=5, sticky="w")
                    else:
                        err.pack(fill="x", after=ent)
                    ent.focus_set()
                    return
            state["done"] = True
            ent.destroy()
            err.destroy()
            if info:
                label.grid()
            elif label.winfo_exists():
                rest = [w for w in parent.winfo_children() if w is not label and w.winfo_manager()]
                label.pack(fill="x", **({"before": rest[0]} if rest else {}))
            if on_done:
                on_done()
        ent.bind("<Return>", lambda e: close(True))
        ent.bind("<Escape>", lambda e: close(False))
        ent.bind("<FocusOut>", lambda e: self.root.after(150, lambda: ent.winfo_exists() and
                                                           self.root.focus_get() is not ent and close(True)))
        ent.focus_set()
        ent.select_range(0, "end")
        label._rename_ent = ent
        self.rename_entry = ent
        return ent

    def begin_rename(self, key):
        """Двойной щелчок по имени в плитке — переименовать её аккаунт прямо в окне."""
        card, t = self.cards.get(key), getattr(self, "tile_info", {}).get(key)
        if not card or not t:
            return
        named = t["title"] != A.PRODUCT[t["kind"]] or t["ident"] in self.names()
        self._rename_entry(card.title, t["ident"], t["title"] if named else "",
                           on_done=lambda: card.fit_title())
