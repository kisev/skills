# Workflow

This skill prepares feedback and difficult conversations and records what was
delivered. It does not deliver the message, decide on compensation, or write
performance reviews; those select their own skills. Mediation between two
other people is out of scope: prepare only conversations the manager personally
holds.

## 1. Establish Scope

Identify the person (report or stakeholder from the profile), the trigger
event, and the direction: reinforcing what worked, correcting behavior, or
navigating a conflict. If the user has not named a concrete observed event,
ask for one; feedback without a specific observation is not preparable.

## 2. Load Context

```shell
python3 scripts/team_workflow.py action-check --kind people --profile PROFILE
python3 scripts/people_journal.py journal-list --profile PROFILE --person NAME --limit 20
```

Read the profile entry for `caution` and `motivators`, prior `feedback`
entries, and any open agreements with this person. History decides whether
this is a first conversation or a repeated pattern; state which it is.

## 3. Draft the Message

Build three blocks in this order:

1. Observation: the specific event, its date, and the visible behavior. Quote
   the journal or the user's evidence verbatim; do not generalize into
   character traits.
2. Impact: the concrete consequence for the team, delivery, or the person's
   own stated goals from the profile.
3. Request: the change expected, checkable by a date or an observable
   outcome; for reinforcing feedback, the request names what to keep doing.

Check the draft against every `caution` entry and against these boundaries:
no comparisons with named peers, no diagnoses of intent or mental state, no
public settings for corrective messages, and no ultimatums that the user has
not explicitly decided on. For a repeated pattern, propose naming the pattern
and the escalation path instead of restating the first conversation.

For a conflict between the manager and the person, add one section with the
other side's likely view drafted honestly, and one question that tests the
manager's assumption before the meeting.

## 4. Rehearse

Provide the opening two sentences verbatim, the two most likely reactions
with a calm response for each, and the exit line if the conversation stops
being productive. Cap the preparation at one page; a longer script will not
survive the room.

## 5. Record Outcomes

After delivery, append what was actually said and agreed:

```shell
python3 scripts/people_journal.py journal-append \
  --profile PROFILE --type feedback --person NAME \
  --text "Corrective: review turnaround (observed 2026-09-20); agreed two-day SLA"
python3 scripts/people_journal.py journal-append \
  --profile PROFILE --type agreement --person NAME \
  --text "Manager stops forwarding direct requests; routes through the board" \
  --due 2026-10-10
```

Record the message the person heard, not the one that was drafted, when they
differ.

## 6. Verify and Report

Re-read `journal-list --person NAME` and report the recorded entries, the
pattern status (first occurrence or repeated), and the follow-up date the new
agreements imply. Apply `references/language-policy.md` and `humanize` to
every drafted sentence; feedback prose must survive being read by its subject.
