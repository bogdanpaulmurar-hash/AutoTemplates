"""Romanian/English UI strings."""

from __future__ import annotations

_LANG = "ro"

# key: (ro, en)
TEXTS: dict[str, tuple[str, str]] = {
    # launcher
    "launcher.title": ("AutoTemplates Launcher", "AutoTemplates Launcher"),
    "launcher.noteit_title": ("NoteIT", "NoteIT"),
    "launcher.noteit_desc": ("Notă nouă, Word, Outlook, OneNote", "New note, Word, Outlook, OneNote"),
    "launcher.templates_title": ("Templates", "Templates"),
    "launcher.templates_desc": ("Caută și inserează șabloane salvate", "Search and insert saved templates"),
    "launcher.hint": ("Apasă N pentru NoteIT sau Enter/T pentru Templates", "Press N for NoteIT or Enter/T for Templates"),
    # noteit
    "noteit.window_title": ("NoteIT - Notă rapidă", "NoteIT - Quick Note"),
    "noteit.title_placeholder": ("Titlu notă...", "Note title..."),
    "noteit.folder": ("Folder / Categorie:", "Folder / Category:"),
    "noteit.stay_on_top": ("Păstrează fereastra deasupra (Stay on Top)", "Keep window on top (Stay on Top)"),
    "noteit.save": ("Salvează", "Save"),
    "noteit.save_as": ("Salvează ca...", "Save As..."),
    "noteit.copy_close": ("Copiază & Închide", "Copy & Close"),
    "noteit.send_email": ("Trimite Email", "Send Email"),
    "noteit.send_onenote": ("Trimite OneNote", "Send to OneNote"),
    "noteit.saved": ("Notă salvată: {name}", "Note saved: {name}"),
    "noteit.copied": ("Conținutul a fost copiat în clipboard.", "Content copied to clipboard."),
    "picker.noteit": ("NoteIT - Notă nouă", "NoteIT - New Note"),
    "tray.noteit": ("Notă nouă (NoteIT)", "New note (NoteIT)"),
    # picker
    "picker.search": ("Caută template… (nume, categorie, etichetă, text)", "Search templates… (name, category, tag, text)"),
    "picker.hint": ("Enter inserează · Shift+Enter text simplu · Alt+1…9 · Ctrl+E editează · Ctrl+D favorit · Esc",
                    "Enter inserts · Shift+Enter plain · Alt+1…9 · Ctrl+E edits · Ctrl+D favourite · Esc"),
    "picker.empty_library": ("Biblioteca este goală. Adaugă fișiere în:\n{folder}",
                             "Library is empty. Add files to:\n{folder}"),
    "picker.no_match": ("Niciun rezultat găsit.", "No match."),
    "picker.all_categories": ("Toate categoriile", "All categories"),
    "picker.group_categories": ("Comută gruparea vizuală pe categorii/foldere [P3]", "Toggle visual grouping by categories/folders [P3]"),
    "picker.new": ("Template nou", "New template"),
    "picker.edit": ("Editează", "Edit"),
    "picker.editor": ("Deschide editorul", "Open editor"),
    "picker.settings": ("Setări", "Settings"),
    "picker.preview": ("Previzualizare", "Preview"),
    # editor
    "editor.title": ("AutoTemplates — Editor", "AutoTemplates — Editor"),
    "editor.name": ("Nume:", "Name:"),
    "editor.category": ("Categorie:", "Category:"),
    "editor.tags": ("Etichete:", "Tags:"),
    "editor.abbrev": ("Scurtătură (abrev):", "Abbreviation:"),
    "editor.description": ("Descriere:", "Description:"),
    "editor.variables": ("Variabile disponibile", "Available variables"),
    "editor.save": ("Salvează", "Save"),
    "editor.save_and_close": ("Salvează și închide", "Save & close"),
    "editor.cancel": ("Anulează", "Cancel"),
    "editor.delete": ("Șterge", "Delete"),
    "editor.delete_confirm": ("Sigur vrei să ștergi „{name}”?", "Delete template '{name}'?"),
    "editor.new_template": ("Template nou", "New template"),
    "editor.type": ("Tip:", "Type:"),
    "editor.type_rich": ("Rich text (HTML)", "Rich text (HTML)"),
    "editor.type_markdown": ("Markdown", "Markdown"),
    "editor.type_text": ("Text simplu", "Plain text"),
    "editor.type_code": ("Cod", "Code"),
    "editor.type_code_lang": ("Limbaj cod:", "Code language:"),
    "editor.reload": ("Reîncarcă", "Reload"),
    # settings
    "settings.title": ("AutoTemplates — Setări", "AutoTemplates — Settings"),
    "settings.general": ("General", "General"),
    "settings.insertion": ("Inserare", "Insertion"),
    "settings.editor": ("Editor", "Editor"),
    "settings.library": ("Locație bibliotecă:", "Library folder:"),
    "settings.browse": ("Răsfoiește…", "Browse…"),
    "settings.hotkey": ("Tastă rapidă globală:", "Global hotkey:"),
    "settings.launcher_enabled": ("Afișează meniu popup rapid (NoteIT / Templates) la tasta rapidă",
                                  "Show quick popup launcher (NoteIT / Templates) on hotkey"),
    "settings.noteit_hotkey": ("Tastă rapidă NoteIT dedicată:", "Dedicated NoteIT hotkey:"),
    "settings.or_press": ("sau apasă combinația:", "or press the combo:"),
    "settings.hotkey_invalid": ("Combinație invalidă: {error}", "Invalid hotkey: {error}"),
    "settings.language": ("Limbă interfață:", "Interface language:"),
    "settings.theme": ("Temă:", "Theme:"),
    "settings.dark": ("Întunecată", "Dark"),
    "settings.light": ("Luminoasă", "Light"),
    "settings.autostart": ("Pornește odată cu Windows-ul", "Start with Windows"),
    "settings.devpilot_owns": ("(gestionat de Bogdan's DevPilot)", "(managed by Bogdan's DevPilot)"),
    "settings.mode": ("La apăsarea tastei Enter:", "When pressing Enter:"),
    "settings.mode_rich": ("Inserează cu formatare (HTML/Rich)", "Insert with formatting (HTML/Rich)"),
    "settings.mode_plain": ("Inserează ca text simplu", "Insert as plain text"),
    "settings.enter_inserts": ("(Shift+Enter inserează întotdeauna celălalt format)",
                               "(Shift+Enter always inserts the alternate format)"),
    "settings.restore_clipboard": ("Restaurează clipboardul după inserare", "Restore clipboard after insert"),
    "settings.paste_delay": ("Pauză înainte de lipire (ms):", "Delay before paste (ms):"),
    "settings.restore_delay": ("Pauză înainte de restaurare clipboard (ms):", "Delay before clipboard restore (ms):"),
    "settings.preview": ("Arată panoul de previzualizare în picker", "Show preview pane in picker"),
    "settings.sort": ("Sortare inițială:", "Initial sort:"),
    "settings.sort_smart": ("Inteligentă (favorite + frecvente)", "Smart (favourites + frequent)"),
    "settings.sort_name": ("Alfabetic după nume", "Alphabetical by name"),
    "settings.sort_recent": ("Cele mai recente", "Most recent"),
    "settings.picker_size": ("Dimensiune picker (lățime × înălțime):", "Picker size (width × height):"),
    "settings.date_format": ("Format dată ({date}):", "Date format ({date}):"),
    "settings.time_format": ("Format oră ({time}):", "Time format ({time}):"),
    "settings.editor_font": ("Font editor:", "Editor font:"),
    "settings.code_font": ("Font editor de cod:", "Code font:"),
    "settings.code_style": ("Temă culori cod:", "Code color scheme:"),
    "settings.code_bg": ("Fundal bloc cod inserat:", "Inserted code block background:"),
    "settings.code_bg_auto": ("automat din temă", "automatic from theme"),
    "settings.about": ("AutoTemplates v{version}\nDate: {data}\nIntegrat DevPilot: {managed}",
                       "AutoTemplates v{version}\nData: {data}\nDevPilot integrated: {managed}"),
    "settings.managed_yes": ("Da", "Yes"),
    "settings.managed_no": ("Nu", "No"),
    # tray
    "tray.tooltip": ("AutoTemplates — {hotkey}\nApasă pentru a insera un template",
                     "AutoTemplates — {hotkey}\nPress to insert a template"),
    "tray.insert": ("Inserează template…", "Insert template…"),
    "tray.new": ("Template nou…", "New template…"),
    "tray.new_clipboard": ("Template nou din clipboard…", "New template from clipboard…"),
    "tray.editor": ("Editor…", "Editor…"),
    "tray.folder": ("Deschide folderul de template-uri", "Open templates folder"),
    "tray.reload": ("Reîncarcă biblioteca", "Reload library"),
    "tray.settings": ("Setări…", "Settings…"),
    "tray.quit": ("Ieșire", "Quit"),
    "tray.hotkey_busy": ("Scurtătura {hotkey} este deja folosită de altă aplicație.",
                         "Hotkey {hotkey} is already taken by another application."),
    "tray.inserted": ("Inserat: {name}", "Inserted: {name}"),
    "tray.copied": ("Copiat în clipboard: {name}", "Copied to clipboard: {name}"),
    "tray.reloaded": ("Biblioteca a fost reîncărcată ({count} template-uri).",
                      "Library reloaded ({count} templates)."),
    # variables
    "var.user": ("Nume utilizator curent", "Current user name"),
    "var.date": ("Data curentă", "Current date"),
    "var.time": ("Ora curentă", "Current time"),
    "var.datetime": ("Data și ora", "Date and time"),
    "var.clipboard": ("Conținutul curent din clipboard", "Current clipboard contents"),
    "var.cursor": ("Poziția finală a cursorului după inserare", "Final cursor position after insert"),
    "var.input": ("Câmp solicitat la inserare", "Prompt asked at insert"),
    "var.select": ("Opțiune selectată din listă", "Choice selected from list"),
}


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "ro" if lang.lower().startswith("ro") else "en"


def get_language() -> str:
    return _LANG


def t(key: str, **kwargs) -> str:
    pair = TEXTS.get(key)
    text = key if pair is None else pair[0 if _LANG == "ro" else 1]
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
