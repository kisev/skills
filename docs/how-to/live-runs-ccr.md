# Run synthetic live checks

[Русский](../ru/how-to/live-runs-ccr.md)

Live checks (verification speed 2) send one real-model run against a
versioned scenario and assert the observable outcome. Everything is pinned:
the engine and its engine profile come from `evals/live/profile.json`; the
fixture, the prompt, and the assertions come from
`evals/live/<scenario>/`.

## Prerequisites

1. Install [ccr](https://github.com/musistudio/claude-code-router) on the
   host: `npm install -g @musistudio/claude-code-router`, then confirm
   `ccr --help` answers.
2. Create a dedicated ccr profile named `skills-tests-claude`
   (`~/.claude-code-router/profiles/skills-tests-claude/`) and choose its
   routing and model inside that profile — the model is never the
   repository's concern. Keep provider keys on the host: the repository
   pins names, never credentials and never models.
3. Build the skill archives once: `task generate`.

## Check the setup

```shell
task live:preflight
```

The preflight verifies the profile file, the ccr binary, the
`skills-tests-claude` profile, and every scenario format — without any
model call. Every red line names the exact repair.

## Run a scenario

```shell
task live:run -- --scenario agents-md-mirror
task live:run -- --scenario agents-md-mirror --variant no-symlink
task live:run -- --all
```

`--all` runs the default variant of every scenario (the release sweep).

The run stages the fixture into an isolated empty workdir, runs the engine
subprocess under a positive environment allowlist (a credential cannot ride
along under any name) with scoped permissions (file edits auto-accepted;
wider tool grants come from the scenario's `allowed_tools`, never a blanket
bypass), and writes a report with a verdict and a redacted transcript under
`.build/live-runs/<timestamp>-<scenario>-<variant>/`. The run also
fingerprints the host-side engine profile directory before and after and
records any drift in the report — informational evidence of session
artifacts, the documented cost of the real HOME, not a leak.

## When to run

One run on a material behavior change of a skill; a sweep over every
scenario before a release. A reproducible failure first sediments as a
speed-1 regression check, then the scenario re-runs green. The system
contract lives in the `live-runs` change under `openspec/changes/`.
