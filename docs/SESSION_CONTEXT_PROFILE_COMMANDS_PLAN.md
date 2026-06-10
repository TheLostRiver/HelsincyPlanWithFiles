# Session Context Profile Commands Plan

## Goal

Add session-scoped context profile commands so users can switch the current Codex conversation between `lean`, `default`, `expanded`, and `deep` planning-context modes without typing environment-variable commands. Also add an optional context injection notice so users can see when PWF has restored task context and roughly how much prompt budget it used.

## Background

PWF already supports context profiles through `PWF_CONTEXT_PROFILE`:

| Profile | Current behavior |
|---------|------------------|
| `lean` | Smaller plan/progress windows |
| `default` | Compatible behavior, progress tail by lines |
| `expanded` | Larger plan head/tail and recent progress by complete auto records |
| `deep` | Even larger recovery payload, recent progress by complete auto records |
| `custom` | Advanced numeric overrides through `PWF_*` variables |

Record-aware progress injection already exists. `expanded` injects 20 recent auto records and `deep` injects 40. The remaining gap is usability: users must currently remember and set environment variables such as:

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
```

That is too manual for ordinary users and awkward for same-project multi-session workflows.

## User Experience

Add button-like slash commands:

```text
/pwf-context-expanded
/pwf-context-deep
/pwf-context-default
/pwf-context-lean
/pwf-context-status
/pwf-context-notice-on
/pwf-context-notice-off
/pwf-context-notice-auto
```

Each preset command changes only the current session. It must not change `.planning/.active_plan`, other sessions, or a workspace-wide default.

`/pwf-context-status` shows the effective profile and where it came from:

```text
session context:
  profile: expanded
  source: session
  notice: auto
  progress mode: record-aware 20 records
  plan: head 80 tail 40
  findings: off
  max: 56000 chars
```

If an environment variable overrides the session setting:

```text
session context:
  profile: deep
  source: env PWF_CONTEXT_PROFILE
  session profile: expanded, currently overridden
  notice: auto
  progress mode: record-aware 40 records
  plan: head 120 tail 80
  findings: off
  max: 96000 chars
```

## CLI Design

Keep a single underlying CLI surface for tests, automation, and advanced users:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py context status
python .codex\skills\planning-with-files\scripts\plan.py context set expanded
python .codex\skills\planning-with-files\scripts\plan.py context set deep
python .codex\skills\planning-with-files\scripts\plan.py context set default
python .codex\skills\planning-with-files\scripts\plan.py context set lean
python .codex\skills\planning-with-files\scripts\plan.py context notice on
python .codex\skills\planning-with-files\scripts\plan.py context notice off
python .codex\skills\planning-with-files\scripts\plan.py context notice auto
python .codex\skills\planning-with-files\scripts\plan.py context clear
```

Only the public user-facing slash commands need to be button-like. The CLI can remain structured.

Unsupported `custom` session presets should be rejected by `context set`. `custom` stays environment-variable only because it needs numeric overrides and is not a simple preset.

## Session Storage

Store the current session context settings under:

```text
.planning/session-context/<session-key>.json
```

Example:

```json
{
  "version": 1,
  "session_id": "opaque-session-id",
  "profile": "expanded",
  "notice": "auto",
  "created_at": "2026-06-10T06:30:00Z",
  "updated_at": "2026-06-10T06:30:00Z",
  "source": "plan.py context set"
}
```

Rules:

- `profile` is one of `lean`, `default`, `expanded`, or `deep`.
- `notice` is one of `auto`, `on`, or `off`.
- The file is keyed by `planning_state.session_key(session_id)`, not raw session id.
- The raw session id may be included inside the JSON payload for diagnostics, following the existing session-binding payload pattern.
- Writes use a temp file plus replace, matching session-binding safety.

## Session Identity

The CLI continues to identify the current session from:

```text
PWF_SESSION_ID
CODEX_THREAD_ID
```

The hook path continues to identify the current session from the hook payload first, with existing environment fallbacks.

If no session id is available:

- `context status` still works and reports no session profile.
- `context set ...`, `context notice ...`, and `context clear` fail with a clear message.
- The command must not write workspace-level context settings as a fallback.

This protects the promise that preset commands affect only the current conversation.

## Precedence

Resolve context settings in this order:

1. Explicit environment variables:
   - `PWF_CONTEXT_PROFILE`
   - numeric `PWF_*` limit overrides
   - `PWF_CONTEXT_NOTICE`
2. Session context file for the current session.
3. Built-in defaults.

Environment variables remain the highest priority because they are explicit operator or CI configuration. When an environment profile overrides a session profile, status and doctor output should say so.

## Hook Injection Notice

Add an optional notice line to rendered prompt context.

English:

```text
[planning-with-files] Injected current-session planning context: profile=expanded, progress=20 records, approx 18.4k chars (~4.6k tokens).
```

Chinese:

```text
[planning-with-files] 已自动注入当前会话的任务上下文：profile=expanded，progress=20 records，约 18.4k chars（估算 4.6k tokens）。
```

The notice is metadata generated by the hook, not content copied from planning files.

### Notice Modes

