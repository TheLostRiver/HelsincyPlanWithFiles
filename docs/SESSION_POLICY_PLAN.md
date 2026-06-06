# Session Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make planning context recovery reliable after Codex compaction or resume by replacing implicit session isolation with an explicit session policy.

**Architecture:** Default hook behavior becomes workspace-wide: the active plan resolved from `PLAN_ID`, `.planning/.active_plan`, newest `.planning/<plan-id>/task_plan.md`, or legacy root files is injected even when `.planning/sessions/` exists. Strict session isolation remains available only through explicit configuration, using `PWF_SESSION_MODE=strict` or `.planning/session-policy.json`. Strict-mode denials produce a clear diagnostic JSON message instead of silent no-output behavior.

**Tech Stack:** Python standard library, Codex hook stdin/stdout JSON, `unittest`, Markdown docs.

---

## Current State

- Previous encoding-safety fix was committed and pushed as `1ac1379 fix: make hook json output encoding safe`.
- Current branch is `main`; `origin/main` includes that commit.
- `dist/` is untracked release output and must remain untouched unless release packaging is explicitly requested.
- `.planning/` is ignored runtime context and must not be committed.

## Design Rules

- Default mode is `workspace`.
- `.planning/sessions/` is data only in workspace mode; its existence must not enable isolation.
- Strict mode is explicit only:
  - `PWF_SESSION_MODE=strict`, or
  - `.planning/session-policy.json` with `{"mode":"strict"}`.
- Environment variable wins over policy file. Valid modes are `workspace` and `strict`.
- Unsupported `PWF_SESSION_MODE` values fall back to `workspace` and are reported by `plan.py doctor`.
- Strict mode with an attached session continues to allow hook context.
- Strict mode with missing or unattached session denies context and emits a diagnostic `systemMessage`.
- Hook JSON output stays ASCII-safe through `codex_hook_adapter.emit_json()`.

## Files

- Modify: `.codex/hooks/codex_hook_adapter.py`
  - Own session policy loading, mode resolution, and hook attachment decisions.
  - Add a reusable diagnostic helper for denied strict-mode hooks.
- Modify: `.codex/hooks/session_start.py`
  - Replace silent `is_session_attached()` return with a helper that can emit strict-mode diagnostics.
- Modify: `.codex/hooks/user_prompt_submit.py`
  - Same session-policy gate behavior as `SessionStart`.
- Modify: `.codex/hooks/pre_tool_use.py`
  - Same session-policy gate behavior as prompt hooks.
- Modify: `.codex/hooks/post_tool_use.py`
  - Same session-policy gate behavior before progress append.
- Modify: `.codex/hooks/stop.py`
  - Same session-policy gate behavior before incomplete-task blocking.
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
  - Add session policy messages to `doctor`.
- Modify: `tests/test_hooks.py`
  - Add behavior tests for workspace default and strict isolation.
- Modify: `tests/test_plan_doctor.py`
  - Add doctor diagnostics for workspace mode, strict mode, and unsupported env values.
- Modify: `README.en.md`
  - Document workspace default and explicit strict mode.
- Modify: `README.md`
  - Document the same behavior in Chinese.
- Modify: `CHANGELOG.md`
  - Add an Unreleased entry.
- Modify: `tests/test_project_consistency.py`
  - Require README documentation for session policy.

---

### Task 1: Preserve Workspace Injection When Sessions Directory Exists

**Files:**
- Test: `tests/test_hooks.py`
- Modify: `.codex/hooks/codex_hook_adapter.py`

- [ ] **Step 1: Write the failing default-workspace test**

Add this test to `HookTests` after `test_user_prompt_submit_outputs_json_additional_context`:

```python
    def test_user_prompt_submit_uses_workspace_mode_when_sessions_dir_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            (root / ".planning" / "sessions").mkdir(parents=True)

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            context = payload["hookSpecificOutput"]["additionalContext"]
            self.assertIn("# Task Plan: Test", context)
            self.assertIn("---BEGIN PLAN DATA---", context)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_uses_workspace_mode_when_sessions_dir_exists -v
```

Expected: FAIL because `result.stdout` is empty when `.planning/sessions/` exists without `session_id`.

- [ ] **Step 3: Add policy helpers and workspace default**

