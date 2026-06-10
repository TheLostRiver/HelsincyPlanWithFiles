# Session Context Profile Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-scoped context profile shortcut commands and optional context injection notices for PWF.

**Architecture:** Keep the existing environment-variable context profile system as the highest-priority override. Add a small session-context JSON file under `.planning/session-context/<session-key>.json`, resolve it from `planning_state.py` when no env profile overrides it, expose `plan.py context ...` for CLI control, and add thin `/pwf-context-*` slash wrappers. Hook notice rendering stays in `planning_state.py` so `UserPromptSubmit` and `SessionStart` use one implementation.

**Tech Stack:** Python standard library, project-local Codex hooks and skills, `unittest`, Markdown docs.

---

## File Structure

Modify:

- `.codex/hooks/planning_state.py`
  - Add session context storage path helpers.
  - Add context profile and notice resolution with source metadata.
  - Add hook injection notice rendering and estimated size metadata.
- `.codex/skills/planning-with-files/scripts/plan.py`
  - Add `context` subcommand.
  - Add session-context write/clear/status helpers.
  - Extend `status` and `doctor` output.
- `tests/test_hooks.py`
  - Add hook-level session profile and notice coverage.
- `tests/test_plan_cli.py`
  - Add CLI context command coverage.
- `tests/test_plan_doctor.py`
  - Add doctor diagnostics coverage.
- `tests/test_pwf_commands.py`
  - Add slash wrapper coverage.
- `tests/test_project_consistency.py`
  - Add documentation consistency checks for new commands.
- `README.md`
- `README.en.md`
- `docs/FAQ.md`
- `docs/USER_GUIDE.zh-CN.md`
- `CHANGELOG.md`

Create:

- `.codex/skills/pwf-context-expanded/SKILL.md`
- `.codex/skills/pwf-context-deep/SKILL.md`
- `.codex/skills/pwf-context-default/SKILL.md`
- `.codex/skills/pwf-context-lean/SKILL.md`
- `.codex/skills/pwf-context-status/SKILL.md`
- `.codex/skills/pwf-context-notice-on/SKILL.md`
- `.codex/skills/pwf-context-notice-off/SKILL.md`
- `.codex/skills/pwf-context-notice-auto/SKILL.md`

Do not create workspace-level context configuration in this feature.

---

## Task 1: Session Context Resolution In Hooks

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing tests for session profile resolution**

Append these tests to `ContextLimitResolverTests` in `tests/test_hooks.py`.

```python
    def test_context_limits_use_session_profile_when_env_profile_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = PLANNING_STATE.session_key("session-a")
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "session_id": "session-a",
                        "profile": "expanded",
                        "notice": "auto",
                        "created_at": "2026-06-10T00:00:00Z",
                        "updated_at": "2026-06-10T00:00:00Z",
                        "source": "test",
                    }
                ),
                encoding="utf-8",
            )

            limits = PLANNING_STATE.context_limits({}, root=root, session_id="session-a")
            source = PLANNING_STATE.context_settings_source({}, root=root, session_id="session-a")

            self.assertEqual(limits.profile, "expanded")
            self.assertEqual(limits.progress_recent_records, 20)
            self.assertEqual(source.profile_source, "session")
            self.assertEqual(source.session_profile, "expanded")

    def test_env_context_profile_overrides_session_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = PLANNING_STATE.session_key("session-a")
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "auto"}),
                encoding="utf-8",
            )

            limits = PLANNING_STATE.context_limits(
                {"PWF_CONTEXT_PROFILE": "deep"},
                root=root,
                session_id="session-a",
            )
            source = PLANNING_STATE.context_settings_source(
                {"PWF_CONTEXT_PROFILE": "deep"},
                root=root,
                session_id="session-a",
            )

            self.assertEqual(limits.profile, "deep")
            self.assertEqual(limits.progress_recent_records, 40)
            self.assertEqual(source.profile_source, "env PWF_CONTEXT_PROFILE")
            self.assertEqual(source.session_profile, "expanded")
            self.assertTrue(source.session_profile_overridden)

    def test_malformed_session_context_falls_back_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = PLANNING_STATE.session_key("session-a")
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text("{not json", encoding="utf-8")

            limits = PLANNING_STATE.context_limits({}, root=root, session_id="session-a")
            source = PLANNING_STATE.context_settings_source({}, root=root, session_id="session-a")

            self.assertEqual(limits.profile, "default")
            self.assertEqual(source.profile_source, "default")
            self.assertTrue(any("session-context" in warning for warning in source.warnings))
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m unittest tests.test_hooks.ContextLimitResolverTests -v
```

Expected: failure because `context_limits()` does not accept `root` or `session_id`, and `context_settings_source()` does not exist.

- [ ] **Step 3: Add session context dataclasses and helpers**

In `.codex/hooks/planning_state.py`, add near `ContextLimits`:

