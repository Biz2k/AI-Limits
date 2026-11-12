"""Запущенная IDE Antigravity: её локальный сервер, лимиты из IDE, запуск и закрытие."""
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import cloud
import storage
from i18n import T
import winapi


def ide_version():
    """Версия установленной IDE Antigravity (из свойств Antigravity.exe) или None."""
    exe = ide_installed()
    return winapi._file_version(exe) if exe else None


def _ide_pids():
    """PID процессов Antigravity.exe."""
    return [pid for pid, name in winapi._win_processes() if name.lower() == "antigravity.exe"]


def _ide_ls_processes():
    """Процессы language_server: [{"id", "cmd"}] (всех IDE на этом движке; cmd = None, если недоступна)."""
    return [{"id": pid, "cmd": winapi._win_process_text(pid, "cmd")}
            for pid, name in winapi._win_processes() if name.lower().startswith("language_server")]


_IDE_PORTS = {}  # {pid language_server: (csrf, порт, схема)} — найденный порт сервера IDE, пока жив процесс


class IdeServer:
    """Локальный сервер запущенной IDE Antigravity (language_server)."""

    def __init__(self, port, csrf):
        import ssl
        self.port, self.csrf = port, csrf
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.scheme = None

    def call(self, method, body=None, timeout=8):
        hdr = {"X-Codeium-Csrf-Token": self.csrf, "Connect-Protocol-Version": "1",
               "Content-Type": "application/json"}
        for scheme in ([self.scheme] if self.scheme else ["https", "http"]):
            url = f"{scheme}://127.0.0.1:{self.port}/exa.language_server_pb.LanguageServerService/{method}"
            req = urllib.request.Request(url, data=json.dumps(body or {}).encode(), headers=hdr)
            try:
                with urllib.request.urlopen(req, timeout=timeout,
                                            context=self.ctx if scheme == "https" else None) as r:
                    self.scheme = scheme
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if self.scheme:
                    raise RuntimeError(f"IDE {method}: HTTP {e.code} {e.read()[:200]!r}") from None
            except Exception:
                if self.scheme:
                    raise
        return None

    def status(self):
        return self.call("GetUserStatus", {"metadata": {"ideName": "antigravity",
                                                        "extensionName": "antigravity", "locale": "en"}})


def find_ide_servers(diag=None):
    """Серверы запущенных IDE Antigravity: [(IdeServer, userStatus | None)].
    diag — необязательный список: в него дописываются строки о том, что найдено (для журнала смены аккаунта).
    Порт, на котором сервер ответил, запоминается в _IDE_PORTS и в следующий раз проверяется первым."""
    if os.name != "nt":
        return []
    import re
    note = diag.append if diag is not None else (lambda text: None)
    try:
        procs = _ide_ls_processes()
    except Exception as e:
        note(f"список процессов не получен ({type(e).__name__}: {str(e)[:60]})")
        return []
    if not procs:
        note("процессов language_server нет")
    for pid in [p for p in _IDE_PORTS if p not in {x["id"] for x in procs}]:
        del _IDE_PORTS[pid]  # процесс завершился
    found, foreign, table = [], 0, None
    for p in procs:
        pid, cmd = p["id"], p["cmd"] or ""
        m = re.search(r"--csrf_token[ =](\S+)", cmd)
        if not cmd:
            note(f"процесс {pid}: командная строка недоступна")
            continue
        if not m or "--override_ide_name antigravity" not in cmd:
            foreign += 1
            continue
        csrf, seen = m.group(1), []
        known = _IDE_PORTS.get(pid)
        if known and known[0] == csrf:  # порт известен с прошлого раза — таблицу соединений не читаем
            srv = IdeServer(known[1], csrf)
            srv.scheme = known[2]
            try:
                st = srv.status()
            except Exception:
                st = None
            if st is not None:
                us = (st or {}).get("userStatus")
                note(f"процесс {pid}: {known[1]} — " + (f"вход {us['email']}" if us and us.get("email") else "входа нет"))
                found.append((srv, us))
                continue
            _IDE_PORTS.pop(pid, None)
        if table is None:
            try:
                table = winapi._win_local_ports()
            except Exception as e:
                note(f"порты не получены ({type(e).__name__})")
                table = {}
        for port in table.get(pid, []):
            srv = IdeServer(port, csrf)
            try:
                st = srv.status()
                why = "не отвечает"
            except Exception as e:
                st, why = None, f"ошибка {type(e).__name__}: {str(e)[:60]}"
            if st is not None:
                us = (st or {}).get("userStatus")
                seen.append(f"{port} — " + (f"вход {us['email']}" if us and us.get("email") else "входа нет"))
                found.append((srv, us))
                _IDE_PORTS[pid] = (csrf, port, srv.scheme)
                break
            seen.append(f"{port} — {why}")
        note(f"процесс {pid}: " + ("; ".join(seen) if seen else "портов на 127.0.0.1 нет"))
    if foreign and foreign == len(procs):
        note(f"language_server есть ({foreign}), но не от Antigravity")
    return found


def local_ide_info():
    """Состояние запущенных IDE Antigravity:
    {"running": bool, "email": str|None, "accounts": {email: {"rows", "plan"}}}."""
    info = {"running": False, "email": None, "accounts": {}}
    for srv, us in find_ide_servers():
        info["running"] = True
        email = (us or {}).get("email")
        if not email:
            continue
        info["email"] = info["email"] or email
        try:
            summ = srv.call("RetrieveUserQuotaSummary", {"forceRefresh": True})
        except Exception:
            summ = None
        rows = cloud._summary_rows((summ or {}).get("response"))
        plan = (us.get("userTier") or {}).get("name") or \
            ((us.get("planStatus") or {}).get("planInfo") or {}).get("planName", "")
        if rows:
            info["accounts"][email.lower()] = {"rows": rows, "plan": plan}
    return info


