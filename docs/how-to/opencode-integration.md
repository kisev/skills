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

`npm view` previews the registry version; `latest` and `dev` can move before
installation. npx runs a CLI without installing it globally. After confirming
an install, use `npm list` in the owning npm project to check the persistent
dependency; a dry run alone does not install it.

### Project Scope

Run the installer from the project root; the confirmed install also provisions
the persistent npm dependency in the nearest npm project:

```shell
cd /path/to/project
# Registry version
npm view --prefer-online @kisev/agentomatic@latest version

# Preview, then confirm the install
npx --yes @kisev/agentomatic@latest install --dry-run
npx --yes @kisev/agentomatic@latest install

# Installed dependency in the owning npm project
npm list @kisev/agentomatic --depth=0
```

The package lands in project `node_modules` and confirmed assets go under
`.opencode`. Without an npm project upward of the working directory, the plan
reports a manual dependency follow-up instead of creating files.

### Global Scope

Run the installer from any directory:

```shell
# Registry version
npm view --prefer-online @kisev/agentomatic@latest version

# Preview, then confirm the install
npx --yes @kisev/agentomatic@latest install --global --dry-run
npx --yes @kisev/agentomatic@latest install --global

# Installed dependency, not npm's global CLI prefix
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
```

The confirmed install owns the npm project at `~/.config/opencode`: it creates
a minimal `package.json` when needed and pins the exact executing version with
`npm install --save-exact`. Confirmed assets go under `~/.config/opencode`.
Read-only commands such as `status`, `doctor`, `catalog`, and `agent list` keep
working from any directory through the same explicit form; run `maintenance cleanup` and
`uninstall` from the owning npm project through `npx agentomatic`, where the
executing version must match the installed package. Offline setups can install
the dependency by hand first: `npm install --save-exact @kisev/agentomatic`,
then `npx agentomatic install --dry-run`. Pass `--no-dependency` to skip the
provisioning step entirely.

### Development Channel

Address the `dev` dist-tag explicitly to pin its prerelease:

```shell
# Registry version
npm view --prefer-online @kisev/agentomatic@dev version

# Preview, then confirm the install
npx --yes @kisev/agentomatic@dev install --global --dry-run
npx --yes @kisev/agentomatic@dev install --global

# Installed dependency
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
```

Each successful push to `dev` publishes a unique prerelease and moves only the
`dev` dist-tag. To return to the stable channel, rerun the stable installer
command; it re-pins the dependency to the current stable release.

## Select Assets

In a TTY, `install` selects command adapters, optional plugins, and core
connection, then offers presets for the chosen agent harness. The six fixed
agents (`manager`, `architect`, `mapper`, `worker`, `review`, `critic`) deploy
only as one complete package: `install` has no agent flag, no agent prompt, and
never asks about models or critics — every agent decision belongs to the
confirmed `configure agent` command afterwards. Model setup is therefore not
part of install at all. A repeat install starts
from the saved component selection; deselection shows owned-file removals.
On first install, all skill commands start selected; `rtk` is the default
wrapper. Skill command adapters are OpenCode
slash commands that load an already-installed same-named portable skill. A
command adapter selection never selects or installs a skill. Each option carries
its description inline in the label, visible on every line rather than only under
the cursor (adapters from the command catalog; presets from the config
fragments), and long descriptions are cut to the terminal width with an
ellipsis. Every option screen after the first offers `← Back`; choosing it (Space
then Enter in a multi-select) returns to the previous screen with the earlier
selection restored. The group controls read: Up/Down moves, Space toggles, A
toggles all selections on and off, Enter confirms, and Escape cancels.

Outside a TTY, the first install requires both selection groups; subsequent
runs can reuse the saved set. This example selects three commands and no
wrapper:

```shell
npx agentomatic install \
  --commands askme,code-review,goal \
  --plugins none --dry-run
```

If any selection flag is present outside a TTY, `--commands` and `--plugins`
are both required. Query exact current names with:

```shell
npx --yes @kisev/agentomatic@latest catalog --json
```

If a saved selection contains a command removed by an update, rerun `install`
with both selection flags and current names. The explicit selection
replaces the saved component names before validation; the saved core connection
choice stays unchanged unless `--core` or `--no-core` overrides it. Preview with
`--dry-run`, then confirm the same selection. This does not migrate skill state.

