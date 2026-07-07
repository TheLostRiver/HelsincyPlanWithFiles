import contextlib
import io
import importlib.util
import json
import os
import subprocess
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


def create_redirected_codex_dir(testcase, target: Path, outside: Path) -> None:
    outside.mkdir(parents=True)
    link = target / ".codex"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            testcase.skipTest(f"cannot create junction: {result.stderr or result.stdout}")
        return

    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        testcase.skipTest(f"cannot create directory symlink: {exc}")


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

    def test_merge_hooks_canonicalizes_current_pwf_hook_metadata(self):
        module = load_installer()
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": "python .codex/hooks/pwf/pre_tool_use.py"}]}
                ]
            }
        }
        manifest = module.Manifest(
            schema=1,
            package="HelsincyPlanWithFiles",
            owned_files=(),
            owned_directory_globs=(),
            hook_entries=(
                module.HookEntry(
                    event="PreToolUse",
                    matcher="Bash|apply_patch|Edit|Write",
                    command="python .codex/hooks/pwf/pre_tool_use.py",
                    statusMessage="Checking plan before tool use",
                ),
            ),
            legacy_hook_commands=(),
        )

        merged, changed = module.merge_hooks_json(existing, manifest)

        self.assertTrue(changed)
        self.assertEqual(
            {
                "matcher": "Bash|apply_patch|Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python .codex/hooks/pwf/pre_tool_use.py",
                        "statusMessage": "Checking plan before tool use",
                    }
                ],
            },
            merged["hooks"]["PreToolUse"][0],
        )


class InstallerApplyTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(module.HookEntry(event="SessionStart", matcher="startup|resume|compact", command="python .codex/hooks/pwf/session_start.py"),),
                legacy_hook_commands=(),
            )

            result = module.install(source, target, manifest, version="0.3.4", dry_run=True)

            self.assertEqual(0, result.exit_code)
            self.assertFalse((target / ".codex/hooks/pwf/session_start.py").exists())
            self.assertFalse((target / ".codex/hooks.json").exists())
            self.assertIn("write: .codex/pwf-install-state.json", result.messages)

    def test_dry_run_accepts_existing_hooks_json_with_utf8_bom(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (target / ".codex").mkdir(parents=True)
            existing_hooks = {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "python .codex/hooks/custom.py"}]}
                    ]
                }
            }
            (target / ".codex/hooks.json").write_text(json.dumps(existing_hooks), encoding="utf-8-sig")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(module.HookEntry(event="SessionStart", matcher="startup|resume|compact", command="python .codex/hooks/pwf/session_start.py"),),
                legacy_hook_commands=(),
            )

            result = module.install(source, target, manifest, version="0.3.4", dry_run=True)

            self.assertEqual(0, result.exit_code)
            self.assertIn("merge: .codex/hooks.json", result.messages)

    def test_install_copies_files_merges_hooks_and_writes_state(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(module.HookEntry(event="SessionStart", matcher="startup|resume|compact", command="python .codex/hooks/pwf/session_start.py"),),
                legacy_hook_commands=(),
            )

            result = module.install(source, target, manifest, version="0.3.4", dry_run=False)

            self.assertEqual(0, result.exit_code)
            self.assertTrue((target / ".codex/hooks/pwf/session_start.py").is_file())
            hooks = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
            self.assertEqual("python .codex/hooks/pwf/session_start.py", hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"])
            state = json.loads((target / ".codex/pwf-install-state.json").read_text(encoding="utf-8"))
            self.assertEqual("0.3.4", state["version"])
            self.assertEqual(".codex/hooks/pwf/session_start.py", state["files"][0]["path"])

    def test_install_aborts_before_writing_when_conflict_exists(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (target / ".codex/hooks/pwf/session_start.py").write_text("print('custom')\n", encoding="utf-8")
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(),
                legacy_hook_commands=(),
            )

            result = module.install(source, target, manifest, version="0.3.4", dry_run=False)

            self.assertEqual(2, result.exit_code)
            self.assertEqual("print('custom')\n", (target / ".codex/hooks/pwf/session_start.py").read_text(encoding="utf-8"))
            self.assertFalse((target / ".codex/pwf-install-state.json").exists())

    def test_install_refuses_redirected_codex_directory(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            outside = target / "outside-codex"
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            create_redirected_codex_dir(self, target, outside)
            manifest = module.Manifest(
                schema=1,
                package="HelsincyPlanWithFiles",
                owned_files=(module.OwnedFile(".codex/hooks/pwf/session_start.py", ".codex/hooks/pwf/session_start.py", "hook"),),
                owned_directory_globs=(),
                hook_entries=(module.HookEntry(event="SessionStart", matcher="startup|resume|compact", command="python .codex/hooks/pwf/session_start.py"),),
                legacy_hook_commands=(),
            )

            result = module.install(source, target, manifest, version="0.3.4", dry_run=False)

            self.assertEqual(2, result.exit_code)
            self.assertTrue(any("unsafe target path" in message for message in result.messages))
            self.assertFalse((outside / "hooks/pwf/session_start.py").exists())
            self.assertFalse((outside / "pwf-install-state.json").exists())


class InstallerUninstallTests(unittest.TestCase):
    def test_uninstall_removes_only_state_owned_files_and_hooks(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as target_dir:
            target = Path(target_dir)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            (target / ".codex/hooks").mkdir(exist_ok=True)
            (target / ".codex/hooks/custom.py").write_text("print('custom')\n", encoding="utf-8")
            owned_file = target / ".codex/hooks/pwf/session_start.py"
            owned_file.write_text("print('pwf')\n", encoding="utf-8")
            hooks = {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "python .codex/hooks/pwf/session_start.py"}]},
                        {"hooks": [{"type": "command", "command": "python .codex/hooks/custom.py"}]},
                    ]
                }
            }
            (target / ".codex/hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
            state = {
                "schema": 1,
                "package": "HelsincyPlanWithFiles",
                "version": "0.3.4",
                "installed_at": "2026-06-25T15:00:00Z",
                "files": [{"path": ".codex/hooks/pwf/session_start.py", "sha256": module.sha256_file(owned_file)}],
                "hooks": [{"event": "SessionStart", "command": "python .codex/hooks/pwf/session_start.py"}],
            }
            (target / ".codex/pwf-install-state.json").write_text(json.dumps(state), encoding="utf-8")

            result = module.uninstall(target, dry_run=False)

            self.assertEqual(0, result.exit_code)
            self.assertFalse(owned_file.exists())
            self.assertTrue((target / ".codex/hooks/custom.py").exists())
            merged = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
            commands = [
                hook["command"]
                for group in merged["hooks"]["SessionStart"]
                for hook in group.get("hooks", [])
            ]
            self.assertEqual(["python .codex/hooks/custom.py"], commands)
            self.assertFalse((target / ".codex/pwf-install-state.json").exists())

    def test_uninstall_refuses_modified_state_owned_file(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as target_dir:
            target = Path(target_dir)
            (target / ".codex/hooks/pwf").mkdir(parents=True)
            owned_file = target / ".codex/hooks/pwf/session_start.py"
            owned_file.write_text("print('local edit')\n", encoding="utf-8")
            state = {
                "schema": 1,
                "package": "HelsincyPlanWithFiles",
                "version": "0.3.4",
                "installed_at": "2026-06-25T15:00:00Z",
                "files": [{"path": ".codex/hooks/pwf/session_start.py", "sha256": "previous-hash"}],
                "hooks": [{"event": "SessionStart", "command": "python .codex/hooks/pwf/session_start.py"}],
            }
            (target / ".codex/pwf-install-state.json").write_text(json.dumps(state), encoding="utf-8")

            result = module.uninstall(target, dry_run=False)

            self.assertEqual(2, result.exit_code)
            self.assertTrue(owned_file.exists())
            self.assertTrue((target / ".codex/pwf-install-state.json").exists())


class InstallerCliTests(unittest.TestCase):
    def test_cli_dry_run_returns_zero(self):
        module = load_installer()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            (source / "installer").mkdir(parents=True)
            (source / ".codex/hooks/pwf").mkdir(parents=True)
            (source / ".codex/hooks/pwf/session_start.py").write_text("print('pwf')\n", encoding="utf-8")
            (source / "VERSION").write_text("0.3.4\n", encoding="utf-8")
            (source / "installer/pwf_install_manifest.json").write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "package": "HelsincyPlanWithFiles",
                        "owned_files": [
                            {
                                "source": ".codex/hooks/pwf/session_start.py",
                                "target": ".codex/hooks/pwf/session_start.py",
                                "kind": "hook",
                            }
                        ],
                        "owned_directory_globs": [],
                        "hook_entries": [
                            {"event": "SessionStart", "command": "python .codex/hooks/pwf/session_start.py"}
                        ],
                        "legacy_hook_commands": [],
                    }
                ),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = module.main(["install", "--source", str(source), "--target", target_dir, "--dry-run"])

            self.assertEqual(0, result)

    def test_cli_rejects_missing_target_argument(self):
        module = load_installer()

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = module.main(["install"])

        self.assertEqual(2, result)


if __name__ == "__main__":
    unittest.main()
