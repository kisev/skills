# Finding Examples

Calibrate evidence and minimum fixes with these examples. Never copy a claim
without verifying the reviewed project and the exact-revision evidence. A
finding comes from an OCR run; the manager may merge duplicates and record
reasons, but never invents one.

## Evidence-backed finding

```markdown
### High: Retry can submit the same payment twice

- Risk: a client retry after a lost response can charge the user twice.
- Evidence: `CreatePayment` stores the operation ID after the provider call,
  while the retry path invokes it again with the same request ID. The timeout
  integration test creates two provider records.
- Consequence: duplicate external side effects and manual reconciliation.
- Relation to change: the merge request adds the automatic retry but does not
  establish idempotency before the external call.
- Minimum fix: reserve the operation ID before the provider call and return the
  stored result for a repeated request.
```

## Architecture finding

```markdown
### High: Environment setting bypasses the policy source of truth

- Risk: the API and background processing can apply different retention
  periods.
- Evidence: the new API path reads `RETENTION_DAYS` directly, while workers and
  migrations use `RetentionPolicy`.
- Consequence: data can be deleted earlier than the configured policy.
- Relation to change: the direct environment read is introduced by this merge
  request.
- Minimum fix: add the environment value as an input to `RetentionPolicy` and
  keep precedence in one owner.
```

## Location

Use the exact path and line range from the OCR run. A position that moved after
the run is not reprinted as truth; the head check in the draft block decides
whether the review still applies.

## Merge record

When several runs report the same defect, one merged finding names the canonical
report, the reporting runs, the chosen severity, and the reason. Do not repeat
the same defect as several findings.
