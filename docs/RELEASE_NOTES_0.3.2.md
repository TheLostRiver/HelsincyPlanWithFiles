# Helsincy Plan With Files v0.3.2 Release Notes

Release date: 2026-06-19

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.3.2-codex.zip
```

Use the `full.zip` package or a source checkout only when you need repository history, tests, and development files.

`v0.3.2` is a patch release focused on a cleaner planning-file ownership model. It clarifies that `progress.md` is an objective hook-written auto-record log, moves interpretive notes and test conclusions toward `findings.md`, keeps phase/status ownership in `task_plan.md`, and adds a `PreCompact` reminder before Codex context compaction.

## 中文

### 这次解决了什么？

`v0.3.2` 解决的是一个容易让 agent 误会的边界问题：旧文案里有些地方把 `progress.md` 描述成“agent 主动维护的 session log / test results / error log”，但当前设计已经把它定位为 hooks 写入的客观 auto records。

如果继续让 agent 手动向 `progress.md` 写日常总结，会带来两个问题：

- 客观记录和主观总结混在一起，恢复上下文时不容易判断哪些是工具实际写入、哪些是 agent 的解释。
- `progress.md` 作为 hot log 会变长，手写总结会挤占真正有价值的最近文件变更记录。

这个版本把边界重新收紧：

```text
task_plan.md   # 阶段、目标、当前状态
findings.md    # 研究发现、测试结论、错误分析、决策和外部资料摘要
progress.md    # hooks 写入的客观 auto records 和文件变更记录
```

### progress.md 现在更明确是 hook-owned

以下位置的提示已经统一改写：

- Python hook runtime 的 `PostToolUse` 和 `Stop` 提示。
- shell fallback hooks：`.codex/hooks/post-tool-use.sh` 和 `.codex/hooks/stop.sh`。
- 兼容检查脚本：`check-complete.sh` 和 `check-complete.ps1`。
- Skill 文档和 hook 示例。
- README、FAQ、task plan 模板和 progress 模板。

新的提示不再说“确保 progress.md 最新”或“把刚做的事写进 progress.md”。它会告诉 agent：

- 阶段完成与否更新到 `task_plan.md`。
- 测试结论、错误分析、决策和解释性笔记写到 `findings.md`。
- `progress.md` 保持为 hooks 写入的客观日志。

### 初始化模板更不容易误导 agent

`progress.md` 模板从“手写会话日志”改成了“Hook-Written Auto Records”结构。

旧模板里的这些手写区域被移除：

- session/phase action log
- test results table
- error log table
- “完成阶段或遇到错误后更新”的提醒

同时，模板保留了 5 问恢复检查，但它现在是只读恢复指引，而不是要求 agent 手写 progress entries：

```text
我在哪里？ -> task_plan.md 中的当前阶段/状态
我要去哪里？ -> task_plan.md 中的剩余阶段
目标是什么？ -> task_plan.md 中的目标
我学到了什么？ -> findings.md
哪些文件发生过变化？ -> 本文件中的 hook auto records
```

这也保留了中文模板初始化测试依赖的 `## 5 问恢复检查` 标题，避免因为文案收紧而造成模板兼容性回归。

### 新增 PreCompact 提醒

这个版本也包含 `PreCompact` hook。它会在 Codex 上下文压缩前给 agent 一个简短提醒：

- 保持 `task_plan.md` 阶段/状态最新。
- 把解释性笔记放进 `findings.md`。
- 保持 `progress.md` 作为 hook-written objective log。

这个 hook 只提醒，不会写文件、不会 compact progress、也不会注入 planning 文件内容。它复用 Python planning resolver，因此会遵守 session ownership；如果 plan attestation 已启用，它会报告当前 plan hash，作为压缩前的锚点。

### 对现有用户的影响

这是文案、模板和 hook 提示边界的 patch release，不改变 `.planning/` 数据格式，也不要求迁移已有任务。

如果你已有旧任务：

- 旧的 `progress.md` 内容会继续保留。
- 新的 hook 提示会从安装新版 `.codex/` 后生效。
- 后续建议把测试结论和错误分析写到 `findings.md`，不要再让 agent 手动扩写 `progress.md`。

### 升级

从 `v0.3.1` 升级：直接覆盖目标项目里的 `.codex/`，保留你的 `.planning/` 数据即可。推荐普通用户下载：

```text
HelsincyPlanWithFiles-v0.3.2-codex.zip
```

## English

### What does this release solve?

`v0.3.2` fixes an ownership-boundary problem in the planning files. Some older prompts still described `progress.md` as an agent-maintained session log for actions, test results, or errors, but the current design treats it as the objective auto-record log written by hooks.

Letting agents hand-write routine summaries into `progress.md` causes two kinds of confusion:

- Objective tool records and interpretive agent summaries become mixed, making recovery less clear.
- `progress.md` is the hot log used for recent objective context; manual summaries can crowd out the more useful recent file-change records.

This release tightens the file roles:

```text
task_plan.md   # phases, goal, current status
findings.md    # discoveries, test conclusions, errors, decisions, external summaries
progress.md    # objective hook-written auto records and file change records
```

### progress.md ownership is now explicit

The wording is now aligned across:

- Python hook runtime `PostToolUse` and `Stop` messages.
- shell fallback hooks: `.codex/hooks/post-tool-use.sh` and `.codex/hooks/stop.sh`.
- compatibility scripts: `check-complete.sh` and `check-complete.ps1`.
- Skill docs and hook examples.
- README, FAQ, task plan templates, and progress templates.

The new prompts no longer use manual freshness wording for `progress.md`. Instead, they direct the agent to:

- update phase/status in `task_plan.md`;
- put test conclusions, error analysis, decisions, and interpretive notes in `findings.md`;
- leave `progress.md` as the objective log maintained by hooks.

### Initialization templates are less misleading

The `progress.md` template has been changed from a hand-written session-log template into a "Hook-Written Auto Records" template.

These old manual sections were removed:

- session/phase action log
- test results table
- error log table
- reminders to update the file after each phase or error

The 5-question recovery check remains, but it is now clearly read-only guidance rather than a prompt to hand-write progress entries:

```text
Where am I? -> Current phase/status in task_plan.md
Where am I going? -> Remaining phases in task_plan.md
What's the goal? -> Goal statement in task_plan.md
What have I learned? -> findings.md
What changed? -> Hook-written auto records in this file
```

This also preserves the Chinese template heading `## 5 问恢复检查`, avoiding a template compatibility regression while keeping the new ownership model intact.

### Added a PreCompact reminder

This release also includes a `PreCompact` hook. Before Codex context compaction, it reminds the agent to:

- keep `task_plan.md` phase/status current;
- capture interpretive notes in `findings.md`;
- leave `progress.md` as the hook-written objective log.

The hook is intentionally non-destructive: it does not write files, does not compact progress, and does not inject planning file contents. It reuses the Python planning resolver, so it respects session ownership; when plan attestation is enabled, it reports the current plan hash as a compaction-time anchor.

### Impact on existing users

This is a patch release for wording, templates, and hook guidance. It does not change the `.planning/` data format and does not require migrating existing tasks.

For existing tasks:

- existing `progress.md` content remains in place;
- the new hook prompts take effect after updating the project `.codex/` directory;
- future test conclusions and error analysis should go to `findings.md`, not manually into `progress.md`.

### Upgrade

From `v0.3.1`: overwrite the target project's `.codex/` directory and keep your existing `.planning/` data. The recommended package for regular users is:

```text
HelsincyPlanWithFiles-v0.3.2-codex.zip
```
