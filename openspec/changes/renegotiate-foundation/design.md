# Design

## Context

The renegotiation was conducted from first principles (October 2026) over
the whole project: implemented components, the TODO decision log, and the
RESEARCH corpus. It produced a treaty that this design records. The current
implementation is treated as a reference, not a gold standard: nothing is
kept merely because it exists.

Constraints that shape the approach: the owner is the primary user and the
project is public from the start; the repository is a monorepo by choice;
three agent hosts must be supported; the Agent Skills open standard already
covers skill packaging, and OpenSpec already covers spec-driven development,
so this project stops duplicating both.

## Goals / Non-Goals

**Goals:**

- Record the renegotiated treaty with its rationale in one authoritative
  place.
- Define the foundation capabilities (charter, skill model, verification,
  distribution, spec process, stack) precisely enough to guide every
  follow-up clarification.
- Fix the structural defects found during the audit: non-self-sufficient
  sources, build artifacts in trees, undeclared families, orphan relations.

**Non-Goals:**

- Exhaustive per-component specifications — produced by the clarification
  waves tracked in tasks.md and in the `clarify-*` placeholder changes.
- The agent-platform ambitions from the research corpus (orchestration,
  approvals protocol, sandboxing, multi-project UI) — they remain research
  input, not a commitment; mechanics may be absorbed into tools later.
- Splitting the repository.

## Decisions

### D1. Identity: personal-first, public from the start

The project is a set of AI/LLM instruments growing from the owner's real
needs, published immediately for users with the same needs. Universality is
consciously preferred over simplicity. Alternative (private tool, publish
later) rejected: publishing is part of the point, not a later stage.

### D2. Working principles (the charter's non-negotiables)

The owner is the architect and manager; agents are the team and personal
assistants. Mutual understanding without micro-coordination. Spec-driven
development (OpenSpec) and Diataxis documentation everywhere, including in
projects built with these tools. Skill texts are guidance, never programming
languages — strictness lives in runtimes. 80/20 over perfectionism; benefit
now; a tool must beat doing it by hand. Inspiration is credited via
`inspired-by`, which doubles as a channel for tracking upstream changes.
Components are uniform and self-sufficient; skills complement each other
without coupling; families are the only place dependencies are allowed.

### D3. Skill and command model follows the hosts

A skill is knowledge and ability the agent invokes contextually; a command
is a human entry point; commands are optional per skill. The definitions
come from the Agent Skills standard and Codex/Claude/OpenCode documentation,
not from this project. The previous rule "commands are thin stubs" is
cancelled: all three hosts expose the same primitives. `agentomatic` stops
being "the OpenCode integration" and becomes one of three host adapters.

### D4. Verification: three speeds

Fast programmatic checks on every change; one trigger-based synthetic live
run on material behavior changes; organic real-task usage with no
obligations. The per-edit pressure rule (>= 5 subagent repeats) is
cancelled. Every existing gate/preflight mechanism must justify itself
against 80/20 or shrink. Alternative (per-class bars only) deferred: bars
may emerge later from the three-speed model in practice.

### D5. Distribution: agentomatic as the single installer

Python rewrite with a host-adapter registry modeled on OpenSpec's
command-generation architecture (one content model, \~50-line adapters).
Existing strengths are kept: preview, confirmation digest, ownership
manifests, drift preservation. The external `skills` CLI and the Pages
channel stop being the primary path. Alternative (stay on the external CLI)
rejected by the owner: scattered setup tools are inconsistent and
inconvenient.

### D6. Specifications: OpenSpec only, plus a companion layer

The in-house spec system (arc42 views, REQ-\*/ADR, `spec-manage`) is
retired. OpenSpec is the only spec system here and the recommended practice
elsewhere. The gap the owner hit — OpenSpec is capability-granular and lacks
a canonical generalization — is filled by this project's reworked spec
skills: they build and maintain the overview layer (mission, principles,
capability map, cross-cutting decisions) on top of per-capability specs.

### D7. Stack: Python everywhere except open questions

