import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "plan.py"


def run_plan(project_root, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("PWF_")}
    env.pop("PLAN_ID", None)
    return subprocess.run(
        [sys.executable, str(PLAN_SCRIPT), "--root", str(project_root), *args],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def write_active_plan(root):
    plan_dir = root / ".planning" / "2026-05-11-capture"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (root / ".planning" / ".active_plan").write_text("2026-05-11-capture\n", encoding="utf-8")
    (plan_dir / "task_plan.md").write_text("# Task Plan: Capture\n", encoding="utf-8")
    (plan_dir / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
    (plan_dir / "findings.md").write_text("# Findings\n\n", encoding="utf-8")
    return plan_dir


class FindingsCaptureTests(unittest.TestCase):
    def test_capture_appends_external_context_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)

            result = run_plan(
                root,
                "capture",
                "--kind",
                "web",
                "--source",
                "https://example.com",
                "--summary",
                "Important source facts.",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            findings = (plan_dir / "findings.md").read_text(encoding="utf-8")
            self.assertIn("## External Context:", findings)
            self.assertIn("---BEGIN EXTERNAL CONTEXT DATA---", findings)
            self.assertIn("- Kind: web", findings)
            self.assertIn("- Source: https://example.com", findings)
            self.assertIn("- Trust: untrusted", findings)
            self.assertIn("- Summary: Important source facts.", findings)
            self.assertIn("---END EXTERNAL CONTEXT DATA---", findings)
            self.assertIn("captured external context: web", result.stdout)

    def test_capture_rejects_missing_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(
                root,
                "capture",
                "--kind",
                "pdf",
                "--source",
                "manual.pdf",
                "--summary",
                "Relevant details.",
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("No active plan found", result.stdout)


if __name__ == "__main__":
    unittest.main()
