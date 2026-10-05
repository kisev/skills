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
assess the collection, ask dependency-bounded user-question rounds only for authority,
private context, or a bounded reversible technical choice, persist immutable
evidence and analysis, atomically
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
or MR evidence, stale bindings, and unanswered user questions make analysis
partial and remain explicit. Non-ready planning and prepared information requests
instead make follow-up pending, with counts and affected issues. Independent
analysis continues before the current independent question round. Dependent
follow-ups are rebuilt only after actual answers under
[REQ-I-001](../../requirements/interfaces/README.md#req-i-001---skill-interface).
Missing task facts
that the user cannot supply become role-authored GitLab question proposals rather
than silent blockers.

## Unique Constraints

Every issue reports actuality, duplicate candidates, task-review quality verdict,
related issues, related MRs, linkage gaps, SemVer impact, severity, priority,
confidence, an autonomous planning decision, and release-milestone disposition.
Each assessment also contains one primary agent recommendation with its rationale,
assumptions, confidence, alternatives, and reconsideration evidence.
Only semantically ready current work may be accepted. Every accepted item binds
the nearest compatible open milestone on its own project or component release
line unless observed evidence shows the team decided not to use milestones, in
which case the accepted item records milestone status `none` with that
rationale; `none` and `not_applicable` impact require at least a patch release.
Deferred work has no milestone, while rejected, duplicate, and obsolete work is
removed from an active release milestone. The collection reports at most five
first tasks plus dependency and parallel-execution groups. Every execution-plan
entry binds accepted collected evidence by digest and includes rationale; digests
are unique in top-five and across parallel groups. Project-wide duplicate
search is bounded to each member's project; external projects are followed only
through explicit input or observed links.

Generated report prose follows the selected locale, while exact technical values
remain unchanged. Metadata proposals apply independently of planning acceptance.
Issue relationships use the issue-link API; MR relationships without a safe link
API use contextual messages. Information requests are derived only from actual
GitLab discussions by the authenticated user and advance strictly through a
question, two pings, and one final message-then-close block. A provably
quiet-fixed issue takes the third closure path instead: the mandatory evidence
chain anchors the symptom with `git log -L <file>:<line>`, re-runs the
reproduction against the current trunk, searches the symptom in the repository
log, CHANGELOG, and merge requests, and requires the fixing commit to be
provably merged into the project's default branch through
`git merge-base --is-ancestor`; `close_fixed` binds no prior notes, and when
only the area was rebuilt the workflow publishes a separate "likely fixed"
confirmation message instead of closing. Replies
are reassessed before advancing, and an insufficient reply begins a new cycle.
The runner generates direct `glab api` commands with inline JSON heredoc bodies,
`#` explanations, and `&&` fail-fast blocks depending only on `glab`, `jq`, and
`sha256sum`; it never executes them. Every writing block starts with an
authenticated-user guard comparing `glab api ... user` with the collected
`current_user` snapshot. The first writing block of a task also compares the
target `updated_at` with the snapshot; every later block re-reads its target and
checks semantic preconditions: unchanged title, description, or labels, expected
status and milestone, a conversation whose non-system note digests still match
the snapshot without the prepared body, and absent links for a new relation.
A stage whose precondition cannot be precomputed is emitted as a regeneration
instruction instead of a command. Repeating a block stops on its own
preconditions because the first execution changed the observed state.
Equal-timestamp notes use numeric note-ID ordering; nonnumeric IDs
retain their API order.
Obsolete and duplicate issues receive one explanation-and-close block with
`state_event=close`; an explicit `close_fixed` request replaces that bare close
so the issue is never closed twice. Every close and every milestone block also
carries the existing-MR guard: one read-only glab search over open merge
requests referencing the issue stops the block before any write when a match
exists, so an open merge request is proposed instead of closing or assigning a
milestone. A missing milestone is one block that finds or creates the
milestone, extracts its ID with `jq`, and attaches the task. The stale closure
publishes the final message and closes the issue in one `&&` chain. A new
relation is created only after a links GET proves the target absent; a
conflicting relation type is replaced by one delete-then-create block that
re-verifies the observed link ID before deleting.
Every assessment explicitly supplies one structured `issue_relations` list,
including an empty list; legacy free-form relation fields are invalid. Every
relation is bound to an observed issue on the same GitLab host, including targets
returned by collected issue-link evidence. Missing relations and relation-type
replacements correspond exactly to proposed links; extra, duplicate, self,
existing, or unobserved proposals are invalid. A replacement uses guarded delete
and receipt-dependent create commands with fresh evidence checks.
In REST issue-link listings, the relationship identity is `issue_link_id`, not
the linked issue's `id`; an invalid explicit relationship ID fails closed.
Listing issue links returns one complete collection, not pages. Collection must
retain all links at CE's 100-link boundary without requesting a repeated second page;
this does not relax completeness checks for paged resources.
Unknown deletion is reconciled only when fresh evidence proves absence or the exact original link;
missing or unsupported observed link types fail closed. A relation also
produces a contextual comment only when a concrete
decision, constraint, or research result should be transferred. New information
requests prefer the most specific relevant observed discussion and may start a
standalone note only with an explicit reason. The authenticated user's authorship
is considered so the workflow never proposes asking that user to ask themselves.
The author of an observed related or closing MR is a valid fallback participant.
A non-null fallback binds that participant, an observed target, and a body to one
matching non-`none` information request and its manual publication command.

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
the user one consolidated round only for authority, private context, or bounded
technical choices between concrete, understood, reversible alternatives. Each
question shall link the issue, summarize its context, explain why the answer
changes planning, and include a reasoned recommendation with directly selectable
answers. Open-ended technical uncertainty shall become an agent recommendation or
research step. Priority questions use `authority`; questions about already-made
decisions use `private_context`. The authenticated user's observed authorship shall prevent a
proposal to ask that user to ask themselves. Before drafting unresolved questions
for relevant GitLab participants, the workflow shall prefer the most specific
relevant observed discussion and require an explicit reason for a standalone note.
Every item shall contain one primary recommendation with rationale, assumptions,
confidence, alternatives, and reconsideration evidence. Every structured issue
relation shall bind observed evidence, correspond exactly to any proposed link,
use one delete-then-create block that re-verifies the observed link for a
conflicting existing type, and
add a contextual comment only to transfer a concrete useful result. Every proposed title, description,
label set, milestone, issue link, message, and stale closure shall have one
guarded direct-command block beside its preview, independent of the issue's
planning decision except for milestone assignment. No generated command shall
record a local marker, reservation, or receipt; guards and their fresh reads
provide the replay protection, and the summary shall list every action without
a command together with its reason, leaving none after a complete analysis.
Information-request actions shall be derived
from actual GitLab notes and advance without skipped stages through a question,
two pings, and one final message-then-close block; a provably quiet-fixed issue
shall instead take `close_fixed` with the mandatory anchor, reproduction, and
`merge-base --is-ancestor` evidence chain recorded in its body, and an
unproven rebuilt area shall produce a "likely fixed" confirmation message
instead of a closure; any reply shall
be reassessed, and an insufficient reply shall start a new cycle. Every
generated writing block shall stop before any write when the authenticated user
differs from the snapshot, when the first block observes a changed
`updated_at`, when a later block's semantic precondition fails, or — for every
close and milestone block — when one read-only glab search finds an open merge
request already referencing the issue.
commands shall run under `python -I -S -B` before materialization while built
archives remain self-contained. The stable summary shall separate analysis
completeness from pending follow-up, group report links by planning decision,
subdivide accepted work by planning readiness, include a reason and next step per
issue, and report both active information-request and affected-issue counts. It
shall accept modern and legacy same-host evidence URLs, emit canonical modern URLs,
and escape untrusted Markdown titles in both summaries and per-issue reports. It
shall link unambiguous observed issue and merge-request references only when the
complete analyzed value is plain text; values containing Markdown, code, HTML,
URLs, any backslash, or reference-like syntax shall remain unchanged. Reference
numbers followed by a word character shall remain plain, and conflicting
`references.full` and `web_url` identities shall remain unresolved. Partial or stale evidence shall remain
explicit and shall not be reported as complete. The summary shall stay honest
about its evidence: it shall state fetched versus expected collection counts
with every collection error, quote ready actions verbatim, and give no priority
weight to authority-free signals such as +1 comments, emoji reactions, or
bot-set labels. The workflow shall never execute
generated commands or mutate GitLab. Source-layout commands shall run under
`python -I -S -B` before materialization while built archives remain
self-contained.

#### Verification

Triage tests cover collection completeness, retained item decisions, scoped
release planning, stale evidence, direct-command guards, block coverage, and
summary honesty: the quietly-fixed closure publishes its evidence and closes in
one block, refuses to abandon the agent's own unanswered question, requires a
standalone reason, replaces the bare obsolete close, and the existing-MR guard
search command precedes every close and milestone write. Final plans account
for each selected issue and never publish automatically.

## Example

`task-triage` reuses an unchanged issue analysis, recomputes collection-level
priority after another issue changes, and emits an updated stable summary without
executing its proposed GitLab commands.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
