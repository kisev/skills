# `ast-grep`

## Purpose

Search and rewrite source by syntax tree with preview and safety checks.

## Triggers and Near-Misses

Trigger for structural code search or rewrite; near-miss: plain text replacement.

## Inputs and Outputs

Input is a pattern, path, and optional rewrite. Output is matches or a digest-bound plan.

## Workflow Stages

Resolve bounded paths, search, preview, confirm apply, verify, report.

## Dependencies

ast-grep runtime and repository paths.

## Remote/Local Effects

Local reads and confirmed local mutations; no remote effects.

## Errors, Partial, Escalation

External or symlink targets block; empty search is a valid result.

## Unique Constraints

Rewrite requires atomic replacement and stale-digest rejection.

## Requirement

### REQ-F-103 - Guard structural rewrites

The skill shall preview syntax rewrites and reject stale, external, or unsafe targets.

## Example

`ast-grep` previews a function rename before applying an atomic rewrite.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
