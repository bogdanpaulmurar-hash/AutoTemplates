"""Settings stored as JSON; every behaviour is configurable from the UI."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from autotemplates.core.paths import default_library_dir

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "library_dir": "",  # empty = Documents\AutoTemplates
    "hotkey": "Ctrl+Q",
    "noteit_hotkey": "Ctrl+Alt+N",
    "noteit_stay_on_top": True,
    "noteit_folder": "Notes",  # library sub-folder where notes are saved
    "noteit_last_dir": "",  # last "Other location..." folder
    "noteit_onenote_section": "",  # OneNote section ID used last
    "launcher_enabled": True,
    "language": "ro",  # ro | en
    "theme": "dark",  # dark | light
    "start_with_windows": True,
    "insert_mode": "rich",  # rich | plain (Enter); Shift+Enter is the other one
    "restore_clipboard": True,
    "paste_delay_ms": 60,  # time for the target window to take the focus back
    "restore_delay_ms": 800,  # time for the target to read the clipboard before it is restored
    "picker_width": 720,
    "picker_height": 440,
    "picker_show_preview": True,
    "picker_sort": "smart",  # smart (favourites, use count, recent) | name
    "picker_group_categories": False,
    "stats_keep_days": 30,  # statistics of deleted templates are kept this long (restore from the Recycle Bin)
    "editor_font_family": "Segoe UI",
    "editor_font_size": 11,
    "code_font_family": "Cascadia Mono",
    "code_font_size": 10,
    "code_style": "default",  # Pygments style used when code is inserted
    "code_background": "#f6f8fa",
    "date_format": "%d.%m.%Y",
    "time_format": "%H:%M",
}


class Settings:
    def __init__(self, path: Path, library_dir: Path | None = None) -> None:
        self.path = Path(path)
        self._default_library = library_dir
        self._values: dict[str, Any] = dict(DEFAULTS)
        self._listeners: list[Callable[[str, Any], None]] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in DEFAULTS:
                        self._values[key] = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            log.exception("Settings file is unreadable; defaults are used: %s", self.path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._values, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        if key not in DEFAULTS:
            self._values[key] = value
        elif self._values.get(key) == value:
            return
        else:
            self._values[key] = value

        if save:
            self.save()
        for listener in list(self._listeners):
            try:
                listener(key, value)
            except Exception:  # noqa: BLE001
                log.exception("Settings listener failed for %s", key)

    def update(self, values: dict[str, Any]) -> None:
        changed = {k: v for k, v in values.items() if self._values.get(k) != v}
        for key, value in changed.items():
            self.set(key, value, save=False)
        if changed:
            self.save()

    def add_listener(self, fn: Callable[[str, Any], None]) -> None:
        self._listeners.append(fn)

    def subscribe(self, fn: Callable[[str, Any], None]) -> None:
        """Alias for add_listener."""
        self.add_listener(fn)

    @property
    def library_dir(self) -> Path:
        value = str(self.get("library_dir") or "").strip()
        if value:
            return Path(os.path.expandvars(os.path.expanduser(value)))
        if self._default_library is not None:
            return Path(self._default_library)
        return default_library_dir()

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)
