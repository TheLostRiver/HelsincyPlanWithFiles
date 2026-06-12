# PWF Doctor Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/pwf-doctor` a high-safety, reliable, and human-friendly read-only auditor for append-only progress rollover storage.

**Architecture:** Keep all progress storage integrity checks in `.codex/skills/planning-with-files/scripts/progress_lifecycle.py` as a pure read-only report API. Keep `.codex/skills/planning-with-files/scripts/plan.py` responsible for CLI flags, formatting, JSON output, and exit-code policy. The doctor command must never repair, delete, move, overwrite, compact, or create progress files.

**Tech Stack:** Python standard library, `argparse`, `dataclasses`, Markdown files, NDJSON, `unittest`, PowerShell verification commands.

---

## Scope

This plan hardens `plan.py doctor` for the append-only rollover model introduced in `docs/APPEND_ONLY_PROGRESS_ROLLOVER_DESIGN.md`.

It adds diagnostics for:

- `progress-index.ndjson` syntax and rollover event schema.
- Active/archive directory role confusion.
- Missing latest active progress segments.
- Missing indexed archive files.
- SHA-256 mismatches for indexed archive and active segment files.
- Orphan generated active/archive files that are not referenced by the index.
- Legacy plans that have only `progress.md`.
- Legacy `progress.archive.md` cold storage files.
- Default concise output, `--verbose`, `--json`, and `--strict`.

## Non-Goals

- Do not repair index files.
- Do not move misplaced files.
- Do not delete orphan files.
- Do not migrate `progress.archive.md`.
- Do not change `plan.py compact` rollover behavior.
- Do not auto-inject archive contents into prompt context.
- Do not add a UI for archive browsing.

## Safety Policy

`doctor` is a report-only command.

Severity policy:

| Severity | Default exit code | Meaning |
|----------|-------------------|---------|
| `ok` | `0` | Healthy state. |
| `info` | `0` | Useful context, no action needed. |
| `warn` | `0` | Degraded or unusual state, user may inspect manually. |
| `error` | non-zero | Integrity or safety issue that can make writes/audit chain unsafe. |

`--strict` returns non-zero when any `warn` or `error` exists.

Default `error` cases:

- Invalid `progress-index.ndjson` line.
- Indexed path escapes the progress root.
- Indexed active file is not under `progress-active/`.
- Indexed archive file is not under `progress-archive/`.
- Latest indexed active segment is missing.
- Indexed SHA-256 does not match file contents.
- Archive-shaped file appears under `progress-active/`.
- Active-shaped file appears under `progress-archive/`.

Default `warn` cases:

- Indexed non-latest archive file is missing.
- Orphan generated segment exists but is not referenced by the index.
- Unknown rollover event version.
- Rollover event lacks optional count metadata.

Default `info` cases:

- No `progress-index.ndjson` exists and legacy `progress.md` is present.
- `progress.archive.md` exists as old-format cold storage.

## Files

- Modify: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py`
  - Add structured progress storage doctor dataclasses.
  - Add raw NDJSON parser that preserves line-level diagnostics.
  - Add path role validation for active/archive references.
  - Add hash verification and orphan segment scanning.
  - Add a pure `doctor_progress_storage(progress_path)` API.

- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
  - Add `doctor --verbose`, `doctor --json`, and `doctor --strict`.
  - Render concise human output by default.
  - Merge progress storage doctor severity into existing doctor exit code.

- Modify: `tests/test_progress_compaction.py`
  - Cover pure progress storage diagnostics.

- Modify: `tests/test_plan_doctor.py`
  - Cover CLI output, JSON output, strict exit code, and no-mutation behavior.

- Modify: `.codex/skills/pwf-doctor/SKILL.md`
  - Document report-only behavior and safe interpretation.

- Modify: `.codex/skills/planning-with-files/SKILL.md`
  - Document doctor integrity checks for rollover storage.

- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/APPEND_ONLY_PROGRESS_ROLLOVER_DESIGN.md`
  - Document the new diagnostics and the no automatic repair guarantee.

- Modify: `tests/test_project_consistency.py`
  - Keep docs and user-facing guarantees synchronized.

---

## Diagnostic Data Model

Add these dataclasses near `RolloverResult` in `progress_lifecycle.py`:

```python
@dataclass(frozen=True)
class ProgressDoctorIssue:
    severity: str
    code: str
    path: str
    message: str
    effect: str
    action: str


@dataclass(frozen=True)
class ProgressDoctorReport:
    progress_path: Path
    active_path: Path
    index_path: Path
    index_exists: bool
    rollover_events: int
    referenced_paths: tuple[str, ...]
    orphan_paths: tuple[str, ...]
    issues: tuple[ProgressDoctorIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warn" for issue in self.issues)
```

Use stable machine-readable `code` values:

```python
INVALID_INDEX_JSON = "invalid_index_json"
INVALID_EVENT_SCHEMA = "invalid_event_schema"
PATH_ESCAPES_ROOT = "path_escapes_root"
ACTIVE_ROLE_MISMATCH = "active_role_mismatch"
ARCHIVE_ROLE_MISMATCH = "archive_role_mismatch"
MISSING_LATEST_ACTIVE = "missing_latest_active"
MISSING_ARCHIVE = "missing_archive"
HASH_MISMATCH = "hash_mismatch"
ORPHAN_SEGMENT = "orphan_segment"
LEGACY_PROGRESS_ONLY = "legacy_progress_only"
LEGACY_ARCHIVE_FILE = "legacy_archive_file"
```

---

### Task 1: Add Pure Progress Storage Doctor Tests

**Files:**
- Modify: `tests/test_progress_compaction.py`

- [ ] **Step 1: Add a helper for indexed rollover fixtures**

Add this helper above `class ProgressCompactionTests`:

```python
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
```

Also add `import json` at the top of the file.

- [ ] **Step 2: Add healthy and legacy tests**

Add these tests to `ProgressCompactionTests`:

```python
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
```

- [ ] **Step 3: Add corruption and path safety tests**

Add:

```python
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
```

- [ ] **Step 4: Add hash and orphan tests**

Add:

```python
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
```

- [ ] **Step 5: Run the new pure tests and confirm they fail**

Run:

```powershell
python -m unittest `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_reports_healthy_rollover_chain `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_accepts_legacy_progress_without_index `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_reports_invalid_index_json `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_reports_missing_latest_active `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_reports_active_archive_role_confusion `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_reports_hash_mismatch `
  tests.test_progress_compaction.ProgressCompactionTests.test_doctor_progress_storage_reports_orphan_generated_segments -v
```

Expected before implementation: fail with `AttributeError: module 'progress_lifecycle' has no attribute 'doctor_progress_storage'`.

---

### Task 2: Implement Pure Read-Only Progress Storage Diagnostics

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py`

- [ ] **Step 1: Add dataclasses and constants**

Add the dataclasses and code constants from the "Diagnostic Data Model" section near `RolloverResult`.

- [ ] **Step 2: Add safe reference helpers**

Add below `_sha256_text`:

```python
def _sha256_file_text(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8", errors="replace"))


def _is_hex_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_safe_relative_ref(value: str) -> bool:
    if not value or "\\" in value:
        return False
    parts = PurePosixPath(value).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts) and not PurePosixPath(value).is_absolute()


def _is_archive_segment_ref(value: str) -> bool:
    parts = PurePosixPath(value).parts
    return (
        len(parts) >= 3
        and parts[0] == "progress-archive"
        and all(part not in {"", ".", ".."} for part in parts)
        and parts[-1].startswith("archive-")
        and parts[-1].endswith(".md")
    )


def _issue(severity: str, code: str, path: str, message: str, effect: str, action: str) -> ProgressDoctorIssue:
    return ProgressDoctorIssue(
        severity=severity,
        code=code,
        path=path,
        message=message,
        effect=effect,
        action=action,
    )
```

- [ ] **Step 3: Add raw index reader**

Add:

```python
def _read_index_events_with_issues(index_path: Path) -> tuple[list[tuple[int, dict[str, object]]], list[ProgressDoctorIssue]]:
    if not index_path.is_file():
        return [], []
    events: list[tuple[int, dict[str, object]]] = []
    issues: list[ProgressDoctorIssue] = []
    for line_number, line in enumerate(index_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(
                _issue(
                    "error",
                    INVALID_INDEX_JSON,
                    f"{index_path.name}:{line_number}",
                    f"invalid JSON: {exc.msg}",
                    "Doctor cannot fully trust the rollover event chain after this line.",
                    "Inspect progress-index.ndjson manually; PWF did not modify files.",
                )
            )
            continue
        if not isinstance(payload, dict):
            issues.append(
                _issue(
                    "error",
                    INVALID_EVENT_SCHEMA,
                    f"{index_path.name}:{line_number}",
                    "index line is not a JSON object",
                    "The rollover event chain contains data that cannot describe progress storage.",
                    "Inspect progress-index.ndjson manually; PWF did not modify files.",
                )
            )
            continue
        events.append((line_number, payload))
    return events, issues
```

