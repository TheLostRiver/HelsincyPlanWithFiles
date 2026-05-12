# Changelog

## Unreleased

- Converted `/plw-*` commands into project-local user-invocable skill wrappers under `.codex/skills/plw-*`.

## 0.1.0 - 2026-05-11

- Added a Windows-first Python hook runtime for Codex.
- Added objective auto records for `progress.md`, including tool, result, files, operation types, and active phase.
- Added delimiter framing for injected plan, progress, and opt-in findings data.
- Added opt-in SHA-256 plan attestation with tamper blocking.
- Added `plan.py doctor`, `status`, `init`, `switch`, `attest`, and `capture` commands.
- Added `/plw-*` agent slash command prompts for the planning CLI.
- Added bilingual README files for Chinese and English users.
