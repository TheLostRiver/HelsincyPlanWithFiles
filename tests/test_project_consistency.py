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
            self.assertIn("PWF_STRICT_REQUIRES_BINDING=1", text)
            self.assertIn("Session", text)
            self.assertIn("Plan-Source", text)
            self.assertIn("stale", text)

        self.assertIn("session binding", changelog)
        self.assertIn("task ownership", changelog)
        self.assertIn("progress.md lock", changelog)

    def test_hooks_json_references_existing_hook_files(self):
        hooks = json.loads(read_text(".codex/hooks.json"))
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

        self.assertIn("docs/FAQ.md", readme_cn)
        self.assertIn("docs/FAQ.md", readme_en)

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

    def test_release_notes_are_bilingual_for_current_version(self):
        version = read_text("VERSION").strip()
        changelog = read_text("CHANGELOG.md")
        release_notes = read_text(f"docs/RELEASE_NOTES_{version}.md")

        match = re.search(
            rf"^## {re.escape(version)}\b(?P<body>.*?)(?=^## |\Z)",
            changelog,
            flags=re.MULTILINE | re.DOTALL,
        )

        self.assertIsNotNone(match)
        section = match.group("body")
        self.assertIn("中文：", section)
        self.assertIn("English:", section)
        self.assertIn("workspace", section)
        self.assertIn("strict", section)
        self.assertIn("FAQ", section)

        self.assertIn("中文", release_notes)
        self.assertIn("English", release_notes)
        self.assertIn("HelsincyPlanWithFiles-v", release_notes)
        self.assertIn("context compaction", release_notes)
        self.assertIn("上下文压缩", release_notes)

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
