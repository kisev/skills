# Workflow

This skill reads the recorded signals and reports what they prove about team
health. It does not survey people behind the manager's back, diagnose
individuals, or aggregate private journal contents into shared channels. The
team's delivery retrospective selects `team-retro`.

## 1. Establish Scope

Identify the review period (strict `[since, until)`) and the audience: the
manager alone, or a team-view artifact with private details stripped.
Confirm the workspace target when an artifact is requested.

## 2. Load Signals

```shell
python3 scripts/team_workflow.py action-check --kind people --profile PROFILE
python3 scripts/people_journal.py journal-list --profile PROFILE \
  --since START --until END --limit 1000
python3 scripts/team_workflow.py action-check --profile PROFILE
```

Delivery load comes from the team evidence store over the same window,
collected exactly as `team-retro` prescribes when freshness matters; for a
health review, totals per person suffice.

## 3. Compute the Signal Set

From the journal and profiles, compute per person and for the team:

- 1:1 cadence adherence: meetings recorded versus the profile cadence, and
  the longest gap;
- open-commitment age: open agreements older than their due date or 30 days;
- feedback balance: reinforcing versus corrective entries recorded;
- growth-thread movement: 1:1 entries touching a profile growth area;
- delivery load: merged or released volume from evidence, marked with its
  completeness.

A missing signal is reported as missing; do not substitute impressions for
absent records. Signals are observations, not verdicts: the manager
interprets.

## 4. Optional Survey

When the user wants a pulse, draft five or fewer anonymous questions about
clarity of priorities, workload sustainability, support availability, and
process friction, in the team's language. The manager distributes and
collects them manually through their own channel; this skill never sends,
collects, or attributes responses. Tallying supplied anonymous answers is in
scope; attributing them to named people is not.

## 5. Render the Review

For the manager: per-person signal table, team aggregates, and the two or
three signals that most need a decision, each with the journal dates that
back it. For the team view: aggregates and team-level zones of attention
only, no per-person rows, no names beside weak signals. Write artifacts with
`artifact-write`; recommend the natural follow-up skill per zone (`team-1on1`
for cadence gaps, `team-feedback` for balance, `team-agreements` for aged
commitments) without running them.

## 6. Verify and Report

Report the period, signal completeness, artifact paths, and every limitation
(tiny evidence, missing cadence, partial delivery data). Record a `note`
entry with the review date when the manager accepts the findings. Apply
`references/language-policy.md`; findings about people stay with the manager.
