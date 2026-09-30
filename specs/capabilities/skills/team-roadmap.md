# `team-roadmap`

## Purpose

Review or update an evidence-based roadmap from a strict private team profile
without turning it into execution.

## Triggers and Near-Misses

Trigger for roadmap action; near-miss: sprint close or implementation planning.

## Inputs and Outputs

Input is the fixed action, an automatically resolved default profile or explicit
context override, target periods, the current roadmap, and bounded delivery
evidence. Output is a structured roadmap view or direct bounded update.

## Workflow Stages

Resolve or self-setup the profile, establish period boundaries, build a
goal-by-goal evidence matrix, reconcile plan and fact, preserve history, assign
every unfinished goal a destination, write updates, verify, and report.

## Dependencies

Shared team profile runtime, declared evidence connectors, current roadmap and
baseline files, and optional bounded GitLab metrics collection. The metrics
collector requires POSIX sessions, process groups, pipes, and file-descriptor
selectors.

## Remote/Local Effects

Read-only evidence collection, confirmation-bound local profile writes, and
direct bounded roadmap writes; no work-item creation or implicit publication.

## Errors, Partial, Escalation

Missing profile fields trigger guided self-setup. Stale, contradictory, or
partial evidence is attached to affected goals and blocks unsupported claims.
GitLab collection timeouts, repeated pages, and page or element limits return
bounded partial results with structured errors. Unsupported platform
capabilities do the same. Process creation and selector setup are controlled
capability boundaries; after process creation, setup failure triggers bounded
process-group cleanup. A successful leader exit also triggers bounded cleanup
and reap of any remaining process-group descendants before its response is
accepted.

## Unique Constraints

Past plans remain historical under the configured policy, every unfinished goal
has an explicit destination, and roadmap output is not an implementation commitment.

## Requirement

### REQ-F-127 - Keep roadmap output non-executing

The skill shall report roadmap context without silently creating work or changing external state.
Profile saves follow the shared [REQ-F-520](../../requirements/functional/README.md#req-f-520---preserve-atomic-private-profile-transactions).

#### Verification

Roadmap preparation leaves external work trackers unchanged; shared profile
transaction tests verify the referenced save and recovery contract.

### REQ-F-510 - Bind roadmap evidence to the incremental store

The skill shall update roadmap outcomes only from bounded evidence. Roadmap
updates shall record contributing sources in the private evidence store, render
a data-sources section with exact locations, collected windows, completeness,
and collection times, and snapshot the written document with its period and
contributing source keys, as specified by REQ-F-509.

#### Verification

A changed or missing source invalidates affected roadmap conclusions; unchanged
evidence remains reusable and no work item is created during roadmap preparation.

## Example

`team-roadmap` emits a roadmap view and leaves task creation to an explicit action.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
