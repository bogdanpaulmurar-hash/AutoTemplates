"""Editor tree operations (core.folders): move, rename, merge, delete, statistics."""

import shutil
from pathlib import Path

import pytest

from autotemplates.core import folders
from autotemplates.core.folders import KEEP_BOTH, MERGE, FolderConflict, FolderError, TrashFailed
from autotemplates.core.library import Library

RICH = '<html><body><p>Hi</p><img src="{stem}.assets/shot.png"></body></html>'


def make_lib(tmp_path: Path) -> Library:
    root = tmp_path / "lib"
    files = {
        "Emails/Reply.html": None,
        "Emails/Hello.txt": "hello",
        "Emails/Old/Archive.txt": "old",
        "Notes/Meeting.txt": "notes",
        "Notes/Reply.html": None,
        "Top.txt": "top",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            path.write_text(RICH.format(stem=path.stem), encoding="utf-8")
            assets = path.with_suffix(".assets")
            assets.mkdir()
            (assets / "shot.png").write_bytes(b"png")
        else:
            path.write_text(text, encoding="utf-8")
    lib = Library(root, tmp_path / "data" / "index.json", tmp_path / "data" / "usage.json")
    lib.scan()
    return lib


def rels(lib: Library) -> set[str]:
    return {t.rel for t in lib.templates}


def test_move_folder_keeps_stats_and_pictures(tmp_path):
    lib = make_lib(tmp_path)
    lib.usage.used("Emails/Reply.html")
    lib.usage.set_favourite("Emails/Old/Archive.txt", True)
    res = folders.move_folder(lib, "Emails", "Notes")
    assert res.folder == "Notes/Emails"
    assert "Notes/Emails/Reply.html" in rels(lib) and "Notes/Emails/Old/Archive.txt" in rels(lib)
    assert not any(r.startswith("Emails/") for r in rels(lib))
    assert lib.usage.count("Notes/Emails/Reply.html") == 1
    assert lib.usage.favourite("Notes/Emails/Old/Archive.txt")
    assert (lib.root / "Notes/Emails/Reply.assets/shot.png").exists()
    assert lib.get("Notes/Emails/Reply.html").category == "Notes/Emails"
    # the index on disk matches a fresh scan
    again = Library(lib.root, lib.index_file, lib.usage.path)
    again.scan()
    assert rels(again) == rels(lib)


def test_move_to_root_and_rename(tmp_path):
    lib = make_lib(tmp_path)
    folders.move_folder(lib, "Emails/Old", "")
    assert "Old/Archive.txt" in rels(lib)
    res = folders.rename_folder(lib, "Old", "Archive 2025")
    assert res.folder == "Archive 2025" and "Archive 2025/Archive.txt" in rels(lib)
    folders.rename_folder(lib, "Archive 2025", "archive 2025")  # case only
    assert "archive 2025/Archive.txt" in rels(lib)
    assert (lib.root / "archive 2025").is_dir()


def test_cannot_move_into_itself(tmp_path):
    lib = make_lib(tmp_path)
    with pytest.raises(FolderError) as err:
        folders.move_folder(lib, "Emails", "Emails/Old")
    assert err.value.key == "folder.into_itself"
    with pytest.raises(FolderError):
        folders.move_folder(lib, "Emails", "Emails")
    with pytest.raises(FolderError):
        folders.rename_folder(lib, "Emails", "a/b")


def test_conflict_ask_merge_keep_both(tmp_path):
    lib = make_lib(tmp_path)
    (lib.root / "Notes/Emails").mkdir()
    (lib.root / "Notes/Emails/Hello.txt").write_text("other", encoding="utf-8")
    lib.scan()
    with pytest.raises(FolderConflict) as conflict:
        folders.move_folder(lib, "Emails", "Notes")
    assert conflict.value.target == "Notes/Emails"
    assert (lib.root / "Emails").is_dir()  # nothing moved yet

    lib.usage.used("Emails/Hello.txt")
    res = folders.move_folder(lib, "Emails", "Notes", conflict=MERGE)
    assert not (lib.root / "Emails").exists()
    assert (lib.root / "Notes/Emails/Hello.txt").read_text(encoding="utf-8") == "other"  # never overwritten
    assert (lib.root / "Notes/Emails/Hello (2).txt").read_text(encoding="utf-8") == "hello"
    assert ("Hello.txt", "Hello (2).txt") in res.renamed
    assert lib.usage.count("Notes/Emails/Hello (2).txt") == 1
    assert {"Notes/Emails/Reply.html", "Notes/Emails/Old/Archive.txt"} <= rels(lib)

    (lib.root / "Emails").mkdir()
    (lib.root / "Emails/New.txt").write_text("n", encoding="utf-8")
    lib.scan()
    res = folders.move_folder(lib, "Emails", "Notes", conflict=KEEP_BOTH)
    assert res.folder == "Notes/Emails (2)" and "Notes/Emails (2)/New.txt" in rels(lib)


def test_merge_renamed_rich_template_keeps_its_pictures(tmp_path):
    lib = make_lib(tmp_path)
    (lib.root / "Emails/Notes").mkdir()
    folders.move_template(lib, "Notes/Reply.html", "Emails/Notes")
    # "Emails" already has "Reply.html": the incoming one becomes "Reply (2)" and its pictures follow
    res = folders.move_template(lib, "Emails/Notes/Reply.html", "Emails")
    assert res.renamed == [("Reply.html", "Reply (2).html")]
    moved = lib.root / "Emails/Reply (2).html"
    assert 'src="Reply (2).assets/shot.png"' in moved.read_text(encoding="utf-8")
    assert (lib.root / "Emails/Reply (2).assets/shot.png").exists()
    assert (lib.root / "Emails/Reply.assets/shot.png").exists()  # the other one untouched


def test_move_template(tmp_path):
    lib = make_lib(tmp_path)
    lib.usage.set_favourite("Top.txt", True)
    res = folders.move_template(lib, "Top.txt", "New/Sub")
    assert res.moved == {"Top.txt": "New/Sub/Top.txt"}
    assert lib.usage.favourite("New/Sub/Top.txt")
    assert folders.move_template(lib, "New/Sub/Top.txt", "New/Sub").moved == {}  # same folder: nothing


def test_delete_folder_trash_and_permanent(tmp_path):
    lib = make_lib(tmp_path)
    lib.usage.used("Emails/Hello.txt")
    assert folders.folder_counts(lib.root, "Emails") == (3, 1)
    with pytest.raises(TrashFailed):
        folders.delete_folder(lib, "Emails", lambda p: False)
    assert (lib.root / "Emails").is_dir() and "Emails/Hello.txt" in rels(lib)

    binned = []
    recycle_bin = tmp_path / "bin"
    recycle_bin.mkdir()

    def trash(p: Path) -> bool:
        binned.append(p)
        shutil.move(str(p), str(recycle_bin / p.name))
        return True

    res = folders.delete_folder(lib, "Emails", trash)
    assert binned == [lib.root / "Emails"] and not (lib.root / "Emails").exists()
    assert set(res.deleted) == {"Emails/Reply.html", "Emails/Hello.txt", "Emails/Old/Archive.txt"}
    assert not any(r.startswith("Emails/") for r in rels(lib))
    assert lib.usage.count("Emails/Hello.txt") == 1  # kept for a while

    folders.delete_folder(lib, "Notes", lambda p: False, permanent=True)
    assert not (lib.root / "Notes").exists() and rels(lib) == {"Top.txt"}


def test_delete_template_trash_failure_asks(tmp_path):
    lib = make_lib(tmp_path)
    with pytest.raises(TrashFailed):
        folders.delete_template(lib, "Notes/Reply.html", lambda p: False)
    assert (lib.root / "Notes/Reply.html").exists()
    folders.delete_template(lib, "Notes/Reply.html", lambda p: False, permanent=True)
    assert not (lib.root / "Notes/Reply.html").exists() and not (lib.root / "Notes/Reply.assets").exists()
    assert "Notes/Reply.html" not in rels(lib)


def test_usage_retention(tmp_path):
    lib = make_lib(tmp_path)
    lib.usage.used("Top.txt")
    lib.usage.used("Notes/Meeting.txt")
    lib.usage.mark_deleted(["Top.txt", "Notes/Meeting.txt"], now=1000.0)
    # restored within the period: the mark goes away, the stats stay
    assert lib.usage.purge({"Top.txt"}, keep_days=30, now=1000.0 + 86400) == 0
    assert "deleted" not in lib.usage.data["Top.txt"]
    assert lib.usage.count("Notes/Meeting.txt") == 1
    # expired
    assert lib.usage.purge(set(), keep_days=30, now=1000.0 + 31 * 86400) == 1
    assert "Notes/Meeting.txt" not in lib.usage.data and lib.usage.count("Top.txt") == 1
    lib.usage.mark_deleted(["Top.txt"], now=5.0)
    assert lib.usage.purge(set(), keep_days=0, now=5.0) == 1  # 0 days = forget at once


def test_helpers():
    assert folders.remap_category("A/B/C", "A/B", "X") == "X/C"
    assert folders.remap_category("A/BB", "A/B", "X") == "A/BB"
    assert folders.is_inside("A/B", "A") and not folders.is_inside("AB", "A") and not folders.is_inside("A", "")
    assert folders.clean_category(" A \\ B: / ") == "A/B-"
