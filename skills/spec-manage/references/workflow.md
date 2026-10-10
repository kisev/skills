# Canonical project specification

Documents describe the agreed post-merge state and keep a compact lifecycle record for stable requirements and decisions.

## Activation

This skill owns its post-change trigger itself; project instruction files are not required to obtain it. After an authorized change altering material behavior, compatibility, or a security boundary, perform the affected canonical step yourself in `spec-update` mode when `specs/` exists, within the same change authorization. The trigger never creates a missing `specs/` tree: `spec-init` and `spec-onboard` stay user-initiated; an explicit user request for any mode always takes precedence.

## Mode selection

Literal mode tokens remain supported but are optional. An explicit `spec-init`, `spec-onboard`, `spec-update`, or `spec-review` is preserved with its explicit scope, uninterpreted, safety preconditions enforced; otherwise select from intent and repository evidence. Only these four explicit `spec-*` modes are supported; reject other explicit mode tokens rather than reading a removed name as a natural-language alias:

- `spec-review`: inspect, review, check, or compare canonical specs without changing them; a clearly read-only request never authorizes project edits. Private review state follows `references/documentation-review.md`.
- `spec-update`: change the agreed canonical target state in an existing `specs/` tree, including an authorized behavior change's specification step. Mere architecture mention is insufficient; do not invent a new product decision.
- `spec-init`: create canonical specs for a genuinely greenfield project with no `specs/` and no meaningful implementation evidence.
- `spec-onboard`: describe an existing project that has no `specs/`, using repository evidence and confirmed intent.

Before choosing between `spec-init` and `spec-onboard`, inspect source code, tests, schemas, configuration, CLI/API, CI, and deployment material. Absence of `specs/` alone never proves greenfield. If several modes stay plausible, ask one short question naming the alternatives and their different effects, then stop without writing until the user answers.

Implementation workflows may call this skill for their affected canonical step, then resume their authorization; this skill edits only `specs/`. Plans, roadmaps, and user documentation are not canonical work; apply `references/documentation-review.md` to impact selection and review reuse.

Enter a stage, read its files; never the whole set up front:

| Stage or mode | Files |
| - | - |
| Every mode: language authority, tree structure | `references/canonical-contract.md` |
| Interview (spec-init, spec-onboard) | `references/interviewing.md` |
| Brownfield investigation (spec-onboard) | `references/onboarding.md` |
| Requirements, architecture viewpoints, ADRs | `references/requirements.md`, `references/architecture.md`, `references/adr.md` |
| Pre-change consolidation (spec-update) | `references/consolidation.md` |
| Judging sufficient content depth | `references/content-states.md`; `references/minimal-example.md` only as a compact illustration |
| Validation before reporting success | `references/validation.md` |
| Audit (spec-review) | `references/auditing.md` |

Use `templates/` as normative content guidance, the example only to judge minimum meaningful depth; never copy its facts, placeholders, or operational prompts into the specification.

## Invariants

- The canonical structure contains all 19 minimum required `README.md` files from `templates/specs/`; extra sections follow `references/canonical-contract.md`. Each required viewpoint holds a project-specific confirmed fact, a concrete inapplicability reason, or a user-accepted bounded `UNKNOWN` (`references/content-states.md`).
- Documents are compact, present-tense target state, and never state one fact in several viewpoints.
- Canonical prose uses the one language declared in `specs/README.md`; conversation and reports follow `references/language-policy.md` independently; legacy trees and language changes resolve only per `references/canonical-contract.md`.
- Requirements and architecture are organized by knowledge type, not feature, milestone, or issue; the machine-readable contract is the syntax source of truth; Markdown records semantics, errors, compatibility, invariants.
- User decisions, explicit contracts, canonical specs, and repository behavior carry mode-specific authority per `references/canonical-contract.md`; never resolve conflicts by implicit source priority.
- Extra files sit only at indexed, non-duplicating canonical semantic boundaries from the guidance; an ADR covers only an architecturally significant decision.
- Stable `REQ-*` and `ADR-*` namespaces are append-only: new numbers exceed every previously assigned number; never fill a gap, renumber, reuse an ID, or delete a compact lifecycle record.
- No roadmap, archive, proposal, delta, tasks, plan, research, analysis, mapping, or other process artifacts in the canonical tree; private review evidence follows the shared review contract outside the checkout.
- Run the bundled read-only validator for mechanically provable invariants; a pass establishes neither semantic quality, declared-language prose compliance, nor repository correspondence, and never replaces `spec-review`.

## Formal validation

Run snapshot validation on the complete tree before reporting success:

```sh
python3 -I -S -B scripts/spec_validate.py check --path <specs>
```

For `spec-init` and `spec-onboard`, report lifecycle as `not_checked`. For `spec-update`, keep the complete pre-change `specs/` as an explicit bounded baseline, validate both snapshots independently, run:

```sh
python3 -I -S -B scripts/spec_validate.py lifecycle \
  --baseline <previous-specs> \
  --candidate <current-specs>
```

