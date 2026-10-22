"""Small Win32 helpers: the target window, focus, caret position and synthetic keys.

Everything degrades to a no-op on other platforms so the core and UI can be
tested anywhere.
"""

from __future__ import annotations

import logging
import sys
import time

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
VK_V, VK_LEFT, VK_Q = 0x56, 0x25, 0x51
KEYEVENTF_KEYUP = 0x0002

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                    ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                    ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0) if IS_WINDOWS else 0


def window_title(hwnd: int) -> str:
    if not IS_WINDOWS or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def is_own_window(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == kernel32.GetCurrentProcessId()


def focus_window(hwnd: int) -> bool:
    """Brings ``hwnd`` to the front; uses AttachThreadInput when Windows refuses."""
    if not IS_WINDOWS or not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.SetForegroundWindow(hwnd):
        return True
    target = user32.GetWindowThreadProcessId(hwnd, None)
    current = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(current, target, True)
    try:
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        user32.AttachThreadInput(current, target, False)


def caret_position(hwnd: int) -> tuple[int, int, int] | None:
    """Screen (x, bottom, height) of the text caret in ``hwnd``'s thread, when the app exposes one."""
    if not IS_WINDOWS or not hwnd:
        return None
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    thread = user32.GetWindowThreadProcessId(hwnd, None)
    if not user32.GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.hwndCaret:
        return None
    rc = info.rcCaret
    if rc.right == 0 and rc.bottom == 0:
        return None
    pt = wintypes.POINT(rc.left, rc.bottom)
    user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
    return pt.x, pt.y, max(1, rc.bottom - rc.top)


def _key(vk: int, up: bool = False) -> "INPUT":
    inp = INPUT(type=1)
    inp.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP if up else 0, time=0, dwExtraInfo=0)
    return inp


def _send(events: list) -> None:
    arr = (INPUT * len(events))(*events)
    user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))


def release_modifiers(timeout: float = 0.6) -> None:
    """Waits for Ctrl/Shift/Alt/Win to be released, then lifts any that are still down.

    Shift held from Shift+Enter would turn our Ctrl+V into Ctrl+Shift+V (paste
    special) in many programs.
    """
    if not IS_WINDOWS:
        return
    mods = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in mods):
        time.sleep(0.015)
    still = [vk for vk in mods if user32.GetAsyncKeyState(vk) & 0x8000]
    if still:
        _send([_key(vk, up=True) for vk in still])


def send_paste() -> None:
    if IS_WINDOWS:
        _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, True), _key(VK_CONTROL, True)])


def send_left(count: int) -> None:
    """Moves the caret back ``count`` characters (the ``{cursor}`` variable)."""
    if IS_WINDOWS and count > 0:
        events = []
        for _ in range(min(count, 5000)):
            events += [_key(VK_LEFT), _key(VK_LEFT, True)]
        _send(events)


def process_name(hwnd: int) -> str:
    """Executable name (lower case) of the process owning ``hwnd``."""
    if not IS_WINDOWS or not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def class_name(hwnd: int) -> str:
    if not IS_WINDOWS or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


# Windows that cannot receive a template: the taskbar/tray, the desktop, the DevPilot hub.
_NO_TARGET_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow", "Progman", "WorkerW",
                      "TopLevelWindowForOverflowXamlIsland", "Windows.UI.Core.CoreWindow"}
_NO_TARGET_PROCESSES = {"devpilot.exe", "devpilot.ui.exe"}


def can_receive(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    return class_name(hwnd) not in _NO_TARGET_CLASSES and process_name(hwnd) not in _NO_TARGET_PROCESSES