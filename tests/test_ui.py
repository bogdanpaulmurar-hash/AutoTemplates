from pathlib import Path

from PySide6.QtGui import QColor, QImage, QTextListFormat

from autotemplates.core.paths import AppPaths
from autotemplates.core.settings import Settings


def _controller(qapp, home):
    from autotemplates.ui.app import Controller

    paths = AppPaths(home / "data").ensure()
    c = Controller(qapp, paths, Settings(paths.settings_file))
    c._ensure_library()
    c.rescan(sync=True)
    return c


def test_samples_render(qapp, home):
    c = _controller(qapp, home)
    kinds = {t.kind for t in c.library.templates}
    assert {"rich", "code", "text", "markdown"} <= kinds
    for tpl in c.library.templates:
        r = c.renderer.render(tpl, c.library.root)
        assert r.html
    py = next(t for t in c.library.templates if t.rel.endswith(".py"))
    r = c.renderer.render(py, c.library.root)
    assert not r.variables and "<pre" in r.html and "def main" in r.text


def test_prepare_variables_and_cursor(qapp, home):
    c = _controller(qapp, home)
    tpl = next(t for t in c.library.templates if t.category == "Email")
    r = c.renderer.render(tpl, c.library.root)
    from autotemplates.core import variables as tv

    assert tv.input_prompts(r.text + r.html)[:1] in (["Nume"], ["Name"])
    html, text, back = c.inserter.prepare(r, plain=False, answers={"Nume": "Ana", "Termen": "vineri"})
    assert "Ana" in text and "{date}" not in text and "{cursor}" not in html and back > 0


def test_mime(qapp, tmp_path):
    from autotemplates.ui.inserter import build_mime

    img = tmp_path / "a.png"
    QImage(10, 10, QImage.Format_RGB32).save(str(img))
    m = build_mime("<b>x</b>", "x", img)
    assert m.hasHtml() and m.text() == "x" and m.hasImage()
    p = build_mime("<b>x</b>", "x", img, plain=True)
    assert not p.hasHtml() and not p.hasImage()


def test_editor_rich_roundtrip_with_image(qapp, home):
    c = _controller(qapp, home)
    ed = c.editor
    ed.new_template("rich", category="Test")
    ed.name.setText("Cu imagine")
    r = ed.rich
    r.insertPlainText("Titlu")
    r.set_heading(1)
    r.textCursor().insertBlock()
    r.set_bold(True)
    r.insertPlainText("bold")
    r.set_color(QColor("#c62828"))
    r.set_highlight(QColor("#fff59d"))
    r.set_line_spacing(1.5)
    r.set_paragraph_spacing(6, 12)
    r.toggle_list(QTextListFormat.ListDisc)
    r.insert_table(2, 2)
    r.table_op("row_below")
    image = QImage(40, 20, QImage.Format_RGB32)
    image.fill(QColor("red"))
    r.insert_image_file(r.save_image(image))
    assert ed.save()
    path = c.library.root / "Test" / "Cu imagine.html"
    html = path.read_text(encoding="utf-8")
    assert 'src="Cu imagine.assets/' in html
    assert len(list((c.library.root / "Test" / "Cu imagine.assets").iterdir())) == 1
    tpl = c.library.get("Test/Cu imagine.html")
    assert tpl is not None
    rendered = c.renderer.render(tpl, c.library.root)
    assert "file:///" in rendered.html  # absolute for pasting
    # rename moves the assets folder too
    ed.name.setText("Redenumit")
    ed._set_dirty(True)
    assert ed.save()
    assert (c.library.root / "Test" / "Redenumit.assets").is_dir()
    assert not (c.library.root / "Test" / "Cu imagine.html").exists()
    assert 'src="Redenumit.assets/' in (c.library.root / "Test" / "Redenumit.html").read_text(encoding="utf-8")


def test_editor_code_template(qapp, home):
    c = _controller(qapp, home)
    ed = c.editor
    ed.new_template("code", "json", text='{"a": 1}')
    ed.name.setText("cfg")
    assert ed.save()
    tpl = c.library.get("cfg.json")
    assert tpl and tpl.kind == "code" and tpl.language == "json"


def test_convert_docx(qapp, home):
    from conftest import make_docx

    c = _controller(qapp, home)
    make_docx(c.library.root / "Word.docx")
    c.rescan(sync=True)
    c.editor.open_template("Word.docx")
    c.editor.convert_to_rich()
    assert c.library.get("Word.html") is not None


