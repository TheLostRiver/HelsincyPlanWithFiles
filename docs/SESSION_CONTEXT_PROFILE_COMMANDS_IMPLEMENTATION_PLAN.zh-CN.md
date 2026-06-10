# 会话级上下文模式快捷命令实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行。每个任务用 checkbox 跟踪。

**Goal:** 增加只影响当前会话的 PWF context profile 快捷命令，并增加可开关的上下文注入提示。

**Architecture:** 保留现有环境变量体系作为最高优先级；新增 `.planning/session-context/<session-key>.json` 保存当前会话的 profile 和 notice；hook 通过 `planning_state.py` 统一解析；CLI 暴露 `plan.py context ...`；slash commands 只是薄包装。notice 渲染也放在 `planning_state.py`，保证 `UserPromptSubmit` 和 `SessionStart` 使用同一逻辑。

**Tech Stack:** Python 标准库、Codex hook、Codex skill wrapper、`.planning/` 本地 JSON 状态、`unittest`、Markdown 文档。

---

## 执行边界

本计划在隔离 worktree `D:\DEV\Plan_Skill-context-profile-commands` 和分支 `plan/session-context-profile-commands` 执行，不在 `main` 上直接操作。

英文逐步草稿保留在 `docs/SESSION_CONTEXT_PROFILE_COMMANDS_IMPLEMENTATION_PLAN.md`。本文件是中文主读版，后续实现时以本文件的任务边界、测试门槛和安全不变量为准。

本功能不创建 workspace 级 context 配置，不改变 session binding、task lease、workspace active plan 的既有语义。

## 文件职责

- Modify `.codex/hooks/planning_state.py`
  - 增加 session-context 路径与读取 helper。
  - 增加 `SessionContextSettings` 和 `ContextSettingsSource`。
  - 让 `context_limits()` 能在没有 env override 时使用当前 session profile。
  - 增加 notice 解析、提示渲染和估算 token 文案。
  - 让 `render_pre_tool_context()` 和 `render_prompt_context()` 传入 root/session。
- Modify `.codex/hooks/session_start.py`
  - 调用 `render_prompt_context(..., event="SessionStart")`，让 `auto` notice 在会话恢复时可见。
- Modify `.codex/skills/planning-with-files/scripts/plan.py`
  - 增加 `context` subcommand。
  - 增加 session-context 读写、清理和状态输出。
  - 扩展 `status` 和 `doctor` 的 context 来源诊断。
- Create `.codex/skills/pwf-context-expanded/SKILL.md`
- Create `.codex/skills/pwf-context-deep/SKILL.md`
- Create `.codex/skills/pwf-context-default/SKILL.md`
- Create `.codex/skills/pwf-context-lean/SKILL.md`
- Create `.codex/skills/pwf-context-status/SKILL.md`
- Create `.codex/skills/pwf-context-notice-on/SKILL.md`
- Create `.codex/skills/pwf-context-notice-off/SKILL.md`
- Create `.codex/skills/pwf-context-notice-auto/SKILL.md`
- Modify `tests/test_hooks.py`
- Modify `tests/test_plan_cli.py`
- Modify `tests/test_plan_doctor.py`
- Modify `tests/test_pwf_commands.py`
- Modify `tests/test_project_consistency.py`
- Modify `README.md`, `README.en.md`, `docs/FAQ.md`, `docs/USER_GUIDE.zh-CN.md`, `CHANGELOG.md`

## 关键不变量

当前会话的 context profile 只写入 `.planning/session-context/<session-key>.json`。不能写 workspace 默认配置，不能修改其他 session 的设置，不能修改 `.planning/.active_plan`。

没有 session id 时，读取状态可以继续，写入类命令必须拒绝。否则工具无法保证“只影响当前会话”。

环境变量优先于 session 设置。`PWF_CONTEXT_PROFILE=deep` 必须覆盖 session 文件里的 `expanded`，但状态输出要告诉用户 session 设置被覆盖。

`custom` 仍是 env-only。slash command 和 `plan.py context set` 只接受 `lean/default/expanded/deep`。

坏掉的 session-context JSON 不能让 hook 崩溃。hook 回退到 env 或默认设置，doctor 输出 warning。

