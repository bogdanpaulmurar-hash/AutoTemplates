"""DevPilot integration: features owned by the DevPilot hub when it started us.

DevPilot starts managed tools with ``DEVPILOT_MANAGED=1`` and
``DEVPILOT_SUPPRESS=tray,keepawake,autostart`` (see DevPilot docs/INTEGRATION.md).
Started any other way, nothing changes. AutoTemplates never keeps the PC
awake, so only ``tray`` and ``autostart`` matter here.
"""

from __future__ import annotations

import os
from typing import Mapping


def managed(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get("DEVPILOT_MANAGED") == "1"


def suppressed(env: Mapping[str, str] | None = None) -> frozenset[str]:
    env = os.environ if env is None else env
    if not managed(env):
        return frozenset()
    return frozenset(p.strip().lower() for p in env.get("DEVPILOT_SUPPRESS", "").split(",") if p.strip())


def owns(feature: str, env: Mapping[str, str] | None = None) -> bool:
    """True when DevPilot started this process and owns ``feature`` (``tray``, ``autostart``)."""
    return feature.lower() in suppressed(env)
