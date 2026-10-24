# AutoTemplates

Small, fast template inserter for Windows. Press **Ctrl+Q** wherever you type (Outlook, Word, Teams, a browser,
Visual Studio…), pick a template from the list and it is inserted at the cursor: formatted text, screenshots,
tables and coloured code included. Runs on its own (tray icon) or inside **DevPilot**.

- No `.exe`: Python + PySide6, installed per user in a private virtual environment.
- Two dependencies only: `PySide6-Essentials` and `Pygments`. Word and RTF files are read with the standard library.
- The library is a plain folder (it can live in Google Drive / OneDrive): every file is a template, every sub-folder a category.

## Pe scurt (RO)

1. Rulează `Install.bat` (fără drepturi de admin). Pornește singur cu Windows, iconița e în tray.
2. Apasă **Ctrl+Q** oriunde scrii, caută, **Enter** = cu formatare, **Shift+Enter** = text simplu.
3. Template-urile se fac în editor (dublu-clic pe iconiță) sau se pun ca fișiere în `Documente\AutoTemplates`.
4. Tasta, folderul, limba (RO/EN), aspectul și fonturile se schimbă din **Setări**.
5. **NoteIT** (Ctrl+Alt+N sau din meniul de la Ctrl+Q): notă rapidă cu formatare și capturi. Copiere, salvare ca template, mail în Outlook sau pagină în OneNote. Ciorna se păstrează dacă închizi fereastra.
6. **Ghid de utilizare**: F1 în orice fereastră (sau din tray) arată tastele și pașii pe scurt.

## Install

Requirements: Windows 10/11, Python 3.10+ from python.org (per-user install is fine).

```bat
Install.bat
```

This creates `%LOCALAPPDATA%\AutoTemplates\venv`, a Start-menu and Desktop shortcut, turns on *start with Windows*
and starts the app in the tray. `Uninstall.bat` removes everything except your settings and templates.

Manual / development:

```bat
py -3 -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\pythonw -m autotemplates
```

## Using it

| In the list (Ctrl+Q) | |
|---|---|
| type | filters by name, category, tags, shortcut and content (diacritics optional: `raspuns` finds `Răspuns`) |
| ↑ ↓ PgUp PgDn | choose |
| **Enter** | insert with formatting (HTML + plain text on the clipboard, the target program takes the best one) |
| **Shift+Enter** | insert as plain text |
| Alt+1 … Alt+9 | insert the n-th result (headers are not counted) |
| Ctrl+C / Ctrl+Shift+C | copy only (formatted / plain) |
| Ctrl+E · Ctrl+N · Ctrl+D | edit · new template · favourite |
| Tab / Shift+Tab | next / previous category |
| Ctrl+G (or the folder button) | grouped view ↔ plain list (remembered) |
| ← / → · Ctrl+↑ / Ctrl+↓ | grouped view: fold / open the current group · previous / next group |
| Esc | close |

The clipboard you had before is restored after the insertion (setting).

Ordering is *smart* by default: exact shortcut match, favourites, frequently and recently used templates first.

The list is **grouped** by default: ★ Favourites and Recent (the last 5 used) on top, then one foldable group per
folder. Folded groups are remembered; while you type, only the groups with results are shown, all open, the best
match first. Settings → Insert: view (groups / list), number of recent templates (0 = none), whether favourites also
stay in their folder.

### User guide

**F1** in any AutoTemplates window (picker, editor, NoteIT, Settings) opens a short guide in Romanian or English
on the matching section; also from the tray menu, Settings › About and DevPilot. It lists the keys and your
current hotkeys straight from the app, so it is always up to date.

### Variables

Usable in formatted, Markdown and text templates (code files are inserted verbatim):

| Variable | Result |
|---|---|
| `{date}` `{time}` `{datetime}` | now, in the formats from the settings; `{date:%Y-%m-%d}` for a custom format |
| `{weekday}` | day of the week (RO/EN) |
| `{clipboard}` | the text on the clipboard |
| `{user}` | the Windows user name |
| `{input:Customer name}` | asks for a value before inserting (several `{input:…}` = one small form) |
| `{cursor}` | where the caret ends up after the insertion |

### Editor

Open it from the tray (double-click), the list (Ctrl+E) or DevPilot.

- **Formatting:** headings, font, size, bold, italic, underline, strikethrough, superscript, subscript, text colour,
  highlight/background, clear formatting, alignment, line spacing, paragraph spacing, bulleted and numbered lists,
  indentation, links, tables (rows/columns/cell colour), horizontal line.
- **Pictures:** paste a screenshot (Ctrl+V), drag a file in, insert from file, or use the camera button
  (Windows snipping, the capture is inserted automatically). Resize: click the picture and drag its corner,
  double-click it, or use the right-click menu.
- **Clear formatting** (Ctrl+Space) removes character and paragraph styles from the selection; its menu also
  clears the whole document or pastes as plain text (Ctrl+Shift+V). Pictures and links stay.
- **Code:** *Coloured code block* detects the language (Python, JSON, C#, JS/TS, SQL, XML/HTML, YAML,
  PowerShell, Batch, Bash, CSS, C/C++, Java, Markdown…) and inserts it coloured. Code and text files are edited
  with live syntax colouring.
- **Per template:** name, category, tags, shortcut, description and insert mode (as in settings / formatted / plain).
- **New › From clipboard** turns whatever you copied (formatted text, screenshot, code) into a template.
- Word (`.docx`), RTF and pictures are inserted as they are; *Make an editable copy* converts them to an editor template.
- **Library tree:** drag templates and folders onto another folder (or onto empty space for the top level). Right-click a folder: *Rename*, *Move to…*, *Delete*. Nothing is overwritten: a same-name template becomes `Name (2)`; for a same-name folder you choose *Merge* or *Keep both*. Usage statistics and favourites follow the moved templates.
- Delete moves templates and folders to the Recycle Bin (if the bin refuses, e.g. on a cloud drive, you are asked before a permanent delete). Statistics of deleted templates are kept for a number of days (Settings › Insertion), so a restore brings them back.

