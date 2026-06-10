# Helsincy Plan With Files

[简体中文](README.md) | [English](README.en.md)

Helsincy Plan With Files 是给 Codex 准备的“任务记忆本”。

当你让 Codex 做一个很长的任务时，它可能会遇到几种麻烦：聊着聊着上下文变短、换了一个新会话后忘了做到哪一步、多个会话同时操作同一个项目时把进度写混。这个工具会在你的项目里保存任务计划、重要发现和执行进度，让 Codex 可以像翻自己的工作笔记一样找回状态。

如果你只是问一个很短的问题，通常不需要它。如果你要让 Codex 分几步完成一个任务、改多个文件、跨几次会话继续做，或者同一个项目里开了多个 Codex 会话，它就很有用。

第一次使用建议先看这篇通俗说明：[普通用户使用指南](docs/USER_GUIDE.zh-CN.md)。

## 这是什么？

这是一个安装在项目里的 Codex 辅助工具。安装后，你的项目会多出一组 `/pwf-*` 命令，以及一个 `.planning/` 文件夹。Codex 会把当前任务的“要做什么、发现了什么、已经做了什么”写进去：

```text
.planning/<plan-id>/task_plan.md
.planning/<plan-id>/findings.md
.planning/<plan-id>/progress.md
```

- `task_plan.md`：任务清单，记录目标、阶段和完成情况。
- `findings.md`：发现笔记，记录调查结果、重要判断和外部资料摘要。
- `progress.md`：进度日志，记录 Codex 做过什么、改过哪些文件、跑过哪些测试。

你不需要一开始就理解所有内部机制。日常使用时，记住三个命令就够了：`/pwf-doctor` 检查安装，`/pwf-init` 开始任务，`/pwf-status` 查看当前状态。

## 它解决什么问题？

Codex 很擅长执行复杂任务，但长任务里常见几个痛点：

- 上下文压缩后，早期决策、已完成阶段和剩余工作容易丢失。
- 会话中断或恢复后，agent 需要重新阅读大量内容才能找回状态。
- 文件已经被修改，但没有稳定的客观记录说明改过哪些文件。
- 研究资料、测试结果、临时判断散落在聊天记录里，难以复查。

Helsincy Plan With Files 把这些易丢失的信息落到项目文件里，让任务状态从“聊天里的记忆”变成“项目里的工作记录”。

## 为什么要用？

这个工具适合需要多轮推进、跨会话恢复或高可追踪性的 Codex 工作流，例如：

- 修复复杂 bug，需要保留调查过程和决策依据。
- 分阶段实现功能，需要明确当前阶段、完成项和下一步。
- 修改多个文件，需要自动记录真实发生的文件变更。
- 需要在上下文压缩、会话恢复或切换任务后继续工作。

它的核心价值不是多生成几个 `.md` 文件，而是让 Codex 有一套可恢复、可追踪、可诊断的任务记忆。

## 不使用 vs 使用后

| 场景 | 不使用此工具 | 使用 Helsincy Plan With Files |
|------|--------------|-------------------------------|
| 长任务推进 | 依赖当前聊天上下文，压缩后容易漏掉目标和阶段 | `task_plan.md` 保存目标、阶段和当前状态 |
| 研究资料 | 资料和判断散落在对话里，恢复时要重新翻找 | `findings.md` 集中保存发现、决策和外部资料摘要 |
| 文件变更 | 需要 agent 手动总结，容易遗漏或主观化 | hook 自动把写文件工具的客观记录追加到 `progress.md` |
| 会话恢复 | 新会话需要重新建立任务背景 | hook 在会话开始和用户提示时注入 active plan |
| 安装排障 | 需要手动检查 hook、脚本和状态文件 | `/pwf-doctor` 一次诊断安装、active plan 和 attestation |
| 安全边界 | planning 内容可能和普通上下文混在一起 | delimiter framing 把 planning 内容明确标记为数据 |

## 核心工作流

1. 把 `.codex/` 安装到目标项目根目录。
2. 运行 `/pwf-doctor` 检查 hooks 和命令是否可用。
3. 用 `/pwf-init <task name>` 创建一个 planning 任务。
4. 正常让 Codex 研究、修改、测试和总结。
5. hook 自动维护 active `progress.md`，agent 把重要外部上下文总结到 `findings.md`。
6. 需要切换任务、压缩进度或锁定计划时，使用 `/pwf-switch`、`/pwf-compact`、`/pwf-attest`。

