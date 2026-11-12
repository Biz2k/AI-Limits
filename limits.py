#!/usr/bin/env python3
"""limits — лимиты Claude Code и аккаунтов Google Antigravity в одном окне.

Только стандартная библиотека Python 3.9+. Windows 11 / Linux / macOS.

  limits                     показать всё
  limits add                 добавить аккаунт Google (откроется браузер)
  limits accounts            список аккаунтов
  limits remove <email>      удалить аккаунт
  limits -w 60               обновлять каждые 60 с (Ctrl+C — выход)
  limits --json              вывод в JSON
  limits --all-models        показать все модели Antigravity, не только основные
"""

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import time

from version import __version__

import storage
import winapi
import cloud
import ide_local
import ide_switch
import i18n

# ---------------------------------------------------------------- части программы
# Логика разнесена по модулям; limits остаётся единой точкой входа: окно обращается к L.<имя>,
# а имя, которого нет в самом limits, ищется в модулях-частях (значение всегда текущее).
_PARTS = (storage, winapi, cloud, ide_local, ide_switch)


def __getattr__(name):
    for part in _PARTS:
        if name in vars(part):
            return vars(part)[name]
    raise AttributeError(f"module 'limits' has no attribute {name!r}")

# ---------------------------------------------------------------- цвета
if os.name == "nt":
    os.system("")  # включает ANSI-последовательности в консоли Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
USE_COLOR = bool(sys.stdout and sys.stdout.isatty()) and not os.environ.get("NO_COLOR")


def c(code, s):
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def dim(s): return c("2", s)
def bold(s): return c("1", s)


def level_color(used_pct):
    if used_pct >= 90: return "91"   # красный
    if used_pct >= 70: return "93"   # жёлтый
    return "92"                      # зелёный


def bar(used_pct, width=20):
    used_pct = max(0.0, min(100.0, used_pct))
    n = round(used_pct / 100 * width)
    return c(level_color(used_pct), "█" * n) + dim("░" * (width - n))


def fmt_reset(iso):
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    left = t - dt.datetime.now(dt.timezone.utc)
    secs = int(left.total_seconds())
    local = t.astimezone().strftime("%d.%m %H:%M")
    if secs <= 0:
        return f"сброс {local}"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    span = f"{d}д {h}ч" if d else (f"{h}ч {m:02d}м" if h else f"{m}м")
    return f"сброс через {span} ({local})"


# ================================================================ вывод
def render(claude, ag, warn):
    out = []
    now = dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    out.append(bold("AI limits") + dim(f"  ·  {now}  ·  % = израсходовано"))
    out.append("")

    # --- Claude
    if isinstance(claude, Exception):
        out.append(bold("Claude Code") + "  " + c("91", f"ошибка: {claude}"))
    else:
        out.append(bold("Claude Code") + dim(f"  ·  план {claude['plan']}"))
        for r in claude["limits"]:
            flag = c("91", "  ⚠") if r["used"] >= warn else ""
            out.append(f"  {r['name']:<22} {bar(r['used'])} {r['used']:5.0f}%  {dim(fmt_reset(r['resets_at']))}{flag}")
    out.append("")

    # --- Antigravity
    if not ag:
        out.append(bold("Antigravity") + dim("  ·  нет аккаунтов — добавьте: limits add"))
    best = None
    for email, res in ag:
        if isinstance(res, Exception):
            out.append(bold(f"Antigravity · {email}") + "  " + c("91", f"ошибка: {res}"))
            out.append("")
            continue
        plan = f"  ·  {res['plan']}" if res["plan"] else ""
        plan += f"  ·  Gemini, {res.get('source', '')}"
        out.append(bold(f"Antigravity · {email}") + dim(plan))
        if res.get("credits"):
            cr = res["credits"]
            out.append(dim(f"  кредиты: {cr['available']} из {cr['monthly']}"))
        if not res["models"]:
            out.append(dim("  (моделей с квотой нет)"))
        for m in res["models"]:
            if m["used"] is None:
                out.append(f"  {m['name'][:22]:<22} {dim('░' * 20)}     ?  {dim('нет данных — облако сейчас отдаёт другой лимит')}")
                continue
            flag = c("91", "  ⚠") if m["used"] >= warn else ""
            seen = dim(f"  [≈ данные от {m['seen']}]") if m.get("seen") else ""
            out.append(f"  {m['name'][:22]:<22} {bar(m['used'])} {m['used']:5.0f}%  {dim(fmt_reset(m['resets_at']))}{flag}{seen}")
        b = best_weekly([(email, res)])
        if b and (best is None or b[1] > best[1]):
            best = b
        out.append("")

    if best and len(ag) > 1:
        out.append(c("96", f"→ Максимум {best[0]} {best[1]:.0f}%"))
    return "\n".join(out)


