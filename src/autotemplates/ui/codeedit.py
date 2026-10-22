"""Plain-text / code editor with live Pygments colouring."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit


class PygmentsHighlighter(QSyntaxHighlighter):
    """Lexes the whole document (debounced) so multi-line strings/comments colour correctly."""

    def __init__(self, document: QTextDocument, style: str = "default") -> None:
        super().__init__(document)
        self.language = ""
        self.style = style
        self._spans: dict[int, list[tuple[int, int, QTextCharFormat]]] = {}
        self._formats: dict = {}
        self._timer = QTimer(singleShot=True, interval=200)
        self._timer.timeout.connect(self._relex)
        document.contentsChanged.connect(self._timer.start)

    def set_language(self, language: str, style: str | None = None) -> None:
        self.language = language
        if style and style != self.style:
            self.style = style
            self._formats.clear()
        self._relex()

    def _format(self, ttype) -> QTextCharFormat | None:
        if ttype in self._formats:
            return self._formats[ttype]
        from pygments.styles import get_style_by_name

        try:
            style = get_style_by_name(self.style)
        except Exception:  # noqa: BLE001
            style = get_style_by_name("default")
        s = style.style_for_token(ttype)
        fmt = None
        if s.get("color") or s.get("bold") or s.get("italic"):
            fmt = QTextCharFormat()
            if s.get("color"):
                fmt.setForeground(QColor("#" + s["color"]))
            if s.get("bold"):
                fmt.setFontWeight(QFont.Bold)
            if s.get("italic"):
                fmt.setFontItalic(True)
        self._formats[ttype] = fmt
        return fmt

    def _relex(self) -> None:
        self._spans = {}
        if self.language:
            from autotemplates.core.highlight import _lexer

            text = self.document().toPlainText()
            block, col = 0, 0
            for ttype, value in _lexer(self.language).get_tokens(text):
                fmt = self._format(ttype)
                parts = value.split("\n")
                for i, part in enumerate(parts):
                    if i:
                        block, col = block + 1, 0
                    if part and fmt is not None:
                        self._spans.setdefault(block, []).append((col, len(part), fmt))
                    col += len(part)
        self.blockSignals(True)
        self.rehighlight()
        self.blockSignals(False)

    def highlightBlock(self, text: str) -> None:
        for start, length, fmt in self._spans.get(self.currentBlock().blockNumber(), ()):
            self.setFormat(start, length, fmt)


class CodeEdit(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.highlighter = PygmentsHighlighter(self.document())

    def set_code_font(self, family: str, size: int) -> None:
        font = QFont(family)
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(size)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)