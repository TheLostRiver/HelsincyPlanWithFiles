import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = SourceFileLoader(
    "progress_lifecycle",
    str(REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "progress_lifecycle.py"),
).load_module()


class ProgressCompactionTests(unittest.TestCase):
    def test_compact_archives_old_auto_records_and_keeps_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            records = []
            for index in range(5):
                records.append(
                    "\n".join(
                        [
                            f"### Auto Record: 2026-05-12 10:0{index}:00",
                            "- Tool: apply_patch",
                            "- Files:",
                            f"  - `src/file_{index}.py` (update)",
                            "",
                        ]
                    )
                )
            progress.write_text("# Progress Log\n\nManual note stays.\n\n" + "\n".join(records), encoding="utf-8")

            result = MODULE.compact_progress(
                progress,
                archive,
                keep_records=2,
                dry_run=False,
                now="2026-05-12 22:10:00",
            )

            self.assertEqual(result.archived_count, 3)
            self.assertEqual(result.kept_count, 2)
            self.assertEqual(result.total_auto_records, 5)
            self.assertTrue(result.changed)
            updated = progress.read_text(encoding="utf-8")
            archived = archive.read_text(encoding="utf-8")
            self.assertIn("Manual note stays.", updated)
            self.assertIn("PWF_COMPACT_SUMMARY_START", updated)
            self.assertIn("- Archived Auto Records: 3", updated)
            self.assertIn("- Kept Recent Auto Records: 2", updated)
            self.assertIn("- Tools: apply_patch=3", updated)
            self.assertIn("- Unique Files: 3", updated)
            self.assertNotIn("src/file_0.py", updated)
            self.assertNotIn("src/file_2.py", updated)
            self.assertIn("src/file_3.py", updated)
            self.assertIn("src/file_4.py", updated)
            self.assertIn("src/file_0.py", archived)
            self.assertIn("src/file_2.py", archived)
            self.assertNotIn("src/file_3.py", archived)
            self.assertIn("---BEGIN ARCHIVED AUTO RECORDS---", archived)
            self.assertIn("---END ARCHIVED AUTO RECORDS---", archived)

    def test_compact_dry_run_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            original = "\n".join(
                [
                    "# Progress Log",
                    "",
                    "### Auto Record: 2026-05-12 10:00:00",
                    "- Tool: Write",
                    "- Files:",
                    "  - `a.md` (write)",
                    "",
                    "### Auto Record: 2026-05-12 10:01:00",
                    "- Tool: Edit",
                    "- Files:",
                    "  - `b.md` (edit)",
                    "",
                ]
            )
            progress.write_text(original, encoding="utf-8")

            result = MODULE.compact_progress(
                progress,
                archive,
                keep_records=1,
                dry_run=True,
                now="2026-05-12 22:10:00",
            )

            self.assertEqual(result.archived_count, 1)
            self.assertEqual(result.kept_count, 1)
            self.assertFalse(result.changed)
            self.assertEqual(progress.read_text(encoding="utf-8"), original)
            self.assertFalse(archive.exists())

    def test_compact_replaces_existing_managed_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "<!-- PWF_COMPACT_SUMMARY_START -->",
                        "old summary",
                        "<!-- PWF_COMPACT_SUMMARY_END -->",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: Write",
                        "- Files:",
                        "  - `old.md` (write)",
                        "",
                        "### Auto Record: 2026-05-12 10:01:00",
                        "- Tool: Edit",
                        "- Files:",
                        "  - `new.md` (edit)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            MODULE.compact_progress(progress, archive, keep_records=1, now="2026-05-12 22:10:00")

            updated = progress.read_text(encoding="utf-8")
            self.assertNotIn("old summary", updated)
            self.assertEqual(updated.count("PWF_COMPACT_SUMMARY_START"), 1)
            self.assertIn("new.md", updated)
            self.assertNotIn("old.md", updated)

    def test_count_and_summary_handle_missing_progress_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "missing.md"

            self.assertEqual(MODULE.count_auto_records(progress), 0)
            self.assertEqual(MODULE.extract_compaction_summary(progress), "")

            result = MODULE.compact_progress(progress, root / "archive.md", keep_records=5)

            self.assertEqual(result.archived_count, 0)
            self.assertEqual(result.kept_count, 0)
            self.assertEqual(result.total_auto_records, 0)
            self.assertFalse(result.changed)

    def test_compact_rejects_invalid_keep_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text("# Progress Log\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                MODULE.compact_progress(progress, root / "archive.md", keep_records=0)

    def test_compact_rejects_archive_path_matching_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: Write",
                        "",
                        "### Auto Record: 2026-05-12 10:01:00",
                        "- Tool: Edit",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                MODULE.compact_progress(progress, progress, keep_records=1)

    def test_compact_rejects_directory_archive_without_modifying_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "archive-dir"
            archive.mkdir()
            original = "\n".join(
                [
                    "# Progress Log",
                    "",
                    "### Auto Record: 2026-05-12 10:00:00",
                    "- Tool: Write",
                    "- Files:",
                    "  - `old.md` (write)",
                    "",
                    "### Auto Record: 2026-05-12 10:01:00",
                    "- Tool: Edit",
                    "- Files:",
                    "  - `new.md` (edit)",
                    "",
                ]
            )
            progress.write_text(original, encoding="utf-8")

            with self.assertRaises(ValueError):
                MODULE.compact_progress(progress, archive, keep_records=1)

            self.assertEqual(progress.read_text(encoding="utf-8"), original)

    def test_compact_keeps_manual_bullet_after_archived_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        "  - `src/file_0.py` (update)",
                        "",
                        "- Manual bullet note that should stay hot",
                        "",
                        "### Auto Record: 2026-05-12 10:01:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        "  - `src/file_1.py` (update)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            MODULE.compact_progress(progress, archive, keep_records=1, now="2026-05-12 22:10:00")

            updated = progress.read_text(encoding="utf-8")
            archived = archive.read_text(encoding="utf-8")
            self.assertIn("- Manual bullet note that should stay hot", updated)
            self.assertNotIn("- Manual bullet note that should stay hot", archived)

    def test_compact_keeps_indented_manual_bullet_after_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: apply_patch",
                        "",
                        "  - Indented manual note that should stay hot",
                        "",
                        "### Auto Record: 2026-05-12 10:01:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        "  - `src/file_1.py` (update)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            MODULE.compact_progress(progress, archive, keep_records=1, now="2026-05-12 22:10:00")

            updated = progress.read_text(encoding="utf-8")
            archived = archive.read_text(encoding="utf-8")
            self.assertIn("  - Indented manual note that should stay hot", updated)
            self.assertNotIn("Indented manual note that should stay hot", archived)


if __name__ == "__main__":
    unittest.main()
