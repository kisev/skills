# User Documentation Workflow

Read applicable `AGENTS.md`, the existing target document, source code, tests,
configuration, and related canonical specifications. Without a path or section,
inspect the complete user-facing documentation set to select the relevant document.
Apply `humanize` before drafting documentation prose.

## Document selection

Choose one reader and one purpose: a tutorial teaches through a guided path, a
how-to reaches a concrete result, reference describes commands/API/configuration,
and explanation gives concepts and rationale. Create or improve one document
using repository conventions or the appropriate Diataxis directory in `docs/`.
Do not create an empty four-directory tree or overwrite a document with a different
purpose or audience.

## Preparation

Follow `references/interaction-contract.md`. Verify claims, paths, commands,
versions, and examples against source and tests; label unverified claims explicitly.
Prepare the complete content and validate its bounded workspace path, then
write it directly with atomic replacement. Do not create a private preview artifact or
pause for confirmation before ordinary project-file edits.

Report the resulting path, diff summary, verified sources, checks, and limitations.
Do not modify `specs/`. If documentation reveals a specification mismatch,
separately propose `spec-manage` audit or update; never combine workflows.
