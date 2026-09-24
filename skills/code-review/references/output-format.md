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

Keep the chat result compact. `report-review` owns the labels and layout; print
its `chat` field verbatim rather than composing the result manually. A missing,
incomplete, or stale contract-6 plan produces only a localized blocked report
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
- **Publication plan:** `<absolute path>/review-publication.md`
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
check tables in chat. Put them in `review-publication.md`.

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

The stable `review-publication.md` is a compact human review document. Its header
shows `code-review: <skill version> · contract: <version>`, then contains:

1. Target, role, verdict, and the manual-only warning.
2. Compact MR metadata without a repeated labels recommendation.
3. A project-label section beside metadata with only add/remove delta and its
   command. Keep current labels, unresolved labels, and exhaustive assessment in
   private JSON.
4. A compact previous-finding table with ID, previous status, current status,
   rationale, and action.
5. Open-thread actions.
6. Closed-thread actions.
7. Read-only local fixes for author mode.
8. New reviewer findings and their line or general discussion actions.
9. Non-blocking recommended issues for confirmed out-of-scope problems.
10. Threads reviewed without publication.
11. Architecture, SemVer, and checks.
12. No separate manual-publication section: each command stays beside its item.

For every actionable item, show its natural conclusion, publication preview,
suggestion or patch when applicable, and directly runnable command. Do not show
`fix_mode`, action IDs, operations, body paths, digests, raw positions, or a
separate artifact copy of a patch. Those bindings remain in private JSON.

The model supplies semantic assessment prose, natural role-authored publication
bodies, template selections, and exhaustive label-applicability rationales. The
runner owns standard localized presentation labels, observed label descriptions,
paths, exact GitLab identity, body files, direct commands, and chat rendering.
Do not hand-edit generated commands or final chat.

The publication plan is a manual checklist, not a publication protocol. Each
publishable item has a body file and a directly runnable `glab` command. For an
incremental review, determine whether content is already published from actual
GitLab discussions, notes, and issues authored by the current `glab` user and a
semantic comparison of the content. Never infer publication from local state,
receipts, a command that was previously shown, or the advisory marker recording
that the exact command exited zero. Use that marker only to require remote
revalidation before deciding whether a retry is needed.

Severity and internal review bookkeeping must not appear in publication bodies.
Published prose is concise without losing the evidence or required action. Apply
the `humanize` skill before drafting it and do not use `;` outside code,
commands, or exact quotations. It
starts with the answer, correction, or concrete fix, speaks as the authenticated
user, and continues the complete existing conversation naturally instead of
restating it. A fix
on an applicable current new-line position contains exactly one single-line or
bounded multi-line `suggestion`; general, deleted, outdated, non-contiguous, and
otherwise unanchorable fixes contain the exact validated unified patch inside one
copy-ready `sh` block using `git apply <<'PATCH'`. A body intended for GitLab must
not contain a local checkout path, interpreter path, runtime helper, or local
marker command. The same patch is available as
an immutable local `.patch` artifact for manual use. A thread-state command is
shown separately after the command that publishes its explanation.
