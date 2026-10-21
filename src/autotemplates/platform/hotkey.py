"""One system-wide hotkey through ``RegisterHotKey`` (no keyboard hook).

``RegisterHotKey`` does not observe other keystrokes (unlike low-level hooks,
which security tools flag) and fails cleanly when another program already owns
the combination, so the settings can report the conflict.
Registration and the message loop must share one thread, so the listener owns
a small dedicated thread.
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN, "meta": MOD_WIN}
_NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pageup": 0x21, "pgdown": 0x22, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "pause": 0x13,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE,
    ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC, "+": 0xBB,
}


@dataclass(frozen=True)
class Hotkey:
    modifiers: int
    vk: int
    text: str

    @classmethod
    def parse(cls, text: str) -> "Hotkey":
        """``"Ctrl+Q"``, ``"Ctrl+Alt+Space"``, ``"Win+Shift+F2"`` … (case-insensitive)."""
        parts = [p.strip() for p in text.replace(" ", "").split("+") if p.strip()]
        if text.strip().endswith("++"):
            parts.append("+")
        if not parts:
            raise ValueError("empty hotkey")
        *mods, key = parts
        modifiers = 0
        for mod in mods:
            if mod.lower() not in _MODS:
                raise ValueError(f"unknown modifier: {mod}")
            modifiers |= _MODS[mod.lower()]
        vk = key_code(key)
        if not modifiers and not (0x70 <= vk <= 0x87):
            raise ValueError("a hotkey needs Ctrl, Alt, Shift or Win (or a function key)")
        return cls(modifiers, vk, "+".join([*(m.capitalize() for m in mods), key.upper() if len(key) == 1 else key.capitalize()]))


def key_code(key: str) -> int:
    k = key.lower()
    if len(k) == 1 and ("a" <= k <= "z" or "0" <= k <= "9"):
        return ord(k.upper())
    if k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        return 0x6F + int(k[1:])
    if k in _NAMED_KEYS:
        return _NAMED_KEYS[k]
    raise ValueError(f"unknown key: {key}")


class HotkeyListener:
    """Calls ``on_hotkey`` (on the listener thread) when the registered hotkey is pressed."""

    ID = 0xA7E1

    def __init__(self, on_hotkey: Callable[[], None]) -> None:
        self._on_hotkey = on_hotkey
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._result: tuple[threading.Event, list[bool]] | None = None

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def register(self, hotkey: Hotkey) -> bool:
        """(Re)registers ``hotkey``; ``False`` when another program owns it."""
        self.stop()
        if not self.supported:
            return False
        done, result = threading.Event(), [False]
        self._thread = threading.Thread(target=self._run, args=(hotkey, done, result), name="hotkey", daemon=True)
        self._thread.start()
        done.wait(2.0)
        if not result[0]:
            self.stop()
        return result[0]

    def stop(self) -> None:
        if self._thread is None:
            return
        import ctypes

        ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        self._thread.join(2.0)
        self._thread = None

    def _run(self, hotkey: Hotkey, done: threading.Event, result: list[bool]) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # creates the message queue
        self._thread_id = kernel32.GetCurrentThreadId()
        ok = bool(user32.RegisterHotKey(None, self.ID, hotkey.modifiers | MOD_NOREPEAT, hotkey.vk))
        if not ok:
            log.warning("RegisterHotKey(%s) failed, Win32 error %d", hotkey.text, ctypes.get_last_error())
        result[0] = ok
        done.set()
        if not ok:
            return
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam == self.ID:  # WM_HOTKEY
                    try:
                        self._on_hotkey()
                    except Exception:  # noqa: BLE001
                        log.exception("Hotkey handler failed")
        finally:
            user32.UnregisterHotKey(None, self.ID)
