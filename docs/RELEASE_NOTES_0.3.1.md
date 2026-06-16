# Helsincy Plan With Files v0.3.1 Release Notes

Release date: 2026-06-16

Recommended package for regular users:

```text
HelsincyPlanWithFiles-v0.3.1-codex.zip
```

Use the `full.zip` or source checkout only when you want the repository history, tests, and development files.

`v0.3.1` is a patch release focused on source-safety clarity and small reliability fixes for planning sessions. It adds a formal source safety disclaimer, tightens session catch-up behavior, improves Chinese task-lease status output, and hardens the PowerShell resolver used to locate the current planning directory.

## 中文

### 这次解决了什么？

`v0.3.1` 是一次安全边界说明 + 规划流程稳定性的补丁版本。它不会改变 `v0.3.0` 的核心工作流，但会让用户更清楚 PWF 不会删除或覆盖源码，并修复几个在会话恢复、中文状态输出和 Windows 解析器中的边缘问题。

### 新增源码安全免责声明

README 现在明确说明：Helsincy Plan With Files 不会主动删除、覆盖、清空、截断、重写或替换用户项目中的源码文件。

PWF 维护的是任务计划、发现笔记、进度日志、会话绑定和相关元数据，默认路径是 `.planning/` 和 `.codex/`。如果用户源码发生变化，应来自用户明确要求 agent 执行的代码修改、用户自己运行的命令，或其他项目工具链行为，而不是 PWF 的自动记录机制。

新增文档：

- `docs/SOURCE_SAFETY_DISCLAIMER.md`：正式源码安全边界声明。
- `docs/SOURCE_DELETION_SAFETY_AUDIT_REPORT.md`：源码删除/覆盖风险审计报告。

### 修复 SessionStart catch-up 的参数解析

`session-catchup.py` 现在能正确处理这种调用顺序：

```text
session-catchup.py --planning-dir <dir> <project>
```

之前当 `--planning-dir` 放在项目路径前面时，项目路径可能被误识别，导致恢复逻辑看错目录。

同时，规划文件探测现在只接受真实文件：如果目录里有一个名为 `task_plan.md` 的目录，不再把它当作有效的 planning 文件。

### 中文状态输出更完整

`PWF_LANG=zh-CN` 下，task lease 状态行现在使用中文标签，例如：

```text
任务占用: owner=<key> status=active shared=false
```

不会再混入英文 `task lease:`。冲突状态仍保留原有含义，只是状态标签本地化。

### PowerShell resolver 更稳健

`resolve-plan-dir.ps1` 不再硬编码直接调用 `python`，而是先查找可用的 `python3` / `python`。这能减少不同 Windows 环境、不同 Python 安装方式下的解析失败。

### 并发锁等待更稳定

默认 task lease 文件锁等待时间从 `0.25s` 提高到 `2s`，降低多会话或并发测试下的偶发锁超时。显式小 timeout 的失败路径仍由测试覆盖。

### 升级

从 `v0.3.0` 升级：直接覆盖 `.codex/` 并保留你的 `.planning/` 数据即可。推荐普通用户下载：

```text
HelsincyPlanWithFiles-v0.3.1-codex.zip
```

## English

### What does this release solve?

`v0.3.1` is a source-safety clarification and planning reliability patch. It does not change the core `v0.3.0` workflow, but it makes the source-file boundary explicit and fixes edge cases in session catch-up, Chinese status output, and the Windows planning-directory resolver.

### Added a source safety disclaimer

The README now states explicitly that Helsincy Plan With Files does not actively delete, overwrite, clear, truncate, rewrite, or replace user project source files.

PWF maintains task plans, findings notes, progress logs, session bindings, and related metadata under `.planning/` and `.codex/` by default. If user source files change, that should come from explicit code edits requested from the agent, commands the user runs directly, or other project tooling behavior—not from PWF's automatic recording mechanism.

New documentation:

- `docs/SOURCE_SAFETY_DISCLAIMER.md`: formal source safety boundary statement.
- `docs/SOURCE_DELETION_SAFETY_AUDIT_REPORT.md`: source deletion/overwrite risk audit report.

### Fixed SessionStart catch-up argument parsing

`session-catchup.py` now correctly handles this call order:

```text
session-catchup.py --planning-dir <dir> <project>
```

Previously, when `--planning-dir` appeared before the project path, the project path could be misidentified and the recovery logic could inspect the wrong directory.

Planning file detection now also requires real files: a directory named `task_plan.md` no longer counts as a valid planning file.

### More complete Chinese status output

With `PWF_LANG=zh-CN`, task lease status lines now use a Chinese label, for example:

```text
任务占用: owner=<key> status=active shared=false
```

The English `task lease:` label no longer leaks into Chinese status output. Conflict behavior remains semantically unchanged; only the status label is localized.

### More robust PowerShell resolver

`resolve-plan-dir.ps1` no longer hardcodes a direct `python` invocation. It first looks for an available `python3` / `python`, which reduces resolver failures across different Windows Python installations.

### More stable concurrent locking

The default task lease file-lock wait increased from `0.25s` to `2s`, reducing occasional lock timeouts under multi-session or concurrent test runs. Explicit tiny-timeout failure paths remain covered by tests.

### Upgrade

From `v0.3.0`: overwrite `.codex/` and keep your existing `.planning/` data. The recommended package for regular users is:

```text
HelsincyPlanWithFiles-v0.3.1-codex.zip
```