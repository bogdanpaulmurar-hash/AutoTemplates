"""Settings dialog with hotkey recorder and preferences."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFontComboBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from autotemplates import __version__
from autotemplates.core import highlight
from autotemplates.i18n import t
from autotemplates.platform import devpilot
from autotemplates.platform.hotkey import Hotkey


class SettingsDialog(QDialog):
    """Configuration dialog for hotkeys, paths, themes, and behavior."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.c = controller
        s = controller.settings
        self.setWindowTitle(t("settings.title"))
        self.resize(560, 480)

        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # ----------------------------------------------------------- General
        g = QWidget()
        gf = QFormLayout(g)
        self.library = QLineEdit(str(s.library_dir) if not s.get("library_dir") else s.get("library_dir"))
        browse = QPushButton(t("settings.browse"))
        browse.clicked.connect(self._browse)
        r1 = QHBoxLayout()
        r1.addWidget(self.library, 1)
        r1.addWidget(browse)
        gf.addRow(t("settings.library"), r1)

        # Global Hotkey (Picker / Launcher)
        hk = QHBoxLayout()
        self.hotkey = QLineEdit(s.get("hotkey"))
        from PySide6.QtWidgets import QKeySequenceEdit
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

        # Quick Launcher toggle at main hotkey
        self.launcher_enabled = QCheckBox(t("settings.launcher_enabled"))
        self.launcher_enabled.setChecked(bool(s.get("launcher_enabled", True)))
        gf.addRow("", self.launcher_enabled)

        # Dedicated NoteIT Hotkey
        hk_n = QHBoxLayout()
        self.noteit_hotkey = QLineEdit(s.get("noteit_hotkey") or "")
        self.noteit_hotkey_rec = QKeySequenceEdit()
        self.noteit_hotkey_rec.setMaximumSequenceLength(1)
        self.noteit_hotkey_rec.keySequenceChanged.connect(self._recorded_noteit)
        hk_n.addWidget(self.noteit_hotkey, 1)
        hk_n.addWidget(QLabel(t("settings.or_press")))
        hk_n.addWidget(self.noteit_hotkey_rec, 1)
        gf.addRow(t("settings.noteit_hotkey"), hk_n)

        self.language = QComboBox()
        self.language.addItem("Română", "ro")
        self.language.addItem("English", "en")
        idx = self.language.findData(s.get("language"))
        if idx >= 0:
            self.language.setCurrentIndex(idx)
        gf.addRow(t("settings.language"), self.language)

        self.theme = QComboBox()
        self.theme.addItem(t("settings.dark"), "dark")
        self.theme.addItem(t("settings.light"), "light")
        idx = self.theme.findData(s.get("theme"))
        if idx >= 0:
            self.theme.setCurrentIndex(idx)
        gf.addRow(t("settings.theme"), self.theme)

        self.autostart = QCheckBox(t("settings.autostart"))
        self.autostart.setChecked(bool(s.get("start_with_windows")))
        if devpilot.managed():
            self.autostart.setEnabled(False)
            self.autostart.setText(self.autostart.text() + " " + t("settings.devpilot_owns"))
        gf.addRow("", self.autostart)
        tabs.addTab(g, t("settings.general"))

        # --------------------------------------------------------- Insertion
        i = QWidget()
        inf = QFormLayout(i)
        self.insert_mode = QComboBox()
        self.insert_mode.addItem(t("settings.mode_rich"), "rich")
        self.insert_mode.addItem(t("settings.mode_plain"), "plain")
        idx = self.insert_mode.findData(s.get("insert_mode"))
        if idx >= 0:
            self.insert_mode.setCurrentIndex(idx)
        inf.addRow(t("settings.mode"), self.insert_mode)
        inf.addRow("", QLabel(t("settings.enter_inserts")))

        self.base_font = QComboBox()
        self.base_font.addItem(t("settings.base_font_editor"), "editor")
        self.base_font.addItem(t("settings.base_font_target"), "target")
        self.base_font.setCurrentIndex(max(0, self.base_font.findData(s.get("insert_base_font"))))
        inf.addRow(t("settings.base_font"), self.base_font)

        self.images = QComboBox()
        for key in ("auto", "file", "data"):
            self.images.addItem(t(f"settings.images_{key}"), key)
        self.images.setCurrentIndex(max(0, self.images.findData(s.get("insert_images"))))
        self.images.setToolTip(t("settings.images_tip"))
        inf.addRow(t("settings.images"), self.images)

        self.office_com = QCheckBox(t("settings.office_com"))
        self.office_com.setChecked(bool(s.get("office_com_paste")))
        inf.addRow("", self.office_com)

        self.restore_clip = QCheckBox(t("settings.restore_clipboard"))
        self.restore_clip.setChecked(bool(s.get("restore_clipboard")))
        inf.addRow("", self.restore_clip)

        self.paste_delay = QSpinBox()
        self.paste_delay.setRange(0, 1000)
        self.paste_delay.setSingleStep(10)
        self.paste_delay.setValue(int(s.get("paste_delay_ms")))
        inf.addRow(t("settings.paste_delay"), self.paste_delay)

        self.restore_delay = QSpinBox()
        self.restore_delay.setRange(50, 5000)
        self.restore_delay.setSingleStep(50)
        self.restore_delay.setValue(int(s.get("restore_delay_ms")))
        inf.addRow(t("settings.restore_delay"), self.restore_delay)

        self.preview = QCheckBox(t("settings.preview"))
        self.preview.setChecked(bool(s.get("picker_show_preview")))
        inf.addRow("", self.preview)

        self.sort = QComboBox()
        self.sort.addItem(t("settings.sort_smart"), "smart")
        self.sort.addItem(t("settings.sort_name"), "name")
        self.sort.addItem(t("settings.sort_recent"), "recent")
        idx = self.sort.findData(s.get("picker_sort"))
        if idx >= 0:
            self.sort.setCurrentIndex(idx)
        inf.addRow(t("settings.sort"), self.sort)

        self.stats_days = QSpinBox()
        self.stats_days.setRange(0, 3650)
        self.stats_days.setValue(int(s.get("stats_keep_days")))
        self.stats_days.setToolTip(t("settings.stats_keep_days_tip"))
        inf.addRow(t("settings.stats_keep_days"), self.stats_days)

        dim = QHBoxLayout()
        self.pw = QSpinBox()
        self.pw.setRange(400, 2000)
        self.pw.setValue(int(s.get("picker_width")))
        self.ph = QSpinBox()
        self.ph.setRange(300, 1400)
        self.ph.setValue(int(s.get("picker_height")))
        dim.addWidget(self.pw)
        dim.addWidget(QLabel("×"))
        dim.addWidget(self.ph)
        inf.addRow(t("settings.picker_size"), dim)

        self.date_fmt = QLineEdit(s.get("date_format"))
        inf.addRow(t("settings.date_format"), self.date_fmt)
        self.time_fmt = QLineEdit(s.get("time_format"))
        inf.addRow(t("settings.time_format"), self.time_fmt)
        tabs.addTab(i, t("settings.insertion"))

        # ------------------------------------------------------------ Editor
        e = QWidget()
        ef = QFormLayout(e)
        self.ed_font = QFontComboBox()
        self.ed_font.setCurrentFont(QFont(s.get("editor_font_family")))
        self.ed_size = QSpinBox()
        self.ed_size.setRange(8, 36)
        self.ed_size.setValue(int(s.get("editor_font_size")))
        r = QHBoxLayout()
        r.addWidget(self.ed_font, 1)
        r.addWidget(self.ed_size)
        ef.addRow(t("settings.editor_font"), r)

        self.code_font = QFontComboBox()
        self.code_font.setCurrentFont(QFont(s.get("code_font_family")))
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

        # ------------------------------------------------------ Version & About
        about_box = QGroupBox("Despre AutoTemplates")
        about_lay = QVBoxLayout(about_box)
        ver_lbl = QLabel(f"<b>AutoTemplates v{__version__}</b> (cu NoteIT, Quick Launcher & [P3] Category View)")
        ver_lbl.setStyleSheet("font-size: 10pt; color: #5b6cff;")
        about_lay.addWidget(ver_lbl)

        about = QLabel(t("settings.about", version=__version__, data=str(controller.paths.data_dir),
                         managed=t("settings.managed_yes") if devpilot.managed() else t("settings.managed_no")))
        about.setObjectName("Hint")
        about.setWordWrap(True)
        about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        about_lay.addWidget(about)
        lay.addWidget(about_box)

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

    def _recorded_noteit(self, seq: QKeySequence) -> None:
        text = seq.toString(QKeySequence.PortableText)
        if text:
            self.noteit_hotkey.setText(text.replace("Meta", "Win"))

    def _pick_bg(self) -> None:
        col = QColorDialog.getColor(QColor(self.code_bg.text() or "#f6f8fa"), self)
        if col.isValid():
            self.code_bg.setText(col.name())

    def _accept(self) -> None:
        try:
            Hotkey.parse(self.hotkey.text().strip())
        except ValueError as exc:
            self.hotkey_state.setText(t("settings.hotkey_invalid", error=str(exc)))
            return
        noteit_hk = self.noteit_hotkey.text().strip()
        if noteit_hk:
            try:
                Hotkey.parse(noteit_hk)
            except ValueError as exc:
                self.hotkey_state.setText(f"NoteIT Hotkey invalid: {exc}")
                return
        default_lib = str(self.c.settings.library_dir) if not self.c.settings.get("library_dir") else None
        lib = self.library.text().strip()
        self.c.settings.update({
            "library_dir": "" if lib == default_lib else lib,
            "hotkey": self.hotkey.text().strip(),
            "noteit_hotkey": noteit_hk,
            "launcher_enabled": self.launcher_enabled.isChecked(),
            "language": self.language.currentData(),
            "theme": self.theme.currentData(),
            "start_with_windows": self.autostart.isChecked(),
            "insert_mode": self.insert_mode.currentData(),
            "insert_base_font": self.base_font.currentData(),
            "insert_images": self.images.currentData(),
            "office_com_paste": self.office_com.isChecked(),
            "restore_clipboard": self.restore_clip.isChecked(),
            "paste_delay_ms": self.paste_delay.value(),
            "restore_delay_ms": self.restore_delay.value(),
            "picker_show_preview": self.preview.isChecked(),
            "picker_sort": self.sort.currentData(),
            "stats_keep_days": self.stats_days.value(),
            "picker_width": self.pw.value(),
            "picker_height": self.ph.value(),
            "editor_font_family": self.ed_font.currentFont().family(),
            "editor_font_size": self.ed_size.value(),
            "code_font_family": self.code_font.currentFont().family(),
            "code_font_size": self.code_size.value(),
            "code_style": self.code_style.currentText(),
            "code_background": self.code_bg.text().strip(),
            "date_format": self.date_fmt.text().strip(),
            "time_format": self.time_fmt.text().strip(),
        })
        self.accept()
