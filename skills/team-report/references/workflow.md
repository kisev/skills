# Workflow

This skill produces the stakeholder-facing periodic roll-up: a quarterly
report for leadership or the theses for a quarterly demo. The team's own
retrospective, monthly delivery review, and Marp presentation flow select
`team-retro`; slide imagery selects `slides-prompts-prepare`.

## 1. Establish Scope

Identify the period (strict `[since, until)`), the audience (leadership,
directors, or a broad demo), and the artifact form. Confirm the workspace
target and any house format from the delivery profile's `actions` or the
user's statement.

## 2. Collect Evidence

Resolve the delivery profile with `scripts/team_workflow.py action-check`,
then follow the same evidence rules as `team-retro`: every included project
contributes, the bundled GitLab collector runs with `--resume-profile` for
configured metrics sources, other sources are recorded with `evidence-record`,
and the result must be complete or explicitly partial.

Resolve the people profile with `action-check --kind people` and read the
period's journal (`journal-list --since --until --limit 500`) for
delivery-relevant facts: releases supported, agreements with other teams,
and kept commitments. Personal, medical, and financial entries never enter a
stakeholder artifact.

## 3. Interpret Delivery Correctly

Apply the delivery-signal discipline from `team-retro`: released work uses
`released_at`, tags are not releases, pre-release suffixes are excluded, and
movable aliases never count. Achievement claims require evidence of user or
engineering value; version bumps and mechanical updates count in totals only.

## 4. Draft the Roll-Up

Structure by audience:

- **Leadership report**: one-paragraph TLDR; three to five outcomes as
  "result - business or engineering value" with links; delivery totals for
  the period; dependencies and risks with owners; next-period focus from
  current goals. Dry tone, no personnel details, no internal jargon without
  a gloss.
- **Demo theses**: per product, what shipped, what it unlocks for users, and
  one live-demo point each; unfinished work appears only as a named next
  step, never as a padded achievement.

Credit external contributors by policy exactly as `team-retro` prescribes.
The manager's own assessment of the period is written by the manager; this
skill assembles and formats, it does not editorialize morale.

## 5. Render and Record

Write the artifact with `artifact-write`, then snapshot it:

```shell
python3 scripts/evidence_store.py artifact-record \
  --profile PROFILE --target ARTIFACT_PATH \
  --since START --until END --source SOURCE_KEY
```

End with the "Data sources" section rendered from `evidence-show` exactly as
`team-retro` requires. Journal a completion note when the report cites
journal facts.

## 6. Verify and Report

Run the profile's `verification_command` when present. Report the artifact
path, evidence completeness, totals, and every `[no data]` gap. The user
publishes manually; this skill never posts.
