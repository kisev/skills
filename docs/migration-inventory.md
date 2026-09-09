# Migration Inventory

[Русский](ru/migration-inventory.md)

This catalog records the portable skills shipped by this repository. Each is
installed independently through `npx skills` and does not depend on checkout
files after installation.

| Skill | Mode | Purpose |
| --- | --- | --- |
| `agents-md` | previewed read/write | Repository-scoped agent instructions. |
| `askme` | read-only | Task and decision clarification interview. |
| `ast-grep` | digest-protected read/write | Structural search and confirmed AST rewrite. |
| `commit-msg` | read-only | Commit message from actual changes. |
| `doit` | previewed write | Scoped engineering work. |
| `docs-prepare` | previewed write | One Diataxis user document. |
| `docs-review` | read-only | User-documentation review. |
| `humanize` | read-only | Natural Russian prose. |
| `project-spec` | explicit read/write or read-only modes | Canonical specification. |
| `rtk` | read-only CLI check | Selective external-output compression. |
| `skill-improver` | read-only checker | One Agent Skill improvement cycle. |
| `stopit` | previewed write | De-identified context handoff outside the repository. |
| `summary` | read-only by default | Structured summary of supplied material. |
| `task-triage` | read-only | Substantive analysis of specific GitLab issues. |
| `task-review` | read-only | GitLab issue and MR metadata review. |
| `task-prepare` | local plan | GitLab issue preparation without publication. |
| `mr-prepare` | local plan | Ordinary GitLab MR preparation. |
| `code-review` | read-only and local plan | Deep GitLab MR or local WIP review. |
| `release-prepare` | local plan | Release MR, inventory, and publication-plan preparation. |
| `release-review` | read-only | Release readiness review. |
| `mattermost` | read-only, identity-private cache | Bounded Mattermost reading. |
| `team-workflow` | confirmed read/write | One explicit team-cycle action from explicit context. |
| `walkthrough` | read-only runner | Reading map for a current diff, Git range, or diff file. |
| `attempt` | package tool | Bounded Background Attempt inspection and confirmed cancellation. |
| `goal` | read-only portable skill | Verifiable goal in canonical `work-item/v1`. |
| `schedule` | confirmed write | Explicit disabled-by-default definitions. |
| `usage` | read-only runner | Token and cost ledger with honest unknown values. |
| `overview` | read-only runner | Partial-tolerant OpenCode state overview. |
| `lsp-report` | read-only runner | Applicable LSPs without launching servers or installing tools. |

Skills do not inherit runtime state, providers, global configuration, or
host-specific tool names. Interaction stays host-neutral: use the host mechanism
when available and otherwise ask in chat.

The `askme`, `task-prepare`, `task-review`, and `goal` workflows share versioned
`work-item/v1`: problem/outcome, criteria/evidence, scope/non-goals,
dependencies/actions/assumptions, safety, risks/questions, and stop conditions.
The machine validator checks form, links, boundaries, DAG, and report stability;
feasibility and semantic contradictions come from a separate structured
assessment. `goal` creates no state or lifecycle. An optional premortem runs once
through an independent agent or returns `skipped` without blocking.

`skills/` contains no commands, agents, or plugins. Context logic is in
`SKILL.md`; runners, when needed, live in their owning skill. Their minimal shared
stdlib is authored canonically in `shared/references/` and committed as exact
generated copies in each dependent `skills/<name>/` source directory. A clean
Git clone is therefore directly installable.
The optional `packages/opencode/` package contains OpenCode-specific assets,
runtime, and opt-in installer but never copied skills or changes to `npx skills`
installation. Agent profiles are package-domain functionality with direct CLI;
four slash commands and `agent_profiles` only adapt that interface. Stateful
plugins are disabled by default.

Machine-readable public-surface history is in
`packages/opencode/assets/migration-inventory.json`. It contains only portable
skills, package assets, and installation metadata available through public GitHub
tags or npm releases. Retired entries require exact SHA-256 validation and
scope-bound confirmation before removal.
