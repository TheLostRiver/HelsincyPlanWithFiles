# 会话任务隔离实现方案

> **给 agentic workers：** 实施本文档时，必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行。步骤使用 checkbox（`- [ ]`）追踪。

**目标：** 让同一个项目里的多个 Codex 对话可以并发使用不同 PWF 任务，避免无关任务上下文混入，也避免不同对话的自动记录写进同一个 `progress.md`。

**架构：** 保留 `.planning/.active_plan` 作为 workspace 级默认任务和兼容 fallback，同时新增显式的 session-to-plan binding 层。hook 在读取 workspace active plan 之前先检查当前会话是否绑定了任务。对于同一个 hook payload，上下文注入和 `PostToolUse` 进度写入必须解析到同一个 effective plan，这样一个对话读的是哪个任务，写入的也就是哪个任务。CLI 和 doctor/status 需要能显示 workspace active plan、session binding 和 strict 隔离状态。

**技术栈：** Python 标准库、Codex hook stdin/stdout JSON payload、项目本地 `.planning/` 运行态文件、Markdown planning 文件、`unittest`、PowerShell 验证命令。

---

## 1. 问题背景

Helsincy Plan With Files 目前默认把一个项目视为只有一个 active planning task。hook 解析任务目录的顺序是：

```text
PLAN_ID environment variable
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

这对“一个项目当前只有一个主对话/主任务”的场景很可靠。但如果用户在同一个项目里打开多个 Codex 对话，并希望这些对话分别处理不同 PWF 任务，当前模型就会不安全。

当前会出现几类问题：

| 问题 | 表现 | 原因 |
|------|------|------|
| 上下文混入 | 对话 A 看到了对话 B 的 recent progress | 两个对话都解析到同一个 `.planning/.active_plan` |
| progress 混入 | 多个对话的 `PostToolUse` auto records 追加到同一个 `progress.md` | `append_progress()` 使用 workspace 解析出的 plan |
| 切换竞态 | 对话 A 开始时使用 plan X；对话 B 运行 `/pwf-switch plan-y` 后，对话 A 下一次 hook 可能改用 plan Y | `.planning/.active_plan` 是项目全局状态 |
| strict 模式误解 | `PWF_SESSION_MODE=strict` 可以阻止未 attach 的 session 注入上下文，但不会把某个 session 绑定到某个 plan | strict 当前只是访问门禁，不是任务归属解析器 |

只加文件锁不能解决这个问题。锁可以防止两个 append 把文本写坏，但它不能判断“这个对话应该读写哪个任务”。真正缺少的是“会话级任务归属”。

## 2. 目标

- 保留现有单项目单任务的默认工作流。
- 支持同项目多个对话分别绑定不同 PWF 任务并发工作。
- 对同一个 hook 事件，确保上下文注入和 progress 追加使用同一个 effective task。
- 一旦 session binding 存在，不再把 `.planning/.active_plan` 当作唯一真相。
- 在 `status` 和 `doctor` 中显示 workspace active plan、当前 session binding 和 effective plan。
- 保持 strict session isolation 显式、可诊断。
- 增加轻量 append lock，让多个对话有意共享同一任务时 `progress.md` 仍保持记录边界完整。
- 在 auto record 中增加来源元数据，让共享任务仍可审计。
- 保持 `.planning/` 作为本地运行态，不要求提交到 git。

## 3. 非目标

- 不强制用户为并发任务创建 git worktree。
- 不移除 `.planning/.active_plan`；它仍然是兼容 fallback。
- 不静默为所有项目开启 strict mode。
- 不要求用户提交 `.planning/session-bindings/`。
- 第一轮实现不把 `progress.md` 拆成 per-session 日志。
- 不降低 `PLAN_ID` 优先级；显式环境变量覆盖仍然是最高优先级。
- 不依赖 Codex UI 专属能力；CLI fallback 必须能表达同样状态。

## 4. 推荐设计

新增一层解析顺序：

```text
PLAN_ID environment variable
session-bound plan id
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

