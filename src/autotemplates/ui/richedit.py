"""Rich text editing widget: formatting commands, pasted screenshots, tables, code blocks."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QKeyCombination, QMimeData, QPoint, QRect, QUrl, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextImageFormat,
    QTextLength,
    QTextListFormat,
    QTextTableFormat,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from autotemplates.core import formats
from autotemplates.i18n import t

log = logging.getLogger(__name__)

IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.I)
HEADING_SIZES = {1: 20, 2: 16, 3: 13}

# Formatting shortcuts handled by RichEdit itself (template editor and NoteIT alike).
# Word-like where possible; chosen to be independent of the keyboard layout (no [ ] or Shift+digit).
# The first sequence is the one shown in tooltips.
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
_KEYMAP: dict[str, str] = {
    QKeySequence(seq).toString(QKeySequence.PortableText): name
    for name, seqs in FORMAT_SHORTCUTS.items()
    for seq in seqs
}
_MODIFIER_KEYS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr}
HANDLE = 10  # px, size of the image resize handle


def shortcut_text(name: str) -> str:
    """Display text of the main shortcut of a formatting command ("Ctrl+B")."""
    seqs = FORMAT_SHORTCUTS.get(name)
    return QKeySequence(seqs[0]).toString(QKeySequence.NativeText) if seqs else ""


def with_shortcut(label: str, name: str) -> str:
    """Tooltip text: "Bold (Ctrl+B)"."""
    sc = shortcut_text(name)
    return f"{label} ({sc})" if sc else label


class ImageResizeDialog(QDialog):
    """Interactive dialog for resizing and modifying pasted images with live presets."""

    def __init__(
        self,
        parent=None,
        orig_w: int = 800,
        orig_h: int = 600,
        current_w: int = 500,
        current_h: int = 375,
        avail_w: int = 520,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("image.dialog_title"))
        self.setMinimumWidth(380)
        self.orig_w = max(1, orig_w)
        self.orig_h = max(1, orig_h)
        self.aspect_ratio = self.orig_w / self.orig_h
        self.avail_w = max(100, avail_w)
        self.should_delete = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header info
        info_orig = QLabel(t("image.orig_size", w=self.orig_w, h=self.orig_h))
        info_orig.setStyleSheet("font-weight: bold; font-size: 10pt;")
        layout.addWidget(info_orig)

        info_curr = QLabel(t("image.curr_size", w=current_w, h=current_h))
        info_curr.setStyleSheet("color: #9a9eab; font-size: 9pt;")
        layout.addWidget(info_curr)

        # Presets label
        lbl_presets = QLabel("Preset-uri rapide / Quick presets:")
        lbl_presets.setStyleSheet("font-size: 8.5pt; color: #9a9eab; margin-top: 4px;")
        layout.addWidget(lbl_presets)

        row_presets = QHBoxLayout()
        row_presets.setSpacing(6)

        btn_fit = QPushButton("100% Fit")
        btn_fit.setToolTip(t("image.fit_width"))
        btn_fit.clicked.connect(self._set_fit)
        row_presets.addWidget(btn_fit)

        btn_75 = QPushButton("75%")
        btn_75.clicked.connect(lambda: self._set_percent(0.75))
        row_presets.addWidget(btn_75)

        btn_50 = QPushButton("50%")
        btn_50.clicked.connect(lambda: self._set_percent(0.50))
        row_presets.addWidget(btn_50)

        btn_25 = QPushButton("25%")
        btn_25.clicked.connect(lambda: self._set_percent(0.25))
        row_presets.addWidget(btn_25)

        btn_orig = QPushButton("1:1 (Orig)")
        btn_orig.setToolTip(t("image.original_size"))
        btn_orig.clicked.connect(self._set_original)
        row_presets.addWidget(btn_orig)

        layout.addLayout(row_presets)

        # Dimension spinboxes
        grid = QHBoxLayout()
        grid.setSpacing(10)

        col_w = QVBoxLayout()
        lbl_w = QLabel(t("image.width"))
        lbl_w.setStyleSheet("font-size: 9pt;")
        self.spin_w = QSpinBox()
        self.spin_w.setRange(20, 5000)
        self.spin_w.setValue(max(20, current_w))
        col_w.addWidget(lbl_w)
        col_w.addWidget(self.spin_w)
        grid.addLayout(col_w)

        col_h = QVBoxLayout()
        lbl_h = QLabel(t("image.height"))
        lbl_h.setStyleSheet("font-size: 9pt;")
        self.spin_h = QSpinBox()
        self.spin_h.setRange(20, 5000)
        self.spin_h.setValue(max(20, current_h))
        col_h.addWidget(lbl_h)
        col_h.addWidget(self.spin_h)
        grid.addLayout(col_h)

        layout.addLayout(grid)

        # Ratio checkbox
        self.chk_ratio = QCheckBox(t("image.keep_ratio"))
        self.chk_ratio.setChecked(True)
        layout.addWidget(self.chk_ratio)

        self.spin_w.valueChanged.connect(self._on_width_changed)
        self.spin_h.valueChanged.connect(self._on_height_changed)

        # Action buttons
        layout.addSpacing(6)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_del = QPushButton("🗑️ " + t("image.delete"))
        self.btn_del.setStyleSheet("color: #ff6b6b;")
        self.btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_del)

        btn_row.addStretch(1)

        btn_cancel = QPushButton("Anulează")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_apply = QPushButton(t("image.apply"))
        btn_apply.setObjectName("Primary")
        btn_apply.setStyleSheet("background: #5b6cff; color: white; font-weight: bold;")
        btn_apply.clicked.connect(self.accept)
        btn_row.addWidget(btn_apply)

        layout.addLayout(btn_row)

    def _set_fit(self) -> None:
        target_w = min(self.orig_w, self.avail_w)
        self.spin_w.setValue(int(target_w))

    def _set_original(self) -> None:
        self.spin_w.setValue(int(self.orig_w))

    def _set_percent(self, frac: float) -> None:
        self.spin_w.setValue(max(20, int(round(self.orig_w * frac))))

    def _on_width_changed(self, val: int) -> None:
        if self.chk_ratio.isChecked() and self.aspect_ratio:
            self.spin_h.blockSignals(True)
            self.spin_h.setValue(max(20, int(round(val / self.aspect_ratio))))
            self.spin_h.blockSignals(False)

    def _on_height_changed(self, val: int) -> None:
        if self.chk_ratio.isChecked() and self.aspect_ratio:
            self.spin_w.blockSignals(True)
            self.spin_w.setValue(max(20, int(round(val * self.aspect_ratio))))
            self.spin_w.blockSignals(False)

    def _on_delete(self) -> None:
        self.should_delete = True
        self.accept()

    def get_dimensions(self) -> tuple[int, int]:
        return self.spin_w.value(), self.spin_h.value()


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
        self._active_image: int | None = None  # document position of the selected picture
        self._drag: tuple[QPoint, int, int, float] | None = None  # start pos, width, height, ratio
        self.cursorPositionChanged.connect(self._track_image)
        self.selectionChanged.connect(self._track_image)

    # ---------------------------------------------------------------- pictures
    def save_image(self, image: QImage) -> Path:
        self.paste_dir.mkdir(parents=True, exist_ok=True)
        data = image.bits().tobytes() if image.sizeInBytes() else b""
        name = hashlib.sha1(data + f"{image.width()}x{image.height()}".encode()).hexdigest()[:12] + ".png"
        path = self.paste_dir / name
        if not path.exists():
            image.save(str(path), "PNG", quality=100)
        return path

    def _register_smooth_resource(self, name: str, img: QImage, w: int, h: int) -> None:
        """Registers a high-DPI smooth-scaled pixmap resource in the document cache to eliminate pixelation."""
        if img.isNull() or w <= 0 or h <= 0:
            return
        dpr = max(1.0, float(self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0))
        target_pw = max(1, int(round(w * dpr)))
        target_ph = max(1, int(round(h * dpr)))
        smooth = img.scaled(
            target_pw,
            target_ph,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        smooth.setDevicePixelRatio(dpr)
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), smooth)

    def insert_image_file(self, path: Path, max_width: int | None = None) -> None:
        image = QImage(str(path))
        if image.isNull():
            return

        avail_w = max(240, self.viewport().width() - 36)
        target_w = image.width()
        if max_width is not None and max_width > 0:
            target_w = min(target_w, max_width)
        elif target_w > avail_w:
            target_w = avail_w

        target_h = max(1, int(round(image.height() * target_w / image.width())))

        fmt = QTextImageFormat()
        fmt.setName(Path(path).resolve().as_uri())
        fmt.setWidth(target_w)
        fmt.setHeight(target_h)

        # Smooth high-DPI resource registration
        self._register_smooth_resource(fmt.name(), image, target_w, target_h)

        self.textCursor().insertImage(fmt)
        self.image_added.emit()

    def _constrain_all_images(self) -> None:
        """Ensures all images in the document fit viewport width and use high-DPI smooth filtering."""
        avail_w = max(240, self.viewport().width() - 36)
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.isImageFormat():
                    img_fmt = fmt.toImageFormat()
                    src = QUrl(img_fmt.name()).toLocalFile() or img_fmt.name()
                    img = QImage(src)
                    if not img.isNull():
                        curr_w = img_fmt.width()
                        target_w = curr_w
                        if curr_w <= 0 or curr_w > avail_w:
                            target_w = min(img.width(), avail_w)
                        target_h = max(1, int(round(img.height() * target_w / img.width())))
                        img_fmt.setWidth(target_w)
                        img_fmt.setHeight(target_h)
                        self._register_smooth_resource(img_fmt.name(), img, target_w, target_h)
                        cur = QTextCursor(doc)
                        cur.setPosition(frag.position())
                        cur.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                        cur.setCharFormat(img_fmt)
                it += 1
            block = block.next()

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
            self._constrain_all_images()
            return
        super().insertFromMimeData(source)

    def _data_uri_to_file(self, m: re.Match) -> str:
        import base64

        try:
            image = QImage.fromData(base64.b64decode(m.group(2)))
            return f'src="{self.save_image(image).as_uri()}"'
        except Exception:  # noqa: BLE001
            return m.group(0)

    # ---------------------------------------------------------------- image interaction & resizing
    def image_at_cursor(self, cursor: QTextCursor | None = None) -> tuple[QTextCursor, QTextImageFormat] | None:
        """Finds image format under or directly adjacent to cursor position."""
        if cursor is None:
            cursor = self.textCursor()
        if cursor.hasSelection() and cursor.charFormat().isImageFormat():
            return cursor, cursor.charFormat().toImageFormat()
        # Look 1 step to right
        c_r = QTextCursor(cursor)
        c_r.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
        if c_r.charFormat().isImageFormat():
            return c_r, c_r.charFormat().toImageFormat()
        # Look 1 step to left
        c_l = QTextCursor(cursor)
        c_l.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor)
        if c_l.charFormat().isImageFormat():
            return c_l, c_l.charFormat().toImageFormat()
        return None

    def image_at_pos(self, pos: QPoint) -> tuple[QTextCursor, QTextImageFormat] | None:
        cursor = self.cursorForPosition(pos)
        return self.image_at_cursor(cursor)

    def _image_at_doc_pos(self, pos: int) -> tuple[QTextCursor, QTextImageFormat] | None:
        cursor = QTextCursor(self.document())
        if pos < 0 or pos + 1 >= self.document().characterCount():
            return None
        cursor.setPosition(pos)
        cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
        fmt = cursor.charFormat()
        return (cursor, fmt.toImageFormat()) if fmt.isImageFormat() else None

    def _image_rect(self, pos: int) -> QRect | None:
        """Viewport rectangle of the picture at document position *pos* (approximate for inline images)."""
        found = self._image_at_doc_pos(pos)
        if not found:
            return None
        _, fmt = found
        c = QTextCursor(self.document())
        c.setPosition(pos)
        left = self.cursorRect(c)
        c.setPosition(pos + 1)
        right = self.cursorRect(c)
        w = int(fmt.width()) or max(1, right.left() - left.left())
        h = int(fmt.height()) or left.height()
        return QRect(left.left(), left.bottom() - h + 1, w, h)

    def _handle_rect(self) -> QRect | None:
        if self._active_image is None:
            return None
        rect = self._image_rect(self._active_image)
        if rect is None:
            return None
        return QRect(rect.right() - HANDLE + 2, rect.bottom() - HANDLE + 2, HANDLE, HANDLE)

    def _track_image(self) -> None:
        cursor = self.textCursor()
        pos = None
        if cursor.hasSelection() and cursor.selectionEnd() - cursor.selectionStart() == 1:
            if self._image_at_doc_pos(cursor.selectionStart()):
                pos = cursor.selectionStart()
        if pos != self._active_image:
            self._active_image = pos
            self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._active_image is None:
            return
        rect = self._image_rect(self._active_image)
        if rect is None:
            return
        p = QPainter(self.viewport())
        accent = QColor("#2f6feb")
        pen = QPen(accent)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.fillRect(QRect(rect.right() - HANDLE + 2, rect.bottom() - HANDLE + 2, HANDLE, HANDLE), accent)
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            handle = self._handle_rect()
            if handle is not None and handle.adjusted(-3, -3, 3, 3).contains(event.pos()):
                found = self._image_at_doc_pos(self._active_image)
                if found:
                    _, fmt = found
                    w = int(fmt.width()) or 100
                    h = int(fmt.height()) or 100
                    self._drag = (event.pos(), w, h, w / max(1, h))
                    event.accept()
                    return
            found = self.image_at_pos(event.pos())
            if found:
                cursor, _ = found
                self.setTextCursor(cursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and self._active_image is not None:
            start, w, h, ratio = self._drag
            found = self._image_at_doc_pos(self._active_image)
            if found:
                cursor, fmt = found
                new_w = max(20, w + event.pos().x() - start.x())
                fmt.setWidth(new_w)
                fmt.setHeight(max(1, int(round(new_w / ratio))))
                cursor.setCharFormat(fmt)  # cheap preview; smooth scaling on release
                self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)
        handle = self._handle_rect()
        if handle is not None and handle.adjusted(-3, -3, 3, 3).contains(event.pos()):
            self.viewport().setCursor(Qt.SizeFDiagCursor)
        elif self.viewport().cursor().shape() == Qt.SizeFDiagCursor:
            self.viewport().setCursor(Qt.IBeamCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is not None:
            self._drag = None
            if self._active_image is not None:
                found = self._image_at_doc_pos(self._active_image)
                if found:
                    _, fmt = found
                    self.resize_image(int(fmt.width()), int(fmt.height()), found)
                    self.document().setModified(True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            found = self.image_at_pos(event.pos())
            if found:
                self.prompt_resize_image(found)
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        found = self.image_at_pos(event.pos()) or self.image_at_cursor()
        if found:
            cursor, fmt = found
            self.setTextCursor(cursor)
            menu = self.createStandardContextMenu()
            menu.addSeparator()
            img_menu = menu.addMenu("📐 " + t("image.menu_title"))
            act_dlg = img_menu.addAction(t("image.resize_dialog"))
            act_dlg.triggered.connect(lambda: self.prompt_resize_image(found))
            act_fit = img_menu.addAction(t("image.fit_width"))
            act_fit.triggered.connect(lambda: self.resize_image_to_fit(found))
            act_75 = img_menu.addAction("75%")
            act_75.triggered.connect(lambda: self.resize_image_percent(found, 0.75))
            act_50 = img_menu.addAction("50%")
            act_50.triggered.connect(lambda: self.resize_image_percent(found, 0.50))
            act_25 = img_menu.addAction("25%")
            act_25.triggered.connect(lambda: self.resize_image_percent(found, 0.25))
            act_100 = img_menu.addAction(t("image.original_size"))
            act_100.triggered.connect(lambda: self.resize_image_original(found))
            img_menu.addSeparator()
            act_del = img_menu.addAction(t("image.delete"))
            act_del.triggered.connect(lambda: self.delete_image(found))
            menu.exec(event.globalPos())
            return
        super().contextMenuEvent(event)

    def prompt_resize_image(self, found: tuple[QTextCursor, QTextImageFormat] | None = None) -> bool:
        """Opens interactive ImageResizeDialog to modify image dimensions."""
        if found is None:
            found = self.image_at_cursor()
        if not found:
            QMessageBox.information(self, "AutoTemplates", t("image.no_image_selected"))
            return False
        cursor, fmt = found
        src = QUrl(fmt.name()).toLocalFile() or fmt.name()
        img = QImage(src)
        orig_w = img.width() if not img.isNull() else int(fmt.width() or 600)
        orig_h = img.height() if not img.isNull() else int(fmt.height() or 400)
        curr_w = int(fmt.width() or orig_w)
        curr_h = int(fmt.height() or orig_h)
        avail_w = max(240, self.viewport().width() - 36)

        dlg = ImageResizeDialog(self, orig_w, orig_h, curr_w, curr_h, avail_w)
        if dlg.exec():
            if dlg.should_delete:
                return self.delete_image(found)
            w, h = dlg.get_dimensions()
            return self.resize_image(w, h, found)
        return False

    def resize_image(
        self,
        width: int,
        height: int | None = None,
        found: tuple[QTextCursor, QTextImageFormat] | None = None,
    ) -> bool:
        if found is None:
            found = self.image_at_cursor()
        if not found:
            return False
        cursor, fmt = found
        src = QUrl(fmt.name()).toLocalFile() or fmt.name()
        image = QImage(src)
        if not image.isNull() and image.width():
            if height is None or height <= 0:
                height = max(1, int(round(image.height() * width / image.width())))
            self._register_smooth_resource(fmt.name(), image, width, height)
        elif height is None:
            height = max(1, int(round((fmt.height() or width) * width / (fmt.width() or width))))

        fmt.setWidth(width)
        fmt.setHeight(height)
        cursor.setCharFormat(fmt)
        return True

    def resize_image_to_fit(self, found: tuple[QTextCursor, QTextImageFormat] | None = None) -> bool:
        avail_w = max(240, self.viewport().width() - 36)
        if found is None:
            found = self.image_at_cursor()
        if not found:
            return False
        _, fmt = found
        src = QUrl(fmt.name()).toLocalFile() or fmt.name()
        img = QImage(src)
        orig_w = img.width() if not img.isNull() else int(fmt.width() or 600)
        target_w = min(orig_w, avail_w)
        return self.resize_image(target_w, None, found)

    def resize_image_percent(self, found: tuple[QTextCursor, QTextImageFormat] | None, frac: float) -> bool:
        if found is None:
            found = self.image_at_cursor()
        if not found:
            return False
        _, fmt = found
        src = QUrl(fmt.name()).toLocalFile() or fmt.name()
        img = QImage(src)
        orig_w = img.width() if not img.isNull() else int(fmt.width() or 600)
        target_w = max(20, int(round(orig_w * frac)))
        return self.resize_image(target_w, None, found)

    def resize_image_original(self, found: tuple[QTextCursor, QTextImageFormat] | None = None) -> bool:
        if found is None:
            found = self.image_at_cursor()
        if not found:
            return False
        _, fmt = found
        src = QUrl(fmt.name()).toLocalFile() or fmt.name()
        img = QImage(src)
        orig_w = img.width() if not img.isNull() else int(fmt.width() or 600)
        orig_h = img.height() if not img.isNull() else int(fmt.height() or 400)
        return self.resize_image(orig_w, orig_h, found)

    def delete_image(self, found: tuple[QTextCursor, QTextImageFormat] | None = None) -> bool:
        if found is None:
            found = self.image_at_cursor()
        if not found:
            return False
        cursor, _ = found
        cursor.removeSelectedText()
        return True

    # ---------------------------------------------------------------- shortcuts
    def format_command(self, event) -> str | None:
        """Name of the formatting command for a key event, or None (see FORMAT_SHORTCUTS)."""
        if self.isReadOnly():
            return None
        key = event.key()
        mods = event.modifiers() & ~Qt.KeypadModifier
        if key in _MODIFIER_KEYS or not (mods & Qt.ControlModifier):
            return None
        ctrl_alt = Qt.ControlModifier | Qt.AltModifier
        text = event.text()
        if (mods & ctrl_alt) == ctrl_alt and text and text.isprintable():
            base = chr(key).lower() if key < 0x80 else ""
            if text.lower() != base:
                return None  # AltGr produced a character (ă, î, ~ …): typing wins
        seq = QKeySequence(QKeyCombination(mods, Qt.Key(key))).toString(QKeySequence.PortableText)
        return _KEYMAP.get(seq)

    def event(self, e) -> bool:
        # Claim our shortcuts before window-level actions (Ctrl+S, Ctrl+N …) or global ones can take them.
        if e.type() == QEvent.ShortcutOverride and self.format_command(e):
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, event) -> None:
        cmd = self.format_command(event)
        if cmd:
            self.run_format(cmd)
            event.accept()
            return
        super().keyPressEvent(event)

    def run_format(self, name: str) -> None:
        """Runs a formatting command by name; used by shortcuts and toolbar buttons."""
        actions = {
            "bold": self.toggle_bold,
            "italic": self.toggle_italic,
            "underline": self.toggle_underline,
            "strike": self.toggle_strike,
            "superscript": lambda: self.set_vertical(QTextCharFormat.AlignSuperScript),
            "subscript": lambda: self.set_vertical(QTextCharFormat.AlignSubScript),
            "clear": self.clear_formatting,
            "bullets": lambda: self.toggle_list(QTextListFormat.ListDisc),
            "numbers": lambda: self.toggle_list(QTextListFormat.ListDecimal),
            "indent": lambda: self.change_indent(1),
            "outdent": lambda: self.change_indent(-1),
            "h1": lambda: self.set_heading(1),
            "h2": lambda: self.set_heading(2),
            "h3": lambda: self.set_heading(3),
            "normal": lambda: self.set_heading(0),
            "left": lambda: self.set_alignment(Qt.AlignLeft),
            "center": lambda: self.set_alignment(Qt.AlignHCenter),
            "right": lambda: self.set_alignment(Qt.AlignRight),
            "justify": lambda: self.set_alignment(Qt.AlignJustify),
            "link": self.prompt_link,
            "paste_plain": self.paste_plain,
        }
        fn = actions.get(name)
        if fn is not None:
            fn()
            self.setFocus()

    def _all_selected(self, test) -> bool:
        """True when every text fragment of the selection passes *test* (Word-like toggling)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return bool(test(self.currentCharFormat()))
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        seen = False
        block = self.document().findBlock(start)
        while block.isValid() and block.position() < end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                a, b = max(start, frag.position()), min(end, frag.position() + frag.length())
                if a < b and not frag.charFormat().isImageFormat():
                    if not test(frag.charFormat()):
                        return False
                    seen = True
                it += 1
            block = block.next()
        return seen

    def toggle_bold(self) -> None:
        self.set_bold(not self._all_selected(lambda f: f.fontWeight() >= QFont.DemiBold))

    def toggle_italic(self) -> None:
        self.set_italic(not self._all_selected(lambda f: f.fontItalic()))

    def toggle_underline(self) -> None:
        self.set_underline(not self._all_selected(lambda f: f.fontUnderline()))

    def toggle_strike(self) -> None:
        self.set_strike(not self._all_selected(lambda f: f.fontStrikeOut()))

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
        if not self.textCursor().hasSelection() and not self.currentCharFormat().isImageFormat():
            fmt = self.currentCharFormat()
            self.setCurrentCharFormat(change(fmt) or fmt)

    def clear_formatting(self) -> None:
        """Removes character and paragraph formatting from the selection (or the current paragraph).

        Pictures and links stay; headings, lists, alignment, spacing and indents go.
        """
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.BlockUnderCursor)
            self.setTextCursor(cursor)
        start, end = cursor.selectionStart(), cursor.selectionEnd()

        def plain(fmt: QTextCharFormat) -> QTextCharFormat:
            clean = QTextCharFormat()
            if fmt.isAnchor():
                clean.setAnchor(True)
                clean.setAnchorHref(fmt.anchorHref())
            return clean

        cursor.beginEditBlock()
        self._each_fragment(plain)
        block = self.document().findBlock(start)
        while block.isValid() and block.position() <= end:
            lst = block.textList()
            if lst is not None:
                lst.remove(block)
            QTextCursor(block).setBlockFormat(QTextBlockFormat())
            block = block.next()
        cursor.endEditBlock()

    def clear_all_formatting(self) -> None:
        """Clear formatting for the whole document (e.g. text pasted with unwanted styles)."""
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        self.setTextCursor(cursor)
        self.clear_formatting()
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

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
        elif current is not None:
            lf = current.format()  # other list type: switch it, like Word (no nesting)
            lf.setStyle(style)
            current.setFormat(lf)
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
    def prompt_link(self) -> None:
        url, ok = QInputDialog.getText(self, t("fmt.link"), "URL:",
                                       text=self.textCursor().charFormat().anchorHref() or "https://")
        if ok and url.strip():
            self.insert_link(url.strip())

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
        lambda m: m.group(0)
        if re.match(r"^(file|https?|data):", m.group(2), re.I)
        else f"{m.group(1)}{(html_path.parent / m.group(2)).resolve().as_uri()}{m.group(3)}",
        markup,
    )
    edit.setHtml(markup)
    if hasattr(edit, "_constrain_all_images"):
        edit._constrain_all_images()
    doc.setModified(False)


__all__ = ["ImageResizeDialog", "RichEdit", "localize_images", "load_document"]
