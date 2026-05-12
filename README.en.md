# Helsincy Plan With Files

[简体中文](README.md) | [English](README.en.md)

Helsincy Plan With Files is a Codex skill + hook tool. It stores task plans, research findings, and progress logs as local project files so an agent can keep working after long tasks, context compaction, or session recovery.

## Version

Current version: `0.1.2`. See [CHANGELOG.md](CHANGELOG.md) for release notes.

Important: please do not use `v0.1.0` or earlier anymore. Older versions include the incorrect `/plw-*` command prefix and briefly introduced a global prompts installation route, which can make migration and uninstall confusing. Upgrade to the current version and use `/pwf-*` commands instead.

## Project Plans

- [Chinese Localization Plan](docs/CHINESE_LOCALIZATION_PLAN.md): plans the in-repo Chinese language mode, Chinese templates, Chinese CLI/hook messages, and the future `v0.2.0` release path.
- [Progress Compaction Plan](docs/PROGRESS_COMPACTION_PLAN.md): plans `progress.md` compaction, archival, summary injection, and the future `/pwf-compact` command for long-running tasks.

## Installation

For regular users, download `HelsincyPlanWithFiles-v0.1.2-codex.zip` from the release page. This package contains only the project-local `.codex/`, hooks, `/pwf-*` commands, and basic docs needed for installation.

### Option A: Download From Release

1. Open the [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
2. Download `HelsincyPlanWithFiles-v0.1.2-codex.zip`.
3. Unzip it and copy the `.codex/` directory into your target project root.
4. Restart Codex and approve the hooks when Codex asks for trust.
5. Run `/pwf-doctor` in Codex to check the installation.

The target project should look like this:

```text
your-project/
  .codex/
    hooks.json
    hooks/
    skills/
```

If the target project already has a `.codex/` directory, back it up or merge `hooks.json` manually so existing project configuration is not overwritten.

### Option B: Install From git clone

Use this path if you want to inspect source code, run tests, or contribute:

```powershell
git clone https://github.com/TheLostRiver/HelsincyPlanWithFiles.git
Copy-Item -Recurse -Force .\HelsincyPlanWithFiles\.codex .\your-project\
```

### Option C: Download Source ZIP

You can also use `Code` -> `Download ZIP` on GitHub to download the full source. After extracting it, copy only `.codex/` into the target project root. For normal use, prefer the release `codex.zip` package.

## Agent Slash Commands

The repository includes local user-invocable skill wrappers in `.codex/skills/pwf-*`. After copying `.codex/` into a target project, these commands work like `/planning-with-files`; they do not need to be installed into the user-level `.codex`, so uninstalling is just removing the project-local `.codex/`.

The first batch uses the `/pwf-XXX` naming pattern. `pwf` means planning with files:

| Command | Purpose | Equivalent CLI |
|---------|---------|----------------|
| `/pwf-doctor` | Diagnose hooks, active plan, and attestation state | `plan.py doctor` |
| `/pwf-init` | Create a new planning task | `plan.py init <task name>` |
| `/pwf-status` | Show the current active plan status | `plan.py status` |
| `/pwf-switch` | Show or switch the active plan | `plan.py switch [plan-id]` |
| `/pwf-attest` | Create, show, or clear plan hash attestation | `plan.py attest [--show or --clear]` |
| `/pwf-capture` | Save web, browser, image, PDF, file, or note context to `findings.md` | `plan.py capture ...` |
| `/pwf-compact` | Archive old auto records and keep `progress.md` small | `plan.py compact` |

## Compared With Upstream

| Area | Upstream `planning-with-files` | Helsincy Plan With Files |
|------|--------------------------------|--------------------------|
| Positioning | Multi-platform Manus-style planning skill | Codex/Windows-first planning runtime |
| Hook runtime | Shell-oriented scripts and platform mirrors | Python hook runtime for more reliable Windows behavior |
| Progress records | Mostly reminds the agent to write notes | Hooks automatically record objective file changes |
| Diagnostics | Requires users to inspect scripts and hook state | `plan.py doctor` diagnoses install, active plan, and attestation |
| Security boundary | Canonical skill emphasizes delimiter and attestation | Delimiter, attestation, and findings opt-in framing are implemented in Codex hooks |

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
- Files:
  - `.codex/hooks/planning_state.py`
```

By default, the hook records only objective facts: time, tool, result, and file paths. Set `PWF_LOG_COMMAND=1` to include a command summary for debugging.

## Progress Lifecycle

`progress.md` is the hot log, not the permanent audit file. In long-running tasks, run `/pwf-compact` to archive old objective auto records to `progress.archive.md` while keeping a compact summary and recent records in `progress.md`.

```text
/pwf-compact
```

Terminal fallback:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
python .codex\skills\planning-with-files\scripts\plan.py compact --keep-records 50
python .codex\skills\planning-with-files\scripts\plan.py compact --dry-run
```

The compact summary only reports objective facts, such as archived count, time range, tool counts, and file count. Agent-written summaries remain interpretive and should be checked against hook records, tests, and actual code when accuracy matters.

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
