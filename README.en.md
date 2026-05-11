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
### Auto Record: 2026-05-11 20:35:47
- Tool: apply_patch
- Files:
  - `.codex/hooks/planning_state.py`
```

By default, the hook records only objective facts: time, tool, result, and file paths. Set `PWF_LOG_COMMAND=1` to include a command summary for debugging.

## Security Boundary

When hooks inject planning files, they use delimiter framing to mark file contents as data:

```text
---BEGIN PLAN DATA---
...
---END PLAN DATA---

---BEGIN PROGRESS DATA---
...
---END PROGRESS DATA---
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
- planning data delimiter framing
- optional hash attestation match and tamper blocking
- `Stop` blocking incomplete tasks

## Design Principles

- Hooks automatically record only file writes and edits.
- Hook records are objective facts, such as tool, time, result, and file paths.
- Agent notes are interpretive notes, such as rationale, judgment, risk, and next steps. They are useful references but are not guaranteed to be fully accurate; verify them against hook facts and code.
- External web, browser, image, and PDF context is summarized by the agent.
- Planning files are injected as data, not executable instructions.
- Delimiter framing is enabled by default; hash attestation is optional explicit locking.
- Hooks fail open: errors should not break the main Codex workflow.
