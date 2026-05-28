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

        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(version, changelog)

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
