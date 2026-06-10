# 默认会话优先 PWF 隔离策略实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/pwf-init` 和 `plan.py init` 在能识别当前 Codex 会话时默认自动绑定新任务，从默认体验上支持同项目多会话并发，并保留旧 workspace 工作流的明确逃生口。

**Architecture:** 在现有 session binding、task lease、`/pwf-tasks`、`/pwf-use` 安全边界之上，把 `init` 的默认策略改为 session-first：`PWF_SESSION_ID` 或 `CODEX_THREAD_ID` 可用时自动执行“创建任务 + claim task lease + 写 session binding”。`.planning/.active_plan` 继续作为兼容层和单会话兜底；显式 `--no-bind-session` 可恢复旧的 workspace-only 行为；没有 session id 时只能降级到 workspace active，并在会产生孤儿任务的组合上拒绝执行。

**Tech Stack:** Python 标准库、`argparse`、本地 `.planning/` JSON/Markdown 状态、Codex skill wrapper、`unittest`、PowerShell 验证命令。

---

## 背景

`v0.2.3` 和 `v0.2.4` 已经建立了同项目多会话的安全基础：

- session binding 决定当前会话应该使用哪个 PWF 任务。
- task lease 阻止一个会话默认接管另一个会话的任务。
- `/pwf-tasks` 默认只列出当前会话可见任务。
- `/pwf-use` 默认只绑定当前会话可见任务，跨会话必须显式 `--claim` 或 `--share`。
- CLI 已能通过 `PWF_SESSION_ID` 或 `CODEX_THREAD_ID` 识别当前会话。

剩下的问题是普通用户创建任务时仍要知道 `--bind-session`。这和目标体验不一致：同项目多会话很常见，默认就应该把每个会话新建的任务绑定到各自会话。

## 用户可见行为

### 默认行为

在能识别当前会话时：

```text
/pwf-init 写文档
```

等价于：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "写文档" --bind-session
```

也就是创建任务后自动：

- 写 `.planning/session-bindings/<session-key>.json`
- 写 `.planning/<plan-id>/.task-lease.json`
- 输出 `session binding set: <key> -> <plan-id>`
- 输出 `task lease: owner=<key> status=active shared=false`
- 默认仍写 `.planning/.active_plan`，作为单会话兼容和 workspace fallback。

### 只绑定当前会话，不改 workspace active

```text
/pwf-init 写文档 --no-workspace-active
```

在能识别 session id 时，创建任务并绑定当前会话，但不写 `.planning/.active_plan`。

### 明确恢复旧 workspace-only 行为

```text
/pwf-init 写文档 --no-bind-session
```

只创建任务并写 `.planning/.active_plan`，不写 session binding，不写 task lease。这个选项主要服务脚本、兼容测试、以及用户明确知道自己只想使用 workspace active 的场景。

### 无 session id 的降级

如果没有 `PWF_SESSION_ID` 和 `CODEX_THREAD_ID`：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "写文档"
```

保持旧 workspace 行为，但输出清晰提示：

```text
session id: unavailable; created workspace active plan without session binding
```

如果同时传入 `--no-workspace-active`，命令必须失败，因为这会创建既无 session binding、也无 workspace active 的孤儿任务：

```text
session id: unavailable; cannot create a task with --no-workspace-active unless session binding is enabled
```

### 接管和共享仍显式

本计划不改变 `/pwf-use`、`tasks --all`、`--claim`、`--share` 语义。默认自动绑定只影响“新建任务属于当前会话”这一点，不允许自动接管旧任务或 stale owner。

## 非目标

- 不改变 hook payload 的 session id 解析顺序。
- 不删除 `.planning/.active_plan`。
- 不把 stale owner 自动转移给新会话。
- 不让 `/pwf-use` 默认解析其他会话独占任务。
- 不调整 release packaging。

## 文件职责

- Modify `.codex/skills/planning-with-files/scripts/plan.py`
  - 新增 `--no-bind-session`。
  - 将 `init` 的 `bind_session` 参数改为三态：auto / true / false。
  - 在 session id 可用时默认自动绑定。
  - 在 session id 缺失时输出 workspace 降级提示。
  - 拒绝无 session id 且 `--no-workspace-active` 的孤儿任务组合。
