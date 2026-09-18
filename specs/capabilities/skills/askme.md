# `askme`

## Purpose

Interview for decisions that determine implementation boundaries.

## Triggers and Near-Misses

Trigger for an invitation to ask questions or clarify requirements, including
"ask me", "askme", and the Russian discovery terms in the skill description.
Match equivalent intent, not an exhaustive phrase list. Conditional invitations
also trigger the workflow, even when the task is already fully specified.
Near-misses are quoted examples, negated requests, and discussion of the skill
without a separate invitation to interview the user.

## Inputs and Outputs

Input is a goal and repository facts. Output is ordered decision answers or an
explicit statement that no clarification questions remain, followed by a stop.

## Workflow Stages

Resolve dependencies, inspect facts, present the proposed task, ask the next
independent question if needed, report, and wait for manual continuation.

## Dependencies

Repository evidence and user answers.

## Remote/Local Effects

Reads local evidence; no writes or remote effects.

## Errors, Partial, Escalation

Unknown prerequisites block dependent questions; unresolved answers escalate.

## Unique Constraints

Questions follow dependency order and do not repeat answered decisions. Do not
invent questions or require redundant confirmation when facts suffice. Interview
answers alone do not authorize implementation or automatic resumption of a
calling workflow, including `task-prepare`.

## Requirement

### REQ-F-102 - Ask dependency-bounded questions

The skill shall recognize direct and conditional invitations to clarify by intent,
ask only questions whose answers determine the next safe decision, explicitly
report when no clarification questions remain, and always stop for explicit
manual continuation before another workflow or the calling task resumes.

## Example

`askme` asks for the exact external boundary before selecting an API workflow.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
