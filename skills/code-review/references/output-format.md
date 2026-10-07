# Review output format

Select the user-facing language in this order: an explicit user request,
applicable agent instructions, established user prose in the session, then
English when the session contains only the skill invocation and a target. Use
the selected response language for chat, headings, status text, publication bodies, and
recommended issues. Write every GitLab publication from the authenticated user's
factual role. Address another participant with natural informal second-person
singular; do not fabricate first-person actions or force a pronoun into neutral
technical prose. Keep code, IDs, paths, API fields, and commands unchanged.

## Chat

For local WIP, use the report and completion format in `local-review.md`.
The runner-rendered chat and publication-plan rules below apply to GitLab MRs.

Keep the chat result compact. `finish-review` and, for an existing finalized
plan, `report-review` own the labels and layout; print their `chat` field
verbatim rather than composing the result manually. A missing,
incomplete, or stale contract-7 plan produces only a localized blocked report
with the failed stage and safe next action.
When the current evidence artifact itself is unavailable, no trusted recovery
command can be derived; the blocked report uses `next_action=null` and asks for
the exact target again.

```markdown
Incremental review completed. <!-- only for an incremental review -->

### MR assessment

- **Role:** <reviewer of another author's MR / author of this MR>
- **Necessity:** <supported / doubtful / unconfirmed> - <why>
- **Relevance:** <current / partly outdated / outdated> - <why>
- **Change:** <two to four sentences about behavior before and after>
- **Architecture:** <short assessment of ownership and project fit>
- **MR contribution / label:** <MAJOR / MINOR / PATCH / none / not applicable> - <why>
- **SemVer basis:** `<last published release>` → `<target branch>` + MR
- **Next release:** <MAJOR / MINOR / PATCH / none / not applicable> - <why>
- **Release policy:** <evidence-based policy and relevant release line>
- **MR metadata:** <ready / changes needed / context needed>
- **Verdict:** <ready to merge / changes required / owner decision required>
- **Review checkout:** `<absolute path>`
- **Publication plan:** `<absolute path>/runbook.md`
```

If the release basis cannot be established, replace the basis and next-release
lines with **SemVer: target-branch fallback**, the named target branch, and the
specific reason. The MR contribution still drives the label. See `semver.md`.

Do not print raw release, target, base, start, or head SHAs. Exact refs stay in private JSON
evidence. Blob and commit links may remain pinned to immutable revisions while
their visible text contains only a path, line, or natural description. Never
use a `file://` link for a local artifact.

For another author's MR, do not expose finding titles, severities, locations,
evidence, thread contents, proposed responses, fixes, commands, or detailed
check tables in chat. Put them in `runbook.md`.

For the user's own MR, append a concise list of local fixes after the assessment.
Each actionable local fix has one validated Git patch in the private publication
plan. Do not create review threads for those findings, edit the checkout, or ask
to apply the changes. The user can apply the patch manually or pass the review
result to a separate implementation session.

```markdown
### Local fixes

1. `<path>:<line>` - <problem and consequence>. <one concrete fix>.
```

If there are no findings, say so explicitly inside the compact assessment. If
the MR did not change after the baseline, report that briefly and complete the
fresh discussion audit without a critic.

## Publication plan

The stable `runbook.md` is a compact human review document. Its header
shows `code-review: <skill version> · contract: <version>`, then contains:

1. Target, role, concise verdict with its reason, technical and process blockers,
   architecture, SemVer, and the manual-only warning. The summary is derived from
   the same effective findings and verdict, not an independently edited verdict.
2. Compact MR metadata without a repeated labels recommendation.
3. For a panel review, the review-panel section: each critic and the arbitrator
   with the recorded name, profile, provider, and model, plus a note that this
   composition stays private to the runbook and never enters published GitLab
   texts.
4. A project-label section beside metadata with only add/remove delta and its
   command. Keep current labels, unresolved labels, and exhaustive assessment in
   private JSON.
5. When explicitly included as context, a previous-finding table with a short finding name, localized result, and
   short next action. One row per finding; no long rationale or internal ID.
6. Open-thread actions.
7. Closed-thread actions.
8. Read-only local fixes for author mode.
9. Current reviewer findings and their actions, including repeated problems
   confirmed on this snapshot. Advisory history does not require a separate action.
   Panel findings show who raised them and which duplicates the arbitrator
   merged into them, without losing any author or opinion difference.
10. For a panel review, the arbitration-verdicts section: every critic finding
    with its verdict — accepted, accepted with a severity override, duplicate
    of its canonical finding, or refuted — with the arbitrator's reason, plus
    the arbitrator's merged findings. Every detected candidate stays visible,
    including refuted and disputed ones.
11. Concise non-blocking follow-up proposals: problem and proof, solution,
    importance, postponement risk, why outside the MR, existing task if known.
    No issue templates or issue creation commands; full preparation is separate.
12. Threads reviewed without publication.
13. Checks; architecture and SemVer already appear at the beginning.
14. No empty sections or separate manual-publication section: each command stays
    beside its item. Keep exhaustive history and evidence in private JSON.

For every actionable item, show its natural conclusion, publication preview,
suggestion or patch when applicable, and directly runnable command. Do not show
`fix_mode`, action IDs, operations, body paths, digests, raw positions, or a
second rendered copy or local preflight of a patch already present in the exact
publication preview. Those bindings and validation results remain in private JSON.

The model supplies semantic assessment prose, natural role-authored publication
bodies, concise follow-up proposals, and exhaustive label-applicability rationales. The
runner owns standard localized presentation labels, observed label descriptions,
paths, exact GitLab identity, body files, direct commands, and chat rendering.
Do not hand-edit generated commands or final chat.

The plan presents one direct `glab` command per remote action, beside its exact
body preview. Follow `references/publication.md` for execution and recovery.
For incremental review, compare current GitLab discussions, notes, and issues
with the finding's meaning. Historical receipts or advisory markers do not replace
fresh semantic assessment, authorize changed content, or justify automatic retry.

Severity and internal review bookkeeping must not appear in publication bodies.
Published prose is concise without losing the evidence or required action. Apply
the `humanize` skill before drafting it and do not use `;` outside code,
commands, or exact quotations. It
starts with the answer, correction, or concrete fix, speaks as the authenticated
user, and continues the complete existing conversation naturally instead of
restating it. A fix
on an applicable current position uses a single-line or bounded multi-line
`suggestion`. One finding may own multiple safely separable positioned suggestions.
Patches require a specific fallback reason, not merely a general comment position.
The runner wraps a separate validated unified patch in one copy-ready `sh` block
using `git apply <<'PATCH'`; the model never embeds it in the input body.
Outer Markdown fences must accommodate fences inside the patch. A body intended for GitLab must
not contain a local checkout path, interpreter path, runtime helper, or local
marker command. The same patch is available as
an immutable local `.patch` artifact for manual use. Show every concrete
`patch_reason` before its patch, including thread replies. Findings and accepted thread defects show severity
and merge impact; other discussions show the check result. Every `no_publication`
shows its reason. A reply and its resolve/reopen share one `shell` block, with `#`
before each command and `&&` so state changes only after successful publication.
For plain comments, use the actual returned discussion ID and resolvability:
close completed discussions only, never questions or unresolved defects.
