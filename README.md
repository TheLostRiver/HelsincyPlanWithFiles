# Helsincy Plan With Files

[简体中文](README.md) | [English](README.en.md)

Helsincy Plan With Files 是一个用于 Codex 的 skill + hook 工具。它把任务计划、研究发现和执行进度保存在项目本地文件中，让 agent 在长任务、上下文压缩或会话恢复后仍能继续工作。

## 版本

当前版本：`0.1.1`。变更记录见 [CHANGELOG.md](CHANGELOG.md)。

重要：请不要再使用 `v0.1.0` 或更早版本。旧版本包含错误的 `/plw-*` 命令前缀，并且曾经引入过全局 prompts 安装路线，容易造成迁移和卸载混乱。请升级到 `v0.1.1` 并使用 `/pwf-*` 命令。

## 项目规划

- [中文化实现方案](docs/CHINESE_LOCALIZATION_PLAN.md)：规划项目内中文模式、中文模板、中文 CLI/hook 文案和后续 `v0.2.0` 发布路线。

## 安装

推荐普通用户从 Release 下载 `HelsincyPlanWithFiles-v0.1.1-codex.zip`。这个包只包含安装到项目所需的 `.codex/`、hooks、`/pwf-*` commands 和基础文档。

### 方式 A：从 Release 下载

1. 打开 [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest)。
2. 下载 `HelsincyPlanWithFiles-v0.1.1-codex.zip`。
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
| `/pwf-init` | 创建新的 planning 任务 | `plan.py init <task name>` |
| `/pwf-status` | 查看当前 active plan 状态 | `plan.py status` |
| `/pwf-switch` | 查看或切换 active plan | `plan.py switch [plan-id]` |
| `/pwf-attest` | 创建、查看或清除计划 hash attestation | `plan.py attest [--show or --clear]` |
| `/pwf-capture` | 把网页、浏览器、图片、PDF、文件或笔记上下文写入 `findings.md` | `plan.py capture ...` |

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
.planning/.active_plan
最新的 .planning/<plan-id>/task_plan.md
项目根目录 task_plan.md
```

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
- Files:
  - `.codex/hooks/planning_state.py`
```

默认记录只包含客观事实：时间、工具、结果和文件路径。设置 `PWF_LOG_COMMAND=1` 后，hook 会额外记录命令摘要，主要用于调试。

## 安全边界

hook 注入 planning 文件时会使用 delimiter framing，把文件内容明确标记为数据：

```text
---BEGIN PLAN DATA---
...
---END PLAN DATA---

---BEGIN PROGRESS DATA---
...
---END PROGRESS DATA---
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
