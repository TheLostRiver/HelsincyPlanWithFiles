# Safe Installation Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current "copy the whole `.codex/` directory" installation flow with a manifest-driven installer that merges project Codex configuration without overwriting unrelated user files.

**Architecture:** Add a small Python installer as the source of truth, with PowerShell and POSIX shell wrappers for user convenience. The installer reads a declarative manifest, copies only PWF-owned files, merges `hooks.json` structurally, writes an install-state ledger, and refuses unknown conflicts by default. Release packaging includes the installer, manifest, and wrappers so users install from the extracted release directory instead of manually copying `.codex/`.

**Tech Stack:** Python standard library, PowerShell wrapper, POSIX shell wrapper, Codex project-local `.codex` hooks/skills, `unittest`, existing `build-release.ps1`.

---

## Scope

This plan covers the installer and release/documentation changes needed for a safer project-local install.

In scope:

- Install from an extracted release package into a target project.
- Update an existing PWF installation without blindly overwriting local changes.
- Merge `.codex/hooks.json` without deleting existing project hooks.
- Record installed file hashes in `.codex/pwf-install-state.json`.
- Support dry-run and uninstall flows.
- Keep manual copy as a documented advanced fallback only.

Out of scope:

- Global user-level Codex installation.
- A graphical installer.
- Automatic migration of arbitrary third-party hook scripts into PWF namespaces.
- Deleting `.planning/` data during uninstall.

## Design Decisions

### Canonical Installer Entry Points

Release packages should expose these top-level commands:

```powershell
.\install-pwf.ps1 -TargetPath C:\path\to\project
.\install-pwf.ps1 -TargetPath C:\path\to\project -DryRun
```

```bash
sh ./install-pwf.sh --target /path/to/project
sh ./install-pwf.sh --target /path/to/project --dry-run
```

```powershell
python .\installer\pwf_install.py install --target C:\path\to\project
python .\installer\pwf_install.py uninstall --target C:\path\to\project --dry-run
```

The wrappers delegate to Python and do not implement merge logic themselves.

### Default Safety Policy

The installer must never perform a recursive overwrite of `.codex/`.

File behavior:

| Target state | Installer behavior |
| --- | --- |
| target file missing | copy source file |
| target file exists with same hash | skip |
| target file exists and install-state says PWF owns the same current hash | overwrite during upgrade |
| target file exists, install-state says PWF owns it, but local file was modified | conflict unless `--force-owned` is set |
| target file exists and is unknown to PWF | conflict |

`hooks.json` behavior:

| Target state | Installer behavior |
| --- | --- |
| missing | create with manifest hook entries |
| valid JSON with no PWF hooks | append PWF hooks; preserve existing hooks |
| valid JSON with current PWF hooks | dedupe; no duplicate entries |
| valid JSON with legacy PWF hook commands | replace known legacy commands with current namespaced commands |
| invalid JSON | conflict; do not overwrite |

Backups:

- Before changing `hooks.json`, write a timestamped backup under `.codex/backups/pwf-install-<timestamp>/hooks.json`.
- Before overwriting an owned file with `--force-owned`, write that file to the same backup directory while preserving its relative path.
- Do not back up on dry-run because dry-run writes nothing.

### Namespaced Hook Files

To reduce collisions with target projects that already have generic hook scripts, new installs should use:

```text
.codex/hooks/pwf/session_start.py
.codex/hooks/pwf/user_prompt_submit.py
.codex/hooks/pwf/pre_tool_use.py
.codex/hooks/pwf/post_tool_use.py
.codex/hooks/pwf/pre_compact.py
.codex/hooks/pwf/stop.py
.codex/hooks/pwf/codex_hook_adapter.py
.codex/hooks/pwf/planning_state.py
```

The existing top-level hook files remain as compatibility wrappers for one release cycle:

```text
.codex/hooks/session_start.py
.codex/hooks/user_prompt_submit.py
.codex/hooks/pre_tool_use.py
.codex/hooks/post_tool_use.py
.codex/hooks/pre_compact.py
.codex/hooks/stop.py
.codex/hooks/codex_hook_adapter.py
.codex/hooks/planning_state.py
```

New `hooks.json` entries use only the namespaced paths. Doctor diagnostics should accept both current and legacy paths during the migration, but warn when legacy paths are detected.

### Install State

The target project receives:

```text
.codex/pwf-install-state.json
```

Schema:

```json
{
  "schema": 1,
  "package": "HelsincyPlanWithFiles",
  "version": "0.3.4",
  "installed_at": "2026-06-25T15:00:00Z",
  "files": [
    {
      "path": ".codex/hooks/pwf/session_start.py",
      "sha256": "hex"
    }
  ],
  "hooks": [
    {
      "event": "SessionStart",
      "matcher": "startup|resume|compact",
      "command": "python .codex/hooks/pwf/session_start.py"
    }
  ]
}
```

Rules:

- `path` is always relative to the target root.
- No absolute project path is stored.
- Hashes describe the target file content after install.
- The state file itself is PWF-owned.

## File Structure

Create:

- `installer/pwf_install.py` - manifest loading, planning, file copy, hook merge, backup, uninstall, CLI.
- `installer/pwf_install_manifest.json` - declarative owned files and hook entries.
- `install-pwf.ps1` - PowerShell wrapper around `installer/pwf_install.py`.
- `install-pwf.sh` - POSIX shell wrapper around `installer/pwf_install.py`.
- `tests/test_installer.py` - installer unit tests using temporary source/target directories.
- `.codex/hooks/pwf/session_start.py` - namespaced hook entrypoint.
- `.codex/hooks/pwf/user_prompt_submit.py` - namespaced hook entrypoint.
- `.codex/hooks/pwf/pre_tool_use.py` - namespaced hook entrypoint.
- `.codex/hooks/pwf/post_tool_use.py` - namespaced hook entrypoint.
- `.codex/hooks/pwf/pre_compact.py` - namespaced hook entrypoint.
- `.codex/hooks/pwf/stop.py` - namespaced hook entrypoint.
- `.codex/hooks/pwf/codex_hook_adapter.py` - moved shared hook adapter.
- `.codex/hooks/pwf/planning_state.py` - moved shared planning state module.
- `.codex/hooks/pwf/__init__.py` - package marker for legacy compatibility imports.

Modify:

- `.codex/hooks.json` - switch commands to `.codex/hooks/pwf/*.py`.
- `.codex/hooks/*.py` - replace old hook entrypoints with compatibility wrappers.
- `.codex/skills/planning-with-files/scripts/plan.py` - doctor canonical hook path checks and installer diagnostics.
- `build-release.ps1` - include installer files in both release variants and mention installer package semantics.
- `README.md` - Chinese install instructions.
- `README.en.md` - English install instructions.
- `docs/FAQ.md` - install conflict and upgrade answers.
- `docs/USER_GUIDE.zh-CN.md` - plain-language install flow.
- `docs/SOURCE_SAFETY_DISCLAIMER.md` - clarify installer conflict policy.
- `CHANGELOG.md` - unreleased entry for safer installer.
- `tests/test_hooks.py` - namespaced hook script invocation and JSONL behavior.
- `tests/test_plan_doctor.py` - doctor accepts namespaced hooks and warns on legacy hooks.
- `tests/test_project_consistency.py` - hooks path consistency checks.
- `tests/test_pwf_commands.py` - docs and command wrappers still point to existing plan script paths.