```python
SESSION_CONTEXT_PROFILES = {"lean", "default", "expanded", "deep"}
CONTEXT_NOTICE_MODES = {"auto", "on", "off"}


@dataclass(frozen=True)
class SessionContextSettings:
    session_key: str
    profile: str | None
    notice: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextSettingsSource:
    profile: str
    profile_source: str
    session_profile: str | None
    session_profile_overridden: bool
    notice: str
    notice_source: str
    session_notice: str | None
    session_notice_overridden: bool
    warnings: tuple[str, ...] = ()
```

Add path and reader helpers near existing session path helpers:

```python
def session_context_path(root: Path, session_id: str) -> Path:
    return root / ".planning" / "session-context" / f"{session_key(session_id)}.json"


def read_session_context(root: Path, session_id: str | None) -> SessionContextSettings | None:
    if not session_id:
        return None
    key = session_key(session_id)
    path = session_context_path(root, session_id)
    if not path.is_file():
        return None
    warnings: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return SessionContextSettings(key, None, None, (f"[warn] invalid session-context file: {path}",))
    if not isinstance(payload, dict):
        return SessionContextSettings(key, None, None, (f"[warn] invalid session-context file: {path}",))
    profile = payload.get("profile")
    notice = payload.get("notice")
    if not isinstance(profile, str) or profile not in SESSION_CONTEXT_PROFILES:
        profile = None
        warnings.append(f"[warn] invalid session context profile in {path}")
    if notice is not None and (not isinstance(notice, str) or notice not in CONTEXT_NOTICE_MODES):
        notice = None
        warnings.append(f"[warn] invalid session context notice in {path}")
    return SessionContextSettings(key, profile, notice if isinstance(notice, str) else None, tuple(warnings))
```

- [ ] **Step 4: Update profile resolver signatures**

Change `_resolved_context_profile()`, `current_context_profile()`, `context_limits()`, and `context_profile_warnings()` signatures so they can accept `root` and `session_id`.

Implement source-aware helpers:

```python
def context_settings_source(
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> ContextSettingsSource:
    source = env if env is not None else os.environ
    session_settings = read_session_context(root, session_id) if root is not None else None
    warnings = list(session_settings.warnings if session_settings else ())

    raw_profile = source.get("PWF_CONTEXT_PROFILE", "")
    normalized_profile = raw_profile.strip(" \t\r\n").lower()
    if normalized_profile:
        if normalized_profile in CONTEXT_PROFILES:
            profile = normalized_profile
            profile_source = "env PWF_CONTEXT_PROFILE"
        else:
            profile = "default"
            profile_source = "default"
            warnings.append(f'[warn] invalid PWF_CONTEXT_PROFILE="{safe_env_value(raw_profile)}"; using default')
    elif session_settings and session_settings.profile:
        profile = session_settings.profile
        profile_source = "session"
    else:
        profile = "default"
        profile_source = "default"

    raw_notice = source.get("PWF_CONTEXT_NOTICE", "")
    normalized_notice = raw_notice.strip(" \t\r\n").lower()
    if normalized_notice:
        if normalized_notice in CONTEXT_NOTICE_MODES:
            notice = normalized_notice
            notice_source = "env PWF_CONTEXT_NOTICE"
        else:
            notice = "auto"
            notice_source = "default"
            warnings.append(f'[warn] invalid PWF_CONTEXT_NOTICE="{safe_env_value(raw_notice)}"; using auto')
    elif session_settings and session_settings.notice:
        notice = session_settings.notice
        notice_source = "session"
    else:
        notice = "auto"
        notice_source = "default"

    return ContextSettingsSource(
        profile=profile,
        profile_source=profile_source,
        session_profile=session_settings.profile if session_settings else None,
        session_profile_overridden=bool(session_settings and session_settings.profile and profile_source.startswith("env ")),
        notice=notice,
        notice_source=notice_source,
        session_notice=session_settings.notice if session_settings else None,
        session_notice_overridden=bool(session_settings and session_settings.notice and notice_source.startswith("env ")),
        warnings=tuple(warnings),
    )
```

Then make `context_limits()` call `context_settings_source()` and keep numeric override behavior unchanged:

```python
def context_limits(
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> ContextLimits:
    settings = context_settings_source(env, root=root, session_id=session_id)
    profile = settings.profile
    warnings = list(settings.warnings)
    ...
```

- [ ] **Step 5: Wire hook rendering to pass root/session**

In `render_pre_tool_context()` and `render_prompt_context()`, change:

```python
limits = context_limits()
```

to:

```python
limits = context_limits(root=root, session_id=session_id)
```

This makes hooks use session profile files.

- [ ] **Step 6: Run tests for Task 1**

Run:

```powershell
python -m unittest tests.test_hooks.ContextLimitResolverTests -v
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_expanded_profile_includes_complete_recent_progress_records tests.test_hooks.HookTests.test_user_prompt_submit_deep_profile_uses_larger_recent_record_count -v
```

Expected: all pass. Existing environment-variable tests must still pass.