def collect(all_models):
    accs = cloud.load_accounts()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        fc = ex.submit(cloud.claude_fetch)
        local = ex.submit(ide_local.local_ide_quota).result()
        fa = [(a["email"], ex.submit(cloud.ag_fetch, a, all_models, local)) for a in accs]

        def res(f):
            try:
                return f.result()
            except Exception as e:  # noqa
                return e
        ag = [(e, res(f)) for e, f in fa]
        # аккаунт, вошедший в IDE, показываем, даже если он не добавлен через `limits add`
        known = {a["email"].lower() for a in accs}
        for email, li in local.items():
            if email not in known:
                ag.append((email, {"plan": li["plan"], "models": li["rows"], "credits": None,
                                   "source": "данные IDE Antigravity", "ide_only": True}))
        return res(fc), merge_with_cache(ag)


# ---------------------------------------------------------------- кэш лимитов
# Облако по аккаунту, не вошедшему в IDE, отдаёт только один (самый строгий) лимит Gemini.
# Поэтому запоминаем каждый увиденный лимит и показываем его, пока не наступил его сброс.
CACHE_FILE = os.path.join(storage.APPDIR, "cache.json")
WINDOWS = ("Неделя", "5 часов")


def _future(iso):
    try:
        return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")) > dt.datetime.now(dt.timezone.utc)
    except Exception:
        return False


def best_weekly(ag):
    """(email, % свободно) аккаунта с наибольшим остатком недельного лимита Gemini."""
    best = None
    for email, res in ag:
        if not isinstance(res, dict):
            continue
        for m in res["models"]:
            if m["name"] == "Неделя" and m["used"] is not None:
                free = 100 - m["used"]
                if best is None or free > best[1]:
                    best = (email, free)
    return best


def merge_with_cache(ag):
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    now = dt.datetime.now().strftime("%d.%m %H:%M")
    out = []
    for email, res in ag:
        if isinstance(res, Exception):
            out.append((email, res))
            continue
        key = email.lower()
        ent = {k: v for k, v in cache.get(key, {}).items() if _future(v.get("resets_at", ""))}
        fresh = {m["name"]: m for m in res["models"] if m["name"] in WINDOWS}
        for name, m in fresh.items():
            ent[name] = {"used": m["used"], "resets_at": m["resets_at"], "seen": now}
        rows = []
        for name in WINDOWS:
            if name in fresh:
                rows.append(fresh[name])
            elif name in ent:
                v = ent[name]
                rows.append({"name": name, "used": v["used"], "resets_at": v["resets_at"], "seen": v["seen"]})
            else:
                rows.append({"name": name, "used": None, "resets_at": None})
        cache[key] = ent
        out.append((email, dict(res, models=rows)))
    try:
        storage.atomic_write_json(CACHE_FILE, cache)
    except Exception:
        pass
    return out


def to_jsonable(claude, ag):
    j = lambda r: {"error": str(r)} if isinstance(r, Exception) else r
    return {"time": dt.datetime.now().astimezone().isoformat(), "claude": j(claude),
            "antigravity": {e: j(r) for e, r in ag}}


