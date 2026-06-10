# 会话级上下文模式快捷命令方案

## 目标

为 PWF 增加“只影响当前会话”的上下文模式快捷命令，让用户不用手动设置环境变量，也能在长任务、上下文压缩、恢复会话时切到更多任务上下文。

同时增加可开关的上下文注入提示：当工具自动把当前 PWF 任务上下文放回提示词时，可以告诉用户“已经注入了任务上下文”，并给出大致字符数和估算 token 数。

英文版设计稿保留在 `docs/SESSION_CONTEXT_PROFILE_COMMANDS_PLAN.md`。

## 用户能看到什么

新增命令：

```text
/pwf-context-expanded
/pwf-context-deep
/pwf-context-default
/pwf-context-lean
/pwf-context-status
/pwf-context-notice-auto
/pwf-context-notice-on
/pwf-context-notice-off
```

这些命令默认只作用于当前 Codex 会话。它们不会修改 `.planning/.active_plan`，不会影响同项目下其他会话，也不会把当前会话切到别的会话正在使用的 PWF 任务。

底层 CLI：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py context status
python .codex\skills\planning-with-files\scripts\plan.py context set expanded
python .codex\skills\planning-with-files\scripts\plan.py context set deep
python .codex\skills\planning-with-files\scripts\plan.py context set default
python .codex\skills\planning-with-files\scripts\plan.py context set lean
python .codex\skills\planning-with-files\scripts\plan.py context notice auto
python .codex\skills\planning-with-files\scripts\plan.py context notice on
python .codex\skills\planning-with-files\scripts\plan.py context notice off
python .codex\skills\planning-with-files\scripts\plan.py context clear
```

## 上下文模式

现有 `PWF_CONTEXT_PROFILE` 已经支持这些模式：

| 模式 | 行为 |
|------|------|
| `lean` | 少量注入，适合省上下文 |
| `default` | 兼容旧行为，按行注入最近 progress |
| `expanded` | 注入更多 plan，并按完整 auto record 注入最近 20 条 progress |
| `deep` | 比 expanded 更强，按完整 auto record 注入最近 40 条 progress |
| `custom` | 仍只通过环境变量和数值覆盖使用，不做 slash 快捷命令 |

新增快捷命令只开放 `lean/default/expanded/deep`。`custom` 需要多个数值参数，不适合作为一键命令。

## 会话级存储

当前会话的上下文设置保存到：

```text
.planning/session-context/<session-key>.json
```

示例：

```json
{
  "version": 1,
  "session_id": "opaque-session-id",
  "profile": "expanded",
  "notice": "auto",
  "created_at": "2026-06-10T06:30:00Z",
  "updated_at": "2026-06-10T06:30:00Z",
  "source": "plan.py context"
}
```

文件名使用 `planning_state.session_key(session_id)`，不直接使用原始 session id。JSON 里保留原始 session id 只用于本地诊断。

写入时使用临时文件加 replace，沿用 session binding 的安全风格。

## 会话识别

CLI 继续从下面两个来源识别当前会话：

```text
PWF_SESSION_ID
CODEX_THREAD_ID
```

hook 继续优先从 hook payload 读取 session id，再使用现有 fallback。

如果没有 session id：

- `context status` 可以执行，但会说明没有当前会话设置。
- `context set ...`、`context notice ...`、`context clear` 必须失败。
- 不允许退化成 workspace 级设置。

这个规则非常重要：如果无法确认“当前会话是谁”，工具就不能声称“只改当前会话”。

## 优先级

最终生效的设置按这个顺序解析：

1. 环境变量：
   - `PWF_CONTEXT_PROFILE`
   - `PWF_CONTEXT_NOTICE`
   - 现有 `PWF_*` 数值覆盖
2. 当前 session 的 `.planning/session-context/<session-key>.json`
3. 内置默认值

环境变量优先级最高，因为它通常代表高级用户、脚本或 CI 的明确配置。

`/pwf-context-status` 和 `plan.py doctor` 必须说明设置来源。比如 session 设置为 `expanded`，但环境变量覆盖成 `deep` 时，状态里要明确显示：

```text
profile: deep
source: env PWF_CONTEXT_PROFILE
session profile: expanded, currently overridden
```

## 注入提示

新增 notice 模式：

| 模式 | 行为 |
|------|------|
| `off` | 从不显示注入提示 |
| `on` | 只要注入 prompt context 就显示 |
| `auto` | 默认值；在 `expanded`、`deep` 或 `SessionStart` 时显示 |

英文提示示例：

```text
[planning-with-files] Injected current-session planning context: profile=expanded, progress=20 records, approx 18.4k chars (~4.6k tokens).
```

中文提示示例：

```text
[planning-with-files] 已自动注入当前会话的任务上下文：profile=expanded，progress=20 records，约 18.4k chars（估算 4.6k tokens）。
```

token 估算使用：

```text
estimated_tokens = ceil(chars / 4)
```

提示必须说“估算”或 `approx`，不能声称精确。

## 错误处理

这些操作必须拒绝：

- `context set custom`
- `context set <未知模式>`
- `context notice <未知模式>`
- 没有 session id 时执行任何会写入的 context 命令

如果 session-context JSON 损坏：

- hook 不能崩溃。
- 生效设置回退到环境变量或默认值。
- `doctor` 输出 warning。

## 需要修改的文件

| 文件 | 责任 |
|------|------|
| `.codex/hooks/planning_state.py` | 解析 session context、notice、注入提示和诊断来源 |
| `.codex/skills/planning-with-files/scripts/plan.py` | 增加 `context` CLI、读写 session-context、扩展 status/doctor |
| `.codex/skills/pwf-context-*/SKILL.md` | 新增 slash command wrapper |
| `tests/test_hooks.py` | hook 解析和 notice 测试 |
| `tests/test_plan_cli.py` | CLI context 命令测试 |
| `tests/test_plan_doctor.py` | doctor 诊断测试 |
| `tests/test_pwf_commands.py` | slash wrapper 覆盖 |
| `tests/test_project_consistency.py` | 文档一致性检查 |
| `README.md`, `README.en.md`, `docs/FAQ.md`, `docs/USER_GUIDE.zh-CN.md`, `CHANGELOG.md` | 用户文档和发布说明 |

## 验收标准

- `/pwf-context-expanded` 和 `/pwf-context-deep` 不需要环境变量即可作用于当前会话。
- 同项目其他会话不受影响。
- 没有 session id 时，写入类命令拒绝执行。
- `PWF_CONTEXT_PROFILE` 仍然可用，并优先于 session 设置。
- prompt context 可以按 `auto/on/off` 显示注入提示。
- status 和 doctor 能解释 profile、notice 和来源。
- 测试全部通过。
