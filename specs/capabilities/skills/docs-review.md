---
review: {"components": ["documentation-review"], "sources": ["skills/docs-review/*", "skills/docs-review/references/*", "shared/references/documentation*", "tests/test_documentation_review.py"], "contracts": ["specs/requirements/functional/README.md"]}
---

# `docs-review`

## Purpose

Review user-facing Diataxis documentation for accuracy and usability.

## Triggers and Near-Misses

Trigger for docs review; near-miss: review of canonical `specs/`.

## Inputs and Outputs

Input is a document path or scope and compatible prior evidence. Output is
findings in chat and a private snapshot-bound result.

## Workflow Stages

Resolve scope, compare sources, inspect links and audience fit, verify language
mirrors and agent annotations, report findings.

## Dependencies

Documentation, source, tests, and links.

## Remote/Local Effects

Project reads and private workspace-scoped XDG review records; no project writes
or remote effects. The shared lifecycle is owned by REQ-F-519.

## Errors, Partial, Escalation

Missing source evidence is reported as a boundary, not guessed.

## Unique Constraints

Canonical specs are redirected to `spec-manage` in `spec-review` mode.

## Requirement

### REQ-F-108 - Keep documentation review read-only

The skill shall report documentation findings without changing repository files.
Without an explicit path or area it shall inspect the complete current project's
user-facing documentation set and name every unchecked boundary. Canonical specs
remain the responsibility of `spec-manage` in `spec-review` mode. Full reviews
require one independent critic; repeated reviews reuse compatible evidence.

#### Verification

Review a changed prerequisite and verify a finding identifies the failed user
step without editing the project. `tests/test_documentation_review.py` checks
retained evidence and explicit missing-critic limitations.

### REQ-F-518 - Verify language mirrors and agent annotations

The skill shall verify that the documentation language set matches its declared
resolution order, that machine tokens and agent annotations are byte-identical
across language mirrors, that agent hints still match actual commands and
behavior, and that executable contracts do not hide in user prose.

#### Verification

`scripts/check_locales.py` checks declared mirrors; review checks that translated
instructions preserve the same effects, prerequisites, and limitations.

## Example

`docs-review` stops and redirects when the requested path is under `specs/`.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
