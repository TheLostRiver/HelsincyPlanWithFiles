# Helsincy Plan With Files v0.2.4 Release Notes

Release date: 2026-06-10

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.2.4-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

## 中文

### 这次解决了什么？

`v0.2.4` 聚焦同一项目多会话并发时的任务选择体验。`v0.2.3` 已经建立 session binding 和 task lease 安全边界，本版本在这个基础上补上更顺手的选择入口：

```text
/pwf-tasks
/pwf-use <short-id>
```

`/pwf-tasks` 默认只显示当前会话可见的 PWF 任务，并给出可复制的短 ID。其他会话独占的任务默认不会显示，避免用户误复制、误切换到别的会话任务。

`/pwf-use` 可以用 `/pwf-tasks` 显示的短 ID 或完整 plan id 绑定当前会话。默认情况下，它也只会匹配当前会话可见任务，不会因为另一个会话停止运行或 owner stale 就自动接管。

### 安全边界

跨会话操作仍然必须显式表达意图：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py tasks --all
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --claim
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --share
```

`tasks --all` 是只读诊断视图，用来查看为什么某个任务不可见。真正跨 owner 使用任务时，仍然必须显式 `--claim` 或 `--share`，并继续受 workspace/strict 模式、session binding 和 task lease lock 保护。

### 易用性改进

CLI 现在会在 `PWF_SESSION_ID` 缺失时 fallback 到 `CODEX_THREAD_ID`，普通 Codex 会话通常不需要额外手动设置 session 环境变量。

短 ID 也更稳健：如果当前输出集合里两个任务的 6 位短 ID 完全碰撞，显示时会自动扩展到 8、10 或 12 位，确保用户从 `/pwf-tasks` 复制出来的 ID 可以直接交给 `/pwf-use`。

### 用户需要做什么？

单会话用户可以继续使用原有流程：

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

同一项目同时打开多个 Codex 会话时，推荐先运行：

```text
/pwf-tasks
```

看到当前会话可见任务后，再复制短 ID：

```text
/pwf-use <short-id>
```

上下文压缩后恢复任务时，也建议先用 `/pwf-status` 或 `/pwf-tasks` 确认当前会话绑定和可见任务，再继续执行，避免误写到其他任务的 `progress.md`。

### 文档更新

本版本新增了 [普通用户使用指南](USER_GUIDE.zh-CN.md)，并改写 README 开头，让用户先理解“任务记忆本”的用途，再进入命令和高级配置。

同时更新了 [FAQ](FAQ.md)、README 和 changelog，说明 `/pwf-tasks`、`/pwf-use`、默认隐藏其他会话独占任务、显式 claim/share、workspace/strict 边界、上下文压缩后的任务恢复方式，以及推荐的 `v0.2.4` 安装包。

## English

### What changed?

`v0.2.4` focuses on the task-selection experience for concurrent Codex conversations in the same project. `v0.2.3` introduced the session binding and task lease safety boundary; this release adds easier entry points on top:

```text
/pwf-tasks
/pwf-use <short-id>
```

`/pwf-tasks` lists only the PWF tasks visible to the current session by default and prints copyable short IDs. Other sessions' exclusive tasks stay hidden by default, reducing accidental cross-session switching.

`/pwf-use` binds the current session using a short ID or full plan id shown by `/pwf-tasks`. By default it only resolves current-session-visible tasks, so it will not automatically take over another conversation's task just because that conversation stopped running or its owner looks stale.

### Safety boundaries

Cross-session operations still require explicit intent:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py tasks --all
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --claim
python .codex\skills\planning-with-files\scripts\plan.py use <selector> --share
```

`tasks --all` is a read-only diagnostic view for understanding why a task is hidden. Actually crossing ownership boundaries still requires explicit `--claim` or `--share`, and continues to respect workspace/strict mode, session binding, and the task lease lock.

### Usability improvements

The CLI now falls back to `CODEX_THREAD_ID` when `PWF_SESSION_ID` is not set, so ordinary Codex sessions usually do not need manual session environment setup.

Short IDs are more robust as well. If two tasks in the current output set fully collide at six characters, their displayed IDs expand to 8, 10, or 12 characters so an ID copied from `/pwf-tasks` remains usable with `/pwf-use`.

### What should users do?

Single-session users can keep using the existing flow:

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

When several Codex conversations are open in the same project, start with:

```text
/pwf-tasks
```

Then copy the short ID you want:

```text
/pwf-use <short-id>
```

After context compaction, use `/pwf-status` or `/pwf-tasks` to confirm the current session binding and visible tasks before continuing, so progress does not get written to another task's `progress.md`.

### Documentation updates

This release adds a Chinese [plain-language user guide](USER_GUIDE.zh-CN.md) and rewrites the README opening so users understand the "task notebook" purpose before command details and advanced configuration.

It also updates the [FAQ](FAQ.md), READMEs, and changelog with `/pwf-tasks`, `/pwf-use`, hidden-by-default tasks owned by other sessions, explicit claim/share flows, workspace/strict boundaries, task recovery after context compaction, and the recommended `v0.2.4` package.
