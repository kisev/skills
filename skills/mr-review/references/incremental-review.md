# Incremental Review

Incrementality is OCR sessions, not a ledger.

Every `ocr review` run persists a session. A follow-up review of the same merge
request is a fresh run over the current range plus a comparison with the
previous session:

```shell
reviewmatic ocr-compare --before <previous-session> --after <current-session> --repo <checkout>
```

The comparison matches findings on path, category, and the offending snippet,
so a finding that only moved down the file still counts as persisting. It
groups the current findings as:

- new — not present in the previous session;
- persisting — present in both;
- resolved — reported before and absent now;
- not reviewed — not reached by the current run.

The grouping is advisory context for the runbook's Previous findings section.
The verdict stands on the current run; never copy historical IDs or infer that
an old verdict remains true.

The reviewer always sees current code. There is no anchoring on old findings,
no ledger reconciliation, and no old-finding checklist in the background.

`--resume <session-id>` continues an interrupted single run instead of starting
over. A compressed prior-review summary — verdict, accepted risks, open
questions — may ride in the background file as context, not as a checklist.
