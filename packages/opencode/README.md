# OpenCode Integration

[Русский](README.ru.md)

`@kisev/skills-opencode@2.0.3` is the optional OpenCode-specific layer. Portable
skills have a separate lifecycle and must be installed independently through the
[root portable flow](../../README.md).

## Requirements and Ownership

The package requires Node.js 22+ and OpenCode `>=1.18.29 <1.19.0`.

| Component          | Project scope                | Global scope                                              |
| ------------------ | ---------------------------- | --------------------------------------------------------- |
| npm package        | project `node_modules`       | `node_modules` in the npm project at `~/.config/opencode` |
| Commands           | `.opencode/commands`         | `~/.config/opencode/commands`                             |
| Agents             | `.opencode/agents`           | `~/.config/opencode/agents`                               |
| Optional wrappers  | `.opencode/plugins`          | `~/.config/opencode/plugins`                              |
| Ownership metadata | `.opencode/.skills-opencode` | `~/.config/opencode/.skills-opencode`                     |

The package and generated wrappers must remain resolvable after the installer
exits. Import, plugin loading, and npm lifecycle scripts do not install assets,
install portable skills, or edit OpenCode configuration.

## Persistent Package Install

### Project Scope

Install in the repository's npm project and run the CLI from that project root:

```shell
cd /path/to/project
npm install --save-exact @kisev/skills-opencode@2.0.3
npm exec -- skills-opencode install --scope project --dry-run
```

The package remains in project `node_modules`; confirmed assets go under
`.opencode`.

### Global Scope

Use `~/.config/opencode` as the persistent npm project:

```shell
mkdir -p "$HOME/.config/opencode"
cd "$HOME/.config/opencode"
test -f package.json || npm init --yes
npm install --save-exact @kisev/skills-opencode@2.0.3
npm exec -- skills-opencode install --scope global --dry-run
```

Keep the dependency in that npm project's `package.json` and lock file.
Confirmed assets go under `~/.config/opencode`.

## Select Assets

In a TTY, `install` opens four selection groups: Skill command adapters, Package
command adapters, Fixed agents, and Selectable plugins. The two command groups
and six fixed agents start selected; optional plugins start unselected. Skill
command adapters are OpenCode slash commands that load an already-installed
same-named portable skill. Package command adapters invoke package tools. A
command adapter selection never selects or installs a skill.

Outside a TTY, pass all three selection groups. This example selects three
commands, all fixed agents, and no wrapper:

```shell
npm exec -- skills-opencode install --scope project \
  --commands doctor,reconcile,agent-profiles \
  --agents manager,architect,mapper,worker,review,critic \
  --plugins none --dry-run
```

If any selection flag is present outside a TTY, `--commands`, `--agents`, and
`--plugins` are all required. Query exact current names with:

```shell
npm exec -- skills-opencode capabilities --json
```

The selectable wrappers are `rules-injector`, `rtk`, and `zed-bell`.

## Activate the Core Plugin

The installer records whether the selection needs core integration, but never
creates or edits `opencode.json`. Add the package to the user-owned `plugin`
array for the same scope while preserving existing entries:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

For project scope, keep the package in project `node_modules` and configuration
in the project. For global scope, keep the npm project and user configuration
under `~/.config/opencode`. Restart OpenCode after activation or asset changes.

## Preview and Confirm

Every mutation begins with `--dry-run`. The preview reports operations,
conflicts, restart requirements, receipt expiry, separate plan and confirmation
digests, and the exact confirmation command. If reconcile reports modified
managed files or ownership conflicts, it is blocked: no receipt or Apply command
is issued. Install or upgrade the current package first, apply its exact
installer confirmation, then repeat reconcile; resolve ownership conflicts
manually.

```shell
npm exec -- skills-opencode install --scope project --dry-run
```

The mandatory OpenCode flow is: persistent npm install, `install --dry-run`, the
exact confirmation command printed by that preview, add the package to the
user-owned `plugin` entry, and restart OpenCode. Use the persistent npm project
at `~/.config/opencode` for global commands. Install or upgrade the package and
apply its installer plan before every reconcile.

The preview has a deterministic `plan_digest` and a unique
`confirmation_digest`. A later dry-run in the same scope supersedes any older
unconsumed preview, including previews from another package or agent operation;
the older confirmation is rejected.

