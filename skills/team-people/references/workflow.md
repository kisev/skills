# Workflow

This skill owns the people profile and journal for one team. Do not combine it
with preparing a specific 1:1, drafting feedback, or writing performance
reviews: those skills consume this context. Editing the delivery profile
(projects, goals, cadence) selects the team profile workflow instead.

## 1. Establish Scope

Determine whether the request is setup, a remembered update, a journal record,
or a review. The request must identify the affected person by the exact name
used in the profile; if two reports could match, ask one question before
touching data.

## 2. Resolve the Profile

Run first:

```shell
python3 scripts/team_workflow.py action-check --kind people
```

Read the returned `context_path` before doing action work. On
`setup-required`, follow `references/people-workflow.md` Self-Setup: inspect
supplied evidence first (1:1 notes, meeting protocols, transcripts, messenger
history read through an installed messaging skill from an exact URL), derive
facts conservatively, and ask only for missing fields that evidence cannot
answer. Present the summary, then use `profile-prepare --kind people` and the
confirmed `profile-save`.

When `action-check` reports a legacy delivery profile, offer `profile-migrate`
exactly as `references/team-profile-workflow.md` describes it; never mix the
two kinds in one transaction.

## 3. Classify Remembered Facts

Route each remembered fact by durability:

- Stable facts (role, level, tenure, strengths, growth areas, motivators,
  cautions, cadence) belong in `people.json` through the confirmed update
  flow. A strength or growth area needs at least one concrete observed
  example; otherwise keep it out.
- Dated outcomes (what was agreed, decided, observed, or promised) belong in
  the journal as `agreement`, `fact`, or `note` entries with `--person`.
- Anything credential-like is rejected; never store it anywhere.

## 4. Record Journal Entries

```shell
python3 scripts/people_journal.py journal-append \
  --profile PROFILE --type agreement --person NAME \
  --text "Agreed to review the raise case after the MVP release" \
  --due 2026-10-01 --source "https://chat.example/thread"
```

Keep entries bounded and decision-relevant; resolutions close agreements by
reference (`--resolves ENTRY_ID`), never by rewriting history.

## 5. Review Open Commitments

For a review request, build the dashboard from the store, not memory:

- `journal-open --profile PROFILE` for all open agreements;
- `journal-list --profile PROFILE --type 1on1 --limit 200` to find the last
  recorded 1:1 per person and flag anyone without one for longer than the
  profile cadence;
- agreements past `--due` or older than 30 days surface first, oldest first.

Report per person: open loops, oldest outstanding item, last recorded 1:1,
and cadence gaps. Do not dump journal contents; summarize decisions.

## 6. Verify and Report

After any mutation, rerun `action-check --kind people` or re-read the changed
store to confirm the write. Report the exact fields or entries added, the
digest-bound commands that ran, and every unresolved ambiguity. Apply
`references/language-policy.md` to user-facing prose and keep personal
details out of shared channels.
