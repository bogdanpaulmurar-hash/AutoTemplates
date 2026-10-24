"""Puts a template into the window that had the focus: clipboard + Ctrl+V, then restores the clipboard.

Pasting is the only method that keeps formatting and pictures in every program
(Word, Outlook, Teams, browsers, code editors). The text goes to the clipboard
as HTML *and* plain text (plus the original RTF for .rtf templates), so each
program takes the richest format it supports.

The HTML is rebuilt by ``core.clipboard_html`` so the fragment carries all of its
styles inline, and pictures travel the way the target app can load them. In
Outlook/Word the paste goes through COM with "Keep source formatting" when the
setting is on (Ctrl+V would follow the user's "Keep text only" option).
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QMimeData, QObject, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QImage

from autotemplates.core import clipboard_html as ch
from autotemplates.core import variables as tv
from autotemplates.core.settings import Settings
from autotemplates.platform import office, win32
from autotemplates.ui.content import Rendered

log = logging.getLogger(__name__)

MAX_BACKUP_BYTES = 64 * 1024 * 1024
RTF_MIME = 'application/x-qt-windows-mime;value="Rich Text Format"'  # CF "Rich Text Format" on Windows


def backup_clipboard() -> QMimeData | None:
    """A copy of the current clipboard (every format), or None when it is empty or huge."""
    source = QGuiApplication.clipboard().mimeData()
    if source is None:
        return None
    copy = QMimeData()
    total = 0
    try:
        for fmt in source.formats():
            data = source.data(fmt)
            total += data.size()
            if total > MAX_BACKUP_BYTES:
                log.info("Clipboard too large to back up (%d MB)", total // (1024 * 1024))
                return None
            copy.setData(fmt, data)
        if source.hasImage() and not copy.hasImage():
            copy.setImageData(source.imageData())
    except RuntimeError:
        return None
    return copy if copy.formats() else None


def wrap_cf_html(html: str) -> str:
    """Wraps HTML so Windows CF_HTML (MS Word, Outlook, Teams, OneNote) reliably detects fragments."""
    if not html:
        return ""
    if "<!--StartFragment-->" in html:
        return html
    lower = html.lower()
    if "<body" in lower and "</body>" in lower:
        body_start = lower.find("<body")
        body_tag_end = html.find(">", body_start) + 1
        body_close = lower.rfind("</body>")
        return (
            html[:body_tag_end]
            + "<!--StartFragment-->"
            + html[body_tag_end:body_close]
            + "<!--EndFragment-->"
            + html[body_close:]
        )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body>"
        "<!--StartFragment-->" + html + "<!--EndFragment-->"
        "</body></html>"
    )


def build_mime(html: str, text: str, image_path=None, *, plain: bool = False, rtf: bytes = b"") -> QMimeData:
    mime = QMimeData()
    mime.setText(text)
    if not plain:
        if rtf:
            mime.setData(RTF_MIME, rtf)
        if html:
            mime.setHtml(wrap_cf_html(html))
        if image_path is not None:
            image = QImage(str(image_path))
            if not image.isNull():
                mime.setImageData(image)
                mime.setUrls([QUrl.fromLocalFile(str(image_path))])
    return mime


class Inserter(QObject):
    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._restore: QMimeData | None = None
        self._restore_timer = QTimer(self, singleShot=True)
        self._restore_timer.timeout.connect(self._restore_clipboard)

    def prepare(self, rendered: Rendered, *, plain: bool, answers: dict[str, str] | None = None) -> tuple[str, str, int]:
        """Expands the variables; returns (html, text, characters after {cursor})."""
        html, text = rendered.html, rendered.text
        if rendered.variables:
            ctx = tv.VariableContext(
                clipboard=QGuiApplication.clipboard().text(),
                date_format=self.settings.get("date_format"),
                time_format=self.settings.get("time_format"),
                language=self.settings.get("language"),
                answers=answers or {},
            )
            html = tv.expand(html, ctx, html=True)
            text = tv.expand(text, ctx)
        text, back = tv.split_cursor(text)
        html = html.replace(tv.CURSOR_MARK, "")
        return html, text, back

    def clipboard_html(self, html: str, process: str = "") -> str:
        """The HTML exactly as it goes on the clipboard for a target ``process`` ("" = unknown)."""
        if not html:
            return ""
        s = self.settings
        out = ch.fragment_html(html, base_font=str(s.get("editor_font_family") or ""),
                               base_size_pt=float(s.get("editor_font_size") or 0),
                               keep_body_font=s.get("insert_base_font") != "target")
        return ch.set_image_sources(out, ch.image_mode_for(process, str(s.get("insert_images") or "auto")))

    def mime_for(self, rendered: Rendered, html: str, text: str, *, plain: bool, process: str = "") -> QMimeData:
        # The original RTF only when nothing had to be filled in (variables live in the HTML/text copies).
        rtf = rendered.rtf if rendered.rtf and not tv.has_variables(rendered.text) else b""
        return build_mime("" if plain else self.clipboard_html(html, process), text, rendered.image,
                          plain=plain, rtf=rtf)

    def _paste(self, target_hwnd: int, process: str, plain: bool) -> None:
        if not plain and self.settings.get("office_com_paste") and process in office.COM_PASTE_PROCESSES:
            try:
                office.paste_original(process, win32.window_title(target_hwnd), win32.focused_class(target_hwnd))
                return
            except office.OfficeUnavailable as e:
                log.info("COM paste not used (%s); falling back to Ctrl+V", e)
        win32.send_paste()

    def insert(self, rendered: Rendered, target_hwnd: int, *, plain: bool, answers: dict[str, str] | None = None) -> None:
        html, text, back = self.prepare(rendered, plain=plain, answers=answers)
        if self._restore_timer.isActive():  # a previous insertion has not restored yet: keep the original
            self._restore_timer.stop()
        elif self.settings.get("restore_clipboard"):
            self._restore = backup_clipboard()
        process = win32.process_name(target_hwnd) if target_hwnd else ""
        QGuiApplication.clipboard().setMimeData(self.mime_for(rendered, html, text, plain=plain, process=process))
        QGuiApplication.processEvents()

        win32.release_modifiers()
        if target_hwnd:
            win32.focus_window(target_hwnd)
        time.sleep(max(0.08, int(self.settings.get("paste_delay_ms")) / 1000))
        self._paste(target_hwnd, process, plain)
        if back:
            time.sleep(0.03)
            win32.send_left(back)
        if self.settings.get("restore_clipboard"):
            self._restore_timer.start(max(1200, int(self.settings.get("restore_delay_ms"))))

    def copy_only(self, rendered: Rendered, *, plain: bool, answers: dict[str, str] | None = None) -> None:
        """Puts the template on the clipboard without pasting (Ctrl+C in the picker)."""
        html, text, _ = self.prepare(rendered, plain=plain, answers=answers)
        self._restore_timer.stop()
        self._restore = None
        QGuiApplication.clipboard().setMimeData(self.mime_for(rendered, html, text, plain=plain))

    def _restore_clipboard(self) -> None:
        if self._restore is not None:
            QGuiApplication.clipboard().setMimeData(self._restore)
            self._restore = None
