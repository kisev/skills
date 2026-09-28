---
audience: user
review: {"components": ["taskmatic"], "sources": ["skills/taskmatic/references/*", "apps/taskmatic/src/*", "apps/taskmatic/test/*"], "contracts": ["specs/capabilities/skills/taskmatic.md"]}
---

# Create and Use a Taskmatic Board

[Русский](../ru/how-to/taskmatic.md)

## Install and Create the Store

Use Node.js 22.13+. Install the application separately from the `taskmatic` skill
(see the [portable skills guide](portable-skills.md)). After npm publication, use
the development channel or select a published stable version:

```shell
npm install --global @kisev/taskmatic@dev
taskmatic --version
taskmatic add "Check the first board" --board main
taskmatic list --board main
```

The CLI creates the private SQLite store and derived exports. The read-only
web server cannot initialize a missing store; create a card or board first.
CLI, MCP and viewer must use the same absolute `TASKMATIC_HOME`, or the default
`${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`.

## Work with Cards

Replace `CARD_ID` with the ID returned by the create or list command:

```shell
taskmatic show CARD_ID
taskmatic claim CARD_ID --agent review-bot --ttl 30m
taskmatic note CARD_ID "Checked the setup" --actor review-bot
taskmatic complete CARD_ID
```

Statuses are `todo`, `doing`, `review`, `blocked`, and `done`. Another agent's
active claim prevents takeover; use heartbeat during long work and release a
claim when blocked. The [runner workflow](../../skills/taskmatic/references/workflow.md)
lists edit, child-card, filter, and claim commands. Completion clears the claim.

## View the Board

```shell
taskmatic serve
```

Open `http://127.0.0.1:8765`. Use `--port 0` for a free port. Non-loopback hosts
are rejected; the board has no authentication for network sharing. Cards and
claims change only through the CLI or MCP. Without a live server, open the
derived `export/web/index.html`; it updates only when the export is regenerated.

## Connect an Agent

For OpenCode, Kilo or MiMo, add this to user-owned configuration and restart the host:

```json
{"mcp": {"taskmatic": {"type": "local", "command": ["taskmatic", "mcp"], "enabled": true}}}
```

Verify `taskmatic_list` and `taskmatic_read`, then use `taskmatic_claim` before
agent work. The MCP and CLI share one store. Do not edit `taskmatic.db` or its
derived Markdown mirrors; correct cards through the commands. Keep the database,
notes, and exports out of Git. A missing-store error means the root differs or
the first card has not been created, not that the web server should create a new database.

## Migrate from Python

The npm application opens the existing SQLite v1 database directly. Card IDs,
boards, notes, labels, parent links, activity and claims are retained; no import,
reset or schema rewrite is required. The skill now contains instructions and
the snapshot contract, not a Python runner.

1. Record the current state root (`TASKMATIC_HOME` or the default above). Stop
   writers before making a consistent backup of the whole state directory,
   including any SQLite WAL files. Keep the old executable for rollback.
2. Install the npm application. Verify `taskmatic --version` and
   `taskmatic --home /absolute/state/root snapshot` against the existing board.
3. Replace the Python MCP command with `taskmatic mcp` in each host. Update the
   service's `ExecStart` to the absolute npm executable plus `serve`; keep the
   same state environment, loopback host and port. Preview and confirm these
   user-owned edits, reload systemd if used, and restart the service and hosts.
4. Check boards, a known card, claims, and the live page. `taskmatic-web` is an
   npm compatibility alias, but a previous uv/pipx executable may shadow it;
   prefer the absolute `taskmatic` path in services. Remove the old installation
   only after successful verification and explicit cleanup approval.

Rollback switches the commands back to the retained Python installation using
the same v1 store. Do not overwrite newer tasks with an old backup. Markdown and
HTML exports remain derived and can be regenerated with `taskmatic export`.
