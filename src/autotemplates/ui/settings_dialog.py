"""Settings: library folder, hotkey, insertion, look and editor fonts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFontComboBox, QFormLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from autotemplates import __version__
from autotemplates.core import highlight
from autotemplates.i18n import t
from autotemplates.platform import devpilot
from autotemplates.platform.hotkey import Hotkey


class SettingsDialog(QDialog):
    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.c = controller
        s = controller.settings
        self.setWindowTitle(t("settings.title"))
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # ---------------- general
        g = QWidget()
        gf = QFormLayout(g)
        row = QHBoxLayout()
        self.library = QLineEdit(s.get("library_dir") or str(s.library_dir))
        browse = QPushButton(t("settings.browse"))
        browse.clicked.connect(self._browse)
        row.addWidget(self.library, 1)
        row.addWidget(browse)
        gf.addRow(t("settings.library"), row)
        hk = QHBoxLayout()
        self.hotkey = QLineEdit(s.get("hotkey"))
        self.hotkey_rec = QKeySequenceEdit()
        self.hotkey_rec.setMaximumSequenceLength(1)
        self.hotkey_rec.keySequenceChanged.connect(self._recorded)
        hk.addWidget(self.hotkey, 1)
        hk.addWidget(QLabel(t("settings.or_press")))
        hk.addWidget(self.hotkey_rec, 1)
        gf.addRow(t("settings.hotkey"), hk)
        self.hotkey_state = QLabel(controller.hotkey_status())
        self.hotkey_state.setObjectName("Hint")
        self.hotkey_state.setWordWrap(True)
        gf.addRow("", self.hotkey_state)
        self.language = QComboBox()
        self.language.addItem("Română", "ro")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(max(0, self.language.findData(s.get("language"))))
        gf.addRow(t("settings.language"), self.language)
        self.theme = QComboBox()
        self.theme.addItem(t("settings.dark"), "dark")
        self.theme.addItem(t("settings.light"), "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.get("theme"))))
        gf.addRow(t("settings.theme"), self.theme)
        self.autostart = QCheckBox(t("settings.autostart"))
        self.autostart.setChecked(bool(s.get("start_with_windows")))
        if devpilot.owns("autostart"):
            self.autostart.setEnabled(False)
            self.autostart.setToolTip(t("settings.devpilot_owns"))
        gf.addRow("", self.autostart)
        tabs.addTab(g, t("settings.general"))

        # ---------------- insertion
        i = QWidget()
        inf = QFormLayout(i)
        self.mode = QComboBox()
        self.mode.addItem(t("settings.mode_rich"), "rich")
        self.mode.addItem(t("settings.mode_plain"), "plain")
        self.mode.setCurrentIndex(max(0, self.mode.findData(s.get("insert_mode"))))
        inf.addRow(t("settings.enter_inserts"), self.mode)
        self.restore = QCheckBox(t("settings.restore_clipboard"))
        self.restore.setChecked(bool(s.get("restore_clipboard")))
        inf.addRow("", self.restore)
        self.paste_delay = QSpinBox()
        self.paste_delay.setRange(0, 2000)
        self.paste_delay.setSuffix(" ms")
        self.paste_delay.setValue(int(s.get("paste_delay_ms")))
        inf.addRow(t("settings.paste_delay"), self.paste_delay)
        self.restore_delay = QSpinBox()
        self.restore_delay.setRange(150, 5000)
        self.restore_delay.setSuffix(" ms")
        self.restore_delay.setValue(int(s.get("restore_delay_ms")))
        inf.addRow(t("settings.restore_delay"), self.restore_delay)
        self.preview = QCheckBox(t("settings.preview"))
        self.preview.setChecked(bool(s.get("picker_show_preview")))
        inf.addRow("", self.preview)
        self.sort = QComboBox()
        self.sort.addItem(t("settings.sort_smart"), "smart")
        self.sort.addItem(t("settings.sort_name"), "name")
        self.sort.setCurrentIndex(max(0, self.sort.findData(s.get("picker_sort"))))
        inf.addRow(t("settings.sort"), self.sort)
        size = QHBoxLayout()
        self.pw, self.ph = QSpinBox(), QSpinBox()
        self.pw.setRange(360, 2000)
        self.ph.setRange(240, 1400)
        self.pw.setValue(int(s.get("picker_width")))
        self.ph.setValue(int(s.get("picker_height")))
        size.addWidget(self.pw)
        size.addWidget(QLabel("×"))
        size.addWidget(self.ph)
        size.addStretch(1)
        inf.addRow(t("settings.picker_size"), size)
        self.date_fmt = QLineEdit(s.get("date_format"))
        self.time_fmt = QLineEdit(s.get("time_format"))
        inf.addRow(t("settings.date_format"), self.date_fmt)
        inf.addRow(t("settings.time_format"), self.time_fmt)
        tabs.addTab(i, t("settings.insertion"))

        # ---------------- editor / code
        e = QWidget()
        ef = QFormLayout(e)
        self.ed_font = QFontComboBox()
        self.ed_font.setCurrentFont(s.get("editor_font_family"))
        self.ed_size = QSpinBox()
        self.ed_size.setRange(6, 48)
        self.ed_size.setValue(int(s.get("editor_font_size")))
        r1 = QHBoxLayout()
        r1.addWidget(self.ed_font, 1)
        r1.addWidget(self.ed_size)
        ef.addRow(t("settings.editor_font"), r1)
        self.code_font = QFontComboBox()
        self.code_font.setFontFilters(QFontComboBox.MonospacedFonts)
        self.code_font.setCurrentFont(s.get("code_font_family"))
        self.code_size = QSpinBox()
        self.code_size.setRange(6, 48)
        self.code_size.setValue(int(s.get("code_font_size")))
        r2 = QHBoxLayout()
        r2.addWidget(self.code_font, 1)
        r2.addWidget(self.code_size)
        ef.addRow(t("settings.code_font"), r2)
        self.code_style = QComboBox()
        self.code_style.addItems(highlight.style_names())
        self.code_style.setCurrentText(s.get("code_style"))
        ef.addRow(t("settings.code_style"), self.code_style)
        r3 = QHBoxLayout()
        self.code_bg = QLineEdit(s.get("code_background"))
        self.code_bg.setPlaceholderText(t("settings.code_bg_auto"))
        pick = QPushButton("…")
        pick.setMaximumWidth(32)
        pick.clicked.connect(self._pick_bg)
        r3.addWidget(self.code_bg, 1)
        r3.addWidget(pick)
        ef.addRow(t("settings.code_bg"), r3)
        tabs.addTab(e, t("settings.editor"))

        about = QLabel(t("settings.about", version=__version__, data=str(controller.paths.data_dir),
                         managed=t("settings.managed_yes") if devpilot.managed() else t("settings.managed_no")))
        about.setObjectName("Hint")
        about.setWordWrap(True)
        about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(about)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("settings.library"), self.library.text())
        if folder:
            self.library.setText(folder)

    def _recorded(self, seq: QKeySequence) -> None:
        text = seq.toString(QKeySequence.PortableText)
        if text:
            self.hotkey.setText(text.replace("Meta", "Win"))

    def _pick_bg(self) -> None:
        col = QColorDialog.getColor(QColor(self.code_bg.text() or "#f6f8fa"), self)
        if col.isValid():
            self.code_bg.setText(col.name())

    def _accept(self) -> None:
        try:
            Hotkey.parse(self.hotkey.text())
        except ValueError as exc:
            self.hotkey_state.setText(t("settings.hotkey_invalid", error=str(exc)))
            return
        default_lib = str(self.c.settings.library_dir) if not self.c.settings.get("library_dir") else None
        lib = self.library.text().strip()
        self.c.settings.update({
            "library_dir": "" if lib == default_lib else lib,
            "hotkey": self.hotkey.text().strip(),
            "language": self.language.currentData(),
            "theme": self.theme.currentData(),
            "start_with_windows": self.autostart.isChecked(),
            "insert_mode": self.mode.currentData(),
            "restore_clipboard": self.restore.isChecked(),
            "paste_delay_ms": self.paste_delay.value(),
            "restore_delay_ms": self.restore_delay.value(),
            "picker_show_preview": self.preview.isChecked(),
            "picker_sort": self.sort.currentData(),
            "picker_width": self.pw.value(),
            "picker_height": self.ph.value(),
            "date_format": self.date_fmt.text() or "%d.%m.%Y",
            "time_format": self.time_fmt.text() or "%H:%M",
            "editor_font_family": self.ed_font.currentFont().family(),
            "editor_font_size": self.ed_size.value(),
            "code_font_family": self.code_font.currentFont().family(),
            "code_font_size": self.code_size.value(),
            "code_style": self.code_style.currentText(),
            "code_background": self.code_bg.text().strip(),
        })
        self.accept()
