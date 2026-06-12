# Append-Only Progress Rollover Design

## Goal

Replace progress compaction's overwrite-based storage model with an append-only rollover model that never deletes or overwrites progress/archive files, while preserving auditability and bounded prompt context.

## Problem

The historical `plan.py compact` implementation archived old auto records and then rewrote `progress.md` with a managed summary plus recent records. Path validation lowered the immediate risk, but the deeper safety problem remained: compact had overwrite semantics for PWF-owned files. A future bug in path resolution, archive selection, or progress rewriting could again damage user-visible files.

The desired model is stricter:

- The tool must not delete progress history.
- The tool must not overwrite existing progress/archive files.
- Archive and active records must live in separate directories so their roles cannot be confused.
- Old records must remain available for audit and incident analysis.
- Users can manually delete archive files if they choose; the tool must not do that for them.

## Directory Layout

For named tasks:

```text
.planning/<plan-id>/
  task_plan.md
  findings.md
  progress.md
  progress-index.ndjson
  progress-active/
    <session-key>/
      active-20260611173000-abc123.md
  progress-archive/
    <session-key>/
      archive-20260611173000-abc123.md
```

For legacy root-level plans:

```text
.
  task_plan.md
  findings.md
  progress.md
  progress-index.ndjson
  progress-active/
    <session-key>/
      active-20260611173000-abc123.md
  progress-archive/
    <session-key>/
      archive-20260611173000-abc123.md
```

## Hard Rules

- `progress-active/` contains only writable active progress segments.
- `progress-archive/` contains only sealed archive files.
- `progress-index.ndjson` is append-only; each line is one JSON event.
- `progress.md` remains the legacy initial segment. After the first rollover, compact must not rewrite it.
- Generated active and archive filenames must be unique and created with exclusive-create semantics.
- `plan.py compact` must not accept user-provided archive paths.
- The tool must never place an archive file in `progress-active/`.
- The tool must never place an active segment in `progress-archive/`.
- The tool must never delete archive files, active segment files, or the legacy `progress.md`.

## Event Model

The index records objective events. The current implementation writes this event type:

```json
{"event":"rollover","version":1,"created_at":"2026-06-11T09:40:00Z","session":"abc123","old_active":"progress.md","archive":"progress-archive/abc123/archive-20260611094000-8f3a2c.md","new_active":"progress-active/abc123/active-20260611094000-8f3a2c.md","source_sha256":"...","archive_sha256":"...","new_active_sha256":"...","archived_auto_records":72,"kept_recent_auto_records":30}
```

The index is not a source of executable instructions. Hook rendering must treat it as structured data only.

## Rollover Behavior

`plan.py compact` becomes a rollover command:

1. Resolve the effective plan using the existing session-aware planning resolver.
2. Resolve the current active progress segment:
   - If `progress-index.ndjson` has a valid latest `rollover` event, use its `new_active`.
   - Otherwise use `progress.md`.
3. Parse auto records from the current active segment.
4. If there are at most `--keep-records` records, make no changes.
5. Create a new archive file under `progress-archive/<session-key>/`.
6. Write the archived records and metadata to that archive file.
7. Create a new active file under `progress-active/<session-key>/`.
8. Write a header, continuation metadata, manual context, and the kept recent auto records to the new active file.
9. Append a rollover event to `progress-index.ndjson`.
10. Leave the old active file unchanged.

The ordering favors auditability. If writing a new archive or active file fails, no index event is appended. If appending the index fails after both files are created, the files remain orphaned but harmless; a later doctor check can report them.

## Archive File Format

```markdown
# Progress Archive

- Version: 1
- Plan-ID: 2026-06-11-demo
- Session: abc123
- Source-Progress: progress.md
- Source-SHA256: <sha256>
- Created-At: 2026-06-11T09:40:00Z
- Archived Auto Records: 72
- Kept Recent Auto Records: 30

---BEGIN ARCHIVED AUTO RECORDS---
### Auto Record: 2026-06-10 09:00:00
- Tool: apply_patch
- Files:
  - `src/example.py` (update)
---END ARCHIVED AUTO RECORDS---
```

Archive files are sealed after creation. Later compact operations create new archive files.

## Active Segment Format

```markdown
# Progress Log

- Version: 1
- Plan-ID: 2026-06-11-demo
- Session: abc123
- Continued-From: progress.md
- Continued-From-SHA256: <sha256>
- Archive: progress-archive/abc123/archive-20260611094000-8f3a2c.md
- Created-At: 2026-06-11T09:40:00Z

## Recent Progress

### Auto Record: 2026-06-11 09:35:00
- Tool: apply_patch
- Files:
  - `src/current.py` (update)
```

The new active segment is not an empty template. It carries enough metadata to connect it to the sealed source and archive.

## Hook Behavior

`append_progress()` must write to the current active segment, not always to `paths.progress`.

Resolution order:

1. If there is a valid latest `rollover` event, append to its `new_active`.
2. If no valid index exists, append to `progress.md`.
3. If the indexed active segment is invalid, outside `progress-active/`, or missing, ignore that event and fall back to the latest valid event or legacy `progress.md`.

Prompt context reads:

1. The active segment for recent progress records.
2. Existing plan and findings behavior unchanged.

This keeps context bounded without rewriting old logs.

## CLI Behavior

`plan.py compact` retains the user-facing command name for compatibility, but the help text should describe rollover:

```text
Roll over old progress auto records into append-only active/archive segments.
```

Arguments:

- Keep `--keep-records N`.
- Keep `--dry-run`.
- Remove `--archive PATH`, or keep it temporarily as a rejected compatibility argument that prints a clear message:

```text
archive paths are generated automatically; --archive is no longer supported
```

## Doctor and Status Behavior

`plan.py status` and `plan.py doctor` count records through the latest valid active segment, so rollover recommendations follow the file hooks are currently appending to:

```text
progress: 126 auto records, compact recommended
```

Future doctor diagnostics can report:

- Missing indexed active segment.
- Archive file accidentally placed under `progress-active/`.
- Active file accidentally placed under `progress-archive/`.
- Invalid index JSON lines.
- Orphan generated progress files not referenced by the index.

Doctor should only report. It must not repair by deleting, moving, or overwriting.

Current `/pwf-doctor` also audits append-only progress storage. It checks `progress-index.ndjson`, active/archive directory roles, missing indexed files, hash mismatches, and orphan generated segments. It is report-only: it prints `No automatic repair was attempted.` and never deletes, moves, overwrites, compacts, or recreates progress files. Use `plan.py doctor --verbose` for effect/action details, `--json` for machine-readable output, and `--strict` to fail on warnings.

## Compatibility

Existing tasks without `progress-index.ndjson` continue to use `progress.md`.

Existing `progress.archive.md` remains readable as an old-format archive. The new implementation does not append to it. Documentation should tell users it is legacy cold storage.

Existing tests that assert `progress.md` is rewritten must change to assert:

- `progress.md` stays byte-for-byte unchanged after rollover.
- A new archive file is created under `progress-archive/<session-key>/`.
- A new active segment is created under `progress-active/<session-key>/`.
- New hook records append to the new active segment.

## Non-Goals

- Do not implement automatic deletion or pruning of archives.
- Do not migrate old archive files by moving or rewriting them.
- Do not auto-inject full archive contents into prompts.
- Do not build a UI for browsing archives in this change.
