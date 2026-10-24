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
    library.py         folder scan, cached index, search/ranking, usage + favourites (+ retention of deleted)
    grouping.py        picker groups: ★ Favourites, Recent, one per folder (order rules for browsing vs searching)
    folders.py         editor tree ops: move/rename/merge/delete folders and templates, index + usage kept in step
    formats.py         file kinds, rtf → HTML/text, HTML → text, <meta> metadata
    docx_html.py       docx → HTML with styles.xml, theme fonts, numbering.xml, spacing, sized pictures
    clipboard_html.py  CF_HTML fragment with every style inline; pictures as file:/// or data: (original bytes)
    variables.py       {date} {time} {clipboard} {input:…} {cursor} …
    highlight.py       language detection + inline-styled Pygments HTML
    noteit_export.py   NoteIT: Outlook HTML with cid: pictures, OneNote page XML, OneNote hierarchy parsing
    backup.py          backup zip (manifest + settings, usage, NoteIT drafts, optional library), rotation, restore
  platform/
    hotkey.py          RegisterHotKey on its own thread; "Ctrl+Q" parsing
    win32.py           foreground window, caret position, focused control, focus, SendInput (Ctrl+V, ←)
    autostart.py       HKCU Run entry, Start-menu shortcut, AppUserModelID
    devpilot.py        DEVPILOT_MANAGED / DEVPILOT_SUPPRESS
    office.py          Outlook / OneNote desktop through COM (pywin32); Word/Outlook paste with source formatting;
                       raises OfficeUnavailable → UI fallback
  ui/
    app.py             Controller: tray, hotkey → picker → insert, watcher, actions
    picker.py          the Ctrl+Q list (built once, then shown/hidden); list or grouped view with foldable headers
    launcher.py        optional card at the cursor on the hotkey: NoteIT or Templates
    noteit.py          NoteIT quick-note window (draft/last note, save, Outlook, OneNote)
    content.py         template → (HTML, text, image) with a small render cache
    inserter.py        clipboard backup → HTML+text → focus target → Ctrl+V → restore
    editor.py          library tree + editors (rich / code / read-only)
    librarytree.py     tree widget: drag & drop reports source + target, the editor moves the files
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
   plain text (plus the bitmap for picture templates and the original RTF for `.rtf` templates without variables),
   the target window gets the focus back, held modifiers are released (so Shift+Enter does not become
   Ctrl+Shift+V), and Ctrl+V is sent with `SendInput`. In Word/Outlook, with `office_com_paste` on and the caret in
   the document body (`_WwG`), the paste is `Selection.PasteAndFormat(wdFormatOriginalFormatting)` instead, because
   Ctrl+V follows the user's "Pasting from other programs" option (possibly "Keep text only").
5. `{cursor}` sends ← as many times as there are characters after the marker.
6. After `restore_delay_ms` the old clipboard is put back.

### Formatting on the clipboard (`core/clipboard_html.py`)

Targets read only the CF_HTML fragment; browsers and Teams also ignore `<head><style>`. Qt keeps the base font
on `<body style>` and paragraph rules in `<head>`, so before pasting the HTML is rebuilt: head rules with plain tag
selectors and the body style are moved inline, `-qt-*` CSS is dropped, `monospace` becomes Consolas, and the
fragment is wrapped in a `<div>` with the base font. Text without a font of its own gets the editor font
(`insert_base_font = editor`) so Word/Outlook do not fall back to Times New Roman; `target` leaves it to the app.

Pictures (`insert_images`): `auto` keeps `file:///` for Office (it embeds the original file) and uses `data:` URIs
for other apps. Both carry the original bytes: pictures are never recompressed or scaled (a picture over 5 MB stays
`file:///` rather than being shrunk). Displayed size comes from the template's `width`/`height`.

## NoteIT

- Opened by its own hotkey (`noteit_hotkey`, default Ctrl+Alt+N, also via RegisterHotKey), from the launcher on the
  main hotkey, from the picker or the tray. The launcher keeps the window and caret recorded by the hotkey thread, so
  "Templates" still pastes into the original app.
- State in `%LOCALAPPDATA%\AutoTemplates\noteit`: `draft.json` (autosaved every 5 s and on close) and `last.json`
  (the last finished note). Copy, save, mail and OneNote "finish" a note: the next open starts empty.
- Save: library sub-folder (typed or picked) or any folder; pictures go to `<name>.assets` like editor templates, so a
  note saved in the library is a normal template.
- Mail: Outlook COM, HTML body with pictures attached inline (`cid:`), shown for review, signature kept.
  Fallback: `mailto:` with plain text.
- OneNote: desktop OneNote COM (`GetHierarchy` → section picker, `CreateNewPage`, `UpdatePageContent` with HTMLBlocks
  and base64 pictures, schema 2013). The Store/"for Windows 10" app has no COM → fallback: clipboard + `onenote:`.

## Backup and restore (`core/backup.py`)

- One zip per backup, `AutoTemplates-backup-YYYYMMDD-HHMMSS[-tag].zip`, written as a hidden `.tmp` and renamed.
  `manifest.json` holds the format version (`FORMAT_VERSION`), app version, date, computer, library path and contents.
- Contents: `settings.json`, `usage.json`, NoteIT `draft.json`/`last.json` and the pictures they link to
  (`data/images`, original bytes, links recorded in `manifest.noteit_images`); the library only when
  `backup_include_templates` is on. `index.json` is a cache and is never included.
- Settings: `backup_dir`, `backup_auto` (off | startup | daily), `backup_keep` (rotation only touches files named like
  backups), `backup_include_templates`, `backup_last`. The controller checks 8 s after start and hourly; the zip is
  written on a background thread (`backup_finished` signal).
- Restore: preview (`RestoreDialog`), safety backup (`-before-restore`) first, then inside `library_operation()`.
  `LOCAL_KEYS` (library folder, backup folder, autostart, NoteIT last folder, OneNote section) stay local; values
  of the wrong type are ignored. Usage is merged (max count, latest use, favourite if either) or replaced.
  Templates never overwrite: identical ones are skipped, different ones become `Name (2)` with their `.assets`
  renamed and the `<img src>` rewritten. NoteIT picture links are rewritten to this computer's cache.
  Backups from a newer format and zips with unsafe paths are refused.

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
## Editor tree operations

`core/folders.py` moves, renames, merges and deletes folders and templates; the editor only asks
the questions. Rules:

- Nothing is ever overwritten: a template with the same name gets `Name (2)` (its `.assets` folder and
  the `src` of its pictures follow); a folder with the same name → the user picks *Merge* or *Keep both*.
- A folder cannot go into itself or a sub-folder of itself.
- Delete goes to the Recycle Bin; if the bin refuses (cloud drives), the user is asked before a permanent delete.
- The index and the usage statistics are updated in the same operation (`Library.apply_moves`,
  `Usage.rename_many`); the controller pauses the folder watcher meanwhile (`library_operation`) and rescans once.
- Statistics of deleted templates are kept `stats_keep_days` days (setting) so a restore from the bin
  gets them back; `Usage.purge` runs after each scan.
- The open template, the NoteIT folder setting and an unsaved new template follow a moved folder.
