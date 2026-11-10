# Run synthetic live checks

[Русский](../ru/how-to/live-runs-ccr.md)

Live checks (verification speed 2) send one real-model run against a
versioned scenario and assert the observable outcome. Everything is pinned:
the engine and its engine profile come from a profile file, the fixture, the
prompt, and the assertions come from `evals/live/<scenario>/`. The default
profile is `evals/live/profile.json` (ccr); `--profile` selects another host
without changing the scenario.

## Prerequisites

1. Install [ccr](https://github.com/musistudio/claude-code-router) on the
   host: `npm install -g @musistudio/claude-code-router`, then confirm
   `ccr --help` answers.
2. Create a dedicated ccr profile named `skills-tests-claude`
   (`~/.claude-code-router/profiles/skills-tests-claude/`) and choose its
   routing and model inside that profile — the model is never the
   repository's concern. Keep provider keys on the host: the repository
   pins names, never credentials and never models.
3. For opencode, install the CLI and choose the host-side agent named by
   `engine_profile` in `evals/live/profiles/opencode.json` (default `build`).
   The agent owns the model and provider configuration.
4. For codex, install the CLI and create the host-side profile named by
   `engine_profile` in `evals/live/profiles/codex.json` (default `live-runs`)
   at `$CODEX_HOME/live-runs.config.toml` (`~/.codex` by default). The profile
   owns the model and provider configuration.
5. Build the skill archives once: `task generate`.

## Check the setup

```shell
task live:preflight
task live:preflight -- --profile evals/live/profiles/opencode.json
task live:preflight -- --profile evals/live/profiles/codex.json
```

The preflight verifies the profile file, the host CLI, the host-side profile
where the host has one, and every scenario format — without any model call.
Every red line names the exact repair.

## Run a scenario

```shell
task live:run -- --scenario agents-md-mirror
task live:run -- --scenario agents-md-mirror --variant no-symlink
task live:run -- --scenario mr-review-untrusted --profile evals/live/profiles/opencode.json
task live:run -- --all
```

`--all` runs the default variant of every scenario (the release sweep).

The run stages the fixture into an isolated empty workdir, runs the engine
subprocess under a positive environment allowlist (a credential cannot ride
along under any name) with scoped permissions (edits stay inside the staged
workdir; wider tool grants come from the scenario's `allowed_tools` or the
host-side agent, never a blanket bypass), and writes a report with the host,
engine profile, verdict, and a redacted transcript under
`.build/live-runs/<timestamp>-<scenario>-<variant>/`. The opencode run stages a
project config that denies shell execution and network fetches, and the codex
run uses its `workspace-write` sandbox; the run also fingerprints the bounded
host-side engine state before and after and records any drift in the report —
informational evidence of session artifacts, the documented cost of the real
HOME, not a leak.

## Cross-host evidence

Run the text scenarios guided once per host plus one no-guidance control per
host, read the outputs manually, and record the host matrix in the reports.
The full five-repeat pressure stays on the default ccr host; the cross-host
pass is parity evidence, not a second pressure run. A host whose CLI or
host-side profile is missing is reported blocked with the exact name; never
simulate a pass or substitute another host.

## When to run

One run on a material behavior change of a skill; a sweep over every
scenario before a release. A reproducible failure first sediments as a
speed-1 regression check, then the scenario re-runs green. The system
contract lives in the `live-runs` change under `openspec/changes/`.