Runtime logic and standalone apps are Python with declared dependencies
(`agentomatic`, `taskmatic`, `memomatic` ports; `reviewmatic` and
`shopmatic` reworks). Stdlib-only remains the rule for scripts inside
portable archives. This reverses the earlier "agentomatic stays TS"
decision. The documentation site's stack is an open question.

### D8. Component verdicts

Core set (confirmed, frequently used): agents-md, askme, briefing,
code-review (simplify — heavy, complex, slow), commit-msg, docs-prepare,
docs-review, eli5, goal, handoff, humanize (hub), mattermost (weight
hygiene), mattermost-triage (weight hygiene), mr-prepare, release-prepare,
release-review. Deleted: slides-prompts-prepare. Reworked strongly:
spec-manage (into OpenSpec companions). Kept with details deferred: tdd,
debugging, verification, code-simplify, code-explain (script broken in
checkout), ast-grep (broken in checkout — needs repair decision), each with
its own change. Every undecided component is tracked by its own placeholder
change recording no decisions: `spec-task-prepare`, `spec-task-review`,
`spec-task-triage`, `spec-taskmatic`, `spec-rtk`, `spec-skill-doctor`,
`spec-asd-ste100`, and the twelve `spec-team-*` changes (the sprint pair
combined into `spec-team-sprint` as a merge candidate). Cross-cutting known defects to fix: `__pycache__`
in authored trees (mattermost, mattermost-triage, release-prepare, handoff),
stale `.build` copies, sprint-close's undeclared collector dependency,
jq/sha256sum missing from declared requirements.

### D9. Families become explicit

`shared/skill-relations.json` gains a family concept; the de-facto families
(work-item, team, mattermost) are declared, and dependencies are only legal
inside families. Hub status (humanize, team-people, team-retiro, mattermost)
is tracked as a fact in the charter's capability map.

### D10. OpenSpec change structure for this renegotiation

One foundation change (this one) holds the treaty and the cross-cutting
capabilities. Every component — every skill and every application — gets its
own change that carries its verdict, its dossier facts, and its open
questions; decided components record their decisions, undecided components
record deferral and nothing else. Each component change drafts the
exhaustive specification of its component when picked up. This is a
deliberate rolling wave: capture now, refine by priority, implement by
component.

## Risks / Trade-offs

- \[Placeholder changes rot unnoticed] → the charter's capability map lists
  them; a periodic release-time review of open changes keeps them honest.
- \[Three-speed verification lets regressions through between sweeps] →
  failures found by speeds 2/3 must sediment into speed 1 regressions; that
  rule is the counterweight.
- \[agentomatic rewrite in Python is a large migration] → its safety model
  (preview, digests, ownership) is re-implemented first and tested against
  the current behavior before the TS version is retired.
- \[Legacy specs/ migration loses history] → migrate content, not structure;
  still-valuable ADR/REQ text is distilled into the charter and capability
  specs; the legacy tree stays in git history.
- \[Host semantics drift (three vendors evolve fast)] → the skill-model spec
  pins to the standard and documented semantics; adapter tests per host
  catch drift in speed 1.

## Migration Plan

1. Foundation wave: charter spec, skill-model contract, verification-model
   rewrite of gates and repository rules, family declarations.
2. `agentomatic` Python rewrite with the adapter registry; retire the TS
   implementation only after behavioral parity.
3. Component waves per the per-component `spec-*` changes.
4. Legacy `specs/` migration and removal of `slides-prompts-prepare`.
   Rollback: each wave is a separately archivable change; the legacy tree is
   removed only after migration is verified.

## Open Questions

- The documentation site's stack and fate (TS Astro site today).
- The final form of the memory tooling (`memomatic` idea confirmed, current
  form uncertain).
- The release and publication machinery's target shape after the 80/20
  audit (dual channels, Pages, dev tag).
- The Ozon blocker in `shopmatic` (anti-bot on datacenter IPs; residential
  retry pending).
- Whether per-class quality bars will crystallize on top of the three-speed
  model.
