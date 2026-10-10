# Review output format

Select the response language in this order: explicit user request, applicable agent instructions, established user prose in the session, then English when the session holds only the skill invocation and a target. The selected response language applies to chat, headings, status text, publication bodies, and recommended issues. Write every GitLab publication from the authenticated user's factual role, address another participant with informal second-person singular, never fabricate first-person actions or force a pronoun, and keep code, IDs, paths, API fields, and commands unchanged.

## Chat

Local WIP: use the `local-review.md` report format; runner-rendered chat and publication-plan rules below apply to GitLab MRs. Keep chat compact: `finish-review` and, for an existing finalized plan, `report-review` own labels and layout; print their `chat` field verbatim, not composed manually. A missing, incomplete, or stale plan yields only a localized blocked report: failed stage and safe next action (`next_action=null` when the evidence artifact itself is unavailable).

```markdown
### MR assessment

- **Role:** \<reviewer of another author's MR / author of this MR>
- **Necessity:** \<supported / doubtful / unconfirmed> - <why>
- **Relevance:** \<current / partly outdated / outdated> - <why>
- **Change:** <two to four sentences about behavior before and after>
- **Architecture:** <short assessment of ownership and project fit>
- **MR contribution / label:** \<MAJOR / MINOR / PATCH / none / not applicable> - <why>
- **SemVer basis:** `<last published release>` → `<target branch>` + MR
- **Next release:** \<MAJOR / MINOR / PATCH / none / not applicable> - <why>
- **Release policy:** <evidence-based policy and relevant release line>
- **MR metadata:** \<ready / changes needed / context needed>
- **Verdict:** \<ready to merge / changes required / owner decision required>
- **Review checkout:** `<absolute path>`
- **Publication plan:** `<absolute path>/runbook.md`

```

Without an established release basis, show **SemVer: target-branch fallback** with the named branch and reason; the MR contribution still drives the label (`semver.md`).

Never print raw release, target, base, start, or head SHAs — exact refs stay in private JSON — and never use a `file://` link for a local artifact; blob and commit links may stay pinned to immutable revisions, with visible path, line, or description text.

For another author's MR, do not expose finding titles, severities, locations, evidence, thread contents, proposed responses, fixes, commands, or detailed check tables in chat; put them in `runbook.md`.

For the user's own MR, append a concise local-fix list; each actionable fix has one validated Git patch in the private plan, applied manually by the user or handed to an implementation session. Never create review threads for author findings or edit the checkout.

```markdown
### Local fixes

1. `<path>:<line>` - <problem and consequence>. <one concrete fix>.
```

State explicitly in the assessment when there are no findings; if the MR did not change after the baseline, report it briefly and complete the fresh discussion audit without a critic.

## Publication plan

Stable `runbook.md` is a compact human review document. Header: `code-review: <skill version> · contract: <version>`, then:

1. Target, role, concise verdict + reason, technical and process blockers, architecture, SemVer, manual-only warning; the summary derives from the same effective findings and verdict, not an independently edited verdict.
2. Compact MR metadata, no repeated labels recommendation.
3. Panel review: review-panel section — each critic and the arbitrator with recorded name, profile, provider, model; private to the runbook, never to published GitLab texts.
4. Project-label section beside metadata: only add/remove delta and its command. Keep current labels, unresolved labels, and exhaustive assessment in
   private JSON.
5. Previous-finding table when explicitly included as context: short finding name, localized result, short next action; one row per finding, no long rationale or internal ID.
6. Open-thread actions, closed-thread actions, read-only local fixes for author mode.
7. Current reviewer findings and actions, including repeated problems confirmed on this snapshot; advisory history needs no separate action. Panel findings show who raised them and which duplicates the arbitrator merged in, losing no author or opinion difference.
8. Panel review: arbitration-verdicts section — every critic finding with its verdict (accepted, accepted with severity override, duplicate of its canonical finding, or refuted), the arbitrator's reason, and the arbitrator's merged findings. Every detected candidate stays visible, including refuted and disputed ones.
9. Concise non-blocking follow-up proposals: problem and proof, solution, importance, postponement risk, why outside the MR, existing task if known. No issue templates or issue-creation commands; full preparation is separate.
10. Threads reviewed without publication, and checks; architecture and SemVer already appear at the start. No empty sections or separate manual-publication section: each command stays beside its item.

Each actionable item shows its natural conclusion, publication preview, suggestion or patch when applicable, and directly runnable command. Do not show `fix_mode`, action IDs, operations, body paths, digests, raw positions, or a second rendered copy of a patch; those bindings and validation results stay in private JSON.

The model supplies assessment prose, role-authored publication bodies, follow-up proposals, and label rationales; the runner owns localized labels, observed descriptions, paths, exact identity, body files, direct commands, and chat rendering — never hand-edit generated commands or final chat.

The plan presents one direct `glab` command per remote action, beside its exact body preview; follow `references/publication.md` for execution and recovery. For incremental review, compare current GitLab discussions, notes, and issues with the finding's meaning; historical receipts or advisory markers do not replace fresh semantic assessment, authorize changed content, or justify automatic retry.

Severity and internal review bookkeeping must not appear in publication bodies. Published prose stays concise, keeping evidence and required action. Apply the `humanize` skill before drafting it and do not use `;` outside code, commands, or exact quotations. It starts with the answer, correction, or concrete fix, speaks as the authenticated user, and continues the complete existing conversation naturally, not restating it. One finding may own multiple safely separable positioned suggestions. Patches require a specific fallback reason, not merely a general comment position. The runner wraps a separate validated unified patch in one copy-ready `sh` block using `git apply <<'PATCH'`; the model never embeds it in the input body. Outer Markdown fences must accommodate fences inside the patch. A body intended for GitLab must not contain a local checkout path, interpreter path, runtime helper, or local marker command; the same patch is also an immutable local `.patch` artifact for manual use. Show every concrete `patch_reason` before its patch, including thread replies. Findings and accepted thread defects show severity and merge impact; other discussions, the check result. Every `no_publication` shows its reason. A reply and its resolve/reopen share one `shell` block: `#` before each command, `&&` so state changes only after successful publication. For plain comments, use the actual returned discussion ID and resolvability: close completed discussions only, never questions or unresolved defects.
