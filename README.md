# Helsincy Plan With Files

[简体中文](README.md) | [English](README.en.md)

Helsincy Plan With Files 是一个用于 Codex 的 skill + hook 工具。它把任务计划、研究发现和执行进度保存在项目本地文件中，让 agent 在长任务、上下文压缩或会话恢复后仍能继续工作。

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

## 安装

把 `.codex/` 目录复制到目标项目根目录：

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

确保 Codex hooks 已启用，并在 Codex 提示信任 hook 时批准。当前配置使用 `python` 运行 hook，因此 Windows 环境下不依赖 `python3` 或 `sh`。

## 使用

初始化 planning 文件可以使用 skill 自带脚本，或者手动创建：

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
