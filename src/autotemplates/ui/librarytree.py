"""The editor's library tree with drag & drop of folders and templates.

The tree never moves its own items: a drop only reports *what* was dropped
*where*; the editor moves the files (``core.folders``) and rebuilds the tree.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from autotemplates.core.folders import is_inside

ROLE_REL = Qt.UserRole + 1  # template rel (None for folders)
ROLE_CAT = Qt.UserRole + 2  # folder category (folders only)


class LibraryTree(QTreeWidget):
    # ("template", rel) or ("folder", category), destination category ("" = library root)
    dropped = Signal(str, str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.drag_allowed = True  # off while the search filter is active
        self._drag: tuple[str, str] | None = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    # ---------------------------------------------------------------- what / where
    @staticmethod
    def item_source(item: QTreeWidgetItem | None) -> tuple[str, str] | None:
        if item is None:
            return None
        rel = item.data(0, ROLE_REL)
        if rel:
            return "template", rel
        cat = item.data(0, ROLE_CAT)
        return ("folder", cat) if cat else None

    def target_category(self, item: QTreeWidgetItem | None) -> str:
        """Folder under the cursor; a template stands for its own folder; empty space = root."""
        if item is None:
            return ""
        cat = item.data(0, ROLE_CAT)
        if cat:
            return cat
        parent = item.parent()
        return (parent.data(0, ROLE_CAT) or "") if parent else ""

    @staticmethod
    def can_drop(source: tuple[str, str] | None, target: str) -> bool:
        if source is None:
            return False
        kind, value = source
        if kind == "folder":
            return not is_inside(target, value) and target != value.rpartition("/")[0]
        return target != value.rpartition("/")[0]  # already in that folder

    # ---------------------------------------------------------------- Qt events
    def startDrag(self, actions) -> None:
        if not self.drag_allowed:
            return
        self._drag = self.item_source(self.currentItem())
        if self._drag is None:
            return
        try:
            super().startDrag(Qt.CopyAction | Qt.MoveAction)
        finally:
            self._drag = None

    def _check(self, event) -> str | None:
        if event.source() is not self or self._drag is None:
            return None
        pos = event.position().toPoint()
        target = self.target_category(self.itemAt(pos))
        return target if self.can_drop(self._drag, target) else None

    def dragEnterEvent(self, event) -> None:
        if event.source() is self and self._drag is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        super().dragMoveEvent(event)  # auto-scroll, auto-expand, drop indicator
        if self._check(event) is None:
            event.ignore()
        else:
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def _end_drag_state(self) -> None:
        """We handle the drop ourselves, so reset what QAbstractItemView.dropEvent would reset."""
        self.stopAutoScroll()
        self.setState(QAbstractItemView.NoState)
        self.viewport().update()

    def dropEvent(self, event) -> None:
        target = self._check(event)
        source = self._drag
        self._end_drag_state()
        if target is None or source is None:
            event.ignore()
            return
        # CopyAction: Qt must not remove the dragged item itself; the editor rebuilds the tree.
        event.setDropAction(Qt.CopyAction)
        event.accept()
        kind, value = source
        QTimer.singleShot(0, lambda: self.dropped.emit(kind, value, target))
