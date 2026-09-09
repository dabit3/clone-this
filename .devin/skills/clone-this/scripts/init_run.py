"""Create a clone-this run directory and initial manifest.

An existing run is preserved. The script never overwrites state.json.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from fingerprint import compute_fingerprint


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_ROOT / "templates" / "state.json"
EVIDENCE_DIRECTORIES = ("reference", "clone", "diffs", "tests", "discovery")
MAX_SAFE_NAME_LENGTH = 64


def safe_name(clone_name):
    """Derive the run directory name: lowercase, hyphen-separated, bounded, and never empty."""
    name = re.sub(r"[^a-z0-9]+", "-", clone_name.lower()).strip("-")[:MAX_SAFE_NAME_LENGTH].rstrip("-")
    return name or "clone"


def run_directory(clone_root, clone_name):
    return Path(clone_root).resolve() / ".devin" / "clone-this" / safe_name(clone_name)


def initialize_run(source, clone_name, clone_root):
    """Create the run directory and manifest. Return the run directory and whether it was created."""
    if not all(isinstance(value, str) and value.strip() for value in (source, clone_name)):
        raise ValueError("source and clone_name must contain nonempty text.")
    root = Path(clone_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The clone root must be an existing directory.")
    run_dir = run_directory(root, clone_name)
    state_path = run_dir / "state.json"
    events_path = run_dir / "events.jsonl"
    for path in (root / ".devin", run_dir.parent, run_dir, state_path, events_path):
        if path.is_symlink():
            raise ValueError(f"Refusing the symlinked run path {path.name!r}.")
    if state_path.exists():
        existing = json.loads(state_path.read_text(encoding="utf-8"))
        identity = {"source": source, "clone_name": clone_name, "clone_root": str(root)}
        if not isinstance(existing, dict) or any(existing.get(key) != value for key, value in identity.items()):
            raise ValueError("The existing run belongs to a different source, name, or destination. Use a separate clone root.")
        if type(existing.get("schema_version")) is not int or existing["schema_version"] != 1:
            raise ValueError("The existing run has an unsupported schema. Preserve it for manual recovery.")
        if not events_path.is_file():
            raise ValueError("The existing run lacks its event log. Preserve it for manual recovery.")
        return run_dir, False
    if run_dir.exists():
        raise ValueError("The run directory exists without a manifest. Preserve it for manual recovery.")
    state = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    state.update(
        source=source, clone_name=clone_name, clone_root=str(root), revision=compute_fingerprint(root),
        next_action="Inspect the source entry point and record the first routes and discovery branches.",
    )
    event = {
        "iteration": 0,
        "revision": state["revision"],
        "outcome": "Initialized the run directory and manifest.",
        "next_action": state["next_action"],
    }
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir()
    for name in EVIDENCE_DIRECTORIES:
        (run_dir / "evidence" / name).mkdir(parents=True)
    with events_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    with state_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(state, indent=2) + "\n")
    return run_dir, True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a clone-this run directory without overwriting an existing run.")
    parser.add_argument("source", help="Source project reference without secrets")
    parser.add_argument("clone_name", help="Requested name of the cloned application")
    parser.add_argument("clone_root", type=Path, help="Destination directory for the clone")
    args = parser.parse_args(argv)
    try:
        run_dir, created = initialize_run(args.source, args.clone_name, args.clone_root)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Cannot initialize the run: {error}", file=sys.stderr)
        return 2
    print(f"Run directory: {run_dir}")
    if created:
        print("Created a new manifest and the first events.jsonl record.")
    else:
        print("Preserved the existing manifest. Resume from its recorded next_action.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
