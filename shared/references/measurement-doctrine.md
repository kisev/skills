# Measurement doctrine

How to treat a number offered as proof, shared by `verification` (claims about
state and performance) and `debugging` (reproducing and fixing a defect). The
doctrine applies to every measured claim, including timing, memory, counters,
and coverage.

## Validity before the number

A wrong setup produces clean, confident, wrong numbers, and a clean number
ends an investigation. Establish that the instrument works before believing
what it reports:

- Zero is a measurement. A reading of zero, an absent metric, or a perfectly
  quiet result is a claim that needs evidence, because a disabled instrument
  reports exactly the same thing. Confirm the instrument fired and the
  workload ran, for example by asserting on an independent signal that must
  move while the measured signal stays quiet.
- Prove the workload is comparable. When the stimulus differs in size between
  runs, totals and rates are not comparable; normalize by work delivered and
  check run-to-run spread before attributing a difference to a change.
- State which validity checks ran whenever a measured number is reported. Do
  not report a number whose validity was not established.

## Before on the identical build

Never accept an "after" without a "before" on the identical scenario and
build. Comparing a fixed build against a remembered number, a nearby scenario,
or an old baseline proves nothing: the changed mechanism may not even execute
in the measured path. Re-run the unchanged build through the same scenario,
however inconvenient the rebuild, and expect to discover that a plausible fix
changes nothing.

## Revert what you cannot measure

A change that does not move its target metric is not a small win, a safety
improvement, or a cleanup; it is unvalidated complexity, and shipping it under
a measurement rationale makes the next investigation harder. Revert it and
record the hypothesis as rejected. Report negative results explicitly: a
measured non-effect is a finding the next person needs.

## The budget is the stop condition

Compare the remaining cost against the budget, not against zero. When the
measured path already sits inside budget, further work on it trades real
regression risk for an invisible gain and displaces the path that was actually
reported. Say so and stop.

## Prove by removing

To prove that a guard, a fix, or a new test actually protects, remove the
protection, watch the check go red, and restore it. A green-only run shows
that the suite passes; it does not show that the new check can fail. This is
the same red-green discipline the regression phase requires, applied when the
fix already landed before the check existed.

## Source

The measurement discipline adapts the performance-engineering skill from
`openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f` (MIT,
Copyright (c) 2025 Bohdan Triapitsyn); the pinned revision is recorded in each
skill's frontmatter `metadata.inspired-by` field. This document is an original
adaptation of that idea for this collection, not a copy of the upstream text.
