# Canonical specification consolidation

Consolidation is a mandatory part of every `spec-update`, not a separate periodic project. Its purpose is to keep `specs/` a compact model of the current system that a person can read and hold in mind. Git retains history; canonical documents are not a change log.

## Scope

An ordinary `spec-update` checks affected documents, requirements, ADRs, and viewpoints impacted by the request. Do not expand scope unnecessarily.

An explicit request to consolidate the specification requires a native question: agree on a limited area or all `specs/`. Do not investigate or rewrite the full specification by default.

## Analysis

Before preview, check whether the affected area requires combining two normative formulations of one contract into one canonical point and replacing a duplicate with a reference; removing a withdrawn requirement, temporary implementation plan, or behavior no longer in the agreed target state; removing details that do not affect an observable contract or architectural invariant while retaining necessary causality and references; repairing a link to a removed path, stale `REQ-*`/`ADR-*`, or withdrawn interface; or replacing a changed architectural decision with a new ADR with explicit supersession rather than rewriting an accepted ADR.

Do not remove current non-scope, confirmed risk, compatibility boundary, or necessary explanation merely for brevity. Do not create an archive, version, changelog, plan, delta, or other durable workflow artifact inside `specs/`.

## Preview and confirmation

Before showing the diff, explicitly add either:

```text
Consolidation: required
Scope: requirements/interfaces/cli.md and architecture/06-runtime-view
Changes: remove superseded apply wording; retain ADR-0001 as history;
add one canonical reference.
```

or:

```text
Consolidation: not required
Scope: requirements/interfaces/cli.md
Reason: the requested contract is new and has no duplicate or superseded wording.
```

For `required`, the preview must contain both the substantive change and justified simplification edits. For `not required`, do not invent cleanup. In both cases, obtain confirmation of the exact diff first.

## Completion

After change in the checked area, no competing canonical documents exist for one interface or constraint, no withdrawn norm or duplicate formulation remains, and no link is broken. If evidence is insufficient, ask; do not remove text based on an assumption.
