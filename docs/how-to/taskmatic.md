---
audience: user
review: {"components": ["taskmatic"], "sources": ["skills/taskmatic/scripts/*", "apps/taskmatic/src/taskmatic_web/*", "apps/taskmatic/tests/*"], "contracts": ["specs/capabilities/skills/taskmatic.md"]}
---

# Create and Use a Taskmatic Board

[Русский](../ru/how-to/taskmatic.md)

## Install and Create the Store

Use Python 3.12+. Install the `taskmatic` skill through the
[portable skills guide](portable-skills.md). Set `TASKMATIC_SKILL` to its installed
directory containing `SKILL.md`, then create a first card:

```shell
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" add "Check the first board" --board main
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" list --board main
```

The runner creates the private SQLite store and derived exports. The separate
web application cannot initialize a missing store; create a card before starting it.
Both tools must use the same absolute `TASKMATIC_HOME`, or the default
`${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`.

## Work with Cards

Replace `CARD_ID` with the ID returned by the create or list command:

```shell
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" show CARD_ID
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" claim CARD_ID --agent review-bot --ttl 30m
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" note CARD_ID "Checked the setup" --actor review-bot
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" complete CARD_ID
```

Statuses are `todo`, `doing`, `review`, `blocked`, and `done`. Another agent's
active claim prevents takeover; use heartbeat during long work and release a
claim when blocked. The [runner workflow](../../skills/taskmatic/references/workflow.md)
lists edit, child-card, filter, and claim commands. Completion clears the claim.

## View the Board

```shell
uv tool install git+https://github.com/kisev/skills#subdirectory=apps/taskmatic
taskmatic-web serve
```

Open `http://127.0.0.1:8765`. Use `--port 0` for a free port. Non-loopback hosts
are rejected; the board has no authentication for network sharing. Cards and
claims change only through the runner or MCP. Without the application, open the
derived `export/web/index.html`; it updates only when the export is regenerated.

## Connect an Agent

For OpenCode, add this to user-owned configuration, replacing the placeholder with
the directory containing the installed skill's `SKILL.md`, then restart the host:

```json
{"mcp": {"taskmatic": {"type": "local", "command": ["python3", "<installed-skill-path>/scripts/taskmatic.py", "mcp"], "enabled": true}}}
```

Verify `taskmatic_list` and `taskmatic_read`, then use `taskmatic_claim` before
agent work. The MCP and CLI share one store. Do not edit `taskmatic.db` or its
derived Markdown mirrors; correct cards through the commands. Keep the database,
notes, and exports out of Git. A missing-store error means the root differs or
the first card has not been created, not that the web server should create a new database.
