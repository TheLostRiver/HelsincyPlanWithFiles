# Session Isolation Safety Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining multi-session safety gaps so a PWF session cannot read or write another session's exclusive task through `PLAN_ID`, stale diagnostics reflect owner session heartbeat, and hook session identity matches CLI fallback behavior.

**Architecture:** Keep resolver precedence as `PLAN_ID -> session binding -> workspace active -> newest -> legacy`, but separate routing from authorization. `PLAN_ID` remains a routing override; task ownership gate still authorizes context injection and progress writes. Task ownership remains in `.planning/<plan-id>/.task-lease.json`, while owner freshness is derived from `.planning/session-leases/<owner-key>.json`.

**Tech Stack:** Python standard library, Codex hook entrypoints under `.codex/hooks`, PWF CLI under `.codex/skills/planning-with-files/scripts/plan.py`, `unittest`.

---

## Scope

This plan fixes three defects only:

- `PLAN_ID` currently bypasses task ownership and can write B session auto records into A session's `progress.md`.
- Task lease `stale` status currently uses `.task-lease.json.updated_at`, even though active hook heartbeats update `.planning/session-leases/<session>.json`.
- CLI resolves `CODEX_THREAD_ID` as a session fallback, but hooks only resolve payload `session_id` and `PWF_SESSION_ID`.

No hidden override flag should be added. Cross-owner use remains explicit through claim, share, or release.

## Files

- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Modify: `tests/test_hooks.py`
- Modify: `tests/test_plan_cli.py`
- Modify: `tests/test_plan_doctor.py`
- Modify: `tests/test_project_consistency.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`

---

### Task 1: Add Failing Tests for `PLAN_ID` Ownership Enforcement

**Files:**
- Modify: `tests/test_hooks.py`

- [ ] **Step 1: Add denial regression test**

Add this test to `HookTests` near `test_unbound_workspace_fallback_denies_task_owned_by_other_session`:

```python
    def test_plan_id_env_does_not_bypass_other_session_task_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-env-owned"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            owner_key = self.write_task_lease(root, plan_id, "session-a")

            prompt = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-b"},
                env={"PLAN_ID": plan_id},
            )
            post = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/env-conflict.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-b",
                },
                env={"PLAN_ID": plan_id},
            )

            self.assertEqual(prompt.returncode, 0, prompt.stderr)
            self.assertEqual(post.returncode, 0, post.stderr)
            self.assertIn("owned by another session", json.loads(prompt.stdout)["systemMessage"])
            self.assertIn(owner_key, prompt.stdout)
            self.assertNotIn("additionalContext", prompt.stdout)
            self.assertIn("owned by another session", json.loads(post.stdout)["systemMessage"])
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertNotIn("src/env-conflict.py", progress)
```

- [ ] **Step 2: Add owner positive regression test**

Add:

```python
    def test_plan_id_env_allows_current_owner_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-env-owner"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            key = self.write_task_lease(root, plan_id, "session-a")

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/env-owner.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-a",
                },
                env={"PLAN_ID": plan_id},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("src/env-owner.py", progress)
            self.assertIn(f"- Session: {key}", progress)
            self.assertIn("- Plan-Source: env", progress)
```

- [ ] **Step 3: Add shared and released positive regression tests**

Add:

```python
    def test_plan_id_env_allows_shared_task_for_other_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-env-shared"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            self.write_task_lease(root, plan_id, "session-a", shared=True)

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/env-shared.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-b",
                },
                env={"PLAN_ID": plan_id},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("src/env-shared.py", progress)
```

Add:

```python
    def test_plan_id_env_allows_released_task_for_other_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-env-released"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            owner_key = PLANNING_STATE.session_key("session-a")
            (plan_dir / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": owner_key,
                        "owner_status": "released",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                        "source": "test",
                    }
                ),
                encoding="utf-8",
            )

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/env-released.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-b",
                },
                env={"PLAN_ID": plan_id},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("src/env-released.py", progress)
```

- [ ] **Step 4: Verify the denial test fails before implementation**

Run:

```powershell
python -m unittest `
  tests.test_hooks.HookTests.test_plan_id_env_does_not_bypass_other_session_task_ownership `
  tests.test_hooks.HookTests.test_plan_id_env_allows_current_owner_session `
  tests.test_hooks.HookTests.test_plan_id_env_allows_shared_task_for_other_session `
  tests.test_hooks.HookTests.test_plan_id_env_allows_released_task_for_other_session -v
```

Expected before implementation: `test_plan_id_env_does_not_bypass_other_session_task_ownership` fails because `PLAN_ID` bypasses authorization and writes `src/env-conflict.py`.

---

### Task 2: Enforce Ownership for Env-Sourced Resolution

**Files:**
- Modify: `.codex/hooks/planning_state.py`

- [ ] **Step 1: Remove the env bypass**

Change:

```python
def ownership_denial_for_resolution(
    root: Path,
    resolution: PlanResolution,
    session_id: str | None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    if resolution.source == "env":
        return None
    lease = read_task_lease(root, resolution.plan_id)
```

to:

```python
def ownership_denial_for_resolution(
    root: Path,
    resolution: PlanResolution,
    session_id: str | None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    lease = read_task_lease(root, resolution.plan_id)
```

- [ ] **Step 2: Make the diagnostic source-neutral**

Change:

```python
        "[planning-with-files] workspace active plan is owned by another session; "
```

to:

```python
        f"[planning-with-files] {resolution.source} plan is owned by another session; "
```

Keep the rest of the message unchanged.

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m unittest `
  tests.test_hooks.HookTests.test_plan_id_env_does_not_bypass_other_session_task_ownership `
  tests.test_hooks.HookTests.test_plan_id_env_allows_current_owner_session `
  tests.test_hooks.HookTests.test_plan_id_env_allows_shared_task_for_other_session `
  tests.test_hooks.HookTests.test_plan_id_env_allows_released_task_for_other_session `
  tests.test_hooks.HookTests.test_unbound_workspace_fallback_denies_task_owned_by_other_session `
  tests.test_hooks.HookTests.test_shared_task_lease_allows_second_session -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add .codex/hooks/planning_state.py tests/test_hooks.py
git commit -m "fix: enforce task ownership for plan id override"
```

---

### Task 3: Add Failing Tests for Session-Heartbeat-Based Lease Freshness

**Files:**
- Modify: `tests/test_hooks.py`

- [ ] **Step 1: Add session lease helper to `HookTests`**

Add after `write_task_lease()`:

```python
    def write_session_lease(self, root, session_id, *, heartbeat_at, bound_plan_id=None):
        key = PLANNING_STATE.session_key(session_id)
        lease_dir = root / ".planning" / "session-leases"
        lease_dir.mkdir(parents=True, exist_ok=True)
        (lease_dir / f"{key}.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "session_key": key,
                    "session_id": session_id,
                    "started_at": "2026-06-07T10:00:00Z",
                    "heartbeat_at": heartbeat_at,
                    "status": "active",
                    "bound_plan_id": bound_plan_id,
                    "source": "test",
                }
            ),
            encoding="utf-8",
        )
        return key
```

- [ ] **Step 2: Add active heartbeat test**

Add:

```python
    def test_task_lease_status_uses_owner_session_heartbeat_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-heartbeat-active"
            write_plan(root / ".planning" / plan_id)
            self.write_task_lease(root, plan_id, "session-a", heartbeat_at="2000-01-01T00:00:00Z")
            self.write_session_lease(root, "session-a", heartbeat_at="2999-01-01T00:00:00Z", bound_plan_id=plan_id)

            lease = PLANNING_STATE.read_task_lease(root, plan_id)

            self.assertEqual(PLANNING_STATE.task_lease_status(root, lease), "active")
```

- [ ] **Step 3: Add stale heartbeat test**

Add:

```python
    def test_task_lease_status_reports_stale_when_owner_session_heartbeat_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-heartbeat-stale"
            write_plan(root / ".planning" / plan_id)
            self.write_task_lease(root, plan_id, "session-a", heartbeat_at="2999-01-01T00:00:00Z")
            self.write_session_lease(root, "session-a", heartbeat_at="2000-01-01T00:00:00Z", bound_plan_id=plan_id)

            lease = PLANNING_STATE.read_task_lease(root, plan_id)

            self.assertEqual(
                PLANNING_STATE.task_lease_status(
                    root,
                    lease,
                    env={"PWF_SESSION_LEASE_TTL_SECONDS": "600"},
                ),
                "stale",
            )
