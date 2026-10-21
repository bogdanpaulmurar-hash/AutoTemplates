"""Variables inside templates, filled in at insertion time.

``{date}`` ``{date:%Y-%m-%d}`` ``{time}`` ``{datetime}`` ``{weekday}``
``{clipboard}`` ``{user}`` ``{cursor}`` ``{input:Customer name}``

Only these names are recognised, so CSS and ordinary braces stay untouched.
``{cursor}`` marks where the caret ends up after the insertion.
Code files are inserted verbatim (``{name}`` is common in source code).
"""

from __future__ import annotations

import getpass
import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

VAR_RE = re.compile(r"\{(date|time|datetime|weekday|clipboard|user|cursor|input):?([^{}<>\n]*)\}")
CURSOR_MARK = "⁣"  # invisible separator: survives HTML -> text, removed before pasting

WEEKDAYS = {
    "ro": ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


@dataclass
class VariableContext:
    now: datetime = field(default_factory=datetime.now)
    clipboard: str = ""
    date_format: str = "%d.%m.%Y"
    time_format: str = "%H:%M"
    language: str = "ro"
    answers: dict[str, str] = field(default_factory=dict)


def has_variables(text: str) -> bool:
    return bool(VAR_RE.search(text))


def input_prompts(text: str) -> list[str]:
    """Distinct ``{input:Label}`` labels, in order of appearance."""
    seen: list[str] = []
    for name, arg in VAR_RE.findall(text):
        label = arg.strip() or "Text"
        if name == "input" and label not in seen:
            seen.append(label)
    return seen


def _value(name: str, arg: str, ctx: VariableContext) -> str:
    arg = arg.strip()
    if name == "date":
        return ctx.now.strftime(arg or ctx.date_format)
    if name == "time":
        return ctx.now.strftime(arg or ctx.time_format)
    if name == "datetime":
        return ctx.now.strftime(arg or f"{ctx.date_format} {ctx.time_format}")
    if name == "weekday":
        return WEEKDAYS.get(ctx.language, WEEKDAYS["en"])[ctx.now.weekday()]
    if name == "clipboard":
        return ctx.clipboard
    if name == "user":
        try:
            return getpass.getuser()
        except Exception:  # noqa: BLE001
            return ""
    if name == "cursor":
        return CURSOR_MARK
    if name == "input":
        return ctx.answers.get(arg or "Text", "")
    return ""


def expand(text: str, ctx: VariableContext, *, html: bool = False) -> str:
    def repl(match: re.Match) -> str:
        try:
            value = _value(match.group(1), match.group(2), ctx)
        except ValueError:  # bad strftime format
            return match.group(0)
        if html and value != CURSOR_MARK:
            value = htmllib.escape(value).replace("\r\n", "\n").replace("\n", "<br/>")
        return value

    return VAR_RE.sub(repl, text)


def split_cursor(text: str) -> tuple[str, int]:
    """Removes the cursor marker; returns the text and how many characters follow it."""
    index = text.find(CURSOR_MARK)
    clean = text.replace(CURSOR_MARK, "")
    if index < 0:
        return clean, 0
    after = text[index + 1:].replace(CURSOR_MARK, "").replace("\r\n", "\n")
    return clean, len(after)


Asker = Callable[[list[str]], "dict[str, str] | None"]