workspace active plan 继续作为默认值和迁移路径。只要 hook payload 有 `session_id`，并且该 session 有有效绑定，就优先使用绑定的 plan。这样即使另一个对话后来切换了 workspace active plan，当前对话的任务归属也不会漂移。

核心不变量：

> 对同一个 hook payload，`render_prompt_context()`、`render_pre_tool_context()`、`append_progress()` 和 `stop_message()` 必须基于同一个 root、payload、environment 解析到同一个 effective planning directory。

这个不变量比具体存储格式更重要。如果用户看到 hook 注入的是 plan A，那么这一轮文件修改的 auto record 也必须写到 plan A 的 `progress.md`。

## 5. 运行态数据结构

建议每个 session binding 使用一个小 JSON 文件：

```text
.planning/
  .active_plan
  session-policy.json
  session-bindings/
    <session-key>.json
```

示例：

```json
{
  "version": 1,
  "session_id": "abc123",
  "plan_id": "2026-06-07-session-task-isolation-plan",
  "created_at": "2026-06-07T10:12:30Z",
  "updated_at": "2026-06-07T10:12:30Z",
  "source": "plan.py switch --session"
}
```

选择“一 session 一文件”，而不是一个共享大 JSON map，原因是：

- 更容易原子写入。
- 更容易检查单个 session 的状态。
- 更容易清理过期绑定。
- 不需要多个 CLI/hook 同时重写同一个 map 文件。

文件名不要使用原始 `session_id`。建议使用稳定、短的 SHA-256 digest：

```text
.planning/session-bindings/3f9a8c1d2e77.json
```

JSON 内部可以保留原始 `session_id` 作为本地诊断信息，但 `doctor` 和 `status` 输出必须做 sanitize 和截断。

## 6. Session Identity

当前 hook 已经通过 `session_id_from_payload(payload)` 读取 session identity，并 fallback 到 `PWF_SESSION_ID`。继续复用这个唯一来源：

```python
def session_id_from_payload(payload: dict[str, Any]) -> str | None:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    env_sid = os.environ.get("PWF_SESSION_ID", "")
    return env_sid if env_sid else None
```

没有 session id 时：

- workspace mode：fallback 到 `.planning/.active_plan`。
- strict mode：保持现有行为，除非未来增加显式非 session override，否则拒绝上下文注入。
- CLI 在 hook 外运行时，可以通过 `PWF_SESSION_ID` 作为终端 fallback。

## 7. CLI 行为

扩展 `plan.py`，新增 session-aware 操作，同时保持现有命令兼容。

### 7.1 `init`

现有命令继续可用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name"
```

行为保持：

- 创建新 plan。
- 写入 `.planning/.active_plan`。

新增：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

行为：

- 创建新 plan。
- 默认仍设置 `.planning/.active_plan`，除非提供 `--no-workspace-active`。
- 如果存在 session id，则把当前 session 绑定到新 plan。
- 如果用户传入 `--bind-session` 但没有 session id，输出清晰诊断并返回非 0。

高级用法：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session --no-workspace-active
```

这个用法允许用户打开一个旁路任务，同时不影响仍依赖 workspace fallback 的其他对话。

### 7.2 `switch`

现有行为继续保留：

```powershell
plan.py switch 2026-06-07-some-task
```

默认仍表示切换 workspace active plan。

新增显式模式：

```powershell
plan.py switch 2026-06-07-some-task --session
plan.py switch 2026-06-07-some-task --workspace
```

规则：

- 不加 flag：保持现有 workspace 行为。
- `--workspace`：写 `.planning/.active_plan`。
- `--session`：写 `.planning/session-bindings/<session-key>.json`。
- `--session` 需要 hook payload 或 `PWF_SESSION_ID` 提供 session id。
- `PLAN_ID` 在 hook 解析时仍覆盖 session binding 和 workspace active plan。

新增清理命令：

```powershell
plan.py switch --clear-session
```

它删除当前 session binding，让这个对话重新 fallback 到 workspace mode。

### 7.3 `status`

`status` 应显示 workspace 和 session 两层状态：