In `.codex/hooks/codex_hook_adapter.py`, add these constants and helpers after `HOOK_DIR`:

```python
SESSION_MODES = {"workspace", "strict"}
DEFAULT_SESSION_MODE = "workspace"


def _session_policy_path(root: Path) -> Path:
    return root / ".planning" / "session-policy.json"


def _session_mode_from_policy_file(root: Path) -> str | None:
    policy = _session_policy_path(root)
    if not policy.is_file():
        return None
    try:
        payload = json.loads(policy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    mode = payload.get("mode")
    if isinstance(mode, str):
        return mode.strip().lower()
    return None


def session_mode(root: Path) -> str:
    env_mode = os.environ.get("PWF_SESSION_MODE", "").strip().lower()
    raw_mode = env_mode or _session_mode_from_policy_file(root) or DEFAULT_SESSION_MODE
    return raw_mode if raw_mode in SESSION_MODES else DEFAULT_SESSION_MODE
```

Replace `is_session_attached()` with:

```python
def is_session_attached(root: Path, session_id: str | None) -> bool:
    """Return True if this hook event should receive plan context."""
    if session_mode(root) != "strict":
        return True

    sessions_dir = root / ".planning" / "sessions"
    if not session_id:
        return False
    return (sessions_dir / f"{session_id}.attached").exists()
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_uses_workspace_mode_when_sessions_dir_exists -v
```

Expected: PASS.

- [ ] **Step 5: Run current hook tests**

Run:

```powershell
python -m unittest tests.test_hooks -v
```

Expected: all hook tests pass.

---

### Task 2: Keep Strict Session Isolation Explicit and Tested

**Files:**
- Test: `tests/test_hooks.py`
- Modify: `.codex/hooks/codex_hook_adapter.py`

- [ ] **Step 1: Add strict-mode allow and deny tests**

Add these tests near the workspace-mode test:

```python
    def test_user_prompt_submit_strict_mode_requires_attached_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            sessions = root / ".planning" / "sessions"
            sessions.mkdir(parents=True)

            missing = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue"},
                env={"PWF_SESSION_MODE": "strict"},
            )
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertEqual(missing.stdout.strip(), "")

            unattached = run_hook(
                "user_prompt_submit.py",
                root,
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "continue",
                    "session_id": "abc",
                },
                env={"PWF_SESSION_MODE": "strict"},
            )
            self.assertEqual(unattached.returncode, 0, unattached.stderr)
            self.assertEqual(unattached.stdout.strip(), "")

            (sessions / "abc.attached").write_text("attached\n", encoding="utf-8")
            attached = run_hook(
                "user_prompt_submit.py",
                root,
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "continue",
                    "session_id": "abc",
                },
                env={"PWF_SESSION_MODE": "strict"},
            )

            self.assertEqual(attached.returncode, 0, attached.stderr)
            context = json.loads(attached.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("# Task Plan: Test", context)

    def test_user_prompt_submit_strict_mode_can_be_enabled_by_policy_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            sessions = root / ".planning" / "sessions"
            sessions.mkdir(parents=True)
            (root / ".planning" / "session-policy.json").write_text(
                json.dumps({"mode": "strict"}),
                encoding="utf-8",
            )

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "")
```

