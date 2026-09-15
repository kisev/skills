# `code-review`

## Purpose

Review a local WIP or exact GitLab change for defects and contract regressions.

## Triggers and Near-Misses

Trigger for review; near-miss: preparing a merge request description.

## Inputs and Outputs

Input is an exact scope or WIP. Remote output is ranked findings, MR metadata
assessment, SemVer impact with rationale, and a local manual publication preview.

## Workflow Stages

Resolve boundary, inspect diff and contracts, critic pass, classify findings, report.

## Dependencies

Git, tests, and optional GitLab read-only evidence.

## Remote/Local Effects

Local reads and private immutable artifact/body writes; external reads only for
exact review targets. The skill may prepare manual GitLab note commands but never
executes external writes.

## Errors, Partial, Escalation

Missing head or critic evidence is blocked, not silently ignored.

## Unique Constraints

Findings precede summaries and use exact file/line references. Artifact paths are
reported as plain absolute paths. Every remote finding receives an immutable body
and manual publication command even when the MR is merged or closed.

## Requirement

### REQ-F-105 - Review exact changes

The skill shall review the complete exact diff, rank confirmed risks before the
summary, assess title, description, labels, workflow state, and SemVer impact,
and prepare one preflight-bound manual note command per finding without executing
it.

## Example

`code-review` rejects a review when the independent critic receipt is absent.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