- Modify `.codex/skills/pwf-init/SKILL.md`
  - 说明 `/pwf-init` 默认自动绑定当前会话。
  - 说明 `--no-bind-session`、`--no-workspace-active` 的用途。
- Modify `.codex/skills/planning-with-files/SKILL.md`
  - 更新 Session Task Binding 段落，从“手动绑定”改为“默认自动绑定，显式关闭”。
- Modify `README.md`, `README.en.md`, `docs/FAQ.md`, `docs/USER_GUIDE.zh-CN.md`
  - 更新默认策略说明。
  - 解释 workspace active 是兼容层，不是多会话下的首选路由。
- Modify `CHANGELOG.md`
  - 在 `Unreleased` 记录行为变更和兼容选项。
- Modify `tests/test_plan_cli.py`
  - 覆盖默认自动绑定、CODEX_THREAD_ID fallback、显式关闭、无 session id 降级、无路由组合失败。
- Modify `tests/test_project_consistency.py`
  - 覆盖 README/FAQ/用户指南记录默认 session-first 行为和 `--no-bind-session`。

## 关键不变量

创建新任务时，如果当前会话可识别，新任务默认归当前会话所有。

session binding 仍优先于 `.planning/.active_plan`。因此同项目会话 A、B、C 分别创建任务后，即使 workspace active 最后指向 C，会话 A 和 B 仍应继续解析到自己的 session-bound plan。

`.planning/.active_plan` 仍可写入，作为旧工作流和单会话恢复兜底。它不能绕过 task lease ownership gate。

显式 `--no-bind-session` 不能创建 task lease。它是真正的旧行为逃生口。

显式 `--bind-session` 在没有 session id 时继续失败，不降级。用户显式要求绑定，工具不能悄悄改成 workspace-only。

`--no-workspace-active` 必须有 session binding。否则任务没有自动路由入口，应拒绝创建。

## Task 1: CLI `init` 默认自动绑定

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写默认自动绑定失败测试**

在 `PlanCliTests` 中 `test_init_creates_active_planning_directory` 后新增：

```python
def test_init_defaults_to_session_binding_when_session_id_available(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(root, "init", "Session First", env={"PWF_SESSION_ID": "session-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        today = datetime.now().strftime("%Y-%m-%d")
        plan_id = f"{today}-session-first"
        key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), plan_id)
        binding = root / ".planning" / "session-bindings" / f"{key}.json"
        self.assertEqual(json.loads(binding.read_text(encoding="utf-8"))["plan_id"], plan_id)
        lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
        self.assertEqual(lease["owner_session_key"], key)
        self.assertFalse(lease["shared"])
        self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)
        self.assertIn(f"task lease: owner={key} status=active shared=false", result.stdout)
```

- [ ] **Step 2: 验证测试失败**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_init_defaults_to_session_binding_when_session_id_available -v
```

Expected: FAIL，因为当前 `init` 默认不写 session binding。

- [ ] **Step 3: 改 `init` 函数为三态绑定策略**

在 `.codex/skills/planning-with-files/scripts/plan.py` 中，把 `init` 签名改成：

```python
def init(
    root: Path,
    name: str,
    legacy: bool = False,
    force: bool = False,
    bind_session: bool | None = None,
    workspace_active: bool = True,
) -> int:
```

在 legacy 检查后加入：

```python
    session_id = _current_session_id()
    explicit_bind = bind_session is True
    explicit_no_bind = bind_session is False
    auto_bind = bind_session is None and not legacy and session_id is not None
    effective_bind_session = explicit_bind or auto_bind

    if legacy and effective_bind_session:
        print(LEGACY_BIND_SESSION_UNSUPPORTED)
        return 1

    if not workspace_active and not effective_bind_session:
        if not session_id:
            print(_message("session_binding_unavailable_no_workspace"))
        else:
            print(_message("session_binding_required_for_no_workspace"))
        return 1
```

替换原来的：

```python
    if legacy and bind_session:
