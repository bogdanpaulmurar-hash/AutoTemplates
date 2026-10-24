"""The quick list opened by the hotkey: type to filter, Enter to insert.

Built once and only hidden/shown afterwards, so it opens instantly.

Keys: ↑/↓ PgUp/PgDn choose · Enter insert (formatted) · Shift+Enter insert as plain
text · Ctrl+C copy only · Alt+1…9 insert the n-th · Ctrl+E edit · Ctrl+N new ·
Ctrl+D favourite · Tab next category · Ctrl+G list/groups · Esc close.

Grouped view (``picker_view = "groups"``, see ``core/grouping.py``): ★ Favourites and
Recent on top, then one header per folder. ↑/↓ skip the headers of open groups and stop
on folded ones; ← folds the current group, → (or Enter) opens a folded one,
Ctrl+↑/↓ jump to the previous/next group. While searching every group is open.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QSplitter, QStyle, QStyledItemDelegate, QTextBrowser, QToolButton, QVBoxLayout,
                               QWidget)

from autotemplates.core.formats import LANGUAGE_NAMES
from autotemplates.core.grouping import FAVOURITES, RECENT, Group, folder_title, group_results
from autotemplates.core.library import Template
from autotemplates.i18n import t
from autotemplates.ui import theme

ROLE_REL = Qt.UserRole + 1
ROLE_SUB = Qt.UserRole + 2
ROLE_FAV = Qt.UserRole + 3
ROLE_IS_HEADER = Qt.UserRole + 4
ROLE_GROUP = Qt.UserRole + 5  # group key of a header or of a template inside a group
ROLE_NUM = Qt.UserRole + 6  # Alt+n number (1…9) of a template row
ROLE_COLLAPSED = Qt.UserRole + 7
ROLE_COUNT = Qt.UserRole + 8

KIND_BADGE = {"rich": "Rich", "markdown": "MD", "text": "TXT", "code": "", "docx": "DOCX", "rtf": "RTF", "image": "IMG"}


def kind_label(tpl: Template) -> str:
    if tpl.kind == "code":
        return LANGUAGE_NAMES.get(tpl.language, tpl.language.upper() or "Code")
    return KIND_BADGE.get(tpl.kind, tpl.kind)


class ItemDelegate(QStyledItemDelegate):
    """Two lines per template: name (+ shortcut, star) and category · type · preview.
    Handles visual headers cleanly."""

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        if index.data(ROLE_IS_HEADER):
            return QSize(200, fm.height() + 8)
        return QSize(200, fm.height() * 2 + 14)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        c = theme.colors(self.parent().property("themeMode") or "dark")
        rect = option.rect.adjusted(2, 1, -2, -1)

        if index.data(ROLE_IS_HEADER):
            selected = bool(option.state & QStyle.State_Selected)
            painter.fillRect(rect, QColor(c["select"] if selected else c["panel2"]))
            if selected:
                painter.fillRect(QRect(rect.left(), rect.top() + 3, 3, rect.height() - 6), QColor(theme.ACCENT))
            h_font = QFont(option.font)
            h_font.setBold(True)
            h_font.setPointSize(max(8, option.font.pointSize() - 1))
            painter.setFont(h_font)
            hfm = QFontMetrics(h_font)
            arrow = "▸ " if index.data(ROLE_COLLAPSED) else "▾ "
            count = f"{index.data(ROLE_COUNT)}"
            count_w = hfm.horizontalAdvance(count) + 8
            painter.setPen(QColor(c["muted"]))
            painter.drawText(QRect(rect.right() - count_w - 6, rect.top() + 2, count_w, rect.height() - 4),
                             Qt.AlignRight | Qt.AlignVCenter, count)
            painter.setPen(QColor(theme.ACCENT))
            title = hfm.elidedText(arrow + (index.data(Qt.DisplayRole) or ""), Qt.ElideRight,
                                   rect.width() - count_w - 22)
            painter.drawText(QRect(rect.left() + 8, rect.top() + 2, rect.width() - count_w - 22, rect.height() - 4),
                             Qt.AlignLeft | Qt.AlignVCenter, title)
            painter.setPen(QColor(c["border"]))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
            painter.restore()
            return

        if option.state & QStyle.State_Selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(c["select"]))
            painter.drawRoundedRect(rect, 6, 6)
            painter.fillRect(QRect(rect.left(), rect.top() + 6, 3, rect.height() - 12), QColor(theme.ACCENT))
        elif option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(c["hover"]))
            painter.drawRoundedRect(rect, 6, 6)

        name_font = QFont(option.font)
        name_font.setBold(True)
        fm = QFontMetrics(name_font)
        x, y = rect.left() + 12, rect.top() + 5
        number = index.data(ROLE_NUM)
        if number:
            painter.setPen(QColor(c["muted"]))
            painter.setFont(option.font)
            painter.drawText(QRect(rect.right() - 28, y, 22, fm.height()), Qt.AlignRight, f"{number}")
        painter.setFont(name_font)
        painter.setPen(QColor(c["text"]))
        star = "★ " if index.data(ROLE_FAV) else ""
        name = fm.elidedText(star + (index.data(Qt.DisplayRole) or ""), Qt.ElideRight, rect.width() - 50)
        painter.drawText(QRect(x, y, rect.width() - 50, fm.height()), Qt.AlignLeft, name)
        painter.setFont(option.font)
        painter.setPen(QColor(c["muted"]))
        sub_fm = QFontMetrics(option.font)
        sub = sub_fm.elidedText(index.data(ROLE_SUB) or "", Qt.ElideRight, rect.width() - 24)
        painter.drawText(QRect(x, y + fm.height() + 2, rect.width() - 24, sub_fm.height()), Qt.AlignLeft, sub)
        painter.restore()


class Picker(QWidget):
    insert_requested = Signal(str, bool)  # rel, shift (= the other mode)
    copy_requested = Signal(str, bool)
    edit_requested = Signal(str)
    new_requested = Signal()
    noteit_requested = Signal()
    settings_requested = Signal()
    editor_requested = Signal()
    favourite_toggled = Signal(str)

    def __init__(self, controller) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.controller = controller
        self.setObjectName("Picker")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._results: list[Template] = []
        self._numbered: list[int] = []  # list rows of the templates reachable with Alt+1…9
        self._category: str | None = None
        self._preview_timer = QTimer(self, singleShot=True, interval=60)
        self._preview_timer.timeout.connect(self._update_preview)

        frame = QFrame(self)
        frame.setObjectName("PickerFrame")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        root = QVBoxLayout(frame)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _text: self.refresh())
        self.search.installEventFilter(self)
        self.view_button = QToolButton()
        self.view_button.setIcon(theme.glyph_icon("folder"))
        self.view_button.setCheckable(True)
        self.view_button.setAutoRaise(True)
        self.view_button.toggled.connect(self._view_toggled)
        self.category = QComboBox()
        self.category.setMinimumWidth(150)
        self.category.currentIndexChanged.connect(self._category_changed)
        top.addWidget(self.search, 1)
        top.addWidget(self.view_button)
        top.addWidget(self.category)
        root.addLayout(top)

        self.list = QListWidget()
        self.list.setItemDelegate(ItemDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.installEventFilter(self)
        self.list.currentRowChanged.connect(lambda _: self._preview_timer.start())
        self.list.itemClicked.connect(self._item_clicked)
        self.list.itemDoubleClicked.connect(lambda item: None if item.data(ROLE_IS_HEADER) else self._insert(False))
        self.preview = QTextBrowser()
        self.preview.setObjectName("Paper")  # white page: shows what will be pasted
        self.preview.setOpenLinks(False)
        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.list)
        self.split.addWidget(self.preview)
        self.split.setStretchFactor(0, 5)
        self.split.setStretchFactor(1, 6)
        root.addWidget(self.split, 1)

        bottom = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setObjectName("Hint")
        bottom.addWidget(self.hint, 1)
        for icon, tip, slot in (("note", "picker.noteit", self.noteit_requested.emit),
                                ("new", "picker.new", self.new_requested.emit),
                                ("edit", "picker.edit", self._edit),
                                ("doc", "picker.editor", self.editor_requested.emit),
                                ("settings", "picker.settings", self.settings_requested.emit)):
            b = QToolButton()
            b.setIcon(theme.glyph_icon(icon))
            b.setToolTip(t(tip))
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            bottom.addWidget(b)
        root.addLayout(bottom)

        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._edit)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_requested.emit)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._toggle_fav)
        QShortcut(QKeySequence("Ctrl+C"), self, activated=lambda: self._copy(False))
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=lambda: self._copy(True))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.settings_requested.emit)
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self.view_button.toggle)
        for n in range(1, 10):
            QShortcut(QKeySequence(f"Alt+{n}"), self, activated=lambda n=n: self._insert_row(n - 1))
        self.retranslate()

    # ------------------------------------------------------------------ public
    def retranslate(self) -> None:
        hk = self.controller.settings.get("hotkey")
        self.search.setPlaceholderText(t("picker.search"))
        self.hint.setText(t("picker.hint", hotkey=hk))
        self.view_button.setToolTip(t("picker.group_categories") + " (Ctrl+G)")
        self.reload_categories()

    def reload_categories(self) -> None:
        current = self._category
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem(t("picker.all"), None)
        self.category.addItem("★ " + t("picker.favourites"), "★")
        raw_cats = self.controller.library.categories() if callable(getattr(self.controller.library, "categories", None)) else getattr(self.controller.library, "categories", [])
        for cat in raw_cats:
            self.category.addItem(cat, cat)
        idx = max(0, self.category.findData(current)) if current else 0
        self.category.setCurrentIndex(idx)
        self._category = self.category.currentData()
        self.category.blockSignals(False)

    def popup(self, anchor: QPoint | None, hwnd: int = 0) -> None:
        s = self.controller.settings
        self.setProperty("themeMode", s.get("theme"))
        self.list.setProperty("themeMode", s.get("theme"))
        self.preview.setVisible(bool(s.get("picker_show_preview")))
        w, h = int(s.get("picker_width")), int(s.get("picker_height"))
        if not s.get("picker_show_preview"):
            w = min(w, 460)
        self.resize(w, h)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.reload_categories()
        self.view_button.blockSignals(True)
        self.view_button.setChecked(self._grouped())
        self.view_button.blockSignals(False)
        self.refresh()
        self._place(anchor or QCursor.pos())
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def refresh(self, *, select_rel: str | None = None, select_group: str | None = None) -> None:
        """Rebuild the list. ``select_rel`` keeps a template selected; ``select_group`` selects that
        group (its header when folded, else its first template)."""
        lib = self.controller.library
        s = self.controller.settings
        query = self.search.text()
        self._results = lib.search(query, category=self._category, sort=s.get("picker_sort"))
        grouped = self._grouped()
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        self._numbered = []
        self.list.setUniformItemSizes(not grouped)
        if grouped and self._results:
            searching = bool(query.strip())
            groups = group_results(self._results, lib.usage, searching=searching,
                                   filtered=self._category is not None,
                                   recent_count=int(s.get("picker_recent_count")),
                                   favourites_in_folder=bool(s.get("picker_favourites_in_folder")))
            collapsed = set() if searching else self._collapsed()
            for group in groups:
                folded = group.key in collapsed
                self._add_header(group, folded)
                if not folded:
                    for tpl in group.items:
                        self._add_template(tpl, group.key, show_category=group.special)
        else:
            for tpl in self._results:
                self._add_template(tpl, None, show_category=True)
        self.list.setUpdatesEnabled(True)
        if self._results:
            row = self._find_row(select_rel, select_group)
            stops = self._stops()
            self.list.setCurrentRow(row if row is not None else (stops[0] if stops else 0))
        else:
            empty = t("picker.empty_library", folder=str(lib.root)) if not lib.templates else t("picker.no_match")
            self.preview.setHtml(f"<p style='color:gray'>{empty}</p>")

    def _add_template(self, tpl: Template, group: str | None, *, show_category: bool) -> None:
        item = QListWidgetItem(tpl.name)
        item.setData(ROLE_REL, tpl.rel)
        item.setData(ROLE_GROUP, group)
        sub = " · ".join(x for x in (tpl.category if show_category else "", kind_label(tpl),
                                      f"⌨ {tpl.abbreviation}" if tpl.abbreviation else "",
                                      " ".join(tpl.preview.split())[:120]) if x)
        item.setData(ROLE_SUB, sub)
        item.setData(ROLE_FAV, self.controller.library.usage.favourite(tpl.rel))
        if len(self._numbered) < 9:
            self._numbered.append(self.list.count())
            item.setData(ROLE_NUM, len(self._numbered))
        self.list.addItem(item)

    def _add_header(self, group: Group, folded: bool) -> None:
        if group.key == FAVOURITES:
            title = "★ " + t("picker.favourites")
        elif group.key == RECENT:
            title = t("picker.recent")
        else:
            title = folder_title(group.key) or t("picker.no_folder")
        item = QListWidgetItem(title)
        item.setData(ROLE_IS_HEADER, True)
        item.setData(ROLE_GROUP, group.key)
        item.setData(ROLE_COLLAPSED, folded)
        item.setData(ROLE_COUNT, len(group.items))
        # A folded header is a stop for the keyboard (Enter / → opens it); an open one is only clickable.
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable if folded else Qt.ItemIsEnabled)
        self.list.addItem(item)

    def current_rel(self) -> str | None:
        item = self.list.currentItem()
        return item.data(ROLE_REL) if item else None

    # ------------------------------------------------------------------ grouped view
    def _grouped(self) -> bool:
        return self.controller.settings.get("picker_view") == "groups"

    def _collapsed(self) -> set[str]:
        return {k for k in (self.controller.settings.get("picker_collapsed") or []) if isinstance(k, str)}

    def _searching(self) -> bool:
        return bool(self.search.text().strip())

    def _is_stop(self, row: int) -> bool:
        item = self.list.item(row)
        return item is not None and (not item.data(ROLE_IS_HEADER) or bool(item.data(ROLE_COLLAPSED)))

    def _stops(self) -> list[int]:
        """Rows the keyboard can land on: templates and folded headers."""
        return [r for r in range(self.list.count()) if self._is_stop(r)]

    def _find_row(self, rel: str | None, group: str | None) -> int | None:
        if rel:
            for r in range(self.list.count()):
                if self.list.item(r).data(ROLE_REL) == rel:
                    return r
        if group is not None:
            for r in range(self.list.count()):
                item = self.list.item(r)
                if item.data(ROLE_GROUP) == group and self._is_stop(r):
                    return r
        return None

    def _move(self, step: int) -> None:
        stops = self._stops()
        if not stops:
            return
        row = self.list.currentRow()
        if row in stops:
            pos = stops.index(row)
        else:  # on an open header (mouse): the next stop down / up
            later = [i for i, r in enumerate(stops) if r > row]
            pos = (later[0] - (1 if step > 0 else 0)) if later else len(stops) - 1
        self.list.setCurrentRow(stops[max(0, min(len(stops) - 1, pos + step))])

    def _group_keys(self) -> list[str]:
        keys: list[str] = []
        for r in range(self.list.count()):
            item = self.list.item(r)
            if item.data(ROLE_IS_HEADER):
                keys.append(item.data(ROLE_GROUP))
        return keys

    def _jump_group(self, step: int) -> None:
        item = self.list.currentItem()
        keys = self._group_keys()
        if not keys or item is None:
            return
        current = item.data(ROLE_GROUP)
        pos = keys.index(current) if current in keys else 0
        target = keys[max(0, min(len(keys) - 1, pos + step))]
        row = self._find_row(None, target)
        if row is not None:
            self.list.setCurrentRow(row)

    def _set_folded(self, key: str, folded: bool) -> None:
        if self._searching():
            return  # every group is open while searching
        collapsed = self._collapsed()
        if folded == (key in collapsed):
            return
        collapsed.symmetric_difference_update({key})
        self.controller.settings.set("picker_collapsed", sorted(collapsed))
        self.refresh(select_group=key)

    def _fold_current(self) -> bool:
        item = self.list.currentItem()
        if item is None or not self._grouped() or item.data(ROLE_GROUP) is None:
            return False
        self._set_folded(item.data(ROLE_GROUP), True)
        return True

    def _unfold_current(self) -> bool:
        item = self.list.currentItem()
        if item is None or not item.data(ROLE_IS_HEADER) or not item.data(ROLE_COLLAPSED):
            return False
        self._set_folded(item.data(ROLE_GROUP), False)
        return True

    def _item_clicked(self, item: QListWidgetItem) -> None:
        if item.data(ROLE_IS_HEADER):
            self._set_folded(item.data(ROLE_GROUP), not item.data(ROLE_COLLAPSED))
            self.search.setFocus()

    def _view_toggled(self, grouped: bool) -> None:
        self.controller.settings.set("picker_view", "groups" if grouped else "list")
        self.refresh(select_rel=self.current_rel())
        self.search.setFocus()

    # ------------------------------------------------------------------ internals
    def _place(self, anchor: QPoint) -> None:
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(area.left(), anchor.x()), area.right() - self.width())
        y = anchor.y() + 4
        if y + self.height() > area.bottom():
            y = max(area.top(), anchor.y() - self.height() - 28)
        self.move(x, y)

    def _category_changed(self) -> None:
        self._category = self.category.currentData()
        self.refresh()

    def _update_preview(self) -> None:
        rel = self.current_rel()
        if not self.preview.isVisible() or not rel:
            return
        tpl = self.controller.library.get(rel)
        if tpl is None:
            return
        rendered = self.controller.renderer.render(tpl, self.controller.library.root)
        if tpl.kind == "image":
            self.preview.setHtml(f'<img src="{tpl.path(self.controller.library.root).as_uri()}" width="{self.preview.width() - 30}"/>')
        else:
            self.preview.setHtml(rendered.html or "<pre>" + rendered.text + "</pre>")

    def _insert(self, shift: bool) -> None:
        if self._unfold_current():  # Enter on a folded header opens it
            return
        rel = self.current_rel()
        if rel:
            self.hide()
            self.insert_requested.emit(rel, shift)

    def _insert_row(self, n: int) -> None:
        """Alt+1…9: the n-th template shown (headers are not counted)."""
        if 0 <= n < len(self._numbered):
            self.list.setCurrentRow(self._numbered[n])
            self._insert(False)

    def _copy(self, shift: bool) -> None:
        if self.search.hasSelectedText():
            self.search.copy()
            return
        rel = self.current_rel()
        if rel:
            self.hide()
            self.copy_requested.emit(rel, shift)

    def _edit(self) -> None:
        rel = self.current_rel()
        self.hide()
        if rel:
            self.edit_requested.emit(rel)
        else:
            self.editor_requested.emit()

    def _toggle_fav(self) -> None:
        rel = self.current_rel()
        if rel:
            self.favourite_toggled.emit(rel)
            if self._grouped():  # the ★ group changes
                self.refresh(select_rel=rel)
                return
            row = self.list.currentRow()
            self.list.currentItem().setData(ROLE_FAV, self.controller.library.usage.favourite(rel))
            self.list.setCurrentRow(row)

    def eventFilter(self, obj, event) -> bool:
        if obj in (self.search, self.list) and event.type() == QEvent.KeyPress:
            key, mods = event.key(), event.modifiers()
            if key in (Qt.Key_Down, Qt.Key_Up) and mods & Qt.ControlModifier:
                self._jump_group(1 if key == Qt.Key_Down else -1)
                return True
            if key in (Qt.Key_Down, Qt.Key_Up, Qt.Key_PageDown, Qt.Key_PageUp):
                self._move({Qt.Key_Down: 1, Qt.Key_Up: -1, Qt.Key_PageDown: 8, Qt.Key_PageUp: -8}[key])
                return True
            # ←/→ fold and open groups; in the search box only while it is empty (else they move the caret).
            plain = not (mods & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier))
            if key in (Qt.Key_Left, Qt.Key_Right) and plain and self._grouped() and \
                    (obj is self.list or not self.search.text()):
                if key == Qt.Key_Left:
                    self._fold_current()
                else:
                    self._unfold_current()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._insert(bool(mods & Qt.ShiftModifier))
                return True
            if key == Qt.Key_Tab:
                self.category.setCurrentIndex((self.category.currentIndex() + 1) % self.category.count())
                return True
            if key == Qt.Key_Backtab:
                self.category.setCurrentIndex((self.category.currentIndex() - 1) % self.category.count())
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.list.hasFocus():
            self._insert(bool(event.modifiers() & Qt.ShiftModifier))
            return
        super().keyPressEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow() and self.isVisible():
            QTimer.singleShot(120, self._hide_if_inactive)
        super().changeEvent(event)

    def _hide_if_inactive(self) -> None:
        from PySide6.QtWidgets import QApplication

        active = QApplication.activeWindow()
        if not self.isActiveWindow() and (active is None or active is self):
            self.hide()
