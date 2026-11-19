"""Смена аккаунта Claude Code (1.5.3): вход выбранного профиля Claude подставляется в вход самого Claude Code.

Вход Claude Code — два файла: ~/.claude/.credentials.json (поле claudeAiOauth — токены; рядом mcpOAuth и другое —
не трогаем) и ~/.claude.json (поле oauthAccount — email, организация; остальное — настройки и проекты — не трогаем).
Порядок: копия обоих (зашифрована) → нынешний вход — в профиль его аккаунта (аккаунт не добавлен — профиль создаётся,
на него можно вернуться) → запись входа профиля → проверка → при сбое прежний вход обратно.
Claude Code **не закрываем** (решение владельца 19.11.2026: в нём идут рабочие сеансы, в том числе с самим Claude).
Новые сеансы работают под выбранным аккаунтом, открытые — под прежним до перезапуска; открытый сеанс, обновляя
токен, может записать прежний вход обратно — об этом предупреждает окно подтверждения.
"""
import json
import os
import time
import uuid

import accounts
import storage
from i18n import T

KEEP_BACKUPS = 5


def config_path():
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def backups_dir():
    return os.path.join(storage.APPDIR, "claude_backups")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _profile_account(profile, data):
    """oauthAccount профиля: из его входа, иначе из .claude.json в его папке, иначе — только email и организация."""
    if data.get("oauthAccount"):
        return data["oauthAccount"]
    try:
        oa = (_load(accounts.profile_path(profile, ".claude.json")) or {}).get("oauthAccount")
        if oa:
            return oa
    except (OSError, ValueError):
        pass
    return {"emailAddress": profile["email"], "organizationUuid": profile.get("org")}


def backup(creds, config_account):
    d = backups_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, time.strftime("claude_%Y%m%d_%H%M%S.dat"))
    with open(path, "wb") as f:
        f.write(storage.protect_bytes(json.dumps({"credentials": creds, "oauthAccount": config_account}).encode()))
    for old in sorted(n for n in os.listdir(d) if n.startswith("claude_"))[:-KEEP_BACKUPS]:
        os.remove(os.path.join(d, old))
    return path


def _keep_current(oauth, account):
    """Нынешний вход Claude Code — в профиль его аккаунта. Возвращает (профиль, создан ли)."""
    email = (account or {}).get("emailAddress")
    if not email or not (oauth or {}).get("accessToken"):
        return None, False
    data = {"claudeAiOauth": oauth, "oauthAccount": account}
    key = accounts.ident("claude", email)
    for p in accounts.load_profiles():
        if p["kind"] == "claude" and accounts.ident("claude", p["email"]) == key:
            accounts.write_secret(p, data)
            return p, False
    p = {"kind": "claude", "dir": f"claude-{uuid.uuid4().hex[:8]}", "email": email,
         "org": account.get("organizationUuid")}
    os.makedirs(os.path.join(accounts.profiles_dir(), p["dir"]), exist_ok=True)
    accounts.write_secret(p, data)
    accounts.save_profiles(accounts.load_profiles() + [p])
    return p, True


def _write(oauth, account):
    """Записать токены и аккаунт, сохранив всё остальное в обоих файлах (перечитываются перед записью)."""
    creds = _load(storage.CLAUDE_CREDS) or {}
    creds["claudeAiOauth"] = oauth
    os.makedirs(os.path.dirname(storage.CLAUDE_CREDS), exist_ok=True)
    storage.atomic_write_json(storage.CLAUDE_CREDS, creds)
    cfg = _load(config_path()) or {}
    cfg["oauthAccount"] = account
    storage.atomic_write_json(config_path(), cfg)


def switch(profile, on_status=lambda s: None):
    """Сделать профиль Claude аккаунтом Claude Code. Возвращает {"email", "kept", "created"}."""
    target = accounts.read_secret(profile)
    t_oauth = target.get("claudeAiOauth") or {}
    if not t_oauth.get("accessToken"):
        raise RuntimeError(T("вход профиля потерян — удалите аккаунт и добавьте заново"))
    t_account = _profile_account(profile, target)
    t_email = t_account.get("emailAddress") or profile["email"]
    creds, cfg = _load(storage.CLAUDE_CREDS) or {}, _load(config_path()) or {}
    cur_oauth, cur_account = creds.get("claudeAiOauth"), cfg.get("oauthAccount")
    if (cur_account or {}).get("emailAddress", "").lower() == t_email.lower():
        return {"email": t_email, "kept": None, "created": False}
    backup(creds, cur_account)
    kept, created = _keep_current(cur_oauth, cur_account)
    on_status(T("Claude: записываю вход…"))
    try:
        _write(t_oauth, t_account)
        got = (_load(config_path()) or {}).get("oauthAccount") or {}
        tok = ((_load(storage.CLAUDE_CREDS) or {}).get("claudeAiOauth") or {}).get("accessToken")
        if (got.get("emailAddress") or "").lower() != t_email.lower() or tok != t_oauth["accessToken"]:
            raise RuntimeError(T("в Claude Code записался {now}, а не {email}",
                                 now=got.get("emailAddress") or T("никто"), email=t_email))
    except Exception:
        if cur_oauth is not None or cur_account is not None:
            _write(cur_oauth, cur_account)
        raise
    return {"email": t_email, "kept": kept, "created": created}
