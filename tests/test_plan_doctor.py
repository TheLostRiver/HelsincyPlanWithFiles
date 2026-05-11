import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "plan.py"
REQUIRED_HOOKS = [
    "session_start.py",
    "user_prompt_submit.py",
    "pre_tool_use.py",
    "post_tool_use.py",
    "stop.py",
]


def run_plan(project_root, *args):
    env = dict(os.environ)
    env.pop("PLAN_ID", None)
    return subprocess.run(
        [sys.executable, str(PLAN_SCRIPT), "--root", str(project_root), *args],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def write_hooks(root, hooks_json=None, hook_files=None):
    hooks_dir = root / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for name in hook_files or REQUIRED_HOOKS:
        (hooks_dir / name).write_text("# hook\n", encoding="utf-8")

    if hooks_json is None:
        hooks_json = {
            "hooks": {
                "SessionStart": [{"hooks": [{"command": "python .codex/hooks/session_start.py"}]}],
                "UserPromptSubmit": [{"hooks": [{"command": "python .codex/hooks/user_prompt_submit.py"}]}],
                "PreToolUse": [{"hooks": [{"command": "python .codex/hooks/pre_tool_use.py"}]}],
                "PostToolUse": [{"hooks": [{"command": "python .codex/hooks/post_tool_use.py"}]}],
                "Stop": [{"hooks": [{"command": "python .codex/hooks/stop.py"}]}],
            }
        }
    (root / ".codex" / "hooks.json").write_text(
        json.dumps(hooks_json),
        encoding="utf-8",
    )


def write_active_plan(root):
    plan_dir = root / ".planning" / "2026-05-11-demo"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (root / ".planning" / ".active_plan").write_text("2026-05-11-demo\n", encoding="utf-8")
    (plan_dir / "task_plan.md").write_text("# Task Plan: Demo\n", encoding="utf-8")
    (plan_dir / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
    (plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")
    return plan_dir


class PlanDoctorTests(unittest.TestCase):
    def test_doctor_reports_healthy_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("hooks.json: ok", result.stdout)
            self.assertIn("hook files: ok", result.stdout)
            self.assertIn("active plan: ok", result.stdout)
            self.assertIn("planning files: ok", result.stdout)
            self.assertIn("attestation: not set", result.stdout)

    def test_doctor_reports_missing_hooks_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 1)
            self.assertIn("hooks.json: missing", result.stdout)

    def test_doctor_reports_invalid_hooks_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)
            hooks_dir = root / ".codex" / "hooks"
            hooks_dir.mkdir(parents=True)
            for name in REQUIRED_HOOKS:
                (hooks_dir / name).write_text("# hook\n", encoding="utf-8")
            (root / ".codex" / "hooks.json").write_text("{not json", encoding="utf-8")

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 1)
            self.assertIn("hooks.json: invalid", result.stdout)

    def test_doctor_reports_missing_hook_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)
            write_hooks(root, hook_files=[name for name in REQUIRED_HOOKS if name != "pre_tool_use.py"])

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 1)
            self.assertIn("hook files: missing .codex/hooks/pre_tool_use.py", result.stdout)

    def test_doctor_warns_about_python3_hook_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)
            hooks_json = {
                "hooks": {
                    "PreToolUse": [{"hooks": [{"command": "python3 .codex/hooks/pre_tool_use.py"}]}]
                }
            }
            write_hooks(root, hooks_json=hooks_json)

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("python runtime: warning python3 command in hooks.json", result.stdout)

    def test_doctor_reports_matching_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            digest = hashlib.sha256((plan_dir / "task_plan.md").read_bytes()).hexdigest()
            (plan_dir / ".attestation").write_text(digest, encoding="ascii")

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("attestation: ok", result.stdout)
            self.assertIn(digest[:12], result.stdout)

    def test_doctor_reports_tampered_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            actual = hashlib.sha256((plan_dir / "task_plan.md").read_bytes()).hexdigest()
            (plan_dir / ".attestation").write_text("0" * 64, encoding="ascii")

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 1)
            self.assertIn("attestation: tampered", result.stdout)
            self.assertIn("expected=000000000000", result.stdout)
            self.assertIn(f"actual={actual[:12]}", result.stdout)


if __name__ == "__main__":
    unittest.main()
