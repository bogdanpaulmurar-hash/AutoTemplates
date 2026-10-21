"""Modern flat look (dark / light), glyph icons and the app icon, all drawn in code (no image files)."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette,
                           QPen, QPixmap)
from PySide6.QtWidgets import QApplication

ACCENT = "#5b6cff"

PALETTES = {
    "dark": dict(bg="#1e1f24", panel="#26282e", panel2="#2e3038", border="#3a3d46", text="#e8e9ee",
                 muted="#9a9eab", select="#3b4370", hover="#33363f", input="#191a1f"),
    "light": dict(bg="#f5f6f8", panel="#ffffff", panel2="#eef0f4", border="#d9dce3", text="#1d1f24",
                  muted="#6b7080", select="#dfe3ff", hover="#eceef3", input="#ffffff"),
}


def colors(mode: str) -> dict[str, str]:
    return PALETTES.get(mode, PALETTES["dark"])


def stylesheet(mode: str) -> str:
    c = colors(mode)
    return f"""
    QWidget {{ color: {c['text']}; }}
    QMainWindow, QDialog, #Picker, #PickerFrame {{ background: {c['bg']}; }}
    #PickerFrame {{ border: 1px solid {c['border']}; border-radius: 10px; }}
    QToolBar {{ background: {c['panel']}; border: none; border-bottom: 1px solid {c['border']}; spacing: 2px; padding: 3px; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px; min-width: 22px; }}
    QToolButton:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
    QToolButton:checked {{ background: {c['select']}; border-color: {ACCENT}; }}
    QToolButton::menu-indicator {{ image: none; }}
    QPushButton {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 12px; }}
    QPushButton:hover {{ border-color: {ACCENT}; }}
    QPushButton#Primary {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox, QComboBox, QKeySequenceEdit, QFontComboBox {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 6px;
        selection-background-color: {ACCENT}; selection-color: white; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
    QLineEdit#Search {{ font-size: 12pt; padding: 8px 10px; border-radius: 8px; }}
    #Paper {{ background: #ffffff; color: #1d1f24; border-color: {c['border']}; selection-background-color: #b4c0ff; selection-color: #1d1f24; }}
    QComboBox QAbstractItemView {{ background: {c['panel']}; border: 1px solid {c['border']};
        selection-background-color: {c['select']}; selection-color: {c['text']}; }}
    QListWidget, QTreeWidget {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; outline: 0; }}
    QListWidget::item, QTreeWidget::item {{ padding: 3px; border-radius: 6px; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {c['select']}; color: {c['text']}; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['hover']}; }}
    QSplitter::handle {{ background: transparent; width: 6px; }}
    QStatusBar {{ background: {c['panel']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
    QLabel#Muted, QLabel#Hint {{ color: {c['muted']}; }}
    QLabel#Hint {{ font-size: 9pt; }}
    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px; background: {c['panel']}; }}
    QTabBar::tab {{ background: transparent; padding: 6px 14px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ border-bottom-color: {ACCENT}; }}
    QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['select']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 6px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; }}
    """


def apply_theme(app: QApplication, mode: str) -> None:
    app.setStyle("Fusion")
    families = set(QFontDatabase.families())
    ui_font = next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in families), app.font().family())
    app.setFont(QFont(ui_font, 10))
    c = colors(mode)
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "input"), (QPalette.AlternateBase, "panel2"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "panel2"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "panel"), (QPalette.ToolTipText, "text"),
                      (QPalette.PlaceholderText, "muted")):
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(mode))
    glyph_icon.cache_clear()


# Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10) code points.
GLYPHS = {
    "undo": "", "redo": "", "bold": "", "italic": "", "underline": "",
    "strike": "", "color": "", "highlight": "", "clear": "", "left": "",
    "center": "", "right": "", "justify": "", "bullets": "", "numbers": "",
    "check": "", "indent": "", "outdent": "", "link": "", "table": "",
    "image": "", "code": "", "rule": "", "save": "", "new": "", "delete": "",
    "folder": "", "settings": "", "search": "", "star": "", "starfill": "",
    "edit": "", "copy": "", "insert": "", "screenshot": "", "variable": "",
    "superscript": "", "subscript": "", "import": "", "refresh": "", "rename": "",
    "text": "", "doc": "", "spacing": "", "resize": "", "plain": "",
}
_FALLBACK = {"bold": "B", "italic": "I", "underline": "U", "strike": "S", "superscript": "x²", "subscript": "x₂",
             "color": "A", "highlight": "H", "code": "</>", "variable": "{}", "table": "▦", "image": "▣",
             "link": "🔗", "rule": "—", "bullets": "•", "numbers": "1.", "check": "☑", "indent": "→", "outdent": "←",
             "left": "⯇", "center": "≡", "right": "⯈", "justify": "☰", "undo": "↶", "redo": "↷", "clear": "⌫",
             "save": "💾", "new": "+", "delete": "🗑", "folder": "📁", "settings": "⚙", "search": "🔍", "star": "☆",
             "starfill": "★", "edit": "✎", "copy": "⧉", "insert": "↵", "screenshot": "📷", "import": "⇩",
             "refresh": "⟳", "rename": "✎", "text": "T", "doc": "📄", "spacing": "↕", "resize": "⤢", "plain": "T"}


# Drawn as text everywhere: letters read better than glyphs for formatting buttons.
TEXT_ONLY = {"bold", "italic", "underline", "strike", "superscript", "subscript", "numbers", "check", "table",
             "rule", "justify", "spacing", "indent", "outdent", "variable", "text", "plain"}


@lru_cache(maxsize=1)
def _icon_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if name in families:
            return name
    return ""


@lru_cache(maxsize=256)
def glyph_icon(name: str, color: str = "", size: int = 32) -> QIcon:
    """A crisp toolbar icon from the Windows icon font (text fallback elsewhere)."""
    if not color:
        app = QApplication.instance()
        color = app.palette().color(QPalette.Text).name() if app else "#888888"
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(QColor(color))
    family = _icon_font()
    if family and name in GLYPHS and name not in TEXT_ONLY:
        font = QFont(family)
        font.setPixelSize(int(size * 0.62))
        p.setFont(font)
        p.drawText(pm.rect(), Qt.AlignCenter, GLYPHS[name])
    else:
        font = QFont("Segoe UI")
        label = _FALLBACK.get(name, name[:1].upper())
        font.setPixelSize(int(size * (0.62 if len(label) == 1 else 0.42)))
        font.setBold(name == "bold")
        font.setItalic(name == "italic")
        font.setUnderline(name == "underline")
        font.setStrikeOut(name == "strike")
        p.setFont(font)
        p.drawText(pm.rect(), Qt.AlignCenter, label)
    p.end()
    return QIcon(pm)


def color_icon(color: str, letter: str = "A", size: int = 32) -> QIcon:
    """Letter with a colour bar below it (text colour / highlight buttons)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    app = QApplication.instance()
    p.setPen(app.palette().color(QPalette.Text) if app else QColor("#888"))
    font = QFont("Segoe UI")
    font.setPixelSize(int(size * 0.55))
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, 0, size, size * 0.78), Qt.AlignCenter, letter)
    p.fillRect(QRectF(size * 0.15, size * 0.78, size * 0.7, size * 0.16), QColor(color))
    p.end()
    return QIcon(pm)


