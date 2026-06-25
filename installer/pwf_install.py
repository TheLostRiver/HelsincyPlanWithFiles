from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


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
