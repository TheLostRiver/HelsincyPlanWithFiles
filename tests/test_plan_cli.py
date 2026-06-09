import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "scripts" / "plan.py"


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


def auto_records(count):
    records = []
    for index in range(count):
        records.append(
            "\n".join(
                [
                    f"### Auto Record: 2026-05-12 10:{index:02d}:00",
                    "- Tool: apply_patch",
                    "- Files:",
                    f"  - `src/file_{index}.py` (update)",
                    "",
                ]
            )
        )
    return "\n".join(records)


class PlanCliTests(unittest.TestCase):
    def test_help_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "--help", env={"PWF_LANG": "zh-CN"})
            init_help = run_plan(root, "init", "--help", env={"PWF_LANG": "zh-CN"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("要检查的项目根目录", result.stdout)
            self.assertIn("创建新的 planning 会话", result.stdout)
            self.assertEqual(init_help.returncode, 0, init_help.stderr)
            self.assertIn("创建根目录级 planning 文件", init_help.stdout)
            self.assertIn("覆盖已有 planning 文件", init_help.stdout)

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
            self.assertIn("progress: 0 auto records", result.stdout)
            self.assertIn(
                "context: profile=default, plan=head 50 tail 0, progress=tail 80 lines, findings=off, max=32000 chars",
                result.stdout,
            )

    def test_status_reports_expanded_context_profile_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)

            result = run_plan(
                root,
                "status",
                env={"PWF_CONTEXT_PROFILE": "expanded", "PWF_INCLUDE_FINDINGS": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "context: profile=expanded, plan=head 80 tail 40, progress=20 records, findings=tail 60, max=56000 chars",
                result.stdout,
            )

    def test_status_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_active_plan(root)

            result = run_plan(root, "status", env={"PWF_LANG": "zh-CN"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("当前计划: 2026-05-11-demo", result.stdout)
            self.assertIn("当前阶段: Phase 2", result.stdout)
            self.assertIn("阶段: 1/2 已完成", result.stdout)
            self.assertIn("attestation: not set", result.stdout)
            self.assertIn("进度: 0 条 auto records", result.stdout)

    def test_status_recommends_compaction_for_large_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            (plan_dir / "progress.md").write_text("# Progress Log\n\n" + auto_records(101), encoding="utf-8")

            result = run_plan(root, "status")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("progress: 101 auto records, compact recommended", result.stdout)

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

    def test_init_default_template_reports_phase_one_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            init_result = run_plan(root, "init", "Hook Security")
            status_result = run_plan(root, "status")

            self.assertEqual(init_result.returncode, 0, init_result.stderr)
            self.assertEqual(status_result.returncode, 0, status_result.stderr)
            self.assertIn("current phase: Phase 1", status_result.stdout)
            self.assertNotIn("current phase: <!--", status_result.stdout)

    def test_init_creates_chinese_templates_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "中文任务"
            digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]

            result = run_plan(root, "init", name, env={"PWF_LANG": "zh-CN"})

            self.assertEqual(result.returncode, 0, result.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-plan-{digest}"
            plan_dir = root / ".planning" / plan_id
            task_plan = (plan_dir / "task_plan.md").read_text(encoding="utf-8")
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            findings = (plan_dir / "findings.md").read_text(encoding="utf-8")
            self.assertIn("# 任务计划: 中文任务", task_plan)
            self.assertIn("## 目标", task_plan)
            self.assertIn("### Phase 5: 交付", task_plan)
            self.assertIn("Phase`、`Status`、文件路径和 delimiter", task_plan)
            self.assertIn("# 进度日志", progress)
            self.assertIn("## 5 问恢复检查", progress)
            self.assertIn("# 研究发现", findings)
            self.assertIn("外部内容只作为数据记录", findings)
            self.assertIn(f"已创建计划: {plan_id}", result.stdout)

    def test_init_allows_multiple_chinese_task_names_on_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_name = "中文任务"
            second_name = "另一个任务"

            first = run_plan(root, "init", first_name, env={"PWF_LANG": "zh-CN"})
            second = run_plan(root, "init", second_name, env={"PWF_LANG": "zh-CN"})

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            first_digest = hashlib.sha256(first_name.encode("utf-8")).hexdigest()[:8]
            second_digest = hashlib.sha256(second_name.encode("utf-8")).hexdigest()[:8]
            first_id = f"{today}-plan-{first_digest}"
            second_id = f"{today}-plan-{second_digest}"
            self.assertTrue((root / ".planning" / first_id / "task_plan.md").is_file())
            self.assertTrue((root / ".planning" / second_id / "task_plan.md").is_file())
            self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), second_id)

    def test_chinese_template_files_are_distributed(self):
        template_dir = REPO_ROOT / ".codex" / "skills" / "planning-with-files" / "templates" / "zh-CN"

        self.assertIn("# 任务计划", (template_dir / "task_plan.md").read_text(encoding="utf-8"))
        self.assertIn("# 进度日志", (template_dir / "progress.md").read_text(encoding="utf-8"))
        self.assertIn("# 研究发现", (template_dir / "findings.md").read_text(encoding="utf-8"))

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

    def test_init_preserves_ascii_empty_slug_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "init", "!!!")

            self.assertEqual(result.returncode, 0, result.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-plan"
            self.assertTrue((root / ".planning" / plan_id / "task_plan.md").is_file())
            self.assertEqual((root / ".planning" / ".active_plan").read_text(encoding="utf-8"), plan_id)

    def test_init_legacy_creates_root_planning_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "init", "Legacy Task", "--legacy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "task_plan.md").is_file())
            self.assertTrue((root / "progress.md").is_file())
            self.assertTrue((root / "findings.md").is_file())
            self.assertIn("created legacy plan", result.stdout.lower())

    def test_init_legacy_bind_session_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]

            result = run_plan(
                root,
                "init",
                "Legacy Bound",
                "--legacy",
                "--bind-session",
                env={"PWF_SESSION_ID": "session-a"},
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("legacy plans do not support session binding", result.stdout)
            self.assertFalse((root / "task_plan.md").exists())
            self.assertFalse((root / "progress.md").exists())
            self.assertFalse((root / "findings.md").exists())
            self.assertFalse((root / ".planning" / "session-bindings" / f"{key}.json").exists())
            self.assertFalse((root / ".planning" / "legacy" / ".task-lease.json").exists())

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

    def test_switch_session_writes_binding_without_changing_workspace_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root / ".planning" / "2026-06-07-workspace")
            write_plan(root / ".planning" / "2026-06-07-session")
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")

            result = run_plan(
                root,
                "switch",
                "2026-06-07-session",
                "--session",
                env={"PWF_SESSION_ID": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (root / ".planning" / ".active_plan").read_text(encoding="utf-8"),
                "2026-06-07-workspace\n",
            )
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding = root / ".planning" / "session-bindings" / f"{key}.json"
            self.assertTrue(binding.is_file())
            self.assertEqual(
                json.loads(binding.read_text(encoding="utf-8"))["plan_id"],
                "2026-06-07-session",
            )
            self.assertIn(f"session binding set: {key} -> 2026-06-07-session", result.stdout)

    def test_switch_session_uses_codex_thread_id_when_pwf_session_id_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-09-thread"
            write_plan(root / ".planning" / plan_id)

            result = run_plan(root, "switch", plan_id, "--session", env={"CODEX_THREAD_ID": "thread-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            key = hashlib.sha256("thread-a".encode("utf-8")).hexdigest()[:12]
            binding = root / ".planning" / "session-bindings" / f"{key}.json"
            self.assertTrue(binding.is_file())
            self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)

    def test_switch_session_creates_task_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-session"
            write_plan(root / ".planning" / plan_id)

            result = run_plan(root, "switch", plan_id, "--session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_session_key"], key)
            self.assertFalse(lease["shared"])
            self.assertIn(f"task lease: owner={key} status=active shared=false", result.stdout)

    def test_switch_session_requires_force_claim_for_owned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-owned"
            write_plan(root / ".planning" / plan_id)
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": owner_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "switch", plan_id, "--session", env={"PWF_SESSION_ID": "session-b"})

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("owned by another session", result.stdout)
            self.assertIn("--force-claim", result.stdout)

    def test_switch_session_force_claim_transfers_task_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-claim"
            write_plan(root / ".planning" / plan_id)
            old_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            new_key = hashlib.sha256("session-b".encode("utf-8")).hexdigest()[:12]
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": old_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(
                root,
                "switch",
                plan_id,
                "--session",
                "--force-claim",
                env={"PWF_SESSION_ID": "session-b"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_session_key"], new_key)
            self.assertIn(f"task lease: owner={new_key} status=active shared=false", result.stdout)

    def test_switch_session_share_marks_task_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-share"
            write_plan(root / ".planning" / plan_id)

            result = run_plan(root, "switch", plan_id, "--session", "--share", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertTrue(lease["shared"])
            self.assertIn("shared=true", result.stdout)

    def test_switch_session_keeps_shared_task_shared_for_second_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-share"
            write_plan(root / ".planning" / plan_id)
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]

            share_result = run_plan(
                root,
                "switch",
                plan_id,
                "--session",
                "--share",
                env={"PWF_SESSION_ID": "session-a"},
            )
            join_result = run_plan(root, "switch", plan_id, "--session", env={"PWF_SESSION_ID": "session-b"})

            self.assertEqual(share_result.returncode, 0, share_result.stderr)
            self.assertEqual(join_result.returncode, 0, join_result.stderr)
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_session_key"], owner_key)
            self.assertTrue(lease["shared"])
            self.assertIn("shared=true", join_result.stdout)

    def test_switch_session_concurrent_claim_allows_single_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-race"
            write_plan(root / ".planning" / plan_id)

            def claim(session_id):
                return run_plan(root, "switch", plan_id, "--session", env={"PWF_SESSION_ID": session_id})

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(claim, ["session-a", "session-b"]))

            successes = [result for result in results if result.returncode == 0]
            failures = [result for result in results if result.returncode != 0]
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))

            self.assertEqual(len(successes), 1, [result.stdout for result in results])
            self.assertEqual(len(failures), 1, [result.stdout for result in results])
            self.assertIn("owned by another session", failures[0].stdout)
            self.assertIn(lease["owner_session_key"], successes[0].stdout)

    def test_switch_session_reports_task_lease_lock_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-locked"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            (plan_dir / ".task-lease.lock").write_text("held\n", encoding="utf-8")

            result = run_plan(
                root,
                "switch",
                plan_id,
                "--session",
                env={"PWF_SESSION_ID": "session-a", "PWF_TASK_LEASE_LOCK_TIMEOUT_MS": "1"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("task lease lock timed out", result.stdout)
            self.assertFalse((plan_dir / ".task-lease.json").exists())

    def test_switch_clear_session_removes_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text('{"version": 1}', encoding="utf-8")

            result = run_plan(root, "switch", "--clear-session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((binding_dir / f"{key}.json").exists())
            self.assertIn(f"session binding cleared: {key}", result.stdout)

    def test_switch_release_session_releases_owned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-release"
            write_plan(root / ".planning" / plan_id)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": plan_id}),
                encoding="utf-8",
            )
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "switch", "--release-session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((binding_dir / f"{key}.json").exists())
            lease = json.loads((root / ".planning" / plan_id / ".task-lease.json").read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_status"], "released")
            self.assertIn(f"task lease released: {key} -> {plan_id}", result.stdout)

    def test_switch_release_session_reports_task_lease_lock_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-release-locked"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir)
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            binding = binding_dir / f"{key}.json"
            binding.write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": plan_id}),
                encoding="utf-8",
            )
            lease_path = plan_dir / ".task-lease.json"
            lease_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (plan_dir / ".task-lease.lock").write_text("held\n", encoding="utf-8")

            result = run_plan(
                root,
                "switch",
                "--release-session",
                env={"PWF_SESSION_ID": "session-a", "PWF_TASK_LEASE_LOCK_TIMEOUT_MS": "1"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("task lease lock timed out", result.stdout)
            self.assertTrue(binding.exists())
            lease = json.loads(lease_path.read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_status"], "active")

    def test_init_bind_session_no_workspace_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(
                root,
                "init",
                "Side Task",
                "--bind-session",
                "--no-workspace-active",
                env={"PWF_SESSION_ID": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-side-task"
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            self.assertFalse((root / ".planning" / ".active_plan").exists())
            binding = root / ".planning" / "session-bindings" / f"{key}.json"
            self.assertEqual(json.loads(binding.read_text(encoding="utf-8"))["plan_id"], plan_id)
            self.assertIn(f"session binding set: {key} -> {plan_id}", result.stdout)

    def test_init_bind_session_creates_task_lease_for_workspace_active_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_plan(root, "init", "Bound Task", "--bind-session", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-bound-task"
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            lease_path = root / ".planning" / plan_id / ".task-lease.json"
            lease = json.loads(lease_path.read_text(encoding="utf-8"))
            self.assertEqual(lease["owner_session_key"], key)
            self.assertFalse(lease["shared"])
            self.assertIn(f"task lease: owner={key} status=active shared=false", result.stdout)

    def test_init_force_bind_session_does_not_overwrite_other_owned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-owned-task"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir, title="Original Owner")
            original_plan = (plan_dir / "task_plan.md").read_text(encoding="utf-8")
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            (plan_dir / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": owner_key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(
                root,
                "init",
                "Owned Task",
                "--force",
                "--bind-session",
                env={"PWF_SESSION_ID": "session-b"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("owned by another session", result.stdout)
            self.assertEqual((plan_dir / "task_plan.md").read_text(encoding="utf-8"), original_plan)

    def test_init_force_bind_session_does_not_overwrite_shared_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            today = datetime.now().strftime("%Y-%m-%d")
            plan_id = f"{today}-shared-task"
            plan_dir = root / ".planning" / plan_id
            write_plan(plan_dir, title="Shared Owner")
            original_plan = (plan_dir / "task_plan.md").read_text(encoding="utf-8")
            owner_key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            (plan_dir / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": owner_key,
                        "owner_status": "active",
                        "shared": True,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2026-06-07T10:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(
                root,
                "init",
                "Shared Task",
                "--force",
                "--bind-session",
                env={"PWF_SESSION_ID": "session-b"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("shared=true", result.stdout)
            self.assertEqual((plan_dir / "task_plan.md").read_text(encoding="utf-8"), original_plan)

    def test_status_reports_workspace_session_and_effective_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root / ".planning" / "2026-06-07-workspace")
            write_plan(root / ".planning" / "2026-06-07-session")
            (root / ".planning" / ".active_plan").write_text("2026-06-07-workspace\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-07-session"}),
                encoding="utf-8",
            )

            result = run_plan(root, "status", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("workspace active plan: 2026-06-07-workspace", result.stdout)
            self.assertIn(f"session binding: {key} -> 2026-06-07-session", result.stdout)
            self.assertIn("effective plan: 2026-06-07-session", result.stdout)
            self.assertIn("plan source: session", result.stdout)

    def test_status_reports_session_and_task_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "2026-06-07-status"
            write_plan(root / ".planning" / plan_id)
            (root / ".planning" / ".active_plan").write_text(plan_id + "\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": plan_id}),
                encoding="utf-8",
            )
            lease_dir = root / ".planning" / "session-leases"
            lease_dir.mkdir(parents=True)
            (lease_dir / f"{key}.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "session_key": key,
                        "session_id": "session-a",
                        "started_at": "2026-06-07T10:00:00Z",
                        "heartbeat_at": "2999-01-01T00:00:00Z",
                        "status": "active",
                        "bound_plan_id": plan_id,
                    }
                ),
                encoding="utf-8",
            )
            (root / ".planning" / plan_id / ".task-lease.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "plan_id": plan_id,
                        "owner_session_key": key,
                        "owner_status": "active",
                        "shared": False,
                        "claimed_at": "2026-06-07T10:00:00Z",
                        "updated_at": "2999-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            result = run_plan(root, "status", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"session lease: active {key}", result.stdout)
            self.assertIn(f"task lease: owner={key} status=active shared=false", result.stdout)

    def test_switch_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_plan(root / ".planning" / "2026-05-11-a")
            write_plan(root / ".planning" / "2026-05-11-b")

            set_result = run_plan(root, "switch", "2026-05-11-b", env={"PWF_LANG": "zh-CN"})
            show_result = run_plan(root, "switch", env={"PWF_LANG": "zh-CN"})

            self.assertEqual(set_result.returncode, 0, set_result.stderr)
            self.assertIn("已将当前计划设为: 2026-05-11-b", set_result.stdout)
            self.assertIn("路径:", set_result.stdout)
            self.assertEqual(show_result.returncode, 0, show_result.stderr)
            self.assertIn("当前计划: 2026-05-11-b", show_result.stdout)

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

    def test_attest_uses_session_bound_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_dir = root / ".planning" / "2026-06-08-workspace"
            session_dir = root / ".planning" / "2026-06-08-session"
            write_plan(workspace_dir, title="Workspace")
            write_plan(session_dir, title="Session")
            (root / ".planning" / ".active_plan").write_text("2026-06-08-workspace\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-08-session"}),
                encoding="utf-8",
            )
            expected = hashlib.sha256((session_dir / "task_plan.md").read_bytes()).hexdigest()

            result = run_plan(root, "attest", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((session_dir / ".attestation").read_text(encoding="ascii"), expected)
            self.assertFalse((workspace_dir / ".attestation").exists())
            self.assertIn(str(session_dir / "task_plan.md"), result.stdout)

    def test_attest_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            expected = hashlib.sha256((plan_dir / "task_plan.md").read_bytes()).hexdigest()

            attest = run_plan(root, "attest", env={"PWF_LANG": "zh-CN"})
            self.assertEqual(attest.returncode, 0, attest.stderr)
            self.assertEqual((plan_dir / ".attestation").read_text(encoding="ascii"), expected)
            self.assertIn("[plan-attest] 已锁定", attest.stdout)

            clear = run_plan(root, "attest", "--clear", env={"PWF_LANG": "zh-CN"})
            self.assertEqual(clear.returncode, 0, clear.stderr)
            self.assertIn("已清除", clear.stdout)

    def test_attest_show_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            expected = hashlib.sha256((plan_dir / "task_plan.md").read_bytes()).hexdigest()
            (plan_dir / ".attestation").write_text(expected, encoding="ascii")

            show = run_plan(root, "attest", "--show", env={"PWF_LANG": "zh-CN"})

            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("计划:", show.stdout)
            self.assertIn("Attestation:", show.stdout)
            self.assertIn(expected, show.stdout)

    def test_capture_uses_session_bound_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_dir = root / ".planning" / "2026-06-08-workspace"
            session_dir = root / ".planning" / "2026-06-08-session"
            write_plan(workspace_dir, title="Workspace")
            write_plan(session_dir, title="Session")
            (root / ".planning" / ".active_plan").write_text("2026-06-08-workspace\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-08-session"}),
                encoding="utf-8",
            )

            result = run_plan(
                root,
                "capture",
                "--kind",
                "note",
                "--source",
                "manual",
                "--summary",
                "session-bound finding",
                env={"PWF_SESSION_ID": "session-a"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(session_dir / "findings.md"), result.stdout)
            self.assertIn("session-bound finding", (session_dir / "findings.md").read_text(encoding="utf-8"))
            self.assertNotIn("session-bound finding", (workspace_dir / "findings.md").read_text(encoding="utf-8"))

    def test_capture_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)

            result = run_plan(
                root,
                "capture",
                "--kind",
                "web",
                "--source",
                "https://example.test",
                "--summary",
                "captured summary",
                env={"PWF_LANG": "zh-CN"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("已捕获外部上下文: web", result.stdout)
            self.assertIn("findings:", result.stdout)
            self.assertIn("captured summary", (plan_dir / "findings.md").read_text(encoding="utf-8"))

    def test_compact_archives_old_progress_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            (plan_dir / "progress.md").write_text("# Progress Log\n\n" + auto_records(4), encoding="utf-8")

            result = run_plan(root, "compact", "--keep-records", "2")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("compacted progress.md", result.stdout)
            self.assertIn("archived auto records: 2", result.stdout)
            self.assertIn("kept recent auto records: 2", result.stdout)
            self.assertTrue((plan_dir / "progress.archive.md").is_file())
            progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
            self.assertNotIn("src/file_0.py", progress)
            self.assertIn("src/file_2.py", progress)

    def test_compact_uses_session_bound_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace_dir = root / ".planning" / "2026-06-08-workspace"
            session_dir = root / ".planning" / "2026-06-08-session"
            write_plan(workspace_dir, title="Workspace")
            write_plan(session_dir, title="Session")
            (workspace_dir / "progress.md").write_text("# Progress Log\n\n" + auto_records(4), encoding="utf-8")
            (session_dir / "progress.md").write_text("# Progress Log\n\n" + auto_records(4), encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text("2026-06-08-workspace\n", encoding="utf-8")
            key = hashlib.sha256("session-a".encode("utf-8")).hexdigest()[:12]
            binding_dir = root / ".planning" / "session-bindings"
            binding_dir.mkdir(parents=True)
            (binding_dir / f"{key}.json").write_text(
                json.dumps({"version": 1, "session_id": "session-a", "plan_id": "2026-06-08-session"}),
                encoding="utf-8",
            )

            result = run_plan(root, "compact", "--keep-records", "2", env={"PWF_SESSION_ID": "session-a"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((session_dir / "progress.archive.md").is_file())
            self.assertFalse((workspace_dir / "progress.archive.md").exists())
            session_progress = (session_dir / "progress.md").read_text(encoding="utf-8")
            workspace_progress = (workspace_dir / "progress.md").read_text(encoding="utf-8")
            self.assertNotIn("src/file_0.py", session_progress)
            self.assertIn("src/file_0.py", workspace_progress)

    def test_compact_reports_chinese_output_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            (plan_dir / "progress.md").write_text("# Progress Log\n\n" + auto_records(4), encoding="utf-8")

            result = run_plan(root, "compact", "--keep-records", "2", env={"PWF_LANG": "zh-CN"})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("已压缩 progress.md", result.stdout)
            self.assertIn("已归档 auto records: 2", result.stdout)
            self.assertIn("保留最近 auto records: 2", result.stdout)

    def test_compact_dry_run_leaves_progress_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_active_plan(root)
            original = "\n".join(
                [
                    "# Progress Log",
                    "",
                    "### Auto Record: 2026-05-12 10:00:00",
                    "- Tool: Write",
                    "- Files:",
                    "  - `a.md` (write)",
                    "",
                    "### Auto Record: 2026-05-12 10:01:00",
                    "- Tool: Edit",
                    "- Files:",
                    "  - `b.md` (edit)",
                    "",
                ]
            )
            (plan_dir / "progress.md").write_text(original, encoding="utf-8")

            result = run_plan(root, "compact", "--keep-records", "1", "--dry-run")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("progress compaction dry run", result.stdout)
            self.assertIn("would archive auto records: 1", result.stdout)
            self.assertEqual((plan_dir / "progress.md").read_text(encoding="utf-8"), original)
            self.assertFalse((plan_dir / "progress.archive.md").exists())


if __name__ == "__main__":
    unittest.main()
