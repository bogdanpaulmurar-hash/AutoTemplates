"""Template manager and editor: library tree on the left, editor on the right."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PySide6.QtCore import QFile, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QFont, QGuiApplication, QKeySequence,
                           QTextCharFormat)
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFontComboBox,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QSpinBox, QSplitter, QStackedWidget, QTextBrowser, QToolBar,
                               QToolButton, QTreeWidgetItem, QVBoxLayout, QWidget)

from autotemplates.core import folders, formats, highlight
from autotemplates.core.folders import ASK, KEEP_BOTH, MERGE, FolderConflict, FolderError, TrashFailed
from autotemplates.core.library import Template, fold, safe_name, unique_path
from autotemplates.core.settings import DEFAULTS
from autotemplates.core.shortcuts import EDITOR_SHORTCUTS
from autotemplates.core.variables import INPUT_EXAMPLE, VARIABLES
from autotemplates.i18n import t
from autotemplates.ui import theme
from autotemplates.ui.codeedit import CodeEdit
from autotemplates.ui.librarytree import ROLE_CAT, ROLE_REL, LibraryTree
from autotemplates.ui.content import absolutize_images
from autotemplates.ui.richedit import RichEdit, load_document, localize_images, with_shortcut

log = logging.getLogger(__name__)

PRESET_COLORS = ["#000000", "#5f6368", "#c62828", "#e65100", "#f9a825", "#2e7d32", "#00838f", "#1565c0",
                 "#6a1b9a", "#ad1457", "#ffffff"]
HIGHLIGHTS = ["#fff59d", "#c5e1a5", "#80deea", "#90caf9", "#f48fb1", "#ffcc80", "#e0e0e0"]
CODE_LANGS = ["python", "json", "csharp", "javascript", "typescript", "sql", "xml", "html", "yaml", "powershell",
              "batch", "bash", "css", "c", "cpp", "java", "go", "rust", "php", "markdown", "ini", "toml"]
NEW_CODE_EXT = {"python": ".py", "json": ".json", "csharp": ".cs", "javascript": ".js", "typescript": ".ts",
                "sql": ".sql", "xml": ".xml", "html": ".html", "yaml": ".yaml", "powershell": ".ps1",
                "batch": ".bat", "bash": ".sh", "css": ".css", "c": ".c", "cpp": ".cpp", "java": ".java",
                "go": ".go", "rust": ".rs", "php": ".php", "ini": ".ini", "toml": ".toml"}


class CodeDialog(QDialog):
    """Paste code, pick (or auto-detect) the language, insert it coloured."""

    def __init__(self, parent, style: str, font: str, size: int) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("code.title"))
        self.resize(700, 460)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("code.language")))
        self.lang = QComboBox()
        self.lang.addItem(t("code.auto"), "")
        for name in CODE_LANGS:
            self.lang.addItem(formats.LANGUAGE_NAMES.get(name, name), name)
        row.addWidget(self.lang)
        self.detected = QLabel()
        self.detected.setObjectName("Muted")
        row.addWidget(self.detected, 1)
        lay.addLayout(row)
        self.edit = CodeEdit()
        self.edit.set_code_font(font, size)
        self.edit.highlighter.style = style
        clip = QGuiApplication.clipboard().text()
        if clip and len(clip) < 200_000:
            self.edit.setPlainText(clip)
        lay.addWidget(self.edit, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.edit.textChanged.connect(self._detect)
        self.lang.currentIndexChanged.connect(self._detect)
        self._detect()

    def language(self) -> str:
        return self.lang.currentData() or highlight.detect_language(self.edit.toPlainText())

    def _detect(self) -> None:
        lang = self.language()
        if not self.lang.currentData():
            self.detected.setText(t("code.detected", lang=formats.LANGUAGE_NAMES.get(lang, lang or "—")))
        else:
            self.detected.setText("")
        if lang != self.edit.highlighter.language:
            self.edit.highlighter.set_language(lang)


class EditorWindow(QMainWindow):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self.setWindowTitle("AutoTemplates")
        self.setWindowIcon(theme.app_icon())
        self.resize(1180, 760)
        self.current: Template | None = None
        self._new_path: Path | None = None  # a new template not saved yet
        self._loading = False
        self._screenshot_wait = False

        # ---------------- left: library
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 4, 8)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(t("editor.filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.reload_tree)
        top.addWidget(self.filter, 1)
        self.new_btn = QToolButton()
        self.new_btn.setIcon(theme.glyph_icon("new"))
        self.new_btn.setToolTip(t("editor.new"))
        self.new_btn.setPopupMode(QToolButton.InstantPopup)
        self.new_btn.setMenu(self._new_menu())
        top.addWidget(self.new_btn)
        self.a_help = QAction(theme.glyph_icon("help"), t("tray.help"), self)
        self.a_help.setShortcut(QKeySequence(EDITOR_SHORTCUTS["help"]))
        self.a_help.setShortcutContext(Qt.WindowShortcut)
        self.a_help.setToolTip(f"{t('tray.help')} ({EDITOR_SHORTCUTS['help']})")
        self.a_help.triggered.connect(lambda: self.c.show_help("editor"))
        self.addAction(self.a_help)
        help_btn = QToolButton()
        help_btn.setDefaultAction(self.a_help)
        top.addWidget(help_btn)
        ll.addLayout(top)
        self.tree = LibraryTree()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.tree.dropped.connect(self._tree_dropped)
        ll.addWidget(self.tree, 1)
        folder_btn = QPushButton(theme.glyph_icon("folder"), t("editor.open_folder"))
        folder_btn.clicked.connect(self.c.open_library_folder)
        ll.addWidget(folder_btn)

        # ---------------- right: meta + editors
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 8, 8, 8)
        meta = QFormLayout()
        meta.setHorizontalSpacing(10)
        meta.setVerticalSpacing(6)
        row1 = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText(t("editor.name"))
        f = self.name.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        self.name.setFont(f)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.setMinimumWidth(180)
        self.category.lineEdit().setPlaceholderText(t("editor.category"))
        row1.addWidget(self.name, 3)
        row1.addWidget(self.category, 2)
        rl.addLayout(row1)
        row2 = QHBoxLayout()
        self.tags = QLineEdit()
        self.tags.setPlaceholderText(t("editor.tags"))
        self.abbrev = QLineEdit()
        self.abbrev.setPlaceholderText(t("editor.abbreviation"))
        self.abbrev.setMaximumWidth(160)
        self.mode = QComboBox()
        self.mode.addItem(t("editor.mode_default"), "")
        self.mode.addItem(t("editor.mode_rich"), "rich")
        self.mode.addItem(t("editor.mode_plain"), "plain")
        row2.addWidget(self.tags, 3)
        row2.addWidget(self.abbrev, 1)
        row2.addWidget(self.mode, 1)
        rl.addLayout(row2)
        self.description = QLineEdit()
        self.description.setPlaceholderText(t("editor.description"))
        rl.addWidget(self.description)
        for w in (self.name, self.tags, self.abbrev, self.description):
            w.textEdited.connect(self._mark_dirty)
        self.category.editTextChanged.connect(self._mark_dirty)
        self.mode.currentIndexChanged.connect(self._mark_dirty)

        self.stack = QStackedWidget()
        # rich
        self.rich_page = QWidget()
        rp = QVBoxLayout(self.rich_page)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(0)
        self.rich = RichEdit(self.c.paths.data_dir / "cache" / "pasted")
        self.rich_bar = self._rich_toolbar()
        rp.addWidget(self.rich_bar)
        rp.addWidget(self.rich, 1)
        self.rich.document().modificationChanged.connect(self._doc_modified)
        self.rich.currentCharFormatChanged.connect(self._sync_char)
        self.rich.cursorPositionChanged.connect(self._sync_block)
        self.rich.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rich.customContextMenuRequested.connect(self._rich_menu)
        # code / text
        self.code_page = QWidget()
        cp = QVBoxLayout(self.code_page)
        cp.setContentsMargins(0, 0, 0, 0)
        crow = QHBoxLayout()
        crow.addWidget(QLabel(t("code.language")))
        self.code_lang = QComboBox()
        self.code_lang.addItem(t("code.none"), "")
        for name in CODE_LANGS:
            self.code_lang.addItem(formats.LANGUAGE_NAMES.get(name, name), name)
        self.code_lang.currentIndexChanged.connect(lambda: self.code.highlighter.set_language(self.code_lang.currentData() or ""))
        crow.addWidget(self.code_lang)
        crow.addStretch(1)
        self.code_hint = QLabel(t("editor.code_hint"))
        self.code_hint.setObjectName("Muted")
        crow.addWidget(self.code_hint)
        cp.addLayout(crow)
        self.code = CodeEdit()
        self.code.document().modificationChanged.connect(self._doc_modified)
        cp.addWidget(self.code, 1)
        # read-only (docx, rtf, image)
        self.view_page = QWidget()
        vp = QVBoxLayout(self.view_page)
        vp.setContentsMargins(0, 0, 0, 0)
        vrow = QHBoxLayout()
        self.view_label = QLabel()
        self.view_label.setObjectName("Muted")
        vrow.addWidget(self.view_label, 1)
        convert = QPushButton(theme.glyph_icon("edit"), t("editor.convert"))
        convert.clicked.connect(self.convert_to_rich)
        open_ext = QPushButton(theme.glyph_icon("doc"), t("editor.open_external"))
        open_ext.clicked.connect(self._open_external)
        vrow.addWidget(open_ext)
        vrow.addWidget(convert)
        vp.addLayout(vrow)
        self.viewer = QTextBrowser()
        self.viewer.setObjectName("Paper")
        self.viewer.setOpenExternalLinks(True)
        vp.addWidget(self.viewer, 1)
        # empty
        self.empty_page = QLabel(t("editor.empty"))
        self.empty_page.setAlignment(Qt.AlignCenter)
        self.empty_page.setObjectName("Muted")
        self.empty_page.setWordWrap(True)
        for page in (self.empty_page, self.rich_page, self.code_page, self.view_page):
            self.stack.addWidget(page)
        rl.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("Muted")
        bottom.addWidget(self.status, 1)
        self.copy_btn = QPushButton(theme.glyph_icon("copy"), t("editor.copy"))
        self.copy_btn.setToolTip(t("editor.copy_tip"))
        self.copy_btn.clicked.connect(self._copy_result)
        self.save_btn = QPushButton(theme.glyph_icon("save"), t("editor.save"))
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self.save)
        bottom.addWidget(self.copy_btn)
        bottom.addWidget(self.save_btn)
        rl.addLayout(bottom)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([300, 880])
        self.setCentralWidget(split)

        for name, slot in (("save", self.save), ("new", lambda: self.new_template("rich")),
                           ("filter", lambda: self.filter.setFocus())):
            self.addAction(QAction(self, shortcut=QKeySequence(EDITOR_SHORTCUTS[name]), triggered=slot))
        QGuiApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        self.apply_settings()
        self.reload_tree()
        self._show_page(None)

    # ================================================================ toolbar
    def _act(self, bar: QToolBar, icon: str, tip: str, slot, *, checkable=False, shortcut: str | None = None) -> QAction:
        a = QAction(theme.glyph_icon(icon), t(tip), self)
        a.setCheckable(checkable)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(f"{t(tip)} ({shortcut})")
            a.setShortcutContext(Qt.WindowShortcut)
        a.triggered.connect(slot)
        bar.addAction(a)
        return a

    def _fmt(self, bar: QToolBar, icon: str, tip: str, name: str, *, checkable=False) -> QAction:
        """Toolbar button for a RichEdit formatting command; the shortcut itself is handled by RichEdit."""
        a = QAction(theme.glyph_icon(icon), t(tip), self)
        a.setCheckable(checkable)
        a.setToolTip(with_shortcut(t(tip), name))
        a.triggered.connect(lambda _=False, n=name: self._run_format(n))
        bar.addAction(a)
        return a

    def _run_format(self, name: str) -> None:
        self.rich.run_format(name)
        self._sync_char(self.rich.currentCharFormat())
        self._sync_block()

    def _rich_toolbar(self) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar1, bar2 = QToolBar(), QToolBar()
        for b in (bar1, bar2):
            b.setIconSize(QSize(18, 18))
            lay.addWidget(b)
        r = self.rich
        self._act(bar1, "undo", "fmt.undo", r.undo)
        self._act(bar1, "redo", "fmt.redo", r.redo)
        bar1.addSeparator()
        self.style_box = QComboBox()
        for label, level in ((t("fmt.normal"), 0), (t("fmt.h1"), 1), (t("fmt.h2"), 2), (t("fmt.h3"), 3)):
            self.style_box.addItem(label, level)
        self.style_box.setToolTip(t("fmt.style_tip"))
        self.style_box.activated.connect(lambda: (r.set_heading(self.style_box.currentData()), r.setFocus()))
        bar1.addWidget(self.style_box)
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(190)
        self.font_box.currentFontChanged.connect(lambda f: (not self._loading) and (r.set_family(f.family()), r.setFocus()))
        bar1.addWidget(self.font_box)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        for s in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72):
            self.size_box.addItem(str(s))
        self.size_box.setMaximumWidth(64)
        self.size_box.textActivated.connect(lambda s: (r.set_size(float(s)) if s.replace(".", "").isdigit() else None, r.setFocus()))
        bar1.addWidget(self.size_box)
        bar1.addSeparator()
        self.a_bold = self._fmt(bar1, "bold", "fmt.bold", "bold", checkable=True)
        self.a_italic = self._fmt(bar1, "italic", "fmt.italic", "italic", checkable=True)
        self.a_under = self._fmt(bar1, "underline", "fmt.underline", "underline", checkable=True)
        self.a_strike = self._fmt(bar1, "strike", "fmt.strike", "strike", checkable=True)
        self._fmt(bar1, "superscript", "fmt.superscript", "superscript")
        self._fmt(bar1, "subscript", "fmt.subscript", "subscript")
        bar1.addSeparator()
        self.color_btn = self._color_button(bar1, "fmt.color", PRESET_COLORS, r.set_color, "A")
        self.hl_btn = self._color_button(bar1, "fmt.highlight", HIGHLIGHTS, r.set_highlight, "H")
        bar1.addWidget(self._clear_button())

        group = QActionGroup(self)
        self.a_align = {}
        for icon, tip, align, name in (("left", "fmt.left", Qt.AlignLeft, "left"), ("center", "fmt.center", Qt.AlignHCenter, "center"),
                                       ("right", "fmt.right", Qt.AlignRight, "right"), ("justify", "fmt.justify", Qt.AlignJustify, "justify")):
            a = self._fmt(bar2, icon, tip, name, checkable=True)
            group.addAction(a)
            self.a_align[align] = a
        bar2.addSeparator()
        self._fmt(bar2, "bullets", "fmt.bullets", "bullets")
        self._fmt(bar2, "numbers", "fmt.numbers", "numbers")
        self._fmt(bar2, "outdent", "fmt.outdent", "outdent")
        self._fmt(bar2, "indent", "fmt.indent", "indent")
        spacing = QToolButton()
        spacing.setIcon(theme.glyph_icon("spacing"))
        spacing.setToolTip(t("fmt.spacing"))
        spacing.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(spacing)
        for factor in (1.0, 1.15, 1.5, 2.0, 2.5, 3.0):
            menu.addAction(t("fmt.line", n=f"{factor:g}"), lambda f=factor: r.set_line_spacing(f))
        menu.addSeparator()
        for before, after, key in ((0, 0, "fmt.para_none"), (0, 6, "fmt.para_small"), (6, 12, "fmt.para_medium"), (12, 18, "fmt.para_large")):
            menu.addAction(t(key), lambda b=before, a=after: r.set_paragraph_spacing(b, a))
        spacing.setMenu(menu)
        bar2.addWidget(spacing)
        bar2.addSeparator()
        self._fmt(bar2, "link", "fmt.link", "link")
        table = QToolButton()
        table.setIcon(theme.glyph_icon("table"))
        table.setToolTip(t("fmt.table"))
        table.setPopupMode(QToolButton.InstantPopup)
        tmenu = QMenu(table)
        tmenu.addAction(t("fmt.table_insert"), self._insert_table)
        tmenu.addSeparator()
        for op, key in (("row_above", "fmt.row_above"), ("row_below", "fmt.row_below"), ("col_left", "fmt.col_left"),
                        ("col_right", "fmt.col_right"), ("del_row", "fmt.del_row"), ("del_col", "fmt.del_col")):
            tmenu.addAction(t(key), lambda o=op: r.table_op(o))
        tmenu.addAction(t("fmt.cell_color"), self._cell_color)
        table.setMenu(tmenu)
        bar2.addWidget(table)
        self._act(bar2, "rule", "fmt.rule", r.insert_rule)
        bar2.addSeparator()
        self._act(bar2, "image", "fmt.image", self._insert_image)
        self._act(bar2, "screenshot", "fmt.screenshot", self._take_screenshot)
        a_resize = self._act(bar2, "resize", "fmt.resize", self._resize_image)
        a_resize.setToolTip(t("fmt.resize_tip"))
        self._act(bar2, "code", "fmt.code", self._insert_code, shortcut=EDITOR_SHORTCUTS["code"])
        var = QToolButton()
        var.setIcon(theme.glyph_icon("variable"))
        var.setToolTip(t("fmt.variable"))
        var.setPopupMode(QToolButton.InstantPopup)
        var.setMenu(self._variables_menu(var))
        bar2.addWidget(var)
        return holder

    def _clear_button(self) -> QToolButton:
        """Clear formatting: click = selection/paragraph; menu = whole document or paste as plain text."""
        btn = QToolButton()
        btn.setIcon(theme.glyph_icon("clear"))
        btn.setToolTip(with_shortcut(t("fmt.clear"), "clear"))
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        btn.clicked.connect(lambda: self._run_format("clear"))
        menu = QMenu(btn)
        menu.addAction(with_shortcut(t("fmt.clear"), "clear"), lambda: self._run_format("clear"))
        menu.addAction(t("fmt.clear_all"), lambda: (self.rich.clear_all_formatting(), self._sync_block()))
        menu.addAction(with_shortcut(t("fmt.paste_plain"), "paste_plain"), lambda: self._run_format("paste_plain"))
        btn.setMenu(menu)
        return btn

    def _color_button(self, bar: QToolBar, tip: str, colors: list[str], apply, letter: str) -> QToolButton:
        btn = QToolButton()
        btn.setToolTip(t(tip))
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        btn.setProperty("color", colors[2] if letter == "A" else colors[0])
        btn.setIcon(theme.color_icon(btn.property("color"), letter))
        btn.clicked.connect(lambda: apply(QColor(btn.property("color"))))
        menu = QMenu(btn)

        def choose(color: str | None) -> None:
            if color:
                btn.setProperty("color", color)
                btn.setIcon(theme.color_icon(color, letter))
            apply(QColor(color) if color else None)
            self.rich.setFocus()

        for col in colors:
            menu.addAction(theme.color_icon(col, " "), col, lambda c=col: choose(c))
        menu.addSeparator()
        menu.addAction(t("fmt.no_color"), lambda: choose(None))

        def more() -> None:
            col = QColorDialog.getColor(QColor(btn.property("color")), self)
            if col.isValid():
                choose(col.name())

        menu.addAction(t("fmt.more_colors"), more)
        btn.setMenu(menu)
        bar.addWidget(btn)
        return btn

    def _variables_menu(self, parent) -> QMenu:
        menu = QMenu(parent)
        for token, key in VARIABLES:
            menu.addAction(f"{token}  —  {t(key)}", lambda tk=token: self._insert_token(tk))

        def ask() -> None:
            label, ok = QInputDialog.getText(self, t("var.input"), t("var.input_label"))
            if ok and label.strip():
                self._insert_token("{input:" + label.strip() + "}")

        menu.addAction(f"{INPUT_EXAMPLE}  —  " + t("var.input"), ask)
        return menu

    def _insert_token(self, token: str) -> None:
        target = self.rich if self.stack.currentWidget() is self.rich_page else self.code
        target.insertPlainText(token) if target is self.code else target.textCursor().insertText(token)
        target.setFocus()

    def _new_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(theme.glyph_icon("edit"), t("new.rich"), lambda: self.new_template("rich"))
        menu.addAction(theme.glyph_icon("copy"), t("new.clipboard"), self.new_from_clipboard)
        menu.addAction(theme.glyph_icon("text"), t("new.text"), lambda: self.new_template("text"))
        menu.addAction(theme.glyph_icon("doc"), t("new.markdown"), lambda: self.new_template("markdown"))
        code = menu.addMenu(theme.glyph_icon("code"), t("new.code"))
        for lang in CODE_LANGS:
            if lang in NEW_CODE_EXT:
                code.addAction(formats.LANGUAGE_NAMES.get(lang, lang), lambda l=lang: self.new_template("code", l))
        menu.addSeparator()
        menu.addAction(theme.glyph_icon("import"), t("new.import"), self.import_files)
        menu.addAction(theme.glyph_icon("folder"), t("new.category"), self.new_category)
        return menu

    # ================================================================ settings
    def apply_settings(self) -> None:
        s = self.c.settings
        font = QFont(s.get("editor_font_family"))
        font.setPointSize(int(s.get("editor_font_size")))
        self.rich.setFont(font)
        self.rich.document().setDefaultFont(font)
        self.code.set_code_font(s.get("code_font_family"), int(s.get("code_font_size")))
        style = "monokai" if s.get("theme") == "dark" else "default"
        self.code.highlighter.set_language(self.code.highlighter.language, style)

    # ================================================================ tree
    def reload_tree(self) -> None:
        keep = self.current.rel if self.current else None
        query = fold(self.filter.text())
        self.tree.drag_allowed = not query  # moving inside a filtered view would be confusing
        self.tree.blockSignals(True)
        self.tree.clear()
        lib = self.c.library
        folders: dict[str, QTreeWidgetItem] = {}

        def folder_item(cat: str) -> QTreeWidgetItem | None:
            if not cat:
                return None
            if cat in folders:
                return folders[cat]
            parent_cat, _, leaf = cat.rpartition("/")
            parent = folder_item(parent_cat)
            item = QTreeWidgetItem([leaf])
            item.setIcon(0, theme.glyph_icon("folder"))
            item.setData(0, ROLE_REL, None)
            item.setData(0, ROLE_CAT, cat)
            (parent.addChild(item) if parent else self.tree.addTopLevelItem(item))
            item.setExpanded(True)
            folders[cat] = item
            return item

        for cat in self._all_categories():
            if not query:
                folder_item(cat)
        select = None
        for tpl in lib.templates:
            if query and not all(w in tpl.search for w in query.split()):
                continue
            item = QTreeWidgetItem([("★ " if lib.usage.favourite(tpl.rel) else "") + tpl.name])
            item.setData(0, ROLE_REL, tpl.rel)
            item.setToolTip(0, f"{tpl.rel}\n{tpl.description}".strip())
            icon = {"rich": "edit", "code": "code", "image": "image", "docx": "doc", "rtf": "doc"}.get(tpl.kind, "text")
            item.setIcon(0, theme.glyph_icon(icon))
            parent = folder_item(tpl.category)
            (parent.addChild(item) if parent else self.tree.addTopLevelItem(item))
            if tpl.rel == keep:
                select = item
        self.tree.blockSignals(False)
        if select is not None:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(select)
            self.tree.blockSignals(False)
        cats = self._all_categories()
        text = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("")
        self.category.addItems(cats)
        self.category.setEditText(text)
        self.category.blockSignals(False)

    def _all_categories(self) -> list[str]:
        root = self.c.library.root
        cats = set(self.c.library.categories())
        if root.is_dir():
            for folder in self.c.library.folders()[1:]:
                cats.add(folder.relative_to(root).as_posix())
        return sorted(cats, key=fold)

    def _tree_selected(self, item: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        rel = item.data(0, ROLE_REL) if item else None
        if not rel or (self.current and rel == self.current.rel and not self._new_path):
            return
        if not self.maybe_save():
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(previous)
            self.tree.blockSignals(False)
            return
        self.open_template(rel)

    def _tree_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        rel = item.data(0, ROLE_REL) if item else None
        if rel:
            tpl = self.c.library.get(rel)
            fav = self.c.library.usage.favourite(rel)
            menu.addAction(theme.glyph_icon("starfill" if not fav else "star"),
                           t("tree.unfav") if fav else t("tree.fav"), lambda: self._toggle_fav(rel))
            menu.addAction(theme.glyph_icon("rename"), t("tree.rename"), lambda: self.rename_template(rel))
            menu.addAction(theme.glyph_icon("folder"), t("tree.move"), lambda: self.move_template(rel))
            menu.addAction(theme.glyph_icon("copy"), t("tree.duplicate"), lambda: self.duplicate_template(rel))
            menu.addAction(theme.glyph_icon("folder"), t("tree.reveal"), lambda: self.c.reveal(tpl.path(self.c.library.root)))
            menu.addSeparator()
            menu.addAction(theme.glyph_icon("delete"), t("tree.delete"), lambda: self.delete_template(rel))
        else:
            cat = item.data(0, ROLE_CAT) if item else ""
            menu.addAction(theme.glyph_icon("new"), t("new.rich"), lambda: self.new_template("rich", category=cat))
            menu.addAction(theme.glyph_icon("folder"), t("new.category"), lambda: self.new_category(cat))
            if cat:
                menu.addAction(theme.glyph_icon("folder"), t("tree.reveal"), lambda: self.c.reveal(self.c.library.root / cat))
                menu.addSeparator()
                menu.addAction(theme.glyph_icon("rename"), t("folder.rename"), lambda: self.rename_folder(cat))
                menu.addAction(theme.glyph_icon("folder"), t("folder.move"), lambda: self.move_folder(cat))
                menu.addSeparator()
                menu.addAction(theme.glyph_icon("delete"), t("folder.delete"), lambda: self.delete_folder(cat))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _toggle_fav(self, rel: str) -> None:
        self.c.library.usage.set_favourite(rel, not self.c.library.usage.favourite(rel))
        self.reload_tree()

    # ================================================================ open / show
    def _show_page(self, kind: str | None) -> None:
        page = {None: self.empty_page, "rich": self.rich_page, "code": self.code_page, "text": self.code_page,
                "markdown": self.code_page}.get(kind, self.view_page)
        self.stack.setCurrentWidget(page)
        rich_meta = kind == "rich"
        for w in (self.tags, self.abbrev, self.mode, self.description):
            w.setEnabled(rich_meta)
            w.setToolTip("" if rich_meta else t("editor.meta_rich_only"))
        for w in (self.name, self.category, self.save_btn, self.copy_btn):
            w.setEnabled(kind is not None)

    def open_template(self, rel: str) -> None:
        tpl = self.c.library.get(rel)
        if tpl is None:
            return
        path = tpl.path(self.c.library.root)
        self._loading = True
        self.current, self._new_path = tpl, None
        self.name.setText(tpl.name)
        self.category.setEditText(tpl.category)
        self.tags.setText(", ".join(tpl.tags))
        self.abbrev.setText(tpl.abbreviation)
        self.description.setText(tpl.description)
        self.mode.setCurrentIndex(max(0, self.mode.findData(tpl.mode)))
        self._show_page(tpl.kind)
        try:
            if tpl.kind == "rich":
                load_document(self.rich, path)
                self.rich.setFocus()
                self._sync_char(self.rich.currentCharFormat())
                self._sync_block()
            elif tpl.kind in ("code", "text", "markdown"):
                self.code.setPlainText(formats.read_text(path))
                lang = tpl.language or highlight.detect_language(self.code.toPlainText()[:4000]) if tpl.kind != "text" else ""
                self.code_lang.setCurrentIndex(max(0, self.code_lang.findData(lang)))
                self.code.highlighter.set_language(lang)
                self.code.document().setModified(False)
                self.code.setFocus()
            else:
                rendered = self.c.renderer.render(tpl, self.c.library.root)
                self.viewer.setHtml(rendered.html or f"<pre>{rendered.text}</pre>")
                self.view_label.setText(t("editor.readonly", kind=tpl.kind.upper()))
        except OSError as exc:
            QMessageBox.warning(self, "AutoTemplates", str(exc))
        self._loading = False
        self._set_dirty(False)
        self.status.setText(tpl.rel)
        self._select_in_tree(rel)

    def _select_in_tree(self, rel: str) -> None:
        it = self.tree.invisibleRootItem()
        stack = [it.child(i) for i in range(it.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, ROLE_REL) == rel:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(item)
                self.tree.blockSignals(False)
                return
            stack.extend(item.child(i) for i in range(item.childCount()))

    # ================================================================ new
    def new_template(self, kind: str = "rich", language: str = "", *, category: str | None = None,
                     html: str | None = None, text: str | None = None) -> None:
        if not self.maybe_save():
            return
        ext = {"rich": ".html", "text": ".txt", "markdown": ".md"}.get(kind) or NEW_CODE_EXT.get(language, ".txt")
        cat = category if category is not None else (self.current.category if self.current else "")
        folder = self.c.library.root / cat if cat else self.c.library.root
        self._new_path = unique_path(folder, t("new.default_name"), ext)
        self.current = None
        self._loading = True
        self.name.setText(self._new_path.stem)
        self.category.setEditText(cat)
        for w in (self.tags, self.abbrev, self.description):
            w.clear()
        self.mode.setCurrentIndex(0)
        page_kind = "code" if kind == "code" else kind
        self._show_page(page_kind)
        if kind == "rich":
            self.rich.document().setBaseUrl(QUrl.fromLocalFile(str(folder) + "/"))
            self.rich.setHtml(html or "")
            self.rich.document().setModified(True)
            self._sync_char(self.rich.currentCharFormat())
        else:
            self.code.setPlainText(text or "")
            self.code_lang.setCurrentIndex(max(0, self.code_lang.findData(language or ("markdown" if kind == "markdown" else ""))))
            self.code.document().setModified(True)
        self._loading = False
        self._set_dirty(True)
        self.status.setText(t("editor.new_status"))
        self.name.setFocus()
        self.name.selectAll()
        self.show_and_raise()

    def new_from_clipboard(self) -> None:
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None:
            return
        if mime.hasHtml() or mime.hasImage():
            self.new_template("rich")
            self.rich.insertFromMimeData(mime)
        elif mime.hasText():
            text = mime.text()
            lang = highlight.detect_language(text)
            if lang and lang != "markdown":
                self.new_template("code", lang, text=text)
            else:
                self.new_template("markdown" if lang == "markdown" else "text", text=text)

    def new_category(self, parent: str = "") -> None:
        name, ok = QInputDialog.getText(self, t("new.category"), t("new.category_name"))
        if ok and name.strip():
            path = self.c.library.root / parent / safe_name(name) if parent else self.c.library.root / safe_name(name)
            path.mkdir(parents=True, exist_ok=True)
            self.reload_tree()

    def import_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(formats.SUPPORTED_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, t("new.import"), str(Path.home()), f"{t('new.supported')} ({exts})")
        if not files:
            return
        cat = self.category.currentText().strip() if self.current or self._new_path else ""
        folder = self.c.library.root / cat if cat else self.c.library.root
        folder.mkdir(parents=True, exist_ok=True)
        last = None
        for f in files:
            src = Path(f)
            dst = unique_path(folder, src.stem, src.suffix.lower())
            shutil.copy2(src, dst)
            last = dst
        self.c.rescan(sync=True)
        if last:
            self.open_template(last.relative_to(self.c.library.root).as_posix())

    # ================================================================ save
    def _mark_dirty(self, *_):
        if not self._loading:
            self._set_dirty(True)

    def _doc_modified(self, modified: bool) -> None:
        if modified and not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.setWindowTitle(("● " if dirty else "") + (self.name.text() or "AutoTemplates") + " — AutoTemplates")

    def maybe_save(self) -> bool:
        if not getattr(self, "_dirty", False) or (self.current is None and self._new_path is None):
            return True
        answer = QMessageBox.question(self, "AutoTemplates", t("editor.unsaved", name=self.name.text()),
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save()
        if answer == QMessageBox.Discard:
            self._set_dirty(False)
            self._new_path = None
            return True
        return False

    def _target_path(self) -> Path | None:
        old = self._new_path or (self.current.path(self.c.library.root) if self.current else None)
        if old is None:
            return None
        cat = "/".join(safe_name(p) for p in self.category.currentText().strip().replace("\\", "/").split("/") if p.strip())
        folder = self.c.library.root / cat if cat else self.c.library.root
        return folder / (safe_name(self.name.text()) + old.suffix)

    def save(self) -> bool:
        old = self._new_path or (self.current.path(self.c.library.root) if self.current else None)
        target = self._target_path()
        if target is None:
            return False
        if target != old and target.exists():
            QMessageBox.warning(self, "AutoTemplates", t("editor.exists", name=target.name))
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            moved = old is not None and old.exists() and target != old
            if moved:
                old.replace(target)
                old_assets, new_assets = old.with_suffix(".assets"), target.with_suffix(".assets")
                if old_assets.is_dir() and not new_assets.exists():
                    old_assets.replace(new_assets)
            kind = self.current.kind if self.current else formats.kind_for(target)
            if kind == "rich":
                markup = self.rich.toHtml()
                if moved:
                    markup = markup.replace(old.with_suffix(".assets").resolve().as_uri(),
                                            target.with_suffix(".assets").resolve().as_uri())
                markup = localize_images(markup, target)
                markup = formats.write_meta(markup, {
                    "tags": ", ".join(x.strip() for x in self.tags.text().split(",") if x.strip()),
                    "abbreviation": self.abbrev.text().strip(),
                    "description": self.description.text().strip(),
                    "mode": self.mode.currentData() or "",
                })
                target.write_text(markup, encoding="utf-8")
                self.rich.document().setBaseUrl(QUrl.fromLocalFile(str(target.parent) + "/"))
                self.rich.document().setModified(False)
            elif kind in ("code", "text", "markdown"):
                target.write_text(self.code.toPlainText(), encoding="utf-8")
                self.code.document().setModified(False)
        except OSError as exc:
            QMessageBox.critical(self, "AutoTemplates", t("editor.save_failed", error=str(exc)))
            return False
        root = self.c.library.root
        if old is not None and old != target and old.exists() is False:
            old_rel = old.relative_to(root).as_posix() if old.is_relative_to(root) else None
            if old_rel:
                self.c.library.remove(old_rel)
                self.c.library.usage.rename(old_rel, target.relative_to(root).as_posix())
        tpl = self.c.library.refresh_one(target)
        self._new_path = None
        self.current = tpl
        self._set_dirty(False)
        self.c.renderer.clear()
        self.reload_tree()
        if tpl:
            self._select_in_tree(tpl.rel)
            self.status.setText(t("editor.saved", rel=tpl.rel))
        self.c.library_changed()
        return True

    # ================================================================ template ops
    def rename_template(self, rel: str) -> None:
        if self.current is None or self.current.rel != rel:
            self.open_template(rel)
        name, ok = QInputDialog.getText(self, t("tree.rename"), t("editor.name"), text=self.name.text())
        if ok and name.strip():
            self.name.setText(name.strip())
            self._set_dirty(True)
            self.save()

    def move_template(self, rel: str) -> None:
        tpl = self.c.library.get(rel)
        if not tpl:
            return
        cat = self._pick_folder(t("tree.move"), tpl.category, [""] + self._all_categories())
        if cat is not None:
            self.move_template_to(rel, cat)

    def move_template_to(self, rel: str, dest: str) -> None:
        if self.current and self.current.rel == rel:
            if not self.maybe_save():
                return
            rel = self.current.rel if self.current else rel  # saving may have renamed it
        self._run(lambda: folders.move_template(self.c.library, rel, dest))

    def duplicate_template(self, rel: str) -> None:
        tpl = self.c.library.get(rel)
        if not tpl:
            return
        src = tpl.path(self.c.library.root)
        dst = unique_path(src.parent, src.stem + " - " + t("tree.copy_suffix"), src.suffix)
        if tpl.kind == "rich":
            markup = formats.read_text(src)
            markup = absolutize_images(markup, src.parent)
            dst.write_text(localize_images(markup, dst), encoding="utf-8")
        else:
            shutil.copy2(src, dst)
        self.c.library.refresh_one(dst)
        self.reload_tree()
        self.open_template(dst.relative_to(self.c.library.root).as_posix())

    def delete_template(self, rel: str) -> None:
        tpl = self.c.library.get(rel)
        if not tpl:
            return
        if QMessageBox.question(self, "AutoTemplates", t("tree.delete_confirm", name=tpl.name)) != QMessageBox.Yes:
            return
        self._delete(lambda permanent: folders.delete_template(self.c.library, rel, self._trash, permanent=permanent),
                     tpl.name)

    # ================================================================ folder ops
    def rename_folder(self, cat: str) -> None:
        name, ok = QInputDialog.getText(self, t("folder.rename"), t("new.category_name"), text=folders.leaf_of(cat))
        if ok and name.strip() and name.strip() != folders.leaf_of(cat):
            self.move_folder_to(cat, folders.parent_of(cat), name.strip())

    def move_folder(self, cat: str) -> None:
        choices = [""] + [c for c in self._all_categories() if not folders.is_inside(c, cat)]
        dest = self._pick_folder(t("folder.move_to", name=folders.leaf_of(cat)), folders.parent_of(cat), choices)
        if dest is not None:
            self.move_folder_to(cat, dest)

    def move_folder_to(self, cat: str, dest_parent: str, new_name: str | None = None) -> None:
        if self.current and folders.is_inside(self.current.category, cat) and not self.maybe_save():
            return
        policy = ASK
        while True:
            try:
                self._run(lambda: folders.move_folder(self.c.library, cat, dest_parent, new_name=new_name,
                                                      conflict=policy), old_cat=cat)
                return
            except FolderConflict as conflict:
                policy = self._ask_conflict(conflict.target)
                if policy is None:
                    return

    def delete_folder(self, cat: str) -> None:
        n_templates, n_folders = folders.folder_counts(self.c.library.root, cat)
        text = t("folder.delete_confirm", name=folders.leaf_of(cat), templates=n_templates, folders=n_folders)
        if QMessageBox.question(self, "AutoTemplates", text) != QMessageBox.Yes:
            return
        self._delete(lambda permanent: folders.delete_folder(self.c.library, cat, self._trash, permanent=permanent),
                     folders.leaf_of(cat), old_cat=cat)

    def _tree_dropped(self, kind: str, value: str, target: str) -> None:
        if kind == "template":
            self.move_template_to(value, target)
        else:
            self.move_folder_to(value, target)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _trash(path: Path) -> bool:
        result = QFile.moveToTrash(str(path))
        ok = result[0] if isinstance(result, tuple) else bool(result)  # PySide may return (ok, path_in_trash)
        return bool(ok) and not path.exists()

    def _pick_folder(self, title: str, current: str, choices: list[str]) -> str | None:
        """Folder chooser; the library root is shown as a label, a typed new path is allowed."""
        root_label = t("folder.root")
        labels = [c or root_label for c in choices]
        idx = choices.index(current) if current in choices else 0
        value, ok = QInputDialog.getItem(self, title, t("editor.category"), labels, idx, editable=True)
        if not ok:
            return None
        return "" if value.strip() in ("", root_label) else value.strip()

    def _ask_conflict(self, target: str) -> str | None:
        box = QMessageBox(QMessageBox.Question, "AutoTemplates", t("folder.conflict", name=target), parent=self)
        merge = box.addButton(t("folder.merge"), QMessageBox.AcceptRole)
        both = box.addButton(t("folder.keep_both"), QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(both)
        box.exec()
        return {merge: MERGE, both: KEEP_BOTH}.get(box.clickedButton())

    def _delete(self, op, name: str, *, old_cat: str | None = None) -> None:
        try:
            self._run(lambda: op(False), old_cat=old_cat, deleted=True)
        except TrashFailed:
            answer = QMessageBox.warning(self, "AutoTemplates", t("folder.trash_failed", name=name),
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                self._run(lambda: op(True), old_cat=old_cat, deleted=True)

    def _run(self, op, *, old_cat: str | None = None, deleted: bool = False):
        """Runs a file operation with the watcher paused; FolderConflict/TrashFailed go to the caller."""
        try:
            with self.c.library_operation():
                result = op()
        except (FolderConflict, TrashFailed):
            raise
        except FolderError as exc:
            QMessageBox.warning(self, "AutoTemplates", t(exc.key, **exc.kwargs))
            return None
        except OSError as exc:
            log.exception("Library operation failed")
            QMessageBox.critical(self, "AutoTemplates", t("folder.failed", error=str(exc)))
            self.reload_tree()
            return None
        self._after_operation(result, old_cat, deleted)
        return result

    def _after_operation(self, result: folders.Result, old_cat: str | None, deleted: bool) -> None:
        settings = self.c.settings
        note_folder = settings.get("noteit_folder") or ""
        if old_cat and deleted:
            if folders.is_inside(note_folder, old_cat):
                settings.set("noteit_folder", DEFAULTS["noteit_folder"])
        elif old_cat and result.folder and result.folder != old_cat:
            new_note_folder = folders.remap_category(note_folder, old_cat, result.folder)
            if new_note_folder != note_folder:
                settings.set("noteit_folder", new_note_folder)
        if self._new_path is not None and old_cat and result.folder and not deleted:
            self.category.setEditText(folders.remap_category(self.category.currentText().strip(), old_cat, result.folder))
        if self.current is not None:
            new_rel = result.moved.get(self.current.rel)
            if new_rel:
                self.reload_tree()
                self.open_template(new_rel)
            elif self.current.rel in result.deleted:
                self.current = None
                self._set_dirty(False)
                self._show_page(None)
        self.c.renderer.clear()
        self.reload_tree()
        if result.renamed:
            items = "\n".join(f"{old} → {new}" for old, new in result.renamed)
            QMessageBox.information(self, "AutoTemplates", t("folder.renamed", items=items))
        if result.moved or result.folder:
            self.status.setText(t("folder.done"))

    def convert_to_rich(self) -> None:
        """docx / rtf / image → an editable copy (.html) next to the original."""
        tpl = self.current
        if tpl is None:
            return
        rendered = self.c.renderer.render(tpl, self.c.library.root)
        src = tpl.path(self.c.library.root)
        dst = unique_path(src.parent, src.stem, ".html")
        markup = localize_images(rendered.html, dst)
        dst.write_text(markup, encoding="utf-8")
        self.c.library.refresh_one(dst)
        self.reload_tree()
        self.open_template(dst.relative_to(self.c.library.root).as_posix())

    def _open_external(self) -> None:
        if self.current:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current.path(self.c.library.root))))

    def _copy_result(self) -> None:
        if getattr(self, "_dirty", False) and not self.save():
            return
        if self.current:
            self.c.copy_template(self.current.rel, plain=False)
            self.status.setText(t("editor.copied"))

    # ================================================================ rich helpers
    def _sync_char(self, fmt: QTextCharFormat) -> None:
        self._loading = True
        self.a_bold.setChecked(fmt.fontWeight() >= QFont.DemiBold)
        self.a_italic.setChecked(fmt.fontItalic())
        self.a_under.setChecked(fmt.fontUnderline())
        self.a_strike.setChecked(fmt.fontStrikeOut())
        fams = fmt.fontFamilies()
        if fams:
            self.font_box.setCurrentFont(QFont(fams[0] if isinstance(fams, list) else str(fams)))
        size = fmt.fontPointSize() or fmt.font().pointSizeF() or self.rich.document().defaultFont().pointSizeF()
        self.size_box.setEditText(f"{size:g}")
        self._loading = False

    def _sync_block(self) -> None:
        cursor = self.rich.textCursor()
        align = self.rich.alignment()
        for al, act in self.a_align.items():
            act.setChecked(bool(align & al) if al != Qt.AlignLeft else not (align & (Qt.AlignHCenter | Qt.AlignRight | Qt.AlignJustify)))
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(cursor.blockFormat().headingLevel())))

    def _insert_link(self) -> None:
        self.rich.prompt_link()

    def _insert_table(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(t("fmt.table_insert"))
        form = QFormLayout(dlg)
        rows, cols = QSpinBox(), QSpinBox()
        rows.setRange(1, 100)
        cols.setRange(1, 20)
        rows.setValue(3)
        cols.setValue(3)
        form.addRow(t("fmt.rows"), rows)
        form.addRow(t("fmt.cols"), cols)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            self.rich.insert_table(rows.value(), cols.value())

    def _cell_color(self) -> None:
        col = QColorDialog.getColor(QColor("#fff59d"), self)
        if col.isValid():
            self.rich.set_cell_background(col)

    def _insert_image(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(formats.IMAGE_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, t("fmt.image"), str(Path.home() / "Pictures"), f"Images ({exts})")
        for f in files:
            self.rich.insert_image_file(Path(f))

    def _resize_image(self) -> None:
        self.rich.prompt_resize_image()

    def _take_screenshot(self) -> None:
        """Windows snipping (Win+Shift+S); the picture is inserted as soon as it reaches the clipboard."""
        self._screenshot_wait = True
        QTimer.singleShot(60_000, lambda: setattr(self, "_screenshot_wait", False))
        if not QDesktopServices.openUrl(QUrl("ms-screenclip:")):
            self.status.setText(t("fmt.screenshot_hint"))
        else:
            self.status.setText(t("fmt.screenshot_wait"))

    def _clipboard_changed(self) -> None:
        if not self._screenshot_wait:
            return
        mime = QGuiApplication.clipboard().mimeData()
        if mime is not None and mime.hasImage():
            self._screenshot_wait = False
            image = QGuiApplication.clipboard().image()
            self.rich.insert_image_file(self.rich.save_image(image))
            self.show_and_raise()
            self.status.setText(t("fmt.screenshot_done"))

    def _insert_code(self) -> None:
        s = self.c.settings
        dlg = CodeDialog(self, "monokai" if s.get("theme") == "dark" else "default", s.get("code_font_family"),
                         int(s.get("code_font_size")))
        if dlg.exec():
            code = dlg.edit.toPlainText()
            if code.strip():
                self.rich.insert_code_html(self.c.renderer.code(code, dlg.language()))

    def _rich_menu(self, pos) -> None:
        menu = self.rich.createStandardContextMenu(pos)
        menu.addSeparator()
        menu.addAction(t("fmt.paste_plain") + "\tCtrl+Shift+V", self.rich.paste_plain)
        menu.addAction(t("fmt.clear") + "\tCtrl+Space", lambda: self._run_format("clear"))
        menu.addAction(t("fmt.clear_all"), self.rich.clear_all_formatting)
        if self.rich.textCursor().currentTable() is not None:
            tm = menu.addMenu(t("fmt.table"))
            for op, key in (("row_above", "fmt.row_above"), ("row_below", "fmt.row_below"), ("col_left", "fmt.col_left"),
                            ("col_right", "fmt.col_right"), ("del_row", "fmt.del_row"), ("del_col", "fmt.del_col")):
                tm.addAction(t(key), lambda o=op: self.rich.table_op(o))
            tm.addAction(t("fmt.cell_color"), self._cell_color)
        if self.rich.image_at_cursor():
            menu.addAction(t("fmt.resize"), self._resize_image)
        menu.exec(self.rich.viewport().mapToGlobal(pos))

    # ================================================================ window
    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if self.maybe_save():
            event.accept()
        else:
            event.ignore()