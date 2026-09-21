# Canonical project specification

Maintain `specs/` as the shared source of truth for people and agents. Documents describe the agreed system state after merge and retain a compact lifecycle record for stable requirements and decisions; Git keeps the full edit history.

## Mode selection

Literal mode tokens remain supported but are optional. If the user explicitly
provides `spec-init`, `spec-onboard`, `spec-update`, or `spec-audit`, preserve that
mode and any explicit scope without reinterpretation, then enforce that mode's
safety preconditions. Otherwise select from intent and repository evidence:

- `spec-audit`: inspect, review, check, or compare canonical specs without changing them. A clearly read-only request always stays read-only.
- `spec-update`: change the agreed canonical target state in an existing `specs/` tree. Mentioning requirements or architecture is insufficient; the user must intend to change canonical specs.
- `spec-init`: create canonical specs for a genuinely greenfield project with no `specs/` and no meaningful implementation evidence.
- `spec-onboard`: describe an existing project that has no `specs/`, using repository evidence and confirmed intent.

Before choosing between `spec-init` and `spec-onboard`, inspect the available
repository for source code, tests, schemas, configuration, CLI/API surfaces, CI,
and deployment material. Absence of `specs/` alone never proves greenfield. When
several modes remain plausible after inspecting available facts, ask one short
question that names the alternatives and their different effects, then stop
without writing until the user answers.

Requests to implement behavior, prepare a plan or roadmap, or write user
documentation are near-misses even when they mention requirements or
architecture. Do not proceed to implementation after a specification workflow.

Read only the required resources under this skill's own root:

- always: `references/canonical-contract.md`, `references/requirements.md`, `references/architecture.md`, `references/interviewing.md`, and `references/validation.md`;
- for brownfield: `references/onboarding.md`;
- for ADR: `references/adr.md`;
- for `spec-update`: `references/consolidation.md`;
- for audit: `references/auditing.md`.
- when judging sufficient content depth: `references/content-states.md` and, only as a compact illustration, `references/minimal-example.md`.

Use `templates/` as normative content guidance. Use the example only to judge
minimum meaningful depth; it is not a second template. Do not copy example facts,
placeholders, or operational prompts into the final specification.

## Invariants

- The canonical structure contains all 19 minimum required `README.md` files from `templates/specs/`. Additional sections follow `references/canonical-contract.md`; every required viewpoint contains a project-specific confirmed fact, a concrete reason for inapplicability, or a user-accepted bounded `UNKNOWN` as defined in `references/content-states.md`.
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

In a full `spec-audit`, run snapshot validation before semantic review, mark it
mandatory, and include its result as formal evidence. In a focused audit, run it
only when the complete tree is available; otherwise report snapshot validation
as `not_checked` and state whether it is required by the focused scope.
Lifecycle remains `not_checked (not required)` unless the audit requires a
user-supplied complete baseline. Continue with `references/auditing.md`
regardless of a successful formal result because formal validation does not
assess meaning or drift.

## Dialogue and writing

Read `references/interaction-contract.md` and follow its lifecycle for ordinary bounded project-file edits.

Separate confirmed repository facts from human intent. When requirements, external behavior, architecture, compatibility, security, or quality are ambiguous, use the host's native interactive mechanism; if unavailable, ask in chat. Do not ask what is already confirmed.

In writing modes, prepare the complete file set in memory, validate every target under `specs/`, write it directly with atomic replacement or rollback, and report the resulting paths, diff summary, and actual checks. Do not create a private preview artifact or pause for confirmation before writing project files.

When selecting a durable design in writing modes, develop at least two materially different options, compare them against constraints, interfaces, failures, compatibility, security, observability, testability, migration, and rollback. Obtain the human's choice. Preserve architecturally significant alternatives and the outcome in an ADR.

## Modes

### `spec-init`

1. Verify that `specs/` is absent and inspect source code, tests, schemas, configuration, CLI/API, CI, and deployment evidence. Select this mode only when the project is truly greenfield. If meaningful implementation evidence exists, use `spec-onboard` unless the user explicitly supplied `spec-init`; for an explicit incompatible mode, stop and explain the failed precondition rather than reinterpreting it.
2. Obtain the user's explicit project-language choice before preparing files. Treat confirmed user decisions as normative and record the chosen canonical language in `specs/README.md`.
3. Conduct an adaptive interview using the areas in `references/interviewing.md`.
4. Prepare the complete `specs/` file set, create all 19 minimum files and any justified indexed extension with rollback if any write fails, then run snapshot validation and report lifecycle as `not_checked`.
5. Do not modify code or create an implementation plan.

### `spec-onboard`

1. Verify that `specs/` is absent and inspect source code, tests, schemas, configuration, CLI/API, CI, and deployment evidence. Existing meaningful implementation evidence distinguishes onboarding from initialization. If `specs/` exists, ask whether the user wants read-only `spec-audit` or target-state-changing `spec-update` unless intent already makes that distinction explicit.
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

This mode is completely read-only. Without an argument, formally validate and
inspect all `specs/`; with a path, `REQ-*`, `ADR-*`, or area, inspect the
specified object and related evidence and report formal validation as
`not_checked` when the complete tree is unavailable. Check the declared
canonical language while allowing the report to follow
`references/language-policy.md`. Follow `references/auditing.md`: use its atomic
drift units, ordered decision table, severity scale, independent-critic protocol,
aggregate precedence, and fixed conversational report order. A full audit
requires one independent critic over the same bounded evidence snapshot; a
focused audit requires one only when the user explicitly requests it. Critic
unavailability makes a required audit partial but does not discard confirmed
findings. Do not create reports, ADRs, temporary artifacts, or audit state, and
do not offer to apply fixes automatically.
