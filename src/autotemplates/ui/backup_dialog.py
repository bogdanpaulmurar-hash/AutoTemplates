"""Restore preview: what the backup holds, what would be overwritten, and the choices."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QLabel,
                               QVBoxLayout, QWidget)

from autotemplates.core.backup import USAGE_MERGE, USAGE_REPLACE, BackupInfo, RestoreOptions
from autotemplates.i18n import t


def _same_folder(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class RestoreDialog(QDialog):
    def __init__(self, controller, info: BackupInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.c = controller
        self.info = info
        self._other_dir = ""
        self.setWindowTitle(t("restore.title"))
        self.resize(560, 0)
        lay = QVBoxLayout(self)

        head = QLabel(t("restore.header", name=info.path.name, created=info.created.replace("T", " "),
                        computer=info.computer or "?", version=info.app_version or "?"))
        head.setWordWrap(True)
        lay.addWidget(head)

        current_settings = controller.settings.as_dict()
        changes = info.settings_changes(current_settings)
        self.cb_settings = QCheckBox(t("restore.settings", count=len(changes)))
        self.cb_settings.setChecked(bool(info.settings))
        self.cb_settings.setEnabled(bool(info.settings))
        lay.addWidget(self.cb_settings)
        hint = QLabel(t("restore.settings_tip", keys=", ".join(changes) or "—"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.cb_usage = QCheckBox(t("restore.usage", count=len(info.usage)))
        self.cb_usage.setChecked(bool(info.usage))
        self.cb_usage.setEnabled(bool(info.usage))
        lay.addWidget(self.cb_usage)
        self.usage_mode = QComboBox()
        self.usage_mode.addItem(t("restore.usage_merge"), USAGE_MERGE)
        self.usage_mode.addItem(t("restore.usage_replace"), USAGE_REPLACE)
        self.usage_mode.setEnabled(bool(info.usage))
        self.cb_usage.toggled.connect(self.usage_mode.setEnabled)
        lay.addWidget(self.usage_mode)

        names = ", ".join(t(f"restore.noteit_{n}") for n in info.noteit) or "—"
        self.cb_noteit = QCheckBox(t("restore.noteit", names=names))
        self.cb_noteit.setChecked(bool(info.noteit))
        self.cb_noteit.setEnabled(bool(info.noteit))
        lay.addWidget(self.cb_noteit)

        self.cb_templates = QCheckBox()
        self.cb_templates.setEnabled(bool(info.template_files))
        self.cb_templates.setChecked(False)
        lay.addWidget(self.cb_templates)

        # Library path: only asked when the backup comes from another folder.
        self.library_box = None
        self.library_choice = None
        current_lib = str(controller.library.root)
        if info.library_dir and not _same_folder(info.library_dir, current_lib):
            self.library_box = QGroupBox(t("restore.library"))
            bl = QVBoxLayout(self.library_box)
            msg = QLabel(t("restore.library_differs", backup=info.library_dir, current=current_lib))
            msg.setWordWrap(True)
            bl.addWidget(msg)
            self.library_choice = QComboBox()
            self.library_choice.addItem(t("restore.library_keep"), "keep")
            exists = Path(info.library_dir).is_dir()
            self.library_choice.addItem(t("restore.library_backup" if exists else "restore.library_backup_missing"),
                                        "backup")
            if not exists:
                self.library_choice.model().item(1).setEnabled(False)
            self.library_choice.addItem(t("restore.library_other"), "other")
            self.library_choice.activated.connect(self._library_chosen)
            bl.addWidget(self.library_choice)
            lay.addWidget(self.library_box)

        safety = QLabel(t("restore.safety"))
        safety.setObjectName("Hint")
        safety.setWordWrap(True)
        lay.addWidget(safety)

        self.error = QLabel("")
        self.error.setObjectName("Hint")
        lay.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("restore.button"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._update_templates()

    # ---------------------------------------------------------------- library
    def target_library(self) -> str | None:
        """None = keep the current library; else the folder to switch to."""
        if self.library_choice is None:
            return None
        choice = self.library_choice.currentData()
        if choice == "backup":
            return self.info.library_dir
        if choice == "other" and self._other_dir:
            return self._other_dir
        return None

    def _library_chosen(self, _index: int) -> None:
        if self.library_choice.currentData() == "other":
            folder = QFileDialog.getExistingDirectory(self, t("restore.library_other"), str(self.c.library.root))
            if folder:
                self._other_dir = folder
                self.library_choice.setItemText(2, folder)
            else:
                self.library_choice.setCurrentIndex(0)
        self._update_templates()

    def _update_templates(self) -> None:
        if not self.info.template_files:
            self.cb_templates.setText(t("restore.templates_none"))
            return
        root = Path(self.target_library() or self.c.library.root)
        plan = self.info.plan_templates(root)
        self.cb_templates.setText(t("restore.templates", new=len(plan.new), same=len(plan.identical),
                                    diff=len(plan.different)))

    # ---------------------------------------------------------------- result
    def options(self) -> RestoreOptions:
        return RestoreOptions(
            settings=self.cb_settings.isChecked(),
            usage=self.cb_usage.isChecked(),
            usage_mode=self.usage_mode.currentData(),
            noteit=self.cb_noteit.isChecked(),
            templates=self.cb_templates.isChecked(),
            library_dir=self.target_library(),
        )

    def _accept(self) -> None:
        o = self.options()
        if not (o.settings or o.usage or o.noteit or o.templates or o.library_dir is not None):
            self.error.setText(t("restore.nothing"))
            return
        self.accept()
