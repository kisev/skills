# taskmatic-web

[Русская версия](README.ru.md)

`taskmatic-web` is the live read-only web board for
[taskmatic](../../skills/taskmatic/): it renders the private SQLite task store as
a local kanban page that refreshes itself while agents and people keep working.

## Install

```bash
uv tool install git+https://github.com/kisev/skills#subdirectory=apps/taskmatic
```

or `pipx install` with the same target. The application reads
`$TASKMATIC_HOME` or `${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`
and never writes to the store.

## Use

```bash
taskmatic-web serve            # http://127.0.0.1:8765
taskmatic-web serve --port 0   # pick a free port
taskmatic-web snapshot         # print the live snapshot JSON
```

The page offers board switching, text and `#label` filtering, card details with
notes and activity, and periodic refresh. The board is strictly read-only: all
mutations go through the taskmatic skill runner CLI or MCP tools.

## Boundaries

- Binds only the loopback interface; no other network access.
- Read-only SQLite connection; claims and cards change only via taskmatic tools.
- The viewer template is kept byte-identical to the skill's static export
  viewer by a contract test.
- This is a user-run application, not a portable skill runner: it may declare
  dependencies, although it currently needs only the Python 3.12+ standard
  library.
