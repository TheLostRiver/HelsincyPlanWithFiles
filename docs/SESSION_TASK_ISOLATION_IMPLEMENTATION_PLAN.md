# 会话任务隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让同一个项目里的多个 Codex 对话可以绑定到不同 PWF 任务，并保证上下文注入、`progress.md` 自动记录、状态诊断和严格隔离策略都按当前会话的 effective plan 路由。

**Architecture:** 在现有 workspace active plan 之上新增 session-to-plan binding 层，解析顺序为 `PLAN_ID -> session binding -> .planning/.active_plan -> newest plan -> legacy root plan`。binding 负责“当前 session 想使用哪个 plan”，session lease 和 task lease 负责“当前 session 是否允许使用这个 plan”。hook entrypoint 从 payload 读取 `session_id` 后传入同一个解析器和 ownership gate；CLI 负责创建、切换、共享、释放和诊断 binding/lease。`progress.md` append 增加短时文件锁和来源元数据，锁只保护物理写入，任务归属仍由 resolver + ownership gate 决定。

**Tech Stack:** Python 标准库、Codex hook JSON stdin/stdout、`.planning/` 本地运行态文件、Markdown planning files、`unittest`、PowerShell 验证命令。

---

## 执行前约束

本计划在 `plan/session-task-isolation` 分支执行，不在 `main` 上直接改。仓库中未跟踪的 `dist/` 不属于本任务，执行期间不读取、不删除、不提交。

`docs/superpowers/` 在本仓库中被忽略，所以本计划保存在可提交的 `docs/SESSION_TASK_ISOLATION_IMPLEMENTATION_PLAN.md`。现有英文设计文档 `docs/SESSION_TASK_ISOLATION_PLAN.en.md` 保留，用户面向文档以中文为主。

## 文件职责图

- Modify `.codex/hooks/planning_state.py`: 增加 `PlanResolution`、session key、binding 读写路径、plan id 校验、session-aware resolver、session lease/task lease 读写、ownership gate、progress append lock、auto record 来源元数据，并让现有 root-only API 保持兼容。
- Modify `.codex/hooks/codex_hook_adapter.py`: 增加 ownership denial 输出和 strict require-binding 开关，读取 env 和 `.planning/session-policy.json`，让 strict mode 可以在 opt-in 时拒绝未绑定 session。
- Modify `.codex/hooks/session_start.py`: 把 `session_id` 传给 resolver 和 prompt context；`session-catchup.py` 只针对 effective plan 做恢复提示。
- Modify `.codex/hooks/user_prompt_submit.py`: 注入 session-bound plan 的 prompt context。
- Modify `.codex/hooks/pre_tool_use.py`: 注入 session-bound plan 的 pre-tool context。
- Modify `.codex/hooks/post_tool_use.py`: 把自动记录写入 session-bound plan 的 `progress.md`，并把 lock warning 放进 system message。
- Modify `.codex/hooks/stop.py`: 用 session-bound plan 判断任务是否完成。
- Modify `.codex/skills/planning-with-files/scripts/plan.py`: 增加 `init --bind-session`、`init --no-workspace-active`、`switch --session`、`switch --workspace`、`switch --clear-session`、`switch --force-claim`、`switch --share`、`switch --release-session`、status/doctor session lease/task lease diagnostics。
- Modify `.codex/skills/planning-with-files/scripts/session-catchup.py`: 支持 `--planning-dir`，只把当前 effective plan 的 planning files 当作 catchup 边界。
- Modify `.codex/skills/planning-with-files/SKILL.md`: 更新用户可见工作流说明。
- Modify `README.md`, `README.en.md`, `docs/FAQ.md`, `CHANGELOG.md`: 记录 session binding、strict binding enforcement、progress metadata 和迁移说明。
- Test `tests/test_hooks.py`: 覆盖 resolver、hook routing、ownership gate、strict enforcement、progress metadata 和 lock。
- Test `tests/test_plan_cli.py`: 覆盖 CLI binding 创建、切换、强制接管、共享、释放、清除和 status 输出。
- Test `tests/test_plan_doctor.py`: 覆盖 doctor session binding、session lease、task lease conflict 和 strict enforcement diagnostics。
- Test `tests/test_progress_compaction.py`: 确认新增 auto record 字段不破坏 recent progress 和 compact parsing。
- Test `tests/test_project_consistency.py`: 确保 README、FAQ、skill 文档都说明 session binding。

## 关键不变量

同一个 hook payload 内，`SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse` 和 `Stop` 必须用相同的 `(root, session_id, env)` 解析到相同 effective plan。用户看到的 planning context 是哪个 plan，自动记录就必须写入同一个 plan 的 `progress.md`。

`PLAN_ID` 仍然是最高优先级显式 override。`.planning/.active_plan` 继续作为 workspace fallback 和默认用户工作流，不因为新增 binding 而改变旧行为。

binding 文件名必须使用短 digest，不使用原始 `session_id`。JSON 内可保存原始 `session_id` 作为本地诊断数据，但任何 hook/CLI 输出都只能显示短 key 或 sanitize 后的截断值。

session binding 是路由选择，task lease 是使用授权。未绑定 session 不能因为 `.planning/.active_plan` 指向某个任务，就自动使用另一个 session 拥有的 task。stale owner 仍然是 owner；TTL 只改变诊断文字，不授予自动接管权限。

ownership 只能通过显式命令改变：`switch --session --force-claim` 接管，`switch --session --share` 共享，`switch --release-session` 释放。任何 hook 都不能在发现 owner stale 后自行转移 `.task-lease.json`。

## Task 1: Plan Resolution Model

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing resolver tests**

在 `tests/test_hooks.py` 的 `ContextLimitResolverTests` 后添加这个 test class：

```python
class PlanResolutionTests(unittest.TestCase):
    def write_named_plan(self, root, plan_id, title):
        plan_dir = root / ".planning" / plan_id
        write_plan(plan_dir)
        (plan_dir / "task_plan.md").write_text(
            f"# Task Plan: {title}\n\n## Phases\n\n### Phase 1: Test\n- **Status:** in_progress\n",
            encoding="utf-8",
        )
        return plan_dir

    def write_session_binding(self, root, session_id, plan_id):
        key = PLANNING_STATE.session_key(session_id)
        bindings = root / ".planning" / "session-bindings"
        bindings.mkdir(parents=True, exist_ok=True)
        (bindings / f"{key}.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "session_id": session_id,
                    "plan_id": plan_id,
                    "created_at": "2026-06-07T00:00:00Z",
                    "updated_at": "2026-06-07T00:00:00Z",
                    "source": "test",
                }
            ),
            encoding="utf-8",
        )
        return key

    def test_session_binding_precedes_workspace_active_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bound = self.write_named_plan(root, "2026-06-07-bound", "Bound")
            self.write_named_plan(root, "2026-06-07-workspace", "Workspace")
            (root / ".planning" / ".active_plan").write_text(
                "2026-06-07-workspace\n",
                encoding="utf-8",
            )
            key = self.write_session_binding(root, "session-a", "2026-06-07-bound")

            resolution = PLANNING_STATE.resolve_planning_context(
                root,
                env={},
                session_id="session-a",
            )

            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.source, "session")
            self.assertEqual(resolution.plan_id, "2026-06-07-bound")
            self.assertEqual(resolution.session_key, key)
            self.assertEqual(resolution.paths.root, bound)

    def test_plan_id_env_precedes_session_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_plan = self.write_named_plan(root, "2026-06-07-env", "Env")
            self.write_named_plan(root, "2026-06-07-bound", "Bound")
            self.write_session_binding(root, "session-a", "2026-06-07-bound")

            resolution = PLANNING_STATE.resolve_planning_context(
                root,
                env={"PLAN_ID": "2026-06-07-env"},
                session_id="session-a",
            )

            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.source, "env")
            self.assertEqual(resolution.plan_id, "2026-06-07-env")
            self.assertEqual(resolution.paths.root, env_plan)

    def test_invalid_session_binding_falls_back_to_workspace_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = self.write_named_plan(root, "2026-06-07-workspace", "Workspace")
            (root / ".planning" / ".active_plan").write_text(
                "2026-06-07-workspace\n",
                encoding="utf-8",
            )
            key = PLANNING_STATE.session_key("session-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True, exist_ok=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "../escape"}),
                encoding="utf-8",
            )

            resolution = PLANNING_STATE.resolve_planning_context(
                root,
                env={},
                session_id="session-a",
            )

            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.source, "workspace")
            self.assertEqual(resolution.plan_id, "2026-06-07-workspace")
            self.assertEqual(resolution.paths.root, workspace)
            self.assertIn("ignored session binding", resolution.warning)

    def test_session_key_is_short_digest_not_raw_session_id(self):
        key = PLANNING_STATE.session_key("raw/session id with spaces")

        self.assertRegex(key, r"^[0-9a-f]{12}$")
        self.assertNotIn("raw", key)
        self.assertNotIn("/", key)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_hooks.PlanResolutionTests -v
```

Expected: tests fail with `AttributeError` for `session_key` or `resolve_planning_context`.

- [ ] **Step 3: Add resolution data structures and helpers**

In `.codex/hooks/planning_state.py`, add this dataclass after `PlanningPaths`:

```python
@dataclass(frozen=True)
class PlanResolution:
    source: str
    plan_id: str
    paths: PlanningPaths
    session_key: str | None = None
    warning: str | None = None
```

