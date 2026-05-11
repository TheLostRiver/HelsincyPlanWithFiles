import hashlib
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "plan.py"


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


def write_plan(plan_dir, title="Demo", current_phase="Phase 2"):
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "task_plan.md").write_text(
        "\n".join(
            [
                f"# Task Plan: {title}",
                "",
                "## Current Phase",
                current_phase,
                "",
                "## Phases",
                "",
                "### Phase 1: Done",
                "- **Status:** complete",
                "",
                "### Phase 2: Active",
                "- **Status:** in_progress",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plan_dir / "progress.md").write_text("# Progress Log\n", encoding="utf-8")
    (plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")


def write_active_plan(root, plan_id="2026-05-11-demo"):
    plan_dir = root / ".planning" / plan_id
    write_plan(plan_dir)
    (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
    return plan_dir


class PlanCliTests(unittest.TestCase):
    def test_status_reports_active_plan_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)

            result = run_plan(root, "status")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("active plan: 2026-05-11-demo", result.stdout)
            self.assertIn("current phase: Phase 2", result.stdout)
            self.assertIn("phases: 1/2 complete", result.stdout)
            self.assertIn("attestation: not set", result.stdout)

    def test_init_creates_active_planning_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "init", "Hook Security")

            self.assertEqual(result.returncode, 0, result.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-hook-security"
            plan_dir = root / ".planning" / plan_id
            self.assertTrue((plan_dir / "task_plan.md").is_file())
            self.assertTrue((plan_dir / "progress.md").is_file())
            self.assertTrue((plan_dir / "findings.md").is_file())
            self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), plan_id)
            self.assertIn(f"created plan: {plan_id}", result.stdout.lower())

    def test_init_refuses_existing_plan_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = run_plan(root, "init", "Hook Security")
            second = run_plan(root, "init", "Hook Security")
            third = run_plan(root, "init", "Hook Security", "--force")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1)
            self.assertIn("already exists", second.stdout)
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertIn("created plan:", third.stdout.lower())

    def test_init_legacy_creates_root_planning_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "init", "Legacy Task", "--legacy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "task_plan.md").is_file())
            self.assertTrue((root / "progress.md").is_file())
            self.assertTrue((root / "findings.md").is_file())
            self.assertIn("created legacy plan", result.stdout.lower())

    def test_switch_sets_and_prints_active_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root / ".planning" / "2026-05-11-a")
            write_plan(root / ".planning" / "2026-05-11-b")

            set_result = run_plan(root, "switch", "2026-05-11-b")
            show_result = run_plan(root, "switch")

            self.assertEqual(set_result.returncode, 0, set_result.stderr)
            self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), "2026-05-11-b")
            self.assertIn("active plan set to: 2026-05-11-b", set_result.stdout)
            self.assertEqual(show_result.returncode, 0, show_result.stderr)
            self.assertIn("active plan: 2026-05-11-b", show_result.stdout)

    def test_switch_rejects_missing_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "switch", "missing")

            self.assertEqual(result.returncode, 1)
            self.assertIn("plan directory not found", result.stdout)

    def test_attest_writes_shows_and_clears_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            expected = hashlib.sha256((plan_dir / "task_plan.md").read_bytes()).hexdigest()

            attest = run_plan(root, "attest")
            self.assertEqual(attest.returncode, 0, attest.stderr)
            self.assertEqual((plan_dir / ".attestation").read_text(encoding="ascii"), expected)
            self.assertIn(expected[:12], attest.stdout)

            show = run_plan(root, "attest", "--show")
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn(expected, show.stdout)

            clear = run_plan(root, "attest", "--clear")
            self.assertEqual(clear.returncode, 0, clear.stderr)
            self.assertFalse((plan_dir / ".attestation").exists())


if __name__ == "__main__":
    unittest.main()
