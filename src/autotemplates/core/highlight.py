"""Code language detection and coloured HTML (Pygments, imported only when needed)."""

from __future__ import annotations

import html as htmllib
import json
import re
from functools import lru_cache

_RULES: list[tuple[str, re.Pattern]] = [
    ("csharp", re.compile(r"^\s*using\s+System|\bnamespace\s+[\w.]+|\bpublic\s+(sealed\s+|static\s+|partial\s+)*(class|record|interface)\b|\bvar\s+\w+\s*=\s*new\b|\basync\s+Task\b", re.M)),
    ("python", re.compile(r"^\s*(def|class)\s+\w+.*:\s*$|^\s*(from\s+[\w.]+\s+)?import\s+\w+|\bself\.\w+|^\s*if\s+__name__\s*==|\belif\b|print\(", re.M)),
    ("powershell", re.compile(r"\$\w+\s*=|\b(Get|Set|New|Remove|Write|Invoke)-[A-Z]\w+|\bparam\s*\(|-ErrorAction\b", re.M)),
    ("sql", re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE)\b[\s\S]*\b(FROM|INTO|SET|WHERE|VALUES|ADD)\b", re.I)),
    ("typescript", re.compile(r"\binterface\s+\w+\s*\{|:\s*(string|number|boolean)\b|\bexport\s+type\b")),
    ("javascript", re.compile(r"\bfunction\s+\w*\s*\(|\b(const|let)\s+\w+\s*=|=>\s*[{(]|\bconsole\.log\(|\brequire\(|document\.")),
    ("batch", re.compile(r"^\s*@?echo\s+off|^\s*set\s+\w+=|%~dp0|\bgoto\s+:?\w+", re.I | re.M)),
    ("bash", re.compile(r"^#!/bin/(ba)?sh|^\s*(export|echo|fi|done|esac)\b|\$\{\w+\}", re.M)),
    ("css", re.compile(r"^[.#]?[\w-]+(\s*[,>+~]\s*[.#]?[\w-]+)*\s*\{[^}]*:[^}]*;", re.M)),
    ("cpp", re.compile(r"#include\s*<|std::|\bint\s+main\s*\(")),
    ("java", re.compile(r"\bpublic\s+static\s+void\s+main\b|System\.out\.print|\bimport\s+java\.")),
    ("yaml", re.compile(r"^(\s*-\s+)?[\w.-]+:\s+\S.*$(\n(\s*-\s+)?[\w.-]+:\s*.*$){2,}", re.M)),
    ("markdown", re.compile(r"^#{1,6}\s+\S|^\s*[-*]\s+\[[ x]\]|\[[^\]]+\]\([^)]+\)|^```", re.M)),
]


def detect_language(code: str) -> str:
    """Best guess of the language of ``code`` ("" when it looks like prose)."""
    sample = code.strip()[:4000]
    if not sample:
        return ""
    if sample[0] in "[{":
        try:
            json.loads(code)
            return "json"
        except ValueError:
            pass
    if sample.startswith("<"):
        if re.match(r"<(!doctype\s+html|html|div|body|span|p)\b", sample, re.I):
            return "html"
        return "xml"
    for name, pattern in _RULES:
        if pattern.search(sample):
            return name
    return ""


@lru_cache(maxsize=64)
def _lexer(language: str):
    from pygments.lexers import get_lexer_by_name, TextLexer

    try:
        return get_lexer_by_name(language or "text", stripnl=False, ensurenl=False)
    except Exception:  # noqa: BLE001
        return TextLexer(stripnl=False, ensurenl=False)


@lru_cache(maxsize=8)
def _formatter(style: str):
    from pygments.formatters import HtmlFormatter

    try:
        return HtmlFormatter(noclasses=True, nowrap=True, style=style)
    except Exception:  # noqa: BLE001
        return HtmlFormatter(noclasses=True, nowrap=True)


def style_names() -> list[str]:
    from pygments.styles import get_all_styles

    return sorted(get_all_styles())


def style_background(style: str) -> str:
    from pygments.styles import get_style_by_name

    try:
        return get_style_by_name(style).background_color or "#ffffff"
    except Exception:  # noqa: BLE001
        return "#ffffff"


def code_html(code: str, language: str, *, style: str = "default", font: str = "Cascadia Mono",
              size_pt: int = 10, background: str | None = None) -> str:
    """Coloured code as one ``<pre>`` with inline styles (works when pasted into Word/Outlook/Teams)."""
    from pygments import highlight

    body = highlight(code, _lexer(language), _formatter(style)) if language else htmllib.escape(code)
    body = body.rstrip("\n")
    bg = background or style_background(style)
    return (
        f'<pre style="background-color:{bg};font-family:\'{font}\',Consolas,\'Courier New\',monospace;'
        f'font-size:{size_pt}pt;padding:8px;margin:4px 0;white-space:pre-wrap;line-height:125%">{body}</pre>'
    )


def text_html(text: str) -> str:
    """Plain text as HTML that keeps line breaks and runs of spaces in every target."""
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        esc = htmllib.escape(line).replace("\t", "&emsp;")
        esc = re.sub(r"  +", lambda m: "&nbsp;" * len(m.group(0)), esc)
        out.append(esc)
    return "<div>" + "<br/>".join(out) + "</div>"