# Proposal

## Why

The live-runs system (change `live-runs`) starts with a single engine and a
single host-side ccr profile (`skills-tests-claude`). The foundation
renegotiation (see `renegotiate-foundation`) targets three hosts — Codex,
Claude, OpenCode — and skill behavior can drift between them; no verdict on
the parity mechanism exists yet, so this change deliberately records no
decisions.

## What Changes

Deferred host-parity runs: a second ccr profile for Codex, a native
OpenCode adapter outside ccr, and host-parity scenarios (the same versioned
scenario executed on every supported host with per-host assertions).

Zero new relations; this extends the `live-runs` system only.
Open: verdict, exhaustive capability spec, adapter design.

## Capabilities

### New Capabilities

None yet — the exhaustive capability spec for this domain is drafted
inside this change when it is picked up.

### Modified Capabilities

None.

## Impact

`scripts/live_runner.py`, `evals/live/`, `docs/how-to/live-runs-ccr.md`
(and its RU mirror).
