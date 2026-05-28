# Changelog

## Unreleased

## 0.2.0 - 2026-05-25

- Added optional Simplified Chinese mode with `PWF_LANG=zh-CN` for hook prompts, CLI output, and generated planning templates.
- Added Chinese template files under `.codex/skills/planning-with-files/templates/zh-CN/`.
- Added Chinese mode guidance to `/pwf-*` skill wrappers and both README files.
- Kept default English behavior and stable ASCII delimiters, hashes, file paths, tool names, and auto-record fields for compatibility.
- Hardened `plan.py compact` to reject unsafe archive targets and preserve `progress.md` when archive writes fail.
- Improved progress compaction parsing so manual bullet notes are not accidentally archived with objective auto records.
- Isolated CLI and hook tests from inherited `PWF_*` environment variables.

## 0.1.5 - 2026-05-13

- Stop hook now stays silent when all phases are complete, avoiding a misleading warning for finished plans.

## 0.1.4 - 2026-05-13

- Hardened `post_tool_use.py` so direct calls only record supported mutating tools: `apply_patch`, `Edit`, and `Write`.
- Improved the Chinese and English README introductions with clearer product positioning, use cases, and before/after workflow comparisons.

## 0.1.3 - 2026-05-12

- Added `plan.py compact` and `/pwf-compact` to archive old objective auto records from `progress.md`.
- Added compacted progress summary injection so long-running tasks keep bounded context without losing audit history.
- Added `status` and `doctor` compact recommendations when `progress.md` grows past the threshold.

## 0.1.2 - 2026-05-12

- Expanded injected recent `progress.md` context from 20 lines to 80 lines so objective hook records are less likely to hide important recent file changes.
- Added tests for the 80-line progress context window.
- Added the progress compaction implementation plan for future `/pwf-compact` work.
- Improved Chinese and English installation docs to start from Release zip, git clone, or source zip workflows.

## 0.1.1 - 2026-05-12

- Deprecated `v0.1.0` and earlier releases. Users should upgrade to `v0.1.1` and use `/pwf-*` commands.
- Renamed the project-local command prefix from `/plw-*` to `/pwf-*`.
- Converted `/pwf-*` commands into project-local user-invocable skill wrappers under `.codex/skills/pwf-*`.
- Removed the global prompts installer path from the current design so slash commands remain project-local and easy to uninstall.
- Updated Chinese and English README guidance for the project-local `/pwf-*` command model.

## 0.1.0 - 2026-05-11

- Added a Windows-first Python hook runtime for Codex.
- Added objective auto records for `progress.md`, including tool, result, files, operation types, and active phase.
- Added delimiter framing for injected plan, progress, and opt-in findings data.
- Added opt-in SHA-256 plan attestation with tamper blocking.
- Added `plan.py doctor`, `status`, `init`, `switch`, `attest`, and `capture` commands.
- Added `/plw-*` agent slash command prompts for the planning CLI.
- Added bilingual README files for Chinese and English users.
