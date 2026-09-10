# Agent `mapper`

## Purpose

Map relevant files, callers, tests, and repository patterns.

## Triggers and Near-Misses

Use for exploration; near-miss: editing or final review.

## Inputs/Outputs

Input is a bounded search question; output is a source map.

## Workflow Stages

Resolve scope, search, read candidates, link evidence, report.

## Dependencies

Local repository tools.

## Remote/Local Effects

Local reads only.

## Errors/Partial/Escalation

Unreachable or unreadable paths are marked.

## Unique Constraints

Map must not claim behavior beyond evidence.

## Requirement

### REQ-F-303 - Produce evidence-bounded maps

The mapper shall identify exact files and symbols supporting each map claim.

## Example

`mapper` links a package tool to its registration and test selector.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
