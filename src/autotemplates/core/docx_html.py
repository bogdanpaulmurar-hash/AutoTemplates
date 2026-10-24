"""Word documents (.docx) as HTML that pastes with the look it has in Word.

Standard library only. Besides the direct formatting of each run it applies what
Word applies: document defaults, paragraph and character styles (with ``basedOn``),
theme fonts, list numbering (bullets vs numbers, nested levels), paragraph spacing,
indents and alignment. Every run gets its font and size explicitly, so Word and
Outlook do not fall back to "Normal (Web)" / Times New Roman.

Pictures are extracted unchanged (original bytes) and keep the size they have in
the document.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A_BLIP = A_NS + "blip"
EMU_PER_PX = 9525
HIGHLIGHT = {"yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff", "blue": "#0000ff",
             "red": "#ff0000", "darkBlue": "#000080", "darkCyan": "#008080", "darkGreen": "#008000",
             "darkMagenta": "#800080", "darkRed": "#800000", "darkYellow": "#808000", "darkGray": "#808080",
             "lightGray": "#c0c0c0", "black": "#000000", "white": "#ffffff"}
OL_TYPES = {"decimal": "1", "decimalZero": "1", "lowerLetter": "a", "upperLetter": "A", "lowerRoman": "i",
            "upperRoman": "I"}


@dataclass
class DocxResult:
    html: str
    text: str
    images: list[Path] = field(default_factory=list)


def _val(el: ET.Element | None, attr: str = "val", default: str | None = None) -> str | None:
    if el is None:
        return default
    return el.get(W + attr, default)


def _on(rpr: ET.Element, name: str) -> bool | None:
    el = rpr.find(W + name)
    if el is None:
        return None
    return el.get(W + "val", "true") not in ("0", "false", "none", "off")


def _twips_pt(value: str | None) -> float | None:
    try:
        return int(value) / 20 if value is not None else None
    except ValueError:
        return None


class _Context:
    """Styles, theme fonts and numbering of one document."""

    def __init__(self, zf: zipfile.ZipFile) -> None:
        self.theme_fonts = self._theme(zf)
        self.styles: dict[str, ET.Element] = {}
        self.default_style: dict[str, str] = {}
        self.defaults_r: dict = {}
        self.defaults_p: dict = {}
        self._resolved: dict[str, tuple[dict, dict]] = {}
        try:
            root = ET.fromstring(zf.read("word/styles.xml"))
        except (KeyError, ET.ParseError):
            root = None
        if root is not None:
            dd = root.find(W + "docDefaults")
            if dd is not None:
                rpr = dd.find(f"{W}rPrDefault/{W}rPr")
                ppr = dd.find(f"{W}pPrDefault/{W}pPr")
                self.defaults_r = self.run_props(rpr) if rpr is not None else {}
                self.defaults_p = self.para_props(ppr) if ppr is not None else {}
            for st in root.findall(W + "style"):
                sid = st.get(W + "styleId", "")
                self.styles[sid] = st
                if st.get(W + "default") in ("1", "true"):
                    self.default_style[st.get(W + "type", "")] = sid
        self.num_formats = self._numbering(zf)

    # -- parts
    @staticmethod
    def _theme(zf: zipfile.ZipFile) -> dict[str, str]:
        fonts: dict[str, str] = {}
        try:
            root = ET.fromstring(zf.read("word/theme/theme1.xml"))
        except (KeyError, ET.ParseError):
            return fonts
        for kind in ("major", "minor"):
            latin = root.find(f".//{A_NS}{kind}Font/{A_NS}latin")
            if latin is not None and latin.get("typeface"):
                fonts[kind] = latin.get("typeface")
        return fonts

    @staticmethod
    def _numbering(zf: zipfile.ZipFile) -> dict[tuple[str, str], tuple[str, str]]:
        """(numId, ilvl) → (numFmt, start)."""
        try:
            root = ET.fromstring(zf.read("word/numbering.xml"))
        except (KeyError, ET.ParseError):
            return {}
        abstract: dict[str, dict[str, tuple[str, str]]] = {}
        for an in root.findall(W + "abstractNum"):
            levels = {}
            for lvl in an.findall(W + "lvl"):
                levels[lvl.get(W + "ilvl", "0")] = (_val(lvl.find(W + "numFmt"), default="bullet") or "bullet",
                                                    _val(lvl.find(W + "start"), default="1") or "1")
            abstract[an.get(W + "abstractNumId", "")] = levels
        out: dict[tuple[str, str], tuple[str, str]] = {}
        for num in root.findall(W + "num"):
            aid = _val(num.find(W + "abstractNumId"), default="")
            for ilvl, fmt in abstract.get(aid or "", {}).items():
                out[(num.get(W + "numId", ""), ilvl)] = fmt
        return out

    # -- properties
    def run_props(self, rpr: ET.Element) -> dict:
        p: dict = {}
        for name in ("b", "i", "strike", "dstrike", "vanish", "caps", "smallCaps"):
            v = _on(rpr, name)
            if v is not None:
                p["strike" if name == "dstrike" and v else name] = v
        u = rpr.find(W + "u")
        if u is not None:
            p["u"] = (u.get(W + "val", "single") or "single") != "none"
        color = _val(rpr.find(W + "color"))
        if color and color.lower() != "auto":
            p["color"] = f"#{color}"
        hl = _val(rpr.find(W + "highlight"))
        if hl in HIGHLIGHT:
            p["bg"] = HIGHLIGHT[hl]
        elif hl == "none":
            p["bg"] = ""
        shd = rpr.find(W + "shd")
        if shd is not None and (shd.get(W + "fill") or "auto") not in ("auto", "") and "bg" not in p:
            p["bg"] = f"#{shd.get(W + 'fill')}"
        sz = _val(rpr.find(W + "sz"))
        if sz and sz.isdigit():
            p["size"] = int(sz) / 2
        fonts = rpr.find(W + "rFonts")
        if fonts is not None:
            face = fonts.get(W + "ascii") or fonts.get(W + "hAnsi")
            theme = fonts.get(W + "asciiTheme") or fonts.get(W + "hAnsiTheme")
            if theme:
                face = self.theme_fonts.get("major" if theme.startswith("major") else "minor", face)
            if face:
                p["font"] = face
        va = _val(rpr.find(W + "vertAlign"))
        if va in ("superscript", "subscript", "baseline"):
            p["va"] = va
        return p

    def para_props(self, ppr: ET.Element) -> dict:
        p: dict = {}
        jc = _val(ppr.find(W + "jc"))
        if jc:
            p["align"] = {"both": "justify", "end": "right", "start": "left", "distribute": "justify"}.get(jc, jc)
        sp = ppr.find(W + "spacing")
        if sp is not None:
            for attr, key in (("before", "before"), ("after", "after")):
                v = _twips_pt(sp.get(W + attr))
                if v is not None and sp.get(W + attr + "Autospacing") not in ("1", "true"):
                    p[key] = v
            line, rule = sp.get(W + "line"), sp.get(W + "lineRule", "auto")
            if line and line.lstrip("-").isdigit():
                p["line"] = f"{int(line) / 240 * 100:.0f}%" if rule == "auto" else f"{int(line) / 20:g}pt"
        ind = ppr.find(W + "ind")
        if ind is not None:
            left = _twips_pt(ind.get(W + "left") or ind.get(W + "start"))
            if left is not None:
                p["left"] = left
            first, hanging = _twips_pt(ind.get(W + "firstLine")), _twips_pt(ind.get(W + "hanging"))
            if hanging is not None:
                p["first"] = -hanging
            elif first is not None:
                p["first"] = first
        num = ppr.find(W + "numPr")
        if num is not None:
            num_id, ilvl = _val(num.find(W + "numId")), _val(num.find(W + "ilvl"))
            if num_id is not None:
                p["numId"] = num_id
            if ilvl is not None:
                p["ilvl"] = ilvl
        return p

    def style(self, sid: str, _seen: frozenset = frozenset()) -> tuple[dict, dict]:
        """(run props, paragraph props) of a style, ``basedOn`` chain included."""
        if sid in self._resolved:
            return self._resolved[sid]
        st = self.styles.get(sid)
        if st is None or sid in _seen:
            return {}, {}
        base_id = _val(st.find(W + "basedOn"))
        r, p = self.style(base_id, _seen | {sid}) if base_id else ({}, {})
        rpr, ppr = st.find(W + "rPr"), st.find(W + "pPr")
        r = {**r, **(self.run_props(rpr) if rpr is not None else {})}
        p = {**p, **(self.para_props(ppr) if ppr is not None else {})}
        self._resolved[sid] = (r, p)
        return r, p

    def style_name(self, sid: str) -> str:
        st = self.styles.get(sid)
        name = _val(st.find(W + "name")) if st is not None else None
        return (name or sid or "").lower()


def _fmt_pt(v: float) -> str:
    return f"{v:g}pt"


def _run_style(props: dict, heading: bool) -> tuple[str, list[str]]:
    styles: list[str] = []
    if props.get("font"):
        styles.append(f"font-family:'{props['font']}'")
    if props.get("size"):
        styles.append(f"font-size:{_fmt_pt(props['size'])}")
    if props.get("color"):
        styles.append(f"color:{props['color']}")
    if props.get("bg"):
        styles.append(f"background-color:{props['bg']}")
    if props.get("caps"):
        styles.append("text-transform:uppercase")
    elif props.get("smallCaps"):
        styles.append("font-variant:small-caps")
    if heading and not props.get("b"):
        styles.append("font-weight:normal")
    if heading and not props.get("i"):
        styles.append("font-style:normal")
    wraps = [t for key, t in (("b", "b"), ("i", "i"), ("u", "u"), ("strike", "s")) if props.get(key)]
    if props.get("va") == "superscript":
        wraps.append("sup")
    elif props.get("va") == "subscript":
        wraps.append("sub")
    return ";".join(styles), wraps


def docx_to_html(path: Path, media_dir: Path | None = None) -> DocxResult:
    """HTML (inline styles only) and plain text of a .docx; pictures go to ``media_dir``."""
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        rels: dict[str, str] = {}
        try:
            for rel in ET.fromstring(zf.read("word/_rels/document.xml.rels")):
                rels[rel.get("Id", "")] = rel.get("Target", "")
        except KeyError:
            pass
        ctx = _Context(zf)
        images: list[Path] = []
        image_src: dict[str, str] = {}
        text_parts: list[str] = []

        def picture(rid: str) -> str:
            if rid in image_src:
                return image_src[rid]
            target = rels.get(rid, "")
            src = ""
            if target and media_dir is not None:
                name = target.lstrip("/") if target.startswith(("word/", "/word/")) else "word/" + target
                try:
                    data = zf.read(name)
                except KeyError:
                    data = b""
                if data:  # the original bytes: no re-encoding, no scaling
                    media_dir.mkdir(parents=True, exist_ok=True)
                    out = media_dir / (hashlib.sha1(data).hexdigest()[:12] + Path(target).suffix.lower())
                    if not out.exists():
                        out.write_bytes(data)
                    images.append(out)
                    src = out.as_uri()
            image_src[rid] = src
            return src

        def drawing_html(el: ET.Element) -> str:
            out = []
            extent = next(el.iter(WP_NS + "extent"), None)
            size = ""
            if extent is not None:
                try:
                    w = round(int(extent.get("cx", "0")) / EMU_PER_PX)
                    h = round(int(extent.get("cy", "0")) / EMU_PER_PX)
                    if w > 0 and h > 0:
                        size = f' width="{w}" height="{h}"'
                except ValueError:
                    pass
            for blip in el.iter(A_BLIP):
                src = picture(blip.get(R_NS + "embed", ""))
                if src:
                    out.append(f'<img src="{src}"{size}/>')
                    text_parts.append("[image]")
            return "".join(out)

        def run_html(run: ET.Element, para_r: dict, heading: bool) -> str:
            rpr = run.find(W + "rPr")
            props = dict(para_r)
            if rpr is not None:
                rstyle = _val(rpr.find(W + "rStyle"))
                if rstyle:
                    props.update(ctx.style(rstyle)[0])
                props.update(ctx.run_props(rpr))
            if props.get("vanish"):
                return ""
            pieces: list[str] = []
            for child in run:
                tag = child.tag
                if tag == W + "t":
                    pieces.append(htmllib.escape(child.text or ""))
                    text_parts.append(child.text or "")
                elif tag == W + "tab":
                    pieces.append("&emsp;")
                    text_parts.append("\t")
                elif tag in (W + "br", W + "cr"):
                    pieces.append("<br/>")
                    text_parts.append("\n")
                elif tag == W + "noBreakHyphen":
                    pieces.append("&#8209;")
                elif tag == W + "drawing" or tag.endswith("}pict"):
                    pieces.append(drawing_html(child))
            body = "".join(pieces)
            if not body:
                return ""
            style, wraps = _run_style(props, heading)
            for t in wraps:
                body = f"<{t}>{body}</{t}>"
            return f'<span style="{style}">{body}</span>' if style else body

        def inline_html(parent: ET.Element, para_r: dict, heading: bool) -> str:
            out = []
            for child in parent:
                if child.tag == W + "r":
                    out.append(run_html(child, para_r, heading))
                elif child.tag == W + "hyperlink":
                    target = rels.get(child.get(R_NS + "id", ""), "")
                    inner = inline_html(child, para_r, heading)
                    out.append(f'<a href="{htmllib.escape(target, quote=True)}">{inner}</a>' if target else inner)
                elif child.tag in (W + "ins", W + "smartTag", W + "sdt", W + "sdtContent", W + "fldSimple",
                                   W + "customXml"):
                    out.append(inline_html(child, para_r, heading))
            return "".join(out)

        def paragraph(p: ET.Element) -> tuple[str, str | None, int, str]:
            """(html of the paragraph or list item body, list tag, level, ol type)."""
            ppr = p.find(W + "pPr")
            sid = _val(ppr.find(W + "pStyle")) if ppr is not None else None
            sid = sid or ctx.default_style.get("paragraph", "")
            style_r, style_p = ctx.style(sid) if sid else ({}, {})
            char_default = ctx.default_style.get("character")
            base_r = {**ctx.defaults_r, **(ctx.style(char_default)[0] if char_default else {}), **style_r}
            pp = {**ctx.defaults_p, **style_p, **(ctx.para_props(ppr) if ppr is not None else {})}
            name = ctx.style_name(sid)
            tag = "p"
            m = re.match(r"(?:heading|titlu)\s*([1-6])$", name)
            if m:
                tag = f"h{m.group(1)}"
            elif name == "title":
                tag = "h1"
            heading = tag != "p" and sid in ctx.styles  # undefined style: leave Word's own heading look
            content = inline_html(p, base_r, heading) or "&nbsp;"
            text_parts.append("\n")

            list_tag, level, ol_type = None, 0, ""
            num_id = pp.get("numId")
            if num_id and num_id != "0":
                ilvl = pp.get("ilvl", "0")
                fmt, _start = ctx.num_formats.get((num_id, ilvl), ("bullet", "1"))
                if fmt != "none":
                    list_tag = "ul" if fmt == "bullet" else "ol"
                    ol_type = OL_TYPES.get(fmt, "1") if list_tag == "ol" else ""
                    level = int(ilvl) if ilvl.isdigit() else 0
            styles = [f"margin-top:{_fmt_pt(pp.get('before', 0))}", f"margin-bottom:{_fmt_pt(pp.get('after', 0))}"]
            if not list_tag:
                styles.append(f"margin-left:{_fmt_pt(pp.get('left', 0))}")
                if pp.get("first"):
                    styles.append(f"text-indent:{_fmt_pt(pp['first'])}")
            if pp.get("align") in ("center", "right", "justify"):
                styles.append(f"text-align:{pp['align']}")
            if pp.get("line"):
                styles.append(f"line-height:{pp['line']}")
            style = ";".join(styles)
            if list_tag:
                return f'<li style="{style}">{content}', list_tag, level, ol_type
            return f'<{tag} style="{style}">{content}</{tag}>', None, 0, ""

        def block_html(parent: ET.Element) -> str:
            out: list[str] = []
            stack: list[list] = []  # [tag, li_open] per nesting level

            def close_to(depth: int) -> None:
                while len(stack) > depth:
                    tag, li_open = stack.pop()
                    out.append(("</li>" if li_open else "") + f"</{tag}>")

            for child in parent:
                if child.tag == W + "p":
                    markup, list_tag, level, ol_type = paragraph(child)
                    if list_tag is None:
                        close_to(0)
                        out.append(markup)
                        continue
                    close_to(level + 1)
                    if len(stack) == level + 1 and stack[-1][0] != list_tag:
                        close_to(level)
                    while len(stack) < level + 1:
                        type_attr = f' type="{ol_type}"' if list_tag == "ol" and ol_type not in ("", "1") else ""
                        out.append(f'<{list_tag}{type_attr} style="margin-top:0;margin-bottom:0">')
                        stack.append([list_tag, False])
                    if stack[-1][1]:
                        out.append("</li>")
                    out.append(markup)
                    stack[-1][1] = True
                    continue
                close_to(0)
                if child.tag == W + "tbl":
                    rows = []
                    for tr in child.findall(W + "tr"):
                        cells = "".join(
                            '<td style="border:1px solid #808080;padding:2pt 5pt;vertical-align:top">'
                            f"{block_html(tc)}</td>" for tc in tr.findall(W + "tc"))
                        rows.append(f"<tr>{cells}</tr>")
                        text_parts.append("\n")
                    out.append('<table style="border-collapse:collapse" cellspacing="0">' + "".join(rows) + "</table>")
                elif child.tag == W + "sdt":
                    content = child.find(W + "sdtContent")
                    if content is not None:
                        out.append(block_html(content))
            close_to(0)
            return "".join(out)

        body = root.find(W + "body")
        markup = block_html(body) if body is not None else ""
    text = re.sub(r"\n{3,}", "\n\n", "".join(text_parts)).strip()
    return DocxResult(f"<html><body>{markup}</body></html>", text, images)


def docx_text(path: Path) -> str:
    return docx_to_html(path, None).text
