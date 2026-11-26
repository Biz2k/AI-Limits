"""Языки интерфейса AI Limits: английский (по умолчанию), русский, украинский.

Исходные строки в коде — русские: T("Обновить") возвращает перевод на текущий язык, а для русского — саму строку.
Подстановки — именованные: T("Добавлен {email}", email=...). Названия окон лимитов («Неделя», «5 часов») и
источников данных в программе остаются русскими (это ключи кэша и истории) и переводятся только при показе.
Консольная версия и журналы не переводятся.
"""

LANGS = (("en", "English"), ("ru", "Русский"), ("uk", "Українська"))
DEFAULT = "en"
_lang = DEFAULT

_DAYS = {"ru": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
         "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
         "uk": ("пн", "вт", "ср", "чт", "пт", "сб", "нд")}


def set_lang(code):
    """Выбирает язык; неизвестный код — язык по умолчанию. Возвращает установленный код."""
    global _lang
    _lang = code if code in dict(LANGS) else DEFAULT
    return _lang


def lang():
    return _lang


def day(index):
    """Короткое название дня недели (0 — понедельник)."""
    return _DAYS[_lang][index]


# единицы времени после «хватит на …»: ru/uk — формы для 1, 2–4, 5+; en — единственное и множественное число
_UNITS = {"ru": {"d": ("день", "дня", "дней"), "h": ("час", "часа", "часов"), "m": ("минуту", "минуты", "минут")},
          "uk": {"d": ("день", "дні", "днів"), "h": ("годину", "години", "годин"),
                 "m": ("хвилину", "хвилини", "хвилин")},
          "en": {"d": ("day", "days"), "h": ("hour", "hours"), "m": ("minute", "minutes")}}


def _count(n, unit):
    forms = _UNITS[_lang][unit]
    if len(forms) == 2:
        return f"{n} {forms[0] if n == 1 else forms[1]}"
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {forms[0]}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {forms[1]}"
    return f"{n} {forms[2]}"


def duration(seconds):
    """Промежуток словами для «хватит на …»: «2 дня 5 часов», «3 часа 20 минут», «40 минут»."""
    minutes = max(1, round(seconds / 60))
    d, rest = divmod(minutes, 1440)
    h, m = divmod(rest, 60)
    if d:
        parts = [_count(d, "d")] + ([_count(h, "h")] if h else [])
    elif h:
        parts = [_count(h, "h")] + ([_count(m, "m")] if m else [])
    else:
        parts = [_count(m, "m")]
    return " ".join(parts)


def T(text, **kw):
    """Перевод строки на текущий язык (нет перевода — русский исходник) с подстановкой именованных значений."""
    if _lang != "ru":
        pair = TEXTS.get(text)
        if pair:
            text = pair[0 if _lang == "en" else 1]
    return text.format(**kw) if kw else text


