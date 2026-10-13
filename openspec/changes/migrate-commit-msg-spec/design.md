# Design

## Context

The legacy canonical specification lives in `specs/` (arc42-style, maintained
through the `spec-manage` workflow, English-only under `REQ-C-001`). Per
capability it holds thin records under `specs/capabilities/{skills,commands}/`;
for `commit-msg` there are two: the skill capability (including `REQ-F-106`
read-only) and the command adapter (`REQ-I-206` route through the shared
command interface). See [proposal.md](proposal.md) for the drift evidence and
motivation.

Two mechanical couplings constrain the migration:

- `scripts/check_documentation.py` requires every authored skill and command to
  have a `specs/capabilities/<kind>/<name>.md` file and an index link in
  `specs/capabilities/README.md`.
- `specs/capabilities/commands/commit-msg.md` links to
  `../skills/commit-msg.md`, so the two legacy records must be retired
  together.

The skill itself (`skills/commit-msg/`, `shared/skill-relations.json`,
`shared/manifest.json`, built archives) is not touched. OpenSpec has no
`openspec/specs/` tree yet; this change creates the first one via its delta.

## Goals / Non-Goals

**Goals:**

- One canonical contract for `commit-msg` under `openspec/specs/commit-msg/`.
- Coverage-complete contract: every normative statement of
  `skills/commit-msg/references/workflow.md` maps into exactly one requirement,
  plus the command-binding essence of `REQ-I-206`.
- Keep gates green during and after the migration step.

**Non-Goals:**

- No change to skill behavior, skill text, relations, or built archives.
- No migration of other capabilities, shared requirements, crosscutting
  concepts, or the architecture/ADR tree.
- No new tooling beyond the minimal `check_documentation.py` adaptation.

## Decisions

### D1: Spec abstraction — coverage-complete contract, not a copy

The spec states each observable guarantee once; operational wording stays in
`workflow.md` and mechanical pins stay in `tests/` and `evals/`. All 18
normative statements of `workflow.md` map onto the ten requirements in
[specs/commit-msg/spec.md](specs/commit-msg/spec.md).

Alternative rejected: copying all statements verbatim into the spec. It doubles
the drift surface at the wrong abstraction level — the legacy tree already
drifted on exactly one statement ("English") while tests stayed green.

### D2: Single canonical text retired in the same change

Both legacy records are deleted by this change, not left as redirects.

Alternatives rejected: keeping the records as pointers (second canonical text,
guaranteed re-drift); retiring only the skill record (dangles the command
record's link to `../skills/commit-msg.md`).

### D3: Self-contained spec, no references into the legacy tree

The new spec restates what it needs (language policy is embodied in
convention-detection requirements) instead of referencing
`specs/architecture/08-crosscutting-concepts/`. Those files will disappear as
the migration proceeds; the OpenSpec spec must outlive them.

Trade-off accepted: temporary duplication with the not-yet-migrated shared
concepts. Re-linking is possible once a shared layer exists under OpenSpec.

### D4: Command adapter folded in as one requirement

`REQ-I-206`'s essence — the command binds exactly this skill and treats
arguments as untrusted — becomes the `Command binding` requirement. The
"shared command interface" (`REQ-I-002`) belongs to the package capability and
migrates with it.

Alternatives rejected: keeping `specs/capabilities/commands/commit-msg.md`
(dangling link, see D2); a separate `commit-msg-command` spec (premature before
the command-interface capability migrates).

### D5: `check_documentation.py` learns an explicit migrated-surfaces list

The script skips the legacy-record and index-link requirements for migrated
names. The existence of the migrated target is guaranteed by the OpenSpec
workflow itself (`openspec validate` during the change, archive creating
`openspec/specs/commit-msg/`), so the script does not re-verify it — this keeps
the apply phase (before archive) green.

Alternatives rejected: teaching the script to resolve OpenSpec specs to surface
names (fuzzy mapping, premature for one capability); dropping the legacy check
entirely (removes protection for the \~40 not-yet-migrated surfaces).

## Risks / Trade-offs

- \[Two validation systems coexist during the migration] → Both must stay green;
  the migrated-surfaces list is the single seam and shrinks to nothing when the
  legacy tree retires.
- \[The migrated-surfaces list can drift from reality] → The list only ever
  grows within migration changes that delete legacy records in the same commit;
  `task check` fails on any mismatch between list and files.
- \[Shared-concept duplication (D3)] → Accepted temporarily; recorded here so a
  later shared-layer change knows where to consolidate.

## Migration Plan

1. Land this change's delta (already in `specs/commit-msg/spec.md`).
2. Apply tasks: delete the two legacy records, update the capabilities index,
   adapt `check_documentation.py` with the migrated-surfaces list.
3. Verify: `task format`, `task check`, `openspec validate --strict` on the
   change.
4. Archive the change: the delta lands as `openspec/specs/commit-msg/spec.md`.

Rollback: `git revert` of the change; no data or external state involved.

## Open Questions

- Program-level migration order (capabilities-first vs shared-concepts-first)
  — deferrable; it does not affect this change, only the shape of later ones.
