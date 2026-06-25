from __future__ import annotations

import argparse
import json
import hashlib
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


@dataclass(frozen=True)
class FileOperation:
    action: str
    source: Path
    target: Path
    relative_target: str
    reason: str


@dataclass(frozen=True)
class InstallResult:
    exit_code: int
    operations: tuple[FileOperation, ...]
    messages: tuple[str, ...]


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
    legacy_entries = tuple(
        HookEntry(event=item["event"], command=item["command"])
        for item in raw.get("legacy_hook_commands", [])
    )
    return Manifest(
        schema=int(raw["schema"]),
        package=str(raw["package"]),
        owned_files=owned_files,
        owned_directory_globs=tuple(str(item) for item in raw.get("owned_directory_globs", [])),
        hook_entries=hook_entries,
        legacy_hook_commands=legacy_entries,
    )


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


def expand_owned_files(source_root: Path, manifest: Manifest) -> tuple[OwnedFile, ...]:
    files = list(manifest.owned_files)
    for pattern in manifest.owned_directory_globs:
        for path in source_root.glob(pattern):
            if not path.is_dir():
                continue
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                if "__pycache__" in child.parts or child.suffix == ".pyc":
                    continue
                rel = child.relative_to(source_root).as_posix()
                files.append(OwnedFile(rel, rel, "skill-wrapper"))

    deduped: dict[str, OwnedFile] = {}
    for item in files:
        deduped[item.target] = item
    return tuple(deduped[path] for path in sorted(deduped))


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
        filtered_groups: list[Any] = []

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
    messages = [f"{op.action}: {op.relative_target} ({op.reason})" for op in operations]
    conflicts = [op for op in operations if op.action == "conflict"]
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
                if not (
                    isinstance(hook, dict)
                    and normalize_command(str(hook.get("command", ""))) in commands
                )
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
        return InstallResult(
            0,
            tuple(operations),
            tuple(messages + [f"delete: {op.relative_target}" for op in operations]),
        )

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
    parser = argparse.ArgumentParser(
        description="Install Helsincy Plan With Files into a project without overwriting unrelated .codex files."
    )
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
