# Changelog

## Unreleased

## 0.2.5 - 2026-06-10

- 中文：将 `/pwf-init` / `plan.py init` 调整为 session-first 默认行为；能识别当前会话时，新任务会自动绑定当前会话并写入 task lease，降低同项目多会话并发时写混 progress 的风险。
- 中文：新增显式兼容逃生口 `--no-bind-session`；`--no-workspace-active` 在默认绑定下可创建只属于当前会话的任务。
- 中文：更新 FAQ、README、普通用户指南和 release notes，说明默认会话绑定、workspace/strict 边界、workspace active 兼容层、上下文压缩后确认任务，以及推荐 `v0.2.5` 安装包。
- English: Made `/pwf-init` / `plan.py init` session-first by default; when the current session is identifiable, new tasks bind to that session and claim a task lease automatically.
- English: Added explicit compatibility escape hatch `--no-bind-session`; `--no-workspace-active` can create session-only tasks under the default binding behavior.
- English: Updated the FAQ, READMEs, plain-language user guide, and release notes with default session binding, workspace/strict boundaries, the workspace active compatibility fallback, task confirmation after context compaction, and the recommended `v0.2.5` package.

## 0.2.4 - 2026-06-10

- 中文：新增 `/pwf-tasks` 和 `/pwf-use`，可用短 ID 查看并绑定当前会话可见任务；默认不显示其他会话独占任务。
- 中文：`plan.py tasks --all` 提供只读诊断视图，跨会话接管或共享仍必须显式使用 `plan.py use <selector> --claim` 或 `--share`，继续遵守 workspace/strict 与 task lease 安全边界。
- 中文：CLI 会话识别新增 `CODEX_THREAD_ID` fallback，减少普通 Codex 会话手动设置 `PWF_SESSION_ID` 的需要。
- 中文：修复同一输出集合内短 ID 完全碰撞时无法复制即用的问题；碰撞的短 ID 会自动扩展到 8/10/12 位。
- 中文：新增面向普通用户的中文使用指南，并改写 README 开头，让用户先理解“任务记忆本”的用途，再进入高级配置。
- 中文：更新 FAQ、README 和 release notes，说明 `/pwf-tasks`、`/pwf-use`、上下文压缩后恢复任务时的选择方式，以及推荐 `v0.2.4` 安装包。
- English: Added `/pwf-tasks` and `/pwf-use` for short-ID based current-session task selection; other sessions' exclusive tasks stay hidden by default.
- English: Added `plan.py tasks --all` as a read-only diagnostic view. Cross-session takeover or sharing still requires explicit `plan.py use <selector> --claim` or `--share`, preserving workspace/strict and task lease safety boundaries.
- English: Added `CODEX_THREAD_ID` fallback for CLI session detection, reducing the need to set `PWF_SESSION_ID` manually in ordinary Codex sessions.
- English: Fixed fully colliding short IDs within the same output set by expanding colliding IDs to 8/10/12 characters so copied IDs remain usable.
- English: Added a Chinese plain-language user guide and rewrote the README opening so users understand the "task notebook" purpose before advanced configuration.
- English: Updated the FAQ, READMEs, and release notes for `/pwf-tasks`, `/pwf-use`, task recovery after context compaction, and the recommended `v0.2.4` package.

## 0.2.3 - 2026-06-09

- 中文：新增 session binding，支持同一项目多个 Codex 对话分别绑定不同 PWF 任务；`plan.py switch <plan-id> --session` 不修改 workspace active plan。
- 中文：新增 task ownership gate；未绑定 session 不会自动接管其他 session 拥有的任务，stale owner 也必须通过 `--force-claim`、`--share` 或 `--release-session` 显式处理。
- 中文：新增 `PWF_STRICT_REQUIRES_BINDING=1`，可让 strict mode 要求 session 已 attach 且已绑定有效任务。
- 中文：`progress.md` 自动记录新增 `Session` 和 `Plan-Source` 字段，并用短时 progress.md lock 保护 append 边界。
- 中文：更新 FAQ、README 和 release notes，说明上下文压缩恢复、workspace/strict 选择、session task binding、context profiles 和推荐 `v0.2.3` 安装包。
- English: Added session binding so multiple Codex conversations in one project can bind to different PWF tasks; `plan.py switch <plan-id> --session` leaves the workspace active plan unchanged.
- English: Added a task ownership gate so unbound sessions cannot automatically take over tasks owned by another session; stale owners require explicit `--force-claim`, `--share`, or `--release-session`.
- English: Added `PWF_STRICT_REQUIRES_BINDING=1` so strict mode can require both an attached session and a valid task binding.
- English: Added `Session` and `Plan-Source` metadata to automatic `progress.md` records and protected append boundaries with a short progress.md lock.
- English: Updated the FAQ, READMEs, and release notes for context compaction recovery, workspace/strict choices, session task binding, context profiles, and the recommended `v0.2.3` package.
- 中文：新增可配置 context injection profiles：`PWF_CONTEXT_PROFILE=lean/default/expanded/deep/custom`，默认行为保持兼容；`expanded` 和 `deep` 会注入计划头尾，并以完整 auto record 方式注入最近 progress。
- 中文：保留 findings 显式 opt-in；只有设置 `PWF_INCLUDE_FINDINGS=1` 后才会注入 findings，并继续使用 delimiter framing 和不可信内容提示。
- 中文：增强 context 配置安全性和可诊断性，包括严格 `PWF_*` 数值/布尔解析、环境变量诊断值清理、delimiter-looking 内容转义、总 context budget 兜底，以及 `/pwf-status`、`/pwf-doctor` 的 profile/limits 输出。
- English: Added configurable context injection profiles through `PWF_CONTEXT_PROFILE=lean/default/expanded/deep/custom`. Default behavior stays compatible; `expanded` and `deep` inject plan head/tail context and recent progress as complete auto records.
- English: Kept findings explicitly opt-in. Findings are injected only when `PWF_INCLUDE_FINDINGS=1` is set, with delimiter framing and untrusted-content warnings preserved.
- English: Hardened context configuration and diagnostics with strict `PWF_*` numeric/boolean parsing, sanitized environment diagnostics, delimiter-looking content escaping, total context budget fallback, and profile/limit output in `/pwf-status` and `/pwf-doctor`.

