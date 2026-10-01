# State, Ownership, and Archive

Every durable state has one owner: portable skill state, package state, user
configuration, runtime state, and archive are distinct. Managed files are
identified by exact semantic ownership and digest. The `skills` CLI owns portable
skill trees and locks; package reconciliation neither inspects nor mutates them.
Retired package assets are preserved in a content-addressed archive; unrelated
history and user-owned content remain byte-for-byte unchanged.
Global archives have one global owner, while each project archive is isolated by
the digest of its resolved project directory so one project's recovery cannot
remove another project's objects.

Stable, substantive XDG state keeps content-addressed versions indefinitely.
Human-readable stable Markdown contains only its latest body followed by a
`History` list of absolute paths to earlier body-only snapshots. A changed write
archives the previous state, including a legacy state first seen after this
contract was introduced; an identical write creates no new version. A candidate
state is never archived before it successfully becomes current. Machine state
uses the same logical rule: immutable content is stored once, while a mutable
pointer is not copied when its complete history remains reachable through verified
immutable artifacts. Locks, caches, transaction journals, one-use receipts, and
credentials are not versioned as stable state.

Direct target-mutation commands that use the shared marker wrapper record an advisory marker below
`$XDG_STATE_HOME/agent-skills/post-success/v1/` only after its process exits zero.
The marker binds the skill, action, target or plan binding, and exact argv/stdin
digest. It has no TTL and is not publication proof, authorization, a postcondition,
or permission to retry. Incremental workflows may use it to distinguish a command
that completed locally from one not observed locally, but must refresh the remote
or local target before suppressing or repeating a mutation. Marker-write failure
after a successful mutation is reported without changing the successful exit code.
Generated mutation blocks expose `execution-status=not_run` when the exact marker
is absent and `execution-status=run_unverified` when it is valid. Regeneration
recomputes this projection from the exact action binding; confirmed target state,
not the marker, removes or completes the action.
The status projection is excluded from immutable publication bindings, so recording
a marker cannot invalidate the approved command or block its required follow-up.
Configured XDG roots must be absolute and normalized; state traversal rejects
symlink components and state snapshots are durable before current-state replacement.

Code-review owns immutable review evidence, source drafts, decisions, and plans
with a stable `runbook.md`. It does not persist publication locks, reservations,
or receipts. Local command status is not remote publication proof. Historical
guarded state is retained without migration or replay; see
[the code-review contract](../../capabilities/skills/code-review.md).

Mattermost triage owns its dedicated private XDG namespace for one-origin,
one-identity incremental checkpoints, immutable evidence, stable current output,
and digest-bound prepared responses. Only a complete run advances its checkpoint;
partial state remains explicit and cannot replace complete provenance. This
mechanism provides [REQ-F-507](../../capabilities/skills/mattermost-triage.md#req-f-507---triage-bounded-mattermost-attention).

This ownership and isolation mechanism provides
[REQ-F-005](../../requirements/functional/README.md#req-f-005---archive-owned-retired-assets),
[REQ-Q-002](../../requirements/quality/README.md#req-q-002---mutation-safety), and
[REQ-C-003](../../requirements/constraints/README.md#req-c-003---explicit-ownership-boundaries).

The shared team-profile runner implements
[REQ-F-520](../../requirements/functional/README.md#req-f-520---preserve-atomic-private-profile-transactions)
for all delivery and people workflows, rather than assigning one transaction
protocol to each skill. Documentation review stores content-addressed snapshots
and results outside the checkout, keyed by workspace and scope, to provide
[REQ-F-519](../../requirements/functional/README.md#req-f-519---maintain-change-linked-documentation-and-reusable-review-evidence).
File digests identify reusable evidence; semantic conclusions still require review.
