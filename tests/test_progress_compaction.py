import json
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = SourceFileLoader(
    "progress_lifecycle",
    str(REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "progress_lifecycle.py"),
).load_module()


def write_indexed_rollover(root: Path, *, session: str = "abc123", nonce: str = "fixed01") -> tuple[Path, Path]:
    progress = root / "progress.md"
    archive = root / "progress-archive" / session / f"archive-20260611100300-{nonce}.md"
    active = root / "progress-active" / session / f"active-20260611100300-{nonce}.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    active.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text("# Progress Log\n\nlegacy\n", encoding="utf-8")
    archive_text = "# Progress Archive\n\nsealed\n"
    active_text = "# Progress Log\n\nactive\n"
    archive.write_text(archive_text, encoding="utf-8")
    active.write_text(active_text, encoding="utf-8")
    event = {
        "event": "rollover",
        "version": 1,
        "created_at": "2026-06-11T10:03:00Z",
        "session": session,
        "old_active": "progress.md",
        "archive": f"progress-archive/{session}/archive-20260611100300-{nonce}.md",
        "new_active": f"progress-active/{session}/active-20260611100300-{nonce}.md",
        "source_sha256": MODULE._sha256_text("# Progress Log\n\nlegacy\n"),
        "archive_sha256": MODULE._sha256_text(archive_text),
        "new_active_sha256": MODULE._sha256_text(active_text),
        "archived_auto_records": 2,
        "kept_recent_auto_records": 1,
    }
    (root / "progress-index.ndjson").write_text(
        json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return archive, active


class ProgressCompactionTests(unittest.TestCase):
    def test_doctor_progress_storage_reports_healthy_rollover_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _archive, active = write_indexed_rollover(root)

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertFalse(report.has_errors)
            self.assertFalse(report.has_warnings)
            self.assertEqual(report.active_path, active)
            self.assertEqual(report.rollover_events, 1)
            self.assertEqual(report.issues, ())

    def test_doctor_progress_storage_accepts_legacy_progress_without_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text("# Progress Log\n\nlegacy\n", encoding="utf-8")

            report = MODULE.doctor_progress_storage(progress)

            self.assertFalse(report.has_errors)
            self.assertEqual(report.active_path, progress)
            self.assertEqual([issue.code for issue in report.issues], ["legacy_progress_only"])
            self.assertEqual(report.issues[0].severity, "info")

    def test_doctor_progress_storage_reports_invalid_index_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text("{not json\n", encoding="utf-8")

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertTrue(report.has_errors)
            self.assertEqual(report.issues[0].code, "invalid_index_json")
            self.assertEqual(report.issues[0].severity, "error")

    def test_doctor_progress_storage_reports_missing_latest_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _archive, active = write_indexed_rollover(root)
            active.unlink()

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertTrue(report.has_errors)
            self.assertIn("missing_latest_active", [issue.code for issue in report.issues])

    def test_doctor_progress_storage_allows_appended_current_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _archive, active = write_indexed_rollover(root)
            with active.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("\n### Auto Record: 2026-06-11 10:04:00\n- Tool: test\n")

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertFalse(report.has_errors)
            active_hash_mismatches = [
                issue
                for issue in report.issues
                if issue.code == "hash_mismatch"
                and issue.path == "progress-active/abc123/active-20260611100300-fixed01.md"
            ]
            self.assertEqual(active_hash_mismatches, [])

    def test_doctor_progress_storage_reports_old_active_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_indexed_rollover(root)
            (root / "progress.md").write_text("# Progress Log\n\nmodified\n", encoding="utf-8")

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertTrue(report.has_errors)
            matching = [
                issue
                for issue in report.issues
                if issue.code == "hash_mismatch" and issue.path == "progress.md"
            ]
            self.assertEqual(len(matching), 1)

    def test_doctor_progress_storage_requires_source_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_indexed_rollover(root)
            event = json.loads((root / "progress-index.ndjson").read_text(encoding="utf-8"))
            del event["source_sha256"]
            (root / "progress-index.ndjson").write_text(
                json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertTrue(report.has_errors)
            matching = [
                issue
                for issue in report.issues
                if issue.code == "invalid_event_schema" and "source_sha256" in issue.message
            ]
            self.assertEqual(len(matching), 1)

    def test_doctor_progress_storage_excludes_unsafe_refs_from_referenced_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text(
                json.dumps(
                    {
                        "event": "rollover",
                        "version": 1,
                        "archive": "../escape.md",
                        "new_active": "C:\\escape.md",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertIn("path_escapes_root", [issue.code for issue in report.issues])
            self.assertNotIn("../escape.md", report.referenced_paths)
            self.assertNotIn("C:\\escape.md", report.referenced_paths)

    def test_doctor_progress_storage_rejects_non_canonical_index_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
            archive = root / "progress-archive" / "abc123" / "archive-20260611100300-fixed01.md"
            active = root / "progress-active" / "abc123" / "active-20260611100300-fixed01.md"
            archive.parent.mkdir(parents=True)
            active.parent.mkdir(parents=True)
            archive.write_text("# Progress Archive\n", encoding="utf-8")
            active.write_text("# Progress Log\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text(
                json.dumps(
                    {
                        "event": "rollover",
                        "version": 1,
                        "archive": "progress-archive//abc123/archive-20260611100300-fixed01.md",
                        "new_active": "progress-active//abc123/active-20260611100300-fixed01.md",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            report = MODULE.doctor_progress_storage(root / "progress.md")

            codes = [issue.code for issue in report.issues]
            self.assertIn("path_escapes_root", codes)
            self.assertNotIn(
                "progress-archive//abc123/archive-20260611100300-fixed01.md",
                report.referenced_paths,
            )
            self.assertNotIn(
                "progress-active//abc123/active-20260611100300-fixed01.md",
                report.referenced_paths,
            )
            self.assertIn("progress-archive/abc123/archive-20260611100300-fixed01.md", report.orphan_paths)
            self.assertIn("progress-active/abc123/active-20260611100300-fixed01.md", report.orphan_paths)

    def test_doctor_progress_storage_uses_previous_valid_active_when_latest_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_archive, first_active = write_indexed_rollover(root, nonce="first01")
            second_archive = root / "progress-archive" / "abc123" / "archive-20260611100400-second01.md"
            second_active = root / "progress-active" / "abc123" / "active-20260611100400-second01.md"
            second_archive.write_text("# Progress Archive\n\nsecond\n", encoding="utf-8")
            event = {
                "event": "rollover",
                "version": 1,
                "created_at": "2026-06-11T10:04:00Z",
                "session": "abc123",
                "old_active": "progress-active/abc123/active-20260611100300-first01.md",
                "archive": "progress-archive/abc123/archive-20260611100400-second01.md",
                "new_active": "progress-active/abc123/active-20260611100400-second01.md",
                "archive_sha256": MODULE._sha256_text("# Progress Archive\n\nsecond\n"),
            }
            with (root / "progress-index.ndjson").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertTrue(first_archive.is_file())
            self.assertFalse(second_active.exists())
            self.assertEqual(report.active_path, first_active)
            self.assertIn("missing_latest_active", [issue.code for issue in report.issues])

    def test_doctor_progress_storage_deduplicates_role_confusion_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "progress-active" / "abc123" / "archive-20260611100300-fixed01.md"
            archive.parent.mkdir(parents=True)
            archive.write_text("# Progress Archive\n", encoding="utf-8")
            (root / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text(
                json.dumps(
                    {
                        "event": "rollover",
                        "version": 1,
                        "archive": "progress-active/abc123/archive-20260611100300-fixed01.md",
                        "new_active": "progress-active/abc123/active-20260611100300-fixed01.md",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            report = MODULE.doctor_progress_storage(root / "progress.md")

            matching = [
                issue
                for issue in report.issues
                if issue.code == "archive_role_mismatch"
                and issue.path == "progress-active/abc123/archive-20260611100300-fixed01.md"
            ]
            self.assertEqual(len(matching), 1)

    def test_doctor_progress_storage_reports_active_archive_role_confusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "progress-active" / "abc123" / "archive-20260611100300-fixed01.md"
            active = root / "progress-archive" / "abc123" / "active-20260611100300-fixed01.md"
            archive.parent.mkdir(parents=True)
            active.parent.mkdir(parents=True)
            archive.write_text("# Progress Archive\n", encoding="utf-8")
            active.write_text("# Progress Log\n", encoding="utf-8")
            (root / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text(
                json.dumps(
                    {
                        "event": "rollover",
                        "version": 1,
                        "archive": "progress-active/abc123/archive-20260611100300-fixed01.md",
                        "new_active": "progress-archive/abc123/active-20260611100300-fixed01.md",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            report = MODULE.doctor_progress_storage(root / "progress.md")

            codes = [issue.code for issue in report.issues]
            self.assertIn("archive_role_mismatch", codes)
            self.assertIn("active_role_mismatch", codes)
            self.assertTrue(report.has_errors)

    def test_doctor_progress_storage_reports_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, _active = write_indexed_rollover(root)
            archive.write_text("# Progress Archive\n\nchanged\n", encoding="utf-8")

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertTrue(report.has_errors)
            self.assertIn("hash_mismatch", [issue.code for issue in report.issues])

    def test_doctor_progress_storage_reports_orphan_generated_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_indexed_rollover(root)
            orphan = root / "progress-archive" / "abc123" / "archive-20260611100400-orphan.md"
            orphan.write_text("# Progress Archive\n\norphan\n", encoding="utf-8")

            report = MODULE.doctor_progress_storage(root / "progress.md")

            self.assertFalse(report.has_errors)
            self.assertTrue(report.has_warnings)
            self.assertIn("orphan_segment", [issue.code for issue in report.issues])
            self.assertIn("progress-archive/abc123/archive-20260611100400-orphan.md", report.orphan_paths)

    def test_doctor_progress_storage_reports_no_index_orphan_generated_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text("# Progress Log\n\nlegacy\n", encoding="utf-8")
            active = root / "progress-active" / "abc123" / "active-20260611100400-orphan.md"
            archive = root / "progress-archive" / "abc123" / "archive-20260611100400-orphan.md"
            active.parent.mkdir(parents=True)
            archive.parent.mkdir(parents=True)
            active.write_text("# Progress Log\n\norphan\n", encoding="utf-8")
            archive.write_text("# Progress Archive\n\norphan\n", encoding="utf-8")

            report = MODULE.doctor_progress_storage(progress)

            self.assertFalse(report.has_errors)
            self.assertTrue(report.has_warnings)
            self.assertFalse(report.index_exists)
            self.assertIn("legacy_progress_only", [issue.code for issue in report.issues])
            self.assertEqual(
                {
                    issue.path
                    for issue in report.issues
                    if issue.code == "orphan_segment" and issue.severity == "warn"
                },
                {
                    "progress-active/abc123/active-20260611100400-orphan.md",
                    "progress-archive/abc123/archive-20260611100400-orphan.md",
                },
            )
            self.assertEqual(
                report.orphan_paths,
                (
                    "progress-active/abc123/active-20260611100400-orphan.md",
                    "progress-archive/abc123/archive-20260611100400-orphan.md",
                ),
            )

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

    def test_rollover_creates_separate_active_and_archive_segments_without_modifying_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            original = "# Progress Log\n\n" + "\n".join(
                [
                    "### Auto Record: 2026-06-11 10:00:00",
                    "- Tool: apply_patch",
                    "- Session: abc123",
                    "- Files:",
                    "  - `src/file_0.py` (update)",
                    "",
                    "### Auto Record: 2026-06-11 10:01:00",
                    "- Tool: apply_patch",
                    "- Session: abc123",
                    "- Files:",
                    "  - `src/file_1.py` (update)",
                    "",
                    "### Auto Record: 2026-06-11 10:02:00",
                    "- Tool: apply_patch",
                    "- Session: abc123",
                    "- Files:",
                    "  - `src/file_2.py` (update)",
                    "",
                ]
            )
            progress.write_text(original, encoding="utf-8")

            result = MODULE.rollover_progress(
                progress,
                plan_id="2026-06-11-demo",
                session_key="abc123",
                keep_records=1,
                now="2026-06-11T10:03:00Z",
                nonce="fixed01",
            )

            self.assertTrue(result.changed)
            self.assertEqual(progress.read_text(encoding="utf-8"), original)
            self.assertIn("progress-active/abc123/active-20260611100300-fixed01.md", result.active_path.as_posix())
            self.assertIn("progress-archive/abc123/archive-20260611100300-fixed01.md", result.archive_path.as_posix())
            self.assertTrue(result.active_path.is_file())
            self.assertTrue(result.archive_path.is_file())
            self.assertTrue((root / "progress-index.ndjson").is_file())
            archived = result.archive_path.read_text(encoding="utf-8")
            active = result.active_path.read_text(encoding="utf-8")
            self.assertIn("src/file_0.py", archived)
            self.assertIn("src/file_1.py", archived)
            self.assertNotIn("src/file_2.py", archived)
            self.assertIn("src/file_2.py", active)

    def test_rollover_refuses_to_overwrite_existing_generated_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "# Progress Log\n\n"
                "### Auto Record: 2026-06-11 10:00:00\n"
                "- Tool: apply_patch\n\n"
                "### Auto Record: 2026-06-11 10:01:00\n"
                "- Tool: apply_patch\n\n",
                encoding="utf-8",
            )
            active = root / "progress-active" / "abc123" / "active-20260611100200-fixed01.md"
            archive = root / "progress-archive" / "abc123" / "archive-20260611100200-fixed01.md"
            active.parent.mkdir(parents=True)
            archive.parent.mkdir(parents=True)
            active.write_text("existing active\n", encoding="utf-8")
            archive.write_text("existing archive\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                MODULE.rollover_progress(
                    progress,
                    plan_id="2026-06-11-demo",
                    session_key="abc123",
                    keep_records=1,
                    now="2026-06-11T10:02:00Z",
                    nonce="fixed01",
                )

            self.assertEqual(active.read_text(encoding="utf-8"), "existing active\n")
            self.assertEqual(archive.read_text(encoding="utf-8"), "existing archive\n")
            self.assertFalse((root / "progress-index.ndjson").exists())

    def test_current_active_progress_prefers_latest_rollover_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "progress-active" / "abc123" / "active-20260611100300-fixed01.md"
            active.parent.mkdir(parents=True)
            active.write_text("# Progress Log\n\nactive\n", encoding="utf-8")
            (root / "progress.md").write_text("# Progress Log\n\nlegacy\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text(
                '{"event":"rollover","version":1,"new_active":"progress-active/abc123/active-20260611100300-fixed01.md"}\n',
                encoding="utf-8",
            )

            self.assertEqual(MODULE.current_active_progress(root / "progress.md"), active)

    def test_current_active_progress_ignores_archive_directory_as_active_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "progress-archive" / "abc123" / "archive-20260611100300-fixed01.md"
            archive.parent.mkdir(parents=True)
            archive.write_text("# Progress Archive\n\nsealed\n", encoding="utf-8")
            progress = root / "progress.md"
            progress.write_text("# Progress Log\n\nlegacy\n", encoding="utf-8")
            (root / "progress-index.ndjson").write_text(
                '{"event":"rollover","version":1,"new_active":"progress-archive/abc123/archive-20260611100300-fixed01.md"}\n',
                encoding="utf-8",
            )

            self.assertEqual(MODULE.current_active_progress(progress), progress)

    def test_rollover_uses_current_active_segment_after_previous_rollover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            original = "# Progress Log\n\n" + "\n".join(
                [
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
                    "### Auto Record: 2026-06-11 10:02:00",
                    "- Tool: apply_patch",
                    "- Files:",
                    "  - `src/file_2.py` (update)",
                    "",
                    "### Auto Record: 2026-06-11 10:03:00",
                    "- Tool: apply_patch",
                    "- Files:",
                    "  - `src/file_3.py` (update)",
                    "",
                ]
            )
            progress.write_text(original, encoding="utf-8")

            first = MODULE.rollover_progress(
                progress,
                plan_id="2026-06-11-demo",
                session_key="abc123",
                keep_records=2,
                now="2026-06-11T10:04:00Z",
                nonce="first",
            )
            with first.active_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "\n### Auto Record: 2026-06-11 10:05:00\n"
                    "- Tool: apply_patch\n"
                    "- Files:\n"
                    "  - `src/file_4.py` (update)\n"
                )

            second = MODULE.rollover_progress(
                progress,
                plan_id="2026-06-11-demo",
                session_key="abc123",
                keep_records=1,
                now="2026-06-11T10:06:00Z",
                nonce="second",
            )

            self.assertEqual(progress.read_text(encoding="utf-8"), original)
            second_archive = second.archive_path.read_text(encoding="utf-8")
            second_active = second.active_path.read_text(encoding="utf-8")
            self.assertIn("src/file_2.py", second_archive)
            self.assertIn("src/file_3.py", second_archive)
            self.assertNotIn("src/file_4.py", second_archive)
            self.assertIn("src/file_4.py", second_active)
            index = (root / "progress-index.ndjson").read_text(encoding="utf-8")
            self.assertIn("progress-active/abc123/active-20260611100400-first.md", index)
            self.assertIn("progress-active/abc123/active-20260611100600-second.md", index)

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