- [ ] **Step 7: Commit Task 1**

```powershell
git add .codex/hooks/planning_state.py tests/test_hooks.py
git commit -m "feat: resolve session context profiles"
```

---

## Task 2: CLI Context Commands

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Add tests to `PlanCliTests` in `tests/test_plan_cli.py`.

```python
    def test_context_set_expanded_writes_current_session_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_plan(root, "context", "set", "expanded", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            path = root / ".planning" / "session-context" / f"{key}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["profile"], "expanded")
            self.assertEqual(payload["notice"], "auto")
            self.assertIn("context profile set: expanded", result.stdout)

    def test_context_set_without_session_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_plan(root, "context", "set", "expanded")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("session id: unavailable", result.stdout + result.stderr)
            self.assertFalse((root / ".planning" / "session-context").exists())

    def test_context_status_reports_session_profile_and_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_result = run_plan(root, "context", "set", "expanded", env={"PWF_SESSION_ID": "session-a"})
            self.assertEqual(set_result.returncode, 0, set_result.stderr)

            status_result = run_plan(root, "context", "status", env={"PWF_SESSION_ID": "session-a"})
            self.assertIn("profile: expanded", status_result.stdout)
            self.assertIn("source: session", status_result.stdout)
            self.assertIn("notice: auto", status_result.stdout)
            self.assertIn("progress mode: record-aware 20 records", status_result.stdout)

            override_result = run_plan(
                root,
                "context",
                "status",
                env={"PWF_SESSION_ID": "session-a", "PWF_CONTEXT_PROFILE": "deep"},
            )
            self.assertIn("profile: deep", override_result.stdout)
            self.assertIn("source: env PWF_CONTEXT_PROFILE", override_result.stdout)
            self.assertIn("session profile: expanded, currently overridden", override_result.stdout)

    def test_context_notice_commands_update_current_session_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_result = run_plan(root, "context", "set", "expanded", env={"PWF_SESSION_ID": "session-a"})
            notice_result = run_plan(root, "context", "notice", "off", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(set_result.returncode, 0, set_result.stderr)
            self.assertEqual(notice_result.returncode, 0, notice_result.stderr)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            payload = json.loads((root / ".planning" / "session-context" / f"{key}.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["profile"], "expanded")
            self.assertEqual(payload["notice"], "off")

    def test_context_clear_removes_current_session_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_result = run_plan(root, "context", "set", "expanded", env={"PWF_SESSION_ID": "session-a"})
            clear_result = run_plan(root, "context", "clear", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(set_result.returncode, 0, set_result.stderr)
            self.assertEqual(clear_result.returncode, 0, clear_result.stderr)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            self.assertFalse((root / ".planning" / "session-context" / f"{key}.json").exists())
```

- [ ] **Step 2: Run failing CLI tests**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_context_set_expanded_writes_current_session_context tests.test_plan_cli.PlanCliTests.test_context_set_without_session_id_is_rejected tests.test_plan_cli.PlanCliTests.test_context_status_reports_session_profile_and_env_override tests.test_plan_cli.PlanCliTests.test_context_notice_commands_update_current_session_context tests.test_plan_cli.PlanCliTests.test_context_clear_removes_current_session_context -v
```

Expected: fail because `context` subcommand does not exist.

- [ ] **Step 3: Add CLI messages**

In `CLI_MESSAGES["en"]`, add:

```python
"help_context": "Manage current-session context profile",
"context_profile_set": "context profile set: {profile}",
"context_notice_set": "context notice set: {notice}",
"context_cleared": "context settings cleared: {key}",
"context_missing_session": "session id: unavailable; context commands only affect the current session",
"context_invalid_profile": "unsupported context profile: {profile}",
"context_invalid_notice": "unsupported context notice mode: {notice}",
```

In `CLI_MESSAGES["zh-CN"]`, add:

```python
"help_context": "管理当前会话的 context profile",
"context_profile_set": "context profile set: {profile}",
"context_notice_set": "context notice set: {notice}",
"context_cleared": "context settings cleared: {key}",
"context_missing_session": "session id: 不可用；context 命令只影响当前会话",
"context_invalid_profile": "unsupported context profile: {profile}",
"context_invalid_notice": "unsupported context notice mode: {notice}",
```

Keep key phrases in English where tests and scripts benefit from stable ASCII.

- [ ] **Step 4: Add session-context payload helpers**

Near existing session binding helpers in `plan.py`, add:

```python
def _session_context_path(root: Path, session_id: str) -> Path:
    return planning_state.session_context_path(root, session_id)


def _read_session_context_payload(root: Path, session_id: str) -> dict[str, object]:
    path = _session_context_path(root, session_id)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_session_context(root: Path, session_id: str, *, profile: str | None = None, notice: str | None = None) -> str:
    key = planning_state.session_key(session_id)
    context_dir = root / ".planning" / "session-context"
    context_dir.mkdir(parents=True, exist_ok=True)
    existing = _read_session_context_payload(root, session_id)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "version": 1,
        "session_id": session_id,
        "profile": profile if profile is not None else existing.get("profile", "default"),
        "notice": notice if notice is not None else existing.get("notice", "auto"),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "source": "plan.py context",
    }
    target = context_dir / f"{key}.json"
    tmp = context_dir / f"{key}.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(target)
    return key


