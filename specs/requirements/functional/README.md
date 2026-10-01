# Functional Requirements

## Normative Requirements

### REQ-F-001 - Expose the verified capability surface

The repository shall expose exactly the public inventory in
`evals/contracts/public-surfaces.json`: 38 skills, 39 commands, 6 agents, 4
selectable plugins, and 1 package tool.

#### Verification

Compare the contract with `skills/`, `packages/agentomatic/src/catalog.ts`, and
generated package assets; execute the public inventory tests.

### REQ-F-002 - Route work through bounded orchestration

When a package-managed OpenCode task is dispatched, the package shall resolve an eligible host
agent and require a one-use receipt bound to task, requirements, card, revision,
and expiry before execution. Ordinary native subagents outside package-managed
profiles shall remain usable without installed specialist agents or package
report envelopes. A pending routed receipt shall still bind its next dispatch;
ordinary subagents shall not bypass a routed operation.
Independent routed review without an execution card shall accept the generic
review report or the versioned code-review critic receipt transport; the skill
runtime owns its complete evidence validation. Parallel routed calls shall have
separate native call identities, and failed calls shall release their own
active binding without cancelling unrelated calls. Receipt expiry shall gate
launch, not invalidate an already admitted independent review solely because
model execution took longer.
The native context hook shall expose the actual current session identity to
primary and child agents for skill receipts, without granting task or
publication authorization or requiring optional agent profiles.

#### Verification

Routing tests reject stale and replayed receipts and validate independent nested
manager-to-review-to-critic sessions with the installed profile permissions.
Plugin tests also exercise native current/general-purpose subagents with no
specialist profiles and preserve enforcement for managed worker/critic calls.

### REQ-F-003 - Preserve useful partial results

When required evidence is missing, stale, malformed, or contradictory, a
workflow shall return a structured `partial`, `blocked`, or `error` outcome and
shall identify the missing evidence and safe escalation.

#### Verification

Runner regression tests inject incomplete pages, malformed evidence, and stale
bindings and assert non-success outcomes with retained useful partial results.

### REQ-F-004 - Publish one verified release

On a validated release tag, CI shall pass the complete quality gate before any
publication, build the exact tagged Pages distribution and the npm tarballs for
`@kisev/safe-fs`, `@kisev/memomatic`, `@kisev/taskmatic`, and `@kisev/agentomatic`, and bind all
artifacts to one release manifest. Each package keeps its maintained version;
development versions and exact dependency pins follow the manifest's member graph.
The publication channel shall be resolved from the tagged commit and fail closed
otherwise: a revision reachable from `origin/main` publishes npm `latest` and the
Pages root, while a revision reachable only from its `origin/release/vX.Y`
maintenance branch publishes the `vX.Y` npm dist-tag without redeploying Pages.
CI shall verify every member's deployed npm artifact, deployed Pages bytes, npm
integrity, signatures, provenance, imports, and CLI before creating the GitHub
Release. The distribution version and source revision shall match the immutable
tag, and a rerun shall accept only identical previously published bytes.

#### Verification

Release contract tests reject version, tag, provenance, digest, and channel
mismatches. The tag workflow verifies the resolved remote channel before GitHub
Release creation.

Package-member tests verify dependency order, exact pins, and complete publication
of all manifest members before declaring a release successful.

### REQ-F-005 - Archive owned retired assets

When exact-owned retired assets are reconciled, the system shall archive them
content-addressably and preserve unrelated user-owned files and durable state.
Reconcile shall inspect and mutate only package-owned OpenCode assets; portable
skill trees and installer lock files shall not affect its classifications, plan,
conflicts, or operations. Portable skill updates and removals remain
owned by the `skills` CLI.
Human reconcile preview shall be blocked, without an apply step, when
`modified_managed` or `conflicts` is non-empty; it shall list every blocking path
and provide remediation. An actionable clean preview shall retain the
interactive consent contract; a no-op preview shall offer no apply.

#### Verification

Package lifecycle tests cover exact ownership, modified files, portable-tree
independence, no-op previews, and consent-gated apply.

### REQ-F-006 - Manage package-owned profiles safely

Profile mutations shall use preview and confirmed apply phases, exact ownership,
atomic rollback, and restart semantics defined by the package contract.

#### Verification

Agent-profile tests exercise confirmed changes, retained model selections,
collisions, replay, and rollback after injected write failures.

### REQ-F-007 - Provide observational health and inventory

The direct CLI shall expose capability and doctor observations without installing,
repairing, or mutating runtime state.

#### Verification

Doctor tests compare state before and after observations and reject incomplete
facts without repair or state creation.

### REQ-F-008 - Support compatible host integration

The package shall support the declared OpenCode compatibility range and expose
the route tool, plugin exports, and CLI behavior defined by the package
contract.

#### Verification

Package smoke tests load rendered assets through pinned OpenCode versions and
verify exports, CLI help, and agent discovery without provider credentials.

### REQ-F-009 - Publish an isolated development channel

After the complete publication gate succeeds for a push to `dev`, publication
shall update the moving
portable distribution at `https://kisev.github.io/skills/dev` and publish one
unique `@kisev/agentomatic` prerelease under npm dist-tag `dev`. The snapshot
version shall combine the maintained stable base, workflow run number, and source
revision without selecting a future stable SemVer. Development publication shall
not create a GitHub Release or change npm `latest`.

#### Verification

Workflow and release tests verify the `dev` trigger, version derivation, npm
dist-tag, Pages subpath, and isolation from stable publication.

### REQ-F-010 - Provision the persistent npm dependency

