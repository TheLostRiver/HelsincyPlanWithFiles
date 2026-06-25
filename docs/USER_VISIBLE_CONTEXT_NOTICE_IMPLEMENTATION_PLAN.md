# User-only Context Notice Implementation Plan

> **For agentic workers:** implement this plan task-by-task. Use the checkbox steps for tracking. This plan assumes the design in `docs/USER_VISIBLE_CONTEXT_NOTICE_DESIGN.md` is the source of truth.

**Goal:** Replace ad-hoc context notice `systemMessage` emission with a centralized notice payload and channel system. Keep current compatibility available through explicit `legacy-system`, while making the default `auto` behavior safe: strict user-only when the Codex host supports it, otherwise silent with status/doctor diagnostics.

**Architecture:**

- Agent planning context continues to use `hookSpecificOutput.additionalContext`.
- Context notices are represented by a structured `ContextNoticePayload`.
- Hook entrypoints call adapter helpers instead of directly emitting notice `systemMessage` payloads.
- Channel selection is centralized in the hook adapter.
- `systemMessage` becomes an explicit legacy compatibility channel.
- Strict user-only output is enabled only when the Codex host advertises support.

**Tech Stack:** Python standard library, Codex hook JSONL protocol, `unittest`, Markdown docs.

---

## File Structure

Modify:

- `.codex/hooks/codex_hook_adapter.py`
  - Add agent-context and user-notice emission helpers.
  - Add notice channel resolution.
  - Add host user-only capability detection.
- `.codex/hooks/planning_state.py`
  - Add notice payload dataclass.
  - Add injection/blocked/skipped notice builders.
  - Keep chars/tokens derived from final rendered context.
- `.codex/hooks/user_prompt_submit.py`
  - Use adapter helpers.
  - Emit injection or blocked notices via centralized path.
- `.codex/hooks/session_start.py`
  - Use adapter helpers.
  - Preserve `startup|resume|compact` behavior.
- `.codex/hooks/pre_tool_use.py`
  - Keep plan reminder behavior separate from context-size notices.
  - Optionally route ownership-denied diagnostics through blocked notice helper.
- `.codex/skills/planning-with-files/scripts/plan.py`
  - Extend context status/doctor output with notice channel diagnostics.
- `tests/test_hooks.py`
  - Add notice payload, channel, and hook JSONL tests.
- `tests/test_plan_cli.py`
  - Add status output tests for notice channel diagnostics.
- `tests/test_plan_doctor.py`
  - Add doctor diagnostics tests.
- `README.md`
- `README.en.md`
- `docs/FAQ.md`
- `docs/USER_GUIDE.zh-CN.md`
- `CHANGELOG.md`

Optional later create:

- `.planning/session-notices/<session-key>.jsonl` runtime files only; do not commit.

Do not create a project-global `.planning/.latest_notice` file.

---

## Compatibility Rules

### Existing notice mode

Keep the existing session-scoped notice mode:

```text
auto | on | off
```

This answers whether the session wants notices.

### New notice channel

Add a separate channel resolver:

```text
auto | user-only | legacy-system | silent
```

This answers where a notice may be sent.

Default:

```text
PWF_CONTEXT_NOTICE_CHANNEL=auto
```

Channel behavior:

| Channel | Behavior |
| --- | --- |
| `auto` | Use strict host user-only support if available; otherwise emit no immediate notice. |
| `user-only` | Require strict host support; if unavailable, emit no notice and report diagnostics. |
| `legacy-system` | Emit `systemMessage`; explicit compatibility only. |
| `silent` | Emit no immediate notice. |

Important rule:

```text
channel=auto must never fall back to systemMessage implicitly.
```

---

## Task 1: Add Notice Channel Resolution

**Files:**