def _clear_session_context(root: Path, session_id: str) -> str:
    key = planning_state.session_key(session_id)
    path = _session_context_path(root, session_id)
    if path.exists():
        path.unlink()
    return key
```

- [ ] **Step 5: Add context status formatter and command handler**

Add:

```python
def _context_source_lines(root: Path, session_id: str | None) -> list[str]:
    limits = planning_state.context_limits(root=root, session_id=session_id)
    source = planning_state.context_settings_source(root=root, session_id=session_id)
    lines = [
        "session context:",
        f"  profile: {limits.profile}",
        f"  source: {source.profile_source}",
    ]
    if source.session_profile_overridden and source.session_profile:
        lines.append(f"  session profile: {source.session_profile}, currently overridden")
    elif source.session_profile:
        lines.append(f"  session profile: {source.session_profile}")
    else:
        lines.append("  session profile: none")
    lines.extend(
        [
            f"  notice: {source.notice}",
            f"  notice source: {source.notice_source}",
            f"  progress mode: {'record-aware ' + str(limits.progress_recent_records) + ' records' if limits.progress_recent_records > 0 else 'line tail ' + str(limits.progress_tail_lines)}",
            f"  plan: head {limits.plan_head_lines} tail {limits.plan_tail_lines}",
            f"  findings: {_context_findings_text(limits)}",
            f"  max: {limits.context_max_chars} chars",
        ]
    )
    lines.extend(source.warnings)
    return lines


def context(root: Path, action: str, value: str | None = None) -> int:
    session_id = _current_session_id()
    if action == "status":
        print("\n".join(_context_source_lines(root, session_id)))
        return 0
    if not session_id:
        print(_message("context_missing_session"))
        return 1
    if action == "set":
        profile = (value or "").lower()
        if profile not in planning_state.SESSION_CONTEXT_PROFILES:
            print(_message("context_invalid_profile", profile=profile))
            return 1
        _write_session_context(root, session_id, profile=profile)
        print(_message("context_profile_set", profile=profile))
        print("\n".join(_context_source_lines(root, session_id)))
        return 0
    if action == "notice":
        notice = (value or "").lower()
        if notice not in planning_state.CONTEXT_NOTICE_MODES:
            print(_message("context_invalid_notice", notice=notice))
            return 1
        _write_session_context(root, session_id, notice=notice)
        print(_message("context_notice_set", notice=notice))
        print("\n".join(_context_source_lines(root, session_id)))
        return 0
    if action == "clear":
        key = _clear_session_context(root, session_id)
        print(_message("context_cleared", key=key))
        return 0
    raise ValueError(f"unsupported context action: {action}")
```

- [ ] **Step 6: Wire argparse**

In `main()`, add:

```python
    context_parser = subparsers.add_parser("context", help=_help("context"))
    context_subparsers = context_parser.add_subparsers(dest="context_command", required=True)
    context_subparsers.add_parser("status")
    context_set = context_subparsers.add_parser("set")
    context_set.add_argument("profile")
    context_notice = context_subparsers.add_parser("notice")
    context_notice.add_argument("mode")
    context_subparsers.add_parser("clear")
```

In command dispatch:

```python
    if args.command == "context":
        if args.context_command == "status":
            return context(root, "status")
        if args.context_command == "set":
            return context(root, "set", args.profile)
        if args.context_command == "notice":
            return context(root, "notice", args.mode)
        if args.context_command == "clear":
            return context(root, "clear")
```

- [ ] **Step 7: Run CLI tests**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_context_set_expanded_writes_current_session_context tests.test_plan_cli.PlanCliTests.test_context_set_without_session_id_is_rejected tests.test_plan_cli.PlanCliTests.test_context_status_reports_session_profile_and_env_override tests.test_plan_cli.PlanCliTests.test_context_notice_commands_update_current_session_context tests.test_plan_cli.PlanCliTests.test_context_clear_removes_current_session_context -v
```

Expected: pass.

