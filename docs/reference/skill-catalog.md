# Skill Catalog

[Русский](../ru/reference/skill-catalog.md)

The current stable release publishes 27 portable Agent Skills. Its release
metadata and archive digests identify the distribution; individual skills carry
no version. Their workflows are self-contained and can be installed independently
of `@kisev/skills-opencode`.

## Active Skills

| Skill | Purpose |
| - | - |
| `agents-md` | Create or review repository-scoped `AGENTS.md` instructions. |
| `askme` | Clarify an incomplete task or design through a bounded interview. |
| `ast-grep` | Run structural search or a safe direct AST rewrite through ast-grep. |
| `code-explain` | Build a read-only guided map of current WIP, a Git range, branch, or MR history. |
| `code-review` | Review a GitLab MR or local WIP for defects and risks. |
| `commit-msg` | Produce one concise English commit message from local changes. |
| `docs-prepare` | Prepare one evidence-based user document directly in the project. |
| `docs-review` | Review user documentation for accuracy and usability. |
| `goal` | Produce a read-only structured Markdown goal of at most 4000 characters. |
| `humanize` | Edit technical prose into direct, natural language. |
| `mattermost` | Read and analyze a bounded Mattermost post, thread, channel, or chat. |
| `mr-prepare` | Prepare metadata and a local publication plan for a GitLab MR. |
| `release-prepare` | Prepare a release MR, inventory, announcement, and publication plan. |
| `release-review` | Review a release MR for completeness and compatibility. |
| `rtk` | Use RTK selectively to compress verbose command output. |
| `skill-improve` | Check and improve one Agent Skill through an iterative loop. |
| `slides-prompts-prepare` | Combine a chosen presentation theme with factual team and technology references. |
| `spec-manage` | Initialize, onboard, update, or audit canonical project specifications. |
| `stopit` | Write a sanitized handoff for the next session. |
| `briefing` | Turn transcripts, notes, or research into a structured factual summary. |
| `task-prepare` | Prepare a task or agreed GitLab task set with a manual publication plan. |
| `task-review` | Review a storage-neutral work item without changing external state. |
| `task-triage` | Triage explicit storage-neutral work-item material read-only. |
| `team-retro` | Prepare an evidence-based retrospective or delivery presentation from a private profile. |
| `team-roadmap` | Review or update an evidence-based roadmap from a private profile. |
| `team-sprint-close` | Close one sprint cycle from a private profile or explicit context. |
| `team-sprint-start` | Start one sprint cycle from a private profile or explicit context. |

Exact active and retired names are recorded in the
[Migration Inventory](../migration-inventory.md).

## Team Profiles

Team skills resolve a default private profile from
`${XDG_CONFIG_HOME:-~/.config}/opencode/team-contexts/`. On first use they can
build one from user answers and explicit files, URLs, repositories, or connector
evidence, ask only for missing fields, and save it after a confirmation-bound
preview. A request to remember a member, project, source, or visual preference
updates the private profile rather than the public skill.

The versioned public schema and sanitized example ship with every team skill as
`references/team-context.schema.json` and
`references/team-context.example.json`. Profiles remain outside this repository;
do not put credentials or personal notes in them.

## Requirements and Limits

- Portable runners use Python 3.12+ standard library only when a runner is
  needed.
- `ast-grep` and `rtk` require their external CLI; skills do not install them.
- Portable skills work without `@kisev/skills-opencode`.
- Skills do not replace repository policy, review, secret scanning, access
  control, or the user's final judgment.
