# Progress Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 每个完成的任务单独提交。

**Goal:** 为 Helsincy Plan With Files 增加 `progress.md` 生命周期管理，让长期任务既保留 hook 生成的客观事实，又避免热日志无限增长和占用上下文。

**Architecture:** 保持 hook 自动记录为客观事实，不让 hook 做语义总结或默认删除内容。新增手动 `compact` 命令，把旧的 auto records 归档到 `progress.archive.md`，在 `progress.md` 中维护一段 deterministic compact summary，并只保留最近 N 条热记录。Hook 继续只注入 bounded context，同时可以注入 compact summary 和给出阈值提醒。

**Tech Stack:** Python standard library, Codex hooks, Markdown files, unittest, PowerShell verification commands.

---

## 1. 背景和原版基线

截至 2026-05-12，原版 `OthmanAdi/planning-with-files` 对 `progress.md` 的上下文注入已经做了截断，但没有提供 `progress.md` 文件本身的归档或压缩机制。

原版 Codex `UserPromptSubmit` hook 的关键行为：

```sh
head -50 "$PLAN_FILE"
tail -20 "$PROGRESS_FILE" 2>/dev/null
```

原版 canonical skill 的内联 hook 也使用：

```sh
head -50 task_plan.md
tail -20 progress.md 2>/dev/null
```

原版 changelog 中提到的 session-catchup 截断是另一件事：它限制恢复会话输出，例如 `head -100`，不是清理 `progress.md`。

参考：

- Upstream Codex hook: `https://raw.githubusercontent.com/OthmanAdi/planning-with-files/master/.codex/hooks/user-prompt-submit.sh`
- Upstream Codex skill: `https://raw.githubusercontent.com/OthmanAdi/planning-with-files/master/.codex/skills/planning-with-files/SKILL.md`
- Upstream changelog: `https://raw.githubusercontent.com/OthmanAdi/planning-with-files/master/CHANGELOG.md`

我们当前版本在原版基础上扩大了最近进度注入窗口：

- `.codex/hooks/planning_state.py` 的 `read_tail(paths.progress, 80)`
- `.codex/hooks/user_prompt_submit.py` 通过 `render_prompt_context()` 注入 bounded progress
- `.codex/hooks/session_start.py` 复用同一套 prompt context

这样比原版 `tail -20` 更适合本项目的客观 hook records；每条 auto record 通常有多行，80 行大约能覆盖最近 10 到 15 条普通记录。因此本方案要解决的不是“当前 hook 全量注入 progress”，而是“长期使用后 `progress.md` 文件无限增长，维护和恢复成本变高”。

## 2. 设计原则

- 客观事实不丢：hook 生成的 auto records 必须可追溯，旧记录进入 `progress.archive.md`，不直接丢弃。
- 热日志要短：`progress.md` 默认只保留最近 `30` 条 auto records，供 agent 快速恢复当前状态。
- 自动总结要克制：compact summary 只统计客观字段，例如记录数量、时间范围、工具计数、文件计数，不生成语义判断。
- Agent 总结要分层：agent 可以把解释性结论写入 `findings.md` 或 `task_plan.md`，但不能把它冒充为 hook 客观事实。
- 手动触发优先：第一版 compact 由 `/pwf-compact` 或 `plan.py compact` 手动触发。Hook 只提醒，不自动重写 `progress.md`。
- 兼容现有文件：legacy 根目录 `progress.md` 和 `.planning/<plan-id>/progress.md` 都要支持。
- 不破坏安全边界：delimiter framing、hash attestation 和 auto record schema 保持稳定。Compact 不修改 `task_plan.md`，不影响 `.attestation`。
- 可回滚：归档文件 append-only，compact 前后可以通过 git diff 检查。

## 3. 文件范围

