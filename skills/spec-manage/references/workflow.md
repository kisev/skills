# Canonical project specification

Maintain `specs/` as the shared source of truth for people and agents. Documents describe the agreed system state after merge and retain a compact lifecycle record for stable requirements and decisions; Git keeps the full edit history.

## Mode selection

The user must explicitly provide one mode: `spec-init`, `spec-onboard`, `spec-update`, or `spec-audit`. If no mode is provided, stop, briefly describe the four modes, and ask the user to choose. Do not guess the mode and do not proceed to implementation after the specification workflow.

Read only the required resources under this skill's own root:

- always: `references/canonical-contract.md`, `references/requirements.md`, `references/architecture.md`, `references/interviewing.md`, and `references/validation.md`;
- for brownfield: `references/onboarding.md`;
- for ADR: `references/adr.md`;
- for `spec-update`: `references/consolidation.md`;
- for audit: `references/auditing.md`.

Use `templates/` as content guidance. Do not copy placeholders or operational prompts into the final specification.

## Invariants

- The canonical structure contains all 19 minimum required `README.md` files from `templates/specs/`. Additional sections follow `references/canonical-contract.md`; an empty or inapplicable minimum section briefly explains why.
- Documents are compact, describe target state in present tense, and do not duplicate one fact in several viewpoints.
- Canonical prose uses the single language declared in `specs/README.md`; conversation and reports independently follow `references/language-policy.md`. Resolve legacy trees and language changes only as specified in `references/canonical-contract.md`.
- Requirements and architecture are organized by knowledge type, not feature, milestone, or issue. The machine-readable contract remains the source of truth for syntax; Markdown records semantics, errors, compatibility, and invariants.
- The authority of user decisions, explicit contracts, canonical specs, and repository behavior is mode-specific as defined in `references/canonical-contract.md`; never resolve a conflict by implicit source priority.
- Additional files are allowed only at indexed, non-duplicating canonical semantic boundaries from the guidance. Create an ADR only for an architecturally significant decision.
- Stable `REQ-*` and `ADR-*` namespaces are append-only. New numbers are greater than every number previously assigned in the namespace; never fill a gap, renumber an entry, reuse an ID, or delete its compact lifecycle record.
- Do not create roadmap, archive, proposal, delta, tasks, plan, research, analysis, mapping, or other durable process artifacts.
- Run the bundled read-only validator for mechanically provable invariants. A successful formal result does not establish semantic quality, declared-language compliance of prose, or repository correspondence and never replaces `spec-audit`.

## Formal validation

Run snapshot validation after preparing a complete tree and before reporting success:

```sh
python3 -I -S -B scripts/spec_validate.py check --path <specs>
```

For `spec-init` and `spec-onboard`, report lifecycle as `not_checked`: there is no prior canonical baseline. For `spec-update`, retain the complete pre-change `specs/` as an explicit bounded baseline, validate both snapshots independently, and run:

```sh
python3 -I -S -B scripts/spec_validate.py lifecycle \
  --baseline <previous-specs> \
  --candidate <current-specs>
```

Do not substitute Git history or an inferred baseline. If no complete explicit baseline is available, report lifecycle as `not_checked`; never claim append-only lifecycle compliance from `check` alone. An input or execution error is not a validation finding and blocks a successful completion report.

In a full `spec-audit`, run snapshot validation before semantic review and include its result as formal evidence. In a focused audit, run it only when the complete tree is available; otherwise report snapshot validation as `not_checked`. Lifecycle remains `not_checked` unless the user explicitly supplies a complete baseline. Continue with `references/auditing.md` regardless of a successful formal result because formal validation does not assess meaning or drift.

## Dialogue and writing

Read `references/interaction-contract.md` and follow its lifecycle for ordinary bounded project-file edits.

Separate confirmed repository facts from human intent. When requirements, external behavior, architecture, compatibility, security, or quality are ambiguous, use the host's native interactive mechanism; if unavailable, ask in chat. Do not ask what is already confirmed.

In writing modes, prepare the complete file set in memory, validate every target under `specs/`, write it directly with atomic replacement or rollback, and report the resulting paths, diff summary, and actual checks. Do not create a private preview artifact or pause for confirmation before writing project files.

When selecting a durable design in writing modes, develop at least two materially different options, compare them against constraints, interfaces, failures, compatibility, security, observability, testability, migration, and rollback. Obtain the human's choice. Preserve architecturally significant alternatives and the outcome in an ADR.

## Modes

### `spec-init`

1. Verify that `specs/` is absent and the project is truly greenfield. If meaningful source code, tests, schemas, configuration, CLI/API, CI, or deployment already exist, stop and propose `spec-onboard`.
2. Obtain the user's explicit project-language choice before preparing files. Treat confirmed user decisions as normative and record the chosen canonical language in `specs/README.md`.
3. Conduct an adaptive interview using the areas in `references/interviewing.md`.
4. Prepare the complete `specs/` file set, create all 19 minimum files and any justified indexed extension with rollback if any write fails, then run snapshot validation and report lifecycle as `not_checked`.
5. Do not modify code or create an implementation plan.

### `spec-onboard`

1. Verify that `specs/` is absent. Otherwise propose `spec-update` or `spec-audit`.
2. Investigate repository evidence according to `references/onboarding.md` before asking questions.
3. Obtain the user's explicit project-language choice before preparing files and record it in `specs/README.md`.
4. Classify individual claims as `KNOWN`, `AMBIGUOUS`, `UNKNOWN`, or `CONFLICT`. Explicit contract sources and confirmed decisions are normative; code and tests prove only current behavior.
5. After the interview, create only canonical `specs/` and necessary ADRs, using atomic replacement or rollback for the complete file set, then run snapshot validation and report lifecycle as `not_checked`.

### `spec-update`

1. Verify that `specs/` exists, resolve and preserve its canonical language according to `references/canonical-contract.md`, read the affected area, and agree on the desired change. Never select the canonical language from the current request.
2. Before design, mandatory perform the analysis in `references/consolidation.md`. Report `Consolidation: required` with precise simplifications or `Consolidation: not required` with a reason after the edit.
3. Agree on an unambiguous target state. A new material requirement receives a number above the historical maximum for its namespace. Retain withdrawn and superseded entries as compact lifecycle records according to `references/requirements.md` and `references/adr.md`.
4. Preserve an explicit complete baseline, modify only `specs/`, including ADRs within `specs/architecture/09-architecture-decisions/`, then run snapshot validation for the candidate and lifecycle validation against that baseline before reporting the resulting changes.

### `spec-audit`

This mode is completely read-only. Without an argument, formally validate and inspect all `specs/`; with a path, `REQ-*`, `ADR-*`, or area, inspect the specified object and related evidence and report formal validation as `not_checked` when the complete tree is unavailable. Check the declared canonical language while allowing the report to follow `references/language-policy.md`. Follow `references/auditing.md`: report ranked quality findings first, then drift statuses and unchecked boundaries. Do not create reports, ADRs, or temporary artifacts, and do not offer to apply fixes automatically.
