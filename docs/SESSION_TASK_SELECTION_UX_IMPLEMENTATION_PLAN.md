# 当前会话任务列表与选择 UX 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让同一项目多 Codex 会话使用 PWF 时，可以用简单命令查看和选择当前会话自己的任务，同时默认不暴露、不误切、不自动接管其他会话的任务。

**Architecture:** 在现有 session binding 和 task lease 之上增加“任务可见集合”薄层：一个只读 scanner 负责枚举 `.planning/<plan-id>`，一个 visibility 函数负责判断当前 session 默认能看见哪些任务，`tasks` 和 `use` 共用同一套过滤与短 ID 解析。跨 owner 操作继续复用现有 `switch --session --force-claim/--share/--release-session` 和 task lease lock，不引入自动接管。

**Tech Stack:** Python 标准库、`argparse`、本地 `.planning/` JSON/Markdown 状态、Codex skill wrapper、`unittest`、PowerShell 验证命令。

---

## 背景与约束

用户反馈的核心不是“缺一个列表命令”这么小，而是“降低操作成本时不能把隔离边界变软”。当前 v0.2.3 已经有 session binding、task lease、显式 claim/share/release 和并发锁，但普通用户要手敲：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

当任务名很长或用户忘记任务名时，这个体验会逼用户去猜、复制路径或使用 workspace active fallback，反而更容易把两个会话混在一起。

本计划只做 UX 与安全过滤增强，不改变以下不变量：

- 默认不显示其他 session 独占任务。
- 默认不把当前会话切到其他 session 拥有的任务。
- stale owner 仍然是 owner，不能自动接管。
- workspace active plan 仍保留向后兼容，但不能绕过 task ownership gate。
- 跨 owner 操作必须显式使用 claim/share/release，并继续受 task lease lock 保护。
- `dist/` 是本地 release 产物，本任务不读取、不删除、不提交。

## 用户命令设计

推荐新增三个面向用户的 slash wrapper：

| 命令 | 默认行为 | CLI |
|------|----------|-----|
| `/pwf-tasks` | 列出当前会话可见任务、短 ID、状态、当前绑定标记 | `plan.py tasks` |
| `/pwf-use <id>` | 只在当前会话可见任务内解析短 ID 或 plan id，并绑定当前会话 | `plan.py use <id>` |

`/pwf-status` 继续承担当前 session binding、effective plan、lease 状态的详情诊断。本轮不新增 `/pwf-current`，避免把实现范围扩大到第三个用户入口。

底层 CLI 推荐新增：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py tasks
python .codex\skills\planning-with-files\scripts\plan.py tasks --all
python .codex\skills\planning-with-files\scripts\plan.py tasks --json
python .codex\skills\planning-with-files\scripts\plan.py use <short-id-or-plan-id>
python .codex\skills\planning-with-files\scripts\plan.py use <short-id-or-plan-id> --claim
python .codex\skills\planning-with-files\scripts\plan.py use <short-id-or-plan-id> --share
```

`use --claim` 等价于 `switch <plan-id> --session --force-claim`，`use --share` 等价于 `switch <plan-id> --session --share`。没有 `--claim/--share` 时，`use` 只能解析默认可见集合。

## 可见性模型

新增一个内部数据结构，例如 `VisibleTask`：

```python
@dataclass(frozen=True)
class TaskSummary:
    plan_id: str
    path: Path
    short_id: str
    title: str
    current_phase: str | None
    phase_counts: tuple[int, int, int, int] | None
    workspace_active: bool
    session_bound: bool
    lease_owner: str | None
    lease_status: str
    shared: bool
    visible: bool
    reason: str
