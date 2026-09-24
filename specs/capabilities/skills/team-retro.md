# `team-retro`

## Purpose

Prepare one evidence-based retrospective, delivery review, report, or
presentation against a strict private team profile.

## Triggers and Near-Misses

Trigger for a retrospective action; near-miss: roadmap or sprint planning.

## Inputs and Outputs

Input is the fixed action, an automatically resolved default profile or explicit
context override, an exact period, and bounded evidence. Output is structured
retrospective material plus evidence-completeness and verification results.

## Workflow Stages

Resolve or self-setup the profile, establish `[since, until)`, inventory every
configured project, collect and validate evidence, distinguish delivery states,
draft the configured artifact, write it, verify, and report.

## Dependencies

Shared team profile runtime, optional bounded GitLab metrics collector, declared
evidence connectors, and owned local state. The metrics collector requires POSIX
sessions, process groups, pipes, and file-descriptor selectors.

## Remote/Local Effects

Read-only evidence collection, confirmation-bound local profile writes, and
direct bounded artifact writes. No implicit external publication.

## Errors, Partial, Escalation

Missing profile fields trigger guided self-setup. Partial project, page, signal,
or timestamp evidence remains explicit and prevents a complete claim. GitLab
collection timeouts, repeated pages, and page or element limits return bounded
partial results with structured errors. Unsupported platform capabilities do the
same. Process creation and selector setup are controlled capability boundaries;
after process creation, setup failure triggers bounded process-group cleanup. A
successful leader exit also triggers bounded cleanup and reap of any remaining
process-group descendants before its response is accepted.

## Unique Constraints

One fixed action is selected; every configured project is accounted for, and
`merged`, `tagged`, and `shipped` are never treated as synonyms.

## Requirement

### REQ-F-126 - Keep retrospective actions explicit

The skill shall execute only the selected fixed action against its declared team context.
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

`team-retro` refuses an unknown action before reading or writing state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
