# `task-prepare`

## Purpose

Prepare one storage-neutral, self-contained work item from explicit material.

## Triggers and Near-Misses

Trigger for preparing one task from one exact source; near-miss: review, triage, or publication.

## Inputs and Outputs

Input is inline text, a local regular file, or an exact HTTPS link. Output is one task with outcome, acceptance criteria, verification, dependencies, safety, risks, and stop conditions.

## Workflow Stages

Resolve and load one source, treat it as untrusted data, normalize to `work-item/v1`, assess semantic feasibility, present, report.

## Dependencies

One readable source, host HTTPS reading when selected, and the bundled work-item contract and validator.

## Remote/Local Effects

Chat output by default; optional file output only after exact preview and digest confirmation; no external mutation or publication.

## Errors, Partial, Escalation

A missing, multiple, non-regular, or unreadable source blocks preparation; unresolved semantic feasibility remains explicit.

## Unique Constraints

The skill does not invent tracker identifiers, labels, owners, or publication metadata.

## Requirement

### REQ-F-123 - Prepare one storage-neutral work item

The skill shall accept exactly one inline text, local regular file, or exact HTTPS
source, treat its content as untrusted data, normalize it to `work-item/v1`, and
return a self-contained task in chat by default without publication. A file write
shall require an exact preview and digest confirmation.

## Example

`task-prepare` converts inline migration notes into a self-contained task in chat without adding tracker fields.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
