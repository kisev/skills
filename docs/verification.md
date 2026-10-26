# Verification

[Русская версия](ru/verification.md)

## Current Release

The supported portable source is the GitHub Pages stable channel at
`https://kisev.github.io/skills`. Portable installation follows `uvx skillmate`
or `npx --yes skills@latest`.

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
Pages URL and the same scope to rebind their source. The upstream index
decides which names count as retired; `update` offers exactly those for
removal.

## Reviewmatic Python Application

`apps/reviewmatic` is the only reviewmatic runtime. It handles GitLab MRs,
local WIP, panel/arbitration, incremental review, repair, refresh, private XDG
state, managed worktrees, and direct manual runbooks. Run it ephemerally from a
selected Git ref with `uvx`; there is no npm or PyPI runtime and no TUI. See the
[application guide](../apps/reviewmatic/README.md) for stable/dev ref selection,
cache refresh, and runbook recovery.

The portable contract core under `src/reviewmatic/portable/` is materialized
byte-for-byte from `shared/references/` through `shared/manifest.json`
(`pythonRuntime`). The 33 golden cases retain expectations generated from
TypeScript revision `3e409c217e94d643f77eb543caab9a2ed4b7288d`; the old
implementation and generator are removed. Python tests recompute and assert
every expected digest, verdict, and state transition without regenerating
expectations from Python. The historical TypeScript baseline and mapping are in
the [test matrix](reviewmatic-test-matrix.md).

```shell
task generate:check
task reviewmatic:check
task reviewmatic:smoke
```

`generate:check` checks materialized shared sources and retained golden
assertions. The application gate runs pytest, mypy, the lock check, and builds
the wheel and source distribution. The separate install smoke exercises a
local Git ref and both built distributions outside the checkout, without Node,
`PYTHONPATH`, or an installed `reviewmatic` tool. The smoke is a scoped gate
layer: CI and the pre-push hook run it when the delta touches
`apps/reviewmatic/**`, and `task check` includes it.

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

## skillmate

The skillmate application in `apps/skillmate` is a standard-library-only
Python 3.12+ installer-configurator, delivered on PyPI. Its gate is fully
offline: committed fixtures back the distribution index and archive parsing,
so no test or gate talks to the network:

```shell
task skillmate:check
```

The gate runs `uv lock --check`, the offline test suite, application-local
strict mypy and ruff, the uv build, and the CLI version contract. The
application layer is registered in `gate-registry.json`, so scoped CI matrix
entries and pre-push globs cover the `apps/skillmate` delta.

## Deterministic Coverage

The secret gate scans Git history plus the current tracked and non-ignored new
files. Ignored runtime state, such as the persistent local Mattermost credentials
and publication ledgers, is not source material. A force-added ignored file is
tracked and remains in the worktree scan. The snapshot preserves symlink bytes
without following links outside the checkout.

The ordinary quality gate does not invoke a model, provider, or credential; the
dependency audit and the docs-site contracts are part of it and of the CI
matrix. The chain starts with a seconds-scale source-only canon preselect
(`task skills:lint`), so a Cyrillic edit in an English canonical text fails
before builds and heavy tests:

```shell
task skills:lint
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

| Area | Deterministic owner | Hostless eval contract | Declared live cases |
| - | - | - | - |
| Language, authority, extensions | `tests/test_spec_manage_contract.py` | bilingual case inventory and digests | language-before-write, preservation, conflicts, accepted/rejected extensions |
| Snapshot and lifecycle validator | `tests/test_spec_validate.py` | runner and invariant safety only | not required |
| Requirements, architecture, ADR, locale parity | `tests/test_spec_manage_model.py` | not required | not required |
| Mode selection, ambiguity, near-misses, content states | `tests/test_spec_manage_evals.py` | bilingual case protocol | per-case mode/stop outcome and observed no-write boundary |
| Audit classification, severity, critic, aggregate | `tests/test_spec_manage_evals.py` | bilingual case protocol | per-case audit outcome and observed no-write boundary |

`tests/test_evals.py` owns the generic eval protocol and its negative cases.
Stage 20 `spec-manage` scenarios prove routing declarations only. Legacy scenarios
without `expected.case_outcomes` remain selection-only and do not prove mode or
audit outcomes. Offline results always use `observation_mode: hostless-contract`;
the corpus case contracts are declared forward declarations — this runner reports
the case layer as `not_observed`, and real-model observation belongs to the
live-runs system.

The catalog descriptions are checked against the current skill contracts:
`goal` returns read-only structured Markdown of at most 4000 characters; task
workflows are storage-neutral; and
`code-explain` accepts current WIP, an exact range, a branch, or an exact HTTPS MR
link and presents history without a review verdict.

## Missed-defect Registry

The testing audit found two defect classes that reached `dev` past every
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

### `prior_decisions` outside the context version, fix `204714f` — closed by PORT-3

Symptom: a significant agreed-decision change kept the question context
version, so a late answer collected under the withdrawn exception could still
finalize the review as ready; documented recovery also removed fresh results
of other critics that only shared the superseded question ID.

Why the gates missed it: undocumented layer. The meaningful-context inputs
were enumerated only in the digest function body; `prior_decisions` was absent
from that list and from the guide, READMEs, and spec, so no contract test
looked at decision churn.

Guard: `_shared_context_inputs` feeds `prior_decisions` into both
`question_context_digest` and `question_context_version`; retirement filters
each answer and verification by its own binding (`is_current_result`), not
only by question ID, and moves only stale entries to history.

Red-capable Python coverage:
`apps/reviewmatic/tests/test_context_package.py::test_prior_decisions_change_both_package_and_question_context_bindings`
fails if `prior_decisions` is removed from either binding.
`apps/reviewmatic/tests/test_context_package_records.py` proves that a changed
decision blocks late V1 answers, preserves authorship and
original bindings in history, keeps a fresh V2 answer and primary verification
from another critic, and makes repeated recovery idempotent.
`apps/reviewmatic/tests/test_local_review_scenarios.py` proves the same
stale-answer rejection and mixed-version preservation.
Proof by removal: temporarily omit `prior_decisions` from `_shared_context_inputs`;
the direct binding test must fail.

Status: closed by PORT-3. These invariants remain covered:

- `prior_decisions` participates in `question_context_digest` and
  `question_context_version`;
- an agreed-decision change invalidates late answers bound to the earlier
  version, so they cannot finalize the review as ready;
- retirement keeps fresh results of other critics, moves only stale entries to
  history with authorship and original bindings, keeps the question ID list as
  diagnostics, and stays idempotent under repeated recovery.

### Not modeled offline

One aspect stays unmodeled offline on purpose, with the risk owned by the
repository owner:

- the exact wire behavior of range-ignoring GitLab versions (header and
  chunking variety) is modeled only synthetically; live behavior belongs to
  the manual GitLab integration stand, not to a gate.

Weakening the covering tests to pass on unmodeled behavior is not allowed;
new knowledge about these aspects lands as new guards with their own
prove-by-removing evidence.

## Real-Model Runs and Clean Checkout

Real-model evaluation is not part of `task check`. It lives in the live-runs
system: `task live:run` (`scripts/live_runner.py`) executes one versioned
scenario through the pinned engine profile, stages the fixture into an isolated
empty workdir, runs the engine subprocess under a positive environment
allowlist, and writes a verdict with a redacted transcript under `.build/`
(setup in `docs/how-to/live-runs-ccr.md`). Corpus case contracts
(`expected.case_outcomes`) are forward declarations for future live scenarios;
the offline runner reports them as `not_observed`.

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
