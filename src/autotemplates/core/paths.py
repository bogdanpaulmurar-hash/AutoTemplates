"""Where AutoTemplates keeps its own files.

* ``data_dir`` (``%LOCALAPPDATA%\\AutoTemplates``): settings, index cache,
  usage statistics, logs, the instance key. Per machine, never synced.
* The template library is a separate folder chosen in the settings
  (default ``Documents\\AutoTemplates``); it can live in Google Drive/OneDrive.

``AUTOTEMPLATES_HOME`` overrides ``data_dir`` (portable use and tests).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def default_data_dir() -> Path:
    override = os.environ.get("AUTOTEMPLATES_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "AutoTemplates"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "autotemplates"


def default_library_dir() -> Path:
    override = os.environ.get("AUTOTEMPLATES_HOME")
    if override:
        return Path(override) / "Library"
    return Path.home() / "Documents" / "AutoTemplates"


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def index_file(self) -> Path:
        return self.data_dir / "index.json"

    @property
    def usage_file(self) -> Path:
        return self.data_dir / "usage.json"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "logs" / "autotemplates.log"

    def ensure(self) -> "AppPaths":
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def default(cls) -> "AppPaths":
        return cls(default_data_dir())


# Alias for backward and forward compatibility
Paths = AppPaths
