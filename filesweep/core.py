"""FileSweep core engine.

Safe, reversible folder organization:
  * plans where every file should go (no changes on disk)
  * moves files into category folders (and optional date folders)
  * writes a journal so every run can be undone with one command
  * never overwrites an existing file
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

APP_NAME = "FileSweep"
VERSION = "1.0.0"
JOURNAL_VERSION = 1
PROJECT_URL = "https://github.com/hassanelsayed91/filesweep"

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
        ".tif", ".tiff", ".heic", ".avif", ".psd", ".raw", ".cr2", ".nef",
    ],
    "Documents": [
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".ods", ".odp",
        ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md", ".epub", ".mobi",
        ".eml", ".msg", ".pages", ".numbers", ".key",
    ],
    "Audio": [
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff",
        ".opus", ".mid", ".midi",
    ],
    "Video": [
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
        ".mpg", ".mpeg", ".3gp",
    ],
    "Archives": [
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
        ".tgz", ".cab",
    ],
    "Installers": [
        ".exe", ".msi", ".msix", ".appx", ".apk", ".appxbundle", ".jar",
    ],
    "Code": [
        ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css",
        ".scss", ".json", ".xml", ".yaml", ".yml", ".sql", ".ps1", ".bat",
        ".cmd", ".sh", ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".php",
        ".go", ".rs", ".rb", ".swift", ".kt", ".lua", ".ipynb",
    ],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2", ".fon"],
}

DEFAULT_EXCLUDES = [
    "*.tmp", "*.temp", "*.crdownload", "*.partial", "*.part", "*.download",
    "desktop.ini", "thumbs.db", "~$*", ".ds_store", "*.lnk.tmp",
]

DEFAULT_EXCLUDE_DIRS = [
    "node_modules", ".git", "__pycache__", "$RECYCLE.BIN",
    "System Volume Information", ".venv", "venv",
]


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def data_dir() -> Path:
    """Per-user folder for config + journals (%LOCALAPPDATA% on Windows)."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def journal_dir() -> Path:
    return data_dir() / "journal"


def config_path() -> Path:
    return data_dir() / "config.json"


# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #
@dataclass
class Rules:
    """How files are sorted."""

    categories: dict[str, list[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_CATEGORIES.items()}
    )
    by_date: bool = False
    date_format: str = "%Y/%m"
    recursive: bool = False
    min_age_seconds: int = 0
    move_unknown: bool = True
    unknown_category: str = "Other"
    exclude_names: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    exclude_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_DIRS))
    target_root: str | None = None

    # -- helpers ---------------------------------------------------------- #
    def extension_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for category, extensions in self.categories.items():
            for ext in extensions:
                ext = ext.strip().lower()
                if not ext:
                    continue
                if not ext.startswith("."):
                    ext = "." + ext
                mapping.setdefault(ext, category)
        return mapping

    def target_for(self, root: Path) -> Path:
        if not self.target_root:
            return Path(root)
        expanded = os.path.expandvars(os.path.expanduser(self.target_root))
        return Path(expanded)

    def to_dict(self) -> dict:
        return {
            "categories": self.categories,
            "by_date": self.by_date,
            "date_format": self.date_format,
            "recursive": self.recursive,
            "min_age_seconds": self.min_age_seconds,
            "move_unknown": self.move_unknown,
            "unknown_category": self.unknown_category,
            "exclude_names": self.exclude_names,
            "exclude_dirs": self.exclude_dirs,
            "target_root": self.target_root,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rules":
        rules = cls()
        for key, value in (data or {}).items():
            if not hasattr(rules, key):
                continue
            if key == "categories" and isinstance(value, dict):
                rules.categories = {
                    str(cat): [str(e) for e in exts] for cat, exts in value.items()
                }
            else:
                setattr(rules, key, value)
        return rules

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Rules":
        config = Path(path) if path else config_path()
        if not config.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(config.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[{APP_NAME}] ignoring broken config {config}: {exc}", file=sys.stderr)
            return cls()

    def save(self, path: str | os.PathLike | None = None) -> Path:
        config = Path(path) if path else config_path()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return config


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
@dataclass
class Move:
    src: Path
    dst: Path
    category: str
    size: int = 0
    status: str = "planned"  # planned | moved | skipped | error | restored
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "src": str(self.src),
            "dst": str(self.dst),
            "category": self.category,
            "size": self.size,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Move":
        return cls(
            src=Path(data["src"]),
            dst=Path(data["dst"]),
            category=data.get("category", ""),
            size=int(data.get("size") or 0),
            status=data.get("status", "planned"),
            error=data.get("error", ""),
        )


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def unique_path(path: Path, taken: set[str] | None = None) -> Path:
    """Return ``path`` or ``name (n).ext`` so nothing is ever overwritten."""
    taken = taken if taken is not None else set()
    if not path.exists() and _norm(path) not in taken:
        return path
    stem, suffix = path.stem, path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists() and _norm(candidate) not in taken:
            return candidate
        index += 1


def _is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    if os.name != "nt":
        return False
    try:
        attrs = path.stat().st_file_attributes
    except (OSError, AttributeError):
        return False
    hidden = getattr(__import__("stat"), "FILE_ATTRIBUTE_HIDDEN", 0x2)
    system = getattr(__import__("stat"), "FILE_ATTRIBUTE_SYSTEM", 0x4)
    return bool(attrs & (hidden | system))


def _is_excluded(name: str, patterns: Iterable[str]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pat.lower()) for pat in patterns)


def _iter_files(root: Path, rules: Rules, target: Path) -> Iterator[Path]:
    walker = root.rglob("*") if rules.recursive else root.iterdir()
    excluded_dirs = {d.lower() for d in rules.exclude_dirs}
    root_norm = _norm(root)
    target_norm = _norm(target)
    target_is_separate = target_norm != root_norm

    for path in walker:
        try:
            if path.is_dir():
                continue
            if path.is_symlink():
                continue
            if target_is_separate and _norm(path).startswith(target_norm + os.sep):
                continue
            if not path.is_file():
                continue
        except OSError:
            continue

        if rules.recursive and excluded_dirs:
            parents = {p.name.lower() for p in path.parents}
            if parents & excluded_dirs:
                continue
        if _is_hidden(path):
            continue
        if _is_excluded(path.name, rules.exclude_names):
            continue
        if rules.min_age_seconds:
            try:
                age = datetime.now().timestamp() - path.stat().st_mtime
            except OSError:
                continue
            if age < rules.min_age_seconds:
                continue
        yield path


def _safe_folder(name: str) -> str:
    for char in '<>:"/\\|?*':
        name = name.replace(char, "_")
    return name.strip(" .") or "Other"


def plan_moves(root: str | os.PathLike, rules: Rules | None = None) -> list[Move]:
    """Work out where each file would go. Touches nothing on disk."""
    rules = rules or Rules()
    root_path = Path(root).expanduser()
    if not root_path.is_dir():
        raise NotADirectoryError(f"not a folder: {root_path}")

    target = rules.target_for(root_path)
    ext_map = rules.extension_map()
    taken: set[str] = set()
    moves: list[Move] = []

    for path in _iter_files(root_path, rules, target):
        ext = path.suffix.lower()
        category = ext_map.get(ext)
        if category is None:
            if not rules.move_unknown:
                continue
            category = rules.unknown_category or "Other"

        dest_dir = target / _safe_folder(category)
        if rules.by_date:
            try:
                stamp = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                stamp = datetime.now()
            dest_dir = dest_dir / stamp.strftime(rules.date_format)

        dst = unique_path(dest_dir / path.name, taken)
        taken.add(_norm(dst))
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        moves.append(Move(src=path, dst=dst, category=category, size=size))

    moves.sort(key=lambda m: (m.category.lower(), m.src.name.lower()))
    return moves


# --------------------------------------------------------------------------- #
# journals
# --------------------------------------------------------------------------- #
def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _save_journal(path: Path, moves: list[Move], note: str) -> None:
    payload = {
        "app": APP_NAME,
        "version": VERSION,
        "journal_version": JOURNAL_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "note": note,
        "moves": [m.to_dict() for m in moves],
    }
    _write_json(path, payload)


def latest_journal() -> Path | None:
    folder = journal_dir()
    if not folder.is_dir():
        return None
    journals = sorted(folder.glob("journal-*.json"), key=lambda p: p.stat().st_mtime)
    return journals[-1] if journals else None


def list_journals() -> list[Path]:
    folder = journal_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob("journal-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


# --------------------------------------------------------------------------- #
# executing / undoing
# --------------------------------------------------------------------------- #
def execute(
    moves: list[Move],
    dry_run: bool = False,
    record: bool = True,
) -> tuple[Counter, Path | None]:
    """Move the planned files. Returns (summary, journal_path)."""
    summary: Counter = Counter()

    if dry_run or not moves:
        for move in moves:
            summary[move.status] += 1
        return summary, None

    if not record:
        for move in moves:
            _apply(move, summary)
        return summary, None

    journal_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    journal = journal_dir() / f"journal-{stamp}-{os.getpid()}.json"
    _save_journal(journal, moves, note="pending")
    try:
        for move in moves:
            _apply(move, summary)
    finally:
        _save_journal(journal, moves, note="finished")

    if summary.get("moved", 0) == 0:
        try:
            journal.unlink()
        except OSError:
            pass
        return summary, None
    return summary, journal


def _apply(move: Move, summary: Counter) -> None:
    try:
        if not move.src.exists():
            move.status, move.error = "skipped", "source no longer exists"
            summary["skipped"] += 1
            return
        destination = unique_path(move.dst)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move.src), str(destination))
        move.dst = destination
        move.status = "moved"
        summary["moved"] += 1
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
        move.status = "error"
        move.error = f"{type(exc).__name__}: {exc}"
        summary["error"] += 1


