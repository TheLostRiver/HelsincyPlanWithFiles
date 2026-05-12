# Changelog

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
