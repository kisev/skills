# OpenCode Integration

[Русский](../ru/how-to/opencode-integration.md)

`@kisev/agentomatic` is the optional OpenCode-specific layer. Portable
skills have a separate lifecycle and must be installed independently through the
[portable skills guide](portable-skills.md).

## Requirements and Ownership

The package requires Node.js 22.13+ and OpenCode `>=2.0.0 <2.1.0`.
See [common CLI conventions](../reference/cli.md) for configuration precedence,
environment variables, diagnostics and machine output. The existing wizard remains available.

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

## OpenCode V2

All patch releases in the `2.0.x` minor are supported. Exact versions
in `evals/contracts/opencode-compatibility.json` are verification samples, not an
allowlist. The package and optional wrappers use the native V2 `setup` entrypoint,
hooks, and ordered permissions. There is no V1 runtime or compatibility gate.
For OpenCode V1, keep the last `11.0.x` stable
[release](https://github.com/kisev/skills/releases)
instead of installing the `dev` channel. V1 and V2 share configuration locations;
do not run V1 against configuration converted to native V2 shapes.

After upgrading an existing installation, use the installer upgrade preview and
confirm it to replace the managed plugin wrappers, then restart OpenCode. Old
function-only wrappers cannot load in V2. Preserve user-modified wrapper files;
the installer reports conflicts instead of overwriting them.

Config setup writes native `plugins` and `permissions` in `opencode.json(c)`.
The core plugin is registered as an exact-version registry spec
(`@kisev/agentomatic@<version>`): OpenCode V2 resolves bare package names
through the npm `latest` dist-tag, which can select a different build than the
installed one. Rerunning the core fragment repins a bare or stale registration
in place while foreign plugin entries stay untouched.
It converts only the sections needed by the selected fragments, not the entire
configuration. Conflicting legacy/native sections are reported rather than merged
by guesswork. Do not register the same package twice.

Maintainers install only V2 through the npm backend in `mise.toml`.
`task package:check` runs installed-tarball smoke checks on its pinned patch,
including real permission evaluation, alongside hostless behavior tests. These checks need no
model credentials; dependency provisioning can require registry access.

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

The `rtk` wrapper compresses verbose `shell` tool output above 8,000 characters
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

The installer records whether the selection needs core integration. A confirmed
`install` with core selected applies the same core config step as `config`;
`uninstall` never edits user configuration. You can also connect the package with
the confirmed `config` command, or add it to the user-owned `plugins` array for
the same scope manually while preserving existing entries:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["@kisev/agentomatic"]
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
`cli.json`, `~/.config/kilo/kilo.json(c)` and `tui.json[c]`, and
`~/.config/mimocode/mimocode.json(c)` and `tui.json`; project scope targets
the project `opencode.json(c)` file only. Outside a TTY, pass `--targets` and
`--fragments` explicitly.

Selectable fragments:

| Fragment | Targets | Effect |
| - | - | - |
| `core-plugin` | opencode | Adds `$schema` and registers `@kisev/agentomatic` in `plugins` |
| `skills-state-permissions` | opencode, kilo, mimo | Allows reads, edits, and external-directory access to standard skills state paths under `~/.local/state/agent-skills/**`; OpenCode also allows reads and external-directory access under the canonical portable-skills tree `~/.agents/skills/**` and the legacy `~/.config/opencode/skills/**`, plus `external_directory` enumeration of those exact roots and `~/.agents` itself, so directory scans (glob/list) do not prompt. OpenCode uses ordered `permissions`; Kilo/MiMo retain their `permission` maps |
| `secrets-guard` | opencode, kilo, mimo | Denies reads and edits of common secret files (`.env*`, keys, credentials) |
| `kilo-display` | kilo | Expands reasoning, terminal, edit, and tool blocks |
| `tui-schema` | opencode, kilo, mimo | OpenCode writes global `cli.json` with its V2 schema, `theme.name: ayu`, and native keybind IDs. Kilo/MiMo retain their TUI formats, `theme: ayu`, stacked diffs, and existing keybind IDs |

Comments and unrelated entries are preserved. OpenCode migrates the touched
legacy `plugin`, `permission`, or standalone `tools` section to native V2.
Permission scalars become wildcard rules; tool/action aliases become `shell`,
`subagent`, or `edit`. Existing rule order is retained, and new preset rules
follow it. Differing legacy/native sections, mixed legacy `tools` and
`permission`, unsupported legacy actions, or explicit rules conflicting with
the preset are conflicts, not silently overridden. Kilo/MiMo still widen scalar
permission maps while retaining the scalar as `"*"`.
Fragments that cannot merge cleanly are reported as conflicts
and skipped without blocking the rest of the plan. Like every mutation, `config`
requires a preview, an explicitly confirmed apply, and a restart of the affected
tool afterwards. A confirmed `install` with core selected applies its core config
step; a failed config step prints a retry command. Other fragments use `config`.

V2 no longer reads `tui.json` as its terminal settings. If that file exists but
`cli.json` does not, start V2 once so its built-in migration preserves your
preferences, then repeat config setup. The preset leaves existing `cli.json`
values unchanged and does not translate the old stacked-diff setting or retired
keybindings into unrelated V2 settings. Project-local terminal configuration is
not supported. Kilo and MiMo files are unaffected by this V2 migration.

`lsp-preset` is removed: V2 accepts `lsp` but currently does not run language
servers. Existing user `lsp` entries remain untouched; use your project's lint,
typecheck, or compiler commands for validation.

Selecting `core-plugin` may access npm and update `package.json`,
`package-lock.json`, and `node_modules`; the preview shows this dependency plan.
An npm failure is reported separately from the committed config transaction.
Fix the dependency error and repeat the preview. `install --no-dependency` disables
provisioning through the whole install path.

Config previews do not write locks or recover interrupted transactions. Interactive
apply binds the displayed plan to a five-minute one-use in-process receipt;
changed source bytes require a fresh preview. A separate `--dry-run` does not
issue a reusable cross-process receipt; `--yes` authorizes a freshly built plan.
For a pending config transaction, inspect and explicitly confirm recovery:

```shell
npx agentomatic config recover --global --dry-run
npx agentomatic config recover --global
```

Omit `--global` for project scope. Recovery restores the interrupted transaction
before a new config preview; changed recovery evidence requires another preview.

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
\--yes; use --dry-run to preview". Apply rejects unsafe conflicts and remains
transactional.

## Doctor

`doctor` reads integration facts without creating state, recovering journals,
starting plugins, or starting LSP servers:

```shell
npx --yes @kisev/agentomatic@latest doctor
npx --yes @kisev/agentomatic@latest doctor --json
```

The report includes versions, ownership, drift, collisions, archive counts,
redacted JSON/JSONC configuration projections, runtime summaries, and LSP facts
marked unsupported in V2 rather than active. Missing LSP binaries are not OpenCode
dependency failures. It does
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

Specialist profiles are optional for skill-driven independent reviews.
`code-review` asks which available critics and how many to use; if none are
installed, the current agent launches ordinary independent native subagents.
The core plugin applies routing receipts and structured-report checks to
package-managed profiles and explicitly routed calls, not ordinary native
subagents. No standalone `opencode run` workaround or agent installation is
required for that fallback.
Routed independent critics may return `review_report` or a code-review receipt;
the caller retains real native invocation identities in reviewmatic's draft.
Parallel critic calls keep separate bindings. Receipts expire before launch;
an already admitted review does not expire merely because the model took longer.
The core plugin supplies actual current session identity to primary and child
agents for receipts; this metadata does not authorize mutations or publication.

Rendered agent files use `permissions` and `provider/model#variant`. The CLI
retains separate `--model` and `--variant` flags and saved profile selections.
Interactive model selection reads the V2 `/api/model` snapshot through
`opencode api`; it does not call an LLM or force a catalog refresh. OpenCode may
start its managed service. If the snapshot is unavailable, pass an exact model
and variant explicitly.

## Uninstall

Keep the package resolvable until its assets are removed:

1. Preview and confirm package-owned asset removal.
2. Remove `@kisev/agentomatic` from the user-owned `plugins` array.
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
- A confirmed `install` with core selected merges its `plugin` entry into
  `opencode.json` through the config executor. `uninstall` preserves user configuration.
- Global scope is cwd-independent; project scope targets `.opencode` under the
  current directory.
- The installer owns only files proved by manifests and exact hashes.
- npm `latest` is the stable channel; npm `dev` is an explicit moving
  development channel and never selects the next stable version.
- The package is MIT-licensed. Current inventory and checks are in
  [Migration Inventory](../migration-inventory.md) and
  [Verification](../verification.md).
