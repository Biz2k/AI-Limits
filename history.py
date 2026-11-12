"""История лимитов: запись значений в history.csv (хранится 60 дней), прогноз исчерпания, ряды для графика.

Строка файла: время (UTC, ISO), ключ ("claude" или email), окно лимита, израсходовано %, время сброса (ISO).
Записываются только свежие значения — сохранённые из кэша (помеченные «≈» в окне) в историю не попадают.
"""
import csv
import datetime as dt
import os

import storage
from i18n import T, day, duration

HISTORY_DAYS = 60     # сколько дней хранить
SAME_VALUE_GAP = 600  # не изменившееся значение записывается не чаще раза в 10 минут
WEEK, FIVE = 7 * 86400, 5 * 3600
DAY = 86400
# окно лимита -> (длина окна, за какое время брать расход, наименьший отрезок данных, считать ли расход суточным)
# Недельный лимит: люди работают сессиями с простоями, поэтому всё набранное за последние сутки считается
# расходом одного дня (даже если данных меньше суток) — темп сессии на круглые сутки не растягивается.
# 5-часовой лимит: темп текущей сессии за последние полтора часа.
RULES = {"нед": (WEEK, DAY, 3600, True), "5 ч": (FIVE, 90 * 60, 600, False)}
OLD_NAMES = {("claude", "Неделя (все модели)"): "Неделя"}  # прежние названия окон в файле истории

_series = None  # {(ключ, окно): [(время, %, сброс)]} — вся история в памяти, читается один раз


def history_file():
    return os.path.join(storage.APPDIR, "history.csv")


def _ts(iso):
    """ISO-время -> секунды эпохи (None, если не разобрать)."""
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp()


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    return dt.datetime.now(dt.timezone.utc).timestamp()


def _rule(window):
    low = window.lower()
    return next((r for k, r in RULES.items() if low.startswith(k)), None)


def load(now=None):
    """Читает историю в память (один раз за запуск) и убирает из файла записи старше HISTORY_DAYS."""
    global _series
    if _series is not None:
        return _series
    now = now or _now()
    edge = now - HISTORY_DAYS * 86400
    data, total = {}, 0
    try:
        with open(history_file(), encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                total += 1
                try:
                    ts, used = _ts(row[0]), float(row[3])
                except (IndexError, ValueError):
                    continue
                if ts is None or ts < edge:
                    continue
                win = OLD_NAMES.get((row[1], row[2]), row[2])
                data.setdefault((row[1], win), []).append((ts, used, _ts(row[4]) if len(row) > 4 else None))
    except OSError:
        pass
    for pts in data.values():
        pts.sort()
    _series = data
    if total > sum(len(p) for p in data.values()):  # есть устаревшие или испорченные строки — переписать файл
        try:
            rows = sorted((ts, key, win, used, rs) for (key, win), pts in data.items() for ts, used, rs in pts)
            tmp = history_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows([_iso(ts), key, win, f"{used:g}", _iso(rs) if rs else ""]
                                        for ts, key, win, used, rs in rows)
            os.replace(tmp, history_file())
        except OSError:
            pass
    return _series


def _points(claude, ag):
    """Свежие значения из данных окна: [(ключ, окно, %, время сброса ISO)]."""
    out = []
    if isinstance(claude, dict):
        out += [("claude", r["name"], r["used"], r.get("resets_at")) for r in claude.get("limits", [])]
    for email, res in ag or []:
        if isinstance(res, dict):
            out += [(email.lower(), m["name"], m["used"], m.get("resets_at")) for m in res.get("models", [])
                    if m.get("used") is not None and not m.get("seen")]
    return out


def record(claude, ag, now=None):
    """Дописывает в историю текущие значения. Возвращает число записанных строк."""
    now = now or _now()
    data = load(now)
    rows = []
    for key, win, used, resets in _points(claude, ag):
        pts = data.setdefault((key, win), [])
        rs = _ts(resets)
        if pts:
            ts0, used0, rs0 = pts[-1]
            if abs(used0 - used) < 0.05 and rs0 == rs and now - ts0 < SAME_VALUE_GAP:
                continue
        pts.append((now, float(used), rs))
        rows.append([_iso(now), key, win, f"{float(used):g}", _iso(rs) if rs else ""])
    if rows:
        try:
            os.makedirs(storage.APPDIR, exist_ok=True)
            with open(history_file(), "a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows(rows)
        except OSError:
            pass
    return len(rows)


def series(key, window, since):
    """Точки ряда не раньше since: [(время, %)]."""
    return [(ts, used) for ts, used, _ in load().get((key.lower(), window), []) if ts >= since]


def when_text(ts, now=None):
    """«14:00» для сегодняшнего дня, иначе «чт 14:00» (день недели — на языке интерфейса)."""
    t = dt.datetime.fromtimestamp(ts)
    today = dt.datetime.fromtimestamp(now or _now()).date()
    return f"{t:%H:%M}" if t.date() == today else f"{day(t.weekday())} {t:%H:%M}"


def forecast(key, window, used, resets_at, now=None):
    """Прогноз: на сколько хватит лимита при нынешнем расходе. None, если данных мало, расход не растёт
    или лимит уже исчерпан. Иначе {"eta": время исчерпания, "left": секунд до него, "reset": время сброса,
    "before_reset": bool, "rate": % в час, "when": «чт 14:00», "line": «хватит на 2 дня 5 часов, до чт 14:00»
    (только если раньше сброса)} — тексты на языке интерфейса."""
    rule = _rule(window)
    reset = _ts(resets_at)
    if not rule or reset is None or used is None or used >= 100:
        return None
    length, lookback, min_span, daily = rule
    now = now or _now()
    start = max(reset - length, now - lookback)
    pts = [(ts, u) for ts, u, _ in load(now).get((key.lower(), window), []) if start <= ts <= now]
    pts.append((now, float(used)))
    for i in range(len(pts) - 1, 0, -1):  # после сброса лимита считаем заново
        if pts[i][1] < pts[i - 1][1] - 1:
            pts = pts[i:]
            break
    span, gain = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
    if span < min_span or gain < 0.5:
        return None
    rate = gain / (DAY if daily else span)  # % в секунду
    left = (100 - used) / rate
    eta = now + left
    before = eta < reset
    when = when_text(eta, now)
    return {"eta": eta, "left": left, "reset": reset, "before_reset": before, "rate": rate * 3600, "when": when,
            "line": T("хватит на {span}, до {when}", span=duration(left), when=when) if before else None}


def forecasts(claude, ag, now=None):
    """Прогнозы для всех свежих значений: {(ключ, окно): прогноз}; ключ аккаунта — email в нижнем регистре."""
    out = {}
    for key, win, used, resets in _points(claude, ag):
        fc = forecast(key, win, used, resets, now)
        if fc:
            out[(key, win)] = fc
    return out
