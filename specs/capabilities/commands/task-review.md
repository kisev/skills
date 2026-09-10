# `/task-review`

## Purpose

Expose storage-neutral work-item quality review.

## Triggers and Near-Misses

Route one exact source for quality review; near-miss: code review, triage, or publication.

## Inputs/Outputs

Arguments provide inline text, a local regular file, or an exact HTTPS link; output is one quality verdict and findings.

## Workflow Stages

Select, pass untrusted source arguments, normalize, review, present, report.

## Dependencies

The `task-review` skill and one readable source.

## Remote/Local Effects

Chat output by default; a file write requires preview and digest confirmation; no publication.

## Errors/Partial/Escalation

Source failures block review; unresolved quality yields `needs_clarification` or `blocked`.

## Unique Constraints

The command adds no tracker metadata or mutation semantics.

## Requirement

### REQ-I-224 - Route the task-review command

The command shall load exactly `task-review` and preserve its storage-neutral
source, verdict, chat-first output, and no-publication boundaries.

## Example

`/task-review --file task.md` returns one quality verdict without changing the file.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
