# Skill Catalog

[Русский](../ru/reference/skill-catalog.md)

The maintained catalog contains 41 portable Agent Skills. Its release
metadata and archive digests identify the distribution; individual skills carry
no version. Their workflows are self-contained and can be installed independently
of `@kisev/agentomatic`.

Declared companions are listed in each skill's built `SKILL.md` "Related skills"
section: `requires` marks a shared credential or workflow, `uses` marks a
composed contract, and `recommends` marks a natural companion. Relations are
install recommendations only; every archive works on its own.

## Mattermost discussion cards

Ask explicitly for an Issue/MR card to open a discussion thread, or select this
mode in the project's `AGENTS.md`. Ordinary messages containing GitLab links
keep their existing format. The skill prepares a manual publication command;
you run it yourself with the existing origin-bound Mattermost credentials.

Standard Issue and MR templates include metadata and a short summary. Custom
cards let an agent choose fields and their order. Both English and Russian are
supported; names from GitLab stay unchanged. Important labels can be shown with
an explicit omitted count. Oversized cards are rejected with an explanation,
so the agent can shorten them before preparing a new command.

See the portable [card guide](../../skills/mattermost/references/cards.md) for the
input contract, examples, and limits, and the
[publication workflow](../../skills/mattermost/references/workflow.md#publication)
for authentication and recovery. Cards use legacy attachments without requiring
a GitLab plugin. Compactness limits are estimates; verify rendering in your
Mattermost client, especially a narrow thread panel. Automatic posting and cron
are not included.

## Active Skills

| Skill | Purpose |
| - | - |
| `agents-md` | Create or review repository-scoped `AGENTS.md` instructions. |
| `asd-ste100` | Check and rewrite technical text in the task's language using Simplified Technical English principles, preserving conditions, exceptions, and obligations. |
| `askme` | Clarify a task or design through a bounded interview; every call returns all current agreements, including those made before the first interview. |
| `ast-grep` | Run structural search or a safe direct AST rewrite through ast-grep. |
| `code-explain` | Build a read-only guided map of current WIP, a Git range, branch, or MR history. |
| `code-review` | Review a GitLab MR or local WIP for defects and risks. |
| `code-simplify` | Keep code necessary with a passive prevention ladder while coding, recording a SIMPLIFY debt marker on a conscious cut; on explicit request, audit a requested scope and report ranked, tagged, one-line simplification findings plus a debt-marker registry without changing files. |
| `commit-msg` | Produce one concise English commit message from local changes. |
| `docs-prepare` | Prepare one evidence-based user document directly in the project. |
| `docs-review` | Review user documentation for accuracy and usability. |
| `eli5` | Explain a complex concept in plain language calibrated to the reader, keeping essential constraints and uncertainty. |
| `goal` | Produce a read-only structured Markdown goal of at most 4000 characters. |
| `humanize` | On explicit request only, edit prose into direct, natural language while preserving meaning and voice. |
| `mattermost` | Read bounded Mattermost conversations and prepare manual publications, including opt-in Issue/MR cards. |
| `mattermost-triage` | Find Mattermost conversations that need attention and prepare durable manual response plans. |
| `mr-prepare` | Prepare metadata and a local publication plan for a GitLab MR. |
| `release-prepare` | Prepare a release MR, inventory, announcement, and publication plan. |
| `release-review` | Review a release MR for completeness and compatibility. |
| `rtk` | Use RTK selectively to compress verbose command output. |
| `skill-doctor` | Diagnose current-session skill usage into private incremental notes and prepare confirmed public bug reports. |
| `slides-prompts-prepare` | Combine a chosen presentation theme with factual team and technology references. |
| `spec-manage` | Create greenfield specs, describe an existing project, change canonical target state, or audit specs read-only; mode tokens are optional. |
| `handoff` | Write a sanitized handoff for the next session. |
| `briefing` | Turn transcripts, notes, or research into a structured factual summary. |
| `task-prepare` | Prepare tasks with shared review, scoped release planning, and manual GitLab publication commands. |
| `task-review` | Review semantic quality and release-milestone compatibility standalone or inside other task workflows. |
| `task-triage` | Triage GitLab issues into persistent decisions, release milestones, priorities, dependencies, and manual update commands. |
| `taskmatic` | Run a local-first task board for people and agents with a markdown mirror, claims, and a read-only web board. |
| `team-1on1` | Prepare a private one-to-one conversation from people context. |
| `team-agreements` | Maintain explicit team working agreements. |
| `team-feedback` | Prepare evidence-based feedback and rehearse the conversation. |
| `team-health` | Review team health from bounded evidence. |
| `team-incident` | Prepare an incident review and its lessons. |
| `team-onboarding` | Prepare role-specific onboarding from a private profile. |
| `team-people` | Maintain a private people profile, journal, and commitments. |
| `team-performance` | Prepare evidence-based performance assessments. |
| `team-report` | Prepare a bounded team delivery report. |
| `team-retro` | Prepare an evidence-based retrospective or delivery presentation from a private profile. |
| `team-roadmap` | Review or update an evidence-based roadmap from a private profile. |
| `team-sprint-close` | Close one sprint cycle from a private profile or explicit context. |
| `team-sprint-start` | Start one sprint cycle from a private profile or explicit context. |

Exact active and retired names are recorded in the
[Migration Inventory](../migration-inventory.md).

## Specification Modes

`spec-manage` accepts explicit `spec-init`, `spec-onboard`, `spec-update`, and
`spec-review` tokens, but ordinary requests can state intent naturally. It checks
repository evidence before distinguishing a new project from an existing one and
asks one short question without writing when more than one mode remains possible.

- “Create the canonical specification for this new empty project” selects `spec-init` only when no meaningful code, tests, schemas, configuration, CI, or deployment exists.
- “Document this existing service as canonical specs” selects `spec-onboard` when the repository already contains implementation evidence but no `specs/`.
- “Change the canonical timeout target to 30 seconds” selects `spec-update` when `specs/` exists.
- “Check these specs against the implementation without changing files” selects `spec-review`, which preserves project files and retains private review evidence.

After an authorized behavior change, `spec-manage` and `docs-prepare` activate
themselves for the affected canonical and user documentation steps; project
instructions are not required for that trigger, and it never creates a missing
`specs/` tree or documentation set. Mentioning architecture alone does not
authorize a new contract.

## Review and Publication

The OpenCode `review` agent can be selected directly or called by `manager`.
It orchestrates the review panel and calls independent critics when the selected
skill requires them: the critic composition and the arbitrator are recorded once
per prepared snapshot, the selected critics run in parallel from one recorded
context package — goal, claims with sources, constraints,
prior decisions, and questions, stored privately outside the checkout and
handed to critics as their primary context — and a separate arbitrator imports
one receipt with a verdict for every critic finding. Fixing project sources requires an
explicit request and a
separate fixing phase. Portable `code-review` also works without this agent layer.

1. Request a code review and read the resulting `runbook.md`.
2. Inspect each proposed action and its exact body before running its command.
3. Copy a direct `glab` command or launch `reviewmatic plan` for the same actions
   interactively. Replies and thread state are separate choices. Reading and
   navigation remain available during sends; `z` cancels waiting, `q` exits.
4. Read the command result/error and check GitLab in your browser. You decide
   whether to repeat; a timeout may have left an accepted request and a repeat
   may duplicate it. No publication ledger, lock, or automatic retry blocks you.
5. New plans support `repair-review` for targeted corrections and `refresh-review`
   for changed evidence without losing findings. Old guarded plans remain readable
   history, without migration or execution of their old actions.

Explicit `/askme` requests end with manual continuation. Internal clarification
returns to the already-authorized workflow without expanding its scope.

## Team Profiles

Team skills resolve a default private profile from
`${XDG_CONFIG_HOME:-~/.config}/agent-skills/team/`. On first use they can
build one from user answers and explicit files, URLs, repositories, or connector
evidence, ask only for missing fields, and save it after a confirmation-bound
preview. A request to remember a member, project, source, or visual preference
updates the private profile rather than the public skill.

Delivery profiles also support the legacy `${XDG_CONFIG_HOME:-~/.config}/opencode/team-contexts/` fallback. Evidence belongs under `${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/team/<profile>/evidence/`; the profile workflow provides explicit migration from the legacy `team-evidence` layout without silently deleting user state.

The versioned public schema and sanitized example ship with every team skill as
`references/team-context.schema.json` and
`references/team-context.example.json`. Profiles remain outside this repository;
do not put credentials or personal notes in them.

## Requirements and Limits

- Portable runners use Python 3.12+ standard library only when a runner is
  needed.
- `ast-grep` and `rtk` require their external CLI; skills do not install them.
- Portable skills work without `@kisev/agentomatic`.
- Skills do not replace repository policy, review, secret scanning, access
  control, or the user's final judgment.
