#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import codex_hook_adapter as adapter
import planning_state


def _run_session_catchup(root: Path, planning_dir: Path | None) -> str:
    hook_dir = Path(__file__).resolve().parent
    skill_dir = hook_dir.parent / "skills" / "planning-with-files"
    script = skill_dir / "scripts" / "session-catchup.py"
    if not script.is_file():
        return ""

    command = [sys.executable, str(script), str(root)]
    if planning_dir is not None:
        command.extend(["--planning-dir", str(planning_dir)])

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip()


def main() -> None:
    payload = adapter.load_payload()
    root = adapter.cwd_from_payload(payload)

    session_id = adapter.session_id_from_payload(payload)
    if adapter.emit_session_denial_if_needed(root, session_id):
        return

    resolution = planning_state.resolve_planning_context(root, session_id=session_id)
    planning_dir = resolution.paths.root if resolution is not None else None
    parts = [
        _run_session_catchup(root, planning_dir),
        planning_state.render_prompt_context(root, session_id=session_id),
    ]
    output = "\n\n".join(part for part in parts if part)
    if output:
        adapter.emit_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": output,
                }
            }
        )


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
