# @kisev/taskmatic

[Русская версия](README.ru.md)

Local-first tasks for people and agents: one TypeScript/Node.js application for
CLI, MCP, Markdown exports and a live read-only web board. Requires Node.js 22.13+.

```shell
# Registry version
npm view --prefer-online @kisev/taskmatic@dev version

# Install
npm install --global @kisev/taskmatic@dev

# Installed package and active CLI
npm list --global @kisev/taskmatic --depth=0
taskmatic --version
```

The tag can move between preview and installation. The last commands show the
installed package and the CLI resolved from PATH. Then create and use a board:

```shell
taskmatic add "Check the first board"
taskmatic list
taskmatic mcp
taskmatic serve
```

The `dev` tag supplies the development build. Updating the portable `taskmatic`
skill does not update the application; rerun the npm installation to update it.
See the [setup and migration guide](../../docs/how-to/taskmatic.md).

## Compatibility

The existing `taskmatic.db` SQLite v1 schema, state root, snapshot format and eleven
MCP tool names are retained. The default root is
`${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`; `TASKMATIC_HOME`
or `--home` can select an absolute normalized path. IDs, notes, relationships,
events and active claims survive the move from Python. Use `--json` for machine
output; `--clear-assignee` and `--clear-linked` clear optional fields.

`taskmatic-web serve` remains a compatibility alias. The viewer requires an
existing store, binds only IPv4 loopback (default `127.0.0.1:8765`), refreshes
snapshots and offers board switching, filtering, notes and activity. It has no
authentication for network sharing and cannot mutate cards. CLI and MCP perform
mutations in immediate transactions; heartbeat extends a claim without exporting.

The Markdown/HTML mirrors are derived, not editable authority. Never commit the
database or private exports. Keep a consistent backup before changing commands,
and retain the old installation until migration checks pass. The npm application
does not modify user MCP configuration or systemd services automatically.