```

- [ ] **Step 4: Add stale-still-blocks test**

Add:

```python
    def test_stale_owner_from_session_heartbeat_still_blocks_takeover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-heartbeat-stale-blocks"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
            self.write_task_lease(root, plan_id, "session-a", heartbeat_at="2999-01-01T00:00:00Z")
            self.write_session_lease(root, "session-a", heartbeat_at="2000-01-01T00:00:00Z", bound_plan_id=plan_id)

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/stale-heartbeat.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-b",
                },
                env={"PWF_SESSION_LEASE_TTL_SECONDS": "600"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            message = json.loads(result.stdout)["systemMessage"]
            self.assertIn("owned by another session", message)
            self.assertIn("stale", message)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertNotIn("src/stale-heartbeat.py", progress)
```

- [ ] **Step 5: Verify tests fail before implementation**

Run:

```powershell
python -m unittest `
  tests.test_hooks.HookTests.test_task_lease_status_uses_owner_session_heartbeat_when_available `
  tests.test_hooks.HookTests.test_task_lease_status_reports_stale_when_owner_session_heartbeat_expired `
  tests.test_hooks.HookTests.test_stale_owner_from_session_heartbeat_still_blocks_takeover -v
```

Expected before implementation: direct calls fail due the changed planned signature, or the active heartbeat test returns `stale`.

---

### Task 4: Implement Session-Heartbeat-Based Task Lease Status

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Modify: `tests/test_hooks.py`
- Modify: `tests/test_plan_cli.py`
- Modify: `tests/test_plan_doctor.py`

- [ ] **Step 1: Add owner-key session lease path helper**

In `.codex/hooks/planning_state.py`, after `session_lease_path()` add:

```python
def session_lease_path_for_key(root: Path, owner_session_key: str) -> Path:
    return _session_leases_dir(root) / f"{owner_session_key}.json"
```

- [ ] **Step 2: Add owner-key session lease reader**

After `refresh_session_lease()`, add:

```python
def read_session_lease_for_key(root: Path, owner_session_key: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[0-9a-f]{12}", owner_session_key):
        return None
    path = session_lease_path_for_key(root, owner_session_key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    if payload.get("session_key") != owner_session_key:
        return None
    heartbeat_at = payload.get("heartbeat_at")
    if not isinstance(heartbeat_at, str):
        return None
    return payload
```

- [ ] **Step 3: Replace `task_lease_status()`**

Replace:

```python
def task_lease_status(lease: TaskLease, env: Mapping[str, str] | None = None) -> str:
    if lease.shared:
        return "shared"
    if lease.owner_status == "released":
        return "released"
    updated = _parse_iso_z(lease.updated_at)
    if updated is None:
        return "stale"
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - updated).total_seconds()
    return "stale" if age > session_lease_ttl_seconds(env) else "active"
```

with:

```python
def task_lease_status(
    root: Path,
    lease: TaskLease,
    env: Mapping[str, str] | None = None,
) -> str:
    if lease.shared:
        return "shared"
    if lease.owner_status == "released":
        return "released"

    session_lease = read_session_lease_for_key(root, lease.owner_session_key)
    heartbeat_value = session_lease.get("heartbeat_at") if session_lease is not None else lease.updated_at
    if not isinstance(heartbeat_value, str):
        return "stale"
    heartbeat = _parse_iso_z(heartbeat_value)
    if heartbeat is None:
        return "stale"
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - heartbeat).total_seconds()
    return "stale" if age > session_lease_ttl_seconds(env) else "active"
```

- [ ] **Step 4: Update Python hook call sites**

Run:

```powershell
rg -n "task_lease_status\(" .codex/hooks/planning_state.py
```

Update each call to pass `root`:

```python
status = task_lease_status(root, lease, env)
status = task_lease_status(root, existing)
```

- [ ] **Step 5: Update CLI call sites**

Run:

```powershell
rg -n "task_lease_status\(" .codex/skills/planning-with-files/scripts/plan.py
```

Update each call to pass `root`:

```python
status = planning_state.task_lease_status(root, lease)
```

- [ ] **Step 6: Update direct test calls**

Run:

```powershell
rg -n "task_lease_status\(" tests
```

Update direct calls to:

```python
PLANNING_STATE.task_lease_status(root, lease)
```

- [ ] **Step 7: Run targeted tests**

Run:

```powershell
python -m unittest `
  tests.test_hooks.HookTests.test_task_lease_status_uses_owner_session_heartbeat_when_available `
  tests.test_hooks.HookTests.test_task_lease_status_reports_stale_when_owner_session_heartbeat_expired `
  tests.test_hooks.HookTests.test_stale_owner_from_session_heartbeat_still_blocks_takeover `
  tests.test_hooks.HookTests.test_stale_owner_still_blocks_workspace_takeover `
  tests.test_plan_cli.PlanCliTests.test_status_reports_session_and_task_lease `
  tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_workspace_active_task_owned_by_another_session -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add .codex/hooks/planning_state.py .codex/skills/planning-with-files/scripts/plan.py tests/test_hooks.py tests/test_plan_cli.py tests/test_plan_doctor.py
git commit -m "fix: derive task lease freshness from session heartbeat"
```

---

### Task 5: Add Failing Tests for Hook `CODEX_THREAD_ID` Fallback

**Files:**
- Modify: `tests/test_hooks.py`

- [ ] **Step 1: Add adapter fallback test**

Add to `PlanResolutionTests`:

```python
    def test_hook_session_id_falls_back_to_codex_thread_id(self):
        adapter = SourceFileLoader(
            "codex_hook_adapter_under_test",
            str(REPO_ROOT / ".codex" / "hooks" / "codex_hook_adapter.py"),
        ).load_module()
        old_pwf = os.environ.pop("PWF_SESSION_ID", None)
        old_thread = os.environ.get("CODEX_THREAD_ID")
        os.environ["CODEX_THREAD_ID"] = "thread-a"
        try:
            self.assertEqual(adapter.session_id_from_payload({}), "thread-a")
            self.assertEqual(adapter.session_id_from_payload({"session_id": "payload-a"}), "payload-a")
        finally:
            if old_pwf is not None:
                os.environ["PWF_SESSION_ID"] = old_pwf
            else:
                os.environ.pop("PWF_SESSION_ID", None)
            if old_thread is not None:
                os.environ["CODEX_THREAD_ID"] = old_thread
            else:
                os.environ.pop("CODEX_THREAD_ID", None)
```

- [ ] **Step 2: Add end-to-end hook fallback test**

Add to `HookTests`:

```python
    def test_post_tool_use_uses_codex_thread_id_when_payload_session_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-11-thread-hook"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            key = PLANNING_STATE.session_key("thread-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "thread-a", "plan_id": plan_id}),
                encoding="utf-8",
            )
            self.write_task_lease(root, plan_id, "thread-a")

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/thread-hook.py"},
                    "tool_response": {"success": True},
                },
                env={"CODEX_THREAD_ID": "thread-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("src/thread-hook.py", progress)
            self.assertIn(f"- Session: {key}", progress)
            self.assertIn("- Plan-Source: session", progress)
```

- [ ] **Step 3: Verify tests fail before implementation**

Run:

```powershell
python -m unittest `
  tests.test_hooks.PlanResolutionTests.test_hook_session_id_falls_back_to_codex_thread_id `
  tests.test_hooks.HookTests.test_post_tool_use_uses_codex_thread_id_when_payload_session_missing -v
```

Expected before implementation: both tests fail because hook adapter ignores `CODEX_THREAD_ID`.

---

### Task 6: Implement Hook `CODEX_THREAD_ID` Fallback

**Files:**
- Modify: `.codex/hooks/codex_hook_adapter.py`

- [ ] **Step 1: Update session identity helper**

Replace:

```python
def session_id_from_payload(payload: dict[str, Any]) -> str | None:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    env_sid = os.environ.get("PWF_SESSION_ID", "")
    return env_sid if env_sid else None
```

with:

```python
def session_id_from_payload(payload: dict[str, Any]) -> str | None:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    for name in ("PWF_SESSION_ID", "CODEX_THREAD_ID"):
        env_sid = os.environ.get(name, "").strip()
        if env_sid:
            return env_sid
    return None
```

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
python -m unittest `
  tests.test_hooks.PlanResolutionTests.test_hook_session_id_falls_back_to_codex_thread_id `
  tests.test_hooks.HookTests.test_post_tool_use_uses_codex_thread_id_when_payload_session_missing `
  tests.test_hooks.HookTests.test_user_prompt_submit_strict_mode_requires_attached_session `
  tests.test_hooks.HookTests.test_strict_requires_binding_rejects_attached_unbound_session -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```powershell
git add .codex/hooks/codex_hook_adapter.py tests/test_hooks.py
git commit -m "fix: align hook session fallback with cli"
```

---

### Task 7: Update Documentation and Consistency Tests

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_project_consistency.py`

- [ ] **Step 1: Update strict-mode session identity wording**

Use this English text in README/FAQ where strict mode is described:

```markdown
In strict mode, hooks must be able to resolve an attached session id. The hook payload `session_id` wins, then `PWF_SESSION_ID`, then `CODEX_THREAD_ID`; otherwise the hook emits a diagnostic message instead of silently skipping planning context.
```

Use this Chinese text in README/FAQ:

```markdown
strict 模式下，hook 必须能解析出已 attach 的 session id。解析顺序是 hook payload `session_id`、`PWF_SESSION_ID`、`CODEX_THREAD_ID`；如果无法解析，hook 会输出诊断消息，而不是静默跳过 planning 上下文。
```

- [ ] **Step 2: Document `PLAN_ID` safety semantics**

English:

```markdown
`PLAN_ID` is a routing override, not a permission override. If the selected named task is owned by another session, hooks still deny context injection and progress writes unless the task is shared, released, or owned by the current session.
```

Chinese:

```markdown
`PLAN_ID` 是路由覆盖，不是权限覆盖。如果它选中的命名任务由另一个 session 拥有，hook 仍会拒绝注入上下文和写入 progress，除非该任务已共享、已释放，或 owner 就是当前 session。
```

- [ ] **Step 3: Document heartbeat freshness semantics**

English:

```markdown
Task ownership lives in `.planning/<plan-id>/.task-lease.json`; owner freshness is diagnosed from `.planning/session-leases/<owner>.json`. A stale owner is still an owner and still requires explicit `--force-claim`, `--share`, or `--release-session`.
```

Chinese:

```markdown
任务 ownership 存在 `.planning/<plan-id>/.task-lease.json`；owner 是否新鲜由 `.planning/session-leases/<owner>.json` 的心跳诊断。stale owner 仍然是 owner，仍然必须显式 `--force-claim`、`--share` 或 `--release-session`。
```

- [ ] **Step 4: Add CHANGELOG entry**

At the top of `CHANGELOG.md`, add:

```markdown
## Unreleased

- 中文：收紧多会话任务隔离：`PLAN_ID` 现在只作为路由覆盖，不再绕过 task ownership gate；task stale 诊断改为基于 owner session heartbeat；hook 会话识别与 CLI 一致，按 payload `session_id`、`PWF_SESSION_ID`、`CODEX_THREAD_ID` 顺序解析。
- English: Hardened multi-session task isolation: `PLAN_ID` is now only a routing override and no longer bypasses the task ownership gate; stale task diagnostics now use the owner session heartbeat; hook session identity now matches CLI fallback order: payload `session_id`, `PWF_SESSION_ID`, `CODEX_THREAD_ID`.
```

- [ ] **Step 5: Extend consistency tests**

In `tests/test_project_consistency.py`, extend the existing session docs tests with these assertions, using the file variables already loaded in the test:

```python
self.assertIn("PLAN_ID", combined)
self.assertIn("routing override", readme_en + faq)
self.assertIn("permission override", readme_en + faq)
self.assertIn("CODEX_THREAD_ID", readme_en + readme_cn + faq)
self.assertIn("owner session heartbeat", readme_en + faq + changelog)
self.assertIn("路由覆盖", readme_cn + faq)
self.assertIn("权限覆盖", readme_cn + faq)
self.assertIn("心跳", readme_cn + faq)
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add README.md README.en.md docs/FAQ.md CHANGELOG.md tests/test_project_consistency.py
git commit -m "docs: clarify session isolation safety boundaries"
```

---

### Task 8: Final Verification and PR Preparation

**Files:**
- No planned source edits.

- [ ] **Step 1: Run targeted safety suite**

Run:

```powershell
python -m unittest `
  tests.test_hooks.HookTests.test_plan_id_env_does_not_bypass_other_session_task_ownership `
  tests.test_hooks.HookTests.test_plan_id_env_allows_current_owner_session `
  tests.test_hooks.HookTests.test_plan_id_env_allows_shared_task_for_other_session `
  tests.test_hooks.HookTests.test_plan_id_env_allows_released_task_for_other_session `
  tests.test_hooks.HookTests.test_task_lease_status_uses_owner_session_heartbeat_when_available `
  tests.test_hooks.HookTests.test_task_lease_status_reports_stale_when_owner_session_heartbeat_expired `
  tests.test_hooks.HookTests.test_stale_owner_from_session_heartbeat_still_blocks_takeover `
  tests.test_hooks.PlanResolutionTests.test_hook_session_id_falls_back_to_codex_thread_id `
  tests.test_hooks.HookTests.test_post_tool_use_uses_codex_thread_id_when_payload_session_missing -v
```

Expected: PASS.

- [ ] **Step 2: Run affected test modules**

Run:

```powershell
python -m unittest tests.test_hooks tests.test_plan_cli tests.test_plan_doctor tests.test_project_consistency -v
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run:

```powershell
python -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 4: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Run doctor**

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Expected: `hooks.json: ok`, `hook files: ok`, `python runtime: ok`, and no new warnings from this branch.

- [ ] **Step 6: Manual smoke for `PLAN_ID` boundary**

Confirm in a temp directory:

- session A owns a named plan,
- session B with `PLAN_ID` pointing at A's plan receives `owned by another session`,
- A's `progress.md` does not include B's file path,
- session A with the same `PLAN_ID` can write.

- [ ] **Step 7: Manual smoke for heartbeat freshness**

Confirm in a temp directory:

- old `.task-lease.json.updated_at` plus fresh owner session lease reports `active`,
- expired owner session lease reports `stale`,
- stale owner still blocks session B without explicit claim/share.

- [ ] **Step 8: Review diff**

Run:

```powershell
git diff --stat origin/main...HEAD
git diff -- .codex/hooks/planning_state.py .codex/hooks/codex_hook_adapter.py .codex/skills/planning-with-files/scripts/plan.py tests README.md README.en.md docs/FAQ.md CHANGELOG.md
```

Check:

- no broad refactor,
- no bypass env var,
- `PLAN_ID` remains routing-first but not permission bypass,
- stale remains diagnostic-only,
- docs match behavior.

- [ ] **Step 9: Push and open draft PR**

Run:

```powershell
git push -u origin fix/session-isolation-safety
```

Draft PR body:

```markdown
## Summary

- enforce task ownership even when hooks resolve a plan through `PLAN_ID`
- derive task lease active/stale diagnostics from owner session heartbeat
- align hook session identity fallback with CLI (`session_id`, `PWF_SESSION_ID`, `CODEX_THREAD_ID`)

## Safety

- `PLAN_ID` remains a routing override, not a permission override
- stale owners still block automatic takeover
- cross-owner use still requires explicit claim/share/release

## Tests

- python -m unittest tests.test_hooks tests.test_plan_cli tests.test_plan_doctor tests.test_project_consistency -v
- python -m unittest discover -v
- git diff --check
- python .codex\skills\planning-with-files\scripts\plan.py doctor
```

---

## Self-Review

- The plan covers all three reviewed defects.
- Tests are written before implementation.
- No bypass flag is introduced.
- Documentation explicitly distinguishes routing override from permission override.
- Verification includes targeted tests, full tests, diff check, doctor, and manual smoke.
