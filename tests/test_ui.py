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
