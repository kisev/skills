# Design

## Context

The skill is text-only: a thin `SKILL.source.md` delegating to a
decision-interview workflow, backed by the shared question guidelines,
clarity rules, and necessity doctrine materialized inside the archive
through `shared/manifest.json`. The work-item family runtime
(`shared/references/work_item.py`) already carries the machine contract for
the optional premortem. The eval corpus covers activation (bilingual
trigger and near-miss) and the command contract. `goal` runs its own
interview paragraph with a second premortem formulation; the legacy
`specs/capabilities/**/askme.md` retirement stays in
`renegotiate-foundation`. The owner reviewed the audit and accepted fixes
1–5 below; the ceremony, continuation semantics, and two-mode
authorization core stay as implemented.

## Goals / Non-Goals

**Goals:**

- One exhaustive behavior contract for askme, checked requirement by
  requirement against the skill text.
- The five accepted fixes: canon-aligned round independence, one premortem
  canon, a corpus-wide conflict order, no duplicate necessity delegation,
  and one bounded mode clarification instead of a bare stop.

**Non-Goals:**

- Redesigning the ceremony (statement rebuild, task block, closing
  boundary) — owner-confirmed as is.
- Retiring the legacy spec documents — `renegotiate-foundation` owns that.
- Corpus-level restructuring of the question guidelines (the Goal Mode
  authorization machinery) — recorded as a renegotiation candidate, not
  this change.

## Decisions

### D1. Capture plus a bounded, owner-accepted rework

The delta captures the behavior as implemented, amended by exactly the five
audit fixes. Everything else the audit found stays out; corpus-level
observations were reported separately to the owner.

### D2. Round independence follows the shared canon

The workflow's "ask the prerequisite alone" over-serializes rounds and is
stronger than the canon's frontier model. The fix aligns the workflow (and
this spec) with the question guidelines: dependents wait for the
prerequisite's actual answer; independent questions may join the round.

### D3. One premortem canon in the necessity doctrine

The premortem prose moves into `shared/references/necessity-doctrine.md`
beside its machine contract in `work_item.py`; askme and `goal` keep a
one-line delegation. `goal` does not materialize the doctrine today, so
`shared/manifest.json` gains the `goal/references/necessity-doctrine.md`
destination and `task generate` flows it into the built archive — the
delegation stays self-contained.

### D4. Conflict order becomes corpus canon

The recommendation-conflict order (safety and confirmation > explicit user
request > pipeline > layering) moves from askme's local "Composition
Protocol" into the shared question guidelines, which the interviewing skills
already materialize. askme's section shrinks to the premortem delegation
and is renamed accordingly.

### D5. Ambiguous mode is clarified, not fatal

A bare stop on ambiguous invocation context contradicts the skill's own
contradiction doctrine and leaves the user with neither an interview nor a
resumed task. Exactly one bounded mode question is asked; only an
unresolved ambiguity stops. Authorization safety is unchanged: the answered
mode still applies its own boundary, and neither mode clears pending gates.

### D6. Verification levels

Activation and command coverage already run in `task eval:check`. The
deeper interview behaviors are verified by the audit reading. Because this
change edits skill text (askme, goal) and shared canon, the repository
rules apply: full pressure runs for askme and goal, `task generate` and
`generate:check` for the new materialization, and the corpus checks.

## Risks / Trade-offs

- \[Shared-canon edits ripple into every materializing archive] → content
  edits are additive (one premortem section, one conflict-order paragraph);
  `task generate:check` and the corpus checks pin the result.
- \[Two pressure runs instead of one] → goal's workflow is touched by the
  premortem delegation; the rule is per edited skill, and the runs are
  independent.
- \[Mode clarification invites marker gaming] → the clarification asks the
  user, not the document; untrusted markers keep losing to the actual
  request, and an unanswered clarification still stops.
