# `mattermost-triage`

## Purpose

Triage bounded Mattermost direct and group messages into an evidence-backed view
of conversations that may require the authenticated user's attention, without
changing Mattermost.

## Triggers and Near-Misses

Trigger for reviewing DM/GM attention, mentions, or follow-up over a bounded
period. Near-misses are broad workspace or channel search, team-wide reporting,
and automatic replies, reactions, edits, or other mutations.

## Inputs and Outputs

Input defaults to the 20 freshest DM/GM conversations on one Mattermost origin
for one authenticated identity. The user may configure that count and add exact
Mattermost URLs. The initial period is 30 days; later runs default to the interval
since the last complete run, while an explicit period selects the requested
interval. Output is one stable private XDG artifact containing classifications,
confidence, closure state, and only the minimal cited excerpts and links needed
to support each result.

## Workflow Stages

Resolve the origin and identity scope, select the default conversations and exact
additional URLs, collect the bounded interval, retrieve complete thread evidence
for candidate items, classify semantic attention and direct name mentions, keep
uncertain items separate, assess confidence and closure, persist immutable
digest-bound evidence, and atomically replace the stable artifact. Optional text
responses are prepared as separately confirmed manual commands; the workflow
never invokes them.

## Dependencies

Authenticated GET access to one Mattermost origin, exact URL resolution, complete
thread retrieval, private XDG state, and the existing
[Mattermost publication contract](mattermost.md) for prepared text responses.

## Remote/Local Effects

Collection is GET-only. The skill owns a dedicated private XDG state scope with
immutable evidence and one stable current artifact. It may prepare one manual,
digest-bound text-response command per action, but never executes a command or
mutates Mattermost. It does not prepare emoji or reaction commands.

## Errors, Partial, Escalation

Authentication, conversation listing, pagination, exact-URL, post, or thread
failures make the affected scope explicitly partial. Useful bounded findings are
retained with missing evidence and consequences; incomplete runs do not advance
the last-complete checkpoint or present uncertain classifications as complete.

## Unique Constraints

One run is bound to exactly one Mattermost origin and authenticated identity.
Every finding is supported by full available thread evidence and reports its
confidence and whether the matter is open, closed, or uncertain. Semantic
attention, direct name mentions, and uncertain candidates remain distinguishable.
Stable output minimizes copied message content while preserving cited excerpts
and exact links. Immutable digests bind collected evidence, the stable result,
and each separately previewed text response. A response requires explicit user
confirmation and manual invocation; no automatic mutation or emoji command is
allowed.

## Requirement

### REQ-F-507 - Triage bounded Mattermost attention

The skill shall inspect, by default, the 20 freshest DM/GM conversations for one
authenticated identity on one Mattermost origin, accept a configured conversation
count and exact additional URLs, use a 30-day initial interval, and use the
interval since the last complete run unless the user supplies an explicit period.
It shall collect the complete thread containing each candidate before classifying
semantic attention and direct name mentions, keep uncertain candidates separate,
and report confidence and open, closed, or uncertain closure state. It shall
atomically maintain one stable private XDG artifact containing only minimal cited
excerpts and exact links, with immutable digest bindings for evidence, results,
and prepared actions. Missing or incomplete required evidence shall remain
explicit, and a partial run shall not advance the last-complete checkpoint. The
skill may prepare separately confirmed manual text-response commands, but shall
never execute them, mutate Mattermost automatically, or prepare emoji or reaction
commands.

#### Verification

Contract tests cover default and configured conversation selection, exact extra
URLs, initial and incremental periods, explicit period overrides, complete thread
collection, classification separation, confidence and closure, minimal citations,
digest binding, origin and identity isolation, partial checkpoint handling, and
manual text-only response commands with no automatic mutation.

## Example

`mattermost-triage` checks the 20 freshest DM/GM conversations since the previous
complete run, keeps a low-confidence possible request separate, and prepares a
confirmed manual text reply without sending it.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
