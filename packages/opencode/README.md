# OpenCode Integration

[Русский](README.ru.md)

`@kisev/skills-opencode` is the optional npm integration. It does not include
portable skills or mutate configuration on import.
Managed files use exact SHA-256 ownership checks.

## Install Skills

Install portable skills first:

```shell
npx --yes skills add kisev/skills --agent opencode --skill '*' --copy --yes
```

Use `--skill <name>` for one skill. `npx skills` accepts a reproducible tag URL,
for example `https://github.com/kisev/skills/tree/v1.1.1`; the package never
installs or updates skills and reports the exact `npx skills add` command when a
skill is missing.

## Install Integration

```shell
npm install @kisev/skills-opencode@1.1.1
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

## Read-only Doctor

`doctor` reports facts without writing:

```shell
npm exec -- skills-opencode doctor --scope project
npm exec -- skills-opencode doctor --scope global --json
```

## Reconcile Retired Assets

`reconcile` previews retirement and preserves conflicts:

```shell
npm exec -- skills-opencode reconcile --scope project --dry-run
npm exec -- skills-opencode reconcile --scope project --confirm <digest>
npm exec -- skills-opencode reconcile --scope global --dry-run --json
```

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

When the catalog is unavailable, use exact `--model <provider/model>` and an
optional `--variant`; `provider/model` identifies the selected model. The
optional `agent_profiles` tool and slash commands adapt the same direct-CLI
plan/apply contract.

```shell
npm exec -- skills-opencode critic add security --scope global \
  --model anthropic/claude-sonnet-4-6 --dry-run
npm exec -- skills-opencode critic remove security --scope global --dry-run
```

## Upgrade and Uninstall

```shell
npm exec -- skills-opencode uninstall --scope global --dry-run
npm exec -- skills-opencode uninstall --scope global --confirm <digest>
```

The full JSON install preview is:

```shell
npm exec -- skills-opencode install --scope global --dry-run --json
```

## Runtime Options

Plugins are independent and stateful ones are opt-in.

```shell
npm exec -- skills-opencode agent list --scope global --json
```

## Boundaries

Portable skills and package assets install independently.

```shell
npm exec -- skills-opencode install --scope project --dry-run
npm exec -- skills-opencode install --scope project --confirm <digest>
```

The package is MIT-licensed; the repository root README has full instructions.
