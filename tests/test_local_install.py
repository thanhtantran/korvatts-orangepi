"""Regression tests for the self-contained Orange Pi installation path."""

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LocalInstallTests(unittest.TestCase):
    def test_example_config_uses_repo_relative_assets_directory(self):
        config = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("KORVATTS_ASSETS_DIR=assets", config)
        self.assertNotIn("KORVATTS_ASSETS_DIR=/", config)

    def test_installer_downloads_models_into_repo_assets_directory(self):
        installer = REPO_ROOT / "scripts" / "install-local.sh"

        self.assertTrue(installer.is_file())
        content = installer.read_text(encoding="utf-8")
        self.assertIn('ASSETS_DIR="$REPO_ROOT/assets"', content)
        self.assertIn('"$VENV_DIR/bin/python" -m ensurepip --upgrade', content)
        self.assertIn("snapshot_download", content)
        self.assertIn("local_dir=assets_dir", content)
        self.assertNotIn("local_dir_use_symlinks", content)


if __name__ == "__main__":
    unittest.main()