```

默认 `plan.py tasks` 只打印 `visible=True` 的任务。建议默认可见集合为：

- 当前 session binding 指向的任务。
- task lease owner 是当前 session key 的任务。
- 当前 session 已绑定到 shared task，或当前 session 是 shared task 的原 owner。
- 当前 session 已绑定到 released task。
- 没有任何 task lease 且是当前 session binding 指向的任务。

默认不可见集合为：

- 其他 session 拥有、未 shared、未 released 的任务。
- 其他 session 拥有但已经 stale 的任务。
- 仅因为 `.planning/.active_plan` 指向而属于其他 session 的任务。
- 无 session id 时，任何有 owner 的 session task。

`tasks --all` 可以只读显示所有任务，用于诊断和复制 plan id，但必须标注：

- `owned-by-other-session`
- `stale-owner`
- `shared`
- `released`
- `workspace-active`
- `session-bound`

`use` 默认不使用 `--all` 视图解析，防止用户从诊断列表复制一个其他会话任务短 ID 后直接切过去。

## Session ID 来源

当前 CLI `_current_session_id()` 只读 `PWF_SESSION_ID`。为降低使用门槛，应改为：

```python
def _current_session_id() -> str | None:
    for name in ("PWF_SESSION_ID", "CODEX_THREAD_ID"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None
```

hook payload 的 session 解析暂不改变：`codex_hook_adapter.session_id_from_payload()` 仍然优先 payload `session_id`，再读 `PWF_SESSION_ID`。这样 CLI 能自然识别 Codex Desktop thread，hook 严格模式仍由 hook payload 控制。

## 短 ID 规则

短 ID 必须稳定、可复制、无状态：

```python
def _task_short_id(plan_id: str, length: int = 6) -> str:
    return hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:length]
