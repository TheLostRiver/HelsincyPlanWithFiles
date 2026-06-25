import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = REPO_ROOT / "installer" / "pwf_install.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("pwf_install", INSTALLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InstallerManifestTests(unittest.TestCase):
    def test_manifest_lists_only_relative_paths(self):
        module = load_installer()
        manifest = module.load_manifest(REPO_ROOT / "installer" / "pwf_install_manifest.json")

        for item in manifest.owned_files:
            self.assertFalse(Path(item.source).is_absolute())
            self.assertFalse(Path(item.target).is_absolute())

    def test_manifest_hook_commands_are_namespaced(self):
        module = load_installer()
        manifest = module.load_manifest(REPO_ROOT / "installer" / "pwf_install_manifest.json")

        commands = [hook.command for hook in manifest.hook_entries]
        self.assertIn("python .codex/hooks/pwf/session_start.py", commands)
        self.assertTrue(all(".codex/hooks/pwf/" in command for command in commands))


class InstallerFilePlanTests(unittest.TestCase):
    def test_missing_target_file_is_planned_for_copy(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")

            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=None)

            self.assertEqual("copy", op.action)

    def test_unknown_existing_target_file_is_conflict(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (target / ".codex/hooks/pwf/session_start.py").write_text("print('user')\n", encoding="utf-8")

            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=None)

            self.assertEqual("conflict", op.action)

    def test_identical_existing_target_file_is_skip(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            for root in (source, target):
                (root / ".codex/hooks/pwf").mkdir(parents=True)
                (root / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")

            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=None)

            self.assertEqual("skip", op.action)

    def test_owned_matching_previous_hash_is_planned_for_overwrite(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            source_file = source / ".codex/hooks/pwf/session_start.py"
            target_file = target / ".codex/hooks/pwf/session_start.py"
            source_file.write_text("print('new pwf')\n", encoding="utf-8")
            target_file.write_text("print('old pwf')\n", encoding="utf-8")
            state = {
                "files": [
                    {
                        "path": ".codex/hooks/pwf/session_start.py",
                        "sha256": module.sha256_file(target_file),
                    }
                ]
            }

            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=state)

            self.assertEqual("overwrite", op.action)

    def test_owned_modified_target_is_conflict_without_force(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('new pwf')\n", encoding="utf-8")
            (target / ".codex/hooks/pwf/session_start.py").write_text("print('local edit')\n", encoding="utf-8")
            state = {
                "files": [
                    {
                        "path": ".codex/hooks/pwf/session_start.py",
                        "sha256": "previous-hash",
                    }
                ]
            }

            owned = module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook")
            op = module.plan_file_operation(source, target, owned, state=state)

            self.assertEqual("conflict", op.action)

    def test_expand_owned_files_adds_pwf_skill_wrappers(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir:
            source = Path(source_dir)
            wrapper = source / ".codex/skills/pwf-status/SKILL.md"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text("---\nname: pwf-status\n---\n", encoding="utf-8")
            (source / ".codex/skills/pwf-status/__pycache__").mkdir()
            (source / ".codex/skills/pwf-status/__pycache__/ignored.pyc").write_bytes(b"cache")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(),
                owned_directory_globs=(".codex/skills/pwf-*",),
                hook_entries=(),
                legacy_hook_commands=(),
            )

            owned_files = module.expand_owned_files(source, manifest)

            self.assertEqual(
                (module.OwnedFile(".codex/skills/pwf-status/SKILL.md", ".codex/skills/pwf-status/SKILL.md", "skill-wrapper"),),
                owned_files,
            )


class InstallerHooksMergeTests(unittest.TestCase):
    def test_merge_hooks_preserves_existing_hook(self):
        module = load_installer()
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/custom.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/pwf/user_prompt_submit.py"),),
            legacy_hook_commands=(),
        )

        merged, changed = module.merge_hooks_json(existing, manifest)
        commands = [
            hook["command"]
            for group in merged["hooks"]["UserPromptSubmit"]
            for hook in group.get("hooks", [])
        ]

        self.assertTrue(changed)
        self.assertIn("python .codex/hooks/custom.py", commands)
        self.assertIn("python .codex/hooks/pwf/user_prompt_submit.py", commands)

    def test_merge_hooks_dedupes_existing_pwf_hook(self):
        module = load_installer()
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/pwf/user_prompt_submit.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/pwf/user_prompt_submit.py"),),
            legacy_hook_commands=(),
        )

        merged, changed = module.merge_hooks_json(existing, manifest)

        self.assertFalse(changed)
        self.assertEqual(1, len(merged["hooks"]["UserPromptSubmit"]))

    def test_merge_hooks_replaces_legacy_pwf_command(self):
        module = load_installer()
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/user_prompt_submit.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/pwf/user_prompt_submit.py"),),
            legacy_hook_commands=(module.HookEntry(event="UserPromptSubmit", command="python .codex/hooks/user_prompt_submit.py"),),
        )

        merged, changed = module.merge_hooks_json(existing, manifest)
        commands = [
            hook["command"]
            for group in merged["hooks"]["UserPromptSubmit"]
            for hook in group.get("hooks", [])
        ]

        self.assertTrue(changed)
        self.assertNotIn("python .codex/hooks/user_prompt_submit.py", commands)
        self.assertIn("python .codex/hooks/pwf/user_prompt_submit.py", commands)


if __name__ == "__main__":
    unittest.main()
