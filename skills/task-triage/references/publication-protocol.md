# Publication command contract

The triage workflow generates manual commands and never executes them. Every
command is a direct `glab api --hostname <host> --method <method> <endpoint>`
invocation with an inline JSON body supplied through a heredoc on standard
input, preceded by a `#` explanation, and chained with `&&` so the block stops
at the first failure. Commands depend only on `glab`, `jq`, and `sha256sum`,
and never on a runtime helper, receipt store, or lock file.

## Guards

Every writing block starts with a user guard: it requests `glab api ... user`
and compares `id` and `username` with the collected `current_user` snapshot; a
mismatch stops the block before any write. The first writing block of a task
additionally compares the target `updated_at` with the snapshot. Every later
block of the same task performs its own GET and checks semantic preconditions
with `jq`: expected title, description, labels, status, and milestone; absence
of a non-system note matching the prepared conversation digest; and absence of
a link to the proposed target. A stage whose precondition cannot be
precomputed is emitted as a regeneration instruction, never as a ready
command.

## Coverage

A complete analysis leaves no action without a command. Obsolete and duplicate
issues get one explanation-and-close block with `state_event=close`. A missing
milestone is one block that searches or creates the milestone, extracts its ID
with `jq`, and attaches the triaged task. Information requests keep the
observed stage selection (`new`, `ping_1`, `ping_2`): each stage is a direct
note POST bound to its observed discussion, and the stale closure is one block
that publishes the final message and closes the issue in the same `&&` chain.
A new relation is created only after a links GET proves the target absent; a
conflicting relation type is replaced by one delete-then-create block that
re-verifies the observed link ID before deleting. Titles, descriptions, and
complete label sets use the direct issue-update format.

## Failure and repetition

The summary lists every action without a command together with its reason; a
complete analysis leaves none. Guards make replay safe: a repeated block stops
on its own preconditions because the first execution changed the observed
state. Nothing erases or rewrites legacy helper state; old guard and receipt
files remain historical and are never executed or interpreted. When a block
stops, refresh the collection evidence and regenerate the plan instead of
editing generated commands.
