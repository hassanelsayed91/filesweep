"""Tests for FileSweep core. Run with: python -m pytest -q  (or python -m unittest)"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from filesweep import core
from filesweep.core import Rules


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_local = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(self.root / "_appdata")

    def tearDown(self) -> None:
        if self._old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old_local
        self._tmp.cleanup()

    def touch(self, name: str, content: bytes = b"x") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


class PlanTests(BaseCase):
    def test_files_are_grouped_by_extension(self) -> None:
        self.touch("a.jpg")
        self.touch("b.mp3")
        self.touch("c.pdf")
        moves = core.plan_moves(self.root)
        by_name = {m.src.name: m for m in moves}
        self.assertEqual(by_name["a.jpg"].category, "Images")
        self.assertEqual(by_name["b.mp3"].category, "Audio")
        self.assertEqual(by_name["c.pdf"].category, "Documents")
        self.assertTrue(str(by_name["a.jpg"].dst).endswith(os.path.join("Images", "a.jpg")))

    def test_unknown_files_go_to_other_or_stay(self) -> None:
        self.touch("weird.xyz")
        self.assertEqual(core.plan_moves(self.root)[0].category, "Other")
        rules = Rules(move_unknown=False)
        self.assertEqual(core.plan_moves(self.root, rules), [])

    def test_planning_does_not_touch_disk(self) -> None:
        self.touch("a.png")
        core.plan_moves(self.root)
        self.assertFalse((self.root / "Images").exists())

    def test_by_date_uses_modified_time(self) -> None:
        file = self.touch("old.txt")
        stamp = time.mktime((2021, 3, 9, 10, 0, 0, 0, 0, -1))
        os.utime(file, (stamp, stamp))
        rules = Rules(by_date=True)
        move = core.plan_moves(self.root, rules)[0]
        expected = Path("Documents") / "2021" / "03" / "old.txt"
        self.assertEqual(move.dst, self.root / expected)

    def test_name_collision_gets_numbered(self) -> None:
        self.touch("photo.jpg", b"old")
        (self.root / "Images").mkdir()
        self.touch("Images/photo.jpg", b"already there")
        move = core.plan_moves(self.root)[0]
        self.assertEqual(move.dst.name, "photo (1).jpg")

    def test_temp_and_hidden_files_are_ignored(self) -> None:
        self.touch("download.crdownload")
        self.touch("~$report.docx")
        self.touch(".hidden_secret")
        self.assertEqual(core.plan_moves(self.root), [])

    def test_recursive_mode_and_excluded_dirs(self) -> None:
        self.touch("top.mp4")
        self.touch("nested/deep/song.flac")
        self.touch("node_modules/lib.js")
        rules = Rules(recursive=True)
        names = sorted(m.src.name for m in core.plan_moves(self.root, rules))
        self.assertEqual(names, ["song.flac", "top.mp4"])

    def test_min_age_filter(self) -> None:
        self.touch("fresh.zip")
        rules = Rules(min_age_seconds=3600)
        self.assertEqual(core.plan_moves(self.root, rules), [])

    def test_target_root_outside_source(self) -> None:
        self.touch("clip.mp4")
        target = self.root / "_sorted"
        rules = Rules(target_root=str(target))
        move = core.plan_moves(self.root, rules)[0]
        self.assertEqual(move.dst, target / "Video" / "clip.mp4")

    def test_missing_folder_raises(self) -> None:
        with self.assertRaises(NotADirectoryError):
            core.plan_moves(self.root / "nope")


class ExecuteTests(BaseCase):
    def test_execute_moves_files_and_journals(self) -> None:
        self.touch("pic.png", b"12345")
        moves = core.plan_moves(self.root)
        summary, journal = core.execute(moves)
        self.assertEqual(summary["moved"], 1)
        self.assertIsNotNone(journal)
        self.assertTrue(journal.exists())
        self.assertTrue((self.root / "Images" / "pic.png").exists())
        self.assertFalse((self.root / "pic.png").exists())

    def test_dry_run_changes_nothing(self) -> None:
        self.touch("song.mp3")
        summary, journal = core.execute(core.plan_moves(self.root), dry_run=True)
        self.assertEqual(summary["planned"], 1)
        self.assertIsNone(journal)
        self.assertTrue((self.root / "song.mp3").exists())

    def test_existing_destination_is_never_overwritten(self) -> None:
        self.touch("notes.txt", b"source")
        (self.root / "Documents").mkdir()
        self.touch("Documents/notes.txt", b"keep me")
        core.execute(core.plan_moves(self.root))
        self.assertEqual((self.root / "Documents/notes.txt").read_bytes(), b"keep me")
        self.assertEqual((self.root / "Documents/notes (1).txt").read_bytes(), b"source")

    def test_undo_puts_everything_back(self) -> None:
        self.touch("a.jpg")
        self.touch("b.mp3")
        _, journal = core.execute(core.plan_moves(self.root))
        summary, _ = core.undo(journal)
        self.assertEqual(summary["restored"], 2)
        self.assertTrue((self.root / "a.jpg").exists())
        self.assertTrue((self.root / "b.mp3").exists())

    def test_undo_twice_is_harmless(self) -> None:
        self.touch("a.jpg")
        _, journal = core.execute(core.plan_moves(self.root))
        core.undo(journal)
        second, _ = core.undo(journal)
        self.assertEqual(second["restored"], 0)
        self.assertTrue((self.root / "a.jpg").exists())

    def test_undo_without_journal(self) -> None:
        summary, used = core.undo()
        self.assertIsNone(used)
        self.assertEqual(summary["missing"], 1)

    def test_undo_skips_files_already_gone(self) -> None:
        self.touch("a.jpg")
        _, journal = core.execute(core.plan_moves(self.root))
        (self.root / "Images" / "a.jpg").unlink()
        summary, _ = core.undo(journal)
        self.assertEqual(summary["missing"], 1)

    def test_execute_skips_missing_source(self) -> None:
        self.touch("gone.txt")
        moves = core.plan_moves(self.root)
        moves[0].src.unlink()
        summary, journal = core.execute(moves)
        self.assertEqual(summary["skipped"], 1)
        self.assertIsNone(journal)


class HelperTests(unittest.TestCase):
    def test_human_size(self) -> None:
        self.assertEqual(core.human_size(0), "0 B")
        self.assertEqual(core.human_size(1536), "1.5 KB")
        self.assertEqual(core.human_size(5 * 1024**3), "5.0 GB")

    def test_rules_roundtrip(self) -> None:
        rules = Rules(by_date=True, recursive=True, min_age_seconds=60)
        clone = Rules.from_dict(rules.to_dict())
        self.assertEqual(clone.by_date, True)
        self.assertEqual(clone.recursive, True)
        self.assertEqual(clone.min_age_seconds, 60)
        self.assertEqual(clone.extension_map()[".jpg"], "Images")

    def test_extension_map_accepts_missing_dot(self) -> None:
        rules = Rules(categories={"Pics": ["png", ".JPG"]})
        mapping = rules.extension_map()
        self.assertEqual(mapping[".png"], "Pics")
        self.assertEqual(mapping[".jpg"], "Pics")

    def test_summarize(self) -> None:
        moves = [
            core.Move(Path("a.jpg"), Path("Images/a.jpg"), "Images", 100),
            core.Move(Path("b.jpg"), Path("Images/b.jpg"), "Images", 200),
            core.Move(Path("c.pdf"), Path("Documents/c.pdf"), "Documents", 50),
        ]
        self.assertEqual(core.summarize(moves), [("Documents", 1, 50), ("Images", 2, 300)])


if __name__ == "__main__":
    unittest.main()
