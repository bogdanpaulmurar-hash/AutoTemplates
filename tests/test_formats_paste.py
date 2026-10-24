"""Formatting kept on paste: CF_HTML fragment, pictures, RTF and DOCX conversion (no Qt)."""

import base64
import re
from pathlib import Path

import pytest

from autotemplates.core import clipboard_html as ch
from autotemplates.core import formats
from conftest import SAMPLE_RTF, make_docx, make_styled_docx

QT_DOC = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN"><html><head><meta name="qrichtext" content="1" />
<style type="text/css">
p, li { white-space: pre-wrap; }
li.unchecked::marker { content: "\\2610"; }
</style></head><body style=" font-family:'Segoe UI'; font-size:11pt; font-weight:400; font-style:normal;">
<p style=" margin-top:0px; margin-bottom:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-weight:700;">Bold</span>
<span style=" font-family:'monospace';">code</span></p></body></html>"""


def fragment(doc: str) -> str:
    m = re.search(r"<!--StartFragment-->(.*)<!--EndFragment-->", doc, re.S)
    assert m and doc.count("<!--StartFragment-->") == 1
    return m.group(1)


def test_fragment_carries_body_and_head_styles():
    frag = fragment(ch.fragment_html(QT_DOC))
    assert frag.startswith("<div style=\"font-family:'Segoe UI';font-size:11pt\">")
    assert "white-space:pre-wrap" in frag  # from <head><style>
    assert "-qt-" not in frag and "font-weight:400" not in frag and "marker" not in frag
    assert '<span style="font-weight:bold">Bold</span>' in frag
    assert "font-family:Consolas,'Courier New',monospace" in frag


def test_fragment_base_font_setting():
    editor = fragment(ch.fragment_html("<p>x <span style=\"font-family:Arial\">y</span></p>",
                                       base_font="Segoe UI", base_size_pt=11))
    assert editor.startswith("<div style=\"font-family:'Segoe UI';font-size:11pt\">")
    target = fragment(ch.fragment_html(QT_DOC, base_font="Segoe UI", base_size_pt=11, keep_body_font=False))
    assert not target.startswith("<div")  # the target app's font
    assert "font-weight:bold" in target  # formatting of words is kept either way
    own = fragment(ch.fragment_html(QT_DOC, base_font="Calibri", base_size_pt=14))
    assert "Segoe UI" in own and "Calibri" not in own  # the template's own font wins


def test_fragment_markers_are_not_doubled():
    doc = ch.fragment_html("<html><body><!--StartFragment--><b>x</b><!--EndFragment--></body></html>")
    assert fragment(doc) == "<b>x</b>"
    assert ch.fragment_html("") == ""


def test_image_mode_for():
    assert ch.image_mode_for("OUTLOOK.EXE") == "file"
    assert ch.image_mode_for("winword.exe") == "file"
    assert ch.image_mode_for("ms-teams.exe") == "data"
    assert ch.image_mode_for("chrome.exe") == "data"
    assert ch.image_mode_for("") == "file"
    assert ch.image_mode_for("winword.exe", "data") == "data"
    assert ch.image_mode_for("chrome.exe", "file") == "file"


def test_pictures_keep_their_original_bytes(tmp_path):
    data = bytes(range(256)) * 50
    pic = tmp_path / "shot 1.png"
    pic.write_bytes(data)
    markup = f'<p><img src="{pic.as_uri()}" width="1920" height="1080"/></p>'
    out = ch.set_image_sources(markup, "data")
    m = re.search(r'src="data:image/png;base64,([^"]+)"', out)
    assert m and base64.b64decode(m.group(1)) == data  # identical: no recompression, no scaling
    assert 'width="1920" height="1080"' in out
    assert ch.set_image_sources(markup, "file") == markup
    assert ch.set_image_sources(markup, "data", max_bytes=10) == markup  # too big: stays a file, never shrunk
    missing = '<img src="file:///nowhere/x.png"/>'
    assert ch.set_image_sources(missing, "data") == missing


def test_local_path_from_file_uri():
    assert ch._local_path("file:///C:/My%20Drive/a.png").as_posix() == "C:/My Drive/a.png"
    assert ch._local_path("file://server/share/a.png").as_posix() == "//server/share/a.png"
    assert ch._local_path("https://x/a.png") is None


def test_rtf_to_html_keeps_formatting():
    html = formats.rtf_to_html(SAMPLE_RTF)
    assert '<p style="margin:0;text-align:center">' in html
    assert "<b>Titlu</b>" in html and "font-size:16pt" in html
    assert "<i>italic</i>" in html and "<u>sub</u>" in html and "<s>t</s>" in html
    assert "color:#ff0000" in html and "roşie" in html  # \ansicpg1250
    assert "font-family:'Consolas'" in html and "font-family:'Calibri'" in html
    assert "<sup>2</sup>" in html
    assert "•&emsp;" in html and "Symbol" not in html
    assert '<a href="https://example.com">' in html and "<u>link</u>" in html
    text = formats.rtf_to_text(SAMPLE_RTF)
    assert "roşie" in text and "Titlu" in text


def test_docx_old_shape_still_works(tmp_path):
    res = formats.docx_to_html(make_docx(tmp_path / "a.docx"), tmp_path / "media")
    assert "Title</h1>" in res.html
    assert "<b>Bold red</b>" in res.html and "color:#FF0000" in res.html
    assert re.search(r"<ul[^>]*><li[^>]*>Item one</li></ul>", res.html)
    assert "<td" in res.html and "A1" in res.text and "Bold red normal" in res.text


def test_docx_styles_theme_numbering_and_pictures(tmp_path):
    image = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 20
    res = formats.docx_to_html(make_styled_docx(tmp_path / "s.docx", image), tmp_path / "media")
    html = res.html
    # heading style (basedOn Normal) with the theme's major font, colour and size
    assert re.search(r"<h1 style=\"margin-top:12pt;margin-bottom:0pt[^\"]*\"><span style=\"font-family:'Calibri Light';"
                     r"font-size:16pt;color:#2F5496;font-weight:normal", html)
    # every run gets the document font: no Times New Roman fallback in Word/Outlook
    assert "<span style=\"font-family:'Calibri';font-size:11pt\">Normal text </span>" in html
    assert "<b>strong</b>" in html and "hidden" not in html  # character style; hidden text skipped
    assert "text-align:center" in html and "margin-bottom:8pt" in html and "line-height:115%" in html
    # numbered list with a nested lettered level, then a bullet list
    assert re.search(r"<ol style=\"[^\"]*\"><li[^>]*>.*One</span><ol type=\"a\"[^>]*><li[^>]*>.*One\.a.*</li></ol></li>"
                     r"<li[^>]*>.*Two.*</li></ol><ul[^>]*><li[^>]*>.*Bullet", html)
    # picture: original bytes, size as in the document (EMU -> px)
    assert 'width="200" height="100"' in html
    assert res.images and res.images[0].read_bytes() == image
    assert "Title" in res.text and "One.a" in res.text


def test_office_paste_only_in_the_document_body():
    from autotemplates.platform import office

    with pytest.raises(office.OfficeUnavailable):
        office.paste_original("notepad.exe", "x", "_WwG")
    with pytest.raises(office.OfficeUnavailable):
        office.paste_original("outlook.exe", "Untitled - Message", "RichEdit20WPT")  # caret in Subject/To
    assert office._same_window("Doc1", "Doc1 - Word")
    assert not office._same_window("Doc2", "Doc1 - Word")
    assert office._same_window("x", "")
