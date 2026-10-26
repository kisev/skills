# Tasks

## 1. Clarify cross-cutting decisions

- [ ] 1.1 Resolve the docs-site fate (stack and future) — verification: the
  decision is recorded in this change's design or in a tracked follow-up
  change
- [ ] 1.2 Define the release/publication machinery target shape after the
  80/20 audit (dual channels, Pages, dev tag, preflights) — verification: an
  audit table with keep/simplify/remove verdicts per mechanism is committed
- [ ] 1.3 Design the materialization redesign for self-sufficient sources
  (no build-time-only references; no build artifacts in trees) —
  verification: design recorded; the affected scripts (ast-grep,
  code-explain) run from a plain checkout
- [ ] 1.4 Plan the AGENTS.md revision to the new treaty — verification: a
  revision list covering every repository rule this change invalidates
  (pressure rule, contract-test wiring, spec routing)
- [ ] 1.5 Inventory the legacy `specs/` tree for migration — verification:
  an inventory mapping each still-valuable piece to its destination
  (charter, capability specs, decisions)

## 2. Foundation contracts

- [ ] 2.1 Keep the charter delta complete and current (mission, principles,
  capability map with component verdicts) so archiving produces the full
  main spec — verification: `openspec show project-charter --type spec`
  answers identity, principles, and verdicts in one read
- [ ] 2.2 Declare skill families (work-item, team, mattermost) in
  shared/skill-relations.json and add a check that dependencies exist only
  inside families — verification: the check fails on a planted cross-family
  dependency
- [ ] 2.3 Rewrite verification rules to the three-speed model: remove the
  per-edit pressure rule from AGENTS.md, rescope the gate registry, add the
  release-time catalog sweep — verification: no repository rule demands
  repeated model runs per wording edit; speed-1 suite green in CI
- [ ] 2.4 Audit every existing verification mechanism against 80/20 and
  record keep/simplify/remove verdicts — verification: the audit table is
  committed and the removals/simplifications are applied
- [ ] 2.5 Remove build artifacts from authored trees (mattermost,
  mattermost-triage, release-prepare, handoff) and add a check that keeps
  them out — verification: a scan over skills/ finds no bytecode caches
- [ ] 2.6 Implement the materialization redesign from 1.3 so authored
  sources are self-sufficient — verification: each affected skill's script
  runs from the authored tree without a build step

## 3. Cross-component migrations

- [ ] 3.1 Delete slides-prompts-prepare (sources, docs, catalog, relations)
  — verification: no references remain; speed-1 checks green
- [ ] 3.2 Migrate still-valuable legacy specs/ content into OpenSpec per the
  1.5 inventory and remove the legacy tree — verification: specs/ is gone
  and its valuable content is findable in openspec/

## Workflow follow-up

- The per-component backlog: every skill and application has its own change
  (`spec-*` per component, `rework-spec-manage`); each delivers its
  component's exhaustive specification and executes the decisions recorded
  in its proposal.
- After the component waves land, run the speed-2 release sweep over the
  whole catalog before archiving this change.
- Archiving this change syncs the six foundation specs into
  openspec/specs/.
