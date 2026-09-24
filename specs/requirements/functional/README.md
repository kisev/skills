# Functional Requirements

## Normative Requirements

### REQ-F-001 - Expose the verified capability surface

The repository shall expose exactly the public inventory in
`evals/contracts/public-surfaces.json`: 27 skills, 27 commands, 6 agents, 3
selectable plugins, and 1 package tool.

#### Verification

Compare the contract with `skills/`, `packages/opencode/src/catalog.ts`, and
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
digest, conflicts, or operations. Portable skill updates and removals remain
owned by the `skills` CLI.
Human reconcile preview shall be blocked, without an Apply command, when
`modified_managed` or `conflicts` is non-empty; it shall list every blocking path
and provide remediation. An actionable clean preview shall retain the digest and
exact Apply command contract; a no-op preview shall issue no receipt or Apply
command. Every new dry-run in one project or global scope shall
supersede the previous unconsumed receipt across installer, reconcile, profile,
and critic domains; deterministic plan and unique confirmation digests are
separate, and superseded confirmation fails closed.

#### Verification

Package lifecycle tests cover exact ownership, modified files, portable-tree
independence, no-op previews, and cross-domain confirmation supersession.

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
facts without repair or receipt creation.

### REQ-F-008 - Support compatible host integration

The package shall support the declared OpenCode compatibility range and expose
the route tool, plugin exports, and CLI behavior defined by the package
contract.

#### Verification

Package smoke tests load rendered assets through pinned OpenCode versions and
verify exports, CLI help, and agent discovery without provider credentials.
