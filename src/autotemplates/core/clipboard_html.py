"""HTML for the Windows clipboard (CF_HTML) that keeps its formatting in the target app.

Word, Outlook, Teams and browsers read only the part between ``<!--StartFragment-->``
and ``<!--EndFragment-->``; browsers and Teams also ignore ``<head><style>``. Qt puts the
base font on ``<body style>`` and paragraph rules in ``<head>``, so both were lost on paste.

``fragment_html`` moves those styles onto the elements inside the fragment, removes
Qt-only CSS (``-qt-*``) and font names the Office apps do not know.
``set_image_sources`` picks how pictures travel: ``file:///`` for Office (it embeds the
original file) or ``data:`` with the original bytes for browsers and Teams. Pictures are
never re-encoded or scaled, so they keep the quality they were inserted with.

No Qt here, so everything is testable on any OS.
"""

from __future__ import annotations

import base64
import html as htmllib
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

OFFICE_PROCESSES = {"winword.exe", "outlook.exe", "onenote.exe", "excel.exe", "powerpnt.exe", "olk.exe"}
DATA_URI_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".bmp": "image/bmp", ".webp": "image/webp", ".svg": "image/svg+xml"}
MONO_STACK = "Consolas,'Courier New',monospace"

_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.I | re.S)
_BODY_RE = re.compile(r"<body\b([^>]*)>(.*)</body>", re.I | re.S)
_BODY_OPEN_RE = re.compile(r"<body\b([^>]*)>(.*)$", re.I | re.S)
_STYLE_ATTR_RE = re.compile(r"""\sstyle\s*=\s*("([^"]*)"|'([^']*)')""", re.I)
_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^<>]*?)(/?)>")
_FRAGMENT_MARK_RE = re.compile(r"<!--\s*(Start|End)Fragment\s*-->", re.I)
_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)
# Values the target applies anyway; dropping them keeps the fragment small.
_NOISE = {("font-weight", "400"), ("font-weight", "normal"), ("font-style", "normal")}


# --------------------------------------------------------------------------- css helpers


def parse_style(style: str) -> list[tuple[str, str]]:
    """``"a:1; b:2"`` → ``[("a", "1"), ("b", "2")]`` (lower-case names, order kept)."""
    out: list[tuple[str, str]] = []
    for part in htmllib.unescape(style).split(";"):
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        name, value = name.strip().lower(), value.strip()
        if name and value:
            out.append((name, value))
    return out


