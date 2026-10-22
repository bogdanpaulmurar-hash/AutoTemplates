"""NoteIT - Fast note taker with rich editor, stays-on-top, and direct export."""

from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QGuiApplication, QIcon, QKeySequence, QTextListFormat
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton,
                               QSizePolicy, QToolBar, QToolButton,
                               QVBoxLayout, QWidget)

from autotemplates.i18n import t
from autotemplates.ui import theme
from autotemplates.ui.richedit import RichEdit


class NoteITWindow(QWidget):
    """Sticky-note style modern window for drafting notes, checklists, and quick emails."""

    closed = Signal()

    def __init__(self, controller) -> None:
        super().__init__(None)
        self.controller = controller
        self.setObjectName("NoteITWindow")
        self.setWindowTitle(t("noteit.window_title"))
        self.resize(520, 560)
        self.setMinimumSize(380, 400)

        stay_top = bool(self.controller.settings.get("noteit_stay_on_top", True))
        flags = Qt.Window
        if stay_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        self._setup_ui()

    def _setup_ui(self) -> None:
        c = theme.colors(self.controller.settings.get("theme", "dark"))
        self.setStyleSheet(f"""
            QWidget#NoteITWindow {{
                background: {c['bg']};
            }}
            QLineEdit#NoteTitle {{
                font-size: 13pt;
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 6px;
                background: {c['panel']};
                color: {c['text']};
                border: 1px solid {c['border']};
            }}
            QLineEdit#NoteTitle:focus {{
                border: 1px solid {theme.ACCENT};
            }}
            QComboBox {{
                padding: 4px 8px;
                border-radius: 6px;
                background: {c['panel']};
                color: {c['text']};
                border: 1px solid {c['border']};
            }}
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }}
            QToolButton:hover {{
                background: {c['hover']};
                border: 1px solid {c['border']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Top bar: Folder selector, Pin on Top toggle, and Date/Time stamp
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        lbl_folder = QLabel(t("noteit.folder"))
        lbl_folder.setStyleSheet(f"color: {c['muted']}; font-weight: 500;")
        top_bar.addWidget(lbl_folder)

        self.combo_folder = QComboBox()
        self.combo_folder.setEditable(True)
        self.combo_folder.setMinimumWidth(160)
        top_bar.addWidget(self.combo_folder)

        top_bar.addStretch(1)

        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet(f"color: {c['muted']}; font-size: 8.5pt;")
        top_bar.addWidget(self.lbl_time)

        self.btn_pin = QToolButton()
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(bool(self.controller.settings.get("noteit_stay_on_top", True)))
        self.btn_pin.setToolTip(t("noteit.stay_on_top"))
        self._update_pin_icon()
        self.btn_pin.toggled.connect(self._toggle_stay_on_top)
        top_bar.addWidget(self.btn_pin)

        layout.addLayout(top_bar)

        # Note title
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("NoteTitle")
        self.title_edit.setPlaceholderText(t("noteit.title_placeholder"))
        layout.addWidget(self.title_edit)

        # Rich text editor
        cache_dir = self.controller.paths.data_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.editor = RichEdit(cache_dir, self)
        self.editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.editor)

        # Editor formatting toolbar
        tb = self._create_formatting_toolbar()
        layout.addWidget(tb)

        # Action bar at bottom
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_copy_close = QPushButton(t("noteit.copy_close"))
        self.btn_copy_close.setStyleSheet(f"background: {theme.ACCENT}; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        self.btn_copy_close.clicked.connect(self._copy_and_close)
        bar.addWidget(self.btn_copy_close)

        self.btn_save = QPushButton(t("noteit.save"))
        self.btn_save.clicked.connect(self._save_as_template)
        bar.addWidget(self.btn_save)

        self.btn_email = QPushButton(t("noteit.send_email"))
        self.btn_email.setIcon(theme.glyph_icon("mail"))
        self.btn_email.clicked.connect(self._send_via_email)
        bar.addWidget(self.btn_email)

        self.btn_onenote = QPushButton(t("noteit.send_onenote"))
        self.btn_onenote.setIcon(theme.glyph_icon("onenote"))
        self.btn_onenote.clicked.connect(self._send_to_onenote)
        bar.addWidget(self.btn_onenote)

        layout.addLayout(bar)

    def _create_formatting_toolbar(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        def add_btn(icon_name: str, tip: str, slot):
            btn = QToolButton()
            btn.setIcon(theme.glyph_icon(icon_name))
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        add_btn("bold", "Bold (Ctrl+B)", self.editor.toggle_bold)
        add_btn("italic", "Italic (Ctrl+I)", self.editor.toggle_italic)
        add_btn("underline", "Underline (Ctrl+U)", self.editor.toggle_underline)
        add_btn("strike", "Strikethrough (Ctrl+Shift+X)", self.editor.toggle_strike)
        add_btn("bullets", "Listă cu puncte", lambda: self.editor.toggle_list(QTextListFormat.ListDisc))
        add_btn("numbers", "Listă numerotată", lambda: self.editor.toggle_list(QTextListFormat.ListDecimal))
        add_btn("highlight", "Evidențiere text", lambda: self.editor.set_highlight(QColor("#fff3b0")))
        add_btn("clear", "Curăță formatarea", self.editor.clear_formatting)
        lay.addStretch(1)
        return w

    def _update_pin_icon(self) -> None:
        icon_name = "pin" if self.btn_pin.isChecked() else "unpin"
        self.btn_pin.setIcon(theme.glyph_icon(icon_name))

    def _toggle_stay_on_top(self, checked: bool) -> None:
        self._update_pin_icon()
        self.controller.settings.set("noteit_stay_on_top", checked)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    def _populate_folders(self) -> None:
        self.combo_folder.clear()
        raw_cats = self.controller.library.categories() if callable(getattr(self.controller.library, "categories", None)) else getattr(self.controller.library, "categories", [])
        cats = sorted(list(raw_cats))
        default_folder = str(self.controller.settings.get("noteit_folder", "Notes"))
        if default_folder not in cats:
            cats.insert(0, default_folder)
        for c in cats:
            self.combo_folder.addItem(c)
        idx = self.combo_folder.findText(default_folder)
        if idx >= 0:
            self.combo_folder.setCurrentIndex(idx)

    def _refresh_time(self) -> None:
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        self.lbl_time.setText(now)

    def reset_form(self, title: str = "", content_html: str = "") -> None:
        self._refresh_time()
        self._populate_folders()
        self.title_edit.setText(title)
        self.editor.setHtml(content_html or "<p></p>")
        if not title:
            self.title_edit.setFocus()
        else:
            self.editor.setFocus()

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        if not self.title_edit.text().strip():
            self.title_edit.setFocus()
        else:
            self.editor.setFocus()

    def _copy_and_close(self) -> None:
        from autotemplates.ui.inserter import wrap_cf_html
        html = self.editor.toHtml()
        text = self.editor.toPlainText()
        clipboard = QGuiApplication.clipboard()
        mime = QMimeData()
        mime.setText(text)
        wrapped = wrap_cf_html(html)
        mime.setHtml(wrapped)
        mime.setData("text/html", wrapped.encode("utf-8"))
        clipboard.setMimeData(mime)
        self.hide()
        self.controller.notify(t("noteit.copied"))

    def _save_as_template(self) -> None:
        title = self.title_edit.text().strip() or "Untitled Note"
        folder = self.combo_folder.currentText().strip() or "Notes"
        target_dir = self.controller.library.root / folder
        target_dir.mkdir(parents=True, exist_ok=True)

        clean_name = "".join(c for c in title if c not in '<>:"/\\|?*').strip() or "note"
        target_file = target_dir / f"{clean_name}.html"

        i = 1
        while target_file.exists():
            target_file = target_dir / f"{clean_name} ({i}).html"
            i += 1

        try:
            target_file.write_text(self.editor.toHtml(), encoding="utf-8")
            self.controller.rescan()
            self.controller.notify(t("noteit.saved", name=target_file.name))
            self.hide()
        except OSError as e:
            QMessageBox.warning(self, "Eroare", f"Nu s-a putut salva nota:\n{e}")

    def _send_via_email(self) -> None:
        title = self.title_edit.text().strip() or "Note"
        body = self.editor.toPlainText()
        import urllib.parse
        subject = urllib.parse.quote(title)
        body_encoded = urllib.parse.quote(body)
        mailto = f"mailto:?subject={subject}&body={body_encoded}"
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(mailto))

    def _send_to_onenote(self) -> None:
        self._copy_and_close()
        import subprocess
        try:
            subprocess.Popen(["cmd", "/c", "start", "onenote:"])
        except Exception:
            pass

    def keyPressEvent(self, event) -> None:
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Escape:
            self.hide()
            return
        if mods == Qt.ControlModifier and key == Qt.Key_Return:
            self._copy_and_close()
            return
        if mods == Qt.ControlModifier and key == Qt.Key_S:
            self._save_as_template()
            return
        super().keyPressEvent(event)
