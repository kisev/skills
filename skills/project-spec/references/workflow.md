# Canonical project specification

Maintain `specs/` as the shared source of truth for people and agents. Documents describe the agreed system state after merge; Git keeps history.

## Mode selection

The user must explicitly provide one mode: `spec-init`, `spec-onboard`, `spec-update`, or `spec-audit`. If no mode is provided, stop, briefly describe the four modes, and ask the user to choose. Do not guess the mode and do not proceed to implementation after the specification workflow.

Read only the required resources under this skill's own root:

- always: `references/requirements.md`, `references/architecture.md`, and `references/interviewing.md`;
- for brownfield: `references/onboarding.md`;
- for ADR: `references/adr.md`;
- for `spec-update`: `references/consolidation.md`;
- for audit: `references/auditing.md`.

Use `templates/` as content guidance. Do not copy placeholders or operational prompts into the final specification.

## Invariants

- The canonical structure contains all 19 required `README.md` files from `templates/specs/`. An empty or inapplicable section briefly explains why.
- Documents are compact, describe target state in present tense, and do not duplicate one fact in several viewpoints.
- Document prose uses the language of the latest user request; use English when that language is ambiguous. Do not translate identifiers, paths, stable `REQ-*` and `ADR-*` IDs, glossary terms, or widely accepted technical terms.
- Requirements and architecture are organized by knowledge type, not feature, milestone, or issue. The machine-readable contract remains the source of truth for syntax; Markdown records semantics, errors, compatibility, and invariants.
- Additional files are allowed only at semantic boundaries from the guidance. Create an ADR only for an architecturally significant decision.
- Do not create roadmap, archive, proposal, delta, tasks, plan, research, analysis, mapping, or other durable process artifacts.

## Dialogue and writing

Read `references/interaction-contract.md` and follow its lifecycle.

Separate confirmed repository facts from human intent. When requirements, external behavior, architecture, compatibility, security, or quality are ambiguous, use the host's native interactive mechanism; if unavailable, ask in chat. Do not ask what is already confirmed.

In writing modes, prepare a complete content-addressed private preview artifact with the exact diff of created or modified canonical documents. In chat, output only compact TLDR, scope, risks, checks, path, and SHA-256 digest; do not print the full diff. After confirmation of the exact mutation, apply the agreed change without new semantic changes and report the result and actual checks separately.

When selecting a durable design in writing modes, develop at least two materially different options, compare them against constraints, interfaces, failures, compatibility, security, observability, testability, migration, and rollback. Obtain the human's choice. Preserve architecturally significant alternatives and the outcome in an ADR.

## Modes

### `spec-init`

1. Verify that `specs/` is absent and the project is truly greenfield. If meaningful source code, tests, schemas, configuration, CLI/API, CI, or deployment already exist, stop and propose `spec-onboard`.
2. Conduct an adaptive interview using the areas in `references/interviewing.md`.
3. Prepare a preview of the complete `specs/`, present a compact summary, obtain confirmation, and create all 19 files.
4. Do not modify code or create an implementation plan.

### `spec-onboard`

1. Verify that `specs/` is absent. Otherwise propose `spec-update` or `spec-audit`.
2. Investigate repository evidence according to `references/onboarding.md` before asking questions.
3. Classify individual claims as `KNOWN`, `AMBIGUOUS`, `UNKNOWN`, or `CONFLICT`. Do not present current code behavior as a supported contract.
4. After the interview, show a preview and create only canonical `specs/` and necessary ADRs.

### `spec-update`

1. Verify that `specs/` exists, read the affected area, and agree on the desired change.
2. Before design, mandatory perform the analysis in `references/consolidation.md`. Explicitly include `Consolidation: required` with precise simplifications or `Consolidation: not required` with a reason in the preview.
3. Agree on an unambiguous target state. A new material requirement receives a new ID; do not renumber or reuse existing IDs.
4. After confirmation, modify only `specs/`, including ADRs within `specs/architecture/09-architecture-decisions/`.

### `spec-audit`

This mode is completely read-only. Without an argument, inspect all `specs/`; with a path, `REQ-*`, `ADR-*`, or area, inspect the specified object and related evidence. Follow `references/auditing.md`: report ranked quality findings first, then drift statuses and unchecked boundaries. Do not create reports, ADRs, or temporary artifacts, and do not offer to apply fixes automatically.