## Task 1: Add Installer Manifest

**Files:**

- Create: `installer/pwf_install_manifest.json`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Write manifest loading tests**

Add `tests/test_installer.py` with these helpers:

```python
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = REPO_ROOT / "installer" / "pwf_install.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("pwf_install", INSTALLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
```

Add tests:

```python
class InstallerManifestTests(unittest.TestCase):
    def test_manifest_lists_only_relative_paths(self):
        module = load_installer()
        manifest = module.load_manifest(REPO_ROOT / "installer" / "pwf_install_manifest.json")
        for item in manifest.owned_files:
            self.assertFalse(Path(item.source).is_absolute())
            self.assertFalse(Path(item.target).is_absolute())

    def test_manifest_hook_commands_are_namespaced(self):
        module = load_installer()
        manifest = module.load_manifest(REPO_ROOT / "installer" / "pwf_install_manifest.json")
        commands = [hook.command for hook in manifest.hook_entries]
        self.assertIn("python .codex/hooks/pwf/session_start.py", commands)
        self.assertTrue(all(".codex/hooks/pwf/" in command for command in commands))
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_installer -v
```

Expected: fail because `installer/pwf_install.py` and `installer/pwf_install_manifest.json` do not exist yet.

- [ ] **Step 3: Create the manifest file**

Create `installer/pwf_install_manifest.json`:

```json
{
  "schema": 1,
  "package": "HelsincyPlanWithFiles",
  "owned_files": [
    {"source": ".codex/hooks/pwf/session_start.py", "target": ".codex/hooks/pwf/session_start.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/user_prompt_submit.py", "target": ".codex/hooks/pwf/user_prompt_submit.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/pre_tool_use.py", "target": ".codex/hooks/pwf/pre_tool_use.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/post_tool_use.py", "target": ".codex/hooks/pwf/post_tool_use.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/pre_compact.py", "target": ".codex/hooks/pwf/pre_compact.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/stop.py", "target": ".codex/hooks/pwf/stop.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/codex_hook_adapter.py", "target": ".codex/hooks/pwf/codex_hook_adapter.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/planning_state.py", "target": ".codex/hooks/pwf/planning_state.py", "kind": "hook"},
    {"source": ".codex/hooks/pwf/__init__.py", "target": ".codex/hooks/pwf/__init__.py", "kind": "hook"},
    {"source": ".codex/hooks/post-tool-use.sh", "target": ".codex/hooks/post-tool-use.sh", "kind": "legacy-shell"},
    {"source": ".codex/hooks/pre-compact.sh", "target": ".codex/hooks/pre-compact.sh", "kind": "legacy-shell"},
    {"source": ".codex/hooks/pre-tool-use.sh", "target": ".codex/hooks/pre-tool-use.sh", "kind": "legacy-shell"},
    {"source": ".codex/hooks/resolve-plan-dir.sh", "target": ".codex/hooks/resolve-plan-dir.sh", "kind": "legacy-shell"},
    {"source": ".codex/hooks/session-start.sh", "target": ".codex/hooks/session-start.sh", "kind": "legacy-shell"},
    {"source": ".codex/hooks/stop.sh", "target": ".codex/hooks/stop.sh", "kind": "legacy-shell"},
    {"source": ".codex/hooks/user-prompt-submit.sh", "target": ".codex/hooks/user-prompt-submit.sh", "kind": "legacy-shell"},
    {"source": ".codex/skills/planning-with-files/SKILL.md", "target": ".codex/skills/planning-with-files/SKILL.md", "kind": "skill"},
    {"source": ".codex/skills/planning-with-files/references/examples.md", "target": ".codex/skills/planning-with-files/references/examples.md", "kind": "skill"},
    {"source": ".codex/skills/planning-with-files/references/reference.md", "target": ".codex/skills/planning-with-files/references/reference.md", "kind": "skill"},
    {"source": ".codex/skills/planning-with-files/scripts/attest-plan.ps1", "target": ".codex/skills/planning-with-files/scripts/attest-plan.ps1", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/attest-plan.sh", "target": ".codex/skills/planning-with-files/scripts/attest-plan.sh", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/check-complete.ps1", "target": ".codex/skills/planning-with-files/scripts/check-complete.ps1", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/check-complete.sh", "target": ".codex/skills/planning-with-files/scripts/check-complete.sh", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/init-session.ps1", "target": ".codex/skills/planning-with-files/scripts/init-session.ps1", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/init-session.sh", "target": ".codex/skills/planning-with-files/scripts/init-session.sh", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/plan.ps1", "target": ".codex/skills/planning-with-files/scripts/plan.ps1", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/plan.py", "target": ".codex/skills/planning-with-files/scripts/plan.py", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/plan.sh", "target": ".codex/skills/planning-with-files/scripts/plan.sh", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/progress_lifecycle.py", "target": ".codex/skills/planning-with-files/scripts/progress_lifecycle.py", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/resolve-plan-dir.ps1", "target": ".codex/skills/planning-with-files/scripts/resolve-plan-dir.ps1", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/resolve-plan-dir.sh", "target": ".codex/skills/planning-with-files/scripts/resolve-plan-dir.sh", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/session-catchup.py", "target": ".codex/skills/planning-with-files/scripts/session-catchup.py", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/set-active-plan.ps1", "target": ".codex/skills/planning-with-files/scripts/set-active-plan.ps1", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/scripts/set-active-plan.sh", "target": ".codex/skills/planning-with-files/scripts/set-active-plan.sh", "kind": "skill-script"},
    {"source": ".codex/skills/planning-with-files/templates/findings.md", "target": ".codex/skills/planning-with-files/templates/findings.md", "kind": "template"},
    {"source": ".codex/skills/planning-with-files/templates/progress.md", "target": ".codex/skills/planning-with-files/templates/progress.md", "kind": "template"},
    {"source": ".codex/skills/planning-with-files/templates/task_plan.md", "target": ".codex/skills/planning-with-files/templates/task_plan.md", "kind": "template"},
    {"source": ".codex/skills/planning-with-files/templates/zh-CN/findings.md", "target": ".codex/skills/planning-with-files/templates/zh-CN/findings.md", "kind": "template"},
    {"source": ".codex/skills/planning-with-files/templates/zh-CN/progress.md", "target": ".codex/skills/planning-with-files/templates/zh-CN/progress.md", "kind": "template"},
    {"source": ".codex/skills/planning-with-files/templates/zh-CN/task_plan.md", "target": ".codex/skills/planning-with-files/templates/zh-CN/task_plan.md", "kind": "template"}
  ],
  "owned_directory_globs": [
    ".codex/skills/pwf-*"
  ],
  "hook_entries": [
    {
      "event": "SessionStart",
      "matcher": "startup|resume|compact",
      "type": "command",
      "command": "python .codex/hooks/pwf/session_start.py",
      "statusMessage": "Loading planning context"
    },
    {
      "event": "UserPromptSubmit",
      "type": "command",
      "command": "python .codex/hooks/pwf/user_prompt_submit.py"
    },
    {
      "event": "PreToolUse",
      "matcher": "Bash|apply_patch|Edit|Write",
      "type": "command",
      "command": "python .codex/hooks/pwf/pre_tool_use.py",
      "statusMessage": "Checking plan before tool use"
    },
    {
      "event": "PostToolUse",
      "matcher": "apply_patch|Edit|Write",
      "type": "command",
      "command": "python .codex/hooks/pwf/post_tool_use.py",
      "statusMessage": "Recording tool context"
    },
    {
      "event": "PreCompact",
      "matcher": "*",
      "type": "command",
      "command": "python .codex/hooks/pwf/pre_compact.py",
      "statusMessage": "Preparing planning context before compact"
    },
    {
      "event": "Stop",
      "type": "command",
      "command": "python .codex/hooks/pwf/stop.py",
      "timeout": 30
    }
  ],
  "legacy_hook_commands": [
    {"event": "SessionStart", "command": "python .codex/hooks/session_start.py"},
    {"event": "UserPromptSubmit", "command": "python .codex/hooks/user_prompt_submit.py"},
    {"event": "PreToolUse", "command": "python .codex/hooks/pre_tool_use.py"},
    {"event": "PostToolUse", "command": "python .codex/hooks/post_tool_use.py"},
    {"event": "PreCompact", "command": "python .codex/hooks/pre_compact.py"},
    {"event": "Stop", "command": "python .codex/hooks/stop.py"}
  ]
}
```