def local_ide_quota():
    """{email: {"rows", "plan"}} от запущенных IDE Antigravity."""
    return local_ide_info()["accounts"]


def ide_current_account():
    for _, us in find_ide_servers():
        if us and us.get("email"):
            return us["email"]
    return None


IDE_LOG = os.path.join(storage.APPDIR, "ide_switch.log")


def _ide_log(*parts):
    """Журнал смены аккаунта IDE (длинные строки, похожие на токены, скрываются)."""
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        if isinstance(o, str) and len(o) > 80 and not o.startswith("http"):
            return f"<строка {len(o)} симв.>"
        return o
    try:
        os.makedirs(storage.APPDIR, exist_ok=True)
        with open(IDE_LOG, "a", encoding="utf-8") as f:
            text = " ".join(p if isinstance(p, str) else json.dumps(clean(p), ensure_ascii=False)
                            for p in parts)
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
    except Exception:
        pass
_IDE_EXE = None       # найденный путь к Antigravity.exe (кэш)


def _ide_exe_standard():
    """Antigravity.exe в стандартных местах установки (быстро, без запуска процессов)."""
    for p in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Antigravity", "Antigravity.exe"),
              os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Antigravity", "Antigravity.exe")):
        if os.path.exists(p):
            return p
    return None


def ide_installed():
    """Быстрая проверка для интерфейса: известен ли путь к Antigravity.exe (PowerShell не запускает)."""
    return _IDE_EXE or _ide_exe_standard()


def find_ide_executable():
    """Путь к Antigravity.exe (из работающего процесса или стандартных мест установки)."""
    global _IDE_EXE
    if os.name != "nt":
        return None
    try:
        for pid in _ide_pids():
            path = winapi._win_process_text(pid, "path")
            if path and path.lower().endswith("antigravity.exe") and os.path.exists(path):
                _IDE_EXE = path
                return path
    except Exception:
        pass
    return _IDE_EXE if _IDE_EXE and os.path.exists(_IDE_EXE) else _ide_exe_standard()


def _ide_running():
    """Есть ли процессы Antigravity.exe."""
    try:
        return bool(_ide_pids())
    except Exception:
        return False


def _ide_ls_pids():
    """PID процессов language_server именно IDE Antigravity (другие IDE на том же движке не трогаем)."""
    try:
        return [p["id"] for p in _ide_ls_processes() if "--override_ide_name antigravity" in (p["cmd"] or "")]
    except Exception:
        return []


def _ide_window_count():
    """Число процессов Antigravity с открытым окном; None, если узнать не удалось."""
    try:
        return len(set(_ide_pids()) & winapi._win_window_pids())
    except Exception:
        return None


def _ide_open():
    """Открыта ли IDE у пользователя: есть окно Antigravity. Фоновый процесс без окна (остаётся после закрытия
    IDE) открытой IDE не считается. Если число окон узнать не удалось — по наличию процесса."""
    n = _ide_window_count()
    return _ide_running() if n is None else n > 0


def stop_ide(timeout=10):
    """Закрывает IDE Antigravity: штатно просит окна закрыться (taskkill без /F). Пока окно открыто
    (например, IDE спрашивает о несохранённых файлах), принудительно её не завершаем — через timeout секунд
    RuntimeError, учётные данные при этом ещё не тронуты. Когда окно закрылось, оставшиеся фоновые процессы
    Antigravity.exe (после закрытия окна они остаются висеть) и её language_server завершаются принудительно."""
    if os.name != "nt":
        return
    if _ide_running():
        failed = RuntimeError(T("Antigravity не закрылся за {timeout} с", timeout=timeout))
        try:  # taskkill без /F шлёт WM_CLOSE окнам IDE
            winapi._run_hidden(["taskkill", "/IM", "Antigravity.exe"], timeout=10)
        except Exception:
            pass
        deadline = time.time() + timeout
        while _ide_running():
            if _ide_window_count() == 0:  # окно закрыто — остались только фоновые процессы
                time.sleep(1)
                if _ide_running():
                    try:
                        winapi._run_hidden(["taskkill", "/F", "/T", "/IM", "Antigravity.exe"], timeout=10)
                    except Exception:
                        pass
                    time.sleep(0.7)
                if _ide_running():
                    raise failed
                break
            if time.time() > deadline:
                raise failed
            time.sleep(0.5)
    # language_server обычно выходит сам вслед за IDE; оставшихся (данных пользователя в них нет) завершаем
    pids = _ide_ls_pids()
    if pids:
        time.sleep(2)
        for pid in _ide_ls_pids():
            try:
                winapi._run_hidden(["taskkill", "/F", "/PID", str(pid)], timeout=5)
            except Exception:
                pass
    time.sleep(0.8)


def start_ide(exe_path=None):
    """Запускает Antigravity.exe в фоновом режиме (detached)."""
    if os.name != "nt":
        return None
    import subprocess
    exe = exe_path or find_ide_executable()
    if not exe or not os.path.exists(exe):
        raise RuntimeError(T("Исполняемый файл IDE Antigravity не найден: {exe}", exe=exe))
    # 0x00000008 = DETACHED_PROCESS, 0x00000200 = CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen([exe], creationflags=0x00000008 | 0x00000200, close_fds=True)
