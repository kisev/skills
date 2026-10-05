# ADR-0018: Unify the gate registry and trust one terminal CI success

- Status: accepted
- Date: 2026-10-04
- Supersedes: none

## Context

"Which gate checks what" lived in three independently maintained copies: the
task graph (`check:core`, `check`, `pre-push`) in `taskfile.yml`, the manual
glob lists of the Lefthook `pre-push` jobs, and the hand-written CI matrix in
`.github/workflows/ci.yml`. The copies drifted: `dependency:audit` and
`docs:check` never ran in CI although CI claimed to repeat the complete gate,
`site:test` ran in no gate at all, and a hand-maintained glob list produced a
false push rejection of the class fixed by the pinned distribution check.
Duplication also caused redundant execution: a full `task check` ran two npm
suites twice, the release path rebuilt the distribution two or three times
across separate `task` processes where `run: once` cannot deduplicate, and the
dev publication repeated the complete gate that CI had just executed for the
same revision. Trusting "a CI run exists" is unsafe because `cancel-in-progress`
lets a newer push cancel the run of the revision being published, while a tag
push triggers no CI run at all and must keep its own full check.

## Decision

Adopt one machine-readable gate registry (`gate-registry.json`) as the single
source that maps every gate layer to its input paths and gate task. The
registry encodes the `build:skills` precondition — tasks consuming materialized
skills render into the CI group whose handwritten skeleton builds first — and
the meta-triggers (`gate-registry.json`, `lefthook.yml`, `mise.toml`,
`taskfile.yml`) carried by every scoped pre-push layer.
`scripts/generate_gates.py` renders only the marked CI `matrix.include` blocks
and pre-push glob lists; branch policy, job skeletons, aggregation, drift-gate
step, and task calls stay hand-written. `task gates:check` runs inside
`check:core` and a dedicated CI job, so any divergence between the registry and
a rendered copy, in either direction, fails the gate.

`dependency:audit` and `docs:check` joined the registry core and therefore run
in CI; `site:test` joined the mandatory gate. `package:check` delegates the npm
suites to `package:test` exactly once. Release verification collapsed into
single-invocation internal tasks (`release:verify`, `release:verify:published`)
that share the gate's distribution build while preserving `--published` and
`--require-clean`. The dev publication trusts only the terminal `success`
conclusion of CI runs for the exact revision (`actions: read` plus
`scripts/await_ci_success.py`) and refuses to publish on cancelled, failed, or
missing runs; `release:prepare` keeps exactly one full check on the tagged
commit, which remains the tag's only automatic gate.

## Alternatives

Widening the CI matrix by hand keeps three copies and gives parity no
executable definition, and was rejected. Generating whole workflows from the
registry lets the generator approve its own output and removes hand review
from branch policy and aggregation, and was rejected. Trusting the existence of
a CI run publishes revisions whose run failed or was cancelled, and was
rejected. Keeping `dependency:audit` as a fourth, hook-only always-on job was
rejected in favor of folding it into the registry core.

## Migration and Tradeoffs

The registry must land together with its rendered copies and the drift gate in
one change; a registry edit without regeneration fails `gates:check`. CI runs
more matrix entries (documentation, docs site build and contracts, dependency
audit), trading runner minutes for literal gate parity. The dev publication
serializes behind CI, so dev snapshots publish later than before. Published
artifacts keep their contracts, and the workflow gains `actions: read` for run
lookup only. Rollback reverts the commits; the registry is one file with no
external state, and the previous task graph, hooks, and workflows are
recoverable from Git history.

## Verification

See [REQ-F-004](../../requirements/functional/README.md#req-f-004---publish-one-verified-release)
and [REQ-F-009](../../requirements/functional/README.md#req-f-009---publish-an-isolated-development-channel).
Tooling contract tests assert that the rendered copies match the registry, that
every layer stays composed into the task graph, CI, and pre-push, and that
every scoped glob carries the meta triggers.
