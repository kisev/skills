# Gate Benchmarks

Measured timings for the verification harness layers and the composite
`task check` gate. The `gates:bench` task appends one dated section per run
(hyperfine, raw JSON export in the untracked `.build/gates-bench.json`); this
file is human-curated, so recorded sections are history and later annotations
never rewrite them. The benchmark is not wired into any hook, CI matrix, or
push gate: it is a measurement instrument, not a gate.

## How to Measure

```shell
task gates:bench
task gates:bench -N 'python:test' -n 'python:test' -- 'task python:test'
```

The default sweep measures the materialization precondition, every registered
layer, and the composite check with three hyperfine runs each; a full sweep
takes roughly half an hour. Extra arguments pass through, so a single layer
can be re-measured with `--runs 5`. Timings are wall-time seconds on the
machine that recorded them (see the recorded date and revision below); they
are not reproducible across hosts and stay a local calibration baseline.

## 2026-10-13 — owner measurement (pre-rework, 034852f)

First recorded by the owner before this file existed: the composite
`task check` took about 2.8 minutes (84% of it inside `python:test` and
`package:check` at the time) on 2026-10-13, and the full Lefthook `pre-push`
gate measured 296.76 s.

## 2026-10-14 — 034852f — pre-rework layers — 3 runs per layer

The first full `gates:bench` sweep before the verification-harness rework.
The composite `check` run was interrupted by the owner after the twenty-one
layer commands, so the composite row comes from the owner measurement above.
Names are pre-rename artifact identifiers recorded with the run.

| Command | Mean (s) | Stddev (s) | Min (s) | Max (s) |
| - | - | - | - | - |
| `build:skills (precondition)` | 0.49 | 0.15 | 0.40 | 0.66 |
| `version:check` | 0.23 | 0.01 | 0.22 | 0.24 |
| `gates:check` | 1.99 | 0.27 | 1.82 | 2.30 |
| `lint:skills` | 2.96 | 0.23 | 2.79 | 3.22 |
| `lint` | 3.55 | 0.33 | 3.17 | 3.75 |
| `typecheck` | 5.83 | 0.61 | 5.45 | 6.53 |
| `security` | 2.41 | 0.37 | 2.14 | 2.83 |
| `docs:check` | 0.57 | 0.16 | 0.39 | 0.68 |
| `site:build` | 4.38 | 0.57 | 3.98 | 5.04 |
| `site:test` | 2.65 | 0.17 | 2.51 | 2.84 |
| `dependency:audit` | 4.05 | 2.13 | 2.42 | 6.46 |
| `distribution:build` | 1.19 | 0.03 | 1.17 | 1.22 |
| `locale:check` | 1.16 | 0.14 | 1.00 | 1.29 |
| `skills:validate` | 7.91 | 0.25 | 7.64 | 8.13 |
| `eval:check` | 0.60 | 0.04 | 0.56 | 0.63 |
| `test:python` | 72.41 | 1.08 | 71.61 | 73.63 |
| `package:check` | 46.13 | 3.18 | 42.94 | 49.30 |
| `package:consumer-smoke` | 13.22 | 3.99 | 10.48 | 17.80 |
| `reviewmatic:check` | 248.30 | 3.68 | 244.23 | 251.37 |
| `reviewmatic:install-smoke` | 6.63 | 2.27 | 4.80 | 9.18 |
| `shopmatic:check` | 7.50 | 0.37 | 7.22 | 7.92 |

## 2026-10-14 — 034852f + verification-harness rework worktree — 3 runs per layer

Recorded after the full rename series, the `package:build` run-once dedup,
and the targeted pre-commit extension, on the uncommitted rework worktree of
revision `034852f` (the owner commits the series; live CI verification is
deferred to the next push). The composite ran green three times with full
output; the interrupted first sweep from 2026-10-14 did not reproduce at the
composite in these three runs.

Owner verdict 2026-10-14: all 20 registered layers stay; no layer is removed
and no optimization is taken in this series. The next series (after this
rework lands) is free to revisit the slow layers, dominated today by
`reviewmatic:check` at about 60% of the composite.

| Command | Mean (s) | Stddev (s) | Min (s) | Max (s) |
| - | - | - | - | - |
| `skills:build` | 0.41 | 0.02 | 0.40 | 0.43 |
| `version:check` | 0.23 | 0.01 | 0.22 | 0.23 |
| `gates:check` | 2.02 | 0.18 | 1.83 | 2.19 |
| `skills:lint` | 2.60 | 0.46 | 2.31 | 3.13 |
| `lint` | 4.11 | 0.27 | 3.94 | 4.42 |
| `typecheck` | 7.75 | 0.71 | 7.10 | 8.51 |
| `secrets:scan` | 2.58 | 0.04 | 2.53 | 2.61 |
| `docs:check` | 0.53 | 0.05 | 0.49 | 0.59 |
| `site:build` | 4.65 | 0.22 | 4.45 | 4.89 |
| `site:test` | 2.80 | 0.13 | 2.65 | 2.89 |
| `dependency:audit` | 2.66 | 0.12 | 2.57 | 2.80 |
| `distribution:build` | 1.24 | 0.10 | 1.16 | 1.34 |
| `locale:check` | 1.32 | 0.02 | 1.30 | 1.34 |
| `skills:check` | 6.50 | 0.61 | 6.10 | 7.20 |
| `eval:check` | 0.43 | 0.03 | 0.41 | 0.46 |
| `python:test` | 73.78 | 4.03 | 69.86 | 77.90 |
| `package:check` | 45.49 | 2.85 | 42.30 | 47.79 |
| `package:smoke` | 13.19 | 4.51 | 10.26 | 18.39 |
| `reviewmatic:check` | 260.80 | 13.96 | 245.45 | 272.74 |
| `reviewmatic:smoke` | 5.25 | 0.68 | 4.50 | 5.85 |
| `shopmatic:check` | 7.67 | 0.29 | 7.34 | 7.87 |
| `check` | 432.61 | 5.94 | 426.87 | 438.72 |

Raw hyperfine export: `.build/gates-bench.json` (untracked).

## 2026-10-14 — 32d3f2e — parallel/xdist/upgrade step

Intermediate measurements of the push-latency step on the worktree of
`32d3f2e`: the pre-push jobs now run in parallel, `reviewmatic:check` runs
its suite under `pytest-xdist -n auto --dist loadgroup`, and every
`pyproject.toml` pin moved to the latest `== major.minor.*` wildcard
(mypy 2.4, pytest 9.1, ruff 0.17). The composite runs sequentially inside
`task check`; the parallel pre-push wall is bounded by the slowest job.

| Command | Mean (s) | Stddev (s) | Min (s) | Max (s) |
| - | - | - | - | - |
| `reviewmatic:check` | 29.18 | 2.48 | 25.38 | 34.56 |
| `check` | 208.66 | 0.00 | 208.66 | 208.66 |

Raw hyperfine export: `.build/gates-bench.json` (untracked).
