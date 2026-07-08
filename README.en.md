# Helsincy Plan With Files

[简体中文](README.md) | [English](README.en.md)

[![Codex CLI](https://img.shields.io/badge/Codex_CLI-supported-00A67E)](README.en.md)
[![Codex App](https://img.shields.io/badge/Codex_App-supported-00A67E)](README.en.md)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4)](README.en.md)
[![License](https://img.shields.io/github/license/TheLostRiver/HelsincyPlanWithFiles?label=license)](LICENSE)
[![PRs](https://img.shields.io/github/issues-pr/TheLostRiver/HelsincyPlanWithFiles?label=PRs)](https://github.com/TheLostRiver/HelsincyPlanWithFiles/pulls)
[![Version](https://img.shields.io/github/v/release/TheLostRiver/HelsincyPlanWithFiles?label=version)](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/TheLostRiver/HelsincyPlanWithFiles/total?label=downloads)](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest)

Helsincy Plan With Files gives Codex a project-local task notebook.

When a Codex task gets long, the chat can lose early context, a later session may not remember where the work stopped, and multiple Codex conversations in the same project can accidentally mix their progress. This tool stores the task plan, useful findings, and progress log in project files so Codex can recover the work state instead of relying only on the current chat window.

For a short one-off question, you probably do not need it. For multi-step work, multi-file edits, session recovery, or several Codex conversations in the same project, it helps keep the work organized and safer.

A plain-language user guide is currently available in Chinese: [普通用户使用指南](docs/USER_GUIDE.zh-CN.md).

> [!IMPORTANT]
> **Source Safety Statement**
>
> The current project code does not contain any operation logic that deletes or overwrites user source files. Helsincy Plan With Files only maintains its own task plans, findings notes, progress logs, session bindings, and related metadata; these records are kept under `.planning/` and `.codex/`-related paths by default.
>
> If project source files change, that should come from explicit code edits requested from the agent, commands the user runs directly, or other project tooling behavior—not from the automatic recording mechanism in Helsincy Plan With Files. See [Source Safety Disclaimer](docs/SOURCE_SAFETY_DISCLAIMER.md) for the formal boundary statement and [Source Deletion Safety Audit Report](docs/SOURCE_DELETION_SAFETY_AUDIT_REPORT.md) for the related safety audit.

## What Is This?

This is a Codex helper installed inside a project. After installation, the project gets `/pwf-*` commands and a `.planning/` folder. Codex stores what the task is, what it has learned, and what it has already done:

```text
.planning/<plan-id>/task_plan.md
.planning/<plan-id>/findings.md
.planning/<plan-id>/progress.md
```

- `task_plan.md`: the task checklist, goal, phases, and completion state.
- `findings.md`: notes for discoveries, test conclusions, errors, decisions, and external context summaries.
- `progress.md`: the objective progress log maintained by hooks, including write/edit auto records and changed files.

For daily use, the first commands to remember are `/pwf-doctor` to check installation, `/pwf-init` to start a task, and `/pwf-status` to see the current state.

## What Problem Does It Solve?

Codex can execute complex work, but long tasks have a few recurring failure modes:

- After context compaction, early decisions, completed phases, and remaining work can disappear.
- After a session interruption or recovery, the agent often has to reread a large amount of context.
- Files may have changed, but there is no stable objective record of which files were touched.
- Research notes, test results, and temporary judgments get scattered across chat history.

Helsincy Plan With Files moves this fragile state into project files, turning task memory from chat-only context into durable local work records.

## Why Use It?

This tool is useful for Codex workflows that need multiple rounds, session recovery, or stronger traceability, such as:

- Debugging complex issues while preserving investigation notes and decisions.
- Implementing features in phases with a clear current phase, completed work, and next steps.
- Editing multiple files while automatically recording the actual file changes.
- Continuing work after context compaction, session recovery, or task switching.

The value is not simply creating a few `.md` files. The value is giving Codex a recoverable, traceable, and diagnosable task memory.

## Without It vs With It

| Scenario | Without This Tool | With Helsincy Plan With Files |
|----------|-------------------|-------------------------------|
| Long task progress | Depends on the current chat context, so goals and phases are easy to lose after compaction | `task_plan.md` stores goals, phases, and current status |
| Research context | Findings and judgments are scattered through the conversation | `findings.md` keeps discoveries, decisions, and external context summaries together |
| File changes | The agent must summarize manually, which can miss details or become subjective | Hooks automatically append objective write-tool records to `progress.md` |
| Session recovery | A new session must rebuild task context from scratch | Hooks inject the active plan on session start and user prompt submit |
| Troubleshooting | Users inspect hooks, scripts, and state files manually | `/pwf-doctor` diagnoses install, active plan, and attestation state |
| Safety boundary | Planning content can blend into normal prompt context | Delimiter framing marks planning content explicitly as data |

## Core Workflow

1. Run `install-pwf.ps1` from the release package; preview with dry-run before installing into the target project root.
2. Run `/pwf-doctor` to check hooks and commands.
3. Create a planning task with `/pwf-init <task name>`.
4. Let Codex research, edit, test, and summarize normally.
5. Hooks maintain the active `progress.md`; the agent summarizes important external context into `findings.md`.
6. Use `/pwf-switch`, `/pwf-compact`, or `/pwf-attest` when you need task switching, progress compaction, or plan locking.

## Version

Current version: `0.3.3`. See [CHANGELOG.md](CHANGELOG.md) for release notes.

Important: please do not use `v0.1.0` or earlier anymore. Older versions include the incorrect `/plw-*` command prefix and briefly introduced a global prompts installation route, which can make migration and uninstall confusing. Upgrade to the current version and use `/pwf-*` commands instead.

## User Documentation

- [普通用户使用指南](docs/USER_GUIDE.zh-CN.md): Chinese plain-language guide for what this tool does, when to use it, how to start, how to continue tasks, and how to avoid mixed progress with multiple sessions.
- [FAQ](docs/FAQ.md): user-facing answers for installation, missing commands, context compaction, session policy, progress compaction, attestation, and Chinese mode.
- [v0.3.3 Release Notes](docs/RELEASE_NOTES_0.3.3.md): bilingual release notes ready to reuse on GitHub Releases.
- [CHANGELOG.md](CHANGELOG.md): complete version history.

## Chinese Mode

By default, Helsincy Plan With Files keeps English output for compatibility with existing scripts and workflows. The language switch supports `PWF_LANG=zh-CN` and `PWF_LANG=en`. To enable Simplified Chinese hook messages, CLI output, and initialization templates, set:

```powershell
$env:PWF_LANG="zh-CN"
python .codex\skills\planning-with-files\scripts\plan.py status
python .codex\skills\planning-with-files\scripts\plan.py init "Chinese Task"
```

To force English output, set:

```powershell
$env:PWF_LANG="en"
```

Other `PWF_LANG` values fall back to English; `plan.py doctor` reports `language: warning unsupported PWF_LANG=<value>`. Safety delimiters, hashes, file paths, tool names, and `progress.md` auto record field names remain stable ASCII.

## Project Plans

- [Chinese Localization Plan](docs/CHINESE_LOCALIZATION_PLAN.md): plans the in-repo Chinese language mode, Chinese templates, Chinese CLI/hook messages, and the future `v0.2.0` release path.
- [Progress Compaction Plan](docs/PROGRESS_COMPACTION_PLAN.md): plans `progress.md` compaction, archival, summary injection, and the future `/pwf-compact` command for long-running tasks.
- [Context Injection Profiles Plan](docs/CONTEXT_INJECTION_PROFILES_PLAN.md): plans configurable hook context windows, record-aware progress injection, and diagnostics.

## Installation

For regular users, download the latest `codex.zip` installer package from the [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest). This package contains the safe installer, project-local `.codex/` payload, hooks, `/pwf-*` commands, and basic docs needed for installation.

### Option A: Download From Release

1. Open the [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
2. Download the latest Release's `codex.zip` installer package.
3. Extract it to a temporary directory.
4. Preview the install:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project -DryRun
   ```

   In a POSIX shell, use:

   ```bash
   sh ./install-pwf.sh --target /path/to/your-project --dry-run
   ```

5. If dry-run reports no conflicts, install:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project
   ```

6. Restart Codex and approve hooks when prompted.
7. Run `/pwf-doctor` inside the target project.

The target project should look like this:

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

The installer does not recursively overwrite the whole `.codex/` directory. It copies only files declared as PWF-owned in the manifest, parses and merges `.codex/hooks.json`, and records install state in `.codex/pwf-install-state.json`. If it finds an unknown same-path file, invalid `hooks.json`, or a locally modified installed file, it stops and reports a conflict by default.

### Option B: Install From git clone

Use this path if you want to inspect source code, run tests, or contribute:

```powershell
git clone https://github.com/TheLostRiver/HelsincyPlanWithFiles.git
.\HelsincyPlanWithFiles\install-pwf.ps1 -TargetPath .\your-project -DryRun
.\HelsincyPlanWithFiles\install-pwf.ps1 -TargetPath .\your-project
```

### Option C: Download Source ZIP

You can also use `Code` -> `Download ZIP` on GitHub to download the full source. After extracting it, install with `install-pwf.ps1` or `install-pwf.sh`. For normal use, prefer the release `codex.zip` package.

## Agent Slash Commands

The repository includes local user-invocable skill wrappers in `.codex/skills/pwf-*`. After installing into a target project, these commands work like `/planning-with-files`; they do not need to be installed into the user-level `.codex`. To uninstall, run `.\install-pwf.ps1 -TargetPath C:\path\to\your-project -Uninstall`; it removes only PWF files and hook entries recorded in install state and leaves `.planning/` intact.

The first batch uses the `/pwf-XXX` naming pattern. `pwf` means planning with files:

| Command | Purpose | Equivalent CLI |
|---------|---------|----------------|
| `/pwf-doctor` | Diagnose hooks, active plan, and attestation state | `plan.py doctor` |
| `/pwf-init` | Create a new planning task; session-first by default when the session is identifiable | `plan.py init <task name>` |
| `/pwf-status` | Show the current active plan status | `plan.py status` |
| `/pwf-switch` | Show or switch the active plan | `plan.py switch [plan-id]` |
| `/pwf-tasks` | List PWF tasks visible to the current session with short IDs; other sessions' exclusive tasks are hidden by default | `plan.py tasks` |
| `/pwf-use` | Bind the current session using a short ID or plan id shown by `/pwf-tasks` | `plan.py use <id>` |
| `/pwf-attest` | Create, show, or clear plan hash attestation | `plan.py attest [--show or --clear]` |
| `/pwf-capture` | Save web, browser, image, PDF, file, or note context to `findings.md` | `plan.py capture ...` |
| `/pwf-compact` | Archive old auto records and keep `progress.md` small | `plan.py compact` |
| `/pwf-context-expanded` | Switch the current session to expanded context mode | `plan.py context set expanded` |
| `/pwf-context-deep` | Switch the current session to deep recovery context mode | `plan.py context set deep` |
| `/pwf-context-default` | Restore default context mode for the current session | `plan.py context set default` |
| `/pwf-context-lean` | Switch the current session to lean context mode | `plan.py context set lean` |
| `/pwf-context-status` | Show current-session context settings and sources | `plan.py context status` |
| `/pwf-context-notice-auto` | Automatically show useful context injection notices | `plan.py context notice auto` |
| `/pwf-context-notice-on` | Show a notice whenever PWF injects context | `plan.py context notice on` |
| `/pwf-context-notice-off` | Hide context injection notices | `plan.py context notice off` |
| `/pwf-pause` | Pause context injection for the current session (PostToolUse progress recording continues) | `plan.py context pause` |
| `/pwf-resume` | Resume context injection for the current session | `plan.py context resume` |

## Compared With Upstream

| Area | Upstream `planning-with-files` | Helsincy Plan With Files |
|------|--------------------------------|--------------------------|
| Positioning | Multi-platform Manus-style planning skill | Codex/Windows-first planning runtime |
| Hook runtime | Shell-oriented scripts and platform mirrors | Python hook runtime for more reliable Windows behavior |
| Progress records | Mostly reminds the agent to write notes | Hooks automatically record objective file changes |
| Diagnostics | Requires users to inspect scripts and hook state | `plan.py doctor` diagnoses install, active plan, and attestation |
| Security boundary | Canonical skill emphasizes delimiter and attestation | Delimiter, attestation, and findings data framing are implemented in Codex hooks |

## Features

- Injects the active plan into Codex context on session start and user prompt submit.
- Includes a bounded `findings.md` tail by default during session start and user prompt submit, with an explicit opt-out.
- Reminds the agent to check the current plan before tool use.
- Appends a compact change summary to `progress.md` after file writes or edits.
- Emits a `PreCompact` reminder before Codex context compaction to keep plan status current while preserving `progress.md` as the hook-written objective log.
- Routes Codex compact recovery through the normal `SessionStart` context renderer; `PostCompact` is not used for context injection.
- Reports task progress before stop and reminds the agent to review `task_plan.md` phase/status and put interpretive conclusions in `findings.md`.
- Uses a Windows-first Python hook runtime while keeping shell and PowerShell helper scripts for compatibility.

## How It Works

The tool uses three local planning files:

```text
task_plan.md   # phases, goal, current status
findings.md    # research findings, decisions, test conclusions, errors, external context summaries
progress.md    # objective hook-written auto records and file change records
```

Hooks resolve the active plan in this order:

```text
PLAN_ID environment variable
current session binding
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

`PLAN_ID` is a routing override, not a permission override. Even when `PLAN_ID` selects a task, hooks still enforce task ownership: the current session cannot write to another session's exclusive task unless it is the owner, the task is released (or carries a legacy `shared` state), or the user explicitly claims or releases ownership. Cross-session task sharing was removed (see `docs/REMOVED_CROSS_SESSION_SHARE.md`), but historical `.task-lease.json` files that still carry `shared=true` remain readable and do not trigger ownership denial.

### Session Policy

By default, `/pwf-init` and `plan.py init` are session-first by default. When the tool can identify the current Codex conversation through `PWF_SESSION_ID` or `CODEX_THREAD_ID`, a new task is bound to that session automatically and protected by a task lease. This makes concurrent conversations in the same project use their own new PWF tasks by default.

Hook session identity is resolved as payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID`; ordinary Codex sessions usually do not need a manually configured `PWF_SESSION_ID`.

`.planning/.active_plan` is still written by default, but workspace active remains a compatibility fallback for single-session and older workflows. In multi-session work, the current session binding takes precedence. Hooks still use workspace session mode as the default policy, which keeps context recovery reliable after Codex compaction, resume, and the next user prompt.

Strict per-session isolation is opt-in. Enable `PWF_SESSION_MODE=strict` only when multiple Codex sessions in the same project must not share the active plan:

```powershell
$env:PWF_SESSION_MODE = "strict"
```

or create `.planning/session-policy.json`:

```json
{"mode":"strict"}
```

In strict mode, hook payloads must include an attached `session_id`; otherwise the hook emits a diagnostic message instead of silently skipping planning context. Run `/pwf-doctor` to inspect the current session mode.

When multiple Codex conversations work in the same project, usually run `/pwf-init <task name>` in each conversation. To intentionally use the old workspace-only behavior, pass:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-bind-session
```

To bind the task to the current session without updating `.planning/.active_plan`, pass:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --no-workspace-active
```

To bind an existing task:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session
```

The explicit form remains available:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "Task Name" --bind-session
```

`--session` writes only `.planning/session-bindings/<session-key>.json`; it does not change `.planning/.active_plan`. The old `plan.py switch <plan-id>` behavior still switches the workspace active plan.

For a lower-friction workflow, run `/pwf-tasks` first. It lists only tasks visible to the current session by default. Copy a short ID and run `/pwf-use <short-id>` to bind this conversation. Use `plan.py tasks --all` only for read-only diagnostics; claiming still requires explicit intent through `plan.py use <id> --claim`.

`--legacy` is only for root-level single-task compatibility mode and does not support session binding; `plan.py init "Task Name" --legacy --bind-session` is rejected. For multi-session isolation, use named `.planning/<plan-id>` tasks with the default session-first behavior.

If the workspace active task is already owned by another session, a new session will not automatically take it over, even when the owner is stale. Explicit claim and release use:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <plan-id> --session --force-claim
python .codex\skills\planning-with-files\scripts\plan.py switch --release-session
```

Cross-session task sharing (the old `--share`) was removed: merging multiple sessions' records into one shared context scrambles each agent's task memory, and a dozen concurrent sessions sharing one task cause progress write contention. See `docs/REMOVED_CROSS_SESSION_SHARE.md`.

`stale` is computed from the owner session heartbeat when that session lease exists; `.task-lease.json` `updated_at` is only a compatibility fallback. Stale is a diagnostic state, not permission to take ownership automatically.

To make strict mode require a task binding as well as an attached session, set:

```powershell
$env:PWF_STRICT_REQUIRES_BINDING=1
```

Automatic `progress.md` records include `Session` and `Plan-Source` fields so audits can identify which session and resolver layer produced each record.

### Context Profiles

Default hook context stays bounded: the plan head, recent progress, and a small `findings.md` tail use compact windows. For large tasks or recovery after context compaction, enable a larger injection profile:

```powershell
$env:PWF_CONTEXT_PROFILE = "expanded"
```

`PWF_CONTEXT_PROFILE` supports:

| Profile | Best For |
|---------|----------|
| `lean` | Small tasks, noisy repos, or smaller hook payloads |
| `default` | The compatible default behavior |
| `expanded` | Recommended large-feature mode with plan tail and record-aware recent progress |
| `deep` | Deliberate recovery after heavy context compaction or resume |
| `custom` | Advanced tuning through explicit `PWF_*` limit variables |

`findings.md` is included by default as a bounded tail for `UserPromptSubmit` and `SessionStart`, including Codex `SessionStart` events with source `compact`. Set `PWF_INCLUDE_FINDINGS=0` to disable findings injection, or `PWF_FINDINGS_TAIL_LINES=N` to tune the tail window. Findings are still framed as untrusted data. Run `/pwf-status` or `/pwf-doctor` to see the active profile, progress mode, findings state, and effective context budget.

Context injection notices are emitted as user-visible hook messages, separate from the injected `additionalContext`. The agent receives only the planning data; the approximate chars/tokens line, profile hints, and mute command stay out of the agent context.

`PostToolUse` only records tools that write or edit files:

```text
apply_patch | Edit | Write
```

Reading files, searching, browsing web pages, viewing images, or reading PDFs does not automatically write to `progress.md`. The agent should summarize important external context into `findings.md` after understanding it.

## Verify and Use

After installation and a Codex restart, verify with the slash command first:

```text
/pwf-doctor
```

If `/pwf-*` commands are not visible yet, use the terminal fallback from the target project root:

```powershell
cd your-project
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Create a task with:

```text
/pwf-init My Task
/pwf-status
```

The terminal fallback is:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init "My Task"
python .codex\skills\planning-with-files\scripts\plan.py status
```

After initialization, the planning files are:

```text
.planning/<plan-id>/task_plan.md
.planning/<plan-id>/findings.md
.planning/<plan-id>/progress.md
.planning/.active_plan
```

`.planning/.active_plan` contains the current plan directory name, for example:

```text
2026-05-11-codex-hooks-repair
```

Then use Codex normally. After the agent edits files, the hook appends a record to the active `progress.md`:

```text
### Auto Record: 2026-05-11 20:35:47
- Tool: apply_patch
- Session: unavailable
- Plan-Source: workspace
- Files:
  - `.codex/hooks/planning_state.py` (update)
```

By default, the hook records only objective facts: time, tool, result, and file paths. Set `PWF_LOG_COMMAND=1` to include a command summary for debugging.

## Progress Lifecycle

`progress.md` is the initial hot log, not the only permanent audit file. In long-running tasks, run `/pwf-compact` for append-only rollover: old objective auto records are written to a newly created `progress-archive/<session-key>/archive-*.md`, future records continue in a newly created `progress-active/<session-key>/active-*.md`, and `progress-index.ndjson` appends the link between them.

```text
/pwf-compact
```

Terminal fallback:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
python .codex\skills\planning-with-files\scripts\plan.py compact --keep-records 50
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
```

Rollover does not delete or overwrite existing `progress.md`, active segments, or archive files. `/pwf-doctor` also audits append-only progress storage. It checks `progress-index.ndjson`, active/archive directory roles, missing indexed files, hash mismatches, and orphan generated segments. It is report-only: it prints `No automatic repair was attempted.` and never deletes, moves, overwrites, compacts, or recreates progress files. Use `plan.py doctor --verbose` for effect/action details, `--json` for machine-readable output, and `--strict` to fail on warnings.

Agent-written summaries remain interpretive and should be checked against hook records, tests, and actual code when accuracy matters.

## Security Boundary

When hooks inject planning files, they use delimiter framing to mark file contents as data:

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

The agent should treat content inside these blocks as structured data and should not follow instruction-like text inside them.

To lock an approved plan, enable optional hash attestation:

```powershell
powershell -ExecutionPolicy RemoteSigned -File .codex\skills\planning-with-files\scripts\attest-plan.ps1
```

The PowerShell script also supports `-Show` and `-Clear`. In shell environments, use:

```text
sh .codex/skills/planning-with-files/scripts/attest-plan.sh
```

Attestation writes the current `task_plan.md` SHA-256 to `.planning/<plan-id>/.attestation`. If you use the legacy root-level `task_plan.md`, it writes `.plan-attestation` instead. On every later plan injection, the hook recomputes the hash. If the hash does not match, the hook blocks plan content injection and emits `[PLAN TAMPERED - injection blocked]` until you review the plan and re-attest or clear the attestation.

## Repository Contents

Recommended to commit:

```text
.codex/
docs/
tests/
README.md
README.en.md
.gitignore
```

Recommended to ignore:

```text
.planning/
.plan-attestation
__pycache__/
*.pyc
```

`.planning/` is runtime context. It often contains current task progress, auto records, and research notes, so it should not be committed as reusable tool code.

## Testing

Run the regression tests:

```powershell
python -m unittest discover -v
```

The tests cover:

- `apply_patch` file change records
- `Edit` / `Write` file path records
- `Bash` not writing to `progress.md`
- active plan directory resolution
- `UserPromptSubmit` / `SessionStart` JSON output
- `PreCompact` reminder output and attestation reporting
- planning data delimiter framing
- optional hash attestation match and tamper blocking
- `Stop` advisory output for incomplete tasks

## Design Principles

- Hooks automatically record only file writes and edits.
- Hook records are objective facts, such as tool, time, result, and file paths.
- Agent notes are interpretive notes, such as rationale, judgment, risk, and next steps. They are useful references but are not guaranteed to be fully accurate; verify them against hook facts and code.
- External web, browser, image, and PDF context is summarized by the agent.
- Planning files are injected as data, not executable instructions.
- Delimiter framing is enabled by default; hash attestation is optional explicit locking.
- Hooks fail open: errors should not break the main Codex workflow.