Never substitute Git history or an inferred baseline; without a complete explicit baseline, report lifecycle as `not_checked`, never claiming append-only compliance from `check` alone. Input or execution errors are not validation findings and block a successful completion report.

In a full `spec-review`, run mandatory snapshot validation before semantic review, including the result as formal evidence. In a focused audit, run it only with the complete tree available; otherwise report it `not_checked`, stating whether the scope requires it. Lifecycle stays `not_checked (not required)` unless the audit requires a user-supplied complete baseline; a passing formal result never replaces `references/auditing.md`: it does not assess meaning or drift.

## Dialogue and writing

Follow `references/interaction-contract.md` for ordinary bounded project-file edits.

Separate confirmed repository facts from human intent; when requirements, external behavior, architecture, compatibility, security, or quality are ambiguous, use the host's native interactive mechanism, else ask in chat. Never ask what is already confirmed.

In writing modes, prepare the complete file set in memory, validate every target under `specs/`, write it directly with atomic replacement or rollback, and report the resulting paths, diff summary, and actual checks. Do not create a private preview artifact or pause for confirmation before writing project files.

To pick a durable design in writing modes, develop at least two materially different options, compare them against constraints, interfaces, failures, compatibility, security, observability, testability, migration, and rollback, obtain the human's choice, and preserve architecturally significant alternatives and the outcome in an ADR.

## Modes

### `spec-init`

1. Verify `specs/` is absent; run the evidence inspection from Mode selection. Meaningful implementation evidence routes to `spec-onboard` unless the user explicitly supplied `spec-init`; an explicit incompatible mode stops with the failed precondition explained, never reinterpreted.
2. Obtain the user's explicit project-language choice before preparing files; treat confirmed user decisions as normative and record the chosen canonical language in `specs/README.md`.
3. Conduct an adaptive interview using the areas in `references/interviewing.md`.
4. Prepare the complete `specs/` file set (all 19 minimum files plus any justified indexed extension), rolling back if any write fails; run snapshot validation and report lifecycle as `not_checked`.
5. Do not modify code or create an implementation plan.

### `spec-onboard`

1. Check `specs/` absence with the evidence inspection; if `specs/` exists, ask whether the user wants read-only `spec-review` or target-state-changing `spec-update` unless intent is already explicit.
2. Investigate repository evidence per `references/onboarding.md` before asking questions.
3. Obtain the user's explicit project-language choice before preparing files and record it in `specs/README.md`.
4. Classify individual claims as `KNOWN`, `AMBIGUOUS`, `UNKNOWN`, or `CONFLICT`; explicit contracts and confirmed decisions are normative; code and tests prove only current behavior.
5. After the interview, create only canonical `specs/` and necessary ADRs (complete file set, atomic replacement or rollback), run snapshot validation, and report lifecycle as `not_checked`.

### `spec-update`

1. Verify `specs/` exists; resolve and preserve its canonical language per `references/canonical-contract.md`; read the affected area and agree on the desired change. Never select the canonical language from the current request.
2. Before design, run the mandatory `references/consolidation.md` analysis; after the edit, report `Consolidation: required` with precise simplifications or `Consolidation: not required` with a reason.
3. Agree on an unambiguous target state; a new material requirement gets a number above its namespace's historical maximum. Retain withdrawn and superseded entries as compact lifecycle records per `references/requirements.md` and `references/adr.md`.
4. Preserve an explicit complete baseline, modify only `specs/` (including ADRs in `specs/architecture/09-architecture-decisions/`), then run candidate snapshot and lifecycle validation against the baseline before reporting changes.

### `spec-review`

This mode never edits the reviewed project. Without an argument, formally validate and inspect all `specs/`; with a path, `REQ-*`, `ADR-*`, or area, inspect that object and related evidence, formal validation `not_checked` without the complete tree. Check the declared canonical language; the report follows `references/language-policy.md`. Follow `references/auditing.md`: atomic drift units, ordered decision table, severity scale, independent-critic protocol, aggregate precedence, fixed conversational report order. A full audit requires one independent critic over the same bounded evidence snapshot; a focused audit, only an explicit user request. A missing critic leaves a required audit partial, keeping confirmed findings. Keep private review evidence only in the shared review runner; no project reports or ADRs, no automatic fixes.

## Memory integration

Before `spec-review` or `spec-onboard`, search personal memory (`memory_search` tool or `memomatic search`) for prior project decisions; personal-only entries inform analysis but must never be quoted into shared `specs/`.

After `spec-update` lands an ADR, offer one memory drop and run it after user confirmation:

```shell
python3 scripts/memomatic_inbox.py drop --source spec-manage \
  --project PROJECT --key spec-PROJECT-ADR-ID \
  --text "Decision: what was accepted and why, in one sentence."
```

The drop queues for the next `memomatic process` pass; an absent memomatic inbox yields `skipped` and the workflow continues unchanged.
