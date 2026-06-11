# Source Deletion Safety Audit Report

Date: 2026-06-11

## Executive Summary

The user report is substantively valid, but the mechanism is more precise than "direct deletion".

No code path was found that directly runs `rm`, `del`, `Remove-Item`, `rmtree`, or `os.remove` against user source files. The confirmed historical risk is that `plan.py compact --archive <PATH>` could write progress archive content to a user-controlled path outside the planning directory. If that path pointed at a project source file, the source file would be modified and corrupted.

The current working tree replaces the exposed compact behavior with append-only rollover and adds regression tests for this issue.

## Scope

This audit investigates a report from an external user of this tool. It is not an incident report for the local `D:\DEV\Plan_Skill` workspace, and no claim is made that this local repository's source files were deleted.

Audited areas:

- `.codex/hooks`
- `.codex/skills/planning-with-files/scripts`
- Relevant tests under `tests/`
- Existing progress compaction and CLI behavior

This report is based on code inspection and controlled local reproduction. It does not include logs or filesystem snapshots from the external user who reported the incident.

## Confirmed Root Cause

The risky path is:

1. `plan.py compact --archive <PATH>` accepts a user-provided archive target.
2. `compact()` resolves a relative archive path under the active plan directory.
3. Historical `_validate_archive_path()` only rejected:
   - archive target equal to `progress.md`
   - archive target that was a directory
4. `_append_archive()` then wrote archive content with `archive_path.write_text(...)`.

In the vulnerable version, a path like:

```text
..\..\src\main.py
```

could escape from `.planning/<plan-id>/` into `src/main.py`. If `src/main.py` existed, the archive writer read its existing text and rewrote the file with the original text plus progress archive content appended. This corrupts source code and can reasonably be perceived by users as source loss.

## Reproduction Evidence

A controlled reproduction was run against the committed `HEAD` version of `progress_lifecycle.py` before the working-tree hardening.

Setup:

- Temporary project root
- Active plan directory: `.planning/2026-06-11-risk`
- Simulated source file: `src/main.py`
- Archive argument: `.planning/2026-06-11-risk/..\..\src\main.py`

Observed result:

```text
changed= True
source_still_original= False
source_prefix= print('keep me')\n\n## Compact Batch: 2026-06-11 10:02:00...
```

This confirms that the historical code could modify a source file outside the planning directory.

## Current Fix

The current working tree removes the dangerous exposed behavior rather than relying only on path validation:

- `plan.py compact` no longer accepts user-provided archive paths; `--archive` is kept only as a rejected compatibility argument.
- Rollover archive files are generated only under `progress-archive/<session-key>/archive-*.md`.
- New active progress segments are generated only under `progress-active/<session-key>/active-*.md`.
- `progress-index.ndjson` is append-only and links the old active file, new archive file, and new active file.
- Generated segment files are created with exclusive-create semantics and refuse to reuse an existing path.
- Existing `progress.md`, active segments, and archive files are not deleted or overwritten.
- Hooks, prompt context, `status`, and `doctor` resolve the latest active segment through `progress-index.ndjson`, with legacy `progress.md` as fallback.

The legacy `compact_progress()` helper still contains path validation for compatibility tests, but the CLI no longer exposes custom archive targets or rewrite-based compaction.

## Verification

Controlled verification against the current working tree now covers the append-only behavior:

```text
custom --archive rejected
source_still_original=True
progress_still_original=True
progress-index.ndjson created only for valid rollover
progress-active/<session-key>/active-*.md created with kept records
progress-archive/<session-key>/archive-*.md created with archived records
```

Focused regression tests:

```text
python -m pytest tests/test_progress_compaction.py tests/test_plan_cli.py tests/test_hooks.py tests/test_plan_doctor.py -k "compact or rollover or current_active_progress or active_progress" -q
38 passed, 174 deselected, 3 warnings
```

Full test suite:

```text
python -m pytest -q
240 passed, 3 warnings
```

## Audited Destructive Paths

No direct source deletion path was found.

Observed write/delete operations are limited as follows:

- Session binding writes and clears target hashed files under `.planning/session-bindings`.
- Session context writes and clears target hashed files under `.planning/session-context`.
- Lease writes target `.planning/session-leases` and `.planning/<plan-id>/.task-lease.json`.
- Lock cleanup unlinks `.task-lease.lock` and `.progress.lock` metadata files.
- `append_progress()` appends only to the resolved active progress segment for the effective plan.
- `attest --clear` unlinks only the plan attestation file.
- `init --legacy --force` can overwrite root-level `task_plan.md`, `progress.md`, and `findings.md`; this is explicit force behavior, not an arbitrary source path write.

The only confirmed historical arbitrary project-file modification vector was `compact --archive`.

## Impact Assessment

Severity: high.

Reason:

- The affected path can modify files outside `.planning`.
- A project source file can become syntactically invalid or semantically corrupted.
- The operation is not an intentional source edit from the user's perspective.
- The failure mode can be described by users as "the tool deleted my source", even though the confirmed mechanism is archive-content overwrite/append.

Historical likelihood depended on whether users or agents passed a custom `--archive` path. In the current working tree, custom archive paths are rejected and default compact uses generated append-only segment paths.

## Residual Risk

- This audit did not inspect external user incident logs, so it cannot prove the exact command used in the reported incident.
- This audit covers the PWF repository code paths, not arbitrary commands an agent might run outside this tool.
- `init --legacy --force` remains intentionally destructive for planning files in the project root. It should remain documented as explicit overwrite behavior.

## Recommended Actions

1. Merge the append-only rollover fix after CI/review.
2. Call out the fix in release notes as a data-loss prevention fix.
3. Keep the regression tests for:
   - custom `--archive` rejection
   - generated active/archive segment separation
   - refusal to overwrite existing generated segment files
   - hooks/context/status/doctor resolving the latest active segment
4. Consider a future doctor check for orphaned generated segment files if index append fails after file creation.
