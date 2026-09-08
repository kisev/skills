# RTK Boundaries by Category

Read only the section relevant to the operation. RTK is suitable for a broad first pass; use the original command for exact results and important decisions.

## Build, Tests, and Linters

`rtk cargo build`, `rtk pytest tests/`, `rtk tsc`, `rtk ruff check .`, and similar wrappers are usually suitable for a complete verbose run. After finding an error, run the focused original test or linter command to preserve traceback, order, code frame, warnings, and exact diagnostics. Do not use compressed output as evidence of complete coverage, absence of warnings, or exact test-runner behavior.

## Git and Hosting

`rtk git status`, `rtk git log`, and broad `rtk git diff` suit an initial summary. For review, patch preparation, whitespace, rename, file-mode, exact-line checks, or an approval decision, use direct `git diff`, `git show`, and other original commands. For hosting CLIs, RTK can summarize lists and statuses; obtain direct fields or API responses when pagination, JSON, comments, object existence, merge, release, or security matters.

## Logs and Data

RTK is useful for repetitive logs and large lists. During incident investigation, switch to a narrow direct fragment when timestamps, event order, frequency, stack traces, or absence of an event matter. Do not pipe transformed RTK output to a JSON parser, redirect, or another command expecting the complete format. For JSON, manifests, databases, and APIs, use direct machine-readable output when exact values, `null`, order, duplicates, hashes, sizes, or a specific field matter.

## Infrastructure and Writes

RTK can summarize resource lists and container logs. Do not use it as the sole evidence before deployment, rollout, migration, deletion, permission changes, or another destructive operation. Before writing, verify target, scope, arguments, and actual result with a direct command. Do not automatically add RTK to shell chains: its compressed human-readable output is a final result, never input to the next step.
