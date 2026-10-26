---
audience: user
review: {"components": ["skillmate", "memomatic", "taskmatic"], "sources": ["apps/skillmate/src/skillmate/cli.py", "apps/memomatic/src/cli.ts", "apps/taskmatic/src/cli.ts"], "contracts": ["specs/requirements/interfaces/README.md"]}
---

# Command-Line Conventions

[Русский](../ru/reference/cli.md)

`skillmate` is Python 3.12+ with the standard library only; memomatic and
taskmatic require Node.js 22.13+. All three share one command grammar:
subcommands with long options, `--help` on every command, and explicit
`--json` for machine-readable output.

## Help and Configuration

```shell
skillmate install --help
memomatic sessions --help
memomatic dream --help
taskmatic claim --help
```

Help and version requests do not create application state or call a model.
Help lists supported options, environment names, choices and examples. Unknown
options fail rather than becoming search text or silently starting a workflow.
`skillmate doctor` and `skillmate status` are read-only and never write;
`memomatic status` is read-only and reports the queue (pending inbox files,
session backlog, promotion candidates, last runs) without model calls; indexing
is an explicit `index` operation.

Values resolve in this order: **CLI arguments > environment > JSON configuration > application defaults**.
`--config FILE` selects a JSON file, or use
`SKILLMATE_CONFIG`, `MEMOMATIC_CONFIG`, or `TASKMATIC_CONFIG`. Generic option keys
in memomatic and taskmatic files are camelCase (`logLevel`, `logFormat`,
`progress`, `color`, `json`); skillmate accepts its snake\_case option names
(`hosts`, `scope`, `version`, `skills`, `index_url`, `json`). Taskmatic also
accepts command fields such as `home`, `board`, `host`, and `port`. Memomatic
keeps its `sessions`, `dream`, `embedding`, `reranker`, `search`, and
`archive` sections. Run-specific overrides such as `--model` take precedence
over the matching `sessions.model`/`dream.model` setting, and a legacy `dream`
extraction value migrates to `sessions` until the new section overrides it. No
configuration file is written automatically by these overrides.

Environment names for application options appear in help: for example,
`MEMOMATIC_MODEL`, `MEMOMATIC_TIMEOUT`, `TASKMATIC_AGENT`, `TASKMATIC_TTL`,
and `TASKMATIC_HOST`; `SKILLMATE_CONFIG` selects the skillmate configuration
file. `MEMOMATIC_HOME`/`--state-dir` and `TASKMATIC_HOME`/`--home` select
absolute state directories. XDG defaults remain supported. `--yes`
confirmation is deliberately CLI-only in every application: a config file or
environment variable cannot authorize changes.

## Results, Logs and Progress

| Option | Values | Environment suffix |
| - | - | - |
| `--json` | Machine-readable result | `_JSON` |
| `--log-level` | `debug`, `info`, `warn`, `error`, `silent` | `_LOG_LEVEL` |
| `--log-format` | `text`, `json` | `_LOG_FORMAT` |
| `--progress` | `auto`, `always`, `never` | `_PROGRESS` |
| `--color` | `auto`, `always`, `never` | `_COLOR` |

The table describes memomatic and taskmatic; prefix each suffix with
`MEMOMATIC` or `TASKMATIC`. skillmate prints human-readable plans by default,
and `--json` selects its versioned plan documents. Default diagnostics are
text at info level; debug adds command diagnostics. `NO_COLOR` disables
color. Auto progress uses stderr only when attached to a terminal; redirected
output and systemd get sequential lines. JSON logs never use terminal
animation. Interactive confirmations retain control of the terminal; their
additional diagnostics are debug-level and animation is off unless requested.

Results go to stdout; diagnostics go to stderr. MCP stdout contains protocol
messages only. Memomatic keeps JSON reports for non-TTY processing runs and uses
a concise summary in a terminal; `--json` explicitly selects JSON. Search and
task lists retain their human defaults unless `--json` is supplied. skillmate
plan and status documents stay on stdout, so a pipeline can preview a plan
before confirming it.

Sessions and Dream progress reports stage, elapsed time and known fragment
counts. Neither invents a percentage for a model request: a waiting message is
emitted every 15 seconds until the response arrives or its timeout expires.
Diagnostics do not print transcripts, prompts, provider response bodies or
authentication data.

## Exit Codes

For memomatic and taskmatic: `0` success/help, `2` parser errors, `1` operation or
configuration failure, `124` timeout, `130` interruption. skillmate uses `0`
success, `2` usage or configuration errors, and `1` operation failures;
declining the confirmation is a normal `0` outcome that writes nothing. A
cancelled Dream retains committed work; it is not reported as a successful
complete pass.

See [Installing and managing skills](../how-to/install-skills.md),
[Dream controls and recovery](../how-to/memomatic.md), and
[Taskmatic commands](../how-to/taskmatic.md).