| 文件 | 责任 |
|------|------|
| `.codex/skills/planning-with-files/scripts/progress_lifecycle.py` | 新增共享 progress parser、统计、summary、compact 实现 |
| `.codex/skills/planning-with-files/scripts/plan.py` | 新增 `compact` 子命令；`status` 和 `doctor` 展示 compact 建议 |
| `.codex/hooks/planning_state.py` | 注入 compact summary；提供 progress record 计数或提醒辅助 |
| `.codex/hooks/post_tool_use.py` | 在达到阈值时把 compact 建议加入 system message |
| `.codex/skills/pwf-compact/SKILL.md` | 新增 `/pwf-compact` user-invocable skill wrapper |
| `.codex/skills/planning-with-files/SKILL.md` | 说明 progress 生命周期、archive 和 compact 命令 |
| `README.md` | 中文文档加入 `/pwf-compact`、长期日志管理说明 |
| `README.en.md` | 英文文档同步说明 |
| `CHANGELOG.md` | 实现后记录新功能 |
| `tests/test_progress_compaction.py` | 新增 compact parser、CLI、归档行为测试 |
| `tests/test_hooks.py` | 验证 prompt context 注入 compact summary 和阈值提醒 |
| `tests/test_pwf_commands.py` | 验证 `/pwf-compact` skill wrapper |
| `tests/test_project_consistency.py` | 验证 README 和版本文档一致性，如需要 |

## 4. 数据格式

### 4.1 Auto Record 边界

当前 hook auto record 格式保持不变：

```markdown
### Auto Record: 2026-05-12 21:13:11
- Tool: apply_patch
- Result: success
- Phase: Phase 4
- Files:
  - `D:\DEV\Plan_Skill\VERSION` (update)
  - `D:\DEV\Plan_Skill\README.md` (update)
```

解析规则：

- auto record 从 `^### Auto Record: ` 开始。
- 后续空行、`- ` 列表项、`  - ` 嵌套列表项属于该 record。
- 遇到下一个 markdown heading、普通段落或文件结束时 record 结束。
- 非 auto record 内容视为手写或 agent-written notes，compact 默认保留在 `progress.md` 原位。

这样可以只归档 hook 生成的客观记录，避免误删人工笔记。

### 4.2 Managed Summary

`progress.md` 中由 compact 维护一个稳定 summary 区块：

```markdown
<!-- PWF_COMPACT_SUMMARY_START -->
## Compacted Progress Summary

- Last Compact: 2026-05-12 22:10:00
- Archive: progress.archive.md
- Archived Auto Records: 72
- Archived Range: 2026-05-10 09:14:20 to 2026-05-12 20:58:46
- Kept Recent Auto Records: 30
- Tools: apply_patch=41, Write=18, Edit=13
- Unique Files: 26
- Note: Archived records are objective hook facts. Agent summaries remain interpretive and should be verified when accuracy matters.
<!-- PWF_COMPACT_SUMMARY_END -->
```

规则：

- 每次 compact 替换这段 managed summary，不重复追加。
- 所有字段来自 auto records 的可解析事实。
- `Unique Files` 只统计 auto records 中的 file list，不读磁盘、不推断语义。
- 如果没有可归档 record，不写 summary。

### 4.3 Archive Format

旧 auto records 追加到 active plan 目录的 `progress.archive.md`：

```markdown
# Progress Archive

## Compact Batch: 2026-05-12 22:10:00
- Source: progress.md
- Archived Auto Records: 72
- Archived Range: 2026-05-10 09:14:20 to 2026-05-12 20:58:46
- Kept Recent Auto Records: 30
- Tools: apply_patch=41, Write=18, Edit=13
- Unique Files: 26

---BEGIN ARCHIVED AUTO RECORDS---
### Auto Record: 2026-05-10 09:14:20
- Tool: apply_patch
- Files:
  - `src/example.py` (update)
---END ARCHIVED AUTO RECORDS---
```

规则：

- archive append-only。
- 每个 compact batch 独立保存 summary 和 archived records。
- archive block 使用 delimiter，便于将来做恢复、审计和安全提示。

## 5. CLI 设计

