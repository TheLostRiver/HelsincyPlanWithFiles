# Helsincy Plan With Files v0.2.3 Release Notes

Release date: 2026-06-09

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.2.3-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

## 中文

### 这次解决了什么？

`v0.2.3` 聚焦两个长任务场景：同一项目里的多会话并发，以及上下文压缩后的可控恢复。

同项目多会话现在可以把每个 Codex 对话绑定到自己的 PWF 任务。这样一个对话切换任务或继续工作时，不会自动写进另一个对话的 `progress.md`：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

任务归属也更严格：如果 workspace active task 已经由另一个 session 拥有，新的未绑定 session 不会自动接管它；即使 owner 已经 stale，也必须显式选择 `--force-claim`、`--share` 或 `--release-session`。`--legacy --bind-session` 会被拒绝，因为 legacy 根目录单任务模式不适合多会话隔离。

上下文注入现在支持 profile：

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
$env:PWF_INCLUDE_FINDINGS = "1"
```

`lean/default/expanded/deep/custom` 可以在默认兼容、长任务开发、上下文压缩恢复和高级调参之间切换。`findings.md` 仍然是显式 opt-in，只有设置 `PWF_INCLUDE_FINDINGS=1` 后才会注入。

### 用户需要做什么？

大多数单会话用户不需要改配置。升级后继续使用默认 `workspace` 模式：

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

如果同一个项目同时开多个 Codex 会话，请在每个会话开始工作前绑定自己的任务：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

如果希望 strict mode 不只要求 session 已 attach，还要求该 session 已绑定有效任务，可以设置：

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```

运行 `/pwf-doctor` 或 `/pwf-status` 可以查看当前 `workspace`/`strict` 模式、session binding、task lease、context profile、findings 是否开启，以及 progress 注入模式。

### 文档更新

本版本更新了 [FAQ](FAQ.md)、README 和 changelog，集中说明 session task binding、task ownership、上下文压缩后的 context compaction 恢复、workspace/strict 选择、context profiles、`PWF_INCLUDE_FINDINGS` 和推荐的 `v0.2.3` 安装包。

## English

### What changed?

`v0.2.3` focuses on two long-running workflow cases: concurrent Codex conversations in the same project, and controlled recovery after context compaction.

Multiple conversations in one project can now bind to different PWF tasks. A conversation can continue or switch its own task without automatically writing into another conversation's `progress.md`:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

Task ownership is stricter as well. If the workspace active task is already owned by another session, an unbound new session will not automatically take it over; even a stale owner requires an explicit `--force-claim`, `--share`, or `--release-session` decision. `--legacy --bind-session` is rejected because the legacy root-level single-task mode is not suitable for multi-session isolation.

Context injection now supports profiles:

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
$env:PWF_INCLUDE_FINDINGS = "1"
```

`lean/default/expanded/deep/custom` lets users choose between compatible defaults, large-feature work, context compaction recovery, and advanced tuning. `findings.md` remains explicitly opt-in and is injected only when `PWF_INCLUDE_FINDINGS=1` is set.

### What should users do?

Most single-session users do not need new configuration. After upgrading, keep using the default `workspace` mode:

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

If several Codex conversations are open in the same project, bind each conversation to its own task before relying on hooks:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

To make strict mode require a valid task binding as well as an attached session, set:

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```

Run `/pwf-doctor` or `/pwf-status` to inspect the current `workspace`/`strict` mode, session binding, task lease, context profile, findings state, and progress injection mode.

### Documentation updates

This release updates the [FAQ](FAQ.md), READMEs, and changelog with session task binding, task ownership, context compaction recovery, workspace/strict selection, context profiles, `PWF_INCLUDE_FINDINGS`, and the recommended `v0.2.3` package.
