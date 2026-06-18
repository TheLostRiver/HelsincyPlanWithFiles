import json
import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def collect_commands(value):
    commands = []
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            commands.append(command)
        for child in value.values():
            commands.extend(collect_commands(child))
    elif isinstance(value, list):
        for child in value:
            commands.extend(collect_commands(child))
    return commands


class ProjectConsistencyTests(unittest.TestCase):
    def test_readmes_document_plan_doctor_and_attestation(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")

        self.assertIn("plan.py doctor", readme_cn)
        self.assertIn("plan.py doctor", readme_en)
        self.assertIn("attestation", readme_cn)
        self.assertIn("attestation", readme_en)

    def test_readmes_link_chinese_localization_plan(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        plan = REPO_ROOT / "docs" / "CHINESE_LOCALIZATION_PLAN.md"

        self.assertTrue(plan.is_file())
        self.assertIn("docs/CHINESE_LOCALIZATION_PLAN.md", readme_cn)
        self.assertIn("docs/CHINESE_LOCALIZATION_PLAN.md", readme_en)

    def test_readmes_document_chinese_language_mode(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        skill = read_text(".codex/skills/planning-with-files/SKILL.md")

        self.assertIn("PWF_LANG=zh-CN", readme_cn)
        self.assertIn("PWF_LANG=zh-CN", readme_en)
        self.assertIn("PWF_LANG=en", readme_cn)
        self.assertIn("PWF_LANG=en", readme_en)
        self.assertIn("PWF_LANG=zh-CN", skill)

    def test_readmes_document_session_policy(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")

        for text in (readme_cn, readme_en):
            self.assertIn("PWF_SESSION_MODE=strict", text)
            self.assertIn("session-policy.json", text)
            self.assertIn("workspace", text)
            self.assertIn("strict", text)

    def test_docs_document_context_profiles(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        changelog = read_text("CHANGELOG.md")

        for text in (readme_cn, readme_en, faq, changelog):
            self.assertIn("PWF_CONTEXT_PROFILE", text)
            self.assertIn("expanded", text)
            self.assertIn("deep", text)
            self.assertIn("PWF_INCLUDE_FINDINGS", text)

    def test_docs_document_doctor_progress_storage_audit(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        changelog = read_text("CHANGELOG.md")
        skill = read_text(".codex/skills/pwf-doctor/SKILL.md")
        design = read_text("docs/APPEND_ONLY_PROGRESS_ROLLOVER_DESIGN.md")
        combined = "\n".join([readme_cn, readme_en, faq, changelog, skill, design])

        for phrase in (
            "progress storage",
            "progress-index.ndjson",
            "progress-active",
            "progress-archive",
            "No automatic repair was attempted.",
            "--strict",
            "--json",
        ):
            self.assertIn(phrase, combined)

    def test_docs_document_pre_compact_hook(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        skill = read_text(".codex/skills/planning-with-files/SKILL.md")
        changelog = read_text("CHANGELOG.md")

        for text in (readme_cn, readme_en, faq, skill, changelog):
            self.assertIn("PreCompact", text)
            self.assertIn("progress.md", text)
            self.assertIn("task_plan.md", text)

        self.assertIn("客观日志", readme_cn)
        for text in (readme_en, faq, skill, changelog):
            self.assertIn("objective log", text)

        for text in (readme_cn, readme_en, faq, skill, changelog):
            self.assertNotIn("flush recent actions into `progress.md`", text)
            self.assertNotIn("captures recent actions", text)
            self.assertNotIn("recent actions are represented in `progress.md`", text)

        for text in (faq, skill):
            self.assertIn("findings.md", text)

    def test_progress_ownership_language_does_not_prompt_manual_progress_writes(self):
        checked_paths = [
            ".codex/hooks/planning_state.py",
            ".codex/hooks/post-tool-use.sh",
            ".codex/hooks/stop.sh",
            ".codex/skills/planning-with-files/SKILL.md",
            ".codex/skills/planning-with-files/scripts/check-complete.sh",
            ".codex/skills/planning-with-files/scripts/check-complete.ps1",
            ".codex/skills/planning-with-files/templates/task_plan.md",
            ".codex/skills/planning-with-files/templates/progress.md",
            ".codex/skills/planning-with-files/templates/zh-CN/task_plan.md",
            ".codex/skills/planning-with-files/templates/zh-CN/progress.md",
            "README.md",
            "README.en.md",
            "docs/FAQ.md",
            "CHANGELOG.md",
        ]
        combined = "\n".join(read_text(path) for path in checked_paths)

        for forbidden in (
            "Update progress.md with what you just did",
            "Update progress.md before stopping",
            "make sure progress.md is up to date",
            "progress.md is up to date",
            "Document test results in progress.md",
            "将测试结果记录到 progress.md",
            "请确保 progress.md 是最新的",
            "保持 `progress.md` 最新",
            "reminds the agent to keep `progress.md` up to date",
            "progress.md    # actions, test results, file change records",
            "progress.md    # 执行动作、测试结果、文件变更记录",
            "Session logging",
        ):
            self.assertNotIn(forbidden, combined)

        for required in (
            "progress.md as the objective log written by hooks",
            "progress.md is maintained by hooks",
            "findings.md",
            "task_plan.md",
        ):
            self.assertIn(required, combined)

    def test_docs_document_session_context_profile_commands(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        user_guide = read_text("docs/USER_GUIDE.zh-CN.md")
        changelog = read_text("CHANGELOG.md")
        combined = "\n".join([readme_cn, readme_en, faq, user_guide, changelog])

        for phrase in (
            "/pwf-context-expanded",
            "/pwf-context-deep",
            "/pwf-context-status",
            "/pwf-context-notice-auto",
            "current session",
            "当前会话",
            "record-aware",
            "PWF_CONTEXT_PROFILE",
        ):
            self.assertIn(phrase, combined)

        for text in (readme_cn, readme_en, faq, changelog):
            self.assertIn("/pwf-context-expanded", text)
            self.assertIn("/pwf-context-notice-auto", text)

        self.assertIn("这些命令只影响当前会话", user_guide)
        self.assertIn("环境变量 `PWF_CONTEXT_PROFILE`", faq)
        self.assertIn("context injection notice", changelog)

    def test_docs_document_session_task_bindings(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        skill = read_text(".codex/skills/planning-with-files/SKILL.md")
        changelog = read_text("CHANGELOG.md")

        for text in (readme_cn, readme_en, faq, skill):
            self.assertIn("plan.py switch <plan-id> --session", text)
            self.assertIn("--force-claim", text)
            self.assertIn("--share", text)
            self.assertIn("--release-session", text)
            self.assertIn('plan.py init "Task Name" --bind-session', text)
            self.assertIn("--legacy --bind-session", text)
            self.assertIn("PWF_STRICT_REQUIRES_BINDING=1", text)
            self.assertIn("Session", text)
            self.assertIn("Plan-Source", text)
            self.assertIn("stale", text)
            self.assertIn("PLAN_ID", text)
            self.assertIn("routing override", text)
            self.assertIn("permission override", text)
            self.assertIn("owner session heartbeat", text)
            self.assertIn("payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID`", text)

        self.assertIn("session binding", changelog)
        self.assertIn("task ownership", changelog)
        self.assertIn("progress.md lock", changelog)
        self.assertIn("routing override", changelog)
        self.assertIn("permission override", changelog)
        self.assertIn("owner session heartbeat", changelog)
        self.assertIn("payload `session_id` -> `PWF_SESSION_ID` -> `CODEX_THREAD_ID`", changelog)

    def test_docs_document_session_task_selection_commands(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")

        for text in (readme_cn, readme_en, faq):
            self.assertIn("/pwf-tasks", text)
            self.assertIn("/pwf-use", text)
            self.assertIn("plan.py tasks", text)
            self.assertIn("plan.py use", text)

        self.assertIn("当前会话可见的 PWF 任务和短 ID；默认不显示其他会话任务", readme_cn)
        self.assertIn("用 `/pwf-tasks` 显示的短 ID 或 plan id 绑定当前会话", readme_cn)
        self.assertIn("visible to the current session with short IDs", readme_en)
        self.assertIn("other sessions' exclusive tasks are hidden by default", readme_en)
        self.assertIn("Bind the current session using a short ID or plan id shown by `/pwf-tasks`", readme_en)

    def test_legacy_resolver_scripts_delegate_to_python_resolver(self):
        shell_resolvers = [
            read_text(".codex/hooks/resolve-plan-dir.sh"),
            read_text(".codex/skills/planning-with-files/scripts/resolve-plan-dir.sh"),
        ]
        powershell_resolver = read_text(".codex/skills/planning-with-files/scripts/resolve-plan-dir.ps1")

        for resolver in shell_resolvers:
            self.assertIn("plan.py", resolver)
            self.assertIn("status", resolver)
            self.assertIn("PYTHON_BIN=", resolver)
            self.assertIn("command -v python3", resolver)
            self.assertIn("command -v python", resolver)
            self.assertIn("PWF_LANG=''", resolver)
            self.assertIn("^path: ", resolver)
            self.assertNotIn("ACTIVE_FILE=", resolver)
            self.assertNotIn("resolve_from_active_file", resolver)

        self.assertIn("plan.py", powershell_resolver)
        self.assertIn("status", powershell_resolver)
        self.assertIn("Get-Command python3, python", powershell_resolver)
        self.assertIn("if ($null -eq $pythonCommand)", powershell_resolver)
        self.assertIn('$env:PWF_LANG = ""', powershell_resolver)
        self.assertIn("path: *", powershell_resolver)
        self.assertNotIn("& python", powershell_resolver)
        self.assertNotIn("$activeFile", powershell_resolver)

    def test_hooks_json_references_existing_hook_files(self):
        hooks = json.loads(read_text(".codex/hooks.json"))
        self.assertIn("PreCompact", hooks["hooks"])
        commands = collect_commands(hooks)

        referenced = []
        for command in commands:
            referenced.extend(re.findall(r"\.codex/hooks/[A-Za-z0-9_]+\.py", command))

        self.assertTrue(referenced)
        for path in referenced:
            self.assertTrue((REPO_ROOT / path).is_file(), path)

    def test_version_is_recorded_in_changelog(self):
        version = read_text("VERSION").strip()
        changelog = read_text("CHANGELOG.md")
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")

        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(version, changelog)
        self.assertIn(f"Current version: `{version}`", readme_en)
        self.assertIn(f"当前版本：`{version}`", readme_cn)
        self.assertIn(f"HelsincyPlanWithFiles-v{version}-codex.zip", readme_cn)
        self.assertIn(f"HelsincyPlanWithFiles-v{version}-codex.zip", readme_en)

    def test_faq_document_is_linked_and_covers_user_questions(self):
        readme_cn = read_text("README.md")
        readme_en = read_text("README.en.md")
        faq = read_text("docs/FAQ.md")
        user_guide = read_text("docs/USER_GUIDE.zh-CN.md")

        self.assertIn("docs/FAQ.md", readme_cn)
        self.assertIn("docs/FAQ.md", readme_en)
        self.assertIn("docs/USER_GUIDE.zh-CN.md", readme_cn)
        self.assertIn("docs/USER_GUIDE.zh-CN.md", readme_en)
        self.assertIn("USER_GUIDE.zh-CN.md", faq)

        for phrase in (
            "上下文压缩",
            "context compaction",
            "PWF_SESSION_MODE=strict",
            "session-policy.json",
            "/pwf-doctor",
            "/pwf-init",
            "/pwf-compact",
            "/pwf-attest",
            "PWF_LANG=zh-CN",
        ):
            self.assertIn(phrase, faq)

        for phrase in (
            "任务记忆本",
            "/pwf-doctor",
            "/pwf-init",
            "/pwf-status",
            "/pwf-tasks",
            "/pwf-use",
            "多个 Codex 会话",
            "上下文压缩",
        ):
            self.assertIn(phrase, user_guide)

        for phrase in (
            "默认会绑定当前会话",
            "--no-bind-session",
            "--no-workspace-active",
            "workspace active 是兼容层",
            "接管或共享仍必须显式",
        ):
            self.assertIn(phrase, readme_cn + faq + user_guide)

        for phrase in (
            "session-first by default",
            "--no-bind-session",
            "workspace active remains a compatibility fallback",
            "claim or share still requires explicit intent",
        ):
            self.assertIn(phrase, readme_en + faq)

    def test_release_notes_are_bilingual_for_current_version(self):
        version = read_text("VERSION").strip()
        changelog = read_text("CHANGELOG.md")
        release_notes = read_text(f"docs/RELEASE_NOTES_{version}.md")

        match = re.search(
            rf"^## {re.escape(version)}\b(?P<body>.*?)(?=^## |\Z)",
            changelog,
            flags=re.MULTILINE | re.DOTALL,
        )

        self.assertIsNotNone(match, f"CHANGELOG must have a section for version {version}")
        section = match.group("body")
        # Every changelog section must be bilingual and substantive.
        self.assertIn("中文：", section)
        self.assertIn("English:", section)

        self.assertIn("中文", release_notes)
        self.assertIn("English", release_notes)
        self.assertIn(f"HelsincyPlanWithFiles-v{version}", release_notes)

    def test_released_compaction_hardening_is_recorded_in_0_2_0(self):
        changelog = read_text("CHANGELOG.md")
        match = re.search(
            r"^## 0\.2\.0\b(?P<body>.*?)(?=^## |\Z)",
            changelog,
            flags=re.MULTILINE | re.DOTALL,
        )

        self.assertIsNotNone(match)
        section = match.group("body")
        self.assertIn("Hardened `plan.py compact`", section)
        self.assertIn("manual bullet notes", section)
        self.assertIn("PWF_*", section)


if __name__ == "__main__":
    unittest.main()
