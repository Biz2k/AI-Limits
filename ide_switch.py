"""Смена аккаунта IDE Antigravity: резервные копии учётных данных, подстановка токена, откат."""
import datetime as dt
import json
import os
import secrets
import threading
import time

import cloud
import ide_local
import storage
import winapi
from i18n import T


IDE_CRED_TARGET = "gemini:antigravity"
IDE_CRED_USER = "antigravity"
IDE_BACKUPS_KEEP = 5  # сколько последних резервных копий хранить


def _copy_file(src, dst):
    with open(src, "rb") as fi:
        data = fi.read()
    with open(dst, "wb") as fo:
        fo.write(data)
    return data


def _prune_ide_backups(folder=None, keep=IDE_BACKUPS_KEEP):
    """Оставляет keep последних резервных копий (в них лежат токены — не копим без нужды).
    Файлы user_scope_<email> не трогает."""
    import re
    folder = folder or storage.IDE_BACKUP_DIR
    try:
        names = os.listdir(folder)
    except OSError:
        return
    stamp = re.compile(r"_(\d{8}_\d{6})(?:\.json)?$")
    stamps = sorted({m.group(1) for m in map(stamp.search, names) if m})
    old = set(stamps[:-keep]) if keep else set(stamps)
    for n in names:
        m = stamp.search(n)
        if (m and m.group(1) in old) or n.endswith("_latest.json"):  # *_latest — копии от прежней версии
            try:
                os.remove(os.path.join(folder, n))
            except OSError:
                pass