新增命令：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
python .codex\skills\planning-with-files\scripts\plan.py compact --keep-records 50
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
```

参数：

| 参数 | 默认值 | 作用 |
|------|--------|------|
| `--keep-records N` | `30` | compact 后保留最近 N 条 auto records |
| `--dry-run` | false | 只输出计划，不修改文件 |
| `--archive PATH` | `progress.archive.md` | 指定 archive 文件名或路径 |

成功输出示例：

```text
compacted progress.md
archived auto records: 72
kept recent auto records: 30
archive: .planning/2026-05-12-demo/progress.archive.md
```

Dry-run 输出示例：

```text
progress compaction dry run
would archive auto records: 72
would keep recent auto records: 30
archive: .planning/2026-05-12-demo/progress.archive.md
```

无需 compact 时输出：

```text
progress compaction not needed
auto records: 18
keep records: 30
```

错误输出：

```text
No active plan found. Create or switch to a plan before compacting progress.
```

## 6. Hook 和上下文注入设计

### 6.1 UserPromptSubmit / SessionStart

当前 prompt context 是：

```text
PLAN head 50
recent progress tail 80
optional findings tail 20
```

实现 compact 后改为：

```text
PLAN head 50
optional compacted progress summary
recent progress tail 80
optional findings tail 20
```

新的 summary 也使用 data block：

```text
=== compacted progress summary ===
---BEGIN PROGRESS SUMMARY DATA---
...
---END PROGRESS SUMMARY DATA---
```

这样 agent 在只看到最近 80 行时，也能知道旧记录已经归档，以及归档的大致范围。后续可以把 `tail 80` 进一步升级为“最近 N 条 auto records + 最大字符数保护”，让注入窗口按记录数量而不是纯行数工作。

### 6.2 PostToolUse Reminder

第一版不让 hook 自动 compact。Hook 只在阈值点提醒：

```text
[planning-with-files] progress.md has 100 auto records. Consider running /pwf-compact to archive old objective records.
```

默认阈值：

```text
PWF_COMPACT_THRESHOLD=100
PWF_COMPACT_KEEP_RECORDS=30
```

提醒规则：

- `PWF_COMPACT_THRESHOLD` 未设置时使用 `100`。
- 当前 auto record 数量刚好是阈值整数倍时提醒，例如 `100`、`200`。
- 阈值小于 `1` 或非法时回退到 `100`。
- 提醒只出现在 `PostToolUse` 的 system message 中，不写入 `progress.md`。

### 6.3 Doctor / Status

`plan.py status` 增加一行：

```text
progress: 126 auto records, compact recommended
```

`plan.py doctor` 在超过阈值时增加 warning：

```text
[warn] progress.md has 126 auto records; run /pwf-compact or plan.py compact
```

## 7. Slash Command 设计

新增 project-local skill wrapper：

```text
.codex/skills/pwf-compact/SKILL.md
```

内容结构：

````markdown
---
name: pwf-compact
description: Archive old progress.md auto records and keep recent progress small. Invoke with /pwf-compact.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-compact

Archive old objective auto records from `progress.md` into `progress.archive.md`, then keep only recent hot records in `progress.md`.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
```

If the user asks for a custom keep count, pass `--keep-records <N>`.
If the user asks to preview only, pass `--dry-run`.

After it completes, summarize archived count, kept count, and archive path.
````

README command table 增加：

| 命令 | 作用 | 等价 CLI |
|------|------|----------|
| `/pwf-compact` | 归档旧 auto records 并缩短 `progress.md` | `plan.py compact` |

## 8. 任务拆分

### Task 1: Progress Parser 和 Compact Core

**Files:**
- Create: `.codex/skills/planning-with-files/scripts/progress_lifecycle.py`
- Test: `tests/test_progress_compaction.py`

- [ ] **Step 1: 写失败测试**

新增 `tests/test_progress_compaction.py`，覆盖 auto record 解析、手写笔记保留、dry-run 不改文件。

核心测试结构：

