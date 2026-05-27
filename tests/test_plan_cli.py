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
