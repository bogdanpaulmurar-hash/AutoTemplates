"""In-app user guide (no Qt): short RO/EN sections rendered as simple HTML for a QTextBrowser.

The prose is written by hand; everything that can drift is generated from the code:
the hotkeys and a few values come from the current settings, the key tables from ``core/shortcuts.py``
and the variables from ``core/variables.py``. ``tests/test_guide.py`` checks that every shortcut and
variable appears in both languages.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from autotemplates.core.library import fold
from autotemplates.core.settings import DEFAULTS
from autotemplates.core.shortcuts import (EDITOR_SHORTCUTS, FORMAT_SHORTCUTS, HELP_KEY, NOTEIT_SHORTCUTS,
                                          PICKER_SHORTCUTS, display)
from autotemplates.core.variables import INPUT_EXAMPLE, VARIABLES
from autotemplates.i18n import TEXTS

# Section ids in display order. Windows open the guide on "their" section (F1).
START, PICKER, EDITOR, NOTEIT, VARIABLES_SECTION, SETTINGS, BACKUP, FAQ = (
    "start", "picker", "editor", "noteit", "variables", "settings", "backup", "faq")
SECTION_IDS = (START, PICKER, EDITOR, NOTEIT, VARIABLES_SECTION, SETTINGS, BACKUP, FAQ)

TITLES: dict[str, tuple[str, str]] = {
    START: ("Pornire rapidă", "Quick start"),
    PICKER: ("Picker (lista de template-uri)", "Picker (template list)"),
    EDITOR: ("Editor", "Editor"),
    NOTEIT: ("NoteIT", "NoteIT"),
    VARIABLES_SECTION: ("Variabile", "Variables"),
    SETTINGS: ("Setări", "Settings"),
    BACKUP: ("Backup și restaurare", "Backup and restore"),
    FAQ: ("Probleme frecvente", "Common problems"),
}

# Labels of the commands in core/shortcuts.py (the formatting ones use the editor's own fmt.* texts).
PICKER_LABELS: dict[str, tuple[str, str]] = {
    "edit": ("Editează template-ul selectat", "Edit the selected template"),
    "new": ("Template nou", "New template"),
    "favourite": ("Adaugă / scoate de la ★ Favorite", "Add to / remove from ★ Favourites"),
    "copy": ("Doar copiază, cu formatare", "Copy only, formatted"),
    "copy_plain": ("Doar copiază, ca text simplu", "Copy only, as plain text"),
    "settings": ("Setări", "Settings"),
    "view": ("Grupuri pe foldere ↔ listă simplă (se ține minte)", "Folder groups ↔ plain list (remembered)"),
    "help": ("Ghidul de utilizare", "User guide"),
}
EDITOR_LABELS: dict[str, tuple[str, str]] = {
    "save": ("Salvează template-ul", "Save the template"),
    "new": ("Template formatat nou", "New formatted template"),
    "filter": ("Caută în arbore", "Search the tree"),
    "code": ("Bloc de cod colorat", "Coloured code block"),
    "help": ("Ghidul de utilizare", "User guide"),
}
NOTEIT_LABELS: dict[str, tuple[str, str]] = {
    "copy_close": ("Copiază & Închide", "Copy & Close"),
    "save": ("Salvează nota", "Save the note"),
    "close": ("Închide (ciorna se păstrează)", "Close (the draft is kept)"),
    "help": ("Ghidul de utilizare", "User guide"),
}


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    html: str
    text: str  # folded plain text, for the search box


Tr = Callable[[str, str], str]


# ----------------------------------------------------------------------------- html helpers
def _k(keys: str) -> str:
    return f"<b>{html.escape(display(keys))}</b>"


def _table(rows: list[tuple[str, str]], head: tuple[str, str] | None = None) -> str:
    out = ['<table cellspacing="0" cellpadding="4" border="1" style="border-collapse: collapse; margin: 6px 0;">']
    if head:
        out.append(f"<tr><th align='left'>{head[0]}</th><th align='left'>{head[1]}</th></tr>")
    out.extend(f"<tr><td style='white-space: nowrap;'>{a}</td><td>{b}</td></tr>" for a, b in rows)
    out.append("</table>")
    return "".join(out)


def _ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def _code(text: str) -> str:
    return f"<code>{html.escape(text)}</code>"


def _text(lang_index: int, key: str) -> str:
    pair = TEXTS.get(key)
    return pair[lang_index] if pair else key


def _plain(markup: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", markup)
    return fold(html.unescape(text))


# ----------------------------------------------------------------------------- sections
def _start(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    hk, nk = _k(c["hotkey"]), _k(c["noteit_hotkey"] or "—")
    enter_rich = c["insert_mode"] != "plain"
    enter = tr("cu formatare", "with formatting") if enter_rich else tr("ca text simplu", "as plain text")
    shift = tr("ca text simplu", "as plain text") if enter_rich else tr("cu formatare", "with formatting")
    steps = [
        tr(f"Apasă {hk} oriunde scrii: Outlook, Word, Teams, browser, editorul de cod.",
           f"Press {hk} wherever you type: Outlook, Word, Teams, a browser, your code editor."),
    ]
    if c["launcher_enabled"]:
        steps.append(tr("Apare meniul rapid: <b>T</b> sau <b>Enter</b> = Templates, <b>N</b> = NoteIT.",
                        "The quick menu appears: <b>T</b> or <b>Enter</b> = Templates, <b>N</b> = NoteIT."))
    steps += [
        tr(f"Scrii câteva litere din nume, etichetă sau text. <b>Enter</b> inserează {enter}, "
           f"<b>Shift+Enter</b> {shift}.",
           f"Type a few letters of the name, a tag or the text. <b>Enter</b> inserts {enter}, "
           f"<b>Shift+Enter</b> {shift}."),
        tr("Template-uri noi: în editor (dublu-clic pe iconița din tray) sau ca fișiere în folderul bibliotecii. "
           "Un fișier = un template, un subfolder = o categorie.",
           "New templates: in the editor (double-click the tray icon) or as files in the library folder. "
           "One file = one template, one sub-folder = one category."),
        tr(f"Notă rapidă: {nk} deschide NoteIT.", f"Quick note: {nk} opens NoteIT."),
        tr(f"{_k(HELP_KEY)} în orice fereastră AutoTemplates deschide ghidul la secțiunea ei.",
           f"{_k(HELP_KEY)} in any AutoTemplates window opens this guide on its section."),
    ]
    return ("<ol>" + "".join(f"<li>{s}</li>" for s in steps) + "</ol>"
            + "<p>" + tr("Clipboardul pe care îl aveai revine după inserare. Mailurile nu se trimit niciodată "
                         "singure: se deschid ca să le verifici.",
                         "The clipboard you had comes back after the insertion. Mails are never sent on their "
                         "own: they open for you to review.") + "</p>")


def _picker(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    recent = int(c["picker_recent_count"])
    groups = (tr(f"★ Favorite și Recente (ultimele {recent} folosite) sus, apoi câte un grup pe folder.",
                 f"★ Favourites and Recent (the last {recent} used) on top, then one group per folder.")
              if recent else
              tr("★ Favorite sus, apoi câte un grup pe folder (grupul Recente e oprit din Setări).",
                 "★ Favourites on top, then one group per folder (the Recent group is off in Settings)."))
    rows = [
        (tr("scrii", "type"), tr("filtrează după nume, categorie, etichete, prescurtare și text",
                                  "filters by name, category, tags, shortcut and text")),
        ("<b>↑ ↓ · PgUp PgDn</b>", tr("alegi (antetele de grup se sar)", "choose (group headers are skipped)")),
        ("<b>Enter</b>", tr("inserează (formatul din Setări)", "insert (format from Settings)")),
        ("<b>Shift+Enter</b>", tr("inserează în celălalt format", "insert in the other format")),
        ("<b>Alt+1 … Alt+9</b>", tr("inserează rezultatul cu cifra respectivă", "insert the result with that number")),
        ("<b>← / →</b>", tr("pliază / deschide grupul (în căutare, doar cu câmpul gol)",
                           "fold / open the group (in the search box only while it is empty)")),
        ("<b>Ctrl+↑ / Ctrl+↓</b>", tr("grupul anterior / următor", "previous / next group")),
        ("<b>Tab / Shift+Tab</b>", tr("categoria următoare / anterioară", "next / previous category")),
    ]
    rows += [(_k(PICKER_SHORTCUTS[n]), tr(*PICKER_LABELS[n])) for n in PICKER_SHORTCUTS]
    rows.append(("<b>Esc</b>", tr("închide", "close")))
    return (
        "<p>" + tr(f"Se deschide sub cursor la {_k(c['hotkey'])}. Căutarea nu ține cont de diacritice: "
                   "„raspuns” găsește „Răspuns”. Prescurtarea exactă a unui template apare prima.",
                   f"Opens under the caret on {_k(c['hotkey'])}. Search ignores diacritics: "
                   "“raspuns” finds “Răspuns”. A template's exact shortcut comes first.") + "</p>"
        + "<p><b>" + tr("Grupuri", "Groups") + ":</b> " + groups + " "
        + tr("Grupurile pliate se țin minte. La căutare rămân doar grupurile cu rezultate, toate deschise.",
             "Folded groups are remembered. While searching only groups with results stay, all open.") + "</p>"
        + _table(rows, (tr("Tastă", "Key"), tr("Ce face", "What it does")))
    )


def _editor(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    items = [
        tr("<b>Nou</b>: template formatat, din clipboard, text sau Markdown. „Din clipboard” transformă ce ai "
           "copiat (text formatat, captură, cod) în template.",
           "<b>New</b>: formatted, from clipboard, text or Markdown. “From clipboard” turns whatever you copied "
           "(formatted text, a screenshot, code) into a template."),
        tr("<b>Proprietăți</b>: nume, categorie, etichete, prescurtare (o tastezi în picker), descriere și "
           "modul de inserare.",
           "<b>Properties</b>: name, category, tags, shortcut (typed in the picker), description and insert mode."),
        tr("<b>Poze</b>: Ctrl+V cu o captură, tragi un fișier sau butonul cu cameră (Win+Shift+S). Click pe poză "
           "și tragi de colț ca s-o redimensionezi; dublu-clic deschide dialogul de mărime. Pozele nu se "
           "recomprimă.",
           "<b>Pictures</b>: Ctrl+V a screenshot, drag a file in or use the camera button (Win+Shift+S). Click a "
           "picture and drag its corner to resize; double-click opens the size dialog. Pictures are never "
           "recompressed."),
        tr("<b>Cod colorat</b>: „Bloc de cod colorat” detectează limbajul. Fișierele de cod și text se editează "
           "cu culori.",
           "<b>Coloured code</b>: “Coloured code block” detects the language. Code and text files are edited "
           "with colours."),
        tr("<b>Word, RTF, poze</b> se inserează cum sunt; butonul „Convertește” le transformă în template de editor.",
           "<b>Word, RTF, pictures</b> are inserted as they are; the “Convert” button turns them into an "
           "editor template."),
        tr("<b>Arbore</b>: tragi template-uri și foldere pe alt folder. Click dreapta pe folder: Redenumește, "
           "Mută în…, Șterge. Nimic nu se suprascrie („Nume (2)”), ștergerea merge în Coș, favoritele și "
           "statisticile se mută odată cu template-urile.",
           "<b>Tree</b>: drag templates and folders onto another folder. Right-click a folder: Rename, Move to…, "
           "Delete. Nothing is overwritten (“Name (2)”), delete goes to the Recycle Bin, favourites and "
           "statistics follow the templates."),
    ]
    window = [(_k(EDITOR_SHORTCUTS[n]), tr(*EDITOR_LABELS[n])) for n in EDITOR_SHORTCUTS]
    fmt = [(" · ".join(_k(s) for s in seqs[:1]), _text(li, f"fmt.{name}")) for name, seqs in FORMAT_SHORTCUTS.items()]
    return (
        "<p>" + tr("Se deschide din tray (dublu-clic), din picker (Ctrl+E) sau din DevPilot. În stânga e "
                   "arborele bibliotecii, în dreapta template-ul.",
                   "Open it from the tray (double-click), the picker (Ctrl+E) or DevPilot. The library tree is "
                   "on the left, the template on the right.") + "</p>"
        + _ul(items)
        + "<h3>" + tr("Taste în editor", "Editor keys") + "</h3>"
        + _table(window, (tr("Tastă", "Key"), tr("Ce face", "What it does")))
        + "<h3>" + tr("Formatare (editor și NoteIT)", "Formatting (editor and NoteIT)") + "</h3>"
        + "<p>" + tr("Ca în Word: se aplică pe toată selecția; încă o apăsare scoate formatul.",
                     "Like Word: applies to the whole selection; press again to remove it.") + "</p>"
        + _table(fmt, (tr("Tastă", "Key"), tr("Ce face", "What it does")))
    )


def _noteit(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    nk = _k(c["noteit_hotkey"] or "—")
    items = [
        tr("<b>Copiază & Închide</b>: nota ajunge în clipboard, cu formatare.",
           "<b>Copy & Close</b>: the note goes to the clipboard, formatted."),
        tr("<b>Salvează</b>: într-un subfolder al bibliotecii (alegi unul sau scrii unul nou, de ex. "
           "Notes/Ședințe), deci devine template. „Altă locație…” salvează oriunde.",
           "<b>Save</b>: into a library sub-folder (pick one or type a new one, e.g. Notes/Meetings), so it "
           "becomes a template. “Other location…” saves anywhere."),
        tr("<b>Trimite Email</b>: mail nou în Outlook cu formatare și poze, deschis pentru verificare. Fără "
           "Outlook clasic se deschide un mail simplu.",
           "<b>Send Email</b>: a new Outlook mail with formatting and pictures, opened for review. Without "
           "classic Outlook a plain mail opens."),
        tr("<b>Trimite OneNote</b>: alegi notebook-ul și secțiunea, se creează o pagină. Fără OneNote desktop "
           "nota ajunge în clipboard și se deschide OneNote.",
           "<b>Send to OneNote</b>: pick the notebook and section, a page is created. Without OneNote desktop "
           "the note is copied and OneNote opens."),
        tr("<b>Ciorna</b> rămâne dacă închizi fereastra. „Notă nouă” păstrează nota curentă ca „Ultima notă”, "
           "iar „Ultima notă” o readuce.",
           "<b>The draft</b> stays when you close the window. “New note” keeps the current note as “Last note”, "
           "and “Last note” brings it back."),
    ]
    keys = [(_k(NOTEIT_SHORTCUTS[n]), tr(*NOTEIT_LABELS[n])) for n in NOTEIT_SHORTCUTS]
    return (
        "<p>" + tr(f"Notă rapidă cu formatare și capturi. Se deschide cu {nk}, din meniul rapid (N), din "
                   "picker sau din tray.",
                   f"A quick note with formatting and screenshots. Open it with {nk}, from the quick menu (N), "
                   "the picker or the tray.") + "</p>"
        + _ul(items)
        + _table(keys, (tr("Tastă", "Key"), tr("Ce face", "What it does")))
        + "<p>" + tr("Scurtăturile de formatare sunt aceleași ca în editor.",
                     "The formatting shortcuts are the same as in the editor.") + "</p>"
    )


def _variables(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    rows = [(_code(token), _text(li, key)) for token, key in VARIABLES]
    rows.insert(1, (_code("{date:%Y-%m-%d}"), tr("data în formatul scris după două puncte",
                                                  "the date in the format written after the colon")))
    rows.append((_code("{input:Nume client}") if li == 0 else _code("{input:Customer name}"),
                 tr("întreabă valoarea înainte de inserare; mai multe = un singur formular",
                    "asks for the value before inserting; several = one small form")))
    example = tr("Bună ziua, {input:Nume client},\nvă trimit raportul din {date}.\n{cursor}\nMulțumesc,\n{user}",
                 "Hello {input:Customer name},\nhere is the report of {date}.\n{cursor}\nThanks,\n{user}")
    return (
        "<p>" + tr("Se scriu în template și se completează la inserare. Merg în template-urile formatate, "
                   f"Markdown și text; fișierele de cod se inserează exact cum sunt. În editor: butonul "
                   f"„{_text(0, 'fmt.variable')}”.",
                   "Written in the template and filled in at insertion time. They work in formatted, Markdown "
                   "and text templates; code files are inserted exactly as they are. In the editor: the "
                   f"“{_text(1, 'fmt.variable')}” button.") + "</p>"
        + _table(rows, (tr("Variabilă", "Variable"), tr("Rezultat", "Result")))
        + "<p><b>" + tr("Exemplu", "Example") + ":</b></p>"
        + "<pre>" + html.escape(example) + "</pre>"
        + "<p>" + tr(f"Formatul pentru {{date}} și {{time}} e în Setări → Inserare (acum "
                     f"{_code(c['date_format'])} și {_code(c['time_format'])}).",
                     f"The format of {{date}} and {{time}} is in Settings → Insertion (now "
                     f"{_code(c['date_format'])} and {_code(c['time_format'])}).") + "</p>"
    )


def _settings(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    items = [
        tr("<b>General</b>: folderul bibliotecii, tasta rapidă (o scrii sau apeși combinația), meniul rapid "
           "NoteIT / Templates, tasta NoteIT, limba, tema, pornirea cu Windows.",
           "<b>General</b>: library folder, hotkey (type it or press the combination), the NoteIT / Templates "
           "quick menu, NoteIT hotkey, language, theme, start with Windows."),
        tr("<b>Inserare</b>: ce face Enter (Shift+Enter face celălalt format), fontul textului fără font "
           "propriu, pozele, lipirea în Outlook/Word cu formatarea sursei, restaurarea clipboardului și pauzele, "
           "previzualizarea, sortarea, grupurile din picker, grupul Recente, favoritele, cât se păstrează "
           "statisticile template-urilor șterse, mărimea pickerului, formatul datei și orei.",
           "<b>Insertion</b>: what Enter does (Shift+Enter does the other format), font of text without its "
           "own font, pictures, Outlook/Word paste keeping the source formatting, clipboard restore and delays, "
           "preview, sorting, picker groups, the Recent group, favourites, how long statistics of deleted "
           "templates are kept, picker size, date and time format."),
        tr("<b>Editor</b>: fonturile editorului și ale codului, tema de culori pentru cod, fundalul blocului "
           "de cod inserat.",
           "<b>Editor</b>: editor and code fonts, code colour theme, background of inserted code blocks."),
        tr("<b>Backup</b>: vezi secțiunea Backup și restaurare.", "<b>Backup</b>: see Backup and restore."),
        tr("<b>Despre</b> (jos): versiunea, folderul de date și butonul pentru acest ghid.",
           "<b>About</b> (bottom): version, data folder and the button for this guide."),
    ]
    return (
        "<p>" + tr("Din tray → Setări, din picker (Ctrl+,) sau din editor.",
                   "From tray → Settings, the picker (Ctrl+,) or the editor.") + "</p>"
        + _ul(items)
        + "<p>" + tr("Limba se aplică complet după repornire.", "The language fully applies after a restart.") + "</p>"
    )


def _backup(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    auto = {"off": "backup.auto_off", "startup": "backup.auto_startup"}.get(c["backup_auto"], "backup.auto_daily")
    items = [
        tr("<b>Ce intră</b>: setările, statisticile și favoritele, ciornele NoteIT cu pozele lor. Template-urile "
           "doar cu bifa „Include și template-urile” (biblioteca stă deja în folderul ei, poate sincronizat).",
           "<b>What is saved</b>: settings, statistics and favourites, NoteIT drafts with their pictures. "
           "Templates only with “Also include the templates” ticked (the library already has its own, possibly "
           "synced, folder)."),
        tr("<b>Când</b>: automat zilnic, la fiecare pornire sau oprit; manual cu „Backup acum” din Setări → "
           "Backup, din tray sau din DevPilot. Cele mai vechi copii se șterg peste numărul ales.",
           "<b>When</b>: automatically daily, at every start or off; by hand with “Back up now” in Settings → "
           "Backup, the tray or DevPilot. The oldest copies beyond the chosen number are deleted."),
        tr("<b>Restaurare</b>: Setări → Backup → Restaurează…, alegi zip-ul. Previzualizarea arată ce diferă; "
           "înainte se face un backup de siguranță (…-before-restore.zip).",
           "<b>Restore</b>: Settings → Backup → Restore…, pick the zip. The preview shows what differs; a safety "
           "backup (…-before-restore.zip) is made first."),
        tr("Restaurarea nu suprascrie template-uri (cele diferite vin ca „Nume (2)”) și păstrează setările "
           "acestui calculator: folderul bibliotecii, folderul de backup, pornirea cu Windows. Statisticile: "
           "Combină sau Înlocuiește complet.",
           "A restore never overwrites templates (different ones come in as “Name (2)”) and keeps this "
           "computer's settings: library folder, backup folder, start with Windows. Statistics: Merge or "
           "Replace completely."),
    ]
    now = tr(f"Acum: {_text(0, auto)}, {int(c['backup_keep'])} copii păstrate.",
             f"Now: {_text(1, auto)}, {int(c['backup_keep'])} copies kept.")
    return _ul(items) + f"<p>{now}</p>"


def _faq(tr: Tr, c: Mapping[str, Any], li: int) -> str:
    logs = _code(r"%LOCALAPPDATA%\AutoTemplates\logs")
    items = [
        tr("<b>Tasta nu merge sau e „deja folosită”</b>: altă aplicație a luat combinația; alege alta în Setări → "
           "General. Ctrl+Q e folosit de Outlook, Word și Excel; recomandat Ctrl+Alt+Q.",
           "<b>The hotkey does nothing or is “already used”</b>: another app took the combination; choose another "
           "in Settings → General. Ctrl+Q is used by Outlook, Word and Excel; Ctrl+Alt+Q is recommended."),
        tr("<b>Word/Outlook primesc doar text</b>: bifa „Outlook/Word: lipește păstrând formatarea sursei” din "
           "Setări → Inserare.",
           "<b>Word/Outlook get only text</b>: tick “Outlook/Word: paste keeping the source formatting” in "
           "Settings → Insertion."),
        tr("<b>Nu se lipește nimic sau ajunge în altă fereastră</b>: mărește „Pauză înainte de lipire”. Dacă "
           "apare conținutul vechi din clipboard, mărește „Pauză înainte de restaurare clipboard”.",
           "<b>Nothing is pasted or it lands in another window</b>: raise “Delay before paste”. If the old "
           "clipboard content appears, raise “Delay before clipboard restore”."),
        tr("<b>OneNote din Microsoft Store</b> nu are integrare: nota ajunge în clipboard și o lipești tu.",
           "<b>OneNote from the Microsoft Store</b> has no integration: the note is copied and you paste it."),
        tr("<b>Biblioteca în Google Drive / OneDrive</b> merge: indexul și statisticile stau pe calculator, deci "
           "nu apar conflicte. Dacă pe Drive Coșul refuză o ștergere, ești întrebat înainte.",
           "<b>Library in Google Drive / OneDrive</b> works: the index and statistics stay on the computer, so "
           "there are no conflicts. If the Recycle Bin refuses a delete on a cloud drive, you are asked first."),
        tr("<b>Un template nou nu apare</b>: tray → Reîncarcă biblioteca.",
           "<b>A new template does not show up</b>: tray → Reload library."),
        tr(f"<b>Loguri</b>: {logs}.", f"<b>Logs</b>: {logs}."),
    ]
    return _ul(items)


_BUILDERS: dict[str, Callable[[Tr, Mapping[str, Any], int], str]] = {
    START: _start, PICKER: _picker, EDITOR: _editor, NOTEIT: _noteit, VARIABLES_SECTION: _variables,
    SETTINGS: _settings, BACKUP: _backup, FAQ: _faq,
}


# ----------------------------------------------------------------------------- public
def context(settings: Any = None) -> dict[str, Any]:
    """The setting values the guide shows, from a Settings object, a dict or nothing (defaults)."""
    keys = ("hotkey", "noteit_hotkey", "launcher_enabled", "insert_mode", "picker_recent_count", "date_format",
            "time_format", "backup_auto", "backup_keep")
    out = {}
    for key in keys:
        value = settings.get(key, DEFAULTS[key]) if settings is not None else None
        out[key] = DEFAULTS[key] if value is None else value
    return out


def build(lang: str = "ro", settings: Any = None) -> list[Section]:
    """All sections in the given language, with the current settings filled in."""
    li = 0 if lang.lower().startswith("ro") else 1

    def tr(ro: str, en: str) -> str:
        return ro if li == 0 else en

    ctx = context(settings)
    out = []
    for sid in SECTION_IDS:
        body = _BUILDERS[sid](tr, ctx, li)
        title = TITLES[sid][li]
        out.append(Section(sid, title, f"<h2>{html.escape(title)}</h2>{body}", _plain(title + " " + body)))
    return out


def search(sections: list[Section], query: str) -> list[Section]:
    """Sections containing every word of the query (diacritics optional)."""
    words = fold(query).split()
    return [s for s in sections if all(w in s.text for w in words)]


STYLE = """
h2 { margin: 0 0 8px 0; }
h3 { margin: 14px 0 4px 0; }
td, th { padding: 3px 8px; }
pre { margin: 4px 0; }
"""


def page(section: Section) -> str:
    """Full HTML document of one section for the guide window."""
    return f"<html><head><style>{STYLE}</style></head><body>{section.html}</body></html>"
