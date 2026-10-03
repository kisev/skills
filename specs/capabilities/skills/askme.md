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
user decisions. It stays in chat and does not create an artifact. On every call,
including the first and a no-questions result, it carries every agreement in
force for the topic, numbered and self-contained, including decisions from
ordinary discussion before the first interview.

## Workflow Stages

Resolve dependencies, inspect facts, rebuild the current statement on every
call, present it before questions or a no-questions result, ask the next
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
Confirmed decisions remain agreed when presenting the current statement;
only new interpretations are hypotheses. Continuation follows the same
context and output contract as the first invocation.

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
Every invocation, including the first and one with no remaining questions, shall
rebuild the current problem statement and the agreements in force from reachable
session context, including ordinary discussion before any interview. It shall
present that statement without requiring redundant confirmation, treat new
information as a supplement that preserves
effective agreements, and reflect an explicitly replaced agreement with a short
note of what changed and why instead of accumulating withdrawn decisions. An
ambiguous contradiction shall not silently remove an agreed condition. The
closing result shall be cumulative and self-contained for the topic: context,
numbered user-approved decisions, and the expected result, with recommendations
never presented as accepted decisions and no invented deadlines, metrics, or
obligations. Independent topics shall keep separate agreements.

#### Verification

Dependent-question cases ask the prerequisite first and rebuild follow-ups from
the actual answer. Explicit invocation stops for manual continuation; internal
clarification returns to its authorized caller without expanding scope.
First-call and repeated-invocation cases rebuild the statement, preserve prior
agreements even with no questions, separate supplements from revisions, and keep
topics isolated. Behavioral checks inspect actual responses and handoffs to
`goal` and `task-prepare`; source-text assertions alone do not establish these
outcomes.

## Example

`askme` asks for the exact external boundary before selecting an API workflow.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
