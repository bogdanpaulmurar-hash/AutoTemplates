"""NoteIT export helpers without Qt: Outlook HTML with inline (CID) pictures,
OneNote page XML and parsing of the OneNote notebook/section hierarchy.

Everything here is plain string/XML work so it can be tested on any OS; the
COM calls live in ``autotemplates.platform.office``.
"""

from __future__ import annotations

import base64
import hashlib
import html as html_lib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)
SRC_RE = re.compile(r"""(\bsrc\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
DIM_RE = re.compile(r"""\b(width|height)\s*=\s*["']?(\d+)""", re.I)
BODY_RE = re.compile(r"<body\b[^>]*>(.*)</body\s*>", re.I | re.S)

ONENOTE_NS_2013 = "http://schemas.microsoft.com/office/onenote/2013/onenote"
IMAGE_FORMATS = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".gif": "gif", ".bmp": "bmp", ".emf": "emf"}


# ------------------------------------------------------------------ helpers
def local_path(src: str, base: Path | None = None) -> Path | None:
    """Turns an <img src> into a local path (file:// URL or path relative to ``base``)."""
    src = html_lib.unescape(src.strip())
    if not src or re.match(r"^(https?|data|cid):", src, re.I):
        return None
    if src.lower().startswith("file:"):
        parsed = urlparse(src)
        raw = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":  # UNC share
            raw = f"//{parsed.netloc}{raw}"
        elif re.match(r"^/[A-Za-z]:", raw):  # /C:/... -> C:/...
            raw = raw[1:]
        path = Path(raw)
    else:
        path = Path(unquote(src))
        if not path.is_absolute() and base is not None:
            path = base / path
    return path


def body_of(markup: str) -> str:
    """Inner <body> of a full HTML document (Qt's toHtml), or the markup itself."""
    m = BODY_RE.search(markup)
    return m.group(1).strip() if m else markup.strip()


# ------------------------------------------------------------------ Outlook
@dataclass
class InlineImage:
    path: Path
    cid: str


def outlook_html(markup: str, base: Path | None = None) -> tuple[str, list[InlineImage]]:
    """Replaces local picture sources with ``cid:`` references for an Outlook mail.

    Returns the new markup and the pictures to attach (each once, even when it
    appears several times). Missing files and web/data pictures are left alone.
    """
    images: dict[Path, InlineImage] = {}

    def repl_tag(tag_match: re.Match) -> str:
        tag = tag_match.group(0)

        def repl_src(m: re.Match) -> str:
            path = local_path(m.group(3), base)
            if path is None or not path.is_file():
                return m.group(0)
            key = path.resolve()
            if key not in images:
                digest = hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:10]
                images[key] = InlineImage(key, f"noteit-{len(images) + 1}-{digest}{key.suffix.lower()}")
            return f"{m.group(1)}{m.group(2)}cid:{images[key].cid}{m.group(2)}"

        return SRC_RE.sub(repl_src, tag, count=1)

    return IMG_TAG_RE.sub(repl_tag, markup), list(images.values())


def merge_into_body(body_html: str, existing: str) -> str:
    """Puts ``body_html`` at the top of an Outlook mail body (keeps the signature)."""
    if not existing.strip():
        return f"<html><body>{body_html}</body></html>"
    m = re.search(r"<body\b[^>]*>", existing, re.I)
    if not m:
        return body_html + existing
    return existing[: m.end()] + body_html + existing[m.end():]


# ------------------------------------------------------------------ OneNote
@dataclass
class OneNotePage:
    id: str
    title: str
    level: int  # 1 = page, 2 = subpage, 3 = sub-subpage


@dataclass
class OneNoteSection:
    notebook: str
    path: str  # "Notebook / Group / Section"
    id: str
    pages: list[OneNotePage] = field(default_factory=list)  # empty when read with hsSections


def parse_hierarchy(xml_text: str) -> list[OneNoteSection]:
    """Sections from ``GetHierarchy(..., hsSections)``; recycle bins are skipped."""
    root = ET.fromstring(xml_text)
    out: list[OneNoteSection] = []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def skip(el: ET.Element) -> bool:
        return el.get("isRecycleBin") == "true" or el.get("isInRecycleBin") == "true"

    def walk(el: ET.Element, notebook: str, trail: list[str]) -> None:
        for child in el:
            kind = local(child.tag)
            if skip(child):
                continue
            name = child.get("name") or child.get("nickname") or "?"
            if kind == "Section" and child.get("ID"):
                pages = [OneNotePage(p.get("ID"), p.get("name") or "?", _level(p))
                         for p in child if local(p.tag) == "Page" and p.get("ID") and not skip(p)]
                out.append(OneNoteSection(notebook, " / ".join(trail + [name]), child.get("ID"), pages))
            elif kind == "SectionGroup":
                walk(child, notebook, trail + [name])

    for nb in root:
        if local(nb.tag) != "Notebook":
            continue
        name = nb.get("nickname") or nb.get("name") or "?"
        walk(nb, name, [name])
    return out


