# Proposal

## Why

The project grew from a personal toolkit into a public multi-identity monorepo
without a renegotiated foundation, and three accumulated problems now block
further evolution: the verification culture overshoots the agreed 80/20
principle (gate registry, pressure runs with >= 5 repeats per wording edit,
dual publication preflights); authored skill sources are not self-sufficient
(`SKILL.source.md` references files that exist only after build
materialization, some skills cannot run from a checkout at all, and build
artifacts pollute authored trees); and the in-house specification system
(`specs/` with arc42 views, REQ-\*/ADR, and `spec-manage` as its owner)
duplicates what OpenSpec already provides. This change renegotiates the
foundation from first principles and records the resulting treaty as the first
content of OpenSpec in this repository.

## What Changes

- A project charter becomes the canonical generalization layer (mission,
  principles, capability map) that per-capability specs assume and that
  answers "what is this project built on" from one place.
- Skill and command semantics follow the Agent Skills open standard and the
  host documentation of Codex, Claude, and OpenCode: a skill is agent-invoked
  knowledge and ability; a command is an optional human entry point. All
  three hosts become first-class targets; not every skill gets a command.
- Authored skill sources become self-sufficient: every file a skill references
  exists in its authored tree, and no build artifacts appear in sources.
- **BREAKING** Verification moves to a three-speed model: fast programmatic
  checks on every change, trigger-based synthetic live runs, and
  obligation-free organic usage. The per-edit pressure rule (>= 5 repeats per
  wording change) is replaced by trigger-based runs.
- **BREAKING** `agentomatic` becomes the single installer-configurator for
  skills, commands, and host configuration across the three hosts (project
  and global scopes) with a host-adapter registry, and is rewritten in
  Python. The external `skills` CLI stops being the primary install channel.
- **BREAKING** OpenSpec becomes the only specification system in this project;
  the legacy `specs/` tree is migrated; `spec-manage` is reworked into an
  OpenSpec companion skill family that maintains the generalization layer
  OpenSpec itself does not provide.
- Component verdicts from the renegotiation are executed per component, one
  change each: the core skill set (16 skills) is confirmed with named
  reworks (`spec-agents-md` … `spec-release-review`); code-flow support
  skills are kept with details deferred (`spec-tdd`, `spec-debugging`,
  `spec-verification`, `spec-code-simplify`, `spec-code-explain`,
  `spec-ast-grep`); every undecided component has its own placeholder change
  recording no decisions yet (`spec-task-prepare`, `spec-task-review`,
  `spec-task-triage`, `spec-taskmatic`, `spec-rtk`, `spec-skill-doctor`,
  `spec-asd-ste100`, and the twelve `spec-team-*` changes);
  `spec-manage` becomes the OpenSpec companion family
  (`rework-spec-manage`); the applications are reworked under their own
  changes (`spec-memomatic`, `spec-skillmate`, `spec-reviewmatic`,
  `spec-shopmatic`); `slides-prompts-prepare` is deleted (a task in this
  change).
- The repository stays a monorepo; splitting is deferred until the shape
  stabilizes.

## Capabilities

### New Capabilities

- `project-charter`: the canonical generalization layer — mission, target
  users, non-negotiable principles, and the capability map that all other
  specs build on.
- `skill-model`: what a skill and a command are in this project, the three
  supported hosts, source self-sufficiency, skill text style, and the family
  contract.
- `verification-model`: the three speeds of quality checking and what each
  speed is triggered by.
- `distribution`: how skills, commands, and host configuration are installed
  and configured for every supported host, and what the installer guarantees
  around preview, confirmation, and user drift.
- `spec-driven-development`: OpenSpec as the only spec system, the companion
  layer on top of it, and the treatment of the legacy `specs/` tree.
- `stack`: technology boundaries for runtimes, applications, and scripts
  shipped inside skill archives.

### Modified Capabilities

- None. The only existing OpenSpec capability (`commit-msg`) keeps its
  requirements; no spec-level change was decided for it.

## Impact

- `skills/*`: catalog verdicts, source self-sufficiency, text style
  revisions; `slides-prompts-prepare` removal.
- `packages/agentomatic`: Python rewrite as the universal
  installer-configurator with a host-adapter registry.
- `apps/*`: Python ports (`memomatic`, `taskmatic`) and reworks
  (`reviewmatic`, `shopmatic`).
- `shared/`: materialization redesign (self-sufficient sources, no build
  artifacts in trees).
- `specs/`: legacy tree, to be migrated into OpenSpec.
- `openspec/`: becomes the single spec home; this change is its first
  content.
- `docs/`, `AGENTS.md`, `taskfile.yml`, gates and CI: revision and audit
  against the 80/20 principle.
