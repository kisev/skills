# debugging Workflow

A discipline for hard bugs. Phases run in order; skip one only with an
explicit justification the user can see.

## Phase 1: Build a feedback loop

This phase is the skill; everything after it consumes its output. A tight
pass/fail signal that goes red on this exact bug makes bisection, hypothesis
testing, and instrumentation mechanical. Without one, staring at code does
not scale.

Construct a loop that drives the actual bug code path and asserts the user's
exact symptom. Prefer, in order: a failing test at a reachable seam, a script
or CLI invocation against a fixture input, a replay of a captured payload, a
headless browser run, or a minimal harness around one component. For
non-deterministic bugs the goal is a higher reproduction rate, not a clean
repro: loop the trigger until the failure is frequent enough to debug
against. Tighten the loop until it is fast, deterministic, and assertable in
one command.

Completion criterion: one named command you have already run once, showing
red output. Reading code to build a theory before that command exists is the
exact failure this phase prevents. **No red-capable command, no phase 2.**
When a loop is genuinely impossible, stop, list what you tried, and ask the
user for environment access, a redacted artifact, or permission to add
temporary instrumentation.

Redact secrets from every command and output you show; a captured loop may
carry credentials, so keep them in the environment and quote only signal
lines.

## Phase 2: Reproduce and minimize

Run the loop and confirm it reproduces the failure the user described — not a
nearby failure — across repeated runs. Then shrink it to the smallest scenario
that still goes red: cut inputs, callers, config, and steps one at a time,
re-running the loop after each cut, and keep only load-bearing elements. A
minimal repro shrinks the hypothesis space and becomes the regression test.

## Phase 3: Hypothesize

Generate 3-5 ranked falsifiable hypotheses before testing any of them; a
single first idea anchors the search. Each hypothesis states a prediction:
what change should make the bug disappear or worse. A hypothesis without a
testable prediction is discarded or sharpened.

Show the ranked list to the user before testing. They often hold domain
knowledge that re-ranks it instantly or have already ruled items out. Do not
block on their reply; proceed with your ranking if they are away.

## Phase 4: Instrument and fix once

Every probe maps to one prediction, and one variable changes at a time.
Prefer a debugger or targeted logs at the boundaries that distinguish
hypotheses; never log everything and grep. Tag every debug log with a unique
prefix so cleanup is one search, and remove all of it before reporting done.

Apply one fix for the confirmed cause. Do not stack speculative changes: if
the first fix does not turn the loop green, revert it and test the next
hypothesis. Count failed fixes: after three failed fixes, stop and question
the architecture instead of attempting a fourth — repeated failures at the
same seam usually mean the design resists the fix, and that finding goes to
the user as a question, not as more patches.

## Phase 5: Regression test

Turn the minimized repro into a failing test at a seam that exercises the
real bug pattern, watch it fail, apply the fix, watch it pass, and re-run the
phase 1 loop against the original scenario. When the fix landed before the
test exists, the red step is prove by removing: revert the fix, watch the new
test go red, restore it, and watch it go green. If no correct seam exists, that
is itself a finding: record it and raise it with the user. Agreeing new test
seams follows the `tdd` skill. The regression test then runs with the suite
per this repository's local verification contracts, which take precedence
over any generic checklist.

## Measured bugs

A bug reported as slow, heavy, or growing is a measurement problem before it
is a code problem. Apply `references/measurement-doctrine.md`: zero is a
measurement, so confirm the instrument fired and the workload ran before
trusting a quiet profile; capture the before on the identical build and
scenario; revert a "fix" you cannot measure; and treat the user-facing budget
as the stop condition instead of optimizing toward zero.

## Cleanup

Before reporting done: the original repro no longer fails, the regression
test passes or the missing seam is documented, every tagged debug log is
removed, throwaway harnesses are deleted, and the confirmed hypothesis is
stated in the commit or report so the next debugger learns from it.

## Credits

Inspired by `mattpocock/skills` (`engineering/diagnosing-bugs`) and
`obra/superpowers` (`systematic-debugging`), both MIT: Copyright (c) 2026
Matt Pocock and Copyright (c) 2025 Jesse Vincent, and by the
performance-engineering skill in `openchamber/openchamber` (MIT,
Copyright (c) 2025 Bohdan Triapitsyn); pinned revisions are recorded in the
frontmatter `metadata.inspired-by` field. This workflow is an
original adaptation of those ideas for this collection, not a copy of the
upstream text.