- [ ] **Step 2: Run strict-mode tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_requires_attached_session tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_can_be_enabled_by_policy_file -v
```

Expected: PASS after Task 1 implementation.

- [ ] **Step 3: Add invalid env fallback test**

Add this test:

```python
    def test_user_prompt_submit_unsupported_session_mode_falls_back_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            (root / ".planning" / "sessions").mkdir(parents=True)

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue"},
                env={"PWF_SESSION_MODE": "surprise"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("# Task Plan: Test", context)
```

- [ ] **Step 4: Run all session policy hook tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_uses_workspace_mode_when_sessions_dir_exists tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_requires_attached_session tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_can_be_enabled_by_policy_file tests.test_hooks.HookTests.test_user_prompt_submit_unsupported_session_mode_falls_back_to_workspace -v
```

Expected: PASS.

---

### Task 3: Emit Diagnostics Instead of Silent Strict-Mode Denials

**Files:**
- Test: `tests/test_hooks.py`
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Modify: `.codex/hooks/session_start.py`
- Modify: `.codex/hooks/user_prompt_submit.py`
- Modify: `.codex/hooks/pre_tool_use.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Modify: `.codex/hooks/stop.py`

- [ ] **Step 1: Update strict denial tests to expect diagnostics**

Replace the empty-stdout checks in `test_user_prompt_submit_strict_mode_requires_attached_session` with diagnostic assertions:

```python
            self.assertEqual(missing.returncode, 0, missing.stderr)
            missing_payload = json.loads(missing.stdout)
            self.assertIn("systemMessage", missing_payload)
            self.assertIn("session isolation is strict", missing_payload["systemMessage"])
            self.assertIn("no session_id", missing_payload["systemMessage"])

            self.assertEqual(unattached.returncode, 0, unattached.stderr)
            unattached_payload = json.loads(unattached.stdout)
            self.assertIn("systemMessage", unattached_payload)
            self.assertIn("session isolation is strict", unattached_payload["systemMessage"])
            self.assertIn("not attached", unattached_payload["systemMessage"])
```

Replace the empty-stdout check in `test_user_prompt_submit_strict_mode_can_be_enabled_by_policy_file` with:

```python
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("systemMessage", payload)
            self.assertIn("session isolation is strict", payload["systemMessage"])
```

- [ ] **Step 2: Run the diagnostics tests to verify failure**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_requires_attached_session tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_can_be_enabled_by_policy_file -v
```

Expected: FAIL because strict denials are still silent.

- [ ] **Step 3: Add a diagnostic helper**

In `.codex/hooks/codex_hook_adapter.py`, add:

```python
def session_denial_message(root: Path, session_id: str | None) -> str:
    if session_mode(root) != "strict":
        return ""
    if not session_id:
        return (
            "[planning-with-files] session isolation is strict but hook payload has "
            "no session_id; planning context was not injected."
        )
    return (
        "[planning-with-files] session isolation is strict and session_id is not "
        "attached; planning context was not injected."
    )


def emit_session_denial_if_needed(root: Path, session_id: str | None) -> bool:
    if is_session_attached(root, session_id):
        return False
    message = session_denial_message(root, session_id)
    if message:
        emit_json({"systemMessage": message})
    return True
```

- [ ] **Step 4: Use the helper in all hook entrypoints**

In each hook entrypoint, replace:

```python
    if not adapter.is_session_attached(root, adapter.session_id_from_payload(payload)):
        return
```

with:

```python
    session_id = adapter.session_id_from_payload(payload)
    if adapter.emit_session_denial_if_needed(root, session_id):
        return
```

Apply this to:

- `.codex/hooks/session_start.py`
- `.codex/hooks/user_prompt_submit.py`
- `.codex/hooks/pre_tool_use.py`
- `.codex/hooks/post_tool_use.py`
- `.codex/hooks/stop.py`

- [ ] **Step 5: Run diagnostics tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_requires_attached_session tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_can_be_enabled_by_policy_file -v
```

Expected: PASS.

- [ ] **Step 6: Run all hook tests**

Run:

```powershell
python -m unittest tests.test_hooks -v
```

Expected: all hook tests pass.

---

### Task 4: Add Doctor Session Policy Diagnostics

**Files:**
- Test: `tests/test_plan_doctor.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`

- [ ] **Step 1: Add doctor tests**

Add these tests to `PlanDoctorTests`:

```python
    def test_doctor_reports_workspace_session_mode_when_sessions_dir_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)
            (root / ".planning" / "sessions").mkdir(parents=True)

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session mode: workspace", result.stdout)
            self.assertIn("sessions directory ignored unless PWF_SESSION_MODE=strict", result.stdout)

    def test_doctor_reports_strict_session_mode_from_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)
            (root / ".planning" / "sessions").mkdir(parents=True)

            result = run_plan(root, "doctor", env={"PWF_SESSION_MODE": "strict"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session mode: strict", result.stdout)
            self.assertIn("attached sessions: 0", result.stdout)

    def test_doctor_warns_about_unsupported_session_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(root, "doctor", env={"PWF_SESSION_MODE": "surprise"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session mode: workspace", result.stdout)
            self.assertIn("unsupported PWF_SESSION_MODE=surprise", result.stdout)
```

- [ ] **Step 2: Run doctor tests to verify failure**

Run:

```powershell
python -m unittest tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_workspace_session_mode_when_sessions_dir_exists tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_strict_session_mode_from_env tests.test_plan_doctor.PlanDoctorTests.test_doctor_warns_about_unsupported_session_mode -v
```

Expected: FAIL because doctor does not report session mode yet.

- [ ] **Step 3: Add CLI messages**

In `CLI_MESSAGES["en"]`, add:

```python
        "session_mode": "session mode: {mode}",
        "session_attached_count": "attached sessions: {count}",
        "session_dir_ignored": "session mode: sessions directory ignored unless PWF_SESSION_MODE=strict",
        "session_mode_unsupported": "session mode: warning unsupported PWF_SESSION_MODE={mode}",
```

In `CLI_MESSAGES["zh-CN"]`, add ASCII-stable fallback messages if Chinese encoding is being handled separately in the branch:

```python
        "session_mode": "session mode: {mode}",
        "session_attached_count": "attached sessions: {count}",
        "session_dir_ignored": "session mode: sessions directory ignored unless PWF_SESSION_MODE=strict",
        "session_mode_unsupported": "session mode: warning unsupported PWF_SESSION_MODE={mode}",
```

- [ ] **Step 4: Add doctor helper functions**

In `plan.py`, after `_unsupported_language_warning()`, add:

```python
def _unsupported_session_mode_warning() -> str:
    mode = os.environ.get("PWF_SESSION_MODE", "").strip()
    if mode and mode.lower() not in {"workspace", "strict"}:
        return _message("session_mode_unsupported", mode=mode)
    return ""


def _attached_session_count(root: Path) -> int:
    sessions_dir = root / ".planning" / "sessions"
    if not sessions_dir.is_dir():
        return 0
    return len(list(sessions_dir.glob("*.attached")))


def _session_status_lines(root: Path) -> list[str]:
    mode = planning_state.current_session_mode(root)
    lines = [_message("session_mode", mode=mode)]
    warning = _unsupported_session_mode_warning()
    if warning:
        lines.append(warning)
    sessions_dir = root / ".planning" / "sessions"
    if mode == "strict":
        lines.append(_message("session_attached_count", count=_attached_session_count(root)))
    elif sessions_dir.is_dir():
        lines.append(_message("session_dir_ignored"))
    return lines
```

This step depends on Task 4 Step 5 adding `planning_state.current_session_mode()`.

- [ ] **Step 5: Expose current session mode from planning_state**

In `.codex/hooks/planning_state.py`, do not duplicate policy parsing. Instead import and call the hook adapter helper:

```python
import codex_hook_adapter  # noqa: E402
```

Add:

```python
def current_session_mode(root: Path) -> str:
    return codex_hook_adapter.session_mode(root)
```

If importing the adapter into `planning_state.py` creates a cycle, put `current_session_mode()` directly in `plan.py` by importing `codex_hook_adapter` there. Do not copy policy parsing into two places.

- [ ] **Step 6: Print session status in doctor**

In `doctor(root)`, after the python runtime line and before active plan resolution, add:

```python
    lines.extend(_session_status_lines(root))
```

- [ ] **Step 7: Run doctor tests**

Run:

```powershell
python -m unittest tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_workspace_session_mode_when_sessions_dir_exists tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_strict_session_mode_from_env tests.test_plan_doctor.PlanDoctorTests.test_doctor_warns_about_unsupported_session_mode -v
```

Expected: PASS.

---

### Task 5: Document Session Policy

**Files:**
- Test: `tests/test_project_consistency.py`
- Modify: `README.en.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add documentation consistency test**

Add this test to `ProjectConsistencyTests`:

```python
    def test_readmes_document_session_policy(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")

        for text in (readme_cn, readme_en):
            self.assertIn("PWF_SESSION_MODE=strict", text)
            self.assertIn("session-policy.json", text)
            self.assertIn("workspace", text)
            self.assertIn("strict", text)
```

- [ ] **Step 2: Run documentation test to verify failure**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_readmes_document_session_policy -v
```

Expected: FAIL because docs do not mention session policy yet.

- [ ] **Step 3: Update README.en.md**

After the active plan resolution block in `README.en.md`, add:

```markdown
### Session Policy

By default, hooks use workspace session mode. The current `.planning/.active_plan`
is the source of truth, and planning context is injected even if
`.planning/sessions/` exists. This keeps context recovery reliable after Codex
compaction, resume, and the next user prompt.

Strict per-session isolation is opt-in. Enable it only when multiple Codex
sessions in the same project must not share the active plan:

```powershell
$env:PWF_SESSION_MODE = "strict"
```

or create:

```json
{"mode":"strict"}
```

at `.planning/session-policy.json`.

In strict mode, hook payloads must include an attached `session_id`; otherwise
the hook emits a diagnostic message instead of silently skipping planning
context. Run `/pwf-doctor` to inspect the current session mode.
```

- [ ] **Step 4: Update README.md**

After the active plan resolution block in `README.md`, add:

```markdown
### Session Policy

默认情况下，hook 使用 workspace session mode。当前 `.planning/.active_plan`
是唯一真相；即使 `.planning/sessions/` 目录存在，也会继续注入 planning
上下文。这样 Codex 压缩上下文、resume、以及下一次用户提示后都更稳定。

严格的按会话隔离是显式 opt-in。只有当同一个项目里多个 Codex 会话必须互不共享
active plan 时才开启：

```powershell
$env:PWF_SESSION_MODE = "strict"
```

也可以创建：

```json
{"mode":"strict"}
```

到 `.planning/session-policy.json`。

strict 模式下，hook payload 必须包含已 attach 的 `session_id`；否则 hook 会输出
诊断消息，而不是静默跳过 planning 上下文。运行 `/pwf-doctor` 可以查看当前
session mode。
```

- [ ] **Step 5: Update CHANGELOG.md**

Under `## Unreleased`, add:

```markdown
- Changed session isolation to an explicit policy: workspace mode is now the default, while strict per-session isolation requires `PWF_SESSION_MODE=strict` or `.planning/session-policy.json`.
- Added diagnostics for strict session mode so hooks explain missing or unattached `session_id` instead of silently skipping planning context.
```

- [ ] **Step 6: Run documentation test**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_readmes_document_session_policy -v
```

Expected: PASS.

---

### Task 6: Full Verification and Commit

**Files:**
- All files modified by Tasks 1-5.

- [ ] **Step 1: Run focused hook and doctor suites**

Run:

```powershell
python -m unittest tests.test_hooks tests.test_plan_doctor -v
```

Expected: all tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 3: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected: exit code 0. Windows line-ending warnings are acceptable only if no whitespace errors are reported.

- [ ] **Step 4: Run doctor smoke test**

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Expected output includes:

```text
hooks.json: ok
hook files: ok
python runtime: ok
session mode: workspace
active plan: ok
planning files: ok
```

- [ ] **Step 5: Review git diff**

Run:

```powershell
git diff --stat
git diff -- .codex/hooks/codex_hook_adapter.py .codex/hooks/session_start.py .codex/hooks/user_prompt_submit.py .codex/hooks/pre_tool_use.py .codex/hooks/post_tool_use.py .codex/hooks/stop.py .codex/skills/planning-with-files/scripts/plan.py tests/test_hooks.py tests/test_plan_doctor.py tests/test_project_consistency.py README.en.md README.md CHANGELOG.md
```

Expected: only planned files changed. `.planning/` and `dist/` are not staged.

- [ ] **Step 6: Commit**

Run:

```powershell
git add .codex/hooks/codex_hook_adapter.py .codex/hooks/session_start.py .codex/hooks/user_prompt_submit.py .codex/hooks/pre_tool_use.py .codex/hooks/post_tool_use.py .codex/hooks/stop.py .codex/skills/planning-with-files/scripts/plan.py tests/test_hooks.py tests/test_plan_doctor.py tests/test_project_consistency.py README.en.md README.md CHANGELOG.md docs/SESSION_POLICY_PLAN.md
git commit -m "fix: make session isolation explicit"
```

Expected: commit succeeds.

- [ ] **Step 7: Push**

Run:

```powershell
git push origin main
```

Expected: `main -> main` pushed successfully.
