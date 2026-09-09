# Project Instructions

This repository contains the `clone-this` agent skill, not a cloned application.
The skill lives in `.devin/skills/clone-this/SKILL.md`.
Its audit reference, state template, scripts, and tests live in the same skill directory.
Keep one source copy of the skill in `.devin/skills/clone-this/`.
Users can copy the complete directory into another agent's skill directory or load `SKILL.md` directly.
The workflow must not require a tool with a Devin-specific name.
Keep manual activation controls in `SKILL.md` for Devin and Claude Code, and in `agents/openai.yaml` for Codex.
All agents use `.devin/clone-this/` for run data so existing runs and fingerprint exclusions remain valid.

The `scripts/` directory holds three standard-library Python scripts:

- `init_run.py` creates the run directory and initial manifest and never overwrites an existing run.
- `fingerprint.py` computes the content fingerprint used as the manifest `revision`.
- `verify_state.py` is the read-only completion gate; it imports the other two.

## Verification

Run the dependency-free tests from the repository root:

```sh
python3 -B -m unittest discover -s .devin/skills/clone-this/tests -v
```

Verify user-invocable skill discovery with:

```sh
devin skills list --trigger user
```

The scripts support Python 3.9 or newer.
The verifier's exit codes are `0` for a passed manifest, `1` for an incomplete manifest, and `2` for input errors.
The verifier needs the clone files at the recorded `clone_root` to recompute the fingerprint.
Fingerprint algorithm changes invalidate earlier revisions, even when the clone files stay unchanged.
The initial state template is intentionally incomplete and must not pass the completion gate.
`test_skill_package.py` covers manual activation controls, copied skill directories, and resuming a run from another installation.
These tests run Python scripts, not live agent sessions.

## Maintenance

Keep the manifest fields, audit IDs, check IDs, safe-name rule, and fingerprint exclusions consistent across the reference, template, scripts, tests, and SKILL.md.
Keep the verifier dependency-free and read-only, including when the caller omits Python's `-B` flag.
Keep `.devin/clone-this/` excluded from the fingerprint so manifest and evidence writes never change the revision they describe.
Test nested repositories, submodules, executable permissions, and filesystem failures when changing the fingerprint.
Test run identity collisions, partial initialization, concurrent initialization, and symlink paths when changing the initializer.
Preserve the distinction between declared manifest evidence and independently verified application parity.
Do not invoke the cloning workflow to test skill discovery.
Do not claim that this skill keeps a terminated agent process alive.