def _level(page: ET.Element) -> int:
    try:
        return min(max(int(page.get("pageLevel") or 1), 1), 3)
    except ValueError:
        return 1


def place_as_subpage(section_xml: str, page_id: str, parent_id: str) -> str | None:
    """Section XML (``GetHierarchy(section, hsPages)``) with ``page_id`` moved right after the
    subtree of ``parent_id`` and one level deeper, for ``UpdateHierarchy``. None if either page is missing.
    """
    root = ET.fromstring(section_xml)
    pages = [el for el in root if el.tag.rsplit("}", 1)[-1] == "Page"]
    by_id = {el.get("ID"): el for el in pages}
    if page_id not in by_id or parent_id not in by_id or page_id == parent_id:
        return None
    new, parent = by_id[page_id], by_id[parent_id]
    root.remove(new)
    pages.remove(new)
    level = _level(parent)
    end = pages.index(parent)
    while end + 1 < len(pages) and _level(pages[end + 1]) > level:
        end += 1
    new.set("pageLevel", str(min(level + 1, 3)))
    root.insert(list(root).index(pages[end]) + 1, new)
    ET.register_namespace("one", root.tag[1:].split("}")[0] if root.tag.startswith("{") else ONENOTE_NS_2013)
    return ET.tostring(root, encoding="unicode")


def namespace_of(xml_text: str) -> str:
    m = re.search(r'xmlns:one="([^"]+)"', xml_text)
    return m.group(1) if m else ONENOTE_NS_2013


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def onenote_page_xml(page_id: str, title: str, markup: str, base: Path | None = None,
                     ns: str = ONENOTE_NS_2013) -> str:
    """XML for ``UpdatePageContent``: title + content, pictures embedded as base64.

    Text runs go in ``HTMLBlock`` elements (OneNote converts the HTML), local
    pictures become ``Image`` elements in document order, so the note keeps its
    layout and does not depend on files in the local cache.
    """
    body = body_of(markup)
    parts: list[str] = []
    pos = 0
    for m in IMG_TAG_RE.finditer(body):
        parts.append(_html_oe(body[pos:m.start()]))
        parts.append(_image_oe(m.group(0), base) or _html_oe(m.group(0)))
        pos = m.end()
    parts.append(_html_oe(body[pos:]))
    children = "".join(p for p in parts if p)
    if not children:
        children = "<one:OE><one:T><![CDATA[]]></one:T></one:OE>"
    return (
        f'<?xml version="1.0"?><one:Page xmlns:one="{ns}" ID="{html_lib.escape(page_id, quote=True)}">'
        f"<one:Title><one:OE><one:T>{_cdata(html_lib.escape(title))}</one:T></one:OE></one:Title>"
        f"<one:Outline><one:OEChildren>{children}</one:OEChildren></one:Outline></one:Page>"
    )


def _html_oe(fragment: str) -> str:
    if not re.sub(r"<[^>]+>|&nbsp;|\s", "", fragment):
        return ""
    return f"<one:OE><one:HTMLBlock><one:Data>{_cdata('<html><body>' + fragment + '</body></html>')}</one:Data></one:HTMLBlock></one:OE>"


def _image_oe(tag: str, base: Path | None) -> str:
    m = SRC_RE.search(tag)
    path = local_path(m.group(3), base) if m else None
    if path is None or not path.is_file():
        return ""
    fmt = IMAGE_FORMATS.get(path.suffix.lower())
    if fmt is None:
        return ""
    try:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    dims = {k.lower(): int(v) for k, v in DIM_RE.findall(tag)}
    size = ""
    if dims.get("width") and dims.get("height"):
        # OneNote sizes are in points; Qt widths are pixels at 96 dpi.
        size = f'<one:Size width="{dims["width"] * 0.75:.1f}" height="{dims["height"] * 0.75:.1f}" isSetByUser="true"/>'
    return f'<one:OE><one:Image format="{fmt}">{size}<one:Data>{data}</one:Data></one:Image></one:OE>'


__all__ = ["InlineImage", "OneNotePage", "OneNoteSection", "place_as_subpage", "body_of", "local_path", "merge_into_body", "namespace_of",
           "onenote_page_xml", "outlook_html", "parse_hierarchy"]
