# `ast-grep`

## Purpose

Search and rewrite source by syntax tree with direct-write safety checks.

## Triggers and Near-Misses

Trigger for structural code search or rewrite; near-miss: plain text replacement.

## Inputs and Outputs

Input is a pattern, path, and optional rewrite. Output is matches or a rewrite result.

## Workflow Stages

Resolve bounded paths, search, rewrite, verify, report.

## Dependencies

ast-grep runtime and repository paths.

## Remote/Local Effects

Local reads and bounded atomic local mutations; no remote effects.

## Errors, Partial, Escalation

External or symlink targets block; empty search is a valid result.

## Unique Constraints

Rewrite requires atomic replacement, rollback, and stale-target rejection.

## Requirement

### REQ-F-103 - Guard structural rewrites

The skill shall write syntax rewrites directly and reject stale, external, or unsafe targets.

## Example

`ast-grep` applies a function rename through an atomic rewrite.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