Add these helpers near `safe_env_value`:

```python
VALID_PLAN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")


def session_key(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


def valid_plan_id(plan_id: str) -> bool:
    if not VALID_PLAN_ID_RE.fullmatch(plan_id):
        return False
    if plan_id in {".", ".."}:
        return False
    return "/" not in plan_id and "\\" not in plan_id


def _paths_for_plan_dir(plan_dir: Path) -> PlanningPaths:
    return PlanningPaths(
        root=plan_dir,
        task_plan=plan_dir / "task_plan.md",
        progress=plan_dir / "progress.md",
        findings=plan_dir / "findings.md",
    )


def _session_binding_path(root: Path, session_id: str) -> Path:
    return root / ".planning" / "session-bindings" / f"{session_key(session_id)}.json"
```

- [ ] **Step 4: Replace root-only resolver with session-aware resolver**

Replace `resolve_plan_dir(root)` with this implementation and keep the public wrapper name:

```python
def _resolution_from_plan_id(
    root: Path,
    plan_id: str,
    source: str,
    session_key_value: str | None = None,
    warning: str | None = None,
) -> PlanResolution | None:
    if not valid_plan_id(plan_id):
        return None
    candidate = root / ".planning" / plan_id
    if not (candidate / "task_plan.md").is_file():
        return None
    return PlanResolution(
        source=source,
        plan_id=plan_id,
        paths=_paths_for_plan_dir(candidate),
        session_key=session_key_value,
        warning=warning,
    )


def _read_session_plan_id(root: Path, session_id: str) -> tuple[str | None, str | None, str | None]:
    key = session_key(session_id)
    path = _session_binding_path(root, session_id)
    if not path.is_file():
        return None, key, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None, key, f"[warn] ignored session binding {key}: invalid json"
    if not isinstance(payload, dict):
        return None, key, f"[warn] ignored session binding {key}: not an object"
    if payload.get("version") != 1:
        return None, key, f"[warn] ignored session binding {key}: unsupported version"
    plan_id = payload.get("plan_id")
    if not isinstance(plan_id, str) or not valid_plan_id(plan_id):
        return None, key, f"[warn] ignored session binding {key}: invalid plan_id"
    return plan_id, key, None


def resolve_planning_context(
    root: Path,
    env: Mapping[str, str] | None = None,
    session_id: str | None = None,
) -> PlanResolution | None:
    root = root.resolve()
    source = env if env is not None else os.environ
    plan_root = root / ".planning"

    env_plan = source.get("PLAN_ID", "").strip()
    if env_plan:
        resolution = _resolution_from_plan_id(root, env_plan, "env")
        if resolution is not None:
            return resolution

    binding_warning: str | None = None
    if session_id:
        bound_plan, key, warning = _read_session_plan_id(root, session_id)
        binding_warning = warning
        if bound_plan:
            resolution = _resolution_from_plan_id(
                root,
                bound_plan,
                "session",
                session_key_value=key,
                warning=warning,
            )
            if resolution is not None:
                return resolution
            binding_warning = f"[warn] ignored session binding {key}: missing plan"

    active_file = plan_root / ".active_plan"
    if active_file.is_file():
        plan_id = active_file.read_text(encoding="utf-8", errors="replace").strip()
        if plan_id:
            resolution = _resolution_from_plan_id(root, plan_id, "workspace", warning=binding_warning)
            if resolution is not None:
                return resolution

    if plan_root.is_dir():
        candidates = [
            item
            for item in plan_root.iterdir()
            if item.is_dir()
            and not item.name.startswith(".")
            and valid_plan_id(item.name)
            and (item / "task_plan.md").is_file()
        ]
        if candidates:
            newest = max(candidates, key=lambda item: item.stat().st_mtime)
            return PlanResolution(
                source="newest",
                plan_id=newest.name,
                paths=_paths_for_plan_dir(newest),
                warning=binding_warning,
            )

    if (root / "task_plan.md").is_file():
        return PlanResolution(
            source="legacy",
            plan_id="legacy",
            paths=_paths_for_plan_dir(root),
            warning=binding_warning,
        )

    return None


def resolve_plan_dir(root: Path) -> Path | None:
    resolution = resolve_planning_context(root)
    return resolution.paths.root if resolution is not None else None
```

Add `import json` near the top of `planning_state.py`.

- [ ] **Step 5: Update `planning_paths` to use the new resolver**

Replace `planning_paths(root)` with:

```python
def planning_paths(root: Path, session_id: str | None = None) -> PlanningPaths | None:
    resolution = resolve_planning_context(root, session_id=session_id)
    return resolution.paths if resolution is not None else None
```

- [ ] **Step 6: Run resolver tests**

Run:

```powershell
python -m unittest tests.test_hooks.PlanResolutionTests -v
```

Expected: all `PlanResolutionTests` pass.

- [ ] **Step 7: Run existing hook tests for regression**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_post_tool_use_resolves_active_plan_directory tests.test_hooks.HookTests.test_pre_tool_use_outputs_json_system_message -v
```

Expected: both tests pass.

- [ ] **Step 8: Commit Task 1**

Run:

```powershell
git add .codex/hooks/planning_state.py tests/test_hooks.py
git commit -m "feat: add session-aware plan resolution"
```

## Task 2: Route Hooks Through Session-Aware Resolution

**Files:**
- Modify: `.codex/hooks/session_start.py`
- Modify: `.codex/hooks/user_prompt_submit.py`
- Modify: `.codex/hooks/pre_tool_use.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Modify: `.codex/hooks/stop.py`
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing hook routing tests**

Append these tests to `HookTests` in `tests/test_hooks.py`:

```python
    def test_user_prompt_submit_uses_session_bound_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bound = root / ".planning" / "2026-06-07-bound"
            workspace = root / ".planning" / "2026-06-07-workspace"
            write_plan(bound)
            write_plan(workspace)
            (bound / "task_plan.md").write_text("# Task Plan: Bound\n", encoding="utf-8")
            (workspace / "task_plan.md").write_text("# Task Plan: Workspace\n", encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")
            key = PLANNING_STATE.session_key("session-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True, exist_ok=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-bound"}),
                encoding="utf-8",
            )

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("# Task Plan: Bound", context)
            self.assertNotIn("# Task Plan: Workspace", context)

    def test_post_tool_use_writes_to_session_bound_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bound = root / ".planning" / "2026-06-07-bound"
            workspace = root / ".planning" / "2026-06-07-workspace"
            write_plan(bound)
            write_plan(workspace)
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")
            key = PLANNING_STATE.session_key("session-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True, exist_ok=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-bound"}),
                encoding="utf-8",
            )

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/session_bound.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-a",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("src/session_bound.py", (bound / "progress.md").read_text(encoding="utf-8"))
            self.assertNotIn("src/session_bound.py", (workspace / "progress.md").read_text(encoding="utf-8"))

    def test_stop_uses_session_bound_plan_completion_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bound = root / ".planning" / "2026-06-07-bound"
            workspace = root / ".planning" / "2026-06-07-workspace"
            write_plan(bound, complete=True)
            write_plan(workspace, complete=False)
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")
            key = PLANNING_STATE.session_key("session-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True, exist_ok=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-bound"}),
                encoding="utf-8",
            )

            result = run_hook(
                "stop.py",
                root,
                {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_uses_session_bound_plan tests.test_hooks.HookTests.test_post_tool_use_writes_to_session_bound_progress tests.test_hooks.HookTests.test_stop_uses_session_bound_plan_completion_state -v
```

Expected: tests fail because hook helpers still call root-only `planning_paths(root)`.

- [ ] **Step 3: Add session parameters to render and status helpers**

In `.codex/hooks/planning_state.py`, update these signatures and internal calls:

```python
def render_pre_tool_context(root: Path, session_id: str | None = None) -> str:
    paths = planning_paths(root, session_id=session_id)
    if paths is None:
        return ""
    limits = context_limits()
    return _render_plan_data(root, paths, limits.pre_tool_plan_head_lines)


def render_prompt_context(root: Path, session_id: str | None = None) -> str:
    paths = planning_paths(root, session_id=session_id)
    if paths is None:
        return ""
    ...


def progress_compaction_notice(root: Path, session_id: str | None = None) -> str:
    paths = planning_paths(root, session_id=session_id)
    if paths is None:
        return ""
    ...


def append_progress(root: Path, payload: dict[str, Any], session_id: str | None = None) -> bool:
    ...
    paths = planning_paths(root, session_id=session_id)
    ...


def phase_counts(root: Path, session_id: str | None = None) -> tuple[int, int, int, int] | None:
    paths = planning_paths(root, session_id=session_id)
    ...


def stop_message(root: Path, session_id: str | None = None) -> str | None:
    counts = phase_counts(root, session_id=session_id)
    ...
```

Keep existing callers working by making every new argument optional.

- [ ] **Step 4: Pass session id through hook entrypoints**

Change hook entrypoints as follows:

```python
# user_prompt_submit.py
context = planning_state.render_prompt_context(root, session_id=session_id)

# pre_tool_use.py
context = planning_state.render_pre_tool_context(root, session_id=session_id)

# post_tool_use.py
if planning_state.append_progress(root, payload, session_id=session_id):
    message = planning_state.message("post_tool_recorded")
    notice = planning_state.progress_compaction_notice(root, session_id=session_id)

# stop.py
message = planning_state.stop_message(root, session_id=session_id)
```

In `session_start.py`, change:

