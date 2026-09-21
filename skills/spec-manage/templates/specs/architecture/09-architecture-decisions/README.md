# 09 Architecture Decisions

## Purpose

Preserve the append-only history and current lifecycle state of architecturally significant decisions.

## Included

- An index of every ADR with its stable ID, title, and current status.
- Decision records for significant boundaries, dependencies, crosscutting mechanisms, compatibility strategies, critical qualities, or costly-to-reverse choices.

## Excluded

- Bugfixes, renames, local refactoring, trivial implementation choices, roadmap items, and decisions rewritten as if their predecessors never existed.

## Decomposition Rules

Keep the index in this `README.md` and one ADR per `NNNN-short-title.md`. Numbers are append-only; never delete or reuse an ADR. Replacements retain both records and direct links in both directions.

## Expected Structure

List all ADRs, including deprecated and superseded records. Each ADR follows `templates/adr.md`, links relevant requirements and related ADRs, and evaluates compatibility, migration, rollback, reversibility, and risks by applicability.

## Content Template

Replace this guidance with a complete linked decision-history index showing `proposed`, `accepted`, `deprecated`, or `superseded` for every ADR.