Run the command printed by the preview, including all selection flags. Receipts
are private, valid for 10 minutes, single-use, and bound to the action, scope,
root, and current inventory. Apply rejects stale state and unsafe conflicts.

## Doctor

`doctor` reads integration facts without creating receipts, recovering journals,
starting plugins, or starting LSP servers:

```shell
npm exec -- skills-opencode doctor --scope project
npm exec -- skills-opencode doctor --scope project --json
```

The report includes versions, ownership, drift, collisions, archive counts,
redacted configuration projections, runtime summaries, and LSP facts. It does
not serialize raw configuration, environment values, receipts, credentials, or
secrets. Exit status `0` is clean, `1` reports findings, and `2` reports invalid
input or an incomplete probe failure.

## Update

From the npm project that owns the dependency, install the exact intended
version, preview and confirm `install` with the same scope and desired selection,
then restart OpenCode:

```shell
npm install --save-exact @kisev/skills-opencode@2.0.3
npm exec -- skills-opencode install --scope project --dry-run
```

Use the complete confirmation command printed by the preview. The installer
updates only files whose recorded ownership and SHA-256 still match. User-owned
or modified managed files remain conflicts. Package update does not reset agent
model choices, variants, additional critics, or retained profile configuration.

## Reconcile

`reconcile` classifies current and historical portable skills, package commands,
plugins, agents, and installation metadata for one scope:

```shell
npm exec -- skills-opencode reconcile --scope project --dry-run
npm exec -- skills-opencode reconcile --scope project --confirm <digest>
npm exec -- skills-opencode reconcile --scope global --dry-run --json
```

Before reconcile, first update the package in its owning npm project and apply
the exact installer plan. Reconcile does not install, update, or remove portable
skills; use only the pinned `npx --yes skills@1.5.23` flow for those skills.

Confirmed reconcile archives exact-owned retired assets in a private
content-addressed XDG archive and removes their deployed copies. Modified,
user-owned, unknown, symlink, unsafe, or ambiguous entries remain unchanged as
findings or conflicts. Worktrees and runtime state are preserved. The archive is
inspectable through `doctor`; no archive restore or purge command is provided.

## Manage Agents

The direct CLI manages fixed-agent models and additional critics without an LLM
call:

```shell
npm exec -- skills-opencode agent list --scope global
npm exec -- skills-opencode agent configure manager --scope global --dry-run
npm exec -- skills-opencode agent model-set worker --scope global --model openai/gpt-5 --variant high --dry-run
npm exec -- skills-opencode critic add security --scope global --model anthropic/claude-sonnet-4-6 --dry-run
npm exec -- skills-opencode agent reconcile --scope global --dry-run
```

Fixed roles keep their names, prompts, and permissions; only model and variant
change. Additional critics use `critic-<safe-suffix>`. Every mutation uses the
same preview and one-time confirmation contract.

## Uninstall

Keep the package resolvable until its assets are removed:

1. Preview and confirm package-owned asset removal.
2. Remove `@kisev/skills-opencode` from the user-owned `plugin` array.
3. Uninstall the dependency from the same npm project.
4. Restart OpenCode.

```shell
npm exec -- skills-opencode uninstall --scope project --dry-run
npm exec -- skills-opencode uninstall --scope project --confirm <digest>
npm uninstall @kisev/skills-opencode
```

For global scope, run the same flow from `~/.config/opencode` with
`--scope global`. Uninstall archives exact manifest-owned assets and preserves
modified files as conflicts, along with worktrees, runtime state, and retained
profile configuration. It does not remove portable skills or edit
`opencode.json`. No archive restore or purge command is provided.

## Boundaries

- Portable skills and package assets install, update, and uninstall independently.
- Commands corresponding to skills are thin adapters; the portable skill remains
  authoritative and must be installed separately.
- Package tools are `capabilities`, `route`, `doctor`, `agent_profiles`, and
  `reconcile`; `route` has no slash command.
- The installer owns only files proved by manifests and exact hashes.
- The package is MIT-licensed. Current inventory and checks are in
  [Migration Inventory](../../docs/migration-inventory.md) and
  [Verification](../../docs/verification.md).
