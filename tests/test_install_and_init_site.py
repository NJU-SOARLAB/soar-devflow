"""Integration tests for install_skills.py and init_docs_site.py."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "skills/soar-devflow-setup/scripts/install_skills.py"
INIT_SITE = ROOT / "skills/soar-devflow-setup/scripts/init_docs_site.py"
CHECK_DOCS = ROOT / "skills/soar-devflow-docs/scripts/check_docs.py"


class SetupToolsTests(unittest.TestCase):
    def test_install_skills_workspace_copy_and_claude_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(INSTALL), "--target", tmp, "--scope", "workspace", "--mode", "copy"],
                check=True, capture_output=True, text=True,
            )
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload["installed"]), 3)
            for name in ("soar-devflow-setup", "soar-devflow-tasks", "soar-devflow-docs"):
                self.assertTrue((Path(tmp) / ".agents/skills" / name / "SKILL.md").is_file())
                claude_link = Path(tmp) / ".claude/skills" / name
                self.assertTrue(claude_link.is_symlink())
                self.assertTrue((claude_link / "SKILL.md").is_file())

    def test_install_skills_relative_symlink_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(INSTALL), "--target", tmp, "--scope", "workspace", "--mode", "symlink", "--relative"],
                check=True, capture_output=True, text=True,
            )
            payload = json.loads(proc.stdout)
            self.assertEqual(len(payload["installed"]), 3)
            link = Path(tmp) / ".agents/skills/soar-devflow-tasks"
            self.assertTrue(link.is_symlink())
            self.assertFalse(Path(link.readlink()).is_absolute())
            self.assertTrue((link / "SKILL.md").is_file())

    def test_init_docs_site_passes_check_docs_gate_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable, str(INIT_SITE),
                    "--target", tmp,
                    "--title", "Demo System",
                    "--languages", "zh,en",
                    "--base", "/docs/",
                ],
                check=True, capture_output=True, text=True,
            )
            info = json.loads(proc.stdout)
            cfg_path = Path(info["docs_config"])
            self.assertTrue(cfg_path.is_file())
            chk = subprocess.run(
                [sys.executable, str(CHECK_DOCS), "--config", str(cfg_path), "--check"],
                check=True, capture_output=True, text=True,
            )
            report = json.loads(chk.stdout)
            self.assertTrue(report["passed"])
            self.assertEqual(report["pages"], 4)


if __name__ == "__main__":
    unittest.main()