```text
workspace active plan: 2026-06-07-main-task
session binding: 3f9a8c1d2e77 -> 2026-06-07-side-task
effective plan: 2026-06-07-side-task
path: D:\project\.planning\2026-06-07-side-task
```

如果当前没有 session id：

```text
workspace active plan: 2026-06-07-main-task
session binding: unavailable (no session_id)
effective plan: 2026-06-07-main-task
```

### 7.4 `doctor`

`doctor` 增加诊断：

```text
session mode: workspace
workspace active plan: ok 2026-06-07-main-task
session binding: none for current session
effective plan: workspace active
```

当检测到多个 attached sessions 但没有 binding：

```text
[warn] multiple sessions detected while using workspace active plan; concurrent conversations may share progress.md
```

strict 模式下：

```text
session mode: strict
session binding: required
[warn] strict mode has attached sessions without plan bindings
```

## 8. Hook 行为

hook 入口应该把 payload/session context 传入 plan resolution，而不是所有路径都调用 root-only resolver。

当前形态：

```python
paths = planning_paths(root)
```

目标形态：

```python
session_id = adapter.session_id_from_payload(payload)
paths = planning_paths(root, session_id=session_id)
```

更推荐使用带诊断信息的解析结果：

```python
resolution = resolve_planning_context(root, env=os.environ, session_id=session_id)
paths = resolution.paths
```

建议新增 dataclass：

```python
@dataclass(frozen=True)
class PlanResolution:
    source: str
    plan_id: str
    paths: PlanningPaths
    session_key: str | None = None
    warning: str | None = None
```

建议 source 值：

```text
env
session
workspace
newest
legacy
none
```

hook 仍应 fail-open。session binding JSON 格式错误时，resolver 应忽略该 binding，在可诊断路径输出 sanitize 后的 warning，然后按策略 fallback。

## 9. Strict Mode 语义

当前 strict mode 的含义是：

> 只有 hook payload 包含已 attach 的 `session_id` 时，才注入 planning context。

新增 binding 后，推荐把 strict mode 扩展为：

> 只有 hook payload 包含已 attach 的 `session_id` 时才允许注入；如果启用了 binding enforcement，则该 session 还必须绑定到有效 plan。

为了兼容已有用户，第一轮不要让 strict mode 默认要求绑定。新增显式开关：

```powershell
$env:PWF_STRICT_REQUIRES_BINDING = "1"
```

或在 policy 文件中写：

```json
{"mode":"strict","require_binding":true}
```

这样不会破坏已经把 strict mode 当作 workspace active plan 访问门禁的用户。

以后可以在 doctor warning 和 release notes 充分铺垫后，再考虑让 strict mode 默认要求 binding。

## 10. Progress 写入和锁

session binding 解决的是语义路由。文件锁解决的是物理 append 完整性。两者都需要，但不能互相替代。

建议为 `append_progress()` 增加锁：

```text
.planning/<plan-id>/.progress.lock
```

要求：

- 获取锁要有短 timeout。
- 锁超时时 hook 仍 fail-open；如果可以，输出诊断 system message。
- 写入保持 newline-normalized。
- 不要在持锁时渲染大上下文或运行外部命令。
- 只锁 append 操作本身。

auto record 增加 sanitize 后的来源字段：

```text
### Auto Record: 2026-06-07 10:12:30
- Tool: apply_patch
- Session: 3f9a8c1d2e77
- Plan-Source: session
- Files:
  - `src/example.py` (update)
```

使用短 session key，不使用原始 session id。没有 session id 时：

```text
- Session: unavailable
- Plan-Source: workspace
```

这样即使多个对话有意共享同一任务，审计时也能看出每条 auto record 的来源。

## 11. 安全和校验

session binding 文件是本地运行态，但会影响 hook context routing，应按不可信数据处理：

- 只接受 JSON object。
- 只接受 `version == 1`。
- 只接受 string `plan_id`，且必须对应存在的 `.planning/<plan-id>/task_plan.md`。
- 拒绝 path separators、`..`、绝对路径、空值和控制字符。
- warning 中的原始值必须用现有 env diagnostic 风格 sanitize。
- binding 不得解析到 `.planning/` 外部。
- 如果 bound plan 有 attestation，继续保留现有 tamper-blocking 行为。

