---
audience: user
review: {"components": ["agentomatic", "memomatic", "taskmatic"], "sources": ["shared/references/cli_runtime.ts", "shared/manifest.json", "scripts/materialize_cli_runtime.mjs", "apps/memomatic/src/cli.ts", "apps/taskmatic/src/cli.ts", "packages/agentomatic/src/cli.ts"], "contracts": ["specs/requirements/interfaces/README.md"]}
---

# Command-Line Conventions

[Русский](../ru/reference/cli.md)

Agentomatic, memomatic and taskmatic require Node.js 22.13+. All three use
Commander for option parsing and the same build-materialized CLI utilities;
there is no additional npm package to install. Agentomatic retains its existing
interactive configuration wizard and command-specific guidance.

## Help and Configuration

```shell
agentomatic install --help
memomatic sessions --help
memomatic dream --help
taskmatic claim --help
```

Help and version requests do not create application state or call a model.
Help lists supported options, environment names, choices and examples. Unknown
options fail rather than becoming search text or silently starting a workflow.
`memomatic status` is read-only and reports the queue (pending inbox files,
session backlog, promotion candidates, last runs) without model calls; indexing
is an explicit `index` operation.

Values resolve in this order: **CLI arguments > environment > JSON configuration > application defaults**.
`--config FILE` selects a JSON file, or use
`AGENTOMATIC_CONFIG`, `MEMOMATIC_CONFIG`, or `TASKMATIC_CONFIG`. Generic option keys
in that file are camelCase (`logLevel`, `logFormat`, `progress`, `color`, `json`).
Taskmatic also accepts command fields such as `home`, `board`, `host`, and `port`.
Memomatic keeps its `sessions`, `dream`, `embedding`, `search`, and `archive`
sections. Run-specific overrides such as `--model` take precedence over the
matching `sessions.model`/`dream.model` setting, and a legacy `dream` extraction
value migrates to `sessions` until the new section overrides it. No
configuration file is written automatically by these overrides.

Environment names for application options appear in help: for example,
`MEMOMATIC_MODEL`, `MEMOMATIC_TIMEOUT`, `TASKMATIC_AGENT`, `TASKMATIC_TTL`,
`TASKMATIC_HOST`, and `AGENTOMATIC_MODEL`. `MEMOMATIC_HOME`/`--state-dir` and
`TASKMATIC_HOME`/`--home` select absolute state directories. XDG defaults remain
supported. Agentomatic's `--yes` confirmation is deliberately CLI-only: a config
file or `AGENTOMATIC_YES` cannot authorize changes.

## Results, Logs and Progress

| Option | Values | Environment suffix |
| - | - | - |
| `--json` | Machine-readable result | `_JSON` |
| `--log-level` | `debug`, `info`, `warn`, `error`, `silent` | `_LOG_LEVEL` |
| `--log-format` | `text`, `json` | `_LOG_FORMAT` |
| `--progress` | `auto`, `always`, `never` | `_PROGRESS` |
| `--color` | `auto`, `always`, `never` | `_COLOR` |

Prefix each suffix with `AGENTOMATIC`, `MEMOMATIC`, or `TASKMATIC`. Default
diagnostics are text at info level; debug adds command diagnostics. `NO_COLOR`
disables color. Auto progress uses stderr only when attached to a terminal;
redirected output and systemd get sequential lines. JSON logs never use terminal
animation. Agentomatic's wizard retains control of the terminal; its additional
diagnostics are debug-level and animation is off unless requested.

Results go to stdout; diagnostics go to stderr. MCP stdout contains protocol
messages only. Memomatic keeps JSON reports for non-TTY processing runs and uses
a concise summary in a terminal; `--json` explicitly selects JSON. Search and
task lists retain their human defaults unless `--json` is supplied. Existing
agentomatic JSON error envelopes stay on stdout for compatibility.

Sessions and Dream progress reports stage, elapsed time and known fragment
counts. Neither invents a percentage for a model request: a waiting message is
emitted every 15 seconds until the response arrives or its timeout expires.
Diagnostics do not print transcripts, prompts, provider response bodies or
authentication data.

## Exit Codes

For memomatic and taskmatic: `0` success/help, `2` parser errors, `1` operation or
configuration failure, `124` timeout, `130` interruption. Agentomatic preserves
its existing error code `2` and doctor-specific codes. A cancelled Dream retains
committed work; it is not reported as a successful complete pass.

See [Dream controls and recovery](../how-to/memomatic.md) and
[Taskmatic commands](../how-to/taskmatic.md).
