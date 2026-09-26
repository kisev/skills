# Workflow

This skill turns recorded journal history into performance documents for one
named report. It does not decide ratings, submit anything to HR systems, or
replace a conversation with a document; the manager owns every judgment. Team
level aggregation selects `team-retro`; a single difficult conversation
selects `team-feedback`.

## 1. Establish Scope

Identify the person, the period (strict `[since, until)`), and the artifact:
performance summary, bonus or raise justification, or a growth-plan draft.
Confirm any length or format constraint the target system imposes (for
example a character limit) before drafting.

## 2. Load Evidence

```shell
python3 scripts/team_workflow.py action-check --kind people --profile PROFILE
python3 scripts/people_journal.py journal-list \
  --profile PROFILE --person NAME --since START --until END --limit 500
```

Read the profile facts (role, level, since, strengths, growth areas) and the
period's entries: `fact`, `agreement`, `feedback`, and `1on1` outcomes. When
delivery numbers are also required, collect them from the team evidence store
through the delivery profile exactly as `team-retro` describes collection;
never mix the two profiles in one write.

## 3. Build the Fact Base

Group the period's entries into outcomes, commitments kept or missed, and
feedback delivered. An outcome qualifies only with a dated record; a
characteristic without a record is an assumption and must be marked as one or
dropped. Flag any quarter with fewer than three recorded facts as evidence
too thin for a rating claim.

## 4. Draft the Document

- Performance summary: outcomes first, each as "result - why it mattered",
  then kept and missed commitments, then the growth thread progress against
  the profile's growth areas.
- Bonus or raise justification: two or three strongest outcomes with dates,
  stated relative to the level expectations from the profile, inside the
  target system's length limit. No comparisons with named peers; no
  promises about decisions the manager does not own.
- Growth-plan draft: two or three growth areas from the profile, each with a
  next concrete step, an owner, and a checkable outcome by a date.

Every claim links back to a journal entry date. Apply `humanize` and
`references/language-policy.md`; the text must read as the manager's own
voice, not a filled template.

## 5. Record and Hand Over

Write the artifact to the workspace through `artifact-write`, then append the
completion to the journal:

```shell
python3 scripts/people_journal.py journal-append \
  --profile PROFILE --type fact --person NAME \
  --text "Q3 review draft prepared; bonus justification cites 3 recorded outcomes"
```

The user submits to external systems manually; this skill never publishes.

## 6. Verify and Report

Report the artifact path, the fact counts behind each section, thin-evidence
warnings, and open commitments that carry into the next period. Re-read
`journal-open --person NAME` after any new agreements.
