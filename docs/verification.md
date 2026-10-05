# Verification

[Русская версия](ru/verification.md)

## Current Release

The supported portable source is the GitHub Pages stable channel at
`https://kisev.github.io/skills`; the optional package is
`@kisev/agentomatic`. Portable installation follows
`npx --yes skills@latest`. The package requires Node.js 22.13+ and declares OpenCode
`>=2.0.0 <2.1.0`.

## Portable Installation

The global installation contract is:

```shell
# Registry version of the installer
npm view --prefer-online skills@latest version

# Install skills
npx --yes skills@latest add https://kisev.github.io/skills --skill '*' --global --yes

# Installed skills
npx --yes skills@latest list --global
```

The npm tag can move between commands. npx does not install a global CLI;
the list command inspects local skills, not the npm or Pages release version.

It produces one canonical copy in `~/.agents/skills` for every host that reads
`.agents/skills`, plus any other installed host. Without `--global`, the
project copy is `.agents/skills`. Release metadata provides source provenance;
the authored repository is not an installation source.

The Pages URL is a moving stable-release channel. `update` verifies the current
well-known digest, downloads changed archives, and offers to remove tracked names
deleted upstream. Existing Git-based installations must repeat `add` with the
Pages URL and the same scope to rebind their source. Explicit cleanup
is limited to the retired names in the current [Migration Inventory](migration-inventory.md).

## OpenCode Integration

Portable skills do not depend on the npm package, and the npm package does not
install portable skills. Project integration persists in project `node_modules`;
global integration persists in the npm project at `~/.config/opencode`.

Scope-aware direct commands default to the current directory and accept one
`--global` flag for global state; `--scope` is unsupported. The installer
requires preview/confirmation. It writes only selected managed assets after
confirmation and stages optional models/critics. It can connect or disconnect
the core plugin and apply presets. `configure integration`
command is the confirmed path for user configuration: it merges selected
fragments into `opencode.json(c)` with native V2 `plugins`/`permissions` and
global `cli.json`, plus `kilo.json(c)` and `mimocode.json(c)` for those hosts,
behind a preview/confirmation receipt, preserving comments, unrelated entries,
and user rule order, migrating only the touched legacy sections and reporting
ambiguities as conflicts; Kilo/MiMo widen scalar permission maps while keeping
the scalar as the `"*"` entry. Update is
an exact npm install followed by install preview, exact confirmation, and
OpenCode restart.

Uninstall previews owned assets, plugin disconnection, retained models, and
opt-in npm removal; completed local stages remain if npm fails. Cleanup and
uninstall archive exact-owned package assets. Reconcile ignores portable skill
trees and installer lock files; `skills update/remove` owns that lifecycle.
Conflicts, worktrees, and runtime state are preserved; no archive restore or
purge command is exposed.

## Current Surface

The current inventory covers 44 portable skills, 41 command adapters, the
`rtk-stats` package command, 6 fixed agents, 4 selectable plugin wrappers,
1 package tool, and the core plugin. The
package tool `route` has no slash command.

The catalog descriptions are checked against the current skill contracts:
`goal` returns read-only structured Markdown of at most 4000 characters; task
workflows are storage-neutral; and
`code-explain` accepts current WIP, an exact range, a branch, or an exact HTTPS MR
link and presents history without a review verdict.

## Python Port Packages

The Python port of the reviewmatic family starts in `apps/reviewmatic-py`.
Stage 1 ships the package skeleton and the complete command surface of the
TypeScript CLI with the same exit-code contract; subcommands whose business
logic has not landed answer an explicit not-implemented envelope with exit
code 5. The canonical contract core is materialized byte-for-byte from
`shared/references/` through the `pythonRuntime` section of
`shared/manifest.json`; the copies in the package are not edited by hand.

Digest parity with the TypeScript implementation is pinned by committed
golden fixtures under `apps/reviewmatic-py/tests/golden/`. They cover
canonical digests, v2 artifact validation, and semver and label assessments.
The declared TypeScript task regenerates them from the real CLI sources, and
the generation is byte-checked:

```shell
task reviewmatic-py:fixtures
task generate:check
```

The same `generate:check` run byte-checks the materialized contract core
through `scripts/materialize_cli_runtime.mjs --check`. The package gate runs
the parity tests, application-local mypy, and the uv build of the sdist and
wheel:

```shell
task reviewmatic-py:check
```

## shopmatic

The shopmatic application in `apps/shopmatic` is an MCP stdio server for
marketplace shopping research through the pinned `agent-browser` CLI
([ADR-0020](../specs/architecture/09-architecture-decisions/0020-drive-marketplace-storefronts-through-agent-browser.md)).
Its automated gate is fully offline: a scripted fake `agent-browser`
executable backs the browser driver, so no test or gate talks to a
marketplace:

```shell
task shopmatic:check
```

The gate runs `uv lock --check`, the offline test suite, application-local
strict mypy and ruff, the uv build, and the CLI version contract. The
application layer is registered in `gate-registry.json`, so scoped CI matrix
entries and pre-push globs cover the `apps/shopmatic` delta.

