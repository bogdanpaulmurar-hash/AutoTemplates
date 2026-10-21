from datetime import datetime
from pathlib import Path

import pytest

from autotemplates.core import formats, highlight, variables as tv
from autotemplates.core.library import Library, fold, safe_name
from autotemplates.core.settings import Settings
from autotemplates.platform import devpilot
from autotemplates.platform.hotkey import Hotkey, MOD_ALT, MOD_CONTROL

from conftest import make_docx


def test_hotkey_parse():
    hk = Hotkey.parse("ctrl+q")
    assert hk.modifiers == MOD_CONTROL and hk.vk == ord("Q") and hk.text == "Ctrl+Q"
    assert Hotkey.parse("Ctrl+Alt+Space").modifiers == MOD_CONTROL | MOD_ALT
    assert Hotkey.parse("F9").vk == 0x78
    with pytest.raises(ValueError):
        Hotkey.parse("Q")
    with pytest.raises(ValueError):
        Hotkey.parse("Hyper+Q")


def test_devpilot_env():
    env = {"DEVPILOT_MANAGED": "1", "DEVPILOT_SUPPRESS": "tray, autostart"}
    assert devpilot.owns("tray", env) and devpilot.owns("autostart", env)
    assert not devpilot.owns("keepawake", env)
    assert not devpilot.owns("tray", {"DEVPILOT_SUPPRESS": "tray"})  # not started by DevPilot


def test_settings_roundtrip(tmp_path):
    s = Settings(tmp_path / "settings.json")
    s.set("hotkey", "Ctrl+Alt+Q")
    again = Settings(tmp_path / "settings.json")
    assert again.get("hotkey") == "Ctrl+Alt+Q"
    (tmp_path / "settings.json").write_text('{"paste_delay_ms": "x", "unknown": 1}', encoding="utf-8")
    assert Settings(tmp_path / "settings.json").get("paste_delay_ms") == 60  # wrong type ignored


def test_variables():
    ctx = tv.VariableContext(now=datetime(2026, 10, 21, 9, 5), clipboard="a<b", answers={"Name": "Ana"},
                             language="ro")
    text = "Hi {input:Name}, {date} {time} {weekday} {date:%Y} {clipboard}{cursor}!"
    out = tv.expand(text, ctx)
    clean, back = tv.split_cursor(out)
    assert clean == "Hi Ana, 21.10.2026 09:05 miercuri 2026 a<b!"
    assert back == 1
    assert "a&lt;b" in tv.expand("{clipboard}", ctx, html=True)
    assert tv.expand("p { color: red; } {unknown}", ctx) == "p { color: red; } {unknown}"
    assert tv.input_prompts("{input:A} {input:B} {input:A}") == ["A", "B"]


def test_meta_roundtrip():
    html = "<html><head><title>x</title></head><body>hi</body></html>"
    out = formats.write_meta(html, {"tags": "a, b", "abbreviation": "ab\"c", "mode": "plain"})
    assert formats.read_meta(out) == {"tags": "a, b", "abbreviation": 'ab"c', "mode": "plain"}
    out2 = formats.write_meta(out, {"tags": "z"})
    assert formats.read_meta(out2) == {"tags": "z"}


def test_rtf_to_text():
    rtf = r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0 Hello \b world\b0\par Second\tab line \'e2\u259?\par}"
    assert formats.rtf_to_text(rtf) == "Hello world\nSecond\tline âă"


def test_docx(tmp_path):
    path = make_docx(tmp_path / "a.docx")
    res = formats.docx_to_html(path, tmp_path / "media")
    assert "<h1>Title</h1>" in res.html
    assert "<b>Bold red</b>" in res.html and "color:#FF0000" in res.html
    assert "<ul><li>Item one</li></ul>" in res.html
    assert "<td>" in res.html and "A1" in res.text and "Bold red normal" in res.text


def test_detect_language():
    assert highlight.detect_language('{"a": 1}') == "json"
    assert highlight.detect_language("def main():\n    return 1\n") == "python"
    assert highlight.detect_language("using System;\nnamespace X { public class A {} }") == "csharp"
    assert highlight.detect_language("SELECT a FROM t WHERE x = 1") == "sql"
    assert highlight.detect_language("<root><a/></root>") == "xml"
    assert highlight.detect_language("Just a sentence.") == ""


def test_code_html_is_inline_styled():
    html = highlight.code_html("x = 1  # c", "python")
    assert html.startswith("<pre style=") and "style=\"color" in html and "class=" not in html


def test_library_scan_search_and_cache(tmp_path):
    root = tmp_path / "lib"
    (root / "Email").mkdir(parents=True)
    (root / "Email" / "Răspuns întârziere.html").write_text(
        formats.write_meta("<html><head></head><body><p>Bună ziua</p></body></html>", {"tags": "client", "abbreviation": "rz"}),
        encoding="utf-8")
    (root / "Code").mkdir()
    (root / "Code" / "main.py").write_text("print('x')", encoding="utf-8")
    (root / "Code" / "main.assets").mkdir()
    (root / "Code" / "main.assets" / "img.png").write_bytes(b"x")
    (root / "~$lock.docx").write_bytes(b"")
    make_docx(root / "Doc.docx")
    lib = Library(root, tmp_path / "index.json", tmp_path / "usage.json")
    assert lib.scan()
    rels = {t.rel for t in lib.templates}
    assert rels == {"Email/Răspuns întârziere.html", "Code/main.py", "Doc.docx"}  # no assets, no lock files
    tpl = lib.get("Email/Răspuns întârziere.html")
    assert tpl.tags == ["client"] and tpl.abbreviation == "rz" and tpl.category == "Email"
    assert [t.rel for t in lib.search("raspuns")] == ["Email/Răspuns întârziere.html"]  # no diacritics needed
    assert lib.search("rz")[0].rel == tpl.rel
    assert lib.search("title")[0].rel == "Doc.docx"  # docx content is searchable
    assert lib.get("Code/main.py").language == "python"
    # cached: a second library reads the index and re-reads nothing
    lib2 = Library(root, tmp_path / "index.json", tmp_path / "usage.json")
    assert len(lib2.templates) == 3
    assert not lib2.scan()
    lib2.usage.set_favourite("Code/main.py", True)
    assert [t.rel for t in lib2.search("", category="★")] == ["Code/main.py"]
    assert lib2.search("")[0].rel == "Code/main.py"  # favourites first


def test_fold_and_safe_name():
    assert fold("Ștefan Țară") == "stefan tara"
    assert safe_name('a/b:c*?"') == "a-b-c---"
