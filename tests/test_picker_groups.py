"""Grouped picker view: core grouping (no Qt) and the picker's keyboard behaviour (Qt)."""

from autotemplates.core.grouping import FAVOURITES, RECENT, folder_title, group_results, recent
from autotemplates.core.library import Library, Template, Usage


def _tpl(rel: str) -> Template:
    category, _, name = rel.rpartition("/")
    return Template(rel=rel, name=name.rsplit(".", 1)[0], category=category, kind="text")


def _usage(tmp_path, data: dict) -> Usage:
    u = Usage(tmp_path / "usage.json")
    u.data = data
    return u


RESULTS = [_tpl("Emails/Reply/Delay.txt"), _tpl("Top.txt"), _tpl("Emails/Hello.txt"), _tpl("Code/Snippet.txt")]


def test_folders_sorted_top_level_first(tmp_path):
    groups = group_results(RESULTS, _usage(tmp_path, {}))
    assert [g.key for g in groups] == ["", "Code", "Emails", "Emails/Reply"]
    assert folder_title("Emails/Reply") == "Emails › Reply"


def test_favourites_and_recent_on_top(tmp_path):
    usage = _usage(tmp_path, {"Code/Snippet.txt": {"fav": True, "last": 10.0},
                              "Top.txt": {"last": 30.0}, "Emails/Hello.txt": {"last": 20.0}})
    groups = group_results(RESULTS, usage, recent_count=2)
    assert [g.key for g in groups[:2]] == [FAVOURITES, RECENT]
    assert [t.rel for t in groups[0].items] == ["Code/Snippet.txt"]
    assert [t.rel for t in groups[1].items] == ["Top.txt", "Emails/Hello.txt"]  # newest first, limited
    code = next(g for g in groups if g.key == "Code")
    assert [t.rel for t in code.items] == ["Code/Snippet.txt"]  # favourite stays in its folder too


def test_favourites_only_on_top(tmp_path):
    usage = _usage(tmp_path, {"Code/Snippet.txt": {"fav": True}})
    keys = [g.key for g in group_results(RESULTS, usage, favourites_in_folder=False)]
    assert keys[0] == FAVOURITES and "Code" not in keys  # the folder had only the favourite


def test_recent_off_and_hidden_while_searching(tmp_path):
    usage = _usage(tmp_path, {"Top.txt": {"last": 5.0}})
    assert RECENT not in [g.key for g in group_results(RESULTS, usage, recent_count=0)]
    assert RECENT not in [g.key for g in group_results(RESULTS, usage, searching=True)]
    assert recent(RESULTS, usage, 5) == [RESULTS[1]]


def test_search_orders_folders_by_best_result(tmp_path):
    groups = group_results(RESULTS, _usage(tmp_path, {}), searching=True)
    assert [g.key for g in groups] == ["Emails/Reply", "", "Emails", "Code"]


def test_filter_hides_special_groups(tmp_path):
    usage = _usage(tmp_path, {"Top.txt": {"fav": True, "last": 1.0}})
    keys = [g.key for g in group_results(RESULTS, usage, filtered=True)]
    assert FAVOURITES not in keys and RECENT not in keys


def test_library_recent_sort(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (root / name).write_text(name, encoding="utf-8")
    lib = Library(root, tmp_path / "index.json", tmp_path / "usage.json")
    lib.scan()
    lib.usage.data = {"b.txt": {"last": 9.0}, "c.txt": {"last": 5.0}}
    assert [t.rel for t in lib.search("", sort="recent")] == ["b.txt", "c.txt", "a.txt"]


# ---------------------------------------------------------------------- Qt


def test_picker_grouped_navigation(qapp, home):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    from test_ui import _controller

    from autotemplates.ui.picker import ROLE_GROUP, ROLE_IS_HEADER, ROLE_NUM

    def key(k, mods=Qt.NoModifier):
        p.eventFilter(p.search, QKeyEvent(QEvent.KeyPress, k, mods))

    c = _controller(qapp, home)
    assert c.settings.get("picker_view") == "groups"
    p = c.picker
    p.popup(None)
    assert p.list.item(0).data(ROLE_IS_HEADER)
    assert p.current_rel() is not None  # the first template is selected, not a header
    numbers = [p.list.item(r).data(ROLE_NUM) for r in range(p.list.count()) if p.list.item(r).data(ROLE_NUM)]
    assert numbers == list(range(1, len(numbers) + 1))

    group = p.list.currentItem().data(ROLE_GROUP)
    key(Qt.Key_Left)  # fold
    assert group in c.settings.get("picker_collapsed")
    assert p.list.currentItem().data(ROLE_IS_HEADER)
    key(Qt.Key_Return)  # Enter opens a folded group instead of inserting
    assert group not in c.settings.get("picker_collapsed")
    assert p.current_rel() is not None

    if len(p._group_keys()) > 1:
        key(Qt.Key_Down, Qt.ControlModifier)
        assert p.list.currentItem().data(ROLE_GROUP) != group

    p.view_button.toggle()  # Ctrl+G
    assert c.settings.get("picker_view") == "list"
    assert not any(p.list.item(r).data(ROLE_IS_HEADER) for r in range(p.list.count()))
    p.hide()