Live storefront verification is a manual runbook, not a gate, because it
depends on external sites and network reputation. It follows the acceptance
evidence recorded on 2026-10-05: anonymous runs on Wildberries and Yandex
Market must open a search with a price cap, wait for the SPA render, and
print structured results (name, price, URL, rating) from a profile that was
proven cookie-empty before the first navigation; Ozon is expected to answer
its antibot challenge and stay blocked. Re-run the same scenario by hand:

```shell
uv run --locked shopmatic search wildberries "клавиатура" --max-price 5000 --limit 5
uv run --locked shopmatic search yandex-market "клавиатура" --max-price 5000 --limit 5
uv run --locked shopmatic compare "клавиатура" --limit 3
```

Marketplace selectors decay with storefront redesigns; a failing adapter
answers an explicit error, and the spike stop conditions in the ADR govern
whether support is paused, not bypassed.

## Consumer Smoke

The npm gates verify that the packages build and pack, but only a real consumer
proves that a published tarball installs and typechecks. The consumer smoke
gate derives the publishable set programmatically from the root `package.json`
workspaces with `private != true`, packs it after `package:build`, and installs
the fresh tarballs into one throwaway consumer project: the dependency-free
foundation package first, then every dependent in a single install, so they
typecheck against the tested copy instead of a healthy registry duplicate. The
generated `consumer.ts` imports every declared typed entry of each package and
must pass strict `tsc --noEmit` with `nodenext` resolution; a generated module
import also proves each package loads under Node. npm does not install optional
peer dependencies, so `@opencode/plugin` and `@types/node` are installed
explicitly at their pinned versions, following the registry smoke precedent.
The npm cache persists under `.build/`, so a warm run takes seconds; the first
run pays the registry download cost.

```shell
task package:consumer-smoke
```

A broken tarball fails the gate even while the same version stays healthy in
the public registry, which is the "broken package shipped" class that only a
live consumer catches. The gate layer is registered in `gate-registry.json`,
so the CI matrix and the scoped pre-push job run it when the npm surface
changes.

## Deterministic Coverage

The secret gate scans Git history plus the current tracked and non-ignored new
files. Ignored runtime state, such as the persistent local Mattermost credentials
and publication ledgers, is not source material. A force-added ignored file is
tracked and remains in the worktree scan. The snapshot preserves symlink bytes
without following links outside the checkout.

The ordinary quality gate does not invoke a model, provider, or credential; the
dependency audit and the docs-site contracts are part of it and of the CI
matrix:

