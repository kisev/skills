# OCR Runs

Every finding comes from an `ocr review` run. The manager never hunts for
defects, never adds a finding of its own, and never runs an in-house critic,
subagent reviewer, or arbitrator.

## One run by default

One selected alias is the default. Depth is chosen by runs, not by a mode:
selecting several aliases with different providers, models, or efforts buys
independence. Each alias runs as its own `ocr review` process with its own
`--output`; several aliases run in parallel.

The runbook lists each run with its alias, provider, model, and effort. When
one run was selected, no arbitration section is produced.

## Merging

When several runs were selected, the manager merges their findings:

- A duplicate of another run's finding is recorded as a duplicate, naming the
  canonical finding and the run that reported it.
- Conflicting severities resolve to one severity, and the merged finding
  records the chosen severity and the reason.
- A finding is never dropped or downgraded silently. Every drop or downgrade
  records its reason: duplicate, out of scope, or contradicting the confirmed
  task baseline.

The arbitration is surfaced in the runbook. It describes the merge decision;
it is not a new review.

## A failed run

An OCR run that fails is reported with its exit code and the disclosed error,
and the review stops. The manager never substitutes its own review for a failed
run. A missing `session_id` means the run has no persistent identity; report it
and do not use its output.

## A suspicion

When the manager suspects a defect the runs did not report, it records a
question without severity or buys one more pointed OCR run with a narrower
background. It creates no finding.
