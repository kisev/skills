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
`reopen`. A publishable response is natural prose; do not put severity or
internal evidence labels in that prose.
Write it from the authenticated user's factual role and use natural informal
second person when addressing the participant.

An open thread must use `reply`, `resolve`, or author-mode `local_fix`. A thread
resolved by another or unknown user still requires a confirming or corrective
reply. Use `no_publication` only for a plain note or when the authenticated user
closed the thread and their latest published conclusion remains current.

For an actionable current new-line position, prepare exactly one suggestion.
Use a bounded range opener for a contiguous multi-line replacement:

````markdown
You need to reserve the idempotency key before the provider call.

```suggestion:-1+1
operation = reserve_operation(request.id)
result = provider.submit(operation)
```
````

For a general, deleted, outdated, non-contiguous, or otherwise unanchorable fix,
set `fix_mode=patch` and provide one applicable textual unified patch:

```sh
git apply <<'PATCH'
diff --git a/src/payment.py b/src/payment.py
--- a/src/payment.py
+++ b/src/payment.py
@@ -18 +18,2 @@
+operation = reserve_operation(request.id)
 result = provider.submit(request)
PATCH
```

The runner checks the patch against the exact reviewed head without changing the
checkout and writes it as an immutable `.patch` file. Do not combine unrelated
findings in one patch. Multiple suggestion blocks, suggestion on a deleted line,
binary or symlink patches, and rewritten fix content after confirmation are
invalid. Omit `index` lines so private revision identifiers do not enter the
publication plan.

For `resolve` or `reopen`, publish the explanatory reply first and show the state
change as a separate command. Never close or reopen a thread without that reply.

## Recommended issue

Use a recommended issue only for a confirmed real problem that the MR neither
introduces, worsens, moves, nor depends on for safe operation. Include a stable
ID, title, problem, risk, evidence, why it is outside this MR, a minimum fix, and
a complete natural issue body. It does not block the MR and is never created
automatically.

## Author mode

For the author's own MR, report the same risk and minimum fix as a `local_fix`
with `fix_mode=patch`. Do not create a new review thread, edit the checkout, or
describe the author as an independent reviewer.

## Weak formulations

- `Closing.` does not explain whether the concern was false, fixed, or still
  relevant, and is not an acceptable closing reply.
- `Fixed.` does not identify the checked behavior or explain why the closure is
  valid.
- `This function is too long` has no consequence or contract evidence.
- `Tests are missing` is not a finding until a concrete unverified behavior is identified.
- `This may be slow` is speculation without a path, scale, or measurement.
- `Move this to another service` is not a fix without an ownership or failure-mode advantage.
