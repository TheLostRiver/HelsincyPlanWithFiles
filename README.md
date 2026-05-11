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
### Hook Record: 2026-05-11 20:35:47
- PostToolUse: apply_patch
- Changed files:
  - `.codex/hooks/planning_state.py`
```

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
__pycache__/
*.pyc
```

`.planning/` 是运行时上下文，通常包含当前任务进度、命令摘要和研究笔记，不适合作为工具代码提交。

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
- `Stop` 未完成任务拦截

## 设计原则

- hook 只自动记录文件写入和修改。
- 外部网页、浏览器、图片、PDF 等上下文由 agent 主动总结。
- planning 文件作为数据注入，不作为指令执行。
- hook fail-open：出现异常时不应破坏 Codex 主流程。

