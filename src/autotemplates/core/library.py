"""The template library: a folder of files, indexed for instant search.

* Every supported file under the library folder is a template; its sub-folder
  is the category (``Emails/Reply - delay.html`` → category ``Emails``).
* ``<name>.assets`` folders hold the pictures of editor templates and are
  not templates themselves. Hidden files and Office lock files (``~$…``) are skipped.
* The index (name, category, tags, preview, search text) is cached in the data
  folder by path + size + mtime, so only new or changed files are read again.
* Usage statistics and favourites are local (data folder), so the library can
  be synced (Google Drive, OneDrive) without conflicts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from autotemplates.core import formats

log = logging.getLogger(__name__)

INDEX_VERSION = 2
PREVIEW_CHARS = 600
SEARCH_CHARS = 6000
ASSETS_SUFFIX = ".assets"


def fold(text: str) -> str:
    """Lower-case without diacritics: ``ă`` finds ``a`` (Romanian keyboards optional)."""
    norm = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in norm if not unicodedata.combining(c))


@dataclass
class Template:
    rel: str  # path relative to the library, with "/" separators
    name: str
    category: str
    kind: str
    language: str = ""
    tags: list[str] = field(default_factory=list)
    abbreviation: str = ""
    description: str = ""
    mode: str = ""  # "" (use the setting) | rich | plain
    preview: str = ""
    search: str = ""
    size: int = 0
    mtime: float = 0.0

    def path(self, root: Path) -> Path:
        return root / Path(self.rel)

    @property
    def editable_rich(self) -> bool:
        return self.kind == "rich"

    @property
    def editable_text(self) -> bool:
        return self.kind in ("text", "code", "markdown")


def _read_template(root: Path, path: Path, stat: os.stat_result) -> Template | None:
    kind = formats.kind_for(path)
    if kind is None:
        return None
    rel = path.relative_to(root).as_posix()
    category = path.parent.relative_to(root).as_posix()
    category = "" if category == "." else category
    meta: dict[str, str] = {}
    text = formats.plain_text(path, kind)
    if kind == "rich":
        try:
            meta = formats.read_meta(formats.read_text(path))
        except OSError:
            meta = {}
    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
    tpl = Template(
        rel=rel,
        name=path.stem,
        category=category,
        kind=kind,
        language=formats.language_for(path) if kind == "code" else ("markdown" if kind == "markdown" else ""),
        tags=tags,
        abbreviation=meta.get("abbreviation", "").strip(),
        description=meta.get("description", "").strip(),
        mode=meta.get("mode", "").strip() if meta.get("mode", "").strip() in ("rich", "plain") else "",
        preview=re.sub(r"\s+\n", "\n", text[:PREVIEW_CHARS]),
        size=stat.st_size,
        mtime=stat.st_mtime,
    )
    tpl.search = fold(" ".join([tpl.name, category.replace("/", " "), " ".join(tags), tpl.abbreviation,
                                tpl.description, path.suffix, text[:SEARCH_CHARS]]))
    return tpl


class Usage:
    """Use count, last use and favourites per template (local JSON)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict] = {}
        self._lock = threading.Lock()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data = {k: v for k, v in loaded.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                log.exception("Could not save usage statistics")

    def used(self, rel: str) -> None:
        entry = self.data.setdefault(rel, {})
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last"] = time.time()
        self.save()

    def count(self, rel: str) -> int:
        return int(self.data.get(rel, {}).get("count", 0))

    def last(self, rel: str) -> float:
        return float(self.data.get(rel, {}).get("last", 0))

    def favourite(self, rel: str) -> bool:
        return bool(self.data.get(rel, {}).get("fav"))

    def set_favourite(self, rel: str, value: bool) -> None:
        self.data.setdefault(rel, {})["fav"] = bool(value)
        self.save()

    def rename(self, old: str, new: str) -> None:
        self.rename_many({old: new})

    def rename_many(self, mapping: dict[str, str]) -> None:
        """Moved templates keep their statistics (old rel -> new rel)."""
        changed = False
        for old, new in mapping.items():
            if old != new and old in self.data:
                entry = self.data.pop(old)
                entry.pop("deleted", None)
                self.data[new] = entry
                changed = True
        if changed:
            self.save()

    def mark_deleted(self, rels, now: float | None = None) -> None:
        """Deleted templates keep their statistics for a while (restore from the Recycle Bin)."""
        now = time.time() if now is None else now
        changed = False
        for rel in rels:
            if rel in self.data:
                self.data[rel]["deleted"] = now
                changed = True
        if changed:
            self.save()

    def purge(self, present, keep_days: int, now: float | None = None) -> int:
        """Restored templates get their statistics back; others expire after ``keep_days``.

        ``present`` = rels currently in the library. Returns the number of forgotten entries.
        """
        now = time.time() if now is None else now
        present = set(present)
        removed = 0
        changed = False
        for rel in list(self.data):
            entry = self.data[rel]
            if "deleted" not in entry:
                continue
            if rel in present:
                entry.pop("deleted")
                changed = True
            elif now - float(entry["deleted"]) >= max(0, int(keep_days)) * 86400:
                del self.data[rel]
                removed += 1
                changed = True
        if changed:
            self.save()
        return removed


class Library:
    def __init__(self, root: Path, index_file: Path, usage_file: Path) -> None:
        self.root = Path(root)
        self.index_file = index_file
        self.usage = Usage(usage_file)
        self.templates: list[Template] = []
        self._lock = threading.RLock()
        self._load_index()

    # ------------------------------------------------------------------ index
    def _load_index(self) -> None:
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            if data.get("version") == INDEX_VERSION and data.get("root") == str(self.root):
                self.templates = [Template(**t) for t in data.get("templates", [])]
        except (OSError, ValueError, TypeError):
            self.templates = []

    def _save_index(self) -> None:
        try:
            self.index_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.index_file.with_suffix(".tmp")
            payload = {"version": INDEX_VERSION, "root": str(self.root), "templates": [asdict(t) for t in self.templates]}
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.index_file)
        except OSError:
            log.exception("Could not save the index")

    def set_root(self, root: Path) -> None:
        with self._lock:
            self.root = Path(root)
            self.templates = []

    def scan(self) -> bool:
        """Re-reads new/changed files; returns True when the list changed."""
        start = time.perf_counter()
        with self._lock:
            root = self.root
            cached = {t.rel: t for t in self.templates}
        found: list[Template] = []
        reread = 0
        if root.is_dir():
            for path, stat in _walk(root):
                rel = path.relative_to(root).as_posix()
                old = cached.get(rel)
                if old and old.size == stat.st_size and abs(old.mtime - stat.st_mtime) < 1e-6:
                    found.append(old)
                    continue
                tpl = _read_template(root, path, stat)
                reread += 1
                if tpl:
                    found.append(tpl)
        found.sort(key=lambda t: (fold(t.category), fold(t.name)))
        with self._lock:
            if root != self.root:
                return False  # the folder changed while scanning
            changed = [asdict(t) for t in found] != [asdict(t) for t in self.templates]
            self.templates = found
        if changed:
            self._save_index()
        log.info("Library scan: %d templates, %d read, %.0f ms", len(found), reread, (time.perf_counter() - start) * 1000)
        return changed

    def refresh_one(self, path: Path) -> Template | None:
        """Re-indexes a single file right after the editor saved it."""
        with self._lock:
            rel = path.relative_to(self.root).as_posix()
            self.templates = [t for t in self.templates if t.rel != rel]
            tpl = _read_template(self.root, path, path.stat()) if path.exists() else None
            if tpl:
                self.templates.append(tpl)
                self.templates.sort(key=lambda t: (fold(t.category), fold(t.name)))
        self._save_index()
        return tpl

    def remove(self, rel: str) -> None:
        self.remove_many([rel])

    def remove_many(self, rels) -> None:
        gone = set(rels)
        with self._lock:
            self.templates = [t for t in self.templates if t.rel not in gone]
        self._save_index()

    def apply_moves(self, mapping: dict[str, str]) -> None:
        """Updates the index after files were moved (old rel -> new rel), without a full scan."""
        if not mapping:
            return
        with self._lock:
            root = self.root
            self.templates = [t for t in self.templates if t.rel not in mapping]
            known = {t.rel for t in self.templates}
            for new in mapping.values():
                path = root / new
                if new in known or not path.is_file():
                    continue
                tpl = _read_template(root, path, path.stat())
                if tpl:
                    self.templates.append(tpl)
                    known.add(new)
            self.templates.sort(key=lambda t: (fold(t.category), fold(t.name)))
        self._save_index()

    def get(self, rel: str) -> Template | None:
        with self._lock:
            return next((t for t in self.templates if t.rel == rel), None)

    def categories(self) -> list[str]:
        with self._lock:
            return sorted({t.category for t in self.templates if t.category}, key=fold)

    def folders(self) -> list[Path]:
        """Every folder to watch for changes."""
        out = [self.root]
        if self.root.is_dir():
            for dirpath, dirnames, _ in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
                out.extend(Path(dirpath) / d for d in dirnames)
        return out

    # ------------------------------------------------------------------ search
    def search(self, query: str, *, category: str | None = None, sort: str = "smart", limit: int = 500) -> list[Template]:
        """All words must match; name/abbreviation hits rank first, then usage."""
        words = fold(query).split()
        with self._lock:
            items = list(self.templates)
        if category == "★":  # favourites
            items = [t for t in items if self.usage.favourite(t.rel)]
        elif category:
            items = [t for t in items if t.category == category or t.category.startswith(category + "/")]
        scored: list[tuple[float, Template]] = []
        for t in items:
            if words and not all(w in t.search for w in words):
                continue
            name = fold(t.name)
            score = 0.0
            for w in words:
                if fold(t.abbreviation) == w:
                    score += 100
                if name.startswith(w):
                    score += 30
                elif w in name:
                    score += 15
                elif any(w in fold(tag) for tag in t.tags):
                    score += 8
                elif w in fold(t.category):
                    score += 5
            if sort == "smart":
                score += (20 if self.usage.favourite(t.rel) else 0) + min(self.usage.count(t.rel), 50) * 0.4
                age_days = (time.time() - self.usage.last(t.rel)) / 86400
                score += max(0.0, 10 - age_days) if self.usage.last(t.rel) else 0
            scored.append((score, t))
        if sort == "smart" or words:
            scored.sort(key=lambda st: (-st[0], fold(st[1].category), fold(st[1].name)))
        return [t for _, t in scored[:limit]]


def _skip_dir(name: str) -> bool:
    return name.startswith(".") or name.endswith(ASSETS_SUFFIX) or name in ("__pycache__", "node_modules")


def _walk(root: Path):
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not _skip_dir(entry.name):
                        stack.append(Path(entry.path))
                elif entry.is_file() and not entry.name.startswith((".", "~$")):
                    if Path(entry.name).suffix.lower() in formats.SUPPORTED_EXT:
                        yield Path(entry.path), entry.stat()
            except OSError:
                continue


def safe_name(name: str) -> str:
    """A file name Windows accepts."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip(" .")
    return clean[:120] or "Template"


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    candidate = folder / f"{stem}{suffix}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({n}){suffix}"
        n += 1
    return candidate