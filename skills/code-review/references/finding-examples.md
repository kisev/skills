# Finding examples

Use these examples to calibrate evidence and minimum fixes. Do not copy claims without verifying the reviewed project and private exact-revision evidence. Keep raw SHAs out of user-facing prose.

## Evidence-backed finding

```markdown
### High: Retry can submit the same payment twice

- Risk: a client retry after a lost response can charge the user twice.
- Evidence: `CreatePayment` stores the operation ID after the provider call, while the retry path invokes it again with the same request ID. The timeout integration test creates two provider records. Link both locations to immutable revisions without displaying raw SHAs.
- Consequence: duplicate external side effects and manual reconciliation.
- Relation to change: the MR adds the automatic retry but does not establish idempotency before the external call.
- Minimum fix: reserve the operation ID before the provider call and return the stored result for a repeated request.
```

## Architecture finding

```markdown
### High: Environment setting bypasses the policy source of truth

- Risk: API and background processing can apply different retention periods.
- Evidence: the new API path reads `RETENTION_DAYS` directly, while workers and migrations use `RetentionPolicy`.
- Consequence: data can be deleted earlier than the configured policy.
- Relation to change: the direct environment read is introduced by this MR.
- Minimum fix: add the environment value as an input to `RetentionPolicy` and keep precedence in one owner.
```

## Thread decision

```markdown
| Thread                                                                     | State | Assessment | Rationale                                                         | Proposed outcome |
| -------------------------------------------------------------------------- | ----- | ---------- | ----------------------------------------------------------------- | ---------------- |
| [note_42](https://gitlab.example/group/project/-/merge_requests/7#note_42) | open  | accepted   | The exact reviewed path still retries without an idempotency key. | local_fix        |
```

Valid outcomes are `no_publication`, `local_fix`, `reply`, `resolve`, and
`reopen`. A publishable response is natural prose followed by a runner-owned
hidden marker; do not put severity or internal evidence labels in that prose.
Write it from the authenticated user's factual role and use natural informal
second person when addressing the participant.

For an actionable current new-line position, prepare exactly one suggestion:

````markdown
You need to reserve the idempotency key before the provider call.

```suggestion
operation = reserve_operation(request.id)
```
````

For a general, deleted, or outdated position, omit `suggestion` and provide a
concrete patch or replacement in prose instead.

## Recommended issue

Use a recommended issue only for a confirmed real problem that the MR neither
introduces, worsens, moves, nor depends on for safe operation. Include a stable
ID, title, problem, risk, evidence, why it is outside this MR, a minimum fix, and
a complete natural issue body. It does not block the MR and is never created
automatically.

## Author mode

For the author's own MR, report the same risk and minimum fix as a local correction. Do not create a new review thread or describe the author as an independent reviewer.

## Weak formulations

- `This function is too long` has no consequence or contract evidence.
- `Tests are missing` is not a finding until a concrete unverified behavior is identified.
- `This may be slow` is speculation without a path, scale, or measurement.
- `Move this to another service` is not a fix without an ownership or failure-mode advantage.
