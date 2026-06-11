# FAQ

[简体中文](#简体中文) | [English](#english)

## 简体中文

如果你是第一次使用，建议先看 [普通用户使用指南](USER_GUIDE.zh-CN.md)。那篇文档会用更少术语解释“它是干什么的、怎么开始、多个会话怎么不写混”。

### 1. Helsincy Plan With Files 适合什么场景？

它适合长任务、多轮任务、需要恢复上下文的任务，以及需要记录“做过什么、改过哪些文件、为什么这么做”的 Codex 工作流。典型场景包括复杂 bug 修复、分阶段功能开发、跨会话继续工作、上下文压缩后恢复任务，以及需要保留研究发现和测试结果的任务。

如果只是一次很短的问答，可能不需要它。如果任务会跨多轮、跨文件、跨时间，建议使用。

### 2. 它和普通 README/notes 有什么不同？

普通笔记依赖 agent 主动记。这个工具把任务拆成三类项目本地文件：

```text
task_plan.md   # 目标、阶段、当前状态
findings.md    # 研究发现、决策、外部资料摘要
progress.md    # 执行动作、测试结果、文件变更记录
```

hook 会在会话开始、用户提交提示、工具调用前后和停止前读取或更新这些文件，让 Codex 在上下文变短或会话恢复后仍能找到任务状态。

### 3. 应该下载哪个 Release 包？

普通用户优先下载：

```text
HelsincyPlanWithFiles-v0.2.7-codex.zip
```

这个包只包含安装到目标项目所需的 `.codex/`、hooks、`/pwf-*` commands 和基础文档。

`full.zip` 或 GitHub source zip 更适合开发者查看源码、运行测试或参与贡献。普通安装不需要复制整个仓库。

### 4. 怎么安装到我的项目？

把 Release 包里的 `.codex/` 复制到目标项目根目录，然后重启 Codex，并在首次提示信任 hook 时批准。

目标项目大致如下：

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

如果你的项目已经有 `.codex/`，不要直接覆盖。先备份，或手动合并 `hooks.json` 和 skills。

### 5. `/pwf-*` 命令看不到怎么办？

先确认 `.codex/skills/pwf-*` 已经复制到目标项目，然后重启 Codex。命令仍不可见时，在项目根目录用终端备用命令检查：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

如果 doctor 通过，但 slash command 仍不可见，通常是 Codex 尚未重新加载项目本地 skills。重启当前 Codex 会话或重新打开项目通常可以解决。

### 6. 安装后第一条命令应该跑什么？

优先运行：

```text
/pwf-doctor
```

它会检查 hooks、hook 文件、Python runtime、active plan、attestation、语言设置和 session mode。终端备用命令是：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

### 7. 怎么开始一个任务？

创建任务：

```text
/pwf-init My Task
```

如果当前 Codex 会话可以识别，`/pwf-init` 默认会绑定当前会话，并给新任务写入 task lease。这样同一项目多个会话分别创建任务时，默认不会把进度写到同一本 `progress.md`。

如果你明确想使用旧的 workspace-only 行为，可以运行：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-bind-session
```

如果你想只绑定当前会话、不更新 `.planning/.active_plan`，可以运行：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-workspace-active
```

查看状态：

```text
/pwf-status
```

切换任务：

```text
/pwf-switch
/pwf-switch 2026-06-06-my-task
```

创建任务后，当前任务 ID 通常也会写入 `.planning/.active_plan`。workspace active 是兼容层，用于单会话和旧工作流；多会话下当前 session binding 优先。

### 8. `.planning/` 要提交到 git 吗？

通常不要提交。`.planning/` 是运行时上下文，里面可能包含当前任务进度、临时判断、研究笔记和项目细节。它默认应该留在本地。

建议提交工具本身：

```text
.codex/
docs/
README.md
README.en.md
CHANGELOG.md
VERSION
tests/
```

建议忽略：

```text
.planning/
.plan-attestation
```

### 9. 上下文压缩后为什么有时 hook 有提示、有时没有？

在 `v0.2.2` 之前，工具曾经根据 `.planning/sessions/` 推断是否启用 session isolation。某些情况下，这会让历史 session 状态影响默认 hook 行为。Codex 上下文压缩、resume 或下一次用户提示后，如果 hook payload 没有提供可匹配的 `session_id`，planning context 可能被静默跳过。

`v0.2.2` 改为显式 session policy：

- 默认 `workspace` 模式：使用 `.planning/.active_plan` 恢复上下文。
- `.planning/sessions/` 目录存在也不会让默认 hook 静默。
- `strict` 模式必须显式开启。
- strict 模式无法匹配 `session_id` 时会输出诊断消息。

所以普通用户升级后不需要额外配置，默认行为更稳定。

### 10. 怎么判断是工具问题还是 Codex 本身行为？

先运行：

```text
/pwf-doctor
```

或：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

重点看这些信息：

- `hooks.json: ok`：Codex hook 配置文件能被读取。
- `hook files: ok`：hook 入口文件存在。
- `python runtime: ok`：Python 能执行 hook 脚本。
- `active plan: ok ...`：当前 active plan 能解析。
- `session mode: workspace`：默认推荐模式。

如果 doctor 正常，但 Codex UI 某次没有显示明显提示，可能是 Codex 自身对 hook 输出展示、上下文压缩或 resume 流程的表现差异。此时看 `.planning/<plan-id>/progress.md` 是否仍有记录，以及下一次用户提示是否注入了 active plan。

如果 doctor 报 hook 文件缺失、Python 不可用、active plan 缺失或 strict session mismatch，就优先按工具配置问题处理。

### 11. `workspace` 和 `strict` 应该怎么选？

大多数项目使用默认 `workspace`。它把 `.planning/.active_plan` 当作唯一真相，适合一个项目当前只有一个主要 Codex 工作流，或者你希望上下文压缩后尽量稳定恢复任务。

只有在同一个项目里同时开多个 Codex 会话，并且这些会话必须互不共享 active plan 时，才使用 `strict`：

```powershell
$env:PWF_SESSION_MODE = "strict"
```

等价策略名是 `PWF_SESSION_MODE=strict`。

或创建 `.planning/session-policy.json`：

```json
{"mode":"strict"}
```

strict 模式更隔离，但也更依赖 Codex hook payload 中的 `session_id`。不确定时，用默认 `workspace`。

### 11a. 同一项目里多个对话会不会混用 `progress.md`？

默认 `workspace` 模式仍保留 `.planning/.active_plan`，但 workspace active 是兼容层。现在 `/pwf-init` / `plan.py init` 在能识别当前会话时默认会绑定当前会话，所以同一项目多个 Codex 对话各自新建任务时，会自然拥有各自的 PWF 任务。

需要明确恢复旧 workspace-only 行为时，使用 `--no-bind-session`：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-bind-session
```

需要只绑定当前会话、不更新 workspace active 时，使用 `--no-workspace-active`：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-workspace-active
```

绑定已有任务时仍使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

显式创建并绑定的旧写法仍然可用，适合脚本或旧文档迁移：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

绑定后，该对话的上下文注入和 `progress.md` 自动记录都会使用 session-bound plan。自动记录包含 `Session` 和 `Plan-Source` 字段，便于审计。如果需要 strict mode 强制要求 binding，请设置：

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```

`PLAN_ID` 可以显式选择要注入或记录的任务，但它只是 routing override，不是 permission override。hook 会话识别顺序是 payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID`；如果目标任务由其他 session 独占，仍必须满足 ownership、shared/released，或显式 claim/share/release。

如果 workspace active task 已经由另一个 session 拥有，新的未绑定对话不会自动接管它；owner stale 也仍然需要显式选择。接管或共享仍必须显式表达意图：接管用 `--force-claim` 或 `plan.py use <id> --claim`，有意共享用 `--share`，释放当前 session 的 ownership 用 `--release-session`：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --force-claim
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --share
python .codex\skills\planning-with-files\scripts\plan.py switch --release-session
```

`stale` 优先由 owner session heartbeat 判断；只有找不到对应 session lease 时才回退到 `.task-lease.json` 的 `updated_at`。stale 只是诊断状态，不是自动接管许可。

### 11b. 同一个项目里开了多个会话，我忘记当前会话能用哪个任务怎么办？

先运行 `/pwf-tasks`。它默认只列出当前会话可见任务，并显示短 ID、绑定状态和 lease 状态。复制短 ID 后运行 `/pwf-use <short-id>`。终端备用命令是：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py tasks
python .codex\skills\planning-with-files\scripts\plan.py use <short-id>
```

如果你需要排查整个项目里的任务，运行 `plan.py tasks --all`。这个列表是诊断视图；默认 `/pwf-use` 不会因为你看到了其他会话任务就自动切过去。跨会话接管或共享必须显式使用 `plan.py use <id> --claim` 或 `plan.py use <id> --share`。

### 12. `progress.md` 越来越长怎么办？

运行：

```text
/pwf-compact
```

终端备用命令：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
python .codex\skills\planning-with-files\scripts\plan.py compact --keep-records 50
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
```

它会把旧 auto records 归档到 `progress.archive.md`，并在 `progress.md` 保留 compact summary 和最近记录。

### 13. `findings.md` 什么时候用？

hook 自动记录的是文件写入事实。网页、浏览器、图片、PDF、用户提供的长资料，以及 agent 做出的重要判断，都应该由 agent 总结到 `findings.md`。

简单说：

- `progress.md` 记录“做了什么”。
- `findings.md` 记录“学到了什么、为什么这样决定”。
- `task_plan.md` 记录“目标是什么、现在到哪一步”。

### 14. `/pwf-attest` 是做什么的？

`/pwf-attest` 用于锁定已确认的 `task_plan.md`。它会保存计划文件的 SHA-256 hash。之后 hook 注入计划前会重新计算 hash；如果计划被改过且 hash 不匹配，hook 会阻断计划注入并提示 `[PLAN TAMPERED - injection blocked]`。

适合在高风险任务、多人协作或需要确认计划未被意外修改时使用。普通任务可以不用。

### 15. 怎么启用中文模式？

设置：

```powershell
$env:PWF_LANG = "zh-CN"
```

然后运行：

```text
/pwf-doctor
/pwf-init 中文任务
```

终端备用命令也支持 `PWF_LANG=zh-CN`。如果要强制英文，设置：

```powershell
$env:PWF_LANG = "en"
```

其他语言值会回退英文，`/pwf-doctor` 会报告 unsupported language warning。

### 16. hook 会不会执行 planning 文件里的指令？

不应该。hook 注入 planning 文件时会使用 delimiter framing：

```text
---BEGIN PLAN DATA---
...
---END PLAN DATA---
```

agent 应把这些内容当作结构化数据，而不是可执行指令。这个边界能降低 planning 文件中出现指令式文本时的风险。

### 17. 升级版本时需要迁移 `.planning/` 吗？

通常不需要。升级工具时替换 `.codex/` 即可，`.planning/` 是目标项目的运行时状态，应该保留在目标项目里。

升级后建议运行：

```text
/pwf-doctor
```

确认 hook、active plan 和 session mode 都正常。

### 18. 上下文压缩后还是丢上下文怎么办？

先确认当前任务存在 active plan，并运行：

```text
/pwf-doctor
/pwf-status
```

如果任务很大，默认 hook 窗口可能仍然只注入计划开头和最近 progress 行。普通用户优先用当前会话命令切换，不需要手动敲环境变量：

```text
/pwf-context-expanded
```

`expanded` 适合大多数大型功能开发，会注入 `task_plan.md` 的头尾，并按完整 auto record 注入最近 progress。恢复很长、压缩很重的任务时再使用：

```text
/pwf-context-deep
```

查看当前会话正在使用哪种上下文模式：

```text
/pwf-context-status
```

这些命令只影响当前会话，不会修改其他会话的上下文设置，也不会切换其他会话的 PWF 任务。需要恢复默认或省上下文模式时，可以使用 `/pwf-context-default` 或 `/pwf-context-lean`。

如果你想看到工具是否自动注入了任务上下文，可以开启提示：

```text
/pwf-context-notice-auto
```

提示里显示的是约占用量，不是精确 token 计数。

环境变量 `PWF_CONTEXT_PROFILE` 仍然保留给高级用法，例如脚本、CI 或临时覆盖。它的优先级高于当前会话设置；如果你设置了 `PWF_CONTEXT_PROFILE=deep`，即使当前会话文件里保存的是 `expanded`，实际也会使用 `deep`。

`findings.md` 仍然是显式 opt-in。如果恢复需要研究笔记或外部资料摘要，再设置：

```powershell
$env:PWF_INCLUDE_FINDINGS = "1"
```

### 19. 为什么 hook context 现在变大了？

只有设置 `PWF_CONTEXT_PROFILE=expanded`、`deep` 或自定义 limit 后，hook payload 才会明显变大。默认 `default` profile 保持兼容；`lean` 可以减少注入窗口。

变大的主要原因是 expanded/deep 会注入计划尾部，并把 progress 从原来的行尾窗口升级为 record-aware 最近记录窗口。这样更利于 resume 和上下文压缩后恢复，但会消耗更多上下文。运行 `/pwf-status` 或 `/pwf-doctor` 可以查看当前 profile、progress mode、findings 是否开启和 max chars。

## English

If this is your first time using the tool and you read Chinese, start with the [plain-language user guide](USER_GUIDE.zh-CN.md). It explains what the tool is for, how to start, and how to avoid mixed progress across multiple sessions with fewer technical terms.

### 1. When should I use Helsincy Plan With Files?

Use it for long-running, multi-step, or cross-session Codex work where you need recoverable task state. Good examples include complex bug fixes, phased feature work, continuing after context compaction, and tasks that need durable research notes or test evidence.

For a short one-off question, you may not need it. If the task spans several turns, several files, or several sessions, it helps.

### 2. How is this different from normal notes?

Normal notes depend on the agent remembering to write them. This tool organizes task memory into project-local files:

```text
task_plan.md   # goal, phases, current status
findings.md    # research findings, decisions, external summaries
progress.md    # actions, test results, file change records
```

Hooks read or update those files at session start, user prompt submit, tool use, and stop time, so Codex can recover task state after the chat context gets shorter.

### 3. Which release package should I download?

Most users should download:

```text
HelsincyPlanWithFiles-v0.2.7-codex.zip
```

It contains the `.codex/` directory, hooks, `/pwf-*` commands, and basic docs needed for project-local installation.

Use `full.zip` or the GitHub source zip only if you want source code, tests, and development files.

### 4. How do I install it into my project?

Copy `.codex/` from the release package into your target project root, restart Codex, and approve the hook trust prompt.

Your target project should look like this:

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

If the project already has `.codex/`, do not overwrite it blindly. Back it up or merge `hooks.json` and skills manually.

### 5. What if `/pwf-*` commands do not appear?

First confirm `.codex/skills/pwf-*` exists in the target project, then restart Codex. If commands still do not appear, run the terminal fallback from the project root:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

If doctor passes, Codex probably has not reloaded project-local skills yet. Restarting the session or reopening the project usually fixes it.

### 6. What should I run first after installation?

Run:

```text
/pwf-doctor
```

It checks hooks, hook files, Python runtime, active plan, attestation, language settings, and session mode. Terminal fallback:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

### 7. How do I start a task?

Create a task:

```text
/pwf-init My Task
```

When the current Codex conversation can be identified, `/pwf-init` is session-first by default. It binds the new task to the current session and claims a task lease, so concurrent conversations in the same project get separate PWF tasks by default.

To intentionally use the old workspace-only behavior, run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-bind-session
```

To bind only the current session without updating `.planning/.active_plan`, run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task" --no-workspace-active
```

Check status:

```text
/pwf-status
```

Switch tasks:

```text
/pwf-switch
/pwf-switch 2026-06-06-my-task
```

The active task ID is usually also stored in `.planning/.active_plan`. workspace active remains a compatibility fallback for single-session and older workflows; in multi-session work, the current session binding takes precedence.

### 8. Should I commit `.planning/` to git?

Usually no. `.planning/` is runtime context and may contain current task progress, temporary judgments, research notes, and project details.

Recommended to commit:

```text
.codex/
docs/
README.md
README.en.md
CHANGELOG.md
VERSION
tests/
```

Recommended to ignore:

```text
.planning/
.plan-attestation
```

### 9. Why did hooks sometimes appear after context compaction and sometimes stay silent?

Before `v0.2.2`, the tool inferred session isolation from `.planning/sessions/`. In some cases, stale session state could affect the default hook path. After Codex context compaction, resume, or the next user prompt, if the hook payload did not include a matching `session_id`, planning context could be skipped silently.

`v0.2.2` makes session policy explicit:

- Default `workspace` mode uses `.planning/.active_plan` for context recovery.
- Existing `.planning/sessions/` no longer makes default hooks silent.
- `strict` mode must be enabled explicitly.
- Strict mode emits diagnostics when `session_id` is missing or unattached.

Most users do not need extra configuration after upgrading.

### 10. How do I tell whether this is a tool issue or Codex behavior?

Start with:

```text
/pwf-doctor
```

or:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Check these lines:

- `hooks.json: ok`: Codex can read the hook config.
- `hook files: ok`: hook entrypoints exist.
- `python runtime: ok`: Python can run the hook scripts.
- `active plan: ok ...`: the active plan resolves.
- `session mode: workspace`: the recommended default.

If doctor is clean but a specific Codex UI turn does not show visible hook text, it may be Codex display, context compaction, or resume behavior. Check whether `.planning/<plan-id>/progress.md` still records file changes and whether the next user prompt injects the active plan.

If doctor reports missing hook files, Python failure, missing active plan, or strict session mismatch, treat it as a tool configuration issue first.

### 11. Should I use `workspace` or `strict` mode?

Most projects should use the default `workspace` mode. It treats `.planning/.active_plan` as the source of truth and is best when one project has one main Codex workflow, or when reliable recovery after context compaction matters most.

Use `strict` only when several Codex sessions in the same project must not share the active plan:

```powershell
$env:PWF_SESSION_MODE = "strict"
```

The equivalent policy name is `PWF_SESSION_MODE=strict`.

or create `.planning/session-policy.json`:

```json
{"mode":"strict"}
```

Strict mode provides more isolation, but depends on `session_id` in the Codex hook payload. When unsure, use `workspace`.

### 11a. Will multiple conversations in one project mix `progress.md`?

Default `workspace` mode still preserves `.planning/.active_plan`, but workspace active remains a compatibility fallback. `/pwf-init` / `plan.py init` is session-first by default when the current session can be identified, so multiple Codex conversations that create their own tasks get separate PWF tasks automatically.

To intentionally use the old workspace-only behavior, use `--no-bind-session`:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-bind-session
```

To bind the task to the current session without updating workspace active, use `--no-workspace-active`:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-workspace-active
```

To bind an existing task, use:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

The explicit create-and-bind form is still supported for scripts or older docs:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

`--legacy` is only for root-level single-task compatibility mode. `plan.py init "Task Name" --legacy --bind-session` is rejected; use a named `.planning/<plan-id>` task for multi-session isolation.

After binding, context injection and automatic `progress.md` records use the session-bound plan. Auto records include `Session` and `Plan-Source` fields for auditing. To make strict mode require a binding, set:

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```

`PLAN_ID` can explicitly choose the task to inject or record, but it is a routing override, not a permission override. Hook session identity is resolved as payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID`; if the target task is exclusive to another session, ownership, shared/released state, or an explicit claim/share/release is still required.

If the workspace active task is already owned by another session, an unbound new conversation will not automatically take it over; a stale owner still requires an explicit choice. claim or share still requires explicit intent: use `--force-claim` or `plan.py use <id> --claim` to take ownership, `--share` for intentional sharing, and `--release-session` to release the current session:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --force-claim
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --share
python .codex\skills\planning-with-files\scripts\plan.py switch --release-session
```

`stale` is computed from the owner session heartbeat when that session lease exists; `.task-lease.json` `updated_at` is only a compatibility fallback. Stale is a diagnostic state, not permission to take ownership automatically.

### 11b. What if I forget which task this conversation can use?

Run `/pwf-tasks` first. It lists only tasks visible to the current session by default, with short IDs, binding state, and lease state. Copy a short ID and run `/pwf-use <short-id>`. Terminal fallback:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py tasks
python .codex\skills\planning-with-files\scripts\plan.py use <short-id>
```

If you need to inspect every task in the project, run `plan.py tasks --all`. That is a read-only diagnostic view; `/pwf-use` will not automatically switch to another session's task just because it appeared in `--all`. Crossing session ownership still requires explicit `plan.py use <id> --claim` or `plan.py use <id> --share`.

### 12. What if `progress.md` gets too large?

Run:

```text
/pwf-compact
```

Terminal fallback:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
python .codex\skills\planning-with-files\scripts\plan.py compact --keep-records 50
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
```

It archives old auto records into `progress.archive.md` while keeping a compact summary and recent records in `progress.md`.

### 13. When should I use `findings.md`?

Hooks automatically record file write facts. Web pages, browser context, images, PDFs, user-provided long context, and important judgments should be summarized by the agent into `findings.md`.

In short:

- `progress.md` records what happened.
- `findings.md` records what was learned and why decisions were made.
- `task_plan.md` records the goal and current phase.

### 14. What does `/pwf-attest` do?

`/pwf-attest` locks an approved `task_plan.md` by storing its SHA-256 hash. Before later plan injection, the hook recomputes the hash. If the file changed and the hash no longer matches, the hook blocks plan injection and emits `[PLAN TAMPERED - injection blocked]`.

Use it for higher-risk tasks, collaboration, or cases where the plan must not change unnoticed. For ordinary tasks, it is optional.

### 15. How do I enable Chinese mode?

Set:

```powershell
$env:PWF_LANG = "zh-CN"
```

Then run:

```text
/pwf-doctor
/pwf-init Chinese Task
```

Terminal commands also support `PWF_LANG=zh-CN`. To force English:

```powershell
$env:PWF_LANG = "en"
```

Other language values fall back to English, and `/pwf-doctor` reports an unsupported language warning.

### 16. Will hooks execute instructions written inside planning files?

They should not. Hooks inject planning files with delimiter framing:

```text
---BEGIN PLAN DATA---
...
---END PLAN DATA---
```

The agent should treat content inside those blocks as structured data, not executable instructions. This boundary reduces risk when planning files contain instruction-like text.

### 17. Do I need to migrate `.planning/` when upgrading?

Usually no. Upgrade the tool by replacing `.codex/`; keep `.planning/` in the target project as runtime state.

After upgrading, run:

```text
/pwf-doctor
```

Confirm hooks, active plan, and session mode are healthy.

### 18. What if I still lose context after compaction?

First confirm there is an active plan:

```text
/pwf-doctor
/pwf-status
```

For large tasks, the default hook window may still inject only the plan head and recent progress lines. Most users should switch the current session with slash commands instead of typing environment variables:

```text
/pwf-context-expanded
```

`expanded` is the usual choice for large feature work. It injects both the head and tail of `task_plan.md`, and it includes recent progress as complete auto records. Use this only for deliberate recovery after heavy compaction or resume:

```text
/pwf-context-deep
```

Check the current session setting with:

```text
/pwf-context-status
```

These commands affect only the current session. They do not change other sessions' context settings, and they do not switch another session's PWF task. Use `/pwf-context-default` or `/pwf-context-lean` to return to the default or lean mode.

To see when the tool injected task context, use:

```text
/pwf-context-notice-auto
```

The notice reports an approximate size, not an exact token count.

The `PWF_CONTEXT_PROFILE` environment variable still exists for advanced use cases such as scripts, CI, or temporary overrides. It has higher priority than the current-session setting; if `PWF_CONTEXT_PROFILE=deep` is set, it overrides a saved session profile such as `expanded`.

`findings.md` remains explicit opt-in. If recovery needs research notes or external-context summaries, also set:

```powershell
$env:PWF_INCLUDE_FINDINGS = "1"
```

### 19. Why is hook context larger now?

Hook payloads grow noticeably only when `PWF_CONTEXT_PROFILE=expanded`, `deep`, or custom limit variables are enabled. The `default` profile stays compatible; `lean` reduces the injected windows.

The larger payload comes from injecting the plan tail and switching progress from a raw line tail to a record-aware recent-record window. This helps after resume and context compaction, but uses more context. Run `/pwf-status` or `/pwf-doctor` to see the active profile, progress mode, findings state, and max chars.
