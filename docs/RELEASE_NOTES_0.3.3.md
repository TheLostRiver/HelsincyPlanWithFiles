# Helsinky Plan With Files v0.3.3 Release Notes

Release date: 2026-06-19

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.3.3-codex.zip
```

Use the `full.zip` package or a source checkout only when you need repository history, tests, and development files.

`v0.3.3` is a feature and reliability release focused on safer installation, default findings context injection, and compact recovery. It enables `findings.md` tail injection by default in `SessionStart` and `UserPromptSubmit`, routes Codex compact recovery through the normal context renderer, separates user-visible context notices from agent-injected data, updates hook feature-flag docs to `[features] hooks = true`, and improves the semantics of blocked-context notices.

## 中文

### 这次解决了什么？

`v0.3.3` 之前，`findings.md` 内容注入需要显式设置 `PWF_INCLUDE_FINDINGS=1` 才会启用。多数用户不知道这个开关，导致 agent 在上下文恢复时缺少重要的研究发现和决策记录。

同时，Codex 上下文压缩后的恢复路径也没有走正常的 context renderer，压缩后注入的 planning context 可能不完整。context injection notice 作为 hook message 和注入给 agent 的 `additionalContext` 混在一起，既浪费 token 又可能干扰 agent 理解。

这个版本做了五件事：

1. 安装路线区分 Codex CLI 和 Codex App，并使用安全 installer。
2. 默认注入 `findings.md` 有界 tail，保留显式关闭。
3. 压缩恢复复用正常 context renderer。
4. context notice 从 agent 注入数据中分离出来。
5. blocked context 通知的语义更准确。

### 安装更安全

- 普通用户使用 Release 包里的 `install-pwf.ps1` / `install-pwf.sh`，先 dry-run 再安装，不再手动覆盖整个 `.codex/`。
- 干净目标项目会获得项目级 `.codex/config.toml`，内容使用官方当前的 `[features] hooks = true`。
- 不再推荐 `[features].codex_hooks`；这是 Codex 已弃用的旧别名。
- 如果目标项目已有 `.codex/config.toml`，安装器会停止并报告 conflict，请人工检查后添加 `hooks = true` 或用 `codex --enable hooks` 启动 CLI。

### findings 默认注入

`SessionStart` 和 `UserPromptSubmit` 现在默认注入有界的 `findings.md` 尾部内容。

- 不再需要手动设置 `PWF_INCLUDE_FINDINGS=1`。
- 设置 `PWF_INCLUDE_FINDINGS=0` 可以显式关闭。
- 设置 `PWF_FINDINGS_TAIL_LINES=N` 可以调整 tail 窗口。
- findings 仍然使用 delimiter framing 和不可信内容提示。

### 压缩恢复走正常路径

Codex 的 `SessionStart` hook 现在覆盖 `compact` source。

- 压缩后恢复的上下文注入和普通 session start 使用同一套 context renderer，确保注入格式一致。
- `PreCompact` 仍只提醒和报告 attestation，暂不使用 `PostCompact` 做上下文注入。

### context notice 不再污染注入数据

- context injection notice 现在作为用户可见 hook message 输出，不再拼进 `additionalContext`。
- agent 只接收 planning 数据（计划、progress、findings）。
- 约 chars/tokens、profile 建议和静音命令不会进入 agent 上下文，也不参与压缩恢复。

### blocked context 语义更准确

- 当 attestation 阻断注入或上下文预算过小时，用户可见提示现在明确说明 planning context 未注入，而不是显示成功型的 token 估算 notice。
- agent 不会收到误导性的注入确认。

### 对现有用户的影响

这是一个行为变更版本：

- `findings.md` 默认开始注入。如果你之前没设 `PWF_INCLUDE_FINDINGS`，新版本开始会自动注入 findings tail。不喜欢可以设置 `PWF_INCLUDE_FINDINGS=0`。
- Codex 压缩恢复后注入的 planning context 会更完整。
- context notice 不再出现在给 agent 的注入数据里，不会浪费 token。

不改变 `.planning/` 数据格式，不需要迁移已有任务。

### 升级

从 `v0.3.2` 升级：使用 Release 包里的安全 installer，先 dry-run，再安装到目标项目；保留你的 `.planning/` 数据。推荐普通用户下载：

```text
HelsincyPlanWithFiles-v0.3.3-codex.zip
```

## English

### What does this release solve?

Before `v0.3.3`, injecting `findings.md` content required explicitly setting `PWF_INCLUDE_FINDINGS=1`. Most users were unaware of this opt-in switch, so agents often recovered from context compaction without important research findings and decision records.

At the same time, Codex compact recovery did not route through the normal context renderer, so injected planning context after compaction could be inconsistent. Context injection notices were mixed into the same `additionalContext` payload sent to the agent, wasting tokens and potentially confusing the agent's understanding of injected data.

This release makes five changes:

1. Splits installation into Codex CLI and Codex App flows using the safe installer.
2. Enables bounded `findings.md` tail injection by default, with an explicit opt-out.
3. Routes Codex compact recovery through the normal context renderer.
4. Separates user-visible context notices from agent-injected data.
5. Improves the semantics of blocked-context notices.

### Safer installation

- Regular users should run `install-pwf.ps1` / `install-pwf.sh` from the release package, dry-run first, and avoid manually overwriting the whole `.codex/`.
- Clean target projects receive project-level `.codex/config.toml` with the current official `[features] hooks = true` setting.
- New docs and examples no longer recommend `[features].codex_hooks`; it is a deprecated Codex alias.
- If the target project already has `.codex/config.toml`, the installer stops and reports a conflict. Review the existing file and add `hooks = true`, or start the CLI with `codex --enable hooks`.

### Findings injection is now default

`SessionStart` and `UserPromptSubmit` now inject a bounded `findings.md` tail by default.

- No need to manually set `PWF_INCLUDE_FINDINGS=1`.
- Set `PWF_INCLUDE_FINDINGS=0` to opt out explicitly.
- Set `PWF_FINDINGS_TAIL_LINES=N` to adjust the tail window.
- Findings still use delimiter framing and untrusted-content warnings.

### Compact recovery uses the normal path

The Codex `SessionStart` hook now covers the `compact` source.

- Post-compaction context injection uses the same context renderer as a regular session start, ensuring consistent injection format.
- `PreCompact` remains a reminder/attestation hook; `PostCompact` is intentionally not used for context injection.

### Context notices no longer pollute injected data

- Context injection notices are now emitted as user-visible hook messages, not prepended to `additionalContext`.
- The agent receives only planning data (plan, progress, findings).
- Approximate chars/tokens, profile hints, and mute commands stay out of the agent context and do not participate in compaction recovery.

### Blocked-context semantics are more accurate

- When attestation blocks injection or the context budget is too small, the user-visible notice now explicitly states that planning context was not injected, instead of showing a success-style token estimate.
- The agent does not receive a misleading injection confirmation.

### Impact on existing users

This is a behavioral change release:

- `findings.md` is now injected by default. If you previously did not set `PWF_INCLUDE_FINDINGS`, the new version will start auto-injecting the findings tail. Set `PWF_INCLUDE_FINDINGS=0` if you prefer to opt out.
- Codex compact recovery now injects more complete planning context.
- Context notices no longer appear in the agent's injected data, saving tokens.

The `.planning/` data format is unchanged; no migration of existing tasks is required.

### Upgrade

From `v0.3.2`: run the safe installer from the release package, dry-run first, then install into the target project. Keep your existing `.planning/` data. The recommended package for regular users is:

```text
HelsincyPlanWithFiles-v0.3.3-codex.zip
```
