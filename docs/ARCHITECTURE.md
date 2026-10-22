# Architecture

```
src/autotemplates/
  __main__.py          CLI: gui, action <id>, setup, version, --self-test
  instance.py          single instance + forwarded commands (authenticated named pipe, stdlib only)
  i18n.py              RO / EN texts
  samples.py           example templates for an empty library
  core/                Qt-free, unit-tested
    paths.py           %LOCALAPPDATA%\AutoTemplates (settings, index, usage, logs)
    settings.py        JSON settings with defaults and change listeners
    library.py         folder scan, cached index, search/ranking, usage + favourites
    formats.py         file kinds, docx → HTML, rtf → text, HTML → text, <meta> metadata
    variables.py       {date} {time} {clipboard} {input:…} {cursor} …
    highlight.py       language detection + inline-styled Pygments HTML
  platform/
    hotkey.py          RegisterHotKey on its own thread; "Ctrl+Q" parsing
    win32.py           foreground window, caret position, focus, SendInput (Ctrl+V, ←)
    autostart.py       HKCU Run entry, Start-menu shortcut, AppUserModelID
    devpilot.py        DEVPILOT_MANAGED / DEVPILOT_SUPPRESS
  ui/
    app.py             Controller: tray, hotkey → picker → insert, watcher, actions
    picker.py          the Ctrl+Q list (built once, then shown/hidden)
    content.py         template → (HTML, text, image) with a small render cache
    inserter.py        clipboard backup → HTML+text → focus target → Ctrl+V → restore
    editor.py          library tree + editors (rich / code / read-only)
    richedit.py        QTextEdit commands, pasted pictures, saving pictures to <name>.assets
    codeedit.py        QPlainTextEdit + Pygments highlighter
    settings_dialog.py
    theme.py           dark/light QSS, icon-font glyphs, app icon drawn in code
```

## Insertion flow

1. The hotkey thread receives `WM_HOTKEY` and immediately records the foreground window and its caret
   position (`GetGUIThreadInfo`), then signals the UI thread.
2. The picker (already built) is positioned under the caret (or the mouse) and activated.
3. Enter: the template is rendered (cached by path + mtime), `{input:…}` values are asked in one small form, the other
   variables are expanded.
4. The current clipboard is copied (all formats, up to 64 MB), the template is put on the clipboard as HTML **and**
   plain text (plus the bitmap for picture templates), the target window gets the focus back, held modifiers are
   released (so Shift+Enter does not become Ctrl+Shift+V), and Ctrl+V is sent with `SendInput`.
5. `{cursor}` sends ← as many times as there are characters after the marker.
6. After `restore_delay_ms` the old clipboard is put back.

Pictures in HTML are absolute `file:///` URLs at insertion time: Word, Outlook and Teams load them while pasting.

## Performance

- The picker is created 300 ms after start-up while idle and is reused; opening it only filters a list in memory.
- The index (`index.json`) keeps name, category, tags, preview and search text; on start only new/changed files
  (size + mtime) are read. Scans run on a background thread; a `QFileSystemWatcher` triggers a debounced rescan.
- Pygments and the docx reader are imported only when needed; rendered templates are cached (40 entries).
- Measured (Linux test machine, 1 000 text templates): first scan 280 ms, cached rescan 55 ms, search 1–5 ms per keystroke.

## Storage format of editor templates

`Category/Name.html` is the HTML written by Qt plus `<meta name="autotemplates:tags|abbreviation|description|mode">`
in the head. Pictures live in `Category/Name.assets/` and are referenced relatively, so the folder can be moved or
synced. Renaming a template renames its assets folder; unused pictures are deleted on save.

## Conventions

- Code, commits and technical docs in English; user-facing progress updates in Romanian; UI in RO + EN.
- No `.exe`; install with `Install.bat` (private venv, `pythonw`, tray, autostart).
- Behaviour is configured in Settings, not hard-coded.