- [ ] **Step 8: Commit Task 2**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_cli.py
git commit -m "feat: add session context CLI commands"
```

---

## Task 3: Injection Notice Rendering

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing hook notice tests**

Add tests to `HookTests` in `tests/test_hooks.py`.

```python
    def test_user_prompt_submit_session_expanded_profile_shows_auto_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            key = PLANNING_STATE.session_key("session-a")
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "auto"}),
                encoding="utf-8",
            )
            (root / "progress.md").write_text("# Progress Log\n" + "\n".join(auto_records(25)), encoding="utf-8")

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Injected current-session planning context", context)
            self.assertIn("profile=expanded", context)
            self.assertIn("progress=20 records", context)
            self.assertRegex(context, r"approx [0-9.]+k chars \\(~[0-9.]+k tokens\\)")

    def test_user_prompt_submit_default_profile_auto_notice_stays_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("Injected current-session planning context", context)

    def test_user_prompt_submit_notice_off_suppresses_expanded_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            key = PLANNING_STATE.session_key("session-a")
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "off"}),
                encoding="utf-8",
            )

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("Injected current-session planning context", context)

    def test_user_prompt_submit_notice_on_shows_default_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            key = PLANNING_STATE.session_key("session-a")
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "default", "notice": "on"}),
                encoding="utf-8",
            )

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Injected current-session planning context", context)
            self.assertIn("profile=default", context)
```

- [ ] **Step 2: Run failing notice tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_session_expanded_profile_shows_auto_notice tests.test_hooks.HookTests.test_user_prompt_submit_default_profile_auto_notice_stays_quiet tests.test_hooks.HookTests.test_user_prompt_submit_notice_off_suppresses_expanded_notice tests.test_hooks.HookTests.test_user_prompt_submit_notice_on_shows_default_notice -v
```

Expected: fail because notice rendering does not exist.

- [ ] **Step 3: Add notice messages**

In `MESSAGES["en"]`, add:

```python
"context_injection_notice": (
    "[planning-with-files] Injected current-session planning context: "
    "profile={profile}, progress={progress}, approx {chars} chars (~{tokens} tokens)."
),
```

In `MESSAGES["zh-CN"]`, add:

```python
"context_injection_notice": (
    "[planning-with-files] 已自动注入当前会话的任务上下文："
    "profile={profile}，progress={progress}，约 {chars} chars（估算 {tokens} tokens）。"
),
```

- [ ] **Step 4: Add estimate helpers**

In `planning_state.py`, add:

```python
def _format_approx_count(value: int) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def _estimated_tokens(chars: int) -> int:
    return max(1, math.ceil(chars / 4))


def _progress_notice_text(limits: ContextLimits) -> str:
    if limits.progress_recent_records > 0:
        return f"{limits.progress_recent_records} records"
    return f"tail {limits.progress_tail_lines} lines"


def _should_show_context_notice(settings: ContextSettingsSource, limits: ContextLimits, *, event: str) -> bool:
    if settings.notice == "off":
        return False
    if settings.notice == "on":
        return True
    return limits.profile in {"expanded", "deep"} or event == "SessionStart"
```

Remember to import `math`.

- [ ] **Step 5: Add render function**

Add:

```python
def _append_context_notice(
    rendered: str,
    *,
    settings: ContextSettingsSource,
    limits: ContextLimits,
    event: str,
) -> str:
    if not _should_show_context_notice(settings, limits, event=event):
        return rendered
    chars = len(rendered)
    tokens = _estimated_tokens(chars)
    notice = message(
        "context_injection_notice",
        profile=limits.profile,
        progress=_progress_notice_text(limits),
        chars=_format_approx_count(chars),
        tokens=_format_approx_count(tokens),
    )
    return f"{notice}\n{rendered}"
```

- [ ] **Step 6: Pass hook event into render_prompt_context**

Change signature:

```python
def render_prompt_context(root: Path, session_id: str | None = None, event: str = "UserPromptSubmit") -> str:
```

Inside, compute:

```python
settings = context_settings_source(root=root, session_id=session_id)
limits = context_limits(root=root, session_id=session_id)
...
rendered = apply_total_context_budget("\n".join(parts).rstrip(), limits)
return _append_context_notice(rendered, settings=settings, limits=limits, event=event)
```

Update `session_start.py` to call:

```python
planning_state.render_prompt_context(root, session_id=session_id, event="SessionStart")
```

Keep `user_prompt_submit.py` compatible; it may omit `event`.

- [ ] **Step 7: Ensure total budget still applies**

If a notice can push context over the budget, call budget once more:

```python
rendered = _append_context_notice(rendered, settings=settings, limits=limits, event=event)
return apply_total_context_budget(rendered, limits)
```

This keeps oversized contexts bounded.

- [ ] **Step 8: Run notice tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_session_expanded_profile_shows_auto_notice tests.test_hooks.HookTests.test_user_prompt_submit_default_profile_auto_notice_stays_quiet tests.test_hooks.HookTests.test_user_prompt_submit_notice_off_suppresses_expanded_notice tests.test_hooks.HookTests.test_user_prompt_submit_notice_on_shows_default_notice -v
```

Expected: pass.

- [ ] **Step 9: Run existing hook context tests**

Run:

```powershell
python -m unittest tests.test_hooks -v
```

Expected: pass. If existing default-profile tests fail because `SessionStart` now shows auto notice, update only the expected context for SessionStart-specific tests.

- [ ] **Step 10: Commit Task 3**

```powershell
git add .codex/hooks/planning_state.py .codex/hooks/session_start.py tests/test_hooks.py
git commit -m "feat: show optional context injection notices"
```

---

## Task 4: Status And Doctor Diagnostics

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`, `tests/test_plan_doctor.py`

