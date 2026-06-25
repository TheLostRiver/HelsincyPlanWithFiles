import importlib.util
import sys
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


if __name__ == "__main__":
    unittest.main()