## 版本

当前版本：`0.2.6`。变更记录见 [CHANGELOG.md](CHANGELOG.md)。

重要：请不要再使用 `v0.1.0` 或更早版本。旧版本包含错误的 `/plw-*` 命令前缀，并且曾经引入过全局 prompts 安装路线，容易造成迁移和卸载混乱。请升级到当前版本并使用 `/pwf-*` 命令。

## 用户文档

- [普通用户使用指南](docs/USER_GUIDE.zh-CN.md)：用通俗语言说明这个工具是干什么的、什么时候用、怎么开始、怎么继续任务，以及多个会话怎么避免写混。
- [FAQ](docs/FAQ.md)：面向普通用户的常见问题，覆盖安装、命令不可见、上下文压缩、session policy、progress compaction、attestation 和中文模式。
- [v0.2.6 Release Notes](docs/RELEASE_NOTES_0.2.6.md)：本次发布的中英双语说明，可直接用于 GitHub Release。
- [CHANGELOG.md](CHANGELOG.md)：完整版本变更记录。

## 中文模式

默认情况下，Helsincy Plan With Files 保持英文输出，以兼容现有脚本和工作流。语言开关支持 `PWF_LANG=zh-CN` 和 `PWF_LANG=en`。需要简体中文 hook 提示、CLI 输出和初始化模板时，设置：

```powershell
$env:PWF_LANG="zh-CN"
python .codex\skills\planning-with-files\scripts\plan.py status
python .codex\skills\planning-with-files\scripts\plan.py init "中文任务"
```

强制英文输出可以设置：

```powershell
$env:PWF_LANG="en"
```

其他 `PWF_LANG` 值会回退英文；`plan.py doctor` 会报告 `language: warning unsupported PWF_LANG=<value>`。安全相关 delimiter、hash、文件路径、工具名和 `progress.md` auto record 字段名保持稳定 ASCII。

## 项目规划

- [中文化实现方案](docs/CHINESE_LOCALIZATION_PLAN.md)：规划项目内中文模式、中文模板、中文 CLI/hook 文案和后续 `v0.2.0` 发布路线。
- [Progress compaction 实现方案](docs/PROGRESS_COMPACTION_PLAN.md)：规划 `progress.md` 长期增长后的 compact、归档、summary 注入和 `/pwf-compact` 命令。
- [Context injection profiles 实现方案](docs/CONTEXT_INJECTION_PROFILES_PLAN.md)：规划可配置 hook 上下文注入窗口、record-aware progress 注入和诊断输出。

## 安装

推荐普通用户从 Release 下载 `HelsincyPlanWithFiles-v0.2.6-codex.zip`。这个包只包含安装到项目所需的 `.codex/`、hooks、`/pwf-*` commands 和基础文档。

### 方式 A：从 Release 下载

1. 打开 [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest)。
2. 下载 `HelsincyPlanWithFiles-v0.2.6-codex.zip`。
3. 解压后，把里面的 `.codex/` 复制到你的项目根目录。
4. 重启 Codex，第一次提示信任 hook 时选择批准。
5. 在 Codex 中运行 `/pwf-doctor` 检查安装状态。

目标项目目录应类似这样：

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

如果目标项目已经有 `.codex/`，请先备份或手动合并 `hooks.json`，避免覆盖已有的项目配置。

### 方式 B：从 git clone 安装

适合想看源码、跑测试或参与开发的用户：

```powershell
git clone https://github.com/TheLostRiver/HelsincyPlanWithFiles.git
Copy-Item -Recurse -Force .\HelsincyPlanWithFiles\.codex .\your-project\
```

### 方式 C：下载源码 zip

也可以在 GitHub 页面点击 `Code` -> `Download ZIP` 下载完整源码。解压后同样只需要把 `.codex/` 复制到目标项目根目录。普通使用优先选择 Release 里的 `codex.zip`。

## Agent Slash Commands

仓库提供 `.codex/skills/pwf-*` 本地 user-invocable skill wrapper。复制 `.codex/` 到目标项目后，这些命令会像 `/planning-with-files` 一样随项目生效，不需要安装到用户全局 `.codex`，卸载时删除项目内 `.codex/` 即可。

