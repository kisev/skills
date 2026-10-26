# Proposal

## Why

taskmatic (skill + application) — application verdict decided (needed, rework, Python port); the skill interface itself has no verdict yet. This change gives the component its exhaustive
specification and executes the renegotiation decisions that concern it.

## What Changes

The kanban application — SQLite as the single source of truth, markdown mirror, read-only web export, agent claims with TTL/heartbeat, an MCP server with eleven tools — and its skill interface, which is instructions plus a snapshot contract only.

Fully standalone today: zero relations. The npm/Node runtime is replaced by the Python port decided in the renegotiation.
Open: application rework spec, skill-interface verdict, exhaustive capability specs.

## Capabilities

### New Capabilities

None yet — the exhaustive capability spec for this component is drafted
inside this change when it is picked up.

### Modified Capabilities

None.

## Impact

`skills/taskmatic` and `apps/taskmatic`.