The manifest intentionally lists `planning-with-files` files explicitly. `pwf-*` wrapper skills may be collected from the source tree by the installer using the `owned_directory_globs` entry, because that set changes more often.

- [ ] **Step 4: Implement minimal manifest loader**

Create `installer/pwf_install.py`:

```python
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class OwnedFile:
    source: str
    target: str
    kind: str


@dataclass(frozen=True)
class HookEntry:
    event: str
    command: str
    type: str = "command"
    matcher: str | None = None
    statusMessage: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class Manifest:
    schema: int
    package: str
    owned_files: tuple[OwnedFile, ...]
    owned_directory_globs: tuple[str, ...]
    hook_entries: tuple[HookEntry, ...]
    legacy_hook_commands: tuple[HookEntry, ...]


def _require_relative(path_text: str, field_name: str) -> str:
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be a safe relative path: {path_text}")
    return path_text.replace("\\", "/")


def load_manifest(path: Path) -> Manifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    owned_files = tuple(
        OwnedFile(
            source=_require_relative(item["source"], "source"),
            target=_require_relative(item["target"], "target"),
            kind=item["kind"],
        )
        for item in raw.get("owned_files", [])
    )
    hook_entries = tuple(HookEntry(**item) for item in raw.get("hook_entries", []))
    legacy_entries = tuple(HookEntry(event=item["event"], command=item["command"]) for item in raw.get("legacy_hook_commands", []))
    return Manifest(
        schema=int(raw["schema"]),
        package=str(raw["package"]),
        owned_files=owned_files,
        owned_directory_globs=tuple(str(item) for item in raw.get("owned_directory_globs", [])),
        hook_entries=hook_entries,
        legacy_hook_commands=legacy_entries,
    )
```

- [ ] **Step 5: Run focused tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: manifest tests pass.

- [ ] **Step 6: Commit**

```powershell
git add installer/pwf_install.py installer/pwf_install_manifest.json tests/test_installer.py
git commit -m "test: add installer manifest contract"
```

## Task 2: Implement Safe File Planning

**Files:**

- Modify: `installer/pwf_install.py`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Add file-plan tests**

Add tests:

```python
class InstallerFilePlanTests(unittest.TestCase):
    def test_missing_target_file_is_planned_for_copy(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=None)
            self.assertEqual("copy", op.action)

    def test_unknown_existing_target_file_is_conflict(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (target / ".codex/hooks/pwf/session_start.py").write_text("print('user')\n", encoding="utf-8")
            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=None)
            self.assertEqual("conflict", op.action)

    def test_identical_existing_target_file_is_skip(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            for root in (source, target):
                (root / ".codex/hooks/pwf").mkdir(parents=True)
                (root / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=None)
            self.assertEqual("skip", op.action)
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_installer -v
```

Expected: fail because `plan_file_operation` is not implemented.

- [ ] **Step 3: Add file operation model**

In `installer/pwf_install.py`:

```python
@dataclass(frozen=True)
class FileOperation:
    action: str
    source: Path
    target: Path
    relative_target: str
    reason: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_install_state(target_root: Path) -> dict[str, Any] | None:
    state_path = target_root / ".codex" / "pwf-install-state.json"
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def state_file_hash(state: Mapping[str, Any] | None, rel_path: str) -> str | None:
    if not state:
        return None
    for item in state.get("files", []):
        if item.get("path") == rel_path:
            value = item.get("sha256")
            return value if isinstance(value, str) else None
    return None


def plan_file_operation(
    source_root: Path,
    target_root: Path,
    owned: OwnedFile,
    state: Mapping[str, Any] | None,
    *,
    force_owned: bool = False,
) -> FileOperation:
    source = source_root / owned.source
    target = target_root / owned.target
    rel = owned.target
    if not source.is_file():
        return FileOperation("conflict", source, target, rel, "source file missing from installer package")
    if not target.exists():
        return FileOperation("copy", source, target, rel, "target file is missing")
    source_hash = sha256_file(source)
    target_hash = sha256_file(target)
    if source_hash == target_hash:
        return FileOperation("skip", source, target, rel, "target file already matches package")
    owned_hash = state_file_hash(state, rel)
    if owned_hash and owned_hash == target_hash:
        return FileOperation("overwrite", source, target, rel, "target file matches previous PWF install state")
    if owned_hash and force_owned:
        return FileOperation("overwrite", source, target, rel, "target file is PWF-owned and --force-owned was set")
    if owned_hash:
        return FileOperation("conflict", source, target, rel, "PWF-owned file has local modifications")
    return FileOperation("conflict", source, target, rel, "target file exists but is not recorded as PWF-owned")
```

- [ ] **Step 4: Add glob expansion**

Add:

```python
def expand_owned_files(source_root: Path, manifest: Manifest) -> tuple[OwnedFile, ...]:
    files = list(manifest.owned_files)
    for pattern in manifest.owned_directory_globs:
        for path in source_root.glob(pattern):
            if not path.is_dir():
                continue
            for child in path.rglob("*"):
                if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc":
                    rel = child.relative_to(source_root).as_posix()
                    files.append(OwnedFile(rel, rel, "skill-wrapper"))
    deduped: dict[str, OwnedFile] = {}
    for item in files:
        deduped[item.target] = item
    return tuple(deduped[path] for path in sorted(deduped))
```

- [ ] **Step 5: Run focused tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: all installer tests pass.

- [ ] **Step 6: Commit**

```powershell
git add installer/pwf_install.py tests/test_installer.py
git commit -m "feat: plan safe installer file operations"
```

## Task 3: Implement `hooks.json` Merge

**Files:**

- Modify: `installer/pwf_install.py`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Add hook merge tests**

Add tests:

```python
class InstallerHooksMergeTests(unittest.TestCase):
    def test_merge_hooks_preserves_existing_hook(self):
        module = load_installer()
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/custom.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/pwf/user_prompt_submit.py"),),
            legacy_hook_commands=(),
        )
        merged, changed = module.merge_hooks_json(existing, manifest)
        self.assertTrue(changed)
        commands = [
            hook["command"]
            for group in merged["hooks"]["UserPromptSubmit"]
            for hook in group.get("hooks", [])
        ]
        self.assertIn("python .codex/hooks/custom.py", commands)
        self.assertIn("python .codex/hooks/pwf/user_prompt_submit.py", commands)

    def test_merge_hooks_dedupes_existing_pwf_hook(self):
        module = load_installer()
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/pwf/user_prompt_submit.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/pwf/user_prompt_submit.py"),),
            legacy_hook_commands=(),
        )
        merged, changed = module.merge_hooks_json(existing, manifest)
        self.assertFalse(changed)
        groups = merged["hooks"]["UserPromptSubmit"]
        self.assertEqual(1, len(groups))

    def test_merge_hooks_replaces_legacy_pwf_command(self):
        module = load_installer()
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/user_prompt_submit.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/pwf/user_prompt_submit.py"),),
            legacy_hook_commands=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/user_prompt_submit.py"),),
        )
        merged, changed = module.merge_hooks_json(existing, manifest)
        self.assertTrue(changed)
        commands = [
            hook["command"]
            for group in merged["hooks"]["UserPromptSubmit"]
            for hook in group.get("hooks", [])
        ]
        self.assertNotIn("python .codex/hooks/user_prompt_submit.py", commands)
        self.assertIn("python .codex/hooks/pwf/user_prompt_submit.py", commands)
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_installer -v
```

Expected: fail because `merge_hooks_json` is not implemented.

- [ ] **Step 3: Implement hook entry serialization**

Add:

```python
def normalize_command(command: str) -> str:
    return " ".join(command.replace("\\", "/").split())


def hook_entry_to_group(entry: HookEntry) -> dict[str, Any]:
    hook: dict[str, Any] = {"type": entry.type, "command": entry.command}
    if entry.statusMessage:
        hook["statusMessage"] = entry.statusMessage
    if entry.timeout is not None:
        hook["timeout"] = entry.timeout
    group: dict[str, Any] = {"hooks": [hook]}
    if entry.matcher is not None:
        group["matcher"] = entry.matcher
    return group
```

- [ ] **Step 4: Implement merge function**

Add:

```python
def merge_hooks_json(existing: Mapping[str, Any], manifest: Manifest) -> tuple[dict[str, Any], bool]:
    merged = json.loads(json.dumps(existing))
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks.json field 'hooks' must be an object")

    changed = False
    legacy_by_event: dict[str, set[str]] = {}
    for legacy in manifest.legacy_hook_commands:
        legacy_by_event.setdefault(legacy.event, set()).add(normalize_command(legacy.command))

    for entry in manifest.hook_entries:
        event_groups = hooks.setdefault(entry.event, [])
        if not isinstance(event_groups, list):
            raise ValueError(f"hooks.json event {entry.event} must be an array")

        current_command = normalize_command(entry.command)
        legacy_commands = legacy_by_event.get(entry.event, set())
        found_current = False
        filtered_groups: list[dict[str, Any]] = []

        for group in event_groups:
            if not isinstance(group, dict):
                filtered_groups.append(group)
                continue
            group_hooks = group.get("hooks", [])
            if not isinstance(group_hooks, list):
                filtered_groups.append(group)
                continue
            kept_hooks = []
            for hook in group_hooks:
                if not isinstance(hook, dict):
                    kept_hooks.append(hook)
                    continue
                command = hook.get("command")
                normalized = normalize_command(command) if isinstance(command, str) else ""
                if normalized == current_command:
                    found_current = True
                    kept_hooks.append(hook)
                elif normalized in legacy_commands:
                    changed = True
                else:
                    kept_hooks.append(hook)
            if kept_hooks:
                new_group = dict(group)
                new_group["hooks"] = kept_hooks
                filtered_groups.append(new_group)
            elif group_hooks:
                changed = True

        if not found_current:
            filtered_groups.append(hook_entry_to_group(entry))
            changed = True
        if filtered_groups != event_groups:
            changed = True
        hooks[entry.event] = filtered_groups

    return merged, changed
```

- [ ] **Step 5: Run focused tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: hook merge tests pass.

- [ ] **Step 6: Commit**

```powershell
git add installer/pwf_install.py tests/test_installer.py
git commit -m "feat: merge codex hooks during install"
```

## Task 4: Implement Install, Dry-run, Backup, and State Write

**Files:**

- Modify: `installer/pwf_install.py`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Add end-to-end install tests**

Add tests:

```python
class InstallerApplyTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(module.HookEntry(event="SessionStart", matcher="startup|resume|compact", command="python .codex/hooks/pwf/session_start.py"),),
                legacy_hook_commands=(),
            )
            result = module.install(source, target, manifest, version="0.3.4", dry_run=True)
            self.assertEqual(0, result.exit_code)
            self.assertFalse((target / ".codex/hooks/pwf/session_start.py").exists())
            self.assertFalse((target / ".codex/hooks.json").exists())

    def test_install_copies_files_merges_hooks_and_writes_state(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(module.HookEntry(event="SessionStart", matcher="startup|resume|compact", command="python .codex/hooks/pwf/session_start.py"),),
                legacy_hook_commands=(),
            )
            result = module.install(source, target, manifest, version="0.3.4", dry_run=False)
            self.assertEqual(0, result.exit_code)
            self.assertTrue((target / ".codex/hooks/pwf/session_start.py").is_file())
            hooks = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
            self.assertEqual("python .codex/hooks/pwf/session_start.py", hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"])
            state = json.loads((target / ".codex/pwf-install-state.json").read_text(encoding="utf-8"))
            self.assertEqual("0.3.4", state["version"])

    def test_install_aborts_before_writing_when_conflict_exists(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (target / ".codex/hooks/pwf/session_start.py").write_text("print('custom')\n", encoding="utf-8")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(),
                legacy_hook_commands=(),
            )
            result = module.install(source, target, manifest, version="0.3.4", dry_run=False)
            self.assertEqual(2, result.exit_code)
            self.assertEqual("print('custom')\n", (target / ".codex/hooks/pwf/session_start.py").read_text(encoding="utf-8"))
            self.assertFalse((target / ".codex/pwf-install-state.json").exists())
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_installer -v
```

Expected: fail because `install` is not implemented.

- [ ] **Step 3: Add result model and backup helpers**

Add:

```python
@dataclass(frozen=True)
class InstallResult:
    exit_code: int
    operations: tuple[FileOperation, ...]
    messages: tuple[str, ...]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_path(target_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return target_root / ".codex" / "backups" / f"pwf-install-{stamp}"


def copy_with_backup(op: FileOperation, backup_root: Path | None) -> None:
    if op.target.exists() and backup_root is not None:
        backup_file = backup_root / op.relative_target
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(op.target, backup_file)
    op.target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(op.source, op.target)
```

- [ ] **Step 4: Add state writer**

Add:

```python
def write_install_state(target_root: Path, manifest: Manifest, version: str, installed_files: Iterable[str]) -> None:
    files = []
    for rel in sorted(installed_files):
        path = target_root / rel
        if path.is_file():
            files.append({"path": rel, "sha256": sha256_file(path)})
    hooks = []
    for entry in manifest.hook_entries:
        item: dict[str, Any] = {"event": entry.event, "command": entry.command}
        if entry.matcher is not None:
            item["matcher"] = entry.matcher
        hooks.append(item)
    state = {
        "schema": 1,
        "package": manifest.package,
        "version": version,
        "installed_at": utc_timestamp(),
        "files": files,
        "hooks": hooks,
    }
    state_path = target_root / ".codex" / "pwf-install-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
```

- [ ] **Step 5: Implement install transaction**

Add:

```python
def load_hooks_json(target_root: Path) -> dict[str, Any]:
    path = target_root / ".codex" / "hooks.json"
    if not path.exists():
        return {"hooks": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"hooks.json is invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("hooks.json root must be an object")
    return raw


def install(
    source_root: Path,
    target_root: Path,
    manifest: Manifest,
    *,
    version: str,
    dry_run: bool = False,
    force_owned: bool = False,
) -> InstallResult:
    state = read_install_state(target_root)
    owned_files = expand_owned_files(source_root, manifest)
    operations = tuple(
        plan_file_operation(source_root, target_root, owned, state, force_owned=force_owned)
        for owned in owned_files
    )
    conflicts = [op for op in operations if op.action == "conflict"]
    messages = [f"{op.action}: {op.relative_target} ({op.reason})" for op in operations]
    if conflicts:
        return InstallResult(2, operations, tuple(messages))

    try:
        hooks_json = load_hooks_json(target_root)
        merged_hooks, hooks_changed = merge_hooks_json(hooks_json, manifest)
    except ValueError as exc:
        return InstallResult(2, operations, tuple(messages + [str(exc)]))

    if dry_run:
        if hooks_changed:
            messages.append("merge: .codex/hooks.json")
        return InstallResult(0, operations, tuple(messages))

    backup_root = backup_path(target_root)
    backup_needed = hooks_changed or any(op.action == "overwrite" for op in operations)
    if backup_needed:
        backup_root.mkdir(parents=True, exist_ok=True)

    for op in operations:
        if op.action in {"copy", "overwrite"}:
            copy_with_backup(op, backup_root if op.action == "overwrite" else None)

    hooks_path = target_root / ".codex" / "hooks.json"
    if hooks_changed:
        if hooks_path.exists():
            backup_file = backup_root / ".codex" / "hooks.json"
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hooks_path, backup_file)
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        hooks_path.write_text(json.dumps(merged_hooks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    write_install_state(target_root, manifest, version, (owned.target for owned in owned_files))
    return InstallResult(0, operations, tuple(messages))
```

- [ ] **Step 6: Run focused tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: installer apply tests pass.

- [ ] **Step 7: Commit**

```powershell
git add installer/pwf_install.py tests/test_installer.py
git commit -m "feat: install pwf files without overwriting conflicts"
```

## Task 5: Implement Uninstall

**Files:**

- Modify: `installer/pwf_install.py`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Add uninstall tests**

Add tests:

```python
class InstallerUninstallTests(unittest.TestCase):
    def test_uninstall_removes_only_state_owned_files_and_hooks(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as target_dir:
            target = Path(target_dir)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/custom.py").write_text("print('custom')\n", encoding="utf-8")
            owned_file = target / ".codex/hooks/pwf/session_start.py"
            owned_file.write_text("print('pwf')\n", encoding="utf-8")
            hooks = {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "python .codex/hooks/pwf/session_start.py"}]},
                        {"hooks": [{"type": "command", "command": "python .codex/hooks/custom.py"}]},
                    ]
                }
            }
            (target / ".codex/hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
            state = {
                "schema": 1,
                "package": "HelsincyPlanWithFiles",
                "version": "0.3.4",
                "installed_at": "2026-06-25T15:00:00Z",
                "files": [{"path": ".codex/hooks/pwf/session_start.py", "sha256": module.sha256_file(owned_file)}],
                "hooks": [{"event": "SessionStart", "command": "python .codex/hooks/pwf/session_start.py"}],
            }
            (target / ".codex/pwf-install-state.json").write_text(json.dumps(state), encoding="utf-8")
            result = module.uninstall(target, dry_run=False)
            self.assertEqual(0, result.exit_code)
            self.assertFalse(owned_file.exists())
            self.assertTrue((target / ".codex/hooks/custom.py").exists())
            merged = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
            commands = [
                hook["command"]
                for group in merged["hooks"]["SessionStart"]
                for hook in group.get("hooks", [])
            ]
            self.assertEqual(["python .codex/hooks/custom.py"], commands)
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_installer -v
```

Expected: fail because `uninstall` is not implemented.

- [ ] **Step 3: Implement hook removal**

Add:

```python
def remove_state_hooks(existing: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    merged = json.loads(json.dumps(existing))
    hooks = merged.get("hooks", {})
    if not isinstance(hooks, dict):
        return merged, False
    changed = False
    commands_by_event: dict[str, set[str]] = {}
    for item in state.get("hooks", []):
        event = item.get("event")
        command = item.get("command")
        if isinstance(event, str) and isinstance(command, str):
            commands_by_event.setdefault(event, set()).add(normalize_command(command))
    for event, commands in commands_by_event.items():
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            continue
        new_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                new_groups.append(group)
                continue
            kept = [
                hook
                for hook in group["hooks"]
                if not (isinstance(hook, dict) and normalize_command(str(hook.get("command", ""))) in commands)
            ]
            if kept:
                updated = dict(group)
                updated["hooks"] = kept
                new_groups.append(updated)
            elif group["hooks"]:
                changed = True
        if new_groups != groups:
            changed = True
            hooks[event] = new_groups
    return merged, changed
```

- [ ] **Step 4: Implement safe uninstall**

Add:

```python
def _safe_relative_target(target_root: Path, rel_path: str) -> Path:
    rel = _require_relative(rel_path, "state path")
    path = (target_root / rel).resolve()
    root = target_root.resolve()
    if root != path and root not in path.parents:
        raise ValueError(f"state path escapes target root: {rel_path}")
    return path


def uninstall(target_root: Path, *, dry_run: bool = False) -> InstallResult:
    state = read_install_state(target_root)
    if not state:
        return InstallResult(0, (), ("no PWF install state found",))
    messages: list[str] = []
    operations: list[FileOperation] = []
    for item in state.get("files", []):
        rel = item.get("path")
        expected_hash = item.get("sha256")
        if not isinstance(rel, str) or not isinstance(expected_hash, str):
            continue
        path = _safe_relative_target(target_root, rel)
        if not path.exists():
            messages.append(f"skip missing: {rel}")
            continue
        if sha256_file(path) != expected_hash:
            messages.append(f"conflict modified: {rel}")
            return InstallResult(2, tuple(operations), tuple(messages))
        operations.append(FileOperation("delete", path, path, rel, "state-owned file hash matches"))

    try:
        hooks_json = load_hooks_json(target_root)
    except ValueError as exc:
        return InstallResult(2, tuple(operations), (str(exc),))
    merged_hooks, hooks_changed = remove_state_hooks(hooks_json, state)

    if dry_run:
        return InstallResult(0, tuple(operations), tuple(messages + [f"delete: {op.relative_target}" for op in operations]))

    backup_root = backup_path(target_root)
    if hooks_changed:
        backup_root.mkdir(parents=True, exist_ok=True)
        hooks_path = target_root / ".codex" / "hooks.json"
        if hooks_path.exists():
            backup_file = backup_root / ".codex" / "hooks.json"
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hooks_path, backup_file)
        hooks_path.write_text(json.dumps(merged_hooks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for op in operations:
        op.target.unlink()
    state_path = target_root / ".codex" / "pwf-install-state.json"
    if state_path.exists():
        state_path.unlink()
    return InstallResult(0, tuple(operations), tuple(messages))
```

- [ ] **Step 5: Run focused tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: uninstall tests pass.

- [ ] **Step 6: Commit**

