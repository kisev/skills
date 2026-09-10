# `rtk`

## Purpose

Summarize eligible command output while preserving actionable errors and context.

## Triggers and Near-Misses

Trigger for verbose tool output; near-miss: hiding evidence or changing commands.

## Inputs and Outputs

Input is command output under the supported adapter. Output is compact evidence.

## Workflow Stages

Resolve eligible command, execute through adapter, compress, preserve errors, report.

## Dependencies

RTK adapter and the invoked command.

## Remote/Local Effects

Effects equal the invoked command; the summarizer adds no independent remote effect.

## Errors, Partial, Escalation

Unsupported or failed commands retain original error status and escalate.

## Unique Constraints

Compression must not remove paths, exit status, or failure evidence.

## Requirement

### REQ-F-117 - Preserve error evidence when compressing

The skill shall summarize output without hiding exit status, errors, or actionable paths.

## Example

`rtk` shortens a successful test log but retains a failing selector and exit code.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