def clean_declarations(decls: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drops Qt-only properties and maps values Office does not understand."""
    out: list[tuple[str, str]] = []
    for name, value in decls:
        if name.startswith("-qt-") or name.startswith("qt-"):
            continue
        if name == "font-family":
            families = [f.strip().strip("'\"") for f in value.split(",") if f.strip()]
            if families and families[0].lower() in ("monospace", "courier", "mono"):
                value = MONO_STACK
        elif name == "font-weight" and value in ("700", "800", "900"):
            value = "bold"
        if (name, value.lower()) in _NOISE:
            continue
        out.append((name, value))
    return out


def merge_declarations(*groups: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Later groups win; the order of first appearance is kept."""
    merged: dict[str, str] = {}
    for group in groups:
        for name, value in group:
            merged.pop(name, None)
            merged[name] = value
    return list(merged.items())


def format_style(decls: list[tuple[str, str]]) -> str:
    return ";".join(f"{n}:{v}" for n, v in decls).replace('"', "'")


def _tag_rules(css: str) -> dict[str, list[tuple[str, str]]]:
    """Rules whose selectors are plain tag names (``p, li { ... }``); the rest is ignored."""
    rules: dict[str, list[tuple[str, str]]] = {}
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        decls = clean_declarations(parse_style(body))
        if not decls:
            continue
        for sel in selectors.split(","):
            sel = sel.strip().lower()
            if re.fullmatch(r"[a-z][a-z0-9]*", sel):
                rules[sel] = merge_declarations(rules.get(sel, []), decls)
    return rules


def _restyle_tags(markup: str, rules: dict[str, list[tuple[str, str]]]) -> str:
    """Applies tag rules and cleans every inline ``style`` attribute."""

    def repl(m: re.Match) -> str:
        tag, attrs, slash = m.group(1), m.group(2), m.group(3)
        sm = _STYLE_ATTR_RE.search(attrs)
        own = parse_style((sm.group(2) if sm.group(2) is not None else sm.group(3)) or "") if sm else []
        rule = rules.get(tag.lower(), [])
        if not sm and not rule:
            return m.group(0)
        decls = merge_declarations(rule, clean_declarations(own))
        attrs = _STYLE_ATTR_RE.sub("", attrs) if sm else attrs
        style = f' style="{format_style(decls)}"' if decls else ""
        return f"<{tag}{attrs.rstrip()}{style}{slash}>"

    return _TAG_RE.sub(repl, markup)


# --------------------------------------------------------------------------- fragment


def split_document(markup: str) -> tuple[str, list[tuple[str, str]], str]:
    """(css from ``<style>`` blocks, ``<body>`` style, body content) of an HTML document or snippet."""
    markup = _FRAGMENT_MARK_RE.sub("", markup)
    css = "\n".join(_STYLE_BLOCK_RE.findall(markup))
    m = _BODY_RE.search(markup) or _BODY_OPEN_RE.search(markup)
    if m:
        sm = _STYLE_ATTR_RE.search(m.group(1))
        body_style = parse_style((sm.group(2) if sm.group(2) is not None else sm.group(3)) or "") if sm else []
        content = m.group(2)
    else:
        body_style = []
        content = re.sub(r"<head\b.*?</head>", "", markup, flags=re.I | re.S)
        content = re.sub(r"</?(html|body)\b[^>]*>|<!doctype[^>]*>", "", content, flags=re.I)
    content = _STYLE_BLOCK_RE.sub("", content)
    return css, body_style, content.strip()


def fragment_html(markup: str, *, base_font: str = "", base_size_pt: float = 0, keep_body_font: bool = True) -> str:
    """A complete HTML document whose fragment carries all of its formatting inline.

    ``base_font`` / ``base_size_pt`` apply when the template sets no font of its own
    (otherwise Word and Outlook fall back to "Normal (Web)", Times New Roman).
    With ``keep_body_font=False`` the base font is left to the target app; fonts set on
    individual words are kept either way.
    """
    if not markup:
        return ""
    css, body_style, content = split_document(markup)
    content = _restyle_tags(content, _tag_rules(css))
    base = clean_declarations(body_style)
    names = {n for n, _ in base}
    if keep_body_font:
        if base_font and "font-family" not in names:
            base.append(("font-family", f"'{base_font}'" if " " in base_font else base_font))
        if base_size_pt and "font-size" not in names:
            base.append(("font-size", f"{base_size_pt:g}pt"))
    else:
        base = [(n, v) for n, v in base if n not in ("font-family", "font-size")]
    if base:
        content = f'<div style="{format_style(base)}">{content}</div>'
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
            f"<!--StartFragment-->{content}<!--EndFragment--></body></html>")


# --------------------------------------------------------------------------- pictures


def image_mode_for(process: str, setting: str = "auto") -> str:
    """``file`` (Office embeds the original file) or ``data`` (browsers, Teams)."""
    if setting in ("file", "data"):
        return setting
    if not process:
        return "file"  # copied without a target: Office is the usual destination
    return "file" if process.lower() in OFFICE_PROCESSES else "data"


def _local_path(src: str) -> Path | None:
    if not src.lower().startswith("file:"):
        return None
    parsed = urlparse(src)
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        return Path(f"//{parsed.netloc}{path}")  # UNC share
    if re.match(r"^/[A-Za-z]:", path):  # file:///C:/x -> C:/x
        path = path[1:]
    return Path(path)


def set_image_sources(markup: str, mode: str, max_bytes: int = DATA_URI_MAX_BYTES) -> str:
    """``data`` mode: local pictures become ``data:`` URIs with their original bytes.

    Pictures larger than ``max_bytes`` stay ``file:///`` rather than being recompressed.
    """
    if mode != "data" or "<img" not in markup.lower():
        return markup

    def repl(m: re.Match) -> str:
        path = _local_path(htmllib.unescape(m.group(2)))
        if path is None:
            return m.group(0)
        mime = _IMAGE_MIME.get(path.suffix.lower())
        try:
            if mime is None or path.stat().st_size > max_bytes:
                return m.group(0)
            data = path.read_bytes()
        except OSError:
            return m.group(0)
        return f"{m.group(1)}data:{mime};base64,{base64.b64encode(data).decode('ascii')}{m.group(3)}"

    return _SRC_RE.sub(repl, markup)