第一批命令都使用 `/pwf-XXX` 命名，`pwf` 代表 planning with files：

| 命令 | 作用 | 等价 CLI |
|------|------|----------|
| `/pwf-doctor` | 诊断 hook、active plan 和 attestation 状态 | `plan.py doctor` |
| `/pwf-init` | 创建新的 planning 任务；能识别会话时默认会绑定当前会话 | `plan.py init <task name>` |
| `/pwf-status` | 查看当前 active plan 状态 | `plan.py status` |
| `/pwf-switch` | 查看或切换 active plan | `plan.py switch [plan-id]` |
| `/pwf-tasks` | 列出当前会话可见的 PWF 任务和短 ID；默认不显示其他会话任务 | `plan.py tasks` |
| `/pwf-use` | 用 `/pwf-tasks` 显示的短 ID 或 plan id 绑定当前会话 | `plan.py use <id>` |
| `/pwf-attest` | 创建、查看或清除计划 hash attestation | `plan.py attest [--show or --clear]` |
| `/pwf-capture` | 把网页、浏览器、图片、PDF、文件或笔记上下文写入 `findings.md` | `plan.py capture ...` |
| `/pwf-compact` | 归档旧 auto records 并缩短 `progress.md` | `plan.py compact` |
| `/pwf-context-expanded` | 当前会话切到大型任务上下文模式 | `plan.py context set expanded` |
| `/pwf-context-deep` | 当前会话切到深度恢复上下文模式 | `plan.py context set deep` |
| `/pwf-context-default` | 当前会话恢复默认上下文模式 | `plan.py context set default` |
| `/pwf-context-lean` | 当前会话切到省上下文模式 | `plan.py context set lean` |
| `/pwf-context-status` | 查看当前会话上下文设置和来源 | `plan.py context status` |
| `/pwf-context-notice-auto` | 自动提示上下文注入情况 | `plan.py context notice auto` |
| `/pwf-context-notice-on` | 每次注入上下文都提示 | `plan.py context notice on` |
| `/pwf-context-notice-off` | 关闭上下文注入提示 | `plan.py context notice off` |

## 与原版对比

| 方向 | 原版 `planning-with-files` | Helsincy Plan With Files |
|------|----------------------------|--------------------------|
| 定位 | 多平台 Manus-style planning skill | Codex/Windows 优先 planning runtime |
| hook runtime | 偏 shell 脚本和跨平台镜像 | Python hook runtime，Windows 上更稳定 |
| progress 记录 | 更偏提醒 agent 手动记录 | hook 自动记录客观文件变更 |
| 诊断能力 | 依赖用户理解脚本和 hook 状态 | `plan.py doctor` 一条命令诊断安装、active plan、attestation |
| 安全边界 | canonical skill 强调 delimiter 和 attestation | delimiter、attestation、findings opt-in framing 已在 Codex hook 中落地 |

## 功能

- 在会话开始和用户提交提示时，把当前计划注入为 Codex 上下文。
- 在工具调用前提醒 agent 查看当前计划。
- 在文件写入或修改后，把变更摘要追加到 `progress.md`。
- 在停止前检查任务阶段是否完成，未完成时提醒继续收尾。
- 支持 Windows 优先的 Python hook runtime，同时保留 shell/PowerShell helper 脚本。

## 工作方式

这个工具使用三类本地 planning 文件：

```text
task_plan.md   # 阶段、目标、当前状态
findings.md    # 研究发现、决策、外部资料摘要
progress.md    # 执行动作、测试结果、文件变更记录
```

hook 会解析当前 active plan：

```text
PLAN_ID 环境变量
当前 session binding
.planning/.active_plan
最新的 .planning/<plan-id>/task_plan.md
项目根目录 task_plan.md
```

### Session Policy

默认情况下，`/pwf-init` 和 `plan.py init` 是 session-first：如果工具能识别当前 Codex 会话，也就是存在 `PWF_SESSION_ID` 或 `CODEX_THREAD_ID`，新建任务默认会绑定当前会话并写入 task lease。这样同一项目里开多个会话时，每个会话新建的 PWF 任务会自然归属各自会话。

