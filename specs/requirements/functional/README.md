# Functional Requirements

## Normative Requirements

### REQ-F-001 - Expose the verified capability surface

The repository shall expose exactly the public inventory in
`evals/contracts/public-surfaces.json`: 38 skills, 38 commands, 6 agents, 3
selectable plugins, and 1 package tool.

#### Verification

Compare the contract with `skills/`, `packages/agentomatic/src/catalog.ts`, and
generated package assets; execute the public inventory tests.

### REQ-F-002 - Route work through bounded orchestration

When an OpenCode task is dispatched, the package shall resolve an eligible host
agent and require a one-use receipt bound to task, requirements, card, revision,
and expiry before execution.

#### Verification

Routing tests reject stale and replayed receipts and validate independent nested
manager-to-review-to-critic sessions with the installed profile permissions.

### REQ-F-003 - Preserve useful partial results

When required evidence is missing, stale, malformed, or contradictory, a
workflow shall return a structured `partial`, `blocked`, or `error` outcome and
shall identify the missing evidence and safe escalation.

#### Verification

Runner regression tests inject incomplete pages, malformed evidence, and stale
bindings and assert non-success outcomes with retained useful partial results.

### REQ-F-004 - Publish one verified release

On a validated release tag, CI shall pass the complete quality gate before any
publication, build the exact tagged Pages distribution and one exact npm tarball,
and bind both to one release manifest. CI shall verify deployed Pages bytes, npm
integrity, signatures, provenance, imports, and CLI before creating the GitHub
Release. The distribution version and source revision shall match the immutable
tag, and a rerun shall accept only identical previously published bytes.

#### Verification

Release contract tests reject version, tag, provenance, and digest mismatches.
The tag workflow verifies both remote channels before GitHub Release creation.

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
