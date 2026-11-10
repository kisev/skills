# mr-review: 1.0.0 · contract: 1

## Target

`https://gitlab.example.com/group/project/-/merge_requests/7`, author role.
Verdict: partially. One acceptance criterion is uncovered.

## Task fulfillment

**Verdict:** partially.

Evidence: the limit applies per IP, but the per-user criterion is absent. The
uncovered criterion is "limits are per authenticated user".

## OCR runs

| Alias | Provider | Model | Effort | Mode | Duration | Exit | Findings |
| - | - | - | - | - | - | - | - |
| fast | openai | gpt-5 | medium | parallel | 41.0s | 0 | 2 |
| deep | anthropic | claude-opus-5 | high | parallel | 66.2s | 0 | 3 |

## Arbitration verdicts

- `fast` and `deep` both reported the missing per-user limit; merged once with
  the canonical report from `deep`.
- `fast` reported a stale-cache concern at `high`; `deep` reported the same
  defect at `medium`. Chosen severity: `medium`, because the cache expires in
  one minute and the duplicate is recorded.
- `deep` reported a logging concern outside the reviewed scope; dropped as out
  of scope, reason recorded.

## Architecture assessment

The limiter sits in the API middleware; a second copy in the worker path
duplicates the policy and is the main architectural risk.

## SemVer impact

Minor: the endpoint gains a new throttling behavior but no breaking contract
change.

## Checks

- Pipeline: passed.
- Covered by OCR: `src/middleware.py`, `src/worker.py`.
- Unverified: the load test did not run on this revision.

## Findings

### Medium: The worker path bypasses the limiter

`src/worker.py:88-95`. Background jobs can exceed the configured limit.

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
  -f 'body=The worker path bypasses the limiter.'
```
