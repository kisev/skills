# Publication helper protocol

The triage workflow generates manual commands and never executes them. Helpers
re-read the current target and conversation, verify the authenticated user, and
reject stale evidence. Commands use bounded POSIX locking and process groups.

Guard v4 binds a new standalone note to every observed non-system note and a new
reply to every non-system note in its selected discussion. Older guards fail
closed and require regeneration. Before each information POST, the helper writes
an `in_progress` reservation. Only a proven process-start failure removes it.
Timeout, nonzero exit, oversized or malformed output, and post-start cleanup
failure keep the reservation and require fresh assessment.

A successful POST produces an exact guard-, body-, and note-ID-bound receipt.
The close command requires that receipt and verifies the final explanation. It
durably replaces the receipt with a close reservation before PUT. A proven
pre-start failure restores the message receipt. An ambiguous result keeps the
reservation; only a fresh GET proving the exact project, issue IID, and closed
state permits a terminal receipt. Reopening the issue does not permit replay.

`mutation_outcome` is `none`, `unknown`, or `applied`; `external_mutations` is
consistent with whether the process started. The process runner has one deadline,
bounded stdout/stderr, and forced group cleanup and reap. Lock files must be
regular, current-user-owned, singly linked, and inaccessible to group/others.

Source-layout commands resolve only the bounded repository-relative shared
runtime. Built archives use their local bundled runtime. These implementation
details are enforced by the helpers; the model prepares semantic decisions and
handles their structured results rather than reproducing the protocol.
