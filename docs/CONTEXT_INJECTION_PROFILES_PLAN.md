# Context Injection Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable planning-context injection profiles so small tasks keep lean hook payloads while large projects can request stronger recovery context after compaction or resume.

**Architecture:** Keep the current default hook output backward-compatible, then introduce a profile resolver in `planning_state.py` that computes effective limits from `PWF_CONTEXT_PROFILE` plus explicit numeric overrides. `default` keeps existing line-based behavior; `expanded` and `deep` add plan head+tail rendering and record-aware progress rendering with character budgets. Diagnostics in `plan.py status` and `plan.py doctor` make the active profile and limits visible before users rely on them.

**Tech Stack:** Python standard library, Codex hook JSON output, Markdown data blocks, `unittest`, PowerShell verification commands.

---

## 1. Background

Helsincy Plan With Files currently keeps durable task context in three active planning files:

```text
.planning/<plan-id>/task_plan.md
.planning/<plan-id>/progress.md
.planning/<plan-id>/findings.md
```

The hook injection path is bounded, which is good. It prevents a long-running task from flooding every prompt with the entire planning directory. The current limits are fixed, though, and fixed line windows become unstable when projects grow.

Current behavior:

| Hook path | Current injected content |
|----------|--------------------------|
| `UserPromptSubmit` | `task_plan.md` head 50, compact summary 20 if present, `progress.md` tail 80, `findings.md` tail 20 only when `PWF_INCLUDE_FINDINGS=1` |
| `SessionStart` | `session-catchup.py` output plus the same `render_prompt_context()` payload |
| `PreToolUse` | `task_plan.md` head 30 only |
| `PostToolUse` | Appends objective auto records for write/edit tools and warns at compact thresholds |

This is enough for many tasks. It is not reliable enough for very large work:

- `task_plan.md` head 50 can omit later decisions, errors, and final delivery status.
- `progress.md` tail 80 is not 80 records. One auto record can take many lines, so the practical window may shrink to a handful of edits.
- `findings.md` is intentionally opt-in, but when enabled, tail 20 may be too small for research-heavy work.
- Raising every default limit globally would increase token use and noise for users who do not need it.

The right change is not "make 80 bigger." The right change is "make the injection budget intentional."

## 2. Goals

- Preserve current default hook behavior for existing users.
- Let large projects opt into more planning context with one clear profile setting.
- Support precise overrides for advanced users and tests.
- Make progress injection record-aware in larger profiles, because auto records are semantic units and lines are not.
- Keep findings injection explicitly opt-in because findings may contain external or untrusted content.
- Keep `PreToolUse` lightweight so every edit does not repeat a large context payload.
- Add diagnostics so users can see the effective profile, limits, and warnings.
- Keep delimiter framing and attestation behavior intact.

## 3. Non-Goals

- Do not auto-compact `progress.md`; `/pwf-compact` remains manual.
- Do not inject full planning files by default.
- Do not let profiles bypass plan attestation.
- Do not make `findings.md` implicit in `expanded` or `deep`.
- Do not redesign `session-catchup.py` in the first implementation pass.
- Do not add model-specific token counting; use character budgets as a stable local approximation.

## 4. User-Facing Configuration

### 4.1 Profile Variable