Target question wording: the installer calls the supported hosts agent
harnesses — `opencode`, `kilo`, and `mimo` are the applications whose
configuration files accept the package fragments. Preset questions explain
themselves: presets are permission, secrets-guard, and terminal-settings
fragments merged into each selected harness configuration.

The selectable wrappers are `rules-injector`, `rtk`, `zed-bell`, and
`code-simplify`; `rtk` is preselected by the installer. OpenCode loads deployed
wrapper files from the `plugins` directory automatically, so they need no
`plugin` array entry; that array stays reserved for the npm core package. Opt
out explicitly with `--plugins none`.

The `code-simplify` wrapper injects the compact prevention criteria into every
session. Its options travel through a plugin array entry:
`"plugins": [["@kisev/agentomatic/plugins/code-simplify", { "level": "full",
"scope": ["worker", "review", "critic"] }]]`. The `level` option selects
`lite` (ladder only), `full` (ladder plus the audit contract, the default),
`ultra` (plus usage-search and safety-floor guards), or `off`. The optional
`scope` array enumerates the fixed roles `manager`, `architect`, `mapper`,
`worker`, `review`, and `critic` — `critic-*` specialist profiles count as
`critic` — and restricts the injection to the listed roles; without the option
every role is injected, as before the option existed. Keeping `worker`,
`review`, and `critic` in the scope preserves the review panel's access to the
same criteria.

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
`install` with core selected applies the same core config step as
`configure integration`; `--no-core` disconnects the plugin without removing
the npm dependency. `uninstall` proposes disconnection too. You can also connect
the package with the confirmed `configure integration` command, or add it to the user-owned `plugins` array for
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

`configure` opens a menu for components, agent models, critics, and integration.
`configure components` changes the installed set without resetting models.
`configure integration` connects the package and recommended fragments into
user-owned configuration files:

```shell
npx agentomatic configure integration --global --dry-run
npx agentomatic configure integration --dry-run
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
| `core-disable` | opencode | Removes only agentomatic/legacy package registrations, preserving other plugins and presets; cannot be combined with `core-plugin` |
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
Fragments that cannot merge cleanly are reported as conflicts. The CLI blocks
apply until conflicts are resolved or excluded from the selection. Like every
mutation, configuration requires a preview, explicit confirmation, and a restart
of the affected application afterwards. Connection choices are saved for repeat
install and repair. A failed install configuration step reports which earlier
stages completed and how to continue with `configure integration`.

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
npx agentomatic maintenance recover --global --dry-run
npx agentomatic maintenance recover --global
```

Omit `--global` for project scope. Recovery restores the interrupted transaction
before a new config preview; changed recovery evidence requires another preview.

## Preview and Confirm

Every mutation begins with `--dry-run`. The read-only preview reports
operations, conflicts, and restart requirements, and ends with an Apply hint
for the same command that notes the interactive confirmation and the `--yes`
fallback outside a terminal. If cleanup reports modified
managed files or ownership conflicts, it is blocked: no apply consent is
offered. Install or upgrade the current package first, apply its installer
plan, then repeat cleanup; resolve ownership conflicts manually.

```shell
npx agentomatic install --dry-run
```

The OpenCode flow is a single install run: the wizard asks for command adapters,
wrappers, core connection, and optional harness presets. Install always deploys
the six fixed agents as one package and never offers agent models, composition,
or critics. One confirmation applies owned components and profiles, wires the `core-plugin`
fragment into the user config, and provisions the persistent npm dependency in
`~/.config/opencode` that keeps the global plugin resolvable. The dependency
step removes a pinned legacy `@kisev/skills-opencode` in the same pass.
Non-interactive runs pass `--core` (or `--no-core`) with the explicit selection
flags. Install summaries list every deployed fixed role with its model (or
`default (host)` when none is saved) and close with the critic panel; both
epilogues point at `agent list`, the canonical overview, and `configure agent`,
the single mutation point. `configure integration` remains the full fragment manager for every target;
applying its `core-plugin` fragment provisions the same dependency when the
installer skipped it. Before showing its first screen, `configure integration`
compares the default selection with the current files: a fully satisfied state
asks nothing and prints the header, `No configuration changes are required.`,
and the critic panel, while a partial state asks only about divergent targets and
presets and leaves merged presets out. The plan is rendered once, and the run
closes with an explicit `Done:` line. Every confirmed config apply first archives the previous
content of each changed user file into the package archive store
(`~/.local/share/opencode/agentomatic/archive`), content-addressed and
deduplicated; `doctor --json` reports the latest snapshot under
`config.backups`.
Scope-aware commands target the current directory by default. Add `--global`
once to target global state from any directory. The removed `--scope` option
is not accepted. Components/profiles, npm provisioning, and application configuration
are separate stages, not one atomic transaction. A later failure leaves completed
stages in place and reports continuation; inspect `status` before retrying.