```powershell
git add installer/pwf_install.py tests/test_installer.py
git commit -m "feat: uninstall pwf-owned files safely"
```

## Task 6: Add Installer CLI and Wrappers

**Files:**

- Modify: `installer/pwf_install.py`
- Create: `install-pwf.ps1`
- Create: `install-pwf.sh`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Add CLI smoke tests**

Add tests:

```python
class InstallerCliTests(unittest.TestCase):
    def test_cli_dry_run_returns_zero(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            (source / "installer").mkdir(parents=True)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (source / "VERSION").write_text("0.3.4\n", encoding="utf-8")
            (source / "installer/pwf_install_manifest.json").write_text(json.dumps({
                "schema": 1,
                "package": "HelsincyPlanWithFiles",
                "owned_files": [
                    {"source": ".codex/hooks/pwf/session_start.py", "target": ".codex/hooks/pwf/session_start.py", "kind": "hook"}
                ],
                "owned_directory_globs": [],
                "hook_entries": [
                    {"event": "SessionStart", "command": "python .codex/hooks/pwf/session_start.py"}
                ],
                "legacy_hook_commands": []
            }), encoding="utf-8")
            result = module.main(["install", "--source", str(source), "--target", target_dir, "--dry-run"])
            self.assertEqual(0, result)

    def test_cli_rejects_missing_target_argument(self):
        module = load_installer()
        result = module.main(["install"])
        self.assertEqual(2, result)
```

- [ ] **Step 2: Implement CLI parser**

Add:

```python
def default_source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_version(source_root: Path) -> str:
    version_path = source_root / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "0.0.0"


def print_result(result: InstallResult) -> None:
    for message in result.messages:
        print(message)
    if result.exit_code == 0:
        print("PWF installer completed.")
    else:
        print("PWF installer stopped because conflicts were found.", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Helsincy Plan With Files into a project without overwriting unrelated .codex files.")
    sub = parser.add_subparsers(dest="command", required=True)
    install_cmd = sub.add_parser("install")
    install_cmd.add_argument("--target", required=True, help="Target project root")
    install_cmd.add_argument("--source", default=None, help="Installer package root; defaults to this script's package")
    install_cmd.add_argument("--dry-run", action="store_true")
    install_cmd.add_argument("--force-owned", action="store_true")
    uninstall_cmd = sub.add_parser("uninstall")
    uninstall_cmd.add_argument("--target", required=True, help="Target project root")
    uninstall_cmd.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if args.command == "install":
        source_root = Path(args.source).resolve() if args.source else default_source_root()
        target_root = Path(args.target).resolve()
        manifest = load_manifest(source_root / "installer" / "pwf_install_manifest.json")
        result = install(
            source_root,
            target_root,
            manifest,
            version=read_version(source_root),
            dry_run=args.dry_run,
            force_owned=args.force_owned,
        )
        print_result(result)
        return result.exit_code
    if args.command == "uninstall":
        target_root = Path(args.target).resolve()
        result = uninstall(target_root, dry_run=args.dry_run)
        print_result(result)
        return result.exit_code
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Create PowerShell wrapper**

Create `install-pwf.ps1`:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath,

    [switch]$DryRun,

    [switch]$ForceOwned,

    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $ScriptRoot "installer\pwf_install.py"

$argsList = @()
if ($Uninstall) {
    $argsList += "uninstall"
} else {
    $argsList += "install"
}
$argsList += "--target"
$argsList += $TargetPath
if ($DryRun) { $argsList += "--dry-run" }
if ($ForceOwned -and -not $Uninstall) { $argsList += "--force-owned" }

python $Installer @argsList
exit $LASTEXITCODE
```

- [ ] **Step 4: Create POSIX wrapper**

Create `install-pwf.sh`:

```bash
#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python
fi

case "${1:-}" in
  install|uninstall)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/installer/pwf_install.py" "$@"
    ;;
  *)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/installer/pwf_install.py" install "$@"
    ;;
esac
```

- [ ] **Step 5: Run focused tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: CLI tests pass.

- [ ] **Step 6: Commit**

```powershell
git add installer/pwf_install.py install-pwf.ps1 install-pwf.sh tests/test_installer.py
git commit -m "feat: add safe installer command wrappers"
```

## Task 7: Namespace Hook Entry Points

**Files:**

- Create: `.codex/hooks/pwf/*.py`
- Modify: `.codex/hooks/*.py`
- Modify: `.codex/hooks.json`
- Test: `tests/test_hooks.py`
- Test: `tests/test_project_consistency.py`

- [ ] **Step 1: Add consistency tests for namespaced hooks**

In `tests/test_project_consistency.py`, update `test_hooks_json_references_existing_hook_files` so it recognizes nested PWF hook paths:

```python
referenced.extend(re.findall(r"\.codex/hooks/(?:pwf/)?[A-Za-z0-9_]+\.py", command))
```

Add:

```python
def test_hooks_json_uses_namespaced_pwf_hooks(self):
    hooks = json.loads(read_text(".codex/hooks.json"))
    commands = []
    for groups in hooks["hooks"].values():
        for group in groups:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                if "planning context" in hook.get("statusMessage", "") or ".codex/hooks/" in command:
                    commands.append(command)
    self.assertTrue(commands)
    self.assertTrue(all(".codex/hooks/pwf/" in command for command in commands))
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: fail because `hooks.json` still points at top-level hook scripts.

- [ ] **Step 3: Move current hook modules to namespaced directory**

For each current Python file:

```text
.codex/hooks/session_start.py
.codex/hooks/user_prompt_submit.py
.codex/hooks/pre_tool_use.py
.codex/hooks/post_tool_use.py
.codex/hooks/pre_compact.py
.codex/hooks/stop.py
.codex/hooks/codex_hook_adapter.py
.codex/hooks/planning_state.py
```

Create the corresponding file under `.codex/hooks/pwf/` with the current implementation.

- [ ] **Step 4: Replace top-level entrypoints with wrappers**

For each top-level entrypoint file such as `.codex/hooks/session_start.py`, replace content with:

```python
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "pwf" / "session_start.py"), run_name="__main__")
```

Use the matching target filename for each wrapper.

For top-level shared modules `.codex/hooks/codex_hook_adapter.py` and `.codex/hooks/planning_state.py`, keep compatibility imports:

```python
from __future__ import annotations

from pwf.codex_hook_adapter import *  # noqa: F401,F403
```

```python
from __future__ import annotations

from pwf.planning_state import *  # noqa: F401,F403
```

Create an empty `.codex/hooks/pwf/__init__.py` and include it in the manifest so the top-level compatibility modules can import `pwf.codex_hook_adapter` and `pwf.planning_state` on every supported Python version.

- [ ] **Step 5: Update internal imports**

Inside namespaced hook scripts, imports should prefer same-directory modules:

```python
import codex_hook_adapter as adapter
import planning_state
```

Because Python places the script directory on `sys.path`, this resolves to `.codex/hooks/pwf/`.

- [ ] **Step 6: Update `.codex/hooks.json`**

Change commands to:

```json
"command": "python .codex/hooks/pwf/session_start.py"
```

Do the same for `user_prompt_submit.py`, `pre_tool_use.py`, `post_tool_use.py`, `pre_compact.py`, and `stop.py`.

- [ ] **Step 7: Update hook tests**

In `tests/test_hooks.py`, update `run_hook_script` to prefer the namespaced path:

```python
script = REPO_ROOT / ".codex" / "hooks" / "pwf" / script_name
```

Keep a compatibility test that the top-level wrapper still works:

```python
def test_legacy_hook_wrapper_delegates_to_namespaced_hook(self):
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / ".codex" / "hooks" / "user_prompt_submit.py")],
        input=json.dumps({"cwd": str(REPO_ROOT), "hook_event_name": "UserPromptSubmit", "prompt": "status"}),
        text=True,
        capture_output=True,
    )
    self.assertEqual(0, result.returncode)
