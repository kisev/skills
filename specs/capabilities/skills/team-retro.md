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

Shared team profile runtime, the private per-profile evidence store, optional
bounded GitLab metrics collector, declared evidence connectors, and owned local
state. The metrics collector requires POSIX sessions, process groups, pipes,
and file-descriptor selectors.

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
Profile saves follow the shared [REQ-F-520](../../requirements/functional/README.md#req-f-520---preserve-atomic-private-profile-transactions).

#### Verification

Action checks reject missing or ambiguous action selection; shared profile
transaction tests verify the referenced save and recovery contract.

### REQ-F-509 - Keep collected evidence incremental and provenance-bound

Team skills shall keep collected evidence in a private per-profile store under
XDG state with a coverage manifest and immutable content-addressed snapshots.
The GitLab metrics collector with an explicit profile shall fetch only windows
missing from stored complete coverage, merge the remaining windows from the
store, and record each newly collected window; complete GitLab windows shall
remain reusable without an age limit because terminal delivery timestamps
never move, while an explicit refresh flag shall force full re-collection.
Partial collections shall be recorded for provenance only and never reused as
data. Every rendered artifact shall end with a data-sources section listing
each contributing source's kind, exact location, collected window or point
timestamp, completeness, and collection time, and every written artifact shall
be snapshotted in the store with its period and contributing source keys.

#### Verification

Evidence-store tests distinguish complete and missing configured sources and
retain immutable provenance; report review verifies merged, tagged, and shipped
results remain distinct in the selected period.

## Example

`team-retro` refuses an unknown action before reading or writing state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
