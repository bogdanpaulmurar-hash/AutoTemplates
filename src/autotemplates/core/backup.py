"""Backup and restore of AutoTemplates' own data (no Qt).

A backup is one zip in a user-chosen folder::

    AutoTemplates-backup-20261024-123000.zip
        manifest.json            format version, app version, date, computer, library path, contents
        data/settings.json       settings (machine-specific values are ignored on restore)
        data/usage.json          use count, last use, favourites (keys are library-relative)
        data/noteit/draft.json   NoteIT draft and "last note"
        data/noteit/last.json
        data/images/<name>       pictures referenced by the NoteIT notes (local cache)
        library/<rel>            the templates, only when asked for (with their ``.assets``)

``index.json`` is a cache rebuilt by the scan and is never backed up.

Restore rules: machine-specific settings stay local; statistics are merged by
default; templates never overwrite a file (identical ones are skipped, different
ones become ``Name (2)``); NoteIT picture links are rewritten to the local cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from autotemplates import __version__
from autotemplates.core import formats
from autotemplates.core.library import ASSETS_SUFFIX, Usage
from autotemplates.core.settings import DEFAULTS, LOCAL_KEYS, _same_type

log = logging.getLogger(__name__)

FORMAT_VERSION = 1
PREFIX = "AutoTemplates-backup-"
SAFETY_TAG = "before-restore"
MANIFEST = "manifest.json"
NOTEIT_STATES = ("draft", "last")
AUTO_MODES = ("off", "startup", "daily")
_NAME_RE = re.compile(r"^AutoTemplates-backup-(\d{8}-\d{6})(?:-[a-z0-9-]+)?\.zip$")
_SRC_RE = re.compile(r"""(\bsrc\s*=\s*["'])([^"']*)(["'])""", re.I)


class BackupError(Exception):
    """The zip is not an AutoTemplates backup, is damaged, or is from a newer version."""


# ===================================================================== helpers
def _file_from_uri(src: str) -> Path | None:
    if not src.lower().startswith("file:"):
        return None
    parsed = urlparse(src)
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:", path):  # file:///C:/... -> C:/...
        path = path[1:]
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        path = f"//{parsed.netloc}{path}"  # UNC share
    return Path(path)


def _image_name(path: Path, cache_dir: Path) -> str:
    """Cache pictures keep their (content hash) name; others get a path-hash prefix."""
    try:
        if path.resolve().parent == cache_dir.resolve():
            return path.name
    except OSError:
        pass
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    return f"{digest}-{path.name}"


def _safe_member(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
        raise BackupError(f"Unsafe path in backup: {name}")
    return p


def _library_files(root: Path):
    """Every file of the library (templates, their ``.assets``, other files), hidden ones skipped."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in ("__pycache__", "node_modules"))
        for name in sorted(filenames):
            if name.startswith((".", "~$")):
                continue
            yield Path(dirpath) / name


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ===================================================================== create
@dataclass
class BackupSource:
    data_dir: Path
    library_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def usage_file(self) -> Path:
        return self.data_dir / "usage.json"

    @property
    def noteit_dir(self) -> Path:
        return self.data_dir / "noteit"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


def backup_name(now: datetime | None = None, tag: str = "") -> str:
    now = now or datetime.now()
    return f"{PREFIX}{now:%Y%m%d-%H%M%S}{'-' + tag if tag else ''}.zip"


