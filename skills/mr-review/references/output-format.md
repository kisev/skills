# Output Format

Select the response language in this order: explicit user request, applicable
agent instructions, established user prose, then English. The selected language
applies to questions, runbook prose, and replies. Preserve code, commands,
paths, IDs, revisions, labels, and quotations exactly.

## Runbook

The runbook is the human review document written by the manager, normally
`.reviewmatic/runbook.md`. It keeps its existing sections with only these
changes. Empty sections are omitted.

| Section | Content |
| - | - |
| Header | `mr-review: <skill version> · contract: <version>` |
| Target and verdict | merge request, role, the fulfillment verdict with its reason, technical and process blockers |
| Task fulfillment | solved, partially, or not solved; the evidence; every uncovered acceptance criterion |
| OCR runs | each run with alias, provider, model, and effort, parallel or serial, duration, exit code, and finding count |
| Arbitration verdicts | only when several runs were merged: duplicates, conflicting severities, and every recorded reason |
| Previous findings | only with a previous session: current findings grouped as new, persisting, resolved, or not reviewed |
| Architecture assessment | one manager-written paragraph against `architecture-checklist.md` |
| SemVer impact | the compatibility assessment against the established release basis (`semver.md`) |
| Checks | pipeline status, failed jobs one line each, what the OCR runs covered, and what stayed unverified |
| Finding list | each finding's essence, severity, and location, with the draft block at the end |
| Draft notes | one non-interactive shell block, defined in `publication.md` |

The runbook does not contain `Project labels`, `MR metadata`, `Local fixes`, or
`Manual publication preflight`. Checks do not classify every failed job by
trace, and no publish command exists.

Each actionable item shows its natural conclusion and its exact location so the
human can find it. The runbook never shows raw internal IDs, digests, or a
second copy of a draft note body.

## Chat report

The final chat report describes the process only:

- what was collected and what failed;
- each OCR run: alias, provider, model, effort, parallel or serial, duration,
  exit code, and findings count;
- the merge result when several runs were used;
- limitations: background cuts, unavailable CI traces, incomplete collection;
- the absolute runbook path and the draft block path;
- the next step.

The chat report carries no merge request verdict or assessment; the verdict
stays in the runbook. A blocked or partial result is reported as blocked or
partial together with the missing input.