## 0.2.2 - 2026-06-06

- 中文：将 session isolation 明确为显式策略；默认 `workspace` 模式始终使用 `.planning/.active_plan` 恢复上下文，避免 Codex 上下文压缩或 resume 后因为历史 `.planning/sessions/` 目录而静默跳过 planning context。
- 中文：保留 opt-in 的 `strict` 模式，可通过 `PWF_SESSION_MODE=strict` 或 `.planning/session-policy.json` 开启；strict 模式缺少或未 attach `session_id` 时会输出诊断消息，而不是静默失败。
- 中文：增强 `/pwf-doctor` 的 session policy 诊断，并新增用户 FAQ 文档，解释安装、命令、上下文压缩、workspace/strict 选择、progress compaction、attestation 和中文模式等常见问题。
- English: Made session isolation an explicit policy. The default `workspace` mode now always uses `.planning/.active_plan` for context recovery, preventing stale `.planning/sessions/` state from silently suppressing planning context after Codex context compaction or resume.
- English: Preserved opt-in `strict` mode through `PWF_SESSION_MODE=strict` or `.planning/session-policy.json`; strict mode now emits diagnostics for missing or unattached `session_id` values instead of failing silently.
- English: Improved `/pwf-doctor` session policy diagnostics and added a user FAQ covering installation, commands, context compaction, workspace/strict mode selection, progress compaction, attestation, and Chinese mode.

## 0.2.1 - 2026-05-28

- 中文：修复英文默认模板初始化后 `plan.py status` 把 HTML 注释误识别为当前阶段的问题。
- 中文：修复 `plan.py compact` 摘要把 `- Command:` 里的反引号文本误统计为文件路径的问题。
- 中文：修正 `0.2.0` changelog 归属，确保已发布的压缩加固说明记录在对应版本条目中。
- English: Fixed default English template initialization so `plan.py status` reports `Phase 1` instead of an HTML comment.
- English: Fixed `plan.py compact` summaries so backtick text in `- Command:` is not counted as a file path.
- English: Corrected the `0.2.0` changelog section so released compaction hardening notes are recorded under the released version.

## 0.2.0 - 2026-05-25

- Added optional Simplified Chinese mode with `PWF_LANG=zh-CN` for hook prompts, CLI output, and generated planning templates.
- Added Chinese template files under `.codex/skills/planning-with-files/templates/zh-CN/`.
- Added Chinese mode guidance to `/pwf-*` skill wrappers and both README files.
- Kept default English behavior and stable ASCII delimiters, hashes, file paths, tool names, and auto-record fields for compatibility.
- Hardened `plan.py compact` to reject unsafe archive targets and preserve `progress.md` when archive writes fail.
- Improved progress compaction parsing so manual bullet notes are not accidentally archived with objective auto records.
- Isolated CLI and hook tests from inherited `PWF_*` environment variables.

## 0.1.5 - 2026-05-13

- Stop hook now stays silent when all phases are complete, avoiding a misleading warning for finished plans.

## 0.1.4 - 2026-05-13

- Hardened `post_tool_use.py` so direct calls only record supported mutating tools: `apply_patch`, `Edit`, and `Write`.
- Improved the Chinese and English README introductions with clearer product positioning, use cases, and before/after workflow comparisons.

## 0.1.3 - 2026-05-12

- Added `plan.py compact` and `/pwf-compact` to archive old objective auto records from `progress.md`.
- Added compacted progress summary injection so long-running tasks keep bounded context without losing audit history.
- Added `status` and `doctor` compact recommendations when `progress.md` grows past the threshold.

## 0.1.2 - 2026-05-12

- Expanded injected recent `progress.md` context from 20 lines to 80 lines so objective hook records are less likely to hide important recent file changes.
- Added tests for the 80-line progress context window.
- Added the progress compaction implementation plan for future `/pwf-compact` work.
- Improved Chinese and English installation docs to start from Release zip, git clone, or source zip workflows.

## 0.1.1 - 2026-05-12

- Deprecated `v0.1.0` and earlier releases. Users should upgrade to `v0.1.1` and use `/pwf-*` commands.
- Renamed the project-local command prefix from `/plw-*` to `/pwf-*`.
- Converted `/pwf-*` commands into project-local user-invocable skill wrappers under `.codex/skills/pwf-*`.
- Removed the global prompts installer path from the current design so slash commands remain project-local and easy to uninstall.
- Updated Chinese and English README guidance for the project-local `/pwf-*` command model.

## 0.1.0 - 2026-05-11

- Added a Windows-first Python hook runtime for Codex.
- Added objective auto records for `progress.md`, including tool, result, files, operation types, and active phase.
- Added delimiter framing for injected plan, progress, and opt-in findings data.
- Added opt-in SHA-256 plan attestation with tamper blocking.
- Added `plan.py doctor`, `status`, `init`, `switch`, `attest`, and `capture` commands.
- Added `/plw-*` agent slash command prompts for the planning CLI.
- Added bilingual README files for Chinese and English users.
