"""Прямые вызовы Windows через ctypes: процессы, порты, окна, версия файла, диспетчер учётных данных."""
import os


def _file_version(path):
    """Версия exe-файла из его свойств: (2, 31, 2) или None."""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(wintypes.UINT)]
        ver.VerQueryValueW.restype = wintypes.BOOL
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)) or n.value < 16:
            return None
        info = (wintypes.DWORD * 4).from_address(ptr.value)  # подпись, версия структуры, старшая и младшая части
        return (info[2] >> 16, info[2] & 0xFFFF, info[3] >> 16)
    except Exception:
        return None


# ---------------------------------------------------------------- Windows: процессы, окна, порты
# Прямые вызовы Windows через ctypes (раньше для этого каждый раз запускался PowerShell — 0,3–0,7 с на вызов).
def _win_processes():
    """Все процессы: [(pid, имя exe)]."""
    import ctypes
    from ctypes import wintypes

    class ENTRY(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, ctypes.c_void_p(-1).value):
        raise OSError("список процессов недоступен")
    out = []
    try:
        e = ENTRY()
        e.dwSize = ctypes.sizeof(ENTRY)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.szExeFile))
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return out


def _win_process_text(pid, what):
    """Командная строка (what="cmd") или полный путь exe (what="path") процесса; None, если недоступно."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        if what == "path":
            k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
            buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
            return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None

        class USTR(ctypes.Structure):
            _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]

        nt = ctypes.WinDLL("ntdll")
        nt.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                                 ctypes.POINTER(wintypes.ULONG)]
        nt.NtQueryInformationProcess.restype = ctypes.c_long
        buf, n = ctypes.create_string_buffer(70000), wintypes.ULONG()
        if nt.NtQueryInformationProcess(h, 60, buf, len(buf), ctypes.byref(n)) != 0:  # 60 — командная строка
            return None
        us = USTR.from_buffer(buf)
        return ctypes.wstring_at(us.Buffer, us.Length // 2) if us.Buffer else ""
    finally:
        k.CloseHandle(h)


def _win_local_ports():
    """Порты TCP на 127.0.0.1 по процессам: {pid: [порты]}, слушающие — первыми."""
    import ctypes
    import socket
    from ctypes import wintypes
    ip = ctypes.WinDLL("iphlpapi")
    ip.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                                       wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    ip.GetExtendedTcpTable.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    ip.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0)  # 2 — IPv4, 5 — все соединения с PID
    for _ in range(4):
        buf = ctypes.create_string_buffer(size.value + 4096)
        size = wintypes.DWORD(len(buf))
        if ip.GetExtendedTcpTable(buf, ctypes.byref(size), False, 2, 5, 0) == 0:
            break
    else:
        raise OSError("таблица соединений недоступна")
    count = wintypes.DWORD.from_buffer(buf).value
    rows = (wintypes.DWORD * (count * 6)).from_buffer(buf, 4)  # состояние, адрес, порт, адрес, порт, PID
    listen, other = {}, {}
    for i in range(count):
        state, addr, port, pid = rows[i * 6], rows[i * 6 + 1], rows[i * 6 + 2], rows[i * 6 + 5]
        if addr != 0x0100007F:  # 127.0.0.1
            continue
        lst = (listen if state == 2 else other).setdefault(pid, [])
        p = socket.ntohs(port & 0xFFFF)
        if p not in lst:
            lst.append(p)
    return {pid: sorted(listen.get(pid, [])) + sorted(x for x in other.get(pid, []) if x not in listen.get(pid, []))
            for pid in set(listen) | set(other)}


def _win_window_pids():
    """PID процессов, у которых есть видимое главное окно (верхнего уровня, без владельца)."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL("user32")
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindow.restype = wintypes.HWND
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pids = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4):  # 4 — GW_OWNER
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pids.add(pid.value)
        return True

    u.EnumWindows.argtypes = [type(each), wintypes.LPARAM]
    u.EnumWindows(each, 0)
    return pids


def _wincred():
    """advapi32 и структура CREDENTIAL. Блоб — указатель на байты (не c_char_p: в нём могут быть нули)."""
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ('Flags', wintypes.DWORD),
            ('Type', wintypes.DWORD),
            ('TargetName', wintypes.LPWSTR),
            ('Comment', wintypes.LPWSTR),
            ('LastWritten', wintypes.FILETIME),
            ('CredentialBlobSize', wintypes.DWORD),
            ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
            ('Persist', wintypes.DWORD),
            ('AttributeCount', wintypes.DWORD),
            ('Attributes', ctypes.c_void_p),
            ('TargetAlias', wintypes.LPWSTR),
            ('UserName', wintypes.LPWSTR),
        ]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    adv.CredFree.restype = None
    return ctypes, adv, CREDENTIAL


def _wincred_read(target):
    """Чтение записи Windows Credential Manager (CRED_TYPE_GENERIC). Возвращает dict или None."""
    if os.name != "nt":
        return None
    ctypes, adv, CREDENTIAL = _wincred()
    pcred = ctypes.POINTER(CREDENTIAL)()
    if not adv.CredReadW(target, 1, 0, ctypes.byref(pcred)):
        return None
    try:
        c = pcred.contents
        size = c.CredentialBlobSize
        return {
            "target": c.TargetName,
            "user": c.UserName,
            "type": c.Type,
            "persist": c.Persist,
            "blob": ctypes.string_at(c.CredentialBlob, size) if size else b"",
        }
    finally:
        adv.CredFree(pcred)


def _wincred_write(target, user, blob_bytes, persist=2):
    """Запись в Windows Credential Manager (CRED_TYPE_GENERIC = 1, CRED_PERSIST_LOCAL_MACHINE = 2)."""
    if os.name != "nt":
        return False
    ctypes, adv, CREDENTIAL = _wincred()
    buf = (ctypes.c_ubyte * len(blob_bytes)).from_buffer_copy(blob_bytes)
    cred = CREDENTIAL()
    cred.Type = 1
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob_bytes)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = persist
    cred.UserName = user
    if not adv.CredWriteW(ctypes.byref(cred), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return True


def _wincred_delete(target):
    """Удаление записи Credential Manager; False, если её не было."""
    if os.name != "nt":
        return False
    _, adv, _ = _wincred()
    return bool(adv.CredDeleteW(target, 1, 0))


def _run_hidden(args, timeout=8):
    import subprocess
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