notice 是 hook 生成的元数据，不是 planning file 里的内容。它不能从 `task_plan.md`、`progress.md`、`findings.md` 复制指令式文本。

token 数是估算值。英文使用 `approx`，中文使用“约”或“估算”。

## Task 1: hook 读取当前会话 context profile

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_hooks.py` 的 `ContextLimitResolverTests` 增加这些测试：

- `test_context_limits_use_session_profile_when_env_profile_missing`
- `test_env_context_profile_overrides_session_profile`
- `test_malformed_session_context_falls_back_without_crashing`

测试要覆盖：

```python
limits = PLANNING_STATE.context_limits({}, root=root, session_id="session-a")
source = PLANNING_STATE.context_settings_source({}, root=root, session_id="session-a")
```

断言：

```python
self.assertEqual(limits.profile, "expanded")
self.assertEqual(limits.progress_recent_records, 20)
self.assertEqual(source.profile_source, "session")
self.assertEqual(source.session_profile, "expanded")
```

env override 测试断言：

```python
self.assertEqual(limits.profile, "deep")
self.assertEqual(limits.progress_recent_records, 40)
self.assertEqual(source.profile_source, "env PWF_CONTEXT_PROFILE")
self.assertTrue(source.session_profile_overridden)
```

坏 JSON 测试断言：

```python
self.assertEqual(limits.profile, "default")
self.assertEqual(source.profile_source, "default")
self.assertTrue(any("session-context" in warning for warning in source.warnings))
```

- [ ] **Step 2: 确认测试失败**

```powershell
python -m unittest tests.test_hooks.ContextLimitResolverTests -v
```

预期：失败，因为 `context_limits()` 还不支持 `root/session_id`，`context_settings_source()` 还不存在。

- [ ] **Step 3: 增加数据结构和 helper**

在 `.codex/hooks/planning_state.py` 的 `ContextLimits` 附近增加：

```python
SESSION_CONTEXT_PROFILES = {"lean", "default", "expanded", "deep"}
CONTEXT_NOTICE_MODES = {"auto", "on", "off"}


@dataclass(frozen=True)
class SessionContextSettings:
    session_key: str
    profile: str | None
    notice: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextSettingsSource:
    profile: str
    profile_source: str
    session_profile: str | None
    session_profile_overridden: bool
    notice: str
    notice_source: str
    session_notice: str | None
    session_notice_overridden: bool
    warnings: tuple[str, ...] = ()
```

增加路径 helper：

```python
def session_context_path(root: Path, session_id: str) -> Path:
    return root / ".planning" / "session-context" / f"{session_key(session_id)}.json"