| Mode | Behavior |
|------|----------|
| `off` | Never show the notice. |
| `on` | Show the notice whenever prompt context is injected. |
| `auto` | Show the notice when it is especially useful: `expanded`, `deep`, or `SessionStart` context rendering. |

Default notice mode is `auto`.

The implementation cannot reliably know every Codex context-compaction event. The design therefore does not promise exact compaction detection. It gives a reliable signal when PWF injects recovery-oriented context.

### Size Estimate

Use the rendered context string length for chars. Estimate tokens with a simple transparent approximation:

```text
estimated_tokens = ceil(chars / 4)
```

This is intentionally approximate. Do not call it exact tokens.

The estimate should reflect the final rendered context after total-budget trimming. If adding the notice would exceed the budget, the budget application may trim lower-priority data as it already does, but must preserve security metadata and delimiters.

## Status And Doctor Output

Extend `plan.py status` and `plan.py doctor` so users can understand effective behavior.

Status should include:

- effective profile
- source: `env`, `session`, or `default`
- session profile when overridden
- notice mode and source
- progress mode
- plan head/tail limits
- findings status
- context max chars

Doctor should add machine-readable-ish plain text lines:

```text
context profile: expanded
context profile source: session
context notice: auto
context progress mode: record-aware 20 records
```

When overridden:

```text
context profile source: env PWF_CONTEXT_PROFILE
context session profile: expanded overridden
```

## Error Handling

Rejected operations:

- `context set custom`
- `context set <unsupported-profile>`
- `context notice <unsupported-mode>`
- any mutating context command without a session id
- malformed existing session-context JSON should be ignored for effective behavior and reported by doctor as a warning

Invalid file contents should never crash hooks. Hooks should fall back to environment or default behavior.

## Files To Modify

| File | Purpose |
|------|---------|
| `.codex/hooks/planning_state.py` | Resolve session context profile and notice mode; render injection notice; expose diagnostics. |
| `.codex/skills/planning-with-files/scripts/plan.py` | Add `context` subcommand, session-context read/write helpers, status/doctor output. |
| `.codex/skills/pwf-context-expanded/SKILL.md` | Slash wrapper for `plan.py context set expanded`. |
| `.codex/skills/pwf-context-deep/SKILL.md` | Slash wrapper for `plan.py context set deep`. |
| `.codex/skills/pwf-context-default/SKILL.md` | Slash wrapper for `plan.py context set default`. |
| `.codex/skills/pwf-context-lean/SKILL.md` | Slash wrapper for `plan.py context set lean`. |
| `.codex/skills/pwf-context-status/SKILL.md` | Slash wrapper for `plan.py context status`. |
| `.codex/skills/pwf-context-notice-on/SKILL.md` | Slash wrapper for `plan.py context notice on`. |
| `.codex/skills/pwf-context-notice-off/SKILL.md` | Slash wrapper for `plan.py context notice off`. |
| `.codex/skills/pwf-context-notice-auto/SKILL.md` | Slash wrapper for `plan.py context notice auto`. |
| `tests/test_hooks.py` | Hook resolution and injection notice tests. |
| `tests/test_plan_cli.py` | CLI context command tests. |
| `tests/test_plan_doctor.py` | Doctor output tests. |
| `tests/test_pwf_commands.py` | Slash wrapper coverage. |
| `tests/test_project_consistency.py` | Documentation consistency expectations. |
| `README.md` / `README.en.md` | User-facing docs. |
| `docs/FAQ.md` | Troubleshooting and plain-language explanation. |
| `docs/USER_GUIDE.zh-CN.md` | Beginner-friendly usage notes. |
| `CHANGELOG.md` | Unreleased entry. |

## Testing Strategy

Tests should prove:

- session context files are written under the current session key only
- missing session id rejects mutating commands
- `expanded` and `deep` session settings affect hook context without env vars
- `PWF_CONTEXT_PROFILE` overrides session settings
- status and doctor show source and override details
- notice modes behave as `auto/on/off`
- notice chars/tokens are present and approximate
- malformed session-context JSON does not crash hooks or CLI
- all new slash wrappers exist and route to `plan.py context`
- docs mention the new commands and the session-only behavior

Run at minimum:

```powershell
python -m unittest tests.test_plan_cli tests.test_hooks tests.test_plan_doctor tests.test_pwf_commands tests.test_project_consistency -v
python -m unittest discover -v
git diff --check
```

## Release Notes Draft

中文：

- 新增会话级 context profile 快捷命令：`/pwf-context-expanded`、`/pwf-context-deep`、`/pwf-context-default`、`/pwf-context-lean` 和 `/pwf-context-status`，默认只影响当前会话。
- 新增 context injection notice 开关：`/pwf-context-notice-auto`、`/pwf-context-notice-on`、`/pwf-context-notice-off`，可提示 PWF 已自动注入任务上下文及大致占用。

English:

- Added session-scoped context profile shortcut commands: `/pwf-context-expanded`, `/pwf-context-deep`, `/pwf-context-default`, `/pwf-context-lean`, and `/pwf-context-status`.
- Added context injection notice controls: `/pwf-context-notice-auto`, `/pwf-context-notice-on`, and `/pwf-context-notice-off`, with approximate prompt-size reporting.
