import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_hook(script_name, project_root, payload):
    script = REPO_ROOT / ".codex" / "hooks" / script_name
    env = dict(os.environ)
    env.pop("PWF_LOG_COMMAND", None)
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        input=json.dumps({"cwd": str(project_root), **payload}),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def write_plan(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "task_plan.md").write_text(
        "\n".join(
            [
                "# Task Plan: Progress Records",
                "",
                "## Current Phase",
                "Phase 1",
                "",
                "## Phases",
                "",
                "### Phase 1: Test",
                "- **Status:** in_progress",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "progress.md").write_text("# Progress Log\n\n", encoding="utf-8")
    (root / "findings.md").write_text("# Findings\n\n", encoding="utf-8")


class ProgressRecordTests(unittest.TestCase):
    def test_apply_patch_records_operation_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            result = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "apply_patch",
                    "tool_input": {
                        "command": "\n".join(
                            [
                                "*** Begin Patch",
                                "*** Add File: src/new.py",
                                "+print('new')",
                                "*** Update File: src/existing.py",
                                "@@",
                                "-old",
                                "+new",
                                "*** Delete File: src/old.py",
                                "*** End Patch",
                            ]
                        )
                    },
                    "tool_response": {"success": True},
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertIn("- `src/new.py` (add)", progress)
            self.assertIn("- `src/existing.py` (update)", progress)
            self.assertIn("- `src/old.py` (delete)", progress)

    def test_edit_and_write_record_tool_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            edit = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "Source/Edited.cpp"},
                    "tool_response": {"success": True},
                },
            )
            write = run_hook(
                "post_tool_use.py",
                root,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Write",
                    "tool_input": {"file_path": "Docs/NewFile.md"},
                    "tool_response": {"success": True},
                },
            )

            self.assertEqual(edit.returncode, 0, edit.stderr)
            self.assertEqual(write.returncode, 0, write.stderr)
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertIn("- `Source/Edited.cpp` (edit)", progress)
            self.assertIn("- `Docs/NewFile.md` (write)", progress)


if __name__ == "__main__":
    unittest.main()
