# `task-triage`

## Purpose

Triage one GitLab issue or a bounded issue collection into actionable,
evidence-backed task assessments and an execution order without changing GitLab.

## Triggers and Near-Misses

Trigger for project-level issue triage, an explicit issue list, or one issue that
requires project context; near-miss: drafting a new task or implementing it.

## Inputs and Outputs

Input is one exact GitLab issue URL, an explicit cross-project issue list, or a
project issue/work-item collection URL with optional user-supplied filters. A
collection defaults to open issues. Output is one stable collection summary and
one stable detailed report per issue in private XDG state.

## Workflow Stages

Resolve the bounded collection, collect GET-only GitLab evidence, reuse current
per-issue analysis when its issue and related-MR fingerprint is unchanged,
normalize each issue to `work-item/v1`, invoke the task-review quality contract,
assess the collection, persist immutable evidence and analysis, atomically
replace stable Markdown views, present, and report.

## Dependencies

Authenticated read access through `glab`, complete pagination for the declared
scope, and the bundled work-item, review, and GitLab triage contracts.

## Remote/Local Effects

Private content-addressed evidence and analysis are stored below XDG state with
stable summary and per-issue Markdown pointers. Output includes manual `glab`
commands backed by immutable request files. The workflow never executes those
commands or mutates GitLab.

## Errors, Partial, Escalation

Target failures are isolated per issue. Incomplete pagination, unavailable issue
or MR evidence, stale bindings, and unanswered business-priority questions make
the collection partial and remain explicit. Independent analysis continues
before one consolidated question round.

## Unique Constraints

Every issue reports actuality, duplicate candidates, task-review quality verdict,
related issues, related MRs, linkage gaps, SemVer impact, severity, priority,
confidence, and recommended manual changes. The collection reports at most five
first tasks plus dependency and parallel-execution groups. Project-wide duplicate
search is bounded to each member's project; external projects are followed only
through explicit input or observed links.

## Requirement

### REQ-F-125 - Triage a bounded GitLab issue collection

The skill shall accept one issue, an explicit cross-project issue list, or a
filtered project collection; default a collection to open issues; and normalize
each selected issue to `work-item/v1`. It shall collect complete GET-only evidence,
reuse deep analysis only when its bound issue and related-MR fingerprint is
current, apply the `task-review` quality contract, and persist private immutable
evidence and analysis with atomic stable Markdown views. Each issue shall report
actuality, duplicates, quality, links, related merge requests, SemVer, severity,
priority, confidence, and safe manual update commands. The collection shall
report dependencies, parallel work, and at most five first tasks. Partial or
stale evidence shall remain explicit and shall not be reported as complete. The
workflow shall never execute generated commands or mutate GitLab.

## Example

`task-triage` reuses an unchanged issue analysis, recomputes collection-level
priority after another issue changes, and emits an updated stable summary without
executing its proposed GitLab commands.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
