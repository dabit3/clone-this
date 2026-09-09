import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from fingerprint import compute_fingerprint, list_files, main, walk_files


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.write("src/app.js", "export const name = 'Replica';\n")
        self.write("package.json", '{"name": "replica"}\n')

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_fingerprint_is_deterministic_and_prefixed(self):
        first = compute_fingerprint(self.root)
        self.assertTrue(first.startswith("sha256:"))
        self.assertEqual(first, compute_fingerprint(self.root))

    def test_content_and_path_changes_alter_fingerprint(self):
        original = compute_fingerprint(self.root)
        self.write("src/app.js", "export const name = 'Changed';\n")
        changed = compute_fingerprint(self.root)
        self.assertNotEqual(original, changed)
        (self.root / "src" / "app.js").rename(self.root / "src" / "main.js")
        self.assertNotEqual(changed, compute_fingerprint(self.root))
        self.write("src/extra.js", "")
        self.assertNotEqual(changed, compute_fingerprint(self.root))

    def test_run_directory_and_system_files_are_excluded(self):
        original = compute_fingerprint(self.root)
        self.write(".devin/clone-this/replica/state.json", "{}\n")
        self.write(".devin/clone-this/replica/evidence/report.txt", "Evidence\n")
        self.write("src/.DS_Store", "junk")
        self.assertEqual(original, compute_fingerprint(self.root))
        self.assertNotIn(".devin/clone-this/replica/state.json", list_files(self.root)[1])

    def test_other_devin_configuration_is_included(self):
        original = compute_fingerprint(self.root)
        self.write(".devin/skills/local/SKILL.md", "# Local\n")
        self.assertNotEqual(original, compute_fingerprint(self.root))

    def test_walk_mode_skips_generated_directories(self):
        for relative in ("node_modules/dep/index.js", "dist/bundle.js", ".git/HEAD", "coverage/lcov.info"):
            self.write(relative, "generated")
        self.assertEqual(sorted(walk_files(self.root)), ["package.json", "src/app.js"])

    def test_symlink_targets_are_hashed(self):
        (self.root / "link.js").symlink_to("src/app.js")
        original = compute_fingerprint(self.root)
        (self.root / "link.js").unlink()
        (self.root / "link.js").symlink_to("package.json")
        self.assertNotEqual(original, compute_fingerprint(self.root))

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_git_mode_respects_ignore_rules_and_includes_untracked_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.write(".gitignore", "dist/\nsecrets.env\n")
        self.write("dist/bundle.js", "generated")
        self.write("secrets.env", "TOKEN=redacted")
        self.write("src/untracked.js", "export {};\n")
        method, paths = list_files(self.root)
        self.assertEqual(method, "git")
        self.assertEqual(paths, [".gitignore", "package.json", "src/app.js", "src/untracked.js"])
        subprocess.run(["git", "-C", str(self.root), "add", "-f", "dist/bundle.js"], check=True, capture_output=True)
        self.assertIn("dist/bundle.js", list_files(self.root)[1])

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_git_mode_skips_tracked_files_deleted_from_disk(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True, capture_output=True)
        before = compute_fingerprint(self.root)
        (self.root / "package.json").unlink()
        self.assertNotEqual(before, compute_fingerprint(self.root))

    def test_executable_permission_changes_alter_fingerprint(self):
        script = self.write("start.sh", "exit 0\n")
        script.chmod(0o644)
        original = compute_fingerprint(self.root)
        script.chmod(0o755)
        self.assertNotEqual(original, compute_fingerprint(self.root))
        fingerprints = set()
        for mode in (0o644, 0o744, 0o754, 0o755):
            script.chmod(mode)
            fingerprints.add(compute_fingerprint(self.root))
        self.assertEqual(len(fingerprints), 4)

    def test_missing_root_is_an_error(self):
        with self.assertRaises((OSError, ValueError)):
            compute_fingerprint(self.root / "absent")

    def test_permission_errors_are_not_silently_skipped(self):
        with mock.patch("fingerprint.os.lstat", side_effect=PermissionError("Denied")):
            with self.assertRaises(PermissionError):
                compute_fingerprint(self.root)

    def test_git_errors_do_not_fall_back_to_a_different_file_set(self):
        error = subprocess.CalledProcessError(128, ["git"], stderr=b"fatal: index file corrupt")
        with mock.patch("fingerprint.subprocess.run", side_effect=error):
            with self.assertRaises((OSError, ValueError, subprocess.CalledProcessError)):
                compute_fingerprint(self.root)

    def test_broken_repository_is_not_treated_as_an_unversioned_tree(self):
        (self.root / ".git").mkdir()
        error = subprocess.CalledProcessError(128, ["git"], stderr=b"fatal: not a git repository")
        with mock.patch("fingerprint.subprocess.run", side_effect=error):
            with self.assertRaises(ValueError):
                compute_fingerprint(self.root)

    def test_walk_records_directory_symlinks_without_following_them(self):
        (self.root / "alias").symlink_to("src", target_is_directory=True)
        with mock.patch("fingerprint.git_files", return_value=None):
            self.assertIn("alias", list_files(self.root)[1])

    def test_external_symlinks_are_not_silently_certified(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "external").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                compute_fingerprint(self.root)

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_nested_repository_content_is_included(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        nested = self.root / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True, capture_output=True)
        self.write("nested/app.js", "before\n")
        self.write("nested/.gitignore", "output/\n")
        self.write("nested/output/result.txt", "ignored\n")
        self.assertIn("nested/app.js", list_files(self.root)[1])
        self.assertNotIn("nested/output/result.txt", list_files(self.root)[1])
        before = compute_fingerprint(self.root)
        self.write("nested/app.js", "after\n")
        self.assertNotEqual(before, compute_fingerprint(self.root))

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_uninitialized_submodule_is_an_error(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.root), "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",module"],
            check=True, capture_output=True,
        )
        with self.assertRaises(ValueError):
            compute_fingerprint(self.root)

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_clone_subdirectory_does_not_include_parent_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.write("child/app.js", "child\n")
        child = self.root / "child"
        self.assertEqual(list_files(child)[1], ["app.js"])
        original = compute_fingerprint(child)
        self.write("package.json", "parent changed\n")
        self.assertEqual(original, compute_fingerprint(child))

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_dirty_submodule_content_is_included(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        module = self.root / "module"
        module.mkdir()
        subprocess.run(["git", "init", "-q", str(module)], check=True, capture_output=True)
        self.write("module/app.js", "before\n")
        subprocess.run(["git", "-C", str(module), "add", "app.js"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.root), "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",module"],
            check=True, capture_output=True,
        )
        before = compute_fingerprint(self.root)
        self.write("module/app.js", "after\n")
        self.assertNotEqual(before, compute_fingerprint(self.root))

    @unittest.skipIf(shutil.which("git") is None, "git is unavailable")
    def test_symlink_to_ignored_source_is_rejected(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.write(".gitignore", "hidden.js\n")
        self.write("hidden.js", "hidden\n")
        (self.root / "link.js").symlink_to("hidden.js")
        with self.assertRaises(ValueError):
            compute_fingerprint(self.root)

    def test_walk_errors_propagate(self):
        def failed_walk(root, onerror):
            onerror(PermissionError("Denied"))

        with mock.patch("fingerprint.os.walk", side_effect=failed_walk):
            with self.assertRaises(PermissionError):
                walk_files(self.root)

    def test_file_changes_during_hashing_are_rejected(self):
        original = Path.open
        source = self.root / "src/app.js"

        def changing_open(path, *args, **kwargs):
            handle = original(path, *args, **kwargs)
            if path == source and args == ("rb",):
                source.write_text("changed during capture\n")
            return handle

        with mock.patch.object(Path, "open", changing_open):
            with self.assertRaises(ValueError):
                compute_fingerprint(self.root)

    def test_file_listing_changes_during_hashing_are_rejected(self):
        first = ("walk", ["package.json", "src/app.js"])
        second = ("walk", ["package.json", "src/app.js", "src/new.js"])
        with mock.patch("fingerprint.list_files", side_effect=[first, second]):
            with self.assertRaises(ValueError):
                compute_fingerprint(self.root)

    def test_cli_reports_io_errors_without_traceback(self):
        output = io.StringIO()
        with mock.patch("fingerprint.compute_fingerprint", side_effect=PermissionError("Denied")):
            with contextlib.redirect_stderr(output):
                self.assertEqual(main([str(self.root)]), 2)
        self.assertIn("Cannot fingerprint", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(SKILL_ROOT / "scripts" / "fingerprint.py"), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_prints_fingerprint_and_listing(self):
        result = self.run_cli(str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), compute_fingerprint(self.root))
        listing = self.run_cli(str(self.root), "--list")
        self.assertEqual(listing.returncode, 0)
        self.assertRegex(listing.stdout.splitlines()[0], r"^# method: (git|walk)$")
        self.assertIn("src/app.js", listing.stdout.splitlines())
        self.assertEqual(self.run_cli(str(self.root / "absent")).returncode, 2)


if __name__ == "__main__":
    unittest.main()