def create_backup(src: BackupSource, dest_dir: Path, *, include_templates: bool = False, tag: str = "",
                  now: datetime | None = None) -> Path:
    """Writes one backup zip into ``dest_dir`` (via a temporary file) and returns its path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    target = dest_dir / backup_name(now, tag)
    n = 2
    while target.exists():
        target = dest_dir / backup_name(now, f"{tag}-{n}" if tag else str(n))
        n += 1
    tmp = dest_dir / f".{target.name}.tmp"

    contents: dict = {"settings": False, "usage": 0, "noteit": [], "images": 0, "templates": 0, "library_files": 0}
    images: dict[str, str] = {}  # src exactly as in the note HTML -> stored name
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if src.settings_file.is_file():
                zf.write(src.settings_file, "data/settings.json")
                contents["settings"] = True
            if src.usage_file.is_file():
                zf.write(src.usage_file, "data/usage.json")
                contents["usage"] = len(_read_json(src.usage_file))
            stored: set[str] = set()
            for state in NOTEIT_STATES:
                path = src.noteit_dir / f"{state}.json"
                data = _read_json(path)
                if not data:
                    continue
                zf.writestr(f"data/noteit/{state}.json", json.dumps(data, ensure_ascii=False))
                contents["noteit"].append(state)
                for m in _SRC_RE.finditer(str(data.get("html") or "")):
                    uri = m.group(2)
                    file = _file_from_uri(uri)
                    if file is None or uri in images or not file.is_file():
                        continue
                    name = _image_name(file, src.cache_dir)
                    images[uri] = name
                    if name not in stored:
                        zf.write(file, f"data/images/{name}")  # stored as-is: pictures are never recompressed
                        stored.add(name)
            contents["images"] = len(stored)
            if include_templates and src.library_dir.is_dir():
                root = src.library_dir
                for file in _library_files(root):
                    rel = file.relative_to(root).as_posix()
                    zf.write(file, f"library/{rel}")
                    contents["library_files"] += 1
                    if formats.kind_for(file) is not None and not any(
                            part.endswith(ASSETS_SUFFIX) for part in file.relative_to(root).parts[:-1]):
                        contents["templates"] += 1
            manifest = {
                "app": "AutoTemplates",
                "format": FORMAT_VERSION,
                "app_version": __version__,
                "created": now.isoformat(timespec="seconds"),
                "computer": platform.node(),
                "library_dir": str(src.library_dir),
                "kind": tag or "backup",
                "contents": contents,
                "noteit_images": images,
            }
            zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    log.info("Backup written: %s", target)
    return target


def list_backups(folder: Path) -> list[Path]:
    """Backup zips in ``folder``, newest first (by the timestamp in the name)."""
    try:
        files = [p for p in Path(folder).iterdir() if p.is_file() and _NAME_RE.match(p.name)]
    except OSError:
        return []
    return sorted(files, key=lambda p: (_NAME_RE.match(p.name).group(1), p.name), reverse=True)


def rotate(folder: Path, keep: int) -> list[Path]:
    """Deletes the oldest backup zips beyond ``keep``; only files named like our backups are touched."""
    removed = []
    for old in list_backups(folder)[max(1, int(keep)):]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            log.warning("Could not delete old backup %s", old)
    return removed


def is_due(mode: str, last: float, *, startup: bool, now: float | None = None) -> bool:
    """``startup``: one at every start. ``daily``: one per calendar day (checked at start and hourly)."""
    if mode == "startup":
        return startup
    if mode == "daily":
        now = time.time() if now is None else now
        return not last or datetime.fromtimestamp(last).date() != datetime.fromtimestamp(now).date()
    return False


# ===================================================================== inspect
@dataclass
class TemplatePlan:
    new: list[str] = field(default_factory=list)  # library-relative paths in the backup
    identical: list[str] = field(default_factory=list)
    different: list[str] = field(default_factory=list)  # restored as "Name (2)"


@dataclass
class BackupInfo:
    path: Path
    manifest: dict
    settings: dict
    usage: dict
    noteit: list[str]
    template_files: list[str]  # library-relative, template files only (assets travel with them)
    other_files: list[str]

    @property
    def created(self) -> str:
        return str(self.manifest.get("created", ""))

    @property
    def computer(self) -> str:
        return str(self.manifest.get("computer", ""))

    @property
    def app_version(self) -> str:
        return str(self.manifest.get("app_version", ""))

    @property
    def library_dir(self) -> str:
        return str(self.manifest.get("library_dir", ""))

    def settings_changes(self, current: dict) -> list[str]:
        """Setting keys the restore would change (machine-specific ones excluded)."""
        return sorted(k for k, v in restorable_settings(self.settings).items() if current.get(k, DEFAULTS[k]) != v)

    def plan_templates(self, library_root: Path) -> TemplatePlan:
        plan = TemplatePlan()
        with zipfile.ZipFile(self.path) as zf:
            for rel in self.template_files:
                local = Path(library_root) / Path(rel)
                if not local.exists():
                    plan.new.append(rel)
                elif _same_template(zf, rel, local):
                    plan.identical.append(rel)
                else:
                    plan.different.append(rel)
        return plan


def restorable_settings(values: dict) -> dict:
    return {k: v for k, v in values.items() if k in DEFAULTS and k not in LOCAL_KEYS and _same_type(v, DEFAULTS[k])}


def read_backup(path: Path) -> BackupInfo:
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for name in names:
                _safe_member(name)
            if MANIFEST not in names:
                raise BackupError("The file is not an AutoTemplates backup (no manifest).")
            manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("app") != "AutoTemplates":
                raise BackupError("The file is not an AutoTemplates backup.")
            fmt = manifest.get("format")
            if not isinstance(fmt, int) or fmt > FORMAT_VERSION:
                raise BackupError(f"The backup was made by a newer AutoTemplates ({manifest.get('app_version')}). "
                                  "Update the application first.")

            def load(name: str) -> dict:
                if name not in names:
                    return {}
                data = json.loads(zf.read(name).decode("utf-8"))
                return data if isinstance(data, dict) else {}

            settings = load("data/settings.json")
            usage = {k: v for k, v in load("data/usage.json").items() if isinstance(v, dict)}
            noteit = [s for s in NOTEIT_STATES if f"data/noteit/{s}.json" in names]
            template_files, other_files = [], []
            for name in names:
                if not name.startswith("library/") or name.endswith("/"):
                    continue
                rel = name[len("library/"):]
                parts = PurePosixPath(rel).parts
                if any(p.endswith(ASSETS_SUFFIX) for p in parts[:-1]):
                    continue  # pictures of a template: restored with it
                (template_files if formats.kind_for(Path(rel)) is not None else other_files).append(rel)
    except BackupError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError, UnicodeDecodeError) as exc:
        raise BackupError(f"The backup cannot be read: {exc}") from exc
    return BackupInfo(path, manifest, settings, usage, noteit, template_files, other_files)


def _assets_members(zf: zipfile.ZipFile, rel: str) -> list[str]:
    prefix = "library/" + str(PurePosixPath(rel).with_suffix(ASSETS_SUFFIX)) + "/"
    return [n for n in zf.namelist() if n.startswith(prefix) and not n.endswith("/")]


def _same_template(zf: zipfile.ZipFile, rel: str, local: Path) -> bool:
    try:
        if zf.read("library/" + rel) != local.read_bytes():
            return False
        local_assets = local.with_suffix(ASSETS_SUFFIX)
        for member in _assets_members(zf, rel):
            sub = member[len("library/" + str(PurePosixPath(rel).with_suffix(ASSETS_SUFFIX)) + "/"):]
            other = local_assets / Path(sub)
            if not other.is_file() or zf.read(member) != other.read_bytes():
                return False
        return True
    except OSError:
        return False


# ===================================================================== restore
USAGE_MERGE = "merge"
USAGE_REPLACE = "replace"


@dataclass
class RestoreOptions:
    settings: bool = True
    usage: bool = True
    usage_mode: str = USAGE_MERGE
    noteit: bool = True
    templates: bool = False
    library_dir: str | None = None  # None = keep the current library; else the folder to use


@dataclass
class RestoreResult:
    settings_changed: list[str] = field(default_factory=list)
    usage_entries: int = 0
    noteit: list[str] = field(default_factory=list)
    templates_added: int = 0
    templates_skipped: int = 0
    renamed: list[tuple[str, str]] = field(default_factory=list)  # (rel in backup, rel restored)
    library_changed: bool = False


def merge_usage(current: dict, incoming: dict) -> dict:
    """Highest count, latest use, favourite if either says so; "deleted" only if both say so."""
    result = {k: dict(v) for k, v in current.items()}
    for rel, entry in incoming.items():
        if not isinstance(entry, dict):
            continue
        mine = result.get(rel)
        if mine is None:
            result[rel] = dict(entry)
            continue
        mine["count"] = max(int(mine.get("count", 0)), int(entry.get("count", 0)))
        last = max(float(mine.get("last", 0)), float(entry.get("last", 0)))
        if last:
            mine["last"] = last
        if mine.get("fav") or entry.get("fav"):
            mine["fav"] = True
        if "deleted" in mine and "deleted" not in entry:
            mine.pop("deleted")
    return result


def _free_path(folder: Path, stem: str, suffix: str, taken_assets: bool) -> Path:
    n = 2
    while True:
        candidate = folder / f"{stem} ({n}){suffix}"
        if not candidate.exists() and not (taken_assets and candidate.with_suffix(ASSETS_SUFFIX).exists()):
            return candidate
        n += 1


def _rewrite_assets_markup(markup: str, old_stem: str, new_stem: str) -> str:
    old_prefix, new_prefix = old_stem + ASSETS_SUFFIX + "/", new_stem + ASSETS_SUFFIX + "/"

    def repl(m: re.Match) -> str:
        src = m.group(2)
        return f"{m.group(1)}{new_prefix}{src[len(old_prefix):]}{m.group(3)}" if src.startswith(old_prefix) else m.group(0)

    return _SRC_RE.sub(repl, markup)


def _restore_templates(zf: zipfile.ZipFile, info: BackupInfo, root: Path, result: RestoreResult) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel in info.template_files:
        local = root / Path(rel)
        if local.exists() and _same_template(zf, rel, local):
            result.templates_skipped += 1
            continue
        target = local if not local.exists() and not local.with_suffix(ASSETS_SUFFIX).exists() else \
            _free_path(local.parent, local.stem, local.suffix, True)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = zf.read("library/" + rel)
        if target.stem != local.stem and formats.kind_for(target) == "rich":
            text = data.decode("utf-8", errors="surrogateescape")
            data = _rewrite_assets_markup(text, local.stem, target.stem).encode("utf-8", errors="surrogateescape")
        target.write_bytes(data)
        prefix = "library/" + str(PurePosixPath(rel).with_suffix(ASSETS_SUFFIX)) + "/"
        for member in _assets_members(zf, rel):
            out = target.with_suffix(ASSETS_SUFFIX) / Path(member[len(prefix):])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(zf.read(member))
        result.templates_added += 1
        new_rel = target.relative_to(root).as_posix()
        if new_rel != rel:
            result.renamed.append((rel, new_rel))
    for rel in info.other_files:  # non-template files: only when missing
        local = root / Path(rel)
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(zf.read("library/" + rel))


def _restore_noteit(zf: zipfile.ZipFile, info: BackupInfo, noteit_dir: Path, cache_dir: Path,
                    result: RestoreResult) -> None:
    images: dict = info.manifest.get("noteit_images") or {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_uri: dict[str, str] = {}
    for src, name in images.items():
        member = f"data/images/{name}"
        if member not in zf.namelist():
            continue
        out = cache_dir / Path(PurePosixPath(name).name)
        if not out.exists():
            out.write_bytes(zf.read(member))
        local_uri[src] = out.resolve().as_uri()
    for state in info.noteit:
        data = json.loads(zf.read(f"data/noteit/{state}.json").decode("utf-8"))
        if not isinstance(data, dict):
            continue
        html = str(data.get("html") or "")
        if local_uri:
            html = _SRC_RE.sub(lambda m: f"{m.group(1)}{local_uri.get(m.group(2), m.group(2))}{m.group(3)}", html)
            data["html"] = html
        _write_json(noteit_dir / f"{state}.json", data)
        result.noteit.append(state)


def restore_backup(info: BackupInfo, options: RestoreOptions, *, settings, usage: Usage, noteit_dir: Path,
                   cache_dir: Path) -> RestoreResult:
    """Applies a backup. ``settings`` is the live Settings object, ``usage`` the live Usage object."""
    result = RestoreResult()
    try:
        with zipfile.ZipFile(info.path) as zf:
            if options.library_dir is not None and options.library_dir != str(settings.get("library_dir") or ""):
                settings.set("library_dir", options.library_dir)
                result.library_changed = True
            if options.templates and info.template_files:
                _restore_templates(zf, info, settings.library_dir, result)
            if options.usage and info.usage:
                usage.data = dict(info.usage) if options.usage_mode == USAGE_REPLACE else merge_usage(usage.data, info.usage)
                for rel_old, rel_new in result.renamed:  # renamed copies start without statistics
                    usage.data.pop(rel_new, None)
                usage.save()
                result.usage_entries = len(info.usage)
            if options.noteit and info.noteit:
                _restore_noteit(zf, info, noteit_dir, cache_dir, result)
            if options.settings and info.settings:
                values = restorable_settings(info.settings)
                result.settings_changed = info.settings_changes(settings.as_dict())
                if values:
                    settings.update(values)
    except (zipfile.BadZipFile, OSError, ValueError, UnicodeDecodeError) as exc:
        raise BackupError(f"Restore failed: {exc}") from exc
    return result
