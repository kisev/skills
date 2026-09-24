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
Confirmed profile saves that also select the default profile shall update profile
and settings atomically with rollback, recover interrupted transactions from a
private schema v3 journal, and store bounded previous bytes in private
content-addressed state files referenced by digest and exact path rather than
inline encoding. Backup cleanup shall follow commit or completed rollback and
shall preserve content still referenced by another journal. Existing schema v2
journals shall remain recoverable under a separate compatible legacy bound. The
runtime shall consume the receipt only after both writes and the report
succeed, their parent directories are fsync-durable, and safe private reads match
all three journal-declared postconditions immediately before receipt creation; a
pre-receipt mismatch shall roll back without a receipt. The runtime shall fsync every transaction
replace, create, and unlink including journal deletion, fsync the receipt
namespace before recovery accepts either commit or rollback state, and report
unavailable POSIX durability primitives or other expected local I/O failures as JSON errors.
Recovery shall accept commit only for an exact receipt whose journal-bound
profile, settings, and report existence and digests match durable files. It shall
never remove an exact durable receipt: intended state shall finish commit, while
prior, mixed, or unknown state shall preserve the receipt, journal, and backups
and fail closed. Without such a receipt, recovery shall finish rollback for prior
or mixed prior/intended state but preserve the journal, backups, and any current
file that matches neither state. Confirmed context saves shall be serialized,
roll back visible context and new report state after pre-receipt fsync, report, or
required marker failure, and create the one-use receipt only at the safe commit
point. A post-link receipt error shall finish as committed only when the exact
receipt and intended context and report digests match. Existing persisted plans
shall remain compatible. Backup paths, digests,
sizes, ownership, and private permissions shall be verified before restoration.
Mutation locking shall use non-blocking POSIX `flock` retries with a five-second
monotonic deadline and reject a lock with more than one hardlink before changing
its mode, while module import and read-only commands remain portable.

## Example

`team-roadmap` emits a roadmap view and leaves task creation to an explicit action.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