- [ ] **Step 4: Add reference validation**

Add:

```python
def _resolve_index_ref(progress_path: Path, value: object, *, role: str, line_number: int) -> tuple[str | None, Path | None, list[ProgressDoctorIssue]]:
    index_path = progress_index_path(progress_path)
    if not isinstance(value, str) or not value:
        return None, None, [
            _issue(
                "error",
                INVALID_EVENT_SCHEMA,
                f"{index_path.name}:{line_number}",
                f"missing {role} path",
                "The rollover event cannot be used safely.",
                "Inspect progress-index.ndjson manually; PWF did not modify files.",
            )
        ]
    if not _is_safe_relative_ref(value):
        return value, None, [
            _issue(
                "error",
                PATH_ESCAPES_ROOT,
                value,
                f"{role} path is not a safe relative path",
                "A malformed reference could point outside the progress storage root.",
                "Inspect progress-index.ndjson manually; PWF did not modify files.",
            )
        ]
    candidate = progress_path.parent / value
    try:
        candidate.resolve().relative_to(progress_path.parent.resolve())
    except (OSError, ValueError):
        return value, None, [
            _issue(
                "error",
                PATH_ESCAPES_ROOT,
                value,
                f"{role} path escapes the progress storage root",
                "A malformed reference could point outside the progress storage root.",
                "Inspect progress-index.ndjson manually; PWF did not modify files.",
            )
        ]
    return value, candidate, []
```

- [ ] **Step 5: Add `doctor_progress_storage`**

Implement:

```python
def doctor_progress_storage(progress_path: Path) -> ProgressDoctorReport:
    index_path = progress_index_path(progress_path)
    events_with_lines, issues = _read_index_events_with_issues(index_path)
    rollover_events = [(line, event) for line, event in events_with_lines if event.get("event") == "rollover"]
    referenced: set[str] = set()
    active_path = progress_path

    if not index_path.is_file():
        if progress_path.is_file():
            issues.append(
                _issue(
                    "info",
                    LEGACY_PROGRESS_ONLY,
                    progress_path.name,
                    "legacy progress.md is the active progress file",
                    "No append-only rollover index exists yet.",
                    "No action is needed.",
                )
            )
        legacy_archive = progress_path.parent / "progress.archive.md"
        if legacy_archive.is_file():
            issues.append(
                _issue(
                    "info",
                    LEGACY_ARCHIVE_FILE,
                    "progress.archive.md",
                    "legacy progress archive file is present",
                    "This file is old-format cold storage and is not modified by rollover.",
                    "Keep it for audit, or remove it manually only if you no longer need it.",
                )
            )
        return ProgressDoctorReport(progress_path, active_path, index_path, False, 0, (), (), tuple(issues))

    for line_number, event in rollover_events:
        if event.get("version") != 1:
            issues.append(
                _issue(
                    "warn",
                    INVALID_EVENT_SCHEMA,
                    f"{index_path.name}:{line_number}",
                    f"unexpected rollover version={event.get('version')!r}",
                    "This doctor version may not understand every field in the event.",
                    "Upgrade PWF if this was written by a newer version.",
                )
            )

        archive_ref, archive_path, archive_issues = _resolve_index_ref(
            progress_path,
            event.get("archive"),
            role="archive",
            line_number=line_number,
        )
        issues.extend(archive_issues)
        if archive_ref:
            referenced.add(archive_ref)
            if not _is_archive_segment_ref(archive_ref):
                issues.append(
                    _issue(
                        "error",
                        ARCHIVE_ROLE_MISMATCH,
                        archive_ref,
                        "archive path is not under progress-archive/",
                        "Archive and active directories are role-separated to prevent writes to sealed history.",
                        "Inspect the index manually; PWF did not move files.",
                    )
                )
            elif archive_path is not None and not archive_path.is_file():
                issues.append(
                    _issue(
                        "warn",
                        MISSING_ARCHIVE,
                        archive_ref,
                        "indexed archive file is missing",
                        "Historical auto records referenced by this event may be unavailable.",
                        "Inspect storage manually; PWF did not recreate files.",
                    )
                )
            elif archive_path is not None and _is_hex_sha256(event.get("archive_sha256")):
                actual = _sha256_file_text(archive_path)
                if actual != event["archive_sha256"]:
                    issues.append(
                        _issue(
                            "error",
                            HASH_MISMATCH,
                            archive_ref,
                            "archive SHA-256 does not match progress-index.ndjson",
                            "The archive audit chain is not trustworthy.",
                            "Inspect the file and index manually; PWF did not modify either file.",
                        )
                    )

        active_ref, candidate_active, active_issues = _resolve_index_ref(
            progress_path,
            event.get("new_active"),
            role="new_active",
            line_number=line_number,
        )
        issues.extend(active_issues)
        if active_ref:
            referenced.add(active_ref)
            is_latest = (line_number, event) == rollover_events[-1]
            if not _is_active_segment_ref(active_ref):
                issues.append(
                    _issue(
                        "error",
                        ACTIVE_ROLE_MISMATCH,
                        active_ref,
                        "active path is not under progress-active/",
                        "Hooks must only append to active progress segments.",
                        "Inspect the index manually; PWF did not move files.",
                    )
                )
            elif candidate_active is not None and not candidate_active.is_file() and is_latest:
                issues.append(
                    _issue(
                        "error",
                        MISSING_LATEST_ACTIVE,
                        active_ref,
                        "latest indexed active progress segment is missing",
                        "Hooks may fall back to legacy progress.md instead of the intended active segment.",
                        "Inspect storage manually; PWF did not recreate files.",
                    )
                )
            elif candidate_active is not None and candidate_active.is_file():
                if is_latest:
                    active_path = candidate_active
                if _is_hex_sha256(event.get("new_active_sha256")):
                    actual = _sha256_file_text(candidate_active)
                    if actual != event["new_active_sha256"]:
                        issues.append(
                            _issue(
                                "error",
                                HASH_MISMATCH,
                                active_ref,
                                "active segment SHA-256 does not match progress-index.ndjson",
                                "The active progress audit chain is not trustworthy.",
                                "Inspect the file and index manually; PWF did not modify either file.",
                            )
                        )

    orphan_paths: list[str] = []
    for directory, matcher in (("progress-active", "active-*.md"), ("progress-archive", "archive-*.md")):
        base = progress_path.parent / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob(f"**/{matcher}")):
            rel = _relative_to_progress_root(progress_path, path)
            if rel not in referenced:
                orphan_paths.append(rel)
                issues.append(
                    _issue(
                        "warn",
                        ORPHAN_SEGMENT,
                        rel,
                        "generated progress segment is not referenced by progress-index.ndjson",
                        "A previous rollover may have created files before appending the index.",
                        "Keep it for analysis, or remove manually only if you are sure it is no longer needed.",
                    )
                )

    legacy_archive = progress_path.parent / "progress.archive.md"
    if legacy_archive.is_file():
        issues.append(
            _issue(
                "info",
                LEGACY_ARCHIVE_FILE,
                "progress.archive.md",
                "legacy progress archive file is present",
                "The new append-only rollover does not write to this file.",
                "Keep it for audit, or remove it manually only if you no longer need it.",
            )
        )

    return ProgressDoctorReport(
        progress_path=progress_path,
        active_path=active_path,
        index_path=index_path,
        index_exists=True,
        rollover_events=len(rollover_events),
        referenced_paths=tuple(sorted(referenced)),
        orphan_paths=tuple(orphan_paths),
        issues=tuple(issues),
    )
```

- [ ] **Step 6: Run pure tests**

Run the Task 1 command again.

Expected after implementation: all listed tests pass.

- [ ] **Step 7: Commit**

```powershell
git add .codex/skills/planning-with-files/scripts/progress_lifecycle.py tests/test_progress_compaction.py
git commit -m "test: cover progress storage doctor diagnostics"
```

---

### Task 3: Add CLI Flags, Human Output, JSON Output, and Strict Mode

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Modify: `tests/test_plan_doctor.py`

- [ ] **Step 1: Add CLI tests**

Add to `PlanDoctorTests`:

```python
    def test_doctor_reports_progress_storage_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            active = plan_dir / "progress-active" / "abc123" / "active-20260611100300-fixed01.md"
            archive = plan_dir / "progress-archive" / "abc123" / "archive-20260611100300-fixed01.md"
            active.parent.mkdir(parents=True)
            archive.parent.mkdir(parents=True)
            active_text = "# Progress Log\n\nactive\n"
            archive_text = "# Progress Archive\n\nsealed\n"
            active.write_text(active_text, encoding="utf-8")
            archive.write_text(archive_text, encoding="utf-8")
            (plan_dir / "progress-index.ndjson").write_text(
                json.dumps(
                    {
                        "event": "rollover",
                        "version": 1,
                        "archive": "progress-archive/abc123/archive-20260611100300-fixed01.md",
                        "new_active": "progress-active/abc123/active-20260611100300-fixed01.md",
                        "archive_sha256": hashlib.sha256(archive_text.encode("utf-8")).hexdigest(),
                        "new_active_sha256": hashlib.sha256(active_text.encode("utf-8")).hexdigest(),
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("progress storage: ok", result.stdout)
            self.assertIn("progress active: progress-active/abc123/active-20260611100300-fixed01.md", result.stdout)
            self.assertIn("progress index: 1 rollover event", result.stdout)
            self.assertIn("No automatic repair was attempted.", result.stdout)

    def test_doctor_progress_storage_error_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            (plan_dir / "progress-index.ndjson").write_text("{not json\n", encoding="utf-8")

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 1)
            self.assertIn("progress storage: error", result.stdout)
            self.assertIn("[error] invalid_index_json", result.stdout)

    def test_doctor_strict_returns_nonzero_for_progress_storage_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            orphan = plan_dir / "progress-archive" / "abc123" / "archive-20260611100400-orphan.md"
            orphan.parent.mkdir(parents=True)
            orphan.write_text("# Progress Archive\n", encoding="utf-8")

            normal = run_plan(root, "doctor")
            strict = run_plan(root, "doctor", "--strict")

            self.assertEqual(normal.returncode, 0, normal.stderr)
            self.assertEqual(strict.returncode, 1)
            self.assertIn("[warn] orphan_segment", strict.stdout)

    def test_doctor_json_reports_progress_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(root, "doctor", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("progress_storage", payload)
            self.assertEqual(payload["progress_storage"]["status"], "info")
            self.assertIn("issues", payload["progress_storage"])

    def test_doctor_does_not_modify_progress_storage_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            index = plan_dir / "progress-index.ndjson"
            index.write_text("{not json\n", encoding="utf-8")
            before = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (plan_dir / "progress.md", index)
            }

            result = run_plan(root, "doctor", "--verbose")

            after = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (plan_dir / "progress.md", index)
            }
            self.assertEqual(result.returncode, 1)
            self.assertEqual(before, after)
```

- [ ] **Step 2: Run CLI tests and confirm they fail**

Run:

```powershell
python -m unittest `
  tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_progress_storage_summary `
  tests.test_plan_doctor.PlanDoctorTests.test_doctor_progress_storage_error_returns_nonzero `
  tests.test_plan_doctor.PlanDoctorTests.test_doctor_strict_returns_nonzero_for_progress_storage_warning `
  tests.test_plan_doctor.PlanDoctorTests.test_doctor_json_reports_progress_storage `
  tests.test_plan_doctor.PlanDoctorTests.test_doctor_does_not_modify_progress_storage_files -v
```

Expected before implementation: failures because `doctor` has no flags and no progress storage output.

- [ ] **Step 3: Add formatting helpers**

Add near `_progress_doctor_warning` in `plan.py`:

```python
def _relative_to_plan_root(paths: planning_state.PlanningPaths, path: Path) -> str:
    try:
        return path.relative_to(paths.root).as_posix()
    except ValueError:
        return str(path)


def _progress_storage_status(report: progress_lifecycle.ProgressDoctorReport, strict: bool = False) -> str:
    if report.has_errors:
        return "error"
    if report.has_warnings:
        return "warning" if strict else "warning"
    if report.issues:
        return "info"
    return "ok"


