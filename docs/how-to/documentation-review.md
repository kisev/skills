---
audience: maintainer
review: {"components": ["documentation-review"], "sources": ["shared/references/documentation*", "scripts/check_locales.py", "taskfile.yml", "skills/docs-prepare/references/workflow.md", "skills/docs-review/references/workflow.md", "skills/spec-manage/references/*"], "contracts": ["specs/requirements/functional/README.md"]}
---

# Keep Documentation in Step with Changes

[Русский](../ru/how-to/documentation-review.md)

## Choose the Right Step

An agreed specification defines the contract; source and tests show current
behavior. Correct code that violates a valid guarantee. Update stale descriptions
for confirmed product changes. Ask the owner when normative sources conflict.

For each behavior change, inspect affected specs, guides, examples, translations,
and navigation before completion. Use `spec-manage` with `spec-update` for the
canonical step and `docs-prepare` for the user-facing set. Their steps can share
one authorized task. Preserve prerequisites, limitations, failure consequences,
compatibility, recovery details, and rationale; moving a detail requires a link.

Use `docs-review` for user documentation and `spec-manage` with `spec-review`
for canonical specifications. The previous specification-check mode has been
removed without an alias. Scope and depth are separate from the word review:
a complete review requires an independent critic; a changed-area check can reuse evidence.

## Declare Useful Dependencies

Add a short `review` mapping to maintained documents when it helps select evidence:

```yaml
---
review: {"components": ["example"], "sources": ["src/example/**", "tests/test_example.py"], "contracts": ["specs/requirements/interfaces/README.md"]}
---
```

Replace example paths with existing workspace-relative paths or globs. Include
shared implementation and tests that can invalidate the document, not only the
closest source file. Keep metadata identical across translations. A document
without metadata still needs impact assessment; new unmapped files are not exempt.
Avoid manual hashes and verification dates: the runner records source digests.

```shell
task docs:check
task locale:check
```

These checks validate structure, declared dependencies, inventories, links, and
mirrors. They cannot establish semantic correctness or complete coverage.

## Reuse a Review

The installed `docs-review` and `spec-manage` skills bundle
`scripts/documentation_review.py`. Their workflows call `prepare` with the workspace,
scope, and host session identity, inspect the previous result, and finalize a
fresh report. No separate installation or OpenCode plugin is required.

- `full`: first baseline or an explicitly fresh full review; one independent critic.
- `incremental`: changed sources, affected documents, previous findings, and user decisions.
- `unchanged`: retained results and limits; no broad re-analysis merely because the skill ran again.

Private records live under `${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/documentation-review/`,
separated by workspace and scope. They retain file digests, findings, decisions,
checked and unchecked boundaries, and actual check results. They contain no source
bytes and must never contain copied credentials or private transcripts. A changed
snapshot blocks finalization; run preparation again and check the affected evidence.

The user may remove private review state; the next invocation establishes a full
baseline. A saved result is neither publication approval nor proof that every
possible defect was excluded. Accepted risks remain accepted until evidence or
the user's decision changes; an unchanged hash never closes an unchecked boundary.
