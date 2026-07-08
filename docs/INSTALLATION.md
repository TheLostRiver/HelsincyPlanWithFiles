# Installation Guide

This project is installed into each target repository with the release installer. Do not manually copy the whole `.codex/` directory over an existing project, because that can overwrite project-local Codex settings.

Use the latest `codex.zip` from [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest). The installer copies only manifest-owned PWF files, merges `.codex/hooks.json`, and records ownership in `.codex/pwf-install-state.json`.

## Hook Feature Flag

Codex now uses this feature flag name:

```toml
[features]
hooks = true
```

Do not write new docs or examples with `[features].codex_hooks`; that key is deprecated. The installer includes `.codex/config.toml` with `hooks = true` for clean target projects. If your target project already has `.codex/config.toml`, the safe installer stops instead of merging it blindly. In that case, review your existing config and add `hooks = true` under `[features]`, or start Codex CLI with `codex --enable hooks`.

Project-local `.codex/config.toml`, `.codex/hooks.json`, and project-local hooks are loaded only after Codex trusts the project.

## Codex CLI

1. Open [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
2. Download the latest `codex.zip`.
3. Extract it to a temporary directory.
4. Preview the install from the extracted directory:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project -DryRun
   ```

   POSIX shell:

   ```bash
   sh ./install-pwf.sh --target /path/to/your-project --dry-run
   ```

5. If dry-run reports no conflicts, install:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project
   ```

6. Start Codex CLI in the target project. If hooks are disabled in your environment, use:

   ```powershell
   codex --enable hooks
   ```

7. Approve the project or hooks trust prompt when Codex asks.
8. Run:

   ```text
   /pwf-doctor
   ```

## Codex App

1. Open the target project in Codex App and use Local mode.
2. Download and extract the latest `codex.zip` from [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
3. Run the same dry-run and install commands from the extracted directory:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project -DryRun
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project
   ```

4. Reopen the project or start a new thread so the app reloads project-local `.codex/` files.
5. Approve the project or hooks trust prompt when Codex asks.
6. Run:

   ```text
   /pwf-doctor
   ```

The Codex App Settings -> Configuration screen opens user-level config. PWF installs project-level config at `your-project/.codex/config.toml`, so project trust and the currently selected project still matter.

## Existing `.codex/`

If the target project already has `.codex/`, always run dry-run first. The installer is intentionally conservative:

- Unknown same-path files are conflicts.
- Invalid `.codex/hooks.json` is a conflict.
- Locally modified PWF-owned files are conflicts unless you explicitly choose a force-owned upgrade.
- Existing `.codex/config.toml` is not merged automatically; review it and add `[features] hooks = true` yourself if needed.

Uninstall removes only files and hook entries recorded in `.codex/pwf-install-state.json`. It leaves `.planning/` task data in place.
