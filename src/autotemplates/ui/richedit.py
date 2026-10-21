"""Rich text editing widget: formatting commands, pasted screenshots, tables, code blocks."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QKeySequence, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFrameFormat, QTextImageFormat, QTextLength,
                           QTextListFormat, QTextTableFormat)
from PySide6.QtWidgets import QTextEdit

from autotemplates.core import formats

log = logging.getLogger(__name__)

IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)
HEADING_SIZES = {1: 20, 2: 16, 3: 13}


class RichEdit(QTextEdit):
    """QTextEdit that stores pasted/dropped pictures as files and keeps their paths."""

    image_added = Signal()

    def __init__(self, paste_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.paste_dir = paste_dir
        self.setAcceptRichText(True)
        self.setObjectName("Paper")  # white page like Word/Outlook, whatever the app theme
        self.setTabChangesFocus(False)
        self.document().setDocumentMargin(14)

    # ---------------------------------------------------------------- pictures
    def save_image(self, image: QImage) -> Path:
        self.paste_dir.mkdir(parents=True, exist_ok=True)
        data = image.bits().tobytes() if image.sizeInBytes() else b""
        name = hashlib.sha1(data + f"{image.width()}x{image.height()}".encode()).hexdigest()[:12] + ".png"
        path = self.paste_dir / name
        if not path.exists():
            image.save(str(path), "PNG")
        return path

    def insert_image_file(self, path: Path, max_width: int = 900) -> None:
        image = QImage(str(path))
        fmt = QTextImageFormat()
        fmt.setName(Path(path).resolve().as_uri())
        if not image.isNull() and image.width() > max_width:
            fmt.setWidth(max_width)
            fmt.setHeight(image.height() * max_width / image.width())
        self.textCursor().insertImage(fmt)
        self.image_added.emit()

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        if source.hasUrls():
            local = [Path(u.toLocalFile()) for u in source.urls() if u.isLocalFile()]
            images = [p for p in local if p.suffix.lower() in formats.IMAGE_EXT]
            if images and len(images) == len(local):
                for p in images:
                    self.insert_image_file(p)
                return
        if source.hasImage() and not source.hasHtml():
            image = QImage(source.imageData())
            if not image.isNull():
                self.insert_image_file(self.save_image(image))
                return
        if source.hasHtml():
            # Pictures pasted from browsers/Word: data: URIs are saved as files.
            html = source.html()
            html = re.sub(r'src="data:image/(png|jpe?g|gif);base64,([^"]+)"', self._data_uri_to_file, html)
            self.textCursor().insertHtml(html)
            return
        super().insertFromMimeData(source)

    def _data_uri_to_file(self, m: re.Match) -> str:
        import base64

        try:
            image = QImage.fromData(base64.b64decode(m.group(2)))
            return f'src="{self.save_image(image).as_uri()}"'
        except Exception:  # noqa: BLE001
            return m.group(0)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Paste) and event.modifiers() & Qt.ShiftModifier:
            self.paste_plain()
            return
        super().keyPressEvent(event)

    def paste_plain(self) -> None:
        from PySide6.QtGui import QGuiApplication

        self.textCursor().insertText(QGuiApplication.clipboard().text())

    # ---------------------------------------------------------------- character formatting
    def merge(self, fmt: QTextCharFormat) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.mergeCurrentCharFormat(fmt)

    def set_bold(self, on: bool) -> None:
        f = QTextCharFormat()
        f.setFontWeight(QFont.Bold if on else QFont.Normal)
        self.merge(f)

    def set_italic(self, on: bool) -> None:
        f = QTextCharFormat()
        f.setFontItalic(on)
        self.merge(f)

    def set_underline(self, on: bool) -> None:
        f = QTextCharFormat()
        f.setFontUnderline(on)
        self.merge(f)

    def set_strike(self, on: bool) -> None:
        f = QTextCharFormat()
        f.setFontStrikeOut(on)
        self.merge(f)

    def set_vertical(self, align: QTextCharFormat.VerticalAlignment) -> None:
        current = self.currentCharFormat().verticalAlignment()
        f = QTextCharFormat()
        f.setVerticalAlignment(QTextCharFormat.AlignNormal if current == align else align)
        self.merge(f)

    def set_family(self, family: str) -> None:
        f = QTextCharFormat()
        f.setFontFamilies([family])
        self.merge(f)

    def set_size(self, size: float) -> None:
        if size > 0:
            f = QTextCharFormat()
            f.setFontPointSize(size)
            self.merge(f)

    def set_color(self, color: QColor | None) -> None:
        if color is None:
            self._each_fragment(lambda f: f.clearForeground())
            return
        f = QTextCharFormat()
        f.setForeground(QBrush(color))
        self.merge(f)

    def set_highlight(self, color: QColor | None) -> None:
        if color is None:
            self._each_fragment(lambda f: f.clearBackground())
            return
        f = QTextCharFormat()
        f.setBackground(QBrush(color))
        self.merge(f)

    def _each_fragment(self, change) -> None:
        """Applies ``change(format)`` (which edits it or returns a new one) to every text fragment of the selection (pictures are skipped).

        Needed to *remove* a property: mergeCharFormat can only add or overwrite.
        """
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.beginEditBlock()
        block = self.document().findBlock(start)
        while block.isValid() and block.position() <= end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                a, b = max(start, frag.position()), min(end, frag.position() + frag.length())
                if a < b and not frag.charFormat().isImageFormat():
                    part = QTextCursor(self.document())
                    part.setPosition(a)
                    part.setPosition(b, QTextCursor.KeepAnchor)
                    fmt = frag.charFormat()
                    part.setCharFormat(change(fmt) or fmt)
                it += 1
            block = block.next()
        cursor.endEditBlock()
        # Typing continues without the property (setCurrentCharFormat would re-apply it to a selection).
        if not self.textCursor().hasSelection() and not self.currentCharFormat().isImageFormat():
            fmt = self.currentCharFormat()
            self.setCurrentCharFormat(change(fmt) or fmt)

    def clear_formatting(self) -> None:
        """Back to plain text: no colours, weight, size, font or links (pictures stay)."""
        if not self.textCursor().hasSelection():
            cursor = self.textCursor()
            cursor.select(QTextCursor.BlockUnderCursor)
            self.setTextCursor(cursor)
        self._each_fragment(lambda f: QTextCharFormat())

    # ---------------------------------------------------------------- blocks
    def _merge_block(self, fmt: QTextBlockFormat) -> None:
        self.textCursor().mergeBlockFormat(fmt)

    def set_alignment(self, align: Qt.AlignmentFlag) -> None:
        self.setAlignment(align)

    def set_line_spacing(self, factor: float) -> None:
        f = QTextBlockFormat()
        f.setLineHeight(factor * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        self._merge_block(f)

    def set_paragraph_spacing(self, before: float, after: float) -> None:
        f = QTextBlockFormat()
        f.setTopMargin(before)
        f.setBottomMargin(after)
        self._merge_block(f)

    def set_heading(self, level: int) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        bf = QTextBlockFormat()
        bf.setHeadingLevel(level)
        cursor.mergeBlockFormat(bf)
        sel = QTextCursor(cursor)
        if not cursor.hasSelection():
            sel.movePosition(QTextCursor.StartOfBlock)
            sel.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cf = QTextCharFormat()
        cf.setFontWeight(QFont.Bold if level else QFont.Normal)
        cf.setFontPointSize(HEADING_SIZES.get(level, self.document().defaultFont().pointSizeF()))
        sel.mergeCharFormat(cf)
        cursor.endEditBlock()

    def toggle_list(self, style: QTextListFormat.Style) -> None:
        cursor = self.textCursor()
        current = cursor.currentList()
        cursor.beginEditBlock()
        if current is not None and current.format().style() == style:
            block = cursor.block()
            current.remove(block)
            bf = cursor.blockFormat()
            bf.setIndent(0)
            cursor.setBlockFormat(bf)
        else:
            lf = QTextListFormat()
            lf.setStyle(style)
            lf.setIndent((current.format().indent() if current else 0) + 1)
            cursor.createList(lf)
        cursor.endEditBlock()

    def change_indent(self, delta: int) -> None:
        cursor = self.textCursor()
        current = cursor.currentList()
        if current is not None:
            lf = current.format()
            lf.setIndent(max(1, lf.indent() + delta))
            current.setFormat(lf)
            return
        bf = cursor.blockFormat()
        bf.setIndent(max(0, bf.indent() + delta))
        cursor.setBlockFormat(bf)

    # ---------------------------------------------------------------- inserts
    def insert_link(self, url: str, text: str = "") -> None:
        cursor = self.textCursor()
        label = text or cursor.selectedText() or url
        f = QTextCharFormat()
        f.setAnchor(True)
        f.setAnchorHref(url)
        f.setForeground(QBrush(QColor("#2f6feb")))
        f.setFontUnderline(True)
        cursor.insertText(label, f)
        self.setCurrentCharFormat(QTextCharFormat())

    def insert_table(self, rows: int, cols: int) -> None:
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        tf.setCellPadding(5)
        tf.setCellSpacing(0)
        tf.setBorderCollapse(True)
        tf.setWidth(QTextLength(QTextLength.PercentageLength, 100))
        self.textCursor().insertTable(max(1, rows), max(1, cols), tf)

    def table_op(self, op: str) -> None:
        cursor = self.textCursor()
        table = cursor.currentTable()
        if table is None:
            return
        cell = table.cellAt(cursor)
        r, c = cell.row(), cell.column()
        if op == "row_above":
            table.insertRows(r, 1)
        elif op == "row_below":
            table.insertRows(r + 1, 1)
        elif op == "col_left":
            table.insertColumns(c, 1)
        elif op == "col_right":
            table.insertColumns(c + 1, 1)
        elif op == "del_row":
            table.removeRows(r, 1)
        elif op == "del_col":
            table.removeColumns(c, 1)

    def set_cell_background(self, color: QColor | None) -> None:
        cursor = self.textCursor()
        table = cursor.currentTable()
        if table is None:
            return
        cell = table.cellAt(cursor)
        f = cell.format().toTableCellFormat()
        f.setBackground(QBrush(color) if color else QBrush(Qt.NoBrush))
        cell.setFormat(f)

    def insert_rule(self) -> None:
        self.textCursor().insertHtml("<hr/>")
        self.textCursor().insertBlock(QTextBlockFormat(), QTextCharFormat())

    def insert_code_html(self, html: str) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.block().length() > 1:
            cursor.insertBlock()
        cursor.insertHtml(html)
        cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
        cursor.endEditBlock()

    def image_at_cursor(self) -> tuple[QTextCursor, QTextImageFormat] | None:
        cursor = self.textCursor()
        for move in (None, QTextCursor.Left, QTextCursor.Right):
            probe = QTextCursor(cursor)
            if move is not None:
                probe.movePosition(move, QTextCursor.KeepAnchor if move == QTextCursor.Right else QTextCursor.MoveAnchor)
            if move == QTextCursor.Left:
                probe.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
            fmt = probe.charFormat()
            if fmt.isImageFormat() and probe.hasSelection():
                return probe, fmt.toImageFormat()
        return None

    def resize_image(self, width: int) -> bool:
        found = self.image_at_cursor()
        if not found:
            return False
        cursor, fmt = found
        image = QImage(QUrl(fmt.name()).toLocalFile() or fmt.name())
        if not image.isNull() and image.width():
            fmt.setHeight(image.height() * width / image.width())
        fmt.setWidth(width)
        cursor.setCharFormat(fmt)
        return True


# -------------------------------------------------------------------- saving


def localize_images(markup: str, html_path: Path) -> str:
    """Copies every picture into ``<name>.assets`` and makes the ``src`` relative; removes unused ones."""
    assets = html_path.with_suffix(".assets")
    folder = html_path.parent
    used: set[str] = set()

    def repl(m: re.Match) -> str:
        src = m.group(2)
        if re.match(r"^(https?|data):", src, re.I):
            return m.group(0)
        path = Path(QUrl(src).toLocalFile()) if src.lower().startswith("file:") else (folder / src)
        try:
            path = path.resolve()
        except OSError:
            return m.group(0)
        if not path.exists():
            return m.group(0)
        if path.parent != assets.resolve():
            assets.mkdir(parents=True, exist_ok=True)
            target = assets / path.name
            if target.exists() and target.resolve() != path:
                digest = hashlib.sha1(path.read_bytes()).hexdigest()[:8]
                target = assets / f"{path.stem}-{digest}{path.suffix}"
            if not target.exists():
                shutil.copy2(path, target)
            path = target
        used.add(path.name)
        rel = os.path.relpath(path, folder).replace(os.sep, "/")
        return f"{m.group(1)}{rel}{m.group(3)}"

    markup = IMG_SRC_RE.sub(repl, markup)
    if assets.is_dir():
        for f in assets.iterdir():
            if f.is_file() and f.name not in used:
                try:
                    f.unlink()
                except OSError:
                    pass
        try:
            if not any(assets.iterdir()):
                assets.rmdir()
        except OSError:
            pass
    return markup


def load_document(edit: QTextEdit, html_path: Path) -> None:
    """Loads an editor template; relative pictures resolve against its folder."""
    doc: QTextDocument = edit.document()
    doc.setBaseUrl(QUrl.fromLocalFile(str(html_path.parent) + "/"))
    markup = formats.read_text(html_path)
    markup = IMG_SRC_RE.sub(
        lambda m: m.group(0) if re.match(r"^(file|https?|data):", m.group(2), re.I)
        else f"{m.group(1)}{(html_path.parent / m.group(2)).resolve().as_uri()}{m.group(3)}",
        markup,
    )
    edit.setHtml(markup)
    doc.setModified(False)


__all__ = ["RichEdit", "localize_images", "load_document"]