def undo(journal: str | os.PathLike | None = None, dry_run: bool = False) -> tuple[Counter, Path | None]:
    """Put every successfully moved file back where it came from."""
    path = Path(journal) if journal else latest_journal()
    if not path or not path.exists():
        return Counter({"missing": 1}), None

    data = json.loads(path.read_text(encoding="utf-8"))
    summary: Counter = Counter()
    updated: list[dict] = []

    # newest file first, so nested/renamed files go back safely
    for record in reversed(data.get("moves", [])):
        move = Move.from_dict(record)
        if move.status != "moved":
            updated.append(record)
            continue
        try:
            if not move.dst.exists():
                summary["missing"] += 1
                updated.append(record)
                continue
            destination = unique_path(move.src)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not dry_run:
                shutil.move(str(move.dst), str(destination))
            record["status"] = "restored"
            record["restored_to"] = str(destination)
            summary["restored"] += 1
            updated.append(record)
        except Exception as exc:  # noqa: BLE001
            summary["error"] += 1
            moved = dict(record)
            moved["error"] = f"{type(exc).__name__}: {exc}"
            updated.append(moved)
            print(f"[{APP_NAME}] could not restore {move.dst}: {exc}", file=sys.stderr)

    if not dry_run:
        data["undone_at"] = datetime.now().isoformat(timespec="seconds")
        data["moves"] = list(reversed(updated))
        _write_json(path, data)
        _prune_empty_dirs(updated)

    return summary, path


def _prune_empty_dirs(records: list[dict]) -> None:
    """Remove category folders that only exist because of this run."""
    restored = [r for r in records if r.get("status") == "restored"]
    if not restored:
        return
    try:
        stop = Path(os.path.commonpath([str(Path(r["src"]).parent) for r in restored]))
    except ValueError:
        return  # files came from different drives

    seen: set[Path] = set()
    for record in restored:
        folder = Path(record["dst"]).parent
        while folder != stop and folder not in seen and folder.parent != folder:
            seen.add(folder)
            try:
                if any(folder.iterdir()):
                    break
                folder.rmdir()
            except OSError:
                break
            folder = folder.parent


# --------------------------------------------------------------------------- #
# small helpers used by the CLI / GUI
# --------------------------------------------------------------------------- #
def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024 or unit == "TB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def summarize(moves: Iterable[Move]) -> list[tuple[str, int, int]]:
    """[(category, file_count, total_bytes)] sorted by category."""
    counts: Counter = Counter()
    sizes: Counter = Counter()
    for move in moves:
        counts[move.category] += 1
        sizes[move.category] += move.size
    return [(cat, counts[cat], sizes[cat]) for cat in sorted(counts)]