- [ ] **Step 1: Add failing doctor tests**

Add to `tests/test_plan_doctor.py`.

```python
    def test_doctor_reports_session_context_profile_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "auto"}),
                encoding="utf-8",
            )

            result = run_plan(root, "doctor", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("context profile: expanded", result.stdout)
            self.assertIn("context profile source: session", result.stdout)
            self.assertIn("context notice: auto", result.stdout)
            self.assertIn("context progress mode: record-aware 20 records", result.stdout)

    def test_doctor_reports_env_override_for_session_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "auto"}),
                encoding="utf-8",
            )

            result = run_plan(root, "doctor", env={"PWF_SESSION_ID": "session-a", "PWF_CONTEXT_PROFILE": "deep"})

            self.assertIn("context profile: deep", result.stdout)
            self.assertIn("context profile source: env PWF_CONTEXT_PROFILE", result.stdout)
            self.assertIn("context session profile: expanded overridden", result.stdout)
```

- [ ] **Step 2: Update existing status expectations**

In `tests/test_plan_cli.py`, add assertions to `test_status_reports_expanded_context_profile_summary`:

```python
            self.assertIn("context source: env PWF_CONTEXT_PROFILE", result.stdout)
            self.assertIn("context notice: auto", result.stdout)
```

If status is kept as one compact line plus extra diagnostic lines, assert both.

- [ ] **Step 3: Run failing diagnostics tests**

Run:

```powershell
python -m unittest tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_session_context_profile_source tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_env_override_for_session_context tests.test_plan_cli.PlanCliTests.test_status_reports_expanded_context_profile_summary -v
```

Expected: fail until status/doctor output is extended.

- [ ] **Step 4: Extend `_context_status_line()`**

Change `_context_status_line()` to accept `root` and `session_id`:

```python
def _context_status_lines(root: Path, session_id: str | None) -> list[str]:
    limits = planning_state.context_limits(root=root, session_id=session_id)
    source = planning_state.context_settings_source(root=root, session_id=session_id)
    lines = [
        (
            f"context: profile={limits.profile}, "
            f"plan=head {limits.plan_head_lines} tail {limits.plan_tail_lines}, "
            f"progress={_context_progress_text(limits)}, "
            f"findings={_context_findings_text(limits)}, "
            f"max={limits.context_max_chars} chars"
        ),
        f"context source: {source.profile_source}",
        f"context notice: {source.notice}",
    ]
    if source.session_profile_overridden and source.session_profile:
        lines.append(f"context session profile: {source.session_profile} overridden")
    lines.extend(source.warnings)
    return lines
```

In `status()`, replace:

```python
print(_context_status_line())
```

with:

```python
for line in _context_status_lines(root, session_id):
    print(line)
```

- [ ] **Step 5: Extend `_context_doctor_lines()`**

Change signature to:

```python
def _context_doctor_lines(root: Path, session_id: str | None) -> list[str]:
```

Use:

```python
limits = planning_state.context_limits(root=root, session_id=session_id)
source = planning_state.context_settings_source(root=root, session_id=session_id)
```

Add lines:

```python
f"context profile source: {source.profile_source}",
f"context notice: {source.notice}",
f"context notice source: {source.notice_source}",
```

If overridden:

```python
if source.session_profile_overridden and source.session_profile:
    lines.append(f"context session profile: {source.session_profile} overridden")
if source.session_notice_overridden and source.session_notice:
    lines.append(f"context session notice: {source.session_notice} overridden")
```

In `doctor()`, compute `session_id = _current_session_id()` before context lines and call:

```python
lines.extend(_context_doctor_lines(root, session_id))
```

- [ ] **Step 6: Run diagnostics tests**

Run:

```powershell
python -m unittest tests.test_plan_doctor tests.test_plan_cli.PlanCliTests.test_status_reports_active_plan_summary tests.test_plan_cli.PlanCliTests.test_status_reports_expanded_context_profile_summary -v
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_cli.py tests/test_plan_doctor.py
git commit -m "feat: report context profile sources"
```

---

## Task 5: Slash Command Wrappers

**Files:**
- Create: `.codex/skills/pwf-context-expanded/SKILL.md`
- Create: `.codex/skills/pwf-context-deep/SKILL.md`
- Create: `.codex/skills/pwf-context-default/SKILL.md`
- Create: `.codex/skills/pwf-context-lean/SKILL.md`
- Create: `.codex/skills/pwf-context-status/SKILL.md`
- Create: `.codex/skills/pwf-context-notice-on/SKILL.md`
- Create: `.codex/skills/pwf-context-notice-off/SKILL.md`
- Create: `.codex/skills/pwf-context-notice-auto/SKILL.md`
- Modify: `tests/test_pwf_commands.py`

- [ ] **Step 1: Add failing wrapper tests**

