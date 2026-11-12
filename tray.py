"""Иконка в системном трее Windows на чистом ctypes (без сторонних пакетов).

Работает в своём потоке со своим скрытым окном и циклом сообщений.
События (клик, пункт меню) отдаются через callback — вызывающий сам
переносит их в поток Tk (например, через queue + root.after).
"""
import ctypes
import threading
from ctypes import wintypes as W

u32 = ctypes.WinDLL("user32", use_last_error=True)
sh32 = ctypes.WinDLL("shell32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

WM_DESTROY, WM_CLOSE, WM_COMMAND, WM_USER = 0x0002, 0x0010, 0x0111, 0x0400
WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
WM_TRAY = WM_USER + 20
WM_APP_UPDATE = WM_USER + 21
WM_APP_SHOW = WM_USER + 22
WM_APP_ICON = WM_USER + 23  # wParam: 1 показать иконку, 0 убрать
CLASS_NAME = "AILimitsTrayWnd"


def activate_running_instance():
    """True, если программа уже запущена (тогда просим её показать окно)."""
    k32.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
    k32.CreateMutexW.restype = W.HANDLE
    globals()["_mutex"] = k32.CreateMutexW(None, False, "AILimits.SingleInstance")
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return False
    u32.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
    u32.FindWindowW.restype = W.HWND
    h = u32.FindWindowW(CLASS_NAME, None)
    if h:
        u32.PostMessageW(h, WM_APP_SHOW, 0, 0)
    return True
NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIN_POPUPOPEN, NIN_POPUPCLOSE = 0x406, 0x407
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x80
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
MF_STRING, MF_SEPARATOR = 0x0, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80


class GUID(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", W.HICON)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                ("lpszClassName", W.LPCWSTR)]


u32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u32.DefWindowProcW.restype = LRESULT
u32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
u32.CreateWindowExW.restype = W.HWND
u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
u32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
u32.LoadImageW.restype = W.HANDLE
u32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u32.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.LPVOID]
u32.AppendMenuW.argtypes = [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR]
u32.CreatePopupMenu.restype = W.HMENU
u32.DestroyMenu.argtypes = [W.HMENU]
u32.SetForegroundWindow.argtypes = [W.HWND]
u32.RegisterWindowMessageW.argtypes = [W.LPCWSTR]
sh32.Shell_NotifyIconW.argtypes = [W.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
k32.GetModuleHandleW.restype = W.HMODULE


class TrayIcon:
    """TrayIcon(ico_path, tip, on_click, menu=[(id, title) | None], on_menu)."""

    def __init__(self, ico_path, tip, on_click, menu, on_menu, visible=False, on_hover=None, on_rclick=None):
        """on_hover(True/False) — своё всплывающее окно вместо стандартной подсказки.
        on_rclick(x, y) — своё меню по правому щелчку (координаты курсора) вместо системного."""
        self.ico_path, self.tip = ico_path, tip
        self.on_hover = on_hover
        self.on_rclick = on_rclick
        self.visible = visible
        self.on_click, self.menu, self.on_menu = on_click, menu, on_menu
        self.hwnd = None
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(5)

    # -------------------------------------------------- публичное (из любого потока)
    def set_tip(self, text):
        self.tip = text[:127]
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    def show(self):
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_APP_ICON, 1, 0)

    def hide(self):
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_APP_ICON, 0, 0)

    def icon_rect(self):
        """(left, top, right, bottom) иконки на экране или None."""
        if not self.hwnd or not self.visible:
            return None

        class NOTIFYICONIDENTIFIER(ctypes.Structure):
            _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("guidItem", GUID)]
        ni = NOTIFYICONIDENTIFIER()
        ni.cbSize = ctypes.sizeof(ni)
        ni.hWnd, ni.uID = self.hwnd, 1
        r = W.RECT()
        if sh32.Shell_NotifyIconGetRect(ctypes.byref(ni), ctypes.byref(r)) != 0:
            return None
        return r.left, r.top, r.right, r.bottom

    def stop(self):
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # -------------------------------------------------- поток трея
    def _nid(self, flags):
        n = NOTIFYICONDATAW()
        n.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        n.hWnd, n.uID, n.uFlags = self.hwnd, 1, flags
        n.uCallbackMessage = WM_TRAY
        n.hIcon = self.hicon
        n.szTip = self.tip[:127]
        return n

    def _add(self):
        flags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        if not self.on_hover:
            flags |= NIF_SHOWTIP
        n = self._nid(flags)
        sh32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(n))
        if self.on_hover:  # версия 4: события NIN_POPUPOPEN/CLOSE при наведении
            n.uVersion = 4
            sh32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(n))

    def _popup(self):
        m = u32.CreatePopupMenu()
        for item in self.menu:
            if item is None:
                u32.AppendMenuW(m, MF_SEPARATOR, 0, None)
            else:
                u32.AppendMenuW(m, MF_STRING, item[0], item[1])
        pt = W.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self.hwnd)
        cmd = u32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                 pt.x, pt.y, 0, self.hwnd, None)
        u32.DestroyMenu(m)
        if cmd:
            self.on_menu(cmd)

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == WM_TRAY:
            ev = lp & 0xFFFF
            if ev == NIN_POPUPOPEN and self.on_hover:
                self.on_hover(True)
            elif ev == NIN_POPUPCLOSE and self.on_hover:
                self.on_hover(False)
            elif ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                if self.on_hover:
                    self.on_hover(False)
                self.on_click()
            elif ev == WM_RBUTTONUP:
                if self.on_hover:
                    self.on_hover(False)
                if self.on_rclick:
                    pt = W.POINT()
                    u32.GetCursorPos(ctypes.byref(pt))
                    self.on_rclick(pt.x, pt.y)
                else:
                    self._popup()
            return 0
        if msg == WM_APP_SHOW:  # второй запуск просит показать окно
            self.on_menu(1)
            return 0
        if msg == WM_APP_ICON:
            if wp and not self.visible:
                self._add()
            elif not wp and self.visible:
                sh32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid(0)))
            self.visible = bool(wp)
            return 0
        if msg == WM_APP_UPDATE:
            if not self.visible:
                return 0
            n = self._nid(NIF_TIP | (0 if self.on_hover else NIF_SHOWTIP))
            sh32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(n))
            return 0
        if msg == self._taskbar_created:  # Проводник перезапустился — вернуть иконку
            if self.visible:
                self._add()
            return 0
        if msg == WM_CLOSE:
            if self.visible:
                sh32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid(0)))
            u32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    def _run(self):
        hinst = k32.GetModuleHandleW(None)
        self._proc = WNDPROC(self._wndproc)  # держим ссылку, иначе GC
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = CLASS_NAME
        u32.RegisterClassW(ctypes.byref(wc))
        self._taskbar_created = u32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = u32.CreateWindowExW(0, wc.lpszClassName, "AI Limits tray", 0,
                                        0, 0, 0, 0, None, None, hinst, None)
        self.hicon = u32.LoadImageW(None, self.ico_path, IMAGE_ICON, 0, 0,
                                    LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if self.visible:
            self._add()
        self._ready.set()
        msg = W.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
