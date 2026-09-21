# Interface Requirements

## Public Interfaces

### REQ-I-001 - Skill interface

Each public skill definition shall have an English canonical `SKILL.source.md`
with standards-valid frontmatter and explicit trigger boundaries. Its published
archive shall expose root `SKILL.md`, portable referenced resources, and the
shared interaction/evidence contract. Authored and built skill metadata shall not
carry a version; release identity belongs to distribution metadata and archive
digest. Every published skill shall carry the exact cleanup provenance marker
`metadata.source: "https://kisev.github.io/skills"`. The `goal`, `task-prepare`, `task-review`, and `task-triage` skills shall
normalize their documented inputs to `work-item/v1` before semantic processing.

### REQ-I-002 - Command interface

Each public command shall route to its same-named skill, shall treat
arguments as untrusted input without bypassing the selected contract, and shall
not add state, storage, or publication behavior absent from that contract. Command
selection remains the user's decision: the installer selects command adapters,
not portable skills. Command adapters load an already-installed same-named skill.
Pre-selector guidance shall identify the exact configured `skills` CLI version
and the supported Pages source, and previews shall expose deterministic
`plan_digest` separately from the unique `confirmation_digest`; superseded plans
expose only redacted kind, short confirmation digest, and timestamps.

### REQ-I-003 - Package tool interface

The core plugin shall register exactly the `route` package tool with versioned
structured results and one-use routing receipts.

### REQ-I-004 - Plugin interface

The package shall export the core infrastructure plugin and exactly three
selectable plugin modules: `rules-injector`, `rtk`, and `zed-bell`.

### REQ-I-005 - Evidence interface

Tests and evals shall expose stable selectors, scenario IDs, invariant paths,
and bounded hostless execution metadata. A scenario may opt into structured
per-case outcomes. For such a scenario, trusted-live observation shall contain
exactly one correct outcome for every declared case, while hostless evaluation
shall validate only the scenario contract and shall not present fixture outcomes
as observed model behavior. Existing selection-only scenarios remain valid.

### REQ-I-006 - Compatibility interface

The package shall declare `@opencode-ai/plugin >=1.18.29 <1.19.0` and preserve
the checked versions and no-network/no-credentials compatibility boundary.

### REQ-I-007 - Support location-independent direct CLI invocation

Human-facing direct CLI commands shall use the exact-version invocation
`npx --yes @kisev/skills-opencode@<version>`. Global scope shall resolve deployment
and lifecycle roots independently of the current working directory. Scope-aware
commands shall default to project scope, accept one `--global`, reject `--scope`,
and reject every option outside the selected command's documented allowlist.

### REQ-I-008 - Provide structured contextual CLI help

Root and contextual `--help` shall describe every direct CLI command and group.
Each command page shall present its own usage, accepted options, behavior, and
examples in separate readable sections. Help shall remain read-only and require
no scope. It shall document project scope as the default and `--global` as the
only direct global selector.

### REQ-I-009 - Unify interactive selectors

Interactive CLI selectors shall share one visual and keyboard contract. Single
selection shall support Up/Down, Enter, and cancellation; multi-selection shall
also support Space toggle, select all, and select none. The installer shall allow
arbitrary command, agent, and plugin subsets while preserving documented defaults.
