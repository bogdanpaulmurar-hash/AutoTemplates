"""File types a template can be, and Qt-free readers for them.

* ``rich``     .html/.htm  (templates made in the editor; metadata in ``<meta>``)
* ``markdown`` .md/.markdown
* ``text``     .txt/.log/.csv
* ``code``     source files, highlighted with Pygments when inserted
* ``docx``     Word documents, converted to HTML with the standard library (``docx_html``)
* ``rtf``      Rich Text: the original RTF goes to the clipboard, plus HTML made from it
* ``image``    png/jpg/gif/bmp/webp, inserted as a picture
"""

from __future__ import annotations

import html as htmllib
import re
from html.parser import HTMLParser
from pathlib import Path

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


def _decode_byte(value: int, codepage: str) -> str:
    try:
        return bytes([value]).decode(codepage, errors="replace")
    except LookupError:
        return bytes([value]).decode("cp1252", errors="replace")


def rtf_to_text(rtf: str) -> str:
    """Plain text of an RTF document (the classic striprtf state machine)."""
    stack: list[tuple[int, bool]] = []
    ignorable = False
    ucskip = 1
    curskip = 0
    codepage = "cp1252"
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
            elif word == "ansicpg" and arg:
                codepage = f"cp{int(arg)}"
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
                out.append(_decode_byte(int(hexcode, 16), codepage))
        elif tchar:
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                out.append(tchar)
    return "".join(out).strip()


_RTF_ALIGN = {"qc": "center", "qr": "right", "qj": "justify", "ql": ""}
_RTF_UL_ON = {"ul", "uld", "uldash", "uldashd", "uldashdd", "uldb", "ulhwave", "ulldash", "ulth", "ulthd",
              "ulthdash", "ulthdashd", "ulthdashdd", "ulthldash", "ululdbwave", "ulw", "ulwave"}


def _rtf_run_html(text: str, props: dict, fonts: dict, colors: list) -> str:
    if not text:
        return ""
    body = htmllib.escape(text).replace("\t", "&emsp;").replace("\n", "<br/>")
    body = re.sub(r"  +", lambda m: "&nbsp;" * len(m.group(0)), body)
    styles = []
    font = fonts.get(props.get("f"))
    if font:
        styles.append(f"font-family:'{font}'")
    if props.get("fs"):
        styles.append(f"font-size:{props['fs'] / 2:g}pt")
    for key, css in (("cf", "color"), ("bg", "background-color")):
        idx = props.get(key)
        if idx and 0 < idx < len(colors) and colors[idx]:
            styles.append(f"{css}:{colors[idx]}")
    if props.get("b"):
        body = f"<b>{body}</b>"
    if props.get("i"):
        body = f"<i>{body}</i>"
    if props.get("ul"):
        body = f"<u>{body}</u>"
    if props.get("strike"):
        body = f"<s>{body}</s>"
    if props.get("va") == "super":
        body = f"<sup>{body}</sup>"
    elif props.get("va") == "sub":
        body = f"<sub>{body}</sub>"
    if styles:
        body = f'<span style="{";".join(styles)}">{body}</span>'
    if props.get("link"):
        body = f'<a href="{htmllib.escape(props["link"], quote=True)}">{body}</a>'
    return body


