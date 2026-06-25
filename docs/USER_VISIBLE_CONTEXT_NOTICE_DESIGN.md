# User-only Context Notice Design

## 1. Summary

PWF currently emits context injection metadata as a separate hook message after it emits planning context. This correctly keeps the notice out of `hookSpecificOutput.additionalContext`, but it does **not** prove the notice is hidden from the model. Whether `systemMessage` is user-only is a Codex host contract, not something this repository can guarantee.

This design separates three concerns:

1. the agent context channel, which injects planning data into the agent;
2. the strict user-only notice channel, which must be enforced by the Codex host;
3. optional diagnostic storage, which may help debugging but is not a secrecy boundary.

Default policy for the final design:

```text
PWF_CONTEXT_NOTICE_CHANNEL=auto
```

`auto` must use a strict host-provided user-only channel when available. If no such channel is available, it must become silent; it must not implicitly fall back to `systemMessage`.

## 2. Current implementation and guarantees

### 2.1 Current hook paths

Current implementation locations:

- `.codex/hooks/user_prompt_submit.py`
  - renders `planning_state.render_prompt_context(...)`
  - emits `hookSpecificOutput.additionalContext`
  - emits a separate `systemMessage` notice when a context was actually injected
- `.codex/hooks/session_start.py`
  - handles `startup`, `resume`, and `compact` through the `SessionStart` matcher
  - emits `hookSpecificOutput.additionalContext`
  - emits a separate `systemMessage` notice when a context was actually injected
- `.codex/hooks/pre_compact.py`
  - emits a pre-compaction reminder and attestation information
  - does not emit a token-size notice
  - does not inject post-compaction recovery context
- `.codex/hooks/planning_state.py`
  - `render_context_notice(...)`
  - `_context_notice(...)`
  - `_estimated_tokens(chars) = ceil(chars / 4)`

Current `SessionStart` compact recovery flow:

```text
PreCompact
  -> reminder/attestation only
  -> no token notice

Codex host compacts transcript

SessionStart(source=compact)
  -> render final planning context
  -> emit additionalContext
  -> emit legacy systemMessage notice
```

### 2.2 Current guarantee table

| Capability | Current implementation | Guaranteed by this repo? |
| --- | --- | --- |
| Notice is not prepended to `additionalContext` | yes, emitted as separate JSONL | yes |
| Notice and `additionalContext` are separate hook outputs | yes | yes |
| Notice contains only metadata, not planning file bodies | intended and tested partially | mostly |
| Notice is visible in Codex UI | depends on host `systemMessage` handling | no |
| Notice is hidden from model input/transcript | depends on host `systemMessage` handling | no |
| Notice is excluded from compaction | depends on host transcript semantics | no |
| Strict user-only notice channel | not implemented | no |

### 2.3 Current non-guarantees

The repository cannot currently prove that:

- `systemMessage` is displayed only to the user;
- `systemMessage` is excluded from model input;
- `systemMessage` is excluded from compacted transcript recovery;
- a future agent cannot see the notice after compaction;
- a notice is routed only to the corresponding UI session in all host implementations.

Therefore `systemMessage` must be treated as a **legacy compatibility channel**, not as the final security boundary.

## 3. Problem statement

Users need to understand how much prompt budget PWF consumes, especially after context compaction and recovery. The notice must report the profile, progress mode, approximate character count, approximate token count, and profile adjustment hints.

At the same time, the notice itself must not become additional agent context. If the notice is meant only for the user, it must not be included in:

- `hookSpecificOutput.additionalContext`;
- model input;
- compacted transcript;
- later recovered context;
- planning files;
- progress auto records.

The current code solves only the first item. The remaining guarantees require explicit host support.

## 4. Goals

1. Show a context injection notice to the user when planning context is actually injected.
2. Report approximate prompt cost from the final emitted `additionalContext` string.
3. Keep notice text out of `additionalContext`.
4. Keep strict user-only notices out of model input and compaction.
5. Route notices by the current hook invocation/session, not by workspace-global state.
6. Emit blocked/skipped diagnostics without pretending context was injected.
7. Preserve existing session-scoped notice mode commands:
   - `/pwf-context-notice-auto`
   - `/pwf-context-notice-on`
   - `/pwf-context-notice-off`
8. Keep legacy `systemMessage` available only as explicit compatibility mode.

## 5. Non-goals

- Do not automatically claim stale tasks to make a notice appear.
- Do not bypass task ownership, strict session isolation, or attestation checks.
- Do not write notices to `progress.md`; progress remains the objective auto record log.
- Do not treat project-local sidecar files as hidden from the agent.
- Do not promise exact tokenizer counts; use transparent estimation `ceil(chars / 4)`.
- Do not use OS-level desktop notifications as the primary channel.
- Do not infer host support from undocumented version strings.