Formatting shortcuts (template editor and NoteIT):

| Keys | |
|---|---|
| Ctrl+B · Ctrl+I · Ctrl+U · Ctrl+Shift+X | bold · italic · underline · strikethrough (whole selection, like Word) |
| Ctrl+Shift+= · Ctrl+= | superscript · subscript |
| Ctrl+Shift+L · Ctrl+Shift+O | bulleted · numbered list |
| Ctrl+M · Ctrl+Shift+M | indent · outdent |
| Ctrl+Alt+1/2/3 · Ctrl+Shift+N | heading 1/2/3 · normal |
| Ctrl+L · Ctrl+E · Ctrl+R · Ctrl+J | align left · centre · right · justify |
| Ctrl+K · Ctrl+Space · Ctrl+Shift+V | link · clear formatting · paste as plain text |

### NoteIT

A quick-note window (own hotkey, default **Ctrl+Alt+N**; also from the launcher on the main hotkey, the picker and the tray).
Title, formatted text and screenshots, then:

- **Copy & Close** (Ctrl+Enter): the note goes to the clipboard, formatted.
- **Save** (Ctrl+S): into a library sub-folder (pick one or type a new one, e.g. `Notes/Meetings`), so it becomes a template; *Other location…* saves anywhere.
- **Send Email**: a new Outlook mail with the formatted note and inline pictures, opened for review (needs classic Outlook; otherwise a plain `mailto:`).
- **Send to OneNote**: pick the notebook / section, a page is created and opened (needs OneNote desktop; otherwise the note is copied and OneNote is opened).

Closing the window keeps a draft. **Last note** brings back the previously finished note.

### Backup

Settings → **Backup**: a zip with the settings, the usage statistics and favourites, and the NoteIT drafts (with
their pictures); the templates only if you tick it (the library folder is usually synced already).
Default folder `Documents\AutoTemplates Backups`, automatic backup **daily** (at most one a day), the newest
**10** kept. *Back up now* is also in the tray menu. *Restore…* shows what the backup holds and what would change,
makes a safety backup first, keeps this computer's paths, merges the statistics and never overwrites a template
(different ones come back as `Name (2)`).

## Library folder

Default `Documents\AutoTemplates` (change it in Settings). Supported files:

| Kind | Extensions |
|---|---|
| Formatted (editor) | `.html` `.htm` – pictures in `<name>.assets\`, metadata in `<meta name="autotemplates:…">` |
| Markdown | `.md` `.markdown` (inserted rendered; plain-text mode inserts the Markdown source) |
| Text | `.txt` `.log` `.csv` `.tsv` |
| Word / RTF | `.docx` (formatting, lists, tables, pictures) · `.rtf` (text) |
| Pictures | `.png` `.jpg` `.jpeg` `.gif` `.bmp` `.webp` |
| Code | `.py` `.json` `.cs` `.js` `.ts` `.tsx` `.sql` `.xml` `.xaml` `.yaml` `.ps1` `.bat` `.cmd` `.sh` `.css` `.scss` `.c` `.cpp` `.h` `.java` `.kt` `.go` `.rs` `.php` `.rb` `.vb` `.ini` `.toml` `.lua` … |

Files are picked up automatically when they change (folder watcher). Hidden files, Office lock files (`~$…`) and
`*.assets` folders are ignored. Usage statistics and favourites stay on this PC (`%LOCALAPPDATA%\AutoTemplates`),
so a synced library never conflicts.

## DevPilot

AutoTemplates follows DevPilot's integration contract (`docs/INTEGRATION.md` in DevPilot):

- `devpilot.tool.json` (repository root, also copied to `%LOCALAPPDATA%\AutoTemplates`) describes the actions:
  *Insert template*, *New template*, *New from clipboard*, *Editor and library*, *Library folder*, *Reload*, *Settings*.
  Each one is `python -m autotemplates action <id>`, forwarded to the running app (it starts when needed).
- In DevPilot set **Interpreter** to `%LOCALAPPDATA%\AutoTemplates\venv\Scripts\pythonw.exe`, **Python module**
  `autotemplates`, arguments `gui` (or load *From devpilot.tool.json*).
- When DevPilot starts it with `DEVPILOT_SUPPRESS=tray,autostart`, AutoTemplates shows no tray icon of its own and
  leaves the *start with Windows* entry to DevPilot. The hotkey keeps working in both cases.
- *Insert template* from the hub copies the chosen template to the clipboard (the hub has the focus, so there is
  no text field to paste into); Ctrl+Q inserts directly.

## Hotkey

Ctrl+Q is registered with `RegisterHotKey` (no keyboard hook). While AutoTemplates runs, programs that use Ctrl+Q
themselves (Outlook: mark as read, Word: reset paragraph, Excel: Quick Analysis) do not receive it. Pick another
combination in Settings if needed (for example `Ctrl+Alt+Q`); the settings show whether the hotkey is active.

## Command line

```
python -m autotemplates [gui] [--autostart]
python -m autotemplates action picker|new|new_clipboard|editor|settings|folder|reload|backup|quit [--no-start]
python -m autotemplates setup [--start-menu] [--autostart on|off] [--remove]
python -m autotemplates version
python -m autotemplates --self-test
```

## Development

```
pip install -e .[dev]
pytest                      # on Linux: QT_QPA_PLATFORM=offscreen pytest
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.