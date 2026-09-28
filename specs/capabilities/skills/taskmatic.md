# `taskmatic`

## Purpose

Run a local-first task board for one person and their agents with SQLite authority,
a regenerated markdown mirror, static web export, and agent claims through the
separately installed `@kisev/taskmatic` TypeScript application. The skill supplies
instructions and the snapshot contract; CLI, MCP and live viewer share one runtime.

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
JSON, and the static web export; live loopback serving is `taskmatic serve` from
the same npm package under `apps/taskmatic/`.

## Workflow Stages

Resolve the absolute state root, open the versioned SQLite store, apply one
mutation (create, edit, move, claim, heartbeat, release, complete, note) inside an
immediate transaction with recorded activity, regenerate the mirror, then read
through `list`, `show`, `snapshot`, or MCP tools with computed claim state.
`taskmatic serve` reads an existing store; `taskmatic-web` remains a compatibility alias.

## Dependencies

Node.js 22.13+, the installed npm application, and a writable XDG state directory. The web
application additionally needs a loopback socket and an existing store.

## Remote/Local Effects

Private local state only: the SQLite store, the derived mirror, and derived web
files are atomically replaced inside the state root. No network access except the
loopback listener in `taskmatic-web serve`, which is read-only and rejects
non-loopback addresses. No repository or remote effects.

## Errors, Partial, Escalation

Unknown card, invalid status, priority, slug, title, label, note, or TTL, a
non-absolute state root, or an unclaimed claim target fail with a controlled error
before any write. Claiming a card held by another agent is rejected; an expired
claim may be taken over. A failed mutation rolls back without touching the mirror.

## Unique Constraints

The SQLite database is the only authority; the markdown mirror and web export are
derived and overwritten. The web board and MCP reads never mutate. Claim expiry is
computed at read time, so mirror files can show a stale claim until the next
mutation or explicit export. Heartbeat extends only the claim deadline without
regenerating the mirror. A skill archive has no runtime imports from other skills.

## Requirement

### REQ-F-515 - Keep board authority in SQLite with derived mirrors and computed claims

> Lifecycle: `superseded` | Changed: `2026-09-28` | Reason: The standalone TypeScript application replaces the bundled Python runtime. | Replacement: [REQ-F-542](#req-f-542---preserve-taskmatic-data-through-the-typescript-runtime)

Formerly required a bundled standard-library-only Python runtime with separate
live serving. SQLite authority, claim semantics and derived mirrors are retained
under REQ-F-542.

### REQ-F-542 - Preserve taskmatic data through the TypeScript runtime

The application shall store boards, cards, and activity only in a versioned private
SQLite database under an absolute normalized XDG state root, write every mutation
through an immediate transaction that records activity, and regenerate the markdown
mirror and web export from a snapshot after each mutating command except heartbeat.
The application shall
compute `claim_state` and `claim_remaining_seconds` at read time, reject claims on
cards held by another agent, allow takeover of expired claims, and clear the claim
on completion. Views (`snapshot`, list and show output, the static export) shall stay
read-only. CLI, MCP and web shall share the same TypeScript application; the npm
package shall support non-mutating `--version` and `--help`. Existing Python-era
SQLite v1 stores, card IDs, relations, events, timestamps and claims remain
readable and writable without a schema migration. Unsupported schema versions
and symlinked state paths fail closed. Host command and service changes require
preview and confirmation; publication follows the npm package lifecycle.

#### Verification

Taskmatic tests compare database snapshots with mirrors, reject conflicting
claims across connections, and verify rollback. A fixture created by Python
SQLite opens in the TypeScript runtime with retained notes, events and claims.
Web tests reject missing stores and public binds and read live updates without
mutating the database. MCP tests retain all eleven names and error envelopes.

## Example

`taskmatic add "Investigate flaky test" --labels ci` then
`taskmatic claim <id> --agent review-bot --ttl 30m` while
`taskmatic serve` shows the board in a browser after npm installation.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