- Modify: `.codex/hooks/codex_hook_adapter.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing tests for channel resolution**

Add tests covering:

1. default channel is `auto`;
2. `auto` with no host capability resolves to `silent`;
3. `auto` with host capability resolves to `user-only`;
4. `legacy-system` is used only when explicitly set;
5. invalid `PWF_CONTEXT_NOTICE_CHANNEL` falls back to safe `auto` behavior and records a warning;
6. `user-only` with missing host capability resolves to `silent` plus diagnostic warning.

Suggested test names:

```python
def test_notice_channel_auto_without_capability_is_silent(self): ...
def test_notice_channel_auto_with_payload_capability_is_user_only(self): ...
def test_notice_channel_legacy_system_is_explicit_opt_in(self): ...
def test_notice_channel_invalid_value_warns_and_uses_auto(self): ...
def test_notice_channel_user_only_without_capability_warns(self): ...
```

- [ ] **Step 2: Add channel constants**

In `.codex/hooks/codex_hook_adapter.py`:

```python
NOTICE_CHANNELS = {"auto", "user-only", "legacy-system", "silent"}
DEFAULT_NOTICE_CHANNEL = "auto"
```

- [ ] **Step 3: Add host capability detection**

Add a helper that checks, in order:

1. hook payload capability, for example:

```python
payload.get("capabilities", {}).get("userNotification") is True
```

2. host environment variable, for example:

```text
CODEX_USER_NOTIFICATION=1
```

3. otherwise unavailable.

Do not infer support from version strings.

- [ ] **Step 4: Add resolver result dataclass**

Suggested shape:

```python
@dataclass(frozen=True)
class NoticeChannelResolution:
    requested: str
    effective: str
    source: str
    host_user_only_available: bool
    warnings: tuple[str, ...] = ()
