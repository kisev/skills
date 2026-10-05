# Manual publication

Review preparation never publishes. The supported publication interface is to
copy and run the direct `glab` commands from `<artifact-root>/runbook.md`.
Runbook creation requires the selected Python reviewmatic runtime; publication
does not. Reviewmatic has no terminal UI or in-app send interface.

The runbook keeps the exact body preview beside its command. Generated body
files are private and immutable; a repair writes a new body and updates the
runbook. Commands name the exact GitLab host, project, MR, and position. Raw
refs may appear in executable position arguments, not in prose or chat.

Every shell block that creates a comment or discussion or changes thread state
starts with a manual head check. It uses `glab api --hostname` for the exact MR
host. The GET runs as a command substitution, so a nonzero `glab` exit stops the
block even when it prints a matching SHA. `jq -e` rejects malformed JSON and a
missing or invalid `sha`; the digest comparison rejects a moved head. No write
runs after a failed request, invalid response, or mismatch. This check does not
depend on `set -o pipefail`. It runs only when the user executes the block, never
during runbook preparation. The check and every write in the block target the
same MR hostname.

A reply and planned `resolve` or `reopen` appear in one annotated `shell` block
with `&&` between commands. State changes follow a successful reply only. For
an ordinary comment, the POST returns a discussion: inspect its actual ID and
resolvability, then resolve it only for a completed assessment. Unresolved
problems and questions stay open. The direct block uses `jq`; the backend parses
JSON. Agents do not execute these commands.

## Failure and repetition

One manual send performs the selected operation and any explicitly planned
state change after successful publication. Show the exit code, output, and
bounded redacted error. Exit zero means the command completed, not that the
remote effect was independently verified. The user checks GitLab in the
browser and decides whether to repeat. There are no publication reservations,
persistent locks, expiry, automatic freshness checks, polling, or automatic
retries. A network failure, timeout, or interruption must not block another
manual send.

A repeat after an uncertain outcome can duplicate a comment; explain this
without preventing the user's choice. Never erase or rewrite live legacy
publication state during review or upgrade. Old guarded action files remain
historical and are not executed by the new runtime; prepare a new runbook.

## Local fixes

Local patch application is separate from GitLab publication. A generated patch
is bound to the managed review worktree and exact reviewed head. Show the
read-only `git apply --check` command first. A marked `git apply` mutation must
stop before changing files when the worktree head no longer matches. Run a
returned `reviewmatic marker-run` action through the same selected `uvx --from`
source as every other reviewmatic command. Commit and push remain separate
user decisions.

Patch blocks embedded in GitLab publication prose remain checkout-independent
and contain no local paths or runtime helpers; only local application commands
carry the post-success marker. Read `references/repair.md` for targeted local
repair and `references/local-review.md` for the local WIP lifecycle.