Add:

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
```

Supported values:

| Profile | Intended user | Behavior |
|---------|---------------|----------|
| `lean` | Small tasks and noisy repos | Smaller windows than default, no new behavior |
| `default` | Existing behavior | Current limits preserved |
| `expanded` | Large feature work | More plan context, record-aware progress context |
| `deep` | Recovery after heavy compaction/resume | Largest safe window, with stricter character budget enforcement |
| `custom` | Advanced tuning | Uses default profile as base, then expects explicit override env vars |

Unset or empty `PWF_CONTEXT_PROFILE` means `default`.

Unsupported values fall back to `default` and are reported by `plan.py doctor`.

### 4.2 Explicit Override Variables

Profiles are presets. Explicit variables override the selected preset:

| Variable | Meaning |
|----------|---------|
| `PWF_PLAN_HEAD_LINES` | Number of leading `task_plan.md` lines to inject |
| `PWF_PLAN_TAIL_LINES` | Number of trailing `task_plan.md` lines to inject after the head window |
| `PWF_PROGRESS_TAIL_LINES` | Raw progress tail line count for line-based profiles |
| `PWF_PROGRESS_RECENT_RECORDS` | Number of recent auto records for record-aware profiles |
| `PWF_PROGRESS_MANUAL_TAIL_LINES` | Number of recent non-auto progress lines to preserve in record-aware mode |
| `PWF_PROGRESS_MAX_CHARS` | Character budget for rendered progress content |
| `PWF_PROGRESS_SUMMARY_LINES` | Lines from compacted progress summary |
| `PWF_FINDINGS_TAIL_LINES` | Findings tail line count when findings injection is enabled |
| `PWF_CONTEXT_MAX_CHARS` | Approximate total budget for all rendered planning data blocks |

`PWF_INCLUDE_FINDINGS=1` remains the only switch that enables findings injection. Profiles only change how much findings content is included after that switch is enabled.

## 5. Profile Defaults

The initial preset values should be conservative:

| Limit | `lean` | `default` | `expanded` | `deep` |
|-------|--------|-----------|------------|--------|
| Plan head lines | 40 | 50 | 80 | 120 |
| Plan tail lines | 0 | 0 | 40 | 80 |
| Progress raw tail lines | 40 | 80 | 0 | 0 |
| Progress recent auto records | 0 | 0 | 20 | 40 |
| Progress manual tail lines | 20 | 0 | 40 | 80 |
| Progress max chars | 8,000 | 16,000 | 24,000 | 40,000 |
| Compact summary lines | 10 | 20 | 30 | 50 |
| Findings tail lines if enabled | 10 | 20 | 60 | 120 |
| Total context max chars | 16,000 | 32,000 | 56,000 | 96,000 |
| PreToolUse plan head lines | 20 | 30 | 30 | 40 |

Why these values:

- `default` exactly matches existing user-facing windows.
- `lean` is smaller but still useful for short tasks and constrained contexts.
- `expanded` is the recommended large-project mode; it adds plan tail and record-aware progress without turning every prompt into an archive dump.
- `deep` is for deliberate recovery sessions, not everyday use.
- `custom` should not define new defaults. It should resolve as `default` plus explicit overrides, then warn if no overrides are present.
- `progress_manual_tail_lines` is ignored when `progress_recent_records == 0`; `lean` and `default` keep raw line-tail rendering.

## 6. Rendering Rules

### 6.1 Plan Rendering

Current default behavior is:

```python
_data_block("PLAN", read_head(paths.task_plan, 50))
```

Keep that exact behavior for `default`.

For profiles with tail lines, add a helper that combines head and tail without duplication:

```text
<first N lines>

[planning-with-files] ... omitted M middle lines ...

<last K lines>
```

Rules:

- If `head + tail >= total_lines`, inject the file once.
- If `tail == 0`, render only the head.
- The omission marker is generated by the hook, not read from the planning file.
- Attestation still applies before reading plan content. A tampered attested plan blocks plan injection for every profile.

### 6.2 Progress Rendering

Default keeps the existing line tail:

```python
read_progress_tail(paths.progress, 80)
```

For `expanded` and `deep`, progress becomes record-aware:

1. Remove the managed compact summary block.
2. Parse `progress.md` into text nodes and auto record nodes using the existing auto record grammar.
3. Keep the last `PWF_PROGRESS_RECENT_RECORDS` auto records.
4. Keep the last `PWF_PROGRESS_MANUAL_TAIL_LINES` lines from non-auto text.
5. Render kept nodes in chronological order.
6. Apply `PWF_PROGRESS_MAX_CHARS` by dropping the oldest kept progress content first.
7. If content is truncated, prepend a short hook-generated note inside the progress data block.

The result should still be wrapped as:

```text
---BEGIN PROGRESS DATA---
...
---END PROGRESS DATA---
```

The record-aware renderer should not read `progress.archive.md`. Archive content remains available on disk, but prompt injection should stay focused on active hot context plus compact summary.

### 6.3 Findings Rendering

Findings stay off unless explicitly enabled:

```powershell
$env:PWF_INCLUDE_FINDINGS = "1"
```

When enabled:

- Use the selected profile's findings tail line count.
- Keep the existing warning before the data block.
- Apply remaining total context budget if the rendered prompt context is too large.
- Do not summarize findings automatically. The agent should write durable summaries into `findings.md`; the hook should only frame and bound what already exists.

### 6.4 Compact Summary Rendering

`progress_lifecycle.extract_compaction_summary()` currently defaults to 20 lines. Change call sites so the profile supplies `summary_lines`.

The compact summary should remain before recent progress:

```text
=== compacted progress summary ===
---BEGIN PROGRESS SUMMARY DATA---
...
---END PROGRESS SUMMARY DATA---

