"""A few example templates written into an empty library on first start."""

from __future__ import annotations

from pathlib import Path

from autotemplates.core import formats

_WELCOME = {
    "ro": """<h2>Bun venit în AutoTemplates</h2>
<p>Apasă <b>{hotkey}</b> oriunde scrii (Outlook, Word, Teams, browser, Visual Studio…), caută și apasă <b>Enter</b>.</p>
<ul>
<li><b>Enter</b> inserează cu formatare, <b>Shift+Enter</b> ca text simplu.</li>
<li><b>Alt+1…9</b> inserează direct, <b>Ctrl+E</b> editează, <b>Ctrl+D</b> favorit, <b>Tab</b> schimbă categoria.</li>
<li>Variabile: <span style="background-color:#fff59d">{{date}}</span>, {{time}}, {{weekday}}, {{clipboard}}, {{user}}, {{cursor}}, {{input:Nume client}}.</li>
</ul>
<p>Orice fișier pus în folderul bibliotecii devine template: <i>txt, md, html, rtf, docx, imagini, cod</i>. Subfolderul este categoria.</p>""",
    "en": """<h2>Welcome to AutoTemplates</h2>
<p>Press <b>{hotkey}</b> wherever you type (Outlook, Word, Teams, a browser, Visual Studio…), search and press <b>Enter</b>.</p>
<ul>
<li><b>Enter</b> inserts with formatting, <b>Shift+Enter</b> as plain text.</li>
<li><b>Alt+1…9</b> inserts directly, <b>Ctrl+E</b> edits, <b>Ctrl+D</b> favourite, <b>Tab</b> switches the category.</li>
<li>Variables: <span style="background-color:#fff59d">{{date}}</span>, {{time}}, {{weekday}}, {{clipboard}}, {{user}}, {{cursor}}, {{input:Customer name}}.</li>
</ul>
<p>Any file in the library folder is a template: <i>txt, md, html, rtf, docx, pictures, code</i>. The sub-folder is the category.</p>""",
}

_REPLY = {
    "ro": ("Email", "Răspuns - confirmare", "confirmare, mail", "conf",
           "<p>Bună ziua {input:Nume},</p><p>Vă confirm primirea solicitării din {date}. "
           "Revin cu un răspuns până <b>{input:Termen}</b>.</p><p>{cursor}</p><p>Cu stimă,<br/>{user}</p>"),
    "en": ("Email", "Reply - confirmation", "confirmation, mail", "conf",
           "<p>Hello {input:Name},</p><p>I confirm receiving your request on {date}. "
           "I will get back to you by <b>{input:Deadline}</b>.</p><p>{cursor}</p><p>Kind regards,<br/>{user}</p>"),
}

_FILES = {
    "Code/Python - script.py": '''"""{description}"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    log.info("Started in %s", Path.cwd())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    "Code/JSON - settings.json": '{\n  "name": "example",\n  "enabled": true,\n  "retries": 3,\n  "tags": ["a", "b"]\n}\n',
    "Code/C# - class.cs": '''namespace MyApp;

public sealed class Example
{
    public string Name { get; init; } = string.Empty;

    public override string ToString() => $"Example: {Name}";
}
''',
    "Text/Signature.txt": "--\n{user}\n{date}\n",
    "Markdown/Release notes.md": "## Release {input:Version} — {date}\n\n### New\n- \n\n### Fixed\n- \n\n### Known issues\n- \n",
}


def create_samples(root: Path, language: str = "ro", hotkey: str = "Ctrl+Q") -> None:
    lang = language if language in _WELCOME else "en"
    welcome = root / ("Bun venit.html" if lang == "ro" else "Welcome.html")
    welcome.write_text(formats.write_meta(f"<html><head></head><body>{_WELCOME[lang].format(hotkey=hotkey)}</body></html>",
                                          {"tags": "help", "abbreviation": "help"}), encoding="utf-8")
    cat, name, tags, abbr, body = _REPLY[lang]
    (root / cat).mkdir(exist_ok=True)
    (root / cat / f"{name}.html").write_text(
        formats.write_meta(f"<html><head></head><body>{body}</body></html>", {"tags": tags, "abbreviation": abbr}),
        encoding="utf-8")
    for rel, text in _FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")