def rtf_to_html(rtf: str) -> str:
    """Formatted HTML of an RTF document: fonts, sizes, colours, bold/italic/underline/strike,
    super/subscript, alignment, paragraphs, bullets and hyperlinks (pictures stay in the RTF itself)."""
    fonts: dict[int, str] = {}
    colors: list[str] = []
    cur_color: dict[str, int] = {}
    codepage = "cp1252"
    deff: int | None = None

    # state = (char props, paragraph props, ignorable, ucskip, destination)
    props: dict = {}
    para: dict = {}
    ignorable, ucskip, dest = False, 1, ""
    stack: list[tuple] = []
    curskip = 0
    font_num: int | None = None
    font_name: list[str] = []
    fldinst: list[str] = []
    paragraphs: list[tuple[dict, list[tuple[str, dict]]]] = []
    runs: list[tuple[str, dict]] = []

    def emit(text: str) -> None:
        if dest == "fonttbl":
            font_name.append(text)
        elif dest == "fldinst":
            fldinst.append(text)
        elif dest == "colortbl":
            pass
        elif not ignorable:
            run_props = {} if dest == "listtext" else props  # bullets: no Symbol/Wingdings font
            if runs and runs[-1][1] == run_props:
                runs[-1] = (runs[-1][0] + text, runs[-1][1])
            else:
                runs.append((text, dict(run_props)))

    def end_paragraph() -> None:
        nonlocal runs
        paragraphs.append((dict(para), runs))
        runs = []

    for match in _RTF_TOKEN.finditer(rtf):
        word, arg, hexcode, char, brace, tchar = match.groups()
        if brace:
            curskip = 0
            if brace == "{":
                stack.append((dict(props), dict(para), ignorable, ucskip, dest))
            elif stack:
                closing = dest
                if closing == "fonttbl" and font_num is not None and font_name:
                    fonts[font_num] = "".join(font_name).strip().rstrip(";").strip()
                    font_num, font_name = None, []
                props, para, ignorable, ucskip, dest = stack.pop()
                if closing == "fldinst" and dest != "fldinst":
                    m = re.search(r'HYPERLINK\s+"([^"]+)"', "".join(fldinst))
                    fldinst = []
                    if m:
                        props["link"] = m.group(1)
            continue
        if char:
            curskip = 0
            if char == "~":
                emit("\xa0")
            elif char in "{}\\":
                emit(char)
            elif char == "*":
                ignorable = True
            elif char == "-" or char == "_":
                emit("-" if char == "_" else "")
            continue
        if word:
            curskip = 0
            num = int(arg) if arg is not None else None
            if word == "fonttbl":
                dest, ignorable = "fonttbl", False
                continue
            if word == "colortbl":
                dest, ignorable = "colortbl", False
                continue
            if word == "fldinst":
                dest, ignorable = "fldinst", False
                continue
            if word == "field" and not ignorable:
                continue
            if word in ("listtext", "pntext") and not ignorable:
                dest = "listtext"
                continue
            if dest == "fonttbl":
                if word == "f":
                    if font_num is not None and font_name:
                        fonts[font_num] = "".join(font_name).strip().rstrip(";").strip()
                    font_num, font_name = num, []
                continue
            if dest == "colortbl":
                if word in ("red", "green", "blue"):
                    cur_color[word] = num or 0
                continue
            if word in _RTF_DEST:
                ignorable = True
                continue
            if ignorable:
                continue
            if word == "ansicpg" and num:
                codepage = f"cp{num}"
            elif word == "deff":
                deff = num
            elif word == "uc":
                ucskip = num if num is not None else 1
            elif word == "u":
                code = num or 0
                emit(chr(code + 0x10000 if code < 0 else code))
                curskip = ucskip
            elif word == "par" or word == "sect" or word == "page" or word == "row":
                end_paragraph()
            elif word in ("line",):
                emit("\n")
            elif word in _RTF_SPECIAL:
                emit(_RTF_SPECIAL[word])
            elif word == "plain":
                link = props.get("link")
                props = {"link": link} if link else {}
            elif word == "pard":
                para = {}
            elif word in _RTF_ALIGN:
                para["align"] = _RTF_ALIGN[word]
            elif word in ("b", "i", "strike", "striked"):
                props["strike" if word.startswith("strike") else word] = num != 0
            elif word in _RTF_UL_ON:
                props["ul"] = num != 0
            elif word == "ulnone":
                props["ul"] = False
            elif word == "fs":
                props["fs"] = num
            elif word == "f":
                props["f"] = num
            elif word == "cf":
                props["cf"] = num
            elif word in ("highlight", "cb", "chcbpat"):
                props["bg"] = num
            elif word == "super":
                props["va"] = "super"
            elif word == "sub":
                props["va"] = "sub"
            elif word == "nosupersub":
                props.pop("va", None)
            continue
        if hexcode:
            if curskip > 0:
                curskip -= 1
                continue
            raw = bytes([int(hexcode, 16)])
            if dest == "listtext":
                emit("\u2022" if raw in (b"\xb7", b"\xa7", b"\x95") else _decode_byte(raw[0], codepage))
            else:
                emit(_decode_byte(raw[0], codepage))
            continue
        if tchar:
            if curskip > 0:
                curskip -= 1
                continue
            if dest == "colortbl" and tchar == ";":
                colors.append("#%02x%02x%02x" % (cur_color.get("red", 0), cur_color.get("green", 0),
                                                  cur_color.get("blue", 0)) if cur_color else "")
                cur_color = {}
            else:
                emit(tchar)
    if runs:
        end_paragraph()

    if deff is not None and deff in fonts:
        fonts.setdefault(-1, fonts[deff])
    out: list[str] = []
    for para_props, para_runs in paragraphs:
        parts = []
        for text, run_props in para_runs:
            if "f" not in run_props and deff is not None:
                run_props = {**run_props, "f": deff}
            parts.append(_rtf_run_html(text, run_props, fonts, colors))
        style = "margin:0"
        if para_props.get("align"):
            style += f";text-align:{para_props['align']}"
        out.append(f'<p style="{style}">{"".join(parts) or "&nbsp;"}</p>')
    while out and out[-1].endswith(">&nbsp;</p>"):
        out.pop()
    return "<html><body>" + "".join(out) + "</body></html>"


# --------------------------------------------------------------------------- docx

from autotemplates.core.docx_html import DocxResult, docx_text, docx_to_html  # noqa: E402,F401  (re-exported)


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