def test_picker_search(qapp, home):
    c = _controller(qapp, home)
    p = c.picker
    p.popup(None)
    p.search.setText("json")
    assert p.list.count() >= 1 and p.current_rel().endswith(".json")
    p.hide()


def test_instance_channel(tmp_path):
    from autotemplates.instance import InstanceServer, action_message, send

    got = []
    server = InstanceServer(tmp_path, lambda m: (got.append(m), {"ok": True})[1])
    assert server.start()
    assert send(tmp_path, action_message("picker")) == {"ok": True}
    assert got[0]["action"] == "picker"
    server.stop()


def test_clear_formatting_keeps_pictures(qapp, tmp_path):
    from PySide6.QtGui import QTextCursor

    from autotemplates.ui.richedit import RichEdit

    r = RichEdit(tmp_path)
    r.setHtml('<p><span style="color:#ff0000;background-color:#ffff00;font-weight:700">Red</span> plain</p>')
    r.moveCursor(QTextCursor.End)
    r.insert_image_file(r.save_image(QImage(5, 5, QImage.Format_RGB32)))
    cursor = r.textCursor()
    cursor.select(QTextCursor.Document)
    r.setTextCursor(cursor)
    r.set_highlight(None)
    assert "background-color" not in r.toHtml().split("<body")[1]
    r.set_color(None)
    assert "#ff0000" not in r.toHtml()
    r.clear_formatting()
    html = r.toHtml()
    assert "font-weight:700" not in html and "<img" in html

def test_noteit_save_draft_and_last(qapp, home):
    from autotemplates.ui.noteit import NoteITWindow

    c = _controller(qapp, home)
    ni = c.noteit
    img = QImage(8, 8, QImage.Format_RGB32)
    img.fill(QColor("red"))
    shot = ni.editor.save_image(img)

    # draft survives a restart of the window
    ni.reset_form()
    ni.title_edit.setText("Meeting 1")
    ni.editor.setHtml(f'<p>Body</p><img src="{shot.as_uri()}" width="8" height="8" />')
    ni.close()
    again = NoteITWindow(c)
    assert again.title_edit.text() == "Meeting 1" and "Body" in again.editor.toPlainText()

    # save -> library sub-folder, pictures copied next to the note, relative src
    ni.combo_folder.setEditText("Notes/Meetings")
    ni._save_note()
    saved = c.library.root / "Notes" / "Meetings" / "Meeting 1.html"
    assert saved.is_file()
    markup = saved.read_text(encoding="utf-8")
    assert "file:" not in markup and "Meeting 1.assets/" in markup
    assert (saved.with_suffix(".assets") / shot.name).is_file()
    assert not (ni.state_dir / "draft.json").exists()

    # a finished note gives way to an empty one; "Last note" brings it back
    ni.prepare_to_show()
    assert ni.is_empty()
    ni.restore_last()
    assert ni.title_edit.text() == "Meeting 1"


def test_launcher_templates_keep_hotkey_target(qapp, home, monkeypatch):
    from autotemplates.platform import win32

    c = _controller(qapp, home)
    monkeypatch.setattr(win32, "can_receive", lambda hwnd: True)
    monkeypatch.setattr(win32, "foreground_window", lambda: 999)  # would be the launcher itself
    c.settings.set("launcher_enabled", True)
    c._on_hotkey(1234, None)
    assert c._target == 1234
    c.launcher.templates_selected.emit()
    assert c._target == 1234
    c.picker.hide()


# ---------------------------------------------------------------- formatting shortcuts (Ctrl+B/I/U …)
def _key(widget, key, mods):
    from PySide6.QtTest import QTest

    QTest.keyClick(widget, key, mods)


def _select(r, start, end):
    from PySide6.QtGui import QTextCursor

    cursor = r.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.KeepAnchor)
    r.setTextCursor(cursor)


