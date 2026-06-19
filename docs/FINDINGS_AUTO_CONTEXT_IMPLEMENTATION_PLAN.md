# Findings Auto Context Implementation Plan

## Goal

Make planning recovery preserve important `findings.md` context by default, while keeping prompt payloads bounded, preserving delimiter-based safety, and using Codex's supported context-injection hooks.

## Background

`task_plan.md` is already injected through `SessionStart`, `UserPromptSubmit`, and the lightweight `PreToolUse` path. `findings.md` is currently injected only when `PWF_INCLUDE_FINDINGS=1` is set, even though current guidance tells agents to put decisions, test conclusions, external summaries, and interpretive notes in `findings.md`.

That creates a recovery gap after `/clear`, resume, or Codex context compaction: the files remain on disk, but the default hook context may omit the reasoning context that explains why the current plan looks the way it does.

OpenAI's Codex hook docs list `SessionStart` sources including `startup`, `resume`, `clear`, and `compact`, and list `PostCompact` as a separate event. The supported extra developer context path is already used by `SessionStart` and `UserPromptSubmit` through `hookSpecificOutput.additionalContext`.

## Decisions

- Keep `PostCompact` out of scope for this change. It is a more precise lifecycle event, but it is not the established context-injection channel in this codebase.
- Extend the `SessionStart` matcher from `startup|resume` to `startup|resume|compact` so Codex compaction recovery uses the same `additionalContext` path as startup and resume.
- Keep `PreCompact` as a reminder and attestation anchor only. It must not inject `task_plan.md`, `progress.md`, or `findings.md` contents.
- Change findings injection from default-off to default-auto for `SessionStart` and `UserPromptSubmit`.
- Preserve explicit opt-out: `PWF_INCLUDE_FINDINGS=0`, `false`, `no`, or `off` disables findings injection.
- Preserve explicit opt-in: `PWF_INCLUDE_FINDINGS=1`, `true`, `yes`, or `on` enables findings injection.
- Treat unset `PWF_INCLUDE_FINDINGS` as auto-enabled for prompt context rendering.
- Keep invalid `PWF_INCLUDE_FINDINGS` values safe: warn, sanitize the value, and do not enable findings.
- Keep findings framed as data with the existing warning and `---BEGIN FINDINGS DATA---` / `---END FINDINGS DATA---` delimiters.
- Keep findings bounded by the existing profile limits: lean 10, default 20, expanded 60, deep 120, and explicit `PWF_FINDINGS_TAIL_LINES` overrides.
- Keep total context budget trimming order unchanged, with findings trimmed before progress, progress summary, and plan content.

## User-Visible Behavior

By default, `UserPromptSubmit` and `SessionStart` include:

- plan context;
- compacted progress summary when present;
- recent progress context;
- recent findings tail;
- the existing footer and context injection notice.

`/pwf-status` and `/pwf-doctor` should report default findings state as auto, not off. Explicit true values report enabled tail limits. Explicit false values report off. Invalid values report off plus a warning.

`SessionStart` should run after Codex compaction when the event source is `compact`, using the same renderer and session-bound planning resolver as startup and resume.

## Out Of Scope

- Adding a `PostCompact` hook.
- Adding new persistent state for compaction recovery.
- Moving findings content into `task_plan.md`.
- Reintroducing manual write prompts for `progress.md`.
- Changing `PreToolUse` to inject findings.

## Task 1: Add Failing Hook Tests For Default Findings Injection

Files:

- Modify `tests/test_hooks.py`

Steps:

1. Rename `test_user_prompt_submit_does_not_include_findings_by_default` to `test_user_prompt_submit_includes_findings_by_default`.
2. Change its assertions to require the findings warning, `---BEGIN FINDINGS DATA---`, `- external fact`, and `---END FINDINGS DATA---`.
3. Rename `test_user_prompt_submit_expanded_profile_does_not_enable_findings_by_itself` to `test_user_prompt_submit_expanded_profile_includes_findings_by_default`.
4. Assert that expanded profile includes the findings block and the sample finding by default.
5. Add `test_user_prompt_submit_disables_findings_when_explicitly_false` using `env={"PWF_INCLUDE_FINDINGS": "0"}` and assert the findings block is absent.
6. Keep the existing explicit opt-in, tail override, Chinese warning, budget trimming, and invalid flag tests.

Focused command:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_includes_findings_by_default tests.test_hooks.HookTests.test_user_prompt_submit_expanded_profile_includes_findings_by_default tests.test_hooks.HookTests.test_user_prompt_submit_disables_findings_when_explicitly_false -v
```

Expected before implementation: default include tests fail because findings are still gated off by default.

## Task 2: Implement Tri-State Findings Injection

Files:

- Modify `.codex/hooks/planning_state.py`
- Test `tests/test_hooks.py`

Steps:

1. Add `findings_injection_state(env=None) -> tuple[str, bool, str | None]` near `findings_injection_enabled()`.
2. Return `("auto", True, None)` when `PWF_INCLUDE_FINDINGS` is unset.
3. Return `("on", True, None)` for `1`, `true`, `yes`, and `on`.
4. Return `("off", False, None)` for `0`, `false`, `no`, and `off`.
5. Return `("invalid", False, warning)` for every other value, using `safe_env_value(raw)` in the warning.
6. Update `findings_injection_enabled()` to call `findings_injection_state()` and return only the enabled boolean.
7. Leave `render_prompt_context()` structurally unchanged so findings are included by default in `SessionStart` and `UserPromptSubmit`.

Implementation sketch:

```python
def findings_injection_state(
    env: Mapping[str, str] | None = None,
) -> tuple[str, bool, str | None]:
    source = env if env is not None else os.environ
    raw = source.get("PWF_INCLUDE_FINDINGS")
    if raw is None:
        return "auto", True, None
    value = raw.strip(" \t\r\n").lower()
    if value == "auto":
        return "auto", True, None
    if value in {"1", "true", "yes", "on"}:
        return "on", True, None
    if value in {"0", "false", "no", "off"}:
        return "off", False, None
    warning = f'[warn] invalid PWF_INCLUDE_FINDINGS="{safe_env_value(raw)}"; findings injection disabled'
    return "invalid", False, warning
