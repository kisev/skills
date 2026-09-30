# Workflow

This skill assembles an onboarding pack for one new team member from both
private contexts. It does not provision accounts or access (that belongs to
the team's own tools), and it does not run the first 1:1 (`team-1on1` does).

## 1. Establish Scope

Identify the new member's name, role, level, and start date, plus the
artifact form: a welcome pack for the person, a first-two-weeks plan, or
both. Confirm the workspace target for the artifact.

## 2. Load Contexts

```shell
python3 scripts/team_workflow.py action-check --profile PROFILE
python3 scripts/team_workflow.py action-check --kind people --profile PROFILE
```

From the delivery profile take: team purpose (projects, categories), wiki and
documentation sources, cadence (syncs, planning, retro), and the messenger
channel names from `sources`. From the people profile take: the manager's own
1:1 cadence, one report suitable as a buddy (matching strengths to the
newcomer's area), and stakeholder names the newcomer will meet. Never expose
`caution`, `growth_areas`, or journal history of other reports in the pack.

## 3. Build the Pack

The pack contains, in order:

1. One-paragraph team purpose derived from delivery-profile projects and
   goals, in the team's own language.
2. Cadence: the meetings that concern the newcomer, with days and channels
   from the profile.
3. First-week checklist: accounts and access requests the team's sources
   name, local environment setup, and one small starter task per delivery
   profile backlog. Mark items the profile cannot confirm as `[verify]`
   instead of inventing them.
4. People map: manager, buddy, and the stakeholders the newcomer meets in
   week one, each with one line of role description from the people profile.
5. Working agreements: where to ask questions, how review works, and what
   the delivery profile records about definition of done.

## 4. Build the First-Weeks Plan

Two weeks, dated from the start date: week one covers environment, first
task, and the first syncs; week two adds a first review by the buddy and a
first delivery step tied to a real backlog item. Include the first 1:1 slots
following the manager's cadence and a day-14 check-in with explicit
questions (what blocked you, what surprised you, what is missing). Every
plan item names an owner and a checkable outcome.

## 5. Write and Record

Write the artifact through `artifact-write` to the workspace target, then
record the onboarding in the journal:

```shell
python3 scripts/people_journal.py journal-append \
  --profile PROFILE --type note --person NAME \
  --text "Onboarding pack prepared; buddy NAME; first 1:1 scheduled day 3"
```

If the person is missing from `people.json`, offer the confirmed
`profile-prepare --kind people` update from the known start facts.

## 6. Verify and Report

Report the artifact path, items marked `[verify]`, and the day-14 check-in
date. Apply `references/language-policy.md`; the pack is the newcomer's first
impression of the team and contains no internal jargon without a gloss.
