"""Command line interface for FileSweep."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import core
from .core import Rules

BANNER = "FileSweep {v} - tidy folders, undo anytime".format(v=core.VERSION)


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def _default_root() -> Path:
    for name in ("Downloads", "downloads", "التنزيلات"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return candidate
    return Path.cwd()


def _build_rules(args: argparse.Namespace) -> Rules:
    rules = Rules.load(args.config)
    if getattr(args, "recursive", False):
        rules.recursive = True
    if getattr(args, "by_date", False):
        rules.by_date = True
    if getattr(args, "target", None):
        rules.target_root = args.target
    if getattr(args, "older_than", None) is not None:
        rules.min_age_seconds = args.older_than
    if getattr(args, "keep_unknown", False):
        rules.move_unknown = False
    return rules


def _print_plan(moves: list[core.Move], limit: int | None = None) -> None:
    rows = core.summarize(moves)
    if not rows:
        print("Nothing to organise. This folder is already tidy.")
        return

    total_files = sum(count for _, count, _ in rows)
    total_bytes = sum(size for _, _, size in rows)
    width = max(len("Category"), *(len(cat) for cat, _, _ in rows))
    print(f"  {'Category'.ljust(width)}   Files        Size")
    print(f"  {'-' * width}   -----   ---------")
    for category, count, size in rows:
        print(f"  {category.ljust(width)}   {count:>5}   {core.human_size(size):>9}")
    print(f"  {'-' * width}   -----   ---------")
    print(f"  {'TOTAL'.ljust(width)}   {total_files:>5}   {core.human_size(total_bytes):>9}")

    if limit is not None:
        shown = moves[:limit]
        print()
        for move in shown:
            print(f"  {move.src.name}  ->  {move.dst}")
        if len(moves) > len(shown):
            print(f"  ... and {len(moves) - len(shown)} more")
    print()


def _print_summary(summary, journal: Path | None) -> None:
    moved = summary.get("moved", 0)
    skipped = summary.get("skipped", 0)
    errors = summary.get("error", 0)
    print(f"  moved: {moved}   skipped: {skipped}   errors: {errors}")
    if journal:
        print(f"  undo with:  filesweep undo \"{journal}\"")
    print()


def cmd_plan(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser() if args.path else _default_root()
    rules = _build_rules(args)
    moves = core.plan_moves(root, rules)
    print(f"\n{BANNER}\n  folder: {root}\n")
    _print_plan(moves, limit=args.limit)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser() if args.path else _default_root()
    rules = _build_rules(args)
    moves = core.plan_moves(root, rules)
    print(f"\n{BANNER}\n  folder: {root}\n")
    _print_plan(moves, limit=args.limit)

    if not moves:
        return 0
    if args.dry_run:
        print("  dry run: nothing was changed.\n")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("  refusing to move files without --yes in a non-interactive shell.\n")
            return 2
        answer = input(f"  Move {len(moves)} file(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "نعم", "ن"):
            print("  cancelled.\n")
            return 0

    summary, journal = core.execute(moves)
    _print_summary(summary, journal)
    return 0 if summary.get("error", 0) == 0 else 1


def cmd_undo(args: argparse.Namespace) -> int:
    journal = Path(args.journal).expanduser() if args.journal else None
    summary, used = core.undo(journal, dry_run=args.dry_run)
    if not used:
        print("No journal found - nothing to undo.")
        return 1
    prefix = "would restore" if args.dry_run else "restored"
    print(f"\n{BANNER}\n  journal: {used}\n")
    print(f"  {prefix}: {summary.get('restored', 0)}   "
          f"missing: {summary.get('missing', 0)}   errors: {summary.get('error', 0)}\n")
    return 0


def cmd_journals(args: argparse.Namespace) -> int:
    journals = core.list_journals()
    if not journals:
        print(f"No journals yet in {core.journal_dir()}")
        return 0
    print(f"\n  {len(journals)} journal(s) in {core.journal_dir()}\n")
    for path in journals[: args.limit]:
        stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {stamp}   {path.name}")
    print()
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    path = Path(args.config) if args.config else core.config_path()
    if args.init or not path.exists():
        saved = Rules().save(path)
        print(f"Default config written to: {saved}")
    else:
        print(f"Config: {path}")
    print("\nCategories:")
    rules = Rules.load(path)
    for category, extensions in rules.categories.items():
        print(f"  {category:<12} {', '.join(extensions)}")
    print()
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser() if args.path else _default_root()
    rules = _build_rules(args)
    if not rules.min_age_seconds:
        rules.min_age_seconds = 15
    print(f"\n{BANNER}\n  watching: {root}  (every {args.interval}s, Ctrl+C to stop)\n")
    try:
        while True:
            moves = core.plan_moves(root, rules)
            if moves:
                print(f"  [{datetime.now():%H:%M:%S}] {len(moves)} new file(s)")
                summary, journal = core.execute(moves)
                print(f"      moved {summary.get('moved', 0)}, errors {summary.get('error', 0)}"
                      + (f", journal {journal.name}" if journal else ""))
            time.sleep(max(5, args.interval))
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui import main as gui_main
    except ImportError as exc:
        print(f"Tkinter is not available: {exc}", file=sys.stderr)
        return 1
    gui_main(args.path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="filesweep",
        description="Tidy any folder by file type - with a one-command undo.",
    )
    parser.add_argument("--version", action="version", version=f"FileSweep {core.VERSION}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", help="path to a JSON config file")
    common.add_argument("-r", "--recursive", action="store_true", help="include subfolders")
    common.add_argument("--by-date", action="store_true", help="add YYYY/MM folders inside each category")
    common.add_argument("--target", help="put category folders somewhere else (e.g. D:\\Sorted)")
    common.add_argument("--older-than", type=int, metavar="SECONDS", help="only touch files older than this")
    common.add_argument("--keep-unknown", action="store_true", help="leave unknown file types where they are")

    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", parents=[common], help="show what would happen (no changes)")
    plan.add_argument("path", nargs="?", help="folder to organise (default: Downloads)")
    plan.add_argument("-n", "--limit", type=int, default=25, help="how many example moves to print")
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", parents=[common], help="actually move the files")
    run.add_argument("path", nargs="?", help="folder to organise (default: Downloads)")
    run.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    run.add_argument("--dry-run", action="store_true", help="pretend to move, change nothing")
    run.add_argument("-n", "--limit", type=int, default=10, help="how many example moves to print")
    run.set_defaults(func=cmd_run)

    undo = sub.add_parser("undo", help="restore the files from a journal")
    undo.add_argument("journal", nargs="?", help="journal file (default: most recent)")
    undo.add_argument("--dry-run", action="store_true", help="show what would be restored")
    undo.set_defaults(func=cmd_undo)

    journals = sub.add_parser("journals", help="list saved journals")
    journals.add_argument("-n", "--limit", type=int, default=20)
    journals.set_defaults(func=cmd_journals)

    config = sub.add_parser("config", help="show or create the config file")
    config.add_argument("--init", action="store_true", help="write a default config")
    config.set_defaults(func=cmd_config)

    watch = sub.add_parser("watch", parents=[common], help="keep a folder tidy in the background")
    watch.add_argument("path", nargs="?", help="folder to watch (default: Downloads)")
    watch.add_argument("--interval", type=int, default=60, help="seconds between scans")
    watch.set_defaults(func=cmd_watch)

    gui = sub.add_parser("gui", help="open the desktop app")
    gui.add_argument("path", nargs="?", help="folder to open with (default: Downloads)")
    gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
