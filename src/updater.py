"""Проверка и загрузка обновлений AI Limits с GitHub Releases."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import version
import i18n
from i18n import T

REPO = "Biz2k/AI-Limits"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
CHECK_INTERVAL = 86400  # раз в сутки, с
TIMEOUT = 12


def parse_version(text):
    """'v1.5.8' -> (1, 5, 8); нечисловые суффиксы отбрасываются."""
    nums = [int(x) for x in re.findall(r"\d+", str(text or ""))]
    return tuple(nums) if nums else (0,)


def extract_sha256(notes):
    """Достаёт 64-символьный SHA-256 из текста заметок релиза (или None)."""
    m = re.search(r"\b([0-9a-fA-F]{64})\b", notes or "")
    return m.group(1).lower() if m else None


_LANG_HEAD_RE = re.compile(r"^#{1,3}\s*(?:.*\((EN|RU|UK)\)|(EN|RU|UK))\s*$", re.IGNORECASE)


def _pick_lang_section(notes, lang):
    """Если заметки релиза разбиты на секции по языкам (## ... (EN)/(RU)/(UK)), возвращает нужную."""
    sections = {}
    cur = None
    for raw in (notes or "").splitlines():
        s = raw.strip()
        if "SHA-256" in s.upper() or re.fullmatch(r"[0-9a-fA-F]{64}", s) or s.startswith("```"):
            break
        m = _LANG_HEAD_RE.match(s)
        if m:
            cur = (m.group(1) or m.group(2)).lower()
            sections.setdefault(cur, [])
            continue
        if cur is not None:
            sections[cur].append(raw)
    if not sections:
        return notes
    want = (lang or i18n.lang() or "en").lower()
    chosen = sections.get(want) or sections.get("en") or next(iter(sections.values()))
    return "\n".join(chosen)


def clean_notes(notes, lang=None, max_chars=480):
    """Выбирает заметки для текущего языка, убирает блок SHA-256 и лишнюю markdown-разметку."""
    if not notes:
        return ""
    body = _pick_lang_section(notes, lang)
    lines = []
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        if "SHA-256" in s.upper() or re.fullmatch(r"[0-9a-fA-F]{64}", s) or s.startswith("```"):
            break
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)
        if s.startswith("- "):
            s = "• " + s[2:]
        lines.append(s)
    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def _fetch_latest_json(timeout=TIMEOUT):
    req = urllib.request.Request(
        LATEST_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"AI-Limits/{version.__version__}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_latest(timeout=TIMEOUT):
    """Запрашивает последний релиз на GitHub и сравнивает с текущей версией."""
    data = _fetch_latest_json(timeout=timeout)
    tag = str(data.get("tag_name") or "").strip()
    latest = tag.lstrip("vV") or version.__version__
    body = str(data.get("body") or "")
    asset_url = asset_name = None
    for a in data.get("assets") or ():
        name = str(a.get("name") or "")
        if name.lower().endswith(".exe") and a.get("browser_download_url"):
            asset_url = a["browser_download_url"]
            asset_name = name
            break
    return {
        "current": version.__version__,
        "latest": latest,
        "tag": tag or f"v{latest}",
        "available": parse_version(latest) > parse_version(version.__version__),
        "notes": clean_notes(body),
        "raw_notes": body,
        "url": str(data.get("html_url") or RELEASES_URL),
        "asset_url": asset_url,
        "asset_name": asset_name,
        "sha256": extract_sha256(body),
        "checked_at": time.time(),
    }


def download_and_verify(asset_url, expected_sha256=None, dest_path=None, on_progress=None, timeout=60):
    """Скачивает exe во временный файл и проверяет SHA-256 (если задан). Возвращает путь к файлу."""
    if not dest_path:
        dest_path = os.path.join(tempfile.gettempdir(), f"ai_limits_new_{os.getpid()}.exe")
    req = urllib.request.Request(asset_url, headers={"User-Agent": f"AI-Limits/{version.__version__}"})
    h = hashlib.sha256()
    got = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest_path, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(got, total)
        digest = h.hexdigest().lower()
        if expected_sha256 and digest != expected_sha256.lower():
            raise RuntimeError(T("Контрольная сумма SHA-256 не совпала"))
        return dest_path
    except Exception:
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        raise


def apply_exe_update(new_exe, target_exe=None):
    """Запускает фоновый .cmd, который дожидается освобождения exe, заменяет его и запускает новый."""
    target = target_exe or (sys.executable if getattr(sys, "frozen", False) else None)
    if not target or not os.path.exists(new_exe):
        raise RuntimeError(T("Автообновление доступно только для собранного AI Limits.exe"))
    pid = os.getpid()
    bat = os.path.join(tempfile.gettempdir(), f"ai_limits_update_{pid}.cmd")
    # Без пайпов (tasklist | find): в оконном процессе (--windowed) без stdin/stdout/stderr пайп в cmd.exe падает.
    # Ждём 1 с и пробуем copy /Y в цикле, пока старый процесс и загрузчик PyInstaller не освободят exe.
    script = (
        "@echo off\r\n"
        "setlocal\r\n"
        'set "_MEIPASS2="\r\n'
        'set "_PYI_APPLICATION_HOME_DIR="\r\n'
        'set "_PYI_ARCHIVE_FILE="\r\n'
        'set "_PYI_PARENT_PROCESS_LEVEL="\r\n'
        'set "TCL_LIBRARY="\r\n'
        'set "TK_LIBRARY="\r\n'
        f'set "SRC={new_exe}"\r\n'
        f'set "DST={target}"\r\n'
        "ping -n 2 127.0.0.1 >nul\r\n"
        "for /L %%j in (1,1,30) do (\r\n"
        '  copy /Y "%SRC%" "%DST%" >nul 2>&1 && goto :ok\r\n'
        "  ping -n 2 127.0.0.1 >nul\r\n"
        ")\r\n"
        "goto :done\r\n"
        ":ok\r\n"
        'del /F /Q "%SRC%" >nul 2>&1\r\n'
        'start "" "%DST%"\r\n'
        ":done\r\n"
        'del /F /Q "%~f0" >nul 2>&1\r\n'
    )
    with open(bat, "w", encoding="cp866", errors="replace", newline="") as f:
        f.write(script)
    # Убираем переменные окружения PyInstaller (_MEIPASS2 и др.), иначе новый exe попытается
    # загрузить python313.dll из уже удалённой временной папки _MEI* старого процесса.
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("_MEIPASS", "_PYI_"))
           and k.upper() not in ("TCL_LIBRARY", "TK_LIBRARY")}
    if "PATH" in env:
        mei = getattr(sys, "_MEIPASS", "")
        if mei:
            env["PATH"] = os.pathsep.join(
                p for p in env["PATH"].split(os.pathsep) if os.path.normcase(p) != os.path.normcase(mei)
            )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        ["cmd.exe", "/c", bat],
        env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, close_fds=True,
    )
    return bat
