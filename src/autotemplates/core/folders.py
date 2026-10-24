"""Folder and template operations of the editor tree (move, rename, delete).

No Qt here: the Recycle Bin call is injected, so everything is testable.

Every operation keeps the index and the usage statistics in step with the disk:
moved templates keep their use count, last use and favourite flag; deleted
templates keep them for ``stats_keep_days`` (so a restore from the Recycle Bin
brings them back), then :meth:`Usage.purge` forgets them.

Pictures of editor templates live in ``<name>.assets`` next to the file and are
referenced with relative paths, so moving a whole folder needs no rewrite; only a
template whose *name* changes (conflict → ``Name (2)``) gets its ``src`` updated.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from autotemplates.core import formats
from autotemplates.core.library import ASSETS_SUFFIX, Library, _skip_dir, safe_name

Trash = Callable[[Path], bool]

# conflict policies when a folder with the same name exists in the destination
ASK = "ask"
MERGE = "merge"
KEEP_BOTH = "keep_both"

_SRC_RE = re.compile(r"""(\bsrc\s*=\s*["'])([^"']*)(["'])""", re.I)


class FolderError(Exception):
    """An operation that is not allowed (message key for the UI in ``key``)."""

    def __init__(self, key: str, **kwargs) -> None:
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


class FolderConflict(Exception):
    """The destination already has a folder with this name; ask the user what to do."""

    def __init__(self, target: str) -> None:
        super().__init__(target)
        self.target = target


class TrashFailed(Exception):
    """The Recycle Bin refused the item (e.g. a cloud drive); ask before deleting permanently."""


@dataclass
class Result:
    moved: dict[str, str] = field(default_factory=dict)  # old rel -> new rel (templates)
    renamed: list[tuple[str, str]] = field(default_factory=list)  # (old name, new name) because of conflicts
    folder: str = ""  # the folder's new category (move/rename) or the deleted one
    deleted: list[str] = field(default_factory=list)  # rels of deleted templates


# ---------------------------------------------------------------------- helpers
def clean_category(cat: str) -> str:
    parts = [p.strip() for p in (cat or "").replace("\\", "/").split("/") if p.strip()]
    return "/".join(safe_name(p) for p in parts)


def join(parent: str, name: str) -> str:
    return f"{parent}/{name}" if parent else name


def parent_of(cat: str) -> str:
    return cat.rpartition("/")[0]


def leaf_of(cat: str) -> str:
    return cat.rpartition("/")[2]


def is_inside(cat: str, folder: str) -> bool:
    """True when ``cat`` is ``folder`` or one of its sub-folders."""
    return bool(folder) and (cat == folder or cat.startswith(folder + "/"))


def remap_category(cat: str, old: str, new: str) -> str:
    """``cat`` after ``old`` was moved to ``new`` (unchanged when it is outside ``old``)."""
    if not is_inside(cat, old):
        return cat
    return new + cat[len(old):]


def folder_counts(root: Path, cat: str) -> tuple[int, int]:
    """(templates, sub-folders) under a folder, for the delete confirmation."""
    base = root / cat
    templates = folders = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
        folders += len(dirnames)
        templates += sum(1 for f in filenames if not f.startswith((".", "~$")) and formats.kind_for(Path(f)))
    return templates, folders


def _same_entry(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def _rename(src: Path, dst: Path) -> None:
    """Rename/move, also when only the letter case changes (Windows is case-insensitive)."""
    if _same_entry(src, dst) and src.name != dst.name:
        tmp = src.with_name(src.name + ".__moving__")
        os.rename(src, tmp)
        os.rename(tmp, dst)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _free_template_path(folder: Path, stem: str, suffix: str) -> Path:
    """``Name.ext`` or ``Name (2).ext`` such that neither the file nor its ``.assets`` exists."""
    n = 1
    while True:
        candidate = folder / (f"{stem}{suffix}" if n == 1 else f"{stem} ({n}){suffix}")
        if not candidate.exists() and not candidate.with_suffix(ASSETS_SUFFIX).exists():
            return candidate
        n += 1


def _free_folder_path(parent: Path, name: str) -> Path:
    n = 1
    while True:
        candidate = parent / (name if n == 1 else f"{name} ({n})")
        if not candidate.exists():
            return candidate
        n += 1


def _rewrite_assets(path: Path, old_stem: str, new_stem: str) -> None:
    """Points ``<img src="Old.assets/…">`` to ``New.assets/…`` after a rename."""
    old_prefix, new_prefix = old_stem + ASSETS_SUFFIX + "/", new_stem + ASSETS_SUFFIX + "/"
    try:
        markup = formats.read_text(path)
    except OSError:
        return

    def repl(m: re.Match) -> str:
        src = m.group(2)
        return f"{m.group(1)}{new_prefix}{src[len(old_prefix):]}{m.group(3)}" if src.startswith(old_prefix) else m.group(0)

    new = _SRC_RE.sub(repl, markup)
    if new != markup:
        path.write_text(new, encoding="utf-8")


def _move_file(src: Path, dst_folder: Path, result: Result, root: Path) -> None:
    """Moves one file (a template with its ``.assets``, or any other file) without overwriting."""
    is_template = formats.kind_for(src) is not None
    dst = _free_template_path(dst_folder, src.stem, src.suffix) if is_template else _free_folder_path(dst_folder, src.name)
    assets = src.with_suffix(ASSETS_SUFFIX)
    _rename(src, dst)
    if is_template and assets.is_dir():
        _rename(assets, dst.with_suffix(ASSETS_SUFFIX))
    if dst.stem != src.stem:
        result.renamed.append((src.name, dst.name))
        if is_template and formats.kind_for(dst) == "rich":
            _rewrite_assets(dst, src.stem, dst.stem)
    if is_template:
        result.moved[src.relative_to(root).as_posix()] = dst.relative_to(root).as_posix()


def _merge(src: Path, dst: Path, result: Result, root: Path) -> None:
    """Moves the content of ``src`` into the existing ``dst``; same-name files get ``(2)``."""
    dst.mkdir(parents=True, exist_ok=True)
    entries = sorted(src.iterdir(), key=lambda p: p.name)
    owned_assets = {p.with_suffix(ASSETS_SUFFIX).name for p in entries if p.is_file() and formats.kind_for(p)}
    for entry in entries:
        if entry.is_dir():
            if entry.name in owned_assets:
                continue  # moves with its template
            if _skip_dir(entry.name):
                _rename(entry, _free_folder_path(dst, entry.name))
                continue
            target = dst / entry.name
            if target.is_dir():
                _merge(entry, target, result, root)
            else:
                if target.exists():
                    target = _free_folder_path(dst, entry.name)
                    result.renamed.append((entry.name, target.name))
                _record_tree(entry, target, result, root)
                _rename(entry, target)
        else:
            _move_file(entry, dst, result, root)
    try:
        src.rmdir()
    except OSError:
        pass


def _record_tree(src: Path, dst: Path, result: Result, root: Path) -> None:
    """Records old → new rels of every template under ``src`` before it moves to ``dst``."""
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
        for f in filenames:
            p = Path(dirpath) / f
            if f.startswith((".", "~$")) or formats.kind_for(p) is None:
                continue
            result.moved[p.relative_to(root).as_posix()] = (dst / p.relative_to(src)).relative_to(root).as_posix()


def _commit(lib: Library, result: Result) -> None:
    lib.apply_moves(result.moved)
    lib.usage.rename_many(result.moved)


# ---------------------------------------------------------------------- operations
def move_template(lib: Library, rel: str, dest: str) -> Result:
    """Moves a template (with its pictures) into folder ``dest``; a same-name file there → ``Name (2)``."""
    root = lib.root
    dest = clean_category(dest)
    src = root / rel
    if not src.is_file():
        raise FolderError("folder.missing", name=rel)
    result = Result(folder=dest)
    if src.parent == (root / dest if dest else root):
        return result
    (root / dest).mkdir(parents=True, exist_ok=True)
    _move_file(src, root / dest if dest else root, result, root)
    _commit(lib, result)
    return result


def move_folder(lib: Library, cat: str, dest_parent: str, *, new_name: str | None = None,
                conflict: str = ASK) -> Result:
    """Moves folder ``cat`` into ``dest_parent`` (``""`` = library root), optionally renaming it.

    Raises :class:`FolderConflict` when the target exists and ``conflict`` is ``ask``.
    """
    root = lib.root
    cat = clean_category(cat)
    dest_parent = clean_category(dest_parent)
    name = clean_category(new_name or "") or leaf_of(cat)
    if "/" in name:
        raise FolderError("folder.bad_name")
    src = root / cat
    if not cat or not src.is_dir():
        raise FolderError("folder.missing", name=cat)
    if is_inside(dest_parent, cat):
        raise FolderError("folder.into_itself", name=leaf_of(cat))
    target_cat = join(dest_parent, name)
    if target_cat == cat:
        return Result(folder=cat)
    target = root / target_cat
    result = Result()
    case_only = target_cat.lower() == cat.lower()
    if target.exists() and not case_only:
        if conflict == ASK:
            raise FolderConflict(target_cat)
        if conflict == MERGE and target.is_dir():
            result.folder = target_cat
            _merge(src, target, result, root)
            _commit(lib, result)
            return result
        target = _free_folder_path(target.parent, name)
        target_cat = target.relative_to(root).as_posix()
        result.renamed.append((name, target.name))
    result.folder = target_cat
    _record_tree(src, target, result, root)
    _rename(src, target)
    _commit(lib, result)
    return result


def rename_folder(lib: Library, cat: str, new_name: str, *, conflict: str = ASK) -> Result:
    return move_folder(lib, cat, parent_of(clean_category(cat)), new_name=new_name, conflict=conflict)


def delete_folder(lib: Library, cat: str, trash: Trash, *, permanent: bool = False) -> Result:
    """Deletes a folder with everything in it: to the Recycle Bin, or permanently when asked.

    Raises :class:`TrashFailed` when the Recycle Bin refuses it and ``permanent`` is False.
    """
    root = lib.root
    cat = clean_category(cat)
    path = root / cat
    if not cat or not path.is_dir():
        raise FolderError("folder.missing", name=cat)
    rels = [t.rel for t in lib.templates if is_inside(t.category, cat)]
    if permanent:
        shutil.rmtree(path)
    elif not trash(path):
        raise TrashFailed(cat)
    lib.remove_many(rels)
    lib.usage.mark_deleted(rels)
    return Result(folder=cat, deleted=rels)


def delete_template(lib: Library, rel: str, trash: Trash, *, permanent: bool = False) -> Result:
    """Deletes a template and its ``.assets`` folder (Recycle Bin first, like :func:`delete_folder`)."""
    path = lib.root / rel
    items = [p for p in (path, path.with_suffix(ASSETS_SUFFIX)) if p.exists()]
    if not permanent:
        if items and not trash(items[0]):
            raise TrashFailed(rel)
        for p in items[1:]:
            trash(p)  # if the bin refuses the pictures, they stay (ignored) so a restore still finds them
    else:
        for p in items:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    lib.remove_many([rel])
    lib.usage.mark_deleted([rel])
    return Result(deleted=[rel])
