# Helsincy Plan With Files v0.2.5 Release Notes

Release date: 2026-06-10

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.2.5-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

## 中文

### 这次解决了什么？

`v0.2.5` 让同一项目多会话并发更省心：`/pwf-init` 和 `plan.py init` 现在默认优先绑定当前会话。只要工具能识别当前会话，新建任务就会自动属于这个会话，并写入 task lease。

这意味着用户在同一个项目里开第二个、第三个 Codex 会话时，正常创建 PWF 任务即可。每个会话的新任务会默认绑定到自己的会话，不会因为另一个会话停止运行，就自动切到别的会话任务上继续写 `progress.md`。

### 默认行为

普通流程不需要额外参数：

```text
/pwf-init My Task
```

或：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task"
```

如果当前会话可识别，新任务会同时：

- 绑定当前 session。
- 写入 task lease。
- 保持 `.planning/.active_plan` 作为兼容 fallback。

`workspace active` 仍然是兼容层，方便旧流程或单会话项目继续工作；真正的多会话隔离优先靠 session binding 和 task lease。

### 兼容与安全选项

需要旧的 workspace-only 行为时，可以显式使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-bind-session
```

想创建只属于当前会话、不更新 workspace active 的任务时，可以使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-workspace-active
```

`--no-workspace-active` 需要能识别当前 session；否则命令会拒绝执行，避免生成没有 workspace active、也没有 session binding 的悬空任务。

跨会话接管或共享任务仍然必须显式表达意图：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --claim
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --share
```

即使原来的会话已经停止，新的会话也不会静默接管别人的 PWF 任务。

### 用户需要做什么？

单会话用户可以继续照常使用：

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

同一项目开多个 Codex 会话时，也可以照常在每个会话里创建任务。需要确认当前会话能看到哪些任务时，运行：

```text
/pwf-tasks
```

上下文压缩后继续任务时，建议先运行 `/pwf-status` 或 `/pwf-tasks` 确认当前会话绑定的任务，再继续执行。

### 文档更新

本版本同步更新了 [FAQ](FAQ.md)、README、[普通用户使用指南](USER_GUIDE.zh-CN.md) 和 changelog，说明默认会话绑定、`--no-bind-session`、`--no-workspace-active`、workspace active 兼容层、显式 claim/share，以及推荐的 `v0.2.5` 安装包。

## English

### What changed?

`v0.2.5` makes concurrent work in the same project easier: `/pwf-init` and `plan.py init` are now session-first by default. When the tool can identify the current conversation, a new task binds to that session automatically and claims a task lease.

This means users can open a second or third Codex conversation in the same project and create PWF tasks normally. Each conversation's new task defaults to that conversation, instead of silently switching to another conversation's task and writing to the wrong `progress.md`.

### Default behavior

The normal flow needs no extra flag:

```text
/pwf-init My Task
```

Or:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task"
```

When the current session is identifiable, the new task will:

- Bind to the current session.
- Write a task lease.
- Keep `.planning/.active_plan` as a compatibility fallback.

`workspace active` remains a compatibility fallback for older flows and single-session projects. Multi-session isolation is handled by session binding and task leases.

### Compatibility and safety options

To intentionally use the old workspace-only behavior:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-bind-session
```

To create a task that belongs only to the current session without updating workspace active:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-workspace-active
```

`--no-workspace-active` requires an identifiable current session. Without one, the command is rejected so it cannot create a task with neither workspace active nor session binding.

Cross-session claim or share still requires explicit intent:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --claim
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --share
```

Even if the original conversation has stopped, a new conversation will not silently take over another conversation's PWF task.

### What should users do?

Single-session users can keep using the familiar flow:

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

When several Codex conversations are open in the same project, create tasks normally in each conversation. To check which tasks are visible to the current session, run:

```text
/pwf-tasks
```

After context compaction, run `/pwf-status` or `/pwf-tasks` before continuing so you can confirm which task is bound to the current session.

### Documentation updates

This release updates the [FAQ](FAQ.md), READMEs, [plain-language user guide](USER_GUIDE.zh-CN.md), and changelog with default session binding, `--no-bind-session`, `--no-workspace-active`, the workspace active compatibility fallback, explicit claim/share flows, and the recommended `v0.2.5` package.