## 6. Terminology

| Term | Meaning |
| --- | --- |
| Agent context channel | `hookSpecificOutput.additionalContext`; planning data that is intentionally injected into the agent. |
| Legacy host message channel | `systemMessage`; current compatibility output, not a proven user-only boundary. |
| Strict user-only channel | Host-enforced notice path that is displayed to the user and excluded from model/transcript/compaction. |
| Diagnostic ledger | Optional non-sensitive metadata log for debugging; not a secrecy boundary. |
| Injection notice | Notice emitted after final context was injected; includes chars/tokens. |
| Blocked notice | Notice emitted when a policy/security gate prevented injection; never includes chars/tokens. |
| Skipped notice | Notice for non-error no-injection states such as pause, no plan, or missing host capability. |

## 7. Notice classes

### 7.1 Injection notice

Emission condition:

- final `additionalContext` was produced and emitted;
- notice mode is not `off`;
- selected notice channel supports emission.

Required semantics:

- `chars` equals `len(final_additional_context)`;
- `estimated_tokens` equals `ceil(chars / 4)`;
- message contains only metadata;
- message does not contain plan/progress/findings body text.

Example legacy message:

```text
[planning-with-files] context: profile=default, progress=tail 80 lines, ~774 chars (~194 tokens). Upgrade: /pwf-context-expanded, /pwf-context-deep. Mute: /pwf-context-notice-off.
```

### 7.2 Blocked notice

Emission condition:

- PWF considered injecting context;
- a gate prevented injection.

Examples:

- strict session isolation denied access;
- effective plan is owned by another session;
- task plan attestation mismatch;
- session binding is invalid or points to a missing plan.

Required semantics:

- no `chars` field;
- no `estimated_tokens` field;
- no profile-size claim;
- safe summary only.

Blocked notice example:

```text
[planning-with-files] planning context was not injected: task_plan.md attestation mismatch.
```

### 7.3 Skipped notice

Emission condition:

- no context was injected for a non-error reason.

Examples:

- session context injection is paused;
- no active plan exists;
- notice mode is `off`;
- channel is `auto` but host has no strict user-only capability.

Default behavior:

- do not emit noisy per-prompt skipped notices;
- expose state through `plan.py status` and `plan.py doctor`;
- optionally emit one-time user-only diagnostics when useful.

## 8. Why no token notice appears

| Situation | Context injected? | Token notice? | Diagnostic behavior |
| --- | ---: | ---: | --- |
| notice mode `off` | yes | no | no notice |
| no active plan | no | no | status/doctor should show no plan |
| session paused | no | no | status/doctor should show paused |
| strict session isolation denied | no | no | blocked notice |
| ownership denied | no | no | blocked notice |
| attestation mismatch | no | no | blocked notice |
| host lacks user-only channel and channel=`auto` | maybe | no | status/doctor warning |
| channel=`legacy-system` | yes | yes via `systemMessage` | not model-hidden guarantee |

A token notice must never be emitted when no context was injected. This avoids reporting another session's context size or implying that blocked planning data was added to the prompt.

## 9. Host contract for strict user-only notice

The Codex host must provide a hook output contract with strict user-only semantics. The field name may differ from this design, but the behavior must match.

Example shape:

```json
{
  "userNotification": {
    "kind": "planning-with-files.context_notice",
    "visibility": "user",
    "sessionKey": "3984dc71968e",
    "message": "[planning-with-files] context: profile=default, progress=tail 80 lines, ~774 chars (~194 tokens). Upgrade: /pwf-context-expanded, /pwf-context-deep. Mute: /pwf-context-notice-off.",
    "payload": {
      "version": 1,
      "state": "injected",
      "hook_event": "SessionStart",
      "hook_source": "compact",
      "profile": "default",
      "chars": 774,
      "estimated_tokens": 194
    }
  }
}
```

### 9.1 Host MUST

The host MUST:

- display the notice to the current user session;
- route by hook invocation/session identity;
- exclude notice message and payload from model input;
- exclude notice message and payload from compacted transcript;
- not merge notice data into `additionalContext`;
- ignore unknown fields safely;
- avoid broadcasting a workspace-level notice to unrelated sessions.

### 9.2 Host MUST NOT

The host MUST NOT:

- append `userNotification.message` to the conversation transcript visible to the model;
- expose strict user-only notification history through normal agent tools;
- merge notices from different sessions;
- downgrade to `systemMessage` without explicit PWF request;
- treat a diagnostic ledger as the user-only channel.

### 9.3 Minimal payload

Required for all notice states:

- `version`
- `kind`
- `state`
- `hook_event`
- `session_key`
- `message`

Required when `state=injected`:

- `profile`
- `progress_mode`
- `chars`
- `estimated_tokens`

