# Interface Requirements

## Public Interfaces

### REQ-I-001 - Skill interface

Each public skill definition shall have an English canonical `SKILL.source.md`
with standards-valid frontmatter and explicit trigger boundaries. Its published
archive shall expose root `SKILL.md`, portable referenced resources, and the
shared interaction/evidence contract. Authored and built skill metadata shall not
carry a version; release identity belongs to distribution metadata and archive
digest. Stable skills shall carry cleanup provenance
`metadata.source: "https://kisev.github.io/skills"`; dev skills shall carry
`metadata.source: "https://kisev.github.io/skills/dev"`. The `goal`,
`task-prepare`, `task-review`, and `task-triage` skills shall
normalize their documented inputs to `work-item/v1` before semantic processing.

Every skill shall reference and bundle the canonical question guidelines for
native-tool and chat questions, its own interviews, missing facts, profile setup,
and confirmations. Before a choice, it shall explain why the question arose,
relevant evidence and assumptions, practical option effects and material risks,
and the basis of any recommendation, proportionate to the consequences. It shall
group only questions whose necessity, wording, options, recommendations, and
context cannot be changed by plausible answers to one another, including custom
or non-recommended answers. It shall wait for prerequisites and rebuild affected
follow-ups from actual answers, without adding questions or authorization gates
when its workflow does not require them.

#### Verification

Built archives pass Agent Skills validation and isolated installation tests.
Question-guideline scenarios check dependent questions and retained user decisions.

### REQ-I-002 - Command interface

Each skill-adapter command shall route to its same-named skill, shall treat
arguments as untrusted input without bypassing the selected contract, and shall
not add state, storage, or publication behavior absent from that contract. Command
selection remains the user's decision: the installer selects command adapters,
not portable skills. Command adapters load an already-installed same-named skill.
Pre-selector guidance shall identify the exact configured `skills` CLI version
and the supported Pages source, and previews shall remain read-only summaries
that end with an apply hint requiring interactive confirmation or `--yes`.

Package commands such as `rtk-stats` have their own capability contract and do
not load a same-named skill.

#### Verification

Rendered command tests verify native skill loading, argument boundaries, and
missing-skill guidance; package-command tests verify direct exact-version invocation.

### REQ-I-003 - Package tool interface

The core plugin shall register exactly the `route` package tool with versioned
structured results and one-use routing receipts.

#### Verification

Routing tests reject expired, replayed, and task-mismatched receipts and compare
registered package tools with the public inventory.

### REQ-I-004 - Plugin interface

The package shall export the core infrastructure plugin and exactly three
selectable plugin modules: `rules-injector`, `rtk`, and `zed-bell`.

#### Verification

Public inventory checks compare package exports with all documented plugins;
plugin tests verify disabled behavior and registered tools.

### REQ-I-005 - Evidence interface

Tests and evals shall expose stable selectors, scenario IDs, invariant paths,
and bounded hostless execution metadata. A scenario may opt into structured
per-case outcomes. For such a scenario, trusted-live observation shall contain
exactly one correct outcome for every declared case, while hostless evaluation
shall validate only the scenario contract and shall not present fixture outcomes
as observed model behavior. Existing selection-only scenarios remain valid.

#### Verification

Eval validation rejects incomplete per-case outcomes and stale scenario digests;
offline results explicitly identify fixture-only evidence.

### REQ-I-006 - Compatibility interface

The package shall declare `@opencode-ai/plugin >=1.18.29 <1.19.0` and preserve
the checked versions and no-network/no-credentials compatibility boundary.

#### Verification

The compatibility matrix loads exports and host commands at every declared
tested version without live providers or credentials.

### REQ-I-007 - Support location-independent direct CLI invocation

Human-facing direct CLI commands shall use the exact-version invocation
`npx --yes @kisev/agentomatic@<version>`. Global scope shall resolve deployment
and lifecycle roots independently of the current working directory. Scope-aware
commands shall default to project scope, accept one `--global`, reject `--scope`,
and reject every option outside the selected command's documented allowlist.

#### Verification

CLI tests invoke commands from unrelated working directories and reject unsupported
options; rendered package commands contain the executing package version.

### REQ-I-008 - Provide structured contextual CLI help

Root and contextual `--help` shall describe every direct CLI command and group.
Each command page shall present its own usage, accepted options, behavior, and
examples in separate readable sections. Help shall remain read-only and require
no scope. It shall document project scope as the default and `--global` as the
only direct global selector.

#### Verification

Contextual-help tests enumerate public command pages and assert read-only help
behavior, scope defaults, and command-specific flags.

### REQ-I-009 - Unify interactive selectors

Interactive CLI selectors shall share one visual and keyboard contract. Single
selection shall support Up/Down, Enter, and cancellation; multi-selection shall
also support Space toggle, select all, and select none. The installer shall allow
arbitrary command, agent, and plugin subsets while preserving documented defaults.

#### Verification

Selector tests cover keyboard navigation, toggles, cancellation, empty selections,
and installer defaults.

### REQ-I-010 - Skill relations interface

`shared/skill-relations.json` shall be the single source of truth for the
cross-skill relation graph. Each entry shall name two existing skills, one
relation type, and a one-line English reason. The portable build shall validate
the graph, reject unknown skill names, self-relations, and duplicates, and
render each skill's relations into its built `SKILL.md` "Related skills"
section, which points to the source recorded in the skill's `metadata.source`.

#### Verification

Build tests reject unknown nodes, self-relations, and duplicate edges and verify
that each materialized archive remains independently installable.

### REQ-I-419 - Share CLI parsing and observability without another npm package

Agentomatic, memomatic and taskmatic shall use Commander and one authored common
CLI runtime in `shared/references/cli_runtime.ts`. `shared/manifest.json` declares
the generated package copies; public generation tasks materialize and verify
them. Each existing npm archive includes its compiled copy and declares its own
Commander dependency. No fourth application or new npm name is introduced.

Commands expose contextual help, environment bindings, choices, examples and
configuration precedence: CLI > environment > JSON file > defaults. Help/version
do not start models or create application state. Common result/log options keep
stdout machine-readable when selected and stderr diagnostic; MCP stdout remains
protocol-only. JSON logs and non-TTY defaults do not contain animation. Terminal
progress reflects known counts and elapsed wait time, with `NO_COLOR` respected.
Agentomatic retains its wizard, contextual guidance, confirmation boundaries and
legacy versioned JSON error envelopes; configuration and environment cannot supply
implicit `--yes` approval.

The runtime requires Node.js 22.13+. Memomatic/taskmatic parser errors exit 2,
operational/configuration failures 1, timeout 124, interruption 130 and success 0.
Agentomatic retains its existing doctor/error codes. Application configuration
overrides do not persist themselves or restart services.

#### Verification

CLI subprocess tests check contextual non-mutating help/status, unknown options,
CLI/env/file precedence, protocol-only stdout and configuration unable to confirm
mutations. Materialization tests compare all generated copies with the authored
source. Packed-package smoke tests cover the existing npm graph.
