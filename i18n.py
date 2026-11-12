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
    "Убрать {email} из списка?": ("Remove {email} from the list?", "Прибрати {email} зі списку?"),
    "Вернуть его можно через «Добавить Google-аккаунт».": ("You can add it back with “Add Google account”.",
                                                          "Повернути його можна через «Додати Google-акаунт»."),
    "макс {pct}%": ("max {pct}%", "макс {pct}%"),
    "Аккаунтов нет. Добавьте его в меню ⚙ → «Добавить Google-аккаунт».":
        ("No accounts yet. Add one: ⚙ → “Add Google account”.",
         "Акаунтів немає. Додайте його в меню ⚙ → «Додати Google-акаунт»."),
    "Нет данных о лимитах Gemini": ("No Gemini limit data", "Немає даних про ліміти Gemini"),
    "Максимум": ("Maximum", "Максимум"),
    "  ·  авто {interval}": ("  ·  auto {interval}", "  ·  авто {interval}"),
    "Обновлено {time}{auto}": ("Updated {time}{auto}", "Оновлено {time}{auto}"),
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
    "при таком темпе {line}": ("at this pace {line}", "за такого темпу {line}"),
    "до {when}": ("until {when}", "до {when}"),
    "Предупреждения по прогнозу": ("Forecast warnings", "Попередження за прогнозом"),
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
    "Добавить Google-аккаунт": ("Add Google account", "Додати Google-акаунт"),
    "Убрать Google-аккаунт": ("Remove Google account", "Прибрати Google-акаунт"),
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
}
