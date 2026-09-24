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
explicit statement that no clarification questions remain, followed by the invocation-specific boundary below.
The final decision boundary names the expected result, supported scenarios,
acceptance checks, constraints, accepted risks, deferred work, and the basis of
user decisions. It stays in chat and does not create an artifact.

## Workflow Stages

Resolve dependencies, inspect facts, present the proposed task, ask the next
independent question if needed, report, and stop or return decisions to the caller.

## Dependencies

Repository evidence and user answers.

## Remote/Local Effects

Reads local evidence; no writes or remote effects.

## Errors, Partial, Escalation

Unknown prerequisites block dependent questions; unresolved answers escalate.

## Unique Constraints

Questions follow dependency order and do not repeat answered decisions. Do not
invent questions or require redundant confirmation when facts suffice. Interview
answers do not expand authorization or clear pending publication gates.

## Requirement

### REQ-F-102 - Ask dependency-bounded questions

The skill shall recognize direct and conditional invitations to clarify by intent,
ask only questions whose answers determine the next safe decision, explicitly
report when no clarification questions remain, and distinguish invocation contexts.
An explicit user invocation, including a conditional invitation, shall stop for
manual continuation. Internal clarification of an already-authorized workflow
shall return decisions to that caller, including `task-prepare`, which may resume
within the agreed scope. Explicit interview intent takes precedence; ambiguity
shall stop. Neither mode shall expand scope or clear pending mutation gates.
For review follow-ups, the skill shall assess the agreed requirement, reachable
scenario, user impact, relation to changes, and proportionate remedy before
asking implementation questions. It shall distinguish mandatory corrections,
optional hardening, pre-existing debt, and new features; reproduction and
severity alone shall not make a candidate mandatory. It shall preserve accepted
limitations until facts or user decisions change, explain the cost of an approved
scope expansion, and consider simplification when repeated fixes expand one
mechanism. Extra structural fields shall not be presented as proof of semantic
reasoning quality. Completion shall mean satisfying the agreed result and checks,
not proving the absence of every possible defect or reaching a fixed round limit.

## Example

`askme` asks for the exact external boundary before selecting an API workflow.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