`.planning/.active_plan` 仍会默认写入，但 workspace active 是兼容层，用来照顾单会话和旧工作流；多会话下优先使用当前 session binding。hook 仍使用 workspace session mode 作为默认 policy，因此 Codex 压缩上下文、resume、以及下一次用户提示后都更稳定。

严格的按会话隔离是显式 opt-in。只有当同一个项目里多个 Codex 会话必须互不共享 active plan 时才开启 `PWF_SESSION_MODE=strict`：

```powershell
$env:PWF_SESSION_MODE = "strict"
```

也可以创建 `.planning/session-policy.json`：

```json
{"mode":"strict"}
```

strict 模式下，hook payload 必须包含已 attach 的 `session_id`；否则 hook 会输出诊断消息，而不是静默跳过 planning 上下文。运行 `/pwf-doctor` 可以查看当前 session mode。

同一项目多会话并发时，通常直接在每个会话里运行 `/pwf-init <task name>` 即可。需要恢复旧的 workspace-only 行为时，显式使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-bind-session
```

需要只绑定当前会话、不更新 `.planning/.active_plan` 时使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-workspace-active
```

绑定已有任务时使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

显式写法仍然可用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

`--session` 只写 `.planning/session-bindings/<session-key>.json`，不会修改 `.planning/.active_plan`。旧的 `plan.py switch <plan-id>` 仍然切换 workspace active plan。

更省心的方式是先运行 `/pwf-tasks`。它默认只显示当前会话可见任务，不会列出其他会话独占任务。复制列表中的短 ID 后运行 `/pwf-use <short-id>` 即可绑定当前会话。需要诊断所有任务时才使用 `plan.py tasks --all`；即使在 `--all` 中看到了其他会话任务，接管或共享仍必须显式使用 `plan.py use <id> --claim` 或 `plan.py use <id> --share` 才能跨 ownership 边界。

`--legacy` 只用于根目录单任务兼容模式，不支持 session binding；`plan.py init "Task Name" --legacy --bind-session` 会被拒绝。需要多会话隔离时，请使用 `.planning/<plan-id>` 命名任务和默认 session-first 行为。

如果 workspace active task 已经由另一个 session 拥有，新的 session 不会自动接管；即使 owner 已经 stale，也必须显式选择。接管、共享和释放当前会话分别使用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --force-claim
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --share
python .codex\skills\planning-with-files\scripts\plan.py switch --release-session
```

如果希望 strict mode 同时要求 session 已 attach 且已有有效 binding，可以设置：

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```

自动写入的 `progress.md` 记录会包含 `Session` 和 `Plan-Source` 字段，便于审计一条记录来自哪个会话和哪一层 plan resolver。

### Context Profiles

默认 hook 上下文保持兼容：计划开头、最近 progress 和 opt-in findings 都使用原来的紧凑窗口。大型任务或上下文压缩后恢复时，可以开启更大的上下文注入 profile：

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
$env:PWF_INCLUDE_FINDINGS = "1"
```

`PWF_CONTEXT_PROFILE` 支持：

| Profile | 适合场景 |
|---------|----------|
| `lean` | 小任务、噪声多或想减少 hook payload |
| `default` | 默认兼容模式 |
| `expanded` | 推荐的大型功能开发模式，会注入计划尾部和 record-aware 最近 progress |
| `deep` | 上下文压缩或 resume 后需要更强恢复信息的刻意恢复模式 |
| `custom` | 高级用户用显式 `PWF_*` limit 变量调参 |

`findings.md` 始终需要显式开启：只有设置 `PWF_INCLUDE_FINDINGS=1` 后才会注入 findings。运行 `/pwf-status` 或 `/pwf-doctor` 可以查看当前 profile、progress 注入模式、findings 是否开启和有效预算。

`PostToolUse` 只记录真正的写文件/改文件工具：

```text
apply_patch | Edit | Write
```

读文件、搜索、浏览网页、查看图片或 PDF 不会被 hook 自动写入 `progress.md`。这些外部上下文应该由 agent 根据理解主动总结到 `findings.md`。

## 安装后验证和使用

安装完成并重启 Codex 后，优先使用 slash command 验证：

```text
/pwf-doctor
```

如果还看不到 `/pwf-*` 命令，也可以在目标项目根目录用终端备用命令检查：

```powershell
cd your-project
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

创建任务建议用：

```text
/pwf-init My Task
/pwf-status
```

