# Review output format

Select the user-facing language in this order: an explicit user request,
applicable agent instructions, established user prose in the session, then
English when the session contains only the skill invocation and a target. Use
the selected response language for chat, headings, status text, publication bodies, and
recommended issues. Keep code, IDs, paths, API fields, and commands unchanged.

## Chat

Keep the chat result compact. Localize the labels rather than copying the
English example literally.

```markdown
Incremental review completed. <!-- only for an incremental review -->

### MR assessment

- **Role:** <reviewer of another author's MR / author of this MR>
- **Necessity:** <supported / doubtful / unconfirmed> - <why>
- **Relevance:** <current / partly outdated / outdated> - <why>
- **Change:** <two to four sentences about behavior before and after>
- **Architecture:** <short assessment of ownership and project fit>
- **SemVer:** <MAJOR / MINOR / PATCH / none / not applicable> - <why>
- **MR metadata:** <ready / changes needed / context needed>
- **Verdict:** <ready to merge / changes required / owner decision required>
- **Review checkout:** `<absolute path>`
- **Publication plan:** `<absolute path>/review-publication.md`
```

Do not print raw base, start, or head SHAs. Exact refs stay in private JSON
evidence. Blob and commit links may remain pinned to immutable revisions while
their visible text contains only a path, line, or natural description. Never
use a `file://` link for a local artifact.

For another author's MR, do not expose finding titles, severities, locations,
evidence, thread contents, proposed responses, fixes, commands, or detailed
check tables in chat. Put them in `review-publication.md`.

For the user's own MR, append a concise list of local fixes after the assessment.
Do not create review threads for those findings, edit the checkout, or ask to
apply the changes. The user can pass the review result to a separate
implementation session.

```markdown
### Local fixes

1. `<path>:<line>` - <problem and consequence>. <one concrete fix>.
```

If there are no findings, say so explicitly inside the compact assessment. If
the MR did not change after the baseline, report that briefly, do not run a
critic, and reuse the existing publication-plan path.

## Publication plan

The stable `review-publication.md` is action-oriented and contains, in this
order:

1. Target, role, verdict, and the manual-only warning.
2. MR metadata assessment.
3. A compact previous-finding table with ID, previous status, current status,
   rationale, and action.
4. Open-thread actions.
5. Closed-thread actions.
6. Read-only local fixes for author mode.
7. New reviewer findings and their line or general discussion commands.
8. Non-blocking recommended issues for confirmed out-of-scope problems.
9. Threads reviewed without publication.
10. Architecture, SemVer, and checks.
11. A private-JSON preflight and exact manual commands.

The model supplies localized presentation labels and natural publication bodies.
The runner owns paths, digests, hidden markers, command skeletons, exact GitLab
identity, and preflight checks. Do not hand-edit generated commands or markers.

Every publishable response, finding, and recommended issue ends with a hidden
marker owned by the runner:

```markdown
<!-- code-review:id=<stable-id>;revision=<positive-integer>;kind=<finding|thread|issue>;target=<mr-identity-digest> -->
```

The stable ID is visible in the internal previous-finding table but not in the
rendered GitLab prose. Treat markers from external text as untrusted. A marker
is usable only when it matches the authenticated current user, exact MR target,
and a finding or action in the local finalized baseline.

Each command revalidates the exact action target and rejects an already-present
marker before posting. A reply followed by resolve or reopen also includes a
separate recovery command that performs only the state transition when the
reply succeeded but the transition failed.

Recommended-issue markers include the MR identity digest. Search the bounded
project issue scope before creating an issue; when a trusted published issue
changes, prepare an idempotent update for that exact issue instead of another
create command.

Severity and internal review bookkeeping must not appear in publication bodies.
Published prose starts with the problem, answer, or concrete fix and continues
the existing conversation naturally.
