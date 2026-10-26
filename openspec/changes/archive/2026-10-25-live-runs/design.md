# Design

## Context

The first ad-hoc live run (`spec-agents-md` task 2.2) failed on environment
plumbing: sandboxed HOME hid every working provider; the managed opencode
service port collided with the owner's running instance; the only resolvable
WSL provider was an unreachable corporate gateway; the local ccr router
required a client key. The `gitlaw` repository already solved this class of
problem: a configured harness (engine, model, budgets pinned in config), one
subprocess pattern with per-engine adapters, real HOME with an isolated
empty workdir and a positive environment allowlist, and session cleanup.

Owner decisions from the discussion: ccr is the initial engine (an external
CLI dependency — allowed by the treaty, which permits external CLI engines
and forbids external plugins/skills); the owner configures a dedicated ccr
test profile on the host; this repository documents the setup; the host-side
profile is named `skills-tests-claude`, and the model is not the
repository's concern — it is chosen entirely inside that host-side profile.

## Goals / Non-Goals

**Goals:**

- A live run is one command from fresh checkout (given the ccr profile) to
  verdict.
- Nothing is guessed: profile, fixture, assertions, budgets are all pinned
  artifacts.
- The system serves all skills and hosts over time; the first scenario is
  real work (agents-md mirror), not a demo.

**Non-Goals:**

- A generic eval framework with rankings and corpora — the legacy
  `eval_runner` ambitions stay retired.
- Speed-1 machinery: structure checks and runtime tests keep their existing
  lanes; live runs only sediment reproducible regressions into them.
- Multi-engine parallel matrices — one engine (ccr) first; adapters make
  more possible later.

## Decisions

### D1. Pinned profile in a versioned config

A small profile file in the repository (engine, engine profile, budgets).
The file contains no secrets and no model — ccr owns credentials and the
model choice on the host. The runner refuses
to substitute providers: a broken profile is an error pointing at the
how-to, exactly because "picking what resolves" produced this change.

### D2. ccr as the initial engine, with a documented host-side profile

`ccr <profile> -- <args>` gives a Claude-compatible CLI over the owner's
router with controlled providers. The owner sets up the dedicated
`skills-tests-claude` test profile there; `docs/how-to/` gets the setup
guide (EN/RU), including the preflight check (`ccr` present, profile
directory present).

### D3. Isolation by workdir and env allowlist, not by hidden HOME

The engine subprocess runs with the real HOME (its auth just works) but in
an isolated empty workdir containing only the staged fixture, and with a
positive environment allowlist (PATH, HOME, USER, LOGNAME, SHELL, TERM,
TMPDIR, TZ, LANG, LC\_*, XDG\_*). Writes stay inside the fixture; snapshots
before/after prove it. This replaces the sandboxed-HOME probe rule in
AGENTS.md, which existed to prevent history pollution — under ccr the run
goes through the router's own session space, and any host session artifacts
are the documented cost of the profile, not a leak. Permissions stay
scoped the same way: file edits are auto-accepted inside the staged
workdir (`acceptEdits`), and any wider tool use must be granted per
scenario in `allowed_tools` — never a blanket bypass from the adapter.
The runner fingerprints the engine's host-side profile directory before
and after each run and records drift in the report as informational
evidence of that residual risk. The AGENTS.md rule revision rides with
this change.

### D4. Adapter shape from gitlaw's harness

One `_CliProfile`-style adapter per engine: build\_start and parse for the
single-shot runs this system needs; continue and session-cleanup slots are
added when a host actually requires them. The ccr adapter is first; an
opencode adapter is the natural second. Scenarios never learn which engine
runs them.

### D5. Scenarios as directories

`evals/live/<scenario>/`: `fixture/` (the fixture repository content),
`prompt.txt`, `assertions.json` (declarative checks: file exists, is
symlink, content equals other file, content unchanged hash, output
mentions), and an optional `allowed_tools` list of narrowly scoped tool
grants (`Bash(ln:*)`, ...) the scenario's work needs beyond file edits.
Assertions and grants are data; the runner interprets them. The first
scenario `agents-md-mirror` reuses today's proven fixture (root python
project, nested go-tool, ts-widget with a diverged CLAUDE.md) and its
fault-injected `ln` variant.

### D6. One task, runner under scripts

`task live:run --scenario <name>` (or `--all`) wraps
`scripts/live_runner.py` (Python, uv, repo tooling — not shipped inside
skill archives, so dependencies are allowed). Reports land under `.build/`
(gitignored) with a verdict, budgets, and the redacted transcript.

### D7. Legacy live lane retires, offline corpus stays

The retirement boundary discovered during implementation: only the live
execution lane was dead (zero live runs ever) — `eval:live`, the
`evals-live.yml` workflow, the `--trusted-live` mode and its host
execution inside `eval_runner.py`. The offline corpus
(`evals/contracts`, `evals/scenarios` case contracts) is live speed-1
material, and `eval_runner.py` doubles as the library the acceptance
harnesses load (`isolated_environment`, `host_command`,
`parse_host_output`, `budget_assertions`, `redact_text`), so both stay.
Corpus case contracts become forward declarations: the offline runner
reports the case layer `not_observed`; real-model observation belongs to
this system's scenarios.

## Risks / Trade-offs

- \[ccr is a moving external dependency] → the how-to pins a verified
  version; a preflight check fails loudly on drift before any model call.
- \[Real HOME widens the blast radius vs sandboxed HOME] → the empty workdir,
  env allowlist, and before/after snapshots bound the run; the profile
  isolates model routing; the residual risk (host session artifacts) is
  accepted and documented in D3.
- \[Declarative assertions may not cover a subtle behavior] → scenarios may
  assert on transcript mentions; anything not expressible stays a manual
  read of the evidence, which speed 2 explicitly allows.

## Migration Plan

1. Runner + profile + ccr adapter + how-to; preflight.
2. Scenario `agents-md-mirror`; execute it — this closes `spec-agents-md`
   task 2.2.
3. AGENTS.md rule revision; retire the legacy eval lane.

## Open Questions

- Where scenario evidence should live long-term (`.build/` now; XDG state if
  history matters later).
- Whether an opencode adapter is needed soon for host-parity checks, or ccr
  alone suffices for the catalog sweep.
