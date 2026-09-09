# Clone This

Clone an existing app under a new name. The agent discovers features, builds a separate copy, and repeats visual and behavior tests until completion or a blocker.

## Install

Copy `.devin/skills/clone-this/` to your agent's skill directory:

| Agent | Project path | User path (macOS/Linux) |
| --- | --- | --- |
| Claude Code | `.claude/skills/clone-this/` | `~/.claude/skills/clone-this/` |
| Codex | `.agents/skills/clone-this/` | `~/.agents/skills/clone-this/` |
| Devin CLI | `.devin/skills/clone-this/` | `~/.config/devin/skills/clone-this/` |

Keep the supporting files with `SKILL.md`. The scripts require Python 3.9 or newer.

## Use

Give the source app's name and a name for your copy.

In Claude Code or Devin CLI, use:

```text
/clone-this Linear "New Product"
```

In Codex, use:

```text
$clone-this Linear "New Product"
```

You can also provide a URL, repository, or local directory instead of an app name. With other agents, ask them to follow the installed `SKILL.md` with the source app and new name.

## Progress and completion

Runs save progress and evidence under `.devin/clone-this/<safe-name>/` inside the new app. This data path does not require Devin. To resume, give the agent the same app directory and ask it to continue through this skill.

When switching agents, stop the first agent before the next agent writes to the run. Keep the saved run files and app directory in place. Saved progress does not keep a stopped agent running.

Completion requires passing tests, evidence for every discovered requirement, and zero unexplained screenshot differences. Missing access or services remain blockers. The completion script reads the recorded evidence but does not independently prove that the apps match.

See [SKILL.md](.devin/skills/clone-this/SKILL.md) for the workflow and [the audit reference](.devin/skills/clone-this/references/parity-audit.md) for completion rules.

## Tests

Run the tests from the repository root:

```sh
python3 -B -m unittest discover -s .devin/skills/clone-this/tests -v
```

These tests cover the scripts and skill package. They do not run live agent sessions or test a cloned app.
