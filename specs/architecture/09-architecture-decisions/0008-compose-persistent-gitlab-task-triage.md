# ADR-0008: Compose persistent GitLab task triage

- Status: accepted
- Date: 2026-09-23
- Status changed: none
- Supersedes: none
- Superseded by: none

## Context and problem statement

Useful triage requires collection-wide duplicate, dependency, priority, and
parallelism analysis. The previous single-source storage-neutral contract could
not retain evidence, avoid repeated deep analysis, or relate issues and merge
requests.

## Decision drivers

- Preserve portable, read-only behavior and private state.
- Reuse one quality contract across standalone review, preparation, and triage.
- Support one issue and bounded cross-project collections without repeated work.
- Keep generated GitLab mutations manual and auditable.

## Considered options

- Extend the generic work-item runtime with GitLab collection and state semantics.
- Restore the complete multi-purpose portable GitLab runtime in every task skill.
- Add a narrow shared triage runtime and compose the existing work-item and review contracts.

## Outcome

Task triage owns a narrow GitLab collection runtime and XDG collection state. It
stores immutable evidence and semantic analysis, publishes atomic stable Markdown
views, and invokes the same quality rules documented by `task-review`.
`task-prepare` remains the authoring workflow and may consume triage findings;
standalone `task-review` remains storage-neutral. The generic work-item runtime
does not acquire tracker-specific behavior.

## Consequences

### Positive

- Collection analysis, stable artifacts, and cache invalidation have one owner.
- Task quality findings remain consistent across all three task workflows.
- GitLab mutation commands are reviewable and cannot execute accidentally.

### Negative

- Triage has a larger read scope and a separate persistent-state contract.
- Collection-level ordering must be recomputed when membership changes even when
  deep per-issue analysis remains reusable.

## Compatibility

The former generic triage input contract is replaced. Standalone preparation and
review retain their neutral inputs, and `work-item/v1` remains the common semantic
representation.

## Migration

Existing generic triage output is not durable and requires no state migration.
New state uses a dedicated task-triage XDG namespace and does not reinterpret
other portable GitLab pointers.

## Rollback

The triage adapter and its manifest entries can be removed without changing
GitLab. Its private state can remain inert because no other workflow owns it.

## Reversibility

Reversal is moderate: canonical contracts and generated assets must return to the
single-source model, but no external data migration is required.

## Risks

- Stale collection conclusions are mitigated by separate per-issue and collection fingerprints.
- Large projects are mitigated by bounded pagination, incremental analysis, and explicit partial status.

## Links

- Requirements: [REQ-F-125](../../capabilities/skills/task-triage.md#req-f-125---triage-a-bounded-gitlab-issue-collection), [REQ-I-225](../../capabilities/commands/task-triage.md#req-i-225---route-the-task-triage-command)
- Related ADRs: [ADR-0004](0004-content-addressed-archive.md)