A confirmed `install` with core integration selected shall provision the exact
executing package version as a persistent npm dependency in the owning project:
global scope owns `~/.config/opencode`, and project scope owns the nearest npm
project upward from the working directory. Provisioning creates a minimal
`package.json` when the global project has none, pins the dependency with
`npm install --save-exact`, removes a pinned legacy `@kisev/skills-opencode`
dependency in the same pass, and reports the outcome in the applied plan.
The same confirmed run applies the `opencode` `core-plugin` config fragment
through the config-setup executor while keeping package-owned and user-owned
writes in separate transactions. Project scope without an npm project shall
report a manual follow-up instead of creating files. `install --no-dependency`
skips the dependency step, `--no-core` skips the fragment and the dependency,
and `uninstall` never changes the dependency.

#### Verification

Package tests stub the npm runner and verify plan states (`install`, `update`,
`satisfied`, `manual`), package.json creation, argument shape, failure wrapping,
and dependency coupling through preview and apply.

### REQ-F-519 - Maintain change-linked documentation and reusable review evidence

An authorized behavior change shall assess affected canonical contracts,
guides, examples, language mirrors, and navigation, updating them or recording
a concrete no-update reason. Existing prerequisites, limitations, recovery,
compatibility, and rationale shall survive unless the agreed target changes.
The agreed contract is normative; implementation evidence alone shall not weaken it.
The portable specification and documentation skills shall own this trigger
themselves: they activate for the affected canonical and user documentation
steps after a completed authorized behavior change without per-project
instruction files, while a missing `specs/` tree or documentation set is never
created by the trigger alone.

Document `review` metadata shall select dependencies, not assert correctness.
Unmapped changes, including newly added sources, shall require impact assessment.
Portable documentation and specification review shall retain private,
workspace-scoped evidence outside the checkout and reuse compatible prior
results in full, incremental, or unchanged modes. Previous findings, decisions,
and unchecked boundaries shall remain visible. Changed evidence invalidates
affected conclusions; full review requires one independent critic.

#### Verification

`tests/test_documentation_review.py` checks dependency selection, new unmapped
sources, stale finalization, retained limitations, and finding continuity.
Behavioral review evaluates preservation of prerequisites and explanations;
`task docs:check` validates metadata and structure, not semantic truth.

### REQ-F-520 - Preserve atomic private profile transactions

This shared owner consolidates the transaction guarantees formerly repeated
under REQ-F-126 and REQ-F-127, without changing those guarantees.

Confirmed profile saves that also select the default profile shall update profile
and settings atomically with rollback, recover interrupted transactions from a
private schema v3 journal, and store bounded previous bytes in private
content-addressed state files referenced by digest and exact path rather than
inline encoding. Backup cleanup shall follow commit or completed rollback and
shall preserve content still referenced by another journal. Existing schema v2
journals shall remain recoverable under a separate compatible legacy bound. The
runtime shall consume the receipt only after both writes and the report
succeed, their parent directories are fsync-durable, and safe private reads match
all three journal-declared postconditions immediately before receipt creation; a
pre-receipt mismatch shall roll back without a receipt. The runtime shall fsync every transaction
replace, create, and unlink including journal deletion, fsync the receipt
namespace before recovery accepts either commit or rollback state, and report
unavailable POSIX durability primitives or other expected local I/O failures as JSON errors.
Recovery shall accept commit only for an exact receipt whose journal-bound
profile, settings, and report existence and digests match durable files. It shall
never remove an exact durable receipt: intended state shall finish commit, while
prior, mixed, or unknown state shall preserve the receipt, journal, and backups
and fail closed. Without such a receipt, recovery shall finish rollback for prior
or mixed prior/intended state but preserve the journal, backups, and any current
file that matches neither state. Confirmed context saves shall be serialized,
roll back visible context and new report state after pre-receipt fsync, report, or
required marker failure, and create the one-use receipt only at the safe commit
point. A post-link receipt error shall finish as committed only when the exact
receipt and intended context and report digests match. Existing persisted plans
shall remain compatible. Backup paths, digests,
sizes, ownership, and private permissions shall be verified before restoration.
Mutation locking shall use non-blocking POSIX `flock` retries with a five-second
monotonic deadline and reject a lock with more than one hardlink before changing
its mode, while module import and read-only commands remain portable.

#### Verification

`tests/test_team_workflow.py` and the profile transaction regression tests inject
write, fsync, report, and recovery failures and check preserved bytes, exact
receipts, rollback, legacy journals, and rejection of unsafe backup or lock paths.

### REQ-F-547 - Automate a persistent local Mattermost test environment

The repository shall provide an opt-in local Mattermost environment with automatic,
idempotent fixture and credential initialization. Normal runs shall preserve
server data, local skill state, and the separate free zone for manual experiments.
Automated tests may execute publication helpers only against owned local fixtures;
ordinary skill publication remains manual.

The deterministic level shall check the Mattermost reader, publication and triage
runtimes through real APIs, CLI and browser assertions, supplemented by controlled
fault tests. A separate live level shall reuse the repository's host adapters,
require explicit model and budgets, and verify real skill artifacts. Missing
usage or cost evidence shall not count as a successful live budget check.

An explicit digest-confirmed reset shall bind the selected project's resources,
remove its server and local state including the free zone, retain reports, and
initialize again. Normal test failures shall never trigger a reset. Reports shall
distinguish observed results from unverified scenarios and preserve failure evidence.

#### Verification

Run the deterministic suite twice with stable fixture identities and unchanged
free-zone content. Exercise reset on a separately owned disposable project and
verify that the primary project and reports survive. Live tests require actual
configured host/model execution; no hostless result substitutes for them.
