"""Keyboard shortcuts in one place (no Qt): the windows bind them and the in-app guide lists them.

Sequences use Qt's portable text ("Ctrl+Shift+L"). The first sequence of a command is the one shown
in tooltips and in the guide.
"""

from __future__ import annotations

HELP_KEY = "F1"

# Formatting commands handled by RichEdit (template editor and NoteIT alike).
# Word-like where possible; chosen to be independent of the keyboard layout (no [ ] or Shift+digit).
FORMAT_SHORTCUTS: dict[str, tuple[str, ...]] = {
    "bold": ("Ctrl+B",),
    "italic": ("Ctrl+I",),
    "underline": ("Ctrl+U",),
    "strike": ("Ctrl+Shift+X",),
    "superscript": ("Ctrl+Shift+=", "Ctrl+Shift++", "Ctrl++"),
    "subscript": ("Ctrl+=",),
    "clear": ("Ctrl+Space",),
    "bullets": ("Ctrl+Shift+L",),
    "numbers": ("Ctrl+Shift+O",),
    "indent": ("Ctrl+M",),
    "outdent": ("Ctrl+Shift+M",),
    "h1": ("Ctrl+Alt+1",),
    "h2": ("Ctrl+Alt+2",),
    "h3": ("Ctrl+Alt+3",),
    "normal": ("Ctrl+Shift+N",),
    "left": ("Ctrl+L",),
    "center": ("Ctrl+E",),
    "right": ("Ctrl+R",),
    "justify": ("Ctrl+J",),
    "link": ("Ctrl+K",),
    "paste_plain": ("Ctrl+Shift+V",),
}

# Picker commands bound with QShortcut (the list keys ↑ ↓ ← → Enter Tab Esc are handled in its event filter).
PICKER_SHORTCUTS: dict[str, str] = {
    "edit": "Ctrl+E",
    "new": "Ctrl+N",
    "favourite": "Ctrl+D",
    "copy": "Ctrl+C",
    "copy_plain": "Ctrl+Shift+C",
    "settings": "Ctrl+,",
    "view": "Ctrl+G",
    "help": HELP_KEY,
}

# Template editor window.
EDITOR_SHORTCUTS: dict[str, str] = {
    "save": "Ctrl+S",
    "new": "Ctrl+N",
    "filter": "Ctrl+F",
    "code": "Ctrl+Shift+K",
    "help": HELP_KEY,
}

# NoteIT window.
NOTEIT_SHORTCUTS: dict[str, str] = {
    "copy_close": "Ctrl+Return",
    "copy_plain": "Ctrl+Shift+Return",
    "timestamp": "Ctrl+Shift+D",
    "save": "Ctrl+S",
    "discard": "Ctrl+Shift+Delete",
    "close": "Esc",
    "help": HELP_KEY,
}


def display(seq: str) -> str:
    """Readable form for the guide: "Ctrl+Return" → "Ctrl+Enter"."""
    return seq.replace("Return", "Enter")
