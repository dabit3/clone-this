import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from fingerprint import compute_fingerprint
from verify_state import validate_state


def write_png(path, width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\0" + b"\0\0\0" * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class VerifyStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clone_root = Path(self.temporary.name).resolve()
        self.source_file = self.clone_root / "src" / "app.js"
        self.source_file.parent.mkdir()
        self.source_file.write_text("export const name = 'Replica';\n")
        self.root = self.clone_root / ".devin" / "clone-this" / "replica"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir(parents=True)
        for name in ("report.txt", "sweep-1.json", "sweep-2.json"):
            (self.evidence / name).write_text("Synthetic manifest validation fixture.\n")
        for name in ("reference.png", "actual.png", "diff.png"):
            write_png(self.evidence / name, 10, 10)
        revision = compute_fingerprint(self.clone_root)
        self.events = self.root / "events.jsonl"
        self.events.write_text(json.dumps({"iteration": 4, "revision": revision, "next_action": "Deliver"}) + "\n")
        self.state = json.loads((SKILL_ROOT / "templates" / "state.json").read_text())
        self.state.update(
            source="/reference/application",
            clone_name="Replica",
            clone_root=str(self.clone_root),
            revision=revision,
            iteration=4,
        )
        self.state["items"] = [
            {
                "id": f"{kind}-home",
                "kind": kind,
                "label": f"Home {kind}",
                "status": "verified",
                "verified_revision": self.state["revision"],
                "evidence": ["evidence/report.txt"],
            }
            for kind in ("route", "feature", "journey", "visual")
        ]
        self.state["items"][-1]["comparison"] = {
            "mode": "exact",
            "reference": "evidence/reference.png",
            "actual": "evidence/actual.png",
            "diff": "evidence/diff.png",
            "different_pixels": 0,
            "total_pixels": 100,
        }
        for group, status in (("audits", "verified"), ("checks", "passed")):
            for record in self.state[group]:
                record.update(
                    status=status,
                    verified_revision=self.state["revision"],
                    evidence=["evidence/report.txt"],
                )
        self.state["sweeps"] = [
            {
                "revision": self.state["revision"],
                "new_items": 0,
                "frontier_empty": True,
                "audit_ids": [record["id"] for record in self.state["audits"]],
                "evidence": [f"evidence/sweep-{number}.json"],
            }
            for number in (1, 2)
        ]

    def errors(self):
        return validate_state(self.state, self.root)

    def test_complete_manifest_passes(self):
        self.assertEqual(self.errors(), [])
        self.state["status"] = "complete"
        self.assertEqual(self.errors(), [])

    def test_uninitialized_template_fails(self):
        template = json.loads((SKILL_ROOT / "templates" / "state.json").read_text())
        self.assertTrue(validate_state(template, self.root))

    def test_status_alone_does_not_prove_completion(self):
        self.state["status"] = "complete"
        self.state["items"][0]["status"] = "pending"
        self.assertTrue(self.errors())

    def test_blocked_and_paused_runs_fail(self):
        for status in ("blocked", "paused", "unknown", None):
            with self.subTest(status=status):
                self.state["status"] = status
                self.assertTrue(self.errors())

    def test_unresolved_work_fails(self):
        for field in ("frontier", "blockers", "unverified_assumptions"):
            with self.subTest(field=field):
                self.state[field] = ["Unresolved requirement"]
                self.assertTrue(self.errors())
                self.state[field] = []

    def test_missing_metadata_fails(self):
        for field in ("source", "clone_name", "clone_root", "revision", "next_action"):
            with self.subTest(field=field):
                previous = self.state.pop(field)
                self.assertTrue(self.errors())
                self.state[field] = previous

    def test_relative_clone_root_fails(self):
        self.state["clone_root"] = "relative/clone"
        self.assertTrue(self.errors())

    def test_missing_clone_root_fails(self):
        self.state["clone_root"] = str(self.clone_root / "absent")
        self.assertIn("clone_root must be an existing directory.", self.errors())

    def test_changed_clone_content_invalidates_revision(self):
        self.source_file.write_text("export const name = 'Changed';\n")
        self.assertTrue(any("does not match the current content fingerprint" in error for error in self.errors()))

    def test_evidence_changes_do_not_invalidate_revision(self):
        (self.evidence / "late-note.txt").write_text("Evidence written after the fingerprint.\n")
        self.events.write_text(self.events.read_text() + json.dumps({"revision": self.state["revision"]}) + "\n")
        self.assertEqual(self.errors(), [])

    def test_run_directory_outside_clone_root_fails(self):
        with tempfile.TemporaryDirectory() as other:
            self.state["clone_root"] = other
            self.assertIn("The run directory must be <clone_root>/.devin/clone-this/<safe-name>.", self.errors())

    def test_run_directory_name_must_derive_from_clone_name(self):
        self.state["clone_name"] = "Other Product"
        self.assertTrue(any("must be 'other-product'" in error for error in self.errors()))

    def test_events_log_is_required(self):
        self.events.unlink()
        self.assertIn("events.jsonl must exist in the run directory.", self.errors())
        self.events.write_text("\n")
        self.assertIn("events.jsonl must contain at least one iteration record.", self.errors())

    def test_malformed_event_records_fail(self):
        good = json.dumps({"revision": self.state["revision"]})
        for line in ("not json", "[]", json.dumps({"iteration": 1}), json.dumps({"revision": ""})):
            with self.subTest(line=line):
                self.events.write_text(line + "\n" + good + "\n")
                self.assertTrue(self.errors())

    def test_final_event_must_carry_current_revision(self):
        self.events.write_text(self.events.read_text() + json.dumps({"revision": "old-fingerprint"}) + "\n")
        self.assertIn("The final events.jsonl record must carry the current revision.", self.errors())

    def test_screenshots_must_be_png(self):
        for field in ("reference", "actual"):
            with self.subTest(field=field):
                write_png(self.evidence / "reference.png", 10, 10)
                write_png(self.evidence / "actual.png", 10, 10)
                (self.evidence / f"{field}.png").write_text("Not an image.\n")
                self.assertTrue(any("must be a PNG image" in error for error in self.errors()))

    def test_mismatched_screenshot_dimensions_fail(self):
        write_png(self.evidence / "actual.png", 10, 12)
        self.assertTrue(any("Dimensions must match" in error for error in self.errors()))

    def test_total_pixels_must_match_reference_image(self):
        self.state["items"][-1]["comparison"]["total_pixels"] = 99
        self.assertTrue(any("must equal the reference pixel count 100" in error for error in self.errors()))

    def test_invalid_numeric_metadata_fails(self):
        for field, values in (("schema_version", (True, 2, "1")), ("iteration", (True, -1, 1.5))):
            original = self.state[field]
            for value in values:
                with self.subTest(field=field, value=value):
                    self.state[field] = value
                    self.assertTrue(self.errors())
            self.state[field] = original

    def test_every_required_item_kind_is_needed(self):
        original = self.state["items"]
        for kind in ("route", "feature", "journey", "visual"):
            with self.subTest(kind=kind):
                self.state["items"] = [item for item in original if item["kind"] != kind]
                self.assertTrue(self.errors())
        self.state["items"] = []
        self.assertTrue(self.errors())

    def test_unknown_item_kind_fails(self):
        self.state["items"][0]["kind"] = "unknown"
        self.assertTrue(self.errors())

    def test_duplicate_ids_fail(self):
        for group in ("items", "audits", "checks"):
            with self.subTest(group=group):
                self.state[group].append(copy.deepcopy(self.state[group][0]))
                self.assertTrue(self.errors())
                self.state[group].pop()

    def test_every_audit_and_check_is_required(self):
        for group in ("audits", "checks"):
            original = self.state[group]
            for record in original:
                with self.subTest(group=group, record=record["id"]):
                    self.state[group] = [item for item in original if item["id"] != record["id"]]
                    self.assertTrue(self.errors())
            self.state[group] = original

    def test_stale_verifications_fail(self):
        for group in ("items", "audits", "checks"):
            with self.subTest(group=group):
                self.state[group][0]["verified_revision"] = "old-fingerprint"
                self.assertTrue(self.errors())
                self.state[group][0]["verified_revision"] = self.state["revision"]

    def test_failed_check_fails(self):
        self.state["checks"][0]["status"] = "failed"
        self.assertTrue(self.errors())

    def test_missing_empty_or_directory_evidence_fails(self):
        (self.evidence / "empty.txt").touch()
        for path in ("evidence/missing.txt", "evidence/empty.txt", "evidence", ""):
            with self.subTest(path=path):
                self.state["items"][0]["evidence"] = [path]
                self.assertTrue(self.errors())

    def test_missing_evidence_array_fails(self):
        for value in ([], None, "evidence/report.txt"):
            with self.subTest(value=value):
                self.state["items"][0]["evidence"] = value
                self.assertTrue(self.errors())

    def test_unsafe_evidence_paths_fail(self):
        for path in (str(self.evidence / "report.txt"), "../outside.txt", "evidence/../evidence/report.txt", "evidence\\report.txt"):
            with self.subTest(path=path):
                self.state["items"][0]["evidence"] = [path]
                self.assertTrue(self.errors())

    def test_external_symlink_fails(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "report.txt"
            target.write_text("Outside the run directory")
            (self.evidence / "external.txt").symlink_to(target)
            self.state["items"][0]["evidence"] = ["evidence/external.txt"]
            self.assertTrue(self.errors())

    def test_different_pixels_fail(self):
        self.state["items"][-1]["comparison"]["different_pixels"] = 1
        self.assertTrue(self.errors())

    def test_invalid_pixel_metrics_fail(self):
        comparison = self.state["items"][-1]["comparison"]
        for field, values in (("different_pixels", (False, -1, 0.0, "0")), ("total_pixels", (True, 0, -1, 1.5))):
            original = comparison[field]
            for value in values:
                with self.subTest(field=field, value=value):
                    comparison[field] = value
                    self.assertTrue(self.errors())
            comparison[field] = original

    def test_visual_artifacts_are_required_and_distinct(self):
        comparison = self.state["items"][-1]["comparison"]
        for field in ("reference", "actual", "diff"):
            with self.subTest(field=field):
                original = comparison.pop(field)
                self.assertTrue(self.errors())
                comparison[field] = original
        comparison["actual"] = comparison["reference"]
        self.assertTrue(self.errors())

    def test_normalized_comparison_requires_evidence(self):
        comparison = self.state["items"][-1]["comparison"]
        comparison["mode"] = "normalized"
        self.assertTrue(self.errors())
        comparison["normalization_evidence"] = "evidence/report.txt"
        self.assertEqual(self.errors(), [])

    def test_exact_mode_rejects_normalization(self):
        self.state["items"][-1]["comparison"]["normalization_evidence"] = "evidence/report.txt"
        self.assertTrue(self.errors())

    def test_two_final_zero_discovery_sweeps_are_required(self):
        self.state["sweeps"][0]["new_items"] = 1
        self.assertTrue(self.errors())
        self.state["sweeps"][0]["new_items"] = 0
        self.state["sweeps"].pop()
        self.assertTrue(self.errors())

    def test_old_sweep_history_does_not_prevent_completion(self):
        earlier = copy.deepcopy(self.state["sweeps"][0])
        earlier.update(revision="old-fingerprint", new_items=10, frontier_empty=False)
        self.state["sweeps"].insert(0, earlier)
        self.assertEqual(self.errors(), [])

    def test_incomplete_or_stale_sweep_fails(self):
        for field, value in (("revision", "old-fingerprint"), ("frontier_empty", False), ("audit_ids", []), ("new_items", False)):
            with self.subTest(field=field):
                original = self.state["sweeps"][1][field]
                self.state["sweeps"][1][field] = value
                self.assertTrue(self.errors())
                self.state["sweeps"][1][field] = original

    def test_reused_sweep_evidence_fails(self):
        self.state["sweeps"][1]["evidence"] = self.state["sweeps"][0]["evidence"]
        self.assertTrue(self.errors())

    def test_invalid_shapes_return_errors_without_crashing(self):
        self.assertTrue(validate_state([], self.root))
        for field in ("items", "audits", "checks", "sweeps", "frontier", "blockers", "unverified_assumptions"):
            original = self.state[field]
            for value in (None, {}, "invalid", [None]):
                with self.subTest(field=field, value=value):
                    self.state[field] = value
                    self.assertTrue(self.errors())
            self.state[field] = original
        self.state["items"][0]["id"] = []
        self.state["items"][0]["kind"] = {}
        self.state["items"][-1]["comparison"] = []
        self.assertTrue(self.errors())

    def test_external_event_log_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "events.jsonl"
            target.write_bytes(self.events.read_bytes())
            self.events.unlink()
            self.events.symlink_to(target)
            self.assertTrue(self.errors())

    def test_non_utf8_event_log_returns_errors(self):
        self.events.write_bytes(b"\xff\xfe")
        self.assertTrue(self.errors())

    def test_incomplete_or_corrupt_png_headers_fail(self):
        path = self.evidence / "reference.png"
        original = path.read_bytes()
        for content in (original[:24], original[:8] + b"\0\0\0\x0c" + original[12:],
                        original[:32] + bytes([original[32] ^ 1]) + original[33:]):
            with self.subTest(content=content[:33]):
                path.write_bytes(content)
                self.assertTrue(self.errors())

    def test_zero_sized_png_fails(self):
        write_png(self.evidence / "actual.png", 0, 10)
        self.assertTrue(self.errors())

    def test_hardlinked_visual_artifacts_are_not_distinct(self):
        actual = self.evidence / "actual.png"
        actual.unlink()
        os.link(self.evidence / "reference.png", actual)
        self.assertTrue(self.errors())

    def test_cli_does_not_write_bytecode_without_B_flag(self):
        copied = self.root / "verifier-copy"
        shutil.copytree(SKILL_ROOT / "scripts", copied, ignore=shutil.ignore_patterns("__pycache__"))
        path = self.root / "state.json"
        path.write_text(json.dumps(self.state))
        result = subprocess.run(
            [sys.executable, str(copied / "verify_state.py"), str(path)],
            capture_output=True, text=True, check=False,
            env={key: value for key, value in os.environ.items() if not key.startswith("PYTHON")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((copied / "__pycache__").exists())

    def run_cli(self, path):
        return subprocess.run(
            [sys.executable, "-B", str(SKILL_ROOT / "scripts" / "verify_state.py"), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_exit_codes_and_output(self):
        path = self.root / "state.json"
        path.write_text(json.dumps(self.state))
        result = self.run_cli(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"revision {self.state['revision']}", result.stdout)
        self.assertIn("items: 4 verified (route 1, feature 1, journey 1, visual 1)", result.stdout)
        self.assertIn("audits: 10 verified; checks: 5 passed; sweeps: 2", result.stdout)
        self.assertIn("does not prove application parity", result.stdout)
        self.state["blockers"] = ["Missing reference access"]
        path.write_text(json.dumps(self.state))
        result = self.run_cli(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("blockers", result.stderr)
        path.write_text("invalid JSON")
        self.assertEqual(self.run_cli(path).returncode, 2)
        self.assertEqual(self.run_cli(self.root / "missing.json").returncode, 2)


if __name__ == "__main__":
    unittest.main()
