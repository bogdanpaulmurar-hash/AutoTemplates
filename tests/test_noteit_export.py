"""NoteIT export helpers (no Qt, no Office needed)."""

import base64
import re
import xml.etree.ElementTree as ET

from autotemplates.core import noteit_export as ne

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

HIERARCHY = """<?xml version="1.0"?>
<one:Notebooks xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote">
  <one:Notebook name="Work" nickname="Work" ID="{NB1}">
    <one:Section name="Inbox" ID="{S1}"/>
    <one:SectionGroup name="Projects" ID="{G1}">
      <one:Section name="AutoTemplates" ID="{S2}"/>
    </one:SectionGroup>
    <one:SectionGroup name="OneNote_RecycleBin" ID="{RB}" isRecycleBin="true">
      <one:Section name="Deleted Pages" ID="{S3}"/>
    </one:SectionGroup>
  </one:Notebook>
  <one:Notebook name="Personal" nickname="Home" ID="{NB2}">
    <one:Section name="Ideas" ID="{S4}"/>
  </one:Notebook>
</one:Notebooks>"""


def _img(tmp_path, name="shot.png"):
    path = tmp_path / name
    path.write_bytes(PNG)
    return path


def test_local_path_variants(tmp_path):
    p = _img(tmp_path)
    assert ne.local_path(p.as_uri()) == p
    assert ne.local_path("shot.png", tmp_path) == p
    assert ne.local_path("https://example.com/a.png") is None
    assert ne.local_path("data:image/png;base64,AAAA") is None
    assert ne.local_path("cid:x") is None


def test_outlook_html_uses_cid_once_per_file(tmp_path):
    p = _img(tmp_path)
    markup = (f'<html><body><p>Hi</p><img src="{p.as_uri()}" width="10" />'
              f'<img src="{p.as_uri()}" /><img src="https://x/y.png" /><img src="file:///missing.png" /></body></html>')
    html, images = ne.outlook_html(markup)
    assert len(images) == 1 and images[0].path == p.resolve()
    assert html.count(f"cid:{images[0].cid}") == 2
    assert "https://x/y.png" in html and "file:///missing.png" in html
    assert 'width="10"' in html


def test_merge_into_body_keeps_signature():
    sig = '<html><head></head><body lang="ro"><p>--<br>Signature</p></body></html>'
    merged = ne.merge_into_body("<p>Note</p>", sig)
    assert merged.index("<p>Note</p>") < merged.index("Signature")
    assert merged.startswith('<html><head></head><body lang="ro"><p>Note</p>')
    assert ne.merge_into_body("<p>x</p>", "") == "<html><body><p>x</p></body></html>"


def test_parse_hierarchy_skips_recycle_bin():
    sections = ne.parse_hierarchy(HIERARCHY)
    assert [(s.path, s.id) for s in sections] == [
        ("Work / Inbox", "{S1}"),
        ("Work / Projects / AutoTemplates", "{S2}"),
        ("Home / Ideas", "{S4}"),
    ]
    assert ne.namespace_of(HIERARCHY) == ne.ONENOTE_NS_2013


def test_onenote_page_xml_keeps_order_and_embeds_pictures(tmp_path):
    p = _img(tmp_path)
    markup = (f'<html><head><style>p{{}}</style></head><body><p>Before</p>'
              f'<p><img src="{p.as_uri()}" width="40" height="20" /></p><p>After ]]> end</p></body></html>')
    xml = ne.onenote_page_xml("{PAGE}", "Title & <x>", markup)
    root = ET.fromstring(xml)  # well-formed
    ns = {"one": ne.ONENOTE_NS_2013}
    assert root.get("ID") == "{PAGE}"
    assert root.find("one:Title/one:OE/one:T", ns).text == "Title &amp; &lt;x&gt;"
    kinds = [("img" if oe.find("one:Image", ns) is not None else "html") for oe in root.find("one:Outline/one:OEChildren", ns)]
    assert kinds == ["html", "img", "html"]
    img = root.find(".//one:Image", ns)
    assert img.get("format") == "png"
    assert base64.b64decode(img.find("one:Data", ns).text) == PNG
    assert img.find("one:Size", ns).get("width") == "30.0"
    blocks = [d.text for d in root.iterfind(".//one:HTMLBlock/one:Data", ns)]
    assert "Before" in blocks[0] and "After ]]> end" in blocks[1]
    assert "<style>" not in "".join(blocks)


def test_onenote_page_xml_empty_note():
    xml = ne.onenote_page_xml("{P}", "", "<html><body><p></p></body></html>")
    root = ET.fromstring(xml)
    assert re.search(r"<one:OEChildren><one:OE><one:T>", xml)
    assert root.get("ID") == "{P}"


SECTION_PAGES = """<one:Section xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote" name="S" ID="{S}">
  <one:Page ID="{A}" name="A" pageLevel="1"/>
  <one:Page ID="{A1}" name="A1" pageLevel="2"/>
  <one:Page ID="{B}" name="B" pageLevel="1"/>
  <one:Page ID="{NEW}" name="New" pageLevel="1"/>
</one:Section>"""


def _order(xml):
    import xml.etree.ElementTree as ET
    return [(p.get("ID"), p.get("pageLevel")) for p in ET.fromstring(xml)]


def test_parse_hierarchy_reads_pages_with_levels():
    xml = ('<one:Notebooks xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote">'
           '<one:Notebook name="N" ID="{N}"><one:Section name="S" ID="{S}">'
           '<one:Page ID="{A}" name="A" pageLevel="1"/><one:Page ID="{A1}" name="A1" pageLevel="2"/>'
           '</one:Section></one:Notebook></one:Notebooks>')
    (section,) = ne.parse_hierarchy(xml)
    assert [(p.id, p.title, p.level) for p in section.pages] == [("{A}", "A", 1), ("{A1}", "A1", 2)]


def test_place_as_subpage_goes_after_the_parent_subtree():
    out = ne.place_as_subpage(SECTION_PAGES, "{NEW}", "{A}")
    assert _order(out) == [("{A}", "1"), ("{A1}", "2"), ("{NEW}", "2"), ("{B}", "1")]


def test_place_as_subpage_under_a_subpage_and_missing_ids():
    out = ne.place_as_subpage(SECTION_PAGES, "{NEW}", "{A1}")
    assert _order(out)[2] == ("{NEW}", "3")
    assert ne.place_as_subpage(SECTION_PAGES, "{NEW}", "{nope}") is None


def test_onenote_dialog_tree_selects_section_or_page(qapp):
    from autotemplates.ui.noteit import OneNoteSectionDialog

    sec = ne.OneNoteSection("N", "N / G / S", "{S}", [ne.OneNotePage("{A}", "A", 1), ne.OneNotePage("{A1}", "A1", 2)])
    dlg = OneNoteSectionDialog([sec], "{S}")
    assert dlg.selected() == (sec, None)
    page_item = dlg.tree.topLevelItem(0).child(0).child(0).child(0).child(0)  # N > G > S > A > A1
    assert page_item.text(0) == "A1"
    dlg.tree.setCurrentItem(page_item)
    assert dlg.selected()[1].id == "{A1}"
    dlg.filter.setText("zzz")
    assert dlg.selected() is None
