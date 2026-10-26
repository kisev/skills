# Proposal

## Why

handoff — core skill confirmed in the foundation renegotiation (see `renegotiate-foundation`): frequently used and staying. This change gives the component its exhaustive
specification and executes the renegotiation decisions that concern it.

## What Changes

Session handoff into XDG state with per-session isolation, content-addressed history snapshots, and a 256KiB cap; the repository is never touched.

Decided rework: weight hygiene (21KB bytecode cache in the authored tree) and formalizing the optional memomatic mirror, which no relation records today.
Open: exhaustive capability spec.

## Capabilities

### New Capabilities

None yet — the exhaustive capability spec for this component is drafted
inside this change when it is picked up.

### Modified Capabilities

None.

## Impact

`skills/handoff` and its memory integration.
