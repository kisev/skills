# Workflow

This skill captures agreements the moment a conversation ends and keeps the
open-commitment list honest. It does not prepare meetings, chase people
automatically, or edit the people profile; setup and stable facts select
`team-people`.

## 1. Establish Scope

Determine whether the request is to record new agreements from a stated
conversation, close existing ones, or review what is open. The user must name
the conversation source: a call that just ended, a supplied transcript, a
messenger thread read from an exact URL, or their own statement.

## 2. Resolve the Journal

```shell
python3 scripts/team_workflow.py action-check --kind people --profile PROFILE
```

The profile resolves the default journal location and the exact person names;
match every participant to a profile report or stakeholder name before
writing. A participant absent from the profile is recorded with the name the
user confirms, and the user is offered a profile update through the confirmed
flow, never a silent one.

## 3. Extract Agreements

From the source, extract only real commitments: an owner, an action, and a
checkable completion. Prefer the source's own words for the action; normalize
only names and product terms against the profile. Distinguish explicit
agreements from intentions; record an intention as a `note`, not an
`agreement`. When the source is ambiguous about who owns an action, ask one
question instead of assigning the owner by assumption.

## 4. Record

```shell
python3 scripts/people_journal.py journal-append \
  --profile PROFILE --type agreement --person NAME \
  --text "Nikita merges the shared pipeline before Thursday's release" \
  --due 2026-10-08 --source "https://chat.example/thread/id"
```

Add `--due` only when the source states or the user confirms a date. Closings
append a new entry with `--resolves ENTRY_ID`; never rewrite an existing one.
If the manager is the owner, record it against their own name with the same
discipline: the log is symmetric.

## 5. Review Open Items

For review requests:

- `journal-open --profile PROFILE` for everything outstanding;
- agreements past `--due` are listed first with their age in days;
- report per person and per side (theirs to the manager, the manager's to
  them), then the oldest item overall.

## 6. Verify and Report

After recording, re-run `journal-open` and report the new entry ids, what
remains open, and any agreement whose due date is already past. Keep
personal, medical, and financial details out of entry text unless they change
the commitment itself. Apply `references/language-policy.md`.