Allowed but optional:

- `hook_source`
- `plan_id`
- `plan_source`
- `findings_mode`
- `context_truncated`
- `notice_mode`
- `notice_channel`
- `message_lang`

Forbidden in message and payload:

- planning file body text;
- progress auto record body text;
- findings body text;
- user prompt text;
- tool input/output;
- raw environment values;
- absolute project root path;
- raw session id.

## 10. Channel resolution

Add a channel resolver separate from the existing session-scoped notice mode.

Existing notice mode answers: should this session request notices?

```text
auto | on | off
```

New notice channel answers: where may the notice be sent?

```text
auto | user-only | legacy-system | silent
```

### 10.1 Channel behavior

| Channel | Behavior |
| --- | --- |
| `auto` | Use strict user-only if host capability is available; otherwise silent. Never implicit legacy fallback. |
| `user-only` | Require strict user-only host support. If unavailable, emit no notice and expose a warning in status/doctor. |
| `legacy-system` | Emit separate `systemMessage`. Compatibility only; no strict model-hidden guarantee. |
| `silent` | Emit no immediate notice. |

### 10.2 Default

Default should be:

```text
PWF_CONTEXT_NOTICE_CHANNEL=auto
```

Rationale:

- strict environments get the desired user-only behavior;
- unsupported hosts avoid accidental model-visible notices;
- legacy behavior remains available only by explicit opt-in.

### 10.3 Host capability detection

Capability detection priority:

1. Hook payload capability flag, for example `capabilities.userNotification == true`.
2. Host-provided environment flag, for example `CODEX_USER_NOTIFICATION=1`.
3. Explicit PWF override, `PWF_CONTEXT_NOTICE_CHANNEL=user-only`.
4. Otherwise unavailable.

Rules:

- Do not infer support from undocumented Codex version strings.
- `PWF_CONTEXT_NOTICE_CHANNEL=legacy-system` must be explicit.
- `auto` must not emit `systemMessage` when strict user-only support is missing.

## 11. Session routing and concurrency

Notice routing must reuse the existing PWF session identity chain:

```text
payload.session_id
  -> PWF_SESSION_ID
  -> CODEX_THREAD_ID
```

The session key remains:

```text
sha256(session_id)[:12]
```

Per-hook routing sequence:

1. read hook payload;
2. resolve root;
3. resolve session id;
4. compute session key;
5. refresh session lease;
6. resolve effective plan;
7. enforce strict session/ownership/attestation gates;
8. render final context if allowed;
9. derive notice metadata from final context;
10. emit notice only through the selected channel for the same session.

Never use workspace-global files like `.planning/.latest_notice` for routing. Never display one session's context size to another session.

## 12. Optional diagnostic ledger

A diagnostic ledger may help users inspect recent notice decisions, but it is not a user-only boundary.

Suggested layout:

```text
.planning/
  session-notices/
    <session-key>.jsonl
    <session-key>.lock
```

Rules:

- one JSON object per line;
- append-only;
- session-scoped lock;
- metadata only;
- no planning file body text;
- no prompt text;
- no tool input/output;
- documented as agent-readable unless the host stores it outside the tool-accessible filesystem.

If strict invisibility is required, the host must store notification state in private UI/session storage, not in `.planning/`.

## 13. Implementation plan

### Phase 1: Adapter and payload abstraction

Add centralized APIs in `.codex/hooks/codex_hook_adapter.py`:

```python
def emit_agent_context(event_name: str, context: str) -> None:
    emit_json({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    })


def emit_user_notice(payload: ContextNoticePayload) -> None:
    channel = resolve_notice_channel(payload)
    if channel == "user-only":
        emit_json({"userNotification": payload.to_hook_output()})
    elif channel == "legacy-system":
        emit_json({"systemMessage": payload.message})
    elif channel == "silent":
        return
```

Add centralized notice construction in `.codex/hooks/planning_state.py`:

- `ContextNoticePayload`
- `build_context_injection_notice(...)`
- `build_context_blocked_notice(...)`
- `resolve_notice_channel(...)` or equivalent channel metadata helper

Hook entrypoints should no longer directly construct context notices with `adapter.emit_json({"systemMessage": ...})`.

### Phase 2: Strict user-only channel

When the Codex host provides a documented user-only hook output:

- implement `user-only` emission;
- detect capability from payload/env;
- keep `auto` silent when unsupported;
- add status/doctor warnings when strict notices are unavailable.

### Phase 3: Status, doctor, and optional ledger

Extend `plan.py status` and `plan.py doctor` with:

```text
context notice mode: auto
context notice channel: user-only|silent|legacy-system
context notice channel source: host capability|env override|default
last context notice: SessionStart compact, profile=default, ~774 chars (~194 tokens)
```

If no strict channel exists:

```text
context notice channel: silent
context notice warning: host user-only notification channel is unavailable; legacy systemMessage is opt-in and not strict user-only
```

### Phase 4: Documentation and migration

Update:

- `README.md`
- `docs/FAQ.md`
- user guide docs
- release notes / changelog

Required wording change:

```text
Context injection notices are not written to additionalContext. When the host supports PWF's strict user-only notice channel, notices are shown only to the user and excluded from model context. In legacy-system mode, PWF can only guarantee separation from additionalContext, not strict model invisibility.
```

## 14. Gap from current code

Current code still has these gaps:

- hook entrypoints directly emit `systemMessage`;
- no `emit_agent_context(...)` abstraction;
- no `emit_user_notice(...)` abstraction;
- no `ContextNoticePayload` data model;
- no notice channel resolver;
- no host capability detection;
- no strict user-only hook output;
- no status/doctor reporting of notice channel;
- no optional per-session diagnostic ledger;
- blocked/skipped/injected notice states are not first-class payload concepts.

Current code does already provide:

- final rendered context before notice creation;
- separate JSONL output for `additionalContext` and `systemMessage`;
- chars/tokens derived from rendered text;
- session identity and session key helpers;
- task ownership and attestation gates;
- tests proving notice is not in `additionalContext` for key paths.

## 15. MVP tests

Minimum tests before merging Phase 1:

1. `UserPromptSubmit` emits `additionalContext`; notice text is not inside it.
2. `SessionStart(source=compact)` uses the same injection notice builder.
3. notice mode `off` suppresses injection notices.
4. channel `auto` without host capability emits no `systemMessage`.
5. channel `legacy-system` emits a separate `systemMessage` only when explicitly selected.
6. ownership denied emits a blocked notice with no `chars` or `estimated_tokens`.
7. attestation mismatch emits a blocked notice with no `chars` or `estimated_tokens`.
8. notice message does not contain plan/progress/findings sentinels.

## 16. Extended tests

Additional tests for later phases:

- strict `user-only` hook output shape;
- host capability detection from payload/env;
- invalid channel env falls back safely;
- multi-session A/B notices route to their own session keys;
- unbound session does not see another session's context size;
- diagnostic ledger writes are append-only and session-scoped;
- concurrent ledger writes produce valid JSONL;
- status/doctor report channel and last-notice metadata;
- legacy-system mode remains clearly opt-in.

## 17. Host-level validation

Python unit tests cannot prove model invisibility. Strict user-only semantics require host-level validation.

Validation steps:

1. Configure a test hook to emit a unique user-only notice sentinel.
2. Verify the UI shows the sentinel.
3. Inspect host model-input traces and confirm the sentinel is absent.
4. Trigger context compaction and recovery.
5. Inspect compacted/recovered transcript traces and confirm the sentinel is absent.
6. Confirm normal agent tools cannot read strict user-only notification history.

Do not rely on asking the model whether it remembers the sentinel as the only proof. The authoritative check must be host transcript/model-input tracing.

## 18. Acceptance criteria

### Functional

- If strict user-only host support exists, context injection notice is visible to the user.
- If strict support is unavailable and channel=`auto`, no immediate notice is emitted.
- If channel=`legacy-system`, notice is emitted as `systemMessage` with explicit compatibility semantics.
- `chars` and `estimated_tokens` are based on final emitted `additionalContext`.
- blocked states never include fake token usage.
- notice mode `off` suppresses injection notices.

### Security

- notice text is never written into `additionalContext`;
- notice text is never written into planning files;
- notice text is never written into progress auto records;
- strict user-only notices are absent from model input and compaction traces;
- legacy `systemMessage` is never documented as strict user-only.

### Multi-session

- session A and session B receive only their own notices;
- profile and chars/tokens are computed from the session's effective plan;
- unbound or denied sessions do not receive another session's context size;
- stale ownership does not trigger automatic claim or cross-session reporting.

### Maintainability

- hook entrypoints use adapter APIs instead of hand-built notice `systemMessage` calls;
- notice payload construction is centralized;
- channel selection is centralized;
- tests cover `auto`, `user-only`, `legacy-system`, and `silent` behavior.

## 19. Recommended conclusion

The current implementation is a useful compatibility step because the notice is no longer part of `additionalContext`. It should not be described as a strict user-only solution.

The safe target is:

```text
additionalContext -> agent context only
userNotification  -> host-enforced user-only notice
systemMessage      -> explicit legacy compatibility only
```

Until the Codex host provides a documented strict user-only notification channel, the safest default is silent `auto` behavior plus clear status/doctor diagnostics. Users who prefer current compatibility behavior may explicitly select `legacy-system`, but documentation must state that this only separates the notice from `additionalContext`; it does not prove the notice is invisible to the model.