Update `COMMANDS` in `tests/test_pwf_commands.py`:

```python
COMMANDS = {
    "pwf-doctor": "doctor",
    "pwf-init": "init",
    "pwf-status": "status",
    "pwf-switch": "switch",
    "pwf-tasks": "tasks",
    "pwf-use": "use",
    "pwf-attest": "attest",
    "pwf-capture": "capture",
    "pwf-compact": "compact",
    "pwf-context-expanded": "context set expanded",
    "pwf-context-deep": "context set deep",
    "pwf-context-default": "context set default",
    "pwf-context-lean": "context set lean",
    "pwf-context-status": "context status",
    "pwf-context-notice-on": "context notice on",
    "pwf-context-notice-off": "context notice off",
    "pwf-context-notice-auto": "context notice auto",
}
```

Change `test_pwf_skill_wrappers_route_to_plan_cli()` to handle multi-word routes:

```python
                for part in subcommand.split():
                    self.assertIn(part, text)
```

- [ ] **Step 2: Run failing wrapper tests**

Run:

```powershell
python -m unittest tests.test_pwf_commands -v
```

Expected: fail because new wrapper directories do not exist.

- [ ] **Step 3: Create preset wrappers**

Create `.codex/skills/pwf-context-expanded/SKILL.md`:

```markdown
---
name: pwf-context-expanded
description: Switch the current session to expanded PWF context injection. Invoke with /pwf-context-expanded.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-context-expanded

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py context set expanded
```

中文模式：如果用户希望中文输出，先设置 `PWF_LANG=zh-CN`，再运行相同命令。

This changes only the current session context profile. It does not change other sessions or workspace active plan.
```

Create the same shape for:

- `pwf-context-deep`: `plan.py context set deep`
- `pwf-context-default`: `plan.py context set default`
- `pwf-context-lean`: `plan.py context set lean`

For `deep`, add:

```markdown
Use this for deliberate recovery after heavy context compaction. It injects more context than expanded mode.
```

- [ ] **Step 4: Create status and notice wrappers**

Create `.codex/skills/pwf-context-status/SKILL.md`:

```markdown
---
name: pwf-context-status
description: Show the current session PWF context profile and notice settings. Invoke with /pwf-context-status.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-context-status

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py context status
```

中文模式：如果用户希望中文输出，先设置 `PWF_LANG=zh-CN`，再运行相同命令。

Show the effective profile, source, notice mode, progress mode, findings state, and context budget for the current session.
```

Create notice wrappers:

- `pwf-context-notice-on`: `plan.py context notice on`
- `pwf-context-notice-off`: `plan.py context notice off`
- `pwf-context-notice-auto`: `plan.py context notice auto`

Each wrapper must mention that notice settings are current-session scoped.

- [ ] **Step 5: Run wrapper tests**

Run:

```powershell
python -m unittest tests.test_pwf_commands -v
```

