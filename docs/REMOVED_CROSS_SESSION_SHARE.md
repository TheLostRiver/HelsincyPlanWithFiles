# Removed: Cross-Session PWF Task Sharing

> Status: removed in the current unreleased work, on top of v0.2.7.
> Scope: the `--share` flag on `plan.py switch` and `plan.py use`, and the
> `/pwf-use --share` shortcut.

## What was removed

The `--share` flag previously let session A mark a PWF task as shared so that
session B could read and write the same `task_plan.md` / `progress.md` /
`findings.md` without claiming ownership. The flag is no longer registered on
either subcommand:

```text
plan.py switch <plan-id> --session --share   # no longer exists
plan.py use <id> --share                     # no longer exists
```

Running either command with `--share` now fails with an argparse usage error
and writes nothing to disk.

## Why it was removed

The feature looked flexible but caused real problems in practice:

1. **Scrambled task memory.** Each Codex session has its own conversation
   context. When two sessions share one PWF task, both sessions' records,
   findings, and progress notes get merged into the same files, and each
   agent re-injects that mixed content on every prompt. The agents no longer
   have a coherent single-task picture; they have two interleaved task
   narratives.

2. **Write contention under concurrency.** Sharing one task across ten or more
   open sessions means every `PostToolUse` hook in every session appends to
   the same `progress.md`. The short progress lock protects the append
   boundary, but high fan-out still produces contention, lock timeouts, and
   interleaved auto records.

3. **Ambiguous disconnect semantics.** When sharing was enabled, there was no
   clear answer to "if I stop sharing, where does the binding live — session
   A, session B, or both?" Users had to remember manual bookkeeping, and
   silent no-ops made the feature feel broken.

Per-session task isolation (the default since v0.2.5) already covers the
legitimate use case: each session has its own PWF task and its own
`.planning/<plan-id>/` directory. If you genuinely need two sessions to work
on the same logical task, the supported path is `plan.py switch <plan-id>
--session --force-claim` — explicit takeover, single owner, no shared writes.

## What was kept for backward compatibility

Nothing was deleted that would corrupt existing `.planning/` state:

- `TaskLease.shared` field still exists in the dataclass.
- `read_task_lease` still parses `shared=true` from old `.task-lease.json`
  files.
- `task_lease_status` still reports `shared` for those legacy leases.
- `ownership_denial_for_resolution` still treats `shared=true` leases as
  non-conflicting, so a session that historically joined a shared task is
  not suddenly denied.
- `write_task_lease` still accepts the `shared` keyword (defaulting to
  `False`); no command passes `True` anymore.

This means: if you upgrade an existing project whose `.task-lease.json`
contains `shared=true`, those tasks keep working as before until the lease is
rewritten by a normal claim/release. The only thing that disappears is the
ability to **create new** shared leases.

## Migration

- If you were using `switch --share` to let a second session read a task,
  switch that session to its own task with `/pwf-init`, or take explicit
  ownership with `plan.py switch <plan-id> --session --force-claim`.
- If you relied on shared progress for cross-session visibility, run
  `/pwf-tasks --all` in the new session to see what exists, then `/pwf-use
  <short-id> --claim` to bind it explicitly.
- Old shared leases do not need to be cleaned up; they age out naturally
  through the existing stale/release flow.
