"""Backup and restore (core.backup): zip + manifest, rotation, restore rules."""

import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from autotemplates.core import backup
from autotemplates.core.backup import BackupError, BackupSource, RestoreOptions
from autotemplates.core.library import Usage
from autotemplates.core.settings import Settings


def make_machine(base: Path, *, lib_name: str = "lib") -> dict:
    data = base / "data"
    lib = base / lib_name
    (data / "noteit").mkdir(parents=True)
    (data / "cache").mkdir()
    (lib / "Emails").mkdir(parents=True)
    settings = Settings(data / "settings.json", lib)
    settings.update({"library_dir": str(lib), "hotkey": "Ctrl+Alt+Q", "theme": "light",
                     "noteit_last_dir": str(base / "elsewhere")})
    usage = Usage(data / "usage.json")
    usage.data = {"Emails/Reply.html": {"count": 5, "last": 100.0, "fav": True},
                  "Top.txt": {"count": 1, "last": 50.0}}
    usage.save()
    png = data / "cache" / "abcdef123456.png"
    png.write_bytes(b"\x89PNG fake picture bytes")
    draft = {"title": "Draft", "html": f'<p>hi</p><img src="{png.resolve().as_uri()}" width="10">', "folder": "Notes"}
    (data / "noteit" / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
    (data / "noteit" / "last.json").write_text(json.dumps({"title": "Last", "html": "<p>x</p>"}), encoding="utf-8")
    (lib / "Emails" / "Reply.html").write_text('<html><body><img src="Reply.assets/a.png"></body></html>', encoding="utf-8")
    (lib / "Emails" / "Reply.assets").mkdir()
    (lib / "Emails" / "Reply.assets" / "a.png").write_bytes(b"picture-a")
    (lib / "Top.txt").write_text("top", encoding="utf-8")
    (data / "index.json").write_text("{}", encoding="utf-8")
    return {"data": data, "lib": lib, "settings": settings, "usage": usage,
            "src": BackupSource(data, lib), "png": png}


def test_create_backup_contents_and_manifest(tmp_path):
    m = make_machine(tmp_path)
    dest = tmp_path / "backups"
    zpath = backup.create_backup(m["src"], dest, now=datetime(2026, 10, 24, 12, 30, 0))
    assert zpath.name == "AutoTemplates-backup-20261024-123000.zip"
    assert not list(dest.glob(".*.tmp"))
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
        assert zf.read("data/images/abcdef123456.png") == m["png"].read_bytes()
    assert {"data/settings.json", "data/usage.json", "data/noteit/draft.json", "data/noteit/last.json"} <= names
    assert "data/index.json" not in names
    assert not any(n.startswith("library/") for n in names)  # templates only on request
    assert manifest["format"] == backup.FORMAT_VERSION and manifest["app"] == "AutoTemplates"
    assert manifest["library_dir"] == str(m["lib"])
    assert manifest["contents"]["usage"] == 2 and manifest["contents"]["noteit"] == ["draft", "last"]


def test_backup_with_templates_counts_templates_not_assets(tmp_path):
    m = make_machine(tmp_path)
    zpath = backup.create_backup(m["src"], tmp_path / "b", include_templates=True)
    info = backup.read_backup(zpath)
    assert sorted(info.template_files) == ["Emails/Reply.html", "Top.txt"]
    assert info.manifest["contents"]["templates"] == 2
    with zipfile.ZipFile(zpath) as zf:
        assert "library/Emails/Reply.assets/a.png" in zf.namelist()


def test_same_second_does_not_overwrite(tmp_path):
    m = make_machine(tmp_path)
    now = datetime(2026, 1, 1, 8, 0, 0)
    a = backup.create_backup(m["src"], tmp_path / "b", now=now)
    b = backup.create_backup(m["src"], tmp_path / "b", now=now)
    assert a != b and a.exists() and b.exists()


def test_rotation_keeps_newest_and_ignores_other_files(tmp_path):
    folder = tmp_path / "b"
    folder.mkdir()
    for day in range(1, 15):
        (folder / f"AutoTemplates-backup-202610{day:02d}-090000.zip").write_bytes(b"x")
    (folder / "AutoTemplates-backup-20261015-090000-before-restore.zip").write_bytes(b"x")
    (folder / "my-notes.zip").write_bytes(b"x")
    removed = backup.rotate(folder, 10)
    left = backup.list_backups(folder)
    assert len(left) == 10 and len(removed) == 5
    assert left[0].name.endswith("20261015-090000-before-restore.zip")
    assert (folder / "my-notes.zip").exists()
    assert not (folder / "AutoTemplates-backup-20261005-090000.zip").exists()
    assert (folder / "AutoTemplates-backup-20261006-090000.zip").exists()


def test_is_due():
    day1 = datetime(2026, 10, 24, 9, 0).timestamp()
    later_same_day = datetime(2026, 10, 24, 23, 0).timestamp()
    next_day = datetime(2026, 10, 25, 0, 5).timestamp()
    assert backup.is_due("daily", 0, startup=False)
    assert not backup.is_due("daily", day1, startup=True, now=later_same_day)
    assert backup.is_due("daily", day1, startup=False, now=next_day)
    assert backup.is_due("startup", day1, startup=True, now=later_same_day)
    assert not backup.is_due("startup", day1, startup=False)
    assert not backup.is_due("off", 0, startup=True)


def test_read_backup_rejects_bad_files(tmp_path):
    not_zip = tmp_path / "a.zip"
    not_zip.write_bytes(b"nope")
    with pytest.raises(BackupError):
        backup.read_backup(not_zip)
    foreign = tmp_path / "b.zip"
    with zipfile.ZipFile(foreign, "w") as zf:
        zf.writestr("hello.txt", "x")
    with pytest.raises(BackupError):
        backup.read_backup(foreign)
    newer = tmp_path / "c.zip"
    with zipfile.ZipFile(newer, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "AutoTemplates", "format": 99, "app_version": "9.0"}))
    with pytest.raises(BackupError, match="newer"):
        backup.read_backup(newer)
    evil = tmp_path / "d.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "AutoTemplates", "format": 1}))
        zf.writestr("../outside.txt", "x")
    with pytest.raises(BackupError, match="Unsafe"):
        backup.read_backup(evil)


