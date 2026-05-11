#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


CODEX_DIR = Path(__file__).resolve().parents[3]
HOOKS_DIR = CODEX_DIR / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import planning_state  # noqa: E402


REQUIRED_HOOK_ENTRYPOINTS = [
    ".codex/hooks/session_start.py",
    ".codex/hooks/user_prompt_submit.py",
    ".codex/hooks/pre_tool_use.py",
    ".codex/hooks/post_tool_use.py",
    ".codex/hooks/stop.py",
]


def _collect_hook_commands(value: Any) -> list[str]:
    commands: list[str] = []
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            commands.append(command)
        for child in value.values():
            commands.extend(_collect_hook_commands(child))
    elif isinstance(value, list):
        for child in value:
            commands.extend(_collect_hook_commands(child))
    return commands


def _load_hooks_json(root: Path) -> tuple[dict[str, Any] | None, str]:
    hooks_json = root / ".codex" / "hooks.json"
    if not hooks_json.is_file():
        return None, "missing"
    try:
        payload = json.loads(hooks_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "invalid"
    return payload if isinstance(payload, dict) else None, "ok"


def _uses_python3(command: str) -> bool:
    words = command.replace("\\", "/").split()
    return bool(words and words[0].endswith("python3"))


def _short_digest(value: str | None) -> str:
    return value[:12] if value else "unknown"


def _plan_id(root: Path, paths: planning_state.PlanningPaths) -> str:
    try:
        if paths.root.resolve() == root.resolve():
            return "legacy"
    except OSError:
        pass
    return paths.root.name


def _current_phase(paths: planning_state.PlanningPaths) -> str | None:
    if not paths.task_plan.is_file():
        return None
    lines = paths.task_plan.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "## Current Phase":
            continue
        for value in lines[index + 1 :]:
            candidate = value.strip()
            if candidate:
                return candidate
        return None
    return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "plan"


def _task_plan_template(name: str) -> str:
    return "\n".join(
        [
            f"# Task Plan: {name}",
            "",
            "## Goal",
            "Define the desired end state.",
            "",
            "## Current Phase",
            "Phase 1",
            "",
            "## Phases",
            "",
            "### Phase 1: Discovery",
            "- [ ] Confirm requirements",
            "- [ ] Record findings",
            "- **Status:** in_progress",
            "",
            "### Phase 2: Implementation",
            "- [ ] Make changes",
            "- [ ] Run verification",
            "- **Status:** pending",
            "",
            "## Decisions Made",
            "| Decision | Rationale |",
            "|----------|-----------|",
            "",
            "## Errors Encountered",
            "| Error | Resolution |",
            "|-------|------------|",
            "",
        ]
    )


def _progress_template() -> str:
    return "# Progress Log\n\n"


def _findings_template() -> str:
    return "# Findings\n\n"


def _planning_files_status(paths: planning_state.PlanningPaths | None) -> tuple[str, bool]:
    if paths is None:
        return "planning files: missing", False

    required = [
        paths.task_plan,
        paths.progress,
        paths.findings,
    ]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        return f"planning files: missing {', '.join(missing)}", False
    return "planning files: ok", True


def _attestation_status(root: Path, paths: planning_state.PlanningPaths | None) -> tuple[str, bool]:
    if paths is None:
        return "attestation: not checked", False

    status = planning_state.plan_attestation_status(root, paths)
    if status.valid is None:
        return "attestation: not set", True
    if status.valid:
        return f"attestation: ok sha256={_short_digest(status.actual)}", True
    return (
        "attestation: tampered "
        f"expected={_short_digest(status.expected)} actual={_short_digest(status.actual)}",
        False,
    )


def doctor(root: Path) -> int:
    lines: list[str] = []
    ok = True

    hooks_payload, hooks_status = _load_hooks_json(root)
    if hooks_status == "ok":
        lines.append("hooks.json: ok")
    else:
        lines.append(f"hooks.json: {hooks_status}")
        ok = False

    missing_hook_files = [
        path for path in REQUIRED_HOOK_ENTRYPOINTS if not (root / path).is_file()
    ]
    if missing_hook_files:
        lines.append(f"hook files: missing {', '.join(missing_hook_files)}")
        ok = False
    else:
        lines.append("hook files: ok")

    commands = _collect_hook_commands(hooks_payload) if hooks_payload is not None else []
    if any(_uses_python3(command) for command in commands):
        lines.append("python runtime: warning python3 command in hooks.json")
    else:
        lines.append("python runtime: ok")

    paths = planning_state.planning_paths(root)
    if paths is None:
        lines.append("active plan: missing")
        ok = False
    else:
        lines.append(f"active plan: ok {paths.root}")

    planning_line, planning_ok = _planning_files_status(paths)
    lines.append(planning_line)
    ok = ok and planning_ok

    attestation_line, attestation_ok = _attestation_status(root, paths)
    lines.append(attestation_line)
    ok = ok and attestation_ok

    print("\n".join(lines))
    return 0 if ok else 1


def status(root: Path) -> int:
    paths = planning_state.planning_paths(root)
    if paths is None:
        print("active plan: missing")
        print("planning files: missing")
        return 1

    print(f"active plan: {_plan_id(root, paths)}")
    print(f"path: {paths.root}")

    phase = _current_phase(paths)
    if phase:
        print(f"current phase: {phase}")

    counts = planning_state.phase_counts(root)
    if counts is not None:
        total, complete, _in_progress, _pending = counts
        print(f"phases: {complete}/{total} complete")

    planning_line, planning_ok = _planning_files_status(paths)
    print(planning_line)

    attestation_line, attestation_ok = _attestation_status(root, paths)
    print(attestation_line)
    return 0 if planning_ok and attestation_ok else 1


def init(root: Path, name: str, legacy: bool = False, force: bool = False) -> int:
    if legacy:
        target = root
        label = "legacy plan"
        plan_id = "legacy"
    else:
        plan_id = f"{datetime.now().strftime('%Y-%m-%d')}-{_slugify(name)}"
        target = root / ".planning" / plan_id
        label = "plan"

    existing = [target / "task_plan.md", target / "progress.md", target / "findings.md"]
    if any(path.exists() for path in existing) and not force:
        print(f"{label} already exists: {target}")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    (target / "task_plan.md").write_text(_task_plan_template(name), encoding="utf-8", newline="\n")
    (target / "progress.md").write_text(_progress_template(), encoding="utf-8", newline="\n")
    (target / "findings.md").write_text(_findings_template(), encoding="utf-8", newline="\n")

    if not legacy:
        active_file = root / ".planning" / ".active_plan"
        active_file.parent.mkdir(parents=True, exist_ok=True)
        active_file.write_text(plan_id, encoding="utf-8")

    print(f"created {label}: {plan_id}")
    print(f"path: {target}")
    return 0


def switch(root: Path, plan_id: str | None) -> int:
    plan_root = root / ".planning"
    active_file = plan_root / ".active_plan"

    if not plan_id:
        if active_file.is_file():
            active = active_file.read_text(encoding="utf-8", errors="replace").strip()
            print(f"active plan: {active}" if active else "no active plan set")
            return 0 if active else 1
        print("no active plan set")
        return 1

    plan_dir = plan_root / plan_id
    if not (plan_dir / "task_plan.md").is_file():
        print(f"plan directory not found: {plan_dir}")
        return 1

    active_file.parent.mkdir(parents=True, exist_ok=True)
    active_file.write_text(plan_id, encoding="utf-8")
    print(f"active plan set to: {plan_id}")
    print(f"path: {plan_dir}")
    return 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attest(root: Path, show: bool = False, clear: bool = False) -> int:
    paths = planning_state.planning_paths(root)
    if paths is None:
        print("[plan-attest] No task_plan.md found. Create a plan first.")
        return 1

    attestation = planning_state.attestation_path(root, paths)

    if show:
        if not attestation.is_file():
            print(f"[plan-attest] No attestation set for {paths.task_plan}.")
            return 1
        print(f"Plan: {paths.task_plan}")
        print(f"Attestation: {attestation}")
        print(f"SHA-256: {attestation.read_text(encoding='utf-8', errors='replace').strip()}")
        return 0

    if clear:
        if attestation.is_file():
            attestation.unlink()
            print(f"[plan-attest] Cleared attestation for {paths.task_plan}.")
        else:
            print("[plan-attest] No attestation to clear.")
        return 0

    digest = _sha256(paths.task_plan)
    attestation.write_text(digest, encoding="ascii")
    print(f"[plan-attest] Locked {paths.task_plan}")
    print(f"[plan-attest] SHA-256: {digest[:12]}... (stored in {attestation})")
    print("[plan-attest] Hooks will block injection if the file is modified without re-running this command.")
    return 0


def capture(root: Path, kind: str, source: str, summary: str, trust: str = "untrusted") -> int:
    paths = planning_state.planning_paths(root)
    if paths is None:
        print("No active plan found. Create or switch to a plan before capturing external context.")
        return 1

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = "\n".join(
        [
            "",
            f"## External Context: {timestamp}",
            "",
            "---BEGIN EXTERNAL CONTEXT DATA---",
            f"- Kind: {kind}",
            f"- Source: {source}",
            f"- Trust: {trust}",
            f"- Summary: {summary}",
            "---END EXTERNAL CONTEXT DATA---",
            "",
        ]
    )
    paths.findings.parent.mkdir(parents=True, exist_ok=True)
    with paths.findings.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)

    print(f"captured external context: {kind}")
    print(f"findings: {paths.findings}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan.py")
    parser.add_argument("--root", default=".", help="Project root to inspect")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Diagnose hooks, active plan, and attestation")
    subparsers.add_parser("status", help="Show active plan status")

    init_parser = subparsers.add_parser("init", help="Create a new planning session")
    init_parser.add_argument("name")
    init_parser.add_argument("--legacy", action="store_true", help="Create root-level planning files")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing planning files")

    switch_parser = subparsers.add_parser("switch", help="Set or show active plan")
    switch_parser.add_argument("plan_id", nargs="?")

    attest_parser = subparsers.add_parser("attest", help="Lock, show, or clear plan attestation")
    attest_group = attest_parser.add_mutually_exclusive_group()
    attest_group.add_argument("--show", action="store_true")
    attest_group.add_argument("--clear", action="store_true")

    capture_parser = subparsers.add_parser("capture", help="Append external context to findings.md")
    capture_parser.add_argument("--kind", required=True, choices=["web", "browser", "image", "pdf", "file", "note"])
    capture_parser.add_argument("--source", required=True)
    capture_parser.add_argument("--summary", required=True)
    capture_parser.add_argument("--trust", default="untrusted")

    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve()

    if args.command == "doctor":
        return doctor(root)
    if args.command == "status":
        return status(root)
    if args.command == "init":
        return init(root, args.name, legacy=args.legacy, force=args.force)
    if args.command == "switch":
        return switch(root, args.plan_id)
    if args.command == "attest":
        return attest(root, show=args.show, clear=args.clear)
    if args.command == "capture":
        return capture(root, args.kind, args.source, args.summary, trust=args.trust)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
