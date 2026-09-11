# Verification

[Русская версия](ru/verification.md)

## Release 2.0.5

The exact portable source is
`https://github.com/kisev/skills/tree/v2.0.5`; the optional package is
`@kisev/skills-opencode@2.0.5`. Portable installation pins
`npx --yes skills@1.5.23`. The package requires Node.js 22+ and declares OpenCode
`>=1.18.29 <1.19.0`.

## Portable Installation

The global contract for both supported hosts is:

```shell
npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.5 --agent opencode --agent codex --skill '*' --copy --global --yes
```

It produces one canonical copy in `~/.agents/skills`. Without `--global`, the
project copy is `.agents/skills`. `kisev/skills` selects latest source separately
from the exact tag URL.

A tag-based installation remains pinned during `update`. Moving to another tag
requires repeating `add` with the new exact URL. Update does not prune renamed or
deleted skills. Cleanup is limited to the eight portable names in the current
[Migration Inventory](migration-inventory.md); no portable `multi-run` cleanup
record exists.

## OpenCode Integration

Portable skills do not depend on the npm package, and the npm package does not
install portable skills. Project integration persists in project `node_modules`;
global integration persists in the npm project at `~/.config/opencode`.

The installer requires explicit scope and preview/confirmation. It writes only
selected managed assets after confirmation and never creates or edits
`opencode.json`; the core `plugin` entry remains user-owned. Update is an exact
npm install followed by install preview, exact confirmation, and OpenCode
restart.

Uninstall order is asset preview and confirmation, user-owned plugin-entry
removal, npm uninstall in the owning project, then restart. Reconcile and
uninstall archive exact-owned assets. Conflicts, worktrees, and runtime state are
preserved; no archive restore or purge command is exposed.

## Current Surface

The current inventory covers 29 portable skills, 33 command adapters, 6 fixed
agents, 3 selectable plugin wrappers, 5 package tools, and the core plugin. The
package tool `route` has no slash command.

The catalog descriptions are checked against the current skill contracts:
`goal` returns read-only structured Markdown of at most 4000 characters;
`lsp-report` is host-neutral; task workflows are storage-neutral; and
`code-explain` accepts current WIP, an exact range, a branch, or an exact HTTPS MR
link and presents history without a review verdict.

## Deterministic Coverage

The ordinary quality gate does not invoke a model, provider, or credential:

```shell
task eval:check
task check
```

The committed corpus has English trigger, English near-miss, Russian trigger, and
Russian near-miss scenarios for every active skill. Deterministic checks cover
registration, configuration, installer ownership, archive/reconcile behavior,
agent discovery, negative inputs, path escapes, malformed results, incomplete
budgets, and secret leakage.

Compatibility checks exercise OpenCode `1.18.29` and `1.18.30` inside
`>=1.18.29 <1.19.0` without credentials.

## Live Evaluation and Clean Checkout

Live evaluation is not part of `task check`. It requires explicit trusted-live
mode, host, model, timeout, token and cost budgets, and an output path. No model
or baseline is selected by default, and untrusted CI does not receive
credentials.

Generated runtime copies and distribution outputs are checked for parity. In a
clean temporary checkout, build and check must leave `git status` unchanged:
declared generated copies are tracked and temporary outputs remain ignored.