```shell
task eval:check
task check
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

Compatibility checks exercise OpenCode `2.0.19` inside
`>=2.0.0 <2.1.0` without credentials: installed-tarball package smoke, native
server permission evaluation, and the memomatic V2 HTTP and read-only database
contract.

## Missed-defect Registry

The testing audit found three defect classes that reached `dev` past every
gate. Each fix landed with tests, but nothing proved those tests fail on the
pre-fix behavior, and the decisions not to model some conditions stayed
implicit. This registry makes both explicit: every class records the symptom,
why the gates missed it, the guard that now owns it, the covering tests, and
the proof status. Prove-by-removing means that in a disposable copy of the
checkout the guard part of the fix was removed, the focused test failed with
the expected pre-fix cause, the guard was restored, and the test passed again.

### GitLab instances that ignore Range requests, fix `b5cf464` — covered

Symptom: a failed CI job whose trace exceeded the 64 KiB streaming cap raised
a fatal collection error and blocked the whole review at the prepared stage on
instances that answer `Range` requests with the full trace.

Why the gates missed it: environment divergence. Offline fixtures and mocked
`glab` responses modeled only instances that honor `Range`; the full-trace
response of range-ignoring instances exists only on real installs, which no
offline gate talks to.

Guard: `streamed_glab_trace` keeps the last bounded tail and marks the stream
as tail-dropped; `parse_glab_trace` and `glab_text` propagate it as
`complete=false`; `collect_pipeline_jobs` records the truncated tail as
per-job trace evidence while metadata, depth, and trace-count protection stay
fatal.

Covering tests in `tests/test_application_workflows.py`:

- `test_gitlab_trace_streaming_enforces_limit_and_cleans_up_timeout` — an
  oversized response yields a bounded `complete=false` excerpt through
  `glab_text` instead of a fatal error;
- `test_gitlab_trace_streaming_keeps_the_last_bounded_tail_bytes` — the kept
  excerpt is the last bounded tail, not the head;
- `test_gitlab_trace_completeness_requires_confirmed_full_range` — the
  tail-dropped flag propagates to `complete=false` and a truncated tail stays
  non-fatal evidence in `collect_pipeline_jobs`;
- `test_collect_pipeline_jobs_marks_trace_limit_overflow_truncated_without_fatal_error`
  — the trace-count limit marks evidence truncated without a fatal pipeline
  error;
- `test_gitlab_trace_streaming_preserves_other_separator_in_body` and
  `test_gitlab_trace_streaming_accepts_exact_header_body_and_crlf_limits` —
  healthy responses are not marked truncated.

Proof on 2026-10-05: removing the tail-retention branch failed
`test_gitlab_trace_streaming_enforces_limit_and_cleans_up_timeout` and
`test_gitlab_trace_streaming_keeps_the_last_bounded_tail_bytes` with
`WorkflowError: GitLab job trace exceeds the response size limit`; restoring
the branch turned both tests green. Restoring the fatal trace-limit error
failed
`test_collect_pipeline_jobs_marks_trace_limit_overflow_truncated_without_fatal_error`
on the pipeline completeness assertion; removing it again turned the test
green.

### Unavailable model catalog in the wizard, fix `184327d` — covered

Symptom: `install` aborted agent model setup with a fatal
`catalog_unavailable` error whenever the OpenCode V2 model catalog could not
be read, instead of accepting an explicitly typed provider/model.

Why the gates missed it: unmodelable unavailability. TTY wizard tests drove
only the healthy-catalog path backed by a working OpenCode runtime, and no
offline harness simulated a failing runtime until the fix introduced a fake
`opencode` executable that exits non-zero.

Guard: `modelSelection` catches `catalog_unavailable`, warns on stderr, and
prompts for an explicit model and an optional variant instead of failing.

Covering tests in `packages/agentomatic/test/command-cli.test.mjs`:

- `TTY install falls back to an explicit model entry when the catalog is unavailable` —
  with a failing `opencode` executable the wizard completes and applies the
  explicitly typed model;
- `TTY install stages a critic model from the catalog and applies it with one confirmation` —
  the healthy catalog path keeps its catalog pick flow.

Proof on 2026-10-05: rethrowing `catalog_unavailable` from `modelSelection`
aborted the wizard with `Error [catalog_unavailable]` before the
explicit-model prompt and failed the fallback test; restoring the catch turned
the test green.

### `prior_decisions` outside the context version, fix `204714f` — deferred to PORT-2

Symptom: a significant agreed-decision change kept the question context
version, so a late answer collected under the withdrawn exception could still
finalize the review as ready; documented recovery also removed fresh results
of other critics that only shared the superseded question ID.

Why the gates missed it: undocumented layer. The meaningful-context inputs
were enumerated only in the digest function body; `prior_decisions` was absent
from that list and from the guide, READMEs, and spec, so no contract test
looked at decision churn.

Guard: `sharedContextInputs` feeds `prior_decisions` into both
`questionContextDigest` and `questionContextVersion`; retirement filters every
collected answer and verification by its own context binding
(`isCurrentResult`) instead of the question ID and moves only stale entries to
history.

Covering tests shipped with the fix:
`apps/reviewmatic/test/context-package.test.mjs` proves that a significant
prior-decision change supersedes answers for the same question and that
mixed-version recovery keeps fresh results while retiring only the stale
entry; `apps/reviewmatic/test/local-review.test.mjs` proves the same pair for
the local review flow.

Status: deferred. These files are being ported by PORT-2, so new tests here
would collide with that port; the obligation to prove the covering tests
red-capable moves to PORT-2. The invariants PORT-2 must keep covered:

- `prior_decisions` participates in `questionContextDigest` and
  `questionContextVersion`;
- an agreed-decision change invalidates late answers bound to the earlier
  version, so they cannot finalize the review as ready;
- retirement keeps fresh results of other critics, moves only stale entries to
  history with authorship and original bindings, keeps the question ID list as
  diagnostics, and stays idempotent under repeated recovery.

### Not modeled offline

Two aspects stay unmodeled offline on purpose, with the risk owned by the
repository owner:

- the exact wire behavior of range-ignoring GitLab versions (header and
  chunking variety) is modeled only synthetically; live behavior belongs to
  the manual GitLab integration stand, not to a gate;
- the real OpenCode V2 catalog and terminal rendering inside the wizard are
  modeled by a fake executable and a forced TTY, so real runtime and terminal
  diversity stay outside the gates.

Weakening the covering tests to pass on unmodeled behavior is not allowed;
new knowledge about these aspects lands as new guards with their own
prove-by-removing evidence.

## Live Evaluation and Clean Checkout

Live evaluation is not part of `task check`. It requires explicit trusted-live
mode, host, model, timeout, token and cost budgets, and an output path. No model
or baseline is selected by default, and untrusted CI does not receive
credentials.

Scenarios with `expected.case_outcomes` require one observed result for every
case. Missing, extra, malformed, or incorrect outcomes fail the evaluation.
Fixture cases that declare a `verify` contract, such as the `humanize`
edit-contract pair, additionally require the returned `outcome` to carry the
complete edited text: the harness checks that rewrite itself for byte-identical
protected fragments, absence of forbidden punctuation outside preserved exact
quotations, surviving declared claims, and absent declared inventions. A
missing or defective rewrite fails those assertions even when the host reports
success. Read-only boundaries are checked from the project sandbox diff; `specs-only`
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

Development publication tests additionally check deterministic snapshot version
derivation, `dev` source provenance, Pages root and `/dev` composition, and the
required npm `dev` dist-tag. CI rejects pull requests into `main` from branches
outside `dev`, `release/*`, and `fix/*` and rejects non-merge pushes to `main`;
repository branch protection remains an external setting.