```

Focused command:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_includes_findings_by_default tests.test_hooks.HookTests.test_user_prompt_submit_expanded_profile_includes_findings_by_default tests.test_hooks.HookTests.test_user_prompt_submit_disables_findings_when_explicitly_false tests.test_hooks.HookTests.test_user_prompt_submit_invalid_findings_flag_does_not_enable_findings -v
```

Expected after implementation: all listed tests pass.

## Task 3: Update Status And Doctor Findings Diagnostics

Files:

- Modify `.codex/skills/planning-with-files/scripts/plan.py`
- Modify `tests/test_plan_cli.py`
- Modify `tests/test_plan_doctor.py`

Steps:

1. Replace `_findings_context_enabled()` with `_findings_context_state()` that calls `planning_state.findings_injection_state()`.
2. Update `_context_findings_text()` to report `auto tail N` for the unset/default state, `tail N` for explicit true values, and `off` for false or invalid values.
3. Update `_context_doctor_lines()` to report `context findings: auto tail N`, `context findings: on tail N`, or `context findings: off`.
4. Preserve invalid-value warnings in doctor output.
5. Update `test_status_reports_active_plan_summary` to expect `findings=auto tail 20`.
6. Keep `test_status_reports_expanded_context_profile_summary` explicit opt-in expectation as `findings=tail 60`.
7. Add `test_status_reports_findings_off_when_explicitly_disabled`.
8. Update `test_doctor_reports_healthy_project` to expect `context findings: auto tail 20`.
9. Keep `test_doctor_reports_expanded_context_profile` explicit opt-in expectation as `context findings: on tail 60`.

Focused command:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_status_reports_active_plan_summary tests.test_plan_cli.PlanCliTests.test_status_reports_expanded_context_profile_summary tests.test_plan_cli.PlanCliTests.test_status_reports_findings_off_when_explicitly_disabled tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_healthy_project tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_expanded_context_profile -v
```

Expected after implementation: all listed tests pass.

## Task 4: Make SessionStart Match Codex Compact Recovery

Files:

- Modify `.codex/hooks.json`
- Modify `tests/test_project_consistency.py`
- Modify `tests/test_hooks.py`

Steps:

1. Add `test_session_start_hook_matches_compact_source` near `test_hooks_json_references_existing_hook_files`.
2. Assert that at least one `SessionStart` matcher contains `compact` as a `|`-separated token.
3. Update `.codex/hooks.json` from `"matcher": "startup|resume"` to `"matcher": "startup|resume|compact"`.
4. Do not add a `PostCompact` hook.
5. Add `test_session_start_compact_source_outputs_prompt_context` to run `session_start.py` with `{"hook_event_name": "SessionStart", "source": "compact", "session_id": "session-a"}`.
6. In that test, create `findings.md` with `- compact recovery finding` and assert the `additionalContext` contains both `# Task Plan: Test` and that finding.

Focused command:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_session_start_hook_matches_compact_source tests.test_hooks.HookTests.test_session_start_compact_source_outputs_prompt_context -v
```

Expected after implementation: both tests pass.

## Task 5: Update Documentation

Files:

- Modify `README.en.md`
- Modify `README.md`
- Modify `docs/FAQ.md`
- Modify `.codex/skills/planning-with-files/SKILL.md`
- Modify `CHANGELOG.md`

Steps:

1. Replace language that says `findings.md` is always opt-in.
2. Document that `UserPromptSubmit` and `SessionStart` include a bounded findings tail by default.
3. Document `PWF_INCLUDE_FINDINGS=0` as the opt-out.
4. Document `PWF_FINDINGS_TAIL_LINES=N` as the tail override.
5. Preserve the warning that findings can contain untrusted external context.
6. Document that `SessionStart` now matches Codex's `compact` source and reuses the normal prompt-context renderer after compaction.
7. State that `PostCompact` is intentionally not used for context injection in this release.
8. Keep `PreCompact` documented as non-injective. If the wording says files "will be re-read after compaction", revise it to "will be available for re-injection or manual reading after compaction."

Focused command:

```powershell
python -m unittest tests.test_project_consistency tests.test_plan_cli tests.test_plan_doctor tests.test_hooks -v
```

Expected after documentation updates: all listed test modules pass.

## Task 6: Full Verification

Steps:

1. Run the full suite:

```powershell
python -m unittest discover -v
```

2. Validate hook JSON:

```powershell
python -m json.tool .codex/hooks.json > $null
Select-String -Path .codex/hooks.json -Pattern '"matcher": "startup\|resume\|compact"'
```

3. Review the final diff:

```powershell
git diff -- .codex/hooks/planning_state.py .codex/hooks.json .codex/skills/planning-with-files/scripts/plan.py tests README.en.md README.md docs/FAQ.md .codex/skills/planning-with-files/SKILL.md CHANGELOG.md
```

Expected:

- no `PostCompact` hook was added;
- `PreCompact` still does not inject file contents;
- findings are framed as data only;
- invalid `PWF_INCLUDE_FINDINGS` values are sanitized and do not enable findings;
- `SessionStart` covers `compact`;
- full tests pass.
