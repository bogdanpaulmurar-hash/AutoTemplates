"""Application controller: hotkey, tray, picker, editor, library watching, forwarded commands."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMenu,
                               QSystemTrayIcon)

from autotemplates import __version__, i18n
from autotemplates.core import backup as bk
from autotemplates.core import variables as tv
from autotemplates.core.library import Library
from autotemplates.core.paths import AppPaths
from autotemplates.core.settings import Settings
from autotemplates.i18n import t
from autotemplates.platform import devpilot, win32
from autotemplates.platform.hotkey import Hotkey, HotkeyListener
from autotemplates.ui import theme
from autotemplates.ui.content import Renderer
from autotemplates.ui.inserter import Inserter

log = logging.getLogger(__name__)

ACTIONS = ("picker", "new", "new_clipboard", "editor", "settings", "folder", "reload", "quit", "show", "noteit", "backup")


def caret_to_logical(x: int, y: int) -> QPoint:
    """Win32 physical pixels → Qt logical coordinates (per-monitor DPI)."""
    for screen in QGuiApplication.screens():
        g, dpr = screen.geometry(), screen.devicePixelRatio()
        if g.x() <= x < g.x() + g.width() * dpr and g.y() <= y < g.y() + g.height() * dpr:
            return QPoint(int(g.x() + (x - g.x()) / dpr), int(g.y() + (y - g.y()) / dpr))
    return QPoint(x, y)


class InputDialog(QDialog):
    """Asks for the ``{input:…}`` values of a template before it is inserted."""

    def __init__(self, title: str, labels: list[str]) -> None:
        super().__init__(None)
        from PySide6.QtCore import Qt

        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setWindowTitle(title)
        self.setWindowIcon(theme.app_icon())
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.fields: dict[str, QLineEdit] = {}
        for label in labels:
            edit = QLineEdit()
            form.addRow(QLabel(label), edit)
            self.fields[label] = edit
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("input.insert"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def answers(self) -> dict[str, str]:
        return {k: v.text() for k, v in self.fields.items()}


class Controller(QObject):
    hotkey_fired = Signal(int, object)  # target hwnd, caret (x, y, h) or None
    remote_action = Signal(dict)
    scanned = Signal(bool)
    backup_finished = Signal(str, str, bool)  # zip path ("" on failure), error, automatic

    def __init__(self, qt_app: QApplication, paths: AppPaths, settings: Settings) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.paths = paths
        self.settings = settings
        i18n.set_language(settings.get("language"))
        self.library = Library(settings.library_dir, paths.index_file, paths.usage_file)
        self.renderer = Renderer(settings, paths.data_dir / "cache")
        self.inserter = Inserter(settings, self)
        self.tray: QSystemTrayIcon | None = None
        self._picker = None
        self._launcher = None
        self._noteit = None
        self._editor = None
        self._help = None
        self._target = 0
        self._launch_origin: tuple[int, object] = (0, None)
        self._hotkey_ok = False
        self._scan_lock = threading.Lock()
        self._backup_lock = threading.Lock()
        self._auto_backup_warned = False

        self.hotkey_fired.connect(self._on_hotkey)
        self.remote_action.connect(self.run_action)
        self.scanned.connect(self._after_scan)
        self.backup_finished.connect(self._after_backup)
        self._backup_timer = QTimer(self, interval=60 * 60 * 1000)  # daily mode: also checked every hour
        self._backup_timer.timeout.connect(lambda: self.check_auto_backup(startup=False))
        self.listener = HotkeyListener(self._hotkey_thread)
        self.watcher = QFileSystemWatcher(self)
        self._rescan_timer = QTimer(self, singleShot=True, interval=500)
        self._rescan_timer.timeout.connect(self.rescan)
        self.watcher.directoryChanged.connect(lambda _: self._rescan_timer.start())
        settings.add_listener(self._setting_changed)

    # ================================================================ start / stop
    def start(self) -> None:
        theme.apply_theme(self.qt_app, self.settings.get("theme"))
        self.register_hotkey()
        self._ensure_library()
        self.rescan()
        if not devpilot.owns("tray"):
            self._create_tray()
        else:
            log.info("Started by DevPilot: no tray icon (DevPilot shows AutoTemplates' actions)")
        QTimer.singleShot(300, lambda: self.picker)  # build the list while idle: first Ctrl+Q is instant
        QTimer.singleShot(8000, lambda: self.check_auto_backup(startup=True))  # after the start-up work
        self._backup_timer.start()

    def shutdown(self) -> None:
        self.listener.stop()
        if self.tray:
            self.tray.hide()

    def _ensure_library(self) -> None:
        root = self.library.root
        if root.exists():
            return
        try:
            from autotemplates.samples import create_samples

            root.mkdir(parents=True, exist_ok=True)
            create_samples(root, self.settings.get("language"), self.settings.get("hotkey"))
        except OSError:
            log.exception("Could not create the library folder %s", root)

    # ================================================================ hotkey
    def register_hotkey(self) -> bool:
        hotkeys: dict[str, tuple[Hotkey, any]] = {}
        try:
            hk_picker = Hotkey.parse(self.settings.get("hotkey"))
        except ValueError:
            log.warning("Invalid hotkey %r; using Ctrl+Q", self.settings.get("hotkey"))
            hk_picker = Hotkey.parse("Ctrl+Q")
        hotkeys["picker"] = (hk_picker, self._hotkey_thread)

        noteit_hk_str = str(self.settings.get("noteit_hotkey") or "").strip()
        if noteit_hk_str:
            try:
                hk_note = Hotkey.parse(noteit_hk_str)
                hotkeys["noteit"] = (hk_note, lambda: self.remote_action.emit({"action": "noteit"}))
            except ValueError:
                log.warning("Invalid noteit hotkey %r", noteit_hk_str)

        results = self.listener.register_map(hotkeys)
        self._hotkey_ok = results.get("picker", False)
        if not self._hotkey_ok and self.listener.supported:
            self.notify(t("tray.hotkey_busy", hotkey=hk_picker.text))
        return self._hotkey_ok

    def hotkey_status(self) -> str:
        if not self.listener.supported:
            return t("settings.hotkey_unsupported")
        return t("settings.hotkey_ok") if self._hotkey_ok else t("settings.hotkey_busy")

    def _hotkey_thread(self) -> None:
        hwnd = win32.foreground_window()  # read immediately, before anything changes the focus
        self.hotkey_fired.emit(hwnd, win32.caret_position(hwnd))

    def _on_hotkey(self, hwnd: int, caret) -> None:
        if self._launcher is not None and self._launcher.isVisible():
            self._launcher.hide()
            return
        if self._picker is not None and self._picker.isVisible():
            self._picker.hide()
            return

        own_picker = self._picker is not None and hwnd == int(self._picker.winId())
        self._target = hwnd if hwnd and not own_picker and win32.can_receive(hwnd) else 0
        # Remember where the hotkey was pressed: once the launcher has the focus,
        # the foreground window is the launcher itself, not the target app.
        self._launch_origin = (hwnd, caret)

        anchor = caret_to_logical(caret[0], caret[1]) if caret else QCursor.pos()
        if self.settings.get("launcher_enabled", True):
            self.show_launcher(anchor)
        else:
            self.show_picker(hwnd, caret)

    @property
    def launcher(self):
        if self._launcher is None:
            from autotemplates.ui.launcher import QuickLauncher

            self._launcher = QuickLauncher(self)
            self._launcher.noteit_selected.connect(lambda: self.show_noteit())
            self._launcher.templates_selected.connect(lambda: self.show_picker(*self._launch_origin))
        return self._launcher

    def show_launcher(self, anchor: QPoint | None = None) -> None:
        if self._picker is not None and self._picker.isVisible():
            self._picker.hide()
        self.launcher.popup(anchor)
        win32.focus_window(int(self.launcher.winId()))

    @property
    def noteit(self):
        if self._noteit is None:
            from autotemplates.ui.noteit import NoteITWindow

            self._noteit = NoteITWindow(self)
        return self._noteit

    def show_noteit(self, title: str = "", content_html: str = "") -> None:
        if self._launcher is not None and self._launcher.isVisible():
            self._launcher.hide()
        if self._picker is not None and self._picker.isVisible():
            self._picker.hide()
        ni = self.noteit
        if title or content_html:
            if not ni.is_empty() and not ni._finished:
                ni._store_last()  # do not lose the current draft: "Last note" brings it back
            ni.reset_form(title, content_html)
        elif not ni.isVisible():
            ni.prepare_to_show()
        ni.show_and_raise()
        try:
            win32.focus_window(int(ni.winId()))
        except Exception:
            pass

    # ================================================================ picker / insert
    @property
    def picker(self):
        if self._picker is None:
            from autotemplates.ui.picker import Picker

            p = Picker(self)
            p.insert_requested.connect(self.insert_template)
            p.copy_requested.connect(lambda rel, shift: self.copy_template(rel, plain=self._plain(rel, shift)))
            p.edit_requested.connect(self.edit_template)
            p.new_requested.connect(lambda: self.editor.new_template("rich"))
            p.noteit_requested.connect(self.show_noteit)
            p.editor_requested.connect(self.show_editor)
            p.settings_requested.connect(self.show_settings)
            p.help_requested.connect(lambda: self.show_help("picker"))
            p.favourite_toggled.connect(lambda rel: self.library.usage.set_favourite(rel, not self.library.usage.favourite(rel)))
            self._picker = p
        return self._picker

    def show_picker(self, hwnd: int | None = None, caret=None) -> None:
        if self._launcher is not None and self._launcher.isVisible():
            self._launcher.hide()
        if hwnd is None:
            hwnd = win32.foreground_window()
            caret = win32.caret_position(hwnd)
        own_picker = self._picker is not None and hwnd == int(self._picker.winId())
        self._target = hwnd if hwnd and not own_picker and win32.can_receive(hwnd) else 0
        anchor = caret_to_logical(caret[0], caret[1]) if caret else QCursor.pos()
        self.picker.popup(anchor)
        win32.focus_window(int(self.picker.winId()))  # Windows may refuse a plain activateWindow()

    def _plain(self, rel: str, shift: bool) -> bool:
        tpl = self.library.get(rel)
        base = (tpl.mode if tpl and tpl.mode else "") or self.settings.get("insert_mode")
        return (base == "plain") != shift

    def _answers(self, rendered, name: str) -> dict[str, str] | None:
        if not rendered.variables:
            return {}
        labels = tv.input_prompts(rendered.text + rendered.html)
        if not labels:
            return {}
        dlg = InputDialog(name, labels)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg.answers() if dlg.exec() else None

    def insert_template(self, rel: str, shift: bool = False) -> None:
        tpl = self.library.get(rel)
        if tpl is None:
            return
        if not self._target and win32.IS_WINDOWS:  # opened from the tray/DevPilot: nowhere to paste
            self.copy_template(rel, plain=self._plain(rel, shift))
            return
        rendered = self.renderer.render(tpl, self.library.root)
        answers = self._answers(rendered, tpl.name)
        if answers is None:
            return
        self.inserter.insert(rendered, self._target, plain=self._plain(rel, shift), answers=answers)
        self.library.usage.used(rel)

    def copy_template(self, rel: str, plain: bool = False) -> None:
        tpl = self.library.get(rel)
        if tpl is None:
            return
        rendered = self.renderer.render(tpl, self.library.root)
        answers = self._answers(rendered, tpl.name)
        if answers is None:
            return
        self.inserter.copy_only(rendered, plain=plain, answers=answers)
        self.library.usage.used(rel)
        self.notify(t("tray.copied", name=tpl.name))

    # ================================================================ editor / settings
    @property
    def editor(self):
        if self._editor is None:
            from autotemplates.ui.editor import EditorWindow

            self._editor = EditorWindow(self)
        return self._editor

    def show_editor(self) -> None:
        self.editor.show_and_raise()

    def edit_template(self, rel: str) -> None:
        ed = self.editor
        ed.show_and_raise()
        if ed.maybe_save():
            ed.open_template(rel)

    def show_help(self, section: str | None = None, parent=None) -> None:
        """Open the user guide on a section (core/guide.py ids); F1 in every window ends up here."""
        from autotemplates.ui.help_window import HelpWindow

        if self._launcher is not None and self._launcher.isVisible():
            self._launcher.hide()
        if self._picker is not None and self._picker.isVisible():
            self._picker.hide()
        host = parent or QApplication.activeModalWidget()
        if host is not None:
            # A modal dialog (Settings) blocks every other window: give it a guide window of its own.
            win = HelpWindow(self, host)
            win.setAttribute(Qt.WA_DeleteOnClose)
            win.open_section(section)
            return
        if self._help is None:
            self._help = HelpWindow(self)
        # NoteIT may stay on top: the guide opened from it must not end up hidden behind it.
        on_top = self._noteit is not None and self._noteit.isVisible() and \
            bool(self._noteit.windowFlags() & Qt.WindowStaysOnTopHint)
        if bool(self._help.windowFlags() & Qt.WindowStaysOnTopHint) != on_top:
            self._help.setWindowFlag(Qt.WindowStaysOnTopHint, on_top)
        self._help.open_section(section)
        try:
            win32.focus_window(int(self._help.winId()))
        except Exception:
            pass

    def show_settings(self) -> None:
        from autotemplates.ui.settings_dialog import SettingsDialog

        parent = self._editor if self._editor is not None and self._editor.isVisible() else None
        dlg = SettingsDialog(self, parent)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.exec()

    def _setting_changed(self, key: str, value) -> None:
        if key in ("hotkey", "noteit_hotkey"):
            self.register_hotkey()
        elif key == "theme":
            theme.apply_theme(self.qt_app, value)
            if self._editor:
                self._editor.apply_settings()
        elif key == "language":
            i18n.set_language(value)
            self.notify(t("tray.restart_language"))
        elif key == "library_dir":
            self.library.set_root(self.settings.library_dir)
            self._ensure_library()
            self.rescan()
        elif key in ("editor_font_family", "editor_font_size", "code_font_family", "code_font_size") and self._editor:
            self._editor.apply_settings()
        elif key.startswith("code_"):
            self.renderer.clear()
        elif key == "start_with_windows" and not devpilot.owns("autostart"):
            from autotemplates.platform.autostart import Autostart

            try:
                Autostart().set_enabled(bool(value))
            except OSError:
                log.exception("Could not update the autostart entry")

    # ================================================================ library
    def rescan(self, sync: bool = False) -> None:
        def work() -> None:
            if not self._scan_lock.acquire(blocking=False):
                return
            try:
                changed = self.library.scan()
            except Exception:  # noqa: BLE001
                log.exception("Library scan failed")
                changed = False
            finally:
                self._scan_lock.release()
            self.scanned.emit(changed)

        if sync:
            with self._scan_lock:
                changed = self.library.scan()
            self._after_scan(changed)
        else:
            threading.Thread(target=work, name="scan", daemon=True).start()

    @contextmanager
    def library_operation(self):
        """Editor move/rename/delete: no rescans while files move, one rescan afterwards."""
        self._rescan_timer.stop()
        self.watcher.blockSignals(True)
        self._scan_lock.acquire()  # waits for a scan already running
        try:
            yield
        finally:
            self._scan_lock.release()
            self.watcher.blockSignals(False)
            self.rescan()
            self.library_changed()

    def _after_scan(self, changed: bool) -> None:
        try:
            self.library.usage.purge((t.rel for t in self.library.templates), self.settings.get("stats_keep_days"))
        except Exception:  # noqa: BLE001
            log.exception("Could not purge old statistics")
        folders = [str(p) for p in self.library.folders()]
        old = set(self.watcher.directories())
        if old != set(folders):
            if old:
                self.watcher.removePaths(list(old))
            if folders:
                self.watcher.addPaths([f for f in folders if Path(f).is_dir()])
        if changed:
            self.library_changed()

    def library_changed(self) -> None:
        self.renderer.clear()
        if self._picker is not None:
            self._picker.reload_categories()
            if self._picker.isVisible():
                self._picker.refresh()
        if self._editor is not None and self._editor.isVisible():
            self._editor.reload_tree()

    def open_library_folder(self) -> None:
        self.library.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.root)))

    def reveal(self, path: Path) -> None:
        import subprocess
        import sys

        if sys.platform == "win32" and path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603,S607
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    # ================================================================ backup
    def backup_source(self) -> bk.BackupSource:
        return bk.BackupSource(self.paths.data_dir, self.library.root)

    def _flush_noteit(self) -> None:
        """The NoteIT draft on disk must be current before it is backed up."""
        if self._noteit is not None:
            try:
                self._noteit._write_draft()
            except Exception:  # noqa: BLE001
                log.exception("Could not save the NoteIT draft before the backup")

    def check_auto_backup(self, startup: bool) -> None:
        mode = self.settings.get("backup_auto")
        if bk.is_due(mode, float(self.settings.get("backup_last") or 0), startup=startup):
            self.backup_now(automatic=True)

    def backup_now(self, *, folder: Path | None = None, include_templates: bool | None = None,
                   keep: int | None = None, automatic: bool = False) -> bool:
        """Writes a backup in the background; False when one is already running."""
        if not self._backup_lock.acquire(blocking=False):
            return False
        self._flush_noteit()
        dest = Path(folder) if folder else self.settings.backup_dir
        include = self.settings.get("backup_include_templates") if include_templates is None else include_templates
        keep = int(self.settings.get("backup_keep") if keep is None else keep)
        src = self.backup_source()

        def work() -> None:
            try:
                path = bk.create_backup(src, dest, include_templates=bool(include))
                bk.rotate(dest, keep)
                self.backup_finished.emit(str(path), "", automatic)
            except Exception as exc:  # noqa: BLE001
                log.exception("Backup failed (%s)", dest)
                self.backup_finished.emit("", str(exc), automatic)
            finally:
                self._backup_lock.release()

        if not automatic:
            self.notify(t("backup.running"))
        threading.Thread(target=work, name="backup", daemon=True).start()
        return True

    def _after_backup(self, path: str, error: str, automatic: bool) -> None:
        if path:
            self.settings.set("backup_last", time.time())
            self._auto_backup_warned = False
            if not automatic:
                self.notify(t("backup.done", name=Path(path).name))
        elif not automatic or not self._auto_backup_warned:
            self._auto_backup_warned = automatic
            self.notify(t("backup.failed", error=error))

    def restore_backup(self, info: bk.BackupInfo, options: bk.RestoreOptions) -> tuple[bk.RestoreResult, Path]:
        """Safety backup of the current state first, then the restore. Raises BackupError/OSError."""
        with self._backup_lock:  # waits for a backup that is running
            return self._restore_locked(info, options)

    def _restore_locked(self, info: bk.BackupInfo, options: bk.RestoreOptions) -> tuple[bk.RestoreResult, Path]:
        self._flush_noteit()
        src = self.backup_source()
        try:
            safety = bk.create_backup(src, self.settings.backup_dir, include_templates=options.templates,
                                      tag=bk.SAFETY_TAG)
        except OSError:
            log.warning("Backup folder not writable; safety backup goes to the data folder")
            safety = bk.create_backup(src, self.paths.data_dir / "backups", include_templates=options.templates,
                                      tag=bk.SAFETY_TAG)
        with self.library_operation():
            result = bk.restore_backup(info, options, settings=self.settings, usage=self.library.usage,
                                       noteit_dir=self.paths.noteit_dir, cache_dir=self.paths.cache_dir)
        if self._noteit is not None and result.noteit:
            self._noteit._finished = False
            self._noteit._load_draft()
        log.info("Backup restored from %s (safety copy %s)", info.path, safety)
        return result, safety

    # ================================================================ tray / commands
    def _create_tray(self) -> None:
        tray = QSystemTrayIcon(theme.app_icon(), self)
        tray.setToolTip(f"AutoTemplates {__version__}\n{t('tray.tooltip', hotkey=self.settings.get('hotkey'))}")
        menu = QMenu()
        for label, icon, action in (("tray.insert", "insert", "picker"), ("tray.noteit", "note", "noteit"), ("tray.new", "new", "new"),
                                    ("tray.new_clipboard", "copy", "new_clipboard"), ("tray.editor", "edit", "editor"),
                                    (None, None, None), ("tray.folder", "folder", "folder"),
                                    ("tray.reload", "refresh", "reload"), ("tray.backup", "save", "backup"),
                                    ("tray.settings", "settings", "settings"), ("tray.help", "help", "help"),
                                    (None, None, None), ("tray.quit", "delete", "quit")):
            if label is None:
                menu.addSeparator()
                continue
            text = t(label) + (f"\t{self.settings.get('hotkey')}" if action == "picker" else "")
            a = QAction(theme.glyph_icon(icon), text, menu)
            a.triggered.connect(lambda _=False, act=action: self.run_action({"action": act}))
            menu.addAction(a)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self.show_editor() if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger) else None)
        tray.show()
        self.tray = tray
        self._tray_menu = menu

    def notify(self, message: str) -> None:
        log.info(message)
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage("AutoTemplates", message, theme.app_icon(), 2500)

    def accept_remote(self, message: dict) -> dict:
        """Runs on the instance-server thread: hand over to the UI thread."""
        if message.get("cmd") != "action" or message.get("action") not in ACTIONS:
            return {"ok": False, "error": "unknown action"}
        message = dict(message)
        if message.get("action") == "picker":
            hwnd = win32.foreground_window()
            message["hwnd"], message["caret"] = hwnd, win32.caret_position(hwnd)
        self.remote_action.emit(message)
        return {"ok": True}

    def run_action(self, message: dict) -> None:
        action = message.get("action")
        if action == "picker":
            self.show_picker(message.get("hwnd"), message.get("caret"))
        elif action == "noteit":
            self.show_noteit()
        elif action == "new":
            self.editor.new_template("rich")
        elif action == "new_clipboard":
            self.editor.new_from_clipboard()
            self.editor.show_and_raise()
        elif action in ("editor", "show"):
            self.show_editor()
        elif action == "settings":
            self.show_settings()
        elif action == "folder":
            self.open_library_folder()
        elif action == "reload":
            self.rescan()
        elif action == "backup":
            self.backup_now()
        elif action == "help":
            self.show_help(message.get("section"))
        elif action == "quit":
            if self._editor is None or self._editor.maybe_save():
                self.qt_app.quit()
