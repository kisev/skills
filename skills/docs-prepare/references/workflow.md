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

## Language set

Resolve the documentation language set in this order: an explicit user request,
project rules, the agent's global rules, then English by default. Produce one
single-language set or mirrored multilingual sets in any languages. Translate
prose per mirror while machine tokens (commands, paths, flags, IDs, JSON
fields) stay byte-identical across mirrors. The set is independent of the
canonical specification language: never mirror `specs/` and never change its
single canonical language from documentation work.

## Agent annotations

Write for humans first. Add machine-readable guidance for agents as YAML
frontmatter: `audience: user` by default, plus an optional `agent` block with
`purpose` and a `hints` list of short imperatives:

```yaml
---
audience: user
agent:
  purpose: install portable skills globally
  hints:
    - prefer the default agent selection
---
```

Add a dedicated agent section inside the document only when an agent needs an
expanded instruction that does not fit `hints`; title it explicitly, for
example `## Notes for agents`. Keep executable contracts, gates, and
inventories out of user prose: they belong in the canonical specification or
an explicit agent section. Frontmatter and agent sections are machine tokens:
keep them identical across language mirrors.

## Preparation

Follow `references/interaction-contract.md`. Verify claims, paths, commands,
versions, and examples against source and tests; label unverified claims explicitly.
Prepare the complete content and validate its bounded workspace path, then
write it directly with atomic replacement. Do not create a private preview artifact or
pause for confirmation before ordinary project-file edits.

Report the resulting path, diff summary, verified sources, checks, and limitations.
Do not modify `specs/`. If documentation reveals a specification mismatch,
separately propose `spec-manage` audit or update; never combine workflows.

## Memory integration

After the document is written and verified, offer one memory drop of the
durable documentation convention observed in this repository (audience,
locale, Diataxis layout, verified check commands) and run it after user
confirmation:

```shell
python3 scripts/memomatic_inbox.py drop --source docs-prepare \
  --project PROJECT --text "Documentation convention in one sentence."
```

The drop is queued for the next `memomatic process` pass; when the memomatic
inbox is absent the command reports `skipped` and the workflow continues
unchanged.
