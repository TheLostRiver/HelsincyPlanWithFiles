# Session Task Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support multiple concurrent Codex conversations in the same project without mixing unrelated task context or writing unrelated auto records into the same `progress.md`.

**Architecture:** Keep `.planning/.active_plan` as the workspace fallback for backward compatibility, but introduce an explicit session-to-plan binding layer that hooks consult before the workspace active plan. Hook context injection and `PostToolUse` progress writes must resolve the same effective plan for a given hook payload, so a conversation reads from and writes to the task it is bound to. Add diagnostics and CLI affordances so users can see and control workspace active plans, per-session bindings, and strict isolation behavior.

**Tech Stack:** Python standard library, Codex hook stdin/stdout JSON payloads, project-local `.planning/` runtime files, Markdown planning files, `unittest`, PowerShell verification commands.

---

## 1. Problem Statement

Helsincy Plan With Files currently treats the project as having one active planning task by default. Hooks resolve the task in this order:

```text
PLAN_ID environment variable
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

This is reliable for one main conversation in one project. It becomes unsafe when a user opens several Codex conversations against the same project and expects them to work on different PWF tasks at the same time.

The current failure modes are:

| Failure mode | What happens | Why it happens |
|--------------|--------------|----------------|
| Context mixing | Conversation A sees conversation B's recent progress | Both resolve `.planning/.active_plan` |
| Progress mixing | `PostToolUse` records from multiple conversations append to one `progress.md` | `append_progress()` uses the workspace-resolved plan |
| Switch race | Conversation A starts on plan X, then conversation B runs `/pwf-switch plan-y`; A's next hook can use plan Y | `.planning/.active_plan` is global project state |
| Strict-mode friction | `PWF_SESSION_MODE=strict` can prevent context injection, but it does not by itself bind a session to a specific plan | Strict mode is an access gate, not a task resolver |

File locking alone cannot fix this. A lock can prevent physical write corruption, but it cannot decide which task a conversation should read or write. The missing concept is task ownership at the conversation/session level.

## 2. Goals

- Preserve the existing default workflow for users with one main task per project.
- Allow same-project conversations to bind to different PWF tasks concurrently.
- Ensure hook injection and progress append use the same effective task for the same hook event.
- Avoid relying on `.planning/.active_plan` as the only truth once a session binding exists.
- Make the active workspace plan, current session binding, and effective plan visible in `status` and `doctor`.
- Keep strict session isolation explicit and diagnosable.
- Add a lightweight append lock so concurrent writes to the same `progress.md` stay well formed.
- Add source metadata to auto records so shared tasks remain auditable.
- Keep `.planning/` runtime data uncommitted and backward compatible.

## 3. Non-Goals

- Do not make git worktrees mandatory for concurrent tasks.
- Do not remove `.planning/.active_plan`; it remains the compatibility fallback.
- Do not silently enable strict mode for every project.
- Do not require users to commit `.planning/session-bindings/`.
- Do not split `progress.md` into per-session logs in the first implementation pass.
- Do not make `PLAN_ID` weaker; explicit environment override remains the highest-priority resolver.
- Do not rely on a Codex-only UI feature when a CLI fallback can express the same state.

## 4. Recommended Design

Introduce a new resolver layer:

```text
PLAN_ID environment variable
session-bound plan id
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

The workspace active plan remains useful as a default and as a migration path. Once a hook payload has a `session_id` and that session has a binding, the binding wins. This makes conversation-level intent stable even if another conversation changes the workspace active plan later.

The core invariant:

> For one hook payload, `render_prompt_context()`, `render_pre_tool_context()`, `append_progress()`, and `stop_message()` must resolve the same effective planning directory from the same root, payload, and environment.

That invariant is more important than the exact storage file layout. If the user sees plan A injected before work, file edits from that turn must be recorded in plan A's `progress.md`.

## 5. Runtime State Layout

Use one small file per session binding:

```text
.planning/
  .active_plan
  session-policy.json
  session-bindings/
    <session-key>.json
```

Example binding:

```json
{
  "version": 1,
  "session_id": "abc123",
  "plan_id": "2026-06-07-session-task-isolation-plan",
  "created_at": "2026-06-07T10:12:30Z",
  "updated_at": "2026-06-07T10:12:30Z",
  "source": "plan.py switch --session"
}
```

Use one file per session instead of one shared JSON map because it is easier to update atomically and easier to inspect. The filename must not be the raw `session_id`. It should be a stable sanitized key, preferably a short SHA-256 digest of the session id:

```text
.planning/session-bindings/3f9a8c1d2e77.json
```

The JSON may include the raw `session_id` for local diagnostics, but all doctor/status output must sanitize and shorten it.

## 6. Session Identity

Hooks already read session identity through `session_id_from_payload(payload)`, falling back to `PWF_SESSION_ID`. Reuse that as the only source of session identity:

```python
def session_id_from_payload(payload: dict[str, Any]) -> str | None:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    env_sid = os.environ.get("PWF_SESSION_ID", "")
    return env_sid if env_sid else None
```

If no session id is available:

- Workspace mode: fall back to `.planning/.active_plan`.
- Strict mode: deny context as today unless a future explicit non-session override is added.
- CLI commands run outside a hook may use `PWF_SESSION_ID` for terminal fallback.

## 7. CLI Behavior

Extend `plan.py` with session-aware switches while keeping existing commands compatible.

### 7.1 `init`

Current behavior:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name"
```

Keep creating a new plan and setting `.planning/.active_plan`.

Add:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

Behavior:

- Create the plan.
- Set `.planning/.active_plan` unless `--no-workspace-active` is provided.
- If a session id is present, bind the current session to the new plan.
- If `--bind-session` is provided but no session id exists, print a clear diagnostic and return nonzero.

Optional advanced flag:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session --no-workspace-active
```

This supports opening a side task without changing other conversations that still use the workspace fallback.

### 7.2 `switch`

Current behavior:

```powershell
plan.py switch 2026-06-07-some-task
```

Keep this as workspace switch for compatibility.

Add:

```powershell
plan.py switch 2026-06-07-some-task --session
plan.py switch 2026-06-07-some-task --workspace
```

Rules:

- No flag keeps existing workspace behavior.
- `--workspace` writes `.planning/.active_plan`.
- `--session` writes `.planning/session-bindings/<session-key>.json`.
- `--session` requires a session id through hook payload or `PWF_SESSION_ID`.
- `PLAN_ID` still overrides both when hooks resolve context.

Add:

```powershell
plan.py switch --clear-session
```

This removes the current session binding so the conversation falls back to workspace mode.

### 7.3 `status`

Show both workspace and session state:

```text
workspace active plan: 2026-06-07-main-task
session binding: 3f9a8c1d2e77 -> 2026-06-07-side-task
effective plan: 2026-06-07-side-task
path: D:\project\.planning\2026-06-07-side-task
```

If no session id exists:

```text
workspace active plan: 2026-06-07-main-task
session binding: unavailable (no session_id)
effective plan: 2026-06-07-main-task
```

### 7.4 `doctor`

Add diagnostics:

```text
session mode: workspace
workspace active plan: ok 2026-06-07-main-task
session binding: none for current session
effective plan: workspace active
```

When multiple attached sessions exist and no bindings exist:

```text
[warn] multiple sessions detected while using workspace active plan; concurrent conversations may share progress.md
```

In strict mode:

```text
session mode: strict
session binding: required
[warn] strict mode has attached sessions without plan bindings
```

## 8. Hook Behavior

Hook entrypoints should pass payload/session context into plan resolution instead of calling a root-only resolver for every operation.

Current pattern:

```python
paths = planning_paths(root)
```

Target pattern:

```python
session_id = adapter.session_id_from_payload(payload)
paths = planning_paths(root, session_id=session_id)
```

Or, for clearer boundaries:

```python
resolution = resolve_planning_context(root, env=os.environ, session_id=session_id)
paths = resolution.paths
```

The second shape is preferable because it can carry diagnostics:

```python
@dataclass(frozen=True)
class PlanResolution:
    source: str
    plan_id: str
    paths: PlanningPaths
    session_key: str | None = None
    warning: str | None = None
```

Suggested sources:

```text
env
session
workspace
newest
legacy
none
```

The hooks should stay fail-open. If session binding JSON is malformed, the resolver should ignore that binding, emit a sanitized warning in diagnostics where possible, and fall back according to policy.

## 9. Strict Mode Semantics

Current strict mode means:

> Context is injected only when the hook payload has an attached `session_id`.

After adding bindings, strict mode should mean:

> Context is injected only when the hook payload has an attached `session_id`; if plan binding enforcement is enabled, the session must also be bound to a valid plan.

To preserve compatibility, do not require bindings in strict mode by default in the first implementation. Instead add an explicit setting:

```powershell
$env:PWF_STRICT_REQUIRES_BINDING = "1"
```

or:

```json
{"mode":"strict","require_binding":true}
```

This avoids breaking users who already use strict mode as an access gate around the workspace active plan.

Future default can change in a later release after doctor warnings and release notes prepare users.

## 10. Progress Writes and Locking

Session binding fixes semantic routing. A file lock still helps when two conversations intentionally share one task.

Add a lock around `append_progress()`:

```text
.planning/<plan-id>/.progress.lock
```

Requirements:

- Lock acquisition must have a short timeout.
- On lock timeout, hook should fail open and emit a diagnostic system message if possible.
- Writes must remain newline-normalized.
- Never hold the lock while rendering large context or running external commands.
- Lock only the append operation.

Auto records should include sanitized source metadata:

```text
### Auto Record: 2026-06-07 10:12:30
- Tool: apply_patch
- Session: 3f9a8c1d2e77
- Plan-Source: session
- Files:
  - `src/example.py` (update)
```

Use the short session key, not the raw session id. If no session id exists:

```text
- Session: unavailable
- Plan-Source: workspace
```

This metadata makes shared-task work auditable without injecting raw identifiers.

## 11. Safety and Validation

Session binding files are local runtime state, but they still affect hook context routing. Treat them as untrusted data:

- Accept only JSON objects.
- Accept only `version == 1`.
- Accept only string `plan_id` matching an existing `.planning/<plan-id>/task_plan.md`.
- Reject path separators, `..`, absolute paths, empty values, and control characters in `plan_id`.
- Sanitize raw values in warnings with the same style as existing env diagnostics.
- Do not allow binding files to resolve outside `.planning/`.
- If attestation exists for the bound plan, preserve current tamper-blocking behavior.

Use atomic writes for binding updates:

1. Write `<session-key>.json.tmp`.
2. Flush and close.
3. Replace `<session-key>.json`.

## 12. Documentation Updates

Update user-facing docs after implementation:

- `README.md`
- `README.en.md`
- `docs/FAQ.md`
- `CHANGELOG.md`

Key messaging:

- Workspace active plan remains the default.
- Concurrent same-project conversations should use session bindings.
- `strict` controls whether sessions are allowed; bindings control which task a session uses.
- `PLAN_ID` is the strongest explicit override.
- `--session` switch avoids changing other conversations.

Suggested FAQ addition:

```text
If you run several Codex conversations in the same project, bind each conversation to its own PWF task:

plan.py switch <plan-id> --session

The old switch behavior still changes the workspace active plan and is best for single-task projects.
```

## 13. Tests

Add focused tests before implementation.

### 13.1 Resolver Tests

- `PLAN_ID` beats session binding.
- Session binding beats `.planning/.active_plan`.
- Workspace active plan remains the fallback.
- Missing session id falls back in workspace mode.
- Invalid binding JSON falls back and does not crash.
- Binding with path traversal plan id is rejected.
- Binding to missing plan is ignored.

### 13.2 Hook Tests

- `UserPromptSubmit` injects the session-bound plan when binding exists.
- `PostToolUse` appends to the session-bound plan's `progress.md`.
- Switching workspace active plan does not affect an already bound session.
- `PreToolUse` uses the same effective plan as `UserPromptSubmit`.
- `Stop` checks phases in the session-bound plan.
- Strict mode with missing session id still emits denial diagnostics.
- Strict mode with attached but unbound session falls back unless `require_binding` is enabled.
- Strict mode with `require_binding` denies unbound sessions.

### 13.3 CLI Tests

- `init --bind-session` creates a plan and binding when `PWF_SESSION_ID` is set.
- `init --bind-session --no-workspace-active` does not overwrite `.active_plan`.
- `switch --session` writes the binding file.
- `switch --workspace` writes `.active_plan`.
- `switch --clear-session` removes the binding file.
- `status` shows workspace active, session binding, and effective plan.
- `doctor` warns about multiple sessions sharing workspace fallback.

### 13.4 Progress Lock Tests

- Two append calls preserve complete auto record boundaries.
- Lock timeout fails open without corrupting existing progress.
- Auto records include `Session` and `Plan-Source`.

## 14. Implementation Tasks

