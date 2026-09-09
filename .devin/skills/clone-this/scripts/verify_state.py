import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import zlib

sys.dont_write_bytecode = True

from fingerprint import compute_fingerprint
from init_run import safe_name


AUDIT_IDS = (
    "source", "navigation", "roles", "states", "responsive",
    "data", "assets", "accessibility", "reliability", "rebrand",
)
CHECK_IDS = ("functional", "visual", "build", "quality", "security")
REQUIRED_KINDS = ("route", "feature", "journey", "visual")
ITEM_KINDS = REQUIRED_KINDS + ("asset", "integration")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_dimensions(path):
    """Return (width, height) from a PNG header, or None when the file is not a PNG."""
    with Path(path).open("rb") as handle:
        header = handle.read(33)
    if len(header) != 33 or header[:8] != PNG_SIGNATURE or header[8:16] != b"\0\0\0\rIHDR":
        return None
    if zlib.crc32(header[12:29]) & 0xFFFFFFFF != int.from_bytes(header[29:33], "big"):
        return None
    width, height = int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if not (0 < width < 2**31 and 0 < height < 2**31):
        return None
    if header[24] not in depths.get(header[25], ()) or header[26:28] != b"\0\0" or header[28] not in (0, 1):
        return None
    return width, height


def validate_state(state, run_dir):
    errors = []
    root = Path(run_dir).resolve()
    if not isinstance(state, dict):
        return ["The manifest must be a JSON object."]

    def require_text(value, context):
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{context} must contain nonempty text.")
            return False
        return True

    def require_integer(value, minimum, context):
        if type(value) is not int or value < minimum:
            errors.append(f"{context} must be an integer of at least {minimum}.")
            return False
        return True

    def evidence_path(value, context):
        if not require_text(value, context):
            return None
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            errors.append(f"{context} must be a relative path inside the run directory, without parent traversal.")
            return None
        try:
            path = (root / path).resolve(strict=True)
            path.relative_to(root)
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"{context} must identify a nonempty evidence file.")
                return None
        except (OSError, ValueError, RuntimeError):
            errors.append(f"{context} is unavailable or resolves outside the run directory.")
            return None
        return path

    def evidence_files(value, context):
        if not isinstance(value, list) or not value:
            errors.append(f"{context} must contain at least one evidence path.")
            return set()
        paths = set()
        for index, entry in enumerate(value):
            path = evidence_path(entry, f"{context}[{index}]")
            if path is not None:
                paths.add(path)
        return paths

    revision = state.get("revision")
    for field in ("source", "clone_name", "clone_root", "revision", "next_action"):
        require_text(state.get(field), field)
    clone_root = state.get("clone_root")
    clone_name = state.get("clone_name")
    if isinstance(clone_root, str) and clone_root.strip():
        if not Path(clone_root).is_absolute():
            errors.append("clone_root must be an absolute path.")
        elif not Path(clone_root).is_dir():
            errors.append("clone_root must be an existing directory.")
        else:
            clone_path = Path(clone_root).resolve()
            if root.parent != clone_path / ".devin" / "clone-this":
                errors.append("The run directory must be <clone_root>/.devin/clone-this/<safe-name>.")
            elif isinstance(clone_name, str) and clone_name.strip() and root.name != safe_name(clone_name):
                errors.append(f"The run directory name must be {safe_name(clone_name)!r}, derived from clone_name.")
            elif isinstance(revision, str) and revision.strip():
                actual = compute_fingerprint(clone_path)
                if actual != revision:
                    errors.append(
                        f"revision {revision!r} does not match the current content fingerprint {actual!r}. "
                        "The clone changed after verification; repeat the final suite, audits, and sweeps."
                    )
    if type(state.get("schema_version")) is not int or state["schema_version"] != 1:
        errors.append("schema_version must be integer 1.")
    require_integer(state.get("iteration"), 0, "iteration")
    if state.get("status") not in ("active", "complete"):
        errors.append("status must be active or complete. Blocked and paused runs cannot pass.")
    for field in ("frontier", "blockers", "unverified_assumptions"):
        if not isinstance(state.get(field), list) or state[field]:
            errors.append(f"{field} must be an empty array before completion.")

    def records(field, required_status, required_ids=()):
        entries = state.get(field)
        if not isinstance(entries, list) or not entries:
            errors.append(f"{field} must be a nonempty array.")
            return []
        seen = set()
        valid = []
        for index, entry in enumerate(entries):
            context = f"{field}[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{context} must be an object.")
                continue
            identifier = entry.get("id")
            if require_text(identifier, f"{context}.id"):
                if identifier in seen:
                    errors.append(f"{context}.id duplicates {identifier!r}.")
                seen.add(identifier)
            if entry.get("status") != required_status:
                errors.append(f"{context}.status must be {required_status!r}.")
            if entry.get("verified_revision") != revision:
                errors.append(f"{context}.verified_revision does not match the current revision.")
            evidence_files(entry.get("evidence"), f"{context}.evidence")
            valid.append((context, entry))
        if required_ids:
            for identifier in sorted(set(required_ids) - seen):
                errors.append(f"{field} lacks the required record {identifier!r}.")
            for identifier in sorted(seen - set(required_ids)):
                errors.append(f"{field} contains an unknown record {identifier!r}.")
        return valid

    kinds = set()
    for context, item in records("items", "verified"):
        require_text(item.get("label"), f"{context}.label")
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in ITEM_KINDS:
            errors.append(f"{context}.kind is not a supported inventory kind.")
            continue
        kinds.add(kind)
        if kind != "visual":
            continue
        comparison = item.get("comparison")
        context += ".comparison"
        if not isinstance(comparison, dict):
            errors.append(f"{context} must be an object.")
            continue
        mode = comparison.get("mode")
        if mode not in ("exact", "normalized"):
            errors.append(f"{context}.mode must be exact or normalized.")
        paths = []
        dimensions = {}
        for field in ("reference", "actual", "diff"):
            path = evidence_path(comparison.get(field), f"{context}.{field}")
            if path is None:
                continue
            paths.append(path)
            if field == "diff":
                continue
            size = png_dimensions(path)
            if size is None:
                errors.append(f"{context}.{field} must be a PNG image.")
            else:
                dimensions[field] = size
        identities = {(path.stat().st_dev, path.stat().st_ino) for path in paths}
        if len(paths) != len(identities):
            errors.append(f"{context} requires separate reference, actual, and diff files.")
        if len(dimensions) == 2 and dimensions["reference"] != dimensions["actual"]:
            errors.append(
                f"{context} compares a {dimensions['reference'][0]}x{dimensions['reference'][1]} reference "
                f"with a {dimensions['actual'][0]}x{dimensions['actual'][1]} capture. Dimensions must match."
            )
        changed = comparison.get("different_pixels")
        if require_integer(changed, 0, f"{context}.different_pixels") and changed != 0:
            errors.append(f"{context} still has {changed} differing pixels.")
        total = comparison.get("total_pixels")
        if require_integer(total, 1, f"{context}.total_pixels") and "reference" in dimensions:
            width, height = dimensions["reference"]
            if total != width * height:
                errors.append(f"{context}.total_pixels must equal the reference pixel count {width * height}.")
        if mode == "normalized":
            evidence_path(comparison.get("normalization_evidence"), f"{context}.normalization_evidence")
        elif mode == "exact" and "normalization_evidence" in comparison:
            errors.append(f"{context} cannot claim exact mode with normalization evidence.")
    for kind in REQUIRED_KINDS:
        if kind not in kinds:
            errors.append(f"items lacks the required kind {kind!r}.")

    records("audits", "verified", AUDIT_IDS)
    records("checks", "passed", CHECK_IDS)

    events_path = evidence_path("events.jsonl", "events.jsonl")
    if events_path is None:
        errors.append("events.jsonl must exist in the run directory.")
    else:
        last = None
        try:
            with events_path.open(encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        errors.append(f"events.jsonl line {number} is not valid JSON.")
                        continue
                    if not isinstance(event, dict) or not isinstance(event.get("revision"), str) or not event["revision"].strip():
                        errors.append(f"events.jsonl line {number} must be an object with a revision.")
                        continue
                    last = event
        except (OSError, UnicodeError):
            errors.append("events.jsonl must be readable UTF-8 text.")
        if last is None:
            errors.append("events.jsonl must contain at least one iteration record.")
        elif last["revision"] != revision:
            errors.append("The final events.jsonl record must carry the current revision.")

    sweeps = state.get("sweeps")
    if not isinstance(sweeps, list) or len(sweeps) < 2:
        errors.append("sweeps must contain two consecutive final discovery sweeps.")
        return errors
    final_evidence = []
    for index, sweep in enumerate(sweeps):
        context = f"sweeps[{index}]"
        if not isinstance(sweep, dict):
            errors.append(f"{context} must be an object.")
            continue
        require_text(sweep.get("revision"), f"{context}.revision")
        count = sweep.get("new_items")
        require_integer(count, 0, f"{context}.new_items")
        if type(sweep.get("frontier_empty")) is not bool:
            errors.append(f"{context}.frontier_empty must be a boolean.")
        audit_ids = sweep.get("audit_ids")
        if not isinstance(audit_ids, list) or not all(isinstance(entry, str) for entry in audit_ids):
            errors.append(f"{context}.audit_ids must be an array of audit IDs.")
        elif set(audit_ids) != set(AUDIT_IDS) or len(audit_ids) != len(AUDIT_IDS):
            errors.append(f"{context}.audit_ids must contain every mandatory audit ID exactly once.")
        paths = evidence_files(sweep.get("evidence"), f"{context}.evidence")
        if index < len(sweeps) - 2:
            continue
        final_evidence.append(paths)
        if sweep.get("revision") != revision:
            errors.append(f"{context}.revision does not match the current revision.")
        if type(count) is not int or count != 0:
            errors.append(f"{context} must discover zero new requirements.")
        if sweep.get("frontier_empty") is not True:
            errors.append(f"{context} must close the discovery frontier.")
    if len(final_evidence) == 2:
        first, second = final_evidence
        if not (first - second) or not (second - first):
            errors.append("The final two sweeps each require separate evidence of an independent inspection.")
    return errors


def summarize(state):
    kinds = Counter(item.get("kind") for item in state["items"])
    by_kind = ", ".join(f"{kind} {kinds[kind]}" for kind in ITEM_KINDS if kinds[kind])
    return [
        f"Manifest gate passed for revision {state['revision']}.",
        f"- items: {len(state['items'])} verified ({by_kind})",
        f"- audits: {len(state['audits'])} verified; checks: {len(state['checks'])} passed; sweeps: {len(state['sweeps'])}",
        "This does not prove application parity.",
        "Inspect the referenced evidence before claiming completion.",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a clone-this completion manifest without modifying it.")
    parser.add_argument("state", type=Path, help="Path to the run's state.json")
    args = parser.parse_args(argv)
    try:
        state = json.loads(args.state.read_text(encoding="utf-8"))
        errors = validate_state(state, args.state.resolve().parent)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Cannot validate the manifest: {error}", file=sys.stderr)
        return 2
    if errors:
        print("Completion gate failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("\n".join(summarize(state)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
