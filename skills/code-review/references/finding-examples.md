# Finding examples

Calibrate evidence and minimum fixes with these examples; never copy claims
without verifying the reviewed project and exact-revision evidence, and keep
raw SHAs out of user-facing prose.

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
| Thread | State | Assessment | Rationale | Proposed outcome |
| --- | --- | --- | --- | --- |
| [note_42](https://gitlab.example/group/project/-/merge_requests/7#note_42) | open | accepted | The exact reviewed path still retries without an idempotency key. | local_fix |
```

Valid outcomes are `no_reply`, `local_fix`, `reply`, `resolve`, and
`reopen`, following the six-case matrix: natural prose from the authenticated
user's factual role with
informal second person, and no severity or evidence labels. An open thread
with an attempted fix uses `reply` (or author-mode `local_fix`); an open
thread with a confirmed but unattempted defect uses `no_reply`; an open
thread the review confirms fixed or does not confirm uses `reply` plus
`resolve`; a thread resolved by
another user needs a reply only when it adds information, and
`no_reply` applies after confirming the existing explanation or applied
suggestion remains correct.

For an actionable current new-line position, prepare exactly one suggestion.
Use a bounded range opener for a contiguous multi-line replacement:

````markdown
You need to reserve the idempotency key before the provider call.

```suggestion:-1+1
operation = reserve_operation(request.id)
result = provider.submit(operation)
```
````

For separate safe positions, use related `suggestions` records (`path`, `line`,
natural `body` with one block each) plus `split_rationale`; never split one
problem into several findings, and prefer a suggestion to a patch
(`fix_mode=patch` only when a suggestion cannot express the fix or division
is unsafe, with `patch_reason` and prose-only `body`). The runner checks the
patch against the exact reviewed head without changing the checkout and
writes it as an immutable `.patch` file; unrelated findings stay in one patch,
multiple blocks in one positioned part, suggestion on a deleted line, binary
or symlink patches, and rewritten fix content after confirmation are invalid.
Omit `index` lines so private revision identifiers do not enter the plan.

## Grouped suggestion bodies

For `resolve` or `reopen`, publish the explanatory reply first and show the
state change as a separate command; never close or reopen a thread without
that reply. Parts of grouped suggestions are published verbatim as complete
short comments; preserve all necessary caveats per part and do not repeat
the shared explanation the part already covers.

## Recommended issue

Use a recommended issue only for a confirmed real problem the MR neither
introduces, worsens, moves, nor depends on for safe operation — stable ID,
title, problem, risk, evidence, why it is outside this MR, minimum fix, and a
complete natural issue body. It never blocks the MR and is never created
automatically.

## Author mode

For the author's own MR, report the same risk and minimum fix as a
`local_fix` with `fix_mode=patch`; never create a review thread, edit the
checkout, or describe the author as an independent reviewer.

## Weak formulations

- `Closing.` / `Fixed.`: neither names the checked behavior nor explains why
  the closure is valid.
- `This function is too long`: no consequence or contract evidence.
- `Tests are missing`: not a finding until a concrete unverified behavior is
  identified.
- `This may be slow`: speculation without a path, scale, or measurement.
- `Move this to another service`: not a fix without an ownership or
  failure-mode advantage.

## Follow-up calibration

- A user accepts one narrow risk (switching a local account mid-operation); a
  new reviewer inherits it; a regression sending every request under the wrong
  account is different and stays actionable.
- The agreed renderer links only wholly plain-text values and leaves mixed
  Markdown untouched. An unlinked reference inside a Markdown table is within
  the accepted boundary, not a new parser requirement. Corrupting that table is
  a regression that must still be reported.
- A list of examined discussion IDs does not prove the model chose the
  right discussion; it never becomes a blocking validator change without a
  concrete violated requirement.
- A generated summary showing a deferred item as ready: fix the evidence
  binding, don't label High merely for a constructible invalid input.
- An API rejecting a second relation between the same pair: rejecting the
  conflicting proposal satisfies the contract; delete-and-recreate is a
  separate feature with partial-failure cost, required only by user scope.