```

- [ ] **Step 8: Run hook and consistency tests**

```powershell
python -m unittest tests.test_hooks tests.test_project_consistency -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```powershell
git add .codex/hooks .codex/hooks.json tests/test_hooks.py tests/test_project_consistency.py
git commit -m "feat: namespace pwf hook entrypoints"
```

## Task 8: Extend Doctor Diagnostics

**Files:**

- Modify: `.codex/skills/planning-with-files/scripts/plan.py`
- Test: `tests/test_plan_doctor.py`

- [ ] **Step 1: Add doctor tests**

Add tests:

```python
def test_doctor_accepts_namespaced_hook_paths(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_basic_plan(root)
        write_hooks(root, hooks_json={
            "hooks": {
                "SessionStart": [{"hooks": [{"command": "python .codex/hooks/pwf/session_start.py"}]}],
                "UserPromptSubmit": [{"hooks": [{"command": "python .codex/hooks/pwf/user_prompt_submit.py"}]}],
                "PreToolUse": [{"hooks": [{"command": "python .codex/hooks/pwf/pre_tool_use.py"}]}],
                "PostToolUse": [{"hooks": [{"command": "python .codex/hooks/pwf/post_tool_use.py"}]}],
                "PreCompact": [{"hooks": [{"command": "python .codex/hooks/pwf/pre_compact.py"}]}],
                "Stop": [{"hooks": [{"command": "python .codex/hooks/pwf/stop.py"}]}],
            }
        }, hook_files={
            ".codex/hooks/pwf/session_start.py": "",
            ".codex/hooks/pwf/user_prompt_submit.py": "",
            ".codex/hooks/pwf/pre_tool_use.py": "",
            ".codex/hooks/pwf/post_tool_use.py": "",
            ".codex/hooks/pwf/pre_compact.py": "",
            ".codex/hooks/pwf/stop.py": "",
        })
        result = run_plan(root, "doctor")
        self.assertIn("hooks.json: ok", result.stdout)


def test_doctor_warns_about_legacy_hook_paths(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_basic_plan(root)
        write_hooks(root)
        result = run_plan(root, "doctor")
        self.assertIn("hook paths: warning legacy PWF hook paths detected", result.stdout)
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_plan_doctor -v
```

Expected: fail until doctor recognizes namespaced paths and legacy warnings.

- [ ] **Step 3: Update canonical hook path constants**

In `plan.py`, define:

```python
PWF_CANONICAL_HOOKS = {
    "SessionStart": ".codex/hooks/pwf/session_start.py",
    "UserPromptSubmit": ".codex/hooks/pwf/user_prompt_submit.py",
    "PreToolUse": ".codex/hooks/pwf/pre_tool_use.py",
    "PostToolUse": ".codex/hooks/pwf/post_tool_use.py",
    "PreCompact": ".codex/hooks/pwf/pre_compact.py",
    "Stop": ".codex/hooks/pwf/stop.py",
}

PWF_LEGACY_HOOKS = {
    "SessionStart": ".codex/hooks/session_start.py",
    "UserPromptSubmit": ".codex/hooks/user_prompt_submit.py",
    "PreToolUse": ".codex/hooks/pre_tool_use.py",
    "PostToolUse": ".codex/hooks/post_tool_use.py",
    "PreCompact": ".codex/hooks/pre_compact.py",
    "Stop": ".codex/hooks/stop.py",
}
```

- [ ] **Step 4: Update doctor hook validation**

Validation should:

- pass when canonical paths exist and are referenced;
- pass with warning when only legacy paths exist and are referenced;
- fail when neither canonical nor legacy path exists for a required event;
- keep existing Python runtime warnings such as `python3` command detection.

Doctor output line:

```text
hook paths: warning legacy PWF hook paths detected; run install-pwf to migrate hooks.json safely
```

- [ ] **Step 5: Add installer state diagnostics**

Doctor should read `.codex/pwf-install-state.json` if present:

```text
installer state: version 0.3.4, 42 files tracked
```

If absent:

```text
installer state: not found
```

Absence should be informational for existing manual installs, not a failure.

- [ ] **Step 6: Run doctor tests**

```powershell
python -m unittest tests.test_plan_doctor -v
```

Expected: doctor tests pass.

- [ ] **Step 7: Commit**

```powershell
git add .codex/skills/planning-with-files/scripts/plan.py tests/test_plan_doctor.py
git commit -m "feat: diagnose safe installer state"
```

## Task 9: Update Release Packaging

**Files:**

- Modify: `build-release.ps1`
- Test: `tests/test_project_consistency.py`

- [ ] **Step 1: Add release packaging consistency test**

In `tests/test_project_consistency.py`, add:

```python
def test_release_script_includes_safe_installer_files(self):
    script = read_text("build-release.ps1")
    self.assertIn("install-pwf.ps1", script)
    self.assertIn("install-pwf.sh", script)
    self.assertIn("installer", script)
```

- [ ] **Step 2: Run test and confirm failure**

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: fail because the release script does not include installer files explicitly.

- [ ] **Step 3: Update release description**

Change the `-codex.zip` description in `build-release.ps1` from:

```text
Install package: .codex/, docs/, README*, CHANGELOG, LICENSE, VERSION.
What an end user copies into their project.
```

to:

```text
Install package: installer, install wrappers, .codex payload, docs, README*, CHANGELOG, LICENSE, VERSION.
What an end user runs against their project.
```

- [ ] **Step 4: Include installer files**

Update `$IncludeCommon`:

```powershell
$IncludeCommon = @(
    "VERSION",
    "README.md",
    "README.en.md",
    "CHANGELOG.md",
    "LICENSE",
    "install-pwf.ps1",
    "install-pwf.sh"
)
```

Update `$IncludeDirsBoth`:

```powershell
$IncludeDirsBoth = @(
    ".codex",
    "docs",
    "installer"
)
```

- [ ] **Step 5: Run tests**

```powershell
python -m unittest tests.test_project_consistency -v
```

Expected: consistency tests pass.

- [ ] **Step 6: Build codex release smoke package**

```powershell
powershell -ExecutionPolicy RemoteSigned -File .\build-release.ps1 -Variant codex
```

Expected output includes one `HelsincyPlanWithFiles-v<version>-codex.zip`.

- [ ] **Step 7: Commit**

```powershell
git add build-release.ps1 tests/test_project_consistency.py
git commit -m "build: include safe installer in release packages"
```

## Task 10: Update Installation Documentation

**Files:**

- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/FAQ.md`
- Modify: `docs/USER_GUIDE.zh-CN.md`
- Modify: `docs/SOURCE_SAFETY_DISCLAIMER.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_project_consistency.py`
- Test: `tests/test_pwf_commands.py`

- [ ] **Step 1: Add docs consistency tests**

In `tests/test_project_consistency.py`, add:

```python
def test_readmes_document_safe_installer(self):
    readme_cn = read_text("README.md")
    readme_en = read_text("README.en.md")
    self.assertIn("install-pwf.ps1", readme_cn)
    self.assertIn("install-pwf.ps1", readme_en)
    self.assertIn("--dry-run", readme_cn)
    self.assertIn("--dry-run", readme_en)
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest tests.test_project_consistency tests.test_pwf_commands -v
```

Expected: fail until docs mention the safe installer.

- [ ] **Step 3: Update Chinese README install section**

Replace the Release install steps with:

```markdown
1. 打开 [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest)。
2. 下载 `HelsincyPlanWithFiles-v0.3.4-codex.zip`。
3. 解压到任意临时目录。
4. 先预览安装：

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project -DryRun
   ```

5. 如果 dry-run 没有报告 conflict，再执行安装：

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project
   ```

6. 重启 Codex，第一次提示信任 hook 时选择批准。
7. 在目标项目中运行 `/pwf-doctor` 检查安装状态。
```

Add conflict wording:

```markdown
安装器不会覆盖未知文件。如果目标项目已经有 `.codex/hooks.json`，安装器会解析 JSON 并追加 PWF hook；如果发现未知同名文件或无效 JSON，会停止并报告 conflict。需要升级已安装的 PWF 文件时，安装器只会覆盖 install-state 记录且 hash 未被本地修改的文件。
```

- [ ] **Step 4: Update English README install section**

Use the same structure:

```markdown
1. Open the [Latest Release](https://github.com/TheLostRiver/HelsincyPlanWithFiles/releases/latest).
2. Download `HelsincyPlanWithFiles-v0.3.4-codex.zip`.
3. Extract it to a temporary directory.
4. Preview the install:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project -DryRun
   ```

5. If dry-run reports no conflicts, install:

   ```powershell
   .\install-pwf.ps1 -TargetPath C:\path\to\your-project
   ```

6. Restart Codex and approve hooks when prompted.
7. Run `/pwf-doctor` inside the target project.
```

- [ ] **Step 5: Update FAQ and user guide**

FAQ must answer:

```markdown
### 我的项目已经有 `.codex/`，还能安装吗？

可以。请使用 `install-pwf.ps1 -DryRun` 先预览。安装器会合并 `hooks.json`，不会覆盖未知文件；如果存在同名未知文件或无效 `hooks.json`，它会停止并报告 conflict。
```

User guide must replace "copy `.codex/`" with "run installer".

- [ ] **Step 6: Update source safety disclaimer**

Add:

```markdown
当前推荐安装方式是运行 release 包里的 installer。installer 的默认策略是冲突即停止：它不会递归覆盖目标项目的 `.codex/`，也不会把已有 `hooks.json` 整文件替换掉。手动复制 `.codex/` 仍然属于用户或外部文件管理工具执行的操作，不是本项目运行时自动行为。
```

- [ ] **Step 7: Update changelog**

Under `Unreleased`, add bilingual entries:

```markdown
- 中文：新增 manifest 驱动的安全安装器，默认合并 `.codex/hooks.json`、记录 `.codex/pwf-install-state.json`，并在遇到未知同名文件时停止，避免直接复制 `.codex/` 覆盖项目已有配置。
- English: Added a manifest-driven safe installer that merges `.codex/hooks.json`, records `.codex/pwf-install-state.json`, and stops on unknown same-path files so users no longer need to copy `.codex/` over existing project configuration.
```

- [ ] **Step 8: Run docs tests**

```powershell
python -m unittest tests.test_project_consistency tests.test_pwf_commands -v
```

Expected: tests pass.

- [ ] **Step 9: Commit**

```powershell
git add README.md README.en.md docs/FAQ.md docs/USER_GUIDE.zh-CN.md docs/SOURCE_SAFETY_DISCLAIMER.md CHANGELOG.md tests/test_project_consistency.py
git commit -m "docs: document safe pwf installer"
```

## Task 11: Full Verification

**Files:**

- No planned source changes.

- [ ] **Step 1: Run installer tests**

```powershell
python -m unittest tests.test_installer -v
```

Expected: all installer tests pass.

- [ ] **Step 2: Run hook tests**

```powershell
python -m unittest tests.test_hooks -v
```

Expected: all hook tests pass.

- [ ] **Step 3: Run doctor tests**

```powershell
python -m unittest tests.test_plan_doctor -v
```

Expected: all doctor tests pass.

- [ ] **Step 4: Run command and consistency tests**

```powershell
python -m unittest tests.test_pwf_commands tests.test_project_consistency -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full suite**

```powershell
python -m unittest discover tests -v
```

Expected: full suite passes.

- [ ] **Step 6: Manual dry-run smoke**

Create a temporary target with an existing custom hook:

```powershell
$tmp = Join-Path $env:TEMP "pwf-install-smoke"
Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Join-Path $tmp ".codex\hooks") -Force | Out-Null
@'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {"type": "command", "command": "python .codex/hooks/custom.py"}
        ]
      }
    ]
  }
}
'@ | Set-Content -Path (Join-Path $tmp ".codex\hooks.json") -Encoding UTF8
Set-Content -Path (Join-Path $tmp ".codex\hooks\custom.py") -Value "print('custom')" -Encoding UTF8
.\install-pwf.ps1 -TargetPath $tmp -DryRun
```

Expected: dry-run reports copy/merge operations and does not modify `$tmp`.

- [ ] **Step 7: Manual install smoke**

```powershell
.\install-pwf.ps1 -TargetPath $tmp
python .codex\skills\planning-with-files\scripts\plan.py --root $tmp doctor
```

Expected:

- `.codex/hooks/custom.py` still exists.
- `.codex/hooks.json` contains both custom hook and PWF hook.
- `.codex/pwf-install-state.json` exists.
- doctor reports namespaced hooks as valid.

- [ ] **Step 8: Manual uninstall smoke**

```powershell
.\install-pwf.ps1 -TargetPath $tmp -Uninstall
```

Expected:

- PWF state-owned files are removed.
- `.codex/hooks/custom.py` remains.
- `.codex/hooks.json` no longer contains PWF commands.
- `.planning/` is not removed.

- [ ] **Step 9: Build release smoke**

```powershell
powershell -ExecutionPolicy RemoteSigned -File .\build-release.ps1 -Variant both
```

Expected: both zip files are built and include:

- `install-pwf.ps1`
- `install-pwf.sh`
- `installer/pwf_install.py`
- `installer/pwf_install_manifest.json`
- `.codex/hooks/pwf/*.py`
- `.codex/skills/planning-with-files/scripts/plan.py`

## Acceptance Criteria

- Users no longer need to copy `.codex/` into a target project for normal installation.
- Installer dry-run can show all writes before they happen.
- Installer refuses unknown same-path files.
- Installer preserves existing non-PWF hooks in `.codex/hooks.json`.
- Installer dedupes current PWF hook entries.
- Installer migrates known legacy PWF hook commands to namespaced hook commands.
- Installer writes `.codex/pwf-install-state.json` with relative paths and hashes.
- Installer uninstall removes only state-owned files whose hash still matches.
- Doctor accepts namespaced hooks and warns about legacy PWF hook paths.
- Release packages include installer files.
- README, FAQ, user guide, source safety disclaimer, and changelog describe the safer install path.

## Execution Handoff

Plan complete when this file is committed. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batching work with checkpoints.
