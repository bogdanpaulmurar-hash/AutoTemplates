"""User guide window: section list, search and the section text (content from core/guide.py)."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSplitter,
                               QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from autotemplates.core import guide
from autotemplates.core.library import fold
from autotemplates.core.shortcuts import HELP_KEY
from autotemplates.i18n import get_language, t
from autotemplates.ui import theme

ROLE_ID = Qt.UserRole + 1
_LOOSE = {"a": "[aăâ]", "i": "[iî]", "s": "[sșş]", "t": "[tțţ]"}


def _loose_pattern(word: str) -> str:
    """Regex that finds the word with or without Romanian diacritics ("restaureaza" → "restaurează")."""
    return "".join(_LOOSE.get(c, QRegularExpression.escape(c)) for c in fold(word))


class HelpWindow(QDialog):
    """Non-modal window; rebuilt on every open so hotkeys, settings, language and theme are current."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.controller = controller
        self.setModal(False)
        self.setObjectName("HelpWindow")
        self.setWindowIcon(theme.app_icon())
        self.resize(900, 620)
        self._sections: list[guide.Section] = []
        self._current = guide.START

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        root.addLayout(top)

        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        self.list.currentItemChanged.connect(lambda item, _prev: self._show(item))
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.list)
        split.addWidget(self.browser)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        split.setSizes([210, 690])
        root.addWidget(split, 1)

        self.none = QLabel()
        self.none.setObjectName("Hint")
        self.none.hide()
        root.addWidget(self.none)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence(HELP_KEY), self, activated=lambda: self.search.setFocus())

    # ------------------------------------------------------------------ public
    def open_section(self, section: str | None = None) -> None:
        """Show the window on a section (None keeps the last one), with fresh content."""
        if section in guide.SECTION_IDS:
            self._current = section
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.rebuild()
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.list.setFocus()

    def rebuild(self) -> None:
        self.setWindowTitle(t("help.title"))
        self.search.setPlaceholderText(t("help.search"))
        self.none.setText(t("help.nothing"))
        self._sections = guide.build(get_language(), self.controller.settings)
        self._filter(self.search.text())

    # ------------------------------------------------------------------ internals
    def _filter(self, text: str) -> None:
        found = guide.search(self._sections, text)
        self.list.blockSignals(True)
        self.list.clear()
        selected = None
        for sec in found:
            item = QListWidgetItem(sec.title)
            item.setData(ROLE_ID, sec.id)
            self.list.addItem(item)
            if sec.id == self._current:
                selected = item
        self.list.blockSignals(False)
        self.none.setVisible(not found)
        if not found:
            self.browser.clear()
            return
        self.list.setCurrentItem(selected or self.list.item(0))
        self._show(self.list.currentItem())

    def _show(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        sid = item.data(ROLE_ID)
        sec = next((s for s in self._sections if s.id == sid), None)
        if sec is None:
            return
        self._current = sid
        self.browser.setHtml(guide.page(sec))
        self._highlight(self.search.text())

    def _highlight(self, text: str) -> None:
        """Mark the search words in the shown section and scroll to the first one."""
        words = [w for w in text.split() if len(w) > 1]
        doc = self.browser.document()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(theme.ACCENT).lighter(150))
        fmt.setForeground(QColor("#000000"))
        marks: list[QTextEdit.ExtraSelection] = []
        for word in words:
            pattern = QRegularExpression(_loose_pattern(word), QRegularExpression.CaseInsensitiveOption)
            cursor = QTextCursor(doc)
            while True:
                cursor = doc.find(pattern, cursor)
                if cursor.isNull() or not cursor.hasSelection():
                    break
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cursor
                sel.format = fmt
                marks.append(sel)
        self.browser.setExtraSelections(marks)
        if marks:
            first = min(marks, key=lambda m: m.cursor.position())
            self.browser.setTextCursor(QTextCursor(first.cursor))
            self.browser.ensureCursorVisible()
            cursor = self.browser.textCursor()
            cursor.clearSelection()
            self.browser.setTextCursor(cursor)
        else:
            self.browser.moveCursor(QTextCursor.Start)
