# Guarded publication

Review preparation never publishes. It creates one immutable action per remote
mutation and prints the exact `review_publication.py apply --action <path> --confirm <sha256>` command beside its body preview. Only the user's separate
invocation starts publication. Do not execute these commands during review.

Each action belongs to the current finalized review plan, expires after 24 hours,
and binds the GitLab user, MR identity and refs, conversation, labels, request
payload, and any body file. The helper accepts only the generated operation set:
new general or line discussions, replies, recommended issues, thread state, and
label updates. It invokes `glab api` without a shell and prints a compact JSON
result instead of the remote response.

A thread state action requires the successful receipt for its preceding
explanation. Earlier verified actions from the same evidence snapshot are
accounted for during freshness checks; unrelated edits or replies invalidate the
remaining plan. Success requires a separate GitLab read proving the exact effect.
Repeated successful actions return `already_applied` without another write.

## Failure and inspection

The helper persists an in-progress reservation before starting the mutation.
Only a proven process-start failure removes it without a remote postcondition.
Timeout, nonzero exit, oversized output, or an unverified postcondition leaves the
result `unknown` and blocks further writes for this collection.

Replace `apply` with `inspect` in the exact action command to perform a read-only
GitLab check. A unique matching effect completes the receipt. Insufficient
evidence leaves the reservation blocked; it never authorizes an automatic retry.
An explicitly repeated write must pass current freshness and confirmation checks.
Inspection may update the local receipt but never writes to GitLab.

Exit codes are `0` for a completed observation/action, `1` for an unknown outcome,
and `2` for invalid, stale, expired, or otherwise blocked input. The JSON result
separates `status`, `mutation_outcome`, and whether this invocation may have
mutated GitLab. POSIX locking and process groups are required.

Old direct-command plans remain historical review material. Regenerate against
fresh evidence to obtain guarded commands; advisory markers are not migrated to
publication receipts. Local `git apply` commands retain their separate exact-head
precondition and advisory markers. Portable patch blocks posted to GitLab contain
no local helper or checkout paths.