```

增加读取 helper。读取失败、JSON 不是 dict、profile/notice 非法时，返回 warning，不抛异常。

- [ ] **Step 4: 改造解析函数**

新增：

```python
def context_settings_source(
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> ContextSettingsSource:
    ...
```

解析顺序：

1. `PWF_CONTEXT_PROFILE`
2. session-context profile
3. default

notice 解析顺序：

1. `PWF_CONTEXT_NOTICE`
2. session-context notice
3. `auto`

然后把 `context_limits()` 签名改为：

```python
def context_limits(
    env: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> ContextLimits:
    ...
```

保留现有数值型 `PWF_*` override 行为。

- [ ] **Step 5: hook 渲染传入 session**

把：

```python
limits = context_limits()
```

改为：

```python
limits = context_limits(root=root, session_id=session_id)
```

覆盖 `render_pre_tool_context()` 和 `render_prompt_context()`。

- [ ] **Step 6: 运行 Task 1 测试**

```powershell
python -m unittest tests.test_hooks.ContextLimitResolverTests -v
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_expanded_profile_includes_complete_recent_progress_records tests.test_hooks.HookTests.test_user_prompt_submit_deep_profile_uses_larger_recent_record_count -v
```

预期：全部通过，原有 env profile 测试不回退。

- [ ] **Step 7: 提交**

```powershell
git add .codex/hooks/planning_state.py tests/test_hooks.py
git commit -m "feat: resolve session context profiles"
```

## Task 2: CLI `plan.py context ...`

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`

- [ ] **Step 1: 写失败测试**

在 `PlanCliTests` 增加：

- `test_context_set_expanded_writes_current_session_context`
- `test_context_set_without_session_id_is_rejected`
- `test_context_status_reports_session_profile_and_env_override`
- `test_context_notice_commands_update_current_session_context`
- `test_context_clear_removes_current_session_context`

必须断言 session 文件路径：

```python
key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
path = root / ".planning" / "session-context" / f"{key}.json"
```

`set expanded` 后 JSON 至少包含：

```python
self.assertEqual(payload["profile"], "expanded")
self.assertEqual(payload["notice"], "auto")
```

无 session id 时断言：

```python
self.assertNotEqual(result.returncode, 0)
self.assertIn("session id: unavailable", result.stdout + result.stderr)
self.assertFalse((root / ".planning" / "session-context").exists())
```

- [ ] **Step 2: 确认测试失败**

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_context_set_expanded_writes_current_session_context tests.test_plan_cli.PlanCliTests.test_context_set_without_session_id_is_rejected tests.test_plan_cli.PlanCliTests.test_context_status_reports_session_profile_and_env_override tests.test_plan_cli.PlanCliTests.test_context_notice_commands_update_current_session_context tests.test_plan_cli.PlanCliTests.test_context_clear_removes_current_session_context -v
```

预期：失败，因为还没有 `context` subcommand。

- [ ] **Step 3: 增加 CLI 文案**

`CLI_MESSAGES["en"]` 增加：

```python
"help_context": "Manage current-session context profile",
"context_profile_set": "context profile set: {profile}",
"context_notice_set": "context notice set: {notice}",
"context_cleared": "context settings cleared: {key}",
"context_missing_session": "session id: unavailable; context commands only affect the current session",
"context_invalid_profile": "unsupported context profile: {profile}",
"context_invalid_notice": "unsupported context notice mode: {notice}",
```

`CLI_MESSAGES["zh-CN"]` 增加中文说明。关键短语如 `context profile set`、`session id: unavailable` 保持 ASCII，方便测试和排障。

- [ ] **Step 4: 增加 session-context 写入 helper**

在现有 session binding helper 附近增加：

```python
def _session_context_path(root: Path, session_id: str) -> Path:
    return planning_state.session_context_path(root, session_id)


def _read_session_context_payload(root: Path, session_id: str) -> dict[str, object]:
    ...


def _write_session_context(
    root: Path,
    session_id: str,
    *,
    profile: str | None = None,
    notice: str | None = None,
) -> str:
    ...


def _clear_session_context(root: Path, session_id: str) -> str:
    ...
```

写入必须：

- 创建 `.planning/session-context`。
- 保留已有 `created_at`。
- 更新 `updated_at`。
- 默认 `profile=default`、`notice=auto`。
- 使用 `.tmp` 文件再 `replace()`。

- [ ] **Step 5: 增加状态 formatter 和 command handler**

新增 `_context_source_lines(root, session_id)`，输出：

```text
session context:
  profile: expanded
  source: session
  session profile: expanded
  notice: auto
  notice source: session
  progress mode: record-aware 20 records
  plan: head 80 tail 40
  findings: off
  max: 56000 chars
```

新增：

```python
def context(root: Path, action: str, value: str | None = None) -> int:
    ...
```

行为：

- `status` 不要求 session id。
- `set`、`notice`、`clear` 要求 session id。
- `set custom` 拒绝。
- `notice` 只接受 `auto/on/off`。

- [ ] **Step 6: 接入 argparse**

在 `main()` 增加：

```python
context_parser = subparsers.add_parser("context", help=_help("context"))
context_subparsers = context_parser.add_subparsers(dest="context_command", required=True)
context_subparsers.add_parser("status")
context_set = context_subparsers.add_parser("set")
context_set.add_argument("profile")
context_notice = context_subparsers.add_parser("notice")
context_notice.add_argument("mode")
context_subparsers.add_parser("clear")
```

dispatch 到 `context(root, ...)`。

- [ ] **Step 7: 运行 CLI 测试**

```powershell
python -m unittest tests.test_plan_cli.PlanCliTests.test_context_set_expanded_writes_current_session_context tests.test_plan_cli.PlanCliTests.test_context_set_without_session_id_is_rejected tests.test_plan_cli.PlanCliTests.test_context_status_reports_session_profile_and_env_override tests.test_plan_cli.PlanCliTests.test_context_notice_commands_update_current_session_context tests.test_plan_cli.PlanCliTests.test_context_clear_removes_current_session_context -v
```

预期：全部通过。

- [ ] **Step 8: 提交**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_cli.py
git commit -m "feat: add session context CLI commands"
```

## Task 3: 注入提示 notice

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/hooks/session_start.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: 写失败测试**

在 `HookTests` 增加：

- `test_user_prompt_submit_session_expanded_profile_shows_auto_notice`
- `test_user_prompt_submit_default_profile_auto_notice_stays_quiet`
- `test_user_prompt_submit_notice_off_suppresses_expanded_notice`
- `test_user_prompt_submit_notice_on_shows_default_notice`

expanded + auto 应断言：

```python
self.assertIn("Injected current-session planning context", context)
self.assertIn("profile=expanded", context)
self.assertIn("progress=20 records", context)
self.assertRegex(context, r"approx [0-9.]+k chars \(~[0-9.]+k tokens\)")
```

default + auto 应断言不显示 notice。

notice off 应断言不显示 notice。

notice on + default 应断言显示 notice。

- [ ] **Step 2: 确认测试失败**

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_session_expanded_profile_shows_auto_notice tests.test_hooks.HookTests.test_user_prompt_submit_default_profile_auto_notice_stays_quiet tests.test_hooks.HookTests.test_user_prompt_submit_notice_off_suppresses_expanded_notice tests.test_hooks.HookTests.test_user_prompt_submit_notice_on_shows_default_notice -v
```

预期：失败，因为 notice 还不存在。

- [ ] **Step 3: 增加 hook 文案**

`MESSAGES["en"]` 增加：

```python
"context_injection_notice": (
    "[planning-with-files] Injected current-session planning context: "
    "profile={profile}, progress={progress}, approx {chars} chars (~{tokens} tokens)."
),
```

`MESSAGES["zh-CN"]` 增加：

```python
"context_injection_notice": (
    "[planning-with-files] 已自动注入当前会话的任务上下文："
    "profile={profile}，progress={progress}，约 {chars} chars（估算 {tokens} tokens）。"
),
```

- [ ] **Step 4: 增加估算 helper**

在 `planning_state.py` 增加 `import math`，并增加：

```python
def _format_approx_count(value: int) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def _estimated_tokens(chars: int) -> int:
    return max(1, math.ceil(chars / 4))


def _progress_notice_text(limits: ContextLimits) -> str:
    if limits.progress_recent_records > 0:
        return f"{limits.progress_recent_records} records"
    return f"tail {limits.progress_tail_lines} lines"
```

增加判断：

```python
def _should_show_context_notice(settings: ContextSettingsSource, limits: ContextLimits, *, event: str) -> bool:
    if settings.notice == "off":
        return False
    if settings.notice == "on":
        return True
    return limits.profile in {"expanded", "deep"} or event == "SessionStart"
```

- [ ] **Step 5: 增加 notice 渲染函数**

```python
def _append_context_notice(
    rendered: str,
    *,
    settings: ContextSettingsSource,
    limits: ContextLimits,
    event: str,
) -> str:
    if not rendered:
        return rendered
    if not _should_show_context_notice(settings, limits, event=event):
        return rendered
    chars = len(rendered)
    tokens = _estimated_tokens(chars)
    notice = message(
        "context_injection_notice",
        profile=limits.profile,
        progress=_progress_notice_text(limits),
        chars=_format_approx_count(chars),
        tokens=_format_approx_count(tokens),
    )
    return f"{notice}\n{rendered}"
```

`if not rendered` 必须保留，避免没有任何可注入上下文时只输出一行 notice。

- [ ] **Step 6: `render_prompt_context()` 接收 event**

签名改为：

```python
def render_prompt_context(root: Path, session_id: str | None = None, event: str = "UserPromptSubmit") -> str:
    ...
```

内部顺序：

```python
settings = context_settings_source(root=root, session_id=session_id)
limits = context_limits(root=root, session_id=session_id)
rendered = apply_total_context_budget("\n".join(parts).rstrip(), limits)
rendered = _append_context_notice(rendered, settings=settings, limits=limits, event=event)
return apply_total_context_budget(rendered, limits)
```

第二次 budget 是为了 notice 追加后仍不超过总上限。

- [ ] **Step 7: `SessionStart` 传事件名**

在 `.codex/hooks/session_start.py` 改为：

```python
planning_state.render_prompt_context(root, session_id=session_id, event="SessionStart")
```

`user_prompt_submit.py` 可以继续省略 `event`。

- [ ] **Step 8: 运行 notice 测试**

```powershell
python -m unittest tests.test_hooks.HookTests.test_user_prompt_submit_session_expanded_profile_shows_auto_notice tests.test_hooks.HookTests.test_user_prompt_submit_default_profile_auto_notice_stays_quiet tests.test_hooks.HookTests.test_user_prompt_submit_notice_off_suppresses_expanded_notice tests.test_hooks.HookTests.test_user_prompt_submit_notice_on_shows_default_notice -v
python -m unittest tests.test_hooks -v
```

预期：全部通过。

- [ ] **Step 9: 提交**

```powershell
git add .codex/hooks/planning_state.py .codex/hooks/session_start.py tests/test_hooks.py
git commit -m "feat: show optional context injection notices"
```

## Task 4: status 和 doctor 诊断

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_cli.py`
- Test: `tests/test_plan_doctor.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_plan_doctor.py` 增加：

- `test_doctor_reports_session_context_profile_source`
- `test_doctor_reports_env_override_for_session_context`

断言：

```python
self.assertIn("context profile: expanded", result.stdout)
self.assertIn("context profile source: session", result.stdout)
self.assertIn("context notice: auto", result.stdout)
self.assertIn("context progress mode: record-aware 20 records", result.stdout)
```

env override 断言：

```python
self.assertIn("context profile: deep", result.stdout)
self.assertIn("context profile source: env PWF_CONTEXT_PROFILE", result.stdout)
self.assertIn("context session profile: expanded overridden", result.stdout)
```

在 `tests/test_plan_cli.py` 的 `test_status_reports_expanded_context_profile_summary` 增加：

```python
self.assertIn("context source: env PWF_CONTEXT_PROFILE", result.stdout)
self.assertIn("context notice: auto", result.stdout)
```

- [ ] **Step 2: 确认测试失败**

```powershell
python -m unittest tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_session_context_profile_source tests.test_plan_doctor.PlanDoctorTests.test_doctor_reports_env_override_for_session_context tests.test_plan_cli.PlanCliTests.test_status_reports_expanded_context_profile_summary -v
```

- [ ] **Step 3: 扩展 status**

把 `_context_status_line()` 改为 `_context_status_lines(root, session_id)`：

```python
def _context_status_lines(root: Path, session_id: str | None) -> list[str]:
    limits = planning_state.context_limits(root=root, session_id=session_id)
    source = planning_state.context_settings_source(root=root, session_id=session_id)
    lines = [
        (
            f"context: profile={limits.profile}, "
            f"plan=head {limits.plan_head_lines} tail {limits.plan_tail_lines}, "
            f"progress={_context_progress_text(limits)}, "
            f"findings={_context_findings_text(limits)}, "
            f"max={limits.context_max_chars} chars"
        ),
        f"context source: {source.profile_source}",
        f"context notice: {source.notice}",
    ]
    if source.session_profile_overridden and source.session_profile:
        lines.append(f"context session profile: {source.session_profile} overridden")
    lines.extend(source.warnings)
    return lines
```

`status()` 逐行打印。

- [ ] **Step 4: 扩展 doctor**

把 `_context_doctor_lines()` 改为接收 `root/session_id`，输出：

```python
f"context profile: {limits.profile}"
f"context profile source: {source.profile_source}"
f"context notice: {source.notice}"
f"context notice source: {source.notice_source}"
```

如果 session profile 或 session notice 被 env 覆盖，输出：

```python
context session profile: expanded overridden
context session notice: off overridden
```

- [ ] **Step 5: 运行诊断测试**

```powershell
python -m unittest tests.test_plan_doctor tests.test_plan_cli.PlanCliTests.test_status_reports_active_plan_summary tests.test_plan_cli.PlanCliTests.test_status_reports_expanded_context_profile_summary -v
```

预期：全部通过。

- [ ] **Step 6: 提交**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_cli.py tests/test_plan_doctor.py
git commit -m "feat: report context profile sources"
```

## Task 5: slash command wrapper

**Files:**
- Create: `.codex/skills/pwf-context-expanded/SKILL.md`
- Create: `.codex/skills/pwf-context-deep/SKILL.md`
- Create: `.codex/skills/pwf-context-default/SKILL.md`
- Create: `.codex/skills/pwf-context-lean/SKILL.md`
- Create: `.codex/skills/pwf-context-status/SKILL.md`
- Create: `.codex/skills/pwf-context-notice-on/SKILL.md`
- Create: `.codex/skills/pwf-context-notice-off/SKILL.md`
- Create: `.codex/skills/pwf-context-notice-auto/SKILL.md`
- Modify: `tests/test_pwf_commands.py`

- [ ] **Step 1: 写失败测试**

更新 `tests/test_pwf_commands.py` 的 `COMMANDS`：

```python
"pwf-context-expanded": "context set expanded",
"pwf-context-deep": "context set deep",
"pwf-context-default": "context set default",
"pwf-context-lean": "context set lean",
"pwf-context-status": "context status",
"pwf-context-notice-on": "context notice on",
"pwf-context-notice-off": "context notice off",
"pwf-context-notice-auto": "context notice auto",
```

路由测试要对 multi-word route 逐词断言：

```python
for part in subcommand.split():
    self.assertIn(part, text)
```

- [ ] **Step 2: 确认测试失败**

```powershell
python -m unittest tests.test_pwf_commands -v
```

预期：失败，因为 wrapper 目录还不存在。

- [ ] **Step 3: 创建 wrapper**

每个 wrapper 都是薄文档，运行对应 CLI。示例：

````markdown
---
name: pwf-context-expanded
description: Switch the current session to expanded PWF context injection. Invoke with /pwf-context-expanded.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-context-expanded

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py context set expanded
```

中文模式：如果用户希望中文输出，先设置 `PWF_LANG=zh-CN`，再运行相同命令。

This changes only the current session context profile. It does not change other sessions or workspace active plan.
````

`deep/default/lean/status/notice-*` 按同一结构写清楚对应命令和“只影响当前会话”。

- [ ] **Step 4: 运行 wrapper 测试**

```powershell
python -m unittest tests.test_pwf_commands -v
```

预期：通过。

- [ ] **Step 5: 提交**

```powershell
git add .codex/skills/pwf-context-expanded .codex/skills/pwf-context-deep .codex/skills/pwf-context-default .codex/skills/pwf-context-lean .codex/skills/pwf-context-status .codex/skills/pwf-context-notice-on .codex/skills/pwf-context-notice-off .codex/skills/pwf-context-notice-auto tests/test_pwf_commands.py
git commit -m "feat: add context profile slash commands"
```

## Task 6: 用户文档和一致性

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `docs/USER_GUIDE.zh-CN.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_project_consistency.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_project_consistency.py` 增加：

```python
def test_docs_document_session_context_profile_commands(self):
    readme_cn = read_text("README.md")
    readme_en = read_text("README.en.md")
    faq = read_text("docs/FAQ.md")
    user_guide = read_text("docs/USER_GUIDE.zh-CN.md")
    changelog = read_text("CHANGELOG.md")
    combined = "\n".join([readme_cn, readme_en, faq, user_guide, changelog])

    for phrase in (
        "/pwf-context-expanded",
        "/pwf-context-deep",
        "/pwf-context-status",
        "/pwf-context-notice-auto",
        "current session",
        "当前会话",
        "record-aware",
        "PWF_CONTEXT_PROFILE",
    ):
        self.assertIn(phrase, combined)
```

- [ ] **Step 2: 确认测试失败**

```powershell
python -m unittest tests.test_project_consistency.ProjectConsistencyTests.test_docs_document_session_context_profile_commands -v
```

- [ ] **Step 3: 更新 README 命令表**

中文 README 增加：

```markdown
| `/pwf-context-expanded` | 当前会话切到大型任务上下文模式 | `plan.py context set expanded` |
| `/pwf-context-deep` | 当前会话切到深度恢复上下文模式 | `plan.py context set deep` |
| `/pwf-context-default` | 当前会话恢复默认上下文模式 | `plan.py context set default` |
| `/pwf-context-lean` | 当前会话切到省上下文模式 | `plan.py context set lean` |
| `/pwf-context-status` | 查看当前会话上下文设置和来源 | `plan.py context status` |
| `/pwf-context-notice-auto` | 自动提示上下文注入情况 | `plan.py context notice auto` |
| `/pwf-context-notice-on` | 每次注入上下文都提示 | `plan.py context notice on` |
| `/pwf-context-notice-off` | 关闭上下文注入提示 | `plan.py context notice off` |
```

英文 README 增加对应英文行。

- [ ] **Step 4: 更新 FAQ 和普通用户指南**

把优先说明改为 slash command：

```text
/pwf-context-expanded
/pwf-context-deep
```

说明：

- 命令只影响当前会话。
- `PWF_CONTEXT_PROFILE` 仍保留给高级用法。
- 环境变量优先级高于会话设置。
- notice 显示的是估算占用，不是精确 token。

- [ ] **Step 5: 更新 changelog**

`## Unreleased` 下增加中英双语：

```markdown
- 中文：新增会话级 context profile 快捷命令，可用 `/pwf-context-expanded`、`/pwf-context-deep`、`/pwf-context-default`、`/pwf-context-lean` 和 `/pwf-context-status` 管理当前会话上下文注入强度。
- 中文：新增 context injection notice 开关：`/pwf-context-notice-auto`、`/pwf-context-notice-on`、`/pwf-context-notice-off`，可提示已自动注入任务上下文及大致占用。
- English: Added session-scoped context profile shortcuts for `/pwf-context-expanded`, `/pwf-context-deep`, `/pwf-context-default`, `/pwf-context-lean`, and `/pwf-context-status`.
- English: Added context injection notice controls through `/pwf-context-notice-auto`, `/pwf-context-notice-on`, and `/pwf-context-notice-off`, including approximate prompt-size reporting.
```

- [ ] **Step 6: 运行一致性测试**

```powershell
python -m unittest tests.test_project_consistency -v
```

预期：通过。

- [ ] **Step 7: 提交**

```powershell
git add README.md README.en.md docs/FAQ.md docs/USER_GUIDE.zh-CN.md CHANGELOG.md tests/test_project_consistency.py
git commit -m "docs: document context profile commands"
```

## Task 7: 最终验证

**Files:**
- No new files unless fixes are required.

- [ ] **Step 1: 运行目标测试**

```powershell
python -m unittest tests.test_plan_cli tests.test_hooks tests.test_plan_doctor tests.test_pwf_commands tests.test_project_consistency -v
```

预期：全部通过。

- [ ] **Step 2: 运行全量测试**

```powershell
python -m unittest discover -v
```

预期：全部通过。

- [ ] **Step 3: 检查 diff 空白**

```powershell
git diff --check
```

预期：无输出，退出码 0。

- [ ] **Step 4: 手动 smoke test**

```powershell
$tmp = Join-Path $env:TEMP "pwf-context-smoke"
if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
Copy-Item -Recurse .codex $tmp
Push-Location $tmp
$env:PWF_SESSION_ID = "smoke-session"
python .codex\skills\planning-with-files\scripts\plan.py init "Smoke Context"
python .codex\skills\planning-with-files\scripts\plan.py context set expanded
python .codex\skills\planning-with-files\scripts\plan.py context status
python .codex\skills\planning-with-files\scripts\plan.py status
Pop-Location
```

预期：

- `context set expanded` 成功。
- `context status` 显示 `profile: expanded` 和 `source: session`。
- `status` 显示 `progress=20 records`。

- [ ] **Step 5: 检查提交范围**

```powershell
git status --short --branch --untracked-files=all
git log --oneline --max-count=8
git diff origin/main...HEAD --stat
```

预期：

- 分支是 `plan/session-context-profile-commands`。
- 没有无关 tracked changes。
- 提交按任务拆分。

## 完成标准

- 当前会话可通过 slash command 切换 `lean/default/expanded/deep`。
- session-context 文件只写当前 session key。
- 缺少 session id 时，写入类命令失败。
- env override 行为完全兼容。
- notice 可以按 `auto/on/off` 工作。
- status 和 doctor 可以解释来源与覆盖关系。
- 文档用通俗语言说明普通用户怎么用。
- 目标测试、全量测试和 `git diff --check` 通过。
