from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from fingerprint import compute_fingerprint
from init_run import initialize_run, safe_name
from verify_state import validate_state


class SafeNameTests(unittest.TestCase):
    def test_names_are_lowercased_hyphenated_and_trimmed(self):
        for name, expected in (
            ("New Product", "new-product"),
            ("  --Weird__Name!!  ", "weird-name"),
            ("Replica", "replica"),
            ("v2.0 Beta", "v2-0-beta"),
            ("../../etc/passwd", "etc-passwd"),
            ("$(rm -rf ~)", "rm-rf"),
        ):
            with self.subTest(name=name):
                self.assertEqual(safe_name(name), expected)

    def test_names_without_ascii_alphanumerics_fall_back(self):
        for name in ("", "   ", "!!!", "新产品"):
            with self.subTest(name=name):
                self.assertEqual(safe_name(name), "clone")

    def test_long_names_are_bounded(self):
        name = safe_name("word " * 40)
        self.assertLessEqual(len(name), 64)
        self.assertFalse(name.endswith("-"))


class InitializeRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clone_root = Path(self.temporary.name).resolve() / "new-product"
        self.clone_root.mkdir()
        (self.clone_root / "README.md").write_text("# New Product\n")

    def test_creates_run_directory_manifest_and_first_event(self):
        run_dir, created = initialize_run("/reference/app", "New Product", self.clone_root)
        self.assertTrue(created)
        self.assertEqual(run_dir, self.clone_root / ".devin" / "clone-this" / "new-product")
        for name in ("reference", "clone", "diffs", "tests", "discovery"):
            self.assertTrue((run_dir / "evidence" / name).is_dir())
        state = json.loads((run_dir / "state.json").read_text())
        template = json.loads((SKILL_ROOT / "templates" / "state.json").read_text())
        self.assertEqual(state["source"], "/reference/app")
        self.assertEqual(state["clone_name"], "New Product")
        self.assertEqual(state["clone_root"], str(self.clone_root))
        self.assertEqual(state["revision"], compute_fingerprint(self.clone_root))
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["audits"], template["audits"])
        self.assertEqual(state["checks"], template["checks"])
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["revision"], state["revision"])
        self.assertEqual(events[0]["next_action"], state["next_action"])

    def test_manifest_excludes_itself_from_the_fingerprint(self):
        run_dir, _ = initialize_run("/reference/app", "New Product", self.clone_root)
        state = json.loads((run_dir / "state.json").read_text())
        self.assertEqual(state["revision"], compute_fingerprint(self.clone_root))

    def test_existing_run_is_preserved(self):
        run_dir, _ = initialize_run("/reference/app", "New Product", self.clone_root)
        state_path = run_dir / "state.json"
        state = json.loads(state_path.read_text())
        state.update(iteration=7, next_action="Resume the search feature.")
        state_path.write_text(json.dumps(state))
        (run_dir / "events.jsonl").write_text("existing log\n")
        again, created = initialize_run("/reference/app", "New Product", self.clone_root)
        self.assertFalse(created)
        self.assertEqual(again, run_dir)
        self.assertEqual(json.loads(state_path.read_text()), state)
        self.assertEqual((run_dir / "events.jsonl").read_text(), "existing log\n")

    def test_conflicting_run_identity_is_rejected_without_changes(self):
        run_dir, _ = initialize_run("/reference/app", "New Product", self.clone_root)
        before = {path: path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
        for source, name in (("/other/app", "New Product"), ("/reference/app", "New-Product")):
            with self.subTest(source=source, name=name):
                with self.assertRaises(ValueError):
                    initialize_run(source, name, self.clone_root)
                self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_partial_run_is_not_overwritten(self):
        run_dir = self.clone_root / ".devin/clone-this/new-product"
        run_dir.mkdir(parents=True)
        events = run_dir / "events.jsonl"
        events.write_text("existing history\n")
        with self.assertRaises(ValueError):
            initialize_run("/reference/app", "New Product", self.clone_root)
        self.assertEqual(events.read_text(), "existing history\n")
        self.assertFalse((run_dir / "state.json").exists())

    def test_symlinked_run_ancestors_are_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.clone_root / ".devin").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                initialize_run("/reference/app", "New Product", self.clone_root)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_dangling_state_symlink_is_not_followed(self):
        run_dir = self.clone_root / ".devin/clone-this/new-product"
        run_dir.mkdir(parents=True)
        target = self.clone_root / "do-not-create.json"
        (run_dir / "state.json").symlink_to(target)
        with self.assertRaises(ValueError):
            initialize_run("/reference/app", "New Product", self.clone_root)
        self.assertFalse(target.exists())

    def test_invalid_api_inputs_do_not_create_a_run(self):
        for source, name in (("", "New Product"), ("/reference/app", "  ")):
            with self.subTest(source=source, name=name):
                with self.assertRaises(ValueError):
                    initialize_run(source, name, self.clone_root)
        self.assertFalse((self.clone_root / ".devin").exists())

    def test_destination_must_exist(self):
        missing = self.clone_root / "missing"
        with self.assertRaises((OSError, ValueError)):
            initialize_run("/reference/app", "New Product", missing)
        self.assertFalse(missing.exists())

    def test_initial_next_action_does_not_repeat_intake(self):
        run_dir, _ = initialize_run("/reference/app", "New Product", self.clone_root)
        state = json.loads((run_dir / "state.json").read_text())
        self.assertNotIn("Resolve the source", state["next_action"])

    def test_concurrent_initializers_never_replace_a_run(self):
        def initialize():
            try:
                return initialize_run("/reference/app", "New Product", self.clone_root)[1]
            except (FileExistsError, ValueError):
                return False

        with ThreadPoolExecutor(max_workers=2) as workers:
            created = list(workers.map(lambda _: initialize(), range(2)))
        self.assertEqual(created.count(True), 1)
        run_dir = self.clone_root / ".devin/clone-this/new-product"
        self.assertEqual(len((run_dir / "events.jsonl").read_text().splitlines()), 1)
        self.assertEqual(json.loads((run_dir / "state.json").read_text())["iteration"], 0)

    def test_fresh_run_does_not_pass_the_completion_gate(self):
        run_dir, _ = initialize_run("/reference/app", "New Product", self.clone_root)
        state = json.loads((run_dir / "state.json").read_text())
        errors = validate_state(state, run_dir)
        self.assertTrue(errors)
        self.assertFalse(any("fingerprint" in error or "run directory" in error.lower() for error in errors), errors)

    def test_cli_reports_creation_and_preservation(self):
        command = [sys.executable, "-B", str(SKILL_ROOT / "scripts" / "init_run.py"), "/reference/app", "New Product", str(self.clone_root)]
        first = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("Created a new manifest", first.stdout)
        second = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Preserved the existing manifest", second.stdout)
        empty = subprocess.run(command[:4] + ["  ", str(self.clone_root)], capture_output=True, text=True, check=False)
        self.assertEqual(empty.returncode, 2)
        self.assertIn("source and clone_name must contain nonempty text", empty.stderr)
        conflict = subprocess.run(command[:3] + ["/other/app", "New Product", str(self.clone_root)], capture_output=True, text=True, check=False)
        self.assertEqual(conflict.returncode, 2)
        self.assertNotIn("Traceback", conflict.stderr)


if __name__ == "__main__":
    unittest.main()
