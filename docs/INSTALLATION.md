# Installation Guide

Use the latest `codex.zip` from [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest). Do not download or document a fixed versioned zip name in general installation docs.

This project is currently installed as project-local Codex files. The important safety rule is: do not blindly overwrite an existing `.codex/` directory.

## Hook Feature Flag

Codex now uses this feature flag name:

```toml
[features]
hooks = true
```

Do not write new docs or examples with `[features].codex_hooks`; that key is deprecated. You can enable hooks in user or project config, or start Codex CLI with:

```powershell
codex --enable hooks
```

Project-local `.codex/config.toml`, `.codex/hooks.json`, and project-local hooks are loaded only after Codex trusts the project.

## Codex CLI

1. Open [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
2. Download the latest `codex.zip`.
3. Extract it to a temporary directory.
4. If the target project does not have `.codex/`, copy the extracted `.codex/` directory into the project root.
5. If the target project already has `.codex/`, do not overwrite it. Manually merge `hooks.json`, `hooks/`, and `skills/`, or inspect the diff with Codex first.
6. Ensure hooks are enabled with `[features] hooks = true` in config, or start the CLI with `codex --enable hooks`.
7. Start Codex CLI in the target project and approve the project or hook trust prompt.
8. Run:

   ```text
   /pwf-doctor
   ```

## Codex App

1. Open the target project in Codex App and use Local mode.
2. Download and extract the latest `codex.zip` from [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
3. If the target project does not have `.codex/`, copy the extracted `.codex/` directory into the project root.
4. If the target project already has `.codex/`, do not overwrite it. Manually merge `hooks.json`, `hooks/`, and `skills/`, or inspect the diff with Codex first.
5. Reopen the project or start a new thread so the app reloads project-local `.codex/`.
6. Approve the project or hook trust prompt when Codex asks.
7. Run:

   ```text
   /pwf-doctor
   ```

The Codex App Settings -> Configuration screen opens user-level config. Project-local behavior still depends on the currently selected trusted project.

## Existing `.codex/`

If the target project already has `.codex/`, treat it as user-owned project configuration:

- Do not use a file manager copy operation that replaces the whole directory.
- Review `.codex/hooks.json` before adding PWF hook entries.
- Preserve unrelated hooks, skills, rules, MCP settings, and project config.
- Keep `.planning/` task data in the target project when upgrading.