```python
import tempfile
from pathlib import Path
import unittest

from importlib.machinery import SourceFileLoader

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = SourceFileLoader(
    "progress_lifecycle",
    str(REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "progress_lifecycle.py"),
).load_module()


class ProgressCompactionTests(unittest.TestCase):
    def test_compact_archives_old_auto_records_and_keeps_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            records = []
            for index in range(5):
                records.append(
                    "\n".join(
                        [
                            f"### Auto Record: 2026-05-12 10:0{index}:00",
                            "- Tool: apply_patch",
                            "- Files:",
                            f"  - `src/file_{index}.py` (update)",
                            "",
                        ]
                    )
                )
            progress.write_text("# Progress Log\n\nManual note stays.\n\n" + "\n".join(records), encoding="utf-8")

            result = MODULE.compact_progress(progress, archive, keep_records=2, dry_run=False, now="2026-05-12 22:10:00")

            self.assertEqual(result.archived_count, 3)
            self.assertEqual(result.kept_count, 2)
            updated = progress.read_text(encoding="utf-8")
            archived = archive.read_text(encoding="utf-8")
            self.assertIn("Manual note stays.", updated)
            self.assertIn("PWF_COMPACT_SUMMARY_START", updated)
            self.assertNotIn("src/file_0.py", updated)
            self.assertIn("src/file_3.py", updated)
            self.assertIn("src/file_0.py", archived)
            self.assertIn("---BEGIN ARCHIVED AUTO RECORDS---", archived)

    def test_compact_dry_run_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "progress.md"
            archive = root / "progress.archive.md"
            original = "\n".join(
                [
                    "# Progress Log",
                    "",
                    "### Auto Record: 2026-05-12 10:00:00",
                    "- Tool: Write",
                    "- Files:",
                    "  - `a.md` (write)",
                    "",
                    "### Auto Record: 2026-05-12 10:01:00",
                    "- Tool: Edit",
                    "- Files:",
                    "  - `b.md` (edit)",
                    "",
                ]
            )
            progress.write_text(original, encoding="utf-8")

            result = MODULE.compact_progress(progress, archive, keep_records=1, dry_run=True, now="2026-05-12 22:10:00")

            self.assertEqual(result.archived_count, 1)
            self.assertEqual(progress.read_text(encoding="utf-8"), original)
            self.assertFalse(archive.exists())
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m unittest tests.test_progress_compaction -v
```

Expected: FAIL because `progress_lifecycle.py` does not exist.

- [ ] **Step 3: 实现 core module**

实现公开函数和数据结构：

```python
@dataclass(frozen=True)
class CompactResult:
    archived_count: int
    kept_count: int
    total_auto_records: int
    archive_path: Path
    changed: bool
    dry_run: bool
    summary: str


def count_auto_records(progress_path: Path) -> int:
    ...


def extract_compaction_summary(progress_path: Path, line_limit: int = 20) -> str:
    ...


def compact_progress(
    progress_path: Path,
    archive_path: Path,
    keep_records: int = 30,
    dry_run: bool = False,
    now: str | None = None,
) -> CompactResult:
    ...
```

Implementation constraints:

- Use only Python standard library.
- Preserve newline style as `\n`.
- Treat missing `progress.md` as zero records and no change.
- Reject `keep_records < 1` with `ValueError`.
- Archive only auto record blocks.
- Preserve non-auto content in `progress.md`.
- Replace old managed summary if present.

- [ ] **Step 4: 运行 core 测试确认通过**

```powershell
python -m unittest tests.test_progress_compaction -v
```

Expected: OK.

- [ ] **Step 5: 提交**

```powershell
git add .codex/skills/planning-with-files/scripts/progress_lifecycle.py tests/test_progress_compaction.py
git commit -m "feat: add progress compaction core"
```

### Task 2: CLI Compact, Status 和 Doctor 集成

**Files:**
- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Modify: `tests/test_plan_cli.py`
- Modify: `tests/test_plan_doctor.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_plan_cli.py` 中增加：

