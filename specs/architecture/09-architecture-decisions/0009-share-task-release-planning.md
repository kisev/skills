# ADR-0009: Share task release planning

- Status: accepted
- Date: 2026-09-23
- Status changed: none
- Supersedes: none
- Superseded by: none

## Context and problem statement

Task preparation could pass an observed milestone ID, but task review and triage
did not validate release planning. Copying code-review's MR-specific SemVer logic
would duplicate policy and introduce checkout assumptions into portable tasks.

## Decision drivers

- Every accepted versioned task must belong to a compatible release milestone.
- SemVer and milestone rules must be identical across all task workflows.
- Each project or independently versioned component owns its release line.
- GitLab changes remain manual and evidence-bound.

## Considered options

- Duplicate milestone selection in each task skill.
- Require users to run triage manually before every preparation or review.
- Share one pure release-planning contract and let triage own evidence and state.

## Outcome

All task skills materialize one tracker-neutral release-planning validator.
It validates task impact, selected release impact, planning decision, milestone
identity, and compatibility. Agents establish project release policy from
evidence; the validator does not infer policy from branch or tag names.

Task triage collects release and milestone catalogs, autonomously records the
planning decision, and owns durable artifacts. Task review reuses the validation
without fetching or persisting tracker state. Task preparation consumes current
triage evidence or invokes scoped single-item triage and translates only an
observed selected milestone ID into publication metadata.

## Consequences

### Positive

- SemVer and milestone decisions have one machine-checked shape.
- Top-five prioritization cannot leave other accepted work unplanned.
- Cross-project collections retain separate release lines.

### Negative

- GitLab preparation may remain partial until a newly proposed milestone exists
  and scoped triage is refreshed.
- Release-policy interpretation remains a semantic agent responsibility.

## Compatibility

GitLab task preparation now requires release-planning evidence for ready issue
publication. Neutral work-item structure remains `work-item/v1`.

## Migration

Existing triage analysis is invalidated by the expanded analysis contract and
must be regenerated. Existing task-publication plans without release planning
remain readable but are not current ready plans.

## Rollback

Remove the shared validator materializations and milestone fields. No GitLab
mutation requires reversal because all commands are manual.

## Reversibility

Moderate. Persisted task analysis must be regenerated after either transition.

## Risks

- An incorrect project release policy can still select the wrong milestone; all
  semantic decisions therefore retain rationale, confidence, and catalog binding.
- `none` and `not_applicable` map to patch planning by explicit project policy.

## Links

- Requirements: [REQ-F-125](../../capabilities/skills/task-triage.md#req-f-125---triage-a-bounded-gitlab-issue-collection)
- Related ADRs: [ADR-0008](0008-compose-persistent-gitlab-task-triage.md)
