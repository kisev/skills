# Tasks

## 1. Core runner

- [x] 1.1 Create `scripts/live_runner.py`: profile loading, fixture staging
  (copy into an isolated empty workdir), engine subprocess with the
  positive env allowlist, before/after snapshots, budgets (timeout), report
  with verdict and redacted transcript under `.build/` — verification: a
  dry preflight mode runs without a model and reports profile status
- [x] 1.2 Add the pinned profile file (engine `ccr`, engine profile
  `skills-tests-claude`, budgets) with no secrets and no model inside —
  the model is chosen in the host-side ccr profile — verification: the
  runner names the engine and engine profile from the file in every report
- [x] 1.3 Implement the ccr engine adapter (start, parse) over one
  subprocess pattern — verification: adapter unit tests with a fake runner
  pass

## 2. ccr setup documentation

- [x] 2.1 Write `docs/how-to/live-runs-ccr.md` (EN) and the RU mirror:
  installing ccr, creating the dedicated test profile, running the
  preflight — verification: `locale:check` passes; a reader can bring a
  fresh host to a green preflight

## 3. First scenario

- [x] 3.1 Define the scenario format (fixture/, prompt.txt,
  assertions.json) and implement declarative assertion evaluation (file
  exists, symlink target, content equals sibling, hash unchanged, output
  mentions) — verification: unit tests over a staged fixture pass
- [x] 3.2 Add the `agents-md-mirror` scenario with the proven fixture (root
  project, nested go-tool, ts-widget with a diverged CLAUDE.md) and the
  fault-injected `ln` variant for the copy fallback — verification: the
  scenario validates against the format
- [x] 3.3 Execute the scenario through `task live:run` against the owner's
  ccr profile: fresh mirrors at root and nested scope, copy fallback, and
  the diverged CLAUDE.md asking instead of overwriting — verification: the
  report shows all three behaviors; this closes task 2.2 of
  `spec-agents-md`

## 4. Wiring and cleanup

- [x] 4.1 Add the `live:run` task wrapping the runner — verification: one
  command produces a verdict from a fresh checkout with the profile
  configured
- [x] 4.2 Revise the AGENTS.md agent-host probe rule to the new isolation
  contract (real HOME, isolated workdir, env allowlist, ccr profile) —
  verification: the rule describes the live-runs system and no longer
  mandates sandboxed HOME/XDG
- [x] 4.3 Retire the legacy live lane: `eval:live` task, `evals-live.yml`
  workflow, and the `--trusted-live` host execution inside `eval_runner.py`
  (the offline corpus and the library functions the acceptance harnesses
  load stay; corpus case contracts become declared-but-unobserved forward
  declarations) — verification: no dead eval tasks remain in the task
  graph; the offline suite, gates, and locale checks stay green

## Workflow follow-up

- Before archiving: run the scenario sweep (`live:run --all`); with one
  scenario this equals 3.3.
- Archiving this change creates the `live-runs` capability spec.
