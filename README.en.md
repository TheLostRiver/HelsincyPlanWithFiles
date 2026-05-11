# Helsincy Plan With Files

[简体中文](README.md) | [English](README.en.md)

Helsincy Plan With Files is a Codex skill + hook tool. It stores task plans, research findings, and progress logs as local project files so an agent can keep working after long tasks, context compaction, or session recovery.

## Features

- Injects the active plan into Codex context on session start and user prompt submit.
- Reminds the agent to check the current plan before tool use.
- Appends a compact change summary to `progress.md` after file writes or edits.
- Checks task completion before stop and asks the agent to continue when phases are incomplete.
- Uses a Windows-first Python hook runtime while keeping shell and PowerShell helper scripts for compatibility.

## How It Works

The tool uses three local planning files:

```text
task_plan.md   # phases, goal, current status
findings.md    # research findings, decisions, external context summaries
progress.md    # actions, test results, file change records
```

Hooks resolve the active plan in this order:

```text
PLAN_ID environment variable
.planning/.active_plan
newest .planning/<plan-id>/task_plan.md
root-level task_plan.md
```

`PostToolUse` only records tools that write or edit files:

```text
apply_patch | Edit | Write
```

Reading files, searching, browsing web pages, viewing images, or reading PDFs does not automatically write to `progress.md`. The agent should summarize important external context into `findings.md` after understanding it.

## Installation

Copy the `.codex/` directory into the target project root:

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

Make sure Codex hooks are enabled, and approve the hooks when Codex asks for trust. The current configuration runs hooks with `python`, so it does not require `python3` or `sh` on Windows.

## Usage

Initialize planning files with the bundled skill scripts, or create them manually:

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
### Hook Record: 2026-05-11 20:35:47
- PostToolUse: apply_patch
- Changed files:
  - `.codex/hooks/planning_state.py`
```

## Repository Contents

Recommended to commit:

```text
.codex/
tests/
README.md
README.en.md
.gitignore
```

Recommended to ignore:

```text
.planning/
__pycache__/
*.pyc
```

`.planning/` is runtime context. It often contains current task progress, command summaries, and research notes, so it should not be committed as reusable tool code.

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
- `Stop` blocking incomplete tasks

## Design Principles

- Hooks automatically record only file writes and edits.
- External web, browser, image, and PDF context is summarized by the agent.
- Planning files are injected as data, not executable instructions.
- Hooks fail open: errors should not break the main Codex workflow.

