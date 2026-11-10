---
audience: maintainer
review: {"components": ["skill-acceptance"], "sources": ["tests/integration/acceptance.py", "tests/integration/acceptance_probes.py", "taskfile.yml"], "contracts": ["docs/reviewmatic-test-matrix.md"]}
---

# Run the Live Skill Acceptance

[Русский](../ru/how-to/skill-acceptance.md)

## What It Is

`task acceptance` is the single launcher over every live skill family. One
command drives the GitLab and Mattermost live runs and a minimal behavioral
probe for every skill the harnesses do not cover. It prints line-by-line progress (skill,
family, stage, model, elapsed seconds) and leaves machine and human reports.

The umbrella is user-run and explicitly optional, the same class as
`live:run`: it needs provider credentials and never runs inside `task check`,
`check:core`, Lefthook hooks, CI, or the gate registry.

## Run It

1. Build and start what the harness families need: `task skills:build`
   (the task does this), and for the live families `task env:up`.
2. Export explicit provider credentials, for example
   `OPENCODE_CONFIG_CONTENT` (or a provider API key). Credentials are never
   copied from your global OpenCode profile into the isolated hosts by the
   repository; you pass them explicitly.
3. Run `task acceptance` for all 44 skills, or `task acceptance SKILL=eli5`
   for one entry. `task acceptance:plan` prints the coverage plan without
   running anything.

The default model is the cheap flash-class `zai-coding-plan/glm-5.3-flash`.
Every `EVAL_*` variable (`EVAL_MODEL`, `EVAL_TIMEOUT`, `EVAL_MAX_TOKENS`,
`EVAL_MAX_COST`) overrides the defaults. Before the first run the launcher
prints the selected model, the budget guardrails, and the last measured
cost. Selecting a model that is not cheap (flash-class) fails unless you
pass `--yes` or export `ACCEPT_EXPENSIVE=1`.

## What Runs

- `mattermost-live` (`mattermost`, `mattermost-triage`) and `gitlab-live`
  (`mr-prepare`): the existing live harnesses against the dev stacks. When
  a stack is down or its fixtures are missing, the family is skipped with
  the exact reason instead of failing.
- `gitlab-review-live` (`mr-review`): the full review on the disposable
  local GitLab stand through the opencode host. It provisions a project and
  a merge request with a real diff, checks the skill out at the exact
  reviewed revisions, seeds the startup answers in the prompt, records the
  runbook and the draft block, moves the head and reviews again to exercise
  `ocr session compare`, then executes the draft block (draft notes only,
  never a publish) and deletes the fixture. The family is skipped with the
  exact reason when the stand, `ocr`, or the two reviewer aliases are absent.
- `behavior-probe` (34 skills): a minimal live run per skill — the probe
  installs only that skill into an isolated host sandbox, seeds small
  fixture files, and machine-checks the produced artifact (demanded section
  headers, grounded fixture facts, answer contract). Transport-level
  failures retry once.
- Skips (6 skills): skills a synthetic fixture cannot exercise meaningfully
  (`taskmatic` needs its board service, `rtk` and `ast-grep` drive CLIs the
  sandbox does not pin). Each skip prints its reason in the report; a skip
  is a non-run, never a green check.

## mr-review live prerequisites

The `gitlab-review-live` family needs, in addition to the dev stacks:

1. The `ocr` CLI at the tested minimum (1.13.6) on `PATH`.
2. Two reviewer aliases, either exported as
   `EVAL_OCR_REVIEWERS=alias=provider:model,alias=provider:model` or present
   in `~/.reviewmatic/reviewers.json`. Providers must appear in
   `ocr llm providers` and be configured in OCR's own configuration.
3. Provider credentials for the opencode host (`OPENCODE_CONFIG_CONTENT` or a
   provider key) and for OCR.

Run `task acceptance SKILL=mr-review`. Only the local stand fixture project
changes; the generated draft block creates GitLab draft notes, and the
harness deletes the merge request and its branches afterwards.

## Where the Reports Land

Every umbrella run writes to `.build/acceptance/<timestamp>/`:

- `result.json` — the machine aggregate: config, per-family verdicts,
  coverage, durations, and report pointers.
- `summary.md` — the human report: verdict, coverage table (skill, family,
  status, report or reason), skips with reasons, failures with reasons.
- `.build/acceptance/latest.json` points at the newest run.

Each family keeps its own evidence: the GitLab and Mattermost live runs in
their `reports/latest.json` trees, and every probe attempt keeps its sandbox,
`agent-output.txt`, and checks. The `gitlab-review-live` evidence keeps both
runbooks, both agent transcripts, the executed draft block, and `live.json`
with the reviewed head and the reviewer aliases; it never enters Git.

## Hand the Report to the Master Session

Paste into the master session: the verdict line, the coverage table, the
failure reasons, and the `result.json` path printed by the run. The raw
attempt outputs stay in the private report directories referenced by the
machine report; do not paste provider responses or redacted-secrets-free
logs wholesale without reading them first.
