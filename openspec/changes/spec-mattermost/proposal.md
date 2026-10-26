# Proposal

## Why

mattermost — core skill confirmed in the foundation renegotiation (see `renegotiate-foundation`): frequently used and staying. This change gives the component its exhaustive
specification and executes the renegotiation decisions that concern it.

## What Changes

Reads Mattermost/Band by exact link (GET-only, SQLite cache with 7-day immutable coverage, transcript windows) and prepares manual, digest-confirmed publications with cards; never sends anything itself.

Decided rework: weight hygiene — more than half of the 604KB directory is bytecode cache; the core runner is 3136 lines.
Open: exhaustive capability spec.

## Capabilities

### New Capabilities

None yet — the exhaustive capability spec for this component is drafted
inside this change when it is picked up.

### Modified Capabilities

None.

## Impact

`skills/mattermost` and its token/auth contract shared with mattermost-triage.
