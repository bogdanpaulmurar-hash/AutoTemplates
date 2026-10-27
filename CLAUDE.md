# AutoTemplates — notes for Claude

Reguli generale (v1.1; textul complet: repo `dev-framework`, GLOBAL_RULES.md):
- Răspunde în română, scurt; rezultatul primul; spune ce nu ai putut verifica.
- Lucrează în etape mici: citește doar ce trebuie (caută, apoi deschide porțiunea), scrie doar funcțiile modificate, plan de 3–5 rânduri înainte de schimbări mari.
- După fiecare etapă rulează testele proiectului și notează în CHANGELOG.md.
- Parolele și cheile stau în keyring sau variabile de mediu; documentația vizibilă omite numele angajatorului, e-mailurile de firmă, ID-urile și numerele interne.
- Aplicații Windows: Python cu `pythonw`, tray, fără `.exe`; respectă DevPilot (`DEVPILOT_MANAGED`, `DEVPILOT_SUPPRESS`).
- Git: GitHub e sursa de adevăr; un singur laptop o dată; commit și push înainte de schimbarea laptopului; lasă Drive să termine sincronizarea.

Small Windows tool that keeps the user's templates (formatted text, screenshots, coloured code, txt/docx/md/code files) and inserts them at the cursor in any app, on a global hotkey. Python + PySide6-Essentials + Pygments.

## Commands
- Dev install: `pip install -e .[dev]`
- Tests: `pytest` (on Linux: `QT_QPA_PLATFORM=offscreen pytest`)
- Run: `python -m autotemplates gui`; actions: `python -m autotemplates action picker|new|editor|settings|folder|reload|backup|help|quit`; `--self-test`; `version`
- User install: `Install.bat` → private venv in `%LOCALAPPDATA%\AutoTemplates\venv`, started with `pythonw`
- Design: `docs/ARCHITECTURE.md` — read it before structural changes

## Map (`src/autotemplates/`)
`core` (library, index, folder ops, variables, conversion incl. `docx_html`, clipboard HTML `clipboard_html`, NoteIT export, `backup`, `shortcuts`, `guide` — no Qt) · `ui` (picker, launcher, NoteIT, editor, settings, help window, tray) · `platform` (Win32: hotkey, caret position, paste, clipboard; `office.py` Outlook/OneNote COM) · `i18n.py` · `instance.py` (single instance + named pipe) · `samples.py`

## Rules
- No `.exe`: Python, `pythonw`, tray, start with Windows, own icon. Must not interfere with the other Python apps running in parallel.
- Hotkey via `RegisterHotKey`, never a keyboard hook/keylogger. Default Ctrl+Q collides with Outlook/Word/Excel; Ctrl+Alt+Q is the recommended alternative.
- The previous clipboard is always restored after pasting.
- Templates live in a user-chosen folder (may be in Google Drive): one file = one template, sub-folder = category. Index and stats stay in `%LOCALAPPDATA%`, never in the library (sync conflicts).
- Lazy loading for speed: Pygments and converters load on first use; library scan runs in the background.
- DevPilot: `devpilot.tool.json`; respect `DEVPILOT_MANAGED` / `DEVPILOT_SUPPRESS` (`tray`, `autostart`).
- UI in Romanian + English; code, comments, commits and technical docs in English; updates to the user in Romanian, short.
- Visible docs: never the employer's name, company e-mails, internal IDs or numbers.
- Tree operations never overwrite files and always update index + usage in the same step (`core/folders.py`).
- Office integration only through COM with a fallback (`OfficeUnavailable`); never send mail automatically.
- Clipboard HTML goes through `core/clipboard_html.py` (styles inline inside the fragment). Pictures are never recompressed or scaled.
- Backups (`core/backup.py`): restore never overwrites templates and never takes machine-specific settings (`LOCAL_KEYS`); bump `FORMAT_VERSION` when the zip layout changes.
- Shortcuts live in `core/shortcuts.py` and are listed in the in-app guide (`core/guide.py`, F1): a new shortcut, variable or setting the user should know about gets a line there too (`tests/test_guide.py` checks shortcuts and variables).
- Status 0.3.6: `--self-test` passes on Windows (it caught a picker crash the offscreen tests missed — run it after UI changes); hotkey, paste, clipboard, the Office COM calls, the COM paste, backup/restore, the grouped picker and the guide window not yet tested on Windows — verify there before building on them.

## Status and logs
- Open bugs and changes: `KNOWN_ISSUES.md`. History: `CHANGELOG.md` (if present). Test steps for unconfirmed versions: `TESTING.md`. Move an item from KNOWN_ISSUES to CHANGELOG once implemented and confirmed.

## Keep this file current
Update it in the same commit when: install/test/run commands change, a package is added/moved, the DevPilot integration changes, or a bug teaches a rule worth remembering. Not for ordinary features. Keep it under ~60 lines.
