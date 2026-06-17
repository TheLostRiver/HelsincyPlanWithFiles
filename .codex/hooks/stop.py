#!/usr/bin/env python3
from __future__ import annotations

import codex_hook_adapter as adapter
import planning_state


def main() -> None:
    payload = adapter.load_payload()
    root = adapter.cwd_from_payload(payload)

    session_id = adapter.session_id_from_payload(payload)
    if adapter.emit_session_denial_if_needed(root, session_id):
        return

    message = planning_state.stop_message(root, session_id=session_id)
    if not message:
        return

    adapter.emit_json({"systemMessage": message})


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
