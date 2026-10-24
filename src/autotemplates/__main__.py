"""Command line.

    python -m autotemplates [gui] [--autostart]     start (or show the running app)
    python -m autotemplates action <id> [--no-start] picker | new | new_clipboard | editor |
                                                     settings | folder | reload | backup | help | quit
    python -m autotemplates setup [--start-menu] [--autostart on|off] [--remove]
    python -m autotemplates version
    python -m autotemplates --self-test
"""

from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Sequence

from autotemplates import __version__

log = logging.getLogger("autotemplates")


def _setup_logging(paths) -> None:
    handler = RotatingFileHandler(paths.log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def run_gui(args: list[str]) -> int:
    started = time.perf_counter()
    from autotemplates.core.paths import AppPaths
    from autotemplates.instance import InstanceServer, action_message, send

    paths = AppPaths.default().ensure()
    command = {"cmd": "ping"} if "--autostart" in args else action_message("editor")
    if send(paths.data_dir, command) is not None:
        return 0  # already running: it shows its editor
    _setup_logging(paths)

    from PySide6.QtWidgets import QApplication

    from autotemplates.core.settings import Settings
    from autotemplates.platform import devpilot
    from autotemplates.platform.autostart import Autostart, set_app_user_model_id
    from autotemplates.ui import theme
    from autotemplates.ui.app import Controller

    set_app_user_model_id()  # own taskbar button and icon, separate from other pythonw apps
    qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    qt_app.setApplicationName("AutoTemplates")
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setWindowIcon(theme.app_icon())

    settings = Settings(paths.settings_file)
    controller = Controller(qt_app, paths, settings)
    server = InstanceServer(paths.data_dir, controller.accept_remote)
    if not server.start():
        send(paths.data_dir, command)
        return 0
    qt_app.aboutToQuit.connect(server.stop)
    qt_app.aboutToQuit.connect(controller.shutdown)

    if devpilot.owns("autostart"):
        log.info("Started by DevPilot: it owns 'start with Windows'")
    else:
        try:
            Autostart().sync(bool(settings.get("start_with_windows")))
        except OSError:
            log.exception("Could not update the autostart entry")

    controller.start()
    pending = args[args.index("--action") + 1] if "--action" in args and args.index("--action") + 1 < len(args) else None
    if pending:
        controller.run_action({"action": pending})
    elif "--autostart" not in args and not devpilot.managed():
        controller.show_editor()
    log.info("AutoTemplates %s ready in %.0f ms (DevPilot: %s)", __version__, (time.perf_counter() - started) * 1000,
             ",".join(sorted(devpilot.suppressed())) or "no")
    return qt_app.exec()


def run_action(action: str, args: list[str]) -> int:
    from autotemplates.core.paths import AppPaths
    from autotemplates.instance import action_message, send

    paths = AppPaths.default().ensure()
    reply = send(paths.data_dir, action_message(action))
    if reply is not None:
        return 0 if reply.get("ok") else 1
    if "--no-start" in args or action == "quit":
        return 0
    return run_gui(["--action", action])


def setup(args: list[str]) -> int:
    from pathlib import Path

    from autotemplates.core.paths import AppPaths
    from autotemplates.platform.autostart import SHORTCUT_NAME, Autostart, create_shortcut, start_menu_dir

    paths = AppPaths.default().ensure()
    if "--remove" in args:
        link = start_menu_dir() / SHORTCUT_NAME
        if link.exists():
            link.unlink()
            print(f"Removed {link}")
        Autostart().set_enabled(False)
        return 0
    if "--start-menu" in args:
        from PySide6.QtGui import QGuiApplication

        from autotemplates.ui.theme import app_icon_pixmap

        app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        icon = paths.data_dir / "autotemplates.ico"
        app_icon_pixmap(256).scaled(64, 64).toImage().save(str(icon), "ICO")
        link = create_shortcut(start_menu_dir() / SHORTCUT_NAME, Path(icon))
        print(f"Start menu shortcut: {link}")
        del app
    if "--autostart" in args:
        value = args[args.index("--autostart") + 1] if args.index("--autostart") + 1 < len(args) else "on"
        from autotemplates.core.settings import Settings

        enabled = value.lower() in ("on", "1", "true", "yes")
        Settings(paths.settings_file).set("start_with_windows", enabled)
        Autostart().set_enabled(enabled)
        print(f"Start with Windows: {'on' if enabled else 'off'}")
    return 0


def self_test() -> int:
    """Headless check: library scan, rendering, picker and editor construction."""
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["AUTOTEMPLATES_HOME"] = tmp
        from PySide6.QtWidgets import QApplication

        from autotemplates.core.paths import AppPaths
        from autotemplates.core.settings import Settings
        from autotemplates.ui.app import Controller

        app = QApplication.instance() or QApplication([])
        paths = AppPaths(Path(tmp)).ensure()
        controller = Controller(app, paths, Settings(paths.settings_file))
        controller._ensure_library()
        controller.rescan(sync=True)
        ok = len(controller.library.templates) >= 5
        for tpl in controller.library.templates:
            ok = ok and bool(controller.renderer.render(tpl, controller.library.root).html)
        controller.picker.popup(None)
        controller.picker.hide()
        controller.editor.open_template(controller.library.templates[0].rel)
        controller.editor.close()
        controller.shutdown()
        print("self-test", "ok" if ok else "FAILED", f"({len(controller.library.templates)} templates)")
        return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return self_test()
    if args and args[0] in ("version", "--version"):
        print(f"AutoTemplates {__version__}")
        return 0
    if args and args[0] == "action":
        if len(args) < 2:
            print(__doc__)
            return 2
        return run_action(args[1], args[2:])
    if args and args[0] == "setup":
        return setup(args[1:])
    if args and args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    return run_gui(args[1:] if args and args[0] == "gui" else args)


if __name__ == "__main__":
    raise SystemExit(main())