binding 更新使用 atomic write：

1. 写 `<session-key>.json.tmp`。
2. flush 并关闭。
3. replace `<session-key>.json`。

## 12. 文档更新

实现后需要更新：

- `README.md`
- `README.en.md`
- `docs/FAQ.md`
- `CHANGELOG.md`

核心说明：

- workspace active plan 仍然是默认行为。
- 同项目并发多个 Codex 对话时，推荐使用 session binding。
- `strict` 控制 session 是否允许参与；binding 控制 session 使用哪个任务。
- `PLAN_ID` 是最强显式 override。
- `--session` 切换不会影响其他对话。

FAQ 建议新增：

```text
如果你在同一个项目里同时运行多个 Codex 对话，请把每个对话绑定到自己的 PWF 任务：

plan.py switch <plan-id> --session

旧的 switch 行为仍然会修改 workspace active plan，适合单任务项目。
```

## 13. 测试

实现前先补测试。

### 13.1 Resolver Tests

- `PLAN_ID` 优先于 session binding。
- Session binding 优先于 `.planning/.active_plan`。
- Workspace active plan 仍然是 fallback。
- workspace mode 下缺少 session id 时 fallback 到 workspace active plan。
- 无效 binding JSON 会 fallback，且不 crash。
- 带 path traversal 的 plan id 被拒绝。
- binding 指向不存在的 plan 时被忽略。

### 13.2 Hook Tests

- binding 存在时，`UserPromptSubmit` 注入 session-bound plan。
- binding 存在时，`PostToolUse` 追加到 session-bound plan 的 `progress.md`。
- workspace active plan 被另一个对话切换后，已绑定 session 的 effective plan 不变。
- `PreToolUse` 和 `UserPromptSubmit` 使用同一个 effective plan。
- `Stop` 检查 session-bound plan 的 phase 状态。
- strict mode 缺少 session id 时仍输出 denial diagnostic。
- strict mode 下 attached 但 unbound 的 session 在未开启 `require_binding` 时仍 fallback。
- strict mode 开启 `require_binding` 后拒绝 unbound session。

### 13.3 CLI Tests

- `init --bind-session` 在设置 `PWF_SESSION_ID` 时创建 plan 和 binding。
- `init --bind-session --no-workspace-active` 不覆盖 `.active_plan`。
- `switch --session` 写 binding 文件。
- `switch --workspace` 写 `.active_plan`。
- `switch --clear-session` 删除 binding 文件。
- `status` 显示 workspace active、session binding 和 effective plan。
- `doctor` 对多个 session 共享 workspace fallback 发出 warning。

### 13.4 Progress Lock Tests

- 两次 append 保留完整 auto record 边界。
- 锁 timeout 时 fail-open，且不破坏已有 progress。
- auto record 包含 `Session` 和 `Plan-Source`。

## 14. 实施任务

### Task 1: Add Plan Resolution Model

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] 添加 `PlanResolution` dataclass。
- [ ] 添加基于 SHA-256 的 session-key helper。
- [ ] 添加 plan-id validation helper。
- [ ] 添加 binding read helper。
- [ ] 添加 `resolve_planning_context(root, env=None, session_id=None)`。
- [ ] 保留 `planning_paths(root)` 作为兼容 wrapper。
- [ ] 添加 resolver tests。

### Task 2: Route Hooks Through Session-Aware Resolution

**Files:**
- Modify: `.codex/hooks/session_start.py`
- Modify: `.codex/hooks/user_prompt_submit.py`
- Modify: `.codex/hooks/pre_tool_use.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Modify: `.codex/hooks/stop.py`
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] 从 hook payload 读取 `session_id` 并传入 render/append helpers。
- [ ] 确保 prompt、pre-tool、post-tool、stop 对同一个 payload 解析到同一个 plan。
- [ ] 添加 session-bound injection 和 progress append hook tests。

### Task 3: Add Binding CLI

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`
- Test: `tests/test_plan_doctor.py`