Without `--dry-run`, a mutation asks for consent directly. In a TTY, the
interactive selection wizards run first, the plan summary is printed, and
nothing is written until the final question "Apply the displayed changes?" is answered
with Yes. Outside a TTY, pass the explicit selection flags plus `--yes`;
without `--yes` the command fails with guidance to preview or confirm explicitly.
Preview never creates locks or automatically recovers journals. A changed source
invalidates the confirmed plan; each local transaction rolls back on failure.

## Inspect the Installation

```shell
npx agentomatic status --global
npx agentomatic status --global --json
```

`status` shows the installed component set, plugin connection, npm dependency,
saved models, and critic pool. `agent list` provides the profile table;
`not-installed` means a saved or available role is not selected, not damaged.
`catalog --json` describes the running package's capabilities, not this installation.

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

## Maintenance

`maintenance cleanup` classifies current and historical package commands, plugins, agents,
and installation metadata for one scope:

```shell
npx agentomatic maintenance cleanup --dry-run
npx agentomatic maintenance cleanup --yes
npx agentomatic maintenance cleanup --global --dry-run --json
npx agentomatic maintenance repair --global --dry-run
```

Before cleanup, update the package through its owning installer. Manage
portable skills separately with `npx --yes skills@latest update` or
`npx --yes skills@latest remove`; their trees and lock files do not affect the
cleanup plan, conflicts, or operations.

Confirmed cleanup archives the current bytes in a private content-addressed
XDG archive. Package assets are then removed transactionally. User-owned,
unknown, symlink, unsafe, or ambiguous package entries remain unchanged as
findings or conflicts. A no-op preview reports that no reconciliation changes
are required and offers no apply. Portable
skills, their lock files, worktrees, and runtime state are preserved. The archive
is inspectable through `doctor`; no archive restore or purge command is provided.

`maintenance repair` restores missing selected components and regenerates owned
files from saved model choices. It does not add unselected roles or overwrite
changed managed bytes. Resolve ownership/byte conflicts before retrying; mode-only
damage to exact-owned bytes can be repaired. Without a saved installation, use
`install`. `maintenance recover` restores an interrupted journal only after its
paths and digest are confirmed, then requires a fresh preview.

## Manage Agents

The direct CLI manages fixed-agent models and additional critics without an LLM
call:

```shell
npx --yes @kisev/agentomatic@latest agent list --global
npx agentomatic configure agent manager --global --dry-run
npx agentomatic configure agent worker --global --model openai/gpt-5 --variant high --dry-run
npx agentomatic configure agent critic-security --global --model anthropic/claude-sonnet-4-6 --dry-run
npx agentomatic configure critics --global
```

`configure agent` is the single mutation point for agent models and critics:
nameless (or through the `configure critics` alias) it opens one staged editor
over every agent; with a name it sets the model of an existing profile, and a
fresh `critic-<safe-suffix>` name adds that critic. `agent` and `agent list`
are read-only over profiles, models, ownership, collisions, and drift.
Install deploys the fixed roles only as the whole package; the package-owned
fixed critic `critic` always ships with it and is kept separate from the
additional `critic-*` pool in every summary and epilogue.
Fixed roles keep their names, prompts, and permissions; only model and variant
change; generated delegation allowlists reflect the selected roles and critic pool.
Saving a model for an uninstalled fixed role does not install it. Removing an
additional critic happens in the staged editor. Every mutation uses the
same preview and confirmation contract.

