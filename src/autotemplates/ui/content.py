"""Turns a template file into what gets inserted: HTML, plain text and (for pictures) an image."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QFont, QTextDocument

from autotemplates.core import formats, highlight
from autotemplates.core.library import Template
from autotemplates.core.settings import Settings

log = logging.getLogger(__name__)


@dataclass
class Rendered:
    html: str
    text: str
    image: Path | None = None
    variables: bool = True  # code files are inserted verbatim
    rtf: bytes = b""  # original RTF (.rtf templates): Word/Outlook paste it with every detail, pictures included


_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)


def absolutize_images(markup: str, base: Path) -> str:
    """Relative ``<img src>`` → absolute ``file:///`` URLs (Word/Outlook load them when pasting)."""

    def repl(m: re.Match) -> str:
        src = m.group(2)
        if re.match(r"^(file|https?|data):", src, re.I):
            return m.group(0)
        path = (base / src).resolve()
        return f"{m.group(1)}{path.as_uri()}{m.group(3)}"

    return _SRC_RE.sub(repl, markup)


class Renderer:
    """Renders templates, with a small cache keyed by path + mtime (fast previews)."""

    def __init__(self, settings: Settings, cache_dir: Path) -> None:
        self.settings = settings
        self.cache_dir = cache_dir
        self._cache: OrderedDict[tuple, Rendered] = OrderedDict()

    def clear(self) -> None:
        self._cache.clear()

    def render(self, tpl: Template, root: Path) -> Rendered:
        path = tpl.path(root)
        s = self.settings
        key = (str(path), tpl.mtime, tpl.size, s.get("code_style"), s.get("code_font_family"), s.get("code_font_size"),
               s.get("code_background"), s.get("editor_font_family"), s.get("editor_font_size"))
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        rendered = self._render(tpl, path)
        self._cache[key] = rendered
        while len(self._cache) > 40:
            self._cache.popitem(last=False)
        return rendered

    def code(self, code: str, language: str) -> str:
        s = self.settings
        return highlight.code_html(code, language, style=s.get("code_style"), font=s.get("code_font_family"),
                                   size_pt=int(s.get("code_font_size")), background=s.get("code_background") or None)

    def _render(self, tpl: Template, path: Path) -> Rendered:
        kind = tpl.kind
        try:
            if kind == "rich":
                markup = formats.read_text(path)
                doc = QTextDocument()
                doc.setHtml(markup)
                return Rendered(absolutize_images(markup, path.parent), doc.toPlainText())
            if kind == "markdown":
                source = formats.read_text(path)
                doc = QTextDocument()
                # The base font goes on <body>; without this it would be Qt's default UI font.
                doc.setDefaultFont(QFont(self.settings.get("editor_font_family") or "Segoe UI",
                                         int(self.settings.get("editor_font_size") or 11)))
                doc.setMarkdown(source)
                return Rendered(absolutize_images(doc.toHtml(), path.parent), source)
            if kind == "code":
                source = formats.read_text(path)
                return Rendered(self.code(source, tpl.language), source, variables=False)
            if kind == "text":
                source = formats.read_text(path)
                return Rendered(highlight.text_html(source), source)
            if kind == "rtf":
                raw = path.read_bytes()
                source = raw.decode("latin-1")  # RTF is 7-bit; \'hh escapes are decoded by the parser
                return Rendered(formats.rtf_to_html(source), formats.rtf_to_text(source), rtf=raw)
            if kind == "docx":
                media = self.cache_dir / "docx" / f"{abs(hash(str(path))) & 0xFFFFFFFF:08x}"
                result = formats.docx_to_html(path, media)
                return Rendered(result.html, result.text)
            if kind == "image":
                return Rendered(f'<img src="{path.resolve().as_uri()}"/>', "", image=path, variables=False)
        except Exception as exc:  # noqa: BLE001
            log.exception("Could not read %s", path)
            return Rendered(f"<p style='color:#c62828'>{exc}</p>", "", variables=False)
        return Rendered("", "", variables=False)