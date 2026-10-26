# Proposal

## Why

The renegotiated verification model (see `renegotiate-foundation`,
capability `verification-model`) defines speed 2 — synthetic live runs with
a real model — but the project has no working system for them: the legacy
`eval_runner` was never once run live (`eval:live`: zero runs in history),
and the first ad-hoc attempt during `spec-agents-md` spent an afternoon on
environment plumbing (provider resolution, service ports, auth staging,
permissions) because nothing is pinned and nothing is one command. The owner
decided to build the system properly, modeled on the harness architecture
proven in the `gitlaw` repository.

## What Changes

- A live-run system with a **pinned eval profile**: engine, engine
  profile, and budgets are fixed in a versioned config file — never
  discovered or guessed at run time. The model is not pinned here: it is
  chosen entirely inside the host-side ccr profile.
- **ccr (claude-code-router) is the initial engine**, an external CLI
  dependency: the owner configures a dedicated ccr profile for this
  project's test runs on the host; this repository documents how to install
  ccr and set up the profile (Diataxis how-to).
- The runner talks to engines through a **small adapter** (start, continue,
  parse, cleanup), one subprocess pattern — the same shape proven in
  gitlaw's harness; adding an engine means adding an adapter.
- Isolation follows the gitlaw philosophy, replacing the current
  sandboxed-HOME rule: real HOME (engine auth just works), an isolated empty
  workdir holding only the fixture, a positive environment allowlist so
  credentials cannot ride along, and nothing outside the fixture is
  modified.
- **Scenarios are versioned artifacts**: fixture repository + prompt +
  assertions in the repo; a new scenario is a new directory, not a code
  change. The first scenario is `agents-md-mirror` (fresh mirrors at root
  and a nested scope, copy fallback on symlink failure, a diverged CLAUDE.md
  asking instead of overwriting) — it closes task 2.2 of `spec-agents-md`.
- **One command** runs a scenario end to end: profile, fixture, run,
  assertions, report.
- The AGENTS.md probe rule (isolated HOME/XDG sandboxing) is revised to the
  new isolation contract; the dead `eval:live` machinery is retired, with
  its still-valuable parts absorbed.

## Capabilities

### New Capabilities

- `live-runs`: the synthetic live-run system — pinned eval profile, engine
  adapters, isolation contract, versioned scenarios, one-command runner,
  reporting, and integration with the three-speed verification model.

### Modified Capabilities

None.

## Impact

- New runner tooling under `scripts/` and a `live:run` task.
- New scenario storage (fixtures, prompts, assertions).
- `docs/how-to/`: the ccr setup and profile guide (EN/RU).
- `AGENTS.md`: the agent-host probe rule is rewritten to the new isolation
  contract.
- `evals/` + `eval_runner.py`: legacy live machinery retired; offline
  contract checks that still earn their keep are absorbed.
- `openspec/changes/spec-agents-md/tasks.md`: task 2.2 executes through the
  first scenario.
