"""In-app guide: content built from the code, both languages complete (no Qt)."""

from autotemplates.core import guide
from autotemplates.core.shortcuts import (EDITOR_SHORTCUTS, FORMAT_SHORTCUTS, NOTEIT_SHORTCUTS, PICKER_SHORTCUTS,
                                          display)
from autotemplates.core.variables import VARIABLES
from autotemplates.i18n import TEXTS


def _section(lang: str, sid: str, settings=None) -> guide.Section:
    return next(s for s in guide.build(lang, settings) if s.id == sid)


def test_same_sections_in_both_languages():
    for lang in ("ro", "en"):
        secs = guide.build(lang)
        assert [s.id for s in secs] == list(guide.SECTION_IDS)
        assert all(s.title and len(s.html) > 200 for s in secs)
    assert guide.build("ro")[0].title != guide.build("en")[0].title


def test_every_command_has_a_label():
    assert set(guide.PICKER_LABELS) == set(PICKER_SHORTCUTS)
    assert set(guide.EDITOR_LABELS) == set(EDITOR_SHORTCUTS)
    assert set(guide.NOTEIT_LABELS) == set(NOTEIT_SHORTCUTS)
    for name in FORMAT_SHORTCUTS:
        assert f"fmt.{name}" in TEXTS


def test_every_shortcut_is_listed():
    for lang in ("ro", "en"):
        picker = _section(lang, guide.PICKER).html
        for seq in PICKER_SHORTCUTS.values():
            assert f"<b>{display(seq)}</b>" in picker
        editor = _section(lang, guide.EDITOR).html
        for seqs in FORMAT_SHORTCUTS.values():
            assert f"<b>{display(seqs[0])}</b>" in editor
        for seq in EDITOR_SHORTCUTS.values():
            assert f"<b>{display(seq)}</b>" in editor
        noteit = _section(lang, guide.NOTEIT).html
        for seq in NOTEIT_SHORTCUTS.values():
            assert f"<b>{display(seq)}</b>" in noteit


def test_every_variable_is_listed():
    for lang in ("ro", "en"):
        html = _section(lang, guide.VARIABLES_SECTION).html
        for token, key in VARIABLES:
            assert token in html
            assert TEXTS[key][0 if lang == "ro" else 1] in html
        assert "{input:" in html


def test_current_settings_are_shown():
    settings = {"hotkey": "Ctrl+Alt+Q", "noteit_hotkey": "Ctrl+Alt+N", "picker_recent_count": 0,
                "launcher_enabled": False, "insert_mode": "plain", "date_format": "%Y-%m-%d"}
    start = _section("ro", guide.START, settings).html
    assert "<b>Ctrl+Alt+Q</b>" in start and "<b>Ctrl+Alt+N</b>" in start
    assert "<b>T</b>" not in start  # quick menu off
    assert "Enter</b> inserează ca text simplu" in start
    assert "Recente (ultimele" not in _section("ro", guide.PICKER, settings).html
    assert "%Y-%m-%d" in _section("ro", guide.VARIABLES_SECTION, settings).html


def test_settings_object_and_defaults():
    class FakeSettings:
        def get(self, key, default=None):
            return {"hotkey": "Ctrl+Shift+Space"}.get(key, default)

    assert "<b>Ctrl+Shift+Space</b>" in _section("en", guide.START, FakeSettings()).html
    assert "<b>Ctrl+Q</b>" in _section("en", guide.START).html  # defaults without settings


def test_search_ignores_diacritics_and_needs_all_words():
    secs = guide.build("ro")
    assert guide.START in [s.id for s in guide.search(secs, "notă rapidă")]
    assert [s.id for s in guide.search(secs, "restaureaza")] == [s.id for s in guide.search(secs, "restaurează")]
    assert guide.BACKUP in [s.id for s in guide.search(secs, "restaurează")]
    assert guide.search(secs, "onenote zzzz") == []
    assert len(guide.search(secs, "")) == len(secs)


def test_no_markup_leaks_into_search_text():
    for s in guide.build("en"):
        assert "<" not in s.text and "&amp;" not in s.text


def test_page_is_a_full_document():
    doc = guide.page(guide.build("en")[0])
    assert doc.startswith("<html>") and "<h2>Quick start</h2>" in doc
