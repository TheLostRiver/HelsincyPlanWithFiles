# Helsincy Plan With Files v0.2.2 Release Notes

Release date: 2026-06-06

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.2.2-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

## 中文

### 这次解决了什么？

`v0.2.2` 重点修复上下文压缩后的 hook 静默问题。过去工具会从 `.planning/sessions/` 推断 session isolation，这会让一些已经存在的 session 状态影响默认恢复流程。结果是 Codex context compaction、resume 或新一轮用户提示后，有时能看到 planning context 提示，有时却没有明显提示。

现在 session policy 是显式的：

- 默认是 `workspace` 模式，hook 使用 `.planning/.active_plan` 恢复当前任务。
- `.planning/sessions/` 目录存在时，不会自动让默认 hook 静默。
- 需要多会话隔离时，再显式开启 `strict` 模式。
- strict 模式缺少或未 attach `session_id` 时，会输出诊断消息，不再静默跳过。

### 用户需要做什么？

大多数用户不需要配置任何 session policy。升级后继续使用：

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

如果 `/pwf-doctor` 显示 `session mode: workspace`，这就是推荐默认值。

只有当同一个项目里多个 Codex 会话必须互不共享 active plan 时，才设置：

```powershell
$env:PWF_SESSION_MODE = "strict"
```

或创建：

```json
{"mode":"strict"}
```

文件路径是 `.planning/session-policy.json`。

### 文档更新

本版本新增 [FAQ](FAQ.md)，集中解释安装、命令不可见、上下文压缩、workspace/strict 选择、`/pwf-doctor` 排障、`/pwf-compact`、`/pwf-attest` 和 `PWF_LANG=zh-CN`。

## English

### What changed?

`v0.2.2` focuses on the hook silence users could see after context compaction. Older behavior inferred session isolation from `.planning/sessions/`, so stale session state could affect the default recovery path. After Codex context compaction, resume, or the next user prompt, users could sometimes see planning context and sometimes see no visible hook prompt.

Session policy is now explicit:

- `workspace` mode is the default, and hooks recover the current task through `.planning/.active_plan`.
- The presence of `.planning/sessions/` no longer makes default hooks silently skip context.
- Use `strict` mode only when several Codex sessions in the same project must not share the active plan.
- In strict mode, missing or unattached `session_id` values produce diagnostics instead of silent skips.

### What should users do?

Most users do not need to configure session policy. After upgrading, continue with:

```text
/pwf-doctor
/pwf-init My Task
/pwf-status
```

If `/pwf-doctor` reports `session mode: workspace`, you are on the recommended default.

Enable strict mode only for explicit per-session isolation:

```powershell
$env:PWF_SESSION_MODE = "strict"
```

or create `.planning/session-policy.json`:

```json
{"mode":"strict"}
```

### Documentation updates

This release adds [FAQ](FAQ.md), covering installation, missing slash commands, context compaction, choosing workspace or strict mode, `/pwf-doctor` troubleshooting, `/pwf-compact`, `/pwf-attest`, and `PWF_LANG=zh-CN`.
