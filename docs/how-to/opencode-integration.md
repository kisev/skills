# OpenCode Integration

[Русский](../ru/how-to/opencode-integration.md)

`@kisev/agentomatic` is the optional OpenCode-specific layer. Portable
skills have a separate lifecycle and must be installed independently through the
[portable skills guide](portable-skills.md).

## Requirements and Ownership

The package requires Node.js 22+ and OpenCode `>=1.18.29 <1.19.0`.

| Component | Project scope | Global scope |
| - | - | - |
| npm package | project `node_modules` | `node_modules` in the npm project at `~/.config/opencode` |
| Commands | `.opencode/commands` | `~/.config/opencode/commands` |
| Agents | `.opencode/agents` | `~/.config/opencode/agents` |
| Optional wrappers | `.opencode/plugins` | `~/.config/opencode/plugins` |
| Ownership metadata | `.opencode/.agentomatic` | `~/.config/opencode/.agentomatic` |

The package and generated wrappers must remain resolvable after the installer
exits. Import, plugin loading, and npm lifecycle scripts do not install assets,
install portable skills, or edit OpenCode configuration.

## Install

### Project Scope

Run the installer from the project root; the confirmed install also provisions
the persistent npm dependency in the nearest npm project:

```shell
cd /path/to/project
npx --yes @kisev/agentomatic@latest install --dry-run
```

The package lands in project `node_modules` and confirmed assets go under
`.opencode`. Without an npm project upward of the working directory, the plan
reports a manual dependency follow-up instead of creating files.

### Global Scope

Run the installer from any directory:

```shell
npx --yes @kisev/agentomatic@latest install --global --dry-run
```

The confirmed install owns the npm project at `~/.config/opencode`: it creates
a minimal `package.json` when needed and pins the exact executing version with
`npm install --save-exact`. Confirmed assets go under `~/.config/opencode`.
Read-only commands such as `doctor`, `capabilities`, and `agent list` keep
working from any directory through the same explicit form; run `reconcile` and
`uninstall` from the owning npm project through `npx agentomatic`, where the
executing version must match the installed package. Offline setups can install
the dependency by hand first: `npm install --save-exact @kisev/agentomatic`,
then `npx agentomatic install --dry-run`. Pass `--no-dependency` to skip the
provisioning step entirely.

### Development Channel

Address the `dev` dist-tag explicitly to pin its prerelease:

```shell
npx --yes @kisev/agentomatic@dev install --global --dry-run
```

Each successful push to `dev` publishes a unique prerelease and moves only the
`dev` dist-tag. To return to the stable channel, rerun the stable installer
command; it re-pins the dependency to the current stable release.

## Select Assets

In a TTY, `install` opens three selection groups: Skill command adapters, Fixed
agents, and Selectable plugins. Skill commands and six fixed agents start
selected; optional plugins start unselected. Skill command adapters are OpenCode
slash commands that load an already-installed same-named portable skill. A
command adapter selection never selects or installs a skill. Each group supports
an arbitrary subset: Up/Down moves, Space toggles, A selects all, N selects none,
Enter confirms, and Escape cancels.

Outside a TTY, pass all three selection groups. This example selects three
commands, all fixed agents, and no wrapper:

```shell
npx agentomatic install \
  --commands askme,code-review,goal \
  --agents manager,architect,mapper,worker,review,critic \
  --plugins none --dry-run
```

If any selection flag is present outside a TTY, `--commands`, `--agents`, and
`--plugins` are all required. Query exact current names with:

```shell
npx --yes @kisev/agentomatic@latest capabilities --json
```

The selectable wrappers are `rules-injector`, `rtk`, and `zed-bell`; `rtk` is
preselected by the installer. OpenCode loads deployed wrapper files from the
`plugins` directory automatically, so they need no `plugin` array entry; that
array stays reserved for the npm core package. Opt out explicitly with
`--plugins none`.

## RTK Compression Observability

The `rtk` wrapper compresses verbose `bash` tool output above 8,000 characters
through the external RTK CLI, falls back to head+tail truncation when the
binary is unavailable, and appends an
`[rtk: compressed method=...; sizes=...; evidence_complete=false]` marker to
every compressed output. Classified event counters, character savings, and a
capped recent-event list are stored only in
`$XDG_STATE_HOME/opencode/skills/rtk/stats.json` (mode 0600) and never include
command output contents.

Inspect the summary with the `/rtk-stats` command, or machine-readably through
the `rtk.observability` check:

```shell
npx --yes @kisev/agentomatic@latest doctor --json
```

The check reports wrapper deployment, RTK binary availability, event counters,
estimated token savings, and the statistics timestamp.

## Activate the Core Plugin

The installer records whether the selection needs core integration, but
`install` and `uninstall` never create or edit `opencode.json`. Connect the
package with the confirmed `config` command, or add it to the user-owned
`plugin` array for the same scope manually while preserving existing entries:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/agentomatic"]
}
```

For project scope, keep the package in project `node_modules` and configuration
in the project. For global scope, keep the npm project and user configuration
under `~/.config/opencode`. Restart OpenCode after activation or asset changes.

## Configure User Configs

The `config` command connects the package and recommended fragments into
user-owned configuration files:

```shell
npx agentomatic config --global --dry-run
npx agentomatic config --dry-run
```

In a TTY, target and fragment selectors open when flags are omitted. Targets
are agents: global scope targets `~/.config/opencode/opencode.json(c)` and
`tui.json`, `~/.config/kilo/kilo.json(c)` and `tui.json[c]`, and
`~/.config/mimocode/mimocode.json(c)` and `tui.json`; project scope targets
the project `opencode.json(c)` file only. Outside a TTY, pass `--targets` and
`--fragments` explicitly.

Selectable fragments:

| Fragment | Targets | Effect |
| - | - | - |
| `core-plugin` | opencode | Adds `$schema` and registers `@kisev/agentomatic` in `plugin` |
| `skills-state-permissions` | opencode, kilo, mimo | Allows `~/.local/state/agent-skills/**` (plus `~/.config/opencode/skills/**` for OpenCode) in `permission.read`, `permission.edit`, and `permission.external_directory` so the standard skills state paths stop prompting |
| `lsp-preset` | opencode | Adds LSP servers from the shared catalog with standard commands |
| `secrets-guard` | opencode, kilo, mimo | Denies reads and edits of common secret files (`.env*`, keys, credentials) |
| `kilo-display` | kilo | Expands reasoning, terminal, edit, and tool blocks |
| `tui-schema` | opencode, kilo, mimo | Unifies each agent TUI file: per-agent `$schema` (OpenCode, MiMo), `theme: ayu`, `diff_style: stacked`, and the shared leader keybind map; Kilo writes `tui.json[c]`, MiMo and OpenCode write `tui.json` |

The merge never overwrites user data: existing keys, comments, and unrelated
entries are preserved; only absent keys are added; a scalar permission map such
as `"external_directory": "ask"` is widened to a map that keeps the scalar as
the `"*"` entry. Fragments that cannot merge cleanly are reported as conflicts
and skipped without blocking the rest of the plan. Like every mutation, `config`
requires a `--dry-run` preview, an explicitly confirmed apply, and a restart of
the affected tool afterwards. A successful `install` apply prints the matching
`config` dry-run as its next step.

## Preview and Confirm

Every mutation begins with `--dry-run`. The read-only preview reports
operations, conflicts, and restart requirements, and ends with an Apply hint
for the same command that notes the interactive confirmation and the `--yes`
fallback outside a terminal. If reconcile reports modified
managed files or ownership conflicts, it is blocked: no apply consent is
offered. Install or upgrade the current package first, apply its installer
plan, then repeat reconcile; resolve ownership conflicts manually.

```shell
npx agentomatic install --dry-run
```

The mandatory OpenCode flow is a single install run with core integration
confirmed: the wizard asks for command adapters, fixed agents, plugin wrappers,
and core integration; one consent applies the assets, wires the `core-plugin`
fragment into the user config, and provisions the persistent npm dependency in
`~/.config/opencode` that keeps the global plugin resolvable. The dependency
step removes a pinned legacy `@kisev/skills-opencode` in the same pass.
Non-interactive runs pass `--core` (or `--no-core`) with the explicit selection
flags. The `config` command remains the full fragment manager for every target;
applying its `core-plugin` fragment provisions the same dependency when the
installer skipped it. Every confirmed config apply first archives the previous
content of each changed user file into the package archive store
(`~/.local/share/opencode/agentomatic/archive`), content-addressed and
deduplicated; `doctor --json` reports the latest snapshot under
`config.backups`.
Scope-aware commands target the current directory by default. Add `--global`
once to target global state from any directory. The removed `--scope` option
is not accepted. Install or upgrade the package and
apply its installer plan before every reconcile.

Without `--dry-run`, a mutation asks for consent directly. In a TTY, the
interactive selection wizards run first, the plan summary is printed, and
nothing is written until the final question "Apply these changes?" is answered
with Yes. Outside a TTY, pass the explicit selection flags plus `--yes`;
without `--yes` the command fails with "Applying outside a terminal requires
--yes; use --dry-run to preview". Apply rejects unsafe conflicts and remains
transactional.

## Doctor

`doctor` reads integration facts without creating state, recovering journals,
starting plugins, or starting LSP servers:

```shell
npx --yes @kisev/agentomatic@latest doctor
npx --yes @kisev/agentomatic@latest doctor --json
```

The report includes versions, ownership, drift, collisions, archive counts,
redacted configuration projections, runtime summaries, and LSP facts. It does
not serialize raw configuration, environment values, credentials, or secrets.
Exit status `0` is clean, `1` reports findings, and `2` reports invalid
input or an incomplete probe failure.

## Update

Update by running the current stable installer with the same scope and desired
selection, then restart OpenCode:

```shell
npx --yes @kisev/agentomatic@latest install --global --dry-run
```

Rerun the install command without `--dry-run` and confirm the plan summary; the
confirmed install re-pins the persistent dependency to the executed version. The
installer
updates only files whose recorded ownership and SHA-256 still match. User-owned
or modified managed files remain conflicts. Package update does not reset agent
model choices, variants, additional critics, or retained profile configuration.

## Reconcile

`reconcile` classifies current and historical package commands, plugins, agents,
and installation metadata for one scope:

```shell
npx agentomatic reconcile --dry-run
npx agentomatic reconcile --yes
npx agentomatic reconcile --global --dry-run --json
```

Before reconcile, update the package through its owning installer. Manage
portable skills separately with `npx --yes skills@latest update` or
`npx --yes skills@latest remove`; their trees and lock files do not affect the
reconcile plan, conflicts, or operations.

Confirmed reconcile archives the current bytes in a private content-addressed
XDG archive. Package assets are then removed transactionally. User-owned,
unknown, symlink, unsafe, or ambiguous package entries remain unchanged as
findings or conflicts. A no-op preview reports that no reconciliation changes
are required and offers no apply. Portable
skills, their lock files, worktrees, and runtime state are preserved. The archive
is inspectable through `doctor`; no archive restore or purge command is provided.

## Manage Agents

The direct CLI manages fixed-agent models and additional critics without an LLM
call:

```shell
npx --yes @kisev/agentomatic@latest agent list --global
npx agentomatic agent configure manager --global --dry-run
npx agentomatic agent model-set worker --global --model openai/gpt-5 --variant high --dry-run
npx agentomatic critic add security --global --model anthropic/claude-sonnet-4-6 --dry-run
npx agentomatic agent reconcile --global --dry-run
```

Fixed roles keep their names, prompts, and permissions; only model and variant
change. Additional critics use `critic-<safe-suffix>`. Every mutation uses the
same preview and confirmation contract.

## Uninstall

Keep the package resolvable until its assets are removed:

1. Preview and confirm package-owned asset removal.
2. Remove `@kisev/agentomatic` from the user-owned `plugin` array.
3. Uninstall the dependency from the same npm project.
4. Restart OpenCode.

```shell
npx agentomatic uninstall --dry-run
npx agentomatic uninstall --yes
npm uninstall @kisev/agentomatic
```

For global scope, run the same commands from the persistent npm project
at `~/.config/opencode` with `--global`, then uninstall the dependency there.
Uninstall archives exact manifest-owned assets and
preserves modified files as conflicts, along with worktrees, runtime state, and
retained profile configuration. It does not remove portable skills or edit
`opencode.json`. No archive restore or purge command is provided.

## Boundaries

- Portable skills and package assets install, update, and uninstall independently.
- Commands corresponding to skills are thin adapters; the portable skill remains
  authoritative and must be installed separately.
- The only package tool is `route`; it has no slash command. Administrative
  operations use the direct `agentomatic` CLI.
- `install` and `uninstall` never edit `opencode.json`; the `config` command is
  the only confirmed path for configuration fragments.
- Global scope is cwd-independent; project scope targets `.opencode` under the
  current directory.
- The installer owns only files proved by manifests and exact hashes.
- npm `latest` is the stable channel; npm `dev` is an explicit moving
  development channel and never selects the next stable version.
- The package is MIT-licensed. Current inventory and checks are in
  [Migration Inventory](../migration-inventory.md) and
  [Verification](../verification.md).