```python
def test_compact_archives_old_progress_records(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_dir = write_active_plan(root)
        records = []
        for index in range(4):
            records.append(
                "\n".join(
                    [
                        f"### Auto Record: 2026-05-12 10:0{index}:00",
                        "- Tool: apply_patch",
                        "- Files:",
                        f"  - `src/file_{index}.py` (update)",
                        "",
                    ]
                )
            )
        (plan_dir / "progress.md").write_text("# Progress Log\n\n" + "\n".join(records), encoding="utf-8")

        result = run_plan(root, "compact", "--keep-records", "2")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("archived auto records: 2", result.stdout)
        self.assertTrue((plan_dir / "progress.archive.md").is_file())
        progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
        self.assertNotIn("src/file_0.py", progress)
        self.assertIn("src/file_2.py", progress)
```

在 `tests/test_plan_cli.py` 中增加 dry-run：

```python
def test_compact_dry_run_leaves_progress_unchanged(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_dir = write_active_plan(root)
        original = "\n".join(
            [
                "# Progress Log",
                "",
                "### Auto Record: 2026-05-12 10:00:00",
                "- Tool: Write",
                "- Files:",
                "  - `a.md` (write)",
                "",
                "### Auto Record: 2026-05-12 10:01:00",
                "- Tool: Edit",
                "- Files:",
                "  - `b.md` (edit)",
                "",
            ]
        )
        (plan_dir / "progress.md").write_text(original, encoding="utf-8")

        result = run_plan(root, "compact", "--keep-records", "1", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("progress compaction dry run", result.stdout)
        self.assertEqual((plan_dir / "progress.md").read_text(encoding="utf-8"), original)
        self.assertFalse((plan_dir / "progress.archive.md").exists())
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m unittest tests.test_plan_cli tests.test_plan_doctor -v
```

Expected: FAIL because `compact` subcommand does not exist.

- [ ] **Step 3: 实现 CLI**

在 `plan.py` 中：

- Import `progress_lifecycle`.
- Add `compact(root, keep_records, dry_run, archive)` function.
- Add parser:

```python
compact_parser = subparsers.add_parser("compact", help="Archive old progress.md auto records")
compact_parser.add_argument("--keep-records", type=int, default=30)
compact_parser.add_argument("--dry-run", action="store_true")
compact_parser.add_argument("--archive", default="progress.archive.md")
```

Routing:

```python
if args.command == "compact":
    return compact(root, keep_records=args.keep_records, dry_run=args.dry_run, archive=args.archive)
```

`status` 增加 progress 行：

```text
progress: 126 auto records, compact recommended
```

`doctor` 超过阈值时 warning：

```text
[warn] progress.md has 126 auto records; run /pwf-compact or plan.py compact
```

- [ ] **Step 4: 运行 CLI 测试确认通过**

```powershell
python -m unittest tests.test_plan_cli tests.test_plan_doctor -v
```

Expected: OK.