=== recent progress ===
---BEGIN PROGRESS DATA---
...
---END PROGRESS DATA---
```

### 6.5 Total Context Budget

The profile should apply a final approximate `PWF_CONTEXT_MAX_CHARS` budget after individual block rendering.

Priority when trimming:

1. Trim findings first.
2. Trim progress content next.
3. Trim plan tail before plan head.
4. Never remove delimiter lines.
5. Never partially emit a delimiter block.
6. Never truncate the tamper warning.

This budget is a safety rail, not a token counter. It should be deterministic and easy to test.

## 7. Environment Parsing Rules

Add shared parsing helpers in `planning_state.py`:

- `env_int(name, default, minimum, maximum)` for numeric limits.
- `current_context_profile(env=None)` for profile names.
- `context_limits(env=None)` for effective resolved limits.
- `context_profile_warnings(env=None)` for invalid profile or override diagnostics.

Validation rules:

- Empty values fall back to the profile default.
- Non-integer values fall back to the profile default and create a doctor warning.
- Negative values fall back unless the field explicitly allows `0`.
- Upper bounds protect accidental enormous injection. Suggested hard caps:
  - lines: 2,000
  - records: 200
  - per-block chars: 200,000
  - total chars: 300,000
- `custom` with no explicit override should be valid but should produce an informational doctor line: `context profile: custom, no overrides detected; effective limits match default`.

## 8. Diagnostics

### 8.1 `plan.py status`

Add a context line:

```text
context: profile=expanded, plan=head 80 tail 40, progress=20 records, findings=off, max=56000 chars
```

If findings is enabled:

```text
context: profile=expanded, plan=head 80 tail 40, progress=20 records, findings=tail 60, max=56000 chars
```

### 8.2 `plan.py doctor`

Doctor should report:

- Active context profile.
- Unsupported profile fallback.
- Invalid numeric override fallback.
- Whether findings injection is enabled.
- Current effective progress mode: line tail or record-aware.

Example warnings:

```text
[warn] unsupported PWF_CONTEXT_PROFILE=huge; using default
[warn] invalid PWF_PROGRESS_RECENT_RECORDS=abc; using profile default 20
```

### 8.3 Hook Payload Visibility

For non-default profiles, add one hook-generated line near the top of prompt context:

```text
Context-Profile: expanded
```

Do not add this line for `default` in the first release. That keeps default payloads visually stable and minimizes test churn.

## 9. File-Level Design

| File | Planned responsibility |
|------|------------------------|
| `.codex/hooks/planning_state.py` | Resolve context profiles, render plan head/tail, render prompt context with profile limits, expose diagnostics helpers |
| `.codex/skills/planning-with-files/scripts/progress_lifecycle.py` | Add public record-aware progress context extraction using existing auto record parsing |
| `.codex/skills/planning-with-files/scripts/plan.py` | Print context profile status and doctor warnings |
| `tests/test_hooks.py` | Verify default compatibility, expanded/deep rendering, findings safety, total budget behavior |
| `tests/test_progress_compaction.py` | Verify recent auto record extraction and manual tail preservation |
| `tests/test_plan_doctor.py` | Verify profile diagnostics and invalid override warnings |
| `README.md` | Document Chinese user-facing profile usage |
| `README.en.md` | Document English user-facing profile usage |
| `docs/FAQ.md` | Add troubleshooting entry for context profiles and injection size |
| `CHANGELOG.md` | Record the feature after implementation |

## 10. Implementation Tasks

### Task 1: Add Context Limit Model

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] Add a frozen dataclass:

```python
@dataclass(frozen=True)
class ContextLimits:
    profile: str
    plan_head_lines: int
    plan_tail_lines: int
    progress_tail_lines: int
    progress_recent_records: int
    progress_manual_tail_lines: int
    progress_max_chars: int
    progress_summary_lines: int
    findings_tail_lines: int
    context_max_chars: int
    pre_tool_plan_head_lines: int
    warnings: tuple[str, ...] = ()