def test_merge_usage():
    current = {"a": {"count": 3, "last": 10.0}, "b": {"count": 1, "last": 5.0, "deleted": 7.0}}
    incoming = {"a": {"count": 2, "last": 20.0, "fav": True}, "b": {"count": 4, "last": 1.0}, "c": {"count": 1}}
    merged = backup.merge_usage(current, incoming)
    assert merged["a"] == {"count": 3, "last": 20.0, "fav": True}
    assert merged["b"]["count"] == 4 and "deleted" not in merged["b"]
    assert merged["c"] == {"count": 1}
    assert current["a"] == {"count": 3, "last": 10.0}  # input untouched


def test_restore_on_other_computer(tmp_path):
    old = make_machine(tmp_path / "old")
    zpath = backup.create_backup(old["src"], tmp_path / "b", include_templates=True)

    new = make_machine(tmp_path / "new", lib_name="library")
    new["settings"].update({"theme": "dark", "hotkey": "Ctrl+Q"})
    for f in (new["data"] / "noteit").iterdir():
        f.unlink()
    new["png"].unlink()
    (new["lib"] / "Top.txt").write_text("changed locally", encoding="utf-8")
    new["usage"].data = {"Top.txt": {"count": 9, "last": 10.0}}
    new["usage"].save()

    info = backup.read_backup(zpath)
    assert info.library_dir == str(old["lib"])
    assert set(info.settings_changes(new["settings"].as_dict())) == {"hotkey", "theme"}
    plan = info.plan_templates(new["lib"])
    assert plan.identical == ["Emails/Reply.html"] and plan.different == ["Top.txt"] and plan.new == []

    result = backup.restore_backup(info, RestoreOptions(templates=True), settings=new["settings"],
                                   usage=new["usage"], noteit_dir=new["data"] / "noteit",
                                   cache_dir=new["data"] / "cache")
    s = new["settings"]
    assert s.get("theme") == "light" and s.get("hotkey") == "Ctrl+Alt+Q"
    assert s.library_dir == new["lib"]  # machine-specific: kept
    assert s.get("noteit_last_dir") == str(tmp_path / "new" / "elsewhere")
    # templates: never overwritten
    assert (new["lib"] / "Top.txt").read_text(encoding="utf-8") == "changed locally"
    assert (new["lib"] / "Top (2).txt").read_text(encoding="utf-8") == "top"
    assert result.renamed == [("Top.txt", "Top (2).txt")] and result.templates_skipped == 1
    # statistics merged
    assert new["usage"].data["Top.txt"]["count"] == 9
    assert new["usage"].data["Emails/Reply.html"]["fav"] is True
    assert "Top (2).txt" not in new["usage"].data
    assert json.loads((new["data"] / "usage.json").read_text(encoding="utf-8"))["Top.txt"]["count"] == 9
    # NoteIT picture link points to this computer's cache
    draft = json.loads((new["data"] / "noteit" / "draft.json").read_text(encoding="utf-8"))
    local_png = (new["data"] / "cache" / "abcdef123456.png").resolve()
    assert local_png.read_bytes() == old["png"].read_bytes()
    assert local_png.as_uri() in draft["html"]
    assert old["png"].resolve().as_uri() not in draft["html"]
    assert result.noteit == ["draft", "last"]