# русский исходник -> (английский, украинский)
TEXTS = {
    # ---- главное окно
    "⟳  Обновить": ("⟳  Refresh", "⟳  Оновити"),
    "Настройки": ("Settings", "Налаштування"),
    "Загрузка…": ("Loading…", "Завантаження…"),
    "Войдите в Google в открывшемся браузере…": ("Sign in to Google in the browser window that opened…",
                                                 "Увійдіть у Google у браузері, що відкрився…"),
    "Добавлен {email}": ("Added {email}", "Додано {email}"),
    "Вход не выполнен: {error}": ("Sign-in failed: {error}", "Вхід не виконано: {error}"),
    "Переключить IDE на {email}?": ("Switch the IDE to {email}?", "Перемкнути IDE на {email}?"),
    "Antigravity перезапустится, незавершённые ответы агента прервутся.":
        ("Antigravity will restart; unfinished agent replies will be interrupted.",
         "Antigravity перезапуститься, незавершені відповіді агента перервуться."),
    "IDE: подготовка…": ("IDE: preparing…", "IDE: підготовка…"),
    "IDE теперь работает под {email}": ("The IDE now runs as {email}", "IDE тепер працює під {email}"),
    "В IDE вошёл {now}, а не {email}": ("The IDE signed in as {now}, not {email}", "В IDE увійшов {now}, а не {email}"),
    "никто": ("nobody", "ніхто"),
    "Не удалось сменить аккаунт: {error}": ("Could not switch the account: {error}",
                                            "Не вдалося змінити акаунт: {error}"),
    "Нет данных о лимитах Gemini": ("No Gemini limit data", "Немає даних про ліміти Gemini"),
    "макс.": ("max", "макс."),
    'Claude: записываю вход…':
        ('Claude: writing the sign-in…',
         'Claude: записую вхід…'),
    'в Claude Code записался {now}, а не {email}':
        ('Claude Code got {now} instead of {email}',
         'у Claude Code записався {now}, а не {email}'),
    'Переключить Claude Code на {email}?':
        ('Switch Claude Code to {email}?',
         'Перемкнути Claude Code на {email}?'),
    'Новые сеансы Claude Code начнут работать под этим аккаунтом, открытые — под прежним до перезапуска; открытый сеанс может вернуть прежний вход, тогда повторите смену. Прежний вход сохранится в AI Limits — на него можно вернуться.':
        ('New Claude Code sessions will use this account; open ones keep the previous account until restarted, and an open session may bring the previous sign-in back — then switch again. The current sign-in is kept in AI Limits, so you can switch back.',
         'Нові сеанси Claude Code працюватимуть під цим акаунтом, відкриті — під попереднім до перезапуску; відкритий сеанс може повернути попередній вхід — тоді повторіть зміну. Попередній вхід збережеться в AI Limits — до нього можна повернутися.'),
    'Claude: подготовка…':
        ('Claude: preparing…',
         'Claude: підготовка…'),
    'Не удалось сменить аккаунт Claude Code: {error}':
        ('Could not switch the Claude Code account: {error}',
         'Не вдалося змінити акаунт Claude Code: {error}'),
    'Claude Code теперь работает под {email}':
        ('Claude Code now works as {email}',
         'Claude Code тепер працює під {email}'),
    'Этот аккаунт сейчас вошёл в Claude Code':
        ('Claude Code is signed in to this account now',
         'Цей акаунт зараз увійшов у Claude Code'),
    '→ в Claude':
        ('→ to Claude',
         '→ в Claude'),
    'Сделать этот аккаунт текущим в Claude Code':
        ('Make this the current account in Claude Code',
         'Зробити цей акаунт поточним у Claude Code'),
    'Codex не закрылся за {timeout} с':
        ('Codex did not close within {timeout} s',
         'Codex не закрився за {timeout} с'),
    'во входе профиля нет аккаунта ChatGPT — добавьте его заново':
        ('the profile sign-in has no ChatGPT account — add it again',
         'у вході профілю немає акаунта ChatGPT — додайте його знову'),
    'Codex запущен в терминале — закройте его и повторите':
        ('Codex is running in a terminal — close it and try again',
         'Codex запущено в терміналі — закрийте його і повторіть'),
    'Codex: закрываю приложение…':
        ('Codex: closing the app…',
         'Codex: закриваю застосунок…'),
    'в Codex записался {now}, а не {email}':
        ('Codex got {now} instead of {email}',
         'у Codex записався {now}, а не {email}'),
    'Codex: запускаю приложение…':
        ('Codex: starting the app…',
         'Codex: запускаю застосунок…'),
    'Этот аккаунт сейчас вошёл в Codex':
        ('Codex is signed in to this account now',
         'Цей акаунт зараз увійшов у Codex'),
    '→ в Codex':
        ('→ to Codex',
         '→ в Codex'),
    'Сделать этот аккаунт текущим в Codex':
        ('Make this the current account in Codex',
         'Зробити цей акаунт поточним у Codex'),
    'Переключить Codex на {email}?':
        ('Switch Codex to {email}?',
         'Перемкнути Codex на {email}?'),
    'Приложение Codex перезапустится, незавершённые ответы прервутся. Прежний вход сохранится в AI Limits — на него можно вернуться.':
        ('The Codex app will restart and unfinished answers will stop. The current sign-in is kept in AI Limits, so you can switch back.',
         "Застосунок Codex перезапуститься, незавершені відповіді перерв'ються. Попередній вхід збережеться в AI Limits — до нього можна повернутися."),
    'Codex: подготовка…':
        ('Codex: preparing…',
         'Codex: підготовка…'),
    'Не удалось сменить аккаунт Codex: {error}':
        ('Could not switch the Codex account: {error}',
         'Не вдалося змінити акаунт Codex: {error}'),
    'Codex теперь работает под {email}':
        ('Codex now works as {email}',
         'Codex тепер працює під {email}'),
    'Войдите в аккаунт Claude в открывшемся браузере…':
        ('Sign in to your Claude account in the browser that opened…',
         'Увійдіть в акаунт Claude у браузері, що відкрився…'),
    'Войдите в аккаунт ChatGPT в открывшемся браузере…':
        ('Sign in to your ChatGPT account in the browser that opened…',
         'Увійдіть в акаунт ChatGPT у браузері, що відкрився…'),
    'Вход отменён':
        ('Sign-in cancelled',
         'Вхід скасовано'),
    'Отменить':
        ('Cancel',
         'Скасувати'),
    'отменено':
        ('cancelled',
         'скасовано'),
    'время ожидания вышло':
        ('timed out',
         'час очікування минув'),
    'программа входа завершилась без входа':
        ('the sign-in program exited without signing in',
         'програма входу завершилася без входу'),
    'IDE Antigravity запущена, но вход не выполнен':
        ('The Antigravity IDE is running but not signed in',
         'IDE Antigravity запущено, але вхід не виконано'),
    '{product}: аккаунт {email} теперь называется «{name}»':
        ('{product}: account {email} is now called “{name}”',
         '{product}: акаунт {email} тепер називається «{name}»'),
    'Аккаунт {email} уже добавлен':
        ('Account {email} is already added',
         'Акаунт {email} уже додано'),
    'Аккаунтов нет. Добавьте его в меню ⚙ → «Добавить аккаунт».':
        ('No accounts. Add one in ⚙ → “Add account”.',
         'Акаунтів немає. Додайте його в меню ⚙ → «Додати акаунт».'),
    'Вернуть его можно через «Добавить аккаунт».':
        ('You can add it back with “Add account”.',
         'Повернути його можна через «Додати акаунт».'),
    'Вход не выполнен':
        ('Not signed in',
         'Вхід не виконано'),
    'Добавить аккаунт':
        ('Add account',
         'Додати акаунт'),
    'Добавлен {email} — «{name}»':
        ('Added {email} — “{name}”',
         'Додано {email} — «{name}»'),
    'Имя «{name}» уже занято':
        ('The name “{name}” is already taken',
         "Ім'я «{name}» уже зайняте"),
    'Имя длиннее {n} символов':
        ('The name is longer than {n} characters',
         "Ім'я довше за {n} символів"),
    'Имя не может быть пустым':
        ("The name can't be empty",
         "Ім'я не може бути порожнім"),
    'Не найден Claude Code (claude.exe) — установите его':
        ('Claude Code (claude.exe) not found — install it',
         'Не знайдено Claude Code (claude.exe) — встановіть його'),
    'Не найден Codex (codex.exe) — установите его':
        ('Codex (codex.exe) not found — install it',
         'Не знайдено Codex (codex.exe) — встановіть його'),
    'Не удалось узнать email вошедшего аккаунта':
        ("Couldn't get the email of the signed-in account",
         'Не вдалося дізнатися email акаунта, що увійшов'),
    'Удалить «{name}» ({email})?':
        ('Delete “{name}” ({email})?',
         'Видалити «{name}» ({email})?'),
    'Управление аккаунтами':
        ('Manage accounts',
         'Керування акаунтами'),
    'вход профиля потерян — удалите аккаунт и добавьте заново':
        ('the profile sign-in is lost — delete the account and add it again',
         'вхід профілю втрачено — видаліть акаунт і додайте знову'),
    'вход профиля устарел — удалите аккаунт и добавьте заново ({error})':
        ('the profile sign-in has expired — delete the account and add it again ({error})',
         'вхід профілю застарів — видаліть акаунт і додайте знову ({error})'),
    'из программы':
        ('from the app',
         'з програми'),
    'нет аккаунтов':
        ('no accounts',
         'немає акаунтів'),
    "Нет данных о лимитах": ("No limit data", "Немає даних про ліміти"),
    "Codex не установлен или в него не входили": ("Codex is not installed or not signed in",
                                                  "Codex не встановлено або в нього не входили"),
    "Codex вошёл не через аккаунт ChatGPT — лимитов подписки нет":
        ("Codex is not signed in with a ChatGPT account — there are no subscription limits",
         "Codex увійшов не через акаунт ChatGPT — лімітів підписки немає"),
    "вход Codex устарел — запустите Codex, он обновит его сам":
        ("the Codex sign-in is out of date — start Codex, it will renew it",
         "вхід Codex застарів — запустіть Codex, він оновить його сам"),
    "Обновлено {time}": ("Updated {time}", "Оновлено {time}"),
    # ---- время
    "1 мин": ("1 min", "1 хв"),
    "5 мин": ("5 min", "5 хв"),
    "15 мин": ("15 min", "15 хв"),
    "выкл": ("off", "вимк"),
    "сброшено": ("reset", "скинуто"),
    "{d}д {h}ч": ("{d}d {h}h", "{d}д {h}г"),
    "{h}ч {m}м": ("{h}h {m}m", "{h}г {m}хв"),
    "{m}м": ("{m}m", "{m}хв"),
    # ---- карточки
    "нет данных": ("no data", "немає даних"),
    "Облако сейчас отдаёт только другой лимит.\nЗначение появится, когда он сбросится,\n"
    "или если войти этим аккаунтом в IDE Antigravity.":
        ("The cloud currently reports only the other limit.\nThe value will appear when that one resets,\n"
         "or if you sign in to the Antigravity IDE with this account.",
         "Хмара зараз віддає лише інший ліміт.\nЗначення з'явиться, коли він скинеться,\n"
         "або якщо увійти цим акаунтом в IDE Antigravity."),
    "Google просит подтвердить этот аккаунт (Verify your account).\n"
    "Лимиты Gemini недоступны, пока вы не войдёте им в IDE Antigravity\n"
    "и не подтвердите аккаунт.":
        ("Google asks to verify this account (Verify your account).\n"
         "Gemini limits are unavailable until you sign in with it in the Antigravity IDE\n"
         "and verify the account.",
         "Google просить підтвердити цей акаунт (Verify your account).\n"
         "Ліміти Gemini недоступні, доки ви не увійдете ним в IDE Antigravity\n"
         "і не підтвердите акаунт."),
    "Войдите в {email} в открывшемся браузере…":
        ("Sign in to {email} in the browser that opened…", "Увійдіть у {email} у браузері, що відкрився…"),
    "в браузере выбран {got}, а не {email} — вход не обновлён":
        ("{got} was chosen in the browser, not {email} — the sign-in was not updated",
         "у браузері вибрано {got}, а не {email} — вхід не оновлено"),
    "Google просит подтвердить аккаунт": ("Google asks to verify the account", "Google просить підтвердити акаунт"),
    "Вход в {email} выполнен, но лимиты Gemini недоступны, пока аккаунт не подтверждён в Google.":
        ("Signed in to {email}, but Gemini limits are unavailable until the account is verified at Google.",
         "Вхід у {email} виконано, але ліміти Gemini недоступні, доки акаунт не підтверджено в Google."),
    "Подтвердить аккаунт": ("Verify the account", "Підтвердити акаунт"),
    "Зачем это нужно —": ("Why this is needed —", "Навіщо це потрібно —"),
    "справка Google": ("Google Help", "довідка Google"),
    "Готово": ("Done", "Готово"),
    "Вход в {email} выполнен. Эту вкладку можно закрыть.":
        ("Signed in to {email}. You can close this tab.", "Вхід у {email} виконано. Цю вкладку можна закрити."),
    "Сервер временно ограничил запросы — повторю через {min} мин":
        ("The server is temporarily limiting requests — will retry in {min} min",
         "Сервер тимчасово обмежив запити — повторю через {min} хв"),
    "IDE запущена; новая версия IDE не даёт проверить вход — проверьте аккаунт в самой IDE":
        ("The IDE is running; the new IDE version does not allow checking the sign-in — check the account in the IDE",
         "IDE запущена; нова версія IDE не дає перевірити вхід — перевірте акаунт у самій IDE"),
    "Google просит подтвердить аккаунт {email} — переключение отменено. Войдите в него заново кнопкой ↻ в "
    "«Управлении аккаунтами»":
        ("Google asks to verify the account {email} — the switch was cancelled. Sign in to it again with ↻ in "
         "“Manage accounts”",
         "Google просить підтвердити акаунт {email} — перемикання скасовано. Увійдіть у нього знову кнопкою ↻ в "
         "«Керуванні акаунтами»"),
    "Вход не выполнен": ("Sign-in failed", "Вхід не виконано"),
    "неверный ответ Google": ("invalid response from Google", "неправильна відповідь Google"),
    "Вход {email} получен, но Google просит подтвердить аккаунт — ссылка на странице в браузере":
        ("Signed in to {email}, but Google asks to verify the account — the link is on the page in the browser",
         "Вхід {email} отримано, але Google просить підтвердити акаунт — посилання на сторінці в браузері"),
    "Вход «{name}» обновлён": ("Sign-in of “{name}” updated", "Вхід «{name}» оновлено"),
    "Войти в аккаунт заново — обновить вход":
        ("Sign in to the account again — refresh the sign-in", "Увійти в акаунт заново — оновити вхід"),
    "Сохранённое значение от {seen}.\nСейчас облако отдаёт другой лимит.":
        ("Saved value from {seen}.\nThe cloud currently reports a different limit.",
         "Збережене значення від {seen}.\nЗараз хмара віддає інший ліміт."),
    "Этот аккаунт сейчас вошёл в IDE Antigravity": ("This account is signed in to the Antigravity IDE",
                                                   "Цей акаунт зараз увійшов в IDE Antigravity"),
    "→ в IDE": ("→ to IDE", "→ в IDE"),
    "Сделать этот аккаунт текущим в IDE Antigravity": ("Make this the current account of the Antigravity IDE",
                                                      "Зробити цей акаунт поточним в IDE Antigravity"),
    # ---- названия лимитов и источников (в данных остаются русскими)
    "Неделя": ("Week", "Тиждень"),
    "5 часов": ("5 hours", "5 годин"),
    "Неделя Opus": ("Week Opus", "Тиждень Opus"),
    "Неделя Sonnet": ("Week Sonnet", "Тиждень Sonnet"),
    "Действующий лимит": ("Active limit", "Чинний ліміт"),
    "неделя": ("week", "тиждень"),
    "данные IDE Antigravity": ("Antigravity IDE data", "дані IDE Antigravity"),
    "облако": ("cloud", "хмара"),
    "облако · действующий лимит": ("cloud · active limit", "хмара · чинний ліміт"),
    # ---- прогноз и график
    "хватит на {span}, до {when}": ("lasts {span}, until {when}", "вистачить на {span}, до {when}"),
    "до {when}": ("until {when}", "до {when}"),
    "Предупреждения по прогнозу": ("Forecast warnings", "Попередження за прогнозом"),
    "Карточки в две колонки": ("Cards in two columns", "Картки у дві колонки"),
    "Расход за 7 дней": ("Usage over 7 days", "Витрата за 7 днів"),
    "Расход за сутки": ("Usage over 24 hours", "Витрата за добу"),
    "Истории пока нет — она копится при каждом обновлении": ("No history yet — it builds up with every refresh",
                                                            "Історії поки немає — вона накопичується з кожним оновленням"),
    "При таком темпе {line} — раньше сброса ({reset}).":
        ("At this pace it {line} — before the reset ({reset}).",
         "За такого темпу {line} — раніше скидання ({reset})."),
    "При таком темпе лимита хватит до сброса.": ("At this pace the limit lasts until the reset.",
                                                "За такого темпу ліміту вистачить до скидання."),
    "Прогноза нет: мало данных или расход не растёт.": ("No forecast: not enough data, or usage is not growing.",
                                                       "Прогнозу немає: мало даних або витрата не зростає."),
    "При таком темпе закончится раньше сброса": ("At this pace runs out before the reset",
                                                "За такого темпу закінчиться раніше скидання"),
    # ---- меню и всплывающие окна
    "Нет": ("No", "Ні"),
    "Да": ("Yes", "Так"),
    "Поверх всех окон": ("Always on top", "Поверх усіх вікон"),
    "Автозапуск: {error}": ("Autostart: {error}", "Автозапуск: {error}"),
    "Сворачивать в трей": ("Minimize to tray", "Згортати в трей"),
    "Сворачивать в трей при закрытии": ("Close to tray", "Згортати в трей під час закриття"),
    "Автозапуск после старта системы": ("Start with Windows", "Автозапуск після старту системи"),
    "Автообновление": ("Auto refresh", "Автооновлення"),
    "Порог предупреждения": ("Warning threshold", "Поріг попередження"),
    "Язык": ("Language", "Мова"),
    "Открыть папку данных": ("Open data folder", "Відкрити папку даних"),
    "Не удалось открыть папку: {error}": ("Could not open the folder: {error}", "Не вдалося відкрити папку: {error}"),
    "Израсходовано больше {pct}% лимита": ("More than {pct}% of the limit used", "Витрачено понад {pct}% ліміту"),
    "и ещё {n}": ("and {n} more", "і ще {n}"),
    # ---- трей
    "Открыть": ("Open", "Відкрити"),
    "Обновить": ("Refresh", "Оновити"),
    "Выход": ("Exit", "Вихід"),
    "загрузка": ("loading", "завантаження"),
    "загрузка…": ("loading…", "завантаження…"),
    "ошибка": ("error", "помилка"),
    "{name}  нед {week} · 5ч {five}": ("{name}  wk {week} · 5h {five}", "{name}  тиж {week} · 5г {five}"),
    # ---- сообщения логики, которые видны в окне
    "нет OAuth-ключей Antigravity — задайте их: python limits.py keys или переменные окружения (см. README)":
        ("Antigravity OAuth keys are missing — set them: python limits.py keys, or environment variables (see README)",
         "немає OAuth-ключів Antigravity — задайте їх: python limits.py keys або змінні середовища (див. README)"),
    "сеть: {reason}": ("network: {reason}", "мережа: {reason}"),
    "Нет связи с сервером": ("No connection to the server", "Немає зв'язку з сервером"),
    "нет ~/.claude/.credentials.json — войдите в Claude Code командой `claude`":
        ("~/.claude/.credentials.json not found — sign in to Claude Code with `claude`",
         "немає ~/.claude/.credentials.json — увійдіть у Claude Code командою `claude`"),
    "Claude Code не залогинен через подписку (claudeAiOauth нет)":
        ("Claude Code is not signed in with a subscription (no claudeAiOauth)",
         "Claude Code не увійшов через підписку (claudeAiOauth немає)"),
    "токен аккаунта не расшифрован (данные с другого компьютера?) — добавьте аккаунт заново":
        ("the account token cannot be decrypted (data from another computer?) — add the account again",
         "токен акаунта не розшифровано (дані з іншого комп'ютера?) — додайте акаунт знову"),
    "Готово, можно закрыть вкладку.": ("Done, you can close this tab.", "Готово, вкладку можна закрити."),
    "Ошибка входа, см. консоль.": ("Sign-in error.", "Помилка входу."),
    "вход не завершён: {reason}": ("sign-in not completed: {reason}", "вхід не завершено: {reason}"),
    "таймаут": ("timeout", "таймаут"),
    "Google не выдал refresh_token — попробуйте ещё раз": ("Google did not return a refresh token — try again",
                                                          "Google не видав refresh_token — спробуйте ще раз"),
    "Antigravity не закрылся за {timeout} с": ("Antigravity did not close in {timeout} s",
                                               "Antigravity не закрився за {timeout} с"),
    "Исполняемый файл IDE Antigravity не найден: {exe}": ("Antigravity IDE executable not found: {exe}",
                                                         "Виконуваний файл IDE Antigravity не знайдено: {exe}"),
    "Не указан email аккаунта для IDE": ("No account email given for the IDE", "Не вказано email акаунта для IDE"),
    "Аккаунт {email} не найден в {file}": ("Account {email} not found in {file}", "Акаунт {email} не знайдено в {file}"),
    "У аккаунта {email} отсутствует refresh_token": ("Account {email} has no refresh token",
                                                    "В акаунта {email} немає refresh_token"),
    "Проверка токена Google…": ("Checking the Google token…", "Перевірка токена Google…"),
    "Не удалось обновить токен для {email}: {error}": ("Could not refresh the token for {email}: {error}",
                                                      "Не вдалося оновити токен для {email}: {error}"),
    "Google не вернул access_token для {email}": ("Google did not return an access token for {email}",
                                                 "Google не повернув access_token для {email}"),
    "Не найден Antigravity.exe — убедитесь, что IDE Antigravity установлена":
        ("Antigravity.exe not found — make sure the Antigravity IDE is installed",
         "Не знайдено Antigravity.exe — переконайтеся, що IDE Antigravity встановлено"),
    "Резервное копирование прежних настроек…": ("Backing up the current credentials…",
                                               "Резервне копіювання попередніх налаштувань…"),
    "Закрытие IDE Antigravity…": ("Closing the Antigravity IDE…", "Закриття IDE Antigravity…"),
    "Подстановка токена в Credential Manager и настройки…": ("Writing the token to Credential Manager and settings…",
                                                            "Підставлення токена в Credential Manager і налаштування…"),
    "Перезапуск IDE Antigravity…": ("Restarting the Antigravity IDE…", "Перезапуск IDE Antigravity…"),
    "Проверка входа через GetUserStatus…": ("Checking the sign-in…", "Перевірка входу…"),
    "в IDE обнаружен аккаунт {found}, а не {email}": ("the IDE shows account {found}, not {email}",
                                                     "в IDE виявлено акаунт {found}, а не {email}"),
    "IDE не вошла в аккаунт за {timeout} с": ("the IDE did not sign in within {timeout} s",
                                              "IDE не увійшла в акаунт за {timeout} с"),
    "IDE не ответила за {timeout} с — проверьте аккаунт в самой IDE":
        ("The IDE did not respond within {timeout} s — check the account in the IDE itself",
         "IDE не відповіла за {timeout} с — перевірте акаунт у самій IDE"),
    "Не получилось — возвращаю прежний аккаунт IDE…": ("It did not work — restoring the previous IDE account…",
                                                      "Не вийшло — повертаю попередній акаунт IDE…"),
    "{error}. Вернуть прежний аккаунт тоже не удалось ({error2}) — копии лежат в {folder}, журнал: {log}":
        ("{error}. Restoring the previous account failed too ({error2}) — backups are in {folder}, log: {log}",
         "{error}. Повернути попередній акаунт теж не вдалося ({error2}) — копії лежать у {folder}, журнал: {log}"),
    "{error}. Прежний аккаунт IDE ({previous}) возвращён (журнал: {log})":
        ("{error}. The previous IDE account ({previous}) was restored (log: {log})",
         "{error}. Попередній акаунт IDE ({previous}) повернуто (журнал: {log})"),
    "без входа": ("not signed in", "без входу"),
    "Резервных копий нет в {folder}": ("No backups in {folder}", "Резервних копій немає в {folder}"),
    "Сохранение нынешних учётных данных…": ("Saving the current credentials…", "Збереження поточних облікових даних…"),
    "Возврат учётных данных из копии…": ("Restoring the credentials from the backup…",
                                        "Повернення облікових даних із копії…"),
    "Запуск IDE Antigravity…": ("Starting the Antigravity IDE…", "Запуск IDE Antigravity…"),
    "IDE Antigravity не запущена — откройте её и повторите": ("The Antigravity IDE is not running — open it and try again",
                                                             "IDE Antigravity не запущено — відкрийте її та повторіть"),
    "IDE: выход из текущего аккаунта…": ("IDE: signing out of the current account…",
                                        "IDE: вихід із поточного акаунта…"),
    "Выберите аккаунт в открывшемся окне Google…": ("Choose an account in the Google window that opened…",
                                                   "Виберіть акаунт у вікні Google, що відкрилося…"),
    "IDE не выполнила вход: {error}": ("The IDE did not sign in: {error}", "IDE не виконала вхід: {error}"),
    "IDE ответила, но вход не выполнен — войдите в самой IDE": ("The IDE responded but did not sign in — sign in in the IDE itself",
                                                               "IDE відповіла, але вхід не виконано — увійдіть у самій IDE"),
    "Вход не выполнен за 5 минут — войдите в самой IDE (журнал: {log})":
        ("Sign-in was not completed in 5 minutes — sign in in the IDE itself (log: {log})",
         "Вхід не виконано за 5 хвилин — увійдіть у самій IDE (журнал: {log})"),
    "Понятно": ("OK", "Зрозуміло"),
    "Поиск ключей {product}…": ("Looking for {product} keys…", "Пошук ключів {product}…"),
    "Установите {product}": ("Install {product}", "Установіть {product}"),
    "Чтобы добавить аккаунт {service}, установите {product} на этот компьютер.":
        ("To add a {service} account, install {product} on this computer.",
         "Щоб додати акаунт {service}, установіть {product} на цей комп'ютер."),
    "Проверить обновления": ("Check for updates", "Перевірити оновлення"),
    "Проверка обновлений…": ("Checking for updates…", "Перевірка оновлень…"),
    "Установлена последняя версия": ("You are on the latest version", "Встановлено останню версію"),
    "Доступна версия {ver}": ("Version {ver} available", "Доступна версія {ver}"),
    "Версия: v{cur}  •  GitHub: v{lat}": ("Version: v{cur}  •  GitHub: v{lat}", "Версія: v{cur}  •  GitHub: v{lat}"),
    "Версия: v{cur}": ("Version: v{cur}", "Версія: v{cur}"),
    "Скачать и установить v{ver}": ("Download and install v{ver}", "Завантажити та встановити v{ver}"),
    "Открыть релиз на GitHub": ("Open release on GitHub", "Відкрити реліз на GitHub"),
    "Не удалось проверить обновления": ("Could not check for updates", "Не вдалося перевірити оновлення"),
    "Загрузка обновления… {pct}%": ("Downloading update… {pct}%", "Завантаження оновлення… {pct}%"),
    "Загрузка обновления…": ("Downloading update…", "Завантаження оновлення…"),
    "Проверка SHA-256 и перезапуск…": ("Verifying SHA-256 and restarting…", "Перевірка SHA-256 і перезапуск…"),
    "Контрольная сумма SHA-256 не совпала": ("SHA-256 checksum mismatch", "Контрольна сума SHA-256 не збіглася"),
    "Автообновление доступно только для собранного AI Limits.exe":
        ("Auto-update is only available for the packaged AI Limits.exe",
         "Автооновлення доступне лише для зібраного AI Limits.exe"),
    "Ошибка обновления: {error}": ("Update failed: {error}", "Помилка оновлення: {error}"),
}
