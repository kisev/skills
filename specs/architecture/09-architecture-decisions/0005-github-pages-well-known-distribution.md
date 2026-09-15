# ADR-0005: GitHub Pages Well-Known Distribution

- Status: accepted
- Date: 2026-09-14
- Supersedes: [ADR-0001](0001-direct-git-self-contained-skills.md)

## Context

Portable skills must be autonomous after installation, while canonical shared
contracts and runtimes should not be duplicated in the authored Git tree. The
`skills` CLI does not execute a repository build hook during installation.

## Decision

Keep deduplicated authored definitions and shared material in Git. On an exact
validated release tag, build every complete skill in an isolated output and
deploy a standard agentskills.io well-known index plus one content-addressed,
SHA-256-bound archive per skill to GitHub Pages. Use the stable Pages URL as the
supported installation and update source. Keep Git tags as source provenance and
the optional OpenCode npm package as an independently installed layer.

## Alternatives

We rejected committed generated copies because they obscure canonical ownership
and create repository drift. We rejected install-time build hooks because the
portable installer does not support them and they expand the consumer trust
boundary. Direct GitHub Release archive URLs do not provide one catalog and
tracked update source. A separate generated Git repository preserves Git install
syntax but retains generated history without improving the artifact contract.

## Consequences

The authored repository is no longer an installation source. Release CI and
GitHub Pages availability become part of publication, while deterministic
content-addressed archives make cache and integrity failures observable. Existing
Git-based installations must be rebound once by repeating `skills add` with the
Pages URL. Historical release tags remain unchanged and installable under their
original contract.
