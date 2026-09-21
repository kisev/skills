# `/stopit`

## Purpose

Expose stable workspace-scoped anonymized handoff creation.

## Triggers and Near-Misses

Routes session handoff; near-miss: repository notes.

## Inputs/Outputs

Arguments provide session context; output is the stable workspace-scoped XDG
handoff path.

## Workflow Stages

Select, resolve the destination read-only, redact, preview draft and path,
confirm, bind the write to that exact path, atomically write approved standard
input, verify, report.

## Dependencies

`stopit`, an existing workspace, and XDG state.

## Remote/Local Effects

One confirmed private XDG state write only; no repository or remote write.

## Errors/Partial/Escalation

Redaction uncertainty, invalid content, or unsafe state paths block the write.

## Unique Constraints

No repository or separate draft file is created. The same canonical workspace
always resolves to the same path.

## Requirement

### REQ-I-221 - Route the stopit command

The command shall load exactly `stopit` and preserve its explicit-confirmation,
workspace-scoped XDG storage contract.

## Example

`/stopit` previews and then writes an approved anonymized handoff outside the
repository.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