```python
parts = [_run_session_catchup(root), planning_state.render_prompt_context(root, session_id=session_id)]
```

- [ ] **Step 5: Run hook routing tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_uses_session_bound_plan tests.test_hooks.HookTests.test_post_tool_use_writes_to_session_bound_progress tests.test_hooks.HookTests.test_stop_uses_session_bound_plan_completion_state -v
```

Expected: all three tests pass.

- [ ] **Step 6: Run existing hook regression tests**

Run:

```powershell
python -m unittest tests.test_hooks -v
```

Expected: all `tests.test_hooks` tests pass.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add .codex/hooks/session_start.py .codex/hooks/user_prompt_submit.py .codex/hooks/pre_tool_use.py .codex/hooks/post_tool_use.py .codex/hooks/stop.py .codex/hooks/planning_state.py tests/test_hooks.py
git commit -m "feat: route hooks through session-bound plans"
```

## Task 3: Session Catchup Uses Effective Plan

**Files:**
- Modify: `.codex/hooks/session_start.py`
- Modify: `.codex/skills/planning-with-files/scripts/session-catchup.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Add failing catchup argument test**

Add this test to `HookTests`:

```python
    def test_session_start_calls_catchup_for_effective_plan_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-06-07-bound"
            write_plan(plan_dir)
            key = PLANNING_STATE.session_key("session-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True, exist_ok=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-bound"}),
                encoding="utf-8",
            )

            result = run_hook(
                "session_start.py",
                root,
                {"hook_event_name": "SessionStart", "source": "startup", "session_id": "session-a"},
                env={"PWF_SESSION_CATCHUP_ECHO_ARGS": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn(f"planning-dir: {plan_dir}", output)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_session_start_calls_catchup_for_effective_plan_directory -v
```

Expected: fail because `session_start.py` does not pass `--planning-dir` to `session-catchup.py`.

- [ ] **Step 3: Update `session-catchup.py` argument parsing**

In `.codex/skills/planning-with-files/scripts/session-catchup.py`, replace `main()` argument extraction with:

```python
def parse_args(argv: List[str]) -> Tuple[str, Optional[str]]:
    project_path = argv[1] if len(argv) > 1 else os.getcwd()
    planning_dir = None
    if "--planning-dir" in argv:
        index = argv.index("--planning-dir")
        if index + 1 < len(argv):
            planning_dir = argv[index + 1]
    return project_path, planning_dir


def planning_files_exist(project_path: str, planning_dir: Optional[str]) -> bool:
    base = Path(planning_dir) if planning_dir else Path(project_path)
    return any(Path(base, name).exists() for name in PLANNING_FILES)
```

Then at the top of `main()` use:

```python
    project_path, planning_dir = parse_args(sys.argv)

    if os.getenv("PWF_SESSION_CATCHUP_ECHO_ARGS", "").strip() == "1":
        print(f"[planning-with-files] catchup project: {project_path}")
        print(f"[planning-with-files] planning-dir: {planning_dir or project_path}")
        return

    if not planning_files_exist(project_path, planning_dir):
        return
```

- [ ] **Step 4: Pass effective plan dir from `session_start.py`**

In `.codex/hooks/session_start.py`, change `_run_session_catchup` to accept a plan dir:

```python
def _run_session_catchup(root: Path, planning_dir: Path | None) -> str:
    hook_dir = Path(__file__).resolve().parent
    skill_dir = hook_dir.parent / "skills" / "planning-with-files"
    script = skill_dir / "scripts" / "session-catchup.py"
    if not script.is_file():
        return ""

    command = [sys.executable, str(script), str(root)]
    if planning_dir is not None:
        command.extend(["--planning-dir", str(planning_dir)])

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip()
```

Resolve once in `main()`:

```python
    resolution = planning_state.resolve_planning_context(root, session_id=session_id)
    planning_dir = resolution.paths.root if resolution is not None else None
    parts = [
        _run_session_catchup(root, planning_dir),
        planning_state.render_prompt_context(root, session_id=session_id),
    ]
```

- [ ] **Step 5: Run catchup test**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_session_start_calls_catchup_for_effective_plan_directory -v
```

Expected: test passes.

- [ ] **Step 6: Run session start regression**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_session_start_outputs_json_additional_context -v
```

Expected: test passes.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add .codex/hooks/session_start.py .codex/skills/planning-with-files/scripts/session-catchup.py tests/test_hooks.py
git commit -m "feat: scope session catchup to effective plan"
```

## Task 4: CLI Session Binding Commands

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Add these tests to `PlanCliTests`:

```python
    def test_switch_session_writes_binding_without_changing_workspace_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root / ".planning" / "2026-06-07-workspace")
            write_plan(root / ".planning" / "2026-06-07-session")
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")

            result = run_plan(
                root,
                "switch",
                "2026-06-07-session",
                "--session",
                env={"PWF_SESSION_ID": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), "2026-06-07-workspace\n")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding = root / ".planning" / "session-bindings" / f"{key}.json"
            self.assertTrue(binding.is_file())
            self.assertEqual(json.loads(binding.read_text(encoding="utf-8"))["plan_id"], "2026-06-07-session")
            self.assertIn(f"session binding set: {key} -> 2026-06-07-session", result.stdout)

    def test_switch_clear_session_removes_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text('{"version": 1}', encoding="utf-8")

            result = run_plan(root, "switch", "--clear-session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((binding_dir / f"{key}.json").exists())
            self.assertIn(f"session binding cleared: {key}", result.stdout)

    def test_init_bind_session_no_workspace_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(
                root,
                "init",
                "Side Task",
                "--bind-session",
                "--no-workspace-active",
                env={"PWF_SESSION_ID": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-side-task"
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            self.assertFalse((root / ".planning" / ".active_plan").exists())
            self.assertEqual(
                json.loads((root / ".planning" / "session-bindings" / f"{key}.json").read_text(encoding="utf-8"))["plan_id"],
                plan_id,
            )
            self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)

    def test_status_reports_workspace_session_and_effective_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root / ".planning" / "2026-06-07-workspace")
            write_plan(root / ".planning" / "2026-06-07-session")
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-session"}),
                encoding="utf-8",
            )

            result = run_plan(root, "status", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("workspace active plan: 2026-06-07-workspace", result.stdout)
            self.assertIn(f"session binding: {key} -> 2026-06-07-session", result.stdout)
            self.assertIn("effective plan: 2026-06-07-session", result.stdout)
            self.assertIn("plan source: session", result.stdout)
```

Add `import json` to `tests/test_plan_cli.py`.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_switch_session_writes_binding_without_changing_workspace_active tests.test_plan_cli.PlanCliTests.test_switch_clear_session_removes_binding tests.test_plan_cli.PlanCliTests.test_init_bind_session_no_workspace_active tests.test_plan_cli.PlanCliTests.test_status_reports_workspace_session_and_effective_plan -v
```

Expected: `argparse` rejects the new flags or output lacks session binding lines.

- [ ] **Step 3: Add binding helpers in `plan.py`**

Add these helpers near `_attached_session_count`:

```python
def _current_session_id() -> str | None:
    return os.environ.get("PWF_SESSION_ID", "").strip() or None


def _binding_payload(session_id: str, plan_id: str, source: str) -> dict[str, object]:
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return {
        "version": 1,
        "session_id": session_id,
        "plan_id": plan_id,
        "created_at": now,
        "updated_at": now,
        "source": source,
    }


def _write_session_binding(root: Path, session_id: str, plan_id: str, source: str) -> str:
    key = planning_state.session_key(session_id)
    binding_dir = root / ".planning" / "session-bindings"
    binding_dir.mkdir(parents=True, exist_ok=True)
    target = binding_dir / f"{key}.json"
    tmp = binding_dir / f"{key}.json.tmp"
    tmp.write_text(
        json.dumps(_binding_payload(session_id, plan_id, source), ensure_ascii=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(target)
    return key


def _clear_session_binding(root: Path, session_id: str) -> str:
    key = planning_state.session_key(session_id)
    binding = root / ".planning" / "session-bindings" / f"{key}.json"
    if binding.exists():
        binding.unlink()
    return key


def _workspace_active_plan_id(root: Path) -> str | None:
    active_file = root / ".planning" / ".active_plan"
    if not active_file.is_file():
        return None
    value = active_file.read_text(encoding="utf-8", errors="replace").strip()
    return value or None
```

- [ ] **Step 4: Add CLI messages**

In `CLI_MESSAGES["en"]`, add:

```python
        "effective_plan": "effective plan: {plan_id}",
        "missing_session_id": "session id: unavailable; set PWF_SESSION_ID or run from a hook payload",
        "plan_source": "plan source: {source}",
        "session_binding": "session binding: {key} -> {plan_id}",
        "session_binding_cleared": "session binding cleared: {key}",
        "session_binding_missing": "session binding: unavailable (no session_id)",
        "session_binding_none": "session binding: none for current session",
        "session_binding_set": "session binding set: {key} -> {plan_id}",
        "workspace_active_plan": "workspace active plan: {plan_id}",
        "workspace_active_plan_missing": "workspace active plan: missing",
```

Add matching `zh-CN` strings that keep field names readable and stable:

```python
        "effective_plan": "effective plan: {plan_id}",
        "missing_session_id": "session id: 不可用；请设置 PWF_SESSION_ID 或从 hook payload 运行",
        "plan_source": "plan source: {source}",
        "session_binding": "session binding: {key} -> {plan_id}",
        "session_binding_cleared": "session binding cleared: {key}",
        "session_binding_missing": "session binding: unavailable (no session_id)",
        "session_binding_none": "session binding: none for current session",
        "session_binding_set": "session binding set: {key} -> {plan_id}",
        "workspace_active_plan": "workspace active plan: {plan_id}",
        "workspace_active_plan_missing": "workspace active plan: missing",
```

- [ ] **Step 5: Extend `init` behavior**

Change signature:

```python
def init(
    root: Path,
    name: str,
    legacy: bool = False,
    force: bool = False,
    bind_session: bool = False,
    workspace_active: bool = True,
) -> int:
```

Replace the active plan write block with:

```python
    if not legacy and workspace_active:
        active_file = root / ".planning" / ".active_plan"
        active_file.parent.mkdir(parents=True, exist_ok=True)
        active_file.write_text(plan_id, encoding="utf-8")

    print(_message("created", label=label, plan_id=plan_id))
    print(_message("path", path=target))

    if bind_session:
        session_id = _current_session_id()
        if not session_id:
            print(_message("missing_session_id"))
            return 1
        key = _write_session_binding(root, session_id, plan_id, "plan.py init --bind-session")
        print(_message("session_binding_set", key=key, plan_id=plan_id))
```

- [ ] **Step 6: Extend `switch` behavior**

Change signature:

```python
def switch(
    root: Path,
    plan_id: str | None,
    session: bool = False,
    workspace: bool = False,
    clear_session: bool = False,
) -> int:
```

At the top of `switch`, add:

```python
    if clear_session:
        session_id = _current_session_id()
        if not session_id:
            print(_message("missing_session_id"))
            return 1
        key = _clear_session_binding(root, session_id)
        print(_message("session_binding_cleared", key=key))
        return 0
```

After plan existence validation, branch writes:

```python
    if session:
        session_id = _current_session_id()
        if not session_id:
            print(_message("missing_session_id"))
            return 1
        key = _write_session_binding(root, session_id, plan_id, "plan.py switch --session")
        print(_message("session_binding_set", key=key, plan_id=plan_id))
        print(_message("path", path=plan_dir))
        return 0

    active_file.parent.mkdir(parents=True, exist_ok=True)
    active_file.write_text(plan_id, encoding="utf-8")
```

`workspace` flag is explicit documentation of default behavior. It does not need separate logic unless `session` is also set; argparse will make them mutually exclusive.

- [ ] **Step 7: Update `status` output**

At the top of `status(root)`, compute resolution:

```python
    session_id = _current_session_id()
    resolution = planning_state.resolve_planning_context(root, session_id=session_id)
    paths = resolution.paths if resolution is not None else None
```

Before the existing `active plan` line, print workspace/session/effective state:

```python
    workspace_plan = _workspace_active_plan_id(root)
    print(
        _message("workspace_active_plan", plan_id=workspace_plan)
        if workspace_plan
        else _message("workspace_active_plan_missing")
    )
    if session_id:
        key = planning_state.session_key(session_id)
        if resolution is not None and resolution.source == "session":
            print(_message("session_binding", key=key, plan_id=resolution.plan_id))
        else:
            print(_message("session_binding_none"))
    else:
        print(_message("session_binding_missing"))
    if resolution is not None:
        print(_message("effective_plan", plan_id=resolution.plan_id))
        print(_message("plan_source", source=resolution.source))
```

- [ ] **Step 8: Add argparse flags**

In `main()`, extend parsers:

```python
    init_parser.add_argument("--bind-session", action="store_true")
    init_parser.add_argument("--no-workspace-active", action="store_true")

    switch_group = switch_parser.add_mutually_exclusive_group()
    switch_group.add_argument("--session", action="store_true")
    switch_group.add_argument("--workspace", action="store_true")
    switch_group.add_argument("--clear-session", action="store_true")
```

Update dispatch:

```python
    if args.command == "init":
        return init(
            root,
            args.name,
            legacy=args.legacy,
            force=args.force,
            bind_session=args.bind_session,
            workspace_active=not args.no_workspace_active,
        )
    if args.command == "switch":
        return switch(
            root,
            args.plan_id,
            session=args.session,
            workspace=args.workspace,
            clear_session=args.clear_session,
        )
```

- [ ] **Step 9: Run CLI tests**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_switch_session_writes_binding_without_changing_workspace_active tests.test_plan_cli.PlanCliTests.test_switch_clear_session_removes_binding tests.test_plan_cli.PlanCliTests.test_init_bind_session_no_workspace_active tests.test_plan_cli.PlanCliTests.test_status_reports_workspace_session_and_effective_plan -v
```

Expected: all four tests pass.

- [ ] **Step 10: Run full CLI regression**

Run:

```powershell
python -m unittest tests.test_plan_cli -v
```

Expected: all `tests.test_plan_cli` tests pass.

- [ ] **Step 11: Commit Task 4**

Run:

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_cli.py
git commit -m "feat: add session binding cli commands"
```

## Task 5: Session Lease and Task Ownership Gate

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Modify: `.codex/hooks/session_start.py`
- Modify: `.codex/hooks/user_prompt_submit.py`
- Modify: `.codex/hooks/pre_tool_use.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_hooks.py`
- Test: `tests/test_plan_cli.py`
- Test: `tests/test_plan_doctor.py`

- [ ] **Step 1: Add failing hook ownership tests**

Add these tests to `HookTests`:

```python
    def write_task_lease(self, root, plan_id, owner_session_id, *, heartbeat_at="2026-06-07T10:00:00Z", shared=False):
        owner_key = PLANNING_STATE.session_key(owner_session_id)
        plan_dir = root / ".planning" / plan_id
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / ".task-lease.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "plan_id": plan_id,
                    "owner_session_key": owner_key,
                    "owner_status": "active",
                    "shared": shared,
                    "claimed_at": "2026-06-07T10:00:00Z",
                    "updated_at": heartbeat_at,
                    "source": "test",
                }
            ),
            encoding="utf-8",
        )
        return owner_key

    def test_session_start_refreshes_session_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            result = run_hook(
                "session_start.py",
                root,
                {"hook_event_name": "SessionStart", "session_id": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            key = PLANNING_STATE.session_key("session-a")
            lease = root / ".planning" / "session-leases" / f"{key}.json"
            self.assertTrue(lease.is_file())
            payload = json.loads(lease.read_text(encoding="utf-8"))
            self.assertEqual(payload["session_key"], key)
            self.assertEqual(payload["status"], "active")
            self.assertIn("heartbeat_at", payload)

    def test_unbound_workspace_fallback_denies_task_owned_by_other_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-owned"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
            owner_key = self.write_task_lease(root, plan_id, "session-a")

            prompt = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-b"},
            )
            post = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/conflict.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-b",
                },
            )

            self.assertEqual(prompt.returncode, 0, prompt.stderr)
            self.assertEqual(post.returncode, 0, post.stderr)
            self.assertIn("owned by another session", json.loads(prompt.stdout)["systemMessage"])
            self.assertIn(owner_key, prompt.stdout)
            self.assertNotIn("additionalContext", prompt.stdout)
            self.assertIn("owned by another session", json.loads(post.stdout)["systemMessage"])
            self.assertNotIn("src/conflict.py", (plan_dir / "progress.md").read_text(encoding="utf-8"))

    def test_stale_owner_still_blocks_workspace_takeover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-stale"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
            self.write_task_lease(root, plan_id, "session-a", heartbeat_at="2000-01-01T00:00:00Z")

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-b"},
                env={"PWF_SESSION_LEASE_TTL_SECONDS": "600"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            message = json.loads(result.stdout)["systemMessage"]
            self.assertIn("owned by another session", message)
            self.assertIn("stale", message)
            self.assertNotIn("additionalContext", result.stdout)

    def test_shared_task_lease_allows_second_session_and_records_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-shared"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
            self.write_task_lease(root, plan_id, "session-a", shared=True)

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/shared.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-b",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("src/shared.py", progress)
            self.assertIn(f"- Session: {PLANNING_STATE.session_key('session-b')}", progress)
```

- [ ] **Step 2: Add failing CLI and doctor lease tests**

Add these tests to `PlanCliTests`:

```python
    def test_switch_session_creates_task_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-session"
            write_plan(root / ".planning" / plan_id)

            result = run_plan(root, "switch", plan_id, "--session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_session_key"], key)
            self.assertFalse(lease["shared"])
            self.assertIn(f"task lease: owner={key} status=active shared=false", result.stdout)

    def test_switch_session_requires_force_claim_for_owned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-owned"
            write_plan(root / ".planning" / plan_id)
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": owner_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "switch", plan_id, "--session", env={"PWF_SESSION_ID": "session-b"})

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("owned by another session", result.stdout)
            self.assertIn("--force-claim", result.stdout)

    def test_switch_session_force_claim_transfers_task_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-claim"
            write_plan(root / ".planning" / plan_id)
            old_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            new_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": old_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(
                root,
                "switch",
                plan_id,
                "--session",
                "--force-claim",
                env={"PWF_SESSION_ID": "session-b"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_session_key"], new_key)
            self.assertIn(f"task lease: owner={new_key} status=active shared=false", result.stdout)

    def test_switch_session_share_marks_task_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-share"
            write_plan(root / ".planning" / plan_id)

            result = run_plan(root, "switch", plan_id, "--session", "--share", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertTrue(lease["shared"])
            self.assertIn("shared=true", result.stdout)

    def test_switch_release_session_releases_owned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-release"
            write_plan(root / ".planning" / plan_id)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": plan_id}),
                encoding="utf-8",
            )
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "switch", "--release-session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((binding_dir / f"{key}.json").exists())
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_status"], "released")
            self.assertIn(f"task lease released: {key} -> {plan_id}", result.stdout)

    def test_status_reports_session_and_task_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-status"
            write_plan(root / ".planning" / plan_id)
            (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": plan_id}),
                encoding="utf-8",
            )
            lease_dir = root / ".planning" / "session-leases"
            lease_dir.mkdir(parents=True)
            (lease_dir / f"{key}.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "session_key": key,
                        "session_id": "session-a",
                        "started_at": "2026-06-07T10:00:00Z",
                        "heartbeat_at": "2026-06-07T10:00:00Z",
                        "status": "active",
                        "bound_plan_id": plan_id,
                    }
                ),
                encoding="utf-8",
            )
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "status", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"session lease: active {key}", result.stdout)
            self.assertIn(f"task lease: owner={key} status=active shared=false", result.stdout)
