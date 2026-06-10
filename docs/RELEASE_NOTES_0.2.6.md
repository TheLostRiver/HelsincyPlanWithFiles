# Helsincy Plan With Files v0.2.6 Release Notes

Release date: 2026-06-10

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.2.6-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

## 中文

### 这次解决了什么？

`v0.2.6` 让当前会话的任务上下文注入更容易控制。以前用户想临时增加或减少 PWF 注入到 Codex 上下文里的任务信息，通常要记住环境变量。现在可以直接用 `/pwf-context-*` 命令切换当前会话的模式。

这对上下文压缩后的恢复尤其有用：如果你担心 Codex 继续任务时拿到的上下文太少，可以把当前会话切到 expanded 或 deep；如果你想减少上下文占用，可以切回 lean 或 default。

### 新增 context profile 快捷命令

可用命令：

```text
/pwf-context-expanded
/pwf-context-deep
/pwf-context-default
/pwf-context-lean
/pwf-context-status
```

这些命令只影响当前会话，不会替你切换到其他会话的任务，也不会放松已有的 workspace/strict 和 task lease 安全边界。

常见用法：

```text
/pwf-context-expanded
/pwf-context-status
```

如果你希望工具注入更多任务计划和最近进度，用 expanded。需要更深恢复时用 deep。任务很短、上下文预算比较紧时，用 lean 或 default。

### 新增 context injection notice 开关

可用命令：

```text
/pwf-context-notice-auto
/pwf-context-notice-on
/pwf-context-notice-off
```

notice 用来提示“工具已经自动注入了任务上下文信息”，并显示一个大致占用估算。这个数值只是估算，适合帮助用户判断当前会话是不是在使用较重的上下文注入模式。

### 小维护项

本版本也忽略了本地 `dist/` 发布输出目录。这样生成 release zip 后，工作区不会因为本地包文件而变脏。`dist/` 仍然用于本地打包，正式发布资产继续通过 GitHub Release 上传。

### 用户需要做什么？

普通用户继续下载推荐包：

```text
HelsincyPlanWithFiles-v0.2.6-codex.zip
```

安装方式不变：把包里的 `.codex/` 复制到目标项目根目录，重启 Codex，批准 hook 信任提示，然后运行：

```text
/pwf-doctor
```

如果上下文压缩后想确认当前任务和注入模式，建议运行：

```text
/pwf-status
/pwf-context-status
```

### 文档更新

本版本同步更新了 [FAQ](FAQ.md)、README、[普通用户使用指南](USER_GUIDE.zh-CN.md) 和 changelog，说明 context profile 快捷命令、context injection notice、上下文压缩后的任务恢复提示、workspace/strict 边界，以及推荐的 `v0.2.6` 安装包。

## English

### What changed?

`v0.2.6` makes the current session's task context injection easier to control. Previously, users usually needed to remember environment variables when they wanted more or less PWF task context in Codex. Now the current session can switch profiles through `/pwf-context-*` commands.

This is especially useful after context compaction. If you want Codex to recover with more task context, switch the current session to expanded or deep. If you want to reduce prompt usage, switch back to lean or default.

### New context profile shortcuts

Available commands:

```text
/pwf-context-expanded
/pwf-context-deep
/pwf-context-default
/pwf-context-lean
/pwf-context-status
```

These commands affect only the current session. They do not switch you to another session's task, and they do not loosen the existing workspace/strict or task lease safety boundaries.

Common flow:

```text
/pwf-context-expanded
/pwf-context-status
```

Use expanded when you want more task plan and recent progress context. Use deep for heavier recovery. Use lean or default when the task is short or prompt budget is tight.

### New context injection notice controls

Available commands:

```text
/pwf-context-notice-auto
/pwf-context-notice-on
/pwf-context-notice-off
```

Notices can tell users that task context was automatically injected and show an approximate prompt-size estimate. The number is an estimate, useful for understanding whether the current session is using a heavier context injection profile.

### Small maintenance item

This release also ignores the local `dist/` release output directory. Generated release zip files no longer make the worktree appear dirty. `dist/` is still used for local packaging, while official assets are uploaded through GitHub Releases.

### What should users do?

Most users should download:

```text
HelsincyPlanWithFiles-v0.2.6-codex.zip
```

Installation is unchanged: copy `.codex/` from the package into the target project root, restart Codex, approve the hook trust prompt, then run:

```text
/pwf-doctor
```

After context compaction, run these when you want to confirm the current task and injection profile:

```text
/pwf-status
/pwf-context-status
```

### Documentation updates

This release updates the [FAQ](FAQ.md), READMEs, [plain-language user guide](USER_GUIDE.zh-CN.md), and changelog with context profile shortcuts, context injection notices, task recovery after context compaction, workspace/strict boundaries, and the recommended `v0.2.6` package.
