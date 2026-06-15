# Helsincy Plan With Files v0.3.0 Release Notes

Release date: 2026-06-15

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.3.0-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

This release removes cross-session task sharing (a `--share` flag that was easy to misuse), adds per-session pause/resume for context injection, makes the context-injection notice visible on all profiles with a concise single line, and makes `/pwf-compact` keep-records default profile-aware. It is backward compatible: historical `.task-lease.json` files carrying `shared=true` remain readable and do not block access.

## 中文

### 这次解决了什么？

`v0.3.0` 是一次会话注入体验 + 归档优化的版本。它移除了一个设计上容易出问题的功能（跨会话共享 PWF 任务），并新增了用户长期需要的暂停/恢复能力，同时让上下文占用更透明。

### 移除了多会话共享 PWF 任务（`--share`）

`switch --share` / `use --share` 不再可用。原因：把多个会话的 PWF 任务记录塞进同一上下文，会打乱每个 agent 的任务记忆；十几个会话并发共享同一任务，还会导致 `progress.md` 写入竞态和锁超时。

替代方案：每个会话用 `/pwf-init` 创建自己的任务（默认行为）。如果确实需要两个会话操作同一逻辑任务，用 `plan.py switch <plan-id> --session --force-claim` 显式接管——单一 owner，没有共享写入。

向后兼容：旧的 `.planning/<plan-id>/.task-lease.json` 里若仍带 `shared=true`，仍可被读取，不会触发 ownership denial。详见 `docs/REMOVED_CROSS_SESSION_SHARE.md`。

### 新增 `/pwf-pause`、`/pwf-resume`

- `/pwf-pause`（等价 `plan.py context pause`）暂停当前会话的 SessionStart / UserPromptSubmit / PreToolUse 上下文注入。
- **PostToolUse 的 progress 记录仍继续工作**——暂停只影响"注入给 agent 看的上下文"，不影响"客观文件变更日志"。
- `/pwf-resume` 恢复注入。未暂停时用 resume 会提示"未暂停，无需恢复"；已暂停时再 pause 会提示"已暂停"，避免静默 no-op。
- 暂停状态存 `.planning/session-context/<key>.json` 的 `paused` 字段，只影响当前会话。

适合开个"侧边对话"问不相干的小问题、又不想每次提示被一大段任务上下文挤占的场景。

### 上下文注入提示现在所有档位都显示

`/pwf-context-notice-auto` 之前只在 expanded/deep 档或 SessionStart 才显示。现在所有档位（含 default/lean）每次注入都显示一行精简提示：

```text
[planning-with-files] context: profile=default, progress=tail 80 lines, ~1.2k chars (~300 tokens). Upgrade: /pwf-context-expanded, /pwf-context-deep. Mute: /pwf-context-notice-off.
```

档位建议是智能的：default/lean 建议升级，expanded 建议更深+降档，deep 提示已是最深。想完全静音用 `/pwf-context-notice-off`。

`/pwf-doctor` 和 `/pwf-context-status` 现在也会报告当前会话的 paused 状态。

### `/pwf-compact` 保留记录数按档位自动决定

归档（context compaction）时保留多少条最近 auto records，现在默认按当前 context profile 自动决定：

| Profile | 默认保留 |
|---|---|
| lean | 10 |
| default | 30 |
| expanded | 60 |
| deep | 100 |

这样归档后活跃 progress 与档位的注入预算匹配，不会出现"想注入 40 条但归档只剩 30 条"。优先级：`PWF_COMPACT_KEEP_RECORDS` 环境变量 > 显式 `--keep-records` flag > profile 默认。compact 输出会告诉你最终用了哪个值和来源。

### 升级

从 v0.2.7 升级：直接覆盖 `.codex/`。如果你之前用过 `--share`，相关任务会保持原样，不会丢失数据；用 `/pwf-tasks` 查看现有任务，需要的话用 `plan.py switch <plan-id> --session --force-claim` 重新绑定。

## English

### What does this release solve?

`v0.3.0` is a session-injection experience + archiving optimization release. It removes a feature that was easy to misuse (cross-session PWF task sharing), adds the long-requested pause/resume capability, makes context-injection cost transparent on all profiles, and makes `/pwf-compact` keep-records default profile-aware.

### Removed cross-session task sharing (`--share`)

`switch --share` / `use --share` are no longer available. Rationale: merging multiple sessions' PWF task records into one shared context scrambles each agent's task memory; a dozen sessions concurrently sharing one task also causes `progress.md` write contention and lock timeouts.

Replacement: each session creates its own task with `/pwf-init` (the default behavior). If two sessions genuinely need to work on the same logical task, use `plan.py switch <plan-id> --session --force-claim` for explicit takeover — single owner, no shared writes.

Backward compatible: historical `.planning/<plan-id>/.task-lease.json` files carrying `shared=true` remain readable and do not trigger ownership denial. See `docs/REMOVED_CROSS_SESSION_SHARE.md`.

### Added `/pwf-pause` and `/pwf-resume`

- `/pwf-pause` (equivalent to `plan.py context pause`) pauses SessionStart / UserPromptSubmit / PreToolUse context injection for the current session.
- **PostToolUse progress recording keeps working** — pause only affects "context injected into the agent", not the "objective file change log".
- `/pwf-resume` restores injection. Running it while not paused shows "not paused; nothing to resume"; pausing while already paused shows "already paused", avoiding silent no-ops.
- The paused state is stored in `.planning/session-context/<key>.json` under a `paused` field, affecting only the current session.

Useful for opening a "side conversation" to ask an unrelated quick question without having every prompt crowded out by task context.

### Context-injection notice now shows on all profiles

`/pwf-context-notice-auto` previously only showed on expanded/deep profiles or SessionStart. Now all profiles (including default/lean) show a concise single line on every injection:

```text
[planning-with-files] context: profile=default, progress=tail 80 lines, ~1.2k chars (~300 tokens). Upgrade: /pwf-context-expanded, /pwf-context-deep. Mute: /pwf-context-notice-off.
```

The profile hint is smart: default/lean suggests upgrading, expanded suggests deeper + reduce, deep notes you're already at the deepest. To mute completely use `/pwf-context-notice-off`.

`/pwf-doctor` and `/pwf-context-status` now also report the current session's paused state.

### `/pwf-compact` keep-records default is now profile-aware

How many recent auto records to keep when rolling over (context compaction) now defaults to the current context profile:

| Profile | Default keep |
|---|---|
| lean | 10 |
| default | 30 |
| expanded | 60 |
| deep | 100 |

This keeps the active progress after rollover aligned with the profile's injection budget, so you won't hit "want to inject 40 records but only 30 survived the rollover". Priority: `PWF_COMPACT_KEEP_RECORDS` env > explicit `--keep-records` flag > profile default. compact output reports which value and source it used.

### Upgrade

From v0.2.7: overwrite `.codex/`. If you previously used `--share`, those tasks stay as-is and no data is lost; run `/pwf-tasks` to see existing tasks, and rebind with `plan.py switch <plan-id> --session --force-claim` if needed.
