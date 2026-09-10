# Interface Requirements

## Public Interfaces

### REQ-I-001 - Skill interface

Each public skill shall have an English canonical `SKILL.md`, stable frontmatter,
portable referenced resources, explicit trigger boundaries, and the shared
interaction/evidence contract. The `goal`, `task-prepare`, `task-review`, and
`task-triage` skills shall normalize their documented inputs to `work-item/v1`
before semantic processing.

### REQ-I-002 - Command interface

Each public command shall route to its named skill or package tool, shall treat
arguments as untrusted input without bypassing the selected contract, and shall
not add state, storage, or publication behavior absent from that contract.

### REQ-I-003 - Package tool interface

The core plugin shall register exactly `capabilities`, `route`, `doctor`,
`agent_profiles`, and `reconcile` tools with versioned structured results.

### REQ-I-004 - Plugin interface

The package shall export the core infrastructure plugin and exactly three
selectable plugin modules: `rules-injector`, `rtk`, and `zed-bell`.

### REQ-I-005 - Evidence interface

Tests and evals shall expose stable selectors, scenario IDs, invariant paths,
and bounded hostless execution metadata.

### REQ-I-006 - Compatibility interface

The package shall declare `@opencode-ai/plugin >=1.18.29 <1.19.0` and preserve
the checked versions and no-network/no-credentials compatibility boundary.
