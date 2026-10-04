# `verification`

## Purpose

Gate every completion claim behind fresh verification evidence from a command
run in the current session, in any environment.

## Triggers and Near-Misses

Trigger for imminent completion, "done", "fixed", or "passing" claims and for
commits or publications about to happen; near-misses: change summaries with
no completion claim, and repositories with their own verification contracts,
which take precedence and are run instead of restated.

## Inputs and Outputs

Input is the claim about to be made and the repository's verification
surface. Output is the claim restated with its proving command and output —
or the actual failing status; nothing is written.

## Workflow Stages

Identify the command that proves the claim, run it fresh and complete, read
the full output, verify it confirms the claim, and only then report status
with evidence; a failed or unrunnable gate is reported as exactly that.

## Dependencies

The verification commands the project or user already owns; none are
invented.

## Remote/Local Effects

Read-only execution of verification commands; no external or write effects
beyond those commands themselves.

## Errors, Partial, Escalation

Partial checks, extrapolation, stale evidence, and delegated success reports
are rejected as evidence; an explicitly accepted unverified state is labeled
unverified with the missing evidence named.

## Unique Constraints

Evidence must be fresh for the current state. The rule binds paraphrases and
implications of success, not only exact words. Local project contracts
outrank this portable floor inside their repository.

## Requirement

### REQ-F-563 - No completion claims without fresh verification evidence

The skill shall require a command run in the current session whose output
proves each completion claim before the claim is made, shall reject stale,
partial, and delegated evidence, and shall defer to repository-local
verification contracts where they exist.

#### Verification

`tests/test_repository.py` pins the workflow contract phrases; the bilingual
trigger and near-miss pairs in `tests/test_stage20_verification.py` cover
routing, and the near-miss rejects only the `verification` skill itself.

## Example

`verification` blocks a "tests pass" claim until the suite runs in that
session, reports 34/34 with the command line, and reports the one failing
module instead of the intended completion sentence.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