Nameless `configure agent` (and its alias `configure critics`) opens one staged
editor over every agent: it first prints the critic panel (every package-owned critic row and every
additional `critic-<suffix>` pool entry, or `No critics`), then offers model changes,
adding critics, and removal until `Done`, and applies the staged batch behind the
usual preview and confirmation. Unsafe critic input such as `sonnet-5.5`
converts to `critic-sonnet-5-5` after an explicit confirmation, rejected input
re-prompts with the naming requirements, and the model cascade walks
Provider → Model → Variant, marking the saved variant `(default)` and offering
`(none)` for no variant. When the OpenCode host is not running, the wizard shows
`Start opencode in another terminal to browse models, or enter provider/model
manually` and accepts an explicit value; the CLI never starts the host itself.

Specialist profiles are optional for skill-driven independent reviews.
`code-review` asks once which available critics and how many to use and which
arbitrator to select; if none are
installed, the current agent launches ordinary independent native subagents
running the session's agent, provider, and model, and the recorded selection
is never substituted silently. The core plugin applies routing receipts and
structured-report checks to
package-managed profiles and explicitly routed calls, not ordinary native
subagents. No standalone `opencode run` workaround or agent installation is
required for that fallback.
Routed independent critics may return `review_report` or a code-review receipt;
the caller retains real native invocation identities in reviewmatic's draft.
Critics receive the recorded context package — goal, claims with sources,
constraints, prior decisions, questions — as their primary task context and
answer the questions assigned to them in their receipts; a separate arbitrator
then returns one receipt with a verdict for every critic finding and the
consolidated decisions, so the orchestrating agent adds no full review of its
own. Parallel critic
calls keep separate bindings. Receipts expire before launch;
an already admitted review does not expire merely because the model took longer.
The core plugin supplies actual current session identity to primary and child
agents for receipts; this metadata does not authorize mutations or publication.

Rendered agent files use `permissions` and `provider/model#variant`. The CLI
retains separate `--model` and `--variant` flags and saved profile selections.
Interactive model selection reads the V2 `/api/model` snapshot through
`opencode api`; it does not call an LLM or force a catalog refresh. OpenCode may
start its managed service. If the snapshot is unavailable, the wizard asks for
an exact provider/model and an optional variant as text input instead of
aborting; non-interactive runs pass `--model` and `--variant` explicitly.

## Uninstall

Keep the package resolvable until its assets are removed:

The preview separates owned components, plugin disconnection, npm removal, and
saved models. Disconnection is proposed by default; `--no-disconnect` retains it.
Models are retained. npm removal is opt-in with `--remove-dependency` or the
interactive question. Other configuration presets remain unchanged.

```shell
npx agentomatic uninstall --dry-run
npx agentomatic uninstall --yes
npx agentomatic uninstall --remove-dependency --yes
```

For global scope, run the same commands from the persistent npm project
at `~/.config/opencode` with `--global`, or invoke the exact-version package from
any directory. Keep it resolvable until the command completes, then restart OpenCode.
Uninstall archives exact manifest-owned assets and
preserves modified files as conflicts, along with worktrees, runtime state, and
retained profile configuration. The CLI blocks unsafe conflicts before removal.
It can edit only the selected plugin registrations in `opencode.json(c)` and
explicitly remove the package dependency. It does not remove portable skills.
Completed local stages are not rolled back if a later npm step fails; inspect
`status` and retry the same uninstall choices. No archive restore or purge command is provided.

## Boundaries

- Portable skills and package assets install, update, and uninstall independently.
- Commands corresponding to skills are thin adapters; the portable skill remains
  authoritative and must be installed separately.
- The only package tool is `route`; it has no slash command. Administrative
  operations use the direct `agentomatic` CLI.
- A confirmed `install` with core selected merges its `plugin` entry into
  `opencode.json` through the config executor. `uninstall` preserves unrelated configuration.
- Global scope is cwd-independent; project scope targets `.opencode` under the
  current directory.
- The installer owns only files proved by manifests and exact hashes.
- npm `latest` is the stable channel; npm `dev` is an explicit moving
  development channel and never selects the next stable version.
- The package is MIT-licensed. Current inventory and checks are in
  [Migration Inventory](../migration-inventory.md) and
  [Verification](../verification.md).
