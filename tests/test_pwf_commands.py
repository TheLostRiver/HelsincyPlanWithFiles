from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".codex" / "skills"
PROJECT_COMMAND_DIR = REPO_ROOT / ".codex" / "commands"
LEGACY_COMMAND_DIR = REPO_ROOT / "commands"
INSTALL_COMMANDS_SCRIPT = (
    SKILL_ROOT / "planning-with-files" / "scripts" / "install-commands.ps1"
)

COMMANDS = {
    "pwf-doctor": "doctor",
    "pwf-init": "init",
    "pwf-status": "status",
    "pwf-switch": "switch",
    "pwf-attest": "attest",
    "pwf-capture": "capture",
    "pwf-compact": "compact",
}


def read_repo_text(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class PwfCommandTests(unittest.TestCase):
    def test_command_prompt_directories_are_not_used(self):
        self.assertFalse(
            LEGACY_COMMAND_DIR.exists(),
            "root commands are easy to miss when users copy only .codex",
        )
        self.assertFalse(
            PROJECT_COMMAND_DIR.exists(),
            "project .codex/commands is not the local user-invocable skill path",
        )

    def test_pwf_skill_wrappers_have_slash_command_metadata(self):
        for command_name in COMMANDS:
            with self.subTest(command=command_name):
                path = SKILL_ROOT / command_name / "SKILL.md"

                self.assertTrue(path.is_file(), f"missing {path}")
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"), f"{path} needs YAML frontmatter")
                self.assertIn(f"name: {command_name}", text)
                self.assertIn("user-invocable: true", text)
                self.assertIn(f"/{command_name}", text)

    def test_pwf_skill_wrappers_route_to_plan_cli(self):
        for command_name, subcommand in COMMANDS.items():
            with self.subTest(command=command_name):
                text = read_repo_text(f".codex/skills/{command_name}/SKILL.md")

                self.assertIn("plan.py", text)
                self.assertIn(subcommand, text)

    def test_pwf_compact_skill_wrapper_routes_to_plan_cli(self):
        path = SKILL_ROOT / "pwf-compact" / "SKILL.md"

        self.assertTrue(path.is_file(), f"missing {path}")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), f"{path} needs YAML frontmatter")
        self.assertIn("name: pwf-compact", text)
        self.assertIn("user-invocable: true", text)
        self.assertIn("/pwf-compact", text)
        self.assertIn("plan.py", text)
        self.assertIn("compact", text)

    def test_readmes_document_local_skill_location(self):
        readme_cn = read_repo_text("README.md")
        readme_en = read_repo_text("README.en.md")

        self.assertIn(".codex/skills/pwf-", readme_cn)
        self.assertIn(".codex/skills/pwf-", readme_en)
        self.assertNotIn("install-commands.ps1", readme_cn)
        self.assertNotIn("install-commands.ps1", readme_en)
        self.assertFalse(INSTALL_COMMANDS_SCRIPT.exists())

    def test_readmes_document_pwf_commands(self):
        readme_cn = read_repo_text("README.md")
        readme_en = read_repo_text("README.en.md")

        for command_name in COMMANDS:
            with self.subTest(command=command_name):
                slash_command = f"/{command_name}"
                table_row = f"| `{slash_command}` |"

                self.assertIn(table_row, readme_cn)
                self.assertIn(table_row, readme_en)


if __name__ == "__main__":
    unittest.main()
