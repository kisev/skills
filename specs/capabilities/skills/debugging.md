# `debugging`

## Purpose

Find the cause of hard bugs by building a red-capable feedback loop before
forming hypotheses, then converging on one confirmed cause with one fix.

## Triggers and Near-Misses

Trigger for reports of broken, failing, throwing, or slow behavior and
"debug/diagnose" wording; near-misses: readability refactoring with nothing
broken, feature work that merely needs tests (routes to `tdd`), and claims
that a fix works (gated by `verification`).

## Inputs and Outputs

Input is the user's symptom and access to the failing code. Output is a
red-capable loop command, a minimized reproduction, a ranked hypothesis list
shown to the user, one fix, and a regression test; debug instrumentation is
removed before reporting.

## Workflow Stages

Phase 1 builds and tightens a fast deterministic loop that goes red on the
exact symptom; without it, no phase 2. Phase 2 reproduces and minimizes.
Phase 3 shows the user 3-5 ranked falsifiable hypotheses. Phase 4 instruments
one variable at a time and applies one fix; after three failed fixes it stops
and questions the architecture. Phase 5 locks the fix down with a regression
test and re-runs the loop.

## Dependencies

The project's test runner or script surface; no external services.

## Remote/Local Effects

Local writes limited to the fix, the regression test, and temporary tagged
instrumentation that is deleted; no external effects.

## Errors, Partial, Escalation

When no red-capable loop is possible, the skill stops and asks the user for
environment access, a redacted artifact, or instrumentation permission
instead of guessing. Secrets in shown commands and outputs are redacted.

## Unique Constraints

Hypotheses are ranked, falsifiable, and shown to the user before testing.
Fixes are not stacked: a failed fix is reverted before the next hypothesis.

## Requirement

### REQ-F-562 - Feedback loop before hypotheses, one fix with a regression test

The skill shall refuse to hypothesize before a named red-capable command has
been run once, shall minimize the reproduction, shall present 3-5 ranked
falsifiable hypotheses to the user before testing, shall apply one fix for
the confirmed cause, and shall turn the minimized repro into a regression
test or record the missing seam as a finding.

#### Verification

`tests/test_repository.py` pins the workflow contract phrases including the
loop gate and the three-failures architecture rule; the bilingual trigger and
near-miss pairs in `tests/test_stage20_verification.py` cover routing.

## Example

`debugging` reduces a flaky checkout failure to a two-line curl against a
fixture, shows four ranked hypotheses, confirms the timezone-dependent sort
with one tagged log, reverts the first wrong fix, applies one change, and
leaves a regression test at the service seam.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
