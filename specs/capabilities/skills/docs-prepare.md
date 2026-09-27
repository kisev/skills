# `docs-prepare`

## Purpose

Prepare one accurate user-facing Diataxis document from verified code evidence.

## Triggers and Near-Misses

Trigger for README/tutorial/reference/how-to work; near-miss: canonical `specs/`.

## Inputs and Outputs

Input is one document path and scope. Output is a draft or updated document.

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

### REQ-F-517 - Keep documentation multilingual with agent annotations

The skill shall resolve the documentation language set from an explicit user
request, project rules, the agent's global rules, or English by default, and
shall keep machine tokens byte-identical across language mirrors. Documents
are human-first and shall carry agent guidance as frontmatter (`audience`,
optional `agent` purpose and hints) plus explicit agent sections only where an
expanded instruction is required; annotations shall stay identical across
mirrors, and executable contracts shall stay out of user prose.

## Example

`docs-prepare` updates a package reference without touching canonical specs.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
