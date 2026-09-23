# `task-triage`

## Purpose

Triage one GitLab issue or a bounded issue collection into actionable,
evidence-backed task assessments and an execution order without changing GitLab.

## Triggers and Near-Misses

Trigger for project-level issue triage, an explicit issue list, or one issue that
requires project context; near-miss: drafting a new task or implementing it.

## Inputs and Outputs

Input is one exact GitLab issue URL, an explicit cross-project issue list, or a
project issue/work-item collection URL with optional user-supplied filters and a
selected `en` or `ru` locale. A collection defaults to open issues. Output is one
localized stable collection summary and one stable detailed report per issue in
private XDG state.

## Workflow Stages

Resolve the bounded collection, collect GET-only GitLab evidence, reuse current
per-issue analysis when its issue and related-MR fingerprint is unchanged,
normalize each issue to `work-item/v1`, invoke the task-review quality contract,
assess the collection, ask one consolidated user-question round when the user may
supply missing context, persist immutable evidence and analysis, atomically
replace stable Markdown views, present, and report.

## Dependencies

Authenticated read access through `glab`, complete pagination for the declared
scope, and the bundled work-item, review, and GitLab triage contracts.

## Remote/Local Effects

Private content-addressed evidence and analysis are stored below XDG state with
stable summary and per-issue Markdown pointers. Output includes one manual
`glab` command per proposed action, backed by immutable request files and placed
beside its preview. The workflow never executes those commands or mutates GitLab.

## Errors, Partial, Escalation

Target failures are isolated per issue. Incomplete pagination, unavailable issue
or MR evidence, stale bindings, and unanswered business-priority questions make
the collection partial and remain explicit. Independent analysis continues
before one consolidated question round. Missing task facts that the user cannot
supply become role-authored GitLab question proposals rather than silent blockers.

## Unique Constraints

Every issue reports actuality, duplicate candidates, task-review quality verdict,
related issues, related MRs, linkage gaps, SemVer impact, severity, priority,
confidence, an autonomous planning decision, and release-milestone disposition.
Only semantically ready current work may be accepted. Every accepted item binds
the nearest compatible open milestone on its own project or component release
line; `none` and `not_applicable` impact require at least a patch release.
Deferred work has no milestone, while rejected, duplicate, and obsolete work is
removed from an active release milestone. The collection reports at most five
first tasks plus dependency and parallel-execution groups. Project-wide duplicate
search is bounded to each member's project; external projects are followed only
through explicit input or observed links.

Generated report prose follows the selected locale, while exact technical values
remain unchanged. Metadata proposals apply independently of planning acceptance.
Issue relationships use the issue-link API; MR relationships without a safe link
API use contextual messages. Information requests are derived only from actual
GitLab discussions by the authenticated user and advance strictly through a
question, two pings, and a final message plus separate closure proposal. Replies
are reassessed before advancing, and an insufficient reply begins a new cycle.

## Requirement

### REQ-F-125 - Triage a bounded GitLab issue collection

The skill shall accept one issue, an explicit cross-project issue list, or a
filtered project collection; default a collection to open issues; select an
`en` or `ru` output locale; and normalize each selected issue to `work-item/v1`.
It shall collect complete GET-only evidence, including the authenticated user and
observed related-MR discussions, reuse deep analysis only when its fingerprint is
current, apply the `task-review` quality contract, and persist private immutable
evidence and analysis with localized atomic stable Markdown views and retained
body-only content-addressed history. Each issue shall report
actuality, duplicates, quality, links, related merge requests, SemVer, severity,
priority, confidence, `accepted`/`deferred`/`rejected`/`duplicate`/`obsolete`
planning decision, release line, and milestone disposition. Accepted work shall
require a `ready` quality verdict and the nearest compatible open milestone;
`none` and `not_applicable` shall be treated as patch planning impact. Missing
milestones shall produce a manual creation proposal. Non-accepted work shall not
receive a new milestone, and rejected, duplicate, or obsolete work shall produce
a removal proposal when currently assigned. The collection shall
report dependencies, parallel work, and at most five first tasks. It shall ask
the user one consolidated round of material questions before drafting unresolved
questions for relevant GitLab participants. Every proposed title, description,
label set, milestone, issue link, message, and stale closure shall have a separate
manual command beside its preview, independent of the issue's planning decision
except for milestone assignment. Each mutation command shall record an advisory
post-success XDG marker and require target revalidation before retry. Information-request actions shall be derived
from actual GitLab notes and advance without skipped stages through a question,
two pings, and a final message plus separate issue-close command; any reply shall
be reassessed, and an insufficient reply shall start a new cycle. The stable
summary shall list detailed reports as plain absolute paths. Partial or stale
evidence shall remain explicit and shall not be reported as complete. The
workflow shall never execute generated commands or mutate GitLab.

## Example

`task-triage` reuses an unchanged issue analysis, recomputes collection-level
priority after another issue changes, and emits an updated stable summary without
executing its proposed GitLab commands.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