def test_restore_rich_template_conflict_moves_assets(tmp_path):
    old = make_machine(tmp_path / "old")
    zpath = backup.create_backup(old["src"], tmp_path / "b", include_templates=True)
    new = make_machine(tmp_path / "new")
    (new["lib"] / "Emails" / "Reply.assets" / "a.png").write_bytes(b"other picture")
    info = backup.read_backup(zpath)
    backup.restore_backup(info, RestoreOptions(settings=False, usage=False, noteit=False, templates=True),
                          settings=new["settings"], usage=new["usage"], noteit_dir=new["data"] / "noteit",
                          cache_dir=new["data"] / "cache")
    copy = new["lib"] / "Emails" / "Reply (2).html"
    assert 'src="Reply (2).assets/a.png"' in copy.read_text(encoding="utf-8")
    assert (new["lib"] / "Emails" / "Reply (2).assets" / "a.png").read_bytes() == b"picture-a"
    assert (new["lib"] / "Emails" / "Reply.assets" / "a.png").read_bytes() == b"other picture"


def test_restore_replace_usage_and_library_choice(tmp_path):
    old = make_machine(tmp_path / "old")
    zpath = backup.create_backup(old["src"], tmp_path / "b")
    new = make_machine(tmp_path / "new")
    new["usage"].data = {"Only.txt": {"count": 1}}
    info = backup.read_backup(zpath)
    result = backup.restore_backup(
        info, RestoreOptions(settings=False, noteit=False, usage_mode=backup.USAGE_REPLACE,
                             library_dir=str(old["lib"])),
        settings=new["settings"], usage=new["usage"], noteit_dir=new["data"] / "noteit",
        cache_dir=new["data"] / "cache")
    assert "Only.txt" not in new["usage"].data and "Top.txt" in new["usage"].data
    assert result.library_changed and new["settings"].library_dir == old["lib"]


def test_restore_ignores_wrong_types(tmp_path):
    old = make_machine(tmp_path / "old")
    raw = json.loads((old["data"] / "settings.json").read_text(encoding="utf-8"))
    raw["paste_delay_ms"] = "fast"
    (old["data"] / "settings.json").write_text(json.dumps(raw), encoding="utf-8")
    zpath = backup.create_backup(old["src"], tmp_path / "b")
    new = make_machine(tmp_path / "new")
    backup.restore_backup(backup.read_backup(zpath), RestoreOptions(), settings=new["settings"],
                          usage=new["usage"], noteit_dir=new["data"] / "noteit", cache_dir=new["data"] / "cache")
    assert new["settings"].get("paste_delay_ms") == 60
