# Architecture checklist

Use only the groups relevant to the change, but make each group an explicit decision.

## Necessity and scope

- Identify the observable problem, affected user, and success condition.
- Verify that the change solves the cause rather than masking a symptom.
- Identify unrelated scope that increases risk.
- Preserve the agreed supported scenarios, accepted risks, and completion checks.
- Separate reachable contract failures from optional hardening and new features;
  reproduction alone does not establish that a remedy is proportionate.

## Ownership and boundaries

- Confirm that responsibility belongs in the changed module and layer.
- Look for a second source of truth, duplicate state machine, or conflicting precedence.
- Match resource and data lifecycle to its durable owner.

## Existing behavior

- Find direct callers and consumers, not only changed files.
- Check batch/single, sync/async, retry, cache, rollback, and background paths.
- Verify configuration, environment, argument precedence, defaults, and compatibility.

## Failure and operations

- Check timeout, partial failure, duplicate delivery, restart, and idempotency.
- Ensure errors are observable without leaking secrets or personal data.
- Check bounded memory, queues, requests, concurrency, and metric cardinality.
- Identify a safe rollout and rollback for stateful or incompatible changes.

## Security and data

- Identify every trust boundary and authorization decision.
- Trace untrusted values reaching `eval`, `exec`, `source`, command substitutions, paths, templates, and serialization.
- Check tenant isolation, least privilege, retention, deletion, and migration.

## Verification

- Tests must exercise an observable contract and a meaningful negative path.
- A mock must not merely repeat the implementation.
- Confirm that CI ran against the exact reviewed SHA and affected path.
- State how a failure would be detected after rollout.

## Alternatives

- Propose an alternative only after finding existing project patterns.
- Compare ownership, compatibility, failure modes, implementation cost, maintenance, rollout, and verification.
- Do not request an abstraction or refactor without a concrete risk reduction.
- If repeated fixes expand one mechanism, consider a simpler supported behavior
  before adding another layer; explain the tradeoff against the agreed goal.
