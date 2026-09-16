# `/agent-profiles`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Profile management remains available through `skills-opencode agent` and `critic` commands.

## Purpose

Historical capability record for the retired slash-command adapter.

## Triggers and Near-Misses

Trigger for profile lifecycle; near-miss: direct `opencode.json` editing.

## Inputs/Outputs

Input is action, optional scope defaulting to project, and optional confirmed
digest; output is structured plan/result.

## Workflow Stages

Resolve ownership, inspect/list, preview, confirm, apply atomically, report.

## Dependencies

Core `agent_profiles` package tool and profile manifests.

## Remote/Local Effects

Bounded local global/project configuration effects; no remote effects.

## Errors/Partial/Escalation

Collision, stale receipt, symlink, or rollback failure is explicit.

## Unique Constraints

Package does not edit `opencode.json` directly.

## Requirement

### REQ-I-233 - Route the agent-profiles package command

Status: withdrawn on 2026-09-16 because profile management is now CLI-only.

Former requirement: the command shall expose the exact package-tool argument schema, default omitted
scope to project, invoke package tool `agent_profiles`, and require preview plus
confirmation for mutation.

## Example

`/agent-profiles` previews a project profile change before apply.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