```

以及后续 `if bind_session:` 判断为 `if effective_bind_session:`。保留 `explicit_bind` 在无 session id 时失败：

```python
    if effective_bind_session:
        if not session_id:
            print(_message("missing_session_id"))
            return 1
```

在写完输出后，如果 `not effective_bind_session and bind_session is None and not legacy and session_id is None`，打印：

```python
        print(_message("session_binding_auto_unavailable"))
```

- [ ] **Step 4: 增加 CLI 文案**

在 `CLI_MESSAGES["en"]` 增加：

```python
"help_bind_session": "Bind the created plan to the current session",
"help_no_bind_session": "Do not bind the created plan to the current session",
"help_no_workspace_active": "Do not update .planning/.active_plan",
"session_binding_auto_unavailable": "session id: unavailable; created workspace active plan without session binding",
"session_binding_required_for_no_workspace": "session binding is required when --no-workspace-active is used",
"session_binding_unavailable_no_workspace": "session id: unavailable; cannot create a task with --no-workspace-active unless session binding is enabled",
```

在 `CLI_MESSAGES["zh-CN"]` 增加：

```python
"help_bind_session": "将新建计划绑定到当前会话",
"help_no_bind_session": "不要将新建计划绑定到当前会话",
"help_no_workspace_active": "不要更新 .planning/.active_plan",
"session_binding_auto_unavailable": "session id: 不可用；已创建 workspace active plan，但未绑定会话",
"session_binding_required_for_no_workspace": "使用 --no-workspace-active 时必须启用 session binding",
"session_binding_unavailable_no_workspace": "session id: 不可用；没有 session binding 时不能创建 --no-workspace-active 任务",
```

- [ ] **Step 5: 更新 argparse**

把 init parser 的两个参数：

```python
init_parser.add_argument("--bind-session", action="store_true")
init_parser.add_argument("--no-workspace-active", action="store_true")
```

改成：

```python
init_bind_group = init_parser.add_mutually_exclusive_group()
init_bind_group.add_argument("--bind-session", dest="bind_session", action="store_true", help=_help("bind_session"))
init_bind_group.add_argument("--no-bind-session", dest="bind_session", action="store_false", help=_help("no_bind_session"))
init_parser.set_defaults(bind_session=None)
init_parser.add_argument("--no-workspace-active", action="store_true", help=_help("no_workspace_active"))
```

- [ ] **Step 6: 跑单测确认通过**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_init_defaults_to_session_binding_when_session_id_available -v
```

Expected: PASS。

## Task 2: 兼容开关与失败模式

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写 `--no-bind-session` 测试**

新增：

```python
def test_init_no_bind_session_preserves_workspace_only_behavior(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(
            root,
            "init",
            "Workspace Only",
            "--no-bind-session",
            env={"PWF_SESSION_ID": "session-a"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        today = datetime.now().strftime("%Y-%m-%d")
        plan_id = f"{today}-workspace-only"
        key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), plan_id)
        self.assertFalse((root / ".planning" / "session-bindings" / f"{key}.json").exists())
        self.assertFalse((root / ".planning" / plan_id / ".task-lease.json").exists())
```

- [ ] **Step 2: 写 `--no-workspace-active` 默认绑定测试**

新增：

```python
def test_init_no_workspace_active_defaults_to_session_binding(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(
            root,
            "init",
            "Side Task",
            "--no-workspace-active",
            env={"PWF_SESSION_ID": "session-a"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        today = datetime.now().strftime("%Y-%m-%d")
        plan_id = f"{today}-side-task"
        key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        self.assertFalse((root / ".planning" / ".active_plan").exists())
        binding = root / ".planning" / "session-bindings" / f"{key}.json"
        self.assertEqual(json.loads(binding.read_text(encoding="utf-8"))["plan_id"], plan_id)
        self.assertTrue((root / ".planning" / plan_id / ".task-lease.json").is_file())
```

- [ ] **Step 3: 写无 session id 降级测试**

新增：

