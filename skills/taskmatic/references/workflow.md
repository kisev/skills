# taskmatic Workflow

Taskmatic is a local-first task board for one person and their agents. SQLite under
private XDG state is the source of truth; every mutation regenerates a readable
markdown mirror and a read-only web export. Nothing leaves the machine.

## Storage layout

- State root: `$TASKMATIC_HOME` when set, otherwise
  `${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`. The root must be an
  absolute normalized path.
- `taskmatic.db` — SQLite database, the only authority. Never hand-edit it.
- `export/boards/<slug>/BOARD.md` — one markdown board with status sections.
- `export/boards/<slug>/cards/<id>-<slug>.md` — one markdown card with YAML
  frontmatter, notes, and activity.
- `export/web/` — `index.html` with an embedded snapshot plus `snapshot.json`.

The mirror is derived output: it is rewritten on every mutation and manual edits to
it are overwritten. Read it, do not write it. Claim expiry is derived, so a mirror
can show a stale `claim_state` until the next mutation or explicit
`taskmatic export`.

## Human surface

Run the runner as `python3 scripts/taskmatic.py` (adjust the path to the installed
skill) or through any wrapper the host provides.

- `boards`, `board-create <slug> [--title TITLE]`
- `add <title> [--board SLUG] [--priority low|normal|high|urgent] [--labels a,b]`
  `[--assignee NAME] [--parent ID] [--linked REF] [--notes TEXT | --notes-file -]`
- `list [--board SLUG] [--status STATUS] [--assignee NAME] [--label LABEL]`
- `show <id>` — full card with activity; add `--json` for machine output.
- `move <id> <status>`, `complete <id>`
- `edit <id> [--title ...] [--priority ...] [--labels ...]`
  `[--assignee NAME|unset] [--linked REF|unset] [--notes ... | --notes-file -]`
- `note <id> <text> [--actor NAME]`
- `claim <id> --agent NAME [--ttl 30m]`, `heartbeat <id> --agent NAME [--ttl 30m]`,
  `release <id> --agent NAME`
- `export` — regenerate the mirror; `snapshot [--board ...]` — print snapshot JSON;
  `path [root|db|export|web]`

The live web board is the standalone `taskmatic-web` application (see
`apps/taskmatic/` in the skills repository), installed with `uv tool install` or
`pipx install` and run as `taskmatic-web serve [--host 127.0.0.1] [--port 8765]`.
It is a user-run application, not part of the skill runner. Without it, open the
static `export/web/index.html` from any file browser or static server.

Statuses: `todo`, `doing`, `review`, `blocked`, `done`. TTL accepts seconds
(`1800`) or `30m`, `2h`, `1d`. All list and show output is also available as
`--json`.

## Agent contract

Agents act through the same runner or through the MCP server (`... taskmatic.py
mcp`, newline-delimited JSON-RPC 2.0 over stdio; tools `taskmatic_boards`,
`taskmatic_list`, `taskmatic_read`, `taskmatic_create`, `taskmatic_edit`,
`taskmatic_move`, `taskmatic_claim`, `taskmatic_heartbeat`, `taskmatic_release`,
`taskmatic_complete`, `taskmatic_note`).

1. Before taking work, `taskmatic_list` (or `list --board ...`) and read candidate
   cards with `taskmatic_read`. Never start work on a card whose `claim_state` is
   `held` by another agent.
2. Claim with `taskmatic_claim` using a stable agent name. A claim moves a `todo`
   card to `doing`. Default TTL is 30 minutes.
3. Refresh the claim with `taskmatic_heartbeat` well before expiry on long work
   (for example every 10 minutes of a 30-minute TTL). Heartbeat does not touch the
   mirror; it only extends the deadline.
4. Record meaningful progress with `taskmatic_note` instead of resending the whole
   notes body. Keep notes as the stable task brief and progress in the activity
   log.
5. When work needs a human decision, `taskmatic_move` the card to `review` and add
   a note stating the exact question. When blocked, move it to `blocked`, release
   the claim with `taskmatic_release`, and note the blocker.
6. On success, `taskmatic_complete` marks the card done and clears the claim.
   Verify checks that the acceptance criteria in the notes actually hold first.
7. Derived claim fields are computed by the tool: compare
   `claim_remaining_seconds` with your own grace window instead of doing datetime
   arithmetic.
8. Split large work: `taskmatic_create` child cards with `parent`, then complete
   children before the parent.
9. A failed `taskmatic_claim` means another agent holds the card; pick a different
   one or stop. Never retry claims in a loop.
10. Tool errors arrive as `isError: true` results with a `taskmatic:` message;
    report them instead of improvising a workaround.

For an OpenCode MCP registration, add to the user-owned `opencode.json`:

```json
{
  "mcp": {
    "taskmatic": {
      "type": "local",
      "command": ["python3", "<installed-skill-path>/taskmatic/scripts/taskmatic.py", "mcp"],
      "enabled": true
    }
  }
}
```

`<installed-skill-path>` is the directory containing this skill's `SKILL.md`; the
exact location depends on the host installation.

## Boundaries

- The runner and the MCP server never open network connections. All views are
  read-only; only the separate user-run `taskmatic-web` application binds a
  local loopback socket.
- The board is private state: never commit `taskmatic.db` or `export/` to a
  repository and never publish a snapshot that contains private data.
- The web board is strictly read-only; every mutation goes through the CLI or MCP.
- The runner is standard-library-only Python 3.12+; do not add dependencies.
- Do not hand-edit the database. Corrections go through `edit`, `note`, or a new
  card.