def backup_ide_credentials():
    r"""Резервная копия учётных данных IDE перед изменением:
    - запись gemini:antigravity (Credential Manager)
    - %APPDATA%\Antigravity\app_storage.json
    - %APPDATA%\Antigravity\credential-user-scope
    Возвращает dict с метаданными (его принимает restore_ide_credentials)."""
    os.makedirs(storage.IDE_BACKUP_DIR, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {"timestamp": ts, "files": {}}

    # 1. Windows Credential Manager
    cred = winapi._wincred_read(IDE_CRED_TARGET)
    if cred and cred.get("blob"):
        blob = cred["blob"]
        cred_path = os.path.join(storage.IDE_BACKUP_DIR, f"gemini_antigravity_{ts}.json")
        with open(cred_path, "wb") as f:
            f.write(storage.protect_bytes(blob))  # в записи лежат токены — храним зашифрованной
        meta["files"]["cred"] = cred_path
        meta["cred_user"] = cred.get("user")
        meta["cred_persist"] = cred.get("persist")
        try:
            parsed = json.loads(blob.decode("utf-8"))
            meta["previous_email"] = parsed.get("id_token_email")
            meta["writer_id"] = parsed.get("writer_id")
        except Exception:
            pass

    # 2. app_storage.json
    storage_file = os.path.join(storage.ANTIGRAVITY_APPDATA, "app_storage.json")
    if os.path.exists(storage_file):
        storage_backup = os.path.join(storage.IDE_BACKUP_DIR, f"app_storage_{ts}.json")
        try:
            with open(storage_file, "rb") as fi, open(storage_backup, "wb") as fo:
                fo.write(storage.protect_bytes(fi.read()))
            meta["files"]["app_storage"] = storage_backup
        except Exception as e:
            ide_local._ide_log(f"Ошибка бэкапа app_storage.json: {e}")

    # 3. credential-user-scope
    scope_file = os.path.join(storage.ANTIGRAVITY_APPDATA, "credential-user-scope")
    if os.path.exists(scope_file):
        scope_backup = os.path.join(storage.IDE_BACKUP_DIR, f"credential-user-scope_{ts}")
        try:
            raw_scope = _copy_file(scope_file, scope_backup)
            meta["files"]["scope"] = scope_backup
            meta["scope_content"] = raw_scope.decode("utf-8", errors="replace")
            if meta.get("previous_email"):
                safe_email = meta["previous_email"].replace("@", "_at_")
                with open(os.path.join(storage.IDE_BACKUP_DIR, f"user_scope_{safe_email}"), "wb") as fo:
                    fo.write(raw_scope)
        except Exception as e:
            ide_local._ide_log(f"Ошибка бэкапа credential-user-scope: {e}")

    storage.atomic_write_json(os.path.join(storage.IDE_BACKUP_DIR, f"meta_{ts}.json"), meta)
    _prune_ide_backups()
    return meta


def restore_ide_credentials(meta):
    """Возвращает учётные данные IDE из резервной копии (meta от backup_ide_credentials). IDE должна быть закрыта."""
    files = (meta or {}).get("files") or {}
    cred_path = files.get("cred")
    if cred_path:
        with open(cred_path, "rb") as f:
            winapi._wincred_write(IDE_CRED_TARGET, meta.get("cred_user") or IDE_CRED_USER, storage.unprotect_bytes(f.read()),
                           meta.get("cred_persist") or 2)
    else:  # до переключения записи не было (в IDE никто не входил)
        winapi._wincred_delete(IDE_CRED_TARGET)
    if files.get("app_storage"):
        with open(files["app_storage"], "rb") as fi:
            data = storage.unprotect_bytes(fi.read())
        with open(os.path.join(storage.ANTIGRAVITY_APPDATA, "app_storage.json"), "wb") as fo:
            fo.write(data)
    scope_file = os.path.join(storage.ANTIGRAVITY_APPDATA, "credential-user-scope")
    if files.get("scope"):
        _copy_file(files["scope"], scope_file)
    elif os.path.exists(scope_file):
        os.remove(scope_file)


def _ide_write_account(acc, token_resp, writer_id):
    """Записывает токен аккаунта во все места хранения учётных данных IDE (IDE должна быть закрыта)."""
    expires_in = token_resp.get("expires_in", 3599)
    cred_data = {
        "token": {
            "access_token": token_resp["access_token"],
            "token_type": token_resp.get("token_type", "Bearer"),
            "refresh_token": acc["refresh_token"],
            "expiry": (dt.datetime.now().astimezone() + dt.timedelta(seconds=expires_in)).isoformat(),
            "expires_in": expires_in,
        },
        "auth_method": "consumer",
        "id_token_email": acc["email"],
        "writer_id": writer_id,
    }
    winapi._wincred_write(IDE_CRED_TARGET, IDE_CRED_USER, json.dumps(cred_data, separators=(",", ":")).encode("utf-8"))
    ide_local._ide_log("Windows Credential gemini:antigravity записан для", acc["email"])

    # app_storage.json
    os.makedirs(storage.ANTIGRAVITY_APPDATA, exist_ok=True)
    storage_file = os.path.join(storage.ANTIGRAVITY_APPDATA, "app_storage.json")
    storage_data = {}
    if os.path.exists(storage_file):
        with open(storage_file, "r", encoding="utf-8") as f:
            storage_data = json.load(f)  # не читается — ошибка и откат, а не затирание настроек IDE
    storage_data["agy.onboarding.lastLoginUsername"] = acc["email"]
    storage.atomic_write_json(storage_file, storage_data)
    ide_local._ide_log("app_storage.json обновлен (lastLoginUsername)")

    # credential-user-scope
    scope_file = os.path.join(storage.ANTIGRAVITY_APPDATA, "credential-user-scope")
    saved_user_scope = os.path.join(storage.IDE_BACKUP_DIR, "user_scope_" + acc["email"].replace("@", "_at_"))
    if os.path.exists(saved_user_scope):
        _copy_file(saved_user_scope, scope_file)
        ide_local._ide_log("Восстановлен сохранённый credential-user-scope для", acc["email"])
    elif os.path.exists(scope_file):
        os.remove(scope_file)
        ide_local._ide_log("Старый credential-user-scope удалён (будет пересоздан при старте)")
    return scope_file, saved_user_scope


class IdeSwitchUnverified(RuntimeError):
    """Токен записан и IDE запущена, но её локальный сервер так и не ответил — проверить аккаунт не удалось."""


def ide_switch_account(target_email, on_status=None, timeout=90, bad_token=False):
    r"""Смена аккаунта IDE Antigravity на target_email без окна Google:
    1. Находит refresh_token выбранного аккаунта в accounts.json и получает свежий access_token
       (OAuth-клиент тот же, что у входа IDE).
    2. Делает резервную копию учётных данных IDE.
    3. Штатно закрывает IDE (не закрылась — отмена, ничего не изменено).
    4. Записывает токен в Credential Manager (gemini:antigravity), lastLoginUsername в
       %APPDATA%\Antigravity\app_storage.json и обновляет credential-user-scope.
    5. Запускает IDE и проверяет аккаунт через GetUserStatus её локального сервера.
    При сбое на шагах 4–5 возвращает прежние учётные данные из резервной копии. Если же сервер IDE просто
    не ответил за timeout секунд (IDE ещё запускается), отката нет — IdeSwitchUnverified.
    bad_token=True — проверка отката: в IDE подставляется заведомо негодный токен."""
    say = on_status or (lambda s: None)
    target_email = (target_email or "").strip()
    if not target_email:
        raise ValueError(T("Не указан email аккаунта для IDE"))

    accs = cloud.load_accounts()
    acc = next((a for a in accs if a.get("email", "").lower() == target_email.lower()), None)
    if not acc:
        raise RuntimeError(T("Аккаунт {email} не найден в {file}", email=target_email, file=storage.ACCOUNTS_FILE))
    if not acc.get("refresh_token"):
        raise RuntimeError(T("У аккаунта {email} отсутствует refresh_token", email=target_email))

    ide_local._ide_log("=== Старт переключения IDE на", target_email, "===")
    was_running = ide_local._ide_open()  # нужно для отката: закрытую IDE после него не запускаем
    if was_running:
        try:
            cur = ide_local.ide_current_account()
        except Exception:
            cur = None
        if cur and cur.lower() == acc["email"].lower():
            ide_local._ide_log("IDE уже работает под", cur, "— перезапуск не нужен")
            return cur

    say(T("Проверка токена Google…"))
    try:
        cloud._need_google_keys()
        token_resp = cloud.http_json(cloud.G_TOKEN_URL, {
            "client_id": cloud.G_CLIENT_ID,
            "client_secret": cloud.G_CLIENT_SECRET,
            "refresh_token": acc["refresh_token"],
            "grant_type": "refresh_token"
        }, form=True)
    except Exception as e:
        ide_local._ide_log("Ошибка обновления токена:", str(e))
        raise RuntimeError(T("Не удалось обновить токен для {email}: {error}", email=target_email, error=e)) from None
    if not token_resp.get("access_token"):
        raise RuntimeError(T("Google не вернул access_token для {email}", email=target_email))
    if bad_token:
        ide_local._ide_log("ПРОВЕРКА ОТКАТА: в IDE подставляется заведомо негодный токен")
        token_resp = dict(token_resp, access_token="ai-limits-rollback-test")
        acc = dict(acc, refresh_token="ai-limits-rollback-test")

    exe_path = ide_local.find_ide_executable()
    if not exe_path:
        raise RuntimeError(T("Не найден Antigravity.exe — убедитесь, что IDE Antigravity установлена"))

    say(T("Резервное копирование прежних настроек…"))
    backup_meta = backup_ide_credentials()
    previous = backup_meta.get("previous_email")
    ide_local._ide_log("Бэкап сохранён:", backup_meta.get("timestamp"), "предыдущий email:", str(previous))
    writer_id = backup_meta.get("writer_id") or secrets.token_urlsafe(16)[:22]

    say(T("Закрытие IDE Antigravity…"))
    try:
        ide_local.stop_ide()
    except Exception as e:
        ide_local._ide_log("IDE не закрылась, переключение отменено:", str(e))
        raise
    ide_local._ide_log("IDE остановлена")

    try:
        say(T("Подстановка токена в Credential Manager и настройки…"))
        scope_file, saved_user_scope = _ide_write_account(acc, token_resp, writer_id)

        say(T("Перезапуск IDE Antigravity…"))
        ide_local.start_ide(exe_path)
        ide_local._ide_log("IDE запущена:", exe_path)

        say(T("Проверка входа через GetUserStatus…"))
        started = time.time()
        deadline = started + timeout
        last_detected = None
        state = None  # что видно в IDE: None — сервер не найден, "нет входа" — сервер отвечает без аккаунта
        seen_line, seen_at = None, 0
        while time.time() < deadline:
            time.sleep(1)
            diag, began = [], time.time()
            try:
                servers = ide_local.find_ide_servers(diag)
            except Exception as e:
                ide_local._ide_log("Опрос language_server:", str(e))
                continue
            if not servers:
                diag.append("Antigravity.exe " + ("запущен" if ide_local._ide_running() else "не запущен"))
            line = "; ".join(diag)
            if line != seen_line or time.time() - seen_at >= 15:  # каждое изменение и не реже раза в 15 с
                ide_local._ide_log(f"Ожидание {int(began - started)} с (опрос {time.time() - began:.1f} с):", line)
                seen_line, seen_at = line, time.time()
            cur = next((us["email"] for _, us in servers if us and us.get("email")), None)
            state = cur or ("нет входа" if servers else None)
            if not cur:
                continue
            if cur.lower() == acc["email"].lower():
                ide_local._ide_log("Успешный вход под целевым аккаунтом:", cur)
                try:
                    if os.path.exists(scope_file):
                        _copy_file(scope_file, saved_user_scope)
                except Exception:
                    pass
                return cur
            if cur != last_detected:
                ide_local._ide_log("В IDE обнаружен другой аккаунт:", cur)
            last_detected = cur
        if last_detected:
            raise RuntimeError(T("в IDE обнаружен аккаунт {found}, а не {email}", found=last_detected, email=acc["email"]))
        if state == "нет входа":
            raise RuntimeError(T("IDE не вошла в аккаунт за {timeout} с", timeout=timeout))
        raise IdeSwitchUnverified(T("IDE не ответила за {timeout} с — проверьте аккаунт в самой IDE", timeout=timeout))
    except IdeSwitchUnverified as e:
        ide_local._ide_log("Проверка не удалась, отката нет:", str(e))
        raise
    except Exception as e:
        ide_local._ide_log("Сбой переключения:", str(e), "— возвращаю прежние учётные данные")
        say(T("Не получилось — возвращаю прежний аккаунт IDE…"))
        try:
            ide_local.stop_ide()
            restore_ide_credentials(backup_meta)
            if was_running:
                ide_local.start_ide(exe_path)
            ide_local._ide_log("Откат выполнен, прежний аккаунт:", str(previous))
        except Exception as e2:
            ide_local._ide_log("Откат не удался:", str(e2))
            raise RuntimeError(T("{error}. Вернуть прежний аккаунт тоже не удалось ({error2}) — "
                                 "копии лежат в {folder}, журнал: {log}", error=e, error2=e2,
                                 folder=storage.IDE_BACKUP_DIR, log=ide_local.IDE_LOG)) from None
        raise RuntimeError(T("{error}. Прежний аккаунт IDE ({previous}) возвращён (журнал: {log})", error=e,
                             previous=previous or T("без входа"), log=ide_local.IDE_LOG)) from None


def latest_ide_backup():
    """Метаданные самой свежей резервной копии учётных данных IDE или None."""
    try:
        names = sorted(n for n in os.listdir(storage.IDE_BACKUP_DIR) if n.startswith("meta_") and n.endswith(".json"))
    except OSError:
        return None
    for name in reversed(names):
        try:
            with open(os.path.join(storage.IDE_BACKUP_DIR, name), encoding="utf-8") as f:
                meta = json.load(f)
            if isinstance(meta, dict) and meta.get("timestamp"):
                return meta
        except Exception:
            continue
    return None


def ide_restore_backup(meta=None, on_status=None):
    """Возвращает учётные данные IDE из резервной копии (по умолчанию — из последней): закрывает IDE,
    сохраняет нынешние данные новой копией (так что повтор команды отменяет возврат), записывает прежние
    и запускает IDE, если она была запущена. Возвращает метаданные возвращённой копии."""
    say = on_status or (lambda s: None)
    meta = meta or latest_ide_backup()
    if not meta:
        raise RuntimeError(T("Резервных копий нет в {folder}", folder=storage.IDE_BACKUP_DIR))
    ide_local._ide_log("=== Возврат учётных данных IDE из копии", meta.get("timestamp"),
             "аккаунт:", str(meta.get("previous_email")), "===")
    was_running = ide_local._ide_open()
    exe_path = ide_local.find_ide_executable() if was_running else None
    say(T("Закрытие IDE Antigravity…"))
    try:
        ide_local.stop_ide()
    except Exception as e:
        ide_local._ide_log("IDE не закрылась, возврат отменён:", str(e))
        raise
    say(T("Сохранение нынешних учётных данных…"))
    now = backup_ide_credentials()
    ide_local._ide_log("Нынешние данные сохранены копией:", now.get("timestamp"))
    say(T("Возврат учётных данных из копии…"))
    restore_ide_credentials(meta)
    ide_local._ide_log("Учётные данные возвращены")
    if was_running and exe_path:
        say(T("Запуск IDE Antigravity…"))
        ide_local.start_ide(exe_path)
    return meta


def ide_login_browser(on_status=None, timeout=300):
    """Запасной способ смены аккаунта IDE — через окно Google, без записи учётных данных
    (`python limits.py switch-ide --browser`). Метод IDE `Login` сам открывает в браузере
    «Вход – Google Аккаунты» и отвечает после входа. IDE должна быть запущена."""
    say = on_status or (lambda s: None)
    servers = ide_local.find_ide_servers()
    if not servers:
        raise RuntimeError(T("IDE Antigravity не запущена — откройте её и повторите"))
    srv, us = servers[0]
    before = (us or {}).get("email")
    ide_local._ide_log("вход через браузер; сейчас в IDE:", str(before), "порт", str(srv.port))
    if before:
        say(T("IDE: выход из текущего аккаунта…"))
        ide_local._ide_log("AuthLogout ->", srv.call("AuthLogout", {}))

    result = {}

    def login():
        # LoginWithBrowser в новых версиях IDE отключён («deprecated»), основной метод — Login
        try:
            for method in ("Login", "LoginWithBrowser"):
                try:
                    result["resp"] = srv.call(method, {}, timeout=timeout)
                    ide_local._ide_log(f"{method} ->", result["resp"])
                    return
                except Exception as e:
                    ide_local._ide_log(f"{method} ошибка:", str(e))
                    result["err"] = e
                    if not any(s in str(e) for s in ("deprecated", "404", "unimplemented")):
                        return
        finally:
            result["done"] = True

    threading.Thread(target=login, daemon=True).start()
    say(T("Выберите аккаунт в открывшемся окне Google…"))
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        try:
            cur = ide_local.ide_current_account()
        except Exception:
            cur = None
        if cur:
            ide_local._ide_log("вход выполнен:", cur)
            return cur
        if result.get("done"):  # IDE ответила (или отказала), а входа так и нет
            time.sleep(2)
            cur = ide_local.ide_current_account()
            if cur:
                ide_local._ide_log("вход выполнен:", cur)
                return cur
            err = result.get("err")
            raise RuntimeError(T("IDE не выполнила вход: {error}", error=err) if err and "resp" not in result
                               else T("IDE ответила, но вход не выполнен — войдите в самой IDE"))
    ide_local._ide_log("время ожидания вышло, вход не выполнен")
    raise RuntimeError(T("Вход не выполнен за 5 минут — войдите в самой IDE (журнал: {log})", log=ide_local.IDE_LOG))
