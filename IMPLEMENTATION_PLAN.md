# Helsincy Plan With Files 实现方案

> **给执行 agent 的要求：** 实施本文档时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。所有步骤都使用 checkbox（`- [ ]`）追踪状态。

**目标：** 让 Helsincy Plan With Files 在 Codex 优先、Windows 优先的 planning 工作流上超越原版 `planning-with-files`。

**架构方向：** 保留当前 Python hook runtime 作为可信核心；新增一个统一的 Python 命令入口处理 init/status/switch/attest/doctor/capture；PowerShell 和 shell 脚本作为兼容 wrapper。planning 数据继续本地优先存储在 `.planning/`，hook 输出保持 fail-open、结构化、可测试。

**技术栈：** Python 标准库、PowerShell wrapper、现有 Codex hooks、`unittest`、Markdown 文档。

---

## 1. 产品定位

不要用“多平台覆盖”去和原版硬拼。原版在多 IDE、多平台镜像、社区传播上很强。我们的突破点应该是：

- Codex/Windows 上更稳定。
- hook 行为更可诊断。
- 自动记录客观事实，而不是只提醒 agent 手写。
- 对外部上下文和 prompt injection 有更明确的安全边界。
- 提供一套统一命令，让用户不用记多个脚本。

最终定位：

```text
原版：广覆盖的 Manus-style planning skill。
Helsincy 版：Codex/Windows 上更可靠、更可诊断、更自动化的 planning runtime。
```

## 2. 当前优势

- Python hook runtime 已经能在 Windows 上运行，不依赖 `sh` 或 `python3`。
- `UserPromptSubmit`、`SessionStart`、`PreToolUse`、`PostToolUse`、`Stop` 都有回归测试。
- 计划注入已经带 `---BEGIN PLAN DATA---` / `---END PLAN DATA---`。
- 进度注入已经带 `---BEGIN PROGRESS DATA---` / `---END PROGRESS DATA---`。
- 可选 SHA-256 attestation 已经能在计划被改动后阻断注入。
- `PostToolUse` 会自动把客观文件变更写入 `progress.md`。
- README 已经有中英文版本。

## 3. 当前短板

| 方向 | 现状短板 | 影响 |
|------|----------|------|
| 命令体验 | 用户需要记 `attest-plan.ps1`、`set-active-plan.ps1` 等脚本 | 不如原版 `/plan`、`/plan-attest` 直观 |
| 诊断能力 | 没有一条命令解释 hook 为什么不生效 | Windows 下 hook 问题排查成本高 |
| 计划生命周期 | hook 支持 `.planning/<plan-id>`，但初始化和切换体验不完整 | 并行任务和长期任务不够顺手 |
| 外部上下文 | 文档说网页、图片、PDF 要写入 findings，但没有工具辅助 | 这些上下文容易丢，也容易被误信任 |
| 自动记录 | 当前只记录工具、结果、文件路径 | 缺少 add/update/delete、当前阶段、测试状态等信息 |
| 发布治理 | 没有 `VERSION`、`CHANGELOG.md`、一致性测试 | 长期维护时容易文档和实现漂移 |

---

## 4. 目标体验

