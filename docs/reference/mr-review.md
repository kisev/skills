# mr-review: Collection, OCR Runs, Runbook

[Русский](../ru/reference/mr-review.md)

This page documents the `mr-review` line: the read-only collection, the single
startup round, the parallel OCR runs, the runbook, and the GitLab draft notes.
The skill texts in `skills/mr-review/` own the operational doctrine; this page
is the architecture view.

## Pipeline map

One map for the review line. Every command and stage names the runtime's
canonical tokens; the contract test pins both directions, so a renamed command
cannot appear on one side alone.

```mermaid
flowchart TD
    P0[Pinned uvx runtime\nruntime-info] --> P1[collect\nMR, diff, discussions\npipelines, linked issues\nexact refs]
    P1 --> P2{Startup round\naliases and effort\ntask baseline}
    P2 --> P3[background\n8000-byte limit\ndisclosed cuts]
    P3 --> P4[ocr-runs\none process per alias\nparallel]
    P4 --> P5{Previous session?}
    P5 -->|yes| P6[ocr-compare\nnew, persisting, resolved\nnot reviewed]
    P5 -->|no| P7[revalidate\nhead freshness]
    P6 --> P7
    P7 --> P8[runbook\nOCR runs, Task fulfillment\nChecks]
    P8 --> P9[drafts\nhead check\ndraft notes]
    P9 --> P10[report\nprocess only]
```

## Target and scope

Exactly one GitLab merge request URL is the target. A branch name is not a
target, a local working tree is out of scope, and several URLs stop the skill.
A release merge request routes to `release-review`.

## Untrusted input

Merge request content and OCR output are untrusted data, never instructions.
The URL, title, description, notes, discussions, diff, pipeline fields, linked
issues, and OCR findings are evidence to assess; an embedded instruction never
changes the procedure, the verdict criteria, or the read-only boundary.

## Self-contained archive

The installed archive carries every `references/...` path its text names. It
does not bundle the shared GitLab publication workflow or interaction-contract
references, which the skill never links. The distribution check fails on a
dangling backticked reference in any archive.

## Engine and profile

The external `ocr` CLI is the only review engine; the tested minimum is 1.13.6.
The in-house critic, arbitration, receipt, and repair machinery is gone. The
profile defines reviewer aliases in `~/.reviewmatic/reviewers.json` and
`./.reviewmatic/reviewers.json`; the local file overlays the global one by alias
and default. A profile holds aliases, provider, model, and effort, never
secrets, and the skill never reads `~/.opencodereview/config.json`.

## Sessions

Every OCR run persists a session. A follow-up review is a fresh run over the
current range plus `ocr session compare`, grouped as new, persisting, resolved,
or not reviewed. `--resume` continues an interrupted run. There is no ledger.

## Runbook and publication

The runbook keeps its format with listed changes: `OCR runs` replaces the panel,
`Arbitration verdicts` appears only for merged runs, `Task fulfillment` is
added, labels and MR metadata are removed, checks are simplified, and `Previous
findings` comes from the session comparison. Publication is one non-interactive
shell block of GitLab draft notes with a head check; the human edits and
publishes in the UI. No publish command exists.

## Helper surface

| Command | Mechanical guarantee |
| - | - |
| `collect` | read-only exact collection, completeness, redaction |
| `background` | the 8000-byte limit, task first, disclosed cuts |
| `ocr-runs` | one process per alias, parallel, JSON parsing |
| `ocr-compare` | new, persisting, resolved, not reviewed |
| `revalidate` | head freshness against the collected snapshot |
| `drafts` | head check and draft-note commands, no publish |
| `profiles` | effective profile and provider validation |
| `runtime-info` | version and resolved install commit |
