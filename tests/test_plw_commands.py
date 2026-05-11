from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]

COMMANDS = {
    "plw-doctor": "doctor",
    "plw-init": "init",
    "plw-status": "status",
    "plw-switch": "switch",
    "plw-attest": "attest",
    "plw-capture": "capture",
}


def read_repo_text(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class PlwCommandTests(unittest.TestCase):
    def test_command_files_have_slash_command_metadata(self):
        for command_name in COMMANDS:
            with self.subTest(command=command_name):
                path = REPO_ROOT / "commands" / f"{command_name}.md"

                self.assertTrue(path.is_file(), f"missing {path}")
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"), f"{path} needs YAML frontmatter")
                self.assertIn("description:", text)
                self.assertIn(f"/{command_name}", text)

    def test_command_files_route_to_plan_cli(self):
        for command_name, subcommand in COMMANDS.items():
            with self.subTest(command=command_name):
                text = read_repo_text(f"commands/{command_name}.md")

                self.assertIn("plan.py", text)
                self.assertIn(subcommand, text)

    def test_readmes_document_plw_commands(self):
        readme_cn = read_repo_text("README.md")
        readme_en = read_repo_text("README.en.md")

        for command_name in COMMANDS:
            with self.subTest(command=command_name):
                slash_command = f"/{command_name}"

                self.assertIn(slash_command, readme_cn)
                self.assertIn(slash_command, readme_en)


if __name__ == "__main__":
    unittest.main()