新增统一命令入口：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
python .codex\skills\planning-with-files\scripts\plan.py init "Hook Security Hardening"
python .codex\skills\planning-with-files\scripts\plan.py status
python .codex\skills\planning-with-files\scripts\plan.py attest
python .codex\skills\planning-with-files\scripts\plan.py switch 2026-05-11-hook-security-hardening
python .codex\skills\planning-with-files\scripts\plan.py capture --kind web --source https://example.com --summary "Key facts..."
```

再提供 PowerShell wrapper：

```powershell
.\.codex\skills\planning-with-files\scripts\plan.ps1 doctor
.\.codex\skills\planning-with-files\scripts\plan.ps1 status
```

---

## 5. 文件职责

| 路径 | 职责 |
|------|------|
| `.codex/hooks/planning_state.py` | hook 共享逻辑：计划解析、attestation、上下文渲染、progress 记录 |
| `.codex/hooks/*.py` | Codex hook 入口，保持薄封装 |
| `.codex/hooks.json` | Codex hook 生命周期注册 |
| `.codex/skills/planning-with-files/scripts/plan.py` | 新增统一命令入口 |
| `.codex/skills/planning-with-files/scripts/plan.ps1` | 新增 PowerShell wrapper |
| `.codex/skills/planning-with-files/scripts/init-session.ps1` | 后续委托给 `plan.py init` |
| `.codex/skills/planning-with-files/scripts/set-active-plan.ps1` | 后续委托给 `plan.py switch/status` |
| `.codex/skills/planning-with-files/scripts/attest-plan.ps1` | 后续委托给 `plan.py attest` |
| `tests/test_hooks.py` | 现有 hook 行为测试 |
| `tests/test_plan_doctor.py` | 新增 doctor 诊断测试 |
| `tests/test_plan_cli.py` | 新增命令入口测试 |
| `tests/test_progress_records.py` | 新增自动记录测试 |
| `tests/test_findings_capture.py` | 新增外部上下文 capture 测试 |
| `tests/test_project_consistency.py` | 新增项目一致性测试 |
| `README.md` | 中文用户文档 |
| `README.en.md` | 英文用户文档 |
| `CHANGELOG.md` | 发布记录 |
| `VERSION` | 当前版本号 |

---

## 6. 里程碑 1：`plan doctor`

**目标：** 一条命令诊断工具是否安装正确、active plan 是否存在、hook 是否可运行、attestation 是否可信。

**优先级：最高。** 这是我们超越原版最容易打出差异的功能。

### Task 1.1：建立 doctor 命令骨架

**文件：**
- 新建：`.codex/skills/planning-with-files/scripts/plan.py`
- 新建：`tests/test_plan_doctor.py`

- [x] **Step 1：写失败测试**

测试健康项目：

```python
def test_doctor_reports_healthy_project(tmp_path):
    root = tmp_path
    plan_dir = root / ".planning" / "2026-05-11-demo"
    plan_dir.mkdir(parents=True)
    (root / ".planning" / ".active_plan").write_text("2026-05-11-demo\n", encoding="utf-8")
    (plan_dir / "task_plan.md").write_text("# Task Plan: Demo\n", encoding="utf-8")
    (plan_dir / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
    (plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")

    result = run_plan(root, "doctor")

    assert result.returncode == 0
    assert "hooks.json: ok" in result.stdout
    assert "active plan: ok" in result.stdout
    assert "planning files: ok" in result.stdout
```

- [x] **Step 2：确认测试失败**

```powershell
python -m unittest tests.test_plan_doctor -v
```

预期：失败，因为 `plan.py` 还不存在。

- [x] **Step 3：实现最小 CLI**

`plan.py` 先支持：

```text
plan.py doctor
plan.py --root <path> doctor
```

输出检查项：

```text
hooks.json: ok
active plan: ok
planning files: ok
```

- [x] **Step 4：运行测试**

```powershell
python -m unittest tests.test_plan_doctor -v
```

预期：doctor 基础测试通过。

### Task 1.2：检查 hook JSON 和 Python runtime

**文件：**
- 修改：`.codex/skills/planning-with-files/scripts/plan.py`
- 修改：`tests/test_plan_doctor.py`

- [x] **Step 1：补失败测试**

测试场景：

- 缺少 `.codex/hooks.json` 时输出 `hooks.json: missing`。
- JSON 无效时输出 `hooks.json: invalid`。
- hook command 指向不存在的 Python 文件时输出具体路径。
- hook command 使用 `python3` 时输出 Windows portability warning。

- [x] **Step 2：实现 hook 检查**

检查这些入口是否存在：

```text
.codex/hooks/session_start.py
.codex/hooks/user_prompt_submit.py
.codex/hooks/pre_tool_use.py
.codex/hooks/post_tool_use.py
.codex/hooks/stop.py
```

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_plan_doctor -v
```

预期：全部通过。

### Task 1.3：检查 attestation 状态

**文件：**
- 修改：`.codex/hooks/planning_state.py`
- 修改：`.codex/skills/planning-with-files/scripts/plan.py`
- 修改：`tests/test_plan_doctor.py`

- [x] **Step 1：补失败测试**

测试场景：

- 没有 attestation：输出 `attestation: not set`。
- hash 匹配：输出 `attestation: ok`。
- hash 不匹配：输出 `attestation: tampered`，并显示 expected/actual 的短 hash。

- [x] **Step 2：在 `planning_state.py` 暴露可复用状态**

新增数据结构：

```python
@dataclass(frozen=True)
class AttestationStatus:
    path: Path | None
    expected: str | None
    actual: str | None
    valid: bool | None
```

hook 和 doctor 共用同一套校验逻辑。

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_plan_doctor tests.test_hooks -v
```

预期：全部通过。

- [ ] **Step 4：提交**

```powershell
git add .codex/hooks/planning_state.py .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_doctor.py tests/test_hooks.py
git commit -m "feat: add plan doctor diagnostics"
```

---

## 7. 里程碑 2：统一命令入口

**目标：** 用 `plan.py` 统一 init/status/switch/attest，旧脚本只做 wrapper。

### Task 2.1：实现 `plan status`

**文件：**
- 修改：`.codex/skills/planning-with-files/scripts/plan.py`
- 新建或修改：`tests/test_plan_cli.py`

- [x] **Step 1：写 status 测试**

输出必须包含：

- active plan id
- plan directory
- current phase
- completed/total phase count
- attestation state

- [x] **Step 2：实现 status**

解析顺序必须和 hook 一致：

1. `PLAN_ID`
2. `.planning/.active_plan`
3. 最新 `.planning/<plan-id>/task_plan.md`
4. legacy 根目录 `task_plan.md`

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_plan_cli -v
```

预期：status 测试通过。

### Task 2.2：实现 `plan init`

**文件：**
- 修改：`.codex/skills/planning-with-files/scripts/plan.py`
- 修改：`.codex/skills/planning-with-files/scripts/init-session.ps1`
- 修改：`.codex/skills/planning-with-files/scripts/init-session.sh`
- 修改：`tests/test_plan_cli.py`

- [x] **Step 1：写 init 测试**

预期行为：

- `plan.py init "Hook Security"` 创建 `.planning/YYYY-MM-DD-hook-security/`。
- 创建 `task_plan.md`、`progress.md`、`findings.md`。
- 写入 `.planning/.active_plan`。
- 默认不覆盖已有计划。
- `--force` 才允许覆盖。
- `--legacy` 创建根目录 planning 文件，兼容旧模式。

- [x] **Step 2：实现 slug 规则**

规则：

- 小写 ASCII。
- 非字母数字替换为 `-`。
- 去掉首尾 `-`。
- 前缀使用本地日期 `YYYY-MM-DD`。

- [x] **Step 3：旧脚本委托给新命令**

`init-session.ps1` 调用：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init <name>
```

shell 脚本调用：

```text
python .codex/skills/planning-with-files/scripts/plan.py init <name>
```

- [x] **Step 4：运行测试**

```powershell
python -m unittest tests.test_plan_cli -v
```

预期：init 测试通过。

### Task 2.3：实现 `plan switch` 和 `plan attest`

**文件：**
- 修改：`.codex/skills/planning-with-files/scripts/plan.py`
- 修改：`.codex/skills/planning-with-files/scripts/set-active-plan.ps1`
- 修改：`.codex/skills/planning-with-files/scripts/attest-plan.ps1`
- 修改：`.codex/skills/planning-with-files/scripts/set-active-plan.sh`
- 修改：`.codex/skills/planning-with-files/scripts/attest-plan.sh`
- 修改：`tests/test_plan_cli.py`

- [x] **Step 1：写 switch 测试**

预期行为：

- `plan.py switch <plan-id>` 写入 `.planning/.active_plan`。
- 切换不存在的 plan 时 exit code 为 `1`。
- `plan.py switch` 不带参数时显示当前 active plan。

- [x] **Step 2：写 attest 测试**

预期行为：

- `plan.py attest` 给 active `.planning/<plan-id>` 写 `.attestation`。
- `plan.py attest --show` 显示 SHA-256。
- `plan.py attest --clear` 删除 attestation。

- [x] **Step 3：实现命令**

复用 hook 的 SHA-256 和 attestation 路径逻辑，避免两套规则漂移。

- [x] **Step 4：运行测试**

```powershell
python -m unittest tests.test_plan_cli tests.test_hooks -v
```

预期：全部通过。

- [x] **Step 5：提交**

```powershell
git add .codex/skills/planning-with-files/scripts tests/test_plan_cli.py tests/test_hooks.py
git commit -m "feat: add unified plan commands"
```

---

## 8. 里程碑 3：外部上下文 inbox

**目标：** 让网页、浏览器、图片、PDF 这类容易丢失且可能不可信的上下文，有统一、安全的记录方式。

### Task 3.1：实现 `plan capture`

**文件：**
- 修改：`.codex/skills/planning-with-files/scripts/plan.py`
- 新建：`tests/test_findings_capture.py`

- [x] **Step 1：写 capture 测试**

预期行为：

- `plan.py capture --kind web --source https://example.com --summary "..."` 追加到 active `findings.md`。
- 支持 kind：`web`、`browser`、`image`、`pdf`、`file`、`note`。
- 记录时间、kind、source、trust、summary。
- 内容用 `---BEGIN EXTERNAL CONTEXT DATA---` / `---END EXTERNAL CONTEXT DATA---` 包起来。

- [x] **Step 2：实现记录格式**

追加格式：

```markdown
## External Context: 2026-05-11 22:45:00

---BEGIN EXTERNAL CONTEXT DATA---
- Kind: web
- Source: https://example.com
- Trust: untrusted
- Summary: Example summary.
---END EXTERNAL CONTEXT DATA---
```

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_findings_capture -v
```

预期：capture 测试通过。

### Task 3.2：findings 注入必须单独 framing

**文件：**
- 修改：`.codex/hooks/planning_state.py`
- 修改：`tests/test_hooks.py`

- [x] **Step 1：写 hook 测试**

预期行为：

- 默认不注入 findings，保持上下文轻量。
- 设置 `PWF_INCLUDE_FINDINGS=1` 时才注入 findings tail。
- findings 使用 `---BEGIN FINDINGS DATA---` / `---END FINDINGS DATA---`。
- header 明确说明 findings 可能包含不可信外部内容。

- [x] **Step 2：实现 opt-in 注入**

只读 `findings.md` 尾部固定行数，例如 20 行。

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_hooks tests.test_findings_capture -v
```

预期：全部通过。

- [x] **Step 4：提交**

```powershell
git add .codex/hooks/planning_state.py .codex/skills/planning-with-files/scripts/plan.py tests/test_hooks.py tests/test_findings_capture.py
git commit -m "feat: add external context capture"
```

---

## 9. 里程碑 4：增强自动客观记录

**目标：** 让 `progress.md` 的 auto record 更有审计价值，但仍然只记录客观事实。

### Task 4.1：记录操作类型

**文件：**
- 修改：`.codex/hooks/planning_state.py`
- 新建：`tests/test_progress_records.py`

- [x] **Step 1：写操作类型测试**

预期映射：

- `*** Add File:` -> `add`
- `*** Update File:` -> `update`
- `*** Delete File:` -> `delete`
- `Edit` -> `edit`
- `Write` -> `write`

- [x] **Step 2：实现 ChangedPath**

新增：

```python
@dataclass(frozen=True)
class ChangedPath:
    path: str
    operation: str
```

渲染为：

```markdown
- Files:
  - `src/example.py` (update)
```

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_progress_records tests.test_hooks -v
```

预期：全部通过。

### Task 4.2：记录 active phase

**文件：**
- 修改：`.codex/hooks/planning_state.py`
- 修改：`tests/test_progress_records.py`

- [x] **Step 1：写 phase 测试**

预期：

- `task_plan.md` 中 `## Current Phase` 后面是 `Phase 3` 时，auto record 包含 `- Phase: Phase 3`。
- 没有 current phase 时不输出 phase 行。

- [x] **Step 2：实现简单解析器**

只从 `task_plan.md` 读取，不从 progress notes 推断。

- [x] **Step 3：运行测试**

```powershell
python -m unittest tests.test_progress_records tests.test_hooks -v
```

预期：全部通过。

- [x] **Step 4：提交**

```powershell
git add .codex/hooks/planning_state.py tests/test_progress_records.py tests/test_hooks.py
git commit -m "feat: enrich objective progress records"
```

---

## 10. 里程碑 5：发布治理

**目标：** 让项目有版本、变更记录和一致性测试，降低长期维护成本。

### Task 5.1：新增版本和 changelog

**文件：**
- 新建：`VERSION`
- 新建：`CHANGELOG.md`
- 修改：`README.md`
- 修改：`README.en.md`

- [x] **Step 1：创建版本文件**

内容：

```text
0.1.0
```

- [x] **Step 2：创建 changelog**

首个版本记录包含：

- Windows-first Python hook runtime。
- 自动客观 progress records。
- delimiter framing。
- opt-in hash attestation。
- bilingual README。

- [x] **Step 3：README 链接 changelog**

中英文 README 都增加简短 Version 小节。

- [x] **Step 4：提交**

```powershell
git add VERSION CHANGELOG.md README.md README.en.md
git commit -m "docs: add release governance"
```

### Task 5.2：新增一致性测试

**文件：**
- 新建：`tests/test_project_consistency.py`

- [ ] **Step 1：写一致性测试**

检查：

- `README.md` 和 `README.en.md` 都提到 `plan doctor`。
- `README.md` 和 `README.en.md` 都提到 attestation。
- `.codex/hooks.json` 引用的 hook 文件都存在。
- `VERSION` 的内容出现在 `CHANGELOG.md`。

- [ ] **Step 2：运行测试**

```powershell
python -m unittest tests.test_project_consistency -v
```

预期：通过。

- [ ] **Step 3：提交**

```powershell
git add tests/test_project_consistency.py
git commit -m "test: add project consistency checks"
```

---

## 11. 里程碑 6：文档包装

**目标：** 让项目更像一个可传播、可安装、可持续使用的工具。

### Task 6.1：新增对比和 30 秒上手

**文件：**
- 修改：`README.md`
- 修改：`README.en.md`

- [ ] **Step 1：新增对比表**

必须说明：

- 原版强在多平台生态。
- Helsincy 版强在 Codex/Windows 可靠性、自动事实记录、诊断能力、统一命令体验。

- [ ] **Step 2：新增 30 秒上手**

命令示例：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
python .codex\skills\planning-with-files\scripts\plan.py init "My Task"
python .codex\skills\planning-with-files\scripts\plan.py status
```

- [ ] **Step 3：运行全量测试**

```powershell
python -m unittest discover -v
```

预期：全部通过。

- [x] **Step 4：提交**

```powershell
git add README.md README.en.md
git commit -m "docs: clarify codex-first positioning"
```

---

## 12. 推荐执行顺序

1. `plan doctor`
2. 统一命令入口：`init/status/switch/attest`
3. 增强自动客观记录
4. 外部上下文 inbox
5. 发布治理
6. 文档包装

如果接下来会大量做网页、PDF、图片研究，可以把“外部上下文 inbox”提前到第 3 位。

## 13. 每次提交前验证

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -v
git diff --check
git status --short --branch --ignored
```

## 14. 每次 push 前验证

```powershell
git log --oneline --decorate --max-count=5
git push
git status --short --branch --ignored
```

## 15. 完成标准

这份路线完成时，应满足：

- `plan.py doctor` 能解释 install、active plan、hook、session、attestation 状态。
- `plan.py init/status/switch/attest/capture` 在 Windows 上不依赖 `sh`。
- 旧 PowerShell 和 shell 脚本委托给统一命令层。
- auto progress record 包含操作类型和 active phase。
- 外部上下文以不可信结构化数据写入 `findings.md`。
- README 明确说明 Codex-first 价值和命令入口。
- 有 `CHANGELOG.md`、`VERSION` 和一致性测试。
- clean checkout 后全量测试通过。