# ================================================================ main
def main():
    i18n.set_lang("ru")  # консольная версия не переведена: сообщения логики тоже по-русски
    storage.install_error_log()
    ap = argparse.ArgumentParser(prog="limits", description="Лимиты Claude Code и Google Antigravity")
    ap.add_argument("cmd", nargs="?", default="show", choices=["show", "add", "accounts", "remove", "switch-ide", "restore-ide", "keys"])
    ap.add_argument("email", nargs="?")
    ap.add_argument("-w", "--watch", type=int, metavar="SEC", help="обновлять каждые SEC секунд")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    ap.add_argument("--version", action="version", version=f"AI Limits {__version__}")
    ap.add_argument("--browser", action="store_true",
                    help="switch-ide: вход через окно Google (запасной способ)")
    ap.add_argument("--test-rollback", action="store_true",
                    help="switch-ide: проверка отката — подставить негодный токен и убедиться, что прежний аккаунт вернулся")
    ap.add_argument("--yes", action="store_true", help="restore-ide: не спрашивать подтверждение")
    ap.add_argument("--all-models", action="store_true", help="все модели Antigravity")
    ap.add_argument("--warn", type=float, default=80, help="порог предупреждения, %% (по умолчанию 80)")
    a = ap.parse_args()
    cloud.protect_stored_secrets()

    if a.cmd == "keys":
        print("OAuth-ключи Antigravity: " + (f"заданы ({cloud.G_KEYS_SOURCE})" if cloud.G_KEYS_SOURCE else "не заданы"))
        print(dim(f"файл: {storage.KEYS_FILE} (зашифрован под вашей учётной записью Windows)"))
        import getpass
        cid = input("Новый client id (пусто — ничего не менять): ").strip()
        if not cid:
            return
        sec = getpass.getpass("Client secret (при вводе не показывается): ").strip()
        if not sec:
            print("Отменено.")
            return
        cloud.set_google_keys(cid, sec)
        print(c("92", "Ключи сохранены."))
        return
    if a.cmd == "add":
        acc = cloud.ag_login()
        accs = [x for x in cloud.load_accounts() if x["email"] != acc["email"]] + [acc]
        cloud.save_accounts(accs)
        print(c("92", f"Добавлен {acc['email']}. Всего аккаунтов: {len(accs)}"))
        return
    if a.cmd == "accounts":
        accs = cloud.load_accounts()
        print("\n".join(f"  {i+1}. {x['email']}" for i, x in enumerate(accs)) or "аккаунтов нет")
        print(dim(f"\nфайл: {storage.ACCOUNTS_FILE}"))
        return
    if a.cmd == "remove":
        if not a.email:
            ap.error("укажите email")
        accs = cloud.load_accounts()
        left = [x for x in accs if x["email"].lower() != a.email.lower()]
        cloud.save_accounts(left)
        print(f"Удалено: {len(accs) - len(left)}")
        return
    if a.cmd == "switch-ide":
        def say(s):
            print(dim(s))
        if a.browser:
            res = ide_switch.ide_login_browser(on_status=say)
        elif not a.email:
            ap.error("укажите email для переключения IDE (или --browser для входа через окно Google)")
        else:
            res = ide_switch.ide_switch_account(a.email, on_status=say, bad_token=a.test_rollback)
        print(c("92", f"IDE переключена на {res}"))
        return
    if a.cmd == "restore-ide":
        meta = ide_switch.latest_ide_backup()
        if not meta:
            raise RuntimeError(f"Резервных копий нет в {storage.IDE_BACKUP_DIR}")
        ts = meta["timestamp"]
        try:
            ts = f"{dt.datetime.strptime(ts, '%Y%m%d_%H%M%S'):%d.%m.%Y %H:%M:%S}"
        except ValueError:
            pass
        print(f"Копия от {ts}, аккаунт IDE в ней: {meta.get('previous_email') or 'без входа'}.")
        print("IDE Antigravity будет закрыта и запущена снова, если она открыта.")
        if not a.yes and input("Вернуть учётные данные IDE из этой копии? [y/N] ").strip().lower() not in ("y", "д"):
            print("Отменено.")
            return
        ide_switch.ide_restore_backup(meta, on_status=lambda t: print(dim(t)))
        print(c("92", "Учётные данные IDE возвращены."))
        return

    while True:
        claude, ag = collect(a.all_models)
        if a.json:
            print(json.dumps(to_jsonable(claude, ag), ensure_ascii=False, indent=2))
        else:
            if a.watch:
                print("\033[2J\033[H", end="")
            print(render(claude, ag, a.warn))
        if not a.watch:
            break
        try:
            time.sleep(a.watch)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except RuntimeError as e:
        print(c("91", f"Ошибка: {e}"), file=sys.stderr)
        sys.exit(1)
