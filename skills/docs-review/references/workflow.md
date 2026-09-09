# Documentation Review Workflow

The input is a path or scope. Without one, establish the boundary through the host interaction mechanism or chat. If it is in `specs/`, stop and offer `spec-manage` in `spec-audit` mode. Do not change the repository, documents, external systems, or create artifacts; report findings only in chat and never publish them.

Identify the target reader and purpose in scope. Check claims, commands, APIs, configuration, and examples against source, configuration, and repository instructions. Check prerequisites, sequence, error consequences, compatibility, stale links, and terminology. Report only confirmed findings, each with severity, exact evidence, consequence, and minimal correction. If none exist, say so briefly and list unverified boundaries.

## Boundary

- Input is a path or area. Without either, first clarify the boundary using the host's standard interactive mechanism, or ask in chat if the host has none.
- If the area is in `specs/`, stop and propose `spec-manage` in `spec-audit` mode.
- Do not modify the repository, documents, external systems, or create artifacts.
- Output findings only in chat; do not publish them to external systems.

## Review

1. Determine the target reader and the purpose of documentation in the specified boundary.
2. Check claims, commands, APIs, configuration, and examples against source code, configuration, and repository instructions.
3. Check prerequisites, order of actions, effects of errors, compatibility, stale links, and terminological consistency.
4. Report only confirmed findings. For each, state severity, precise evidence, consequence, and the minimal fix.
5. If there are no findings, state that briefly and list unverified boundaries.