def _progress_storage_summary_lines(paths: planning_state.PlanningPaths, report: progress_lifecycle.ProgressDoctorReport, *, verbose: bool = False) -> list[str]:
    status = _progress_storage_status(report)
    event_word = "event" if report.rollover_events == 1 else "events"
    lines = [
        f"progress storage: {status}",
        f"progress active: {_relative_to_plan_root(paths, report.active_path)}",
        f"progress index: {report.rollover_events} rollover {event_word}",
    ]
    for issue in report.issues:
        if issue.severity == "info" and not verbose:
            continue
        lines.append(f"[{issue.severity}] {issue.code}: {issue.message}")
        lines.append(f"  path: {issue.path}")
        if verbose:
            lines.append(f"  effect: {issue.effect}")
            lines.append(f"  action: {issue.action}")
    lines.append("No automatic repair was attempted.")
    return lines
```

- [ ] **Step 4: Add JSON helpers**

Add:

```python
def _progress_storage_json(paths: planning_state.PlanningPaths, report: progress_lifecycle.ProgressDoctorReport) -> dict[str, object]:
    return {
        "status": _progress_storage_status(report),
        "active_path": _relative_to_plan_root(paths, report.active_path),
        "index_path": _relative_to_plan_root(paths, report.index_path),
        "index_exists": report.index_exists,
        "rollover_events": report.rollover_events,
        "referenced_paths": list(report.referenced_paths),
        "orphan_paths": list(report.orphan_paths),
        "issues": [
            {
                "severity": issue.severity,
                "code": issue.code,
                "path": issue.path,
                "message": issue.message,
                "effect": issue.effect,
                "action": issue.action,
            }
            for issue in report.issues
        ],
    }
```

- [ ] **Step 5: Extend `doctor` signature and CLI parser**

Change:

```python
def doctor(root: Path) -> int:
```

to:

```python
def doctor(root: Path, *, verbose: bool = False, as_json: bool = False, strict: bool = False) -> int:
```

Replace `subparsers.add_parser("doctor", help=_help("doctor"))` with:

```python
doctor_parser = subparsers.add_parser("doctor", help=_help("doctor"))
doctor_parser.add_argument("--verbose", action="store_true")
doctor_parser.add_argument("--json", action="store_true", dest="as_json")
doctor_parser.add_argument("--strict", action="store_true")
```

Replace:

```python
if args.command == "doctor":
    return doctor(root)
```

with:

```python
if args.command == "doctor":
    return doctor(root, verbose=args.verbose, as_json=args.as_json, strict=args.strict)
```

- [ ] **Step 6: Merge progress storage report into doctor**

Inside `doctor`, after attestation status and before context lines:

```python
progress_report = None
if paths is not None:
    progress_report = progress_lifecycle.doctor_progress_storage(paths.progress)
    if progress_report.has_errors or (strict and progress_report.has_warnings):
        ok = False
    lines.extend(_progress_storage_summary_lines(paths, progress_report, verbose=verbose))
```

For `as_json`, return JSON instead of text:

```python
if as_json:
    payload: dict[str, object] = {
        "ok": ok,
        "strict": strict,
        "checks": lines,
    }
    if paths is not None and progress_report is not None:
        payload["progress_storage"] = _progress_storage_json(paths, progress_report)
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if ok else 1
```

Place this block immediately before `print("\n".join(lines))`.

- [ ] **Step 7: Run CLI tests**

Run the Task 3 command again.

Expected after implementation: all listed tests pass.

- [ ] **Step 8: Commit**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_doctor.py
git commit -m "feat: add read-only progress storage doctor"
```

---

### Task 4: Update User-Facing Documentation

**Files:**
- Modify: `.codex/skills/pwf-doctor/SKILL.md`
- Modify: `.codex/skills/planning-with-files/SKILL.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/APPEND_ONLY_PROGRESS_ROLLOVER_DESIGN.md`
- Modify: `tests/test_project_consistency.py`

- [ ] **Step 1: Add consistency test**

Add to `tests/test_project_consistency.py`:

```python
    def test_docs_document_doctor_progress_storage_audit(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        skill = read_text(".codex/skills/pwf-doctor/SKILL.md")
        design = read_text("docs/APPEND_ONLY_PROGRESS_ROLLOVER_DESIGN.md")
        combined = "\n".join([readme_cn, readme_en, faq, skill, design])

        for phrase in (
            "progress storage",
            "progress-index.ndjson",
            "progress-active",
            "progress-archive",
            "No automatic repair was attempted.",
            "--strict",
            "--json",
        ):
            self.assertIn(phrase, combined)
```

