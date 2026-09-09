# ADR profile

Create an ADR only for an architecturally significant decision: changed component boundaries, major technology or external dependency, cross-cutting mechanism, compatibility strategy, critical quality attribute, or a costly-to-reverse decision. An ADR is not needed for a bugfix, rename, local refactoring, or trivial implementation. Ask the user if significance is ambiguous.

Use the next free number and `templates/adr.md`. One ADR is one file, `NNNN-short-title.md`. Supported statuses: `proposed`, `accepted`, `deprecated`, `superseded`.

An ADR retains decision history. Do not rewrite an old ADR as though the new decision had always existed. For a replacement, create a new ADR, set the old one to `superseded`, link both documents, and retain the original context.