def app_icon_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(size * 0.06, size * 0.06, size * 0.88, size * 0.88)
    grad = QLinearGradient(r.topLeft(), r.bottomRight())
    grad.setColorAt(0, QColor("#6d7cff"))
    grad.setColorAt(1, QColor("#9b5cff"))
    path = QPainterPath()
    path.addRoundedRect(r, size * 0.2, size * 0.2)
    p.fillPath(path, grad)
    # a document with lines and a lightning "insert" bolt
    doc = QRectF(size * 0.27, size * 0.22, size * 0.40, size * 0.54)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawRoundedRect(doc, size * 0.05, size * 0.05)
    pen = QPen(QColor("#6d7cff"), size * 0.035, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    for i in range(4):
        y = doc.top() + size * (0.11 + i * 0.09)
        p.drawLine(QPointF(doc.left() + size * 0.07, y), QPointF(doc.right() - size * (0.07 if i % 2 == 0 else 0.15), y))
    bolt = QPainterPath()
    pts = [(0.66, 0.48), (0.56, 0.66), (0.64, 0.66), (0.58, 0.82), (0.78, 0.60), (0.69, 0.60), (0.76, 0.48)]
    bolt.moveTo(QPointF(pts[0][0] * size, pts[0][1] * size))
    for x, y in pts[1:]:
        bolt.lineTo(QPointF(x * size, y * size))
    bolt.closeSubpath()
    p.setPen(QPen(QColor("#ffffff"), size * 0.02))
    p.setBrush(QColor("#ffc83d"))
    p.drawPath(bolt)
    p.end()
    return pm


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 256):
        icon.addPixmap(app_icon_pixmap(s))
    return icon
