# Changelog

## Unreleased
- OneNote fix: on installs where pywin32 late binding raises `AttributeError: OneNote.Application.GetHierarchy` (classic OneNote present, type library not registered) the app now talks to OneNote through a PowerShell COM bridge (`platform/office.py`, `-EncodedCommand`, no script file, so no execution-policy issue). pywin32 is probed once; error messages now include the exception type, and an empty hierarchy says so. Diagnosed on Windows; the bridge itself is tested only with fakes on Linux.
- Install.bat: stops with a clear message when `scripts\install.ps1` is missing (Drive not synced yet) and also catches negative exit codes, so it no longer prints "installed" after a failure.
- OneNote: the note can go into a section (new page) or under an existing page (new subpage): the dialog is now a notebook/section/page tree with a filter; the page is moved after the parent's subtree with `UpdateHierarchy` (`core/noteit_export.place_as_subpage`, `platform/office.py`). Fix: when OneNote COM is unavailable the app no longer opens the bare `onenote:` link (OneNote answered "We couldn't open that location"); the note is copied and the real reason is shown.
- NoteIT: Ctrl+Shift+D inserts date and time (formats from the settings); Ctrl+Shift+Enter copies as plain text and closes. Both are in the guide.
- Tests: 97 pass offscreen on Linux; COM/OneNote not tested on Windows.
- Editor: larger, clearer buttons. Toolbar icons 18 -> 22 px, tool buttons min 28 px with more padding, push buttons get more padding and a minimum height (`ui/theme.py`, `ui/editor.py`). Tests not run: PySide6/pytest are unavailable in the cloud environment; verify on Windows.
