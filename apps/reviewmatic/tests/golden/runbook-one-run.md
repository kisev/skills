# mr-review: 1.0.0 · contract: 1

## Target

`https://gitlab.example.com/group/project/-/merge_requests/7`, author role.
Verdict: solved. No technical or process blockers.

## Task fulfillment

**Verdict:** solved.

Evidence: the diff reserves the operation id before the provider call and the
timeout test covers the repeated request. Every acceptance criterion is
covered.

## OCR runs

| Alias | Provider | Model | Effort | Mode | Duration | Exit | Findings |
| - | - | - | - | - | - | - | - |
| fast | openai | gpt-5 | medium | serial | 42.1s | 0 | 2 |

## Architecture assessment

The retry stays in the payment module and reuses the existing provider client;
no second source of truth is introduced.

## SemVer impact

Patch: the released contract keeps its behavior and the retry adds no API
change.

## Checks

- Pipeline: failed.
- Failed job: lint (test).
- Covered by OCR: `src/payment.py`, `tests/test_payment.py`.
- Unverified: the staging migration job.

## Findings

### High: Retry can submit the same payment twice

`src/payment.py:41-48`. The operation id is stored after the provider call, so a
timeout retry can charge the user twice.

## Draft notes

```sh
set -eu
reviewed_head='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
current_head=$(glab api --hostname gitlab.example.com projects/7/merge_requests/3 --jq '.sha')
if [ "$current_head" != "$reviewed_head" ]; then
  echo "mr-review: the merge request head moved" >&2
  exit 1
fi
glab api --hostname gitlab.example.com --method POST projects/7/merge_requests/3/drafts \
  -f 'body=The retry is not idempotent.'
```