- [ ] 给 `init` 添加 `--bind-session` 和 `--no-workspace-active`。
- [ ] 给 `switch` 添加 `--session`、`--workspace` 和 `--clear-session`。
- [ ] 给 `status` 添加 session binding 和 effective plan 输出。
- [ ] 给 `doctor` 添加 session binding diagnostics。
- [ ] 添加 CLI 和 doctor tests。

### Task 4: Add Strict Binding Enforcement Option

**Files:**
- Modify: `.codex/hooks/codex_hook_adapter.py`
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_hooks.py`
- Test: `tests/test_plan_doctor.py`

- [ ] 严格解析 `PWF_STRICT_REQUIRES_BINDING` boolean。
- [ ] 从 `.planning/session-policy.json` 读取 `require_binding`。
- [ ] 只在 binding enforcement 开启时拒绝 strict unbound sessions。
- [ ] 为 unbound strict sessions 输出清晰 diagnostics。
- [ ] 在 doctor 中报告 enforcement 状态。

### Task 5: Add Progress Append Lock and Source Metadata

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py` if parsing needs source metadata awareness
- Test: `tests/test_hooks.py`
- Test: `tests/test_progress_compaction.py`

- [ ] 为 `progress.md` append 添加本地 lock helper。
- [ ] 给 auto records 添加 `Session` 和 `Plan-Source` 字段。
- [ ] 确保现有 compaction 和 recent-record parsing 能容忍新增字段。
- [ ] 添加 lock 行为和 metadata tests。

### Task 6: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py`

- [ ] 文档说明 workspace active plan 和 session binding 的区别。
- [ ] 文档说明 `plan.py switch --session`。
- [ ] 文档说明 `plan.py init --bind-session`。
- [ ] 文档说明 strict binding enforcement。
- [ ] 添加文档一致性测试。

### Task 7: Verification and Release Readiness

**Files:**
- All modified files.

- [ ] Run `python -m unittest tests.test_hooks -v`.
- [ ] Run `python -m unittest tests.test_plan_cli tests.test_plan_doctor tests.test_progress_compaction tests.test_project_consistency -v`.
- [ ] Run `python -m unittest discover -v`.
- [ ] Run `git diff --check`.
- [ ] Run `python .codex\skills\planning-with-files\scripts\plan.py doctor`.
- [ ] Review `git diff --stat`.
- [ ] Commit implementation changes on the feature branch.

## 15. 发布和迁移策略

推荐发布节奏：

1. 先发布 opt-in session binding，同时保留 workspace 默认行为。
2. 在 doctor 中增加“多个 session 共享 workspace active plan”的 warning。
3. 收集 `--session` 和 `--bind-session` 的易用性反馈。
4. 如果未来 Codex 总能稳定提供 `session_id`，再考虑让 `/pwf-init` 自动绑定当前 session。
5. 在 major release 或明确公告后，再考虑让 strict mode 默认要求 binding。

## 16. 待确认问题

1. slash command wrapper 在 Codex 内调用时，是否应该自动加 `--session`，还是让用户显式选择？
2. `/pwf-switch` 是否应该永远默认 workspace 行为，还是当检测到多个 session 时提示用户？
3. 多个对话有意共享同一任务时，默认注入所有 recent progress，还是只注入当前 session 的 recent records？
4. Codex desktop 的 `session_id` 在 context compaction、resume 和 thread continuation 后是否稳定？
5. 如果 Codex 未来暴露更稳定的 thread id，binding 应该继续使用 `session_id`，还是优先使用 thread id？

## 17. 成功标准

- 同一个项目中的两个对话可以绑定到不同 plan id。
- 一个对话切换 workspace active plan，不会改变另一个已绑定对话的 effective plan。
- Hook prompt context 和 `PostToolUse` progress append 指向同一个 effective plan。
- 现有单任务项目无需新配置，行为保持兼容。
- `doctor` 能在用户被混入问题惊到之前提示潜在共享风险。
- 测试覆盖 resolver 优先级、无效 binding、strict-mode diagnostics、CLI binding commands 和 progress metadata。
