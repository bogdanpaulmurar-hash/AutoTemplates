"""NoteIT - quick note with a rich editor: copy, save as a template, Outlook mail, OneNote page.

The window is a normal top-level window (taskbar button, can be minimised) and
optionally stays on top. Closing it without finishing keeps a draft on disk;
finishing a note (copy, save, mail, OneNote) starts the next one empty, and
"Last note" brings the finished one back.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from autotemplates.core import formats
from autotemplates.i18n import t
from autotemplates.ui import theme
from autotemplates.ui.richedit import RichEdit, localize_images, with_shortcut

log = logging.getLogger(__name__)

OTHER_LOCATION = "\x00other"  # item data of the "Other location..." folder entry
AUTOSAVE_MS = 5000


def safe_file_name(title: str) -> str:
    name = "".join(c for c in title if c not in '<>:"/\\|?*' and ord(c) >= 32).strip().rstrip(".")
    return name[:120] or "note"


def unique_path(folder: Path, stem: str, suffix: str = ".html") -> Path:
    target = folder / f"{stem}{suffix}"
    i = 1
    while target.exists():
        target = folder / f"{stem} ({i}){suffix}"
        i += 1
    return target


class NoteITWindow(QWidget):
    """Quick-note window for drafting notes, checklists and quick e-mails."""

    closed = Signal()

    def __init__(self, controller) -> None:
        super().__init__(None)
        self.controller = controller
        self.setObjectName("NoteITWindow")
        self.setWindowTitle(t("noteit.window_title"))
        self.setWindowIcon(theme.app_icon())
        self.resize(560, 600)
        self.setMinimumSize(400, 420)

        self.state_dir = self.controller.paths.data_dir / "noteit"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._finished = False  # the content was copied/saved/sent: the next open starts empty
        self._title_saved = ""

        flags = (Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint
                 | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        if bool(self.controller.settings.get("noteit_stay_on_top", True)):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        self._setup_ui()
        self._load_draft()

        self._autosave = QTimer(self)
        self._autosave.setInterval(AUTOSAVE_MS)
        self._autosave.timeout.connect(self._autosave_tick)
        self._autosave.start()

    # ================================================================ UI
    def _setup_ui(self) -> None:
        c = theme.colors(self.controller.settings.get("theme", "dark"))
        self.setStyleSheet(f"""
            QWidget#NoteITWindow {{ background: {c['bg']}; }}
            QLineEdit#NoteTitle {{
                font-size: 13pt; font-weight: bold; padding: 6px 10px; border-radius: 6px;
                background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
            }}
            QLineEdit#NoteTitle:focus {{ border: 1px solid {theme.ACCENT}; }}
            QComboBox {{
                padding: 4px 8px; border-radius: 6px;
                background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
            }}
            QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px; }}
            QToolButton:hover {{ background: {c['hover']}; border: 1px solid {c['border']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Top bar: folder, time stamp, new/last note, pin
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)
        lbl_folder = QLabel(t("noteit.folder"))
        lbl_folder.setStyleSheet(f"color: {c['muted']}; font-weight: 500;")
        top_bar.addWidget(lbl_folder)

        self.combo_folder = QComboBox()
        self.combo_folder.setEditable(True)  # a new sub-folder can be typed ("Notes/Meetings")
        self.combo_folder.setMinimumWidth(180)
        self.combo_folder.setToolTip(t("noteit.folder_tip"))
        self.combo_folder.activated.connect(self._folder_activated)
        top_bar.addWidget(self.combo_folder, 1)

        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet(f"color: {c['muted']}; font-size: 8.5pt;")
        top_bar.addWidget(self.lbl_time)

        self.btn_new = self._tool_button("new", t("noteit.new_note"), self.new_note)
        top_bar.addWidget(self.btn_new)
        self.btn_last = self._tool_button("undo", t("noteit.last_note"), self.restore_last)
        top_bar.addWidget(self.btn_last)

        self.btn_pin = QToolButton()
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(bool(self.controller.settings.get("noteit_stay_on_top", True)))
        self.btn_pin.setToolTip(t("noteit.stay_on_top"))
        self._update_pin_icon()
        self.btn_pin.toggled.connect(self._toggle_stay_on_top)
        top_bar.addWidget(self.btn_pin)
        layout.addLayout(top_bar)

        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("NoteTitle")
        self.title_edit.setPlaceholderText(t("noteit.title_placeholder"))
        layout.addWidget(self.title_edit)

        # Pasted/dropped pictures stay in the local cache until the note is saved.
        cache_dir = self.controller.paths.data_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.editor = RichEdit(cache_dir, self)
        self.editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.editor)
        layout.addWidget(self._create_formatting_toolbar())

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_copy_close = QPushButton(t("noteit.copy_close"))
        self.btn_copy_close.setToolTip("Ctrl+Enter")
        self.btn_copy_close.setStyleSheet(f"background: {theme.ACCENT}; color: white; font-weight: bold; "
                                          "padding: 6px 14px; border-radius: 6px;")
        self.btn_copy_close.clicked.connect(self._copy_and_close)
        bar.addWidget(self.btn_copy_close)

        self.btn_save = QPushButton(t("noteit.save"))
        self.btn_save.setToolTip("Ctrl+S")
        self.btn_save.setIcon(theme.glyph_icon("save"))
        self.btn_save.clicked.connect(lambda: self._save_note())
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

    def _tool_button(self, icon: str, tip: str, slot) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(theme.glyph_icon(icon))
        btn.setToolTip(tip)
        btn.clicked.connect(lambda: slot())
        return btn

    def _create_formatting_toolbar(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        for icon, tip, name in (
            ("bold", "noteit.fmt_bold", "bold"),
            ("italic", "noteit.fmt_italic", "italic"),
            ("underline", "noteit.fmt_underline", "underline"),
            ("strike", "noteit.fmt_strike", "strike"),
            ("bullets", "noteit.fmt_bullets", "bullets"),
            ("numbers", "noteit.fmt_numbers", "numbers"),
        ):
            lay.addWidget(self._tool_button(icon, with_shortcut(t(tip), name), lambda n=name: self.editor.run_format(n)))
        lay.addWidget(self._tool_button("highlight", t("noteit.fmt_highlight"),
                                        lambda: self.editor.set_highlight(QColor("#fff3b0"))))
        lay.addWidget(self._clear_button())
        lay.addWidget(self._tool_button("image", t("noteit.fmt_image"), self._insert_image))
        lay.addWidget(self._tool_button("resize", t("fmt.resize_tip"), lambda: self.editor.prompt_resize_image()))
        hint = QLabel(t("noteit.shortcuts_hint"))
        hint.setToolTip(t("noteit.shortcuts_tip"))
        hint.setStyleSheet("color: #9a9eab; font-size: 8.5pt;")
        lay.addSpacing(6)
        lay.addWidget(hint)
        lay.addStretch(1)
        return w

    def _insert_image(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(formats.IMAGE_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, t("fmt.image"), str(Path.home() / "Pictures"),
                                                f"Images ({exts})")
        for f in files:
            self.editor.insert_image_file(Path(f))

    def _clear_button(self) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(theme.glyph_icon("clear"))
        btn.setToolTip(with_shortcut(t("noteit.fmt_clear"), "clear"))
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        btn.clicked.connect(lambda: self.editor.run_format("clear"))
        menu = QMenu(btn)
        menu.addAction(with_shortcut(t("fmt.clear"), "clear"), lambda: self.editor.run_format("clear"))
        menu.addAction(t("fmt.clear_all"), self.editor.clear_all_formatting)
        menu.addAction(with_shortcut(t("fmt.paste_plain"), "paste_plain"), lambda: self.editor.run_format("paste_plain"))
        btn.setMenu(menu)
        return btn

    def _update_pin_icon(self) -> None:
        self.btn_pin.setIcon(theme.glyph_icon("pin" if self.btn_pin.isChecked() else "unpin"))

    def _toggle_stay_on_top(self, checked: bool) -> None:
        self._update_pin_icon()
        self.controller.settings.set("noteit_stay_on_top", checked)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    # ================================================================ folders
    def _library_folders(self) -> list[str]:
        lib = self.controller.library
        root = Path(lib.root)
        rels: set[str] = set()
        try:
            for folder in lib.folders():
                if folder != root:
                    rels.add(folder.relative_to(root).as_posix())
        except (OSError, ValueError):
            log.debug("Listing library folders failed", exc_info=True)
        rels.update(c for c in lib.categories() if c)
        return sorted(rels, key=str.casefold)

    def _populate_folders(self, wanted: str = "") -> None:
        wanted = wanted or self.combo_folder.currentText().strip()
        default = str(self.controller.settings.get("noteit_folder", "Notes") or "Notes")
        self.combo_folder.blockSignals(True)
        self.combo_folder.clear()
        folders = self._library_folders()
        if default not in folders:
            folders.insert(0, default)
        for f in folders:
            self.combo_folder.addItem(f, f)
        self.combo_folder.insertSeparator(self.combo_folder.count())
        self.combo_folder.addItem(t("noteit.other_location"), OTHER_LOCATION)
        wanted = wanted if wanted and wanted != t("noteit.other_location") else default
        idx = self.combo_folder.findText(wanted)
        if idx >= 0:
            self.combo_folder.setCurrentIndex(idx)
        else:
            self.combo_folder.setEditText(wanted)  # a new sub-folder typed earlier
        self.combo_folder.blockSignals(False)

    def _folder_activated(self, index: int) -> None:
        if self.combo_folder.itemData(index) == OTHER_LOCATION:
            self._populate_folders(self._read_state("draft").get("folder", ""))
            self._save_note(other_location=True)

    # ================================================================ state
    def is_empty(self) -> bool:
        return (not self.title_edit.text().strip() and not self.editor.toPlainText().strip()
                and "<img" not in self.editor.toHtml())

    def _refresh_time(self) -> None:
        self.lbl_time.setText(datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))

    def reset_form(self, title: str = "", content_html: str = "") -> None:
        """Fills the form (template/clipboard content) or empties it."""
        self._refresh_time()
        self._populate_folders(str(self.controller.settings.get("noteit_folder", "Notes") or "Notes"))
        self.title_edit.setText(title)
        self.editor.setHtml(content_html or "<p></p>")
        self._finished = False
        self._write_draft()

    def prepare_to_show(self) -> None:
        """Called before every show: a finished note gives way to a new one."""
        if self._finished:
            self.reset_form()
        else:
            self._refresh_time()
            self._populate_folders()

    def new_note(self) -> None:
        if not self._finished:
            self._store_last()
        self.reset_form()
        self.title_edit.setFocus()

    def restore_last(self) -> None:
        data = self._read_state("last")
        if not data:
            self.controller.notify(t("noteit.no_last"))
            return
        if not self._finished:
            self._store_last()  # swap: the current draft becomes "last"
        self.title_edit.setText(data.get("title", ""))
        self.editor.setHtml(data.get("html") or "<p></p>")
        self._populate_folders(data.get("folder", ""))
        self._finished = False
        self._write_draft()

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        (self.editor if self.title_edit.text().strip() else self.title_edit).setFocus()

    def _finish(self) -> None:
        """The note did its job: keep it as "last", drop the draft, hide the window."""
        self._store_last()
        self._finished = True
        self._delete_state("draft")
        self.hide()

    # ---------------------------------------------------------------- persistence
    def _state_file(self, name: str) -> Path:
        return self.state_dir / f"{name}.json"

    def _snapshot(self) -> dict:
        return {"title": self.title_edit.text(), "html": self.editor.toHtml(),
                "folder": self.combo_folder.currentText().strip(),
                "time": datetime.datetime.now().isoformat(timespec="seconds")}

    def _write_state(self, name: str, data: dict) -> None:
        path = self._state_file(name)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            log.warning("Could not write NoteIT %s", name, exc_info=True)

    def _read_state(self, name: str) -> dict:
        try:
            data = json.loads(self._state_file(name).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _delete_state(self, name: str) -> None:
        try:
            self._state_file(name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            log.debug("Could not delete NoteIT %s", name, exc_info=True)

    def _store_last(self) -> None:
        if not self.is_empty():
            self._write_state("last", self._snapshot())

    def _write_draft(self) -> None:
        if self._finished or self.is_empty():
            self._delete_state("draft")
        else:
            self._write_state("draft", self._snapshot())
        self.editor.document().setModified(False)
        self._title_saved = self.title_edit.text()

    def _autosave_tick(self) -> None:
        if self.editor.document().isModified() or self.title_edit.text() != self._title_saved:
            self._write_draft()

    def _load_draft(self) -> None:
        self._refresh_time()
        data = self._read_state("draft")
        self._populate_folders(data.get("folder", ""))
        if data:
            self.title_edit.setText(data.get("title", ""))
            self.editor.setHtml(data.get("html") or "<p></p>")
        self.editor.document().setModified(False)
        self._title_saved = self.title_edit.text()

    # ================================================================ actions
    def _title(self, fallback_key: str = "noteit.untitled") -> str:
        return self.title_edit.text().strip() or t(fallback_key)

    def _copy_and_close(self) -> None:
        from autotemplates.ui.inserter import build_mime

        html = self.controller.inserter.clipboard_html(self.editor.toHtml())
        QGuiApplication.clipboard().setMimeData(build_mime(html, self.editor.toPlainText()))
        self._finish()
        self.controller.notify(t("noteit.copied"))

    def _target_for_save(self, other_location: bool) -> Path | None:
        stem = safe_file_name(self._title())
        if other_location:
            start = str(self.controller.settings.get("noteit_last_dir") or Path.home() / "Documents")
            path, _ = QFileDialog.getSaveFileName(self, t("noteit.save_as"), str(Path(start) / f"{stem}.html"),
                                                  "HTML (*.html *.htm)")
            if not path:
                return None
            target = Path(path)
            if target.suffix.lower() not in (".html", ".htm"):
                target = target.with_suffix(".html")
            self.controller.settings.set("noteit_last_dir", str(target.parent))
            return target
        folder = self.combo_folder.currentText().strip().strip("/\\") or "Notes"
        root = Path(self.controller.library.root).resolve()
        target_dir = (root / folder).resolve()
        if root not in (target_dir, *target_dir.parents):  # "..\.." typed in the box
            target_dir = root / "Notes"
        target_dir.mkdir(parents=True, exist_ok=True)
        return unique_path(target_dir, safe_file_name(stem))

    def _save_note(self, *, other_location: bool = False) -> None:
        try:
            target = self._target_for_save(other_location)
            if target is None:
                return
            markup = localize_images(self.editor.toHtml(), target)  # pictures -> "<name>.assets"
            target.write_text(markup, encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, t("noteit.error"), t("noteit.save_failed", error=e))
            return
        if not other_location:
            self.controller.settings.set("noteit_folder", self.combo_folder.currentText().strip() or "Notes")
            self.controller.rescan()
        self.controller.notify(t("noteit.saved", name=target.name))
        self._finish()

    def _send_via_email(self) -> None:
        from autotemplates.platform import office

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            office.open_outlook_mail(self._title("noteit.default_subject"), self.editor.toHtml())
        except office.OfficeUnavailable as e:
            log.info("Outlook unavailable (%s); using mailto", e)
            QApplication.restoreOverrideCursor()
            self._mailto_fallback()
            return
        QApplication.restoreOverrideCursor()
        self._finish()

    def _mailto_fallback(self) -> None:
        import urllib.parse

        subject = urllib.parse.quote(self._title("noteit.default_subject"))
        body = urllib.parse.quote(self.editor.toPlainText()[:1800])  # mailto URLs are length-limited
        QDesktopServices.openUrl(QUrl(f"mailto:?subject={subject}&body={body}"))
        self.controller.notify(t("noteit.mail_plain"))

    def _send_to_onenote(self) -> None:
        from autotemplates.platform import office

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            sections = office.onenote_sections()
        except office.OfficeUnavailable as e:
            log.info("OneNote unavailable (%s); copying instead", e)
            sections = []
        finally:
            QApplication.restoreOverrideCursor()
        if not sections:
            self._onenote_fallback()
            return
        dlg = OneNoteSectionDialog(sections, str(self.controller.settings.get("noteit_onenote_section") or ""), self)
        if dlg.exec() != QDialog.Accepted or dlg.selected() is None:
            return
        section = dlg.selected()
        self.controller.settings.set("noteit_onenote_section", section.id)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            office.create_onenote_page(section.id, self._title(), self.editor.toHtml())
        except office.OfficeUnavailable as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "OneNote", t("noteit.onenote_failed", error=e))
            return
        QApplication.restoreOverrideCursor()
        self.controller.notify(t("noteit.onenote_done", section=section.path))
        self._finish()

    def _onenote_fallback(self) -> None:
        self._copy_and_close()
        if not QDesktopServices.openUrl(QUrl("onenote:")):
            log.debug("onenote: protocol not registered")
        self.controller.notify(t("noteit.onenote_paste"))

    # ================================================================ events
    def keyPressEvent(self, event) -> None:
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key_Escape:
            self.close()
            return
        if mods == Qt.ControlModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            self._copy_and_close()
            return
        if mods == Qt.ControlModifier and key == Qt.Key_S:
            self._save_note()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """Closing only hides the window; the draft stays for next time."""
        self._write_draft()
        event.ignore()
        self.hide()
        self.closed.emit()


class OneNoteSectionDialog(QDialog):
    """Pick the OneNote notebook / section for the new page (with a filter)."""

    def __init__(self, sections, current_id: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("noteit.onenote_pick"))
        self.resize(460, 420)
        lay = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(t("noteit.onenote_filter"))
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.list = QListWidget()
        for s in sections:
            item = QListWidgetItem(s.path)
            item.setData(Qt.UserRole, s)
            self.list.addItem(item)
            if s.id == current_id:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        lay.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.filter.setFocus()

    def _apply_filter(self, text: str) -> None:
        needle = text.casefold().strip()
        first = None
        for i in range(self.list.count()):
            item = self.list.item(i)
            hidden = bool(needle) and needle not in item.text().casefold()
            item.setHidden(hidden)
            if not hidden and first is None:
                first = item
        cur = self.list.currentItem()
        if (cur is None or cur.isHidden()) and first is not None:
            self.list.setCurrentItem(first)

    def selected(self):
        item = self.list.currentItem()
        return None if item is None or item.isHidden() else item.data(Qt.UserRole)


__all__ = ["NoteITWindow", "OneNoteSectionDialog", "safe_file_name", "unique_path"]
