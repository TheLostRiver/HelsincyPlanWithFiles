# Source Deletion Safety Audit Report

Date: 2026-06-11

## Executive Summary

The user report is substantively valid, but the mechanism is more precise than "direct deletion".

No code path was found that directly runs `rm`, `del`, `Remove-Item`, `rmtree`, or `os.remove` against user source files. The confirmed historical risk is that `plan.py compact --archive <PATH>` could write progress archive content to a user-controlled path outside the planning directory. If that path pointed at a project source file, the source file would be modified and corrupted.

The current working tree already contains a hardening fix and regression tests for this issue.

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

The current working tree hardens `_validate_archive_path()` in `progress_lifecycle.py`:

- The resolved archive target must be different from `progress.md`.
- The resolved archive target must stay in the same directory as `progress.md`.
- The archive target must use the `.md` suffix.
- If the archive target already exists, it must be empty or start with `# Progress Archive`.

This blocks both path traversal into project source directories and accidental reuse of existing project Markdown files such as `README.md`.

## Verification

Controlled verification against the current working tree:

```text
rejected= archive path must stay in the same directory as progress.md
source_still_original= True
progress_still_original= True
```

Focused regression tests:

```text
python -m pytest tests/test_progress_compaction.py tests/test_plan_cli.py -k compact -q
25 passed, 64 deselected, 1 warning
```

Full test suite:

```text
python -m pytest -q
230 passed, 3 warnings
```

## Audited Destructive Paths

No direct source deletion path was found.

Observed write/delete operations are limited as follows:

- Session binding writes and clears target hashed files under `.planning/session-bindings`.
- Session context writes and clears target hashed files under `.planning/session-context`.
- Lease writes target `.planning/session-leases` and `.planning/<plan-id>/.task-lease.json`.
- Lock cleanup unlinks `.task-lease.lock` and `.progress.lock` metadata files.
- `append_progress()` appends only to the resolved active plan's `progress.md`.
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

Likelihood depends on whether users or agents passed a custom `--archive` path. Default `plan.py compact` uses `progress.archive.md` beside `progress.md` and is not the dangerous case.

## Residual Risk

- This audit did not inspect external user incident logs, so it cannot prove the exact command used in the reported incident.
- This audit covers the PWF repository code paths, not arbitrary commands an agent might run outside this tool.
- `init --legacy --force` remains intentionally destructive for planning files in the project root. It should remain documented as explicit overwrite behavior.

## Recommended Actions

1. Ship the current hardening quickly.
2. Call out the fix in release notes as a data-loss prevention fix.
3. Keep the regression tests for:
   - archive path traversal into `src/main.py`
   - existing non-archive Markdown files such as `README.md`
4. Consider adding a short user-facing warning that custom `--archive` should normally be left at the default value.
