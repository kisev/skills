# OpenCode Integration

[Русский](README.ru.md)

`@kisev/skills-opencode` is the optional npm integration. It does not include
portable skills or mutate configuration on import.
Managed files use exact SHA-256 ownership checks.
It provides the capability router, OpenCode runtime, agent-profile management,
and an opt-in installer for agents, commands, and plugins. It requires Node.js
22+ and OpenCode 1.18.29+; import, plugin loading, and npm lifecycle do not
write configuration.

## Install Skills

Install portable skills first:

```shell
npx --yes skills add kisev/skills --agent opencode --skill '*' --copy --yes
```

Use `--skill <name>` for one skill. `npx skills` accepts a reproducible tag URL,
for example `https://github.com/kisev/skills/tree/v2.0.0`; the package never
installs or updates skills and reports the exact `npx skills add` command when a
skill is missing.

## Install Integration

```shell
npm install @kisev/skills-opencode@2.0.0
```

Preview before any write:

```shell
npm exec -- skills-opencode install --scope global --dry-run
```

Apply the shown digest only:

```shell
npm exec -- skills-opencode install --scope global --confirm <digest>
```

Use `--json` for automation.
The machine-readable plan includes `requires_restart`; a preview uses `--dry-run`
and an apply uses `--confirm <digest>` with identical arguments.

`global` manages `.config/opencode/agents`, `.config/opencode/commands`, and
`.config/opencode/plugins`. Project scope manages `.opencode/agents`,
`.opencode/commands`, and `.opencode/plugins`. Profile configuration is kept in
`.config/opencode/.skills-opencode/agent-profiles.json` globally or under
`.opencode/.skills-opencode` for a project.
Project assets are limited to the current working directory. Scope is required;
the installer never changes `opencode.json`, overwrites unknown or modified
files, or records ownership manifests before confirmed apply. The short preview
reports changed paths, conflicts, restart status, digest, and its confirm command.

## Read-only Doctor

`doctor` reports facts without writing:

```shell
npm exec -- skills-opencode doctor --scope project
npm exec -- skills-opencode doctor --scope global --json
```

It never creates lifecycle state, consumes receipts, recovers journals, starts
plugins, or starts LSP servers. Its versioned JSON report contains stable check
IDs, catalog and installed-manifest versions, ownership/drift/collision classes,
inventory findings, runtime summaries, redacted configuration projections, and
LSP facts. It never serializes secrets, raw configuration, environment values,
receipts, or credentials. Exit status `0` is clean, `1` reports findings, and
`2` means invalid input or an incomplete probe failure.

## Reconcile Retired Assets

`reconcile` previews retirement and preserves conflicts:

```shell
npm exec -- skills-opencode reconcile --scope project --dry-run
npm exec -- skills-opencode reconcile --scope project --confirm <digest>
npm exec -- skills-opencode reconcile --scope global --dry-run --json
```

It considers only public portable skills, package commands, plugins, agents, and
installation metadata for the selected scope; XDG runtime state is neither read
nor changed. Only retired files with proven inventory ownership and exact SHA-256
are removed. Modified-managed, user-owned, unknown, symlink, unsafe-path, and
ambiguous-source entries remain conflicts. Other scopes, sources, and lock entries
are preserved byte-for-byte. The journaled transaction provides rollback,
recovery, and repeatable no-op reconciliation. Restart OpenCode fully after
install, upgrade, or uninstall because agent and command registries are built
before plugin hooks.

Add the plugin manually:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

## Manage Agents

The direct CLI manages models without LLM calls:

```shell
npm exec -- skills-opencode agent list --scope global
npm exec -- skills-opencode agent configure manager --scope global --dry-run
npm exec -- skills-opencode agent model-set worker --scope global \
  --model openai/gpt-5 --variant high --dry-run
npm exec -- skills-opencode agent reconcile --scope global --dry-run
```

Fixed roles preserve their names and canonical prompts and permissions; only
model and variant change. The interactive configuration wizard selects an agent,
provider, its models, and published variants, showing the current target and
offering keep, change, clear variant, back, and cancel. It does not invoke an
LLM, OpenCode Question, or catalog refresh. If the catalog is unavailable it
does not write and prints the exact model instruction.

When the catalog is unavailable, use exact `--model <provider/model>` and an
optional `--variant`; `provider/model` identifies the selected model. The
optional `agent_profiles` tool and slash commands adapt the same direct-CLI
plan/apply contract.

```shell
npm exec -- skills-opencode critic add security --scope global \
  --model anthropic/claude-sonnet-4-6 --dry-run
npm exec -- skills-opencode critic remove security --scope global --dry-run
```

Additional critics use `critic-<safe-suffix>`; fixed roles and the standard
critic cannot be renamed or removed. Every mutation uses a one-time private
receipt valid for 10 minutes, a lifecycle lock, inventory recheck, journaled
all-or-rollback transaction, and final validation. Interrupted mutations recover
before requiring a fresh plan. Global profile configuration and its semantic
deployment manifest are kept together; project scope keeps corresponding files
under its `.opencode` directory. Package updates do not reset selected models,
variants, or additional critics.

## Upgrade and Uninstall

```shell
npm exec -- skills-opencode uninstall --scope global --dry-run
npm exec -- skills-opencode uninstall --scope global --confirm <digest>
```

The full JSON install preview is:

```shell
npm exec -- skills-opencode install --scope global --dry-run --json
```

On upgrade, the installer updates only managed files whose SHA-256 still matches.
The one-time `1.0.0` migration transfers the six fixed-agent ownership records
only when package/version, manifest records, and every file hash match exactly.
Uninstall removes only unchanged manifest-owned files; modified files remain
conflicts and profile configuration is retained for a later installation.

## Runtime Options

Plugins are independent and stateful ones are opt-in.

```shell
npm exec -- skills-opencode agent list --scope global --json
```

The package exports independent factories for background attempts, schedule,
autonomy policy, rules injection, RTK, and Zed integrations. Background Attempts,
Scheduler, and Autonomy Policy are disabled by default. Background attempts use
the managed worktree owner and current-only private state; Scheduler accepts only
strict five-field cron and never replays missed slots. Rules injection fails soft
within a bounded budget and preserves native rules; RTK fails open.

## Stage 18 Routing

`doit` owns the complete evidence -> plan -> confirmation -> execution -> checks
-> report lifecycle; `manager` only adapts it to OpenCode. The route tool has four
destinations: exploration to `mapper`, architecture to `architect`, implementation
to `worker`, and review to `review` or one selected `critic`. Documentation and
quick work remain in `doit`.

The route inventory comes only from resolved host configuration. Callers cannot
inject agents, capabilities, tools, models, or availability. Versioned receipts,
cards, and mapper/worker/review/critic reports are checked at real Task dispatch
and result hooks. Cards bind paths, checks, explicit VCS operations, and separate
execution, publication, and history-rewrite confirmations.

## Boundaries

Portable skills and package assets install independently.

```shell
npm exec -- skills-opencode install --scope project --dry-run
npm exec -- skills-opencode install --scope project --confirm <digest>
```

Commands are thin adapters that pass untrusted arguments to the native Skill
tool; validation, confirmation, batch/review rules, and result format remain the
skill or runner responsibility. `capabilities`, `route`, and `doctor` are package
tools and commands for catalog, routing, and health. `agent_profiles` and the
four agent slash commands are optional UX adapters, not a separate skill.

The package is MIT-licensed; the repository root README has full instructions.
