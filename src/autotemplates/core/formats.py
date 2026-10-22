"""File types a template can be, and Qt-free readers for them.

* ``rich``     .html/.htm  (templates made in the editor; metadata in ``<meta>``)
* ``markdown`` .md/.markdown
* ``text``     .txt/.log/.csv
* ``code``     source files, highlighted with Pygments when inserted
* ``docx``     Word documents, converted to HTML with the standard library
* ``rtf``      Rich Text, read as plain text
* ``image``    png/jpg/gif/bmp/webp, inserted as a picture
"""

from __future__ import annotations

import hashlib
import html as htmllib
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

RICH_EXT = {".html", ".htm"}
MARKDOWN_EXT = {".md", ".markdown"}
TEXT_EXT = {".txt", ".text", ".log", ".csv", ".tsv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
# extension -> Pygments lexer alias
CODE_EXT = {
    ".py": "python", ".pyw": "python", ".json": "json", ".cs": "csharp", ".js": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx", ".sql": "sql", ".xml": "xml", ".xaml": "xml", ".csproj": "xml",
    ".yaml": "yaml", ".yml": "yaml", ".ps1": "powershell", ".psm1": "powershell", ".bat": "batch", ".cmd": "batch",
    ".sh": "bash", ".css": "css", ".scss": "scss", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".java": "java", ".kt": "kotlin", ".go": "go", ".rs": "rust", ".php": "php", ".rb": "ruby", ".vb": "vbnet",
    ".ini": "ini", ".cfg": "ini", ".toml": "toml", ".gs": "javascript", ".r": "r", ".swift": "swift",
    ".dockerfile": "docker", ".vue": "html", ".razor": "razor", ".graphql": "graphql", ".lua": "lua",
}
LANGUAGE_NAMES = {
    "python": "Python", "json": "JSON", "csharp": "C#", "javascript": "JavaScript", "typescript": "TypeScript",
    "tsx": "TSX", "jsx": "JSX", "sql": "SQL", "xml": "XML", "yaml": "YAML", "powershell": "PowerShell",
    "batch": "Batch", "bash": "Bash", "css": "CSS", "scss": "SCSS", "c": "C", "cpp": "C++", "java": "Java",
    "kotlin": "Kotlin", "go": "Go", "rust": "Rust", "php": "PHP", "ruby": "Ruby", "vbnet": "VB.NET", "ini": "INI",
    "toml": "TOML", "r": "R", "swift": "Swift", "docker": "Dockerfile", "html": "HTML", "razor": "Razor",
    "graphql": "GraphQL", "lua": "Lua", "markdown": "Markdown", "text": "Text",
}
SUPPORTED_EXT = RICH_EXT | MARKDOWN_EXT | TEXT_EXT | IMAGE_EXT | set(CODE_EXT) | {".docx", ".rtf"}

META_PREFIX = "autotemplates:"
META_KEYS = ("tags", "abbreviation", "description", "mode")


def kind_for(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in RICH_EXT:
        return "rich"
    if ext in MARKDOWN_EXT:
        return "markdown"
    if ext in TEXT_EXT:
        return "text"
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".docx":
        return "docx"
    if ext == ".rtf":
        return "rtf"
    if ext in CODE_EXT:
        return "code"
    return None


def language_for(path: Path) -> str:
    return CODE_EXT.get(path.suffix.lower(), "")


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- html


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "table", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head", "title"):
            self._skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "img":
            alt = dict(attrs).get("alt") or ""
            self.parts.append(f"[{alt or 'image'}]")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head", "title"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    text = "".join(parser.parts).replace("\u2029", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


_META_RE = re.compile(r'<meta\s+name="autotemplates:([a-z]+)"\s+content="([^"]*)"\s*/?>', re.I)


def read_meta(markup: str) -> dict[str, str]:
    return {k.lower(): htmllib.unescape(v) for k, v in _META_RE.findall(markup[:8192])}


def write_meta(markup: str, meta: dict[str, str]) -> str:
    """Replaces the ``autotemplates:*`` meta tags of a full HTML document."""
    markup = _META_RE.sub("", markup)
    tags = "".join(
        f'<meta name="{META_PREFIX}{k}" content="{htmllib.escape(str(v), quote=True)}" />'
        for k, v in meta.items()
        if k in META_KEYS and str(v).strip()
    )
    if re.search(r"<head[^>]*>", markup, re.I):
        return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + tags, markup, count=1, flags=re.I)
    return f"<html><head>{tags}</head><body>{markup}</body></html>"


# --------------------------------------------------------------------------- rtf

_RTF_DEST = {
    "aftncn", "aftnsep", "aftnsepc", "annotation", "atnauthor", "atndate", "atnicn", "atnid", "atnparent", "atnref",
    "atntime", "atrfend", "atrfstart", "author", "background", "bkmkend", "bkmkstart", "blipuid", "buptim",
    "category", "colorschememapping", "colortbl", "comment", "company", "creatim", "datafield", "datastore",
    "defchp", "defpap", "do", "doccomm", "docvar", "dptxbxtext", "ebcend", "ebcstart", "factoidname", "falt",
    "fchars", "ffdeftext", "ffentrymcr", "ffexitmcr", "ffformat", "ffhelptext", "ffl", "ffname", "ffstattext",
    "field", "file", "filetbl", "fldinst", "fldtype", "fname", "fontemb", "fontfile", "fonttbl", "footer",
    "footerf", "footerl", "footerr", "footnote", "formfield", "ftncn", "ftnsep", "ftnsepc", "g", "generator",
    "gridtbl", "header", "headerf", "headerl", "headerr", "hl", "hlfr", "hlinkbase", "hlloc", "hlsrc", "hsv",
    "htmltag", "info", "keycode", "keywords", "latentstyles", "lchars", "levelnumbers", "leveltext", "lfolevel",
    "linkval", "list", "listlevel", "listname", "listoverride", "listoverridetable", "listpicture", "liststylename",
    "listtable", "listtext", "lsdlockedexcept", "macc", "maccPr", "mailmerge", "maln", "malnScr", "manager",
    "margPr", "mbar", "mbarPr", "mbaseJc", "mbegChr", "mborderBox", "mborderBoxPr", "mbox", "mboxPr", "mchr",
    "mcount", "mctrlPr", "md", "mdeg", "mdegHide", "mden", "mdiff", "mdPr", "me", "mendChr", "meqArr", "meqArrPr",
    "mf", "mfName", "mfPr", "mfunc", "mfuncPr", "mgroupChr", "mgroupChrPr", "mgrow", "mhideBot", "mhideLeft",
    "mhideRight", "mhideTop", "mhtmltag", "mlim", "mlimloc", "mlimlow", "mlimlowPr", "mlimupp", "mlimuppPr", "mm",
    "mmaddfieldname", "mmath", "mmathPict", "mmathPr", "mmaxdist", "mmc", "mmcJc", "mmconnectstr",
    "mmconnectstrdata", "mmcPr", "mmcs", "mmdatasource", "mmheadersource", "mmmailsubject", "mmodso",
    "mmodsofilter", "mmodsofldmpdata", "mmodsomappedname", "mmodsoname", "mmodsorecipdata", "mmodsosort",
    "mmodsosrc", "mmodsotable", "mmodsoudl", "mmodsoudldata", "mmodsouniquetag", "mmPr", "mmquery", "mmr", "mnary",
    "mnaryPr", "mnoBreak", "mnum", "mobjDist", "moMath", "moMathPara", "moMathParaPr", "mopEmu", "mphant",
    "mphantPr", "mplcHide", "mpos", "mr", "mrad", "mradPr", "mrPr", "msepChr", "mshow", "mshp", "msPre", "msPrePr",
    "msSub", "msSubPr", "msSubSup", "msSubSupPr", "msSup", "msSupPr", "mstrikeBLTR", "mstrikeH", "mstrikeTLBR",
    "mstrikeV", "msub", "msubHide", "msup", "msupHide", "mtransp", "mtype", "mvertJc", "mvfmf", "mvfml", "mvtof",
    "mvtol", "mzeroAsc", "mzeroDesc", "mzeroWid", "nesttableprops", "nextfile", "nonesttables", "objalias",
    "objclass", "objdata", "object", "objname", "objsect", "objtime", "oldcprops", "oldpprops", "oldsprops",
    "oldtprops", "oleclsid", "operator", "panose", "password", "passwordhash", "pgp", "pgptbl", "picprop", "pict",
    "pn", "pnseclvl", "pntext", "pntxta", "pntxtb", "printim", "private", "propname", "protend", "protstart",
    "protusertbl", "pxe", "result", "revtbl", "revtim", "rsidtbl", "rxe", "shp", "shpgrp", "shpinst", "shppict",
    "shprslt", "shptxt", "sn", "sp", "staticval", "stylesheet", "subject", "sv", "svb", "tc", "template",
    "themedata", "title", "txe", "ud", "upr", "userprops", "wgrffmtfilter", "windowcaption", "writereservation",
    "writereservhash", "xe", "xform", "xmlattrname", "xmlattrvalue", "xmlclose", "xmlname", "xmlnstbl", "xmlopen",
}
_RTF_SPECIAL = {"par": "\n", "sect": "\n\n", "page": "\n\n", "line": "\n", "tab": "\t", "emdash": "\u2014",
                "endash": "\u2013", "emspace": "\u2003", "enspace": "\u2002", "qmspace": "\u2005", "bullet": "\u2022",
                "lquote": "\u2018", "rquote": "\u2019", "ldblquote": "\u201c", "rdblquote": "\u201d", "row": "\n",
                "cell": "\t"}
_RTF_TOKEN = re.compile(r"\\([a-z]{1,32})(-?\d{1,10})?[ ]?|\\'([0-9a-f]{2})|\\([^a-z])|([{}])|[\r\n]+|(.)", re.I | re.S)


def rtf_to_text(rtf: str) -> str:
    """Plain text of an RTF document (the classic striprtf state machine)."""
    stack: list[tuple[int, bool]] = []
    ignorable = False
    ucskip = 1
    curskip = 0
    out: list[str] = []
    for match in _RTF_TOKEN.finditer(rtf):
        word, arg, hexcode, char, brace, tchar = match.groups()
        if brace:
            curskip = 0
            if brace == "{":
                stack.append((ucskip, ignorable))
            elif stack:
                ucskip, ignorable = stack.pop()
        elif char:
            curskip = 0
            if char == "~":
                if not ignorable:
                    out.append("\xa0")
            elif char in "{}\\":
                if not ignorable:
                    out.append(char)
            elif char == "*":
                ignorable = True
        elif word:
            curskip = 0
            if word in _RTF_DEST:
                ignorable = True
            elif ignorable:
                pass
            elif word in _RTF_SPECIAL:
                out.append(_RTF_SPECIAL[word])
            elif word == "uc":
                ucskip = int(arg or 1)
            elif word == "u":
                code = int(arg or 0)
                out.append(chr(code + 0x10000 if code < 0 else code))
                curskip = ucskip
        elif hexcode:
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                out.append(bytes([int(hexcode, 16)]).decode("cp1252", errors="replace"))
        elif tchar:
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                out.append(tchar)
    return "".join(out).strip()


# --------------------------------------------------------------------------- docx

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_HIGHLIGHT = {"yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff", "blue": "#0000ff",
              "red": "#ff0000", "darkBlue": "#000080", "darkCyan": "#008080", "darkGreen": "#008000",
              "darkMagenta": "#800080", "darkRed": "#800000", "darkYellow": "#808000", "darkGray": "#808080",
              "lightGray": "#c0c0c0", "black": "#000000", "white": "#ffffff"}


@dataclass
class DocxResult:
    html: str
    text: str
    images: list[Path] = field(default_factory=list)


def docx_to_html(path: Path, media_dir: Path | None = None) -> DocxResult:
    """Paragraphs, headings, lists, tables, run formatting and pictures of a .docx.

    Pictures are extracted to ``media_dir`` (when given) and referenced as files,
    which Word and Outlook accept when the HTML is pasted.
    """
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        rels: dict[str, str] = {}
        try:
            for rel in ET.fromstring(zf.read("word/_rels/document.xml.rels")):
                rels[rel.get("Id", "")] = rel.get("Target", "")
        except KeyError:
            pass
        images: list[Path] = []
        image_src: dict[str, str] = {}

        def picture(rid: str) -> str:
            if rid in image_src:
                return image_src[rid]
            target = rels.get(rid, "")
            src = ""
            if target and media_dir is not None:
                name = "word/" + target.lstrip("/") if not target.startswith("word/") else target
                try:
                    data = zf.read(name)
                except KeyError:
                    data = b""
                if data:
                    media_dir.mkdir(parents=True, exist_ok=True)
                    out = media_dir / (hashlib.sha1(data).hexdigest()[:12] + Path(target).suffix.lower())
                    if not out.exists():
                        out.write_bytes(data)
                    images.append(out)
                    src = out.as_uri()
            image_src[rid] = src
            return src

        text_parts: list[str] = []

        def run_html(run: ET.Element) -> str:
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
                elif tag == W + "drawing" or tag.endswith("}pict"):
                    for blip in child.iter(A_BLIP):
                        src = picture(blip.get(R_NS + "embed", ""))
                        if src:
                            pieces.append(f'<img src="{src}"/>')
                            text_parts.append("[image]")
            body = "".join(pieces)
            if not body:
                return ""
            rpr = run.find(W + "rPr")
            if rpr is None:
                return body
            styles: list[str] = []

            def on(name: str) -> bool:
                el = rpr.find(W + name)
                return el is not None and el.get(W + "val", "true") not in ("0", "false", "none")

            color = rpr.find(W + "color")
            if color is not None and color.get(W + "val", "auto") != "auto":
                styles.append(f"color:#{color.get(W + 'val')}")
            hl = rpr.find(W + "highlight")
            if hl is not None and hl.get(W + "val") in _HIGHLIGHT:
                styles.append(f"background-color:{_HIGHLIGHT[hl.get(W + 'val')]}")
            shd = rpr.find(W + "shd")
            if shd is not None and shd.get(W + "fill", "auto") not in ("auto", ""):
                styles.append(f"background-color:#{shd.get(W + 'fill')}")
            sz = rpr.find(W + "sz")
            if sz is not None and (sz.get(W + "val") or "").isdigit():
                styles.append(f"font-size:{int(sz.get(W + 'val')) / 2:g}pt")
            fonts = rpr.find(W + "rFonts")
            if fonts is not None and fonts.get(W + "ascii"):
                styles.append(f"font-family:'{fonts.get(W + 'ascii')}'")
            if on("b"):
                body = f"<b>{body}</b>"
            if on("i"):
                body = f"<i>{body}</i>"
            if on("u"):
                body = f"<u>{body}</u>"
            if on("strike") or on("dstrike"):
                body = f"<s>{body}</s>"
            va = rpr.find(W + "vertAlign")
            if va is not None and va.get(W + "val") in ("superscript", "subscript"):
                body = f"<sup>{body}</sup>" if va.get(W + "val") == "superscript" else f"<sub>{body}</sub>"
            return f'<span style="{";".join(styles)}">{body}</span>' if styles else body

        def inline_html(parent: ET.Element) -> str:
            out = []
            for child in parent:
                if child.tag == W + "r":
                    out.append(run_html(child))
                elif child.tag == W + "hyperlink":
                    target = rels.get(child.get(R_NS + "id", ""), "")
                    inner = inline_html(child)
                    out.append(f'<a href="{htmllib.escape(target, quote=True)}">{inner}</a>' if target else inner)
                elif child.tag in (W + "ins", W + "smartTag", W + "sdt", W + "sdtContent", W + "fldSimple"):
                    out.append(inline_html(child))
            return "".join(out)

        def paragraph_html(p: ET.Element) -> tuple[str, str | None]:
            ppr = p.find(W + "pPr")
            tag, styles, list_kind = "p", [], None
            if ppr is not None:
                style = ppr.find(W + "pStyle")
                sval = (style.get(W + "val") if style is not None else "") or ""
                m = re.match(r"(?i)heading\s*([1-6])|titlu\s*([1-6])", sval)
                if m:
                    tag = f"h{m.group(1) or m.group(2)}"
                elif sval.lower() == "title":
                    tag = "h1"
                jc = ppr.find(W + "jc")
                if jc is not None and jc.get(W + "val") in ("center", "right", "both", "end"):
                    styles.append("text-align:" + {"both": "justify", "end": "right"}.get(jc.get(W + "val"), jc.get(W + "val")))
                if ppr.find(W + "numPr") is not None or sval.lower().startswith("list"):
                    list_kind = "ol" if "number" in sval.lower() else "ul"
            content = inline_html(p) or "&nbsp;"
            text_parts.append("\n")
            attr = f' style="{";".join(styles)}"' if styles else ""
            if list_kind:
                return f"<li{attr}>{content}</li>", list_kind
            return f"<{tag}{attr}>{content}</{tag}>", None

        def block_html(parent: ET.Element) -> str:
            out: list[str] = []
            open_list: str | None = None
            for child in parent:
                if child.tag == W + "p":
                    markup, kind = paragraph_html(child)
                    if kind != open_list:
                        if open_list:
                            out.append(f"</{open_list}>")
                        if kind:
                            out.append(f"<{kind}>")
                        open_list = kind
                    out.append(markup)
                    continue
                if open_list:
                    out.append(f"</{open_list}>")
                    open_list = None
                if child.tag == W + "tbl":
                    rows = []
                    for tr in child.findall(W + "tr"):
                        cells = "".join(f"<td>{block_html(tc)}</td>" for tc in tr.findall(W + "tc"))
                        rows.append(f"<tr>{cells}</tr>")
                        text_parts.append("\n")
                    out.append('<table border="1" cellspacing="0" cellpadding="4">' + "".join(rows) + "</table>")
                elif child.tag == W + "sdt":
                    content = child.find(W + "sdtContent")
                    if content is not None:
                        out.append(block_html(content))
            if open_list:
                out.append(f"</{open_list}>")
            return "".join(out)

        body = root.find(W + "body")
        markup = block_html(body) if body is not None else ""
    text = re.sub(r"\n{3,}", "\n\n", "".join(text_parts)).strip()
    return DocxResult(f"<html><body>{markup}</body></html>", text, images)


def docx_text(path: Path) -> str:
    return docx_to_html(path, None).text


# --------------------------------------------------------------------------- index text


def plain_text(path: Path, kind: str) -> str:
    """Plain text used for search and the list preview (never raises)."""
    try:
        if kind == "rich":
            return html_to_text(read_text(path))
        if kind in ("markdown", "text", "code"):
            return read_text(path)
        if kind == "docx":
            return docx_text(path)
        if kind == "rtf":
            return rtf_to_text(read_text(path))
        if kind == "image":
            return ""
    except Exception:  # noqa: BLE001 - a broken file must not break the library
        return ""
    return ""