```

生成列表时，先对当前输出集合按 `plan_id` 排序，再为碰撞项扩展到 8、10、12 位。若 12 位仍碰撞，保留 12 位并在 `use` 解析时视为 ambiguous。

`use <selector>` 的解析顺序：

1. 如果 selector 是合法 plan id 且在默认可见集合中，直接使用。
2. 否则按 short id 前缀匹配默认可见集合。
3. 0 个匹配：失败，提示运行 `/pwf-tasks`。
4. 多个匹配：失败，打印候选，不自动猜测。
5. 仅当传入 `--claim` 或 `--share` 时，允许 selector 在 `--all` 集合内解析，但最终仍调用现有 task lease claim/share 逻辑。

## 文件职责

- Modify `.codex/skills/planning-with-files/scripts/plan.py`
  - 增加 `CODEX_THREAD_ID` fallback。
  - 增加 task scanner、visibility filter、short id 生成、selector 解析。
  - 增加 `tasks`、`use` 子命令和输出文案。
  - 可选增加 `current` 或 `status --brief`。
- Modify `.codex/hooks/planning_state.py`
  - 如果 `plan.py` 需要复用 `PlanningPaths`、phase parsing 或 lease helper，可增加只读 helper；不要让 scanner 调用 `planning_paths()`，因为它会经过 ownership gate。
- Create `.codex/skills/pwf-tasks/SKILL.md`
  - 包装 `/pwf-tasks` 到 `plan.py tasks`。
- Create `.codex/skills/pwf-use/SKILL.md`
  - 包装 `/pwf-use <id>` 到 `plan.py use <id>`。
- Modify `tests/test_plan_cli.py`
  - 覆盖 CLI session fallback、任务列表、短 ID、可见性和选择安全。
- Modify `tests/test_pwf_commands.py`
  - 将新增 slash wrapper 加入 `COMMANDS`。
- Modify `tests/test_project_consistency.py`
  - 检查 README/FAQ 记录新增命令和默认安全行为。
- Modify `README.md`, `README.en.md`, `docs/FAQ.md`, `CHANGELOG.md`
  - 中文为主，英文保留同步说明。

## Task 1: CLI Session ID Fallback

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写失败测试**

在 `PlanCliTests` 中新增：

```python
def test_switch_session_uses_codex_thread_id_when_pwf_session_id_missing(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-thread"
        write_plan(root / ".planning" / plan_id)

        result = run_plan(root, "switch", plan_id, "--session", env={"CODEX_THREAD_ID": "thread-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        key = hashlib.sha256("thread-a".encode("utf-8")).hexdigest()[:12]
        binding = root / ".planning" / "session-bindings" / f"{key}.json"
        self.assertTrue(binding.is_file())
        self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_switch_session_uses_codex_thread_id_when_pwf_session_id_missing -v
```

Expected: FAIL，输出包含 `session id: unavailable`。

- [ ] **Step 3: 修改 `_current_session_id()`**

将 `plan.py` 中现有函数替换为：

```python
def _current_session_id() -> str | None:
    for name in ("PWF_SESSION_ID", "CODEX_THREAD_ID"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None
```

- [ ] **Step 4: 运行通过测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_switch_session_uses_codex_thread_id_when_pwf_session_id_missing -v
```

Expected: PASS。

- [ ] **Step 5: 小范围回归**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_switch_session_writes_binding_without_changing_workspace_active tests.test_plan_cli.PlanCliTests.test_switch_session_requires_force_claim_for_owned_task -v
```

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add .codex\skills\planning-with-files\scripts\plan.py tests\test_plan_cli.py
git commit -m "feat: detect codex thread id for pwf cli sessions"
```

## Task 2: 只读任务扫描与可见性过滤

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写默认列表不泄露其他会话任务的失败测试**

在 `PlanCliTests` 中新增：

```python
def test_tasks_default_lists_only_current_session_visible_tasks(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        own_plan = "2026-06-09-own"
        other_plan = "2026-06-09-other"
        write_plan(root / ".planning" / own_plan, title="Own")
        write_plan(root / ".planning" / other_plan, title="Other")
        own_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        other_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / own_plan / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": own_plan,
                "owner_session_key": own_key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )
        (root / ".planning" / other_plan / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": other_plan,
                "owner_session_key": other_key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )

        result = run_plan(root, "tasks", env={"PWF_SESSION_ID": "session-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(own_plan, result.stdout)
        self.assertIn("owned-by-current-session", result.stdout)
        self.assertNotIn(other_plan, result.stdout)
```

- [ ] **Step 2: 写 `--all` 只读诊断测试**

```python
def test_tasks_all_lists_other_session_tasks_as_read_only(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-other"
        write_plan(root / ".planning" / plan_id, title="Other")
        owner_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / plan_id / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": plan_id,
                "owner_session_key": owner_key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )

        result = run_plan(root, "tasks", "--all", env={"PWF_SESSION_ID": "session-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(plan_id, result.stdout)
        self.assertIn("owned-by-other-session", result.stdout)
        self.assertIn(owner_key, result.stdout)
```

- [ ] **Step 3: 运行失败测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_tasks_default_lists_only_current_session_visible_tasks tests.test_plan_cli.PlanCliTests.test_tasks_all_lists_other_session_tasks_as_read_only -v
```

Expected: FAIL，`tasks` 子命令不存在。

- [ ] **Step 4: 增加扫描与可见性 helper**

在 `plan.py` 顶部 dataclass import 后可复用已有 `dataclass`。如未导入，加入：

```python
from dataclasses import dataclass
```

增加：

```python
@dataclass(frozen=True)
class TaskSummary:
    plan_id: str
    path: Path
    short_id: str
    title: str
    current_phase: str | None
    phase_counts: tuple[int, int, int, int] | None
    workspace_active: bool
    session_bound: bool
    lease_owner: str | None
    lease_status: str
    shared: bool
    visible: bool
    reason: str
```

增加只读 scanner：

```python
def _iter_plan_ids(root: Path) -> list[str]:
    planning_root = root / ".planning"
    if not planning_root.is_dir():
        return []
    plan_ids = []
    for child in planning_root.iterdir():
        if not child.is_dir():
            continue
        if not planning_state.valid_plan_id(child.name):
            continue
        if (child / "task_plan.md").is_file():
            plan_ids.append(child.name)
    return sorted(plan_ids)
```

增加标题读取：

```python
def _paths_for_plan_dir(plan_dir: Path) -> planning_state.PlanningPaths:
    return planning_state.PlanningPaths(
        root=plan_dir,
        task_plan=plan_dir / "task_plan.md",
        progress=plan_dir / "progress.md",
        findings=plan_dir / "findings.md",
    )


def _task_title(plan_dir: Path) -> str:
    task_plan = plan_dir / "task_plan.md"
    if not task_plan.is_file():
        return ""
    for line in task_plan.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("# Task Plan:"):
            return stripped.removeprefix("# Task Plan:").strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""
```

增加任意 plan 目录的 phase 计数。这里不能调用 `planning_state.phase_counts(root, session_id=...)`，因为它解析的是当前 effective plan，不是 scanner 正在枚举的 plan：

```python
def _phase_counts_for_plan_dir(plan_dir: Path) -> tuple[int, int, int, int] | None:
    task_plan = plan_dir / "task_plan.md"
    if not task_plan.is_file():
        return None
    text = task_plan.read_text(encoding="utf-8", errors="replace")
    total = len(re.findall(r"^### Phase", text, flags=re.MULTILINE))
    complete = text.count("**Status:** complete")
    in_progress = text.count("**Status:** in_progress")
    pending = text.count("**Status:** pending")
    if complete == 0 and in_progress == 0 and pending == 0:
        complete = text.count("[complete]")
        in_progress = text.count("[in_progress]")
        pending = text.count("[pending]")
    return total, complete, in_progress, pending
```

增加短 ID：

```python
def _task_short_id(plan_id: str, length: int = 6) -> str:
    return hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:length]
```

增加 summary 构造：

```python
def _task_summaries(root: Path, include_all: bool = False, session_id: str | None = None) -> list[TaskSummary]:
    current_key = planning_state.session_key(session_id) if session_id else None
    bound_plan = _read_session_binding_plan_id(root, session_id) if session_id else None
    workspace_plan = _workspace_active_plan_id(root)
    summaries: list[TaskSummary] = []
    for plan_id in _iter_plan_ids(root):
        plan_dir = root / ".planning" / plan_id
        lease = planning_state.read_task_lease(root, plan_id)
        status = planning_state.task_lease_status(lease) if lease else "none"
        owner = lease.owner_session_key if lease else None
        shared = bool(lease.shared) if lease else False
        session_bound = plan_id == bound_plan
        workspace_active = plan_id == workspace_plan
        visible = False
        reason = "unowned"
        if session_bound:
            visible = True
            reason = "session-bound"
        elif lease is None:
            visible = False
            reason = "unowned"
        elif current_key and owner == current_key:
            visible = True
            reason = "owned-by-current-session"
        elif shared:
            visible = session_bound
            reason = "shared" if visible else "shared-not-joined"
        elif status == "released":
            visible = session_bound
            reason = "released" if visible else "released-not-bound"
        else:
            reason = "owned-by-other-session"
            if status == "stale":
                reason = "stale-owner"
        summary = TaskSummary(
            plan_id=plan_id,
            path=plan_dir,
            short_id=_task_short_id(plan_id),
            title=_task_title(plan_dir),
            current_phase=_current_phase(_paths_for_plan_dir(plan_dir)),
            phase_counts=_phase_counts_for_plan_dir(plan_dir),
            workspace_active=workspace_active,
            session_bound=session_bound,
            lease_owner=owner,
            lease_status=status,
            shared=shared,
            visible=visible,
            reason=reason,
        )
        if include_all or summary.visible:
            summaries.append(summary)
    return summaries
```

实现时注意：scanner 必须使用 `_paths_for_plan_dir(plan_dir)` 和 `_phase_counts_for_plan_dir(plan_dir)` 这种只读 helper，不要调用 `planning_state.planning_paths()` 或 `planning_state.phase_counts(root, session_id=...)` 来枚举任意任务。

- [ ] **Step 5: 增加输出函数和 `tasks` 子命令**

```python
def tasks(root: Path, include_all: bool = False, as_json: bool = False) -> int:
    session_id = _current_session_id()
    summaries = _task_summaries(root, include_all=include_all, session_id=session_id)
    if as_json:
        print(json.dumps([summary.__dict__ | {"path": str(summary.path)} for summary in summaries], ensure_ascii=True, indent=2))
        return 0
    if not summaries:
        print("tasks: none visible for current session")
        return 0
    for summary in summaries:
        markers = []
        if summary.session_bound:
            markers.append("session-bound")
        if summary.workspace_active:
            markers.append("workspace-active")
        markers.append(summary.reason)
        if summary.lease_owner:
            markers.append(f"owner={summary.lease_owner}")
        marker_text = ", ".join(markers)
        title = f" {summary.title}" if summary.title else ""
        print(f"{summary.short_id}  {summary.plan_id}{title} [{marker_text}]")
    return 0
```

在 `main()` 中加入：

```python
tasks_parser = subparsers.add_parser("tasks", help="List PWF tasks visible to the current session")
tasks_parser.add_argument("--all", action="store_true")
tasks_parser.add_argument("--json", action="store_true")
```

并在 dispatch 中加入：

```python
if args.command == "tasks":
    return tasks(root, include_all=args.all, as_json=args.json)
```

- [ ] **Step 6: 运行通过测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_tasks_default_lists_only_current_session_visible_tasks tests.test_plan_cli.PlanCliTests.test_tasks_all_lists_other_session_tasks_as_read_only -v
```

Expected: PASS。

- [ ] **Step 7: 补充 JSON 测试**

```python
def test_tasks_json_is_machine_readable(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-json"
        write_plan(root / ".planning" / plan_id)
        key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / plan_id / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": plan_id,
                "owner_session_key": key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )

        result = run_plan(root, "tasks", "--json", env={"PWF_SESSION_ID": "session-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["plan_id"], plan_id)
        self.assertEqual(payload[0]["reason"], "owned-by-current-session")
```

- [ ] **Step 8: 提交**

```powershell
git add .codex\skills\planning-with-files\scripts\plan.py tests\test_plan_cli.py
git commit -m "feat: list pwf tasks visible to current session"
```

## Task 3: 安全选择与短 ID 解析

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写短 ID use 成功测试**

```python
def test_use_short_id_binds_visible_current_session_task(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-use"
        write_plan(root / ".planning" / plan_id)
        key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / plan_id / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": plan_id,
                "owner_session_key": key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )
        short_id = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:6]

        result = run_plan(root, "use", short_id, env={"PWF_SESSION_ID": "session-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        binding = root / ".planning" / "session-bindings" / f"{key}.json"
        self.assertEqual(json.loads(binding.read_text(encoding="utf-8"))["plan_id"], plan_id)
        self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)
```

- [ ] **Step 2: 写 use 不可越权测试**

```python
def test_use_short_id_does_not_bind_other_session_task_by_default(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-other"
        write_plan(root / ".planning" / plan_id)
        owner_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
        current_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / plan_id / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": plan_id,
                "owner_session_key": owner_key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )
        short_id = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:6]

        result = run_plan(root, "use", short_id, env={"PWF_SESSION_ID": "session-a"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not visible to current session", result.stdout)
        self.assertFalse((root / ".planning" / "session-bindings" / f"{current_key}.json").exists())
```

- [ ] **Step 3: 写 stale owner 不自动接管测试**

```python
def test_use_does_not_auto_claim_stale_owner_task(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-stale"
        write_plan(root / ".planning" / plan_id)
        owner_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / plan_id / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": plan_id,
                "owner_session_key": owner_key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2000-01-01T00:00:00Z",
                "updated_at": "2000-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )

        result = run_plan(root, "use", plan_id, env={"PWF_SESSION_ID": "session-a"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not visible to current session", result.stdout)
        self.assertIn("--claim", result.stdout)
```

- [ ] **Step 4: 运行失败测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_use_short_id_binds_visible_current_session_task tests.test_plan_cli.PlanCliTests.test_use_short_id_does_not_bind_other_session_task_by_default tests.test_plan_cli.PlanCliTests.test_use_does_not_auto_claim_stale_owner_task -v
```

Expected: FAIL，`use` 子命令不存在。

- [ ] **Step 5: 实现 selector 解析**

```python
def _resolve_task_selector(root: Path, selector: str, *, include_all: bool, session_id: str | None) -> tuple[TaskSummary | None, str | None]:
    summaries = _task_summaries(root, include_all=include_all, session_id=session_id)
    exact = [summary for summary in summaries if summary.plan_id == selector]
    if len(exact) == 1:
        return exact[0], None
    matches = [summary for summary in summaries if summary.short_id.startswith(selector)]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        all_matches = _task_summaries(root, include_all=True, session_id=session_id)
        hidden = [summary for summary in all_matches if summary.plan_id == selector or summary.short_id.startswith(selector)]
        if hidden:
            return None, "task is not visible to current session; run /pwf-tasks or use --claim/--share explicitly."
        return None, "task selector not found; run /pwf-tasks to list visible tasks."
    candidates = ", ".join(f"{summary.short_id}={summary.plan_id}" for summary in matches)
    return None, f"task selector is ambiguous: {candidates}"
```

- [ ] **Step 6: 实现 `use`**

```python
def use(root: Path, selector: str, *, claim: bool = False, share: bool = False) -> int:
    session_id = _current_session_id()
    if not session_id:
        print(_message("missing_session_id"))
        return 1
    summary, error = _resolve_task_selector(root, selector, include_all=claim or share, session_id=session_id)
    if summary is None:
        print(error or "task selector not found")
        return 1
    return switch(root, summary.plan_id, session=True, force_claim=claim, share=share)
```

在 `main()` 中加入：

```python
use_parser = subparsers.add_parser("use", help="Bind current session to a visible PWF task")
use_parser.add_argument("selector")
use_parser.add_argument("--claim", action="store_true")
use_parser.add_argument("--share", action="store_true")
```

dispatch：

```python
if args.command == "use":
    return use(root, args.selector, claim=args.claim, share=args.share)
```

- [ ] **Step 7: 运行通过测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_use_short_id_binds_visible_current_session_task tests.test_plan_cli.PlanCliTests.test_use_short_id_does_not_bind_other_session_task_by_default tests.test_plan_cli.PlanCliTests.test_use_does_not_auto_claim_stale_owner_task -v
```

Expected: PASS。

- [ ] **Step 8: 补充 explicit claim/share 测试**

```python
def test_use_claim_explicitly_transfers_other_session_task(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_id = "2026-06-09-claim"
        write_plan(root / ".planning" / plan_id)
        old_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
        new_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        (root / ".planning" / plan_id / ".task-lease.json").write_text(
            json.dumps({
                "version": 1,
                "plan_id": plan_id,
                "owner_session_key": old_key,
                "owner_status": "active",
                "shared": False,
                "claimed_at": "2026-06-09T10:00:00Z",
                "updated_at": "2999-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )

        result = run_plan(root, "use", plan_id, "--claim", env={"PWF_SESSION_ID": "session-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
        self.assertEqual(lease["owner_session_key"], new_key)
        self.assertIn(f"task lease: owner={new_key}", result.stdout)
```

- [ ] **Step 9: 提交**

```powershell
git add .codex\skills\planning-with-files\scripts\plan.py tests\test_plan_cli.py
git commit -m "feat: bind pwf session by visible task id"
```

## Task 4: Slash Wrappers

**Files:**
- Create: `.codex/skills/pwf-tasks/SKILL.md`
- Create: `.codex/skills/pwf-use/SKILL.md`
- Modify: `tests/test_pwf_commands.py`

- [ ] **Step 1: 写失败测试**

修改 `tests/test_pwf_commands.py`：

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
}
```

Run:

```powershell
python -m unittest tests.test_pwf_commands.PwfCommandTests.test_pwf_skill_wrappers_have_slash_command_metadata tests.test_pwf_commands.PwfCommandTests.test_pwf_skill_wrappers_route_to_plan_cli -v
```

Expected: FAIL，缺少 wrapper 文件。

- [ ] **Step 2: 创建 `/pwf-tasks` wrapper**

`.codex/skills/pwf-tasks/SKILL.md`：

````markdown
---
name: pwf-tasks
description: List Helsincy Plan With Files tasks visible to the current session. Invoke with /pwf-tasks.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-tasks

Use any text after `/pwf-tasks` as optional flags.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py tasks <optional flags>
```

中文模式：如果用户希望中文输出，先设置 `PWF_LANG=zh-CN`，再运行相同命令。

By default, show only tasks visible to the current session. Do not show tasks owned by other sessions unless the user explicitly passes `--all`.
````

- [ ] **Step 3: 创建 `/pwf-use` wrapper**

`.codex/skills/pwf-use/SKILL.md`：

````markdown
---
name: pwf-use
description: Bind the current session to a visible Helsincy Plan With Files task. Invoke with /pwf-use.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-use

Use any text after `/pwf-use` as the required task selector and optional flags.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py use <task selector and optional flags>
```

中文模式：如果用户希望中文输出，先设置 `PWF_LANG=zh-CN`，再运行相同命令。

The selector may be a plan id or short id from `/pwf-tasks`. By default it only resolves tasks visible to the current session. Use explicit `--claim` or `--share` only when the user intentionally wants to cross an ownership boundary.
````

- [ ] **Step 4: 运行通过测试**

Run:

```powershell
python -m unittest tests.test_pwf_commands -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add .codex\skills\pwf-tasks\SKILL.md .codex\skills\pwf-use\SKILL.md tests\test_pwf_commands.py
git commit -m "feat: add pwf task selection slash commands"
```

## Task 5: 文档与用户说明

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py`

- [ ] **Step 1: 写文档一致性失败测试**

在 `ProjectConsistencyTests` 中新增：

```python
def test_docs_document_session_task_selection_commands(self):
    readme_cn = read_text("README.md")
    readme_en = read_text("README.en.md")
    faq = read_text("docs/FAQ.md")

    for text in (readme_cn, readme_en, faq):
        self.assertIn("/pwf-tasks", text)
        self.assertIn("/pwf-use", text)
        self.assertIn("plan.py tasks", text)
        self.assertIn("plan.py use", text)

    self.assertIn("默认", readme_cn)
    self.assertIn("current session", readme_en)
    self.assertIn("other session", readme_en)
```

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_session_task_selection_commands -v
```

Expected: FAIL。

- [ ] **Step 2: 更新 README 中文命令表**

在 `README.md` 的 `/pwf-*` 命令表加入：

```markdown
| `/pwf-tasks` | 列出当前会话可见的 PWF 任务和短 ID；默认不显示其他会话任务 | `plan.py tasks` |
| `/pwf-use <id>` | 用 `/pwf-tasks` 显示的短 ID 或 plan id 绑定当前会话 | `plan.py use <id>` |
```

在 session binding 小节加入：

```markdown
更省心的方式是先运行 `/pwf-tasks`。它默认只显示当前会话可见任务，不会列出其他会话独占任务。复制列表中的短 ID 后运行 `/pwf-use <short-id>` 即可绑定当前会话。需要诊断所有任务时才使用 `plan.py tasks --all`；即使在 `--all` 中看到了其他会话任务，也必须显式使用 `plan.py use <id> --claim` 或 `plan.py use <id> --share` 才能跨 ownership 边界。
```

- [ ] **Step 3: 更新 README 英文**

在 `README.en.md` 同步加入命令表和说明：

```markdown
| `/pwf-tasks` | List PWF tasks visible to the current session with short IDs; other sessions' exclusive tasks are hidden by default | `plan.py tasks` |
| `/pwf-use <id>` | Bind the current session using a short ID or plan id shown by `/pwf-tasks` | `plan.py use <id>` |
```

说明：

```markdown
For a lower-friction workflow, run `/pwf-tasks` first. It lists only tasks visible to the current session by default. Copy a short ID and run `/pwf-use <short-id>` to bind this conversation. Use `plan.py tasks --all` only for read-only diagnostics; crossing another session's ownership boundary still requires explicit `plan.py use <id> --claim` or `plan.py use <id> --share`.
```

- [ ] **Step 4: 更新 FAQ**

增加问答：

```markdown
### 同一个项目里开了多个会话，我忘记当前会话能用哪个任务怎么办？

先运行 `/pwf-tasks`。它默认只列出当前会话可见任务，并显示短 ID、绑定状态和 lease 状态。复制短 ID 后运行 `/pwf-use <short-id>`。

如果你需要排查整个项目里的任务，运行 `plan.py tasks --all`。这个列表是诊断视图；默认 `/pwf-use` 不会因为你看到了其他会话任务就自动切过去。跨会话接管或共享必须显式使用 `--claim` 或 `--share`。
```

- [ ] **Step 5: 更新 CHANGELOG**

在 Unreleased 添加双语条目：

```markdown
- 中文：新增 `/pwf-tasks` 和 `/pwf-use`，可用短 ID 查看并绑定当前会话可见任务；默认不显示其他会话独占任务。
- English: Added `/pwf-tasks` and `/pwf-use` for short-ID based current-session task selection; other sessions' exclusive tasks stay hidden by default.
```

- [ ] **Step 6: 运行通过测试**

Run:

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_session_task_selection_commands tests.test_pwf_commands.PwfCommandTests.test_readmes_document_pwf_commands -v
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add README.md README.en.md docs\FAQ.md CHANGELOG.md tests\test_project_consistency.py
git commit -m "docs: document session task selection workflow"
```

## Task 6: 全量验证与人工 review

**Files:**
- No new files required unless fixes are found.

- [ ] **Step 1: 运行核心单测**

Run:

```powershell
python -m unittest tests.test_plan_cli tests.test_pwf_commands tests.test_project_consistency -v
```

Expected: PASS。

- [ ] **Step 2: 运行完整单测**

Run:

```powershell
python -m unittest discover -v
```

Expected: PASS。

- [ ] **Step 3: 运行格式/空白检查**

Run:

```powershell
git diff --check
```

Expected: no output，exit code 0。

- [ ] **Step 4: 运行 PWF doctor**

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Expected: no traceback；如果当前 workspace active plan 是本地 ignored PWF 任务，doctor 应正常输出。

- [ ] **Step 5: 手工安全验证**

在临时目录手工造两个 task lease：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py --root <tmp> tasks
python .codex\skills\planning-with-files\scripts\plan.py --root <tmp> tasks --all
python .codex\skills\planning-with-files\scripts\plan.py --root <tmp> use <other-session-short-id>
```

Expected:

- 默认 `tasks` 不显示其他 session 独占任务。
- `tasks --all` 显示其他 session 任务并标注 owner。
- `use <other-session-short-id>` 失败，提示 not visible 和 explicit claim/share。

- [ ] **Step 6: review 重点**

人工 review 时重点看：

- `tasks` 与 `use` 是否共用同一 visibility filter。
- `use` 是否在默认路径里调用了 `include_all=True`。
- stale owner 是否只改变显示标签，不改变权限。
- `--claim/--share` 是否最终复用 `switch()` 和 `claim_task_lease()`。
- JSON 输出是否包含原始 session id；不应泄露，只输出短 owner key。
- slash wrapper 是否不会提示用户直接使用 workspace `switch`。

- [ ] **Step 7: 最终提交或 PR**

如果 Task 1-5 已分别提交，此步只需确认 working tree：

```powershell
git status --short
```

Expected: 没有除 `dist/` 之外的未提交变更。

## Release Note 草案

中文：

> 新增当前会话任务列表与短 ID 选择工作流：运行 `/pwf-tasks` 可查看当前会话可见任务，默认不显示其他会话独占任务；复制短 ID 后运行 `/pwf-use <id>` 即可绑定当前会话。需要跨会话接管或共享时，仍必须显式使用 `--claim` 或 `--share`，不会自动接管 stale owner。

English:

> Added current-session task listing and short-ID selection: `/pwf-tasks` shows tasks visible to the current session by default, hiding other sessions' exclusive tasks, and `/pwf-use <id>` binds the conversation by short ID. Crossing ownership boundaries still requires explicit `--claim` or `--share`; stale owners are never auto-claimed.

## 执行建议

推荐按 Task 1 到 Task 6 顺序执行，不并行改同一个 `plan.py`。如果使用 subagent，每个 subagent 只负责一个 Task，并在进入下一 Task 前做 review，尤其要检查 visibility filter 和 selector resolver 的边界。