Expected: pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add .codex/skills/pwf-context-expanded .codex/skills/pwf-context-deep .codex/skills/pwf-context-default .codex/skills/pwf-context-lean .codex/skills/pwf-context-status .codex/skills/pwf-context-notice-on .codex/skills/pwf-context-notice-off .codex/skills/pwf-context-notice-auto tests/test_pwf_commands.py
git commit -m "feat: add context profile slash commands"
```

---

## Task 6: Documentation And Consistency

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `docs/USER_GUIDE.zh-CN.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_project_consistency.py`

- [ ] **Step 1: Add failing consistency checks**

In `tests/test_project_consistency.py`, extend or add a test:

```python
    def test_docs_document_session_context_profile_commands(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        user_guide = read_text("docs/USER_GUIDE.zh-CN.md")
        changelog = read_text("CHANGELOG.md")
        combined = "\n".join([readme_cn, readme_en, faq, user_guide, changelog])

        for phrase in (
            "/pwf-context-expanded",
            "/pwf-context-deep",
            "/pwf-context-status",
            "/pwf-context-notice-auto",
            "current session",
            "当前会话",
            "record-aware",
            "PWF_CONTEXT_PROFILE",
        ):
            self.assertIn(phrase, combined)
```

- [ ] **Step 2: Run failing consistency test**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_session_context_profile_commands -v
```

Expected: fail until docs are updated.

- [ ] **Step 3: Update README command tables**

In `README.md` command table, add rows:

```markdown
| `/pwf-context-expanded` | 当前会话切到大型任务上下文模式 | `plan.py context set expanded` |
| `/pwf-context-deep` | 当前会话切到深度恢复上下文模式 | `plan.py context set deep` |
| `/pwf-context-default` | 当前会话恢复默认上下文模式 | `plan.py context set default` |
| `/pwf-context-lean` | 当前会话切到省上下文模式 | `plan.py context set lean` |
| `/pwf-context-status` | 查看当前会话上下文设置和来源 | `plan.py context status` |
| `/pwf-context-notice-auto` | 自动提示上下文注入情况 | `plan.py context notice auto` |
| `/pwf-context-notice-on` | 每次注入上下文都提示 | `plan.py context notice on` |
| `/pwf-context-notice-off` | 关闭上下文注入提示 | `plan.py context notice off` |
```

In `README.en.md`, add equivalent English rows.

- [ ] **Step 4: Update context profile docs**

Replace the environment-variable-only guidance in README and FAQ with slash command first:

```markdown
大型任务优先使用：

```text
/pwf-context-expanded
```

上下文压缩或 resume 后需要更强恢复时使用：

```text
/pwf-context-deep
```

这些命令只影响当前会话。环境变量 `PWF_CONTEXT_PROFILE` 仍然保留，并且优先级高于会话设置。
```

Keep the environment variable examples in an advanced note.

- [ ] **Step 5: Update user guide**

In `docs/USER_GUIDE.zh-CN.md`, add a plain-language section:

```markdown
### 任务很长时，让工具多带一点上下文

如果任务已经做了很久，或者 Codex 上下文压缩后你担心它忘了前面的步骤，可以在当前会话运行：

```text
/pwf-context-expanded
```

如果还是恢复困难，再运行：

```text
/pwf-context-deep
```

这些命令只影响当前会话，不会改到同项目其他 Codex 会话。
```

- [ ] **Step 6: Update changelog**

Under `## Unreleased`, add:

```markdown
- 中文：新增会话级 context profile 快捷命令，可用 `/pwf-context-expanded`、`/pwf-context-deep`、`/pwf-context-default`、`/pwf-context-lean` 和 `/pwf-context-status` 管理当前会话上下文注入强度。
- 中文：新增 context injection notice 开关：`/pwf-context-notice-auto`、`/pwf-context-notice-on`、`/pwf-context-notice-off`，可提示已自动注入任务上下文及大致占用。
- English: Added session-scoped context profile shortcuts for `/pwf-context-expanded`, `/pwf-context-deep`, `/pwf-context-default`, `/pwf-context-lean`, and `/pwf-context-status`.
- English: Added context injection notice controls through `/pwf-context-notice-auto`, `/pwf-context-notice-on`, and `/pwf-context-notice-off`, including approximate prompt-size reporting.
```

- [ ] **Step 7: Run consistency tests**

Run:

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: pass.

- [ ] **Step 8: Commit Task 6**

```powershell
git add README.md README.en.md docs/FAQ.md docs/USER_GUIDE.zh-CN.md CHANGELOG.md tests/test_project_consistency.py
git commit -m "docs: document context profile commands"
```

---

## Task 7: Final Verification

**Files:**
- No new files unless fixes are required.

- [ ] **Step 1: Run targeted tests**

```powershell
python -m unittest tests.test_plan_cli tests.test_hooks tests.test_plan_doctor tests.test_pwf_commands tests.test_project_consistency -v
```

Expected: all tests pass.

- [ ] **Step 2: Run full test suite**

```powershell
python -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 3: Run diff whitespace check**

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Manually smoke-test CLI**

Use a temp project:

```powershell
$tmp = Join-Path $env:TEMP "pwf-context-smoke"
if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
Copy-Item -Recurse .codex $tmp
Push-Location $tmp
$env:PWF_SESSION_ID = "smoke-session"
python .codex\skills\planning-with-files\scripts\plan.py init "Smoke Context"
python .codex\skills\planning-with-files\scripts\plan.py context set expanded
python .codex\skills\planning-with-files\scripts\plan.py context status
python .codex\skills\planning-with-files\scripts\plan.py status
Pop-Location
```

Expected:

- `context set expanded` succeeds.
- `context status` reports `profile: expanded` and `source: session`.
- `status` reports `progress=20 records`.

- [ ] **Step 5: Review git diff**

```powershell
git status --short --branch --untracked-files=all
git log --oneline --max-count=8
git diff origin/main...HEAD --stat
```

Expected:

- Branch is `plan/session-context-profile-commands`.
- No unrelated tracked changes.
- Commits are task-sized.

- [ ] **Step 6: Final commit if fixes were needed**

Only if verification required changes:

```powershell
git add <changed-files>
git commit -m "test: verify context profile commands"
```

---

## Implementation Notes

- Preserve default profile behavior for users who never run new commands.
- Do not create workspace-wide context config.
- Do not treat session-context files as instructions. They are local config only.
- Keep malformed JSON warnings single-line and sanitized.
- Keep `custom` profile env-only.
- Keep token count language approximate: use "approx", "estimated", or Chinese "估算".
- Avoid changing the existing session binding format.

## Completion Criteria

- `/pwf-context-expanded` and `/pwf-context-deep` work for the current session without environment variables.
- Missing session id refuses mutating context commands.
- Existing `PWF_CONTEXT_PROFILE` env behavior still works and overrides session settings.
- Hook prompt context can show injection notice based on `auto/on/off`.
- Status and doctor explain effective profile source and notice mode.
- Full test suite passes.
