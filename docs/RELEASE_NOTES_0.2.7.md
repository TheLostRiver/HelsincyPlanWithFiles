# Helsincy Plan With Files v0.2.7 Release Notes

Release date: 2026-06-11

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.2.7-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

## 中文

### 这次解决了什么？

`v0.2.7` 是一次多会话安全加固版本。它修复了同一项目里多个 Codex 会话并发使用 PWF 时的三个边界问题，重点是防止不同会话把进度写入同一个不该使用的 PWF 任务。

这次发布不改变普通用户的主要工作流。默认情况下，能识别当前会话时，`/pwf-init` 和 `plan.py init` 仍会创建并绑定当前会话自己的任务；上下文压缩后也仍建议用 `/pwf-status`、`/pwf-tasks` 或 `/pwf-context-status` 确认当前任务。

### `PLAN_ID` 只负责路由，不负责授权

以前 `PLAN_ID` 可以显式选择要注入或记录的任务，但这条路径曾经绕过 task ownership 判断。现在 `PLAN_ID` 只是 routing override，不是 permission override。

如果指定的任务由另一个 session 独占，hook 会拒绝写入和注入，并提示 ownership 冲突。只有以下情况才允许继续使用：

- 当前 session 就是 owner
- 任务已 shared
- 任务已 released
- 用户显式使用 claim、share 或 release 相关命令改变 ownership

### stale 诊断改用 owner session heartbeat

task ownership 仍存放在 `.planning/<plan-id>/.task-lease.json`。但 owner 是否 stale，现在优先看 `.planning/session-leases/<owner>.json` 里的 owner session heartbeat。

这能避免 `.task-lease.json` 本身很新、但真正的 owner session 已经不再活跃时被误报为 active。找不到 owner session lease 时，才回退到 `.task-lease.json` 的 `updated_at`，用于兼容旧数据。

注意：stale 仍然只是诊断状态，不是自动接管许可。跨会话任务仍必须显式 `--force-claim`、`--share` 或 `--release-session`。

### hook 会话识别与 CLI 对齐

Python hooks 现在按这个顺序识别当前会话：

```text
payload session_id -> PWF_SESSION_ID -> CODEX_THREAD_ID
```

这与 CLI 行为一致。普通 Codex 会话通常不再需要手动设置 `PWF_SESSION_ID`，也能正确使用 session binding。

### workspace/strict 边界不变

本版本不放宽 workspace/strict 的安全边界。workspace mode 仍用于兼容单会话和旧工作流；strict mode 仍是显式 opt-in，并且可以继续用 `PWF_STRICT_REQUIRES_BINDING=1` 要求 session 已 attach 且已有有效 binding。

### 用户需要做什么？

普通用户下载：

```text
HelsincyPlanWithFiles-v0.2.7-codex.zip
```

安装方式不变：把包里的 `.codex/` 复制到目标项目根目录，重启 Codex，批准 hook 信任提示，然后运行：

```text
/pwf-doctor
```

如果你在同一项目里开了多个 Codex 会话，建议每个会话分别运行 `/pwf-init <任务名>` 创建自己的任务。需要查看当前会话能使用哪些任务时，运行：

```text
/pwf-tasks
```

### 文档更新

本版本同步更新了 [FAQ](FAQ.md)、README、[普通用户使用指南](USER_GUIDE.zh-CN.md) 和 changelog，说明 `PLAN_ID` 权限边界、owner heartbeat stale 诊断、hook session fallback、上下文压缩后的任务确认方式、workspace/strict 边界，以及推荐的 `v0.2.7` 安装包。

## English

### What changed?

`v0.2.7` hardens multi-session safety. It fixes three boundary issues for concurrent PWF usage in the same project, with the main goal of preventing one Codex session from writing progress into another session's exclusive PWF task.

This release does not change the normal user workflow. When the current session is identifiable, `/pwf-init` and `plan.py init` still create and bind a task for the current session by default. After context compaction, users should still confirm the current task with `/pwf-status`, `/pwf-tasks`, or `/pwf-context-status` when needed.

### `PLAN_ID` routes only; it does not grant permission

`PLAN_ID` can explicitly choose which task a hook should inject or record, but that path previously bypassed task ownership checks. It is now a routing override, not a permission override.

If the selected task is exclusive to another session, hooks deny injection and progress writes with an ownership conflict diagnostic. Access is allowed only when:

- the current session is the owner
- the task is shared
- the task is released
- the user explicitly changes ownership through claim, share, or release commands

### stale diagnostics now use the owner session heartbeat

Task ownership still lives in `.planning/<plan-id>/.task-lease.json`. Owner freshness is now diagnosed from `.planning/session-leases/<owner>.json` when that owner session lease exists.

This avoids reporting a task as active just because `.task-lease.json` was fresh while the actual owner session heartbeat had expired. If the owner session lease is missing, the code falls back to `.task-lease.json` `updated_at` for compatibility with older data.

Stale remains diagnostic only. It is not permission to take over a task automatically. Cross-session task use still requires explicit `--force-claim`, `--share`, or `--release-session`.

### Hook session identity now matches the CLI

Python hooks now resolve the current session in this order:

```text
payload session_id -> PWF_SESSION_ID -> CODEX_THREAD_ID
```

This matches CLI behavior. Ordinary Codex sessions usually do not need to set `PWF_SESSION_ID` manually to use session binding correctly.

### workspace/strict boundaries are unchanged

This release does not loosen workspace/strict safety boundaries. workspace mode remains the compatibility path for single-session and older workflows. strict mode remains explicit opt-in, and `PWF_STRICT_REQUIRES_BINDING=1` can still require both an attached session and a valid binding.

### What should users do?

Most users should download:

```text
HelsincyPlanWithFiles-v0.2.7-codex.zip
```

Installation is unchanged: copy `.codex/` from the package into the target project root, restart Codex, approve the hook trust prompt, then run:

```text
/pwf-doctor
```

If you run multiple Codex sessions in the same project, create a separate task in each session with `/pwf-init <task name>`. To see which tasks the current session can use, run:

```text
/pwf-tasks
```

### Documentation updates

This release updates the [FAQ](FAQ.md), READMEs, [plain-language user guide](USER_GUIDE.zh-CN.md), and changelog with the `PLAN_ID` permission boundary, owner heartbeat stale diagnostics, hook session fallback, task confirmation after context compaction, workspace/strict boundaries, and the recommended `v0.2.7` package.
