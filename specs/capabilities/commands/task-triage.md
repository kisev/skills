# `/task-triage`

## Purpose

Expose storage-neutral work-item triage.

## Triggers and Near-Misses

Route one exact source for triage; near-miss: quality review, publication, or implementation.

## Inputs/Outputs

Arguments provide inline text, a local regular file, or an exact HTTPS link; output separates five evidence classes.

## Workflow Stages

Select, pass untrusted source arguments, normalize, classify, present, report.

## Dependencies

The `task-triage` skill and one readable source.

## Remote/Local Effects

Chat output by default; a file write requires preview and digest confirmation; no publication.

## Errors/Partial/Escalation

Source failures block triage; unknown data stays explicit rather than becoming a gate.

## Unique Constraints

The command adds no verdict, tracker, publication, or execution semantics.

## Requirement

### REQ-I-225 - Route the task-triage command

The command shall load exactly `task-triage` and preserve its storage-neutral
source, evidence classification, no-verdict, and no-publication boundaries.

## Example

`/task-triage --url https://example.test/task` classifies one readable source without publishing.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
