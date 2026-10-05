# `tdd`

## Purpose

Drive feature and bug-fix work through the test-first red-green cycle so the
produced tests specify behavior through public interfaces and survive
refactors.

## Triggers and Near-Misses

Trigger for test-first feature or fix requests and "red-green-refactor"
wording; near-misses: running or summarizing an existing suite without new
behavior, debugging a live failure (routes to `debugging`), and behavior
review (routes to `code-review`).

## Inputs and Outputs

Input is the agreed feature or fix and the confirmed seam list. Output is new
tests at agreed seams plus minimal implementation, one vertical slice at a
time; the repository receives both.

## Workflow Stages

Agree the seams with the user; then repeat the slice: write one failing test
(red), implement only enough to pass (green), learn, and choose the next
behavior. Refactoring stays outside the loop and belongs to review.

## Dependencies

The project test runner at the agreed seams; no external services.

## Remote/Local Effects

Local writes of tests and implementation inside the working tree only; no
external effects.

## Errors, Partial, Escalation

A needed but unagreed seam is proposed to the user instead of tested at
silently; a test that cannot fail for the expected reason is fixed or deleted
before the slice continues.

## Unique Constraints

No test is written at an unconfirmed seam. Expected values come from an
independent source of truth, never recomputed the way the code computes them.

## Requirement

### REQ-F-561 - Test-first slices at user-agreed seams

The skill shall confirm the seams under test with the user before writing any
test, shall work in vertical slices of one failing test followed by one
minimal implementation, and shall refuse tautological, horizontally sliced,
and implementation-coupled tests.

#### Verification

`tests/test_repository.py` pins the workflow contract phrases, and the
bilingual trigger and near-miss pairs in `tests/test_stage20_verification.py`
cover routing; the near-miss rejects only the `tdd` skill itself.

## Example

`tdd` agrees with the user that pagination is observable through the list
endpoint, then adds one failing test for the first page, implements page
slicing, and repeats for sorting — never writing the whole test file first.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