```python
def test_init_without_session_id_keeps_workspace_behavior_with_warning(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(root, "init", "Workspace Fallback")

        self.assertEqual(result.returncode, 0, result.stderr)
        today = datetime.now().strftime("%Y-%m-%d")
        plan_id = f"{today}-workspace-fallback"
        self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), plan_id)
        self.assertFalse((root / ".planning" / "session-bindings").exists())
        self.assertFalse((root / ".planning" / plan_id / ".task-lease.json").exists())
        self.assertIn("created workspace active plan without session binding", result.stdout)
```

- [ ] **Step 4: 写无 session id 且无 workspace active 的失败测试**

新增：

```python
def test_init_no_workspace_active_without_session_id_is_rejected(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(root, "init", "Orphan", "--no-workspace-active")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot create a task with --no-workspace-active", result.stdout)
        self.assertFalse((root / ".planning" / "task_plan.md").exists())
        self.assertFalse((root / ".planning" / ".active_plan").exists())
        self.assertFalse(any((root / ".planning").glob("*")) if (root / ".planning").exists() else False)
```

- [ ] **Step 5: 写显式 `--bind-session` 无 session id 仍失败测试**

新增：

```python
def test_init_explicit_bind_session_without_session_id_still_fails(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(root, "init", "Needs Session", "--bind-session")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("session id: unavailable", result.stdout)
        self.assertFalse((root / ".planning").exists())
```

- [ ] **Step 6: 跑这些测试确认先失败后通过**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_init_no_bind_session_preserves_workspace_only_behavior tests.test_plan_cli.PlanCliTests.test_init_no_workspace_active_defaults_to_session_binding tests.test_plan_cli.PlanCliTests.test_init_without_session_id_keeps_workspace_behavior_with_warning tests.test_plan_cli.PlanCliTests.test_init_no_workspace_active_without_session_id_is_rejected tests.test_plan_cli.PlanCliTests.test_init_explicit_bind_session_without_session_id_still_fails -v
```

Expected after implementation: all PASS。

## Task 3: 多会话默认隔离回归测试

**Files:**
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写同项目多会话默认隔离测试**

新增：

```python
def test_multiple_sessions_init_default_to_separate_bound_tasks(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        first = run_plan(root, "init", "Write Docs", env={"PWF_SESSION_ID": "session-a"})
        second = run_plan(root, "init", "Fix Bug", env={"PWF_SESSION_ID": "session-b"})

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        today = datetime.now().strftime("%Y-%m-%d")
        docs_plan = f"{today}-write-docs"
        bug_plan = f"{today}-fix-bug"
        key_a = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
        key_b = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]

        binding_a = root / ".planning" / "session-bindings" / f"{key_a}.json"
        binding_b = root / ".planning" / "session-bindings" / f"{key_b}.json"
        self.assertEqual(json.loads(binding_a.read_text(encoding="utf-8"))["plan_id"], docs_plan)
        self.assertEqual(json.loads(binding_b.read_text(encoding="utf-8"))["plan_id"], bug_plan)

        lease_a = json.loads((root / ".planning" / docs_plan / ".task-lease.json").read_text(encoding="utf-8"))
        lease_b = json.loads((root / ".planning" / bug_plan / ".task-lease.json").read_text(encoding="utf-8"))
        self.assertEqual(lease_a["owner_session_key"], key_a)
        self.assertEqual(lease_b["owner_session_key"], key_b)

        tasks_a = run_plan(root, "tasks", env={"PWF_SESSION_ID": "session-a"})
        tasks_b = run_plan(root, "tasks", env={"PWF_SESSION_ID": "session-b"})
        self.assertIn(docs_plan, tasks_a.stdout)
        self.assertNotIn(bug_plan, tasks_a.stdout)
        self.assertIn(bug_plan, tasks_b.stdout)
        self.assertNotIn(docs_plan, tasks_b.stdout)

        status_a = run_plan(root, "status", env={"PWF_SESSION_ID": "session-a"})
        status_b = run_plan(root, "status", env={"PWF_SESSION_ID": "session-b"})
        self.assertIn(f"effective plan: {docs_plan}", status_a.stdout)
        self.assertIn(f"effective plan: {bug_plan}", status_b.stdout)
