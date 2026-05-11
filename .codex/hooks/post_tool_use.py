#!/usr/bin/env python3
from __future__ import annotations

import codex_hook_adapter as adapter
import planning_state


def main() -> None:
    payload = adapter.load_payload()
    root = adapter.cwd_from_payload(payload)

    if not adapter.is_session_attached(root, adapter.session_id_from_payload(payload)):
        return

    if planning_state.append_progress(root, payload):
        adapter.emit_json(
            {
                "systemMessage": (
                    "[planning-with-files] Recorded PostToolUse context in progress.md. "
                    "If a phase is now complete, update task_plan.md status."
                )
            }
        )


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
