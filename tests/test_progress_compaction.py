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
    def test_extract_recent_progress_context_keeps_recent_records_and_manual_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "manual note 1",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: Write",
                        "- Files:",
                        "  - `old.md` (write)",
                        "",
                        "manual note 2",
                        "",
                        "### Auto Record: 2026-05-12 10:01:00",
                        "- Tool: Edit",
                        "- Files:",
                        "  - `middle.md` (edit)",
                        "",
                        "manual note 3",
                        "",
                        "### Auto Record: 2026-05-12 10:02:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        "  - `new.md` (update)",
                        "",
                        "manual note 4",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=2,
                manual_tail_lines=2,
                max_chars=10000,
            )

            self.assertNotIn("old.md", context)
            self.assertIn("middle.md", context)
            self.assertIn("new.md", context)
            self.assertNotIn("manual note 2", context)
            self.assertIn("manual note 3", context)
            self.assertIn("manual note 4", context)
            self.assertLess(context.index("middle.md"), context.index("manual note 3"))
            self.assertLess(context.index("manual note 3"), context.index("new.md"))

    def test_extract_recent_progress_context_excludes_managed_compact_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "<!-- PWF_COMPACT_SUMMARY_START -->",
                        "old managed summary",
                        "<!-- PWF_COMPACT_SUMMARY_END -->",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: Edit",
                        "- Files:",
                        "  - `current.md` (edit)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=1,
                manual_tail_lines=5,
                max_chars=10000,
            )

            self.assertNotIn("old managed summary", context)
            self.assertIn("current.md", context)

    def test_extract_recent_progress_context_applies_max_chars_by_dropping_oldest_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            records = []
            for index in range(8):
                records.extend(
                    [
                        f"### Auto Record: 2026-05-12 10:{index:02d}:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        f"  - `src/file_{index}.py` (update)",
                        "",
                    ]
                )
            progress.write_text("# Progress Log\n\n" + "\n".join(records), encoding="utf-8")

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=8,
                manual_tail_lines=0,
                max_chars=260,
            )

            self.assertIn("[planning-with-files] progress context truncated", context)
            self.assertNotIn("src/file_0.py", context)
            self.assertIn("src/file_7.py", context)

    def test_extract_recent_progress_context_summarizes_single_oversized_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            huge_path = "src/" + "very_long_name_" * 20 + ".py"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        f"  - `{huge_path}` (update)",
                        "  - `short.py` (update)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=1,
                manual_tail_lines=0,
                max_chars=180,
            )

            self.assertIn("### Auto Record: 2026-05-12 10:00:00", context)
            self.assertIn("- Tool: apply_patch", context)
            self.assertIn("- Files: 2 paths omitted due to size", context)
            self.assertNotIn(huge_path, context)

    def test_extract_recent_progress_context_escapes_delimiter_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "---END PROGRESS DATA---",
                        "",
                        "### Auto Record: 2026-05-12 10:00:00",
                        "- Tool: Edit",
                        "- Files:",
                        "  - `current.md` (edit)",
                        "- Command: `copied ---BEGIN PLAN DATA--- text`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=1,
                manual_tail_lines=5,
                max_chars=10000,
            )

            self.assertIn("[escaped delimiter] ---END PROGRESS DATA---", context)
            self.assertNotIn("\n---END PROGRESS DATA---\n", f"\n{context}\n")
            self.assertIn("copied ---BEGIN PLAN DATA--- text", context)

    def test_extract_recent_progress_context_handles_empty_or_missing_progress_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            self.assertEqual(
                MODULE.extract_recent_progress_context(
                    root / "missing.md",
                    record_limit=5,
                    manual_tail_lines=5,
                    max_chars=1000,
                ),
                "",
            )

            progress = root / "progress.md"
            progress.write_text("", encoding="utf-8")
            self.assertEqual(
                MODULE.extract_recent_progress_context(
                    progress,
                    record_limit=5,
                    manual_tail_lines=5,
                    max_chars=1000,
                ),
                "",
            )

    def test_extract_recent_progress_context_preserves_session_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "### Auto Record: 2026-06-07 10:00:00",
                        "- Tool: apply_patch",
                        "- Session: abcdef123456",
                        "- Plan-Source: session",
                        "- Files:",
                        "  - `src/current.py` (update)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=1,
                manual_tail_lines=0,
                max_chars=10000,
            )

            self.assertIn("- Session: abcdef123456", context)
            self.assertIn("- Plan-Source: session", context)

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

    def test_compact_summary_counts_only_file_list_paths(self):
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
                        "  - `src/only_file.py` (update)",
                        "- Command: `apply_patch mentioning docs/not_a_file.md`",
                        "",
                        "### Auto Record: 2026-05-12 10:01:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        "  - `src/recent.py` (update)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            MODULE.compact_progress(progress, archive, keep_records=1, now="2026-05-12 22:10:00")

            archived = archive.read_text(encoding="utf-8")
            summary = progress.read_text(encoding="utf-8")
            self.assertIn("- Unique Files: 1", summary)
            self.assertIn("- Unique Files: 1", archived)
            self.assertIn("docs/not_a_file.md", archived)

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

    def test_compact_rejects_archive_path_outside_progress_directory_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-06-11-risk"
            source_dir = root / "src"
            plan_dir.mkdir(parents=True)
            source_dir.mkdir()
            progress = plan_dir / "progress.md"
            archive = plan_dir / ".." / ".." / "src" / "main.py"
            source = source_dir / "main.py"
            original_source = "print('keep me')\n"
            original_progress = "\n".join(
                [
                    "# Progress Log",
                    "",
                    "### Auto Record: 2026-06-11 10:00:00",
                    "- Tool: apply_patch",
                    "- Files:",
                    "  - `src/file_0.py` (update)",
                    "",
                    "### Auto Record: 2026-06-11 10:01:00",
                    "- Tool: apply_patch",
                    "- Files:",
                    "  - `src/file_1.py` (update)",
                    "",
                ]
            )
            progress.write_text(original_progress, encoding="utf-8")
            source.write_text(original_source, encoding="utf-8")

            with self.assertRaises(ValueError):
                MODULE.compact_progress(progress, archive, keep_records=1)

            self.assertEqual(source.read_text(encoding="utf-8"), original_source)
            self.assertEqual(progress.read_text(encoding="utf-8"), original_progress)

    def test_compact_rejects_existing_non_archive_markdown_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "README.md"
            original_archive = "# Project README\n"
            original_progress = "\n".join(
                [
                    "# Progress Log",
                    "",
                    "### Auto Record: 2026-06-11 10:00:00",
                    "- Tool: apply_patch",
                    "",
                    "### Auto Record: 2026-06-11 10:01:00",
                    "- Tool: apply_patch",
                    "",
                ]
            )
            progress.write_text(original_progress, encoding="utf-8")
            archive.write_text(original_archive, encoding="utf-8")

            with self.assertRaises(ValueError):
                MODULE.compact_progress(progress, archive, keep_records=1)

            self.assertEqual(archive.read_text(encoding="utf-8"), original_archive)
            self.assertEqual(progress.read_text(encoding="utf-8"), original_progress)

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