```

- [ ] Add preset constants for `lean`, `default`, `expanded`, and `deep`.
- [ ] Add `context_limits(env=None)` that resolves `PWF_CONTEXT_PROFILE` and numeric overrides.
- [ ] Add focused unit tests through hook execution or direct import to prove:
  - no env means `default`;
  - invalid profile falls back to `default`;
  - explicit overrides win over profile presets;
  - invalid numeric overrides do not crash.

### Task 2: Preserve Default Prompt Context Exactly

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] Refactor `render_prompt_context()` to call `context_limits()`.
- [ ] Keep the current default equivalent:

```text
PLAN head 50
compact summary 20
progress tail 80
findings tail 20 only when enabled
```

- [ ] Keep `render_pre_tool_context()` equivalent to plan head 30 under default.
- [ ] Extend existing tests instead of replacing them:
  - `test_user_prompt_submit_includes_last_80_progress_lines`
  - `test_user_prompt_submit_does_not_include_findings_by_default`
  - `test_pre_tool_use_outputs_json_system_message`

### Task 3: Add Plan Head+Tail Rendering

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] Add `read_head_tail(path, head_limit, tail_limit)`.
- [ ] Avoid duplicate lines when the file is shorter than `head + tail`.
- [ ] Add an omission marker when the middle is skipped.
- [ ] Verify `PWF_CONTEXT_PROFILE=expanded` includes both early goal text and late decision/error text from a long `task_plan.md`.
- [ ] Verify default still omits late lines when the file exceeds 50 lines.

### Task 4: Add Record-Aware Progress Extraction

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py`
- Test: `tests/test_progress_compaction.py`

- [ ] Add a public function:

```python
def extract_recent_progress_context(
    progress_path: Path,
    record_limit: int,
    manual_tail_lines: int,
    max_chars: int,
) -> str:
    ...
```

- [ ] Reuse existing auto record parsing rules so compaction and context rendering agree.
- [ ] Preserve recent manual progress notes as bounded text.
- [ ] Preserve the last N auto records as complete records.
- [ ] Apply `max_chars` by dropping oldest kept content first.
- [ ] Include a deterministic truncation note when content was dropped.
- [ ] Add tests for:
  - long records with many files;
  - manual notes after auto records;
  - managed compact summary exclusion;
  - character budget truncation;
  - empty or missing progress file.

### Task 5: Wire Record-Aware Progress into Expanded Profiles

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] In `render_prompt_context()`, use raw line tail when `progress_recent_records == 0`.
- [ ] Use `extract_recent_progress_context()` when `progress_recent_records > 0`.
- [ ] Verify `PWF_CONTEXT_PROFILE=expanded` can include 20 complete recent records even when those records exceed 80 raw lines.
- [ ] Verify `PWF_CONTEXT_PROFILE=deep` uses the larger configured record count.
- [ ] Verify line-based `default` output remains compatible.

