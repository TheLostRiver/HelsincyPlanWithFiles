# Changelog

## Unreleased

- 中文：统一 Stop/PostToolUse、兼容脚本、Skill 示例、初始化模板和 FAQ/README 的 `progress.md` 责任边界：`progress.md` 保持为 hooks 写入的客观 auto records，agent 更新 `task_plan.md` 阶段状态，并把解释性笔记、测试结论、错误分析和决策写入 `findings.md`。
- English: Aligned Stop/PostToolUse messages, compatibility scripts, skill hook examples, initialization templates, and FAQ/README wording around `progress.md` ownership: `progress.md` remains the objective hook-written auto-record log, while agents update `task_plan.md` phase/status and put interpretive notes, test conclusions, errors, and decisions in `findings.md`.
- English: Added a Codex `PreCompact` hook that reminds the agent to keep `task_plan.md` status current before context compaction while preserving `progress.md` as the hook-written objective log; the hook reuses the Python planning resolver, respects session ownership, reports attestation hashes, and does not modify files.

## 0.3.1 - 2026-06-16

- 中文：新增源码安全声明和正式免责声明，明确 Helsincy Plan With Files 不会删除或覆盖用户源码，只维护 `.planning/`、`.codex/` 相关任务计划、发现笔记、进度日志、会话绑定和元数据；README 现在直接链接免责声明和源码删除安全审计报告。
- English: Added a source safety statement and formal disclaimer clarifying that Helsincy Plan With Files does not delete or overwrite user source files and only maintains `.planning/` / `.codex` task plans, findings, progress logs, session bindings, and metadata; the README now links directly to the disclaimer and source deletion safety audit report.
- 中文：修复 `session-catchup.py` 的参数解析，`--planning-dir <dir> <project>` 现在能正确识别项目路径；规划文件探测也只接受真实文件，不再把同名目录当作有效的 planning 文件。
- English: Fixed `session-catchup.py` argument parsing so `--planning-dir <dir> <project>` keeps the project path intact; planning file detection now requires real files instead of accepting same-named directories.
- 中文：补全 task lease 状态输出的中文本地化，`PWF_LANG=zh-CN` 下状态行不再混入英文 `task lease` 标签，同时保留冲突提示的原有语义。
- English: Completed Chinese localization for task lease status output so `PWF_LANG=zh-CN` no longer leaks the English `task lease` label while preserving the existing conflict semantics.
- 中文：加固 PowerShell planning 目录解析器的 Python 命令查找，优先安全选择 `python3` / `python`，避免硬编码 `python` 调用在不同 Windows 环境中失效。
- English: Hardened the PowerShell planning-directory resolver by safely selecting `python3` / `python` instead of hardcoding a brittle `python` invocation.
- 中文：提高默认 task lease 文件锁等待时间，降低多会话或并发测试下的偶发锁超时；补充对应回归测试和项目一致性检查。
- English: Increased the default task lease file-lock wait to reduce occasional lock timeouts under multi-session or concurrent test runs; added regression tests and consistency checks.

## 0.3.0 - 2026-06-15

- 中文：移除多会话共享 PWF 任务的路径（`switch --share`、`use --share`）；多会话记录塞进同一上下文会打乱各自任务记忆，且十几个会话并发共享会导致 progress 写入竞态。旧的 `.task-lease.json` 里若仍带 `shared=true` 仍可被读取，不会触发 ownership denial；详见 `docs/REMOVED_CROSS_SESSION_SHARE.md`。
- English: Removed cross-session task sharing paths (`switch --share`, `use --share`); merging multiple sessions' records into one shared context scrambles each agent's task memory and a dozen concurrent sessions sharing one task cause progress write contention. Historical `.task-lease.json` files carrying `shared=true` remain readable and do not trigger ownership denial; see `docs/REMOVED_CROSS_SESSION_SHARE.md`.
- 中文：新增 `/pwf-pause`、`/pwf-resume`（等价 `plan.py context pause|resume`），暂停当前会话的 SessionStart/UserPromptSubmit/PreToolUse 上下文注入；PostToolUse 的 progress 记录仍继续工作（客观事实不停）。未暂停时使用 resume 会给提示，已暂停时再次 pause 也给提示。暂停状态存 `.planning/session-context/<key>.json` 的 `paused` 字段，只影响当前会话。
- English: Added `/pwf-pause` and `/pwf-resume` (equivalent to `plan.py context pause|resume`) to pause SessionStart/UserPromptSubmit/PreToolUse context injection for the current session; PostToolUse progress recording keeps working (objective facts are never paused). Running resume while not paused shows a hint, as does pausing while already paused. The paused state is stored in `.planning/session-context/<key>.json` under a `paused` field and affects only the current session.
- 中文：`/pwf-context-notice-auto` 现在在所有档位（含 default/lean）都显示上下文注入提示，文案改为单行精简格式，并附档位升降建议（升级到 expanded/deep 或降档到 lean）和静音命令；不再仅在 expanded/deep/SessionStart 才显示。
- English: `/pwf-context-notice-auto` now shows the context injection notice on all profiles (including default/lean); the message is a single concise line with a profile upgrade/downgrade hint (to expanded/deep or down to lean) and the mute command. Previously the auto notice only appeared on expanded/deep or SessionStart.
- 中文：`/pwf-compact` 的保留记录数默认按当前 context profile 自动决定（lean=10 / default=30 / expanded=60 / deep=100），让归档后活跃 progress 与注入预算匹配；优先级为 `PWF_COMPACT_KEEP_RECORDS` 环境变量 > 显式 `--keep-records` flag > profile 默认。compact 输出新增一行说明 keep 来源和当前 profile。
- English: `/pwf-compact` keep-records default is now derived from the current context profile (lean=10 / default=30 / expanded=60 / deep=100) so the active segment after rollover matches the profile's injection budget; priority is `PWF_COMPACT_KEEP_RECORDS` env > explicit `--keep-records` flag > profile default. compact output adds a line reporting the keep source and current profile.