def test_richedit_bold_italic_underline_toggle_like_word(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    from autotemplates.ui.richedit import RichEdit

    r = RichEdit(tmp_path)
    r.setPlainText("one two")
    bold = lambda f: f.fontWeight() >= QFont.DemiBold  # noqa: E731
    _select(r, 0, 7)
    _key(r, Qt.Key_B, Qt.ControlModifier)
    assert r._all_selected(bold)
    _key(r, Qt.Key_B, Qt.ControlModifier)
    assert not r._all_selected(bold)
    # mixed selection -> everything becomes bold (not un-bolded)
    _select(r, 0, 3)
    _key(r, Qt.Key_B, Qt.ControlModifier)
    _select(r, 0, 7)
    _key(r, Qt.Key_B, Qt.ControlModifier)
    assert r._all_selected(bold)
    for key, test in ((Qt.Key_I, lambda f: f.fontItalic()), (Qt.Key_U, lambda f: f.fontUnderline())):
        _key(r, key, Qt.ControlModifier)
        assert r._all_selected(test)
        _key(r, key, Qt.ControlModifier)
        assert not r._all_selected(test)
    _key(r, Qt.Key_X, Qt.ControlModifier | Qt.ShiftModifier)
    assert r._all_selected(lambda f: f.fontStrikeOut())


def test_richedit_paragraph_shortcuts_and_clear(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QTextListFormat

    from autotemplates.ui.richedit import RichEdit

    r = RichEdit(tmp_path)
    r.setPlainText("item")
    _key(r, Qt.Key_L, Qt.ControlModifier | Qt.ShiftModifier)
    assert r.textCursor().currentList().format().style() == QTextListFormat.ListDisc
    _key(r, Qt.Key_M, Qt.ControlModifier)
    assert r.textCursor().currentList().format().indent() == 2
    _key(r, Qt.Key_M, Qt.ControlModifier | Qt.ShiftModifier)
    assert r.textCursor().currentList().format().indent() == 1
    _key(r, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
    assert r.textCursor().currentList().format().style() == QTextListFormat.ListDecimal
    _key(r, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
    assert r.textCursor().currentList() is None

    _key(r, Qt.Key_1, Qt.ControlModifier | Qt.AltModifier)
    assert r.textCursor().blockFormat().headingLevel() == 1
    _key(r, Qt.Key_E, Qt.ControlModifier)
    assert r.alignment() & Qt.AlignHCenter
    _key(r, Qt.Key_N, Qt.ControlModifier | Qt.ShiftModifier)
    assert r.textCursor().blockFormat().headingLevel() == 0

    # Ctrl+Space clears characters and paragraph (heading, list, alignment), keeps links
    r.setHtml('<h1 style="text-align:center"><b>Big</b> <a href="https://x.test">link</a></h1><ul><li>li</li></ul>')
    _select(r, 0, len(r.toPlainText()))
    _key(r, Qt.Key_Space, Qt.ControlModifier)
    html = r.toHtml()
    assert "https://x.test" in html and "<ul" not in html and "<h1" not in html
    assert not r._all_selected(lambda f: f.fontWeight() >= QFont.DemiBold)
    assert not (r.alignment() & Qt.AlignHCenter)


def test_richedit_claims_its_shortcuts_only(qapp, tmp_path):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from autotemplates.ui.richedit import FORMAT_SHORTCUTS, RichEdit, with_shortcut

    r = RichEdit(tmp_path)
    ev = lambda key, mods, text="": QKeyEvent(QEvent.ShortcutOverride, key, mods, text)  # noqa: E731
    assert r.format_command(ev(Qt.Key_B, Qt.ControlModifier)) == "bold"
    assert r.format_command(ev(Qt.Key_S, Qt.ControlModifier)) is None  # Ctrl+S stays with the window
    assert r.format_command(ev(Qt.Key_Q, Qt.ControlModifier)) is None
    assert r.format_command(ev(Qt.Key_Plus, Qt.ControlModifier | Qt.ShiftModifier, "+")) == "superscript"
    # AltGr (= Ctrl+Alt on Windows) typing a character must not become a shortcut
    assert r.format_command(ev(Qt.Key_1, Qt.ControlModifier | Qt.AltModifier, "~")) is None
    assert r.format_command(ev(Qt.Key_1, Qt.ControlModifier | Qt.AltModifier)) == "h1"
    r.setReadOnly(True)
    assert r.format_command(ev(Qt.Key_B, Qt.ControlModifier)) is None
    assert with_shortcut("Bold", "bold") == "Bold (Ctrl+B)"
    assert all(seqs for seqs in FORMAT_SHORTCUTS.values())


def test_editor_and_noteit_tooltips_and_no_duplicate_shortcuts(qapp, home):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QToolButton

    c = _controller(qapp, home)
    ed = c.editor
    assert "Ctrl+B" in ed.a_bold.toolTip() and "Ctrl+Shift+L" in "".join(
        a.toolTip() for a in ed.findChildren(QAction))
    seqs = [a.shortcut().toString() for a in ed.findChildren(QAction) if not a.shortcut().isEmpty()]
    assert len(seqs) == len(set(seqs)), seqs

    tips = " ".join(b.toolTip() for b in c.noteit.findChildren(QToolButton))
    assert "Ctrl+B" in tips and "Ctrl+Space" in tips

    # toolbar button and shortcut run the same command
    ed.new_template("rich", category="Test")
    ed.rich.setPlainText("abc")
    _select(ed.rich, 0, 3)
    ed.a_bold.trigger()
    assert ed.a_bold.isChecked()

    # the code editor has no rich formatting: Ctrl+B leaves the text alone
    ed.code.setPlainText("x = 1")
    _key(ed.code, Qt.Key_B, Qt.ControlModifier)
    assert ed.code.toPlainText() == "x = 1"


def test_noteit_shortcut_formats_note(qapp, home):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    c = _controller(qapp, home)
    ed = c.noteit.editor
    ed.setPlainText("note")
    _select(ed, 0, 4)
    _key(ed, Qt.Key_B, Qt.ControlModifier)
    assert ed._all_selected(lambda f: f.fontWeight() >= QFont.DemiBold)


def test_image_drag_resize_and_clear_all(qapp, tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from autotemplates.ui.richedit import RichEdit

    r = RichEdit(tmp_path)
    r.resize(500, 400)
    r.show()
    img = QImage(100, 50, QImage.Format_RGB32)
    img.fill(QColor("blue"))
    r.insert_image_file(r.save_image(img))
    _select(r, 0, 1)
    assert r._active_image == 0
    qapp.processEvents()
    handle = r._handle_rect()
    assert handle is not None
    start = handle.center()
    QTest.mousePress(r.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(r.viewport(), start + QPoint(40, 10))
    QTest.mouseRelease(r.viewport(), Qt.LeftButton, Qt.NoModifier, start + QPoint(40, 10))
    found = r._image_at_doc_pos(0)
    assert found and int(found[1].width()) == 140 and int(found[1].height()) == 70

    r.moveCursor(r.textCursor().MoveOperation.End)
    r.insertHtml("<b>bold</b>")
    r.clear_all_formatting()
    assert "font-weight:700" not in r.toHtml() and "<img" in r.toHtml()
    r.close()


def test_editor_tree_folder_move_rename_delete(qapp, home, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    c = _controller(qapp, home)
    ed = c.editor
    root = c.library.root
    for rel in ("Work/Mail/A.txt", "Work/B.txt", "Notes/N.txt"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel, encoding="utf-8")
    c.rescan(sync=True)
    c.library.usage.set_favourite("Work/Mail/A.txt", True)
    c.settings.set("noteit_folder", "Work/Mail")
    ed.reload_tree()
    ed.open_template("Work/Mail/A.txt")

    # drop of a folder (what LibraryTree emits) moves it, keeps stats, follows the open template and NoteIT folder
    ed._tree_dropped("folder", "Work/Mail", "Notes")
    assert (root / "Notes/Mail/A.txt").exists() and not (root / "Work/Mail").exists()
    assert c.library.usage.favourite("Notes/Mail/A.txt")
    assert ed.current.rel == "Notes/Mail/A.txt"
    assert c.settings.get("noteit_folder") == "Notes/Mail"

    # drop of a template onto the library root
    ed._tree_dropped("template", "Work/B.txt", "")
    assert (root / "B.txt").exists() and c.library.get("B.txt")

    # rename with a conflict → "keep both"
    (root / "Notes/Other").mkdir()
    monkeypatch.setattr(ed, "_ask_conflict", lambda target: "keep_both")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    ed.move_folder_to("Notes/Mail", "Notes", "Other")
    assert (root / "Notes/Other (2)/A.txt").exists()

    # the tree refuses to drop a folder into itself
    from autotemplates.ui.librarytree import LibraryTree
    assert not LibraryTree.can_drop(("folder", "Notes"), "Notes/Other (2)")
    assert LibraryTree.can_drop(("folder", "Notes/Other (2)"), "")

    # delete: Recycle Bin refused → asks, "No" keeps everything; "Yes" deletes permanently
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(type(ed), "_trash", staticmethod(lambda p: False))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    ed.delete_folder("Notes")
    assert (root / "Notes").is_dir()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Yes)
    ed.delete_folder("Notes")
    assert not (root / "Notes").exists()
    assert ed.current is None
    assert c.settings.get("noteit_folder") == "Notes"  # back to the default
    assert not any(t.rel.startswith("Notes/") for t in c.library.templates)


def test_rtf_template_keeps_original_rtf_and_formatted_html(qapp, home):
    from conftest import SAMPLE_RTF
    from autotemplates.ui.inserter import RTF_MIME

    c = _controller(qapp, home)
    (c.library.root / "Semnătură.rtf").write_bytes(SAMPLE_RTF.encode("latin-1"))
    c.rescan(sync=True)
    tpl = c.library.get("Semnătură.rtf")
    r = c.renderer.render(tpl, c.library.root)
    assert r.rtf == SAMPLE_RTF.encode("latin-1") and "<b>Titlu</b>" in r.html and "Titlu" in r.text
    html, text, _ = c.inserter.prepare(r, plain=False)
    rich = c.inserter.mime_for(r, html, text, plain=False)
    assert RTF_MIME in rich.formats() and bytes(rich.data(RTF_MIME)) == r.rtf
    assert rich.html().count("<!--StartFragment-->") == 1 and "<b>Titlu</b>" in rich.html()
    plain = c.inserter.mime_for(r, html, text, plain=True)
    assert RTF_MIME not in plain.formats() and not plain.hasHtml() and plain.text() == text


def test_rtf_with_variables_uses_filled_html_only(qapp, home):
    from autotemplates.ui.content import Rendered
    from autotemplates.ui.inserter import RTF_MIME

    c = _controller(qapp, home)
    r = Rendered("<p>Azi {date}</p>", "Azi {date}", rtf=rb"{\rtf1 Azi \{date\}\par}")
    html, text, _ = c.inserter.prepare(r, plain=False)
    m = c.inserter.mime_for(r, html, text, plain=False)
    assert RTF_MIME not in m.formats() and "{date}" not in m.html()


def test_clipboard_html_base_font_and_pictures(qapp, home, tmp_path):
    import base64
    import re

    from autotemplates.ui.content import Rendered

    c = _controller(qapp, home)
    c.settings.update({"editor_font_family": "Calibri", "editor_font_size": 12})
    pic = tmp_path / "s.png"
    QImage(1600, 900, QImage.Format_RGB32).save(str(pic))
    original = pic.read_bytes()
    r = Rendered(f'<p>Salut <img src="{pic.as_uri()}" width="800" height="450"/></p>', "Salut")
    html, text, _ = c.inserter.prepare(r, plain=False)

    office = c.inserter.clipboard_html(html, "outlook.exe")
    assert "font-family:Calibri;font-size:12pt" in office and pic.as_uri() in office
    web = c.inserter.clipboard_html(html, "chrome.exe")
    data = re.search(r'src="data:image/png;base64,([^"]+)"', web).group(1)
    assert base64.b64decode(data) == original and 'width="800" height="450"' in web  # original quality

    c.settings.set("insert_base_font", "target")
    assert "Calibri" not in c.inserter.clipboard_html(html, "outlook.exe")
    c.settings.set("insert_images", "file")
    assert pic.as_uri() in c.inserter.clipboard_html(html, "chrome.exe")


def test_markdown_and_editor_templates_carry_their_font_into_the_fragment(qapp, home):
    import re

    c = _controller(qapp, home)
    c.settings.update({"editor_font_family": "Verdana", "editor_font_size": 13})
    (c.library.root / "Nota.md").write_text("# Titlu\n\nText **bold** și `cod`\n", encoding="utf-8")
    c.rescan(sync=True)
    r = c.renderer.render(c.library.get("Nota.md"), c.library.root)
    html, text, _ = c.inserter.prepare(r, plain=False)
    out = c.inserter.clipboard_html(html, "ms-teams.exe")
    frag = re.search(r"<!--StartFragment-->(.*)<!--EndFragment-->", out, re.S).group(1)
    assert "Verdana" in frag and "13pt" in frag  # the body font now lives inside the fragment
    assert "-qt-" not in frag and "bold" in frag
    assert "Consolas" in frag or "Courier New" in frag  # inline code: a font Office knows


def test_insert_mode_template_setting_and_shift(qapp, home):
    from autotemplates.core import formats

    c = _controller(qapp, home)
    lib = c.library.root
    (lib / "Implicit.html").write_text("<html><head></head><body><b>x</b></body></html>", encoding="utf-8")
    (lib / "Simplu.html").write_text(formats.write_meta("<html><head></head><body><b>x</b></body></html>",
                                                       {"mode": "plain"}), encoding="utf-8")
    (lib / "Bogat.html").write_text(formats.write_meta("<html><head></head><body><b>x</b></body></html>",
                                                      {"mode": "rich"}), encoding="utf-8")
    c.rescan(sync=True)
    c.settings.set("insert_mode", "rich")
    assert not c._plain("Implicit.html", False) and c._plain("Implicit.html", True)
    assert c._plain("Simplu.html", False) and not c._plain("Simplu.html", True)
    c.settings.set("insert_mode", "plain")
    assert c._plain("Implicit.html", False) and not c._plain("Implicit.html", True)
    assert not c._plain("Bogat.html", False) and c._plain("Bogat.html", True)


def test_backup_tab_restore_dialog_and_controller_restore(qapp, home, tmp_path):
    from autotemplates.core import backup as bk
    from autotemplates.ui.backup_dialog import RestoreDialog
    from autotemplates.ui.settings_dialog import SettingsDialog

    c = _controller(qapp, home)
    c.settings.set("backup_dir", str(tmp_path / "bk"))
    rel = c.library.templates[0].rel
    c.library.usage.set_favourite(rel, True)
    note = c.noteit
    note.title_edit.setText("Backup draft")
    note.editor.insertPlainText("keep me")
    note._write_draft()

    dlg = SettingsDialog(c)
    assert dlg.backup_auto.currentData() == "daily" and dlg.backup_keep.value() == 10
    assert not dlg.backup_templates.isChecked()
    dlg.reject()

    zpath = bk.create_backup(c.backup_source(), tmp_path / "bk")
    c.settings.set("theme", "light")
    c.library.usage.set_favourite(rel, False)
    note.title_edit.setText("Other")
    note._write_draft()

    info = bk.read_backup(zpath)
    rd = RestoreDialog(c, info)
    assert rd.cb_settings.isChecked() and rd.cb_usage.isChecked() and rd.cb_noteit.isChecked()
    assert not rd.cb_templates.isEnabled() and rd.library_choice is None
    result, safety = c.restore_backup(info, rd.options())
    assert safety.exists() and bk.SAFETY_TAG in safety.name
    assert c.settings.get("theme") == "dark"
    assert c.library.usage.favourite(rel)
    assert note.title_edit.text() == "Backup draft"
    assert "theme" in result.settings_changed


def test_help_window_sections_search_and_settings(qapp, home):
    from autotemplates import i18n
    from autotemplates.core import guide

    c = _controller(qapp, home)
    c.show_help("noteit")
    win = c._help
    assert win.isVisible() and win.list.count() == len(guide.SECTION_IDS)
    assert win.list.currentItem().data(257) == "noteit"  # Qt.UserRole + 1
    win.search.setText("restaureaza")  # no diacritics
    ids = [win.list.item(i).data(257) for i in range(win.list.count())]
    assert "backup" in ids and "picker" not in ids
    assert win.browser.extraSelections()  # the word is marked in the text
    win.search.setText("zzzz-nothing")
    assert win.list.count() == 0 and not win.none.isHidden()
    c.show_help("start")  # a section request clears the search
    assert win.search.text() == "" and c.settings.get("hotkey") in win.browser.toPlainText()
    i18n.set_language("en")
    try:
        c.show_help()
        assert win.windowTitle().endswith("User guide") and win.list.item(0).text() == "Quick start"
    finally:
        i18n.set_language("ro")
    win.close()


def test_f1_opens_the_guide_on_the_right_section(qapp, home, monkeypatch):
    c = _controller(qapp, home)
    opened = []
    monkeypatch.setattr(c, "show_help", lambda section=None, parent=None: opened.append(section))
    c.picker.help_requested.emit()
    assert c.editor.a_help.shortcut().toString() == "F1"
    c.editor.a_help.trigger()
    c.run_action({"action": "help", "section": "backup"})
    assert opened == ["picker", "editor", "backup"]