### Task 6: Apply Findings and Summary Limits

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py` if needed for call signature only
- Test: `tests/test_hooks.py`

- [ ] Pass `limits.progress_summary_lines` into `progress_summary_block()`.
- [ ] Pass `limits.findings_tail_lines` into findings rendering.
- [ ] Verify `PWF_CONTEXT_PROFILE=expanded` does not inject findings unless `PWF_INCLUDE_FINDINGS=1`.
- [ ] Verify expanded findings uses 60 tail lines when enabled.
- [ ] Verify deep findings uses 120 tail lines when enabled.

### Task 7: Add Total Budget Enforcement

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] Add deterministic block-level trimming that preserves delimiters.
- [ ] Trim findings before progress.
- [ ] Trim plan tail before plan head.
- [ ] Verify budget enforcement with a deliberately large plan, progress, and findings fixture.
- [ ] Verify tamper warning output is never trimmed.

### Task 8: Add CLI Diagnostics

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_doctor.py`
- Test: `tests/test_plan_cli.py`

- [ ] Add status line for effective context profile and limits.
- [ ] Add doctor lines for:
  - active profile;
  - findings on/off;
  - progress mode;
  - invalid profile fallback;
  - invalid numeric override fallback.
- [ ] Keep existing progress compact threshold diagnostics unchanged.
- [ ] Add Chinese messages if `PWF_LANG=zh-CN` is enabled.

### Task 9: Update User Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py` if new consistency checks are useful

- [ ] Add a concise README section:

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
$env:PWF_INCLUDE_FINDINGS = "1"
```

- [ ] Explain when to use `lean`, `default`, `expanded`, and `deep`.
- [ ] Explain that findings remain opt-in.
- [ ] Add FAQ troubleshooting for "I still lose context after compaction" and "Why is hook context larger now?"
- [ ] Record the feature in the changelog only when implementation ships.

### Task 10: Final Verification

**Files:**
- No new source files expected.

- [ ] Run focused hook tests:

```powershell
python -m unittest tests.test_hooks -v
```

- [ ] Run lifecycle and CLI tests:

```powershell
python -m unittest tests.test_progress_compaction tests.test_plan_doctor tests.test_plan_cli -v
```

- [ ] Run the full suite:

```powershell
python -m unittest discover -v
```

- [ ] Run whitespace check:

```powershell
git diff --check
```

- [ ] Run doctor:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Expected result: all tests pass; doctor reports active plan and context diagnostics without unexpected warnings.

## 11. Rollout Strategy

1. Ship the profile resolver with default behavior unchanged.
2. Add expanded/deep behavior behind `PWF_CONTEXT_PROFILE`.
3. Add diagnostics before broad documentation so early adopters can self-check.
4. Update README and FAQ after behavior is verified.
5. Keep a follow-up issue for `session-catchup.py` profile support after the main path is stable.

## 12. Risk Analysis

| Risk | Mitigation |
|------|------------|
| Larger prompts increase token cost | Keep default unchanged; require explicit profile selection for larger payloads |
| Findings could contain untrusted external text | Keep `PWF_INCLUDE_FINDINGS` as the explicit gate and preserve warning text |
| Record-aware progress misses manual notes | Preserve bounded manual tail lines in expanded/deep |
| Character trimming breaks delimiter framing | Trim block content before wrapping or trim whole blocks only |
| Invalid env vars cause silent confusion | Report fallback warnings in doctor |
| Tests become brittle around exact payload text | Preserve default output and add profile-specific tests with targeted assertions |

## 13. Open Follow-Ups

These are deliberately outside the first implementation:

- Profile-aware `session-catchup.py` limits.
- A `/pwf-context` command for interactively showing or switching profiles.
- Token estimation by model family.
- Automatic profile suggestion based on planning file sizes.
- Optional archive search or selective archive injection.

## 14. Acceptance Criteria

The feature is ready when:

- Existing default hook behavior remains compatible.
- `PWF_CONTEXT_PROFILE=expanded` includes plan tail and complete recent progress records.
- `PWF_CONTEXT_PROFILE=deep` provides a larger bounded recovery payload.
- `PWF_INCLUDE_FINDINGS` remains required for findings injection.
- `plan.py status` and `plan.py doctor` display effective context profile details.
- Invalid profile and numeric env values are visible in diagnostics and do not crash hooks.
- The full unittest suite passes.
- README, FAQ, and changelog explain the feature when implementation ships.