```

- [ ] **Step 2: 写 `CODEX_THREAD_ID` 默认绑定测试**

新增：

```python
def test_init_default_binding_uses_codex_thread_id_when_pwf_session_id_missing(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        result = run_plan(root, "init", "Thread Task", env={"CODEX_THREAD_ID": "thread-a"})

        self.assertEqual(result.returncode, 0, result.stderr)
        today = datetime.now().strftime("%Y-%m-%d")
        plan_id = f"{today}-thread-task"
        key = hashlib.sha256("thread-a".encode("utf-8")).hexdigest()[:12]
        binding = root / ".planning" / "session-bindings" / f"{key}.json"
        self.assertEqual(json.loads(binding.read_text(encoding="utf-8"))["plan_id"], plan_id)
        self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)
```

- [ ] **Step 3: 跑回归测试**

Run:

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_multiple_sessions_init_default_to_separate_bound_tasks tests.test_plan_cli.PlanCliTests.test_init_default_binding_uses_codex_thread_id_when_pwf_session_id_missing -v
```

Expected: PASS。

## Task 4: 旧测试调整与兼容确认

**Files:**
- Modify: `tests/test_plan_cli.py`

- [ ] **Step 1: 保留旧 workspace 行为测试**

现有 `test_init_creates_active_planning_directory` 不传 session env，应该继续通过。确认它不需要改成 `--no-bind-session`，因为无 session id 时仍降级到 workspace active。

- [ ] **Step 2: 保留显式绑定测试**

现有这些测试应继续通过：

```text
test_init_bind_session_no_workspace_active
test_init_bind_session_creates_task_lease_for_workspace_active_plan
test_init_force_bind_session_does_not_overwrite_other_owned_task
test_init_force_bind_session_does_not_overwrite_shared_task
```

如果它们和新增默认行为有重复，只做断言微调，不删除安全覆盖。

- [ ] **Step 3: 跑 Plan CLI 全量测试**

Run:

```powershell
python -m unittest tests.test_plan_cli -v
```

Expected: all tests PASS。

## Task 5: 文档与 slash wrapper 更新

**Files:**
- Modify: `.codex/skills/pwf-init/SKILL.md`
- Modify: `.codex/skills/planning-with-files/SKILL.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `docs/USER_GUIDE.zh-CN.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py`

- [ ] **Step 1: 更新 `/pwf-init` wrapper 文案**

把 `.codex/skills/pwf-init/SKILL.md` 的核心说明改成：

```markdown
Use any text after `/pwf-init` as the task name and options.

By default, when the current Codex session can be identified, `plan.py init` binds the new PWF task to this session and claims its task lease. This is the recommended behavior for multiple Codex conversations in the same project.

If no task name was provided, ask the user for the task name. Otherwise run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init <task name and options>
```

Useful options:

- `--no-workspace-active`: bind the task to this session without changing `.planning/.active_plan`.
- `--no-bind-session`: use the old workspace-only behavior intentionally.
```

- [ ] **Step 2: 更新主 skill 文档**

在 `.codex/skills/planning-with-files/SKILL.md` 的 `Session Task Binding` 段落前加：

```markdown
`/pwf-init` and `plan.py init` are session-first by default. When `PWF_SESSION_ID` or `CODEX_THREAD_ID` is available, a new named task is automatically bound to the current session and protected by a task lease.
```

并把原来的“创建任务并立即绑定”命令改为“显式形式仍可用”：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name"
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-workspace-active
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-bind-session
```

- [ ] **Step 3: 更新 README/FAQ/用户指南**

必须包含这些中文短语：

```text
默认会绑定当前会话
--no-bind-session
--no-workspace-active
workspace active 是兼容层
接管或共享仍必须显式
```

英文 README/FAQ 至少包含：

```text
session-first by default
--no-bind-session
workspace active remains a compatibility fallback
claim or share still requires explicit intent
```

- [ ] **Step 4: 更新 CHANGELOG**

在 `## Unreleased` 下增加中英双语条目：

