"""Modern popup launcher at the cursor: choose NoteIT (quick note) or Templates."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QCursor, QFont, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from autotemplates.i18n import t
from autotemplates.ui import theme

ACCENT = "#5b6cff"


class QuickLauncher(QWidget):
    """Modern floating card at cursor with two big action cards: NoteIT & Templates."""

    noteit_selected = Signal()
    templates_selected = Signal()

    def __init__(self, controller) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.controller = controller
        self.setObjectName("QuickLauncher")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)

        frame = QFrame(self)
        frame.setObjectName("LauncherFrame")
        frame.setStyleSheet("""
            #LauncherFrame {
                background: #202228;
                border: 1px solid #3c404b;
                border-radius: 12px;
            }
            QLabel {
                color: #e8e9ee;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header title
        header = QLabel(t("launcher.title"))
        header.setStyleSheet("font-size: 10pt; font-weight: bold; color: #a0a4b0; letter-spacing: 0.5px;")
        layout.addWidget(header)

        # Cards container
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        # 1. NoteIT Card
        self.btn_noteit = QPushButton()
        self.btn_noteit.setObjectName("CardNoteIT")
        self.btn_noteit.setCursor(Qt.PointingHandCursor)
        self.btn_noteit.setStyleSheet(f"""
            QPushButton#CardNoteIT {{
                background: #282b34;
                border: 1.5px solid #373b47;
                border-radius: 10px;
                padding: 14px 16px;
                text-align: left;
                min-width: 170px;
            }}
            QPushButton#CardNoteIT:hover, QPushButton#CardNoteIT:focus {{
                background: #313542;
                border: 1.5px solid {ACCENT};
            }}
        """)
        lay_n = QVBoxLayout(self.btn_noteit)
        lay_n.setContentsMargins(0, 0, 0, 0)
        lay_n.setSpacing(4)

        row_nh = QHBoxLayout()
        icon_n = QLabel()
        icon_n.setPixmap(theme.glyph_icon("note").pixmap(24, 24))
        row_nh.addWidget(icon_n)
        row_nh.addStretch(1)
        n_key = QLabel("N")
        n_key.setStyleSheet(f"background: #1e2026; color: {ACCENT}; font-size: 8pt; font-weight: bold; padding: 2px 7px; border-radius: 4px; border: 1px solid #3c404b;")
        row_nh.addWidget(n_key)
        lay_n.addLayout(row_nh)

        n_title = QLabel(t("launcher.noteit_title"))
        n_title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ffffff;")
        lay_n.addWidget(n_title)
        n_desc = QLabel(t("launcher.noteit_desc"))
        n_desc.setStyleSheet("font-size: 8pt; color: #8a8e9b;")
        lay_n.addWidget(n_desc)
        self.btn_noteit.clicked.connect(self._select_noteit)
        cards_row.addWidget(self.btn_noteit)

        # 2. Templates Card
        self.btn_templates = QPushButton()
        self.btn_templates.setObjectName("CardTemplates")
        self.btn_templates.setCursor(Qt.PointingHandCursor)
        self.btn_templates.setStyleSheet(f"""
            QPushButton#CardTemplates {{
                background: #282b34;
                border: 1.5px solid #373b47;
                border-radius: 10px;
                padding: 14px 16px;
                text-align: left;
                min-width: 170px;
            }}
            QPushButton#CardTemplates:hover, QPushButton#CardTemplates:focus {{
                background: #313542;
                border: 1.5px solid {ACCENT};
            }}
        """)
        lay_t = QVBoxLayout(self.btn_templates)
        lay_t.setContentsMargins(0, 0, 0, 0)
        lay_t.setSpacing(4)

        row_th = QHBoxLayout()
        icon_t = QLabel()
        icon_t.setPixmap(theme.glyph_icon("insert").pixmap(24, 24))
        row_th.addWidget(icon_t)
        row_th.addStretch(1)
        t_key = QLabel("T")
        t_key.setStyleSheet(f"background: #1e2026; color: {ACCENT}; font-size: 8pt; font-weight: bold; padding: 2px 7px; border-radius: 4px; border: 1px solid #3c404b;")
        row_th.addWidget(t_key)
        lay_t.addLayout(row_th)

        t_title = QLabel(t("launcher.templates_title"))
        t_title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ffffff;")
        lay_t.addWidget(t_title)
        t_desc = QLabel(t("launcher.templates_desc"))
        t_desc.setStyleSheet("font-size: 8pt; color: #8a8e9b;")
        lay_t.addWidget(t_desc)
        self.btn_templates.clicked.connect(self._select_templates)
        cards_row.addWidget(self.btn_templates)

        layout.addLayout(cards_row)

        footer = QLabel(t("launcher.hint"))
        footer.setStyleSheet("color: #6a6f7d; font-size: 8pt; margin-top: 2px;")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

        self.btn_templates.setDefault(True)
        self.btn_templates.setFocus()

    def popup(self, anchor: QPoint | None = None) -> None:
        self.adjustSize()
        pos = anchor or QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        w = self.sizeHint().width()
        h = self.sizeHint().height()
        x = min(max(pos.x() - w // 2, avail.left() + 10), avail.right() - w - 10)
        y = min(max(pos.y() - h // 2, avail.top() + 10), avail.bottom() - h - 10)

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.btn_templates.setFocus()

    def _select_noteit(self) -> None:
        self.hide()
        self.noteit_selected.emit()

    def _select_templates(self) -> None:
        self.hide()
        self.templates_selected.emit()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide()
            return
        if key == Qt.Key_N:
            self._select_noteit()
            return
        if key == Qt.Key_T:
            self._select_templates()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self.btn_noteit.hasFocus():
                self._select_noteit()
            else:
                self._select_templates()
            return
        if key in (Qt.Key_Left, Qt.Key_Up):
            self.btn_noteit.setFocus()
            return
        if key in (Qt.Key_Right, Qt.Key_Down):
            self.btn_templates.setFocus()
            return
        super().keyPressEvent(event)