```

- [ ] **Step 5: Implement `resolve_notice_channel(...)`**

Suggested signature:

```python
def resolve_notice_channel(
    payload: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> NoticeChannelResolution:
    ...
```

Expected rules:

- missing env -> requested `auto`;
- invalid env -> requested `auto` with warning;
- `auto` + capability -> effective `user-only`;
- `auto` + no capability -> effective `silent`;
- `user-only` + capability -> effective `user-only`;
- `user-only` + no capability -> effective `silent` with warning;
- `legacy-system` -> effective `legacy-system`;
- `silent` -> effective `silent`.

- [ ] **Step 6: Run focused tests**

```powershell
python -m unittest tests.test_hooks -k notice_channel -v
```

If `-k` is unavailable in the local Python version, run the whole module:

```powershell
python -m unittest tests.test_hooks -v
```

---

## Task 2: Add Context Notice Payload Model

**Files:**

- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing payload tests**

Add tests for:

1. injection payload chars equals `len(final_context)`;
2. tokens equals `ceil(chars / 4)`;
3. payload includes profile and progress mode;
4. payload message does not include plan/progress/findings sentinel body text;
5. blocked payload has no chars/tokens;
6. notice mode `off` suppresses injection payload creation.

Suggested sentinel values:

```text
PLAN_SECRET_SENTINEL
PROGRESS_SECRET_SENTINEL
FINDINGS_SECRET_SENTINEL
NOTICE_ONLY_SENTINEL
```

- [ ] **Step 2: Add payload dataclass**

In `.codex/hooks/planning_state.py`:

```python
@dataclass(frozen=True)
class ContextNoticePayload:
    version: int
    kind: str
    state: str
    hook_event: str
    session_key: str | None
    message: str
    profile: str | None = None
    progress_mode: str | None = None
    chars: int | None = None
    estimated_tokens: int | None = None
    hook_source: str | None = None
    plan_id: str | None = None
    plan_source: str | None = None
    findings_mode: str | None = None
    notice_mode: str | None = None
    notice_channel: str | None = None
    warnings: tuple[str, ...] = ()
```

State values:

```text
injected | blocked | paused | no_plan | suppressed
```

- [ ] **Step 3: Add serialization helper**

Suggested method or function:

```python
def context_notice_to_hook_payload(payload: ContextNoticePayload) -> dict[str, object]:
    ...
```

Rules:

- omit `None` fields;
- never include raw session id;
- never include absolute root path;
- include `session_key`, not `session_id`.

- [ ] **Step 4: Add injection payload builder**

Suggested signature:

```python
def build_context_injection_notice(
    rendered: str,
    *,
    root: Path,
    session_id: str | None,
    event: str,
    hook_source: str | None = None,
) -> ContextNoticePayload | None:
    ...
```

Rules:

- return `None` if `rendered` is empty;
- return `None` if notice mode is `off`;
- call existing context settings/profile helpers;
- derive `chars` from `len(rendered)`;
- derive `estimated_tokens` from `_estimated_tokens(chars)`;
- build the current short human-readable message;
- do not inspect or embed planning body text beyond metadata.

- [ ] **Step 5: Add blocked payload builder**

Suggested signature:

```python
def build_context_blocked_notice(
    reason: str,
    *,
    root: Path,
    session_id: str | None,
    event: str,
    hook_source: str | None = None,
) -> ContextNoticePayload | None:
    ...
```

Rules:

- respect notice mode `off` if the decision is to suppress all notices;
- no `chars`;
- no `estimated_tokens`;
- sanitize reason text;
- message uses `context_blocked_notice` wording.

- [ ] **Step 6: Keep compatibility wrapper temporarily**

Keep `render_context_notice(...)` as a compatibility wrapper during migration:

```python
def render_context_notice(...):
    payload = build_context_injection_notice(...)
    return payload.message if payload else ""
```

Remove this wrapper only after all call sites and tests have moved to payload APIs.

---

## Task 3: Add Adapter Emission Helpers

**Files:**

- Modify: `.codex/hooks/codex_hook_adapter.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add `emit_agent_context(...)`**

```python
def emit_agent_context(event_name: str, context: str) -> None:
    emit_json({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    })
```

- [ ] **Step 2: Add `emit_user_notice(...)`**

Suggested signature:

```python
def emit_user_notice(
    notice: planning_state.ContextNoticePayload | None,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    ...
```

Behavior:

- return immediately if notice is `None`;
- resolve channel;
- if effective `user-only`, emit `{"userNotification": ...}`;
- if effective `legacy-system`, emit `{"systemMessage": notice.message}`;
- if effective `silent`, emit nothing.

- [ ] **Step 3: Avoid circular imports**

`codex_hook_adapter.py` currently imports `planning_state` in some paths indirectly. If direct type references create circular imports, use one of these approaches:

1. use `from __future__ import annotations` and runtime duck typing;
2. place serialization helper in `planning_state.py` and call it lazily;
3. pass `message` plus serialized payload dict to adapter.

Prefer the smallest change that keeps existing imports stable.

- [ ] **Step 4: Test JSONL output shape**

Tests should prove:

- `emit_agent_context` produces exactly the previous `hookSpecificOutput` shape;
- user-only channel produces `userNotification` and no `systemMessage`;
- legacy channel produces `systemMessage` and no `userNotification`;
- silent channel produces no notice output.

---

## Task 4: Migrate `UserPromptSubmit`

**Files:**

- Modify: `.codex/hooks/user_prompt_submit.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing hook tests**

Add tests for:

1. default `auto` without host capability emits only `additionalContext`, no `systemMessage`;
2. explicit `PWF_CONTEXT_NOTICE_CHANNEL=legacy-system` emits `additionalContext` and a separate `systemMessage`;
3. payload capability emits `userNotification`;
4. ownership denied emits blocked notice through selected channel;
5. blocked notice has no chars/tokens in user-only payload.

- [ ] **Step 2: Refactor success path**

Replace direct JSON emission:

```python
adapter.emit_json({"hookSpecificOutput": ...})
notice = planning_state.render_context_notice(...)
adapter.emit_json({"systemMessage": notice})
```

with:

```python
adapter.emit_agent_context("UserPromptSubmit", context)
notice = planning_state.build_context_injection_notice(
    context,
    root=root,
    session_id=session_id,
    event="UserPromptSubmit",
)
adapter.emit_user_notice(notice, payload=payload)
```

- [ ] **Step 3: Refactor blocked path**

When `planning_access_denial(...)` returns a reason:

```python
notice = planning_state.build_context_blocked_notice(
    ownership_denial,
    root=root,
    session_id=session_id,
    event="UserPromptSubmit",
)
adapter.emit_user_notice(notice, payload=payload)
return
```

Do not emit token usage for blocked state.

---

## Task 5: Migrate `SessionStart`

**Files:**

- Modify: `.codex/hooks/session_start.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing tests for compact source**

Add tests for:

1. `SessionStart(source=compact)` emits `additionalContext`;
2. legacy channel emits a separate `systemMessage` notice;
3. user-only channel emits `userNotification` with `hook_source=compact`;
4. default auto without capability emits no immediate notice;
5. notice chars are based on the final combined output, including session catchup if present.

- [ ] **Step 2: Preserve catchup behavior**

`session_start.py` currently combines:

```python
catchup_context
prompt_context
```

The notice count should continue using the final emitted `output`, not only `prompt_context`.

- [ ] **Step 3: Use centralized helpers**

Refactor success path:

```python
adapter.emit_agent_context("SessionStart", output)
notice = planning_state.build_context_injection_notice(
    output,
    root=root,
    session_id=session_id,
    event="SessionStart",
    hook_source=payload.get("source") if isinstance(payload.get("source"), str) else None,
)
adapter.emit_user_notice(notice, payload=payload)
```

For blocked access warnings, use `build_context_blocked_notice(...)`.

---

## Task 6: Clarify `PreCompact` and `PreToolUse`

**Files:**

- Modify if needed: `.codex/hooks/pre_compact.py`
- Modify if needed: `.codex/hooks/pre_tool_use.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Keep `PreCompact` out of token notice flow**

`PreCompact` should continue to emit only reminder/attestation information. It should not report chars/tokens because it does not emit recovery `additionalContext`.

- [ ] **Step 2: Keep `PreToolUse` behavior explicit**

`PreToolUse` currently emits plan reminders through `systemMessage`. This is not the context-size notice path. Do not accidentally route plan reminder data into `userNotification` unless the design is expanded for all user-facing messages.

- [ ] **Step 3: Optional blocked diagnostics**

Ownership/session denied diagnostics in `PreToolUse` may be migrated to blocked notice helpers later, but this is not required for MVP context-size notice correctness.

---

## Task 7: Extend CLI Status and Doctor Diagnostics

**Files:**

- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`
- Test: `tests/test_plan_doctor.py`

- [ ] **Step 1: Add failing CLI tests**

Status should include:

```text
context notice: auto
context notice channel: silent
```

When no strict host channel is available and default channel is `auto`, status/doctor should include a warning similar to:

```text
context notice warning: host user-only notification channel is unavailable; legacy systemMessage is opt-in and not strict user-only
```

- [ ] **Step 2: Add channel status helper**

`plan.py` can call adapter channel resolution directly only if imports stay safe. If importing adapter from CLI is undesirable, move pure channel resolution into `planning_state.py` or a small shared helper.

Preferred option:

- keep protocol emission in `codex_hook_adapter.py`;
- keep pure channel resolution in `planning_state.py` or a new small shared module;
- have both adapter and CLI use the same resolver.

- [ ] **Step 3: Extend context status lines**

Current context status already includes profile and notice mode. Add:

```text
context notice channel: <effective>
context notice channel source: <source>
```

- [ ] **Step 4: Extend doctor diagnostics**

Doctor should report invalid env values and unavailable strict user-only support.

Do not fail doctor solely because strict user-only support is unavailable unless a strict channel was explicitly requested.

---

## Task 8: Optional Per-session Diagnostic Ledger

**Files:**

- Modify: `.codex/hooks/planning_state.py` or new helper module
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Test: `tests/test_hooks.py`

This task is optional after MVP. Do it only if diagnostic history is required.

- [ ] **Step 1: Add ledger path helpers**

Runtime path:

```text
.planning/session-notices/<session-key>.jsonl
```

Lock path:

```text
.planning/session-notices/<session-key>.lock
```

- [ ] **Step 2: Add append helper**

Rules:

- append one JSON object per line;
- include metadata only;
- use session-scoped lock;
- tolerate write failure without breaking hooks.

- [ ] **Step 3: Add concurrency tests**

Tests should prove:

- session A writes only A file;
- session B writes only B file;
- concurrent writes produce valid JSONL;
- no planning body sentinels appear in ledger.

- [ ] **Step 4: Document non-secrecy**

Every ledger doc mention must say the ledger is diagnostic metadata and not hidden from the agent.

---

## Task 9: Update Documentation

**Files:**

- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `docs/USER_GUIDE.zh-CN.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Remove strong claims about `systemMessage`**

Replace claims like:

```text
notice is user-visible and agent cannot see it
```

with:

```text
notice is not written to additionalContext. Strict model invisibility requires host user-only notice support. Legacy systemMessage mode is compatibility-only.
```

- [ ] **Step 2: Document channel env**

Add:

```text
PWF_CONTEXT_NOTICE_CHANNEL=auto|user-only|legacy-system|silent
```

- [ ] **Step 3: Document why notices may not appear**

Mention:

- no active plan;
- paused context injection;
- ownership denied;
- attestation mismatch;
- notice off;
- no strict user-only channel in default auto mode.

- [ ] **Step 4: Update changelog**

Changelog should say:

- `systemMessage` notice emission is now explicit legacy mode;
- default auto no longer falls back to possibly model-visible notices;
- status/doctor explain the effective channel.

---

## Task 10: Final Verification

- [ ] Run hook tests:

```powershell
python -m unittest tests.test_hooks -v
```

- [ ] Run CLI tests:

```powershell
python -m unittest tests.test_plan_cli -v
```

- [ ] Run doctor tests:

```powershell
python -m unittest tests.test_plan_doctor -v
```

- [ ] Run project consistency tests:

```powershell
python -m unittest tests.test_project_consistency -v
```

- [ ] Run the full test suite:

```powershell
python -m unittest discover tests -v
```

- [ ] Manually inspect hook JSONL output for these scenarios:

```powershell
# default auto without host capability: no systemMessage notice
printf '{"cwd":"<repo>","hook_event_name":"UserPromptSubmit","prompt":"continue"}' | python .codex/hooks/user_prompt_submit.py

# explicit legacy mode: separate systemMessage notice
PWF_CONTEXT_NOTICE_CHANNEL=legacy-system printf '{"cwd":"<repo>","hook_event_name":"UserPromptSubmit","prompt":"continue"}' | python .codex/hooks/user_prompt_submit.py

# compact recovery source
PWF_CONTEXT_NOTICE_CHANNEL=legacy-system printf '{"cwd":"<repo>","hook_event_name":"SessionStart","source":"compact"}' | python .codex/hooks/session_start.py
```

On Windows shells, adapt env var syntax as needed.

---

## MVP Acceptance Criteria

MVP is complete when:

- `UserPromptSubmit` uses centralized agent-context and user-notice helpers;
- `SessionStart` uses centralized agent-context and user-notice helpers;
- default `auto` emits no `systemMessage` when strict host capability is absent;
- explicit `legacy-system` preserves old separate `systemMessage` behavior;
- user-only capability emits `userNotification` shape;
- notice mode `off` suppresses notices;
- blocked notices contain no chars/tokens;
- injection notice chars/tokens come from final emitted context;
- status/doctor show effective notice channel;
- docs no longer present `systemMessage` as strict user-only.

## Non-MVP Follow-up

After MVP, consider:

- per-session diagnostic ledger;
- host-level trace validation for strict user-only invisibility;
- richer skipped-state one-time diagnostics;
- removal of compatibility wrappers once all call sites use payload APIs;
- dedicated tests for host capability payload variants once the Codex host contract is finalized.
