import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
INSTALL_PATHS = (".devin/skills/clone-this", ".claude/skills/clone-this", ".agents/skills/clone-this", "custom skills/clone-this")


class SkillPackageTests(unittest.TestCase):
    def test_devin_requires_explicit_invocation(self):
        metadata = (SKILL_ROOT / "SKILL.md").read_text().split("---", 2)[1]
        self.assertIn("name: clone-this\n", metadata)
        self.assertRegex(metadata, r"(?m)^triggers:\n  - user\n(?=\S|\Z)")

    def test_claude_requires_explicit_invocation(self):
        metadata = (SKILL_ROOT / "SKILL.md").read_text().split("---", 2)[1]
        self.assertRegex(metadata, r"(?m)^disable-model-invocation: true$")

    def test_codex_requires_explicit_invocation(self):
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text()
        self.assertEqual(metadata, "policy:\n  allow_implicit_invocation: false\n")

    def test_scripts_work_from_copied_skill_directories(self):
        for install_path in INSTALL_PATHS:
            with self.subTest(install_path=install_path), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                installed = root / install_path
                shutil.copytree(SKILL_ROOT, installed)
                clone_root = root / "New Product"
                clone_root.mkdir()
                source = clone_root / "app.txt"
                source.write_text("First version\n")
                working_directory = root / "unrelated working directory"
                working_directory.mkdir()

                def run(script, *args):
                    return subprocess.run(
                        [sys.executable, "-B", str(installed / "scripts" / script), *map(str, args)],
                        cwd=working_directory, capture_output=True, text=True, check=False,
                    )

                initialized = run("init_run.py", "--", "/reference/app", "New Product", clone_root)
                self.assertEqual(initialized.returncode, 0, initialized.stderr)
                state_path = clone_root / ".devin/clone-this/new-product/state.json"
                state = json.loads(state_path.read_text())
                self.assertEqual(state["clone_root"], str(clone_root))
                fingerprint = run("fingerprint.py", clone_root)
                self.assertEqual(fingerprint.returncode, 0, fingerprint.stderr)
                self.assertEqual(fingerprint.stdout.strip(), state["revision"])
                before = {path: path.read_bytes() for path in state_path.parent.rglob("*") if path.is_file()}
                gate = run("verify_state.py", state_path)
                self.assertEqual(gate.returncode, 1, gate.stderr)
                self.assertIn("Completion gate failed:", gate.stderr)
                self.assertNotIn("fingerprint", gate.stderr)
                self.assertNotIn("run directory", gate.stderr.lower())
                self.assertEqual(before, {path: path.read_bytes() for path in state_path.parent.rglob("*") if path.is_file()})
                source.write_text("Second version\n")
                changed = run("fingerprint.py", clone_root)
                self.assertEqual(changed.returncode, 0, changed.stderr)
                self.assertNotEqual(changed.stdout.strip(), state["revision"])
                stale = run("verify_state.py", state_path)
                self.assertEqual(stale.returncode, 1, stale.stderr)
                self.assertIn("does not match the current content fingerprint", stale.stderr)

    def test_run_can_resume_from_another_skill_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            clone_root = root / "New Product"
            clone_root.mkdir()
            state_path = clone_root / ".devin/clone-this/new-product/state.json"
            for index, install_path in enumerate(INSTALL_PATHS):
                with self.subTest(install_path=install_path):
                    installed = root / install_path
                    shutil.copytree(SKILL_ROOT, installed)
                    result = subprocess.run(
                        [sys.executable, "-B", str(installed / "scripts/init_run.py"), "--", "/reference/app", "New Product", str(clone_root)],
                        cwd=root, capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if index == 0:
                        self.assertIn("Created a new manifest", result.stdout)
                        state = json.loads(state_path.read_text())
                        state.update(iteration=3, next_action="Resume the search feature.")
                        state_path.write_text(json.dumps(state))
                        before = {path: path.read_bytes() for path in state_path.parent.rglob("*") if path.is_file()}
                    else:
                        self.assertIn("Preserved the existing manifest", result.stdout)
                        self.assertEqual(before, {path: path.read_bytes() for path in state_path.parent.rglob("*") if path.is_file()})


if __name__ == "__main__":
    unittest.main()
