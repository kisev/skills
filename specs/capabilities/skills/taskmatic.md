# `taskmatic`

## Purpose

Run a local-first task board for one person and their agents with SQLite authority,
a regenerated markdown mirror, read-only web views, and agent claims.

## Triggers and Near-Misses

Trigger when the user asks to track personal or agent work on a local board, to
coordinate agents over shared cards, or to view the board. Near-misses: GitLab
issue workflows (use `task-triage` or `task-prepare`) and read-only goal drafting
(use `goal`).

## Inputs and Outputs

Input is card data through the CLI, MCP tool calls, or nothing (viewer). Output is
the private SQLite store under `$TASKMATIC_HOME` or
`${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`, a regenerated
markdown mirror (`export/boards/...`) and web export (`export/web/`), snapshot
JSON, and a loopback read-only HTTP board.

## Workflow Stages

Resolve the absolute state root, open the versioned SQLite store, apply one
mutation (create, edit, move, claim, heartbeat, release, complete, note) inside an
immediate transaction with recorded activity, regenerate the mirror, then read
through `list`, `show`, `snapshot`, `serve`, or MCP tools with computed claim
state.

## Dependencies

Python 3.12+ standard library (sqlite3, http.server), a writable XDG state
directory, and a loopback socket for `serve`.

## Remote/Local Effects

Private local state only: the SQLite store, the derived mirror, and derived web
files are atomically replaced inside the state root. No network access except the
loopback listener in `serve`, which is read-only. No repository or remote effects.

## Errors, Partial, Escalation

Unknown card, invalid status, priority, slug, title, label, note, or TTL, a
non-absolute state root, or an unclaimed claim target fail with a controlled error
before any write. Claiming a card held by another agent is rejected; an expired
claim may be taken over. A failed mutation rolls back without touching the mirror.

## Unique Constraints

The SQLite database is the only authority; the markdown mirror and web export are
derived and overwritten. The web board and MCP reads never mutate. Claim expiry is
computed at read time, so mirror files can show a stale claim until the next
mutation or explicit export. The runner stays standard-library-only and adds no
dependencies.

## Requirement

### REQ-F-515 - Keep board authority in SQLite with derived mirrors and computed claims

The skill shall store boards, cards, and activity only in a versioned private
SQLite database under an absolute normalized XDG state root, write every mutation
through an immediate transaction that records activity, and regenerate the markdown
mirror and web export from a snapshot after each mutating command. The runner shall
compute `claim_state` and `claim_remaining_seconds` at read time, reject claims on
cards held by another agent, allow takeover of expired claims, and clear the claim
on completion. Views (`serve`, `snapshot`, list and show output) shall stay
read-only, bind at most a loopback socket, and never require dependencies beyond
the Python 3.12+ standard library.

## Example

`taskmatic add "Investigate flaky test" --labels ci` then
`taskmatic claim <id> --agent review-bot --ttl 30m` while
`taskmatic serve` shows the board in a browser.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
