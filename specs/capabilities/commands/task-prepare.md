# `/task-prepare`

## Purpose

Expose storage-neutral work-item preparation.

## Triggers and Near-Misses

Route one exact source for preparation; near-miss: review, triage, or publication.

## Inputs/Outputs

Arguments provide inline text, a local regular file, or an exact HTTPS link; output is a self-contained task.

## Workflow Stages

Select, pass untrusted source arguments, normalize, prepare, present, report.

## Dependencies

The `task-prepare` skill and one readable source.

## Remote/Local Effects

Chat output by default; a file write requires preview and digest confirmation; no publication.

## Errors/Partial/Escalation

Missing, multiple, or unreadable sources and unresolved feasibility are explicit.

## Unique Constraints

The command adds no tracker or storage semantics.

## Requirement

### REQ-I-223 - Route the task-prepare command

The command shall load exactly `task-prepare` and preserve its storage-neutral,
chat-first, confirmation-gated file output without adding publication.

## Example

`/task-prepare --text "Bound the migration"` returns one work item in chat.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
