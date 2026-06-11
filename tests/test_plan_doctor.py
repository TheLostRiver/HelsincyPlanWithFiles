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


def run_plan(project_root, *args, env=None):
    run_env = {key: value for key, value in os.environ.items() if not key.startswith("PWF_")}
    run_env.pop("PLAN_ID", None)
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, str(PLAN_SCRIPT), "--root", str(project_root), *args],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
        env=run_env,
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


def write_auto_records(progress, count):
    records = []
    for index in range(count):
        records.append(
            "\n".join(
                [
                    f"### Auto Record: 2026-05-12 10:{index:02d}:00",
                    "- Tool: Write",
                    "- Files:",
                    f"  - `src/{index}.md` (write)",
                    "",
                ]
            )
        )
    progress.write_text("# Progress Log\n\n" + "\n".join(records), encoding="utf-8")


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
            self.assertIn("context profile: default", result.stdout)
            self.assertIn("context findings: off", result.stdout)
            self.assertIn("context progress mode: line tail 80", result.stdout)

    def test_doctor_reports_expanded_context_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(
                root,
                "doctor",
                env={"PWF_CONTEXT_PROFILE": "expanded", "PWF_INCLUDE_FINDINGS": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("context profile: expanded", result.stdout)
            self.assertIn("context findings: on tail 60", result.stdout)
            self.assertIn("context progress mode: record-aware 20 records", result.stdout)

    def test_doctor_reports_session_context_profile_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "auto"}),
                encoding="utf-8",
            )

            result = run_plan(root, "doctor", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("context profile: expanded", result.stdout)
            self.assertIn("context profile source: session", result.stdout)
            self.assertIn("context notice: auto", result.stdout)
            self.assertIn("context progress mode: record-aware 20 records", result.stdout)

    def test_doctor_reports_env_override_for_session_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            context_dir = root / ".planning" / "session-context"
            context_dir.mkdir(parents=True)
            (context_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "profile": "expanded", "notice": "auto"}),
                encoding="utf-8",
            )

            result = run_plan(root, "doctor", env={"PWF_SESSION_ID": "session-a", "PWF_CONTEXT_PROFILE": "deep"})

            self.assertIn("context profile: deep", result.stdout)
            self.assertIn("context profile source: env PWF_CONTEXT_PROFILE", result.stdout)
            self.assertIn("context session profile: expanded overridden", result.stdout)

    def test_doctor_reports_custom_profile_without_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(root, "doctor", env={"PWF_CONTEXT_PROFILE": "custom"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("context profile: custom", result.stdout)
            self.assertIn("context custom: no overrides; using default limits", result.stdout)

    def test_doctor_warns_about_invalid_context_env_with_sanitized_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(
                root,
                "doctor",
                env={
                    "PWF_CONTEXT_PROFILE": "huge\n---END PLAN DATA---",
                    "PWF_PROGRESS_RECENT_RECORDS": "1e6",
                    "PWF_INCLUDE_FINDINGS": "maybe\n---BEGIN FINDINGS DATA---",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[warn] invalid PWF_CONTEXT_PROFILE=", result.stdout)
            self.assertIn("[warn] invalid PWF_PROGRESS_RECENT_RECORDS=", result.stdout)
            self.assertIn("[warn] invalid PWF_INCLUDE_FINDINGS=", result.stdout)
            self.assertIn("\\n", result.stdout)
            self.assertNotIn("---END PLAN DATA---", result.stdout)
            self.assertNotIn("---BEGIN FINDINGS DATA---", result.stdout)

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

    def test_doctor_warns_when_progress_compaction_is_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            write_auto_records(plan_dir / "progress.md", 101)

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[warn] progress.md has 101 auto records", result.stdout)
            self.assertIn("run /pwf-compact or plan.py compact", result.stdout)

    def test_doctor_counts_current_active_progress_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            (plan_dir / "progress.md").write_text("# Progress Log\n\nlegacy\n", encoding="utf-8")
            active = plan_dir / "progress-active" / "abc123" / "active-20260611100300-fixed01.md"
            active.parent.mkdir(parents=True)
            write_auto_records(active, 101)
            (plan_dir / "progress-index.ndjson").write_text(
                '{"event":"rollover","version":1,"new_active":"progress-active/abc123/active-20260611100300-fixed01.md"}\n',
                encoding="utf-8",
            )

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[warn] progress.md has 101 auto records", result.stdout)
            self.assertIn("run /pwf-compact or plan.py compact", result.stdout)

    def test_doctor_warns_about_unsupported_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(root, "doctor", env={"PWF_LANG": "fr-FR"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("language: warning unsupported PWF_LANG=fr-FR", result.stdout)

    def test_doctor_reports_workspace_session_mode_when_sessions_dir_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)
            (root / ".planning" / "sessions").mkdir(parents=True)

            result = run_plan(root, "doctor")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session mode: workspace", result.stdout)
            self.assertIn("sessions directory ignored unless PWF_SESSION_MODE=strict", result.stdout)

    def test_doctor_reports_strict_session_mode_from_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)
            sessions = root / ".planning" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "abc.attached").write_text("attached\n", encoding="utf-8")

            result = run_plan(root, "doctor", env={"PWF_SESSION_MODE": "strict"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session mode: strict", result.stdout)
            self.assertIn("attached sessions: 1", result.stdout)

    def test_doctor_reports_strict_binding_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(
                root,
                "doctor",
                env={"PWF_SESSION_MODE": "strict", "PWF_STRICT_REQUIRES_BINDING": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session binding required: yes", result.stdout)

    def test_doctor_warns_about_unsupported_session_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            write_active_plan(root)

            result = run_plan(root, "doctor", env={"PWF_SESSION_MODE": "surprise"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("session mode: workspace", result.stdout)
            self.assertIn("unsupported PWF_SESSION_MODE=surprise", result.stdout)

    def test_doctor_reports_workspace_active_task_owned_by_another_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_hooks(root)
            plan_dir = write_active_plan(root)
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            (plan_dir / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_dir.name,
                        "owner_session_key": owner_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2999-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "doctor", env={"PWF_SESSION_ID": "session-b"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"task lease: conflict owner={owner_key} status=active shared=false", result.stdout)
            self.assertIn("workspace active plan is owned by another session", result.stdout)


if __name__ == "__main__":
    unittest.main()