```

Add this test to `PlanDoctorTests`:

```python
    def test_doctor_reports_workspace_active_task_owned_by_another_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            (plan_dir / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_dir.name,
                        "owner_session_key": owner_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "doctor", env={"PWF_SESSION_ID": "session-b"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"task lease: conflict owner={owner_key} status=active shared=false", result.stdout)
            self.assertIn("workspace active plan is owned by another session", result.stdout)
```

- [ ] **Step 3: Run lease tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_session_start_refreshes_session_lease tests.test_hooks.HookTests.test_unbound_workspace_fallback_denies_task_owned_by_other_session tests.test_hooks.HookTests.test_stale_owner_still_blocks_workspace_takeover tests.test_hooks.HookTests.test_shared_task_lease_allows_second_session_and_records_session tests.test_plan_cli.PlanCliTests.test_switch_session_creates_task_lease tests.test_plan_cli.PlanCliTests.test_switch_session_requires_force_claim_for_owned_task tests.test_plan_cli.PlanCliTests.test_switch_session_force_claim_transfers_task_lease tests.test_plan_cli.PlanCliTests.test_switch_session_share_marks_task_shared tests.test_plan_cli.PlanCliTests.test_switch_release_session_releases_owned_task tests.test_plan_cli.PlanCliTests.test_status_reports_session_and_task_lease tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_workspace_active_task_owned_by_another_session -v
```

Expected: hook tests fail because lease helpers and ownership denial do not exist; CLI tests fail because new flags and task lease output do not exist.

- [ ] **Step 4: Add lease dataclasses and path helpers**

In `.codex/hooks/planning_state.py`, add after `PlanResolution`:

```python
@dataclass(frozen=True)
class SessionLease:
    session_key: str
    session_id: str
    status: str
    started_at: str
    heartbeat_at: str
    bound_plan_id: str | None = None


@dataclass(frozen=True)
class TaskLease:
    plan_id: str
    owner_session_key: str
    owner_status: str
    shared: bool
    claimed_at: str
    updated_at: str


@dataclass(frozen=True)
class PlanningAccess:
    resolution: PlanResolution | None
    allowed: bool = True
    warning: str | None = None
```

Add helpers near the session binding helpers:

```python
LEASE_STATUSES = {"active", "stale", "released", "shared"}
DEFAULT_SESSION_LEASE_TTL_SECONDS = 600


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _session_leases_dir(root: Path) -> Path:
    return root / ".planning" / "session-leases"


def session_lease_path(root: Path, session_id: str) -> Path:
    return _session_leases_dir(root) / f"{session_key(session_id)}.json"


def task_lease_path(root: Path, plan_id: str) -> Path:
    return root / ".planning" / plan_id / ".task-lease.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)
```

- [ ] **Step 5: Add session lease refresh and task lease readers**

In `.codex/hooks/planning_state.py`, add:

```python
def session_lease_ttl_seconds(env: Mapping[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    raw = source.get("PWF_SESSION_LEASE_TTL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SESSION_LEASE_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SESSION_LEASE_TTL_SECONDS
    return value if value >= 1 else DEFAULT_SESSION_LEASE_TTL_SECONDS


def refresh_session_lease(
    root: Path,
    session_id: str | None,
    bound_plan_id: str | None = None,
    source: str = "hook",
) -> str | None:
    if not session_id:
        return None
    key = session_key(session_id)
    now = _utc_now()
    path = session_lease_path(root, session_id)
    started_at = now
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(existing, dict) and isinstance(existing.get("started_at"), str):
                started_at = existing["started_at"]
        except (OSError, json.JSONDecodeError):
            started_at = now
    _atomic_write_json(
        path,
        {
            "version": 1,
            "session_key": key,
            "session_id": session_id,
            "started_at": started_at,
            "heartbeat_at": now,
            "status": "active",
            "bound_plan_id": bound_plan_id,
            "source": source,
        },
    )
    return key


def read_task_lease(root: Path, plan_id: str) -> TaskLease | None:
    if not valid_plan_id(plan_id):
        return None
    path = task_lease_path(root, plan_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    if payload.get("plan_id") != plan_id:
        return None
    owner = payload.get("owner_session_key")
    status = payload.get("owner_status")
    shared = payload.get("shared")
    claimed_at = payload.get("claimed_at")
    updated_at = payload.get("updated_at")
    if not isinstance(owner, str) or not re.fullmatch(r"[0-9a-f]{12}", owner):
        return None
    if not isinstance(status, str) or status not in LEASE_STATUSES:
        return None
    if not isinstance(shared, bool):
        return None
    if not isinstance(claimed_at, str) or not isinstance(updated_at, str):
        return None
    return TaskLease(plan_id, owner, status, shared, claimed_at, updated_at)
```

- [ ] **Step 6: Add stale calculation and ownership gate**

In `.codex/hooks/planning_state.py`, add:

```python
def _parse_iso_z(value: str) -> datetime | None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except ValueError:
        return None


def task_lease_status(lease: TaskLease, env: Mapping[str, str] | None = None) -> str:
    if lease.shared:
        return "shared"
    if lease.owner_status == "released":
        return "released"
    updated = _parse_iso_z(lease.updated_at)
    if updated is None:
        return "stale"
    age = (datetime.utcnow() - updated).total_seconds()
    return "stale" if age > session_lease_ttl_seconds(env) else "active"


def ownership_denial_for_resolution(
    root: Path,
    resolution: PlanResolution,
    session_id: str | None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    if resolution.source == "env":
        return None
    lease = read_task_lease(root, resolution.plan_id)
    if lease is None:
        return None
    status = task_lease_status(lease, env)
    if lease.shared or status == "released":
        return None
    current_key = session_key(session_id) if session_id else None
    if current_key and current_key == lease.owner_session_key:
        return None
    return (
        "[planning-with-files] workspace active plan is owned by another session; "
        f"owner={lease.owner_session_key} status={status} shared=false. "
        "Bind this session with plan.py switch <plan-id> --session, create a new task "
        "with plan.py init \"Task Name\" --bind-session, or use --force-claim only "
        "when you mean to take ownership."
    )


def resolve_planning_access(
    root: Path,
    env: Mapping[str, str] | None = None,
    session_id: str | None = None,
) -> PlanningAccess:
    resolution = resolve_planning_context(root, env=env, session_id=session_id)
    refresh_session_lease(
        root,
        session_id,
        bound_plan_id=resolution.plan_id if resolution is not None and resolution.source == "session" else None,
    )
    if resolution is None:
        return PlanningAccess(None)
    denial = ownership_denial_for_resolution(root, resolution, session_id, env)
    if denial:
        return PlanningAccess(resolution, allowed=False, warning=denial)
    return PlanningAccess(resolution)
```

Update `planning_paths(root, session_id=None)` to call `resolve_planning_access`; return `None` when `allowed` is `False`.

- [ ] **Step 7: Route hook denial diagnostics through the ownership gate**

Add to `.codex/hooks/planning_state.py`:

```python
def planning_access_denial(root: Path, session_id: str | None = None) -> str | None:
    access = resolve_planning_access(root, session_id=session_id)
    return access.warning if not access.allowed else None
```

In `user_prompt_submit.py` and `pre_tool_use.py`, after strict-session denial and before rendering context, add:

```python
    ownership_denial = planning_state.planning_access_denial(root, session_id)
    if ownership_denial:
        adapter.emit_json({"systemMessage": ownership_denial})
        return
```

In `session_start.py`, after reading `session_id`, call:

```python
    planning_state.refresh_session_lease(root, session_id)
```

In `post_tool_use.py`, the progress-lock task later converts append results to a warning object. For this task, add a guard before append:

```python
    ownership_denial = planning_state.planning_access_denial(root, session_id)
    if ownership_denial:
        adapter.emit_json({"systemMessage": ownership_denial})
        return
```

When the progress-lock task changes `append_progress` to return `ProgressAppendResult`, keep this denial path so the hook does not write conflicting records.

- [ ] **Step 8: Add task lease claim/release helpers for CLI**

In `.codex/hooks/planning_state.py`, add:

```python
def write_task_lease(
    root: Path,
    plan_id: str,
    owner_session_key: str,
    *,
    shared: bool = False,
    owner_status: str = "active",
    source: str = "plan.py",
) -> TaskLease:
    now = _utc_now()
    existing = read_task_lease(root, plan_id)
    claimed_at = existing.claimed_at if existing and existing.owner_session_key == owner_session_key else now
    payload = {
        "version": 1,
        "plan_id": plan_id,
        "owner_session_key": owner_session_key,
        "owner_status": owner_status,
        "shared": shared,
        "claimed_at": claimed_at,
        "updated_at": now,
        "source": source,
    }
    _atomic_write_json(task_lease_path(root, plan_id), payload)
    return TaskLease(plan_id, owner_session_key, owner_status, shared, claimed_at, now)


def claim_task_lease(
    root: Path,
    plan_id: str,
    session_id: str,
    *,
    force: bool = False,
    share: bool = False,
    source: str = "plan.py switch --session",
) -> tuple[TaskLease, str | None]:
    current_key = session_key(session_id)
    existing = read_task_lease(root, plan_id)
    if existing:
        status = task_lease_status(existing)
        conflict = (
            existing.owner_session_key != current_key
            and not existing.shared
            and status != "released"
        )
        if conflict and not force:
            return existing, (
                f"task is owned by another session: owner={existing.owner_session_key} "
                f"status={status} shared=false; rerun with --force-claim if you mean to take ownership."
            )
    lease = write_task_lease(root, plan_id, current_key, shared=share, source=source)
    refresh_session_lease(root, session_id, bound_plan_id=plan_id, source=source)
    return lease, None


def release_task_lease_for_session(root: Path, plan_id: str, session_id: str) -> TaskLease | None:
    existing = read_task_lease(root, plan_id)
    if existing is None:
        return None
    current_key = session_key(session_id)
    if existing.owner_session_key != current_key:
        return existing
    return write_task_lease(
        root,
        plan_id,
        current_key,
        shared=False,
        owner_status="released",
        source="plan.py switch --release-session",
    )
```

- [ ] **Step 9: Extend `plan.py switch` for ownership operations**

Extend the `switch` signature:

```python
def switch(
    root: Path,
    plan_id: str | None,
    session: bool = False,
    workspace: bool = False,
    clear_session: bool = False,
    release_session: bool = False,
    force_claim: bool = False,
    share: bool = False,
) -> int:
```

Add CLI messages in both `en` and `zh-CN`:

```python
        "session_released": "session binding released: {key}",
        "task_lease": "task lease: owner={owner} status={status} shared={shared}",
        "task_lease_conflict": "task is owned by another session: owner={owner} status={status} shared=false; rerun with --force-claim if you mean to take ownership.",
        "task_lease_released": "task lease released: {key} -> {plan_id}",
```

At the top of `switch`, handle release:

```python
    if release_session:
        session_id = _current_session_id()
        if not session_id:
            print(_message("missing_session_id"))
            return 1
        key = planning_state.session_key(session_id)
        bound_plan_id = _read_session_binding_plan_id(root, session_id)
        _clear_session_binding(root, session_id)
        print(_message("session_released", key=key))
        if bound_plan_id:
            lease = planning_state.release_task_lease_for_session(root, bound_plan_id, session_id)
            if lease and lease.owner_session_key == key:
                print(_message("task_lease_released", key=key, plan_id=bound_plan_id))
        return 0
```

Add helper in `plan.py`:

```python
def _read_session_binding_plan_id(root: Path, session_id: str) -> str | None:
    key = planning_state.session_key(session_id)
    binding = root / ".planning" / "session-bindings" / f"{key}.json"
    if not binding.is_file():
        return None
    try:
        payload = json.loads(binding.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    plan_id = payload.get("plan_id") if isinstance(payload, dict) else None
    return plan_id if isinstance(plan_id, str) and planning_state.valid_plan_id(plan_id) else None
```

Inside the `if session:` branch, claim the task lease before writing the binding:

```python
        lease, conflict = planning_state.claim_task_lease(
            root,
            plan_id,
            session_id,
            force=force_claim,
            share=share,
            source="plan.py switch --session",
        )
        if conflict:
            status = planning_state.task_lease_status(lease)
            print(_message("task_lease_conflict", owner=lease.owner_session_key, status=status))
            return 1
        key = _write_session_binding(root, session_id, plan_id, "plan.py switch --session")
        status = planning_state.task_lease_status(lease)
        print(_message("session_binding_set", key=key, plan_id=plan_id))
        print(_message("task_lease", owner=lease.owner_session_key, status=status, shared=str(lease.shared).lower()))
        print(_message("path", path=plan_dir))
        return 0
```

Extend argparse:

```python
    switch_group.add_argument("--release-session", action="store_true")
    switch_parser.add_argument("--force-claim", action="store_true")
    switch_parser.add_argument("--share", action="store_true")
```

Pass the new flags in dispatch.

- [ ] **Step 10: Add status and doctor lease diagnostics**

In `.codex/skills/planning-with-files/scripts/plan.py`, add:

```python
def _task_lease_line(root: Path, plan_id: str | None, session_id: str | None = None) -> str | None:
    if not plan_id:
        return None
    lease = planning_state.read_task_lease(root, plan_id)
    if lease is None:
        return "task lease: none"
    status = planning_state.task_lease_status(lease)
    shared = str(lease.shared).lower()
    current_key = planning_state.session_key(session_id) if session_id else None
    if current_key and lease.owner_session_key != current_key and not lease.shared and status != "released":
        return f"task lease: conflict owner={lease.owner_session_key} status={status} shared={shared}"
    return f"task lease: owner={lease.owner_session_key} status={status} shared={shared}"
```

In `status(root)`, after effective plan output:

```python
    if session_id:
        key = planning_state.session_key(session_id)
        lease_path = planning_state.session_lease_path(root, session_id)
        print(f"session lease: {'active ' + key if lease_path.is_file() else 'missing ' + key}")
    else:
        print("session lease: unavailable (no session_id)")
    task_line = _task_lease_line(root, resolution.plan_id if resolution else workspace_plan, session_id)
    if task_line:
        print(task_line)
```

In `doctor(root)`, append the same task lease line and warning:

```python
    task_line = _task_lease_line(root, paths.root.name if paths and paths.root.parent.name == ".planning" else None, _current_session_id())
    if task_line:
        lines.append(task_line)
        if task_line.startswith("task lease: conflict"):
            lines.append("[warn] workspace active plan is owned by another session; bind this session with plan.py switch <plan-id> --session or create a new task with plan.py init \"Task Name\" --bind-session")
```

- [ ] **Step 11: Run lease tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_session_start_refreshes_session_lease tests.test_hooks.HookTests.test_unbound_workspace_fallback_denies_task_owned_by_other_session tests.test_hooks.HookTests.test_stale_owner_still_blocks_workspace_takeover tests.test_hooks.HookTests.test_shared_task_lease_allows_second_session_and_records_session tests.test_plan_cli.PlanCliTests.test_switch_session_creates_task_lease tests.test_plan_cli.PlanCliTests.test_switch_session_requires_force_claim_for_owned_task tests.test_plan_cli.PlanCliTests.test_switch_session_force_claim_transfers_task_lease tests.test_plan_cli.PlanCliTests.test_switch_session_share_marks_task_shared tests.test_plan_cli.PlanCliTests.test_switch_release_session_releases_owned_task tests.test_plan_cli.PlanCliTests.test_status_reports_session_and_task_lease tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_workspace_active_task_owned_by_another_session -v
```

Expected: all lease and ownership tests pass.

- [ ] **Step 12: Run resolver, hook, CLI, and doctor regressions**

Run:

```powershell
python -m unittest tests.test_hooks.PlanResolutionTests tests.test_hooks.HookTests.test_user_prompt_submit_uses_session_bound_plan tests.test_hooks.HookTests.test_post_tool_use_writes_to_session_bound_progress tests.test_plan_cli tests.test_plan_doctor -v
```

Expected: all selected tests pass; legacy workspace behavior remains covered by existing CLI and doctor tests.

- [ ] **Step 13: Commit Task 5**

Run:

```powershell
git add .codex/hooks/planning_state.py .codex/hooks/codex_hook_adapter.py .codex/hooks/session_start.py .codex/hooks/user_prompt_submit.py .codex/hooks/pre_tool_use.py .codex/hooks/post_tool_use.py .codex/skills/planning-with-files/scripts/plan.py tests/test_hooks.py tests/test_plan_cli.py tests/test_plan_doctor.py
git commit -m "feat: prevent automatic task takeover"
```

## Task 6: Strict Binding Enforcement

**Files:**
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_hooks.py`
- Test: `tests/test_plan_doctor.py`

- [ ] **Step 1: Add failing strict enforcement tests**

Add these tests to `HookTests`:

```python
    def test_strict_attached_unbound_session_falls_back_without_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            sessions = root / ".planning" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "session-a.attached").write_text("attached\n", encoding="utf-8")

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
                env={"PWF_SESSION_MODE": "strict"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("additionalContext", result.stdout)

    def test_strict_requires_binding_rejects_attached_unbound_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            sessions = root / ".planning" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "session-a.attached").write_text("attached\n", encoding="utf-8")

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue", "session_id": "session-a"},
                env={"PWF_SESSION_MODE": "strict", "PWF_STRICT_REQUIRES_BINDING": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            message = json.loads(result.stdout)["systemMessage"]
            self.assertIn("requires a session plan binding", message)
            self.assertNotIn("additionalContext", result.stdout)
```

Add this test to `PlanDoctorTests`:

```python
    def test_doctor_reports_strict_binding_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(
                root,
                "doctor",
                env={"PWF_SESSION_MODE": "strict", "PWF_STRICT_REQUIRES_BINDING": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session binding required: yes", result.stdout)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_strict_attached_unbound_session_falls_back_without_enforcement tests.test_hooks.HookTests.test_strict_requires_binding_rejects_attached_unbound_session tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_strict_binding_enforcement -v
```

Expected: the enforcement test fails because strict mode only checks attached sessions today.

- [ ] **Step 3: Add policy helpers**

In `.codex/hooks/codex_hook_adapter.py`, add:

```python
def _session_policy(root: Path) -> dict[str, Any]:
    policy = _session_policy_path(root)
    if not policy.is_file():
        return {}
    try:
        payload = json.loads(policy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def strict_requires_binding(root: Path) -> bool:
    env_value = os.environ.get("PWF_STRICT_REQUIRES_BINDING", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False
    policy_value = _session_policy(root).get("require_binding")
    return policy_value is True
```

Update `_session_mode_from_policy_file` to call `_session_policy(root)` instead of parsing the file a second time.

- [ ] **Step 4: Add binding existence helper**

In `.codex/hooks/planning_state.py`, add:

```python
def session_has_valid_binding(root: Path, session_id: str) -> bool:
    resolution = resolve_planning_context(root, env={}, session_id=session_id)
    return resolution is not None and resolution.source == "session"
```

- [ ] **Step 5: Enforce binding in strict mode**

In `codex_hook_adapter.py`, import `planning_state` with the same local import style used by hook scripts:

```python
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

import planning_state  # noqa: E402
```

Update `is_session_attached`:

```python
def is_session_attached(root: Path, session_id: str | None) -> bool:
    if session_mode(root) != "strict":
        return True

    sessions_dir = root / ".planning" / "sessions"
    if not session_id:
        return False
    if not (sessions_dir / f"{session_id}.attached").exists():
        return False
    if strict_requires_binding(root):
        return planning_state.session_has_valid_binding(root, session_id)
    return True
```

Update `session_denial_message`:

```python
    if session_id and strict_requires_binding(root):
        return (
            "[planning-with-files] session isolation is strict and requires a "
            "session plan binding; planning context was not injected."
        )
```

Place this branch after the missing `session_id` check and before the generic unattached message.

- [ ] **Step 6: Report enforcement in doctor**

In `plan.py`, add an English CLI message:

```python
        "session_binding_required": "session binding required: {value}",
```

Add the same stable ASCII line in `zh-CN`:

```python
        "session_binding_required": "session binding required: {value}",
```

In `_session_status_lines`, append:

```python
    if mode == "strict":
        required = "yes" if codex_hook_adapter.strict_requires_binding(root) else "no"
        lines.append(_message("session_binding_required", value=required))
```

- [ ] **Step 7: Run strict tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_strict_attached_unbound_session_falls_back_without_enforcement tests.test_hooks.HookTests.test_strict_requires_binding_rejects_attached_unbound_session tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_strict_binding_enforcement -v
```

Expected: all three tests pass.

- [ ] **Step 8: Run policy regression tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_hooks_are_silent_without_plan tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_strict_session_mode_from_env tests.test_plan_doctor.PlanDoctorTests.test_doctor_warns_about_unsupported_session_mode -v
```

Expected: all three tests pass.

- [ ] **Step 9: Commit Task 6**

Run:

```powershell
git add .codex/hooks/codex_hook_adapter.py .codex/hooks/planning_state.py .codex/skills/planning-with-files/scripts/plan.py tests/test_hooks.py tests/test_plan_doctor.py
git commit -m "feat: enforce strict session plan bindings"
```

## Task 7: Progress Lock and Source Metadata

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Test: `tests/test_hooks.py`
- Test: `tests/test_progress_compaction.py`

- [ ] **Step 1: Add failing metadata and lock tests**

Add these tests to `HookTests`:

```python
    def test_post_tool_use_records_session_and_plan_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-06-07-bound"
            write_plan(plan_dir)
            key = PLANNING_STATE.session_key("session-a")
            bindings = root / ".planning" / "session-bindings"
            bindings.mkdir(parents=True, exist_ok=True)
            (bindings / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-bound"}),
                encoding="utf-8",
            )

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/metadata.py"},
                    "tool_response": {"success": True},
                    "session_id": "session-a",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn(f"- Session: {key}", progress)
            self.assertIn("- Plan-Source: session", progress)

    def test_post_tool_use_reports_lock_timeout_without_corrupting_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)
            (root / ".progress.lock").write_text("held\n", encoding="utf-8")
            before = (root / "progress.md").read_text(encoding="utf-8")

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/locked.py"},
                    "tool_response": {"success": True},
                },
                env={"PWF_PROGRESS_LOCK_TIMEOUT_MS": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            message = json.loads(result.stdout)["systemMessage"]
            self.assertIn("progress.md lock timed out", message)
            self.assertEqual((root / "progress.md").read_text(encoding="utf-8"), before)
```

Add this test to `ProgressCompactionTests`:

```python
    def test_extract_recent_progress_context_preserves_session_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            progress.write_text(
                "\n".join(
                    [
                        "# Progress Log",
                        "",
                        "### Auto Record: 2026-06-07 10:00:00",
                        "- Tool: apply_patch",
                        "- Session: abcdef123456",
                        "- Plan-Source: session",
                        "- Files:",
                        "  - `src/current.py` (update)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            context = MODULE.extract_recent_progress_context(
                progress,
                record_limit=1,
                manual_tail_lines=0,
                max_chars=10000,
            )

            self.assertIn("- Session: abcdef123456", context)
            self.assertIn("- Plan-Source: session", context)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_post_tool_use_records_session_and_plan_source_metadata tests.test_hooks.HookTests.test_post_tool_use_reports_lock_timeout_without_corrupting_progress tests.test_progress_compaction.ProgressCompactionTests.test_extract_recent_progress_context_preserves_session_metadata -v
```

Expected: metadata and lock tests fail; compaction test may pass already, but keep it to protect future parser changes.

- [ ] **Step 3: Add append result and lock helpers**

In `planning_state.py`, add after `ChangedPath`:

```python
@dataclass(frozen=True)
class ProgressAppendResult:
    recorded: bool
    warning: str | None = None
```

Add lock helpers near `append_progress`:

```python
def progress_lock_timeout_seconds(env: Mapping[str, str] | None = None) -> float:
    source = env if env is not None else os.environ
    raw = source.get("PWF_PROGRESS_LOCK_TIMEOUT_MS", "250").strip()
    if not raw.isdigit():
        return 0.25
    return max(1, min(int(raw), 5000)) / 1000.0


class ProgressFileLock:
    def __init__(self, path: Path, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self) -> "ProgressFileLock":
        deadline = datetime.now().timestamp() + self.timeout
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii", errors="ignore"))
                return self
            except FileExistsError:
                if datetime.now().timestamp() >= deadline:
                    raise TimeoutError("progress.md lock timed out")
                time.sleep(0.02)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
```

Add `import time` near the top of the file.

- [ ] **Step 4: Return append result with metadata**

Change `append_progress` signature:

```python
def append_progress(
    root: Path,
    payload: dict[str, Any],
    session_id: str | None = None,
) -> ProgressAppendResult:
```

Replace `return False` with `return ProgressAppendResult(False)` in early exits.

Resolve once:

```python
    access = resolve_planning_access(root, session_id=session_id)
    if not access.allowed:
        return ProgressAppendResult(False, access.warning)
    if access.resolution is None:
        return ProgressAppendResult(False)
    resolution = access.resolution
    paths = resolution.paths
```

After `- Tool`, add:

```python
    session_label = session_key(session_id) if session_id else "unavailable"
    lines = [
        "",
        f"### Auto Record: {timestamp}",
        f"- Tool: {tool_name}",
        f"- Session: {session_label}",
        f"- Plan-Source: {resolution.source}",
    ]
```

Wrap physical append:

```python
    paths.progress.parent.mkdir(parents=True, exist_ok=True)
    lock_path = paths.progress.parent / ".progress.lock"
    try:
        with ProgressFileLock(lock_path, progress_lock_timeout_seconds()):
            with paths.progress.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines).rstrip() + "\n")
    except TimeoutError:
        return ProgressAppendResult(False, "[planning-with-files] progress.md lock timed out; auto record was skipped.")
    return ProgressAppendResult(True)
```

- [ ] **Step 5: Update `post_tool_use.py` for result object**

Replace the append block:

```python
    result = planning_state.append_progress(root, payload, session_id=session_id)
    if result.recorded or result.warning:
        parts = []
        if result.recorded:
            parts.append(planning_state.message("post_tool_recorded"))
            notice = planning_state.progress_compaction_notice(root, session_id=session_id)
            if notice:
                parts.append(notice)
        if result.warning:
            parts.append(result.warning)
        adapter.emit_json({"systemMessage": " ".join(parts)})
```

- [ ] **Step 6: Run metadata and lock tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_post_tool_use_records_session_and_plan_source_metadata tests.test_hooks.HookTests.test_post_tool_use_reports_lock_timeout_without_corrupting_progress tests.test_progress_compaction.ProgressCompactionTests.test_extract_recent_progress_context_preserves_session_metadata -v
```

Expected: all three tests pass.

- [ ] **Step 7: Run progress regression tests**

Run:

```powershell
python -m unittest tests.test_hooks.HookTests.test_post_tool_use_records_apply_patch_changed_files tests.test_hooks.HookTests.test_post_tool_use_warns_when_progress_hits_compact_threshold tests.test_progress_compaction -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 7**

Run:

```powershell
git add .codex/hooks/planning_state.py .codex/hooks/post_tool_use.py tests/test_hooks.py tests/test_progress_compaction.py
git commit -m "feat: lock progress writes and record plan source"
```

## Task 8: Documentation and Consistency Tests

**Files:**
- Modify: `.codex/skills/planning-with-files/SKILL.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py`

- [ ] **Step 1: Add failing documentation consistency test**

Add this test to `ProjectConsistencyTests`:

```python
    def test_docs_document_session_task_bindings(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        skill = read_text(".codex/skills/planning-with-files/SKILL.md")
        changelog = read_text("CHANGELOG.md")

        for text in (readme_cn, readme_en, faq, skill):
            self.assertIn("plan.py switch <plan-id> --session", text)
            self.assertIn("--force-claim", text)
            self.assertIn("--share", text)
            self.assertIn("--release-session", text)
            self.assertIn("plan.py init \"Task Name\" --bind-session", text)
            self.assertIn("PWF_STRICT_REQUIRES_BINDING=1", text)
            self.assertIn("Session", text)
            self.assertIn("Plan-Source", text)
            self.assertIn("stale", text)

        self.assertIn("session binding", changelog)
        self.assertIn("task ownership", changelog)
        self.assertIn("progress.md lock", changelog)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_session_task_bindings -v
```

Expected: test fails because docs do not yet mention session binding commands.

- [ ] **Step 3: Update Chinese README**

In `README.md`, update the active plan resolution list to:

```text
PLAN_ID 环境变量
当前 session binding
.planning/.active_plan
最新的 .planning/<plan-id>/task_plan.md
项目根目录 task_plan.md
```

Add a user workflow block under Session Policy:

````markdown
同一项目多对话并发时，请给每个对话绑定自己的任务：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

新建旁路任务时可以直接绑定当前 session：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session --no-workspace-active
```

`--session` 只写 `.planning/session-bindings/<session-key>.json`，不会修改 `.planning/.active_plan`。旧的 `plan.py switch <plan-id>` 仍然切换 workspace active plan。

如果 workspace active task 已经由另一个 session 拥有，新 session 不会自动接管，即使 owner stale 也一样。显式接管、共享和释放分别使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --force-claim
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --share
python .codex\skills\planning-with-files\scripts\plan.py switch --release-session
```

如果希望 strict mode 同时要求 session 已绑定任务，可设置：

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```
````

Update the auto record example:

```text
### Auto Record: 2026-05-11 20:35:47
- Tool: apply_patch
- Session: unavailable
- Plan-Source: workspace
- Files:
  - `.codex/hooks/planning_state.py` (update)
```

- [ ] **Step 4: Update English README**

In `README.en.md`, update the resolver order:

```text
PLAN_ID environment variable
current session binding
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

Add this block under Session Policy:

````markdown
When multiple Codex conversations work in the same project, bind each conversation to its own task:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

To create a side task and bind the current session immediately:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session --no-workspace-active
```

`--session` writes only `.planning/session-bindings/<session-key>.json`; it does not change `.planning/.active_plan`. The old `plan.py switch <plan-id>` behavior still switches the workspace active plan.

If the workspace active task is already owned by another session, a new session will not automatically take it over, even when the owner is stale. Explicit claim, sharing, and release use:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --force-claim
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --share
python .codex\skills\planning-with-files\scripts\plan.py switch --release-session
```

To make strict mode require a task binding as well as an attached session, set:

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```
````

Update the auto record example:

```text
### Auto Record: 2026-05-11 20:35:47
- Tool: apply_patch
- Session: unavailable
- Plan-Source: workspace
- Files:
  - `.codex/hooks/planning_state.py` (update)
```

- [ ] **Step 5: Update FAQ, skill doc, and changelog**

Add a FAQ entry:

````markdown
## 同一个项目里多个对话会不会混用 progress.md？

默认 workspace 模式仍然使用 `.planning/.active_plan`，适合单任务项目。如果同一项目同时开多个 Codex 对话，请为每个对话绑定自己的 PWF 任务：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

也可以在创建任务时绑定：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

绑定后，该对话的上下文注入和 `progress.md` 自动记录都会使用 session-bound plan。自动记录会包含 `Session` 和 `Plan-Source` 字段，便于审计。如果需要 strict mode 强制要求 binding，请设置 `PWF_STRICT_REQUIRES_BINDING=1`。

如果 workspace active task 已经由另一个 session 拥有，新的未绑定对话不会自动接管它；owner stale 也仍然需要显式选择。接管用 `--force-claim`，有意共享用 `--share`，释放当前 session 的 ownership 用 `--release-session`。
````

In `.codex/skills/planning-with-files/SKILL.md`, add the same terminal commands under Session Policy or Advanced Topics.

In `CHANGELOG.md` Unreleased section, add bilingual bullets mentioning session binding, strict binding enforcement, and progress lock:

```markdown
- 中文：新增 session binding，支持同一项目多 Codex 对话分别绑定不同 PWF 任务；`plan.py switch <plan-id> --session` 不修改 workspace active plan。
- 中文：新增 task ownership gate；未绑定 session 不会自动接管其他 session 拥有的任务，stale owner 也必须通过 `--force-claim`、`--share` 或 `--release-session` 显式处理。
- 中文：新增 `PWF_STRICT_REQUIRES_BINDING=1`，可让 strict mode 要求 session 已 attach 且已绑定有效任务。
- 中文：`progress.md` 自动记录新增 `Session` 和 `Plan-Source` 字段，并用短时 progress.md lock 保护 append 边界。
- English: Added session binding so multiple Codex conversations in one project can bind to different PWF tasks; `plan.py switch <plan-id> --session` leaves the workspace active plan unchanged.
- English: Added a task ownership gate so unbound sessions cannot automatically take over tasks owned by another session; stale owners require explicit `--force-claim`, `--share`, or `--release-session`.
- English: Added `PWF_STRICT_REQUIRES_BINDING=1` so strict mode can require both an attached session and a valid task binding.
- English: Added `Session` and `Plan-Source` metadata to automatic `progress.md` records and protected append boundaries with a short progress.md lock.
```

- [ ] **Step 6: Run documentation consistency test**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_session_task_bindings -v
```

Expected: test passes.

- [ ] **Step 7: Run project consistency regression**

Run:

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: all project consistency tests pass.

- [ ] **Step 8: Commit Task 8**

Run:

```powershell
git add .codex/skills/planning-with-files/SKILL.md README.md README.en.md docs/FAQ.md CHANGELOG.md tests/test_project_consistency.py
git commit -m "docs: document session task bindings"
```

## Task 9: Full Verification and Release Readiness

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run hook tests**

Run:

```powershell
python -m unittest tests.test_hooks -v
```

Expected: all hook tests pass.

- [ ] **Step 2: Run CLI and doctor tests**

Run:

```powershell
python -m unittest tests.test_plan_cli tests.test_plan_doctor -v
```

Expected: all CLI and doctor tests pass.

- [ ] **Step 3: Run progress and docs tests**

Run:

```powershell
python -m unittest tests.test_progress_compaction tests.test_project_consistency -v
```

Expected: all progress compaction and project consistency tests pass.

- [ ] **Step 4: Run full test suite**

Run:

```powershell
python -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 5: Check patch whitespace**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 6: Inspect doctor output manually**

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Expected: output includes hook status, session mode, workspace active plan, effective plan, context profile, and progress diagnostics without traceback.

- [ ] **Step 7: Inspect final diff**

Run:

```powershell
git diff --stat HEAD
git status --short
```

Expected: only intentional files are modified. `dist/` may remain untracked and must not be staged for this task.

- [ ] **Step 8: Commit final adjustments if any**

If verification required small fixes, commit them with:

```powershell
git add <changed-files>
git commit -m "fix: stabilize session task isolation"
```

## 验收标准

- 同一项目中两个 Codex 对话可以分别绑定到不同 plan id。
- `PLAN_ID` 仍高于 session binding，session binding 高于 `.planning/.active_plan`。
- 一个对话切换 workspace active plan，不改变另一个已绑定对话的 effective plan。
- `UserPromptSubmit`、`PreToolUse`、`PostToolUse` 和 `Stop` 对同一 `session_id` 使用同一个 effective plan。
- `plan.py status` 显示 workspace active plan、session binding、effective plan 和 plan source。
- `plan.py doctor` 显示 session mode、attached sessions、binding enforcement 状态，并在风险场景给出诊断。
- strict mode 默认仍只要求 attached session；设置 `PWF_STRICT_REQUIRES_BINDING=1` 后才要求有效 binding。
- `progress.md` auto record 包含 `Session` 和 `Plan-Source`，并在 append 时使用短时 lock。
- 没有 session id 的默认 workspace 工作流保持兼容。
- 文档说明中文优先，英文 README 保留同步说明。

## 执行交接

Plan complete and saved to `docs/SESSION_TASK_ISOLATION_IMPLEMENTATION_PLAN.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Recommended choice for this implementation: Subagent-Driven. The tasks are independent enough for task-by-task execution, but they share resolver invariants, so each task should be reviewed before the next one starts.