- [ ] **Step 2: Run the consistency test and confirm it fails**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_doctor_progress_storage_audit -v
```

Expected before docs update: fail because the new phrases are not yet documented.

- [ ] **Step 3: Update docs**

Add concise user-facing text with these facts:

```markdown
`/pwf-doctor` also audits append-only progress storage. It checks `progress-index.ndjson`, active/archive directory roles, missing indexed files, hash mismatches, and orphan generated segments. It is report-only: it prints `No automatic repair was attempted.` and never deletes, moves, overwrites, compacts, or recreates progress files. Use `plan.py doctor --verbose` for effect/action details, `--json` for machine-readable output, and `--strict` to fail on warnings.
```

For Chinese docs, use:

```markdown
`/pwf-doctor` 还会审计 append-only progress storage：检查 `progress-index.ndjson`、`progress-active/` 与 `progress-archive/` 的目录角色、索引文件缺失、hash mismatch，以及未被 index 引用的 generated segment。它只报告，不自动修复；输出会明确包含 `No automatic repair was attempted.`，并且不会删除、移动、覆盖、compact 或重建任何 progress 文件。需要细节时用 `plan.py doctor --verbose`，需要机器可读输出时用 `--json`，需要 CI 式严格失败时用 `--strict`。
```

- [ ] **Step 4: Run consistency test**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_doctor_progress_storage_audit -v
```

Expected after docs update: pass.

- [ ] **Step 5: Commit**

```powershell
git add .codex/skills/pwf-doctor/SKILL.md .codex/skills/planning-with-files/SKILL.md README.md README.en.md docs/FAQ.md CHANGELOG.md docs/APPEND_ONLY_PROGRESS_ROLLOVER_DESIGN.md tests/test_project_consistency.py
git commit -m "docs: document progress storage doctor audit"
```

---

### Task 5: Full Verification and Regression Sweep

**Files:**
- No source edits expected unless verification finds a defect.

- [ ] **Step 1: Run focused doctor and rollover tests**

Run:

```powershell
python -m pytest tests/test_progress_compaction.py tests/test_plan_doctor.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run hook and CLI regression tests related to current active progress**

Run:

```powershell
python -m pytest tests/test_plan_cli.py tests/test_hooks.py -k "progress or compact or rollover or active_progress or doctor" -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run project consistency tests**

Run:

```powershell
python -m pytest tests/test_project_consistency.py tests/test_pwf_commands.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 5: Manual smoke test**

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py --root . doctor --verbose
python .codex\skills\planning-with-files\scripts\plan.py --root . doctor --json
```

Expected:

- Human output includes `progress storage:` and `No automatic repair was attempted.`
- JSON output parses with `json.loads`.
- No tracked or ignored progress files are modified by either command.

- [ ] **Step 6: Commit any verification fixes**

If verification required changes:

```powershell
git add <changed-files>
git commit -m "fix: stabilize progress storage doctor verification"
```

If no changes were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Report-only guarantee: covered by Safety Policy, docs, no-mutation CLI test.
- Index parse/schema diagnostics: covered by Task 1 and Task 2.
- Active/archive folder separation: covered by role confusion tests and `_is_active_segment_ref` / `_is_archive_segment_ref`.
- Missing latest active: covered as default `error`.
- Missing archive: covered as `warn`.
- Hash mismatch: covered as default `error`.
- Orphan generated files: covered as `warn`.
- Human-friendly output: covered by CLI summary tests and docs.
- `--verbose`, `--json`, `--strict`: covered by Task 3.

Placeholder scan:

- No deferred placeholder markers.
- No unfinished-task markers.
- No unspecified "add appropriate tests" step.
- Every task has exact file paths and verification commands.

Risk notes:

- `doctor_progress_storage()` must not call `mkdir`, `write_text`, `open("w")`, `open("a")`, `unlink`, `rename`, `replace`, `rollover_progress()`, or `compact_progress()`.
- Default output should not print file contents from progress/archive files.
- Existing `doctor` return-code behavior for hook, planning file, and attestation failures must remain unchanged.
- Existing tests that assert `"progress.md has N auto records"` should keep passing even when the active path is a generated segment, because the current user-facing wording already uses `progress.md` as a stable label.