### Task 1: Add Plan Resolution Model

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] Add `PlanResolution` dataclass.
- [ ] Add session-key helper based on SHA-256.
- [ ] Add plan-id validation helper.
- [ ] Add binding read helper.
- [ ] Add `resolve_planning_context(root, env=None, session_id=None)`.
- [ ] Keep `planning_paths(root)` as a compatibility wrapper.
- [ ] Add resolver tests.

### Task 2: Route Hooks Through Session-Aware Resolution

**Files:**
- Modify: `.codex/hooks/session_start.py`
- Modify: `.codex/hooks/user_prompt_submit.py`
- Modify: `.codex/hooks/pre_tool_use.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Modify: `.codex/hooks/stop.py`
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] Pass `session_id` from hook payload into render and append helpers.
- [ ] Ensure prompt, pre-tool, post-tool, and stop paths resolve the same plan for the same payload.
- [ ] Add hook tests for session-bound injection and progress append.

### Task 3: Add Binding CLI

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`
- Test: `tests/test_plan_doctor.py`

- [ ] Add `--bind-session` and `--no-workspace-active` to `init`.
- [ ] Add `--session`, `--workspace`, and `--clear-session` to `switch`.
- [ ] Add session binding and effective plan output to `status`.
- [ ] Add session binding diagnostics to `doctor`.
- [ ] Add CLI and doctor tests.

### Task 4: Add Strict Binding Enforcement Option

**Files:**
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_hooks.py`
- Test: `tests/test_plan_doctor.py`

- [ ] Parse `PWF_STRICT_REQUIRES_BINDING` strictly as a boolean.
- [ ] Read `require_binding` from `.planning/session-policy.json`.
- [ ] Deny strict unbound sessions only when binding enforcement is enabled.
- [ ] Emit clear diagnostics for unbound strict sessions.
- [ ] Report enforcement state in doctor.

### Task 5: Add Progress Append Lock and Source Metadata

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py` if parsing needs source metadata awareness
- Test: `tests/test_hooks.py`
- Test: `tests/test_progress_compaction.py`

- [ ] Add a local lock helper for `progress.md` append.
- [ ] Add `Session` and `Plan-Source` fields to auto records.
- [ ] Ensure existing compaction and recent-record parsing tolerate the new fields.
- [ ] Add tests for lock behavior and metadata.

### Task 6: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py`

- [ ] Document workspace active plan vs session binding.
- [ ] Document `plan.py switch --session`.
- [ ] Document `plan.py init --bind-session`.
- [ ] Document strict binding enforcement.
- [ ] Add consistency tests for the new docs.

### Task 7: Verification and Release Readiness

**Files:**
- All modified files.

- [ ] Run `python -m unittest tests.test_hooks -v`.
- [ ] Run `python -m unittest tests.test_plan_cli tests.test_plan_doctor tests.test_progress_compaction tests.test_project_consistency -v`.
- [ ] Run `python -m unittest discover -v`.
- [ ] Run `git diff --check`.
- [ ] Run `python .codex\skills\planning-with-files\scripts\plan.py doctor`.
- [ ] Review `git diff --stat`.
- [ ] Commit implementation changes on the feature branch.

## 15. Rollout Plan

Recommended release shape:

1. Ship session binding as opt-in while preserving workspace default.
2. Add doctor warnings for likely concurrent workspace-sharing cases.
3. Collect feedback on `--session` and `--bind-session` ergonomics.
4. Later consider making `/pwf-init` bind automatically when a reliable `session_id` is always available.
5. Later consider making strict mode require bindings by default in a major or clearly announced release.

## 16. Open Questions

1. Should slash command wrappers automatically pass `--session` when invoked inside Codex, or should users explicitly choose session binding?
2. Should `/pwf-switch` default to workspace forever for compatibility, or eventually prompt users when multiple sessions are detected?
3. Should a shared task inject only records from the current session by default, or should shared-task progress remain global?
4. How stable is Codex `session_id` across context compaction, resume, and thread continuation in the desktop app?
5. Should the binding source use `session_id` only, or should it prefer a more stable thread id if Codex exposes one later?

## 17. Success Criteria

- Two conversations in the same project can bind to different plan ids.
- A workspace active-plan switch in one conversation does not change another bound conversation's effective plan.
- Hook prompt context and `PostToolUse` progress append target the same effective plan.
- Existing single-task projects behave as before without new configuration.
- `doctor` makes accidental sharing visible before it surprises the user.
- Tests cover resolver precedence, invalid binding data, strict-mode diagnostics, CLI binding commands, and progress metadata.