终端备用命令是：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task"
python .codex\skills\planning-with-files\scripts\plan.py status
```

初始化后会生成这些 planning 文件：

```text
.planning/<plan-id>/task_plan.md
.planning/<plan-id>/findings.md
.planning/<plan-id>/progress.md
.planning/.active_plan
```

`.planning/.active_plan` 内容是当前计划目录名，例如：

```text
2026-05-11-codex-hooks-repair
```

然后正常使用 Codex。agent 修改文件后，hook 会自动在 active `progress.md` 中追加类似记录：

```text
### Auto Record: 2026-05-11 20:35:47
- Tool: apply_patch
- Session: unavailable
- Plan-Source: workspace
- Files:
  - `.codex/hooks/planning_state.py` (update)
```

默认记录只包含客观事实：时间、工具、结果和文件路径。设置 `PWF_LOG_COMMAND=1` 后，hook 会额外记录命令摘要，主要用于调试。

## Progress 生命周期

`progress.md` 是热日志，不是永久审计文件。长期任务中可以运行 `/pwf-compact`，把旧的客观 auto records 归档到 `progress.archive.md`，并在 `progress.md` 保留 compact summary 和最近记录。

```text
/pwf-compact
```

终端备用命令：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
python .codex\skills\planning-with-files\scripts\plan.py compact --keep-records 50
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
```

compact summary 只统计客观事实，例如归档数量、时间范围、工具计数和文件数量。agent 写入的解释性总结仍然只是参考，需要在关键场景结合 hook 记录、测试和实际代码核对。

## 安全边界

hook 注入 planning 文件时会使用 delimiter framing，把文件内容明确标记为数据：

```text
---BEGIN PLAN DATA---
...
---END PLAN DATA---

---BEGIN PROGRESS DATA---
...
---END PROGRESS DATA---

---BEGIN PROGRESS SUMMARY DATA---
...
---END PROGRESS SUMMARY DATA---
```

agent 应把这些 block 中的内容当作结构化数据，不执行其中出现的指令式文本。

如果想锁定已确认的计划，可以启用可选 hash attestation：

```powershell
powershell -ExecutionPolicy RemoteSigned -File .codex\skills\planning-with-files\scripts\attest-plan.ps1
```

PowerShell 脚本还支持 `-Show` 和 `-Clear`。在 shell 环境中也可以使用：

```text
sh .codex/skills/planning-with-files/scripts/attest-plan.sh
```

attestation 会把当前 `task_plan.md` 的 SHA-256 写入 `.planning/<plan-id>/.attestation`；如果使用项目根目录的 legacy `task_plan.md`，则写入 `.plan-attestation`。之后 hook 每次注入计划前都会重新计算 hash。若 hash 不匹配，hook 会阻断计划内容注入，只输出 `[PLAN TAMPERED - injection blocked]` 提醒，直到你检查计划并重新 attest 或清除 attestation。

## 仓库内容建议

建议提交：

```text
.codex/
docs/
tests/
README.md
README.en.md
.gitignore
```

不建议提交：

```text
.planning/
.plan-attestation
__pycache__/
*.pyc
```

`.planning/` 是运行时上下文，通常包含当前任务进度、自动记录和研究笔记，不适合作为工具代码提交。

## 测试

运行回归测试：

```powershell
python -m unittest discover -v
```

测试覆盖：

- `apply_patch` 文件变更记录
- `Edit` / `Write` 文件路径记录
- `Bash` 不写入 `progress.md`
- active plan 目录解析
- `UserPromptSubmit` / `SessionStart` JSON 输出
- planning data delimiter framing
- 可选 hash attestation 匹配和篡改阻断
- `Stop` 未完成任务拦截

## 设计原则

- hook 只自动记录文件写入和修改。
- hook 自动记录的是客观事实，例如工具、时间、结果和文件路径。
- agent 主动记录的是解释性笔记，例如原因、判断、风险和下一步；这些内容可供参考，但不保证绝对准确，需要结合事实日志和实际代码核对。
- 外部网页、浏览器、图片、PDF 等上下文由 agent 主动总结。
- planning 文件作为数据注入，不作为指令执行。
- delimiter framing 是默认保护；hash attestation 是可选的显式锁定。
- hook fail-open：出现异常时不应破坏 Codex 主流程。