```markdown
- 中文：规划将 `/pwf-init` / `plan.py init` 调整为 session-first 默认行为；能识别当前会话时，新任务会自动绑定当前会话并写入 task lease，降低同项目多会话并发时写混 progress 的风险。
- 中文：新增显式兼容逃生口 `--no-bind-session`；`--no-workspace-active` 在默认绑定下可创建只属于当前会话的任务。
- English: Plan `/pwf-init` / `plan.py init` as session-first by default; when the current session is identifiable, new tasks bind to that session and claim a task lease automatically.
- English: Add explicit compatibility escape hatch `--no-bind-session`; `--no-workspace-active` can create session-only tasks under the default binding behavior.
```

- [ ] **Step 5: 增加文档一致性测试**

在 `test_faq_document_is_linked_and_covers_user_questions` 中追加：

```python
        for phrase in (
            "默认会绑定当前会话",
            "--no-bind-session",
            "--no-workspace-active",
            "workspace active 是兼容层",
            "接管或共享仍必须显式",
        ):
            self.assertIn(phrase, readme_cn + faq + user_guide)

        for phrase in (
            "session-first by default",
            "--no-bind-session",
            "workspace active remains a compatibility fallback",
            "claim or share still requires explicit intent",
        ):
            self.assertIn(phrase, readme_en + faq)
```

- [ ] **Step 6: 跑文档一致性测试**

Run:

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: PASS。

## Task 6: 全量验证与审查

**Files:**
- No new source files.

- [ ] **Step 1: 跑 CLI 和 hooks 重点测试**

Run:

```powershell
python -m unittest tests.test_plan_cli tests.test_hooks -v
```

Expected: PASS。

- [ ] **Step 2: 跑全量测试**

Run:

```powershell
python -m unittest discover -v
```

Expected: PASS，当前基线是 191 tests，新增测试后数量会增加。

- [ ] **Step 3: 检查 diff 空白**

Run:

```powershell
git diff --check
```

Expected: exit 0。Windows 上可能出现 LF/CRLF 提示，但不能有 trailing whitespace 或 conflict marker。

- [ ] **Step 4: 人工审查关键场景**

逐条确认：

- 无 session id 的 `plan.py init "Task"` 仍创建 workspace active plan。
- 有 `PWF_SESSION_ID` 的 `plan.py init "Task"` 自动写 session binding 和 task lease。
- 有 `CODEX_THREAD_ID` 的 `plan.py init "Task"` 自动写 session binding 和 task lease。
- `plan.py init "Task" --no-bind-session` 不写 binding/lease。
- `plan.py init "Task" --no-workspace-active` 在有 session id 时不写 `.active_plan`，但写 binding/lease。
- `plan.py init "Task" --no-workspace-active` 在无 session id 时失败。
- 两个 session 在同一项目各自 init 后，`tasks` 和 `status` 默认只看到/解析自己的任务。
- `use` 默认仍不会接管 stale owner，`--claim` / `--share` 仍显式生效。

## Task 7: 提交与 PR 准备

**Files:**
- All modified implementation, docs, and tests.

- [ ] **Step 1: 查看状态**

Run:

```powershell
git status --short --branch
git diff --stat
```

Expected: only planned source, docs, and test files changed. `.planning/` remains ignored and not staged.

- [ ] **Step 2: 提交**

Run:

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py .codex/skills/pwf-init/SKILL.md .codex/skills/planning-with-files/SKILL.md README.md README.en.md docs/FAQ.md docs/USER_GUIDE.zh-CN.md CHANGELOG.md tests/test_plan_cli.py tests/test_project_consistency.py
git commit -m "feat: default pwf init to session binding"
```

- [ ] **Step 3: 推送并创建 PR**

Run:

```powershell
git push -u origin plan/session-first-default-isolation
gh pr create --base main --head plan/session-first-default-isolation --title "[codex] default PWF init to session binding" --body-file <pr-body.md>
```

PR body 应包含：

```markdown
## Summary
- Make `plan.py init` session-first by default when `PWF_SESSION_ID` or `CODEX_THREAD_ID` is available.
- Add `--no-bind-session` as an explicit workspace-only compatibility escape hatch.
- Document default multi-session isolation behavior and update tests.

## Test Plan
- `python -m unittest tests.test_plan_cli tests.test_hooks -v`
- `python -m unittest tests.test_project_consistency -v`
- `python -m unittest discover -v`
- `git diff --check`
```