- [ ] **Step 5: 提交**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_cli.py tests/test_plan_doctor.py
git commit -m "feat: add progress compact cli"
```

### Task 3: Hook Summary 注入和阈值提醒

**Files:**
- Modify: `.codex/hooks/planning_state.py`
- Modify: `.codex/hooks/post_tool_use.py`
- Modify: `tests/test_hooks.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_hooks.py` 中增加 summary 注入测试：

```python
def test_user_prompt_submit_includes_compacted_progress_summary(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_plan(root)
        (root / "progress.md").write_text(
            "\n".join(
                [
                    "# Progress Log",
                    "",
                    "<!-- PWF_COMPACT_SUMMARY_START -->",
                    "## Compacted Progress Summary",
                    "",
                    "- Archived Auto Records: 72",
                    "- Unique Files: 26",
                    "<!-- PWF_COMPACT_SUMMARY_END -->",
                    "",
                    "### Auto Record: 2026-05-12 22:00:00",
                    "- Tool: Edit",
                    "- Files:",
                    "  - `src/current.py` (edit)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = run_hook("user_prompt_submit.py", root, {"hook_event_name": "UserPromptSubmit"})

        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("---BEGIN PROGRESS SUMMARY DATA---", context)
        self.assertIn("- Archived Auto Records: 72", context)
        self.assertIn("---END PROGRESS SUMMARY DATA---", context)
        self.assertIn("src/current.py", context)
```

增加 PostToolUse threshold 测试：

```python
def test_post_tool_use_warns_when_progress_hits_compact_threshold(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_plan(root)
        existing = []
        for index in range(99):
            existing.append(
                "\n".join(
                    [
                        f"### Auto Record: 2026-05-12 10:{index:02d}:00",
                        "- Tool: Write",
                        "- Files:",
                        f"  - `src/{index}.md` (write)",
                        "",
                    ]
                )
            )
        (root / "progress.md").write_text("# Progress Log\n\n" + "\n".join(existing), encoding="utf-8")

        result = run_hook(
            "post_tool_use.py",
            root,
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "src/current.md"},
                "tool_response": {"success": True},
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        message = json.loads(result.stdout)["systemMessage"]
        self.assertIn("Recorded PostToolUse context", message)
        self.assertIn("Consider running /pwf-compact", message)
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m unittest tests.test_hooks -v
```

Expected: FAIL because summary block and compact reminder are not implemented.

- [ ] **Step 3: 实现 hook integration**

`planning_state.py`:

- Import shared `progress_lifecycle`.
- Add helper `progress_summary_block(paths.progress)`.
- In `render_prompt_context()`, insert compacted summary before recent progress if summary exists.
- Add `progress_compaction_notice(paths.progress)` returning empty string or one-sentence reminder.

`post_tool_use.py`:

Current system message:

```python
"[planning-with-files] Recorded PostToolUse context in progress.md. "
"If a phase is now complete, update task_plan.md status."
```

New behavior:

```python
notice = planning_state.progress_compaction_notice(root)
message = (
    "[planning-with-files] Recorded PostToolUse context in progress.md. "
    "If a phase is now complete, update task_plan.md status."
)
if notice:
    message += " " + notice
```

- [ ] **Step 4: 运行 hook 测试确认通过**

```powershell
python -m unittest tests.test_hooks -v
```

Expected: OK.

- [ ] **Step 5: 提交**

```powershell
git add .codex/hooks/planning_state.py .codex/hooks/post_tool_use.py tests/test_hooks.py
git commit -m "feat: surface progress compaction context"
```

### Task 4: `/pwf-compact` Slash Command

**Files:**
- Create: `.codex/skills/pwf-compact/SKILL.md`
- Modify: `tests/test_pwf_commands.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_pwf_commands.py` 中把 `pwf-compact` 加入 expected command list，并断言 skill wrapper 调用 `plan.py compact`。

Expected assertions:

```python
self.assertTrue((REPO_ROOT / ".codex" / "skills" / "pwf-compact" / "SKILL.md").is_file())
self.assertIn("user-invocable: true", skill_text)
self.assertIn("plan.py compact", skill_text)
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m unittest tests.test_pwf_commands -v
```

Expected: FAIL because `pwf-compact` does not exist.

- [ ] **Step 3: 新增 skill wrapper**

Create `.codex/skills/pwf-compact/SKILL.md` using the structure in section 7.

- [ ] **Step 4: 运行测试确认通过**

```powershell
python -m unittest tests.test_pwf_commands -v
```

Expected: OK.

- [ ] **Step 5: 提交**

```powershell
git add .codex/skills/pwf-compact/SKILL.md tests/test_pwf_commands.py
git commit -m "feat: add pwf compact command"
```

### Task 5: 文档和版本说明

**Files:**
- Modify: `.codex/skills/planning-with-files/SKILL.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 更新 skill 文档**

在 `SKILL.md` 的 `Objective Records vs Agent Notes` 后增加：

````markdown
## Progress Lifecycle

`progress.md` is the hot log. It should stay small enough for recent context.
When auto records grow large, run `/pwf-compact` or:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
```

The command archives old objective auto records to `progress.archive.md`, keeps recent records in `progress.md`, and writes a deterministic compact summary. The summary is factual only: counts, time ranges, tools, and file paths. Agent-written summaries remain interpretive and should be verified when accuracy matters.
````

- [ ] **Step 2: 更新 README 命令表和使用说明**

中文 README 增加：

```markdown
| `/pwf-compact` | 归档旧 auto records 并缩短 `progress.md` | `plan.py compact` |
```

英文 README 增加：

```markdown
| `/pwf-compact` | Archive old auto records and keep `progress.md` small | `plan.py compact` |
```

长期日志说明：

```markdown
`progress.md` 是热日志，不是永久审计文件。长期任务中可以运行 `/pwf-compact`，把旧的客观 auto records 归档到 `progress.archive.md`，并在 `progress.md` 保留 compact summary 和最近记录。
```

- [ ] **Step 3: 更新 CHANGELOG**

在 `Unreleased` 或下一版本条目中增加：

```markdown
- Added `plan.py compact` and `/pwf-compact` to archive old objective auto records from `progress.md`.
- Added compacted progress summary injection so long-running tasks keep bounded context without losing audit history.
```

- [ ] **Step 4: 运行文档相关测试**

```powershell
python -m unittest tests.test_project_consistency tests.test_pwf_commands -v
```

Expected: OK.

- [ ] **Step 5: 提交**

```powershell
git add .codex/skills/planning-with-files/SKILL.md README.md README.en.md CHANGELOG.md
git commit -m "docs: document progress compaction"
```

### Task 6: Full Verification

**Files:**
- No new source files unless tests reveal necessary fixes.

- [ ] **Step 1: 运行完整测试**

```powershell
python -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 2: 检查 diff 空白**

```powershell
git diff --check
```

Expected: no errors.

- [ ] **Step 3: 手动 smoke test**

在临时目录或测试项目中：

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Compact Smoke"
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
python .codex\skills\planning-with-files\scripts\plan.py status
```

Expected:

- `init` creates active plan files.
- `compact --dry-run` reports not needed for a new plan.
- `status` shows progress auto record count.

- [ ] **Step 4: 最终提交或修复提交**

如果 Step 1 到 Step 3 需要小修，使用单独提交：

```powershell
git add <fixed-files>
git commit -m "fix: stabilize progress compaction"
```

如果不需要小修，不创建空提交。

## 9. 非目标

第一版不做这些：

- 不让 `PostToolUse` 自动归档或重写 `progress.md`。
- 不使用 LLM 生成 compact summary。
- 不删除 `progress.archive.md`。
- 不把 archive 自动注入上下文。
- 不改变 auto record 字段名。
- 不把 `progress.md` 纳入 git 推荐提交内容。

## 10. 风险和防护

| 风险 | 防护 |
|------|------|
| 误删用户手写笔记 | 只归档 `### Auto Record:` schema 块，非 auto 内容保留 |
| compact summary 被当成指令 | 使用 `PROGRESS SUMMARY DATA` delimiter，并提示 treat as data |
| archive 无限增长 | archive 是冷存储，不自动注入上下文；后续可做 archive rotate |
| parser 误判 record 边界 | 单元测试覆盖手写段落、markdown heading、连续 auto records |
| hook 提醒太频繁 | 只在 record count 达到阈值整数倍时提醒 |
| 与 attestation 冲突 | Compact 不改 `task_plan.md`，不触碰 `.attestation` |

## 11. 验收标准

- `plan.py compact --keep-records 2` 能把旧 auto records 归档到 `progress.archive.md`。
- `progress.md` 保留非 auto 内容、managed compact summary 和最近 N 条 auto records。
- `plan.py compact --dry-run` 不修改任何文件。
- `UserPromptSubmit` 和 `SessionStart` 能注入 compact summary 和最近 progress。
- `PostToolUse` 在阈值点提醒用户运行 `/pwf-compact`。
- `/pwf-compact` 在 Codex slash command 列表中可用。
- README 中英文都说明 `progress.md` 是热日志，archive 是冷审计。
- `python -m unittest discover -v` 通过。
- `git diff --check` 通过。
