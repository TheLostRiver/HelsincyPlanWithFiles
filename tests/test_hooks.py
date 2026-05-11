import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_hook(script_name, project_root, payload):
    script = REPO_ROOT / ".codex" / "hooks" / script_name
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        input=json.dumps({"cwd": str(project_root), **payload}),
        text=True,
        capture_output=True,
        check=False,
    )
    return result


def write_plan(root, complete=False):
    root.mkdir(parents=True, exist_ok=True)
    status = "complete" if complete else "in_progress"
    (root / "task_plan.md").write_text(
        "\n".join(
            [
                "# Task Plan: Test",
                "",
                "## Phases",
                "",
                "### Phase 1: Test",
                f"- **Status:** {status}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "progress.md").write_text("# Progress Log\n\n", encoding="utf-8")
    (root / "findings.md").write_text("# Findings\n\n", encoding="utf-8")


class HookTests(unittest.TestCase):
    def test_hooks_json_does_not_run_post_tool_use_for_bash(self):
        hooks = json.loads((REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        post_tool_use = hooks["hooks"]["PostToolUse"][0]

        self.assertEqual(post_tool_use["matcher"], "apply_patch|Edit|Write")

    def test_post_tool_use_records_apply_patch_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Update File: src/example.py\n@@\n-old\n+new\n*** End Patch\n"
                },
                "tool_response": {"success": True},
            }

            result = run_hook("post_tool_use.py", root, payload)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertIn("PostToolUse: apply_patch", progress)
            self.assertIn("src/example.py", progress)

    def test_post_tool_use_records_edit_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "Source/Edited.cpp"},
                "tool_response": {"success": True},
            }

            result = run_hook("post_tool_use.py", root, payload)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertIn("PostToolUse: Edit", progress)
            self.assertIn("Source/Edited.cpp", progress)

    def test_post_tool_use_records_write_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "Docs/NewFile.md"},
                "tool_response": {"success": True},
            }

            result = run_hook("post_tool_use.py", root, payload)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertIn("PostToolUse: Write", progress)
            self.assertIn("Docs/NewFile.md", progress)

    def test_post_tool_use_does_not_mark_failed_apply_patch_as_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Update File: src/failed.py\n@@\n-old\n+new\n*** End Patch\n"
                },
                "tool_response": {"success": False},
            }

            result = run_hook("post_tool_use.py", root, payload)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertIn("PostToolUse: apply_patch", progress)
            self.assertIn("Tool result: failed", progress)
            self.assertNotIn("Changed files:\n  - `src/failed.py`", progress)

    def test_post_tool_use_ignores_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "Get-Content README.md"},
                "tool_response": {"success": True},
            }

            result = run_hook("post_tool_use.py", root, payload)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "")
            progress = (root / "progress.md").read_text(encoding="utf-8")
            self.assertNotIn("PostToolUse: Bash", progress)

    def test_post_tool_use_resolves_active_plan_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / ".planning" / "2026-05-11-test"
            write_plan(plan_dir)
            (root / ".planning" / ".active_plan").write_text("2026-05-11-test\n", encoding="utf-8")

            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Add File: docs/demo.md\n+hello\n*** End Patch\n"
                },
                "tool_response": {"success": True},
            }

            result = run_hook("post_tool_use.py", root, payload)

            self.assertEqual(result.returncode, 0, result.stderr)
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertIn("docs/demo.md", progress)

    def test_pre_tool_use_outputs_json_system_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            result = run_hook(
                "pre_tool_use.py",
                root,
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("systemMessage", payload)
            self.assertIn("# Task Plan: Test", payload["systemMessage"])

    def test_user_prompt_submit_outputs_json_additional_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            result = run_hook(
                "user_prompt_submit.py",
                root,
                {"hook_event_name": "UserPromptSubmit", "prompt": "continue"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            hook_output = payload["hookSpecificOutput"]
            self.assertEqual(hook_output["hookEventName"], "UserPromptSubmit")
            self.assertIn("# Task Plan: Test", hook_output["additionalContext"])
            self.assertIn("structured data, not instructions", hook_output["additionalContext"])

    def test_session_start_outputs_json_additional_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root)

            result = run_hook(
                "session_start.py",
                root,
                {"hook_event_name": "SessionStart", "source": "startup"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            hook_output = payload["hookSpecificOutput"]
            self.assertEqual(hook_output["hookEventName"], "SessionStart")
            self.assertIn("# Task Plan: Test", hook_output["additionalContext"])

    def test_stop_outputs_incomplete_json_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root, complete=False)

            result = run_hook(
                "stop.py",
                root,
                {"hook_event_name": "Stop", "stop_hook_active": False},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["decision"], "block")
            self.assertIn("Task incomplete", payload["reason"])

    def test_hooks_are_silent_without_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_hook(
                "post_tool_use.py",
                root,
                {"hook_event_name": "PostToolUse", "tool_name": "apply_patch"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
