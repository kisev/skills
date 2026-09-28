# `docs-prepare`

## Purpose

Prepare accurate user-facing Diataxis documentation from verified evidence,
including the bounded set affected by an authorized behavior change.

## Triggers and Near-Misses

Trigger for README/tutorial/reference/how-to work; near-miss: canonical `specs/`.

## Inputs and Outputs

Input is a document path or affected area. Output is an updated document set,
including necessary mirrors and navigation.

## Workflow Stages

Resolve audience and language set, inspect sources, draft, annotate for agents,
write, check links, report.

## Dependencies

Source, tests, and existing documentation.

## Remote/Local Effects

Local reads and bounded atomic local writes; no remote effects.

## Errors, Partial, Escalation

Unsupported claims are marked or escalated; broken links block completion.

## Unique Constraints

Does not modify `specs/` or invent behavior.

## Requirement

### REQ-F-107 - Prepare factual documentation

The skill shall keep user-facing documentation claims traceable to repository
evidence and write only validated workspace documents.

It follows [REQ-F-519](../../requirements/functional/README.md#req-f-519---maintain-change-linked-documentation-and-reusable-review-evidence)
to preserve applicable details and assess affected contracts without changing
an agreed guarantee implicitly.

#### Verification

Given a moved command and an existing guide with prerequisites and recovery,
the update corrects the command and navigation while preserving those details.

### REQ-F-517 - Keep documentation multilingual with agent annotations

The skill shall resolve the documentation language set from an explicit user
request, project rules, the agent's global rules, or English by default, and
shall keep machine tokens byte-identical across language mirrors. Documents
are human-first and shall carry agent guidance as frontmatter (`audience`,
optional `agent` purpose and hints) plus explicit agent sections only where an
expanded instruction is required; annotations shall stay identical across
mirrors, and executable contracts shall stay out of user prose.

#### Verification

Locale checks compare machine tokens and metadata; semantic review verifies
that mirrors describe the same supported behavior.

## Example

`docs-prepare` updates a package reference without touching canonical specs.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