- 中文：将 `plan.py compact` 改为 append-only rollover，旧 auto records 写入新建的 `progress-archive/<session-key>/archive-*.md`，后续记录写入新建的 `progress-active/<session-key>/active-*.md`，并拒绝自定义 `--archive` 路径，避免删除或覆盖任何已有 progress/archive 文件。
- English: Changed `plan.py compact` to append-only rollover using generated `progress-archive/<session-key>/archive-*.md` and `progress-active/<session-key>/active-*.md` files, while rejecting custom `--archive` paths so existing progress/archive files are not deleted or overwritten.
- 中文：补充 `/pwf-doctor` 的 append-only progress storage 审计文档，说明 `progress-index.ndjson`、`progress-active/`、`progress-archive/`、hash mismatch、orphan generated segment、`No automatic repair was attempted.`、`--json` 和 `--strict` 行为。
- English: Documented the `/pwf-doctor` append-only progress storage audit, including `progress-index.ndjson`, `progress-active/`, `progress-archive/`, hash mismatches, orphan generated segments, `No automatic repair was attempted.`, `--json`, and `--strict`.

## 0.2.7 - 2026-06-11

- 中文：强化多会话 task ownership 安全边界；`PLAN_ID` 现在只是 routing override，不再作为 permission override 绕过其他 session 的独占任务。
- 中文：task lease 的 `stale` 诊断优先使用 owner session heartbeat；`.task-lease.json` 的 `updated_at` 只作为兼容回退，stale owner 仍必须显式 claim/share/release。
- 中文：Python hooks 的会话识别与 CLI 对齐，按 payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID` 回退，避免普通 Codex 会话丢失 session binding。
- 中文：更新 FAQ、README、普通用户指南和 release notes，说明 `PLAN_ID` 权限边界、owner heartbeat stale 诊断、workspace/strict 安全边界不变，以及推荐 `v0.2.7` 安装包。
- English: Hardened multi-session task ownership; `PLAN_ID` is now a routing override, not a permission override for another session's exclusive task.
- English: Task lease `stale` diagnostics now prefer the owner session heartbeat, with `.task-lease.json` `updated_at` only as a compatibility fallback; stale owners still require explicit claim/share/release.
- English: Aligned Python hook session identity with the CLI using payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID`, preserving session binding in ordinary Codex sessions.
- English: Updated the FAQ, READMEs, plain-language user guide, and release notes with the `PLAN_ID` permission boundary, owner heartbeat stale diagnostics, unchanged workspace/strict safety boundaries, and the recommended `v0.2.7` package.

## 0.2.6 - 2026-06-10

- 中文：新增会话级 context profile 快捷命令，可用 `/pwf-context-expanded`、`/pwf-context-deep`、`/pwf-context-default`、`/pwf-context-lean` 和 `/pwf-context-status` 管理当前会话的上下文注入强度。
- 中文：新增 context injection notice 开关：`/pwf-context-notice-auto`、`/pwf-context-notice-on`、`/pwf-context-notice-off`，可提示已自动注入任务上下文及大致占用；提示数值为估算值。
- 中文：忽略本地 `dist/` 发布输出目录，避免生成 release zip 后在工作区显示为未跟踪文件。
- 中文：更新 FAQ、README、普通用户指南和 release notes，说明 context profile 快捷命令、上下文压缩后的任务上下文注入提示、workspace/strict 边界不变，以及推荐 `v0.2.6` 安装包。
- English: Added session-scoped context profile shortcuts for `/pwf-context-expanded`, `/pwf-context-deep`, `/pwf-context-default`, `/pwf-context-lean`, and `/pwf-context-status`.
- English: Added context injection notice controls through `/pwf-context-notice-auto`, `/pwf-context-notice-on`, and `/pwf-context-notice-off`, including approximate prompt-size reporting.
- English: Ignored the local `dist/` release output directory so generated release zip files do not appear as untracked workspace files.
- English: Updated the FAQ, READMEs, plain-language user guide, and release notes with context profile shortcuts, task context injection notices after context compaction, unchanged workspace/strict boundaries, and the recommended `v0.2.6` package.

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
