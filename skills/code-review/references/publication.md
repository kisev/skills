# Manual publication

Review preparation never publishes. The supported publication interface is to
copy direct `glab` commands from `runbook.md`; those commands do not need reviewmatic.
Runbook preparation still depends on the reviewmatic backend. The alternative
`reviewmatic plan` terminal TUI is experimental and outside blocking behavioral
acceptance. The TUI executes the same commands without a shell. Enter only opens an
item. Sending, changing thread state, applying a local fix, committing, and pushing
are explicit user choices; review agents never invoke them.

The runbook keeps the exact body preview beside its command. Generated body files
are private and immutable; a repair writes a new body and updates the runbook.
Commands name the exact GitLab host, project, MR, and position. Raw refs may appear
in executable position arguments, not in prose or chat. Each reply and
`resolve`/`reopen` command is independently runnable. The user may send both from
the TUI or choose only one. There is no receipt dependency.

## Failure and repetition

One send performs one `glab` operation. Show its exit code, output, and bounded
redacted error. Exit zero means the command completed, not independently verified
publication. The user checks GitLab in the browser and decides whether to repeat.
There are no publication reservations, persistent locks, expiry, automatic
freshness checks, polling, or automatic retries. A network failure, timeout,
interruption, or application restart must not block another manual send.

Cancelling local waiting does not undo an accepted GitLab request. A repeat after
an uncertain outcome can duplicate a comment; explain this without preventing
the user's choice. Never erase or rewrite live legacy publication state during
review or upgrade. Old guarded action files remain historical and are not executed
by the new runtime; prepare a new plan for direct commands.

## TUI and local fixes

Opening a plan, reading, scrolling, and navigating require no network. These
remain available during a send; local cancellation and exit remain available too.
Use `t` to switch reply/context, `e` to edit, `s` for a reply, `r` for thread state,
`S` for both, `z` to cancel waiting, and `q` to exit. Body editing saves a new local
plan without sending. Code changes use the targeted repair workflow, not prose
editing. See `references/repair.md`.

The TUI can preview and apply a validated fix in a dedicated worktree. Commit and
push remain separate confirmations. Local application is not GitLab publication
and does not silently edit the reviewed checkout.
