"""Outlook and OneNote (desktop) through COM, with pywin32.

Both are optional: every function raises ``OfficeUnavailable`` when the app,
pywin32 or Windows is missing, and the UI falls back to mailto / clipboard.
Nothing is sent automatically: the mail opens for review, the OneNote page is
created in the section the user picked.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from autotemplates.core.noteit_export import (OneNoteSection, body_of, merge_into_body, onenote_page_xml,
                                              outlook_html, parse_hierarchy)

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
HS_SECTIONS = 3  # HierarchyScope.hsSections


class OfficeUnavailable(RuntimeError):
    """The Office app (or pywin32) is not available; use the fallback."""


def _client():
    if not IS_WINDOWS:
        raise OfficeUnavailable("not Windows")
    try:
        import pythoncom  # noqa: F401  (initialises COM for this thread)
        import win32com.client as client
    except ImportError as e:
        raise OfficeUnavailable("pywin32 is not installed") from e
    return client


def _dispatch(prog_id: str):
    client = _client()
    try:
        # Early binding knows the [out] parameters of the OneNote API.
        return client.gencache.EnsureDispatch(prog_id)
    except Exception:  # noqa: BLE001 - broken gen_py cache, no type library...
        try:
            return client.Dispatch(prog_id)
        except Exception as e:  # noqa: BLE001
            raise OfficeUnavailable(f"{prog_id}: {e}") from e


def _out(value):
    """pywin32 returns [out] parameters as the result, sometimes inside a tuple."""
    if isinstance(value, tuple):
        return next((v for v in value if isinstance(v, str)), value[-1])
    return value


# ------------------------------------------------------------------ Outlook
def open_outlook_mail(subject: str, markup: str, base: Path | None = None) -> None:
    """Opens a new Outlook mail with the formatted note and inline pictures."""
    app = _dispatch("Outlook.Application")
    try:
        mail = app.CreateItem(0)  # olMailItem
        body, images = outlook_html(markup, base)
        for img in images:
            att = mail.Attachments.Add(str(img.path), 1, 0)  # olByValue, position 0 = hidden inline
            att.PropertyAccessor.SetProperty(PR_ATTACH_CONTENT_ID, img.cid)
        mail.Subject = subject
        mail.Display(False)  # display first so Outlook adds the default signature
        mail.HTMLBody = merge_into_body(body_of(body), mail.HTMLBody or "")
    except OfficeUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("Outlook mail failed")
        raise OfficeUnavailable(f"Outlook: {e}") from e


# ------------------------------------------------------------------ paste keeping the source formatting
WD_FORMAT_ORIGINAL = 16  # wdFormatOriginalFormatting
COM_PASTE_PROCESSES = {"winword.exe", "outlook.exe"}
WORD_EDITOR_CLASS = "_WwG"  # the Word document window, also used by Outlook's mail editor


def _active(prog_id: str):
    client = _client()
    try:
        return client.GetActiveObject(prog_id)
    except Exception as e:  # noqa: BLE001 - not running, other user, broken registration
        raise OfficeUnavailable(f"{prog_id}: {e}") from e


def _same_window(caption: str, title: str) -> bool:
    caption, title = (caption or "").strip().lower(), (title or "").strip().lower()
    return not title or (bool(caption) and caption in title)


def _selection(process: str, title: str):
    """The Word selection of the editor in the window the user was typing in."""
    if process == "winword.exe":
        word = _active("Word.Application")
        if not _same_window(word.ActiveWindow.Caption, title):
            raise OfficeUnavailable("Word: another window is active")
        return word.ActiveWindow.Selection
    outlook = _active("Outlook.Application")
    inspector = outlook.ActiveInspector()
    if inspector is not None and inspector.EditorType == 4 and _same_window(inspector.Caption, title):  # olEditorWord
        return inspector.WordEditor.Windows(1).Selection
    explorer = outlook.ActiveExplorer()
    if explorer is not None and _same_window(explorer.Caption, title):
        editor = explorer.ActiveInlineResponseWordEditor
        if editor is not None:
            return editor.Application.Selection
    raise OfficeUnavailable("Outlook: no mail editor in this window")


def paste_original(process: str, title: str, focus_class: str) -> None:
    """Pastes the clipboard into Word/Outlook with "Keep source formatting".

    Ctrl+V follows the user's "Pasting from other programs" option, which may be
    "Keep text only". Only used when the caret is in the document body (``_WwG``),
    never in To/Subject. Raises ``OfficeUnavailable`` so the caller falls back to Ctrl+V.
    """
    if process not in COM_PASTE_PROCESSES:
        raise OfficeUnavailable(f"{process}: no COM paste")
    if focus_class != WORD_EDITOR_CLASS:
        raise OfficeUnavailable(f"focus is in {focus_class or 'an unknown control'}, not in the document body")
    selection = _selection(process, title)
    try:
        selection.PasteAndFormat(WD_FORMAT_ORIGINAL)
    except Exception as e:  # noqa: BLE001 - read-only mail, protected document...
        raise OfficeUnavailable(f"PasteAndFormat: {e}") from e


# ------------------------------------------------------------------ OneNote
def onenote_sections() -> list[OneNoteSection]:
    app = _dispatch("OneNote.Application")
    try:
        xml_text = _out(app.GetHierarchy("", HS_SECTIONS))
        return parse_hierarchy(xml_text)
    except Exception as e:  # noqa: BLE001
        log.exception("OneNote hierarchy failed")
        raise OfficeUnavailable(f"OneNote: {e}") from e


def create_onenote_page(section_id: str, title: str, markup: str, base: Path | None = None) -> None:
    """Creates a page in ``section_id`` with the note and opens it in OneNote."""
    app = _dispatch("OneNote.Application")
    try:
        page_id = _out(app.CreateNewPage(section_id, 0))  # npsDefault
        app.UpdatePageContent(onenote_page_xml(page_id, title, markup, base))  # 2013 schema (OneNote 2013+)
        try:
            app.NavigateTo(page_id, "", False)
        except Exception:  # noqa: BLE001 - the page exists; showing it is a bonus
            log.debug("OneNote NavigateTo failed", exc_info=True)
    except Exception as e:  # noqa: BLE001
        log.exception("OneNote page failed")
        raise OfficeUnavailable(f"OneNote: {e}") from e


__all__ = ["OfficeUnavailable", "create_onenote_page", "onenote_sections", "open_outlook_mail"]
