# Verification

[Русская версия](ru/verification.md)

## Current Release

The supported portable source is the GitHub Pages stable channel at
`https://kisev.github.io/skills`; the optional package is
`@kisev/skills-opencode`. Portable installation follows
`npx --yes skills@latest`. The package requires Node.js 22+ and declares OpenCode
`>=1.18.29 <1.19.0`.

## Portable Installation

The global contract for both supported hosts is:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

It produces one canonical copy in `~/.agents/skills`. Without `--global`, the
project copy is `.agents/skills`. Release metadata provides source provenance;
the authored repository is not an installation source.

The Pages URL is a moving stable-release channel. `update` verifies the current
well-known digest, downloads changed archives, and offers to remove tracked names
deleted upstream. Existing Git-based installations must repeat `add` with the
Pages URL and the same scope and agents to rebind their source. Explicit cleanup
is limited to the retired names in the current [Migration Inventory](migration-inventory.md).

## OpenCode Integration

Portable skills do not depend on the npm package, and the npm package does not
install portable skills. Project integration persists in project `node_modules`;
global integration persists in the npm project at `~/.config/opencode`.

Scope-aware direct commands default to the current directory and accept one
`--global` flag for global state; `--scope` is unsupported. The installer
requires preview/confirmation. It writes only selected managed assets after confirmation and never creates or edits
`opencode.json`; the core `plugin` entry remains user-owned. Update is an exact
npm install followed by install preview, exact confirmation, and OpenCode
restart.

Uninstall order is asset preview and confirmation, user-owned plugin-entry
removal, `npm uninstall` in the owning project, then restart. Reconcile and
uninstall archive exact-owned package assets. Reconcile ignores portable skill
trees and installer lock files; `skills update/remove` owns that lifecycle.
Conflicts, worktrees, and runtime state are preserved; no archive restore or
purge command is exposed.

## Current Surface

The current inventory covers 27 portable skills, 27 command adapters, 6 fixed
agents, 3 selectable plugin wrappers, 1 package tool, and the core plugin. The
package tool `route` has no slash command.

The catalog descriptions are checked against the current skill contracts:
`goal` returns read-only structured Markdown of at most 4000 characters; task
workflows are storage-neutral; and
`code-explain` accepts current WIP, an exact range, a branch, or an exact HTTPS MR
link and presents history without a review verdict.

## Deterministic Coverage

The ordinary quality gate does not invoke a model, provider, or credential:

```shell
task eval:check
task check
task dependency:audit
```

The committed corpus has English trigger, English near-miss, Russian trigger, and
Russian near-miss scenarios for every active skill. Deterministic checks cover
registration, configuration, installer ownership, archive/reconcile behavior,
agent discovery, negative inputs, path escapes, malformed results, incomplete
budgets, and secret leakage.

For `spec-manage`, coverage has one primary deterministic owner per area. Hostless
eval validates corpus contracts but does not observe model behavior:

| Area | Deterministic owner | Hostless eval contract | Trusted-live behavior |
| - | - | - | - |
| Language, authority, extensions | `tests/test_spec_manage_contract.py` | bilingual case inventory and digests | language-before-write, preservation, conflicts, accepted/rejected extensions |
| Snapshot and lifecycle validator | `tests/test_spec_validate.py` | runner and invariant safety only | not required |
| Requirements, architecture, ADR, locale parity | `tests/test_spec_manage_model.py` | not required | not required |
| Mode selection, ambiguity, near-misses, content states | `tests/test_spec_manage_evals.py` | bilingual case protocol | per-case mode/stop outcome and observed no-write boundary |
| Audit classification, severity, critic, aggregate | `tests/test_spec_manage_evals.py` | bilingual case protocol | per-case audit outcome and observed no-write boundary |

`tests/test_evals.py` owns the generic eval protocol and its negative cases.
Stage 20 `spec-manage` scenarios prove routing declarations only. Legacy scenarios
without `expected.case_outcomes` remain selection-only and do not prove mode or
audit outcomes. Offline results use `observation_mode: hostless-contract`; only
trusted-live results use `observation_mode: trusted-live` and may satisfy case
outcome assertions.

Compatibility checks exercise OpenCode `1.18.29` and `1.18.31` inside
`>=1.18.29 <1.19.0` without credentials.

## Live Evaluation and Clean Checkout

Live evaluation is not part of `task check`. It requires explicit trusted-live
mode, host, model, timeout, token and cost budgets, and an output path. No model
or baseline is selected by default, and untrusted CI does not receive
credentials.

Scenarios with `expected.case_outcomes` require one observed result for every
case. Missing, extra, malformed, or incorrect outcomes fail the evaluation.
Read-only boundaries are checked from the project sandbox diff; `specs-only`
scenarios fail when a changed path is outside sandbox `specs/`. Live output is
private run evidence and is not committed.

Shared runtime copies exist only in ignored build outputs and are checked for
parity. In a clean temporary checkout, build and check must leave `git status`
unchanged. Distribution tests serve the complete Pages layout from a local HTTP
fixture, install it through stable `skills@latest`, remove the fixture, and then
run the installed runners. Release CI additionally checks the tag, version,
source revision, every deployed Pages byte, the exact npm tarball, package
imports and CLI, registry signatures, SLSA provenance, and cross-channel digests
before creating the GitHub Release.
